from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_governed_rebuild_validation"
REVIEW_PACKET_DRAFT_FOLDER_NAME = "materialized_source_review_packet_draft"
SCHEMA_AMBIGUITY_RESOLUTION_FOLDER_NAME = "materialized_source_schema_ambiguity_resolution"

DRAFT_ROWS_FILE_NAME = "materialized_source_review_packet_draft_rows.csv"
DRAFT_QUARANTINE_FILE_NAME = "materialized_source_review_packet_draft_quarantine_rows.csv"
DRAFT_SCHEMA_VALIDATION_FILE_NAME = "materialized_source_review_packet_draft_schema_validation.csv"
DRAFT_QUALITY_CHECKS_FILE_NAME = "materialized_source_review_packet_draft_quality_checks.csv"
DRAFT_FIELD_LINEAGE_FILE_NAME = "materialized_source_review_packet_draft_field_lineage.csv"
AMBIGUITY_VALIDATION_FILE_NAME = "materialized_source_schema_ambiguity_resolution_validation.csv"

REQUIRED_DRAFT_FILE_NAMES: tuple[str, ...] = (
    DRAFT_ROWS_FILE_NAME,
    DRAFT_QUARANTINE_FILE_NAME,
    DRAFT_SCHEMA_VALIDATION_FILE_NAME,
    DRAFT_QUALITY_CHECKS_FILE_NAME,
    DRAFT_FIELD_LINEAGE_FILE_NAME,
)

REQUIRED_AMBIGUITY_FILE_NAMES: tuple[str, ...] = (
    AMBIGUITY_VALIDATION_FILE_NAME,
)

GOVERNED_REBUILD_VALIDATION_READY = "GOVERNED_REBUILD_VALIDATION_READY"
GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE = "GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE"
GOVERNED_REBUILD_VALIDATION_BLOCKED_MISSING_COLUMNS = "GOVERNED_REBUILD_VALIDATION_BLOCKED_MISSING_COLUMNS"
GOVERNED_REBUILD_VALIDATION_BLOCKED_GUARDRAIL_FAILURE = "GOVERNED_REBUILD_VALIDATION_BLOCKED_GUARDRAIL_FAILURE"
GOVERNED_REBUILD_VALIDATION_BLOCKED_ZERO_FILLED_ACTUALS = "GOVERNED_REBUILD_VALIDATION_BLOCKED_ZERO_FILLED_ACTUALS"
GOVERNED_REBUILD_VALIDATION_BLOCKED_LINEAGE_GAP = "GOVERNED_REBUILD_VALIDATION_BLOCKED_LINEAGE_GAP"
GOVERNED_REBUILD_VALIDATION_BLOCKED_ARTIFACT_PLAN_GAP = "GOVERNED_REBUILD_VALIDATION_BLOCKED_ARTIFACT_PLAN_GAP"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

CHECKS_COLUMNS: tuple[str, ...] = (
    "check_name",
    "check_status",
    "check_flag",
    "details",
)

REQUIRED_COLUMNS_COLUMNS: tuple[str, ...] = (
    "required_column",
    "field_group",
    "present_flag",
    "lineage_present_flag",
    "downstream_approved_flag",
    "column_status",
    "notes",
)

ARTIFACT_PLAN_COLUMNS: tuple[str, ...] = (
    "artifact_name",
    "artifact_required_flag",
    "artifact_plan_status",
    "future_writer_stage",
    "notes",
)

BLOCKERS_COLUMNS: tuple[str, ...] = (
    "blocker_code",
    "blocker_type",
    "blocker_detail",
    "blocking_flag",
    "remediation",
)

DRAFT_FIELD_ORDER: tuple[str, ...] = (
    "store_number",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "sku_number",
    "sku_description",
    "expected_promo_demand",
    "recommended_order_units",
    "final_store_order_units",
    "store_action_label",
    "store_action_reason",
    "demand_evidence_label",
    "actual_units",
    "actual_gross_profit",
    "actual_sell_through_pct",
    "capital_left",
    "capital_left_value",
    "stockout_or_missed_demand_flag",
    "promo_price",
    "promo_cost",
    "promo_gross_profit_per_unit",
    "gross_profit_represented",
    "capital_at_risk",
    "production_order_change_flag",
    "stage_12_change_flag",
    "quarantine_flag",
    "source_row_id",
    "join_key_status",
    "schema_mapping_status",
)

