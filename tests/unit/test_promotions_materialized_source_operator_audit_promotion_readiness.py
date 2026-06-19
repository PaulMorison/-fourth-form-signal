from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.runtime.promotions.run_promotions_materialized_source_operator_audit_promotion_readiness import (
    OPERATOR_AUDIT_PROMOTION_BLOCKED_BLANK_JOIN_KEYS,
    OPERATOR_AUDIT_PROMOTION_BLOCKED_GOVERNED_FILE_ALREADY_EXISTS,
    OPERATOR_AUDIT_PROMOTION_BLOCKED_QUARANTINE_EVIDENCE_MISMATCH,
    OPERATOR_AUDIT_PROMOTION_BLOCKED_ROW_COUNT_MISMATCH,
    OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_MISSING,
    OPERATOR_AUDIT_PROMOTION_READY,
    build_promotions_materialized_source_operator_audit_promotion_readiness,
    write_promotions_materialized_source_operator_audit_promotion_readiness,
)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45-46 BABY YOU BOX"


def _build_packet_root(
    tmp_path: Path,
    *,
    include_template: bool = True,
    template_status: str = "OPERATOR_AUDIT_TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE",
    blank_sku_in_template: bool = False,
    template_row_count_metric: int = 1,
    source_row_count_metric: int = 2,
    quarantined_row_count_metric: int = 1,
    evidence_advice_batch_row_number: str = "147188",
    sidecar_advice_batch_row_number: str = "147188",
    create_governed_file: bool = False,
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
                    "source_csv_line_number": 72,
                    "store_number": "772",
                    "promotion_start_date": "2026-05-07",
                    "promotional_end_date": "2026-05-20",
                    "sku_number": "189225",
                    "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                    "sku_description": "Rev Cs Suede Ink Gut Instinct",
                    "source_file": "07052026_wk45&46_baby&You_box_20052026.csv",
                    "advice_batch_row_number": "147187",
                },
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
                },
            ]
        ),
    )

    template_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_operator_audit_template"
    _write_csv(
        template_root / "operator_audit_template_summary.csv",
        pd.DataFrame(
            [
                {"metric_name": "TEMPLATE_STATUS", "metric_value": template_status, "metric_display": template_status, "notes": "n"},
                {"metric_name": "SOURCE_ROW_COUNT", "metric_value": source_row_count_metric, "metric_display": str(source_row_count_metric), "notes": "n"},
                {"metric_name": "TEMPLATE_ROW_COUNT", "metric_value": template_row_count_metric, "metric_display": str(template_row_count_metric), "notes": "n"},
                {"metric_name": "QUARANTINED_ROW_COUNT", "metric_value": quarantined_row_count_metric, "metric_display": str(quarantined_row_count_metric), "notes": "n"},
            ]
        ),
    )
    if include_template:
        _write_csv(
            template_root / "operator_audit_source_TEMPLATE.csv",
            pd.DataFrame(
                [
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-07",
                        "promotion_end_date": "2026-05-20",
                        "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                        "sku_number": "" if blank_sku_in_template else "189225",
                        "sku_description": "Rev Cs Suede Ink Gut Instinct",
                        "operator_audit_status": "PENDING_OPERATOR_REVIEW",
                        "operator_audit_decision": "",
                        "operator_audit_reason": "",
                        "operator_audit_timestamp": "",
                        "operator_audit_user": "",
                        "approved_join_key": "store_number + promotion_start_date + promotion_name + sku_number",
                    }
                ]
            ),
        )
    _write_csv(
        template_root / "operator_audit_template_quarantine_evidence.csv",
        pd.DataFrame(
            [
                {
                    "promotion_key": _promotion_key(),
                    "source_csv_line_number": 73,
                    "advice_batch_row_number": evidence_advice_batch_row_number,
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
                    "sidecar_status": "QUARANTINED_FOR_OPERATOR_AUDIT",
                    "sidecar_created_timestamp": "2026-06-16T00:16:19Z",
                    "template_exclusion_status": "EXCLUDED_FROM_OPERATOR_AUDIT_TEMPLATE_BY_GOVERNED_SIDECAR",
                }
            ]
        ),
    )

    sidecar_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_blank_key_quarantine_sidecar_build"
    _write_csv(
        sidecar_root / "blank_key_quarantine_sidecar.csv",
        pd.DataFrame(
            [
                {
                    "promotion_key": _promotion_key(),
                    "source_csv_line_number": 73,
                    "advice_batch_row_number": sidecar_advice_batch_row_number,
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
                    "sidecar_status": "QUARANTINED_FOR_OPERATOR_AUDIT",
                    "sidecar_created_timestamp": "2026-06-16T00:16:19Z",
                }
            ]
        ),
    )

    if create_governed_file:
        (source_folder / "operator_audit_source.csv").write_text("already exists\n", encoding="utf-8")

    return packet_root


def test_ready_template_with_quarantine_evidence_returns_ready(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    result = build_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.readiness_status == OPERATOR_AUDIT_PROMOTION_READY


def test_missing_template_blocks(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_template=False)

    result = build_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.readiness_status == OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_MISSING


def test_template_with_blank_sku_blocks(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, blank_sku_in_template=True)

    result = build_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.readiness_status == OPERATOR_AUDIT_PROMOTION_BLOCKED_BLANK_JOIN_KEYS


def test_row_count_mismatch_blocks(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, template_row_count_metric=2)

    result = build_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.readiness_status == OPERATOR_AUDIT_PROMOTION_BLOCKED_ROW_COUNT_MISMATCH


def test_quarantine_evidence_mismatch_blocks(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, evidence_advice_batch_row_number="999999")

    result = build_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.readiness_status == OPERATOR_AUDIT_PROMOTION_BLOCKED_QUARANTINE_EVIDENCE_MISMATCH


def test_existing_governed_file_blocks_but_is_not_overwritten(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, create_governed_file=True)
    governed_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "operator_audit_source.csv"
    before = governed_path.read_text(encoding="utf-8")

    result = build_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.readiness_status == OPERATOR_AUDIT_PROMOTION_BLOCKED_GOVERNED_FILE_ALREADY_EXISTS
    assert governed_path.read_text(encoding="utf-8") == before


def test_planner_does_not_create_governed_operator_audit_file(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    build_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    governed_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "operator_audit_source.csv"
    assert not governed_path.exists()


def test_planner_does_not_mutate_source_packets(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)
    source_file = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "promotion_source_rows.csv"
    source_bytes_before = source_file.read_bytes()

    result = build_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.source_packets_unchanged_flag == 1
    assert source_file.read_bytes() == source_bytes_before


def test_candidate_artifact_contains_template_and_future_destination_paths(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)
    artifacts = write_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )
    candidate_frame = pd.read_csv(artifacts.candidate_csv_path, keep_default_na=False, low_memory=False)

    assert candidate_frame.loc[0, "template_source_path"].endswith("operator_audit_source_TEMPLATE.csv")
    assert candidate_frame.loc[0, "future_governed_destination_path"].endswith("operator_audit_source.csv")


def test_memo_states_readiness_only_and_no_promotion(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    result = build_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert "readiness artifact" in result.memo_markdown.lower()
    assert "No promotion is performed" in result.memo_markdown