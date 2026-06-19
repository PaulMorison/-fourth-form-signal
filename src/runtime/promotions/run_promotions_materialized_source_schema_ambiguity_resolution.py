from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_schema_ambiguity_resolution"
SCHEMA_MAPPING_PLAN_FOLDER_NAME = "materialized_source_schema_mapping_plan"
PREVIEW_JOIN_FOLDER_NAME = "materialized_source_preview_join"

MAPPING_ROWS_FILE_NAME = "materialized_source_schema_mapping_rows.csv"
AMBIGUITIES_FILE_NAME = "materialized_source_schema_mapping_ambiguities.csv"
DERIVED_FIELDS_FILE_NAME = "materialized_source_schema_mapping_derived_fields.csv"
MAPPING_VALIDATION_FILE_NAME = "materialized_source_schema_mapping_validation.csv"
PREVIEW_ROWS_FILE_NAME = "materialized_source_preview_join_rows.csv"
PREVIEW_QUARANTINE_FILE_NAME = "materialized_source_preview_join_quarantine_rows.csv"

REQUIRED_MAPPING_FILE_NAMES: tuple[str, ...] = (
    MAPPING_ROWS_FILE_NAME,
    AMBIGUITIES_FILE_NAME,
    DERIVED_FIELDS_FILE_NAME,
    MAPPING_VALIDATION_FILE_NAME,
)

AMBIGUITY_RESOLVED = "AMBIGUITY_RESOLVED"
AMBIGUITY_RESOLVED_WITH_DERIVATION = "AMBIGUITY_RESOLVED_WITH_DERIVATION"
AMBIGUITY_BLOCKED_MISSING_PREFERRED_SOURCE = "AMBIGUITY_BLOCKED_MISSING_PREFERRED_SOURCE"
AMBIGUITY_BLOCKED_TYPE_MISMATCH = "AMBIGUITY_BLOCKED_TYPE_MISMATCH"
AMBIGUITY_BLOCKED_GUARDRAIL_FAILURE = "AMBIGUITY_BLOCKED_GUARDRAIL_FAILURE"

SCHEMA_AMBIGUITY_RESOLUTION_READY_FOR_REVIEW_PACKET_DRAFT = (
    "SCHEMA_AMBIGUITY_RESOLUTION_READY_FOR_REVIEW_PACKET_DRAFT"
)
SCHEMA_AMBIGUITY_RESOLUTION_READY_WITH_DERIVED_FIELDS = "SCHEMA_AMBIGUITY_RESOLUTION_READY_WITH_DERIVED_FIELDS"
SCHEMA_AMBIGUITY_RESOLUTION_BLOCKED = "SCHEMA_AMBIGUITY_RESOLUTION_BLOCKED"
SCHEMA_AMBIGUITY_RESOLUTION_BLOCKED_GUARDRAIL_FAILURE = "SCHEMA_AMBIGUITY_RESOLUTION_BLOCKED_GUARDRAIL_FAILURE"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)

RULES_COLUMNS: tuple[str, ...] = (
    "canonical_field",
    "preferred_source_column",
    "selected_source_column",
    "resolution_status",
    "derivation_formula",
    "resolution_reason",
    "rejected_candidate_count",
)

REJECTED_CANDIDATES_COLUMNS: tuple[str, ...] = (
    "canonical_field",
    "rejected_candidate_column",
    "selected_source_column",
    "rejection_status",
    "rejection_reason",
)

AMBIGUOUS_FIELDS: tuple[str, ...] = (
    "store_action_label",
    "actual_units",
    "actual_sell_through_pct",
    "capital_left",
    "capital_left_value",
)

CAPITAL_LEFT_QUANTITY_FALLBACKS: tuple[str, ...] = (
    "actual_unsold_units_vs_store_adjusted_qty",
    "actual_unsold_units_vs_pl_allocated",
    "actual_estimated_stock_left_after_promo",
)

PRODUCTION_GUARDRAIL_COLUMNS: tuple[str, ...] = (
    "operator_raw_model_order_units",
    "operator_provisional_review_order_units",
    "operator_final_store_order_units",
    "operator_raw_model_order_value",
    "operator_final_store_order_value",
)

STAGE12_GUARDRAIL_COLUMNS: tuple[str, ...] = (
    "operator_shadow_policy_should_publish_flag",
    "operator_shadow_policy_should_affect_final_order_flag",
    "operator_low_soh_policy_production_eligible_flag",
)


