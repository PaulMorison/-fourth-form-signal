from __future__ import annotations

"""Promo-recurrence ft module."""

import pandas as pd

from state.promotions.feature_engineering.demand.ft_promo_uplift_history import rolling_past_density


def apply_ft_promo_recurrence(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add the trailing density of prior promos for the same sku and store."""

    del reference_frame
    working = frame.copy()
    working["feature_promo_recurrence_density"] = rolling_past_density(
        working,
        group_columns=["sku_number_key", "store_number_key"],
        date_column="promotion_start_date_date",
        lookback_days=365,
    )
    return working