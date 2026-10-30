"""Check local inline Markdown link targets in project documentation."""

from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")


def main() -> int:
    documents = sorted(ROOT.glob("*.md"))
    for folder in ("docs", "assets", "outputs"):
        documents.extend(sorted((ROOT / folder).rglob("*.md")))
    errors: list[str] = []
    count = 0
    for document in documents:
        # Exclude examples in fenced code, including proposed manifest content.
        body = re.sub(r"```.*?```", "", document.read_text(encoding="utf-8"),
                      flags=re.DOTALL)
        for match in LINK.finditer(body):
            target = match.group(1).strip()
            target = target[1:target.index(">")] if target.startswith("<") else target.split()[0]
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            count += 1
            destination = document.parent / unquote(parsed.path)
            if not destination.exists():
                errors.append(f"{document.relative_to(ROOT)}: missing {target}")
    for error in errors:
        print(error)
    if not errors:
        print(f"Validated {count} local link targets in {len(documents)} documents.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
