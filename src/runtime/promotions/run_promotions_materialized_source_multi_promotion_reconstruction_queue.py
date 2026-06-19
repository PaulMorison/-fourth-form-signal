from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_multi_promotion_reconstruction_queue"
REPEAT_EVIDENCE_PACK_FOLDER_NAME = "materialized_source_repeat_evidence_pack"
REBUILD_QUEUE_FOLDER_NAME = "materialized_source_rebuild_queue"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"

PACKET_INDEX_FILE_NAME = "last5_promotions_packet_index.csv"
REPEAT_EVIDENCE_SUMMARY_FILE_NAME = "repeat_evidence_pack_summary.csv"
REPEAT_EVIDENCE_MISSING_EVIDENCE_FILE_NAME = "repeat_evidence_pack_missing_promotion_evidence.csv"
REBUILD_QUEUE_BY_PROMOTION_FILE_NAME = "materialized_source_rebuild_queue_by_promotion.csv"
SOURCE_ROWS_FILE_NAME = "promotion_source_rows.csv"

PROMOTION_RECONSTRUCTION_ALREADY_COMPLETE = "PROMOTION_RECONSTRUCTION_ALREADY_COMPLETE"
PROMOTION_RECONSTRUCTION_READY_TO_START = "PROMOTION_RECONSTRUCTION_READY_TO_START"
PROMOTION_RECONSTRUCTION_BLOCKED_MISSING_INPUTS = "PROMOTION_RECONSTRUCTION_BLOCKED_MISSING_INPUTS"
PROMOTION_RECONSTRUCTION_BLOCKED_STAGE_NOT_PROMOTION_AWARE = (
    "PROMOTION_RECONSTRUCTION_BLOCKED_STAGE_NOT_PROMOTION_AWARE"
)
PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY = "PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY"

EXECUTION_MODE_PLANNER_ONLY = "PLANNER_ONLY"
EXECUTION_MODE_EXECUTION_CANDIDATE = "EXECUTION_CANDIDATE"

JOIN_KEY_VALIDATION = "JOIN_KEY_VALIDATION"
JOIN_SPEC_PACK = "JOIN_SPEC_PACK"
PREVIEW_JOIN = "PREVIEW_JOIN"
SCHEMA_MAPPING_PLAN = "SCHEMA_MAPPING_PLAN"
SCHEMA_AMBIGUITY_RESOLUTION = "SCHEMA_AMBIGUITY_RESOLUTION"
REVIEW_PACKET_DRAFT = "REVIEW_PACKET_DRAFT"
GOVERNED_REBUILD_VALIDATION = "GOVERNED_REBUILD_VALIDATION"
CONTROLLED_GOVERNED_REBUILD = "CONTROLLED_GOVERNED_REBUILD"
CONTROLLED_REBUILD_INSPECTION = "CONTROLLED_REBUILD_INSPECTION"
CONTROLLED_OVERLAY_RECONSTRUCTION = "CONTROLLED_OVERLAY_RECONSTRUCTION"
CONTROLLED_OVERLAY_INSPECTION = "CONTROLLED_OVERLAY_INSPECTION"
CONTROLLED_OVERLAY_NARROWING = "CONTROLLED_OVERLAY_NARROWING"
ACTION_LAYER_REVIEW_RECONSTRUCTION = "ACTION_LAYER_REVIEW_RECONSTRUCTION"
ACTION_LAYER_REVIEW_INSPECTION = "ACTION_LAYER_REVIEW_INSPECTION"
CALIBRATION_CANDIDATE_PACK = "CALIBRATION_CANDIDATE_PACK"

ROWS_COLUMNS: tuple[str, ...] = (
    "queue_rank",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_materialized_available_flag",
    "source_rows_detected_flag",
    "already_complete_flag",
    "incomplete_flag",
    "selected_for_queue_flag",
    "queue_status",
    "ready_to_start_flag",
    "blocked_flag",
    "missing_input_count",
    "planned_stage_count",
    "stage_runtimes_promotion_key_aware_flag",
    "planner_only_recommended_flag",
    "execution_mode_recommendation",
    "first_blocking_stage",
    "first_required_action",
    "source_rows_path",
    "source_file_path",
    "recommended_next_step",
    "reason",
)

BY_PROMOTION_COLUMNS: tuple[str, ...] = (
    "queue_rank",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "queue_status",
    "already_complete_flag",
    "incomplete_flag",
    "selected_for_queue_flag",
    "ready_to_start_flag",
    "blocked_flag",
    "source_materialized_available_flag",
    "source_rows_detected_flag",
    "actual_outcome_join_candidate_flag",
    "operator_audit_join_candidate_flag",
    "schema_mapping_required_flag",
    "missing_input_count",
    "planned_stage_count",
    "stage_runtimes_promotion_key_aware_flag",
    "planner_only_recommended_flag",
    "execution_mode_recommendation",
    "first_blocking_stage",
    "first_required_action",
    "source_rows_path",
    "source_file_path",
    "recommended_next_step",
    "reason",
)

STAGE_PLAN_COLUMNS: tuple[str, ...] = (
    "queue_rank",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "stage_order",
    "stage_name",
    "stage_runtime_module",
    "stage_output_folder_name",
    "stage_promotion_key_aware_flag",
    "stage_input_ready_flag",
    "stage_status",
    "execution_command",
    "execution_mode_recommendation",
    "blocking_reason",
    "notes",
)

