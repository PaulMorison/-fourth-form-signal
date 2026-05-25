from __future__ import annotations

"""Transparent decision fusion for promotions row-model and cohort evidence.

Canon ownership:
- Combines row-model outputs, cohort expectations, archetype evidence strength,
  and explicit penalty signals into a final transparent decision surface.
- Keeps weighting, disagreement, confidence, and recommendation logic surfaced
  as formula-driven columns rather than a hidden ensemble.
- Does not own model fitting, cohort-history construction, diagnostics
  aggregation, or reporting persistence.
"""

from dataclasses import dataclass

import pandas as pd


_DEFAULT_SPARSE_PENALTY_CURVE = (
    (2, 0.85),
    (4, 0.55),
    (8, 0.25),
    (None, 0.0),
)


@dataclass(frozen=True)
class PromotionDecisionFusionConfig:
    similarity_threshold: float = 0.55
    archetype_confidence_floor: float = 0.45
    row_model_confidence_floor: float = 0.45
    disagreement_moderate_cutoff: float = 0.30
    disagreement_severe_cutoff: float = 0.55
    sparse_history_penalty_curve: tuple[tuple[int | None, float], ...] = _DEFAULT_SPARSE_PENALTY_CURVE
    stable_sample_size_breakpoint: int = 8
    destructive_archetype_cutoff: float = 0.75
    repeatable_winner_cutoff: float = 0.75

    @classmethod
    def from_thresholds(cls, thresholds: dict[str, object]) -> "PromotionDecisionFusionConfig":
        disagreement_cutoffs = thresholds.get("disagreement_penalty_cutoffs", {})
        sparse_curve = thresholds.get("sparse_cohort_penalty_curve", _DEFAULT_SPARSE_PENALTY_CURVE)
        sample_breakpoints = thresholds.get("minimum_archetype_sample_size_breakpoints", {})
        destructive_cutoffs = thresholds.get("destructive_archetype_cutoffs", {})
        repeatable_cutoffs = thresholds.get("repeatable_winner_cutoffs", {})
        return cls(
            similarity_threshold=float(thresholds.get("similarity_threshold", 0.55) or 0.55),
            archetype_confidence_floor=float(
                thresholds.get("archetype_confidence_floor", 0.45) or 0.45
            ),
            row_model_confidence_floor=float(
                thresholds.get("row_model_confidence_floor", 0.45) or 0.45
            ),
            disagreement_moderate_cutoff=float(
                disagreement_cutoffs.get("moderate", 0.30) or 0.30
            ),
            disagreement_severe_cutoff=float(
                disagreement_cutoffs.get("severe", 0.55) or 0.55
            ),
            sparse_history_penalty_curve=tuple(
                (
                    None if breakpoint.get("max_sample_size") is None else int(breakpoint["max_sample_size"]),
                    float(breakpoint.get("penalty", 0.0) or 0.0),
                )
                for breakpoint in sparse_curve
            )
            if isinstance(sparse_curve, list)
            else tuple(sparse_curve),
            stable_sample_size_breakpoint=int(sample_breakpoints.get("stable", 8) or 8),
            destructive_archetype_cutoff=float(
                destructive_cutoffs.get("destructiveness", 0.75) or 0.75
            ),
            repeatable_winner_cutoff=float(
                repeatable_cutoffs.get("repeatability", 0.75) or 0.75
            ),
        )


@dataclass(frozen=True)
class PromotionDecisionFusionResult:
    decision_surface_frame: pd.DataFrame
    metrics: dict[str, object]


