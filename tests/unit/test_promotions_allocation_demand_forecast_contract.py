from __future__ import annotations

import pandas as pd

from models.promotions.allocation_demand_forecast_contract import (
    BASIS_BASELINE_UPLIFT,
    BASIS_INVENTORY_INTEGRITY_CONTAMINATED,
    BASIS_MODEL_PREDICTION,
    BASIS_REVIEW,
    BASIS_STOCK_CONSTRAINED_HISTORY,
    CONFIDENCE_REVIEW,
    CUSTOMER_READY_TINY_MODEL_DEMAND_SHARE_THRESHOLD,
    DEMAND_COLLAPSE_RISK_WARNING,
    DEMAND_CONFIDENCE_LEVELS,
    MODEL_DEMAND_COLLAPSED_WARNING,
    DemandForecastInputRow,
    build_demand_forecast_contract_frame,
    compute_demand_forecast_row,
    customer_ready_blocked_by_tiny_model_demand,
    validate_demand_forecast_contract_frame,
)
from surfaces.promotions.reporting.allocation_stock_contract import (
    build_allocation_stock_contract_frame,
    validate_allocation_stock_contract_frame,
)


def _row(**overrides: object) -> DemandForecastInputRow:
    base = {
        "model_run_date": "2026-05-20",
        "promotion_start_date": "2026-06-01",
        "promotion_end_date": "2026-06-14",
        "baseline_daily_units": 1.0,
        "promo_uplift_factor": 2.0,
        "model_promo_window_units": 8.0,
        "confidence_fraction": 0.7,
    }
    base.update(overrides)
    return DemandForecastInputRow(**base)  # type: ignore[arg-type]


def test_case_1_pre_promo_demand_from_run_to_start() -> None:
    result = compute_demand_forecast_row(
        _row(baseline_daily_units=2.0, model_promo_window_units=10.0)
    )
    assert result["days_until_promo_start"] == 12
    # 2 units/day * 12 days lead-up
    assert result["pre_promo_demand_units"] == 24


def test_case_2_promo_window_demand_is_separate_from_pre_promo() -> None:
    result = compute_demand_forecast_row(
        _row(baseline_daily_units=2.0, model_promo_window_units=10.0)
    )
    assert result["promo_window_demand_units"] == 10
    assert result["pre_promo_demand_units"] == 24
    assert result["promo_window_demand_units"] != result["pre_promo_demand_units"]


def test_case_3_total_demand_equals_pre_plus_promo() -> None:
    result = compute_demand_forecast_row(
        _row(baseline_daily_units=2.0, model_promo_window_units=10.0)
    )
    assert (
        result["total_expected_demand_units"]
        == result["pre_promo_demand_units"] + result["promo_window_demand_units"]
    )


def test_case_4_missing_model_demand_routes_to_review_not_zero() -> None:
    result = compute_demand_forecast_row(
        DemandForecastInputRow(
            model_run_date="2026-05-20",
            promotion_start_date="2026-06-01",
            promotion_end_date="2026-06-14",
            baseline_daily_units=0.0,
            model_promo_window_units=None,
        )
    )
    assert result["demand_forecast_basis"] == BASIS_REVIEW
    assert result["demand_forecast_confidence"] == CONFIDENCE_REVIEW
    assert result["demand_forecast_reason_code"] == "REVIEW_DEMAND_FORECAST"
    assert result["demand_forecast_warning"] != ""


def test_case_5_positive_promo_demand_never_no_demand() -> None:
    result = compute_demand_forecast_row(
        _row(model_promo_window_units=6.0)
    )
    assert result["promo_window_demand_units"] > 0
    assert "NO_DEMAND" not in result["demand_forecast_basis"]
    assert result["demand_forecast_basis"] == BASIS_MODEL_PREDICTION


def test_case_6_stock_constrained_history_changes_basis_and_warns() -> None:
    constrained = compute_demand_forecast_row(
        _row(model_promo_window_units=10.0, soh_zero_in_comparable_promo=True)
    )
    unconstrained = compute_demand_forecast_row(
        _row(model_promo_window_units=10.0, soh_zero_in_comparable_promo=False)
    )
    assert constrained["demand_forecast_basis"] == BASIS_STOCK_CONSTRAINED_HISTORY
    assert constrained["stock_constraint_flag"] is True
    assert constrained["stock_constraint_adjustment_units"] > 0
    # Stock-constrained demand must not be lower than unconstrained estimate.
    assert constrained["promo_window_demand_units"] >= unconstrained["promo_window_demand_units"]


