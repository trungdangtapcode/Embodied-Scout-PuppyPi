"""Local operator CLI for object memory and evidence-based inspection."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys

import cv2

from teach_and_find.config import Settings
from teach_and_find.inspection import InspectionService
from teach_and_find.library import build_library
from teach_and_find.storage import AssistantError, EvidenceStore


def read_image(path: str):
    image = cv2.imread(path)
    if image is None:
        raise AssistantError("INVALID_IMAGE", "Cannot read the requested image.")
    return image


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--data-dir", help="Override TEACH_FIND_DATA_DIR.")
    commands = root.add_subparsers(dest="command", required=True)
    objects = commands.add_parser("objects").add_subparsers(
        dest="action", required=True
    )
    teach = objects.add_parser(
        "teach", help="Enroll reference crops or replace an object's references."
    )
    teach.add_argument("--name", required=True)
    teach.add_argument("--images", nargs="+", required=True)
    teach.add_argument("--angles", nargs="+", type=float)
    teach.add_argument("--object-id")
    listing = objects.add_parser("list")
    listing.add_argument("--archived", action="store_true")
    rename = objects.add_parser("rename")
    rename.add_argument("object_id")
    rename.add_argument("name")
    archive = objects.add_parser("archive")
    archive.add_argument("object_id")
    match = objects.add_parser(
        "match", help="Rank candidate matches; does not confirm or record a sighting."
    )
    match.add_argument("image")
    observe = commands.add_parser(
        "observe", help="Record an operator annotation with an image and capture time."
    )
    observe.add_argument("--object-id", required=True)
    observe.add_argument("--station", required=True)
    observe.add_argument(
        "--assertion", choices=["present", "absent", "unknown"], required=True
    )
    observe.add_argument("--image", required=True)
    observe.add_argument("--captured-at", required=True)
    observe.add_argument("--quality", type=float, default=1.0)
    observe.add_argument("--visibility", type=float, default=1.0)
    observe.add_argument(
        "--mode", choices=["synthetic", "replay", "physical"], default="replay"
    )
    history = commands.add_parser("history")
    history.add_argument("object_id")
    history.add_argument("--limit", type=int)
    last = commands.add_parser("last-seen")
    last.add_argument("object_id")
    last.add_argument(
        "--mode", choices=["synthetic", "replay", "physical"], default="replay"
    )
    checklists = commands.add_parser("checklists").add_subparsers(
        dest="action", required=True
    )
    create = checklists.add_parser("create")
    create.add_argument("--name", required=True)
    create.add_argument(
        "--item", action="append", required=True, metavar="OBJECT_ID@STATION"
    )
    checklists.add_parser("list")
    inspect = commands.add_parser(
        "inspect", help="Assess recorded observations without moving the robot."
    )
    inspect.add_argument("checklist_id")
    inspect.add_argument(
        "--mode", choices=["synthetic", "replay", "physical"], default="replay"
    )
    inspect.add_argument("--as-of")
    inspect.add_argument("--max-age", type=float)
    export = commands.add_parser("export")
    export.add_argument("report_id")
    export.add_argument("--output", type=Path, required=True)
    return root


def dispatch(args, library, inspection):
    if args.command == "objects":
        if args.action == "teach":
            return library.teach(
                args.name,
                [read_image(path) for path in args.images],
                args.angles,
                object_id=args.object_id,
            )
        if args.action == "list":
            return library.list(include_archived=args.archived)
        if args.action == "rename":
            return library.rename(args.object_id, args.name)
        if args.action == "archive":
            return library.archive(args.object_id)
        return library.match(read_image(args.image))
    if args.command == "observe":
        observation = library.observe(
            args.object_id,
            args.station,
            args.assertion,
            read_image(args.image),
            args.captured_at,
            quality=args.quality,
            visibility=args.visibility,
            mode=args.mode,
            source="operator",
        )
        return {
            **observation,
            "effective_status": library.effective_status(observation),
        }
    if args.command == "history":
        limit = (
            args.limit
            if args.limit is not None
            else library.settings.assistant.history_limit
        )
        return library.history(args.object_id, limit=limit)
    if args.command == "last-seen":
        return library.last_seen(args.object_id, mode=args.mode)
    if args.command == "checklists":
        if args.action == "list":
            return inspection.list_checklists()
        items = []
        for item in args.item:
            parts = item.split("@", 1)
            if len(parts) != 2:
                raise AssistantError(
                    "INVALID_CHECKLIST", "Use OBJECT_ID@STATION for every item."
                )
            items.append(tuple(parts))
        return inspection.create_checklist(args.name, items)
    if args.command == "inspect":
        return inspection.run(
            args.checklist_id, mode=args.mode, as_of=args.as_of, max_age_s=args.max_age
        )
    return inspection.export(args.report_id, args.output)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    settings = Settings()
    if args.data_dir:
        settings = replace(
            settings, assistant=replace(settings.assistant, data_dir=args.data_dir)
        )
    try:
        with EvidenceStore(settings.assistant.data_dir) as store:
            library = build_library(store, settings)
            result = dispatch(args, library, InspectionService(library))
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except AssistantError as error:
        print(
            json.dumps({"error": {"code": error.code, "message": str(error)}}),
            file=sys.stderr,
        )
        return 2
    except OSError:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "STORAGE_IO_ERROR",
                        "message": "Unable to access local files.",
                    }
                }
            ),
            file=sys.stderr,
        )
        return 2
    except sqlite3.Error:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "DATABASE_ERROR",
                        "message": "Unable to read or update the evidence database.",
                    }
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
