from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_controlled_overlay_narrowing_plan as module  # noqa: E402


PROMOTION_KEY = "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1"
PROMOTION_NAME = "Allocation Report - WK47&48 WINTER PART 1"
PROMOTION_START_DATE = "2026-05-21"
PROMOTION_END_DATE = "2026-06-03"

SECOND_PROMOTION_KEY = "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX"
SECOND_PROMOTION_NAME = "Allocation Report - WK45&46 BABY & YOU BOX"
SECOND_PROMOTION_START_DATE = "2026-05-07"
SECOND_PROMOTION_END_DATE = "2026-05-20"


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _overlay_rows() -> list[dict[str, object]]:
    return [
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 1,
            "sku_number": "1001",
            "sku_description": "Strong Conversion One",
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 8,
            "forecast_error_units": -7.0,
            "absolute_error_units": 7.0,
            "actual_sell_through_pct": 0.8,
            "actual_gross_profit": 28.0,
            "capital_left": 0,
            "capital_left_value": 0.0,
            "gross_profit_represented": 28.0,
            "capital_at_risk": 4.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 5,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 2,
            "sku_number": "1002",
            "sku_description": "Strong Conversion Two",
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 7,
            "forecast_error_units": -6.0,
            "absolute_error_units": 6.0,
            "actual_sell_through_pct": 0.7,
            "actual_gross_profit": 22.0,
            "capital_left": 1,
            "capital_left_value": 1.0,
            "gross_profit_represented": 22.0,
            "capital_at_risk": 5.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 14,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 3,
            "sku_number": "1003",
            "sku_description": "Low Soh Strong",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 6,
            "forecast_error_units": -5.0,
            "absolute_error_units": 5.0,
            "actual_sell_through_pct": 1.0,
            "actual_gross_profit": 18.0,
            "capital_left": 0,
            "capital_left_value": 0.0,
            "gross_profit_represented": 18.0,
            "capital_at_risk": 5.0,
            "stockout_or_missed_demand_flag": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 18,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 4,
            "sku_number": "1004",
            "sku_description": "No Prior Strong",
            "store_action_label": "NO_DEMAND",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NEVER_SOLD_IN_PROMO",
            "expected_promo_demand": 1,
            "actual_units": 5,
            "forecast_error_units": -4.0,
            "absolute_error_units": 4.0,
            "actual_sell_through_pct": 0.9,
            "actual_gross_profit": 16.0,
            "capital_left": 2,
            "capital_left_value": 3.0,
            "gross_profit_represented": 16.0,
            "capital_at_risk": 4.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 12,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 5,
            "sku_number": "1005",
            "sku_description": "Online Floor Moderate",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 4,
            "forecast_error_units": -3.0,
            "absolute_error_units": 3.0,
            "actual_sell_through_pct": 0.6,
            "actual_gross_profit": 9.0,
            "capital_left": 2,
            "capital_left_value": 4.0,
            "gross_profit_represented": 9.0,
            "capital_at_risk": 5.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "ONLINE_FLOOR_PROTECTION_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 31,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 6,
            "sku_number": "1006",
            "sku_description": "No Prior Moderate",
            "store_action_label": "NO_DEMAND",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NEVER_SOLD_IN_PROMO",
            "expected_promo_demand": 1,
            "actual_units": 3,
            "forecast_error_units": -3.0,
            "absolute_error_units": 3.0,
            "actual_sell_through_pct": 0.6,
            "actual_gross_profit": 8.0,
            "capital_left": 3,
            "capital_left_value": 5.0,
            "gross_profit_represented": 8.0,
            "capital_at_risk": 4.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 42,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 7,
            "sku_number": "1007",
            "sku_description": "Action Layer Moderate",
            "store_action_label": "PROTECT_AVAILABILITY",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 2,
            "forecast_error_units": -3.0,
            "absolute_error_units": 3.0,
            "actual_sell_through_pct": 0.5,
            "actual_gross_profit": 8.0,
            "capital_left": 3,
            "capital_left_value": 5.0,
            "gross_profit_represented": 8.0,
            "capital_at_risk": 6.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 48,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 8,
            "sku_number": "1008",
            "sku_description": "Low Soh Weak",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 2,
            "forecast_error_units": -2.0,
            "absolute_error_units": 2.0,
            "actual_sell_through_pct": 0.3,
            "actual_gross_profit": 5.0,
            "capital_left": 4,
            "capital_left_value": 8.0,
            "gross_profit_represented": 5.0,
            "capital_at_risk": 4.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 60,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 9,
            "sku_number": "1009",
            "sku_description": "Action Layer Weak",
            "store_action_label": "PROTECT_AVAILABILITY",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 1,
            "forecast_error_units": -2.0,
            "absolute_error_units": 2.0,
            "actual_sell_through_pct": 0.2,
            "actual_gross_profit": 3.0,
            "capital_left": 2,
            "capital_left_value": 6.0,
            "gross_profit_represented": 3.0,
            "capital_at_risk": 4.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 85,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 10,
            "sku_number": "1010",
            "sku_description": "No Prior Weak",
            "store_action_label": "NO_DEMAND",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NEVER_SOLD_IN_PROMO",
            "expected_promo_demand": 1,
            "actual_units": 1,
            "forecast_error_units": -1.0,
            "absolute_error_units": 1.0,
            "actual_sell_through_pct": 0.1,
            "actual_gross_profit": 2.0,
            "capital_left": 5,
            "capital_left_value": 8.0,
            "gross_profit_represented": 2.0,
            "capital_at_risk": 3.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 130,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 11,
            "sku_number": "1011",
            "sku_description": "Online Weak",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 0,
            "forecast_error_units": 0.0,
            "absolute_error_units": 0.0,
            "actual_sell_through_pct": 0.0,
            "actual_gross_profit": 0.0,
            "capital_left": 6,
            "capital_left_value": 11.0,
            "gross_profit_represented": 0.0,
            "capital_at_risk": 2.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "ONLINE_FLOOR_PROTECTION_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 170,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 12,
            "sku_number": "1012",
            "sku_description": "Zero Order Cleanup",
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "Order now to protect availability.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 1,
            "forecast_error_units": -1.0,
            "absolute_error_units": 1.0,
            "actual_sell_through_pct": 0.1,
            "actual_gross_profit": 1.0,
            "capital_left": 3,
            "capital_left_value": 4.0,
            "gross_profit_represented": 1.0,
            "capital_at_risk": 1.0,
            "stockout_or_missed_demand_flag": 0,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "overlay_category": "ZERO_ORDER_TEXT_CLEANUP_REVIEW",
            "proposed_review_action": "INSPECT_ONLY",
            "why_review_required": "review",
            "review_trigger_detail": "detail",
            "review_only_flag": 1,
            "generated_order_recommendation_flag": 0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "top_error_rank": 175,
        },
    ]


