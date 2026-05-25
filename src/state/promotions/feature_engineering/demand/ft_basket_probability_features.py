from __future__ import annotations

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


BASKET_PROBABILITY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_probability_sku_in_multi_item_basket",
    "feature_probability_sku_solo_purchase",
    "feature_probability_units_given_multi_item_basket",
    "feature_probability_zero_units_given_low_traffic",
    "feature_companion_absence_risk_score",
)

_BETA_PRIOR_ALPHA = 1.0
_BETA_PRIOR_BETA = 1.0


def build_basket_probability_features(summary_frame: pd.DataFrame) -> pd.DataFrame:
    transaction_count = ensure_numeric_series(
        summary_frame,
        "basket_history_transaction_count",
        default=float("nan"),
    )
    multi_item_transaction_count = ensure_numeric_series(
        summary_frame,
        "basket_history_multi_item_transaction_count",
        default=float("nan"),
    )
    solo_transaction_count = ensure_numeric_series(
        summary_frame,
        "basket_history_solo_transaction_count",
        default=float("nan"),
    )
    multi_item_multi_unit_transaction_count = ensure_numeric_series(
        summary_frame,
        "basket_history_multi_item_multi_unit_transaction_count",
        default=float("nan"),
    )
    probability_sku_in_multi_item_basket = _beta_posterior_mean(
        successes=multi_item_transaction_count,
        total=transaction_count,
    ).where(transaction_count > 0.0)
    probability_sku_solo_purchase = _beta_posterior_mean(
        successes=solo_transaction_count,
        total=transaction_count,
    ).where(transaction_count > 0.0)
    probability_units_given_multi_item_basket = _beta_posterior_mean(
        successes=multi_item_multi_unit_transaction_count,
        total=multi_item_transaction_count,
    ).where(multi_item_transaction_count > 0.0)
    low_traffic_event_count = ensure_numeric_series(
        summary_frame,
        "basket_history_low_traffic_event_count",
        default=float("nan"),
    )
    low_traffic_zero_unit_event_count = ensure_numeric_series(
        summary_frame,
        "basket_history_low_traffic_zero_unit_event_count",
        default=float("nan"),
    )
    probability_zero_units_given_low_traffic = _beta_posterior_mean(
        successes=low_traffic_zero_unit_event_count,
        total=low_traffic_event_count,
    ).where(low_traffic_event_count > 0.0)
    top_companion_share = ensure_numeric_series(
        summary_frame,
        "basket_history_top_companion_sku_1_share",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0).where(transaction_count > 0.0)
    concentration_index = ensure_numeric_series(
        summary_frame,
        "basket_history_companion_concentration_index",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0).where(transaction_count > 0.0)
    companion_absence_risk_score = (
        probability_sku_in_multi_item_basket
        * top_companion_share
        * concentration_index
    ).clip(lower=0.0, upper=1.0)

    return pd.DataFrame(
        {
            "feature_probability_sku_in_multi_item_basket": probability_sku_in_multi_item_basket,
            "feature_probability_sku_solo_purchase": probability_sku_solo_purchase,
            "feature_probability_units_given_multi_item_basket": probability_units_given_multi_item_basket,
            "feature_probability_zero_units_given_low_traffic": probability_zero_units_given_low_traffic,
            "feature_companion_absence_risk_score": companion_absence_risk_score,
        },
        index=summary_frame.index,
    )


def _beta_posterior_mean(
    *,
    successes: pd.Series,
    total: pd.Series,
) -> pd.Series:
    denominator = total + _BETA_PRIOR_ALPHA + _BETA_PRIOR_BETA
    return (successes + _BETA_PRIOR_ALPHA).divide(
        denominator.replace(0.0, np.nan)
    )