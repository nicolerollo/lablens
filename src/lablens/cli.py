from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import demo
from .sources import SOURCE_PARSERS, detect_source_system, parse_by_source
from .parser import normalize_panels
from .database import (
    connect,
    connect_existing,
    insert_results,
    fetch_numeric_results,
    fetch_qualitative_results,
    fetch_review_queue,
    export_review_queue_csv,
)
from .analytics import compute_baselines
from .report import write_reports

DEFAULT_DB = demo.SAMPLE_OUTPUT / "lablens_demo.sqlite"
DEFAULT_OUTPUT_DIR = demo.SAMPLE_OUTPUT


def _read_input_files(input_path: Path) -> list[Path]:
    if input_path.is_dir():
        files = sorted(p for p in input_path.iterdir() if p.suffix == ".txt")
        if not files:
            raise SystemExit(f"No .txt files found in {input_path}")
        return files
    return [input_path]


def _resolve_format(text: str, forced_source_system: str | None, input_file: Path) -> str:
    if forced_source_system:
        return forced_source_system
    detected = detect_source_system(text)
    if detected is None:
        raise SystemExit(
            f"Could not auto-detect the source format of {input_file}. "
            f"Pass --source-system explicitly (one of: {sorted(SOURCE_PARSERS)})."
        )
    return detected


def cmd_demo(args: argparse.Namespace) -> None:
    demo.main()


def cmd_parse(args: argparse.Namespace) -> None:
    input_file = Path(args.input_file)
    text = input_file.read_text(encoding="utf-8")
    source_system = _resolve_format(text, args.source_system, input_file)
    panels = parse_by_source(text, source_system)
    results = normalize_panels(panels)
    print(f"# Detected format: {source_system}", file=sys.stderr)
    print(json.dumps([r.to_dict() for r in results], indent=2))


def cmd_ingest(args: argparse.Namespace) -> None:
    input_path = Path(args.input_path)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        total = 0
        for input_file in _read_input_files(input_path):
            text = input_file.read_text(encoding="utf-8")
            source_system = _resolve_format(text, args.source_system, input_file)
            panels = parse_by_source(text, source_system)
            results = normalize_panels(panels)
            insert_results(
                conn,
                results,
                filename=input_file.name,
                source_system=source_system,
                parser_name=f"lablens_{source_system}_parser",
            )
            total += len(results)
            print(f"Detected {source_system} and ingested {len(results)} results from {input_file.name}")

        print(f"Ingested {total} results into {db_path}")
    finally:
        conn.close()


def cmd_report(args: argparse.Namespace) -> None:
    try:
        conn = connect_existing(args.db)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        output_dir = Path(args.out)
        numeric_rows = fetch_numeric_results(conn)
        qualitative_rows = fetch_qualitative_results(conn)
        summaries = compute_baselines(numeric_rows)
        report_path, html_report_path = write_reports(summaries, output_dir, qualitative_rows)
        print(f"Wrote {report_path}")
        print(f"Wrote {html_report_path}")
    finally:
        conn.close()


def cmd_export_review(args: argparse.Namespace) -> None:
    db_path = Path(args.db)
    try:
        conn = connect_existing(db_path)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        out_path = Path(args.out) if args.out else db_path.parent / "review_queue.csv"
        rows = fetch_review_queue(conn)
        csv_path = export_review_queue_csv(conn, out_path)
        print(f"Wrote {csv_path} ({len(rows)} rows flagged for review)")
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lablens",
        description=(
            "LabLens: parse extracted clinical lab text from fragmented healthcare PDF exports "
            "into normalized, database-backed longitudinal records and physician summaries. "
            "Synthetic data only -- not a diagnostic tool."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo", help="Run the full bundled demo across all synthetic source systems.")
    p_demo.set_defaults(func=cmd_demo)

    p_parse = sub.add_parser(
        "parse", help="Parse one extracted-text file and print normalized records as JSON (no DB write)."
    )
    p_parse.add_argument("input_file", help="Path to an extracted-text input file.")
    p_parse.add_argument(
        "--source-system",
        choices=sorted(SOURCE_PARSERS),
        default=None,
        help="Force a specific parser instead of auto-detecting the format.",
    )
    p_parse.set_defaults(func=cmd_parse)

    p_ingest = sub.add_parser(
        "ingest", help="Parse and store one file (or every .txt file in a directory) into a SQLite database."
    )
    p_ingest.add_argument("input_path", help="An extracted-text file, or a directory of .txt files.")
    p_ingest.add_argument(
        "--db", default=str(DEFAULT_DB), help=f"SQLite database path, created if missing (default: {DEFAULT_DB})."
    )
    p_ingest.add_argument(
        "--source-system",
        choices=sorted(SOURCE_PARSERS),
        default=None,
        help="Force a specific parser/source_system for every input file instead of auto-detecting each one.",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_report = sub.add_parser("report", help="Generate physician-summary Markdown/HTML reports from a database.")
    p_report.add_argument("db", help="SQLite database path.")
    p_report.add_argument(
        "--out", default=str(DEFAULT_OUTPUT_DIR), help=f"Output directory for reports (default: {DEFAULT_OUTPUT_DIR})."
    )
    p_report.set_defaults(func=cmd_report)

    p_export = sub.add_parser("export-review", help="Export the human review queue to CSV.")
    p_export.add_argument("db", help="SQLite database path.")
    p_export.add_argument("--out", default=None, help="CSV output path (default: review_queue.csv next to the database).")
    p_export.set_defaults(func=cmd_export_review)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