def _inspection_summary_rows(*, overlay_rows_count: int, inspection_status: str = "CONTROLLED_OVERLAY_INSPECTION_REQUIRES_NARROWING", production_guardrail_status: str = "PASS", stage12_guardrail_status: str = "PASS") -> list[dict[str, object]]:
    metrics = {
        "SELECTED_PROMOTION": PROMOTION_KEY,
        "INSPECTION_STATUS": inspection_status,
        "OVERLAY_ROW_COUNT": overlay_rows_count,
        "REVIEW_ROW_COUNT": 100,
        "QUARANTINE_ROW_COUNT": 1,
        "PRODUCTION_GUARDRAIL_STATUS": production_guardrail_status,
        "STAGE12_GUARDRAIL_STATUS": stage12_guardrail_status,
    }
    return [
        {"metric_name": name, "metric_value": value, "metric_display": str(value), "notes": "ok"}
        for name, value in metrics.items()
    ]


def _retarget_rows(
    rows: list[dict[str, object]],
    *,
    promotion_key: str,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
) -> list[dict[str, object]]:
    retargeted: list[dict[str, object]] = []
    for row in rows:
        updated = dict(row)
        updated["promotion_key"] = promotion_key
        if "promotion_name" in updated:
            updated["promotion_name"] = promotion_name
        if "promotion_start_date" in updated:
            updated["promotion_start_date"] = promotion_start_date
        if "promotion_end_date" in updated:
            updated["promotion_end_date"] = promotion_end_date
        retargeted.append(updated)
    return retargeted