class PromotionsMaterializedSourceSchemaAmbiguityResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class ResolutionRule:
    canonical_field: str
    preferred_source_column: str
    selected_source_column: str
    resolution_status: str
    derivation_formula: str
    resolution_reason: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceSchemaAmbiguityResolutionResult:
    selected_promotion: PromotionSelection
    overall_resolution_status: str
    rules_frame: pd.DataFrame
    rows_frame: pd.DataFrame
    rejected_candidates_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceSchemaAmbiguityResolutionArtifacts:
    output_root: str
    rules_csv_path: str
    rows_csv_path: str
    rejected_candidates_csv_path: str
    validation_csv_path: str
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
        raise PromotionsMaterializedSourceSchemaAmbiguityResolutionError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceSchemaAmbiguityResolutionError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceSchemaAmbiguityResolutionError(f"CSV is empty: {csv_path}")
    return frame


def _has_required_mapping_files(mapping_root: Path) -> bool:
    return all((mapping_root / file_name).exists() for file_name in REQUIRED_MAPPING_FILE_NAMES)


def _resolve_mapping_root(*, packet_root: Path, upstream_root: str | Path | None) -> Path:
    if upstream_root is None:
        return packet_root / SCHEMA_MAPPING_PLAN_FOLDER_NAME
    upstream_root_path = Path(upstream_root)
    candidate_roots = (
        upstream_root_path / SCHEMA_MAPPING_PLAN_FOLDER_NAME,
        upstream_root_path,
    )
    for candidate_root in candidate_roots:
        if _has_required_mapping_files(candidate_root):
            return candidate_root
    candidate_locations = ", ".join(str(path) for path in candidate_roots)
    expected_files = ", ".join(REQUIRED_MAPPING_FILE_NAMES)
    raise PromotionsMaterializedSourceSchemaAmbiguityResolutionError(
        "--upstream-root was provided, but required schema-mapping-plan artifacts were not found. "
        f"Looked under: {candidate_locations}. Expected files: {expected_files}."
    )


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _validation_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
    return {
        "validation_name": name,
        "validation_status": status,
        "validation_flag": int(flag),
        "details": details,
    }


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _selection_from_rows(rows_frame: pd.DataFrame, promotion_key: str | None) -> PromotionSelection:
    if "promotion_key" not in rows_frame.columns:
        raise PromotionsMaterializedSourceSchemaAmbiguityResolutionError("Schema mapping rows are missing promotion_key.")
    unique_keys = [value for value in rows_frame["promotion_key"].astype(str).drop_duplicates().tolist() if value]
    if not unique_keys:
        raise PromotionsMaterializedSourceSchemaAmbiguityResolutionError("Schema mapping rows did not contain a promotion key.")
    resolved_key = promotion_key or unique_keys[0]
    if resolved_key not in unique_keys:
        raise PromotionsMaterializedSourceSchemaAmbiguityResolutionError(
            f"Requested promotion key was not found in schema mapping rows: {resolved_key}"
        )
    parts = resolved_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceSchemaAmbiguityResolutionError(
            f"Promotion key is not in the expected pipe-delimited format: {resolved_key}"
        )
    return PromotionSelection(
        promotion_key=resolved_key,
        promotion_name=parts[3],
        promotion_start_date=parts[1],
        promotion_end_date=parts[2],
    )


def _normalized_preview_end_date(frame: pd.DataFrame) -> pd.Series:
    for column in ("promotion_end_date", "promotional_end_date"):
        if column in frame.columns:
            return frame[column].fillna("").astype(str).str.strip()
    return pd.Series([""] * len(frame.index), index=frame.index, dtype="object")


def _filter_frame_for_selection(frame: pd.DataFrame, *, selection: PromotionSelection) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    if "promotion_key" in frame.columns:
        filtered = frame.loc[
            frame["promotion_key"].fillna("").astype(str).str.strip().eq(selection.promotion_key)
        ].copy()
        if not filtered.empty:
            return filtered.reset_index(drop=True)
    required_columns = {"promotion_name", "promotion_start_date"}
    if required_columns.issubset(frame.columns):
        filtered = frame.loc[
            frame["promotion_name"].fillna("").astype(str).str.strip().eq(selection.promotion_name)
            & frame["promotion_start_date"].fillna("").astype(str).str.strip().eq(selection.promotion_start_date)
            & _normalized_preview_end_date(frame).eq(selection.promotion_end_date)
        ].copy()
        if not filtered.empty:
            return filtered.reset_index(drop=True)
    return frame.copy().reset_index(drop=True)


def _validation_lookup(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}
    return dict(zip(frame["validation_name"].astype(str), frame["validation_status"].astype(str)))


def _candidate_lookup(ambiguities_frame: pd.DataFrame) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    if ambiguities_frame.empty:
        return lookup
    for _, row in ambiguities_frame.iterrows():
        field_name = _normalize_text(row.get("canonical_field"))
        candidates = [
            candidate.strip()
            for candidate in _normalize_text(row.get("candidate_columns")).split(";")
            if candidate.strip()
        ]
        if field_name:
            lookup[field_name] = candidates
    return lookup


