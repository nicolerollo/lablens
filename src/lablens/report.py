from __future__ import annotations

from html import escape
from pathlib import Path

from .analytics import BaselineSummary


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    text = f"{value:.{digits}f}"
    return text.rstrip("0").rstrip(".")


def _fmt_percent(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.0f}%"


def _fmt_lab_range(summary: BaselineSummary) -> str:
    unit = f" {summary.latest_unit}" if summary.latest_unit else ""
    if summary.latest_ref_comparator == "<" and summary.latest_ref_high is not None:
        return f"<{_fmt(summary.latest_ref_high)}{unit}"
    if summary.latest_ref_comparator == ">" and summary.latest_ref_low is not None:
        return f">{_fmt(summary.latest_ref_low)}{unit}"
    if summary.latest_ref_low is not None and summary.latest_ref_high is not None:
        return f"{_fmt(summary.latest_ref_low)}–{_fmt(summary.latest_ref_high)}{unit}"
    return "—"


def _direction_symbol(text: str) -> str:
    return {"rising": "↑", "falling": "↓", "stable": "→"}.get(text, "·")


def _markdown_priority_section(summaries: list[BaselineSummary], qualitative_rows: list[dict] | None = None) -> list[str]:
    priority = [s for s in summaries if s.review_priority in {"review first", "review"}]
    abnormal_qualitative = [r for r in (qualitative_rows or []) if r["interpretation"] == "qualitative_abnormal"]
    if not priority and not abnormal_qualitative:
        return ["## Review priorities", "", "No synthetic results were flagged for priority review in this demo.", ""]

    lines = ["## Review priorities", ""]
    for r in abnormal_qualitative:
        lines.append(
            f"- **{r['canonical_test_name'] or r['test_name_raw']}**: `{r['qualitative_value']}` "
            f"on {r['collection_date']} (panel: {r['panel']}) — qualitative finding, review recommended."
        )
    for s in priority:
        lines.append(
            f"- **{s.test_name}**: latest {_fmt(s.latest_value)} {s.latest_unit or ''} "
            f"on {s.latest_date}; lab status **{s.latest_interpretation}**; "
            f"personal baseline **{s.personal_baseline_flag}**; trend **{s.trend}**."
        )
    lines.append("")
    return lines


def _markdown_qualitative_section(qualitative_rows: list[dict]) -> list[str]:
    if not qualitative_rows:
        return []
    abnormal = [r for r in qualitative_rows if r["interpretation"] == "qualitative_abnormal"]
    lines = ["## Qualitative results", ""]
    if abnormal:
        lines.append("**Flagged abnormal/detected:**")
        lines.append("")
        for r in abnormal:
            lines.append(
                f"- **{r['canonical_test_name'] or r['test_name_raw']}**: "
                f"`{r['qualitative_value']}` on {r['collection_date']} (panel: {r['panel']})"
            )
        lines.append("")
    others = [r for r in qualitative_rows if r["interpretation"] != "qualitative_abnormal"]
    if others:
        lines.append("Other qualitative results:")
        lines.append("")
        for r in others:
            lines.append(
                f"- {r['canonical_test_name'] or r['test_name_raw']}: `{r['qualitative_value']}` on {r['collection_date']}"
            )
        lines.append("")
    return lines


