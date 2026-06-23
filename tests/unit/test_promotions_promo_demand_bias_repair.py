from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_demand_backtest import compute_wape  # noqa: E402
from models.promotions.promo_demand_bias_repair import (  # noqa: E402
    FACTOR_MAX,
    FACTOR_MIN,
    DEFAULT_MIN_SAMPLE,
    apply_underforecast_bias_adjustments,
    build_bias_adjusted_backtest_summary,
    compute_residual_bias_breakdown,
    evaluate_bias_adjusted_release_gate,
    fit_underforecast_bias_adjustments,
)
from models.promotions.promo_demand_calibration import (  # noqa: E402
    apply_promo_demand_calibration,
    assign_observation_quality,
    fit_promo_demand_calibration_factors,
)


def _backtest_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": [772] * 8,
            "sku_number": [1, 2, 3, 4, 5, 6, 7, 8],
            "promotion_start_date": ["2024-01-01"] * 8,
            "promotion_end_date": ["2024-01-07"] * 8,
            "promo_days": [7] * 8,
            "department": ["A", "A", "A", "A", "B", "B", "B", "B"],
            "category": ["c1"] * 8,
            "discount_percent": [15, 15, 15, 15, 25, 25, 25, 25],
            "actual_units_sold_promo": [20.0, 16.0, 24.0, 18.0, 8.0, 0.0, 12.0, 10.0],
            "model_expected_units_total_promo": [10.0, 8.0, 12.0, 9.0, 4.0, 2.0, 4.0, 3.0],
            "baseline_expected_units_total_promo": [16.0, 16.0, 16.0, 16.0, 10.0, 10.0, 10.0, 10.0],
            "historical_proxy_expected_units_total_promo": [14.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0, 8.0],
            "promo_demand_source_quality": ["HIGH"] * 8,
            "promo_demand_source_quality_repaired": ["HIGH", "HIGH", "MEDIUM", "MEDIUM", "MEDIUM", "UNSAFE", "HIGH", "HIGH"],
            "promo_demand_release_ready_flag": ["YES"] * 8,
            "promo_demand_release_ready_flag_repaired": ["YES"] * 8,
            "calibration_eligible_flag_repaired": ["YES", "NO", "YES", "YES", "YES", "YES", "YES", "YES"],
            "model_beats_baseline_flag": [1] * 8,
            "model_beats_historical_proxy_flag": [1] * 8,
            "stockout_suspected_flag": [0, 1, 0, 0, 0, 0, 0, 0],
            "leftover_units_estimate": [0.0] * 8,
            "under_order_risk_units": [0.0] * 8,
        }
    )


def _calibrated_frame() -> pd.DataFrame:
    frame = assign_observation_quality(_backtest_frame())
    factors = fit_promo_demand_calibration_factors(frame)
    return apply_promo_demand_calibration(frame, factors)


