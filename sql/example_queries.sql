-- Example portfolio queries for LabLens Phase 2.

-- 1. Trend one canonical test over time, merged across every source system the patient's
--    records were extracted from (e.g. a military-health-style export and a academic-medical-center-style
--    export both contribute rows here).
SELECT collection_date, canonical_name, numeric_value, normalized_unit, lab_interpretation, source_document
FROM v_normalized_lab_results
WHERE canonical_name = 'White blood cell count'
ORDER BY collection_date;

-- 1b. Same test, but show which source system each result came from -- this is the
--     "fragmented across providers, unified by LabLens" story in one query.
SELECT v.collection_date, v.canonical_name, v.numeric_value, v.normalized_unit,
       v.lab_interpretation, sd.source_system, sd.filename
FROM v_normalized_lab_results v
JOIN lab_results lr ON lr.lab_result_id = v.lab_result_id
JOIN source_documents sd ON sd.source_document_id = lr.source_document_id
WHERE v.canonical_name = 'Potassium'
ORDER BY v.collection_date;

-- 2. Show abnormal results by the performing lab's own reference range.
SELECT collection_date, panel, canonical_name, numeric_value, normalized_unit, ref_range_raw, lab_interpretation
FROM v_normalized_lab_results
WHERE lab_interpretation IN ('high', 'low')
ORDER BY collection_date DESC, canonical_name;

-- 3. Show raw aliases that map to one canonical test.
SELECT ct.canonical_name, lta.alias_raw, lta.source_lab, lta.confidence
FROM lab_test_aliases lta
JOIN canonical_lab_tests ct ON ct.canonical_test_id = lta.canonical_test_id
WHERE ct.canonical_name = 'Platelet count';

-- 4. Find rows that need human review.
SELECT collection_date, panel, test_name_raw, value_raw, unit_raw, ref_range_raw, normalization_status, confidence
FROM v_normalized_lab_results
WHERE normalization_status != 'normalized' OR confidence < 0.75
ORDER BY collection_date DESC;

-- 5. Compute personal baseline from normalized numeric values.
SELECT canonical_name,
       COUNT(*) AS observations,
       MIN(numeric_value) AS min_value,
       AVG(numeric_value) AS mean_value,
       MAX(numeric_value) AS max_value
FROM v_normalized_lab_results
WHERE numeric_value IS NOT NULL
GROUP BY canonical_name
HAVING COUNT(*) >= 2
ORDER BY canonical_name;

-- 6. List every source system contributing to one patient's record, with row counts.
--    Useful for sanity-checking that multi-source ingestion is actually merging data,
--    not silently creating duplicate per-source patient histories.
SELECT sd.source_system, sd.filename, COUNT(lr.lab_result_id) AS result_count
FROM source_documents sd
JOIN lab_results lr ON lr.source_document_id = sd.source_document_id
GROUP BY sd.source_system, sd.filename
ORDER BY sd.source_system;

-- 7. Qualitative (non-numeric) results flagged abnormal, such as a positive pathogen test.
--    These are easy to silently drop in a numeric-only pipeline, so they get their own check.
SELECT collection_date, panel, test_name_raw, qualitative_value, lab_interpretation
FROM v_normalized_lab_results
WHERE numeric_value IS NULL AND lab_interpretation = 'qualitative_abnormal'
ORDER BY collection_date DESC;

-- 8. Results flagged as possible duplicates across source systems (e.g. a referral lab
--    reporting the same draw back to two different downstream systems). These are excluded
--    from fetch_numeric_results()/baseline analytics but kept visible here for audit.
SELECT collection_date, test_name_raw, value_raw, normalization_status
FROM v_normalized_lab_results
WHERE normalization_status = 'possible_duplicate';
