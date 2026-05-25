from __future__ import annotations

"""Sales-ex-GST target ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_target_sales_ex_gst(frame: pd.DataFrame) -> pd.DataFrame:
    """Add realized ex-GST sales as a governed target."""

    working = frame.copy()
    working["target_actual_sales_ex_gst"] = ensure_numeric_series(working, "actual_sales_ex_gst")
    return working
