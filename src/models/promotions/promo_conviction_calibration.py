from __future__ import annotations

"""Phase 5L — regime-aware conviction calibration and bias learning."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_demand_backtest import compute_wape
from models.promotions.promo_optimal_stock_learning import (
    apply_optimal_stock_learning,
    simulate_stock_position_outcomes,
)
from models.promotions.promo_regime_state import apply_regime_brain_decisioning, load_regime_artifacts
from models.promotions.promo_stock_outcome_optimisation import (
    DEFAULT_UNIT_COST_PROXY,
    apply_stock_outcome_optimisation,
)
from models.promotions.promo_stock_truth_repair import apply_stock_truth_repair, load_stock_truth_source

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5l01_regime_conviction_calibration")
DEFAULT_MODEL_BIAS_PCT = -23.6
MIN_PROFILE_SAMPLE = 30
SMALL_PROFILE_SAMPLE = 100

PROFILE_GROUP_COLS: tuple[str, ...] = (
    "stock_position_regime",
    "sku_demand_regime",
    "supplier_replenishment_regime",
    "promo_convexity_regime",
    "cash_efficiency_regime",
    "customer_basket_trust_regime",
    "release_ready_flag",
    "promo_demand_source_quality",
    "promo_start_soh_source_quality",
)


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _first_col(frame: pd.DataFrame, names: tuple[str, ...], default: float = 0.0) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce").fillna(default)
    return pd.Series(default, index=frame.index, dtype=float)


def _clip_score(series: pd.Series) -> pd.Series:
    return series.clip(0.0, 100.0).round(1)


def _quality_col(frame: pd.DataFrame) -> str:
    return "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"


def _release_col(frame: pd.DataFrame) -> str:
    return "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in frame.columns else "promo_demand_release_ready_flag"


def _forecast_col(frame: pd.DataFrame) -> pd.Series:
    return _first_col(
        frame,
        (
            "bias_adjusted_expected_units_total_promo",
            "model_expected_units_total_promo_calibrated",
            "model_expected_units_total_promo",
        ),
    )


def _prepare_profile_frame(backtest_df: pd.DataFrame, regime_df: pd.DataFrame) -> pd.DataFrame:
    """Align backtest and regime frames for profile building."""
    if regime_df is backtest_df or len(regime_df) == len(backtest_df):
        out = regime_df.copy()
    else:
        keys = [c for c in ("store_number", "sku_number", "promotion_start_date") if c in backtest_df.columns and c in regime_df.columns]
        out = backtest_df.merge(regime_df, on=keys, how="left", suffixes=("", "_reg"))
    release = _release_col(out)
    out["release_ready_flag"] = out.get(release, pd.Series("NO", index=out.index)).astype(str)
    out["promo_demand_source_quality"] = out.get(_quality_col(out), pd.Series("UNSAFE", index=out.index)).astype(str)
    out["promo_start_soh_source_quality"] = out.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str)
    for col in PROFILE_GROUP_COLS:
        if col not in out.columns:
            out[col] = "UNKNOWN"
        else:
            out[col] = out[col].astype(str).replace({"nan": "UNKNOWN", "": "UNKNOWN"})
    out["_forecast_units"] = _forecast_col(out)
    out["_actual_units"] = _numeric(out, "actual_units_sold_promo")
    out["_forecast_error"] = out["_forecast_units"] - out["_actual_units"]
    out["_abs_error"] = out["_forecast_error"].abs()
    out["_distance_before"] = (_numeric(out, "current_soh") - _numeric(out, "optimal_base_soh_units")).abs()
    out["_distance_after"] = _numeric(out, "distance_to_optimal_end_soh")
    out["_distance_improvement"] = out.get("distance_to_optimal_improvement", out["_distance_before"] - out["_distance_after"])
    out["_missed_demand"] = _numeric(out, "simulated_missed_demand_units")
    out["_leftover"] = _numeric(out, "leftover_units_above_optimal")
    out["_cash_above"] = (_numeric(out, "_leftover") * DEFAULT_UNIT_COST_PROXY).round(3)
    return out


def _profile_key(frame: pd.DataFrame) -> pd.Series:
    parts = [frame[col].astype(str) for col in PROFILE_GROUP_COLS if col in frame.columns]
    if not parts:
        return pd.Series("UNKNOWN", index=frame.index)
    key = parts[0]
    for part in parts[1:]:
        key = key + "|" + part
    return key


def _recommended_confidence_cap(row: pd.Series) -> float:
    cap = 90.0
    n = float(row.get("row_count", 0))
    wape = float(row.get("WAPE", 0.0))
    bias = abs(float(row.get("bias_pct", 0.0)))
    unsafe_share = float(row.get("unsafe_count", 0)) / max(n, 1.0)
    block_share = float(row.get("constraint_block_count", 0)) / max(n, 1.0)
    unknown_soh_share = float(row.get("unknown_soh_count", 0)) / max(n, 1.0)
    missed_avg = float(row.get("missed_demand_units", 0.0)) / max(n, 1.0)
    cash_avg = float(row.get("cash_tied_above_optimal", 0.0)) / max(n, 1.0)

    if n < MIN_PROFILE_SAMPLE:
        cap = min(cap, 35.0)
    elif n < SMALL_PROFILE_SAMPLE:
        cap = min(cap, 55.0)
    if wape > 0.50:
        cap -= 30.0
    elif wape > 0.30:
        cap -= 18.0
    elif wape > 0.15:
        cap -= 8.0
    if bias > 30.0:
        cap -= 28.0
    elif bias > 15.0:
        cap -= 15.0
    if unsafe_share > 0.50:
        cap -= 25.0
    elif unsafe_share > 0.20:
        cap -= 12.0
    if unknown_soh_share > 0.30:
        cap -= 15.0
    if block_share > 0.50:
        cap -= 12.0
    if missed_avg > 2.0:
        cap -= 10.0
    if cash_avg > 50.0:
        cap -= 10.0
    if wape <= 0.15 and bias <= 10.0 and n >= SMALL_PROFILE_SAMPLE and unsafe_share <= 0.10:
        cap = min(85.0, cap + 5.0)
    return float(np.clip(cap, 5.0, 90.0))


def build_regime_error_profile(
    backtest_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build historical error profile by regime segment."""
    del config
    working = _prepare_profile_frame(backtest_df, regime_df)
    working["regime_error_profile_key"] = _profile_key(working)
    quality = _quality_col(working)
    release = _release_col(working)

    rows: list[dict[str, Any]] = []
    for key, chunk in working.groupby("regime_error_profile_key", dropna=False):
        actual = _numeric(chunk, "_actual_units")
        forecast = _numeric(chunk, "_forecast_units")
        err = forecast - actual
        actual_total = float(actual.sum())
        forecast_total = float(forecast.sum())
        bias_pct = float((forecast_total - actual_total) / actual_total * 100.0) if actual_total > 0 else 0.0
        rows.append({
            "regime_error_profile_key": str(key),
            **{col: str(chunk[col].iloc[0]) for col in PROFILE_GROUP_COLS},
            "row_count": int(len(chunk)),
            "actual_units_total": actual_total,
            "forecast_units_total": forecast_total,
            "WAPE": float(compute_wape(actual, forecast)),
            "bias_pct": bias_pct,
            "MAE": float(_numeric(chunk, "_abs_error").mean()),
            "RMSE": float(np.sqrt((_numeric(chunk, "_forecast_error") ** 2).mean())),
            "missed_demand_units": float(_numeric(chunk, "_missed_demand").sum()),
            "leftover_units": float(_numeric(chunk, "_leftover").sum()),
            "cash_tied_above_optimal": float(_numeric(chunk, "_cash_above").sum()),
            "average_distance_to_optimal_before": float(_numeric(chunk, "_distance_before").mean()),
            "average_distance_to_optimal_after": float(_numeric(chunk, "_distance_after").mean()),
            "distance_to_optimal_improvement": float(_numeric(chunk, "_distance_improvement").mean()),
            "release_ready_count": int(chunk.get(release, pd.Series("NO", index=chunk.index)).astype(str).eq("YES").sum()),
            "unsafe_count": int(chunk.get(quality, pd.Series("UNSAFE", index=chunk.index)).astype(str).eq("UNSAFE").sum()),
            "constraint_block_count": int(chunk.get("constraint_block_flag", pd.Series("NO", index=chunk.index)).astype(str).eq("YES").sum()),
            "unknown_soh_count": int(chunk["promo_start_soh_source_quality"].eq("UNKNOWN").sum()),
        })
    profile = pd.DataFrame(rows)
    if profile.empty:
        return profile
    profile["recommended_confidence_cap"] = profile.apply(_recommended_confidence_cap, axis=1).round(1)
    return profile.sort_values("row_count", ascending=False).reset_index(drop=True)


