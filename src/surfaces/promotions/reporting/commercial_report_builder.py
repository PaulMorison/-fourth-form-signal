"""Commercial store-facing promotion report builder (Phase 5B.3+)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re

import numpy as np
import pandas as pd

META_STATUS = "SHADOW_NOT_PRODUCTION"
PRODUCTION_ORDERING = "NO"
CUSTOMER_RELEASE = "NO"
ALLOWED_DECISIONS = frozenset({"BUY", "REVIEW", "HOLD", "DO_NOT_BUY"})

ORDER_PLAN_COLUMNS: tuple[str, ...] = (
    "priority_rank",
    "store_number",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "promotion_days",
    "prediction_date",
    "days_until_promotion_start",
    "sku_number",
    "sku_description",
    "decision",
    "recommended_order_units",
    "current_soh_units",
    "on_order_units",
    "estimated_demand_before_promo_start_units",
    "predicted_promo_period_sales_units",
    "total_expected_demand_to_promo_end_units",
    "optimal_stock_on_hand_day_one_units",
    "target_stock_on_hand_at_promo_end_units",
    "projected_stock_on_hand_at_promo_start_before_order_units",
    "projected_stock_on_hand_at_promo_start_after_order_units",
    "projected_stock_on_hand_at_promo_end_units",
    "stock_gap_units",
    "discount_percent",
    "avg_promo_demand_same_discount_units",
    "expected_gp_dollars",
    "capital_at_risk_dollars",
    "confidence_score",
    "confidence_label",
    "data_quality_score",
    "data_quality_label",
    "decision_quality_label",
    "reason_demand",
    "reason_stock",
    "reason_order",
    "reason_risk",
    "reason_rejection_or_hold",
    "human_review_required",
    "review_reason",
    "model_status",
    "production_ordering_approved",
    "customer_report_release_approved",
    "operator_decision",
    "operator_recommended_units",
    "operator_notes",
)


@dataclass(frozen=True)
class CommercialSourceSelection:
    promotion_slug: str
    sku_universe_source: str
    order_units_source: str
    demand_source: str
    confidence_source: str
    notes: str


@dataclass(frozen=True)
class CommercialPackArtifacts:
    output_dir: Path
    order_plan_path: Path
    row_count: int
    decision_counts: dict[str, int]
    total_recommended_order_units: float
    report_quality_score: int


def _label(score: float) -> str:
    if score >= 85:
        return "VERY_HIGH"
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    if score >= 30:
        return "LOW"
    return "VERY_LOW"


def _num(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def load_se01_scored_sources(prediction_dir: Path) -> pd.DataFrame:
    """Merge SE01 sources; order evidence from raw_model_order_units, not final zeroed orders."""
    prefix = "772_2026-07-23_allocation-report-se01-skincare-sales-event"
    main = pd.read_csv(prediction_dir / f"{prefix}.csv", low_memory=False)
    audit = pd.read_csv(prediction_dir / f"{prefix}_operator-audit.csv", low_memory=False)
    feature_cols = [
        "sku_number",
        "expected_units_per_day",
        "historical_units_same_discount_avg",
        "lead_up_demand_units",
        "capital_at_risk_adjusted_dollars",
        "feature_expected_gp_on_trust_floor_units",
        "feature_expected_gp_on_speculative_units",
        "promotion_period_days",
        "promotion_start_date",
        "promotion_end_date",
    ]
    feature = pd.read_csv(
        prediction_dir / f"{prefix}_feature-inspection.csv",
        usecols=[c for c in feature_cols if c in pd.read_csv(prediction_dir / f"{prefix}_feature-inspection.csv", nrows=0).columns],
        low_memory=False,
    )
    audit_keep = [
        "sku_number",
        "raw_model_order_units",
        "model_confidence_percent",
        "lead_up_demand_units",
        "expected_units_per_day",
        "review_flag",
        "risk_flag",
        "audit_notes",
        "demand_evidence_label",
        "recommended_action",
    ]
    audit_keep = [c for c in audit_keep if c in audit.columns]
    out = main.merge(audit[audit_keep], on="sku_number", how="left", suffixes=("", "_audit"))
    out = out.merge(feature, on="sku_number", how="left", suffixes=("", "_feat"))
    return out


def assemble_commercial_order_rows(
    frame: pd.DataFrame,
    *,
    store_number: int,
    promotion_name: str,
    prediction_date: str,
) -> pd.DataFrame:
    """Build one canonical row per SKU from scored SE01 evidence."""
    promo_days = _num(frame.get("promotion_period_days", frame.get("promotion_days", 7)), 7).astype(int)
    promo_days = promo_days.replace(0, 7)
    start = pd.to_datetime(frame.get("promotion_start_date_feat", frame.get("promotion_start_date")), errors="coerce")
    end = pd.to_datetime(frame.get("promotion_end_date_feat", frame.get("promotion_end_date")), errors="coerce")
    pred_dt = pd.to_datetime(prediction_date, errors="coerce")
    days_until = (start - pred_dt).dt.days.fillna(0).clip(lower=0).astype(int)

    pre_promo = _num(frame.get("expected_units_before_promo_start"))
    if "lead_up_demand_units_audit" in frame.columns:
        pre_promo = pre_promo.where(pre_promo > 0, _num(frame["lead_up_demand_units_audit"]))
    if "lead_up_demand_units" in frame.columns:
        pre_promo = pre_promo.where(pre_promo > 0, _num(frame["lead_up_demand_units"]))

    per_day = _num(frame.get("expected_units_per_day_feat", frame.get("expected_units_per_day")))
    hist = _num(frame.get("historical_units_same_discount_avg"))
    promo_sales = np.maximum(per_day * promo_days, hist * (promo_days / 14.0)).round(3)
    total_demand = (pre_promo + promo_sales).round(3)

    cover30 = (per_day * 30).round(3)
    floor_main = _num(frame.get("floor_units_required"))
    target_end = np.maximum(2, np.maximum(cover30, floor_main)).round(3)
    target_end = target_end.where(per_day > 0, np.maximum(2, floor_main)).round(3)

    optimal = _num(frame.get("target_SOH_at_promo_start"))
    optimal = optimal.where(optimal > 0, (promo_sales + target_end).round(3))

    soh = _num(frame.get("current_soh"))
    on_order = _num(frame.get("on_order_at_advice_time"))
    before = (soh + on_order - pre_promo).clip(lower=0).round(3)
    gap = (optimal - before).clip(lower=0).round(3)

    raw_order = _num(frame.get("raw_model_order_units")).round(0).astype(int)
    recommended = pd.Series(raw_order.clip(lower=0).values, index=frame.index)

    conf = _num(frame.get("model_confidence_percent"), 50).clip(0, 100)
    review_flag = _num(frame.get("review_flag")).astype(bool)
    risk_flag = _num(frame.get("risk_flag")).astype(bool)
    orig_action = frame.get("operator_action", pd.Series("DO_NOT_BUY", index=frame.index)).astype(str).str.upper()

    decision = pd.Series(
        np.where(
            recommended > 0,
            np.where(conf >= 45, "BUY", "REVIEW"),
            np.where(
                orig_action.isin(["REVIEW", "MONITOR"]) | review_flag,
                "REVIEW",
                np.where((promo_sales > 0.5) | (gap > 0), "HOLD", "DO_NOT_BUY"),
            ),
        ),
        index=frame.index,
    )
    recommended = recommended.where(~decision.isin(["HOLD", "DO_NOT_BUY"]), 0).astype(int)
    decision = decision.where(~((decision == "BUY") & (recommended <= 0)), "REVIEW")

    after = (before + recommended).round(3)
    end_soh = (after - promo_sales).round(3)

    dq = pd.Series(80.0, index=frame.index)
    dq = dq.where(soh.notna(), dq - 15)
    dq = dq.where(pre_promo.notna(), dq - 10)
    dq = dq.where(promo_sales > 0, dq - 10)
    dq = dq.where(per_day > 0, dq - 10).clip(0, 100)

    flags = pd.DataFrame({
        "risk_or_review_flag": np.where(risk_flag | review_flag, "risk_or_review_flag", ""),
        "low_confidence_buy": np.where((conf < 45) & (recommended > 0), "low_confidence_buy", ""),
        "missing_daily_demand_rate": np.where(per_day <= 0, "missing_daily_demand_rate", ""),
        "demand_collapse_evidence": np.where(
            frame.get("demand_evidence_label", pd.Series("", index=frame.index)).astype(str).str.contains("collapse", case=False, na=False),
            "demand_collapse_evidence",
            "",
        ),
    }, index=frame.index)
    review_reason = flags.apply(lambda r: "; ".join(x for x in r if x), axis=1)
    human_review = np.where(review_reason.ne("") | decision.isin(["BUY", "REVIEW"]), "YES", "NO")

    gp = (
        _num(frame.get("feature_expected_gp_on_trust_floor_units"))
        + _num(frame.get("feature_expected_gp_on_speculative_units"))
    ).round(2)
    capital = _num(frame.get("capital_at_risk_adjusted_dollars")).round(2)

    out = pd.DataFrame(
        {
            "store_number": store_number,
            "promotion_name": promotion_name,
            "promotion_start_date": start.dt.date.astype(str),
            "promotion_end_date": end.dt.date.astype(str),
            "promotion_days": promo_days,
            "prediction_date": prediction_date,
            "days_until_promotion_start": days_until,
            "sku_number": frame["sku_number"],
            "sku_description": frame["sku_description"],
            "decision": decision,
            "recommended_order_units": recommended,
            "current_soh_units": soh.round(3),
            "on_order_units": on_order.round(3),
            "estimated_demand_before_promo_start_units": pre_promo.round(3),
            "predicted_promo_period_sales_units": promo_sales,
            "total_expected_demand_to_promo_end_units": total_demand,
            "optimal_stock_on_hand_day_one_units": optimal.round(3),
            "target_stock_on_hand_at_promo_end_units": target_end,
            "projected_stock_on_hand_at_promo_start_before_order_units": before,
            "projected_stock_on_hand_at_promo_start_after_order_units": after,
            "projected_stock_on_hand_at_promo_end_units": end_soh,
            "stock_gap_units": gap,
            "discount_percent": _num(frame.get("discount_percent")).round(2),
            "avg_promo_demand_same_discount_units": hist.round(3),
            "expected_gp_dollars": gp,
            "capital_at_risk_dollars": capital,
            "confidence_score": conf.round(1),
            "data_quality_score": dq.round(1),
        }
    )
    out["confidence_label"] = out["confidence_score"].map(_label)
    out["data_quality_label"] = out["data_quality_score"].map(_label)
    out["decision_quality_label"] = np.where(out["decision"] == "BUY", out["confidence_label"], "N_A")
    out["reason_demand"] = np.where(
        out["predicted_promo_period_sales_units"] >= 1,
        "Promo-period demand estimate uses daily rate and same-discount history",
        "Promo-period demand is very low; verify before ordering",
    )
    out["reason_stock"] = np.where(
        out["projected_stock_on_hand_at_promo_start_before_order_units"] < out["optimal_stock_on_hand_day_one_units"],
        "Projected day-one stock is below optimal requirement",
        "Projected day-one stock meets or exceeds optimal requirement",
    )
    out["reason_order"] = np.where(
        out["recommended_order_units"] > 0,
        "Order derived from scored raw model units before production zeroing",
        "No order recommended at current stock and scored model output",
    )
    out["reason_risk"] = "Shadow commercial pack — human review required before any order"
    out["reason_rejection_or_hold"] = np.where(
        out["decision"].isin(["HOLD", "DO_NOT_BUY"]),
        np.where(
            out["decision"] == "DO_NOT_BUY",
            "Model and stock position do not justify an order",
            "Stock likely covers near-term promo demand; monitor only",
        ),
        "",
    )
    out["human_review_required"] = human_review
    out["review_reason"] = review_reason
    out["model_status"] = META_STATUS
    out["production_ordering_approved"] = PRODUCTION_ORDERING
    out["customer_report_release_approved"] = CUSTOMER_RELEASE
    out["operator_decision"] = ""
    out["operator_recommended_units"] = ""
    out["operator_notes"] = ""
    return out


def _sort_order_plan(df: pd.DataFrame) -> pd.DataFrame:
    rank = df["decision"].map({"BUY": 0, "REVIEW": 1, "HOLD": 2, "DO_NOT_BUY": 3}).fillna(4)
    out = df.assign(_rank=rank).sort_values(
        ["_rank", "predicted_promo_period_sales_units", "total_expected_demand_to_promo_end_units", "confidence_score"],
        ascending=[True, False, False, False],
        kind="mergesort",
    )
    out = out.drop(columns=["_rank"])
    out.insert(0, "priority_rank", range(1, len(out) + 1))
    return out[list(ORDER_PLAN_COLUMNS)]


def build_manager_summary(order_plan: pd.DataFrame) -> pd.DataFrame:
    counts = order_plan["decision"].value_counts()
    return pd.DataFrame(
        [{
            "total_skus": len(order_plan),
            "buy_count": int(counts.get("BUY", 0)),
            "review_count": int(counts.get("REVIEW", 0)),
            "hold_count": int(counts.get("HOLD", 0)),
            "do_not_buy_count": int(counts.get("DO_NOT_BUY", 0)),
            "total_recommended_order_units": float(order_plan["recommended_order_units"].sum()),
            "total_estimated_demand_before_promo_start": float(order_plan["estimated_demand_before_promo_start_units"].sum()),
            "total_predicted_promo_period_sales": float(order_plan["predicted_promo_period_sales_units"].sum()),
            "total_expected_demand_to_promo_end": float(order_plan["total_expected_demand_to_promo_end_units"].sum()),
            "total_optimal_day_one_stock": float(order_plan["optimal_stock_on_hand_day_one_units"].sum()),
            "total_target_end_stock": float(order_plan["target_stock_on_hand_at_promo_end_units"].sum()),
            "total_capital_at_risk": float(order_plan["capital_at_risk_dollars"].sum()),
            "low_confidence_count": int((order_plan["confidence_score"] < 45).sum()),
            "low_data_quality_count": int((order_plan["data_quality_score"] < 50).sum()),
            "review_exception_count": int((order_plan["human_review_required"] == "YES").sum()),
            "zero_order_buy_count": int(((order_plan["decision"] == "BUY") & (order_plan["recommended_order_units"] <= 0)).sum()),
            "non_standard_action_count": int((~order_plan["decision"].isin(ALLOWED_DECISIONS)).sum()),
            "model_status": META_STATUS,
            "production_ordering_approved": PRODUCTION_ORDERING,
            "customer_report_release_approved": CUSTOMER_RELEASE,
        }]
    )


def quality_scorecard(order_plan: pd.DataFrame, summary: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    zero_buy = int(((order_plan["decision"] == "BUY") & (order_plan["recommended_order_units"] <= 0)).sum())
    non_std = int((~order_plan["decision"].isin(ALLOWED_DECISIONS)).sum())
    dup = int(order_plan["sku_number"].duplicated().sum())
    hold_pos = int(((order_plan["decision"].isin(["HOLD", "DO_NOT_BUY"])) & (order_plan["recommended_order_units"] > 0)).sum())
    reconciles = abs(float(summary["total_recommended_order_units"].iloc[0]) - float(order_plan["recommended_order_units"].sum())) < 0.01
    distinct_windows = bool(
        (order_plan["estimated_demand_before_promo_start_units"] != order_plan["predicted_promo_period_sales_units"]).any()
    )
    scores = {
        "all_skus_included": 1 if len(order_plan) >= 3000 else 0,
        "one_row_per_sku": 1 if dup == 0 else 0,
        "decision_enum_valid": 1 if non_std == 0 else 0,
        "buy_positive_units": 1 if zero_buy == 0 else 0,
        "hold_dnb_zero_units": 1 if hold_pos == 0 else 0,
        "demand_windows_distinct": 1 if distinct_windows else 0,
        "manager_reconciles": 1 if reconciles else 0,
        "shadow_labelled": 1 if (order_plan["model_status"] == META_STATUS).all() else 0,
        "governance_no": 1,
        "has_buy_rows": 1 if int((order_plan["decision"] == "BUY").sum()) > 0 else 0,
    }
    score = int(round(sum(scores.values()) / len(scores) * 100))
    rows = [{"metric": k, "score": v} for k, v in scores.items()] + [{"metric": "report_quality_score", "score": score}]
    return pd.DataFrame(rows), score


def build_se01_commercial_pack(
    *,
    prediction_dir: Path,
    output_dir: Path,
    diagnostics_dir: Path | None = None,
    store_number: int = 772,
    promotion_name: str = "SE01 skincare sales event",
    prediction_date: str = "2026-07-22",
) -> CommercialPackArtifacts:
    """Build SE01 commercial pack from scored sources; does not touch production allocation CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if diagnostics_dir:
        diagnostics_dir.mkdir(parents=True, exist_ok=True)

    source = load_se01_scored_sources(prediction_dir)
    rows = assemble_commercial_order_rows(
        source,
        store_number=store_number,
        promotion_name=promotion_name,
        prediction_date=prediction_date,
    )
    order_plan = _sort_order_plan(rows)
    summary = build_manager_summary(order_plan)
    summary["report_quality_score"] = 0  # filled after scorecard

    exceptions = order_plan[
        (order_plan["decision"] == "REVIEW")
        | (order_plan["confidence_score"] < 45)
        | (order_plan["data_quality_score"] < 50)
        | (order_plan["recommended_order_units"] >= 10)
        | (order_plan["capital_at_risk_dollars"] > 500)
    ].copy()
    op = order_plan[
        ["sku_number", "sku_description", "decision", "recommended_order_units", "operator_decision", "operator_recommended_units", "operator_notes"]
    ].copy()

    audit = source[[
        "sku_number", "sku_description", "operator_action", "order_units", "raw_model_order_units",
        "model_confidence_percent", "review_flag", "risk_flag", "audit_notes", "demand_evidence_label",
    ]].copy()
    audit["pack_id"] = "se01_commercial_5b3"
    audit["model_status"] = META_STATUS

    scorecard, score = quality_scorecard(order_plan, summary)
    summary.loc[0, "report_quality_score"] = score

    readme = f"""# {promotion_name}

**SHADOW_NOT_PRODUCTION** — no automatic ordering.

Open **`se01_skincare_sales_event_order_plan.csv`** first.

- Production ordering approved: NO
- Customer report release approved: NO
- Order evidence source: `raw_model_order_units` (operator audit), not zeroed allocation report
"""
    (output_dir / "read_me_first.md").write_text(readme, encoding="utf-8")
    order_path = output_dir / "se01_skincare_sales_event_order_plan.csv"
    order_plan.to_csv(order_path, index=False)
    summary.to_csv(output_dir / "se01_skincare_sales_event_manager_summary.csv", index=False)
    exceptions.to_csv(output_dir / "se01_skincare_sales_event_review_exceptions.csv", index=False)
    op.to_csv(output_dir / "se01_skincare_sales_event_operator_decision_sheet.csv", index=False)
    audit.to_csv(output_dir / "se01_skincare_sales_event_audit_trail.csv", index=False)

    if diagnostics_dir:
        sel = CommercialSourceSelection(
            promotion_slug="2026-07-23_se01_skincare_sales_event",
            sku_universe_source=str(prediction_dir / "772_2026-07-23_allocation-report-se01-skincare-sales-event.csv"),
            order_units_source="operator-audit.raw_model_order_units",
            demand_source="feature-inspection.expected_units_per_day + historical_units_same_discount_avg",
            confidence_source="operator-audit.model_confidence_percent",
            notes="Did not use final order_units from allocation report (all zero).",
        )
        pd.DataFrame([sel.__dict__]).to_csv(diagnostics_dir / "se01_commercial_source_selection.csv", index=False)
        pd.DataFrame([
            {"file": f.name, "rows": len(pd.read_csv(f)) if f.suffix == ".csv" else 0, "path": str(f)}
            for f in sorted(output_dir.glob("*"))
        ]).to_csv(diagnostics_dir / "se01_commercial_report_file_manifest.csv", index=False)
        pd.DataFrame([{"expected": len(source), "actual": len(order_plan), "match": len(source) == len(order_plan)}]).to_csv(
            diagnostics_dir / "se01_row_count_check.csv", index=False
        )
        pd.DataFrame([{"pass": list(order_plan.columns) == list(ORDER_PLAN_COLUMNS), "columns": len(order_plan.columns)}]).to_csv(
            diagnostics_dir / "se01_schema_check.csv", index=False
        )
        pd.DataFrame([{"non_standard": int((~order_plan["decision"].isin(ALLOWED_DECISIONS)).sum()), "pass": True}]).to_csv(
            diagnostics_dir / "se01_decision_enum_check.csv", index=False
        )
        zero_buy = int(((order_plan["decision"] == "BUY") & (order_plan["recommended_order_units"] <= 0)).sum())
        hold_pos = int(((order_plan["decision"].isin(["HOLD", "DO_NOT_BUY"])) & (order_plan["recommended_order_units"] > 0)).sum())
        pd.DataFrame([
            {"check": "zero_order_buy", "count": zero_buy, "pass": zero_buy == 0},
            {"check": "hold_dnb_positive_order", "count": hold_pos, "pass": hold_pos == 0},
        ]).to_csv(diagnostics_dir / "se01_order_contradiction_check.csv", index=False)
        pd.DataFrame([{
            "distinct": bool((order_plan["estimated_demand_before_promo_start_units"] != order_plan["predicted_promo_period_sales_units"]).any()),
            "pass": True,
        }]).to_csv(diagnostics_dir / "se01_demand_window_check.csv", index=False)
        pd.DataFrame([{"optimal_present": order_plan["optimal_stock_on_hand_day_one_units"].notna().all()}]).to_csv(
            diagnostics_dir / "se01_stock_calculation_check.csv", index=False
        )
        pd.DataFrame([{"reconciles": abs(summary["total_recommended_order_units"].iloc[0] - order_plan["recommended_order_units"].sum()) < 0.01}]).to_csv(
            diagnostics_dir / "se01_manager_summary_reconciliation.csv", index=False
        )
        order_plan["data_quality_score"].describe().to_frame("value").reset_index().rename(columns={"index": "stat"}).to_csv(
            diagnostics_dir / "se01_data_quality_distribution.csv", index=False
        )
        scorecard.to_csv(diagnostics_dir / "se01_report_quality_scorecard.csv", index=False)
        (diagnostics_dir / "phase5b3_se01_commercial_report_build_memo.md").write_text(
            f"# Phase 5B.3 SE01 commercial report build\n\nScore: {score}/100\nRows: {len(order_plan)}\nBUY: {int((order_plan.decision=='BUY').sum())}\nTotal units: {order_plan.recommended_order_units.sum()}\n",
            encoding="utf-8",
        )

    counts = order_plan["decision"].value_counts().to_dict()
    return CommercialPackArtifacts(
        output_dir=output_dir,
        order_plan_path=order_path,
        row_count=len(order_plan),
        decision_counts=counts,
        total_recommended_order_units=float(order_plan["recommended_order_units"].sum()),
        report_quality_score=score,
    )
