from __future__ import annotations

"""Review-only fragility-adjusted opportunity and DAG support diagnostics."""

import numpy as np
import pandas as pd


FRAGILITY_ADJUSTED_OPPORTUNITY_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_fragility_adjusted_opportunity_score",
    "feature_convex_upside_small_unit_flag",
    "feature_dag_dependency_support_indicator",
    "feature_dependency_support_confidence_score",
    "feature_opportunity_tail_support_score",
    "feature_fragility_opportunity_review_only_flag",
)

FRAGILITY_ADJUSTED_OPPORTUNITY_FEATURE_COLUMNS: tuple[str, ...] = (
    *FRAGILITY_ADJUSTED_OPPORTUNITY_REVIEW_ONLY_FEATURE_COLUMNS,
)


def apply_ft_fragility_adjusted_opportunity(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append review-only opportunity diagnostics without causal overclaiming.

    Purpose:
        Combine basket dependency, sparse/noise, distribution, and survival
        signals into auditable opportunity-support indicators. The DAG support
        field is a structured support indicator, not a causal proof.

    Inputs:
        frame: candidate rows carrying prior-safe engineered features.
        reference_frame: accepted for registry compatibility and unused.

    Outputs:
        A copy of ``frame`` with review-only opportunity diagnostics appended.

    Failure behavior:
        Missing upstream diagnostics lower support confidence; they do not alter
        BUY/ORDER or publishability logic.
    """

    del reference_frame
    working = frame.copy()
    basket_convexity = _optional_numeric_series(working, "feature_basket_convexity_support_score").clip(0.0, 1.0)
    anchor_score = _optional_numeric_series(working, "feature_basket_anchor_sku_score").clip(0.0, 1.0)
    sparse_stable = _optional_numeric_series(working, "feature_sparse_demand_stable_low_trust_flag").clip(0.0, 1.0)
    random_tail = _optional_numeric_series(working, "feature_sparse_demand_random_tail_flag").clip(0.0, 1.0)
    tail_pressure = _optional_numeric_series(working, "feature_distribution_tail_pressure_score").clip(0.0, 1.0)
    survival_convexity = _optional_numeric_series(
        working,
        "feature_survival_internal_convex_upside_proxy_score",
    ).clip(0.0, 1.0)
    small_unit_gap = _first_optional_numeric_series(
        working,
        (
            "feature_units_needed_for_trust_floor",
            "feature_units_needed_for_high_demand_cover",
            "feature_expected_lost_units_below_trust_floor",
        ),
    ).clip(lower=0.0)

    evidence_frame = pd.concat(
        [basket_convexity, anchor_score, sparse_stable, random_tail, tail_pressure, survival_convexity],
        axis=1,
    )
    support_confidence = evidence_frame.notna().sum(axis=1).astype(float).divide(float(evidence_frame.shape[1]))
    basket_convexity = basket_convexity.fillna(0.0)
    anchor_score = anchor_score.fillna(0.0)
    sparse_stable = sparse_stable.fillna(0.0)
    random_tail = random_tail.fillna(0.0)
    tail_pressure = tail_pressure.fillna(0.0)
    survival_convexity = survival_convexity.fillna(0.0)
    small_unit_gap = small_unit_gap.fillna(0.0)
    small_unit_flag = small_unit_gap.between(1.0, 2.0, inclusive="both").astype(float)
    dag_support = (
        (basket_convexity.ge(0.35) | anchor_score.ge(0.45))
        & random_tail.lt(1.0)
        & support_confidence.ge(0.5)
    ).astype(float)
    opportunity_tail_support = (
        0.35 * survival_convexity
        + 0.25 * basket_convexity
        + 0.20 * sparse_stable
        + 0.20 * tail_pressure
    ).clip(0.0, 1.0)
    opportunity_score = (
        opportunity_tail_support
        * (0.6 + 0.4 * support_confidence)
        * (1.0 - 0.35 * random_tail)
    ).clip(0.0, 1.0)

    derived = pd.DataFrame(
        {
            "feature_fragility_adjusted_opportunity_score": opportunity_score,
            "feature_convex_upside_small_unit_flag": small_unit_flag,
            "feature_dag_dependency_support_indicator": dag_support,
            "feature_dependency_support_confidence_score": support_confidence.clip(0.0, 1.0),
            "feature_opportunity_tail_support_score": opportunity_tail_support,
            "feature_fragility_opportunity_review_only_flag": pd.Series(1.0, index=working.index),
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived.columns), errors="ignore")
    return pd.concat([base_columns, derived], axis=1)


def _optional_numeric_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    """Return a numeric series preserving missing evidence as NaN."""

    if column_name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce")


def _first_optional_numeric_series(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
) -> pd.Series:
    """Return the first non-null numeric evidence from candidate columns."""

    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return frame[present_columns].apply(pd.to_numeric, errors="coerce").bfill(axis=1).iloc[:, 0]