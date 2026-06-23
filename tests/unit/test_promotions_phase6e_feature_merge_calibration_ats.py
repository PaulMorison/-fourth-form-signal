from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_available_to_sell_evidence import (  # noqa: E402
    detect_censored_zero_demand_risk,
    strengthen_ats_confidence,
    write_phase6e_ats_diagnostics,
)
from models.promotions.promo_core_feature_merge import (  # noqa: E402
    build_feature_merge_plan,
    merge_safe_features_into_core_frame,
    validate_feature_merge_safety,
    write_phase6e_feature_merge_diagnostics,
)
from models.promotions.promo_phase6e_orchestrator import (  # noqa: E402
    RELEASE_RECOMMENDATION,
    build_brain_retraining_readiness,
    write_phase6e_diagnostics,
)
from surfaces.promotions.reporting.promo_operating_pack_export import run_store_772_reporting_export  # noqa: E402


def _row(**overrides) -> dict:
    base = {
        "store_number": 772,
        "promotion_id": "P1",
        "sku_number": "101",
        "department": "SKIN",
        "actual_units_sold_promo": 5.0,
        "model_expected_units_total_promo": 3.0,
        "current_soh": 2.0,
        "expected_soh_at_promo_start_before_order": 2.0,
        "promo_start_soh_source_quality": "HIGH",
        "stockout_suspected_flag": 0,
        "supplier_replenishment_regime": "NORMAL",
        "feature_basket_3plus_attach_rate": 0.2,
        "mission_sku_score": 55,
        "available_to_sell_confidence_score": 0.35,
        "ats_confidence_label": "LOW",
        "ats_stockout_censoring_risk": "NO",
        "weak_history_flag": "YES",
        "new_line_flag": "NO",
        "adjacent_confidence_calibrated": 0.32,
        "adjacent_path_use_policy": "USE_FOR_NEW_LINE_CONTEXT_ONLY",
        "adjacent_path_warning": "ADVISORY_SIMULATION_NOT_DEPLOYED",
        "dag_state_coverage_score_v2": 0.5,
        "active_learning_score": 25.0,
        "active_learning_reason": "LOW_ATS_CONFIDENCE",
        "expected_information_gain": 0.25,
        "which_model_component_will_learn": "ats",
        "final_governed_action_label": "TOP_UP_TO_OPTIMAL",
        "promo_demand_source_quality": "MEDIUM",
        "demand_observation_quality": "HIGH",
        "calibration_eligible_flag": "YES",
        "segment_calibration_eligible_flag": "YES",
    }
    base.update(overrides)
    return base


def _enrichment() -> pd.DataFrame:
    return pd.DataFrame([_row(), _row(sku_number="102", ats_confidence_label="UNKNOWN")])


