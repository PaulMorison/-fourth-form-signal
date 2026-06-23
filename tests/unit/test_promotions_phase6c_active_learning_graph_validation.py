from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_phase6c_active_learning_graph_validation import (  # noqa: E402
    RELEASE_RECOMMENDATION,
    build_active_learning_review_queue,
    enrich_knowledge_graph_edges,
    repair_graph_coverage,
    validate_adjacent_path_against_actuals,
    validate_available_to_sell_confidence,
    validate_feature_visibility_counts,
    write_phase6c_diagnostics,
)
from surfaces.promotions.reporting.promo_operating_pack_export import run_store_772_reporting_export  # noqa: E402


def _row(**overrides) -> dict:
    base = {
        "store_number": 772,
        "promotion_id": "P1",
        "sku_number": "101",
        "department": "SKIN",
        "category": "FACE",
        "actual_units_sold_promo": 5.0,
        "model_expected_units_total_promo": 3.0,
        "model_expected_units_total_promo_calibrated": 3.5,
        "segment_calibrated_expected_units": 4.0,
        "promo_days": 7,
        "promo_demand_source_quality": "LOW",
        "current_soh": 2.0,
        "stockout_suspected_flag": 0,
        "long_tail_sku_flag": "YES",
        "mission_sku_score": 55,
        "basket_attachment_source_quality": "LOW",
        "supplier_replenishment_regime": "NORMAL",
        "feature_basket_3plus_attach_rate": 0.2,
        "final_governed_action_label": "TOP_UP_TO_OPTIMAL",
        "final_governed_order_units": 2,
        "human_review_status": "PENDING",
        "lesson_learned_label": "PENDING_REVIEW",
        "weak_history_flag": "YES",
        "new_line_flag": "NO",
        "adjacent_expected_units": 6.0,
        "adjacent_confidence_score": 0.85,
        "available_to_sell_confidence_score": 0.3,
        "ats_confidence_label": "LOW",
        "ats_false_zero_demand_risk": "NO",
        "dag_state_coverage_score": 0.4,
        "economic_net_value_score": 100,
        "segment_calibration_allowed_flag": "NO",
        "adjacent_path_value_delta_vs_model": 3.0,
        "nearest_adjacent_simulation_required_flag": "YES",
    }
    base.update(overrides)
    return base


class TestPhase6cActiveLearningGraphValidation(unittest.TestCase):
    def test_feature_inventory_reconciliation(self) -> None:
        frame = pd.DataFrame([_row()])
        visibility = pd.DataFrame([{
            "feature_name": "mission_sku_score",
            "feature_family": "basket_trust",
            "available_in_source_frame_flag": "YES",
            "used_by_brain_model_flag": "YES",
            "used_by_governance_flag": "NO",
            "used_by_report_flag": "NO",
            "excluded_from_brain_reason": "",
            "legacy_hardcoded_limit_flag": "NO",
            "recommended_action": "KEEP",
        }])
        summary, detail = validate_feature_visibility_counts(frame, visibility)
        self.assertEqual(summary.iloc[0]["count_reconciliation_status"], "RECONCILED")
        self.assertIn("column_name", detail.columns)

    def test_adjacent_path_validation_metrics(self) -> None:
        frame = pd.DataFrame([_row(), _row(sku_number="102", actual_units_sold_promo=2.0, adjacent_expected_units=2.5)])
        validated = validate_adjacent_path_against_actuals(frame)
        self.assertIn("adjacent_path_validation_status", validated.columns)
        self.assertIn("validation_summary", validated.attrs)

    def test_active_learning_queue_ranks(self) -> None:
        frame = pd.DataFrame([_row(), _row(sku_number="102", economic_net_value_score=10, adjacent_confidence_score=0.95)])
        queue = build_active_learning_review_queue(frame)
        self.assertIn("active_learning_rank", queue.columns)
        self.assertEqual(int(queue.iloc[0]["active_learning_rank"]), 1)
        self.assertIn(queue.iloc[0]["priority_bucket"], {"TOP_25_HUMAN_REVIEW", "TOP_50_HUMAN_REVIEW", "TOP_100_HUMAN_REVIEW", "DATA_REPAIR_FIRST", "NOT_SELECTED"})

    def test_active_learning_does_not_create_orders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase6c_diagnostics(diagnostics_dir=diag, source_frame=pd.DataFrame([_row()]))
            auto = list(diag.rglob("*auto*order*"))
            self.assertEqual(len(auto), 0)
            self.assertFalse(result.get("auto_order_created", True))

    def test_graph_repair_identifies_missing_nodes(self) -> None:
        frame = pd.DataFrame([_row()])
        coverage = pd.DataFrame([{"node_name": "brain_forecast", "populated_flag": "YES"}])
        repair = repair_graph_coverage(frame, coverage)
        self.assertFalse(repair.empty)
        self.assertIn("node_or_edge_type", repair.columns)

    def test_kg_enrichment_creates_edges(self) -> None:
        edges, lift = enrich_knowledge_graph_edges(pd.DataFrame([_row()]))
        self.assertFalse(edges.empty)
        self.assertIn("edge_type", edges.columns)

    def test_ats_validation_detects_weak_logic(self) -> None:
        frame = pd.DataFrame([
            _row(actual_units_sold_promo=0.0, current_soh=5.0, ats_false_zero_demand_risk="NO"),
            _row(sku_number="102", actual_units_sold_promo=0.0, current_soh=4.0, ats_false_zero_demand_risk="NO"),
        ])
        ats = validate_available_to_sell_confidence(frame)
        self.assertIn("validation_status", ats.attrs)

    def test_ml_roadmap_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            write_phase6c_diagnostics(diagnostics_dir=diag, source_frame=pd.DataFrame([_row()]))
            roadmap = pd.read_csv(diag / "phase6c01_ml_innovation_implementation_roadmap.csv")
            self.assertIn("phase6c_validation_result", roadmap.columns)
            self.assertTrue(roadmap["implementation_status"].notna().any())

    def test_store_772_export_status_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_root = Path(tmp) / "export"
            diag6c = Path(tmp) / "phase6c"
            result = run_store_772_reporting_export(
                export_root=export_root,
                phase6c_dir=diag6c,
                phase6b_dir=Path(tmp) / "phase6b",
            )
            self.assertTrue((diag6c / "phase6c01_store_reporting_export_status.csv").exists())
            self.assertIn("export_folder", result)

    def test_manager_summary_fields_populated_via_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            write_phase6c_diagnostics(diagnostics_dir=diag, source_frame=pd.DataFrame([_row()]))
            gate = pd.read_csv(diag / "phase6c01_release_gate.csv")
            self.assertIn("phase6c_active_learning_candidates", gate.columns)
            self.assertIn("kg_enriched_edge_count", gate.columns)

    def test_governed_actions_not_overwritten(self) -> None:
        frame = pd.DataFrame([_row()])
        before = str(frame.iloc[0]["final_governed_action_label"])
        queue = build_active_learning_review_queue(frame)
        self.assertEqual(str(queue.iloc[0]["final_governed_action_label"]), before)

    def test_release_status_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_phase6c_diagnostics(diagnostics_dir=Path(tmp), source_frame=pd.DataFrame([_row()]))
            self.assertEqual(result["release_recommendation"], RELEASE_RECOMMENDATION)
            self.assertFalse(result.get("governed_actions_overwritten", True))


if __name__ == "__main__":
    unittest.main()
