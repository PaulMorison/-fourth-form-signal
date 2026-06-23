from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_active_learning_review_pack import (  # noqa: E402
    WORKBOOK_FILENAME,
    build_active_learning_workbook_sheets,
    write_active_learning_review_pack_diagnostics,
)
from models.promotions.promo_adjacent_path_simulation import (  # noqa: E402
    ADJACENT_USE_POLICIES,
    assign_adjacent_path_policies,
    calibrate_adjacent_path_confidence,
    write_phase6d_adjacent_calibration_diagnostics,
)
from models.promotions.promo_decision_graph_memory import (  # noqa: E402
    DAG_NODES,
    derive_dag_state_features,
    populate_repairable_dag_nodes,
    validate_dag_state_population,
    write_phase6d_graph_diagnostics,
)
from models.promotions.promo_phase6d_orchestrator import (  # noqa: E402
    RELEASE_RECOMMENDATION,
    build_feature_merge_opportunity_review,
    build_segment_calibration_eligibility_repair,
    write_phase6d_diagnostics,
)
from surfaces.promotions.reporting.promo_operating_pack_export import run_store_772_reporting_export  # noqa: E402


def _row(**overrides) -> dict:
    base = {
        "store_number": 772,
        "promotion_id": "P1",
        "sku_number": "101",
        "promotion_name": "Test Promo",
        "department": "SKIN",
        "category": "FACE",
        "actual_units_sold_promo": 5.0,
        "model_expected_units_total_promo": 3.0,
        "model_expected_units_total_promo_calibrated": 3.5,
        "segment_calibrated_expected_units": 4.0,
        "segment_bias_factor": 1.1,
        "current_soh": 2.0,
        "expected_soh_at_promo_start_before_order": 2.0,
        "supplier_replenishment_regime": "NORMAL",
        "feature_basket_3plus_attach_rate": 0.2,
        "basket_attachment_source_quality": "HIGH",
        "mission_sku_score": 55,
        "mission_sku_flag": "YES",
        "available_to_sell_confidence_score": 0.3,
        "ats_confidence_label": "LOW",
        "expected_promo_uplift_units": 1.5,
        "target_end_promo_soh": 3.0,
        "adjacent_expected_units": 6.0,
        "adjacent_confidence_score": 0.91,
        "final_governed_action_label": "TOP_UP_TO_OPTIMAL",
        "final_governed_order_units": 2,
        "human_review_status": "PENDING",
        "lesson_learned_label": "PENDING_REVIEW",
        "weak_history_flag": "YES",
        "new_line_flag": "NO",
        "long_tail_sku_flag": "YES",
        "promo_demand_source_quality": "LOW",
        "demand_observation_quality": "LOW",
        "calibration_eligible_flag": "NO",
        "stockout_suspected_flag": 0,
        "segment_calibration_eligible_flag": "NO",
        "active_learning_score": 30.0,
        "active_learning_rank": 1,
        "active_learning_reason": "LOW_ATS_CONFIDENCE",
        "expected_information_gain": 0.3,
        "human_review_question": "Review?",
        "which_model_component_will_learn": "ats",
        "priority_bucket": "TOP_25_HUMAN_REVIEW",
    }
    base.update(overrides)
    return base


