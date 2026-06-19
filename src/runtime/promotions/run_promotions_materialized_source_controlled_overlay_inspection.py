from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd

OUTPUT_FOLDER_NAME = "materialized_source_controlled_overlay_inspection"
OVERLAY_RECONSTRUCTION_FOLDER_NAME = "materialized_source_controlled_overlay_reconstruction"
CONTROLLED_REBUILD_FOLDER_NAME = "materialized_source_controlled_governed_rebuild"

OVERLAY_ROWS_FILE_NAME = "controlled_overlay_reconstruction_rows.csv"
OVERLAY_SUMMARY_FILE_NAME = "controlled_overlay_reconstruction_summary.csv"
OVERLAY_BY_CATEGORY_FILE_NAME = "controlled_overlay_reconstruction_by_category.csv"
OVERLAY_TOP_SKUS_FILE_NAME = "controlled_overlay_reconstruction_top_skus.csv"
OVERLAY_VALIDATION_FILE_NAME = "controlled_overlay_reconstruction_validation.csv"
OVERLAY_QUARANTINE_FILE_NAME = "controlled_overlay_reconstruction_quarantine_rows.csv"
REBUILD_REVIEW_ROWS_FILE_NAME = "model_vs_actual_review_rows.csv"
REBUILD_TOP_ERRORS_FILE_NAME = "model_vs_actual_top_errors.csv"

REQUIRED_OVERLAY_FILE_NAMES: tuple[str, ...] = (
    OVERLAY_ROWS_FILE_NAME,
    OVERLAY_SUMMARY_FILE_NAME,
    OVERLAY_BY_CATEGORY_FILE_NAME,
    OVERLAY_TOP_SKUS_FILE_NAME,
    OVERLAY_VALIDATION_FILE_NAME,
    OVERLAY_QUARANTINE_FILE_NAME,
)

REQUIRED_REBUILD_FILE_NAMES: tuple[str, ...] = (
    REBUILD_REVIEW_ROWS_FILE_NAME,
    REBUILD_TOP_ERRORS_FILE_NAME,
)

CONTROLLED_OVERLAY_INSPECTION_PASS = "CONTROLLED_OVERLAY_INSPECTION_PASS"
CONTROLLED_OVERLAY_INSPECTION_PASS_WITH_QUARANTINE = "CONTROLLED_OVERLAY_INSPECTION_PASS_WITH_QUARANTINE"
CONTROLLED_OVERLAY_INSPECTION_REQUIRES_NARROWING = "CONTROLLED_OVERLAY_INSPECTION_REQUIRES_NARROWING"
CONTROLLED_OVERLAY_INSPECTION_BLOCKED_GUARDRAIL_FAILURE = (
    "CONTROLLED_OVERLAY_INSPECTION_BLOCKED_GUARDRAIL_FAILURE"
)
CONTROLLED_OVERLAY_INSPECTION_BLOCKED_ORDER_RECOMMENDATION_RISK = (
    "CONTROLLED_OVERLAY_INSPECTION_BLOCKED_ORDER_RECOMMENDATION_RISK"
)

BROAD_REVIEW_SURFACE = "BROAD_REVIEW_SURFACE"
VERY_BROAD_REVIEW_SURFACE = "VERY_BROAD_REVIEW_SURFACE"
CONTROLLED_REVIEW_SURFACE = "CONTROLLED_REVIEW_SURFACE"

READY_OVERLAY_RECONSTRUCTION_STATUSES: set[str] = {
    "CONTROLLED_OVERLAY_RECONSTRUCTION_READY",
    "CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE",
}

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)
CATEGORY_QUALITY_COLUMNS: tuple[str, ...] = (
    "overlay_category",
    "row_count",
    "overlay_row_share_pct",
    "reference_row_count",
    "absolute_difference_vs_reference",
    "top20_error_hit_count",
    "top20_error_hit_share_pct",
    "mean_absolute_error_units",
    "mean_actual_gross_profit",
    "mean_capital_left_value",
    "strength_score",
    "noise_score",
    "strength_status",
    "noise_status",
    "quality_notes",
)
TOP_SKU_REVIEW_COLUMNS: tuple[str, ...] = (
    "review_rank",
    "sku_number",
    "sku_description",
    "trigger_count",
    "category_count",
    "categories",
    "best_top_error_rank",
    "max_absolute_error_units",
    "max_actual_gross_profit",
    "max_capital_left_value",
    "breadth_signal_status",
    "review_notes",
)
BROADNESS_REVIEW_COLUMNS: tuple[str, ...] = (
    "broadness_metric",
    "metric_value",
    "metric_display",
    "broadness_status",
    "notes",
)
ACTION_READINESS_COLUMNS: tuple[str, ...] = (
    "check_name",
    "check_status",
    "check_flag",
    "details",
)

EXPECTED_OVERLAY_ROW_COUNT = 598
EXPECTED_QUARANTINE_ROW_COUNT = 1
TOP_ERROR_CONCENTRATION_LIMIT = 20
TOP_SKU_LIMIT = 20


