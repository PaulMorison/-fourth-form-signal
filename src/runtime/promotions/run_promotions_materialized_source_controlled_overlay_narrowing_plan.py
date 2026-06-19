from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_controlled_overlay_narrowing_plan"
INSPECTION_FOLDER_NAME = "materialized_source_controlled_overlay_inspection"
OVERLAY_RECONSTRUCTION_FOLDER_NAME = "materialized_source_controlled_overlay_reconstruction"
CONTROLLED_REBUILD_FOLDER_NAME = "materialized_source_controlled_governed_rebuild"

INSPECTION_SUMMARY_FILE_NAME = "controlled_overlay_inspection_summary.csv"
INSPECTION_CATEGORY_QUALITY_FILE_NAME = "controlled_overlay_inspection_category_quality.csv"
INSPECTION_TOP_SKU_REVIEW_FILE_NAME = "controlled_overlay_inspection_top_sku_review.csv"
INSPECTION_BROADNESS_REVIEW_FILE_NAME = "controlled_overlay_inspection_broadness_review.csv"
OVERLAY_ROWS_FILE_NAME = "controlled_overlay_reconstruction_rows.csv"
OVERLAY_BY_CATEGORY_FILE_NAME = "controlled_overlay_reconstruction_by_category.csv"
OVERLAY_QUARANTINE_FILE_NAME = "controlled_overlay_reconstruction_quarantine_rows.csv"
REBUILD_REVIEW_ROWS_FILE_NAME = "model_vs_actual_review_rows.csv"
REBUILD_TOP_ERRORS_FILE_NAME = "model_vs_actual_top_errors.csv"

REQUIRED_INSPECTION_FILE_NAMES: tuple[str, ...] = (
    INSPECTION_SUMMARY_FILE_NAME,
    INSPECTION_CATEGORY_QUALITY_FILE_NAME,
    INSPECTION_TOP_SKU_REVIEW_FILE_NAME,
    INSPECTION_BROADNESS_REVIEW_FILE_NAME,
)

REQUIRED_OVERLAY_FILE_NAMES: tuple[str, ...] = (
    OVERLAY_ROWS_FILE_NAME,
    OVERLAY_BY_CATEGORY_FILE_NAME,
    OVERLAY_QUARANTINE_FILE_NAME,
)

REQUIRED_REBUILD_FILE_NAMES: tuple[str, ...] = (
    REBUILD_REVIEW_ROWS_FILE_NAME,
    REBUILD_TOP_ERRORS_FILE_NAME,
)

PLAN_ROWS_FILE_NAME = "controlled_overlay_narrowing_plan_rows.csv"
PLAN_BY_CATEGORY_FILE_NAME = "controlled_overlay_narrowing_plan_by_category.csv"
PLAN_TIERS_FILE_NAME = "controlled_overlay_narrowing_plan_tiers.csv"
PLAN_REJECTED_ROWS_FILE_NAME = "controlled_overlay_narrowing_plan_rejected_rows.csv"
PLAN_SUMMARY_FILE_NAME = "controlled_overlay_narrowing_plan_summary.csv"
PLAN_VALIDATION_FILE_NAME = "controlled_overlay_narrowing_plan_validation.csv"
PLAN_MEMO_FILE_NAME = "controlled_overlay_narrowing_plan_memo.md"

CONTROLLED_OVERLAY_NARROWING_READY = "CONTROLLED_OVERLAY_NARROWING_READY"
CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE = (
    "CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE"
)
CONTROLLED_OVERLAY_NARROWING_REQUIRES_REVIEW = (
    "CONTROLLED_OVERLAY_NARROWING_REQUIRES_REVIEW"
)
CONTROLLED_OVERLAY_NARROWING_BLOCKED_GUARDRAIL_FAILURE = (
    "CONTROLLED_OVERLAY_NARROWING_BLOCKED_GUARDRAIL_FAILURE"
)
CONTROLLED_OVERLAY_NARROWING_BLOCKED_ORDER_RECOMMENDATION_RISK = (
    "CONTROLLED_OVERLAY_NARROWING_BLOCKED_ORDER_RECOMMENDATION_RISK"
)

TIER_1_ACTION_LAYER_REVIEW_CANDIDATE = "TIER_1_ACTION_LAYER_REVIEW_CANDIDATE"
TIER_2_KEEP_FOR_OPERATOR_REVIEW = "TIER_2_KEEP_FOR_OPERATOR_REVIEW"
TIER_3_KEEP_IN_DIAGNOSTICS_ONLY = "TIER_3_KEEP_IN_DIAGNOSTICS_ONLY"
REJECT_NOISY_BROAD_TRIGGER = "REJECT_NOISY_BROAD_TRIGGER"

READY_INSPECTION_STATUSES: set[str] = {
    "CONTROLLED_OVERLAY_INSPECTION_PASS",
    "CONTROLLED_OVERLAY_INSPECTION_PASS_WITH_QUARANTINE",
    "CONTROLLED_OVERLAY_INSPECTION_REQUIRES_NARROWING",
}

REVIEW_SAFE_CATEGORIES: set[str] = {
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
    "ONLINE_FLOOR_PROTECTION_REVIEW",
}

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
PLAN_ROWS_METADATA_COLUMNS: tuple[str, ...] = (
    "selected_promotion",
    "narrowing_tier",
    "tier_rank",
    "overall_rank",
    "evidence_score",
    "evidence_band",
    "tier_reason",
    "review_safe_category_flag",
    "top_error_priority_flag",
    "top_sku_priority_flag",
    "category_strength_score",
    "category_noise_score",
    "category_strength_status",
    "category_noise_status",
)
BY_CATEGORY_COLUMNS: tuple[str, ...] = (
    "overlay_category",
    "input_row_count",
    "tier_1_row_count",
    "tier_2_row_count",
    "tier_3_row_count",
    "rejected_row_count",
    "retained_row_count",
    "retention_rate_pct",
    "rejection_rate_pct",
    "mean_retained_evidence_score",
    "mean_rejected_evidence_score",
    "category_strength_score",
    "category_noise_score",
    "category_strength_status",
    "category_noise_status",
    "reference_row_count",
    "category_decision_status",
)
TIERS_COLUMNS: tuple[str, ...] = (
    "narrowing_tier",
    "row_count",
    "row_share_pct",
    "mean_evidence_score",
    "min_evidence_score",
    "max_evidence_score",
    "top_categories",
    "tier_notes",
)

