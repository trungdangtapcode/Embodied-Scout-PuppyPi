"""Validate scoped Conventional Commit subjects without project dependencies."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


TYPES = "feat|fix|docs|refactor|test|perf|build|ci|chore|revert"
SCOPES = {
    "repo", "core", "perception", "memory", "planner", "verification",
    "mission", "inspection", "interaction", "motion", "bridge", "sim",
    "eval", "ui", "research", "docs", "deps", "workflow", "tests", "assets",
}
PATTERN = re.compile(rf"(?:{TYPES})\(([a-z]+)\)!?: ([a-z].*)")


def validate_subject(subject: str) -> str | None:
    if len(subject) > 72:
        return "Subject exceeds 72 characters."
    match = PATTERN.fullmatch(subject)
    if match is None:
        return "Expected type(scope): description, with a lowercase initial."
    if match.group(1) not in SCOPES:
        return "Unknown scope; use a scope from CONTRIBUTING.md."
    if subject != subject.strip() or subject.endswith("."):
        return "Remove trailing whitespace or the final period."
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("message_file", nargs="?", type=Path)
    group.add_argument("--history", action="store_true")
    args = parser.parse_args()
    if args.history:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "log", "--format=%s"], cwd=root, text=True,
            capture_output=True, check=True,
        )
        subjects = result.stdout.splitlines()
    else:
        lines = args.message_file.read_text(encoding="utf-8").splitlines()
        subjects = [lines[0] if lines else ""]
    errors = [(subject, error) for subject in subjects
              if (error := validate_subject(subject)) is not None]
    for subject, error in errors:
        print(f"Invalid commit subject: {subject!r}\n{error}", file=sys.stderr)
    if not errors and args.history:
        print(f"Validated {len(subjects)} commit subjects.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