class PromotionsMaterializedSourceControlledOverlayInspectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceControlledOverlayInspectionResult:
    selected_promotion: PromotionSelection
    inspection_status: str
    broadness_status: str
    overlay_row_count: int
    review_row_count: int
    overlay_percent_of_review_rows: float
    unique_sku_count: int
    multi_category_sku_count: int
    strongest_category: str
    noisiest_category: str
    quarantine_row_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    action_layer_reconstruction_should_proceed: int
    overlay_rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    category_quality_frame: pd.DataFrame
    overlap_matrix_frame: pd.DataFrame
    top_sku_review_frame: pd.DataFrame
    broadness_review_frame: pd.DataFrame
    action_readiness_frame: pd.DataFrame
    quarantine_review_frame: pd.DataFrame
    memo_markdown: str
    recommendation: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceControlledOverlayInspectionArtifacts:
    output_root: str
    summary_csv_path: str
    category_quality_csv_path: str
    overlap_matrix_csv_path: str
    top_sku_review_csv_path: str
    broadness_review_csv_path: str
    action_readiness_csv_path: str
    quarantine_review_csv_path: str
    memo_md_path: str
    selected_promotion: str
    inspection_status: str
    overlay_row_count: int
    overlay_percent_of_review_rows: float
    unique_sku_count: int
    multi_category_sku_count: int
    broadness_status: str
    strongest_category: str
    noisiest_category: str
    quarantine_row_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    action_layer_reconstruction_should_proceed: int
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
        raise PromotionsMaterializedSourceControlledOverlayInspectionError(
            f"CSV not found: {csv_path}"
        )
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceControlledOverlayInspectionError(
            f"CSV is empty: {csv_path}"
        )
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceControlledOverlayInspectionError(
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
    raise PromotionsMaterializedSourceControlledOverlayInspectionError(
        f"--upstream-root was provided, but required {stage_label} artifacts were not found. "
        f"Looked under: {candidate_locations}. Expected files: {expected_files}."
    )


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _action_readiness_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
    return {
        "check_name": name,
        "check_status": status,
        "check_flag": int(flag),
        "details": details,
    }


def _broadness_row(metric_name: str, metric_value: object, broadness_status: str, notes: str) -> dict[str, object]:
    return {
        "broadness_metric": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "broadness_status": broadness_status,
        "notes": notes,
    }


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.map(lambda value: _normalize_text(value) or None), errors="coerce")


def _selection_from_inputs(
    *,
    requested_promotion_key: str | None,
    summary_metrics: dict[str, object],
    overlay_rows_frame: pd.DataFrame,
) -> PromotionSelection:
    resolved_key = requested_promotion_key or _normalize_text(summary_metrics.get("SELECTED_PROMOTION", ""))
    if not resolved_key and "promotion_key" in overlay_rows_frame.columns:
        keys = [value for value in overlay_rows_frame["promotion_key"].astype(str).drop_duplicates().tolist() if value]
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
    return frame.loc[frame["promotion_key"].astype(str) == promotion_key].reset_index(drop=True).copy()


def _broadness_status(overlay_percent_of_review_rows: float) -> str:
    if overlay_percent_of_review_rows > 20.0:
        return VERY_BROAD_REVIEW_SURFACE
    if overlay_percent_of_review_rows > 10.0:
        return BROAD_REVIEW_SURFACE
    return CONTROLLED_REVIEW_SURFACE


def _top_error_lookup(top_errors_frame: pd.DataFrame) -> pd.DataFrame:
    if top_errors_frame.empty:
        return pd.DataFrame(columns=["source_row_id", "top_error_rank"])
    lookup = top_errors_frame.loc[:, ["source_row_id", "error_rank"]].copy()
    lookup["source_row_id"] = lookup["source_row_id"].map(_normalize_text)
    lookup = lookup.drop_duplicates(subset=["source_row_id"], keep="first")
    return lookup.rename(columns={"error_rank": "top_error_rank"})


