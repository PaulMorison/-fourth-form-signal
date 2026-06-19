from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_full_chain_isolated_dry_run_plan as module  # noqa: E402


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
            packet_root / module.SOURCE_MATERIALIZED_FOLDER_NAME / folder_name / module.SOURCE_ROWS_FILE_NAME,
            [{"sku_number": "1001"}],
        )


def _queue_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rank, (promotion_key, folder_name) in enumerate(
        zip(PROMOTION_KEYS, FOLDER_NAMES, strict=True), start=1
    ):
        _, start_date, end_date, promotion_name = promotion_key.split("|", 3)
        already_complete_flag = int(rank == 1)
        incomplete_flag = int(rank != 1)
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
                    else "PROMOTION_RECONSTRUCTION_READY_TO_START"
                ),
                "ready_to_start_flag": incomplete_flag,
                "blocked_flag": 0,
                "missing_input_count": 0,
                "planned_stage_count": 15 if incomplete_flag else 0,
                "stage_runtimes_promotion_key_aware_flag": 1,
                "planner_only_recommended_flag": 1,
                "execution_mode_recommendation": "PLANNER_ONLY",
                "first_blocking_stage": "",
                "first_required_action": "VALIDATE_JOIN_KEY_COVERAGE",
                "source_rows_path": str(
                    Path("tmp/last5_promotions_diagnostic_packets")
                    / module.SOURCE_MATERIALIZED_FOLDER_NAME
                    / folder_name
                    / module.SOURCE_ROWS_FILE_NAME
                ),
                "source_file_path": f"tmp/source_{rank}.csv",
                "recommended_next_step": "Plan isolated execution wiring only.",
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
                    "stage_input_ready_flag": 1,
                    "stage_status": (
                        "PROMOTION_RECONSTRUCTION_READY_TO_START"
                        if spec.stage_order == 1
                        else "PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY"
                    ),
                    "execution_command": "noop",
                    "execution_mode_recommendation": "PLANNER_ONLY",
                    "blocking_reason": "",
                    "notes": "queue planner",
                }
            )
    return rows


