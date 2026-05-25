from __future__ import annotations

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


COMPANION_ITEM_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_top_companion_sku_1_share",
    "feature_top_companion_sku_2_share",
    "feature_companion_concentration_index",
    "feature_basket_diversity_when_sku_present",
)


def build_companion_item_features(summary_frame: pd.DataFrame) -> pd.DataFrame:
    transaction_count = ensure_numeric_series(
        summary_frame,
        "basket_history_transaction_count",
        default=float("nan"),
    )
    top_companion_sku_1_share = ensure_numeric_series(
        summary_frame,
        "basket_history_top_companion_sku_1_share",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0).where(transaction_count > 0.0)
    top_companion_sku_2_share = ensure_numeric_series(
        summary_frame,
        "basket_history_top_companion_sku_2_share",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0).where(transaction_count > 0.0)
    concentration_index = ensure_numeric_series(
        summary_frame,
        "basket_history_companion_concentration_index",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0).where(transaction_count > 0.0)
    diversity_index = (1.0 - concentration_index).clip(lower=0.0, upper=1.0)

    return pd.DataFrame(
        {
            "feature_top_companion_sku_1_share": top_companion_sku_1_share,
            "feature_top_companion_sku_2_share": top_companion_sku_2_share,
            "feature_companion_concentration_index": concentration_index,
            "feature_basket_diversity_when_sku_present": diversity_index,
        },
        index=summary_frame.index,
    )