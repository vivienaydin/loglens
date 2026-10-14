"""Export endpoint summaries without coupling file output to log analysis."""

import csv
from pathlib import Path

from loglens.analyzer import AnalysisSummary


def safe_csv_text(value: str) -> str:
    """Prevent untrusted endpoint names from becoming spreadsheet formulas."""
    # Quoting CSV fields alone does not stop spreadsheet formula evaluation.
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_endpoints_csv(summary: AnalysisSummary, destination: Path) -> None:
    """Write endpoint statistics; refuse overwrites and clean up failed writes."""
    # Exclusive creation protects both existing reports and the source log file.
    # newline='' lets csv manage line endings correctly on Windows.
    # A UTF-8 BOM improves compatibility when opening the file in Excel.
    with destination.open("x", encoding="utf-8-sig", newline="") as output:
        try:
            writer = csv.writer(output)
            writer.writerow([
                "endpoint", "request_count",
                "average_duration_ms", "maximum_duration_ms",
            ])
            for endpoint in summary.endpoints:
                writer.writerow([
                    safe_csv_text(endpoint.endpoint),
                    endpoint.request_count,
                    endpoint.average_duration_ms,
                    endpoint.maximum_duration_ms,
                ])
            # Flush inside this block so write failures trigger cleanup as well.
            output.flush()
        except (OSError, UnicodeError, csv.Error):
            # Close before removal because Windows locks files that are still open.
            output.close()
            destination.unlink(missing_ok=True)
            raise
