"""Focused tests for publication opportunity classification and reconciliation."""

import unittest
from runtime.promotions.publication_opportunity import (
    FRESHNESS_NO_NEW_PUBLICATIONS_REVIEW_ONLY,
    PUBLICATION_OPPORTUNITY_FRESH,
    PUBLICATION_OPPORTUNITY_DUPLICATE_ONLY,
    PUBLICATION_OPPORTUNITY_LEGITIMATE_ZERO,
    PUBLICATION_OPPORTUNITY_REVIEW_ONLY,
    PUBLICATION_OPPORTUNITY_FILTERED_OUT,
    PUBLICATION_OPPORTUNITY_BLOCKED_BY_DEFECT,
    REPLAY_SAFETY_SAFE_REVIEW_OR_INPUT_CHANGE_NEEDED,
    PublicationOpportunityInput,
    PublicationOpportunityClassification,
    classify_commercial_freshness,
    classify_publication_opportunity,
    classify_replay_safety,
    build_publish_reconciliation_summary,
    build_commercial_stage_timing,
    build_duplicate_registry_skip_summary,
    build_commercial_operator_brief,
)



class PublicationOpportunityClassifierTests(unittest.TestCase):
    """Tests for publication opportunity classification."""

    def test_classifier_returns_fresh_when_publishable_rows_exist(self) -> None:
        payload = PublicationOpportunityInput(
            stage11_total_rows=10,
            stage11_order_rows=7,
            stage11_review_rows=0,
            stage11_true_zero_rows=0,
            stage11_cold_start_rows=1,
            stage11_low_nonzero_rows=1,
            stage11_artificial_collapse_rows=1,
            stage12_publish_status="PASS",
            stage12_publish_status_reason="new_publications_written",
            stage12_candidate_row_count=7,
            stage12_publishable_row_count=5,
            stage12_review_only_row_count=0,
            stage12_legitimate_excluded_row_count=1,
            stage12_defect_excluded_row_count=0,
            stage12_duplicate_registry_skip_count=0,
        )

        result = classify_publication_opportunity(payload)

        self.assertEqual(result.publication_opportunity_class, PUBLICATION_OPPORTUNITY_FRESH)
        self.assertFalse(result.duplicate_only_noop_flag)
        self.assertFalse(result.review_only_cycle_flag)
        self.assertFalse(result.legitimate_zero_cycle_flag)
        self.assertFalse(result.filtered_out_cycle_flag)
        self.assertFalse(result.blocked_by_defect_flag)
        self.assertEqual(result.fresh_publication_candidate_count, 5)

    def test_classifier_returns_duplicate_only_for_noop_already_published(self) -> None:
        payload = PublicationOpportunityInput(
            stage11_total_rows=5,
            stage11_order_rows=5,
            stage11_review_rows=0,
            stage11_true_zero_rows=0,
            stage11_cold_start_rows=0,
            stage11_low_nonzero_rows=0,
            stage11_artificial_collapse_rows=0,
            stage12_publish_status="NOOP_ALREADY_PUBLISHED",
            stage12_publish_status_reason="all_candidates_already_published",
            stage12_candidate_row_count=5,
            stage12_publishable_row_count=0,
            stage12_review_only_row_count=0,
            stage12_legitimate_excluded_row_count=0,
            stage12_defect_excluded_row_count=0,
            stage12_duplicate_registry_skip_count=5,
        )

        result = classify_publication_opportunity(payload)

        self.assertEqual(result.publication_opportunity_class, PUBLICATION_OPPORTUNITY_DUPLICATE_ONLY)
        self.assertTrue(result.duplicate_only_noop_flag)
        self.assertFalse(result.review_only_cycle_flag)
        self.assertFalse(result.legitimate_zero_cycle_flag)
        self.assertFalse(result.filtered_out_cycle_flag)
        self.assertFalse(result.blocked_by_defect_flag)
        self.assertEqual(result.fresh_publication_candidate_count, 0)

    def test_classifier_returns_legitimate_zero_for_true_zero_demand_rows(self) -> None:
        payload = PublicationOpportunityInput(
            stage11_total_rows=8,
            stage11_order_rows=0,
            stage11_review_rows=0,
            stage11_true_zero_rows=6,
            stage11_cold_start_rows=1,
            stage11_low_nonzero_rows=1,
            stage11_artificial_collapse_rows=0,
            stage12_publish_status="NOOP_VALID_NO_PUBLISHABLE_ROWS",
            stage12_publish_status_reason="no_publishable_rows_legitimate",
            stage12_candidate_row_count=8,
            stage12_publishable_row_count=0,
            stage12_review_only_row_count=0,
            stage12_legitimate_excluded_row_count=6,
            stage12_defect_excluded_row_count=0,
            stage12_duplicate_registry_skip_count=0,
        )

        result = classify_publication_opportunity(payload)

        self.assertEqual(result.publication_opportunity_class, PUBLICATION_OPPORTUNITY_LEGITIMATE_ZERO)
        self.assertFalse(result.duplicate_only_noop_flag)
        self.assertFalse(result.review_only_cycle_flag)
        self.assertTrue(result.legitimate_zero_cycle_flag)
        self.assertFalse(result.filtered_out_cycle_flag)
        self.assertFalse(result.blocked_by_defect_flag)

    def test_classifier_returns_review_only_when_all_rows_are_review_gated(self) -> None:
        payload = PublicationOpportunityInput(
            stage11_total_rows=4,
            stage11_order_rows=0,
            stage11_review_rows=4,
            stage11_true_zero_rows=0,
            stage11_cold_start_rows=0,
            stage11_low_nonzero_rows=0,
            stage11_artificial_collapse_rows=0,
            stage12_publish_status="NOOP_VALID_NO_PUBLISHABLE_ROWS",
            stage12_publish_status_reason="no_publishable_rows",
            stage12_candidate_row_count=4,
            stage12_publishable_row_count=0,
            stage12_review_only_row_count=4,
            stage12_legitimate_excluded_row_count=0,
            stage12_defect_excluded_row_count=0,
            stage12_duplicate_registry_skip_count=0,
        )

        result = classify_publication_opportunity(payload)

        self.assertEqual(result.publication_opportunity_class, PUBLICATION_OPPORTUNITY_REVIEW_ONLY)
        self.assertFalse(result.duplicate_only_noop_flag)
        self.assertTrue(result.review_only_cycle_flag)
        self.assertFalse(result.legitimate_zero_cycle_flag)
        self.assertFalse(result.filtered_out_cycle_flag)
        self.assertFalse(result.blocked_by_defect_flag)

    def test_commercial_freshness_preserves_mixed_duplicate_and_review_only(self) -> None:
        freshness = classify_commercial_freshness(
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_REVIEW_ONLY,
            newly_published_row_count=0,
            duplicate_registry_skip_count=500,
            review_only_row_count=1000,
            legitimate_zero_row_count=0,
            filtered_out_row_count=0,
            defect_blocked_row_count=0,
            validation_status="SKIPPED_NO_NEW_PUBLICATIONS",
        )

        self.assertEqual(freshness.freshness_class, FRESHNESS_NO_NEW_PUBLICATIONS_REVIEW_ONLY)
        self.assertEqual(freshness.freshness_reason, "review_only_rows")
        self.assertIn("prior publications", freshness.freshness_message)

        replay_safety = classify_replay_safety(
            freshness_class=freshness.freshness_class,
            commercial_outcome_blocked_by_defect_flag=False,
            stage12_publish_status="NOOP_VALID_NO_PUBLISHABLE_ROWS",
        )

        self.assertEqual(
            replay_safety.replay_safety_class,
            REPLAY_SAFETY_SAFE_REVIEW_OR_INPUT_CHANGE_NEEDED,
        )
        self.assertEqual(replay_safety.replay_safety_reason, "review_only_may_change_with_approval")

    def test_classifier_returns_filtered_out_when_candidates_excluded_by_policy(self) -> None:
        payload = PublicationOpportunityInput(
            stage11_total_rows=12,
            stage11_order_rows=10,
            stage11_review_rows=2,
            stage11_true_zero_rows=0,
            stage11_cold_start_rows=0,
            stage11_low_nonzero_rows=0,
            stage11_artificial_collapse_rows=0,
            stage12_publish_status="NOOP_VALID_NO_PUBLISHABLE_ROWS",
            stage12_publish_status_reason="filtered_out_by_policy",
            stage12_candidate_row_count=10,
            stage12_publishable_row_count=0,
            stage12_review_only_row_count=0,
            stage12_legitimate_excluded_row_count=10,
            stage12_defect_excluded_row_count=0,
            stage12_duplicate_registry_skip_count=0,
        )

        result = classify_publication_opportunity(payload)

        self.assertEqual(result.publication_opportunity_class, PUBLICATION_OPPORTUNITY_FILTERED_OUT)
        self.assertFalse(result.duplicate_only_noop_flag)
        self.assertFalse(result.review_only_cycle_flag)
        self.assertFalse(result.legitimate_zero_cycle_flag)
        self.assertTrue(result.filtered_out_cycle_flag)
        self.assertFalse(result.blocked_by_defect_flag)
        self.assertEqual(result.fresh_publication_candidate_count, 10)

    def test_classifier_returns_blocked_by_defect_when_stage12_fails(self) -> None:
        payload = PublicationOpportunityInput(
            stage11_total_rows=5,
            stage11_order_rows=5,
            stage11_review_rows=0,
            stage11_true_zero_rows=0,
            stage11_cold_start_rows=0,
            stage11_low_nonzero_rows=0,
            stage11_artificial_collapse_rows=0,
            stage12_publish_status="FAIL",
            stage12_publish_status_reason="critical_defect",
            stage12_candidate_row_count=5,
            stage12_publishable_row_count=0,
            stage12_review_only_row_count=0,
            stage12_legitimate_excluded_row_count=0,
            stage12_defect_excluded_row_count=5,
            stage12_duplicate_registry_skip_count=0,
        )

        result = classify_publication_opportunity(payload)

        self.assertEqual(result.publication_opportunity_class, PUBLICATION_OPPORTUNITY_BLOCKED_BY_DEFECT)
        self.assertFalse(result.duplicate_only_noop_flag)
        self.assertFalse(result.review_only_cycle_flag)
        self.assertFalse(result.legitimate_zero_cycle_flag)
        self.assertFalse(result.filtered_out_cycle_flag)
        self.assertTrue(result.blocked_by_defect_flag)

    def test_classifier_to_dict(self) -> None:
        payload = PublicationOpportunityInput(
            stage11_total_rows=5,
            stage11_order_rows=5,
            stage11_review_rows=0,
            stage11_true_zero_rows=0,
            stage11_cold_start_rows=0,
            stage11_low_nonzero_rows=0,
            stage11_artificial_collapse_rows=0,
            stage12_publish_status="PASS",
            stage12_publish_status_reason="fresh_publications_written",
            stage12_candidate_row_count=5,
            stage12_publishable_row_count=3,
            stage12_review_only_row_count=0,
            stage12_legitimate_excluded_row_count=2,
            stage12_defect_excluded_row_count=0,
            stage12_duplicate_registry_skip_count=0,
        )

        result = classify_publication_opportunity(payload)
        as_dict = result.to_dict()

        self.assertIn("publication_opportunity_class", as_dict)
        self.assertEqual(as_dict["publication_opportunity_class"], PUBLICATION_OPPORTUNITY_FRESH)


