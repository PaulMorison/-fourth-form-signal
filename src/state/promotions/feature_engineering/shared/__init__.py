from __future__ import annotations

"""Shared helpers for promotions ft modules."""

from state.promotions.feature_engineering.shared.ft_group_windows import apply_ft_baseline_windows
from state.promotions.feature_engineering.shared.ft_safe_division import safe_divide, safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import (
    DATE_COLUMNS,
    NUMERIC_COLUMNS,
    PROMOTION_GRAIN_COLUMNS,
    apply_canonical_pricing_columns,
    build_promotion_network_key,
    build_promotion_row_key,
    build_promotion_store_event_key,
    coerce_promotions_frame_types,
    discount_band_from_decimal,
    normalize_discount_decimal,
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
    "apply_canonical_pricing_columns",
    "apply_ft_baseline_windows",
    "build_promotion_network_key",
    "build_promotion_row_key",
    "build_promotion_store_event_key",
    "coerce_promotions_frame_types",
    "discount_band_from_decimal",
    "normalize_discount_decimal",
    "resolve_allocation_basis_units",
    "resolve_effective_cost_per_unit",
    "resolve_promo_price_ex_gst",
    "resolve_promo_window_days",
    "resolve_regular_price_ex_gst",
    "safe_divide",
    "safe_ratio",
]
