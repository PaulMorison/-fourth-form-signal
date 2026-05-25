from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import (  # noqa: E402
    _TARGET_CONTRACT_THREE_WAY_HISTORICAL_CANDIDATE,
    _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
)
from runtime.promotions.run_promotions_target_contract_three_way_comparison import (  # noqa: E402
    run_target_contract_three_way_comparison,
)
from runtime.promotions.run_promotions_target_promotion_readiness import (  # noqa: E402
    run_target_promotion_readiness,
)
from tests.unit.test_promotions_target_contract_three_way_comparison import (  # noqa: E402
    _build_three_way_runtime_source_artifacts,
)


def _build_readiness_runtime_source_artifacts(
    temp_path: Path,
    *,
    slice_identifier: str,
):
    artifact_paths, repeated_evidence_runtime_artifacts, repeated_evidence_root, proposal_root = (
        _build_three_way_runtime_source_artifacts(
            temp_path,
            slice_identifier=slice_identifier,
        )
    )
    three_way_runtime_artifacts = run_target_contract_three_way_comparison(
        artifact_root=str(artifact_paths.root),
        run_id=f"{slice_identifier}-three-way-runtime",
        repeated_evidence_runtime_manifest_path=repeated_evidence_runtime_artifacts.runtime_manifest_path,
    )
    three_way_root = Path(three_way_runtime_artifacts.evaluator_manifest_path).parent
    return (
        artifact_paths,
        repeated_evidence_runtime_artifacts,
        repeated_evidence_root,
        proposal_root,
        three_way_runtime_artifacts,
        three_way_root,
    )


