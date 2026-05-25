from __future__ import annotations

"""Authoritative post-publication outcome attribution and recommendation learning seam."""

from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional

import pandas as pd

from runtime.promotions.commercial_change_explainer import (
    ACTION_NO_ACTION_DUPLICATE,
    ACTION_REVIEW_NOW,
)

ATTRIBUTION_READY = "ATTRIBUTION_READY"
ATTRIBUTION_NOT_YET_MATURE = "ATTRIBUTION_NOT_YET_MATURE"
ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA = "ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA"
ATTRIBUTION_BLOCKED_INCONSISTENT_KEYS = "ATTRIBUTION_BLOCKED_INCONSISTENT_KEYS"
ATTRIBUTION_EXCLUDED_DUPLICATE_ONLY = "ATTRIBUTION_EXCLUDED_DUPLICATE_ONLY"
ATTRIBUTION_EXCLUDED_REVIEW_ONLY = "ATTRIBUTION_EXCLUDED_REVIEW_ONLY"

EFFECTIVE_STRONG = "EFFECTIVE_STRONG"
EFFECTIVE_MODERATE = "EFFECTIVE_MODERATE"
NEUTRAL = "NEUTRAL"
INEFFECTIVE = "INEFFECTIVE"
HARMFUL = "HARMFUL"
INCONCLUSIVE = "INCONCLUSIVE"

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_NONE = "NONE"

LEARNING_SIGNAL_STRONG = "LEARNING_SIGNAL_STRONG"
LEARNING_SIGNAL_MODERATE = "LEARNING_SIGNAL_MODERATE"
LEARNING_SIGNAL_WEAK = "LEARNING_SIGNAL_WEAK"
LEARNING_SIGNAL_NOT_READY = "LEARNING_SIGNAL_NOT_READY"

REALIZED_POSITIVE = "REALIZED_POSITIVE"
REALIZED_NEUTRAL = "REALIZED_NEUTRAL"
REALIZED_NEGATIVE = "REALIZED_NEGATIVE"
REALIZED_INCONCLUSIVE = "REALIZED_INCONCLUSIVE"


@dataclass(frozen=True)
class RecommendationEffectivenessSummary:
    total_rows_evaluated: int
    attribution_ready_count: int
    attribution_not_yet_mature_count: int
    blocked_missing_outcome_data_count: int
    effective_strong_count: int
    effective_moderate_count: int
    neutral_count: int
    ineffective_count: int
    harmful_count: int
    inconclusive_count: int
    average_effectiveness_score: Optional[float]
    publish_now_average_effectiveness_score: Optional[float]
    review_now_average_effectiveness_score: Optional[float]
    attribution_effective_count: int
    attribution_harmful_count: int
    attribution_inconclusive_count: int
    commercial_learning_signal_strength_class: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialOutcomeAttributionArtifacts:
    attribution: pd.DataFrame
    recommendation_effectiveness_summary: RecommendationEffectivenessSummary
    recommendation_effectiveness_by_reason: pd.DataFrame
    recommendation_learning_priority_queue: pd.DataFrame


def build_commercial_outcome_attribution_artifacts(
    *,
    as_of_date: str,
    current_store_prediction_csv_path: str,
    commercial_change_explanations: pd.DataFrame,
    current_freshness_class: str,
    current_commercial_outcome_class: str,
    duplicate_registry_skip_count: int,
) -> CommercialOutcomeAttributionArtifacts:
    current_frame = pd.read_csv(current_store_prediction_csv_path, encoding="utf-8")
    attribution = _build_attribution_frame(
        as_of_date=as_of_date,
        current_frame=current_frame,
        commercial_change_explanations=commercial_change_explanations,
        current_freshness_class=current_freshness_class,
        current_commercial_outcome_class=current_commercial_outcome_class,
        duplicate_registry_skip_count=int(duplicate_registry_skip_count),
    )
    summary = _build_effectiveness_summary(attribution)
    by_reason = _build_effectiveness_by_reason(attribution)
    learning_queue = _build_learning_priority_queue(attribution)

    _validate_attribution_consistency(
        attribution=attribution,
        summary=summary,
        learning_queue=learning_queue,
    )

    return CommercialOutcomeAttributionArtifacts(
        attribution=attribution,
        recommendation_effectiveness_summary=summary,
        recommendation_effectiveness_by_reason=by_reason,
        recommendation_learning_priority_queue=learning_queue,
    )


