# LogLens

**Turn structured request logs into actionable error and latency reports.**

LogLens is a Python command-line tool for investigating application failures and slow endpoints. It reads JSONL request logs, produces a machine-readable JSON report, and optionally exports endpoint statistics to CSV.

Use it to answer three practical questions after a deployment: **How many requests failed? Which errors repeat? Which endpoints are slowest on average?**

The application runs entirely on the Python standard library. No database, account, API key, or external service is required.

## Try it

Requires **Python 3.10 or newer** and Git. Run these commands in a terminal:

```sh
git clone https://github.com/vivienaydin/loglens.git
cd loglens
python -B main.py data/sample.jsonl
```

If your system exposes Python as `python3`, use that command instead of `python`.

The included synthetic sample contains eight requests. Its report identifies three failures, a **37.5% error rate**, and two occurrences of `Database timeout`.

| Endpoint | Requests | Average duration | Maximum duration |
| --- | ---: | ---: | ---: |
| `/payments` | 2 | 700 ms | 1,200 ms |
| `/users` | 4 | 580 ms | 950 ms |
| `/health` | 2 | 10 ms | 12 ms |

Endpoints are sorted by average duration, highest first. Endpoint names break ties alphabetically so reports are reproducible.

## Features

- Stream log files one line at a time instead of loading all requests into memory.
- Count requests, log levels, and repeated error messages.
- Calculate the percentage of requests marked `ERROR` or `CRITICAL`.
- Report request count, average duration, and maximum duration per endpoint.
- Reject invalid required fields and include physical line numbers in parsing errors.
- Export endpoint statistics without overwriting an existing file.
- Keep diagnostic logging on stderr and JSON results on stdout.
- Process local files without sending log contents to an external service.

## Input contract

**Each non-blank line must describe exactly one request.** LogLens expects UTF-8 JSONL and also accepts a UTF-8 byte-order mark.

```json
{"level":"ERROR","message":"Database timeout","endpoint":"/users","duration_ms":850}
```

| Field | Required value |
| --- | --- |
| `level` | Non-empty string: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`; normalized to uppercase |
| `message` | Non-empty string describing the request outcome |
| `endpoint` | Non-empty string used to group requests |
| `duration_ms` | Finite, non-negative number; booleans and numeric strings are rejected |

String fields are trimmed. Additional fields are ignored. Blank lines are skipped but still count toward physical line numbers in error messages.

`ERROR` and `CRITICAL` count as failed requests. `WARNING` does not. The calculation is:

```text
error_rate_percent = failed_requests / total_requests * 100
```

Empty input produces zero totals and a warning. If your application writes several records per request, first transform those records into one request summary per line; otherwise this percentage describes log records rather than requests.

## Usage

Analyze the included sample:

```sh
python -B main.py data/sample.jsonl
```

Export endpoint statistics and show progress messages:

```sh
python -B main.py data/sample.jsonl --csv endpoints.csv --log-level INFO
```

The export contains `endpoint`, `request_count`, `average_duration_ms`, and `maximum_duration_ms`. It does not contain the complete JSON report or individual log records.

The destination directory must already exist. An existing destination is rejected, so repeating this export requires a different filename or moving the previous report first. Formula-like endpoint names are prefixed with an apostrophe to reduce spreadsheet formula injection risks.

Show debugging details or CLI help:

```sh
python -B main.py data/sample.jsonl --log-level DEBUG
python -B main.py --help
```

| Option | Purpose |
| --- | --- |
| `file` | Required path to a JSONL request log |
| `--csv PATH` | Export endpoint statistics to a new CSV file |
| `--log-level WARNING` | Default: display warnings and errors |
| `--log-level INFO` | Also display analysis and export progress |
| `--log-level DEBUG` | Also display tracebacks for handled failures |

## Automation behavior

Successful analysis writes one JSON document to stdout. Progress messages and handled errors go to stderr, allowing other tools to parse stdout independently.

| Exit code | Meaning |
| ---: | --- |
| `0` | Analysis and any requested export completed |
| `1` | Input validation, file access, or export failed |
| `2` | Command-line arguments are invalid |
| `130` | The user interrupted analysis or export |

A nonzero error rate in the input does **not** change the exit code: a completed analysis still returns `0`. LogLens reports failures observed in the logs; it does not enforce deployment thresholds.

Malformed records stop analysis. Handled analysis or export failures return no JSON report, avoiding the impression that a partial result represents the entire file.

## Development and tests

The application itself has no third-party dependencies. `requirements.txt` declares pytest for development. Create an isolated environment:

```sh
python -m venv .venv
```

**Windows PowerShell:**

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q tests
```

**Linux and macOS:**

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q tests
```

The nine test methods cover sample calculations, empty input, invalid durations, line numbers, CSV values, overwrite protection, formula-like names, CLI output streams, and failure exit codes. Temporary test files are isolated under the ignored `.test-tmp/` directory.

The same tests can run without installing pytest:

```sh
python -B -m unittest discover -s tests -v
```

## Project structure

| Path | Responsibility |
| --- | --- |
| `main.py` | Argument parsing, logging configuration, output, and exit codes |
| `loglens/analyzer.py` | Validated records, streaming input, and aggregation |
| `loglens/exporter.py` | CSV serialization and overwrite protection |
| `loglens/__init__.py` | Python package definition |
| `data/sample.jsonl` | Synthetic data for a reproducible demonstration |
| `tests/test_loglens.py` | Behavioral and CLI regression tests |
| `requirements.txt` | Development dependency constraints |
| `.gitignore` | Exclusions for local environments and generated files |
| `README.md` | Setup, usage, input contract, and design decisions |

## Engineering decisions and trade-offs

**Separate interfaces from analysis.** Parsing and aggregation do not depend on argparse, logging configuration, or CSV output. This keeps the core reusable from another interface without duplicating business rules.

**Validate before aggregating.** Invalid durations and missing fields stop processing rather than silently changing the report. This prioritizes explainable results over partial recovery.

**Aggregate instead of retaining requests.** The analyzer keeps counters and per-endpoint totals. Memory use grows with unique endpoints and error messages, not just file size. High-cardinality input can still consume substantial memory; this is not a bounded-memory guarantee.

**Keep outputs predictable.** Frozen result dataclasses describe the report, deterministic ordering stabilizes output, and diagnostics use a separate stream. CSV creation uses exclusive mode to protect existing files.

## Scope

This version analyzes local JSONL request summaries and exports endpoint aggregates. It does not include an HTTP API, live tailing, timestamp filters, percentile latency calculations, or measured performance benchmarks. It groups endpoint strings exactly as provided after trimming, so parameterized routes should be normalized upstream.

Built by **Vivien Aydin** as a practical backend and automation portfolio project.