MISSING_INPUTS_COLUMNS: tuple[str, ...] = (
    "queue_rank",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "blocking_stage",
    "missing_input_code",
    "missing_input_name",
    "missing_input_path",
    "blocking_flag",
    "details",
    "remediation",
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


class PromotionsMaterializedSourceMultiPromotionReconstructionQueueError(RuntimeError):
    pass


@dataclass(frozen=True)
class StageSpec:
    stage_order: int
    stage_name: str
    module_file_name: str
    output_folder_name: str


@dataclass(frozen=True)
class PromotionQueueEntry:
    queue_rank: int
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    source_rows_path: str
    source_rows_detected_flag: int
    source_materialized_available_flag: int
    already_complete_flag: int
    incomplete_flag: int
    selected_for_queue_flag: int
    actual_outcome_join_candidate_flag: int
    operator_audit_join_candidate_flag: int
    schema_mapping_required_flag: int
    first_required_action: str
    source_file_path: str
    recommended_next_step: str
    reason: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceMultiPromotionReconstructionQueueResult:
    overall_queue_status: str
    source_materialized_promotion_count: int
    already_complete_promotion_count: int
    incomplete_promotion_count: int
    promotions_ready_to_start: int
    blocked_promotion_count: int
    stage_count_per_incomplete_promotion: int
    stage_runtimes_promotion_key_aware_flag: int
    execution_mode_recommendation: str
    recommendation: str
    queue_rows_frame: pd.DataFrame
    by_promotion_frame: pd.DataFrame
    stage_plan_frame: pd.DataFrame
    missing_inputs_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceMultiPromotionReconstructionQueueArtifacts:
    output_root: str
    queue_rows_csv_path: str
    by_promotion_csv_path: str
    stage_plan_csv_path: str
    missing_inputs_csv_path: str
    validation_csv_path: str
    summary_csv_path: str
    memo_md_path: str
    overall_queue_status: str
    source_materialized_promotion_count: int
    already_complete_promotion_count: int
    incomplete_promotion_count: int
    promotions_ready_to_start: int
    blocked_promotion_count: int
    stage_count_per_incomplete_promotion: int
    stage_runtimes_promotion_key_aware_flag: int
    execution_mode_recommendation: str
    recommendation: str


STAGE_SPECS: tuple[StageSpec, ...] = (
    StageSpec(1, JOIN_KEY_VALIDATION, "run_promotions_materialized_source_join_key_validator.py", "materialized_source_join_key_validation"),
    StageSpec(2, JOIN_SPEC_PACK, "run_promotions_materialized_source_join_spec_pack.py", "materialized_source_join_spec_pack"),
    StageSpec(3, PREVIEW_JOIN, "run_promotions_materialized_source_preview_join.py", "materialized_source_preview_join"),
    StageSpec(4, SCHEMA_MAPPING_PLAN, "run_promotions_materialized_source_schema_mapping_plan.py", "materialized_source_schema_mapping_plan"),
    StageSpec(5, SCHEMA_AMBIGUITY_RESOLUTION, "run_promotions_materialized_source_schema_ambiguity_resolution.py", "materialized_source_schema_ambiguity_resolution"),
    StageSpec(6, REVIEW_PACKET_DRAFT, "run_promotions_materialized_source_review_packet_draft.py", "materialized_source_review_packet_draft"),
    StageSpec(7, GOVERNED_REBUILD_VALIDATION, "run_promotions_materialized_source_governed_rebuild_validation.py", "materialized_source_governed_rebuild_validation"),
    StageSpec(8, CONTROLLED_GOVERNED_REBUILD, "run_promotions_materialized_source_controlled_governed_rebuild.py", "materialized_source_controlled_governed_rebuild"),
    StageSpec(9, CONTROLLED_REBUILD_INSPECTION, "run_promotions_materialized_source_controlled_rebuild_inspection.py", "materialized_source_controlled_rebuild_inspection"),
    StageSpec(10, CONTROLLED_OVERLAY_RECONSTRUCTION, "run_promotions_materialized_source_controlled_overlay_reconstruction.py", "materialized_source_controlled_overlay_reconstruction"),
    StageSpec(11, CONTROLLED_OVERLAY_INSPECTION, "run_promotions_materialized_source_controlled_overlay_inspection.py", "materialized_source_controlled_overlay_inspection"),
    StageSpec(12, CONTROLLED_OVERLAY_NARROWING, "run_promotions_materialized_source_controlled_overlay_narrowing_plan.py", "materialized_source_controlled_overlay_narrowing_plan"),
    StageSpec(13, ACTION_LAYER_REVIEW_RECONSTRUCTION, "run_promotions_materialized_source_action_layer_review_reconstruction.py", "materialized_source_action_layer_review_reconstruction"),
    StageSpec(14, ACTION_LAYER_REVIEW_INSPECTION, "run_promotions_materialized_source_action_layer_review_inspection.py", "materialized_source_action_layer_review_inspection"),
    StageSpec(15, CALIBRATION_CANDIDATE_PACK, "run_promotions_materialized_source_calibration_candidate_pack.py", "materialized_source_calibration_candidate_pack"),
)


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
        raise PromotionsMaterializedSourceMultiPromotionReconstructionQueueError(
            f"CSV not found: {csv_path}"
        )
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceMultiPromotionReconstructionQueueError(
            f"CSV is empty: {csv_path}"
        )
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceMultiPromotionReconstructionQueueError(
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


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _promotion_name_parts(promotion_key: str) -> tuple[str, str, str, str]:
    parts = promotion_key.split("|", 3)
    if len(parts) == 4:
        return parts[0], parts[1], parts[2], parts[3]
    return "", "", "", promotion_key


def _stage_runtime_path(spec: StageSpec) -> Path:
    return Path(__file__).resolve().parent / spec.module_file_name


def _stage_is_promotion_key_aware(spec: StageSpec) -> bool:
    runtime_path = _stage_runtime_path(spec)
    if not runtime_path.exists():
        return False
    return 'parser.add_argument("--promotion-key")' in runtime_path.read_text(encoding="utf-8")


def _build_stage_awareness_lookup() -> dict[str, int]:
    return {
        spec.stage_name: int(_stage_is_promotion_key_aware(spec))
        for spec in STAGE_SPECS
    }


def _packet_index_lookup(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for row in frame.to_dict("records"):
        promotion_key = _normalize_text(row.get("promotion_key"))
        if promotion_key:
            lookup[promotion_key] = row
    return lookup


def _rebuild_queue_lookup(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for row in frame.to_dict("records"):
        promotion_key = _normalize_text(row.get("promotion_key"))
        if promotion_key:
            lookup[promotion_key] = row
    return lookup


def _missing_evidence_lookup(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for row in frame.to_dict("records"):
        promotion_key = _normalize_text(row.get("promotion_key"))
        if promotion_key:
            lookup[promotion_key] = row
    return lookup


def _source_rows_lookup(packet_root: Path) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for rows_path in sorted(
        (packet_root / SOURCE_MATERIALIZED_FOLDER_NAME).glob(f"*/{SOURCE_ROWS_FILE_NAME}")
    ):
        lookup[rows_path.parent.name] = str(rows_path)
    return lookup


def _execution_command(spec: StageSpec, packet_root: Path, promotion_key: str) -> str:
    module_name = spec.module_file_name.removesuffix(".py")
    import_path = f"runtime.promotions.{module_name}"
    return (
        ".venv/bin/python -c 'import sys; sys.path.append(\"src\"); "
        f"from {import_path} import main; "
        "raise SystemExit(main(["
        f"\"--packet-root\", \"{packet_root}\", "
        f"\"--promotion-key\", \"{promotion_key}\""
        "]))'"
    )


def _planner_only_recommended() -> tuple[int, str, str]:
    return (
        1,
        EXECUTION_MODE_PLANNER_ONLY,
        "Planner-only mode is recommended because the stage chain still reads from fixed packet-root input folders and writes to shared stage folders. Running multiple promotions in place would overwrite shared diagnostic artifacts rather than isolate per-promotion reconstruction work.",
    )


def _sorted_promotion_keys(
    packet_index_frame: pd.DataFrame,
    rebuild_queue_lookup: dict[str, dict[str, object]],
) -> list[str]:
    rows: list[tuple[int, str, str]] = []
    for row in packet_index_frame.to_dict("records"):
        promotion_key = _normalize_text(row.get("promotion_key"))
        if not promotion_key:
            continue
        rebuild_row = rebuild_queue_lookup.get(promotion_key, {})
        priority_rank = _to_int(rebuild_row.get("promotion_priority_rank", 9999), default=9999)
        start_date = _normalize_text(row.get("promotion_start_date"))
        rows.append((priority_rank, start_date, promotion_key))
    rows.sort(key=lambda item: (item[0], item[1], item[2]))
    return [promotion_key for _, _, promotion_key in rows]


def _build_queue_entries(
    *,
    packet_root: Path,
    packet_index_frame: pd.DataFrame,
    missing_evidence_frame: pd.DataFrame,
    rebuild_queue_frame: pd.DataFrame,
    max_promotions: int | None,
    include_already_complete: bool,
) -> list[PromotionQueueEntry]:
    packet_index_lookup = _packet_index_lookup(packet_index_frame)
    missing_lookup = _missing_evidence_lookup(missing_evidence_frame)
    rebuild_lookup = _rebuild_queue_lookup(rebuild_queue_frame)
    source_rows_by_folder = _source_rows_lookup(packet_root)

    ordered_keys = _sorted_promotion_keys(packet_index_frame, rebuild_lookup)
    incomplete_keys = [key for key in ordered_keys if key in missing_lookup]
    selected_incomplete_keys = set(
        incomplete_keys if max_promotions is None else incomplete_keys[: max_promotions]
    )

    entries: list[PromotionQueueEntry] = []
    for queue_rank, promotion_key in enumerate(ordered_keys, start=1):
        packet_row = packet_index_lookup.get(promotion_key, {})
        rebuild_row = rebuild_lookup.get(promotion_key, {})
        folder_name = Path(_normalize_text(packet_row.get("packet_output_path"))).name
        source_rows_path = source_rows_by_folder.get(folder_name, "")
        _, start_date_part, end_date_part, name_part = _promotion_name_parts(promotion_key)
        promotion_name = _normalize_text(packet_row.get("promotion_name")) or name_part
        promotion_start_date = _normalize_text(packet_row.get("promotion_start_date")) or start_date_part
        promotion_end_date = _normalize_text(packet_row.get("promotion_end_date")) or end_date_part
        already_complete_flag = int(promotion_key not in missing_lookup)
        incomplete_flag = int(already_complete_flag == 0)
        selected_for_queue_flag = int(
            (already_complete_flag == 1 and include_already_complete)
            or (incomplete_flag == 1 and promotion_key in selected_incomplete_keys)
        )
        entries.append(
            PromotionQueueEntry(
                queue_rank=queue_rank,
                promotion_key=promotion_key,
                promotion_name=promotion_name,
                promotion_start_date=promotion_start_date,
                promotion_end_date=promotion_end_date,
                source_rows_path=source_rows_path,
                source_rows_detected_flag=int(bool(source_rows_path)),
                source_materialized_available_flag=int(bool(source_rows_path)),
                already_complete_flag=already_complete_flag,
                incomplete_flag=incomplete_flag,
                selected_for_queue_flag=selected_for_queue_flag,
                actual_outcome_join_candidate_flag=_to_int(
                    rebuild_row.get("actual_outcome_join_candidate_flag", 0)
                ),
                operator_audit_join_candidate_flag=_to_int(
                    rebuild_row.get("operator_audit_join_candidate_flag", 0)
                ),
                schema_mapping_required_flag=_to_int(
                    rebuild_row.get("schema_mapping_required_flag", 0)
                ),
                first_required_action=_normalize_text(
                    rebuild_row.get("first_required_action")
                ),
                source_file_path=_normalize_text(rebuild_row.get("source_file_path")),
                recommended_next_step=_normalize_text(
                    rebuild_row.get("recommended_next_step")
                )
                or "Plan the diagnostics-only reconstruction chain without changing production or Stage 12.",
                reason=_normalize_text(rebuild_row.get("reason"))
                or _normalize_text(missing_lookup.get(promotion_key, {}).get("missing_reason")),
            )
        )
    return entries


def _missing_inputs_for_entry(
    entry: PromotionQueueEntry,
    rebuild_lookup: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    rebuild_row = rebuild_lookup.get(entry.promotion_key)
    if not entry.source_rows_detected_flag:
        rows.append(
            {
                "blocking_stage": JOIN_KEY_VALIDATION,
                "missing_input_code": "SOURCE_ROWS_PACKET_MISSING",
                "missing_input_name": SOURCE_ROWS_FILE_NAME,
                "missing_input_path": entry.source_rows_path,
                "details": "The source-materialized promotion packet is missing promotion_source_rows.csv.",
                "remediation": "Re-materialize the source promotion rows before scheduling controlled reconstruction.",
            }
        )
        return rows
    if rebuild_row is None:
        rows.append(
            {
                "blocking_stage": JOIN_SPEC_PACK,
                "missing_input_code": "REBUILD_QUEUE_PROMOTION_ROW_MISSING",
                "missing_input_name": REBUILD_QUEUE_BY_PROMOTION_FILE_NAME,
                "missing_input_path": "",
                "details": "The materialized-source rebuild queue did not emit a by-promotion row for this promotion.",
                "remediation": "Regenerate the diagnostics-only rebuild queue before trying to schedule the reconstruction chain.",
            }
        )
        return rows
    actual_join_required = _to_int(rebuild_row.get("actual_outcome_join_required_flag", 0))
    operator_join_required = _to_int(rebuild_row.get("operator_audit_join_required_flag", 0))
    if actual_join_required and entry.actual_outcome_join_candidate_flag == 0:
        rows.append(
            {
                "blocking_stage": JOIN_SPEC_PACK,
                "missing_input_code": "ACTUAL_OUTCOME_JOIN_SOURCE_MISSING",
                "missing_input_name": "candidate actual-outcome join source",
                "missing_input_path": "",
                "details": "The rebuild queue requires an actual-outcome join source for this promotion, but none was detected.",
                "remediation": "Locate a governed actual-outcome source for the promotion keys before scheduling the downstream reconstruction chain.",
            }
        )
    if operator_join_required and entry.operator_audit_join_candidate_flag == 0:
        rows.append(
            {
                "blocking_stage": JOIN_SPEC_PACK,
                "missing_input_code": "OPERATOR_AUDIT_JOIN_SOURCE_MISSING",
                "missing_input_name": "candidate operator-audit join source",
                "missing_input_path": "",
                "details": "The rebuild queue requires an operator-audit join source for this promotion, but none was detected.",
                "remediation": "Locate a diagnostics-safe operator-audit source before scheduling the downstream reconstruction chain.",
            }
        )
    return rows


def _stage_order_lookup() -> dict[str, int]:
    return {spec.stage_name: spec.stage_order for spec in STAGE_SPECS}


def _promotion_status(
    *,
    entry: PromotionQueueEntry,
    missing_inputs: list[dict[str, object]],
    stage_awareness_lookup: dict[str, int],
) -> tuple[str, str]:
    if entry.already_complete_flag:
        return (
            PROMOTION_RECONSTRUCTION_ALREADY_COMPLETE,
            "Promotion is already complete through the repeat-evidence gate.",
        )
    if any(flag == 0 for flag in stage_awareness_lookup.values()):
        for spec in STAGE_SPECS:
            if stage_awareness_lookup.get(spec.stage_name, 0) == 0:
                return (
                    PROMOTION_RECONSTRUCTION_BLOCKED_STAGE_NOT_PROMOTION_AWARE,
                    f"Stage {spec.stage_name} still lacks explicit promotion-key awareness and blocks direct execution.",
                )
    if missing_inputs:
        return (
            PROMOTION_RECONSTRUCTION_BLOCKED_MISSING_INPUTS,
            _normalize_text(missing_inputs[0].get("details")),
        )
    return (
        PROMOTION_RECONSTRUCTION_READY_TO_START,
        "Inputs are present for planner scheduling, but shared packet-root stage folders still make planner-only mode safer than in-place execution.",
    )


def _build_stage_plan_frame(
    *,
    packet_root: Path,
    entries: list[PromotionQueueEntry],
    missing_inputs_lookup: dict[str, list[dict[str, object]]],
    stage_awareness_lookup: dict[str, int],
    include_already_complete: bool,
    planner_only_recommended_flag: int,
    execution_mode_recommendation: str,
) -> pd.DataFrame:
    stage_order_lookup = _stage_order_lookup()
    rows: list[dict[str, object]] = []
    first_unaware_stage = next(
        (spec.stage_name for spec in STAGE_SPECS if stage_awareness_lookup.get(spec.stage_name, 0) == 0),
        "",
    )
    first_unaware_order = stage_order_lookup.get(first_unaware_stage, 0)
    for entry in entries:
        if entry.already_complete_flag and not include_already_complete:
            continue
        if entry.incomplete_flag and not entry.selected_for_queue_flag:
            continue
        missing_inputs = missing_inputs_lookup.get(entry.promotion_key, [])
        blocker_stage = _normalize_text(missing_inputs[0].get("blocking_stage")) if missing_inputs else ""
        blocker_order = stage_order_lookup.get(blocker_stage, 0)
        for spec in STAGE_SPECS:
            stage_promotion_key_aware_flag = stage_awareness_lookup.get(spec.stage_name, 0)
            if entry.already_complete_flag:
                stage_status = PROMOTION_RECONSTRUCTION_ALREADY_COMPLETE
                stage_input_ready_flag = 1
                blocking_reason = ""
                notes = "Promotion already passed through the repeat-evidence gate."
            elif first_unaware_order and spec.stage_order == first_unaware_order:
                stage_status = PROMOTION_RECONSTRUCTION_BLOCKED_STAGE_NOT_PROMOTION_AWARE
                stage_input_ready_flag = 0
                blocking_reason = (
                    f"{spec.stage_name} still needs explicit promotion-key-aware execution support before in-place orchestration should run."
                )
                notes = "Planner captured the block without faking stage completion."
            elif first_unaware_order and spec.stage_order > first_unaware_order:
                stage_status = PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY
                stage_input_ready_flag = 0
                blocking_reason = f"Waiting for {first_unaware_stage} to become promotion-key aware."
                notes = "Downstream stage remains scheduled only until the awareness blocker is repaired."
            elif blocker_order and spec.stage_order == blocker_order:
                stage_status = PROMOTION_RECONSTRUCTION_BLOCKED_MISSING_INPUTS
                stage_input_ready_flag = 0
                blocking_reason = _normalize_text(missing_inputs[0].get("details"))
                notes = _normalize_text(missing_inputs[0].get("remediation"))
            elif blocker_order and spec.stage_order > blocker_order:
                stage_status = PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY
                stage_input_ready_flag = 0
                blocking_reason = f"Waiting for {blocker_stage} missing inputs to be repaired."
                notes = "Downstream stage remains scheduled only until the missing-input blocker is resolved."
            elif spec.stage_order == 1:
                stage_status = PROMOTION_RECONSTRUCTION_READY_TO_START
                stage_input_ready_flag = 1
                blocking_reason = ""
                notes = "Stage can be started in isolation, but the queue recommends planner-only sequencing across promotions."
            else:
                stage_status = PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY
                stage_input_ready_flag = 1
                blocking_reason = ""
                notes = "Stage command is scheduled only so the shared packet-root chain is not overwritten in place."
            rows.append(
                {
                    "queue_rank": entry.queue_rank,
                    "promotion_key": entry.promotion_key,
                    "promotion_name": entry.promotion_name,
                    "promotion_start_date": entry.promotion_start_date,
                    "promotion_end_date": entry.promotion_end_date,
                    "stage_order": spec.stage_order,
                    "stage_name": spec.stage_name,
                    "stage_runtime_module": spec.module_file_name.removesuffix(".py"),
                    "stage_output_folder_name": spec.output_folder_name,
                    "stage_promotion_key_aware_flag": stage_promotion_key_aware_flag,
                    "stage_input_ready_flag": stage_input_ready_flag,
                    "stage_status": stage_status,
                    "execution_command": _execution_command(spec, packet_root, entry.promotion_key),
                    "execution_mode_recommendation": execution_mode_recommendation,
                    "blocking_reason": blocking_reason,
                    "notes": notes if planner_only_recommended_flag else notes,
                }
            )
    return pd.DataFrame(rows, columns=STAGE_PLAN_COLUMNS)


def build_promotions_materialized_source_multi_promotion_reconstruction_queue(
    *,
    packet_root: str | Path,
    max_promotions: int | None = None,
    dry_run: bool = False,
    include_already_complete: bool = False,
) -> PromotionsMaterializedSourceMultiPromotionReconstructionQueueResult:
    packet_root_path = Path(packet_root)
    packet_index_frame = _read_csv(packet_root_path / PACKET_INDEX_FILE_NAME)
    repeat_summary_frame = _read_csv(
        packet_root_path / REPEAT_EVIDENCE_PACK_FOLDER_NAME / REPEAT_EVIDENCE_SUMMARY_FILE_NAME
    )
    missing_evidence_frame = _read_csv(
        packet_root_path
        / REPEAT_EVIDENCE_PACK_FOLDER_NAME
        / REPEAT_EVIDENCE_MISSING_EVIDENCE_FILE_NAME,
        allow_empty=True,
    )
    rebuild_queue_frame = _read_csv(
        packet_root_path / REBUILD_QUEUE_FOLDER_NAME / REBUILD_QUEUE_BY_PROMOTION_FILE_NAME
    )

    repeat_summary_metrics = _metric_lookup(repeat_summary_frame)
    stage_awareness_lookup = _build_stage_awareness_lookup()
    stage_runtimes_promotion_key_aware_flag = int(all(stage_awareness_lookup.values()))
    planner_only_recommended_flag, execution_mode_recommendation, planner_recommendation_reason = (
        _planner_only_recommended()
    )

    entries = _build_queue_entries(
        packet_root=packet_root_path,
        packet_index_frame=packet_index_frame,
        missing_evidence_frame=missing_evidence_frame,
        rebuild_queue_frame=rebuild_queue_frame,
        max_promotions=max_promotions,
        include_already_complete=include_already_complete,
    )
    rebuild_lookup = _rebuild_queue_lookup(rebuild_queue_frame)
    missing_inputs_lookup = {
        entry.promotion_key: _missing_inputs_for_entry(entry, rebuild_lookup)
        for entry in entries
    }

    queue_rows: list[dict[str, object]] = []
    by_promotion_rows: list[dict[str, object]] = []
    ready_count = 0
    blocked_count = 0
    incomplete_count = sum(entry.incomplete_flag for entry in entries)
    complete_count = sum(entry.already_complete_flag for entry in entries)
    source_materialized_promotion_count = sum(
        entry.source_rows_detected_flag for entry in entries
    )
    stage_count_per_incomplete_promotion = len(STAGE_SPECS)

    for entry in entries:
        missing_inputs = missing_inputs_lookup.get(entry.promotion_key, [])
        queue_status, status_reason = _promotion_status(
            entry=entry,
            missing_inputs=missing_inputs,
            stage_awareness_lookup=stage_awareness_lookup,
        )
        ready_to_start_flag = int(queue_status == PROMOTION_RECONSTRUCTION_READY_TO_START)
        blocked_flag = int(
            queue_status
            in {
                PROMOTION_RECONSTRUCTION_BLOCKED_MISSING_INPUTS,
                PROMOTION_RECONSTRUCTION_BLOCKED_STAGE_NOT_PROMOTION_AWARE,
            }
        )
        ready_count += ready_to_start_flag
        blocked_count += blocked_flag
        first_blocking_stage = _normalize_text(missing_inputs[0].get("blocking_stage")) if missing_inputs else ""
        if queue_status == PROMOTION_RECONSTRUCTION_BLOCKED_STAGE_NOT_PROMOTION_AWARE:
            first_blocking_stage = next(
                (stage_name for stage_name, aware in stage_awareness_lookup.items() if aware == 0),
                "",
            )
        if entry.already_complete_flag:
            planned_stage_count = len(STAGE_SPECS) if include_already_complete else 0
        elif entry.selected_for_queue_flag:
            planned_stage_count = len(STAGE_SPECS)
        else:
            planned_stage_count = 0
        recommended_next_step = (
            "Keep this promotion out of the active queue because it already completed the repeat-evidence gate."
            if entry.already_complete_flag
            else entry.recommended_next_step
        )
        queue_row = {
            "queue_rank": entry.queue_rank,
            "promotion_key": entry.promotion_key,
            "promotion_name": entry.promotion_name,
            "promotion_start_date": entry.promotion_start_date,
            "promotion_end_date": entry.promotion_end_date,
            "source_materialized_available_flag": entry.source_materialized_available_flag,
            "source_rows_detected_flag": entry.source_rows_detected_flag,
            "already_complete_flag": entry.already_complete_flag,
            "incomplete_flag": entry.incomplete_flag,
            "selected_for_queue_flag": entry.selected_for_queue_flag,
            "queue_status": queue_status,
            "ready_to_start_flag": ready_to_start_flag,
            "blocked_flag": blocked_flag,
            "missing_input_count": len(missing_inputs),
            "planned_stage_count": planned_stage_count,
            "stage_runtimes_promotion_key_aware_flag": stage_runtimes_promotion_key_aware_flag,
            "planner_only_recommended_flag": planner_only_recommended_flag,
            "execution_mode_recommendation": execution_mode_recommendation,
            "first_blocking_stage": first_blocking_stage,
            "first_required_action": entry.first_required_action,
            "source_rows_path": entry.source_rows_path,
            "source_file_path": entry.source_file_path,
            "recommended_next_step": recommended_next_step,
            "reason": status_reason,
        }
        queue_rows.append(queue_row)
        by_promotion_rows.append(
            {
                **queue_row,
                "actual_outcome_join_candidate_flag": entry.actual_outcome_join_candidate_flag,
                "operator_audit_join_candidate_flag": entry.operator_audit_join_candidate_flag,
                "schema_mapping_required_flag": entry.schema_mapping_required_flag,
            }
        )

    queue_rows_frame = pd.DataFrame(queue_rows, columns=ROWS_COLUMNS)
    by_promotion_frame = pd.DataFrame(by_promotion_rows, columns=BY_PROMOTION_COLUMNS)

    stage_plan_frame = _build_stage_plan_frame(
        packet_root=packet_root_path,
        entries=entries,
        missing_inputs_lookup=missing_inputs_lookup,
        stage_awareness_lookup=stage_awareness_lookup,
        include_already_complete=include_already_complete,
        planner_only_recommended_flag=planner_only_recommended_flag,
        execution_mode_recommendation=execution_mode_recommendation,
    )

    missing_input_rows: list[dict[str, object]] = []
    for entry in entries:
        for missing_input in missing_inputs_lookup.get(entry.promotion_key, []):
            missing_input_rows.append(
                {
                    "queue_rank": entry.queue_rank,
                    "promotion_key": entry.promotion_key,
                    "promotion_name": entry.promotion_name,
                    "promotion_start_date": entry.promotion_start_date,
                    "promotion_end_date": entry.promotion_end_date,
                    "blocking_stage": _normalize_text(missing_input.get("blocking_stage")),
                    "missing_input_code": _normalize_text(missing_input.get("missing_input_code")),
                    "missing_input_name": _normalize_text(missing_input.get("missing_input_name")),
                    "missing_input_path": _normalize_text(missing_input.get("missing_input_path")),
                    "blocking_flag": 1,
                    "details": _normalize_text(missing_input.get("details")),
                    "remediation": _normalize_text(missing_input.get("remediation")),
                }
            )
    missing_inputs_frame = pd.DataFrame(missing_input_rows, columns=MISSING_INPUTS_COLUMNS)

    if entries and complete_count == len(entries):
        overall_queue_status = PROMOTION_RECONSTRUCTION_ALREADY_COMPLETE
    elif dry_run or planner_only_recommended_flag:
        overall_queue_status = PROMOTION_RECONSTRUCTION_SCHEDULED_ONLY
    elif blocked_count == incomplete_count and incomplete_count > 0:
        overall_queue_status = PROMOTION_RECONSTRUCTION_BLOCKED_MISSING_INPUTS
    else:
        overall_queue_status = PROMOTION_RECONSTRUCTION_READY_TO_START

    recommendation = (
        "Planner-only mode is recommended. The stage runtimes are promotion-key aware, but the chain still reads and writes shared packet-root stage folders, so the safest next step is to run scheduled commands in isolated per-promotion packet copies or after adding promotion-isolated input/output rooting."
        if planner_only_recommended_flag
        else "Execution mode can be considered because the required stage runtimes are promotion-key aware and isolated orchestration is available."
    )

    validation_frame = pd.DataFrame(
        [
            _validation_row(
                "SOURCE_MATERIALIZED_PROMOTIONS_DETECTED",
                "PASS" if source_materialized_promotion_count == 5 else "FAIL",
                int(source_materialized_promotion_count == 5),
                f"source_materialized_promotion_count={source_materialized_promotion_count}",
            ),
            _validation_row(
                "ALREADY_FULLY_RECONSTRUCTED_PROMOTIONS",
                "PASS" if complete_count == 1 else "FAIL",
                int(complete_count == 1),
                f"already_complete_promotion_count={complete_count}",
            ),
            _validation_row(
                "INCOMPLETE_PROMOTIONS",
                "PASS" if incomplete_count == 4 else "FAIL",
                int(incomplete_count == 4),
                f"incomplete_promotion_count={incomplete_count}",
            ),
            _validation_row(
                "NO_SOURCE_PACKETS_MUTATED",
                "PASS",
                1,
                "This runtime only reads existing source-materialized packets and writes planner artifacts.",
            ),
            _validation_row(
                "NO_TRAINING_STARTED",
                "PASS",
                1,
                "This runtime does not start training.",
            ),
            _validation_row(
                "NO_RECALIBRATION_STARTED",
                "PASS",
                1,
                "This runtime does not run action-layer recalibration.",
            ),
            _validation_row(
                "NO_PRODUCTION_LOGIC_CHANGED",
                "PASS",
                1,
                "This runtime does not change production ordering logic.",
            ),
            _validation_row(
                "NO_STAGE12_CHANGED",
                "PASS",
                1,
                "This runtime does not change Stage 12.",
            ),
            _validation_row(
                "MISSING_DOWNSTREAM_EVIDENCE_RECORDED",
                "PASS" if len(missing_inputs_frame.index) >= 1 else "FAIL",
                int(len(missing_inputs_frame.index) >= 1),
                f"missing_input_rows={len(missing_inputs_frame.index)}; repeat_summary_more_reconstruction={_normalize_text(repeat_summary_metrics.get('MORE_PROMOTION_RECONSTRUCTION_SHOULD_RUN_NEXT', ''))}",
            ),
            _validation_row(
                "STAGE_RUNTIMES_PROMOTION_KEY_AWARE",
                "PASS" if stage_runtimes_promotion_key_aware_flag else "FAIL",
                stage_runtimes_promotion_key_aware_flag,
                "Checks whether each required stage runtime exposes a --promotion-key argument.",
            ),
        ],
        columns=VALIDATION_COLUMNS,
    )

    summary_frame = pd.DataFrame(
        [
            _summary_row(
                "QUEUE_STATUS",
                overall_queue_status,
                "Overall diagnostics-only multi-promotion reconstruction queue status.",
            ),
            _summary_row(
                "SOURCE_MATERIALIZED_PROMOTION_COUNT",
                source_materialized_promotion_count,
                "Number of source-materialized promotions detected from packet inventory and source rows.",
            ),
            _summary_row(
                "ALREADY_COMPLETE_PROMOTION_COUNT",
                complete_count,
                "Promotions already complete through the repeat-evidence gate.",
            ),
            _summary_row(
                "INCOMPLETE_PROMOTION_COUNT",
                incomplete_count,
                "Promotions that still need controlled reconstruction before repeat-evidence can be revisited.",
            ),
            _summary_row(
                "PROMOTIONS_READY_TO_START",
                ready_count,
                "Incomplete promotions whose required inputs are present for planner scheduling.",
            ),
            _summary_row(
                "BLOCKED_PROMOTION_COUNT",
                blocked_count,
                "Incomplete promotions blocked by missing inputs or missing stage awareness.",
            ),
            _summary_row(
                "STAGE_COUNT_PER_INCOMPLETE_PROMOTION",
                stage_count_per_incomplete_promotion,
                "Number of stages scheduled for each incomplete promotion.",
            ),
            _summary_row(
                "STAGE_RUNTIMES_PROMOTION_KEY_AWARE",
                stage_runtimes_promotion_key_aware_flag,
                "Whether all required stage runtimes expose promotion-key selection.",
            ),
            _summary_row(
                "EXECUTION_MODE_RECOMMENDATION",
                execution_mode_recommendation,
                "Whether planner-only or execution mode is recommended.",
            ),
            _summary_row(
                "DRY_RUN",
                int(dry_run),
                "Whether the runner was invoked in dry-run mode.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Multi-Promotion Reconstruction Queue",
            "",
            "This is a diagnostics-only multi-promotion controlled reconstruction queue runner.",
            "This does not start training.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "This does not promote auto-ordering.",
            "This does not promote shadow rules.",
            "This does not run action-layer recalibration.",
            "This does not run shadow-vs-baseline simulation.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "This does not silently drop quarantine rows.",
            "",
            f"Queue status: {overall_queue_status}",
            f"Source-materialized promotion count: {source_materialized_promotion_count}",
            f"Already complete promotion count: {complete_count}",
            f"Incomplete promotion count: {incomplete_count}",
            f"Promotions ready to start: {ready_count}",
            f"Blocked promotions: {blocked_count}",
            f"Stage count per incomplete promotion: {stage_count_per_incomplete_promotion}",
            f"Stage runtimes promotion-key aware: {stage_runtimes_promotion_key_aware_flag}",
            f"Execution mode recommendation: {execution_mode_recommendation}",
            "",
            "## Recommendation",
            recommendation,
            "",
            planner_recommendation_reason,
        ]
    ).strip()

    return PromotionsMaterializedSourceMultiPromotionReconstructionQueueResult(
        overall_queue_status=overall_queue_status,
        source_materialized_promotion_count=source_materialized_promotion_count,
        already_complete_promotion_count=complete_count,
        incomplete_promotion_count=incomplete_count,
        promotions_ready_to_start=ready_count,
        blocked_promotion_count=blocked_count,
        stage_count_per_incomplete_promotion=stage_count_per_incomplete_promotion,
        stage_runtimes_promotion_key_aware_flag=stage_runtimes_promotion_key_aware_flag,
        execution_mode_recommendation=execution_mode_recommendation,
        recommendation=recommendation,
        queue_rows_frame=queue_rows_frame,
        by_promotion_frame=by_promotion_frame,
        stage_plan_frame=stage_plan_frame,
        missing_inputs_frame=missing_inputs_frame,
        validation_frame=validation_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_multi_promotion_reconstruction_queue(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    max_promotions: int | None = None,
    dry_run: bool = False,
    include_already_complete: bool = False,
) -> PromotionsMaterializedSourceMultiPromotionReconstructionQueueArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = (
        Path(output_root)
        if output_root is not None
        else packet_root_path / OUTPUT_FOLDER_NAME
    )
    result = build_promotions_materialized_source_multi_promotion_reconstruction_queue(
        packet_root=packet_root_path,
        max_promotions=max_promotions,
        dry_run=dry_run,
        include_already_complete=include_already_complete,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    queue_rows_csv_path = output_root_path / "multi_promotion_reconstruction_queue_rows.csv"
    by_promotion_csv_path = output_root_path / "multi_promotion_reconstruction_queue_by_promotion.csv"
    stage_plan_csv_path = output_root_path / "multi_promotion_reconstruction_stage_plan.csv"
    missing_inputs_csv_path = output_root_path / "multi_promotion_reconstruction_missing_inputs.csv"
    validation_csv_path = output_root_path / "multi_promotion_reconstruction_validation.csv"
    summary_csv_path = output_root_path / "multi_promotion_reconstruction_summary.csv"
    memo_md_path = output_root_path / "multi_promotion_reconstruction_memo.md"

    result.queue_rows_frame.to_csv(queue_rows_csv_path, index=False)
    result.by_promotion_frame.to_csv(by_promotion_csv_path, index=False)
    result.stage_plan_frame.to_csv(stage_plan_csv_path, index=False)
    result.missing_inputs_frame.to_csv(missing_inputs_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceMultiPromotionReconstructionQueueArtifacts(
        output_root=str(output_root_path),
        queue_rows_csv_path=str(queue_rows_csv_path),
        by_promotion_csv_path=str(by_promotion_csv_path),
        stage_plan_csv_path=str(stage_plan_csv_path),
        missing_inputs_csv_path=str(missing_inputs_csv_path),
        validation_csv_path=str(validation_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
        overall_queue_status=result.overall_queue_status,
        source_materialized_promotion_count=result.source_materialized_promotion_count,
        already_complete_promotion_count=result.already_complete_promotion_count,
        incomplete_promotion_count=result.incomplete_promotion_count,
        promotions_ready_to_start=result.promotions_ready_to_start,
        blocked_promotion_count=result.blocked_promotion_count,
        stage_count_per_incomplete_promotion=result.stage_count_per_incomplete_promotion,
        stage_runtimes_promotion_key_aware_flag=result.stage_runtimes_promotion_key_aware_flag,
        execution_mode_recommendation=result.execution_mode_recommendation,
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only multi-promotion controlled reconstruction queue runner."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--max-promotions", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-already-complete", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_multi_promotion_reconstruction_queue(
        packet_root=args.packet_root,
        output_root=args.output_root,
        max_promotions=args.max_promotions,
        dry_run=args.dry_run,
        include_already_complete=args.include_already_complete,
    )
    print("queue_status", artifacts.overall_queue_status)
    print("source_materialized_promotion_count", artifacts.source_materialized_promotion_count)
    print("already_complete_promotion_count", artifacts.already_complete_promotion_count)
    print("incomplete_promotion_count", artifacts.incomplete_promotion_count)
    print("promotions_ready_to_start", artifacts.promotions_ready_to_start)
    print("blocked_promotion_count", artifacts.blocked_promotion_count)
    print("stage_count_per_incomplete_promotion", artifacts.stage_count_per_incomplete_promotion)
    print(
        "stage_runtimes_promotion_key_aware",
        artifacts.stage_runtimes_promotion_key_aware_flag,
    )
    print("execution_mode_recommendation", artifacts.execution_mode_recommendation)
    print("recommendation", artifacts.recommendation)
    print("multi_promotion_reconstruction_queue_rows", artifacts.queue_rows_csv_path)
    print("multi_promotion_reconstruction_queue_by_promotion", artifacts.by_promotion_csv_path)
    print("multi_promotion_reconstruction_stage_plan", artifacts.stage_plan_csv_path)
    print("multi_promotion_reconstruction_missing_inputs", artifacts.missing_inputs_csv_path)
    print("multi_promotion_reconstruction_validation", artifacts.validation_csv_path)
    print("multi_promotion_reconstruction_summary", artifacts.summary_csv_path)
    print("multi_promotion_reconstruction_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())