from __future__ import annotations

"""Phase 6E — available-to-sell evidence strengthening from existing raw/derived data."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6e01_feature_merge_calibration_ats")


def _numeric(series: pd.Series | Any, default: float = 0.0) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series([pd.to_numeric(series, errors="coerce")]).fillna(default)
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _col(frame: pd.DataFrame, col: str, default: str = "UNKNOWN") -> pd.Series:
    return frame.get(col, pd.Series(default, index=frame.index)).astype(str)


def build_available_to_sell_evidence_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Assemble ATS evidence inputs from existing columns only."""
    out = frame.copy()
    evidence_sources: list[pd.Series] = []
    for col in (
        "current_soh", "expected_soh_at_promo_start_before_order", "promo_start_soh_resolved",
        "supplier_replenishment_regime", "supplier_risk_cost", "supplier_economic_risk_cost",
        "promo_start_soh_source_quality", "stockout_suspected_flag", "actual_units_sold_promo",
        "feature_basket_3plus_attach_rate", "mission_sku_score", "weak_history_flag", "new_line_flag",
        "available_to_sell_confidence_score", "ats_stockout_censoring_risk",
    ):
        if col in out.columns:
            present = out[col].notna() & out[col].astype(str).ne("UNKNOWN")
            evidence_sources.append(present.astype(int))
    out["ats_evidence_source_count"] = sum(evidence_sources) if evidence_sources else 0
    return out


def detect_censored_zero_demand_risk(frame: pd.DataFrame) -> pd.DataFrame:
    """Label zero-sales learnability and censoring risk."""
    out = frame.copy()
    actual = _numeric(out.get("actual_units_sold_promo", 0))
    soh = _numeric(out.get("current_soh", out.get("expected_soh_at_promo_start_before_order", 0)))
    stockout = _numeric(out.get("stockout_suspected_flag", 0)).astype(int)
    ats_censor = _col(out, "ats_stockout_censoring_risk").eq("YES")
    quality = _col(out, "promo_start_soh_source_quality")
    weak = _col(out, "weak_history_flag").eq("YES") | _col(out, "new_line_flag").eq("YES")

    censored = (actual.le(0.01) & ((soh.gt(0) & stockout.eq(1)) | ats_censor | quality.eq("UNKNOWN")))
    out["ats_censoring_risk_reason"] = np.where(
        stockout.eq(1), "STOCKOUT_SUSPECTED",
        np.where(quality.eq("UNKNOWN"), "SOH_QUALITY_UNKNOWN",
        np.where(ats_censor, "ATS_STOCKOUT_CENSORING", "")),
    )
    learnable = actual.gt(0) | ((actual.le(0.01) & soh.le(0)) & ~censored)
    out["ats_zero_sales_learnable_flag"] = learnable.map({True: "YES", False: "NO"})
    out["ats_zero_sales_not_learnable_reason"] = np.where(
        ~learnable & censored, "CENSORED_OR_STOCKOUT",
        np.where(~learnable & weak, "WEAK_HISTORY_NEW_LINE", ""),
    )
    return out


