from __future__ import annotations

import pandas as pd
import pytest

from surfaces.promotions.reporting.allocation_stock_contract import (
    AllocationStockContractRow,
    apply_allocation_order_blockers,
    build_allocation_stock_contract_frame,
    compose_contract_audit_notes,
    compute_allocation_stock_contract_row,
    validate_allocation_stock_contract_frame,
)


def _row(**overrides: object) -> AllocationStockContractRow:
    base = {
        "model_run_date": "2026-05-20",
        "promotion_start_date": "2026-06-01",
        "promotion_end_date": "2026-06-14",
        "days_until_promo_start": 12,
        "promo_window_days": 14,
        "current_soh_at_model_run": 0.0,
        "confirmed_inbound_units_before_promo_start": 0.0,
        "expected_pre_promo_demand_units": 0.0,
        "expected_promo_window_demand_units": 0.0,
        "floor_units_required_at_promo_start": 2.0,
    }
    base.update(overrides)
    return AllocationStockContractRow(**base)  # type: ignore[arg-type]


def test_case_1_stock_gap_drives_order_units() -> None:
    result = compute_allocation_stock_contract_row(
        _row(
            current_soh_at_model_run=10,
            expected_pre_promo_demand_units=3,
            expected_promo_window_demand_units=8,
            floor_units_required_at_promo_start=2,
        )
    )
    assert result["projected_soh_at_promo_start_before_order"] == 7
    assert result["target_soh_at_promo_start"] == 10
    assert result["raw_stock_gap_units"] == 3
    assert result["recommended_order_units"] == 3
    assert result["projected_soh_at_promo_start_after_order"] == 10
    assert result["projected_soh_at_promo_end_after_order"] == 2
    assert result["total_expected_demand_model_run_to_promo_end_units"] == 11


def test_case_2_no_gap_when_stock_covers_target() -> None:
    result = compute_allocation_stock_contract_row(
        _row(
            current_soh_at_model_run=20,
            expected_pre_promo_demand_units=2,
            expected_promo_window_demand_units=5,
            floor_units_required_at_promo_start=2,
        )
    )
    assert result["projected_soh_at_promo_start_before_order"] == 18
    assert result["target_soh_at_promo_start"] == 7
    assert result["raw_stock_gap_units"] == 0
    assert result["recommended_order_units"] == 0
    assert result["projected_soh_at_promo_end_after_order"] == 13
    assert result["total_expected_demand_model_run_to_promo_end_units"] == 7


def test_case_3_large_gap_orders_unless_hard_blocker() -> None:
    result = compute_allocation_stock_contract_row(
        _row(
            current_soh_at_model_run=1,
            expected_pre_promo_demand_units=2,
            expected_promo_window_demand_units=9,
            floor_units_required_at_promo_start=2,
        )
    )
    assert result["projected_soh_at_promo_start_before_order"] == 0
    assert result["target_soh_at_promo_start"] == 11
    assert result["raw_stock_gap_units"] == 11
    assert result["recommended_order_units"] == 11
    assert result["total_expected_demand_model_run_to_promo_end_units"] == 11

    contract = build_allocation_stock_contract_frame(
        model_run_date="2026-05-20",
        promotion_start_date=pd.Series(["2026-06-01"]),
        promotion_end_date=pd.Series(["2026-06-14"]),
        current_soh_at_model_run=pd.Series([1.0]),
        confirmed_inbound_units_before_promo_start=pd.Series([0.0]),
        expected_pre_promo_demand_units=pd.Series([2.0]),
        expected_promo_window_demand_units=pd.Series([9.0]),
        floor_units_required_at_promo_start=pd.Series([2.0]),
    )
    blocked = apply_allocation_order_blockers(
        contract_frame=contract,
        hard_blocker_codes=pd.Series(["blocked_by_sparse_history"]),
    )
    assert int(blocked.loc[0, "recommended_order_units"]) == 0
    assert blocked.loc[0, "order_reason_code"] == "blocked_by_sparse_history"


def test_case_4_zero_promo_demand_allows_no_demand_label() -> None:
    result = compute_allocation_stock_contract_row(
        _row(
            current_soh_at_model_run=10,
            expected_promo_window_demand_units=0,
            floor_units_required_at_promo_start=2,
        )
    )
    assert result["raw_stock_gap_units"] == 0
    assert result["recommended_order_units"] == 0
    notes = compose_contract_audit_notes(
        order_reason_code="",
        expected_promo_window_demand_units=0.0,
        demand_evidence_label="NO_DEMAND",
        stock_position_status=str(result["stock_position_status"]),
        raw_stock_gap_units=float(result["raw_stock_gap_units"]),
        recommended_order_units=float(result["recommended_order_units"]),
    )
    assert "demand=NO_DEMAND" in notes


def test_case_5_positive_promo_demand_never_reports_no_demand() -> None:
    notes = compose_contract_audit_notes(
        order_reason_code="",
        expected_promo_window_demand_units=5.0,
        demand_evidence_label="NO_DEMAND",
        stock_position_status="SHORT_AT_PROMO_START",
        raw_stock_gap_units=3.0,
        recommended_order_units=3.0,
    )
    assert "demand=NO_DEMAND" not in notes
    assert "demand=PROMO_DEMAND_PRESENT" in notes


def test_validation_catches_identity_failures() -> None:
    frame = build_allocation_stock_contract_frame(
        model_run_date="2026-05-20",
        promotion_start_date=pd.Series(["2026-06-01", "2026-06-01"]),
        promotion_end_date=pd.Series(["2026-06-14", "2026-06-14"]),
        current_soh_at_model_run=pd.Series([10.0, 20.0]),
        confirmed_inbound_units_before_promo_start=pd.Series([0.0, 0.0]),
        expected_pre_promo_demand_units=pd.Series([3.0, 2.0]),
        expected_promo_window_demand_units=pd.Series([8.0, 5.0]),
        floor_units_required_at_promo_start=pd.Series([2.0, 2.0]),
    )
    frame.loc[0, "projected_soh_at_promo_start_before_order"] = 999
    frame["audit_notes"] = "demand=NO_DEMAND"
    frame["priority_band"] = "BUY_NOW"
    frame["operator_action"] = "DO_NOT_BUY"
    summary, issues = validate_allocation_stock_contract_frame(frame)
    assert summary.rows_failing_stock_identity == 1
    assert summary.rows_with_no_demand_label_but_positive_demand == 1
    assert summary.rows_with_buy_now_but_do_not_buy == 1
    assert not issues.empty


def test_pack_size_rounds_up_recommended_order_units() -> None:
    result = compute_allocation_stock_contract_row(
        _row(
            current_soh_at_model_run=0,
            expected_promo_window_demand_units=10,
            floor_units_required_at_promo_start=0,
            pack_size=6,
        )
    )
    assert result["raw_stock_gap_units"] == 10
    assert result["recommended_order_units"] == 12