class PromotionTargetPromotionReadinessTests(unittest.TestCase):
    def test_three_way_runtime_manifest_replay_uses_existing_three_way_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (
                artifact_paths,
                _,
                _,
                _,
                three_way_runtime_artifacts,
                _,
            ) = _build_readiness_runtime_source_artifacts(
                temp_path,
                slice_identifier="promotion-readiness-three-way-runtime",
            )

            runtime_artifacts = run_target_promotion_readiness(
                artifact_root=str(artifact_paths.root),
                run_id="promotion-readiness-runtime",
                three_way_runtime_manifest_path=three_way_runtime_artifacts.runtime_manifest_path,
            )
            runtime_manifest_payload = json.loads(
                Path(runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )

            self.assertTrue(Path(runtime_artifacts.decision_packet_json_path).exists())

        self.assertEqual(runtime_artifacts.decision_packet["current_decision"], "diagnostics_only")
        self.assertEqual(runtime_manifest_payload["requested_source_mode"], "three_way_runtime_manifest_path")
        self.assertEqual(runtime_manifest_payload["resolved_source_mode"], "three_way_runtime_manifest_path")
        self.assertTrue(runtime_manifest_payload["used_existing_three_way_evidence"])
        self.assertEqual(
            runtime_artifacts.decision_packet["current_best_candidate"]["candidate_name"],
            _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
        )
        self.assertTrue(runtime_manifest_payload["live_default_unchanged_confirmation"])
        self.assertTrue(runtime_manifest_payload["policy_paused_confirmation"])
        self.assertFalse(runtime_manifest_payload["publish_tree_created"])
        self.assertFalse(runtime_manifest_payload["store_facing_csv_changed"])

    def test_repeated_evidence_runtime_manifest_builds_in_memory_three_way_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, repeated_evidence_runtime_artifacts, _, _ = _build_three_way_runtime_source_artifacts(
                temp_path,
                slice_identifier="promotion-readiness-repeated-evidence-runtime",
            )

            runtime_artifacts = run_target_promotion_readiness(
                artifact_root=str(artifact_paths.root),
                run_id="promotion-readiness-runtime-from-repeated-evidence",
                repeated_evidence_runtime_manifest_path=repeated_evidence_runtime_artifacts.runtime_manifest_path,
            )

        self.assertFalse(runtime_artifacts.used_existing_three_way_evidence)
        self.assertEqual(
            runtime_artifacts.decision_packet["current_best_candidate"]["candidate_name"],
            _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
        )
        self.assertEqual(runtime_artifacts.decision_packet["dominant_blocker_family"], "candidate_quality")
        self.assertEqual(runtime_artifacts.decision_packet["dominant_blocker"], "candidate_did_not_improve_on_enough_slices")
        self.assertEqual(
            runtime_artifacts.decision_packet["minimum_next_evidence_required"]["required_value"],
            0.8,
        )
        self.assertEqual(
            runtime_artifacts.decision_packet["minimum_next_evidence_required"]["observed_value"],
            0.0,
        )
        self.assertEqual(
            runtime_artifacts.decision_packet["minimum_next_evidence_required"]["delta_to_threshold"],
            0.8,
        )
        self.assertFalse(runtime_artifacts.decision_packet["historical_candidate_shadow_ready"])
        self.assertFalse(runtime_artifacts.decision_packet["design_candidate_shadow_ready"])

    def test_explicit_three_way_root_replay_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, _, _, _, _, three_way_root = _build_readiness_runtime_source_artifacts(
                temp_path,
                slice_identifier="promotion-readiness-explicit-three-way-root",
            )

            runtime_artifacts = run_target_promotion_readiness(
                artifact_root=str(artifact_paths.root),
                run_id="promotion-readiness-runtime-explicit-root",
                source_inputs=[three_way_root],
                target_mode="dual_contract_diagnostics",
            )
            runtime_manifest_payload = json.loads(
                Path(runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )

            self.assertTrue(Path(runtime_artifacts.scoreboard_json_path).exists())

        self.assertEqual(runtime_manifest_payload["requested_source_mode"], "explicit_source_inputs")
        self.assertEqual(runtime_manifest_payload["resolved_source_mode"], "explicit_three_way_root")
        self.assertEqual(runtime_manifest_payload["source_inputs"], [str(three_way_root.resolve())])
        self.assertTrue(runtime_manifest_payload["used_existing_three_way_evidence"])

    def test_explicit_sources_fail_loud_when_inconsistent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            left_path = temp_path / "left"
            right_path = temp_path / "right"
            left_path.mkdir()
            right_path.mkdir()
            (
                artifact_paths,
                _,
                _,
                _,
                _,
                left_three_way_root,
            ) = _build_readiness_runtime_source_artifacts(
                left_path,
                slice_identifier="promotion-readiness-explicit-left",
            )
            _, _, right_repeated_evidence_root, _ = _build_three_way_runtime_source_artifacts(
                right_path,
                slice_identifier="promotion-readiness-explicit-right",
            )

            with self.assertRaisesRegex(ValueError, "source_repeated_evidence_manifest_path"):
                run_target_promotion_readiness(
                    artifact_root=str(artifact_paths.root),
                    run_id="promotion-readiness-runtime-inconsistent-explicit-sources",
                    source_inputs=[left_three_way_root, right_repeated_evidence_root],
                    target_mode="dual_contract_diagnostics",
                )

    def test_scoreboard_rows_keep_historical_and_design_blockers_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, repeated_evidence_runtime_artifacts, _, _ = _build_three_way_runtime_source_artifacts(
                temp_path,
                slice_identifier="promotion-readiness-scoreboard-rows",
            )

            runtime_artifacts = run_target_promotion_readiness(
                artifact_root=str(artifact_paths.root),
                run_id="promotion-readiness-runtime-scoreboard-rows",
                repeated_evidence_runtime_manifest_path=repeated_evidence_runtime_artifacts.runtime_manifest_path,
            )
            scoreboard_payload = json.loads(Path(runtime_artifacts.scoreboard_json_path).read_text(encoding="utf-8"))

        scoreboard_rows = {
            row["candidate_name"]: row
            for row in scoreboard_payload["candidate_rows"]
        }
        historical_row = scoreboard_rows[_TARGET_CONTRACT_THREE_WAY_HISTORICAL_CANDIDATE]
        design_row = scoreboard_rows[_TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE]

        self.assertFalse(historical_row["shadow_ready"])
        self.assertFalse(design_row["shadow_ready"])
        self.assertEqual(historical_row["dominant_blocker"], "candidate_did_not_improve_on_enough_slices")
        self.assertEqual(design_row["dominant_blocker"], "candidate_did_not_improve_on_enough_slices")
        self.assertIn("Need candidate improvement on at least 0.8000 of slices", historical_row["minimum_next_evidence_summary"])
        self.assertIn("Need candidate improvement on at least 0.8000 of slices", design_row["minimum_next_evidence_summary"])


if __name__ == "__main__":
    unittest.main()