from __future__ import annotations

"""Cannibalisation-pressure ft module."""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_text_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import build_promotion_store_event_key


def apply_ft_cannibalisation_pressure(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add concurrent-offer overlap and cannibalisation pressure features."""

    del reference_frame
    working = frame.copy()
    working["promotion_store_event_key"] = build_promotion_store_event_key(working)
    overlap_metrics = _compute_overlap_metrics(working)
    working = working.merge(overlap_metrics, on="promotion_row_key", how="left")
    department_key = ensure_text_series(working, "department")
    department_counts = working.groupby([working["promotion_store_event_key"], department_key])["promotion_row_key"].transform("count")
    event_counts = working.groupby("promotion_store_event_key")["promotion_row_key"].transform("count")
    working["feature_department_intensity"] = safe_ratio(
        department_counts.astype(float),
        event_counts.astype(float),
    )
    working["feature_cannibalisation_pressure_proxy"] = safe_ratio(
        working["feature_category_overlap_discount_sum"].fillna(0.0),
        working["feature_store_overlap_count"].fillna(0.0).replace(0.0, np.nan),
    )
    return working


def _compute_overlap_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    overlap_frames: list[pd.DataFrame] = []
    for _, store_group in frame.groupby("store_number_key", sort=False):
        overlap_frames.append(_compute_store_overlap_metrics(store_group))
    if not overlap_frames:
        return pd.DataFrame(
            columns=[
                "promotion_row_key",
                "feature_store_overlap_count",
                "feature_category_overlap_discount_sum",
                "feature_supplier_overlap_discount_sum",
                "feature_substitute_overlap_discount_sum",
                "feature_local_promotional_field_density_score",
            ]
        )
    return pd.concat(overlap_frames, ignore_index=True)


def _compute_store_overlap_metrics(store_group: pd.DataFrame) -> pd.DataFrame:
    ordered_group = store_group.sort_values(
        ["promotion_start_date_date", "promotional_end_date_date", "promotion_row_key"],
        kind="mergesort",
    ).reset_index(drop=True)
    row_count = len(ordered_group.index)
    overlap_count = np.zeros(row_count, dtype="float64")
    category_discount_sum = np.zeros(row_count, dtype="float64")
    supplier_discount_sum = np.zeros(row_count, dtype="float64")
    substitute_discount_sum = np.zeros(row_count, dtype="float64")
    local_field_density = np.zeros(row_count, dtype="float64")

    promotion_row_keys = ensure_text_series(ordered_group, "promotion_row_key").to_numpy()
    categories = ensure_text_series(ordered_group, "category").to_numpy()
    suppliers = ordered_group.get("inferred_supplier_number", pd.Series(0.0, index=ordered_group.index))
    suppliers = pd.to_numeric(suppliers, errors="coerce").fillna(0.0).to_numpy(dtype="float64")
    discounts = pd.to_numeric(
        ordered_group.get("feature_discount_depth_pct", pd.Series(0.0, index=ordered_group.index)),
        errors="coerce",
    ).fillna(0.0).to_numpy(dtype="float64")
    baselines = pd.to_numeric(
        ordered_group.get("baseline_expected_units", pd.Series(0.0, index=ordered_group.index)),
        errors="coerce",
    ).fillna(0.0).to_numpy(dtype="float64")
    price_ratios = pd.to_numeric(
        ordered_group.get("feature_promo_price_ratio_vs_normal", pd.Series(0.0, index=ordered_group.index)),
        errors="coerce",
    ).fillna(0.0).to_numpy(dtype="float64")
    start_dates = pd.to_datetime(ordered_group["promotion_start_date_date"], errors="coerce")
    end_dates = pd.to_datetime(ordered_group["promotional_end_date_date"], errors="coerce")

    active_indices: list[int] = []
    for current_index, current_start in enumerate(start_dates):
        current_end = end_dates.iloc[current_index]
        if pd.isna(current_start) or pd.isna(current_end):
            continue
        active_indices = [
            sibling_index
            for sibling_index in active_indices
            if pd.notna(end_dates.iloc[sibling_index]) and end_dates.iloc[sibling_index] >= current_start
        ]
        current_category = categories[current_index]
        current_supplier = suppliers[current_index]
        current_discount = discounts[current_index]
        current_baseline = baselines[current_index]
        current_price_ratio = price_ratios[current_index]
        for sibling_index in active_indices:
            overlap_count[current_index] += 1.0
            overlap_count[sibling_index] += 1.0
            sibling_discount = discounts[sibling_index]
            sibling_baseline = baselines[sibling_index]
            local_field_density[current_index] += sibling_discount * sibling_baseline
            local_field_density[sibling_index] += current_discount * current_baseline
            if categories[sibling_index] == current_category:
                category_discount_sum[current_index] += sibling_discount
                category_discount_sum[sibling_index] += current_discount
                if abs(price_ratios[sibling_index] - current_price_ratio) <= 0.2:
                    substitute_discount_sum[current_index] += sibling_discount
                    substitute_discount_sum[sibling_index] += current_discount
            if suppliers[sibling_index] == current_supplier:
                supplier_discount_sum[current_index] += sibling_discount
                supplier_discount_sum[sibling_index] += current_discount
        active_indices.append(current_index)

    return pd.DataFrame(
        {
            "promotion_row_key": promotion_row_keys,
            "feature_store_overlap_count": overlap_count,
            "feature_category_overlap_discount_sum": category_discount_sum,
            "feature_supplier_overlap_discount_sum": supplier_discount_sum,
            "feature_substitute_overlap_discount_sum": substitute_discount_sum,
            "feature_local_promotional_field_density_score": local_field_density,
        }
    )