def test_case_7_negative_soh_marks_inventory_contamination() -> None:
    result = compute_demand_forecast_row(
        _row(model_promo_window_units=10.0, negative_soh_detected=True)
    )
    assert result["demand_forecast_basis"] == BASIS_INVENTORY_INTEGRITY_CONTAMINATED
    assert result["stock_constraint_flag"] is True
    assert result["demand_forecast_warning"] != ""


def test_case_8_quantiles_are_monotonic() -> None:
    result = compute_demand_forecast_row(
        _row(model_promo_window_units=10.0, confidence_fraction=0.2)
    )
    q50 = result["demand_forecast_units_q50"]
    q70 = result["demand_forecast_units_q70"]
    q85 = result["demand_forecast_units_q85"]
    q95 = result["demand_forecast_units_q95"]
    assert q50 <= q70 <= q85 <= q95
    # Low confidence should widen spread.
    assert q95 > q50


def test_case_8b_high_confidence_narrows_spread() -> None:
    low = compute_demand_forecast_row(_row(model_promo_window_units=20.0, confidence_fraction=0.1))
    high = compute_demand_forecast_row(_row(model_promo_window_units=20.0, confidence_fraction=0.95))
    low_spread = low["demand_forecast_units_q95"] - low["demand_forecast_units_q50"]
    high_spread = high["demand_forecast_units_q95"] - high["demand_forecast_units_q50"]
    assert high_spread < low_spread


def test_case_9_selected_quantile_maps_to_selected_units() -> None:
    result = compute_demand_forecast_row(
        _row(model_promo_window_units=10.0, high_stockout_cost=True, confidence_fraction=0.95)
    )
    selected_quantile = result["selected_demand_quantile"]
    selected_units = result["selected_demand_units"]
    assert selected_units == result[f"demand_forecast_units_{selected_quantile}"]


def test_case_10_high_stockout_cost_selects_higher_quantile() -> None:
    high_cost = compute_demand_forecast_row(
        _row(model_promo_window_units=10.0, high_stockout_cost=True, confidence_fraction=0.95)
    )
    baseline = compute_demand_forecast_row(
        _row(model_promo_window_units=10.0, confidence_fraction=0.95)
    )
    assert high_cost["selected_demand_quantile"] in {"q85", "q95"}
    assert high_cost["selected_demand_units"] >= baseline["selected_demand_units"]


def test_case_11_high_capital_drag_weak_evidence_stays_conservative() -> None:
    result = compute_demand_forecast_row(
        _row(
            model_promo_window_units=10.0,
            high_stockout_cost=True,
            high_capital_drag=True,
            sparse_or_weak_evidence=True,
            confidence_fraction=0.3,
        )
    )
    assert result["selected_demand_quantile"] == "q50"
    assert result["selected_demand_units"] == result["demand_forecast_units_q50"]


def test_case_12_stage11_integration_preserves_stock_identities() -> None:
    demand_frame = build_demand_forecast_contract_frame(
        model_run_date="2026-05-20",
        promotion_start_date=pd.Series(["2026-06-01", "2026-06-01", "2026-06-01"]),
        promotion_end_date=pd.Series(["2026-06-14", "2026-06-14", "2026-06-14"]),
        baseline_daily_units=pd.Series([2.0, 1.0, 0.0]),
        promo_uplift_factor=pd.Series([2.0, 1.5, 1.0]),
        model_promo_window_units=pd.Series([8.0, None, None]),
        confidence_fraction=pd.Series([0.8, 0.5, 0.2]),
    )
    demand_summary, demand_issues = validate_demand_forecast_contract_frame(demand_frame)
    assert demand_summary.rows_failing_total_demand_identity == 0
    assert demand_summary.rows_failing_quantile_monotonicity == 0
    assert demand_summary.rows_with_negative_units == 0
    assert demand_issues.empty

    stock_frame = build_allocation_stock_contract_frame(
        model_run_date="2026-05-20",
        promotion_start_date=pd.Series(["2026-06-01", "2026-06-01", "2026-06-01"]),
        promotion_end_date=pd.Series(["2026-06-14", "2026-06-14", "2026-06-14"]),
        current_soh_at_model_run=pd.Series([30.0, 10.0, 5.0]),
        confirmed_inbound_units_before_promo_start=pd.Series([0.0, 0.0, 0.0]),
        expected_pre_promo_demand_units=demand_frame["pre_promo_demand_units"],
        expected_promo_window_demand_units=demand_frame["selected_demand_units"],
        floor_units_required_at_promo_start=pd.Series([2.0, 2.0, 2.0]),
    )
    stock_summary, stock_issues = validate_allocation_stock_contract_frame(stock_frame)
    assert stock_summary.rows_failing_stock_identity == 0
    assert stock_summary.rows_failing_target_identity == 0
    assert stock_summary.rows_failing_total_demand_identity == 0
    assert stock_issues.empty


