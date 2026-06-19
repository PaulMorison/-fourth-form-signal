from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.runtime.promotions.run_promotions_materialized_source_blank_key_remediation_plan import (
    BLANK_KEY_REMEDIATION_BLOCKED_MISSING_SOURCE_ROWS,
    BLANK_KEY_REMEDIATION_NOT_REQUIRED,
    BLANK_KEY_REMEDIATION_REQUIRED,
    RECOMMENDED_ACTION,
    build_promotions_materialized_source_blank_key_remediation_plan,
    write_promotions_materialized_source_blank_key_remediation_plan,
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
    blank_sku: bool = True,
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
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-07",
                "promotional_end_date": "2026-05-20",
                "sku_number": "189226",
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                "sku_description": "Example Product",
                "source_file": "07052026_wk45&46_baby&You_box_20052026.csv",
                "advice_batch_row_number": "147189",
                "promotion_row_key": "772|189226|2026-05-07|2026-05-20|772-189226-20260507|Allocation Report - WK45&46 BABY & YOU BOX",
            },
        ]
        if not blank_sku:
            rows[1]["sku_number"] = "189225"
            rows[1]["sku_description"] = "Blank SKU replacement example"
        _write_csv(source_folder / "promotion_source_rows.csv", pd.DataFrame(rows))

    _write_csv(
        source_folder / "promotion_source_summary.csv",
        pd.DataFrame([{ "metric_name": "X", "metric_value": 1, "metric_display": "1", "notes": "n" }]),
    )
    return packet_root


def test_detects_one_blank_sku(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, blank_sku=True)

    result = build_promotions_materialized_source_blank_key_remediation_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.remediation_status == BLANK_KEY_REMEDIATION_REQUIRED
    assert result.blank_key_row_count == 1
    assert result.remediation_rows_frame.loc[0, "source_csv_line_number"] == 3
    assert result.remediation_rows_frame.loc[0, "advice_batch_row_number"] == "147188"
    assert result.remediation_rows_frame.loc[0, "recommended_action"] == RECOMMENDED_ACTION
    assert "corrected upstream or explicitly quarantined" in result.remediation_rows_frame.loc[0, "reason"]


def test_writes_blank_key_rows_artifact(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, blank_sku=True)
    output_root = tmp_path / "output"

    artifacts = write_promotions_materialized_source_blank_key_remediation_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
        output_root=output_root,
    )

    assert Path(artifacts.blank_key_rows_csv_path).exists()
    assert Path(artifacts.blank_key_recommended_actions_csv_path).exists()
    assert Path(artifacts.summary_csv_path).exists()
    assert Path(artifacts.remediation_validation_csv_path).exists()
    assert Path(artifacts.memo_md_path).exists()


def test_does_not_mutate_source_rows(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, blank_sku=True)
    source_file = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "promotion_source_rows.csv"
    source_bytes_before = source_file.read_bytes()

    result = build_promotions_materialized_source_blank_key_remediation_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.source_packets_unchanged_flag == 1
    assert source_file.read_bytes() == source_bytes_before


def test_does_not_create_governed_operator_audit_file(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, blank_sku=True)

    build_promotions_materialized_source_blank_key_remediation_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    governed_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "operator_audit_source.csv"
    assert not governed_path.exists()


def test_missing_source_rows_blocks_cleanly(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, include_source_rows=False)

    result = build_promotions_materialized_source_blank_key_remediation_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.remediation_status == BLANK_KEY_REMEDIATION_BLOCKED_MISSING_SOURCE_ROWS
    assert result.blank_key_row_count == 0


def test_no_blank_keys_returns_not_required(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, blank_sku=False)

    result = build_promotions_materialized_source_blank_key_remediation_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert result.remediation_status == BLANK_KEY_REMEDIATION_NOT_REQUIRED
    assert result.blank_key_row_count == 0


def test_memo_states_no_auto_fill_and_no_silent_exclusion(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path, blank_sku=True)

    result = build_promotions_materialized_source_blank_key_remediation_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )

    assert "No auto-fill and no silent exclusion are permitted." in result.memo_markdown
    assert "explicitly quarantined" in result.memo_markdown
