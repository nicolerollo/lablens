from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path
from .normalizer import NormalizedLabResult

# Path-based, relative to the repo checkout -- works for an editable install (`pip install -e .`)
# run from a source checkout, which is the only way this project is currently installed. A built
# wheel would not package sql/ unless it were added as package data, so this would need to move to
# importlib.resources (with sql/ moved inside the package) before publishing a wheel. See
# docs/database.md "A packaging caveat" for the tradeoff.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"


def _read_schema() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def _open(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) a database and ensure the schema and reference data are present.

    This is the right call for anything that might be writing new data -- the demo, `lablens
    ingest`, or a fresh database. It is idempotent (safe to call repeatedly against the same
    database) but it does still execute the schema script and a reference-data upsert on every
    call, which is unnecessary work -- and an unnecessary write -- for something that only reads.
    Use `connect_existing()` instead for read-only workflows like `lablens report` or
    `lablens export-review`.
    """
    conn = _open(db_path)
    conn.executescript(_read_schema())
    seed_reference_data(conn)
    return conn


# Alias documenting intent at call sites that are specifically creating a brand-new database
# (the demo, `lablens ingest`), as opposed to reusing `connect()` out of habit.
initialize_database = connect


def connect_existing(db_path: str | Path) -> sqlite3.Connection:
    """Open an already-initialized database without re-running schema/seed writes.

    Use this for read-only workflows (`lablens report`, `lablens export-review`) so that simply
    reading a database doesn't also re-execute `seed_reference_data()` against it. Raises if the
    database file doesn't exist yet -- a read-only command has nothing to read from a database
    that was never created with `connect()`/`initialize_database()`.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found: {path}. Run `lablens ingest` (or `lablens demo`) to create it first."
        )
    return _open(path)


