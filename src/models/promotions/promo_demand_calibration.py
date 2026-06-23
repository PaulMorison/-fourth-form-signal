from __future__ import annotations

"""Phase 5E — promo demand bias calibration and limited release gate."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_demand_backtest import compute_wape

DEFAULT_BACKTEST_FRAME = Path(
    "Diagnostics/phase5d01_forecast_backtest_validation/phase5d01_backtest_frame.csv"
)
DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5e01_bias_calibration_limited_release")

FACTOR_MIN = 0.75
FACTOR_MAX = 2.50
DEFAULT_MIN_SAMPLE = 30
DEFAULT_BIAS_MIN_PCT = -15.0
DEFAULT_BIAS_MAX_PCT = 20.0

SEGMENT_HIERARCHY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("department+discount+promo_duration", ("department", "_discount_band", "_promo_duration_band")),
    ("department+discount", ("department", "_discount_band")),
    ("department", ("department",)),
    ("total", ()),
)


def _safe_div(num: pd.Series | float, den: pd.Series | float) -> float | pd.Series:
    if isinstance(den, (int, float, np.floating)):
        if float(den) == 0.0:
            return 0.0
        return float(num) / float(den)
    if isinstance(num, (int, float, np.floating)):
        num = pd.Series([num], index=den.index[:1])
    with np.errstate(divide="ignore", invalid="ignore"):
        out = num / den.replace(0.0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _band_series(values: pd.Series, bins: list[float], labels: list[str]) -> pd.Series:
    return pd.cut(values, bins=bins, labels=labels, include_lowest=True).astype(str)


def add_calibration_bands(frame: pd.DataFrame) -> pd.DataFrame:
    """Add segmentation bands used for bias diagnostics and calibration."""
    out = frame.copy()
    actual = _numeric(out, "actual_units_sold_promo")
    baseline = _numeric(out, "baseline_expected_units_total_promo")
    promo_days = _numeric(out, "promo_days", 7.0)
    if "_discount_band" not in out.columns and "discount_percent" in out.columns:
        out["_discount_band"] = _band_series(
            _numeric(out, "discount_percent"),
            [-0.1, 10, 20, 30, 100],
            ["0-10", "10-20", "20-30", "30+"],
        )
    elif "_discount_band" not in out.columns:
        out["_discount_band"] = "unknown"
    out["_actual_demand_band"] = _band_series(
        actual,
        [-0.1, 0.5, 2, 5, 15, 1e9],
        ["zero", "micro", "low", "mid", "high"],
    )
    out["_baseline_demand_band"] = _band_series(
        baseline,
        [-0.1, 0.5, 2, 5, 15, 1e9],
        ["zero", "micro", "low", "mid", "high"],
    )
    out["_promo_duration_band"] = _band_series(
        promo_days,
        [-0.1, 3, 7, 14, 1e9],
        ["short", "week", "standard", "long"],
    )
    return out


def assign_observation_quality(frame: pd.DataFrame) -> pd.DataFrame:
    """Separate clean calibration rows from censored/low-quality observations."""
    out = add_calibration_bands(frame)
    actual = _numeric(out, "actual_units_sold_promo")
    baseline = _numeric(out, "baseline_expected_units_total_promo")
    stockout = _numeric(out, "stockout_suspected_flag").astype(int)
    leftover = _numeric(out, "leftover_units_estimate")
    promo_days = _numeric(out, "promo_days")
    start = pd.to_datetime(out.get("promotion_start_date"), errors="coerce")
    end = pd.to_datetime(out.get("promotion_end_date"), errors="coerce")
    invalid_window = start.isna() | end.isna() | (end < start) | promo_days.le(0)
    quality = pd.Series("HIGH", index=out.index, dtype=object)

    censored = stockout.eq(1)
    quality = quality.where(~censored, "CENSORED")

    low = (
        invalid_window
        | actual.isna()
        | ((actual <= 0) & (baseline > 0.5))
        | out.get("promo_demand_source_quality", pd.Series("", index=out.index)).astype(str).eq("UNSAFE")
    )
    quality = quality.where(~((quality == "HIGH") & low), "LOW")

    leftover_suspect = leftover.gt(actual) & actual.gt(0)
    quality = quality.where(~((quality == "HIGH") & leftover_suspect), "LOW")

    out["demand_observation_quality"] = quality
    out["stock_constraint_flag"] = censored.map({True: "YES", False: "NO"})
    out["actual_units_observed_is_censored_flag"] = censored.map({True: "YES", False: "NO"})
    out["calibration_eligible_flag"] = (
        quality.eq("HIGH")
        & out.get("promo_demand_source_quality", pd.Series("UNSAFE", index=out.index))
        .astype(str)
        .ne("UNSAFE")
    ).map({True: "YES", False: "NO"})
    return out


def _segment_metrics(chunk: pd.DataFrame, label: str) -> dict[str, Any]:
    actual = _numeric(chunk, "actual_units_sold_promo")
    forecast = _numeric(chunk, "model_expected_units_total_promo")
    baseline = _numeric(chunk, "baseline_expected_units_total_promo")
    hist = _numeric(chunk, "historical_proxy_expected_units_total_promo")
    abs_err = (forecast - actual).abs()
    bias_units = (forecast - actual).sum()
    actual_total = float(actual.sum())
    return {
        "segment": label,
        "row_count": int(len(chunk)),
        "actual_units_total": actual_total,
        "forecast_units_total": float(forecast.sum()),
        "forecast_bias_units": float(bias_units),
        "forecast_bias_pct": float(_safe_div(bias_units, actual_total) * 100.0) if actual_total > 0 else 0.0,
        "wape": compute_wape(actual, forecast),
        "mae": float(abs_err.mean()) if len(chunk) else 0.0,
        "rmse": float(np.sqrt(((forecast - actual) ** 2).mean())) if len(chunk) else 0.0,
        "model_beats_baseline_pct": float(
            _numeric(chunk, "model_beats_baseline_flag").mean() * 100.0
        ) if len(chunk) else 0.0,
        "model_beats_historical_proxy_pct": float(
            _numeric(chunk, "model_beats_historical_proxy_flag").mean() * 100.0
        ) if len(chunk) else 0.0,
        "median_actual_units": float(actual.median()) if len(chunk) else 0.0,
        "median_forecast_units": float(forecast.median()) if len(chunk) else 0.0,
        "p75_abs_error": float(abs_err.quantile(0.75)) if len(chunk) else 0.0,
        "p95_abs_error": float(abs_err.quantile(0.95)) if len(chunk) else 0.0,
        "baseline_wape": compute_wape(actual, baseline),
        "historical_proxy_wape": compute_wape(actual, hist),
    }


def compute_bias_diagnostics(frame: pd.DataFrame) -> pd.DataFrame:
    """Segment underforecast bias to locate systematic error sources."""
    enriched = assign_observation_quality(frame)
    if "leftover_suspected_flag" not in enriched.columns:
        enriched = enriched.copy()
        enriched["leftover_suspected_flag"] = (_numeric(enriched, "leftover_units_estimate") > 0).astype(int)
    rows: list[dict[str, Any]] = [_segment_metrics(enriched, "total")]

    segment_specs: list[tuple[str, str]] = [
        ("department", "department"),
        ("category", "category"),
        ("promo_type", "promo_type"),
        ("discount_depth_band", "_discount_band"),
        ("source_quality", "promo_demand_source_quality"),
        ("release_ready", "promo_demand_release_ready_flag"),
        ("actual_demand_band", "_actual_demand_band"),
        ("baseline_demand_band", "_baseline_demand_band"),
        ("promo_duration_band", "_promo_duration_band"),
        ("stockout_suspected", "stockout_suspected_flag"),
        ("leftover_suspected", "leftover_suspected_flag"),
    ]
    for prefix, col in segment_specs:
        if col not in enriched.columns:
            continue
        if col == "leftover_suspected_flag":
            col = "leftover_suspected_flag"
        for value, chunk in enriched.groupby(col, dropna=False):
            rows.append(_segment_metrics(chunk, f"{prefix}={value}"))

    out = pd.DataFrame(rows)
    total_rows = int(enriched.shape[0])
    out["segment_row_share_pct"] = out["row_count"] / max(total_rows, 1) * 100.0
    return out


def _segment_key(row: pd.Series, cols: tuple[str, ...]) -> str:
    if not cols:
        return "total"
    parts = [str(row.get(c, "unknown")) for c in cols]
    return "|".join(parts)


def _fit_segment_factor(
    chunk: pd.DataFrame,
    *,
    segment_key: str,
    segment_level: str,
    total_factor: float,
    min_sample: int,
) -> dict[str, Any]:
    actual = _numeric(chunk, "actual_units_sold_promo")
    forecast = _numeric(chunk, "model_expected_units_total_promo")
    actual_total = float(actual.sum())
    forecast_total = float(forecast.sum())
    row_count = int(len(chunk))
    if forecast_total <= 0 or actual_total <= 0:
        raw = 1.0
    else:
        raw = actual_total / forecast_total
    weight = min(1.0, row_count / max(min_sample, 1))
    shrunk = weight * raw + (1.0 - weight) * total_factor
    applied = float(np.clip(shrunk, FACTOR_MIN, FACTOR_MAX))
    bias_before = float(_safe_div(forecast.sum() - actual.sum(), actual.sum()) * 100.0) if actual_total > 0 else 0.0
    est_after = float(_safe_div(forecast.sum() * applied - actual.sum(), actual.sum()) * 100.0) if actual_total > 0 else 0.0
    sample_ok = row_count >= min_sample and forecast_total > 0 and actual_total > 0
    return {
        "segment_key": segment_key,
        "segment_level": segment_level,
        "row_count": row_count,
        "actual_units_total": actual_total,
        "forecast_units_total": forecast_total,
        "raw_factor": round(raw, 6),
        "shrunk_factor": round(shrunk, 6),
        "factor_applied": applied,
        "sample_size_ok_flag": "YES" if sample_ok else "NO",
        "bias_before_pct": round(bias_before, 4),
        "estimated_bias_after_pct": round(est_after, 4),
        "notes": "" if sample_ok else "insufficient_sample_or_zero_totals",
    }


def fit_promo_demand_calibration_factors(
    backtest_df: pd.DataFrame,
    *,
    segment_cols: list[str] | None = None,
    min_sample: int = DEFAULT_MIN_SAMPLE,
) -> pd.DataFrame:
    """Estimate multiplicative calibration factors from eligible historical rows."""
    enriched = assign_observation_quality(backtest_df)
    eligible = enriched[enriched["calibration_eligible_flag"].eq("YES")].copy()
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "segment_key", "segment_level", "row_count", "actual_units_total",
                "forecast_units_total", "raw_factor", "shrunk_factor", "factor_applied",
                "sample_size_ok_flag", "bias_before_pct", "estimated_bias_after_pct", "notes",
            ]
        )

    total_row = _fit_segment_factor(
        eligible,
        segment_key="total",
        segment_level="total",
        total_factor=1.0,
        min_sample=min_sample,
    )
    total_factor = total_row["factor_applied"]

    rows = [total_row]
    hierarchy = SEGMENT_HIERARCHY
    if segment_cols:
        hierarchy = tuple((name, tuple(cols)) for name, cols in [("custom", tuple(segment_cols))]) + hierarchy

    seen: set[str] = {"total"}
    for level_name, cols in hierarchy:
        if level_name == "total":
            continue
        missing = [c for c in cols if c not in eligible.columns]
        if missing:
            continue
        grouped = eligible.groupby(list(cols), dropna=False)
        for key_vals, chunk in grouped:
            if not isinstance(key_vals, tuple):
                key_vals = (key_vals,)
            key = "|".join(str(v) for v in key_vals)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                _fit_segment_factor(
                    chunk,
                    segment_key=key,
                    segment_level=level_name,
                    total_factor=total_factor,
                    min_sample=min_sample,
                )
            )
    return pd.DataFrame(rows)


def _lookup_factor(row: pd.Series, factors: pd.DataFrame) -> tuple[float, str, str, str]:
    """Return factor, segment key, segment level, quality for one row."""
    ok = factors[factors["sample_size_ok_flag"].eq("YES")].copy()
    if ok.empty:
        return 1.0, "none", "none", "LOW"

    for level_name, cols in SEGMENT_HIERARCHY:
        if not cols:
            total = ok[ok["segment_level"].eq("total")]
            if not total.empty:
                r = total.iloc[0]
                return float(r["factor_applied"]), "total", "total", "MEDIUM"
            continue
        if any(c not in row.index for c in cols):
            continue
        key = "|".join(str(row.get(c, "unknown")) for c in cols)
        match = ok[(ok["segment_key"] == key) & (ok["segment_level"] == level_name)]
        if not match.empty:
            r = match.iloc[0]
            quality = "HIGH" if level_name.startswith("department+") else "MEDIUM"
            return float(r["factor_applied"]), key, level_name, quality
    total = ok[ok["segment_level"].eq("total")]
    if not total.empty:
        r = total.iloc[0]
        return float(r["factor_applied"]), "total", "total", "MEDIUM"
    return 1.0, "none", "none", "LOW"


def apply_promo_demand_calibration(
    scored_df: pd.DataFrame,
    calibration_factors_df: pd.DataFrame,
) -> pd.DataFrame:
    """Apply segment calibration while preserving raw model forecast."""
    out = scored_df.copy()
    raw_col = "model_expected_units_total_promo"
    if raw_col not in out.columns:
        out[raw_col] = 0.0
    raw = _numeric(out, raw_col)
    out["model_expected_units_total_promo_raw"] = raw.round(6)

    factors: list[float] = []
    keys: list[str] = []
    levels: list[str] = []
    qualities: list[str] = []
    sources: list[str] = []

    banded = add_calibration_bands(out)
    for _, row in banded.iterrows():
        factor, key, level, quality = _lookup_factor(row, calibration_factors_df)
        factors.append(factor)
        keys.append(key)
        levels.append(level)
        qualities.append(quality)
        sources.append(f"phase5e_segment_calibration:{level}")

    out["promo_demand_calibration_factor"] = pd.Series(factors, index=out.index).round(6)
    calibrated = (raw * out["promo_demand_calibration_factor"]).clip(lower=0.0).round(6)
    out["model_expected_units_total_promo_calibrated"] = calibrated
    out["calibrated_forecast_source"] = pd.Series(sources, index=out.index)
    out["calibration_segment_key"] = pd.Series(keys, index=out.index)
    out["calibration_quality"] = pd.Series(qualities, index=out.index)

    no_factor = out["calibration_segment_key"].eq("none") | out["promo_demand_calibration_factor"].eq(1.0)
    out.loc[no_factor & out["calibration_quality"].ne("HIGH"), "calibration_quality"] = "LOW"
    out.loc[no_factor, "calibrated_forecast_source"] = "raw_model_no_calibration_factor"

    source_quality = out.get("promo_demand_source_quality", pd.Series("UNSAFE", index=out.index)).astype(str)
    release_ready = (
        out["calibration_quality"].isin(["HIGH", "MEDIUM"])
        & source_quality.isin(["HIGH", "MEDIUM"])
        & out["promo_demand_calibration_factor"].between(FACTOR_MIN, FACTOR_MAX)
        & calibrated.gt(0)
        & (calibrated - raw).abs().gt(1e-9)
    )
    out["calibration_release_ready_flag"] = release_ready.map({True: "YES", False: "NO"})
    return out.fillna(0.0)


def _summary_row(
    label: str,
    frame: pd.DataFrame,
    forecast_col: str,
) -> dict[str, Any]:
    actual = _numeric(frame, "actual_units_sold_promo")
    forecast = _numeric(frame, forecast_col)
    baseline = _numeric(frame, "baseline_expected_units_total_promo")
    hist = _numeric(frame, "historical_proxy_expected_units_total_promo")
    abs_err = (forecast - actual).abs()
    bias_units = float((forecast - actual).sum())
    actual_total = float(actual.sum())
    leftover = float(_numeric(frame, "leftover_units_estimate").sum()) if "leftover_units_estimate" in frame.columns else float((forecast - actual).clip(lower=0).sum())
    missed = float(_numeric(frame, "under_order_risk_units").sum()) if "under_order_risk_units" in frame.columns else float((actual - forecast).clip(lower=0).sum())
    gp_proxy = actual_total * 4.82
    net_proxy = gp_proxy - leftover * 2.0 - missed * 4.0
    return {
        "variant": label,
        "wape": compute_wape(actual, forecast),
        "mae": float(abs_err.mean()),
        "rmse": float(np.sqrt(((forecast - actual) ** 2).mean())),
        "bias_pct": float(_safe_div(bias_units, actual_total) * 100.0) if actual_total > 0 else 0.0,
        "model_beats_baseline_pct": float((abs_err.lt((baseline - actual).abs())).mean() * 100.0),
        "model_beats_historical_proxy_pct": float((abs_err.lt((hist - actual).abs())).mean() * 100.0),
        "p75_abs_error": float(abs_err.quantile(0.75)),
        "p95_abs_error": float(abs_err.quantile(0.95)),
        "estimated_missed_sales_units": missed,
        "estimated_leftover_units": leftover,
        "estimated_net_value_proxy": net_proxy,
        "baseline_wape": compute_wape(actual, baseline),
        "historical_proxy_wape": compute_wape(actual, hist),
    }


def build_calibrated_backtest_summary(
    backtest_df: pd.DataFrame,
    calibrated_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compare raw, calibrated, baseline, and historical proxy backtests."""
    merged = backtest_df.copy()
    merged["model_expected_units_total_promo_calibrated"] = _numeric(
        calibrated_df, "model_expected_units_total_promo_calibrated"
    )
    rows = [
        _summary_row("raw_model", merged, "model_expected_units_total_promo"),
        _summary_row("calibrated_model", merged, "model_expected_units_total_promo_calibrated"),
        _summary_row("baseline", merged, "baseline_expected_units_total_promo"),
        _summary_row("historical_proxy", merged, "historical_proxy_expected_units_total_promo"),
    ]
    return pd.DataFrame(rows)


