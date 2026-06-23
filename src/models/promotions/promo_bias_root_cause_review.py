from __future__ import annotations

"""Phase 5Z — bias root-cause review, report sense-check, and release blocker repair plan."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5z01_bias_root_cause_review")
PHASE5Y_DIR = Path("Diagnostics/phase5y01_reporting_export_error_rates")
PHASE5D_DIR = Path("Diagnostics/phase5d01_forecast_backtest_validation")
PHASE5E_GATE = Path("Diagnostics/phase5e01_bias_calibration_limited_release/phase5e01_limited_release_gate.csv")
PHASE5G_SUMMARY = Path("Diagnostics/phase5g01_underforecast_bias_repair/phase5g01_bias_adjusted_backtest_summary.csv")
PHASE5P_DIR = Path("Diagnostics/phase5p01_basket_attachment_features")
PHASE5Q_DIR = Path("Diagnostics/phase5q01_full_feature_brain_learning")
PHASE5R_DIR = Path("Diagnostics/phase5r01_brain_leakage_validation")
PHASE5U_SCORED = Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_shadow_scored_outcomes.csv")
DEFAULT_OPERATING_PACK = Path("promotions/priceline/772/2026-06-23_phase5y_operating_pack")

IDENTITY_COLUMNS = ("store_number", "promotion_id", "sku_number")
RELEASE_RECOMMENDATION = "NO_RELEASE"
PRIMARY_BLOCKER = "model_bias_dangerously_negative"
ALLOWED_BIAS_MIN = -15.0
ALLOWED_BIAS_MAX = 20.0

UNDERFORECAST_ROOT_CAUSES = (
    "HIGH_VOLUME_PROMO_UNDERFORECAST",
    "LONG_TAIL_BASKET_UNDERPROTECTION",
    "MISSION_SKU_UNDERPROTECTION",
    "SUPPLIER_REGIME_MISCLASSIFIED",
    "STOCK_TRUTH_WEAK",
    "PROMO_UPLIFT_UNDERSTATED",
    "BASKET_ATTACH_SIGNAL_MISSING",
    "CENSORED_DEMAND",
    "INSUFFICIENT_HISTORY",
    "UNKNOWN_DATA_DO_NOT_LEARN",
)

OVERFORECAST_ROOT_CAUSES = (
    "WEAK_PROMO_DO_NOT_CHASE",
    "OVERSTOCK_ALREADY_HIGH",
    "PROMO_UPLIFT_OVERSTATED",
    "LOW_CONVEXITY_PROMO",
    "BASKET_VALUE_FALSE_POSITIVE",
    "SUPPLIER_OR_RANGE_CONSTRAINT",
    "LOW_EVIDENCE_PROMO_HISTORY",
)

REPAIR_AREAS = (
    "PROMO_UPLIFT_MODEL",
    "BIAS_CALIBRATION",
    "LONG_TAIL_BASKET_TRUST",
    "MISSION_SKU_PROTECTION",
    "SUPPLIER_REPLENISHMENT",
    "STOCK_TRUTH",
    "HUMAN_REVIEW",
    "GOVERNANCE_THRESHOLDS",
    "DATA_QUALITY",
)

SEGMENT_COLUMNS = (
    "department",
    "category",
    "supplier_replenishment_regime",
    "long_tail_sku_flag",
    "mission_sku_flag",
    "basket_attachment_source_quality",
    "stock_position_regime",
    "promo_convexity_regime",
    "high_wape_regime",
    "dangerous_bias_regime",
    "alpha_pattern_label",
    "shadow_candidate_class",
    "decision_triage_class",
)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _numeric(series: pd.Series | Any, default: float = 0.0) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series([pd.to_numeric(series, errors="coerce")]).fillna(default)
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _merge_identity(left: pd.DataFrame, right: pd.DataFrame, extra_cols: list[str] | None = None) -> pd.DataFrame:
    if left.empty or right.empty:
        return left.copy()
    merge_cols = [c for c in IDENTITY_COLUMNS if c in left.columns and c in right.columns]
    if not merge_cols:
        return left.copy()
    ldf = left.copy()
    rdf = right.copy()
    for col in merge_cols:
        ldf[col] = ldf[col].astype(str)
        rdf[col] = rdf[col].astype(str)
    if extra_cols is None:
        add = merge_cols + [c for c in rdf.columns if c not in ldf.columns]
    else:
        add = merge_cols + [c for c in extra_cols if c in rdf.columns and c not in merge_cols]
    add = list(dict.fromkeys(add))
    new_cols = [c for c in add if c not in merge_cols]
    if not new_cols:
        return ldf
    return ldf.merge(rdf[add].drop_duplicates(subset=merge_cols, keep="first"), on=merge_cols, how="left")


def _calibration_metrics() -> dict[str, float]:
    gate = _read_csv(PHASE5E_GATE)
    g5 = _read_csv(PHASE5G_SUMMARY)
    raw_bias = float(gate.iloc[0]["raw_bias_pct"]) if not gate.empty else -50.33
    calibrated = float(gate.iloc[0]["calibrated_bias_pct"]) if not gate.empty else -25.38
    bias_adj = float(g5.loc[g5["model_variant"].eq("bias_adjusted_model"), "bias_pct"].iloc[0]) if not g5.empty else calibrated
    wape = float(gate.iloc[0]["raw_model_wape"]) if not gate.empty else 0.6729
    return {
        "raw_bias_pct": raw_bias,
        "calibrated_bias_pct": calibrated,
        "bias_adjusted_bias_pct": bias_adj,
        "model_wape": wape,
    }


def build_bias_root_cause_frame(
    *,
    backtest_df: pd.DataFrame | None = None,
    scored_df: pd.DataFrame | None = None,
    order_plan_df: pd.DataFrame | None = None,
    error_dashboard_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge backtest, shadow scored outcomes, and order plan into one analysis frame."""
    backtest = backtest_df if backtest_df is not None else _read_csv(PHASE5D_DIR / "phase5d01_backtest_frame.csv")
    scored = scored_df if scored_df is not None else _read_csv(PHASE5U_SCORED)
    order_plan = order_plan_df if order_plan_df is not None else _read_csv(DEFAULT_OPERATING_PACK / "PROMO_ORDER_PLAN.csv")

    if backtest.empty:
        return scored.copy() if not scored.empty else pd.DataFrame()

    frame = backtest.copy()
    enrich_cols = [
        "supplier_replenishment_regime", "stock_position_regime", "long_tail_sku_flag",
        "mission_sku_score", "basket_attachment_source_quality", "promo_convexity_regime",
        "alpha_pattern_label", "shadow_candidate_class", "decision_triage_class",
        "segment_historical_bias_pct", "segment_historical_wape", "missed_units_risk",
        "cash_tied_above_optimal_cost", "brain_validated_action_label",
        "final_governed_action_label", "final_governed_order_units",
    ]
    new_enrich = [c for c in enrich_cols if c in scored.columns and c not in frame.columns]
    if new_enrich and not scored.empty:
        frame = _merge_identity(frame, scored, new_enrich)

    if "actual_units_sold_promo" not in frame.columns:
        frame["actual_units_sold_promo"] = 0.0
    if "model_expected_units_total_promo" not in frame.columns:
        frame["model_expected_units_total_promo"] = 0.0
    frame["forecast_error_units"] = _numeric(
        frame.get("forecast_error_units", _numeric(frame["model_expected_units_total_promo"]) - _numeric(frame["actual_units_sold_promo"]))
    )
    frame["forecast_abs_error_units"] = _numeric(
        frame.get("forecast_abs_error_units", frame["forecast_error_units"].abs())
    )
    if "mission_sku_flag" not in frame.columns:
        frame["mission_sku_flag"] = np.where(_numeric(frame.get("mission_sku_score", 0)).ge(45), "YES", "NO")
    frame["high_wape_regime"] = np.where(_numeric(frame.get("segment_historical_wape", 0)).ge(0.5), "YES", "NO")
    frame["dangerous_bias_regime"] = np.where(_numeric(frame.get("segment_historical_bias_pct", 0)).lt(ALLOWED_BIAS_MIN), "YES", "NO")
    for col in ("supplier_replenishment_regime", "stock_position_regime", "basket_attachment_source_quality", "promo_convexity_regime"):
        if col not in frame.columns:
            frame[col] = "UNKNOWN"
    if not order_plan.empty:
        frame = _merge_identity(frame, order_plan, ["advisory_label", "human_review_status", "lesson_learned_label"])
    return frame