class ReconciliationTests(unittest.TestCase):
    """Tests for publish reconciliation summary."""

    def test_reconciliation_passes_when_counts_align(self) -> None:
        payload = PublicationOpportunityInput(
            stage11_total_rows=10,
            stage11_order_rows=7,
            stage11_review_rows=0,
            stage11_true_zero_rows=1,
            stage11_cold_start_rows=1,
            stage11_low_nonzero_rows=1,
            stage11_artificial_collapse_rows=0,
            stage12_publish_status="PASS",
            stage12_publish_status_reason="fresh",
            stage12_candidate_row_count=7,
            stage12_publishable_row_count=5,
            stage12_review_only_row_count=0,
            stage12_legitimate_excluded_row_count=2,
            stage12_defect_excluded_row_count=0,
            stage12_duplicate_registry_skip_count=0,
        )

        summary = build_publish_reconciliation_summary(payload)

        self.assertTrue(summary.reconciled_flag)
        self.assertEqual(summary.stage11_total_rows, 10)
        self.assertIn("reconciled", summary.reconciliation_message.lower())

    def test_reconciliation_fails_when_counts_mismatch(self) -> None:
        payload = PublicationOpportunityInput(
            stage11_total_rows=15,  # Intentional mismatch
            stage11_order_rows=7,
            stage11_review_rows=0,
            stage11_true_zero_rows=1,
            stage11_cold_start_rows=1,
            stage11_low_nonzero_rows=1,
            stage11_artificial_collapse_rows=0,
            stage12_publish_status="PASS",
            stage12_publish_status_reason="fresh",
            stage12_candidate_row_count=7,
            stage12_publishable_row_count=5,
            stage12_review_only_row_count=0,
            stage12_legitimate_excluded_row_count=2,
            stage12_defect_excluded_row_count=0,
            stage12_duplicate_registry_skip_count=0,
        )

        with self.assertRaises(ValueError) as context:
            build_publish_reconciliation_summary(payload)

        self.assertIn("FAILED", str(context.exception))

    def test_reconciliation_to_dict(self) -> None:
        payload = PublicationOpportunityInput(
            stage11_total_rows=8,
            stage11_order_rows=5,
            stage11_review_rows=0,
            stage11_true_zero_rows=2,
            stage11_cold_start_rows=1,
            stage11_low_nonzero_rows=0,
            stage11_artificial_collapse_rows=0,
            stage12_publish_status="PASS",
            stage12_publish_status_reason="fresh",
            stage12_candidate_row_count=5,
            stage12_publishable_row_count=4,
            stage12_review_only_row_count=0,
            stage12_legitimate_excluded_row_count=1,
            stage12_defect_excluded_row_count=0,
            stage12_duplicate_registry_skip_count=0,
        )

        summary = build_publish_reconciliation_summary(payload)
        as_dict = summary.to_dict()

        self.assertIn("stage11_total_rows", as_dict)
        self.assertIn("reconciled_flag", as_dict)
        self.assertTrue(as_dict["reconciled_flag"])


