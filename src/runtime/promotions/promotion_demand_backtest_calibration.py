from __future__ import annotations

"""Commercial calibration layer for the completed-promotion demand backtest.

Turns the technically correct backtest output into a commercially decisive
calibration system. Adds:

- materiality columns per segment (units, exposure $, leftover $)
- commercial harm classification (over/under/balanced)
- calibration action recommendations + priority bands + reasons
- a materially-ranked watchlist (sorted by harm $, not just statistical breach)
- an overall commercial calibration summary JSON
- a plain-English commercial calibration brief markdown

This module is import-pure (no IO). The orchestrator owns IO and manifest.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

import numpy as np
import pandas as pd


# Materiality thresholds — easy to tune in one place.
MATERIAL_EXPOSURE_DOLLARS_BREACH = 5_000.0
MATERIAL_LEFTOVER_DOLLARS_BREACH = 1_000.0
HARM_BIAS_MARGIN = 0.20  # over- minus under- forecast rate margin to call a bias
DOMINANT_BIAS_MARGIN_OVERALL = 0.10

# Priority bands.
PRIORITY_P1 = "P1_URGENT"
PRIORITY_P2 = "P2_INVESTIGATE"
PRIORITY_P3 = "P3_MONITOR"
PRIORITY_P4 = "P4_KEEP_AS_IS"

# Harm classes.
HARM_OVERFORECAST_CASH_RISK = "OVERFORECAST_CASH_RISK"
HARM_UNDERFORECAST_AVAILABILITY_RISK = "UNDERFORECAST_AVAILABILITY_RISK"
HARM_BALANCED = "BALANCED"

# Calibration action classes.
ACTION_KEEP_AS_IS = "KEEP_AS_IS"
ACTION_ROUTE_TO_REVIEW = "ROUTE_TO_REVIEW"
ACTION_TIGHTEN_AUTO_PUBLISH_THRESHOLD = "TIGHTEN_AUTO_PUBLISH_THRESHOLD"
ACTION_SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER = "SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER"
ACTION_INVESTIGATE_PROMO_MEMORY_BIAS = "INVESTIGATE_PROMO_MEMORY_BIAS"
ACTION_INVESTIGATE_INTERMITTENT_DEMAND_BIAS = "INVESTIGATE_INTERMITTENT_DEMAND_BIAS"


def _safe_div(num: float, denom: float) -> float:
    if denom is None or denom == 0 or pd.isna(denom):
        return 0.0
    return float(num) / float(denom)


def compute_row_economics(enriched_frame: pd.DataFrame) -> pd.DataFrame:
    """Per-row commercial economics derived from the test-set predictions.

    Effective unit price comes from realised promo revenue divided by realised
    units (when both are present). When the row has zero realised units OR
    `actual_sales_ex_gst_promo` is missing, the effective unit price is null
    and downstream dollar columns become NaN — we never invent a price.

    Returns a frame indexed identically to `enriched_frame` with:
      effective_unit_price_dollars
      estimated_exposure_dollars       = predicted_units * unit_price
      estimated_leftover_cost_dollars  = max(predicted - actual, 0) * unit_price
      estimated_lost_sales_dollars     = max(actual - predicted, 0) * unit_price
    """
    predicted = pd.to_numeric(
        enriched_frame.get("predicted_units_total_promo", pd.Series(0.0, index=enriched_frame.index)),
        errors="coerce",
    ).fillna(0.0)
    actual = pd.to_numeric(
        enriched_frame.get("actual_units_sold_promo", pd.Series(0.0, index=enriched_frame.index)),
        errors="coerce",
    ).fillna(0.0)
    if "actual_sales_ex_gst_promo" in enriched_frame.columns:
        sales = pd.to_numeric(enriched_frame["actual_sales_ex_gst_promo"], errors="coerce")
        denom = actual.where(actual > 0)
        unit_price = (sales / denom).astype(float)
    else:
        unit_price = pd.Series(np.nan, index=enriched_frame.index)
    exposure = predicted * unit_price
    leftover = (predicted - actual).clip(lower=0.0) * unit_price
    lost_sales = (actual - predicted).clip(lower=0.0) * unit_price
    return pd.DataFrame(
        {
            "effective_unit_price_dollars": unit_price,
            "estimated_exposure_dollars": exposure,
            "estimated_leftover_cost_dollars": leftover,
            "estimated_lost_sales_dollars": lost_sales,
            "_predicted_units": predicted,
            "_actual_units": actual,
        },
        index=enriched_frame.index,
    )


def enrich_segment_table(
    *,
    segment_table: pd.DataFrame,
    backtest_rows: pd.DataFrame,
    enriched_frame: pd.DataFrame,
    segment_builders: list[tuple[str, object]],
    row_economics: pd.DataFrame,
) -> pd.DataFrame:
    """Add commercial materiality columns to the segment table.

    For each (segment_dimension, segment_value) row in `segment_table`, recompute
    the row mask via `segment_builders` and aggregate dollar/units totals.
    """
    if segment_table.empty:
        return segment_table.assign(
            total_predicted_units=pd.Series(dtype=float),
            total_actual_units=pd.Series(dtype=float),
            total_estimated_exposure_dollars=pd.Series(dtype=float),
            total_estimated_leftover_cost_dollars=pd.Series(dtype=float),
            total_estimated_lost_sales_dollars=pd.Series(dtype=float),
            total_recommended_order_units=pd.Series(dtype=float),
            total_capital_at_risk_adjusted_dollars=pd.Series(dtype=float),
        )

    builder_map = dict(segment_builders)
    enriched_indexed = enriched_frame.reset_index(drop=True)
    rows_indexed = backtest_rows.reset_index(drop=True)
    economics_indexed = row_economics.reset_index(drop=True)

    additions: list[dict[str, float]] = []
    for _, row in segment_table.iterrows():
        dimension = row["segment_dimension"]
        value = row["segment_value"]
        builder = builder_map.get(dimension)
        if builder is None:
            additions.append({})
            continue
        labels = builder(enriched_indexed)
        mask = labels.astype(str).values == str(value)
        if not mask.any():
            additions.append({})
            continue
        sub_rows = rows_indexed.loc[mask]
        sub_econ = economics_indexed.loc[mask]
        additions.append(
            {
                "total_predicted_units": float(sub_rows["predicted_units_total_promo"].sum()),
                "total_actual_units": float(sub_rows["actual_units_sold_promo"].sum()),
                "total_estimated_exposure_dollars": float(
                    sub_econ["estimated_exposure_dollars"].fillna(0.0).sum()
                ),
                "total_estimated_leftover_cost_dollars": float(
                    sub_econ["estimated_leftover_cost_dollars"].fillna(0.0).sum()
                ),
                "total_estimated_lost_sales_dollars": float(
                    sub_econ["estimated_lost_sales_dollars"].fillna(0.0).sum()
                ),
            }
        )

    enrichment = pd.DataFrame(additions, index=segment_table.index)
    out = pd.concat([segment_table.reset_index(drop=True), enrichment.reset_index(drop=True)], axis=1)
    # `total_recommended_order_units` and `total_capital_at_risk_adjusted_dollars`
    # are commercial-scoring outputs computed at Stage 11 for FUTURE promotions
    # only. They are not on the completed-promotion test-set parquet, so we
    # emit them as NaN per the user's "if available" clause and the brief
    # explicitly notes this.
    out["total_recommended_order_units"] = np.nan
    out["total_capital_at_risk_adjusted_dollars"] = np.nan
    # Round to 2dp for CSV readability.
    for column_name in (
        "total_predicted_units",
        "total_actual_units",
        "total_estimated_exposure_dollars",
        "total_estimated_leftover_cost_dollars",
        "total_estimated_lost_sales_dollars",
    ):
        if column_name in out.columns:
            out[column_name] = pd.to_numeric(out[column_name], errors="coerce").round(2)
    return out


def classify_segment_harm(segment_table_enriched: pd.DataFrame) -> pd.Series:
    """Per-segment commercial harm class.

    OVERFORECAST_CASH_RISK if overforecast bias AND material leftover dollars,
    UNDERFORECAST_AVAILABILITY_RISK if underforecast bias AND non-trivial
    actual demand, otherwise BALANCED.
    """
    if segment_table_enriched.empty:
        return pd.Series([], dtype=str)
    over = pd.to_numeric(segment_table_enriched["overforecast_rate"], errors="coerce").fillna(0.0)
    under = pd.to_numeric(segment_table_enriched["underforecast_rate"], errors="coerce").fillna(0.0)
    leftover = pd.to_numeric(
        segment_table_enriched.get(
            "total_estimated_leftover_cost_dollars",
            pd.Series(0.0, index=segment_table_enriched.index),
        ),
        errors="coerce",
    ).fillna(0.0)
    actual_units = pd.to_numeric(
        segment_table_enriched.get(
            "total_actual_units", pd.Series(0.0, index=segment_table_enriched.index)
        ),
        errors="coerce",
    ).fillna(0.0)

    over_bias = (over - under) >= HARM_BIAS_MARGIN
    under_bias = (under - over) >= HARM_BIAS_MARGIN
    cash_risk_material = leftover >= MATERIAL_LEFTOVER_DOLLARS_BREACH
    availability_risk_material = actual_units > 0

    classes: list[str] = []
    for is_over, is_under, cash_mat, avail_mat in zip(
        over_bias, under_bias, cash_risk_material, availability_risk_material
    ):
        if is_over and cash_mat:
            classes.append(HARM_OVERFORECAST_CASH_RISK)
        elif is_under and avail_mat:
            classes.append(HARM_UNDERFORECAST_AVAILABILITY_RISK)
        else:
            classes.append(HARM_BALANCED)
    return pd.Series(classes, index=segment_table_enriched.index, name="commercial_harm_class")


def assign_calibration_actions(segment_table_with_harm: pd.DataFrame) -> pd.DataFrame:
    """Add calibration_action_class, calibration_priority_band, calibration_reason_summary.

    Rules (transparent and explicit so an operator can audit them in the brief):

    P1_URGENT — material cash risk OR severe under-availability:
      - OVERFORECAST_CASH_RISK + leftover >= 2x material breach
        => SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER
      - UNDERFORECAST_AVAILABILITY_RISK + within_10pct < 0.20
        => ROUTE_TO_REVIEW

    P2_INVESTIGATE — feature-driven bias suggested:
      - intermittent_demand_flag=yes harming accuracy
        => INVESTIGATE_INTERMITTENT_DEMAND_BIAS
      - prior_promo_*_flag=yes harming accuracy
        => INVESTIGATE_PROMO_MEMORY_BIAS
      - any other harm class with material exposure
        => TIGHTEN_AUTO_PUBLISH_THRESHOLD

    P3_MONITOR — harm class non-balanced but immaterial dollars
        => ROUTE_TO_REVIEW

    P4_KEEP_AS_IS — BALANCED + within_10pct >= 0.50
        => KEEP_AS_IS
    """
    if segment_table_with_harm.empty:
        return segment_table_with_harm.assign(
            calibration_action_class=pd.Series(dtype=str),
            calibration_priority_band=pd.Series(dtype=str),
            calibration_reason_summary=pd.Series(dtype=str),
        )

    actions: list[str] = []
    priorities: list[str] = []
    reasons: list[str] = []

    for _, row in segment_table_with_harm.iterrows():
        harm = str(row.get("commercial_harm_class", HARM_BALANCED))
        leftover = float(row.get("total_estimated_leftover_cost_dollars", 0.0) or 0.0)
        exposure = float(row.get("total_estimated_exposure_dollars", 0.0) or 0.0)
        within_10 = float(row.get("within_10pct_rate", 0.0) or 0.0)
        comparable = int(row.get("comparable_rows", 0) or 0)
        dimension = str(row.get("segment_dimension", ""))
        value = str(row.get("segment_value", ""))

        chosen_action = ACTION_KEEP_AS_IS
        chosen_priority = PRIORITY_P4
        reason_parts: list[str] = []

        if harm == HARM_OVERFORECAST_CASH_RISK and leftover >= 2.0 * MATERIAL_LEFTOVER_DOLLARS_BREACH:
            chosen_action = ACTION_SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER
            chosen_priority = PRIORITY_P1
            reason_parts.append(
                f"overforecast bias with leftover-cost ${leftover:,.0f} above 2x materiality"
            )
        elif harm == HARM_UNDERFORECAST_AVAILABILITY_RISK and within_10 < 0.20 and comparable >= 20:
            chosen_action = ACTION_ROUTE_TO_REVIEW
            chosen_priority = PRIORITY_P1
            reason_parts.append(
                f"underforecast bias and only {within_10 * 100:.0f}% of rows within 10% of actual"
            )
        elif dimension == "intermittent_demand_flag" and value == "yes" and harm != HARM_BALANCED:
            chosen_action = ACTION_INVESTIGATE_INTERMITTENT_DEMAND_BIAS
            chosen_priority = PRIORITY_P2
            reason_parts.append(
                "intermittent-demand SKUs are showing systematic bias — review the intermittent-demand features"
            )
        elif (
            dimension.startswith("prior_promo_") or dimension == "prior_same_or_better_discount_56d_flag"
        ) and value == "yes" and harm != HARM_BALANCED:
            chosen_action = ACTION_INVESTIGATE_PROMO_MEMORY_BIAS
            chosen_priority = PRIORITY_P2
            reason_parts.append(
                "promo-memory features are correlated with bias on this segment — review the prior-promo memory weights"
            )
        elif harm != HARM_BALANCED and exposure >= MATERIAL_EXPOSURE_DOLLARS_BREACH:
            chosen_action = ACTION_TIGHTEN_AUTO_PUBLISH_THRESHOLD
            chosen_priority = PRIORITY_P2
            reason_parts.append(
                f"non-balanced bias with material exposure ${exposure:,.0f}"
            )
        elif harm != HARM_BALANCED:
            chosen_action = ACTION_ROUTE_TO_REVIEW
            chosen_priority = PRIORITY_P3
            reason_parts.append(
                "non-balanced bias but exposure dollars are below materiality — monitor"
            )
        elif within_10 >= 0.50:
            chosen_action = ACTION_KEEP_AS_IS
            chosen_priority = PRIORITY_P4
            reason_parts.append(
                f"balanced bias and {within_10 * 100:.0f}% of rows within 10% of actual"
            )
        else:
            chosen_action = ACTION_ROUTE_TO_REVIEW
            chosen_priority = PRIORITY_P3
            reason_parts.append("balanced bias but accuracy below 50% within-10% — review")

        actions.append(chosen_action)
        priorities.append(chosen_priority)
        reasons.append("; ".join(reason_parts))

    out = segment_table_with_harm.copy()
    out["calibration_action_class"] = actions
    out["calibration_priority_band"] = priorities
    out["calibration_reason_summary"] = reasons
    return out


_PRIORITY_RANK = {
    PRIORITY_P1: 0,
    PRIORITY_P2: 1,
    PRIORITY_P3: 2,
    PRIORITY_P4: 3,
}


def materially_rank_watchlist(watchlist_enriched: pd.DataFrame) -> pd.DataFrame:
    """Sort watchlist by commercial materiality, not just statistical breach.

    Sort keys (in order):
      calibration_priority_band   asc (P1 first)
      total_estimated_leftover_cost_dollars  desc
      overforecast_rate           desc
      within_10pct_rate           asc
      comparable_rows             desc
    """
    if watchlist_enriched.empty:
        return watchlist_enriched
    out = watchlist_enriched.copy()
    out["_priority_rank"] = out["calibration_priority_band"].map(_PRIORITY_RANK).fillna(99)
    out = out.sort_values(
        by=[
            "_priority_rank",
            "total_estimated_leftover_cost_dollars",
            "overforecast_rate",
            "within_10pct_rate",
            "comparable_rows",
        ],
        ascending=[True, False, False, True, False],
    ).drop(columns=["_priority_rank"]).reset_index(drop=True)
    return out


def compute_commercial_calibration_summary(
    *,
    segment_table_enriched: pd.DataFrame,
    backtest_summary: dict[str, object],
    row_economics: pd.DataFrame,
) -> dict[str, object]:
    """Top-level commercial summary JSON payload."""
    overall_within_10 = float(backtest_summary.get("within_10pct_rate", 0.0) or 0.0)
    overall_within_20 = float(backtest_summary.get("within_20pct_rate", 0.0) or 0.0)
    total_comparable = int(backtest_summary.get("comparable_rows", 0) or 0)
    total_material_exposure = float(
        pd.to_numeric(row_economics["estimated_exposure_dollars"], errors="coerce")
        .fillna(0.0)
        .sum()
    )
    total_leftover = float(
        pd.to_numeric(row_economics["estimated_leftover_cost_dollars"], errors="coerce")
        .fillna(0.0)
        .sum()
    )
    total_lost_sales = float(
        pd.to_numeric(row_economics["estimated_lost_sales_dollars"], errors="coerce")
        .fillna(0.0)
        .sum()
    )

    over_rate = float(backtest_summary.get("overforecast_rate", 0.0) or 0.0)
    under_rate = float(backtest_summary.get("underforecast_rate", 0.0) or 0.0)
    if over_rate - under_rate >= DOMINANT_BIAS_MARGIN_OVERALL:
        dominant_bias = "OVERFORECASTING"
    elif under_rate - over_rate >= DOMINANT_BIAS_MARGIN_OVERALL:
        dominant_bias = "UNDERFORECASTING"
    else:
        dominant_bias = "NO_DOMINANT_BIAS"

    highest_risk_segment: dict[str, object] | None = None
    highest_opportunity_segment: dict[str, object] | None = None
    review_count = 0
    threshold_change_recommended = False

    if not segment_table_enriched.empty and "calibration_action_class" in segment_table_enriched.columns:
        review_count = int(
            (segment_table_enriched["calibration_action_class"].isin(
                {ACTION_ROUTE_TO_REVIEW, ACTION_INVESTIGATE_PROMO_MEMORY_BIAS,
                 ACTION_INVESTIGATE_INTERMITTENT_DEMAND_BIAS,
                 ACTION_SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER}
            )).sum()
        )
        threshold_change_recommended = bool(
            (segment_table_enriched["calibration_action_class"] == ACTION_TIGHTEN_AUTO_PUBLISH_THRESHOLD).any()
            or (segment_table_enriched["calibration_action_class"] == ACTION_SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER).any()
        )
        risk_candidates = segment_table_enriched[
            segment_table_enriched["commercial_harm_class"] != HARM_BALANCED
        ]
        if not risk_candidates.empty:
            top_risk = risk_candidates.sort_values(
                ["total_estimated_leftover_cost_dollars", "total_estimated_lost_sales_dollars"],
                ascending=[False, False],
            ).iloc[0]
            highest_risk_segment = {
                "segment_dimension": str(top_risk["segment_dimension"]),
                "segment_value": str(top_risk["segment_value"]),
                "comparable_rows": int(top_risk["comparable_rows"]),
                "commercial_harm_class": str(top_risk["commercial_harm_class"]),
                "total_estimated_leftover_cost_dollars": float(top_risk["total_estimated_leftover_cost_dollars"]),
                "total_estimated_lost_sales_dollars": float(top_risk["total_estimated_lost_sales_dollars"]),
                "calibration_action_class": str(top_risk["calibration_action_class"]),
                "calibration_priority_band": str(top_risk["calibration_priority_band"]),
            }
        opportunity_candidates = segment_table_enriched[
            (segment_table_enriched["commercial_harm_class"] == HARM_BALANCED)
            & (segment_table_enriched["comparable_rows"] >= 20)
        ]
        if not opportunity_candidates.empty:
            top_opp = opportunity_candidates.sort_values(
                ["within_10pct_rate", "total_estimated_exposure_dollars"],
                ascending=[False, False],
            ).iloc[0]
            highest_opportunity_segment = {
                "segment_dimension": str(top_opp["segment_dimension"]),
                "segment_value": str(top_opp["segment_value"]),
                "comparable_rows": int(top_opp["comparable_rows"]),
                "within_10pct_rate": float(top_opp["within_10pct_rate"]),
                "total_estimated_exposure_dollars": float(top_opp["total_estimated_exposure_dollars"]),
                "calibration_action_class": str(top_opp["calibration_action_class"]),
            }

    return {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "overall_within_10pct_rate": round(overall_within_10, 4),
        "overall_within_20pct_rate": round(overall_within_20, 4),
        "total_comparable_rows": total_comparable,
        "total_material_exposure_dollars": round(total_material_exposure, 2),
        "total_estimated_leftover_cost_dollars": round(total_leftover, 2),
        "total_estimated_lost_sales_dollars": round(total_lost_sales, 2),
        "dominant_bias_class": dominant_bias,
        "highest_risk_segment": highest_risk_segment,
        "highest_opportunity_segment": highest_opportunity_segment,
        "review_recommended_segment_count": int(review_count),
        "threshold_change_recommended_flag": bool(threshold_change_recommended),
        "materiality_thresholds": {
            "exposure_dollars_breach": MATERIAL_EXPOSURE_DOLLARS_BREACH,
            "leftover_dollars_breach": MATERIAL_LEFTOVER_DOLLARS_BREACH,
            "harm_bias_margin": HARM_BIAS_MARGIN,
            "dominant_bias_margin_overall": DOMINANT_BIAS_MARGIN_OVERALL,
        },
    }


def compose_segment_explanation(row: pd.Series, *, kind: str) -> str:
    """Plain-English commercial sentence for a single segment row.

    `kind` is "bad" or "good". Language is intentionally direct — no hedging,
    no AI filler. Operator-facing.
    """
    dimension = str(row.get("segment_dimension", "segment"))
    value = str(row.get("segment_value", ""))
    comparable = int(row.get("comparable_rows", 0) or 0)
    within_10 = float(row.get("within_10pct_rate", 0.0) or 0.0) * 100.0
    mape = float(row.get("mean_absolute_percentage_error", 0.0) or 0.0)
    over = float(row.get("overforecast_rate", 0.0) or 0.0) * 100.0
    under = float(row.get("underforecast_rate", 0.0) or 0.0) * 100.0
    leftover = float(row.get("total_estimated_leftover_cost_dollars", 0.0) or 0.0)
    lost_sales = float(row.get("total_estimated_lost_sales_dollars", 0.0) or 0.0)
    action = str(row.get("calibration_action_class", ""))
    if kind == "bad":
        if leftover >= MATERIAL_LEFTOVER_DOLLARS_BREACH and over >= under:
            return (
                f"{dimension}={value} ({comparable} promos) is overforecasting on {over:.0f}% of rows "
                f"and is on track to leave roughly ${leftover:,.0f} of stock unsold. "
                f"Recommended action: {action}."
            )
        if lost_sales >= MATERIAL_LEFTOVER_DOLLARS_BREACH and under > over:
            return (
                f"{dimension}={value} ({comparable} promos) is underforecasting on {under:.0f}% of rows "
                f"and is missing roughly ${lost_sales:,.0f} of demand. "
                f"Recommended action: {action}."
            )
        return (
            f"{dimension}={value} ({comparable} promos): only {within_10:.0f}% of forecasts land within 10% "
            f"of actual and average error is {mape:.0f}%. Recommended action: {action}."
        )
    # good
    return (
        f"{dimension}={value} ({comparable} promos) is the model's strongest segment — "
        f"{within_10:.0f}% of forecasts land within 10% of actual at average error {mape:.0f}%. "
        f"Keep current settings."
    )


def compose_commercial_calibration_brief(
    *,
    summary: dict[str, object],
    segment_table_enriched: pd.DataFrame,
    watchlist_ranked: pd.DataFrame,
    run_id: str,
    as_of_date: str | None,
    skip_reason: str | None,
    skip_class: str | None,
) -> str:
    """Operator-facing commercial calibration brief markdown."""
    lines: list[str] = []
    lines.append(f"# Promotion demand calibration brief — run {run_id}")
    if as_of_date:
        lines.append(f"As-of date: {as_of_date}")
    lines.append("")

    if skip_reason:
        lines.append(f"**Calibration brief skipped:** {skip_class} — {skip_reason}")
        lines.append("")
        lines.append("There is no commercial calibration evidence for this run.")
        return "\n".join(lines) + "\n"

    # Q1: are we mostly overforecasting or underforecasting?
    bias = str(summary.get("dominant_bias_class", "NO_DOMINANT_BIAS"))
    lines.append("## Are we mostly overforecasting or underforecasting?")
    if bias == "OVERFORECASTING":
        lines.append(
            f"The model is **overforecasting** this period. "
            f"Estimated leftover-cost exposure is "
            f"**${float(summary.get('total_estimated_leftover_cost_dollars', 0.0)):,.0f}**."
        )
    elif bias == "UNDERFORECASTING":
        lines.append(
            f"The model is **underforecasting** this period. "
            f"Estimated lost-sales exposure is "
            f"**${float(summary.get('total_estimated_lost_sales_dollars', 0.0)):,.0f}**."
        )
    else:
        lines.append(
            "Bias is balanced overall. Over- and under-forecasting offset within the "
            f"{DOMINANT_BIAS_MARGIN_OVERALL * 100:.0f}-point margin we treat as noise."
        )
    lines.append("")

    # Q2 / Q3: cash-risk vs availability-risk environments.
    cash_risk = segment_table_enriched[
        segment_table_enriched.get("commercial_harm_class") == HARM_OVERFORECAST_CASH_RISK
    ] if not segment_table_enriched.empty else pd.DataFrame()
    avail_risk = segment_table_enriched[
        segment_table_enriched.get("commercial_harm_class") == HARM_UNDERFORECAST_AVAILABILITY_RISK
    ] if not segment_table_enriched.empty else pd.DataFrame()

    lines.append("## Which environments are hurting cash?")
    if cash_risk.empty:
        lines.append("No segment is currently flagged as overforecast cash risk.")
    else:
        cash_top = cash_risk.sort_values(
            "total_estimated_leftover_cost_dollars", ascending=False
        ).head(5)
        for _, row in cash_top.iterrows():
            lines.append("- " + compose_segment_explanation(row, kind="bad"))
    lines.append("")

    lines.append("## Which environments are hurting availability?")
    if avail_risk.empty:
        lines.append("No segment is currently flagged as underforecast availability risk.")
    else:
        avail_top = avail_risk.sort_values(
            "total_estimated_lost_sales_dollars", ascending=False
        ).head(5)
        for _, row in avail_top.iterrows():
            lines.append("- " + compose_segment_explanation(row, kind="bad"))
    lines.append("")

    # Q4: closest to the 10% goal.
    lines.append("## Where are we closest to the 10% goal?")
    opp = summary.get("highest_opportunity_segment")
    if isinstance(opp, dict) and opp:
        lines.append(
            f"`{opp['segment_dimension']}={opp['segment_value']}` — "
            f"{float(opp['within_10pct_rate']) * 100:.0f}% within-10% on {int(opp['comparable_rows'])} promos. "
            f"Carrying ${float(opp['total_estimated_exposure_dollars']):,.0f} of exposure dollars."
        )
        # Top 3 opportunity segments overall.
        if not segment_table_enriched.empty:
            opp_pool = segment_table_enriched[
                (segment_table_enriched["commercial_harm_class"] == HARM_BALANCED)
                & (segment_table_enriched["comparable_rows"] >= 20)
            ]
            if not opp_pool.empty:
                lines.append("")
                lines.append("Other strong segments:")
                for _, row in opp_pool.sort_values("within_10pct_rate", ascending=False).head(3).iterrows():
                    lines.append("- " + compose_segment_explanation(row, kind="good"))
    else:
        lines.append("No segment with sufficient row count meets the strong-accuracy bar yet.")
    lines.append("")

    # Q5: what should the operator change first?
    lines.append("## What should the operator change first?")
    if watchlist_ranked.empty:
        lines.append("No calibration changes are recommended this run. Keep current settings.")
    else:
        top_actions = watchlist_ranked.head(5)
        for _, row in top_actions.iterrows():
            lines.append(
                f"- **{row['calibration_priority_band']}** — `{row['segment_dimension']}={row['segment_value']}` "
                f"({int(row['comparable_rows'])} promos): {row['calibration_action_class']}. "
                f"Reason: {row['calibration_reason_summary']}."
            )
    lines.append("")

    # Materiality thresholds for transparency.
    thresholds = summary.get("materiality_thresholds", {})
    if isinstance(thresholds, dict):
        lines.append("## Materiality thresholds in force")
        lines.append(
            f"- Material exposure: ${float(thresholds.get('exposure_dollars_breach', 0.0)):,.0f}"
        )
        lines.append(
            f"- Material leftover cost: ${float(thresholds.get('leftover_dollars_breach', 0.0)):,.0f}"
        )
        lines.append(
            f"- Harm bias margin: {float(thresholds.get('harm_bias_margin', 0.0)):.2f}"
        )
        lines.append(
            f"- Overall dominant-bias margin: {float(thresholds.get('dominant_bias_margin_overall', 0.0)):.2f}"
        )
    lines.append("")
    lines.append(
        "Note: `total_recommended_order_units` and `total_capital_at_risk_adjusted_dollars` "
        "are commercial-scoring outputs computed at Stage 11 for future promotions. They are "
        "not produced for completed promotions in this pipeline, so the corresponding columns "
        "in the by-segment CSV are left null."
    )
    return "\n".join(lines) + "\n"
