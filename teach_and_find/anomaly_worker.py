"""One-request-at-a-time original anomaly inference over local JSON lines."""

from contextlib import redirect_stdout
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

from teach_and_find.config import SearchSettings, VisionSettings
from teach_and_find.errors import AssistantError
from teach_and_find.model_artifacts import verified_weights


def main():
    try:
        request = json.loads(sys.stdin.readline())
        cfg, vision = (
            SearchSettings(**request["search"]),
            VisionSettings(**request["vision"]),
        )
        calibration_file = verified_weights(
            cfg.anomaly_calibration,
            cfg.anomaly_calibration_sha256,
            "ANOMALY_CALIBRATION",
        )
        calibration = json.loads(calibration_file.read_text())
        with redirect_stdout(sys.stderr):
            import cv2
            import numpy as np
            from teach_and_find.anomaly_model import OriginalAnomalyDino, fit_decision
            from teach_and_find.storage import EvidenceStore

            if calibration["scoring"] != {
                "function_sha256": "45d4135040305ffef3933766eb2021ede369964146f9d9e5aac37d2773293f5d",
                "resolution": cfg.anomaly_resolution,
                "masking": False,
                "rotation": False,
            }:
                raise AssistantError(
                    "ANOMALY_CALIBRATION_PROFILE_MISMATCH",
                    "Development fit does not match the original scoring profile.",
                )
            decision = fit_decision(calibration)
            model = OriginalAnomalyDino(cfg, vision)
            if (
                model.provenance["packages"]["scikit-learn"]
                != calibration["sklearn_version"]
            ):
                raise AssistantError(
                    "ANOMALY_CALIBRATION_ENVIRONMENT_MISMATCH",
                    "Fitted decision framework version changed.",
                )
        provenance = {
            **model.provenance,
            "calibration_sha256": cfg.anomaly_calibration_sha256,
            "decision": "original_sklearn_DecisionTreeClassifier_max_depth_1_development_fit_not_probability",
            "decision_threshold": float(decision.tree_.threshold[0]),
        }
        print(json.dumps({"type": "ready", "provenance": provenance}), flush=True)
        with EvidenceStore(request["store"]) as store:
            references = [
                cv2.cvtColor(store.load_image(sha), cv2.COLOR_BGR2RGB)
                for sha in request["references"]
            ]
            for line in sys.stdin:
                payload = json.loads(line)
                started = time.monotonic()
                records = []
                for sha in payload["crops"]:
                    with redirect_stdout(sys.stderr):
                        value, distances, mask = model.score(
                            cv2.cvtColor(store.load_image(sha), cv2.COLOR_BGR2RGB),
                            references,
                        )
                    value = float(value)
                    if (
                        not np.isfinite(value)
                        or not np.isfinite(distances).all()
                        or not mask.all()
                    ):
                        raise AssistantError(
                            "ANOMALY_OUTPUT_INVALID",
                            "Finite unmasked original output is mandatory.",
                        )
                    image_path = store.root / "anomaly-maps"
                    image_path.mkdir(exist_ok=True)
                    name = (
                        hashlib.sha256(
                            (
                                sha
                                + cfg.anomaly_calibration_sha256
                                + ":"
                                + str(request["references"])
                            ).encode()
                        ).hexdigest()
                        + ".npy"
                    )
                    np.save(image_path / name, distances)
                    display = cv2.applyColorMap(
                        (np.clip(distances / 2, 0, 1) * 255).astype(np.uint8),
                        cv2.COLORMAP_MAGMA,
                    )
                    map_image_sha = store.save_image(display)
                    records.append(
                        {
                            "crop_image_sha": sha,
                            "reference_shas": request["references"],
                            "score": value,
                            "appearance_rejected": bool(decision.predict([[value]])[0]),
                            "map_file": str(Path("anomaly-maps") / name),
                            "map_sha256": hashlib.sha256(
                                (image_path / name).read_bytes()
                            ).hexdigest(),
                            "map_shape": list(distances.shape),
                            "map_image_sha": map_image_sha,
                            "display_scale": "patch_cosine_distance_0_to_2_full_unmasked_crop",
                            "provenance": {
                                **provenance,
                                "executed_scoring_calls": model.score_calls,
                            },
                            "method": "original_anomalydino_with_fitted_scalar_application_gate",
                        }
                    )
                print(
                    json.dumps(
                        {
                            "type": "result",
                            "request_id": payload["request_id"],
                            "records": records,
                            "seconds": time.monotonic() - started,
                            "executed_scoring_calls": model.score_calls,
                        }
                    ),
                    flush=True,
                )
    except Exception as error:
        print(
            json.dumps(
                {
                    "type": "error",
                    "code": getattr(error, "code", "ANOMALY_EXECUTION_FAILED"),
                    "message": str(error)[:1500],
                }
            ),
            flush=True,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