class TestPhase6dDagActiveLearningAdjacent(unittest.TestCase):
    def test_dag_nodes_populated_when_evidence_exists(self) -> None:
        frame = pd.DataFrame([_row()])
        populated = populate_repairable_dag_nodes(frame)
        self.assertEqual(populated.iloc[0]["dag_brain_forecast_available_flag"], "YES")
        self.assertIn("dag_raw_transaction_history_available_flag", populated.columns)

    def test_missing_nodes_labelled_not_invented(self) -> None:
        frame = pd.DataFrame([{"store_number": 772, "promotion_id": "P1", "sku_number": "101"}])
        populated = populate_repairable_dag_nodes(frame)
        self.assertEqual(populated.iloc[0]["dag_brain_forecast_available_flag"], "NO")
        self.assertNotEqual(populated.iloc[0]["dag_brain_forecast_missing_reason"], "")

    def test_dag_coverage_v2_calculated(self) -> None:
        frame = pd.DataFrame([_row()])
        enriched = derive_dag_state_features(populate_repairable_dag_nodes(frame))
        self.assertIn("dag_state_coverage_score_v2", enriched.columns)
        self.assertGreater(float(enriched.iloc[0]["dag_state_coverage_score_v2"]), 0.0)

    def test_adjacent_confidence_reduced(self) -> None:
        frame = pd.DataFrame([_row()])
        calibrated = calibrate_adjacent_path_confidence(frame)
        raw = float(calibrated.iloc[0]["adjacent_confidence_raw"])
        cal = float(calibrated.iloc[0]["adjacent_confidence_calibrated"])
        self.assertLess(cal, raw)

    def test_adjacent_policy_advisory_only(self) -> None:
        frame = pd.DataFrame([_row(), _row(sku_number="102", basket_attachment_source_quality="LOW")])
        policies = assign_adjacent_path_policies(frame)
        self.assertTrue(policies["adjacent_path_use_policy"].isin(ADJACENT_USE_POLICIES).all())
        self.assertNotIn("REPLACE_FORECAST", policies["adjacent_path_use_policy"].tolist())

    def test_active_learning_workbook_sheets(self) -> None:
        pack = pd.DataFrame([_row()])
        sheets = build_active_learning_workbook_sheets(pack)
        required = {
            "Top_100_Active_Learning", "Low_ATS_Confidence", "Model_Adjacent_Disagreement",
            "Weak_History_New_Lines", "Long_Tail_Mission_SKUs", "Graph_Missing_State",
            "Instructions", "Allowed_Values",
        }
        self.assertTrue(required.issubset(set(sheets.keys())))

    def test_feature_merge_opportunity_review(self) -> None:
        frame = pd.DataFrame([_row()])
        visibility = pd.DataFrame([{
            "feature_name": "average_daily_units",
            "feature_family": "demand_uplift",
            "available_in_source_frame_flag": "NO",
            "used_by_brain_model_flag": "YES",
            "recommended_action": "BUILD_OR_MERGE_FEATURE",
            "legacy_hardcoded_limit_flag": "NO",
        }])
        review = build_feature_merge_opportunity_review(frame, visibility)
        self.assertFalse(review.empty)
        self.assertIn("merge_blocker", review.columns)

    def test_segment_calibration_eligibility_repair(self) -> None:
        repair = build_segment_calibration_eligibility_repair(pd.DataFrame([_row(), _row(sku_number="102")]))
        self.assertFalse(repair.empty)
        self.assertIn("path_to_eligibility", repair.columns)

    def test_phase6d_diagnostics_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase6d_diagnostics(diagnostics_dir=diag, source_frame=pd.DataFrame([_row(), _row(sku_number="102")]))
            required = [
                "phase6d01_dag_state_population.csv",
                "phase6d01_dag_state_coverage_summary.csv",
                "phase6d01_adjacent_confidence_calibration.csv",
                "phase6d01_adjacent_policy_review.csv",
                "phase6d01_active_learning_review_pack_summary.csv",
                "phase6d01_feature_merge_opportunity_review.csv",
                "phase6d01_segment_calibration_eligibility_repair.csv",
                "phase6d01_release_gate.csv",
            ]
            for fname in required:
                self.assertTrue((diag / fname).exists(), fname)
            self.assertIn("dag_state_coverage_score_v2", result)

    def test_store_export_status_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_root = Path(tmp) / "export"
            diag6d = Path(tmp) / "phase6d"
            result = run_store_772_reporting_export(
                export_root=export_root,
                phase6d_dir=diag6d,
                phase6c_dir=Path(tmp) / "phase6c",
                phase6b_dir=Path(tmp) / "phase6b",
            )
            self.assertTrue((diag6d / "phase6d01_store_reporting_export_status.csv").exists())
            self.assertIn("phase6e_operating_pack", result["export_folder"])

    def test_governed_actions_not_overwritten(self) -> None:
        frame = pd.DataFrame([_row()])
        before = str(frame.iloc[0]["final_governed_action_label"])
        after = assign_adjacent_path_policies(frame)
        self.assertEqual(str(after.iloc[0]["final_governed_action_label"]), before)

    def test_no_auto_order_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            write_phase6d_diagnostics(diagnostics_dir=diag, source_frame=pd.DataFrame([_row()]))
            auto = list(diag.rglob("*auto*order*"))
            self.assertEqual(len(auto), 0)

    def test_release_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_phase6d_diagnostics(diagnostics_dir=Path(tmp), source_frame=pd.DataFrame([_row()]))
            self.assertEqual(result["release_recommendation"], RELEASE_RECOMMENDATION)

    def test_graph_diagnostics_node_count(self) -> None:
        node_df, summary = validate_dag_state_population(pd.DataFrame([_row()]))
        self.assertEqual(len(node_df), len(DAG_NODES))
        self.assertIn("dag_state_coverage_score_v2", summary.columns)

    def test_active_learning_review_pack_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            queue = pd.DataFrame([_row()])
            result = write_active_learning_review_pack_diagnostics(queue, diagnostics_dir=diag)
            self.assertGreaterEqual(result["active_learning_review_rows"], 1)
            if result["workbook_written"]:
                self.assertTrue((diag / WORKBOOK_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()