class PromotionDecisionFusion:
    """Fuse row-model and cohort evidence into a decision-grade promotions surface."""

    def fuse(
        self,
        frame: pd.DataFrame,
        *,
        config: PromotionDecisionFusionConfig | None = None,
    ) -> PromotionDecisionFusionResult:
        """Attach weighted decision, confidence, alignment, and recommendation columns."""

        resolved_config = config or PromotionDecisionFusionConfig()
        working = frame.copy()
        disagreement_score = build_row_cohort_disagreement_score(working)
        working["row_cohort_disagreement_score"] = disagreement_score.fillna(0.5).clip(lower=0.0, upper=1.0)
        working["decision_alignment_score"] = (1.0 - working["row_cohort_disagreement_score"]).clip(
            lower=0.0,
            upper=1.0,
        )

        row_model_confidence = _series_or_default(working, "row_model_confidence_score")
        sample_size = _series_or_default(working, "nearest_archetype_sample_size")
        similarity = _series_or_default(working, "nearest_archetype_similarity")
        ranking_confidence = _first_present_series(
            working,
            ("nearest_archetype_confidence_score", "archetype_confidence_score"),
        )
        sample_confidence = (sample_size / float(max(resolved_config.stable_sample_size_breakpoint, 1))).clip(
            lower=0.0,
            upper=1.0,
        )
        archetype_confidence = (
            0.45 * similarity.clip(lower=0.0, upper=1.0)
            + 0.30 * ranking_confidence.clip(lower=0.0, upper=1.0)
            + 0.25 * sample_confidence
        ).clip(lower=0.0, upper=1.0)
        working["archetype_confidence_score"] = archetype_confidence

        sparse_history_penalty = _sparse_history_penalty(sample_size, resolved_config)
        sparse_history_penalty = sparse_history_penalty.where(
            _series_or_default(working, "sparse_cohort_flag").fillna(0.0) <= 0.0,
            other=sparse_history_penalty.clip(lower=0.85, upper=1.0),
        )
        working["sparse_history_penalty"] = sparse_history_penalty

        working["instability_penalty"] = (
            0.60 * _first_present_series(
                working,
                ("feature_composite_promo_instability", "avg_zeta_instability"),
            ).clip(lower=0.0, upper=1.0)
            + 0.40 * _first_present_series(
                working,
                ("nearest_archetype_fragility_score", "archetype_fragility_score"),
            ).clip(lower=0.0, upper=1.0)
        ).clip(lower=0.0, upper=1.0)

        row_model_score = _row_model_commercial_score(working)
        cohort_model_score = _cohort_model_commercial_score(working)
        margin_risk_penalty = _margin_risk_penalty(working)
        leftover_risk_penalty = _leftover_risk_penalty(working)
        stockout_risk_penalty = _stockout_risk_penalty(working)
        overallocation_penalty = _overallocation_penalty(working)
        underallocation_penalty = _underallocation_penalty(working)
        disagreement_penalty = _disagreement_penalty(working["row_cohort_disagreement_score"], resolved_config)

        working["margin_risk_penalty"] = margin_risk_penalty
        working["leftover_risk_penalty"] = leftover_risk_penalty
        working["stockout_risk_penalty"] = stockout_risk_penalty
        working["overallocation_risk_penalty"] = overallocation_penalty
        working["underallocation_risk_penalty"] = underallocation_penalty
        working["disagreement_penalty"] = disagreement_penalty

        effective_row_confidence = row_model_confidence.where(
            row_model_confidence >= float(resolved_config.row_model_confidence_floor),
            other=0.0,
        )
        effective_cohort_confidence = (
            archetype_confidence * (1.0 - sparse_history_penalty)
        ).where(
            archetype_confidence >= float(resolved_config.archetype_confidence_floor),
            other=0.0,
        )
        confidence_total = effective_row_confidence + effective_cohort_confidence
        working["row_model_weight"] = effective_row_confidence.where(confidence_total > 0.0, other=0.0) / confidence_total.where(
            confidence_total > 0.0,
            other=1.0,
        )
        working["cohort_model_weight"] = effective_cohort_confidence.where(confidence_total > 0.0, other=0.0) / confidence_total.where(
            confidence_total > 0.0,
            other=1.0,
        )

        repeatable_bonus = (
            _first_present_series(
                working,
                ("nearest_archetype_repeatability_score", "archetype_repeatability_score"),
            )
            >= float(resolved_config.repeatable_winner_cutoff)
        ).astype(float) * 0.08
        destructive_penalty = (
            _first_present_series(
                working,
                ("nearest_archetype_destructiveness_score", "archetype_destructiveness_score"),
            )
            >= float(resolved_config.destructive_archetype_cutoff)
        ).astype(float) * 0.10
        base_decision_score = (
            working["row_model_weight"] * row_model_score
            + working["cohort_model_weight"] * cohort_model_score
            + repeatable_bonus
        )
        penalty_stack = (
            0.18 * sparse_history_penalty
            + 0.15 * working["instability_penalty"]
            + 0.18 * margin_risk_penalty
            + 0.12 * leftover_risk_penalty
            + 0.10 * stockout_risk_penalty
            + 0.12 * overallocation_penalty
            + 0.08 * underallocation_penalty
            + 0.15 * disagreement_penalty
            + destructive_penalty
        )
        working["final_decision_score"] = (base_decision_score - penalty_stack).clip(lower=0.0, upper=1.0)
        raw_confidence_score = (
            0.40 * row_model_confidence
            + 0.35 * archetype_confidence
            + 0.25 * working["decision_alignment_score"]
        )
        confidence_penalty = (
            0.20 * sparse_history_penalty
            + 0.15 * working["instability_penalty"]
            + 0.20 * disagreement_penalty
        )
        working["final_confidence_score"] = (raw_confidence_score - confidence_penalty).clip(
            lower=0.0,
            upper=1.0,
        )
        recommendation_frame = _build_recommendations(working)
        working["decision_recommendation"] = recommendation_frame["decision_recommendation"]
        working["decision_recommendation_reason"] = recommendation_frame[
            "decision_recommendation_reason"
        ]
        return PromotionDecisionFusionResult(
            decision_surface_frame=working,
            metrics=_decision_surface_metrics(working),
        )