def _roots_rows(packet_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rank, (promotion_key, folder_name) in enumerate(
        zip(PROMOTION_KEYS[1:], FOLDER_NAMES[1:], strict=True), start=2
    ):
        _, start_date, end_date, promotion_name = promotion_key.split("|", 3)
        promotion_run_root = packet_root / "promotion_runs" / folder_name
        rows.append(
            {
                "queue_rank": rank,
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_start_date": start_date,
                "promotion_end_date": end_date,
                "source_rows_path": str(
                    Path("tmp/last5_promotions_diagnostic_packets")
                    / module.SOURCE_MATERIALIZED_FOLDER_NAME
                    / folder_name
                    / module.SOURCE_ROWS_FILE_NAME
                ),
                "current_queue_status": "PROMOTION_RECONSTRUCTION_READY_TO_START",
                "proposed_promotion_run_root": str(promotion_run_root),
                "proposed_stage_root_base": str(promotion_run_root / "<stage-output-folder>"),
                "planned_stage_count": 15,
                "missing_stage_mapping_count": 0,
                "shared_root_risk_flag": 0,
                "execution_mode_safe_now_flag": 1,
                "isolation_plan_status": "PROMOTION_ISOLATION_READY",
                "recommended_next_step": "Proceed only with a planner or smoke test.",
            }
        )
    return rows


def _stage_mapping_rows(packet_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for promotion_key, folder_name in zip(PROMOTION_KEYS[1:], FOLDER_NAMES[1:], strict=True):
        _, start_date, end_date, promotion_name = promotion_key.split("|", 3)
        promotion_run_root = packet_root / "promotion_runs" / folder_name
        for spec in module.STAGE_SPECS:
            rows.append(
                {
                    "queue_rank": PROMOTION_KEYS.index(promotion_key) + 1,
                    "promotion_key": promotion_key,
                    "promotion_name": promotion_name,
                    "promotion_start_date": start_date,
                    "promotion_end_date": end_date,
                    "stage_order": spec.stage_order,
                    "stage_name": spec.stage_name,
                    "current_shared_output_folder": str(packet_root / spec.output_folder_name),
                    "proposed_isolated_output_folder": str(
                        promotion_run_root / spec.output_folder_name
                    ),
                    "runtime_file": str(
                        Path(module.__file__).resolve().parent / spec.module_file_name
                    ),
                    "promotion_key_aware_flag": 1,
                    "requires_output_root_parameter_flag": 0,
                    "requires_input_root_parameter_flag": 0,
                    "safe_for_multi_promotion_execution_flag": 1,
                    "required_change": "No runtime code change required.",
                }
            )
    return rows


def _write_inputs(packet_root: Path) -> None:
    queue_root = packet_root / module.RECONSTRUCTION_QUEUE_FOLDER_NAME
    isolation_root = packet_root / module.PROMOTION_ISOLATION_PLAN_FOLDER_NAME
    _write_csv(queue_root / module.QUEUE_ROWS_FILE_NAME, _queue_rows())
    _write_csv(queue_root / module.STAGE_PLAN_FILE_NAME, _stage_plan_rows())
    _write_csv(isolation_root / module.ROOTS_FILE_NAME, _roots_rows(packet_root))
    _write_csv(
        isolation_root / module.STAGE_MAPPING_FILE_NAME,
        _stage_mapping_rows(packet_root),
    )
    _write_source_materialized_roots(packet_root)


class PromotionsMaterializedSourceFullChainIsolatedDryRunPlanTests(unittest.TestCase):
    def test_produces_15_command_rows_per_incomplete_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
                packet_root=packet_root,
                dry_run=True,
            )

            self.assertEqual(result.incomplete_promotion_count, 4)
            self.assertEqual(result.command_rows_generated, 4 * 15)
            self.assertEqual(result.stages_per_promotion, 15)

    def test_stage1_has_no_upstream_root_and_isolated_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
                packet_root=packet_root,
                dry_run=True,
            )

            stage1 = result.commands_frame.loc[
                result.commands_frame["stage_number"].astype(int).eq(1)
            ]
            self.assertTrue(stage1["uses_upstream_root_flag"].astype(int).eq(0).all())
            self.assertTrue(
                stage1["output_root"].astype(str).str.contains("/promotion_runs/").all()
            )

    def test_stages_2_to_15_include_upstream_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
                packet_root=packet_root,
                dry_run=True,
            )

            downstream = result.commands_frame.loc[
                result.commands_frame["stage_number"].astype(int).gt(1)
            ]
            self.assertTrue(downstream["uses_upstream_root_flag"].astype(int).eq(1).all())
            self.assertTrue(downstream["command"].astype(str).str.contains("--upstream-root").all())

    def test_every_stage_includes_isolated_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
                packet_root=packet_root,
                dry_run=True,
            )

            self.assertTrue(result.commands_frame["uses_output_root_flag"].astype(int).eq(1).all())
            self.assertTrue(result.commands_frame["command"].astype(str).str.contains("--output-root").all())

    def test_no_command_writes_to_shared_packet_root_stage_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
                packet_root=packet_root,
                dry_run=True,
            )

            self.assertEqual(result.shared_packet_root_write_risk_flag, 0)
            self.assertTrue(
                result.stage_contracts_frame["shared_packet_root_write_risk_flag"]
                .astype(int)
                .eq(0)
                .all()
            )

    def test_all_execution_flags_remain_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
                packet_root=packet_root,
                dry_run=True,
            )

            self.assertEqual(result.execution_allowed_flag, 0)
            self.assertTrue(result.commands_frame["execution_allowed_flag"].astype(int).eq(0).all())
            self.assertTrue(result.commands_frame["planner_only_flag"].astype(int).eq(1).all())

    def test_summary_confirms_all_15_stages_isolation_capable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
                packet_root=packet_root,
                dry_run=True,
            )

            summary = result.summary_frame.set_index("metric_name")
            self.assertEqual(result.planner_status, module.FULL_CHAIN_ISOLATED_DRY_RUN_PLAN_READY)
            self.assertEqual(
                str(summary.loc["ALL_15_STAGES_ISOLATION_CAPABLE", "metric_value"]),
                "1",
            )

    def test_summary_confirms_no_stage_local_blocker_remains(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
                packet_root=packet_root,
                dry_run=True,
            )

            summary = result.summary_frame.set_index("metric_name")
            self.assertEqual(
                str(summary.loc["NO_STAGE_LOCAL_BLOCKER_REMAINS", "metric_value"]),
                "1",
            )

    def test_planner_does_not_run_any_stage_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with mock.patch.object(module, "_command_for_stage", wraps=module._command_for_stage) as command_builder:
                result = module.build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
                    packet_root=packet_root,
                    dry_run=True,
                )

            self.assertEqual(command_builder.call_count, 4 * 15)
            self.assertEqual(result.execution_allowed_flag, 0)
            self.assertTrue(result.validation_frame["check_name"].astype(str).isin(["PLANNER_DOES_NOT_EXECUTE_STAGE_COMMANDS"]).any())

    def test_planner_does_not_generate_training_recalibration_repeat_shadow_production_or_stage12_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
                packet_root=packet_root,
                dry_run=True,
            )

            validation = result.validation_frame.set_index("check_name")
            self.assertEqual(str(validation.loc["NO_TRAINING_COMMAND_GENERATED", "check_status"]), "PASS")
            self.assertEqual(str(validation.loc["NO_RECALIBRATION_COMMAND_GENERATED", "check_status"]), "PASS")
            self.assertEqual(str(validation.loc["NO_REPEAT_EVIDENCE_EXECUTION_GENERATED", "check_status"]), "PASS")
            self.assertEqual(str(validation.loc["NO_SHADOW_SIMULATION_GENERATED", "check_status"]), "PASS")
            self.assertEqual(str(validation.loc["NO_PRODUCTION_ORDERING_COMMAND_GENERATED", "check_status"]), "PASS")
            self.assertEqual(str(validation.loc["NO_STAGE12_MUTATION_COMMAND_GENERATED", "check_status"]), "PASS")


if __name__ == "__main__":
    unittest.main()