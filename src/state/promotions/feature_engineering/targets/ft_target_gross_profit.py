from __future__ import annotations

"""Gross-profit target ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_target_gross_profit(frame: pd.DataFrame) -> pd.DataFrame:
    """Add realized gross profit dollars after the effective unit cost basis."""

    working = frame.copy()
    working["target_actual_gross_profit_dollars"] = (
        ensure_numeric_series(working, "target_actual_sales_ex_gst")
        - ensure_numeric_series(working, "target_actual_units_sold")
        * ensure_numeric_series(working, "effective_cost_per_unit")
    )
    return working
