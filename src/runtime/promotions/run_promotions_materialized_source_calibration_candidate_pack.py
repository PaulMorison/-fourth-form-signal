from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_calibration_candidate_pack"
INSPECTION_FOLDER_NAME = "materialized_source_action_layer_review_inspection"
RECONSTRUCTION_FOLDER_NAME = "materialized_source_action_layer_review_reconstruction"

INSPECTION_SUMMARY_FILE_NAME = "action_layer_review_inspection_summary.csv"
INSPECTION_QUALITY_CHECKS_FILE_NAME = "action_layer_review_inspection_quality_checks.csv"
INSPECTION_BY_RULE_FAMILY_FILE_NAME = "action_layer_review_inspection_by_rule_family.csv"
INSPECTION_BY_CATEGORY_FILE_NAME = "action_layer_review_inspection_by_category.csv"
INSPECTION_TOP_SKUS_FILE_NAME = "action_layer_review_inspection_top_skus.csv"
INSPECTION_CALIBRATION_READINESS_FILE_NAME = (
    "action_layer_review_inspection_calibration_readiness.csv"
)
INSPECTION_QUARANTINE_REVIEW_FILE_NAME = (
    "action_layer_review_inspection_quarantine_review.csv"
)
REQUIRED_INSPECTION_FILE_NAMES: tuple[str, ...] = (
    INSPECTION_SUMMARY_FILE_NAME,
    INSPECTION_QUALITY_CHECKS_FILE_NAME,
    INSPECTION_BY_RULE_FAMILY_FILE_NAME,
    INSPECTION_BY_CATEGORY_FILE_NAME,
    INSPECTION_TOP_SKUS_FILE_NAME,
    INSPECTION_CALIBRATION_READINESS_FILE_NAME,
    INSPECTION_QUARANTINE_REVIEW_FILE_NAME,
)
RECONSTRUCTION_ROWS_FILE_NAME = "action_layer_review_reconstruction_rows.csv"
RECONSTRUCTION_QUARANTINE_FILE_NAME = (
    "action_layer_review_reconstruction_quarantine_rows.csv"
)
REQUIRED_RECONSTRUCTION_FILE_NAMES: tuple[str, ...] = (
    RECONSTRUCTION_ROWS_FILE_NAME,
    RECONSTRUCTION_QUARANTINE_FILE_NAME,
)

CALIBRATION_CANDIDATE_PACK_READY = "CALIBRATION_CANDIDATE_PACK_READY"
CALIBRATION_CANDIDATE_PACK_READY_WITH_QUARANTINE = (
    "CALIBRATION_CANDIDATE_PACK_READY_WITH_QUARANTINE"
)
CALIBRATION_CANDIDATE_PACK_REQUIRES_REPEAT_EVIDENCE = (
    "CALIBRATION_CANDIDATE_PACK_REQUIRES_REPEAT_EVIDENCE"
)
CALIBRATION_CANDIDATE_PACK_BLOCKED_GUARDRAIL_FAILURE = (
    "CALIBRATION_CANDIDATE_PACK_BLOCKED_GUARDRAIL_FAILURE"
)
CALIBRATION_CANDIDATE_PACK_BLOCKED_ORDER_RECOMMENDATION_RISK = (
    "CALIBRATION_CANDIDATE_PACK_BLOCKED_ORDER_RECOMMENDATION_RISK"
)

CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST = (
    "CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST"
)
CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE = (
    "CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE"
)
CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY = (
    "CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY"
)
CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL = "CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL"
CALIBRATION_CANDIDATE_REJECT_GUARDRAIL_OR_ORDER_RISK = (
    "CALIBRATION_CANDIDATE_REJECT_GUARDRAIL_OR_ORDER_RISK"
)

