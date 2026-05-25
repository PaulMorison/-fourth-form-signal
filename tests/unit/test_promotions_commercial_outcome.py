from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.commercial_outcome import (
    COMMERCIAL_FAILURE_DEFECT,
    COMMERCIAL_FAILURE_VALIDATION,
    COMMERCIAL_SUCCESS_GOVERNED_NOOP_ALREADY_PUBLISHED,
    COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS,
    COMMERCIAL_SUCCESS_NEW_PUBLICATIONS,
    PUBLISH_STATUS_FAIL,
    PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED,
    PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
    PUBLISH_STATUS_PASS,
    VALIDATION_STATUS_FAIL,
    VALIDATION_STATUS_PASS,
    CommercialOutcomeInput,
    build_publication_freshness_diagnostic,
    classify_commercial_outcome,
)


class PromotionCommercialOutcomeTests(unittest.TestCase):
    def test_classifier_returns_success_new_publications(self) -> None:
        outcome = classify_commercial_outcome(
            CommercialOutcomeInput(
                run_completed_successfully_flag=True,
                stage12_publish_status=PUBLISH_STATUS_PASS,
                stage12_publish_status_reason="all_candidate_rows_published",
                stage12_pos_upload_row_count=42,
                stage12_candidate_row_count=50,
                stage12_duplicate_registry_skip_count=8,
                stage13_validation_status=VALIDATION_STATUS_PASS,
                stage13_validation_status_reason="all_validation_checks_passed",
                stage13_skip_class="VALIDATION_EXECUTED",
            )
        )
        self.assertEqual(outcome.commercial_outcome_class, COMMERCIAL_SUCCESS_NEW_PUBLICATIONS)
        self.assertEqual(outcome.commercial_new_publication_count, 42)
        self.assertFalse(outcome.commercial_failure_flag)

    def test_classifier_returns_success_noop_already_published(self) -> None:
        outcome = classify_commercial_outcome(
            CommercialOutcomeInput(
                run_completed_successfully_flag=True,
                stage12_publish_status=PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED,
                stage12_publish_status_reason="all_candidates_already_published",
                stage12_pos_upload_row_count=0,
                stage12_candidate_row_count=10,
                stage12_duplicate_registry_skip_count=10,
                stage13_validation_status=VALIDATION_STATUS_PASS,
                stage13_validation_status_reason="stage12_noop_already_published",
                stage13_skip_class="STAGE12_NOOP_ALREADY_PUBLISHED",
            )
        )
        self.assertEqual(
            outcome.commercial_outcome_class,
            COMMERCIAL_SUCCESS_GOVERNED_NOOP_ALREADY_PUBLISHED,
        )
        self.assertTrue(outcome.commercial_noop_flag)

    def test_classifier_returns_success_noop_no_publishable_rows(self) -> None:
        outcome = classify_commercial_outcome(
            CommercialOutcomeInput(
                run_completed_successfully_flag=True,
                stage12_publish_status=PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
                stage12_publish_status_reason="legitimate_non_publishable_rows",
                stage12_pos_upload_row_count=0,
                stage12_candidate_row_count=12,
                stage12_duplicate_registry_skip_count=0,
                stage13_validation_status=VALIDATION_STATUS_PASS,
                stage13_validation_status_reason="stage12_noop_no_publishable_rows",
                stage13_skip_class="STAGE12_NOOP_NO_PUBLISHABLE_ROWS",
            )
        )
        self.assertEqual(
            outcome.commercial_outcome_class,
            COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS,
        )
        self.assertTrue(outcome.commercial_noop_flag)

    def test_classifier_returns_failure_defect_and_validation(self) -> None:
        defect_outcome = classify_commercial_outcome(
            CommercialOutcomeInput(
                run_completed_successfully_flag=True,
                stage12_publish_status=PUBLISH_STATUS_FAIL,
                stage12_publish_status_reason="excluded_row_ratio_above_threshold",
                stage12_pos_upload_row_count=0,
                stage12_candidate_row_count=5,
                stage12_duplicate_registry_skip_count=0,
                stage13_validation_status=VALIDATION_STATUS_PASS,
                stage13_validation_status_reason="not_executed",
                stage13_skip_class="VALIDATION_BLOCKED_BY_FAILURE",
            )
        )
        validation_outcome = classify_commercial_outcome(
            CommercialOutcomeInput(
                run_completed_successfully_flag=True,
                stage12_publish_status=PUBLISH_STATUS_PASS,
                stage12_publish_status_reason="all_candidate_rows_published",
                stage12_pos_upload_row_count=10,
                stage12_candidate_row_count=10,
                stage12_duplicate_registry_skip_count=0,
                stage13_validation_status=VALIDATION_STATUS_FAIL,
                stage13_validation_status_reason="pilot_or_gold_standard_failures_detected",
                stage13_skip_class="VALIDATION_EXECUTED",
            )
        )
        self.assertEqual(defect_outcome.commercial_outcome_class, COMMERCIAL_FAILURE_DEFECT)
        self.assertEqual(validation_outcome.commercial_outcome_class, COMMERCIAL_FAILURE_VALIDATION)
        self.assertTrue(defect_outcome.commercial_failure_flag)
        self.assertTrue(validation_outcome.commercial_failure_flag)

    def test_publication_freshness_diagnostic_distinguishes_duplicate_only_vs_empty(self) -> None:
        duplicate_only = build_publication_freshness_diagnostic(
            candidate_row_count=20,
            duplicate_registry_skip_count=20,
        )
        genuinely_empty = build_publication_freshness_diagnostic(
            candidate_row_count=0,
            duplicate_registry_skip_count=0,
        )
        self.assertTrue(duplicate_only.all_candidates_already_published_flag)
        self.assertFalse(genuinely_empty.all_candidates_already_published_flag)
        self.assertFalse(duplicate_only.ready_for_fresh_publication_test_flag)
        self.assertFalse(genuinely_empty.ready_for_fresh_publication_test_flag)


if __name__ == "__main__":
    unittest.main()
