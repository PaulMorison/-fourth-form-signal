from __future__ import annotations

"""Stock-posture ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_stock_posture(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add stock pressure and sufficiency gap features."""

    del reference_frame
    working = frame.copy()
    total_stock_available = ensure_numeric_series(working, "total_stock_available").where(
        lambda values: values > 0.0,
        ensure_numeric_series(working, "stock_basis_units"),
    )
    required_units = ensure_numeric_series(working, "required_implied_units")
    working["feature_total_stock_pressure_ratio"] = total_stock_available.divide(
        required_units.replace(0.0, pd.NA)
    ).fillna(0.0)
    working["feature_stock_sufficiency_gap_units"] = total_stock_available - required_units
    working["feature_current_soh_ratio"] = ensure_numeric_series(working, "current_soh").divide(
        ensure_numeric_series(working, "stock_basis_units").replace(0.0, pd.NA)
    ).fillna(0.0)
    working["feature_stock_strain"] = required_units.divide(
        ensure_numeric_series(working, "current_soh").replace(0.0, pd.NA)
    ).fillna(0.0)
    return working