def _build_attribution_frame(
    *,
    as_of_date: str,
    current_frame: pd.DataFrame,
    commercial_change_explanations: pd.DataFrame,
    current_freshness_class: str,
    current_commercial_outcome_class: str,
    duplicate_registry_skip_count: int,
) -> pd.DataFrame:
    current = _normalize_current_frame(current_frame)
    explanations = _normalize_explanations_frame(commercial_change_explanations)

    merged = current.merge(
        explanations,
        on=["store_number", "sku_number", "promotion_start_date", "promotion_end_date"],
        how="left",
        suffixes=("", "_expl"),
        indicator=True,
    )

    resolved_as_of_date = _parse_date(as_of_date)
    rows: list[dict[str, object]] = []
    for _, row in merged.iterrows():
        publish_eligibility = _nullable_string(row.get("publish_eligibility_class"))
        operator_action_class = _nullable_string(row.get("operator_action_class")) or "UNKNOWN"
        reason_code = _nullable_string(row.get("row_change_reason_code")) or "unavailable"

        recommended_units = _nullable_float(row.get("recommended_order_units"))
        actual_units = _nullable_float(row.get("actual_units_sold_if_available"))
        actual_sales = _nullable_float(row.get("actual_sales_if_available"))
        actual_margin = _nullable_float(row.get("actual_margin_if_available"))
        expected_sales = _nullable_float(row.get("expected_sales_if_available"))
        expected_margin = _nullable_float(row.get("expected_margin_if_available"))

        units_delta = (
            actual_units - recommended_units
            if actual_units is not None and recommended_units is not None
            else None
        )
        sales_delta = (
            actual_sales - expected_sales
            if actual_sales is not None and expected_sales is not None
            else None
        )
        margin_delta = (
            actual_margin - expected_margin
            if actual_margin is not None and expected_margin is not None
            else None
        )

        promotion_end = _parse_date(_nullable_string(row.get("promotion_end_date")))
        window_complete = bool(
            resolved_as_of_date is not None
            and promotion_end is not None
            and resolved_as_of_date >= promotion_end
        )

        recommendation_kept_flag, recommendation_overrode_flag = _resolve_override_state(row)

        inconsistent_key = str(row.get("_merge", "")) != "both"
        duplicate_excluded = operator_action_class == ACTION_NO_ACTION_DUPLICATE or (
            current_freshness_class == "NO_NEW_PUBLICATIONS_DUPLICATE_ONLY"
            and duplicate_registry_skip_count > 0
        )
        review_only_excluded = (
            operator_action_class == ACTION_REVIEW_NOW
            and str(publish_eligibility or "").strip().lower().startswith("review")
        )

        status: str
        attribution_reason_code: str
        attribution_reason: str
        realized_outcome_class: str
        effectiveness_class: str
        effectiveness_score: Optional[int]
        confidence_class: str

        if inconsistent_key:
            status = ATTRIBUTION_BLOCKED_INCONSISTENT_KEYS
            attribution_reason_code = "inconsistent_row_key_missing_explanation_match"
            attribution_reason = "Row key did not match exactly between current outputs and explainability artifacts."
            realized_outcome_class = REALIZED_INCONCLUSIVE
            effectiveness_class = INCONCLUSIVE
            effectiveness_score = None
            confidence_class = CONFIDENCE_NONE
        elif duplicate_excluded:
            status = ATTRIBUTION_EXCLUDED_DUPLICATE_ONLY
            attribution_reason_code = "excluded_duplicate_only_cycle"
            attribution_reason = "Row was duplicate-protected and excluded from new publication attribution."
            realized_outcome_class = REALIZED_INCONCLUSIVE
            effectiveness_class = INCONCLUSIVE
            effectiveness_score = None
            confidence_class = CONFIDENCE_NONE
        elif review_only_excluded:
            status = ATTRIBUTION_EXCLUDED_REVIEW_ONLY
            attribution_reason_code = "excluded_review_only_row"
            attribution_reason = "Row remained review-only and was not treated as a governed publish-now recommendation."
            realized_outcome_class = REALIZED_INCONCLUSIVE
            effectiveness_class = INCONCLUSIVE
            effectiveness_score = None
            confidence_class = CONFIDENCE_NONE
        elif not window_complete:
            status = ATTRIBUTION_NOT_YET_MATURE
            attribution_reason_code = "window_not_complete_early_read_only"
            attribution_reason = "Attribution window is not complete yet, so only early-read diagnostics are available."
            realized_outcome_class = REALIZED_INCONCLUSIVE
            effectiveness_class = INCONCLUSIVE
            effectiveness_score = None
            confidence_class = CONFIDENCE_NONE
        else:
            available_delta_count = sum(v is not None for v in (units_delta, sales_delta, margin_delta))
            if available_delta_count == 0:
                status = ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA
                attribution_reason_code = "missing_realized_outcome_or_expectation_baselines"
                attribution_reason = (
                    "Attribution window is complete but realized outcome baselines are missing, so effectiveness cannot be scored."
                )
                realized_outcome_class = REALIZED_INCONCLUSIVE
                effectiveness_class = INCONCLUSIVE
                effectiveness_score = None
                confidence_class = CONFIDENCE_NONE
            elif recommendation_overrode_flag is True:
                status = ATTRIBUTION_READY
                attribution_reason_code = "ready_but_recommendation_overridden"
                attribution_reason = "Realized outcomes are present, but recommendation override signal prevents governed effectiveness attribution."
                realized_outcome_class = REALIZED_INCONCLUSIVE
                effectiveness_class = INCONCLUSIVE
                effectiveness_score = None
                confidence_class = CONFIDENCE_LOW
            else:
                status = ATTRIBUTION_READY
                attribution_reason_code = "ready_governed_realized_outcomes_available"
                attribution_reason = "Realized outcomes and comparison baselines are available for governed recommendation evaluation."
                effectiveness_score = _score_effectiveness(
                    recommended_units=recommended_units,
                    units_delta=units_delta,
                    sales_delta=sales_delta,
                    expected_sales=expected_sales,
                    margin_delta=margin_delta,
                    expected_margin=expected_margin,
                )
                effectiveness_class = _effectiveness_class(effectiveness_score)
                realized_outcome_class = _realized_outcome_class(effectiveness_score)
                confidence_class = _confidence_class(available_delta_count)

        rows.append(
            {
                "store_number": str(row.get("store_number", "")),
                "sku_number": str(row.get("sku_number", "")),
                "promotion_start_date": str(row.get("promotion_start_date", "")),
                "promotion_end_date": str(row.get("promotion_end_date", "")),
                "decision_recommendation": _nullable_string(row.get("decision_recommendation")),
                "row_change_reason_code": reason_code,
                "operator_action_class": operator_action_class,
                "publish_eligibility_class": publish_eligibility,
                "demand_evidence_class": _nullable_string(row.get("demand_evidence_class")),
                "recommended_order_units": recommended_units,
                "actual_units_sold_if_available": actual_units,
                "actual_sales_if_available": actual_sales,
                "actual_margin_if_available": actual_margin,
                "attribution_status": status,
                "attribution_reason_code": attribution_reason_code,
                "attribution_reason": attribution_reason,
                "realized_outcome_class": realized_outcome_class,
                "realized_units_delta_vs_recommendation": units_delta,
                "realized_sales_delta_vs_expectation": sales_delta,
                "realized_margin_delta_vs_expectation": margin_delta,
                "recommendation_effectiveness_class": effectiveness_class,
                "recommendation_effectiveness_score": effectiveness_score,
                "recommendation_kept_flag": recommendation_kept_flag,
                "recommendation_overrode_flag": recommendation_overrode_flag,
                "attribution_confidence_class": confidence_class,
                "attribution_window_complete_flag": window_complete,
                "_current_commercial_outcome_class": current_commercial_outcome_class,
            }
        )

    return pd.DataFrame(rows, columns=_attribution_columns())


