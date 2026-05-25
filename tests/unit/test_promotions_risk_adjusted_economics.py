from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.risk_adjusted_economics import (  # noqa: E402
    CAPITAL_AT_RISK_MAX_FACTOR,
    CAPITAL_AT_RISK_MIN_FACTOR,
    OUTPUT_COLUMNS,
    RiskAdjustedEconomicsContractError,
    compute_risk_adjusted_economics,
)


def _frame(**overrides: object) -> pd.DataFrame:
    base = {
        "final_confidence_score": 0.7,
        "predicted_units_total_promo": 100.0,
        "baseline_expected_units": 60.0,
        "promo_gm_unit": 4.0,
        "unit_cost": 5.0,
        "recommended_order_units": 120.0,
        "expected_leftover_units": 20.0,
    }
    base.update(overrides)
    return pd.DataFrame([base])


class RiskAdjustedEconomicsContractTests(unittest.TestCase):
    def test_missing_required_column_raises(self) -> None:
        frame = _frame()
        del frame["unit_cost"]
        with self.assertRaises(RiskAdjustedEconomicsContractError):
            compute_risk_adjusted_economics(frame)

    def test_all_governed_columns_emitted(self) -> None:
        result = compute_risk_adjusted_economics(_frame())
        for column_name in OUTPUT_COLUMNS:
            self.assertIn(column_name, result.frame.columns)


class RiskAdjustedEconomicsValueAndMonotonicityTests(unittest.TestCase):
    def test_model_confidence_percent_is_int_zero_to_hundred(self) -> None:
        for raw in (0.0, 0.123, 0.5, 0.999, 1.0, 1.5, -0.2):
            result = compute_risk_adjusted_economics(_frame(final_confidence_score=raw))
            value = result.frame.iloc[0]["model_confidence_percent"]
            self.assertIsInstance(int(value), int)
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)

    def test_lower_confidence_increases_capital_at_risk(self) -> None:
        # Hold every other input fixed; sweep confidence downwards.
        confidences = [0.99, 0.7, 0.4, 0.1]
        risks = []
        for conf in confidences:
            result = compute_risk_adjusted_economics(_frame(final_confidence_score=conf))
            risks.append(float(result.frame.iloc[0]["capital_at_risk_adjusted_dollars"]))
        # Strictly non-decreasing as confidence falls.
        for previous, current in zip(risks, risks[1:]):
            self.assertLessEqual(previous, current + 1e-9)
        self.assertLess(risks[0], risks[-1])

    def test_higher_incremental_margin_increases_risk_reward_ratio(self) -> None:
        # Hold confidence (and therefore capital_at_risk) fixed; raise predicted units.
        ratios = []
        for predicted in (60.0, 80.0, 100.0, 200.0):
            result = compute_risk_adjusted_economics(
                _frame(final_confidence_score=0.7, predicted_units_total_promo=predicted)
            )
            ratios.append(float(result.frame.iloc[0]["retail_risk_reward_ratio"]))
        for previous, current in zip(ratios, ratios[1:]):
            self.assertLessEqual(previous, current + 1e-9)
        self.assertLess(ratios[0], ratios[-1])

    def test_negative_lift_floors_incremental_units_at_zero(self) -> None:
        result = compute_risk_adjusted_economics(
            _frame(predicted_units_total_promo=10.0, baseline_expected_units=80.0)
        )
        self.assertEqual(result.frame.iloc[0]["expected_incremental_units"], 0.0)
        self.assertEqual(result.frame.iloc[0]["expected_incremental_margin_dollars"], 0.0)
        self.assertEqual(result.frame.iloc[0]["retail_risk_reward_ratio"], 0.0)

    def test_zero_exposure_does_not_divide_by_zero(self) -> None:
        result = compute_risk_adjusted_economics(
            _frame(unit_cost=0.0, recommended_order_units=0.0, expected_leftover_units=0.0)
        )
        # Capital at risk is 0; ratio uses floor denominator -> finite.
        self.assertEqual(result.frame.iloc[0]["capital_at_risk_adjusted_dollars"], 0.0)
        ratio = float(result.frame.iloc[0]["retail_risk_reward_ratio"])
        self.assertFalse(pd.isna(ratio))

    def test_risk_factor_bounds_respected(self) -> None:
        # Healthy + low overstock + 100% confidence -> factor floored at MIN.
        result = compute_risk_adjusted_economics(_frame(final_confidence_score=1.0))
        floored_risk = float(result.frame.iloc[0]["capital_at_risk_adjusted_dollars"])
        exposure = max(120.0 * 5.0, 20.0 * 5.0)
        self.assertAlmostEqual(floored_risk, round(exposure * CAPITAL_AT_RISK_MIN_FACTOR, 2), places=2)
        # 0% confidence + sparse evidence + high overstock -> factor capped at MAX.
        capped_frame = _frame(final_confidence_score=0.0)
        capped_frame["demand_evidence_class"] = "low_nonzero_demand"
        capped_frame["overstock_risk_band"] = "HIGH"
        result = compute_risk_adjusted_economics(capped_frame)
        capped_risk = float(result.frame.iloc[0]["capital_at_risk_adjusted_dollars"])
        self.assertAlmostEqual(capped_risk, round(exposure * CAPITAL_AT_RISK_MAX_FACTOR, 2), places=2)


if __name__ == "__main__":
    unittest.main()
