from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import sqrt
from statistics import mean, median
from typing import Iterable, Mapping, Any


@dataclass
class BaselineSummary:
    """Longitudinal summary for one canonical lab test.

    The statistics are descriptive only. LabLens does not diagnose or recommend
    treatment; it highlights patterns that may deserve human review.
    """

    test_name: str
    latest_value: float
    latest_date: str
    latest_interpretation: str
    latest_ref_low: float | None
    latest_ref_high: float | None
    latest_ref_comparator: str | None
    latest_unit: str | None
    median_value: float
    mean_value: float
    minimum_value: float
    maximum_value: float
    iqr_low: float
    iqr_high: float
    observations: int
    abnormal_count: int
    abnormal_rate: float
    trend: str
    personal_baseline_flag: str
    percent_from_median: float | None
    z_score: float | None
    review_priority: str
    sparkline_points: list[tuple[str, float]]


def percentile(values: list[float], p: float) -> float:
    if not values:
        raise ValueError("values cannot be empty")
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    weight = k - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def sample_standard_deviation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    avg = mean(values)
    return sqrt(sum((v - avg) ** 2 for v in values) / (len(values) - 1))


def _trend_for_ordered_values(values: list[float]) -> str:
    if len(values) < 3:
        return "insufficient data"
    midpoint = len(values) // 2
    first_half = values[:midpoint]
    second_half = values[midpoint:]
    first_median = median(first_half)
    second_median = median(second_half)
    delta = second_median - first_median
    threshold = 0.10 * max(abs(first_median), 1.0)
    if delta > threshold:
        return "rising"
    if delta < -threshold:
        return "falling"
    return "stable"


MIN_OBSERVATIONS_FOR_BASELINE = 3


def _personal_baseline_flag(latest: float, q1: float, q3: float, observations: int) -> str:
    """Flag latest value against the patient's observed IQR.

    IQR is deliberately conservative and robust for small synthetic datasets. With fewer than
    `MIN_OBSERVATIONS_FOR_BASELINE` observations there isn't really a "baseline" yet -- with only
    one or two draws, q1 == q3 == the only value(s) seen, which would otherwise silently report
    "at personal baseline" for a number that hasn't actually been observed long enough to call a
    baseline. Saying so explicitly is more honest than a precise-looking but meaningless flag.
    """
    if observations < MIN_OBSERVATIONS_FOR_BASELINE:
        return "insufficient history"
    iqr = q3 - q1
    if iqr == 0:
        return "at personal baseline"
    lower_outer = q1 - 1.5 * iqr
    upper_outer = q3 + 1.5 * iqr
    if latest < lower_outer:
        return "well below personal baseline"
    if latest > upper_outer:
        return "well above personal baseline"
    if latest < q1:
        return "below personal baseline"
    if latest > q3:
        return "above personal baseline"
    return "within observed personal range"


def _review_priority(latest_interpretation: str, baseline_flag: str, trend: str, abnormal_rate: float) -> str:
    concerning_baseline = "well" in baseline_flag
    abnormal_now = latest_interpretation in {"low", "high"}
    persistent_abnormal = abnormal_rate >= 0.50
    directional_change = trend in {"rising", "falling"}

    if abnormal_now and (concerning_baseline or persistent_abnormal or directional_change):
        return "review first"
    if abnormal_now or concerning_baseline or (persistent_abnormal and directional_change):
        return "review"
    neutral_baseline = {"within observed personal range", "at personal baseline", "insufficient history"}
    if directional_change or baseline_flag not in neutral_baseline:
        return "monitor trend"
    return "routine"


def _safe_float(row: Mapping[str, Any], key: str) -> float | None:
    value = row[key]
    return None if value is None else float(value)


def compute_baselines(rows: Iterable[Mapping[str, Any]]) -> list[BaselineSummary]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["canonical_test_name"]].append(row)

    summaries: list[BaselineSummary] = []
    for test_name, test_rows in grouped.items():
        ordered_rows = sorted(test_rows, key=lambda r: r["collection_date"])
        values = [float(r["numeric_value"]) for r in ordered_rows]
        latest = ordered_rows[-1]
        latest_value = float(latest["numeric_value"])
        q1 = percentile(values, 0.25)
        q3 = percentile(values, 0.75)
        median_value = median(values)
        mean_value = mean(values)
        stdev = sample_standard_deviation(values)
        percent_from_median = None if median_value == 0 else ((latest_value - median_value) / abs(median_value)) * 100
        z_score = None if not stdev or stdev == 0 else (latest_value - mean_value) / stdev
        abnormal_count = sum(1 for r in ordered_rows if r["interpretation"] in {"low", "high"})
        abnormal_rate = abnormal_count / len(ordered_rows)
        trend = _trend_for_ordered_values(values)
        baseline_flag = _personal_baseline_flag(latest_value, q1, q3, len(values))
        review_priority = _review_priority(str(latest["interpretation"]), baseline_flag, trend, abnormal_rate)

        summaries.append(
            BaselineSummary(
                test_name=test_name,
                latest_value=latest_value,
                latest_date=str(latest["collection_date"]),
                latest_interpretation=str(latest["interpretation"]),
                latest_ref_low=_safe_float(latest, "ref_low"),
                latest_ref_high=_safe_float(latest, "ref_high"),
                latest_ref_comparator=latest["ref_comparator"],
                latest_unit=latest["unit_raw"],
                median_value=median_value,
                mean_value=mean_value,
                minimum_value=min(values),
                maximum_value=max(values),
                iqr_low=q1,
                iqr_high=q3,
                observations=len(values),
                abnormal_count=abnormal_count,
                abnormal_rate=abnormal_rate,
                trend=trend,
                personal_baseline_flag=baseline_flag,
                percent_from_median=percent_from_median,
                z_score=z_score,
                review_priority=review_priority,
                sparkline_points=[(str(r["collection_date"]), float(r["numeric_value"])) for r in ordered_rows],
            )
        )

    priority_order = {"review first": 0, "review": 1, "monitor trend": 2, "routine": 3}
    return sorted(summaries, key=lambda s: (priority_order.get(s.review_priority, 9), s.test_name))
