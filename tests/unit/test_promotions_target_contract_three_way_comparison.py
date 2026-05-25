from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import (  # noqa: E402
    _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE,
    _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
    _build_target_contract_three_way_artifacts,
)
from runtime.promotions.run_promotions_target_contract_three_way_comparison import (  # noqa: E402
    run_target_contract_three_way_comparison,
)
from runtime.promotions.run_promotions_target_design_repeated_evidence import (  # noqa: E402
    run_target_design_repeated_evidence,
)
from tests.unit.test_promotions_target_contract_design import _three_slice_rows  # noqa: E402
from tests.unit.test_promotions_target_design_repeated_evidence import (  # noqa: E402
    _build_repeated_evidence_runtime_source_artifacts,
)


def _repeated_evidence_gate_payload(*, decision: str = "diagnostics_only") -> dict[str, object]:
    return {
        "decision": decision,
        "shadow_promotion_blockers": ["insufficient_completed_slice_count"] if decision == "diagnostics_only" else [],
        "promotion_criteria": {
            "minimum_slice_count": 5,
            "minimum_comparable_rows_per_slice": 100,
        },
        "current_trainer_contract_remains_live_default": True,
        "policy_remains_paused": True,
        "production_training_target_was_replaced": False,
        "stage_11_was_changed": False,
        "store_facing_csv_was_changed": False,
    }


def _build_three_way_runtime_source_artifacts(
    temp_path: Path,
    *,
    slice_identifier: str,
):
    artifact_paths, design_runtime_manifest_path, _ = _build_repeated_evidence_runtime_source_artifacts(
        temp_path,
        slice_identifier=slice_identifier,
    )
    repeated_evidence_runtime_artifacts = run_target_design_repeated_evidence(
        artifact_root=str(artifact_paths.root),
        run_id=f"{slice_identifier}-repeated-evidence-runtime",
        design_runtime_manifest_path=design_runtime_manifest_path,
    )
    repeated_evidence_root = Path(repeated_evidence_runtime_artifacts.evaluator_manifest_path).parent
    proposal_root = Path(repeated_evidence_runtime_artifacts.target_contract_design_proposal_path).parent
    return artifact_paths, repeated_evidence_runtime_artifacts, repeated_evidence_root, proposal_root


