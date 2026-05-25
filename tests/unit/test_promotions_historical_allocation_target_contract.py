from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import _build_target_contract_artifacts  # noqa: E402
from state.promotions.feature_engineering.targets.ft_target_historical_allocation import (  # noqa: E402
    HistoricalAllocationTargetEvidenceError,
    apply_ft_target_historical_allocation,
)


def _target_contract_row(name: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "promotion_row_key": name,
        "store_number": "1",
        "sku_number": "100",
        "split_name": "validation",
        "stock_basis_units": 8.0,
        "demand_reference_units": 5.0,
        "actual_units_sold": 5.0,
        "unit_cost": 2.0,
        "raw_predicted_units_total_promo": 6.0,
        "calibrated_predicted_units_total_promo": 6.0,
        "policy_adjusted_predicted_units_total_promo": 5.5,
        "actual_overallocation_flag": 1.0,
        "replay_measurement_eligible_flag": 1.0,
        "replay_exclusion_reason": "eligible",
        "historical_allocated_units": 10.0,
        "realised_units_sold_promo": 5.0,
        "replay_unit_cost": 2.0,
        "target_historical_allocation_units": 10.0,
        "target_historical_replay_excess_units": 5.0,
        "target_historical_replay_excess_capital": 10.0,
        "target_historical_overallocation_flag": 1.0,
        "target_historical_allocation_target_valid_flag": 1.0,
    }
    row.update(overrides)
    return row


class PromotionHistoricalAllocationTargetContractTests(unittest.TestCase):
    def test_historical_allocation_target_formulas_use_explicit_allocation_and_realised_units(self) -> None:
        frame = pd.DataFrame(
            {
                "pl_allocation_qty": [10.0, 4.0],
                "actual_units_sold_promo": [6.0, 7.0],
                "effective_cost_per_unit": [2.5, 3.0],
                "stock_basis_units": [999.0, 999.0],
            }
        )

        result = apply_ft_target_historical_allocation(frame)

        self.assertEqual(float(result.loc[0, "target_historical_allocation_units"]), 10.0)
        self.assertEqual(float(result.loc[0, "target_historical_replay_excess_units"]), 4.0)
        self.assertEqual(float(result.loc[0, "target_historical_replay_excess_capital"]), 10.0)
        self.assertEqual(int(result.loc[0, "target_historical_overallocation_flag"]), 1)
        self.assertEqual(float(result.loc[1, "target_historical_replay_excess_units"]), 0.0)
        self.assertEqual(int(result.loc[1, "target_historical_overallocation_flag"]), 0)

    def test_historical_allocation_target_marks_missing_row_evidence_without_zero_filling(self) -> None:
        frame = pd.DataFrame(
            {
                "pl_allocation_qty": [pd.NA, 8.0, 8.0],
                "actual_units_sold_promo": [4.0, pd.NA, 4.0],
                "effective_cost_per_unit": [2.0, 2.0, pd.NA],
            }
        )

        result = apply_ft_target_historical_allocation(frame)

        self.assertTrue(pd.isna(result.loc[0, "target_historical_allocation_units"]))
        self.assertTrue(pd.isna(result.loc[1, "target_historical_replay_excess_units"]))
        self.assertTrue(pd.isna(result.loc[2, "target_historical_replay_excess_capital"]))
        self.assertEqual(int(result.loc[0, "target_historical_allocation_missing_flag"]), 1)
        self.assertEqual(int(result.loc[1, "target_historical_realised_promo_units_missing_flag"]), 1)
        self.assertEqual(int(result.loc[2, "target_historical_unit_cost_missing_flag"]), 1)
        self.assertEqual(result.loc[0, "target_historical_allocation_exclusion_reason"], "missing_historical_allocation_evidence")
        self.assertEqual(result.loc[1, "target_historical_allocation_exclusion_reason"], "missing_realised_promo_evidence")
        self.assertEqual(result.loc[2, "target_historical_allocation_exclusion_reason"], "missing_historical_unit_cost_evidence")

    def test_historical_allocation_target_fails_loud_when_explicit_source_columns_are_absent(self) -> None:
        frame = pd.DataFrame(
            {
                "stock_basis_units": [10.0],
                "actual_units_sold_promo": [5.0],
                "effective_cost_per_unit": [2.0],
            }
        )

        with self.assertRaises(HistoricalAllocationTargetEvidenceError):
            apply_ft_target_historical_allocation(frame)

    def test_dual_contract_row_diagnostics_classify_divergence_and_keep_policy_paused(self) -> None:
        rows = pd.DataFrame(
            [
                _target_contract_row(
                    "stock-basis",
                    stock_basis_units=20.0,
                    historical_allocated_units=10.0,
                    target_historical_allocation_units=10.0,
                    actual_units_sold=5.0,
                    realised_units_sold_promo=5.0,
                    target_historical_replay_excess_units=5.0,
                    target_historical_replay_excess_capital=10.0,
                ),
                _target_contract_row(
                    "realised-promo",
                    stock_basis_units=10.0,
                    historical_allocated_units=10.0,
                    actual_units_sold=10.0,
                    realised_units_sold_promo=4.0,
                    target_historical_replay_excess_units=6.0,
                    target_historical_replay_excess_capital=12.0,
                    actual_overallocation_flag=0.0,
                ),
            ]
        )

        artifacts = _build_target_contract_artifacts(rows)
        diagnostics = artifacts["row_diagnostics_frame"]
        summary_payload = artifacts["summary_payload"]

        self.assertEqual(
            diagnostics["divergence_driver"].astype(str).tolist(),
            ["stock_basis_proxy_mismatch", "realised_promo_units_mismatch"],
        )
        self.assertIn("current_trainer_target_value", diagnostics.columns)
        self.assertIn("historical_allocation_target_value", diagnostics.columns)
        self.assertIn("target_contract_signed_difference", diagnostics.columns)
        self.assertIn("divergence_severity_bucket", diagnostics.columns)
        self.assertEqual(summary_payload["valid_row_counts"]["valid_under_both_contracts"], 2)
        self.assertTrue(summary_payload["policy_pause_conclusion"]["policy_remains_paused"])
        self.assertFalse(summary_payload["policy_pause_conclusion"]["policy_is_dominant_bottleneck"])

    def test_target_promotion_decision_stays_diagnostics_only_when_evidence_is_diffuse(self) -> None:
        rows = pd.DataFrame(
            [
                _target_contract_row(
                    f"stock-{index}",
                    stock_basis_units=20.0,
                    historical_allocated_units=10.0,
                    target_historical_allocation_units=10.0,
                    actual_units_sold=5.0,
                    realised_units_sold_promo=5.0,
                    target_historical_replay_excess_units=5.0,
                    target_historical_replay_excess_capital=10.0,
                )
                for index in range(4)
            ]
        )

        artifacts = _build_target_contract_artifacts(rows)
        decision_payload = artifacts["next_target_promotion_decision_payload"]

        self.assertEqual(decision_payload["decision"], "diagnostics_only")
        self.assertTrue(decision_payload["should_historical_allocation_target_refinement_remain_diagnostics_only"])
        self.assertFalse(decision_payload["should_historical_allocation_target_refinement_replace_current_trainer_contract_now"])


if __name__ == "__main__":
    unittest.main()