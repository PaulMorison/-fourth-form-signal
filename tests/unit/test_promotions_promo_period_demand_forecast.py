"""Tests for Phase 5C promo-period demand forecast repair."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.promotions.promo_period_demand_forecast import (
    attach_promo_period_demand_forecast,
    build_promo_period_demand_forecast_frame,
    detect_flat_placeholder_forecast,
)


def _varied_frame(n: int = 50) -> pd.DataFrame:
    rng = np.arange(n, dtype=float)
    return pd.DataFrame(
        {
            "sku_number": rng.astype(int) + 1,
            "promotion_start_date": "2026-07-23",
            "promotion_end_date": "2026-07-29",
            "promotion_period_days": 7,
            "feature_non_promo_56d_avg_daily_units": 0.2 + rng * 0.03,
            "historical_units_same_discount_avg": rng * 0.5,
            "historical_units_same_or_better_discount_avg": rng * 0.6,
            "discount_percent": 20 + (rng % 5),
            "current_soh": rng % 7,
            "on_order_at_advice_time": rng % 2,
            "final_confidence_score": 0.4 + (rng % 5) * 0.1,
        }
    )


def test_model_expected_units_total_promo_validity() -> None:
    out = build_promo_period_demand_forecast_frame(_varied_frame())
    model = out["model_expected_units_total_promo"]
    assert "model_expected_units_total_promo" in out.columns
    assert pd.api.types.is_numeric_dtype(model)
    assert model.notna().all()
    assert np.isfinite(model).all()
    assert (model >= 0).all()
    assert model.nunique() > 10
    assert not ((model == 0) | (model == 1)).all()
    assert model.max() > 1.5


@pytest.mark.parametrize(
    ("values", "reason_part"),
    [
        ([0.0] * 20, "all_zero"),
        ([1.0] * 20, "top_value_share"),
        ([0.0, 1.0] * 10, "binary_0_1"),
        ([0.1429] * 20, "top_value_share"),
    ],
)
def test_detect_flat_placeholder_forecast_blocks(values: list[float], reason_part: str) -> None:
    df = pd.DataFrame({"forecast": values})
    result = detect_flat_placeholder_forecast(df, "forecast")
    assert result["is_flat_placeholder"] is True
    assert reason_part in result["reason"]


def test_detect_flat_placeholder_forecast_passes_varied() -> None:
    df = pd.DataFrame({"forecast": [0.0, 1.2, 2.4, 5.6, 8.1, 12.0, 0.7, 3.3]})
    result = detect_flat_placeholder_forecast(df, "forecast")
    assert result["is_flat_placeholder"] is False


def test_release_ready_only_for_high_or_medium_real_forecast() -> None:
    out = build_promo_period_demand_forecast_frame(_varied_frame())
    ready = out["promo_demand_release_ready_flag"].eq("YES")
    assert ready.any()
    assert out.loc[ready, "promo_demand_source_quality"].isin(["HIGH", "MEDIUM"]).all()
    assert out.loc[ready, "model_expected_units_total_promo"].gt(0).all()
    low = out["promo_demand_source_quality"].eq("LOW")
    if low.any():
        assert out.loc[low, "promo_demand_release_ready_flag"].eq("NO").all()
    unsafe = out["promo_demand_source_quality"].eq("UNSAFE")
    if unsafe.any():
        assert out.loc[unsafe, "promo_demand_release_ready_flag"].eq("NO").all()


def test_historical_proxy_does_not_become_model_release_ready() -> None:
    frame = pd.DataFrame(
        {
            "sku_number": [1, 2],
            "promotion_start_date": ["2026-07-23", "2026-07-23"],
            "promotion_end_date": ["2026-07-29", "2026-07-29"],
            "promotion_period_days": [7, 7],
            "feature_non_promo_56d_avg_daily_units": [0.0, 0.0],
            "historical_units_same_discount_avg": [5.0, 0.0],
            "historical_units_same_or_better_discount_avg": [0.0, 0.0],
            "discount_percent": [0.0, 0.0],
        }
    )
    out = build_promo_period_demand_forecast_frame(frame)
    assert out.loc[0, "promo_demand_selection_method"] in {
        "historical_proxy_fallback",
        "baseline_period_fallback",
        "unsafe_missing_promo_demand",
    }
    assert out.loc[0, "promo_demand_release_ready_flag"] == "NO"


def test_reconciliation_all_skus_present_no_nan_selected() -> None:
    frame = _varied_frame(100)
    attached = attach_promo_period_demand_forecast(frame)
    assert len(attached) == len(frame)
    assert attached["selected_promo_period_demand"].notna().all()
    unsafe = int(attached["promo_demand_selection_method"].eq("unsafe_missing_promo_demand").sum())
    assert unsafe == int((attached["selected_promo_period_demand"] <= 0).sum())


def test_legacy_flat_expected_units_not_used_as_model() -> None:
    frame = _varied_frame(30)
    frame["expected_units_total_promo"] = 1
    out = build_promo_period_demand_forecast_frame(frame)
    flat = detect_flat_placeholder_forecast(frame, "expected_units_total_promo")
    assert flat["is_flat_placeholder"] is True
    assert out["model_expected_units_total_promo"].nunique() > 5
