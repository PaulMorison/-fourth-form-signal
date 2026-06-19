from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_join_key_validator import (  # noqa: E402
    JOIN_BLOCKED_ROW_EXPLOSION_RISK,
    JOIN_READY,
    JOIN_READY_WITH_DUPLICATE_REVIEW,
    JOIN_SOURCE_NOT_AVAILABLE,
    build_promotions_materialized_source_join_key_validator,
    write_promotions_materialized_source_join_key_validator,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_source_packet(packet_root: Path) -> str:
    folder_name = "promotion_772-2026-05-21-2026-06-03-winter-part-1"
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
                "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
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
                "promotion_start_date": "2026-05-21",
                "promotion_name": " Allocation Report  -  WK47&48 WINTER   PART 1 ",
                "sku_number": "1001.0",
                "source_metric": 1,
            },
            {
                "store_number": 772,
                "promotion_start_date": "21/5/2026",
                "promotion_name": "allocation report - wk47&48 winter part 1",
                "sku_number": "1002",
                "source_metric": 2,
            },
            {
                "store_number": "772.0",
                "promotion_start_date": "2026/05/21",
                "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
                "sku_number": 1003,
                "source_metric": 3,
            },
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-21",
                "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
                "sku_number": "1004",
                "source_metric": 4,
            },
        ],
    )
    return folder_name


def _write_queue_inputs(packet_root: Path, actual_source: Path, operator_source: Path) -> None:
    queue_root = packet_root / "materialized_source_rebuild_queue"
    _write_csv(
        queue_root / "materialized_source_rebuild_queue_by_promotion.csv",
        [
            {
                "promotion_priority_rank": 1,
                "promotion_key": "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
                "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
                "queue_row_count": 8,
                "actual_outcome_join_required_flag": 1,
                "actual_outcome_join_candidate_flag": 1,
                "operator_audit_join_required_flag": 1,
                "operator_audit_join_candidate_flag": 1,
                "schema_mapping_required_flag": 1,
                "blocked_flag": 1,
                "potentially_ready_after_joins_flag": 1,
                "first_required_action": "VALIDATE_JOIN_KEY_COVERAGE",
                "source_file_path": "tmp/source_packet.csv",
                "recommended_next_step": "Validate joins.",
                "reason": "diagnostics only",
            }
        ],
    )
    _write_csv(
        queue_root / "materialized_source_join_execution_plan.csv",
        [
            {
                "promotion_priority_rank": 1,
                "promotion_key": "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
                "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
                "required_action": "JOIN_ACTUAL_OUTCOME_SOURCE",
                "action_status": "WAITING_FOR_PRIOR_STEP",
                "blocking_flag": 0,
                "source_file_path": "tmp/source_packet.csv",
                "candidate_join_source_path": str(actual_source),
                "join_key_columns": "store_number; promotion_start_date; promotion_name; sku_number",
                "missing_fields_addressed": "actual_gross_profit",
                "expected_output": "join spec",
                "recommended_next_step": "Validate join keys first.",
                "reason": "actuals join",
            },
            {
                "promotion_priority_rank": 1,
                "promotion_key": "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
                "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
                "required_action": "JOIN_OPERATOR_AUDIT_SOURCE",
                "action_status": "WAITING_FOR_PRIOR_STEP",
                "blocking_flag": 0,
                "source_file_path": "tmp/source_packet.csv",
                "candidate_join_source_path": str(operator_source),
                "join_key_columns": "store_number; promotion_start_date; promotion_name; sku_number",
                "missing_fields_addressed": "store_action; demand_evidence_label",
                "expected_output": "join spec",
                "recommended_next_step": "Validate join keys first.",
                "reason": "operator join",
            },
        ],
    )


