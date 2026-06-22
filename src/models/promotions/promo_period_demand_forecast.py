from __future__ import annotations

"""SKU-level promo-period demand forecast repair (Phase 5C).

Produces ``model_expected_units_total_promo`` and governed selection fields without
overwriting legacy flat placeholder columns or mixing model output with fallbacks.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_UPLIFT_MULTIPLIER_MIN = 0.25
DEFAULT_UPLIFT_MULTIPLIER_MAX = 8.0
FLAT_TOP_VALUE_SHARE_THRESHOLD = 0.95
FLAT_UNIQUE_RATIO_THRESHOLD = 0.01
PER_DAY_ARTIFACT_VALUES = frozenset({0.1429, 0.142857, 0.1428571})

PROMO_FORECAST_OUTPUT_COLUMNS: tuple[str, ...] = (
    "model_expected_units_total_promo",
    "historical_proxy_expected_units_total_promo",
    "baseline_expected_units_total_promo",
    "selected_promo_period_demand",
    "promo_demand_model_source",
    "promo_demand_source_lineage",
    "promo_demand_source_quality",
    "promo_demand_selection_method",
    "promo_demand_release_ready_flag",
    "promo_demand_blocker_reason",
    "promo_demand_uplift_multiplier",
    "promo_demand_stock_availability_adjustment",
    "promo_demand_recent_momentum_adjustment",
    "promo_demand_confidence_adjustment",
    "promo_demand_baseline_daily_units",
)


def detect_flat_placeholder_forecast(df: pd.DataFrame, column: str) -> dict[str, Any]:
    """Detect flat/binary/constant placeholder forecast columns."""
    if column not in df.columns:
        return {
            "column": column,
            "row_count": int(len(df)),
            "non_null_count": 0,
            "unique_count": 0,
            "top_value": np.nan,
            "top_value_share": 1.0,
            "is_flat_placeholder": True,
            "reason": "column_missing",
        }

    s = pd.to_numeric(df[column], errors="coerce")
    row_count = int(len(df))
    non_null = s.dropna()
    non_null_count = int(non_null.shape[0])
    if non_null_count == 0:
        return {
            "column": column,
            "row_count": row_count,
            "non_null_count": 0,
            "unique_count": 0,
            "top_value": np.nan,
            "top_value_share": 1.0,
            "is_flat_placeholder": True,
            "reason": "all_null",
        }

    unique_count = int(non_null.nunique(dropna=True))
    value_counts = non_null.value_counts(normalize=True)
    top_value = float(value_counts.index[0])
    top_value_share = float(value_counts.iloc[0])
    reasons: list[str] = []

    if non_null_count > 0 and (non_null <= 0).all():
        reasons.append("all_zero")
    if unique_count <= 2 and set(non_null.round(6).unique()).issubset({0.0, 1.0}):
        reasons.append("binary_0_1")
    if unique_count == 1:
        reasons.append("zero_variance")
    if top_value_share >= FLAT_TOP_VALUE_SHARE_THRESHOLD:
        reasons.append(f"top_value_share_{top_value_share:.3f}")
    if row_count > 0 and unique_count / row_count <= FLAT_UNIQUE_RATIO_THRESHOLD:
        reasons.append("low_unique_ratio")
    if any(abs(float(v) - artifact) < 1e-4 for v in non_null.unique() for artifact in PER_DAY_ARTIFACT_VALUES):
        if unique_count <= 3:
            reasons.append("constant_per_day_artifact")

    is_flat = bool(reasons)
    return {
        "column": column,
        "row_count": row_count,
        "non_null_count": non_null_count,
        "unique_count": unique_count,
        "top_value": top_value,
        "top_value_share": top_value_share,
        "is_flat_placeholder": is_flat,
        "reason": "; ".join(reasons) if reasons else "",
    }


def _first_numeric(frame: pd.DataFrame, names: tuple[str, ...], index: pd.Index | None = None) -> pd.Series:
    idx = index if index is not None else frame.index
    for name in names:
        for col in (name, f"{name}_audit", f"{name}_feat"):
            if col in frame.columns:
                return pd.to_numeric(frame[col], errors="coerce").fillna(0.0).reindex(idx).fillna(0.0)
    return pd.Series(0.0, index=idx)


def _promo_window_days(frame: pd.DataFrame) -> pd.Series:
    days = _first_numeric(
        frame,
        (
            "promotion_period_days",
            "promotion_period_days_feat",
            "promo_window_days",
            "live_promo_window_days",
            "promo_days",
        ),
    ).replace(0.0, np.nan)
    if {"promotion_start_date", "promotion_end_date"}.issubset(frame.columns):
        derived = (
            pd.to_datetime(frame["promotion_end_date"], errors="coerce")
            - pd.to_datetime(frame["promotion_start_date"], errors="coerce")
        ).dt.days.add(1).astype(float)
        days = days.where(days.notna() & days.gt(0), derived)
    return days.fillna(7.0).clip(lower=1.0)


def _valid_promo_window(frame: pd.DataFrame, promo_days: pd.Series) -> pd.Series:
    if not {"promotion_start_date", "promotion_end_date"}.issubset(frame.columns):
        return promo_days.gt(0)
    start = pd.to_datetime(frame["promotion_start_date"], errors="coerce")
    end = pd.to_datetime(frame["promotion_end_date"], errors="coerce")
    return start.notna() & end.notna() & end.ge(start) & promo_days.gt(0)


def build_promo_period_demand_forecast_frame(
    frame: pd.DataFrame,
    *,
    uplift_multiplier_max: float = DEFAULT_UPLIFT_MULTIPLIER_MAX,
) -> pd.DataFrame:
    """Build governed promo-period demand forecast columns at SKU grain."""
    if frame.empty:
        return pd.DataFrame(columns=list(PROMO_FORECAST_OUTPUT_COLUMNS), index=frame.index)

    idx = frame.index
    promo_days = _promo_window_days(frame)
    valid_window = _valid_promo_window(frame, promo_days)
    tiny = 1e-6

    feature_baseline = _first_numeric(
        frame,
        (
            "feature_non_promo_56d_avg_daily_units",
            "feature_non_promo_30d_avg_daily_units",
            "baseline_daily_units",
            "feature_pre_promo_baseline_daily_units",
        ),
    )
    lead_up = _first_numeric(frame, ("lead_up_demand_units",))
    lead_days = _first_numeric(frame, ("days_to_promo_start", "lead_days_to_promo_start")).replace(0.0, np.nan)
    from_lead = (lead_up / lead_days).fillna(0.0)
    independent_baseline = feature_baseline.gt(tiny) | from_lead.gt(tiny)

    baseline_daily = feature_baseline.where(feature_baseline.gt(0), from_lead)

    same_discount_total = _first_numeric(
        frame,
        ("historical_units_same_discount_avg", "feature_historical_units_same_discount_avg"),
    )
    same_or_better_total = _first_numeric(
        frame,
        ("historical_units_same_or_better_discount_avg", "feature_historical_units_same_or_better_discount_avg"),
    )
    hist_fallback_daily = (same_discount_total / promo_days).where(same_discount_total.gt(0), 0.0)
    baseline_daily = baseline_daily.where(baseline_daily.gt(0), hist_fallback_daily)

    same_discount_daily = (same_discount_total / promo_days).where(same_discount_total.gt(0), 0.0)
    same_or_better_daily = (same_or_better_total / promo_days).where(same_or_better_total.gt(0), 0.0)

    discount_pct = _first_numeric(
        frame,
        ("discount_percent", "feature_discount_depth_pct", "promo_discount_percent"),
    ).clip(lower=0.0, upper=100.0)
    discount_depth = discount_pct / 100.0

    daily_30 = _first_numeric(frame, ("feature_non_promo_30d_avg_daily_units",))
    daily_56 = _first_numeric(frame, ("feature_non_promo_56d_avg_daily_units",))
    with np.errstate(divide="ignore", invalid="ignore"):
        momentum = (daily_30 / daily_56.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    momentum = momentum.clip(lower=0.5, upper=2.0)

    confidence = _first_numeric(frame, ("final_confidence_score", "model_confidence_percent"))
    confidence = confidence.where(confidence.le(1.0), confidence / 100.0).clip(lower=0.0, upper=1.0)
    confidence_adj = (0.85 + 0.15 * confidence).clip(lower=0.75, upper=1.0)

    soh = _first_numeric(frame, ("current_soh", "current_soh_units")).clip(lower=0.0)
    on_order = _first_numeric(frame, ("on_order_at_advice_time", "qty_on_order_units", "on_order_units"))
    stock_adj = pd.Series(1.0, index=idx)
    stock_adj = stock_adj.where(~((soh + on_order).le(0) & same_discount_total.gt(0)), 0.85)

    baseline_floor = baseline_daily * promo_days
    historical_proxy = same_discount_total.where(same_discount_total.gt(0), same_or_better_total).round(3)
    baseline_expected = baseline_floor.round(3)

    tiny = 1e-6
    same_uplift = (same_discount_daily / baseline_daily.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
    sob_uplift = (same_or_better_daily / baseline_daily.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
    discount_uplift = 1.0 + discount_depth * 0.35

    uplift_parts: list[pd.Series] = []
    uplift_weights: list[float] = []
    if same_discount_total.gt(0).any():
        uplift_parts.append(same_uplift.fillna(1.0))
        uplift_weights.append(0.45)
    if same_or_better_total.gt(0).any():
        uplift_parts.append(sob_uplift.fillna(1.0))
        uplift_weights.append(0.25)
    if discount_pct.gt(0).any():
        uplift_parts.append(discount_uplift)
        uplift_weights.append(0.20)
    if uplift_parts:
        weight_sum = float(sum(uplift_weights))
        uplift = sum(part * weight for part, weight in zip(uplift_parts, uplift_weights)) / weight_sum
    else:
        uplift = pd.Series(1.0, index=idx)
    uplift = uplift.clip(lower=DEFAULT_UPLIFT_MULTIPLIER_MIN, upper=uplift_multiplier_max)

    model_expected = (
        baseline_daily * promo_days * uplift * stock_adj * momentum * confidence_adj
    ).clip(lower=0.0).replace([np.inf, -np.inf], 0.0).fillna(0.0).round(3)

    legacy_model = _first_numeric(
        frame,
        ("model_expected_units_total_promo", "predicted_units_total_promo", "expected_units_total_promo"),
    )
    legacy_flat = detect_flat_placeholder_forecast(
        pd.DataFrame({"legacy": legacy_model}), "legacy"
    )["is_flat_placeholder"]
    if not legacy_flat and legacy_model.gt(0).any():
        model_expected = legacy_model.where(legacy_model.gt(0), model_expected).round(3)

    has_same = same_discount_total.gt(0)
    has_sob = same_or_better_total.gt(0)
    has_baseline = baseline_daily.gt(tiny)
    has_discount = discount_pct.gt(0)

    quality = pd.Series("UNSAFE", index=idx, dtype=object)
    quality = quality.where(
        ~(
            valid_window
            & independent_baseline
            & has_baseline
            & model_expected.gt(0)
            & (has_same | has_sob)
        ),
        "HIGH",
    )
    quality = quality.where(
        ~(
            valid_window
            & independent_baseline
            & has_baseline
            & model_expected.gt(0)
            & ~quality.eq("HIGH")
            & has_discount
        ),
        "MEDIUM",
    )
    quality = quality.where(
        ~(
            valid_window
            & has_baseline
            & model_expected.gt(0)
            & ~quality.isin(["HIGH", "MEDIUM"])
        ),
        "LOW",
    )
    quality = quality.where(
        ~(model_expected.le(0) & historical_proxy.gt(0)),
        "LOW",
    )

    row_flat = model_expected.le(0)
    per_row_placeholder = (model_expected.eq(1.0) & ~has_same & ~has_sob) | (
        model_expected.gt(0) & model_expected.lt(1.01)
    )
    quality = quality.where(~(per_row_placeholder & quality.ne("UNSAFE")), "UNSAFE")
    row_flat = row_flat | per_row_placeholder

    release_ready = (
        quality.isin(["HIGH", "MEDIUM"])
        & model_expected.gt(0)
        & valid_window
        & ~row_flat
    )

    selected = pd.Series(0.0, index=idx)
    selection_method = pd.Series("unsafe_missing_promo_demand", index=idx, dtype=object)
    model_source = pd.Series("model_expected_units_total_promo", index=idx, dtype=object)
    lineage = pd.Series("models.promo_period_demand_forecast:model_expected_units_total_promo", index=idx, dtype=object)
    blocker = pd.Series("", index=idx, dtype=object)

    take_model = release_ready & selected.le(0)
    selected = selected.where(~take_model, model_expected)
    selection_method = selection_method.where(~take_model, "model_release_ready_forecast")
    model_source = model_source.where(~take_model, "model_expected_units_total_promo")
    lineage = lineage.where(~take_model, "models.promo_period_demand_forecast:model_expected_units_total_promo")

    take_hist = (~release_ready) & historical_proxy.gt(0) & selected.le(0)
    selected = selected.where(~take_hist, historical_proxy)
    selection_method = selection_method.where(~take_hist, "historical_proxy_fallback")
    model_source = model_source.where(~take_hist, "historical_proxy_expected_units_total_promo")
    lineage = lineage.where(
        ~take_hist,
        np.where(
            same_discount_total.gt(0),
            "operator-audit:historical_units_same_discount_avg",
            "operator-audit:historical_units_same_or_better_discount_avg",
        ),
    )

    take_base = selected.le(0) & baseline_expected.ge(1.0)
    selected = selected.where(~take_base, baseline_expected)
    selection_method = selection_method.where(~take_base, "baseline_period_fallback")
    model_source = model_source.where(~take_base, "baseline_expected_units_total_promo")
    lineage = lineage.where(~take_base, "derived:baseline_daily_units_x_promo_days")

    missing = selected.le(0)
    selection_method = selection_method.where(~missing, "unsafe_missing_promo_demand")
    model_source = model_source.where(~missing, "missing_promo_period_demand")
    lineage = lineage.where(~missing, "none")
    blocker = blocker.where(
        ~missing,
        np.where(~valid_window, "invalid_promo_window", "insufficient_promo_demand_evidence"),
    )
    blocker = blocker.where(
        ~(release_ready & selected.gt(0)),
        "",
    )
    blocker = blocker.where(
        ~((~release_ready) & selected.gt(0)),
        np.where(quality.eq("UNSAFE"), "model_forecast_not_release_ready", "using_governed_proxy"),
    )

    return pd.DataFrame(
        {
            "model_expected_units_total_promo": model_expected,
            "historical_proxy_expected_units_total_promo": historical_proxy,
            "baseline_expected_units_total_promo": baseline_expected,
            "selected_promo_period_demand": selected.round(3),
            "promo_demand_model_source": model_source,
            "promo_demand_source_lineage": lineage.astype(str),
            "promo_demand_source_quality": quality,
            "promo_demand_selection_method": selection_method,
            "promo_demand_release_ready_flag": release_ready.map({True: "YES", False: "NO"}),
            "promo_demand_blocker_reason": blocker,
            "promo_demand_uplift_multiplier": uplift.round(4),
            "promo_demand_stock_availability_adjustment": stock_adj.round(4),
            "promo_demand_recent_momentum_adjustment": momentum.round(4),
            "promo_demand_confidence_adjustment": confidence_adj.round(4),
            "promo_demand_baseline_daily_units": baseline_daily.round(6),
        },
        index=idx,
    )


def attach_promo_period_demand_forecast(frame: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
    """Return a copy of ``frame`` with Phase 5C forecast columns attached."""
    forecast = build_promo_period_demand_forecast_frame(frame, **kwargs)
    out = frame.copy()
    for column in PROMO_FORECAST_OUTPUT_COLUMNS:
        out[column] = forecast[column]
    return out


def forecast_distribution_row(df: pd.DataFrame, column: str) -> dict[str, Any]:
    """Summarize one forecast column for diagnostics."""
    flat = detect_flat_placeholder_forecast(df, column)
    s = pd.to_numeric(df[column], errors="coerce") if column in df.columns else pd.Series(dtype=float)
    if s.notna().sum() == 0:
        return {
            "column": column,
            "row_count": int(len(df)),
            "non_null_count": 0,
            "zero_count": 0,
            "one_count": 0,
            "unique_count": 0,
            "min": np.nan,
            "p05": np.nan,
            "p25": np.nan,
            "median": np.nan,
            "mean": np.nan,
            "p75": np.nan,
            "p95": np.nan,
            "max": np.nan,
            "top_value": flat["top_value"],
            "top_value_share": flat["top_value_share"],
            "flat_placeholder_flag": flat["is_flat_placeholder"],
            "flat_placeholder_reason": flat["reason"],
        }
    return {
        "column": column,
        "row_count": int(len(df)),
        "non_null_count": int(s.notna().sum()),
        "zero_count": int((s == 0).sum()),
        "one_count": int((s == 1).sum()),
        "unique_count": int(s.nunique(dropna=True)),
        "min": float(s.min()),
        "p05": float(s.quantile(0.05)),
        "p25": float(s.quantile(0.25)),
        "median": float(s.median()),
        "mean": float(s.mean()),
        "p75": float(s.quantile(0.75)),
        "p95": float(s.quantile(0.95)),
        "max": float(s.max()),
        "top_value": flat["top_value"],
        "top_value_share": flat["top_value_share"],
        "flat_placeholder_flag": flat["is_flat_placeholder"],
        "flat_placeholder_reason": flat["reason"],
    }


def write_phase5c01_diagnostics(
    frame: pd.DataFrame,
    diagnostics_dir: Path,
    *,
    promotion_name: str = "",
    commercial_release_score: int | None = None,
    primary_blocker: str = "",
) -> None:
    """Write Phase 5C.01 diagnostics CSVs and memo."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    forecast = build_promo_period_demand_forecast_frame(frame)

    candidate_columns = [
        "expected_units_total_promo",
        "expected_promo_demand",
        "projected_promotional_units",
        "expected_units_per_day",
        "model_expected_units_total_promo",
        "historical_proxy_expected_units_total_promo",
        "baseline_expected_units_total_promo",
        "selected_promo_period_demand",
    ]
    dist_rows = [forecast_distribution_row(frame, col) for col in candidate_columns if col in frame.columns]
    dist_rows.append(forecast_distribution_row(forecast, "model_expected_units_total_promo"))
    dist_rows.append(forecast_distribution_row(forecast, "selected_promo_period_demand"))
    pd.DataFrame(dist_rows).to_csv(diagnostics_dir / "phase5c01_forecast_distribution.csv", index=False)

    count_specs = [
        ("promo_demand_model_source", forecast["promo_demand_model_source"]),
        ("promo_demand_source_quality", forecast["promo_demand_source_quality"]),
        ("promo_demand_release_ready_flag", forecast["promo_demand_release_ready_flag"]),
        ("promo_demand_selection_method", forecast["promo_demand_selection_method"]),
    ]
    quality_counts: list[dict[str, Any]] = []
    for field_name, series in count_specs:
        for value, count in series.value_counts().items():
            quality_counts.append({"field": field_name, "value": value, "count": int(count)})
    pd.DataFrame(quality_counts).to_csv(diagnostics_dir / "phase5c01_source_quality_counts.csv", index=False)

    merged = frame.copy()
    for column in PROMO_FORECAST_OUTPUT_COLUMNS:
        merged[column] = forecast[column]

    sku_col = "sku_number" if "sku_number" in merged.columns else merged.index.astype(str)
    desc_col = merged.get("sku_description", pd.Series("", index=merged.index))
    sample_cols = [
        "sku_number", "sku_description", "promotion_name", "promotion_start_date", "promotion_end_date",
        "promo_demand_baseline_daily_units", "promo_demand_uplift_multiplier", "discount_percent",
        "promo_demand_stock_availability_adjustment", "promo_demand_recent_momentum_adjustment",
        "model_expected_units_total_promo", "historical_proxy_expected_units_total_promo",
        "baseline_expected_units_total_promo", "selected_promo_period_demand",
        "promo_demand_source_quality", "promo_demand_release_ready_flag", "promo_demand_blocker_reason",
    ]
    if "promotion_name" not in merged.columns:
        merged["promotion_name"] = promotion_name
    if "promotion_period_days" in merged.columns:
        merged["promo_days"] = pd.to_numeric(merged["promotion_period_days"], errors="coerce")
    elif "promotion_period_days_feat" in merged.columns:
        merged["promo_days"] = pd.to_numeric(merged["promotion_period_days_feat"], errors="coerce")
    else:
        merged["promo_days"] = _promo_window_days(merged)
    sample_cols.insert(6, "promo_days")

    def _sample(mask: pd.Series, n: int = 20) -> pd.DataFrame:
        chunk = merged.loc[mask]
        if chunk.empty:
            return chunk
        return chunk.head(n)

    parts = [
        _sample(merged["model_expected_units_total_promo"].rank(ascending=False, method="first").le(20)),
        _sample((merged["model_expected_units_total_promo"] > 0) & (merged["model_expected_units_total_promo"].rank(method="first") <= 20)),
        _sample(merged["promo_demand_release_ready_flag"].eq("YES"), 25),
        _sample(merged["promo_demand_release_ready_flag"].eq("NO"), 25),
        _sample(merged["promo_demand_selection_method"].eq("historical_proxy_fallback"), 15),
        _sample(merged["promo_demand_selection_method"].eq("baseline_period_fallback"), 15),
        _sample(merged["promo_demand_selection_method"].eq("unsafe_missing_promo_demand"), 15),
    ]
    sample = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["sku_number"] if "sku_number" in merged.columns else None)
    hist_daily = merged["historical_proxy_expected_units_total_promo"] / merged["promo_days"].where(merged["promo_days"].gt(0), 1)
    sample_out = sample.copy()
    sample_out["historical_promo_units_per_day"] = hist_daily.reindex(sample.index).round(4)
    if "discount_percent" not in sample_out.columns:
        sample_out["discount_percent"] = _first_numeric(merged, ("discount_percent",))
    available = [c for c in sample_cols if c in sample_out.columns or c == "promo_days"]
    extra = [c for c in sample_out.columns if c not in available and c in {"historical_promo_units_per_day", "promo_days"}]
    sample_out[available + extra].head(120).to_csv(diagnostics_dir / "phase5c01_forecast_sample_review.csv", index=False)

    total = len(merged)
    release_ready = int(forecast["promo_demand_release_ready_flag"].eq("YES").sum())
    unsafe = int(forecast["promo_demand_selection_method"].eq("unsafe_missing_promo_demand").sum())
    model_median = float(forecast["model_expected_units_total_promo"].median())
    model_p95 = float(forecast["model_expected_units_total_promo"].quantile(0.95))
    flat_model = detect_flat_placeholder_forecast(forecast, "model_expected_units_total_promo")["is_flat_placeholder"]
    summary = pd.DataFrame([{
        "total_skus": total,
        "release_ready_count": release_ready,
        "release_ready_percentage": round(release_ready / max(total, 1) * 100, 2),
        "unsafe_count": unsafe,
        "unsafe_percentage": round(unsafe / max(total, 1) * 100, 2),
        "model_forecast_median": model_median,
        "model_forecast_p95": model_p95,
        "historical_proxy_count": int(forecast["promo_demand_selection_method"].eq("historical_proxy_fallback").sum()),
        "baseline_fallback_count": int(forecast["promo_demand_selection_method"].eq("baseline_period_fallback").sum()),
        "missing_demand_count": unsafe,
        "flat_placeholder_detected": "YES" if flat_model else "NO",
        "commercial_release_score_estimate": commercial_release_score if commercial_release_score is not None else "",
        "primary_blocker": primary_blocker,
    }])
    summary.to_csv(diagnostics_dir / "phase5c01_manager_summary.csv", index=False)