ACTION_LAYER_REVIEW_INSPECTION_READY_FOR_CALIBRATION_CANDIDATE_PACK = (
    "ACTION_LAYER_REVIEW_INSPECTION_READY_FOR_CALIBRATION_CANDIDATE_PACK"
)
ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE = (
    "ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE"
)
READY_INSPECTION_STATUSES = {
    ACTION_LAYER_REVIEW_INSPECTION_READY_FOR_CALIBRATION_CANDIDATE_PACK,
    ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE,
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
ROWS_COLUMNS = (
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_row_id",
    "sku_number",
    "sku_description",
    "overlay_category",
    "rule_family_candidate",
    "review_signal_score",
    "review_signal_label",
    "actual_units",
    "expected_promo_demand",
    "absolute_error_units",
    "actual_gross_profit",
    "capital_left_value",
    "production_order_change_flag",
    "stage_12_change_flag",
    "quarantine_flag",
    "calibration_candidate_tier",
    "calibration_priority_score",
    "repeat_evidence_required_flag",
    "calibration_candidate_status",
    "row_recommendation",
    "calibration_notes",
)
BY_RULE_FAMILY_COLUMNS = (
    "rule_family_candidate",
    "review_row_count",
    "candidate_row_count",
    "tier_1_count",
    "tier_2_count",
    "tier_3_count",
    "deferred_count",
    "rejected_count",
    "row_share_pct",
    "mean_review_signal_score",
    "mean_actual_gross_profit",
    "mean_capital_left_value",
    "sample_skus",
    "family_priority_score",
    "family_readiness_tier",
    "repeat_evidence_required_flag",
    "quality_notes",
)
BY_CATEGORY_COLUMNS = (
    "overlay_category",
    "review_row_count",
    "candidate_row_count",
    "tier_1_count",
    "tier_2_count",
    "tier_3_count",
    "deferred_count",
    "rejected_count",
    "row_share_pct",
    "mean_review_signal_score",
    "mean_actual_gross_profit",
    "mean_capital_left_value",
    "sample_skus",
    "category_priority_score",
    "category_readiness_tier",
    "repeat_evidence_required_flag",
    "quality_notes",
)
PRIORITY_QUEUE_COLUMNS = (
    "queue_rank",
    "calibration_candidate_tier",
    "rule_family_candidate",
    "overlay_category",
    "sku_number",
    "sku_description",
    "review_signal_score",
    "actual_units",
    "expected_promo_demand",
    "actual_gross_profit",
    "capital_left_value",
    "calibration_priority_score",
    "repeat_evidence_required_flag",
    "row_recommendation",
    "calibration_notes",
)

TIER_PRIORITY = {
    CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST: 1,
    CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE: 2,
    CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY: 3,
    CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL: 4,
    CALIBRATION_CANDIDATE_REJECT_GUARDRAIL_OR_ORDER_RISK: 5,
}
DISALLOWED_ORDER_COLUMNS = {
    "recommended_order_units",
    "final_store_order_units",
    "generated_order_recommendation_flag",
}


class PromotionsMaterializedSourceCalibrationCandidatePackError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceCalibrationCandidatePackResult:
    selected_promotion: PromotionSelection
    candidate_pack_status: str
    input_review_rows: int
    tier_1_candidate_count: int
    tier_2_candidate_count: int
    tier_3_candidate_count: int
    deferred_count: int
    rejected_count: int
    strongest_candidate_rule_family: str
    repeat_evidence_required_flag: int
    quarantine_row_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    repeat_evidence_pack_can_be_authored_next: int
    candidate_rows_frame: pd.DataFrame
    by_rule_family_frame: pd.DataFrame
    by_category_frame: pd.DataFrame
    priority_queue_frame: pd.DataFrame
    rejected_or_deferred_rows_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str
    recommendation: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceCalibrationCandidatePackArtifacts:
    output_root: str
    rows_csv_path: str
    by_rule_family_csv_path: str
    by_category_csv_path: str
    priority_queue_csv_path: str
    rejected_or_deferred_csv_path: str
    validation_csv_path: str
    summary_csv_path: str
    memo_md_path: str
    selected_promotion: str
    candidate_pack_status: str
    input_review_rows: int
    tier_1_candidate_count: int
    tier_2_candidate_count: int
    tier_3_candidate_count: int
    deferred_count: int
    rejected_count: int
    strongest_candidate_rule_family: str
    repeat_evidence_required_flag: int
    quarantine_row_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    repeat_evidence_pack_can_be_authored_next: int
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
        raise PromotionsMaterializedSourceCalibrationCandidatePackError(
            f"CSV not found: {csv_path}"
        )
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceCalibrationCandidatePackError(
            f"CSV is empty: {csv_path}"
        )
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceCalibrationCandidatePackError(
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
    raise PromotionsMaterializedSourceCalibrationCandidatePackError(
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


def _quality_lookup(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty or "check_name" not in frame.columns:
        return {}
    return {
        _normalize_text(row.get("check_name")): _normalize_text(row.get("check_status"))
        for row in frame.to_dict("records")
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


def _aggregate_lookup(frame: pd.DataFrame, key_column: str) -> dict[str, dict[str, object]]:
    if frame.empty or key_column not in frame.columns:
        return {}
    lookup: dict[str, dict[str, object]] = {}
    for row in frame.to_dict("records"):
        lookup[_normalize_text(row.get(key_column))] = row
    return lookup


def _row_priority_score(
    row: pd.Series,
    *,
    family_lookup: dict[str, dict[str, object]],
    category_lookup: dict[str, dict[str, object]],
    strongest_rule_family: str,
) -> float:
    rule_family = _normalize_text(row.get("rule_family_candidate"))
    category = _normalize_text(row.get("overlay_category"))
    signal = _to_float(row.get("review_signal_score"))
    absolute_error = _to_float(row.get("absolute_error_units"))
    actual_units = _to_float(row.get("actual_units"))
    expected_units = max(_to_float(row.get("expected_promo_demand")), 1.0)
    gross_profit = _to_float(row.get("actual_gross_profit"))
    capital_left = _to_float(row.get("capital_left_value"))
    family_row = family_lookup.get(rule_family, {})
    category_row = category_lookup.get(category, {})
    family_noise = _normalize_text(family_row.get("noise_status")) == "NOISY_SURFACE"
    category_noise = _normalize_text(category_row.get("noise_status")) == "NOISY_SURFACE"
    family_strength_bonus = 2.0 if _normalize_text(family_row.get("strength_status")) == "STRONG_SIGNAL" else 0.0
    category_strength_bonus = 1.0 if _normalize_text(category_row.get("strength_status")) == "STRONG_SIGNAL" else 0.0
    strongest_bonus = 3.0 if rule_family == strongest_rule_family else 0.0
    demand_ratio_bonus = min(actual_units / expected_units, 5.0)
    economics_bonus = min(gross_profit / 10.0, 4.0) + min(capital_left / 5.0, 2.0)
    noise_penalty = 3.0 if family_noise or category_noise else 0.0
    return round(
        signal + (absolute_error * 0.5) + demand_ratio_bonus + economics_bonus + strongest_bonus + family_strength_bonus + category_strength_bonus - noise_penalty,
        4,
    )


def _classify_row(
    row: pd.Series,
    *,
    family_lookup: dict[str, dict[str, object]],
    category_lookup: dict[str, dict[str, object]],
    strongest_rule_family: str,
    blocked_order_risk: bool,
    blocked_guardrail: bool,
    repeat_evidence_required_flag: int,
) -> tuple[str, str, str, float]:
    priority_score = _row_priority_score(
        row,
        family_lookup=family_lookup,
        category_lookup=category_lookup,
        strongest_rule_family=strongest_rule_family,
    )
    rule_family = _normalize_text(row.get("rule_family_candidate"))
    category = _normalize_text(row.get("overlay_category"))
    signal = _to_float(row.get("review_signal_score"))
    actual_units = _to_float(row.get("actual_units"))
    expected_units = max(_to_float(row.get("expected_promo_demand")), 1.0)
    gross_profit = _to_float(row.get("actual_gross_profit"))
    capital_left = _to_float(row.get("capital_left_value"))
    absolute_error = _to_float(row.get("absolute_error_units"))
    demand_ratio = actual_units / expected_units
    family_row = family_lookup.get(rule_family, {})
    category_row = category_lookup.get(category, {})
    family_noise = _normalize_text(family_row.get("noise_status")) == "NOISY_SURFACE"
    category_noise = _normalize_text(category_row.get("noise_status")) == "NOISY_SURFACE"
    row_guardrail_risk = (
        blocked_guardrail
        or blocked_order_risk
        or _to_int(row.get("production_order_change_flag")) != 0
        or _to_int(row.get("stage_12_change_flag")) != 0
        or _to_int(row.get("quarantine_flag")) != 0
    )

    if row_guardrail_risk:
        return (
            CALIBRATION_CANDIDATE_REJECT_GUARDRAIL_OR_ORDER_RISK,
            "REJECT",
            "Keep this row out of calibration research until guardrail or order-risk conditions are repaired.",
            priority_score,
        )
    if (
        (rule_family == strongest_rule_family and signal >= 9.0 and demand_ratio >= 3.0 and (gross_profit >= 15.0 or capital_left >= 1.0))
        or (signal >= 10.0 and (gross_profit >= 12.0 or capital_left >= 2.0 or absolute_error >= 5.0))
    ):
        return (
            CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST,
            "CANDIDATE",
            "Highest-priority calibration research row; keep diagnostics-only and test first after repeat evidence is assembled.",
            priority_score,
        )
    if family_noise or category_noise:
        if signal >= 8.0 and actual_units >= 5.0 and gross_profit >= 10.0:
            return (
                CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE,
                "CANDIDATE",
                "Commercially useful signal is present, but this broader surface still needs repeat evidence before calibration work.",
                priority_score,
            )
        return (
            CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL,
            "DEFER",
            "Signal remains too noisy for calibration research on a single-promotion surface.",
            priority_score,
        )
    if signal >= 7.0 and actual_units >= 4.0 and (gross_profit >= 8.0 or absolute_error >= 4.0):
        return (
            CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE,
            "CANDIDATE",
            "Useful calibration research row, but repeat evidence across more promotions is still required.",
            priority_score,
        )
    if signal >= 4.0 and (actual_units > 0.0 or gross_profit > 0.0):
        notes = (
            "Operator-review-only row. Keep for notes and pattern review, not for immediate calibration candidate promotion."
            if repeat_evidence_required_flag == 1
            else "Operator-review-only row that can stay in the pack for context."
        )
        return (
            CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY,
            "CANDIDATE",
            notes,
            priority_score,
        )
    return (
        CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL,
        "DEFER",
        "Signal is too weak to carry into calibration research yet.",
        priority_score,
    )


def _build_row_frames(
    rows_frame: pd.DataFrame,
    *,
    family_lookup: dict[str, dict[str, object]],
    category_lookup: dict[str, dict[str, object]],
    strongest_rule_family: str,
    blocked_order_risk: bool,
    blocked_guardrail: bool,
    repeat_evidence_required_flag: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if rows_frame.empty:
        empty = pd.DataFrame(columns=ROWS_COLUMNS)
        return empty, empty.copy()

    records: list[dict[str, object]] = []
    for row_dict in rows_frame.to_dict("records"):
        row = pd.Series(row_dict)
        tier, status, notes, priority_score = _classify_row(
            row,
            family_lookup=family_lookup,
            category_lookup=category_lookup,
            strongest_rule_family=strongest_rule_family,
            blocked_order_risk=blocked_order_risk,
            blocked_guardrail=blocked_guardrail,
            repeat_evidence_required_flag=repeat_evidence_required_flag,
        )
        records.append(
            {
                "promotion_key": _normalize_text(row.get("promotion_key")),
                "promotion_name": _normalize_text(row.get("promotion_name")),
                "promotion_start_date": _normalize_text(row.get("promotion_start_date")),
                "promotion_end_date": _normalize_text(row.get("promotion_end_date")),
                "source_row_id": _to_int(row.get("source_row_id"), default=-1),
                "sku_number": _normalize_text(row.get("sku_number")),
                "sku_description": _normalize_text(row.get("sku_description")),
                "overlay_category": _normalize_text(row.get("overlay_category")),
                "rule_family_candidate": _normalize_text(row.get("rule_family_candidate")),
                "review_signal_score": _to_float(row.get("review_signal_score")),
                "review_signal_label": _normalize_text(row.get("review_signal_label")),
                "actual_units": row.get("actual_units"),
                "expected_promo_demand": _to_float(row.get("expected_promo_demand")),
                "absolute_error_units": _to_float(row.get("absolute_error_units")),
                "actual_gross_profit": _to_float(row.get("actual_gross_profit")),
                "capital_left_value": _to_float(row.get("capital_left_value")),
                "production_order_change_flag": _to_int(row.get("production_order_change_flag")),
                "stage_12_change_flag": _to_int(row.get("stage_12_change_flag")),
                "quarantine_flag": _to_int(row.get("quarantine_flag")),
                "calibration_candidate_tier": tier,
                "calibration_priority_score": priority_score,
                "repeat_evidence_required_flag": int(repeat_evidence_required_flag),
                "calibration_candidate_status": status,
                "row_recommendation": (
                    "Carry into repeat-evidence pack next."
                    if tier in {
                        CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST,
                        CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE,
                        CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY,
                    }
                    else "Do not promote past diagnostics-only review."
                ),
                "calibration_notes": notes,
            }
        )
    classified = pd.DataFrame(records, columns=ROWS_COLUMNS)
    classified = classified.sort_values(
        by=[
            "calibration_candidate_tier",
            "calibration_priority_score",
            "review_signal_score",
            "actual_gross_profit",
            "sku_number",
        ],
        ascending=[True, False, False, False, True],
        kind="stable",
        key=lambda series: (
            series.map(TIER_PRIORITY) if series.name == "calibration_candidate_tier" else series
        ),
    ).reset_index(drop=True)
    candidate_rows = classified.loc[
        classified["calibration_candidate_tier"].isin(
            {
                CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST,
                CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE,
                CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY,
            }
        )
    ].reset_index(drop=True)
    deferred_or_rejected = classified.loc[
        classified["calibration_candidate_tier"].isin(
            {
                CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL,
                CALIBRATION_CANDIDATE_REJECT_GUARDRAIL_OR_ORDER_RISK,
            }
        )
    ].reset_index(drop=True)
    return candidate_rows, deferred_or_rejected


def _dominant_family_tier(group: pd.DataFrame) -> str:
    counts = {
        tier: int(group["calibration_candidate_tier"].eq(tier).sum())
        for tier in TIER_PRIORITY
    }
    for tier in (
        CALIBRATION_CANDIDATE_REJECT_GUARDRAIL_OR_ORDER_RISK,
        CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST,
        CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE,
        CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY,
        CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL,
    ):
        if counts[tier] > 0:
            return tier
    return CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL


def _build_by_rule_family_frame(
    classified_rows_frame: pd.DataFrame,
    *,
    input_review_rows: int,
    repeat_evidence_required_flag: int,
) -> pd.DataFrame:
    if classified_rows_frame.empty:
        return pd.DataFrame(columns=BY_RULE_FAMILY_COLUMNS)
    rows: list[dict[str, object]] = []
    for rule_family, group in classified_rows_frame.groupby("rule_family_candidate", sort=False):
        tier_1_count = int(group["calibration_candidate_tier"].eq(CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST).sum())
        tier_2_count = int(group["calibration_candidate_tier"].eq(CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE).sum())
        tier_3_count = int(group["calibration_candidate_tier"].eq(CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY).sum())
        deferred_count = int(group["calibration_candidate_tier"].eq(CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL).sum())
        rejected_count = int(group["calibration_candidate_tier"].eq(CALIBRATION_CANDIDATE_REJECT_GUARDRAIL_OR_ORDER_RISK).sum())
        candidate_row_count = tier_1_count + tier_2_count + tier_3_count
        family_priority_score = round(float(_to_numeric(group.get("calibration_priority_score")).fillna(0.0).mean()), 4)
        family_readiness_tier = _dominant_family_tier(group)
        rows.append(
            {
                "rule_family_candidate": _normalize_text(rule_family),
                "review_row_count": len(group.index),
                "candidate_row_count": candidate_row_count,
                "tier_1_count": tier_1_count,
                "tier_2_count": tier_2_count,
                "tier_3_count": tier_3_count,
                "deferred_count": deferred_count,
                "rejected_count": rejected_count,
                "row_share_pct": round(len(group.index) / input_review_rows * 100.0, 2) if input_review_rows else 0.0,
                "mean_review_signal_score": round(float(_to_numeric(group.get("review_signal_score")).fillna(0.0).mean()), 4),
                "mean_actual_gross_profit": round(float(_to_numeric(group.get("actual_gross_profit")).fillna(0.0).mean()), 4),
                "mean_capital_left_value": round(float(_to_numeric(group.get("capital_left_value")).fillna(0.0).mean()), 4),
                "sample_skus": _sample_values(group.get("sku_number")),
                "family_priority_score": family_priority_score,
                "family_readiness_tier": family_readiness_tier,
                "repeat_evidence_required_flag": int(repeat_evidence_required_flag),
                "quality_notes": (
                    "Strongest candidate family for diagnostics-only repeat-evidence authoring."
                    if family_readiness_tier == CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST
                    else "Retain for diagnostics-only repeat-evidence or operator review, not live calibration promotion."
                    if family_readiness_tier in {
                        CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE,
                        CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY,
                    }
                    else "Do not promote beyond diagnostics-only review on the current evidence."
                ),
            }
        )
    frame = pd.DataFrame(rows, columns=BY_RULE_FAMILY_COLUMNS)
    return frame.sort_values(
        by=["tier_1_count", "candidate_row_count", "family_priority_score", "rule_family_candidate"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_by_category_frame(
    classified_rows_frame: pd.DataFrame,
    *,
    input_review_rows: int,
    repeat_evidence_required_flag: int,
) -> pd.DataFrame:
    if classified_rows_frame.empty:
        return pd.DataFrame(columns=BY_CATEGORY_COLUMNS)
    rows: list[dict[str, object]] = []
    for category, group in classified_rows_frame.groupby("overlay_category", sort=False):
        tier_1_count = int(group["calibration_candidate_tier"].eq(CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST).sum())
        tier_2_count = int(group["calibration_candidate_tier"].eq(CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE).sum())
        tier_3_count = int(group["calibration_candidate_tier"].eq(CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY).sum())
        deferred_count = int(group["calibration_candidate_tier"].eq(CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL).sum())
        rejected_count = int(group["calibration_candidate_tier"].eq(CALIBRATION_CANDIDATE_REJECT_GUARDRAIL_OR_ORDER_RISK).sum())
        candidate_row_count = tier_1_count + tier_2_count + tier_3_count
        category_priority_score = round(float(_to_numeric(group.get("calibration_priority_score")).fillna(0.0).mean()), 4)
        category_readiness_tier = _dominant_family_tier(group)
        rows.append(
            {
                "overlay_category": _normalize_text(category),
                "review_row_count": len(group.index),
                "candidate_row_count": candidate_row_count,
                "tier_1_count": tier_1_count,
                "tier_2_count": tier_2_count,
                "tier_3_count": tier_3_count,
                "deferred_count": deferred_count,
                "rejected_count": rejected_count,
                "row_share_pct": round(len(group.index) / input_review_rows * 100.0, 2) if input_review_rows else 0.0,
                "mean_review_signal_score": round(float(_to_numeric(group.get("review_signal_score")).fillna(0.0).mean()), 4),
                "mean_actual_gross_profit": round(float(_to_numeric(group.get("actual_gross_profit")).fillna(0.0).mean()), 4),
                "mean_capital_left_value": round(float(_to_numeric(group.get("capital_left_value")).fillna(0.0).mean()), 4),
                "sample_skus": _sample_values(group.get("sku_number")),
                "category_priority_score": category_priority_score,
                "category_readiness_tier": category_readiness_tier,
                "repeat_evidence_required_flag": int(repeat_evidence_required_flag),
                "quality_notes": (
                    "Strongest category slice for diagnostics-only repeat-evidence authoring."
                    if category_readiness_tier == CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST
                    else "Retain as a broader or weaker category for diagnostics-only review."
                ),
            }
        )
    frame = pd.DataFrame(rows, columns=BY_CATEGORY_COLUMNS)
    return frame.sort_values(
        by=["tier_1_count", "candidate_row_count", "category_priority_score", "overlay_category"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_priority_queue_frame(candidate_rows_frame: pd.DataFrame) -> pd.DataFrame:
    if candidate_rows_frame.empty:
        return pd.DataFrame(columns=PRIORITY_QUEUE_COLUMNS)
    frame = candidate_rows_frame.sort_values(
        by=[
            "calibration_candidate_tier",
            "calibration_priority_score",
            "review_signal_score",
            "actual_gross_profit",
            "sku_number",
        ],
        ascending=[True, False, False, False, True],
        kind="stable",
        key=lambda series: (
            series.map(TIER_PRIORITY) if series.name == "calibration_candidate_tier" else series
        ),
    ).reset_index(drop=True)
    frame.insert(0, "queue_rank", range(1, len(frame.index) + 1))
    return frame.loc[:, PRIORITY_QUEUE_COLUMNS].copy()


def _contains_disallowed_order_columns(frame: pd.DataFrame) -> bool:
    return bool(DISALLOWED_ORDER_COLUMNS.intersection(set(frame.columns)))


def _strongest_candidate_rule_family(by_rule_family_frame: pd.DataFrame) -> str:
    if by_rule_family_frame.empty:
        return ""
    candidate_families = by_rule_family_frame.loc[
        by_rule_family_frame["candidate_row_count"].astype(int) > 0
    ]
    if candidate_families.empty:
        return ""
    return _normalize_text(candidate_families.iloc[0]["rule_family_candidate"])


def build_promotions_materialized_source_calibration_candidate_pack(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceCalibrationCandidatePackResult:
    packet_root_path = Path(packet_root)
    inspection_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=INSPECTION_FOLDER_NAME,
        required_file_names=REQUIRED_INSPECTION_FILE_NAMES,
        stage_label="action-layer-review-inspection",
    )
    reconstruction_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=RECONSTRUCTION_FOLDER_NAME,
        required_file_names=REQUIRED_RECONSTRUCTION_FILE_NAMES,
        stage_label="action-layer-review-reconstruction",
    )

    inspection_summary_frame = _read_csv(inspection_root / INSPECTION_SUMMARY_FILE_NAME)
    inspection_quality_checks_frame = _read_csv(
        inspection_root / INSPECTION_QUALITY_CHECKS_FILE_NAME
    )
    inspection_by_rule_family_frame = _read_csv(
        inspection_root / INSPECTION_BY_RULE_FAMILY_FILE_NAME
    )
    inspection_by_category_frame = _read_csv(
        inspection_root / INSPECTION_BY_CATEGORY_FILE_NAME
    )
    _read_csv(inspection_root / INSPECTION_TOP_SKUS_FILE_NAME, allow_empty=True)
    inspection_calibration_readiness_frame = _read_csv(
        inspection_root / INSPECTION_CALIBRATION_READINESS_FILE_NAME
    )
    inspection_quarantine_review_frame = _read_csv(
        inspection_root / INSPECTION_QUARANTINE_REVIEW_FILE_NAME,
        allow_empty=True,
    )
    reconstruction_rows_frame = _read_csv(
        reconstruction_root / RECONSTRUCTION_ROWS_FILE_NAME
    )
    reconstruction_quarantine_rows_frame = _read_csv(
        reconstruction_root / RECONSTRUCTION_QUARANTINE_FILE_NAME,
        allow_empty=True,
    )

    summary_metrics = _metric_lookup(inspection_summary_frame)
    quality_lookup = _quality_lookup(inspection_quality_checks_frame)
    readiness_lookup = _metric_lookup(
        inspection_calibration_readiness_frame.rename(
            columns={"readiness_metric": "metric_name", "metric_value": "metric_value"}
        )
        if not inspection_calibration_readiness_frame.empty
        else pd.DataFrame(columns=["metric_name", "metric_value"])
    )
    selection = _selection_from_inputs(
        requested_promotion_key=promotion_key,
        summary_metrics=summary_metrics,
        rows_frame=reconstruction_rows_frame,
    )

    reconstruction_rows_frame = _filter_for_promotion(
        reconstruction_rows_frame,
        selection.promotion_key,
    )
    reconstruction_quarantine_rows_frame = _filter_for_promotion(
        reconstruction_quarantine_rows_frame,
        selection.promotion_key,
    )
    inspection_by_rule_family_frame = _filter_for_promotion(
        inspection_by_rule_family_frame,
        selection.promotion_key,
    )
    inspection_by_category_frame = _filter_for_promotion(
        inspection_by_category_frame,
        selection.promotion_key,
    )
    inspection_quarantine_review_frame = _filter_for_promotion(
        inspection_quarantine_review_frame,
        selection.promotion_key,
    )

    inspection_status = _normalize_text(summary_metrics.get("INSPECTION_STATUS", ""))
    input_review_rows = len(reconstruction_rows_frame.index)
    quarantine_row_count = len(reconstruction_quarantine_rows_frame.index)
    production_guardrail_status = _normalize_text(
        summary_metrics.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL")
    ) or "FAIL"
    stage12_guardrail_status = _normalize_text(
        summary_metrics.get("STAGE12_GUARDRAIL_STATUS", "FAIL")
    ) or "FAIL"
    repeat_evidence_required_flag = _to_int(
        summary_metrics.get(
            "REPEAT_EVIDENCE_REQUIRED_FLAG",
            readiness_lookup.get("REPEAT_EVIDENCE_REQUIRED_FLAG", 1),
        ),
        default=1,
    )

    quarantine_numbers = set(
        _to_numeric(
            reconstruction_quarantine_rows_frame.get("source_row_number", pd.Series(dtype="object"))
        )
        .fillna(0)
        .astype(int)
        .tolist()
    )
    review_row_ids = set(
        _to_numeric(
            reconstruction_rows_frame.get("source_row_id", pd.Series(dtype="object"))
        )
        .fillna(0)
        .astype(int)
        .tolist()
    )
    no_quarantine_rows_included_flag = int(not bool(quarantine_numbers.intersection(review_row_ids)))

    blocked_guardrail = (
        production_guardrail_status != "PASS"
        or stage12_guardrail_status != "PASS"
        or quality_lookup.get("PRODUCTION_GUARDRAIL_PASS", "FAIL") != "PASS"
        or quality_lookup.get("STAGE12_GUARDRAIL_PASS", "FAIL") != "PASS"
    )
    blocked_order_risk = (
        inspection_status not in READY_INSPECTION_STATUSES
        or quality_lookup.get("NO_ORDER_RECOMMENDATION_FIELDS_GENERATED", "FAIL") != "PASS"
        or quality_lookup.get("REVIEW_ONLY_OUTPUT_CONFIRMED", "FAIL") != "PASS"
        or _contains_disallowed_order_columns(reconstruction_rows_frame)
    )

    family_lookup = _aggregate_lookup(inspection_by_rule_family_frame, "rule_family_candidate")
    category_lookup = _aggregate_lookup(inspection_by_category_frame, "overlay_category")
    strongest_rule_family = _normalize_text(
        summary_metrics.get("STRONGEST_RULE_FAMILY", "")
    )

    candidate_rows_frame, rejected_or_deferred_rows_frame = _build_row_frames(
        reconstruction_rows_frame,
        family_lookup=family_lookup,
        category_lookup=category_lookup,
        strongest_rule_family=strongest_rule_family,
        blocked_order_risk=blocked_order_risk,
        blocked_guardrail=blocked_guardrail,
        repeat_evidence_required_flag=repeat_evidence_required_flag,
    )
    classified_rows_frame = pd.concat(
        [candidate_rows_frame, rejected_or_deferred_rows_frame],
        ignore_index=True,
    ).reset_index(drop=True)

    by_rule_family_frame = _build_by_rule_family_frame(
        classified_rows_frame,
        input_review_rows=input_review_rows,
        repeat_evidence_required_flag=repeat_evidence_required_flag,
    )
    by_category_frame = _build_by_category_frame(
        classified_rows_frame,
        input_review_rows=input_review_rows,
        repeat_evidence_required_flag=repeat_evidence_required_flag,
    )
    priority_queue_frame = _build_priority_queue_frame(candidate_rows_frame)

    tier_1_candidate_count = int(
        candidate_rows_frame.get("calibration_candidate_tier", pd.Series(dtype="object"))
        .eq(CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST)
        .sum()
    )
    tier_2_candidate_count = int(
        candidate_rows_frame.get("calibration_candidate_tier", pd.Series(dtype="object"))
        .eq(CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE)
        .sum()
    )
    tier_3_candidate_count = int(
        candidate_rows_frame.get("calibration_candidate_tier", pd.Series(dtype="object"))
        .eq(CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY)
        .sum()
    )
    deferred_count = int(
        rejected_or_deferred_rows_frame.get("calibration_candidate_tier", pd.Series(dtype="object"))
        .eq(CALIBRATION_CANDIDATE_DEFER_NOISY_SIGNAL)
        .sum()
    )
    rejected_count = int(
        rejected_or_deferred_rows_frame.get("calibration_candidate_tier", pd.Series(dtype="object"))
        .eq(CALIBRATION_CANDIDATE_REJECT_GUARDRAIL_OR_ORDER_RISK)
        .sum()
    )
    strongest_candidate_rule_family = _strongest_candidate_rule_family(by_rule_family_frame)
    all_rows_accounted_for_flag = int(
        len(candidate_rows_frame.index) + len(rejected_or_deferred_rows_frame.index)
        == input_review_rows
    )

    if blocked_guardrail:
        candidate_pack_status = CALIBRATION_CANDIDATE_PACK_BLOCKED_GUARDRAIL_FAILURE
    elif blocked_order_risk:
        candidate_pack_status = CALIBRATION_CANDIDATE_PACK_BLOCKED_ORDER_RECOMMENDATION_RISK
    elif repeat_evidence_required_flag == 1:
        candidate_pack_status = CALIBRATION_CANDIDATE_PACK_REQUIRES_REPEAT_EVIDENCE
    elif quarantine_row_count > 0:
        candidate_pack_status = CALIBRATION_CANDIDATE_PACK_READY_WITH_QUARANTINE
    else:
        candidate_pack_status = CALIBRATION_CANDIDATE_PACK_READY

    repeat_evidence_pack_can_be_authored_next = int(
        candidate_pack_status
        in {
            CALIBRATION_CANDIDATE_PACK_READY,
            CALIBRATION_CANDIDATE_PACK_READY_WITH_QUARANTINE,
            CALIBRATION_CANDIDATE_PACK_REQUIRES_REPEAT_EVIDENCE,
        }
    )

    if candidate_pack_status == CALIBRATION_CANDIDATE_PACK_BLOCKED_GUARDRAIL_FAILURE:
        recommendation = (
            "Keep calibration candidate work blocked. Repair production-order or Stage 12 guardrail failures before authoring any repeat-evidence pack."
        )
    elif candidate_pack_status == CALIBRATION_CANDIDATE_PACK_BLOCKED_ORDER_RECOMMENDATION_RISK:
        recommendation = (
            "Keep calibration candidate work blocked. Remove order-recommendation risk and preserve review-only output before proceeding."
        )
    else:
        recommendation = (
            "Author a diagnostics-only repeat-evidence pack next across more promotions. Keep recalibration, shadow simulation, repeat-evidence execution, training, production ordering, and Stage 12 unchanged in this stage."
        )

    validation_frame = pd.DataFrame(
        [
            _validation_row(
                "INPUT_REVIEW_ROWS_PRESENT",
                "PASS" if input_review_rows > 0 else "FAIL",
                int(input_review_rows > 0),
                f"input_review_rows={input_review_rows}",
            ),
            _validation_row(
                "QUARANTINE_ROWS_PRESENT",
                "PASS" if quarantine_row_count >= 0 else "FAIL",
                1,
                f"quarantine_rows={quarantine_row_count}",
            ),
            _validation_row(
                "ALL_INPUT_ROWS_ACCOUNTED_FOR",
                "PASS" if all_rows_accounted_for_flag else "FAIL",
                all_rows_accounted_for_flag,
                (
                    f"candidate_rows={len(candidate_rows_frame.index)}, deferred_or_rejected_rows={len(rejected_or_deferred_rows_frame.index)}, input_review_rows={input_review_rows}"
                ),
            ),
            _validation_row(
                "NO_QUARANTINE_ROWS_INCLUDED",
                "PASS" if no_quarantine_rows_included_flag else "FAIL",
                no_quarantine_rows_included_flag,
                "Quarantine row 48 remains separate from calibration candidate rows.",
            ),
            _validation_row(
                "NO_ORDER_RECOMMENDATION_FIELDS_GENERATED",
                "PASS" if not _contains_disallowed_order_columns(classified_rows_frame) else "FAIL",
                int(not _contains_disallowed_order_columns(classified_rows_frame)),
                "Candidate-pack outputs remain review-only and exclude order recommendation fields.",
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
                "CALIBRATION_REMAINS_BLOCKED",
                "PASS",
                1,
                "This pack is diagnostics-only and does not recalibrate action-layer logic.",
            ),
            _validation_row(
                "SHADOW_SIMULATION_REMAINS_BLOCKED",
                "PASS",
                1,
                "This pack does not run shadow-vs-baseline simulation.",
            ),
            _validation_row(
                "TRAINING_REMAINS_BLOCKED",
                "PASS",
                1,
                "This pack does not start training.",
            ),
            _validation_row(
                "REPEAT_EVIDENCE_REQUIRED_FLAG_SET",
                "PASS" if repeat_evidence_required_flag == 1 else "PASS",
                int(repeat_evidence_required_flag == 1),
                f"repeat_evidence_required_flag={repeat_evidence_required_flag}",
            ),
        ],
        columns=VALIDATION_COLUMNS,
    )

    summary_frame = pd.DataFrame(
        [
            _summary_row(
                "SELECTED_PROMOTION",
                selection.promotion_key,
                "Promotion selected for the diagnostics-only calibration candidate pack.",
            ),
            _summary_row(
                "CANDIDATE_PACK_STATUS",
                candidate_pack_status,
                "Overall diagnostics-only calibration candidate pack status.",
            ),
            _summary_row(
                "INPUT_REVIEW_ROWS",
                input_review_rows,
                "Action-layer review rows received from reconstruction.",
            ),
            _summary_row(
                "TIER_1_CANDIDATE_COUNT",
                tier_1_candidate_count,
                "Highest-priority diagnostics-only calibration research rows.",
            ),
            _summary_row(
                "TIER_2_CANDIDATE_COUNT",
                tier_2_candidate_count,
                "Useful rows that still need repeat evidence.",
            ),
            _summary_row(
                "TIER_3_CANDIDATE_COUNT",
                tier_3_candidate_count,
                "Operator-review-only rows retained for context.",
            ),
            _summary_row(
                "DEFERRED_COUNT",
                deferred_count,
                "Rows deferred for noisy or weak signal.",
            ),
            _summary_row(
                "REJECTED_COUNT",
                rejected_count,
                "Rows rejected for guardrail or order-risk reasons.",
            ),
            _summary_row(
                "STRONGEST_CANDIDATE_RULE_FAMILY",
                strongest_candidate_rule_family,
                "Strongest rule family retained in the candidate pack.",
            ),
            _summary_row(
                "REPEAT_EVIDENCE_REQUIRED_FLAG",
                repeat_evidence_required_flag,
                "Calibration remains blocked until repeat evidence exists across more promotions.",
            ),
            _summary_row(
                "QUARANTINE_ROW_COUNT",
                quarantine_row_count,
                "Quarantine rows preserved separately and excluded from candidate rows.",
            ),
            _summary_row(
                "PRODUCTION_GUARDRAIL_STATUS",
                production_guardrail_status,
                "Production ordering logic remains unchanged.",
            ),
            _summary_row(
                "STAGE12_GUARDRAIL_STATUS",
                stage12_guardrail_status,
                "Stage 12 remains unchanged.",
            ),
            _summary_row(
                "REPEAT_EVIDENCE_PACK_CAN_BE_AUTHORED_NEXT",
                repeat_evidence_pack_can_be_authored_next,
                "Whether the next diagnostics-only stage can author a repeat-evidence pack.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Calibration Candidate Pack",
            "",
            "This is a diagnostics-only calibration candidate pack built from the inspected action-layer review surface.",
            "This does not recalibrate action-layer logic.",
            "This does not run shadow-vs-baseline simulation.",
            "This does not run repeat-evidence yet.",
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
            f"Candidate pack status: {candidate_pack_status}",
            f"Input review rows: {input_review_rows}",
            f"Tier 1 candidate count: {tier_1_candidate_count}",
            f"Tier 2 candidate count: {tier_2_candidate_count}",
            f"Tier 3 candidate count: {tier_3_candidate_count}",
            f"Deferred count: {deferred_count}",
            f"Rejected count: {rejected_count}",
            f"Strongest candidate rule family: {strongest_candidate_rule_family}",
            f"Repeat-evidence required flag: {repeat_evidence_required_flag}",
            f"Quarantine row count: {quarantine_row_count}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Repeat-evidence pack can be authored next: {repeat_evidence_pack_can_be_authored_next}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()

    return PromotionsMaterializedSourceCalibrationCandidatePackResult(
        selected_promotion=selection,
        candidate_pack_status=candidate_pack_status,
        input_review_rows=input_review_rows,
        tier_1_candidate_count=tier_1_candidate_count,
        tier_2_candidate_count=tier_2_candidate_count,
        tier_3_candidate_count=tier_3_candidate_count,
        deferred_count=deferred_count,
        rejected_count=rejected_count,
        strongest_candidate_rule_family=strongest_candidate_rule_family,
        repeat_evidence_required_flag=repeat_evidence_required_flag,
        quarantine_row_count=quarantine_row_count,
        production_guardrail_status=production_guardrail_status,
        stage12_guardrail_status=stage12_guardrail_status,
        repeat_evidence_pack_can_be_authored_next=repeat_evidence_pack_can_be_authored_next,
        candidate_rows_frame=candidate_rows_frame,
        by_rule_family_frame=by_rule_family_frame,
        by_category_frame=by_category_frame,
        priority_queue_frame=priority_queue_frame,
        rejected_or_deferred_rows_frame=rejected_or_deferred_rows_frame,
        validation_frame=validation_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
        recommendation=recommendation,
    )


def write_promotions_materialized_source_calibration_candidate_pack(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceCalibrationCandidatePackArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = (
        Path(output_root)
        if output_root is not None
        else packet_root_path / OUTPUT_FOLDER_NAME
    )
    result = build_promotions_materialized_source_calibration_candidate_pack(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    rows_csv_path = output_root_path / "calibration_candidate_pack_rows.csv"
    by_rule_family_csv_path = output_root_path / "calibration_candidate_pack_by_rule_family.csv"
    by_category_csv_path = output_root_path / "calibration_candidate_pack_by_category.csv"
    priority_queue_csv_path = output_root_path / "calibration_candidate_pack_priority_queue.csv"
    rejected_or_deferred_csv_path = (
        output_root_path / "calibration_candidate_pack_rejected_or_deferred_rows.csv"
    )
    validation_csv_path = output_root_path / "calibration_candidate_pack_validation.csv"
    summary_csv_path = output_root_path / "calibration_candidate_pack_summary.csv"
    memo_md_path = output_root_path / "calibration_candidate_pack_memo.md"

    result.candidate_rows_frame.to_csv(rows_csv_path, index=False)
    result.by_rule_family_frame.to_csv(by_rule_family_csv_path, index=False)
    result.by_category_frame.to_csv(by_category_csv_path, index=False)
    result.priority_queue_frame.to_csv(priority_queue_csv_path, index=False)
    result.rejected_or_deferred_rows_frame.to_csv(rejected_or_deferred_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceCalibrationCandidatePackArtifacts(
        output_root=str(output_root_path),
        rows_csv_path=str(rows_csv_path),
        by_rule_family_csv_path=str(by_rule_family_csv_path),
        by_category_csv_path=str(by_category_csv_path),
        priority_queue_csv_path=str(priority_queue_csv_path),
        rejected_or_deferred_csv_path=str(rejected_or_deferred_csv_path),
        validation_csv_path=str(validation_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
        selected_promotion=result.selected_promotion.promotion_key,
        candidate_pack_status=result.candidate_pack_status,
        input_review_rows=result.input_review_rows,
        tier_1_candidate_count=result.tier_1_candidate_count,
        tier_2_candidate_count=result.tier_2_candidate_count,
        tier_3_candidate_count=result.tier_3_candidate_count,
        deferred_count=result.deferred_count,
        rejected_count=result.rejected_count,
        strongest_candidate_rule_family=result.strongest_candidate_rule_family,
        repeat_evidence_required_flag=result.repeat_evidence_required_flag,
        quarantine_row_count=result.quarantine_row_count,
        production_guardrail_status=result.production_guardrail_status,
        stage12_guardrail_status=result.stage12_guardrail_status,
        repeat_evidence_pack_can_be_authored_next=result.repeat_evidence_pack_can_be_authored_next,
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only calibration candidate pack."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_calibration_candidate_pack(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    print("selected_promotion", artifacts.selected_promotion)
    print("candidate_pack_status", artifacts.candidate_pack_status)
    print("input_review_rows", artifacts.input_review_rows)
    print("tier_1_candidate_count", artifacts.tier_1_candidate_count)
    print("tier_2_candidate_count", artifacts.tier_2_candidate_count)
    print("tier_3_candidate_count", artifacts.tier_3_candidate_count)
    print("deferred_count", artifacts.deferred_count)
    print("rejected_count", artifacts.rejected_count)
    print("strongest_candidate_rule_family", artifacts.strongest_candidate_rule_family)
    print("repeat_evidence_required_flag", artifacts.repeat_evidence_required_flag)
    print("quarantine_row_count", artifacts.quarantine_row_count)
    print("production_guardrail_status", artifacts.production_guardrail_status)
    print("stage12_guardrail_status", artifacts.stage12_guardrail_status)
    print(
        "repeat_evidence_pack_can_be_authored_next",
        artifacts.repeat_evidence_pack_can_be_authored_next,
    )
    print("recommendation", artifacts.recommendation)
    print("calibration_candidate_pack_rows", artifacts.rows_csv_path)
    print(
        "calibration_candidate_pack_by_rule_family",
        artifacts.by_rule_family_csv_path,
    )
    print("calibration_candidate_pack_by_category", artifacts.by_category_csv_path)
    print("calibration_candidate_pack_priority_queue", artifacts.priority_queue_csv_path)
    print(
        "calibration_candidate_pack_rejected_or_deferred_rows",
        artifacts.rejected_or_deferred_csv_path,
    )
    print("calibration_candidate_pack_validation", artifacts.validation_csv_path)
    print("calibration_candidate_pack_summary", artifacts.summary_csv_path)
    print("calibration_candidate_pack_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())