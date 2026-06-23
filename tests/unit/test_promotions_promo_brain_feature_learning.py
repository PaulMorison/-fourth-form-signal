from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_brain_feature_learning import (  # noqa: E402
    ACTION_LABELS,
    BRAIN_OUTPUT_COLUMNS,
    FEATURE_FAMILIES,
    TARGET_COLUMNS,
    UNKNOWN,
    apply_brain_feature_learning,
    build_brain_training_frame,
    score_brain_value_models,
    train_brain_value_models,
    write_phase5q_diagnostics,
)


def _synthetic_row(**overrides) -> dict:
    base = {
        "store_number": "772",
        "promotion_id": "P1",
        "promotion_name": "Test Promo",
        "promotion_start_date": "2024-06-01",
        "promotion_end_date": "2024-06-14",
        "sku_number": "100",
        "sku_description": "Test SKU",
        "department": "Grocery",
        "category": "Snacks",
        "average_daily_units": 2.0,
        "expected_normal_units_during_promo": 10.0,
        "expected_promo_uplift_units": 5.0,
        "promo_convexity_score": 45.0,
        "sku_demand_regime": "STABLE",
        "current_soh": 1.0,
        "promo_start_soh_resolved": 1.0,
        "expected_soh_at_promo_start_before_order": 1.0,
        "optimal_base_soh_units": 8.0,
        "target_day_one_promo_soh": 10.0,
        "target_end_promo_soh": 4.0,
        "distance_to_optimal_end_soh": 3.0,
        "current_stock_position_label": "UNDERSTOCKED",
        "stock_position_regime": "UNDERSTOCKED",
        "cash_tied_above_optimal_cost": 0.0,
        "feature_basket_attach_rate": 0.4,
        "feature_basket_3plus_attach_rate": 0.35,
        "feature_basket_5plus_attach_rate": 0.2,
        "feature_avg_basket_value_when_present": 25.0,
        "feature_avg_basket_gp_when_present": 8.0,
        "feature_sister_club_attach_rate": 0.3,
        "mission_sku_score": 50.0,
        "mission_sku_flag": "YES",
        "basket_completion_sku_score": 40.0,
        "range_trust_sku_score": 35.0,
        "long_tail_sku_flag": "YES",
        "long_tail_mission_sku_flag": "YES",
        "long_tail_protection_value": 30.0,
        "basket_trust_convexity_value": 20.0,
        "supplier_number_resolved": "999",
        "supplier_replenishment_regime": "DAILY",
        "replenishment_lead_time_days": 1.0,
        "replenishment_reliability": "HIGH",
        "supplier_risk_cost": 0.0,
        "supplier_economic_risk_cost": 0.0,
        "store_sales_regime": "STRONG",
        "customer_loyalty_regime": "LOYAL",
        "customer_price_sensitivity_regime": "MEDIUM",
        "customer_basket_trust_regime": "HIGH",
        "promo_discount_regime": "MODERATE",
        "promo_convexity_regime": "HIGH",
        "cash_efficiency_regime": "EFFICIENT",
        "overall_regime_opportunity_score": 60.0,
        "overall_regime_risk_score": 20.0,
        "calibrated_regime_conviction_score": 55.0,
        "economic_net_value_score": 40.0,
        "expected_gp_capture_value": 25.0,
        "missed_sales_avoidance_value": 15.0,
        "basket_trust_protection_value": 20.0,
        "overstock_cash_release_value": 0.0,
        "review_roi_score": 10.0,
        "decision_triage_class": "REVIEW",
        "promo_demand_source_quality": "HIGH",
        "promo_start_soh_source_quality": "HIGH",
        "basket_attachment_source_quality": "HIGH",
        "calibration_eligible_flag": "YES",
        "promo_demand_release_ready_flag": "NO",
        "constraint_block_flag": "NO",
        "unsafe_flag": "NO",
        "actual_units_sold_promo": 18.0,
        "final_governed_action_label": "REVIEW",
        "final_governed_order_units": 5.0,
        "promo_exit_success_flag": "YES",
        "distance_to_optimal_improvement": 1.0,
        "leftover_units_estimate": 0.0,
        "simulated_missed_demand_units": 4.0,
        "regime_adjusted_decision_value": 35.0,
    }
    base.update(overrides)
    return base


