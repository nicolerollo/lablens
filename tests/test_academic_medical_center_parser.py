from lablens.academic_medical_center_parser import parse_academic_medical_center_text
from lablens.parser import normalize_panels
from lablens.sources import SOURCE_PARSERS, parse_by_source


def test_parse_academic_medical_center_panel_and_rows():
    text = """
    Panel: CBC WITH DIFFERENTIAL | Collected: 2026-02-10
      WBC .................. 6.4 K/uL Ref: 4.0-11.0
      Platelet Count ........ 301 K/uL Ref: 150-400
    """
    panels = parse_academic_medical_center_text(text)
    assert len(panels) == 1
    assert panels[0].panel == "CBC WITH DIFFERENTIAL"
    assert panels[0].collection_date == "2026-02-10"
    assert len(panels[0].rows) == 2

    results = normalize_panels(panels)
    # Canonical-test resolution is database-driven (database.resolve_canonical_test); the parser
    # and normalizer only preserve the raw test name.
    assert results[0].test_name_raw == "WBC"
    assert results[0].canonical_test_name is None
    assert results[0].numeric_value == 6.4
    assert results[0].ref_low == 4.0
    assert results[0].ref_high == 11.0


def test_qualitative_row_without_unit():
    text = """
    Panel: URINALYSIS | Collected: 2026-02-10
      Leukocyte Esterase .... Trace Ref: Negative
    """
    panels = parse_academic_medical_center_text(text)
    assert panels[0].rows[0]["value_raw"] == "Trace"
    assert panels[0].rows[0]["ref_range_raw"] == "Negative"


def test_row_before_header_is_skipped():
    text = """
    WBC .................. 6.4 K/uL Ref: 4.0-11.0
    Panel: CBC WITH DIFFERENTIAL | Collected: 2026-02-10
      Platelet Count ........ 301 K/uL Ref: 150-400
    """
    panels = parse_academic_medical_center_text(text)
    assert len(panels) == 1
    assert len(panels[0].rows) == 1


def test_source_registry_dispatches_by_name():
    assert "military_health_style" in SOURCE_PARSERS
    assert "academic_medical_center_style" in SOURCE_PARSERS
    panels = parse_by_source("Panel: CMP | Collected: 2026-02-10\n  Sodium .... 137 mmol/L Ref: 136-145", "academic_medical_center_style")
    assert panels[0].panel == "CMP"
