from __future__ import annotations

import pandas as pd

from state.promotions.feature_engineering.demand.probability.ft_probability_shared_helpers import (
    clip_zero_one,
    numeric_series,
    rowwise_nanmean,
)


PROBABILITY_COMPANION_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_probability_sold_in_multi_item_basket_rate",
    "feature_probability_sold_as_solo_item_rate",
    "feature_probability_companion_dependency_score",
    "feature_probability_basket_depth_when_sold",
    "feature_probability_companion_overallocation_risk_score",
)


def build_probability_companion_features(
    probability_input_frame: pd.DataFrame,
) -> pd.DataFrame:
    sold_in_multi_item_basket_rate = clip_zero_one(
        numeric_series(
            probability_input_frame,
            "probability_sold_in_multi_item_basket_rate",
        )
    )
    sold_as_solo_item_rate = clip_zero_one(
        numeric_series(
            probability_input_frame,
            "probability_sold_as_solo_item_rate",
        )
    )
    companion_dependency_score = clip_zero_one(
        numeric_series(
            probability_input_frame,
            "probability_companion_dependency_score_prior_mean",
        )
    )
    basket_depth_when_sold = numeric_series(
        probability_input_frame,
        "probability_basket_depth_when_sold_mean",
    )
    companion_overallocation_risk_proxy = numeric_series(
        probability_input_frame,
        "probability_companion_overallocation_risk_proxy",
    )
    companion_overallocation_risk_score = rowwise_nanmean(
        [
            clip_zero_one(companion_overallocation_risk_proxy),
            clip_zero_one(companion_dependency_score * (1.0 - sold_as_solo_item_rate)),
        ],
        lower=0.0,
        upper=1.0,
    )

    return pd.DataFrame(
        {
            "feature_probability_sold_in_multi_item_basket_rate": sold_in_multi_item_basket_rate,
            "feature_probability_sold_as_solo_item_rate": sold_as_solo_item_rate,
            "feature_probability_companion_dependency_score": companion_dependency_score,
            "feature_probability_basket_depth_when_sold": basket_depth_when_sold,
            "feature_probability_companion_overallocation_risk_score": companion_overallocation_risk_score,
        },
        index=probability_input_frame.index,
    )