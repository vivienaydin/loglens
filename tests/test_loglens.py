"""Protect observable behavior with tests runnable by pytest or unittest."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from loglens.analyzer import LogEntry, analyze_entries, parse_entry, read_entries
from loglens.exporter import export_endpoints_csv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AnalysisTests(unittest.TestCase):
    """Check calculations and validation without relying on external services."""

    def test_sample_report_matches_known_request_statistics(self) -> None:
        """A fixed sample provides independently calculated expected results."""
        report = analyze_entries(read_entries(PROJECT_ROOT / "data" / "sample.jsonl"))

        self.assertEqual(report.total_requests, 8)
        self.assertEqual(report.error_requests, 3)
        self.assertEqual(report.error_rate_percent, 37.5)
        self.assertEqual(report.level_counts, {
            "CRITICAL": 1, "ERROR": 2, "INFO": 4, "WARNING": 1,
        })
        self.assertEqual(report.error_messages["Database timeout"], 2)
        self.assertEqual(
            [item.endpoint for item in report.endpoints],
            ["/payments", "/users", "/health"],
        )
        self.assertEqual(
            [item.average_duration_ms for item in report.endpoints],
            [700.0, 580.0, 10.0],
        )
        self.assertEqual(
            [item.maximum_duration_ms for item in report.endpoints],
            [1200.0, 950.0, 12.0],
        )

    def test_empty_input_returns_zero_totals(self) -> None:
        """Empty files must produce a usable report instead of division by zero."""
        report = analyze_entries(iter(()))

        self.assertEqual(report.total_requests, 0)
        self.assertEqual(report.error_requests, 0)
        self.assertEqual(report.error_rate_percent, 0.0)
        self.assertEqual(report.endpoints, [])

    def test_invalid_durations_are_rejected(self) -> None:
        """Booleans and non-finite values must never silently skew statistics."""
        for duration in (True, -1, "120", None, float("nan"), float("inf")):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    parse_entry({
                        "level": "INFO", "message": "Request completed",
                        "endpoint": "/health", "duration_ms": duration,
                    })


class FileAndCliTests(unittest.TestCase):
    """Use isolated files so test runs cannot overwrite a developer's reports."""

    def setUp(self) -> None:
        """Create an isolated workspace with a narrowly scoped cleanup target."""
        temporary_parent = PROJECT_ROOT / ".test-tmp"
        temporary_parent.mkdir(exist_ok=True)
        self.workspace = tempfile.TemporaryDirectory(dir=temporary_parent)
        self.directory = Path(self.workspace.name)
        # Verify containment before registering recursive temporary-file cleanup.
        if not self.directory.resolve().is_relative_to(temporary_parent.resolve()):
            raise RuntimeError("Temporary test directory escaped its parent.")
        self.addCleanup(self.workspace.cleanup)

    def test_invalid_json_reports_the_physical_line_number(self) -> None:
        """Blank lines must not shift the line number shown to the user."""
        source = self.directory / "invalid.jsonl"
        source.write_text("\n{invalid json}\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Line 2:"):
            list(read_entries(source))

    def test_csv_preserves_endpoint_statistics(self) -> None:
        """Read exported CSV back to verify its public columns and values."""
        report = analyze_entries(read_entries(PROJECT_ROOT / "data" / "sample.jsonl"))
        destination = self.directory / "endpoints.csv"

        export_endpoints_csv(report, destination)

        with destination.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], {
            "endpoint": "/payments", "request_count": "2",
            "average_duration_ms": "700.0", "maximum_duration_ms": "1200.0",
        })

    def test_export_never_overwrites_existing_files(self) -> None:
        """An existing file must remain byte-for-byte unchanged after rejection."""
        destination = self.directory / "existing.csv"
        original = b"existing report\r\n"
        destination.write_bytes(original)

        with self.assertRaises(FileExistsError):
            export_endpoints_csv(analyze_entries([]), destination)

        self.assertEqual(destination.read_bytes(), original)

    def test_formula_like_endpoints_are_exported_as_text(self) -> None:
        """Untrusted endpoint names must not become active spreadsheet formulas."""
        report = analyze_entries([LogEntry("INFO", "Request", "=1+1", 10)])
        destination = self.directory / "safe.csv"

        export_endpoints_csv(report, destination)

        with destination.open(encoding="utf-8-sig", newline="") as source:
            row = next(csv.DictReader(source))
        self.assertEqual(row["endpoint"], "'=1+1")

    def test_cli_keeps_json_and_diagnostics_on_separate_streams(self) -> None:
        """Exercise the real entry point as an automation tool would invoke it."""
        result = subprocess.run(
            [sys.executable, "-B", str(PROJECT_ROOT / "main.py"),
             str(PROJECT_ROOT / "data" / "sample.jsonl"), "--log-level", "INFO"],
            capture_output=True, text=True, check=False, timeout=15,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["total_requests"], 8)
        self.assertIn("INFO | loglens", result.stderr)

    def test_cli_returns_failure_without_a_partial_report(self) -> None:
        """Missing input must be detectable through both exit code and stderr."""
        result = subprocess.run(
            [sys.executable, "-B", str(PROJECT_ROOT / "main.py"),
             str(self.directory / "missing.jsonl")],
            capture_output=True, text=True, check=False, timeout=15,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("ERROR | loglens", result.stderr)