def build_row_cohort_disagreement_score(frame: pd.DataFrame) -> pd.Series:
    """Measure row-model versus cohort expectation disagreement on a 0 to 1 scale."""

    comparisons: list[pd.Series] = []
    comparisons.append(
        _normalized_absolute_difference(
            _series_or_default(frame, "predicted_units_sold"),
            _series_or_default(frame, "nearest_archetype_expected_units"),
            minimum_scale=1.0,
        )
    )
    comparisons.append(
        _normalized_absolute_difference(
            _series_or_default(frame, "predicted_sales_ex_gst"),
            _series_or_default(frame, "nearest_archetype_expected_sales_ex_gst"),
            minimum_scale=1.0,
        )
    )
    comparisons.append(
        _normalized_absolute_difference(
            _series_or_default(frame, "predicted_gross_profit_dollars"),
            _series_or_default(frame, "nearest_archetype_expected_gp"),
            minimum_scale=1.0,
        )
    )
    comparisons.append(
        _normalized_absolute_difference(
            _series_or_default(frame, "predicted_sell_through_pct"),
            _series_or_default(frame, "nearest_archetype_expected_sell_through"),
            minimum_scale=1.0,
        )
    )
    comparisons.append(
        _normalized_absolute_difference(
            _series_or_default(frame, "predicted_overallocation_risk"),
            _series_or_default(frame, "nearest_archetype_expected_overallocation_rate"),
            minimum_scale=1.0,
        )
    )
    comparisons.append(
        _normalized_absolute_difference(
            _series_or_default(frame, "predicted_underallocation_risk"),
            _series_or_default(frame, "nearest_archetype_expected_underallocation_rate"),
            minimum_scale=1.0,
        )
    )
    comparisons.append(
        _normalized_absolute_difference(
            _series_or_default(frame, "predicted_stockout_risk"),
            _series_or_default(frame, "nearest_archetype_expected_stockout_rate"),
            minimum_scale=1.0,
        )
    )
    comparison_frame = pd.concat(comparisons, axis=1)
    comparison_frame = comparison_frame.mask(comparison_frame.isna())
    return comparison_frame.mean(axis=1, skipna=True)


def _row_model_commercial_score(frame: pd.DataFrame) -> pd.Series:
    gross_profit_ratio = (
        _series_or_default(frame, "predicted_gross_profit_dollars")
        / _series_or_default(frame, "predicted_sales_ex_gst").abs().clip(lower=1.0)
    ).clip(lower=-1.0, upper=1.0)
    profit_score = ((gross_profit_ratio + 1.0) / 2.0).clip(lower=0.0, upper=1.0)
    sell_through_score = _series_or_default(frame, "predicted_sell_through_pct").clip(lower=0.0, upper=1.0)
    risk_safety = 1.0 - (
        0.45 * _series_or_default(frame, "predicted_overallocation_risk")
        + 0.20 * _series_or_default(frame, "predicted_underallocation_risk")
        + 0.35 * _series_or_default(frame, "predicted_stockout_risk")
    ).clip(lower=0.0, upper=1.0)
    return (
        0.40 * profit_score
        + 0.30 * sell_through_score
        + 0.30 * risk_safety
    ).clip(lower=0.0, upper=1.0)


