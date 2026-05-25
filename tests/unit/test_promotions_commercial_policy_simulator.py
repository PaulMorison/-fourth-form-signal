from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.commercial_policy_simulator import (  # noqa: E402
    SIMULATED_HOLD,
    SIMULATED_INCONCLUSIVE,
    SIMULATED_LOOSEN,
    SIMULATED_TIGHTEN,
    SIMULATION_LOW_COVERAGE,
    SIMULATION_READY,
    _validate_simulation_consistency,
    build_commercial_policy_simulation_artifacts,
)


def _attr_row(
    *,
    store: int,
    sku: int,
    action: str = "ACTION_PUBLISH_NOW",
    eligibility: str = "publishable",
    demand: str = "healthy_nonzero_demand",
    status: str = "ATTRIBUTION_READY",
    eff_class: str = "EFFECTIVE_STRONG",
    confidence: str = "HIGH",
) -> dict[str, object]:
    return {
        "store_number": str(store),
        "sku_number": str(sku),
        "promotion_start_date": "2024-09-01",
        "promotion_end_date": "2024-09-07",
        "operator_action_class": action,
        "publish_eligibility_class": eligibility,
        "demand_evidence_class": demand,
        "attribution_status": status,
        "recommendation_effectiveness_class": eff_class,
        "attribution_confidence_class": confidence,
    }