def test_case_13_demand_collapse_emits_warning_when_feature_signal_higher() -> None:
    result = compute_demand_forecast_row(
        _row(model_promo_window_units=1.0, confidence_fraction=0.7, feature_demand_signal=30.0)
    )
    assert result["promo_window_demand_units"] == 1
    assert DEMAND_COLLAPSE_RISK_WARNING in result["demand_forecast_warning"]


def test_case_14_demand_collapse_guard_does_not_auto_inflate() -> None:
    with_signal = compute_demand_forecast_row(
        _row(model_promo_window_units=1.0, confidence_fraction=0.7, feature_demand_signal=50.0)
    )
    without_signal = compute_demand_forecast_row(
        _row(model_promo_window_units=1.0, confidence_fraction=0.7)
    )
    # The feature signal must NOT change the numeric demand, only warn.
    assert with_signal["promo_window_demand_units"] == without_signal["promo_window_demand_units"]
    assert with_signal["selected_demand_units"] == without_signal["selected_demand_units"]
    assert with_signal["total_expected_demand_units"] == without_signal["total_expected_demand_units"]


def test_case_15_demand_collapse_leaves_selected_visible_with_warning() -> None:
    result = compute_demand_forecast_row(
        _row(model_promo_window_units=0.0, confidence_fraction=0.5, feature_demand_signal=12.0)
    )
    # Selected demand stays as forecast (collapse is surfaced, not hidden).
    assert result["selected_demand_units"] <= 1
    assert DEMAND_COLLAPSE_RISK_WARNING in result["demand_forecast_warning"]


def test_case_15b_no_collapse_warning_when_feature_signal_not_higher() -> None:
    healthy = compute_demand_forecast_row(
        _row(model_promo_window_units=10.0, confidence_fraction=0.7, feature_demand_signal=12.0)
    )
    no_signal = compute_demand_forecast_row(
        _row(model_promo_window_units=1.0, confidence_fraction=0.7)
    )
    low_feature = compute_demand_forecast_row(
        _row(model_promo_window_units=1.0, confidence_fraction=0.7, feature_demand_signal=2.0)
    )
    assert DEMAND_COLLAPSE_RISK_WARNING not in healthy["demand_forecast_warning"]
    assert DEMAND_COLLAPSE_RISK_WARNING not in no_signal["demand_forecast_warning"]
    assert DEMAND_COLLAPSE_RISK_WARNING not in low_feature["demand_forecast_warning"]


def test_case_16_validation_detects_demand_collapse_without_failing_invariants() -> None:
    frame = build_demand_forecast_contract_frame(
        model_run_date="2026-05-20",
        promotion_start_date=pd.Series(["2026-06-01", "2026-06-01"]),
        promotion_end_date=pd.Series(["2026-06-14", "2026-06-14"]),
        baseline_daily_units=pd.Series([0.0, 0.0]),
        model_promo_window_units=pd.Series([1.0, 20.0]),
        confidence_fraction=pd.Series([0.7, 0.7]),
        feature_demand_signal=pd.Series([40.0, 25.0]),
    )
    summary, issues = validate_demand_forecast_contract_frame(frame)
    assert summary.rows_with_demand_collapse_risk == 1
    # Collapse risk is diagnostic only: hard invariants must still pass.
    assert summary.rows_failing_total_demand_identity == 0
    assert summary.rows_failing_quantile_monotonicity == 0
    assert summary.rows_with_negative_units == 0
    assert (issues["issue_type"] == "demand_collapse_risk").sum() == 1


