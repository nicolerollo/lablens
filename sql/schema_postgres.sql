-- LabLens schema, ported to PostgreSQL.
--
-- This is a direct translation of sql/schema.sql (the schema the demo pipeline actually runs
-- against, via SQLite). It is provided to show the migration path to a multi-user deployment
-- target; the application code in src/lablens/database.py still targets SQLite for the demo and
-- is not (yet) wired up to run against this file. See docs/database.md "PostgreSQL migration
-- path" for what would need to change in database.py to make this the live backend.
--
-- Differences from schema.sql:
--   * INTEGER PRIMARY KEY AUTOINCREMENT -> GENERATED ALWAYS AS IDENTITY
--   * SQLite's permissive INTEGER-as-boolean for contains_phi -> BOOLEAN
--   * CURRENT_TIMESTAMP -> TIMESTAMPTZ DEFAULT now()
--   * CREATE VIEW IF NOT EXISTS -> CREATE OR REPLACE VIEW (Postgres has no IF NOT EXISTS for views)
--   * UPPER(alias_raw) functional index syntax is unchanged; Postgres supports it natively

CREATE TABLE IF NOT EXISTS patients (
    patient_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_patient_key TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL DEFAULT 'Synthetic Demo Patient',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_documents (
    source_document_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
    filename TEXT NOT NULL,
    document_type TEXT NOT NULL DEFAULT 'extracted_pdf_text',
    source_system TEXT,
    document_date DATE,
    contains_phi BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    extraction_run_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_document_id INTEGER NOT NULL REFERENCES source_documents(source_document_id),
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    extraction_started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    extraction_status TEXT NOT NULL DEFAULT 'completed',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS canonical_lab_tests (
    canonical_test_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_name TEXT UNIQUE NOT NULL,
    loinc_code TEXT,
    default_unit TEXT,
    result_kind TEXT NOT NULL CHECK (result_kind IN ('quantitative', 'qualitative', 'mixed')),
    body_system TEXT
);

CREATE TABLE IF NOT EXISTS lab_test_aliases (
    alias_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_test_id INTEGER NOT NULL REFERENCES canonical_lab_tests(canonical_test_id),
    alias_raw TEXT NOT NULL,
    source_lab TEXT,
    confidence REAL NOT NULL DEFAULT 0.90,
    UNIQUE (alias_raw, source_lab)
);

CREATE TABLE IF NOT EXISTS lab_panels (
    lab_panel_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_document_id INTEGER NOT NULL REFERENCES source_documents(source_document_id),
    extraction_run_id INTEGER NOT NULL REFERENCES extraction_runs(extraction_run_id),
    panel_name_raw TEXT NOT NULL,
    collection_date DATE NOT NULL,
    source_page_start INTEGER,
    source_page_end INTEGER,
    performing_lab_raw TEXT
);

CREATE TABLE IF NOT EXISTS units (
    unit_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unit_raw TEXT UNIQUE NOT NULL,
    normalized_unit TEXT,
    unit_family TEXT,
    conversion_factor_to_normalized REAL DEFAULT 1.0,
    conversion_note TEXT
);

CREATE TABLE IF NOT EXISTS lab_results (
    lab_result_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
    lab_panel_id INTEGER NOT NULL REFERENCES lab_panels(lab_panel_id),
    source_document_id INTEGER NOT NULL REFERENCES source_documents(source_document_id),
    extraction_run_id INTEGER NOT NULL REFERENCES extraction_runs(extraction_run_id),
    canonical_test_id INTEGER REFERENCES canonical_lab_tests(canonical_test_id),
    unit_id INTEGER REFERENCES units(unit_id),

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS review_queue (
    review_item_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lab_result_id INTEGER NOT NULL REFERENCES lab_results(lab_result_id),
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'ignored')),
    reviewer_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW v_normalized_lab_results AS
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

-- See sql/schema.sql for why this expression index is needed: Postgres, like SQLite, treats every
-- NULL as distinct under UNIQUE(alias_raw, source_lab), so generic (source_lab IS NULL) aliases
-- would otherwise duplicate on every re-seed.
CREATE UNIQUE INDEX IF NOT EXISTS idx_alias_unique_generic
ON lab_test_aliases (UPPER(alias_raw), COALESCE(source_lab, ''));

CREATE INDEX IF NOT EXISTS idx_unit_lookup
ON units (UPPER(unit_raw));
