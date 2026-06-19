from pathlib import Path

from lablens.academic_medical_center_parser import parse_academic_medical_center_text
from lablens.parser import normalize_panels
from lablens.normalizer import interpret_qualitative

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "sample_input" / "messy_academic_medical_center_extracted_text.txt"


def test_messy_fixture_recovers_line_wrapped_rows():
    text = FIXTURE.read_text(encoding="utf-8")
    panels = parse_academic_medical_center_text(text)

    cbc_rows = [row for panel in panels if panel.panel == "CBC WITH DIFFERENTIAL" for row in panel.rows]
    by_name = {row["test_name_raw"]: row for row in cbc_rows}

    # WBC and Hemoglobin were wrapped across two lines in the fixture; both must still recover
    # their value and unit correctly.
    assert by_name["WBC"]["value_raw"] == "6.4"
    assert by_name["WBC"]["ref_range_raw"] == "4.0-11.0 K/uL"
    assert by_name["Hemoglobin"]["value_raw"] == "13.2"
    assert by_name["Hemoglobin"]["ref_range_raw"] == "11.0-15.1 g/dL"

    # RBC was not wrapped -- sanity check it still parses normally alongside the wrapped rows.
    assert by_name["RBC"]["value_raw"] == "4.50"


def test_messy_fixture_panel_continues_after_page_break():
    text = FIXTURE.read_text(encoding="utf-8")
    panels = parse_academic_medical_center_text(text)

    cbc_panels = [p for p in panels if p.panel == "CBC WITH DIFFERENTIAL"]
    # The fixture repeats the "Panel: CBC WITH DIFFERENTIAL | Collected: ..." header after a
    # page break; the parser is expected to start a second ParsedPanel rather than merging them
    # itself -- database.insert_results() merges same (panel, collection_date) panels downstream.
    assert len(cbc_panels) == 2
    assert any(row["test_name_raw"] == "Platelet Count" for row in cbc_panels[1].rows)


def test_messy_fixture_skips_letterhead_and_footer_junk_without_warning_as_unparsable(caplog):
    text = FIXTURE.read_text(encoding="utf-8")
    with caplog.at_level("WARNING"):
        parse_academic_medical_center_text(text)
    unparsable_warnings = [r for r in caplog.records if "unparsable" in r.message.lower()]
    assert unparsable_warnings == []


def test_messy_fixture_qualitative_panel_flagged_abnormal():
    text = FIXTURE.read_text(encoding="utf-8")
    panels = parse_academic_medical_center_text(text)
    results = normalize_panels(panels)
    flu = next(r for r in results if r.test_name_raw == "Influenza Virus Type A")
    assert flu.qualitative_value == "DETECTED"
    assert interpret_qualitative(flu.qualitative_value) == "qualitative_abnormal"


def test_messy_fixture_total_row_count():
    text = FIXTURE.read_text(encoding="utf-8")
    panels = parse_academic_medical_center_text(text)
    results = normalize_panels(panels)
    assert len(results) == 5