IDENTITY_FIELDS: tuple[str, ...] = (
    "store_number",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "sku_number",
    "sku_description",
)

PREDICTION_ACTION_FIELDS: tuple[str, ...] = (
    "expected_promo_demand",
    "recommended_order_units",
    "final_store_order_units",
    "store_action_label",
    "store_action_reason",
    "demand_evidence_label",
)

ACTUAL_OUTCOME_FIELDS: tuple[str, ...] = (
    "actual_units",
    "actual_gross_profit",
    "actual_sell_through_pct",
    "capital_left",
    "capital_left_value",
    "stockout_or_missed_demand_flag",
)

ECONOMICS_FIELDS: tuple[str, ...] = (
    "promo_price",
    "promo_cost",
    "promo_gross_profit_per_unit",
    "gross_profit_represented",
    "capital_at_risk",
)

DOWNSTREAM_APPROVED_COLUMNS: tuple[str, ...] = DRAFT_FIELD_ORDER

EXPECTED_FUTURE_ARTIFACTS: tuple[str, ...] = (
    "model_vs_actual_review_rows.csv",
    "model_vs_actual_summary.csv",
    "model_vs_actual_by_action_label.csv",
    "model_vs_actual_by_department.csv",
    "model_vs_actual_top_errors.csv",
    "model_vs_actual_memo.md",
)
PLANNED_FUTURE_ARTIFACTS: tuple[str, ...] = EXPECTED_FUTURE_ARTIFACTS


class PromotionsMaterializedSourceGovernedRebuildValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceGovernedRebuildValidationResult:
    selected_promotion: PromotionSelection
    validation_status: str
    checks_frame: pd.DataFrame
    required_columns_frame: pd.DataFrame
    artifact_plan_frame: pd.DataFrame
    blockers_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceGovernedRebuildValidationArtifacts:
    output_root: str
    checks_csv_path: str
    required_columns_csv_path: str
    artifact_plan_csv_path: str
    blockers_csv_path: str
    summary_csv_path: str
    memo_md_path: str


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
        raise PromotionsMaterializedSourceGovernedRebuildValidationError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceGovernedRebuildValidationError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceGovernedRebuildValidationError(f"CSV is empty: {csv_path}")
    return frame


def _has_required_files(stage_root: Path, required_file_names: Sequence[str]) -> bool:
    return all((stage_root / file_name).exists() for file_name in required_file_names)


def _resolve_stage_root(
    *,
    packet_root: Path,
    upstream_root: str | Path | None,
    folder_name: str,
    required_file_names: Sequence[str],
    stage_label: str,
) -> Path:
    if upstream_root is None:
        return packet_root / folder_name
    upstream_root_path = Path(upstream_root)
    candidate_roots = (
        upstream_root_path / folder_name,
        upstream_root_path,
    )
    for candidate_root in candidate_roots:
        if _has_required_files(candidate_root, required_file_names):
            return candidate_root
    candidate_locations = ", ".join(str(path) for path in candidate_roots)
    expected_files = ", ".join(required_file_names)
    raise PromotionsMaterializedSourceGovernedRebuildValidationError(
        f"--upstream-root was provided, but required {stage_label} artifacts were not found. "
        f"Looked under: {candidate_locations}. Expected files: {expected_files}."
    )


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _check_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
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


def _filter_for_promotion(frame: pd.DataFrame, promotion_key: str) -> pd.DataFrame:
    if frame.empty or "promotion_key" not in frame.columns:
        return frame.copy()
    return frame.loc[frame["promotion_key"].astype(str) == promotion_key].reset_index(drop=True).copy()


def _selection_from_rows(rows_frame: pd.DataFrame, promotion_key: str | None) -> PromotionSelection:
    if "promotion_key" not in rows_frame.columns:
        raise PromotionsMaterializedSourceGovernedRebuildValidationError("Draft rows are missing promotion_key.")
    keys = [value for value in rows_frame["promotion_key"].astype(str).drop_duplicates().tolist() if value]
    if not keys:
        raise PromotionsMaterializedSourceGovernedRebuildValidationError("Draft rows did not contain a promotion key.")
    resolved_key = promotion_key or keys[0]
    if resolved_key not in keys:
        raise PromotionsMaterializedSourceGovernedRebuildValidationError(
            f"Requested promotion key was not found in draft rows: {resolved_key}"
        )
    parts = resolved_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceGovernedRebuildValidationError(
            f"Promotion key is not in the expected pipe-delimited format: {resolved_key}"
        )
    return PromotionSelection(
        promotion_key=resolved_key,
        promotion_name=parts[3],
        promotion_start_date=parts[1],
        promotion_end_date=parts[2],
    )


