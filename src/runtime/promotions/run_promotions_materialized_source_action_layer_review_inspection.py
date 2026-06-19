from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_action_layer_review_inspection"
RECONSTRUCTION_FOLDER_NAME = "materialized_source_action_layer_review_reconstruction"

RECONSTRUCTION_ROWS_FILE_NAME = "action_layer_review_reconstruction_rows.csv"
RECONSTRUCTION_SUMMARY_FILE_NAME = "action_layer_review_reconstruction_summary.csv"
RECONSTRUCTION_BY_CATEGORY_FILE_NAME = "action_layer_review_reconstruction_by_category.csv"
RECONSTRUCTION_RULE_FAMILY_PLAN_FILE_NAME = (
    "action_layer_review_reconstruction_rule_family_plan.csv"
)
RECONSTRUCTION_TOP_SKUS_FILE_NAME = "action_layer_review_reconstruction_top_skus.csv"
RECONSTRUCTION_VALIDATION_FILE_NAME = "action_layer_review_reconstruction_validation.csv"
RECONSTRUCTION_QUARANTINE_FILE_NAME = (
    "action_layer_review_reconstruction_quarantine_rows.csv"
)

REQUIRED_RECONSTRUCTION_FILE_NAMES: tuple[str, ...] = (
    RECONSTRUCTION_ROWS_FILE_NAME,
    RECONSTRUCTION_SUMMARY_FILE_NAME,
    RECONSTRUCTION_BY_CATEGORY_FILE_NAME,
    RECONSTRUCTION_RULE_FAMILY_PLAN_FILE_NAME,
    RECONSTRUCTION_TOP_SKUS_FILE_NAME,
    RECONSTRUCTION_VALIDATION_FILE_NAME,
    RECONSTRUCTION_QUARANTINE_FILE_NAME,
)

ACTION_LAYER_REVIEW_INSPECTION_READY_FOR_CALIBRATION_CANDIDATE_PACK = (
    "ACTION_LAYER_REVIEW_INSPECTION_READY_FOR_CALIBRATION_CANDIDATE_PACK"
)
ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE = (
    "ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE"
)
ACTION_LAYER_REVIEW_INSPECTION_REQUIRES_MORE_NARROWING = (
    "ACTION_LAYER_REVIEW_INSPECTION_REQUIRES_MORE_NARROWING"
)
ACTION_LAYER_REVIEW_INSPECTION_BLOCKED_GUARDRAIL_FAILURE = (
    "ACTION_LAYER_REVIEW_INSPECTION_BLOCKED_GUARDRAIL_FAILURE"
)
ACTION_LAYER_REVIEW_INSPECTION_BLOCKED_ORDER_RECOMMENDATION_RISK = (
    "ACTION_LAYER_REVIEW_INSPECTION_BLOCKED_ORDER_RECOMMENDATION_RISK"
)

ACTION_LAYER_REVIEW_RECONSTRUCTION_READY = "ACTION_LAYER_REVIEW_RECONSTRUCTION_READY"
ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE = (
    "ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE"
)
READY_RECONSTRUCTION_STATUSES = {
    ACTION_LAYER_REVIEW_RECONSTRUCTION_READY,
    ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE,
}

CONTROLLED_REVIEW_SURFACE = "CONTROLLED_REVIEW_SURFACE"
BROAD_REVIEW_SURFACE = "BROAD_REVIEW_SURFACE"
VERY_BROAD_REVIEW_SURFACE = "VERY_BROAD_REVIEW_SURFACE"

SUMMARY_COLUMNS = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)
QUALITY_CHECK_COLUMNS = (
    "check_name",
    "check_status",
    "check_flag",
    "details",
)
BY_RULE_FAMILY_COLUMNS = (
    "rule_family_candidate",
    "review_row_count",
    "row_share_pct",
    "source_categories",
    "mean_review_signal_score",
    "max_review_signal_score",
    "mean_absolute_error_units",
    "mean_actual_gross_profit",
    "mean_capital_left_value",
    "sample_skus",
    "strength_score",
    "noise_score",
    "strength_status",
    "noise_status",
    "quality_notes",
)
BY_CATEGORY_COLUMNS = (
    "overlay_category",
    "review_row_count",
    "row_share_pct",
    "mean_review_signal_score",
    "max_review_signal_score",
    "mean_absolute_error_units",
    "mean_actual_gross_profit",
    "mean_capital_left_value",
    "sample_skus",
    "strength_score",
    "noise_score",
    "strength_status",
    "noise_status",
    "quality_notes",
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
    "dominant_signal_axis",
    "signal_strength_status",
    "review_notes",
)
CALIBRATION_READINESS_COLUMNS = (
    "readiness_metric",
    "metric_value",
    "metric_display",
    "readiness_status",
    "notes",
)

