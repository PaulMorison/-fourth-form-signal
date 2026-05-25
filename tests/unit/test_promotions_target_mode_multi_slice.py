from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import (  # noqa: E402
    PromotionTargetModeShadowEvaluator,
    _build_target_mode_multi_slice_artifacts,
    _build_target_mode_shadow_stability_gate_payload,
    _resolve_target_mode_shadow_evaluator_inputs,
    _resolve_target_mode_shadow_slice_inputs,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.run_promotions_target_mode_multi_slice import (  # noqa: E402
    run_target_mode_multi_slice,
)
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


def _slice_row(
    identifier: str,
    *,
    improvement: float = 2.0,
    improvement_rate: float = 0.08,
    comparable_rows: int = 250,
    top_driver: str = "stock_basis_proxy_mismatch",
    exclusion_rate: float = 0.0,
    shadow_ready: bool = True,
) -> dict[str, object]:
    return {
        "slice_index": 1,
        "slice_identifier": identifier,
        "source_type": "training_ready_parquet",
        "source_path": f"{identifier}.parquet",
        "source_manifest_path": None,
        "dataset_path": f"{identifier}.parquet",
        "child_run_id": f"run-{identifier}",
        "target_mode": "dual_contract_diagnostics",
        "training_manifest_target_mode": "dual_contract_diagnostics",
        "comparison_cohort_size": comparable_rows,
        "comparable_rows": comparable_rows,
        "evaluation_row_count": comparable_rows,
        "coverage_rate": 1.0 - exclusion_rate,
        "historical_exclusion_rate": exclusion_rate,
        "current_vs_historical_disagreement_rate": 0.95,
        "current_vs_historical_capital_gap_total": 1000.0,
        "current_shadow_excess_capital_mae_on_historical_target": 10.0,
        "historical_shadow_excess_capital_mae_on_historical_target": 10.0 - improvement,
        "candidate_capital_mae_improvement": improvement,
        "candidate_capital_mae_improvement_rate": improvement_rate,
        "candidate_shadow_model_outperformed_current_shadow_model": improvement > 0.0,
        "current_shadow_flag_precision_on_historical_target": 0.1,
        "current_shadow_flag_recall_on_historical_target": 0.1,
        "historical_shadow_flag_precision_on_historical_target": 0.95,
        "historical_shadow_flag_recall_on_historical_target": 0.96,
        "dominant_divergence_driver": top_driver,
        "slice_gate_decision": "candidate_for_shadow_training" if shadow_ready else "diagnostics_only",
        "slice_should_promote_to_shadow": shadow_ready,
        "slice_should_promote_to_primary": False,
        "slice_should_remain_diagnostics_only": not shadow_ready,
        "current_trainer_contract_remains_live_default": True,
        "policy_remains_paused": True,
        "policy_is_dominant_bottleneck": False,
        "target_contract_misalignment_is_dominant_bottleneck": top_driver == "stock_basis_proxy_mismatch",
        "evidence_outcome": "shadow-only" if shadow_ready else "evidence-only",
        "target_mode_summary_json_path": f"{identifier}/target_mode_comparison_summary.json",
        "target_contract_summary_json_path": f"{identifier}/target_contract_comparison_summary.json",
        "target_contract_promotion_gate_json_path": f"{identifier}/target_contract_promotion_gate.json",
    }


def _bucket_row(identifier: str) -> dict[str, object]:
    return {
        "bucket_name": "stock_basis_proxy_mismatch",
        "slice_identifier": identifier,
        "row_count": 250,
        "comparable_row_count": 250,
        "current_label_vs_historical_excess_capital_error_total": 1000.0,
        "current_shadow_vs_historical_excess_capital_mae": 10.0,
        "historical_candidate_shadow_vs_historical_excess_capital_mae": 8.0,
        "candidate_shadow_capital_mae_improvement": 2.0,
    }


def _build_training_ready_dataset(
    artifact_paths: PromotionArtifactPaths,
    *,
    run_id: str,
):
    completed_base_frame = build_completed_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(completed_base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    return PromotionDatasetAssembler().assemble_training_dataset(
        run_id=run_id,
        base_frame=completed_base_frame,
        target_frame=target_result.frame,
        feature_frame=feature_result.frame,
        target_columns=target_result.target_columns,
        feature_columns=feature_result.feature_columns,
        artifact_paths=artifact_paths,
    )


class PromotionTargetModeMultiSliceTests(unittest.TestCase):
    def test_multi_slice_aggregation_promotes_primary_candidate_only_when_stable(self) -> None:
        slice_rows = [
            _slice_row("slice-a", improvement=2.0, improvement_rate=0.08),
            _slice_row("slice-b", improvement=2.2, improvement_rate=0.09),
            _slice_row("slice-c", improvement=1.9, improvement_rate=0.075),
        ]

        artifacts = _build_target_mode_multi_slice_artifacts(
            run_id="stable-shadow",
            target_mode="dual_contract_diagnostics",
            slice_rows=slice_rows,
            bucket_records=[_bucket_row("slice-a"), _bucket_row("slice-b"), _bucket_row("slice-c")],
            residual_records=[{"slice_identifier": "slice-a", "trainer_vs_historical_excess_capital_gap_abs": 100.0}],
            slice_run_artifact_paths=[],
        )
        gate = artifacts["stability_gate_payload"]

        self.assertEqual(gate["decision"], "candidate_for_primary_training")
        self.assertTrue(gate["should_promote_to_candidate_for_primary_training"])
        self.assertTrue(gate["should_current_trainer_contract_remain_default_primary"])
        self.assertTrue(gate["stock_basis_proxy_mismatch_persistent"])
        self.assertFalse(artifacts["bucket_ranking_frame"].empty)

    def test_noisy_single_slice_win_stays_shadow_only_not_primary(self) -> None:
        gate = _build_target_mode_shadow_stability_gate_payload(
            pd.DataFrame([_slice_row("single-winner", improvement=4.0, improvement_rate=0.20)])
        )

        self.assertEqual(gate["decision"], "candidate_for_shadow_training")
        self.assertFalse(gate["should_promote_to_candidate_for_primary_training"])
        self.assertTrue(gate["should_candidate_remain_shadow_only"])
        self.assertIn("insufficient_slice_count", gate["primary_promotion_blockers"])

    def test_missing_slice_evidence_fails_loud(self) -> None:
        rows = pd.DataFrame([_slice_row("missing")])
        rows.loc[0, "candidate_capital_mae_improvement"] = pd.NA

        with self.assertRaisesRegex(ValueError, "missing required numeric slice evidence"):
            _build_target_mode_shadow_stability_gate_payload(rows)

        with self.assertRaises(FileNotFoundError):
            _resolve_target_mode_shadow_slice_inputs(["/definitely/not/a/slice.parquet"])

    def test_training_ready_parquet_input_uses_dataset_run_as_slice_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir) / "completed-slice-20260523T000000Z"
            dataset_dir.mkdir(parents=True)
            dataset_path = dataset_dir / "training_ready.parquet"
            pd.DataFrame({"sku": ["A"]}).to_parquet(dataset_path, index=False)

            resolved = _resolve_target_mode_shadow_slice_inputs([dataset_path])

        self.assertEqual(resolved[0]["slice_identifier"], "completed-slice-20260523T000000Z")
        self.assertEqual(resolved[0]["source_type"], "training_ready_parquet")

    def test_manifest_input_evaluation_records_gate_and_slice_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts", local_inspection_root=None)
            dataset = _build_training_ready_dataset(
                artifact_paths,
                run_id="multi-slice-dataset",
            )
            slice_manifest_path = Path(temp_dir) / "slice_manifest.json"
            slice_manifest_path.write_text(
                json.dumps(
                    {
                        "slice_identifier": "manifest-slice",
                        "training_ready_dataset_path": dataset.dataset_path,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifacts = PromotionTargetModeShadowEvaluator().evaluate(
                run_id="multi-slice-shadow",
                slice_inputs=[slice_manifest_path],
                artifact_paths=artifact_paths,
            )
            manifest_payload = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            summary_payload = json.loads(Path(artifacts.summary_json_path).read_text(encoding="utf-8"))

        self.assertEqual(manifest_payload["target_mode"], "dual_contract_diagnostics")
        self.assertEqual(manifest_payload["slice_count"], 1)
        self.assertEqual(manifest_payload["slice_runs"][0]["slice_identifier"], "manifest-slice")
        self.assertIn("gate_inputs", manifest_payload)
        self.assertIn("gate_outcome", manifest_payload)
        self.assertEqual(summary_payload["slice_rows"][0]["evidence_outcome"], "shadow-only")
        self.assertTrue(artifacts.stability_gate["should_current_trainer_contract_remain_default_primary"])

    def test_multi_slice_manifest_source_resolves_child_run_manifests_and_runtime_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts", local_inspection_root=None)
            dataset = _build_training_ready_dataset(
                artifact_paths,
                run_id="multi-slice-runtime-dataset",
            )
            slice_manifest_path = Path(temp_dir) / "slice_manifest.json"
            slice_manifest_path.write_text(
                json.dumps(
                    {
                        "slice_identifier": "runtime-manifest-slice",
                        "training_ready_dataset_path": dataset.dataset_path,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            source_artifacts = PromotionTargetModeShadowEvaluator().evaluate(
                run_id="source-multi-slice-shadow",
                slice_inputs=[slice_manifest_path],
                artifact_paths=artifact_paths,
            )

            resolved_inputs = _resolve_target_mode_shadow_evaluator_inputs(
                multi_slice_manifest_path=source_artifacts.manifest_path,
                slice_inputs=(),
            )
            runtime_artifacts = run_target_mode_multi_slice(
                artifact_root=str(artifact_paths.root),
                run_id="runtime-multi-slice-shadow",
                multi_slice_manifest_path=source_artifacts.manifest_path,
            )
            runtime_manifest_payload = json.loads(
                Path(runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )

            self.assertTrue(Path(runtime_artifacts.summary_json_path).exists())

        self.assertEqual(resolved_inputs["requested_evaluator_mode"], "multi_slice_manifest_path")
        self.assertEqual(resolved_inputs["resolved_slice_inputs"][0]["source_type"], "governed_slice_manifest")
        self.assertEqual(runtime_manifest_payload["requested_evaluator_mode"], "multi_slice_manifest_path")
        self.assertEqual(runtime_manifest_payload["resolved_evaluator_mode"], "multi_slice_manifest_path")
        self.assertEqual(runtime_manifest_payload["resolved_target_mode"], "dual_contract_diagnostics")
        self.assertEqual(
            runtime_manifest_payload["output_artifact_paths"]["target_mode_multi_slice_manifest_path"],
            runtime_artifacts.evaluator_manifest_path,
        )
        self.assertTrue(runtime_artifacts.gate["should_current_trainer_contract_remain_default_primary"])

    def test_multi_slice_manifest_source_fails_loud_when_child_row_diagnostics_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts", local_inspection_root=None)
            dataset = _build_training_ready_dataset(
                artifact_paths,
                run_id="multi-slice-missing-artifact-dataset",
            )
            slice_manifest_path = Path(temp_dir) / "slice_manifest.json"
            slice_manifest_path.write_text(
                json.dumps(
                    {
                        "slice_identifier": "missing-row-diagnostics-slice",
                        "training_ready_dataset_path": dataset.dataset_path,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            source_artifacts = PromotionTargetModeShadowEvaluator().evaluate(
                run_id="source-multi-slice-missing-row-diagnostics",
                slice_inputs=[slice_manifest_path],
                artifact_paths=artifact_paths,
            )
            source_manifest_payload = json.loads(
                Path(source_artifacts.manifest_path).read_text(encoding="utf-8")
            )
            child_manifest_path = Path(source_manifest_payload["slice_runs"][0]["manifest_path"])
            child_manifest_payload = json.loads(child_manifest_path.read_text(encoding="utf-8"))
            row_diagnostics_path = Path(
                child_manifest_payload["artifact_files"]["target_contract_row_diagnostics_parquet"]
            )
            row_diagnostics_path.unlink()

            with self.assertRaisesRegex(FileNotFoundError, "target_contract_row_diagnostics_parquet"):
                _resolve_target_mode_shadow_evaluator_inputs(
                    multi_slice_manifest_path=source_artifacts.manifest_path,
                    slice_inputs=(),
                )


if __name__ == "__main__":
    unittest.main()