def _cohort_model_commercial_score(frame: pd.DataFrame) -> pd.Series:
    gross_profit_ratio = (
        _series_or_default(frame, "nearest_archetype_expected_gp")
        / _series_or_default(frame, "nearest_archetype_expected_sales_ex_gst").abs().clip(lower=1.0)
    ).clip(lower=-1.0, upper=1.0)
    profit_score = ((gross_profit_ratio + 1.0) / 2.0).clip(lower=0.0, upper=1.0)
    sell_through_score = _series_or_default(frame, "nearest_archetype_expected_sell_through").clip(
        lower=0.0,
        upper=1.0,
    )
    uplift_score = _series_or_default(frame, "nearest_archetype_expected_uplift").clip(lower=0.0, upper=1.0)
    leftover_safety = 1.0 - _series_or_default(frame, "nearest_archetype_expected_leftover").clip(
        lower=0.0,
        upper=1.0,
    )
    risk_safety = 1.0 - (
        0.45 * _series_or_default(frame, "nearest_archetype_expected_overallocation_rate")
        + 0.20 * _series_or_default(frame, "nearest_archetype_expected_underallocation_rate")
        + 0.35 * _series_or_default(frame, "nearest_archetype_expected_stockout_rate")
    ).clip(lower=0.0, upper=1.0)
    return (
        0.28 * profit_score
        + 0.22 * sell_through_score
        + 0.10 * uplift_score
        + 0.20 * leftover_safety
        + 0.20 * risk_safety
    ).clip(lower=0.0, upper=1.0)


def _margin_risk_penalty(frame: pd.DataFrame) -> pd.Series:
    row_margin_trap = (
        _series_or_default(frame, "predicted_gross_profit_dollars") <= 0.0
    ).astype(float)
    cohort_margin_trap = (
        _series_or_default(frame, "nearest_archetype_expected_gp") <= 0.0
    ).astype(float)
    destructiveness = _first_present_series(
        frame,
        ("nearest_archetype_destructiveness_score", "archetype_destructiveness_score"),
    ).clip(lower=0.0, upper=1.0)
    return (0.35 * row_margin_trap + 0.25 * cohort_margin_trap + 0.40 * destructiveness).clip(
        lower=0.0,
        upper=1.0,
    )


def _leftover_risk_penalty(frame: pd.DataFrame) -> pd.Series:
    return (
        0.65 * _series_or_default(frame, "nearest_archetype_expected_leftover").clip(lower=0.0, upper=1.0)
        + 0.35 * (1.0 - _series_or_default(frame, "predicted_sell_through_pct").clip(lower=0.0, upper=1.0))
    ).clip(lower=0.0, upper=1.0)


def _stockout_risk_penalty(frame: pd.DataFrame) -> pd.Series:
    return pd.concat(
        [
            _series_or_default(frame, "predicted_stockout_risk"),
            _series_or_default(frame, "nearest_archetype_expected_stockout_rate"),
        ],
        axis=1,
    ).max(axis=1).clip(lower=0.0, upper=1.0)


def _overallocation_penalty(frame: pd.DataFrame) -> pd.Series:
    return pd.concat(
        [
            _series_or_default(frame, "predicted_overallocation_risk"),
            _series_or_default(frame, "nearest_archetype_expected_overallocation_rate"),
        ],
        axis=1,
    ).max(axis=1).clip(lower=0.0, upper=1.0)


def _underallocation_penalty(frame: pd.DataFrame) -> pd.Series:
    return pd.concat(
        [
            _series_or_default(frame, "predicted_underallocation_risk"),
            _series_or_default(frame, "nearest_archetype_expected_underallocation_rate"),
        ],
        axis=1,
    ).max(axis=1).clip(lower=0.0, upper=1.0)


def _sparse_history_penalty(
    sample_size: pd.Series,
    config: PromotionDecisionFusionConfig,
) -> pd.Series:
    penalty = pd.Series(0.0, index=sample_size.index, dtype="float64")
    for max_sample_size, penalty_value in config.sparse_history_penalty_curve:
        if max_sample_size is None:
            penalty = penalty.where(penalty > 0.0, other=float(penalty_value))
            continue
        penalty = penalty.where(sample_size > float(max_sample_size), other=float(penalty_value))
    return penalty.clip(lower=0.0, upper=1.0)