class CommercialStageTimingTests(unittest.TestCase):
    """Tests for commercial stage timing summary."""

    def test_timing_identifies_longest_stage(self) -> None:
        timing = build_commercial_stage_timing(
            run_id="test-run",
            stage6_elapsed_seconds=5.0,
            stage8_elapsed_seconds=120.0,
            stage11_elapsed_seconds=15.0,
            stage12_elapsed_seconds=10.0,
            stage13_elapsed_seconds=3.0,
        )

        self.assertEqual(timing.longest_commercial_stage, "Stage 8")
        self.assertEqual(timing.longest_commercial_stage_elapsed_seconds, 120.0)

    def test_timing_generates_guidance_for_long_run(self) -> None:
        timing = build_commercial_stage_timing(
            run_id="test-run",
            stage6_elapsed_seconds=100.0,
            stage8_elapsed_seconds=150.0,
            stage11_elapsed_seconds=80.0,
            stage12_elapsed_seconds=50.0,
            stage13_elapsed_seconds=30.0,
        )

        self.assertIn("Long commercial run detected", timing.operator_guidance_message)
        self.assertIn("Stage 8", timing.operator_guidance_message)

    def test_timing_generates_guidance_for_single_long_stage(self) -> None:
        timing = build_commercial_stage_timing(
            run_id="test-run",
            stage6_elapsed_seconds=150.0,
            stage8_elapsed_seconds=5.0,
            stage11_elapsed_seconds=5.0,
            stage12_elapsed_seconds=5.0,
            stage13_elapsed_seconds=3.0,
        )

        self.assertIn("bottleneck", timing.operator_guidance_message.lower())
        self.assertIn("Stage 6", timing.operator_guidance_message)

    def test_timing_generates_healthy_guidance_for_short_run(self) -> None:
        timing = build_commercial_stage_timing(
            run_id="test-run",
            stage6_elapsed_seconds=5.0,
            stage8_elapsed_seconds=8.0,
            stage11_elapsed_seconds=10.0,
            stage12_elapsed_seconds=5.0,
            stage13_elapsed_seconds=2.0,
        )

        self.assertIn("healthy", timing.operator_guidance_message.lower())

    def test_timing_to_dict(self) -> None:
        timing = build_commercial_stage_timing(
            run_id="test-run",
            stage6_elapsed_seconds=5.0,
            stage8_elapsed_seconds=10.0,
            stage11_elapsed_seconds=15.0,
            stage12_elapsed_seconds=8.0,
            stage13_elapsed_seconds=3.0,
        )
        as_dict = timing.to_dict()

        self.assertIn("run_id", as_dict)
        self.assertIn("longest_commercial_stage", as_dict)
        self.assertEqual(as_dict["longest_commercial_stage"], "Stage 11")