def evaluate_limited_release_gate(
    calibrated_backtest_summary: pd.DataFrame,
    scored_df: pd.DataFrame,
    *,
    bias_min_pct: float = DEFAULT_BIAS_MIN_PCT,
    bias_max_pct: float = DEFAULT_BIAS_MAX_PCT,
) -> tuple[str, str, pd.DataFrame]:
    """Evidence-based limited release gate; CUSTOMER_RELEASE_READY blocked in Phase 5E."""
    raw = calibrated_backtest_summary[calibrated_backtest_summary["variant"].eq("raw_model")].iloc[0]
    cal = calibrated_backtest_summary[calibrated_backtest_summary["variant"].eq("calibrated_model")].iloc[0]
    base = calibrated_backtest_summary[calibrated_backtest_summary["variant"].eq("baseline")].iloc[0]

    release_ready_rows = int(scored_df.get("calibration_release_ready_flag", pd.Series("NO")).eq("YES").sum())
    limited_release_rows = int(
        (
            scored_df.get("calibration_release_ready_flag", pd.Series("NO")).eq("YES")
            & scored_df.get("calibration_quality", pd.Series("LOW")).isin(["HIGH", "MEDIUM"])
            & scored_df.get("promo_demand_source_quality", pd.Series("UNSAFE")).isin(["HIGH", "MEDIUM"])
        ).sum()
    )
    unsafe_rows = int(scored_df.get("promo_demand_source_quality", pd.Series("UNSAFE")).eq("UNSAFE").sum())
    economic_proxy = float(cal["estimated_net_value_proxy"])

    raw_wape = float(raw["wape"])
    cal_wape = float(cal["wape"])
    base_wape = float(base["wape"])
    raw_bias = float(raw["bias_pct"])
    cal_bias = float(cal["bias_pct"])

    recommendation = "NO_RELEASE"
    blocker = "pending_evaluation"
    notes: list[str] = []

    if cal_wape >= base_wape:
        blocker = "calibrated_wape_not_better_than_baseline"
    elif cal_bias < bias_min_pct or cal_bias > bias_max_pct:
        blocker = "calibrated_bias_outside_allowed_range"
    elif limited_release_rows <= 0:
        blocker = "no_high_medium_calibration_release_ready_rows"
    elif economic_proxy <= 0:
        blocker = "negative_economic_proxy"
    elif _is_flat_placeholder(_numeric(scored_df, "model_expected_units_total_promo_calibrated")):
        blocker = "calibrated_forecast_flat_placeholder"
    elif cal_wape < base_wape and bias_min_pct <= cal_bias <= bias_max_pct and limited_release_rows > 0:
        recommendation = "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"
        blocker = "none_limited_release_earned"
        notes.append("phase5e_blocks_full_customer_release_by_default")
    elif cal_wape < base_wape and cal_bias > bias_min_pct:
        recommendation = "INTERNAL_SHADOW_ONLY"
        blocker = "calibration_improves_but_limited_release_threshold_not_met"
    else:
        blocker = "overall_gate_not_met"

    gate = pd.DataFrame([{
        "raw_model_wape": raw_wape,
        "calibrated_model_wape": cal_wape,
        "baseline_wape": base_wape,
        "raw_bias_pct": raw_bias,
        "calibrated_bias_pct": cal_bias,
        "release_ready_rows": release_ready_rows,
        "limited_release_rows": limited_release_rows,
        "unsafe_rows": unsafe_rows,
        "economic_value_proxy": economic_proxy,
        "recommendation": recommendation,
        "primary_blocker": blocker,
        "notes": "; ".join(notes) if notes else "",
    }])
    return recommendation, blocker, gate