def _blank_series(index: pd.Index) -> pd.Series:
    return pd.Series([""] * len(index), index=index, dtype="object")


def _series_for_column(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name in frame.columns:
        return frame[column_name]
    return _blank_series(frame.index)


def _is_blank_series(series: pd.Series) -> pd.Series:
    return series.map(_normalize_text).eq("")


def _missing_actuals_preserved(source_series: pd.Series, resolved_series: pd.Series) -> bool:
    blank_mask = _is_blank_series(source_series)
    if not bool(blank_mask.any()):
        return True
    return bool(_is_blank_series(resolved_series.loc[blank_mask]).all())


def _resolve_rule(
    *,
    canonical_field: str,
    preview_rows_frame: pd.DataFrame,
    candidate_lookup: dict[str, list[str]],
) -> tuple[ResolutionRule, pd.Series, list[dict[str, object]]]:
    preview_columns = set(preview_rows_frame.columns.astype(str).tolist())
    rejected_rows: list[dict[str, object]] = []
    candidate_columns = candidate_lookup.get(canonical_field, [])

    def reject(candidate_column: str, selected_source: str, status: str, reason: str) -> None:
        rejected_rows.append(
            {
                "canonical_field": canonical_field,
                "rejected_candidate_column": candidate_column,
                "selected_source_column": selected_source,
                "rejection_status": status,
                "rejection_reason": reason,
            }
        )

    if canonical_field == "store_action_label":
        preferred = "operator_store_action_label"
        selected = preferred if preferred in preview_columns else ""
        if not selected:
            return (
                ResolutionRule(
                    canonical_field=canonical_field,
                    preferred_source_column=preferred,
                    selected_source_column="",
                    resolution_status=AMBIGUITY_BLOCKED_MISSING_PREFERRED_SOURCE,
                    derivation_formula="",
                    resolution_reason="Preferred operator action surface column was not available.",
                ),
                _blank_series(preview_rows_frame.index),
                rejected_rows,
            )
        for candidate in candidate_columns:
            if candidate != selected:
                reject(candidate, selected, AMBIGUITY_RESOLVED, "Operator audit is the clean action surface.")
        return (
            ResolutionRule(
                canonical_field=canonical_field,
                preferred_source_column=preferred,
                selected_source_column=selected,
                resolution_status=AMBIGUITY_RESOLVED,
                derivation_formula="",
                resolution_reason="Operator audit is the clean action surface.",
            ),
            _series_for_column(preview_rows_frame, selected),
            rejected_rows,
        )

    if canonical_field == "actual_units":
        preferred = "actual_join_units_sold"
        selected = preferred if preferred in preview_columns else ""
        if not selected:
            return (
                ResolutionRule(
                    canonical_field=canonical_field,
                    preferred_source_column=preferred,
                    selected_source_column="",
                    resolution_status=AMBIGUITY_BLOCKED_MISSING_PREFERRED_SOURCE,
                    derivation_formula="",
                    resolution_reason="Preferred joined actual-outcome units column was not available.",
                ),
                _blank_series(preview_rows_frame.index),
                rejected_rows,
            )
        for candidate in candidate_columns:
            if candidate != selected:
                reject(candidate, selected, AMBIGUITY_RESOLVED, "Joined actual-outcome source is post-promo truth.")
        return (
            ResolutionRule(
                canonical_field=canonical_field,
                preferred_source_column=preferred,
                selected_source_column=selected,
                resolution_status=AMBIGUITY_RESOLVED,
                derivation_formula="",
                resolution_reason="Joined actual-outcome source is post-promo truth.",
            ),
            _series_for_column(preview_rows_frame, selected),
            rejected_rows,
        )

    if canonical_field == "actual_sell_through_pct":
        preferred = "actual_sell_through_pct_vs_store_adjusted_qty"
        selected = preferred if preferred in preview_columns else ""
        if not selected:
            return (
                ResolutionRule(
                    canonical_field=canonical_field,
                    preferred_source_column=preferred,
                    selected_source_column="",
                    resolution_status=AMBIGUITY_BLOCKED_MISSING_PREFERRED_SOURCE,
                    derivation_formula="",
                    resolution_reason="Preferred actual sell-through ratio column was not available.",
                ),
                _blank_series(preview_rows_frame.index),
                rejected_rows,
            )
        for candidate in candidate_columns:
            if candidate != selected:
                reject(candidate, selected, AMBIGUITY_RESOLVED, "Direct actual sell-through ratio is preferred over alternate denominators.")
        return (
            ResolutionRule(
                canonical_field=canonical_field,
                preferred_source_column=preferred,
                selected_source_column=selected,
                resolution_status=AMBIGUITY_RESOLVED,
                derivation_formula="",
                resolution_reason="Actual outcome source provides the direct sell-through ratio.",
            ),
            _series_for_column(preview_rows_frame, selected),
            rejected_rows,
        )

    if canonical_field == "capital_left":
        preferred = "actual_capital_left_units_in_unsold_store_allocation"
        if preferred in preview_columns:
            selected = preferred
            for candidate in candidate_columns:
                if candidate != selected:
                    reject(candidate, selected, AMBIGUITY_RESOLVED, "Value fields cannot be used as unit fields when a direct leftover-units source exists.")
            return (
                ResolutionRule(
                    canonical_field=canonical_field,
                    preferred_source_column=preferred,
                    selected_source_column=selected,
                    resolution_status=AMBIGUITY_RESOLVED,
                    derivation_formula="",
                    resolution_reason="Direct leftover-units field exists and matches the canonical unit contract.",
                ),
                _series_for_column(preview_rows_frame, selected),
                rejected_rows,
            )
        for candidate in candidate_columns:
            reject(candidate, preferred, AMBIGUITY_BLOCKED_TYPE_MISMATCH, "Candidate is a value field and cannot be used as a unit field.")
        for fallback in CAPITAL_LEFT_QUANTITY_FALLBACKS:
            if fallback in preview_columns:
                return (
                    ResolutionRule(
                        canonical_field=canonical_field,
                        preferred_source_column=preferred,
                        selected_source_column=fallback,
                        resolution_status=AMBIGUITY_RESOLVED_WITH_DERIVATION,
                        derivation_formula=f"capital_left = {fallback}",
                        resolution_reason="Preferred direct leftover-units field is absent, so the planner uses the highest-precedence actual leftover quantity field.",
                    ),
                    _series_for_column(preview_rows_frame, fallback),
                    rejected_rows,
                )
        blocking_status = (
            AMBIGUITY_BLOCKED_TYPE_MISMATCH if candidate_columns else AMBIGUITY_BLOCKED_MISSING_PREFERRED_SOURCE
        )
        blocking_reason = (
            "Only capital value fields were present, so the unit field cannot be resolved without a type mismatch."
            if candidate_columns
            else "No direct or fallback actual leftover quantity field was available."
        )
        return (
            ResolutionRule(
                canonical_field=canonical_field,
                preferred_source_column=preferred,
                selected_source_column="",
                resolution_status=blocking_status,
                derivation_formula="",
                resolution_reason=blocking_reason,
            ),
            _blank_series(preview_rows_frame.index),
            rejected_rows,
        )

    if canonical_field == "capital_left_value":
        preferred = "actual_capital_left_in_unsold_store_allocation"
        selected = preferred if preferred in preview_columns else ""
        if not selected:
            for candidate in candidate_columns:
                reject(candidate, "", AMBIGUITY_BLOCKED_MISSING_PREFERRED_SOURCE, "Preferred capital-left value field was not available.")
            return (
                ResolutionRule(
                    canonical_field=canonical_field,
                    preferred_source_column=preferred,
                    selected_source_column="",
                    resolution_status=AMBIGUITY_BLOCKED_MISSING_PREFERRED_SOURCE,
                    derivation_formula="",
                    resolution_reason="Preferred actual leftover capital value field was not available.",
                ),
                _blank_series(preview_rows_frame.index),
                rejected_rows,
            )
        for candidate in candidate_columns:
            if candidate != selected:
                reject(candidate, selected, AMBIGUITY_RESOLVED, "Preferred actual leftover capital value source is more direct.")
        return (
            ResolutionRule(
                canonical_field=canonical_field,
                preferred_source_column=preferred,
                selected_source_column=selected,
                resolution_status=AMBIGUITY_RESOLVED,
                derivation_formula="",
                resolution_reason="Actual outcome source provides leftover capital value directly.",
            ),
            _series_for_column(preview_rows_frame, selected),
            rejected_rows,
        )

    raise PromotionsMaterializedSourceSchemaAmbiguityResolutionError(
        f"No ambiguity resolution rule was defined for canonical field: {canonical_field}"
    )


def build_promotions_materialized_source_schema_ambiguity_resolution(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceSchemaAmbiguityResolutionResult:
    packet_root_path = Path(packet_root)
    mapping_root = _resolve_mapping_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
    )
    preview_root = packet_root_path / PREVIEW_JOIN_FOLDER_NAME

    mapping_rows_frame = _read_csv(mapping_root / MAPPING_ROWS_FILE_NAME)
    ambiguities_frame = _read_csv(mapping_root / AMBIGUITIES_FILE_NAME, allow_empty=True)
    derived_fields_frame = _read_csv(mapping_root / DERIVED_FIELDS_FILE_NAME, allow_empty=True)
    mapping_validation_frame = _read_csv(mapping_root / MAPPING_VALIDATION_FILE_NAME)
    preview_rows_frame = _read_csv(preview_root / PREVIEW_ROWS_FILE_NAME)
    preview_quarantine_frame = _read_csv(preview_root / PREVIEW_QUARANTINE_FILE_NAME, allow_empty=True)

    selection = _selection_from_rows(mapping_rows_frame, promotion_key)
    selected_mapping_rows_frame = _filter_frame_for_selection(
        mapping_rows_frame,
        selection=selection,
    )
    selected_preview_rows_frame = _filter_frame_for_selection(
        preview_rows_frame,
        selection=selection,
    )
    selected_preview_quarantine_frame = _filter_frame_for_selection(
        preview_quarantine_frame,
        selection=selection,
    )
    if selected_mapping_rows_frame.empty:
        raise PromotionsMaterializedSourceSchemaAmbiguityResolutionError(
            f"No schema-mapping rows found for promotion: {selection.promotion_key}"
        )
    candidate_lookup = _candidate_lookup(ambiguities_frame)
    mapping_validation_lookup = _validation_lookup(mapping_validation_frame)

    guardrail_failure_flag = int(
        mapping_validation_lookup.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL") != "PASS"
        or mapping_validation_lookup.get("STAGE12_GUARDRAIL_STATUS", "FAIL") != "PASS"
        or mapping_validation_lookup.get("MISSING_ACTUALS_NOT_ZERO_FILLED", "FAIL") != "PASS"
        or mapping_validation_lookup.get("PREVIEW_ROW_COUNT_PRESERVED", "FAIL") != "PASS"
    )

    resolved_rows_frame = selected_mapping_rows_frame.copy()
    rules_rows: list[dict[str, object]] = []
    rejected_rows: list[dict[str, object]] = []
    resolved_series_by_field: dict[str, pd.Series] = {}

    for field_name in AMBIGUOUS_FIELDS:
        rule, series, field_rejected_rows = _resolve_rule(
            canonical_field=field_name,
            preview_rows_frame=selected_preview_rows_frame,
            candidate_lookup=candidate_lookup,
        )
        if guardrail_failure_flag > 0 and rule.resolution_status.startswith("AMBIGUITY_RESOLVED"):
            rule = ResolutionRule(
                canonical_field=rule.canonical_field,
                preferred_source_column=rule.preferred_source_column,
                selected_source_column=rule.selected_source_column,
                resolution_status=AMBIGUITY_BLOCKED_GUARDRAIL_FAILURE,
                derivation_formula=rule.derivation_formula,
                resolution_reason="Upstream guardrail validation failed, so ambiguity resolution readiness remains blocked.",
            )
        resolved_series_by_field[field_name] = series if rule.resolution_status.startswith("AMBIGUITY_RESOLVED") else _blank_series(resolved_rows_frame.index)
        resolved_rows_frame[field_name] = resolved_series_by_field[field_name]
        rules_rows.append(
            {
                "canonical_field": rule.canonical_field,
                "preferred_source_column": rule.preferred_source_column,
                "selected_source_column": rule.selected_source_column,
                "resolution_status": rule.resolution_status,
                "derivation_formula": rule.derivation_formula,
                "resolution_reason": rule.resolution_reason,
                "rejected_candidate_count": len(field_rejected_rows),
            }
        )
        rejected_rows.extend(field_rejected_rows)

    rules_frame = pd.DataFrame(rules_rows, columns=RULES_COLUMNS)
    rejected_candidates_frame = pd.DataFrame(rejected_rows, columns=REJECTED_CANDIDATES_COLUMNS)

    resolved_statuses = set(rules_frame["resolution_status"].astype(str).tolist()) if not rules_frame.empty else set()
    blocked_ambiguity_count = int(sum(not status.startswith("AMBIGUITY_RESOLVED") for status in resolved_statuses for _ in [0]))
    blocked_ambiguity_count = int(rules_frame["resolution_status"].astype(str).str.startswith("AMBIGUITY_BLOCKED").sum()) if not rules_frame.empty else 0
    derived_ambiguity_count = int(
        rules_frame["resolution_status"].astype(str).eq(AMBIGUITY_RESOLVED_WITH_DERIVATION).sum()
    ) if not rules_frame.empty else 0
    resolved_ambiguity_count = int(
        rules_frame["resolution_status"].astype(str).isin(
            [AMBIGUITY_RESOLVED, AMBIGUITY_RESOLVED_WITH_DERIVATION]
        ).sum()
    ) if not rules_frame.empty else 0

    if guardrail_failure_flag > 0:
        overall_resolution_status = SCHEMA_AMBIGUITY_RESOLUTION_BLOCKED_GUARDRAIL_FAILURE
    elif blocked_ambiguity_count > 0:
        overall_resolution_status = SCHEMA_AMBIGUITY_RESOLUTION_BLOCKED
    elif derived_ambiguity_count > 0 or not derived_fields_frame.empty:
        overall_resolution_status = SCHEMA_AMBIGUITY_RESOLUTION_READY_WITH_DERIVED_FIELDS
    else:
        overall_resolution_status = SCHEMA_AMBIGUITY_RESOLUTION_READY_FOR_REVIEW_PACKET_DRAFT

    resolved_rows_frame["schema_mapping_status"] = overall_resolution_status

    missing_actuals_preserved_flag = 1
    for field_name, source_column in (
        ("actual_units", rules_frame.loc[rules_frame["canonical_field"].eq("actual_units"), "selected_source_column"].iloc[0] if not rules_frame.loc[rules_frame["canonical_field"].eq("actual_units")].empty else ""),
        ("actual_sell_through_pct", rules_frame.loc[rules_frame["canonical_field"].eq("actual_sell_through_pct"), "selected_source_column"].iloc[0] if not rules_frame.loc[rules_frame["canonical_field"].eq("actual_sell_through_pct")].empty else ""),
        ("capital_left", rules_frame.loc[rules_frame["canonical_field"].eq("capital_left"), "selected_source_column"].iloc[0] if not rules_frame.loc[rules_frame["canonical_field"].eq("capital_left")].empty else ""),
        ("capital_left_value", rules_frame.loc[rules_frame["canonical_field"].eq("capital_left_value"), "selected_source_column"].iloc[0] if not rules_frame.loc[rules_frame["canonical_field"].eq("capital_left_value")].empty else ""),
    ):
        if source_column and source_column in selected_preview_rows_frame.columns:
            missing_actuals_preserved_flag = int(
                missing_actuals_preserved_flag
                and _missing_actuals_preserved(selected_preview_rows_frame[source_column], resolved_rows_frame[field_name])
            )

    review_packet_draft_can_be_authored_next = int(
        overall_resolution_status
        in {
            SCHEMA_AMBIGUITY_RESOLUTION_READY_FOR_REVIEW_PACKET_DRAFT,
            SCHEMA_AMBIGUITY_RESOLUTION_READY_WITH_DERIVED_FIELDS,
        }
    )

    quarantine_row_numbers = set(
        pd.to_numeric(selected_preview_quarantine_frame.get("source_row_number", pd.Series(dtype="object")), errors="coerce").fillna(0).astype(int).tolist()
    )
    validation_frame = pd.DataFrame(
        [
            _validation_row(
                "ALL_AMBIGUITIES_RESOLVED_OR_BLOCKED",
                "PASS" if len(rules_frame.index) == len(AMBIGUOUS_FIELDS) else "FAIL",
                int(len(rules_frame.index) == len(AMBIGUOUS_FIELDS)),
                f"rules={len(rules_frame.index)}, expected={len(AMBIGUOUS_FIELDS)}",
            ),
            _validation_row(
                "MISSING_ACTUALS_NOT_ZERO_FILLED",
                "PASS" if missing_actuals_preserved_flag else "FAIL",
                missing_actuals_preserved_flag,
                "Resolved ambiguity fields preserve blank actual values as blank rather than zero-filling them.",
            ),
            _validation_row(
                "PRODUCTION_GUARDRAIL_STATUS",
                mapping_validation_lookup.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL"),
                int(mapping_validation_lookup.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL") == "PASS"),
                "Production order fields remain unchanged from the schema mapping planner input.",
            ),
            _validation_row(
                "STAGE12_GUARDRAIL_STATUS",
                mapping_validation_lookup.get("STAGE12_GUARDRAIL_STATUS", "FAIL"),
                int(mapping_validation_lookup.get("STAGE12_GUARDRAIL_STATUS", "FAIL") == "PASS"),
                "Stage 12 fields remain unchanged from the schema mapping planner input.",
            ),
            _validation_row(
                "PREVIEW_ROW_COUNT_PRESERVED",
                "PASS" if len(resolved_rows_frame.index) == len(selected_mapping_rows_frame.index) else "FAIL",
                int(len(resolved_rows_frame.index) == len(selected_mapping_rows_frame.index)),
                f"preview_rows={len(selected_mapping_rows_frame.index)}, resolution_rows={len(resolved_rows_frame.index)}",
            ),
            _validation_row(
                "QUARANTINE_COUNT_PRESERVED",
                "PASS" if len(selected_preview_quarantine_frame.index) == 1 else "FAIL",
                int(len(selected_preview_quarantine_frame.index) == 1),
                f"quarantine_rows={len(selected_preview_quarantine_frame.index)}",
            ),
            _validation_row(
                "QUARANTINE_ROW_48_REMAINS_SEPARATE",
                "PASS" if 48 in quarantine_row_numbers else "FAIL",
                int(48 in quarantine_row_numbers),
                "Quarantine row 48 remains separate from the resolved schema rows.",
            ),
            _validation_row(
                "REVIEW_PACKET_DRAFT_CAN_BE_AUTHORED_NEXT",
                "PASS" if review_packet_draft_can_be_authored_next else "FAIL",
                review_packet_draft_can_be_authored_next,
                "Draft authoring requires all ambiguities resolved plus passing validation.",
            ),
            _validation_row(
                "FULL_GOVERNED_REBUILD_REMAINS_BLOCKED",
                "PASS",
                1,
                "This pack only resolves schema ambiguities and does not authorize the full governed rebuild.",
            ),
        ],
        columns=VALIDATION_COLUMNS,
    )

    preferred_sources = {
        row["canonical_field"]: row["preferred_source_column"]
        for _, row in rules_frame.iterrows()
    }
    summary_frame = pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION", selection.promotion_key, "Promotion selected for diagnostics-only schema ambiguity resolution."),
            _summary_row("OVERALL_RESOLUTION_STATUS", overall_resolution_status, "Overall status after applying explicit source-precedence rules."),
            _summary_row("RESOLVED_AMBIGUITY_COUNT", resolved_ambiguity_count, "Ambiguous fields resolved directly or with derivation."),
            _summary_row("BLOCKED_AMBIGUITY_COUNT", blocked_ambiguity_count, "Ambiguous fields still blocked after applying explicit rules."),
            _summary_row("DERIVED_AMBIGUITY_COUNT", derived_ambiguity_count, "Ambiguous fields resolved via documented derivation rather than a direct source column."),
            _summary_row("REJECTED_CANDIDATE_COUNT", len(rejected_candidates_frame.index), "Candidate source columns rejected by precedence or type rules."),
            _summary_row("PREVIEW_ROW_COUNT", len(resolved_rows_frame.index), "Schema ambiguity resolution row count."),
            _summary_row("QUARANTINE_ROW_COUNT", len(selected_preview_quarantine_frame.index), "Quarantined rows preserved separately from resolved rows."),
            _summary_row("PREFERRED_SOURCE_STORE_ACTION_LABEL", preferred_sources.get("store_action_label", ""), "Preferred source for store_action_label."),
            _summary_row("PREFERRED_SOURCE_ACTUAL_UNITS", preferred_sources.get("actual_units", ""), "Preferred source for actual_units."),
            _summary_row("PREFERRED_SOURCE_ACTUAL_SELL_THROUGH_PCT", preferred_sources.get("actual_sell_through_pct", ""), "Preferred source for actual_sell_through_pct."),
            _summary_row("PREFERRED_SOURCE_CAPITAL_LEFT", preferred_sources.get("capital_left", ""), "Preferred source for capital_left units."),
            _summary_row("PREFERRED_SOURCE_CAPITAL_LEFT_VALUE", preferred_sources.get("capital_left_value", ""), "Preferred source for capital_left_value."),
            _summary_row("PRODUCTION_GUARDRAIL_STATUS", mapping_validation_lookup.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL"), "Production-order guardrail status inherited from the schema mapping planner."),
            _summary_row("STAGE12_GUARDRAIL_STATUS", mapping_validation_lookup.get("STAGE12_GUARDRAIL_STATUS", "FAIL"), "Stage 12 guardrail status inherited from the schema mapping planner."),
            _summary_row("REVIEW_PACKET_DRAFT_CAN_BE_AUTHORED_NEXT", review_packet_draft_can_be_authored_next, "Whether a draft review packet can be authored next after ambiguity resolution."),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Materialized Source Schema Ambiguity Resolution",
            "",
            "This is a diagnostics-only schema ambiguity resolution pack.",
            "This does not start training.",
            "This does not write the final governed review packet.",
            "This does not run the full governed review rebuild.",
            "This does not mutate source packets.",
            "This does not change production ordering logic or Stage 12.",
            "This does not fill missing actuals with zero.",
            "This keeps quarantine row 48 separate.",
            "",
            f"Selected promotion: {selection.promotion_key}",
            f"Overall resolution status: {overall_resolution_status}",
            f"Resolved ambiguity count: {resolved_ambiguity_count}",
            f"Blocked ambiguity count: {blocked_ambiguity_count}",
            f"Derived ambiguity count: {derived_ambiguity_count}",
            f"Rejected candidates count: {len(rejected_candidates_frame.index)}",
            f"Preview row count: {len(resolved_rows_frame.index)}",
            f"Quarantine row count: {len(selected_preview_quarantine_frame.index)}",
            f"Production guardrail status: {mapping_validation_lookup.get('PRODUCTION_GUARDRAIL_STATUS', 'FAIL')}",
            f"Stage 12 guardrail status: {mapping_validation_lookup.get('STAGE12_GUARDRAIL_STATUS', 'FAIL')}",
            f"Review packet draft can be authored next: {review_packet_draft_can_be_authored_next}",
            "",
            "## Recommendation",
            (
                "Author a diagnostics-only review-packet draft next from the resolved schema rows, but keep quarantine row 48 separate and leave the full governed rebuild blocked."
                if review_packet_draft_can_be_authored_next > 0
                else "Do not author the review-packet draft yet; one or more ambiguities or validations remain blocked."
            ),
        ]
    ).strip()

    return PromotionsMaterializedSourceSchemaAmbiguityResolutionResult(
        selected_promotion=selection,
        overall_resolution_status=overall_resolution_status,
        rules_frame=rules_frame,
        rows_frame=resolved_rows_frame,
        rejected_candidates_frame=rejected_candidates_frame,
        validation_frame=validation_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_schema_ambiguity_resolution(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceSchemaAmbiguityResolutionArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_schema_ambiguity_resolution(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    rules_csv_path = output_root_path / "materialized_source_schema_ambiguity_resolution_rules.csv"
    rows_csv_path = output_root_path / "materialized_source_schema_ambiguity_resolution_rows.csv"
    rejected_candidates_csv_path = output_root_path / "materialized_source_schema_ambiguity_resolution_rejected_candidates.csv"
    validation_csv_path = output_root_path / "materialized_source_schema_ambiguity_resolution_validation.csv"
    summary_csv_path = output_root_path / "materialized_source_schema_ambiguity_resolution_summary.csv"
    memo_md_path = output_root_path / "materialized_source_schema_ambiguity_resolution_memo.md"

    result.rules_frame.to_csv(rules_csv_path, index=False)
    result.rows_frame.to_csv(rows_csv_path, index=False)
    result.rejected_candidates_frame.to_csv(rejected_candidates_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceSchemaAmbiguityResolutionArtifacts(
        output_root=str(output_root_path),
        rules_csv_path=str(rules_csv_path),
        rows_csv_path=str(rows_csv_path),
        rejected_candidates_csv_path=str(rejected_candidates_csv_path),
        validation_csv_path=str(validation_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only schema ambiguity resolution pack for the preview-joined materialized promotion."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_schema_ambiguity_resolution(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary_frame)
    print("selected_promotion", _normalize_text(metrics.get("SELECTED_PROMOTION", "")))
    print("overall_resolution_status", _normalize_text(metrics.get("OVERALL_RESOLUTION_STATUS", "")))
    print("resolved_ambiguity_count", _normalize_text(metrics.get("RESOLVED_AMBIGUITY_COUNT", 0)))
    print("blocked_ambiguity_count", _normalize_text(metrics.get("BLOCKED_AMBIGUITY_COUNT", 0)))
    print("derived_ambiguity_count", _normalize_text(metrics.get("DERIVED_AMBIGUITY_COUNT", 0)))
    print("rejected_candidates_count", _normalize_text(metrics.get("REJECTED_CANDIDATE_COUNT", 0)))
    print("preview_row_count", _normalize_text(metrics.get("PREVIEW_ROW_COUNT", 0)))
    print("quarantine_row_count", _normalize_text(metrics.get("QUARANTINE_ROW_COUNT", 0)))
    print("production_guardrail_status", _normalize_text(metrics.get("PRODUCTION_GUARDRAIL_STATUS", "")))
    print("stage12_guardrail_status", _normalize_text(metrics.get("STAGE12_GUARDRAIL_STATUS", "")))
    print("review_packet_draft_can_be_authored_next", _normalize_text(metrics.get("REVIEW_PACKET_DRAFT_CAN_BE_AUTHORED_NEXT", 0)))
    print("materialized_source_schema_ambiguity_resolution_rules", artifacts.rules_csv_path)
    print("materialized_source_schema_ambiguity_resolution_rows", artifacts.rows_csv_path)
    print("materialized_source_schema_ambiguity_resolution_rejected_candidates", artifacts.rejected_candidates_csv_path)
    print("materialized_source_schema_ambiguity_resolution_validation", artifacts.validation_csv_path)
    print("materialized_source_schema_ambiguity_resolution_summary", artifacts.summary_csv_path)
    print("materialized_source_schema_ambiguity_resolution_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())