from __future__ import annotations

"""Phase 5D — promo-period demand forecast backtest and economic validation."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_period_demand_forecast import attach_promo_period_demand_forecast

BACKTEST_OUTPUT_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_id",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "sku_number",
    "sku_description",
    "promo_days",
    "actual_units_sold_promo",
    "model_expected_units_total_promo",
    "historical_proxy_expected_units_total_promo",
    "baseline_expected_units_total_promo",
    "selected_promo_period_demand",
    "promo_demand_source_quality",
    "promo_demand_release_ready_flag",
    "forecast_error_units",
    "forecast_abs_error_units",
    "forecast_pct_error",
    "forecast_abs_pct_error",
    "model_bias_units",
    "baseline_abs_error_units",
    "historical_proxy_abs_error_units",
    "model_beats_baseline_flag",
    "model_beats_historical_proxy_flag",
    "stockout_suspected_flag",
    "leftover_units_estimate",
    "under_order_risk_units",
    "over_order_risk_units",
)

ACTUALS_COLUMN_CANDIDATES: tuple[str, ...] = (
    "actual_units_sold_promo",
    "actual_units_sold",
    "target_actual_units_sold",
)

GP_COLUMN_CANDIDATES: tuple[str, ...] = (
    "actual_sales_ex_gst_promo",
    "actual_sales_ex_gst",
    "gross_profit_promo_dollars",
    "estimated_actual_gross_profit",
)

ORDER_COLUMN_CANDIDATES: tuple[str, ...] = (
    "store_adjusted_qty",
    "pl_allocation_qty",
    "recommended_order_units",
    "promo_allocated_units",
    "predicted_units_total_promo",
)

UNIT_COST_CANDIDATES: tuple[str, ...] = (
    "promo_effective_cost",
    "last_received_cost",
    "promo_cost_price",
    "effective_cost_per_unit",
    "unit_cost",
)

DEFAULT_HISTORICAL_SOURCE = Path(
    "/Users/paulmorison/promotions_runtime_governed/training/models/"
    "e2e-live-20260619T123109/test_set_predictions.parquet"
)


def _first_numeric(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=frame.index)


def _first_text(frame: pd.DataFrame, names: tuple[str, ...], default: str = "") -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name].fillna(default).astype(str)
    return pd.Series(default, index=frame.index, dtype=object)


def _safe_div(num: pd.Series | float, den: pd.Series | float) -> pd.Series | float:
    if isinstance(den, (int, float, np.floating)):
        if float(den) == 0.0:
            return 0.0
        return float(num) / float(den)
    if isinstance(num, (int, float, np.floating)):
        num = pd.Series([num], index=den.index[:1])
    with np.errstate(divide="ignore", invalid="ignore"):
        out = num / den.replace(0.0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _promo_days(frame: pd.DataFrame) -> pd.Series:
    days = _first_numeric(frame, ("promo_days", "live_promo_window_days", "promotion_period_days"))
    days = days.where(days.gt(0), 0.0)
    if days.eq(0).any() and {"promotion_start_date", "promotional_end_date"}.issubset(frame.columns):
        derived = (
            pd.to_datetime(frame["promotional_end_date"], errors="coerce")
            - pd.to_datetime(frame["promotion_start_date"], errors="coerce")
        ).dt.days.add(1).astype(float)
        days = days.where(days.gt(0), derived)
    return days.fillna(0.0).clip(lower=0.0)


def resolve_actuals_column(frame: pd.DataFrame) -> str:
    for column in ACTUALS_COLUMN_CANDIDATES:
        if column in frame.columns:
            return column
    raise ValueError(f"No realised promo units column found; expected one of {ACTUALS_COLUMN_CANDIDATES}")


def dedupe_promo_sku_events(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per store + promo window + SKU event."""
    keys = [
        c
        for c in (
            "store_number",
            "promotion_id",
            "promotion_name",
            "promotion_start_date",
            "promotion_end_date",
            "promotional_end_date",
            "sku_number",
        )
        if c in frame.columns
    ]
    if not keys:
        keys = ["sku_number"]
    end_col = "promotion_end_date" if "promotion_end_date" in frame.columns else "promotional_end_date"
    if end_col not in keys and end_col in frame.columns:
        keys.append(end_col)
    return frame.sort_values(keys).drop_duplicates(subset=keys, keep="first").reset_index(drop=True)


