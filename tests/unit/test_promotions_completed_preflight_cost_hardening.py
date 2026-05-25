from __future__ import annotations

from datetime import UTC, date, datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from data.promotions.promotion_base_extractor import (  # noqa: E402
    PromotionExtractionPreflightArtifacts,
    PromotionExtractionPreflightResult,
    PromotionExtractionPreflightSummary,
)
from runtime.promotions.completed_extraction_cost_model import (  # noqa: E402
    CompletedExtractionCostModelEstimator,
    CompletedExtractionCostModelSettings,
    CompletedExtractionPreflightMetrics,
)
from runtime.promotions.config import (  # noqa: E402
    PromotionArtifactPaths,
    PromotionCompletedPreflightPlannerSettings,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
)
from runtime.promotions.run_promotions_operational_cycle import (  # noqa: E402
    COMPLETED_PROOF_SLICE_DATE_COUNT,
    PromotionCompletedPreflightRejectedError,
    _build_failure_final_outputs,
    _resolve_completed_preflight_proof_fallback,
    _resolve_completed_repartition_retry,
    _write_completed_preflight_cost_diagnostic,
)


class PromotionsCompletedPreflightCostHardeningTests(unittest.TestCase):
    def test_cost_model_handles_high_fixed_low_candidate_scenario(self) -> None:
        estimator = CompletedExtractionCostModelEstimator(
            settings=CompletedExtractionCostModelSettings(
                fixed_overhead_seconds=13.5,
                variable_cost_per_candidate_row_seconds=0.001,
                variable_cost_per_window_span_day_seconds=0.0005,
            )
        )
        estimation = estimator.estimate_extraction_cost(
            preflight_metrics=CompletedExtractionPreflightMetrics(
                observed_preflight_execution_seconds=14.551,
                candidate_promotion_row_count=95,
                candidate_store_sku_count=95,
                candidate_window_span_days_total=7784,
                candidate_window_span_days_max=120,
            ),
            query_timeout_seconds=60.0,
        )

        self.assertGreater(estimation.fixed_overhead_seconds, estimation.variable_cost_signal)
        self.assertGreater(estimation.estimated_extract_query_seconds, 13.5)
        self.assertGreaterEqual(estimation.estimated_cost_score, 0.0)

    def test_reduced_candidate_scope_does_not_force_explosive_partition_growth(self) -> None:
        estimator = CompletedExtractionCostModelEstimator(
            settings=CompletedExtractionCostModelSettings(
                fixed_overhead_seconds=13.5,
                variable_cost_per_candidate_row_seconds=0.001,
                variable_cost_per_window_span_day_seconds=0.0005,
            )
        )
        estimation_a = estimator.estimate_extraction_cost(
            preflight_metrics=CompletedExtractionPreflightMetrics(
                observed_preflight_execution_seconds=14.551,
                candidate_promotion_row_count=95,
                candidate_store_sku_count=95,
                candidate_window_span_days_total=7784,
                candidate_window_span_days_max=120,
            ),
            query_timeout_seconds=60.0,
        )
        estimation_b = estimator.estimate_extraction_cost(
            preflight_metrics=CompletedExtractionPreflightMetrics(
                observed_preflight_execution_seconds=13.816,
                candidate_promotion_row_count=40,
                candidate_store_sku_count=40,
                candidate_window_span_days_total=3182,
                candidate_window_span_days_max=120,
            ),
            query_timeout_seconds=60.0,
        )

        self.assertLess(
            estimation_b.estimated_extract_query_seconds,
            estimation_a.estimated_extract_query_seconds,
        )
        self.assertLessEqual(
            estimation_b.recommended_partition_count or 1,
            (estimation_a.recommended_partition_count or 1) + 1,
        )

    def test_proof_mode_fallback_is_available_only_in_proof_mode(self) -> None:
        preflight_result = self._build_preflight_result(
            verdict="TOO_WIDE_REPARTITION_REQUIRED",
            reason="slice is too expensive",
        )
        planner_settings = PromotionCompletedPreflightPlannerSettings(
            proof_completed_fallback_mode="diagnostic_topn",
            proof_completed_fallback_topn_limit=11,
        )

        query_options, fallback_mode, fallback_reason = _resolve_completed_preflight_proof_fallback(
            proof_mode=True,
            planner_settings=planner_settings,
            preflight_result=preflight_result,
        )
        self.assertIsNotNone(query_options)
        self.assertEqual(query_options.extraction_mode, "diagnostic_topn")
        self.assertEqual(query_options.limit_promotions, 11)
        self.assertEqual(fallback_mode, "diagnostic_topn")
        self.assertIn("falling back", fallback_reason or "")

        query_options_live, fallback_mode_live, _ = _resolve_completed_preflight_proof_fallback(
            proof_mode=False,
            planner_settings=planner_settings,
            preflight_result=preflight_result,
        )
        self.assertIsNone(query_options_live)
        self.assertIsNone(fallback_mode_live)

    def test_proof_slice_fallback_preserves_training_date_diversity(self) -> None:
        preflight_result = self._build_preflight_result(
            verdict="TOO_WIDE_REPARTITION_REQUIRED",
            reason="slice is too expensive",
        )
        planner_settings = PromotionCompletedPreflightPlannerSettings(
            proof_completed_fallback_mode="proof_slice",
            proof_completed_fallback_slice_promotion_count=17,
        )

        query_options, fallback_mode, fallback_reason = _resolve_completed_preflight_proof_fallback(
            proof_mode=True,
            planner_settings=planner_settings,
            preflight_result=preflight_result,
        )

        self.assertIsNotNone(query_options)
        self.assertEqual(query_options.extraction_mode, "diagnostic_topn")
        self.assertEqual(query_options.limit_promotions, 17)
        self.assertEqual(
            query_options.completed_proof_slice_date_count,
            COMPLETED_PROOF_SLICE_DATE_COUNT,
        )
        self.assertEqual(fallback_mode, "proof_slice")
        self.assertIn("promotion start dates", fallback_reason or "")

    def test_live_mode_fail_loud_repartition_rejection_still_enforces_governed_max(self) -> None:
        error = PromotionCompletedPreflightRejectedError("too expensive")
        setattr(error, "preflight_verdict", "TOO_WIDE_REPARTITION_REQUIRED")
        setattr(error, "recommended_partition_strategy", "store_sku_hash_bucket")
        setattr(error, "recommended_partition_count", 2048)

        next_partition_settings, retry_record, decision_reason = _resolve_completed_repartition_retry(
            run_id="run-a",
            current_partition_settings=None,
            error=error,
            planner_settings=PromotionCompletedPreflightPlannerSettings(
                max_completed_partition_count=512
            ),
            attempt_number=1,
        )

        self.assertIsNone(next_partition_settings)
        self.assertEqual(retry_record.status, "rejected_max_partition_count")
        self.assertIn("max_completed_partition_count 512", decision_reason)

    def test_completed_preflight_cost_diagnostic_artifact_contains_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-db",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=60,
                ),
                runtime_date=date(2024, 9, 1),
                artifacts=PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts"),
            )
            preflight_result = self._build_preflight_result(
                verdict="TOO_WIDE_REPARTITION_REQUIRED",
                reason="estimated extraction cost exceeds timeout budget",
            )
            path = _write_completed_preflight_cost_diagnostic(
                settings=settings,
                run_id="run-b",
                preflight_result=preflight_result,
                rejection_reason=preflight_result.summary.reason,
                proof_fallback_used=True,
                proof_fallback_mode="diagnostic_topn",
            )

            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertIn("old_heuristic_estimate_extract_query_seconds", payload)
            self.assertIn("new_model_estimate_extract_query_seconds", payload)
            self.assertEqual(payload["proof_fallback_used"], True)
            self.assertEqual(payload["proof_fallback_mode"], "diagnostic_topn")

    def test_failure_final_outputs_thread_new_stage3_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-db",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=60,
                ),
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
            )
            error = RuntimeError("stage3 failed")
            setattr(error, "completed_preflight_cost_diagnostic_path", "path/to/cost.json")
            setattr(error, "completed_proof_fallback_used", True)
            setattr(error, "completed_proof_fallback_mode", "diagnostic_topn")
            setattr(error, "completed_proof_fallback_reason", "test fallback reason")

            outputs = _build_failure_final_outputs(
                settings=settings,
                run_id="run-c",
                score_run_id="run-c-score",
                decision_surface_run_id="run-c-decision",
                manifest_path=artifact_paths.operational_cycle_manifest_path("run-c"),
                error=error,
            )

            self.assertIn("completed_preflight_cost_diagnostic_path", outputs)
            self.assertIn("completed_preflight_model_learning_diagnostic_path", outputs)
            self.assertEqual(outputs["completed_proof_fallback_used"], "true")
            self.assertEqual(outputs["completed_proof_fallback_mode"], "diagnostic_topn")

    def _build_preflight_result(self, *, verdict: str, reason: str) -> PromotionExtractionPreflightResult:
        summary = PromotionExtractionPreflightSummary(
            run_id="run-test",
            selection_mode="completed",
            extraction_mode="live_sql",
            as_of_date=date(2024, 9, 1).isoformat(),
            query_version="promotion_base_v4",
            preflight_status="succeeded",
            verdict=verdict,
            reason=reason,
            rendered_query_parameter_summary={},
            diagnostic_filter_summary={},
            estimated_window_summary={},
            planner_thresholds={
                "preflight_query_execution_seconds_multiplier": 20.0,
            },
            constraint_results={},
            candidate_promotion_row_count=95,
            candidate_store_sku_count=95,
            candidate_window_count=95,
            candidate_window_span_days_total=7784,
            candidate_window_span_days_max=120,
            estimated_cost_score=1.2,
            estimated_extract_query_seconds=72.0,
            fixed_overhead_seconds=13.5,
            variable_cost_signal=58.5,
            cost_model_version="v1_decomposed",
            phase_elapsed_seconds={"query_execution": 14.551},
        )
        artifacts = PromotionExtractionPreflightArtifacts(
            summary_json_path="/tmp/extraction_preflight_summary.json",
            summary_csv_path="/tmp/extraction_preflight_summary.csv",
            rendered_sql_path="/tmp/rendered_preflight_sql.sql",
            rendered_sql_parameters_path="/tmp/rendered_preflight_sql_parameters.json",
        )
        return PromotionExtractionPreflightResult(summary=summary, artifacts=artifacts)


