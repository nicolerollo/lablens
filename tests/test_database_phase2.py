import pytest

from lablens.database import (
    connect,
    connect_existing,
    insert_results,
    fetch_numeric_results,
    fetch_review_queue,
    fetch_qualitative_results,
    export_review_queue_csv,
    resolve_canonical_test,
)
from lablens.normalizer import normalize_row


def test_phase2_schema_inserts_normalized_result(tmp_path):
    db_path = tmp_path / "lablens.sqlite"
    conn = connect(db_path)
    result = normalize_row(
        "CBC WITH DIFFERENTIAL",
        "2026-01-01",
        {
            "test_name_raw": "WBC",
            "value_raw": "7.2",
            "ref_range_raw": "4.0 - 11.0 K/uL",
            "source_page": 3,
            "confidence": 0.95,
        },
    )
    insert_results(conn, [result])

    rows = fetch_numeric_results(conn)
    assert len(rows) == 1
    assert rows[0]["canonical_test_name"] == "White blood cell count"
    assert rows[0]["numeric_value"] == 7.2
    assert rows[0]["interpretation"] == "normal"

    stored = conn.execute("SELECT COUNT(*) AS n FROM lab_results").fetchone()["n"]
    assert stored == 1

    # insert_results() also writes the DB-resolved canonical name back onto the in-memory
    # NormalizedLabResult, so callers (e.g. the JSON export in demo.py) see it without a
    # second query -- it starts out None straight out of normalize_row().
    assert result.canonical_test_name == "White blood cell count"


def test_alias_resolution_is_database_driven_not_hardcoded(tmp_path):
    """lab_test_aliases is the single source of truth for raw-name -> canonical-test mapping.
    Adding a brand-new alias row (no Python code change) must immediately change resolution."""
    db_path = tmp_path / "lablens.sqlite"
    conn = connect(db_path)

    # "Total Leukocyte Ct" is not seeded anywhere -- it should come back unmapped.
    before_id, before_name = resolve_canonical_test(conn, "Total Leukocyte Ct")
    assert before_id is None
    assert before_name is None

    wbc_id = conn.execute(
        "SELECT canonical_test_id FROM canonical_lab_tests WHERE canonical_name = 'White blood cell count'"
    ).fetchone()["canonical_test_id"]
    conn.execute(
        "INSERT INTO lab_test_aliases (canonical_test_id, alias_raw, confidence) VALUES (?, ?, 0.9)",
        (wbc_id, "Total Leukocyte Ct"),
    )
    conn.commit()

    after_id, after_name = resolve_canonical_test(conn, "Total Leukocyte Ct")
    assert after_id == wbc_id
    assert after_name == "White blood cell count"

    # Matching is case/whitespace-insensitive on alias_raw.
    mixed_case_id, _ = resolve_canonical_test(conn, "  total   leukocyte ct ")
    assert mixed_case_id == wbc_id

    # And a row using that brand-new alias resolves end-to-end through insert_results(), with
    # the original raw test name preserved exactly.
    result = normalize_row(
        "CBC WITH DIFFERENTIAL",
        "2026-01-01",
        {"test_name_raw": "Total Leukocyte Ct", "value_raw": "6.5", "ref_range_raw": "4.0 - 11.0 K/uL"},
    )
    insert_results(conn, [result])
    rows = fetch_numeric_results(conn)
    assert rows[0]["canonical_test_name"] == "White blood cell count"
    assert rows[0]["test_name_raw"] == "Total Leukocyte Ct"


def test_resolve_canonical_test_prefers_source_specific_alias_over_generic(tmp_path):
    """The same raw alias can mean different canonical concepts for different source systems
    (e.g. 'CRP' meaning plain CRP generically but high-sensitivity CRP for one specific source).
    Resolution must prefer an exact source_system match over a generic (source_lab IS NULL) row,
    and must NOT fall back to a different source's specific mapping."""
    db_path = tmp_path / "lablens.sqlite"
    conn = connect(db_path)

    crp_id = conn.execute(
        "SELECT canonical_test_id FROM canonical_lab_tests WHERE canonical_name = 'C-reactive protein'"
    ).fetchone()["canonical_test_id"]
    conn.execute(
        """
        INSERT INTO canonical_lab_tests (canonical_name, result_kind, body_system)
        VALUES ('High-sensitivity CRP', 'quantitative', 'inflammation')
        """
    )
    hscrp_id = conn.execute(
        "SELECT canonical_test_id FROM canonical_lab_tests WHERE canonical_name = 'High-sensitivity CRP'"
    ).fetchone()["canonical_test_id"]
    conn.execute(
        "INSERT INTO lab_test_aliases (canonical_test_id, alias_raw, source_lab, confidence) VALUES (?, 'CRP', 'lab_b', 0.9)",
        (hscrp_id,),
    )
    conn.commit()

    # lab_b's source-specific alias wins over the generic 'CRP' -> C-reactive protein mapping.
    lab_b_id, lab_b_name = resolve_canonical_test(conn, "CRP", source_system="lab_b")
    assert lab_b_id == hscrp_id
    assert lab_b_name == "High-sensitivity CRP"

    # A different (or no) source system falls back to the generic mapping, not lab_b's override.
    other_id, other_name = resolve_canonical_test(conn, "CRP", source_system="lab_c")
    assert other_id == crp_id
    assert other_name == "C-reactive protein"

    no_source_id, _ = resolve_canonical_test(conn, "CRP")
    assert no_source_id == crp_id


def test_cbc_unit_variants_resolve_without_hitting_review_queue(tmp_path):
    """Common real-world CBC unit spellings should normalize cleanly instead of generating
    noisy ambiguous_unit review-queue rows for something that isn't actually ambiguous."""
    db_path = tmp_path / "lablens.sqlite"
    conn = connect(db_path)
    variants = [
        ("WBC", "6.0", "10^3/uL"),
        ("WBC", "6.1", "x10^3/uL"),
        ("WBC", "6.2", "X10^3/uL"),
        ("WBC", "6.3", "10*3/uL"),
        ("WBC", "6.4", "k/ul"),  # lowercase, case-insensitive match
        ("RBC", "4.4", "10^6/uL"),
        ("RBC", "4.5", "M/µL"),
        ("RBC", "4.6", "M/mcL"),
    ]
    results = [
        normalize_row("CBC WITH DIFFERENTIAL", "2026-01-01",
                      {"test_name_raw": name, "value_raw": value, "unit_raw": unit, "ref_range_raw": None})
        for name, value, unit in variants
    ]
    insert_results(conn, results)

    statuses = {
        row["normalization_status"]
        for row in conn.execute("SELECT normalization_status FROM lab_results")
    }
    assert statuses == {"normalized"}

    review = fetch_review_queue(conn)
    assert review == []


def test_unmapped_test_enters_review_queue(tmp_path):
    db_path = tmp_path / "lablens.sqlite"
    conn = connect(db_path)
    result = normalize_row(
        "MYSTERY PANEL",
        "2026-01-01",
        {
            "test_name_raw": "Imaginary Biomarker",
            "value_raw": "42",
            "ref_range_raw": "0 - 10 units",
            "source_page": 9,
            "confidence": 0.70,
        },
    )
    insert_results(conn, [result])
    review = fetch_review_queue(conn)
    assert len(review) >= 1
    assert review[0]["test_name_raw"] == "Imaginary Biomarker"


def test_abnormal_qualitative_result_reaches_report_feed_and_review_queue(tmp_path):
    db_path = tmp_path / "lablens.sqlite"
    conn = connect(db_path)
    result = normalize_row(
        "RESPIRATORY PATHOGEN PANEL",
        "2026-04-20",
        {"test_name_raw": "Respiratory Syncytial Virus", "value_raw": "DETECTED", "ref_range_raw": "Not Detected"},
    )
    insert_results(conn, [result])

    qualitative_rows = fetch_qualitative_results(conn)
    assert len(qualitative_rows) == 1
    assert qualitative_rows[0]["qualitative_value"] == "DETECTED"
    assert qualitative_rows[0]["interpretation"] == "qualitative_abnormal"

    review = fetch_review_queue(conn)
    assert any("abnormal" in r["reason"].lower() for r in review)


