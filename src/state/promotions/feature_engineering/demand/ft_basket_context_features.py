from __future__ import annotations

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


BASKET_CONTEXT_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_basket_attach_rate",
    "feature_sku_solo_purchase_rate",
    "feature_basket_avg_items_when_sku_present",
    "feature_basket_median_items_when_sku_present",
    "feature_basket_avg_value_when_sku_present",
    "feature_basket_median_value_when_sku_present",
    "feature_sku_basket_dependency_score",
)


def build_basket_context_features(summary_frame: pd.DataFrame) -> pd.DataFrame:
    transaction_count = ensure_numeric_series(
        summary_frame,
        "basket_history_transaction_count",
        default=float("nan"),
    )
    attach_rate = safe_ratio(
        ensure_numeric_series(
            summary_frame,
            "basket_history_multi_item_transaction_count",
            default=float("nan"),
        ),
        transaction_count,
        default=float("nan"),
    ).where(transaction_count > 0.0)
    solo_rate = safe_ratio(
        ensure_numeric_series(
            summary_frame,
            "basket_history_solo_transaction_count",
            default=float("nan"),
        ),
        transaction_count,
        default=float("nan"),
    ).where(transaction_count > 0.0)
    average_items = safe_ratio(
        ensure_numeric_series(
            summary_frame,
            "basket_history_item_count_sum",
            default=float("nan"),
        ),
        transaction_count,
        default=float("nan"),
    ).where(transaction_count > 0.0)
    median_items = ensure_numeric_series(
        summary_frame,
        "basket_history_item_count_median",
        default=float("nan"),
    ).where(transaction_count > 0.0)
    average_value = safe_ratio(
        ensure_numeric_series(
            summary_frame,
            "basket_history_basket_value_sum",
            default=float("nan"),
        ),
        transaction_count,
        default=float("nan"),
    ).where(transaction_count > 0.0)
    median_value = ensure_numeric_series(
        summary_frame,
        "basket_history_basket_value_median",
        default=float("nan"),
    ).where(transaction_count > 0.0)
    dependency_score = (
        attach_rate * ((average_items - 1.0).clip(lower=0.0, upper=4.0) / 4.0)
    ).clip(lower=0.0, upper=1.0)

    return pd.DataFrame(
        {
            "feature_basket_attach_rate": attach_rate,
            "feature_sku_solo_purchase_rate": solo_rate,
            "feature_basket_avg_items_when_sku_present": average_items,
            "feature_basket_median_items_when_sku_present": median_items,
            "feature_basket_avg_value_when_sku_present": average_value,
            "feature_basket_median_value_when_sku_present": median_value,
            "feature_sku_basket_dependency_score": dependency_score,
        },
        index=summary_frame.index,
    )