def seed_reference_data(conn: sqlite3.Connection) -> None:
    """Seed minimal synthetic canonical lab metadata and alias mappings."""
    canonical_tests = [
        ("White blood cell count", None, "K/uL", "quantitative", "hematology"),
        ("Red blood cell count", None, "M/uL", "quantitative", "hematology"),
        ("Hemoglobin", None, "g/dL", "quantitative", "hematology"),
        ("Hematocrit", None, "%", "quantitative", "hematology"),
        ("Platelet count", None, "K/uL", "quantitative", "hematology"),
        ("Absolute neutrophil count", None, "K/uL", "quantitative", "hematology"),
        ("Potassium", None, "mmol/L", "quantitative", "chemistry"),
        ("Sodium", None, "mmol/L", "quantitative", "chemistry"),
        ("Creatinine", None, "mg/dL", "quantitative", "chemistry"),
        ("Alanine aminotransferase", None, "U/L", "quantitative", "chemistry"),
        ("Aspartate aminotransferase", None, "U/L", "quantitative", "chemistry"),
        ("C-reactive protein", None, "mg/L", "quantitative", "inflammation"),
        ("Glucose", None, "mg/dL", "quantitative", "chemistry"),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO canonical_lab_tests
            (canonical_name, loinc_code, default_unit, result_kind, body_system)
        VALUES (?, ?, ?, ?, ?)
        """,
        canonical_tests,
    )

    aliases = {
        "White blood cell count": ["WBC", "White Blood Cell Count", "Leukocytes"],
        "Red blood cell count": ["RBC", "Red Blood Cell Count"],
        "Hemoglobin": ["Hemoglobin", "Hgb"],
        "Hematocrit": ["Hematocrit", "Hct"],
        "Platelet count": ["Platelet Count", "Platelets", "PLT"],
        "Absolute neutrophil count": ["Abs Neutrophils", "Neutrophils Absolute", "Automated Abs Neutrophil Cnt"],
        "Potassium": ["Potassium", "Potassium, Blood"],
        "Sodium": ["Sodium", "Sodium, Blood"],
        "Creatinine": ["Creatinine"],
        "Alanine aminotransferase": ["ALT", "Alanine Aminotransferase"],
        "Aspartate aminotransferase": ["AST", "Aspartate Aminotransferase"],
        "C-reactive protein": ["CRP", "C-Reactive Protein", "C Reactive Protein"],
        "Glucose": ["Glucose", "Glucose, Fasting", "Fasting Glucose"],
    }
    for canonical_name, raw_aliases in aliases.items():
        canonical_id = conn.execute(
            "SELECT canonical_test_id FROM canonical_lab_tests WHERE canonical_name = ?",
            (canonical_name,),
        ).fetchone()["canonical_test_id"]
        conn.executemany(
            """
            INSERT OR IGNORE INTO lab_test_aliases
                (canonical_test_id, alias_raw, source_lab, confidence)
            VALUES (?, ?, NULL, 0.95)
            """,
            [(canonical_id, alias) for alias in raw_aliases],
        )

    # Cell-count units are where real-world CBC exports vary the most: "thousands per
    # microliter" gets written as K/uL, X10E3/uL, 10^3/uL, x10^3/uL, 10*3/uL, K/mcL, K/uL with a
    # true micro sign, and more, depending on the system. Each is matched case-insensitively (see
    # `_unit_id()`) and mapped to the same normalized unit so these stop showing up as noisy
    # `ambiguous_unit` review-queue rows for something that is, in fact, completely unambiguous.
    units = [
        # thousands per microliter -> K/uL
        ("K/uL", "K/uL", "cell_count", 1.0, "Already normalized."),
        ("K/µL", "K/uL", "cell_count", 1.0, "True micro-sign (µ) variant of K/uL."),
        ("K/mcL", "K/uL", "cell_count", 1.0, "mcL spelling variant of K/uL."),
        ("X10E3/uL", "K/uL", "cell_count", 1.0, "Scientific-notation variant for thousands per microliter."),
        ("10^3/uL", "K/uL", "cell_count", 1.0, "Caret-exponent variant for thousands per microliter."),
        ("x10^3/uL", "K/uL", "cell_count", 1.0, "Lowercase-x caret-exponent variant."),
        ("X10^3/uL", "K/uL", "cell_count", 1.0, "Uppercase-X caret-exponent variant."),
        ("10*3/uL", "K/uL", "cell_count", 1.0, "Asterisk-exponent variant for thousands per microliter."),
        # millions per microliter -> M/uL
        ("M/uL", "M/uL", "cell_count", 1.0, "Already normalized."),
        ("M/µL", "M/uL", "cell_count", 1.0, "True micro-sign (µ) variant of M/uL."),
        ("M/mcL", "M/uL", "cell_count", 1.0, "mcL spelling variant of M/uL."),
        ("X10E6/uL", "M/uL", "cell_count", 1.0, "Scientific-notation variant for millions per microliter."),
        ("10^6/uL", "M/uL", "cell_count", 1.0, "Caret-exponent variant for millions per microliter."),
        ("x10^6/uL", "M/uL", "cell_count", 1.0, "Lowercase-x caret-exponent variant."),
        ("X10^6/uL", "M/uL", "cell_count", 1.0, "Uppercase-X caret-exponent variant."),
        ("10*6/uL", "M/uL", "cell_count", 1.0, "Asterisk-exponent variant for millions per microliter."),
        # other panels' units
        ("g/dL", "g/dL", "mass_concentration", 1.0, "Already normalized."),
        ("%", "%", "percentage", 1.0, "Already normalized."),
        ("mmol/L", "mmol/L", "molar_concentration", 1.0, "Already normalized."),
        ("mg/dL", "mg/dL", "mass_concentration", 1.0, "Already normalized."),
        ("mg/L", "mg/L", "mass_concentration", 1.0, "Already normalized."),
        ("U/L", "U/L", "enzyme_activity", 1.0, "Already normalized."),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO units
            (unit_raw, normalized_unit, unit_family, conversion_factor_to_normalized, conversion_note)
        VALUES (?, ?, ?, ?, ?)
        """,
        units,
    )
    conn.commit()


