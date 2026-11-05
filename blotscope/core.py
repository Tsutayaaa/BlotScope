"""Pure numerical calibration and peak analysis; no GUI dependencies."""
from __future__ import annotations
from .i18n import translate as _
from .presets import PRODUCT_PRESETS
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

@dataclass
class FitResult:
    slope: float
    intercept: float
    r_squared: float
    n: int
    rmse_log10: float = 0.0
    mean_relative_error: float = 0.0
    max_relative_error: float = 0.0

    def predict(self, position: float) -> float:
        return 10 ** (self.slope * position + self.intercept)


@dataclass
class TargetLane:
    name: str
    image_index: int
    start: tuple[float, float]
    end: tuple[float, float]
    signal: list[float]
    smoothed: list[float]
    sample_points: list[tuple[float, float]]
    peaks: list[int]


@dataclass
class MarkerLane:
    name: str
    image_index: int
    start: tuple[float, float]
    end: tuple[float, float]
    signal: list[float]
    smoothed: list[float]
    sample_points: list[tuple[float, float]]
    peaks: list[int]
    peak_kda: dict[int, str]
    peak_widths: dict[int, float]
    fit_result: FitResult | None = None
    cv_rows: list[dict[str, float | None]] | None = None
    preset_name: str = ""


@dataclass
class LocalEstimate:
    position_px: float
    peak_width_px: float
    position_uncertainty_px: float
    upper_marker_position_px: float
    upper_marker_kda: float
    lower_marker_position_px: float
    lower_marker_kda: float
    apparent_mw_local_kda: float
    apparent_mw_global_kda: float
    local_global_difference_percent: float
    mw_lower_kda: float
    mw_upper_kda: float
    relative_uncertainty_percent: float
    range_status: str
    confidence: str
    reported_mw: float | None
    reported_mw_text: str
    warnings: list[str]
    marker_group: str = "Marker 1"
    selection_reason: str = ""


def prepare_markers(positions: Sequence[float], molecular_weights: Sequence[float]) -> list[tuple[float, float]]:
    if len(positions) != len(molecular_weights) or len(positions) < 2:
        raise ValueError(_('至少需要两个 Marker 点。'))
    markers = sorted((float(p), float(mw)) for p, mw in zip(positions, molecular_weights))
    if any(not math.isfinite(p) or not math.isfinite(mw) or mw <= 0 for p, mw in markers):
        raise ValueError(_('Marker kDa 必须大于 0。'))
    if any(markers[i][0] == markers[i + 1][0] for i in range(len(markers) - 1)):
        raise ValueError(_('Marker 峰位置不能重复。'))
    if any(markers[i][1] <= markers[i + 1][1] for i in range(len(markers) - 1)):
        raise ValueError(_('Marker kDa 必须随迁移位置增加而递减；请检查峰与预设的对应顺序。'))
    return markers


def local_log_interpolate(markers: Sequence[tuple[float, float]], position: float) -> tuple[float, tuple[float, float], tuple[float, float], str]:
    """Piecewise interpolation in position-vs-log10(MW); endpoint pairs extrapolate."""
    ordered = sorted((float(p), float(mw)) for p, mw in markers)
    if len(ordered) < 2:
        raise ValueError(_('局部插值至少需要两个 Marker。'))
    if any(mw <= 0 for _p, mw in ordered):
        raise ValueError(_('Marker kDa 必须大于 0。'))
    x = float(position)
    if x < ordered[0][0]:
        left, right = ordered[0], ordered[1]
        status = "extrapolation_high_MW"
    elif x > ordered[-1][0]:
        left, right = ordered[-2], ordered[-1]
        status = "extrapolation_low_MW"
    else:
        left, right = ordered[0], ordered[1]
        for index in range(len(ordered) - 1):
            if ordered[index][0] <= x <= ordered[index + 1][0]:
                left, right = ordered[index], ordered[index + 1]
                break
        boundary_margin = max(2.0, (ordered[-1][0] - ordered[0][0]) * 0.015)
        status = "near_boundary" if min(x - ordered[0][0], ordered[-1][0] - x) <= boundary_margin else "interpolation"
    fraction = (x - left[0]) / (right[0] - left[0])
    log_mw = math.log10(left[1]) + fraction * (math.log10(right[1]) - math.log10(left[1]))
    return 10 ** log_mw, left, right, status