def _category_quality_frame(overlay_rows_frame: pd.DataFrame, by_category_frame: pd.DataFrame) -> pd.DataFrame:
    if overlay_rows_frame.empty:
        return pd.DataFrame(columns=CATEGORY_QUALITY_COLUMNS)

    total_overlay_rows = len(overlay_rows_frame.index)
    by_category_lookup: dict[str, dict[str, object]] = {}
    if not by_category_frame.empty and "overlay_category" in by_category_frame.columns:
        by_category_lookup = by_category_frame.set_index("overlay_category").to_dict("index")

    rows: list[dict[str, object]] = []
    for category, category_frame in overlay_rows_frame.groupby("overlay_category", sort=False):
        row_count = len(category_frame.index)
        overlay_share_pct = round(row_count / total_overlay_rows * 100.0, 2) if total_overlay_rows else 0.0
        reference_row_count = int(
            pd.to_numeric(
                pd.Series([by_category_lookup.get(str(category), {}).get("reference_row_count", 0)]),
                errors="coerce",
            ).fillna(0).iloc[0]
        )
        absolute_difference = abs(row_count - reference_row_count)
        top20_error_hit_count = int(
            _to_numeric(category_frame.get("top_error_rank", pd.Series(dtype="object")))
            .fillna(10**9)
            .le(TOP_ERROR_CONCENTRATION_LIMIT)
            .sum()
        )
        top20_error_hit_share_pct = round(top20_error_hit_count / row_count * 100.0, 2) if row_count else 0.0
        mean_absolute_error_units = round(
            float(_to_numeric(category_frame.get("absolute_error_units", pd.Series(dtype="object"))).fillna(0.0).mean()),
            4,
        )
        mean_actual_gross_profit = round(
            float(_to_numeric(category_frame.get("actual_gross_profit", pd.Series(dtype="object"))).fillna(0.0).mean()),
            4,
        )
        mean_capital_left_value = round(
            float(_to_numeric(category_frame.get("capital_left_value", pd.Series(dtype="object"))).fillna(0.0).mean()),
            4,
        )
        strength_score = round(top20_error_hit_share_pct + min(mean_absolute_error_units * 2.0, 50.0) - overlay_share_pct, 2)
        noise_score = round(overlay_share_pct + absolute_difference - top20_error_hit_share_pct, 2)
        strength_status = "STRONG_REVIEW_TRIGGER" if strength_score >= 15.0 else "WEAKER_REVIEW_TRIGGER"
        noise_status = "NOISY_REVIEW_CATEGORY" if overlay_share_pct >= 25.0 or absolute_difference > row_count else "REVIEW_CATEGORY_IN_RANGE"
        quality_notes = (
            "Category is broad relative to the original reference intent and likely needs narrowing."
            if noise_status == "NOISY_REVIEW_CATEGORY"
            else "Category remains within a review-trigger range for diagnostics-only use."
        )
        rows.append(
            {
                "overlay_category": str(category),
                "row_count": row_count,
                "overlay_row_share_pct": overlay_share_pct,
                "reference_row_count": reference_row_count,
                "absolute_difference_vs_reference": absolute_difference,
                "top20_error_hit_count": top20_error_hit_count,
                "top20_error_hit_share_pct": top20_error_hit_share_pct,
                "mean_absolute_error_units": mean_absolute_error_units,
                "mean_actual_gross_profit": mean_actual_gross_profit,
                "mean_capital_left_value": mean_capital_left_value,
                "strength_score": strength_score,
                "noise_score": noise_score,
                "strength_status": strength_status,
                "noise_status": noise_status,
                "quality_notes": quality_notes,
            }
        )
    return pd.DataFrame(rows, columns=CATEGORY_QUALITY_COLUMNS)


