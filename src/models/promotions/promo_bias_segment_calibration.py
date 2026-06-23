from __future__ import annotations

"""Phase 6A — asymmetric segment bias calibration and repair evaluation."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_bias_root_cause_review import (
    ALLOWED_BIAS_MAX,
    ALLOWED_BIAS_MIN,
    PRIMARY_BLOCKER,
    RELEASE_RECOMMENDATION,
    build_bias_root_cause_frame,
)
from models.promotions.promo_demand_backtest import compute_wape
from models.promotions.promo_demand_calibration import (
    DEFAULT_MIN_SAMPLE,
    add_calibration_bands,
    apply_promo_demand_calibration,
    assign_observation_quality,
    fit_promo_demand_calibration_factors,
)

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6a01_segment_bias_calibration")
PHASE5D_BACKTEST = Path("Diagnostics/phase5d01_forecast_backtest_validation/phase5d01_backtest_frame.csv")
PHASE5U_SCORED = Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_shadow_scored_outcomes.csv")
PHASE5Z_REPAIR = Path("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_bias_repair_plan.csv")

FACTOR_MIN = 0.90
FACTOR_MAX = 1.65
OVERFORECAST_DAMPING = 0.35

SEGMENT_HIERARCHY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("department+long_tail", ("department", "long_tail_sku_flag")),
    ("department+mission", ("department", "mission_sku_flag")),
    ("department+discount", ("department", "_discount_band")),
    ("department", ("department",)),
    ("long_tail_sku_flag", ("long_tail_sku_flag",)),
    ("mission_sku_flag", ("mission_sku_flag",)),
    ("basket_attachment_source_quality", ("basket_attachment_source_quality",)),
    ("total", ()),
)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


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


def _eligible_for_segment_fit(frame: pd.DataFrame) -> pd.Series:
    quality = frame.get("promo_demand_source_quality", pd.Series("UNSAFE", index=frame.index)).astype(str)
    obs = frame.get("demand_observation_quality", pd.Series("LOW", index=frame.index)).astype(str)
    cal = frame.get("calibration_eligible_flag", pd.Series("NO", index=frame.index)).astype(str)
    return (
        quality.isin(["HIGH", "MEDIUM"])
        & obs.eq("HIGH")
        & cal.eq("YES")
        & _numeric(frame, "stockout_suspected_flag").astype(int).eq(0)
    )


def build_bias_calibration_frame(
    *,
    backtest_df: pd.DataFrame | None = None,
    scored_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build calibration-ready frame from backtest, shadow outcomes, and root-cause enrichments."""
    backtest = backtest_df if backtest_df is not None else _read_csv(PHASE5D_BACKTEST)
    scored = scored_df if scored_df is not None else _read_csv(PHASE5U_SCORED)
    frame = build_bias_root_cause_frame(backtest_df=backtest, scored_df=scored)

    if frame.empty:
        return frame

    if "model_expected_units_total_promo_raw" not in frame.columns:
        frame["model_expected_units_total_promo_raw"] = _numeric(frame, "model_expected_units_total_promo")

    frame = add_calibration_bands(frame)
    frame = assign_observation_quality(frame)

    factors = fit_promo_demand_calibration_factors(frame)
    frame = apply_promo_demand_calibration(frame, factors)

    if "mission_sku_flag" not in frame.columns:
        frame["mission_sku_flag"] = np.where(_numeric(frame.get("mission_sku_score", 0)).ge(45), "YES", "NO")
    if "long_tail_sku_flag" not in frame.columns:
        frame["long_tail_sku_flag"] = "NO"
    if "basket_attachment_source_quality" not in frame.columns:
        frame["basket_attachment_source_quality"] = "UNKNOWN"

    frame["segment_calibration_eligible_flag"] = _eligible_for_segment_fit(frame).map({True: "YES", False: "NO"})
    frame["requires_human_approval_flag"] = "YES"
    frame["segment_calibration_status"] = "PROPOSED_NOT_DEPLOYED"
    return frame


