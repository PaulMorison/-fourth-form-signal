from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_promotion_isolation_plan as module  # noqa: E402


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


def _write_source_materialized_roots(packet_root: Path) -> None:
    for folder_name in FOLDER_NAMES:
        _write_csv(
            packet_root / module.SOURCE_MATERIALIZED_FOLDER_NAME / folder_name / "promotion_source_rows.csv",
            [{"sku_number": "1001"}],
        )


def _queue_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rank, (promotion_key, folder_name) in enumerate(zip(PROMOTION_KEYS, FOLDER_NAMES, strict=True), start=1):
        _, start_date, end_date, promotion_name = promotion_key.split("|", 3)
        already_complete_flag = int(rank == 1)
        incomplete_flag = int(rank != 1)
        ready_flag = int(rank in (2, 3, 4))
        blocked_flag = int(rank == 5)
        rows.append(
            {
                "queue_rank": rank,
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_start_date": start_date,
                "promotion_end_date": end_date,
                "source_materialized_available_flag": 1,
                "source_rows_detected_flag": 1,
                "already_complete_flag": already_complete_flag,
                "incomplete_flag": incomplete_flag,
                "selected_for_queue_flag": incomplete_flag,
                "queue_status": (
                    "PROMOTION_RECONSTRUCTION_ALREADY_COMPLETE"
                    if already_complete_flag
                    else "PROMOTION_RECONSTRUCTION_BLOCKED_MISSING_INPUTS"
                    if blocked_flag
                    else "PROMOTION_RECONSTRUCTION_READY_TO_START"
                ),
                "ready_to_start_flag": ready_flag,
                "blocked_flag": blocked_flag,
                "missing_input_count": int(rank == 5),
                "planned_stage_count": 15 if incomplete_flag else 0,
                "stage_runtimes_promotion_key_aware_flag": 1,
                "planner_only_recommended_flag": 1,
                "execution_mode_recommendation": "PLANNER_ONLY",
                "first_blocking_stage": "JOIN_SPEC_PACK" if blocked_flag else "",
                "first_required_action": "VALIDATE_JOIN_KEY_COVERAGE",
                "source_rows_path": str(
                    Path("tmp/last5_promotions_diagnostic_packets")
                    / module.SOURCE_MATERIALIZED_FOLDER_NAME
                    / folder_name
                    / "promotion_source_rows.csv"
                ),
                "source_file_path": f"tmp/source_{rank}.csv",
                "recommended_next_step": "Plan isolation first.",
                "reason": "Diagnostics-only queue context.",
            }
        )
    return rows


def _stage_plan_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rank, promotion_key in enumerate(PROMOTION_KEYS[1:], start=2):
        _, start_date, end_date, promotion_name = promotion_key.split("|", 3)
        for spec in module.STAGE_SPECS:
            rows.append(
                {
                    "queue_rank": rank,
                    "promotion_key": promotion_key,
                    "promotion_name": promotion_name,
                    "promotion_start_date": start_date,
                    "promotion_end_date": end_date,
                    "stage_order": spec.stage_order,
                    "stage_name": spec.stage_name,
                    "stage_runtime_module": spec.module_file_name.removesuffix(".py"),
                    "stage_output_folder_name": spec.output_folder_name,
                    "stage_promotion_key_aware_flag": 1,
                    "stage_input_ready_flag": 1 if spec.stage_order == 1 and rank != 5 else 0 if rank == 5 and spec.stage_order > 1 else 1,
                    "stage_status": "PROMOTION_RECONSTRUCTION_READY_TO_START" if spec.stage_order == 1 and rank != 5 else "PROMOTION_RECONSTRUCTION_BLOCKED_MISSING_INPUTS" if rank == 5 and spec.stage_order == 2 else "PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY",
                    "execution_command": "noop",
                    "execution_mode_recommendation": "PLANNER_ONLY",
                    "blocking_reason": "missing actual outcome source" if rank == 5 and spec.stage_order == 2 else "",
                    "notes": "queue planner",
                }
            )
    return rows


def _summary_rows() -> list[dict[str, object]]:
    return [
        {
            "metric_name": "QUEUE_STATUS",
            "metric_value": "PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY",
            "metric_display": "PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY",
            "notes": "",
        },
        {
            "metric_name": "INCOMPLETE_PROMOTION_COUNT",
            "metric_value": 4,
            "metric_display": "4",
            "notes": "",
        },
    ]


def _write_inputs(packet_root: Path) -> None:
    queue_root = packet_root / module.RECONSTRUCTION_QUEUE_FOLDER_NAME
    _write_csv(queue_root / module.QUEUE_ROWS_FILE_NAME, _queue_rows())
    _write_csv(queue_root / module.QUEUE_BY_PROMOTION_FILE_NAME, _queue_rows())
    _write_csv(queue_root / module.STAGE_PLAN_FILE_NAME, _stage_plan_rows())
    _write_csv(queue_root / module.QUEUE_SUMMARY_FILE_NAME, _summary_rows())
    _write_source_materialized_roots(packet_root)


class PromotionsMaterializedSourcePromotionIsolationPlanTests(unittest.TestCase):
    def test_isolated_roots_generated_for_incomplete_promotions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_promotion_isolation_plan(
                packet_root=packet_root
            )

            self.assertEqual(result.source_materialized_promotion_count, 5)
            self.assertEqual(result.incomplete_promotion_count, 4)
            self.assertEqual(result.isolated_roots_planned, 4)
            self.assertEqual(len(result.roots_frame.index), 4)

    def test_all_15_stages_mapped_for_each_incomplete_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_promotion_isolation_plan(
                packet_root=packet_root
            )

            self.assertEqual(result.stages_mapped_per_promotion, 15)
            self.assertEqual(len(result.stage_mapping_frame.index), 4 * 15)

    def test_shared_root_risk_and_runtime_changes_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_promotion_isolation_plan(
                packet_root=packet_root
            )

            self.assertEqual(
                result.isolation_plan_status,
                module.PROMOTION_ISOLATION_PLAN_READY_RUNTIME_CHANGES_REQUIRED,
            )
            self.assertEqual(result.shared_root_risk_status, "SHARED_ROOT_RISK_CONFIRMED")
            self.assertEqual(result.execution_mode_safe_now_flag, 0)
            self.assertEqual(result.stages_requiring_runtime_changes, 14)

    def test_write_outputs_and_execution_mode_blocked_until_isolation_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            artifacts = module.write_promotions_materialized_source_promotion_isolation_plan(
                packet_root=packet_root
            )
            summary_frame = pd.read_csv(artifacts.summary_csv_path)
            summary_lookup = summary_frame.set_index("metric_name")

            self.assertTrue(Path(artifacts.roots_csv_path).exists())
            self.assertTrue(Path(artifacts.stage_mapping_csv_path).exists())
            self.assertTrue(Path(artifacts.required_runtime_changes_csv_path).exists())
            self.assertTrue(Path(artifacts.execution_safety_csv_path).exists())
            self.assertEqual(
                str(summary_lookup.loc["ISOLATION_PLAN_STATUS", "metric_value"]),
                module.PROMOTION_ISOLATION_PLAN_READY_RUNTIME_CHANGES_REQUIRED,
            )
            self.assertEqual(
                str(summary_lookup.loc["EXECUTION_MODE_SAFE_NOW", "metric_value"]),
                "0",
            )


if __name__ == "__main__":
    unittest.main()