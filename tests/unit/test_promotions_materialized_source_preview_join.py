from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_preview_join import (  # noqa: E402
    PREVIEW_JOIN_READY_FOR_SCHEMA_MAPPING,
    PREVIEW_JOIN_BLOCKED_DUPLICATE_EXPANSION,
    PREVIEW_JOIN_BLOCKED_MISSING_REQUIRED_SOURCE,
    PromotionsMaterializedSourcePreviewJoinError,
    PREVIEW_JOIN_READY_WITH_QUARANTINE,
    build_promotions_materialized_source_preview_join,
    write_promotions_materialized_source_preview_join,
)


PROMOTION_KEY = "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1"
PROMOTION_NAME = "Allocation Report - WK47&48 WINTER PART 1"
PROMOTION_FOLDER_NAME = "promotion_772-2026-05-21-2026-06-03-allocation-report-wk47-48-winter-part-1"
PROMOTION_START_DATE = "2026-05-21"
PROMOTION_END_DATE = "2026-06-03"

SECOND_PROMOTION_KEY = "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX"
SECOND_PROMOTION_NAME = "Allocation Report - WK45&46 BABY & YOU BOX"
SECOND_PROMOTION_FOLDER_NAME = "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"
SECOND_PROMOTION_START_DATE = "2026-05-07"
SECOND_PROMOTION_END_DATE = "2026-05-20"


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_source_packet(
    packet_root: Path,
    *,
    folder_name: str = PROMOTION_FOLDER_NAME,
    promotion_name: str = PROMOTION_NAME,
    promotion_start_date: str = PROMOTION_START_DATE,
    promotion_end_date: str = PROMOTION_END_DATE,
) -> None:
    packet_folder = packet_root / "source_materialized_promotions" / folder_name
    _write_csv(
        packet_folder / "promotion_source_manifest.csv",
        [
            {
                "source_file_path": "tmp/source_packet.csv",
                "source_file_type": "DECISION_SURFACE",
                "row_count": 4,
                "sku_count": 4,
                "store_number": "772",
                "promotion_name": promotion_name,
                "promotion_start_date": promotion_start_date,
                "promotion_end_date": promotion_end_date,
                "source_discovery_status": "SOURCE_ROW_DISCOVERED",
                "materialization_status": "SOURCE_ROWS_WRITTEN",
                "downstream_full_diagnostic_chain_available_flag": 0,
                "downstream_full_packet_reason": "source only",
                "missing_canonical_fields": "predicted_gross_profit",
            }
        ],
    )
    _write_csv(
        packet_folder / "promotion_source_rows.csv",
        [
            {
                "store_number": "772",
                "promotion_start_date": promotion_start_date,
                "promotion_name": promotion_name,
                "promotion_end_date": promotion_end_date,
                "sku_number": "1001",
                "final_store_order_units": 5,
                "shadow_policy_should_publish_flag": 0,
            },
            {
                "store_number": 772,
                "promotion_start_date": "21/5/2026" if promotion_start_date == PROMOTION_START_DATE else promotion_start_date,
                "promotion_name": promotion_name.lower() if promotion_name == PROMOTION_NAME else promotion_name,
                "promotion_end_date": promotion_end_date,
                "sku_number": "1002",
                "final_store_order_units": 3,
                "shadow_policy_should_publish_flag": 0,
            },
            {
                "store_number": "772.0",
                "promotion_start_date": "2026/05/21" if promotion_start_date == PROMOTION_START_DATE else promotion_start_date,
                "promotion_name": promotion_name,
                "promotion_end_date": promotion_end_date,
                "sku_number": 1003,
                "final_store_order_units": 1,
                "shadow_policy_should_publish_flag": 0,
            },
            {
                "store_number": "772",
                "promotion_start_date": promotion_start_date,
                "promotion_name": promotion_name,
                "promotion_end_date": promotion_end_date,
                "sku_number": "",
                "final_store_order_units": 2,
                "shadow_policy_should_publish_flag": 0,
            },
        ],
    )


