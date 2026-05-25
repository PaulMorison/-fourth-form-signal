"""Unit tests for the governed Stage 11/12 publishability transparency split."""

from __future__ import annotations

import unittest

import pandas as pd

from runtime.promotions.commercial_publishability_split import (
    DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE,
    DEMAND_EVIDENCE_CLASS_COLD_START,
    DEMAND_EVIDENCE_CLASS_LOW_NONZERO,
    DEMAND_EVIDENCE_CLASS_TRUE_ZERO,
    HEADLINE_NO_DECISION_SURFACE,
    HEADLINE_ALREADY_PUBLISHED_ONLY,
    HEADLINE_PUBLISHED,
    HEADLINE_REVIEW_ONLY,
    HEADLINE_SUSPICIOUS_COLLAPSE,
    HEADLINE_VALID_ZEROS_ONLY,
    build_commercial_publishability_split,
    split_to_manifest_payload,
)


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class CommercialPublishabilitySplitTests(unittest.TestCase):
    def test_empty_decision_surface_yields_governed_no_surface_headline(self) -> None:
        split = build_commercial_publishability_split(
            store_download_frame=_frame([]),
            pos_upload_row_count=0,
            pos_excluded_row_count=0,
        )
        self.assertEqual(split.total_decision_surface_rows, 0)
        self.assertEqual(split.headline_class, HEADLINE_NO_DECISION_SURFACE)

    def test_published_orders_drive_published_headline(self) -> None:
        split = build_commercial_publishability_split(
            store_download_frame=_frame(
                [
                    {"decision_recommendation": "ORDER", "demand_evidence_class": "HEALTHY"},
                    {"decision_recommendation": "ORDER", "demand_evidence_class": "HEALTHY"},
                    {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                ]
            ),
            pos_upload_row_count=2,
            pos_excluded_row_count=0,
        )
        self.assertEqual(split.final_publishable_rows, 2)
        self.assertEqual(split.review_required_rows, 1)
        self.assertEqual(split.headline_class, HEADLINE_PUBLISHED)

    def test_review_only_when_nothing_published(self) -> None:
        split = build_commercial_publishability_split(
            store_download_frame=_frame(
                [
                    {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                    {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                ]
            ),
            pos_upload_row_count=0,
            pos_excluded_row_count=0,
        )
        self.assertEqual(split.review_required_rows, 2)
        self.assertEqual(split.final_publishable_rows, 0)
        self.assertEqual(split.headline_class, HEADLINE_REVIEW_ONLY)

    def test_artificial_collapse_dominates_yields_suspicious_headline(self) -> None:
        split = build_commercial_publishability_split(
            store_download_frame=_frame(
                [
                    {
                        "decision_recommendation": "REVIEW",
                        "demand_evidence_class": DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE,
                    },
                    {
                        "decision_recommendation": "REVIEW",
                        "demand_evidence_class": DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE,
                    },
                    {
                        "decision_recommendation": "REVIEW",
                        "demand_evidence_class": DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE,
                    },
                    {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                ]
            ),
            pos_upload_row_count=0,
            pos_excluded_row_count=0,
        )
        self.assertEqual(split.artificial_collapse_rows, 3)
        # The 3 ARTIFICIAL_COLLAPSE rows are pulled out of the REVIEW count.
        self.assertEqual(split.review_required_rows, 1)
        self.assertEqual(split.headline_class, HEADLINE_SUSPICIOUS_COLLAPSE)

    def test_legitimate_zeros_only_headline(self) -> None:
        split = build_commercial_publishability_split(
            store_download_frame=_frame(
                [
                    {
                        "decision_recommendation": "DO_NOT_ORDER",
                        "demand_evidence_class": DEMAND_EVIDENCE_CLASS_TRUE_ZERO,
                    },
                    {
                        "decision_recommendation": "DO_NOT_ORDER",
                        "demand_evidence_class": DEMAND_EVIDENCE_CLASS_COLD_START,
                    },
                    {
                        "decision_recommendation": "DO_NOT_ORDER",
                        "demand_evidence_class": DEMAND_EVIDENCE_CLASS_LOW_NONZERO,
                    },
                ]
            ),
            pos_upload_row_count=0,
            pos_excluded_row_count=0,
        )
        self.assertEqual(split.true_zero_demand_rows, 1)
        self.assertEqual(split.evidence_supported_zero_rows, 2)
        self.assertEqual(split.artificial_collapse_rows, 0)
        self.assertEqual(split.headline_class, HEADLINE_VALID_ZEROS_ONLY)

    def test_split_is_row_conserving_with_residual_bucket(self) -> None:
        frame = _frame(
            [
                {"decision_recommendation": "ORDER", "demand_evidence_class": "HEALTHY"},
                {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                {"decision_recommendation": "HOLD", "demand_evidence_class": "HEALTHY"},
                {
                    "decision_recommendation": "DO_NOT_ORDER",
                    "demand_evidence_class": DEMAND_EVIDENCE_CLASS_TRUE_ZERO,
                },
            ]
        )
        split = build_commercial_publishability_split(
            store_download_frame=frame,
            pos_upload_row_count=1,
            pos_excluded_row_count=0,
        )
        accounted = (
            split.true_zero_demand_rows
            + split.evidence_supported_zero_rows
            + split.artificial_collapse_rows
            + split.registry_duplicate_rows
            + split.review_required_rows
            + split.final_publishable_rows
            + split.policy_excluded_legitimate_rows
            + split.other_non_actionable_rows
        )
        self.assertEqual(accounted, split.total_decision_surface_rows)

    def test_mixed_registry_duplicate_and_review_only_is_row_conserving(self) -> None:
        frame = _frame(
            [
                {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
            ]
        )
        split = build_commercial_publishability_split(
            store_download_frame=frame,
            pos_upload_row_count=0,
            pos_excluded_row_count=4,
            stage12_review_only_row_count=4,
            registry_duplicate_row_count=2,
        )

        self.assertEqual(split.registry_duplicate_rows, 2)
        self.assertEqual(split.review_required_rows, 4)
        self.assertEqual(split.policy_excluded_legitimate_rows, 0)
        self.assertEqual(split.other_non_actionable_rows, 0)
        self.assertEqual(split.headline_class, HEADLINE_REVIEW_ONLY)
        accounted = (
            split.true_zero_demand_rows
            + split.evidence_supported_zero_rows
            + split.artificial_collapse_rows
            + split.registry_duplicate_rows
            + split.review_required_rows
            + split.final_publishable_rows
            + split.policy_excluded_legitimate_rows
            + split.other_non_actionable_rows
        )
        self.assertEqual(accounted, split.total_decision_surface_rows)

    def test_all_duplicate_registry_rows_are_not_reported_as_review_work(self) -> None:
        frame = _frame(
            [
                {"decision_recommendation": "REVIEW", "demand_evidence_class": "HEALTHY"},
                {"decision_recommendation": "ORDER", "demand_evidence_class": "HEALTHY"},
            ]
        )
        split = build_commercial_publishability_split(
            store_download_frame=frame,
            pos_upload_row_count=0,
            pos_excluded_row_count=0,
            stage12_review_only_row_count=0,
            registry_duplicate_row_count=2,
        )

        self.assertEqual(split.registry_duplicate_rows, 2)
        self.assertEqual(split.review_required_rows, 0)
        self.assertEqual(split.policy_excluded_legitimate_rows, 0)
        self.assertEqual(split.other_non_actionable_rows, 0)
        self.assertEqual(split.headline_class, HEADLINE_ALREADY_PUBLISHED_ONLY)

    def test_manifest_payload_keys_are_governed_and_complete(self) -> None:
        split = build_commercial_publishability_split(
            store_download_frame=_frame(
                [{"decision_recommendation": "ORDER", "demand_evidence_class": "HEALTHY"}]
            ),
            pos_upload_row_count=1,
            pos_excluded_row_count=0,
        )
        payload = split_to_manifest_payload(split)
        self.assertIn("commercial_publishability_total_rows", payload)
        self.assertIn("commercial_publishability_registry_duplicate_rows", payload)
        self.assertIn("commercial_publishability_final_publishable_rows", payload)
        self.assertIn("commercial_publishability_headline_class", payload)
        self.assertIn("commercial_publishability_headline_message", payload)


if __name__ == "__main__":
    unittest.main()