def _field_group(field_name: str) -> str:
    if field_name in IDENTITY_FIELDS:
        return "IDENTITY"
    if field_name in PREDICTION_ACTION_FIELDS:
        return "PREDICTION_ACTION"
    if field_name in ACTUAL_OUTCOME_FIELDS:
        return "ACTUAL_OUTCOME"
    if field_name in ECONOMICS_FIELDS:
        return "ECONOMICS"
    return "GOVERNANCE"


def _quality_lookup(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}
    return dict(zip(frame["check_name"].astype(str), frame["check_status"].astype(str)))


def _schema_validation_lookup(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}
    return dict(zip(frame["draft_field"].astype(str), frame["field_status"].astype(str)))


def _numeric_parseable(frame: pd.DataFrame) -> tuple[int, str]:
    numeric_fields = (
        "expected_promo_demand",
        "recommended_order_units",
        "final_store_order_units",
        "actual_units",
        "actual_gross_profit",
        "actual_sell_through_pct",
        "capital_left",
        "capital_left_value",
        "stockout_or_missed_demand_flag",
        "promo_price",
        "promo_cost",
        "promo_gross_profit_per_unit",
        "gross_profit_represented",
        "capital_at_risk",
        "production_order_change_flag",
        "stage_12_change_flag",
        "quarantine_flag",
        "source_row_id",
    )
    failures: list[str] = []
    for field_name in numeric_fields:
        if field_name not in frame.columns:
            failures.append(f"{field_name}:missing")
            continue
        series = frame[field_name]
        non_blank = series.map(_normalize_text).ne("")
        if not bool(non_blank.any()):
            continue
        parsed = pd.to_numeric(series.loc[non_blank], errors="coerce")
        invalid_count = int(parsed.isna().sum())
        if invalid_count > 0:
            failures.append(f"{field_name}:{invalid_count}")
    if failures:
        return 0, "; ".join(failures)
    return 1, "All populated numeric fields are parseable."


