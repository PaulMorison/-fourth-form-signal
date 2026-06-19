from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.runtime.promotions.run_promotions_materialized_source_blank_key_quarantine_approval_plan import (
    BLANK_KEY_QUARANTINE_APPROVAL_BLOCKED_MISSING_REMEDIATION_ROWS,
    BLANK_KEY_QUARANTINE_APPROVAL_NOT_REQUIRED,
    BLANK_KEY_QUARANTINE_APPROVAL_REQUIRED,
    build_promotions_materialized_source_blank_key_quarantine_approval_plan,
    write_promotions_materialized_source_blank_key_quarantine_approval_plan,
)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45-46 BABY YOU BOX"


def _build_packet_root(
    tmp_path: Path,
    *,
    include_remediation_rows: bool = True,
    include_blank_row: bool = True,
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
                    "sku_number": "189225",
                    "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                    "sku_description": "Rev Cs Suede Ink Gut Instinct",
                    "source_file": "07052026_wk45&46_baby&You_box_20052026.csv",
                    "advice_batch_row_number": "147187",
                    "promotion_row_key": "772|189225|2026-05-07|2026-05-20|772-189225-20260507|Allocation Report - WK45&46 BABY & YOU BOX",
                },
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
                },
            ]
        ),
    )

    remediation_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_blank_key_remediation_plan"
    if include_remediation_rows:
        if include_blank_row:
            blank_rows = pd.DataFrame(
                [
                    {
                        "source_csv_line_number": 73,
                        "store_number": "772",
                        "promotion_start_date": "2026-05-07",
                        "promotion_end_date_or_promotional_end_date": "2026-05-20",
                        "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                        "sku_number": "",
                        "sku_description": "",
                        "source_file": "07052026_wk45&46_baby&You_box_20052026.csv",
                        "advice_batch_row_number": "147188",
                        "promotion_row_key": "772|SATURDAY, 28 MARCH 2026 11:52 AM|2026-05-07|2026-05-20|772-SATURDAY, 28 MARCH 2026 11:52 AM-20260507|Allocation Report - WK45&46 BABY & YOU BOX",
                        "surrounding_row_context": "line=72 ... ; line=73 ... ; line=74 ...",
                        "structural_row_likelihood": "LOW",
                        "merchandise_row_likelihood": "MEDIUM",
                        "recommended_action": "REQUIRE_UPSTREAM_SOURCE_CORRECTION_OR_EXPLICIT_QUARANTINE",
                        "reason": "Blank join-key fields block governed OPERATOR_AUDIT template generation; this row should be corrected upstream or explicitly quarantined.",
                    }
                ]
            )
        else:
            blank_rows = pd.DataFrame(
                columns=[
                    "source_csv_line_number",
                    "store_number",
                    "promotion_start_date",
                    "promotion_end_date_or_promotional_end_date",
                    "promotion_name",
                    "sku_number",
                    "sku_description",
                    "source_file",
                    "advice_batch_row_number",
                    "promotion_row_key",
                    "surrounding_row_context",
                    "structural_row_likelihood",
                    "merchandise_row_likelihood",
                    "recommended_action",
                    "reason",
                ]
            )
        _write_csv(remediation_root / "blank_key_rows.csv", blank_rows)
        _write_csv(
            remediation_root / "blank_key_recommended_actions.csv",
            pd.DataFrame(
                [
                    {
                        "source_csv_line_number": 73,
                        "promotion_row_key": "772|SATURDAY, 28 MARCH 2026 11:52 AM|2026-05-07|2026-05-20|772-SATURDAY, 28 MARCH 2026 11:52 AM-20260507|Allocation Report - WK45&46 BABY & YOU BOX",
                        "recommended_action": "REQUIRE_UPSTREAM_SOURCE_CORRECTION_OR_EXPLICIT_QUARANTINE",
                        "reason": "Blank join-key fields block governed OPERATOR_AUDIT template generation; this row should be corrected upstream or explicitly quarantined.",
                    }
                ]
            ),
        )
    return packet_root


def test_writes_one_decision_template_row_for_blank_sku(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_remediation_rows=True, include_blank_row=True)

    result = build_promotions_materialized_source_blank_key_quarantine_approval_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.quarantine_approval_status == BLANK_KEY_QUARANTINE_APPROVAL_REQUIRED
    assert result.decision_row_count == 1
    assert result.decision_template_frame.loc[0, "source_csv_line_number"] == 73
    assert result.decision_template_frame.loc[0, "advice_batch_row_number"] == "147188"


def test_leaves_decision_fields_blank(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_remediation_rows=True, include_blank_row=True)

    result = build_promotions_materialized_source_blank_key_quarantine_approval_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    row = result.decision_template_frame.iloc[0]
    assert row["quarantine_decision"] == ""
    assert row["quarantine_reason"] == ""
    assert row["approved_by"] == ""
    assert row["approved_timestamp"] == ""
    assert row["source_correction_available_flag"] == ""
    assert row["notes"] == ""


def test_does_not_mutate_source_rows(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_remediation_rows=True, include_blank_row=True)
    source_file = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "promotion_source_rows.csv"
    source_bytes_before = source_file.read_bytes()

    result = build_promotions_materialized_source_blank_key_quarantine_approval_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.source_packets_unchanged_flag == 1
    assert source_file.read_bytes() == source_bytes_before


def test_does_not_create_governed_operator_audit_file(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_remediation_rows=True, include_blank_row=True)

    build_promotions_materialized_source_blank_key_quarantine_approval_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    governed_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "operator_audit_source.csv"
    assert not governed_path.exists()


def test_missing_remediation_rows_blocks_cleanly(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_remediation_rows=False)

    result = build_promotions_materialized_source_blank_key_quarantine_approval_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.quarantine_approval_status == BLANK_KEY_QUARANTINE_APPROVAL_BLOCKED_MISSING_REMEDIATION_ROWS
    assert result.decision_row_count == 0


def test_no_blank_rows_returns_not_required_status(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_remediation_rows=True, include_blank_row=False)

    result = build_promotions_materialized_source_blank_key_quarantine_approval_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.quarantine_approval_status == BLANK_KEY_QUARANTINE_APPROVAL_NOT_REQUIRED
    assert result.decision_row_count == 0


def test_memo_prohibits_auto_fill_and_silent_exclusion(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_remediation_rows=True, include_blank_row=True)

    result = build_promotions_materialized_source_blank_key_quarantine_approval_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert "Silent exclusion and SKU auto-fill are prohibited." in result.memo_markdown
    assert "Upstream correction is preferred if a true SKU can be recovered." in result.memo_markdown


def test_writes_required_artifacts(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_remediation_rows=True, include_blank_row=True)
    output_root = tmp_path / "output"

    artifacts = write_promotions_materialized_source_blank_key_quarantine_approval_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
        output_root=output_root,
    )

    assert Path(artifacts.summary_csv_path).exists()
    assert Path(artifacts.decision_template_csv_path).exists()
    assert Path(artifacts.validation_csv_path).exists()
    assert Path(artifacts.memo_md_path).exists()
