from __future__ import annotations

"""Overhang-risk proxy ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_overhang_risk_proxy(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add an overhang proxy from stock exceeding baseline demand."""

    del reference_frame
    working = frame.copy()
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    baseline_units = ensure_numeric_series(working, "baseline_expected_units")
    working["feature_overhang_risk_proxy"] = safe_ratio(
        (stock_basis - baseline_units).clip(lower=0.0),
        stock_basis,
    )
    return working