class PromotionTargetContractThreeWayComparisonTests(unittest.TestCase):
    def test_three_way_artifacts_rank_top_design_candidate_ahead_of_tied_historical_candidate(self) -> None:
        artifacts = _build_target_contract_three_way_artifacts(
            run_id="three-way-ranking",
            source_repeated_evidence_manifest_path="target_design_repeated_evidence_manifest.json",
            source_repeated_evidence_manifest_payload={
                "run_id": "repeated-evidence-source",
                "target_mode_multi_slice_manifest_path": "target_mode_multi_slice_manifest.json",
                "target_contract_design_proposal_path": "target_contract_design_proposal.json",
                "gate_outcome": _repeated_evidence_gate_payload(decision="diagnostics_only"),
            },
            source_design_proposal_path="target_contract_design_proposal.json",
            source_design_proposal_payload={
                "best_target_design_candidate": {"candidate_name": _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE},
                "decision": "diagnostics_only",
            },
            source_rows=_three_slice_rows(),
        )
        summary_frame = artifacts["summary_frame"]
        proposal_payload = artifacts["proposal_payload"]

        self.assertEqual(
            summary_frame["candidate_name"].tolist(),
            [
                _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
                "historical_excess_units",
                _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE,
            ],
        )
        design_row = summary_frame.loc[
            summary_frame["candidate_name"].eq(_TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE)
        ].iloc[0]
        self.assertTrue(bool(design_row["has_metric_tie"]))
        self.assertIn("historical_excess_units", str(design_row["tied_contract_names"]))
        self.assertEqual(
            proposal_payload["top_design_candidate_assessment"],
            "better_than_current_but_not_promotable",
        )
        self.assertEqual(proposal_payload["decision"], "diagnostics_only")

    def test_runtime_manifest_source_defaults_to_diagnostics_only_and_persists_runtime_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, repeated_evidence_runtime_artifacts, _, _ = _build_three_way_runtime_source_artifacts(
                temp_path,
                slice_identifier="three-way-runtime-default",
            )

            runtime_artifacts = run_target_contract_three_way_comparison(
                artifact_root=str(artifact_paths.root),
                run_id="target-contract-three-way-runtime",
                repeated_evidence_runtime_manifest_path=repeated_evidence_runtime_artifacts.runtime_manifest_path,
            )
            runtime_manifest_payload = json.loads(
                Path(runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )

            self.assertTrue(Path(runtime_artifacts.proposal_json_path).exists())

        self.assertEqual(runtime_artifacts.proposal["decision"], "diagnostics_only")
        self.assertEqual(runtime_artifacts.proposal["top_design_candidate_assessment"], "better_than_current_but_not_promotable")
        self.assertEqual(runtime_manifest_payload["requested_source_mode"], "repeated_evidence_runtime_manifest_path")
        self.assertEqual(runtime_manifest_payload["resolved_source_mode"], "repeated_evidence_runtime_manifest_path")
        self.assertIsNone(runtime_manifest_payload["requested_target_mode_context"])
        self.assertEqual(runtime_manifest_payload["resolved_target_mode_context"], "dual_contract_diagnostics")
        self.assertEqual(
            [contract["candidate_name"] for contract in runtime_manifest_payload["compared_contracts"]],
            [
                _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE,
                "historical_excess_units",
                _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
            ],
        )
        self.assertTrue(runtime_manifest_payload["diagnostics_only_confirmation"]["runtime_path_has_no_primary_promotion_authority"])
        self.assertTrue(runtime_manifest_payload["live_default_unchanged_confirmation"])
        self.assertTrue(runtime_manifest_payload["policy_paused_confirmation"])
        self.assertEqual(
            runtime_manifest_payload["output_artifact_paths"]["target_contract_three_way_proposal_json_path"],
            runtime_artifacts.proposal_json_path,
        )

    def test_runtime_explicit_repeated_evidence_root_replay_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, _, repeated_evidence_root, _ = _build_three_way_runtime_source_artifacts(
                temp_path,
                slice_identifier="three-way-runtime-explicit-root",
            )

            runtime_artifacts = run_target_contract_three_way_comparison(
                artifact_root=str(artifact_paths.root),
                run_id="target-contract-three-way-runtime-explicit-root",
                source_inputs=[repeated_evidence_root],
                target_mode="dual_contract_diagnostics",
            )
            runtime_manifest_payload = json.loads(
                Path(runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )

            self.assertTrue(Path(runtime_artifacts.summary_json_path).exists())

        self.assertEqual(runtime_manifest_payload["requested_source_mode"], "explicit_source_inputs")
        self.assertEqual(runtime_manifest_payload["resolved_source_mode"], "explicit_repeated_evidence_root")
        self.assertEqual(runtime_manifest_payload["source_inputs"], [str(repeated_evidence_root.resolve())])

    def test_runtime_manifest_source_fails_loud_when_upstream_design_artifact_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, repeated_evidence_runtime_artifacts, _, _ = _build_three_way_runtime_source_artifacts(
                temp_path,
                slice_identifier="three-way-runtime-missing-upstream",
            )
            repeated_evidence_runtime_manifest_payload = json.loads(
                Path(repeated_evidence_runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )
            proposal_path = Path(
                repeated_evidence_runtime_manifest_payload["output_artifact_paths"]["target_contract_design_proposal_path"]
            )
            proposal_path.unlink()

            with self.assertRaisesRegex(FileNotFoundError, "target_contract_design_proposal"):
                run_target_contract_three_way_comparison(
                    artifact_root=str(artifact_paths.root),
                    run_id="target-contract-three-way-runtime-missing-upstream",
                    repeated_evidence_runtime_manifest_path=repeated_evidence_runtime_artifacts.runtime_manifest_path,
                )


if __name__ == "__main__":
    unittest.main()