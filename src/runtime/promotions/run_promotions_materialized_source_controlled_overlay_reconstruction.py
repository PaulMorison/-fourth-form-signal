from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_controlled_overlay_reconstruction"
INSPECTION_FOLDER_NAME = "materialized_source_controlled_rebuild_inspection"
CONTROLLED_REBUILD_FOLDER_NAME = "materialized_source_controlled_governed_rebuild"

INSPECTION_SUMMARY_FILE_NAME = "controlled_rebuild_inspection_summary.csv"
INSPECTION_QUALITY_FILE_NAME = "controlled_rebuild_inspection_quality_checks.csv"
REBUILD_REVIEW_ROWS_FILE_NAME = "model_vs_actual_review_rows.csv"
REBUILD_SUMMARY_FILE_NAME = "model_vs_actual_summary.csv"
REBUILD_TOP_ERRORS_FILE_NAME = "model_vs_actual_top_errors.csv"
REBUILD_QUARANTINE_FILE_NAME = "controlled_governed_rebuild_quarantine_rows.csv"

REQUIRED_INSPECTION_FILE_NAMES: tuple[str, ...] = (
    INSPECTION_SUMMARY_FILE_NAME,
    INSPECTION_QUALITY_FILE_NAME,
)

REQUIRED_REBUILD_FILE_NAMES: tuple[str, ...] = (
    REBUILD_REVIEW_ROWS_FILE_NAME,
    REBUILD_SUMMARY_FILE_NAME,
    REBUILD_TOP_ERRORS_FILE_NAME,
    REBUILD_QUARANTINE_FILE_NAME,
)

CONTROLLED_OVERLAY_RECONSTRUCTION_READY = "CONTROLLED_OVERLAY_RECONSTRUCTION_READY"
CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE = (
    "CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE"
)
CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_GATE_FAILURE = (
    "CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_GATE_FAILURE"
)
CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_GUARDRAIL_FAILURE = (
    "CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_GUARDRAIL_FAILURE"
)
CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_EMPTY_OVERLAY = (
    "CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_EMPTY_OVERLAY"
)
CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_ORDER_RECOMMENDATION_RISK = (
    "CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_ORDER_RECOMMENDATION_RISK"
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "check_name",
    "check_status",
    "check_flag",
    "details",
)

BLOCKERS_COLUMNS: tuple[str, ...] = (
    "blocker_code",
    "blocker_type",
    "blocker_detail",
    "blocking_flag",
    "remediation",
)

ROWS_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_row_id",
    "sku_number",
    "sku_description",
    "store_action_label",
    "store_action_reason",
    "demand_evidence_label",
    "expected_promo_demand",
    "actual_units",
    "forecast_error_units",
    "absolute_error_units",
    "actual_sell_through_pct",
    "actual_gross_profit",
    "capital_left",
    "capital_left_value",
    "gross_profit_represented",
    "capital_at_risk",
    "stockout_or_missed_demand_flag",
    "recommended_order_units",
    "final_store_order_units",
    "overlay_category",
    "proposed_review_action",
    "why_review_required",
    "review_trigger_detail",
    "review_only_flag",
    "generated_order_recommendation_flag",
    "production_order_change_flag",
    "stage_12_change_flag",
    "top_error_rank",
)

BY_CATEGORY_COLUMNS: tuple[str, ...] = (
    "overlay_category",
    "row_count",
    "reference_row_count",
    "absolute_difference_vs_reference",
    "reconciliation_status",
    "actual_units_total",
    "actual_gross_profit_total",
    "capital_left_value_total",
    "sample_skus",
    "notes",
)

TOP_SKUS_COLUMNS: tuple[str, ...] = (
    "overlay_rank",
    "top_error_rank",
    "overlay_category",
    "sku_number",
    "sku_description",
    "store_action_label",
    "demand_evidence_label",
    "actual_units",
    "absolute_error_units",
    "actual_gross_profit",
    "capital_left_value",
    "review_trigger_detail",
)

EXPECTED_REVIEW_ROW_COUNT = 3597
EXPECTED_QUARANTINE_ROW_COUNT = 1

REFERENCE_CATEGORY_COUNTS: dict[str, int] = {
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": 31,
    "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": 27,
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW": 18,
    "ONLINE_FLOOR_PROTECTION_REVIEW": 16,
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": 5,
    "ZERO_ORDER_TEXT_CLEANUP_REVIEW": 2,
}

OVERLAY_CATEGORY_PRIORITY: dict[str, int] = {
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": 1,
    "ONLINE_FLOOR_PROTECTION_REVIEW": 2,
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW": 3,
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": 4,
    "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": 5,
    "ZERO_ORDER_TEXT_CLEANUP_REVIEW": 6,
}

PROPOSED_REVIEW_ACTION_BY_CATEGORY: dict[str, str] = {
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": "INSPECT_TRUE_MISSED_DEMAND",
    "ONLINE_FLOOR_PROTECTION_REVIEW": "INSPECT_ONLINE_FLOOR_RISK",
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": "INSPECT_STRONG_CONVERTER_CAPITAL_DRAG_HEADLINE",
    "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": "KEEP_SHADOW_ONLY_FOR_ACTION_LAYER",
    "ZERO_ORDER_TEXT_CLEANUP_REVIEW": "FIX_VISIBLE_REASON_TEXT",
}

WHY_REVIEW_REQUIRED_BY_CATEGORY: dict[str, str] = {
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": "Material demand landed while the row stayed low-SOH suppressed, so a human should inspect missed demand before any policy change.",
    "ONLINE_FLOOR_PROTECTION_REVIEW": "The row needs a human floor-risk check because low-SOH or floor-protection context stayed review-only and must not auto-order.",
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW": "Material demand landed without strong prior promo evidence, so the row needs governed human inspection rather than a demand-proxy change.",
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": "Strong sell-through contradicted the visible capital-drag headline, so the row should be inspected as a review-only headline correction.",
    "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": "The action layer was too conservative or missed a governed review trigger, so any response must stay shadow-only and human-reviewed.",
    "ZERO_ORDER_TEXT_CLEANUP_REVIEW": "Visible wording still implies buy or order on a zero-order row, so the row needs contract cleanup review before operator use.",
}

PASS_GATE_STATUSES: set[str] = {
    "CONTROLLED_REBUILD_INSPECTION_PASS",
    "CONTROLLED_REBUILD_INSPECTION_PASS_WITH_QUARANTINE",
}

REVIEW_ONLY_CATEGORIES: tuple[str, ...] = tuple(OVERLAY_CATEGORY_PRIORITY.keys())

PLANNED_PASS_ARTIFACTS: tuple[str, ...] = (
    "controlled_overlay_reconstruction_rows.csv",
    "controlled_overlay_reconstruction_summary.csv",
    "controlled_overlay_reconstruction_by_category.csv",
    "controlled_overlay_reconstruction_top_skus.csv",
    "controlled_overlay_reconstruction_quarantine_rows.csv",
    "controlled_overlay_reconstruction_validation.csv",
    "controlled_overlay_reconstruction_memo.md",
)

PLANNED_FAIL_ARTIFACTS: tuple[str, ...] = (
    "controlled_overlay_reconstruction_blockers.csv",
    "controlled_overlay_reconstruction_validation.csv",
    "controlled_overlay_reconstruction_memo.md",
)


class PromotionsMaterializedSourceControlledOverlayReconstructionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceControlledOverlayReconstructionResult:
    selected_promotion: PromotionSelection
    gate_status: str
    overlay_reconstruction_status: str
    dry_run: bool
    overlay_rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_category_frame: pd.DataFrame
    top_skus_frame: pd.DataFrame
    quarantine_rows_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    blockers_frame: pd.DataFrame
    memo_markdown: str
    reference_reconciliation_status: str
    production_guardrail_status: str
    stage12_guardrail_status: str
    action_layer_review_reconstruction_can_be_authored_next: int
    recommendation: str
    artifacts_planned: tuple[str, ...]


@dataclass(frozen=True)
class PromotionsMaterializedSourceControlledOverlayReconstructionArtifacts:
    output_root: str
    rows_csv_path: str | None
    summary_csv_path: str | None
    by_category_csv_path: str | None
    top_skus_csv_path: str | None
    quarantine_rows_csv_path: str | None
    validation_csv_path: str
    blockers_csv_path: str | None
    memo_md_path: str
    selected_promotion: str
    gate_status: str
    overlay_reconstruction_status: str
    dry_run: bool
    overlay_row_count: int
    quarantine_row_count: int
    category_count_summary: str
    reference_reconciliation_status: str
    production_guardrail_status: str
    stage12_guardrail_status: str
    action_layer_review_reconstruction_can_be_authored_next: int
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
        raise PromotionsMaterializedSourceControlledOverlayReconstructionError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceControlledOverlayReconstructionError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceControlledOverlayReconstructionError(f"CSV is empty: {csv_path}")
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
    raise PromotionsMaterializedSourceControlledOverlayReconstructionError(
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


def _validation_row(check_name: str, check_status: str, check_flag: int, details: str) -> dict[str, object]:
    return {
        "check_name": check_name,
        "check_status": check_status,
        "check_flag": int(check_flag),
        "details": details,
    }


def _blocker_row(code: str, blocker_type: str, detail: str, remediation: str) -> dict[str, object]:
    return {
        "blocker_code": code,
        "blocker_type": blocker_type,
        "blocker_detail": detail,
        "blocking_flag": 1,
        "remediation": remediation,
    }


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _filter_for_promotion(frame: pd.DataFrame, promotion_key: str) -> pd.DataFrame:
    if frame.empty or "promotion_key" not in frame.columns or not promotion_key:
        return frame.copy()
    return frame.loc[frame["promotion_key"].astype(str) == promotion_key].reset_index(drop=True).copy()


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.map(lambda value: _normalize_text(value) or None), errors="coerce")


def _selection_from_inputs(
    *,
    requested_promotion_key: str | None,
    inspection_summary_metrics: dict[str, object],
    review_rows_frame: pd.DataFrame,
    quarantine_rows_frame: pd.DataFrame,
) -> PromotionSelection:
    resolved_key = requested_promotion_key or _normalize_text(inspection_summary_metrics.get("SELECTED_PROMOTION", ""))
    if not resolved_key and "promotion_key" in review_rows_frame.columns:
        keys = [value for value in review_rows_frame["promotion_key"].astype(str).drop_duplicates().tolist() if value]
        resolved_key = keys[0] if keys else "UNKNOWN|||UNKNOWN"
    if not resolved_key and "promotion_key" in quarantine_rows_frame.columns:
        keys = [value for value in quarantine_rows_frame["promotion_key"].astype(str).drop_duplicates().tolist() if value]
        resolved_key = keys[0] if keys else "UNKNOWN|||UNKNOWN"
    parts = resolved_key.split("|", 3)
    if len(parts) != 4:
        return PromotionSelection(
            promotion_key=resolved_key,
            promotion_name="",
            promotion_start_date="",
            promotion_end_date="",
        )
    return PromotionSelection(
        promotion_key=resolved_key,
        promotion_name=parts[3],
        promotion_start_date=parts[1],
        promotion_end_date=parts[2],
    )


def _category_order() -> list[str]:
    return sorted(OVERLAY_CATEGORY_PRIORITY.keys(), key=lambda value: OVERLAY_CATEGORY_PRIORITY[value])


def _contains_order_language(series: pd.Series) -> pd.Series:
    normalized = series.fillna("").astype(str).str.casefold()
    has_order_language = normalized.str.contains(r"\b(?:order|buy)\b", regex=True)
    blocked_phrases = normalized.str.contains(
        r"do not buy|do not auto-order|do not order|no order|do_not_buy|do_not_auto-order",
        regex=True,
    )
    return has_order_language & ~blocked_phrases


def _build_candidate_frame(
    review_rows_frame: pd.DataFrame,
    *,
    mask: pd.Series,
    category: str,
    trigger_detail: str,
) -> pd.DataFrame:
    rows = review_rows_frame.loc[mask].copy()
    if rows.empty:
        return pd.DataFrame(columns=list(ROWS_COLUMNS) + ["_overlay_priority"])
    rows["overlay_category"] = category
    rows["proposed_review_action"] = PROPOSED_REVIEW_ACTION_BY_CATEGORY[category]
    rows["why_review_required"] = WHY_REVIEW_REQUIRED_BY_CATEGORY[category]
    rows["review_trigger_detail"] = trigger_detail
    rows["review_only_flag"] = 1
    rows["generated_order_recommendation_flag"] = 0
    rows["top_error_rank"] = _to_numeric(rows.get("top_error_rank", pd.Series(dtype="object")))
    rows["_overlay_priority"] = OVERLAY_CATEGORY_PRIORITY[category]
    for column_name in ROWS_COLUMNS:
        if column_name not in rows.columns:
            rows[column_name] = ""
    return rows.loc[:, list(ROWS_COLUMNS) + ["_overlay_priority"]].copy()