class PromotionsCompletedPreflightPlannerConvergenceTests(unittest.TestCase):
    """Stage 6 planner must converge under hash-bucket skew within the
    configured repartition retry budget without rejecting valid workloads."""

    def _settings(self, *, multiplier: float = 1.5) -> PromotionPipelineSettings:
        return PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-db",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
                query_timeout_seconds=60,
            ),
            runtime_date=date(2024, 9, 1),
            artifacts=PromotionArtifactPaths(root=Path("/tmp/__planner_convergence__")),
            completed_preflight_planner=PromotionCompletedPreflightPlannerSettings(
                max_candidate_promotion_rows=2_000,
                max_candidate_store_sku=1_000,
                max_window_span_days_total=125_000,
                max_window_span_days_max=120,
                max_estimated_cost_score=1.0,
                repartition_skew_safety_multiplier=multiplier,
            ),
        )

    def _planner_decision(
        self,
        *,
        partition_count: int | None,
        candidate_promotion_row_count: int,
        candidate_window_span_days_max: int = 100,
        multiplier: float = 1.5,
    ):
        from data.promotions.promotion_base_extractor import _plan_preflight_verdict  # noqa: E402
        from data.promotions.sql.promotion_base_query import (  # noqa: E402
            PromotionBaseQueryOptions,
        )
        from data.promotions.mssql_query_executor import (  # noqa: E402
            PromotionSqlExecutionTelemetry,
        )
        from runtime.promotions.config import (  # noqa: E402
            PromotionCompletedPartitionSettings,
        )

        settings = self._settings(multiplier=multiplier)
        query_options = PromotionBaseQueryOptions(
            completed_partition=PromotionCompletedPartitionSettings(
                strategy="store_sku_hash_bucket",
                partition_count=partition_count,
                partition_index=1,
            )
            if partition_count is not None
            else None,
        )
        metrics = {
            "candidate_promotion_row_count": candidate_promotion_row_count,
            "candidate_store_sku_count": min(candidate_promotion_row_count, 500),
            "candidate_window_count": candidate_promotion_row_count,
            "candidate_window_span_days_total": candidate_promotion_row_count * 50,
            "candidate_window_span_days_max": candidate_window_span_days_max,
            "candidate_window_span_days_avg": 50,
            "candidate_global_min_date": "2024-01-01",
            "candidate_global_max_date": "2024-09-01",
            "distinct_store_count": 10,
            "distinct_sku_count": 50,
            "observed_max_grouped_live_window_span_days": 50,
            "observed_max_live_promo_days": 30,
        }
        telemetry = PromotionSqlExecutionTelemetry(
            connect_timeout_seconds=15,
            connect_retry_attempts=2,
            connect_retry_backoff_seconds=1.5,
            query_timeout_seconds=60,
            query_timeout_applied=True,
        )
        return _plan_preflight_verdict(
            selection_mode="completed",
            planner_settings=settings.completed_preflight_planner,
            settings=settings,
            query_options=query_options,
            metrics=metrics,
            sql_execution_telemetry=telemetry,
        )

    def test_default_repartition_attempt_budget_is_six(self) -> None:
        # The previous default of 3 was too tight to absorb hash-bucket skew;
        # the new authoritative default must be 6 so the planner has room to
        # converge before the operational cycle hard-rejects the run.
        self.assertEqual(
            PromotionCompletedPreflightPlannerSettings().max_completed_repartition_attempts,
            6,
        )

    def test_planner_recommendation_applies_skew_safety_multiplier(self) -> None:
        decision = self._planner_decision(
            partition_count=86,
            candidate_promotion_row_count=2_094,
            multiplier=1.5,
        )
        self.assertEqual(decision.verdict, "TOO_WIDE_REPARTITION_REQUIRED")
        self.assertEqual(decision.recommended_partition_strategy, "store_sku_hash_bucket")
        self.assertIsNotNone(decision.recommended_partition_count)
        # Old formula: max(87, ceil(86 * 1.047)) = 91 → fails to escape skew.
        # New formula: max(87, ceil(86 * 1.047 * 1.5)) >= 135 → escapes.
        self.assertGreaterEqual(decision.recommended_partition_count, 135)

    def test_multiplier_of_one_recovers_legacy_proportional_formula(self) -> None:
        decision = self._planner_decision(
            partition_count=86,
            candidate_promotion_row_count=2_094,
            multiplier=1.0,
        )
        # With multiplier = 1.0 we must match the historical behaviour exactly
        # so existing governance can opt out of skew anticipation if desired.
        self.assertEqual(decision.recommended_partition_count, 91)

    def test_window_span_max_does_not_get_skew_multiplied(self) -> None:
        # Per-row width metrics cannot be reduced by partitioning, so the
        # multiplier must NOT amplify the recommendation when window_span_max
        # is the dominant constraint. We keep proportional behaviour to allow
        # the existing fail-loud path to converge to rejection cleanly.
        decision = self._planner_decision(
            partition_count=10,
            candidate_promotion_row_count=500,
            candidate_window_span_days_max=240,  # 2x the 120 threshold
            multiplier=1.5,
        )
        self.assertEqual(decision.verdict, "TOO_WIDE_REPARTITION_REQUIRED")
        # 10 * 2.0 = 20 (without skew multiplier); skew multiplier would give 30.
        # We must observe 20, not 30.
        self.assertEqual(decision.recommended_partition_count, 20)

    def test_three_retries_converge_under_observed_production_skew(self) -> None:
        # Reproduces the exact failing live trace:
        #   attempt 1: full scope (170,960 rows) -> recommended count
        #   attempt 2: hot partition still 2,094 rows -> next count
        #   attempt 3: hot partition still 2,003 rows -> final count
        # Under the new skew-aware formula the planner should reach a
        # recommendation large enough that the hot-partition row count
        # (~170,960 / N) is comfortably under the 2,000 threshold.
        first = self._planner_decision(
            partition_count=None,
            candidate_promotion_row_count=170_960,
            multiplier=1.5,
        )
        self.assertEqual(first.verdict, "TOO_WIDE_REPARTITION_REQUIRED")
        self.assertIsNotNone(first.recommended_partition_count)
        n1 = first.recommended_partition_count

        second = self._planner_decision(
            partition_count=n1,
            candidate_promotion_row_count=2_094,
            multiplier=1.5,
        )
        n2 = second.recommended_partition_count

        third = self._planner_decision(
            partition_count=n2,
            candidate_promotion_row_count=2_003,
            multiplier=1.5,
        )
        n3 = third.recommended_partition_count

        # After three retries with the user's observed skew, the recommended
        # partition count must give the largest hot partition a healthy
        # margin under the 2,000 row threshold.
        self.assertGreaterEqual(n3, 200)
        average_hot_partition_load = 170_960 / n3
        self.assertLess(average_hot_partition_load, 2_000)

    def test_truly_unsafe_workloads_still_get_rejected_at_partition_cap(self) -> None:
        # A workload so wide that even the skew-safe recommendation exceeds
        # the governed max_completed_partition_count must still trigger the
        # explicit rejected_max_partition_count signal from the runtime.
        error = PromotionCompletedPreflightRejectedError("workload too wide for governed cap")
        setattr(error, "preflight_verdict", "TOO_WIDE_REPARTITION_REQUIRED")
        setattr(error, "recommended_partition_strategy", "store_sku_hash_bucket")
        setattr(error, "recommended_partition_count", 9_999)

        next_partition_settings, retry_record, decision_reason = _resolve_completed_repartition_retry(
            run_id="run-cap-protection",
            current_partition_settings=None,
            error=error,
            planner_settings=PromotionCompletedPreflightPlannerSettings(
                max_completed_partition_count=512,
            ),
            attempt_number=1,
        )
        self.assertIsNone(next_partition_settings)
        self.assertEqual(retry_record.status, "rejected_max_partition_count")
        self.assertIn("max_completed_partition_count 512", decision_reason)


if __name__ == "__main__":
    unittest.main()