def _overlap_matrix_frame(overlay_rows_frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    categories = overlay_rows_frame.get("overlay_category", pd.Series(dtype="object")).astype(str).drop_duplicates().tolist()
    if not categories:
        return pd.DataFrame(columns=["overlay_category"]), 0

    presence = pd.crosstab(
        overlay_rows_frame.get("sku_number", pd.Series(dtype="object")).astype(str),
        overlay_rows_frame.get("overlay_category", pd.Series(dtype="object")).astype(str),
    ).gt(0)

    rows: list[dict[str, object]] = []
    overlap_count = 0
    for left_category in categories:
        row: dict[str, object] = {"overlay_category": left_category}
        for right_category in categories:
            shared_count = int((presence[left_category] & presence[right_category]).sum())
            if left_category != right_category:
                overlap_count += shared_count
            row[right_category] = shared_count
        rows.append(row)
    return pd.DataFrame(rows, columns=["overlay_category", *categories]), overlap_count


def _top_sku_review_frame(overlay_rows_frame: pd.DataFrame) -> pd.DataFrame:
    if overlay_rows_frame.empty:
        return pd.DataFrame(columns=TOP_SKU_REVIEW_COLUMNS)

    grouped = (
        overlay_rows_frame.assign(
            sku_number=lambda frame: frame["sku_number"].astype(str),
            top_error_rank_numeric=lambda frame: _to_numeric(frame.get("top_error_rank", pd.Series(dtype="object"))),
            absolute_error_numeric=lambda frame: _to_numeric(frame.get("absolute_error_units", pd.Series(dtype="object"))).fillna(0.0),
            actual_gp_numeric=lambda frame: _to_numeric(frame.get("actual_gross_profit", pd.Series(dtype="object"))).fillna(0.0),
            capital_left_numeric=lambda frame: _to_numeric(frame.get("capital_left_value", pd.Series(dtype="object"))).fillna(0.0),
        )
        .groupby(["sku_number", "sku_description"], as_index=False)
        .agg(
            trigger_count=("source_row_id", "count"),
            category_count=("overlay_category", "nunique"),
            categories=("overlay_category", lambda values: "; ".join(sorted({str(value) for value in values}))),
            best_top_error_rank=("top_error_rank_numeric", "min"),
            max_absolute_error_units=("absolute_error_numeric", "max"),
            max_actual_gross_profit=("actual_gp_numeric", "max"),
            max_capital_left_value=("capital_left_numeric", "max"),
        )
    )
    grouped = grouped.sort_values(
        by=["trigger_count", "max_absolute_error_units", "max_actual_gross_profit", "max_capital_left_value", "sku_number"],
        ascending=[False, False, False, False, True],
        kind="stable",
    ).head(TOP_SKU_LIMIT)
    grouped = grouped.reset_index(drop=True)
    grouped["review_rank"] = range(1, len(grouped.index) + 1)
    grouped["breadth_signal_status"] = grouped["category_count"].map(
        lambda value: "MULTI_CATEGORY_TRIGGER" if int(value) > 1 else "SINGLE_CATEGORY_TRIGGER"
    )
    grouped["review_notes"] = grouped["breadth_signal_status"].map(
        lambda value: (
            "SKU carries multiple category triggers and should be checked for duplicate review signals."
            if value == "MULTI_CATEGORY_TRIGGER"
            else "SKU carries a single category trigger."
        )
    )
    grouped["best_top_error_rank"] = grouped["best_top_error_rank"].fillna("")
    return grouped.loc[:, TOP_SKU_REVIEW_COLUMNS].copy()


def _quarantine_review_frame(quarantine_rows_frame: pd.DataFrame, overlay_rows_frame: pd.DataFrame) -> pd.DataFrame:
    columns = (
        "quarantine_review_status",
        "quarantine_preserved_flag",
        "overlay_rows_clear_flag",
        *quarantine_rows_frame.columns,
    )
    if quarantine_rows_frame.empty:
        return pd.DataFrame(columns=columns)

    review_frame = quarantine_rows_frame.copy()
    quarantine_row_numbers = set(
        pd.to_numeric(review_frame.get("source_row_number", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    overlay_row_ids = set(
        pd.to_numeric(overlay_rows_frame.get("source_row_id", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    quarantine_preserved_flag = int(48 in quarantine_row_numbers and len(review_frame.index) == EXPECTED_QUARANTINE_ROW_COUNT)
    overlay_rows_clear_flag = int(not bool(quarantine_row_numbers.intersection(overlay_row_ids)))
    review_frame["quarantine_review_status"] = (
        "QUARANTINE_ROW_48_PRESERVED" if quarantine_preserved_flag and overlay_rows_clear_flag else "QUARANTINE_REVIEW_FAILED"
    )
    review_frame["quarantine_preserved_flag"] = quarantine_preserved_flag
    review_frame["overlay_rows_clear_flag"] = overlay_rows_clear_flag
    return review_frame.loc[:, columns].copy()


def _strongest_and_noisiest_category(category_quality_frame: pd.DataFrame) -> tuple[str, str]:
    if category_quality_frame.empty:
        return "", ""
    strongest_category = str(
        category_quality_frame.sort_values(
            by=["strength_score", "top20_error_hit_share_pct", "row_count", "overlay_category"],
            ascending=[False, False, False, True],
            kind="stable",
        ).iloc[0]["overlay_category"]
    )
    noisiest_category = str(
        category_quality_frame.sort_values(
            by=["noise_score", "row_count", "overlay_category"],
            ascending=[False, False, True],
            kind="stable",
        ).iloc[0]["overlay_category"]
    )
    return strongest_category, noisiest_category


def build_promotions_materialized_source_controlled_overlay_inspection(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceControlledOverlayInspectionResult:
    packet_root_path = Path(packet_root)
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

    overlay_rows_frame = _read_csv(overlay_root / OVERLAY_ROWS_FILE_NAME)
    overlay_summary_frame = _read_csv(overlay_root / OVERLAY_SUMMARY_FILE_NAME)
    overlay_by_category_frame = _read_csv(overlay_root / OVERLAY_BY_CATEGORY_FILE_NAME)
    _read_csv(overlay_root / OVERLAY_TOP_SKUS_FILE_NAME, allow_empty=True)
    overlay_validation_frame = _read_csv(overlay_root / OVERLAY_VALIDATION_FILE_NAME)
    overlay_quarantine_rows_frame = _read_csv(overlay_root / OVERLAY_QUARANTINE_FILE_NAME, allow_empty=True)
    rebuild_review_rows_frame = _read_csv(rebuild_root / REBUILD_REVIEW_ROWS_FILE_NAME)
    rebuild_top_errors_frame = _read_csv(rebuild_root / REBUILD_TOP_ERRORS_FILE_NAME)

    overlay_summary_metrics = _metric_lookup(overlay_summary_frame)
    selection = _selection_from_inputs(
        requested_promotion_key=promotion_key,
        summary_metrics=overlay_summary_metrics,
        overlay_rows_frame=overlay_rows_frame,
    )

    overlay_rows_frame = _filter_for_promotion(overlay_rows_frame, selection.promotion_key)
    overlay_quarantine_rows_frame = _filter_for_promotion(overlay_quarantine_rows_frame, selection.promotion_key)
    rebuild_review_rows_frame = _filter_for_promotion(rebuild_review_rows_frame, selection.promotion_key)
    rebuild_top_errors_frame = _filter_for_promotion(rebuild_top_errors_frame, selection.promotion_key)

    if "top_error_rank" not in overlay_rows_frame.columns or overlay_rows_frame["top_error_rank"].astype(str).eq("").all():
        lookup = _top_error_lookup(rebuild_top_errors_frame)
        overlay_rows_frame["source_row_id"] = overlay_rows_frame["source_row_id"].map(_normalize_text)
        overlay_rows_frame = overlay_rows_frame.merge(lookup, on="source_row_id", how="left")

    overlay_reconstruction_status = _normalize_text(overlay_summary_metrics.get("OVERLAY_RECONSTRUCTION_STATUS", ""))
    production_guardrail_status = _normalize_text(overlay_summary_metrics.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL")) or "FAIL"
    stage12_guardrail_status = _normalize_text(overlay_summary_metrics.get("STAGE12_GUARDRAIL_STATUS", "FAIL")) or "FAIL"

    overlay_row_count = len(overlay_rows_frame.index)
    review_row_count = len(rebuild_review_rows_frame.index)
    quarantine_row_count = len(overlay_quarantine_rows_frame.index)
    overlay_percent_of_review_rows = round(overlay_row_count / review_row_count * 100.0, 2) if review_row_count else 0.0
    unique_sku_count = overlay_rows_frame.get("sku_number", pd.Series(dtype="object")).astype(str).nunique()
    multi_category_sku_count = int(
        overlay_rows_frame.groupby(overlay_rows_frame.get("sku_number", pd.Series(dtype="object")).astype(str))["overlay_category"]
        .nunique()
        .gt(1)
        .sum()
        if overlay_row_count
        else 0
    )
    broadness_status = _broadness_status(overlay_percent_of_review_rows)

    category_quality_frame = _category_quality_frame(overlay_rows_frame, overlay_by_category_frame)
    strongest_category, noisiest_category = _strongest_and_noisiest_category(category_quality_frame)
    overlap_matrix_frame, overlap_count = _overlap_matrix_frame(overlay_rows_frame)
    top_sku_review_frame = _top_sku_review_frame(overlay_rows_frame)
    quarantine_review_frame = _quarantine_review_frame(overlay_quarantine_rows_frame, overlay_rows_frame)

    overlay_validation_lookup: dict[str, str] = {}
    if not overlay_validation_frame.empty and {"check_name", "check_status"}.issubset(overlay_validation_frame.columns):
        overlay_validation_lookup = dict(
            zip(
                overlay_validation_frame["check_name"].astype(str),
                overlay_validation_frame["check_status"].astype(str),
            )
        )

    quarantine_numbers = set(
        pd.to_numeric(overlay_quarantine_rows_frame.get("source_row_number", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    overlay_row_ids = set(
        pd.to_numeric(overlay_rows_frame.get("source_row_id", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    no_quarantine_rows_included_flag = int(not bool(quarantine_numbers.intersection(overlay_row_ids)))
    no_order_recommendations_generated_flag = int(
        _to_numeric(overlay_rows_frame.get("generated_order_recommendation_flag", pd.Series(dtype="object")))
        .fillna(0.0)
        .eq(0.0)
        .all()
        and overlay_validation_lookup.get("NO_ORDER_RECOMMENDATIONS_GENERATED", "PASS") == "PASS"
    )
    overlay_row_count_matches_expected_flag = int(overlay_row_count == EXPECTED_OVERLAY_ROW_COUNT)
    quarantine_row_count_matches_expected_flag = int(quarantine_row_count == EXPECTED_QUARANTINE_ROW_COUNT)
    category_rows_non_empty_flag = int(not category_quality_frame.empty)
    top_sku_review_non_empty_flag = int(not top_sku_review_frame.empty)
    overlap_matrix_written_flag = int(not overlap_matrix_frame.empty)
    broadness_score = round(overlay_percent_of_review_rows + float(multi_category_sku_count), 2)
    upstream_overlay_ready_flag = int(overlay_reconstruction_status in READY_OVERLAY_RECONSTRUCTION_STATUSES)

    if production_guardrail_status != "PASS" or stage12_guardrail_status != "PASS":
        inspection_status = CONTROLLED_OVERLAY_INSPECTION_BLOCKED_GUARDRAIL_FAILURE
    elif no_order_recommendations_generated_flag == 0 or upstream_overlay_ready_flag == 0:
        inspection_status = CONTROLLED_OVERLAY_INSPECTION_BLOCKED_ORDER_RECOMMENDATION_RISK
    elif broadness_status in {BROAD_REVIEW_SURFACE, VERY_BROAD_REVIEW_SURFACE}:
        inspection_status = CONTROLLED_OVERLAY_INSPECTION_REQUIRES_NARROWING
    elif quarantine_row_count > 0:
        inspection_status = CONTROLLED_OVERLAY_INSPECTION_PASS_WITH_QUARANTINE
    else:
        inspection_status = CONTROLLED_OVERLAY_INSPECTION_PASS

    action_layer_reconstruction_should_proceed = int(
        inspection_status in {CONTROLLED_OVERLAY_INSPECTION_PASS, CONTROLLED_OVERLAY_INSPECTION_PASS_WITH_QUARANTINE}
    )

    if inspection_status == CONTROLLED_OVERLAY_INSPECTION_REQUIRES_NARROWING:
        recommendation = (
            "Do not proceed to action-layer review reconstruction yet. Narrow the controlled overlay surface before recalibration or downstream action-layer work."
        )
    elif inspection_status in {
        CONTROLLED_OVERLAY_INSPECTION_BLOCKED_GUARDRAIL_FAILURE,
        CONTROLLED_OVERLAY_INSPECTION_BLOCKED_ORDER_RECOMMENDATION_RISK,
    }:
        recommendation = (
            "Do not proceed to action-layer review reconstruction yet. Repair the blocked guardrail or review-only safety findings first."
        )
    else:
        recommendation = (
            "Controlled overlay inspection passed. Action-layer review reconstruction may proceed as a diagnostics-only next step while quarantine row 48 remains separate."
        )

    broadness_review_frame = pd.DataFrame(
        [
            _broadness_row("OVERLAY_ROW_COUNT", overlay_row_count, broadness_status, "Controlled overlay reconstruction row count."),
            _broadness_row("REVIEW_ROW_COUNT", review_row_count, broadness_status, "Controlled governed rebuild review row count."),
            _broadness_row("OVERLAY_PERCENT_OF_REVIEW_ROWS", overlay_percent_of_review_rows, broadness_status, "Overlay rows as a percent of review rows."),
            _broadness_row("UNIQUE_SKU_COUNT", unique_sku_count, broadness_status, "Unique SKUs represented in the overlay rows."),
            _broadness_row(
                "UNIQUE_SKU_PERCENT_OF_REVIEW_ROWS",
                round(unique_sku_count / review_row_count * 100.0, 2) if review_row_count else 0.0,
                broadness_status,
                "Unique overlay SKUs as a percent of review rows.",
            ),
            _broadness_row("MULTI_CATEGORY_SKU_COUNT", multi_category_sku_count, broadness_status, "Count of SKUs appearing in multiple overlay categories."),
            _broadness_row("OVERLAP_COUNT_BY_SKU", overlap_count, broadness_status, "Off-diagonal category overlap count by SKU."),
            _broadness_row(
                "ROWS_PER_CATEGORY",
                "; ".join([f"{category}:{count}" for category, count in overlay_rows_frame["overlay_category"].value_counts().to_dict().items()]),
                broadness_status,
                "Rows per overlay category.",
            ),
            _broadness_row(
                "TOP_20_SKUS_BY_REVIEW_TRIGGERS",
                "; ".join(top_sku_review_frame["sku_number"].astype(str).head(TOP_SKU_LIMIT).tolist()),
                broadness_status,
                "Top 20 SKUs ranked by number of review triggers.",
            ),
            _broadness_row("BROADNESS_SCORE", broadness_score, broadness_status, "Composite broadness score from overall surface share and multi-category overlap."),
        ],
        columns=BROADNESS_REVIEW_COLUMNS,
    )

    action_readiness_frame = pd.DataFrame(
        [
            _action_readiness_row(
                "OVERLAY_ROW_COUNT_MATCHES_EXPECTATION",
                "PASS" if overlay_row_count_matches_expected_flag else "FAIL",
                overlay_row_count_matches_expected_flag,
                f"overlay_rows={overlay_row_count}, expected={EXPECTED_OVERLAY_ROW_COUNT}",
            ),
            _action_readiness_row(
                "QUARANTINE_ROW_COUNT_MATCHES_EXPECTATION",
                "PASS" if quarantine_row_count_matches_expected_flag else "FAIL",
                quarantine_row_count_matches_expected_flag,
                f"quarantine_rows={quarantine_row_count}, expected={EXPECTED_QUARANTINE_ROW_COUNT}",
            ),
            _action_readiness_row(
                "NO_QUARANTINE_ROWS_INCLUDED_IN_OVERLAY_ROWS",
                "PASS" if no_quarantine_rows_included_flag else "FAIL",
                no_quarantine_rows_included_flag,
                "Quarantine row 48 remains excluded from the overlay rows.",
            ),
            _action_readiness_row(
                "NO_ORDER_RECOMMENDATIONS_GENERATED",
                "PASS" if no_order_recommendations_generated_flag else "FAIL",
                no_order_recommendations_generated_flag,
                "Overlay rows remain review triggers only and do not generate order recommendations.",
            ),
            _action_readiness_row(
                "PRODUCTION_GUARDRAIL_PASS",
                production_guardrail_status,
                int(production_guardrail_status == "PASS"),
                f"production_guardrail_status={production_guardrail_status}",
            ),
            _action_readiness_row(
                "STAGE12_GUARDRAIL_PASS",
                stage12_guardrail_status,
                int(stage12_guardrail_status == "PASS"),
                f"stage12_guardrail_status={stage12_guardrail_status}",
            ),
            _action_readiness_row(
                "CATEGORY_ROWS_NON_EMPTY",
                "PASS" if category_rows_non_empty_flag else "FAIL",
                category_rows_non_empty_flag,
                f"category_rows={len(category_quality_frame.index)}",
            ),
            _action_readiness_row(
                "TOP_SKU_REVIEW_NON_EMPTY",
                "PASS" if top_sku_review_non_empty_flag else "FAIL",
                top_sku_review_non_empty_flag,
                f"top_sku_review_rows={len(top_sku_review_frame.index)}",
            ),
            _action_readiness_row(
                "CATEGORY_OVERLAP_MATRIX_WRITTEN",
                "PASS" if overlap_matrix_written_flag else "FAIL",
                overlap_matrix_written_flag,
                f"overlap_matrix_rows={len(overlap_matrix_frame.index)}",
            ),
            _action_readiness_row(
                "BROADNESS_SCORE_CALCULATED",
                "PASS",
                1,
                f"broadness_score={broadness_score}",
            ),
            _action_readiness_row(
                "ACTION_LAYER_RECONSTRUCTION_READINESS_STATED",
                "PASS",
                1,
                recommendation,
            ),
            _action_readiness_row(
                "UPSTREAM_OVERLAY_RECONSTRUCTION_READY",
                "PASS" if upstream_overlay_ready_flag else "FAIL",
                upstream_overlay_ready_flag,
                f"overlay_reconstruction_status={overlay_reconstruction_status}",
            ),
        ],
        columns=ACTION_READINESS_COLUMNS,
    )

    summary_frame = pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION", selection.promotion_key, "Promotion selected for the diagnostics-only controlled overlay inspection pack."),
            _summary_row("INSPECTION_STATUS", inspection_status, "Overall diagnostics-only controlled overlay inspection status."),
            _summary_row("OVERLAY_ROW_COUNT", overlay_row_count, "Controlled overlay reconstruction row count."),
            _summary_row("REVIEW_ROW_COUNT", review_row_count, "Controlled governed rebuild review row count."),
            _summary_row("OVERLAY_PERCENT_OF_REVIEW_ROWS", overlay_percent_of_review_rows, "Overlay rows as a percent of review rows."),
            _summary_row("UNIQUE_SKU_COUNT", unique_sku_count, "Unique SKUs represented in the overlay rows."),
            _summary_row("MULTI_CATEGORY_SKU_COUNT", multi_category_sku_count, "Count of SKUs that appear in multiple overlay categories."),
            _summary_row("BROADNESS_STATUS", broadness_status, "Broadness interpretation of the reconstructed overlay surface."),
            _summary_row("STRONGEST_CATEGORY", strongest_category, "Category with the strongest concentration and signal profile."),
            _summary_row("NOISIEST_CATEGORY", noisiest_category, "Category with the broadest and noisiest signal profile."),
            _summary_row("QUARANTINE_ROW_COUNT", quarantine_row_count, "Quarantine row count preserved separately."),
            _summary_row("PRODUCTION_GUARDRAIL_STATUS", production_guardrail_status, "Production ordering logic remained unchanged."),
            _summary_row("STAGE12_GUARDRAIL_STATUS", stage12_guardrail_status, "Stage 12 remained unchanged."),
            _summary_row("ACTION_LAYER_RECONSTRUCTION_SHOULD_PROCEED", action_layer_reconstruction_should_proceed, "Whether action-layer review reconstruction should proceed from this inspection outcome."),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Controlled Overlay Inspection Pack",
            "",
            "This is a diagnostics-only inspection pack for the controlled overlay reconstruction outputs.",
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
            f"Inspection status: {inspection_status}",
            f"Overlay row count: {overlay_row_count}",
            f"Overlay percent of review rows: {overlay_percent_of_review_rows}",
            f"Unique SKU count: {unique_sku_count}",
            f"Multi-category SKU count: {multi_category_sku_count}",
            f"Broadness status: {broadness_status}",
            f"Strongest category: {strongest_category}",
            f"Noisiest category: {noisiest_category}",
            f"Quarantine row count: {quarantine_row_count}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Whether action-layer reconstruction should proceed: {action_layer_reconstruction_should_proceed}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()

    return PromotionsMaterializedSourceControlledOverlayInspectionResult(
        selected_promotion=selection,
        inspection_status=inspection_status,
        broadness_status=broadness_status,
        overlay_row_count=overlay_row_count,
        review_row_count=review_row_count,
        overlay_percent_of_review_rows=overlay_percent_of_review_rows,
        unique_sku_count=unique_sku_count,
        multi_category_sku_count=multi_category_sku_count,
        strongest_category=strongest_category,
        noisiest_category=noisiest_category,
        quarantine_row_count=quarantine_row_count,
        production_guardrail_status=production_guardrail_status,
        stage12_guardrail_status=stage12_guardrail_status,
        action_layer_reconstruction_should_proceed=action_layer_reconstruction_should_proceed,
        overlay_rows_frame=overlay_rows_frame,
        summary_frame=summary_frame,
        category_quality_frame=category_quality_frame,
        overlap_matrix_frame=overlap_matrix_frame,
        top_sku_review_frame=top_sku_review_frame,
        broadness_review_frame=broadness_review_frame,
        action_readiness_frame=action_readiness_frame,
        quarantine_review_frame=quarantine_review_frame,
        memo_markdown=memo_markdown,
        recommendation=recommendation,
    )


def write_promotions_materialized_source_controlled_overlay_inspection(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceControlledOverlayInspectionArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_controlled_overlay_inspection(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_root_path / "controlled_overlay_inspection_summary.csv"
    category_quality_csv_path = output_root_path / "controlled_overlay_inspection_category_quality.csv"
    overlap_matrix_csv_path = output_root_path / "controlled_overlay_inspection_overlap_matrix.csv"
    top_sku_review_csv_path = output_root_path / "controlled_overlay_inspection_top_sku_review.csv"
    broadness_review_csv_path = output_root_path / "controlled_overlay_inspection_broadness_review.csv"
    action_readiness_csv_path = output_root_path / "controlled_overlay_inspection_action_readiness.csv"
    quarantine_review_csv_path = output_root_path / "controlled_overlay_inspection_quarantine_review.csv"
    memo_md_path = output_root_path / "controlled_overlay_inspection_memo.md"

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.category_quality_frame.to_csv(category_quality_csv_path, index=False)
    result.overlap_matrix_frame.to_csv(overlap_matrix_csv_path, index=False)
    result.top_sku_review_frame.to_csv(top_sku_review_csv_path, index=False)
    result.broadness_review_frame.to_csv(broadness_review_csv_path, index=False)
    result.action_readiness_frame.to_csv(action_readiness_csv_path, index=False)
    result.quarantine_review_frame.to_csv(quarantine_review_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceControlledOverlayInspectionArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_csv_path),
        category_quality_csv_path=str(category_quality_csv_path),
        overlap_matrix_csv_path=str(overlap_matrix_csv_path),
        top_sku_review_csv_path=str(top_sku_review_csv_path),
        broadness_review_csv_path=str(broadness_review_csv_path),
        action_readiness_csv_path=str(action_readiness_csv_path),
        quarantine_review_csv_path=str(quarantine_review_csv_path),
        memo_md_path=str(memo_md_path),
        selected_promotion=result.selected_promotion.promotion_key,
        inspection_status=result.inspection_status,
        overlay_row_count=result.overlay_row_count,
        overlay_percent_of_review_rows=result.overlay_percent_of_review_rows,
        unique_sku_count=result.unique_sku_count,
        multi_category_sku_count=result.multi_category_sku_count,
        broadness_status=result.broadness_status,
        strongest_category=result.strongest_category,
        noisiest_category=result.noisiest_category,
        quarantine_row_count=result.quarantine_row_count,
        production_guardrail_status=result.production_guardrail_status,
        stage12_guardrail_status=result.stage12_guardrail_status,
        action_layer_reconstruction_should_proceed=result.action_layer_reconstruction_should_proceed,
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only controlled overlay reconstruction inspection pack."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_controlled_overlay_inspection(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    print("selected_promotion", artifacts.selected_promotion)
    print("inspection_status", artifacts.inspection_status)
    print("overlay_row_count", artifacts.overlay_row_count)
    print("overlay_percent_of_review_rows", artifacts.overlay_percent_of_review_rows)
    print("unique_sku_count", artifacts.unique_sku_count)
    print("multi_category_sku_count", artifacts.multi_category_sku_count)
    print("broadness_status", artifacts.broadness_status)
    print("strongest_category", artifacts.strongest_category)
    print("noisiest_category", artifacts.noisiest_category)
    print("quarantine_row_count", artifacts.quarantine_row_count)
    print("production_guardrail_status", artifacts.production_guardrail_status)
    print("stage12_guardrail_status", artifacts.stage12_guardrail_status)
    print("action_layer_reconstruction_should_proceed", artifacts.action_layer_reconstruction_should_proceed)
    print("recommendation", artifacts.recommendation)
    print("controlled_overlay_inspection_summary", artifacts.summary_csv_path)
    print("controlled_overlay_inspection_category_quality", artifacts.category_quality_csv_path)
    print("controlled_overlay_inspection_overlap_matrix", artifacts.overlap_matrix_csv_path)
    print("controlled_overlay_inspection_top_sku_review", artifacts.top_sku_review_csv_path)
    print("controlled_overlay_inspection_broadness_review", artifacts.broadness_review_csv_path)
    print("controlled_overlay_inspection_action_readiness", artifacts.action_readiness_csv_path)
    print("controlled_overlay_inspection_quarantine_review", artifacts.quarantine_review_csv_path)
    print("controlled_overlay_inspection_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