def build_promotions_materialized_source_governed_rebuild_validation(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceGovernedRebuildValidationResult:
    packet_root_path = Path(packet_root)
    draft_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=REVIEW_PACKET_DRAFT_FOLDER_NAME,
        required_file_names=REQUIRED_DRAFT_FILE_NAMES,
        stage_label="review-packet-draft",
    )
    ambiguity_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=SCHEMA_AMBIGUITY_RESOLUTION_FOLDER_NAME,
        required_file_names=REQUIRED_AMBIGUITY_FILE_NAMES,
        stage_label="schema-ambiguity-resolution",
    )

    draft_rows_frame = _read_csv(draft_root / DRAFT_ROWS_FILE_NAME)
    draft_quarantine_frame = _read_csv(draft_root / DRAFT_QUARANTINE_FILE_NAME, allow_empty=True)
    draft_schema_validation_frame = _read_csv(draft_root / DRAFT_SCHEMA_VALIDATION_FILE_NAME)
    draft_quality_checks_frame = _read_csv(draft_root / DRAFT_QUALITY_CHECKS_FILE_NAME)
    draft_field_lineage_frame = _read_csv(draft_root / DRAFT_FIELD_LINEAGE_FILE_NAME)
    ambiguity_validation_frame = _read_csv(ambiguity_root / AMBIGUITY_VALIDATION_FILE_NAME)

    selection = _selection_from_rows(draft_rows_frame, promotion_key)
    draft_rows_frame = _filter_for_promotion(draft_rows_frame, selection.promotion_key)
    draft_quarantine_frame = _filter_for_promotion(draft_quarantine_frame, selection.promotion_key)

    draft_statuses = [value for value in draft_rows_frame.get("schema_mapping_status", pd.Series(dtype="object")).astype(str).drop_duplicates().tolist() if value]
    draft_status = draft_statuses[0] if draft_statuses else ""
    draft_status_ready_flag = int(
        draft_status in {
            "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "REVIEW_PACKET_DRAFT_READY_FOR_GOVERNED_REBUILD_VALIDATION",
        }
    )
    draft_row_count_flag = int(len(draft_rows_frame.index) == 3597)
    quarantine_row_count_flag = int(len(draft_quarantine_frame.index) == 1)
    quarantine_row_numbers = set(
        pd.to_numeric(draft_quarantine_frame.get("source_row_number", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    quarantine_remains_separate_flag = int(48 in quarantine_row_numbers and quarantine_row_count_flag == 1)

    quality_lookup = _quality_lookup(draft_quality_checks_frame)
    schema_lookup = _schema_validation_lookup(draft_schema_validation_frame)
    ambiguity_validation_lookup = dict(
        zip(
            ambiguity_validation_frame.get("validation_name", pd.Series(dtype="object")).astype(str),
            ambiguity_validation_frame.get("validation_status", pd.Series(dtype="object")).astype(str),
        )
    )

    draft_columns = set(draft_rows_frame.columns.astype(str).tolist())
    lineage_fields = set(draft_field_lineage_frame.get("draft_field", pd.Series(dtype="object")).astype(str).tolist())
    required_columns_rows: list[dict[str, object]] = []
    missing_required_columns: list[str] = []
    lineage_gap_columns: list[str] = []
    unapproved_columns = sorted(column_name for column_name in draft_columns if column_name not in DOWNSTREAM_APPROVED_COLUMNS)
    for field_name in DRAFT_FIELD_ORDER:
        present_flag = int(field_name in draft_columns)
        lineage_present_flag = int(field_name in lineage_fields)
        downstream_approved_flag = int(field_name in DOWNSTREAM_APPROVED_COLUMNS)
        status = "PRESENT"
        notes = "Approved downstream draft column."
        if not present_flag:
            status = "MISSING_REQUIRED_COLUMN"
            notes = "Required downstream column is absent from the draft packet."
            missing_required_columns.append(field_name)
        elif not lineage_present_flag:
            status = "LINEAGE_GAP"
            notes = "Required downstream column is present but missing draft lineage."
            lineage_gap_columns.append(field_name)
        required_columns_rows.append(
            {
                "required_column": field_name,
                "field_group": _field_group(field_name),
                "present_flag": present_flag,
                "lineage_present_flag": lineage_present_flag,
                "downstream_approved_flag": downstream_approved_flag,
                "column_status": status,
                "notes": notes,
            }
        )
    required_columns_frame = pd.DataFrame(required_columns_rows, columns=REQUIRED_COLUMNS_COLUMNS)

    required_downstream_columns_present_flag = int(len(missing_required_columns) == 0 and len(unapproved_columns) == 0)
    lineage_complete_flag = int(len(lineage_gap_columns) == 0)
    numeric_fields_parseable_flag, numeric_fields_parseable_details = _numeric_parseable(draft_rows_frame)
    actual_outcome_fields_available_flag = int(all(field_name in draft_columns for field_name in ACTUAL_OUTCOME_FIELDS))
    prediction_action_fields_available_flag = int(all(field_name in draft_columns for field_name in PREDICTION_ACTION_FIELDS))
    economics_fields_available_or_derived_flag = int(
        all(field_name in draft_columns and field_name in lineage_fields for field_name in ECONOMICS_FIELDS)
    )
    zero_filled_actuals_flag = int(
        quality_lookup.get("missing_actuals_not_zero_filled", "FAIL") != "PASS"
        or quality_lookup.get("no_silent_null_to_zero_coercion", "FAIL") != "PASS"
    )
    production_guardrail_status = "PASS" if quality_lookup.get("production_fields_unchanged", "FAIL") == "PASS" else "FAIL"
    stage12_guardrail_status = "PASS" if quality_lookup.get("stage12_unchanged", "FAIL") == "PASS" else "FAIL"
    draft_schema_complete_flag = int(all(status == "PRESENT" for status in schema_lookup.values())) if schema_lookup else 0
    guardrail_failure_flag = int(
        production_guardrail_status != "PASS"
        or stage12_guardrail_status != "PASS"
        or ambiguity_validation_lookup.get("QUARANTINE_ROW_48_REMAINS_SEPARATE", "PASS") != "PASS"
        or not draft_status_ready_flag
        or not draft_row_count_flag
        or not quarantine_row_count_flag
        or not quarantine_remains_separate_flag
        or not numeric_fields_parseable_flag
        or not draft_schema_complete_flag
    )

    artifact_plan_rows = [
        {
            "artifact_name": artifact_name,
            "artifact_required_flag": 1,
            "artifact_plan_status": "PLANNED",
            "future_writer_stage": "governed_model_vs_actual_review_chain",
            "notes": "Expected downstream governed rebuild artifact; validation gate only verifies the plan and does not execute the writer.",
        }
        for artifact_name in PLANNED_FUTURE_ARTIFACTS
    ]
    artifact_plan_frame = pd.DataFrame(artifact_plan_rows, columns=ARTIFACT_PLAN_COLUMNS)
    planned_artifacts = set(artifact_plan_frame["artifact_name"].astype(str).tolist()) if not artifact_plan_frame.empty else set()
    artifact_plan_complete_flag = int(
        planned_artifacts == set(EXPECTED_FUTURE_ARTIFACTS)
        and len(artifact_plan_frame.index) == len(EXPECTED_FUTURE_ARTIFACTS)
    )

    blockers_rows: list[dict[str, object]] = []
    if not required_downstream_columns_present_flag:
        blockers_rows.append(
            {
                "blocker_code": GOVERNED_REBUILD_VALIDATION_BLOCKED_MISSING_COLUMNS,
                "blocker_type": "MISSING_COLUMNS",
                "blocker_detail": f"missing_required_columns={'; '.join(missing_required_columns)}; unapproved_columns={'; '.join(unapproved_columns)}",
                "blocking_flag": 1,
                "remediation": "Align the draft packet columns to the approved model-vs-actual review contract before attempting governed rebuild authoring.",
            }
        )
    if guardrail_failure_flag:
        blockers_rows.append(
            {
                "blocker_code": GOVERNED_REBUILD_VALIDATION_BLOCKED_GUARDRAIL_FAILURE,
                "blocker_type": "GUARDRAIL_FAILURE",
                "blocker_detail": (
                    f"production_guardrail_status={production_guardrail_status}; "
                    f"stage12_guardrail_status={stage12_guardrail_status}; "
                    f"draft_status_ready_flag={draft_status_ready_flag}; "
                    f"draft_row_count_flag={draft_row_count_flag}; "
                    f"quarantine_row_count_flag={quarantine_row_count_flag}; "
                    f"quarantine_remains_separate_flag={quarantine_remains_separate_flag}; "
                    f"numeric_fields_parseable_flag={numeric_fields_parseable_flag}; "
                    f"draft_schema_complete_flag={draft_schema_complete_flag}"
                ),
                "blocking_flag": 1,
                "remediation": "Keep production ordering and Stage 12 unchanged before attempting governed rebuild authoring.",
            }
        )
    if zero_filled_actuals_flag:
        blockers_rows.append(
            {
                "blocker_code": GOVERNED_REBUILD_VALIDATION_BLOCKED_ZERO_FILLED_ACTUALS,
                "blocker_type": "ZERO_FILLED_ACTUALS",
                "blocker_detail": "Draft quality checks indicate missing actuals were zero-filled or silently coerced.",
                "blocking_flag": 1,
                "remediation": "Rebuild the draft packet with missing actuals preserved as missing values.",
            }
        )
    if not lineage_complete_flag:
        blockers_rows.append(
            {
                "blocker_code": GOVERNED_REBUILD_VALIDATION_BLOCKED_LINEAGE_GAP,
                "blocker_type": "LINEAGE_GAP",
                "blocker_detail": f"lineage_gap_columns={'; '.join(lineage_gap_columns)}",
                "blocking_flag": 1,
                "remediation": "Add field lineage for every required downstream draft field before attempting governed rebuild authoring.",
            }
        )
    if not artifact_plan_complete_flag:
        blockers_rows.append(
            {
                "blocker_code": GOVERNED_REBUILD_VALIDATION_BLOCKED_ARTIFACT_PLAN_GAP,
                "blocker_type": "ARTIFACT_PLAN_GAP",
                "blocker_detail": "The future governed rebuild artifact plan is incomplete.",
                "blocking_flag": 1,
                "remediation": "Complete the downstream model-vs-actual artifact plan before attempting governed rebuild authoring.",
            }
        )
    blockers_frame = pd.DataFrame(blockers_rows, columns=BLOCKERS_COLUMNS)

    checks_frame = pd.DataFrame(
        [
            _check_row(
                "DRAFT_STATUS_READY",
                "PASS" if draft_status_ready_flag else "FAIL",
                draft_status_ready_flag,
                f"draft_status={draft_status}",
            ),
            _check_row(
                "DRAFT_ROW_COUNT_MATCHES_EXPECTATION",
                "PASS" if draft_row_count_flag else "FAIL",
                draft_row_count_flag,
                f"draft_rows={len(draft_rows_frame.index)}, expected=3597",
            ),
            _check_row(
                "QUARANTINE_ROW_COUNT_MATCHES_EXPECTATION",
                "PASS" if quarantine_row_count_flag else "FAIL",
                quarantine_row_count_flag,
                f"quarantine_rows={len(draft_quarantine_frame.index)}, expected=1",
            ),
            _check_row(
                "REQUIRED_DOWNSTREAM_FIELDS_PRESENT",
                "PASS" if required_downstream_columns_present_flag else "FAIL",
                required_downstream_columns_present_flag,
                f"missing_required_columns={'; '.join(missing_required_columns)}; unapproved_columns={'; '.join(unapproved_columns)}",
            ),
            _check_row(
                "NO_ZERO_FILLED_ACTUALS",
                "PASS" if not zero_filled_actuals_flag else "FAIL",
                int(not zero_filled_actuals_flag),
                "Draft quality checks confirm missing actuals remain missing rather than being zero-filled.",
            ),
            _check_row(
                "PRODUCTION_FIELDS_UNCHANGED",
                production_guardrail_status,
                int(production_guardrail_status == "PASS"),
                "Production-facing fields remain unchanged from the resolved schema rows.",
            ),
            _check_row(
                "STAGE12_FIELDS_UNCHANGED",
                stage12_guardrail_status,
                int(stage12_guardrail_status == "PASS"),
                "Stage 12 fields remain unchanged from the resolved schema rows.",
            ),
            _check_row(
                "QUARANTINE_ROW_REMAINS_SEPARATE",
                "PASS" if quarantine_remains_separate_flag else "FAIL",
                quarantine_remains_separate_flag,
                "Quarantine row 48 remains separate from the draft packet rows.",
            ),
            _check_row(
                "NUMERIC_FIELDS_PARSE_CLEANLY",
                "PASS" if numeric_fields_parseable_flag else "FAIL",
                numeric_fields_parseable_flag,
                numeric_fields_parseable_details,
            ),
            _check_row(
                "ACTUAL_OUTCOME_FIELDS_AVAILABLE",
                "PASS" if actual_outcome_fields_available_flag else "FAIL",
                actual_outcome_fields_available_flag,
                "All downstream actual outcome fields are available on the draft packet.",
            ),
            _check_row(
                "PREDICTION_ACTION_FIELDS_AVAILABLE",
                "PASS" if prediction_action_fields_available_flag else "FAIL",
                prediction_action_fields_available_flag,
                "All downstream prediction/action fields are available on the draft packet.",
            ),
            _check_row(
                "ECONOMICS_FIELDS_AVAILABLE_OR_DERIVED",
                "PASS" if economics_fields_available_or_derived_flag else "FAIL",
                economics_fields_available_or_derived_flag,
                "All downstream economics fields are available directly or supported by lineage/derivation.",
            ),
            _check_row(
                "FIELD_LINEAGE_EXISTS_FOR_EVERY_REQUIRED_FIELD",
                "PASS" if lineage_complete_flag else "FAIL",
                lineage_complete_flag,
                f"lineage_gap_columns={'; '.join(lineage_gap_columns)}",
            ),
            _check_row(
                "MODEL_VS_ACTUAL_REVIEW_INPUT_IS_APPROVED",
                "PASS" if required_downstream_columns_present_flag and draft_schema_complete_flag else "FAIL",
                int(required_downstream_columns_present_flag and draft_schema_complete_flag),
                "The draft packet matches the approved governed review packet contract and does not require unapproved input columns.",
            ),
            _check_row(
                "OUTPUT_ARTIFACT_PLAN_IS_COMPLETE",
                "PASS" if artifact_plan_complete_flag else "FAIL",
                artifact_plan_complete_flag,
                "The future governed rebuild artifact plan includes the full model-vs-actual output set.",
            ),
        ],
        columns=CHECKS_COLUMNS,
    )

    if not required_downstream_columns_present_flag:
        validation_status = GOVERNED_REBUILD_VALIDATION_BLOCKED_MISSING_COLUMNS
    elif guardrail_failure_flag:
        validation_status = GOVERNED_REBUILD_VALIDATION_BLOCKED_GUARDRAIL_FAILURE
    elif zero_filled_actuals_flag:
        validation_status = GOVERNED_REBUILD_VALIDATION_BLOCKED_ZERO_FILLED_ACTUALS
    elif not lineage_complete_flag:
        validation_status = GOVERNED_REBUILD_VALIDATION_BLOCKED_LINEAGE_GAP
    elif not artifact_plan_complete_flag:
        validation_status = GOVERNED_REBUILD_VALIDATION_BLOCKED_ARTIFACT_PLAN_GAP
    elif len(draft_quarantine_frame.index) > 0:
        validation_status = GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE
    else:
        validation_status = GOVERNED_REBUILD_VALIDATION_READY

    controlled_governed_rebuild_can_be_authored_next = int(
        validation_status in {
            GOVERNED_REBUILD_VALIDATION_READY,
            GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE,
        }
    )

    summary_frame = pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION", selection.promotion_key, "Promotion selected for diagnostics-only governed rebuild validation."),
            _summary_row("VALIDATION_STATUS", validation_status, "Overall diagnostics-only governed rebuild validation status."),
            _summary_row("DRAFT_ROW_COUNT", len(draft_rows_frame.index), "Draft row count evaluated by the gate."),
            _summary_row("QUARANTINE_ROW_COUNT", len(draft_quarantine_frame.index), "Quarantine row count evaluated by the gate."),
            _summary_row("REQUIRED_DOWNSTREAM_COLUMNS_PRESENT_FLAG", required_downstream_columns_present_flag, "Whether all approved downstream review columns are present and no unapproved columns are required."),
            _summary_row("ZERO_FILLED_ACTUALS_FLAG", zero_filled_actuals_flag, "1 means missing actuals were zero-filled or silently coerced; 0 means blanks were preserved."),
            _summary_row("LINEAGE_COMPLETE_FLAG", lineage_complete_flag, "Whether field lineage exists for every required downstream draft field."),
            _summary_row("ARTIFACT_PLAN_COMPLETE_FLAG", artifact_plan_complete_flag, "Whether the future model-vs-actual artifact plan is complete."),
            _summary_row("PRODUCTION_GUARDRAIL_STATUS", production_guardrail_status, "Production-order guardrail status inherited and re-validated at the governed rebuild validation gate."),
            _summary_row("STAGE12_GUARDRAIL_STATUS", stage12_guardrail_status, "Stage 12 guardrail status inherited and re-validated at the governed rebuild validation gate."),
            _summary_row("CONTROLLED_GOVERNED_REBUILD_CAN_BE_AUTHORED_NEXT", controlled_governed_rebuild_can_be_authored_next, "Whether a controlled governed rebuild can be authored next without executing it."),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Materialized Source Governed Rebuild Validation",
            "",
            "This is a diagnostics-only governed rebuild validation gate.",
            "This does not run the governed rebuild.",
            "This does not run the model-vs-actual review runtime.",
            "This does not start training.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "This does not promote auto-ordering.",
            "This does not promote shadow rules.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "This keeps quarantine row 48 separate.",
            "",
            f"Selected promotion: {selection.promotion_key}",
            f"Validation status: {validation_status}",
            f"Draft row count: {len(draft_rows_frame.index)}",
            f"Quarantine row count: {len(draft_quarantine_frame.index)}",
            f"Required downstream columns present flag: {required_downstream_columns_present_flag}",
            f"Zero-filled actuals flag: {zero_filled_actuals_flag}",
            f"Lineage complete flag: {lineage_complete_flag}",
            f"Artifact plan complete flag: {artifact_plan_complete_flag}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Controlled governed rebuild can be authored next: {controlled_governed_rebuild_can_be_authored_next}",
            "",
            "## Recommendation",
            (
                "Author the controlled governed rebuild next as a diagnostics-only step, while continuing to keep quarantine row 48 separate and without executing the rebuild in this gate."
                if controlled_governed_rebuild_can_be_authored_next
                else "Do not author the controlled governed rebuild yet; one or more validation gate checks remain blocked."
            ),
        ]
    ).strip()

    return PromotionsMaterializedSourceGovernedRebuildValidationResult(
        selected_promotion=selection,
        validation_status=validation_status,
        checks_frame=checks_frame,
        required_columns_frame=required_columns_frame,
        artifact_plan_frame=artifact_plan_frame,
        blockers_frame=blockers_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_governed_rebuild_validation(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceGovernedRebuildValidationArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_governed_rebuild_validation(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    checks_csv_path = output_root_path / "materialized_source_governed_rebuild_validation_checks.csv"
    required_columns_csv_path = output_root_path / "materialized_source_governed_rebuild_validation_required_columns.csv"
    artifact_plan_csv_path = output_root_path / "materialized_source_governed_rebuild_validation_artifact_plan.csv"
    blockers_csv_path = output_root_path / "materialized_source_governed_rebuild_validation_blockers.csv"
    summary_csv_path = output_root_path / "materialized_source_governed_rebuild_validation_summary.csv"
    memo_md_path = output_root_path / "materialized_source_governed_rebuild_validation_memo.md"

    result.checks_frame.to_csv(checks_csv_path, index=False)
    result.required_columns_frame.to_csv(required_columns_csv_path, index=False)
    result.artifact_plan_frame.to_csv(artifact_plan_csv_path, index=False)
    result.blockers_frame.to_csv(blockers_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceGovernedRebuildValidationArtifacts(
        output_root=str(output_root_path),
        checks_csv_path=str(checks_csv_path),
        required_columns_csv_path=str(required_columns_csv_path),
        artifact_plan_csv_path=str(artifact_plan_csv_path),
        blockers_csv_path=str(blockers_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only governed rebuild validation gate for the materialized source review-packet draft."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_governed_rebuild_validation(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary_frame)
    print("selected_promotion", _normalize_text(metrics.get("SELECTED_PROMOTION", "")))
    print("validation_status", _normalize_text(metrics.get("VALIDATION_STATUS", "")))
    print("draft_row_count", _normalize_text(metrics.get("DRAFT_ROW_COUNT", 0)))
    print("quarantine_row_count", _normalize_text(metrics.get("QUARANTINE_ROW_COUNT", 0)))
    print("required_downstream_columns_present_flag", _normalize_text(metrics.get("REQUIRED_DOWNSTREAM_COLUMNS_PRESENT_FLAG", 0)))
    print("zero_filled_actuals_flag", _normalize_text(metrics.get("ZERO_FILLED_ACTUALS_FLAG", 0)))
    print("lineage_complete_flag", _normalize_text(metrics.get("LINEAGE_COMPLETE_FLAG", 0)))
    print("artifact_plan_complete_flag", _normalize_text(metrics.get("ARTIFACT_PLAN_COMPLETE_FLAG", 0)))
    print("production_guardrail_status", _normalize_text(metrics.get("PRODUCTION_GUARDRAIL_STATUS", "")))
    print("stage12_guardrail_status", _normalize_text(metrics.get("STAGE12_GUARDRAIL_STATUS", "")))
    print(
        "controlled_governed_rebuild_can_be_authored_next",
        _normalize_text(metrics.get("CONTROLLED_GOVERNED_REBUILD_CAN_BE_AUTHORED_NEXT", 0)),
    )
    print("materialized_source_governed_rebuild_validation_checks", artifacts.checks_csv_path)
    print("materialized_source_governed_rebuild_validation_required_columns", artifacts.required_columns_csv_path)
    print("materialized_source_governed_rebuild_validation_artifact_plan", artifacts.artifact_plan_csv_path)
    print("materialized_source_governed_rebuild_validation_blockers", artifacts.blockers_csv_path)
    print("materialized_source_governed_rebuild_validation_summary", artifacts.summary_csv_path)
    print("materialized_source_governed_rebuild_validation_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
