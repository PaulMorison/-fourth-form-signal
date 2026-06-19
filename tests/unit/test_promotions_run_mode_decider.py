from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.promotion_run_mode_decider import (  # noqa: E402
    PromotionRunDecisionInput,
    decide_run_mode,
)


class PromotionsRunModeDeciderTests(unittest.TestCase):
    def test_auto_unknown_drift_warns_and_skips_training(self) -> None:
        decision = decide_run_mode(
            PromotionRunDecisionInput(
                requested_mode="auto",
                drift_signal="unknown",
                model_approved=True,
                schema_approved=True,
                training_permitted=True,
            )
        )

        self.assertEqual(decision.selected_mode, "skip-train")
        self.assertFalse(decision.should_train)
        self.assertTrue(decision.warnings)

    def test_auto_degraded_without_permission_does_not_train(self) -> None:
        decision = decide_run_mode(
            PromotionRunDecisionInput(
                requested_mode="auto",
                drift_signal="degraded",
                model_approved=True,
                schema_approved=True,
                training_permitted=False,
            )
        )

        self.assertEqual(decision.selected_mode, "skip-train")
        self.assertFalse(decision.should_train)

    def test_auto_degraded_with_permission_can_train(self) -> None:
        decision = decide_run_mode(
            PromotionRunDecisionInput(
                requested_mode="auto",
                drift_signal="degraded",
                model_approved=True,
                schema_approved=True,
                training_permitted=True,
            )
        )

        self.assertEqual(decision.selected_mode, "train")
        self.assertTrue(decision.should_train)

    def test_schema_not_approved_forces_validate_only(self) -> None:
        decision = decide_run_mode(
            PromotionRunDecisionInput(
                requested_mode="auto",
                drift_signal="stable",
                model_approved=True,
                schema_approved=False,
                training_permitted=True,
            )
        )

        self.assertEqual(decision.selected_mode, "validate-only")
        self.assertFalse(decision.should_train)
        self.assertTrue(decision.blockers)

    def test_explicit_train_mode_trains(self) -> None:
        decision = decide_run_mode(
            PromotionRunDecisionInput(
                requested_mode="train",
                drift_signal="stable",
                model_approved=True,
                schema_approved=True,
                training_permitted=False,
            )
        )

        self.assertEqual(decision.selected_mode, "train")
        self.assertTrue(decision.should_train)


if __name__ == "__main__":
    unittest.main()