def _write_spec_pack_inputs(
    packet_root: Path | None = None,
    actual_source: Path | None = None,
    operator_source: Path | None = None,
    *,
    spec_root: Path | None = None,
    promotion_key: str = PROMOTION_KEY,
    promotion_name: str = PROMOTION_NAME,
    promotion_start_date: str = PROMOTION_START_DATE,
    promotion_end_date: str = PROMOTION_END_DATE,
    spec_status: str = "SPEC_READY_WITH_QUARANTINE",
    include_quarantine: bool = True,
    selected_promotion: str | None = None,
) -> None:
    if spec_root is None:
        if packet_root is None:
            raise ValueError("packet_root or spec_root is required")
        spec_root = packet_root / "materialized_source_join_spec_pack"
    if actual_source is None or operator_source is None:
        raise ValueError("actual_source and operator_source are required")
    selected_promotion_key = selected_promotion or promotion_key
    join_key = "store_number + promotion_start_date + promotion_name + sku_number"
    _write_csv(
        spec_root / "materialized_source_join_spec_summary.csv",
        [
            {
                "metric_name": "SELECTED_PROMOTION",
                "metric_value": selected_promotion_key,
                "metric_display": selected_promotion_key,
                "notes": "selected promotion",
            },
            {
                "metric_name": "SPEC_STATUS",
                "metric_value": spec_status,
                "metric_display": spec_status,
                "notes": "spec status",
            },
        ],
    )
    _write_csv(
        spec_root / "materialized_source_join_spec_sources.csv",
        [
            {
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_start_date": promotion_start_date,
                "promotion_end_date": promotion_end_date,
                "join_source_type": "ACTUAL_OUTCOME",
                "source_file_path": str(actual_source),
                "join_key_columns": join_key,
                "match_rate": 0.75,
                "matched_source_rows": 3,
                "unmatched_source_rows": 1,
                "duplicate_key_count": 0,
                "row_explosion_risk_flag": 0,
                "join_spec_status": spec_status,
                "execution_allowed_flag": 1,
                "execution_block_reason": "quarantine row remains separate",
            },
            {
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_start_date": promotion_start_date,
                "promotion_end_date": promotion_end_date,
                "join_source_type": "OPERATOR_AUDIT",
                "source_file_path": str(operator_source),
                "join_key_columns": join_key,
                "match_rate": 0.75,
                "matched_source_rows": 3,
                "unmatched_source_rows": 1,
                "duplicate_key_count": 0,
                "row_explosion_risk_flag": 0,
                "join_spec_status": spec_status,
                "execution_allowed_flag": 1,
                "execution_block_reason": "quarantine row remains separate",
            },
        ],
    )
    _write_csv(
        spec_root / "materialized_source_join_spec_keys.csv",
        [
            {
                "promotion_key": promotion_key,
                "join_source_type": "ACTUAL_OUTCOME",
                "join_key_columns": join_key,
                "source_row_count": 4,
                "candidate_source_row_count": 3,
                "matched_source_rows": 3,
                "unmatched_source_rows": 1,
                "match_rate": 0.75,
                "join_readiness_status": "JOIN_READY",
                "join_spec_status": spec_status,
                "recommended_for_preview_join_flag": 1,
                "notes": "actual key",
            },
            {
                "promotion_key": promotion_key,
                "join_source_type": "OPERATOR_AUDIT",
                "join_key_columns": join_key,
                "source_row_count": 4,
                "candidate_source_row_count": 3,
                "matched_source_rows": 3,
                "unmatched_source_rows": 1,
                "match_rate": 0.75,
                "join_readiness_status": "JOIN_READY",
                "join_spec_status": spec_status,
                "recommended_for_preview_join_flag": 1,
                "notes": "operator key",
            },
        ],
    )
    quarantine_rows = (
        [
            {
                "source_row_number": 4,
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_start_date": promotion_start_date,
                "promotion_end_date": promotion_end_date,
                "quarantine_reason": "At least one required key field is blank after normalization.",
                "remediation_required": "Populate or remediate the missing join-key fields before any preview join includes this row.",
            }
        ]
        if include_quarantine
        else []
    )
    _write_csv(spec_root / "materialized_source_join_spec_quarantine_rows.csv", quarantine_rows)


