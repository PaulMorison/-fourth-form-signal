from __future__ import annotations

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


STOCK_CONSTRAINED_DEMAND_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_stock_constrained_history_flag",
    "feature_lost_sales_risk_score",
    "feature_stock_constrained_evidence_promo_count",
)


def build_stock_constrained_demand_features(summary_frame: pd.DataFrame) -> pd.DataFrame:
    evidence_count = ensure_numeric_series(
        summary_frame,
        "basket_history_stock_constrained_event_count",
        default=0.0,
    )
    event_share = ensure_numeric_series(
        summary_frame,
        "basket_history_stock_constrained_event_share",
        default=float("nan"),
    ).where(evidence_count > 0.0)
    lost_sales_risk_score = ensure_numeric_series(
        summary_frame,
        "basket_history_lost_sales_proxy_mean",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0).where(evidence_count > 0.0)
    stock_constrained_history_flag = (
        (event_share >= 0.25) & (evidence_count >= 2.0)
    ).astype(float).where(evidence_count > 0.0)

    return pd.DataFrame(
        {
            "feature_stock_constrained_history_flag": stock_constrained_history_flag,
            "feature_lost_sales_risk_score": lost_sales_risk_score,
            "feature_stock_constrained_evidence_promo_count": evidence_count,
        },
        index=summary_frame.index,
    )