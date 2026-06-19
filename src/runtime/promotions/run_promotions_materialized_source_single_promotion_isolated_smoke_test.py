from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Sequence

import pandas as pd

from runtime.promotions.run_promotions_materialized_source_full_chain_isolated_dry_run_plan import (
    OUTPUT_FOLDER_NAME as FULL_CHAIN_DRY_RUN_PLAN_FOLDER_NAME,
)
from runtime.promotions.run_promotions_materialized_source_multi_promotion_reconstruction_queue import (
    OUTPUT_FOLDER_NAME as RECONSTRUCTION_QUEUE_FOLDER_NAME,
    SOURCE_MATERIALIZED_FOLDER_NAME,
    STAGE_SPECS,
)


OUTPUT_FOLDER_NAME = "materialized_source_single_promotion_isolated_smoke_test"
COMMAND_PLAN_FILE_NAME = "full_chain_isolated_dry_run_commands.csv"
QUEUE_ROWS_FILE_NAME = "multi_promotion_reconstruction_queue_rows.csv"
COMMANDS_OUTPUT_FILE_NAME = "single_promotion_isolated_smoke_test_commands.csv"
STAGE_RESULTS_FILE_NAME = "single_promotion_isolated_smoke_test_stage_results.csv"
VALIDATION_FILE_NAME = "single_promotion_isolated_smoke_test_validation.csv"
SUMMARY_FILE_NAME = "single_promotion_isolated_smoke_test_summary.csv"
MEMO_FILE_NAME = "single_promotion_isolated_smoke_test_memo.md"
COMMAND_AUDIT_FILE_NAME = "single_promotion_isolated_smoke_test_command_audit.csv"
COMMAND_AUDIT_SUMMARY_FILE_NAME = "single_promotion_isolated_smoke_test_command_audit_summary.csv"
COMMAND_AUDIT_MEMO_FILE_NAME = "single_promotion_isolated_smoke_test_command_audit_memo.md"

SMOKE_TEST_DRY_RUN_READY = "SMOKE_TEST_DRY_RUN_READY"
SMOKE_TEST_EXECUTION_READY = "SMOKE_TEST_EXECUTION_READY"
SMOKE_TEST_STAGE_COMPLETED = "SMOKE_TEST_STAGE_COMPLETED"
SMOKE_TEST_STAGE_FAILED = "SMOKE_TEST_STAGE_FAILED"
SMOKE_TEST_COMPLETED = "SMOKE_TEST_COMPLETED"
SMOKE_TEST_BLOCKED_MULTIPLE_PROMOTIONS = "SMOKE_TEST_BLOCKED_MULTIPLE_PROMOTIONS"
SMOKE_TEST_BLOCKED_ALREADY_COMPLETE = "SMOKE_TEST_BLOCKED_ALREADY_COMPLETE"
SMOKE_TEST_BLOCKED_SHARED_ROOT_RISK = "SMOKE_TEST_BLOCKED_SHARED_ROOT_RISK"
SMOKE_TEST_BLOCKED_MISSING_COMMAND_PLAN = "SMOKE_TEST_BLOCKED_MISSING_COMMAND_PLAN"
SMOKE_TEST_BLOCKED_MISSING_PROMOTION_KEY = "SMOKE_TEST_BLOCKED_MISSING_PROMOTION_KEY"

COMMAND_AUDIT_READY = "COMMAND_AUDIT_READY"
COMMAND_AUDIT_PASS = "COMMAND_AUDIT_PASS"
COMMAND_AUDIT_BLOCKED = "COMMAND_AUDIT_BLOCKED"
COMMAND_AUDIT_BLOCKED_MISSING_COMMANDS = "COMMAND_AUDIT_BLOCKED_MISSING_COMMANDS"
COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND = "COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND"
COMMAND_AUDIT_BLOCKED_SHARED_ROOT_RISK = "COMMAND_AUDIT_BLOCKED_SHARED_ROOT_RISK"
COMMAND_AUDIT_BLOCKED_MISSING_RUNTIME = "COMMAND_AUDIT_BLOCKED_MISSING_RUNTIME"
COMMAND_AUDIT_BLOCKED_BAD_STAGE_ORDER = "COMMAND_AUDIT_BLOCKED_BAD_STAGE_ORDER"

READY_RECOMMENDATION = (
    "Dry-run validation passed. Next step is to review the staged outputs before any explicit execute-mode smoke test."
)
EXECUTION_RECOMMENDATION = (
    "Single-promotion isolated smoke test completed. Review stage outputs and logs before any broader execution."
)
BLOCKED_RECOMMENDATION = (
    "Smoke test is blocked. Repair the command plan or selection guardrail before execution."
)
FAILED_RECOMMENDATION = (
    "Smoke test stopped on a failing stage or source mutation. Inspect stage logs before retrying."
)
AUDIT_READY_RECOMMENDATION = (
    "Command audit passed. Review the audit outputs before any explicit execute-mode smoke test."
)
AUDIT_BLOCKED_RECOMMENDATION = (
    "Command audit is blocked. Repair the unsafe or non-isolated command contract before any execution is allowed."
)

COMMANDS_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_slug",
    "stage_number",
    "stage_name",
    "runtime_file",
    "command",
    "packet_root",
    "promotion_run_root",
    "upstream_root",
    "output_root",
    "uses_upstream_root_flag",
    "uses_output_root_flag",
    "isolation_ready_flag",
    "execution_allowed_flag",
    "planner_only_flag",
)

STAGE_RESULTS_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_slug",
    "stage_number",
    "stage_name",
    "runtime_file",
    "command",
    "promotion_run_root",
    "upstream_root",
    "output_root",
    "started_at",
    "finished_at",
    "duration_seconds",
    "exit_code",
    "status",
    "stdout_path",
    "stderr_path",
    "shared_packet_root_write_detected_flag",
    "source_packet_mutation_detected_flag",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "check_name",
    "check_status",
    "check_flag",
    "details",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

COMMAND_AUDIT_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_slug",
    "stage_number",
    "stage_name",
    "runtime_file",
    "command",
    "promotion_run_root",
    "upstream_root",
    "output_root",
    "runtime_exists_flag",
    "packet_root_flag",
    "promotion_key_flag",
    "isolated_output_root_flag",
    "stage1_upstream_root_flag",
    "downstream_upstream_root_flag",
    "shared_packet_root_write_risk_flag",
    "output_root_under_run_root_flag",
    "upstream_root_under_run_root_flag",
    "dangerous_shell_fragment_flag",
    "forbidden_command_flag",
    "audit_status",
    "audit_details",
)

