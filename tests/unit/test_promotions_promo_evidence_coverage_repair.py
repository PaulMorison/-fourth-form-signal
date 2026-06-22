from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_evidence_coverage_repair import (  # noqa: E402
    build_unsafe_reason_breakdown,
    classify_unsafe_reason,
    discount_band_from_percent,
    evaluate_limited_release_gate,
    recalculate_evidence_quality,
    repair_baseline_features,
    repair_discount_depth_features,
    repair_evidence_coverage,
    repair_promo_history_features,
)
from models.promotions.promo_demand_calibration import build_calibrated_backtest_summary


def _history_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": [772, 772, 772, 772],
            "sku_number": ["100", "100", "100", "200"],
            "promotion_start_date": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-02-01"],
            "promotion_end_date": ["2024-01-07", "2024-02-07", "2024-03-07", "2024-02-07"],
            "promo_days": [7, 7, 7, 7],
            "discount_percent": [5.0, 20.0, 20.0, 15.0],
            "actual_units_sold_promo": [7.0, 14.0, 21.0, 0.0],
            "department": ["A", "A", "A", "B"],
            "category": ["c1", "c1", "c1", "c2"],
            "promo_demand_source_quality": ["UNSAFE", "UNSAFE", "UNSAFE", "UNSAFE"],
            "promo_demand_release_ready_flag": ["NO", "NO", "NO", "NO"],
            "model_expected_units_total_promo": [1.0, 2.0, 3.0, 0.0],
            "stockout_suspected_flag": [0, 0, 1, 0],
            "leftover_units_estimate": [0.0, 0.0, 0.0, 0.0],
        }
    )


class PromoEvidenceCoverageRepairTests(unittest.TestCase):
    def test_unsafe_reason_classification(self) -> None:
        frame = _history_frame()
        repaired = repair_baseline_features(frame)
        repaired = repair_promo_history_features(repaired)
        repaired = repair_discount_depth_features(repaired)
        row_stockout = repaired.iloc[2]
        row_zero = repaired.iloc[3]
        self.assertEqual(classify_unsafe_reason(row_stockout), "actuals_censored_by_stockout")
        self.assertIn(
            classify_unsafe_reason(row_zero),
            {"missing_baseline_daily_units", "actuals_quality_low", "missing_same_discount_history", "legacy_placeholder_detected"},
        )

    def test_baseline_repair_excludes_current_and_future(self) -> None:
        repaired = repair_baseline_features(_history_frame())
        third = repaired[(repaired["sku_number"] == "100")].sort_values("promotion_start_date").iloc[2]
        self.assertGreater(float(third["baseline_daily_units_selected"]), 0.0)
        self.assertEqual(str(third["baseline_units_leakage_safe_flag"]), "YES")
        self.assertFalse(repaired[["baseline_daily_units_28d", "baseline_daily_units_56d", "baseline_daily_units_90d"]].isna().any().any())

    def test_promo_history_uses_prior_promos_only(self) -> None:
        repaired = repair_promo_history_features(_history_frame())
        third = repaired[(repaired["sku_number"] == "100")].sort_values("promotion_start_date").iloc[2]
        first = repaired[(repaired["sku_number"] == "100")].sort_values("promotion_start_date").iloc[0]
        self.assertEqual(int(first["same_discount_history_event_count"]), 0)
        self.assertGreaterEqual(int(third["same_discount_history_event_count"]), 1)

    def test_same_or_better_discount_logic(self) -> None:
        bands = discount_band_from_percent(pd.Series([5.0, 25.0]))
        self.assertEqual(bands.iloc[0], "0-10")
        self.assertEqual(bands.iloc[1], "20-30")

    def test_discount_repair_and_missing_not_zero_quality(self) -> None:
        frame = _history_frame()
        frame.loc[0, "discount_percent"] = 0.0
        repaired = repair_discount_depth_features(frame)
        self.assertAlmostEqual(float(repaired.loc[1, "discount_depth_repaired"]), 0.20, places=2)
        self.assertEqual(repaired.loc[0, "discount_depth_quality"], "UNSAFE")

    def test_evidence_quality_bounds_and_rules(self) -> None:
        repaired = repair_evidence_coverage(_history_frame())
        self.assertTrue(repaired["evidence_coverage_score"].between(0, 100).all())
        invalid = repaired.copy()
        invalid["promotion_end_date"] = "2023-01-01"
        invalid = recalculate_evidence_quality(invalid)
        self.assertTrue((invalid["promo_demand_source_quality_repaired"] == "UNSAFE").any())
        censored = repaired[repaired["demand_observation_quality"].eq("CENSORED")]
        if not censored.empty:
            self.assertTrue((censored["promo_demand_release_ready_flag_repaired"] == "NO").all())

    def test_repaired_gate_blocks_and_allows(self) -> None:
        summary = pd.DataFrame(
            [
                {"variant": "raw_model", "wape": 0.7, "bias_pct": -40.0, "estimated_net_value_proxy": 100.0},
                {"variant": "calibrated_model", "wape": 0.9, "bias_pct": -5.0, "estimated_net_value_proxy": 100.0},
                {"variant": "baseline", "wape": 0.8, "bias_pct": 0.0, "estimated_net_value_proxy": 0.0},
            ]
        )
        rec, blocker, _ = evaluate_limited_release_gate(summary, pd.DataFrame({"promo_demand_source_quality": ["HIGH"]}))
        self.assertEqual(rec, "NO_RELEASE")
        self.assertEqual(blocker, "calibrated_wape_not_better_than_baseline")

        scored = pd.DataFrame(
            {
                "promo_demand_source_quality": ["HIGH", "MEDIUM"],
                "calibration_release_ready_flag": ["YES", "YES"],
                "calibration_quality": ["HIGH", "MEDIUM"],
                "model_expected_units_total_promo_calibrated": [2.0, 3.0],
            }
        )
        good = pd.DataFrame(
            [
                {"variant": "raw_model", "wape": 0.7, "bias_pct": -40.0, "estimated_net_value_proxy": 100.0},
                {"variant": "calibrated_model", "wape": 0.6, "bias_pct": -5.0, "estimated_net_value_proxy": 500.0},
                {"variant": "baseline", "wape": 0.8, "bias_pct": 0.0, "estimated_net_value_proxy": 0.0},
            ]
        )
        rec2, _, _ = evaluate_limited_release_gate(good, scored)
        self.assertEqual(rec2, "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        self.assertNotEqual(rec2, "CUSTOMER_RELEASE_READY")

    def test_unsafe_breakdown_counts(self) -> None:
        frame = _history_frame()
        frame = repair_discount_depth_features(repair_promo_history_features(repair_baseline_features(frame)))
        breakdown = build_unsafe_reason_breakdown(frame)
        self.assertFalse(breakdown.empty)
        self.assertIn("unsafe_primary_reason", breakdown.columns)


if __name__ == "__main__":
    unittest.main()
