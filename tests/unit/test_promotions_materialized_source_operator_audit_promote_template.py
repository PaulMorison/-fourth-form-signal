from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.runtime.promotions.run_promotions_materialized_source_operator_audit_promote_template import (
    OPERATOR_AUDIT_PROMOTION_READY,
    OPERATOR_AUDIT_TEMPLATE_PROMOTED,
    OPERATOR_AUDIT_TEMPLATE_PROMOTION_BLOCKED_BLANK_JOIN_KEYS,
    OPERATOR_AUDIT_TEMPLATE_PROMOTION_BLOCKED_DESTINATION_EXISTS,
    OPERATOR_AUDIT_TEMPLATE_PROMOTION_BLOCKED_NOT_READY,
    OPERATOR_AUDIT_TEMPLATE_PROMOTION_BLOCKED_ROW_COUNT_MISMATCH,
    OPERATOR_AUDIT_TEMPLATE_PROMOTION_BLOCKED_TEMPLATE_MISSING,
    build_promotions_materialized_source_operator_audit_promote_template,
    write_promotions_materialized_source_operator_audit_promote_template,
)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45-46 BABY YOU BOX"


def _build_packet_root(
    tmp_path: Path,
    *,
    readiness_status: str = OPERATOR_AUDIT_PROMOTION_READY,
    include_template: bool = True,
    blank_sku_in_template: bool = False,
    candidate_row_count: int = 1,
    template_rows: int = 1,
    quarantined_row_count: int = 1,
    include_quarantine_evidence: bool = True,
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

    readiness_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_operator_audit_promotion_readiness"
    _write_csv(
        readiness_root / "operator_audit_promotion_readiness_summary.csv",
        pd.DataFrame(
            [
                {"metric_name": "READINESS_STATUS", "metric_value": readiness_status, "metric_display": readiness_status, "notes": "n"},
            ]
        ),
    )
    _write_csv(
        readiness_root / "operator_audit_promotion_readiness_candidate.csv",
        pd.DataFrame(
            [
                {
                    "promotion_key": _promotion_key(),
                    "promotion_folder_name": "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box",
                    "template_status_used": "OPERATOR_AUDIT_TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE",
                    "template_source_path": str(packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_operator_audit_template" / "operator_audit_source_TEMPLATE.csv"),
                    "quarantine_evidence_path": str(packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_operator_audit_template" / "operator_audit_template_quarantine_evidence.csv"),
                    "sidecar_path": str(packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_blank_key_quarantine_sidecar_build" / "blank_key_quarantine_sidecar.csv"),
                    "future_governed_destination_path": str(source_folder / "operator_audit_source.csv"),
                    "source_row_count": 2,
                    "template_row_count": candidate_row_count,
                    "quarantined_row_count": quarantined_row_count,
                    "readiness_status": readiness_status,
                }
            ]
        ),
    )

    template_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_operator_audit_template"
    if include_template:
        template_frame = pd.DataFrame(
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
        )
        if template_rows == 2:
            template_frame = pd.concat([template_frame, template_frame.assign(sku_number="189226", sku_description="Second Row")], ignore_index=True)
        _write_csv(template_root / "operator_audit_source_TEMPLATE.csv", template_frame)
    if include_quarantine_evidence:
        _write_csv(
            template_root / "operator_audit_template_quarantine_evidence.csv",
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

    if create_governed_file:
        (source_folder / "operator_audit_source.csv").write_text("already exists\n", encoding="utf-8")

    return packet_root


def test_promotes_template_only_when_readiness_is_ready(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    result = build_promotions_materialized_source_operator_audit_promote_template(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.promotion_status == OPERATOR_AUDIT_TEMPLATE_PROMOTED
    assert result.readiness_status_used == OPERATOR_AUDIT_PROMOTION_READY
    assert Path(result.governed_destination_path).exists()


def test_blocks_when_readiness_is_not_ready(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, readiness_status="OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_NOT_READY")

    result = build_promotions_materialized_source_operator_audit_promote_template(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.promotion_status == OPERATOR_AUDIT_TEMPLATE_PROMOTION_BLOCKED_NOT_READY
    assert not Path(result.governed_destination_path).exists()


def test_blocks_when_template_is_missing(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_template=False)

    result = build_promotions_materialized_source_operator_audit_promote_template(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.promotion_status == OPERATOR_AUDIT_TEMPLATE_PROMOTION_BLOCKED_TEMPLATE_MISSING


def test_blocks_when_template_has_blank_join_keys(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, blank_sku_in_template=True)

    result = build_promotions_materialized_source_operator_audit_promote_template(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.promotion_status == OPERATOR_AUDIT_TEMPLATE_PROMOTION_BLOCKED_BLANK_JOIN_KEYS


def test_blocks_on_row_count_mismatch(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, candidate_row_count=2, template_rows=1)

    result = build_promotions_materialized_source_operator_audit_promote_template(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.promotion_status == OPERATOR_AUDIT_TEMPLATE_PROMOTION_BLOCKED_ROW_COUNT_MISMATCH


def test_blocks_if_governed_destination_already_exists(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, create_governed_file=True)
    governed_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "operator_audit_source.csv"
    before = governed_path.read_text(encoding="utf-8")

    result = build_promotions_materialized_source_operator_audit_promote_template(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.promotion_status == OPERATOR_AUDIT_TEMPLATE_PROMOTION_BLOCKED_DESTINATION_EXISTS
    assert governed_path.read_text(encoding="utf-8") == before


def test_creates_exactly_one_governed_operator_audit_source_csv(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)
    source_folder = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"

    build_promotions_materialized_source_operator_audit_promote_template(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    matches = list(source_folder.glob("operator_audit_source.csv"))
    assert len(matches) == 1


def test_does_not_mutate_promotion_source_rows_csv(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)
    source_rows_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "promotion_source_rows.csv"
    before = source_rows_path.read_bytes()

    result = build_promotions_materialized_source_operator_audit_promote_template(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.source_packets_unchanged_flag == 1
    assert source_rows_path.read_bytes() == before


def test_manifest_records_template_destination_row_count_and_timestamp(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    artifacts = write_promotions_materialized_source_operator_audit_promote_template(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )
    manifest_frame = pd.read_csv(artifacts.manifest_csv_path, keep_default_na=False, low_memory=False)

    assert manifest_frame.loc[0, "source_template_path"].endswith("operator_audit_source_TEMPLATE.csv")
    assert manifest_frame.loc[0, "governed_destination_path"].endswith("operator_audit_source.csv")
    assert int(manifest_frame.loc[0, "promoted_row_count"]) == 1
    assert manifest_frame.loc[0, "promoted_timestamp"]


def test_memo_states_controlled_operator_audit_promotion_only(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)

    result = build_promotions_materialized_source_operator_audit_promote_template(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert "Controlled OPERATOR_AUDIT promotion step only." in result.memo_markdown
