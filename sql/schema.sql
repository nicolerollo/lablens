-- LabLens Phase 2 normalized relational schema (SQLite-compatible).
-- Design goal: preserve source truth while supporting cleaned longitudinal analytics.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS patients (
    patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_patient_key TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL DEFAULT 'Synthetic Demo Patient',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_documents (
    source_document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    document_type TEXT NOT NULL DEFAULT 'extracted_pdf_text',
    source_system TEXT,
    document_date TEXT,
    contains_phi INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    extraction_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_document_id INTEGER NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    extraction_started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    extraction_status TEXT NOT NULL DEFAULT 'completed',
    notes TEXT,
    FOREIGN KEY (source_document_id) REFERENCES source_documents(source_document_id)
);

CREATE TABLE IF NOT EXISTS canonical_lab_tests (
    canonical_test_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT UNIQUE NOT NULL,
    loinc_code TEXT,
    default_unit TEXT,
    result_kind TEXT NOT NULL CHECK (result_kind IN ('quantitative', 'qualitative', 'mixed')),
    body_system TEXT
);

CREATE TABLE IF NOT EXISTS lab_test_aliases (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_test_id INTEGER NOT NULL,
    alias_raw TEXT NOT NULL,
    source_lab TEXT,
    confidence REAL NOT NULL DEFAULT 0.90,
    FOREIGN KEY (canonical_test_id) REFERENCES canonical_lab_tests(canonical_test_id),
    UNIQUE(alias_raw, source_lab)
);

CREATE TABLE IF NOT EXISTS lab_panels (
    lab_panel_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_document_id INTEGER NOT NULL,
    extraction_run_id INTEGER NOT NULL,
    panel_name_raw TEXT NOT NULL,
    collection_date TEXT NOT NULL,
    source_page_start INTEGER,
    source_page_end INTEGER,
    performing_lab_raw TEXT,
    FOREIGN KEY (source_document_id) REFERENCES source_documents(source_document_id),
    FOREIGN KEY (extraction_run_id) REFERENCES extraction_runs(extraction_run_id)
);

CREATE TABLE IF NOT EXISTS units (
    unit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_raw TEXT UNIQUE NOT NULL,
    normalized_unit TEXT,
    unit_family TEXT,
    conversion_factor_to_normalized REAL DEFAULT 1.0,
    conversion_note TEXT
);

CREATE TABLE IF NOT EXISTS lab_results (
    lab_result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    lab_panel_id INTEGER NOT NULL,
    source_document_id INTEGER NOT NULL,
    extraction_run_id INTEGER NOT NULL,
    canonical_test_id INTEGER,
    unit_id INTEGER,

    test_name_raw TEXT NOT NULL,
    value_raw TEXT NOT NULL,
    unit_raw TEXT,
    ref_range_raw TEXT,
    source_page INTEGER,
    source_text TEXT,

    numeric_value REAL,
    qualitative_value TEXT,
    normalized_value REAL,
    normalized_unit TEXT,

    lab_ref_low REAL,
    lab_ref_high REAL,
    lab_ref_comparator TEXT,
    lab_interpretation TEXT NOT NULL,

    normalization_status TEXT NOT NULL DEFAULT 'normalized'
        CHECK (normalization_status IN (
            'normalized', 'needs_review', 'unmapped_test', 'ambiguous_unit', 'possible_duplicate'
        )),
    confidence REAL NOT NULL DEFAULT 0.80,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
    FOREIGN KEY (lab_panel_id) REFERENCES lab_panels(lab_panel_id),
    FOREIGN KEY (source_document_id) REFERENCES source_documents(source_document_id),
    FOREIGN KEY (extraction_run_id) REFERENCES extraction_runs(extraction_run_id),
    FOREIGN KEY (canonical_test_id) REFERENCES canonical_lab_tests(canonical_test_id),
    FOREIGN KEY (unit_id) REFERENCES units(unit_id)
);

CREATE TABLE IF NOT EXISTS review_queue (
    review_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    lab_result_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'ignored')),
    reviewer_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lab_result_id) REFERENCES lab_results(lab_result_id)
);

CREATE VIEW IF NOT EXISTS v_normalized_lab_results AS
SELECT
    lr.lab_result_id,
    p.external_patient_key,
    lp.collection_date,
    lp.panel_name_raw AS panel,
    ct.canonical_name,
    lr.test_name_raw,
    lr.value_raw,
    lr.numeric_value,
    lr.qualitative_value,
    lr.unit_raw,
    lr.normalized_value,
    lr.normalized_unit,
    lr.ref_range_raw,
    lr.lab_ref_low,
    lr.lab_ref_high,
    lr.lab_ref_comparator,
    lr.lab_interpretation,
    lr.normalization_status,
    lr.confidence,
    sd.filename AS source_document,
    lr.source_page
FROM lab_results lr
JOIN patients p ON p.patient_id = lr.patient_id
JOIN lab_panels lp ON lp.lab_panel_id = lr.lab_panel_id
JOIN source_documents sd ON sd.source_document_id = lr.source_document_id
LEFT JOIN canonical_lab_tests ct ON ct.canonical_test_id = lr.canonical_test_id;

CREATE INDEX IF NOT EXISTS idx_lab_results_patient_test_date
ON lab_results (patient_id, canonical_test_id, lab_panel_id);

CREATE INDEX IF NOT EXISTS idx_lab_panels_collection_date
ON lab_panels (collection_date);

CREATE INDEX IF NOT EXISTS idx_alias_lookup
ON lab_test_aliases (UPPER(alias_raw));

-- The table-level UNIQUE(alias_raw, source_lab) constraint does NOT prevent duplicate generic
-- aliases: SQL treats every NULL as distinct from every other NULL, so two rows with the same
-- alias_raw and source_lab = NULL do not violate it. Most seeded aliases are generic
-- (source_lab IS NULL), so without this expression index, re-running seed_reference_data()
-- against an existing database (e.g. every call to connect()) would insert duplicates of every
-- generic alias each time. COALESCE(source_lab, '') collapses all NULLs to the same value for
-- uniqueness purposes, closing that gap; UPPER(alias_raw) keeps matching case-insensitive,
-- consistent with how resolve_canonical_test() looks rows up.
CREATE UNIQUE INDEX IF NOT EXISTS idx_alias_unique_generic
ON lab_test_aliases (UPPER(alias_raw), COALESCE(source_lab, ''));

CREATE INDEX IF NOT EXISTS idx_unit_lookup
ON units (UPPER(unit_raw));
