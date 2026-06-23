from __future__ import annotations

"""Phase 5O addendum — long-tail basket trust protection."""

from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_stock_outcome_optimisation import DEFAULT_UNIT_COST_PROXY

LONG_TAIL_DAILY_THRESHOLD = 0.07
MIN_OPEN_FOR_SALE = 2.0
MAX_LONG_TAIL_PROTECTION = 300.0
MAX_CONVEXITY_VALUE = 200.0
GP_MARGIN_PROXY = 0.35

BASKET_RATE_COLS = (
    "basket_3plus_attachment_rate",
    "basket_5plus_attachment_rate",
    "avg_basket_value_when_present",
    "avg_basket_gp_when_present",
    "sister_club_attachment_rate",
    "mission_basket_attachment_rate",
)


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _first_col(frame: pd.DataFrame, names: tuple[str, ...], default: float = np.nan) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(default, index=frame.index, dtype=float)


def _quality_col(frame: pd.DataFrame) -> str:
    return "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"


def _gp_unit(frame: pd.DataFrame) -> pd.Series:
    return _first_col(frame, ("promo_gm_unit",), default=DEFAULT_UNIT_COST_PROXY * GP_MARGIN_PROXY).fillna(
        DEFAULT_UNIT_COST_PROXY * GP_MARGIN_PROXY
    )


def _has_basket_evidence(frame: pd.DataFrame) -> pd.Series:
    flag = _first_col(frame, ("feature_basket_structure_evidence_available_flag",), default=np.nan)
    attach = _first_col(
        frame,
        ("feature_basket_attach_rate", "feature_probability_sku_in_multi_item_basket"),
        default=np.nan,
    )
    dependency = _first_col(frame, ("feature_basket_drag_along_dependency_score",), default=np.nan)
    return flag.eq(1) | attach.notna() | dependency.notna()


def _rate_or_unknown(frame: pd.DataFrame, values: pd.Series) -> pd.Series:
    """Label missing basket transaction evidence as UNKNOWN, not zero."""
    evidence = _has_basket_evidence(frame)
    labelled = np.where(
        ~evidence,
        "UNKNOWN",
        np.where(values.notna(), values.round(4), "UNKNOWN"),
    )
    return pd.Series(labelled, index=frame.index)