def load_historical_promo_backtest_source(path: Path | None = None) -> pd.DataFrame:
    """Load completed-promotion rows with realised outcomes (honest test split preferred)."""
    source_path = path or DEFAULT_HISTORICAL_SOURCE
    if not source_path.exists():
        raise FileNotFoundError(f"Historical backtest source not found: {source_path}")
    if source_path.suffix.lower() == ".parquet":
        return pd.read_parquet(source_path)
    return pd.read_csv(source_path, low_memory=False)


def build_promo_demand_backtest_frame(
    frame: pd.DataFrame,
    *,
    actuals_column: str | None = None,
) -> pd.DataFrame:
    """Build one row per historical promo SKU event with forecast comparison metrics."""
    working = dedupe_promo_sku_events(frame.copy())
    actual_col = actuals_column or resolve_actuals_column(working)
    actual = pd.to_numeric(working[actual_col], errors="coerce").fillna(0.0).clip(lower=0.0)
    if actual_col != "actual_units_sold_promo":
        working["actual_units_sold_promo"] = actual
    else:
        working["actual_units_sold_promo"] = actual

    if "promotion_end_date" not in working.columns and "promotional_end_date" in working.columns:
        working["promotion_end_date"] = working["promotional_end_date"]
    if "promotion_name" not in working.columns:
        working["promotion_name"] = working.get("promotion_id", pd.Series("unknown", index=working.index)).astype(str)
    if "sku_description" not in working.columns:
        working["sku_description"] = working.get("product_description", pd.Series("", index=working.index)).astype(str)

    enriched = attach_promo_period_demand_forecast(working)
    promo_days = _promo_days(enriched)
    model = pd.to_numeric(enriched["model_expected_units_total_promo"], errors="coerce").fillna(0.0)
    baseline = pd.to_numeric(enriched["baseline_expected_units_total_promo"], errors="coerce").fillna(0.0)
    hist_proxy = pd.to_numeric(enriched["historical_proxy_expected_units_total_promo"], errors="coerce").fillna(0.0)
    selected = pd.to_numeric(enriched["selected_promo_period_demand"], errors="coerce").fillna(0.0)
    actual_s = enriched["actual_units_sold_promo"]

    error = model - actual_s
    abs_error = error.abs()
    pct_error = _safe_div(error, actual_s.where(actual_s.gt(0), np.nan)) * 100.0
    abs_pct = pct_error.abs()

    stock_basis = _first_numeric(
        enriched,
        ("total_stock_available", "store_adjusted_qty", "pl_allocation_qty", "stock_basis_units"),
    )
    sell_through = _safe_div(actual_s, stock_basis.where(stock_basis.gt(0), np.nan))
    stockout = (actual_s.gt(0)) & (sell_through.ge(0.98) | (stock_basis.gt(0) & actual_s.ge(stock_basis * 0.95)))
    recommended = _first_numeric(enriched, ORDER_COLUMN_CANDIDATES)
    leftover = (recommended - actual_s).clip(lower=0.0)
    under = (actual_s - recommended - stock_basis.clip(lower=0.0)).clip(lower=0.0)
    over = leftover

    out = pd.DataFrame(
        {
            "store_number": _first_text(enriched, ("store_number",)),
            "promotion_id": _first_text(enriched, ("promotion_id", "promotion_row_key", "promotional_sku_id"), ""),
            "promotion_name": _first_text(enriched, ("promotion_name",)),
            "promotion_start_date": _first_text(enriched, ("promotion_start_date",)),
            "promotion_end_date": _first_text(enriched, ("promotion_end_date", "promotional_end_date")),
            "sku_number": _first_text(enriched, ("sku_number", "sku_number_key")),
            "sku_description": enriched["sku_description"].astype(str),
            "promo_days": promo_days.round(0),
            "actual_units_sold_promo": actual_s.round(3),
            "model_expected_units_total_promo": model.round(3),
            "historical_proxy_expected_units_total_promo": hist_proxy.round(3),
            "baseline_expected_units_total_promo": baseline.round(3),
            "selected_promo_period_demand": selected.round(3),
            "promo_demand_source_quality": enriched["promo_demand_source_quality"].astype(str),
            "promo_demand_release_ready_flag": enriched["promo_demand_release_ready_flag"].astype(str),
            "forecast_error_units": error.round(3),
            "forecast_abs_error_units": abs_error.round(3),
            "forecast_pct_error": pct_error.round(3),
            "forecast_abs_pct_error": abs_pct.round(3),
            "model_bias_units": error.round(3),
            "baseline_abs_error_units": (baseline - actual_s).abs().round(3),
            "historical_proxy_abs_error_units": (hist_proxy - actual_s).abs().round(3),
            "model_beats_baseline_flag": (abs_error.lt((baseline - actual_s).abs())).astype(int),
            "model_beats_historical_proxy_flag": (abs_error.lt((hist_proxy - actual_s).abs())).astype(int),
            "stockout_suspected_flag": stockout.astype(int),
            "leftover_units_estimate": leftover.round(3),
            "under_order_risk_units": under.round(3),
            "over_order_risk_units": over.round(3),
        }
    )
    for dim in ("promo_type", "department", "category", "_discount_band", "discount_percent"):
        if dim in enriched.columns:
            out[dim] = enriched[dim]
    return out.fillna(0.0)


