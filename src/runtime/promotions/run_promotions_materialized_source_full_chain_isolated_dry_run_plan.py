from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd

from runtime.promotions.run_promotions_materialized_source_multi_promotion_reconstruction_queue import (
    OUTPUT_FOLDER_NAME as RECONSTRUCTION_QUEUE_FOLDER_NAME,
    SOURCE_MATERIALIZED_FOLDER_NAME,
    STAGE_SPECS,
    StageSpec,
)
from runtime.promotions.run_promotions_materialized_source_promotion_isolation_plan import (
    OUTPUT_FOLDER_NAME as PROMOTION_ISOLATION_PLAN_FOLDER_NAME,
)


OUTPUT_FOLDER_NAME = "materialized_source_full_chain_isolated_dry_run_plan"
PROMOTION_RUNS_FOLDER_NAME = "promotion_runs"
SOURCE_ROWS_FILE_NAME = "promotion_source_rows.csv"

QUEUE_ROWS_FILE_NAME = "multi_promotion_reconstruction_queue_rows.csv"
STAGE_PLAN_FILE_NAME = "multi_promotion_reconstruction_stage_plan.csv"
ROOTS_FILE_NAME = "promotion_isolation_plan_roots.csv"
STAGE_MAPPING_FILE_NAME = "promotion_isolation_plan_stage_mapping.csv"

FULL_CHAIN_ISOLATED_DRY_RUN_PLAN_READY = "FULL_CHAIN_ISOLATED_DRY_RUN_PLAN_READY"
FULL_CHAIN_ISOLATED_DRY_RUN_PLAN_BLOCKED = "FULL_CHAIN_ISOLATED_DRY_RUN_PLAN_BLOCKED"

