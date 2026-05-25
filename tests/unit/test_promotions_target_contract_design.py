from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.preprocessing import prepare_model_input_frame  # noqa: E402
from models.promotions.trainer import (  # noqa: E402
    PromotionTargetContractDesignEvaluator,
    PromotionTargetModeShadowEvaluator,
    _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS,
    _build_target_contract_design_artifacts,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.run_promotions_target_contract_design import (  # noqa: E402
    run_target_contract_design,
)
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


def _source_manifest_payload(*, decision: str = "candidate_for_shadow_training") -> dict[str, object]:
    return {
        "run_id": "multi-slice-source",
        "gate_outcome": {
            "decision": decision,
            "gate_inputs": {
                "top_persistent_divergence_driver": _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS,
                "slice_count": 3,
            },
        },
        "slice_runs": [],
    }


def _design_rows(slice_identifier: str, *, row_count: int = 120, invalid_rows: int = 0) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        is_valid = index >= invalid_rows
        allocated_units = float(10 + (index % 4))
        realised_units = float(7 + (index % 3))
        replay_unit_cost = float(2 + (index % 5))
        historical_excess_units = max(allocated_units - realised_units, 0.0)
        historical_excess_capital = historical_excess_units * replay_unit_cost
        rows.append(
            {
                "slice_identifier": slice_identifier,
                "child_run_id": f"child-{slice_identifier}",
                "source_row_diagnostics_path": f"{slice_identifier}/target_contract_row_diagnostics.parquet",
                "promotion_row_key": f"{slice_identifier}-{index}",
                "store_number": "772",
                "sku_number": str(90000 + index),
                "split_name": "test" if index % 2 else "validation",
                "target_contract_replay_comparable_flag": 1.0 if is_valid else 0.0,
                "both_contract_valid_flag": 1.0 if is_valid else 0.0,
                "replay_exclusion_reason": "eligible" if is_valid else "missing_historical_allocation_units",
                "dominant_divergence_driver": _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS,
                "stock_basis_units": realised_units,
                "historical_allocated_units": allocated_units if is_valid else pd.NA,
                "target_historical_allocation_units": allocated_units if is_valid else pd.NA,
                "actual_units_sold": realised_units,
                "realised_units_sold_promo": realised_units,
                "unit_cost": replay_unit_cost,
                "replay_unit_cost": replay_unit_cost,
                "trainer_current_excess_units": 0.0,
                "trainer_current_excess_capital": 0.0,
                "historical_allocation_excess_units": historical_excess_units if is_valid else pd.NA,
                "historical_allocation_excess_capital": historical_excess_capital if is_valid else pd.NA,
                "current_overallocation_flag": 0.0,
                "historical_overallocation_flag": 1.0 if is_valid and historical_excess_units > 0.0 else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _three_slice_rows(*, invalid_rows: int = 0) -> pd.DataFrame:
    return pd.concat(
        [
            _design_rows("slice-a", invalid_rows=invalid_rows),
            _design_rows("slice-b", invalid_rows=invalid_rows),
            _design_rows("slice-c", invalid_rows=invalid_rows),
        ],
        axis=0,
        ignore_index=True,
    )


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


def _build_design_runtime_source_artifacts(
    temp_path: Path,
    *,
    slice_identifier: str,
) -> tuple[PromotionArtifactPaths, object, Path]:
    artifact_paths = PromotionArtifactPaths(root=temp_path / "promotions_artifacts", local_inspection_root=None)
    dataset = _build_training_ready_dataset(
        artifact_paths,
        run_id=f"{slice_identifier}-dataset",
    )
    slice_manifest_path = temp_path / f"{slice_identifier}.json"
    slice_manifest_path.write_text(
        json.dumps(
            {
                "slice_identifier": slice_identifier,
                "training_ready_dataset_path": dataset.dataset_path,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    source_artifacts = PromotionTargetModeShadowEvaluator().evaluate(
        run_id=f"{slice_identifier}-source-shadow",
        slice_inputs=[slice_manifest_path],
        artifact_paths=artifact_paths,
    )
    source_manifest_payload = json.loads(Path(source_artifacts.manifest_path).read_text(encoding="utf-8"))
    child_manifest_path = Path(source_manifest_payload["slice_runs"][0]["manifest_path"])
    return artifact_paths, source_artifacts, child_manifest_path


class PromotionTargetContractDesignTests(unittest.TestCase):
    def test_dominant_stock_basis_driver_is_decomposed_into_design_candidates(self) -> None:
        artifacts = _build_target_contract_design_artifacts(
            run_id="design-summary",
            source_manifest_path="multi-slice-manifest.json",
            source_manifest_payload=_source_manifest_payload(),
            source_rows=_three_slice_rows(),
        )
        summary_frame = artifacts["summary_frame"]

        self.assertEqual(artifacts["proposal_payload"]["dominant_divergence_driver"], _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS)
        self.assertIn("historical_allocated_units", set(summary_frame["candidate_name"]))
        self.assertIn("realised_promo_units", set(summary_frame["candidate_name"]))
        self.assertIn("sell_through_aligned_allocation_error", set(summary_frame["candidate_name"]))
        sell_through_row = summary_frame.loc[
            summary_frame["candidate_name"].eq("sell_through_aligned_allocation_error")
        ].iloc[0]
        self.assertTrue(sell_through_row["reduces_dependence_on_stock_basis_proxy_mismatch"])
        self.assertTrue(sell_through_row["creates_cleaner_promotion_decision_boundary"])

    def test_candidate_ranking_selects_sell_through_aligned_error_for_shadow_only_design(self) -> None:
        artifacts = _build_target_contract_design_artifacts(
            run_id="design-ranking",
            source_manifest_path="multi-slice-manifest.json",
            source_manifest_payload=_source_manifest_payload(decision="candidate_for_shadow_training"),
            source_rows=_three_slice_rows(),
        )
        proposal = artifacts["proposal_payload"]

        self.assertEqual(
            proposal["best_target_design_candidate"]["candidate_name"],
            "sell_through_aligned_allocation_error",
        )
        self.assertEqual(proposal["decision"], "candidate_for_shadow_training")
        self.assertTrue(proposal["should_become_candidate_for_shadow_training"])
        self.assertFalse(proposal["should_become_candidate_for_primary_training"])
        self.assertTrue(proposal["current_trainer_contract_remains_live_default"])
        self.assertTrue(proposal["policy_remains_paused"])

    def test_missing_design_evidence_fails_loud(self) -> None:
        source_rows = _three_slice_rows().drop(columns=["historical_allocated_units"])

        with self.assertRaisesRegex(ValueError, "target contract design evidence requires columns"):
            _build_target_contract_design_artifacts(
                run_id="missing-evidence",
                source_manifest_path="multi-slice-manifest.json",
                source_manifest_payload=_source_manifest_payload(),
                source_rows=source_rows,
            )

    def test_design_evaluator_persists_diagnostics_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_root = temp_path / "source"
            slice_runs: list[dict[str, str]] = []
            for index, slice_identifier in enumerate(("slice-a", "slice-b", "slice-c"), start=1):
                child_root = source_root / f"child-{index}"
                child_root.mkdir(parents=True)
                row_path = child_root / "target_contract_row_diagnostics.parquet"
                _design_rows(slice_identifier).to_parquet(row_path, index=False)
                child_manifest_path = child_root / "run_manifest.json"
                child_manifest_path.write_text(
                    json.dumps(
                        {
                            "run_id": f"child-{index}",
                            "artifact_files": {"target_contract_row_diagnostics_parquet": str(row_path)},
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                slice_runs.append(
                    {
                        "slice_identifier": slice_identifier,
                        "child_run_id": f"child-{index}",
                        "manifest_path": str(child_manifest_path),
                    }
                )
            manifest_payload = _source_manifest_payload(decision="candidate_for_shadow_training")
            manifest_payload["slice_runs"] = slice_runs
            source_manifest_path = source_root / "target_mode_multi_slice_manifest.json"
            source_manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")
            artifact_paths = PromotionArtifactPaths(root=temp_path / "promotions_artifacts", local_inspection_root=None)

            artifacts = PromotionTargetContractDesignEvaluator().evaluate(
                run_id="target-design",
                multi_slice_manifest_path=source_manifest_path,
                artifact_paths=artifact_paths,
            )

            self.assertTrue(Path(artifacts.summary_json_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.bucket_ranking_json_path).exists())
            self.assertTrue(Path(artifacts.bucket_ranking_csv_path).exists())
            self.assertTrue(Path(artifacts.residual_examples_json_path).exists())
            self.assertTrue(Path(artifacts.residual_examples_csv_path).exists())
            self.assertTrue(Path(artifacts.proposal_json_path).exists())
            self.assertFalse(artifacts.proposal["should_become_candidate_for_primary_training"])
            self.assertFalse(artifacts.proposal["production_training_target_was_replaced"])

    def test_design_artifact_fields_do_not_enter_model_use_features(self) -> None:
        frame = pd.DataFrame(
            {
                "store_number_key": [772],
                "sku_number_key": [93339],
                "promotion_start_date_date": ["2026-01-01"],
                "stock_basis_units": [8.0],
                "target_contract_design_candidate": ["sell_through_aligned_allocation_error"],
                "target_contract_design_decision": ["candidate_for_shadow_training"],
                "target_contract_design_units_mae": [0.0],
            }
        )

        _, schema = prepare_model_input_frame(frame)

        self.assertNotIn("target_contract_design_candidate", schema.feature_columns)
        self.assertNotIn("target_contract_design_decision", schema.feature_columns)
        self.assertNotIn("target_contract_design_units_mae", schema.feature_columns)

    def test_design_runtime_defaults_to_dual_contract_diagnostics_and_persists_runtime_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, source_artifacts, _ = _build_design_runtime_source_artifacts(
                temp_path,
                slice_identifier="runtime-design-default",
            )

            runtime_artifacts = run_target_contract_design(
                artifact_root=str(artifact_paths.root),
                run_id="runtime-target-contract-design",
                multi_slice_manifest_path=source_artifacts.manifest_path,
            )
            runtime_manifest_payload = json.loads(
                Path(runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )

            self.assertTrue(Path(runtime_artifacts.proposal_json_path).exists())

        self.assertEqual(runtime_artifacts.proposal["decision"], "diagnostics_only")
        self.assertIsNone(runtime_manifest_payload["requested_target_mode"])
        self.assertEqual(runtime_manifest_payload["resolved_target_mode"], "dual_contract_diagnostics")
        self.assertEqual(runtime_manifest_payload["requested_evaluator_mode"], "multi_slice_manifest_path")
        self.assertEqual(runtime_manifest_payload["resolved_evaluator_mode"], "multi_slice_manifest_path")
        self.assertEqual(
            runtime_manifest_payload["output_artifact_paths"]["target_contract_design_proposal_json_path"],
            runtime_artifacts.proposal_json_path,
        )

    def test_design_runtime_explicit_child_run_root_replay_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, _, child_manifest_path = _build_design_runtime_source_artifacts(
                temp_path,
                slice_identifier="runtime-design-explicit",
            )

            runtime_artifacts = run_target_contract_design(
                artifact_root=str(artifact_paths.root),
                run_id="runtime-target-contract-design-explicit",
                slice_inputs=[child_manifest_path.parent],
                target_mode="dual_contract_diagnostics",
            )
            runtime_manifest_payload = json.loads(
                Path(runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )

            self.assertTrue(Path(runtime_artifacts.summary_json_path).exists())

        self.assertEqual(runtime_manifest_payload["requested_evaluator_mode"], "explicit_slice_inputs")
        self.assertEqual(runtime_manifest_payload["resolved_evaluator_mode"], "explicit_slice_inputs")
        self.assertEqual(runtime_manifest_payload["source_slice_inputs"], [str(child_manifest_path.parent.resolve())])
        self.assertEqual(runtime_artifacts.proposal["decision"], "diagnostics_only")

    def test_design_runtime_manifest_source_fails_loud_when_child_row_diagnostics_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, source_artifacts, child_manifest_path = _build_design_runtime_source_artifacts(
                temp_path,
                slice_identifier="runtime-design-missing-upstream",
            )
            child_manifest_payload = json.loads(child_manifest_path.read_text(encoding="utf-8"))
            row_diagnostics_path = Path(
                child_manifest_payload["artifact_files"]["target_contract_row_diagnostics_parquet"]
            )
            row_diagnostics_path.unlink()

            with self.assertRaisesRegex(FileNotFoundError, "target_contract_row_diagnostics.parquet"):
                run_target_contract_design(
                    artifact_root=str(artifact_paths.root),
                    run_id="runtime-target-contract-design-missing-upstream",
                    multi_slice_manifest_path=source_artifacts.manifest_path,
                )


if __name__ == "__main__":
    unittest.main()