COMMAND_AUDIT_SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

FORBIDDEN_COMMAND_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("NO_TRAINING_COMMAND", ("training", "train")),
    ("NO_RECALIBRATION_COMMAND", ("recalibration", "recalibrate")),
    (
        "NO_REPEAT_EVIDENCE_EXECUTION_COMMAND",
        ("repeat_evidence_execution", "run_repeat_evidence_execution"),
    ),
    ("NO_SHADOW_SIMULATION_COMMAND", ("shadow", "simulation")),
    ("NO_PRODUCTION_ORDERING_COMMAND", ("production_order", "auto_order")),
    ("NO_STAGE12_MUTATION_COMMAND", ("stage12_mutation", "stage_12_change")),
)

DANGEROUS_SHELL_PATTERNS: tuple[str, ...] = (
    r"&&",
    r"`",
    r"\$\(",
    r"\brm\s+-rf\b",
    r"\bcurl\b",
    r"\bwget\b",
)

SHELL_MOVE_OR_COPY_PATTERN = r"(^|[;&|]\s*|\s)(mv|cp)\s+"


class PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestResult:
    smoke_test_status: str
    audit_status: str
    selected_promotion_key: str
    command_rows_found: int
    stages_planned: int
    execution_allowed_flag: int
    shared_packet_root_write_risk_flag: int
    source_mutation_risk_flag: int
    unsafe_command_count: int
    missing_runtime_count: int
    audit_frame: pd.DataFrame
    audit_summary_frame: pd.DataFrame
    audit_memo_markdown: str
    commands_frame: pd.DataFrame
    stage_results_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str
    recommendation: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestArtifacts:
    output_root: str
    commands_csv_path: str
    stage_results_csv_path: str
    validation_csv_path: str
    summary_csv_path: str
    memo_md_path: str
    command_audit_csv_path: str
    command_audit_summary_csv_path: str
    command_audit_memo_md_path: str
    smoke_test_status: str
    audit_status: str
    selected_promotion_key: str
    command_rows_found: int
    stages_planned: int
    execution_allowed_flag: int
    shared_packet_root_write_risk_flag: int
    source_mutation_risk_flag: int
    unsafe_command_count: int
    missing_runtime_count: int
    recommendation: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _to_int(value: object, *, default: int = 0) -> int:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return default
    return int(numeric)


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestError(
            f"CSV not found: {csv_path}"
        )
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestError(
            f"CSV is empty: {csv_path}"
        )
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestError(
            f"CSV is empty: {csv_path}"
        )
    return frame


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _validation_row(check_name: str, check_flag: int, details: str) -> dict[str, object]:
    return {
        "check_name": check_name,
        "check_status": "PASS" if int(check_flag) == 1 else "FAIL",
        "check_flag": int(check_flag),
        "details": details,
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _normalized_promotion_key(value: object) -> str:
    text = _normalize_text(value).lower()
    return "".join(character for character in text if character.isalnum())


def _command_plan_path(packet_root: Path) -> Path:
    return packet_root / FULL_CHAIN_DRY_RUN_PLAN_FOLDER_NAME / COMMAND_PLAN_FILE_NAME


def _queue_rows_path(packet_root: Path) -> Path:
    return packet_root / RECONSTRUCTION_QUEUE_FOLDER_NAME / QUEUE_ROWS_FILE_NAME


def _stage_output_folder(stage_number: int) -> str:
    for spec in STAGE_SPECS:
        if spec.stage_order == stage_number:
            return spec.output_folder_name
    raise PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestError(
        f"Unknown stage number: {stage_number}"
    )


def _source_tree_hashes(source_root: Path) -> dict[str, str]:
    if not source_root.exists():
        return {}
    hashes: dict[str, str] = {}
    for file_path in sorted(path for path in source_root.rglob("*") if path.is_file()):
        hashes[str(file_path.relative_to(source_root))] = hashlib.sha256(
            file_path.read_bytes()
        ).hexdigest()
    return hashes


def _contains_forbidden_terms(commands_frame: pd.DataFrame, terms: Sequence[str]) -> bool:
    if commands_frame.empty:
        return False
    haystack = "\n".join(commands_frame["command"].astype(str).tolist()).lower()
    return any(term.lower() in haystack for term in terms)


def _is_known_safe_generated_python_command_shape(command: str, runtime_file: str) -> bool:
    module_name = runtime_file.removesuffix(".py")
    return (
        command.strip().startswith(".venv/bin/python -c")
        and f"runtime.promotions.{module_name}" in command
        and "from runtime.promotions." in command
        and "raise SystemExit(main(" in command
    )


def _command_has_dangerous_fragment(
    *,
    command: str,
    runtime_file: str,
    known_shape_requirements_ok: bool,
) -> bool:
    if any(re.search(pattern, command) for pattern in DANGEROUS_SHELL_PATTERNS):
        return True
    if re.search(SHELL_MOVE_OR_COPY_PATTERN, command):
        return True
    if ";" in command:
        if not (
            _is_known_safe_generated_python_command_shape(command, runtime_file)
            and known_shape_requirements_ok
        ):
            return True
    return False


def _runtime_file_exists(runtime_file: str) -> bool:
    return (_repo_root() / "src" / "runtime" / "promotions" / runtime_file).exists()


def _path_is_under_root(path_text: str, root_text: str) -> bool:
    if not path_text or not root_text:
        return False
    try:
        Path(path_text).relative_to(Path(root_text))
    except ValueError:
        return False
    return True


def _promotion_queue_row(packet_root: Path, promotion_key: str) -> dict[str, object]:
    queue_frame = _read_csv(_queue_rows_path(packet_root), allow_empty=True)
    if queue_frame.empty or "promotion_key" not in queue_frame.columns:
        return {}
    matches = queue_frame.loc[queue_frame["promotion_key"].astype(str).eq(promotion_key)]
    if matches.empty:
        normalized_key = _normalized_promotion_key(promotion_key)
        if normalized_key:
            normalized = queue_frame["promotion_key"].astype(str).map(_normalized_promotion_key)
            matches = queue_frame.loc[normalized.eq(normalized_key)]
    if matches.empty:
        return {}
    if matches["promotion_key"].astype(str).nunique() != 1:
        return {}
    return matches.iloc[0].to_dict()


def _matching_command_rows(commands_frame: pd.DataFrame, promotion_key: str) -> pd.DataFrame:
    exact = commands_frame.loc[
        commands_frame["promotion_key"].astype(str).eq(promotion_key)
    ].copy()
    if not exact.empty:
        return exact
    normalized_key = _normalized_promotion_key(promotion_key)
    if not normalized_key:
        return pd.DataFrame(columns=commands_frame.columns)
    normalized = commands_frame["promotion_key"].astype(str).map(_normalized_promotion_key)
    return commands_frame.loc[normalized.eq(normalized_key)].copy()


def _command_writes_to_shared_root(packet_root: Path, row: dict[str, object]) -> bool:
    stage_number = _to_int(row.get("stage_number"))
    if stage_number not in {spec.stage_order for spec in STAGE_SPECS}:
        return False
    shared_output_root = packet_root / _stage_output_folder(stage_number)
    output_root = _normalize_text(row.get("output_root"))
    command = _normalize_text(row.get("command"))
    return output_root == str(shared_output_root) or str(shared_output_root) in command


def _output_root_is_isolated(packet_root: Path, row: dict[str, object]) -> bool:
    output_root = _normalize_text(row.get("output_root"))
    promotion_run_root = _normalize_text(row.get("promotion_run_root"))
    if not output_root or not promotion_run_root:
        return False
    output_path = Path(output_root)
    promotion_path = Path(promotion_run_root)
    try:
        output_path.relative_to(promotion_path)
    except ValueError:
        return False
    return not _command_writes_to_shared_root(packet_root, row)


def _command_audit_status_from_row(row: dict[str, object]) -> str:
    if _to_int(row.get("shared_packet_root_write_risk_flag")) == 1:
        return COMMAND_AUDIT_BLOCKED_SHARED_ROOT_RISK
    if _to_int(row.get("runtime_exists_flag")) == 0:
        return COMMAND_AUDIT_BLOCKED_MISSING_RUNTIME
    if _to_int(row.get("dangerous_shell_fragment_flag")) == 1 or _to_int(row.get("forbidden_command_flag")) == 1:
        return COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND
    if any(
        _to_int(row.get(flag_name)) == 0
        for flag_name in (
            "packet_root_flag",
            "promotion_key_flag",
            "isolated_output_root_flag",
            "stage1_upstream_root_flag",
            "downstream_upstream_root_flag",
            "output_root_under_run_root_flag",
            "upstream_root_under_run_root_flag",
        )
    ):
        return COMMAND_AUDIT_BLOCKED
    return COMMAND_AUDIT_PASS


def _command_audit_rows(packet_root: Path, selected_commands: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in selected_commands.to_dict("records"):
        stage_number = _to_int(row.get("stage_number"))
        command = _normalize_text(row.get("command"))
        runtime_file = _normalize_text(row.get("runtime_file"))
        promotion_run_root = _normalize_text(row.get("promotion_run_root"))
        upstream_root = _normalize_text(row.get("upstream_root"))
        runtime_exists_flag = int(_runtime_file_exists(runtime_file))
        packet_root_flag = int("--packet-root" in command)
        promotion_key_flag = int("--promotion-key" in command)
        isolated_output_root_flag = int(_output_root_is_isolated(packet_root, row) and "--output-root" in command)
        stage1_upstream_root_flag = int(stage_number != 1 or (not upstream_root and "--upstream-root" not in command))
        downstream_upstream_root_flag = int(
            stage_number == 1 or (bool(upstream_root) and "--upstream-root" in command)
        )
        shared_packet_root_write_risk_flag = int(_command_writes_to_shared_root(packet_root, row))
        output_root_under_run_root_flag = int(
            _path_is_under_root(_normalize_text(row.get("output_root")), promotion_run_root)
        )
        upstream_root_under_run_root_flag = int(
            stage_number == 1 or _path_is_under_root(upstream_root, promotion_run_root)
        )
        known_shape_requirements_ok = int(
            packet_root_flag == 1
            and promotion_key_flag == 1
            and isolated_output_root_flag == 1
            and stage1_upstream_root_flag == 1
            and downstream_upstream_root_flag == 1
            and output_root_under_run_root_flag == 1
            and upstream_root_under_run_root_flag == 1
        )
        dangerous_shell_fragment_flag = int(
            _command_has_dangerous_fragment(
                command=command,
                runtime_file=runtime_file,
                known_shape_requirements_ok=bool(known_shape_requirements_ok),
            )
        )
        forbidden_command_flag = int(
            any(
                _contains_forbidden_terms(pd.DataFrame([row]), terms)
                for _, terms in FORBIDDEN_COMMAND_TERMS
            )
        )
        audit_details = []
        if packet_root_flag == 0:
            audit_details.append("missing --packet-root")
        if promotion_key_flag == 0:
            audit_details.append("missing --promotion-key")
        if isolated_output_root_flag == 0:
            audit_details.append("missing isolated --output-root")
        if stage1_upstream_root_flag == 0:
            audit_details.append("stage 1 has upstream-root")
        if downstream_upstream_root_flag == 0:
            audit_details.append("missing downstream upstream-root")
        if shared_packet_root_write_risk_flag == 1:
            audit_details.append("shared packet-root write risk")
        if dangerous_shell_fragment_flag == 1:
            audit_details.append("dangerous shell fragment")
        if forbidden_command_flag == 1:
            audit_details.append("forbidden command category")
        if runtime_exists_flag == 0:
            audit_details.append("missing runtime file")
        if output_root_under_run_root_flag == 0:
            audit_details.append("output root outside run root")
        if upstream_root_under_run_root_flag == 0:
            audit_details.append("upstream root outside run root")
        audit_row = {
            "promotion_key": _normalize_text(row.get("promotion_key")),
            "promotion_slug": _normalize_text(row.get("promotion_slug")),
            "stage_number": stage_number,
            "stage_name": _normalize_text(row.get("stage_name")),
            "runtime_file": runtime_file,
            "command": command,
            "promotion_run_root": promotion_run_root,
            "upstream_root": upstream_root,
            "output_root": _normalize_text(row.get("output_root")),
            "runtime_exists_flag": runtime_exists_flag,
            "packet_root_flag": packet_root_flag,
            "promotion_key_flag": promotion_key_flag,
            "isolated_output_root_flag": isolated_output_root_flag,
            "stage1_upstream_root_flag": stage1_upstream_root_flag,
            "downstream_upstream_root_flag": downstream_upstream_root_flag,
            "shared_packet_root_write_risk_flag": shared_packet_root_write_risk_flag,
            "output_root_under_run_root_flag": output_root_under_run_root_flag,
            "upstream_root_under_run_root_flag": upstream_root_under_run_root_flag,
            "dangerous_shell_fragment_flag": dangerous_shell_fragment_flag,
            "forbidden_command_flag": forbidden_command_flag,
            "audit_status": COMMAND_AUDIT_PASS,
            "audit_details": "; ".join(audit_details),
        }
        audit_row["audit_status"] = _command_audit_status_from_row(audit_row)
        rows.append(audit_row)
    return rows


def _command_audit_summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return _summary_row(metric_name, metric_value, notes)


def _command_audit_summary(
    *,
    audit_status: str,
    selected_promotion_key: str,
    command_rows_audited: int,
    stages_audited: int,
    unsafe_command_count: int,
    shared_root_risk_count: int,
    missing_runtime_count: int,
    execution_allowed_flag: int,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _command_audit_summary_row("AUDIT_STATUS", audit_status, "Overall pre-execution command audit status."),
            _command_audit_summary_row("SELECTED_PROMOTION_KEY", selected_promotion_key, "Promotion key audited."),
            _command_audit_summary_row("COMMAND_ROWS_AUDITED", command_rows_audited, "Command rows audited for the selected promotion."),
            _command_audit_summary_row("STAGES_AUDITED", stages_audited, "Stage count audited for the selected promotion."),
            _command_audit_summary_row("UNSAFE_COMMAND_COUNT", unsafe_command_count, "Commands blocked for dangerous shell fragments or forbidden command categories."),
            _command_audit_summary_row("SHARED_ROOT_RISK_COUNT", shared_root_risk_count, "Commands blocked for shared packet-root output risk."),
            _command_audit_summary_row("MISSING_RUNTIME_COUNT", missing_runtime_count, "Commands referencing missing runtime files."),
            _command_audit_summary_row("EXECUTION_ALLOWED", execution_allowed_flag, "Execution remains blocked until audit and smoke validations pass with explicit --execute."),
        ],
        columns=COMMAND_AUDIT_SUMMARY_COLUMNS,
    )


def _command_audit_memo_markdown(
    *,
    audit_status: str,
    selected_promotion_key: str,
    command_rows_audited: int,
    stages_audited: int,
    unsafe_command_count: int,
    shared_root_risk_count: int,
    missing_runtime_count: int,
    execution_allowed_flag: int,
    recommendation: str,
) -> str:
    return "\n".join(
        [
            "# Single-Promotion Smoke Test Command Audit",
            "",
            "This is a pre-execution audit only. It does not execute any stage command.",
            "Source-materialised input folders remain read-only by contract.",
            "",
            f"Audit status: {audit_status}",
            f"Selected promotion key: {selected_promotion_key}",
            f"Command rows audited: {command_rows_audited}",
            f"Stages audited: {stages_audited}",
            f"Unsafe command count: {unsafe_command_count}",
            f"Shared-root risk count: {shared_root_risk_count}",
            f"Missing runtime count: {missing_runtime_count}",
            f"Execution allowed: {execution_allowed_flag}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()


def _build_command_audit(
    *,
    packet_root: Path,
    selected_commands: pd.DataFrame,
    selected_promotion_key: str,
    audit_only: bool,
) -> tuple[str, pd.DataFrame, pd.DataFrame, str, int, int, int, list[dict[str, object]]]:
    audit_rows = _command_audit_rows(packet_root, selected_commands)
    stage_numbers = selected_commands["stage_number"].map(_to_int).tolist() if not selected_commands.empty else []
    strict_stage_order_flag = int(stage_numbers == [spec.stage_order for spec in STAGE_SPECS])
    command_rows_found = len(selected_commands.index)
    command_rows_found_flag = int(command_rows_found == len(STAGE_SPECS))
    unsafe_command_count = sum(
        int(row["dangerous_shell_fragment_flag"] == 1 or row["forbidden_command_flag"] == 1)
        for row in audit_rows
    )
    shared_root_risk_count = sum(int(row["shared_packet_root_write_risk_flag"] == 1) for row in audit_rows)
    missing_runtime_count = sum(int(row["runtime_exists_flag"] == 0) for row in audit_rows)
    row_failures = any(row["audit_status"] != COMMAND_AUDIT_PASS for row in audit_rows)
    if command_rows_found_flag == 0:
        audit_status = COMMAND_AUDIT_BLOCKED_MISSING_COMMANDS
    elif strict_stage_order_flag == 0:
        audit_status = COMMAND_AUDIT_BLOCKED_BAD_STAGE_ORDER
    elif shared_root_risk_count > 0:
        audit_status = COMMAND_AUDIT_BLOCKED_SHARED_ROOT_RISK
    elif missing_runtime_count > 0:
        audit_status = COMMAND_AUDIT_BLOCKED_MISSING_RUNTIME
    elif unsafe_command_count > 0:
        audit_status = COMMAND_AUDIT_BLOCKED_UNSAFE_COMMAND
    elif row_failures:
        audit_status = COMMAND_AUDIT_BLOCKED
    else:
        audit_status = COMMAND_AUDIT_PASS if audit_only else COMMAND_AUDIT_READY
    audit_summary_frame = _command_audit_summary(
        audit_status=audit_status,
        selected_promotion_key=selected_promotion_key,
        command_rows_audited=command_rows_found,
        stages_audited=command_rows_found,
        unsafe_command_count=unsafe_command_count,
        shared_root_risk_count=shared_root_risk_count,
        missing_runtime_count=missing_runtime_count,
        execution_allowed_flag=0,
    )
    recommendation = AUDIT_READY_RECOMMENDATION if audit_status in {COMMAND_AUDIT_READY, COMMAND_AUDIT_PASS} else AUDIT_BLOCKED_RECOMMENDATION
    audit_memo_markdown = _command_audit_memo_markdown(
        audit_status=audit_status,
        selected_promotion_key=selected_promotion_key,
        command_rows_audited=command_rows_found,
        stages_audited=command_rows_found,
        unsafe_command_count=unsafe_command_count,
        shared_root_risk_count=shared_root_risk_count,
        missing_runtime_count=missing_runtime_count,
        execution_allowed_flag=0,
        recommendation=recommendation,
    )
    validation_rows = [
        _validation_row("AUDIT_EXACTLY_15_COMMANDS_FOUND", command_rows_found_flag, f"command_rows_found={command_rows_found}"),
        _validation_row("AUDIT_STAGES_ORDERED_1_THROUGH_15", strict_stage_order_flag, f"stage_numbers={stage_numbers}"),
        _validation_row("AUDIT_SOURCE_MATERIALISED_INPUTS_READ_ONLY_BY_CONTRACT", 1, "Source-materialised inputs are treated as read-only contract inputs."),
    ]
    return (
        audit_status,
        pd.DataFrame(audit_rows, columns=COMMAND_AUDIT_COLUMNS),
        audit_summary_frame,
        audit_memo_markdown,
        unsafe_command_count,
        shared_root_risk_count,
        missing_runtime_count,
        validation_rows,
    )


def _selected_commands_frame(
    packet_root: Path,
    promotion_key: str | None,
    allow_complete: bool,
) -> tuple[str, pd.DataFrame]:
    if not _normalize_text(promotion_key):
        return SMOKE_TEST_BLOCKED_MISSING_PROMOTION_KEY, pd.DataFrame(columns=COMMANDS_COLUMNS)
    command_plan_path = _command_plan_path(packet_root)
    if not command_plan_path.exists():
        return SMOKE_TEST_BLOCKED_MISSING_COMMAND_PLAN, pd.DataFrame(columns=COMMANDS_COLUMNS)
    commands_frame = _read_csv(command_plan_path)
    selected = _matching_command_rows(commands_frame, str(promotion_key))
    queue_row = _promotion_queue_row(packet_root, str(promotion_key))
    if selected.empty:
        if _to_int(queue_row.get("already_complete_flag"), default=0) == 1 and not allow_complete:
            return SMOKE_TEST_BLOCKED_ALREADY_COMPLETE, pd.DataFrame(columns=COMMANDS_COLUMNS)
        return SMOKE_TEST_BLOCKED_MISSING_COMMAND_PLAN, pd.DataFrame(columns=COMMANDS_COLUMNS)
    if selected["promotion_key"].astype(str).nunique() != 1:
        return SMOKE_TEST_BLOCKED_MULTIPLE_PROMOTIONS, pd.DataFrame(columns=COMMANDS_COLUMNS)
    if _to_int(queue_row.get("already_complete_flag"), default=0) == 1 and not allow_complete:
        return SMOKE_TEST_BLOCKED_ALREADY_COMPLETE, pd.DataFrame(columns=COMMANDS_COLUMNS)
    selected = selected.sort_values(
        by=["stage_number", "stage_name"],
        ascending=[True, True],
        kind="stable",
    ).reset_index(drop=True)
    return "", selected.reindex(columns=COMMANDS_COLUMNS)


def _validate_selected_commands(
    packet_root: Path,
    selected_commands: pd.DataFrame,
    *,
    execute: bool,
) -> tuple[str, list[dict[str, object]], int, int]:
    command_rows_found = len(selected_commands.index)
    stage_numbers = selected_commands["stage_number"].map(_to_int).tolist() if not selected_commands.empty else []
    expected_stage_numbers = [spec.stage_order for spec in STAGE_SPECS]
    stage1_rows = selected_commands.loc[selected_commands["stage_number"].map(_to_int).eq(1)]
    downstream_rows = selected_commands.loc[selected_commands["stage_number"].map(_to_int).gt(1)]
    shared_packet_root_write_risk_flag = int(
        any(
            _command_writes_to_shared_root(packet_root, row)
            for row in selected_commands.to_dict("records")
        )
    )

    validation_rows = [
        _validation_row(
            "EXACTLY_ONE_PROMOTION_SELECTED",
            int(
                not selected_commands.empty
                and selected_commands["promotion_key"].astype(str).nunique() == 1
            ),
            f"selected_promotions={selected_commands['promotion_key'].astype(str).nunique() if not selected_commands.empty else 0}",
        ),
        _validation_row(
            "FIFTEEN_COMMAND_ROWS_FOUND",
            int(command_rows_found == len(STAGE_SPECS)),
            f"command_rows_found={command_rows_found}",
        ),
        _validation_row(
            "STAGES_ORDERED_1_THROUGH_15",
            int(stage_numbers == expected_stage_numbers),
            f"stage_numbers={stage_numbers}",
        ),
        _validation_row(
            "STAGE1_HAS_NO_UPSTREAM_ROOT",
            int(
                len(stage1_rows.index) == 1
                and stage1_rows["upstream_root"].astype(str).eq("").all()
                and not stage1_rows["command"].astype(str).str.contains("--upstream-root", regex=False).any()
            ),
            "Stage 1 must omit --upstream-root.",
        ),
        _validation_row(
            "STAGES_2_TO_15_HAVE_UPSTREAM_ROOT",
            int(
                len(downstream_rows.index) == len(STAGE_SPECS) - 1
                and downstream_rows["upstream_root"].astype(str).ne("").all()
                and downstream_rows["command"].astype(str).str.contains("--upstream-root", regex=False).all()
            ),
            "Stages 2 through 15 must include --upstream-root.",
        ),
        _validation_row(
            "ALL_STAGES_HAVE_ISOLATED_OUTPUT_ROOT",
            int(
                not selected_commands.empty
                and all(
                    _output_root_is_isolated(packet_root, row)
                    and "--output-root" in _normalize_text(row.get("command"))
                    for row in selected_commands.to_dict("records")
                )
            ),
            "Every stage must write to an isolated promotion output root.",
        ),
        _validation_row(
            "NO_SHARED_PACKET_ROOT_STAGE_WRITES",
            int(shared_packet_root_write_risk_flag == 0),
            "No command may write to a shared packet-root stage folder.",
        ),
    ]
    for check_name, terms in FORBIDDEN_COMMAND_TERMS:
        validation_rows.append(
            _validation_row(
                check_name,
                int(not _contains_forbidden_terms(selected_commands, terms)),
                f"forbidden_terms={','.join(terms)}",
            )
        )
    preflight_passed = int(all(row["check_flag"] == 1 for row in validation_rows))
    execution_allowed_flag = int(execute and preflight_passed == 1)
    validation_rows.append(
        _validation_row(
            "EXECUTE_RUNS_EXACTLY_ONE_PROMOTION",
            int((not execute) or selected_commands["promotion_key"].astype(str).nunique() == 1),
            f"execute_requested={int(execute)}",
        )
    )
    if preflight_passed == 0:
        return (
            SMOKE_TEST_BLOCKED_SHARED_ROOT_RISK,
            validation_rows,
            execution_allowed_flag,
            shared_packet_root_write_risk_flag,
        )
    return "", validation_rows, execution_allowed_flag, shared_packet_root_write_risk_flag


def _stage_log_paths(output_root: Path, promotion_slug: str, stage_number: int) -> tuple[Path, Path]:
    stdout_path = output_root / "logs" / promotion_slug / f"stage_{stage_number:02d}.stdout.txt"
    stderr_path = output_root / "logs" / promotion_slug / f"stage_{stage_number:02d}.stderr.txt"
    return stdout_path, stderr_path


def _planned_stage_result_rows(commands_frame: pd.DataFrame, status: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in commands_frame.to_dict("records"):
        rows.append(
            {
                "promotion_key": _normalize_text(row.get("promotion_key")),
                "promotion_slug": _normalize_text(row.get("promotion_slug")),
                "stage_number": _to_int(row.get("stage_number")),
                "stage_name": _normalize_text(row.get("stage_name")),
                "runtime_file": _normalize_text(row.get("runtime_file")),
                "command": _normalize_text(row.get("command")),
                "promotion_run_root": _normalize_text(row.get("promotion_run_root")),
                "upstream_root": _normalize_text(row.get("upstream_root")),
                "output_root": _normalize_text(row.get("output_root")),
                "started_at": "",
                "finished_at": "",
                "duration_seconds": 0.0,
                "exit_code": "",
                "status": status,
                "stdout_path": "",
                "stderr_path": "",
                "shared_packet_root_write_detected_flag": 0,
                "source_packet_mutation_detected_flag": 0,
            }
        )
    return rows


def _run_stage_command(command: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        executable=shutil.which("zsh") or "/bin/zsh",
        capture_output=True,
        text=True,
        check=False,
    )


def _execute_commands(
    *,
    packet_root: Path,
    output_root: Path,
    commands_frame: pd.DataFrame,
    clean_run_root: bool,
) -> tuple[list[dict[str, object]], int, int]:
    repo_root = _repo_root()
    source_root = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME
    source_hashes_before = _source_tree_hashes(source_root)
    stage_result_rows: list[dict[str, object]] = []
    source_mutation_risk_flag = 0
    if clean_run_root and not commands_frame.empty:
        promotion_run_root = Path(_normalize_text(commands_frame.iloc[0].get("promotion_run_root")))
        if promotion_run_root.exists():
            shutil.rmtree(promotion_run_root)
    for row in commands_frame.to_dict("records"):
        stage_number = _to_int(row.get("stage_number"))
        promotion_slug = _normalize_text(row.get("promotion_slug"))
        stdout_path, stderr_path = _stage_log_paths(output_root, promotion_slug, stage_number)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc).isoformat()
        started_clock = time.monotonic()
        completed = _run_stage_command(_normalize_text(row.get("command")), cwd=repo_root)
        finished_at = datetime.now(timezone.utc).isoformat()
        duration_seconds = time.monotonic() - started_clock
        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")
        source_hashes_after = _source_tree_hashes(source_root)
        stage_source_mutation_flag = int(source_hashes_before != source_hashes_after)
        if stage_source_mutation_flag == 1:
            source_mutation_risk_flag = 1
        exit_code = int(completed.returncode)
        failed = int(exit_code != 0 or stage_source_mutation_flag == 1)
        stage_result_rows.append(
            {
                "promotion_key": _normalize_text(row.get("promotion_key")),
                "promotion_slug": promotion_slug,
                "stage_number": stage_number,
                "stage_name": _normalize_text(row.get("stage_name")),
                "runtime_file": _normalize_text(row.get("runtime_file")),
                "command": _normalize_text(row.get("command")),
                "promotion_run_root": _normalize_text(row.get("promotion_run_root")),
                "upstream_root": _normalize_text(row.get("upstream_root")),
                "output_root": _normalize_text(row.get("output_root")),
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_seconds": round(duration_seconds, 6),
                "exit_code": exit_code,
                "status": SMOKE_TEST_STAGE_FAILED if failed else SMOKE_TEST_STAGE_COMPLETED,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "shared_packet_root_write_detected_flag": int(
                    _command_writes_to_shared_root(packet_root, row)
                ),
                "source_packet_mutation_detected_flag": stage_source_mutation_flag,
            }
        )
        if failed:
            return stage_result_rows, 1, source_mutation_risk_flag
    return stage_result_rows, 0, source_mutation_risk_flag


def _recommendation_for_status(status: str) -> str:
    if status == SMOKE_TEST_DRY_RUN_READY:
        return READY_RECOMMENDATION
    if status == SMOKE_TEST_COMPLETED:
        return EXECUTION_RECOMMENDATION
    if status == SMOKE_TEST_STAGE_FAILED:
        return FAILED_RECOMMENDATION
    return BLOCKED_RECOMMENDATION


def _memo_markdown(
    *,
    status: str,
    promotion_key: str,
    command_rows_found: int,
    stages_planned: int,
    execution_allowed_flag: int,
    shared_packet_root_write_risk_flag: int,
    source_mutation_risk_flag: int,
    recommendation: str,
) -> str:
    return "\n".join(
        [
            "# Single-Promotion Isolated Smoke Test",
            "",
            "This is a controlled single-promotion isolated smoke-test runner for the 15-stage promotion reconstruction chain.",
            "This does not start training.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "This does not promote auto-ordering.",
            "This does not promote shadow rules.",
            "This does not run recalibration.",
            "This does not run shadow-vs-baseline simulation.",
            "This does not run repeat-evidence execution.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "This does not run multi-promotion execution.",
            "",
            f"Smoke-test status: {status}",
            f"Selected promotion key: {promotion_key}",
            f"Command rows found: {command_rows_found}",
            f"Stages planned: {stages_planned}",
            f"Execution allowed: {execution_allowed_flag}",
            f"Shared packet-root write risk: {shared_packet_root_write_risk_flag}",
            f"Source mutation risk: {source_mutation_risk_flag}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()


def build_promotions_materialized_source_single_promotion_isolated_smoke_test(
    *,
    packet_root: str | Path,
    promotion_key: str | None,
    dry_run: bool = True,
    execute: bool = False,
    audit_only: bool = False,
    stop_after_stage: int | None = None,
    clean_run_root: bool = False,
    allow_complete: bool = False,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestResult:
    if execute:
        dry_run = False
    if audit_only:
        execute = False
        dry_run = True
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME

    selection_status, selected_commands_all = _selected_commands_frame(
        packet_root_path,
        promotion_key,
        allow_complete,
    )
    command_rows_found = len(selected_commands_all.index)
    selected_promotion_key = _normalize_text(promotion_key)
    stages_planned = command_rows_found
    execution_allowed_flag = 0
    shared_packet_root_write_risk_flag = 0
    source_mutation_risk_flag = 0
    unsafe_command_count = 0
    missing_runtime_count = 0
    validation_rows: list[dict[str, object]] = []
    stage_result_rows: list[dict[str, object]] = []
    audit_status = COMMAND_AUDIT_BLOCKED_MISSING_COMMANDS if selection_status else COMMAND_AUDIT_READY
    audit_frame = pd.DataFrame(columns=COMMAND_AUDIT_COLUMNS)
    audit_summary_frame = pd.DataFrame(columns=COMMAND_AUDIT_SUMMARY_COLUMNS)
    audit_memo_markdown = ""

    selected_commands = selected_commands_all.copy()
    if stop_after_stage is not None and not selected_commands.empty:
        selected_commands = selected_commands.loc[
            selected_commands["stage_number"].map(_to_int).le(stop_after_stage)
        ].reset_index(drop=True)
        stages_planned = len(selected_commands.index)

    smoke_test_status = selection_status
    if not smoke_test_status:
        (
            audit_status,
            audit_frame,
            audit_summary_frame,
            audit_memo_markdown,
            unsafe_command_count,
            shared_root_risk_flag_count,
            missing_runtime_count,
            audit_validation_rows,
        ) = _build_command_audit(
            packet_root=packet_root_path,
            selected_commands=selected_commands_all,
            selected_promotion_key=selected_promotion_key,
            audit_only=audit_only,
        )
        (
            smoke_test_status,
            validation_rows,
            execution_allowed_flag,
            shared_packet_root_write_risk_flag,
        ) = _validate_selected_commands(
            packet_root_path,
            selected_commands_all,
            execute=execute and audit_status in {COMMAND_AUDIT_READY, COMMAND_AUDIT_PASS},
        )
        shared_packet_root_write_risk_flag = max(
            shared_packet_root_write_risk_flag,
            shared_root_risk_flag_count,
        )
        validation_rows = [*audit_validation_rows, *validation_rows]
    else:
        validation_rows.append(
            _validation_row(
                "PRECONDITION_BLOCKED",
                0,
                f"smoke_test_status={smoke_test_status}",
            )
        )
        audit_status = COMMAND_AUDIT_BLOCKED_MISSING_COMMANDS if smoke_test_status == SMOKE_TEST_BLOCKED_MISSING_COMMAND_PLAN else COMMAND_AUDIT_BLOCKED
        audit_summary_frame = _command_audit_summary(
            audit_status=audit_status,
            selected_promotion_key=selected_promotion_key,
            command_rows_audited=command_rows_found,
            stages_audited=command_rows_found,
            unsafe_command_count=0,
            shared_root_risk_count=0,
            missing_runtime_count=0,
            execution_allowed_flag=0,
        )
        audit_memo_markdown = _command_audit_memo_markdown(
            audit_status=audit_status,
            selected_promotion_key=selected_promotion_key,
            command_rows_audited=command_rows_found,
            stages_audited=command_rows_found,
            unsafe_command_count=0,
            shared_root_risk_count=0,
            missing_runtime_count=0,
            execution_allowed_flag=0,
            recommendation=AUDIT_BLOCKED_RECOMMENDATION,
        )

    if audit_only:
        smoke_test_status = SMOKE_TEST_DRY_RUN_READY if audit_status in {COMMAND_AUDIT_READY, COMMAND_AUDIT_PASS} else smoke_test_status
        stage_result_rows = _planned_stage_result_rows(selected_commands, COMMAND_AUDIT_READY if audit_status in {COMMAND_AUDIT_READY, COMMAND_AUDIT_PASS} else audit_status)
    elif smoke_test_status:
        stage_result_rows = _planned_stage_result_rows(selected_commands, smoke_test_status)
    elif dry_run or not execute:
        smoke_test_status = SMOKE_TEST_DRY_RUN_READY
        stage_result_rows = _planned_stage_result_rows(selected_commands, SMOKE_TEST_DRY_RUN_READY)
    else:
        validation_rows.append(
            _validation_row(
                "EXECUTION_REQUEST_ACCEPTED",
                1,
                f"smoke_test_status={SMOKE_TEST_EXECUTION_READY}",
            )
        )
        (
            stage_result_rows,
            execution_failed_flag,
            source_mutation_risk_flag,
        ) = _execute_commands(
            packet_root=packet_root_path,
            output_root=output_root_path,
            commands_frame=selected_commands,
            clean_run_root=clean_run_root,
        )
        smoke_test_status = (
            SMOKE_TEST_STAGE_FAILED if execution_failed_flag == 1 else SMOKE_TEST_COMPLETED
        )

    validation_rows.append(
        _validation_row(
            "SOURCE_MATERIALISED_HASHES_MATCH",
            int(source_mutation_risk_flag == 0),
            f"source_mutation_risk_flag={source_mutation_risk_flag}",
        )
    )
    validation_rows.append(
        _validation_row(
            "DRY_RUN_DOES_NOT_EXECUTE_COMMANDS",
            int(audit_only or dry_run or not execute),
            f"dry_run={int(audit_only or dry_run or not execute)}",
        )
    )

    commands_frame = selected_commands.reindex(columns=COMMANDS_COLUMNS)
    stage_results_frame = pd.DataFrame(stage_result_rows, columns=STAGE_RESULTS_COLUMNS)
    validation_frame = pd.DataFrame(validation_rows, columns=VALIDATION_COLUMNS)
    recommendation = (
        AUDIT_READY_RECOMMENDATION if audit_only and audit_status in {COMMAND_AUDIT_READY, COMMAND_AUDIT_PASS}
        else AUDIT_BLOCKED_RECOMMENDATION if audit_only
        else _recommendation_for_status(smoke_test_status)
    )
    summary_frame = pd.DataFrame(
        [
            _summary_row(
                "SMOKE_TEST_STATUS",
                smoke_test_status,
                "Overall single-promotion isolated smoke-test status.",
            ),
            _summary_row(
                "SELECTED_PROMOTION_KEY",
                selected_promotion_key,
                "Selected promotion key for this smoke test.",
            ),
            _summary_row(
                "COMMAND_ROWS_FOUND",
                command_rows_found,
                "Command-plan rows found for the selected promotion before any stop-after-stage limit.",
            ),
            _summary_row(
                "STAGES_PLANNED",
                stages_planned,
                "Stages planned for this smoke test after any stop-after-stage limit.",
            ),
            _summary_row(
                "EXECUTION_ALLOWED",
                execution_allowed_flag,
                "Execution only occurs when --execute is explicitly supplied and validations pass.",
            ),
            _summary_row(
                "SHARED_PACKET_ROOT_WRITE_RISK",
                shared_packet_root_write_risk_flag,
                "Whether any selected command writes to a shared packet-root stage folder.",
            ),
            _summary_row(
                "SOURCE_MUTATION_RISK",
                source_mutation_risk_flag,
                "Whether source-materialised inputs changed during execution.",
            ),
            _summary_row(
                "AUDIT_STATUS",
                audit_status,
                "Overall pre-execution command audit status.",
            ),
            _summary_row(
                "UNSAFE_COMMAND_COUNT",
                unsafe_command_count,
                "Commands blocked for dangerous shell fragments or forbidden command categories.",
            ),
            _summary_row(
                "MISSING_RUNTIME_COUNT",
                missing_runtime_count,
                "Commands referencing runtime files that do not exist.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )
    memo_markdown = _memo_markdown(
        status=smoke_test_status,
        promotion_key=selected_promotion_key,
        command_rows_found=command_rows_found,
        stages_planned=stages_planned,
        execution_allowed_flag=execution_allowed_flag,
        shared_packet_root_write_risk_flag=shared_packet_root_write_risk_flag,
        source_mutation_risk_flag=source_mutation_risk_flag,
        recommendation=recommendation,
    )
    return PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestResult(
        smoke_test_status=smoke_test_status,
        audit_status=audit_status,
        selected_promotion_key=selected_promotion_key,
        command_rows_found=command_rows_found,
        stages_planned=stages_planned,
        execution_allowed_flag=execution_allowed_flag,
        shared_packet_root_write_risk_flag=shared_packet_root_write_risk_flag,
        source_mutation_risk_flag=source_mutation_risk_flag,
        unsafe_command_count=unsafe_command_count,
        missing_runtime_count=missing_runtime_count,
        audit_frame=audit_frame,
        audit_summary_frame=audit_summary_frame,
        audit_memo_markdown=audit_memo_markdown,
        commands_frame=commands_frame,
        stage_results_frame=stage_results_frame,
        validation_frame=validation_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
        recommendation=recommendation,
    )


def write_promotions_materialized_source_single_promotion_isolated_smoke_test(
    *,
    packet_root: str | Path,
    promotion_key: str | None,
    output_root: str | Path | None = None,
    dry_run: bool = True,
    execute: bool = False,
    audit_only: bool = False,
    stop_after_stage: int | None = None,
    clean_run_root: bool = False,
    allow_complete: bool = False,
) -> PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    output_root_path.mkdir(parents=True, exist_ok=True)
    result = build_promotions_materialized_source_single_promotion_isolated_smoke_test(
        packet_root=packet_root_path,
        promotion_key=promotion_key,
        output_root=output_root_path,
        dry_run=dry_run,
        execute=execute,
        audit_only=audit_only,
        stop_after_stage=stop_after_stage,
        clean_run_root=clean_run_root,
        allow_complete=allow_complete,
    )
    commands_csv_path = output_root_path / COMMANDS_OUTPUT_FILE_NAME
    stage_results_csv_path = output_root_path / STAGE_RESULTS_FILE_NAME
    validation_csv_path = output_root_path / VALIDATION_FILE_NAME
    summary_csv_path = output_root_path / SUMMARY_FILE_NAME
    memo_md_path = output_root_path / MEMO_FILE_NAME
    command_audit_csv_path = output_root_path / COMMAND_AUDIT_FILE_NAME
    command_audit_summary_csv_path = output_root_path / COMMAND_AUDIT_SUMMARY_FILE_NAME
    command_audit_memo_md_path = output_root_path / COMMAND_AUDIT_MEMO_FILE_NAME
    result.commands_frame.to_csv(commands_csv_path, index=False)
    result.stage_results_frame.to_csv(stage_results_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")
    result.audit_frame.to_csv(command_audit_csv_path, index=False)
    result.audit_summary_frame.to_csv(command_audit_summary_csv_path, index=False)
    command_audit_memo_md_path.write_text(result.audit_memo_markdown, encoding="utf-8")
    return PromotionsMaterializedSourceSinglePromotionIsolatedSmokeTestArtifacts(
        output_root=str(output_root_path),
        commands_csv_path=str(commands_csv_path),
        stage_results_csv_path=str(stage_results_csv_path),
        validation_csv_path=str(validation_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
        command_audit_csv_path=str(command_audit_csv_path),
        command_audit_summary_csv_path=str(command_audit_summary_csv_path),
        command_audit_memo_md_path=str(command_audit_memo_md_path),
        smoke_test_status=result.smoke_test_status,
        audit_status=result.audit_status,
        selected_promotion_key=result.selected_promotion_key,
        command_rows_found=result.command_rows_found,
        stages_planned=result.stages_planned,
        execution_allowed_flag=result.execution_allowed_flag,
        shared_packet_root_write_risk_flag=result.shared_packet_root_write_risk_flag,
        source_mutation_risk_flag=result.source_mutation_risk_flag,
        unsafe_command_count=result.unsafe_command_count,
        missing_runtime_count=result.missing_runtime_count,
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a controlled single-promotion isolated smoke test for the 15-stage reconstruction chain."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--stop-after-stage", type=int)
    parser.add_argument("--clean-run-root", action="store_true")
    parser.add_argument("--allow-complete", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    execute = bool(args.execute)
    audit_only = bool(args.audit_only)
    dry_run = audit_only or (not execute or bool(args.dry_run))
    artifacts = write_promotions_materialized_source_single_promotion_isolated_smoke_test(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
        dry_run=dry_run,
        execute=execute,
        audit_only=audit_only,
        stop_after_stage=args.stop_after_stage,
        clean_run_root=bool(args.clean_run_root),
        allow_complete=bool(args.allow_complete),
    )
    print("smoke_test_status", artifacts.smoke_test_status)
    print("audit_status", artifacts.audit_status)
    print("selected_promotion_key", artifacts.selected_promotion_key)
    print("command_rows_found", artifacts.command_rows_found)
    print("stages_planned", artifacts.stages_planned)
    print("unsafe_command_count", artifacts.unsafe_command_count)
    print("missing_runtime_count", artifacts.missing_runtime_count)
    print("execution_allowed", artifacts.execution_allowed_flag)
    print("shared_packet_root_write_risk", artifacts.shared_packet_root_write_risk_flag)
    print("source_mutation_risk", artifacts.source_mutation_risk_flag)
    print("recommendation", artifacts.recommendation)
    print("single_promotion_isolated_smoke_test_commands", artifacts.commands_csv_path)
    print("single_promotion_isolated_smoke_test_stage_results", artifacts.stage_results_csv_path)
    print("single_promotion_isolated_smoke_test_validation", artifacts.validation_csv_path)
    print("single_promotion_isolated_smoke_test_summary", artifacts.summary_csv_path)
    print("single_promotion_isolated_smoke_test_memo", artifacts.memo_md_path)
    print("single_promotion_isolated_smoke_test_command_audit", artifacts.command_audit_csv_path)
    print("single_promotion_isolated_smoke_test_command_audit_summary", artifacts.command_audit_summary_csv_path)
    print("single_promotion_isolated_smoke_test_command_audit_memo", artifacts.command_audit_memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
