from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.runtime.promotions.run_promotions_materialized_source_blank_key_quarantine_sidecar_build import (
    BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_DECISION_NOT_APPROVED,
    BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_NOT_READY,
    BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_ROW_COUNT_MISMATCH,
    BLANK_KEY_QUARANTINE_SIDECAR_BUILT,
    SIDECAR_ROW_STATUS,
    build_promotions_materialized_source_blank_key_quarantine_sidecar_build,
    write_promotions_materialized_source_blank_key_quarantine_sidecar_build,
)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45-46 BABY YOU BOX"


def _build_packet_root(
    tmp_path: Path,
    *,
    sidecar_plan_status: str = "BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD",
    decision_checker_status: str = "BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR",
    decision_value: str = "APPROVE_QUARANTINE",
    include_candidate_row: bool = True,
    include_decision_row: bool = True,
) -> Path:
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

    sidecar_plan_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_blank_key_quarantine_sidecar_plan"
    _write_csv(
        sidecar_plan_root / "blank_key_quarantine_sidecar_plan_summary.csv",
        pd.DataFrame(
            [
                {"metric_name": "SIDECAR_PLAN_STATUS", "metric_value": sidecar_plan_status, "metric_display": sidecar_plan_status, "notes": "n"},
                {"metric_name": "DECISION_CHECKER_STATUS", "metric_value": decision_checker_status, "metric_display": decision_checker_status, "notes": "n"},
            ]
        ),
    )
    _write_csv(
        sidecar_plan_root / "blank_key_quarantine_sidecar_candidate_rows.csv",
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
                    "quarantine_decision": decision_value,
                    "quarantine_reason": "r",
                    "approved_by": "Paul Morison",
                    "approved_timestamp": "2026-06-15T23:57:04Z",
                    "source_correction_available_flag": "0",
                    "sidecar_status": "",
                    "sidecar_created_timestamp": "",
                }
            ]
            if include_candidate_row
            else [],
            columns=[
                "promotion_key",
                "source_csv_line_number",
                "advice_batch_row_number",
                "source_file",
                "promotion_name",
                "sku_number",
                "sku_description",
                "blank_key_fields",
                "quarantine_decision",
                "quarantine_reason",
                "approved_by",
                "approved_timestamp",
                "source_correction_available_flag",
                "sidecar_status",
                "sidecar_created_timestamp",
            ],
        ),
    )

    decision_check_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_blank_key_quarantine_decision_check"
    _write_csv(
        decision_check_root / "blank_key_quarantine_decision_check_rows.csv",
        pd.DataFrame(
            [
                {
                    "promotion_key": _promotion_key(),
                    "source_csv_line_number": 73,
                    "advice_batch_row_number": "147188",
                    "quarantine_decision": decision_value,
                    "row_check_status": decision_checker_status,
                    "missing_approval_fields": "",
                    "decision_target": decision_checker_status,
                    "details": "n",
                }
            ]
            if include_decision_row
            else [],
            columns=[
                "promotion_key",
                "source_csv_line_number",
                "advice_batch_row_number",
                "quarantine_decision",
                "row_check_status",
                "missing_approval_fields",
                "decision_target",
                "details",
            ],
        ),
    )

    decision_approval_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_blank_key_quarantine_approval_plan"
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
                    "quarantine_decision": decision_value,
                    "quarantine_reason": "r",
                    "approved_by": "Paul Morison",
                    "approved_timestamp": "2026-06-15T23:57:04Z",
                    "source_correction_available_flag": "0",
                    "notes": "n",
                }
            ]
            if include_decision_row
            else [],
            columns=[
                "promotion_key",
                "source_csv_line_number",
                "advice_batch_row_number",
                "source_file",
                "promotion_name",
                "sku_number",
                "sku_description",
                "blank_key_fields",
                "recommended_action",
                "quarantine_decision",
                "quarantine_reason",
                "approved_by",
                "approved_timestamp",
                "source_correction_available_flag",
                "notes",
            ],
        ),
    )
    return packet_root


def test_builds_sidecar_only_when_plan_ready(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.sidecar_build_status == BLANK_KEY_QUARANTINE_SIDECAR_BUILT
    assert len(result.sidecar_frame.index) == 1


def test_blocks_when_sidecar_plan_not_ready(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, sidecar_plan_status="BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INCOMPLETE")

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.sidecar_build_status == BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_NOT_READY
    assert result.sidecar_frame.empty


def test_blocks_when_decision_not_approve_quarantine(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, decision_value="REQUIRE_SOURCE_CORRECTION")

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.sidecar_build_status == BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_DECISION_NOT_APPROVED


def test_blocks_on_row_count_mismatch(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_decision_row=False)

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.sidecar_build_status == BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_ROW_COUNT_MISMATCH


def test_sidecar_preserves_blank_sku_fields(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    row = result.sidecar_frame.iloc[0]
    assert row["sku_number"] == ""
    assert row["sku_description"] == ""


def test_sidecar_writes_quarantined_status(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.sidecar_frame.iloc[0]["sidecar_status"] == SIDECAR_ROW_STATUS


def test_does_not_mutate_source_rows(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)
    source_file = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "promotion_source_rows.csv"
    source_bytes_before = source_file.read_bytes()

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.source_packets_unchanged_flag == 1
    assert source_file.read_bytes() == source_bytes_before


def test_does_not_create_governed_operator_audit_file(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    governed_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "operator_audit_source.csv"
    assert not governed_path.exists()


def test_memo_states_evidence_only_and_no_operator_audit_promotion(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert "evidence only" in result.memo_markdown
    assert "does not promote OPERATOR_AUDIT" in result.memo_markdown


def test_writes_required_artifacts(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)
    output_root = tmp_path / "output"

    artifacts = write_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
        output_root=output_root,
    )

    assert Path(artifacts.sidecar_csv_path).exists()
    assert Path(artifacts.summary_csv_path).exists()
    assert Path(artifacts.validation_csv_path).exists()
    assert Path(artifacts.memo_md_path).exists()