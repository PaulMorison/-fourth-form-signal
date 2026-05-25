from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.commercial_action_instructions import (  # noqa: E402
    ACTION_INVESTIGATE_HARMFUL_RECOMMENDATIONS,
    ACTION_NO_ACTION_REQUIRED,
    ACTION_REVIEW_DUPLICATE_ONLY_NOOP,
    ACTION_REVIEW_HIGH_IMPACT_SIMULATION,
    ACTION_REVIEW_LOW_COVERAGE_SEGMENT,
    ATTENTION_IMMEDIATE,
    _build_segment_summary,
    _build_summary,
    _validate_instruction_consistency,
    build_commercial_action_instruction_artifacts,
)


def _base_current_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "store_number": "101",
                "sku_number": "9001",
                "promotion_start_date": "2026-05-01",
                "promotion_end_date": "2026-05-07",
                "promotion_id": "PROMO-1",
                "promotion_row_key": "ROW-1",
                "promotion_header_key": "HDR-1",
                "demand_evidence_class": "healthy_nonzero_demand",
                "publish_eligibility_class": "publishable",
            }
        ]
    )


def _base_explanations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "store_number": "101",
                "sku_number": "9001",
                "promotion_start_date": "2026-05-01",
                "promotion_end_date": "2026-05-07",
                "row_change_class": "CHANGED_ROW",
                "row_change_reason_code": "RECOMMENDATION_CHANGED",
                "operator_action_class": "ACTION_PUBLISH_NOW",
                "operator_priority_score": 90,
                "operator_priority_band": "HIGH",
                "duplicate_blocked_flag": False,
                "current_publish_eligibility_class": "publishable",
                "current_demand_evidence_class": "healthy_nonzero_demand",
            }
        ]
    )


def _base_attribution() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "store_number": "101",
                "sku_number": "9001",
                "promotion_start_date": "2026-05-01",
                "promotion_end_date": "2026-05-07",
                "attribution_status": "ATTRIBUTION_READY",
                "recommendation_effectiveness_class": "EFFECTIVE_STRONG",
                "attribution_confidence_class": "HIGH",
            }
        ]
    )


def _base_delta_top_changes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "store_number": "101",
                "sku_number": "9001",
                "promotion_start_date": "2026-05-01",
                "promotion_end_date": "2026-05-07",
                "changed_flag": True,
            }
        ]
    )


def _base_delta_store_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "store_number": "101",
                "materially_changed_flag": False,
            }
        ]
    )


def _base_calibration_summary() -> dict[str, object]:
    return {
        "calibration_readiness_class": "CALIBRATION_READY",
        "threshold_direction_class": "NO_THRESHOLD_RECOMMENDATION",
        "evidence_row_count": 25,
        "policy_signal_class": "POLICY_SIGNAL_INCONCLUSIVE",
    }


def _base_simulation_summary() -> dict[str, object]:
    return {
        "simulation_readiness_class": "SIMULATION_READY",
        "simulated_policy_direction_class": "SIMULATED_HOLD",
        "simulated_materiality_class": "SIMULATION_LOW_MATERIALITY",
        "simulated_risk_class": "SIMULATION_LOW_RISK",
    }


def _base_segment_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "segment_type": "demand_evidence_class",
                "segment_value": "healthy_nonzero_demand",
                "threshold_direction_class": "HOLD_POLICY",
                "watch_reason": "HIGHEST_IMPACT_SEGMENT",
                "simulated_materiality_class": "SIMULATION_LOW_MATERIALITY",
                "simulated_risk_class": "SIMULATION_LOW_RISK",
            }
        ]
    )


