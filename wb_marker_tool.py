#!/usr/bin/env python3
"""Western blot marker lane peak detection and apparent MW estimation."""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
import tkinter as tk
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Iterable, Sequence

try:
    from PIL import Image, ImageTk
except ImportError:  # Core fitting/peak functions remain testable without Pillow.
    Image = None  # type: ignore[assignment]
    ImageTk = None  # type: ignore[assignment]


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
        raise ValueError("至少需要两个 Marker 点。")
    markers = sorted((float(p), float(mw)) for p, mw in zip(positions, molecular_weights))
    if any(mw <= 0 for _p, mw in markers):
        raise ValueError("Marker kDa 必须大于 0。")
    if any(markers[i][0] == markers[i + 1][0] for i in range(len(markers) - 1)):
        raise ValueError("Marker 峰位置不能重复。")
    if any(markers[i][1] <= markers[i + 1][1] for i in range(len(markers) - 1)):
        raise ValueError("Marker kDa 必须随迁移位置增加而递减；请检查峰与预设的对应顺序。")
    return markers


def local_log_interpolate(markers: Sequence[tuple[float, float]], position: float) -> tuple[float, tuple[float, float], tuple[float, float], str]:
    """Piecewise interpolation in position-vs-log10(MW); endpoint pairs extrapolate."""
    ordered = sorted((float(p), float(mw)) for p, mw in markers)
    if len(ordered) < 2:
        raise ValueError("局部插值至少需要两个 Marker。")
    if any(mw <= 0 for _p, mw in ordered):
        raise ValueError("Marker kDa 必须大于 0。")
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
        raise ValueError("没有可用于该条带的 Marker 校准组。")
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
        raise ValueError("拟合至少需要两个具有 kDa 数值的峰。")
    if any(mw <= 0 for mw in molecular_weights):
        raise ValueError("Marker kDa 必须大于 0。")
    xs = [float(value) for value in positions]
    ys = [math.log10(float(value)) for value in molecular_weights]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        raise ValueError("拟合峰不能位于同一位置。")
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
    "预设1（600–20 kDa）": [600, 400, 250, 230, 130, 110, 75, 45, 20],
    "预设2（170–10 kDa）": [170, 130, 100, 70, 55, 40, 35, 25, 15, 10],
}


def parse_preset_values(text: str) -> list[float]:
    normalized = text.replace("，", " ").replace(",", " ").replace(";", " ")
    try:
        values = [float(item) for item in normalized.split()]
    except ValueError as exc:
        raise ValueError("预设只能包含用空格或逗号分隔的数字。") from exc
    if not values or any(value <= 0 for value in values):
        raise ValueError("预设至少需要一个大于 0 的 kDa 数值。")
    if any(values[i] <= values[i + 1] for i in range(len(values) - 1)):
        raise ValueError("请按从高分子到低分子的顺序输入预设。")
    return values


def sample_line_intensity(
    image: Image.Image,
    start: tuple[float, float],
    end: tuple[float, float],
    half_width: int = 2,
) -> tuple[list[float], list[tuple[float, float]]]:
    """Sample inverted grayscale intensity along a line, averaging its width."""
    gray = image.convert("L")
    x0, y0 = start
    x1, y1 = end
    length = max(2, int(round(math.hypot(x1 - x0, y1 - y0))) + 1)
    dx = (x1 - x0) / (length - 1)
    dy = (y1 - y0) / (length - 1)
    norm = math.hypot(dx, dy) or 1.0
    px, py = -dy / norm, dx / norm
    values: list[float] = []
    points: list[tuple[float, float]] = []
    width = max(0, int(half_width))
    for i in range(length):
        cx, cy = x0 + i * dx, y0 + i * dy
        samples = []
        for offset in range(-width, width + 1):
            x = min(gray.width - 1, max(0, int(round(cx + offset * px))))
            y = min(gray.height - 1, max(0, int(round(cy + offset * py))))
            samples.append(gray.getpixel((x, y)))
        values.append(255.0 - statistics.fmean(samples))
        points.append((cx, cy))
    return values, points


class WBMarkerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("WB Marker 分子量估算工具")
        self.geometry("1180x760")
        self.minsize(820, 560)
        self.images: list[tuple[str, Image.Image]] = []
        self.current_image_index = -1
        self.marker_image_index = -1
        self.photo: ImageTk.PhotoImage | None = None
        self.scale = 1.0
        self.zoom_factor = 1.0
        self.zoom_text = tk.StringVar(value="适应窗口")
        self.line_start: tuple[float, float] | None = None
        self.line_end: tuple[float, float] | None = None
        self.pending_lane_start: tuple[float, float] | None = None
        self.pending_lane_end: tuple[float, float] | None = None
        self.signal: list[float] = []
        self.smoothed: list[float] = []
        self.sample_points: list[tuple[float, float]] = []
        self.peaks: list[int] = []
        self.peak_kda: dict[int, str] = {}
        self.marker_peak_widths: dict[int, float] = {}
        self.marker_lanes: list[MarkerLane] = []
        self.selected_marker_lane_index = -1
        self.fit_result: FitResult | None = None
        self.local_cv_rows: list[dict[str, float | None]] = []
        self.target_position: tk.StringVar = tk.StringVar()
        self.action_var = tk.StringVar(value="marker_line")
        self.image_var = tk.StringVar()
        self.preset_path = Path(__file__).with_name("marker_presets.json")
        self.presets = self._load_presets()
        self.preset_var = tk.StringVar(value=next(iter(self.presets)))
        self.preset_values_var = tk.StringVar()
        self.anchor_kda_var = tk.StringVar()
        self.fit_summary_var = tk.StringVar(value="Marker 尚未拟合")
        self.target_lanes: list[TargetLane] = []
        self.selected_lane_index = -1
        self.status = tk.StringVar(value="请先导入 WB 原图。")
        self._build_ui()

    @property
    def image(self) -> Image.Image | None:
        if 0 <= self.current_image_index < len(self.images):
            return self.images[self.current_image_index][1]
        return None

    @property
    def image_path(self) -> str:
        if 0 <= self.current_image_index < len(self.images):
            return self.images[self.current_image_index][0]
        return ""

    def _load_presets(self) -> dict[str, list[float]]:
        presets = {name: list(values) for name, values in BUILTIN_PRESETS.items()}
        try:
            with self.preset_path.open("r", encoding="utf-8") as handle:
                saved = json.load(handle)
            for name, values in saved.items():
                parsed = [float(value) for value in values]
                if name and parsed:
                    presets[name] = parsed
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return presets

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="1  导入多张图片", command=self.open_images).pack(side=tk.LEFT, padx=3)
        ttk.Label(toolbar, text="当前通道").pack(side=tk.LEFT, padx=(12, 3))
        self.image_combo = ttk.Combobox(toolbar, textvariable=self.image_var, state="readonly", width=24)
        self.image_combo.pack(side=tk.LEFT)
        self.image_combo.bind("<<ComboboxSelected>>", self.switch_image)
        ttk.Button(toolbar, text="清除选线", command=self.clear_line).pack(side=tk.LEFT, padx=8)
        ttk.Button(toolbar, text="保存结果", command=self.save_results).pack(side=tk.LEFT, padx=12)

        modebar = ttk.Frame(self, padding=(8, 0, 8, 7))
        modebar.pack(fill=tk.X)
        ttk.Label(modebar, text="图片操作：").pack(side=tk.LEFT)
        ttk.Radiobutton(modebar, text="画 Marker 选线", variable=self.action_var, value="marker_line").pack(side=tk.LEFT)
        ttk.Radiobutton(modebar, text="添加目标泳道", variable=self.action_var, value="target_lane").pack(side=tk.LEFT, padx=10)
        ttk.Label(modebar, textvariable=self.status).pack(side=tk.LEFT, padx=14)

        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(paned)
        right = ttk.Frame(paned, width=390)
        paned.add(left, weight=3)
        paned.add(right, weight=2)

        image_tools = ttk.Frame(left)
        image_tools.pack(fill=tk.X)
        ttk.Label(image_tools, text="在 Marker 通道画线；目标通道共享坐标。").pack(side=tk.LEFT)
        ttk.Button(image_tools, text="−", width=3, command=lambda: self.zoom_image(0.8)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(image_tools, text="+", width=3, command=lambda: self.zoom_image(1.25)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(image_tools, text="适应窗口", command=self.fit_image_to_window).pack(side=tk.RIGHT, padx=4)
        ttk.Label(image_tools, textvariable=self.zoom_text, width=10, anchor=tk.CENTER).pack(side=tk.RIGHT)

        image_frame = ttk.Frame(left)
        image_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        self.image_canvas = tk.Canvas(image_frame, background="#252525", cursor="crosshair", highlightthickness=0)
        image_vscroll = ttk.Scrollbar(image_frame, orient=tk.VERTICAL, command=self.image_canvas.yview)
        image_hscroll = ttk.Scrollbar(image_frame, orient=tk.HORIZONTAL, command=self.image_canvas.xview)
        self.image_canvas.configure(yscrollcommand=image_vscroll.set, xscrollcommand=image_hscroll.set)
        self.image_canvas.grid(row=0, column=0, sticky=tk.NSEW)
        image_vscroll.grid(row=0, column=1, sticky=tk.NS)
        image_hscroll.grid(row=1, column=0, sticky=tk.EW)
        image_frame.rowconfigure(0, weight=1)
        image_frame.columnconfigure(0, weight=1)
        self.image_canvas.bind("<ButtonPress-1>", self.start_line)
        self.image_canvas.bind("<B1-Motion>", self.drag_line)
        self.image_canvas.bind("<ButtonRelease-1>", self.finish_line)
        self.image_canvas.bind("<Configure>", lambda _e: self.render_image())
        self.image_canvas.bind("<MouseWheel>", self.scroll_image_vertical)
        self.image_canvas.bind("<Shift-MouseWheel>", self.scroll_image_horizontal)
        self.image_canvas.bind("<Command-MouseWheel>", self.zoom_image_wheel)
        self.image_canvas.bind("<Control-MouseWheel>", self.zoom_image_wheel)

        self.workflow_notebook = ttk.Notebook(right)
        self.workflow_notebook.pack(fill=tk.BOTH, expand=True)
        marker_page = ttk.Frame(self.workflow_notebook)
        target_page = ttk.Frame(self.workflow_notebook)
        self.workflow_notebook.add(marker_page, text="1  Marker 定标")
        self.workflow_notebook.add(target_page, text="2  目标泳道分析", state="disabled")
        marker_tab = self._make_scrollable_page(marker_page)
        target_tab = self._make_scrollable_page(target_page)

        style = ttk.Style(self)
        style.configure("Primary.TButton", font=("TkDefaultFont", 12, "bold"), padding=(12, 9))
        marker_action = ttk.Frame(marker_tab)
        marker_action.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(marker_action, text="确认峰与 kDa 后：", font=("TkDefaultFont", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(
            marker_action,
            text="完成 Marker 并立即拟合  →",
            command=self.finish_marker_stage,
            style="Primary.TButton",
        ).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))

        marker_groups = ttk.LabelFrame(marker_tab, text="Marker 泳道组（逐组选择并设置 kDa）", padding=5)
        marker_groups.pack(fill=tk.X, pady=(0, 8))
        self.marker_lane_tree = ttk.Treeview(
            marker_groups, columns=("group", "channel", "peaks", "fit"), show="headings", height=3
        )
        for key, title, width in (
            ("group", "Marker组", 75), ("channel", "通道", 130),
            ("peaks", "峰数", 45), ("fit", "状态", 70),
        ):
            self.marker_lane_tree.heading(key, text=title)
            self.marker_lane_tree.column(key, width=width, anchor=tk.CENTER)
        self.marker_lane_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.marker_lane_tree.bind("<<TreeviewSelect>>", self.on_marker_lane_selected)
        marker_group_buttons = ttk.Frame(marker_groups)
        marker_group_buttons.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        ttk.Button(marker_group_buttons, text="删除所选", command=self.remove_selected_marker_lane).pack(fill=tk.X)
        ttk.Label(marker_group_buttons, text="在图上继续画线\n即可添加新组", foreground="#555", justify=tk.CENTER).pack(pady=(5, 0))

        settings = ttk.LabelFrame(marker_tab, text="峰检测", padding=8)
        settings.pack(fill=tk.X)
        self.smooth_var = tk.IntVar(value=3)
        self.prominence_var = tk.DoubleVar(value=8.0)
        self.distance_var = tk.IntVar(value=12)
        self.width_var = tk.IntVar(value=2)
        for row, (label, variable) in enumerate([
            ("平滑半径 (px)", self.smooth_var),
            ("最小峰突出度 (%)", self.prominence_var),
            ("最小峰间距 (px)", self.distance_var),
            ("选线半宽 (px)", self.width_var),
        ]):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky=tk.W, pady=2)
            ttk.Spinbox(settings, textvariable=variable, width=8, from_=0, to=100).grid(row=row, column=1, pady=2)
        ttk.Button(settings, text="重新检测峰", command=self.analyze_line).grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=(7, 0))

        preset_frame = ttk.LabelFrame(marker_tab, text="Marker 预设与自动排列", padding=8)
        preset_frame.pack(fill=tk.X, pady=(8, 0))
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, values=list(self.presets), state="readonly", width=25)
        self.preset_combo.grid(row=0, column=0, columnspan=2, sticky=tk.EW)
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)
        ttk.Entry(preset_frame, textvariable=self.preset_values_var).grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=4)
        ttk.Button(preset_frame, text="另存为新预设", command=self.save_preset).grid(row=2, column=0, sticky=tk.EW, padx=(0, 3))
        ttk.Button(preset_frame, text="应用完整预设", command=self.apply_full_preset).grid(row=2, column=1, sticky=tk.EW, padx=(3, 0))
        ttk.Label(preset_frame, text="选中一个峰，指定它对应：").grid(row=3, column=0, sticky=tk.W, pady=(6, 2))
        self.anchor_combo = ttk.Combobox(preset_frame, textvariable=self.anchor_kda_var, width=10)
        self.anchor_combo.grid(row=3, column=1, sticky=tk.EW, pady=(6, 2))
        ttk.Button(preset_frame, text="从选中峰开始向下自动排列", command=self.auto_assign_from_selected).grid(row=4, column=0, columnspan=2, sticky=tk.EW)
        preset_frame.columnconfigure(0, weight=1)
        preset_frame.columnconfigure(1, weight=1)
        self.on_preset_selected()

        self.plot = tk.Canvas(marker_tab, height=170, background="white", highlightthickness=1, highlightbackground="#bbb")
        self.plot.pack(fill=tk.X, pady=8)
        self.plot.bind("<Button-1>", self.toggle_peak_from_plot)
        self.plot.bind("<Configure>", lambda _e: self.draw_plot())

        peak_frame = ttk.LabelFrame(marker_tab, text="峰位置与 Marker kDa（可留空）", padding=6)
        peak_frame.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(peak_frame, columns=("position", "kda"), show="headings", height=9)
        self.tree.heading("position", text="沿线位置 (px)")
        self.tree.heading("kda", text="Marker (kDa)")
        self.tree.column("position", width=110, anchor=tk.CENTER)
        self.tree.column("kda", width=110, anchor=tk.CENTER)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(peak_frame, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Double-1>", self.edit_kda)
        self.tree.bind("<<TreeviewSelect>>", self.on_peak_selected)
        ttk.Label(marker_tab, text="双击 kDa 单元格编辑；点击曲线可增删峰。", foreground="#555").pack(anchor=tk.W, pady=(3, 7))

        fit_frame = ttk.LabelFrame(marker_tab, text="Marker 拟合", padding=8)
        fit_frame.pack(fill=tk.X)
        ttk.Button(fit_frame, text="拟合 log10(MW)–位置", command=self.fit_curve).grid(row=0, column=0, columnspan=2, sticky=tk.EW)
        self.fit_text = tk.Text(fit_frame, height=7, width=38, state=tk.DISABLED, background="#f7f7f7")
        self.fit_text.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(4, 0))
        ttk.Label(fit_frame, text="拟合完成后，上方按钮会自动进入目标泳道分析。", foreground="#555").grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))

        self._build_target_tab(target_tab)

    def _make_scrollable_page(self, parent: ttk.Frame) -> ttk.Frame:
        """Create a vertically scrollable notebook page with responsive width."""
        canvas = tk.Canvas(parent, highlightthickness=0, background="#f0f0f0")
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        content = ttk.Frame(canvas, padding=6)
        window_id = canvas.create_window((0, 0), window=content, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        if not hasattr(self, "_scroll_pages"):
            self._scroll_pages: list[tuple[tk.Widget, tk.Canvas]] = []
            self.bind_all("<MouseWheel>", self._route_page_mousewheel, add="+")
        self._scroll_pages.append((content, canvas))
        return content

    def _route_page_mousewheel(self, event: tk.Event):
        widget = event.widget
        if widget is self.image_canvas:
            return None
        current = widget
        while current is not None:
            for content, canvas in getattr(self, "_scroll_pages", []):
                if current is content:
                    units = -1 if event.delta > 0 else 1
                    canvas.yview_scroll(units * 3, "units")
                    return "break"
            current = getattr(current, "master", None)
        return None

    def _build_target_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            textvariable=self.fit_summary_var,
            foreground="#1565c0",
            font=("TkDefaultFont", 10, "bold"),
            wraplength=390,
        ).pack(fill=tk.X, pady=(0, 6))
        ttk.Label(
            parent,
            text="切换到目标通道，选择“添加目标泳道”，从胶顶沿泳道中心拖到胶底。选线半宽决定泳道范围。",
            wraplength=390,
        ).pack(fill=tk.X, pady=(0, 6))

        target_settings = ttk.LabelFrame(parent, text="目标泳道检测参数", padding=6)
        target_settings.pack(fill=tk.X, pady=(0, 6))
        for column, (label, variable) in enumerate((
            ("平滑", self.smooth_var), ("突出度%", self.prominence_var),
            ("峰距px", self.distance_var), ("半宽px", self.width_var),
        )):
            ttk.Label(target_settings, text=label).grid(row=0, column=column, padx=2)
            ttk.Spinbox(target_settings, textvariable=variable, width=6, from_=0, to=100).grid(row=1, column=column, padx=2)

        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="重新识别所选泳道", command=self.reanalyze_selected_lane).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3))
        ttk.Button(actions, text="删除所选泳道", command=self.remove_selected_lane).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0))

        lane_frame = ttk.LabelFrame(parent, text="已添加泳道", padding=5)
        lane_frame.pack(fill=tk.X, pady=7)
        self.lane_tree = ttk.Treeview(lane_frame, columns=("channel", "lane", "bands"), show="headings", height=4)
        for key, title, width in (("channel", "通道", 125), ("lane", "泳道", 80), ("bands", "条带数", 60)):
            self.lane_tree.heading(key, text=title)
            self.lane_tree.column(key, width=width, anchor=tk.CENTER)
        self.lane_tree.pack(fill=tk.X)
        self.lane_tree.bind("<<TreeviewSelect>>", self.on_lane_selected)

        ttk.Label(parent, text="所选泳道灰度曲线（点击曲线可手动增加/删除条带峰）", foreground="#555").pack(anchor=tk.W)
        self.target_plot = tk.Canvas(parent, height=180, background="white", highlightthickness=1, highlightbackground="#bbb")
        self.target_plot.pack(fill=tk.X, pady=(3, 8))
        self.target_plot.bind("<Button-1>", self.toggle_target_peak_from_plot)
        self.target_plot.bind("<Configure>", lambda _e: self.draw_target_plot())

        result_frame = ttk.LabelFrame(parent, text="每个泳道的条带结果", padding=5)
        result_frame.pack(fill=tk.BOTH, expand=True)
        self.result_tree = ttk.Treeview(
            result_frame,
            columns=("lane", "band", "marker", "position", "local_mw", "range", "confidence", "reported", "status"),
            show="headings",
            height=10,
        )
        for key, title, width in (
            ("lane", "泳道", 70), ("band", "条带", 45), ("marker", "采用Marker", 80), ("position", "位置 px", 65),
            ("local_mw", "Local kDa", 75), ("range", "不确定范围 kDa", 115),
            ("confidence", "可信度", 65), ("reported", "建议报告", 125), ("status", "范围状态", 110),
        ):
            self.result_tree.heading(key, text=title)
            self.result_tree.column(key, width=width, anchor=tk.CENTER)
        self.result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        result_scroll = ttk.Scrollbar(result_frame, command=self.result_tree.yview)
        result_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_tree.configure(yscrollcommand=result_scroll.set)
        result_hscroll = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self.result_tree.xview)
        result_hscroll.pack(fill=tk.X)
        self.result_tree.configure(xscrollcommand=result_hscroll.set)

    def finish_marker_stage(self) -> None:
        fitted_count = self.fit_all_marker_lanes()
        if fitted_count == 0:
            return
        self.workflow_notebook.tab(1, state="normal")
        self.workflow_notebook.select(1)
        self.action_var.set("target_lane")
        self.status.set(f"已完成 {fitted_count} 组 Marker 拟合；目标条带将自动选择不确定度最低的校准组。")

    def open_images(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=[("图片", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"), ("所有文件", "*")])
        if not paths:
            return
        loaded: list[tuple[str, Image.Image]] = []
        errors = []
        for path in paths:
            try:
                with Image.open(path) as opened:
                    loaded.append((path, opened.convert("RGB")))
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")
        if not loaded:
            messagebox.showerror("无法打开图片", "\n".join(errors))
            return
        self.images = loaded
        self.current_image_index = 0
        self.zoom_factor = 1.0
        labels = [f"{i + 1}. {os.path.basename(path)}" for i, (path, _image) in enumerate(self.images)]
        self.image_combo.configure(values=labels)
        self.image_var.set(labels[0])
        self.clear_line()
        sizes = {(image.width, image.height) for _path, image in self.images}
        size_note = "" if len(sizes) == 1 else "；注意：图片尺寸不同，请确认坐标已经对齐"
        self.status.set(f"已导入 {len(loaded)} 个通道{size_note}")
        if errors:
            messagebox.showwarning("部分图片未导入", "\n".join(errors))
        self.render_image()

    def switch_image(self, _event=None) -> None:
        selection = self.image_combo.current()
        if selection < 0:
            return
        self.current_image_index = selection
        self.render_image()
        self.status.set(f"当前通道：{os.path.basename(self.image_path)}")

    def render_image(self) -> None:
        if not self.image:
            return
        width = max(1, self.image_canvas.winfo_width())
        height = max(1, self.image_canvas.winfo_height())
        fit_scale = min(width / self.image.width, height / self.image.height, 1.0)
        self.scale = max(0.02, fit_scale * self.zoom_factor)
        shown = self.image.resize((max(1, round(self.image.width * self.scale)), max(1, round(self.image.height * self.scale))))
        self.photo = ImageTk.PhotoImage(shown)
        self.image_canvas.delete("all")
        self.image_canvas.create_image(0, 0, image=self.photo, anchor=tk.NW, tags="image")
        self.image_canvas.configure(scrollregion=(0, 0, shown.width, shown.height))
        self.zoom_text.set(f"{self.scale * 100:.0f}%")
        if self.line_start and self.line_end:
            x0, y0 = self._to_canvas(self.line_start)
            x1, y1 = self._to_canvas(self.line_end)
            self.image_canvas.create_line(x0, y0, x1, y1, fill="#00e5ff", width=3, tags="selection")
            self._draw_peak_marks()
            self._draw_target_mark()
        self._draw_other_marker_lanes()
        self._draw_target_lanes()
        if self.pending_lane_start and self.pending_lane_end:
            x0, y0 = self._to_canvas(self.pending_lane_start)
            x1, y1 = self._to_canvas(self.pending_lane_end)
            self.image_canvas.create_line(x0, y0, x1, y1, fill="#ff9800", width=max(3, self.width_var.get() * 2), tags="selection")

    def _to_image(self, x: float, y: float) -> tuple[float, float]:
        assert self.image
        canvas_x = self.image_canvas.canvasx(x)
        canvas_y = self.image_canvas.canvasy(y)
        return (
            min(self.image.width - 1, max(0, canvas_x / self.scale)),
            min(self.image.height - 1, max(0, canvas_y / self.scale)),
        )

    def _to_canvas(self, point: tuple[float, float]) -> tuple[float, float]:
        return point[0] * self.scale, point[1] * self.scale

    def fit_image_to_window(self) -> None:
        self.zoom_factor = 1.0
        self.image_canvas.xview_moveto(0)
        self.image_canvas.yview_moveto(0)
        self.render_image()

    def zoom_image(self, multiplier: float) -> None:
        if not self.image:
            return
        xview = self.image_canvas.xview()
        yview = self.image_canvas.yview()
        center_x = (xview[0] + xview[1]) / 2 if xview else 0.5
        center_y = (yview[0] + yview[1]) / 2 if yview else 0.5
        self.zoom_factor = min(12.0, max(0.25, self.zoom_factor * multiplier))
        self.render_image()
        self.update_idletasks()
        visible_x = self.image_canvas.xview()[1] - self.image_canvas.xview()[0]
        visible_y = self.image_canvas.yview()[1] - self.image_canvas.yview()[0]
        self.image_canvas.xview_moveto(max(0.0, center_x - visible_x / 2))
        self.image_canvas.yview_moveto(max(0.0, center_y - visible_y / 2))

    def zoom_image_wheel(self, event: tk.Event):
        self.zoom_image(1.15 if event.delta > 0 else 1 / 1.15)
        return "break"

    def scroll_image_vertical(self, event: tk.Event):
        self.image_canvas.yview_scroll((-1 if event.delta > 0 else 1) * 3, "units")
        return "break"

    def scroll_image_horizontal(self, event: tk.Event):
        self.image_canvas.xview_scroll((-1 if event.delta > 0 else 1) * 3, "units")
        return "break"

    def start_line(self, event: tk.Event) -> None:
        if not self.image:
            return
        if self.action_var.get() == "target_lane":
            if not self.fit_result:
                messagebox.showinfo("请先完成 Marker 拟合", "Marker 拟合完成后才能添加目标泳道。")
                return
            self.pending_lane_start = self._to_image(event.x, event.y)
            self.pending_lane_end = self.pending_lane_start
            self.render_image()
            return
        self.line_start = self._to_image(event.x, event.y)
        self.line_end = self.line_start
        self.marker_image_index = self.current_image_index
        self.render_image()

    def drag_line(self, event: tk.Event) -> None:
        if self.action_var.get() == "target_lane" and self.image and self.pending_lane_start:
            self.pending_lane_end = self._to_image(event.x, event.y)
            self.render_image()
        elif self.action_var.get() == "marker_line" and self.image and self.line_start:
            self.line_end = self._to_image(event.x, event.y)
            self.render_image()

    def finish_line(self, event: tk.Event) -> None:
        if self.action_var.get() == "target_lane" and self.image and self.pending_lane_start:
            self.pending_lane_end = self._to_image(event.x, event.y)
            self.add_target_lane(self.pending_lane_start, self.pending_lane_end)
            self.pending_lane_start = self.pending_lane_end = None
            self.render_image()
        elif self.action_var.get() == "marker_line" and self.image and self.line_start:
            self.line_end = self._to_image(event.x, event.y)
            self.add_marker_lane(self.line_start, self.line_end)

    def clear_line(self) -> None:
        self.line_start = self.line_end = None
        self.marker_image_index = -1
        self.pending_lane_start = self.pending_lane_end = None
        self.signal = []
        self.smoothed = []
        self.sample_points = []
        self.peaks = []
        self.peak_kda = {}
        self.marker_peak_widths = {}
        self.marker_lanes = []
        self.selected_marker_lane_index = -1
        self.fit_result = None
        self.local_cv_rows = []
        self.target_position.set("")
        self.target_lanes = []
        self.selected_lane_index = -1
        self.refresh_tree()
        if hasattr(self, "marker_lane_tree"):
            self.refresh_marker_lane_tree()
        if hasattr(self, "lane_tree"):
            self.refresh_target_views()
        self.draw_plot()
        self.render_image()

    def select_target_on_image(self, event: tk.Event) -> None:
        if not (self.image and self.line_start and self.line_end):
            messagebox.showinfo("请先画 Marker 线", "先在任一 Marker 通道沿迁移方向画线，再切换目标通道点击条带。")
            return
        x, y = self._to_image(event.x, event.y)
        x0, y0 = self.line_start
        x1, y1 = self.line_end
        dx, dy = x1 - x0, y1 - y0
        squared_length = dx * dx + dy * dy
        if squared_length <= 0:
            return
        fraction = ((x - x0) * dx + (y - y0) * dy) / squared_length
        fraction = min(1.0, max(0.0, fraction))
        position = fraction * math.sqrt(squared_length)
        self.target_position.set(f"{position:.1f}")
        self.render_image()
        self.status.set(f"已从 {os.path.basename(self.image_path)} 选择目标条带：{position:.1f} px")

    def _draw_target_mark(self) -> None:
        try:
            position = float(self.target_position.get())
        except ValueError:
            return
        if not self.line_start or not self.line_end:
            return
        x0, y0 = self.line_start
        x1, y1 = self.line_end
        length = math.hypot(x1 - x0, y1 - y0)
        if length <= 0:
            return
        fraction = min(1.0, max(0.0, position / length))
        x = (x0 + fraction * (x1 - x0)) * self.scale
        y = (y0 + fraction * (y1 - y0)) * self.scale
        dx, dy = (x1 - x0) / length, (y1 - y0) / length
        px, py = -dy * 14, dx * 14
        self.image_canvas.create_line(x - px, y - py, x + px, y + py, fill="#ffea00", width=3, tags="selection")
        self.image_canvas.create_text(x + px + 5, y + py, text="目标", fill="#ffea00", anchor=tk.W, tags="selection")

    def _draw_target_lanes(self) -> None:
        for index, lane in enumerate(self.target_lanes):
            if lane.image_index != self.current_image_index:
                continue
            x0, y0 = self._to_canvas(lane.start)
            x1, y1 = self._to_canvas(lane.end)
            color = "#ffea00" if index == self.selected_lane_index else "#76ff03"
            self.image_canvas.create_line(
                x0, y0, x1, y1, fill=color,
                width=max(3, round((self.width_var.get() * 2 + 1) * self.scale)),
                tags="selection",
            )
            self.image_canvas.create_text(x0 + 6, y0, text=lane.name, fill=color, anchor=tk.W, tags="selection")
            for peak in lane.peaks:
                if peak >= len(lane.sample_points):
                    continue
                x, y = self._to_canvas(lane.sample_points[peak])
                self.image_canvas.create_oval(x - 4, y - 4, x + 4, y + 4, outline="#ff1744", width=2, tags="selection")

    def _draw_other_marker_lanes(self) -> None:
        for index, lane in enumerate(self.marker_lanes):
            if index == self.selected_marker_lane_index or lane.image_index != self.current_image_index:
                continue
            x0, y0 = self._to_canvas(lane.start)
            x1, y1 = self._to_canvas(lane.end)
            self.image_canvas.create_line(x0, y0, x1, y1, fill="#ab47bc", width=2, dash=(5, 3), tags="selection")
            self.image_canvas.create_text(x0 + 6, y0, text=lane.name, fill="#e1bee7", anchor=tk.W, tags="selection")

    def add_target_lane(self, start: tuple[float, float], end: tuple[float, float]) -> None:
        if not self.image or math.hypot(end[0] - start[0], end[1] - start[1]) < 5:
            messagebox.showinfo("泳道范围太短", "请从泳道顶部沿中心拖到泳道底部。")
            return
        signal, points = sample_line_intensity(self.image, start, end, self.width_var.get())
        smoothed = smooth_signal(signal, self.smooth_var.get())
        peaks = detect_peaks(smoothed, self.prominence_var.get() / 100.0, max(1, self.distance_var.get()))
        lane = TargetLane(
            name=f"Lane {len(self.target_lanes) + 1}",
            image_index=self.current_image_index,
            start=start,
            end=end,
            signal=signal,
            smoothed=smoothed,
            sample_points=points,
            peaks=peaks,
        )
        self.target_lanes.append(lane)
        self.selected_lane_index = len(self.target_lanes) - 1
        self.refresh_target_views()
        self.status.set(f"已添加 {lane.name}，自动识别到 {len(peaks)} 条目标条带。")

    def project_marker_position(self, point: tuple[float, float], marker_lane: MarkerLane | None = None) -> float:
        start = marker_lane.start if marker_lane else self.line_start
        end = marker_lane.end if marker_lane else self.line_end
        if not start or not end:
            return 0.0
        x0, y0 = start
        dx = end[0] - x0
        dy = end[1] - y0
        length = math.hypot(dx, dy)
        if length <= 0:
            return 0.0
        return ((point[0] - x0) * dx + (point[1] - y0) * dy) / length

    def marker_calibration(self, marker_lane: MarkerLane | None = None) -> list[tuple[float, float]]:
        peaks = marker_lane.peaks if marker_lane else self.peaks
        peak_kda = marker_lane.peak_kda if marker_lane else self.peak_kda
        return prepare_markers(
            [p for p in peaks if peak_kda.get(p, "").strip()],
            [float(peak_kda[p]) for p in peaks if peak_kda.get(p, "").strip()],
        )

    def marker_position_uncertainties(self, marker_lane: MarkerLane | None = None) -> dict[float, float]:
        peaks = marker_lane.peaks if marker_lane else self.peaks
        peak_kda = marker_lane.peak_kda if marker_lane else self.peak_kda
        widths = marker_lane.peak_widths if marker_lane else self.marker_peak_widths
        return {
            float(p): max(2.0, widths.get(p, 0.0) / 4.0)
            for p in peaks if peak_kda.get(p, "").strip()
        }

    def estimate_lane_peak(self, lane: TargetLane, peak: int) -> LocalEstimate:
        fitted_marker_lanes = [marker for marker in self.marker_lanes if marker.fit_result]
        if not fitted_marker_lanes and not self.fit_result:
            raise ValueError("Marker 尚未拟合。")
        width = estimate_peak_width(lane.smoothed, peak)
        point = lane.sample_points[peak]
        if not fitted_marker_lanes:
            return estimate_band(
                self.marker_calibration(), self.fit_result, self.project_marker_position(point), width,
                self.marker_position_uncertainties(),
            )
        candidates: list[LocalEstimate] = []
        for marker in fitted_marker_lanes:
            position = self.project_marker_position(point, marker)
            estimate = estimate_band(
                self.marker_calibration(marker), marker.fit_result, position, width,
                self.marker_position_uncertainties(marker),
            )
            estimate.marker_group = marker.name
            candidates.append(estimate)
        return choose_best_marker_estimate(candidates)

    def refresh_target_views(self) -> None:
        if not hasattr(self, "lane_tree"):
            return
        self.lane_tree.delete(*self.lane_tree.get_children())
        for index, lane in enumerate(self.target_lanes):
            channel = os.path.basename(self.images[lane.image_index][0]) if lane.image_index < len(self.images) else ""
            self.lane_tree.insert("", tk.END, iid=str(index), values=(channel, lane.name, len(lane.peaks)))
        if 0 <= self.selected_lane_index < len(self.target_lanes):
            self.lane_tree.selection_set(str(self.selected_lane_index))
        self.result_tree.delete(*self.result_tree.get_children())
        for lane in self.target_lanes:
            for band_number, peak in enumerate(lane.peaks, start=1):
                try:
                    estimate = self.estimate_lane_peak(lane, peak)
                except ValueError:
                    continue
                self.result_tree.insert(
                    "", tk.END,
                    values=(
                        lane.name, band_number, estimate.marker_group, f"{estimate.position_px:.1f}",
                        f"{estimate.apparent_mw_local_kda:.1f}",
                        f"{estimate.mw_lower_kda:.0f}–{estimate.mw_upper_kda:.0f}",
                        estimate.confidence, estimate.reported_mw_text, estimate.range_status,
                    ),
                )
        self.draw_target_plot()
        self.render_image()

    def on_lane_selected(self, _event=None) -> None:
        selection = self.lane_tree.selection()
        if not selection:
            return
        self.selected_lane_index = int(selection[0])
        lane = self.target_lanes[self.selected_lane_index]
        if lane.image_index != self.current_image_index:
            self.current_image_index = lane.image_index
            self.image_combo.current(lane.image_index)
            self.image_var.set(self.image_combo.get())
        self.draw_target_plot()
        self.render_image()

    def draw_target_plot(self) -> None:
        if not hasattr(self, "target_plot"):
            return
        self.target_plot.delete("all")
        if not (0 <= self.selected_lane_index < len(self.target_lanes)):
            self.target_plot.create_text(12, 12, text="添加并选择泳道后显示灰度曲线", anchor=tk.NW, fill="#777")
            return
        lane = self.target_lanes[self.selected_lane_index]
        values = lane.smoothed
        w, h = max(10, self.target_plot.winfo_width()), max(10, self.target_plot.winfo_height())
        margin = 24
        low, high = min(values), max(values)
        span = high - low or 1.0
        coords = []
        for i, value in enumerate(values):
            x = margin + i / max(1, len(values) - 1) * (w - 2 * margin)
            y = h - margin - (value - low) / span * (h - 2 * margin)
            coords.extend((x, y))
        if len(coords) >= 4:
            self.target_plot.create_line(*coords, fill="#00897b", width=2)
        for peak in lane.peaks:
            x = margin + peak / max(1, len(values) - 1) * (w - 2 * margin)
            y = h - margin - (values[peak] - low) / span * (h - 2 * margin)
            self.target_plot.create_line(x, h - margin, x, y, fill="#d32f2f", dash=(3, 2))
            self.target_plot.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#d32f2f", outline="")
        self.target_plot.create_text(margin, h - 4, text="泳道起点", anchor=tk.SW, fill="#555")
        self.target_plot.create_text(w - margin, h - 4, text="泳道终点", anchor=tk.SE, fill="#555")

    def toggle_target_peak_from_plot(self, event: tk.Event) -> None:
        if not (0 <= self.selected_lane_index < len(self.target_lanes)):
            return
        lane = self.target_lanes[self.selected_lane_index]
        margin = 24
        usable = max(1, self.target_plot.winfo_width() - 2 * margin)
        index = round((event.x - margin) / usable * (len(lane.smoothed) - 1))
        index = min(len(lane.smoothed) - 1, max(0, index))
        tolerance = max(4, round(len(lane.smoothed) * 0.012))
        nearest = min(lane.peaks, key=lambda p: abs(p - index), default=None)
        if nearest is not None and abs(nearest - index) <= tolerance:
            lane.peaks.remove(nearest)
        else:
            left, right = max(0, index - tolerance), min(len(lane.smoothed), index + tolerance + 1)
            peak = left + max(range(right - left), key=lambda j: lane.smoothed[left + j])
            if peak not in lane.peaks:
                lane.peaks.append(peak)
                lane.peaks.sort()
        self.refresh_target_views()

    def reanalyze_selected_lane(self) -> None:
        if not (0 <= self.selected_lane_index < len(self.target_lanes)):
            messagebox.showinfo("请选择泳道", "请先选择一个泳道。")
            return
        lane = self.target_lanes[self.selected_lane_index]
        image = self.images[lane.image_index][1]
        lane.signal, lane.sample_points = sample_line_intensity(image, lane.start, lane.end, self.width_var.get())
        lane.smoothed = smooth_signal(lane.signal, self.smooth_var.get())
        lane.peaks = detect_peaks(lane.smoothed, self.prominence_var.get() / 100.0, max(1, self.distance_var.get()))
        self.refresh_target_views()
        self.status.set(f"{lane.name} 已重新识别：{len(lane.peaks)} 个条带。")

    def remove_selected_lane(self) -> None:
        if not (0 <= self.selected_lane_index < len(self.target_lanes)):
            return
        removed = self.target_lanes.pop(self.selected_lane_index)
        for index, lane in enumerate(self.target_lanes, start=1):
            lane.name = f"Lane {index}"
        self.selected_lane_index = min(self.selected_lane_index, len(self.target_lanes) - 1)
        self.refresh_target_views()
        self.status.set(f"已删除 {removed.name}。")

    def add_marker_lane(self, start: tuple[float, float], end: tuple[float, float]) -> None:
        if not self.image or math.hypot(end[0] - start[0], end[1] - start[1]) < 5:
            messagebox.showinfo("Marker 泳道太短", "请从 Marker 泳道顶部沿中心拖到泳道底部。")
            return
        signal, points = sample_line_intensity(self.image, start, end, self.width_var.get())
        smoothed = smooth_signal(signal, self.smooth_var.get())
        peaks = detect_peaks(smoothed, self.prominence_var.get() / 100.0, max(1, self.distance_var.get()))
        lane = MarkerLane(
            name=f"Marker {len(self.marker_lanes) + 1}",
            image_index=self.current_image_index,
            start=start,
            end=end,
            signal=signal,
            smoothed=smoothed,
            sample_points=points,
            peaks=peaks,
            peak_kda={p: "" for p in peaks},
            peak_widths={p: estimate_peak_width(smoothed, p) for p in peaks},
        )
        self.marker_lanes.append(lane)
        self.selected_marker_lane_index = len(self.marker_lanes) - 1
        self.load_marker_lane(self.selected_marker_lane_index)
        self.refresh_marker_lane_tree()
        self.status.set(f"已添加 {lane.name}，检测到 {len(peaks)} 个峰；请为本组设置 Marker kDa。")

    def sync_active_marker_lane(self) -> None:
        if not (0 <= self.selected_marker_lane_index < len(self.marker_lanes)):
            return
        lane = self.marker_lanes[self.selected_marker_lane_index]
        lane.image_index = self.marker_image_index
        lane.start, lane.end = self.line_start, self.line_end
        lane.signal, lane.smoothed = self.signal, self.smoothed
        lane.sample_points, lane.peaks = self.sample_points, self.peaks
        lane.peak_kda, lane.peak_widths = self.peak_kda, self.marker_peak_widths
        lane.fit_result = self.fit_result
        lane.cv_rows = self.local_cv_rows

    def load_marker_lane(self, index: int) -> None:
        if not (0 <= index < len(self.marker_lanes)):
            return
        lane = self.marker_lanes[index]
        self.selected_marker_lane_index = index
        self.marker_image_index = lane.image_index
        self.line_start, self.line_end = lane.start, lane.end
        self.signal, self.smoothed = lane.signal, lane.smoothed
        self.sample_points, self.peaks = lane.sample_points, lane.peaks
        self.peak_kda, self.marker_peak_widths = lane.peak_kda, lane.peak_widths
        self.fit_result = lane.fit_result
        self.local_cv_rows = lane.cv_rows or []
        if lane.image_index != self.current_image_index:
            self.current_image_index = lane.image_index
            self.image_combo.current(lane.image_index)
            self.image_var.set(self.image_combo.get())
        self.refresh_tree()
        self.draw_plot()
        self.render_image()

    def refresh_marker_lane_tree(self) -> None:
        if not hasattr(self, "marker_lane_tree"):
            return
        self.marker_lane_tree.delete(*self.marker_lane_tree.get_children())
        for index, lane in enumerate(self.marker_lanes):
            channel = os.path.basename(self.images[lane.image_index][0]) if lane.image_index < len(self.images) else ""
            assigned = sum(bool(value.strip()) for value in lane.peak_kda.values())
            status = "已拟合" if lane.fit_result else f"已赋值 {assigned}"
            self.marker_lane_tree.insert("", tk.END, iid=str(index), values=(lane.name, channel, len(lane.peaks), status))
        if 0 <= self.selected_marker_lane_index < len(self.marker_lanes):
            self.marker_lane_tree.selection_set(str(self.selected_marker_lane_index))

    def on_marker_lane_selected(self, _event=None) -> None:
        selection = self.marker_lane_tree.selection()
        if not selection:
            return
        new_index = int(selection[0])
        if new_index == self.selected_marker_lane_index:
            return
        self.sync_active_marker_lane()
        self.load_marker_lane(new_index)
        lane = self.marker_lanes[new_index]
        self.status.set(f"正在编辑 {lane.name}；预设和手动 kDa 只作用于这一组。")

    def remove_selected_marker_lane(self) -> None:
        if not (0 <= self.selected_marker_lane_index < len(self.marker_lanes)):
            return
        removed = self.marker_lanes.pop(self.selected_marker_lane_index)
        for index, lane in enumerate(self.marker_lanes, start=1):
            lane.name = f"Marker {index}"
        if self.marker_lanes:
            self.selected_marker_lane_index = min(self.selected_marker_lane_index, len(self.marker_lanes) - 1)
            self.load_marker_lane(self.selected_marker_lane_index)
        else:
            self.selected_marker_lane_index = -1
            self.line_start = self.line_end = None
            self.peaks, self.peak_kda, self.marker_peak_widths = [], {}, {}
            self.fit_result = None
            self.refresh_tree()
            self.draw_plot()
            self.render_image()
        self.refresh_marker_lane_tree()
        self.status.set(f"已删除 {removed.name}。")

    def analyze_line(self) -> None:
        if not (self.images and self.line_start and self.line_end):
            messagebox.showinfo("请先选线", "请在图片上沿 Marker lane 拖出一条线。")
            return
        marker_index = self.marker_image_index if self.marker_image_index >= 0 else self.current_image_index
        marker_path, marker_image = self.images[marker_index]
        self.signal, self.sample_points = sample_line_intensity(marker_image, self.line_start, self.line_end, self.width_var.get())
        self.smoothed = smooth_signal(self.signal, self.smooth_var.get())
        old_kda = dict(self.peak_kda)
        self.peaks = detect_peaks(self.smoothed, self.prominence_var.get() / 100.0, max(1, self.distance_var.get()))
        self.peak_kda = {p: old_kda.get(p, "") for p in self.peaks}
        self.marker_peak_widths = {p: estimate_peak_width(self.smoothed, p) for p in self.peaks}
        self.fit_result = None
        self.refresh_tree()
        self.draw_plot()
        self.render_image()
        self.status.set(f"在 {os.path.basename(marker_path)} 检测到 {len(self.peaks)} 个峰；可在曲线上点击增删。")

    def draw_plot(self) -> None:
        self.plot.delete("all")
        if not self.smoothed:
            self.plot.create_text(12, 12, text="选线后显示灰度强度曲线", anchor=tk.NW, fill="#777")
            return
        w, h = max(10, self.plot.winfo_width()), max(10, self.plot.winfo_height())
        margin = 24
        low, high = min(self.smoothed), max(self.smoothed)
        span = high - low or 1.0
        coords = []
        for i, value in enumerate(self.smoothed):
            x = margin + i / max(1, len(self.smoothed) - 1) * (w - 2 * margin)
            y = h - margin - (value - low) / span * (h - 2 * margin)
            coords.extend((x, y))
        if len(coords) >= 4:
            self.plot.create_line(*coords, fill="#1565c0", width=2)
        for p in self.peaks:
            x = margin + p / max(1, len(self.smoothed) - 1) * (w - 2 * margin)
            y = h - margin - (self.smoothed[p] - low) / span * (h - 2 * margin)
            self.plot.create_line(x, h - margin, x, y, fill="#d32f2f", dash=(3, 2))
            self.plot.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#d32f2f", outline="")
            kda = self.peak_kda.get(p, "").strip()
            if kda:
                self.plot.create_text(x + 4, max(8, y - 7), text=f"{kda} kDa", anchor=tk.SW, fill="#b71c1c", font=("TkDefaultFont", 8, "bold"))
        self.plot.create_text(margin, h - 4, text="0 px", anchor=tk.SW, fill="#555")
        self.plot.create_text(w - margin, h - 4, text=f"{len(self.smoothed)-1} px", anchor=tk.SE, fill="#555")

    def _draw_peak_marks(self) -> None:
        for p in self.peaks:
            if p >= len(self.sample_points):
                continue
            x, y = self._to_canvas(self.sample_points[p])
            self.image_canvas.create_oval(x - 5, y - 5, x + 5, y + 5, outline="#ff1744", width=2, tags="selection")
            kda = self.peak_kda.get(p, "").strip()
            if kda:
                self.image_canvas.create_text(
                    x + 8, y,
                    text=f"{kda} kDa",
                    fill="#ffea00",
                    anchor=tk.W,
                    font=("TkDefaultFont", 10, "bold"),
                    tags="selection",
                )

    def toggle_peak_from_plot(self, event: tk.Event) -> None:
        if not self.smoothed:
            return
        margin = 24
        usable = max(1, self.plot.winfo_width() - 2 * margin)
        index = round((event.x - margin) / usable * (len(self.smoothed) - 1))
        index = min(len(self.smoothed) - 1, max(0, index))
        nearest = min(self.peaks, key=lambda p: abs(p - index), default=None)
        tolerance = max(4, round(len(self.smoothed) * 0.012))
        if nearest is not None and abs(nearest - index) <= tolerance:
            self.peaks.remove(nearest)
            self.peak_kda.pop(nearest, None)
            self.marker_peak_widths.pop(nearest, None)
        else:
            left, right = max(0, index - tolerance), min(len(self.smoothed), index + tolerance + 1)
            peak = left + max(range(right - left), key=lambda j: self.smoothed[left + j])
            if peak not in self.peaks:
                self.peaks.append(peak)
                self.peaks.sort()
                self.peak_kda[peak] = ""
                self.marker_peak_widths[peak] = estimate_peak_width(self.smoothed, peak)
        self.fit_result = None
        self.refresh_tree()
        self.draw_plot()
        self.render_image()

    def refresh_tree(self) -> None:
        if not hasattr(self, "tree"):
            return
        self.sync_active_marker_lane()
        self.tree.delete(*self.tree.get_children())
        for p in self.peaks:
            self.tree.insert("", tk.END, iid=str(p), values=(p, self.peak_kda.get(p, "")))
        self.refresh_marker_lane_tree()

    def edit_kda(self, event: tk.Event) -> None:
        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if region != "cell" or column != "#2" or not row:
            return
        bbox = self.tree.bbox(row, column)
        entry = ttk.Entry(self.tree)
        entry.insert(0, self.peak_kda.get(int(row), ""))
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        entry.focus_set()
        entry.select_range(0, tk.END)

        def commit(_event=None) -> None:
            value = entry.get().strip()
            if value:
                try:
                    if float(value) <= 0:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("数值无效", "kDa 必须是大于 0 的数字。")
                    return
            self.peak_kda[int(row)] = value
            entry.destroy()
            self.fit_result = None
            self.refresh_tree()
            self.draw_plot()
            self.render_image()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", lambda _e: entry.destroy())

    def on_preset_selected(self, _event=None) -> None:
        values = self.presets.get(self.preset_var.get(), [])
        self.preset_values_var.set(" ".join(f"{value:g}" for value in values))
        anchor_values = [f"{value:g}" for value in values]
        if hasattr(self, "anchor_combo"):
            self.anchor_combo.configure(values=anchor_values)
        if anchor_values:
            self.anchor_kda_var.set(anchor_values[0])

    def save_preset(self) -> None:
        try:
            values = parse_preset_values(self.preset_values_var.get())
        except ValueError as exc:
            messagebox.showerror("预设无效", str(exc))
            return
        name = simpledialog.askstring("保存 Marker 预设", "请输入新预设名称：", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        self.presets[name] = values
        custom = {key: value for key, value in self.presets.items() if key not in BUILTIN_PRESETS}
        try:
            with self.preset_path.open("w", encoding="utf-8") as handle:
                json.dump(custom, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            messagebox.showerror("保存预设失败", str(exc))
            return
        self.preset_combo.configure(values=list(self.presets))
        self.preset_var.set(name)
        self.on_preset_selected()
        self.status.set(f"已保存 Marker 预设：{name}")

    def apply_full_preset(self) -> None:
        try:
            values = parse_preset_values(self.preset_values_var.get())
        except ValueError as exc:
            messagebox.showerror("预设无效", str(exc))
            return
        if not self.peaks:
            messagebox.showinfo("没有峰", "请先检测或手动添加峰。")
            return
        for peak, kda in zip(self.peaks, values):
            self.peak_kda[peak] = f"{kda:g}"
        for peak in self.peaks[len(values):]:
            self.peak_kda[peak] = ""
        self.fit_result = None
        self.refresh_tree()
        self.draw_plot()
        self.render_image()
        self.status.set(f"已按迁移顺序填写 {min(len(self.peaks), len(values))} 个 Marker。")

    def on_peak_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        value = self.peak_kda.get(int(selection[0]), "").strip()
        if value:
            self.anchor_kda_var.set(value)

    def auto_assign_from_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("请选择锚点", "请先在峰表中选中一个已知条带。")
            return
        try:
            values = parse_preset_values(self.preset_values_var.get())
            anchor_value = float(self.anchor_kda_var.get())
        except ValueError as exc:
            messagebox.showerror("锚点无效", str(exc))
            return
        anchor_preset_index = min(range(len(values)), key=lambda i: abs(values[i] - anchor_value))
        if not math.isclose(values[anchor_preset_index], anchor_value, rel_tol=1e-6):
            messagebox.showerror("锚点不在预设中", "锚点 kDa 必须是当前预设中的一个数值。")
            return
        anchor_peak = int(selection[0])
        peak_index = self.peaks.index(anchor_peak)
        assigned = 0
        for peak, kda in zip(self.peaks[peak_index:], values[anchor_preset_index:]):
            self.peak_kda[peak] = f"{kda:g}"
            assigned += 1
        self.fit_result = None
        self.refresh_tree()
        self.tree.selection_set(str(anchor_peak))
        self.draw_plot()
        self.render_image()
        self.status.set(f"从 {anchor_value:g} kDa 锚点开始，已向下自动排列 {assigned} 个条带。")

    @staticmethod
    def marker_lane_quality(lane: MarkerLane) -> tuple[float, float]:
        errors = [
            float(row["local_relative_error"])
            for row in (lane.cv_rows or []) if row["local_relative_error"] is not None
        ]
        median_cv = statistics.median(errors) if errors else float("inf")
        global_error = lane.fit_result.mean_relative_error if lane.fit_result else float("inf")
        return median_cv, global_error

    def fit_all_marker_lanes(self) -> int:
        self.sync_active_marker_lane()
        if not self.marker_lanes:
            self.fit_curve()
            return 1 if self.fit_result else 0
        failures = []
        valid_indices = []
        for index, lane in enumerate(self.marker_lanes):
            try:
                pairs = prepare_markers(
                    [p for p in lane.peaks if lane.peak_kda.get(p, "").strip()],
                    [float(lane.peak_kda[p]) for p in lane.peaks if lane.peak_kda.get(p, "").strip()],
                )
                lane.fit_result = linear_fit([p for p, _mw in pairs], [mw for _p, mw in pairs])
                lane.cv_rows = local_cross_validation(pairs)
                valid_indices.append(index)
            except ValueError as exc:
                lane.fit_result = None
                lane.cv_rows = []
                failures.append(f"{lane.name}: {exc}")
        if not valid_indices:
            messagebox.showerror("没有可用的 Marker 拟合", "\n".join(failures))
            self.refresh_marker_lane_tree()
            return 0
        best_index = min(valid_indices, key=lambda i: self.marker_lane_quality(self.marker_lanes[i]))
        self.load_marker_lane(best_index)
        best = self.marker_lanes[best_index]
        median_cv = self.marker_lane_quality(best)[0] * 100
        self.fit_summary_var.set(
            f"已拟合 {len(valid_indices)} 组 Marker｜逐 band 自动择优｜当前总体最佳 {best.name}（CV中位误差 {median_cv:.1f}%）"
        )
        self.refresh_marker_lane_tree()
        if failures:
            messagebox.showwarning("部分 Marker 组未参与", "\n".join(failures))
        return len(valid_indices)

    def fit_curve(self) -> None:
        try:
            pairs = self.marker_calibration()
            self.fit_result = linear_fit([p for p, _ in pairs], [mw for _, mw in pairs])
            self.local_cv_rows = local_cross_validation(pairs)
        except ValueError as exc:
            messagebox.showerror("无法拟合", str(exc))
            return
        fit = self.fit_result
        cv_errors = [float(row["local_relative_error"]) for row in self.local_cv_rows if row["local_relative_error"] is not None]
        cv_median = statistics.median(cv_errors) * 100 if cv_errors else float("nan")
        cv_mean = statistics.fmean(cv_errors) * 100 if cv_errors else float("nan")
        cv_max = max(cv_errors) * 100 if cv_errors else float("nan")
        quality = "优秀" if fit.r_squared >= 0.99 else "良好" if fit.r_squared >= 0.97 else "需检查峰对应关系"
        self._set_fit_text(
            "默认结果：邻近 Marker local log-linear interpolation\n"
            f"log10(MW) = {fit.slope:.6f} × position + {fit.intercept:.5f}\n"
            f"Global 诊断：{quality}，R²={fit.r_squared:.4f}，RMSE={fit.rmse_log10:.4f}\n"
            f"Global 平均/最大误差={fit.mean_relative_error * 100:.2f}% / {fit.max_relative_error * 100:.2f}%\n"
            f"Local LOO-CV 中位/平均/最大误差={cv_median:.2f}% / {cv_mean:.2f}% / {cv_max:.2f}%"
        )
        self.fit_summary_var.set(
            f"默认 Local 插值｜Global R²={fit.r_squared:.4f}｜Local CV中位误差={cv_median:.1f}%"
        )
        self.status.set("拟合完成。目标条带位置应使用同一条选线起点的像素距离。")
        self.sync_active_marker_lane()
        self.refresh_marker_lane_tree()
        if self.target_lanes:
            self.refresh_target_views()

    def predict_target(self) -> None:
        if not self.fit_result:
            self.fit_curve()
            if not self.fit_result:
                return
        try:
            position = float(self.target_position.get())
        except ValueError:
            messagebox.showerror("位置无效", "请输入目标条带沿相同迁移方向的位置（像素）。")
            return
        if position < 0:
            messagebox.showerror("位置无效", "目标条带位置不能小于 0。")
            return
        estimate = estimate_band(
            self.marker_calibration(), self.fit_result, position, 0.0,
            self.marker_position_uncertainties(),
        )
        self._set_fit_text(
            f"Local apparent MW = {estimate.apparent_mw_local_kda:.1f} kDa\n"
            f"Global diagnostic MW = {estimate.apparent_mw_global_kda:.1f} kDa\n"
            f"Uncertainty = {estimate.mw_lower_kda:.1f}–{estimate.mw_upper_kda:.1f} kDa\n"
            f"Confidence = {estimate.confidence}\nReported: {estimate.reported_mw_text}"
        )

    def _set_fit_text(self, value: str) -> None:
        self.fit_text.configure(state=tk.NORMAL)
        self.fit_text.delete("1.0", tk.END)
        self.fit_text.insert("1.0", value)
        self.fit_text.configure(state=tk.DISABLED)

    def band_result_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for lane in self.target_lanes:
            channel = os.path.basename(self.images[lane.image_index][0])
            for band_number, peak in enumerate(lane.peaks, start=1):
                estimate = self.estimate_lane_peak(lane, peak)
                rows.append({
                    "lane": lane.name,
                    "channel": channel,
                    "band": band_number,
                    "marker_group_used": estimate.marker_group,
                    "marker_groups_compared": sum(1 for marker in self.marker_lanes if marker.fit_result) or 1,
                    "marker_selection_reason": estimate.selection_reason,
                    "position_px": estimate.position_px,
                    "peak_width_px": estimate.peak_width_px,
                    "position_uncertainty_px": estimate.position_uncertainty_px,
                    "nearest_upper_marker_kDa": estimate.upper_marker_kda,
                    "nearest_upper_marker_position_px": estimate.upper_marker_position_px,
                    "nearest_lower_marker_kDa": estimate.lower_marker_kda,
                    "nearest_lower_marker_position_px": estimate.lower_marker_position_px,
                    "apparent_MW_local_kDa": estimate.apparent_mw_local_kda,
                    "apparent_MW_global_kDa": estimate.apparent_mw_global_kda,
                    "local_global_difference_percent": estimate.local_global_difference_percent,
                    "MW_lower_kDa": estimate.mw_lower_kda,
                    "MW_upper_kDa": estimate.mw_upper_kda,
                    "relative_uncertainty_percent": estimate.relative_uncertainty_percent,
                    "range_status": estimate.range_status,
                    "confidence": estimate.confidence,
                    "reported_MW": estimate.reported_mw,
                    "reported_MW_text": estimate.reported_mw_text,
                    "warnings": " | ".join(estimate.warnings),
                })
        return rows

    def calibration_report_rows(self, marker_lane: MarkerLane | None = None) -> list[dict[str, object]]:
        if marker_lane is None and self.marker_lanes:
            combined: list[dict[str, object]] = []
            for lane in self.marker_lanes:
                if lane.fit_result:
                    combined.extend(self.calibration_report_rows(lane))
            return combined
        rows = (
            (marker_lane.cv_rows or local_cross_validation(self.marker_calibration(marker_lane)))
            if marker_lane else (self.local_cv_rows or local_cross_validation(self.marker_calibration()))
        )
        return [{
            "marker_group": marker_lane.name if marker_lane else "Marker 1",
            "channel": os.path.basename(self.images[marker_lane.image_index][0]) if marker_lane and marker_lane.image_index < len(self.images) else os.path.basename(self.image_path),
            "marker_position_px": row["marker_position_px"],
            "true_marker_kDa": row["true_marker_kda"],
            "global_predicted_kDa": row["global_predicted_kda"],
            "global_relative_error_percent": float(row["global_relative_error"]) * 100,
            "leave_one_out_local_predicted_kDa": row["leave_one_out_local_predicted_kda"],
            "local_relative_error_percent": None if row["local_relative_error"] is None else float(row["local_relative_error"]) * 100,
        } for row in rows]

    @staticmethod
    def _write_dict_csv(path: Path, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def write_calibration_svgs(self, directory: Path, marker_lane: MarkerLane | None = None) -> None:
        fitted_lanes = [lane for lane in self.marker_lanes if lane.fit_result]
        if marker_lane is None and len(fitted_lanes) > 1:
            for lane in fitted_lanes:
                self.write_calibration_svgs(directory, lane)
            return
        if marker_lane is None and len(fitted_lanes) == 1:
            marker_lane = fitted_lanes[0]
        markers = self.marker_calibration(marker_lane)
        fit = marker_lane.fit_result if marker_lane else self.fit_result
        if not fit:
            return
        suffix = ""
        if len(fitted_lanes) > 1 and marker_lane:
            safe_name = "_".join(marker_lane.name.lower().split())
            suffix = f"_{safe_name}"
        width, height, margin = 820, 500, 65
        xs = [p for p, _mw in markers]
        ys = [math.log10(mw) for _p, mw in markers]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)

        def sx(value: float) -> float:
            return margin + (value - xmin) / max(xmax - xmin, 1e-9) * (width - 2 * margin)

        def sy(value: float) -> float:
            return height - margin - (value - ymin) / max(ymax - ymin, 1e-9) * (height - 2 * margin)

        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="#333"/>',
            f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="#333"/>',
            f'<text x="{width/2}" y="{height-15}" text-anchor="middle" font-family="sans-serif">position_px</text>',
            f'<text x="18" y="{height/2}" text-anchor="middle" transform="rotate(-90 18 {height/2})" font-family="sans-serif">log10(MW_kDa)</text>',
            '<text x="410" y="28" text-anchor="middle" font-family="sans-serif" font-size="18">Marker calibration: local vs global</text>',
        ]
        global_y1, global_y2 = fit.slope * xmin + fit.intercept, fit.slope * xmax + fit.intercept
        parts.append(f'<line x1="{sx(xmin):.1f}" y1="{sy(global_y1):.1f}" x2="{sx(xmax):.1f}" y2="{sy(global_y2):.1f}" stroke="#1565c0" stroke-width="2"/>')
        local_points = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(xs, ys))
        parts.append(f'<polyline points="{local_points}" fill="none" stroke="#ef6c00" stroke-width="2"/>')
        for x, y, (_position, mw) in zip(xs, ys, markers):
            predicted_y = fit.slope * x + fit.intercept
            parts.append(f'<line x1="{sx(x):.1f}" y1="{sy(y):.1f}" x2="{sx(x):.1f}" y2="{sy(predicted_y):.1f}" stroke="#999" stroke-dasharray="3 3"/>')
            parts.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="5" fill="#c62828"/>')
            parts.append(f'<text x="{sx(x)+6:.1f}" y="{sy(y)-6:.1f}" font-family="sans-serif" font-size="11">{mw:g}</text>')
        parts.append('<text x="650" y="55" font-family="sans-serif" fill="#1565c0">Global regression</text>')
        parts.append('<text x="650" y="75" font-family="sans-serif" fill="#ef6c00">Local interpolation</text></svg>')
        (directory / f"calibration_diagnostic{suffix}.svg").write_text("\n".join(parts), encoding="utf-8")

        report = self.calibration_report_rows(marker_lane)
        error_values = [max(float(row["global_relative_error_percent"]), float(row["local_relative_error_percent"] or 0)) for row in report]
        emax = max(10.0, max(error_values, default=10.0) * 1.15)
        mw_logs = [math.log10(float(row["true_marker_kDa"])) for row in report]
        mw_min, mw_max = min(mw_logs), max(mw_logs)

        def ex(value: float) -> float:
            return margin + (math.log10(value) - mw_min) / max(mw_max - mw_min, 1e-9) * (width - 2 * margin)

        def ey(value: float) -> float:
            return height - margin - value / emax * (height - 2 * margin)

        errors = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="#333"/>',
            f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="#333"/>',
            '<text x="410" y="28" text-anchor="middle" font-family="sans-serif" font-size="18">Relative calibration error vs MW</text>',
            f'<text x="{width/2}" y="{height-15}" text-anchor="middle" font-family="sans-serif">Marker MW (log scale)</text>',
            f'<text x="18" y="{height/2}" text-anchor="middle" transform="rotate(-90 18 {height/2})" font-family="sans-serif">relative error (%)</text>',
        ]
        for row in report:
            x = ex(float(row["true_marker_kDa"]))
            global_error = float(row["global_relative_error_percent"])
            errors.append(f'<circle cx="{x:.1f}" cy="{ey(global_error):.1f}" r="5" fill="#1565c0"/>')
            if row["local_relative_error_percent"] is not None:
                local_error = float(row["local_relative_error_percent"])
                errors.append(f'<rect x="{x-4:.1f}" y="{ey(local_error)-4:.1f}" width="8" height="8" fill="#ef6c00"/>')
        errors.append('<text x="650" y="55" font-family="sans-serif" fill="#1565c0">Global error</text>')
        errors.append('<text x="650" y="75" font-family="sans-serif" fill="#ef6c00">Local LOO error</text></svg>')
        (directory / f"calibration_error_vs_mw{suffix}.svg").write_text("\n".join(errors), encoding="utf-8")

    def save_results(self) -> None:
        if not self.peaks:
            messagebox.showinfo("没有结果", "请先选线并检测峰。")
            return
        if not self.fit_result:
            self.fit_curve()
            if not self.fit_result:
                return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Excel workbook", "*.xlsx"), ("JSON", "*.json")],
        )
        if not path:
            return
        output_path = Path(path)
        band_rows = self.band_result_rows()
        lane_summary_rows = organize_band_rows_by_lane(band_rows)
        calibration_rows = self.calibration_report_rows()
        cv_errors = [float(row["local_relative_error_percent"]) for row in calibration_rows if row["local_relative_error_percent"] is not None]
        fit_summary = {
            "default_method": "local_log_linear_interpolation",
            "marker_selection_method": "per-band minimum uncertainty with interpolation preferred over extrapolation",
            "fitted_marker_groups": sum(1 for lane in self.marker_lanes if lane.fit_result) or 1,
            "global_slope": self.fit_result.slope,
            "global_intercept": self.fit_result.intercept,
            "global_R_squared": self.fit_result.r_squared,
            "global_RMSE_log10": self.fit_result.rmse_log10,
            "global_mean_relative_error_percent": self.fit_result.mean_relative_error * 100,
            "global_max_relative_error_percent": self.fit_result.max_relative_error * 100,
            "median_local_cv_error_percent": statistics.median(cv_errors) if cv_errors else None,
            "mean_local_cv_error_percent": statistics.fmean(cv_errors) if cv_errors else None,
            "max_local_cv_error_percent": max(cv_errors) if cv_errors else None,
        }
        payload = {
            "images": [image_path for image_path, _image in self.images],
            "marker_image": self.images[self.marker_image_index][0] if self.marker_image_index >= 0 else self.image_path,
            "line_start_xy": self.line_start,
            "line_end_xy": self.line_end,
            "markers": [
                {
                    "position_px": p,
                    "marker_kDa": float(self.peak_kda[p]),
                    "peak_width_px": self.marker_peak_widths.get(p, 0.0),
                }
                for p in self.peaks if self.peak_kda.get(p, "").strip()
            ],
            "marker_groups": [
                {
                    "name": lane.name,
                    "image": self.images[lane.image_index][0],
                    "line_start_xy": lane.start,
                    "line_end_xy": lane.end,
                    "markers": [
                        {
                            "position_px": p,
                            "marker_kDa": float(lane.peak_kda[p]),
                            "peak_width_px": lane.peak_widths.get(p, 0.0),
                        }
                        for p in lane.peaks if lane.peak_kda.get(p, "").strip()
                    ],
                    "fit": lane.fit_result.__dict__ if lane.fit_result else None,
                }
                for lane in self.marker_lanes
            ],
            "fit_summary": fit_summary,
            "calibration_report": calibration_rows,
            "bands": band_rows,
            "lane_summary": lane_summary_rows,
        }
        try:
            if output_path.suffix.lower() == ".json":
                with output_path.open("w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
            elif output_path.suffix.lower() == ".xlsx":
                try:
                    from openpyxl import Workbook
                    from openpyxl.styles import Alignment, Font, PatternFill
                    from openpyxl.utils import get_column_letter
                except ImportError as exc:
                    raise OSError("保存 XLSX 需要 openpyxl，请运行：python3 -m pip install openpyxl") from exc
                workbook = Workbook()
                summary_sheet = workbook.active
                summary_sheet.title = "Lane summary"
                if lane_summary_rows:
                    summary_sheet.append(list(lane_summary_rows[0]))
                    for row in lane_summary_rows:
                        summary_sheet.append(list(row.values()))
                    summary_sheet.freeze_panes = "D2"
                    summary_sheet.auto_filter.ref = summary_sheet.dimensions
                    for cell in summary_sheet[1]:
                        cell.fill = PatternFill("solid", fgColor="1F4E78")
                        cell.font = Font(color="FFFFFF", bold=True)
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    for column_index, header in enumerate(lane_summary_rows[0], start=1):
                        width = 18
                        if header == "lane": width = 11
                        elif header == "channel": width = 24
                        elif header == "band_count": width = 12
                        elif header == "band_positions_px": width = 32
                        elif header in {"marker_groups_used", "confidence"}: width = 26
                        elif header == "warning_count": width = 14
                        summary_sheet.column_dimensions[get_column_letter(column_index)].width = width
                    for row in summary_sheet.iter_rows(min_row=2):
                        for cell in row:
                            cell.alignment = Alignment(vertical="center", wrap_text=True)
                    summary_sheet.sheet_view.showGridLines = False
                band_sheet = workbook.create_sheet("Band results")
                if band_rows:
                    band_sheet.append(list(band_rows[0]))
                    for row in band_rows:
                        band_sheet.append(list(row.values()))
                    band_sheet.freeze_panes = "A2"
                    band_sheet.auto_filter.ref = band_sheet.dimensions
                calibration_sheet = workbook.create_sheet("Calibration report")
                calibration_sheet.append(list(calibration_rows[0]))
                for row in calibration_rows:
                    calibration_sheet.append(list(row.values()))
                summary_sheet = workbook.create_sheet("Fit summary")
                summary_sheet.append(["metric", "value"])
                for key, value in fit_summary.items():
                    summary_sheet.append([key, value])
                workbook.save(output_path)
            else:
                if band_rows:
                    self._write_dict_csv(output_path, band_rows)
                else:
                    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
                        handle.write("No target bands were defined.\n")
            if lane_summary_rows:
                lane_summary_path = output_path.parent / "lane_summary.csv"
                if lane_summary_path.resolve() == output_path.resolve():
                    lane_summary_path = output_path.parent / "lane_summary_by_lane.csv"
                self._write_dict_csv(lane_summary_path, lane_summary_rows)
            self._write_dict_csv(output_path.parent / "calibration_report.csv", calibration_rows)
            with (output_path.parent / "fit_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["metric", "value"])
                writer.writerows(fit_summary.items())
            self.write_calibration_svgs(output_path.parent)
            self.status.set(f"结果和 calibration diagnostics 已保存到：{output_path.parent}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("保存失败", str(exc))


def main() -> None:
    if Image is None or ImageTk is None:
        raise SystemExit("缺少 Pillow。请先运行：python3 -m pip install Pillow")
    app = WBMarkerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
