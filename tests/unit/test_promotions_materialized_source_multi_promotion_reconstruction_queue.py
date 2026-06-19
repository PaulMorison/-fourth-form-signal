from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_multi_promotion_reconstruction_queue as module  # noqa: E402


PROMOTION_KEYS = (
    "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
    "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX",
    "772|2026-04-23|2026-05-06|Allocation Report - WK43&44 HEALTH & BEAUTY OFFERS",
    "772|2026-04-09|2026-04-22|Allocation Report - WK41&42 SKINCARE GOODY BAG",
    "772|2026-03-24|2026-04-22|Allocation Report - New Line 26 WK38",
)

FOLDER_NAMES = (
    "promotion_772-2026-05-21-2026-06-03-allocation-report-wk47-48-winter-part-1",
    "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box",
    "promotion_772-2026-04-23-2026-05-06-allocation-report-wk43-44-health-beauty-offers",
    "promotion_772-2026-04-09-2026-04-22-allocation-report-wk41-42-skincare-goody-bag",
    "promotion_772-2026-03-24-2026-04-22-allocation-report-new-line-26-wk38",
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _packet_index_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for promotion_key, folder_name in zip(PROMOTION_KEYS, FOLDER_NAMES, strict=True):
        _, start_date, end_date, promotion_name = promotion_key.split("|", 3)
        rows.append(
            {
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_start_date": start_date,
                "promotion_end_date": end_date,
                "packet_output_path": f"tmp/last5_promotions_diagnostic_packets/source_materialized_promotions/{folder_name}",
                "downstream_full_diagnostic_chain_available_flag": 0,
            }
        )
    return rows


def _repeat_summary_rows() -> list[dict[str, object]]:
    return [
        {
            "metric_name": "SELECTED_PROMOTION",
            "metric_value": PROMOTION_KEYS[0],
            "metric_display": PROMOTION_KEYS[0],
            "notes": "",
        },
        {
            "metric_name": "MORE_PROMOTION_RECONSTRUCTION_SHOULD_RUN_NEXT",
            "metric_value": 1,
            "metric_display": "1",
            "notes": "",
        },
    ]


def _missing_evidence_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for promotion_key in PROMOTION_KEYS[1:]:
        _, start_date, end_date, promotion_name = promotion_key.split("|", 3)
        rows.append(
            {
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_start_date": start_date,
                "promotion_end_date": end_date,
                "source_materialized_available_flag": 1,
                "downstream_chain_available_flag": 0,
                "family_comparable_evidence_available_flag": 0,
                "impacted_rule_family_count": 4,
                "impacted_rule_families": "A, B, C, D",
                "missing_reason": "Promotion exists as a source-materialized packet but still needs downstream reconstruction for comparable repeat-evidence work.",
                "candidate_recommendation": "RECONSTRUCT_MORE_PROMOTIONS_FIRST",
            }
        )
    return rows


def _rebuild_queue_rows(*, block_new_line: bool = True) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rank, promotion_key in enumerate(PROMOTION_KEYS, start=1):
        _, start_date, end_date, promotion_name = promotion_key.split("|", 3)
        actual_candidate_flag = 1
        if block_new_line and promotion_key == PROMOTION_KEYS[4]:
            actual_candidate_flag = 0
        rows.append(
            {
                "promotion_priority_rank": rank,
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_start_date": start_date,
                "promotion_end_date": end_date,
                "queue_row_count": 8,
                "actual_outcome_join_required_flag": 1,
                "actual_outcome_join_candidate_flag": actual_candidate_flag,
                "operator_audit_join_required_flag": 0,
                "operator_audit_join_candidate_flag": 0,
                "schema_mapping_required_flag": 1,
                "blocked_flag": int(actual_candidate_flag == 0),
                "potentially_ready_after_joins_flag": int(actual_candidate_flag == 1),
                "first_required_action": "VALIDATE_JOIN_KEY_COVERAGE",
                "source_file_path": f"tmp/source_{rank}.csv",
                "recommended_next_step": "Validate join key coverage first, then author diagnostics-only join specs without running the joins yet.",
                "reason": "Diagnostics-only rebuild queue context.",
            }
        )
    return rows


def _write_source_rows(packet_root: Path) -> None:
    for folder_name in FOLDER_NAMES:
        _write_csv(
            packet_root / module.SOURCE_MATERIALIZED_FOLDER_NAME / folder_name / module.SOURCE_ROWS_FILE_NAME,
            [{"sku_number": "1001"}, {"sku_number": "1002"}],
        )


def _write_inputs(packet_root: Path, *, block_new_line: bool = True) -> None:
    _write_csv(packet_root / module.PACKET_INDEX_FILE_NAME, _packet_index_rows())
    _write_csv(
        packet_root
        / module.REPEAT_EVIDENCE_PACK_FOLDER_NAME
        / module.REPEAT_EVIDENCE_SUMMARY_FILE_NAME,
        _repeat_summary_rows(),
    )
    _write_csv(
        packet_root
        / module.REPEAT_EVIDENCE_PACK_FOLDER_NAME
        / module.REPEAT_EVIDENCE_MISSING_EVIDENCE_FILE_NAME,
        _missing_evidence_rows(),
    )
    _write_csv(
        packet_root / module.REBUILD_QUEUE_FOLDER_NAME / module.REBUILD_QUEUE_BY_PROMOTION_FILE_NAME,
        _rebuild_queue_rows(block_new_line=block_new_line),
    )
    _write_source_rows(packet_root)


class PromotionsMaterializedSourceMultiPromotionReconstructionQueueTests(unittest.TestCase):
    def test_detects_materialized_and_complete_vs_incomplete_promotions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_multi_promotion_reconstruction_queue(
                packet_root=packet_root,
                dry_run=True,
            )

            self.assertEqual(result.source_materialized_promotion_count, 5)
            self.assertEqual(result.already_complete_promotion_count, 1)
            self.assertEqual(result.incomplete_promotion_count, 4)
            self.assertEqual(result.promotions_ready_to_start, 3)
            self.assertEqual(result.blocked_promotion_count, 1)
            self.assertEqual(result.overall_queue_status, module.PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY)

    def test_writes_stage_plan_for_incomplete_promotions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_multi_promotion_reconstruction_queue(
                packet_root=packet_root,
                dry_run=True,
            )

            stage_plan = result.stage_plan_frame
            self.assertEqual(len(stage_plan.index), 4 * len(module.STAGE_SPECS))
            first_stage_rows = stage_plan.loc[
                stage_plan["stage_name"].astype(str).eq(module.JOIN_KEY_VALIDATION)
            ]
            self.assertTrue(
                first_stage_rows["stage_status"].astype(str).isin(
                    [
                        module.PROMOTION_RECONSTRUCTION_READY_TO_START,
                        module.PROMOTION_RECONSTRUCTION_BLOCKED_MISSING_INPUTS,
                    ]
                ).all()
            )

    def test_blocks_when_required_stage_not_promotion_aware(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, block_new_line=False)

            def _awareness(spec: module.StageSpec) -> bool:
                return spec.stage_name != module.PREVIEW_JOIN

            with mock.patch.object(module, "_stage_is_promotion_key_aware", side_effect=_awareness):
                result = module.build_promotions_materialized_source_multi_promotion_reconstruction_queue(
                    packet_root=packet_root,
                    dry_run=True,
                )

            blocked_rows = result.by_promotion_frame.loc[
                result.by_promotion_frame["queue_status"].astype(str).eq(
                    module.PROMOTION_RECONSTRUCTION_BLOCKED_STAGE_NOT_PROMOTION_AWARE
                )
            ]
            self.assertEqual(len(blocked_rows.index), 4)
            preview_rows = result.stage_plan_frame.loc[
                result.stage_plan_frame["stage_name"].astype(str).eq(module.PREVIEW_JOIN)
            ]
            self.assertTrue(
                preview_rows["stage_status"].astype(str).eq(
                    module.PROMOTION_RECONSTRUCTION_BLOCKED_STAGE_NOT_PROMOTION_AWARE
                ).all()
            )

    def test_guardrail_validation_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            artifacts = module.write_promotions_materialized_source_multi_promotion_reconstruction_queue(
                packet_root=packet_root,
                dry_run=True,
            )
            validation_frame = pd.read_csv(artifacts.validation_csv_path)
            lookup = validation_frame.set_index("check_name")

            self.assertEqual(lookup.loc["NO_TRAINING_STARTED", "check_status"], "PASS")
            self.assertEqual(lookup.loc["NO_RECALIBRATION_STARTED", "check_status"], "PASS")
            self.assertEqual(lookup.loc["NO_PRODUCTION_LOGIC_CHANGED", "check_status"], "PASS")
            self.assertEqual(lookup.loc["NO_STAGE12_CHANGED", "check_status"], "PASS")
            self.assertTrue(Path(artifacts.stage_plan_csv_path).exists())


if __name__ == "__main__":
    unittest.main()