def _ensure_demo_context(
    conn: sqlite3.Connection,
    *,
    filename: str = "synthetic_lab_summary.txt",
    document_type: str = "extracted_pdf_text",
    source_system: str = "military_health_style_demo",
    parser_name: str = "lablens_military_health_style_parser",
    parser_version: str = "0.2.0",
    notes: str = "Synthetic upstream PDF-extraction output for portfolio demo.",
) -> tuple[int, int, int]:
    """Create the synthetic patient, source document, and extraction run for one demo input file.

    LabLens models multiple fragmented source systems (e.g. military-health-style and academic-medical-center-style
    portal exports) as distinct `source_documents`/`extraction_runs` rows that share one patient, so
    longitudinal analytics can merge results across systems while still preserving per-source provenance.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO patients (external_patient_key, display_name)
        VALUES ('SYNTH-001', 'Synthetic Demo Patient')
        """
    )
    patient_id = conn.execute(
        "SELECT patient_id FROM patients WHERE external_patient_key = 'SYNTH-001'"
    ).fetchone()["patient_id"]

    conn.execute(
        """
        INSERT INTO source_documents
            (patient_id, filename, document_type, source_system, contains_phi, notes)
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (patient_id, filename, document_type, source_system, notes),
    )
    source_document_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    conn.execute(
        """
        INSERT INTO extraction_runs
            (source_document_id, parser_name, parser_version, extraction_status, notes)
        VALUES (?, ?, ?, 'completed', ?)
        """,
        (
            source_document_id,
            parser_name,
            parser_version,
            f"Rule-based parser for {source_system} extracted PDF text.",
        ),
    )
    extraction_run_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return patient_id, source_document_id, extraction_run_id


def resolve_canonical_test(
    conn: sqlite3.Connection, test_name_raw: str, source_system: str | None = None
) -> tuple[int | None, str | None]:
    """Resolve a raw extracted test name to a canonical lab test via `lab_test_aliases`.

    `lab_test_aliases` is the single source of truth for "many raw names -> one canonical
    concept" -- there is no Python-side alias dictionary. Adding a new alias (e.g. a fourth
    source system's odd spelling of WBC) means inserting one row into `lab_test_aliases`, not
    editing application code. Matching is case/whitespace-insensitive on `alias_raw`; the raw
    test name itself is never altered or guessed at.

    `source_lab` lets the same raw alias mean different things from different sources -- e.g.
    `CRP` could be aliased to `C-reactive protein` generically (`source_lab IS NULL`) but to
    `High-sensitivity CRP` specifically for one source system. Resolution prefers, in order:

    1. an alias row scoped to this exact `source_system`
    2. a generic alias row (`source_lab IS NULL`) that applies regardless of source
    3. otherwise unmapped -- a source-specific alias for a *different* source never matches here,
       so it can't silently steal a row that belongs to another source's mapping
    """
    key = re.sub(r"\s+", " ", test_name_raw.strip())
    row = conn.execute(
        """
        SELECT ct.canonical_test_id, ct.canonical_name
        FROM lab_test_aliases lta
        JOIN canonical_lab_tests ct ON ct.canonical_test_id = lta.canonical_test_id
        WHERE UPPER(lta.alias_raw) = UPPER(?)
          AND (lta.source_lab IS NULL OR lta.source_lab = ?)
        ORDER BY (lta.source_lab IS NULL) ASC, lta.confidence DESC
        LIMIT 1
        """,
        (key, source_system),
    ).fetchone()
    if row is None:
        return None, None
    return int(row["canonical_test_id"]), row["canonical_name"]


def _unit_id(conn: sqlite3.Connection, unit_raw: str | None) -> tuple[int | None, str | None, float | None]:
    """Resolve a raw unit string to its normalized form via `units`, case-insensitively.

    Matching is case-insensitive (`K/UL` and `k/ul` both resolve to the `K/uL` row) but the
    exact raw string is always what gets stored on `lab_results.unit_raw` -- this only affects
    which `units` row a result's FK points to, never the preserved raw text.
    """
    if not unit_raw:
        return None, None, None
    row = conn.execute(
        "SELECT unit_id, normalized_unit, conversion_factor_to_normalized FROM units WHERE UPPER(unit_raw) = UPPER(?)",
        (unit_raw,),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT OR IGNORE INTO units (unit_raw, normalized_unit, unit_family, conversion_note)
            VALUES (?, NULL, 'unknown', 'Unmapped unit preserved for review.')
            """,
            (unit_raw,),
        )
        return conn.execute(
            "SELECT unit_id FROM units WHERE unit_raw = ?", (unit_raw,)
        ).fetchone()["unit_id"], None, None
    return int(row["unit_id"]), row["normalized_unit"], float(row["conversion_factor_to_normalized"])


