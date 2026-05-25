from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import _build_weak_slice_repair_options  # noqa: E402
from runtime.promotions.run_promotions_target_promotion_readiness import (  # noqa: E402
    run_target_promotion_readiness,
)
from runtime.promotions.run_promotions_weak_slice_repair import (  # noqa: E402
    run_weak_slice_repair,
)
from tests.unit.test_promotions_target_promotion_readiness import (  # noqa: E402
    _build_readiness_runtime_source_artifacts,
)


class PromotionWeakSliceRepairTests(unittest.TestCase):
    def test_promotion_readiness_runtime_manifest_replay_uses_existing_readiness_sources(self) -> None:
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
                slice_identifier="weak-slice-repair-readiness-runtime",
            )
            readiness_runtime_artifacts = run_target_promotion_readiness(
                artifact_root=str(artifact_paths.root),
                run_id="promotion-readiness-runtime-for-weak-slice-repair",
                three_way_runtime_manifest_path=three_way_runtime_artifacts.runtime_manifest_path,
            )

            runtime_artifacts = run_weak_slice_repair(
                artifact_root=str(artifact_paths.root),
                run_id="weak-slice-repair-runtime-from-readiness",
                promotion_readiness_runtime_manifest_path=readiness_runtime_artifacts.runtime_manifest_path,
            )
            runtime_manifest_payload = json.loads(
                Path(runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )
            self.assertTrue(Path(runtime_artifacts.plan_json_path).exists())

        self.assertTrue(runtime_artifacts.decision_packet["diagnostics_only"])
        self.assertEqual(
            runtime_artifacts.decision_packet["best_repair_option"]["repair_category"],
            "row_count_repairs",
        )
        self.assertEqual(
            runtime_artifacts.decision_packet["weakest_slice_blocker_family"],
            "row_count_repairs",
        )
        self.assertEqual(
            runtime_manifest_payload["requested_source_mode"],
            "promotion_readiness_runtime_manifest_path",
        )
        self.assertEqual(
            runtime_manifest_payload["resolved_source_mode"],
            "promotion_readiness_runtime_manifest_path",
        )

    def test_three_way_runtime_manifest_replay_builds_plan_without_readiness_sources(self) -> None:
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
                slice_identifier="weak-slice-repair-three-way-runtime",
            )

            runtime_artifacts = run_weak_slice_repair(
                artifact_root=str(artifact_paths.root),
                run_id="weak-slice-repair-runtime-from-three-way",
                three_way_runtime_manifest_path=three_way_runtime_artifacts.runtime_manifest_path,
            )

        self.assertIsNone(runtime_artifacts.source_promotion_readiness_runtime_manifest_path)
        self.assertEqual(runtime_artifacts.requested_source_mode, "three_way_runtime_manifest_path")
        self.assertEqual(
            runtime_artifacts.decision_packet["best_repair_option"]["repair_category"],
            "row_count_repairs",
        )
        self.assertGreaterEqual(runtime_artifacts.decision_packet["weak_slice_count"], 1)

    def test_plan_separates_repair_categories_and_marks_missing_exclusion_attribution(self) -> None:
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
                slice_identifier="weak-slice-repair-plan-categories",
            )
            readiness_runtime_artifacts = run_target_promotion_readiness(
                artifact_root=str(artifact_paths.root),
                run_id="promotion-readiness-runtime-for-weak-slice-plan-categories",
                three_way_runtime_manifest_path=three_way_runtime_artifacts.runtime_manifest_path,
            )

            runtime_artifacts = run_weak_slice_repair(
                artifact_root=str(artifact_paths.root),
                run_id="weak-slice-repair-runtime-plan-categories",
                promotion_readiness_runtime_manifest_path=readiness_runtime_artifacts.runtime_manifest_path,
            )
            plan_payload = json.loads(Path(runtime_artifacts.plan_json_path).read_text(encoding="utf-8"))

        repair_options_by_category = plan_payload["repair_options_by_category"]
        self.assertIn("row_count_repairs", repair_options_by_category)
        self.assertIn("exclusion_rate_repairs", repair_options_by_category)
        self.assertIn("evidence_quality_repairs", repair_options_by_category)
        self.assertIn("source_chain_governance_repairs", repair_options_by_category)

    def test_non_diagnostic_exclusion_attribution_emits_source_chain_repair_option(self) -> None:
        options = _build_weak_slice_repair_options(
            slice_context={
                "weak_slice": True,
                "slice_identifier": "policy-measurement-liveproof-20260522T000000Z",
                "weak_slice_blocker": "insufficient_comparable_rows_per_slice",
                "current_comparable_rows": 63,
                "required_comparable_rows": 100,
                "comparable_row_shortfall": 37,
                "current_exclusion_rate": 0.05970149253731343,
                "allowed_exclusion_rate": 0.05,
                "exclusion_gap": 0.009701492537313428,
                "current_coverage_rate": 0.9402985074626866,
                "required_coverage_rate": 0.95,
                "coverage_gap": 0.009701492537313446,
                "evaluation_row_count": 67,
                "excluded_row_count": 4,
                "candidate_improvement": 0.0,
                "candidate_outperformed": False,
                "minimum_positive_improvement_slice_share": 0.8,
                "current_positive_improvement_slice_count": 2,
                "current_slice_count": 3,
                "blocker_names": [
                    "insufficient_comparable_rows_per_slice",
                    "historical_target_exclusions_not_acceptable",
                    "coverage_below_threshold",
                    "candidate_did_not_improve_on_enough_slices",
                    "missing_governed_exclusion_attribution",
                ],
                "source_chain_governance_repair_needed": True,
                "replay_exclusion_reason_counts": {"eligible": 4},
                "summary_row": {"evidence_quality_repair_needed": True},
            },
            current_global_dominant_blocker="insufficient_comparable_rows_per_slice",
            readiness_ranked_blockers=(
                "insufficient_comparable_rows_per_slice",
                "historical_target_exclusions_not_acceptable",
                "candidate_did_not_improve_on_enough_slices",
            ),
        )

        governance_rows = [
            row for row in options if row["repair_category"] == "source_chain_governance_repairs"
        ]
        self.assertEqual(len(governance_rows), 1)
        self.assertIn("non-diagnostic", governance_rows[0]["minimum_next_evidence_required"])
        self.assertIn("eligible:4", governance_rows[0]["note"])

    def test_inconsistent_readiness_source_chain_fails_loud(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            left_path = temp_path / "left"
            right_path = temp_path / "right"
            left_path.mkdir()
            right_path.mkdir()
            (
                left_artifact_paths,
                _,
                _,
                _,
                left_three_way_runtime_artifacts,
                _,
            ) = _build_readiness_runtime_source_artifacts(
                left_path,
                slice_identifier="weak-slice-repair-inconsistent-left",
            )
            left_readiness_runtime_artifacts = run_target_promotion_readiness(
                artifact_root=str(left_artifact_paths.root),
                run_id="promotion-readiness-runtime-inconsistent-left",
                three_way_runtime_manifest_path=left_three_way_runtime_artifacts.runtime_manifest_path,
            )
            (
                _,
                _,
                _,
                _,
                right_three_way_runtime_artifacts,
                _,
            ) = _build_readiness_runtime_source_artifacts(
                right_path,
                slice_identifier="weak-slice-repair-inconsistent-right",
            )

            mutated_runtime_manifest_path = left_path / "mutated_promotion_readiness_runtime_manifest.json"
            mutated_runtime_manifest_payload = json.loads(
                Path(left_readiness_runtime_artifacts.runtime_manifest_path).read_text(encoding="utf-8")
            )
            mutated_runtime_manifest_payload["source_three_way_runtime_manifest_path"] = (
                right_three_way_runtime_artifacts.runtime_manifest_path
            )
            mutated_runtime_manifest_path.write_text(
                json.dumps(mutated_runtime_manifest_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "disagree on source_target_contract_three_way_proposal_path"):
                run_weak_slice_repair(
                    artifact_root=str(left_artifact_paths.root),
                    run_id="weak-slice-repair-runtime-inconsistent-readiness-source",
                    promotion_readiness_runtime_manifest_path=str(mutated_runtime_manifest_path),
                )


if __name__ == "__main__":
    unittest.main()


def _force_non_diagnostic_exclusion_lineage(three_way_runtime_manifest_path: str) -> None:
    three_way_runtime_manifest_payload = json.loads(
        Path(three_way_runtime_manifest_path).read_text(encoding="utf-8")
    )
    resolved_source_input = three_way_runtime_manifest_payload["resolved_source_inputs"][0]
    multi_slice_manifest_path = _resolve_path(
        resolved_source_input["source_multi_slice_manifest_path"],
        Path(three_way_runtime_manifest_path).parent,
    )
    multi_slice_manifest_payload = json.loads(multi_slice_manifest_path.read_text(encoding="utf-8"))
    multi_slice_summary_path = _resolve_path(
        multi_slice_manifest_payload["summary_json_path"],
        multi_slice_manifest_path.parent,
    )
    multi_slice_summary_payload = json.loads(multi_slice_summary_path.read_text(encoding="utf-8"))
    weak_slice_row = min(
        multi_slice_summary_payload["slice_rows"],
        key=lambda row: int(row["comparable_rows"]),
    )
    slice_run_artifact = next(
        record
        for record in multi_slice_summary_payload["slice_run_artifact_paths"]
        if record["slice_identifier"] == weak_slice_row["slice_identifier"]
    )
    run_manifest_path = _resolve_path(slice_run_artifact["manifest_path"], multi_slice_summary_path.parent)
    run_manifest_payload = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    row_diagnostics_path = _resolve_path(
        run_manifest_payload["artifact_files"]["target_contract_row_diagnostics_parquet"],
        run_manifest_path.parent,
    )
    row_diagnostics_frame = pd.read_parquet(row_diagnostics_path)
    invalid_mask = pd.to_numeric(
        row_diagnostics_frame["historical_contract_valid_flag"],
        errors="coerce",
    ).fillna(0.0).lt(1.0)
    row_diagnostics_frame.loc[invalid_mask, "replay_exclusion_reason"] = "eligible"
    row_diagnostics_frame.to_parquet(row_diagnostics_path, index=False)


def _resolve_path(path_value: str, base_path: Path) -> Path:
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        candidate = (base_path / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate