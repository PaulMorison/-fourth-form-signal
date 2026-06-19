from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_action_layer_review_reconstruction"
NARROWING_FOLDER_NAME = "materialized_source_controlled_overlay_narrowing_plan"
OVERLAY_RECONSTRUCTION_FOLDER_NAME = "materialized_source_controlled_overlay_reconstruction"
CONTROLLED_REBUILD_FOLDER_NAME = "materialized_source_controlled_governed_rebuild"

NARROWING_ROWS_FILE_NAME = "controlled_overlay_narrowing_plan_rows.csv"
NARROWING_SUMMARY_FILE_NAME = "controlled_overlay_narrowing_plan_summary.csv"
NARROWING_VALIDATION_FILE_NAME = "controlled_overlay_narrowing_plan_validation.csv"
NARROWING_TIERS_FILE_NAME = "controlled_overlay_narrowing_plan_tiers.csv"
NARROWING_REJECTED_ROWS_FILE_NAME = "controlled_overlay_narrowing_plan_rejected_rows.csv"
OVERLAY_QUARANTINE_FILE_NAME = "controlled_overlay_reconstruction_quarantine_rows.csv"
REBUILD_REVIEW_ROWS_FILE_NAME = "model_vs_actual_review_rows.csv"

REQUIRED_NARROWING_FILE_NAMES: tuple[str, ...] = (
    NARROWING_ROWS_FILE_NAME,
    NARROWING_SUMMARY_FILE_NAME,
    NARROWING_VALIDATION_FILE_NAME,
    NARROWING_TIERS_FILE_NAME,
    NARROWING_REJECTED_ROWS_FILE_NAME,
)

REQUIRED_OVERLAY_FILE_NAMES: tuple[str, ...] = (
    OVERLAY_QUARANTINE_FILE_NAME,
)

REQUIRED_REBUILD_FILE_NAMES: tuple[str, ...] = (
    REBUILD_REVIEW_ROWS_FILE_NAME,
)

ACTION_LAYER_REVIEW_RECONSTRUCTION_READY = "ACTION_LAYER_REVIEW_RECONSTRUCTION_READY"
ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE = (
    "ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE"
)
ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_GATE_FAILURE = (
    "ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_GATE_FAILURE"
)
ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_TIER_LEAKAGE = (
    "ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_TIER_LEAKAGE"
)
ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_ORDER_RECOMMENDATION_RISK = (
    "ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_ORDER_RECOMMENDATION_RISK"
)
ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_GUARDRAIL_FAILURE = (
    "ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_GUARDRAIL_FAILURE"
)

CONTROLLED_OVERLAY_NARROWING_READY = "CONTROLLED_OVERLAY_NARROWING_READY"
CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE = (
    "CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE"
)
READY_NARROWING_STATUSES = {
    CONTROLLED_OVERLAY_NARROWING_READY,
    CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE,
}

TIER_1_ACTION_LAYER_REVIEW_CANDIDATE = "TIER_1_ACTION_LAYER_REVIEW_CANDIDATE"
TIER_2_KEEP_FOR_OPERATOR_REVIEW = "TIER_2_KEEP_FOR_OPERATOR_REVIEW"
TIER_3_KEEP_IN_DIAGNOSTICS_ONLY = "TIER_3_KEEP_IN_DIAGNOSTICS_ONLY"
REJECT_NOISY_BROAD_TRIGGER = "REJECT_NOISY_BROAD_TRIGGER"

EXPECTED_TIER_1_ROW_COUNT = 108
EXPECTED_QUARANTINE_ROW_COUNT = 1
TIER_1_CONTROLLED_ROW_LIMIT = 120

RULE_FAMILY_BY_CATEGORY = {
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW": "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": "LOW_SOH_MISSED_DEMAND_REVIEW_RULE",
    "ONLINE_FLOOR_PROTECTION_REVIEW": "ONLINE_FLOOR_PROTECTION_REVIEW_RULE",
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
    "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW_RULE",
    "ZERO_ORDER_TEXT_CLEANUP_REVIEW": "ZERO_ORDER_TEXT_CLEANUP_REVIEW_RULE",
}

SUMMARY_COLUMNS = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)
VALIDATION_COLUMNS = (
    "check_name",
    "check_status",
    "check_flag",
    "details",
)
BLOCKERS_COLUMNS = (
    "blocker_code",
    "blocker_type",
    "blocker_detail",
    "blocking_flag",
    "remediation",
)
ROWS_COLUMNS = (
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_row_id",
    "sku_number",
    "sku_description",
    "overlay_category",
    "overlay_tier",
    "review_signal_score",
    "review_signal_label",
    "action_layer_review_reason",
    "rule_family_candidate",
    "actual_units",
    "expected_promo_demand",
    "forecast_error_units",
    "absolute_error_units",
    "actual_gross_profit",
    "capital_left_value",
    "actual_sell_through_pct",
    "store_action_label",
    "demand_evidence_label",
    "quarantine_flag",
    "production_order_change_flag",
    "stage_12_change_flag",
)
BY_CATEGORY_COLUMNS = (
    "overlay_category",
    "review_row_count",
    "row_share_pct",
    "mean_review_signal_score",
    "max_review_signal_score",
    "rule_family_candidates",
    "actual_units_total",
    "actual_gross_profit_total",
    "sample_skus",
    "notes",
)
RULE_FAMILY_PLAN_COLUMNS = (
    "rule_family_candidate",
    "review_row_count",
    "row_share_pct",
    "source_categories",
    "mean_review_signal_score",
    "max_review_signal_score",
    "sample_skus",
    "review_only_flag",
    "notes",
)
TOP_SKUS_COLUMNS = (
    "review_rank",
    "sku_number",
    "sku_description",
    "overlay_category",
    "rule_family_candidate",
    "review_signal_score",
    "review_signal_label",
    "actual_units",
    "absolute_error_units",
    "actual_gross_profit",
    "capital_left_value",
    "action_layer_review_reason",
)

PLANNED_PASS_ARTIFACTS = (
    "action_layer_review_reconstruction_rows.csv",
    "action_layer_review_reconstruction_summary.csv",
    "action_layer_review_reconstruction_by_category.csv",
    "action_layer_review_reconstruction_rule_family_plan.csv",
    "action_layer_review_reconstruction_top_skus.csv",
    "action_layer_review_reconstruction_validation.csv",
    "action_layer_review_reconstruction_quarantine_rows.csv",
    "action_layer_review_reconstruction_memo.md",
)
PLANNED_FAIL_ARTIFACTS = (
    "action_layer_review_reconstruction_blockers.csv",
    "action_layer_review_reconstruction_validation.csv",
    "action_layer_review_reconstruction_memo.md",
)


class PromotionsMaterializedSourceActionLayerReviewReconstructionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceActionLayerReviewReconstructionResult:
    selected_promotion: PromotionSelection
    gate_status: str
    action_layer_review_reconstruction_status: str
    dry_run: bool
    action_layer_review_rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_category_frame: pd.DataFrame
    rule_family_plan_frame: pd.DataFrame
    top_skus_frame: pd.DataFrame
    quarantine_rows_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    blockers_frame: pd.DataFrame
    memo_markdown: str
    input_tier_1_rows: int
    output_review_rows: int
    tier_2_leakage_count: int
    tier_3_leakage_count: int
    rejected_leakage_count: int
    quarantine_rows_included_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    action_layer_inspection_can_be_authored_next: int
    recommendation: str
    artifacts_planned: tuple[str, ...]


@dataclass(frozen=True)
class PromotionsMaterializedSourceActionLayerReviewReconstructionArtifacts:
    output_root: str
    rows_csv_path: str | None
    summary_csv_path: str | None
    by_category_csv_path: str | None
    rule_family_plan_csv_path: str | None
    top_skus_csv_path: str | None
    quarantine_rows_csv_path: str | None
    validation_csv_path: str
    blockers_csv_path: str | None
    memo_md_path: str
    selected_promotion: str
    gate_status: str
    action_layer_review_reconstruction_status: str
    dry_run: bool
    input_tier_1_rows: int
    output_review_rows: int
    tier_2_leakage_count: int
    tier_3_leakage_count: int
    rejected_leakage_count: int
    quarantine_row_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    action_layer_inspection_can_be_authored_next: int
    recommendation: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _is_blank_like(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return isinstance(value, str) and not value.strip()


def _coalesce_value(primary: object, fallback: object) -> object:
    return fallback if _is_blank_like(primary) else primary


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceActionLayerReviewReconstructionError(
            f"CSV not found: {csv_path}"
        )
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceActionLayerReviewReconstructionError(
            f"CSV is empty: {csv_path}"
        )
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceActionLayerReviewReconstructionError(
            f"CSV is empty: {csv_path}"
        )
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
    raise PromotionsMaterializedSourceActionLayerReviewReconstructionError(
        f"--upstream-root was provided, but required {stage_label} artifacts were not found. "
        f"Looked under: {candidate_locations}. Expected files: {expected_files}."
    )


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty or "metric_name" not in frame.columns:
        return {}
    return {
        _normalize_text(row.get("metric_name")): row.get("metric_value")
        for row in frame.to_dict("records")
    }


def _validation_lookup(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty or "check_name" not in frame.columns:
        return {}
    return {
        _normalize_text(row.get("check_name")): _normalize_text(row.get("check_status"))
        for row in frame.to_dict("records")
    }


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


def _blocker_row(
    blocker_code: str,
    blocker_type: str,
    blocker_detail: str,
    remediation: str,
) -> dict[str, object]:
    return {
        "blocker_code": blocker_code,
        "blocker_type": blocker_type,
        "blocker_detail": blocker_detail,
        "blocking_flag": 1,
        "remediation": remediation,
    }


def _to_numeric(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(
        series.map(lambda value: _normalize_text(value) or None),
        errors="coerce",
    )


def _to_int(value: object, *, default: int = 0) -> int:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return default
    return int(numeric)


def _to_float(value: object, *, default: float = 0.0) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return default
    return float(numeric)


def _selection_from_inputs(
    *,
    requested_promotion_key: str | None,
    summary_metrics: dict[str, object],
    narrowing_rows_frame: pd.DataFrame,
    review_rows_frame: pd.DataFrame,
) -> PromotionSelection:
    resolved_key = requested_promotion_key or _normalize_text(
        summary_metrics.get("SELECTED_PROMOTION", "")
    )
    if not resolved_key and "promotion_key" in narrowing_rows_frame.columns:
        keys = [
            _normalize_text(value)
            for value in narrowing_rows_frame["promotion_key"].drop_duplicates().tolist()
            if _normalize_text(value)
        ]
        resolved_key = keys[0] if keys else ""
    if not resolved_key and "promotion_key" in review_rows_frame.columns:
        keys = [
            _normalize_text(value)
            for value in review_rows_frame["promotion_key"].drop_duplicates().tolist()
            if _normalize_text(value)
        ]
        resolved_key = keys[0] if keys else "UNKNOWN|||UNKNOWN"
    parts = resolved_key.split("|", 3)
    if len(parts) != 4:
        return PromotionSelection(resolved_key, "", "", "")
    return PromotionSelection(
        promotion_key=resolved_key,
        promotion_name=parts[3],
        promotion_start_date=parts[1],
        promotion_end_date=parts[2],
    )


def _filter_for_promotion(frame: pd.DataFrame, promotion_key: str) -> pd.DataFrame:
    if frame.empty or "promotion_key" not in frame.columns or not promotion_key:
        return frame.copy()
    return (
        frame.loc[frame["promotion_key"].astype(str) == promotion_key]
        .reset_index(drop=True)
        .copy()
    )


def _sample_values(series: pd.Series | None, *, limit: int = 5) -> str:
    if series is None:
        return ""
    values: list[str] = []
    for value in series.astype(str).tolist():
        cleaned = value.strip()
        if not cleaned or cleaned in values:
            continue
        values.append(cleaned)
        if len(values) >= limit:
            break
    return ", ".join(values)


def _review_row_lookup(review_rows_frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    if review_rows_frame.empty or "source_row_id" not in review_rows_frame.columns:
        return {}
    lookup: dict[str, dict[str, object]] = {}
    for row in review_rows_frame.to_dict("records"):
        source_row_id = _normalize_text(row.get("source_row_id"))
        if source_row_id and source_row_id not in lookup:
            lookup[source_row_id] = row
    return lookup


def _with_review_fallback(
    row: pd.Series,
    review_lookup: dict[str, dict[str, object]],
    column_name: str,
) -> object:
    primary_value = row.get(column_name)
    source_row_id = _normalize_text(row.get("source_row_id"))
    fallback_row = review_lookup.get(source_row_id, {})
    return _coalesce_value(primary_value, fallback_row.get(column_name))


def _build_action_layer_review_rows_frame(
    tier_1_rows_frame: pd.DataFrame,
    *,
    quarantine_numbers: set[int],
    review_lookup: dict[str, dict[str, object]],
) -> pd.DataFrame:
    if tier_1_rows_frame.empty:
        return pd.DataFrame(columns=ROWS_COLUMNS)

    rows: list[dict[str, object]] = []
    for row_dict in tier_1_rows_frame.to_dict("records"):
        row = pd.Series(row_dict)
        source_row_id = _to_int(row.get("source_row_id"), default=-1)
        if source_row_id in quarantine_numbers:
            continue
        overlay_category = _normalize_text(row.get("overlay_category"))
        why_review_required = _normalize_text(
            _with_review_fallback(row, review_lookup, "why_review_required")
        )
        review_trigger_detail = _normalize_text(
            _with_review_fallback(row, review_lookup, "review_trigger_detail")
        )
        tier_reason = _normalize_text(row.get("tier_reason"))
        reason_parts = [
            part
            for part in [why_review_required, review_trigger_detail, tier_reason]
            if part
        ]
        rows.append(
            {
                "promotion_key": _normalize_text(row.get("promotion_key")),
                "promotion_name": _normalize_text(row.get("promotion_name")),
                "promotion_start_date": _normalize_text(row.get("promotion_start_date")),
                "promotion_end_date": _normalize_text(row.get("promotion_end_date")),
                "source_row_id": source_row_id,
                "sku_number": _normalize_text(
                    _with_review_fallback(row, review_lookup, "sku_number")
                ),
                "sku_description": _normalize_text(
                    _with_review_fallback(row, review_lookup, "sku_description")
                ),
                "overlay_category": overlay_category,
                "overlay_tier": TIER_1_ACTION_LAYER_REVIEW_CANDIDATE,
                "review_signal_score": _to_float(row.get("evidence_score")),
                "review_signal_label": _normalize_text(row.get("evidence_band")),
                "action_layer_review_reason": " | ".join(reason_parts)
                or "Tier 1 action-layer review candidate from the controlled narrowing surface.",
                "rule_family_candidate": RULE_FAMILY_BY_CATEGORY.get(
                    overlay_category,
                    "UNMAPPED_ACTION_LAYER_REVIEW_RULE",
                ),
                "actual_units": _with_review_fallback(row, review_lookup, "actual_units"),
                "expected_promo_demand": _to_float(
                    _with_review_fallback(row, review_lookup, "expected_promo_demand")
                ),
                "forecast_error_units": _to_float(
                    _with_review_fallback(row, review_lookup, "forecast_error_units")
                ),
                "absolute_error_units": _to_float(
                    _with_review_fallback(row, review_lookup, "absolute_error_units")
                ),
                "actual_gross_profit": _to_float(
                    _with_review_fallback(row, review_lookup, "actual_gross_profit")
                ),
                "capital_left_value": _to_float(
                    _with_review_fallback(row, review_lookup, "capital_left_value")
                ),
                "actual_sell_through_pct": _to_float(
                    _with_review_fallback(row, review_lookup, "actual_sell_through_pct")
                ),
                "store_action_label": _normalize_text(
                    _with_review_fallback(row, review_lookup, "store_action_label")
                ),
                "demand_evidence_label": _normalize_text(
                    _with_review_fallback(row, review_lookup, "demand_evidence_label")
                ),
                "quarantine_flag": 0,
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            }
        )
    frame = pd.DataFrame(rows, columns=ROWS_COLUMNS)
    if frame.empty:
        return frame
    return frame.sort_values(
        by=[
            "review_signal_score",
            "absolute_error_units",
            "actual_gross_profit",
            "overlay_category",
            "sku_number",
        ],
        ascending=[False, False, False, True, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_by_category_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=BY_CATEGORY_COLUMNS)
    rows: list[dict[str, object]] = []
    total_rows = len(rows_frame.index)
    for category, category_frame in rows_frame.groupby("overlay_category", sort=False):
        scores = _to_numeric(category_frame.get("review_signal_score")).dropna()
        rows.append(
            {
                "overlay_category": _normalize_text(category),
                "review_row_count": len(category_frame.index),
                "row_share_pct": round(len(category_frame.index) / total_rows * 100.0, 2),
                "mean_review_signal_score": round(float(scores.mean()), 4) if not scores.empty else 0.0,
                "max_review_signal_score": round(float(scores.max()), 4) if not scores.empty else 0.0,
                "rule_family_candidates": _sample_values(category_frame.get("rule_family_candidate")),
                "actual_units_total": round(
                    float(_to_numeric(category_frame.get("actual_units")).fillna(0.0).sum()),
                    2,
                ),
                "actual_gross_profit_total": round(
                    float(_to_numeric(category_frame.get("actual_gross_profit")).fillna(0.0).sum()),
                    2,
                ),
                "sample_skus": _sample_values(category_frame.get("sku_number")),
                "notes": "Tier 1-only action-layer review reconstruction category slice.",
            }
        )
    return pd.DataFrame(rows, columns=BY_CATEGORY_COLUMNS)


def _build_rule_family_plan_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=RULE_FAMILY_PLAN_COLUMNS)
    rows: list[dict[str, object]] = []
    total_rows = len(rows_frame.index)
    for rule_family, family_frame in rows_frame.groupby("rule_family_candidate", sort=False):
        scores = _to_numeric(family_frame.get("review_signal_score")).dropna()
        rows.append(
            {
                "rule_family_candidate": _normalize_text(rule_family),
                "review_row_count": len(family_frame.index),
                "row_share_pct": round(len(family_frame.index) / total_rows * 100.0, 2),
                "source_categories": _sample_values(family_frame.get("overlay_category")),
                "mean_review_signal_score": round(float(scores.mean()), 4) if not scores.empty else 0.0,
                "max_review_signal_score": round(float(scores.max()), 4) if not scores.empty else 0.0,
                "sample_skus": _sample_values(family_frame.get("sku_number")),
                "review_only_flag": 1,
                "notes": "Diagnostics-only rule family candidate plan for later inspection.",
            }
        )
    return pd.DataFrame(rows, columns=RULE_FAMILY_PLAN_COLUMNS).sort_values(
        by=["review_row_count", "mean_review_signal_score", "rule_family_candidate"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_top_skus_frame(rows_frame: pd.DataFrame, *, limit: int = 20) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=TOP_SKUS_COLUMNS)
    frame = rows_frame.sort_values(
        by=[
            "review_signal_score",
            "absolute_error_units",
            "actual_gross_profit",
            "overlay_category",
            "sku_number",
        ],
        ascending=[False, False, False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    frame = frame.head(limit).copy()
    frame.insert(0, "review_rank", range(1, len(frame.index) + 1))
    return frame.loc[:, TOP_SKUS_COLUMNS].copy()


def build_promotions_materialized_source_action_layer_review_reconstruction(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
    dry_run: bool = False,
) -> PromotionsMaterializedSourceActionLayerReviewReconstructionResult:
    packet_root_path = Path(packet_root)
    narrowing_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=NARROWING_FOLDER_NAME,
        required_file_names=REQUIRED_NARROWING_FILE_NAMES,
        stage_label="controlled-overlay-narrowing-plan",
    )
    overlay_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=OVERLAY_RECONSTRUCTION_FOLDER_NAME,
        required_file_names=REQUIRED_OVERLAY_FILE_NAMES,
        stage_label="controlled-overlay-reconstruction",
    )
    rebuild_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=CONTROLLED_REBUILD_FOLDER_NAME,
        required_file_names=REQUIRED_REBUILD_FILE_NAMES,
        stage_label="controlled-governed-rebuild",
    )

    required_paths = {
        NARROWING_ROWS_FILE_NAME: narrowing_root / NARROWING_ROWS_FILE_NAME,
        NARROWING_SUMMARY_FILE_NAME: narrowing_root / NARROWING_SUMMARY_FILE_NAME,
        NARROWING_VALIDATION_FILE_NAME: narrowing_root / NARROWING_VALIDATION_FILE_NAME,
        NARROWING_TIERS_FILE_NAME: narrowing_root / NARROWING_TIERS_FILE_NAME,
        NARROWING_REJECTED_ROWS_FILE_NAME: narrowing_root / NARROWING_REJECTED_ROWS_FILE_NAME,
        OVERLAY_QUARANTINE_FILE_NAME: overlay_root / OVERLAY_QUARANTINE_FILE_NAME,
        REBUILD_REVIEW_ROWS_FILE_NAME: rebuild_root / REBUILD_REVIEW_ROWS_FILE_NAME,
    }
    missing_artifacts = [
        artifact_name
        for artifact_name, artifact_path in required_paths.items()
        if not artifact_path.exists()
    ]

    narrowing_rows_frame = (
        _read_csv(required_paths[NARROWING_ROWS_FILE_NAME])
        if NARROWING_ROWS_FILE_NAME not in missing_artifacts
        else pd.DataFrame()
    )
    narrowing_summary_frame = (
        _read_csv(required_paths[NARROWING_SUMMARY_FILE_NAME])
        if NARROWING_SUMMARY_FILE_NAME not in missing_artifacts
        else pd.DataFrame(columns=SUMMARY_COLUMNS)
    )
    narrowing_validation_frame = (
        _read_csv(required_paths[NARROWING_VALIDATION_FILE_NAME])
        if NARROWING_VALIDATION_FILE_NAME not in missing_artifacts
        else pd.DataFrame(columns=VALIDATION_COLUMNS)
    )
    narrowing_tiers_frame = (
        _read_csv(required_paths[NARROWING_TIERS_FILE_NAME])
        if NARROWING_TIERS_FILE_NAME not in missing_artifacts
        else pd.DataFrame()
    )
    rejected_rows_frame = (
        _read_csv(required_paths[NARROWING_REJECTED_ROWS_FILE_NAME], allow_empty=True)
        if NARROWING_REJECTED_ROWS_FILE_NAME not in missing_artifacts
        else pd.DataFrame()
    )
    quarantine_rows_frame = (
        _read_csv(required_paths[OVERLAY_QUARANTINE_FILE_NAME], allow_empty=True)
        if OVERLAY_QUARANTINE_FILE_NAME not in missing_artifacts
        else pd.DataFrame()
    )
    review_rows_frame = (
        _read_csv(required_paths[REBUILD_REVIEW_ROWS_FILE_NAME])
        if REBUILD_REVIEW_ROWS_FILE_NAME not in missing_artifacts
        else pd.DataFrame()
    )

    narrowing_summary_metrics = _metric_lookup(narrowing_summary_frame)
    narrowing_validation_lookup = _validation_lookup(narrowing_validation_frame)
    selection = _selection_from_inputs(
        requested_promotion_key=promotion_key,
        summary_metrics=narrowing_summary_metrics,
        narrowing_rows_frame=narrowing_rows_frame,
        review_rows_frame=review_rows_frame,
    )

    narrowing_rows_frame = _filter_for_promotion(
        narrowing_rows_frame,
        selection.promotion_key,
    )
    rejected_rows_frame = _filter_for_promotion(
        rejected_rows_frame,
        selection.promotion_key,
    )
    quarantine_rows_frame = _filter_for_promotion(
        quarantine_rows_frame,
        selection.promotion_key,
    )
    review_rows_frame = _filter_for_promotion(
        review_rows_frame,
        selection.promotion_key,
    )

    gate_status = _normalize_text(narrowing_summary_metrics.get("NARROWING_STATUS", ""))
    production_guardrail_status = _normalize_text(
        narrowing_summary_metrics.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL")
    ) or "FAIL"
    stage12_guardrail_status = _normalize_text(
        narrowing_summary_metrics.get("STAGE12_GUARDRAIL_STATUS", "FAIL")
    ) or "FAIL"
    action_layer_authored_next_flag = _to_int(
        narrowing_summary_metrics.get("ACTION_LAYER_RECONSTRUCTION_CAN_BE_AUTHORED_NEXT", 0)
    )
    input_tier_1_rows_summary = _to_int(
        narrowing_summary_metrics.get("TIER_1_ROW_COUNT", 0)
    )
    tier_2_rows_summary = _to_int(narrowing_summary_metrics.get("TIER_2_ROW_COUNT", 0))
    tier_3_rows_summary = _to_int(narrowing_summary_metrics.get("TIER_3_ROW_COUNT", 0))
    rejected_rows_summary = _to_int(
        narrowing_summary_metrics.get("REJECTED_ROW_COUNT", 0)
    )
    quarantine_row_count = _to_int(
        narrowing_summary_metrics.get("QUARANTINE_ROW_COUNT", len(quarantine_rows_frame.index))
    )
    no_order_recommendation_risk_flag = int(
        narrowing_validation_lookup.get("NO_ORDER_RECOMMENDATIONS_GENERATED", "FAIL")
        == "PASS"
    )

    tier_1_rows_frame = narrowing_rows_frame.loc[
        narrowing_rows_frame.get("narrowing_tier", pd.Series(dtype="object")).astype(str)
        == TIER_1_ACTION_LAYER_REVIEW_CANDIDATE
    ].reset_index(drop=True)
    tier_2_rows_frame = narrowing_rows_frame.loc[
        narrowing_rows_frame.get("narrowing_tier", pd.Series(dtype="object")).astype(str)
        == TIER_2_KEEP_FOR_OPERATOR_REVIEW
    ].reset_index(drop=True)
    tier_3_rows_frame = narrowing_rows_frame.loc[
        narrowing_rows_frame.get("narrowing_tier", pd.Series(dtype="object")).astype(str)
        == TIER_3_KEEP_IN_DIAGNOSTICS_ONLY
    ].reset_index(drop=True)

    tier_lookup = {
        _normalize_text(row.get("narrowing_tier")): _to_int(row.get("row_count"))
        for row in narrowing_tiers_frame.to_dict("records")
    }
    tier_1_rows_tiers = tier_lookup.get(TIER_1_ACTION_LAYER_REVIEW_CANDIDATE, 0)

    quarantine_numbers = set(
        _to_numeric(
            quarantine_rows_frame.get("source_row_number", pd.Series(dtype="object"))
        )
        .fillna(0)
        .astype(int)
        .tolist()
    )
    review_lookup = _review_row_lookup(review_rows_frame)
    candidate_rows_frame = _build_action_layer_review_rows_frame(
        tier_1_rows_frame,
        quarantine_numbers=quarantine_numbers,
        review_lookup=review_lookup,
    )

    candidate_source_ids = set(
        _to_numeric(candidate_rows_frame.get("source_row_id", pd.Series(dtype="object")))
        .fillna(0)
        .astype(int)
        .tolist()
    )
    tier_2_source_ids = set(
        _to_numeric(tier_2_rows_frame.get("source_row_id", pd.Series(dtype="object")))
        .fillna(0)
        .astype(int)
        .tolist()
    )
    tier_3_source_ids = set(
        _to_numeric(tier_3_rows_frame.get("source_row_id", pd.Series(dtype="object")))
        .fillna(0)
        .astype(int)
        .tolist()
    )
    rejected_source_ids = set(
        _to_numeric(rejected_rows_frame.get("source_row_id", pd.Series(dtype="object")))
        .fillna(0)
        .astype(int)
        .tolist()
    )

    tier_2_leakage_count = len(candidate_source_ids.intersection(tier_2_source_ids))
    tier_3_leakage_count = len(candidate_source_ids.intersection(tier_3_source_ids))
    rejected_leakage_count = len(candidate_source_ids.intersection(rejected_source_ids))
    quarantine_rows_included_count = len(candidate_source_ids.intersection(quarantine_numbers))
    input_tier_1_rows = len(tier_1_rows_frame.index)
    output_review_rows = len(candidate_rows_frame.index)

    no_order_fields_produced_flag = int(
        not {
            "recommended_order_units",
            "final_store_order_units",
            "generated_order_recommendation_flag",
        }.intersection(set(candidate_rows_frame.columns))
    )
    output_review_only_flag = int(
        no_order_fields_produced_flag
        and int(_to_numeric(candidate_rows_frame.get("production_order_change_flag")).fillna(0).sum())
        == 0
        and int(_to_numeric(candidate_rows_frame.get("stage_12_change_flag")).fillna(0).sum())
        == 0
        and int(_to_numeric(candidate_rows_frame.get("quarantine_flag")).fillna(0).sum()) == 0
    )

    gate_failure = False
    guardrail_failure = False
    order_recommendation_risk = False
    tier_leakage_failure = False
    blockers_rows: list[dict[str, object]] = []

    if missing_artifacts:
        gate_failure = True
        blockers_rows.append(
            _blocker_row(
                "INPUT_ARTIFACTS_MISSING",
                "INPUT_ARTIFACT_GAP",
                "; ".join(sorted(missing_artifacts)),
                "Restore the narrowing-plan, quarantine, and controlled rebuild artifacts before authoring the action-layer review reconstruction.",
            )
        )
    if gate_status not in READY_NARROWING_STATUSES:
        gate_failure = True
        blockers_rows.append(
            _blocker_row(
                "NARROWING_GATE_NOT_READY",
                "GATE_FAILURE",
                f"narrowing_status={gate_status}",
                "Run the controlled overlay narrowing planner to a READY status before reconstructing the action-layer review surface.",
            )
        )
    if input_tier_1_rows_summary != EXPECTED_TIER_1_ROW_COUNT:
        gate_failure = True
        blockers_rows.append(
            _blocker_row(
                "TIER_1_ROW_COUNT_MISMATCH",
                "GATE_FAILURE",
                f"tier_1_summary_rows={input_tier_1_rows_summary}, expected={EXPECTED_TIER_1_ROW_COUNT}",
                "Repair the narrowing summary so the controlled Tier 1 surface matches the expected governed count.",
            )
        )
    if input_tier_1_rows != input_tier_1_rows_summary or tier_1_rows_tiers != input_tier_1_rows_summary:
        gate_failure = True
        blockers_rows.append(
            _blocker_row(
                "TIER_1_ROW_ACCOUNTING_MISMATCH",
                "GATE_FAILURE",
                (
                    f"tier_1_rows_file={input_tier_1_rows}, tier_1_summary_rows={input_tier_1_rows_summary}, "
                    f"tier_1_tiers_rows={tier_1_rows_tiers}"
                ),
                "Repair the narrowing plan accounting so Tier 1 rows reconcile across rows, summary, and tiers artifacts.",
            )
        )
    if input_tier_1_rows > TIER_1_CONTROLLED_ROW_LIMIT:
        gate_failure = True
        blockers_rows.append(
            _blocker_row(
                "TIER_1_SURFACE_NOT_CONTROLLED",
                "GATE_FAILURE",
                f"tier_1_rows={input_tier_1_rows}, row_limit={TIER_1_CONTROLLED_ROW_LIMIT}",
                "Reduce the Tier 1 surface further before reconstructing an action-layer review surface.",
            )
        )
    if action_layer_authored_next_flag != 1:
        gate_failure = True
        blockers_rows.append(
            _blocker_row(
                "ACTION_LAYER_NOT_AUTHORED_NEXT",
                "GATE_FAILURE",
                f"action_layer_reconstruction_can_be_authored_next={action_layer_authored_next_flag}",
                "Wait for the narrowing planner to mark the Tier 1 surface as authorable next.",
            )
        )
    if quarantine_row_count != EXPECTED_QUARANTINE_ROW_COUNT:
        gate_failure = True
        blockers_rows.append(
            _blocker_row(
                "QUARANTINE_ROW_COUNT_MISMATCH",
                "GATE_FAILURE",
                f"quarantine_row_count={quarantine_row_count}, expected={EXPECTED_QUARANTINE_ROW_COUNT}",
                "Repair quarantine preservation before reconstructing the action-layer review surface.",
            )
        )
    if production_guardrail_status != "PASS":
        guardrail_failure = True
        blockers_rows.append(
            _blocker_row(
                "PRODUCTION_GUARDRAIL_FAILED",
                "GUARDRAIL_FAILURE",
                f"production_guardrail_status={production_guardrail_status}",
                "Restore production-order invariants before reconstructing the action-layer review surface.",
            )
        )
    if stage12_guardrail_status != "PASS":
        guardrail_failure = True
        blockers_rows.append(
            _blocker_row(
                "STAGE12_GUARDRAIL_FAILED",
                "GUARDRAIL_FAILURE",
                f"stage12_guardrail_status={stage12_guardrail_status}",
                "Restore Stage 12 invariants before reconstructing the action-layer review surface.",
            )
        )
    if not no_order_recommendation_risk_flag:
        order_recommendation_risk = True
        blockers_rows.append(
            _blocker_row(
                "NARROWING_ORDER_RECOMMENDATION_RISK",
                "ORDER_RECOMMENDATION_RISK",
                "NO_ORDER_RECOMMENDATIONS_GENERATED did not pass in the narrowing validation artifact.",
                "Repair order-recommendation risk at the narrowing stage before reconstructing the action-layer review surface.",
            )
        )
    if tier_2_leakage_count > 0:
        tier_leakage_failure = True
        blockers_rows.append(
            _blocker_row(
                "TIER_2_LEAKAGE_DETECTED",
                "TIER_LEAKAGE",
                f"tier_2_leakage_count={tier_2_leakage_count}",
                "Remove Tier 2 overlap from the Tier 1 action-layer reconstruction slice.",
            )
        )
    if tier_3_leakage_count > 0:
        tier_leakage_failure = True
        blockers_rows.append(
            _blocker_row(
                "TIER_3_LEAKAGE_DETECTED",
                "TIER_LEAKAGE",
                f"tier_3_leakage_count={tier_3_leakage_count}",
                "Remove Tier 3 overlap from the Tier 1 action-layer reconstruction slice.",
            )
        )
    if rejected_leakage_count > 0:
        tier_leakage_failure = True
        blockers_rows.append(
            _blocker_row(
                "REJECTED_LEAKAGE_DETECTED",
                "TIER_LEAKAGE",
                f"rejected_leakage_count={rejected_leakage_count}",
                "Remove rejected-row overlap from the Tier 1 action-layer reconstruction slice.",
            )
        )
    if quarantine_rows_included_count > 0:
        tier_leakage_failure = True
        blockers_rows.append(
            _blocker_row(
                "QUARANTINE_ROW_LEAKAGE_DETECTED",
                "TIER_LEAKAGE",
                f"quarantine_rows_included_count={quarantine_rows_included_count}",
                "Keep quarantine row 48 separate from the reconstructed action-layer review surface.",
            )
        )
    if int(_to_numeric(candidate_rows_frame.get("production_order_change_flag")).fillna(0).sum()) != 0:
        guardrail_failure = True
        blockers_rows.append(
            _blocker_row(
                "PRODUCTION_ORDER_CHANGE_FLAG_NONZERO",
                "GUARDRAIL_FAILURE",
                "At least one candidate row carries a production-order change flag.",
                "Keep the action-layer review reconstruction strictly review-only with no production-order changes.",
            )
        )
    if int(_to_numeric(candidate_rows_frame.get("stage_12_change_flag")).fillna(0).sum()) != 0:
        guardrail_failure = True
        blockers_rows.append(
            _blocker_row(
                "STAGE12_CHANGE_FLAG_NONZERO",
                "GUARDRAIL_FAILURE",
                "At least one candidate row carries a Stage 12 change flag.",
                "Keep the action-layer review reconstruction strictly review-only with no Stage 12 changes.",
            )
        )

    if guardrail_failure:
        action_layer_review_reconstruction_status = (
            ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_GUARDRAIL_FAILURE
        )
    elif order_recommendation_risk:
        action_layer_review_reconstruction_status = (
            ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_ORDER_RECOMMENDATION_RISK
        )
    elif tier_leakage_failure:
        action_layer_review_reconstruction_status = (
            ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_TIER_LEAKAGE
        )
    elif gate_failure:
        action_layer_review_reconstruction_status = (
            ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_GATE_FAILURE
        )
    elif quarantine_row_count > 0:
        action_layer_review_reconstruction_status = (
            ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE
        )
    else:
        action_layer_review_reconstruction_status = (
            ACTION_LAYER_REVIEW_RECONSTRUCTION_READY
        )

    action_layer_inspection_can_be_authored_next = int(
        action_layer_review_reconstruction_status
        in {
            ACTION_LAYER_REVIEW_RECONSTRUCTION_READY,
            ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE,
        }
    )

    if action_layer_inspection_can_be_authored_next:
        action_layer_review_rows_frame = candidate_rows_frame
        by_category_frame = _build_by_category_frame(action_layer_review_rows_frame)
        rule_family_plan_frame = _build_rule_family_plan_frame(action_layer_review_rows_frame)
        top_skus_frame = _build_top_skus_frame(action_layer_review_rows_frame)
        recommendation = (
            "Author the diagnostics-only action-layer inspection next from this Tier 1 review surface, while keeping Tier 2, Tier 3, rejected rows, and quarantine row 48 outside the action-layer reconstruction."
        )
    else:
        action_layer_review_rows_frame = pd.DataFrame(columns=ROWS_COLUMNS)
        by_category_frame = pd.DataFrame(columns=BY_CATEGORY_COLUMNS)
        rule_family_plan_frame = pd.DataFrame(columns=RULE_FAMILY_PLAN_COLUMNS)
        top_skus_frame = pd.DataFrame(columns=TOP_SKUS_COLUMNS)
        output_review_rows = 0
        recommendation = (
            "Do not author the action-layer inspection yet. Repair the failed gate, leakage, order-risk, or guardrail blockers first."
        )

    validation_rows = [
        _validation_row(
            "INPUT_TIER_1_ROWS_MATCH_EXPECTATION",
            "PASS" if input_tier_1_rows_summary == EXPECTED_TIER_1_ROW_COUNT else "FAIL",
            int(input_tier_1_rows_summary == EXPECTED_TIER_1_ROW_COUNT),
            f"input_tier_1_rows={input_tier_1_rows_summary}, expected={EXPECTED_TIER_1_ROW_COUNT}",
        ),
        _validation_row(
            "OUTPUT_REVIEW_ROWS_MATCH_INPUT_TIER_1",
            "PASS"
            if output_review_rows == input_tier_1_rows_summary and action_layer_inspection_can_be_authored_next
            else ("PASS" if not action_layer_inspection_can_be_authored_next else "FAIL"),
            int((output_review_rows == input_tier_1_rows_summary) if action_layer_inspection_can_be_authored_next else 1),
            f"output_review_rows={output_review_rows}, input_tier_1_rows={input_tier_1_rows_summary}",
        ),
        _validation_row(
            "TIER_2_ROWS_INCLUDED_ZERO",
            "PASS" if tier_2_leakage_count == 0 else "FAIL",
            int(tier_2_leakage_count == 0),
            f"tier_2_leakage_count={tier_2_leakage_count}, tier_2_summary_rows={tier_2_rows_summary}",
        ),
        _validation_row(
            "TIER_3_ROWS_INCLUDED_ZERO",
            "PASS" if tier_3_leakage_count == 0 else "FAIL",
            int(tier_3_leakage_count == 0),
            f"tier_3_leakage_count={tier_3_leakage_count}, tier_3_summary_rows={tier_3_rows_summary}",
        ),
        _validation_row(
            "REJECTED_ROWS_INCLUDED_ZERO",
            "PASS" if rejected_leakage_count == 0 else "FAIL",
            int(rejected_leakage_count == 0),
            f"rejected_leakage_count={rejected_leakage_count}, rejected_summary_rows={rejected_rows_summary}",
        ),
        _validation_row(
            "QUARANTINE_ROW_COUNT_MATCHES_EXPECTATION",
            "PASS" if quarantine_row_count == EXPECTED_QUARANTINE_ROW_COUNT else "FAIL",
            int(quarantine_row_count == EXPECTED_QUARANTINE_ROW_COUNT),
            f"quarantine_row_count={quarantine_row_count}, expected={EXPECTED_QUARANTINE_ROW_COUNT}",
        ),
        _validation_row(
            "QUARANTINE_ROWS_INCLUDED_ZERO",
            "PASS" if quarantine_rows_included_count == 0 else "FAIL",
            int(quarantine_rows_included_count == 0),
            f"quarantine_rows_included_count={quarantine_rows_included_count}",
        ),
        _validation_row(
            "NO_ORDER_RECOMMENDATION_FIELDS_PRODUCED",
            "PASS" if no_order_fields_produced_flag else "FAIL",
            no_order_fields_produced_flag,
            "Output rows do not include order recommendation or final-order fields.",
        ),
        _validation_row(
            "PRODUCTION_GUARDRAIL_PASS",
            production_guardrail_status,
            int(production_guardrail_status == "PASS"),
            f"production_guardrail_status={production_guardrail_status}",
        ),
        _validation_row(
            "STAGE12_GUARDRAIL_PASS",
            stage12_guardrail_status,
            int(stage12_guardrail_status == "PASS"),
            f"stage12_guardrail_status={stage12_guardrail_status}",
        ),
        _validation_row(
            "ACTION_LAYER_OUTPUT_IS_REVIEW_ONLY",
            "PASS" if output_review_only_flag else "FAIL",
            output_review_only_flag,
            "Output remains review-only with zero quarantine, production-order, and Stage 12 change flags.",
        ),
        _validation_row(
            "RECALIBRATION_REMAINS_BLOCKED",
            "PASS",
            1,
            "This runner does not invoke action-layer recalibration.",
        ),
        _validation_row(
            "SHADOW_SIMULATION_REMAINS_BLOCKED",
            "PASS",
            1,
            "This runner does not invoke shadow-vs-baseline simulation.",
        ),
        _validation_row(
            "TRAINING_REMAINS_BLOCKED",
            "PASS",
            1,
            "This runner does not start training.",
        ),
    ]
    validation_frame = pd.DataFrame(validation_rows, columns=VALIDATION_COLUMNS)

    summary_rows = [
        _summary_row(
            "SELECTED_PROMOTION",
            selection.promotion_key,
            "Promotion selected for the diagnostics-only action-layer review reconstruction.",
        ),
        _summary_row(
            "GATE_STATUS",
            gate_status,
            "Upstream narrowing gate status used to authorize this action-layer reconstruction.",
        ),
        _summary_row(
            "RUN_MODE",
            "DRY_RUN" if dry_run else "LIVE_RUN",
            "Whether the runner was invoked in dry-run or live mode.",
        ),
        _summary_row(
            "ACTION_LAYER_REVIEW_RECONSTRUCTION_STATUS",
            action_layer_review_reconstruction_status,
            "Overall diagnostics-only action-layer review reconstruction status.",
        ),
        _summary_row(
            "INPUT_TIER_1_ROWS",
            input_tier_1_rows_summary,
            "Tier 1 row count inherited from the controlled narrowing plan.",
        ),
        _summary_row(
            "OUTPUT_REVIEW_ROWS",
            output_review_rows,
            "Action-layer review reconstruction row count authored from Tier 1 only.",
        ),
        _summary_row(
            "TIER_2_LEAKAGE_COUNT",
            tier_2_leakage_count,
            "Count of output source rows that overlap the Tier 2 surface.",
        ),
        _summary_row(
            "TIER_3_LEAKAGE_COUNT",
            tier_3_leakage_count,
            "Count of output source rows that overlap the Tier 3 surface.",
        ),
        _summary_row(
            "REJECTED_LEAKAGE_COUNT",
            rejected_leakage_count,
            "Count of output source rows that overlap rejected rows.",
        ),
        _summary_row(
            "QUARANTINE_ROW_COUNT",
            quarantine_row_count,
            "Quarantine row count preserved separately.",
        ),
        _summary_row(
            "PRODUCTION_GUARDRAIL_STATUS",
            production_guardrail_status,
            "Production ordering logic remained unchanged.",
        ),
        _summary_row(
            "STAGE12_GUARDRAIL_STATUS",
            stage12_guardrail_status,
            "Stage 12 remained unchanged.",
        ),
        _summary_row(
            "ACTION_LAYER_INSPECTION_CAN_BE_AUTHORED_NEXT",
            action_layer_inspection_can_be_authored_next,
            "Whether the downstream action-layer inspection pack can be authored next from this reconstructed review surface.",
        ),
    ]
    summary_frame = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)

    memo_markdown = "\n".join(
        [
            "# Action-Layer Review Reconstruction",
            "",
            "This is a diagnostics-only action-layer review reconstruction over the narrowed Tier 1 overlay surface.",
            "This does not run action-layer recalibration.",
            "This does not run shadow-vs-baseline simulation.",
            "This does not run repeat-evidence.",
            "This does not start training.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "This does not promote auto-ordering.",
            "This does not promote shadow rules.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "This keeps quarantine row 48 separate.",
            "This excludes Tier 2, Tier 3, and rejected rows from action-layer reconstruction.",
            "",
            f"Selected promotion: {selection.promotion_key}",
            f"Gate status: {gate_status}",
            f"Run mode: {'DRY_RUN' if dry_run else 'LIVE_RUN'}",
            f"Action-layer review reconstruction status: {action_layer_review_reconstruction_status}",
            f"Input Tier 1 rows: {input_tier_1_rows_summary}",
            f"Output review rows: {output_review_rows}",
            f"Tier 2 leakage count: {tier_2_leakage_count}",
            f"Tier 3 leakage count: {tier_3_leakage_count}",
            f"Rejected leakage count: {rejected_leakage_count}",
            f"Quarantine row count: {quarantine_row_count}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Whether action-layer inspection can be authored next: {action_layer_inspection_can_be_authored_next}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()

    return PromotionsMaterializedSourceActionLayerReviewReconstructionResult(
        selected_promotion=selection,
        gate_status=gate_status,
        action_layer_review_reconstruction_status=action_layer_review_reconstruction_status,
        dry_run=dry_run,
        action_layer_review_rows_frame=action_layer_review_rows_frame,
        summary_frame=summary_frame,
        by_category_frame=by_category_frame,
        rule_family_plan_frame=rule_family_plan_frame,
        top_skus_frame=top_skus_frame,
        quarantine_rows_frame=quarantine_rows_frame,
        validation_frame=validation_frame,
        blockers_frame=pd.DataFrame(blockers_rows, columns=BLOCKERS_COLUMNS),
        memo_markdown=memo_markdown,
        input_tier_1_rows=input_tier_1_rows_summary,
        output_review_rows=output_review_rows,
        tier_2_leakage_count=tier_2_leakage_count,
        tier_3_leakage_count=tier_3_leakage_count,
        rejected_leakage_count=rejected_leakage_count,
        quarantine_rows_included_count=quarantine_rows_included_count,
        production_guardrail_status=production_guardrail_status,
        stage12_guardrail_status=stage12_guardrail_status,
        action_layer_inspection_can_be_authored_next=action_layer_inspection_can_be_authored_next,
        recommendation=recommendation,
        artifacts_planned=(
            PLANNED_PASS_ARTIFACTS
            if action_layer_inspection_can_be_authored_next
            else PLANNED_FAIL_ARTIFACTS
        ),
    )


def write_promotions_materialized_source_action_layer_review_reconstruction(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
    dry_run: bool = False,
) -> PromotionsMaterializedSourceActionLayerReviewReconstructionArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = (
        Path(output_root)
        if output_root is not None
        else packet_root_path / OUTPUT_FOLDER_NAME
    )
    result = build_promotions_materialized_source_action_layer_review_reconstruction(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
        dry_run=dry_run,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    validation_csv_path = output_root_path / "action_layer_review_reconstruction_validation.csv"
    memo_md_path = output_root_path / "action_layer_review_reconstruction_memo.md"
    blockers_csv_path: Path | None = None
    rows_csv_path: Path | None = None
    summary_csv_path: Path | None = None
    by_category_csv_path: Path | None = None
    rule_family_plan_csv_path: Path | None = None
    top_skus_csv_path: Path | None = None
    quarantine_rows_csv_path: Path | None = None

    result.validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    if result.action_layer_review_reconstruction_status in {
        ACTION_LAYER_REVIEW_RECONSTRUCTION_READY,
        ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE,
    } and not dry_run:
        rows_csv_path = output_root_path / "action_layer_review_reconstruction_rows.csv"
        summary_csv_path = (
            output_root_path / "action_layer_review_reconstruction_summary.csv"
        )
        by_category_csv_path = (
            output_root_path / "action_layer_review_reconstruction_by_category.csv"
        )
        rule_family_plan_csv_path = (
            output_root_path / "action_layer_review_reconstruction_rule_family_plan.csv"
        )
        top_skus_csv_path = (
            output_root_path / "action_layer_review_reconstruction_top_skus.csv"
        )
        quarantine_rows_csv_path = (
            output_root_path / "action_layer_review_reconstruction_quarantine_rows.csv"
        )

        result.action_layer_review_rows_frame.to_csv(rows_csv_path, index=False)
        result.summary_frame.to_csv(summary_csv_path, index=False)
        result.by_category_frame.to_csv(by_category_csv_path, index=False)
        result.rule_family_plan_frame.to_csv(rule_family_plan_csv_path, index=False)
        result.top_skus_frame.to_csv(top_skus_csv_path, index=False)
        result.quarantine_rows_frame.to_csv(quarantine_rows_csv_path, index=False)
    elif result.action_layer_review_reconstruction_status not in {
        ACTION_LAYER_REVIEW_RECONSTRUCTION_READY,
        ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE,
    }:
        blockers_csv_path = (
            output_root_path / "action_layer_review_reconstruction_blockers.csv"
        )
        result.blockers_frame.to_csv(blockers_csv_path, index=False)

    return PromotionsMaterializedSourceActionLayerReviewReconstructionArtifacts(
        output_root=str(output_root_path),
        rows_csv_path=str(rows_csv_path) if rows_csv_path is not None else None,
        summary_csv_path=str(summary_csv_path) if summary_csv_path is not None else None,
        by_category_csv_path=(
            str(by_category_csv_path) if by_category_csv_path is not None else None
        ),
        rule_family_plan_csv_path=(
            str(rule_family_plan_csv_path)
            if rule_family_plan_csv_path is not None
            else None
        ),
        top_skus_csv_path=str(top_skus_csv_path) if top_skus_csv_path is not None else None,
        quarantine_rows_csv_path=(
            str(quarantine_rows_csv_path)
            if quarantine_rows_csv_path is not None
            else None
        ),
        validation_csv_path=str(validation_csv_path),
        blockers_csv_path=str(blockers_csv_path) if blockers_csv_path is not None else None,
        memo_md_path=str(memo_md_path),
        selected_promotion=result.selected_promotion.promotion_key,
        gate_status=result.gate_status,
        action_layer_review_reconstruction_status=(
            result.action_layer_review_reconstruction_status
        ),
        dry_run=dry_run,
        input_tier_1_rows=result.input_tier_1_rows,
        output_review_rows=result.output_review_rows,
        tier_2_leakage_count=result.tier_2_leakage_count,
        tier_3_leakage_count=result.tier_3_leakage_count,
        rejected_leakage_count=result.rejected_leakage_count,
        quarantine_row_count=len(result.quarantine_rows_frame.index),
        production_guardrail_status=result.production_guardrail_status,
        stage12_guardrail_status=result.stage12_guardrail_status,
        action_layer_inspection_can_be_authored_next=(
            result.action_layer_inspection_can_be_authored_next
        ),
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only action-layer review reconstruction runner from the narrowed Tier 1 overlay surface."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_action_layer_review_reconstruction(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
        dry_run=args.dry_run,
    )
    print("selected_promotion", artifacts.selected_promotion)
    print("gate_status", artifacts.gate_status)
    print("run_mode", "DRY_RUN" if artifacts.dry_run else "LIVE_RUN")
    print(
        "action_layer_review_reconstruction_status",
        artifacts.action_layer_review_reconstruction_status,
    )
    print("input_tier_1_rows", artifacts.input_tier_1_rows)
    print("output_review_rows", artifacts.output_review_rows)
    print("tier_2_leakage_count", artifacts.tier_2_leakage_count)
    print("tier_3_leakage_count", artifacts.tier_3_leakage_count)
    print("rejected_leakage_count", artifacts.rejected_leakage_count)
    print("quarantine_row_count", artifacts.quarantine_row_count)
    print("production_guardrail_status", artifacts.production_guardrail_status)
    print("stage12_guardrail_status", artifacts.stage12_guardrail_status)
    print(
        "action_layer_inspection_can_be_authored_next",
        artifacts.action_layer_inspection_can_be_authored_next,
    )
    print("recommendation", artifacts.recommendation)
    print(
        "action_layer_review_reconstruction_validation",
        artifacts.validation_csv_path,
    )
    if artifacts.rows_csv_path is not None:
        print("action_layer_review_reconstruction_rows", artifacts.rows_csv_path)
    if artifacts.summary_csv_path is not None:
        print(
            "action_layer_review_reconstruction_summary",
            artifacts.summary_csv_path,
        )
    if artifacts.by_category_csv_path is not None:
        print(
            "action_layer_review_reconstruction_by_category",
            artifacts.by_category_csv_path,
        )
    if artifacts.rule_family_plan_csv_path is not None:
        print(
            "action_layer_review_reconstruction_rule_family_plan",
            artifacts.rule_family_plan_csv_path,
        )
    if artifacts.top_skus_csv_path is not None:
        print(
            "action_layer_review_reconstruction_top_skus",
            artifacts.top_skus_csv_path,
        )
    if artifacts.quarantine_rows_csv_path is not None:
        print(
            "action_layer_review_reconstruction_quarantine_rows",
            artifacts.quarantine_rows_csv_path,
        )
    if artifacts.blockers_csv_path is not None:
        print(
            "action_layer_review_reconstruction_blockers",
            artifacts.blockers_csv_path,
        )
    print("action_layer_review_reconstruction_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())