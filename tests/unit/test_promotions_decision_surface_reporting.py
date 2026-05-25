from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.cohorts.diagnostics import PromotionDecisionDiagnosticsResult  # noqa: E402
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from surfaces.promotions.reporting.decision_surface_report_builder import (  # noqa: E402
    PromotionDecisionSurfaceReportBuilder,
)


def _decision_surface_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "promotion_row_key": ["r1", "r2", "r3"],
            "decision_recommendation": ["strong_go", "avoid", "watch"],
            "final_decision_score": [0.82, 0.12, 0.48],
            "final_confidence_score": [0.76, 0.22, 0.36],
            "row_cohort_disagreement_score": [0.12, 0.68, 0.38],
            "sparse_history_penalty": [0.0, 0.85, 0.55],
            "margin_risk_penalty": [0.12, 0.82, 0.34],
            "leftover_risk_penalty": [0.08, 0.74, 0.22],
            "overallocation_risk_penalty": [0.10, 0.79, 0.28],
        }
    )


def _diagnostics_result() -> PromotionDecisionDiagnosticsResult:
    grouped = pd.DataFrame(
        {
            "row_count": [2],
            "average_final_decision_score": [0.40],
            "average_final_confidence_score": [0.35],
            "disagreement_rate": [0.50],
            "sparse_history_rate": [0.50],
            "low_confidence_rate": [0.50],
            "failure_rate": [0.50],
            "margin_trap_rate": [0.50],
            "leftover_risk_rate": [0.50],
            "stockout_risk_rate": [0.25],
            "feature_missing_rate": [0.10],
        }
    )
    by_store = grouped.copy()
    by_store.insert(0, "store_number", 1)
    by_supplier = grouped.copy()
    by_supplier.insert(0, "inferred_supplier_number", 10)
    by_department = grouped.copy()
    by_department.insert(0, "department", "Beauty")
    by_archetype = grouped.copy()
    by_archetype.insert(0, "cohort_key_archetype_secondary", "arch-1")
    by_archetype.insert(1, "nearest_archetype_key", "arch-1")
    return PromotionDecisionDiagnosticsResult(
        summary={"row_count": 3, "sparse_cohort_rate": 0.33},
        by_store_frame=by_store,
        by_supplier_frame=by_supplier,
        by_department_frame=by_department,
        by_archetype_frame=by_archetype,
    )


class PromotionDecisionSurfaceReportingTests(unittest.TestCase):
    def test_report_builder_writes_decision_surface_outputs_without_manifest_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            artifacts = PromotionDecisionSurfaceReportBuilder().write_reports(
                run_id="decision-reporting",
                decision_surface_frame=_decision_surface_frame(),
                diagnostics_result=_diagnostics_result(),
                metrics={"row_count": 3},
                disagreement_cutoff=0.35,
                artifact_paths=artifact_paths,
                manifest_payload={"run_id": "decision-reporting", "thresholds_used": {"similarity_threshold": 0.55}},
            )

            self.assertTrue(Path(artifacts.manifest_path).exists())
            self.assertTrue(Path(artifacts.metrics_path).exists())
            self.assertTrue(Path(artifacts.diagnostics_summary_path).exists())
            self.assertIn("promotion_decision_surface", artifacts.report_paths)
            self.assertIn("diagnostics_by_store", artifacts.report_paths)
            self.assertNotEqual(
                Path(artifacts.manifest_path),
                artifact_paths.cohort_manifest_path("decision-reporting"),
            )
            self.assertNotEqual(
                Path(artifacts.manifest_path),
                artifact_paths.cohort_report_manifest_path("decision-reporting"),
            )