def insert_results(
    conn: sqlite3.Connection,
    results: list[NormalizedLabResult],
    *,
    filename: str = "synthetic_lab_summary.txt",
    source_system: str = "military_health_style_demo",
    parser_name: str = "lablens_military_health_style_parser",
    parser_version: str = "0.2.0",
) -> None:
    """Insert normalized lab results into the Phase 2 relational schema.

    This intentionally stores raw values and source provenance alongside normalized fields.
    Each call creates one `source_documents`/`extraction_runs` pair tagged with the originating
    system (e.g. a specific patient-portal export), so results from multiple fragmented sources
    can be inserted independently while remaining attributable to where they came from.
    """
    patient_id, source_document_id, extraction_run_id = _ensure_demo_context(
        conn,
        filename=filename,
        source_system=source_system,
        parser_name=parser_name,
        parser_version=parser_version,
    )
    panel_cache: dict[tuple[str, str], int] = {}

    for result in results:
        panel_key = (result.panel, result.collection_date)
        if panel_key not in panel_cache:
            conn.execute(
                """
                INSERT INTO lab_panels
                    (source_document_id, extraction_run_id, panel_name_raw, collection_date,
                     source_page_start, source_page_end, performing_lab_raw)
                VALUES (?, ?, ?, ?, ?, ?, 'Synthetic Demo Laboratory')
                """,
                (
                    source_document_id,
                    extraction_run_id,
                    result.panel,
                    result.collection_date,
                    result.source_page,
                    result.source_page,
                ),
            )
            panel_cache[panel_key] = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

        canonical_id, canonical_name = resolve_canonical_test(conn, result.test_name_raw, source_system=source_system)
        result.canonical_test_name = canonical_name
        unit_id, normalized_unit, factor = _unit_id(conn, result.unit_raw)
        normalized_value = None
        if result.numeric_value is not None and factor is not None:
            normalized_value = result.numeric_value * factor

        duplicate = None
        if canonical_id is not None and result.numeric_value is not None:
            duplicate = conn.execute(
                """
                SELECT sd.source_system
                FROM lab_results lr
                JOIN lab_panels lp ON lp.lab_panel_id = lr.lab_panel_id
                JOIN source_documents sd ON sd.source_document_id = lr.source_document_id
                WHERE lr.patient_id = ? AND lr.canonical_test_id = ? AND lp.collection_date = ?
                      AND lr.numeric_value = ? AND lr.source_document_id != ?
                """,
                (patient_id, canonical_id, result.collection_date, result.numeric_value, source_document_id),
            ).fetchone()

        status = "normalized"
        review_reason = None
        if duplicate is not None:
            status = "possible_duplicate"
            review_reason = (
                f"Matching result already recorded from source_system='{duplicate['source_system']}' "
                "on the same date with the same value -- likely the same draw reported by multiple systems."
            )
        elif canonical_id is None:
            status = "unmapped_test"
            review_reason = "No canonical lab-test mapping found."
        elif result.unit_raw and normalized_unit is None:
            status = "ambiguous_unit"
            review_reason = "Unit was preserved but could not be normalized safely."
        elif result.confidence < 0.75:
            status = "needs_review"
            review_reason = "Parser confidence below review threshold."

        if result.interpretation == "qualitative_abnormal":
            abnormal_reason = "Qualitative result flagged abnormal (e.g. detected/positive); clinical review recommended."
            review_reason = f"{review_reason} {abnormal_reason}" if review_reason else abnormal_reason

        conn.execute(
            """
            INSERT INTO lab_results (
                patient_id, lab_panel_id, source_document_id, extraction_run_id,
                canonical_test_id, unit_id, test_name_raw, value_raw, unit_raw, ref_range_raw,
                source_page, source_text, numeric_value, qualitative_value, normalized_value,
                normalized_unit, lab_ref_low, lab_ref_high, lab_ref_comparator,
                lab_interpretation, normalization_status, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                panel_cache[panel_key],
                source_document_id,
                extraction_run_id,
                canonical_id,
                unit_id,
                result.test_name_raw,
                result.value_raw,
                result.unit_raw,
                result.ref_range_raw,
                result.source_page,
                f"{result.test_name_raw} | {result.value_raw} | {result.ref_range_raw or ''}",
                result.numeric_value,
                result.qualitative_value,
                normalized_value,
                normalized_unit,
                result.ref_low,
                result.ref_high,
                result.ref_comparator,
                result.interpretation,
                status,
                result.confidence,
            ),
        )
        lab_result_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        if review_reason:
            conn.execute(
                "INSERT INTO review_queue (lab_result_id, reason) VALUES (?, ?)",
                (lab_result_id, review_reason),
            )

    conn.commit()


def fetch_numeric_results(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return numeric rows in the shape expected by the analytics layer.

    Rows flagged `possible_duplicate` (the same test/date/value reported by more than one
    source system -- see `insert_results()`) are excluded here so a single draw reported to
    two systems is not double-counted in personal-baseline statistics. The row itself is still
    stored and visible via `fetch_review_queue()`.
    """
    return conn.execute(
        """
        SELECT
            lab_result_id AS id,
            panel,
            collection_date,
            test_name_raw,
            canonical_name AS canonical_test_name,
            value_raw,
            numeric_value,
            qualitative_value,
            unit_raw,
            ref_range_raw,
            lab_ref_low AS ref_low,
            lab_ref_high AS ref_high,
            lab_ref_comparator AS ref_comparator,
            lab_interpretation AS interpretation,
            source_page,
            confidence
        FROM v_normalized_lab_results
        WHERE numeric_value IS NOT NULL
              AND normalization_status != 'possible_duplicate'
              AND canonical_name IS NOT NULL
        ORDER BY canonical_name, collection_date
        """
    ).fetchall()


def fetch_qualitative_results(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return non-numeric rows (e.g. pathogen detected/not detected) so they
    can be surfaced in the physician report instead of being silently dropped."""
    return conn.execute(
        """
        SELECT
            lab_result_id AS id,
            panel,
            collection_date,
            test_name_raw,
            canonical_name AS canonical_test_name,
            qualitative_value,
            lab_interpretation AS interpretation,
            source_page
        FROM v_normalized_lab_results
        WHERE numeric_value IS NULL AND qualitative_value IS NOT NULL
        ORDER BY collection_date DESC, test_name_raw
        """
    ).fetchall()


def fetch_review_queue(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT rq.review_item_id, rq.reason, rq.status, v.*
        FROM review_queue rq
        JOIN lab_results lr ON lr.lab_result_id = rq.lab_result_id
        JOIN v_normalized_lab_results v ON v.lab_result_id = lr.lab_result_id
        ORDER BY rq.created_at DESC
        """
    ).fetchall()


def export_review_queue_csv(conn: sqlite3.Connection, path: str | Path) -> Path:
    """Write the review queue to CSV so a human reviewer can work through it without SQL.

    This is intentionally a flat export, not a review UI -- approving/correcting/rejecting a
    row is still a manual follow-up step (see docs/roadmap.md Milestone 3).
    """
    path = Path(path)
    rows = fetch_review_queue(conn)
    fieldnames = list(rows[0].keys()) if rows else [
        "review_item_id", "reason", "status", "lab_result_id", "canonical_name",
        "test_name_raw", "value_raw", "collection_date", "normalization_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for row in rows:
            writer.writerow([row[key] for key in fieldnames])
    return path
