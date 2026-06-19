import json
import subprocess
import sys

from lablens.cli import build_parser
from lablens.database import connect, fetch_review_queue

# Each CLI test shells out to a real `python -m lablens.cli ...` subprocess, which is the right
# way to test the actual entry point, but it means a hung subprocess (a stuck pipe, antivirus
# scanning a freshly-written file, a slow filesystem under a synced folder, etc.) would otherwise
# freeze the whole test run with no error. A timeout turns that into a clear, fast failure instead.
CLI_SUBPROCESS_TIMEOUT = 30


def _run_cli(args, timeout=CLI_SUBPROCESS_TIMEOUT, **kwargs):
    return subprocess.run(
        [sys.executable, "-m", "lablens.cli", *args],
        capture_output=True, text=True, timeout=timeout, **kwargs,
    )


def test_build_parser_exposes_all_five_commands():
    parser = build_parser()
    subcommands = parser._subparsers._group_actions[0].choices
    assert set(subcommands) == {"demo", "parse", "ingest", "report", "export-review"}


def test_parse_command_auto_detects_and_prints_json(tmp_path):
    input_file = tmp_path / "sample.txt"
    input_file.write_text(
        "Panel: CBC WITH DIFFERENTIAL | Collected: 2026-02-10\n"
        "  WBC .................. 6.4 K/uL Ref: 4.0-11.0\n",
        encoding="utf-8",
    )
    result = _run_cli(["parse", str(input_file)])
    assert result.returncode == 0
    assert "academic_medical_center_style" in result.stderr
    records = json.loads(result.stdout)
    assert records[0]["test_name_raw"] == "WBC"
    assert records[0]["numeric_value"] == 6.4


def test_parse_command_errors_clearly_on_unrecognized_format(tmp_path):
    input_file = tmp_path / "unknown.txt"
    input_file.write_text("this is not a recognized lab export format at all", encoding="utf-8")
    result = _run_cli(["parse", str(input_file)])
    assert result.returncode != 0
    assert "--source-system" in result.stderr


def test_ingest_command_loads_a_directory_of_mixed_formats(tmp_path):
    (tmp_path / "a.txt").write_text(
        "CBC WITH DIFFERENTIAL - Final result (2026-01-14 09:22 AM CDT)\n"
        "WBC | 7.2 | 4.0 - 11.0 K/uL | 10\n",
        encoding="utf-8",
    )
    (tmp_path / "b.txt").write_text(
        "Panel: CBC WITH DIFFERENTIAL | Collected: 2026-02-10\n"
        "  RBC .................. 4.50 M/uL Ref: 3.70-5.10\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "out.sqlite"
    result = _run_cli(["ingest", str(tmp_path), "--db", str(db_path)])
    assert result.returncode == 0
    assert db_path.exists()

    conn = connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM lab_results").fetchone()["n"]
        assert count == 2
    finally:
        conn.close()


def test_export_review_command_writes_csv(tmp_path):
    (tmp_path / "a.txt").write_text(
        "CBC WITH DIFFERENTIAL - Final result (2026-01-14 09:22 AM CDT)\n"
        "Mystery Test | 42 | 0 - 10 units | 1\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "out.sqlite"
    ingest_result = _run_cli(["ingest", str(tmp_path), "--db", str(db_path)])
    assert ingest_result.returncode == 0

    csv_path = tmp_path / "review.csv"
    export_result = _run_cli(["export-review", str(db_path), "--out", str(csv_path)])
    assert export_result.returncode == 0
    assert csv_path.exists()
    assert "Mystery Test" in csv_path.read_text(encoding="utf-8")

    conn = connect(db_path)
    try:
        assert len(fetch_review_queue(conn)) >= 1
    finally:
        conn.close()


def test_report_command_writes_markdown_and_html(tmp_path):
    (tmp_path / "a.txt").write_text(
        "CBC WITH DIFFERENTIAL - Final result (2026-01-14 09:22 AM CDT)\n"
        "WBC | 7.2 | 4.0 - 11.0 K/uL | 10\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "out.sqlite"
    _run_cli(["ingest", str(tmp_path), "--db", str(db_path)])

    out_dir = tmp_path / "reports"
    result = _run_cli(["report", str(db_path), "--out", str(out_dir)])
    assert result.returncode == 0
    assert (out_dir / "physician_summary.md").exists()
    assert (out_dir / "physician_summary.html").exists()


def test_report_and_export_review_subprocess_calls_succeed(tmp_path):
    """One real subprocess call each for `report` and `export-review`, to prove the actual CLI
    entry point wires up correctly end to end. (See the in-process test below for repeated-call
    read-only behavior -- that's deliberately not re-tested here via a subprocess loop, since
    each additional subprocess is more opportunity for an unrelated environment hang.)"""
    (tmp_path / "a.txt").write_text(
        "CBC WITH DIFFERENTIAL - Final result (2026-01-14 09:22 AM CDT)\n"
        "WBC | 7.2 | 4.0 - 11.0 K/uL | 10\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "out.sqlite"
    assert _run_cli(["ingest", str(tmp_path), "--db", str(db_path)]).returncode == 0
    assert _run_cli(["report", str(db_path), "--out", str(tmp_path / "reports")]).returncode == 0
    assert _run_cli(["export-review", str(db_path), "--out", str(tmp_path / "review.csv")]).returncode == 0


def test_report_and_export_review_do_not_grow_alias_table(tmp_path):
    """report/export-review are read-only workflows -- calling them repeatedly against the same
    database must not re-trigger reference-data seeding (see connect_existing()). Exercised here
    by calling the CLI's own command functions in-process (not via subprocess): this still proves
    cmd_report()/cmd_export_review() are wired to connect_existing(), without paying for a new
    subprocess per call -- repeated subprocess launches are exactly what risked hanging this test
    in some sandboxes."""
    (tmp_path / "a.txt").write_text(
        "CBC WITH DIFFERENTIAL - Final result (2026-01-14 09:22 AM CDT)\n"
        "WBC | 7.2 | 4.0 - 11.0 K/uL | 10\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "out.sqlite"
    assert _run_cli(["ingest", str(tmp_path), "--db", str(db_path)]).returncode == 0

    conn = connect(db_path)
    try:
        before = conn.execute("SELECT COUNT(*) AS n FROM lab_test_aliases").fetchone()["n"]
    finally:
        conn.close()

    parser = build_parser()
    report_args = parser.parse_args(["report", str(db_path), "--out", str(tmp_path / "reports")])
    export_args = parser.parse_args(["export-review", str(db_path), "--out", str(tmp_path / "review.csv")])
    for _ in range(3):
        report_args.func(report_args)
        export_args.func(export_args)

    conn = connect(db_path)
    try:
        after = conn.execute("SELECT COUNT(*) AS n FROM lab_test_aliases").fetchone()["n"]
    finally:
        conn.close()
    assert after == before


def test_report_command_errors_clearly_on_missing_database(tmp_path):
    result = _run_cli(["report", str(tmp_path / "does_not_exist.sqlite")])
    assert result.returncode != 0
    assert "not found" in result.stderr.lower()