READY_RECOMMENDATION = (
    "Planner is ready. Next step is a single-promotion isolated execution smoke test, not recalibration or training."
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

BY_PROMOTION_COLUMNS: tuple[str, ...] = (
    "queue_rank",
    "promotion_key",
    "promotion_slug",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "current_queue_status",
    "already_complete_flag",
    "incomplete_flag",
    "selected_for_plan_flag",
    "source_rows_path",
    "promotion_run_root",
    "planned_stage_count",
    "command_row_count",
    "stages_isolation_capable_count",
    "all_stages_isolation_capable_flag",
    "shared_packet_root_write_risk_flag",
    "shared_packet_root_read_risk_flag",
    "execution_allowed_flag",
    "planner_only_flag",
    "recommendation",
)

STAGE_CONTRACTS_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_slug",
    "stage_number",
    "stage_name",
    "runtime_file",
    "stage_output_folder_name",
    "promotion_key_aware_flag",
    "output_root_supported_flag",
    "upstream_root_supported_flag",
    "uses_upstream_root_flag",
    "uses_output_root_flag",
    "isolation_ready_flag",
    "shared_packet_root_write_risk_flag",
    "shared_packet_root_read_risk_flag",
    "required_contract",
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


class PromotionsMaterializedSourceFullChainIsolatedDryRunPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class SelectedPromotion:
    queue_rank: int
    promotion_key: str
    promotion_slug: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    current_queue_status: str
    source_rows_path: str
    promotion_run_root: str
    already_complete_flag: int
    incomplete_flag: int


@dataclass(frozen=True)
class PromotionsMaterializedSourceFullChainIsolatedDryRunPlanResult:
    planner_status: str
    source_materialized_promotion_count: int
    already_complete_promotion_count: int
    incomplete_promotion_count: int
    command_rows_generated: int
    stages_per_promotion: int
    all_stages_isolation_capable_flag: int
    shared_packet_root_write_risk_flag: int
    execution_allowed_flag: int
    by_promotion_frame: pd.DataFrame
    commands_frame: pd.DataFrame
    stage_contracts_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str
    recommendation: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceFullChainIsolatedDryRunPlanArtifacts:
    output_root: str
    commands_csv_path: str
    by_promotion_csv_path: str
    stage_contracts_csv_path: str
    validation_csv_path: str
    summary_csv_path: str
    memo_md_path: str
    planner_status: str
    source_materialized_promotion_count: int
    incomplete_promotion_count: int
    command_rows_generated: int
    stages_per_promotion: int
    all_stages_isolation_capable_flag: int
    shared_packet_root_write_risk_flag: int
    execution_allowed_flag: int
    recommendation: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceFullChainIsolatedDryRunPlanError(
            f"CSV not found: {csv_path}"
        )
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceFullChainIsolatedDryRunPlanError(
            f"CSV is empty: {csv_path}"
        )
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceFullChainIsolatedDryRunPlanError(
            f"CSV is empty: {csv_path}"
        )
    return frame


def _to_int(value: object, *, default: int = 0) -> int:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return default
    return int(numeric)


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _validation_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
    return {
        "check_name": name,
        "check_status": status,
        "check_flag": int(flag),
        "details": details,
    }


def _source_materialized_promotion_count(packet_root: Path) -> int:
    source_root = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME
    if not source_root.exists():
        return 0
    return len([child for child in source_root.iterdir() if child.is_dir()])


def _runtime_file_path(spec: StageSpec) -> Path:
    return Path(__file__).resolve().parent / spec.module_file_name


def _runtime_supports_argument(runtime_file_path: Path, argument_name: str) -> bool:
    if not runtime_file_path.exists():
        return False
    return f'parser.add_argument("{argument_name}")' in runtime_file_path.read_text(
        encoding="utf-8"
    )


def _sorted_queue_rows(queue_rows_frame: pd.DataFrame) -> pd.DataFrame:
    return queue_rows_frame.sort_values(
        by=["queue_rank", "promotion_start_date", "promotion_key"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)


def _roots_lookup(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for row in frame.to_dict("records"):
        promotion_key = _normalize_text(row.get("promotion_key"))
        if promotion_key:
            lookup[promotion_key] = row
    return lookup


def _derived_promotion_run_root(packet_root: Path, source_rows_path: str, promotion_key: str) -> Path:
    if source_rows_path:
        return packet_root / PROMOTION_RUNS_FOLDER_NAME / Path(source_rows_path).parent.name
    return packet_root / PROMOTION_RUNS_FOLDER_NAME / promotion_key.replace("|", "-")


def _select_promotions(
    *,
    packet_root: Path,
    queue_rows_frame: pd.DataFrame,
    roots_frame: pd.DataFrame,
    promotion_key: str | None,
    max_promotions: int | None,
    include_complete: bool,
) -> list[SelectedPromotion]:
    queue_rows = _sorted_queue_rows(queue_rows_frame)
    if promotion_key:
        queue_rows = queue_rows.loc[
            queue_rows["promotion_key"].astype(str) == promotion_key
        ].reset_index(drop=True)
        if queue_rows.empty:
            raise PromotionsMaterializedSourceFullChainIsolatedDryRunPlanError(
                "Requested promotion key was not found in the reconstruction queue."
            )
    else:
        eligible = queue_rows["incomplete_flag"].map(_to_int).eq(1)
        if include_complete:
            eligible = eligible | queue_rows["already_complete_flag"].map(_to_int).eq(1)
        queue_rows = queue_rows.loc[eligible].reset_index(drop=True)
        if max_promotions is not None:
            queue_rows = queue_rows.head(max_promotions).reset_index(drop=True)
    if not include_complete and not promotion_key:
        queue_rows = queue_rows.loc[
            queue_rows["incomplete_flag"].map(_to_int).eq(1)
        ].reset_index(drop=True)
    if queue_rows.empty:
        raise PromotionsMaterializedSourceFullChainIsolatedDryRunPlanError(
            "No promotions were selected for the isolated dry-run plan."
        )

    roots_by_promotion = _roots_lookup(roots_frame)
    selected: list[SelectedPromotion] = []
    for row in queue_rows.to_dict("records"):
        key = _normalize_text(row.get("promotion_key"))
        source_rows_path = _normalize_text(row.get("source_rows_path"))
        root_row = roots_by_promotion.get(key, {})
        promotion_run_root = _normalize_text(root_row.get("proposed_promotion_run_root"))
        if not promotion_run_root:
            if _to_int(row.get("incomplete_flag", 0)) == 1:
                raise PromotionsMaterializedSourceFullChainIsolatedDryRunPlanError(
                    f"Missing promotion isolation root for incomplete promotion: {key}"
                )
            promotion_run_root = str(
                _derived_promotion_run_root(packet_root, source_rows_path, key)
            )
        selected.append(
            SelectedPromotion(
                queue_rank=_to_int(row.get("queue_rank", 0)),
                promotion_key=key,
                promotion_slug=Path(promotion_run_root).name,
                promotion_name=_normalize_text(row.get("promotion_name")),
                promotion_start_date=_normalize_text(row.get("promotion_start_date")),
                promotion_end_date=_normalize_text(row.get("promotion_end_date")),
                current_queue_status=_normalize_text(row.get("queue_status")),
                source_rows_path=source_rows_path,
                promotion_run_root=promotion_run_root,
                already_complete_flag=_to_int(row.get("already_complete_flag", 0)),
                incomplete_flag=_to_int(row.get("incomplete_flag", 0)),
            )
        )
    return selected


def _missing_stage_names(frame: pd.DataFrame, promotion_key: str) -> list[str]:
    stage_names = set(
        frame.loc[
            frame["promotion_key"].astype(str) == promotion_key,
            "stage_name",
        ].astype(str).tolist()
    )
    return [spec.stage_name for spec in STAGE_SPECS if spec.stage_name not in stage_names]


def _validate_stage_inputs(
    *,
    selected_promotions: list[SelectedPromotion],
    stage_plan_frame: pd.DataFrame,
    stage_mapping_frame: pd.DataFrame,
) -> None:
    for promotion in selected_promotions:
        if promotion.incomplete_flag != 1:
            continue
        missing_plan = _missing_stage_names(stage_plan_frame, promotion.promotion_key)
        if missing_plan:
            raise PromotionsMaterializedSourceFullChainIsolatedDryRunPlanError(
                f"Missing queue stage-plan rows for {promotion.promotion_key}: {', '.join(missing_plan)}"
            )
        missing_mapping = _missing_stage_names(stage_mapping_frame, promotion.promotion_key)
        if missing_mapping:
            raise PromotionsMaterializedSourceFullChainIsolatedDryRunPlanError(
                f"Missing isolation stage-mapping rows for {promotion.promotion_key}: {', '.join(missing_mapping)}"
            )


def _stage_contract_row(
    spec: StageSpec,
    *,
    packet_root: Path,
    promotion: SelectedPromotion,
) -> dict[str, object]:
    runtime_file_path = _runtime_file_path(spec)
    promotion_key_aware_flag = int(
        _runtime_supports_argument(runtime_file_path, "--promotion-key")
    )
    output_root_supported_flag = int(
        _runtime_supports_argument(runtime_file_path, "--output-root")
    )
    upstream_root_supported_flag = int(
        spec.stage_order == 1
        or _runtime_supports_argument(runtime_file_path, "--upstream-root")
    )
    output_root = Path(promotion.promotion_run_root) / spec.output_folder_name
    shared_output_root = packet_root / spec.output_folder_name
    shared_packet_root_write_risk_flag = int(output_root == shared_output_root)
    isolation_ready_flag = int(
        promotion_key_aware_flag == 1
        and output_root_supported_flag == 1
        and upstream_root_supported_flag == 1
    )
    return {
        "promotion_key": promotion.promotion_key,
        "promotion_slug": promotion.promotion_slug,
        "stage_number": spec.stage_order,
        "stage_name": spec.stage_name,
        "runtime_file": spec.module_file_name,
        "stage_output_folder_name": spec.output_folder_name,
        "promotion_key_aware_flag": promotion_key_aware_flag,
        "output_root_supported_flag": output_root_supported_flag,
        "upstream_root_supported_flag": upstream_root_supported_flag,
        "uses_upstream_root_flag": int(spec.stage_order > 1),
        "uses_output_root_flag": 1,
        "isolation_ready_flag": isolation_ready_flag,
        "shared_packet_root_write_risk_flag": shared_packet_root_write_risk_flag,
        "shared_packet_root_read_risk_flag": 0,
        "required_contract": (
            "Stage 1 reads the shared source-materialised input surface and writes only to its isolated promotion run root output folder."
            if spec.stage_order == 1
            else "Stage reads upstream artifacts through the isolated promotion run root and writes only to its isolated promotion run root output folder."
        ),
    }


def _command_for_stage(
    spec: StageSpec,
    *,
    packet_root: Path,
    promotion_key: str,
    promotion_run_root: Path,
) -> str:
    module_name = spec.module_file_name.removesuffix(".py")
    import_path = f"runtime.promotions.{module_name}"
    args = [
        "--packet-root",
        str(packet_root),
        "--promotion-key",
        promotion_key,
    ]
    if spec.stage_order > 1:
        args.extend(["--upstream-root", str(promotion_run_root)])
    args.extend(["--output-root", str(promotion_run_root / spec.output_folder_name)])
    serialized_args = ", ".join(f'"{value}"' for value in args)
    return (
        ".venv/bin/python -c 'import sys; sys.path.append(\"src\"); "
        f"from {import_path} import main; "
        f"raise SystemExit(main([{serialized_args}]))'"
    )


def _commands_rows(
    *,
    packet_root: Path,
    promotions: list[SelectedPromotion],
    stage_contracts_frame: pd.DataFrame,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for promotion in promotions:
        promotion_contracts = stage_contracts_frame.loc[
            stage_contracts_frame["promotion_key"].astype(str) == promotion.promotion_key
        ].set_index("stage_number")
        promotion_run_root = Path(promotion.promotion_run_root)
        for spec in STAGE_SPECS:
            contract = promotion_contracts.loc[spec.stage_order]
            rows.append(
                {
                    "promotion_key": promotion.promotion_key,
                    "promotion_slug": promotion.promotion_slug,
                    "stage_number": spec.stage_order,
                    "stage_name": spec.stage_name,
                    "runtime_file": spec.module_file_name,
                    "command": _command_for_stage(
                        spec,
                        packet_root=packet_root,
                        promotion_key=promotion.promotion_key,
                        promotion_run_root=promotion_run_root,
                    ),
                    "packet_root": str(packet_root),
                    "promotion_run_root": str(promotion_run_root),
                    "upstream_root": "" if spec.stage_order == 1 else str(promotion_run_root),
                    "output_root": str(promotion_run_root / spec.output_folder_name),
                    "uses_upstream_root_flag": _to_int(contract["uses_upstream_root_flag"], default=0),
                    "uses_output_root_flag": 1,
                    "isolation_ready_flag": _to_int(contract["isolation_ready_flag"], default=0),
                    "execution_allowed_flag": 0,
                    "planner_only_flag": 1,
                }
            )
    return rows


def _contains_forbidden_command_terms(commands_frame: pd.DataFrame, terms: Sequence[str]) -> bool:
    if commands_frame.empty:
        return False
    haystack = "\n".join(commands_frame["command"].astype(str).tolist()).lower()
    return any(term.lower() in haystack for term in terms)


def build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
    *,
    packet_root: str | Path,
    promotion_key: str | None = None,
    max_promotions: int | None = None,
    include_complete: bool = False,
    dry_run: bool = False,
) -> PromotionsMaterializedSourceFullChainIsolatedDryRunPlanResult:
    packet_root_path = Path(packet_root)
    queue_root = packet_root_path / RECONSTRUCTION_QUEUE_FOLDER_NAME
    isolation_root = packet_root_path / PROMOTION_ISOLATION_PLAN_FOLDER_NAME

    queue_rows_frame = _read_csv(queue_root / QUEUE_ROWS_FILE_NAME)
    stage_plan_frame = _read_csv(queue_root / STAGE_PLAN_FILE_NAME)
    roots_frame = _read_csv(isolation_root / ROOTS_FILE_NAME)
    stage_mapping_frame = _read_csv(isolation_root / STAGE_MAPPING_FILE_NAME)

    source_materialized_promotion_count = _source_materialized_promotion_count(packet_root_path)
    already_complete_promotion_count = int(
        queue_rows_frame["already_complete_flag"].map(_to_int).eq(1).sum()
    )
    incomplete_promotion_count = int(
        queue_rows_frame["incomplete_flag"].map(_to_int).eq(1).sum()
    )

    selected_promotions = _select_promotions(
        packet_root=packet_root_path,
        queue_rows_frame=queue_rows_frame,
        roots_frame=roots_frame,
        promotion_key=promotion_key,
        max_promotions=max_promotions,
        include_complete=include_complete,
    )
    _validate_stage_inputs(
        selected_promotions=selected_promotions,
        stage_plan_frame=stage_plan_frame,
        stage_mapping_frame=stage_mapping_frame,
    )

    stage_contract_rows = [
        _stage_contract_row(spec, packet_root=packet_root_path, promotion=promotion)
        for promotion in selected_promotions
        for spec in STAGE_SPECS
    ]
    stage_contracts_frame = pd.DataFrame(
        stage_contract_rows,
        columns=STAGE_CONTRACTS_COLUMNS,
    ).sort_values(
        by=["promotion_slug", "stage_number", "stage_name"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)

    commands_frame = pd.DataFrame(
        _commands_rows(
            packet_root=packet_root_path,
            promotions=selected_promotions,
            stage_contracts_frame=stage_contracts_frame,
        ),
        columns=COMMANDS_COLUMNS,
    ).sort_values(
        by=["promotion_slug", "stage_number", "stage_name"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)

    by_promotion_rows: list[dict[str, object]] = []
    for promotion in selected_promotions:
        promotion_commands = commands_frame.loc[
            commands_frame["promotion_key"].astype(str) == promotion.promotion_key
        ].reset_index(drop=True)
        promotion_contracts = stage_contracts_frame.loc[
            stage_contracts_frame["promotion_key"].astype(str) == promotion.promotion_key
        ].reset_index(drop=True)
        by_promotion_rows.append(
            {
                "queue_rank": promotion.queue_rank,
                "promotion_key": promotion.promotion_key,
                "promotion_slug": promotion.promotion_slug,
                "promotion_name": promotion.promotion_name,
                "promotion_start_date": promotion.promotion_start_date,
                "promotion_end_date": promotion.promotion_end_date,
                "current_queue_status": promotion.current_queue_status,
                "already_complete_flag": promotion.already_complete_flag,
                "incomplete_flag": promotion.incomplete_flag,
                "selected_for_plan_flag": 1,
                "source_rows_path": promotion.source_rows_path,
                "promotion_run_root": promotion.promotion_run_root,
                "planned_stage_count": len(STAGE_SPECS),
                "command_row_count": len(promotion_commands.index),
                "stages_isolation_capable_count": int(
                    promotion_contracts["isolation_ready_flag"].map(_to_int).eq(1).sum()
                ),
                "all_stages_isolation_capable_flag": int(
                    promotion_contracts["isolation_ready_flag"].map(_to_int).eq(1).all()
                ),
                "shared_packet_root_write_risk_flag": int(
                    promotion_contracts["shared_packet_root_write_risk_flag"].map(_to_int).eq(1).any()
                ),
                "shared_packet_root_read_risk_flag": int(
                    promotion_contracts["shared_packet_root_read_risk_flag"].map(_to_int).eq(1).any()
                ),
                "execution_allowed_flag": 0,
                "planner_only_flag": 1,
                "recommendation": READY_RECOMMENDATION,
            }
        )
    by_promotion_frame = pd.DataFrame(
        by_promotion_rows,
        columns=BY_PROMOTION_COLUMNS,
    ).sort_values(
        by=["queue_rank", "promotion_start_date", "promotion_key"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)

    stages_per_promotion = len(STAGE_SPECS)
    all_stages_isolation_capable_flag = int(
        not stage_contracts_frame.empty
        and stage_contracts_frame["isolation_ready_flag"].map(_to_int).eq(1).all()
    )
    shared_packet_root_write_risk_flag = int(
        stage_contracts_frame["shared_packet_root_write_risk_flag"].map(_to_int).eq(1).any()
    )
    shared_packet_root_read_risk_flag = int(
        stage_contracts_frame["shared_packet_root_read_risk_flag"].map(_to_int).eq(1).any()
    )
    execution_allowed_flag = 0
    no_stage_local_blocker_remains_flag = all_stages_isolation_capable_flag

    no_training_command_flag = int(
        not _contains_forbidden_command_terms(commands_frame, ("training", "train"))
    )
    no_recalibration_command_flag = int(
        not _contains_forbidden_command_terms(commands_frame, ("recalibration", "recalibrate"))
    )
    no_repeat_evidence_execution_flag = int(
        not _contains_forbidden_command_terms(
            commands_frame,
            ("repeat_evidence_execution", "run_repeat_evidence_execution"),
        )
    )
    no_shadow_simulation_flag = int(
        not _contains_forbidden_command_terms(commands_frame, ("shadow", "simulation"))
    )
    no_production_ordering_flag = int(
        not _contains_forbidden_command_terms(commands_frame, ("production_order", "auto_order"))
    )
    no_stage12_mutation_flag = int(
        not _contains_forbidden_command_terms(commands_frame, ("stage12_mutation", "stage_12_change"))
    )

    planner_status = (
        FULL_CHAIN_ISOLATED_DRY_RUN_PLAN_READY
        if (
            len(commands_frame.index) == len(selected_promotions) * stages_per_promotion
            and all_stages_isolation_capable_flag == 1
            and shared_packet_root_write_risk_flag == 0
            and shared_packet_root_read_risk_flag == 0
            and execution_allowed_flag == 0
        )
        else FULL_CHAIN_ISOLATED_DRY_RUN_PLAN_BLOCKED
    )

    stage1_rows = commands_frame.loc[
        commands_frame["stage_number"].map(_to_int).eq(1)
    ]
    downstream_rows = commands_frame.loc[
        commands_frame["stage_number"].map(_to_int).gt(1)
    ]
    validation_frame = pd.DataFrame(
        [
            _validation_row(
                "SOURCE_MATERIALIZED_PROMOTIONS_DETECTED",
                "PASS" if source_materialized_promotion_count == 5 else "FAIL",
                int(source_materialized_promotion_count == 5),
                f"source_materialized_promotion_count={source_materialized_promotion_count}",
            ),
            _validation_row(
                "ALREADY_COMPLETE_PROMOTIONS_DETECTED",
                "PASS" if already_complete_promotion_count == 1 else "FAIL",
                int(already_complete_promotion_count == 1),
                f"already_complete_promotion_count={already_complete_promotion_count}",
            ),
            _validation_row(
                "INCOMPLETE_PROMOTIONS_DETECTED",
                "PASS" if incomplete_promotion_count == 4 else "FAIL",
                int(incomplete_promotion_count == 4),
                f"incomplete_promotion_count={incomplete_promotion_count}",
            ),
            _validation_row(
                "FIFTEEN_STAGES_PER_SELECTED_PROMOTION",
                "PASS"
                if len(commands_frame.index) == len(selected_promotions) * stages_per_promotion
                else "FAIL",
                int(len(commands_frame.index) == len(selected_promotions) * stages_per_promotion),
                f"command_rows={len(commands_frame.index)}, selected_promotions={len(selected_promotions)}, stages_per_promotion={stages_per_promotion}",
            ),
            _validation_row(
                "ALL_15_STAGES_ISOLATION_CAPABLE",
                "PASS" if all_stages_isolation_capable_flag else "FAIL",
                all_stages_isolation_capable_flag,
                f"stage_rows={len(stage_contracts_frame.index)}",
            ),
            _validation_row(
                "STAGE1_HAS_NO_UPSTREAM_ROOT",
                "PASS" if stage1_rows["uses_upstream_root_flag"].map(_to_int).eq(0).all() else "FAIL",
                int(stage1_rows["uses_upstream_root_flag"].map(_to_int).eq(0).all()),
                "Stage 1 commands omit --upstream-root and still write to isolated promotion-specific output roots.",
            ),
            _validation_row(
                "STAGES_2_TO_15_USE_UPSTREAM_ROOT",
                "PASS" if downstream_rows["uses_upstream_root_flag"].map(_to_int).eq(1).all() else "FAIL",
                int(downstream_rows["uses_upstream_root_flag"].map(_to_int).eq(1).all()),
                "Stages 2 through 15 read upstream artifacts from the isolated promotion run root.",
            ),
            _validation_row(
                "ALL_STAGES_USE_OUTPUT_ROOT",
                "PASS" if commands_frame["uses_output_root_flag"].map(_to_int).eq(1).all() else "FAIL",
                int(commands_frame["uses_output_root_flag"].map(_to_int).eq(1).all()),
                "Every stage command writes to an isolated promotion-specific output root.",
            ),
            _validation_row(
                "NO_SHARED_PACKET_ROOT_WRITES",
                "PASS" if shared_packet_root_write_risk_flag == 0 else "FAIL",
                int(shared_packet_root_write_risk_flag == 0),
                "No generated command writes to shared packet-root stage folders.",
            ),
            _validation_row(
                "NO_SHARED_PACKET_ROOT_STAGE_READS",
                "PASS" if shared_packet_root_read_risk_flag == 0 else "FAIL",
                int(shared_packet_root_read_risk_flag == 0),
                "Only Stage 1 depends on shared source-materialised packet-root inputs.",
            ),
            _validation_row(
                "NO_TRAINING_COMMAND_GENERATED",
                "PASS" if no_training_command_flag else "FAIL",
                no_training_command_flag,
                "Planner does not generate training commands.",
            ),
            _validation_row(
                "NO_RECALIBRATION_COMMAND_GENERATED",
                "PASS" if no_recalibration_command_flag else "FAIL",
                no_recalibration_command_flag,
                "Planner does not generate recalibration commands.",
            ),
            _validation_row(
                "NO_REPEAT_EVIDENCE_EXECUTION_GENERATED",
                "PASS" if no_repeat_evidence_execution_flag else "FAIL",
                no_repeat_evidence_execution_flag,
                "Planner does not generate repeat-evidence execution commands.",
            ),
            _validation_row(
                "NO_SHADOW_SIMULATION_GENERATED",
                "PASS" if no_shadow_simulation_flag else "FAIL",
                no_shadow_simulation_flag,
                "Planner does not generate shadow simulation commands.",
            ),
            _validation_row(
                "NO_PRODUCTION_ORDERING_COMMAND_GENERATED",
                "PASS" if no_production_ordering_flag else "FAIL",
                no_production_ordering_flag,
                "Planner does not generate production-ordering commands.",
            ),
            _validation_row(
                "NO_STAGE12_MUTATION_COMMAND_GENERATED",
                "PASS" if no_stage12_mutation_flag else "FAIL",
                no_stage12_mutation_flag,
                "Planner does not generate Stage 12 mutation commands.",
            ),
            _validation_row(
                "EXECUTION_REMAINS_BLOCKED",
                "PASS"
                if commands_frame["execution_allowed_flag"].map(_to_int).eq(0).all()
                and commands_frame["planner_only_flag"].map(_to_int).eq(1).all()
                else "FAIL",
                int(
                    commands_frame["execution_allowed_flag"].map(_to_int).eq(0).all()
                    and commands_frame["planner_only_flag"].map(_to_int).eq(1).all()
                ),
                "All generated commands remain planner-only and blocked from execution.",
            ),
            _validation_row(
                "NO_STAGE_LOCAL_BLOCKER_REMAINS",
                "PASS" if no_stage_local_blocker_remains_flag else "FAIL",
                no_stage_local_blocker_remains_flag,
                "All 15 stage runtimes support the isolated promotion-run contract.",
            ),
            _validation_row(
                "PLANNER_DOES_NOT_EXECUTE_STAGE_COMMANDS",
                "PASS",
                1,
                f"dry_run_requested={int(dry_run)}; planner only emitted {len(commands_frame.index)} command rows without executing them.",
            ),
        ],
        columns=VALIDATION_COLUMNS,
    )

    summary_frame = pd.DataFrame(
        [
            _summary_row(
                "PLANNER_STATUS",
                planner_status,
                "Overall diagnostics-only full-chain isolated dry-run planner status.",
            ),
            _summary_row(
                "SOURCE_MATERIALIZED_PROMOTION_COUNT",
                source_materialized_promotion_count,
                "Source-materialised promotion folders detected under source_materialized_promotions.",
            ),
            _summary_row(
                "ALREADY_COMPLETE_PROMOTION_COUNT",
                already_complete_promotion_count,
                "Promotions already complete through the current repeat-evidence gate.",
            ),
            _summary_row(
                "INCOMPLETE_PROMOTION_COUNT",
                incomplete_promotion_count,
                "Incomplete promotions available for isolated dry-run command planning.",
            ),
            _summary_row(
                "SELECTED_PROMOTION_COUNT",
                len(selected_promotions),
                "Promotions selected for the current planner run.",
            ),
            _summary_row(
                "COMMAND_ROWS_GENERATED",
                len(commands_frame.index),
                "Planner-only stage command rows generated for the selected promotions.",
            ),
            _summary_row(
                "STAGES_PER_PROMOTION",
                stages_per_promotion,
                "Stage count mapped into each isolated promotion run root.",
            ),
            _summary_row(
                "ALL_15_STAGES_ISOLATION_CAPABLE",
                all_stages_isolation_capable_flag,
                "Whether all 15 stage runtimes now support the isolated promotion-run contract.",
            ),
            _summary_row(
                "SHARED_PACKET_ROOT_WRITE_RISK",
                shared_packet_root_write_risk_flag,
                "Whether any generated command still writes into a shared packet-root stage folder.",
            ),
            _summary_row(
                "EXECUTION_ALLOWED",
                execution_allowed_flag,
                "Planner-only task keeps execution blocked for every generated command.",
            ),
            _summary_row(
                "NO_STAGE_LOCAL_BLOCKER_REMAINS",
                no_stage_local_blocker_remains_flag,
                "Whether any stage-local isolation blocker still remains in the 15-stage chain.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Full-Chain Isolated Dry-Run Plan",
            "",
            "This is a diagnostics-only planner for a promotion-isolated full-chain dry run across stages 1 through 15.",
            "This does not execute any stage command.",
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
            "",
            f"Planner status: {planner_status}",
            f"Source-materialised promotion count: {source_materialized_promotion_count}",
            f"Already complete promotion count: {already_complete_promotion_count}",
            f"Incomplete promotion count: {incomplete_promotion_count}",
            f"Selected promotion count: {len(selected_promotions)}",
            f"Command rows generated: {len(commands_frame.index)}",
            f"Stages per promotion: {stages_per_promotion}",
            f"All 15 stages isolation-capable: {all_stages_isolation_capable_flag}",
            f"Shared packet-root write risk: {shared_packet_root_write_risk_flag}",
            f"Execution allowed: {execution_allowed_flag}",
            "",
            "## Recommendation",
            READY_RECOMMENDATION,
        ]
    ).strip()

    return PromotionsMaterializedSourceFullChainIsolatedDryRunPlanResult(
        planner_status=planner_status,
        source_materialized_promotion_count=source_materialized_promotion_count,
        already_complete_promotion_count=already_complete_promotion_count,
        incomplete_promotion_count=incomplete_promotion_count,
        command_rows_generated=len(commands_frame.index),
        stages_per_promotion=stages_per_promotion,
        all_stages_isolation_capable_flag=all_stages_isolation_capable_flag,
        shared_packet_root_write_risk_flag=shared_packet_root_write_risk_flag,
        execution_allowed_flag=execution_allowed_flag,
        by_promotion_frame=by_promotion_frame,
        commands_frame=commands_frame,
        stage_contracts_frame=stage_contracts_frame,
        validation_frame=validation_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
        recommendation=READY_RECOMMENDATION,
    )


def write_promotions_materialized_source_full_chain_isolated_dry_run_plan(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    promotion_key: str | None = None,
    max_promotions: int | None = None,
    include_complete: bool = False,
    dry_run: bool = False,
) -> PromotionsMaterializedSourceFullChainIsolatedDryRunPlanArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = (
        Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    )
    result = build_promotions_materialized_source_full_chain_isolated_dry_run_plan(
        packet_root=packet_root_path,
        promotion_key=promotion_key,
        max_promotions=max_promotions,
        include_complete=include_complete,
        dry_run=dry_run,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    commands_csv_path = output_root_path / "full_chain_isolated_dry_run_commands.csv"
    by_promotion_csv_path = output_root_path / "full_chain_isolated_dry_run_by_promotion.csv"
    stage_contracts_csv_path = output_root_path / "full_chain_isolated_dry_run_stage_contracts.csv"
    validation_csv_path = output_root_path / "full_chain_isolated_dry_run_validation.csv"
    summary_csv_path = output_root_path / "full_chain_isolated_dry_run_summary.csv"
    memo_md_path = output_root_path / "full_chain_isolated_dry_run_memo.md"

    result.commands_frame.to_csv(commands_csv_path, index=False)
    result.by_promotion_frame.to_csv(by_promotion_csv_path, index=False)
    result.stage_contracts_frame.to_csv(stage_contracts_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceFullChainIsolatedDryRunPlanArtifacts(
        output_root=str(output_root_path),
        commands_csv_path=str(commands_csv_path),
        by_promotion_csv_path=str(by_promotion_csv_path),
        stage_contracts_csv_path=str(stage_contracts_csv_path),
        validation_csv_path=str(validation_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
        planner_status=result.planner_status,
        source_materialized_promotion_count=result.source_materialized_promotion_count,
        incomplete_promotion_count=result.incomplete_promotion_count,
        command_rows_generated=result.command_rows_generated,
        stages_per_promotion=result.stages_per_promotion,
        all_stages_isolation_capable_flag=result.all_stages_isolation_capable_flag,
        shared_packet_root_write_risk_flag=result.shared_packet_root_write_risk_flag,
        execution_allowed_flag=result.execution_allowed_flag,
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only full-chain isolated dry-run planner."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--promotion-key")
    parser.add_argument("--max-promotions", type=int)
    parser.add_argument("--include-complete", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_full_chain_isolated_dry_run_plan(
        packet_root=args.packet_root,
        output_root=args.output_root,
        promotion_key=args.promotion_key,
        max_promotions=args.max_promotions,
        include_complete=args.include_complete,
        dry_run=args.dry_run,
    )
    print("planner_status", artifacts.planner_status)
    print("source_materialized_promotion_count", artifacts.source_materialized_promotion_count)
    print("incomplete_promotion_count", artifacts.incomplete_promotion_count)
    print("command_rows_generated", artifacts.command_rows_generated)
    print("stages_per_promotion", artifacts.stages_per_promotion)
    print("all_15_stages_isolation_capable", artifacts.all_stages_isolation_capable_flag)
    print("shared_packet_root_write_risk", artifacts.shared_packet_root_write_risk_flag)
    print("execution_allowed", artifacts.execution_allowed_flag)
    print("recommendation", artifacts.recommendation)
    print("full_chain_isolated_dry_run_commands", artifacts.commands_csv_path)
    print("full_chain_isolated_dry_run_by_promotion", artifacts.by_promotion_csv_path)
    print("full_chain_isolated_dry_run_stage_contracts", artifacts.stage_contracts_csv_path)
    print("full_chain_isolated_dry_run_validation", artifacts.validation_csv_path)
    print("full_chain_isolated_dry_run_summary", artifacts.summary_csv_path)
    print("full_chain_isolated_dry_run_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
