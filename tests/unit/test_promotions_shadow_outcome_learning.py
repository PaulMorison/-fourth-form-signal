from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_shadow_observation_journal import (  # noqa: E402
    CORRECTNESS_LABELS,
    HUMAN_BUYER_DECISIONS,
    LESSON_LEARNED_LABELS,
    MERGE_KEY_COLUMNS,
    PHASE5U_DIAGNOSTICS_DIR,
    build_shadow_lesson_frame,
    build_shadow_observation_journal,
    load_shadow_human_review_template,
    merge_actual_outcomes,
    merge_human_review_decisions,
    score_shadow_outcomes,
    write_phase5u_diagnostics,
)
from tests.unit.test_promotions_promo_shadow_candidate_selection import _eligible_row  # noqa: E402


def _shadow_frame(n: int = 30) -> pd.DataFrame:
    from models.promotions.promo_shadow_candidate_selection import build_shadow_candidate_selection_frame

    rows = [_eligible_row(sku_number=str(100 + i), promotion_id=f"P{i % 8}", economic_net_value_score=float(i)) for i in range(n)]
    return build_shadow_candidate_selection_frame(pd.DataFrame(rows))


def _journal(n: int = 5) -> pd.DataFrame:
    return build_shadow_observation_journal(_shadow_frame(n), config={"shadow_run_id": "phase5t01-test"})


def _keys_row(journal: pd.DataFrame, idx: int = 0) -> dict:
    row = journal.iloc[idx]
    return {k: row[k] for k in MERGE_KEY_COLUMNS}