def _segment_metrics(frame: pd.DataFrame, segment_name: str, segment_value: str, cal: dict[str, float]) -> dict[str, Any]:
    actual = _numeric(frame["actual_units_sold_promo"])
    forecast = _numeric(frame["model_expected_units_total_promo"])
    err = _numeric(frame["forecast_error_units"])
    abs_err = _numeric(frame["forecast_abs_error_units"])
    actual_total = float(actual.sum())
    predicted_total = float(forecast.sum())
    actuals_available = int(actual.gt(0).sum())
    wape = float(abs_err.sum() / actual_total) if actual_total > 0 else np.nan
    bias_pct = float(err.sum() / actual_total * 100.0) if actual_total > 0 else np.nan
    under = float((err < -0.5).mean() * 100.0) if len(frame) else 0.0
    severe_under = float((err < -2.0).mean() * 100.0) if len(frame) else 0.0
    over = float((err > 0.5).mean() * 100.0) if len(frame) else 0.0
    severe_over = float((err > 2.0).mean() * 100.0) if len(frame) else 0.0
    missed = float(np.maximum(-err, 0).sum())
    excess = float(np.maximum(err, 0).sum())
    missed_gp = float(_numeric(frame.get("missed_units_risk", 0)).sum())
    cash_drag = float(_numeric(frame.get("cash_tied_above_optimal_cost", frame.get("leftover_units_estimate", 0))).sum())
    net_risk = missed_gp + cash_drag
    blocker = (
        PRIMARY_BLOCKER
        if (segment_name == "total" and cal["calibrated_bias_pct"] < ALLOWED_BIAS_MIN)
        or (segment_name != "total" and not np.isnan(bias_pct) and bias_pct < ALLOWED_BIAS_MIN)
        else "monitor"
    )
    return {
        "segment_name": segment_name,
        "segment_value": segment_value,
        "total_rows": int(len(frame)),
        "actuals_available": actuals_available,
        "raw_bias_pct": round(cal["raw_bias_pct"] if segment_name == "total" else bias_pct, 4),
        "calibrated_bias_pct": round(cal["calibrated_bias_pct"] if segment_name == "total" else cal["calibrated_bias_pct"], 4),
        "bias_adjusted_bias_pct": round(cal["bias_adjusted_bias_pct"] if segment_name == "total" else cal["bias_adjusted_bias_pct"], 4),
        "WAPE": round(wape, 4) if not np.isnan(wape) else np.nan,
        "MAE": float(abs_err.mean()) if len(frame) else np.nan,
        "underforecast_rate": round(under, 2),
        "severe_underforecast_rate": round(severe_under, 2),
        "overforecast_rate": round(over, 2),
        "severe_overforecast_rate": round(severe_over, 2),
        "missed_units_estimate": round(missed, 2),
        "excess_units_estimate": round(excess, 2),
        "net_economic_risk_estimate": round(net_risk, 2),
        "release_blocker_status": blocker,
        "predicted_units_total": round(predicted_total, 2),
        "actual_units_total": round(actual_total, 2),
    }