def _synthetic_frame(n: int = 40) -> pd.DataFrame:
    rows = []
    for i in range(n):
        row = _synthetic_row(
            sku_number=str(100 + i),
            current_soh=float(i % 5),
            promo_convexity_score=float(10 + (i % 50)),
            economic_net_value_score=float(5 + i),
            actual_units_sold_promo=float(8 + (i % 10)),
            current_stock_position_label=["UNDERSTOCKED", "OVERSTOCKED", "OPTIMAL"][i % 3],
            promo_demand_source_quality="HIGH" if i % 7 else "UNSAFE",
            feature_basket_attach_rate=UNKNOWN if i % 11 == 0 else 0.3,
        )
        rows.append(row)
    return pd.DataFrame(rows)


class TestBrainTrainingFrame(unittest.TestCase):
    def test_all_feature_families_present(self) -> None:
        frame = build_brain_training_frame(_synthetic_frame(5))
        for family, cols in FEATURE_FAMILIES.items():
            for col in cols:
                self.assertIn(col, frame.columns, f"missing {col} in family {family}")

    def test_no_nan_numeric_outputs(self) -> None:
        frame = build_brain_training_frame(_synthetic_frame(10))
        numeric_cols = [c for cols in FEATURE_FAMILIES.values() for c in cols if c not in {
            "recent_momentum_regime", "sku_demand_regime", "current_stock_position_label",
            "stock_position_regime", "mission_sku_flag", "long_tail_sku_flag", "long_tail_mission_sku_flag",
            "supplier_number_resolved", "supplier_replenishment_regime", "replenishment_reliability",
            "store_sales_regime", "customer_loyalty_regime", "customer_price_sensitivity_regime",
            "customer_basket_trust_regime", "promo_discount_regime", "promo_convexity_regime",
            "cash_efficiency_regime", "decision_triage_class", "promo_demand_source_quality",
            "promo_start_soh_source_quality", "basket_attachment_source_quality",
            "calibration_eligible_flag", "promo_demand_release_ready_flag", "constraint_block_flag", "unsafe_flag",
        } and not c.startswith("feature_")]
        for col in numeric_cols:
            self.assertFalse(frame[col].isna().any(), f"NaN in {col}")

    def test_unknown_labels_preserved(self) -> None:
        frame = build_brain_training_frame(pd.DataFrame([_synthetic_row(feature_basket_attach_rate=UNKNOWN)]))
        self.assertEqual(str(frame["feature_basket_attach_rate"].iloc[0]), UNKNOWN)

    def test_target_columns_created(self) -> None:
        frame = build_brain_training_frame(_synthetic_frame(3))
        for col in TARGET_COLUMNS:
            self.assertIn(col, frame.columns, col)

    def test_unsafe_rows_blocked_target(self) -> None:
        frame = build_brain_training_frame(pd.DataFrame([_synthetic_row(promo_demand_source_quality="UNSAFE")]))
        self.assertEqual(frame["target_optimal_action_label"].iloc[0], "BLOCKED_UNSAFE")


class TestBrainModels(unittest.TestCase):
    def test_train_returns_expected_keys(self) -> None:
        training = build_brain_training_frame(_synthetic_frame(50))
        artifact = train_brain_value_models(training)
        self.assertIn("uplift_model", artifact["models"])
        self.assertIn("economic_value_model", artifact["models"])
        self.assertIn("stock_exit_model", artifact["models"])
        self.assertIn("action_classifier", artifact["models"])

    def test_scoring_adds_brain_fields(self) -> None:
        raw = _synthetic_frame(50)
        scored = apply_brain_feature_learning(raw)
        for col in BRAIN_OUTPUT_COLUMNS:
            self.assertIn(col, scored.columns, col)

    def test_models_run_on_small_data(self) -> None:
        artifact = train_brain_value_models(build_brain_training_frame(_synthetic_frame(25)))
        scored = score_brain_value_models(_synthetic_frame(5), artifact)
        self.assertGreater(len(scored), 0)

    def test_fallback_when_sklearn_unavailable(self) -> None:
        with mock.patch("models.promotions.promo_brain_feature_learning._try_import_sklearn", return_value=(None, None, None)):
            artifact = train_brain_value_models(build_brain_training_frame(_synthetic_frame(20)))
            self.assertFalse(artifact["sklearn_available"])
            scored = score_brain_value_models(_synthetic_frame(5), artifact)
            self.assertIn("brain_learning_status", scored.columns)

    def test_failed_baseline_marks_experimental(self) -> None:
        artifact = {
            "models": {},
            "used_features": [],
            "metrics": {
                "uplift_model": {"pass_fail": "FAIL"},
                "economic_value_model": {"pass_fail": "FAIL"},
                "stock_exit_model": {"pass_fail": "FAIL"},
                "action_classifier": {"pass_fail": "FAIL"},
            },
            "sklearn_available": True,
            "x_columns": [],
        }
        scored = score_brain_value_models(_synthetic_frame(3), artifact)
        self.assertTrue((scored["brain_learning_status"] == "EXPERIMENTAL_FAILED_BASELINE").all())


