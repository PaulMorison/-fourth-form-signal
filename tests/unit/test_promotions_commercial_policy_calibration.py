from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.commercial_policy_calibration import (  # noqa: E402
    CALIBRATION_LOW_COVERAGE,
    CALIBRATION_NOT_READY,
    HOLD_POLICY,
    INVESTIGATE_SEGMENT,
    LOOSEN_PUBLISH_POLICY,
    NO_THRESHOLD_RECOMMENDATION,
    POLICY_SIGNAL_HOLD,
    POLICY_SIGNAL_INCONCLUSIVE,
    POLICY_SIGNAL_STRENGTHEN,
    POLICY_SIGNAL_WEAKEN,
    TIGHTEN_PUBLISH_POLICY,
    _validate_policy_calibration_consistency,
    build_commercial_policy_calibration_artifacts,
)


def _attr_row(
    *,
    store: int,
    sku: int,
    action: str = "ACTION_PUBLISH_NOW",
    eligibility: str = "publishable",
    demand: str = "healthy_nonzero_demand",
    reason_code: str = "reason_a",
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
        "row_change_reason_code": reason_code,
        "attribution_status": status,
        "recommendation_effectiveness_class": eff_class,
        "attribution_confidence_class": confidence,
    }


class CommercialPolicyCalibrationTests(unittest.TestCase):
    def test_strong_effective_evidence_yields_strengthen(self) -> None:
        rows = [
            _attr_row(store=1, sku=100 + i, eff_class="EFFECTIVE_STRONG", confidence="HIGH")
            for i in range(16)
        ]
        artifacts = build_commercial_policy_calibration_artifacts(
            attribution=pd.DataFrame(rows),
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertEqual(artifacts.summary.policy_signal_class, POLICY_SIGNAL_STRENGTHEN)
        self.assertEqual(artifacts.summary.threshold_direction_class, LOOSEN_PUBLISH_POLICY)

    def test_strong_harmful_evidence_yields_weaken(self) -> None:
        rows = [
            _attr_row(store=2, sku=200 + i, eff_class="HARMFUL", confidence="HIGH")
            for i in range(14)
        ]
        artifacts = build_commercial_policy_calibration_artifacts(
            attribution=pd.DataFrame(rows),
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertEqual(artifacts.summary.policy_signal_class, POLICY_SIGNAL_WEAKEN)
        self.assertEqual(artifacts.summary.threshold_direction_class, TIGHTEN_PUBLISH_POLICY)

    def test_mixed_evidence_yields_hold_or_investigate(self) -> None:
        rows = []
        for i in range(7):
            rows.append(_attr_row(store=3, sku=300 + i, eff_class="EFFECTIVE_MODERATE", confidence="HIGH"))
        for i in range(5):
            rows.append(_attr_row(store=3, sku=400 + i, eff_class="INEFFECTIVE", confidence="HIGH"))
        for i in range(2):
            rows.append(_attr_row(store=3, sku=500 + i, eff_class="NEUTRAL", confidence="HIGH"))

        artifacts = build_commercial_policy_calibration_artifacts(
            attribution=pd.DataFrame(rows),
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertIn(artifacts.summary.policy_signal_class, {POLICY_SIGNAL_HOLD, POLICY_SIGNAL_INCONCLUSIVE})
        self.assertIn(
            artifacts.summary.threshold_direction_class,
            {HOLD_POLICY, INVESTIGATE_SEGMENT, NO_THRESHOLD_RECOMMENDATION},
        )

    def test_sparse_evidence_yields_not_ready_or_low_coverage(self) -> None:
        rows = [
            _attr_row(store=4, sku=501, eff_class="EFFECTIVE_STRONG"),
            _attr_row(store=4, sku=502, eff_class="HARMFUL"),
        ]
        artifacts = build_commercial_policy_calibration_artifacts(
            attribution=pd.DataFrame(rows),
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertIn(
            artifacts.summary.calibration_readiness_class,
            {CALIBRATION_NOT_READY, CALIBRATION_LOW_COVERAGE},
        )

    def test_high_harm_segment_appears_in_watchlist(self) -> None:
        rows = [
            _attr_row(
                store=5,
                sku=600 + i,
                action="ACTION_PUBLISH_NOW",
                reason_code="harm_segment",
                eff_class="HARMFUL",
                confidence="HIGH",
            )
            for i in range(8)
        ]
        artifacts = build_commercial_policy_calibration_artifacts(
            attribution=pd.DataFrame(rows),
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        self.assertFalse(artifacts.watchlist.empty)
        self.assertTrue((artifacts.watchlist["watch_reason"] == "HIGH_HARM_SEGMENT").any())

    def test_segment_summaries_reconcile_exactly(self) -> None:
        rows = [
            _attr_row(store=6, sku=701, action="ACTION_PUBLISH_NOW", eff_class="EFFECTIVE_STRONG"),
            _attr_row(store=6, sku=702, action="ACTION_REVIEW_NOW", eff_class="INCONCLUSIVE", status="ATTRIBUTION_EXCLUDED_REVIEW_ONLY", confidence="NONE"),
            _attr_row(store=6, sku=703, action="ACTION_PUBLISH_NOW", eff_class="HARMFUL"),
        ]
        attribution = pd.DataFrame(rows)
        artifacts = build_commercial_policy_calibration_artifacts(
            attribution=attribution,
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )

        operator_action_segments = artifacts.by_segment[
            artifacts.by_segment["segment_type"] == "operator_action_class"
        ]
        self.assertEqual(int(operator_action_segments["effective_count"].sum()), 1)
        self.assertEqual(int(operator_action_segments["harmful_count"].sum()), 1)
        self.assertEqual(int(operator_action_segments["inconclusive_count"].sum()), 1)

    def test_calibration_brief_includes_required_sections(self) -> None:
        rows = [
            _attr_row(store=7, sku=801 + i, eff_class="EFFECTIVE_STRONG", confidence="HIGH")
            for i in range(12)
        ]
        artifacts = build_commercial_policy_calibration_artifacts(
            attribution=pd.DataFrame(rows),
            current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
        )
        brief = artifacts.calibration_brief_markdown
        self.assertIn("## Calibration Readiness", brief)
        self.assertIn("## What to tighten", brief)
        self.assertIn("## What to loosen", brief)
        self.assertIn("## What to leave unchanged", brief)
        self.assertIn("## Watchlist", brief)
        self.assertIn("## Recommended next actions", brief)

    def test_contradictory_calibration_state_fails_loud(self) -> None:
        attribution = pd.DataFrame(
            [
                _attr_row(store=8, sku=901, eff_class="EFFECTIVE_STRONG", confidence="HIGH"),
            ]
        )
        summary = type(
            "S",
            (),
            {
                "calibration_readiness_class": "CALIBRATION_READY",
                "evidence_row_count": 0,
                "threshold_direction_class": TIGHTEN_PUBLISH_POLICY,
                "effective_count": 0,
                "harmful_count": 0,
                "neutral_count": 0,
                "inconclusive_count": 0,
                "policy_signal_class": "POLICY_SIGNAL_BLOCKED_DEFECT",
            },
        )()

        with self.assertRaises(ValueError):
            _validate_policy_calibration_consistency(
                attribution=attribution,
                summary=summary,
                by_segment=pd.DataFrame(
                    [
                        {
                            "segment_type": "operator_action_class",
                            "segment_value": "ACTION_PUBLISH_NOW",
                        }
                    ]
                ),
                watchlist=pd.DataFrame(
                    [
                        {
                            "segment_type": "operator_action_class",
                            "segment_value": "UNKNOWN_SEGMENT",
                        }
                    ]
                ),
            )


if __name__ == "__main__":
    unittest.main()
