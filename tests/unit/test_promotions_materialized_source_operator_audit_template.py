from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.runtime.promotions.run_promotions_materialized_source_operator_audit_template import (
    APPROVED_JOIN_KEY,
    LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME,
    QUARANTINE_EVIDENCE_FILE_NAME,
    REVIEW_TEMPLATE_FILE_NAME,
    TEMPLATE_BLOCKED_BLANK_KEYS,
    TEMPLATE_BLOCKED_MISSING_COLUMNS,
    TEMPLATE_BLOCKED_MISSING_SOURCE_ROWS,
    TEMPLATE_EXCLUSION_STATUS,
    TEMPLATE_READY,
    TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE,
    build_promotions_materialized_source_operator_audit_template,
    write_promotions_materialized_source_operator_audit_template,
)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45-46 BABY YOU BOX"


def _build_packet_root(
    tmp_path: Path,
    *,
    include_source_rows: bool = True,
    include_required_columns: bool = True,
    include_blank_row: bool = False,
    include_valid_sidecar: bool = False,
    sidecar_status: str = "QUARANTINED_FOR_OPERATOR_AUDIT",
    sidecar_line_number: int = 73,
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

    if include_source_rows:
        rows = [
            {
                "source_csv_line_number": 72,
                "store_number": "772",
                "promotion_start_date": "2026-05-07",
                "promotional_end_date": "2026-05-20",
                "sku_number": "189225",
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                "sku_description": "Rev Cs Suede Ink Gut Instinct",
                "source_file": "07052026_wk45&46_baby&You_box_20052026.csv",
                "advice_batch_row_number": "147187",
            }
        ]
        if include_blank_row:
            rows.append(
                {
                    "source_csv_line_number": 73,
                    "store_number": "772",
                    "promotion_start_date": "2026-05-07",
                    "promotional_end_date": "2026-05-20",
                    "sku_number": "",
                    "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                    "sku_description": "",
                    "source_file": "07052026_wk45&46_baby&You_box_20052026.csv",
                    "advice_batch_row_number": "147188",
                }
            )
        if not include_required_columns:
            for row in rows:
                row.pop("promotion_name", None)
                row.pop("sku_description", None)
        _write_csv(source_folder / "promotion_source_rows.csv", pd.DataFrame(rows))

    _write_csv(
        source_folder / "promotion_source_summary.csv",
        pd.DataFrame([{"metric_name": "X", "metric_value": 1, "metric_display": "1", "notes": "n"}]),
    )

    if include_valid_sidecar:
        _write_csv(
            packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_blank_key_quarantine_sidecar_build" / "blank_key_quarantine_sidecar.csv",
            pd.DataFrame(
                [
                    {
                        "promotion_key": _promotion_key(),
                        "source_csv_line_number": sidecar_line_number,
                        "advice_batch_row_number": "147188",
                        "source_file": "07052026_wk45&46_baby&You_box_20052026.csv",
                        "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                        "sku_number": "",
                        "sku_description": "",
                        "blank_key_fields": "sku_number",
                        "quarantine_decision": "APPROVE_QUARANTINE",
                        "quarantine_reason": "No recoverable SKU.",
                        "approved_by": "Paul Morison",
                        "approved_timestamp": "2026-06-15T23:57:04Z",
                        "source_correction_available_flag": "0",
                        "sidecar_status": sidecar_status,
                        "sidecar_created_timestamp": "2026-06-16T00:16:19Z",
                    }
                ]
            ),
        )

    return packet_root


def test_template_writes_to_review_folder_not_governed_path(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    result = write_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.output_root.endswith("materialized_source_operator_audit_template")
    assert Path(result.template_csv_path).name == REVIEW_TEMPLATE_FILE_NAME
    assert Path(result.quarantine_evidence_csv_path).name == QUARANTINE_EVIDENCE_FILE_NAME
    assert Path(result.template_csv_path).exists()
    assert not (
        packet_root
        / "tmp"
        / "last5_promotions_diagnostic_packets"
        / "source_materialized_promotions"
        / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"
        / LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME
    ).exists()


def test_template_has_required_schema(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.template_status == TEMPLATE_READY
    assert result.template_frame.columns.tolist() == [
        "store_number",
        "promotion_start_date",
        "promotion_end_date",
        "promotion_name",
        "sku_number",
        "sku_description",
        "operator_audit_status",
        "operator_audit_decision",
        "operator_audit_reason",
        "operator_audit_timestamp",
        "operator_audit_user",
        "approved_join_key",
    ]
    assert result.template_frame.loc[0, "operator_audit_status"] == "PENDING_OPERATOR_REVIEW"
    assert result.template_frame.loc[0, "approved_join_key"] == APPROVED_JOIN_KEY


def test_template_blocks_missing_source_rows(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_source_rows=False)

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.template_status == TEMPLATE_BLOCKED_MISSING_SOURCE_ROWS
    assert result.template_rows_count == 0


def test_template_blocks_missing_required_columns(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_required_columns=False)

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.template_status == TEMPLATE_BLOCKED_MISSING_COLUMNS


def test_without_sidecar_blank_sku_still_blocks(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_blank_row=True)

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.template_status == TEMPLATE_BLOCKED_BLANK_KEYS
    assert result.quarantined_row_count == 0
    assert result.sidecar_consumed_flag == 0


def test_with_valid_sidecar_blank_row_is_excluded_from_review_template(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_blank_row=True, include_valid_sidecar=True)

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.template_status == TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE
    assert result.source_row_count == 2
    assert result.template_row_count == 1
    assert result.quarantined_row_count == 1
    assert result.template_frame["sku_number"].astype(str).map(str.strip).ne("").all()


def test_with_valid_sidecar_quarantine_evidence_artifact_is_written(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_blank_row=True, include_valid_sidecar=True)

    artifacts = write_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())
    evidence_frame = pd.read_csv(artifacts.quarantine_evidence_csv_path, keep_default_na=False, low_memory=False)

    assert len(evidence_frame.index) == 1
    assert evidence_frame.loc[0, "template_exclusion_status"] == TEMPLATE_EXCLUSION_STATUS


def test_template_status_becomes_ready_with_quarantine_evidence(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_blank_row=True, include_valid_sidecar=True)

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.template_status == TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE


def test_template_row_count_equals_source_minus_quarantined_row_count(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_blank_row=True, include_valid_sidecar=True)

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.template_row_count == result.source_row_count - result.quarantined_row_count


def test_source_packets_are_not_mutated(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_blank_row=True, include_valid_sidecar=True)
    source_file = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "promotion_source_rows.csv"
    source_bytes_before = source_file.read_bytes()

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.source_packets_unchanged_flag == 1
    assert source_file.read_bytes() == source_bytes_before


def test_governed_operator_audit_file_is_not_created(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_blank_row=True, include_valid_sidecar=True)

    build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    governed_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME
    assert not governed_path.exists()


def test_invalid_sidecar_status_does_not_unblock(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_blank_row=True, include_valid_sidecar=True, sidecar_status="PENDING_REVIEW")

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.template_status == TEMPLATE_BLOCKED_BLANK_KEYS
    assert result.sidecar_consumed_flag == 0


def test_sidecar_row_mismatch_does_not_unblock(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_blank_row=True, include_valid_sidecar=True, sidecar_line_number=999)

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.template_status == TEMPLATE_BLOCKED_BLANK_KEYS
    assert result.sidecar_consumed_flag == 0


def test_no_rows_are_silently_excluded_without_sidecar_evidence(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_blank_row=True)

    result = build_promotions_materialized_source_operator_audit_template(packet_root=packet_root, promotion_key=_promotion_key())

    assert result.template_status == TEMPLATE_BLOCKED_BLANK_KEYS
    assert result.template_row_count == result.source_row_count
    assert result.quarantine_evidence_frame.empty