def _retarget_quarantine_rows(
    rows: list[dict[str, object]],
    *,
    promotion_key: str,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
    source_row_number: int,
) -> list[dict[str, object]]:
    retargeted = _retarget_rows(
        rows,
        promotion_key=promotion_key,
        promotion_name=promotion_name,
        promotion_start_date=promotion_start_date,
        promotion_end_date=promotion_end_date,
    )
    for row in retargeted:
        row["source_row_number"] = source_row_number
    return retargeted


def _inspection_category_quality_rows() -> list[dict[str, object]]:
    return [
        {"overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW", "row_count": 2, "overlay_row_share_pct": 16.67, "reference_row_count": 2, "absolute_difference_vs_reference": 0, "top20_error_hit_count": 2, "top20_error_hit_share_pct": 100.0, "mean_absolute_error_units": 6.5, "mean_actual_gross_profit": 25.0, "mean_capital_left_value": 0.5, "strength_score": 25.0, "noise_score": 4.0, "strength_status": "STRONG_REVIEW_TRIGGER", "noise_status": "REVIEW_CATEGORY_IN_RANGE", "quality_notes": "ok"},
        {"overlay_category": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW", "row_count": 2, "overlay_row_share_pct": 16.67, "reference_row_count": 2, "absolute_difference_vs_reference": 0, "top20_error_hit_count": 1, "top20_error_hit_share_pct": 50.0, "mean_absolute_error_units": 3.5, "mean_actual_gross_profit": 11.5, "mean_capital_left_value": 4.0, "strength_score": 12.0, "noise_score": 10.0, "strength_status": "WEAKER_REVIEW_TRIGGER", "noise_status": "REVIEW_CATEGORY_IN_RANGE", "quality_notes": "ok"},
        {"overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW", "row_count": 3, "overlay_row_share_pct": 25.0, "reference_row_count": 2, "absolute_difference_vs_reference": 1, "top20_error_hit_count": 1, "top20_error_hit_share_pct": 33.33, "mean_absolute_error_units": 2.67, "mean_actual_gross_profit": 8.67, "mean_capital_left_value": 5.33, "strength_score": 8.0, "noise_score": 155.0, "strength_status": "WEAKER_REVIEW_TRIGGER", "noise_status": "NOISY_REVIEW_CATEGORY", "quality_notes": "noisy"},
        {"overlay_category": "ONLINE_FLOOR_PROTECTION_REVIEW", "row_count": 2, "overlay_row_share_pct": 16.67, "reference_row_count": 2, "absolute_difference_vs_reference": 0, "top20_error_hit_count": 0, "top20_error_hit_share_pct": 0.0, "mean_absolute_error_units": 1.5, "mean_actual_gross_profit": 4.5, "mean_capital_left_value": 7.5, "strength_score": 3.0, "noise_score": 180.0, "strength_status": "WEAKER_REVIEW_TRIGGER", "noise_status": "NOISY_REVIEW_CATEGORY", "quality_notes": "noisy"},
        {"overlay_category": "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW", "row_count": 2, "overlay_row_share_pct": 16.67, "reference_row_count": 2, "absolute_difference_vs_reference": 0, "top20_error_hit_count": 0, "top20_error_hit_share_pct": 0.0, "mean_absolute_error_units": 2.5, "mean_actual_gross_profit": 5.5, "mean_capital_left_value": 5.5, "strength_score": 5.0, "noise_score": 20.0, "strength_status": "WEAKER_REVIEW_TRIGGER", "noise_status": "REVIEW_CATEGORY_IN_RANGE", "quality_notes": "ok"},
        {"overlay_category": "ZERO_ORDER_TEXT_CLEANUP_REVIEW", "row_count": 1, "overlay_row_share_pct": 8.33, "reference_row_count": 1, "absolute_difference_vs_reference": 0, "top20_error_hit_count": 0, "top20_error_hit_share_pct": 0.0, "mean_absolute_error_units": 1.0, "mean_actual_gross_profit": 1.0, "mean_capital_left_value": 4.0, "strength_score": 1.0, "noise_score": 30.0, "strength_status": "WEAKER_REVIEW_TRIGGER", "noise_status": "REVIEW_CATEGORY_IN_RANGE", "quality_notes": "cleanup"},
    ]


def _inspection_top_sku_rows() -> list[dict[str, object]]:
    return [
        {"review_rank": 1, "sku_number": "1001", "sku_description": "Strong Conversion One", "trigger_count": 1, "category_count": 1, "categories": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW", "best_top_error_rank": 5, "max_absolute_error_units": 7.0, "max_actual_gross_profit": 28.0, "max_capital_left_value": 0.0, "breadth_signal_status": "SINGLE_CATEGORY_TRIGGER", "review_notes": "ok"},
        {"review_rank": 2, "sku_number": "1002", "sku_description": "Strong Conversion Two", "trigger_count": 1, "category_count": 1, "categories": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW", "best_top_error_rank": 14, "max_absolute_error_units": 6.0, "max_actual_gross_profit": 22.0, "max_capital_left_value": 1.0, "breadth_signal_status": "SINGLE_CATEGORY_TRIGGER", "review_notes": "ok"},
        {"review_rank": 3, "sku_number": "1003", "sku_description": "Low Soh Strong", "trigger_count": 1, "category_count": 1, "categories": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW", "best_top_error_rank": 18, "max_absolute_error_units": 5.0, "max_actual_gross_profit": 18.0, "max_capital_left_value": 0.0, "breadth_signal_status": "SINGLE_CATEGORY_TRIGGER", "review_notes": "ok"},
    ]


def _inspection_broadness_rows(*, overlay_rows_count: int) -> list[dict[str, object]]:
    return [
        {"broadness_metric": "OVERLAY_ROW_COUNT", "metric_value": overlay_rows_count, "metric_display": str(overlay_rows_count), "broadness_status": "BROAD_REVIEW_SURFACE", "notes": "ok"},
        {"broadness_metric": "REVIEW_ROW_COUNT", "metric_value": 100, "metric_display": "100", "broadness_status": "BROAD_REVIEW_SURFACE", "notes": "ok"},
    ]


def _overlay_by_category_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    frame = pd.DataFrame(rows)
    output: list[dict[str, object]] = []
    reference_lookup = {
        "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": 2,
        "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": 2,
        "NO_PRIOR_DEMAND_SURPRISE_REVIEW": 2,
        "ONLINE_FLOOR_PROTECTION_REVIEW": 2,
        "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": 2,
        "ZERO_ORDER_TEXT_CLEANUP_REVIEW": 1,
    }
    for category, category_frame in frame.groupby("overlay_category", sort=False):
        output.append(
            {
                "overlay_category": category,
                "row_count": len(category_frame.index),
                "reference_row_count": reference_lookup.get(category, 0),
                "absolute_difference_vs_reference": abs(len(category_frame.index) - reference_lookup.get(category, 0)),
                "reconciliation_status": "ABOVE_REFERENCE",
                "actual_units_total": float(pd.to_numeric(category_frame["actual_units"]).sum()),
                "actual_gross_profit_total": float(pd.to_numeric(category_frame["actual_gross_profit"]).sum()),
                "capital_left_value_total": float(pd.to_numeric(category_frame["capital_left_value"]).sum()),
                "sample_skus": ", ".join(category_frame["sku_number"].astype(str).head(3).tolist()),
                "notes": "ok",
            }
        )
    return output


def _quarantine_rows() -> list[dict[str, object]]:
    return [
        {
            "source_row_number": 48,
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "quarantine_reason": "Missing join key",
            "remediation_required": "Keep separate",
        }
    ]


def _review_rows(review_row_count: int) -> list[dict[str, object]]:
    return [
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": index + 1 if index < 47 else index + 2,
            "sku_number": f"BASE{index + 1}",
            "sku_description": f"Base SKU {index + 1}",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "review",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": 3,
            "actual_gross_profit": 5.0,
            "actual_sell_through_pct": 0.3,
            "capital_left": 2,
            "capital_left_value": 4.0,
            "stockout_or_missed_demand_flag": 0,
            "promo_price": 3.0,
            "promo_cost": 2.0,
            "promo_gross_profit_per_unit": 1.0,
            "gross_profit_represented": 5.0,
            "capital_at_risk": 2.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": -2.0,
            "absolute_error_units": 2.0,
        }
        for index in range(review_row_count)
    ]


def _top_errors_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for rank, row in enumerate(rows, start=1):
        copied = dict(row)
        copied["error_rank"] = rank
        output.append(copied)
    return output


def _write_inputs(
    packet_root: Path,
    *,
    inspection_root: Path | None = None,
    overlay_root: Path | None = None,
    rebuild_root: Path | None = None,
    overlay_generated_order_flag: int = 0,
    inspection_status: str = "CONTROLLED_OVERLAY_INSPECTION_REQUIRES_NARROWING",
    overlay_rows: list[dict[str, object]] | None = None,
    inspection_summary_rows: list[dict[str, object]] | None = None,
    inspection_category_quality_rows: list[dict[str, object]] | None = None,
    inspection_top_sku_rows: list[dict[str, object]] | None = None,
    inspection_broadness_rows: list[dict[str, object]] | None = None,
    overlay_by_category_rows: list[dict[str, object]] | None = None,
    overlay_quarantine_rows: list[dict[str, object]] | None = None,
    rebuild_review_rows: list[dict[str, object]] | None = None,
    rebuild_top_errors_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_overlay_rows = _overlay_rows() if overlay_rows is None else overlay_rows
    if overlay_generated_order_flag:
        resolved_overlay_rows[0]["generated_order_recommendation_flag"] = 1

    resolved_inspection_root = inspection_root if inspection_root is not None else packet_root / module.INSPECTION_FOLDER_NAME
    resolved_overlay_root = overlay_root if overlay_root is not None else packet_root / module.OVERLAY_RECONSTRUCTION_FOLDER_NAME
    resolved_rebuild_root = rebuild_root if rebuild_root is not None else packet_root / module.CONTROLLED_REBUILD_FOLDER_NAME
    _write_csv(
        resolved_inspection_root / module.INSPECTION_SUMMARY_FILE_NAME,
        _inspection_summary_rows(overlay_rows_count=len(resolved_overlay_rows), inspection_status=inspection_status)
        if inspection_summary_rows is None
        else inspection_summary_rows,
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_CATEGORY_QUALITY_FILE_NAME,
        _inspection_category_quality_rows() if inspection_category_quality_rows is None else inspection_category_quality_rows,
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_TOP_SKU_REVIEW_FILE_NAME,
        _inspection_top_sku_rows() if inspection_top_sku_rows is None else inspection_top_sku_rows,
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_BROADNESS_REVIEW_FILE_NAME,
        _inspection_broadness_rows(overlay_rows_count=len(resolved_overlay_rows)) if inspection_broadness_rows is None else inspection_broadness_rows,
    )
    _write_csv(resolved_overlay_root / module.OVERLAY_ROWS_FILE_NAME, resolved_overlay_rows)
    _write_csv(
        resolved_overlay_root / module.OVERLAY_BY_CATEGORY_FILE_NAME,
        _overlay_by_category_rows(resolved_overlay_rows) if overlay_by_category_rows is None else overlay_by_category_rows,
    )
    _write_csv(
        resolved_overlay_root / module.OVERLAY_QUARANTINE_FILE_NAME,
        _quarantine_rows() if overlay_quarantine_rows is None else overlay_quarantine_rows,
    )
    _write_csv(
        resolved_rebuild_root / module.REBUILD_REVIEW_ROWS_FILE_NAME,
        _review_rows(100) if rebuild_review_rows is None else rebuild_review_rows,
    )
    _write_csv(
        resolved_rebuild_root / module.REBUILD_TOP_ERRORS_FILE_NAME,
        _top_errors_rows(resolved_overlay_rows) if rebuild_top_errors_rows is None else rebuild_top_errors_rows,
    )


class PromotionsMaterializedSourceControlledOverlayNarrowingPlanTests(unittest.TestCase):
    def test_broad_overlay_narrows_into_tiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.multiple(
                module,
                EXPECTED_INPUT_OVERLAY_ROW_COUNT=12,
                EXPECTED_QUARANTINE_ROW_COUNT=1,
            ):
                result = module.build_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root
                )

            self.assertEqual(result.narrowing_status, module.CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE)
            self.assertGreater(result.tier_1_row_count, 0)
            self.assertGreater(result.tier_2_row_count, 0)
            self.assertGreater(result.rejected_row_count, 0)

    def test_all_input_rows_accounted_for(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.object(module, "EXPECTED_INPUT_OVERLAY_ROW_COUNT", 12):
                result = module.build_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root
                )

            self.assertEqual(
                result.tier_1_row_count + result.tier_2_row_count + result.tier_3_row_count + result.rejected_row_count,
                12,
            )
            validation_lookup = result.validation_frame.set_index("check_name")
            self.assertEqual(str(validation_lookup.loc["ALL_INPUT_ROWS_ACCOUNTED_FOR", "check_status"]), "PASS")

    def test_rejected_rows_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.object(module, "EXPECTED_INPUT_OVERLAY_ROW_COUNT", 12):
                artifacts = module.write_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root
                )

            rejected_frame = pd.read_csv(artifacts.rejected_rows_csv_path, keep_default_na=False)
            self.assertFalse(rejected_frame.empty)
            self.assertTrue(rejected_frame["narrowing_tier"].eq(module.REJECT_NOISY_BROAD_TRIGGER).all())

    def test_quarantine_row_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.multiple(
                module,
                EXPECTED_INPUT_OVERLAY_ROW_COUNT=12,
                EXPECTED_QUARANTINE_ROW_COUNT=1,
            ):
                result = module.build_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root
                )

            self.assertFalse(result.plan_rows_frame["source_row_id"].astype(str).eq("48").any())
            validation_lookup = result.validation_frame.set_index("check_name")
            self.assertEqual(
                str(validation_lookup.loc["NO_QUARANTINE_ROWS_INCLUDED_IN_NARROWED_ROWS", "check_status"]),
                "PASS",
            )

    def test_no_order_recommendation_risk_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, overlay_generated_order_flag=1)

            with patch.object(module, "EXPECTED_INPUT_OVERLAY_ROW_COUNT", 12):
                result = module.build_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root
                )

            self.assertEqual(
                result.narrowing_status,
                module.CONTROLLED_OVERLAY_NARROWING_BLOCKED_ORDER_RECOMMENDATION_RISK,
            )

    def test_tier_1_controlled_surface_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.multiple(
                module,
                EXPECTED_INPUT_OVERLAY_ROW_COUNT=12,
                TIER_1_CONTROLLED_SHARE_LIMIT_PCT=10.0,
            ):
                result = module.build_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root
                )

            self.assertEqual(result.narrowing_status, module.CONTROLLED_OVERLAY_NARROWING_REQUIRES_REVIEW)
            self.assertEqual(result.action_layer_reconstruction_can_be_authored_next, 0)

    def test_narrowing_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, inspection_status="CONTROLLED_OVERLAY_INSPECTION_BLOCKED_GUARDRAIL_FAILURE")
            _write_inputs(
                packet_root,
                inspection_root=upstream_root / module.INSPECTION_FOLDER_NAME,
                overlay_root=upstream_root / module.OVERLAY_RECONSTRUCTION_FOLDER_NAME,
                rebuild_root=upstream_root / module.CONTROLLED_REBUILD_FOLDER_NAME,
            )

            with patch.multiple(module, EXPECTED_INPUT_OVERLAY_ROW_COUNT=12, EXPECTED_QUARANTINE_ROW_COUNT=1):
                result = module.build_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertEqual(result.narrowing_status, module.CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE)
            self.assertGreater(result.tier_1_row_count, 0)
            self.assertGreater(result.rejected_row_count, 0)

    def test_narrowing_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(module.PromotionsMaterializedSourceControlledOverlayNarrowingPlanError) as error_context:
                module.build_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_write_narrowing_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / module.OUTPUT_FOLDER_NAME
            _write_inputs(
                packet_root,
                inspection_root=upstream_root,
                overlay_root=upstream_root,
                rebuild_root=upstream_root,
            )

            with patch.object(module, "EXPECTED_INPUT_OVERLAY_ROW_COUNT", 12):
                artifacts = module.write_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                    output_root=output_root,
                )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / module.PLAN_ROWS_FILE_NAME).exists())
            self.assertTrue((output_root / module.PLAN_VALIDATION_FILE_NAME).exists())

    def test_narrowing_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            second_overlay_rows = _retarget_rows(
                _overlay_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            combined_overlay_rows = _overlay_rows() + second_overlay_rows
            combined_quarantine_rows = _quarantine_rows() + _retarget_quarantine_rows(
                _quarantine_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
                source_row_number=49,
            )
            custom_summary_rows = _inspection_summary_rows(overlay_rows_count=len(second_overlay_rows))
            custom_summary_rows[0]["metric_value"] = SECOND_PROMOTION_KEY
            custom_summary_rows[0]["metric_display"] = SECOND_PROMOTION_KEY
            _write_inputs(
                packet_root,
                overlay_rows=combined_overlay_rows,
                inspection_summary_rows=custom_summary_rows,
                inspection_category_quality_rows=_inspection_category_quality_rows(),
                inspection_top_sku_rows=_inspection_top_sku_rows(),
                inspection_broadness_rows=_inspection_broadness_rows(overlay_rows_count=len(second_overlay_rows)),
                overlay_by_category_rows=_overlay_by_category_rows(second_overlay_rows),
                overlay_quarantine_rows=combined_quarantine_rows,
                rebuild_top_errors_rows=_top_errors_rows(combined_overlay_rows),
                rebuild_review_rows=_retarget_rows(
                    _review_rows(100),
                    promotion_key=SECOND_PROMOTION_KEY,
                    promotion_name=SECOND_PROMOTION_NAME,
                    promotion_start_date=SECOND_PROMOTION_START_DATE,
                    promotion_end_date=SECOND_PROMOTION_END_DATE,
                ) + _review_rows(100),
            )

            with patch.multiple(module, EXPECTED_INPUT_OVERLAY_ROW_COUNT=12, EXPECTED_QUARANTINE_ROW_COUNT=1):
                result = module.build_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root,
                    promotion_key=SECOND_PROMOTION_KEY,
                )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertTrue(result.plan_rows_frame["promotion_key"].astype(str).eq(SECOND_PROMOTION_KEY).all())
            self.assertTrue(result.rejected_rows_frame["promotion_key"].astype(str).eq(SECOND_PROMOTION_KEY).all())
            self.assertEqual(result.quarantine_row_count, 1)

    def test_missing_actuals_are_not_zero_filled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            overlay_rows = _overlay_rows()
            overlay_rows[0]["actual_units"] = ""
            _write_inputs(packet_root, overlay_rows=overlay_rows)

            with patch.object(module, "EXPECTED_INPUT_OVERLAY_ROW_COUNT", 12):
                result = module.build_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root,
                )

            retained_or_rejected = pd.concat(
                [result.plan_rows_frame, result.rejected_rows_frame],
                ignore_index=True,
            )
            selected_row = retained_or_rejected.loc[
                retained_or_rejected["source_row_id"].astype(str).eq("1")
            ].iloc[0]
            self.assertEqual(str(selected_row["actual_units"]), "")

    def test_no_production_or_stage12_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.object(module, "EXPECTED_INPUT_OVERLAY_ROW_COUNT", 12):
                result = module.build_promotions_materialized_source_controlled_overlay_narrowing_plan(
                    packet_root=packet_root,
                )

            retained_or_rejected = pd.concat(
                [result.plan_rows_frame, result.rejected_rows_frame],
                ignore_index=True,
            )
            self.assertTrue(retained_or_rejected["production_order_change_flag"].fillna(0).astype(int).eq(0).all())
            self.assertTrue(retained_or_rejected["stage_12_change_flag"].fillna(0).astype(int).eq(0).all())


if __name__ == "__main__":
    unittest.main()