def _build_effectiveness_summary(attribution: pd.DataFrame) -> RecommendationEffectivenessSummary:
    ready = attribution[attribution["attribution_status"] == ATTRIBUTION_READY]
    ready_scores = pd.to_numeric(ready["recommendation_effectiveness_score"], errors="coerce")

    publish_scores = pd.to_numeric(
        attribution.loc[
            attribution["operator_action_class"] == "ACTION_PUBLISH_NOW",
            "recommendation_effectiveness_score",
        ],
        errors="coerce",
    )
    review_scores = pd.to_numeric(
        attribution.loc[
            attribution["operator_action_class"] == ACTION_REVIEW_NOW,
            "recommendation_effectiveness_score",
        ],
        errors="coerce",
    )

    effective_strong_count = int((attribution["recommendation_effectiveness_class"] == EFFECTIVE_STRONG).sum())
    effective_moderate_count = int((attribution["recommendation_effectiveness_class"] == EFFECTIVE_MODERATE).sum())
    neutral_count = int((attribution["recommendation_effectiveness_class"] == NEUTRAL).sum())
    ineffective_count = int((attribution["recommendation_effectiveness_class"] == INEFFECTIVE).sum())
    harmful_count = int((attribution["recommendation_effectiveness_class"] == HARMFUL).sum())
    inconclusive_count = int((attribution["recommendation_effectiveness_class"] == INCONCLUSIVE).sum())

    summary = RecommendationEffectivenessSummary(
        total_rows_evaluated=int(len(attribution.index)),
        attribution_ready_count=int((attribution["attribution_status"] == ATTRIBUTION_READY).sum()),
        attribution_not_yet_mature_count=int((attribution["attribution_status"] == ATTRIBUTION_NOT_YET_MATURE).sum()),
        blocked_missing_outcome_data_count=int((attribution["attribution_status"] == ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA).sum()),
        effective_strong_count=effective_strong_count,
        effective_moderate_count=effective_moderate_count,
        neutral_count=neutral_count,
        ineffective_count=ineffective_count,
        harmful_count=harmful_count,
        inconclusive_count=inconclusive_count,
        average_effectiveness_score=_mean_or_none(ready_scores),
        publish_now_average_effectiveness_score=_mean_or_none(publish_scores),
        review_now_average_effectiveness_score=_mean_or_none(review_scores),
        attribution_effective_count=effective_strong_count + effective_moderate_count,
        attribution_harmful_count=harmful_count,
        attribution_inconclusive_count=inconclusive_count,
        commercial_learning_signal_strength_class=LEARNING_SIGNAL_NOT_READY,
    )

    return RecommendationEffectivenessSummary(
        **{
            **summary.to_dict(),
            "commercial_learning_signal_strength_class": _classify_learning_signal(
                attribution=attribution,
                summary=summary,
            ),
        }
    )