def estimate_segment_bias_factors(
    frame: pd.DataFrame,
    *,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    forecast_col: str = "model_expected_units_total_promo_calibrated",
) -> pd.DataFrame:
    """Estimate asymmetric segment bias correction factors with shrinkage to global."""
    eligible = frame.loc[_eligible_for_segment_fit(frame)].copy()
    if eligible.empty:
        eligible = frame.loc[_numeric(frame, "actual_units_sold_promo").gt(0)].copy()
    if eligible.empty:
        return pd.DataFrame(columns=[
            "segment_key", "segment_level", "row_count", "actual_units_total",
            "forecast_units_total", "raw_factor", "shrunk_factor", "factor_applied",
            "sample_size_ok_flag", "bias_before_pct", "estimated_bias_after_pct", "notes",
        ])

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
            "actual_units_total": round(actual_total, 4),
            "forecast_units_total": round(forecast_total, 4),
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
    banded = add_calibration_bands(eligible)
    for level_name, cols in SEGMENT_HIERARCHY:
        if level_name == "total":
            continue
        if any(c not in banded.columns for c in cols):
            continue
        for key_vals, chunk in banded.groupby(list(cols), dropna=False):
            if not isinstance(key_vals, tuple):
                key_vals = (key_vals,)
            key = "|".join(str(v) for v in key_vals)
            if key in seen:
                continue
            seen.add(key)
            rows.append(_segment_row(chunk, key, level_name, global_factor))
    return pd.DataFrame(rows)


def _lookup_segment_factor(row: pd.Series, factors: pd.DataFrame) -> tuple[float, str, str]:
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
            quality = "HIGH" if "+" in level_name else "MEDIUM"
            return float(match.iloc[0]["factor_applied"]), key, quality
    total = ok[ok["segment_level"].eq("total")]
    if not total.empty:
        return float(total.iloc[0]["factor_applied"]), "total", "MEDIUM"
    return 1.0, "none", "LOW"


def apply_asymmetric_segment_calibration(
    frame: pd.DataFrame,
    factors_df: pd.DataFrame,
) -> pd.DataFrame:
    """Apply proposed segment calibration — advisory only; preserves raw and governed fields."""
    out = frame.copy()
    raw = _numeric(out, "model_expected_units_total_promo_raw")
    if raw.sum() == 0:
        raw = _numeric(out, "model_expected_units_total_promo")
    out["model_expected_units_total_promo_raw"] = raw.round(6)

    calibrated = _numeric(out, "model_expected_units_total_promo_calibrated")
    if calibrated.sum() == 0:
        cal_factor = _numeric(out, "promo_demand_calibration_factor", 1.0)
        calibrated = (raw * cal_factor).round(6)
        out["model_expected_units_total_promo_calibrated"] = calibrated

    seg_factors: list[float] = []
    seg_sources: list[str] = []
    seg_qualities: list[str] = []
    banded = add_calibration_bands(out)
    for _, row in banded.iterrows():
        factor, key, quality = _lookup_segment_factor(row, factors_df)
        seg_factors.append(factor)
        seg_sources.append(f"phase6a_segment:{key}")
        seg_qualities.append(quality)

    out["segment_bias_factor"] = pd.Series(seg_factors, index=out.index).round(6)
    out["segment_bias_factor_source"] = pd.Series(seg_sources, index=out.index)
    out["segment_bias_factor_quality"] = pd.Series(seg_qualities, index=out.index)
    adjusted = (calibrated * out["segment_bias_factor"]).clip(lower=0.0).round(6)
    out["segment_calibrated_expected_units"] = adjusted

    eligible = (
        out["segment_calibration_eligible_flag"].astype(str).eq("YES")
        & out["segment_bias_factor_quality"].isin(["HIGH", "MEDIUM"])
        & out["segment_bias_factor"].between(FACTOR_MIN, FACTOR_MAX)
        & adjusted.gt(0)
    )
    out["segment_calibration_allowed_flag"] = eligible.map({True: "YES", False: "NO"})
    out["requires_human_approval_flag"] = "YES"
    out["segment_calibration_status"] = "PROPOSED_NOT_DEPLOYED"
    return out.fillna(0.0)


