from __future__ import annotations

"""Phase 5G — asymmetric underforecast bias repair on repaired evidence rows."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_demand_backtest import compute_wape
from models.promotions.promo_demand_calibration import (
    DEFAULT_BIAS_MAX_PCT,
    DEFAULT_BIAS_MIN_PCT,
    DEFAULT_MIN_SAMPLE,
    add_calibration_bands,
    apply_promo_demand_calibration,
    assign_observation_quality,
    fit_promo_demand_calibration_factors,
    load_calibration_artifacts,
)
from models.promotions.promo_evidence_coverage_repair import (
    DEFAULT_BACKTEST_FRAME as F5D_BACKTEST,
    load_repair_source,
    repair_evidence_coverage,
)

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5g01_underforecast_bias_repair")
DEFAULT_REPAIRED_SAMPLE = Path(
    "Diagnostics/phase5f01_historical_evidence_coverage_repair/phase5f01_repaired_evidence_frame_sample.csv"
)

FACTOR_MIN = 0.90
FACTOR_MAX = 1.60
OVERFORECAST_DAMPING = 0.35

SEGMENT_HIERARCHY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("department+discount", ("department", "_discount_band")),
    ("department", ("department",)),
    ("total", ()),
)


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _safe_div(num: float, den: float) -> float:
    if den == 0.0:
        return 0.0
    return float(num / den)


def _asymmetric_raw_factor(actual_total: float, forecast_total: float) -> float:
    if forecast_total <= 0.0 or actual_total <= 0.0:
        return 1.0
    raw = actual_total / forecast_total
    if raw >= 1.0:
        return raw
    return 1.0 + (raw - 1.0) * OVERFORECAST_DAMPING


def _shrink_factor(raw: float, global_factor: float, row_count: int, min_sample: int) -> float:
    weight = min(1.0, row_count / max(min_sample, 1))
    shrunk = weight * raw + (1.0 - weight) * global_factor
    return float(np.clip(shrunk, FACTOR_MIN, FACTOR_MAX))


def _eligible_for_fit(frame: pd.DataFrame) -> pd.Series:
    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"
    cal_col = "calibration_eligible_flag_repaired" if "calibration_eligible_flag_repaired" in frame.columns else "calibration_eligible_flag"
    obs = frame.get("demand_observation_quality", pd.Series("LOW", index=frame.index)).astype(str)
    return (
        frame.get(cal_col, pd.Series("NO", index=frame.index)).astype(str).eq("YES")
        & frame.get(quality_col, pd.Series("UNSAFE", index=frame.index)).astype(str).isin(["HIGH", "MEDIUM"])
        & obs.eq("HIGH")
        & _numeric(frame, "stockout_suspected_flag").astype(int).eq(0)
    )


def load_repaired_calibrated_frame(*, rebuild: bool = False) -> pd.DataFrame:
    """Load merged repaired + calibrated backtest frame."""
    if rebuild:
        frame = load_repair_source()
        repaired = repair_evidence_coverage(frame)
    else:
        backtest = pd.read_csv(F5D_BACKTEST, low_memory=False)
        sample_path = DEFAULT_REPAIRED_SAMPLE
        if sample_path.exists():
            repaired_cols = pd.read_csv(sample_path, low_memory=False)
            keys = ["store_number", "sku_number", "promotion_start_date"]
            repair_only = [
                c for c in repaired_cols.columns
                if c not in backtest.columns or c.endswith("_repaired") or c.startswith("evidence_")
            ]
            repair_subset = repaired_cols[[c for c in keys + repair_only if c in repaired_cols.columns]].copy()
            for df in (backtest, repair_subset):
                for key in keys:
                    if key in df.columns:
                        df[key] = df[key].astype(str)
            repaired = backtest.merge(repair_subset, on=keys, how="left")
        else:
            frame = load_repair_source()
            repaired = repair_evidence_coverage(frame)

    if "model_expected_units_total_promo_raw" not in repaired.columns:
        repaired["model_expected_units_total_promo_raw"] = _numeric(repaired, "model_expected_units_total_promo")

    factors, _, _ = load_calibration_artifacts()
    if factors.empty:
        factors = fit_promo_demand_calibration_factors(repaired)
    calibrated = apply_promo_demand_calibration(repaired, factors)
    if "demand_observation_quality" not in calibrated.columns:
        calibrated = assign_observation_quality(calibrated)
    return add_calibration_bands(calibrated)


def _segment_metrics(chunk: pd.DataFrame, label: str, forecast_col: str) -> dict[str, Any]:
    actual = _numeric(chunk, "actual_units_sold_promo")
    forecast = _numeric(chunk, forecast_col)
    baseline = _numeric(chunk, "baseline_expected_units_total_promo")
    abs_err = (forecast - actual).abs()
    bias_units = float((forecast - actual).sum())
    actual_total = float(actual.sum())
    leftover = float((_numeric(chunk, "leftover_units_estimate").sum()) if "leftover_units_estimate" in chunk.columns else float((forecast - actual).clip(lower=0).sum()))
    missed = float((_numeric(chunk, "under_order_risk_units").sum()) if "under_order_risk_units" in chunk.columns else float((actual - forecast).clip(lower=0).sum()))
    return {
        "segment": label,
        "row_count": int(len(chunk)),
        "actual_units_total": actual_total,
        "forecast_units_total": float(forecast.sum()),
        "bias_units": bias_units,
        "bias_pct": _safe_div(bias_units, actual_total) * 100.0 if actual_total > 0 else 0.0,
        "wape": compute_wape(actual, forecast),
        "mae": float(abs_err.mean()) if len(chunk) else 0.0,
        "rmse": float(np.sqrt(((forecast - actual) ** 2).mean())) if len(chunk) else 0.0,
        "p75_abs_error": float(abs_err.quantile(0.75)) if len(chunk) else 0.0,
        "p95_abs_error": float(abs_err.quantile(0.95)) if len(chunk) else 0.0,
        "model_beats_baseline_pct": float((abs_err.lt((baseline - actual).abs())).mean() * 100.0) if len(chunk) else 0.0,
        "estimated_missed_sales_units": missed,
        "estimated_leftover_units": leftover,
    }


def compute_residual_bias_breakdown(
    frame: pd.DataFrame,
    *,
    forecast_col: str = "model_expected_units_total_promo_calibrated",
) -> pd.DataFrame:
    """Diagnose residual underforecast bias on repaired calibrated rows."""
    rows = [_segment_metrics(frame, "total", forecast_col)]
    specs = [
        ("department", "department"),
        ("category", "category"),
        ("promo_type", "promo_type"),
        ("discount_depth_band", "_discount_band"),
        ("promo_duration_band", "_promo_duration_band"),
        ("baseline_demand_band", "_baseline_demand_band"),
        ("actual_demand_band", "_actual_demand_band"),
        ("evidence_coverage_label", "evidence_coverage_label"),
        ("repaired_source_quality", "promo_demand_source_quality_repaired"),
        ("release_ready", "promo_demand_release_ready_flag_repaired"),
        ("stockout_censored", "stockout_suspected_flag"),
    ]
    for prefix, col in specs:
        if col not in frame.columns:
            continue
        for value, chunk in frame.groupby(col, dropna=False):
            rows.append(_segment_metrics(chunk, f"{prefix}={value}", forecast_col))
    return pd.DataFrame(rows)


def fit_underforecast_bias_adjustments(
    backtest_df: pd.DataFrame,
    *,
    min_sample: int = DEFAULT_MIN_SAMPLE,
) -> pd.DataFrame:
    """Fit conservative asymmetric underforecast correction factors."""
    forecast_col = "model_expected_units_total_promo_calibrated"
    eligible_mask = _eligible_for_fit(backtest_df)
    eligible = backtest_df[eligible_mask]
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "segment_key", "segment_level", "row_count", "actual_units_total",
                "forecast_units_total", "raw_factor", "shrunk_factor", "factor_applied",
                "sample_size_ok_flag", "bias_before_pct", "estimated_bias_after_pct", "notes",
            ]
        )

    def _segment_row(chunk: pd.DataFrame, key: str, level: str, global_factor: float) -> dict[str, Any]:
        actual_total = float(_numeric(chunk, "actual_units_sold_promo").sum())
        forecast_total = float(_numeric(chunk, forecast_col).sum())
        raw = _asymmetric_raw_factor(actual_total, forecast_total)
        n = int(len(chunk))
        applied = _shrink_factor(raw, global_factor, n, min_sample)
        bias_before = _safe_div(forecast_total - actual_total, actual_total) * 100.0 if actual_total > 0 else 0.0
        bias_after = _safe_div(forecast_total * applied - actual_total, actual_total) * 100.0 if actual_total > 0 else 0.0
        return {
            "segment_key": key,
            "segment_level": level,
            "row_count": n,
            "actual_units_total": actual_total,
            "forecast_units_total": forecast_total,
            "raw_factor": round(raw, 6),
            "shrunk_factor": round(applied, 6),
            "factor_applied": applied,
            "sample_size_ok_flag": "YES" if n >= min_sample and forecast_total > 0 else "NO",
            "bias_before_pct": round(bias_before, 4),
            "estimated_bias_after_pct": round(bias_after, 4),
            "notes": "" if n >= min_sample else "insufficient_sample",
        }

    global_actual = float(_numeric(eligible, "actual_units_sold_promo").sum())
    global_forecast = float(_numeric(eligible, forecast_col).sum())
    global_raw = _asymmetric_raw_factor(global_actual, global_forecast)
    global_factor = float(np.clip(global_raw, FACTOR_MIN, FACTOR_MAX))

    rows = [_segment_row(eligible, "total", "total", global_factor)]
    seen = {"total"}
    for level_name, cols in SEGMENT_HIERARCHY:
        if level_name == "total":
            continue
        if any(c not in eligible.columns for c in cols):
            continue
        for key_vals, chunk in eligible.groupby(list(cols), dropna=False):
            if not isinstance(key_vals, tuple):
                key_vals = (key_vals,)
            key = "|".join(str(v) for v in key_vals)
            if key in seen:
                continue
            seen.add(key)
            rows.append(_segment_row(chunk, key, level_name, global_factor))
    return pd.DataFrame(rows)


def _lookup_bias_factor(row: pd.Series, factors: pd.DataFrame) -> tuple[float, str, str]:
    ok = factors[factors["sample_size_ok_flag"].eq("YES")].copy()
    if ok.empty:
        total = factors[factors["segment_level"].eq("total")]
        if not total.empty:
            return float(total.iloc[0]["factor_applied"]), "total", "LOW"
        return 1.0, "none", "LOW"
    for level_name, cols in SEGMENT_HIERARCHY:
        if not cols:
            total = ok[ok["segment_level"].eq("total")]
            if not total.empty:
                return float(total.iloc[0]["factor_applied"]), "total", "MEDIUM"
            continue
        if any(c not in row.index for c in cols):
            continue
        key = "|".join(str(row.get(c, "unknown")) for c in cols)
        match = ok[(ok["segment_key"] == key) & (ok["segment_level"] == level_name)]
        if not match.empty:
            quality = "HIGH" if level_name.startswith("department+") else "MEDIUM"
            return float(match.iloc[0]["factor_applied"]), key, quality
    total = ok[ok["segment_level"].eq("total")]
    if not total.empty:
        return float(total.iloc[0]["factor_applied"]), "total", "MEDIUM"
    return 1.0, "none", "LOW"


def apply_underforecast_bias_adjustments(
    scored_df: pd.DataFrame,
    adjustment_factors_df: pd.DataFrame,
    *,
    gate_recommendation: str = "NO_RELEASE",
) -> pd.DataFrame:
    """Apply bias adjustment while preserving raw and calibrated forecasts."""
    out = scored_df.copy()
    raw = _numeric(out, "model_expected_units_total_promo_raw")
    if raw.sum() == 0:
        raw = _numeric(out, "model_expected_units_total_promo")
    out["model_expected_units_total_promo_raw"] = raw.round(6)
    calibrated = _numeric(out, "model_expected_units_total_promo_calibrated")
    if calibrated.sum() == 0:
        cal_factor = _numeric(out, "promo_demand_calibration_factor", 1.0)
        calibrated = (raw * cal_factor).round(6)
        out["model_expected_units_total_promo_calibrated"] = calibrated

    factors: list[float] = []
    sources: list[str] = []
    qualities: list[str] = []
    banded = add_calibration_bands(out)
    for _, row in banded.iterrows():
        factor, key, quality = _lookup_bias_factor(row, adjustment_factors_df)
        factors.append(factor)
        sources.append(f"phase5g_underforecast:{key}")
        qualities.append(quality)

    out["underforecast_bias_factor"] = pd.Series(factors, index=out.index).round(6)
    out["underforecast_bias_factor_source"] = pd.Series(sources, index=out.index)
    out["underforecast_bias_quality"] = pd.Series(qualities, index=out.index)
    adjusted = (calibrated * out["underforecast_bias_factor"]).clip(lower=0.0).round(6)
    out["bias_adjusted_expected_units_total_promo"] = adjusted

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in out.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in out.columns else "promo_demand_release_ready_flag"
    allowed = (
        (gate_recommendation == "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        & out["underforecast_bias_quality"].isin(["HIGH", "MEDIUM"])
        & out.get(release_col, pd.Series("NO", index=out.index)).astype(str).eq("YES")
        & out.get(quality_col, pd.Series("UNSAFE", index=out.index)).astype(str).isin(["HIGH", "MEDIUM"])
        & out["underforecast_bias_factor"].between(FACTOR_MIN, FACTOR_MAX)
        & adjusted.gt(0)
    )
    out["bias_adjusted_forecast_allowed_flag"] = allowed.map({True: "YES", False: "NO"})
    return out.fillna(0.0)


def _summary_row(label: str, frame: pd.DataFrame, forecast_col: str) -> dict[str, Any]:
    actual = _numeric(frame, "actual_units_sold_promo")
    forecast = _numeric(frame, forecast_col)
    baseline = _numeric(frame, "baseline_expected_units_total_promo")
    hist = _numeric(frame, "historical_proxy_expected_units_total_promo")
    abs_err = (forecast - actual).abs()
    bias_units = float((forecast - actual).sum())
    actual_total = float(actual.sum())
    leftover = float((forecast - actual).clip(lower=0).sum())
    missed = float((actual - forecast).clip(lower=0).sum())
    gp_proxy = actual_total * 4.82
    net_proxy = gp_proxy - leftover * 2.0 - missed * 4.0
    return {
        "model_variant": label,
        "wape": compute_wape(actual, forecast),
        "mae": float(abs_err.mean()),
        "rmse": float(np.sqrt(((forecast - actual) ** 2).mean())),
        "bias_pct": _safe_div(bias_units, actual_total) * 100.0 if actual_total > 0 else 0.0,
        "model_beats_baseline_pct": float((abs_err.lt((baseline - actual).abs())).mean() * 100.0),
        "model_beats_historical_proxy_pct": float((abs_err.lt((hist - actual).abs())).mean() * 100.0),
        "estimated_missed_sales_units": missed,
        "estimated_leftover_units": leftover,
        "estimated_net_value_proxy": net_proxy,
        "baseline_wape": compute_wape(actual, baseline),
        "historical_proxy_wape": compute_wape(actual, hist),
    }


def build_bias_adjusted_backtest_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = [
        _summary_row("raw_model", frame, "model_expected_units_total_promo"),
        _summary_row("calibrated_model", frame, "model_expected_units_total_promo_calibrated"),
        _summary_row("bias_adjusted_model", frame, "bias_adjusted_expected_units_total_promo"),
        _summary_row("baseline", frame, "baseline_expected_units_total_promo"),
        _summary_row("historical_proxy", frame, "historical_proxy_expected_units_total_promo"),
    ]
    return pd.DataFrame(rows)


def evaluate_bias_adjusted_release_gate(
    summary: pd.DataFrame,
    scored_df: pd.DataFrame,
    *,
    bias_min_pct: float = DEFAULT_BIAS_MIN_PCT,
    bias_max_pct: float = DEFAULT_BIAS_MAX_PCT,
) -> tuple[str, str, pd.DataFrame]:
    """Evidence-based release gate for bias-adjusted forecast."""
    cal = summary[summary["model_variant"].eq("calibrated_model")].iloc[0]
    adj = summary[summary["model_variant"].eq("bias_adjusted_model")].iloc[0]
    base = summary[summary["model_variant"].eq("baseline")].iloc[0]

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in scored_df.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in scored_df.columns else "promo_demand_release_ready_flag"

    release_ready_rows = int(scored_df.get(release_col, pd.Series("NO")).eq("YES").sum())
    limited_rows = int(
        (
            scored_df.get("bias_adjusted_forecast_allowed_flag", pd.Series("NO")).eq("YES")
            & scored_df.get(quality_col, pd.Series("UNSAFE")).isin(["HIGH", "MEDIUM"])
        ).sum()
    )
    unsafe_rows = int(scored_df.get(quality_col, pd.Series("UNSAFE")).eq("UNSAFE").sum())

    adj_wape = float(adj["wape"])
    base_wape = float(base["wape"])
    cal_bias = float(cal["bias_pct"])
    adj_bias = float(adj["bias_pct"])
    economic_proxy = float(adj["estimated_net_value_proxy"])

    recommendation = "NO_RELEASE"
    blocker = "pending_evaluation"
    notes: list[str] = []

    if adj_wape >= base_wape:
        blocker = "bias_adjusted_wape_not_better_than_baseline"
    elif adj_bias < bias_min_pct or adj_bias > bias_max_pct:
        blocker = "bias_adjusted_bias_outside_allowed_range"
    elif limited_rows <= 0:
        blocker = "no_bias_adjusted_release_ready_rows"
    elif economic_proxy <= 0:
        blocker = "negative_economic_proxy"
    elif int(_numeric(scored_df, "bias_adjusted_expected_units_total_promo").nunique(dropna=True)) <= 3:
        blocker = "bias_adjusted_forecast_flat_placeholder"
    elif adj_wape < base_wape and bias_min_pct <= adj_bias <= bias_max_pct and limited_rows > 0:
        recommendation = "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"
        blocker = "none_limited_release_earned"
        notes.append("phase5g_blocks_full_customer_release_by_default")
    elif adj_wape < base_wape and adj_bias > cal_bias:
        recommendation = "INTERNAL_SHADOW_ONLY"
        blocker = "bias_improves_but_limited_release_threshold_not_met"
    else:
        blocker = "overall_gate_not_met"

    gate = pd.DataFrame([{
        "calibrated_model_wape": float(cal["wape"]),
        "bias_adjusted_model_wape": adj_wape,
        "baseline_wape": base_wape,
        "calibrated_bias_pct": cal_bias,
        "bias_adjusted_bias_pct": adj_bias,
        "release_ready_rows": release_ready_rows,
        "limited_release_rows": limited_rows,
        "unsafe_rows": unsafe_rows,
        "economic_value_proxy": economic_proxy,
        "recommendation": recommendation,
        "primary_blocker": blocker,
        "notes": "; ".join(notes),
    }])
    return recommendation, blocker, gate


def write_phase5g01_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Run Phase 5G pipeline and write diagnostics."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    working = frame if frame is not None else load_repaired_calibrated_frame(rebuild=rebuild)

    residual = compute_residual_bias_breakdown(working)
    factors = fit_underforecast_bias_adjustments(working, min_sample=min_sample)
    adjusted = apply_underforecast_bias_adjustments(working, factors, gate_recommendation="NO_RELEASE")
    summary = build_bias_adjusted_backtest_summary(adjusted)
    recommendation, blocker, gate = evaluate_bias_adjusted_release_gate(summary, adjusted)
    adjusted = apply_underforecast_bias_adjustments(working, factors, gate_recommendation=recommendation)
    summary = build_bias_adjusted_backtest_summary(adjusted)
    recommendation, blocker, gate = evaluate_bias_adjusted_release_gate(summary, adjusted)

    cal_row = summary[summary["model_variant"].eq("calibrated_model")].iloc[0]
    adj_row = summary[summary["model_variant"].eq("bias_adjusted_model")].iloc[0]

    residual.to_csv(diagnostics_dir / "phase5g01_residual_bias_breakdown.csv", index=False)
    factors.to_csv(diagnostics_dir / "phase5g01_underforecast_bias_factors.csv", index=False)
    summary.to_csv(diagnostics_dir / "phase5g01_bias_adjusted_backtest_summary.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase5g01_limited_release_gate.csv", index=False)

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in adjusted.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in adjusted.columns else "promo_demand_release_ready_flag"

    return {
        "calibrated_wape": float(cal_row["wape"]),
        "bias_adjusted_wape": float(adj_row["wape"]),
        "baseline_wape": float(summary[summary["model_variant"].eq("baseline")]["wape"].iloc[0]),
        "calibrated_bias_pct": float(cal_row["bias_pct"]),
        "bias_adjusted_bias_pct": float(adj_row["bias_pct"]),
        "model_beats_baseline_pct": float(adj_row["model_beats_baseline_pct"]),
        "release_ready_rows": int(adjusted.get(release_col, pd.Series("NO")).eq("YES").sum()),
        "limited_release_rows": int(gate["limited_release_rows"].iloc[0]),
        "unsafe_rows": int(adjusted.get(quality_col, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "missed_sales_before": float(cal_row["estimated_missed_sales_units"]),
        "missed_sales_after": float(adj_row["estimated_missed_sales_units"]),
        "leftover_before": float(cal_row["estimated_leftover_units"]),
        "leftover_after": float(adj_row["estimated_leftover_units"]),
        "economic_value_proxy": float(adj_row["estimated_net_value_proxy"]),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
    }


def run_phase5g01_bias_repair(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
) -> dict[str, Any]:
    return write_phase5g01_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)


def load_bias_repair_artifacts(
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    factors_path = diagnostics_dir / "phase5g01_underforecast_bias_factors.csv"
    gate_path = diagnostics_dir / "phase5g01_limited_release_gate.csv"
    if not factors_path.exists() or not gate_path.exists():
        return pd.DataFrame(), pd.DataFrame(), "NO_RELEASE"
    factors = pd.read_csv(factors_path)
    gate = pd.read_csv(gate_path)
    recommendation = str(gate["recommendation"].iloc[0]) if not gate.empty else "NO_RELEASE"
    return factors, gate, recommendation