def generate_markdown_report(summaries: list[BaselineSummary], qualitative_rows: list[dict] | None = None) -> str:
    lines = [
        "# LabLens Physician Summary",
        "",
        "Synthetic demonstration report. Not for clinical use.",
        "",
        "This report is designed to support a short clinical review conversation. It preserves the source laboratory reference interval while adding patient-specific descriptive statistics.",
        "",
    ]
    lines.extend(_markdown_priority_section(summaries, qualitative_rows))
    lines.extend(_markdown_qualitative_section(qualitative_rows or []))
    lines.extend(
        [
            "## Longitudinal lab summary",
            "",
            "| Priority | Test | Latest | Lab range | Lab flag | Personal median | Mean | Personal IQR | Δ from median | N | Trend |",
            "|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for s in summaries:
        unit = f" {s.latest_unit}" if s.latest_unit else ""
        lines.append(
            f"| {s.review_priority} | {s.test_name} | {_fmt(s.latest_value)}{unit} | {_fmt_lab_range(s)} | "
            f"{s.latest_interpretation} | {_fmt(s.median_value)}{unit} | {_fmt(s.mean_value)}{unit} | "
            f"{_fmt(s.iqr_low)}–{_fmt(s.iqr_high)}{unit} | {_fmt_percent(s.percent_from_median)} | "
            f"{s.observations} | {_direction_symbol(s.trend)} {s.trend} |"
        )
    lines.extend(
        [
            "",
            "## How to read this",
            "",
            "- **Lab range** is the reference interval extracted from the source document for that specific result.",
            "- **Personal median and IQR** describe the synthetic patient's observed baseline across available results.",
            "- **Δ from median** helps highlight values that may be normal by population range but unusual for this patient.",
            "- **Priority** is a descriptive review flag, not medical advice or diagnosis.",
            "- Rows with uncertain extraction or unmapped units should be reviewed before use.",
        ]
    )
    return "\n".join(lines)


def _sparkline_svg(points: list[tuple[str, float]], width: int = 160, height: int = 38) -> str:
    if not points:
        return ""
    values = [v for _, v in points]
    if len(values) == 1:
        return f'<svg viewBox="0 0 {width} {height}" class="spark"><circle cx="{width/2}" cy="{height/2}" r="3" /></svg>'
    min_v, max_v = min(values), max(values)
    span = max(max_v - min_v, 1e-9)
    step = width / (len(values) - 1)
    coords = []
    for i, value in enumerate(values):
        x = i * step
        y = height - ((value - min_v) / span * (height - 8)) - 4
        coords.append(f"{x:.1f},{y:.1f}")
    return f'<svg viewBox="0 0 {width} {height}" class="spark"><polyline points="{" ".join(coords)}" /></svg>'


def _priority_class(priority: str) -> str:
    return priority.replace(" ", "-")


def _qualitative_html_rows(qualitative_rows: list[dict]) -> str:
    rows = []
    for r in qualitative_rows:
        is_abnormal = r["interpretation"] == "qualitative_abnormal"
        pill_class = "review-first" if is_abnormal else "routine"
        pill_text = "review" if is_abnormal else "routine"
        rows.append(
            "<tr>"
            f'<td><span class="pill {pill_class}">{pill_text}</span></td>'
            f"<td><strong>{escape(r['canonical_test_name'] or r['test_name_raw'])}</strong><br>"
            f"<span class='sub'>{escape(r['panel'])}</span></td>"
            f"<td class='num'>{escape(str(r['qualitative_value']))}<br><span class='sub'>{escape(str(r['collection_date']))}</span></td>"
            "</tr>"
        )
    return "".join(rows)


def generate_html_report(summaries: list[BaselineSummary], qualitative_rows: list[dict] | None = None) -> str:
    qualitative_rows = qualitative_rows or []
    review_first = sum(1 for s in summaries if s.review_priority == "review first")
    review = sum(1 for s in summaries if s.review_priority == "review")
    monitor = sum(1 for s in summaries if s.review_priority == "monitor trend")
    abnormal = sum(1 for s in summaries if s.latest_interpretation in {"low", "high"})
    abnormal_qualitative = sum(1 for r in qualitative_rows if r["interpretation"] == "qualitative_abnormal")

    rows = []
    for s in summaries:
        unit = f" {escape(s.latest_unit)}" if s.latest_unit else ""
        rows.append(
            "<tr>"
            f'<td><span class="pill {_priority_class(s.review_priority)}">{escape(s.review_priority)}</span></td>'
            f"<td><strong>{escape(s.test_name)}</strong><br><span class='sub'>{escape(s.personal_baseline_flag)}</span></td>"
            f"<td class='num'>{_fmt(s.latest_value)}{unit}<br><span class='sub'>{escape(s.latest_date)}</span></td>"
            f"<td class='num'>{escape(_fmt_lab_range(s))}<br><span class='flag {escape(s.latest_interpretation)}'>{escape(s.latest_interpretation)}</span></td>"
            f"<td class='num'>{_fmt(s.median_value)}{unit}<br><span class='sub'>mean {_fmt(s.mean_value)}{unit}</span></td>"
            f"<td class='num'>{_fmt(s.iqr_low)}–{_fmt(s.iqr_high)}{unit}<br><span class='sub'>min/max {_fmt(s.minimum_value)}–{_fmt(s.maximum_value)}</span></td>"
            f"<td class='num'>{_fmt_percent(s.percent_from_median)}<br><span class='sub'>z {_fmt(s.z_score)}</span></td>"
            f"<td>{_direction_symbol(s.trend)} {escape(s.trend)}<br><span class='sub'>n={s.observations}; abnormal {s.abnormal_count}</span></td>"
            f"<td>{_sparkline_svg(s.sparkline_points)}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LabLens Physician Summary</title>
  <style>
    :root {{ --ink:#162033; --muted:#5d667a; --line:#d9dee8; --bg:#f6f8fb; --card:#ffffff; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 28px; font-family: Inter, Segoe UI, Roboto, Arial, sans-serif; color: var(--ink); background: var(--bg); }}
    .page {{ max-width: 1180px; margin: 0 auto; }}
    header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:18px; }}
    h1 {{ margin:0 0 6px; font-size:32px; letter-spacing:-0.03em; }}
    .subtitle {{ color:var(--muted); max-width:760px; line-height:1.45; }}
    .notice {{ border:1px solid var(--line); background:#fff8e8; padding:10px 12px; border-radius:12px; color:#6b4e00; font-size:13px; max-width:300px; }}
    .cards {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin:18px 0; }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:16px; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
    .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .big {{ font-size:28px; font-weight:750; margin-top:4px; }}
    .section {{ background:var(--card); border:1px solid var(--line); border-radius:18px; padding:18px; margin-top:14px; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th {{ text-align:left; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; border-bottom:1px solid var(--line); padding:10px 8px; }}
    td {{ border-bottom:1px solid #edf0f5; padding:10px 8px; vertical-align:middle; }}
    tr:last-child td {{ border-bottom:none; }}
    .num {{ text-align:right; font-variant-numeric: tabular-nums; white-space:nowrap; }}
    .sub {{ color:var(--muted); font-size:11px; }}
    .pill {{ display:inline-block; border-radius:999px; padding:4px 8px; font-size:11px; font-weight:700; white-space:nowrap; }}
    .review-first {{ background:#ffe8e5; color:#9b1c13; }}
    .review {{ background:#fff1cc; color:#725000; }}
    .monitor-trend {{ background:#e8f0ff; color:#234f9a; }}
    .routine {{ background:#e8f7ee; color:#17613a; }}
    .flag.high, .flag.low {{ color:#a12116; font-weight:700; }}
    .flag.normal {{ color:#17613a; font-weight:700; }}
    .spark {{ width:160px; height:38px; overflow:visible; }}
    .spark polyline {{ fill:none; stroke:currentColor; stroke-width:2.2; stroke-linecap:round; stroke-linejoin:round; }}
    .spark circle {{ fill:currentColor; }}
    ul {{ margin:8px 0 0 20px; color:var(--muted); line-height:1.45; }}
    @media print {{ body {{ background:white; padding:0; }} .section, .card {{ box-shadow:none; }} .page {{ max-width:none; }} }}
  </style>
</head>
<body>
  <main class="page">
    <header>
      <div>
        <h1>LabLens Physician Summary</h1>
        <div class="subtitle">Synthetic longitudinal lab summary showing latest values, source lab ranges, patient-specific medians/IQRs, descriptive trend flags, and compact sparklines.</div>
      </div>
      <div class="notice"><strong>Demo only.</strong> Synthetic data. Not for diagnosis, treatment, or clinical decision support.</div>
    </header>
    <section class="cards">
      <div class="card"><div class="label">Tests summarized</div><div class="big">{len(summaries)}</div></div>
      <div class="card"><div class="label">Abnormal latest flags</div><div class="big">{abnormal}</div></div>
      <div class="card"><div class="label">Review first/review</div><div class="big">{review_first + review}</div></div>
      <div class="card"><div class="label">Monitor trend</div><div class="big">{monitor}</div></div>
    </section>
    <section class="section">
      <h2>Clinician-facing longitudinal table</h2>
      <table>
        <thead><tr><th>Priority</th><th>Test</th><th class="num">Latest</th><th class="num">Source lab range</th><th class="num">Personal baseline</th><th class="num">Observed range</th><th class="num">Δ median</th><th>Trend</th><th>History</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    {f'''<section class="section">
      <h2>Qualitative results <span class="sub">({abnormal_qualitative} flagged)</span></h2>
      <table>
        <thead><tr><th>Priority</th><th>Test</th><th class="num">Result</th></tr></thead>
        <tbody>{_qualitative_html_rows(qualitative_rows)}</tbody>
      </table>
    </section>''' if qualitative_rows else ''}
    <section class="section">
      <h2>Interpretation notes</h2>
      <ul>
        <li>LabLens preserves the performing laboratory's reference interval from the source document instead of replacing it with a universal range.</li>
        <li>Personal baseline uses median and IQR because they are less sensitive to outliers than a simple average.</li>
        <li>Priority flags are descriptive signals for review, not medical advice.</li>
        <li>Rows with ambiguous extraction, unmapped aliases, or unknown units should remain in a human review queue before use.</li>
      </ul>
    </section>
  </main>
</body>
</html>"""


def write_reports(
    summaries: list[BaselineSummary],
    output_dir: str | Path,
    qualitative_rows: list[dict] | None = None,
) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    markdown_path = output / "physician_summary.md"
    html_path = output / "physician_summary.html"
    markdown_path.write_text(generate_markdown_report(summaries, qualitative_rows), encoding="utf-8")
    html_path.write_text(generate_html_report(summaries, qualitative_rows), encoding="utf-8")
    return markdown_path, html_path
