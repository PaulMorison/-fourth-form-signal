from __future__ import annotations

"""Reality-gap ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_reality_gap(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add feasibility-gap and breakout-response flags."""

    del reference_frame
    working = frame.copy()
    working["feature_uplift_feasibility_gap"] = (
        ensure_numeric_series(working, "required_implied_multiple")
        - ensure_numeric_series(working, "feature_allocation_vs_baseline_demand_ratio")
    )
    working["feature_reality_gap_score"] = (
        ensure_numeric_series(working, "feature_uplift_feasibility_gap").abs()
        + ensure_numeric_series(working, "feature_compensation_needed_score")
        + ensure_numeric_series(working, "feature_sync_misalignment_penalty")
    ) / 3.0
    working["feature_needs_breakout_response_flag"] = (
        (working["feature_uplift_feasibility_gap"] > 1.0)
        | (working["feature_reality_gap_score"] > 0.75)
    ).astype(float)
    return working
