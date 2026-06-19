from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_single_promotion_isolated_smoke_test as module  # noqa: E402
from runtime.promotions.run_promotions_materialized_source_full_chain_isolated_dry_run_plan import (  # noqa: E402
    write_promotions_materialized_source_full_chain_isolated_dry_run_plan,
)
from tests.unit.test_promotions_materialized_source_full_chain_isolated_dry_run_plan import (  # noqa: E402
    PROMOTION_KEYS,
    _write_inputs,
)


SELECTED_PROMOTION_KEY = PROMOTION_KEYS[1]
RELAXED_PROMOTION_KEY = "772|2026-05-07|2026-05-20|Allocation Report - WK45-46 BABY YOU BOX"


def _plan_path(packet_root: Path) -> Path:
    return packet_root / module.FULL_CHAIN_DRY_RUN_PLAN_FOLDER_NAME / module.COMMAND_PLAN_FILE_NAME


def _read_plan(packet_root: Path) -> pd.DataFrame:
    return pd.read_csv(_plan_path(packet_root), keep_default_na=False)


def _write_plan(packet_root: Path, frame: pd.DataFrame) -> None:
    _plan_path(packet_root).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(_plan_path(packet_root), index=False)


def _write_full_chain_plan(packet_root: Path) -> None:
    write_promotions_materialized_source_full_chain_isolated_dry_run_plan(
        packet_root=packet_root,
        dry_run=True,
    )


class PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestTests(unittest.TestCase):
    def test_blocks_when_no_promotion_key_is_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=None,
            )

            self.assertEqual(result.smoke_test_status, module.SMOKE_TEST_BLOCKED_MISSING_PROMOTION_KEY)
            self.assertEqual(result.command_rows_found, 0)

    def test_relaxed_promotion_key_still_selects_unique_plan_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=RELAXED_PROMOTION_KEY,
                dry_run=True,
            )

            self.assertEqual(result.smoke_test_status, module.SMOKE_TEST_DRY_RUN_READY)
            self.assertEqual(result.command_rows_found, 15)
            self.assertEqual(result.commands_frame["promotion_key"].astype(str).nunique(), 1)

    def test_blocks_if_selected_promotion_has_fewer_or_more_than_15_stage_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            fewer = plan.loc[
                ~(
                    plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                    & plan["stage_number"].astype(int).eq(15)
                )
            ].reset_index(drop=True)
            _write_plan(packet_root, fewer)

            fewer_result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
            )

            self.assertEqual(fewer_result.smoke_test_status, module.SMOKE_TEST_BLOCKED_SHARED_ROOT_RISK)
            fewer_validation = fewer_result.validation_frame.set_index("check_name")
            self.assertEqual(int(fewer_validation.loc["FIFTEEN_COMMAND_ROWS_FOUND", "check_flag"]), 0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            duplicate = plan.loc[
                (plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY))
                & (plan["stage_number"].astype(int).eq(15))
            ].copy()
            duplicate.loc[:, "stage_name"] = duplicate["stage_name"].astype(str) + " duplicate"
            more = pd.concat([plan, duplicate], ignore_index=True)
            _write_plan(packet_root, more)

            more_result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
            )

            self.assertEqual(more_result.smoke_test_status, module.SMOKE_TEST_BLOCKED_SHARED_ROOT_RISK)
            more_validation = more_result.validation_frame.set_index("check_name")
            self.assertEqual(int(more_validation.loc["FIFTEEN_COMMAND_ROWS_FOUND", "check_flag"]), 0)

    @mock.patch.object(module, "_run_stage_command")
    def test_dry_run_does_not_execute_commands(self, run_mock: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                dry_run=True,
            )

            self.assertEqual(result.smoke_test_status, module.SMOKE_TEST_DRY_RUN_READY)
            run_mock.assert_not_called()
            self.assertTrue(
                result.stage_results_frame["status"].astype(str).eq(module.SMOKE_TEST_DRY_RUN_READY).all()
            )

    @mock.patch.object(module, "_run_stage_command")
    def test_execute_mode_runs_commands_in_strict_stage_order(self, run_mock: mock.Mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr="")
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                execute=True,
            )

            self.assertEqual(result.smoke_test_status, module.SMOKE_TEST_COMPLETED)
            self.assertEqual(
                result.stage_results_frame["stage_number"].astype(int).tolist(),
                list(range(1, 16)),
            )
            self.assertEqual(len(run_mock.call_args_list), 15)

    @mock.patch.object(module, "_run_stage_command")
    def test_stops_on_first_non_zero_stage_exit(self, run_mock: mock.Mock) -> None:
        run_mock.side_effect = [
            subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr=""),
            subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr=""),
            subprocess.CompletedProcess(args="", returncode=7, stdout="", stderr="boom"),
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                execute=True,
            )

            self.assertEqual(result.smoke_test_status, module.SMOKE_TEST_STAGE_FAILED)
            self.assertEqual(len(run_mock.call_args_list), 3)
            self.assertEqual(len(result.stage_results_frame.index), 3)
            self.assertEqual(int(result.stage_results_frame.iloc[-1]["exit_code"]), 7)

    def test_rejects_any_command_writing_to_shared_packet_root_stage_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(3)
            )
            shared_output = packet_root / module._stage_output_folder(3)
            plan.loc[mask, "output_root"] = str(shared_output)
            plan.loc[mask, "command"] = plan.loc[mask, "command"].astype(str).str.replace(
                plan.loc[mask, "output_root"].iloc[0],
                str(shared_output),
                regex=False,
            )
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
            )

            self.assertEqual(result.smoke_test_status, module.SMOKE_TEST_BLOCKED_SHARED_ROOT_RISK)
            self.assertEqual(result.shared_packet_root_write_risk_flag, 1)

    def test_rejects_any_command_missing_isolated_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(4)
            )
            plan.loc[mask, "output_root"] = ""
            plan.loc[mask, "command"] = "echo missing-output-root"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
            )

            self.assertEqual(result.smoke_test_status, module.SMOKE_TEST_BLOCKED_SHARED_ROOT_RISK)
            validation = result.validation_frame.set_index("check_name")
            self.assertEqual(int(validation.loc["ALL_STAGES_HAVE_ISOLATED_OUTPUT_ROOT", "check_flag"]), 0)

    def test_rejects_any_stage_2_through_15_command_missing_upstream_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(2)
            )
            stage_output = plan.loc[mask, "output_root"].iloc[0]
            plan.loc[mask, "upstream_root"] = ""
            plan.loc[mask, "command"] = f"echo missing-upstream --output-root {stage_output}"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
            )

            self.assertEqual(result.smoke_test_status, module.SMOKE_TEST_BLOCKED_SHARED_ROOT_RISK)
            validation = result.validation_frame.set_index("check_name")
            self.assertEqual(int(validation.loc["STAGES_2_TO_15_HAVE_UPSTREAM_ROOT", "check_flag"]), 0)

    @mock.patch.object(module, "_run_stage_command")
    def test_detects_source_packet_mutation_by_hash(self, run_mock: mock.Mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr="")
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            source_file = next(
                (packet_root / module.SOURCE_MATERIALIZED_FOLDER_NAME).rglob("promotion_source_rows.csv")
            )

            def _mutating_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                source_file.write_text("mutated\n", encoding="utf-8")
                return subprocess.CompletedProcess(args="", returncode=0, stdout="ok", stderr="")

            run_mock.side_effect = _mutating_run
            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                execute=True,
            )

            self.assertEqual(result.smoke_test_status, module.SMOKE_TEST_STAGE_FAILED)
            self.assertEqual(result.source_mutation_risk_flag, 1)
            self.assertEqual(
                int(result.stage_results_frame.iloc[0]["source_packet_mutation_detected_flag"]),
                1,
            )

    def test_produces_all_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)

            artifacts = module.write_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                dry_run=True,
            )

            self.assertTrue(Path(artifacts.commands_csv_path).exists())
            self.assertTrue(Path(artifacts.stage_results_csv_path).exists())
            self.assertTrue(Path(artifacts.validation_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())
            stage_results = pd.read_csv(artifacts.stage_results_csv_path, keep_default_na=False)
            self.assertEqual(stage_results.columns.tolist(), list(module.STAGE_RESULTS_COLUMNS))

    def test_does_not_run_training_recalibration_repeat_shadow_production_or_stage12_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                dry_run=True,
            )

            validation = result.validation_frame.set_index("check_name")
            self.assertEqual(int(validation.loc["NO_TRAINING_COMMAND", "check_flag"]), 1)
            self.assertEqual(int(validation.loc["NO_RECALIBRATION_COMMAND", "check_flag"]), 1)
            self.assertEqual(int(validation.loc["NO_REPEAT_EVIDENCE_EXECUTION_COMMAND", "check_flag"]), 1)
            self.assertEqual(int(validation.loc["NO_SHADOW_SIMULATION_COMMAND", "check_flag"]), 1)
            self.assertEqual(int(validation.loc["NO_PRODUCTION_ORDERING_COMMAND", "check_flag"]), 1)
            self.assertEqual(int(validation.loc["NO_STAGE12_MUTATION_COMMAND", "check_flag"]), 1)

    @mock.patch.object(module, "_run_stage_command")
    def test_audit_only_mode_does_not_execute_commands(self, run_mock: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            run_mock.assert_not_called()
            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_PASS)
            self.assertEqual(result.execution_allowed_flag, 0)

    def test_audit_passes_valid_generated_python_c_command_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_PASS)
            self.assertEqual(result.unsafe_command_count, 0)
            self.assertEqual(result.command_rows_found, 15)
            self.assertEqual(result.stages_planned, 15)

    def test_audit_blocks_missing_command_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            plan = plan.loc[
                ~(
                    plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                    & plan["stage_number"].astype(int).eq(15)
                )
            ].reset_index(drop=True)
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_MISSING_COMMANDS)

    def test_audit_blocks_bad_stage_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(2)
            )
            plan.loc[mask, "stage_number"] = 20
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_BAD_STAGE_ORDER)

    def test_audit_blocks_shared_packet_root_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(3)
            )
            shared_output = packet_root / module._stage_output_folder(3)
            plan.loc[mask, "output_root"] = str(shared_output)
            plan.loc[mask, "command"] = plan.loc[mask, "command"].astype(str).str.replace(
                "materialized_source_preview_join",
                str(shared_output),
                regex=False,
            )
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_SHARED_ROOT_RISK)

    def test_audit_blocks_missing_upstream_root_for_stages_2_to_15(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(2)
            )
            stage_output = plan.loc[mask, "output_root"].iloc[0]
            plan.loc[mask, "upstream_root"] = ""
            plan.loc[mask, "command"] = f".venv/bin/python -c 'import sys; sys.path.append(""src""); from runtime.promotions.run_promotions_materialized_source_join_spec_pack import main; raise SystemExit(main([""--packet-root"", ""tmp/last5_promotions_diagnostic_packets"", ""--promotion-key"", ""{SELECTED_PROMOTION_KEY}"", ""--output-root"", ""{stage_output}""]))'"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND)

    def test_audit_blocks_upstream_root_on_stage_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(1)
            )
            run_root = plan.loc[mask, "promotion_run_root"].iloc[0]
            stage_output = plan.loc[mask, "output_root"].iloc[0]
            plan.loc[mask, "upstream_root"] = run_root
            plan.loc[mask, "command"] = f".venv/bin/python -c 'import sys; sys.path.append(""src""); from runtime.promotions.run_promotions_materialized_source_join_key_validator import main; raise SystemExit(main([""--packet-root"", ""tmp/last5_promotions_diagnostic_packets"", ""--promotion-key"", ""{SELECTED_PROMOTION_KEY}"", ""--upstream-root"", ""{run_root}"", ""--output-root"", ""{stage_output}""]))'"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND)

    def test_audit_blocks_dangerous_shell_and(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(1)
            )
            plan.loc[mask, "command"] = plan.loc[mask, "command"].astype(str) + " && echo pwn"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND)

    def test_audit_blocks_dangerous_shell_backticks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(1)
            )
            plan.loc[mask, "command"] = plan.loc[mask, "command"].astype(str) + " `whoami`"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND)

    def test_audit_blocks_dangerous_shell_dollar_paren(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(1)
            )
            plan.loc[mask, "command"] = plan.loc[mask, "command"].astype(str) + " $(whoami)"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND)

    def test_audit_blocks_dangerous_shell_rm_rf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(1)
            )
            plan.loc[mask, "command"] = plan.loc[mask, "command"].astype(str) + " rm -rf /tmp/nope"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND)

    def test_audit_blocks_dangerous_shell_curl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(1)
            )
            plan.loc[mask, "command"] = plan.loc[mask, "command"].astype(str) + " curl https://example.com"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND)

    def test_audit_blocks_dangerous_shell_wget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(1)
            )
            plan.loc[mask, "command"] = plan.loc[mask, "command"].astype(str) + " wget https://example.com/file"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND)

    def test_audit_blocks_missing_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)
            plan = _read_plan(packet_root)
            mask = (
                plan["promotion_key"].astype(str).eq(SELECTED_PROMOTION_KEY)
                & plan["stage_number"].astype(int).eq(1)
            )
            plan.loc[mask, "runtime_file"] = "run_promotions_materialized_source_missing_runtime.py"
            _write_plan(packet_root, plan)

            result = module.build_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertEqual(result.audit_status, module.COMMAND_AUDIT_BLOCKED_MISSING_RUNTIME)

    def test_audit_writes_required_outputs_and_summary_with_zero_unsafe_for_valid_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            _write_full_chain_plan(packet_root)

            artifacts = module.write_promotions_materialized_source_single_promotion_isolated_smoke_test(
                packet_root=packet_root,
                promotion_key=SELECTED_PROMOTION_KEY,
                audit_only=True,
            )

            self.assertTrue(Path(artifacts.command_audit_csv_path).exists())
            self.assertTrue(Path(artifacts.command_audit_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.command_audit_memo_md_path).exists())
            summary = pd.read_csv(artifacts.command_audit_summary_csv_path, keep_default_na=False)
            summary_lookup = dict(zip(summary["metric_name"].astype(str), summary["metric_value"]))
            self.assertEqual(str(summary_lookup["UNSAFE_COMMAND_COUNT"]), "0")
            self.assertEqual(str(summary_lookup["AUDIT_STATUS"]), module.COMMAND_AUDIT_PASS)


if __name__ == "__main__":
    unittest.main()
