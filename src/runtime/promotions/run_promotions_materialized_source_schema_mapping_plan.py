from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_schema_mapping_plan"
PREVIEW_JOIN_FOLDER_NAME = "materialized_source_preview_join"
SPEC_PACK_FOLDER_NAME = "materialized_source_join_spec_pack"

PREVIEW_ROWS_FILE_NAME = "materialized_source_preview_join_rows.csv"
PREVIEW_QUARANTINE_FILE_NAME = "materialized_source_preview_join_quarantine_rows.csv"
PREVIEW_VALIDATION_FILE_NAME = "materialized_source_preview_join_validation.csv"
PREVIEW_LINEAGE_FILE_NAME = "materialized_source_preview_join_column_lineage.csv"
PREVIEW_SUMMARY_FILE_NAME = "materialized_source_preview_join_summary.csv"
SPEC_SUMMARY_FILE_NAME = "materialized_source_join_spec_summary.csv"

REQUIRED_PREVIEW_FILE_NAMES: tuple[str, ...] = (
    PREVIEW_ROWS_FILE_NAME,
    PREVIEW_QUARANTINE_FILE_NAME,
    PREVIEW_VALIDATION_FILE_NAME,
    PREVIEW_LINEAGE_FILE_NAME,
    PREVIEW_SUMMARY_FILE_NAME,
)

SCHEMA_MAPPING_READY_FOR_REVIEW_PACKET_DRAFT = "SCHEMA_MAPPING_READY_FOR_REVIEW_PACKET_DRAFT"
SCHEMA_MAPPING_READY_WITH_DERIVED_FIELDS = "SCHEMA_MAPPING_READY_WITH_DERIVED_FIELDS"
SCHEMA_MAPPING_NEEDS_REVIEW = "SCHEMA_MAPPING_NEEDS_REVIEW"
SCHEMA_MAPPING_BLOCKED_MISSING_REQUIRED_COLUMNS = "SCHEMA_MAPPING_BLOCKED_MISSING_REQUIRED_COLUMNS"
SCHEMA_MAPPING_BLOCKED_AMBIGUOUS_COLUMNS = "SCHEMA_MAPPING_BLOCKED_AMBIGUOUS_COLUMNS"
SCHEMA_MAPPING_BLOCKED_GUARDRAIL_FAILURE = "SCHEMA_MAPPING_BLOCKED_GUARDRAIL_FAILURE"

MAPPING_DIRECT = "DIRECT"
MAPPING_PREFIXED = "PREFIXED"
MAPPING_DERIVED = "DERIVED"
MAPPING_MISSING = "MISSING"
MAPPING_AMBIGUOUS = "AMBIGUOUS"

JOIN_KEY_STATUS_MATCHED = "MATCHED_APPROVED_PREVIEW_JOIN_KEY"
JOIN_KEY_STATUS_QUARANTINED = "QUARANTINED_MISSING_JOIN_KEY"

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

MISSING_COLUMNS_COLUMNS: tuple[str, ...] = (
    "canonical_field",
    "required_flag",
    "missing_reason",
    "blocking_flag",
    "notes",
)

DERIVED_FIELDS_COLUMNS: tuple[str, ...] = (
    "canonical_field",
    "derivation_formula",
    "source_columns",
    "review_required_flag",
    "notes",
)

AMBIGUITIES_COLUMNS: tuple[str, ...] = (
    "canonical_field",
    "candidate_columns",
    "preferred_column",
    "ambiguity_reason",
    "blocking_flag",
)

MAPPING_ROWS_METADATA_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "source_row_id",
    "join_key_status",
    "quarantine_flag",
    "schema_mapping_status",
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