def _write_promotion_scoped_operator_audit(packet_root: Path, folder_name: str) -> Path:
    operator_path = packet_root / "source_materialized_promotions" / folder_name / "operator_audit_source.csv"
    _write_csv(
        operator_path,
        [
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
                "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                "sku_number": "1001",
                "sku_description": "Item 1001",
                "operator_audit_status": "PENDING_OPERATOR_REVIEW",
                "operator_audit_decision": "",
                "operator_audit_reason": "",
                "operator_audit_timestamp": "",
                "operator_audit_user": "",
                "approved_join_key": "store_number + promotion_start_date + promotion_name + sku_number",
            },
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
                "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                "sku_number": "1002",
                "sku_description": "Item 1002",
                "operator_audit_status": "PENDING_OPERATOR_REVIEW",
                "operator_audit_decision": "",
                "operator_audit_reason": "",
                "operator_audit_timestamp": "",
                "operator_audit_user": "",
                "approved_join_key": "store_number + promotion_start_date + promotion_name + sku_number",
            },
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
                "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                "sku_number": "1003",
                "sku_description": "Item 1003",
                "operator_audit_status": "PENDING_OPERATOR_REVIEW",
                "operator_audit_decision": "",
                "operator_audit_reason": "",
                "operator_audit_timestamp": "",
                "operator_audit_user": "",
                "approved_join_key": "store_number + promotion_start_date + promotion_name + sku_number",
            },
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
                "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                "sku_number": "1004",
                "sku_description": "Item 1004",
                "operator_audit_status": "PENDING_OPERATOR_REVIEW",
                "operator_audit_decision": "",
                "operator_audit_reason": "",
                "operator_audit_timestamp": "",
                "operator_audit_user": "",
                "approved_join_key": "store_number + promotion_start_date + promotion_name + sku_number",
            },
        ],
    )
    return operator_path


