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
    _TARGET_CONTRACT_DIVERGENCE_DRIVER_REALISED_PROMO,
    _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS,
    _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
    PromotionTargetModeShadowEvaluator,
    _build_completed_slice_inventory_frame,
    _build_target_design_repeated_evidence_gate_payload,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.run_promotions_target_contract_design import (  # noqa: E402
    run_target_contract_design,
)
from runtime.promotions.run_promotions_target_design_repeated_evidence import (  # noqa: E402
    run_target_design_repeated_evidence,
)
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


def _training_ready_rows(row_count: int, *, include_cost: bool = True) -> pd.DataFrame:
    start_dates = ["2026-01-01", "2026-02-01", "2026-03-01"]
    end_dates = ["2026-01-28", "2026-02-28", "2026-03-28"]
    frame = pd.DataFrame(
        {
            "store_number": ["772"] * row_count,
            "sku_number": [str(90000 + index) for index in range(row_count)],
            "promotion_start_date_date": [start_dates[index % len(start_dates)] for index in range(row_count)],
            "promotional_end_date_date": [end_dates[index % len(end_dates)] for index in range(row_count)],
            "promotion_name": [f"Completed Slice {index % len(start_dates)}" for index in range(row_count)],
            "pl_allocation_qty": [10.0 + (index % 4) for index in range(row_count)],
            "actual_units_sold_promo": [7.0 + (index % 2) for index in range(row_count)],
        }
    )
    if include_cost:
        frame["promo_effective_cost"] = [2.0 + (index % 3) for index in range(row_count)]
    return frame


def _write_training_ready(root: Path, name: str, frame: pd.DataFrame) -> Path:
    dataset_dir = root / name
    dataset_dir.mkdir(parents=True)
    dataset_path = dataset_dir / "training_ready.parquet"
    frame.to_parquet(dataset_path, index=False)
    return dataset_path