def _build_effectiveness_by_reason(attribution: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        attribution.groupby(
            [
                "row_change_reason_code",
                "operator_action_class",
                "publish_eligibility_class",
                "demand_evidence_class",
                "recommendation_effectiveness_class",
            ],
            dropna=False,
        )
        .agg(
            row_count=("store_number", "count"),
            average_effectiveness_score=("recommendation_effectiveness_score", "mean"),
        )
        .reset_index()
    )
    grouped["average_effectiveness_score"] = grouped["average_effectiveness_score"].round(4)
    return grouped


def _build_learning_priority_queue(attribution: pd.DataFrame) -> pd.DataFrame:
    ready = attribution[attribution["attribution_status"] == ATTRIBUTION_READY].copy()
    if ready.empty:
        return ready

    surprising_neutral = (
        (ready["recommendation_effectiveness_class"] == NEUTRAL)
        & (ready["attribution_confidence_class"].isin([CONFIDENCE_HIGH, CONFIDENCE_MEDIUM]))
        & (pd.to_numeric(ready["recommendation_effectiveness_score"], errors="coerce").abs() <= 5)
    )

    high_confidence_miss = (
        (ready["recommendation_effectiveness_class"].isin([INEFFECTIVE, HARMFUL]))
        & (ready["attribution_confidence_class"] == CONFIDENCE_HIGH)
    )

    high_confidence_win = (
        (ready["recommendation_effectiveness_class"].isin([EFFECTIVE_STRONG, EFFECTIVE_MODERATE]))
        & (ready["attribution_confidence_class"] == CONFIDENCE_HIGH)
    )

    selected = ready[
        (ready["recommendation_effectiveness_class"].isin([EFFECTIVE_STRONG, HARMFUL]))
        | surprising_neutral
        | high_confidence_miss
        | high_confidence_win
    ].copy()

    if selected.empty:
        return selected

    selected["_confidence_rank"] = selected["attribution_confidence_class"].map(
        {
            CONFIDENCE_HIGH: 3,
            CONFIDENCE_MEDIUM: 2,
            CONFIDENCE_LOW: 1,
            CONFIDENCE_NONE: 0,
        }
    ).fillna(0)
    selected["_score_abs"] = (
        pd.to_numeric(selected["recommendation_effectiveness_score"], errors="coerce")
        .fillna(0.0)
        .abs()
    )

    selected = selected.sort_values(
        by=["_confidence_rank", "_score_abs"],
        ascending=[False, False],
    )

    return selected.drop(columns=["_confidence_rank", "_score_abs"])