def _conviction_label(score: pd.Series) -> pd.Series:
    return pd.cut(
        score,
        bins=[-0.1, 20, 40, 60, 79.9, 100.0],
        labels=["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"],
    ).astype(str)


def _bias_direction(bias_pct: float) -> str:
    if bias_pct <= -15.0:
        return "UNDERFORECAST"
    if bias_pct >= 15.0:
        return "OVERFORECAST"
    return "NEUTRAL"


def _bias_learning_note(row: pd.Series) -> tuple[str, str, str, str]:
    demand = str(row.get("sku_demand_regime", ""))
    convexity = str(row.get("promo_convexity_regime", ""))
    stock = str(row.get("stock_position_regime", ""))
    soh_q = str(row.get("promo_start_soh_source_quality", ""))
    quality = str(row.get("promo_demand_source_quality", ""))
    bias = float(row.get("regime_historical_bias_pct", 0.0))
    wape = float(row.get("regime_historical_wape", 0.0))
    direction = _bias_direction(bias)

    if soh_q == "UNKNOWN" or quality == "UNSAFE":
        return direction, "HOLD_BIAS_REPAIR", "P0_BLOCKER", "UNKNOWN_STOCK_TRUTH_DO_NOT_LEARN"
    if direction == "UNDERFORECAST" and demand in {"STABLE_BASE_DEMAND", "INTERMITTENT_LOW_VOLUME"} and wape > 0.2:
        return direction, "RAISE_FORECAST_IN_SEGMENT", "P1_HIGH", "UNDERFORECAST_HIGH_VOLUME_PROMOS"
    if direction == "OVERFORECAST" and convexity == "LOW_CONVEXITY" and stock in {"OVERSTOCKED", "SEVERELY_OVERSTOCKED"}:
        return direction, "LOWER_FORECAST_AND_ORDER", "P1_HIGH", "OVERFORECAST_LOW_CONVEXITY_OVERSTOCK"
    cash_regime = str(row.get("cash_efficiency_regime", row.get("cash_tied_above_optimal_regime", "")))
    if wape > 0.35 and cash_regime == "CASH_TIE_UP_RISK":
        return direction, "REDUCE_PROMO_ORDER_BIAS", "P2_MEDIUM", "CASH_DRAG_FROM_WEAK_PROMO_RESPONSE"
    if str(row.get("stock_constraint_regime", "")) == "CENSORED_DEMAND_RISK":
        return direction, "EXCLUDE_FROM_TRAINING", "P1_HIGH", "CENSORED_DEMAND_UNRELIABLE"
    if direction == "NEUTRAL" and wape <= 0.15:
        return direction, "MONITOR_ONLY", "P3_LOW", "STABLE_SEGMENT_NO_REPAIR"
    return direction, "SEGMENT_BIAS_REVIEW", "P2_MEDIUM", f"{direction}_REGIME_BIAS_REVIEW"