def _build_repeated_evidence_runtime_source_artifacts(
    temp_path: Path,
    *,
    slice_identifier: str,
) -> tuple[PromotionArtifactPaths, Path, Path]:
    artifact_paths = PromotionArtifactPaths(root=temp_path / "promotions_artifacts", local_inspection_root=None)
    completed_base_frame = build_completed_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(completed_base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    dataset_result = PromotionDatasetAssembler().assemble_training_dataset(
        run_id=f"{slice_identifier}-dataset",
        base_frame=completed_base_frame,
        target_frame=target_result.frame,
        feature_frame=feature_result.frame,
        target_columns=target_result.target_columns,
        feature_columns=feature_result.feature_columns,
        artifact_paths=artifact_paths,
    )
    slice_manifest_path = temp_path / f"{slice_identifier}.json"
    slice_manifest_path.write_text(
        json.dumps(
            {
                "slice_identifier": slice_identifier,
                "training_ready_dataset_path": dataset_result.dataset_path,
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
    child_manifest_payload = json.loads(child_manifest_path.read_text(encoding="utf-8"))
    dataset_path = Path(child_manifest_payload["dataset_path"])
    dataset_frame = pd.read_parquet(dataset_path)
    repeat_factor = (120 + len(dataset_frame.index) - 1) // len(dataset_frame.index)
    dataset_frame = pd.concat(
        [
            dataset_frame.assign(
                sku_number=[f"{value}-{repeat_index}" for value in dataset_frame["sku_number"].astype(str)]
            )
            for repeat_index in range(repeat_factor)
        ],
        ignore_index=True,
    ).head(120)
    dataset_frame.to_parquet(dataset_path, index=False)
    design_runtime_artifacts = run_target_contract_design(
        artifact_root=str(artifact_paths.root),
        run_id=f"{slice_identifier}-design-runtime",
        multi_slice_manifest_path=source_artifacts.manifest_path,
    )
    proposal_root = Path(design_runtime_artifacts.proposal_json_path).parent
    return artifact_paths, Path(design_runtime_artifacts.runtime_manifest_path), proposal_root


def _gate_rows(
    *,
    slice_count: int = 5,
    comparable_rows: int = 220,
    coverage_rate: float = 0.98,
    exclusion_rate: float = 0.02,
    relative_improvement: float = 0.08,
    dominant_driver: str = _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS,
    best_candidate: bool = True,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "slice_identifier": f"slice-{index}",
                "row_count": comparable_rows,
                "comparable_rows": comparable_rows,
                "coverage_rate": coverage_rate,
                "exclusion_rate": exclusion_rate,
                "current_shadow_mae_on_historical_target": 10.0,
                "candidate_shadow_mae_on_historical_target": 10.0 - relative_improvement,
                "absolute_improvement": relative_improvement,
                "relative_improvement": relative_improvement,
                "dominant_divergence_driver": dominant_driver,
                "slice_gate_decision": "candidate_for_shadow_training",
                "target_design_candidate": _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
                "candidate_units_mae_against_business_mistake": 0.0,
                "candidate_capital_mae_against_business_mistake": 0.0,
                "candidate_units_mae_improvement_rate_vs_stock_basis": 1.0,
                "cleaner_promotion_decision_boundary": True,
                "reduces_dependence_on_stock_basis_proxy_mismatch": True,
                "best_candidate_name_for_slice": (
                    _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE if best_candidate else "historical_excess_units"
                ),
                "candidate_is_best_for_slice": best_candidate,
            }
            for index in range(slice_count)
        ]
    )


class PromotionTargetDesignRepeatedEvidenceTests(unittest.TestCase):
    def test_completed_slice_discovery_filters_missing_small_and_duplicate_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            good_frame = _training_ready_rows(120)
            _write_training_ready(root, "good-slice", good_frame)
            _write_training_ready(root, "duplicate-good-slice", good_frame)
            _write_training_ready(root, "missing-cost-slice", _training_ready_rows(120, include_cost=False))
            _write_training_ready(root, "small-slice", _training_ready_rows(20))

            inventory = _build_completed_slice_inventory_frame([root])

        included = inventory.loc[inventory["included"].astype(bool)]
        excluded_reasons = set(inventory.loc[~inventory["included"].astype(bool), "exclusion_reason"].astype(str))
        self.assertEqual(len(included.index), 1)
        self.assertIn("duplicate_completed_slice_fingerprint", excluded_reasons)
        self.assertIn("row_count_below_minimum", excluded_reasons)
        self.assertTrue(any("evidence_read_or_target_build_failed" in reason for reason in excluded_reasons))

    def test_completed_slice_discovery_fails_loud_for_missing_input(self) -> None:
        with self.assertRaises(FileNotFoundError):
            _build_completed_slice_inventory_frame(["/definitely/not/a/completed-slice"])

    def test_stable_repeated_evidence_promotes_to_shadow_training_candidate(self) -> None:
        gate = _build_target_design_repeated_evidence_gate_payload(
            _gate_rows(),
            target_design_candidate=_TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
        )

        self.assertEqual(gate["decision"], "candidate_for_shadow_training")
        self.assertTrue(gate["should_promote_to_candidate_for_shadow_training"])
        self.assertFalse(gate["should_promote_to_candidate_for_primary_training"])
        self.assertTrue(gate["current_trainer_contract_remains_live_default"])
        self.assertTrue(gate["policy_remains_paused"])

    def test_noisy_or_shallow_repeated_evidence_stays_diagnostics_only(self) -> None:
        shallow_rows = _gate_rows(slice_count=3, comparable_rows=63, coverage_rate=0.94, exclusion_rate=0.06)
        shallow_rows.loc[2, "relative_improvement"] = 0.0
        shallow_rows.loc[2, "absolute_improvement"] = 0.0

        gate = _build_target_design_repeated_evidence_gate_payload(
            shallow_rows,
            target_design_candidate=_TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
        )

        self.assertEqual(gate["decision"], "diagnostics_only")
        self.assertIn("insufficient_completed_slice_count", gate["shadow_promotion_blockers"])
        self.assertIn("insufficient_comparable_rows_per_slice", gate["shadow_promotion_blockers"])
        self.assertIn("coverage_below_threshold", gate["shadow_promotion_blockers"])
        self.assertIn("exclusion_rate_above_threshold", gate["shadow_promotion_blockers"])

    def test_wrong_dominant_driver_blocks_shadow_promotion(self) -> None:
        gate = _build_target_design_repeated_evidence_gate_payload(
            _gate_rows(dominant_driver=_TARGET_CONTRACT_DIVERGENCE_DRIVER_REALISED_PROMO),
            target_design_candidate=_TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
        )

        self.assertEqual(gate["decision"], "diagnostics_only")
        self.assertIn("stock_basis_proxy_mismatch_not_persistent", gate["shadow_promotion_blockers"])

    def test_runtime_manifest_source_defaults_to_dual_contract_diagnostics_and_persists_runtime_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, design_runtime_manifest_path, _ = _build_repeated_evidence_runtime_source_artifacts(
                temp_path,
                slice_identifier="repeated-evidence-runtime-default",
            )

            runtime_artifacts = run_target_design_repeated_evidence(
                artifact_root=str(artifact_paths.root),
                run_id="target-design-repeated-evidence-runtime",
                design_runtime_manifest_path=design_runtime_manifest_path,
            )
            runtime_manifest_payload = json.loads(
                Path(runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )

            self.assertTrue(Path(runtime_artifacts.evaluator_manifest_path).exists())
            self.assertTrue(Path(runtime_artifacts.summary_json_path).exists())

        self.assertEqual(runtime_artifacts.gate["decision"], "diagnostics_only")
        self.assertEqual(runtime_artifacts.target_design_candidate, _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE)
        self.assertIsNone(runtime_manifest_payload["requested_target_mode"])
        self.assertEqual(runtime_manifest_payload["resolved_target_mode"], "dual_contract_diagnostics")
        self.assertEqual(runtime_manifest_payload["requested_evaluator_mode"], "design_runtime_manifest_path")
        self.assertEqual(runtime_manifest_payload["resolved_evaluator_mode"], "design_runtime_manifest_path")
        self.assertTrue(runtime_manifest_payload["diagnostics_only_confirmation"]["runtime_path_is_diagnostics_only"])
        self.assertTrue(runtime_manifest_payload["diagnostics_only_confirmation"]["repeated_evidence_gate_is_diagnostics_only"])
        self.assertEqual(
            runtime_manifest_payload["output_artifact_paths"]["target_design_repeated_evidence_manifest_path"],
            runtime_artifacts.evaluator_manifest_path,
        )

    def test_runtime_explicit_proposal_root_replay_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, _, proposal_root = _build_repeated_evidence_runtime_source_artifacts(
                temp_path,
                slice_identifier="repeated-evidence-runtime-explicit",
            )

            runtime_artifacts = run_target_design_repeated_evidence(
                artifact_root=str(artifact_paths.root),
                run_id="target-design-repeated-evidence-runtime-explicit",
                proposal_inputs=[proposal_root],
                target_mode="dual_contract_diagnostics",
            )
            runtime_manifest_payload = json.loads(
                Path(runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )

            self.assertTrue(Path(runtime_artifacts.gate_json_path).exists())

        self.assertEqual(runtime_artifacts.gate["decision"], "diagnostics_only")
        self.assertEqual(runtime_manifest_payload["requested_evaluator_mode"], "explicit_proposal_inputs")
        self.assertEqual(runtime_manifest_payload["resolved_evaluator_mode"], "explicit_proposal_inputs")
        self.assertEqual(runtime_manifest_payload["source_proposal_inputs"], [str(proposal_root.resolve())])

    def test_runtime_manifest_source_fails_loud_when_upstream_design_artifact_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths, design_runtime_manifest_path, proposal_root = _build_repeated_evidence_runtime_source_artifacts(
                temp_path,
                slice_identifier="repeated-evidence-runtime-missing-upstream",
            )
            proposal_path = proposal_root / "target_contract_design_proposal.json"
            proposal_path.unlink()

            with self.assertRaisesRegex(FileNotFoundError, "target_contract_design_proposal.json"):
                run_target_design_repeated_evidence(
                    artifact_root=str(artifact_paths.root),
                    run_id="target-design-repeated-evidence-runtime-missing-upstream",
                    design_runtime_manifest_path=design_runtime_manifest_path,
                )


if __name__ == "__main__":
    unittest.main()