from __future__ import annotations

"""Category-context ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_text_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import build_promotion_store_event_key


def apply_ft_category_context(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add category share and sku-rank context within each store event."""

    del reference_frame
    working = frame.copy()
    working["promotion_store_event_key"] = build_promotion_store_event_key(working)
    baseline_units = pd.to_numeric(working["baseline_expected_units"], errors="coerce").fillna(0.0)
    category_key = ensure_text_series(working, "category")
    store_totals = baseline_units.groupby(working["promotion_store_event_key"]).transform("sum")
    category_totals = baseline_units.groupby([working["promotion_store_event_key"], category_key]).transform("sum")
    category_ranks = baseline_units.groupby([working["promotion_store_event_key"], category_key]).rank(
        method="dense",
        ascending=False,
    )
    working["feature_category_share_in_store"] = safe_ratio(category_totals, store_totals)
    working["feature_sku_rank_within_category_within_store"] = category_ranks.fillna(0.0)
    return working
