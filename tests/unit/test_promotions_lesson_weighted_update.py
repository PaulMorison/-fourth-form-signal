from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_lesson_weighted_update import (  # noqa: E402
    ADVISORY_COLUMNS,
    DEFAULT_DIAGNOSTICS_DIR,
    build_lesson_weighted_training_frame,
    derive_brain_update_weights,
    derive_governance_threshold_recommendations,
    derive_human_review_policy_recommendations,
    write_phase5v_diagnostics,
)
from models.promotions.promo_shadow_observation_journal import (  # noqa: E402
    build_shadow_observation_journal,
    score_shadow_outcomes,
)
from tests.unit.test_promotions_promo_shadow_candidate_selection import _eligible_row  # noqa: E402


def _scored_frame(labels: list[str]) -> pd.DataFrame:
    from models.promotions.promo_shadow_candidate_selection import build_shadow_candidate_selection_frame

    n = len(labels)
    rows = [_eligible_row(sku_number=str(100 + i), promotion_id=f"P{i}", economic_net_value_score=float(i + 1)) for i in range(n)]
    frame = build_shadow_candidate_selection_frame(pd.DataFrame(rows))
    journal = build_shadow_observation_journal(frame, config={"shadow_run_id": "phase5v-test"})
    actuals = journal[["store_number", "promotion_id", "sku_number"]].copy()
    actuals["actual_units_sold_promo"] = [10.0] * n
    actuals["actual_gp_promo"] = [30.0] * n
    scored = score_shadow_outcomes(journal, actuals)
    for i, label in enumerate(labels):
        scored.at[i, "lesson_learned_label"] = label
        scored.at[i, "lesson_learned_note"] = f"test note for {label}"
        if label == "CENSORED_BY_STOCKOUT":
            scored.at[i, "actual_stockout_flag"] = "YES"
        if label in {"LONG_TAIL_PROTECTION_CONFIRMED", "MISSION_SKU_SIGNAL_CONFIRMED"}:
            scored.at[i, "long_tail_sku_flag"] = "YES"
    return scored


