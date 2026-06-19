from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_rebuild_queue import (  # noqa: E402
    ACTION_JOIN_ACTUAL_OUTCOME_SOURCE,
    ACTION_JOIN_OPERATOR_AUDIT_SOURCE,
    ACTION_VALIDATE_NO_ACTUALS_AS_ZERO,
    ACTION_VALIDATE_PRODUCTION_AND_STAGE12_GUARDRAILS,
    QUEUE_BLOCKED_MISSING_JOIN_SOURCE,
    QUEUE_NOT_REQUIRED,
    build_promotions_materialized_source_rebuild_queue,
    write_promotions_materialized_source_rebuild_queue,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_manifest(
    packet_root: Path,
    *,
    folder_name: str,
    source_file_path: str,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
) -> None:
    _write_csv(
        packet_root
        / "source_materialized_promotions"
        / folder_name
        / "promotion_source_manifest.csv",
        [
            {
                "source_file_path": source_file_path,
                "source_file_type": "DECISION_SURFACE",
                "row_count": 10,
                "sku_count": 10,
                "store_number": "772",
                "promotion_name": promotion_name,
                "promotion_start_date": promotion_start_date,
                "promotion_end_date": promotion_end_date,
                "source_discovery_status": "SOURCE_ROW_DISCOVERED",
                "materialization_status": "SOURCE_ROWS_WRITTEN",
                "downstream_full_diagnostic_chain_available_flag": 0,
                "downstream_full_packet_reason": "Source-only packet remains diagnostics-only until joins and mapping are prepared.",
                "missing_canonical_fields": "review_packet_row_key; predicted_gross_profit",
            }
        ],
    )


def _write_readiness_inputs(packet_root: Path) -> None:
    readiness_root = packet_root / "materialized_source_readiness_audit"
    actual_path = str(packet_root / "support" / "actual_outcome.csv")
    operator_path = str(packet_root / "support" / "operator_audit.csv")
    inspection_path = str(packet_root / "support" / "review_packet.csv")
    _write_csv(
        readiness_root / "materialized_source_readiness_rows.csv",
        [
            {
                "promotion_folder_name": "promotion_a",
                "promotion_key": "772|2026-05-21|2026-06-03|Winter Part 1",
                "promotion_name": "Winter Part 1",
                "store_number": "772",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
                "source_file_path": "tmp/source_a.csv",
                "source_file_type": "DECISION_SURFACE",
                "source_row_path": "tmp/source_rows_a.csv",
                "source_manifest_path": "tmp/source_manifest_a.csv",
                "row_count": 10,
                "sku_count": 10,
                "identity_columns_present_count": 6,
                "prediction_action_columns_present_count": 1,
                "economics_columns_present_count": 4,
                "actual_outcome_columns_present_count": 1,
                "identity_columns_missing": "",
                "prediction_action_columns_missing": "expected_promo_demand; store_action; demand_evidence_label",
                "economics_columns_missing": "",
                "actual_outcome_columns_missing": "actual_gross_profit",
                "actual_outcome_fields_present_but_blank_count": 0,
                "join_keys_available": "store_number; promotion_start_date; promotion_name; sku_number",
                "candidate_join_source_count": 2,
                "candidate_actual_outcome_source_count": 1,
                "candidate_operator_audit_source_count": 1,
                "candidate_review_packet_source_count": 1,
                "needs_actual_outcome_join_flag": 1,
                "needs_operator_audit_join_flag": 1,
                "needs_canonical_review_schema_mapping_flag": 1,
                "missing_actual_outcome_fields": "actual_gross_profit",
                "candidate_actual_join_sources": f"{actual_path}; {inspection_path}",
                "candidate_operator_join_sources": f"{operator_path}; {inspection_path}",
                "critical_missing_column_count": 4,
                "readiness_status": "NEEDS_ACTUAL_OUTCOME_JOIN",
                "readiness_reason": "Needs actuals and operator evidence.",
                "recommended_rebuild_path": "Join then map",
                "production_order_changes": 0,
                "stage_12_changes": 0,
            },
            {
                "promotion_folder_name": "promotion_b",
                "promotion_key": "772|2026-04-09|2026-04-22|Skincare Goody Bag",
                "promotion_name": "Skincare Goody Bag",
                "store_number": "772",
                "promotion_start_date": "2026-04-09",
                "promotion_end_date": "2026-04-22",
                "source_file_path": "tmp/source_b.csv",
                "source_file_type": "DECISION_SURFACE",
                "source_row_path": "tmp/source_rows_b.csv",
                "source_manifest_path": "tmp/source_manifest_b.csv",
                "row_count": 12,
                "sku_count": 12,
                "identity_columns_present_count": 6,
                "prediction_action_columns_present_count": 1,
                "economics_columns_present_count": 4,
                "actual_outcome_columns_present_count": 1,
                "identity_columns_missing": "",
                "prediction_action_columns_missing": "expected_promo_demand; store_action; demand_evidence_label",
                "economics_columns_missing": "",
                "actual_outcome_columns_missing": "actual_gross_profit",
                "actual_outcome_fields_present_but_blank_count": 0,
                "join_keys_available": "store_number; promotion_start_date; promotion_name; sku_number",
                "candidate_join_source_count": 0,
                "candidate_actual_outcome_source_count": 0,
                "candidate_operator_audit_source_count": 0,
                "candidate_review_packet_source_count": 0,
                "needs_actual_outcome_join_flag": 0,
                "needs_operator_audit_join_flag": 0,
                "needs_canonical_review_schema_mapping_flag": 1,
                "missing_actual_outcome_fields": "actual_gross_profit",
                "candidate_actual_join_sources": "",
                "candidate_operator_join_sources": "",
                "critical_missing_column_count": 4,
                "readiness_status": "NEEDS_CANONICAL_REVIEW_SCHEMA_MAPPING",
                "readiness_reason": "Missing actual join candidate.",
                "recommended_rebuild_path": "Map only",
                "production_order_changes": 0,
                "stage_12_changes": 0,
            },
        ],
    )
    _write_csv(
        readiness_root / "materialized_source_candidate_join_sources.csv",
        [
            {
                "source_path": actual_path,
                "source_role": "ACTUAL_OUTCOME",
                "columns_available": "store_number; promotion_start_date; promotion_name; sku_number; actual_gross_profit",
                "possible_join_keys": "store_number; promotion_start_date; promotion_name; sku_number",
                "matching_promotion_count": 1,
                "matched_promotion_keys": "772|2026-05-21|2026-06-03|Winter Part 1",
                "can_supply_actual_outcome_fields_flag": 1,
                "can_supply_operator_action_fields_flag": 0,
                "can_supply_review_packet_fields_flag": 0,
                "missing_field_groups_addressed": "actual_outcome",
                "file_exists_flag": 1,
            },
            {
                "source_path": operator_path,
                "source_role": "OPERATOR_AUDIT",
                "columns_available": "store_number; promotion_start_date; promotion_name; sku_number; store_action; demand_evidence_label",
                "possible_join_keys": "store_number; promotion_start_date; promotion_name; sku_number",
                "matching_promotion_count": 1,
                "matched_promotion_keys": "772|2026-05-21|2026-06-03|Winter Part 1",
                "can_supply_actual_outcome_fields_flag": 0,
                "can_supply_operator_action_fields_flag": 1,
                "can_supply_review_packet_fields_flag": 0,
                "missing_field_groups_addressed": "operator_action",
                "file_exists_flag": 1,
            },
            {
                "source_path": inspection_path,
                "source_role": "INSPECTION_REVIEW_PACKET",
                "columns_available": "store_number; promotion_start_date; promotion_name; predicted_gross_profit",
                "possible_join_keys": "store_number; promotion_start_date; promotion_name",
                "matching_promotion_count": 1,
                "matched_promotion_keys": "772|2026-05-21|2026-06-03|Winter Part 1",
                "can_supply_actual_outcome_fields_flag": 1,
                "can_supply_operator_action_fields_flag": 1,
                "can_supply_review_packet_fields_flag": 1,
                "missing_field_groups_addressed": "actual_outcome; review_packet",
                "file_exists_flag": 1,
            },
        ],
    )
    _write_csv(
        readiness_root / "materialized_source_rebuild_plan.csv",
        [
            {
                "promotion_key": "772|2026-05-21|2026-06-03|Winter Part 1",
                "promotion_name": "Winter Part 1",
                "readiness_status": "NEEDS_ACTUAL_OUTCOME_JOIN",
                "recommended_rebuild_path": "Join then map",
                "required_steps": "actual_outcome_join; operator_audit_join; schema_mapping",
                "candidate_actual_join_sources": actual_path,
                "candidate_operator_join_sources": operator_path,
                "missing_critical_columns": "actual_gross_profit",
            }
        ],
    )
    _write_csv(
        readiness_root / "materialized_source_readiness_summary.csv",
        [{"metric_name": "PROMOTIONS_AUDITED", "metric_value": 2, "metric_display": "2", "notes": ""}],
    )
    (readiness_root / "materialized_source_readiness_memo.md").write_text(
        "diagnostics only",
        encoding="utf-8",
    )


class PromotionsMaterializedSourceRebuildQueueTests(unittest.TestCase):
    def test_build_rebuild_queue_produces_join_and_guardrail_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_readiness_inputs(packet_root)
            _write_manifest(
                packet_root,
                folder_name="promotion_a",
                source_file_path="tmp/source_a.csv",
                promotion_name="Winter Part 1",
                promotion_start_date="2026-05-21",
                promotion_end_date="2026-06-03",
            )
            _write_manifest(
                packet_root,
                folder_name="promotion_b",
                source_file_path="tmp/source_b.csv",
                promotion_name="Skincare Goody Bag",
                promotion_start_date="2026-04-09",
                promotion_end_date="2026-04-22",
            )

            result = build_promotions_materialized_source_rebuild_queue(packet_root=packet_root)

            queue_rows = result.queue_rows_frame
            self.assertEqual(len(queue_rows.index), 16)

            winter_actual = queue_rows.loc[
                queue_rows["promotion_key"].astype(str).eq(
                    "772|2026-05-21|2026-06-03|Winter Part 1"
                )
                & queue_rows["required_action"].astype(str).eq(ACTION_JOIN_ACTUAL_OUTCOME_SOURCE)
            ].iloc[0]
            self.assertNotEqual(winter_actual["action_status"], QUEUE_NOT_REQUIRED)
            self.assertIn("actual_outcome.csv", winter_actual["candidate_join_source_path"])

            winter_operator = queue_rows.loc[
                queue_rows["promotion_key"].astype(str).eq(
                    "772|2026-05-21|2026-06-03|Winter Part 1"
                )
                & queue_rows["required_action"].astype(str).eq(ACTION_JOIN_OPERATOR_AUDIT_SOURCE)
            ].iloc[0]
            self.assertNotEqual(winter_operator["action_status"], QUEUE_NOT_REQUIRED)
            self.assertIn("operator_audit.csv", winter_operator["candidate_join_source_path"])

            skincare_actual = queue_rows.loc[
                queue_rows["promotion_key"].astype(str).eq(
                    "772|2026-04-09|2026-04-22|Skincare Goody Bag"
                )
                & queue_rows["required_action"].astype(str).eq(ACTION_JOIN_ACTUAL_OUTCOME_SOURCE)
            ].iloc[0]
            self.assertEqual(skincare_actual["action_status"], QUEUE_BLOCKED_MISSING_JOIN_SOURCE)

            actuals_validation = queue_rows.loc[
                queue_rows["required_action"].astype(str).eq(ACTION_VALIDATE_NO_ACTUALS_AS_ZERO)
            ]
            self.assertTrue(
                actuals_validation["reason"].astype(str).str.contains(
                    "never rewritten as zero sales",
                    regex=False,
                ).all()
            )
            guardrail_rows = queue_rows.loc[
                queue_rows["required_action"].astype(str).eq(
                    ACTION_VALIDATE_PRODUCTION_AND_STAGE12_GUARDRAILS
                )
            ]
            self.assertEqual(len(guardrail_rows.index), 2)

    def test_write_rebuild_queue_writes_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_readiness_inputs(packet_root)
            _write_manifest(
                packet_root,
                folder_name="promotion_a",
                source_file_path="tmp/source_a.csv",
                promotion_name="Winter Part 1",
                promotion_start_date="2026-05-21",
                promotion_end_date="2026-06-03",
            )
            _write_manifest(
                packet_root,
                folder_name="promotion_b",
                source_file_path="tmp/source_b.csv",
                promotion_name="Skincare Goody Bag",
                promotion_start_date="2026-04-09",
                promotion_end_date="2026-04-22",
            )

            artifacts = write_promotions_materialized_source_rebuild_queue(
                packet_root=packet_root,
                output_root=packet_root / "materialized_source_rebuild_queue",
            )

            self.assertTrue(Path(artifacts.queue_rows_csv_path).exists())
            self.assertTrue(Path(artifacts.by_promotion_csv_path).exists())
            self.assertTrue(Path(artifacts.join_execution_plan_csv_path).exists())
            self.assertTrue(Path(artifacts.schema_mapping_plan_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())

            summary = pd.read_csv(artifacts.summary_csv_path, keep_default_na=False).set_index(
                "metric_name"
            )
            by_promotion = pd.read_csv(artifacts.by_promotion_csv_path, keep_default_na=False)

            self.assertEqual(int(summary.loc["PROMOTIONS_IN_QUEUE", "metric_value"]), 2)
            self.assertEqual(int(summary.loc["TOTAL_QUEUE_ROWS", "metric_value"]), 16)
            self.assertEqual(
                int(summary.loc["PROMOTIONS_WITH_ACTUAL_OUTCOME_JOIN_CANDIDATE", "metric_value"]),
                1,
            )
            self.assertEqual(
                int(summary.loc["PROMOTIONS_MISSING_ACTUAL_OUTCOME_JOIN_CANDIDATE", "metric_value"]),
                1,
            )
            self.assertEqual(by_promotion.iloc[0]["promotion_key"], "772|2026-05-21|2026-06-03|Winter Part 1")


if __name__ == "__main__":
    unittest.main()


def _write_manifest(packet_root: Path, folder_name: str, *, source_file_path: str, promotion_name: str, promotion_start_date: str, promotion_end_date: str) -> None:
    _write_csv(
        packet_root / "source_materialized_promotions" / folder_name / "promotion_source_manifest.csv",
        [
            {
                "source_file_path": source_file_path,
                "source_file_type": "DECISION_SURFACE",
                "row_count": 10,
                "sku_count": 10,
                "store_number": "772",
                "promotion_name": promotion_name,
                "promotion_start_date": promotion_start_date,
                "promotion_end_date": promotion_end_date,
                "source_discovery_status": "SOURCE_ROW_DISCOVERED",
                "materialization_status": "SOURCE_ROWS_WRITTEN",
                "downstream_full_diagnostic_chain_available_flag": 0,
                "downstream_full_packet_reason": "source only",
                "missing_canonical_fields": "",
            }
        ],
    )


class PromotionsMaterializedSourceRebuildQueueTests(unittest.TestCase):
    def test_build_rebuild_queue_produces_join_and_guardrail_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            audit_root = packet_root / "materialized_source_readiness_audit"
            actual_source = Path(tmp_dir) / "support" / "actual_outcome.csv"
            operator_source = Path(tmp_dir) / "support" / "operator_audit.csv"
            review_source = Path(tmp_dir) / "support" / "review_packet.csv"

            _write_csv(
                audit_root / "materialized_source_readiness_rows.csv",
                [
                    {
                        "promotion_folder_name": "promotion_recent_actual",
                        "promotion_key": "772|2026-05-21|2026-06-03|Winter Part 1",
                        "promotion_name": "Winter Part 1",
                        "promotion_start_date": "2026-05-21",
                        "promotion_end_date": "2026-06-03",
                        "source_file_path": "tmp/source_recent.csv",
                        "source_file_type": "DECISION_SURFACE",
                        "identity_columns_missing": "",
                        "prediction_action_columns_missing": "expected_promo_demand; store_action; demand_evidence_label",
                        "economics_columns_missing": "",
                        "actual_outcome_columns_missing": "actual_gross_profit; capital_left",
                        "join_keys_available": "store_number; promotion_start_date; promotion_name; sku_number",
                        "candidate_actual_outcome_source_count": 2,
                        "candidate_operator_audit_source_count": 1,
                        "needs_actual_outcome_join_flag": 1,
                        "needs_operator_audit_join_flag": 1,
                        "needs_canonical_review_schema_mapping_flag": 1,
                        "missing_actual_outcome_fields": "actual_gross_profit",
                        "candidate_actual_join_sources": f"{actual_source}; {review_source}",
                        "candidate_operator_join_sources": str(operator_source),
                        "critical_missing_column_count": 4,
                        "readiness_status": "NEEDS_ACTUAL_OUTCOME_JOIN",
                        "recommended_rebuild_path": "Join actuals then map schema",
                        "production_order_changes": 0,
                        "stage_12_changes": 0,
                    },
                    {
                        "promotion_folder_name": "promotion_mapping_only",
                        "promotion_key": "772|2026-03-24|2026-04-22|New Line 26",
                        "promotion_name": "New Line 26",
                        "promotion_start_date": "2026-03-24",
                        "promotion_end_date": "2026-04-22",
                        "source_file_path": "tmp/source_old.csv",
                        "source_file_type": "DECISION_SURFACE",
                        "identity_columns_missing": "",
                        "prediction_action_columns_missing": "expected_promo_demand; store_action",
                        "economics_columns_missing": "",
                        "actual_outcome_columns_missing": "actual_gross_profit",
                        "join_keys_available": "store_number; promotion_start_date; promotion_name; sku_number",
                        "candidate_actual_outcome_source_count": 0,
                        "candidate_operator_audit_source_count": 0,
                        "needs_actual_outcome_join_flag": 0,
                        "needs_operator_audit_join_flag": 0,
                        "needs_canonical_review_schema_mapping_flag": 1,
                        "missing_actual_outcome_fields": "actual_gross_profit",
                        "candidate_actual_join_sources": "",
                        "candidate_operator_join_sources": "",
                        "critical_missing_column_count": 3,
                        "readiness_status": "NEEDS_CANONICAL_REVIEW_SCHEMA_MAPPING",
                        "recommended_rebuild_path": "Map schema",
                        "production_order_changes": 0,
                        "stage_12_changes": 0,
                    },
                ],
            )
            _write_csv(
                audit_root / "materialized_source_candidate_join_sources.csv",
                [
                    {
                        "source_path": str(actual_source),
                        "source_role": "ACTUAL_OUTCOME",
                        "columns_available": "actual_gross_profit",
                        "possible_join_keys": "store_number; promotion_start_date; promotion_name; sku_number",
                        "matching_promotion_count": 1,
                        "matched_promotion_keys": "772|2026-05-21|2026-06-03|Winter Part 1",
                        "can_supply_actual_outcome_fields_flag": 1,
                        "can_supply_operator_action_fields_flag": 0,
                        "can_supply_review_packet_fields_flag": 0,
                        "missing_field_groups_addressed": "actual_outcome",
                        "file_exists_flag": 1,
                    },
                    {
                        "source_path": str(operator_source),
                        "source_role": "OPERATOR_AUDIT",
                        "columns_available": "store_action; demand_evidence_label",
                        "possible_join_keys": "store_number; promotion_start_date; promotion_name; sku_number",
                        "matching_promotion_count": 1,
                        "matched_promotion_keys": "772|2026-05-21|2026-06-03|Winter Part 1",
                        "can_supply_actual_outcome_fields_flag": 0,
                        "can_supply_operator_action_fields_flag": 1,
                        "can_supply_review_packet_fields_flag": 0,
                        "missing_field_groups_addressed": "operator_action",
                        "file_exists_flag": 1,
                    },
                    {
                        "source_path": str(review_source),
                        "source_role": "INSPECTION_REVIEW_PACKET",
                        "columns_available": "predicted_gross_profit",
                        "possible_join_keys": "store_number; promotion_start_date; promotion_name",
                        "matching_promotion_count": 1,
                        "matched_promotion_keys": "772|2026-05-21|2026-06-03|Winter Part 1",
                        "can_supply_actual_outcome_fields_flag": 1,
                        "can_supply_operator_action_fields_flag": 0,
                        "can_supply_review_packet_fields_flag": 1,
                        "missing_field_groups_addressed": "actual_outcome; review_packet",
                        "file_exists_flag": 1,
                    },
                ],
            )
            _write_manifest(
                packet_root,
                "promotion_recent_actual",
                source_file_path="tmp/source_recent.csv",
                promotion_name="Winter Part 1",
                promotion_start_date="2026-05-21",
                promotion_end_date="2026-06-03",
            )
            _write_manifest(
                packet_root,
                "promotion_mapping_only",
                source_file_path="tmp/source_old.csv",
                promotion_name="New Line 26",
                promotion_start_date="2026-03-24",
                promotion_end_date="2026-04-22",
            )

            result = build_promotions_materialized_source_rebuild_queue(packet_root=packet_root)

            queue_rows = result.queue_rows_frame
            by_promotion = result.by_promotion_frame

            self.assertGreater(len(queue_rows.index), 0)
            self.assertEqual(by_promotion.iloc[0]["promotion_key"], "772|2026-05-21|2026-06-03|Winter Part 1")
            self.assertTrue(queue_rows["required_action"].astype(str).eq(ACTION_JOIN_ACTUAL_OUTCOME_SOURCE).any())
            self.assertTrue(queue_rows["required_action"].astype(str).eq(ACTION_JOIN_OPERATOR_AUDIT_SOURCE).any())

            actual_row = queue_rows.loc[
                queue_rows["required_action"].astype(str).eq(ACTION_JOIN_ACTUAL_OUTCOME_SOURCE)
            ].iloc[0]
            self.assertEqual(actual_row["candidate_join_source_path"], str(actual_source))
            self.assertEqual(actual_row["missing_fields_addressed"], "actual_gross_profit")
            self.assertNotIn("0", str(actual_row["reason"]).lower())

            guardrail_rows = queue_rows.loc[
                queue_rows["required_action"].astype(str).eq(ACTION_VALIDATE_PRODUCTION_AND_STAGE12_GUARDRAILS)
            ]
            self.assertEqual(len(guardrail_rows.index), 2)

            no_actual_zero_rows = queue_rows.loc[
                queue_rows["required_action"].astype(str).eq(ACTION_VALIDATE_NO_ACTUALS_AS_ZERO)
            ]
            self.assertEqual(len(no_actual_zero_rows.index), 2)
            self.assertTrue(no_actual_zero_rows["reason"].astype(str).str.contains("missing actual", case=False).any())

    def test_write_rebuild_queue_writes_outputs_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            audit_root = packet_root / "materialized_source_readiness_audit"
            _write_csv(
                audit_root / "materialized_source_readiness_rows.csv",
                [
                    {
                        "promotion_folder_name": "promotion_one",
                        "promotion_key": "772|2026-05-21|2026-06-03|Winter Part 1",
                        "promotion_name": "Winter Part 1",
                        "promotion_start_date": "2026-05-21",
                        "promotion_end_date": "2026-06-03",
                        "source_file_path": "tmp/source_recent.csv",
                        "source_file_type": "DECISION_SURFACE",
                        "identity_columns_missing": "",
                        "prediction_action_columns_missing": "expected_promo_demand",
                        "economics_columns_missing": "",
                        "actual_outcome_columns_missing": "actual_gross_profit",
                        "join_keys_available": "store_number; promotion_start_date; promotion_name; sku_number",
                        "candidate_actual_outcome_source_count": 1,
                        "candidate_operator_audit_source_count": 0,
                        "needs_actual_outcome_join_flag": 1,
                        "needs_operator_audit_join_flag": 0,
                        "needs_canonical_review_schema_mapping_flag": 1,
                        "missing_actual_outcome_fields": "actual_gross_profit",
                        "candidate_actual_join_sources": "/tmp/actual.csv",
                        "candidate_operator_join_sources": "",
                        "critical_missing_column_count": 2,
                        "readiness_status": "NEEDS_ACTUAL_OUTCOME_JOIN",
                        "recommended_rebuild_path": "Join actuals then map schema",
                        "production_order_changes": 0,
                        "stage_12_changes": 0,
                    }
                ],
            )
            _write_csv(
                audit_root / "materialized_source_candidate_join_sources.csv",
                [
                    {
                        "source_path": "/tmp/actual.csv",
                        "source_role": "ACTUAL_OUTCOME",
                        "columns_available": "actual_gross_profit",
                        "possible_join_keys": "store_number; promotion_start_date; promotion_name; sku_number",
                        "matching_promotion_count": 1,
                        "matched_promotion_keys": "772|2026-05-21|2026-06-03|Winter Part 1",
                        "can_supply_actual_outcome_fields_flag": 1,
                        "can_supply_operator_action_fields_flag": 0,
                        "can_supply_review_packet_fields_flag": 0,
                        "missing_field_groups_addressed": "actual_outcome",
                        "file_exists_flag": 1,
                    }
                ],
            )
            _write_manifest(
                packet_root,
                "promotion_one",
                source_file_path="tmp/source_recent.csv",
                promotion_name="Winter Part 1",
                promotion_start_date="2026-05-21",
                promotion_end_date="2026-06-03",
            )

            artifacts = write_promotions_materialized_source_rebuild_queue(packet_root=packet_root)

            self.assertTrue(Path(artifacts.queue_rows_csv_path).exists())
            self.assertTrue(Path(artifacts.by_promotion_csv_path).exists())
            self.assertTrue(Path(artifacts.join_execution_plan_csv_path).exists())
            self.assertTrue(Path(artifacts.schema_mapping_plan_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())

            summary = pd.read_csv(artifacts.summary_csv_path, keep_default_na=False).set_index("metric_name")
            self.assertEqual(int(summary.loc["PROMOTIONS_IN_QUEUE", "metric_value"]), 1)
            self.assertEqual(int(summary.loc["PROMOTIONS_WITH_ACTUAL_OUTCOME_JOIN_CANDIDATE", "metric_value"]), 1)


if __name__ == "__main__":
    unittest.main()