def _summary_row(label: str, frame: pd.DataFrame, forecast_col: str) -> dict[str, Any]:
    actual = _numeric(frame, "actual_units_sold_promo")
    forecast = _numeric(frame, forecast_col)
    baseline = _numeric(frame, "baseline_expected_units_total_promo")
    abs_err = (forecast - actual).abs()
    bias_units = float((forecast - actual).sum())
    actual_total = float(actual.sum())
    missed = float((actual - forecast).clip(lower=0).sum())
    leftover = float((forecast - actual).clip(lower=0).sum())
    return {
        "model_variant": label,
        "row_count": int(len(frame)),
        "wape": round(compute_wape(actual, forecast), 6),
        "mae": float(abs_err.mean()),
        "bias_pct": round(_safe_div(bias_units, actual_total) * 100.0, 4) if actual_total > 0 else 0.0,
        "underforecast_rate": round(float((forecast - actual).lt(-0.5).mean() * 100.0), 2),
        "overforecast_rate": round(float((forecast - actual).gt(0.5).mean() * 100.0), 2),
        "estimated_missed_units": round(missed, 2),
        "estimated_excess_units": round(leftover, 2),
        "model_beats_baseline_pct": round(float((abs_err.lt((baseline - actual).abs())).mean() * 100.0), 2),
        "segment_calibration_allowed_rows": int(
            frame.get("segment_calibration_allowed_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES").sum()
        ) if forecast_col == "segment_calibrated_expected_units" else 0,
    }