def _write_support_sources(
    *,
    actual_source: Path,
    operator_source: Path,
    promotion_name: str = PROMOTION_NAME,
    promotion_start_date: str = PROMOTION_START_DATE,
    actual_rows: list[dict[str, object]] | None = None,
    operator_rows: list[dict[str, object]] | None = None,
) -> None:
    uppercase_name = promotion_name.upper()
    _write_csv(
        actual_source,
        actual_rows
        if actual_rows is not None
        else [
            {
                "store_number": "772",
                "promotion_start_date": promotion_start_date,
                "promotion_name": uppercase_name,
                "sku_number": "1001",
                "actual_gross_profit": 10.0,
            },
            {
                "store_number": "772",
                "promotion_start_date": promotion_start_date,
                "promotion_name": uppercase_name,
                "sku_number": "1002",
                "actual_gross_profit": "",
            },
            {
                "store_number": "772",
                "promotion_start_date": promotion_start_date,
                "promotion_name": uppercase_name,
                "sku_number": "1003",
                "actual_gross_profit": 6.0,
            },
        ],
    )
    _write_csv(
        operator_source,
        operator_rows
        if operator_rows is not None
        else [
            {
                "store_number": "772",
                "promotion_start_date": promotion_start_date,
                "promotion_name": uppercase_name,
                "sku_number": "1001",
                "store_action": "BUY",
            },
            {
                "store_number": "772",
                "promotion_start_date": promotion_start_date,
                "promotion_name": uppercase_name,
                "sku_number": "1002",
                "store_action": "REVIEW",
            },
            {
                "store_number": "772",
                "promotion_start_date": promotion_start_date,
                "promotion_name": uppercase_name,
                "sku_number": "1003",
                "store_action": "BUY",
            },
        ],
    )


def _append_secondary_spec_pack_inputs(spec_root: Path, actual_source: Path, operator_source: Path) -> None:
    def _read_optional_csv(path: Path) -> pd.DataFrame:
        try:
            return pd.read_csv(path, keep_default_na=False)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    summary_frame = pd.read_csv(spec_root / "materialized_source_join_spec_summary.csv")
    sources_frame = pd.read_csv(spec_root / "materialized_source_join_spec_sources.csv")
    keys_frame = pd.read_csv(spec_root / "materialized_source_join_spec_keys.csv")
    quarantine_frame = _read_optional_csv(spec_root / "materialized_source_join_spec_quarantine_rows.csv")

    secondary_root = spec_root / "__secondary__"
    _write_spec_pack_inputs(
        spec_root=secondary_root,
        actual_source=actual_source,
        operator_source=operator_source,
        promotion_key=SECOND_PROMOTION_KEY,
        promotion_name=SECOND_PROMOTION_NAME,
        promotion_start_date=SECOND_PROMOTION_START_DATE,
        promotion_end_date=SECOND_PROMOTION_END_DATE,
        spec_status="SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN",
        include_quarantine=False,
    )
    secondary_sources_frame = pd.read_csv(secondary_root / "materialized_source_join_spec_sources.csv")
    secondary_keys_frame = pd.read_csv(secondary_root / "materialized_source_join_spec_keys.csv")
    secondary_quarantine_frame = _read_optional_csv(
        secondary_root / "materialized_source_join_spec_quarantine_rows.csv"
    )

    _write_csv(spec_root / "materialized_source_join_spec_summary.csv", summary_frame.to_dict("records"))
    _write_csv(
        spec_root / "materialized_source_join_spec_sources.csv",
        pd.concat([sources_frame, secondary_sources_frame], ignore_index=True).to_dict("records"),
    )
    _write_csv(
        spec_root / "materialized_source_join_spec_keys.csv",
        pd.concat([keys_frame, secondary_keys_frame], ignore_index=True).to_dict("records"),
    )
    _write_csv(
        spec_root / "materialized_source_join_spec_quarantine_rows.csv",
        pd.concat([quarantine_frame, secondary_quarantine_frame], ignore_index=True).to_dict("records"),
    )


