from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd

from runtime.promotions.run_promotions_materialized_source_multi_promotion_reconstruction_queue import (
    OUTPUT_FOLDER_NAME as RECONSTRUCTION_QUEUE_FOLDER_NAME,
    STAGE_SPECS,
)


OUTPUT_FOLDER_NAME = "materialized_source_promotion_isolation_plan"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
PROMOTION_RUNS_FOLDER_NAME = "promotion_runs"

QUEUE_ROWS_FILE_NAME = "multi_promotion_reconstruction_queue_rows.csv"
QUEUE_BY_PROMOTION_FILE_NAME = "multi_promotion_reconstruction_queue_by_promotion.csv"
LEGACY_QUEUE_BY_PROMOTION_FILE_NAME = "multi_promotion_reconstruction_by_promotion.csv"
STAGE_PLAN_FILE_NAME = "multi_promotion_reconstruction_stage_plan.csv"
QUEUE_SUMMARY_FILE_NAME = "multi_promotion_reconstruction_summary.csv"

PROMOTION_ISOLATION_READY = "PROMOTION_ISOLATION_READY"
PROMOTION_ISOLATION_PLAN_READY_RUNTIME_CHANGES_REQUIRED = (
    "PROMOTION_ISOLATION_PLAN_READY_RUNTIME_CHANGES_REQUIRED"
)
PROMOTION_ISOLATION_BLOCKED_SHARED_ARTIFACT_ROOTS = (
    "PROMOTION_ISOLATION_BLOCKED_SHARED_ARTIFACT_ROOTS"
)
PROMOTION_ISOLATION_BLOCKED_MISSING_STAGE_MAPPING = (
    "PROMOTION_ISOLATION_BLOCKED_MISSING_STAGE_MAPPING"
)

ROOTS_COLUMNS: tuple[str, ...] = (
    "queue_rank",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_rows_path",
    "current_queue_status",
    "proposed_promotion_run_root",
    "proposed_stage_root_base",
    "planned_stage_count",
    "missing_stage_mapping_count",
    "shared_root_risk_flag",
    "execution_mode_safe_now_flag",
    "isolation_plan_status",
    "recommended_next_step",
)

STAGE_MAPPING_COLUMNS: tuple[str, ...] = (
    "queue_rank",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "stage_order",
    "stage_name",
    "current_shared_output_folder",
    "proposed_isolated_output_folder",
    "runtime_file",
    "promotion_key_aware_flag",
    "requires_output_root_parameter_flag",
    "requires_input_root_parameter_flag",
    "safe_for_multi_promotion_execution_flag",
    "required_change",
)

REQUIRED_RUNTIME_CHANGES_COLUMNS: tuple[str, ...] = (
    "stage_order",
    "stage_name",
    "runtime_file",
    "promotion_key_aware_flag",
    "output_root_supported_flag",
    "input_root_supported_flag",
    "requires_output_root_parameter_flag",
    "requires_input_root_parameter_flag",
    "required_runtime_change_flag",
    "safe_for_multi_promotion_execution_flag",
    "impacted_promotion_count",
    "required_change",
)

EXECUTION_SAFETY_COLUMNS: tuple[str, ...] = (
    "plan_scope",
    "promotion_key",
    "promotion_name",
    "planned_stage_count",
    "safe_stage_count",
    "unsafe_stage_count",
    "runtime_changes_required_count",
    "missing_stage_mapping_flag",
    "shared_root_risk_flag",
    "shared_root_risk_status",
    "execution_mode_safe_now_flag",
    "isolation_plan_status",
    "recommendation",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)


class PromotionsMaterializedSourcePromotionIsolationPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class SelectedPromotion:
    queue_rank: int
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    current_queue_status: str
    source_rows_path: str
    proposed_promotion_run_root: str


@dataclass(frozen=True)
class PromotionsMaterializedSourcePromotionIsolationPlanResult:
    isolation_plan_status: str
    source_materialized_promotion_count: int
    incomplete_promotion_count: int
    isolated_roots_planned: int
    stages_mapped_per_promotion: int
    stages_requiring_runtime_changes: int
    shared_root_risk_status: str
    execution_mode_safe_now_flag: int
    recommendation: str
    roots_frame: pd.DataFrame
    stage_mapping_frame: pd.DataFrame
    required_runtime_changes_frame: pd.DataFrame
    execution_safety_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourcePromotionIsolationPlanArtifacts:
    output_root: str
    roots_csv_path: str
    stage_mapping_csv_path: str
    required_runtime_changes_csv_path: str
    execution_safety_csv_path: str
    summary_csv_path: str
    memo_md_path: str
    isolation_plan_status: str
    source_materialized_promotion_count: int
    incomplete_promotion_count: int
    isolated_roots_planned: int
    stages_mapped_per_promotion: int
    stages_requiring_runtime_changes: int
    shared_root_risk_status: str
    execution_mode_safe_now_flag: int
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
        raise PromotionsMaterializedSourcePromotionIsolationPlanError(
            f"CSV not found: {csv_path}"
        )
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourcePromotionIsolationPlanError(
            f"CSV is empty: {csv_path}"
        )
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourcePromotionIsolationPlanError(
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


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _resolve_existing_file(root: Path, file_names: Sequence[str]) -> Path:
    for file_name in file_names:
        candidate = root / file_name
        if candidate.exists():
            return candidate
    raise PromotionsMaterializedSourcePromotionIsolationPlanError(
        f"None of the expected files were found under {root}: {', '.join(file_names)}"
    )


def _promotion_folders(packet_root: Path) -> list[Path]:
    source_root = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME
    if not source_root.exists():
        return []
    return sorted(child for child in source_root.iterdir() if child.is_dir())


def _runtime_file_path(stage_runtime_module: str) -> Path:
    return Path(__file__).resolve().parent / f"{stage_runtime_module}.py"


def _runtime_supports_argument(runtime_file_path: Path, argument_name: str) -> bool:
    if not runtime_file_path.exists():
        return False
    return f'parser.add_argument("{argument_name}")' in runtime_file_path.read_text(
        encoding="utf-8"
    )


def _selected_promotions(
    *,
    by_promotion_frame: pd.DataFrame,
    promotion_key: str | None,
    max_promotions: int | None,
    packet_root: Path,
) -> list[SelectedPromotion]:
    incomplete = by_promotion_frame.loc[
        by_promotion_frame["incomplete_flag"].map(_to_int).eq(1)
    ].copy()
    incomplete = incomplete.sort_values(
        by=["queue_rank", "promotion_start_date", "promotion_key"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)
    if promotion_key:
        incomplete = incomplete.loc[
            incomplete["promotion_key"].astype(str) == promotion_key
        ].reset_index(drop=True)
        if incomplete.empty:
            raise PromotionsMaterializedSourcePromotionIsolationPlanError(
                "Requested promotion key was not found in the incomplete reconstruction queue."
            )
    elif max_promotions is not None:
        incomplete = incomplete.head(max_promotions).reset_index(drop=True)
    selected: list[SelectedPromotion] = []
    for row in incomplete.to_dict("records"):
        source_rows_path = _normalize_text(row.get("source_rows_path"))
        promotion_run_slug = (
            Path(source_rows_path).parent.name if source_rows_path else _normalize_text(row.get("promotion_key")).replace("|", "-")
        )
        proposed_promotion_run_root = str(
            packet_root / PROMOTION_RUNS_FOLDER_NAME / promotion_run_slug
        )
        selected.append(
            SelectedPromotion(
                queue_rank=_to_int(row.get("queue_rank", 0)),
                promotion_key=_normalize_text(row.get("promotion_key")),
                promotion_name=_normalize_text(row.get("promotion_name")),
                promotion_start_date=_normalize_text(row.get("promotion_start_date")),
                promotion_end_date=_normalize_text(row.get("promotion_end_date")),
                current_queue_status=_normalize_text(row.get("queue_status")),
                source_rows_path=source_rows_path,
                proposed_promotion_run_root=proposed_promotion_run_root,
            )
        )
    return selected


def _stage_spec_lookup() -> dict[str, object]:
    return {spec.stage_name: spec for spec in STAGE_SPECS}


def _stage_mapping_rows(
    *,
    packet_root: Path,
    selected_promotions: list[SelectedPromotion],
    stage_plan_frame: pd.DataFrame,
) -> tuple[list[dict[str, object]], dict[str, int], dict[str, int]]:
    stage_lookup = _stage_spec_lookup()
    rows: list[dict[str, object]] = []
    missing_stage_mapping_count: dict[str, int] = {}
    runtime_changes_by_promotion: dict[str, int] = {}
    for promotion in selected_promotions:
        promotion_stage_rows = stage_plan_frame.loc[
            stage_plan_frame["promotion_key"].astype(str) == promotion.promotion_key
        ].copy()
        promotion_stage_rows = promotion_stage_rows.sort_values(
            by=["stage_order", "stage_name"],
            ascending=[True, True],
            kind="stable",
        ).reset_index(drop=True)
        observed_stage_names = set(
            promotion_stage_rows["stage_name"].astype(str).tolist()
        )
        missing_stage_mapping_count[promotion.promotion_key] = len(
            [spec for spec in STAGE_SPECS if spec.stage_name not in observed_stage_names]
        )
        runtime_changes_by_promotion[promotion.promotion_key] = 0
        for spec in STAGE_SPECS:
            stage_row_frame = promotion_stage_rows.loc[
                promotion_stage_rows["stage_name"].astype(str) == spec.stage_name
            ].reset_index(drop=True)
            if stage_row_frame.empty:
                rows.append(
                    {
                        "queue_rank": promotion.queue_rank,
                        "promotion_key": promotion.promotion_key,
                        "promotion_name": promotion.promotion_name,
                        "promotion_start_date": promotion.promotion_start_date,
                        "promotion_end_date": promotion.promotion_end_date,
                        "stage_order": spec.stage_order,
                        "stage_name": spec.stage_name,
                        "current_shared_output_folder": "",
                        "proposed_isolated_output_folder": str(
                            Path(promotion.proposed_promotion_run_root)
                            / spec.output_folder_name
                        ),
                        "runtime_file": str(_runtime_file_path(spec.module_file_name.removesuffix(".py"))),
                        "promotion_key_aware_flag": 0,
                        "requires_output_root_parameter_flag": 1,
                        "requires_input_root_parameter_flag": int(spec.stage_order > 1),
                        "safe_for_multi_promotion_execution_flag": 0,
                        "required_change": "Stage mapping is missing from the reconstruction queue output. Rebuild the queue plan before assessing promotion-isolated execution safety.",
                    }
                )
                runtime_changes_by_promotion[promotion.promotion_key] += 1
                continue
            stage_row = stage_row_frame.iloc[0].to_dict()
            runtime_file_path = _runtime_file_path(
                _normalize_text(stage_row.get("stage_runtime_module"))
            )
            output_root_supported_flag = int(
                _runtime_supports_argument(runtime_file_path, "--output-root")
            )
            input_root_supported_flag = int(
                _runtime_supports_argument(runtime_file_path, "--input-root")
            )
            promotion_key_aware_flag = _to_int(
                stage_row.get("stage_promotion_key_aware_flag", 0)
            )
            requires_output_root_parameter_flag = int(
                output_root_supported_flag == 0
            )
            requires_input_root_parameter_flag = int(
                spec.stage_order > 1 and input_root_supported_flag == 0
            )
            safe_for_multi_promotion_execution_flag = int(
                promotion_key_aware_flag == 1
                and output_root_supported_flag == 1
                and (spec.stage_order == 1 or input_root_supported_flag == 1)
            )
            if requires_output_root_parameter_flag:
                required_change = (
                    "Add --output-root support so this stage can write into the promotion-specific run root."
                )
            elif requires_input_root_parameter_flag:
                required_change = (
                    "Add an isolated input-root or upstream stage-root parameter so this stage reads prior artifacts from the promotion-specific run root instead of shared packet-root stage folders."
                )
            elif promotion_key_aware_flag == 0:
                required_change = (
                    "Add promotion-key selection support before using this stage in a multi-promotion isolated execution plan."
                )
            else:
                required_change = (
                    "No runtime code change required. Invoke this stage with promotion-specific --output-root under the isolated promotion run root."
                )
            runtime_changes_by_promotion[promotion.promotion_key] += int(
                safe_for_multi_promotion_execution_flag == 0
            )
            rows.append(
                {
                    "queue_rank": promotion.queue_rank,
                    "promotion_key": promotion.promotion_key,
                    "promotion_name": promotion.promotion_name,
                    "promotion_start_date": promotion.promotion_start_date,
                    "promotion_end_date": promotion.promotion_end_date,
                    "stage_order": spec.stage_order,
                    "stage_name": spec.stage_name,
                    "current_shared_output_folder": str(
                        packet_root / _normalize_text(stage_row.get("stage_output_folder_name"))
                    ),
                    "proposed_isolated_output_folder": str(
                        Path(promotion.proposed_promotion_run_root)
                        / _normalize_text(stage_row.get("stage_output_folder_name"))
                    ),
                    "runtime_file": str(runtime_file_path),
                    "promotion_key_aware_flag": promotion_key_aware_flag,
                    "requires_output_root_parameter_flag": requires_output_root_parameter_flag,
                    "requires_input_root_parameter_flag": requires_input_root_parameter_flag,
                    "safe_for_multi_promotion_execution_flag": safe_for_multi_promotion_execution_flag,
                    "required_change": required_change,
                }
            )
    return rows, missing_stage_mapping_count, runtime_changes_by_promotion


def _required_runtime_changes_frame(stage_mapping_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if stage_mapping_frame.empty:
        return pd.DataFrame(columns=REQUIRED_RUNTIME_CHANGES_COLUMNS)
    grouped = stage_mapping_frame.groupby("stage_name", sort=False)
    for stage_name, group in grouped:
        first = group.iloc[0]
        rows.append(
            {
                "stage_order": _to_int(first["stage_order"], default=0),
                "stage_name": _normalize_text(stage_name),
                "runtime_file": _normalize_text(first["runtime_file"]),
                "promotion_key_aware_flag": _to_int(first["promotion_key_aware_flag"], default=0),
                "output_root_supported_flag": int(
                    _to_int(first["requires_output_root_parameter_flag"], default=0) == 0
                ),
                "input_root_supported_flag": int(
                    _to_int(first["requires_input_root_parameter_flag"], default=0) == 0
                    or _to_int(first["stage_order"], default=0) == 1
                ),
                "requires_output_root_parameter_flag": _to_int(
                    first["requires_output_root_parameter_flag"], default=0
                ),
                "requires_input_root_parameter_flag": _to_int(
                    first["requires_input_root_parameter_flag"], default=0
                ),
                "required_runtime_change_flag": int(
                    group["safe_for_multi_promotion_execution_flag"].map(_to_int).eq(0).any()
                ),
                "safe_for_multi_promotion_execution_flag": int(
                    group["safe_for_multi_promotion_execution_flag"].map(_to_int).eq(1).all()
                ),
                "impacted_promotion_count": int(group["promotion_key"].astype(str).nunique()),
                "required_change": _normalize_text(first["required_change"]),
            }
        )
    frame = pd.DataFrame(rows, columns=REQUIRED_RUNTIME_CHANGES_COLUMNS)
    return frame.sort_values(
        by=["stage_order", "stage_name"],
        ascending=[True, True],
        kind="stable",
    ).reset_index(drop=True)


def _isolation_status(
    *,
    missing_stage_mapping_flag: int,
    required_runtime_changes_count: int,
    shared_root_risk_flag: int,
) -> str:
    if missing_stage_mapping_flag:
        return PROMOTION_ISOLATION_BLOCKED_MISSING_STAGE_MAPPING
    if required_runtime_changes_count > 0:
        return PROMOTION_ISOLATION_PLAN_READY_RUNTIME_CHANGES_REQUIRED
    if shared_root_risk_flag:
        return PROMOTION_ISOLATION_BLOCKED_SHARED_ARTIFACT_ROOTS
    return PROMOTION_ISOLATION_READY


def build_promotions_materialized_source_promotion_isolation_plan(
    *,
    packet_root: str | Path,
    promotion_key: str | None = None,
    max_promotions: int | None = None,
) -> PromotionsMaterializedSourcePromotionIsolationPlanResult:
    packet_root_path = Path(packet_root)
    queue_root = packet_root_path / RECONSTRUCTION_QUEUE_FOLDER_NAME
    queue_rows_frame = _read_csv(queue_root / QUEUE_ROWS_FILE_NAME)
    by_promotion_path = _resolve_existing_file(
        queue_root,
        (QUEUE_BY_PROMOTION_FILE_NAME, LEGACY_QUEUE_BY_PROMOTION_FILE_NAME),
    )
    by_promotion_frame = _read_csv(by_promotion_path)
    stage_plan_frame = _read_csv(queue_root / STAGE_PLAN_FILE_NAME)
    queue_summary_frame = _read_csv(queue_root / QUEUE_SUMMARY_FILE_NAME)
    queue_summary_metrics = _metric_lookup(queue_summary_frame)

    source_materialized_promotion_count = len(_promotion_folders(packet_root_path))
    selected_promotions = _selected_promotions(
        by_promotion_frame=by_promotion_frame,
        promotion_key=promotion_key,
        max_promotions=max_promotions,
        packet_root=packet_root_path,
    )
    incomplete_promotion_count = int(
        by_promotion_frame["incomplete_flag"].map(_to_int).eq(1).sum()
    )

    stage_mapping_rows, missing_stage_mapping_count, runtime_changes_by_promotion = (
        _stage_mapping_rows(
            packet_root=packet_root_path,
            selected_promotions=selected_promotions,
            stage_plan_frame=stage_plan_frame,
        )
    )
    stage_mapping_frame = pd.DataFrame(stage_mapping_rows, columns=STAGE_MAPPING_COLUMNS)
    required_runtime_changes_frame = _required_runtime_changes_frame(stage_mapping_frame)
    stages_requiring_runtime_changes = int(
        required_runtime_changes_frame.get(
            "required_runtime_change_flag", pd.Series(dtype="int64")
        )
        .map(_to_int)
        .sum()
    )
    stages_mapped_per_promotion = len(STAGE_SPECS)

    roots_rows: list[dict[str, object]] = []
    execution_safety_rows: list[dict[str, object]] = []
    overall_shared_root_risk_flag = 0
    overall_execution_mode_safe_now_flag = 1
    overall_missing_stage_mapping_flag = 0
    for promotion in selected_promotions:
        promotion_stage_mapping = stage_mapping_frame.loc[
            stage_mapping_frame["promotion_key"].astype(str) == promotion.promotion_key
        ].reset_index(drop=True)
        safe_stage_count = int(
            promotion_stage_mapping.get(
                "safe_for_multi_promotion_execution_flag", pd.Series(dtype="int64")
            )
            .map(_to_int)
            .eq(1)
            .sum()
        )
        unsafe_stage_count = int(len(promotion_stage_mapping.index) - safe_stage_count)
        required_runtime_changes_count = runtime_changes_by_promotion.get(
            promotion.promotion_key,
            0,
        )
        missing_stage_mapping_flag = int(
            missing_stage_mapping_count.get(promotion.promotion_key, 0) > 0
        )
        shared_root_risk_flag = int(unsafe_stage_count > 0)
        isolation_plan_status = _isolation_status(
            missing_stage_mapping_flag=missing_stage_mapping_flag,
            required_runtime_changes_count=required_runtime_changes_count,
            shared_root_risk_flag=shared_root_risk_flag,
        )
        execution_mode_safe_now_flag = int(
            isolation_plan_status == PROMOTION_ISOLATION_READY
        )
        overall_shared_root_risk_flag = max(overall_shared_root_risk_flag, shared_root_risk_flag)
        overall_execution_mode_safe_now_flag = min(
            overall_execution_mode_safe_now_flag,
            execution_mode_safe_now_flag,
        )
        overall_missing_stage_mapping_flag = max(
            overall_missing_stage_mapping_flag,
            missing_stage_mapping_flag,
        )
        roots_rows.append(
            {
                "queue_rank": promotion.queue_rank,
                "promotion_key": promotion.promotion_key,
                "promotion_name": promotion.promotion_name,
                "promotion_start_date": promotion.promotion_start_date,
                "promotion_end_date": promotion.promotion_end_date,
                "source_rows_path": promotion.source_rows_path,
                "current_queue_status": promotion.current_queue_status,
                "proposed_promotion_run_root": promotion.proposed_promotion_run_root,
                "proposed_stage_root_base": str(
                    Path(promotion.proposed_promotion_run_root) / "<stage-output-folder>"
                ),
                "planned_stage_count": len(promotion_stage_mapping.index),
                "missing_stage_mapping_count": missing_stage_mapping_count.get(
                    promotion.promotion_key,
                    0,
                ),
                "shared_root_risk_flag": shared_root_risk_flag,
                "execution_mode_safe_now_flag": execution_mode_safe_now_flag,
                "isolation_plan_status": isolation_plan_status,
                "recommended_next_step": (
                    "Add isolated input-root support to downstream stages before enabling execution mode."
                    if execution_mode_safe_now_flag == 0
                    else "Execution mode can be considered because this promotion now has a fully isolated stage chain."
                ),
            }
        )
        execution_safety_rows.append(
            {
                "plan_scope": "PROMOTION",
                "promotion_key": promotion.promotion_key,
                "promotion_name": promotion.promotion_name,
                "planned_stage_count": len(promotion_stage_mapping.index),
                "safe_stage_count": safe_stage_count,
                "unsafe_stage_count": unsafe_stage_count,
                "runtime_changes_required_count": required_runtime_changes_count,
                "missing_stage_mapping_flag": missing_stage_mapping_flag,
                "shared_root_risk_flag": shared_root_risk_flag,
                "shared_root_risk_status": (
                    "SHARED_ROOT_RISK_CONFIRMED" if shared_root_risk_flag else "NO_SHARED_ROOT_RISK"
                ),
                "execution_mode_safe_now_flag": execution_mode_safe_now_flag,
                "isolation_plan_status": isolation_plan_status,
                "recommendation": (
                    "Planner-only mode remains required until the unsafe stages stop depending on shared packet-root inputs."
                    if execution_mode_safe_now_flag == 0
                    else "Execution mode is safe for this promotion under the isolated run root contract."
                ),
            }
        )

    overall_status = _isolation_status(
        missing_stage_mapping_flag=overall_missing_stage_mapping_flag,
        required_runtime_changes_count=stages_requiring_runtime_changes,
        shared_root_risk_flag=overall_shared_root_risk_flag,
    )
    shared_root_risk_status = (
        "SHARED_ROOT_RISK_CONFIRMED"
        if overall_shared_root_risk_flag
        else "NO_SHARED_ROOT_RISK"
    )
    recommendation = (
        "Keep execution mode blocked. Route stage 1 into the isolated promotion run root immediately, then add isolated input-root or stage-root parameters to stages 2 through 15 so they stop reading upstream artifacts from shared packet-root folders."
        if overall_status == PROMOTION_ISOLATION_PLAN_READY_RUNTIME_CHANGES_REQUIRED
        else "Execution mode can be considered because the isolated promotion run roots cover all stage inputs and outputs safely."
        if overall_status == PROMOTION_ISOLATION_READY
        else "Repair the missing stage mappings before deciding whether isolated multi-promotion execution is safe."
    )

    execution_safety_rows.append(
        {
            "plan_scope": "OVERALL",
            "promotion_key": "ALL_SELECTED_INCOMPLETE_PROMOTIONS",
            "promotion_name": "ALL_SELECTED_INCOMPLETE_PROMOTIONS",
            "planned_stage_count": len(selected_promotions) * len(STAGE_SPECS),
            "safe_stage_count": int(
                stage_mapping_frame.get(
                    "safe_for_multi_promotion_execution_flag", pd.Series(dtype="int64")
                )
                .map(_to_int)
                .eq(1)
                .sum()
            ),
            "unsafe_stage_count": int(
                stage_mapping_frame.get(
                    "safe_for_multi_promotion_execution_flag", pd.Series(dtype="int64")
                )
                .map(_to_int)
                .eq(0)
                .sum()
            ),
            "runtime_changes_required_count": stages_requiring_runtime_changes,
            "missing_stage_mapping_flag": overall_missing_stage_mapping_flag,
            "shared_root_risk_flag": overall_shared_root_risk_flag,
            "shared_root_risk_status": shared_root_risk_status,
            "execution_mode_safe_now_flag": overall_execution_mode_safe_now_flag,
            "isolation_plan_status": overall_status,
            "recommendation": recommendation,
        }
    )

    roots_frame = pd.DataFrame(roots_rows, columns=ROOTS_COLUMNS)
    execution_safety_frame = pd.DataFrame(
        execution_safety_rows,
        columns=EXECUTION_SAFETY_COLUMNS,
    )
    summary_frame = pd.DataFrame(
        [
            _summary_row(
                "ISOLATION_PLAN_STATUS",
                overall_status,
                "Overall diagnostics-only promotion-isolated artifact-root planner status.",
            ),
            _summary_row(
                "SOURCE_MATERIALIZED_PROMOTION_COUNT",
                source_materialized_promotion_count,
                "Source-materialized promotion folders detected under source_materialized_promotions.",
            ),
            _summary_row(
                "INCOMPLETE_PROMOTION_COUNT",
                incomplete_promotion_count,
                "Incomplete promotions inherited from the multi-promotion reconstruction queue.",
            ),
            _summary_row(
                "ISOLATED_ROOTS_PLANNED",
                len(selected_promotions),
                "Promotion-specific run roots planned under promotion_runs.",
            ),
            _summary_row(
                "STAGES_MAPPED_PER_PROMOTION",
                stages_mapped_per_promotion,
                "Stage mappings planned for each selected incomplete promotion.",
            ),
            _summary_row(
                "STAGES_REQUIRING_RUNTIME_CHANGES",
                stages_requiring_runtime_changes,
                "Stages that still need runtime changes before isolated multi-promotion execution is safe.",
            ),
            _summary_row(
                "SHARED_ROOT_RISK_STATUS",
                shared_root_risk_status,
                "Whether shared packet-root stage dependencies still make multi-promotion execution unsafe.",
            ),
            _summary_row(
                "EXECUTION_MODE_SAFE_NOW",
                overall_execution_mode_safe_now_flag,
                "Whether execution mode is safe now under the proposed isolation contract.",
            ),
            _summary_row(
                "CURRENT_QUEUE_STATUS",
                _normalize_text(queue_summary_metrics.get("QUEUE_STATUS", "")),
                "Current multi-promotion reconstruction queue status.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Promotion Isolation Plan",
            "",
            "This is a diagnostics-only promotion-isolated artifact-root planner.",
            "This does not execute downstream stages.",
            "This does not start training.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "This does not promote auto-ordering.",
            "This does not promote shadow rules.",
            "This does not run recalibration.",
            "This does not run shadow-vs-baseline simulation.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "",
            f"Isolation plan status: {overall_status}",
            f"Source-materialised promotion count: {source_materialized_promotion_count}",
            f"Incomplete promotion count: {incomplete_promotion_count}",
            f"Isolated roots planned: {len(selected_promotions)}",
            f"Stages mapped per promotion: {stages_mapped_per_promotion}",
            f"Stages requiring runtime changes: {stages_requiring_runtime_changes}",
            f"Shared-root risk status: {shared_root_risk_status}",
            f"Execution mode safe now: {overall_execution_mode_safe_now_flag}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()

    return PromotionsMaterializedSourcePromotionIsolationPlanResult(
        isolation_plan_status=overall_status,
        source_materialized_promotion_count=source_materialized_promotion_count,
        incomplete_promotion_count=incomplete_promotion_count,
        isolated_roots_planned=len(selected_promotions),
        stages_mapped_per_promotion=stages_mapped_per_promotion,
        stages_requiring_runtime_changes=stages_requiring_runtime_changes,
        shared_root_risk_status=shared_root_risk_status,
        execution_mode_safe_now_flag=overall_execution_mode_safe_now_flag,
        recommendation=recommendation,
        roots_frame=roots_frame,
        stage_mapping_frame=stage_mapping_frame,
        required_runtime_changes_frame=required_runtime_changes_frame,
        execution_safety_frame=execution_safety_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_promotion_isolation_plan(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    promotion_key: str | None = None,
    max_promotions: int | None = None,
) -> PromotionsMaterializedSourcePromotionIsolationPlanArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = (
        Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    )
    result = build_promotions_materialized_source_promotion_isolation_plan(
        packet_root=packet_root_path,
        promotion_key=promotion_key,
        max_promotions=max_promotions,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    roots_csv_path = output_root_path / "promotion_isolation_plan_roots.csv"
    stage_mapping_csv_path = output_root_path / "promotion_isolation_plan_stage_mapping.csv"
    required_runtime_changes_csv_path = (
        output_root_path / "promotion_isolation_plan_required_runtime_changes.csv"
    )
    execution_safety_csv_path = (
        output_root_path / "promotion_isolation_plan_execution_safety.csv"
    )
    summary_csv_path = output_root_path / "promotion_isolation_plan_summary.csv"
    memo_md_path = output_root_path / "promotion_isolation_plan_memo.md"

    result.roots_frame.to_csv(roots_csv_path, index=False)
    result.stage_mapping_frame.to_csv(stage_mapping_csv_path, index=False)
    result.required_runtime_changes_frame.to_csv(
        required_runtime_changes_csv_path,
        index=False,
    )
    result.execution_safety_frame.to_csv(execution_safety_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourcePromotionIsolationPlanArtifacts(
        output_root=str(output_root_path),
        roots_csv_path=str(roots_csv_path),
        stage_mapping_csv_path=str(stage_mapping_csv_path),
        required_runtime_changes_csv_path=str(required_runtime_changes_csv_path),
        execution_safety_csv_path=str(execution_safety_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
        isolation_plan_status=result.isolation_plan_status,
        source_materialized_promotion_count=result.source_materialized_promotion_count,
        incomplete_promotion_count=result.incomplete_promotion_count,
        isolated_roots_planned=result.isolated_roots_planned,
        stages_mapped_per_promotion=result.stages_mapped_per_promotion,
        stages_requiring_runtime_changes=result.stages_requiring_runtime_changes,
        shared_root_risk_status=result.shared_root_risk_status,
        execution_mode_safe_now_flag=result.execution_mode_safe_now_flag,
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only promotion-isolated artifact root planner."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--promotion-key")
    parser.add_argument("--max-promotions", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_promotion_isolation_plan(
        packet_root=args.packet_root,
        output_root=args.output_root,
        promotion_key=args.promotion_key,
        max_promotions=args.max_promotions,
    )
    print("isolation_plan_status", artifacts.isolation_plan_status)
    print("source_materialized_promotion_count", artifacts.source_materialized_promotion_count)
    print("incomplete_promotion_count", artifacts.incomplete_promotion_count)
    print("isolated_roots_planned", artifacts.isolated_roots_planned)
    print("stages_mapped_per_promotion", artifacts.stages_mapped_per_promotion)
    print("stages_requiring_runtime_changes", artifacts.stages_requiring_runtime_changes)
    print("shared_root_risk_status", artifacts.shared_root_risk_status)
    print("execution_mode_safe_now", artifacts.execution_mode_safe_now_flag)
    print("recommendation", artifacts.recommendation)
    print("promotion_isolation_plan_roots", artifacts.roots_csv_path)
    print("promotion_isolation_plan_stage_mapping", artifacts.stage_mapping_csv_path)
    print(
        "promotion_isolation_plan_required_runtime_changes",
        artifacts.required_runtime_changes_csv_path,
    )
    print(
        "promotion_isolation_plan_execution_safety",
        artifacts.execution_safety_csv_path,
    )
    print("promotion_isolation_plan_summary", artifacts.summary_csv_path)
    print("promotion_isolation_plan_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())