def evaluate_bias_repair(
    frame: pd.DataFrame,
    *,
    bias_min_pct: float = ALLOWED_BIAS_MIN,
    bias_max_pct: float = ALLOWED_BIAS_MAX,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate raw, calibrated, and segment-calibrated repair outcomes."""
    rows = [
        _summary_row("raw_model", frame, "model_expected_units_total_promo"),
        _summary_row("calibrated_model", frame, "model_expected_units_total_promo_calibrated"),
        _summary_row("segment_calibrated_model", frame, "segment_calibrated_expected_units"),
        _summary_row("baseline", frame, "baseline_expected_units_total_promo"),
    ]
    evaluation = pd.DataFrame(rows)

    raw = evaluation.loc[evaluation["model_variant"].eq("raw_model")].iloc[0]
    cal = evaluation.loc[evaluation["model_variant"].eq("calibrated_model")].iloc[0]
    seg = evaluation.loc[evaluation["model_variant"].eq("segment_calibrated_model")].iloc[0]
    base = evaluation.loc[evaluation["model_variant"].eq("baseline")].iloc[0]

    recommendation = RELEASE_RECOMMENDATION
    blocker = PRIMARY_BLOCKER
    notes: list[str] = ["segment_calibration_proposed_not_deployed", "requires_human_approval"]

    seg_bias = float(seg["bias_pct"])
    cal_bias = float(cal["bias_pct"])
    seg_wape = float(seg["wape"])
    base_wape = float(base["wape"])
    bias_improved = seg_bias > cal_bias
    wape_ok = seg_wape <= base_wape * 1.05

    if seg_bias < bias_min_pct:
        blocker = PRIMARY_BLOCKER
        notes.append("segment_calibrated_bias_still_dangerously_negative")
    elif seg_bias > bias_max_pct:
        blocker = "segment_calibrated_bias_too_positive"
    elif not bias_improved:
        blocker = "segment_calibration_did_not_improve_bias"
    elif not wape_ok:
        blocker = "segment_calibrated_wape_degraded"
    elif int(seg["segment_calibration_allowed_rows"]) <= 0:
        blocker = "no_segment_calibration_allowed_rows"
    else:
        blocker = "segment_repair_improves_metrics_but_not_release_ready"
        notes.append("human_approval_required_before_any_deployment")

    repair_plan = _read_csv(PHASE5Z_REPAIR)
    top_repair = str(repair_plan.iloc[0]["recommended_action"]) if not repair_plan.empty else ""

    gate = pd.DataFrame([{
        "customer_release_recommendation": recommendation,
        "primary_blocker": blocker,
        "raw_bias_pct": float(raw["bias_pct"]),
        "calibrated_bias_pct": cal_bias,
        "segment_calibrated_bias_pct": seg_bias,
        "allowed_bias_range": f"{bias_min_pct} to {bias_max_pct}",
        "raw_wape": float(raw["wape"]),
        "calibrated_wape": float(cal["wape"]),
        "segment_calibrated_wape": seg_wape,
        "baseline_wape": base_wape,
        "bias_improvement_vs_calibrated": round(seg_bias - cal_bias, 4),
        "missed_units_before": float(cal["estimated_missed_units"]),
        "missed_units_after": float(seg["estimated_missed_units"]),
        "excess_units_before": float(cal["estimated_excess_units"]),
        "excess_units_after": float(seg["estimated_excess_units"]),
        "segment_calibration_allowed_rows": int(seg["segment_calibration_allowed_rows"]),
        "requires_human_approval_flag": "YES",
        "deployment_status": "PROPOSED_NOT_DEPLOYED",
        "auto_orders_approved": "NO",
        "top_5z_repair_recommendation": top_repair,
        "notes": "; ".join(notes),
    }])
    return evaluation, gate


def write_phase6a_diagnostics(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    backtest_df: pd.DataFrame | None = None,
    scored_df: pd.DataFrame | None = None,
    min_sample: int = DEFAULT_MIN_SAMPLE,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    frame = build_bias_calibration_frame(backtest_df=backtest_df, scored_df=scored_df)
    factors = estimate_segment_bias_factors(frame, min_sample=min_sample)
    calibrated = apply_asymmetric_segment_calibration(frame, factors)
    evaluation, gate = evaluate_bias_repair(calibrated)

    factors.to_csv(diagnostics_dir / "phase6a01_segment_bias_factors.csv", index=False)
    evaluation.to_csv(diagnostics_dir / "phase6a01_bias_repair_evaluation.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase6a01_release_gate.csv", index=False)

    sample_cols = [
        c for c in [
            "store_number", "promotion_id", "sku_number", "department", "long_tail_sku_flag",
            "mission_sku_flag", "actual_units_sold_promo", "model_expected_units_total_promo_raw",
            "model_expected_units_total_promo_calibrated", "segment_calibrated_expected_units",
            "segment_bias_factor", "segment_bias_factor_source", "segment_calibration_eligible_flag",
            "segment_calibration_allowed_flag", "requires_human_approval_flag",
        ] if c in calibrated.columns
    ]
    calibrated[sample_cols].head(500).to_csv(diagnostics_dir / "phase6a01_bias_calibration_frame_sample.csv", index=False)

    seg = evaluation.loc[evaluation["model_variant"].eq("segment_calibrated_model")].iloc[0]
    cal = evaluation.loc[evaluation["model_variant"].eq("calibrated_model")].iloc[0]

    return {
        "segment_factor_count": int(len(factors)),
        "segment_calibration_allowed_rows": int(seg["segment_calibration_allowed_rows"]),
        "raw_bias_pct": float(evaluation.loc[evaluation["model_variant"].eq("raw_model"), "bias_pct"].iloc[0]),
        "calibrated_bias_pct": float(cal["bias_pct"]),
        "segment_calibrated_bias_pct": float(seg["bias_pct"]),
        "bias_improvement_vs_calibrated": float(gate.iloc[0]["bias_improvement_vs_calibrated"]),
        "missed_units_before": float(gate.iloc[0]["missed_units_before"]),
        "missed_units_after": float(gate.iloc[0]["missed_units_after"]),
        "release_recommendation": str(gate.iloc[0]["customer_release_recommendation"]),
        "primary_blocker": str(gate.iloc[0]["primary_blocker"]),
        "requires_human_approval": True,
        "deployment_status": "PROPOSED_NOT_DEPLOYED",
        "governed_actions_overwritten": False,
        "auto_order_created": False,
    }


def run_phase6a01_segment_bias_calibration(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    return write_phase6a_diagnostics(diagnostics_dir=diagnostics_dir)
