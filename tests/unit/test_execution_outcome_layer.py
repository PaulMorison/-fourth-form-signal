from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from data.ingestion.raw_ingestion_pipeline import RawIngestionCommand  # noqa: E402
from execution import (  # noqa: E402
    ExecutionDispatchBoundaryRequest,
    ExecutionOutcomeAuditAdapter,
    ExecutionOutcomeCaptureRequest,
    ExecutionOutcomeCaptureService,
    JsonExecutionOutcomeRegistry,
)
from state.features.feature_registry import FeatureDefinition  # noqa: E402
from tests.unit import test_execution_dispatch_layer as dispatch_test_module  # noqa: E402


class ExecutionOutcomeLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = dispatch_test_module.ExecutionDispatchLayerTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.execution_dispatch_service = self.helpers.execution_dispatch_service
        self.execution_outcome_service = self._build_execution_outcome_service()

    def test_successful_execution_outcome_from_legitimate_dispatch(self) -> None:
        execution_dispatch = self._build_direct_execution_dispatch(impact_score=0.76)

        execution_outcome = self.execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=execution_dispatch,
                execution_outcome_class_id="favorable_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context=self._favorable_outcome_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-outcome-test",
            )
        )

        self.assertEqual(
            execution_outcome.execution_outcome_status,
            "ready_for_downstream_use",
        )
        self.assertEqual(
            execution_outcome.feedback_capture_readiness,
            "feedback_capture_ready_for_post_mortem",
        )
        self.assertEqual(
            execution_outcome.expected_relation,
            "realized_matches_expected_path",
        )
        self.assertEqual(
            execution_outcome.comparison_posture,
            "comparison_ready_expected_matches_realized",
        )

    def test_blocked_execution_outcome_due_to_missing_required_context(self) -> None:
        execution_dispatch = self._build_direct_execution_dispatch(impact_score=0.76)

        execution_outcome = self.execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=execution_dispatch,
                execution_outcome_class_id="negative_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context={
                    "observation_basis": "post_dispatch_observation",
                    "observation_horizon_reference": "horizon:t-plus-7d",
                },
                correlation_id=str(uuid4()),
                actor_id="execution-outcome-test",
            )
        )

        self.assertEqual(execution_outcome.execution_outcome_status, "blocked")
        self.assertIn(
            "executed_action_reference",
            execution_outcome.missing_execution_outcome_fields,
        )
        self.assertIn(
            "realized_outcome_reference",
            execution_outcome.missing_execution_outcome_fields,
        )

    def test_fallback_template_usage(self) -> None:
        execution_dispatch = self._build_fallback_execution_dispatch()

        execution_outcome = self.execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=execution_dispatch,
                execution_outcome_class_id="deferred_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context=self._deferred_outcome_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-outcome-test",
            )
        )

        self.assertEqual(
            execution_outcome.execution_outcome_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            execution_outcome.execution_outcome_template_id,
            "deferred_execution_outcome_fallback",
        )
        self.assertEqual(
            execution_outcome.feedback_capture_readiness,
            "feedback_capture_deferred",
        )

    def test_execution_outcome_completeness_and_lineage_mapping(self) -> None:
        execution_dispatch = self._build_direct_execution_dispatch(impact_score=0.76)

        execution_outcome = self.execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=execution_dispatch,
                execution_outcome_class_id="favorable_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context=self._favorable_outcome_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-outcome-test",
            )
        )

        self.assertEqual(
            execution_outcome.required_execution_outcome_snapshot[
                "decision_scope_reference"
            ],
            "scope:store:001",
        )
        self.assertEqual(
            execution_outcome.lineage["execution_dispatch_id"],
            execution_dispatch.execution_dispatch_id,
        )
        self.assertEqual(
            execution_outcome.lineage["execution_outcome_template_id"],
            execution_outcome.execution_outcome_template_id,
        )
        self.assertEqual(
            execution_outcome.recommendation_id,
            execution_dispatch.lineage["recommendation_id"],
        )

    def test_deviation_capture_between_dispatch_intent_and_observed_result(self) -> None:
        execution_dispatch = self._build_direct_execution_dispatch(impact_score=0.76)

        execution_outcome = self.execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=execution_dispatch,
                execution_outcome_class_id="negative_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context=self._negative_deviation_outcome_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-outcome-test",
            )
        )

        self.assertEqual(
            execution_outcome.expected_relation,
            "realized_deviates_from_expected_path",
        )
        self.assertEqual(
            execution_outcome.comparison_posture,
            "comparison_ready_expected_differs_from_realized",
        )
        self.assertEqual(execution_outcome.realized_result_class, "negative")

    def test_audit_emission_for_execution_outcome_outcomes(self) -> None:
        direct_execution_dispatch = self._build_direct_execution_dispatch(impact_score=0.76)
        fallback_execution_dispatch = self._build_fallback_execution_dispatch()

        self.execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=direct_execution_dispatch,
                execution_outcome_class_id="favorable_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context=self._favorable_outcome_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-outcome-test",
            )
        )
        self.execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=direct_execution_dispatch,
                execution_outcome_class_id="negative_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context={
                    "observation_basis": "post_dispatch_observation",
                    "observation_horizon_reference": "horizon:t-plus-7d",
                },
                correlation_id=str(uuid4()),
                actor_id="execution-outcome-test",
            )
        )
        self.execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=fallback_execution_dispatch,
                execution_outcome_class_id="deferred_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context=self._deferred_outcome_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-outcome-test",
            )
        )

        event_types = self._event_types()
        self.assertIn("execution_outcome_recorded", event_types)
        self.assertIn("execution_outcome_blocked", event_types)
        self.assertIn("execution_outcome_ready_for_downstream_use", event_types)
        self.assertIn("execution_outcome_missing_context", event_types)
        self.assertIn("execution_outcome_fallback_template_applied", event_types)

    def test_integration_with_lifecycle_through_execution_outcome(self) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.helpers.feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description="Expected revenue delta used to seed execution-outcome tests.",
                semantic_scope="shared_control_plane",
                formula="candidate_revenue - baseline_revenue",
                unit="currency",
                denominator=None,
                time_basis="event_time",
                window="7d",
                data_type="float",
                status="active",
                source_fields=("candidate_revenue", "baseline_revenue"),
                created_at=datetime.now(tz=UTC),
            ),
            correlation_id=str(uuid4()),
            actor_id="execution-outcome-test",
        )
        raw_pipeline = self.helpers.helpers.helpers._build_raw_pipeline()
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-001",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-001",
                        "candidate_revenue": 1200.0,
                        "baseline_revenue": 1000.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="execution-outcome-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-001",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="execution-outcome-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="execution-outcome-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason="Assessment should emit a governed execution outcome only after legitimate dispatch boundary capture.",
            correlation_id=correlation_id,
            actor_id="execution-outcome-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": "Assess whether the elevated impact score warrants accountable manual review."
            },
            review_resolution_class_id="resolved_with_action",
            review_resolution_context={
                "review_summary": "The reviewer confirmed downstream action preparation is warranted.",
                "resolution_rationale": "The required review threshold and packet lineage support action routing.",
            },
            recommendation_class_id="recommend_act_now",
            recommendation_context={
                "recommendation_summary": "Act now while preserving the recommendation boundary.",
                "action_path_reference": "action-path:price-adjustment-001",
                "scope_reference": "scope:store:001",
                "confidence_summary": "high_confidence",
                "constraint_summary": "inventory_and_margin_checked",
                "uncertainty_summary": "remaining_regime_uncertainty_is_bounded",
                "failure_state_context": "no_active_failure_state_detected",
            },
            policy_output_class_id="policy_shaped_allowance",
            policy_output_context={
                "policy_summary": "Preserve bounded allowance for downstream action preparation.",
                "policy_output_reference": "policy-output:allowance-001",
                "policy_rationale": "Recommendation and review lineage justify bounded policy allowance while preserving action-boundary discipline.",
                "action_boundary_summary": "Policy-shaped allowance only; downstream commitment and instruction remain separate.",
                "allowance_reference": "allowance:store:001:price-adjustment-window",
            },
            portfolio_output_class_id="portfolio_bounded_allocation",
            portfolio_output_context={
                "portfolio_summary": "Preserve bounded allocation posture for downstream portfolio planning.",
                "portfolio_output_reference": "portfolio-output:allocation-001",
                "portfolio_rationale": "Policy allowance lineage justifies bounded allocation posture for downstream planning.",
                "action_boundary_summary": "Allocative only; downstream commitment and instruction remain separate.",
                "allocation_reference": "allocation:store:001:price-adjustment-window",
                "allocation_weight_reference": "allocation-weight:store:001:0.72",
            },
            action_instruction_class_id="direct_action_instruction",
            action_instruction_context=self.helpers.helpers.helpers._action_instruction_context(),
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=self.helpers.helpers._direct_execution_request_context(),
            execution_dispatch_class_id="direct_dispatch_boundary",
            execution_dispatch_context=self.helpers._direct_execution_dispatch_context(),
            execution_outcome_class_id="favorable_realized_outcome",
            execution_outcome_context=self._favorable_outcome_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(
            payload["execution_outcome_status"],
            "ready_for_downstream_use",
        )
        self.assertEqual(
            payload["execution_outcome_class_id"],
            "favorable_realized_outcome",
        )
        self.assertEqual(
            payload["execution_outcome_realized_result_class"],
            "favorable",
        )
        self.assertEqual(
            payload["execution_outcome_expected_relation"],
            "realized_matches_expected_path",
        )

    def _build_execution_outcome_service(self) -> ExecutionOutcomeCaptureService:
        execution_outcome_registry = JsonExecutionOutcomeRegistry(
            execution_outcome_classes_path=(
                self.registry_root / "execution_outcome_classes.json"
            ),
            execution_outcome_templates_path=(
                self.registry_root / "execution_outcome_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        execution_outcome_audit_adapter = ExecutionOutcomeAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ExecutionOutcomeCaptureService(
            execution_outcome_registry=execution_outcome_registry,
            execution_outcome_audit_adapter=execution_outcome_audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._execution_outcome_service = (
            self.execution_outcome_service
        )
        return orchestrator

    def _build_direct_execution_dispatch(self, *, impact_score: float):
        execution_request = self.helpers._build_direct_execution_request(
            impact_score=impact_score
        )
        return self.execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=execution_request,
                execution_dispatch_class_id="direct_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context=self.helpers._direct_execution_dispatch_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-outcome-test",
            )
        )

    def _build_fallback_execution_dispatch(self):
        execution_request = self.helpers._build_fallback_execution_request()
        return self.execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=execution_request,
                execution_dispatch_class_id="hold_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context=self.helpers._fallback_execution_dispatch_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-outcome-test",
            )
        )

    def _favorable_outcome_context(self) -> dict[str, object]:
        return {
            "observation_basis": "post_dispatch_observation",
            "observation_horizon_reference": "horizon:t-plus-7d",
            "comparison_basis": "dispatch_target_vs_observed_execution",
            "feedback_maturity_posture": "stabilized_observation",
            "feedback_reuse_boundary": "governed_post_mortem_and_memory_only",
            "tenant_scope_reference": "tenant:store:001",
            "executed_action_reference": "execution-target:price-adjustment-001",
            "realized_outcome_reference": "outcome:revenue-improvement-001",
            "outcome_summary": "The governed dispatch intent was realized within the expected observation horizon.",
            "decision_scope_reference": "scope:store:001",
            "reporting_scope_reference": "reporting:store:001:weekly",
            "execution_condition_references": [
                "condition:inventory-available",
                "condition:margin-threshold-respected"
            ]
        }

    def _negative_deviation_outcome_context(self) -> dict[str, object]:
        return {
            "observation_basis": "post_dispatch_observation",
            "observation_horizon_reference": "horizon:t-plus-7d",
            "comparison_basis": "dispatch_target_vs_observed_execution",
            "feedback_maturity_posture": "stabilized_observation",
            "feedback_reuse_boundary": "governed_post_mortem_and_memory_only",
            "tenant_scope_reference": "tenant:store:001",
            "executed_action_reference": "execution-target:price-adjustment-002",
            "realized_outcome_reference": "outcome:margin-degradation-001",
            "outcome_summary": "The realized action diverged from the expected dispatch target and produced an explicit negative outcome.",
            "decision_scope_reference": "scope:store:001",
            "execution_condition_references": [
                "condition:inventory-constrained"
            ]
        }

    def _deferred_outcome_context(self) -> dict[str, object]:
        return {
            "observation_basis": "hold_boundary_observation",
            "observation_horizon_reference": "horizon:pending-review",
            "comparison_basis": "dispatch_hold_vs_later_observation",
            "feedback_maturity_posture": "preliminary_observation",
            "feedback_reuse_boundary": "local_operational_reuse_only",
            "tenant_scope_reference": "tenant:store:001",
            "non_execution_reference": "non-execution:manual-triage-hold",
            "realized_outcome_reference": "outcome:deferred-observation-001",
            "outcome_summary": "The bounded dispatch remains on hold, so the realized outcome stays explicitly deferred rather than silently favorable or neutral.",
            "decision_scope_reference": "scope:store:001:manual-triage-hold"
        }

    def _event_types(self) -> set[str]:
        return {event.event_type for event in self.audit_store.list_events()}


if __name__ == "__main__":
    unittest.main()