class TestShadowOutcomeLearning(unittest.TestCase):
    def test_human_merge_validates_allowed_decisions(self) -> None:
        journal = _journal(3)
        human = journal[list(MERGE_KEY_COLUMNS)].copy()
        human["human_buyer_decision"] = ""
        human["human_order_units"] = ""
        human["human_confidence_score"] = ""
        human.loc[0, "human_buyer_decision"] = "BUY_AS_BRAIN_SUGGESTED"
        human.loc[0, "human_order_units"] = "4"
        human.loc[0, "human_confidence_score"] = "80"
        human.loc[1, "human_buyer_decision"] = "INVALID_CHOICE"
        human.loc[1, "human_order_units"] = "2"
        merged = merge_human_review_decisions(journal, human)
        by_sku = merged.set_index("sku_number")
        self.assertEqual(by_sku.loc["100", "human_review_status"], "COMPLETE")
        self.assertEqual(by_sku.loc["101", "human_review_status"], "INVALID")
        self.assertEqual(by_sku.loc["102", "human_review_status"], "PENDING")

    def test_duplicate_human_decisions_flagged(self) -> None:
        journal = _journal(2)
        keys = _keys_row(journal, 0)
        human = pd.DataFrame([
            {**keys, "human_buyer_decision": "HOLD", "human_order_units": 0, "human_confidence_score": 50},
            {**keys, "human_buyer_decision": "BUY_AS_GOVERNED_SUGGESTED", "human_order_units": 1, "human_confidence_score": 60},
        ])
        merged = merge_human_review_decisions(journal, human)
        self.assertTrue((merged["human_decision_validation_error"].astype(str).str.contains("duplicate")).any())

    def test_missing_human_decisions_remain_pending(self) -> None:
        journal = _journal(4)
        merged = merge_human_review_decisions(journal, journal[list(MERGE_KEY_COLUMNS)].copy())
        self.assertEqual(int(merged["human_review_status"].eq("PENDING").sum()), 4)
        self.assertEqual(int(merged["human_decision_merge_status"].eq("NOT_MERGED").sum()), 4)

    def test_actual_outcomes_merge_on_keys(self) -> None:
        journal = _journal(3)
        actuals = journal[["store_number", "promotion_id", "sku_number"]].copy()
        actuals["actual_units_sold_promo"] = [10.0, 0.0, 5.0]
        actuals["actual_gp_promo"] = [35.0, 0.0, 12.0]
        merged = merge_actual_outcomes(journal, actuals)
        self.assertEqual(int(merged["actual_outcome_merge_status"].eq("MERGED").sum()), 2)
        self.assertEqual(int(merged["actual_outcome_merge_status"].eq("MISSING").sum()), 1)

    def test_missing_actuals_marked_unscorable(self) -> None:
        journal = _journal(2)
        actuals = journal[["store_number", "promotion_id", "sku_number"]].copy()
        scored = score_shadow_outcomes(journal, actuals)
        self.assertTrue(scored["brain_action_correctness_label"].isin(["UNSCORABLE", "DATA_QUALITY_BLOCKED"]).any())

    def test_stockout_gets_censored_label(self) -> None:
        journal = _journal(1)
        actuals = journal[["store_number", "promotion_id", "sku_number"]].copy()
        actuals["actual_units_sold_promo"] = 8.0
        actuals["actual_gp_promo"] = 20.0
        actuals["actual_stockout_flag"] = "YES"
        scored = score_shadow_outcomes(journal, actuals)
        self.assertEqual(scored.iloc[0]["lesson_learned_label"], "CENSORED_BY_STOCKOUT")
        self.assertEqual(scored.iloc[0]["brain_action_correctness_label"], "CENSORED")

    def test_supplier_failure_not_model_failure(self) -> None:
        journal = _journal(1)
        human = journal[list(MERGE_KEY_COLUMNS)].copy()
        human["human_buyer_decision"] = "SUPPLIER_UNAVAILABLE"
        human["human_order_units"] = "0"
        human["human_confidence_score"] = "90"
        actuals = journal[["store_number", "promotion_id", "sku_number"]].copy()
        actuals["actual_units_sold_promo"] = 0.0
        frame = build_shadow_lesson_frame(journal, human_review_df=human, actuals_df=actuals)
        self.assertEqual(frame.iloc[0]["lesson_learned_label"], "SUPPLIER_FAILURE")
        self.assertEqual(frame.iloc[0]["brain_action_correctness_label"], "SUPPLIER_FAILURE")
        self.assertEqual(frame.iloc[0]["brain_update_recommendation"], "NO_MODEL_UPDATE")

    def test_value_deltas_calculated(self) -> None:
        journal = _journal(1)
        actuals = journal[["store_number", "promotion_id", "sku_number"]].copy()
        actuals["actual_units_sold_promo"] = 12.0
        actuals["actual_gp_promo"] = 40.0
        scored = score_shadow_outcomes(journal, actuals)
        for col in (
            "brain_value_realised_proxy",
            "human_value_realised_proxy",
            "governed_value_realised_proxy",
            "brain_vs_human_value_delta",
            "brain_vs_governed_value_delta",
            "human_vs_governed_value_delta",
        ):
            self.assertIn(col, scored.columns)
            self.assertFalse(pd.isna(scored.iloc[0][col]))

    def test_lesson_labels_populated(self) -> None:
        journal = _journal(3)
        actuals = journal[["store_number", "promotion_id", "sku_number"]].copy()
        actuals["actual_units_sold_promo"] = [10.0, 0.0, 6.0]
        actuals["actual_gp_promo"] = [30.0, 0.0, 18.0]
        scored = score_shadow_outcomes(journal, actuals)
        labels = set(scored["lesson_learned_label"].astype(str))
        self.assertTrue(labels.issubset(set(LESSON_LEARNED_LABELS)))

    def test_correctness_labels_allowed_set(self) -> None:
        journal = _journal(2)
        actuals = journal[["store_number", "promotion_id", "sku_number"]].copy()
        actuals["actual_units_sold_promo"] = [10.0, 0.0]
        scored = score_shadow_outcomes(journal, actuals)
        for col in ("brain_action_correctness_label", "human_action_correctness_label", "governed_action_correctness_label"):
            self.assertTrue(set(scored[col].astype(str)).issubset(set(CORRECTNESS_LABELS)))

    def test_phase5u_diagnostics_written(self) -> None:
        journal = _journal(8)
        actuals = _shadow_frame(80)
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase5u_diagnostics(journal_df=journal, actuals_df=actuals, diagnostics_dir=diag)
            for name in (
                "phase5u01_human_review_ingestion_summary.csv",
                "phase5u01_actual_outcome_ingestion_summary.csv",
                "phase5u01_shadow_scored_outcomes.csv",
                "phase5u01_lesson_learned_summary.csv",
                "phase5u01_brain_vs_human_scorecard.csv",
                "phase5u01_model_update_recommendations.csv",
                "phase5u01_release_gate.csv",
            ):
                self.assertTrue((diag / name).exists(), name)
            self.assertEqual(result["release_recommendation"], "NO_RELEASE")
            gate = pd.read_csv(diag / "phase5u01_release_gate.csv")
            self.assertEqual(gate.iloc[0]["auto_order_created"], "NO")
            self.assertEqual(gate.iloc[0]["governed_actions_overwritten"], "NO")

    def test_governed_actions_not_overwritten(self) -> None:
        frame = _shadow_frame(10)
        before = frame["final_governed_action_label"].copy()
        journal = build_shadow_observation_journal(frame)
        actuals = frame.copy()
        actuals["actual_units_sold_promo"] = 5.0
        scored = score_shadow_outcomes(journal, actuals)
        after = frame["final_governed_action_label"]
        self.assertTrue((before == after).all())
        self.assertIn("final_governed_action_label", scored.columns)

    def test_no_order_file_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            write_phase5u_diagnostics(journal_df=_journal(5), actuals_df=_shadow_frame(20), diagnostics_dir=diag)
            order_like = [p for p in diag.glob("*order*")]
            self.assertEqual(order_like, [])

    def test_load_human_review_template_requires_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "human.csv"
            pd.DataFrame({"store_number": ["1"]}).to_csv(path, index=False)
            with self.assertRaises(ValueError):
                load_shadow_human_review_template(path)

    def test_human_decision_allowed_values_reference(self) -> None:
        for decision in HUMAN_BUYER_DECISIONS:
            self.assertIn(decision, HUMAN_BUYER_DECISIONS)


if __name__ == "__main__":
    unittest.main()
