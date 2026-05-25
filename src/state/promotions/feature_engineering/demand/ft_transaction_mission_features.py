from __future__ import annotations

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


TRANSACTION_MISSION_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_transactions_with_sku_per_day",
    "feature_units_per_transaction_when_sku_present",
    "feature_weekend_share_with_sku",
    "feature_pay_cycle_sensitivity_score",
)


def build_transaction_mission_features(summary_frame: pd.DataFrame) -> pd.DataFrame:
    transaction_count = ensure_numeric_series(
        summary_frame,
        "basket_history_transaction_count",
        default=float("nan"),
    )
    total_promo_days = ensure_numeric_series(
        summary_frame,
        "basket_history_total_promo_days",
        default=float("nan"),
    )
    total_units = ensure_numeric_series(
        summary_frame,
        "basket_history_total_units_sold",
        default=float("nan"),
    )
    transactions_per_day = safe_ratio(
        transaction_count,
        total_promo_days,
        default=float("nan"),
    ).where(total_promo_days > 0.0)
    units_per_transaction = safe_ratio(
        total_units,
        transaction_count,
        default=float("nan"),
    ).where(transaction_count > 0.0)
    weekend_share = safe_ratio(
        ensure_numeric_series(
            summary_frame,
            "basket_history_weekend_transaction_count",
            default=float("nan"),
        ),
        transaction_count,
        default=float("nan"),
    ).where(transaction_count > 0.0)
    pay_cycle_transaction_share = safe_ratio(
        ensure_numeric_series(
            summary_frame,
            "basket_history_pay_cycle_transaction_count",
            default=float("nan"),
        ),
        transaction_count,
        default=float("nan"),
    ).where(transaction_count > 0.0)
    pay_cycle_day_share = safe_ratio(
        ensure_numeric_series(
            summary_frame,
            "basket_history_total_pay_cycle_days",
            default=float("nan"),
        ),
        total_promo_days,
        default=float("nan"),
    ).where(total_promo_days > 0.0)
    pay_cycle_ratio = pay_cycle_transaction_share.divide(
        pay_cycle_day_share.replace(0.0, np.nan)
    )
    pay_cycle_sensitivity_score = ((pay_cycle_ratio - 1.0) / 2.0).clip(
        lower=0.0,
        upper=1.0,
    )

    return pd.DataFrame(
        {
            "feature_transactions_with_sku_per_day": transactions_per_day,
            "feature_units_per_transaction_when_sku_present": units_per_transaction,
            "feature_weekend_share_with_sku": weekend_share,
            "feature_pay_cycle_sensitivity_score": pay_cycle_sensitivity_score,
        },
        index=summary_frame.index,
    )