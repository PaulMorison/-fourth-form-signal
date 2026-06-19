from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_review_packet_draft"
PREVIEW_JOIN_FOLDER_NAME = "materialized_source_preview_join"
SCHEMA_MAPPING_PLAN_FOLDER_NAME = "materialized_source_schema_mapping_plan"
SCHEMA_AMBIGUITY_RESOLUTION_FOLDER_NAME = "materialized_source_schema_ambiguity_resolution"

PREVIEW_ROWS_FILE_NAME = "materialized_source_preview_join_rows.csv"
PREVIEW_QUARANTINE_FILE_NAME = "materialized_source_preview_join_quarantine_rows.csv"
MAPPING_ROWS_FILE_NAME = "materialized_source_schema_mapping_rows.csv"
DERIVED_FIELDS_FILE_NAME = "materialized_source_schema_mapping_derived_fields.csv"
RESOLUTION_RULES_FILE_NAME = "materialized_source_schema_ambiguity_resolution_rules.csv"
RESOLUTION_ROWS_FILE_NAME = "materialized_source_schema_ambiguity_resolution_rows.csv"
RESOLUTION_VALIDATION_FILE_NAME = "materialized_source_schema_ambiguity_resolution_validation.csv"

REQUIRED_RESOLUTION_FILE_NAMES: tuple[str, ...] = (
    RESOLUTION_RULES_FILE_NAME,
    RESOLUTION_ROWS_FILE_NAME,
    RESOLUTION_VALIDATION_FILE_NAME,
)

REVIEW_PACKET_DRAFT_READY_FOR_GOVERNED_REBUILD_VALIDATION = (
    "REVIEW_PACKET_DRAFT_READY_FOR_GOVERNED_REBUILD_VALIDATION"
)
REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE = "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE"
REVIEW_PACKET_DRAFT_BLOCKED_MISSING_REQUIRED_FIELDS = "REVIEW_PACKET_DRAFT_BLOCKED_MISSING_REQUIRED_FIELDS"
REVIEW_PACKET_DRAFT_BLOCKED_ROW_COUNT_MISMATCH = "REVIEW_PACKET_DRAFT_BLOCKED_ROW_COUNT_MISMATCH"
REVIEW_PACKET_DRAFT_BLOCKED_GUARDRAIL_FAILURE = "REVIEW_PACKET_DRAFT_BLOCKED_GUARDRAIL_FAILURE"
REVIEW_PACKET_DRAFT_BLOCKED_MISSING_ACTUAL_ZERO_FILL = "REVIEW_PACKET_DRAFT_BLOCKED_MISSING_ACTUAL_ZERO_FILL"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

SCHEMA_VALIDATION_COLUMNS: tuple[str, ...] = (
    "draft_field",
    "field_group",
    "required_flag",
    "nullable_flag",
    "present_flag",
    "non_null_complete_flag",
    "field_status",
    "notes",
)

FIELD_LINEAGE_COLUMNS: tuple[str, ...] = (
    "draft_field",
    "source_artifact",
    "source_column",
    "lineage_type",
    "derivation_formula",
    "upstream_rule",
    "notes",
)

QUALITY_CHECK_COLUMNS: tuple[str, ...] = (
    "check_name",
    "check_status",
    "check_flag",
    "details",
)