EXPECTED_INPUT_OVERLAY_ROW_COUNT = 598
EXPECTED_QUARANTINE_ROW_COUNT = 1
TIER_1_CONTROLLED_ROW_LIMIT = 120
TIER_1_CONTROLLED_SHARE_LIMIT_PCT = 20.0
TARGET_TIER_1_SHARE_PCT = 18.0
SMALL_SLICE_TARGET_TIER_1_SHARE_PCT = 20.0
MIN_LARGE_SLICE_TIER_1_COUNT = 50
MIN_SCORE_TIER_1 = 6.0
MIN_SCORE_TIER_2 = 4.0
MIN_SCORE_TIER_3 = 2.0
TOP_ERROR_PRIORITY_LIMIT = 20
TOP_ERROR_SECONDARY_LIMIT = 50


class PromotionsMaterializedSourceControlledOverlayNarrowingPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceControlledOverlayNarrowingPlanResult:
    selected_promotion: PromotionSelection
    narrowing_status: str
    input_overlay_rows: int
    tier_1_row_count: int
    tier_2_row_count: int
    tier_3_row_count: int
    rejected_row_count: int
    narrowing_ratio: float
    strongest_retained_category: str
    noisiest_rejected_category: str
    quarantine_row_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    action_layer_reconstruction_can_be_authored_next: int
    plan_rows_frame: pd.DataFrame
    by_category_frame: pd.DataFrame
    tiers_frame: pd.DataFrame
    rejected_rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str
    recommendation: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceControlledOverlayNarrowingPlanArtifacts:
    output_root: str
    plan_rows_csv_path: str
    by_category_csv_path: str
    tiers_csv_path: str
    rejected_rows_csv_path: str
    summary_csv_path: str
    validation_csv_path: str
    memo_md_path: str
    selected_promotion: str
    narrowing_status: str
    input_overlay_rows: int
    tier_1_row_count: int
    tier_2_row_count: int
    tier_3_row_count: int
    rejected_row_count: int
    narrowing_ratio: float
    strongest_retained_category: str
    noisiest_rejected_category: str
    quarantine_row_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    action_layer_reconstruction_can_be_authored_next: int
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
        raise PromotionsMaterializedSourceControlledOverlayNarrowingPlanError(
            f"CSV not found: {csv_path}"
        )
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceControlledOverlayNarrowingPlanError(
            f"CSV is empty: {csv_path}"
        )
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceControlledOverlayNarrowingPlanError(
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
    raise PromotionsMaterializedSourceControlledOverlayNarrowingPlanError(
        f"--upstream-root was provided, but required {stage_label} artifacts were not found. "
        f"Looked under: {candidate_locations}. Expected files: {expected_files}."
    )


def _metric_lookup(
    frame: pd.DataFrame,
    *,
    key_column: str = "metric_name",
    value_column: str = "metric_value",
) -> dict[str, object]:
    if frame.empty or key_column not in frame.columns or value_column not in frame.columns:
        return {}
    lookup: dict[str, object] = {}
    for row in frame.to_dict("records"):
        lookup[_normalize_text(row.get(key_column))] = row.get(value_column)
    return lookup


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
    overlay_rows_frame: pd.DataFrame,
) -> PromotionSelection:
    resolved_key = requested_promotion_key or _normalize_text(
        summary_metrics.get("SELECTED_PROMOTION", "")
    )
    if not resolved_key and "promotion_key" in overlay_rows_frame.columns:
        keys = [
            _normalize_text(value)
            for value in overlay_rows_frame["promotion_key"].drop_duplicates().tolist()
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


def _contains_order_language(value: object) -> int:
    text = _normalize_text(value).lower()
    if not text:
        return 0
    tokens = (
        "order now",
        "order controlled quantity",
        "buy now",
        "allocate now",
        "send stock",
    )
    return int(any(token in text for token in tokens))


def _tier_1_target_count(input_overlay_rows: int) -> int:
    if input_overlay_rows <= 0:
        return 0
    if input_overlay_rows >= 100:
        return min(
            TIER_1_CONTROLLED_ROW_LIMIT,
            max(
                MIN_LARGE_SLICE_TIER_1_COUNT,
                round(input_overlay_rows * TARGET_TIER_1_SHARE_PCT / 100.0),
            ),
        )
    return max(1, round(input_overlay_rows * SMALL_SLICE_TARGET_TIER_1_SHARE_PCT / 100.0))


def _frame_lookup(frame: pd.DataFrame, key_column: str) -> dict[str, dict[str, object]]:
    if frame.empty or key_column not in frame.columns:
        return {}
    lookup: dict[str, dict[str, object]] = {}
    for row in frame.to_dict("records"):
        lookup[_normalize_text(row.get(key_column))] = row
    return lookup


def _top_sku_lookup(top_sku_review_frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    lookup = _frame_lookup(top_sku_review_frame, "sku_number")
    return {_normalize_text(key): value for key, value in lookup.items() if _normalize_text(key)}


def _top_error_lookup(top_errors_frame: pd.DataFrame) -> pd.DataFrame:
    if top_errors_frame.empty or "source_row_id" not in top_errors_frame.columns:
        return pd.DataFrame(columns=["source_row_id", "top_error_rank_lookup"])
    lookup_frame = top_errors_frame.loc[:, ["source_row_id", "error_rank"]].copy()
    lookup_frame["source_row_id"] = lookup_frame["source_row_id"].map(_normalize_text)
    lookup_frame = lookup_frame.drop_duplicates(subset=["source_row_id"], keep="first")
    return lookup_frame.rename(columns={"error_rank": "top_error_rank_lookup"})


def _attach_top_error_ranks(
    overlay_rows_frame: pd.DataFrame,
    rebuild_top_errors_frame: pd.DataFrame,
) -> pd.DataFrame:
    if overlay_rows_frame.empty:
        return overlay_rows_frame.copy()
    attached_frame = overlay_rows_frame.copy()
    attached_frame["source_row_id"] = attached_frame["source_row_id"].map(_normalize_text)
    lookup_frame = _top_error_lookup(rebuild_top_errors_frame)
    if not lookup_frame.empty:
        attached_frame = attached_frame.merge(lookup_frame, on="source_row_id", how="left")
    current_ranks = _to_numeric(attached_frame.get("top_error_rank"))
    lookup_ranks = _to_numeric(attached_frame.get("top_error_rank_lookup"))
    attached_frame["top_error_rank"] = current_ranks.fillna(lookup_ranks).fillna(9999)
    if "top_error_rank_lookup" in attached_frame.columns:
        attached_frame = attached_frame.drop(columns=["top_error_rank_lookup"])
    return attached_frame


def _score_row(
    row: pd.Series,
    *,
    category_meta: dict[str, object],
    top_sku_meta: dict[str, object] | None,
) -> tuple[float, str, int]:
    category = _normalize_text(row.get("overlay_category"))
    actual_units = _to_float(row.get("actual_units"))
    expected_units = _to_float(row.get("expected_promo_demand"))
    absolute_error_units = _to_float(row.get("absolute_error_units"))
    actual_gross_profit = _to_float(row.get("actual_gross_profit"))
    gross_profit_represented = _to_float(row.get("gross_profit_represented"))
    capital_left_value = _to_float(row.get("capital_left_value"))
    stockout_flag = _to_int(row.get("stockout_or_missed_demand_flag"))
    top_error_rank = _to_float(row.get("top_error_rank"), default=9999.0)
    category_noise_score = _to_float(category_meta.get("noise_score"))
    category_strength_status = _normalize_text(category_meta.get("strength_status"))
    category_noise_status = _normalize_text(category_meta.get("noise_status"))

    score = 0.0
    reasons: list[str] = []
    category_weight_lookup = {
        "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": (4.0, "strong conversion category"),
        "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": (2.0, "low soh missed demand"),
        "NO_PRIOR_DEMAND_SURPRISE_REVIEW": (1.5, "no prior demand surprise"),
        "ONLINE_FLOOR_PROTECTION_REVIEW": (1.0, "online floor protection"),
        "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": (1.0, "action layer shadow diagnostics"),
    }
    if category in category_weight_lookup:
        weight, label = category_weight_lookup[category]
        score += weight
        reasons.append(label)

    demand_gap = actual_units - expected_units
    if demand_gap >= 5.0:
        score += 3.0
        reasons.append("material demand gap")
    elif demand_gap >= 3.0:
        score += 2.0
        reasons.append("strong demand gap")
    elif demand_gap >= 1.0:
        score += 1.0
        reasons.append("positive demand gap")

    if absolute_error_units >= 8.0:
        score += 3.0
        reasons.append("very high absolute error")
    elif absolute_error_units >= 5.0:
        score += 2.0
        reasons.append("high absolute error")
    elif absolute_error_units >= 3.0:
        score += 1.0
        reasons.append("moderate absolute error")

    if actual_units >= 7.0:
        score += 2.0
        reasons.append("strong actual demand")
    elif actual_units >= 4.0:
        score += 1.0
        reasons.append("material actual demand")

    if stockout_flag and actual_units > 0.0:
        score += 2.0
        reasons.append("missed demand flag")

    represented_gp = max(actual_gross_profit, gross_profit_represented)
    if represented_gp >= 25.0:
        score += 2.0
        reasons.append("high gp represented")
    elif represented_gp >= 10.0:
        score += 1.0
        reasons.append("positive gp represented")

    if represented_gp >= 10.0 and capital_left_value <= 1.0:
        score += 1.0
        reasons.append("low capital left with gp")

    if top_error_rank <= TOP_ERROR_PRIORITY_LIMIT:
        score += 3.0
        reasons.append("top 20 error")
    elif top_error_rank <= TOP_ERROR_SECONDARY_LIMIT:
        score += 2.0
        reasons.append("top 50 error")
    elif top_error_rank <= 100.0:
        score += 1.0
        reasons.append("top 100 error")

    if top_sku_meta is not None:
        score += 1.0
        reasons.append("top sku review")

    if category_strength_status == "STRONG_REVIEW_TRIGGER":
        score += 1.0
        reasons.append("strong category strength")

    if category_noise_status == "NOISY_REVIEW_CATEGORY":
        score -= 1.0
        reasons.append("noisy category penalty")

    if actual_units <= 1.0:
        score -= 1.0
        reasons.append("low actual demand")
    if represented_gp < 5.0:
        score -= 1.0
        reasons.append("low gp signal")
    if category_noise_score >= 150.0:
        score -= 1.0
        reasons.append("high category breadth")

    hard_reject = int(
        (
            absolute_error_units < 2.0
            and actual_units <= 1.0
            and represented_gp < 5.0
            and stockout_flag == 0
            and top_error_rank > 100.0
        )
        or (
            category == "ZERO_ORDER_TEXT_CLEANUP_REVIEW"
            and _contains_order_language(row.get("store_action_reason"))
        )
    )
    if hard_reject:
        reasons.append("weak demand economics or cleanup order language")

    return round(score, 2), "; ".join(reasons) or "limited evidence", hard_reject


def _evidence_band(score: float) -> str:
    if score >= MIN_SCORE_TIER_1:
        return "HIGH_EVIDENCE"
    if score >= MIN_SCORE_TIER_2:
        return "MODERATE_EVIDENCE"
    if score >= MIN_SCORE_TIER_3:
        return "LOW_EVIDENCE"
    return "WEAK_EVIDENCE"


def _build_classified_frame(
    overlay_rows_frame: pd.DataFrame,
    *,
    category_lookup: dict[str, dict[str, object]],
    top_sku_lookup: dict[str, dict[str, object]],
    target_tier_1_count: int,
) -> pd.DataFrame:
    if overlay_rows_frame.empty:
        return pd.DataFrame(columns=[*overlay_rows_frame.columns, *PLAN_ROWS_METADATA_COLUMNS])

    scored_rows: list[dict[str, object]] = []
    for row_dict in overlay_rows_frame.to_dict("records"):
        row = pd.Series(row_dict)
        category = _normalize_text(row.get("overlay_category"))
        sku_number = _normalize_text(row.get("sku_number"))
        category_meta = category_lookup.get(category, {})
        top_sku_meta = top_sku_lookup.get(sku_number)
        score, tier_reason, hard_reject = _score_row(
            row,
            category_meta=category_meta,
            top_sku_meta=top_sku_meta,
        )
        top_error_rank = _to_int(row.get("top_error_rank"), default=9999)
        scored_rows.append(
            {
                **row_dict,
                "selected_promotion": _normalize_text(row.get("promotion_key")),
                "evidence_score": score,
                "evidence_band": _evidence_band(score),
                "tier_reason": tier_reason,
                "review_safe_category_flag": int(category in REVIEW_SAFE_CATEGORIES),
                "top_error_priority_flag": int(top_error_rank <= TOP_ERROR_PRIORITY_LIMIT),
                "top_sku_priority_flag": int(top_sku_meta is not None),
                "category_strength_score": _to_float(category_meta.get("strength_score")),
                "category_noise_score": _to_float(category_meta.get("noise_score")),
                "category_strength_status": _normalize_text(category_meta.get("strength_status")) or "UNKNOWN",
                "category_noise_status": _normalize_text(category_meta.get("noise_status")) or "UNKNOWN",
                "hard_reject_flag": hard_reject,
            }
        )

    classified_frame = pd.DataFrame(scored_rows)
    classified_frame = classified_frame.sort_values(
        by=[
            "hard_reject_flag",
            "evidence_score",
            "top_error_priority_flag",
            "top_sku_priority_flag",
            "actual_gross_profit",
            "absolute_error_units",
            "actual_units",
            "sku_number",
        ],
        ascending=[True, False, False, False, False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    classified_frame["overall_rank"] = range(1, len(classified_frame.index) + 1)
    classified_frame["narrowing_tier"] = REJECT_NOISY_BROAD_TRIGGER
    classified_frame["tier_rank"] = 0

    retained_mask = classified_frame["hard_reject_flag"].eq(0)
    tier_1_candidates = classified_frame.index[
        retained_mask & classified_frame["evidence_score"].ge(MIN_SCORE_TIER_1)
    ].tolist()
    for tier_rank, index_value in enumerate(tier_1_candidates[:target_tier_1_count], start=1):
        classified_frame.at[index_value, "narrowing_tier"] = TIER_1_ACTION_LAYER_REVIEW_CANDIDATE
        classified_frame.at[index_value, "tier_rank"] = tier_rank

    tier_2_candidates = classified_frame.index[
        retained_mask
        & classified_frame["narrowing_tier"].eq(REJECT_NOISY_BROAD_TRIGGER)
        & classified_frame["evidence_score"].ge(MIN_SCORE_TIER_2)
    ].tolist()
    for tier_rank, index_value in enumerate(tier_2_candidates, start=1):
        classified_frame.at[index_value, "narrowing_tier"] = TIER_2_KEEP_FOR_OPERATOR_REVIEW
        classified_frame.at[index_value, "tier_rank"] = tier_rank

    tier_3_candidates = classified_frame.index[
        retained_mask
        & classified_frame["narrowing_tier"].eq(REJECT_NOISY_BROAD_TRIGGER)
        & classified_frame["evidence_score"].ge(MIN_SCORE_TIER_3)
    ].tolist()
    for tier_rank, index_value in enumerate(tier_3_candidates, start=1):
        classified_frame.at[index_value, "narrowing_tier"] = TIER_3_KEEP_IN_DIAGNOSTICS_ONLY
        classified_frame.at[index_value, "tier_rank"] = tier_rank

    noisy_low_signal_mask = (
        classified_frame["narrowing_tier"].eq(TIER_3_KEEP_IN_DIAGNOSTICS_ONLY)
        & classified_frame["category_noise_status"].eq("NOISY_REVIEW_CATEGORY")
        & classified_frame["evidence_score"].lt(3.0)
    )
    classified_frame.loc[noisy_low_signal_mask, "narrowing_tier"] = REJECT_NOISY_BROAD_TRIGGER
    classified_frame.loc[noisy_low_signal_mask, "tier_rank"] = 0

    return classified_frame.drop(columns=["hard_reject_flag"])


def _build_by_category_frame(
    classified_frame: pd.DataFrame,
    *,
    category_lookup: dict[str, dict[str, object]],
    reference_lookup: dict[str, dict[str, object]],
) -> pd.DataFrame:
    if classified_frame.empty:
        return pd.DataFrame(columns=BY_CATEGORY_COLUMNS)

    rows: list[dict[str, object]] = []
    for category, category_frame in classified_frame.groupby("overlay_category", sort=False):
        input_row_count = len(category_frame.index)
        tier_1_row_count = int(
            category_frame["narrowing_tier"].eq(TIER_1_ACTION_LAYER_REVIEW_CANDIDATE).sum()
        )
        tier_2_row_count = int(
            category_frame["narrowing_tier"].eq(TIER_2_KEEP_FOR_OPERATOR_REVIEW).sum()
        )
        tier_3_row_count = int(
            category_frame["narrowing_tier"].eq(TIER_3_KEEP_IN_DIAGNOSTICS_ONLY).sum()
        )
        rejected_row_count = int(
            category_frame["narrowing_tier"].eq(REJECT_NOISY_BROAD_TRIGGER).sum()
        )
        retained_row_count = tier_1_row_count + tier_2_row_count + tier_3_row_count
        retention_rate_pct = round(retained_row_count / input_row_count * 100.0, 2) if input_row_count else 0.0
        rejection_rate_pct = round(rejected_row_count / input_row_count * 100.0, 2) if input_row_count else 0.0
        retained_scores = _to_numeric(
            category_frame.loc[
                category_frame["narrowing_tier"].ne(REJECT_NOISY_BROAD_TRIGGER),
                "evidence_score",
            ]
        ).dropna()
        rejected_scores = _to_numeric(
            category_frame.loc[
                category_frame["narrowing_tier"].eq(REJECT_NOISY_BROAD_TRIGGER),
                "evidence_score",
            ]
        ).dropna()
        category_meta = category_lookup.get(_normalize_text(category), {})
        reference_meta = reference_lookup.get(_normalize_text(category), {})
        if tier_1_row_count > 0:
            decision_status = "CATEGORY_HAS_ACTION_LAYER_CANDIDATES"
        elif retained_row_count > rejected_row_count:
            decision_status = "CATEGORY_RETAINS_OPERATOR_VALUE"
        else:
            decision_status = "CATEGORY_MOSTLY_REJECTED_AS_BROAD"
        rows.append(
            {
                "overlay_category": _normalize_text(category),
                "input_row_count": input_row_count,
                "tier_1_row_count": tier_1_row_count,
                "tier_2_row_count": tier_2_row_count,
                "tier_3_row_count": tier_3_row_count,
                "rejected_row_count": rejected_row_count,
                "retained_row_count": retained_row_count,
                "retention_rate_pct": retention_rate_pct,
                "rejection_rate_pct": rejection_rate_pct,
                "mean_retained_evidence_score": round(float(retained_scores.mean()), 4) if not retained_scores.empty else 0.0,
                "mean_rejected_evidence_score": round(float(rejected_scores.mean()), 4) if not rejected_scores.empty else 0.0,
                "category_strength_score": _to_float(category_meta.get("strength_score")),
                "category_noise_score": _to_float(category_meta.get("noise_score")),
                "category_strength_status": _normalize_text(category_meta.get("strength_status")) or "UNKNOWN",
                "category_noise_status": _normalize_text(category_meta.get("noise_status")) or "UNKNOWN",
                "reference_row_count": _to_int(reference_meta.get("reference_row_count")),
                "category_decision_status": decision_status,
            }
        )
    return pd.DataFrame(rows, columns=BY_CATEGORY_COLUMNS)


def _build_tiers_frame(classified_frame: pd.DataFrame) -> pd.DataFrame:
    if classified_frame.empty:
        return pd.DataFrame(columns=TIERS_COLUMNS)

    notes_lookup = {
        TIER_1_ACTION_LAYER_REVIEW_CANDIDATE: "Most evidence-supported rows for later action-layer review authoring.",
        TIER_2_KEEP_FOR_OPERATOR_REVIEW: "Rows with usable operator review value but not the tightest next surface.",
        TIER_3_KEEP_IN_DIAGNOSTICS_ONLY: "Rows retained for context and diagnostics-only follow-up.",
        REJECT_NOISY_BROAD_TRIGGER: "Rows rejected from the narrowed surface but retained for auditability.",
    }
    total_rows = len(classified_frame.index)
    tier_rows: list[dict[str, object]] = []
    for tier_name in (
        TIER_1_ACTION_LAYER_REVIEW_CANDIDATE,
        TIER_2_KEEP_FOR_OPERATOR_REVIEW,
        TIER_3_KEEP_IN_DIAGNOSTICS_ONLY,
        REJECT_NOISY_BROAD_TRIGGER,
    ):
        tier_frame = classified_frame.loc[classified_frame["narrowing_tier"] == tier_name].copy()
        scores = _to_numeric(tier_frame.get("evidence_score")).dropna()
        top_categories = "; ".join(
            f"{category}:{count}"
            for category, count in tier_frame.get("overlay_category", pd.Series(dtype="object"))
            .astype(str)
            .value_counts()
            .head(3)
            .to_dict()
            .items()
        )
        tier_rows.append(
            {
                "narrowing_tier": tier_name,
                "row_count": len(tier_frame.index),
                "row_share_pct": round(len(tier_frame.index) / total_rows * 100.0, 2) if total_rows else 0.0,
                "mean_evidence_score": round(float(scores.mean()), 4) if not scores.empty else 0.0,
                "min_evidence_score": round(float(scores.min()), 4) if not scores.empty else 0.0,
                "max_evidence_score": round(float(scores.max()), 4) if not scores.empty else 0.0,
                "top_categories": top_categories,
                "tier_notes": notes_lookup[tier_name],
            }
        )
    return pd.DataFrame(tier_rows, columns=TIERS_COLUMNS)


def _strongest_retained_category(by_category_frame: pd.DataFrame) -> str:
    retained_frame = by_category_frame.loc[by_category_frame["retained_row_count"] > 0].copy()
    if retained_frame.empty:
        return ""
    row = retained_frame.sort_values(
        by=[
            "tier_1_row_count",
            "mean_retained_evidence_score",
            "retained_row_count",
            "overlay_category",
        ],
        ascending=[False, False, False, True],
        kind="stable",
    ).iloc[0]
    return _normalize_text(row["overlay_category"])


def _noisiest_rejected_category(by_category_frame: pd.DataFrame) -> str:
    rejected_frame = by_category_frame.loc[by_category_frame["rejected_row_count"] > 0].copy()
    if rejected_frame.empty:
        return ""
    row = rejected_frame.sort_values(
        by=["category_noise_score", "rejected_row_count", "overlay_category"],
        ascending=[False, False, True],
        kind="stable",
    ).iloc[0]
    return _normalize_text(row["overlay_category"])


def build_promotions_materialized_source_controlled_overlay_narrowing_plan(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceControlledOverlayNarrowingPlanResult:
    packet_root_path = Path(packet_root)
    inspection_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=INSPECTION_FOLDER_NAME,
        required_file_names=REQUIRED_INSPECTION_FILE_NAMES,
        stage_label="controlled-overlay-inspection",
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

    inspection_summary_frame = _read_csv(inspection_root / INSPECTION_SUMMARY_FILE_NAME)
    inspection_category_quality_frame = _read_csv(
        inspection_root / INSPECTION_CATEGORY_QUALITY_FILE_NAME
    )
    inspection_top_sku_review_frame = _read_csv(
        inspection_root / INSPECTION_TOP_SKU_REVIEW_FILE_NAME,
        allow_empty=True,
    )
    inspection_broadness_review_frame = _read_csv(
        inspection_root / INSPECTION_BROADNESS_REVIEW_FILE_NAME
    )
    overlay_rows_frame = _read_csv(overlay_root / OVERLAY_ROWS_FILE_NAME)
    overlay_by_category_frame = _read_csv(overlay_root / OVERLAY_BY_CATEGORY_FILE_NAME)
    overlay_quarantine_rows_frame = _read_csv(
        overlay_root / OVERLAY_QUARANTINE_FILE_NAME,
        allow_empty=True,
    )
    rebuild_review_rows_frame = _read_csv(rebuild_root / REBUILD_REVIEW_ROWS_FILE_NAME)
    rebuild_top_errors_frame = _read_csv(rebuild_root / REBUILD_TOP_ERRORS_FILE_NAME)

    inspection_summary_metrics = _metric_lookup(inspection_summary_frame)
    inspection_broadness_metrics = _metric_lookup(
        inspection_broadness_review_frame,
        key_column="broadness_metric",
        value_column="metric_value",
    )
    selection = _selection_from_inputs(
        requested_promotion_key=promotion_key,
        summary_metrics=inspection_summary_metrics,
        overlay_rows_frame=overlay_rows_frame,
    )

    overlay_rows_frame = _filter_for_promotion(overlay_rows_frame, selection.promotion_key)
    overlay_quarantine_rows_frame = _filter_for_promotion(
        overlay_quarantine_rows_frame,
        selection.promotion_key,
    )
    rebuild_review_rows_frame = _filter_for_promotion(
        rebuild_review_rows_frame,
        selection.promotion_key,
    )
    rebuild_top_errors_frame = _filter_for_promotion(
        rebuild_top_errors_frame,
        selection.promotion_key,
    )
    overlay_rows_frame = _attach_top_error_ranks(
        overlay_rows_frame,
        rebuild_top_errors_frame,
    )

    category_lookup = _frame_lookup(inspection_category_quality_frame, "overlay_category")
    reference_lookup = _frame_lookup(overlay_by_category_frame, "overlay_category")
    top_sku_lookup = _top_sku_lookup(inspection_top_sku_review_frame)

    input_overlay_rows = len(overlay_rows_frame.index)
    quarantine_row_count = len(overlay_quarantine_rows_frame.index)
    review_row_count = len(rebuild_review_rows_frame.index)
    target_tier_1_count = _tier_1_target_count(input_overlay_rows)

    classified_frame = _build_classified_frame(
        overlay_rows_frame,
        category_lookup=category_lookup,
        top_sku_lookup=top_sku_lookup,
        target_tier_1_count=target_tier_1_count,
    )
    plan_rows_frame = classified_frame.loc[
        classified_frame["narrowing_tier"].isin(
            (
                TIER_1_ACTION_LAYER_REVIEW_CANDIDATE,
                TIER_2_KEEP_FOR_OPERATOR_REVIEW,
                TIER_3_KEEP_IN_DIAGNOSTICS_ONLY,
            )
        )
    ].reset_index(drop=True)
    rejected_rows_frame = classified_frame.loc[
        classified_frame["narrowing_tier"].eq(REJECT_NOISY_BROAD_TRIGGER)
    ].reset_index(drop=True)
    by_category_frame = _build_by_category_frame(
        classified_frame,
        category_lookup=category_lookup,
        reference_lookup=reference_lookup,
    )
    tiers_frame = _build_tiers_frame(classified_frame)

    tier_1_row_count = int(
        plan_rows_frame["narrowing_tier"].eq(TIER_1_ACTION_LAYER_REVIEW_CANDIDATE).sum()
    )
    tier_2_row_count = int(
        plan_rows_frame["narrowing_tier"].eq(TIER_2_KEEP_FOR_OPERATOR_REVIEW).sum()
    )
    tier_3_row_count = int(
        plan_rows_frame["narrowing_tier"].eq(TIER_3_KEEP_IN_DIAGNOSTICS_ONLY).sum()
    )
    rejected_row_count = len(rejected_rows_frame.index)
    narrowing_ratio = round(tier_1_row_count / input_overlay_rows, 4) if input_overlay_rows else 0.0
    strongest_retained_category = _strongest_retained_category(by_category_frame)
    noisiest_rejected_category = _noisiest_rejected_category(by_category_frame)

    inspection_status = _normalize_text(
        inspection_summary_metrics.get("INSPECTION_STATUS", "")
    )
    production_guardrail_status = _normalize_text(
        inspection_summary_metrics.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL")
    ) or "FAIL"
    stage12_guardrail_status = _normalize_text(
        inspection_summary_metrics.get("STAGE12_GUARDRAIL_STATUS", "FAIL")
    ) or "FAIL"
    inspection_ready_flag = int(inspection_status in READY_INSPECTION_STATUSES)

    quarantine_numbers = set(
        _to_numeric(
            overlay_quarantine_rows_frame.get("source_row_number", pd.Series(dtype="object"))
        )
        .fillna(0)
        .astype(int)
        .tolist()
    )
    narrowed_row_ids = set(
        _to_numeric(plan_rows_frame.get("source_row_id", pd.Series(dtype="object")))
        .fillna(0)
        .astype(int)
        .tolist()
    )
    no_quarantine_rows_included_flag = int(
        not bool(quarantine_numbers.intersection(narrowed_row_ids))
    )
    all_input_rows_accounted_for_flag = int(
        tier_1_row_count + tier_2_row_count + tier_3_row_count + rejected_row_count == input_overlay_rows
    )
    no_order_recommendations_generated_flag = int(
        _to_numeric(
            overlay_rows_frame.get(
                "generated_order_recommendation_flag",
                pd.Series(0, index=overlay_rows_frame.index, dtype="object"),
            )
        )
        .fillna(0.0)
        .eq(0.0)
        .all()
    )
    inspection_overlay_row_count = _to_int(
        inspection_summary_metrics.get("OVERLAY_ROW_COUNT", 0)
    )
    broadness_overlay_row_count = _to_int(
        inspection_broadness_metrics.get("OVERLAY_ROW_COUNT", 0)
    )
    input_overlay_row_count_matches_flag = int(
        input_overlay_rows == EXPECTED_INPUT_OVERLAY_ROW_COUNT
        and input_overlay_rows == inspection_overlay_row_count
        and input_overlay_rows == broadness_overlay_row_count
    )
    quarantine_row_count_matches_expected_flag = int(
        quarantine_row_count == EXPECTED_QUARANTINE_ROW_COUNT
    )
    category_retention_rejection_calculated_flag = int(
        not by_category_frame.empty or input_overlay_rows == 0
    )
    narrowing_ratio_calculated_flag = int(input_overlay_rows > 0)
    tier_1_share_pct = round(tier_1_row_count / input_overlay_rows * 100.0, 2) if input_overlay_rows else 0.0
    tier_1_surface_controlled_flag = int(
        tier_1_row_count <= TIER_1_CONTROLLED_ROW_LIMIT
        and tier_1_share_pct <= TIER_1_CONTROLLED_SHARE_LIMIT_PCT
    )

    if production_guardrail_status != "PASS" or stage12_guardrail_status != "PASS":
        narrowing_status = CONTROLLED_OVERLAY_NARROWING_BLOCKED_GUARDRAIL_FAILURE
    elif not no_order_recommendations_generated_flag or not inspection_ready_flag:
        narrowing_status = CONTROLLED_OVERLAY_NARROWING_BLOCKED_ORDER_RECOMMENDATION_RISK
    elif tier_1_surface_controlled_flag and quarantine_row_count > 0:
        narrowing_status = CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE
    elif tier_1_surface_controlled_flag:
        narrowing_status = CONTROLLED_OVERLAY_NARROWING_READY
    else:
        narrowing_status = CONTROLLED_OVERLAY_NARROWING_REQUIRES_REVIEW

    action_layer_reconstruction_can_be_authored_next = int(
        narrowing_status
        in {
            CONTROLLED_OVERLAY_NARROWING_READY,
            CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE,
        }
    )
    expected_action_layer_flag = int(
        production_guardrail_status == "PASS"
        and stage12_guardrail_status == "PASS"
        and no_order_recommendations_generated_flag
        and inspection_ready_flag
        and tier_1_surface_controlled_flag
    )

    if action_layer_reconstruction_can_be_authored_next:
        recommendation = (
            "Tier 1 is controlled enough for later action-layer review reconstruction authoring. Keep Tier 2 and Tier 3 review-only, and keep quarantine row 48 separate."
        )
    elif narrowing_status == CONTROLLED_OVERLAY_NARROWING_REQUIRES_REVIEW:
        recommendation = (
            "Do not author action-layer review reconstruction yet. Review Tier 2 and the rejected noisy categories first, then tighten Tier 1 further if the narrowed surface is still broad."
        )
    else:
        recommendation = (
            "Do not author action-layer review reconstruction yet. Repair the blocked guardrail or order-recommendation risk before any downstream review authoring."
        )

    validation_rows = [
        _validation_row(
            "INPUT_OVERLAY_ROW_COUNT_MATCHES_EXPECTATION",
            "PASS" if input_overlay_row_count_matches_flag else "FAIL",
            input_overlay_row_count_matches_flag,
            (
                f"input_overlay_rows={input_overlay_rows}, expected={EXPECTED_INPUT_OVERLAY_ROW_COUNT}, "
                f"inspection_summary={inspection_overlay_row_count}, broadness_review={broadness_overlay_row_count}"
            ),
        ),
        _validation_row(
            "QUARANTINE_ROW_COUNT_MATCHES_EXPECTATION",
            "PASS" if quarantine_row_count_matches_expected_flag else "FAIL",
            quarantine_row_count_matches_expected_flag,
            f"quarantine_rows={quarantine_row_count}, expected={EXPECTED_QUARANTINE_ROW_COUNT}",
        ),
        _validation_row(
            "NO_QUARANTINE_ROWS_INCLUDED_IN_NARROWED_ROWS",
            "PASS" if no_quarantine_rows_included_flag else "FAIL",
            no_quarantine_rows_included_flag,
            "Quarantine row 48 remains excluded from the narrowed rows.",
        ),
        _validation_row(
            "ALL_INPUT_ROWS_ACCOUNTED_FOR",
            "PASS" if all_input_rows_accounted_for_flag else "FAIL",
            all_input_rows_accounted_for_flag,
            (
                f"tier_1={tier_1_row_count}, tier_2={tier_2_row_count}, tier_3={tier_3_row_count}, "
                f"rejected={rejected_row_count}, input_overlay_rows={input_overlay_rows}"
            ),
        ),
        _validation_row(
            "NO_ORDER_RECOMMENDATIONS_GENERATED",
            "PASS" if no_order_recommendations_generated_flag else "FAIL",
            no_order_recommendations_generated_flag,
            "Narrowing planner remains diagnostics-only and does not generate order recommendations.",
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
            "TIER_1_SURFACE_CONTROLLED",
            "PASS" if tier_1_surface_controlled_flag else "FAIL",
            tier_1_surface_controlled_flag,
            (
                f"tier_1_row_count={tier_1_row_count}, tier_1_share_pct={tier_1_share_pct}, "
                f"row_limit={TIER_1_CONTROLLED_ROW_LIMIT}, share_limit_pct={TIER_1_CONTROLLED_SHARE_LIMIT_PCT}"
            ),
        ),
        _validation_row(
            "NARROWING_RATIO_CALCULATED",
            "PASS" if narrowing_ratio_calculated_flag else "FAIL",
            narrowing_ratio_calculated_flag,
            f"narrowing_ratio={narrowing_ratio}",
        ),
        _validation_row(
            "CATEGORY_RETENTION_REJECTION_CALCULATED",
            "PASS" if category_retention_rejection_calculated_flag else "FAIL",
            category_retention_rejection_calculated_flag,
            f"category_rows={len(by_category_frame.index)}",
        ),
        _validation_row(
            "ACTION_LAYER_RECONSTRUCTION_BLOCKED_UNLESS_TIER_1_CONTROLLED",
            "PASS" if action_layer_reconstruction_can_be_authored_next == expected_action_layer_flag else "FAIL",
            int(action_layer_reconstruction_can_be_authored_next == expected_action_layer_flag),
            (
                f"authored_next={action_layer_reconstruction_can_be_authored_next}, "
                f"expected_next={expected_action_layer_flag}, tier_1_surface_controlled={tier_1_surface_controlled_flag}"
            ),
        ),
    ]
    validation_frame = pd.DataFrame(validation_rows, columns=VALIDATION_COLUMNS)

    summary_rows = [
        _summary_row(
            "SELECTED_PROMOTION",
            selection.promotion_key,
            "Promotion selected for the diagnostics-only overlay narrowing planner.",
        ),
        _summary_row(
            "NARROWING_STATUS",
            narrowing_status,
            "Overall diagnostics-only overlay narrowing planner status.",
        ),
        _summary_row(
            "INPUT_OVERLAY_ROWS",
            input_overlay_rows,
            "Input controlled overlay reconstruction row count.",
        ),
        _summary_row(
            "REVIEW_ROW_COUNT",
            review_row_count,
            "Controlled governed rebuild review row count.",
        ),
        _summary_row(
            "TIER_1_ROW_COUNT",
            tier_1_row_count,
            "Tier 1 action-layer review candidate row count.",
        ),
        _summary_row(
            "TIER_2_ROW_COUNT",
            tier_2_row_count,
            "Tier 2 operator review row count.",
        ),
        _summary_row(
            "TIER_3_ROW_COUNT",
            tier_3_row_count,
            "Tier 3 diagnostics-only row count.",
        ),
        _summary_row(
            "REJECTED_ROW_COUNT",
            rejected_row_count,
            "Rejected noisy broad trigger row count.",
        ),
        _summary_row(
            "NARROWING_RATIO",
            narrowing_ratio,
            "Tier 1 row count divided by input overlay rows.",
        ),
        _summary_row(
            "STRONGEST_RETAINED_CATEGORY",
            strongest_retained_category,
            "Strongest retained category after narrowing.",
        ),
        _summary_row(
            "NOISIEST_REJECTED_CATEGORY",
            noisiest_rejected_category,
            "Noisiest category among rejected rows.",
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
            "ACTION_LAYER_RECONSTRUCTION_CAN_BE_AUTHORED_NEXT",
            action_layer_reconstruction_can_be_authored_next,
            "Whether action-layer review reconstruction can be authored next from this narrowed surface.",
        ),
    ]
    summary_frame = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)

    memo_markdown = "\n".join(
        [
            "# Controlled Overlay Narrowing Plan",
            "",
            "This is a diagnostics-only narrowing planner over the controlled overlay reconstruction.",
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
            "",
            f"Selected promotion: {selection.promotion_key}",
            f"Narrowing status: {narrowing_status}",
            f"Input overlay rows: {input_overlay_rows}",
            f"Tier 1 row count: {tier_1_row_count}",
            f"Tier 2 row count: {tier_2_row_count}",
            f"Tier 3 row count: {tier_3_row_count}",
            f"Rejected row count: {rejected_row_count}",
            f"Narrowing ratio: {narrowing_ratio}",
            f"Strongest retained category: {strongest_retained_category}",
            f"Noisiest rejected category: {noisiest_rejected_category}",
            f"Quarantine row count: {quarantine_row_count}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Whether action-layer reconstruction can be authored next: {action_layer_reconstruction_can_be_authored_next}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()

    return PromotionsMaterializedSourceControlledOverlayNarrowingPlanResult(
        selected_promotion=selection,
        narrowing_status=narrowing_status,
        input_overlay_rows=input_overlay_rows,
        tier_1_row_count=tier_1_row_count,
        tier_2_row_count=tier_2_row_count,
        tier_3_row_count=tier_3_row_count,
        rejected_row_count=rejected_row_count,
        narrowing_ratio=narrowing_ratio,
        strongest_retained_category=strongest_retained_category,
        noisiest_rejected_category=noisiest_rejected_category,
        quarantine_row_count=quarantine_row_count,
        production_guardrail_status=production_guardrail_status,
        stage12_guardrail_status=stage12_guardrail_status,
        action_layer_reconstruction_can_be_authored_next=action_layer_reconstruction_can_be_authored_next,
        plan_rows_frame=plan_rows_frame,
        by_category_frame=by_category_frame,
        tiers_frame=tiers_frame,
        rejected_rows_frame=rejected_rows_frame,
        summary_frame=summary_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
        recommendation=recommendation,
    )


def write_promotions_materialized_source_controlled_overlay_narrowing_plan(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceControlledOverlayNarrowingPlanArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = (
        Path(output_root)
        if output_root is not None
        else packet_root_path / OUTPUT_FOLDER_NAME
    )
    result = build_promotions_materialized_source_controlled_overlay_narrowing_plan(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    plan_rows_csv_path = output_root_path / PLAN_ROWS_FILE_NAME
    by_category_csv_path = output_root_path / PLAN_BY_CATEGORY_FILE_NAME
    tiers_csv_path = output_root_path / PLAN_TIERS_FILE_NAME
    rejected_rows_csv_path = output_root_path / PLAN_REJECTED_ROWS_FILE_NAME
    summary_csv_path = output_root_path / PLAN_SUMMARY_FILE_NAME
    validation_csv_path = output_root_path / PLAN_VALIDATION_FILE_NAME
    memo_md_path = output_root_path / PLAN_MEMO_FILE_NAME

    result.plan_rows_frame.to_csv(plan_rows_csv_path, index=False)
    result.by_category_frame.to_csv(by_category_csv_path, index=False)
    result.tiers_frame.to_csv(tiers_csv_path, index=False)
    result.rejected_rows_frame.to_csv(rejected_rows_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceControlledOverlayNarrowingPlanArtifacts(
        output_root=str(output_root_path),
        plan_rows_csv_path=str(plan_rows_csv_path),
        by_category_csv_path=str(by_category_csv_path),
        tiers_csv_path=str(tiers_csv_path),
        rejected_rows_csv_path=str(rejected_rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        validation_csv_path=str(validation_csv_path),
        memo_md_path=str(memo_md_path),
        selected_promotion=result.selected_promotion.promotion_key,
        narrowing_status=result.narrowing_status,
        input_overlay_rows=result.input_overlay_rows,
        tier_1_row_count=result.tier_1_row_count,
        tier_2_row_count=result.tier_2_row_count,
        tier_3_row_count=result.tier_3_row_count,
        rejected_row_count=result.rejected_row_count,
        narrowing_ratio=result.narrowing_ratio,
        strongest_retained_category=result.strongest_retained_category,
        noisiest_rejected_category=result.noisiest_rejected_category,
        quarantine_row_count=result.quarantine_row_count,
        production_guardrail_status=result.production_guardrail_status,
        stage12_guardrail_status=result.stage12_guardrail_status,
        action_layer_reconstruction_can_be_authored_next=result.action_layer_reconstruction_can_be_authored_next,
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only controlled overlay narrowing planner."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_controlled_overlay_narrowing_plan(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    print("selected_promotion", artifacts.selected_promotion)
    print("narrowing_status", artifacts.narrowing_status)
    print("input_overlay_rows", artifacts.input_overlay_rows)
    print("tier_1_row_count", artifacts.tier_1_row_count)
    print("tier_2_row_count", artifacts.tier_2_row_count)
    print("tier_3_row_count", artifacts.tier_3_row_count)
    print("rejected_row_count", artifacts.rejected_row_count)
    print("narrowing_ratio", artifacts.narrowing_ratio)
    print("strongest_retained_category", artifacts.strongest_retained_category)
    print("noisiest_rejected_category", artifacts.noisiest_rejected_category)
    print("quarantine_row_count", artifacts.quarantine_row_count)
    print("production_guardrail_status", artifacts.production_guardrail_status)
    print("stage12_guardrail_status", artifacts.stage12_guardrail_status)
    print(
        "action_layer_reconstruction_can_be_authored_next",
        artifacts.action_layer_reconstruction_can_be_authored_next,
    )
    print("recommendation", artifacts.recommendation)
    print("controlled_overlay_narrowing_plan_rows", artifacts.plan_rows_csv_path)
    print("controlled_overlay_narrowing_plan_by_category", artifacts.by_category_csv_path)
    print("controlled_overlay_narrowing_plan_tiers", artifacts.tiers_csv_path)
    print("controlled_overlay_narrowing_plan_rejected_rows", artifacts.rejected_rows_csv_path)
    print("controlled_overlay_narrowing_plan_summary", artifacts.summary_csv_path)
    print("controlled_overlay_narrowing_plan_validation", artifacts.validation_csv_path)
    print("controlled_overlay_narrowing_plan_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())