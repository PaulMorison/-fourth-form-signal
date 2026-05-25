from __future__ import annotations

"""History-regime ft module."""

import pandas as pd

from state.promotions.feature_engineering.demand.ft_promo_recurrence import apply_ft_promo_recurrence
from state.promotions.feature_engineering.demand.ft_promo_uplift_history import apply_ft_promo_uplift_history
from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_history_regime(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add prior promo response, recurrence, and combined history-regime features."""

    working = apply_ft_promo_uplift_history(frame, reference_frame=reference_frame)
    working = apply_ft_promo_recurrence(working, reference_frame=reference_frame)
    working["feature_history_regime_score"] = (
        ensure_numeric_series(working, "feature_prior_promo_response_same_sku_store")
        + ensure_numeric_series(working, "feature_prior_promo_response_same_sku_network")
        + ensure_numeric_series(working, "feature_promo_recurrence_density")
    ) / 3.0
    return working