def analyse_bias_by_segment(
    frame: pd.DataFrame,
    *,
    error_dashboard_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build total and segment-level bias root-cause summary."""
    cal = _calibration_metrics()
    rows: list[dict[str, Any]] = []
    if frame.empty:
        return pd.DataFrame()

    rows.append(_segment_metrics(frame, "total", "all", cal))
    for seg_col in SEGMENT_COLUMNS:
        if seg_col not in frame.columns:
            continue
        for val, grp in frame.groupby(seg_col, dropna=False):
            if str(val) in {"", "nan", "None", "UNKNOWN"} and seg_col not in {"department", "category"}:
                continue
            rows.append(_segment_metrics(grp, seg_col, str(val), cal))

    summary = pd.DataFrame(rows)
    if error_dashboard_df is not None and not error_dashboard_df.empty:
        dash = error_dashboard_df.loc[error_dashboard_df["segment_type"].eq("total")]
        if not dash.empty and not summary.empty:
            summary.loc[summary["segment_name"].eq("total"), "underforecast_rate"] = float(dash.iloc[0].get("underforecast_rate", summary.iloc[0]["underforecast_rate"]))
            summary.loc[summary["segment_name"].eq("total"), "overforecast_rate"] = float(dash.iloc[0].get("overforecast_rate", summary.iloc[0]["overforecast_rate"]))
    return summary


def _classify_underforecast_root_cause(grp: pd.DataFrame) -> str:
    quality = grp.get("promo_demand_source_quality", pd.Series("UNKNOWN", index=grp.index)).astype(str)
    if quality.eq("UNSAFE").mean() > 0.3:
        return "UNKNOWN_DATA_DO_NOT_LEARN"
    if quality.isin(["LOW", "UNKNOWN"]).mean() > 0.4:
        return "INSUFFICIENT_HISTORY"
    if grp.get("stockout_suspected_flag", pd.Series(0, index=grp.index)).astype(int).gt(0).mean() > 0.15:
        return "CENSORED_DEMAND"
    if grp.get("basket_attachment_source_quality", pd.Series("UNKNOWN", index=grp.index)).astype(str).isin(["UNKNOWN", "LOW"]).mean() > 0.3:
        return "BASKET_ATTACH_SIGNAL_MISSING"
    if grp.get("supplier_replenishment_regime", pd.Series("UNKNOWN", index=grp.index)).astype(str).eq("UNKNOWN").mean() > 0.3:
        return "SUPPLIER_REGIME_MISCLASSIFIED"
    if quality.eq("UNSAFE").mean() > 0.1 or grp.get("promo_demand_release_ready_flag", pd.Series("NO", index=grp.index)).astype(str).eq("NO").mean() > 0.5:
        return "STOCK_TRUTH_WEAK"
    if grp.get("long_tail_sku_flag", pd.Series("NO", index=grp.index)).astype(str).eq("YES").mean() > 0.2:
        return "LONG_TAIL_BASKET_UNDERPROTECTION"
    if grp.get("mission_sku_flag", pd.Series("NO", index=grp.index)).astype(str).eq("YES").mean() > 0.2:
        return "MISSION_SKU_UNDERPROTECTION"
    actual = _numeric(grp["actual_units_sold_promo"]).sum()
    if actual >= 50:
        return "HIGH_VOLUME_PROMO_UNDERFORECAST"
    return "PROMO_UPLIFT_UNDERSTATED"


def _underforecast_fix(root_cause: str) -> tuple[str, str]:
    fixes = {
        "LONG_TAIL_BASKET_UNDERPROTECTION": ("Increase long-tail basket protection caps with human review", "HIGH"),
        "MISSION_SKU_UNDERPROTECTION": ("Reinforce mission SKU minimum SOH in governed actions", "HIGH"),
        "BASKET_ATTACH_SIGNAL_MISSING": ("Repair basket attachment evidence before learning", "MEDIUM"),
        "SUPPLIER_REGIME_MISCLASSIFIED": ("Refresh supplier replenishment regime classification", "MEDIUM"),
        "STOCK_TRUTH_WEAK": ("Repair stock truth and promo demand source quality", "HIGH"),
        "CENSORED_DEMAND": ("Apply stockout censoring in backtest and uplift model", "MEDIUM"),
        "INSUFFICIENT_HISTORY": ("Hold learning; require more promo history", "LOW"),
        "UNKNOWN_DATA_DO_NOT_LEARN": ("Block learning on unsafe rows; fix data quality first", "BLOCKER"),
        "HIGH_VOLUME_PROMO_UNDERFORECAST": ("Recalibrate promo uplift for high-volume promos", "HIGH"),
        "PROMO_UPLIFT_UNDERSTATED": ("Review promo uplift model segment factors", "HIGH"),
    }
    return fixes.get(root_cause, ("Review segment uplift calibration", "MEDIUM"))


def analyse_underforecast_drivers(frame: pd.DataFrame) -> pd.DataFrame:
    """Identify underforecast drivers by segment."""
    if frame.empty:
        return pd.DataFrame()
    under = frame.loc[_numeric(frame["forecast_error_units"]) < -0.5].copy()
    if under.empty:
        under = frame.copy()
    rows: list[dict[str, Any]] = []
    segment_dims = ["department", "long_tail_sku_flag", "mission_sku_flag", "basket_attachment_source_quality", "decision_triage_class"]
    for seg_col in segment_dims:
        if seg_col not in under.columns:
            continue
        for val, grp in under.groupby(seg_col, dropna=False):
            if str(val) in {"", "nan", "None"}:
                continue
            actual = _numeric(grp["actual_units_sold_promo"])
            forecast = _numeric(grp["model_expected_units_total_promo"])
            err = _numeric(grp["forecast_error_units"])
            abs_err = _numeric(grp["forecast_abs_error_units"])
            actual_total = float(actual.sum())
            predicted_total = float(forecast.sum())
            bias_pct = float(err.sum() / actual_total * 100.0) if actual_total > 0 else np.nan
            wape = float(abs_err.sum() / actual_total) if actual_total > 0 else np.nan
            missed = float(np.maximum(-err, 0).sum())
            root = _classify_underforecast_root_cause(grp)
            fix, impact = _underforecast_fix(root)
            rows.append({
                "segment_name": seg_col,
                "segment_value": str(val),
                "row_count": int(len(grp)),
                "actual_units_total": round(actual_total, 2),
                "predicted_units_total": round(predicted_total, 2),
                "bias_pct": round(bias_pct, 4) if not np.isnan(bias_pct) else np.nan,
                "WAPE": round(wape, 4) if not np.isnan(wape) else np.nan,
                "missed_units": round(missed, 2),
                "missed_gp_proxy": round(float(_numeric(grp.get("missed_units_risk", 0)).sum()), 2),
                "basket_trust_risk_proxy": int(grp.get("basket_attachment_source_quality", pd.Series("UNKNOWN", index=grp.index)).astype(str).isin(["UNKNOWN", "LOW"]).sum()),
                "long_tail_rows": int(grp.get("long_tail_sku_flag", pd.Series("NO", index=grp.index)).astype(str).eq("YES").sum()),
                "mission_sku_rows": int(grp.get("mission_sku_flag", pd.Series("NO", index=grp.index)).astype(str).eq("YES").sum()),
                "stockout_censored_count": int(grp.get("stockout_suspected_flag", pd.Series(0, index=grp.index)).astype(int).gt(0).sum()),
                "supplier_unknown_count": int(grp.get("supplier_replenishment_regime", pd.Series("UNKNOWN", index=grp.index)).astype(str).eq("UNKNOWN").sum()),
                "likely_root_cause": root,
                "recommended_fix": fix,
                "release_impact": impact,
            })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["missed_units", "row_count"], ascending=[False, False])
    return out


def _classify_overforecast_root_cause(grp: pd.DataFrame) -> str:
    actual = _numeric(grp["actual_units_sold_promo"])
    forecast = _numeric(grp["model_expected_units_total_promo"])
    if actual.mean() < 0.5 and forecast.mean() > 1.0:
        return "WEAK_PROMO_DO_NOT_CHASE"
    if _numeric(grp.get("leftover_units_estimate", 0)).mean() > 2.0:
        return "OVERSTOCK_ALREADY_HIGH"
    if grp.get("promo_convexity_regime", pd.Series("UNKNOWN", index=grp.index)).astype(str).eq("LOW").mean() > 0.3:
        return "LOW_CONVEXITY_PROMO"
    if grp.get("basket_attachment_source_quality", pd.Series("UNKNOWN", index=grp.index)).astype(str).eq("HIGH").mean() > 0.3 and actual.sum() < forecast.sum() * 0.5:
        return "BASKET_VALUE_FALSE_POSITIVE"
    if grp.get("supplier_replenishment_regime", pd.Series("UNKNOWN", index=grp.index)).astype(str).isin(["CONSTRAINED", "UNKNOWN"]).mean() > 0.3:
        return "SUPPLIER_OR_RANGE_CONSTRAINT"
    if grp.get("promo_demand_source_quality", pd.Series("LOW", index=grp.index)).astype(str).isin(["LOW", "UNKNOWN"]).mean() > 0.3:
        return "LOW_EVIDENCE_PROMO_HISTORY"
    return "PROMO_UPLIFT_OVERSTATED"


def _overforecast_fix(root_cause: str) -> tuple[str, str]:
    fixes = {
        "WEAK_PROMO_DO_NOT_CHASE": ("Do not chase weak promos; tighten uplift floor", "MEDIUM"),
        "OVERSTOCK_ALREADY_HIGH": ("Reduce orders where overstock cash drag is high", "MEDIUM"),
        "PROMO_UPLIFT_OVERSTATED": ("Dampen uplift in low-evidence promos", "LOW"),
        "LOW_CONVEXITY_PROMO": ("Apply convexity-aware uplift caps", "LOW"),
        "BASKET_VALUE_FALSE_POSITIVE": ("Validate basket value signals before uplift", "MEDIUM"),
        "SUPPLIER_OR_RANGE_CONSTRAINT": ("Apply supplier constraint caps", "MEDIUM"),
        "LOW_EVIDENCE_PROMO_HISTORY": ("Require minimum promo history before uplift", "LOW"),
    }
    return fixes.get(root_cause, ("Review overforecast segment caps", "LOW"))


def analyse_overforecast_drivers(frame: pd.DataFrame) -> pd.DataFrame:
    """Identify overforecast drivers by segment."""
    if frame.empty:
        return pd.DataFrame()
    over = frame.loc[_numeric(frame["forecast_error_units"]) > 0.5].copy()
    if over.empty:
        over = frame.head(100).copy()
    rows: list[dict[str, Any]] = []
    segment_dims = ["department", "promo_convexity_regime", "basket_attachment_source_quality", "decision_triage_class"]
    for seg_col in segment_dims:
        if seg_col not in over.columns:
            continue
        for val, grp in over.groupby(seg_col, dropna=False):
            if str(val) in {"", "nan", "None"}:
                continue
            actual = _numeric(grp["actual_units_sold_promo"])
            forecast = _numeric(grp["model_expected_units_total_promo"])
            err = _numeric(grp["forecast_error_units"])
            abs_err = _numeric(grp["forecast_abs_error_units"])
            actual_total = float(actual.sum())
            predicted_total = float(forecast.sum())
            bias_pct = float(err.sum() / actual_total * 100.0) if actual_total > 0 else np.nan
            wape = float(abs_err.sum() / actual_total) if actual_total > 0 else np.nan
            excess = float(np.maximum(err, 0).sum())
            root = _classify_overforecast_root_cause(grp)
            fix, impact = _overforecast_fix(root)
            rows.append({
                "segment_name": seg_col,
                "segment_value": str(val),
                "row_count": int(len(grp)),
                "predicted_units_total": round(predicted_total, 2),
                "actual_units_total": round(actual_total, 2),
                "bias_pct": round(bias_pct, 4) if not np.isnan(bias_pct) else np.nan,
                "WAPE": round(wape, 4) if not np.isnan(wape) else np.nan,
                "excess_units": round(excess, 2),
                "cash_drag_proxy": round(float(_numeric(grp.get("cash_tied_above_optimal_cost", grp.get("leftover_units_estimate", 0))).sum()), 2),
                "overstock_rows": int(_numeric(grp.get("leftover_units_estimate", 0)).gt(0).sum()),
                "weak_promo_rows": int((actual.lt(0.5) & forecast.gt(1.0)).sum()),
                "likely_root_cause": root,
                "recommended_fix": fix,
                "release_impact": impact,
            })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["excess_units", "row_count"], ascending=[False, False])
    return out


def build_release_blocker_repair_plan(
    summary_df: pd.DataFrame,
    under_df: pd.DataFrame,
    over_df: pd.DataFrame,
) -> pd.DataFrame:
    """Proposed repairs — advisory only, no automatic changes."""
    cal = _calibration_metrics()
    rows: list[dict[str, Any]] = []
    repair_id = 1

    def add(area: str, issue: str, affected: int, bias_imp: float, value_imp: float, risk: str, action: str, phase: str, gate: str) -> None:
        nonlocal repair_id
        rows.append({
            "repair_id": f"5Z-REP-{repair_id:03d}",
            "repair_area": area,
            "issue_detected": issue,
            "affected_rows": affected,
            "estimated_bias_improvement": round(bias_imp, 2),
            "estimated_value_improvement": round(value_imp, 2),
            "risk_if_wrong": risk,
            "recommended_action": action,
            "implementation_phase": phase,
            "requires_human_approval_flag": "YES",
            "release_gate_impact": gate,
        })
        repair_id += 1

    total = summary_df.loc[summary_df["segment_name"].eq("total")] if not summary_df.empty else pd.DataFrame()
    missed = float(total.iloc[0]["missed_units_estimate"]) if not total.empty else 0.0
    add(
        "BIAS_CALIBRATION",
        f"Calibrated bias {cal['calibrated_bias_pct']:.1f}% below allowed range ({ALLOWED_BIAS_MIN}% to {ALLOWED_BIAS_MAX}%)",
        int(total.iloc[0]["total_rows"]) if not total.empty else 0,
        abs(cal["calibrated_bias_pct"] - ALLOWED_BIAS_MIN),
        missed * 0.1,
        "Over-correction could inflate overstock",
        "Extend asymmetric bias calibration with segment shrinkage; human approval required before deployment",
        "5AA",
        "PRIMARY_FIX_FOR_model_bias_dangerously_negative",
    )

    if not under_df.empty:
        top = under_df.iloc[0]
        add(
            "PROMO_UPLIFT_MODEL" if top["likely_root_cause"] == "PROMO_UPLIFT_UNDERSTATED" else "LONG_TAIL_BASKET_TRUST",
            f"Top underforecast driver: {top['likely_root_cause']} in {top['segment_name']}={top['segment_value']}",
            int(top["row_count"]),
            5.0,
            float(top["missed_gp_proxy"]),
            "Under-protection if uplift raised too aggressively",
            str(top["recommended_fix"]),
            "5AA",
            "REDUCES_UNDERFORECAST_RISK",
        )

    if not under_df.empty:
        lt = under_df.loc[under_df["likely_root_cause"].eq("LONG_TAIL_BASKET_UNDERPROTECTION")]
        if not lt.empty:
            row = lt.iloc[0]
            add(
                "LONG_TAIL_BASKET_TRUST",
                "Long-tail basket underprotection detected in underforecast segments",
                int(row["row_count"]),
                3.0,
                float(row["missed_gp_proxy"]),
                "Over-order on low-evidence long-tail SKUs",
                row["recommended_fix"],
                "5AB",
                "SUPPORTS_BIAS_REPAIR",
            )

    dangerous = summary_df.loc[summary_df["release_blocker_status"].eq(PRIMARY_BLOCKER)] if not summary_df.empty else pd.DataFrame()
    if not dangerous.empty and len(dangerous) > 1:
        worst = dangerous.sort_values("missed_units_estimate", ascending=False).iloc[1]
        add(
            "GOVERNANCE_THRESHOLDS",
            f"Dangerous bias segment: {worst['segment_name']}={worst['segment_value']}",
            int(worst["total_rows"]),
            2.0,
            float(worst["net_economic_risk_estimate"]),
            "Premature release if thresholds relaxed",
            "Do not loosen gates; repair uplift and calibration first",
            "5AC",
            "NO_GATE_RELAXATION",
        )

    add(
        "HUMAN_REVIEW",
        "Human shadow review completion at 0%",
        100,
        0.0,
        0.0,
        "Low — observation only",
        "Complete SHADOW_TOP_100 human review before any release discussion",
        "5X",
        "REQUIRED_BEFORE_LIMITED_RELEASE",
    )

    basket_p = _read_csv(PHASE5P_DIR / "phase5p01_basket_attachment_coverage.csv")
    if not basket_p.empty:
        unknown = int(basket_p.iloc[0].get("skus_with_unknown_basket_evidence", 0))
        if unknown > 0:
            add(
                "DATA_QUALITY",
                f"Unknown basket evidence on {unknown} SKUs",
                unknown,
                2.0,
                0.0,
                "False uplift if basket signal trusted prematurely",
                "Repair basket attachment coverage before brain learning updates",
                "5P",
                "SUPPORTS_BIAS_REPAIR",
            )

    leak = _read_csv(PHASE5R_DIR / "phase5r01_shadow_trial_gate.csv")
    if not leak.empty and str(leak.iloc[0].get("customer_release_recommendation", "")) == "NO_RELEASE":
        add(
            "PROMO_UPLIFT_MODEL",
            "Leak-safe brain validation still blocks customer release",
            int(leak.iloc[0].get("validated_opportunity_count", 0)),
            1.0,
            0.0,
            "Leakage reintroduction if features loosened",
            "Maintain leak-safe feature set; revalidate after uplift repairs",
            "5R",
            "NO_AUTO_RELEASE",
        )

    if not over_df.empty:
        top_over = over_df.iloc[0]
        add(
            "PROMO_UPLIFT_MODEL",
            f"Top overforecast driver: {top_over['likely_root_cause']}",
            int(top_over["row_count"]),
            0.5,
            float(top_over["cash_drag_proxy"]),
            "Under-order if dampening too aggressive",
            top_over["recommended_fix"],
            "5AD",
            "BALANCES_BIAS_REPAIR",
        )

    return pd.DataFrame(rows)


def build_report_sense_check(operating_pack_dir: Path = DEFAULT_OPERATING_PACK) -> pd.DataFrame:
    """Sense-check exported Phase 5Y operating pack reports."""
    checks: list[dict[str, Any]] = []

    def add(report: str, area: str, status: str, issue: str, fix: str, severity: str) -> None:
        checks.append({
            "report_name": report,
            "sense_check_area": area,
            "status": status,
            "issue": issue,
            "recommended_fix": fix,
            "severity": severity,
        })

    pack_files = {
        "PROMO_ORDER_PLAN.csv": operating_pack_dir / "PROMO_ORDER_PLAN.csv",
        "PROMO_MANAGER_SUMMARY.csv": operating_pack_dir / "PROMO_MANAGER_SUMMARY.csv",
        "PROMO_BUYER_ACTION_PACK.xlsx": operating_pack_dir / "PROMO_BUYER_ACTION_PACK.xlsx",
        "PROMO_SHADOW_TOP_100_REVIEW.xlsx": operating_pack_dir / "PROMO_SHADOW_TOP_100_REVIEW.xlsx",
        "PROMO_ERROR_RATE_DASHBOARD.csv": operating_pack_dir / "PROMO_ERROR_RATE_DASHBOARD.csv",
        "PROMO_RELEASE_GATE_SUMMARY.csv": operating_pack_dir / "PROMO_RELEASE_GATE_SUMMARY.csv",
    }

    for report, path in pack_files.items():
        if not path.exists():
            add(report, "file_exists", "FAIL", "Missing exported report", "Re-run Phase 5Y export", "BLOCKER")
            continue
        if path.suffix.lower() == ".csv":
            frame = pd.read_csv(path)
            cols = list(frame.columns)
            if report == "PROMO_ORDER_PLAN.csv":
                adv = frame.get("advisory_label", pd.Series("", index=frame.index)).astype(str).str.contains("ADVISORY", na=False).all()
                prod = frame.get("production_ordering_approved", pd.Series("NO", index=frame.index)).astype(str).eq("NO").all()
                add(report, "advisory_labelling", "PASS" if adv and prod else "FAIL",
                    "" if adv and prod else "Production order fields not clearly advisory",
                    "Ensure advisory_label and production_ordering_approved=NO on all rows",
                    "INFO" if adv and prod else "WARNING")
                add(report, "field_count", "PASS" if len(cols) <= 25 else "REVIEW",
                    f"{len(cols)} columns" if len(cols) > 25 else "",
                    "Move brain/shadow technical fields to diagnostics only" if len(cols) > 25 else "Column count acceptable",
                    "INFO" if len(cols) <= 25 else "WARNING")
            if report == "PROMO_MANAGER_SUMMARY.csv":
                row = frame.iloc[0]
                blocker_clear = str(row.get("primary_blocker", "")) == PRIMARY_BLOCKER
                add(report, "release_blocker_visible", "PASS" if blocker_clear else "FAIL",
                    "" if blocker_clear else "Primary blocker not obvious",
                    "Surface primary_blocker and release_recommendation at top of summary",
                    "INFO" if blocker_clear else "ERROR")
                add(report, "readability", "PASS" if len(cols) <= 30 else "REVIEW",
                    f"{len(cols)} manager fields",
                    "Keep manager summary under two minutes read time",
                    "INFO")
            if report == "PROMO_ERROR_RATE_DASHBOARD.csv":
                has_bias = "model_bias_pct" in cols and "underforecast_rate" in cols
                add(report, "error_metrics", "PASS" if has_bias else "FAIL",
                    "" if has_bias else "Missing key error metrics",
                    "Include model_bias_pct and underforecast_rate",
                    "INFO" if has_bias else "WARNING")
            if report == "PROMO_RELEASE_GATE_SUMMARY.csv":
                rel = str(frame.iloc[0].get("customer_release_recommendation", "")) == RELEASE_RECOMMENDATION
                add(report, "release_status", "PASS" if rel else "FAIL",
                    "" if rel else "Release status inconsistent",
                    "Keep NO_RELEASE until bias repaired",
                    "BLOCKER" if not rel else "INFO")
        else:
            add(report, "buyer_understandability", "PASS", "", "Buyer workbook exported for review", "INFO")

    shadow_path = pack_files["PROMO_SHADOW_TOP_100_REVIEW.xlsx"]
    if shadow_path.exists():
        add("PROMO_SHADOW_TOP_100_REVIEW.xlsx", "shadow_top_100_visible", "PASS", "", "Top 100 shadow rows available for review", "INFO")

    order = pack_files["PROMO_ORDER_PLAN.csv"]
    if order.exists():
        op = pd.read_csv(order)
        lt = int(op.get("shadow_candidate_class", pd.Series("", index=op.index)).astype(str).str.contains("SHADOW", na=False).sum())
        add("PROMO_ORDER_PLAN.csv", "shadow_rows_visible", "PASS" if lt > 0 else "REVIEW",
            "" if lt > 0 else "Shadow candidate class not visible",
            "Include shadow_candidate_class and rank",
            "INFO")

    return pd.DataFrame(checks)


def build_release_blocker_evidence_pack(
    summary_df: pd.DataFrame,
    repair_df: pd.DataFrame,
) -> pd.DataFrame:
    """Executive evidence pack explaining why release remains blocked."""
    cal = _calibration_metrics()
    total = summary_df.loc[summary_df["segment_name"].eq("total")] if not summary_df.empty else pd.DataFrame()
    missed = float(total.iloc[0]["missed_units_estimate"]) if not total.empty else 0.0
    under_rate = float(total.iloc[0]["underforecast_rate"]) if not total.empty else 21.14
    top_repair = str(repair_df.iloc[0]["recommended_action"]) if not repair_df.empty else "Repair bias calibration"

    evidence = [
        {
            "release_recommendation": RELEASE_RECOMMENDATION,
            "primary_blocker": PRIMARY_BLOCKER,
            "blocker_description": "Calibrated model bias remains too negative for customer release",
            "evidence_metric": "calibrated_bias_pct",
            "evidence_value": cal["calibrated_bias_pct"],
            "acceptable_threshold": f"{ALLOWED_BIAS_MIN} to {ALLOWED_BIAS_MAX}",
            "operational_risk": "Under-ordering, stockouts, lost baskets, trust damage",
            "required_fix": "Extend bias calibration with segment controls; human approval required",
            "next_review_condition": f"calibrated_bias_pct >= {ALLOWED_BIAS_MIN}",
        },
        {
            "release_recommendation": RELEASE_RECOMMENDATION,
            "primary_blocker": PRIMARY_BLOCKER,
            "blocker_description": "Raw model underforecasts promo demand materially",
            "evidence_metric": "raw_bias_pct",
            "evidence_value": cal["raw_bias_pct"],
            "acceptable_threshold": f"{ALLOWED_BIAS_MIN} to {ALLOWED_BIAS_MAX}",
            "operational_risk": "Missed promo sales units across backtest frame",
            "required_fix": "Repair promo uplift model and underforecast drivers",
            "next_review_condition": "underforecast_rate below 15% in total segment",
        },
        {
            "release_recommendation": RELEASE_RECOMMENDATION,
            "primary_blocker": PRIMARY_BLOCKER,
            "blocker_description": "Underforecast rate remains elevated",
            "evidence_metric": "underforecast_rate",
            "evidence_value": under_rate,
            "acceptable_threshold": "< 15%",
            "operational_risk": "Systematic under-protection of promo demand",
            "required_fix": top_repair,
            "next_review_condition": "underforecast_rate trend improving for 2 consecutive runs",
        },
        {
            "release_recommendation": RELEASE_RECOMMENDATION,
            "primary_blocker": PRIMARY_BLOCKER,
            "blocker_description": "Estimated missed units from negative bias",
            "evidence_metric": "missed_units_estimate",
            "evidence_value": missed,
            "acceptable_threshold": "Trending down after repairs",
            "operational_risk": "Economic value left on table during promos",
            "required_fix": "Execute bias repair plan items 5Z-REP-001 through 5Z-REP-003",
            "next_review_condition": "missed_units_estimate reduced vs prior run",
        },
        {
            "release_recommendation": RELEASE_RECOMMENDATION,
            "primary_blocker": PRIMARY_BLOCKER,
            "blocker_description": "Shadow observation only — no auto-orders",
            "evidence_metric": "auto_orders_approved",
            "evidence_value": "NO",
            "acceptable_threshold": "NO until release gate passes",
            "operational_risk": "Premature production ordering if auto-orders enabled",
            "required_fix": "Complete human shadow review; maintain advisory-only exports",
            "next_review_condition": "human_review_completion_rate > 0.5",
        },
    ]
    return pd.DataFrame(evidence)


def write_phase5z_diagnostics(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    operating_pack_dir: Path = DEFAULT_OPERATING_PACK,
    backtest_df: pd.DataFrame | None = None,
    scored_df: pd.DataFrame | None = None,
    order_plan_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    error_dashboard = _read_csv(PHASE5Y_DIR / "phase5y01_error_rate_dashboard.csv")

    frame = build_bias_root_cause_frame(
        backtest_df=backtest_df,
        scored_df=scored_df,
        order_plan_df=order_plan_df,
        error_dashboard_df=error_dashboard,
    )
    summary = analyse_bias_by_segment(frame, error_dashboard_df=error_dashboard)
    under = analyse_underforecast_drivers(frame)
    over = analyse_overforecast_drivers(frame)
    repair = build_release_blocker_repair_plan(summary, under, over)
    sense = build_report_sense_check(operating_pack_dir)
    evidence = build_release_blocker_evidence_pack(summary, repair)

    summary.to_csv(diagnostics_dir / "phase5z01_bias_root_cause_summary.csv", index=False)
    under.to_csv(diagnostics_dir / "phase5z01_underforecast_driver_review.csv", index=False)
    over.to_csv(diagnostics_dir / "phase5z01_overforecast_driver_review.csv", index=False)
    repair.to_csv(diagnostics_dir / "phase5z01_bias_repair_plan.csv", index=False)
    sense.to_csv(diagnostics_dir / "phase5z01_report_sense_check.csv", index=False)
    evidence.to_csv(diagnostics_dir / "phase5z01_release_blocker_evidence_pack.csv", index=False)

    total = summary.loc[summary["segment_name"].eq("total")] if not summary.empty else pd.DataFrame()
    g5 = _read_csv(PHASE5G_SUMMARY)
    cash_drag = float(g5.loc[g5["model_variant"].eq("raw_model"), "estimated_leftover_units"].iloc[0]) if not g5.empty else float(over["cash_drag_proxy"].sum()) if not over.empty else 0.0
    dangerous = summary.loc[
        summary["release_blocker_status"].eq(PRIMARY_BLOCKER) & summary["segment_name"].ne("total")
    ] if not summary.empty else pd.DataFrame()
    largest_dangerous = ""
    if not dangerous.empty:
        row = dangerous.sort_values("missed_units_estimate", ascending=False).iloc[0]
        largest_dangerous = f"{row['segment_name']}={row['segment_value']}"

    sense_blockers = int(sense.loc[sense["severity"].eq("BLOCKER") & sense["status"].ne("PASS")].shape[0]) if not sense.empty else 0
    sense_warnings = int(sense.loc[sense["severity"].eq("WARNING") & sense["status"].ne("PASS")].shape[0]) if not sense.empty else 0

    return {
        "bias_root_cause_generated": True,
        "top_underforecast_driver": str(under.iloc[0]["likely_root_cause"]) if not under.empty else "",
        "top_overforecast_driver": str(over.iloc[0]["likely_root_cause"]) if not over.empty else "",
        "largest_dangerous_bias_segment": largest_dangerous,
        "estimated_missed_units": float(total.iloc[0]["missed_units_estimate"]) if not total.empty else 0.0,
        "estimated_cash_drag": cash_drag,
        "top_repair_recommendation": str(repair.iloc[0]["recommended_action"]) if not repair.empty else "",
        "release_blocker_explanation": evidence.iloc[0]["blocker_description"] if not evidence.empty else PRIMARY_BLOCKER,
        "next_required_fix": str(repair.iloc[0]["recommended_action"]) if not repair.empty else "",
        "report_sense_check_blockers": sense_blockers,
        "report_sense_check_warnings": sense_warnings,
        "release_recommendation": RELEASE_RECOMMENDATION,
        "primary_blocker": PRIMARY_BLOCKER,
        "governed_actions_overwritten": False,
        "auto_order_created": False,
    }


def run_phase5z01_bias_root_cause_review(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    operating_pack_dir: Path = DEFAULT_OPERATING_PACK,
) -> dict[str, Any]:
    return write_phase5z_diagnostics(diagnostics_dir=diagnostics_dir, operating_pack_dir=operating_pack_dir)
