from __future__ import annotations

"""Store+SKU discount-elasticity summaries from strict prior completed promotions."""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series, first_non_null_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import coerce_promotions_frame_types, normalize_discount_decimal


DISCOUNT_ELASTICITY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_discount_elasticity_estimate",
    "feature_discount_elasticity_abs",
    "feature_discount_elasticity_confidence_score",
    "feature_discount_response_slope",
    "feature_discount_response_r_squared",
    "feature_discount_response_event_count",
    "feature_discount_response_direction_consistent_flag",
    "feature_discount_response_instability_score",
)


def apply_ft_discount_elasticity(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append conservative discount-elasticity summaries."""

    candidate = frame.copy()
    history_source = reference_frame if reference_frame is not None else candidate
    candidate_typed = coerce_promotions_frame_types(candidate)
    history_typed = _build_discount_elasticity_history_frame(history_source)

    derived_rows: list[dict[str, float]] = []
    grouped_history: dict[tuple[object, object], pd.DataFrame] = {}
    for key, group in history_typed.groupby(["store_number_key", "sku_number_key"], dropna=False, sort=False):
        grouped_history[tuple(key)] = group.loc[group["_promotion_end"].notna()].sort_values(
            "_promotion_end",
            kind="mergesort",
        )

    candidate_start_dates = pd.to_datetime(candidate_typed.get("promotion_start_date_date"), errors="coerce")
    candidate_discount = normalize_discount_decimal(
        ensure_numeric_series(candidate_typed, "discount_percent", default=float("nan"))
    )
    store_keys = candidate_typed.get("store_number_key")
    sku_keys = candidate_typed.get("sku_number_key")

    for row_index in range(len(candidate_typed.index)):
        candidate_start_date = candidate_start_dates.iloc[row_index]
        candidate_key = (
            store_keys.iloc[row_index] if store_keys is not None else None,
            sku_keys.iloc[row_index] if sku_keys is not None else None,
        )
        if pd.isna(candidate_start_date):
            derived_rows.append(_empty_elasticity_row())
            continue
        prior_rows = grouped_history.get(candidate_key)
        if prior_rows is None or prior_rows.empty:
            derived_rows.append(_empty_elasticity_row())
            continue
        strict_prior_rows = prior_rows.loc[prior_rows["_promotion_end"] < candidate_start_date].copy()
        usable_rows = strict_prior_rows.loc[
            strict_prior_rows["_discount_decimal"].gt(0.0)
            & strict_prior_rows["_uplift_ratio"].notna()
        ].copy()
        if usable_rows.empty:
            derived_rows.append(_empty_elasticity_row())
            continue
        x_values = pd.to_numeric(usable_rows["_discount_decimal"], errors="coerce")
        y_values = pd.to_numeric(usable_rows["_uplift_ratio"], errors="coerce")
        valid_mask = x_values.notna() & y_values.notna()
        x_values = x_values.loc[valid_mask]
        y_values = y_values.loc[valid_mask]
        if len(x_values.index) < 2 or x_values.nunique(dropna=True) < 2:
            derived_rows.append(
                {
                    "feature_discount_elasticity_estimate": 0.0,
                    "feature_discount_elasticity_abs": 0.0,
                    "feature_discount_elasticity_confidence_score": 0.0,
                    "feature_discount_response_slope": 0.0,
                    "feature_discount_response_r_squared": 0.0,
                    "feature_discount_response_event_count": float(len(x_values.index)),
                    "feature_discount_response_direction_consistent_flag": 0.0,
                    "feature_discount_response_instability_score": float("nan"),
                }
            )
            continue
        x_mean = float(x_values.mean())
        y_mean = float(y_values.mean())
        variance_x = float(((x_values - x_mean) ** 2).sum())
        covariance_xy = float(((x_values - x_mean) * (y_values - y_mean)).sum())
        slope = covariance_xy / variance_x if variance_x > 0.0 else 0.0
        intercept = y_mean - (slope * x_mean)
        predicted_y = intercept + (slope * x_values)
        residual_sum_squares = float(((y_values - predicted_y) ** 2).sum())
        total_sum_squares = float(((y_values - y_mean) ** 2).sum())
        r_squared = 1.0 - (residual_sum_squares / total_sum_squares) if total_sum_squares > 0.0 else 0.0
        paired_direction = (((x_values - x_mean) * (y_values - y_mean)) >= 0.0).mean()
        direction_consistent_flag = float((slope > 0.0) and (paired_direction >= 0.60))
        instability_score = safe_ratio(
            pd.Series(float(y_values.std(ddof=0))),
            pd.Series(abs(y_mean) if abs(y_mean) > 0.0 else np.nan),
        ).iloc[0]
        elasticity_estimate = slope * float(candidate_discount.iloc[row_index] if not pd.isna(candidate_discount.iloc[row_index]) else 0.0)
        confidence_score = float(
            np.clip(
                min(1.0, len(x_values.index) / 5.0)
                * min(1.0, x_values.nunique(dropna=True) / 3.0)
                * max(r_squared, 0.0)
                * (1.0 if direction_consistent_flag == 1.0 else 0.5)
                * (1.0 / (1.0 + float(instability_score if not pd.isna(instability_score) else 5.0))),
                0.0,
                1.0,
            )
        )
        derived_rows.append(
            {
                "feature_discount_elasticity_estimate": float(elasticity_estimate),
                "feature_discount_elasticity_abs": float(abs(elasticity_estimate)),
                "feature_discount_elasticity_confidence_score": confidence_score,
                "feature_discount_response_slope": float(slope),
                "feature_discount_response_r_squared": float(np.clip(r_squared, 0.0, 1.0)),
                "feature_discount_response_event_count": float(len(x_values.index)),
                "feature_discount_response_direction_consistent_flag": direction_consistent_flag,
                "feature_discount_response_instability_score": float(instability_score) if not pd.isna(instability_score) else float("nan"),
            }
        )
    derived_columns = pd.DataFrame(
        derived_rows,
        index=candidate.index,
        columns=list(DISCOUNT_ELASTICITY_FEATURE_COLUMNS),
    )
    base_columns = candidate.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _build_discount_elasticity_history_frame(frame: pd.DataFrame) -> pd.DataFrame:
    history = coerce_promotions_frame_types(frame).copy()
    promo_window_days = first_non_null_series(history, ("live_promo_window_days", "promo_days"), positive_only=True)
    baseline_expected_units = ensure_numeric_series(history, "baseline_expected_units", default=float("nan"))
    baseline_daily_units = first_non_null_series(
        history,
        ("baseline_daily_units", "feature_pre_promo_baseline_daily_units", "pre_28d_avg_daily_units", "pre_56d_avg_daily_units"),
        positive_only=True,
    )
    baseline_reference_units = baseline_expected_units.where(
        baseline_expected_units.notna(),
        baseline_daily_units * promo_window_days.where(promo_window_days > 0.0, np.nan),
    )
    actual_units_sold = first_non_null_series(
        history,
        ("actual_units_sold_promo", "target_actual_units_sold", "actual_units_sold"),
    )
    history["_promotion_end"] = pd.to_datetime(history.get("promotional_end_date_date"), errors="coerce")
    history["_discount_decimal"] = normalize_discount_decimal(
        ensure_numeric_series(history, "discount_percent", default=float("nan"))
    )
    history["_uplift_ratio"] = safe_ratio(
        actual_units_sold - baseline_reference_units,
        baseline_reference_units.where(baseline_reference_units > 0.0, np.nan),
    )
    return history


def _empty_elasticity_row() -> dict[str, float]:
    return {
        "feature_discount_elasticity_estimate": 0.0,
        "feature_discount_elasticity_abs": 0.0,
        "feature_discount_elasticity_confidence_score": 0.0,
        "feature_discount_response_slope": 0.0,
        "feature_discount_response_r_squared": 0.0,
        "feature_discount_response_event_count": 0.0,
        "feature_discount_response_direction_consistent_flag": 0.0,
        "feature_discount_response_instability_score": float("nan"),
    }