def test_validation_detects_injected_violations() -> None:
    frame = build_demand_forecast_contract_frame(
        model_run_date="2026-05-20",
        promotion_start_date=pd.Series(["2026-06-01", "2026-06-01"]),
        promotion_end_date=pd.Series(["2026-06-14", "2026-06-14"]),
        baseline_daily_units=pd.Series([2.0, 1.0]),
        model_promo_window_units=pd.Series([8.0, 6.0]),
        confidence_fraction=pd.Series([0.8, 0.8]),
    )
    frame.loc[0, "total_expected_demand_units"] = 99999
    frame.loc[1, "demand_forecast_units_q95"] = 0
    frame.loc[1, "demand_forecast_reason_code"] = ""
    summary, issues = validate_demand_forecast_contract_frame(frame)
    assert summary.rows_failing_total_demand_identity == 1
    assert summary.rows_failing_quantile_monotonicity == 1
    assert summary.rows_with_missing_reason_code == 1
    assert not issues.empty


def test_confidence_values_are_within_closed_set() -> None:
    frame = build_demand_forecast_contract_frame(
        model_run_date="2026-05-20",
        promotion_start_date=pd.Series(["2026-06-01", "2026-06-01", "2026-06-01"]),
        promotion_end_date=pd.Series(["2026-06-14", "2026-06-14", "2026-06-14"]),
        baseline_daily_units=pd.Series([2.0, 1.0, 0.0]),
        model_promo_window_units=pd.Series([8.0, None, None]),
        confidence_fraction=pd.Series([0.9, 0.5, 0.2]),
    )
    assert set(frame["demand_forecast_confidence"]).issubset(DEMAND_CONFIDENCE_LEVELS)


def test_integerize_does_not_floor_subunit_demand_for_contract_input() -> None:
    result = compute_demand_forecast_row(_row(model_promo_window_units=0.0528))
    assert result["promo_window_demand_units"] == 0.0528
    assert result["selected_demand_units"] == 0.0528
    assert result["demand_forecast_units_q50"] == 0.0528
    assert result["demand_forecast_basis"] == BASIS_MODEL_PREDICTION


def test_tiny_calibrated_demand_emits_model_demand_collapsed_warning() -> None:
    result = compute_demand_forecast_row(_row(model_promo_window_units=0.0528))
    assert MODEL_DEMAND_COLLAPSED_WARNING in result["demand_forecast_warning"]


def test_customer_ready_blocked_when_many_tiny_model_demands() -> None:
    tiny_frame = build_demand_forecast_contract_frame(
        model_run_date="2026-05-20",
        promotion_start_date=pd.Series(["2026-06-01"] * 100),
        promotion_end_date=pd.Series(["2026-06-14"] * 100),
        baseline_daily_units=pd.Series([0.0] * 100),
        model_promo_window_units=pd.Series([0.05] * 80 + [12.0] * 20),
        confidence_fraction=pd.Series([0.7] * 100),
    )
    healthy_frame = build_demand_forecast_contract_frame(
        model_run_date="2026-05-20",
        promotion_start_date=pd.Series(["2026-06-01"] * 100),
        promotion_end_date=pd.Series(["2026-06-14"] * 100),
        baseline_daily_units=pd.Series([0.0] * 100),
        model_promo_window_units=pd.Series([12.0] * 100),
        confidence_fraction=pd.Series([0.7] * 100),
    )
    assert customer_ready_blocked_by_tiny_model_demand(tiny_frame)
    assert not customer_ready_blocked_by_tiny_model_demand(healthy_frame)
    summary, _ = validate_demand_forecast_contract_frame(tiny_frame)
    assert summary.rows_with_model_demand_collapsed_warning == 80
    assert summary.rows_with_tiny_model_demand >= 80
    assert 80 / 100 >= CUSTOMER_READY_TINY_MODEL_DEMAND_SHARE_THRESHOLD