def local_cross_validation(markers: Sequence[tuple[float, float]]) -> list[dict[str, float | None]]:
    ordered = sorted((float(p), float(mw)) for p, mw in markers)
    rows: list[dict[str, float | None]] = []
    global_fit = linear_fit([p for p, _mw in ordered], [mw for _p, mw in ordered])
    for index, (position, true_mw) in enumerate(ordered):
        global_prediction = global_fit.predict(position)
        local_prediction: float | None = None
        local_error: float | None = None
        if 0 < index < len(ordered) - 1:
            local_prediction, _left, _right, _status = local_log_interpolate(
                [ordered[index - 1], ordered[index + 1]], position
            )
            local_error = abs(local_prediction - true_mw) / true_mw
        rows.append({
            "marker_position_px": position,
            "true_marker_kda": true_mw,
            "global_predicted_kda": global_prediction,
            "global_relative_error": abs(global_prediction - true_mw) / true_mw,
            "leave_one_out_local_predicted_kda": local_prediction,
            "local_relative_error": local_error,
        })
    return rows


def estimate_peak_width(values: Sequence[float], peak_index: int) -> float:
    """Estimate FWHM in pixels using a local baseline around the detected peak."""
    if not values or not (0 <= peak_index < len(values)):
        return 0.0
    radius = max(6, min(50, len(values) // 10))
    left_edge = max(0, peak_index - radius)
    right_edge = min(len(values) - 1, peak_index + radius)
    baseline = max(min(values[left_edge : peak_index + 1]), min(values[peak_index : right_edge + 1]))
    half_height = baseline + (values[peak_index] - baseline) / 2
    left = peak_index
    while left > 0 and values[left] > half_height:
        left -= 1
    right = peak_index
    while right < len(values) - 1 and values[right] > half_height:
        right += 1
    return float(max(1, right - left))


def _rounding_step(value: float, relative_uncertainty: float = 0.0) -> float:
    if value < 100:
        return 5.0
    if value < 300:
        return 10.0
    if value < 700:
        return 20.0 if relative_uncertainty >= 0.15 else 10.0
    return 50.0


def smart_reported_mw(estimate: float, lower: float, upper: float, confidence: str, range_status: str, markers: Sequence[tuple[float, float]]) -> tuple[float | None, str]:
    ordered = sorted(markers)
    if range_status == "extrapolation_high_MW":
        return None, f">{ordered[0][1]:g} kDa"
    if range_status == "extrapolation_low_MW":
        return None, f"<{ordered[-1][1]:g} kDa"
    relative = max(0.0, (upper - lower) / max(2 * estimate, 1e-12))
    step = _rounding_step(estimate, relative)
    rounded = round(estimate / step) * step
    if relative < 0.20 and confidence in {"high", "medium"}:
        return rounded, f"~{rounded:g} kDa"
    lower_step = _rounding_step(lower, relative)
    upper_step = _rounding_step(upper, relative)
    rounded_lower = max(lower_step, round(lower / lower_step) * lower_step)
    rounded_upper = max(rounded_lower + upper_step, round(upper / upper_step) * upper_step)
    return rounded, f"approximately {rounded_lower:g}–{rounded_upper:g} kDa"


def estimate_band(
    markers: Sequence[tuple[float, float]],
    global_fit: FitResult,
    position_px: float,
    peak_width_px: float = 0.0,
    marker_position_uncertainties: dict[float, float] | None = None,
) -> LocalEstimate:
    ordered = sorted((float(p), float(mw)) for p, mw in markers)
    local_mw, upper_marker, lower_marker, status = local_log_interpolate(ordered, position_px)
    global_mw = global_fit.predict(position_px)
    difference = abs(global_mw - local_mw) / local_mw
    cv_rows = local_cross_validation(ordered)
    cv_by_position = {
        float(row["marker_position_px"]): float(row["local_relative_error"])
        for row in cv_rows if row["local_relative_error"] is not None
    }
    all_cv = list(cv_by_position.values())
    fallback_cv = statistics.median(all_cv) if all_cv else 0.15
    adjacent_cv = [cv_by_position[p] for p in (upper_marker[0], lower_marker[0]) if p in cv_by_position]
    calibration_relative = statistics.fmean(adjacent_cv) if adjacent_cv else fallback_cv

    band_uncertainty = max(2.0, float(peak_width_px) / 4.0)
    marker_uncertainties = marker_position_uncertainties or {}
    adjacent_marker_uncertainty = statistics.fmean([
        marker_uncertainties.get(upper_marker[0], 2.0), marker_uncertainties.get(lower_marker[0], 2.0)
    ])
    position_uncertainty = math.sqrt(band_uncertainty ** 2 + adjacent_marker_uncertainty ** 2)
    mw_minus = local_log_interpolate(ordered, position_px - position_uncertainty)[0]
    mw_plus = local_log_interpolate(ordered, position_px + position_uncertainty)[0]
    position_log_uncertainty = max(abs(math.log10(mw_minus / local_mw)), abs(math.log10(mw_plus / local_mw)))
    calibration_log_uncertainty = math.log10(1 + max(0.0, calibration_relative))
    total_log_uncertainty = math.sqrt(calibration_log_uncertainty ** 2 + position_log_uncertainty ** 2)
    if status.startswith("extrapolation"):
        total_log_uncertainty = max(total_log_uncertainty * 1.75, math.log10(1.30))
    lower = 10 ** (math.log10(local_mw) - total_log_uncertainty)
    upper = 10 ** (math.log10(local_mw) + total_log_uncertainty)
    relative_uncertainty = (upper - lower) / (2 * local_mw)

    interval_width = abs(lower_marker[0] - upper_marker[0])
    marker_gaps = [ordered[i + 1][0] - ordered[i][0] for i in range(len(ordered) - 1)]
    median_gap = statistics.median(marker_gaps) if marker_gaps else interval_width
    score = 100.0
    score -= min(35.0, calibration_relative * 120)
    score -= min(25.0, position_log_uncertainty * 180)
    score -= min(25.0, difference * 80)
    if median_gap and interval_width > 1.5 * median_gap:
        score -= min(15.0, (interval_width / median_gap - 1.5) * 10)
    if status == "near_boundary":
        score -= 8
    if status.startswith("extrapolation"):
        score -= 55
    confidence = "high" if score >= 80 else "medium" if score >= 60 else "low" if score >= 35 else "very_low"
    if status.startswith("extrapolation"):
        confidence = "very_low"

    warnings: list[str] = []
    if difference > 0.10:
        warnings.append("Global fit differs substantially from local marker interpolation. Use local estimate with caution.")
    if calibration_relative > 0.20:
        warnings.append("Local marker cross-validation error is high in this calibration region.")
    if position_uncertainty > 5:
        warnings.append("Band peak is broad; position uncertainty is elevated.")
    if status.startswith("extrapolation"):
        warnings.append("Band is outside the calibrated Marker range; do not report a precise molecular weight.")
    reported_mw, reported_text = smart_reported_mw(local_mw, lower, upper, confidence, status, ordered)
    return LocalEstimate(
        float(position_px), float(peak_width_px), position_uncertainty,
        upper_marker[0], upper_marker[1], lower_marker[0], lower_marker[1],
        local_mw, global_mw, difference * 100, lower, upper, relative_uncertainty * 100,
        status, confidence, reported_mw, reported_text, warnings,
    )


def choose_best_marker_estimate(estimates: Sequence[LocalEstimate]) -> LocalEstimate:
    """Choose per-band calibration, preferring interpolation then lowest uncertainty."""
    if not estimates:
        raise ValueError(_('没有可用于该条带的 Marker 校准组。'))
    confidence_rank = {"high": 0, "medium": 1, "low": 2, "very_low": 3}
    status_rank = {
        "interpolation": 0,
        "near_boundary": 1,
        "extrapolation_high_MW": 3,
        "extrapolation_low_MW": 3,
    }
    chosen = min(
        estimates,
        key=lambda estimate: (
            status_rank.get(estimate.range_status, 2),
            estimate.relative_uncertainty_percent,
            confidence_rank.get(estimate.confidence, 4),
            estimate.local_global_difference_percent,
        ),
    )
    chosen.selection_reason = (
        f"Compared {len(estimates)} fitted Marker groups; selected {chosen.marker_group} "
        f"for {chosen.range_status} status and lowest combined uncertainty "
        f"({chosen.relative_uncertainty_percent:.1f}%)."
    )
    return chosen


def organize_band_rows_by_lane(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    """Convert one-row-per-band results into one-row-per-lane summary records."""
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        key = (str(row.get("lane", "")), str(row.get("channel", "")))
        grouped.setdefault(key, []).append(dict(row))
    if not grouped:
        return []
    for bands in grouped.values():
        bands.sort(key=lambda row: int(row.get("band", 0)))
    max_bands = max(len(bands) for bands in grouped.values())
    result: list[dict[str, object]] = []
    for (lane, channel), bands in grouped.items():
        summary: dict[str, object] = {
            "lane": lane,
            "channel": channel,
            "band_count": len(bands),
        }
        for index in range(max_bands):
            summary[f"band_{index + 1}"] = bands[index].get("reported_MW_text", "") if index < len(bands) else ""
        summary["band_positions_px"] = "; ".join(f"{float(band['position_px']):.1f}" for band in bands)
        summary["marker_groups_used"] = "; ".join(dict.fromkeys(str(band.get("marker_group_used", "")) for band in bands))
        counts = Counter(str(band.get("confidence", "")) for band in bands)
        summary["confidence"] = "; ".join(f"{label} ×{count}" for label, count in counts.items())
        summary["warning_count"] = sum(bool(str(band.get("warnings", "")).strip()) for band in bands)
        result.append(summary)
    return result


def smooth_signal(values: Sequence[float], radius: int = 2) -> list[float]:
    """Centered moving average without third-party dependencies."""
    radius = max(0, int(radius))
    if radius == 0:
        return list(values)
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + float(value))
    result = []
    for i in range(len(values)):
        left = max(0, i - radius)
        right = min(len(values), i + radius + 1)
        result.append((prefix[right] - prefix[left]) / (right - left))
    return result


def detect_peaks(
    values: Sequence[float],
    min_prominence: float = 0.08,
    min_distance: int = 8,
) -> list[int]:
    """Find local maxima using a robust baseline and relative prominence.

    ``min_prominence`` is expressed as a fraction of the signal's robust range.
    Closely spaced candidates are reduced to the strongest peak.
    """
    if len(values) < 3:
        return []
    low = min(values)
    high = max(values)
    dynamic_range = high - low
    if dynamic_range <= 0:
        return []
    window = max(3, int(min_distance))
    threshold = max(0.0, float(min_prominence)) * dynamic_range
    candidates: list[tuple[float, int]] = []
    for i in range(1, len(values) - 1):
        if values[i] < values[i - 1] or values[i] <= values[i + 1]:
            continue
        left_low = min(values[max(0, i - window) : i + 1])
        right_low = min(values[i : min(len(values), i + window + 1)])
        prominence = values[i] - max(left_low, right_low)
        if prominence >= threshold:
            candidates.append((values[i], i))
    selected: list[int] = []
    for _, index in sorted(candidates, reverse=True):
        if all(abs(index - old) >= min_distance for old in selected):
            selected.append(index)
    return sorted(selected)


def linear_fit(positions: Sequence[float], molecular_weights: Sequence[float]) -> FitResult:
    """Fit log10(MW) = slope * position + intercept."""
    if len(positions) != len(molecular_weights) or len(positions) < 2:
        raise ValueError(_('拟合至少需要两个具有 kDa 数值的峰。'))
    if any(not math.isfinite(float(p)) for p in positions) or any(not math.isfinite(float(mw)) or float(mw) <= 0 for mw in molecular_weights):
        raise ValueError(_('Marker kDa 必须大于 0。'))
    xs = [float(value) for value in positions]
    ys = [math.log10(float(value)) for value in molecular_weights]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        raise ValueError(_('拟合峰不能位于同一位置。'))
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    intercept = y_mean - slope * x_mean
    residual = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    total = sum((y - y_mean) ** 2 for y in ys)
    r_squared = 1.0 if total == 0 and residual == 0 else (1.0 - residual / total if total else 0.0)
    predicted_mw = [10 ** (slope * x + intercept) for x in xs]
    relative_errors = [abs(predicted - actual) / actual for predicted, actual in zip(predicted_mw, molecular_weights)]
    rmse_log10 = math.sqrt(residual / len(xs))
    return FitResult(
        slope, intercept, r_squared, len(xs), rmse_log10,
        statistics.fmean(relative_errors), max(relative_errors),
    )


BUILTIN_PRESETS: dict[str, list[float]] = {
    **{name: list(product["values"]) for name, product in PRODUCT_PRESETS.items()},
    "600–20 kDa": [600, 400, 250, 230, 130, 110, 75, 45, 20],
    "170–10 kDa": [170, 130, 100, 70, 55, 40, 35, 25, 15, 10],
}


def parse_preset_values(text: str) -> list[float]:
    normalized = text.replace("，", " ").replace(",", " ").replace(";", " ")
    try:
        values = [float(item) for item in normalized.split()]
    except ValueError as exc:
        raise ValueError(_('预设只能包含用空格或逗号分隔的数字。')) from exc
    if not values or any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError(_('预设至少需要一个大于 0 的 kDa 数值。'))
    if any(values[i] <= values[i + 1] for i in range(len(values) - 1)):
        raise ValueError(_('请按从高分子到低分子的顺序输入预设。'))
    return values


