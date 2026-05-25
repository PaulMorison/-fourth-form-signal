from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from surfaces.promotions.reporting.decision_surface_inspection_builder import (  # noqa: E402
    PromotionDecisionSurfaceInspectionBuilder,
)


def _inspection_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "promotion_row_key": ["r1", "r2", "r3", "r4"],
            "promotion_name": ["Half Price", "Half Price", "Bundle", "Bundle"],
            "promo_type": ["Discount", "Discount", "Bundle", "Bundle"],
            "inferred_supplier_number": [10, 10, 20, 20],
            "department": ["Beauty", "Beauty", "Health", "Health"],
            "store_number": [1, 2, 1, 2],
            "cohort_key_archetype_primary": ["price_led", "price_led", "bundle_led", "bundle_led"],
            "cohort_key_archetype_secondary": ["price_repeatable", "price_repeatable", "bundle_sparse", "bundle_sparse"],
            "decision_recommendation": ["strong_go", "watch", "high_risk", "avoid"],
            "final_decision_score": [0.84, 0.51, 0.28, 0.11],
            "final_confidence_score": [0.78, 0.44, 0.31, 0.22],
            "decision_alignment_score": [0.90, 0.62, 0.41, 0.20],
            "margin_risk_penalty": [0.10, 0.34, 0.63, 0.81],
            "leftover_risk_penalty": [0.08, 0.22, 0.55, 0.74],
            "sparse_history_penalty": [0.00, 0.25, 0.55, 0.85],
            "row_cohort_disagreement_score": [0.10, 0.38, 0.57, 0.72],
        }
    )


class PromotionDecisionSurfaceInspectionReportingTests(unittest.TestCase):
    def test_inspection_builder_writes_sibling_outputs_and_grouped_rollups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            artifacts = PromotionDecisionSurfaceInspectionBuilder().write_reports(
                run_id="decision-inspection",
                decision_surface_frame=_inspection_frame(),
                calibration_summary={"rows_with_similarity": 4},
                thresholds_used={
                    "similarity_threshold": 0.55,
                    "archetype_confidence_floor": 0.45,
                    "row_model_confidence_floor": 0.45,
                },
                diagnostics_summary={
                    "sparse_cohort_rate": 0.50,
                    "low_confidence_row_rate": 0.50,
                    "row_cohort_disagreement_rate": 0.50,
                },
                artifact_paths=artifact_paths,
            )

            self.assertTrue(Path(artifacts.manifest_path).exists())
            self.assertIn("inspection_top_100_strongest_promotions", artifacts.report_paths)
            self.assertIn("inspection_promotion_review_packet", artifacts.report_paths)
            self.assertIn("inspection_summary_by_archetype_secondary", artifacts.report_paths)
            self.assertIn("inspection_management_review_rollup", artifacts.report_paths)
            self.assertNotEqual(
                Path(artifacts.manifest_path),
                artifact_paths.decision_surface_manifest_path("decision-inspection"),
            )

            review_packet = pd.read_csv(
                artifacts.report_paths["inspection_promotion_review_packet"]["csv"]
            )
            archetype_secondary_summary = pd.read_csv(
                artifacts.report_paths["inspection_summary_by_archetype_secondary"]["csv"]
            )
            management_rollup = pd.read_csv(
                artifacts.report_paths["inspection_management_review_rollup"]["csv"]
            )

            self.assertFalse(review_packet.empty)
            self.assertIn("promotion_start_date", review_packet.columns)
            self.assertIn("predicted_gross_profit", review_packet.columns)
            self.assertIn("leftover_risk_penalty", review_packet.columns)
            self.assertIn("stockout_risk_penalty", review_packet.columns)
            self.assertIn("overallocation_risk_penalty", review_packet.columns)
            self.assertIn("underallocation_risk_penalty", review_packet.columns)
            self.assertIn("archetype_secondary", review_packet.columns)
            self.assertIn("decision_recommendation_reason", review_packet.columns)
            self.assertFalse(archetype_secondary_summary.empty)
            self.assertIn("cohort_key_archetype_secondary", archetype_secondary_summary.columns)
            self.assertFalse(management_rollup.empty)
            self.assertIn("metric_group", management_rollup.columns)