def _disagreement_penalty(
    disagreement_score: pd.Series,
    config: PromotionDecisionFusionConfig,
) -> pd.Series:
    moderate = float(config.disagreement_moderate_cutoff)
    severe = float(max(config.disagreement_severe_cutoff, moderate + 0.01))
    penalty = pd.Series(0.0, index=disagreement_score.index, dtype="float64")
    moderate_mask = disagreement_score >= moderate
    severe_mask = disagreement_score >= severe
    penalty.loc[moderate_mask] = (
        (disagreement_score.loc[moderate_mask] - moderate) / max(severe - moderate, 1e-9)
    ).clip(lower=0.0, upper=1.0)
    penalty.loc[severe_mask] = 1.0
    return penalty.clip(lower=0.0, upper=1.0)


def _build_recommendations(frame: pd.DataFrame) -> pd.DataFrame:
    recommendations = []
    reasons = []
    for row in frame.itertuples(index=False):
        row_reasons: list[str] = []
        if row.row_cohort_disagreement_score >= 0.50:
            row_reasons.append("row model and cohort evidence disagree")
        if row.sparse_history_penalty >= 0.50:
            row_reasons.append("historical cohort evidence is sparse")
        if row.margin_risk_penalty >= 0.60:
            row_reasons.append("margin trap risk is elevated")
        if row.leftover_risk_penalty >= 0.60:
            row_reasons.append("leftover risk is elevated")
        if row.stockout_risk_penalty >= 0.60:
            row_reasons.append("stockout risk is elevated")
        if row.overallocation_risk_penalty >= 0.60:
            row_reasons.append("over-allocation risk is elevated")
        if row.final_decision_score >= 0.75 and row.final_confidence_score >= 0.65:
            recommendation = "strong_go"
            if not row_reasons:
                row_reasons.append("row and cohort evidence show repeatable edge")
        elif row.final_decision_score >= 0.60 and row.final_confidence_score >= 0.50:
            recommendation = "go"
            if not row_reasons:
                row_reasons.append("commercial attractiveness remains acceptable")
        elif row.final_decision_score >= 0.45 and row.final_confidence_score >= 0.35:
            recommendation = "watch"
            if not row_reasons:
                row_reasons.append("signal is usable but not decisive")
        elif row.final_decision_score >= 0.25 or row.final_confidence_score >= 0.25:
            recommendation = "high_risk"
            if not row_reasons:
                row_reasons.append("commercial risk outweighs current edge")
        else:
            recommendation = "avoid"
            if not row_reasons:
                row_reasons.append("confidence and commercial attractiveness are too weak")
        recommendations.append(recommendation)
        reasons.append("; ".join(row_reasons[:3]))
    return pd.DataFrame(
        {
            "decision_recommendation": recommendations,
            "decision_recommendation_reason": reasons,
        },
        index=frame.index,
    )


def _decision_surface_metrics(frame: pd.DataFrame) -> dict[str, object]:
    recommendation_counts = (
        frame["decision_recommendation"].value_counts(dropna=False).sort_index().to_dict()
        if "decision_recommendation" in frame.columns
        else {}
    )
    return {
        "row_count": int(len(frame.index)),
        "recommendation_counts": {str(key): int(value) for key, value in recommendation_counts.items()},
        "average_final_decision_score": float(_series_or_default(frame, "final_decision_score").mean()),
        "average_final_confidence_score": float(_series_or_default(frame, "final_confidence_score").mean()),
        "average_alignment_score": float(_series_or_default(frame, "decision_alignment_score").mean()),
        "sparse_history_rate": float((_series_or_default(frame, "sparse_history_penalty") >= 0.5).mean()),
        "disagreement_rate": float((_series_or_default(frame, "row_cohort_disagreement_score") >= 0.30).mean()),
    }


def _normalized_absolute_difference(
    left: pd.Series,
    right: pd.Series,
    *,
    minimum_scale: float,
) -> pd.Series:
    scale = pd.concat([left.abs(), right.abs()], axis=1).max(axis=1).clip(lower=float(minimum_scale))
    difference = (left - right).abs() / scale
    both_missing = left.isna() & right.isna()
    return difference.mask(both_missing)


def _series_or_default(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0)


def _first_present_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            return pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=frame.index, dtype="float64")