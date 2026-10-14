"""Keep log parsing and aggregation independent from the user interface."""

import json
import math
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LogEntry:
    """Represent one validated request; immutability prevents accidental edits."""

    level: str
    message: str
    endpoint: str
    duration_ms: float


@dataclass(frozen=True, slots=True)
class EndpointSummary:
    """Expose response-time statistics in a format an API can reuse."""

    endpoint: str
    request_count: int
    average_duration_ms: float
    maximum_duration_ms: float


@dataclass(frozen=True, slots=True)
class AnalysisSummary:
    """Describe the entire file using explicit, serializable result fields."""

    total_requests: int
    error_requests: int
    error_rate_percent: float
    level_counts: dict[str, int]
    error_messages: dict[str, int]
    endpoints: list[EndpointSummary]


@dataclass(slots=True)
class _EndpointAccumulator:
    """Store aggregates instead of retaining every request in memory."""

    count: int = 0
    total_duration_ms: float = 0.0
    maximum_duration_ms: float = 0.0


def parse_entry(raw: object) -> LogEntry:
    """Validate the schema before aggregation so bad data cannot skew results."""
    if not isinstance(raw, dict):
        raise ValueError("Each log entry must be a JSON object.")

    fields: dict[str, str] = {}
    for name in ("level", "message", "endpoint"):
        value = raw.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"'{name}' must be a non-empty string.")
        fields[name] = value.strip()

    level = fields["level"].upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError(f"Unsupported log level: {level}")

    duration = raw.get("duration_ms")
    # Python treats booleans as integers, but true is not a meaningful latency.
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError("'duration_ms' must be a number.")
    try:
        duration_ms = float(duration)
    except OverflowError as exc:
        raise ValueError("'duration_ms' is too large.") from exc
    if not math.isfinite(duration_ms) or duration_ms < 0:
        raise ValueError("'duration_ms' must be finite and non-negative.")

    return LogEntry(level, fields["message"], fields["endpoint"], duration_ms)


def read_entries(path: Path) -> Iterator[LogEntry]:
    """Stream JSONL records and include line numbers in validation failures."""
    # utf-8-sig also accepts UTF-8 files with a BOM from Windows editors.
    with path.open(encoding="utf-8-sig") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                yield parse_entry(json.loads(line))
            except ValueError as exc:
                raise ValueError(f"Line {line_number}: {exc}") from exc


def analyze_entries(entries: Iterable[LogEntry]) -> AnalysisSummary:
    """Aggregate in one pass; memory grows with unique endpoints and messages."""
    total_requests = 0
    error_requests = 0
    levels: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    endpoints: dict[str, _EndpointAccumulator] = {}

    for entry in entries:
        total_requests += 1
        levels[entry.level] += 1
        # Both levels signal a failed request in this project's input contract.
        if entry.level in {"ERROR", "CRITICAL"}:
            error_requests += 1
            errors[entry.message] += 1

        stats = endpoints.setdefault(entry.endpoint, _EndpointAccumulator())
        stats.count += 1
        stats.total_duration_ms += entry.duration_ms
        if not math.isfinite(stats.total_duration_ms):
            raise ValueError("Combined endpoint duration exceeds numeric limits.")
        stats.maximum_duration_ms = max(stats.maximum_duration_ms, entry.duration_ms)

    endpoint_summaries = [
        EndpointSummary(
            endpoint=endpoint,
            request_count=stats.count,
            average_duration_ms=round(stats.total_duration_ms / stats.count, 2),
            maximum_duration_ms=stats.maximum_duration_ms,
        )
        for endpoint, stats in endpoints.items()
    ]
    # Deterministic tie-breaking makes reports and future tests reproducible.
    endpoint_summaries.sort(key=lambda item: (-item.average_duration_ms, item.endpoint))
    sorted_errors = sorted(errors.items(), key=lambda item: (-item[1], item[0]))

    return AnalysisSummary(
        total_requests=total_requests,
        error_requests=error_requests,
        error_rate_percent=round(error_requests / total_requests * 100, 2)
        if total_requests else 0.0,
        level_counts=dict(sorted(levels.items())),
        error_messages=dict(sorted_errors),
        endpoints=endpoint_summaries,
    )
