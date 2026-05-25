from __future__ import annotations

"""Supplier-context ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import build_promotion_store_event_key


def apply_ft_supplier_context(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add supplier concentration within each store promotion event."""

    del reference_frame
    working = frame.copy()
    working["promotion_store_event_key"] = build_promotion_store_event_key(working)
    supplier_key = ensure_numeric_series(working, "inferred_supplier_number")
    supplier_counts = working.groupby([working["promotion_store_event_key"], supplier_key])["promotion_row_key"].transform("count")
    event_counts = working.groupby("promotion_store_event_key")["promotion_row_key"].transform("count")
    working["feature_supplier_concentration"] = safe_ratio(
        supplier_counts.astype(float),
        event_counts.astype(float),
    )
    return working
