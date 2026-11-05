import math
import unittest
from dataclasses import replace

from wb_tools.core import (
    detect_peaks,
    choose_best_marker_estimate,
    estimate_band,
    estimate_peak_width,
    linear_fit,
    local_cross_validation,
    local_log_interpolate,
    organize_band_rows_by_lane,
    parse_preset_values,
    smooth_signal,
)


EXAMPLE_MARKERS = [
    (25, 600), (94, 400), (124, 250), (141, 230), (215, 130),
    (307, 110), (362, 75), (422, 45), (478, 20),
]


class CoreTests(unittest.TestCase):
    def test_smoothing(self):
        self.assertEqual(smooth_signal([0, 3, 0], 1), [1.5, 1.0, 1.5])

    def test_detect_peaks(self):
        signal = [0, 1, 5, 1, 0, 0, 2, 8, 2, 0]
        self.assertEqual(detect_peaks(signal, min_prominence=0.2, min_distance=3), [2, 7])

    def test_linear_fit_and_prediction(self):
        positions = [10, 20, 30, 40]
        slope, intercept = -0.02, 3.0
        weights = [10 ** (slope * p + intercept) for p in positions]
        fit = linear_fit(positions, weights)
        self.assertAlmostEqual(fit.slope, slope)
        self.assertAlmostEqual(fit.intercept, intercept)
        self.assertAlmostEqual(fit.r_squared, 1.0)
        self.assertAlmostEqual(fit.rmse_log10, 0.0)
        self.assertAlmostEqual(fit.mean_relative_error, 0.0)
        self.assertTrue(math.isclose(fit.predict(25), 10 ** 2.5))

    def test_parse_preset(self):
        self.assertEqual(parse_preset_values("170, 130，100 70"), [170, 130, 100, 70])
        with self.assertRaises(ValueError):
            parse_preset_values("100 130")

    def test_local_interpolation_regression_case(self):
        at_marker = local_log_interpolate(EXAMPLE_MARKERS, 94.0)[0]
        high_region = local_log_interpolate(EXAMPLE_MARKERS, 54.9)[0]
        self.assertAlmostEqual(at_marker, 400.0, places=6)
        self.assertTrue(490 < high_region < 510)
        self.assertTrue(390 < local_log_interpolate(EXAMPLE_MARKERS, 94.3)[0] < 400)
        self.assertTrue(140 < local_log_interpolate(EXAMPLE_MARKERS, 195)[0] < 160)
        self.assertTrue(110 < local_log_interpolate(EXAMPLE_MARKERS, 272)[0] < 125)

    def test_global_is_diagnostic_not_default(self):
        positions = [p for p, _mw in EXAMPLE_MARKERS]
        weights = [mw for _p, mw in EXAMPLE_MARKERS]
        fit = linear_fit(positions, weights)
        estimate = estimate_band(EXAMPLE_MARKERS, fit, 94.3, peak_width_px=8)
        self.assertTrue(390 < estimate.apparent_mw_local_kda < 400)
        self.assertTrue(340 < estimate.apparent_mw_global_kda < 370)
        self.assertGreater(estimate.local_global_difference_percent, 8)
        self.assertIn("kDa", estimate.reported_mw_text)
        self.assertLess(estimate.mw_lower_kda, estimate.apparent_mw_local_kda)
        self.assertGreater(estimate.mw_upper_kda, estimate.apparent_mw_local_kda)

    def test_leave_one_out_and_extrapolation(self):
        rows = local_cross_validation(EXAMPLE_MARKERS)
        self.assertEqual(len(rows), len(EXAMPLE_MARKERS))
        self.assertIsNone(rows[0]["local_relative_error"])
        self.assertIsNotNone(rows[2]["local_relative_error"])
        fit = linear_fit([p for p, _mw in EXAMPLE_MARKERS], [mw for _p, mw in EXAMPLE_MARKERS])
        estimate = estimate_band(EXAMPLE_MARKERS, fit, 10)
        self.assertEqual(estimate.range_status, "extrapolation_high_MW")
        self.assertEqual(estimate.confidence, "very_low")
        self.assertEqual(estimate.reported_mw_text, ">600 kDa")

    def test_peak_width(self):
        signal = [0, 0, 2, 5, 8, 5, 2, 0, 0]
        self.assertGreaterEqual(estimate_peak_width(signal, 4), 2)

    def test_best_marker_group_selection(self):
        fit = linear_fit([p for p, _mw in EXAMPLE_MARKERS], [mw for _p, mw in EXAMPLE_MARKERS])
        base = estimate_band(EXAMPLE_MARKERS, fit, 195, peak_width_px=8)
        higher_uncertainty = replace(
            base, marker_group="Marker 1", relative_uncertainty_percent=22.0,
            confidence="medium", range_status="interpolation",
        )
        lower_uncertainty = replace(
            base, marker_group="Marker 2", relative_uncertainty_percent=9.0,
            confidence="high", range_status="interpolation",
        )
        extrapolated = replace(
            base, marker_group="Marker 3", relative_uncertainty_percent=3.0,
            confidence="very_low", range_status="extrapolation_high_MW",
        )
        chosen = choose_best_marker_estimate([higher_uncertainty, extrapolated, lower_uncertainty])
        self.assertEqual(chosen.marker_group, "Marker 2")
        self.assertIn("Compared 3", chosen.selection_reason)

    def test_organize_band_rows_by_lane(self):
        rows = [
            {"lane": "Lane 1", "channel": "target.tif", "band": 1, "reported_MW_text": "~400 kDa", "position_px": 94.3, "marker_group_used": "Marker 1", "confidence": "high", "warnings": ""},
            {"lane": "Lane 1", "channel": "target.tif", "band": 2, "reported_MW_text": "~150 kDa", "position_px": 195.0, "marker_group_used": "Marker 2", "confidence": "medium", "warnings": "wide peak"},
            {"lane": "Lane 2", "channel": "target.tif", "band": 1, "reported_MW_text": "~120 kDa", "position_px": 272.0, "marker_group_used": "Marker 2", "confidence": "high", "warnings": ""},
        ]
        summary = organize_band_rows_by_lane(rows)
        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]["band_count"], 2)
        self.assertEqual(summary[0]["band_1"], "~400 kDa")
        self.assertEqual(summary[0]["band_2"], "~150 kDa")
        self.assertEqual(summary[0]["marker_groups_used"], "Marker 1; Marker 2")
        self.assertEqual(summary[0]["warning_count"], 1)
        self.assertEqual(summary[1]["band_2"], "")


if __name__ == "__main__":
    unittest.main()
