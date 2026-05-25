from __future__ import annotations

"""Governed target engineering for completed promotions.

Canon ownership:
- Derives the reusable training targets and label flags used to evaluate the
  quality of promotional advice at the promotion x sku x store grain.
- Makes refund netting, baseline windows, post-promo follow-through, and stock
  risk thresholds explicit in one module.
- Does not own feature definitions, model fitting, or scoring outputs.
"""

from dataclasses import dataclass

import pandas as pd

from state.promotions.feature_engineering.targets.ft_target_gross_profit import apply_ft_target_gross_profit
from state.promotions.feature_engineering.targets.ft_target_historical_allocation import (
    HISTORICAL_ALLOCATION_TARGET_COLUMNS,
    apply_ft_target_historical_allocation,
)
from state.promotions.feature_engineering.targets.ft_target_leftover_stock import apply_ft_target_leftover_stock
from state.promotions.feature_engineering.targets.ft_target_overallocation_flag import apply_ft_target_overallocation_flag
from state.promotions.feature_engineering.targets.ft_target_post_promo_followthrough import apply_ft_target_post_promo_followthrough
from state.promotions.feature_engineering.targets.ft_target_realised_uplift import apply_ft_target_realised_uplift
from state.promotions.feature_engineering.targets.ft_target_sales_ex_gst import apply_ft_target_sales_ex_gst
from state.promotions.feature_engineering.targets.ft_target_sell_through import apply_ft_target_sell_through
from state.promotions.feature_engineering.targets.ft_target_stockout_flag import apply_ft_target_stockout_flag
from state.promotions.feature_engineering.targets.ft_target_underallocation_flag import apply_ft_target_underallocation_flag
from state.promotions.feature_engineering.targets.ft_target_units_sold import apply_ft_target_units_sold
from state.promotions.promotion_frame_schema import coerce_promotions_frame_types
from state.promotions.targets.baseline_windows import add_baseline_window_columns


_TARGET_COLUMNS = (
    "target_actual_units_sold",
    "target_actual_sales_ex_gst",
    "target_actual_gross_profit_dollars",
    "target_sell_through_pct",
    "target_leftover_stock_pct",
    "target_post_promo_followthrough_units",
    "target_post_promo_followthrough_sales_ex_gst",
    "target_stockout_flag",
    "target_overallocation_flag",
    "target_underallocation_flag",
    "target_realised_uplift_vs_baseline",
    *HISTORICAL_ALLOCATION_TARGET_COLUMNS,
)


@dataclass(frozen=True)
class PromotionTargetEngineeringResult:
    frame: pd.DataFrame
    target_columns: tuple[str, ...] = _TARGET_COLUMNS


class PromotionTargetEngineer:
    """Derive reusable promotion evaluation targets for completed promotions."""

    def engineer(self, base_frame: pd.DataFrame) -> PromotionTargetEngineeringResult:
        """Add explicit target columns and the auxiliary bases they depend on."""

        working = add_baseline_window_columns(coerce_promotions_frame_types(base_frame))
        for apply_fn in (
            apply_ft_target_units_sold,
            apply_ft_target_sales_ex_gst,
            apply_ft_target_gross_profit,
            apply_ft_target_sell_through,
            apply_ft_target_leftover_stock,
            apply_ft_target_realised_uplift,
            apply_ft_target_post_promo_followthrough,
            apply_ft_target_stockout_flag,
            apply_ft_target_overallocation_flag,
            apply_ft_target_underallocation_flag,
            apply_ft_target_historical_allocation,
        ):
            working = apply_fn(working)
        return PromotionTargetEngineeringResult(frame=working)