def _validate_attribution_consistency(
    *,
    attribution: pd.DataFrame,
    summary: RecommendationEffectivenessSummary,
    learning_queue: pd.DataFrame,
) -> None:
    errors: list[str] = []

    ready_without_support = attribution[
        (attribution["attribution_status"] == ATTRIBUTION_READY)
        & attribution[
            [
                "realized_units_delta_vs_recommendation",
                "realized_sales_delta_vs_expectation",
                "realized_margin_delta_vs_expectation",
            ]
        ]
        .isna()
        .all(axis=1)
    ]
    if not ready_without_support.empty:
        errors.append("ATTRIBUTION_READY rows missing all realized delta support fields")

    mature_but_not_mature_status = attribution[
        (attribution["attribution_window_complete_flag"] == True)
        & (attribution["attribution_status"] == ATTRIBUTION_NOT_YET_MATURE)
    ]
    if not mature_but_not_mature_status.empty:
        errors.append("attribution_window_complete_flag true while attribution_status is ATTRIBUTION_NOT_YET_MATURE")

    blocked_not_inconclusive = attribution[
        attribution["attribution_status"].isin(
            [
                ATTRIBUTION_NOT_YET_MATURE,
                ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA,
                ATTRIBUTION_BLOCKED_INCONSISTENT_KEYS,
                ATTRIBUTION_EXCLUDED_DUPLICATE_ONLY,
                ATTRIBUTION_EXCLUDED_REVIEW_ONLY,
            ]
        )
        & (attribution["recommendation_effectiveness_class"] != INCONCLUSIVE)
    ]
    if not blocked_not_inconclusive.empty:
        errors.append("Blocked/excluded/not-mature rows must have recommendation_effectiveness_class=INCONCLUSIVE")

    ready_rows = attribution[attribution["attribution_status"] == ATTRIBUTION_READY]
    ready_effective_or_harmful_or_inconclusive = int(
        ready_rows["recommendation_effectiveness_class"].isin(
            [EFFECTIVE_STRONG, EFFECTIVE_MODERATE, NEUTRAL, INEFFECTIVE, HARMFUL, INCONCLUSIVE]
        ).sum()
    )
    if ready_effective_or_harmful_or_inconclusive != int(len(ready_rows.index)):
        errors.append("Ready rows are not fully classified by recommendation_effectiveness_class")

    if summary.attribution_harmful_count != int((attribution["recommendation_effectiveness_class"] == HARMFUL).sum()):
        errors.append("attribution_harmful_count does not reconcile")

    if summary.attribution_effective_count != int(
        attribution["recommendation_effectiveness_class"].isin([EFFECTIVE_STRONG, EFFECTIVE_MODERATE]).sum()
    ):
        errors.append("attribution_effective_count does not reconcile")

    if summary.attribution_inconclusive_count != int((attribution["recommendation_effectiveness_class"] == INCONCLUSIVE).sum()):
        errors.append("attribution_inconclusive_count does not reconcile")

    attribution_keys = set(
        attribution.apply(
            lambda r: (
                str(r["store_number"]),
                str(r["sku_number"]),
                str(r["promotion_start_date"]),
                str(r["promotion_end_date"]),
            ),
            axis=1,
        )
    )
    learning_keys = set(
        learning_queue.apply(
            lambda r: (
                str(r["store_number"]),
                str(r["sku_number"]),
                str(r["promotion_start_date"]),
                str(r["promotion_end_date"]),
            ),
            axis=1,
        )
    )
    if not learning_keys.issubset(attribution_keys):
        errors.append("recommendation_learning_priority_queue contains rows not present in commercial_outcome_attribution")

    if errors:
        raise ValueError("Commercial outcome attribution consistency check failed:\n" + "\n".join(errors))