CANONICAL_FIELD_ORDER: tuple[str, ...] = (
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

REQUIRED_IDENTITY_FIELDS: tuple[str, ...] = (
    "store_number",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "sku_number",
)

REQUIRED_ACTUAL_FIELDS: tuple[str, ...] = (
    "actual_units",
    "actual_gross_profit",
    "actual_sell_through_pct",
    "capital_left",
    "capital_left_value",
    "stockout_or_missed_demand_flag",
)

REQUIRED_ECONOMICS_FIELDS: tuple[str, ...] = (
    "promo_price",
    "promo_cost",
    "promo_gross_profit_per_unit",
    "gross_profit_represented",
    "capital_at_risk",
)


class PromotionsMaterializedSourceSchemaMappingPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class FieldMappingPlan:
    canonical_field: str
    mapping_status: str
    source_column: str
    source_columns: tuple[str, ...]
    derivation_formula: str
    ambiguity_reason: str
    notes: str
    blocking_flag: int
    review_required_flag: int


@dataclass(frozen=True)
class PromotionsMaterializedSourceSchemaMappingPlanResult:
    selected_promotion: PromotionSelection
    schema_mapping_status: str
    mapping_rows_frame: pd.DataFrame
    missing_columns_frame: pd.DataFrame
    derived_fields_frame: pd.DataFrame
    ambiguities_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str

    @property
    def rows_frame(self) -> pd.DataFrame:
        return self.mapping_rows_frame


@dataclass(frozen=True)
class PromotionsMaterializedSourceSchemaMappingPlanArtifacts:
    output_root: str
    mapping_rows_csv_path: str
    missing_columns_csv_path: str
    derived_fields_csv_path: str
    ambiguities_csv_path: str
    validation_csv_path: str
    summary_csv_path: str
    memo_md_path: str

    @property
    def rows_csv_path(self) -> str:
        return self.mapping_rows_csv_path


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
        raise PromotionsMaterializedSourceSchemaMappingPlanError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceSchemaMappingPlanError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceSchemaMappingPlanError(f"CSV is empty: {csv_path}")
    return frame


def _has_required_preview_files(preview_root: Path) -> bool:
    return all((preview_root / file_name).exists() for file_name in REQUIRED_PREVIEW_FILE_NAMES)


def _resolve_preview_root(*, packet_root: Path, upstream_root: str | Path | None) -> Path:
    if upstream_root is None:
        return packet_root / PREVIEW_JOIN_FOLDER_NAME
    upstream_root_path = Path(upstream_root)
    candidate_roots = (
        upstream_root_path / PREVIEW_JOIN_FOLDER_NAME,
        upstream_root_path,
    )
    for candidate_root in candidate_roots:
        if _has_required_preview_files(candidate_root):
            return candidate_root
    candidate_locations = ", ".join(str(path) for path in candidate_roots)
    expected_files = ", ".join(REQUIRED_PREVIEW_FILE_NAMES)
    raise PromotionsMaterializedSourceSchemaMappingPlanError(
        "--upstream-root was provided, but required preview-join artifacts were not found. "
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


def _selection_from_promotion_key(promotion_key: str) -> PromotionSelection:
    parts = promotion_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceSchemaMappingPlanError(
            f"Promotion key is not in the expected pipe-delimited format: {promotion_key}"
        )
    _, start_date, end_date, promotion_name = parts
    return PromotionSelection(
        promotion_key=promotion_key,
        promotion_name=promotion_name,
        promotion_start_date=start_date,
        promotion_end_date=end_date,
    )


def _resolve_selected_promotion_key(
    *,
    promotion_key: str | None,
    preview_summary_frame: pd.DataFrame,
    spec_summary_frame: pd.DataFrame,
) -> str:
    if promotion_key:
        return promotion_key
    preview_metrics = _metric_lookup(preview_summary_frame)
    selected = _normalize_text(preview_metrics.get("SELECTED_PROMOTION"))
    if selected:
        return selected
    spec_metrics = _metric_lookup(spec_summary_frame)
    selected = _normalize_text(spec_metrics.get("SELECTED_PROMOTION"))
    if selected:
        return selected
    raise PromotionsMaterializedSourceSchemaMappingPlanError(
        "Selected promotion could not be resolved from preview or spec inputs."
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


def _preferred_candidates(canonical_field: str) -> tuple[str, ...]:
    return {
        "store_number": ("store_number", "store_number_key"),
        "promotion_key": ("promotion_key",),
        "promotion_name": ("promotion_name",),
        "promotion_start_date": ("promotion_start_date", "promotion_start_date_date"),
        "promotion_end_date": ("promotion_end_date", "promotional_end_date", "promotional_end_date_date"),
        "sku_number": ("sku_number", "sku_number_key"),
        "sku_description": ("sku_description", "operator_sku_description", "actual_sku_description"),
        "expected_promo_demand": ("operator_expected_promo_demand", "actual_expected_promo_demand"),
        "recommended_order_units": ("operator_recommended_order_units",),
        "final_store_order_units": ("operator_final_store_order_units",),
        "store_action_label": ("operator_store_action_label", "operator_store_action_label_v2"),
        "store_action_reason": ("operator_store_action_reason", "operator_order_reconciliation_reason"),
        "demand_evidence_label": ("operator_demand_evidence_label",),
        "actual_units": ("actual_join_units_sold", "actual_units_sold", "actual_actual_units_sold"),
        "actual_gross_profit": ("actual_estimated_actual_gross_profit",),
        "actual_sell_through_pct": (
            "actual_sell_through_pct_vs_store_adjusted_qty",
            "actual_sell_through_pct_vs_total_stock_available",
            "actual_sell_through_pct_vs_pl_allocated",
        ),
        "capital_left": (
            "actual_capital_left_in_unsold_store_allocation",
            "actual_current_capital_left_unsold_value",
        ),
        "capital_left_value": (
            "actual_capital_left_in_unsold_store_allocation",
            "actual_current_capital_left_unsold_value",
        ),
        "promo_price": ("promo_price", "actual_promo_price"),
        "promo_cost": ("promo_cost_price", "actual_promo_cost_price"),
        "promo_gross_profit_per_unit": ("promo_gm_unit", "actual_promo_gm_unit"),
    }.get(canonical_field, ())


def _ambiguous_candidates(canonical_field: str, columns: Sequence[str]) -> tuple[str, ...]:
    ambiguous_patterns = {
        "store_action_label": ("operator_store_action_label", "operator_store_action_label_v2"),
        "actual_units": ("actual_join_units_sold", "actual_units_sold"),
        "actual_sell_through_pct": (
            "actual_sell_through_pct_vs_store_adjusted_qty",
            "actual_sell_through_pct_vs_total_stock_available",
            "actual_sell_through_pct_vs_pl_allocated",
        ),
        "capital_left": (
            "actual_capital_left_in_unsold_store_allocation",
            "actual_current_capital_left_unsold_value",
        ),
        "capital_left_value": (
            "actual_capital_left_in_unsold_store_allocation",
            "actual_current_capital_left_unsold_value",
        ),
    }
    candidates = tuple(column for column in ambiguous_patterns.get(canonical_field, ()) if column in columns)
    return candidates if len(candidates) > 1 else ()


def _resolve_plan_for_field(canonical_field: str, columns: Sequence[str]) -> FieldMappingPlan:
    preferred = tuple(column for column in _preferred_candidates(canonical_field) if column in columns)
    ambiguous = _ambiguous_candidates(canonical_field, columns)
    if canonical_field in {"promotion_key", "quarantine_flag", "source_row_id", "join_key_status", "schema_mapping_status"}:
        return FieldMappingPlan(
            canonical_field=canonical_field,
            mapping_status=MAPPING_DERIVED,
            source_column="",
            source_columns=(),
            derivation_formula="runtime-owned metadata",
            ambiguity_reason="",
            notes="Planner-owned metadata field.",
            blocking_flag=0,
            review_required_flag=0,
        )
    if canonical_field == "production_order_change_flag":
        return FieldMappingPlan(
            canonical_field=canonical_field,
            mapping_status=MAPPING_DERIVED,
            source_column="",
            source_columns=("operator_raw_model_order_units", "operator_final_store_order_units"),
            derivation_formula="int(operator_raw_model_order_units != operator_final_store_order_units)",
            ambiguity_reason="",
            notes="Diagnostics-only guardrail flag; does not mutate production ordering.",
            blocking_flag=0,
            review_required_flag=0,
        )
    if canonical_field == "stage_12_change_flag":
        return FieldMappingPlan(
            canonical_field=canonical_field,
            mapping_status=MAPPING_DERIVED,
            source_column="",
            source_columns=(
                "operator_shadow_policy_should_publish_flag",
                "operator_shadow_policy_should_affect_final_order_flag",
                "operator_low_soh_policy_production_eligible_flag",
            ),
            derivation_formula="int(any(stage12 publishability flag changed from source baseline))",
            ambiguity_reason="",
            notes="Diagnostics-only guardrail flag; should remain 0 for preview-derived mapping.",
            blocking_flag=0,
            review_required_flag=0,
        )
    if canonical_field == "stockout_or_missed_demand_flag":
        candidates = tuple(
            column
            for column in (
                "actual_current_missed_sales_risk_flag",
                "actual_shadow_missed_sales_risk_flag",
                "actual_review_oos_proxy_flag",
                "actual_current_oos_proxy_flag",
            )
            if column in columns
        )
        if not candidates:
            return FieldMappingPlan(
                canonical_field=canonical_field,
                mapping_status=MAPPING_MISSING,
                source_column="",
                source_columns=(),
                derivation_formula="",
                ambiguity_reason="",
                notes="No supported stockout or missed-demand signal was present.",
                blocking_flag=1,
                review_required_flag=1,
            )
        return FieldMappingPlan(
            canonical_field=canonical_field,
            mapping_status=MAPPING_DERIVED,
            source_column="",
            source_columns=candidates,
            derivation_formula="int(max(candidate flags) > 0)",
            ambiguity_reason="",
            notes="Derived from actual outcome missed-demand or out-of-stock proxy flags.",
            blocking_flag=0,
            review_required_flag=1,
        )
    if canonical_field == "gross_profit_represented":
        return FieldMappingPlan(
            canonical_field=canonical_field,
            mapping_status=MAPPING_DERIVED,
            source_column="",
            source_columns=("actual_estimated_actual_gross_profit",),
            derivation_formula="actual_estimated_actual_gross_profit",
            ambiguity_reason="",
            notes="Review-packet represented gross profit comes from joined actual-outcome gross profit.",
            blocking_flag=0,
            review_required_flag=0,
        )
    if canonical_field == "capital_at_risk":
        candidates = tuple(
            column
            for column in (
                "operator_capital_at_risk_adjusted_dollars",
                "actual_current_capital_at_risk",
                "actual_shadow_capital_at_risk",
                "actual_capital_left_in_unsold_store_allocation",
            )
            if column in columns
        )
        if not candidates:
            return FieldMappingPlan(
                canonical_field=canonical_field,
                mapping_status=MAPPING_MISSING,
                source_column="",
                source_columns=(),
                derivation_formula="",
                ambiguity_reason="",
                notes="No capital-at-risk candidate columns were present.",
                blocking_flag=1,
                review_required_flag=1,
            )
        return FieldMappingPlan(
            canonical_field=canonical_field,
            mapping_status=MAPPING_DERIVED,
            source_column="",
            source_columns=candidates,
            derivation_formula="prefer operator_capital_at_risk_adjusted_dollars else actual_current_capital_at_risk else actual_shadow_capital_at_risk else actual_capital_left_in_unsold_store_allocation",
            ambiguity_reason="",
            notes="Economics field requires preferred-source derivation rather than a bare exact match.",
            blocking_flag=0,
            review_required_flag=1,
        )
    if preferred:
        if len(ambiguous) > 1 and canonical_field in {"store_action_label", "actual_units", "actual_sell_through_pct", "capital_left", "capital_left_value"}:
            return FieldMappingPlan(
                canonical_field=canonical_field,
                mapping_status=MAPPING_AMBIGUOUS,
                source_column=preferred[0],
                source_columns=ambiguous,
                derivation_formula="",
                ambiguity_reason="Multiple plausible candidate columns exist; the planner prefers the first rule-defined source but keeps review visible.",
                notes="Planner can proceed, but a reviewer should confirm the preferred semantic source.",
                blocking_flag=1,
                review_required_flag=1,
            )
        mapping_status = MAPPING_DIRECT if preferred[0] == canonical_field else MAPPING_PREFIXED
        return FieldMappingPlan(
            canonical_field=canonical_field,
            mapping_status=mapping_status,
            source_column=preferred[0],
            source_columns=(preferred[0],),
            derivation_formula="",
            ambiguity_reason="",
            notes="Resolved through exact or preferred prefixed source-column match.",
            blocking_flag=0,
            review_required_flag=0,
        )
    return FieldMappingPlan(
        canonical_field=canonical_field,
        mapping_status=MAPPING_MISSING,
        source_column="",
        source_columns=(),
        derivation_formula="",
        ambiguity_reason="",
        notes="No supported direct, prefixed, or derived source rule resolved this canonical field.",
        blocking_flag=1,
        review_required_flag=1,
    )


def _ensure_promotion_key(frame: pd.DataFrame, selection: PromotionSelection) -> pd.DataFrame:
    enriched = frame.copy()
    if "promotion_key" not in enriched.columns:
        enriched.insert(1, "promotion_key", selection.promotion_key)
    else:
        enriched["promotion_key"] = enriched["promotion_key"].replace("", selection.promotion_key)
    return enriched


def _apply_plan_to_rows(
    preview_rows_frame: pd.DataFrame,
    *,
    selection: PromotionSelection,
    plans: dict[str, FieldMappingPlan],
) -> pd.DataFrame:
    source = _ensure_promotion_key(preview_rows_frame, selection)
    mapped = pd.DataFrame(index=source.index)
    for field_name in CANONICAL_FIELD_ORDER:
        plan = plans[field_name]
        if plan.mapping_status in {MAPPING_DIRECT, MAPPING_PREFIXED} and plan.source_column:
            mapped[field_name] = source[plan.source_column]
        elif field_name == "promotion_key":
            mapped[field_name] = selection.promotion_key
        elif field_name == "source_row_id":
            mapped[field_name] = source["source_row_number"]
        elif field_name == "join_key_status":
            mapped[field_name] = JOIN_KEY_STATUS_MATCHED
        elif field_name == "quarantine_flag":
            mapped[field_name] = 0
        elif field_name == "schema_mapping_status":
            mapped[field_name] = ""
        elif field_name == "production_order_change_flag":
            raw_units = pd.to_numeric(source.get("operator_raw_model_order_units", pd.Series([0] * len(source.index))), errors="coerce").fillna(0.0)
            final_units = pd.to_numeric(source.get("operator_final_store_order_units", pd.Series([0] * len(source.index))), errors="coerce").fillna(0.0)
            mapped[field_name] = (raw_units != final_units).astype(int)
        elif field_name == "stage_12_change_flag":
            stage12_columns = [column for column in STAGE12_GUARDRAIL_COLUMNS if column in source.columns]
            if not stage12_columns:
                mapped[field_name] = 0
            else:
                numeric = source[stage12_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
                mapped[field_name] = (numeric.sum(axis=1) > 0).astype(int)
        elif field_name == "stockout_or_missed_demand_flag":
            source_columns = [column for column in plan.source_columns if column in source.columns]
            numeric = source[source_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0) if source_columns else pd.DataFrame(index=source.index)
            mapped[field_name] = (numeric.max(axis=1) > 0).astype(int) if not numeric.empty else 0
        elif field_name == "gross_profit_represented":
            mapped[field_name] = source.get("actual_estimated_actual_gross_profit", "")
        elif field_name == "capital_at_risk":
            if "operator_capital_at_risk_adjusted_dollars" in source.columns:
                mapped[field_name] = source["operator_capital_at_risk_adjusted_dollars"]
            elif "actual_current_capital_at_risk" in source.columns:
                mapped[field_name] = source["actual_current_capital_at_risk"]
            elif "actual_shadow_capital_at_risk" in source.columns:
                mapped[field_name] = source["actual_shadow_capital_at_risk"]
            elif "actual_capital_left_in_unsold_store_allocation" in source.columns:
                mapped[field_name] = source["actual_capital_left_in_unsold_store_allocation"]
            else:
                mapped[field_name] = ""
        else:
            mapped[field_name] = ""
    return mapped


def _missing_columns_frame(plans: dict[str, FieldMappingPlan]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for field_name in CANONICAL_FIELD_ORDER:
        plan = plans[field_name]
        if plan.mapping_status != MAPPING_MISSING:
            continue
        required_flag = int(
            field_name in REQUIRED_IDENTITY_FIELDS
            or field_name in REQUIRED_ACTUAL_FIELDS
            or field_name in REQUIRED_ECONOMICS_FIELDS
        )
        rows.append(
            {
                "canonical_field": field_name,
                "required_flag": required_flag,
                "missing_reason": plan.notes,
                "blocking_flag": int(required_flag > 0),
                "notes": "Missing required fields block final governed review rebuild." if required_flag else "Optional field not resolved.",
            }
        )
    return pd.DataFrame(rows, columns=MISSING_COLUMNS_COLUMNS)


def _derived_fields_frame(plans: dict[str, FieldMappingPlan]) -> pd.DataFrame:
    rows = [
        {
            "canonical_field": plan.canonical_field,
            "derivation_formula": plan.derivation_formula,
            "source_columns": "; ".join(plan.source_columns),
            "review_required_flag": plan.review_required_flag,
            "notes": plan.notes,
        }
        for plan in plans.values()
        if plan.mapping_status == MAPPING_DERIVED
    ]
    return pd.DataFrame(rows, columns=DERIVED_FIELDS_COLUMNS)


def _ambiguities_frame(plans: dict[str, FieldMappingPlan]) -> pd.DataFrame:
    rows = [
        {
            "canonical_field": plan.canonical_field,
            "candidate_columns": "; ".join(plan.source_columns),
            "preferred_column": plan.source_column,
            "ambiguity_reason": plan.ambiguity_reason,
            "blocking_flag": plan.blocking_flag,
        }
        for plan in plans.values()
        if plan.mapping_status == MAPPING_AMBIGUOUS
    ]
    return pd.DataFrame(rows, columns=AMBIGUITIES_COLUMNS)


def _schema_mapping_status(
    *,
    preview_validation_frame: pd.DataFrame,
    missing_columns_frame: pd.DataFrame,
    derived_fields_frame: pd.DataFrame,
    ambiguities_frame: pd.DataFrame,
) -> str:
    validation_lookup = dict(
        zip(
            preview_validation_frame.get("validation_name", pd.Series(dtype="object")).astype(str),
            preview_validation_frame.get("validation_status", pd.Series(dtype="object")).astype(str),
        )
    )
    guardrail_failures = any(
        validation_lookup.get(name, "FAIL") != "PASS"
        for name in (
            "PRODUCTION_GUARDRAIL_STATUS",
            "STAGE12_GUARDRAIL_STATUS",
            "MISSING_ACTUALS_NOT_ZERO_FILLED",
            "ROW_COUNT_CONSERVATION",
        )
    )
    if guardrail_failures:
        return SCHEMA_MAPPING_BLOCKED_GUARDRAIL_FAILURE
    required_missing = not missing_columns_frame.loc[missing_columns_frame["blocking_flag"].eq(1)].empty
    if required_missing:
        return SCHEMA_MAPPING_BLOCKED_MISSING_REQUIRED_COLUMNS
    blocking_ambiguities = not ambiguities_frame.loc[ambiguities_frame["blocking_flag"].eq(1)].empty
    if blocking_ambiguities:
        return SCHEMA_MAPPING_BLOCKED_AMBIGUOUS_COLUMNS
    review_ambiguities = not ambiguities_frame.empty
    if review_ambiguities:
        return SCHEMA_MAPPING_NEEDS_REVIEW
    needs_derived_fields = not derived_fields_frame.empty
    if needs_derived_fields:
        return SCHEMA_MAPPING_READY_WITH_DERIVED_FIELDS
    return SCHEMA_MAPPING_READY_FOR_REVIEW_PACKET_DRAFT


def _validation_frame(
    *,
    preview_row_count: int,
    mapping_row_count: int,
    quarantine_row_count: int,
    preview_validation_frame: pd.DataFrame,
    plans: dict[str, FieldMappingPlan],
    schema_mapping_status: str,
) -> pd.DataFrame:
    preview_lookup = dict(
        zip(
            preview_validation_frame.get("validation_name", pd.Series(dtype="object")).astype(str),
            preview_validation_frame.get("validation_status", pd.Series(dtype="object")).astype(str),
        )
    )
    required_identity_mapped_flag = int(
        all(plans[field_name].mapping_status != MAPPING_MISSING for field_name in REQUIRED_IDENTITY_FIELDS)
    )
    required_actuals_mapped_flag = int(
        all(plans[field_name].mapping_status != MAPPING_MISSING for field_name in REQUIRED_ACTUAL_FIELDS)
    )
    required_economics_mapped_or_derived_flag = int(
        all(plans[field_name].mapping_status != MAPPING_MISSING for field_name in REQUIRED_ECONOMICS_FIELDS)
    )
    review_packet_draft_ready_flag = int(
        schema_mapping_status in {
            SCHEMA_MAPPING_READY_FOR_REVIEW_PACKET_DRAFT,
            SCHEMA_MAPPING_READY_WITH_DERIVED_FIELDS,
        }
    )
    return pd.DataFrame(
        [
            _validation_row(
                "PREVIEW_ROW_COUNT_PRESERVED",
                "PASS" if preview_row_count == mapping_row_count else "FAIL",
                int(preview_row_count == mapping_row_count),
                f"preview_rows={preview_row_count}, mapping_rows={mapping_row_count}",
            ),
            _validation_row(
                "QUARANTINE_COUNT_PRESERVED",
                "PASS",
                1,
                f"quarantine_rows={quarantine_row_count}",
            ),
            _validation_row(
                "MISSING_ACTUALS_NOT_ZERO_FILLED",
                preview_lookup.get("MISSING_ACTUALS_NOT_ZERO_FILLED", "FAIL"),
                int(preview_lookup.get("MISSING_ACTUALS_NOT_ZERO_FILLED", "FAIL") == "PASS"),
                "Schema mapping inherits preview-join missing-actual preservation.",
            ),
            _validation_row(
                "PRODUCTION_GUARDRAIL_STATUS",
                preview_lookup.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL"),
                int(preview_lookup.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL") == "PASS"),
                "Schema mapping does not change production ordering fields.",
            ),
            _validation_row(
                "STAGE12_GUARDRAIL_STATUS",
                preview_lookup.get("STAGE12_GUARDRAIL_STATUS", "FAIL"),
                int(preview_lookup.get("STAGE12_GUARDRAIL_STATUS", "FAIL") == "PASS"),
                "Schema mapping does not change Stage 12 fields.",
            ),
            _validation_row(
                "REQUIRED_IDENTITY_FIELDS_MAPPED",
                "PASS" if required_identity_mapped_flag else "FAIL",
                required_identity_mapped_flag,
                "Identity contract fields are mapped or explicitly blocked.",
            ),
            _validation_row(
                "REQUIRED_ACTUAL_OUTCOME_FIELDS_MAPPED",
                "PASS" if required_actuals_mapped_flag else "FAIL",
                required_actuals_mapped_flag,
                "Actual outcome fields are mapped or explicitly blocked.",
            ),
            _validation_row(
                "REQUIRED_ECONOMICS_FIELDS_MAPPED_OR_DERIVED",
                "PASS" if required_economics_mapped_or_derived_flag else "FAIL",
                required_economics_mapped_or_derived_flag,
                "Economics fields are mapped or explicitly derived.",
            ),
            _validation_row(
                "FULL_REBUILD_REMAINS_BLOCKED",
                "PASS",
                1,
                "This planner does not write a final governed review packet and does not unblock the full governed rebuild on its own.",
            ),
            _validation_row(
                "REVIEW_PACKET_DRAFT_CAN_BE_AUTHORED_NEXT",
                "PASS" if review_packet_draft_ready_flag else "FAIL",
                review_packet_draft_ready_flag,
                "Draft authoring can proceed only when mapping status is ready or ready-with-derived-fields.",
            ),
        ],
        columns=VALIDATION_COLUMNS,
    )


def _summary_frame(
    *,
    selection: PromotionSelection,
    schema_mapping_status: str,
    preview_row_count: int,
    quarantine_row_count: int,
    mapped_required_fields: list[str],
    missing_required_fields: list[str],
    derived_fields_required: list[str],
    ambiguous_fields: list[str],
    production_guardrail_status: str,
    stage12_guardrail_status: str,
    review_packet_draft_ready_flag: int,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION", selection.promotion_key, "Promotion selected for diagnostics-only canonical schema mapping planning."),
            _summary_row("SCHEMA_MAPPING_STATUS", schema_mapping_status, "Overall schema-mapping planning status."),
            _summary_row("PREVIEW_ROW_COUNT", preview_row_count, "Joined preview rows available for mapping."),
            _summary_row("QUARANTINE_ROW_COUNT", quarantine_row_count, "Quarantined rows preserved outside the mapping rows output."),
            _summary_row("MAPPED_REQUIRED_FIELDS", "; ".join(mapped_required_fields), "Required canonical fields resolved directly, by prefix, or by derivation."),
            _summary_row("MISSING_REQUIRED_FIELDS", "; ".join(missing_required_fields), "Required canonical fields still unresolved."),
            _summary_row("DERIVED_FIELDS_REQUIRED", "; ".join(derived_fields_required), "Canonical fields that require explicit derivation formulas."),
            _summary_row("AMBIGUOUS_FIELDS", "; ".join(ambiguous_fields), "Canonical fields with multiple plausible source candidates that still need review."),
            _summary_row("PRODUCTION_GUARDRAIL_STATUS", production_guardrail_status, "Production-order guardrail inherited from the preview join."),
            _summary_row("STAGE12_GUARDRAIL_STATUS", stage12_guardrail_status, "Stage 12 guardrail inherited from the preview join."),
            _summary_row("REVIEW_PACKET_DRAFT_NEXT_FLAG", review_packet_draft_ready_flag, "Compatibility metric for whether a draft review packet can be authored next."),
            _summary_row("REVIEW_PACKET_DRAFT_CAN_BE_AUTHORED_NEXT", review_packet_draft_ready_flag, "Whether a draft governed review packet can be authored next without running the full rebuild."),
        ],
        columns=SUMMARY_COLUMNS,
    )


def _memo_markdown(
    *,
    selection: PromotionSelection,
    schema_mapping_status: str,
    preview_row_count: int,
    quarantine_row_count: int,
    mapped_required_fields: list[str],
    missing_required_fields: list[str],
    derived_fields_required: list[str],
    ambiguous_fields: list[str],
    production_guardrail_status: str,
    stage12_guardrail_status: str,
    review_packet_draft_ready_flag: int,
) -> str:
    recommendation = (
        "Author a diagnostics-only review-packet draft next from the mapped preview rows, but keep quarantined rows separate and do not run the full governed rebuild yet."
        if review_packet_draft_ready_flag > 0
        else "Do not author the review-packet draft yet; resolve missing or ambiguous canonical mappings first."
    )
    return "\n".join(
        [
            "# Materialized Source Schema Mapping Plan",
            "",
            "This is a diagnostics-only canonical schema mapping plan.",
            "This does not write the final governed review packet.",
            "This does not start training.",
            "This does not change production ordering logic or Stage 12.",
            "This does not promote auto-ordering or shadow rules.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "This does not silently drop quarantine rows.",
            "",
            f"Selected promotion: {selection.promotion_key}",
            f"Schema mapping status: {schema_mapping_status}",
            f"Preview row count: {preview_row_count}",
            f"Quarantine row count: {quarantine_row_count}",
            f"Mapped required fields: {'; '.join(mapped_required_fields) or '(none)'}",
            f"Missing required fields: {'; '.join(missing_required_fields) or '(none)'}",
            f"Derived fields required: {'; '.join(derived_fields_required) or '(none)'}",
            f"Ambiguous fields: {'; '.join(ambiguous_fields) or '(none)'}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Review packet draft can be authored next: {review_packet_draft_ready_flag}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()


def build_promotions_materialized_source_schema_mapping_plan(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceSchemaMappingPlanResult:
    packet_root_path = Path(packet_root)
    preview_root = _resolve_preview_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
    )
    spec_root = packet_root_path / SPEC_PACK_FOLDER_NAME

    preview_rows_frame = _read_csv(preview_root / PREVIEW_ROWS_FILE_NAME)
    quarantine_frame = _read_csv(preview_root / PREVIEW_QUARANTINE_FILE_NAME, allow_empty=True)
    preview_validation_frame = _read_csv(preview_root / PREVIEW_VALIDATION_FILE_NAME)
    _ = _read_csv(preview_root / PREVIEW_LINEAGE_FILE_NAME, allow_empty=True)
    preview_summary_frame = _read_csv(preview_root / PREVIEW_SUMMARY_FILE_NAME, allow_empty=True)
    spec_summary_frame = _read_csv(spec_root / SPEC_SUMMARY_FILE_NAME, allow_empty=True)

    resolved_promotion_key = _resolve_selected_promotion_key(
        promotion_key=promotion_key,
        preview_summary_frame=preview_summary_frame,
        spec_summary_frame=spec_summary_frame,
    )
    selection = _selection_from_promotion_key(resolved_promotion_key)
    selected_preview_rows_frame = _filter_frame_for_selection(
        preview_rows_frame,
        selection=selection,
    )
    selected_quarantine_frame = _filter_frame_for_selection(
        quarantine_frame,
        selection=selection,
    )
    if selected_preview_rows_frame.empty:
        raise PromotionsMaterializedSourceSchemaMappingPlanError(
            f"No preview-join rows found for promotion: {resolved_promotion_key}"
        )

    columns = tuple(selected_preview_rows_frame.columns.astype(str).tolist())
    plans = {field_name: _resolve_plan_for_field(field_name, columns) for field_name in CANONICAL_FIELD_ORDER}
    mapping_rows_frame = _apply_plan_to_rows(selected_preview_rows_frame, selection=selection, plans=plans)
    missing_columns_frame = _missing_columns_frame(plans)
    derived_fields_frame = _derived_fields_frame(plans)
    ambiguities_frame = _ambiguities_frame(plans)
    schema_mapping_status = _schema_mapping_status(
        preview_validation_frame=preview_validation_frame,
        missing_columns_frame=missing_columns_frame,
        derived_fields_frame=derived_fields_frame,
        ambiguities_frame=ambiguities_frame,
    )
    mapping_rows_frame["schema_mapping_status"] = schema_mapping_status

    preview_lookup = dict(
        zip(
            preview_validation_frame["validation_name"].astype(str),
            preview_validation_frame["validation_status"].astype(str),
        )
    )
    validation_frame = _validation_frame(
        preview_row_count=int(len(selected_preview_rows_frame.index)),
        mapping_row_count=int(len(mapping_rows_frame.index)),
        quarantine_row_count=int(len(selected_quarantine_frame.index)),
        preview_validation_frame=preview_validation_frame,
        plans=plans,
        schema_mapping_status=schema_mapping_status,
    )
    mapped_required_fields = [
        field_name
        for field_name in (*REQUIRED_IDENTITY_FIELDS, *REQUIRED_ACTUAL_FIELDS, *REQUIRED_ECONOMICS_FIELDS)
        if plans[field_name].mapping_status != MAPPING_MISSING
    ]
    missing_required_fields = [
        field_name
        for field_name in (*REQUIRED_IDENTITY_FIELDS, *REQUIRED_ACTUAL_FIELDS, *REQUIRED_ECONOMICS_FIELDS)
        if plans[field_name].mapping_status == MAPPING_MISSING
    ]
    derived_fields_required = [
        field_name for field_name, plan in plans.items() if plan.mapping_status == MAPPING_DERIVED
    ]
    ambiguous_fields = [
        field_name for field_name, plan in plans.items() if plan.mapping_status == MAPPING_AMBIGUOUS
    ]
    review_packet_draft_ready_flag = int(
        schema_mapping_status in {
            SCHEMA_MAPPING_READY_FOR_REVIEW_PACKET_DRAFT,
            SCHEMA_MAPPING_READY_WITH_DERIVED_FIELDS,
        }
    )
    summary_frame = _summary_frame(
        selection=selection,
        schema_mapping_status=schema_mapping_status,
        preview_row_count=int(len(selected_preview_rows_frame.index)),
        quarantine_row_count=int(len(selected_quarantine_frame.index)),
        mapped_required_fields=mapped_required_fields,
        missing_required_fields=missing_required_fields,
        derived_fields_required=derived_fields_required,
        ambiguous_fields=ambiguous_fields,
        production_guardrail_status=preview_lookup.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL"),
        stage12_guardrail_status=preview_lookup.get("STAGE12_GUARDRAIL_STATUS", "FAIL"),
        review_packet_draft_ready_flag=review_packet_draft_ready_flag,
    )
    memo_markdown = _memo_markdown(
        selection=selection,
        schema_mapping_status=schema_mapping_status,
        preview_row_count=int(len(selected_preview_rows_frame.index)),
        quarantine_row_count=int(len(selected_quarantine_frame.index)),
        mapped_required_fields=mapped_required_fields,
        missing_required_fields=missing_required_fields,
        derived_fields_required=derived_fields_required,
        ambiguous_fields=ambiguous_fields,
        production_guardrail_status=preview_lookup.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL"),
        stage12_guardrail_status=preview_lookup.get("STAGE12_GUARDRAIL_STATUS", "FAIL"),
        review_packet_draft_ready_flag=review_packet_draft_ready_flag,
    )
    return PromotionsMaterializedSourceSchemaMappingPlanResult(
        selected_promotion=selection,
        schema_mapping_status=schema_mapping_status,
        mapping_rows_frame=mapping_rows_frame,
        missing_columns_frame=missing_columns_frame,
        derived_fields_frame=derived_fields_frame,
        ambiguities_frame=ambiguities_frame,
        validation_frame=validation_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_schema_mapping_plan(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceSchemaMappingPlanArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_schema_mapping_plan(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)
    mapping_rows_csv_path = output_root_path / "materialized_source_schema_mapping_rows.csv"
    missing_columns_csv_path = output_root_path / "materialized_source_schema_mapping_missing_columns.csv"
    derived_fields_csv_path = output_root_path / "materialized_source_schema_mapping_derived_fields.csv"
    ambiguities_csv_path = output_root_path / "materialized_source_schema_mapping_ambiguities.csv"
    validation_csv_path = output_root_path / "materialized_source_schema_mapping_validation.csv"
    summary_csv_path = output_root_path / "materialized_source_schema_mapping_summary.csv"
    memo_md_path = output_root_path / "materialized_source_schema_mapping_memo.md"

    result.mapping_rows_frame.to_csv(mapping_rows_csv_path, index=False)
    result.missing_columns_frame.to_csv(missing_columns_csv_path, index=False)
    result.derived_fields_frame.to_csv(derived_fields_csv_path, index=False)
    result.ambiguities_frame.to_csv(ambiguities_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceSchemaMappingPlanArtifacts(
        output_root=str(output_root_path),
        mapping_rows_csv_path=str(mapping_rows_csv_path),
        missing_columns_csv_path=str(missing_columns_csv_path),
        derived_fields_csv_path=str(derived_fields_csv_path),
        ambiguities_csv_path=str(ambiguities_csv_path),
        validation_csv_path=str(validation_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only canonical schema mapping plan for the preview-joined materialized promotion."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_schema_mapping_plan(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary_frame)
    print("selected_promotion", _normalize_text(metrics.get("SELECTED_PROMOTION", "")))
    print("schema_mapping_status", _normalize_text(metrics.get("SCHEMA_MAPPING_STATUS", "")))
    print("preview_row_count", _normalize_text(metrics.get("PREVIEW_ROW_COUNT", 0)))
    print("quarantine_row_count", _normalize_text(metrics.get("QUARANTINE_ROW_COUNT", 0)))
    print("mapped_required_fields", _normalize_text(metrics.get("MAPPED_REQUIRED_FIELDS", "")))
    print("missing_required_fields", _normalize_text(metrics.get("MISSING_REQUIRED_FIELDS", "")))
    print("derived_fields_required", _normalize_text(metrics.get("DERIVED_FIELDS_REQUIRED", "")))
    print("ambiguous_fields", _normalize_text(metrics.get("AMBIGUOUS_FIELDS", "")))
    print("production_guardrail_status", _normalize_text(metrics.get("PRODUCTION_GUARDRAIL_STATUS", "")))
    print("stage12_guardrail_status", _normalize_text(metrics.get("STAGE12_GUARDRAIL_STATUS", "")))
    print(
        "review_packet_draft_can_be_authored_next",
        _normalize_text(metrics.get("REVIEW_PACKET_DRAFT_CAN_BE_AUTHORED_NEXT", 0)),
    )
    print("materialized_source_schema_mapping_rows", artifacts.mapping_rows_csv_path)
    print("materialized_source_schema_mapping_missing_columns", artifacts.missing_columns_csv_path)
    print("materialized_source_schema_mapping_derived_fields", artifacts.derived_fields_csv_path)
    print("materialized_source_schema_mapping_ambiguities", artifacts.ambiguities_csv_path)
    print("materialized_source_schema_mapping_validation", artifacts.validation_csv_path)
    print("materialized_source_schema_mapping_summary", artifacts.summary_csv_path)
    print("materialized_source_schema_mapping_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