class PromotionsMaterializedSourceJoinKeyValidatorTests(unittest.TestCase):
    def test_uses_promotion_scoped_governed_operator_audit_when_queue_path_is_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"

            folder_name = _write_source_packet(packet_root)
            _write_queue_inputs(packet_root, actual_source, operator_source)
            join_plan_path = packet_root / "materialized_source_rebuild_queue" / "materialized_source_join_execution_plan.csv"
            join_plan_frame = pd.read_csv(join_plan_path, keep_default_na=False, low_memory=False)
            join_plan_frame.loc[join_plan_frame["required_action"].astype(str).eq("JOIN_OPERATOR_AUDIT_SOURCE"), "candidate_join_source_path"] = ""
            join_plan_frame.to_csv(join_plan_path, index=False)
            governed_operator_path = _write_promotion_scoped_operator_audit(packet_root, folder_name)

            _write_csv(
                actual_source,
                [
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1001", "actual_gross_profit": 10.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1002", "actual_gross_profit": 12.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1003", "actual_gross_profit": 8.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1004", "actual_gross_profit": 6.0},
                ],
            )

            source_rows_path = packet_root / "source_materialized_promotions" / folder_name / "promotion_source_rows.csv"
            source_rows_before = source_rows_path.read_bytes()
            operator_before = governed_operator_path.read_bytes()

            result = build_promotions_materialized_source_join_key_validator(
                packet_root=packet_root,
                promotion_key="772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
            )

            self.assertEqual(result.operator_validation.discovery_source, "PROMOTION_SCOPED_GOVERNED_FILE")
            self.assertEqual(result.operator_validation.candidate_source_path, str(governed_operator_path))
            self.assertNotEqual(result.operator_validation.recommended_evaluation.join_readiness_status, JOIN_SOURCE_NOT_AVAILABLE)
            self.assertEqual(source_rows_path.read_bytes(), source_rows_before)
            self.assertEqual(governed_operator_path.read_bytes(), operator_before)

    def test_without_queue_or_governed_operator_audit_remains_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"

            _write_source_packet(packet_root)
            _write_queue_inputs(packet_root, actual_source, operator_source)
            join_plan_path = packet_root / "materialized_source_rebuild_queue" / "materialized_source_join_execution_plan.csv"
            join_plan_frame = pd.read_csv(join_plan_path, keep_default_na=False, low_memory=False)
            join_plan_frame.loc[join_plan_frame["required_action"].astype(str).eq("JOIN_OPERATOR_AUDIT_SOURCE"), "candidate_join_source_path"] = ""
            join_plan_frame.to_csv(join_plan_path, index=False)

            _write_csv(
                actual_source,
                [
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1001", "actual_gross_profit": 10.0},
                ],
            )

            result = build_promotions_materialized_source_join_key_validator(
                packet_root=packet_root,
                promotion_key="772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
            )

            self.assertEqual(result.operator_validation.discovery_source, "NOT_AVAILABLE")
            self.assertEqual(result.operator_validation.recommended_evaluation.join_readiness_status, JOIN_SOURCE_NOT_AVAILABLE)

    def test_uses_governed_operator_audit_when_queue_path_is_missing_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "missing_operator_audit.csv"

            folder_name = _write_source_packet(packet_root)
            _write_queue_inputs(packet_root, actual_source, operator_source)
            governed_operator_path = _write_promotion_scoped_operator_audit(packet_root, folder_name)

            _write_csv(
                actual_source,
                [
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1001", "actual_gross_profit": 10.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1002", "actual_gross_profit": 10.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1003", "actual_gross_profit": 10.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1004", "actual_gross_profit": 10.0},
                ],
            )

            result = build_promotions_materialized_source_join_key_validator(
                packet_root=packet_root,
                promotion_key="772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
            )

            self.assertEqual(result.operator_validation.discovery_source, "PROMOTION_SCOPED_GOVERNED_FILE")
            self.assertEqual(result.operator_validation.candidate_source_path, str(governed_operator_path))

    def test_queue_plan_behavior_is_preserved_when_operator_path_exists_in_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"

            _write_source_packet(packet_root)
            _write_queue_inputs(packet_root, actual_source, operator_source)
            _write_csv(
                actual_source,
                [
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1001", "actual_gross_profit": 10.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1002", "actual_gross_profit": 10.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1003", "actual_gross_profit": 10.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1004", "actual_gross_profit": 10.0},
                ],
            )
            _write_csv(
                operator_source,
                [
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1001", "store_action": "BUY"},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1002", "store_action": "BUY"},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1003", "store_action": "BUY"},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1004", "store_action": "BUY"},
                ],
            )

            result = build_promotions_materialized_source_join_key_validator(
                packet_root=packet_root,
                promotion_key="772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
            )

            self.assertEqual(result.operator_validation.discovery_source, "QUEUE_PLAN_SOURCE")
            self.assertEqual(result.operator_validation.candidate_source_path, str(operator_source))

    def test_summary_and_plan_include_operator_audit_discovery_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"

            folder_name = _write_source_packet(packet_root)
            _write_queue_inputs(packet_root, actual_source, operator_source)
            join_plan_path = packet_root / "materialized_source_rebuild_queue" / "materialized_source_join_execution_plan.csv"
            join_plan_frame = pd.read_csv(join_plan_path, keep_default_na=False, low_memory=False)
            join_plan_frame.loc[join_plan_frame["required_action"].astype(str).eq("JOIN_OPERATOR_AUDIT_SOURCE"), "candidate_join_source_path"] = ""
            join_plan_frame.to_csv(join_plan_path, index=False)
            governed_operator_path = _write_promotion_scoped_operator_audit(packet_root, folder_name)

            _write_csv(
                actual_source,
                [
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1001", "actual_gross_profit": 10.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1002", "actual_gross_profit": 10.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1003", "actual_gross_profit": 10.0},
                    {"store_number": "772", "promotion_start_date": "2026-05-21", "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1", "sku_number": "1004", "actual_gross_profit": 10.0},
                ],
            )

            artifacts = write_promotions_materialized_source_join_key_validator(
                packet_root=packet_root,
                output_root=packet_root / "out",
            )
            summary_frame = pd.read_csv(artifacts.summary_csv_path, keep_default_na=False, low_memory=False)
            plan_frame = pd.read_csv(artifacts.plan_csv_path, keep_default_na=False, low_memory=False)

            summary_lookup = dict(zip(summary_frame["metric_name"].astype(str), summary_frame["metric_value"].astype(str)))
            self.assertEqual(summary_lookup.get("OPERATOR_AUDIT_DISCOVERY_SOURCE"), "PROMOTION_SCOPED_GOVERNED_FILE")
            self.assertEqual(summary_lookup.get("OPERATOR_AUDIT_SOURCE_PATH"), str(governed_operator_path))
            operator_plan = plan_frame.loc[plan_frame["candidate_source_role"].astype(str).eq("OPERATOR_AUDIT")].iloc[0]
            self.assertEqual(operator_plan["operator_audit_discovery_source"], "PROMOTION_SCOPED_GOVERNED_FILE")
            self.assertEqual(operator_plan["operator_audit_source_path"], str(governed_operator_path))

    def test_build_join_key_validator_selects_safe_actual_and_duplicate_review_operator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"

            _write_source_packet(packet_root)
            _write_queue_inputs(packet_root, actual_source, operator_source)
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
                        "actual_gross_profit": 8.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1004",
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
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1004",
                        "store_action": "BUY",
                    },
                ],
            )

            result = build_promotions_materialized_source_join_key_validator(packet_root=packet_root)

            self.assertEqual(
                result.selected_promotion.promotion_key,
                "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
            )
            self.assertEqual(result.actual_validation.recommended_evaluation.join_readiness_status, JOIN_READY)
            self.assertEqual(
                result.actual_validation.recommended_evaluation.join_key_name,
                "store_number + promotion_start_date + promotion_name + sku_number",
            )
            self.assertAlmostEqual(result.actual_validation.recommended_evaluation.match_rate, 1.0)
            self.assertEqual(
                result.operator_validation.recommended_evaluation.join_readiness_status,
                JOIN_BLOCKED_ROW_EXPLOSION_RISK,
            )
            self.assertEqual(result.operator_validation.recommended_evaluation.row_explosion_risk_flag, 1)
            self.assertTrue(result.rows_frame["candidate_source_role"].astype(str).eq("ACTUAL_OUTCOME").any())
            self.assertTrue(result.rows_frame["recommended_join_key_flag"].astype(int).eq(1).any())
            self.assertEqual(len(result.failures_frame.index), 0)
            self.assertGreater(len(result.duplicates_frame.index), 0)

    def test_build_join_key_validator_blocks_row_explosion_when_override_source_is_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"

            _write_source_packet(packet_root)
            _write_queue_inputs(packet_root, actual_source, operator_source)
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
                    }
                ],
            )

            result = build_promotions_materialized_source_join_key_validator(
                packet_root=packet_root,
                actual_source=str(actual_source),
            )

            self.assertEqual(
                result.actual_validation.recommended_evaluation.join_readiness_status,
                JOIN_BLOCKED_ROW_EXPLOSION_RISK,
            )

    def test_write_join_key_validator_outputs_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"

            _write_source_packet(packet_root)
            _write_queue_inputs(packet_root, actual_source, operator_source)
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
                        "actual_gross_profit": 10.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1003",
                        "actual_gross_profit": 10.0,
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1004",
                        "actual_gross_profit": 10.0,
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
                        "store_action": "BUY",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1003",
                        "store_action": "BUY",
                    },
                    {
                        "store_number": "772",
                        "promotion_start_date": "2026-05-21",
                        "promotion_name": "ALLOCATION REPORT - WK47&48 WINTER PART 1",
                        "sku_number": "1004",
                        "store_action": "BUY",
                    },
                ],
            )

            artifacts = write_promotions_materialized_source_join_key_validator(packet_root=packet_root)

            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.rows_csv_path).exists())
            self.assertTrue(Path(artifacts.failures_csv_path).exists())
            self.assertTrue(Path(artifacts.duplicates_csv_path).exists())
            self.assertTrue(Path(artifacts.plan_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())


if __name__ == "__main__":
    unittest.main()