class TestPatternDiscovery(unittest.TestCase):
    def test_long_tail_basket_convexity_pattern(self) -> None:
        scored = apply_brain_feature_learning(pd.DataFrame([_synthetic_row(
            long_tail_mission_sku_flag="YES",
            economic_net_value_score=10.0,
            current_stock_position_label="OPTIMAL",
            current_soh=5.0,
            promo_convexity_score=20.0,
        )]))
        self.assertIn(scored["alpha_pattern_id"].iloc[0], {
            "LONG_TAIL_BASKET_CONVEXITY", "REGIME_SHIFT_OPPORTUNITY",
        })

    def test_overstock_cash_release_pattern(self) -> None:
        scored = apply_brain_feature_learning(pd.DataFrame([_synthetic_row(
            current_stock_position_label="OVERSTOCKED",
            overstock_cash_release_value=50.0,
            promo_convexity_score=5.0,
            expected_promo_uplift_units=0.0,
        )]))
        self.assertEqual(scored["alpha_pattern_id"].iloc[0], "OVERSTOCK_CASH_RELEASE")

    def test_understocked_high_convexity_pattern(self) -> None:
        scored = apply_brain_feature_learning(pd.DataFrame([_synthetic_row(
            current_stock_position_label="UNDERSTOCKED",
            promo_convexity_score=50.0,
            long_tail_sku_flag="NO",
            current_soh=5.0,
        )]))
        self.assertEqual(scored["alpha_pattern_id"].iloc[0], "UNDERSTOCKED_HIGH_CONVEXITY")

    def test_unknown_data_pattern(self) -> None:
        scored = apply_brain_feature_learning(pd.DataFrame([_synthetic_row(
            feature_basket_attach_rate=UNKNOWN,
            promo_demand_source_quality="HIGH",
        )]))
        self.assertEqual(scored["alpha_pattern_id"].iloc[0], "UNKNOWN_DATA_DO_NOT_LEARN")

    def test_alpha_fields_populated(self) -> None:
        scored = apply_brain_feature_learning(_synthetic_frame(5))
        for col in ("alpha_pattern_id", "alpha_pattern_label", "alpha_pattern_description"):
            self.assertTrue(scored[col].astype(str).str.len().gt(0).all())


class TestGovernance(unittest.TestCase):
    def test_brain_does_not_overwrite_governed_action(self) -> None:
        raw = _synthetic_frame(10)
        raw["final_governed_action_label"] = "HOLD"
        scored = apply_brain_feature_learning(raw)
        self.assertTrue((scored["final_governed_action_label"] == "HOLD").all())

    def test_no_auto_order_created(self) -> None:
        raw = _synthetic_frame(5)
        before_units = raw["final_governed_order_units"].copy()
        scored = apply_brain_feature_learning(raw)
        pd.testing.assert_series_equal(scored["final_governed_order_units"], before_units)

    def test_unsafe_rows_remain_blocked(self) -> None:
        frame = build_brain_training_frame(pd.DataFrame([_synthetic_row(promo_demand_source_quality="UNSAFE")]))
        self.assertEqual(frame["target_optimal_action_label"].iloc[0], "BLOCKED_UNSAFE")
        self.assertIn("BLOCKED_UNSAFE", ACTION_LABELS)


class TestDiagnostics(unittest.TestCase):
    def test_required_diagnostic_files_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase5q_diagnostics(frame=_synthetic_frame(60), diagnostics_dir=diag)
            expected = [
                "phase5q01_training_frame_schema.csv",
                "phase5q01_model_performance_summary.csv",
                "phase5q01_feature_importance.csv",
                "phase5q01_alpha_pattern_discovery.csv",
                "phase5q01_top_brain_opportunities.csv",
                "phase5q01_brain_vs_current_action_review.csv",
                "phase5q01_release_gate.csv",
            ]
            for name in expected:
                self.assertTrue((diag / name).exists(), name)
            self.assertEqual(result["customer_release_recommendation"], "NO_RELEASE")


if __name__ == "__main__":
    unittest.main()
