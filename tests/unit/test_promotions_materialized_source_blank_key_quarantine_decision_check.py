from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.runtime.promotions.run_promotions_materialized_source_blank_key_quarantine_decision_check import (
    BLANK_KEY_QUARANTINE_DECISION_BLOCKED_MISSING_FILE,
    BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE,
    BLANK_KEY_QUARANTINE_DECISION_INVALID,
    BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR,
    BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION,
    build_promotions_materialized_source_blank_key_quarantine_decision_check,
)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45-46 BABY YOU BOX"


def _build_packet_root(tmp_path: Path, *, include_decision_file: bool = True, decision_value: str = "", with_required_fields: bool = False) -> Path:
    packet_root = tmp_path / "packet_root"
    source_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions"
    source_folder = source_root / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"
    source_folder.mkdir(parents=True, exist_ok=True)

    _write_csv(
        source_folder / "promotion_source_manifest.csv",
        pd.DataFrame(
            [
                {
                    "store_number": "772",
                    "promotion_start_date": "2026-05-07",
                    "promotion_end_date": "2026-05-20",
                    "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                }
            ]
        ),
    )
    _write_csv(
        source_folder / "promotion_source_rows.csv",
        pd.DataFrame(
            [
                {
                    "store_number": "772",
                    "promotion_start_date": "2026-05-07",
                    "promotional_end_date": "2026-05-20",
                    "sku_number": "",
                    "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                    "sku_description": "",
                    "source_file": "07052026_wk45&46_baby&You_box_20052026.csv",
                    "advice_batch_row_number": "147188",
                    "promotion_row_key": "772|SATURDAY, 28 MARCH 2026 11:52 AM|2026-05-07|2026-05-20|772-SATURDAY, 28 MARCH 2026 11:52 AM-20260507|Allocation Report - WK45&46 BABY & YOU BOX",
                }
            ]
        ),
    )

    if include_decision_file:
        decision_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_blank_key_quarantine_approval_plan"
        row = {
            "promotion_key": _promotion_key(),
            "source_csv_line_number": 73,
            "advice_batch_row_number": "147188",
            "source_file": "07052026_wk45&46_baby&You_box_20052026.csv",
            "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
            "sku_number": "",
            "sku_description": "",
            "blank_key_fields": "sku_number",
            "recommended_action": "REQUIRE_UPSTREAM_SOURCE_CORRECTION_OR_EXPLICIT_QUARANTINE",
            "quarantine_decision": decision_value,
            "quarantine_reason": "",
            "approved_by": "",
            "approved_timestamp": "",
            "source_correction_available_flag": "",
            "notes": "",
        }
        if with_required_fields:
            row["quarantine_reason"] = "Reviewed malformed row evidence."
            row["approved_by"] = "operator@example.com"
            row["approved_timestamp"] = "2026-06-16T10:30:00Z"
            if decision_value == "APPROVE_QUARANTINE":
                row["source_correction_available_flag"] = "0"
        _write_csv(decision_root / "blank_key_quarantine_decision_TEMPLATE.csv", pd.DataFrame([row]))

    return packet_root


def test_blank_decision_returns_incomplete(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_value="", with_required_fields=False)

    result = build_promotions_materialized_source_blank_key_quarantine_decision_check(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.decision_check_status == BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE


def test_approve_quarantine_missing_fields_returns_incomplete(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_value="APPROVE_QUARANTINE", with_required_fields=False)

    result = build_promotions_materialized_source_blank_key_quarantine_decision_check(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.decision_check_status == BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE
    assert "quarantine_reason" in result.check_rows_frame.loc[0, "missing_approval_fields"]
    assert "approved_by" in result.check_rows_frame.loc[0, "missing_approval_fields"]
    assert "approved_timestamp" in result.check_rows_frame.loc[0, "missing_approval_fields"]
    assert "source_correction_available_flag" in result.check_rows_frame.loc[0, "missing_approval_fields"]


def test_approve_quarantine_all_fields_returns_ready_for_quarantine_sidecar(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_value="APPROVE_QUARANTINE", with_required_fields=True)

    result = build_promotions_materialized_source_blank_key_quarantine_decision_check(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.decision_check_status == BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR


def test_require_source_correction_all_fields_returns_ready_for_source_correction(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_value="REQUIRE_SOURCE_CORRECTION", with_required_fields=True)

    result = build_promotions_materialized_source_blank_key_quarantine_decision_check(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.decision_check_status == BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION


def test_invalid_decision_value_returns_invalid(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_value="DROP_ROW_ANYWAY", with_required_fields=True)

    result = build_promotions_materialized_source_blank_key_quarantine_decision_check(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.decision_check_status == BLANK_KEY_QUARANTINE_DECISION_INVALID


def test_missing_decision_file_blocks_cleanly(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_decision_file=False)

    result = build_promotions_materialized_source_blank_key_quarantine_decision_check(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.decision_check_status == BLANK_KEY_QUARANTINE_DECISION_BLOCKED_MISSING_FILE


def test_checker_does_not_create_governed_operator_audit_file(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_value="", with_required_fields=False)

    build_promotions_materialized_source_blank_key_quarantine_decision_check(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    governed_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "operator_audit_source.csv"
    assert not governed_path.exists()


def test_checker_does_not_mutate_source_packets(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_value="", with_required_fields=False)
    source_file = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "promotion_source_rows.csv"
    source_bytes_before = source_file.read_bytes()

    result = build_promotions_materialized_source_blank_key_quarantine_decision_check(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.source_packets_unchanged_flag == 1
    assert source_file.read_bytes() == source_bytes_before