def _normalize_current_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized["store_number"] = normalized.get("store_number", pd.Series(dtype="object")).astype(str)
    normalized["sku_number"] = normalized.get("sku_number", pd.Series(dtype="object")).astype(str)
    normalized["promotion_start_date"] = normalized.get("promotion_start_date", pd.Series(dtype="object")).astype(str)
    normalized["promotion_end_date"] = normalized.get("promotion_end_date", pd.Series(dtype="object")).astype(str)

    normalized["decision_recommendation"] = normalized.get(
        "decision_recommendation", pd.Series("", index=normalized.index)
    ).fillna("").astype(str)
    normalized["publish_eligibility_class"] = normalized.get(
        "publish_eligibility_reason", pd.Series("", index=normalized.index)
    ).fillna("").astype(str)
    normalized["demand_evidence_class"] = normalized.get(
        "demand_evidence_class", pd.Series("", index=normalized.index)
    ).fillna("").astype(str)
    normalized["recommended_order_units"] = pd.to_numeric(
        normalized.get("suggested_order_units", pd.Series(None, index=normalized.index)),
        errors="coerce",
    )

    normalized["actual_units_sold_if_available"] = _coalesce_numeric(
        normalized,
        ["actual_units_sold", "actual_units_sold_promo", "realized_units_sold", "realised_units_sold"],
    )
    normalized["actual_sales_if_available"] = _coalesce_numeric(
        normalized,
        [
            "actual_sales_if_available",
            "actual_sales_ex_gst_promo",
            "actual_sales_ex_gst",
            "actual_sales",
            "realized_sales",
            "realised_sales",
        ],
    )
    normalized["actual_margin_if_available"] = _coalesce_numeric(
        normalized,
        ["actual_margin_if_available", "actual_margin", "actual_margin_promo", "realized_margin", "realised_margin"],
    )
    normalized["expected_sales_if_available"] = _coalesce_numeric(
        normalized,
        ["predicted_sales_total_promo", "expected_sales_total_promo", "expected_sales"],
    )
    normalized["expected_margin_if_available"] = _coalesce_numeric(
        normalized,
        ["predicted_margin_total_promo", "expected_margin_total_promo", "expected_margin"],
    )

    return normalized[
        [
            "store_number",
            "sku_number",
            "promotion_start_date",
            "promotion_end_date",
            "decision_recommendation",
            "publish_eligibility_class",
            "demand_evidence_class",
            "recommended_order_units",
            "actual_units_sold_if_available",
            "actual_sales_if_available",
            "actual_margin_if_available",
            "expected_sales_if_available",
            "expected_margin_if_available",
            "recommendation_kept_flag",
            "recommendation_overrode_flag",
            "operator_override_flag",
        ]
    ].copy() if {"recommendation_kept_flag", "recommendation_overrode_flag", "operator_override_flag"}.issubset(normalized.columns) else _ensure_override_columns(normalized)


