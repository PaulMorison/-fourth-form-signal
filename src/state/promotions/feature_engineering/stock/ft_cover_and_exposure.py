from __future__ import annotations

"""Cover-and-exposure ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_cover_and_exposure(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add stock-cover and promo-exposure pressure features."""

    del reference_frame
    working = frame.copy()
    promo_days = ensure_numeric_series(working, "live_promo_window_days").where(
        lambda values: values > 0.0,
        ensure_numeric_series(working, "promo_days"),
    )
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    working["feature_stock_to_promo_days_ratio"] = safe_ratio(stock_basis, promo_days)
    working["feature_stock_exposure_vs_promo_days"] = safe_ratio(
        ensure_numeric_series(working, "tot_days_cover"),
        promo_days,
    )
    working["feature_sellthrough_pressure_index"] = safe_ratio(
        ensure_numeric_series(working, "demand_reference_units"),
        stock_basis,
    )
    return working
