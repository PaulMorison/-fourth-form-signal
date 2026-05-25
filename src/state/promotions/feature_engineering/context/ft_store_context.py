from __future__ import annotations

"""Store-context ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import build_promotion_store_event_key


def apply_ft_store_context(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add store-event demand load and within-event demand-share features."""

    del reference_frame
    working = frame.copy()
    working["promotion_store_event_key"] = build_promotion_store_event_key(working)
    baseline_units = pd.to_numeric(working["baseline_expected_units"], errors="coerce").fillna(0.0)
    event_baseline_units = baseline_units.groupby(working["promotion_store_event_key"]).transform("sum")
    working["feature_store_event_baseline_units"] = event_baseline_units
    working["feature_store_baseline_share_in_event"] = safe_ratio(baseline_units, event_baseline_units)
    if "feature_store_overlap_count" in working.columns:
        working["feature_store_level_promo_load"] = working["feature_store_overlap_count"].fillna(0.0)
    else:
        working["feature_store_level_promo_load"] = (
            working.groupby("promotion_store_event_key")["promotion_row_key"].transform("count").astype(float)
        )
    return working
