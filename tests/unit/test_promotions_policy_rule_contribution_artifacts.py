from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import (  # noqa: E402
    PromotionModelTrainer,
    _build_policy_rule_contribution_artifacts,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


RULE_NAMES = (
    "sparse_history_multi_driver_baseline_only",
    "falling_base_launch_conflict_review",
    "weak_same_discount_and_uplift_cap",
    "weak_elasticity_uplift_restraint",
    "stock_gap_high_review_cap",
)


def _base_rule_row() -> dict[str, object]:
    return {
        "replay_measurement_eligible_flag": 1.0,
        "replay_capital_removed": 0.0,
        "replay_units_removed": 0.0,
        "replay_policy_excess_capital": 0.0,
        "replay_policy_excess_units": 0.0,
        **{rule_name: 0.0 for rule_name in RULE_NAMES},
    }


def _contribution_rows() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    sparse_solo = _base_rule_row()
    sparse_solo["sparse_history_multi_driver_baseline_only"] = 1.0
    sparse_solo["replay_capital_removed"] = 100.0
    sparse_solo["replay_units_removed"] = 10.0
    sparse_solo["replay_policy_excess_capital"] = 50.0
    sparse_solo["replay_policy_excess_units"] = 5.0
    rows.append(sparse_solo)

    same_discount_and_elasticity_overlap = _base_rule_row()
    same_discount_and_elasticity_overlap["weak_same_discount_and_uplift_cap"] = 1.0
    same_discount_and_elasticity_overlap["weak_elasticity_uplift_restraint"] = 1.0
    same_discount_and_elasticity_overlap["replay_capital_removed"] = 40.0
    same_discount_and_elasticity_overlap["replay_units_removed"] = 4.0
    same_discount_and_elasticity_overlap["replay_policy_excess_capital"] = 80.0
    same_discount_and_elasticity_overlap["replay_policy_excess_units"] = 8.0
    rows.append(same_discount_and_elasticity_overlap)

    same_discount_solo = _base_rule_row()
    same_discount_solo["weak_same_discount_and_uplift_cap"] = 1.0
    same_discount_solo["replay_capital_removed"] = 20.0
    same_discount_solo["replay_units_removed"] = 2.0
    same_discount_solo["replay_policy_excess_capital"] = 30.0
    same_discount_solo["replay_policy_excess_units"] = 3.0
    rows.append(same_discount_solo)

    falling_and_stock_gap_overlap = _base_rule_row()
    falling_and_stock_gap_overlap["falling_base_launch_conflict_review"] = 1.0
    falling_and_stock_gap_overlap["stock_gap_high_review_cap"] = 1.0
    falling_and_stock_gap_overlap["replay_capital_removed"] = 10.0
    falling_and_stock_gap_overlap["replay_units_removed"] = 1.0
    falling_and_stock_gap_overlap["replay_policy_excess_capital"] = 90.0
    falling_and_stock_gap_overlap["replay_policy_excess_units"] = 9.0
    rows.append(falling_and_stock_gap_overlap)

    return pd.DataFrame(rows)


def _overlap_dominant_rows() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    sparse_and_same = _base_rule_row()
    sparse_and_same["sparse_history_multi_driver_baseline_only"] = 1.0
    sparse_and_same["weak_same_discount_and_uplift_cap"] = 1.0
    sparse_and_same["replay_capital_removed"] = 50.0
    sparse_and_same["replay_units_removed"] = 5.0
    sparse_and_same["replay_policy_excess_capital"] = 90.0
    sparse_and_same["replay_policy_excess_units"] = 9.0
    rows.append(sparse_and_same)

    falling_and_stock = _base_rule_row()
    falling_and_stock["falling_base_launch_conflict_review"] = 1.0
    falling_and_stock["stock_gap_high_review_cap"] = 1.0
    falling_and_stock["replay_capital_removed"] = 40.0
    falling_and_stock["replay_units_removed"] = 4.0
    falling_and_stock["replay_policy_excess_capital"] = 95.0
    falling_and_stock["replay_policy_excess_units"] = 9.5
    rows.append(falling_and_stock)

    same_and_elasticity = _base_rule_row()
    same_and_elasticity["weak_same_discount_and_uplift_cap"] = 1.0
    same_and_elasticity["weak_elasticity_uplift_restraint"] = 1.0
    same_and_elasticity["replay_capital_removed"] = 30.0
    same_and_elasticity["replay_units_removed"] = 3.0
    same_and_elasticity["replay_policy_excess_capital"] = 100.0
    same_and_elasticity["replay_policy_excess_units"] = 10.0
    rows.append(same_and_elasticity)

    return pd.DataFrame(rows)


class PromotionPolicyRuleContributionArtifactTests(unittest.TestCase):
    def test_rule_contribution_totals_report_overlap_inclusive_removed_capital(self) -> None:
        artifacts = _build_policy_rule_contribution_artifacts(_contribution_rows())

        summary_payload = artifacts["summary_payload"]
        summary_frame = artifacts["summary_frame"]

        self.assertEqual(summary_payload["top_capital_removing_rule"], "sparse_history_multi_driver_baseline_only")
        self.assertEqual(summary_payload["top_solo_effect_rule"], "sparse_history_multi_driver_baseline_only")
        self.assertEqual(set(summary_frame["rule_name"].astype(str).tolist()), set(RULE_NAMES))

        sparse_row = summary_frame.loc[
            summary_frame["rule_name"].astype(str).eq("sparse_history_multi_driver_baseline_only")
        ].iloc[0]
        same_discount_row = summary_frame.loc[
            summary_frame["rule_name"].astype(str).eq("weak_same_discount_and_uplift_cap")
        ].iloc[0]

        self.assertEqual(int(sparse_row["triggered_row_count"]), 1)
        self.assertAlmostEqual(float(sparse_row["capital_removed_total"]), 100.0)
        self.assertAlmostEqual(float(sparse_row["share_of_total_replay_capital_removed"]), 100.0 / 170.0)
        self.assertEqual(int(same_discount_row["triggered_row_count"]), 2)
        self.assertAlmostEqual(float(same_discount_row["capital_removed_total"]), 60.0)
        self.assertAlmostEqual(float(same_discount_row["average_capital_removed_per_triggered_row"]), 30.0)
        self.assertAlmostEqual(float(same_discount_row["median_capital_removed_per_triggered_row"]), 30.0)

    def test_rule_overlap_matrix_is_pairwise_correct(self) -> None:
        artifacts = _build_policy_rule_contribution_artifacts(_contribution_rows())
        overlap_frame = artifacts["overlap_matrix_frame"]
        overlap_payload = artifacts["overlap_matrix_payload"]

        same_elasticity_row = overlap_frame.loc[
            overlap_frame["rule_name"].astype(str).eq("weak_same_discount_and_uplift_cap")
            & overlap_frame["overlap_rule_name"].astype(str).eq("weak_elasticity_uplift_restraint")
        ].iloc[0]
        same_same_row = overlap_frame.loc[
            overlap_frame["rule_name"].astype(str).eq("weak_same_discount_and_uplift_cap")
            & overlap_frame["overlap_rule_name"].astype(str).eq("weak_same_discount_and_uplift_cap")
        ].iloc[0]

        self.assertEqual(int(same_elasticity_row["overlap_row_count"]), 1)
        self.assertAlmostEqual(float(same_elasticity_row["overlap_capital_removed_total"]), 40.0)
        self.assertAlmostEqual(float(same_elasticity_row["overlap_capital_removed_share_of_rule_total"]), 40.0 / 60.0)
        self.assertEqual(int(same_same_row["overlap_row_count"]), 2)
        self.assertAlmostEqual(float(same_same_row["overlap_capital_removed_total"]), 60.0)
        self.assertEqual(
            overlap_payload["matrix"]["weak_same_discount_and_uplift_cap"]["weak_elasticity_uplift_restraint"]["overlap_row_count"],
            1,
        )

    def test_rule_solo_vs_overlap_decomposition_is_correct(self) -> None:
        artifacts = _build_policy_rule_contribution_artifacts(_contribution_rows())
        solo_vs_overlap_frame = artifacts["solo_vs_overlap_frame"]

        same_discount_row = solo_vs_overlap_frame.loc[
            solo_vs_overlap_frame["rule_name"].astype(str).eq("weak_same_discount_and_uplift_cap")
        ].iloc[0]
        elasticity_row = solo_vs_overlap_frame.loc[
            solo_vs_overlap_frame["rule_name"].astype(str).eq("weak_elasticity_uplift_restraint")
        ].iloc[0]

        self.assertEqual(int(same_discount_row["solo_trigger_row_count"]), 1)
        self.assertEqual(int(same_discount_row["overlap_trigger_row_count"]), 1)
        self.assertAlmostEqual(float(same_discount_row["solo_capital_removed_total"]), 20.0)
        self.assertAlmostEqual(float(same_discount_row["overlap_capital_removed_total"]), 40.0)
        self.assertAlmostEqual(float(same_discount_row["solo_units_removed_total"]), 2.0)
        self.assertAlmostEqual(float(same_discount_row["overlap_units_removed_total"]), 4.0)
        self.assertEqual(int(elasticity_row["solo_trigger_row_count"]), 0)
        self.assertEqual(int(elasticity_row["overlap_trigger_row_count"]), 1)
        self.assertAlmostEqual(float(elasticity_row["overlap_capital_removed_share_of_rule_total"]), 1.0)

    def test_refinement_candidate_returns_null_when_overlap_dominates(self) -> None:
        artifacts = _build_policy_rule_contribution_artifacts(_overlap_dominant_rows())
        candidate_payload = artifacts["refinement_candidate_payload"]

        self.assertIsNone(candidate_payload["refinement_candidate"])
        self.assertEqual(candidate_payload["recommended_next_move"], "stop_policy_work")
        self.assertIn("Overlap dominates", candidate_payload["explanation"])

    def test_rule_contribution_artifacts_persist_with_trainer_owned_paths(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="promotions-policy-rule-contribution-run",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            training_artifacts = PromotionModelTrainer().train(
                run_id="promotions-policy-rule-contribution-run",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )

            contribution_paths = training_artifacts.policy_rule_contribution_artifact_paths or {}
            self.assertEqual(
                set(contribution_paths.keys()),
                {
                    "summary_json_path",
                    "summary_csv_path",
                    "overlap_matrix_json_path",
                    "overlap_matrix_csv_path",
                    "solo_vs_overlap_json_path",
                    "solo_vs_overlap_csv_path",
                    "refinement_candidate_json_path",
                },
            )
            for path_value in contribution_paths.values():
                self.assertTrue(Path(path_value).exists())

            summary_payload = json.loads(Path(contribution_paths["summary_json_path"]).read_text(encoding="utf-8"))
            summary_frame = pd.read_csv(contribution_paths["summary_csv_path"])
            overlap_payload = json.loads(Path(contribution_paths["overlap_matrix_json_path"]).read_text(encoding="utf-8"))
            overlap_frame = pd.read_csv(contribution_paths["overlap_matrix_csv_path"])
            solo_payload = json.loads(Path(contribution_paths["solo_vs_overlap_json_path"]).read_text(encoding="utf-8"))
            candidate_payload = json.loads(Path(contribution_paths["refinement_candidate_json_path"]).read_text(encoding="utf-8"))

            self.assertEqual(summary_payload["row_scope"], "out_of_sample_validation_and_test")
            self.assertEqual(tuple(summary_payload["rule_order"]), RULE_NAMES)
            self.assertIn("top_capital_removing_rule", summary_payload)
            self.assertEqual(set(summary_frame["rule_name"].astype(str).tolist()), set(RULE_NAMES))
            self.assertEqual(tuple(overlap_payload["rule_order"]), RULE_NAMES)
            self.assertEqual(len(overlap_frame.index), len(RULE_NAMES) * len(RULE_NAMES))
            self.assertEqual(len(solo_payload["rows"]), len(RULE_NAMES))
            self.assertIn("refinement_candidate", candidate_payload)
            self.assertIn("recommended_next_move", candidate_payload)


if __name__ == "__main__":
    unittest.main()