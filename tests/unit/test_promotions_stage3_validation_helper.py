from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.print_completed_stage3_validation import (  # noqa: E402
    _classify_failure_signals,
    collect_completed_stage3_validation_summary,
)


class PromotionStage3ValidationHelperTests(unittest.TestCase):
    def test_classifies_source_sku_identity_failure(self) -> None:
        classification = _classify_failure_signals(
            [
                "Completed Stage 3 source SKU identity validation failed for completed_base: "
                "raw advice-source sku_number could not derive a governed integer sku_number_key."
            ],
            partition_completion_state="finalized",
            completion_state="finalized",
            has_partition_completion=True,
        )

        self.assertEqual(classification, "advice-source identity problem")

    def test_collect_completed_stage3_validation_summary_accepts_local_final_assembler_without_sql_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            run_id = "completed-partition-run-local-final-assembler"
            batch_run_id = f"{run_id}-batch-000001"
            base_stage_run_id = f"{batch_run_id}-base"
            window_stage_run_id = f"{batch_run_id}-window-aggregates"
            transaction_stage_run_id = f"{batch_run_id}-transaction-aggregates"

            partition_manifest_path = artifact_paths.extracted_manifest_path(run_id)
            partition_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            batch_manifest_path = artifact_paths.extracted_manifest_path(batch_run_id)
            batch_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            stage_manifest_paths = [
                artifact_paths.extracted_manifest_path(base_stage_run_id),
                artifact_paths.extracted_manifest_path(window_stage_run_id),
                artifact_paths.extracted_manifest_path(transaction_stage_run_id),
            ]
            for stage_manifest_path in stage_manifest_paths:
                stage_manifest_path.parent.mkdir(parents=True, exist_ok=True)

            partition_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "partition_count": 72,
                        "partition_index": 1,
                        "row_count": 371,
                        "completed_sales_history_start_date": "2024-01-01",
                        "child_batch_manifest_paths": [str(batch_manifest_path)],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_progress_path(run_id).write_text(
                json.dumps(
                    {
                        "batch_row_count": 1000,
                        "partition_completion_state": "finalized",
                        "completion_state": "finalized",
                        "total_landed_rows": 371,
                        "finalized_batch_count": 1,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_completion_path(run_id).write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "partition_completion_state": "finalized",
                        "completion_state": "finalized",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.sql_diagnostics_summary_json_path(run_id).write_text(
                json.dumps(
                    {
                        "extraction_status": "succeeded",
                        "current_sql_subphase": "combining finalized landed batch artifacts",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extracted_base_path(run_id).parent.mkdir(parents=True, exist_ok=True)
            artifact_paths.extracted_base_path(run_id).write_text("placeholder", encoding="utf-8")

            batch_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": batch_run_id,
                        "row_count": 371,
                        "candidate_promotion_row_count": 371,
                        "completed_sales_history_start_date": "2024-01-01",
                        "child_stage_manifest_paths": [str(path) for path in stage_manifest_paths],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            stage_payloads = {
                base_stage_run_id: {"extraction_stage": "completed_base", "row_count": 371},
                window_stage_run_id: {
                    "extraction_stage": "completed_window_aggregates",
                    "row_count": 371,
                },
                transaction_stage_run_id: {
                    "extraction_stage": "completed_transaction_aggregates",
                    "row_count": 371,
                },
            }
            for stage_run_id, payload in stage_payloads.items():
                artifact_paths.extracted_manifest_path(stage_run_id).write_text(
                    json.dumps({"run_id": stage_run_id, **payload}, sort_keys=True),
                    encoding="utf-8",
                )
                artifact_paths.manifests_run_root(stage_run_id).mkdir(parents=True, exist_ok=True)
                (artifact_paths.manifests_run_root(stage_run_id) / "rendered_sql.sql").write_text(
                    "SELECT 1\n",
                    encoding="utf-8",
                )
                artifact_paths.extraction_telemetry_json_path(stage_run_id).write_text(
                    json.dumps({"total_elapsed_seconds": 1.0}, sort_keys=True),
                    encoding="utf-8",
                )
                artifact_paths.sql_diagnostics_summary_json_path(stage_run_id).write_text(
                    json.dumps({"extraction_status": "succeeded"}, sort_keys=True),
                    encoding="utf-8",
                )
                artifact_paths.extraction_partition_completion_path(stage_run_id).write_text(
                    json.dumps(
                        {
                            "run_id": stage_run_id,
                            "partition_completion_state": "finalized",
                            "completion_state": "finalized",
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )

            artifact_paths.extraction_telemetry_json_path(batch_run_id).write_text(
                json.dumps({"total_elapsed_seconds": None}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.sql_diagnostics_summary_json_path(batch_run_id).write_text(
                json.dumps(
                    {
                        "extraction_status": "succeeded",
                        "rendered_sql_path": None,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_completion_path(batch_run_id).write_text(
                json.dumps(
                    {
                        "run_id": batch_run_id,
                        "partition_completion_state": "finalized",
                        "completion_state": "finalized",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            summary = collect_completed_stage3_validation_summary(
                artifact_paths=artifact_paths,
                run_id=run_id,
            )

            self.assertEqual(summary.follow_up.status, "success")
            self.assertTrue(summary.follow_up.safe_to_resume_reuse)
            self.assertEqual(summary.follow_up.failure_classification, None)
            self.assertEqual(summary.follow_up.total_extracted_rows, 371)
            self.assertEqual(summary.follow_up.landed_batch_count, 1)
            assembler_record = next(
                record
                for record in summary.records
                if record.stage_name == "completed_final_assembler"
            )
            self.assertIsNone(assembler_record.rendered_sql_path)
            self.assertIsNone(assembler_record.elapsed_seconds)

    def test_collect_completed_stage3_validation_summary_reads_staged_batch_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            run_id = "completed-partition-run"
            batch_run_id = f"{run_id}-batch-000001"
            base_stage_run_id = f"{batch_run_id}-base"
            window_stage_run_id = f"{batch_run_id}-window-aggregates"
            transaction_stage_run_id = f"{batch_run_id}-transaction-aggregates"

            partition_manifest_path = artifact_paths.extracted_manifest_path(run_id)
            partition_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            batch_manifest_path = artifact_paths.extracted_manifest_path(batch_run_id)
            batch_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            stage_manifest_paths = [
                artifact_paths.extracted_manifest_path(base_stage_run_id),
                artifact_paths.extracted_manifest_path(window_stage_run_id),
                artifact_paths.extracted_manifest_path(transaction_stage_run_id),
            ]
            for stage_manifest_path in stage_manifest_paths:
                stage_manifest_path.parent.mkdir(parents=True, exist_ok=True)

            partition_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "partition_count": 10,
                        "partition_index": 3,
                        "row_count": 77,
                        "completed_sales_history_start_date": "2024-01-01",
                        "child_batch_manifest_paths": [str(batch_manifest_path)],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_progress_path(run_id).write_text(
                json.dumps({"batch_row_count": 1000, "total_landed_rows": 77}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.extracted_base_path(run_id).parent.mkdir(parents=True, exist_ok=True)
            artifact_paths.extracted_base_path(run_id).write_text("placeholder", encoding="utf-8")
            batch_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": batch_run_id,
                        "row_count": 77,
                        "completed_sales_history_start_date": "2024-01-01",
                        "child_stage_manifest_paths": [str(path) for path in stage_manifest_paths],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            stage_payloads = {
                base_stage_run_id: {"extraction_stage": "completed_base", "row_count": 50},
                window_stage_run_id: {
                    "extraction_stage": "completed_window_aggregates",
                    "row_count": 77,
                },
                transaction_stage_run_id: {
                    "extraction_stage": "completed_transaction_aggregates",
                    "row_count": 77,
                },
            }
            for stage_run_id, payload in stage_payloads.items():
                artifact_paths.extracted_manifest_path(stage_run_id).write_text(
                    json.dumps({"run_id": stage_run_id, **payload}, sort_keys=True),
                    encoding="utf-8",
                )
                artifact_paths.manifests_run_root(stage_run_id).mkdir(parents=True, exist_ok=True)
                (artifact_paths.manifests_run_root(stage_run_id) / "rendered_sql.sql").write_text(
                    "SELECT 1\n",
                    encoding="utf-8",
                )
                artifact_paths.extraction_telemetry_json_path(stage_run_id).write_text(
                    json.dumps({"total_elapsed_seconds": 12.5}, sort_keys=True),
                    encoding="utf-8",
                )
                artifact_paths.extraction_partition_completion_path(stage_run_id).write_text(
                    json.dumps(
                        {
                            "run_id": stage_run_id,
                            "partition_completion_state": "finalized",
                            "completion_state": "finalized",
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
            artifact_paths.extraction_telemetry_json_path(batch_run_id).write_text(
                json.dumps({"total_elapsed_seconds": 3.25}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_completion_path(batch_run_id).write_text(
                json.dumps(
                    {
                        "run_id": batch_run_id,
                        "partition_completion_state": "finalized",
                        "completion_state": "finalized",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_completion_path(run_id).write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "partition_completion_state": "finalized",
                        "completion_state": "finalized",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            summary = collect_completed_stage3_validation_summary(
                artifact_paths=artifact_paths,
                run_id=run_id,
            )

            self.assertEqual(summary.partition_index, 3)
            self.assertEqual(summary.partition_count, 10)
            self.assertEqual(summary.completed_sales_history_start_date, "2024-01-01")
            self.assertEqual(len(summary.records), 4)
            self.assertEqual(summary.follow_up.status, "success")
            self.assertEqual(summary.follow_up.total_extracted_rows, 77)
            self.assertEqual(summary.follow_up.landed_batch_count, 1)
            self.assertEqual(summary.follow_up.lower_bound_date_applied, "2024-01-01")
            self.assertTrue(summary.follow_up.safe_to_resume_reuse)
            self.assertEqual(summary.follow_up.failure_classification, None)
            self.assertEqual(
                summary.follow_up.success_summary,
                "Stage 3 completed partition artifacts are consolidated and readable; extracted_rows=77, landed_batch_count=1.",
            )
            base_record = next(
                record for record in summary.records if record.stage_name == "completed_base"
            )
            self.assertEqual(base_record.batch_number, 1)
            self.assertEqual(base_record.row_window_start, 1)
            self.assertEqual(base_record.row_window_end, 1000)
            self.assertEqual(base_record.rows_written, 50)
            self.assertTrue((base_record.rendered_sql_path or "").endswith("rendered_sql.sql"))
            self.assertTrue(
                (base_record.completion_marker_path or "").endswith(
                    "extraction_partition_completion.json"
                )
            )
            assembler_record = next(
                record
                for record in summary.records
                if record.stage_name == "completed_final_assembler"
            )
            self.assertEqual(assembler_record.rows_written, 77)
            self.assertIsNone(assembler_record.rendered_sql_path)
            self.assertEqual(assembler_record.elapsed_seconds, 3.25)
            self.assertEqual(
                assembler_record.completed_sales_history_start_date,
                "2024-01-01",
            )

    def test_collect_completed_stage3_validation_summary_classifies_sql_execution_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            run_id = "completed-partition-run-failure"
            batch_run_id = f"{run_id}-batch-000001"
            base_stage_run_id = f"{batch_run_id}-base"
            window_stage_run_id = f"{batch_run_id}-window-aggregates"
            transaction_stage_run_id = f"{batch_run_id}-transaction-aggregates"

            partition_manifest_path = artifact_paths.extracted_manifest_path(run_id)
            partition_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            batch_manifest_path = artifact_paths.extracted_manifest_path(batch_run_id)
            batch_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            stage_manifest_path = artifact_paths.extracted_manifest_path(base_stage_run_id)
            stage_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            window_stage_manifest_path = artifact_paths.extracted_manifest_path(window_stage_run_id)
            window_stage_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            transaction_stage_manifest_path = artifact_paths.extracted_manifest_path(
                transaction_stage_run_id
            )
            transaction_stage_manifest_path.parent.mkdir(parents=True, exist_ok=True)

            partition_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "partition_count": 8,
                        "partition_index": 2,
                        "row_count": 40,
                        "completed_sales_history_start_date": "2024-01-01",
                        "child_batch_manifest_paths": [str(batch_manifest_path)],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_progress_path(run_id).write_text(
                json.dumps(
                    {
                        "batch_row_count": 1000,
                        "partition_completion_state": "finalized",
                        "completion_state": "failed",
                        "total_landed_rows": 40,
                        "failure_message": "SQL executing timeout in completed_base",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extracted_base_path(run_id).parent.mkdir(parents=True, exist_ok=True)
            artifact_paths.extracted_base_path(run_id).write_text("placeholder", encoding="utf-8")
            artifact_paths.extraction_partition_completion_path(run_id).write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "partition_completion_state": "finalized",
                        "completion_state": "finalized",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            batch_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": batch_run_id,
                        "row_count": 40,
                        "candidate_promotion_row_count": 120,
                        "completed_sales_history_start_date": "2024-01-01",
                        "child_stage_manifest_paths": [
                            str(stage_manifest_path),
                            str(window_stage_manifest_path),
                            str(transaction_stage_manifest_path),
                        ],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            stage_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": base_stage_run_id,
                        "extraction_stage": "completed_base",
                        "row_count": 40,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            window_stage_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": window_stage_run_id,
                        "extraction_stage": "completed_window_aggregates",
                        "row_count": 40,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            transaction_stage_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": transaction_stage_run_id,
                        "extraction_stage": "completed_transaction_aggregates",
                        "row_count": 40,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_telemetry_json_path(base_stage_run_id).write_text(
                json.dumps({"total_elapsed_seconds": 9.0}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.extraction_telemetry_json_path(window_stage_run_id).write_text(
                json.dumps({"total_elapsed_seconds": 2.0}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.extraction_telemetry_json_path(transaction_stage_run_id).write_text(
                json.dumps({"total_elapsed_seconds": 2.0}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.sql_diagnostics_summary_json_path(base_stage_run_id).write_text(
                json.dumps(
                    {
                        "extraction_status": "failed",
                        "current_sql_subphase": "SQL executing",
                        "failure_message": "timeout",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.sql_diagnostics_summary_json_path(window_stage_run_id).write_text(
                json.dumps({"extraction_status": "succeeded"}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.sql_diagnostics_summary_json_path(transaction_stage_run_id).write_text(
                json.dumps({"extraction_status": "succeeded"}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_completion_path(base_stage_run_id).write_text(
                json.dumps(
                    {
                        "run_id": base_stage_run_id,
                        "partition_completion_state": "finalized",
                        "completion_state": "finalized",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_completion_path(window_stage_run_id).write_text(
                json.dumps(
                    {
                        "run_id": window_stage_run_id,
                        "partition_completion_state": "finalized",
                        "completion_state": "finalized",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_completion_path(
                transaction_stage_run_id
            ).write_text(
                json.dumps(
                    {
                        "run_id": transaction_stage_run_id,
                        "partition_completion_state": "finalized",
                        "completion_state": "finalized",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            for stage_run_id in (
                base_stage_run_id,
                window_stage_run_id,
                transaction_stage_run_id,
            ):
                artifact_paths.manifests_run_root(stage_run_id).mkdir(parents=True, exist_ok=True)
                (artifact_paths.manifests_run_root(stage_run_id) / "rendered_sql.sql").write_text(
                    "SELECT 1\n",
                    encoding="utf-8",
                )
            artifact_paths.extraction_telemetry_json_path(batch_run_id).write_text(
                json.dumps({"total_elapsed_seconds": 1.0}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_completion_path(batch_run_id).write_text(
                json.dumps(
                    {
                        "run_id": batch_run_id,
                        "partition_completion_state": "finalized",
                        "completion_state": "finalized",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            summary = collect_completed_stage3_validation_summary(
                artifact_paths=artifact_paths,
                run_id=run_id,
            )

            self.assertEqual(summary.follow_up.status, "failure")
            self.assertEqual(summary.follow_up.total_candidate_rows, 120)
            self.assertEqual(summary.follow_up.failure_classification, "SQL execution problem")
            self.assertEqual(
                summary.follow_up.failure_summary,
                "Stage 3 follow-up detected a failure classified as: SQL execution problem.",
            )
            self.assertFalse(summary.follow_up.safe_to_resume_reuse)

    def test_collect_completed_stage3_validation_summary_returns_preflight_rejected_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            run_id = "completed-preflight-rejected-run"
            preflight_summary_path = artifact_paths.extraction_preflight_summary_json_path(run_id)
            preflight_summary_path.parent.mkdir(parents=True, exist_ok=True)
            preflight_summary_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "verdict": "TOO_WIDE_REPARTITION_REQUIRED",
                        "reason": "candidate_window_span_days_max exceeds threshold",
                        "recommended_partition_strategy": "promotion_row_key_hash_bucket",
                        "recommended_partition_count": 30,
                        "observed_max_grouped_live_window_span_days": 73,
                        "observed_max_live_promo_days": 73,
                        "theoretical_completed_window_span_days_max": 143,
                        "partition_index": 1,
                        "partition_count": 24,
                        "candidate_promotion_row_count": 1121,
                        "rendered_query_parameter_summary": {
                            "completed_sales_history_start_date": "2024-01-01"
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.rendered_preflight_sql_path(run_id).write_text(
                "SELECT 1\n",
                encoding="utf-8",
            )

            summary = collect_completed_stage3_validation_summary(
                artifact_paths=artifact_paths,
                run_id=run_id,
            )

            self.assertEqual(summary.partition_index, 1)
            self.assertEqual(summary.partition_count, 24)
            self.assertEqual(summary.completed_sales_history_start_date, "2024-01-01")
            self.assertEqual(summary.records, ())
            self.assertEqual(summary.follow_up.status, "preflight_rejected_before_stage3")
            self.assertEqual(summary.follow_up.failure_classification, "SQL planning problem")
            self.assertEqual(summary.follow_up.planner_verdict, "TOO_WIDE_REPARTITION_REQUIRED")
            self.assertEqual(summary.follow_up.recommended_partition_count, 30)
            self.assertEqual(
                summary.follow_up.recommended_partition_strategy,
                "promotion_row_key_hash_bucket",
            )
            self.assertEqual(summary.follow_up.observed_max_grouped_live_window_span_days, 73)
            self.assertEqual(summary.follow_up.observed_max_live_promo_days, 73)
            self.assertEqual(summary.follow_up.theoretical_completed_window_span_days_max, 143)
            self.assertTrue(
                (summary.follow_up.preflight_summary_json_path or "").endswith(
                    "extraction_preflight_summary.json"
                )
            )
            self.assertTrue(
                (summary.follow_up.rendered_preflight_sql_path or "").endswith(
                    "rendered_preflight_sql.sql"
                )
            )
            self.assertIn("No Stage 3 extraction artifacts exist yet", summary.follow_up.note or "")


if __name__ == "__main__":
    unittest.main()
