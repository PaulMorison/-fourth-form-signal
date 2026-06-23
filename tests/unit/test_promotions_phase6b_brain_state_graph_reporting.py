from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_adjacent_path_simulation import (  # noqa: E402
    build_available_to_sell_confidence,
    score_adjacent_path_confidence,
    simulate_adjacent_outcome_paths,
    write_phase6b_adjacent_path_diagnostics,
)
from models.promotions.promo_brain_state_audit import (  # noqa: E402
    RELEASE_RECOMMENDATION,
    audit_brain_feature_visibility,
    build_ml_innovation_audit,
    detect_legacy_hardcoded_feature_limits,
    write_phase6b_state_audit_diagnostics,
)
from models.promotions.promo_decision_graph_memory import (  # noqa: E402
    build_promo_decision_dag,
    build_promo_knowledge_graph_edges,
    derive_graph_memory_features,
    write_phase6b_graph_memory_diagnostics,
)
from models.promotions.promo_phase6b_orchestrator import write_phase6b_diagnostics  # noqa: E402
from surfaces.promotions.reporting.promo_operating_pack_export import run_store_772_reporting_export  # noqa: E402


def _row(**overrides) -> dict:
    base = {
        "store_number": 772,
        "promotion_id": "P1",
        "sku_number": "101",
        "department": "SKIN",
        "category": "FACE",
        "actual_units_sold_promo": 0.0,
        "model_expected_units_total_promo": 0.0,
        "promo_days": 7,
        "promo_demand_source_quality": "LOW",
        "current_soh": 2.0,
        "expected_soh_at_promo_start_before_order": 2.0,
        "stockout_suspected_flag": 0,
        "long_tail_sku_flag": "YES",
        "mission_sku_score": 55,
        "basket_attachment_source_quality": "LOW",
        "supplier_replenishment_regime": "NORMAL",
        "stock_position_regime": "BALANCED",
        "promo_convexity_regime": "HIGH",
        "discount_percent": 15,
        "feature_basket_3plus_attach_rate": 0.2,
        "final_governed_action_label": "TOP_UP_TO_OPTIMAL",
        "final_governed_order_units": 2,
        "human_review_status": "PENDING",
        "lesson_learned_label": "PENDING_REVIEW",
    }
    base.update(overrides)
    return base


class TestPhase6bBrainStateGraphReporting(unittest.TestCase):
    def test_feature_visibility_audit(self) -> None:
        frame = pd.DataFrame([_row(), _row(sku_number="102", actual_units_sold_promo=5.0)])
        vis = audit_brain_feature_visibility(frame)
        self.assertIn("used_by_brain_model_flag", vis.columns)
        self.assertIn("legacy_hardcoded_limit_flag", vis.columns)

    def test_legacy_hardcoded_limit_review(self) -> None:
        legacy = detect_legacy_hardcoded_feature_limits()
        self.assertFalse(legacy.empty)
        self.assertIn("severity", legacy.columns)

    def test_adjacent_references_for_weak_history(self) -> None:
        frame = pd.DataFrame([_row(), _row(sku_number="102", actual_units_sold_promo=8.0, department="SKIN")])
        sim = simulate_adjacent_outcome_paths(frame)
        weak = sim.loc[sim["weak_history_flag"].eq("YES")]
        self.assertGreater(len(weak), 0)
        self.assertTrue(_numeric(sim.get("adjacent_expected_units", 0)).gt(0).any())

    def test_new_line_not_zero_demand(self) -> None:
        frame = pd.DataFrame([_row(), _row(sku_number="102", actual_units_sold_promo=10.0)])
        sim = score_adjacent_path_confidence(simulate_adjacent_outcome_paths(frame))
        new_line = sim.loc[sim["new_line_flag"].eq("YES")]
        if not new_line.empty:
            self.assertTrue(float(new_line.iloc[0]["adjacent_expected_units"]) > 0)

    def test_adjacent_confidence_calculated(self) -> None:
        frame = pd.DataFrame([_row(), _row(sku_number="102", actual_units_sold_promo=5.0)])
        sim = score_adjacent_path_confidence(simulate_adjacent_outcome_paths(frame))
        self.assertIn("adjacent_confidence_score", sim.columns)
        self.assertGreaterEqual(float(sim["adjacent_confidence_score"].max()), 0.0)

    def test_ats_false_zero_demand_risk(self) -> None:
        frame = pd.DataFrame([_row(current_soh=3.0, actual_units_sold_promo=0.0)])
        ats = build_available_to_sell_confidence(frame)
        self.assertIn("ats_false_zero_demand_risk", ats.columns)

    def test_dag_and_kg_edges(self) -> None:
        dag = build_promo_decision_dag()
        self.assertGreater(len(dag), 0)
        kg = build_promo_knowledge_graph_edges(pd.DataFrame([_row()]))
        self.assertFalse(kg.empty)

    def test_graph_memory_features(self) -> None:
        frame = pd.DataFrame([_row(), _row(sku_number="102")])
        sim = simulate_adjacent_outcome_paths(frame)
        mem = derive_graph_memory_features(sim, build_promo_knowledge_graph_edges(sim))
        self.assertIn("dag_state_coverage_score", mem.columns)
        self.assertIn("kg_basket_centrality_score", mem.columns)

    def test_phase6b_diagnostics_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            frame = pd.DataFrame([_row(), _row(sku_number="102", actual_units_sold_promo=6.0)])
            result = write_phase6b_diagnostics(diagnostics_dir=diag, source_frame=frame)
            required = [
                "phase6b01_feature_visibility_audit.csv",
                "phase6b01_legacy_hardcoded_limit_review.csv",
                "phase6b01_adjacent_path_simulation.csv",
                "phase6b01_new_line_weak_history_review.csv",
                "phase6b01_available_to_sell_confidence.csv",
                "phase6b01_decision_dag_edges.csv",
                "phase6b01_knowledge_graph_edges.csv",
                "phase6b01_graph_memory_features.csv",
                "phase6b01_graph_coverage_audit.csv",
                "phase6b01_ml_innovation_audit.csv",
                "phase6b01_release_gate.csv",
            ]
            for fname in required:
                self.assertTrue((diag / fname).exists(), fname)
            self.assertEqual(result["release_recommendation"], RELEASE_RECOMMENDATION)

    def test_ml_innovation_audit(self) -> None:
        ml = build_ml_innovation_audit()
        self.assertIn("recommended_status", ml.columns)
        self.assertTrue(ml["recommended_status"].isin({"IMPLEMENT_NOW", "PROTOTYPE_NEXT", "DEFER", "REJECT_FOR_NOW"}).any())

    def test_governed_actions_not_overwritten(self) -> None:
        frame = pd.DataFrame([_row()])
        sim = simulate_adjacent_outcome_paths(frame)
        self.assertEqual(str(sim.iloc[0]["final_governed_action_label"]), "TOP_UP_TO_OPTIMAL")

    def test_no_auto_order_file_in_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            write_phase6b_diagnostics(diagnostics_dir=diag, source_frame=pd.DataFrame([_row()]))
            auto = list(diag.rglob("*auto*order*"))
            self.assertEqual(len(auto), 0)

    def test_release_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_phase6b_diagnostics(diagnostics_dir=Path(tmp), source_frame=pd.DataFrame([_row()]))
            self.assertEqual(result["release_recommendation"], "NO_RELEASE")


def _numeric(series, default=0.0):
    return pd.to_numeric(series, errors="coerce").fillna(default)


if __name__ == "__main__":
    unittest.main()