def _build_artifacts(
    *,
    current_frame: pd.DataFrame | None = None,
    explanations: pd.DataFrame | None = None,
    attribution: pd.DataFrame | None = None,
    delta_top_changes: pd.DataFrame | None = None,
    delta_store_summary: pd.DataFrame | None = None,
    calibration_summary: dict[str, object] | None = None,
    calibration_by_segment: pd.DataFrame | None = None,
    calibration_watchlist: pd.DataFrame | None = None,
    simulation_summary: dict[str, object] | None = None,
    simulation_by_segment: pd.DataFrame | None = None,
    simulation_watchlist: pd.DataFrame | None = None,
    freshness_class: str = "FRESH_PUBLICATION_OPPORTUNITY_PRESENT",
    outcome_class: str = "COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
    commercial_failure_flag: bool = False,
):
    with TemporaryDirectory() as temp_dir:
        current_path = Path(temp_dir) / "current.csv"
        (current_frame if current_frame is not None else _base_current_frame()).to_csv(current_path, index=False)

        return build_commercial_action_instruction_artifacts(
            run_id="action-test-run",
            current_store_prediction_csv_path=str(current_path),
            commercial_change_explanations=(explanations if explanations is not None else _base_explanations()),
            commercial_outcome_attribution=(attribution if attribution is not None else _base_attribution()),
            commercial_delta_top_changes=(delta_top_changes if delta_top_changes is not None else _base_delta_top_changes()),
            commercial_delta_store_summary=(delta_store_summary if delta_store_summary is not None else _base_delta_store_summary()),
            commercial_delta_summary={
                "delta_class": "DELTA_COMPARABLE",
                "materiality_class": "LOW_CHANGE",
                "comparable_prior_cycle_found_flag": True,
            },
            commercial_policy_calibration_summary=(calibration_summary if calibration_summary is not None else _base_calibration_summary()),
            commercial_policy_calibration_by_segment=(calibration_by_segment if calibration_by_segment is not None else pd.DataFrame()),
            commercial_policy_watchlist=(calibration_watchlist if calibration_watchlist is not None else pd.DataFrame()),
            commercial_policy_simulation_summary=(simulation_summary if simulation_summary is not None else _base_simulation_summary()),
            commercial_policy_simulation_by_segment=(simulation_by_segment if simulation_by_segment is not None else pd.DataFrame()),
            commercial_policy_simulation_watchlist=(simulation_watchlist if simulation_watchlist is not None else pd.DataFrame()),
            commercial_outcome_class=outcome_class,
            current_freshness_class=freshness_class,
            current_commercial_failure_flag=commercial_failure_flag,
        )


