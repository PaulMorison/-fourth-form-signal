from __future__ import annotations

"""Typed schema helpers for promotions base, target, and feature frames.

Canon ownership:
- Declares the stable grain columns, surfaced numeric/date coercions, and
  reusable commercial basis helpers used across promotions targets, features,
  datasets, models, and scoring.
- Keeps price, cost, stock, and event-key derivations explicit and reusable so
  those meanings are not redefined slightly in each downstream module.
- Does not own business labels, model logic, or report assembly.
"""

from state.promotions.feature_engineering.shared.ft_base_math import first_non_null_series as first_non_null
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import (
    DATE_COLUMNS,
    NUMERIC_COLUMNS,
    PROMOTION_GRAIN_COLUMNS,
    build_promotion_network_key,
    build_promotion_row_key,
    build_promotion_store_event_key,
    coerce_promotions_frame_types,
    resolve_allocation_basis_units,
    resolve_effective_cost_per_unit,
    resolve_promo_price_ex_gst,
    resolve_promo_window_days,
    resolve_regular_price_ex_gst,
)

__all__ = [
    "DATE_COLUMNS",
    "NUMERIC_COLUMNS",
    "PROMOTION_GRAIN_COLUMNS",
    "build_promotion_network_key",
    "build_promotion_row_key",
    "build_promotion_store_event_key",
    "coerce_promotions_frame_types",
    "first_non_null",
    "resolve_allocation_basis_units",
    "resolve_effective_cost_per_unit",
    "resolve_promo_price_ex_gst",
    "resolve_promo_window_days",
    "resolve_regular_price_ex_gst",
    "safe_ratio",
]
