from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.runtime.promotions.run_promotions_materialized_source_blank_key_quarantine_sidecar_plan import (
    BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INCOMPLETE,
    BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INVALID,
    BLANK_KEY_QUARANTINE_SIDECAR_NOT_REQUIRED_SOURCE_CORRECTION,
    BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD,
    build_promotions_materialized_source_blank_key_quarantine_sidecar_plan,
    write_promotions_materialized_source_blank_key_quarantine_sidecar_plan,
)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45-46 BABY YOU BOX"


def _build_packet_root(tmp_path: Path, *, decision_checker_status: str) -> Path:
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

    decision_check_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_blank_key_quarantine_decision_check"
    _write_csv(
        decision_check_root / "blank_key_quarantine_decision_check_summary.csv",
        pd.DataFrame(
            [
                {
                    "metric_name": "DECISION_CHECK_STATUS",
                    "metric_value": decision_checker_status,
                    "metric_display": decision_checker_status,
                    "notes": "n",
                }
            ]
        ),
    )
    _write_csv(
        decision_check_root / "blank_key_quarantine_decision_check_rows.csv",
        pd.DataFrame(
            [
                {
                    "promotion_key": _promotion_key(),
                    "source_csv_line_number": 73,
                    "advice_batch_row_number": "147188",
                    "quarantine_decision": "",
                    "row_check_status": decision_checker_status,
                    "missing_approval_fields": "",
                    "decision_target": "",
                    "details": "n",
                }
            ]
        ),
    )

    decision_approval_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_blank_key_quarantine_approval_plan"
    quarantine_decision = ""
    if decision_checker_status == "BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR":
        quarantine_decision = "APPROVE_QUARANTINE"
    elif decision_checker_status == "BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION":
        quarantine_decision = "REQUIRE_SOURCE_CORRECTION"
    elif decision_checker_status == "BLANK_KEY_QUARANTINE_DECISION_INVALID":
        quarantine_decision = "INVALID_VALUE"

    _write_csv(
        decision_approval_root / "blank_key_quarantine_decision_TEMPLATE.csv",
        pd.DataFrame(
            [
                {
                    "promotion_key": _promotion_key(),
                    "source_csv_line_number": 73,
                    "advice_batch_row_number": "147188",
                    "source_file": "07052026_wk45&46_baby&You_box_20052026.csv",
                    "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                    "sku_number": "",
                    "sku_description": "",
                    "blank_key_fields": "sku_number",
                    "recommended_action": "REQUIRE_UPSTREAM_SOURCE_CORRECTION_OR_EXPLICIT_QUARANTINE",
                    "quarantine_decision": quarantine_decision,
                    "quarantine_reason": "r",
                    "approved_by": "a",
                    "approved_timestamp": "2026-06-16T10:30:00Z",
                    "source_correction_available_flag": "0",
                    "notes": "",
                }
            ]
        ),
    )
    return packet_root


def test_incomplete_decision_blocks_sidecar_plan(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_checker_status="BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE")

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.sidecar_plan_status == BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INCOMPLETE


def test_invalid_decision_blocks_sidecar_plan(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_checker_status="BLANK_KEY_QUARANTINE_DECISION_INVALID")

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.sidecar_plan_status == BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INVALID


def test_source_correction_decision_returns_not_required(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_checker_status="BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION")

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.sidecar_plan_status == BLANK_KEY_QUARANTINE_SIDECAR_NOT_REQUIRED_SOURCE_CORRECTION


def test_approved_quarantine_decision_returns_ready_to_build(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_checker_status="BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR")

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.sidecar_plan_status == BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD


def test_planner_writes_required_schema_artifact(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_checker_status="BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE")
    output_root = tmp_path / "output"

    artifacts = write_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
        output_root=output_root,
    )

    assert Path(artifacts.required_schema_csv_path).exists()


def test_planner_does_not_create_governed_operator_audit_file(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_checker_status="BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE")

    build_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    governed_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "operator_audit_source.csv"
    assert not governed_path.exists()


def test_planner_does_not_mutate_source_packets(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_checker_status="BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE")
    source_file = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "promotion_source_rows.csv"
    source_bytes_before = source_file.read_bytes()

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.source_packets_unchanged_flag == 1
    assert source_file.read_bytes() == source_bytes_before


def test_memo_states_sidecar_is_not_built_by_planner(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_checker_status="BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE")

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert "does not build the quarantine sidecar" in result.memo_markdown