def _is_flat_placeholder(series: pd.Series) -> bool:
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() == 0:
        return True
    return int(s.nunique(dropna=True)) <= 3 and float(s.quantile(0.9)) <= 1.01


def write_phase5e01_diagnostics(
    *,
    backtest_df: pd.DataFrame,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    min_sample: int = DEFAULT_MIN_SAMPLE,
) -> dict[str, Any]:
    """Run full Phase 5E pipeline and write diagnostics."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    bias = compute_bias_diagnostics(backtest_df)
    factors = fit_promo_demand_calibration_factors(backtest_df, min_sample=min_sample)
    calibrated = apply_promo_demand_calibration(backtest_df, factors)
    summary = build_calibrated_backtest_summary(backtest_df, calibrated)
    recommendation, blocker, gate = evaluate_limited_release_gate(summary, calibrated)

    bias.to_csv(diagnostics_dir / "phase5e01_bias_diagnostics.csv", index=False)
    factors.to_csv(diagnostics_dir / "phase5e01_calibration_factors.csv", index=False)
    summary.to_csv(diagnostics_dir / "phase5e01_calibrated_backtest_summary.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase5e01_limited_release_gate.csv", index=False)
    calibrated.to_csv(diagnostics_dir / "phase5e01_calibrated_backtest_frame.csv", index=False)

    raw = summary[summary["variant"].eq("raw_model")].iloc[0]
    cal = summary[summary["variant"].eq("calibrated_model")].iloc[0]
    return {
        "raw_model_wape": float(raw["wape"]),
        "calibrated_model_wape": float(cal["wape"]),
        "baseline_wape": float(summary[summary["variant"].eq("baseline")]["wape"].iloc[0]),
        "raw_bias_pct": float(raw["bias_pct"]),
        "calibrated_bias_pct": float(cal["bias_pct"]),
        "model_beats_baseline_pct": float(cal["model_beats_baseline_pct"]),
        "limited_release_rows": int(gate["limited_release_rows"].iloc[0]),
        "unsafe_rows": int(gate["unsafe_rows"].iloc[0]),
        "economic_value_proxy": float(gate["economic_value_proxy"].iloc[0]),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
    }


def run_phase5e01_calibration(
    *,
    backtest_path: Path | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    min_sample: int = DEFAULT_MIN_SAMPLE,
) -> dict[str, Any]:
    """Load Phase 5D backtest frame and run Phase 5E calibration."""
    path = backtest_path or DEFAULT_BACKTEST_FRAME
    backtest = pd.read_csv(path, low_memory=False)
    return write_phase5e01_diagnostics(
        backtest_df=backtest,
        diagnostics_dir=diagnostics_dir,
        min_sample=min_sample,
    )


def load_calibration_artifacts(
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Load fitted factors, gate, and recommendation for commercial reporting."""
    factors_path = diagnostics_dir / "phase5e01_calibration_factors.csv"
    gate_path = diagnostics_dir / "phase5e01_limited_release_gate.csv"
    if not factors_path.exists() or not gate_path.exists():
        empty = pd.DataFrame()
        return empty, empty, "NO_RELEASE"
    factors = pd.read_csv(factors_path)
    gate = pd.read_csv(gate_path)
    recommendation = str(gate["recommendation"].iloc[0]) if not gate.empty else "NO_RELEASE"
    return factors, gate, recommendation