QUARANTINE_OUTPUT_COLUMNS: tuple[str, ...] = (
    "source_row_number",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "quarantine_reason",
    "remediation_required",
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

NON_NULL_REQUIRED_FIELDS: tuple[str, ...] = (
    *IDENTITY_FIELDS,
    *PREDICTION_ACTION_FIELDS,
    *ECONOMICS_FIELDS,
    "production_order_change_flag",
    "stage_12_change_flag",
    "quarantine_flag",
    "source_row_id",
    "join_key_status",
)

NUMERIC_FIELDS: tuple[str, ...] = (
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

PRODUCTION_FIELDS: tuple[str, ...] = (
    "expected_promo_demand",
    "recommended_order_units",
    "final_store_order_units",
    "production_order_change_flag",
)

STAGE12_FIELDS: tuple[str, ...] = (
    "stage_12_change_flag",
)


class PromotionsMaterializedSourceReviewPacketDraftError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceReviewPacketDraftResult:
    selected_promotion: PromotionSelection
    draft_status: str
    draft_rows_frame: pd.DataFrame
    quarantine_rows_frame: pd.DataFrame
    schema_validation_frame: pd.DataFrame
    field_lineage_frame: pd.DataFrame
    quality_checks_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceReviewPacketDraftArtifacts:
    output_root: str
    rows_csv_path: str
    quarantine_rows_csv_path: str
    schema_validation_csv_path: str
    field_lineage_csv_path: str
    quality_checks_csv_path: str
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
        raise PromotionsMaterializedSourceReviewPacketDraftError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceReviewPacketDraftError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceReviewPacketDraftError(f"CSV is empty: {csv_path}")
    return frame


def _has_required_resolution_files(resolution_root: Path) -> bool:
    return all((resolution_root / file_name).exists() for file_name in REQUIRED_RESOLUTION_FILE_NAMES)


def _resolve_resolution_root(*, packet_root: Path, upstream_root: str | Path | None) -> Path:
    if upstream_root is None:
        return packet_root / SCHEMA_AMBIGUITY_RESOLUTION_FOLDER_NAME
    upstream_root_path = Path(upstream_root)
    candidate_roots = (
        upstream_root_path / SCHEMA_AMBIGUITY_RESOLUTION_FOLDER_NAME,
        upstream_root_path,
    )
    for candidate_root in candidate_roots:
        if _has_required_resolution_files(candidate_root):
            return candidate_root
    candidate_locations = ", ".join(str(path) for path in candidate_roots)
    expected_files = ", ".join(REQUIRED_RESOLUTION_FILE_NAMES)
    raise PromotionsMaterializedSourceReviewPacketDraftError(
        "--upstream-root was provided, but required schema-ambiguity-resolution artifacts were not found. "
        f"Looked under: {candidate_locations}. Expected files: {expected_files}."
    )


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _quality_check_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
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


def _blank_mask(series: pd.Series) -> pd.Series:
    return series.map(_normalize_text).eq("")


def _series_equal(left: pd.Series, right: pd.Series) -> bool:
    return bool(left.map(_normalize_text).eq(right.map(_normalize_text)).all())


def _ensure_quarantine_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=QUARANTINE_OUTPUT_COLUMNS)
    ensured = frame.copy()
    for column_name in QUARANTINE_OUTPUT_COLUMNS:
        if column_name not in ensured.columns:
            ensured[column_name] = ""
    return ensured.loc[:, list(QUARANTINE_OUTPUT_COLUMNS)].copy()


def _filter_for_promotion(frame: pd.DataFrame, promotion_key: str) -> pd.DataFrame:
    if frame.empty or "promotion_key" not in frame.columns:
        return frame.copy()
    return frame.loc[frame["promotion_key"].astype(str) == promotion_key].reset_index(drop=True).copy()


def _selection_from_rows(rows_frame: pd.DataFrame, promotion_key: str | None) -> PromotionSelection:
    if "promotion_key" not in rows_frame.columns:
        raise PromotionsMaterializedSourceReviewPacketDraftError("Resolved rows are missing promotion_key.")
    keys = [value for value in rows_frame["promotion_key"].astype(str).drop_duplicates().tolist() if value]
    if not keys:
        raise PromotionsMaterializedSourceReviewPacketDraftError("Resolved rows did not contain a promotion key.")
    resolved_key = promotion_key or keys[0]
    if resolved_key not in keys:
        raise PromotionsMaterializedSourceReviewPacketDraftError(
            f"Requested promotion key was not found in resolved rows: {resolved_key}"
        )
    parts = resolved_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceReviewPacketDraftError(
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


def _numeric_parseable(frame: pd.DataFrame) -> tuple[int, str]:
    failures: list[str] = []
    for field_name in NUMERIC_FIELDS:
        if field_name not in frame.columns:
            failures.append(f"{field_name}:missing")
            continue
        non_blank = ~_blank_mask(frame[field_name])
        if not bool(non_blank.any()):
            continue
        parsed = pd.to_numeric(frame.loc[non_blank, field_name], errors="coerce")
        invalid_count = int(parsed.isna().sum())
        if invalid_count > 0:
            failures.append(f"{field_name}:{invalid_count}")
    if failures:
        return 0, "; ".join(failures)
    return 1, "All populated numeric fields are parseable."


def _rules_lookup(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    if frame.empty:
        return {}
    return {
        _normalize_text(row.get("canonical_field")): row.to_dict()
        for _, row in frame.iterrows()
        if _normalize_text(row.get("canonical_field"))
    }


def _derived_lookup(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    if frame.empty:
        return {}
    return {
        _normalize_text(row.get("canonical_field")): row.to_dict()
        for _, row in frame.iterrows()
        if _normalize_text(row.get("canonical_field"))
    }


def _missing_actuals_preserved_from_sources(
    *,
    preview_rows_frame: pd.DataFrame,
    resolved_rows_frame: pd.DataFrame,
    draft_rows_frame: pd.DataFrame,
    rules_lookup: dict[str, dict[str, object]],
) -> int:
    rule_backed_fields = (
        "actual_units",
        "actual_sell_through_pct",
        "capital_left",
        "capital_left_value",
    )
    for field_name in rule_backed_fields:
        rule = rules_lookup.get(field_name, {})
        source_column = _normalize_text(rule.get("selected_source_column")) or field_name
        if source_column not in preview_rows_frame.columns or field_name not in draft_rows_frame.columns:
            continue
        blank_source = _blank_mask(preview_rows_frame[source_column])
        if not bool(blank_source.any()):
            continue
        if not bool(_blank_mask(draft_rows_frame.loc[blank_source, field_name]).all()):
            return 0
    if "actual_gross_profit" in resolved_rows_frame.columns and "actual_gross_profit" in draft_rows_frame.columns:
        resolved_blank = _blank_mask(resolved_rows_frame["actual_gross_profit"])
        if bool(resolved_blank.any()) and not bool(_blank_mask(draft_rows_frame.loc[resolved_blank, "actual_gross_profit"]).all()):
            return 0
    return 1


def build_promotions_materialized_source_review_packet_draft(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceReviewPacketDraftResult:
    packet_root_path = Path(packet_root)
    preview_root = packet_root_path / PREVIEW_JOIN_FOLDER_NAME
    mapping_root = packet_root_path / SCHEMA_MAPPING_PLAN_FOLDER_NAME
    resolution_root = _resolve_resolution_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
    )

    preview_rows_frame = _read_csv(preview_root / PREVIEW_ROWS_FILE_NAME)
    preview_quarantine_frame = _read_csv(preview_root / PREVIEW_QUARANTINE_FILE_NAME, allow_empty=True)
    mapping_rows_frame = _read_csv(mapping_root / MAPPING_ROWS_FILE_NAME)
    derived_fields_frame = _read_csv(mapping_root / DERIVED_FIELDS_FILE_NAME, allow_empty=True)
    rules_frame = _read_csv(resolution_root / RESOLUTION_RULES_FILE_NAME)
    resolved_rows_frame = _read_csv(resolution_root / RESOLUTION_ROWS_FILE_NAME)
    resolution_validation_frame = _read_csv(resolution_root / RESOLUTION_VALIDATION_FILE_NAME)

    selection = _selection_from_rows(resolved_rows_frame, promotion_key)
    preview_rows_frame = _filter_for_promotion(preview_rows_frame, selection.promotion_key)
    preview_quarantine_frame = _ensure_quarantine_columns(
        _filter_for_promotion(preview_quarantine_frame, selection.promotion_key)
    )
    mapping_rows_frame = _filter_for_promotion(mapping_rows_frame, selection.promotion_key)
    resolved_rows_frame = _filter_for_promotion(resolved_rows_frame, selection.promotion_key)

    draft_rows_frame = resolved_rows_frame.copy()
    for column_name in DRAFT_FIELD_ORDER:
        if column_name not in draft_rows_frame.columns:
            draft_rows_frame[column_name] = ""
    draft_rows_frame = draft_rows_frame.loc[:, list(DRAFT_FIELD_ORDER)].copy()

    rules_lookup = _rules_lookup(rules_frame)
    derived_lookup = _derived_lookup(derived_fields_frame)
    resolution_validation_lookup = dict(
        zip(
            resolution_validation_frame["validation_name"].astype(str),
            resolution_validation_frame["validation_status"].astype(str),
        )
    )

    required_fields_complete_flag = 1
    missing_required_fields: list[str] = []
    schema_validation_rows: list[dict[str, object]] = []
    for field_name in DRAFT_FIELD_ORDER:
        present_flag = int(field_name in draft_rows_frame.columns)
        nullable_flag = int(field_name in ACTUAL_OUTCOME_FIELDS)
        non_null_complete_flag = 1
        field_status = "PRESENT"
        notes = "Projected unchanged from the resolved schema rows."
        if field_name in rules_lookup:
            notes = _normalize_text(rules_lookup[field_name].get("resolution_reason"))
        elif field_name in derived_lookup:
            notes = _normalize_text(derived_lookup[field_name].get("notes"))
        if not present_flag:
            non_null_complete_flag = 0
            field_status = "MISSING_REQUIRED_FIELD"
            required_fields_complete_flag = 0
            missing_required_fields.append(field_name)
        elif field_name in NON_NULL_REQUIRED_FIELDS:
            blank_count = int(_blank_mask(draft_rows_frame[field_name]).sum())
            non_null_complete_flag = int(blank_count == 0)
            if blank_count > 0:
                field_status = "INCOMPLETE_NON_NULLABLE_FIELD"
                required_fields_complete_flag = 0
                missing_required_fields.append(field_name)
        schema_validation_rows.append(
            {
                "draft_field": field_name,
                "field_group": _field_group(field_name),
                "required_flag": 1,
                "nullable_flag": nullable_flag,
                "present_flag": present_flag,
                "non_null_complete_flag": non_null_complete_flag,
                "field_status": field_status,
                "notes": notes,
            }
        )
    schema_validation_frame = pd.DataFrame(schema_validation_rows, columns=SCHEMA_VALIDATION_COLUMNS)

    row_count_conservation_flag = int(
        len(draft_rows_frame.index) == len(resolved_rows_frame.index)
        and len(draft_rows_frame.index) == len(mapping_rows_frame.index)
        and len(draft_rows_frame.index) == len(preview_rows_frame.index)
    )
    quarantine_row_numbers = set(
        pd.to_numeric(preview_quarantine_frame.get("source_row_number", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    quarantine_preserved_flag = int(len(preview_quarantine_frame.index) == 1 and 48 in quarantine_row_numbers)
    missing_actuals_not_zero_filled_flag = _missing_actuals_preserved_from_sources(
        preview_rows_frame=preview_rows_frame,
        resolved_rows_frame=resolved_rows_frame,
        draft_rows_frame=draft_rows_frame,
        rules_lookup=rules_lookup,
    )
    no_silent_null_to_zero_coercion_flag = missing_actuals_not_zero_filled_flag
    production_fields_unchanged_flag = int(
        all(
            field_name in resolved_rows_frame.columns
            and field_name in draft_rows_frame.columns
            and _series_equal(resolved_rows_frame[field_name], draft_rows_frame[field_name])
            for field_name in PRODUCTION_FIELDS
        )
    )
    stage12_unchanged_flag = int(
        all(
            field_name in resolved_rows_frame.columns
            and field_name in draft_rows_frame.columns
            and _series_equal(resolved_rows_frame[field_name], draft_rows_frame[field_name])
            for field_name in STAGE12_FIELDS
        )
    )
    no_duplicate_source_rows_flag = int(
        "source_row_id" in draft_rows_frame.columns and not draft_rows_frame["source_row_id"].astype(str).duplicated().any()
    )
    numeric_fields_parseable_flag, numeric_fields_parseable_details = _numeric_parseable(draft_rows_frame)
    actual_outcome_fields_present_flag = int(all(field_name in draft_rows_frame.columns for field_name in ACTUAL_OUTCOME_FIELDS))
    economics_fields_present_or_derived_flag = int(
        all(field_name in draft_rows_frame.columns or field_name in derived_lookup for field_name in ECONOMICS_FIELDS)
    )
    production_guardrail_status = (
        "PASS"
        if resolution_validation_lookup.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL") == "PASS"
        and production_fields_unchanged_flag
        else "FAIL"
    )
    stage12_guardrail_status = (
        "PASS"
        if resolution_validation_lookup.get("STAGE12_GUARDRAIL_STATUS", "FAIL") == "PASS"
        and stage12_unchanged_flag
        else "FAIL"
    )
    missing_actual_zero_fill_flag = int(not missing_actuals_not_zero_filled_flag or not no_silent_null_to_zero_coercion_flag)

    if production_guardrail_status != "PASS" or stage12_guardrail_status != "PASS":
        draft_status = REVIEW_PACKET_DRAFT_BLOCKED_GUARDRAIL_FAILURE
    elif not required_fields_complete_flag:
        draft_status = REVIEW_PACKET_DRAFT_BLOCKED_MISSING_REQUIRED_FIELDS
    elif not row_count_conservation_flag:
        draft_status = REVIEW_PACKET_DRAFT_BLOCKED_ROW_COUNT_MISMATCH
    elif missing_actual_zero_fill_flag:
        draft_status = REVIEW_PACKET_DRAFT_BLOCKED_MISSING_ACTUAL_ZERO_FILL
    elif len(preview_quarantine_frame.index) > 0:
        draft_status = REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE
    else:
        draft_status = REVIEW_PACKET_DRAFT_READY_FOR_GOVERNED_REBUILD_VALIDATION

    draft_rows_frame["schema_mapping_status"] = draft_status
    governed_rebuild_validation_can_be_authored_next = int(
        draft_status
        in {
            REVIEW_PACKET_DRAFT_READY_FOR_GOVERNED_REBUILD_VALIDATION,
            REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE,
        }
    )

    field_lineage_rows: list[dict[str, object]] = []
    for field_name in DRAFT_FIELD_ORDER:
        source_artifact = RESOLUTION_ROWS_FILE_NAME
        source_column = field_name
        lineage_type = "PASSTHROUGH_RESOLVED_SCHEMA"
        derivation_formula = ""
        upstream_rule = ""
        notes = "Copied unchanged from the resolved schema rows."
        if field_name == "schema_mapping_status":
            source_artifact = OUTPUT_FOLDER_NAME
            lineage_type = "RUNTIME_STATUS_OVERRIDE"
            derivation_formula = "schema_mapping_status = review_packet_draft_status"
            upstream_rule = "diagnostics-only draft readiness"
            notes = "Draft stage stamps the diagnostics-only packet readiness status."
        elif field_name in rules_lookup:
            rule = rules_lookup[field_name]
            source_artifact = PREVIEW_ROWS_FILE_NAME
            source_column = _normalize_text(rule.get("selected_source_column")) or field_name
            derivation_formula = _normalize_text(rule.get("derivation_formula"))
            upstream_rule = _normalize_text(rule.get("preferred_source_column"))
            notes = _normalize_text(rule.get("resolution_reason"))
            lineage_type = (
                "AMBIGUITY_RESOLUTION_DERIVED"
                if _normalize_text(rule.get("resolution_status")) == "AMBIGUITY_RESOLVED_WITH_DERIVATION"
                else "AMBIGUITY_RESOLUTION_DIRECT"
            )
        elif field_name in derived_lookup:
            derived = derived_lookup[field_name]
            source_artifact = DERIVED_FIELDS_FILE_NAME
            source_column = _normalize_text(derived.get("source_columns"))
            lineage_type = "DERIVED_FIELD"
            derivation_formula = _normalize_text(derived.get("derivation_formula"))
            upstream_rule = _normalize_text(derived.get("source_columns"))
            notes = _normalize_text(derived.get("notes"))
        field_lineage_rows.append(
            {
                "draft_field": field_name,
                "source_artifact": source_artifact,
                "source_column": source_column,
                "lineage_type": lineage_type,
                "derivation_formula": derivation_formula,
                "upstream_rule": upstream_rule,
                "notes": notes,
            }
        )
    field_lineage_frame = pd.DataFrame(field_lineage_rows, columns=FIELD_LINEAGE_COLUMNS)

    quality_checks_frame = pd.DataFrame(
        [
            _quality_check_row(
                "required_field_completeness",
                "PASS" if required_fields_complete_flag else "FAIL",
                required_fields_complete_flag,
                "Required draft fields are present, and non-nullable fields remain populated.",
            ),
            _quality_check_row(
                "row_count_conservation",
                "PASS" if row_count_conservation_flag else "FAIL",
                row_count_conservation_flag,
                f"preview_rows={len(preview_rows_frame.index)}, mapping_rows={len(mapping_rows_frame.index)}, resolved_rows={len(resolved_rows_frame.index)}, draft_rows={len(draft_rows_frame.index)}",
            ),
            _quality_check_row(
                "quarantine_preservation",
                "PASS" if quarantine_preserved_flag else "FAIL",
                quarantine_preserved_flag,
                f"quarantine_rows={len(preview_quarantine_frame.index)}, quarantine_row_48_present={int(48 in quarantine_row_numbers)}",
            ),
            _quality_check_row(
                "missing_actuals_not_zero_filled",
                "PASS" if missing_actuals_not_zero_filled_flag else "FAIL",
                missing_actuals_not_zero_filled_flag,
                "Missing actuals remain blank rather than being zero-filled.",
            ),
            _quality_check_row(
                "production_fields_unchanged",
                "PASS" if production_fields_unchanged_flag else "FAIL",
                production_fields_unchanged_flag,
                "Production-order fields are copied unchanged from the resolved schema rows.",
            ),
            _quality_check_row(
                "stage12_unchanged",
                "PASS" if stage12_unchanged_flag else "FAIL",
                stage12_unchanged_flag,
                "Stage 12 fields are copied unchanged from the resolved schema rows.",
            ),
            _quality_check_row(
                "no_duplicate_source_rows",
                "PASS" if no_duplicate_source_rows_flag else "FAIL",
                no_duplicate_source_rows_flag,
                "Draft rows retain a one-to-one relationship with source_row_id.",
            ),
            _quality_check_row(
                "no_silent_null_to_zero_coercion",
                "PASS" if no_silent_null_to_zero_coercion_flag else "FAIL",
                no_silent_null_to_zero_coercion_flag,
                "Blank numeric values remain blank and are not silently coerced to zero.",
            ),
            _quality_check_row(
                "numeric_fields_parseable",
                "PASS" if numeric_fields_parseable_flag else "FAIL",
                numeric_fields_parseable_flag,
                numeric_fields_parseable_details,
            ),
            _quality_check_row(
                "actual_outcome_fields_present",
                "PASS" if actual_outcome_fields_present_flag else "FAIL",
                actual_outcome_fields_present_flag,
                "All actual outcome draft fields are present.",
            ),
            _quality_check_row(
                "economics_fields_present_or_derived",
                "PASS" if economics_fields_present_or_derived_flag else "FAIL",
                economics_fields_present_or_derived_flag,
                "Economics fields are present directly or supported by upstream derived-field definitions.",
            ),
        ],
        columns=QUALITY_CHECK_COLUMNS,
    )

    summary_frame = pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION", selection.promotion_key, "Promotion selected for the diagnostics-only governed review-packet draft."),
            _summary_row("DRAFT_STATUS", draft_status, "Overall diagnostics-only review-packet draft status."),
            _summary_row("DRAFT_ROW_COUNT", len(draft_rows_frame.index), "Draft review-packet row count."),
            _summary_row("QUARANTINE_ROW_COUNT", len(preview_quarantine_frame.index), "Quarantine row count preserved separately from the draft rows."),
            _summary_row("REQUIRED_FIELDS_COMPLETE_FLAG", required_fields_complete_flag, "Whether all required fields are present and non-nullable fields remain populated."),
            _summary_row("MISSING_ACTUAL_ZERO_FILL_FLAG", missing_actual_zero_fill_flag, "1 means blank actuals were coerced to zero; 0 means blanks were preserved."),
            _summary_row("ROW_COUNT_CONSERVATION_FLAG", row_count_conservation_flag, "Whether preview, mapping, resolved, and draft row counts all match."),
            _summary_row("PRODUCTION_GUARDRAIL_STATUS", production_guardrail_status, "Production-order guardrail status inherited and re-validated at the draft stage."),
            _summary_row("STAGE12_GUARDRAIL_STATUS", stage12_guardrail_status, "Stage 12 guardrail status inherited and re-validated at the draft stage."),
            _summary_row(
                "GOVERNED_REBUILD_VALIDATION_CAN_BE_AUTHORED_NEXT",
                governed_rebuild_validation_can_be_authored_next,
                "Whether the next diagnostics-only step can author governed rebuild validation without running the rebuild itself.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Materialized Source Review-Packet Draft",
            "",
            "This is a diagnostics-only governed review-packet draft.",
            "This does not start training.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "This does not promote auto-ordering.",
            "This does not promote shadow rules.",
            "This does not run the full governed review rebuild.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "This keeps quarantine row 48 separate.",
            "",
            f"Selected promotion: {selection.promotion_key}",
            f"Draft status: {draft_status}",
            f"Draft row count: {len(draft_rows_frame.index)}",
            f"Quarantine row count: {len(preview_quarantine_frame.index)}",
            f"Required fields complete flag: {required_fields_complete_flag}",
            f"Missing actual zero-fill flag: {missing_actual_zero_fill_flag}",
            f"Row-count conservation flag: {row_count_conservation_flag}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Governed rebuild validation can be authored next: {governed_rebuild_validation_can_be_authored_next}",
            "",
            "## Recommendation",
            (
                "Author diagnostics-only governed rebuild validation next, while continuing to keep quarantine row 48 separate and without running the governed rebuild itself."
                if governed_rebuild_validation_can_be_authored_next
                else "Do not author governed rebuild validation yet; one or more review-packet draft checks remain blocked."
            ),
        ]
    ).strip()

    return PromotionsMaterializedSourceReviewPacketDraftResult(
        selected_promotion=selection,
        draft_status=draft_status,
        draft_rows_frame=draft_rows_frame,
        quarantine_rows_frame=preview_quarantine_frame,
        schema_validation_frame=schema_validation_frame,
        field_lineage_frame=field_lineage_frame,
        quality_checks_frame=quality_checks_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_review_packet_draft(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceReviewPacketDraftArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_review_packet_draft(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    rows_csv_path = output_root_path / "materialized_source_review_packet_draft_rows.csv"
    quarantine_rows_csv_path = output_root_path / "materialized_source_review_packet_draft_quarantine_rows.csv"
    schema_validation_csv_path = output_root_path / "materialized_source_review_packet_draft_schema_validation.csv"
    field_lineage_csv_path = output_root_path / "materialized_source_review_packet_draft_field_lineage.csv"
    quality_checks_csv_path = output_root_path / "materialized_source_review_packet_draft_quality_checks.csv"
    summary_csv_path = output_root_path / "materialized_source_review_packet_draft_summary.csv"
    memo_md_path = output_root_path / "materialized_source_review_packet_draft_memo.md"

    result.draft_rows_frame.to_csv(rows_csv_path, index=False)
    result.quarantine_rows_frame.to_csv(quarantine_rows_csv_path, index=False)
    result.schema_validation_frame.to_csv(schema_validation_csv_path, index=False)
    result.field_lineage_frame.to_csv(field_lineage_csv_path, index=False)
    result.quality_checks_frame.to_csv(quality_checks_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceReviewPacketDraftArtifacts(
        output_root=str(output_root_path),
        rows_csv_path=str(rows_csv_path),
        quarantine_rows_csv_path=str(quarantine_rows_csv_path),
        schema_validation_csv_path=str(schema_validation_csv_path),
        field_lineage_csv_path=str(field_lineage_csv_path),
        quality_checks_csv_path=str(quality_checks_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only governed review-packet draft from the resolved materialized source schema."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_review_packet_draft(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary_frame)
    print("selected_promotion", _normalize_text(metrics.get("SELECTED_PROMOTION", "")))
    print("draft_status", _normalize_text(metrics.get("DRAFT_STATUS", "")))
    print("draft_row_count", _normalize_text(metrics.get("DRAFT_ROW_COUNT", 0)))
    print("quarantine_row_count", _normalize_text(metrics.get("QUARANTINE_ROW_COUNT", 0)))
    print("required_fields_complete_flag", _normalize_text(metrics.get("REQUIRED_FIELDS_COMPLETE_FLAG", 0)))
    print("missing_actual_zero_fill_flag", _normalize_text(metrics.get("MISSING_ACTUAL_ZERO_FILL_FLAG", 0)))
    print("row_count_conservation_flag", _normalize_text(metrics.get("ROW_COUNT_CONSERVATION_FLAG", 0)))
    print("production_guardrail_status", _normalize_text(metrics.get("PRODUCTION_GUARDRAIL_STATUS", "")))
    print("stage12_guardrail_status", _normalize_text(metrics.get("STAGE12_GUARDRAIL_STATUS", "")))
    print(
        "governed_rebuild_validation_can_be_authored_next",
        _normalize_text(metrics.get("GOVERNED_REBUILD_VALIDATION_CAN_BE_AUTHORED_NEXT", 0)),
    )
    print("materialized_source_review_packet_draft_rows", artifacts.rows_csv_path)
    print("materialized_source_review_packet_draft_quarantine_rows", artifacts.quarantine_rows_csv_path)
    print("materialized_source_review_packet_draft_schema_validation", artifacts.schema_validation_csv_path)
    print("materialized_source_review_packet_draft_field_lineage", artifacts.field_lineage_csv_path)
    print("materialized_source_review_packet_draft_quality_checks", artifacts.quality_checks_csv_path)
    print("materialized_source_review_packet_draft_summary", artifacts.summary_csv_path)
    print("materialized_source_review_packet_draft_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())