class TestPhase6eFeatureMergeCalibrationAts(unittest.TestCase):
    def test_safe_features_merged(self) -> None:
        core = pd.DataFrame([_row()])
        enrich = _enrichment()
        plan = build_feature_merge_plan(core, enrich)
        merged, _ = merge_safe_features_into_core_frame(core, enrich, plan)
        self.assertIn("available_to_sell_confidence_score", merged.columns)
        self.assertIn("adjacent_path_use_policy", merged.columns)

    def test_leakage_blocked(self) -> None:
        core = pd.DataFrame([_row()])
        enrich = _enrichment()
        enrich["economic_net_value_score"] = 100.0
        result = validate_feature_merge_safety(
            "economic_net_value_score", enrichment_frame=enrich, core_frame=core,
        )
        self.assertEqual(result["merge_status"], "BLOCKED_LEAKAGE_RISK")

    def test_post_promo_actuals_blocked_from_merge_plan(self) -> None:
        core = pd.DataFrame([_row()])
        enrich = _enrichment()
        plan = build_feature_merge_plan(core, enrich)
        actual_rows = plan.loc[plan["feature_name"].eq("actual_units_sold_promo")]
        if not actual_rows.empty:
            self.assertIn("BLOCKED", actual_rows.iloc[0]["merge_status"])

    def test_unknown_labels_preserved(self) -> None:
        frame = strengthen_ats_confidence(pd.DataFrame([_row(ats_confidence_label="UNKNOWN")]))
        self.assertEqual(str(frame.iloc[0]["ats_confidence_label"]), "UNKNOWN")

    def test_adjacent_fields_advisory(self) -> None:
        core = pd.DataFrame([_row()])
        enrich = _enrichment()
        plan = build_feature_merge_plan(core, enrich)
        adj = plan.loc[plan["feature_name"].eq("adjacent_path_use_policy")]
        self.assertFalse(adj.empty)
        self.assertIn(adj.iloc[0]["merge_status"], {"MERGED_SAFE", "READY_TO_MERGE"})

    def test_ats_evidence_score_calculated(self) -> None:
        frame = strengthen_ats_confidence(pd.DataFrame([_row()]))
        self.assertIn("ats_evidence_score", frame.columns)
        self.assertGreater(float(frame.iloc[0]["ats_evidence_score"]), 0)

    def test_zero_sales_learnability_labelled(self) -> None:
        frame = detect_censored_zero_demand_risk(pd.DataFrame([
            _row(actual_units_sold_promo=0.0, stockout_suspected_flag=1),
        ]))
        self.assertIn("ats_zero_sales_learnable_flag", frame.columns)

    def test_calibration_eligibility_improves_without_deployment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_phase6e_diagnostics(diagnostics_dir=Path(tmp), source_frame=_enrichment())
            gate = pd.read_csv(Path(tmp) / "phase6e01_release_gate.csv")
            self.assertEqual(str(gate.iloc[0]["phase6a_deployment_status"]), "PROPOSED_NOT_DEPLOYED")
            self.assertIn("segment_calibration_eligibility_after_merge", str(list(Path(tmp).iterdir())))

    def test_retraining_readiness_generated(self) -> None:
        plan = build_feature_merge_plan(pd.DataFrame([_row()]), _enrichment())
        readiness = build_brain_retraining_readiness(_enrichment(), plan, pd.DataFrame())
        self.assertIn("recommended_training_status", readiness.columns)

    def test_phase6e_diagnostics_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            write_phase6e_diagnostics(diagnostics_dir=diag, source_frame=_enrichment())
            for fname in (
                "phase6e01_feature_merge_plan.csv",
                "phase6e01_core_frame_feature_merge_audit.csv",
                "phase6e01_ats_evidence_strengthening.csv",
                "phase6e01_segment_calibration_eligibility_after_merge.csv",
                "phase6e01_brain_retraining_readiness.csv",
                "phase6e01_release_gate.csv",
            ):
                self.assertTrue((diag / fname).exists(), fname)

    def test_store_export_status_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_store_772_reporting_export(
                export_root=Path(tmp) / "export",
                phase6e_dir=Path(tmp) / "phase6e",
                phase6d_dir=Path(tmp) / "phase6d",
                phase6c_dir=Path(tmp) / "phase6c",
                phase6b_dir=Path(tmp) / "phase6b",
            )
            self.assertIn("phase6e_operating_pack", result["export_folder"])

    def test_governed_actions_not_overwritten(self) -> None:
        core = pd.DataFrame([_row()])
        enrich = _enrichment()
        plan = build_feature_merge_plan(core, enrich)
        merged, _ = merge_safe_features_into_core_frame(core, enrich, plan)
        self.assertEqual(str(merged.iloc[0]["final_governed_action_label"]), "TOP_UP_TO_OPTIMAL")

    def test_no_auto_order_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_phase6e_diagnostics(diagnostics_dir=Path(tmp), source_frame=_enrichment())
            self.assertEqual(len(list(Path(tmp).rglob("*auto*order*"))), 0)

    def test_release_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_phase6e_diagnostics(diagnostics_dir=Path(tmp), source_frame=_enrichment())
            self.assertEqual(result["release_recommendation"], RELEASE_RECOMMENDATION)


if __name__ == "__main__":
    unittest.main()
