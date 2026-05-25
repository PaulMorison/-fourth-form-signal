from __future__ import annotations

"""Legacy stock-leftover compatibility ft module."""

import pandas as pd

from state.promotions.feature_engineering.targets.ft_target_leftover_stock import apply_ft_target_leftover_stock
from state.promotions.feature_engineering.targets.ft_target_overallocation_flag import apply_ft_target_overallocation_flag
from state.promotions.feature_engineering.targets.ft_target_stockout_flag import apply_ft_target_stockout_flag
from state.promotions.feature_engineering.targets.ft_target_underallocation_flag import apply_ft_target_underallocation_flag


def apply_ft_target_stock_leftover(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the split stock-leftover target modules for compatibility."""

    working = apply_ft_target_leftover_stock(frame)
    working = apply_ft_target_stockout_flag(working)
    working = apply_ft_target_overallocation_flag(working)
    return apply_ft_target_underallocation_flag(working)
