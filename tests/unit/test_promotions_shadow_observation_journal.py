from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_shadow_observation_journal import (  # noqa: E402
    HUMAN_BUYER_DECISIONS,
    HUMAN_TEMPLATE_COLUMNS,
    JOURNAL_COLUMNS,
    LESSON_LEARNED_LABELS,
    OUTCOME_PLACEHOLDER_COLUMNS,
    append_shadow_journal,
    build_allowed_values_reference,
    build_human_review_template,
    build_shadow_observation_journal,
    score_shadow_outcomes,
    write_phase5t_diagnostics,
)
from tests.unit.test_promotions_promo_shadow_candidate_selection import _eligible_row  # noqa: E402


def _shadow_frame(n: int = 120) -> pd.DataFrame:
    from models.promotions.promo_shadow_candidate_selection import build_shadow_candidate_selection_frame

    rows = [_eligible_row(sku_number=str(100 + i), promotion_id=f"P{i % 8}", economic_net_value_score=float(i)) for i in range(n)]
    return build_shadow_candidate_selection_frame(pd.DataFrame(rows))


class TestShadowJournal(unittest.TestCase):
    def test_at_most_top_100_rows(self) -> None:
        journal = build_shadow_observation_journal(_shadow_frame(120))
        self.assertLessEqual(len(journal), 100)

    def test_unique_journal_keys(self) -> None:
        journal = build_shadow_observation_journal(_shadow_frame(80))
        dup = journal.duplicated(subset=["shadow_run_id", "store_number", "promotion_id", "sku_number"]).sum()
        self.assertEqual(dup, 0)

    def test_required_identity_fields(self) -> None:
        journal = build_shadow_observation_journal(_shadow_frame(30))
        for col in ("shadow_run_id", "shadow_created_at", "store_number", "promotion_id", "sku_number"):
            self.assertIn(col, journal.columns)

    def test_brain_governed_human_outcome_fields(self) -> None:
        journal = build_shadow_observation_journal(_shadow_frame(30))
        for col in (
            "brain_validated_action_label", "final_governed_action_label", "human_buyer_decision",
            "actual_units_sold_promo", "lesson_learned_label",
        ):
            self.assertIn(col, journal.columns)

    def test_lesson_labels_in_reference(self) -> None:
        ref = build_allowed_values_reference()
        labels = set(ref.loc[ref["field_name"].eq("lesson_learned_label"), "allowed_value"])
        for label in LESSON_LEARNED_LABELS:
            self.assertIn(label, labels)

    def test_human_template_only_fillable_fields(self) -> None:
        journal = build_shadow_observation_journal(_shadow_frame(20))
        template = build_human_review_template(journal)
        self.assertTrue(set(template.columns).issubset(set(HUMAN_TEMPLATE_COLUMNS)))
        for col in HUMAN_BUYER_DECISIONS:
            self.assertIn(col, set(build_allowed_values_reference().loc[
                build_allowed_values_reference()["field_name"].eq("human_buyer_decision"), "allowed_value"
            ]))

    def test_summary_reconciles_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase5t_diagnostics(frame=_shadow_frame(80), diagnostics_dir=diag)
            summary = pd.read_csv(diag / "phase5t01_shadow_journal_summary.csv")
            self.assertEqual(int(summary["total_journal_rows"].iloc[0]), result["shadow_journal_rows"])
            self.assertLessEqual(int(summary["top_100_rows"].iloc[0]), 100)

    def test_governed_actions_not_in_journal_as_overwrites(self) -> None:
        frame = _shadow_frame(20)
        before = frame["final_governed_action_label"].copy()
        journal = build_shadow_observation_journal(frame)
        merged = frame.merge(
            journal[["sku_number", "final_governed_action_label"]].rename(
                columns={"final_governed_action_label": "journal_action"}
            ),
            on="sku_number",
            how="left",
        )
        self.assertTrue((before == merged["final_governed_action_label"]).all())

    def test_score_outcomes_adds_lesson(self) -> None:
        journal = build_shadow_observation_journal(_shadow_frame(10))
        actuals = journal[["store_number", "promotion_id", "sku_number"]].copy()
        actuals["actual_units_sold_promo"] = 5.0
        actuals["actual_gp_promo"] = 12.0
        scored = score_shadow_outcomes(journal, actuals)
        self.assertTrue(scored["lesson_learned_label"].astype(str).str.len().gt(0).all())

    def test_append_preserves_human_fields(self) -> None:
        base = build_shadow_observation_journal(_shadow_frame(5), config={"shadow_run_id": "run-a"})
        base.loc[0, "human_buyer_decision"] = "HOLD"
        new = build_shadow_observation_journal(_shadow_frame(5), config={"shadow_run_id": "run-a"})
        merged = append_shadow_journal(base, new)
        self.assertEqual(merged.loc[0, "human_buyer_decision"], "HOLD")


if __name__ == "__main__":
    unittest.main()