def calibrate_regime_conviction(
    scored_df: pd.DataFrame,
    error_profile_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Replace naive conviction with calibrated, evidence-based conviction."""
    cfg = config or {}
    model_bias_pct = float(cfg.get("model_bias_pct", DEFAULT_MODEL_BIAS_PCT))
    gate_recommendation = str(cfg.get("gate_recommendation", "NO_RELEASE"))
    out = scored_df.copy()
    quality = _quality_col(out)

    raw = _numeric(out, "overall_regime_conviction_score")
    if "raw_regime_conviction_score" not in out.columns:
        out["raw_regime_conviction_score"] = raw
    else:
        out["raw_regime_conviction_score"] = _numeric(out, "raw_regime_conviction_score").where(
            _numeric(out, "raw_regime_conviction_score").gt(0), raw
        )

    out["regime_error_profile_key"] = _profile_key(_prepare_profile_frame(out, out))
    profile = error_profile_df.set_index("regime_error_profile_key") if not error_profile_df.empty else pd.DataFrame()
    out["regime_error_profile_row_count"] = out["regime_error_profile_key"].map(
        profile["row_count"] if "row_count" in profile.columns else {}
    ).fillna(0).astype(int)
    out["regime_historical_wape"] = out["regime_error_profile_key"].map(
        profile["WAPE"] if "WAPE" in profile.columns else {}
    ).fillna(1.0).round(4)
    out["regime_historical_bias_pct"] = out["regime_error_profile_key"].map(
        profile["bias_pct"] if "bias_pct" in profile.columns else {}
    ).fillna(0.0).round(2)
    out["regime_confidence_cap"] = out["regime_error_profile_key"].map(
        profile["recommended_confidence_cap"] if "recommended_confidence_cap" in profile.columns else {}
    ).fillna(40.0).round(1)

    calibrated = np.minimum(_numeric(out, "raw_regime_conviction_score"), _numeric(out, "regime_confidence_cap"))
    downgrade_reason = np.where(
        calibrated.lt(_numeric(out, "raw_regime_conviction_score")),
        "regime_historical_cap",
        "",
    )

    unsafe = out.get(quality, pd.Series("UNSAFE", index=out.index)).astype(str).eq("UNSAFE")
    unknown_soh = out.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str).eq("UNKNOWN")
    release_blocked = gate_recommendation == "NO_RELEASE"
    dangerous_bias = model_bias_pct < -15.0

    calibrated = np.where(unsafe, np.minimum(calibrated, 40.0), calibrated)
    downgrade_reason = np.where(unsafe & (calibrated < _numeric(out, "raw_regime_conviction_score")), "unsafe_source_quality_cap", downgrade_reason)
    calibrated = np.where(unknown_soh, np.minimum(calibrated, 65.0), calibrated)
    downgrade_reason = np.where(unknown_soh & (calibrated < _numeric(out, "raw_regime_conviction_score")), "unknown_soh_cap", downgrade_reason)
    calibrated = np.where(release_blocked, np.minimum(calibrated, 79.0), calibrated)
    downgrade_reason = np.where(release_blocked & (calibrated < _numeric(out, "raw_regime_conviction_score")), "release_gate_cap", downgrade_reason)
    calibrated = np.where(dangerous_bias, np.minimum(calibrated, 50.0), calibrated)
    downgrade_reason = np.where(dangerous_bias & (calibrated < _numeric(out, "raw_regime_conviction_score")), "model_bias_dangerously_negative_cap", downgrade_reason)
    calibrated = np.where(_numeric(out, "regime_error_profile_row_count").lt(MIN_PROFILE_SAMPLE), np.minimum(calibrated, 45.0), calibrated)
    downgrade_reason = np.where(
        _numeric(out, "regime_error_profile_row_count").lt(MIN_PROFILE_SAMPLE) & (calibrated < _numeric(out, "raw_regime_conviction_score")),
        "small_sample_regime_cap",
        downgrade_reason,
    )
    calibrated = np.where(_numeric(out, "regime_historical_wape").gt(0.50), np.minimum(calibrated, 35.0), calibrated)
    downgrade_reason = np.where(
        _numeric(out, "regime_historical_wape").gt(0.50) & (calibrated < _numeric(out, "raw_regime_conviction_score")),
        "high_wape_regime_cap",
        downgrade_reason,
    )

    out["calibrated_regime_conviction_score"] = _clip_score(pd.Series(calibrated, index=out.index))
    out["calibrated_conviction_label"] = _conviction_label(out["calibrated_regime_conviction_score"])
    out["conviction_downgrade_reason"] = pd.Series(downgrade_reason, index=out.index).replace("", "none")

    bias_notes = out.apply(_bias_learning_note, axis=1, result_type="expand")
    bias_notes.columns = [
        "regime_bias_direction",
        "regime_bias_adjustment_recommendation",
        "regime_bias_repair_priority",
        "regime_bias_learning_note",
    ]
    out = pd.concat([out, bias_notes], axis=1)

    risk = _numeric(out, "overall_regime_risk_score")
    low_conviction = out["calibrated_conviction_label"].isin(["VERY_LOW", "LOW"])
    medium_conviction = out["calibrated_conviction_label"].eq("MEDIUM")
    blocked = out.get("constraint_block_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES")

    review = low_conviction | (medium_conviction & blocked & risk.ge(35))
    review_reason = np.select(
        [
            low_conviction & risk.ge(40),
            low_conviction,
            medium_conviction & blocked,
        ],
        [
            "low_conviction_high_risk",
            "low_calibrated_conviction",
            "medium_conviction_constraint_block",
        ],
        default="",
    )
    out["buyer_review_required_flag"] = np.where(review, "YES", "NO")
    out["buyer_review_reason"] = pd.Series(review_reason, index=out.index).replace("", "none")
    out["decision_confidence_for_report"] = out["calibrated_regime_conviction_score"]
    out["decision_confidence_label_for_report"] = out["calibrated_conviction_label"]

    # Preserve brain proposal; downgrade governed action only when conviction+risk warrant review.
    downgrade_action = (
        review
        & out.get("final_governed_action_label", pd.Series("", index=out.index)).astype(str).eq("AGGRESSIVE_BUY")
        & risk.ge(35)
    )
    out["final_governed_action_label"] = np.where(
        downgrade_action,
        "CONTROLLED_BUY",
        out.get("final_governed_action_label", out.get("brain_action_label", "")),
    )
    out["overall_regime_conviction_score"] = out["calibrated_regime_conviction_score"]

    numeric_cols = out.select_dtypes(include=[np.number]).columns
    out[numeric_cols] = out[numeric_cols].fillna(0.0)
    return out


def build_conviction_distribution(frame: pd.DataFrame, *, stage: str) -> pd.DataFrame:
    raw = _numeric(frame, "raw_regime_conviction_score") if "raw_regime_conviction_score" in frame.columns else _numeric(frame, "overall_regime_conviction_score")
    cal = _numeric(frame, "calibrated_regime_conviction_score") if "calibrated_regime_conviction_score" in frame.columns else raw
    label_col = frame.get("calibrated_conviction_label", pd.Series("UNKNOWN", index=frame.index)).astype(str)
    rows = [{
        "stage": stage,
        "row_count": int(len(frame)),
        "avg_conviction": float(raw.mean()),
        "p25": float(raw.quantile(0.25)),
        "p50": float(raw.quantile(0.50)),
        "p75": float(raw.quantile(0.75)),
        "very_high_count": int((raw >= 80).sum()),
        "high_count": int(((raw >= 60) & (raw < 80)).sum()),
        "medium_count": int(((raw >= 40) & (raw < 60)).sum()),
        "low_count": int(((raw >= 20) & (raw < 40)).sum()),
        "very_low_count": int((raw < 20).sum()),
    }]
    if stage.endswith("_after"):
        rows[0]["avg_conviction"] = float(cal.mean())
        rows[0]["p25"] = float(cal.quantile(0.25))
        rows[0]["p50"] = float(cal.quantile(0.50))
        rows[0]["p75"] = float(cal.quantile(0.75))
        rows[0]["very_high_count"] = int(label_col.eq("VERY_HIGH").sum())
        rows[0]["high_count"] = int(label_col.eq("HIGH").sum())
        rows[0]["medium_count"] = int(label_col.eq("MEDIUM").sum())
        rows[0]["low_count"] = int(label_col.eq("LOW").sum())
        rows[0]["very_low_count"] = int(label_col.eq("VERY_LOW").sum())
    return pd.DataFrame(rows)


def evaluate_conviction_release_gate(
    frame: pd.DataFrame,
    *,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> tuple[str, str, pd.DataFrame]:
    quality = _quality_col(frame)
    release = _release_col(frame)
    limited = int(
        (
            frame.get("conviction_release_ready_flag", pd.Series("NO")).eq("YES")
            & frame.get(quality, pd.Series("UNSAFE")).isin(["HIGH", "MEDIUM"])
            & frame.get("calibrated_conviction_label", pd.Series("LOW")).isin(["HIGH", "VERY_HIGH"])
        ).sum()
    ) if "conviction_release_ready_flag" in frame.columns else 0

    recommendation = "NO_RELEASE"
    blocker = "model_bias_dangerously_negative" if model_bias_pct < -15.0 else "conviction_not_earned"
    if model_bias_pct >= -15.0 and limited > 0:
        recommendation = "INTERNAL_SHADOW_ONLY"
        blocker = "conviction_shadow_only_bias_or_evidence_not_exceptional"
    if model_bias_pct >= -15.0 and limited > 100 and float(_numeric(frame, "calibrated_regime_conviction_score").mean()) >= 45:
        recommendation = "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"
        blocker = "none_limited_release_earned"

    gate = pd.DataFrame([{
        "recommendation": recommendation,
        "primary_blocker": blocker,
        "limited_release_rows": limited,
        "release_ready_rows": int(frame.get(release, pd.Series("NO")).eq("YES").sum()),
        "unsafe_rows": int(frame.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "avg_raw_conviction": float(_numeric(frame, "raw_regime_conviction_score").mean()),
        "avg_calibrated_conviction": float(_numeric(frame, "calibrated_regime_conviction_score").mean()),
        "buyer_review_required_count": int(frame.get("buyer_review_required_flag", pd.Series("NO")).eq("YES").sum()),
        "unsafe_capped_count": int(
            (
                frame.get(quality, pd.Series("UNSAFE")).eq("UNSAFE")
                & ~frame.get("calibrated_conviction_label", pd.Series("")).isin(["HIGH", "VERY_HIGH"])
            ).sum()
        ),
        "notes": "phase5l_conviction_must_be_earned",
    }])
    return recommendation, blocker, gate


def apply_conviction_calibration(
    scored_df: pd.DataFrame,
    *,
    error_profile_df: pd.DataFrame | None = None,
    gate_recommendation: str = "NO_RELEASE",
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> pd.DataFrame:
    profile = error_profile_df if error_profile_df is not None else build_regime_error_profile(scored_df, scored_df)
    out = calibrate_regime_conviction(
        scored_df,
        profile,
        config={"gate_recommendation": gate_recommendation, "model_bias_pct": model_bias_pct},
    )
    quality = _quality_col(out)
    release = _release_col(out)
    ready = (
        (gate_recommendation == "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        & out.get(release, pd.Series("NO", index=out.index)).astype(str).eq("YES")
        & out.get(quality, pd.Series("UNSAFE", index=out.index)).astype(str).isin(["HIGH", "MEDIUM"])
        & out.get("constraint_block_flag", pd.Series("NO", index=out.index)).astype(str).eq("NO")
        & out.get("calibrated_conviction_label", pd.Series("LOW", index=out.index)).isin(["HIGH", "VERY_HIGH"])
        & out.get("buyer_review_required_flag", pd.Series("NO", index=out.index)).astype(str).eq("NO")
    )
    out["conviction_release_ready_flag"] = np.where(ready, "YES", "NO")
    return out


def write_phase5l01_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    source = frame if frame is not None else apply_stock_truth_repair(load_stock_truth_source(rebuild=rebuild))
    source = apply_stock_outcome_optimisation(source, gate_recommendation="NO_RELEASE")
    source = apply_optimal_stock_learning(source, gate_recommendation="NO_RELEASE")
    working = simulate_stock_position_outcomes(source)
    _regime_gate, regime_rec = load_regime_artifacts()
    regime_enriched = apply_regime_brain_decisioning(working, gate_recommendation=regime_rec)

    before_dist = build_conviction_distribution(regime_enriched, stage="conviction_before")
    profile = build_regime_error_profile(regime_enriched, regime_enriched)
    profile.to_csv(diagnostics_dir / "phase5l01_regime_error_profile.csv", index=False)

    recommendation, blocker, gate = evaluate_conviction_release_gate(regime_enriched, model_bias_pct=model_bias_pct)
    calibrated = apply_conviction_calibration(
        regime_enriched,
        error_profile_df=profile,
        gate_recommendation=recommendation,
        model_bias_pct=model_bias_pct,
    )
    recommendation, blocker, gate = evaluate_conviction_release_gate(calibrated, model_bias_pct=model_bias_pct)

    after_dist = build_conviction_distribution(calibrated, stage="conviction_after")
    pd.concat([before_dist, after_dist], ignore_index=True).to_csv(
        diagnostics_dir / "phase5l01_conviction_score_distribution_before_after.csv",
        index=False,
    )

    downgrade = (
        calibrated.loc[calibrated["conviction_downgrade_reason"].astype(str).ne("none"), "conviction_downgrade_reason"]
        .value_counts()
        .rename_axis("conviction_downgrade_reason")
        .reset_index(name="row_count")
    )
    downgrade.to_csv(diagnostics_dir / "phase5l01_conviction_downgrade_reasons.csv", index=False)

    bias_summary = (
        calibrated.groupby(["regime_bias_repair_priority", "regime_bias_learning_note"], dropna=False)
        .size()
        .rename("row_count")
        .reset_index()
        .sort_values(["regime_bias_repair_priority", "row_count"], ascending=[True, False])
    )
    bias_summary.to_csv(diagnostics_dir / "phase5l01_regime_bias_learning_summary.csv", index=False)

    brain_cols = [
        c for c in (
            "sku_number", "sku_description", "department", "promotion_name",
            "brain_action_label", "brain_order_units_proposal",
            "final_governed_action_label", "final_governed_order_units",
            "raw_regime_conviction_score", "calibrated_regime_conviction_score", "calibrated_conviction_label",
            "conviction_downgrade_reason", "buyer_review_required_flag", "buyer_review_reason",
            "decision_confidence_for_report", "decision_confidence_label_for_report",
            "constraint_block_flag", "constraint_block_reason",
        ) if c in calibrated.columns
    ]
    calibrated[brain_cols].to_csv(diagnostics_dir / "phase5l01_brain_vs_governed_actions_with_conviction.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase5l01_release_gate.csv", index=False)

    quality = _quality_col(calibrated)
    release = _release_col(calibrated)
    raw = _numeric(calibrated, "raw_regime_conviction_score")
    cal = _numeric(calibrated, "calibrated_regime_conviction_score")
    labels = calibrated.get("calibrated_conviction_label", pd.Series("UNKNOWN", index=calibrated.index)).astype(str)

    return {
        "avg_raw_conviction": float(raw.mean()),
        "avg_calibrated_conviction": float(cal.mean()),
        "very_high_before": int((raw >= 80).sum()),
        "high_before": int(((raw >= 60) & (raw < 80)).sum()),
        "very_high_after": int(labels.eq("VERY_HIGH").sum()),
        "high_after": int(labels.eq("HIGH").sum()),
        "unsafe_rows_capped": int(
            (
                calibrated.get(quality, pd.Series("UNSAFE")).eq("UNSAFE")
                & ~labels.isin(["HIGH", "VERY_HIGH"])
            ).sum()
        ),
        "buyer_review_required_count": int(calibrated.get("buyer_review_required_flag", pd.Series("NO")).eq("YES").sum()),
        "top_conviction_downgrade_reasons": downgrade.head(5).set_index("conviction_downgrade_reason")["row_count"].to_dict(),
        "top_regime_bias_repair_priorities": bias_summary.head(5).set_index("regime_bias_learning_note")["row_count"].to_dict(),
        "release_ready_rows": int(calibrated.get(release, pd.Series("NO")).eq("YES").sum()),
        "limited_release_rows": int(gate["limited_release_rows"].iloc[0]),
        "unsafe_rows": int(calibrated.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
    }


def run_phase5l01_conviction_calibration(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
) -> dict[str, Any]:
    return write_phase5l01_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)


def load_conviction_artifacts(diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR) -> tuple[pd.DataFrame, str]:
    gate_path = diagnostics_dir / "phase5l01_release_gate.csv"
    profile_path = diagnostics_dir / "phase5l01_regime_error_profile.csv"
    profile = pd.read_csv(profile_path) if profile_path.exists() else pd.DataFrame()
    if not gate_path.exists():
        return profile, "NO_RELEASE"
    gate = pd.read_csv(gate_path)
    return profile, str(gate["recommendation"].iloc[0]) if not gate.empty else "NO_RELEASE"
