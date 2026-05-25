from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.cohorts import PromotionDecisionDiagnostics  # noqa: E402


def _diagnostics_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "promotion_row_key": ["r1", "r2", "r3", "r4"],
            "store_number": [1, 1, 2, 2],
            "inferred_supplier_number": [10, 10, 11, 12],
            "department": ["Beauty", "Beauty", "Health", "Health"],
            "cohort_key_promotion_name": ["a", "a", "b", "c"],
            "cohort_key_archetype_secondary": ["arch-1", "arch-1", "arch-2", "arch-3"],
            "nearest_archetype_key": ["arch-1", "arch-1", "arch-2", ""],
            "decision_recommendation": ["strong_go", "high_risk", "avoid", "watch"],
            "final_decision_score": [0.82, 0.28, 0.12, 0.46],
            "final_confidence_score": [0.76, 0.41, 0.22, 0.36],
            "row_cohort_disagreement_score": [0.18, 0.44, 0.72, 0.30],
            "sparse_history_penalty": [0.0, 0.25, 0.85, 0.55],
            "instability_penalty": [0.12, 0.28, 0.66, 0.48],
            "margin_risk_penalty": [0.12, 0.64, 0.84, 0.28],
            "leftover_risk_penalty": [0.08, 0.52, 0.72, 0.18],
            "overallocation_risk_penalty": [0.10, 0.58, 0.80, 0.22],
            "stockout_risk_penalty": [0.14, 0.36, 0.46, 0.24],
            "feature_discount_depth_pct": [0.20, 0.25, None, 0.18],
            "feature_composite_promo_instability": [0.12, 0.28, 0.66, None],
        }
    )


class PromotionDecisionDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_aggregate_expected_failure_surfaces(self) -> None:
        diagnostics = PromotionDecisionDiagnostics().analyze(
            _diagnostics_frame(),
            low_confidence_floor=0.40,
            disagreement_cutoff=0.35,
        )

        self.assertIn("sparse_cohort_rate", diagnostics.summary)
        self.assertIn("overconfidence_risk_buckets", diagnostics.summary)
        self.assertGreater(diagnostics.summary["row_cohort_disagreement_rate"], 0.0)
        self.assertIn("failure_rate", diagnostics.by_store_frame.columns)
        self.assertIn("feature_missing_rate", diagnostics.by_supplier_frame.columns)
        self.assertIn("margin_trap_rate", diagnostics.by_department_frame.columns)
        self.assertIn("sparse_history_rate", diagnostics.by_archetype_frame.columns)
