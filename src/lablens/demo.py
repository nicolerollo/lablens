from __future__ import annotations

import json
from pathlib import Path

from .parser import normalize_panels
from .sources import SOURCE_PARSERS, detect_source_system
from .database import (
    connect,
    insert_results,
    fetch_numeric_results,
    fetch_qualitative_results,
    fetch_review_queue,
    export_review_queue_csv,
)
from .analytics import compute_baselines
from .report import write_reports

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_INPUT_DIR = ROOT / "data" / "sample_input"
SAMPLE_OUTPUT = ROOT / "data" / "sample_output"

# Three synthetic source systems, each with its own export layout, modeling how a patient's
# lab history is fragmented across providers: a military-health-style portal export, an
# academic-medical-center-style portal export, and a regional-hospital-style portal export. All
# three are funneled through the same normalize/store/report pipeline so the longitudinal
# analytics can merge them into one patient history. The demo deliberately does NOT hardcode each
# file's format -- it calls detect_source_system() to show the format auto-detector picking the
# right parser.
DEMO_SOURCES = [
    {
        "input_file": SAMPLE_INPUT_DIR / "synthetic_lab_summary.txt",
        "filename": "synthetic_lab_summary.txt",
        "source_system": "military_health_style_demo",
        "parser_name": "lablens_military_health_style_parser",
    },
    {
        "input_file": SAMPLE_INPUT_DIR / "academic_medical_center_style_lab_summary.txt",
        "filename": "academic_medical_center_style_lab_summary.txt",
        "source_system": "academic_medical_center_style_demo",
        "parser_name": "lablens_academic_medical_center_style_parser",
    },
    {
        "input_file": SAMPLE_INPUT_DIR / "regional_hospital_style_lab_summary.txt",
        "filename": "regional_hospital_style_lab_summary.txt",
        "source_system": "regional_hospital_style_demo",
        "parser_name": "lablens_regional_hospital_style_parser",
    },
]


def main() -> None:
    SAMPLE_OUTPUT.mkdir(parents=True, exist_ok=True)

    db_path = SAMPLE_OUTPUT / "lablens_demo.sqlite"
    if db_path.exists():
        db_path.unlink()
    conn = connect(db_path)

    all_results = []
    for source in DEMO_SOURCES:
        text = source["input_file"].read_text(encoding="utf-8")
        detected_format = detect_source_system(text)
        if detected_format is None:
            raise ValueError(f"Could not auto-detect the source format of {source['input_file']}")
        panels = SOURCE_PARSERS[detected_format](text)
        results = normalize_panels(panels)
        insert_results(
            conn,
            results,
            filename=source["filename"],
            source_system=source["source_system"],
            parser_name=source["parser_name"],
        )
        all_results.extend(results)
        print(
            f"Detected {detected_format} and parsed {len(results)} results "
            f"from {source['source_system']} ({source['filename']})"
        )

    json_path = SAMPLE_OUTPUT / "normalized_results.json"
    json_path.write_text(
        json.dumps([r.to_dict() for r in all_results], indent=2),
        encoding="utf-8",
    )

    numeric_rows = fetch_numeric_results(conn)
    qualitative_rows = fetch_qualitative_results(conn)
    summaries = compute_baselines(numeric_rows)
    report_path, html_report_path = write_reports(summaries, SAMPLE_OUTPUT, qualitative_rows)

    review_rows = fetch_review_queue(conn)
    review_csv_path = export_review_queue_csv(conn, SAMPLE_OUTPUT / "review_queue.csv")

    print(f"Parsed {len(all_results)} synthetic lab results from {len(DEMO_SOURCES)} source systems")
    print(f"{len(review_rows)} rows flagged for human review")
    print(f"Wrote {json_path}")
    print(f"Wrote {db_path}")
    print(f"Wrote {report_path}")
    print(f"Wrote {html_report_path}")
    print(f"Wrote {review_csv_path}")
    conn.close()


if __name__ == "__main__":
    main()