class DuplicateRegistrySkipSummaryTests(unittest.TestCase):
    """Tests for duplicate registry skip diagnostic."""

    def test_duplicate_summary_for_all_duplicates(self) -> None:
        summary = build_duplicate_registry_skip_summary(
            skipped_row_count=50,
            unique_store_count=5,
            unique_promotion_count=10,
            unique_sku_count=8,
            first_seen_publication_date_min="2024-08-01",
            first_seen_publication_date_max="2024-08-15",
        )

        self.assertTrue(summary.all_rows_previously_published_flag)
        self.assertEqual(summary.skipped_row_count, 50)
        self.assertIn("already published", summary.recommended_next_action.lower())

    def test_duplicate_summary_with_null_dates(self) -> None:
        summary = build_duplicate_registry_skip_summary(
            skipped_row_count=10,
            unique_store_count=2,
            unique_promotion_count=3,
            unique_sku_count=2,
            first_seen_publication_date_min=None,
            first_seen_publication_date_max=None,
        )

        self.assertIsNone(summary.first_seen_publication_date_min)
        self.assertIsNone(summary.first_seen_publication_date_max)

    def test_duplicate_summary_to_dict(self) -> None:
        summary = build_duplicate_registry_skip_summary(
            skipped_row_count=25,
            unique_store_count=3,
            unique_promotion_count=5,
            unique_sku_count=4,
            first_seen_publication_date_min="2024-08-10",
            first_seen_publication_date_max="2024-08-20",
        )
        as_dict = summary.to_dict()

        self.assertIn("skipped_row_count", as_dict)
        self.assertIn("all_rows_previously_published_flag", as_dict)
        self.assertEqual(as_dict["skipped_row_count"], 25)


