from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_conviction_calibration import (  # noqa: E402
    apply_conviction_calibration,
    build_regime_error_profile,
    calibrate_regime_conviction,
    write_phase5l01_diagnostics,
)
from models.promotions.promo_regime_state import apply_regime_brain_decisioning, build_promo_regime_state_frame  # noqa: E402


def _frame(n: int = 8, **overrides: object) -> pd.DataFrame:
    def _rep(values: list[object]) -> list[object]:
        if n <= len(values):
            return values[:n]
        return (values * ((n // len(values)) + 1))[:n]

    base = {
        "store_number": [772] * n,
        "sku_number": [str(i) for i in range(n)],
        "sku_description": [f"SKU{i}" for i in range(n)],
        "department": ["Grocery"] * n,
        "promotion_name": ["Summer"] * n,
        "promotion_start_date": ["2024-06-01"] * n,
        "promo_days": [7] * n,
        "discount_percent": [15.0] * n,
        "average_daily_units": _rep([1.0, 0.05, 2.0, 5.0, 1.0, 0.5, 3.0, 4.0]),
        "actual_units_sold_promo": _rep([10.0, 1.0, 20.0, 50.0, 8.0, 2.0, 30.0, 40.0]),
        "model_expected_units_total_promo": _rep([12.0, 5.0, 18.0, 45.0, 6.0, 8.0, 25.0, 35.0]),
        "current_soh": _rep([5.0, 2.0, 10.0, 200.0, 3.0, 1.0, 15.0, 20.0]),
        "optimal_base_soh_units": _rep([30.0, 2.0, 30.0, 30.0, 30.0, 2.0, 30.0, 30.0]),
        "expected_promo_uplift_units": _rep([2.0, 0.5, 6.0, 15.0, 1.0, 1.0, 5.0, 8.0]),
        "expected_normal_units_during_promo": _rep([7.0, 0.35, 14.0, 35.0, 7.0, 3.5, 21.0, 28.0]),
        "promo_convexity_score": _rep([20.0, 5.0, 25.0, 65.0, 10.0, 8.0, 30.0, 55.0]),
        "current_stock_position_label": _rep(["UNDERSTOCKED", "OPTIMAL", "UNDERSTOCKED", "SEVERELY_OVERSTOCKED", "OPTIMAL", "OPTIMAL", "UNDERSTOCKED", "UNDERSTOCKED"]),
        "distance_to_optimal_end_soh": _rep([5.0, 1.0, 8.0, 50.0, 2.0, 1.0, 6.0, 4.0]),
        "optimal_stock_position_order_units": _rep([20.0, 0.0, 15.0, 0.0, 0.0, 0.0, 10.0, 12.0]),
        "simulated_missed_demand_units": _rep([3.0, 0.0, 5.0, 0.0, 0.0, 0.0, 2.0, 1.0]),
        "leftover_units_above_optimal": _rep([0.0, 0.0, 0.0, 170.0, 0.0, 0.0, 0.0, 0.0]),
        "promo_start_soh_source_quality": _rep(["HIGH", "HIGH", "HIGH", "HIGH", "UNKNOWN", "HIGH", "HIGH", "HIGH"]),
        "supplier_number_source_quality": ["HIGH"] * n,
        "replenishment_risk_class": ["OVERNIGHT_REPLENISHMENT"] * n,
        "supplier_reorder_flexibility_repaired": ["HIGH"] * n,
        "stockout_suspected_flag": _rep([0, 0, 0, 0, 1, 0, 0, 0]),
        "promo_demand_source_quality": _rep(["HIGH", "HIGH", "HIGH", "HIGH", "UNSAFE", "MEDIUM", "HIGH", "HIGH"]),
        "promo_demand_release_ready_flag": _rep(["YES", "YES", "YES", "YES", "NO", "YES", "YES", "YES"]),
        "feature_basket_structure_evidence_available_flag": _rep([1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0]),
        "feature_sparse_demand_evidence_available_flag": _rep([0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]),
        "historical_units_same_discount_avg": _rep([10.0, 0.0, 20.0, 40.0, 0.0, 0.0, 15.0, 25.0]),
        "promo_start_soh_confidence_score": _rep([80.0, 70.0, 75.0, 75.0, 20.0, 60.0, 70.0, 72.0]),
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _enriched(**overrides: object) -> pd.DataFrame:
    frame = _frame(**overrides)
    regime = build_promo_regime_state_frame(frame)
    return apply_regime_brain_decisioning(regime, gate_recommendation="NO_RELEASE")


class PromoConvictionCalibrationTests(unittest.TestCase):
    def test_wape_by_regime(self) -> None:
        enriched = _enriched()
        profile = build_regime_error_profile(enriched, enriched)
        self.assertFalse(profile.empty)
        self.assertIn("WAPE", profile.columns)
        total = profile.loc[profile["row_count"].idxmax()]
        self.assertGreaterEqual(float(total["WAPE"]), 0.0)

    def test_bias_by_regime(self) -> None:
        profile = build_regime_error_profile(_enriched(), _enriched())
        self.assertTrue(profile["bias_pct"].notna().all())

    def test_small_sample_lowers_cap(self) -> None:
        small = build_regime_error_profile(_enriched(n=4), _enriched(n=4))
        self.assertTrue((small["recommended_confidence_cap"] <= 55).all())

    def test_high_wape_lowers_cap(self) -> None:
        bad = _enriched(model_expected_units_total_promo=[100.0] * 8, actual_units_sold_promo=[5.0] * 8)
        profile = build_regime_error_profile(bad, bad)
        self.assertTrue((profile["recommended_confidence_cap"] <= 60).any())

    def test_extreme_bias_lowers_cap(self) -> None:
        biased = _enriched(model_expected_units_total_promo=[100.0] * 8, actual_units_sold_promo=[10.0] * 8)
        profile = build_regime_error_profile(biased, biased)
        self.assertTrue((profile["recommended_confidence_cap"] <= 70).any())

    def test_unsafe_rows_lower_cap(self) -> None:
        profile = build_regime_error_profile(_enriched(), _enriched())
        unsafe_rows = profile[profile["unsafe_count"] > 0]
        if not unsafe_rows.empty:
            self.assertLess(float(unsafe_rows["recommended_confidence_cap"].max()), 90.0)

    def test_raw_conviction_preserved(self) -> None:
        enriched = _enriched()
        profile = build_regime_error_profile(enriched, enriched)
        out = calibrate_regime_conviction(enriched, profile)
        self.assertTrue((out["raw_regime_conviction_score"] >= out["calibrated_regime_conviction_score"]).all())

    def test_calibrated_bounded(self) -> None:
        out = apply_conviction_calibration(_enriched())
        self.assertTrue(out["calibrated_regime_conviction_score"].between(0, 100).all())

    def test_unsafe_cannot_be_high_conviction(self) -> None:
        out = apply_conviction_calibration(_enriched())
        unsafe = out[out["promo_demand_source_quality"].eq("UNSAFE")]
        self.assertTrue(unsafe["calibrated_conviction_label"].isin(["VERY_LOW", "LOW", "MEDIUM"]).all())

    def test_unknown_soh_cannot_be_very_high(self) -> None:
        out = apply_conviction_calibration(_enriched())
        unknown = out[out["promo_start_soh_source_quality"].eq("UNKNOWN")]
        self.assertFalse(unknown["calibrated_conviction_label"].eq("VERY_HIGH").any())

    def test_release_blocked_cannot_be_very_high(self) -> None:
        out = apply_conviction_calibration(_enriched(), gate_recommendation="NO_RELEASE")
        self.assertLess(int(out["calibrated_conviction_label"].eq("VERY_HIGH").sum()), len(out))

    def test_good_regime_can_support_high_conviction(self) -> None:
        rows = 120
        good = _frame(
            n=rows,
            promo_demand_source_quality=["HIGH"] * rows,
            promo_start_soh_source_quality=["HIGH"] * rows,
            model_expected_units_total_promo=[10.1] * rows,
            actual_units_sold_promo=[10.0] * rows,
            average_daily_units=[2.0] * rows,
            current_stock_position_label=["UNDERSTOCKED"] * rows,
            promo_convexity_score=[30.0] * rows,
            promo_demand_release_ready_flag=["YES"] * rows,
            stockout_suspected_flag=[0] * rows,
            feature_basket_structure_evidence_available_flag=[1.0] * rows,
            feature_sparse_demand_evidence_available_flag=[0.0] * rows,
            historical_units_same_discount_avg=[20.0] * rows,
            distance_to_optimal_end_soh=[5.0] * rows,
            optimal_stock_position_order_units=[10.0] * rows,
            current_soh=[5.0] * rows,
            optimal_base_soh_units=[30.0] * rows,
        )
        enriched = apply_regime_brain_decisioning(
            build_promo_regime_state_frame(good),
            gate_recommendation="LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY",
        )
        profile = build_regime_error_profile(enriched, enriched)
        out = calibrate_regime_conviction(
            enriched,
            profile,
            config={"gate_recommendation": "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY", "model_bias_pct": -5.0},
        )
        self.assertGreater(int(out["calibrated_conviction_label"].isin(["HIGH", "VERY_HIGH"]).sum()), 0)

    def test_downgrade_reason_populated(self) -> None:
        out = apply_conviction_calibration(_enriched(), gate_recommendation="NO_RELEASE", model_bias_pct=-23.6)
        self.assertTrue(out["conviction_downgrade_reason"].astype(str).ne("none").any())

    def test_low_conviction_buyer_review(self) -> None:
        out = apply_conviction_calibration(_enriched(), gate_recommendation="NO_RELEASE", model_bias_pct=-23.6)
        low = out[out["calibrated_conviction_label"].isin(["VERY_LOW", "LOW"])]
        if not low.empty:
            self.assertTrue((low["buyer_review_required_flag"] == "YES").all())

    def test_high_risk_low_conviction_review(self) -> None:
        out = apply_conviction_calibration(_enriched(), gate_recommendation="NO_RELEASE", model_bias_pct=-23.6)
        flagged = out[(out["calibrated_conviction_label"].isin(["VERY_LOW", "LOW"])) & (out["overall_regime_risk_score"] >= 40)]
        if not flagged.empty:
            self.assertTrue((flagged["buyer_review_required_flag"] == "YES").all())

    def test_brain_preserved_on_review(self) -> None:
        enriched = _enriched()
        before = enriched["brain_order_units_proposal"].copy()
        out = apply_conviction_calibration(enriched, gate_recommendation="NO_RELEASE", model_bias_pct=-23.6)
        self.assertTrue(out["brain_order_units_proposal"].equals(before))

    def test_governed_traceable(self) -> None:
        out = apply_conviction_calibration(_enriched(), gate_recommendation="NO_RELEASE", model_bias_pct=-23.6)
        self.assertTrue(out["brain_action_label"].notna().all())
        self.assertTrue(out["final_governed_action_label"].notna().all())

    def test_diagnostics_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase5l01_diagnostics(frame=_enriched(), diagnostics_dir=diag)
            for name in (
                "phase5l01_regime_error_profile.csv",
                "phase5l01_conviction_score_distribution_before_after.csv",
                "phase5l01_conviction_downgrade_reasons.csv",
                "phase5l01_regime_bias_learning_summary.csv",
                "phase5l01_brain_vs_governed_actions_with_conviction.csv",
                "phase5l01_release_gate.csv",
            ):
                self.assertTrue((diag / name).exists(), msg=name)
            self.assertIn("avg_calibrated_conviction", result)

    def test_before_after_distribution_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            write_phase5l01_diagnostics(frame=_enriched(), diagnostics_dir=diag)
            dist = pd.read_csv(diag / "phase5l01_conviction_score_distribution_before_after.csv")
            before = dist.loc[dist["stage"] == "conviction_before", "avg_conviction"].iloc[0]
            after = dist.loc[dist["stage"] == "conviction_after", "avg_conviction"].iloc[0]
            self.assertLess(after, before)

    def test_no_nan_numeric_outputs(self) -> None:
        out = apply_conviction_calibration(_enriched())
        numeric = out.select_dtypes(include=[np.number])
        self.assertFalse(numeric.isna().any().any())


if __name__ == "__main__":
    unittest.main()