class CommercialPolicySimulatorTests(unittest.TestCase):
    def test_low_coverage_readiness_class(self) -> None:
        rows = [_attr_row(store=1, sku=100 + i) for i in range(4)]
        artifacts = build_commercial_policy_simulation_artifacts(
            attribution=pd.DataFrame(rows),
            calibration_summary={"threshold_direction_class": "HOLD_POLICY", "policy_signal_class": "POLICY_SIGNAL_HOLD"},
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertEqual(artifacts.summary.simulation_readiness_class, SIMULATION_LOW_COVERAGE)
        self.assertEqual(artifacts.summary.simulated_policy_direction_class, SIMULATED_INCONCLUSIVE)

    def test_tighten_scenario_decreases_publish_rows(self) -> None:
        rows = []
        for i in range(10):
            rows.append(
                _attr_row(
                    store=2,
                    sku=200 + i,
                    action="ACTION_PUBLISH_NOW",
                    eligibility="publishable",
                    demand="low_nonzero_demand" if i < 6 else "healthy_nonzero_demand",
                    eff_class="HARMFUL" if i < 6 else "EFFECTIVE_MODERATE",
                    confidence="LOW" if i < 6 else "HIGH",
                )
            )
        artifacts = build_commercial_policy_simulation_artifacts(
            attribution=pd.DataFrame(rows),
            calibration_summary={
                "threshold_direction_class": "TIGHTEN_PUBLISH_POLICY",
                "policy_signal_class": "POLICY_SIGNAL_WEAKEN",
            },
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertEqual(artifacts.summary.simulated_policy_direction_class, SIMULATED_TIGHTEN)
        self.assertLess(artifacts.summary.net_publish_delta, 0)

    def test_loosen_scenario_increases_publish_rows(self) -> None:
        rows = []
        for i in range(12):
            rows.append(
                _attr_row(
                    store=3,
                    sku=300 + i,
                    action="ACTION_REVIEW_NOW" if i < 8 else "ACTION_PUBLISH_NOW",
                    eligibility="review_required" if i < 8 else "publishable",
                    demand="low_nonzero_demand",
                    eff_class="EFFECTIVE_STRONG",
                    confidence="HIGH",
                )
            )
        artifacts = build_commercial_policy_simulation_artifacts(
            attribution=pd.DataFrame(rows),
            calibration_summary={
                "threshold_direction_class": "LOOSEN_PUBLISH_POLICY",
                "policy_signal_class": "POLICY_SIGNAL_STRENGTHEN",
            },
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertEqual(artifacts.summary.simulated_policy_direction_class, SIMULATED_LOOSEN)
        self.assertGreater(artifacts.summary.net_publish_delta, 0)

    def test_hold_scenario_keeps_changes_minimal(self) -> None:
        rows = [_attr_row(store=4, sku=400 + i, eff_class="NEUTRAL") for i in range(10)]
        artifacts = build_commercial_policy_simulation_artifacts(
            attribution=pd.DataFrame(rows),
            calibration_summary={
                "threshold_direction_class": "HOLD_POLICY",
                "policy_signal_class": "POLICY_SIGNAL_HOLD",
            },
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertEqual(artifacts.summary.simulated_policy_direction_class, SIMULATED_HOLD)
        self.assertEqual(artifacts.summary.affected_row_count, 0)

    def test_simulation_by_segment_contains_required_columns(self) -> None:
        rows = [_attr_row(store=5, sku=500 + i, eff_class="EFFECTIVE_MODERATE") for i in range(10)]
        artifacts = build_commercial_policy_simulation_artifacts(
            attribution=pd.DataFrame(rows),
            calibration_summary={
                "threshold_direction_class": "LOOSEN_PUBLISH_POLICY",
                "policy_signal_class": "POLICY_SIGNAL_STRENGTHEN",
            },
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertFalse(artifacts.by_segment.empty)
        for column in [
            "segment_type",
            "segment_value",
            "baseline_publish_row_count",
            "simulated_publish_row_count",
            "net_publish_delta",
            "baseline_review_row_count",
            "simulated_review_row_count",
            "net_review_delta",
            "affected_row_count",
            "simulated_materiality_class",
            "simulated_risk_class",
            "recommended_attention_flag",
        ]:
            self.assertIn(column, artifacts.by_segment.columns)

    def test_watchlist_flags_high_risk_or_high_impact_segments(self) -> None:
        rows = []
        for i in range(12):
            rows.append(
                _attr_row(
                    store=6,
                    sku=600 + i,
                    action="ACTION_PUBLISH_NOW",
                    demand="low_nonzero_demand",
                    eff_class="HARMFUL",
                    confidence="LOW",
                )
            )
        artifacts = build_commercial_policy_simulation_artifacts(
            attribution=pd.DataFrame(rows),
            calibration_summary={
                "threshold_direction_class": "TIGHTEN_PUBLISH_POLICY",
                "policy_signal_class": "POLICY_SIGNAL_WEAKEN",
            },
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertFalse(artifacts.watchlist.empty)
        self.assertTrue(
            artifacts.watchlist["watch_reason"].isin(
                {
                    "HIGHEST_RISK_SEGMENT",
                    "HIGHEST_IMPACT_SEGMENT",
                    "LARGE_PUBLISH_DELTA_SEGMENT",
                    "WEAK_EVIDENCE_LARGE_EFFECT_SEGMENT",
                }
            ).any()
        )

    def test_counts_reconcile_between_baseline_and_simulated(self) -> None:
        rows = [_attr_row(store=7, sku=700 + i, eff_class="EFFECTIVE_STRONG") for i in range(12)]
        artifacts = build_commercial_policy_simulation_artifacts(
            attribution=pd.DataFrame(rows),
            calibration_summary={
                "threshold_direction_class": "LOOSEN_PUBLISH_POLICY",
                "policy_signal_class": "POLICY_SIGNAL_STRENGTHEN",
            },
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        source_count = len(rows)
        self.assertEqual(
            artifacts.summary.baseline_publish_row_count
            + artifacts.summary.baseline_review_row_count
            + artifacts.summary.baseline_excluded_row_count,
            source_count,
        )
        self.assertEqual(
            artifacts.summary.simulated_publish_row_count
            + artifacts.summary.simulated_review_row_count
            + artifacts.summary.simulated_excluded_row_count,
            source_count,
        )

    def test_contradiction_fails_loud_when_tighten_increases_publish(self) -> None:
        simulation_input = pd.DataFrame(
            [
                {
                    "store_number": "1",
                    "promotion_cycle": "2024-09-01_to_2024-09-07",
                    "attribution_status": "ATTRIBUTION_READY",
                    "baseline_state": "BASELINE_PUBLISH",
                    "simulated_state": "BASELINE_PUBLISH",
                    "affected_flag": False,
                }
            ]
        )
        summary = type(
            "S",
            (),
            {
                "baseline_publish_row_count": 1,
                "baseline_review_row_count": 0,
                "baseline_excluded_row_count": 0,
                "simulated_publish_row_count": 2,
                "simulated_review_row_count": 0,
                "simulated_excluded_row_count": 0,
                "affected_row_count": 0,
                "affected_store_count": 0,
                "affected_promotion_count": 0,
                "simulated_policy_direction_class": SIMULATED_TIGHTEN,
                "net_publish_delta": 1,
                "simulation_readiness_class": SIMULATION_READY,
                "simulated_materiality_class": "SIMULATION_HIGH_MATERIALITY",
                "simulated_risk_class": "SIMULATION_HIGH_RISK",
            },
        )()
        with self.assertRaises(ValueError):
            _validate_simulation_consistency(
                summary=summary,
                simulation_input=simulation_input,
                by_segment=pd.DataFrame([
                    {"segment_type": "store_number", "segment_value": "1"}
                ]),
                watchlist=pd.DataFrame([
                    {"segment_type": "store_number", "segment_value": "1"}
                ]),
            )

    def test_simulation_brief_includes_required_sections(self) -> None:
        rows = [_attr_row(store=8, sku=800 + i, eff_class="EFFECTIVE_MODERATE") for i in range(12)]
        artifacts = build_commercial_policy_simulation_artifacts(
            attribution=pd.DataFrame(rows),
            calibration_summary={
                "threshold_direction_class": "LOOSEN_PUBLISH_POLICY",
                "policy_signal_class": "POLICY_SIGNAL_STRENGTHEN",
            },
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        brief = artifacts.simulation_brief_markdown
        self.assertIn("## Simulation Readiness", brief)
        self.assertIn("## Baseline vs Simulated Outcome", brief)
        self.assertIn("## Biggest Winners", brief)
        self.assertIn("## Biggest Risks", brief)
        self.assertIn("## Watchlist", brief)
        self.assertIn("## Recommended Next Actions", brief)


if __name__ == "__main__":
    unittest.main()