class CommercialOperatorBriefTests(unittest.TestCase):
    """Tests for commercial operator brief markdown generation."""

    def test_operator_brief_includes_key_sections(self) -> None:
        brief = build_commercial_operator_brief(
            run_id="test-run-123",
            as_of_date="2024-09-01",
            commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
            commercial_outcome_message="Fresh publications were written successfully.",
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_FRESH,
            publication_opportunity_message="5 fresh publications available.",
            stage12_publish_status="PASS",
            stage12_publish_status_reason="fresh_publications_written",
            stage13_skip_class="VALIDATION_EXECUTED",
            stage11_total_rows=10,
            stage12_candidate_row_count=7,
            stage12_publishable_row_count=5,
            stage12_duplicate_registry_skip_count=0,
        )

        self.assertIn("# Commercial Operator Brief", brief)
        self.assertIn("test-run-123", brief)
        self.assertIn("## Commercial Outcome", brief)
        self.assertIn("## Publication Opportunity", brief)
        self.assertIn("## Delta vs Prior Cycle", brief)
        self.assertIn("## Materiality", brief)
        self.assertIn("## Top Commercial Changes", brief)
        self.assertIn("## Publish Result", brief)
        self.assertIn("## Validation Result", brief)
        self.assertIn("## Key Counts", brief)
        self.assertIn("## Recommended Next Action", brief)
        self.assertIn("## Outcome Attribution", brief)
        self.assertIn("## What Worked", brief)
        self.assertIn("## What Failed", brief)
        self.assertIn("## What to Learn Next", brief)
        self.assertIn("## Policy Calibration", brief)
        self.assertIn("## What to tighten", brief)
        self.assertIn("## What to loosen", brief)
        self.assertIn("## What to leave unchanged", brief)
        self.assertIn("## Watchlist", brief)
        self.assertIn("## Policy Simulation", brief)
        self.assertIn("## Baseline vs Simulated Outcome", brief)
        self.assertIn("## Biggest Winners", brief)
        self.assertIn("## Biggest Risks", brief)
        self.assertIn("## Simulation Watchlist", brief)
        self.assertIn("## Action Instructions", brief)
        self.assertIn("### Immediate Priorities", brief)
        self.assertIn("### Top Operator Actions", brief)
        self.assertIn("### Top Model Owner Actions", brief)
        self.assertIn("### Action Queue Preview", brief)

    def test_operator_brief_includes_counts(self) -> None:
        brief = build_commercial_operator_brief(
            run_id="test-run",
            as_of_date="2024-09-01",
            commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
            commercial_outcome_message="Success.",
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_FRESH,
            publication_opportunity_message="Fresh publications available.",
            stage12_publish_status="PASS",
            stage12_publish_status_reason="fresh",
            stage13_skip_class="VALIDATION_EXECUTED",
            stage11_total_rows=100,
            stage12_candidate_row_count=75,
            stage12_publishable_row_count=50,
            stage12_duplicate_registry_skip_count=25,
        )

        self.assertIn("100", brief)
        self.assertIn("75", brief)
        self.assertIn("50", brief)
        self.assertIn("25", brief)

    def test_operator_brief_for_duplicate_only_includes_guidance(self) -> None:
        brief = build_commercial_operator_brief(
            run_id="test-run",
            as_of_date="2024-09-01",
            commercial_outcome_class="COMMERCIAL_SUCCESS_GOVERNED_NOOP_ALREADY_PUBLISHED",
            commercial_outcome_message="NOOP because all duplicate.",
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_DUPLICATE_ONLY,
            publication_opportunity_message="All candidates already published.",
            stage12_publish_status="NOOP_ALREADY_PUBLISHED",
            stage12_publish_status_reason="all_candidates_already_published",
            stage13_skip_class="STAGE12_NOOP_ALREADY_PUBLISHED",
            stage11_total_rows=5,
            stage12_candidate_row_count=5,
            stage12_publishable_row_count=0,
            stage12_duplicate_registry_skip_count=5,
        )

        self.assertTrue(
            "next_cycle" in brief.lower() or "fresh_promotion" in brief.lower(),
            f"Expected 'next_cycle' or 'fresh_promotion' in brief but got: {brief}"
        )

    def test_operator_brief_is_markdown_valid(self) -> None:
        """Smoke test that markdown is well-formed."""
        brief = build_commercial_operator_brief(
            run_id="test",
            as_of_date="2024-09-01",
            commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
            commercial_outcome_message="Test outcome.",
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_FRESH,
            publication_opportunity_message="Test opportunity.",
            stage12_publish_status="PASS",
            stage12_publish_status_reason="test",
            stage13_skip_class="VALIDATION_EXECUTED",
            stage11_total_rows=10,
            stage12_candidate_row_count=10,
            stage12_publishable_row_count=10,
            stage12_duplicate_registry_skip_count=0,
        )

        # Markdown should have headers
        self.assertGreater(brief.count("#"), 2)
        # Should have at least one list or bold item
        self.assertIn("**", brief)
        # Should not be empty
        self.assertGreater(len(brief), 100)


if __name__ == "__main__":
    unittest.main()