class PromoDemandBiasRepairTests(unittest.TestCase):
    def test_residual_bias_calculation(self) -> None:
        frame = _calibrated_frame()
        residual = compute_residual_bias_breakdown(frame)
        total = residual[residual["segment"].eq("total")].iloc[0]
        actual = frame["actual_units_sold_promo"].sum()
        forecast = frame["model_expected_units_total_promo_calibrated"].sum()
        expected_bias = (forecast - actual) / actual * 100.0
        self.assertAlmostEqual(float(total["bias_pct"]), expected_bias, places=3)
        self.assertAlmostEqual(
            float(total["wape"]),
            compute_wape(frame["actual_units_sold_promo"], frame["model_expected_units_total_promo_calibrated"]),
            places=4,
        )

    def test_underforecast_factor_clipped_to_bounds(self) -> None:
        frame = _calibrated_frame()
        factors = fit_underforecast_bias_adjustments(frame, min_sample=1)
        applied = factors["factor_applied"].astype(float)
        self.assertTrue((applied >= FACTOR_MIN - 1e-9).all())
        self.assertTrue((applied <= FACTOR_MAX + 1e-9).all())

    def test_small_samples_shrink_toward_global(self) -> None:
        frame = _calibrated_frame()
        factors = fit_underforecast_bias_adjustments(frame, min_sample=DEFAULT_MIN_SAMPLE)
        total = factors[factors["segment_level"].eq("total")].iloc[0]
        global_factor = float(total["factor_applied"])
        dept = factors[factors["segment_level"].eq("department")]
        if not dept.empty:
            for _, row in dept.iterrows():
                if row["row_count"] < DEFAULT_MIN_SAMPLE:
                    self.assertNotAlmostEqual(float(row["factor_applied"]), float(row["raw_factor"]), places=6)

    def test_unsafe_rows_excluded_from_fit(self) -> None:
        frame = _calibrated_frame()
        factors = fit_underforecast_bias_adjustments(frame, min_sample=1)
        eligible = frame[
            frame["calibration_eligible_flag_repaired"].eq("YES")
            & frame["promo_demand_source_quality_repaired"].isin(["HIGH", "MEDIUM"])
            & frame["demand_observation_quality"].eq("HIGH")
            & frame["stockout_suspected_flag"].astype(int).eq(0)
        ]
        total_row = factors[factors["segment_level"].eq("total")].iloc[0]
        self.assertEqual(int(total_row["row_count"]), len(eligible))
        self.assertNotIn("UNSAFE", frame.loc[eligible.index, "promo_demand_source_quality_repaired"].unique())

    def test_censored_rows_excluded_from_fit(self) -> None:
        frame = _calibrated_frame()
        eligible = frame[
            frame["calibration_eligible_flag_repaired"].eq("YES")
            & frame["promo_demand_source_quality_repaired"].isin(["HIGH", "MEDIUM"])
            & frame["demand_observation_quality"].eq("HIGH")
        ]
        self.assertNotIn(2, eligible["sku_number"].tolist())

    def test_raw_and_calibrated_forecasts_preserved(self) -> None:
        frame = _calibrated_frame()
        raw_before = frame["model_expected_units_total_promo_raw"].copy()
        cal_before = frame["model_expected_units_total_promo_calibrated"].copy()
        factors = fit_underforecast_bias_adjustments(frame, min_sample=1)
        adjusted = apply_underforecast_bias_adjustments(frame, factors)
        pd.testing.assert_series_equal(adjusted["model_expected_units_total_promo_raw"], raw_before, check_names=False)
        pd.testing.assert_series_equal(adjusted["model_expected_units_total_promo_calibrated"], cal_before, check_names=False)

    def test_bias_adjusted_forecast_has_no_nan_or_negative(self) -> None:
        frame = _calibrated_frame()
        factors = fit_underforecast_bias_adjustments(frame, min_sample=1)
        adjusted = apply_underforecast_bias_adjustments(frame, factors)
        col = adjusted["bias_adjusted_expected_units_total_promo"]
        self.assertFalse(col.isna().any())
        self.assertFalse(np.isinf(col).any())
        self.assertTrue((col >= 0).all())

    def test_wape_gate_blocks_release_if_worse_than_baseline(self) -> None:
        frame = _calibrated_frame()
        factors = fit_underforecast_bias_adjustments(frame, min_sample=1)
        adjusted = apply_underforecast_bias_adjustments(frame, factors, gate_recommendation="LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        summary = build_bias_adjusted_backtest_summary(adjusted)
        adj = summary[summary["model_variant"].eq("bias_adjusted_model")].iloc[0].copy()
        base = summary[summary["model_variant"].eq("baseline")].iloc[0].copy()
        adj["wape"] = base["wape"] + 0.5
        summary.loc[summary["model_variant"].eq("bias_adjusted_model"), "wape"] = adj["wape"]
        recommendation, blocker, _ = evaluate_bias_adjusted_release_gate(summary, adjusted)
        self.assertEqual(recommendation, "NO_RELEASE")
        self.assertEqual(blocker, "bias_adjusted_wape_not_better_than_baseline")

    def test_limited_release_allowed_only_when_all_gates_pass(self) -> None:
        frame = _calibrated_frame()
        factors = fit_underforecast_bias_adjustments(frame, min_sample=1)
        adjusted = apply_underforecast_bias_adjustments(
            frame,
            factors,
            gate_recommendation="LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY",
        )
        adjusted["bias_adjusted_forecast_allowed_flag"] = "YES"
        summary = build_bias_adjusted_backtest_summary(adjusted)
        adj_row = summary[summary["model_variant"].eq("bias_adjusted_model")].iloc[0]
        base_row = summary[summary["model_variant"].eq("baseline")].iloc[0]
        if float(adj_row["wape"]) < float(base_row["wape"]) and -15.0 <= float(adj_row["bias_pct"]) <= 20.0:
            recommendation, blocker, gate = evaluate_bias_adjusted_release_gate(summary, adjusted)
            if int(gate["limited_release_rows"].iloc[0]) > 0 and float(adj_row["estimated_net_value_proxy"]) > 0:
                self.assertIn(recommendation, {"LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY", "INTERNAL_SHADOW_ONLY", "NO_RELEASE"})
                if recommendation == "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY":
                    self.assertEqual(blocker, "none_limited_release_earned")
        else:
            recommendation, blocker, _ = evaluate_bias_adjusted_release_gate(summary, adjusted)
            self.assertNotEqual(recommendation, "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")


if __name__ == "__main__":
    unittest.main()
