"""Audit integrity across JavaScript's numeric JSON normalization; no models."""

import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest


def test_audit_preserves_original_signed_numeric_snapshot(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/qualify_search.py"
    spec = importlib.util.spec_from_file_location("search_quality_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "store").mkdir()
    with sqlite3.connect(tmp_path / "store/assistant.sqlite3") as database:
        database.execute("CREATE TABLE searches (id TEXT, payload_json TEXT)")
        database.execute(
            "INSERT INTO searches VALUES (?,?)",
            ("unit-job", json.dumps({"gain": 2.0, "threshold": 0.8})),
        )
    browser_export = {"id": "unit-job", "payload": {"gain": 2, "threshold": 0.8}}
    original = module.original_payload(tmp_path, browser_export)
    assert type(original["gain"]) is float
    browser_export["payload"]["threshold"] = 0.7
    with pytest.raises(ValueError, match="disagrees"):
        module.original_payload(tmp_path, browser_export)