def strengthen_ats_confidence(frame: pd.DataFrame) -> pd.DataFrame:
    """Strengthen ATS confidence using multi-source evidence."""
    out = detect_censored_zero_demand_risk(build_available_to_sell_evidence_frame(frame))
    n = len(out)
    soh = _numeric(out.get("current_soh", 0)).values
    expected = _numeric(out.get("expected_soh_at_promo_start_before_order", 0)).values
    stockout = _numeric(out.get("stockout_suspected_flag", 0)).astype(int).values
    quality = _col(out, "promo_start_soh_source_quality").values
    actual = _numeric(out.get("actual_units_sold_promo", 0)).values
    base = _numeric(out.get("available_to_sell_confidence_score", 0.5)).values
    basket = _numeric(out.get("feature_basket_3plus_attach_rate", 0)).values
    mission = _numeric(out.get("mission_sku_score", 0)).values
    src_count = _numeric(out.get("ats_evidence_source_count", 0)).values

    score = np.clip(base, 0, 1)
    score += np.where(soh > 0, 0.1, -0.15)
    score += np.where(expected > 0, 0.05, -0.05)
    score += np.where(stockout == 0, 0.1, -0.2)
    score += np.where(np.isin(quality, ["HIGH", "MEDIUM"]), 0.05, -0.1)
    score += np.where((actual > 0) & (soh > 0), 0.08, 0)
    score += np.clip(basket * 0.1, 0, 0.1)
    score += np.clip(mission / 500.0, 0, 0.08)
    score += np.clip(src_count / 20.0, 0, 0.1)
    score = np.clip(score, 0, 1)

    out["ats_evidence_score"] = np.round(score, 4)
    out["ats_evidence_label"] = np.where(
        score >= 0.7, "STRONG",
        np.where(score >= 0.45, "MODERATE", "WEAK"),
    )
    out["ats_calibration_eligibility_support_flag"] = np.where(
        (score >= 0.45)
        & (stockout == 0)
        & ~np.isin(quality, ["UNKNOWN", "UNSAFE"])
        & out["ats_zero_sales_learnable_flag"].astype(str).ne("NO"),
        "YES", "NO",
    )
    return out


def summarize_ats_evidence(frame: pd.DataFrame) -> pd.DataFrame:
    """Row-level and aggregate ATS evidence metrics."""
    strengthened = strengthen_ats_confidence(frame)
    rows = [{
        "metric": "rows_with_strong_ats_evidence",
        "value": int(strengthened["ats_evidence_label"].eq("STRONG").sum()),
    }, {
        "metric": "rows_with_weak_ats_evidence",
        "value": int(strengthened["ats_evidence_label"].eq("WEAK").sum()),
    }, {
        "metric": "rows_zero_sales_learnable",
        "value": int(strengthened["ats_zero_sales_learnable_flag"].eq("YES").sum()),
    }, {
        "metric": "rows_zero_sales_not_learnable",
        "value": int(strengthened["ats_zero_sales_learnable_flag"].eq("NO").sum()),
    }, {
        "metric": "stockout_censored_rows",
        "value": int(strengthened["ats_censoring_risk_reason"].astype(str).str.len().gt(0).sum()),
    }, {
        "metric": "ats_supported_calibration_rows",
        "value": int(strengthened["ats_calibration_eligibility_support_flag"].eq("YES").sum()),
    }, {
        "metric": "false_zero_risk_rows",
        "value": int(strengthened.get("ats_false_zero_demand_risk", pd.Series("NO")).astype(str).eq("YES").sum()),
    }, {
        "metric": "top_ats_blocker",
        "value": str(
            strengthened.loc[strengthened["ats_evidence_label"].eq("WEAK"), "ats_censoring_risk_reason"]
            .replace("", np.nan).dropna().mode().iloc[0]
            if strengthened["ats_evidence_label"].eq("WEAK").any()
            else "NONE"
        ),
    }]
    summary = pd.DataFrame(rows)
    summary.attrs["strengthened_frame"] = strengthened
    return summary


def write_phase6e_ats_diagnostics(
    frame: pd.DataFrame,
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_ats_evidence(frame)
    strengthened = summary.attrs["strengthened_frame"]
    cols = [c for c in strengthened.columns if c.startswith("ats_") or c == "available_to_sell_confidence_score"]
    key = [c for c in ("store_number", "promotion_id", "sku_number") if c in strengthened.columns]
    strengthened[key + cols].head(2000).to_csv(diagnostics_dir / "phase6e01_ats_evidence_strengthening.csv", index=False)
    summary.to_csv(diagnostics_dir / "phase6e01_ats_evidence_summary.csv", index=False)

    return {
        "ats_strong_evidence_rows": int(strengthened["ats_evidence_label"].eq("STRONG").sum()),
        "ats_weak_evidence_rows": int(strengthened["ats_evidence_label"].eq("WEAK").sum()),
        "ats_supported_calibration_rows": int(strengthened["ats_calibration_eligibility_support_flag"].eq("YES").sum()),
        "strengthened_frame": strengthened,
        "summary_df": summary,
    }
