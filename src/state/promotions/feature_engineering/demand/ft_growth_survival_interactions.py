from __future__ import annotations

"""Disciplined interactions between demand shape and survival convexity.

Business meaning:
- exposes a small number of directional combinations where growth shape changes
  the interpretation of inventory and late-promotion upside risk

Leakage guard:
- uses only features already produced by leakage-guarded ft modules

Output columns are declared in GROWTH_SURVIVAL_INTERACTION_FEATURE_COLUMNS.
"""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


GROWTH_SURVIVAL_INTERACTION_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_growth_survival_acceleration_x_internal_convex_upside_proxy_score",
    "feature_growth_survival_decay_x_inventory_risk_score",
)

FEATURE_COLUMNS: tuple[str, ...] = GROWTH_SURVIVAL_INTERACTION_FEATURE_COLUMNS

REQUIRED_COLUMNS: tuple[str, ...] = (
    "feature_growth_curve_acceleration_score",
    "feature_growth_curve_decay_persistence_score",
    "feature_survival_internal_convex_upside_proxy_score",
    "feature_overhang_risk",
)


def apply_ft_growth_survival_interactions(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append two interpretable growth/survival interaction features."""

    del reference_frame
    _validate_required_columns(frame)

    working = frame.copy()
    acceleration_score = ensure_numeric_series(working, "feature_growth_curve_acceleration_score").clip(lower=0.0, upper=1.0)
    decay_persistence_score = ensure_numeric_series(working, "feature_growth_curve_decay_persistence_score").clip(lower=0.0, upper=1.0)
    convex_upside_proxy = ensure_numeric_series(working, "feature_survival_internal_convex_upside_proxy_score").clip(lower=0.0, upper=1.0)
    inventory_risk_score = ensure_numeric_series(working, "feature_overhang_risk").clip(lower=0.0, upper=1.0)

    derived_columns = pd.DataFrame(
        {
            "feature_growth_survival_acceleration_x_internal_convex_upside_proxy_score": (acceleration_score * convex_upside_proxy).clip(lower=0.0, upper=1.0),
            "feature_growth_survival_decay_x_inventory_risk_score": (decay_persistence_score * inventory_risk_score).clip(lower=0.0, upper=1.0),
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _validate_required_columns(frame: pd.DataFrame) -> None:
    missing_columns = [column_name for column_name in REQUIRED_COLUMNS if column_name not in frame.columns]
    if missing_columns:
        raise ValueError(
            "ft_growth_survival_interactions missing required columns: "
            + ", ".join(missing_columns)
        )