class TestLessonWeightedUpdate(unittest.TestCase):
    def test_lesson_labels_map_to_update_recommendations(self) -> None:
        frame = build_lesson_weighted_training_frame(_scored_frame(["BRAIN_WRONG_HUMAN_RIGHT", "LONG_TAIL_PROTECTION_CONFIRMED"]))
        self.assertTrue(set(ADVISORY_COLUMNS).issubset(set(frame.columns)))
        self.assertEqual(frame.iloc[0]["brain_update_recommendation"], "REVIEW_ACTION_CLASSIFIER")
        self.assertEqual(frame.iloc[1]["long_tail_reinforcement_flag"], "YES")

    def test_brain_wrong_human_right_penalises_brain(self) -> None:
        frame = build_lesson_weighted_training_frame(_scored_frame(["BRAIN_WRONG_HUMAN_RIGHT"]))
        self.assertGreater(float(frame.iloc[0]["brain_negative_reinforcement_weight"]), 0.0)
        brain = derive_brain_update_weights(frame)
        self.assertEqual(brain.iloc[0]["recommended_update_type"], "REVIEW_ACTION_CLASSIFIER")

    def test_governance_too_conservative_review_not_auto_relax(self) -> None:
        frame = build_lesson_weighted_training_frame(_scored_frame(["GOVERNANCE_TOO_CONSERVATIVE"] * 3))
        self.assertEqual(frame.iloc[0]["governance_relaxation_candidate_flag"], "YES")
        gov = derive_governance_threshold_recommendations(frame)
        conservative = gov.loc[gov["governance_rule"].eq("governance_conservative_buy_threshold")]
        self.assertIn(conservative.iloc[0]["recommendation"], {"REVIEW_FOR_RELAXATION", "REQUIRE_MORE_EVIDENCE"})
        self.assertEqual(conservative.iloc[0]["requires_human_approval_flag"], "YES")

    def test_long_tail_confirmed_increases_reinforcement(self) -> None:
        frame = build_lesson_weighted_training_frame(_scored_frame(["LONG_TAIL_PROTECTION_CONFIRMED"] * 12))
        self.assertEqual(frame.iloc[0]["long_tail_reinforcement_flag"], "YES")
        brain = derive_brain_update_weights(frame)
        self.assertEqual(brain.iloc[0]["recommended_update_type"], "INCREASE_FEATURE_WEIGHT")

    def test_supplier_failure_not_model_failure(self) -> None:
        frame = build_lesson_weighted_training_frame(_scored_frame(["SUPPLIER_FAILURE"]))
        self.assertEqual(frame.iloc[0]["brain_update_recommendation"], "NO_MODEL_FAILURE")
        brain = derive_brain_update_weights(frame)
        self.assertEqual(brain.iloc[0]["recommended_update_type"], "REVIEW_SUPPLIER_RISK_MODEL")

    def test_censored_outcomes_not_clean_training_targets(self) -> None:
        frame = build_lesson_weighted_training_frame(_scored_frame(["CENSORED_BY_STOCKOUT"]))
        self.assertEqual(frame.iloc[0]["next_learning_action"], "EXCLUDE_FROM_TRAINING")
        brain = derive_brain_update_weights(frame)
        self.assertEqual(brain.iloc[0]["recommended_update_type"], "REVIEW_STOCK_TRUTH_MODEL")
        self.assertIn("Advisory only", brain.iloc[0]["risk_note"])

    def test_missing_human_review_creates_data_quality_priority(self) -> None:
        frame = build_lesson_weighted_training_frame(_scored_frame(["BRAIN_RIGHT_HUMAN_RIGHT"] * 5))
        from models.promotions.promo_lesson_weighted_update import build_data_quality_update_priorities

        dq = build_data_quality_update_priorities(frame, human_review_complete_rate=0.0)
        self.assertTrue(dq["data_issue"].astype(str).str.contains("missing_filled_human_review").any())

    def test_advisory_fields_only_no_governed_change(self) -> None:
        scored = _scored_frame(["BRAIN_WRONG_HUMAN_RIGHT"])
        before = scored["final_governed_action_label"].iloc[0]
        frame = build_lesson_weighted_training_frame(scored)
        self.assertEqual(frame.iloc[0]["final_governed_action_label"], before)

    def test_release_status_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase5v_diagnostics(scored_df=_scored_frame(["GOVERNANCE_TOO_CONSERVATIVE"]), diagnostics_dir=diag)
            gate = pd.read_csv(diag / "phase5v01_release_gate.csv")
            self.assertEqual(result["release_recommendation"], "NO_RELEASE")
            self.assertEqual(gate.iloc[0]["auto_order_created"], "NO")
            self.assertEqual(gate.iloc[0]["governed_actions_overwritten"], "NO")

    def test_phase5v_diagnostics_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            write_phase5v_diagnostics(scored_df=_scored_frame(["BRAIN_WRONG_HUMAN_RIGHT", "LONG_TAIL_PROTECTION_CONFIRMED"]), diagnostics_dir=diag)
            for name in (
                "phase5v01_brain_update_recommendations.csv",
                "phase5v01_governance_threshold_review.csv",
                "phase5v01_long_tail_reinforcement_review.csv",
                "phase5v01_human_review_policy.csv",
                "phase5v01_data_quality_update_priorities.csv",
                "phase5v01_lesson_weighted_training_frame.csv",
                "phase5v01_release_gate.csv",
            ):
                self.assertTrue((diag / name).exists(), name)

    def test_human_review_policy_maintains_review(self) -> None:
        frame = build_lesson_weighted_training_frame(_scored_frame(["BRAIN_WRONG_HUMAN_RIGHT"] * 5))
        policy = derive_human_review_policy_recommendations(frame)
        self.assertEqual(policy.iloc[0]["review_required_recommendation"], "MAINTAIN_HUMAN_REVIEW")
        self.assertEqual(policy.iloc[0]["operational_trial_recommendation"], "DO_NOT_MOVE_TO_OPERATIONAL_TRIAL")


if __name__ == "__main__":
    unittest.main()