def _build_overlay_rows(
    review_rows_frame: pd.DataFrame,
    top_errors_frame: pd.DataFrame,
    quarantine_rows_frame: pd.DataFrame,
) -> pd.DataFrame:
    if review_rows_frame.empty:
        return pd.DataFrame(columns=ROWS_COLUMNS)

    rows = review_rows_frame.copy()
    quarantine_numbers = set(
        quarantine_rows_frame.get("source_row_number", pd.Series(dtype="object")).map(_normalize_text).tolist()
    )
    if quarantine_numbers:
        rows = rows.loc[~rows.get("source_row_id", pd.Series(dtype="object")).map(_normalize_text).isin(quarantine_numbers)].copy()
    if rows.empty:
        return pd.DataFrame(columns=ROWS_COLUMNS)

    top_error_lookup = top_errors_frame.loc[:, ["source_row_id", "error_rank"]].copy() if not top_errors_frame.empty else pd.DataFrame(columns=["source_row_id", "error_rank"])
    if not top_error_lookup.empty:
        top_error_lookup["source_row_id"] = top_error_lookup["source_row_id"].map(_normalize_text)
        top_error_lookup = top_error_lookup.drop_duplicates(subset=["source_row_id"], keep="first")
        rows["source_row_id"] = rows["source_row_id"].map(_normalize_text)
        rows = rows.merge(top_error_lookup.rename(columns={"error_rank": "top_error_rank"}), on="source_row_id", how="left")
    else:
        rows["top_error_rank"] = pd.NA

    expected_units = _to_numeric(rows["expected_promo_demand"]).fillna(0.0)
    actual_units = _to_numeric(rows["actual_units"]).fillna(0.0)
    absolute_error_units = _to_numeric(rows["absolute_error_units"]).fillna(0.0)
    sell_through = _to_numeric(rows["actual_sell_through_pct"]).fillna(0.0)
    capital_left = _to_numeric(rows["capital_left"]).fillna(0.0)
    capital_left_value = _to_numeric(rows["capital_left_value"]).fillna(0.0)
    stockout_flag = _to_numeric(rows["stockout_or_missed_demand_flag"]).fillna(0.0)
    recommended_units = _to_numeric(rows["recommended_order_units"]).fillna(0.0)
    final_units = _to_numeric(rows["final_store_order_units"]).fillna(0.0)
    reason_text = rows["store_action_reason"].fillna("").astype(str)
    action_label = rows["store_action_label"].fillna("").astype(str)
    demand_label = rows["demand_evidence_label"].fillna("").astype(str)

    conservative_action_mask = action_label.isin(
        {
            "LOW_SOH_NO_AUTO_BUY",
            "REDUCE_HOLDING",
            "NO_DEMAND",
            "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
            "PROTECT_AVAILABILITY",
        }
    )
    material_demand_mask = actual_units.ge(expected_units + 2.0) | absolute_error_units.ge(3.0)

    true_low_soh_mask = (
        action_label.eq("LOW_SOH_NO_AUTO_BUY")
        & stockout_flag.ge(1.0)
        & actual_units.gt(expected_units)
    )
    online_floor_mask = (
        action_label.isin({"LOW_SOH_NO_AUTO_BUY", "PROTECT_AVAILABILITY"})
        & (~true_low_soh_mask)
        & ((sell_through.ge(1.0)) | stockout_flag.ge(1.0) | capital_left.le(1.0))
        & actual_units.ge(1.0)
    )
    no_prior_mask = (
        demand_label.isin({"NO_DEMAND", "NEVER_SOLD_IN_PROMO", "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND"})
        & material_demand_mask
        & actual_units.ge(2.0)
    )
    strong_conversion_mask = (
        action_label.eq("REDUCE_HOLDING")
        & ((sell_through.ge(0.75)) | actual_units.ge(expected_units + 3.0))
        & ((capital_left.le(3.0)) | capital_left_value.le(10.0))
        & actual_units.ge(1.0)
    )
    action_layer_mask = (
        conservative_action_mask
        & ((absolute_error_units.ge(5.0)) | stockout_flag.ge(1.0))
        & actual_units.gt(expected_units)
    )
    zero_order_mask = (
        final_units.eq(0.0)
        & recommended_units.eq(0.0)
        & _contains_order_language(reason_text)
    )

    candidate_frames = [
        _build_candidate_frame(
            rows,
            mask=true_low_soh_mask,
            category="TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
            trigger_detail="Low-SOH suppression coincided with material demand and a missed-demand flag.",
        ),
        _build_candidate_frame(
            rows,
            mask=online_floor_mask,
            category="ONLINE_FLOOR_PROTECTION_REVIEW",
            trigger_detail="Low-SOH or floor-protection context stayed review-only while floor risk remained visible.",
        ),
        _build_candidate_frame(
            rows,
            mask=no_prior_mask,
            category="NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            trigger_detail="Weak or absent prior demand evidence was contradicted by actual units sold.",
        ),
        _build_candidate_frame(
            rows,
            mask=strong_conversion_mask,
            category="STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
            trigger_detail="Strong sell-through and low residual capital contradict the visible capital-drag headline.",
        ),
        _build_candidate_frame(
            rows,
            mask=action_layer_mask,
            category="ACTION_LAYER_SHADOW_CALIBRATION_REVIEW",
            trigger_detail="Controlled rebuild evidence suggests a conservative action-layer miss that must remain shadow-only.",
        ),
        _build_candidate_frame(
            rows,
            mask=zero_order_mask,
            category="ZERO_ORDER_TEXT_CLEANUP_REVIEW",
            trigger_detail="Zero-order row still contains visible order-oriented language that needs review-only cleanup.",
        ),
    ]
    candidate_frames = [frame for frame in candidate_frames if not frame.empty]
    if not candidate_frames:
        return pd.DataFrame(columns=ROWS_COLUMNS)

    overlay_rows = pd.concat(candidate_frames, ignore_index=True)
    overlay_rows["_top_error_rank_sort"] = _to_numeric(overlay_rows["top_error_rank"]).fillna(10**9)
    overlay_rows["_absolute_error_sort"] = _to_numeric(overlay_rows["absolute_error_units"]).fillna(0.0)
    overlay_rows["_actual_gross_profit_sort"] = _to_numeric(overlay_rows["actual_gross_profit"]).fillna(0.0)
    overlay_rows = overlay_rows.sort_values(
        by=["_overlay_priority", "_top_error_rank_sort", "_absolute_error_sort", "_actual_gross_profit_sort", "sku_number"],
        ascending=[True, True, False, False, True],
        kind="stable",
    )
    overlay_rows = overlay_rows.drop_duplicates(subset=["source_row_id"], keep="first")
    overlay_rows = overlay_rows.sort_values(
        by=["_overlay_priority", "_top_error_rank_sort", "_absolute_error_sort", "_actual_gross_profit_sort", "sku_number"],
        ascending=[True, True, False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    return overlay_rows.loc[:, ROWS_COLUMNS].copy()


def _sample_skus(series: pd.Series, *, limit: int = 5) -> str:
    values: list[str] = []
    for value in series.astype(str).tolist():
        cleaned = value.strip()
        if not cleaned or cleaned in values:
            continue
        values.append(cleaned)
        if len(values) >= limit:
            break
    return ", ".join(values)


def _build_by_category_frame(overlay_rows_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for category in _category_order():
        category_frame = overlay_rows_frame.loc[
            overlay_rows_frame["overlay_category"].astype(str).eq(category)
        ].copy()
        observed_count = int(len(category_frame.index))
        reference_count = int(REFERENCE_CATEGORY_COUNTS.get(category, 0))
        difference = abs(observed_count - reference_count)
        if observed_count == reference_count:
            reconciliation_status = "EXACT_MATCH"
        elif observed_count > reference_count:
            reconciliation_status = "ABOVE_REFERENCE"
        else:
            reconciliation_status = "BELOW_REFERENCE"
        rows.append(
            {
                "overlay_category": category,
                "row_count": observed_count,
                "reference_row_count": reference_count,
                "absolute_difference_vs_reference": difference,
                "reconciliation_status": reconciliation_status,
                "actual_units_total": round(float(_to_numeric(category_frame.get("actual_units", pd.Series(dtype="object"))).fillna(0.0).sum()), 2),
                "actual_gross_profit_total": round(float(_to_numeric(category_frame.get("actual_gross_profit", pd.Series(dtype="object"))).fillna(0.0).sum()), 2),
                "capital_left_value_total": round(float(_to_numeric(category_frame.get("capital_left_value", pd.Series(dtype="object"))).fillna(0.0).sum()), 2),
                "sample_skus": _sample_skus(category_frame.get("sku_number", pd.Series(dtype="object"))),
                "notes": "Controlled overlay reconstruction count reconciled against the prior governed review reference count.",
            }
        )
    return pd.DataFrame(rows, columns=BY_CATEGORY_COLUMNS)


def _build_top_skus_frame(overlay_rows_frame: pd.DataFrame) -> pd.DataFrame:
    if overlay_rows_frame.empty:
        return pd.DataFrame(columns=TOP_SKUS_COLUMNS)
    rows = overlay_rows_frame.copy()
    rows["_top_error_rank_sort"] = _to_numeric(rows["top_error_rank"]).fillna(10**9)
    rows["_absolute_error_sort"] = _to_numeric(rows["absolute_error_units"]).fillna(0.0)
    rows["_actual_gross_profit_sort"] = _to_numeric(rows["actual_gross_profit"]).fillna(0.0)
    rows = rows.sort_values(
        by=["_top_error_rank_sort", "_absolute_error_sort", "_actual_gross_profit_sort", "overlay_category", "sku_number"],
        ascending=[True, False, False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    rows["overlay_rank"] = range(1, len(rows.index) + 1)
    for column_name in TOP_SKUS_COLUMNS:
        if column_name not in rows.columns:
            rows[column_name] = ""
    return rows.loc[:, TOP_SKUS_COLUMNS].copy()


def _category_count_summary(by_category_frame: pd.DataFrame) -> str:
    parts: list[str] = []
    for row in by_category_frame.itertuples(index=False):
        parts.append(f"{row.overlay_category}:{row.row_count}")
    return "; ".join(parts)


def build_promotions_materialized_source_controlled_overlay_reconstruction(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
    dry_run: bool = False,
) -> PromotionsMaterializedSourceControlledOverlayReconstructionResult:
    packet_root_path = Path(packet_root)
    inspection_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=INSPECTION_FOLDER_NAME,
        required_file_names=REQUIRED_INSPECTION_FILE_NAMES,
        stage_label="controlled-rebuild-inspection",
    )
    rebuild_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=CONTROLLED_REBUILD_FOLDER_NAME,
        required_file_names=REQUIRED_REBUILD_FILE_NAMES,
        stage_label="controlled-governed-rebuild",
    )

    missing_artifacts = [
        artifact_name
        for artifact_name, artifact_path in {
            INSPECTION_SUMMARY_FILE_NAME: inspection_root / INSPECTION_SUMMARY_FILE_NAME,
            INSPECTION_QUALITY_FILE_NAME: inspection_root / INSPECTION_QUALITY_FILE_NAME,
            REBUILD_REVIEW_ROWS_FILE_NAME: rebuild_root / REBUILD_REVIEW_ROWS_FILE_NAME,
            REBUILD_SUMMARY_FILE_NAME: rebuild_root / REBUILD_SUMMARY_FILE_NAME,
            REBUILD_TOP_ERRORS_FILE_NAME: rebuild_root / REBUILD_TOP_ERRORS_FILE_NAME,
            REBUILD_QUARANTINE_FILE_NAME: rebuild_root / REBUILD_QUARANTINE_FILE_NAME,
        }.items()
        if not artifact_path.exists()
    ]

    inspection_summary_frame = _read_csv(inspection_root / INSPECTION_SUMMARY_FILE_NAME) if not missing_artifacts or INSPECTION_SUMMARY_FILE_NAME not in missing_artifacts else pd.DataFrame(columns=SUMMARY_COLUMNS)
    inspection_quality_frame = _read_csv(inspection_root / INSPECTION_QUALITY_FILE_NAME) if not missing_artifacts or INSPECTION_QUALITY_FILE_NAME not in missing_artifacts else pd.DataFrame(columns=VALIDATION_COLUMNS)
    review_rows_frame = _read_csv(rebuild_root / REBUILD_REVIEW_ROWS_FILE_NAME) if not missing_artifacts or REBUILD_REVIEW_ROWS_FILE_NAME not in missing_artifacts else pd.DataFrame(columns=ROWS_COLUMNS)
    rebuild_summary_frame = _read_csv(rebuild_root / REBUILD_SUMMARY_FILE_NAME) if not missing_artifacts or REBUILD_SUMMARY_FILE_NAME not in missing_artifacts else pd.DataFrame(columns=SUMMARY_COLUMNS)
    top_errors_frame = _read_csv(rebuild_root / REBUILD_TOP_ERRORS_FILE_NAME) if not missing_artifacts or REBUILD_TOP_ERRORS_FILE_NAME not in missing_artifacts else pd.DataFrame(columns=ROWS_COLUMNS)
    quarantine_rows_frame = _read_csv(rebuild_root / REBUILD_QUARANTINE_FILE_NAME, allow_empty=True) if not missing_artifacts or REBUILD_QUARANTINE_FILE_NAME not in missing_artifacts else pd.DataFrame()

    inspection_summary_metrics = _metric_lookup(inspection_summary_frame)
    rebuild_summary_metrics = _metric_lookup(rebuild_summary_frame)
    selection = _selection_from_inputs(
        requested_promotion_key=promotion_key,
        inspection_summary_metrics=inspection_summary_metrics,
        review_rows_frame=review_rows_frame,
        quarantine_rows_frame=quarantine_rows_frame,
    )

    review_rows_frame = _filter_for_promotion(review_rows_frame, selection.promotion_key)
    top_errors_frame = _filter_for_promotion(top_errors_frame, selection.promotion_key)
    quarantine_rows_frame = _filter_for_promotion(quarantine_rows_frame, selection.promotion_key)

    gate_status = _normalize_text(inspection_summary_metrics.get("INSPECTION_STATUS", ""))
    metric_reconciliation_status = _normalize_text(
        inspection_summary_metrics.get("METRIC_RECONCILIATION_STATUS", "")
    )
    review_row_count = int(round(float(pd.to_numeric(pd.Series([inspection_summary_metrics.get("REVIEW_ROW_COUNT", 0)]), errors="coerce").fillna(0).iloc[0])))
    quarantine_row_count = int(round(float(pd.to_numeric(pd.Series([inspection_summary_metrics.get("QUARANTINE_ROW_COUNT", 0)]), errors="coerce").fillna(0).iloc[0])))
    production_guardrail_status = _normalize_text(
        inspection_summary_metrics.get(
            "PRODUCTION_GUARDRAIL_STATUS",
            rebuild_summary_metrics.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL"),
        )
    ) or "FAIL"
    stage12_guardrail_status = _normalize_text(
        inspection_summary_metrics.get(
            "STAGE12_GUARDRAIL_STATUS",
            rebuild_summary_metrics.get("STAGE12_GUARDRAIL_STATUS", "FAIL"),
        )
    ) or "FAIL"
    overlay_authored_next_flag = int(
        round(
            float(
                pd.to_numeric(
                    pd.Series([
                        inspection_summary_metrics.get(
                            "DOWNSTREAM_OVERLAY_RECONSTRUCTION_CAN_BE_AUTHORED_NEXT",
                            0,
                        )
                    ]),
                    errors="coerce",
                ).fillna(0.0).iloc[0]
            )
        )
    )

    gate_checks = {
        "INSPECTION_GATE_PASSED": int(gate_status in PASS_GATE_STATUSES),
        "METRIC_RECONCILIATION_PASSED": int(metric_reconciliation_status == "PASS"),
        "REVIEW_ROW_COUNT_MATCHES_EXPECTATION": int(review_row_count == EXPECTED_REVIEW_ROW_COUNT),
        "QUARANTINE_ROW_COUNT_MATCHES_EXPECTATION": int(quarantine_row_count == EXPECTED_QUARANTINE_ROW_COUNT),
        "PRODUCTION_GUARDRAIL_PASS": int(production_guardrail_status == "PASS"),
        "STAGE12_GUARDRAIL_PASS": int(stage12_guardrail_status == "PASS"),
        "OVERLAY_CAN_BE_AUTHORED_NEXT": int(overlay_authored_next_flag == 1),
        "INPUT_ARTIFACTS_PRESENT": int(not missing_artifacts),
    }

    blockers_rows: list[dict[str, object]] = []
    if missing_artifacts:
        blockers_rows.append(
            _blocker_row(
                "INPUT_ARTIFACTS_MISSING",
                "INPUT_ARTIFACT_GAP",
                "; ".join(sorted(missing_artifacts)),
                "Restore the required inspection and controlled rebuild artifacts before authoring overlay reconstruction.",
            )
        )
    if gate_checks["INSPECTION_GATE_PASSED"] == 0:
        blockers_rows.append(
            _blocker_row(
                "INSPECTION_GATE_NOT_READY",
                "GATE_FAILURE",
                f"inspection_status={gate_status}",
                "Repair the controlled rebuild inspection gate before reconstructing the review overlay packet.",
            )
        )
    if gate_checks["METRIC_RECONCILIATION_PASSED"] == 0:
        blockers_rows.append(
            _blocker_row(
                "METRIC_RECONCILIATION_FAILED",
                "GATE_FAILURE",
                f"metric_reconciliation_status={metric_reconciliation_status}",
                "Repair the controlled rebuild metric reconciliation before reconstructing the review overlay packet.",
            )
        )
    if gate_checks["REVIEW_ROW_COUNT_MATCHES_EXPECTATION"] == 0:
        blockers_rows.append(
            _blocker_row(
                "REVIEW_ROW_COUNT_MISMATCH",
                "GATE_FAILURE",
                f"review_row_count={review_row_count}, expected={EXPECTED_REVIEW_ROW_COUNT}",
                "Rebuild the controlled governed review rows so the selected promotion has the expected controlled population.",
            )
        )
    if gate_checks["QUARANTINE_ROW_COUNT_MATCHES_EXPECTATION"] == 0:
        blockers_rows.append(
            _blocker_row(
                "QUARANTINE_ROW_COUNT_MISMATCH",
                "GATE_FAILURE",
                f"quarantine_row_count={quarantine_row_count}, expected={EXPECTED_QUARANTINE_ROW_COUNT}",
                "Repair quarantine preservation before reconstructing the review overlay packet.",
            )
        )
    if gate_checks["PRODUCTION_GUARDRAIL_PASS"] == 0:
        blockers_rows.append(
            _blocker_row(
                "PRODUCTION_GUARDRAIL_FAILED",
                "GUARDRAIL_FAILURE",
                f"production_guardrail_status={production_guardrail_status}",
                "Restore production ordering invariants before reconstructing the review overlay packet.",
            )
        )
    if gate_checks["STAGE12_GUARDRAIL_PASS"] == 0:
        blockers_rows.append(
            _blocker_row(
                "STAGE12_GUARDRAIL_FAILED",
                "GUARDRAIL_FAILURE",
                f"stage12_guardrail_status={stage12_guardrail_status}",
                "Restore Stage 12 invariants before reconstructing the review overlay packet.",
            )
        )
    if gate_checks["OVERLAY_CAN_BE_AUTHORED_NEXT"] == 0:
        blockers_rows.append(
            _blocker_row(
                "OVERLAY_NOT_AUTHORED_NEXT",
                "GATE_FAILURE",
                f"downstream_overlay_reconstruction_can_be_authored_next={overlay_authored_next_flag}",
                "Wait for the controlled rebuild inspection to mark overlay reconstruction as authorable next.",
            )
        )

    overlay_rows_frame = pd.DataFrame(columns=ROWS_COLUMNS)
    by_category_frame = pd.DataFrame(columns=BY_CATEGORY_COLUMNS)
    top_skus_frame = pd.DataFrame(columns=TOP_SKUS_COLUMNS)
    reference_reconciliation_status = "NOT_RECORDED"
    action_layer_review_reconstruction_can_be_authored_next = 0
    production_fields_unchanged_flag = int(gate_checks["PRODUCTION_GUARDRAIL_PASS"] == 1)
    stage12_unchanged_flag = int(gate_checks["STAGE12_GUARDRAIL_PASS"] == 1)
    no_quarantine_rows_flag = 1
    no_order_recommendations_flag = 0
    review_only_categories_flag = 0
    reference_reconciliation_recorded_flag = 0

    if blockers_rows:
        overlay_reconstruction_status = (
            CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_GUARDRAIL_FAILURE
            if gate_checks["PRODUCTION_GUARDRAIL_PASS"] == 0 or gate_checks["STAGE12_GUARDRAIL_PASS"] == 0
            else CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_GATE_FAILURE
        )
        recommendation = (
            "Do not reconstruct the controlled review overlay packet yet. Repair the inspection gate and guardrail blockers first."
        )
    else:
        overlay_rows_frame = _build_overlay_rows(review_rows_frame, top_errors_frame, quarantine_rows_frame)
        if overlay_rows_frame.empty:
            overlay_reconstruction_status = CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_EMPTY_OVERLAY
            blockers_rows.append(
                _blocker_row(
                    "EMPTY_OVERLAY_RECONSTRUCTION",
                    "EMPTY_OVERLAY",
                    "No controlled review overlay candidates were reconstructed from the controlled governed rebuild review rows.",
                    "Review the controlled category heuristics and controlled rebuild rows before attempting downstream review-only reconstruction.",
                )
            )
            recommendation = (
                "Do not author action-layer review reconstruction yet. Repair the empty overlay reconstruction before any downstream step."
            )
        else:
            production_fields_unchanged_flag = int(
                len(overlay_rows_frame.index)
                == len(
                    overlay_rows_frame.merge(
                        review_rows_frame.loc[
                            :,
                            [
                                "source_row_id",
                                "expected_promo_demand",
                                "recommended_order_units",
                                "final_store_order_units",
                                "production_order_change_flag",
                            ],
                        ].assign(source_row_id=lambda frame: frame["source_row_id"].map(_normalize_text)),
                        on="source_row_id",
                        how="inner",
                        suffixes=("", "_source"),
                    ).loc[
                        lambda frame: frame["expected_promo_demand"].astype(str).eq(frame["expected_promo_demand_source"].astype(str))
                        & frame["recommended_order_units"].astype(str).eq(frame["recommended_order_units_source"].astype(str))
                        & frame["final_store_order_units"].astype(str).eq(frame["final_store_order_units_source"].astype(str))
                        & frame["production_order_change_flag"].astype(str).eq(frame["production_order_change_flag_source"].astype(str))
                    ].index
                )
            )
            stage12_unchanged_flag = int(
                len(overlay_rows_frame.index)
                == len(
                    overlay_rows_frame.merge(
                        review_rows_frame.loc[:, ["source_row_id", "stage_12_change_flag"]].assign(
                            source_row_id=lambda frame: frame["source_row_id"].map(_normalize_text)
                        ),
                        on="source_row_id",
                        how="inner",
                        suffixes=("", "_source"),
                    ).loc[
                        lambda frame: frame["stage_12_change_flag"].astype(str).eq(frame["stage_12_change_flag_source"].astype(str))
                    ].index
                )
            )
            quarantine_numbers = set(
                quarantine_rows_frame.get("source_row_number", pd.Series(dtype="object")).map(_normalize_text).tolist()
            )
            no_quarantine_rows_flag = int(
                not bool(overlay_rows_frame["source_row_id"].map(_normalize_text).isin(quarantine_numbers).any())
            )
            no_order_recommendations_flag = int(
                _to_numeric(overlay_rows_frame["generated_order_recommendation_flag"]).fillna(0.0).eq(0.0).all()
                and overlay_rows_frame["proposed_review_action"].astype(str).isin(
                    PROPOSED_REVIEW_ACTION_BY_CATEGORY.values()
                ).all()
            )
            review_only_categories_flag = int(
                overlay_rows_frame["overlay_category"].astype(str).isin(REVIEW_ONLY_CATEGORIES).all()
                and _to_numeric(overlay_rows_frame["review_only_flag"]).fillna(0.0).eq(1.0).all()
            )
            by_category_frame = _build_by_category_frame(overlay_rows_frame)
            reference_reconciliation_recorded_flag = int(
                len(by_category_frame.index) == len(REFERENCE_CATEGORY_COUNTS)
                and by_category_frame["reconciliation_status"].astype(str).ne("").all()
            )
            reference_reconciliation_status = "PASS" if reference_reconciliation_recorded_flag else "FAIL"
            top_skus_frame = _build_top_skus_frame(overlay_rows_frame)

            if no_order_recommendations_flag == 0:
                overlay_reconstruction_status = CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_ORDER_RECOMMENDATION_RISK
                blockers_rows.append(
                    _blocker_row(
                        "ORDER_RECOMMENDATION_RISK",
                        "REVIEW_ONLY_CONTRACT_FAILURE",
                        "Controlled overlay reconstruction generated non-review-only output semantics.",
                        "Remove order-generating behavior so the reconstruction remains review-only.",
                    )
                )
                recommendation = (
                    "Do not author action-layer review reconstruction yet. Remove order-recommendation risk from the controlled overlay reconstruction first."
                )
            else:
                overlay_reconstruction_status = (
                    CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE
                    if len(quarantine_rows_frame.index) > 0
                    else CONTROLLED_OVERLAY_RECONSTRUCTION_READY
                )
                action_layer_review_reconstruction_can_be_authored_next = int(
                    overlay_reconstruction_status
                    in {
                        CONTROLLED_OVERLAY_RECONSTRUCTION_READY,
                        CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE,
                    }
                )
                recommendation = (
                    "Dry-run confirmed the controlled review-overlay reconstruction gate and category build. Proceed to the live reconstruction write for the selected promotion only."
                    if dry_run
                    else "Controlled review-overlay reconstruction completed successfully. Review the overlay packet before authoring action-layer review reconstruction, and do not run recalibration, simulation, or training yet."
                )

    validation_rows = [
        _validation_row(
            "GATE_PASSED",
            "PASS" if not blockers_rows else "FAIL",
            int(not blockers_rows),
            f"gate_status={gate_status}; metric_reconciliation_status={metric_reconciliation_status}",
        ),
        _validation_row(
            "OVERLAY_ROWS_WRITTEN",
            "PASS" if not overlay_rows_frame.empty else "FAIL",
            int(not overlay_rows_frame.empty),
            (
                "Dry run confirmed overlay rows are ready to be written."
                if dry_run and not overlay_rows_frame.empty
                else f"overlay_rows={len(overlay_rows_frame.index)}"
            ),
        ),
        _validation_row(
            "QUARANTINE_ROW_COUNT_MATCHES_EXPECTATION",
            "PASS" if len(quarantine_rows_frame.index) == EXPECTED_QUARANTINE_ROW_COUNT else "FAIL",
            int(len(quarantine_rows_frame.index) == EXPECTED_QUARANTINE_ROW_COUNT),
            f"quarantine_rows={len(quarantine_rows_frame.index)}, expected={EXPECTED_QUARANTINE_ROW_COUNT}",
        ),
        _validation_row(
            "NO_QUARANTINE_ROWS_IN_OVERLAY_ROWS",
            "PASS" if no_quarantine_rows_flag else "FAIL",
            no_quarantine_rows_flag,
            "Quarantine row numbers remain excluded from the overlay reconstruction rows.",
        ),
        _validation_row(
            "NO_PRODUCTION_FIELDS_CHANGED",
            "PASS" if production_fields_unchanged_flag else "FAIL",
            production_fields_unchanged_flag,
            "Overlay reconstruction copies production fields from the controlled rebuild rows without mutation.",
        ),
        _validation_row(
            "STAGE12_UNCHANGED",
            "PASS" if stage12_unchanged_flag else "FAIL",
            stage12_unchanged_flag,
            "Overlay reconstruction copies Stage 12 fields from the controlled rebuild rows without mutation.",
        ),
        _validation_row(
            "NO_ORDER_RECOMMENDATIONS_GENERATED",
            "PASS" if no_order_recommendations_flag else "FAIL",
            no_order_recommendations_flag,
            "Overlay rows are review triggers only and do not generate order recommendations.",
        ),
        _validation_row(
            "OVERLAY_CATEGORIES_REVIEW_ONLY",
            "PASS" if review_only_categories_flag else "FAIL",
            review_only_categories_flag,
            "Overlay categories remain review-only and do not run downstream recalibration or simulation.",
        ),
        _validation_row(
            "CATEGORY_REFERENCE_RECONCILIATION_WRITTEN",
            "PASS" if reference_reconciliation_recorded_flag else "FAIL",
            reference_reconciliation_recorded_flag,
            f"reference_reconciliation_status={reference_reconciliation_status}",
        ),
        _validation_row(
            "REVIEW_ROW_SOURCE_COUNT_MATCHES_EXPECTATION",
            "PASS" if len(review_rows_frame.index) == EXPECTED_REVIEW_ROW_COUNT else "FAIL",
            int(len(review_rows_frame.index) == EXPECTED_REVIEW_ROW_COUNT),
            f"review_rows={len(review_rows_frame.index)}, expected={EXPECTED_REVIEW_ROW_COUNT}",
        ),
    ]

    if overlay_rows_frame.empty:
        overlay_row_count = 0
    else:
        overlay_row_count = len(overlay_rows_frame.index)
    if len(by_category_frame.index) == len(REFERENCE_CATEGORY_COUNTS):
        reference_reconciliation_status = "PASS"

    summary_frame = pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION", selection.promotion_key, "Promotion selected for controlled review-overlay reconstruction."),
            _summary_row("GATE_STATUS", gate_status, "Inspection gate status inherited from the controlled rebuild inspection."),
            _summary_row(
                "RUN_MODE",
                "DRY_RUN" if dry_run else "LIVE_RUN",
                "Dry-run validates readiness without writing live reconstruction artifacts.",
            ),
            _summary_row("DRY_RUN_FLAG", int(dry_run), "1 means the runner was invoked in dry-run mode."),
            _summary_row(
                "OVERLAY_RECONSTRUCTION_STATUS",
                overlay_reconstruction_status,
                "Controlled review-overlay reconstruction status.",
            ),
            _summary_row("OVERLAY_ROW_COUNT", overlay_row_count, "Controlled overlay reconstruction row count."),
            _summary_row(
                "QUARANTINE_ROW_COUNT",
                len(quarantine_rows_frame.index),
                "Quarantine row count preserved separately from the overlay rows.",
            ),
            _summary_row(
                "REFERENCE_RECONCILIATION_STATUS",
                reference_reconciliation_status,
                "Whether category reference reconciliation rows were written for every controlled overlay category.",
            ),
            _summary_row(
                "PRODUCTION_GUARDRAIL_STATUS",
                production_guardrail_status,
                "Production ordering logic remained unchanged through the controlled overlay reconstruction.",
            ),
            _summary_row(
                "STAGE12_GUARDRAIL_STATUS",
                stage12_guardrail_status,
                "Stage 12 remained unchanged through the controlled overlay reconstruction.",
            ),
            _summary_row(
                "ACTION_LAYER_REVIEW_RECONSTRUCTION_CAN_BE_AUTHORED_NEXT",
                action_layer_review_reconstruction_can_be_authored_next,
                "Whether action-layer review reconstruction can be authored next without running recalibration yet.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Controlled Review-Overlay Reconstruction",
            "",
            "This is a controlled review-overlay reconstruction built from the controlled governed rebuild outputs only.",
            "This does not start training.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "This does not promote auto-ordering.",
            "This does not promote shadow rules.",
            "This does not run action-layer recalibration.",
            "This does not run shadow-vs-baseline simulation.",
            "This does not run repeat-evidence.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "This keeps quarantine row 48 separate.",
            "",
            f"Selected promotion: {selection.promotion_key}",
            f"Gate status: {gate_status}",
            f"Run mode: {'DRY_RUN' if dry_run else 'LIVE_RUN'}",
            f"Overlay reconstruction status: {overlay_reconstruction_status}",
            f"Overlay row count: {overlay_row_count}",
            f"Quarantine row count: {len(quarantine_rows_frame.index)}",
            f"Category count summary: {_category_count_summary(by_category_frame) if not by_category_frame.empty else ''}",
            f"Reference reconciliation status: {reference_reconciliation_status}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Action-layer review reconstruction can be authored next: {action_layer_review_reconstruction_can_be_authored_next}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()

    return PromotionsMaterializedSourceControlledOverlayReconstructionResult(
        selected_promotion=selection,
        gate_status=gate_status,
        overlay_reconstruction_status=overlay_reconstruction_status,
        dry_run=dry_run,
        overlay_rows_frame=overlay_rows_frame,
        summary_frame=summary_frame,
        by_category_frame=by_category_frame,
        top_skus_frame=top_skus_frame,
        quarantine_rows_frame=quarantine_rows_frame,
        validation_frame=pd.DataFrame(validation_rows, columns=VALIDATION_COLUMNS),
        blockers_frame=pd.DataFrame(blockers_rows, columns=BLOCKERS_COLUMNS),
        memo_markdown=memo_markdown,
        reference_reconciliation_status=reference_reconciliation_status,
        production_guardrail_status=production_guardrail_status,
        stage12_guardrail_status=stage12_guardrail_status,
        action_layer_review_reconstruction_can_be_authored_next=action_layer_review_reconstruction_can_be_authored_next,
        recommendation=recommendation,
        artifacts_planned=PLANNED_PASS_ARTIFACTS if not blockers_rows and not overlay_rows_frame.empty else PLANNED_FAIL_ARTIFACTS,
    )


def write_promotions_materialized_source_controlled_overlay_reconstruction(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
    dry_run: bool = False,
) -> PromotionsMaterializedSourceControlledOverlayReconstructionArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_controlled_overlay_reconstruction(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
        dry_run=dry_run,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    validation_csv_path = output_root_path / "controlled_overlay_reconstruction_validation.csv"
    memo_md_path = output_root_path / "controlled_overlay_reconstruction_memo.md"
    blockers_csv_path: Path | None = None
    rows_csv_path: Path | None = None
    summary_csv_path: Path | None = None
    by_category_csv_path: Path | None = None
    top_skus_csv_path: Path | None = None
    quarantine_rows_csv_path: Path | None = None

    result.validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    if result.overlay_reconstruction_status in {
        CONTROLLED_OVERLAY_RECONSTRUCTION_READY,
        CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE,
    } and not dry_run:
        rows_csv_path = output_root_path / "controlled_overlay_reconstruction_rows.csv"
        summary_csv_path = output_root_path / "controlled_overlay_reconstruction_summary.csv"
        by_category_csv_path = output_root_path / "controlled_overlay_reconstruction_by_category.csv"
        top_skus_csv_path = output_root_path / "controlled_overlay_reconstruction_top_skus.csv"
        quarantine_rows_csv_path = output_root_path / "controlled_overlay_reconstruction_quarantine_rows.csv"

        result.overlay_rows_frame.to_csv(rows_csv_path, index=False)
        result.summary_frame.to_csv(summary_csv_path, index=False)
        result.by_category_frame.to_csv(by_category_csv_path, index=False)
        result.top_skus_frame.to_csv(top_skus_csv_path, index=False)
        result.quarantine_rows_frame.to_csv(quarantine_rows_csv_path, index=False)
    elif result.overlay_reconstruction_status not in {
        CONTROLLED_OVERLAY_RECONSTRUCTION_READY,
        CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE,
    }:
        blockers_csv_path = output_root_path / "controlled_overlay_reconstruction_blockers.csv"
        result.blockers_frame.to_csv(blockers_csv_path, index=False)

    return PromotionsMaterializedSourceControlledOverlayReconstructionArtifacts(
        output_root=str(output_root_path),
        rows_csv_path=str(rows_csv_path) if rows_csv_path is not None else None,
        summary_csv_path=str(summary_csv_path) if summary_csv_path is not None else None,
        by_category_csv_path=str(by_category_csv_path) if by_category_csv_path is not None else None,
        top_skus_csv_path=str(top_skus_csv_path) if top_skus_csv_path is not None else None,
        quarantine_rows_csv_path=str(quarantine_rows_csv_path) if quarantine_rows_csv_path is not None else None,
        validation_csv_path=str(validation_csv_path),
        blockers_csv_path=str(blockers_csv_path) if blockers_csv_path is not None else None,
        memo_md_path=str(memo_md_path),
        selected_promotion=result.selected_promotion.promotion_key,
        gate_status=result.gate_status,
        overlay_reconstruction_status=result.overlay_reconstruction_status,
        dry_run=dry_run,
        overlay_row_count=len(result.overlay_rows_frame.index),
        quarantine_row_count=len(result.quarantine_rows_frame.index),
        category_count_summary=_category_count_summary(result.by_category_frame) if not result.by_category_frame.empty else "",
        reference_reconciliation_status=result.reference_reconciliation_status,
        production_guardrail_status=result.production_guardrail_status,
        stage12_guardrail_status=result.stage12_guardrail_status,
        action_layer_review_reconstruction_can_be_authored_next=result.action_layer_review_reconstruction_can_be_authored_next,
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a controlled review-overlay reconstruction runner over the inspected controlled governed rebuild outputs."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_controlled_overlay_reconstruction(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
        dry_run=args.dry_run,
    )
    print("selected_promotion", artifacts.selected_promotion)
    print("gate_status", artifacts.gate_status)
    print("run_mode", "DRY_RUN" if artifacts.dry_run else "LIVE_RUN")
    print("overlay_reconstruction_status", artifacts.overlay_reconstruction_status)
    print("overlay_row_count", artifacts.overlay_row_count)
    print("quarantine_row_count", artifacts.quarantine_row_count)
    print("category_count_summary", artifacts.category_count_summary)
    print("reference_reconciliation_status", artifacts.reference_reconciliation_status)
    print("production_guardrail_status", artifacts.production_guardrail_status)
    print("stage12_guardrail_status", artifacts.stage12_guardrail_status)
    print(
        "action_layer_review_reconstruction_can_be_authored_next",
        artifacts.action_layer_review_reconstruction_can_be_authored_next,
    )
    print("recommendation", artifacts.recommendation)
    print("controlled_overlay_reconstruction_validation", artifacts.validation_csv_path)
    print("controlled_overlay_reconstruction_memo", artifacts.memo_md_path)
    if artifacts.rows_csv_path is not None:
        print("controlled_overlay_reconstruction_rows", artifacts.rows_csv_path)
    if artifacts.summary_csv_path is not None:
        print("controlled_overlay_reconstruction_summary", artifacts.summary_csv_path)
    if artifacts.by_category_csv_path is not None:
        print("controlled_overlay_reconstruction_by_category", artifacts.by_category_csv_path)
    if artifacts.top_skus_csv_path is not None:
        print("controlled_overlay_reconstruction_top_skus", artifacts.top_skus_csv_path)
    if artifacts.quarantine_rows_csv_path is not None:
        print("controlled_overlay_reconstruction_quarantine_rows", artifacts.quarantine_rows_csv_path)
    if artifacts.blockers_csv_path is not None:
        print("controlled_overlay_reconstruction_blockers", artifacts.blockers_csv_path)
    return 0 if artifacts.overlay_reconstruction_status in {CONTROLLED_OVERLAY_RECONSTRUCTION_READY, CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE} else 1


if __name__ == "__main__":
    raise SystemExit(main())