def compute_wape(actual: pd.Series, forecast: pd.Series) -> float:
    actual_sum = float(pd.to_numeric(actual, errors="coerce").fillna(0.0).sum())
    if actual_sum <= 0.0:
        return 0.0
    return float((forecast - actual).abs().sum() / actual_sum)


def compute_accuracy_summary(
    backtest: pd.DataFrame,
    *,
    group_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Summarise forecast accuracy; WAPE is primary metric."""
    groups: list[tuple[str, pd.DataFrame]] = [("total", backtest)]
    if group_columns:
        for col in group_columns:
            if col not in backtest.columns:
                continue
            for value, chunk in backtest.groupby(col, dropna=False):
                groups.append((f"{col}={value}", chunk))

    extra_groups = [
        ("release_ready=YES", backtest[backtest["promo_demand_release_ready_flag"].eq("YES")]),
        ("release_ready=NO", backtest[backtest["promo_demand_release_ready_flag"].eq("NO")]),
    ]
    for quality in ("HIGH", "MEDIUM", "LOW", "UNSAFE"):
        extra_groups.append(
            (f"source_quality={quality}", backtest[backtest["promo_demand_source_quality"].eq(quality)])
        )
    groups.extend(extra_groups)

    rows: list[dict[str, Any]] = []
    for label, chunk in groups:
        if chunk.empty:
            continue
        actual = chunk["actual_units_sold_promo"]
        model = chunk["model_expected_units_total_promo"]
        baseline = chunk["baseline_expected_units_total_promo"]
        hist = chunk["historical_proxy_expected_units_total_promo"]
        abs_err = chunk["forecast_abs_error_units"]
        pos_actual = actual.gt(0)
        rows.append(
            {
                "segment": label,
                "row_count": int(len(chunk)),
                "actual_units_total": float(actual.sum()),
                "forecast_units_total": float(model.sum()),
                "mean_actual_units": float(actual.mean()),
                "mean_forecast_units": float(model.mean()),
                "mae": float(abs_err.mean()),
                "rmse": float(np.sqrt((chunk["forecast_error_units"] ** 2).mean())),
                "wape": compute_wape(actual, model),
                "baseline_wape": compute_wape(actual, baseline),
                "historical_proxy_wape": compute_wape(actual, hist),
                "mape": float(chunk.loc[pos_actual, "forecast_abs_pct_error"].mean()) if pos_actual.any() else 0.0,
                "median_abs_error": float(abs_err.median()),
                "p75_abs_error": float(abs_err.quantile(0.75)),
                "p95_abs_error": float(abs_err.quantile(0.95)),
                "bias_units": float(chunk["model_bias_units"].sum()),
                "bias_pct": float(_safe_div(chunk["model_bias_units"].sum(), actual.sum()) * 100.0),
                "model_beats_baseline_pct": float(chunk["model_beats_baseline_flag"].mean() * 100.0),
                "model_beats_historical_proxy_pct": float(chunk["model_beats_historical_proxy_flag"].mean() * 100.0),
                "stockout_suspected_count": int(chunk["stockout_suspected_flag"].sum()),
                "leftover_suspected_count": int((chunk["leftover_units_estimate"] > 0).sum()),
            }
        )
    return pd.DataFrame(rows)


def _merge_source_for_economics(source: pd.DataFrame, backtest: pd.DataFrame) -> pd.DataFrame:
    source = source.copy()
    if "promotion_end_date" not in source.columns and "promotional_end_date" in source.columns:
        source["promotion_end_date"] = source["promotional_end_date"]
    keys = [c for c in ("store_number", "sku_number", "promotion_start_date", "promotion_end_date") if c in backtest.columns and c in source.columns]
    if not keys:
        return source.reindex(backtest.index)
    left = backtest[keys].copy()
    right = dedupe_promo_sku_events(source)
    for key in keys:
        left[key] = left[key].astype(str)
        right[key] = right[key].astype(str)
    return left.merge(right, on=keys, how="left", suffixes=("", "_src"))


def compute_economic_validation_summary(
    source: pd.DataFrame,
    backtest: pd.DataFrame,
) -> pd.DataFrame:
    """Proxy economic validation — clearly labelled, not exact P&L."""
    aligned = _merge_source_for_economics(source, backtest)
    recommended = _first_numeric(aligned, ORDER_COLUMN_CANDIDATES)
    if recommended.sum() == 0:
        recommended = backtest["selected_promo_period_demand"]
    actual = backtest["actual_units_sold_promo"]
    unit_cost = _first_numeric(aligned, UNIT_COST_CANDIDATES)
    unit_gp = _first_numeric(
        aligned,
        ("promo_gm_unit", "feature_expected_gp_on_trust_floor_units"),
    )
    if unit_gp.le(0).all():
        sales = _first_numeric(aligned, GP_COLUMN_CANDIDATES)
        unit_gp = _safe_div(sales, actual.where(actual.gt(0), np.nan))

    leftover = (recommended - actual).clip(lower=0.0)
    missed = (actual - recommended).clip(lower=0.0)
    sell_through = _safe_div(actual, recommended.where(recommended.gt(0), np.nan))

    gp_captured = (actual * unit_gp).sum()
    gp_missed = (missed * unit_gp).sum()
    capital_at_risk = (recommended * unit_cost).sum()
    over_cost = (leftover * unit_cost).sum()
    under_cost = (missed * unit_gp).sum()
    net_proxy = gp_captured - over_cost - under_cost

    baseline = backtest["baseline_expected_units_total_promo"]
    hist = backtest["historical_proxy_expected_units_total_promo"]
    model = backtest["model_expected_units_total_promo"]
    baseline_over = ((baseline - actual).clip(lower=0.0) * unit_cost).sum()
    hist_over = ((hist - actual).clip(lower=0.0) * unit_cost).sum()
    model_over = (leftover * unit_cost).sum()

    rows = [
        {"metric": "recommended_order_units_total", "value": float(recommended.sum()), "note": "proxy from allocation/adjusted qty"},
        {"metric": "actual_units_sold_total", "value": float(actual.sum()), "note": "realised promo-window units"},
        {"metric": "estimated_leftover_units", "value": float(leftover.sum()), "note": "proxy max(recommended-actual,0)"},
        {"metric": "estimated_missed_sales_units", "value": float(missed.sum()), "note": "proxy max(actual-recommended,0)"},
        {"metric": "estimated_capital_at_risk_proxy", "value": float(capital_at_risk), "note": "recommended * unit_cost"},
        {"metric": "estimated_gross_profit_captured_proxy", "value": float(gp_captured), "note": "actual * unit_gp"},
        {"metric": "estimated_gross_profit_missed_proxy", "value": float(gp_missed), "note": "missed * unit_gp"},
        {"metric": "over_order_cost_proxy", "value": float(over_cost), "note": "leftover * unit_cost"},
        {"metric": "under_order_cost_proxy", "value": float(under_cost), "note": "missed * unit_gp"},
        {"metric": "net_value_proxy", "value": float(net_proxy), "note": "gp_captured - over_cost - under_cost"},
        {"metric": "sell_through_pct_proxy", "value": float(sell_through.mean() * 100.0), "note": "mean(actual/recommended)"},
        {"metric": "capital_efficiency_proxy", "value": float(_safe_div(pd.Series([gp_captured]), pd.Series([capital_at_risk])).iloc[0]), "note": "gp/capital"},
        {"metric": "model_economic_value_vs_baseline_proxy", "value": float(baseline_over - model_over), "note": "baseline over-order cost minus model"},
        {"metric": "model_economic_value_vs_historical_proxy_proxy", "value": float(hist_over - model_over), "note": "historical proxy over-order cost minus model"},
    ]
    return pd.DataFrame(rows)


def assign_error_bucket(row: pd.Series) -> str:
    actual = float(row["actual_units_sold_promo"])
    model = float(row["model_expected_units_total_promo"])
    abs_pct = float(row["forecast_abs_pct_error"])
    if actual <= 0 and model > 0:
        return "actual_zero_forecast_positive"
    if actual > 0 and model <= 0:
        return "forecast_zero_actual_positive"
    if int(row.get("stockout_suspected_flag", 0)) == 1:
        return "stockout_suspected"
    if float(row.get("leftover_units_estimate", 0.0)) > 0 and actual > 0:
        if float(row["leftover_units_estimate"]) > actual:
            return "leftover_suspected"
    if abs_pct <= 15:
        return "excellent"
    if abs_pct <= 30:
        return "good"
    if abs_pct <= 50:
        return "acceptable"
    if abs_pct <= 100:
        return "poor"
    return "failed"


def _likely_cause(bucket: str, quality: str) -> str:
    mapping = {
        "actual_zero_forecast_positive": "no_realised_demand_but_model_positive",
        "forecast_zero_actual_positive": "model_underforecast_or_missing_evidence",
        "stockout_suspected": "stock_constrained_or_under_allocation",
        "leftover_suspected": "over_allocation_or_overforecast",
        "failed": "weak_evidence_or_promo_lift_miss",
        "poor": "uplift_or_baseline_mismatch",
        "acceptable": "moderate_promo_volatility",
        "good": "within_normal_error_band",
        "excellent": "strong_evidence_alignment",
    }
    base = mapping.get(bucket, "review_required")
    if quality in {"LOW", "UNSAFE"}:
        return f"{base};low_source_quality"
    return base


def build_error_bucket_review(backtest: pd.DataFrame) -> pd.DataFrame:
    out = backtest.copy()
    out["error_bucket"] = out.apply(assign_error_bucket, axis=1)
    out["likely_cause"] = [
        _likely_cause(b, q) for b, q in zip(out["error_bucket"], out["promo_demand_source_quality"], strict=True)
    ]
    out["recommended_model_improvement"] = np.where(
        out["error_bucket"].isin(["failed", "poor", "forecast_zero_actual_positive"]),
        "improve_uplift_evidence_or_baseline_independence",
        np.where(
            out["error_bucket"].eq("stockout_suspected"),
            "add_stock_constraint_and_allocation_layer",
            "monitor;acceptable_for_shadow",
        ),
    )
    cols = [
        "sku_number", "sku_description", "promotion_name", "actual_units_sold_promo",
        "model_expected_units_total_promo", "baseline_expected_units_total_promo",
        "historical_proxy_expected_units_total_promo", "selected_promo_period_demand",
        "promo_demand_source_quality", "promo_demand_release_ready_flag",
        "error_bucket", "likely_cause", "recommended_model_improvement",
    ]
    return out[cols]


def recommend_customer_release(
    backtest: pd.DataFrame,
    accuracy: pd.DataFrame,
    economic: pd.DataFrame,
) -> tuple[str, str]:
    """Evidence-based customer release recommendation."""
    total = accuracy[accuracy["segment"].eq("total")]
    ready = accuracy[accuracy["segment"].eq("release_ready=YES")]
    if total.empty:
        return "NO_RELEASE", "insufficient_backtest_rows"
    model_wape = float(total["wape"].iloc[0])
    baseline_wape = float(total["baseline_wape"].iloc[0])
    beats_base = float(total["model_beats_baseline_pct"].iloc[0])
    bias_pct = abs(float(total["bias_pct"].iloc[0]))
    net_proxy = float(economic.loc[economic["metric"].eq("net_value_proxy"), "value"].iloc[0]) if not economic.empty else 0.0
    unsafe_rows = int((backtest["promo_demand_source_quality"].eq("UNSAFE")).sum())
    unsafe_share = unsafe_rows / max(len(backtest), 1)

    if model_wape > 1.0 or model_wape >= baseline_wape:
        return "NO_RELEASE", "model_wape_not_better_than_baseline"
    if beats_base < 50.0:
        return "NO_RELEASE", "model_does_not_beat_baseline_often_enough"
    if bias_pct > 35.0:
        return "NO_RELEASE", "model_bias_too_extreme"
    if net_proxy < 0:
        return "NO_RELEASE", "negative_economic_proxy"
    if unsafe_share > 0.20:
        return "INTERNAL_SHADOW_ONLY", "unsafe_row_share_too_high"

    if not ready.empty:
        ready_wape = float(ready["wape"].iloc[0])
        ready_base = float(ready["baseline_wape"].iloc[0])
        if ready_wape < baseline_wape * 0.85 and ready_wape < 0.75 and beats_base >= 55.0:
            return "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY", "release_ready_subset_materially_better"
        if ready_wape < ready_base * 0.9 and model_wape < baseline_wape * 0.95:
            return "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY", "moderate_improvement_release_ready_only"

    if model_wape < baseline_wape * 0.9 and beats_base >= 52.0 and bias_pct <= 25.0:
        return "INTERNAL_SHADOW_ONLY", "model_improves_but_not_release_ready_threshold"

    return "NO_RELEASE", "overall_wape_or_economics_insufficient"


def write_phase5d01_diagnostics(
    *,
    source: pd.DataFrame,
    backtest: pd.DataFrame,
    diagnostics_dir: Path,
    commercial_release_score_before: int = 92,
    group_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Write Phase 5D diagnostics and return summary metrics."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    accuracy = compute_accuracy_summary(backtest, group_columns=group_columns or ["promo_demand_source_quality"])
    economic = compute_economic_validation_summary(source, backtest)
    buckets = build_error_bucket_review(backtest)

    total = accuracy[accuracy["segment"].eq("total")].iloc[0]
    release_ready_rows = int(backtest["promo_demand_release_ready_flag"].eq("YES").sum())
    unsafe_rows = int(backtest["promo_demand_source_quality"].eq("UNSAFE").sum())
    recommendation, blocker = recommend_customer_release(backtest, accuracy, economic)

    score_after = commercial_release_score_before
    if recommendation == "CUSTOMER_RELEASE_READY":
        score_after = min(98, commercial_release_score_before + 6)
    elif recommendation == "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY":
        score_after = min(96, commercial_release_score_before + 3)
    elif recommendation == "INTERNAL_SHADOW_ONLY":
        score_after = min(94, commercial_release_score_before + 1)
    else:
        score_after = min(commercial_release_score_before, 90)

    manager = pd.DataFrame([{
        "total_rows": int(len(backtest)),
        "release_ready_rows": release_ready_rows,
        "actual_units_total": float(backtest["actual_units_sold_promo"].sum()),
        "model_forecast_units_total": float(backtest["model_expected_units_total_promo"].sum()),
        "selected_demand_units_total": float(backtest["selected_promo_period_demand"].sum()),
        "model_wape": float(total["wape"]),
        "baseline_wape": float(total["baseline_wape"]),
        "historical_proxy_wape": float(total["historical_proxy_wape"]),
        "model_beats_baseline_pct": float(total["model_beats_baseline_pct"]),
        "model_beats_historical_proxy_pct": float(total["model_beats_historical_proxy_pct"]),
        "model_bias_pct": float(total["bias_pct"]),
        "estimated_leftover_units": float(economic.loc[economic["metric"].eq("estimated_leftover_units"), "value"].iloc[0]),
        "estimated_missed_sales_units": float(economic.loc[economic["metric"].eq("estimated_missed_sales_units"), "value"].iloc[0]),
        "estimated_net_value_proxy": float(economic.loc[economic["metric"].eq("net_value_proxy"), "value"].iloc[0]),
        "commercial_release_score_before": commercial_release_score_before,
        "commercial_release_score_after": score_after,
        "primary_remaining_blocker": blocker,
        "customer_release_recommendation": recommendation,
        "unsafe_rows": unsafe_rows,
    }])

    accuracy.to_csv(diagnostics_dir / "phase5d01_forecast_accuracy_summary.csv", index=False)
    economic.to_csv(diagnostics_dir / "phase5d01_economic_validation_summary.csv", index=False)
    buckets.to_csv(diagnostics_dir / "phase5d01_error_bucket_review.csv", index=False)
    manager.to_csv(diagnostics_dir / "phase5d01_manager_summary.csv", index=False)
    backtest.to_csv(diagnostics_dir / "phase5d01_backtest_frame.csv", index=False)

    return {
        "model_wape": float(total["wape"]),
        "baseline_wape": float(total["baseline_wape"]),
        "historical_proxy_wape": float(total["historical_proxy_wape"]),
        "model_beats_baseline_pct": float(total["model_beats_baseline_pct"]),
        "model_beats_historical_proxy_pct": float(total["model_beats_historical_proxy_pct"]),
        "release_ready_rows": release_ready_rows,
        "unsafe_rows": unsafe_rows,
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
        "commercial_release_score_after": score_after,
    }


def run_phase5d01_backtest(
    *,
    source_path: Path | None = None,
    diagnostics_dir: Path,
    commercial_release_score_before: int = 92,
) -> dict[str, Any]:
    """End-to-end Phase 5D backtest from historical source to diagnostics."""
    source = load_historical_promo_backtest_source(source_path)
    if "discount_percent" in source.columns:
        disc = pd.to_numeric(source["discount_percent"], errors="coerce").fillna(0.0)
        source = source.copy()
        source["_discount_band"] = pd.cut(
            disc,
            bins=[-0.1, 10, 20, 30, 100],
            labels=["0-10", "10-20", "20-30", "30+"],
        ).astype(str)
    backtest = build_promo_demand_backtest_frame(source)
    group_cols = [c for c in ("promo_type", "department", "category", "_discount_band") if c in backtest.columns]
    return write_phase5d01_diagnostics(
        source=source,
        backtest=backtest,
        diagnostics_dir=diagnostics_dir,
        commercial_release_score_before=commercial_release_score_before,
        group_columns=group_cols,
    )
