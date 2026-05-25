from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.commercial_change_explainer import (  # noqa: E402
    ACTION_NO_ACTION_DUPLICATE,
    ACTION_PUBLISH_NOW,
    ACTION_REVIEW_NOW,
)
from runtime.promotions.commercial_outcome_attribution import (  # noqa: E402
    ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA,
    ATTRIBUTION_EXCLUDED_DUPLICATE_ONLY,
    ATTRIBUTION_EXCLUDED_REVIEW_ONLY,
    ATTRIBUTION_NOT_YET_MATURE,
    ATTRIBUTION_READY,
    EFFECTIVE_MODERATE,
    EFFECTIVE_STRONG,
    HARMFUL,
    INCONCLUSIVE,
    INEFFECTIVE,
    LEARNING_SIGNAL_NOT_READY,
    LEARNING_SIGNAL_STRONG,
    NEUTRAL,
    _validate_attribution_consistency,
    build_commercial_outcome_attribution_artifacts,
)


def _row(
    *,
    store_number: int,
    sku_number: int,
    start: str = "2024-09-01",
    end: str = "2024-09-07",
    recommendation: str = "ORDER",
    eligibility: str = "publishable",
    demand: str = "healthy_nonzero_demand",
    suggested_order_units: float = 10.0,
    actual_units_sold: float | None = None,
    expected_sales: float | None = None,
    actual_sales: float | None = None,
    expected_margin: float | None = None,
    actual_margin: float | None = None,
) -> dict[str, object]:
    return {
        "store_number": store_number,
        "sku_number": sku_number,
        "promotion_start_date": start,
        "promotion_end_date": end,
        "decision_recommendation": recommendation,
        "publish_eligibility_reason": eligibility,
        "demand_evidence_class": demand,
        "suggested_order_units": suggested_order_units,
        "actual_units_sold": actual_units_sold,
        "expected_sales": expected_sales,
        "actual_sales": actual_sales,
        "expected_margin": expected_margin,
        "actual_margin": actual_margin,
    }


def _explanation(
    *,
    store_number: int,
    sku_number: int,
    start: str = "2024-09-01",
    end: str = "2024-09-07",
    action: str = ACTION_PUBLISH_NOW,
    reason_code: str = "recommendation_changed_order_to_order",
) -> dict[str, object]:
    return {
        "store_number": str(store_number),
        "sku_number": str(sku_number),
        "promotion_start_date": start,
        "promotion_end_date": end,
        "operator_action_class": action,
        "row_change_reason_code": reason_code,
    }


