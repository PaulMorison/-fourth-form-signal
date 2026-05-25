from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from surfaces.promotions.reporting.demand_evidence_classifier import (
    DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE,
    DEMAND_EVIDENCE_CLASS_COLD_START,
    DEMAND_EVIDENCE_CLASS_LOW_NONZERO,
    DEMAND_EVIDENCE_CLASS_TRUE_ZERO,
    classify_demand_evidence_row,
)


class DemandEvidenceClassifierTests(unittest.TestCase):
    def test_true_zero_demand_classifies_as_excluded_true_zero(self) -> None:
        result = classify_demand_evidence_row(
            {
                "predicted_units_total_promo": 0.0,
                "forecast_zero_demand_classification": "TRUE_ZERO_DEMAND",
            }
        )
        self.assertEqual(result.demand_evidence_class, DEMAND_EVIDENCE_CLASS_TRUE_ZERO)
        self.assertEqual(result.publish_eligibility_reason, "excluded_true_zero_demand")
        self.assertEqual(result.eligible_for_publish, 0)

    def test_cold_start_new_line_is_separate_from_true_zero(self) -> None:
        result = classify_demand_evidence_row(
            {
                "predicted_units_total_promo": 0.0,
                "forecast_zero_demand_classification": "COHORT_SOURCE_TOO_FLAT",
                "promotion_name": "New Line Launch",
                "raw_history_units": 0.0,
                "raw_predicted_units_sold": 0.0,
                "raw_demand_reference_units": 0.0,
                "raw_baseline_expected_units": 0.0,
            }
        )
        self.assertEqual(result.demand_evidence_class, DEMAND_EVIDENCE_CLASS_COLD_START)
        self.assertEqual(result.cold_start_flag, 1)
        self.assertEqual(result.requires_review, 1)

    def test_low_nonzero_demand_stays_publish_eligible(self) -> None:
        result = classify_demand_evidence_row(
            {
                "predicted_units_total_promo": 0.6,
                "forecast_zero_demand_classification": "LOW_NONZERO_DEMAND",
            }
        )
        self.assertEqual(result.demand_evidence_class, DEMAND_EVIDENCE_CLASS_LOW_NONZERO)
        self.assertEqual(result.publish_eligibility_reason, "eligible_low_nonzero_demand")
        self.assertEqual(result.eligible_for_publish, 1)

    def test_artificial_collapse_requires_review(self) -> None:
        result = classify_demand_evidence_row(
            {
                "predicted_units_total_promo": 0.0,
                "forecast_zero_demand_classification": "COLLAPSED_FORECAST_REQUIRES_REVIEW",
                "forecast_collapse_requires_review_flag": 1,
            }
        )
        self.assertEqual(result.demand_evidence_class, DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE)
        self.assertEqual(result.requires_review, 1)
        self.assertEqual(result.eligible_for_publish, 0)

    def test_stage11_to_stage12_classification_continuity(self) -> None:
        stage11_like = classify_demand_evidence_row(
            {
                "predicted_units_total_promo": 0.8,
                "forecast_zero_demand_classification": "LOW_NONZERO_DEMAND",
                "promotion_header_key": "PROMO_A",
            }
        )
        stage12_like = classify_demand_evidence_row(
            {
                "forecast_promo_units": 0.8,
                "forecast_zero_demand_classification": "LOW_NONZERO_DEMAND",
                "promotion_header_key": "PROMO_A",
            }
        )
        self.assertEqual(stage11_like.demand_evidence_class, stage12_like.demand_evidence_class)
        self.assertEqual(stage11_like.publish_eligibility_reason, stage12_like.publish_eligibility_reason)


if __name__ == "__main__":
    unittest.main()