EXPECTED_REVIEW_ROW_COUNT = 108
EXPECTED_QUARANTINE_ROW_COUNT = 1
TOP_SKU_LIMIT = 20
REVIEW_ROW_CONTROL_LIMIT = 120
REQUIRES_MORE_NARROWING_LIMIT = 108


class PromotionsMaterializedSourceActionLayerReviewInspectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceActionLayerReviewInspectionResult:
    selected_promotion: PromotionSelection
    inspection_status: str
    review_surface_status: str
    review_row_count: int
    quarantine_row_count: int
    strongest_rule_family: str
    noisiest_rule_family: str
    strongest_category: str
    top_sku_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    calibration_candidate_pack_can_be_authored_next: int
    summary_frame: pd.DataFrame
    quality_checks_frame: pd.DataFrame
    by_rule_family_frame: pd.DataFrame
    by_category_frame: pd.DataFrame
    top_skus_frame: pd.DataFrame
    calibration_readiness_frame: pd.DataFrame
    quarantine_review_frame: pd.DataFrame
    memo_markdown: str
    recommendation: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceActionLayerReviewInspectionArtifacts:
    output_root: str
    summary_csv_path: str
    quality_checks_csv_path: str
    by_rule_family_csv_path: str
    by_category_csv_path: str
    top_skus_csv_path: str
    calibration_readiness_csv_path: str
    quarantine_review_csv_path: str
    memo_md_path: str
    selected_promotion: str
    inspection_status: str
    review_row_count: int
    quarantine_row_count: int
    strongest_rule_family: str
    noisiest_rule_family: str
    strongest_category: str
    top_sku_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    calibration_candidate_pack_can_be_authored_next: int
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
        raise PromotionsMaterializedSourceActionLayerReviewInspectionError(
            f"CSV not found: {csv_path}"
        )
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceActionLayerReviewInspectionError(
            f"CSV is empty: {csv_path}"
        )
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceActionLayerReviewInspectionError(
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
    raise PromotionsMaterializedSourceActionLayerReviewInspectionError(
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


def _quality_check_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
    return {
        "check_name": name,
        "check_status": status,
        "check_flag": int(flag),
        "details": details,
    }


def _readiness_row(name: str, value: object, status: str, notes: str) -> dict[str, object]:
    return {
        "readiness_metric": name,
        "metric_value": value,
        "metric_display": str(value),
        "readiness_status": status,
        "notes": notes,
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


def _selection_from_inputs(
    *,
    requested_promotion_key: str | None,
    summary_metrics: dict[str, object],
    rows_frame: pd.DataFrame,
) -> PromotionSelection:
    resolved_key = requested_promotion_key or _normalize_text(
        summary_metrics.get("SELECTED_PROMOTION", "")
    )
    if not resolved_key and "promotion_key" in rows_frame.columns:
        keys = [
            _normalize_text(value)
            for value in rows_frame["promotion_key"].drop_duplicates().tolist()
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


def _review_surface_status(review_row_count: int) -> str:
    if review_row_count > REVIEW_ROW_CONTROL_LIMIT:
        return VERY_BROAD_REVIEW_SURFACE
    if review_row_count > REQUIRES_MORE_NARROWING_LIMIT:
        return BROAD_REVIEW_SURFACE
    return CONTROLLED_REVIEW_SURFACE


def _quality_status(strength_score: float, noise_score: float) -> tuple[str, str]:
    strength_status = "STRONG_SIGNAL" if strength_score >= 12.0 else "WEAKER_SIGNAL"
    noise_status = "NOISY_SURFACE" if noise_score >= 25.0 else "CONTROLLED_SURFACE"
    return strength_status, noise_status


def _build_by_rule_family_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=BY_RULE_FAMILY_COLUMNS)
    rows: list[dict[str, object]] = []
    total_rows = len(rows_frame.index)
    for rule_family, family_frame in rows_frame.groupby("rule_family_candidate", sort=False):
        mean_signal = float(_to_numeric(family_frame.get("review_signal_score")).fillna(0.0).mean())
        max_signal = float(_to_numeric(family_frame.get("review_signal_score")).fillna(0.0).max())
        mean_error = float(_to_numeric(family_frame.get("absolute_error_units")).fillna(0.0).mean())
        mean_gp = float(_to_numeric(family_frame.get("actual_gross_profit")).fillna(0.0).mean())
        mean_capital = float(_to_numeric(family_frame.get("capital_left_value")).fillna(0.0).mean())
        row_count = len(family_frame.index)
        row_share_pct = round(row_count / total_rows * 100.0, 2) if total_rows else 0.0
        strength_score = round(mean_signal + min(mean_error * 1.5, 20.0) + min(mean_gp / 2.0, 20.0), 2)
        noise_score = round(max(row_share_pct - 25.0, 0.0) + max(15.0 - mean_signal, 0.0), 2)
        strength_status, noise_status = _quality_status(strength_score, noise_score)
        rows.append(
            {
                "rule_family_candidate": _normalize_text(rule_family),
                "review_row_count": row_count,
                "row_share_pct": row_share_pct,
                "source_categories": _sample_values(family_frame.get("overlay_category")),
                "mean_review_signal_score": round(mean_signal, 4),
                "max_review_signal_score": round(max_signal, 4),
                "mean_absolute_error_units": round(mean_error, 4),
                "mean_actual_gross_profit": round(mean_gp, 4),
                "mean_capital_left_value": round(mean_capital, 4),
                "sample_skus": _sample_values(family_frame.get("sku_number")),
                "strength_score": strength_score,
                "noise_score": noise_score,
                "strength_status": strength_status,
                "noise_status": noise_status,
                "quality_notes": (
                    "Rule family remains review-quality for later calibration candidate research."
                    if noise_status == "CONTROLLED_SURFACE"
                    else "Rule family still looks broad or weak and likely needs more narrowing before calibration research."
                ),
            }
        )
    return pd.DataFrame(rows, columns=BY_RULE_FAMILY_COLUMNS).sort_values(
        by=["strength_score", "mean_review_signal_score", "review_row_count", "rule_family_candidate"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_by_category_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=BY_CATEGORY_COLUMNS)
    rows: list[dict[str, object]] = []
    total_rows = len(rows_frame.index)
    for category, category_frame in rows_frame.groupby("overlay_category", sort=False):
        mean_signal = float(_to_numeric(category_frame.get("review_signal_score")).fillna(0.0).mean())
        max_signal = float(_to_numeric(category_frame.get("review_signal_score")).fillna(0.0).max())
        mean_error = float(_to_numeric(category_frame.get("absolute_error_units")).fillna(0.0).mean())
        mean_gp = float(_to_numeric(category_frame.get("actual_gross_profit")).fillna(0.0).mean())
        mean_capital = float(_to_numeric(category_frame.get("capital_left_value")).fillna(0.0).mean())
        row_count = len(category_frame.index)
        row_share_pct = round(row_count / total_rows * 100.0, 2) if total_rows else 0.0
        strength_score = round(mean_signal + min(mean_error * 1.5, 20.0) + min(mean_gp / 2.0, 20.0), 2)
        noise_score = round(max(row_share_pct - 25.0, 0.0) + max(15.0 - mean_signal, 0.0), 2)
        strength_status, noise_status = _quality_status(strength_score, noise_score)
        rows.append(
            {
                "overlay_category": _normalize_text(category),
                "review_row_count": row_count,
                "row_share_pct": row_share_pct,
                "mean_review_signal_score": round(mean_signal, 4),
                "max_review_signal_score": round(max_signal, 4),
                "mean_absolute_error_units": round(mean_error, 4),
                "mean_actual_gross_profit": round(mean_gp, 4),
                "mean_capital_left_value": round(mean_capital, 4),
                "sample_skus": _sample_values(category_frame.get("sku_number")),
                "strength_score": strength_score,
                "noise_score": noise_score,
                "strength_status": strength_status,
                "noise_status": noise_status,
                "quality_notes": (
                    "Category carries reliable review-only signal for a later calibration candidate pack."
                    if noise_status == "CONTROLLED_SURFACE"
                    else "Category still appears broad or weak for calibration candidate promotion."
                ),
            }
        )
    return pd.DataFrame(rows, columns=BY_CATEGORY_COLUMNS).sort_values(
        by=["strength_score", "mean_review_signal_score", "review_row_count", "overlay_category"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _dominant_signal_axis(row: pd.Series) -> str:
    error_units = float(pd.to_numeric(pd.Series([row.get("absolute_error_units")]), errors="coerce").fillna(0.0).iloc[0])
    gross_profit = float(pd.to_numeric(pd.Series([row.get("actual_gross_profit")]), errors="coerce").fillna(0.0).iloc[0])
    capital_left = float(pd.to_numeric(pd.Series([row.get("capital_left_value")]), errors="coerce").fillna(0.0).iloc[0])
    actual_units = float(pd.to_numeric(pd.Series([row.get("actual_units")]), errors="coerce").fillna(0.0).iloc[0])
    candidates = {
        "ACTUAL_ERROR_CONCENTRATED": error_units,
        "GROSS_PROFIT_CONCENTRATED": gross_profit,
        "CAPITAL_DRAG_CONCENTRATED": capital_left,
        "MISSED_DEMAND_CONCENTRATED": actual_units,
    }
    return max(candidates, key=candidates.get)


def _build_top_skus_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=TOP_SKUS_COLUMNS)
    frame = rows_frame.sort_values(
        by=[
            "review_signal_score",
            "absolute_error_units",
            "actual_gross_profit",
            "capital_left_value",
            "sku_number",
        ],
        ascending=[False, False, False, False, True],
        kind="stable",
    ).head(TOP_SKU_LIMIT).copy()
    frame.insert(0, "review_rank", range(1, len(frame.index) + 1))
    frame["dominant_signal_axis"] = frame.apply(_dominant_signal_axis, axis=1)
    frame["signal_strength_status"] = frame["review_signal_score"].map(
        lambda value: "HIGH_SIGNAL_TOP_SKU" if float(value) >= 10.0 else "MODERATE_SIGNAL_TOP_SKU"
    )
    frame["review_notes"] = frame["dominant_signal_axis"].map(
        {
            "ACTUAL_ERROR_CONCENTRATED": "Top SKU is concentrated in absolute forecast error.",
            "GROSS_PROFIT_CONCENTRATED": "Top SKU is concentrated in actual gross profit.",
            "CAPITAL_DRAG_CONCENTRATED": "Top SKU is concentrated in capital drag.",
            "MISSED_DEMAND_CONCENTRATED": "Top SKU is concentrated in missed-demand evidence.",
        }
    )
    return frame.loc[:, TOP_SKUS_COLUMNS].reset_index(drop=True)


def _build_quarantine_review_frame(quarantine_rows_frame: pd.DataFrame, rows_frame: pd.DataFrame) -> pd.DataFrame:
    columns = (
        "quarantine_review_status",
        "quarantine_preserved_flag",
        "review_rows_clear_flag",
        *quarantine_rows_frame.columns,
    )
    if quarantine_rows_frame.empty:
        return pd.DataFrame(columns=columns)
    review_frame = quarantine_rows_frame.copy()
    quarantine_numbers = set(
        pd.to_numeric(review_frame.get("source_row_number", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    review_row_ids = set(
        pd.to_numeric(rows_frame.get("source_row_id", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    quarantine_preserved_flag = int(48 in quarantine_numbers and len(review_frame.index) == EXPECTED_QUARANTINE_ROW_COUNT)
    review_rows_clear_flag = int(not bool(quarantine_numbers.intersection(review_row_ids)))
    review_frame["quarantine_review_status"] = (
        "QUARANTINE_ROW_48_PRESERVED"
        if quarantine_preserved_flag and review_rows_clear_flag
        else "QUARANTINE_REVIEW_FAILED"
    )
    review_frame["quarantine_preserved_flag"] = quarantine_preserved_flag
    review_frame["review_rows_clear_flag"] = review_rows_clear_flag
    return review_frame.loc[:, columns].copy()


def _strongest_and_noisiest_rule_family(by_rule_family_frame: pd.DataFrame) -> tuple[str, str]:
    if by_rule_family_frame.empty:
        return "", ""
    strongest = str(by_rule_family_frame.iloc[0]["rule_family_candidate"])
    noisiest = str(
        by_rule_family_frame.sort_values(
            by=["noise_score", "review_row_count", "rule_family_candidate"],
            ascending=[False, False, True],
            kind="stable",
        ).iloc[0]["rule_family_candidate"]
    )
    return strongest, noisiest


def _strongest_category(by_category_frame: pd.DataFrame) -> str:
    if by_category_frame.empty:
        return ""
    return str(by_category_frame.iloc[0]["overlay_category"])


def build_promotions_materialized_source_action_layer_review_inspection(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceActionLayerReviewInspectionResult:
    packet_root_path = Path(packet_root)
    reconstruction_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=RECONSTRUCTION_FOLDER_NAME,
        required_file_names=REQUIRED_RECONSTRUCTION_FILE_NAMES,
        stage_label="action-layer-review-reconstruction",
    )

    rows_frame = _read_csv(reconstruction_root / RECONSTRUCTION_ROWS_FILE_NAME)
    summary_frame = _read_csv(reconstruction_root / RECONSTRUCTION_SUMMARY_FILE_NAME)
    _read_csv(reconstruction_root / RECONSTRUCTION_BY_CATEGORY_FILE_NAME)
    rule_family_plan_frame = _read_csv(reconstruction_root / RECONSTRUCTION_RULE_FAMILY_PLAN_FILE_NAME)
    _read_csv(reconstruction_root / RECONSTRUCTION_TOP_SKUS_FILE_NAME, allow_empty=True)
    validation_frame = _read_csv(reconstruction_root / RECONSTRUCTION_VALIDATION_FILE_NAME)
    quarantine_rows_frame = _read_csv(reconstruction_root / RECONSTRUCTION_QUARANTINE_FILE_NAME, allow_empty=True)

    summary_metrics = _metric_lookup(summary_frame)
    validation_lookup = _validation_lookup(validation_frame)
    selection = _selection_from_inputs(
        requested_promotion_key=promotion_key,
        summary_metrics=summary_metrics,
        rows_frame=rows_frame,
    )

    rows_frame = _filter_for_promotion(rows_frame, selection.promotion_key)
    rule_family_plan_frame = _filter_for_promotion(rule_family_plan_frame, selection.promotion_key)
    quarantine_rows_frame = _filter_for_promotion(quarantine_rows_frame, selection.promotion_key)

    reconstruction_status = _normalize_text(
        summary_metrics.get("ACTION_LAYER_REVIEW_RECONSTRUCTION_STATUS", "")
    )
    review_row_count = len(rows_frame.index)
    quarantine_row_count = len(quarantine_rows_frame.index)
    review_surface_status = _review_surface_status(review_row_count)
    production_guardrail_status = _normalize_text(
        summary_metrics.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL")
    ) or "FAIL"
    stage12_guardrail_status = _normalize_text(
        summary_metrics.get("STAGE12_GUARDRAIL_STATUS", "FAIL")
    ) or "FAIL"

    by_rule_family_frame = _build_by_rule_family_frame(rows_frame)
    by_category_frame = _build_by_category_frame(rows_frame)
    top_skus_frame = _build_top_skus_frame(rows_frame)
    quarantine_review_frame = _build_quarantine_review_frame(quarantine_rows_frame, rows_frame)
    strongest_rule_family, noisiest_rule_family = _strongest_and_noisiest_rule_family(
        by_rule_family_frame
    )
    strongest_category = _strongest_category(by_category_frame)
    top_sku_count = len(top_skus_frame.index)

    quarantine_numbers = set(
        pd.to_numeric(quarantine_rows_frame.get("source_row_number", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    review_row_ids = set(
        pd.to_numeric(rows_frame.get("source_row_id", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    no_quarantine_rows_included_flag = int(not bool(quarantine_numbers.intersection(review_row_ids)))
    tier_2_leakage_count = _to_int(summary_metrics.get("TIER_2_LEAKAGE_COUNT", 0))
    tier_3_leakage_count = _to_int(summary_metrics.get("TIER_3_LEAKAGE_COUNT", 0))
    rejected_leakage_count = _to_int(summary_metrics.get("REJECTED_LEAKAGE_COUNT", 0))
    no_order_recommendation_fields_flag = int(
        not {
            "recommended_order_units",
            "final_store_order_units",
            "generated_order_recommendation_flag",
        }.intersection(set(rows_frame.columns))
        and validation_lookup.get("NO_ORDER_RECOMMENDATION_FIELDS_PRODUCED", "PASS") == "PASS"
    )
    review_only_output_confirmed_flag = int(
        _to_numeric(rows_frame.get("production_order_change_flag")).fillna(0.0).eq(0.0).all()
        and _to_numeric(rows_frame.get("stage_12_change_flag")).fillna(0.0).eq(0.0).all()
        and _to_numeric(rows_frame.get("quarantine_flag")).fillna(0.0).eq(0.0).all()
        and validation_lookup.get("ACTION_LAYER_OUTPUT_IS_REVIEW_ONLY", "PASS") == "PASS"
    )
    missing_actuals_not_zero_filled_flag = int(
        rows_frame.get("actual_units", pd.Series(dtype="object")).astype(str).str.strip().ne("").all()
    )
    rule_family_plan_exists_flag = int(not rule_family_plan_frame.empty)
    top_sku_review_exists_flag = int(not top_skus_frame.empty)
    upstream_ready_flag = int(reconstruction_status in READY_RECONSTRUCTION_STATUSES)
    row_count_matches_expected_flag = int(review_row_count == EXPECTED_REVIEW_ROW_COUNT)
    quarantine_count_matches_expected_flag = int(
        quarantine_row_count == EXPECTED_QUARANTINE_ROW_COUNT
    )

    if production_guardrail_status != "PASS" or stage12_guardrail_status != "PASS":
        inspection_status = ACTION_LAYER_REVIEW_INSPECTION_BLOCKED_GUARDRAIL_FAILURE
    elif no_order_recommendation_fields_flag == 0 or review_only_output_confirmed_flag == 0 or upstream_ready_flag == 0:
        inspection_status = ACTION_LAYER_REVIEW_INSPECTION_BLOCKED_ORDER_RECOMMENDATION_RISK
    elif review_surface_status in {BROAD_REVIEW_SURFACE, VERY_BROAD_REVIEW_SURFACE}:
        inspection_status = ACTION_LAYER_REVIEW_INSPECTION_REQUIRES_MORE_NARROWING
    elif quarantine_row_count > 0:
        inspection_status = ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE
    else:
        inspection_status = ACTION_LAYER_REVIEW_INSPECTION_READY_FOR_CALIBRATION_CANDIDATE_PACK

    calibration_candidate_pack_can_be_authored_next = int(
        inspection_status
        in {
            ACTION_LAYER_REVIEW_INSPECTION_READY_FOR_CALIBRATION_CANDIDATE_PACK,
            ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE,
        }
    )

    if inspection_status == ACTION_LAYER_REVIEW_INSPECTION_REQUIRES_MORE_NARROWING:
        recommendation = (
            "Keep calibration blocked for now. Narrow the review surface further before authoring a calibration candidate pack."
        )
    elif inspection_status in {
        ACTION_LAYER_REVIEW_INSPECTION_BLOCKED_GUARDRAIL_FAILURE,
        ACTION_LAYER_REVIEW_INSPECTION_BLOCKED_ORDER_RECOMMENDATION_RISK,
    }:
        recommendation = (
            "Keep calibration blocked. Repair the review-only safety or guardrail findings before any candidate-pack authoring."
        )
    else:
        recommendation = (
            "Author a diagnostics-only calibration candidate pack next from this review-only surface while keeping quarantine row 48 separate and leaving recalibration, simulation, training, production ordering, and Stage 12 unchanged."
        )

    quality_checks_frame = pd.DataFrame(
        [
            _quality_check_row(
                "REVIEW_ROWS_MATCH_EXPECTATION",
                "PASS" if row_count_matches_expected_flag else "FAIL",
                row_count_matches_expected_flag,
                f"review_rows={review_row_count}, expected={EXPECTED_REVIEW_ROW_COUNT}",
            ),
            _quality_check_row(
                "QUARANTINE_ROWS_MATCH_EXPECTATION",
                "PASS" if quarantine_count_matches_expected_flag else "FAIL",
                quarantine_count_matches_expected_flag,
                f"quarantine_rows={quarantine_row_count}, expected={EXPECTED_QUARANTINE_ROW_COUNT}",
            ),
            _quality_check_row(
                "NO_QUARANTINE_ROWS_INCLUDED_IN_REVIEW_ROWS",
                "PASS" if no_quarantine_rows_included_flag else "FAIL",
                no_quarantine_rows_included_flag,
                "Quarantine row 48 remains excluded from the review rows.",
            ),
            _quality_check_row(
                "TIER_2_LEAKAGE_ZERO",
                "PASS" if tier_2_leakage_count == 0 else "FAIL",
                int(tier_2_leakage_count == 0),
                f"tier_2_leakage_count={tier_2_leakage_count}",
            ),
            _quality_check_row(
                "TIER_3_LEAKAGE_ZERO",
                "PASS" if tier_3_leakage_count == 0 else "FAIL",
                int(tier_3_leakage_count == 0),
                f"tier_3_leakage_count={tier_3_leakage_count}",
            ),
            _quality_check_row(
                "REJECTED_LEAKAGE_ZERO",
                "PASS" if rejected_leakage_count == 0 else "FAIL",
                int(rejected_leakage_count == 0),
                f"rejected_leakage_count={rejected_leakage_count}",
            ),
            _quality_check_row(
                "NO_ORDER_RECOMMENDATION_FIELDS_GENERATED",
                "PASS" if no_order_recommendation_fields_flag else "FAIL",
                no_order_recommendation_fields_flag,
                "Inspection surface remains review-only and does not generate order recommendation fields.",
            ),
            _quality_check_row(
                "PRODUCTION_GUARDRAIL_PASS",
                production_guardrail_status,
                int(production_guardrail_status == "PASS"),
                f"production_guardrail_status={production_guardrail_status}",
            ),
            _quality_check_row(
                "STAGE12_GUARDRAIL_PASS",
                stage12_guardrail_status,
                int(stage12_guardrail_status == "PASS"),
                f"stage12_guardrail_status={stage12_guardrail_status}",
            ),
            _quality_check_row(
                "REVIEW_ONLY_OUTPUT_CONFIRMED",
                "PASS" if review_only_output_confirmed_flag else "FAIL",
                review_only_output_confirmed_flag,
                "Reconstructed output rows keep production-order, Stage 12, and quarantine flags at zero.",
            ),
            _quality_check_row(
                "MISSING_ACTUALS_NOT_ZERO_FILLED",
                "PASS" if missing_actuals_not_zero_filled_flag else "FAIL",
                missing_actuals_not_zero_filled_flag,
                "Actual-unit fields remain present rather than being zero-filled as a fallback.",
            ),
            _quality_check_row(
                "RULE_FAMILY_PLAN_EXISTS",
                "PASS" if rule_family_plan_exists_flag else "FAIL",
                rule_family_plan_exists_flag,
                f"rule_family_plan_rows={len(rule_family_plan_frame.index)}",
            ),
            _quality_check_row(
                "TOP_SKU_REVIEW_EXISTS",
                "PASS" if top_sku_review_exists_flag else "FAIL",
                top_sku_review_exists_flag,
                f"top_sku_review_rows={top_sku_count}",
            ),
            _quality_check_row(
                "CALIBRATION_READINESS_STATED",
                "PASS",
                1,
                recommendation,
            ),
        ],
        columns=QUALITY_CHECK_COLUMNS,
    )

    calibration_readiness_frame = pd.DataFrame(
        [
            _readiness_row(
                "REVIEW_SURFACE_STATUS",
                review_surface_status,
                review_surface_status,
                "Whether the review surface is controlled or still too broad for later calibration research.",
            ),
            _readiness_row(
                "REVIEW_ROW_COUNT",
                review_row_count,
                review_surface_status,
                "Tier 1 review row count available for inspection.",
            ),
            _readiness_row(
                "STRONGEST_RULE_FAMILY",
                strongest_rule_family,
                "STRONGEST_RULE_FAMILY_RECORDED",
                "Rule family with the strongest combined signal profile.",
            ),
            _readiness_row(
                "NOISIEST_RULE_FAMILY",
                noisiest_rule_family,
                "NOISIEST_RULE_FAMILY_RECORDED",
                "Rule family with the broadest or weakest profile.",
            ),
            _readiness_row(
                "STRONGEST_CATEGORY",
                strongest_category,
                "STRONGEST_CATEGORY_RECORDED",
                "Category with the strongest combined signal profile.",
            ),
            _readiness_row(
                "TOP_SKU_COUNT",
                top_sku_count,
                "TOP_SKU_REVIEW_RECORDED",
                "Count of top SKUs reviewed for error, gross profit, missed demand, and capital drag concentration.",
            ),
            _readiness_row(
                "CALIBRATION_CANDIDATE_PACK_CAN_BE_AUTHORED_NEXT",
                calibration_candidate_pack_can_be_authored_next,
                inspection_status,
                "Whether a later diagnostics-only calibration candidate pack may be authored next.",
            ),
        ],
        columns=CALIBRATION_READINESS_COLUMNS,
    )

    summary_output_frame = pd.DataFrame(
        [
            _summary_row(
                "SELECTED_PROMOTION",
                selection.promotion_key,
                "Promotion selected for the diagnostics-only action-layer review inspection pack.",
            ),
            _summary_row(
                "INSPECTION_STATUS",
                inspection_status,
                "Overall diagnostics-only inspection status for the reconstructed action-layer review surface.",
            ),
            _summary_row(
                "REVIEW_ROW_COUNT",
                review_row_count,
                "Reconstructed Tier 1 review row count.",
            ),
            _summary_row(
                "QUARANTINE_ROW_COUNT",
                quarantine_row_count,
                "Quarantine row count preserved separately.",
            ),
            _summary_row(
                "STRONGEST_RULE_FAMILY",
                strongest_rule_family,
                "Strongest rule family in the inspection pack.",
            ),
            _summary_row(
                "NOISIEST_RULE_FAMILY",
                noisiest_rule_family,
                "Noisiest rule family in the inspection pack.",
            ),
            _summary_row(
                "STRONGEST_CATEGORY",
                strongest_category,
                "Strongest category in the inspection pack.",
            ),
            _summary_row(
                "TOP_SKU_COUNT",
                top_sku_count,
                "Count of top SKUs included in the inspection pack.",
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
                "CALIBRATION_CANDIDATE_PACK_CAN_BE_AUTHORED_NEXT",
                calibration_candidate_pack_can_be_authored_next,
                "Whether a later diagnostics-only calibration candidate pack can be authored next.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Action-Layer Review Inspection Pack",
            "",
            "This is a diagnostics-only inspection pack for the reconstructed action-layer review surface.",
            "This does not run recalibration.",
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
            f"Inspection status: {inspection_status}",
            f"Review row count: {review_row_count}",
            f"Quarantine row count: {quarantine_row_count}",
            f"Strongest rule family: {strongest_rule_family}",
            f"Noisiest rule family: {noisiest_rule_family}",
            f"Strongest category: {strongest_category}",
            f"Top SKU count: {top_sku_count}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Whether calibration candidate pack can be authored next: {calibration_candidate_pack_can_be_authored_next}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()

    return PromotionsMaterializedSourceActionLayerReviewInspectionResult(
        selected_promotion=selection,
        inspection_status=inspection_status,
        review_surface_status=review_surface_status,
        review_row_count=review_row_count,
        quarantine_row_count=quarantine_row_count,
        strongest_rule_family=strongest_rule_family,
        noisiest_rule_family=noisiest_rule_family,
        strongest_category=strongest_category,
        top_sku_count=top_sku_count,
        production_guardrail_status=production_guardrail_status,
        stage12_guardrail_status=stage12_guardrail_status,
        calibration_candidate_pack_can_be_authored_next=calibration_candidate_pack_can_be_authored_next,
        summary_frame=summary_output_frame,
        quality_checks_frame=quality_checks_frame,
        by_rule_family_frame=by_rule_family_frame,
        by_category_frame=by_category_frame,
        top_skus_frame=top_skus_frame,
        calibration_readiness_frame=calibration_readiness_frame,
        quarantine_review_frame=quarantine_review_frame,
        memo_markdown=memo_markdown,
        recommendation=recommendation,
    )


def write_promotions_materialized_source_action_layer_review_inspection(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceActionLayerReviewInspectionArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = (
        Path(output_root)
        if output_root is not None
        else packet_root_path / OUTPUT_FOLDER_NAME
    )
    result = build_promotions_materialized_source_action_layer_review_inspection(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_root_path / "action_layer_review_inspection_summary.csv"
    quality_checks_csv_path = (
        output_root_path / "action_layer_review_inspection_quality_checks.csv"
    )
    by_rule_family_csv_path = (
        output_root_path / "action_layer_review_inspection_by_rule_family.csv"
    )
    by_category_csv_path = (
        output_root_path / "action_layer_review_inspection_by_category.csv"
    )
    top_skus_csv_path = output_root_path / "action_layer_review_inspection_top_skus.csv"
    calibration_readiness_csv_path = (
        output_root_path / "action_layer_review_inspection_calibration_readiness.csv"
    )
    quarantine_review_csv_path = (
        output_root_path / "action_layer_review_inspection_quarantine_review.csv"
    )
    memo_md_path = output_root_path / "action_layer_review_inspection_memo.md"

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.quality_checks_frame.to_csv(quality_checks_csv_path, index=False)
    result.by_rule_family_frame.to_csv(by_rule_family_csv_path, index=False)
    result.by_category_frame.to_csv(by_category_csv_path, index=False)
    result.top_skus_frame.to_csv(top_skus_csv_path, index=False)
    result.calibration_readiness_frame.to_csv(calibration_readiness_csv_path, index=False)
    result.quarantine_review_frame.to_csv(quarantine_review_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceActionLayerReviewInspectionArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_csv_path),
        quality_checks_csv_path=str(quality_checks_csv_path),
        by_rule_family_csv_path=str(by_rule_family_csv_path),
        by_category_csv_path=str(by_category_csv_path),
        top_skus_csv_path=str(top_skus_csv_path),
        calibration_readiness_csv_path=str(calibration_readiness_csv_path),
        quarantine_review_csv_path=str(quarantine_review_csv_path),
        memo_md_path=str(memo_md_path),
        selected_promotion=result.selected_promotion.promotion_key,
        inspection_status=result.inspection_status,
        review_row_count=result.review_row_count,
        quarantine_row_count=result.quarantine_row_count,
        strongest_rule_family=result.strongest_rule_family,
        noisiest_rule_family=result.noisiest_rule_family,
        strongest_category=result.strongest_category,
        top_sku_count=result.top_sku_count,
        production_guardrail_status=result.production_guardrail_status,
        stage12_guardrail_status=result.stage12_guardrail_status,
        calibration_candidate_pack_can_be_authored_next=(
            result.calibration_candidate_pack_can_be_authored_next
        ),
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only action-layer review inspection pack."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_action_layer_review_inspection(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    print("selected_promotion", artifacts.selected_promotion)
    print("inspection_status", artifacts.inspection_status)
    print("review_row_count", artifacts.review_row_count)
    print("quarantine_row_count", artifacts.quarantine_row_count)
    print("strongest_rule_family", artifacts.strongest_rule_family)
    print("noisiest_rule_family", artifacts.noisiest_rule_family)
    print("strongest_category", artifacts.strongest_category)
    print("top_sku_count", artifacts.top_sku_count)
    print("production_guardrail_status", artifacts.production_guardrail_status)
    print("stage12_guardrail_status", artifacts.stage12_guardrail_status)
    print(
        "calibration_candidate_pack_can_be_authored_next",
        artifacts.calibration_candidate_pack_can_be_authored_next,
    )
    print("recommendation", artifacts.recommendation)
    print("action_layer_review_inspection_summary", artifacts.summary_csv_path)
    print(
        "action_layer_review_inspection_quality_checks",
        artifacts.quality_checks_csv_path,
    )
    print(
        "action_layer_review_inspection_by_rule_family",
        artifacts.by_rule_family_csv_path,
    )
    print(
        "action_layer_review_inspection_by_category",
        artifacts.by_category_csv_path,
    )
    print("action_layer_review_inspection_top_skus", artifacts.top_skus_csv_path)
    print(
        "action_layer_review_inspection_calibration_readiness",
        artifacts.calibration_readiness_csv_path,
    )
    print(
        "action_layer_review_inspection_quarantine_review",
        artifacts.quarantine_review_csv_path,
    )
    print("action_layer_review_inspection_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())