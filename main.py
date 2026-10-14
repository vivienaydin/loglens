"""Provide a small CLI while keeping business logic reusable."""

import argparse
import csv
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from loglens.analyzer import analyze_entries, read_entries
from loglens.exporter import export_endpoints_csv

LOGGER = logging.getLogger("loglens")


def main() -> int:
    """Return an exit code so terminals and automation can detect failures."""
    parser = argparse.ArgumentParser(description="Analyze structured JSONL request logs.")
    parser.add_argument("file", type=Path, help="Path to a UTF-8 JSONL log file")
    parser.add_argument(
        "--csv", type=Path, metavar="PATH",
        help="Export endpoint statistics to a new CSV file; never overwrite files",
    )
    parser.add_argument(
        "--log-level", choices=("WARNING", "INFO", "DEBUG"), default="WARNING",
        help="Control diagnostic output on stderr (default: WARNING)",
    )
    args = parser.parse_args()

    # Keep diagnostics on stderr so stdout remains a valid JSON document.
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s | %(name)s | %(message)s",
        stream=sys.stderr,
    )

    try:
        LOGGER.info("Analyzing %s", args.file)
        summary = analyze_entries(read_entries(args.file))
        # Serialize before exporting so serialization failures cannot leave a CSV.
        report = json.dumps(asdict(summary), indent=2, ensure_ascii=False, allow_nan=False)
        if args.csv is not None:
            export_endpoints_csv(summary, args.csv)
            LOGGER.info("Exported endpoint statistics to %s", args.csv)
        LOGGER.info("Analyzed %d requests", summary.total_requests)
        if summary.total_requests == 0:
            LOGGER.warning("No request records found; the report contains zero totals.")
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        LOGGER.error("%s", exc)
        # Tracebacks help debugging but should not overwhelm ordinary CLI users.
        LOGGER.debug("Operation failed", exc_info=True)
        return 1
    except KeyboardInterrupt:
        LOGGER.warning("Analysis interrupted by the user.")
        return 130

    print(report)
    return 0


if __name__ == "__main__":
    # Importing this module must not run the CLI, especially during future tests.
    raise SystemExit(main())
