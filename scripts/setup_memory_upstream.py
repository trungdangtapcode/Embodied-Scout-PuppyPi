"""Fetch the exact upstream source into a configured, isolated checkout."""

from pathlib import Path
import subprocess

from teach_and_find.config import Settings


def main():
    cfg = Settings().memory
    path = Path(cfg.upstream_path).expanduser().resolve()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--no-checkout",
                "https://github.com/mind-palace-laeqa/benchmark",
                str(path),
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "checkout", cfg.upstream_revision], check=True
        )
    revision = subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != cfg.upstream_revision:
        raise SystemExit(
            "Existing upstream revision differs; preserve it and select another configured path."
        )
    subprocess.run(["git", "-C", str(path), "diff", "--exit-code", "HEAD"], check=True)
    print(f"Pinned Mind Palace source ready: {revision}")


if __name__ == "__main__":
    main()
