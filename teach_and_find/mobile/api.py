"""Authenticated local HTTP/WebSocket adapter over shared operator services."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
import hmac
import io
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4
import zipfile
from typing import Literal

import cv2
import numpy as np
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from teach_and_find.config import Settings
from teach_and_find.inspection import InspectionService
from teach_and_find.library import build_library, utc_now
from teach_and_find.mobile.runtime import OperatorRuntime
from teach_and_find.storage import AssistantError, EvidenceStore
from teach_and_find.room import RoomService
from teach_and_find.scene import SceneService
from teach_and_find.memory_service import MemoryService
from teach_and_find.vision_service import VisionService
from teach_and_find.search_service import SearchService
from teach_and_find.tracking_service import TrackingService, mask_bytes, owner_key


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PairRequest(StrictModel):
    token: str = Field(min_length=1, max_length=256)


class RenameRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class ChecklistItem(StrictModel):
    object_id: str
    station: str = Field(min_length=1, max_length=120)


class ChecklistRequest(RenameRequest):
    items: list[ChecklistItem] = Field(min_length=1, max_length=50)


class ObservationRequest(StrictModel):
    object_id: str
    frame_id: str
    station: str = Field(min_length=1, max_length=120)
    assertion: str
    visibility: float = Field(default=1.0, ge=0, le=1)


class ArmRequest(StrictModel):
    type: str
    challenge: str = Field(max_length=100)
    frame_id: str = Field(max_length=150)


class FrameRequest(StrictModel):
    frame_id: str = Field(min_length=1, max_length=150)


class SceneConfirmation(StrictModel):
    proposal_index: int = Field(ge=0, strict=True)
    object_id: str
    station: str = Field(min_length=1, max_length=120)


class RoomQuery(StrictModel):
    kind: Literal["last_seen", "seen_during", "stayed_at"]
    object_id: str
    station: str | None = None
    start_at: str | None = None
    end_at: str | None = None


class DriveRequest(ArmRequest):
    epoch: str = Field(max_length=100)
    sequence: int = Field(ge=0, strict=True)
    forward: float = Field(ge=-1, le=1)
    turn: float = Field(ge=-1, le=1)


class MemoryViewRequest(StrictModel):
    region_name: str = Field(min_length=1, max_length=120)
    viewpoint_name: str = Field(min_length=1, max_length=120)


class MemoryEpisodeRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class MemoryCaptureRequest(FrameRequest):
    episode_id: str = Field(min_length=1, max_length=100)
    view_id: str = Field(min_length=1, max_length=100)
    request_key: str = Field(min_length=1, max_length=120)


class MemoryQuestionRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    episode_ids: list[str] = Field(min_length=1, max_length=24)
    request_key: str = Field(min_length=1, max_length=120)
    scope: Literal["recorded_memory"] = "recorded_memory"


class VisionRequest(FrameRequest):
    object_ids: list[str] = Field(min_length=1, max_length=8)
    request_key: str = Field(min_length=1, max_length=120)


class TrackingAnchorRequest(FrameRequest):
    request_key: str = Field(min_length=1, max_length=120)


class TrackingPromptRequest(StrictModel):
    revision: int = Field(ge=0, strict=True)
    points: list[tuple[float, float]] = Field(default_factory=list, max_length=32)
    labels: list[Literal[0, 1]] = Field(default_factory=list, max_length=32)
    box: tuple[float, float, float, float] | None = None


class TrackingStartRequest(StrictModel):
    revision: int = Field(ge=0, strict=True)
    candidate: int = Field(ge=0, le=2, strict=True)


class SearchRequest(StrictModel):
    object_id: str = Field(min_length=1, max_length=128)
    request_key: str = Field(min_length=1, max_length=128)


class Sessions:
    def __init__(self, settings: Settings):
        self.token = settings.mobile.pairing_token or secrets.token_urlsafe(24)
        self.lifetime = settings.mobile.session_lifetime_s
        self.sessions: dict[str, float] = {}
        self.attempts: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def pair(self, token: str, address: str) -> str:
        with self.lock:
            now = time.monotonic()
            attempts = [
                stamp for stamp in self.attempts.get(address, []) if now - stamp < 60
            ]
            if len(attempts) >= 10:
                raise HTTPException(
                    429, "Too many pairing attempts; try again in a minute."
                )
            attempts.append(now)
            self.attempts[address] = attempts
            if not hmac.compare_digest(token, self.token):
                raise HTTPException(401, "Pairing code is incorrect.")
            session = secrets.token_urlsafe(24)
            self.sessions = {
                key: expiry for key, expiry in self.sessions.items() if expiry > now
            }
            self.sessions[session] = now + self.lifetime
            return session

    def valid(self, session: str | None) -> bool:
        with self.lock:
            return (
                session is not None and self.sessions.get(session, 0) > time.monotonic()
            )


def same_origin(headers) -> bool:
    origin = headers.get("origin")
    return not origin or (
        urlsplit(origin).scheme in {"http", "https"}
        and urlsplit(origin).netloc == headers.get("host")
    )


def create_app(
    settings: Settings | None = None, *, runtime: OperatorRuntime | None = None
) -> FastAPI:
    cfg = settings or Settings()
    robot = runtime or OperatorRuntime(cfg)
    sessions = Sessions(cfg)

    @asynccontextmanager
    async def lifespan(app):
        robot.start()
        try:
            yield
        finally:
            await run_in_threadpool(robot.close)

    app = FastAPI(
        title="PuppyPi Operator",
        version="1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.runtime = robot
    app.state.sessions = sessions

    @contextmanager
    def services():
        # Each request owns its connection in the thread where it is used.
        with EvidenceStore(cfg.assistant.data_dir) as store:
            library = build_library(store, cfg)
            yield library, InspectionService(library)

    def authorized(request: Request) -> str:
        session = request.cookies.get("puppypi_session")
        if not sessions.valid(session):
            raise HTTPException(401, "Pair this device with the operator host.")
        return session

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(
            request.headers
        ):
            return JSONResponse(
                {"detail": "Cross-origin requests are not allowed."}, status_code=403
            )
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid content length."}, status_code=400)
        if length > cfg.mobile.max_request_bytes:
            return JSONResponse({"detail": "Upload is too large."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AssistantError)
    async def assistant_error(request, error):
        status = (
            503
            if error.code == "TRACKING_WORKER_UNAVAILABLE"
            else 403
            if error.code == "TRACKING_OWNERSHIP"
            else 409
            if error.code
            in {
                "TRACKING_CAPACITY",
                "TRACKING_REVISION_CONFLICT",
                "TRACKING_STATIONARY_ONLY",
            }
            else 404
            if error.code.endswith("NOT_FOUND")
            else 409
            if error.code
            in {
                "FRAME_UNAVAILABLE",
                "STALE_FRAME",
                "CONFIRMATION_CONFLICT",
                "IDEMPOTENCY_CONFLICT",
                "CAPTURE_CONFLICT",
            }
            else 422
        )
        return JSONResponse(
            {"error": {"code": error.code, "message": str(error)}}, status_code=status
        )

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, error):
        return JSONResponse(
            {
                "error": {
                    "code": "DATABASE_ERROR",
                    "message": "Unable to access evidence storage.",
                }
            },
            status_code=503,
        )

    def cancel_search(reason):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            SearchService(store, cfg).cancel_all(reason)

    @app.get("/api/search")
    def search_overview(session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return SearchService(store, cfg).overview()

    @app.post("/api/search", status_code=202)
    def search_start(body: SearchRequest, session=Depends(authorized)):
        from teach_and_find.sim.search_device import fixture_calibration

        if cfg.mobile.robot_mode != "search-sim":
            raise AssistantError(
                "SEARCH_CALIBRATION_UNSUPPORTED",
                "Launch the explicitly calibrated search-sim backend.",
            )
        with robot.lock:
            if robot.gate.owner is not None:
                raise AssistantError(
                    "CONTROL_BUSY",
                    "Disarm manual control before starting a station search.",
                )
            if robot.tracking_feed:
                from teach_and_find.tracking_service import ACTIVE

                with EvidenceStore(cfg.assistant.data_dir) as tracking_store:
                    if tracking_store.db.execute(
                        "SELECT 1 FROM tracking_sessions WHERE status IN (?,?,?,?,?)",
                        ACTIVE,
                    ).fetchone():
                        raise AssistantError(
                            "TRACKING_STATIONARY_ONLY",
                            "End stationary interactive tracking before search.",
                        )
            robot.frame(require_fresh=True)
            with EvidenceStore(cfg.assistant.data_dir) as store:
                return SearchService(store, cfg).create(
                    body.object_id,
                    session,
                    body.request_key,
                    fixture_calibration(),
                    robot.device.mode,
                    motion_generation=robot.motion_generation,
                )

    @app.get("/api/search/{identifier}")
    def search_detail(
        identifier: str, export: bool = False, session=Depends(authorized)
    ):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return SearchService(store, cfg).detail(identifier, export=export)

    @app.post("/api/search/{identifier}/cancel")
    def search_cancel(identifier: str, session=Depends(authorized)):
        # Stop/wake control before any potentially blocking database operation.
        robot.stop("operator_cancelled_search")
        with EvidenceStore(cfg.assistant.data_dir) as store:
            service = SearchService(store, cfg)
            result = service.cancel_one(identifier)
        return {"id": identifier, "status": result["status"]}

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/timing")
    def timing(session=Depends(authorized)):
        return {
            "host_unix_ms": time.time() * 1000,
            "host_monotonic_ns": time.monotonic_ns(),
        }

    @app.get("/api/tracking")
    def tracking_overview(session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return TrackingService(store, cfg).overview(robot.device.mode)

    @app.post("/api/tracking/anchors", status_code=202)
    def tracking_anchor(body: TrackingAnchorRequest, session=Depends(authorized)):
        with robot.lock:
            if robot.gate.owner is not None:
                raise AssistantError(
                    "TRACKING_STATIONARY_ONLY",
                    "Disarm motion before selecting a target.",
                )
            frame, _ = robot.frame(body.frame_id, require_fresh=True)
            with EvidenceStore(cfg.assistant.data_dir) as store:
                return TrackingService(store, cfg).pin(
                    frame, robot.device.mode, session, body.request_key
                )

    @app.get("/api/tracking/sessions/{sid}")
    def tracking_session(sid: str, after: int = -1, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            svc = TrackingService(store, cfg)
            row = svc.row(sid, robot.device.mode)
            if row["owner"] == owner_key(session):
                with store.db:
                    store.db.execute(
                        "UPDATE tracking_sessions SET lease_until=? WHERE id=?",
                        (time.time() + cfg.tracking.owner_lease_s, sid),
                    )
            return svc.get(sid, robot.device.mode, after)

    @app.post("/api/tracking/sessions/{sid}/prompts", status_code=202)
    def tracking_prompt(
        sid: str, body: TrackingPromptRequest, session=Depends(authorized)
    ):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return TrackingService(store, cfg).prompt(
                sid,
                robot.device.mode,
                session,
                body.revision,
                body.points,
                body.labels,
                body.box,
            )

    @app.post("/api/tracking/sessions/{sid}/start", status_code=202)
    def tracking_start(
        sid: str, body: TrackingStartRequest, session=Depends(authorized)
    ):
        with robot.lock:
            if robot.gate.owner is not None:
                raise AssistantError(
                    "TRACKING_STATIONARY_ONLY", "Disarm motion before tracking."
                )
            with EvidenceStore(cfg.assistant.data_dir) as store:
                return TrackingService(store, cfg).start(
                    sid, robot.device.mode, session, body.revision, body.candidate
                )

    @app.post("/api/tracking/sessions/{sid}/stop")
    def tracking_stop(sid: str, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return TrackingService(store, cfg).stop(sid, robot.device.mode, session)

    @app.get("/api/tracking/masks/{digest}")
    def tracking_mask(digest: str, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return Response(mask_bytes(store, digest), media_type="image/png")

    @app.post("/api/session")
    def pair(body: PairRequest, request: Request, response: Response):
        session = sessions.pair(
            body.token, request.client.host if request.client else "local"
        )
        response.set_cookie(
            "puppypi_session",
            session,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=int(sessions.lifetime),
        )
        return {"paired": True}

    @app.delete("/api/session")
    def logout(response: Response, session=Depends(authorized)):
        with sessions.lock:
            sessions.sessions.pop(session, None)
        robot.stop("operator_signed_out")
        cancel_search("operator_signed_out")
        response.delete_cookie("puppypi_session")
        return {"paired": False}

    @app.get("/api/state")
    def state(session=Depends(authorized)):
        return robot.status()

    @app.get("/api/frame.jpg")
    def frame(id: str | None = None, session=Depends(authorized)):
        sample, payload = robot.frame(id)
        return Response(
            payload,
            media_type="image/jpeg",
            headers={
                "X-Frame-Id": sample.frame_id,
                "X-Captured-At": sample.captured_at,
                "X-Host-Sent-Unix-Ms": str(time.time() * 1000),
            },
        )

    @app.post("/api/stop")
    def stop(session=Depends(authorized)):
        robot.stop()
        cancel_search("operator_stop")
        return {"requested": "stop", "physical_result": "unverified"}

    @app.get("/api/objects")
    def objects(archived: bool = False, session=Depends(authorized)):
        with services() as (library, _):
            return library.list(include_archived=archived)

    @app.post("/api/objects")
    async def teach(
        name: str = Form(...),
        files: list[UploadFile] = File(...),
        session=Depends(authorized),
    ):
        if not 1 <= len(files) <= 8:
            raise HTTPException(422, "Choose one to eight reference crops.")
        images = []
        for upload in files:
            data = await upload.read(cfg.mobile.max_upload_bytes + 1)
            await upload.close()
            if len(data) > cfg.mobile.max_upload_bytes:
                raise HTTPException(413, "Image exceeds the upload limit.")
            try:
                with Image.open(io.BytesIO(data)) as header:
                    if header.format not in {"PNG", "JPEG"}:
                        raise ValueError("Unsupported image format.")
                    if header.width * header.height > cfg.mobile.max_image_pixels:
                        raise ValueError("Image dimensions exceed the limit.")
                    header.verify()
                image = cv2.imdecode(
                    np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR
                )
                if image is None:
                    raise ValueError("Unreadable image.")
            except (ValueError, OSError, Image.DecompressionBombError) as error:
                raise HTTPException(
                    422, "Use a valid, reasonably sized PNG or JPEG image."
                ) from error
            images.append(image)

        def enroll():
            with services() as (library, _):
                return library.teach(name, images)

        result = await run_in_threadpool(enroll)
        robot.event("object_taught", f"Enrolled {result['name']}.")
        return result

    @app.patch("/api/objects/{object_id}")
    def rename(object_id: str, body: RenameRequest, session=Depends(authorized)):
        with services() as (library, _):
            return library.rename(object_id, body.name)

    @app.delete("/api/objects/{object_id}")
    def archive(object_id: str, session=Depends(authorized)):
        with services() as (library, _):
            return library.archive(object_id)

    @app.get("/api/objects/{object_id}/history")
    def history(object_id: str, session=Depends(authorized)):
        with services() as (library, _):
            return {
                "observations": library.history(
                    object_id, limit=cfg.assistant.history_limit
                ),
                "last_seen": library.last_seen(object_id, mode=robot.device.mode),
                "automatic_sightings": [
                    json.loads(row[0])
                    for row in library.store.db.execute(
                        "SELECT record_json FROM model_sightings WHERE object_id=? ORDER BY captured_at DESC LIMIT ?",
                        (object_id, cfg.assistant.history_limit),
                    )
                ],
            }

    @app.get("/api/evidence/{digest}")
    def evidence(digest: str, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return Response(store.image_bytes(digest), media_type="image/png")

    @app.post("/api/observations")
    def observe(body: ObservationRequest, session=Depends(authorized)):
        sample, _ = robot.frame(body.frame_id, require_fresh=True)
        with services() as (library, _):
            observation = library.observe(
                body.object_id,
                body.station,
                body.assertion,
                sample.image,
                sample.captured_at,
                visibility=body.visibility,
                mode=robot.device.mode,
                source="operator",
                provenance=sample.provenance,
            )
        robot.event(
            "observation_saved",
            f"Operator recorded {body.assertion} at {body.station}.",
        )
        return observation

    @app.get("/api/room")
    def room(session=Depends(authorized)):
        with services() as (library, _):
            return RoomService(library).overview(mode=robot.device.mode)

    @app.get("/api/implementation")
    def implementation(session=Depends(authorized)):
        from teach_and_find.implementation import implementation_summary

        return implementation_summary(cfg, robot.device.mode)

    @app.post("/api/room/queries")
    def room_query(body: RoomQuery, session=Depends(authorized)):
        with services() as (library, _):
            return RoomService(library).query(
                **body.model_dump(), mode=robot.device.mode
            )

    @app.post("/api/room/analyses")
    def analyze_scene(body: FrameRequest, session=Depends(authorized)):
        sample, _ = robot.frame(body.frame_id, require_fresh=True)
        with services() as (library, _):
            return SceneService(library).analyze(sample, mode=robot.device.mode)

    @app.get("/api/room/analyses/{analysis_id}")
    def scene_analysis(analysis_id: str, session=Depends(authorized)):
        with services() as (library, _):
            return SceneService(library).get(analysis_id, mode=robot.device.mode)

    @app.post("/api/room/analyses/{analysis_id}/confirm")
    def confirm_scene(
        analysis_id: str, body: SceneConfirmation, session=Depends(authorized)
    ):
        with services() as (library, _):
            return SceneService(library).confirm(
                analysis_id, **body.model_dump(), mode=robot.device.mode
            )

    def memory_dispatch(job):
        from teach_and_find.memory_queue import dispatch

        # The durable row is an outbox. If dispatch fails the worker heartbeat
        # will republish it; do not replace it with a synchronous/fake result.
        try:
            dispatch(cfg, job["id"])
        except (ImportError, OSError, sqlite3.Error):
            pass
        return job

    @app.get("/api/memory")
    def memory_overview(session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return MemoryService(store, cfg).overview(robot.device.mode)

    @app.post("/api/memory/views")
    def memory_view(body: MemoryViewRequest, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return MemoryService(store, cfg).register_view(**body.model_dump())

    @app.post("/api/memory/episodes")
    def memory_episode(body: MemoryEpisodeRequest, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return MemoryService(store, cfg).episode(body.name, robot.device.mode)

    @app.post("/api/memory/captures", status_code=202)
    def memory_capture(body: MemoryCaptureRequest, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            service = MemoryService(store, cfg)
            service.require_enabled()
            request = {
                "frame_id": body.frame_id,
                "episode_id": body.episode_id,
                "view_id": body.view_id,
            }
            job = service.existing(
                robot.device.mode, body.request_key, "capture", request
            )
            if job is None:
                sample, _ = robot.frame(body.frame_id, require_fresh=True)
                job = service.capture(
                    sample,
                    body.episode_id,
                    body.view_id,
                    body.request_key,
                    robot.device.mode,
                )
        return memory_dispatch(job)

    @app.post("/api/memory/questions", status_code=202)
    def memory_question(body: MemoryQuestionRequest, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            job = MemoryService(store, cfg).question(
                body.question, body.episode_ids, body.request_key, robot.device.mode
            )
        return memory_dispatch(job)

    @app.get("/api/memory/jobs/{job_id}")
    def memory_job(job_id: str, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return MemoryService(store, cfg).job(job_id, robot.device.mode)

    @app.post("/api/memory/jobs/{job_id}/cancel")
    def memory_cancel(job_id: str, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return MemoryService(store, cfg).cancel(job_id, robot.device.mode)

    @app.get("/api/vision")
    def vision_overview(session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return VisionService(store, cfg).overview(robot.device.mode)

    @app.post("/api/vision/jobs", status_code=202)
    def vision_create(body: VisionRequest, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            service = VisionService(store, cfg)
            request = {"frame_id": body.frame_id, "object_ids": body.object_ids}
            job = service.jobs.existing(
                robot.device.mode, body.request_key, "vision", request
            )
            if job is None:
                frames = robot.frame_window(body.frame_id)
                job = service.enqueue(
                    frames, body.object_ids, body.request_key, robot.device.mode
                )
        from teach_and_find.memory_queue import dispatch

        try:
            dispatch(cfg, job["id"], "vision")
        except (ImportError, OSError, sqlite3.Error):
            # Durable outbox remains queued; the vision heartbeat retries delivery.
            pass
        return job

    @app.get("/api/vision/jobs/{job_id}")
    def vision_job(job_id: str, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return VisionService(store, cfg).job(job_id, robot.device.mode)

    @app.post("/api/vision/jobs/{job_id}/cancel")
    def vision_cancel(job_id: str, session=Depends(authorized)):
        with EvidenceStore(cfg.assistant.data_dir) as store:
            return VisionService(store, cfg).cancel(job_id, robot.device.mode)

    @app.get("/api/checklists")
    def checklists(session=Depends(authorized)):
        with services() as (_, inspection):
            return inspection.list_checklists()

    @app.post("/api/checklists")
    def create_checklist(body: ChecklistRequest, session=Depends(authorized)):
        with services() as (_, inspection):
            return inspection.create_checklist(
                body.name, [(item.object_id, item.station) for item in body.items]
            )

    @app.post("/api/checklists/{checklist_id}/inspect")
    def inspect(checklist_id: str, session=Depends(authorized)):
        with services() as (_, inspection):
            result = inspection.run(checklist_id, mode=robot.device.mode)
        robot.event(
            "inspection_completed", "Recorded-evidence checklist assessment completed."
        )
        return result

    @app.get("/api/reports")
    def reports(session=Depends(authorized)):
        with services() as (_, inspection):
            return [
                json.loads(row[0])
                for row in inspection.store.db.execute(
                    "SELECT report_json FROM inspection_reports ORDER BY created_at DESC LIMIT 30"
                )
            ]

    @app.get("/api/reports/{report_id}/download")
    def download_report(report_id: str, session=Depends(authorized)):
        with services() as (_, inspection), tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "report"
            inspection.export(report_id, directory)
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(directory.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(directory))
            return Response(
                output.getvalue(),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="puppypi-report-{report_id}.zip"'
                },
            )

    @app.post("/api/demo")
    def demo(session=Depends(authorized)):
        if robot.device.mode != "synthetic":
            raise HTTPException(409, "Demo data is only available in synthetic mode.")
        with services() as (library, inspection):
            if library.list(include_archived=True):
                raise HTTPException(409, "Demo data requires an empty library.")
            from teach_and_find.sim.world3d import (
                build_object_catalog,
                render_teaching_views,
            )

            catalog = build_object_catalog()
            items = []
            for key, assertion, visibility in (
                ("secret_box_1", "present", 1.0),
                ("blue_tool_case", "absent", 1.0),
                ("emerald_med_kit", "unknown", 0.2),
            ):
                views = render_teaching_views(
                    catalog[key], cfg.camera, rng=np.random.default_rng(7)
                )
                obj = library.teach(
                    catalog[key].display_name,
                    [crop for _, crop in views],
                    [angle for angle, _ in views],
                )
                sample = views[2][1].copy()
                if assertion == "absent":
                    sample[:] = 230
                elif assertion == "unknown":
                    sample[:, : int(sample.shape[1] * 0.8)] = 50
                library.observe(
                    obj["id"],
                    "Station_A",
                    assertion,
                    sample,
                    utc_now(),
                    visibility=visibility,
                    source="synthetic",
                    mode="synthetic",
                    provenance={"source": "scripted_demo_assertion"},
                )
                items.append((obj["id"], "Station_A"))
            checklist = inspection.create_checklist("Workbench readiness", items)
            report = inspection.run(checklist["id"], mode="synthetic")
        robot.event("demo_loaded", "Synthetic library and inspection evidence created.")
        return {"checklist": checklist, "report": report}

    @app.websocket("/api/live")
    async def live(socket: WebSocket):
        session = socket.cookies.get("puppypi_session")
        if not sessions.valid(session) or not same_origin(socket.headers):
            await socket.close(code=1008)
            return
        owner = str(uuid4())
        await socket.accept()
        try:
            while sessions.valid(session):
                await socket.send_json({"type": "status", **robot.status(owner)})
                try:
                    message = await asyncio.wait_for(
                        socket.receive_json(), timeout=cfg.mobile.control_tick_s
                    )
                except asyncio.TimeoutError:
                    continue
                try:
                    if not isinstance(message, dict):
                        raise AssistantError(
                            "INVALID_MESSAGE", "Expected a control object."
                        )
                    if message.get("type") == "arm":
                        parsed = ArmRequest.model_validate(message)
                        search_id = socket.query_params.get("search_id")
                        generation = None
                        with EvidenceStore(cfg.assistant.data_dir) as store:
                            if search_id:
                                task = store.db.execute(
                                    "SELECT status,payload_json FROM searches WHERE id=?",
                                    (search_id,),
                                ).fetchone()
                                if task is None or task["status"] != "running":
                                    raise AssistantError(
                                        "SEARCH_NOT_RUNNING",
                                        "Search authority requires a running task.",
                                    )
                                generation = json.loads(task["payload_json"]).get(
                                    "motion_generation"
                                )
                                if not generation:
                                    raise AssistantError(
                                        "SEARCH_AUTHORITY_MISSING",
                                        "Search has no current runtime motion authority.",
                                    )
                            active = store.db.execute(
                                "SELECT id FROM searches WHERE status IN ('queued','running')"
                            ).fetchone()
                            if (
                                active
                                and socket.query_params.get("search_id") != active[0]
                            ):
                                raise AssistantError(
                                    "SEARCH_BUSY",
                                    "Stop the station search before manual takeover.",
                                )
                        result = robot.arm(
                            owner, parsed.challenge, parsed.frame_id, generation
                        )
                        await socket.send_json({"type": "armed", **result})
                    elif message.get("type") == "search_disarm":
                        if not socket.query_params.get("search_id"):
                            raise AssistantError(
                                "SEARCH_AUTHORITY_MISSING",
                                "Segment disarm is reserved for search control.",
                            )
                        acknowledged = robot.disarm_search_segment(owner)
                        if not await asyncio.to_thread(acknowledged.wait, 1.0):
                            raise AssistantError(
                                "SEARCH_STOP_UNACKNOWLEDGED",
                                "Zero-motion command was not acknowledged.",
                            )
                        await socket.send_json(
                            {"type": "search_disarmed", "acknowledged_at": utc_now()}
                        )
                    elif message.get("type") == "drive":
                        parsed = DriveRequest.model_validate(message)
                        robot.drive(owner, parsed.model_dump())
                    elif message.get("type") == "stop":
                        robot.stop()
                        cancel_search("operator_stop")
                    else:
                        raise AssistantError(
                            "INVALID_MESSAGE", "Unsupported operator action."
                        )
                except (AssistantError, ValidationError) as error:
                    robot.disconnect(owner)
                    await socket.send_json(
                        {
                            "type": "error",
                            "code": getattr(error, "code", "INVALID_MESSAGE"),
                            "message": str(error)
                            if isinstance(error, AssistantError)
                            else "Invalid control message; controls disarmed.",
                        }
                    )
            await socket.close(code=1008)
        except (WebSocketDisconnect, RuntimeError, OSError, ValueError):
            pass
        finally:
            robot.disconnect(owner)

    static = Path(__file__).parent / "static"
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="mobile")
    else:

        @app.get("/")
        def missing_frontend():
            return JSONResponse(
                {"message": "Build the mobile client with make app-build."},
                status_code=503,
            )

    return app
