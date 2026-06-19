from lablens.parser import parse_extracted_text, normalize_panels


def test_parse_panel_and_rows():
    text = """
    CBC WITH DIFFERENTIAL - Final result (2026-01-14 09:22 AM CDT)
    WBC | 7.2 | 4.0 - 11.0 K/uL | 10
    Platelet Count | 355 | 150 - 400 K/uL | 11
    """
    panels = parse_extracted_text(text)
    assert len(panels) == 1
    assert panels[0].panel == "CBC WITH DIFFERENTIAL"
    assert len(panels[0].rows) == 2

    results = normalize_panels(panels)
    # Canonical-test resolution happens later, against lab_test_aliases in the database (see
    # database.resolve_canonical_test) -- normalize_panels() only preserves the raw test name.
    assert results[0].test_name_raw == "WBC"
    assert results[0].canonical_test_name is None
    assert results[0].source_page == 10


def test_row_before_any_panel_header_is_skipped_not_misattributed():
    text = """
    WBC | 7.2 | 4.0 - 11.0 K/uL | 10
    CBC WITH DIFFERENTIAL - Final result (2026-01-14 09:22 AM CDT)
    Platelet Count | 355 | 150 - 400 K/uL | 11
    """
    panels = parse_extracted_text(text)
    assert len(panels) == 1
    assert len(panels[0].rows) == 1
    assert panels[0].rows[0]["test_name_raw"] == "Platelet Count"


def test_malformed_row_is_skipped():
    text = """
    CBC WITH DIFFERENTIAL - Final result (2026-01-14 09:22 AM CDT)
    this line has no pipes at all
    WBC | 7.2 | 4.0 - 11.0 K/uL | 10
    """
    panels = parse_extracted_text(text)
    assert len(panels[0].rows) == 1