class CommercialOutcomeAttributionTests(unittest.TestCase):
    def _build(self, rows: list[dict[str, object]], explanations: list[dict[str, object]], as_of_date: str = "2024-10-01"):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "current.csv"
            pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8")
            artifacts = build_commercial_outcome_attribution_artifacts(
                as_of_date=as_of_date,
                current_store_prediction_csv_path=str(csv_path),
                commercial_change_explanations=pd.DataFrame(explanations),
                current_freshness_class="FRESH_NEW_PUBLICATIONS_CREATED",
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
                duplicate_registry_skip_count=0,
            )
            return artifacts

    def test_published_row_strong_improvement_becomes_effective_strong(self) -> None:
        artifacts = self._build(
            rows=[
                _row(
                    store_number=1,
                    sku_number=100,
                    suggested_order_units=10,
                    actual_units_sold=18,
                    expected_sales=100,
                    actual_sales=180,
                    expected_margin=30,
                    actual_margin=70,
                )
            ],
            explanations=[_explanation(store_number=1, sku_number=100)],
        )
        row = artifacts.attribution.iloc[0]
        self.assertEqual(row["attribution_status"], ATTRIBUTION_READY)
        self.assertEqual(row["recommendation_effectiveness_class"], EFFECTIVE_STRONG)

    def test_published_row_weak_improvement_is_moderate_or_neutral(self) -> None:
        artifacts = self._build(
            rows=[
                _row(
                    store_number=1,
                    sku_number=101,
                    suggested_order_units=10,
                    actual_units_sold=11,
                    expected_sales=100,
                    actual_sales=105,
                    expected_margin=40,
                    actual_margin=41,
                )
            ],
            explanations=[_explanation(store_number=1, sku_number=101)],
        )
        cls = artifacts.attribution.iloc[0]["recommendation_effectiveness_class"]
        self.assertIn(cls, {EFFECTIVE_MODERATE, NEUTRAL})

    def test_published_row_poor_outcome_is_ineffective_or_harmful(self) -> None:
        artifacts = self._build(
            rows=[
                _row(
                    store_number=1,
                    sku_number=102,
                    suggested_order_units=12,
                    actual_units_sold=4,
                    expected_sales=150,
                    actual_sales=80,
                    expected_margin=60,
                    actual_margin=20,
                )
            ],
            explanations=[_explanation(store_number=1, sku_number=102)],
        )
        cls = artifacts.attribution.iloc[0]["recommendation_effectiveness_class"]
        self.assertIn(cls, {INEFFECTIVE, HARMFUL})

    def test_review_only_row_is_excluded(self) -> None:
        artifacts = self._build(
            rows=[_row(store_number=1, sku_number=103, eligibility="review_only")],
            explanations=[_explanation(store_number=1, sku_number=103, action=ACTION_REVIEW_NOW)],
        )
        row = artifacts.attribution.iloc[0]
        self.assertEqual(row["attribution_status"], ATTRIBUTION_EXCLUDED_REVIEW_ONLY)
        self.assertEqual(row["recommendation_effectiveness_class"], INCONCLUSIVE)

    def test_duplicate_only_row_is_excluded(self) -> None:
        artifacts = self._build(
            rows=[_row(store_number=1, sku_number=104)],
            explanations=[_explanation(store_number=1, sku_number=104, action=ACTION_NO_ACTION_DUPLICATE)],
        )
        row = artifacts.attribution.iloc[0]
        self.assertEqual(row["attribution_status"], ATTRIBUTION_EXCLUDED_DUPLICATE_ONLY)
        self.assertEqual(row["recommendation_effectiveness_class"], INCONCLUSIVE)

    def test_missing_downstream_data_is_blocked(self) -> None:
        artifacts = self._build(
            rows=[_row(store_number=1, sku_number=105, suggested_order_units=10)],
            explanations=[_explanation(store_number=1, sku_number=105)],
        )
        row = artifacts.attribution.iloc[0]
        self.assertEqual(row["attribution_status"], ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA)
        self.assertEqual(row["recommendation_effectiveness_class"], INCONCLUSIVE)

    def test_incomplete_window_is_not_yet_mature(self) -> None:
        artifacts = self._build(
            rows=[_row(store_number=1, sku_number=106, start="2024-10-01", end="2024-10-21")],
            explanations=[_explanation(store_number=1, sku_number=106, start="2024-10-01", end="2024-10-21")],
            as_of_date="2024-10-10",
        )
        row = artifacts.attribution.iloc[0]
        self.assertEqual(row["attribution_status"], ATTRIBUTION_NOT_YET_MATURE)
        self.assertFalse(bool(row["attribution_window_complete_flag"]))

    def test_effectiveness_summary_reconciles_exactly(self) -> None:
        artifacts = self._build(
            rows=[
                _row(
                    store_number=1,
                    sku_number=107,
                    suggested_order_units=10,
                    actual_units_sold=18,
                    expected_sales=100,
                    actual_sales=180,
                    expected_margin=30,
                    actual_margin=70,
                ),
                _row(store_number=1, sku_number=108, eligibility="review_only"),
            ],
            explanations=[
                _explanation(store_number=1, sku_number=107, action=ACTION_PUBLISH_NOW, reason_code="r1"),
                _explanation(store_number=1, sku_number=108, action=ACTION_REVIEW_NOW, reason_code="r2"),
            ],
        )
        summary = artifacts.recommendation_effectiveness_summary
        self.assertEqual(summary.total_rows_evaluated, 2)
        self.assertEqual(summary.attribution_ready_count, 1)
        self.assertEqual(summary.effective_strong_count, 1)
        self.assertEqual(summary.inconclusive_count, 1)

    def test_effectiveness_by_reason_groups_correctly(self) -> None:
        artifacts = self._build(
            rows=[
                _row(store_number=1, sku_number=109, suggested_order_units=10, actual_units_sold=15),
                _row(store_number=1, sku_number=110, suggested_order_units=10, actual_units_sold=2),
            ],
            explanations=[
                _explanation(store_number=1, sku_number=109, reason_code="reason_a"),
                _explanation(store_number=1, sku_number=110, reason_code="reason_b"),
            ],
        )
        grouped = artifacts.recommendation_effectiveness_by_reason
        self.assertIn("row_change_reason_code", grouped.columns)
        self.assertIn("row_count", grouped.columns)
        self.assertEqual(int(grouped["row_count"].sum()), 2)

    def test_learning_priority_queue_subset_of_attribution(self) -> None:
        artifacts = self._build(
            rows=[
                _row(store_number=1, sku_number=111, suggested_order_units=10, actual_units_sold=22, expected_sales=100, actual_sales=220, expected_margin=20, actual_margin=60),
                _row(store_number=1, sku_number=112, suggested_order_units=10, actual_units_sold=1, expected_sales=100, actual_sales=40, expected_margin=20, actual_margin=2),
            ],
            explanations=[
                _explanation(store_number=1, sku_number=111, reason_code="win"),
                _explanation(store_number=1, sku_number=112, reason_code="loss"),
            ],
        )
        attr_keys = set(
            artifacts.attribution.apply(
                lambda r: (str(r["store_number"]), str(r["sku_number"]), str(r["promotion_start_date"]), str(r["promotion_end_date"])),
                axis=1,
            )
        )
        queue_keys = set(
            artifacts.recommendation_learning_priority_queue.apply(
                lambda r: (str(r["store_number"]), str(r["sku_number"]), str(r["promotion_start_date"]), str(r["promotion_end_date"])),
                axis=1,
            )
        )
        self.assertTrue(queue_keys.issubset(attr_keys))

    def test_contradictory_state_fails_loud(self) -> None:
        attribution = pd.DataFrame(
            [
                {
                    "store_number": "1",
                    "sku_number": "1",
                    "promotion_start_date": "2024-09-01",
                    "promotion_end_date": "2024-09-07",
                    "attribution_status": ATTRIBUTION_READY,
                    "attribution_window_complete_flag": True,
                    "realized_units_delta_vs_recommendation": None,
                    "realized_sales_delta_vs_expectation": None,
                    "realized_margin_delta_vs_expectation": None,
                    "recommendation_effectiveness_class": EFFECTIVE_STRONG,
                }
            ]
        )
        summary = type(
            "S",
            (),
            {
                "attribution_harmful_count": 0,
                "attribution_effective_count": 1,
                "attribution_inconclusive_count": 0,
            },
        )()
        with self.assertRaises(ValueError):
            _validate_attribution_consistency(
                attribution=attribution,
                summary=summary,
                learning_queue=attribution.copy(),
            )

    def test_learning_signal_classification_available(self) -> None:
        rows = []
        explanations = []
        for idx in range(12):
            rows.append(
                _row(
                    store_number=2,
                    sku_number=200 + idx,
                    suggested_order_units=10,
                    actual_units_sold=20 if idx % 2 == 0 else 2,
                    expected_sales=100,
                    actual_sales=180 if idx % 2 == 0 else 60,
                    expected_margin=40,
                    actual_margin=70 if idx % 2 == 0 else 10,
                )
            )
            explanations.append(_explanation(store_number=2, sku_number=200 + idx, reason_code=f"r{idx}"))

        artifacts = self._build(rows=rows, explanations=explanations)
        self.assertIn(
            artifacts.recommendation_effectiveness_summary.commercial_learning_signal_strength_class,
            {LEARNING_SIGNAL_STRONG, LEARNING_SIGNAL_NOT_READY, "LEARNING_SIGNAL_MODERATE", "LEARNING_SIGNAL_WEAK"},
        )


if __name__ == "__main__":
    unittest.main()
