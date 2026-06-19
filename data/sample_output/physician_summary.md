# LabLens Physician Summary

Synthetic demonstration report. Not for clinical use.

This report is designed to support a short clinical review conversation. It preserves the source laboratory reference interval while adding patient-specific descriptive statistics.

## Review priorities

- **Respiratory Syncytial Virus**: `DETECTED` on 2026-04-20 (panel: RESPIRATORY PATHOGEN PANEL) — qualitative finding, review recommended.
- **Aspartate aminotransferase**: latest 13 U/L on 2026-01-14; lab status **low**; personal baseline **insufficient history**; trend **insufficient data**.
- **Glucose**: latest 188 mg/dL on 2026-02-10; lab status **high**; personal baseline **insufficient history**; trend **insufficient data**.
- **Potassium**: latest 4.1 mmol/L on 2026-05-01; lab status **normal**; personal baseline **within observed personal range**; trend **rising**.

## Qualitative results

**Flagged abnormal/detected:**

- **Respiratory Syncytial Virus**: `DETECTED` on 2026-04-20 (panel: RESPIRATORY PATHOGEN PANEL)

Other qualitative results:

- Influenza Virus Type A: `Not Detected` on 2026-04-20
- Leukocyte Esterase: `Trace` on 2026-02-10

## Longitudinal lab summary

| Priority | Test | Latest | Lab range | Lab flag | Personal median | Mean | Personal IQR | Δ from median | N | Trend |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| review first | Aspartate aminotransferase | 13 U/L | 15–41 U/L | low | 14.5 U/L | 14.5 U/L | 13.75–15.25 U/L | -10% | 2 | · insufficient data |
| review first | Glucose | 188 mg/dL | 70–99 mg/dL | high | 188 mg/dL | 188 mg/dL | 188–188 mg/dL | 0% | 1 | · insufficient data |
| review | Potassium | 4.1 mmol/L | 3.5–5.1 mmol/L | normal | 3.9 mmol/L | 4.2 mmol/L | 3.63–4.47 mmol/L | +5% | 4 | ↑ rising |
| monitor trend | Absolute neutrophil count | 3.9 10^3/uL | 1.5–7.8 10^3/uL | normal | 3.9 10^3/uL | 4.03 10^3/uL | 3.65–4.35 10^3/uL | 0% | 3 | ↑ rising |
| monitor trend | Hematocrit | 37.9 % | 35–45 % | normal | 38.75 % | 38.8 % | 38.27–39.28 % | -2% | 4 | → stable |
| routine | Alanine aminotransferase | 12 U/L | 7–52 U/L | normal | 13 U/L | 13 U/L | 12.5–13.5 U/L | -8% | 2 | · insufficient data |
| routine | C-reactive protein | 5.4 mg/L | <8 mg/L | normal | 8.3 mg/L | 8.3 mg/L | 6.85–9.75 mg/L | -35% | 2 | · insufficient data |
| routine | Creatinine | 0.8 mg/dL | 0.44–1.03 mg/dL | normal | 0.81 mg/dL | 0.81 mg/dL | 0.79–0.82 mg/dL | -1% | 4 | → stable |
| routine | Hemoglobin | 13 g/dL | 11–15.1 g/dL | normal | 13 g/dL | 13.04 g/dL | 12.9–13.1 g/dL | 0% | 5 | → stable |
| routine | Platelet count | 342 10^3/uL | 140–400 10^3/uL | normal | 330 10^3/uL | 329 10^3/uL | 313.75–345.25 10^3/uL | +4% | 4 | → stable |
| routine | Red blood cell count | 4.45 M/uL | 3.7–5.1 M/uL | normal | 4.41 M/uL | 4.41 M/uL | 4.38–4.45 M/uL | +1% | 5 | → stable |
| routine | Sodium | 138 mmol/L | 136–145 mmol/L | normal | 138 mmol/L | 138 mmol/L | 137.75–138.25 mmol/L | 0% | 4 | → stable |
| routine | White blood cell count | 6 K/uL | 4–11 K/uL | normal | 6.1 K/uL | 6.3 K/uL | 6–6.4 K/uL | -2% | 5 | → stable |

## How to read this

- **Lab range** is the reference interval extracted from the source document for that specific result.
- **Personal median and IQR** describe the synthetic patient's observed baseline across available results.
- **Δ from median** helps highlight values that may be normal by population range but unusual for this patient.
- **Priority** is a descriptive review flag, not medical advice or diagnosis.
- Rows with uncertain extraction or unmapped units should be reviewed before use.