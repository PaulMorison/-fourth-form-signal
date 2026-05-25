from __future__ import annotations

"""Real-data calibration support for promotions cohort decision surfaces.

Canon ownership:
- Derives threshold suggestions from observed row-model and cohort evidence
  distributions instead of relying only on fixed heuristics.
- Surfaces sparse-history curves, confidence floors, disagreement cutoffs, and
  archetype winner or destructiveness cutoffs as explicit threshold outputs.
- Does not own per-row decision weighting, diagnostics aggregation, or report
  persistence.
"""

from dataclasses import dataclass

import pandas as pd

from models.promotions.cohorts.decision_fusion import build_row_cohort_disagreement_score


@dataclass(frozen=True)
class PromotionDecisionCalibrationResult:
    summary: dict[str, object]
    thresholds: dict[str, object]


class PromotionDecisionCalibrator:
    """Calibrate decision-surface thresholds from historical promotions evidence."""

    def calibrate(
        self,
        frame: pd.DataFrame,
        *,
        minimum_sample_size: int = 3,
    ) -> PromotionDecisionCalibrationResult:
        """Return data-derived threshold suggestions for fusion and diagnostics."""

        working = frame.copy()
        similarity = _series_or_default(working, "nearest_archetype_similarity")
        sample_size = _series_or_default(working, "nearest_archetype_sample_size")
        archetype_confidence = _first_present_series(
            working,
            ("nearest_archetype_confidence_score", "archetype_confidence_score"),
        )
        row_model_confidence = _series_or_default(working, "row_model_confidence_score")
        destructiveness = _first_present_series(
            working,
            ("nearest_archetype_destructiveness_score", "archetype_destructiveness_score"),
        )
        repeatability = _first_present_series(
            working,
            ("nearest_archetype_repeatability_score", "archetype_repeatability_score"),
        )
        strength = _first_present_series(
            working,
            ("nearest_archetype_strength_score", "archetype_strength_score"),
        )
        fragility = _first_present_series(
            working,
            ("nearest_archetype_fragility_score", "archetype_fragility_score"),
        )
        disagreement = build_row_cohort_disagreement_score(working)

        breakpoints = {
            "critical": max(minimum_sample_size, int(sample_size.replace(0.0, pd.NA).dropna().quantile(0.25) or minimum_sample_size)),
            "developing": max(minimum_sample_size + 1, int(sample_size.replace(0.0, pd.NA).dropna().quantile(0.50) or (minimum_sample_size + 1))),
            "stable": max(minimum_sample_size + 2, int(sample_size.replace(0.0, pd.NA).dropna().quantile(0.75) or (minimum_sample_size + 2))),
        }
        thresholds = {
            "similarity_threshold_suggestion": float(_bounded_quantile(similarity, 0.50, lower=0.45, upper=0.85, default=0.55)),
            "archetype_confidence_floor_suggestion": float(
                _bounded_quantile(archetype_confidence, 0.35, lower=0.25, upper=0.80, default=0.45)
            ),
            "row_model_confidence_floor_suggestion": float(
                _bounded_quantile(row_model_confidence, 0.35, lower=0.25, upper=0.80, default=0.45)
            ),
            "sparse_cohort_penalty_curve": [
                {"max_sample_size": breakpoints["critical"], "penalty": 0.85},
                {"max_sample_size": breakpoints["developing"], "penalty": 0.55},
                {"max_sample_size": breakpoints["stable"], "penalty": 0.25},
                {"max_sample_size": None, "penalty": 0.0},
            ],
            "minimum_archetype_sample_size_breakpoints": breakpoints,
            "destructive_archetype_cutoffs": {
                "destructiveness": float(_bounded_quantile(destructiveness, 0.75, lower=0.55, upper=0.95, default=0.75)),
                "fragility": float(_bounded_quantile(fragility, 0.70, lower=0.50, upper=0.95, default=0.70)),
                "gross_profit_dollars": float(_series_or_default(working, "nearest_archetype_expected_gp").quantile(0.25)) if not working.empty else 0.0,
            },
            "repeatable_winner_cutoffs": {
                "repeatability": float(_bounded_quantile(repeatability, 0.75, lower=0.55, upper=0.95, default=0.75)),
                "strength": float(_bounded_quantile(strength, 0.70, lower=0.50, upper=0.95, default=0.70)),
                "confidence": float(_bounded_quantile(archetype_confidence, 0.60, lower=0.35, upper=0.90, default=0.60)),
            },
            "disagreement_penalty_cutoffs": {
                "moderate": float(_bounded_quantile(disagreement, 0.60, lower=0.20, upper=0.70, default=0.30)),
                "severe": float(_bounded_quantile(disagreement, 0.80, lower=0.35, upper=0.90, default=0.55)),
            },
        }
        summary = {
            "row_count": int(len(working.index)),
            "rows_with_similarity": int(similarity.gt(0.0).sum()),
            "rows_with_row_model_confidence": int(row_model_confidence.gt(0.0).sum()),
            "rows_with_archetype_confidence": int(archetype_confidence.gt(0.0).sum()),
            "rows_with_disagreement_observation": int(disagreement.notna().sum()),
            "minimum_sample_size": int(minimum_sample_size),
            "sample_size_range": {
                "min": int(sample_size.min()) if not sample_size.empty else 0,
                "max": int(sample_size.max()) if not sample_size.empty else 0,
            },
        }
        return PromotionDecisionCalibrationResult(summary=summary, thresholds=thresholds)


def _series_or_default(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0)


def _first_present_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            return pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=frame.index, dtype="float64")


def _bounded_quantile(
    series: pd.Series,
    quantile: float,
    *,
    lower: float,
    upper: float,
    default: float,
) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return float(default)
    value = float(clean.quantile(float(quantile)))
    return float(min(max(value, float(lower)), float(upper)))