def build_long_tail_basket_trust_frame(df: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    """Add long-tail basket trust protection fields at promo SKU grain."""
    del config
    out = df.copy()
    quality = out.get(_quality_col(out), pd.Series("UNSAFE", index=out.index)).astype(str)
    unsafe = quality.eq("UNSAFE")
    avg_daily = _numeric(out, "average_daily_units")
    gp = _gp_unit(out)
    current = _numeric(out, "current_soh")
    expected_start = _numeric(out, "expected_soh_at_promo_start_before_order", _numeric(out, "current_soh"))
    evidence = _has_basket_evidence(out)

    attach_raw = _first_col(out, ("feature_basket_attach_rate", "feature_probability_sku_in_multi_item_basket"), default=np.nan)
    multi_raw = _first_col(
        out,
        ("feature_probability_sold_in_multi_item_basket_rate", "feature_probability_sku_in_multi_item_basket"),
        default=np.nan,
    )
    dependency_raw = _first_col(out, ("feature_basket_drag_along_dependency_score",), default=np.nan)
    convex_support_raw = _first_col(out, ("feature_basket_convexity_support_score",), default=np.nan)
    long_tail_dep = _first_col(out, ("feature_long_tail_dependency_flag",), default=0.0).fillna(0.0)

    out["basket_3plus_attachment_rate"] = _rate_or_unknown(out, attach_raw)
    out["basket_5plus_attachment_rate"] = _rate_or_unknown(out, multi_raw)
    out["avg_basket_value_when_present"] = _rate_or_unknown(
        out, _first_col(out, ("feature_avg_basket_value_when_present",), default=np.nan)
    )
    out["avg_basket_gp_when_present"] = _rate_or_unknown(
        out, _first_col(out, ("feature_avg_basket_gp_when_present",), default=np.nan)
    )
    out["sister_club_attachment_rate"] = _rate_or_unknown(
        out, _first_col(out, ("feature_sister_club_attachment_rate",), default=np.nan)
    )
    mission_raw = pd.concat([dependency_raw, convex_support_raw], axis=1).max(axis=1)
    out["mission_basket_attachment_rate"] = _rate_or_unknown(out, mission_raw)

    attach_num = pd.to_numeric(out["basket_3plus_attachment_rate"], errors="coerce").fillna(0.0)
    mission_num = pd.to_numeric(out["mission_basket_attachment_rate"], errors="coerce").fillna(0.0)
    dependency = dependency_raw.fillna(0.0)
    convex_support = convex_support_raw.fillna(0.0)
    basket_trust_risk = out.get("customer_basket_trust_regime", pd.Series("", index=out.index)).astype(str).eq("BASKET_TRUST_RISK")
    trust_risk_score = _numeric(out, "basket_trust_risk_score")
    structure_evidence = _first_col(out, ("feature_basket_structure_evidence_available_flag",), default=0.0).fillna(0.0).ge(1)
    out["basket_attachment_score"] = (
        attach_num * 50
        + mission_num * 30
        + long_tail_dep * 20
        + out.get("customer_basket_trust_regime", pd.Series("", index=out.index)).astype(str).eq("BASKET_TRUST_RISK").astype(float) * 10
    ).clip(0, 100).round(1)
    out["basket_mission_importance_score"] = (
        mission_num * 60 + dependency.fillna(0.0) * 40 + convex_support.fillna(0.0) * 20
    ).clip(0, 100).round(1)
    out["range_trust_importance_score"] = (
        out["basket_mission_importance_score"] * 0.6 + out["basket_attachment_score"] * 0.4
    ).clip(0, 100).round(1)

    intermittent = avg_daily.lt(LONG_TAIL_DAILY_THRESHOLD) | out.get("sku_demand_regime", pd.Series("", index=out.index)).astype(str).eq("INTERMITTENT_LOW_VOLUME")
    mission_signal = (
        attach_num.ge(0.15)
        | mission_num.ge(0.15)
        | long_tail_dep.gt(0)
        | out.get("mission_sku_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES")
        | dependency.ge(0.35)
        | (structure_evidence & basket_trust_risk & intermittent)
        | (structure_evidence & trust_risk_score.ge(25) & intermittent)
    )
    out["long_tail_sku_flag"] = np.where(intermittent & mission_signal, "YES", "NO")
    out["basket_completion_sku_flag"] = np.where(
        attach_num.ge(0.35)
        | mission_num.ge(0.35)
        | long_tail_dep.gt(0)
        | (structure_evidence & (basket_trust_risk | trust_risk_score.ge(35))),
        "YES",
        "NO",
    )

    below_min = (current.lt(MIN_OPEN_FOR_SALE)) | (expected_start.lt(MIN_OPEN_FOR_SALE))
    blocked = unsafe | out.get("constraint_block_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES")
    out["long_tail_minimum_soh_required"] = np.where(
        out["long_tail_sku_flag"].eq("YES") & ~blocked,
        MIN_OPEN_FOR_SALE,
        0.0,
    )
    out["long_tail_open_for_sale_required_flag"] = np.where(
        out["long_tail_sku_flag"].eq("YES") & below_min & ~blocked,
        "YES",
        "NO",
    )

    stockout_prob = (
        _numeric(out, "simulated_missed_demand_units").div(_numeric(out, "expected_promo_uplift_units").replace(0, np.nan)).fillna(0)
        .clip(0, 1)
        + _numeric(out, "stockout_suspected_flag").astype(float) * 0.5
    ).clip(0, 1)
    out["basket_loss_multiplier"] = (
        1.0
        + out["basket_mission_importance_score"].div(100).mul(1.5)
        + out["long_tail_sku_flag"].eq("YES").astype(float) * 0.5
    ).clip(1.0, 3.0).round(3)

    avg_basket_gp = pd.to_numeric(out["avg_basket_gp_when_present"], errors="coerce").fillna(gp * 3)
    out["long_tail_stockout_risk_score"] = (
        stockout_prob * 40
        + below_min.astype(float) * 30
        + out["long_tail_sku_flag"].eq("YES").astype(float) * 20
        + out["basket_mission_importance_score"] * 0.1
    ).clip(0, 100).round(1)

    out["basket_substitution_risk"] = np.where(
        out["basket_attachment_score"].ge(50) & below_min,
        "HIGH",
        np.where(out["basket_attachment_score"].ge(25), "MEDIUM", "LOW"),
    )
    out["basket_abandonment_risk_proxy"] = np.where(
        out["long_tail_stockout_risk_score"].ge(50),
        "HIGH",
        np.where(out["long_tail_stockout_risk_score"].ge(25), "MEDIUM", "LOW"),
    )

    out["long_tail_stockout_penalty"] = np.where(
        unsafe,
        0.0,
        (stockout_prob * out["basket_loss_multiplier"] * avg_basket_gp * out["basket_mission_importance_score"].div(100)).clip(0, MAX_LONG_TAIL_PROTECTION),
    ).round(3)
    out["basket_abandonment_penalty_proxy"] = (out["long_tail_stockout_penalty"] * 0.5).round(3)
    out["range_trust_damage_penalty"] = (out["long_tail_stockout_penalty"] * 0.35).round(3)
    out["long_tail_missed_sale_value_proxy"] = (
        _numeric(out, "missed_units_risk") * gp * out["basket_loss_multiplier"] * out["long_tail_sku_flag"].eq("YES").astype(float)
    ).clip(0, MAX_LONG_TAIL_PROTECTION).round(3)

    out["basket_trust_convexity_value"] = np.where(
        unsafe,
        0.0,
        (
            out["basket_mission_importance_score"] * avg_basket_gp * 0.05 * out["basket_loss_multiplier"]
            * out["long_tail_sku_flag"].eq("YES").astype(float)
        ).clip(0, MAX_CONVEXITY_VALUE),
    ).round(3)
    out["long_tail_protection_value"] = np.where(
        unsafe,
        0.0,
        (out["long_tail_stockout_penalty"] + out["long_tail_missed_sale_value_proxy"] + out["basket_trust_convexity_value"] * 0.5).clip(0, MAX_LONG_TAIL_PROTECTION),
    ).round(3)

    out["long_tail_basket_protection_reason"] = np.select(
        [
            unsafe,
            out["long_tail_open_for_sale_required_flag"].eq("YES"),
            out["long_tail_sku_flag"].eq("YES") & out["basket_completion_sku_flag"].eq("YES"),
            out["long_tail_sku_flag"].eq("YES"),
            ~evidence,
        ],
        [
            "unsafe_blocked_no_long_tail_auto_order",
            "verify_2_unit_minimum_soh_open_for_sale",
            "basket_completion_long_tail_protect",
            "long_tail_mission_relevance_review",
            "need_basket_attachment_evidence",
        ],
        default="standard_volume_protection",
    )

    numeric_cols = out.select_dtypes(include=[np.number]).columns
    out[numeric_cols] = out[numeric_cols].fillna(0.0)
    return out
