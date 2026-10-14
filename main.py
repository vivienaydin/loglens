"""Provide a small CLI while keeping business logic reusable."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from loglens.analyzer import analyze_entries, read_entries


def main() -> int:
    """Return an exit code so terminals and automation can detect failures."""
    parser = argparse.ArgumentParser(description="Analyze structured JSONL request logs.")
    parser.add_argument("file", type=Path, help="Path to a UTF-8 JSONL log file")
    args = parser.parse_args()

    try:
        summary = analyze_entries(read_entries(args.file))
    except (OSError, UnicodeError, ValueError) as exc:
        # Errors belong on stderr so stdout remains usable as machine-readable JSON.
        print(f"LogLens: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(summary), indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    # Importing this module must not run the CLI, especially during future tests.
    raise SystemExit(main())