def _ensure_override_columns(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    if "recommendation_kept_flag" not in prepared.columns:
        prepared["recommendation_kept_flag"] = None
    if "recommendation_overrode_flag" not in prepared.columns:
        prepared["recommendation_overrode_flag"] = None
    if "operator_override_flag" not in prepared.columns:
        prepared["operator_override_flag"] = None
    return prepared[
        [
            "store_number",
            "sku_number",
            "promotion_start_date",
            "promotion_end_date",
            "decision_recommendation",
            "publish_eligibility_class",
            "demand_evidence_class",
            "recommended_order_units",
            "actual_units_sold_if_available",
            "actual_sales_if_available",
            "actual_margin_if_available",
            "expected_sales_if_available",
            "expected_margin_if_available",
            "recommendation_kept_flag",
            "recommendation_overrode_flag",
            "operator_override_flag",
        ]
    ].copy()


def _normalize_explanations_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    if normalized.empty:
        return pd.DataFrame(
            columns=[
                "store_number",
                "sku_number",
                "promotion_start_date",
                "promotion_end_date",
                "operator_action_class",
                "row_change_reason_code",
            ]
        )

    normalized["store_number"] = normalized.get("store_number", pd.Series(dtype="object")).astype(str)
    normalized["sku_number"] = normalized.get("sku_number", pd.Series(dtype="object")).astype(str)
    normalized["promotion_start_date"] = normalized.get("promotion_start_date", pd.Series(dtype="object")).astype(str)
    normalized["promotion_end_date"] = normalized.get("promotion_end_date", pd.Series(dtype="object")).astype(str)

    return pd.DataFrame(
        {
            "store_number": normalized["store_number"],
            "sku_number": normalized["sku_number"],
            "promotion_start_date": normalized["promotion_start_date"],
            "promotion_end_date": normalized["promotion_end_date"],
            "operator_action_class": normalized.get("operator_action_class", pd.Series("UNKNOWN", index=normalized.index)).fillna("UNKNOWN").astype(str),
            "row_change_reason_code": normalized.get("row_change_reason_code", pd.Series("unavailable", index=normalized.index)).fillna("unavailable").astype(str),
        }
    )


def _coalesce_numeric(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    result = pd.Series([None] * len(frame.index), index=frame.index, dtype="float64")
    for column in columns:
        if column in frame.columns:
            candidate = pd.to_numeric(frame[column], errors="coerce")
            result = result.where(~result.isna(), candidate)
    return result


def _score_effectiveness(
    *,
    recommended_units: Optional[float],
    units_delta: Optional[float],
    sales_delta: Optional[float],
    expected_sales: Optional[float],
    margin_delta: Optional[float],
    expected_margin: Optional[float],
) -> int:
    score = 0.0

    if units_delta is not None:
        units_base = max(abs(recommended_units or 0.0), 1.0)
        score += max(-40.0, min(40.0, (units_delta / units_base) * 40.0))

    if sales_delta is not None:
        sales_base = max(abs(expected_sales or 0.0), 1.0)
        score += max(-30.0, min(30.0, (sales_delta / sales_base) * 30.0))

    if margin_delta is not None:
        margin_base = max(abs(expected_margin or 0.0), 1.0)
        score += max(-30.0, min(30.0, (margin_delta / margin_base) * 30.0))

    return int(max(-100, min(100, round(score))))


def _effectiveness_class(score: int) -> str:
    if score >= 45:
        return EFFECTIVE_STRONG
    if score >= 20:
        return EFFECTIVE_MODERATE
    if score > -15:
        return NEUTRAL
    if score > -40:
        return INEFFECTIVE
    return HARMFUL


def _realized_outcome_class(score: int) -> str:
    if score >= 20:
        return REALIZED_POSITIVE
    if score <= -20:
        return REALIZED_NEGATIVE
    return REALIZED_NEUTRAL


def _confidence_class(available_delta_count: int) -> str:
    if available_delta_count >= 3:
        return CONFIDENCE_HIGH
    if available_delta_count == 2:
        return CONFIDENCE_MEDIUM
    if available_delta_count == 1:
        return CONFIDENCE_LOW
    return CONFIDENCE_NONE


def _classify_learning_signal(
    *,
    attribution: pd.DataFrame,
    summary: RecommendationEffectivenessSummary,
) -> str:
    ready = attribution[attribution["attribution_status"] == ATTRIBUTION_READY]
    ready_count = int(len(ready.index))
    if ready_count < 5:
        return LEARNING_SIGNAL_NOT_READY

    high_conf_ready = int((ready["attribution_confidence_class"] == CONFIDENCE_HIGH).sum())
    high_conf_share = high_conf_ready / max(ready_count, 1)

    breadth = int(
        ready[["row_change_reason_code", "operator_action_class", "demand_evidence_class"]]
        .fillna("unknown")
        .astype(str)
        .drop_duplicates()
        .shape[0]
    )

    outcome_distribution = (
        ready["recommendation_effectiveness_class"].value_counts(normalize=True, dropna=False)
    )
    max_concentration = float(outcome_distribution.max()) if not outcome_distribution.empty else 1.0

    if ready_count >= 20 and high_conf_share >= 0.4 and breadth >= 5 and max_concentration <= 0.85:
        return LEARNING_SIGNAL_STRONG
    if ready_count >= 10 and high_conf_share >= 0.2 and breadth >= 3:
        return LEARNING_SIGNAL_MODERATE

    return LEARNING_SIGNAL_WEAK


def _resolve_override_state(row: pd.Series) -> tuple[Optional[bool], Optional[bool]]:
    explicit_override = _nullable_bool(row.get("recommendation_overrode_flag"))
    explicit_kept = _nullable_bool(row.get("recommendation_kept_flag"))
    operator_override = _nullable_bool(row.get("operator_override_flag"))

    if explicit_override is not None:
        return (not explicit_override, explicit_override)
    if explicit_kept is not None:
        return (explicit_kept, not explicit_kept)
    if operator_override is not None:
        return (not operator_override, operator_override)
    return (None, None)


def _nullable_bool(value: object) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"", "none", "nan"}:
        return None
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _nullable_string(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if text in {"", "None", "nan"}:
        return None
    return text


def _nullable_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value is None or value.strip() == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _mean_or_none(series: pd.Series) -> Optional[float]:
    valid = series.dropna()
    if valid.empty:
        return None
    return float(round(float(valid.mean()), 4))


def _attribution_columns() -> list[str]:
    return [
        "store_number",
        "sku_number",
        "promotion_start_date",
        "promotion_end_date",
        "decision_recommendation",
        "row_change_reason_code",
        "operator_action_class",
        "publish_eligibility_class",
        "demand_evidence_class",
        "recommended_order_units",
        "actual_units_sold_if_available",
        "actual_sales_if_available",
        "actual_margin_if_available",
        "attribution_status",
        "attribution_reason_code",
        "attribution_reason",
        "realized_outcome_class",
        "realized_units_delta_vs_recommendation",
        "realized_sales_delta_vs_expectation",
        "realized_margin_delta_vs_expectation",
        "recommendation_effectiveness_class",
        "recommendation_effectiveness_score",
        "recommendation_kept_flag",
        "recommendation_overrode_flag",
        "attribution_confidence_class",
        "attribution_window_complete_flag",
        "_current_commercial_outcome_class",
    ]