def test_same_draw_from_two_sources_is_flagged_as_possible_duplicate(tmp_path):
    db_path = tmp_path / "lablens.sqlite"
    conn = connect(db_path)
    result = normalize_row(
        "COMPREHENSIVE METABOLIC PANEL",
        "2026-02-10",
        {"test_name_raw": "Sodium", "value_raw": "137", "ref_range_raw": "136 - 145 mmol/L"},
    )

    insert_results(conn, [result], filename="a.txt", source_system="system_a")
    insert_results(conn, [result], filename="b.txt", source_system="system_b")

    statuses = [
        row["normalization_status"]
        for row in conn.execute("SELECT normalization_status FROM lab_results ORDER BY lab_result_id")
    ]
    assert statuses == ["normalized", "possible_duplicate"]

    # The duplicate must not be double-counted in the numeric feed baseline analytics consume.
    numeric_rows = fetch_numeric_results(conn)
    assert len(numeric_rows) == 1


def test_unmapped_numeric_test_does_not_break_baseline_grouping(tmp_path):
    """Regression test: a numeric result for a test with no canonical mapping has
    canonical_test_name=NULL. fetch_numeric_results() must exclude it, since grouping by
    a NULL key previously crashed compute_baselines() when sorting (str vs NoneType)."""
    db_path = tmp_path / "lablens.sqlite"
    conn = connect(db_path)
    result = normalize_row(
        "COMPREHENSIVE METABOLIC PANEL",
        "2026-02-10",
        {"test_name_raw": "Magnesium", "value_raw": "2.0", "ref_range_raw": "1.7 - 2.2 mg/dL"},
    )
    insert_results(conn, [result])

    numeric_rows = fetch_numeric_results(conn)
    assert all(row["canonical_test_name"] is not None for row in numeric_rows)

    review = fetch_review_queue(conn)
    assert any(r["test_name_raw"] == "Magnesium" for r in review)


def test_export_review_queue_csv(tmp_path):
    db_path = tmp_path / "lablens.sqlite"
    conn = connect(db_path)
    result = normalize_row(
        "MYSTERY PANEL",
        "2026-01-01",
        {"test_name_raw": "Imaginary Biomarker", "value_raw": "42", "ref_range_raw": "0 - 10 units"},
    )
    insert_results(conn, [result])

    csv_path = export_review_queue_csv(conn, tmp_path / "review_queue.csv")
    content = csv_path.read_text(encoding="utf-8")
    assert "reason" in content.splitlines()[0]
    assert "Imaginary Biomarker" in content


def test_connecting_repeatedly_does_not_duplicate_generic_aliases(tmp_path):
    """Regression test: lab_test_aliases.UNIQUE(alias_raw, source_lab) does not stop duplicate
    generic aliases, because SQL treats every source_lab=NULL as distinct from every other NULL.
    Reconnecting to an existing database (which re-runs seed_reference_data()) must not grow the
    alias table -- see the idx_alias_unique_generic expression index in sql/schema.sql."""
    db_path = tmp_path / "lablens.sqlite"

    conn = connect(db_path)
    first_count = conn.execute("SELECT COUNT(*) AS n FROM lab_test_aliases").fetchone()["n"]
    assert first_count > 0
    conn.close()

    for _ in range(4):
        conn = connect(db_path)
        count = conn.execute("SELECT COUNT(*) AS n FROM lab_test_aliases").fetchone()["n"]
        assert count == first_count
        conn.close()


def test_connect_existing_does_not_seed_or_require_creation(tmp_path):
    db_path = tmp_path / "lablens.sqlite"

    with pytest.raises(FileNotFoundError):
        connect_existing(db_path)

    connect(db_path).close()
    before = connect_existing(db_path).execute("SELECT COUNT(*) AS n FROM lab_test_aliases").fetchone()["n"]

    # Opening for read multiple times must not change the seeded reference data at all.
    for _ in range(3):
        conn = connect_existing(db_path)
        after = conn.execute("SELECT COUNT(*) AS n FROM lab_test_aliases").fetchone()["n"]
        assert after == before
        conn.close()
