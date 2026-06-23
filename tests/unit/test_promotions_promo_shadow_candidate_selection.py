from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_shadow_candidate_selection import (  # noqa: E402
    OUTPUT_COLUMNS,
    apply_shadow_candidate_selection,
    build_shadow_candidate_selection_frame,
    write_phase5s_diagnostics,
)
from tests.unit.test_promotions_promo_brain_feature_learning import (  # noqa: E402
    _synthetic_frame,
    _synthetic_row,
)


def _eligible_row(**overrides) -> dict:
    base = _synthetic_row(
        promo_demand_source_quality="HIGH",
        promo_start_soh_source_quality="HIGH",
        unsafe_flag="NO",
        constraint_block_flag="NO",
        basket_attachment_used_real_transactions_flag="YES",
        basket_attachment_source_quality="HIGH",
        brain_validation_status="LEAK_SAFE_VALIDATED",
        brain_value_survives_leakage_control_flag="YES",
        brain_validated_expected_value=35.0,
        brain_validated_action_label="CONTROLLED_BUY",
        economic_net_value_score=30.0,
        regime_historical_bias_pct=-5.0,
        regime_historical_wape=0.2,
        regime_error_profile_row_count=50,
        cash_tied_above_optimal_cost=10.0,
        final_governed_order_units=3.0,
        final_governed_action_label="REVIEW",
    )
    base.update(overrides)
    return base


class TestShadowEligibility(unittest.TestCase):
    def test_unsafe_rows_rejected(self) -> None:
        out = build_shadow_candidate_selection_frame(pd.DataFrame([_eligible_row(promo_demand_source_quality="UNSAFE", unsafe_flag="YES")]))
        self.assertEqual(out["shadow_candidate_flag"].iloc[0], "NO")
        self.assertEqual(out["shadow_candidate_class"].iloc[0], "NOT_SHADOW_SAFE")

    def test_unknown_soh_with_buy_rejected(self) -> None:
        out = build_shadow_candidate_selection_frame(pd.DataFrame([_eligible_row(
            promo_start_soh_source_quality="UNKNOWN",
            final_governed_order_units=5.0,
        )]))
        self.assertEqual(out["shadow_candidate_flag"].iloc[0], "NO")

    def test_bias_controlled_segment_can_become_candidate(self) -> None:
        out = build_shadow_candidate_selection_frame(pd.DataFrame([_eligible_row(regime_historical_bias_pct=-8.0)]))
        self.assertEqual(out["segment_bias_control_status"].iloc[0], "BIAS_CONTROLLED")
        self.assertEqual(out["shadow_candidate_flag"].iloc[0], "YES")

    def test_dangerous_bias_segment_blocked(self) -> None:
        out = build_shadow_candidate_selection_frame(pd.DataFrame([_eligible_row(regime_historical_bias_pct=-30.0)]))
        self.assertEqual(out["segment_bias_control_status"].iloc[0], "BIAS_DANGEROUS_BLOCK")
        self.assertEqual(out["shadow_candidate_flag"].iloc[0], "NO")

    def test_mission_sku_with_basket_can_become_candidate(self) -> None:
        out = build_shadow_candidate_selection_frame(pd.DataFrame([_eligible_row(
            mission_sku_score=55.0,
            long_tail_mission_sku_flag="YES",
            feature_basket_3plus_attach_rate=0.4,
        )]))
        self.assertEqual(out["shadow_candidate_flag"].iloc[0], "YES")
        self.assertGreater(float(out["shadow_expected_learning_value"].iloc[0]), 0)

    def test_overstock_run_down_candidate(self) -> None:
        frame = pd.DataFrame([_eligible_row(
            current_stock_position_label="OVERSTOCKED",
            promo_convexity_score=10.0,
            brain_validated_action_label="NO_BUY_RUN_DOWN",
        )])
        out = build_shadow_candidate_selection_frame(frame)
        self.assertEqual(out["shadow_candidate_flag"].iloc[0], "YES")

    def test_understocked_convexity_candidate(self) -> None:
        out = build_shadow_candidate_selection_frame(pd.DataFrame([_eligible_row(
            current_stock_position_label="UNDERSTOCKED",
            promo_convexity_score=50.0,
        )]))
        self.assertEqual(out["shadow_candidate_flag"].iloc[0], "YES")
        self.assertGreater(float(out["shadow_expected_learning_value"].iloc[0]), 20.0)


class TestShadowScoring(unittest.TestCase):
    def test_learning_value_positive_for_edge_cases(self) -> None:
        out = build_shadow_candidate_selection_frame(pd.DataFrame([_eligible_row(
            average_daily_units=2.0,
            long_tail_sku_flag="YES",
            mission_sku_score=50.0,
        )]))
        self.assertGreater(float(out["shadow_expected_learning_value"].iloc[0]), 15.0)

    def test_action_difference_detected(self) -> None:
        out = build_shadow_candidate_selection_frame(pd.DataFrame([_eligible_row(
            final_governed_action_label="HOLD",
            brain_validated_action_label="CONTROLLED_BUY",
        )]))
        self.assertEqual(out["action_difference_flag"].iloc[0], "YES")

    def test_top_50_ranking(self) -> None:
        rows = [_eligible_row(sku_number=str(100 + i), economic_net_value_score=float(10 + i)) for i in range(60)]
        out = build_shadow_candidate_selection_frame(pd.DataFrame(rows))
        top50 = out[out["shadow_candidate_class"].eq("SHADOW_TOP_50_CANDIDATE")]
        self.assertEqual(len(top50), 50)
        self.assertTrue(top50["shadow_candidate_rank"].is_monotonic_increasing)


class TestGovernance(unittest.TestCase):
    def test_governed_actions_not_overwritten(self) -> None:
        raw = _synthetic_frame(10)
        raw["final_governed_action_label"] = "HOLD"
        out = apply_shadow_candidate_selection(raw)
        self.assertTrue((out["final_governed_action_label"] == "HOLD").all())

    def test_output_columns_present(self) -> None:
        out = apply_shadow_candidate_selection(_synthetic_frame(5))
        for col in OUTPUT_COLUMNS:
            self.assertIn(col, out.columns)


class TestDiagnostics(unittest.TestCase):
    def test_diagnostics_written(self) -> None:
        rows = [_eligible_row(sku_number=str(100 + i), promotion_name=f"P{i % 5}") for i in range(80)]
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase5s_diagnostics(frame=pd.DataFrame(rows), diagnostics_dir=diag)
            for name in (
                "phase5s01_shadow_candidate_summary.csv",
                "phase5s01_shadow_top_50_candidates.csv",
                "phase5s01_shadow_candidate_rejection_reasons.csv",
                "phase5s01_bias_controlled_segment_review.csv",
                "phase5s01_shadow_trial_gate.csv",
            ):
                self.assertTrue((diag / name).exists(), name)
            self.assertEqual(result["customer_release_recommendation"], "NO_RELEASE")


if __name__ == "__main__":
    unittest.main()