class PromotionsMaterializedSourcePreviewJoinTests(unittest.TestCase):
    def test_build_preview_join_with_quarantine_conserves_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            _write_source_packet(packet_root)
            _write_spec_pack_inputs(packet_root, actual_source, operator_source)
            _write_csv(
                actual_source,
                [
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1001",
                        "actual_gross_profit": 10.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1002",
                        "actual_gross_profit": "",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1003",
                        "actual_gross_profit": 6.0,
                    },
                ],
            )
            _write_csv(
                operator_source,
                [
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1001",
                        "store_action": "BUY",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1002",
                        "store_action": "REVIEW",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1003",
                        "store_action": "BUY",
                    },
                ],
            )

            result = build_promotions_materialized_source_preview_join(packet_root=packet_root)

            self.assertEqual(result.preview_status, PREVIEW_JOIN_READY_WITH_QUARANTINE)
            self.assertEqual(len(result.joined_rows_frame.index), 3)
            self.assertEqual(len(result.quarantine_rows_frame.index), 1)
            self.assertEqual(len(result.unmatched_rows_frame.index), 0)
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(int(summary_lookup["ROW_COUNT_CONSERVATION_FLAG"]), 1)
            self.assertEqual(int(summary_lookup["CANONICAL_SCHEMA_MAPPING_NEXT_FLAG"]), 1)

    def test_build_preview_join_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            _write_source_packet(packet_root)
            _write_support_sources(actual_source=actual_source, operator_source=operator_source)
            _write_spec_pack_inputs(
                packet_root=packet_root,
                actual_source=actual_source,
                operator_source=operator_source,
                spec_status="SPEC_BLOCKED_MISSING_SOURCE",
                include_quarantine=False,
            )
            _write_spec_pack_inputs(
                spec_root=upstream_root / "materialized_source_join_spec_pack",
                actual_source=actual_source,
                operator_source=operator_source,
            )

            result = build_promotions_materialized_source_preview_join(
                packet_root=packet_root,
                upstream_root=upstream_root,
            )

            self.assertEqual(result.preview_status, PREVIEW_JOIN_READY_WITH_QUARANTINE)
            self.assertEqual(len(result.joined_rows_frame.index), 3)
            self.assertEqual(len(result.quarantine_rows_frame.index), 1)
            self.assertEqual(len(result.unmatched_rows_frame.index), 0)
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(int(summary_lookup["ROW_COUNT_CONSERVATION_FLAG"]), 1)

    def test_build_preview_join_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            _write_source_packet(packet_root)
            _write_support_sources(actual_source=actual_source, operator_source=operator_source)
            _write_spec_pack_inputs(
                packet_root=packet_root,
                actual_source=actual_source,
                operator_source=operator_source,
            )
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(PromotionsMaterializedSourcePreviewJoinError) as error_context:
                build_promotions_materialized_source_preview_join(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_build_preview_join_blocks_when_operator_audit_contract_is_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            _write_source_packet(packet_root)
            _write_support_sources(actual_source=actual_source, operator_source=operator_source)
            _write_spec_pack_inputs(packet_root, actual_source, operator_source)

            spec_sources_path = packet_root / "materialized_source_join_spec_pack" / "materialized_source_join_spec_sources.csv"
            spec_sources_frame = pd.read_csv(spec_sources_path, keep_default_na=False)
            operator_mask = spec_sources_frame["join_source_type"].astype(str).eq("OPERATOR_AUDIT")
            spec_sources_frame.loc[operator_mask, "source_file_path"] = ""
            spec_sources_frame.loc[operator_mask, "join_key_columns"] = ""
            spec_sources_frame.loc[operator_mask, "join_spec_status"] = "SPEC_BLOCKED_MISSING_SOURCE"
            spec_sources_frame.to_csv(spec_sources_path, index=False)

            result = build_promotions_materialized_source_preview_join(packet_root=packet_root)

            self.assertEqual(result.preview_status, PREVIEW_JOIN_BLOCKED_MISSING_REQUIRED_SOURCE)
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(summary_lookup["PREVIEW_STATUS"], PREVIEW_JOIN_BLOCKED_MISSING_REQUIRED_SOURCE)
            preview_status_notes = result.summary_frame.loc[
                result.summary_frame["metric_name"].astype(str).eq("PREVIEW_STATUS"), "notes"
            ].iloc[0]
            self.assertIn("Required OPERATOR_AUDIT source is missing or blank in Stage 2 join-spec artifact", preview_status_notes)

    def test_build_preview_join_still_blocks_nonblank_wrong_approved_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            _write_source_packet(packet_root)
            _write_support_sources(actual_source=actual_source, operator_source=operator_source)
            _write_spec_pack_inputs(packet_root, actual_source, operator_source)

            spec_sources_path = packet_root / "materialized_source_join_spec_pack" / "materialized_source_join_spec_sources.csv"
            spec_sources_frame = pd.read_csv(spec_sources_path, keep_default_na=False)
            operator_mask = spec_sources_frame["join_source_type"].astype(str).eq("OPERATOR_AUDIT")
            spec_sources_frame.loc[operator_mask, "join_key_columns"] = "store_number + promotion_start_date + promotion_name"
            spec_sources_frame.to_csv(spec_sources_path, index=False)

            with self.assertRaises(PromotionsMaterializedSourcePreviewJoinError) as error_context:
                build_promotions_materialized_source_preview_join(packet_root=packet_root)

            self.assertIn("Join source OPERATOR_AUDIT is not using the approved key", str(error_context.exception))

    def test_build_preview_join_blocks_duplicate_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            _write_source_packet(packet_root)
            _write_spec_pack_inputs(packet_root, actual_source, operator_source)
            _write_csv(
                actual_source,
                [
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1001",
                        "actual_gross_profit": 10.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1001",
                        "actual_gross_profit": 11.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1002",
                        "actual_gross_profit": 12.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1003",
                        "actual_gross_profit": 6.0,
                    },
                ],
            )
            _write_csv(
                operator_source,
                [
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1001",
                        "store_action": "BUY",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1002",
                        "store_action": "REVIEW",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1003",
                        "store_action": "BUY",
                    },
                ],
            )

            result = build_promotions_materialized_source_preview_join(packet_root=packet_root)

            self.assertEqual(result.preview_status, PREVIEW_JOIN_BLOCKED_DUPLICATE_EXPANSION)

    def test_build_preview_join_preserves_missing_actuals_and_guardrails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            _write_source_packet(packet_root)
            _write_spec_pack_inputs(packet_root, actual_source, operator_source)
            _write_csv(
                actual_source,
                [
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1001",
                        "actual_gross_profit": "",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1002",
                        "actual_gross_profit": 12.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1003",
                        "actual_gross_profit": 6.0,
                    },
                ],
            )
            _write_csv(
                operator_source,
                [
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1001",
                        "store_action": "BUY",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1002",
                        "store_action": "REVIEW",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1003",
                        "store_action": "BUY",
                    },
                ],
            )

            result = build_promotions_materialized_source_preview_join(packet_root=packet_root)

            preview_rows = result.joined_rows_frame.sort_values(by=["source_row_number"]).reset_index(drop=True)
            self.assertEqual(preview_rows.loc[0, "actual_gross_profit"], "")
            validation_lookup = dict(zip(result.validation_frame["validation_name"], result.validation_frame["validation_status"]))
            self.assertEqual(validation_lookup["MISSING_ACTUALS_NOT_ZERO_FILLED"], "PASS")
            self.assertEqual(validation_lookup["PRODUCTION_GUARDRAIL_STATUS"], "PASS")
            self.assertEqual(validation_lookup["STAGE12_GUARDRAIL_STATUS"], "PASS")

    def test_build_preview_join_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            spec_root = packet_root / "materialized_source_join_spec_pack"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            second_actual_source = Path(tmp_dir) / "support" / "actual_outcome_second.csv"
            second_operator_source = Path(tmp_dir) / "support" / "operator_audit_second.csv"
            _write_source_packet(packet_root)
            _write_source_packet(
                packet_root,
                folder_name=SECOND_PROMOTION_FOLDER_NAME,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            _write_support_sources(actual_source=actual_source, operator_source=operator_source)
            _write_support_sources(
                actual_source=second_actual_source,
                operator_source=second_operator_source,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                actual_rows=[
                    {
                        "store_number": "772",
                        "promotion_start_date": SECOND_PROMOTION_START_DATE,
                        "promotion_name": SECOND_PROMOTION_NAME.upper(),
                        "sku_number": "1001",
                        "actual_gross_profit": 7.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": SECOND_PROMOTION_START_DATE,
                        "promotion_name": SECOND_PROMOTION_NAME.upper(),
                        "sku_number": "1002",
                        "actual_gross_profit": 8.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": SECOND_PROMOTION_START_DATE,
                        "promotion_name": SECOND_PROMOTION_NAME.upper(),
                        "sku_number": "1003",
                        "actual_gross_profit": 9.0,
                    },
                ],
            )
            _write_spec_pack_inputs(
                packet_root=packet_root,
                actual_source=actual_source,
                operator_source=operator_source,
            )
            _append_secondary_spec_pack_inputs(spec_root, second_actual_source, second_operator_source)

            result = build_promotions_materialized_source_preview_join(
                packet_root=packet_root,
                promotion_key=SECOND_PROMOTION_KEY,
            )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertEqual(result.selected_promotion.promotion_name, SECOND_PROMOTION_NAME)
            self.assertEqual(result.preview_status, PREVIEW_JOIN_READY_FOR_SCHEMA_MAPPING)
            self.assertTrue(result.joined_rows_frame["promotion_name"].astype(str).eq(SECOND_PROMOTION_NAME).all())
            self.assertEqual(len(result.quarantine_rows_frame.index), 0)

    def test_write_preview_join_outputs_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            _write_source_packet(packet_root)
            _write_spec_pack_inputs(packet_root, actual_source, operator_source)
            _write_csv(
                actual_source,
                [
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1001",
                        "actual_gross_profit": 10.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1002",
                        "actual_gross_profit": 12.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1003",
                        "actual_gross_profit": 6.0,
                    },
                ],
            )
            _write_csv(
                operator_source,
                [
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1001",
                        "store_action": "BUY",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1002",
                        "store_action": "REVIEW",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1003",
                        "store_action": "BUY",
                    },
                ],
            )

            artifacts = write_promotions_materialized_source_preview_join(packet_root=packet_root)

            self.assertTrue(Path(artifacts.joined_rows_csv_path).exists())
            self.assertTrue(Path(artifacts.quarantine_rows_csv_path).exists())
            self.assertTrue(Path(artifacts.unmatched_rows_csv_path).exists())
            self.assertTrue(Path(artifacts.validation_csv_path).exists())
            self.assertTrue(Path(artifacts.column_lineage_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())

    def test_write_preview_join_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / "materialized_source_preview_join"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            _write_source_packet(packet_root)
            _write_support_sources(actual_source=actual_source, operator_source=operator_source)
            _write_spec_pack_inputs(
                spec_root=upstream_root,
                actual_source=actual_source,
                operator_source=operator_source,
            )

            artifacts = write_promotions_materialized_source_preview_join(
                packet_root=packet_root,
                upstream_root=upstream_root,
                output_root=output_root,
            )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "materialized_source_preview_join_rows.csv").exists())
            self.assertTrue((output_root / "materialized_source_preview_join_validation.csv").exists())


if __name__ == "__main__":
    unittest.main()