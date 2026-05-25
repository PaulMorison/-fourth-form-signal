from __future__ import annotations

"""Friction-signals ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_friction_signals(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add friction and conversion-burden features from demand, margin, and capital."""

    del reference_frame
    working = frame.copy()
    working["feature_stock_tie_up_vs_expected_sales"] = safe_ratio(
        ensure_numeric_series(working, "feature_capital_at_risk"),
        ensure_numeric_series(working, "baseline_expected_sales_ex_gst"),
    )
    working["feature_friction_to_conversion_burden"] = (
        ensure_numeric_series(working, "feature_required_vs_baseline_demand_gap").abs()
        * ensure_numeric_series(working, "feature_sellthrough_pressure_index")
    )
    working["feature_margin_sacrifice_vs_expected_flow"] = safe_ratio(
        ensure_numeric_series(working, "feature_margin_dollars_at_risk"),
        ensure_numeric_series(working, "demand_reference_units"),
    )
    return working