class CommercialActionInstructionTests(unittest.TestCase):
    def test_harmful_recommendation_evidence_creates_investigate_action(self) -> None:
        attribution = _base_attribution()
        attribution.loc[0, "recommendation_effectiveness_class"] = "HARMFUL"
        attribution.loc[0, "attribution_confidence_class"] = "HIGH"

        artifacts = _build_artifacts(attribution=attribution)
        self.assertIn(
            ACTION_INVESTIGATE_HARMFUL_RECOMMENDATIONS,
            set(artifacts.priority_queue["action_class"].astype(str)),
        )

    def test_high_impact_simulation_creates_review_action(self) -> None:
        simulation_watchlist = _base_segment_frame().copy()
        simulation_watchlist.loc[0, "simulated_materiality_class"] = "SIMULATION_HIGH_MATERIALITY"

        artifacts = _build_artifacts(simulation_watchlist=simulation_watchlist)
        self.assertIn(
            ACTION_REVIEW_HIGH_IMPACT_SIMULATION,
            set(artifacts.priority_queue["action_class"].astype(str)),
        )

    def test_low_evidence_segments_create_monitor_or_review_actions(self) -> None:
        attribution = _base_attribution()
        attribution.loc[0, "attribution_status"] = "ATTRIBUTION_NOT_YET_MATURE"
        attribution.loc[0, "attribution_confidence_class"] = "NONE"

        artifacts = _build_artifacts(
            attribution=attribution,
            calibration_summary={
                "calibration_readiness_class": "CALIBRATION_LOW_COVERAGE",
                "threshold_direction_class": "NO_THRESHOLD_RECOMMENDATION",
                "evidence_row_count": 2,
                "policy_signal_class": "POLICY_SIGNAL_INCONCLUSIVE",
            },
            simulation_summary={
                "simulation_readiness_class": "SIMULATION_LOW_COVERAGE",
                "simulated_policy_direction_class": "SIMULATED_INCONCLUSIVE",
                "simulated_materiality_class": None,
                "simulated_risk_class": None,
            },
        )

        classes = set(artifacts.priority_queue["action_class"].astype(str))
        self.assertIn(ACTION_REVIEW_LOW_COVERAGE_SEGMENT, classes)
        self.assertNotIn("TIGHTEN_POLICY_REVIEW", classes)
        self.assertNotIn("LOOSEN_POLICY_REVIEW", classes)

    def test_duplicate_only_noop_creates_review_or_no_action_path(self) -> None:
        explanations = _base_explanations()
        explanations.loc[0, "duplicate_blocked_flag"] = True

        artifacts = _build_artifacts(
            explanations=explanations,
            freshness_class="NO_NEW_PUBLICATIONS_DUPLICATE_ONLY",
        )

        top_action = str(artifacts.summary.top_operator_action_class)
        self.assertIn(top_action, {ACTION_REVIEW_DUPLICATE_ONLY_NOOP, ACTION_NO_ACTION_REQUIRED})

    def test_no_issue_state_creates_no_action_required(self) -> None:
        explanations = _base_explanations()
        explanations.loc[0, "row_change_class"] = "UNCHANGED_ROW"

        artifacts = _build_artifacts(explanations=explanations)
        self.assertIn(ACTION_NO_ACTION_REQUIRED, set(artifacts.priority_queue["action_class"].astype(str)))

    def test_priority_queue_ranks_reconcile(self) -> None:
        artifacts = _build_artifacts()
        ranks = artifacts.priority_queue["action_priority_rank"].astype(int).tolist()
        self.assertEqual(ranks, list(range(1, len(ranks) + 1)))

    def test_blocked_actions_fail_loud_when_marked_safe(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "action_priority_rank": 1,
                    "action_class": "MODEL_OWNER_DATA_QUALITY_REVIEW",
                    "action_owner_class": "MODEL_OWNER",
                    "action_reason": "blocked",
                    "evidence_strength_class": "EVIDENCE_NONE",
                    "requires_human_review_flag": True,
                    "safe_to_execute_as_manual_review_flag": True,
                    "linked_segment_type": "attribution_status",
                    "linked_segment_value": "ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA",
                    "linked_store_number": "101",
                    "linked_promotion_id": "PROMO-1",
                    "linked_run_id": "action-test-run",
                    "supporting_metric_summary": "blocked=true",
                    "operator_attention_class": ATTENTION_IMMEDIATE,
                    "action_priority_score": 999,
                    "blocked_action_flag": True,
                    "attribution_status": "ATTRIBUTION_READY",
                }
            ]
        )
        summary = _build_summary(
            instruction_frame=frame,
            commercial_delta_summary={"materiality_class": "LOW_CHANGE"},
            commercial_policy_calibration_summary={"calibration_readiness_class": "CALIBRATION_READY"},
            commercial_policy_simulation_summary={"simulation_readiness_class": "SIMULATION_READY"},
            current_freshness_class="FRESH_PUBLICATION_OPPORTUNITY_PRESENT",
            current_commercial_failure_flag=False,
        )
        with self.assertRaises(ValueError):
            _validate_instruction_consistency(
                instruction_frame=frame,
                operator_action_summary=pd.DataFrame(
                    [
                        {
                            "action_class": "MODEL_OWNER_DATA_QUALITY_REVIEW",
                            "action_owner_class": "MODEL_OWNER",
                            "action_count": 1,
                            "highest_priority_rank": 1,
                            "immediate_action_count": 1,
                            "high_priority_action_count": 0,
                            "low_evidence_action_count": 1,
                            "safe_manual_review_action_count": 1,
                            "blocked_action_count": 1,
                        }
                    ]
                ),
                model_owner_action_summary=pd.DataFrame(
                    [
                        {
                            "action_class": "MODEL_OWNER_DATA_QUALITY_REVIEW",
                            "action_owner_class": "MODEL_OWNER",
                            "action_count": 1,
                            "highest_priority_rank": 1,
                            "immediate_action_count": 1,
                            "high_priority_action_count": 0,
                            "low_evidence_action_count": 1,
                            "safe_manual_review_action_count": 1,
                            "blocked_action_count": 1,
                        }
                    ]
                ),
                by_segment=_build_segment_summary(frame),
                summary=summary,
            )

    def test_brief_contains_all_new_sections(self) -> None:
        artifacts = _build_artifacts()
        brief = artifacts.brief_markdown
        self.assertIn("## Action Pack Readiness", brief)
        self.assertIn("## Top Operator Actions", brief)
        self.assertIn("## Top Model Owner Actions", brief)
        self.assertIn("## Immediate Priorities", brief)
        self.assertIn("## Segment Watchlist", brief)
        self.assertIn("## Recommended Next Steps", brief)

    def test_segment_summary_reconciles_to_action_queue(self) -> None:
        artifacts = _build_artifacts()
        self.assertEqual(
            int(artifacts.by_segment["action_count"].sum()),
            int(len(artifacts.priority_queue.index)),
        )


if __name__ == "__main__":
    unittest.main()
