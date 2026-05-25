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
    ExecutionDispatchAuditAdapter,
    ExecutionDispatchBoundaryRequest,
    ExecutionDispatchBoundaryService,
    ExecutionRequestRequest,
    JsonExecutionDispatchRegistry,
)
from state.features.feature_registry import FeatureDefinition  # noqa: E402
from tests.unit import test_execution_request_layer as execution_request_test_module  # noqa: E402


class ExecutionDispatchLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = execution_request_test_module.ExecutionRequestLayerTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.feature_registry = self.helpers.feature_registry
        self.execution_request_service = self.helpers.execution_request_service
        self.execution_dispatch_service = self._build_execution_dispatch_service()

    def test_successful_execution_dispatch_from_legitimate_execution_request(self) -> None:
        execution_request = self._build_direct_execution_request(impact_score=0.76)

        execution_dispatch = self.execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=execution_request,
                execution_dispatch_class_id="direct_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context=self._direct_execution_dispatch_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-dispatch-test",
            )
        )

        self.assertEqual(
            execution_dispatch.execution_dispatch_status,
            "ready_for_downstream_use",
        )
        self.assertEqual(
            execution_dispatch.execution_dispatch_readiness,
            "dispatch_boundary_ready",
        )
        self.assertEqual(
            execution_dispatch.dispatch_boundary_posture,
            "dispatch_boundary_ready_non_executing",
        )

    def test_blocked_execution_dispatch_due_to_missing_required_context(self) -> None:
        execution_request = self._build_prerequisite_execution_request(impact_score=0.55)

        execution_dispatch = self.execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=execution_request,
                execution_dispatch_class_id="conditioned_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context={
                    "dispatch_summary": "This dispatch boundary should block because required dispatch fields are missing."
                },
                correlation_id=str(uuid4()),
                actor_id="execution-dispatch-test",
            )
        )

        self.assertEqual(execution_dispatch.execution_dispatch_status, "blocked")
        self.assertIn(
            "dispatch_reference",
            execution_dispatch.missing_execution_dispatch_fields,
        )

    def test_fallback_template_usage(self) -> None:
        execution_request = self._build_fallback_execution_request()

        execution_dispatch = self.execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=execution_request,
                execution_dispatch_class_id="hold_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context=self._fallback_execution_dispatch_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-dispatch-test",
            )
        )

        self.assertEqual(
            execution_dispatch.execution_dispatch_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            execution_dispatch.execution_dispatch_template_id,
            "hold_execution_dispatch_fallback",
        )

    def test_execution_dispatch_completeness_and_lineage_mapping(self) -> None:
        execution_request = self._build_prerequisite_execution_request(impact_score=0.55)

        execution_dispatch = self.execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=execution_request,
                execution_dispatch_class_id="conditioned_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context=self._prerequisite_execution_dispatch_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-dispatch-test",
            )
        )

        self.assertEqual(
            execution_dispatch.required_execution_dispatch_snapshot[
                "clarification_reference"
            ],
            "clarification-placeholder-001",
        )
        self.assertEqual(
            execution_dispatch.execution_dispatch_readiness,
            "dispatch_boundary_blocked_pending_prerequisite",
        )
        self.assertEqual(
            execution_dispatch.lineage["execution_request_id"],
            execution_request.execution_request_id,
        )
        self.assertEqual(
            execution_dispatch.lineage["execution_dispatch_template_id"],
            execution_dispatch.execution_dispatch_template_id,
        )

    def test_integration_with_lifecycle_through_execution_dispatch(self) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description="Expected revenue delta used to seed execution-dispatch tests.",
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
            actor_id="execution-dispatch-test",
        )
        raw_pipeline = self.helpers.helpers._build_raw_pipeline()
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
            actor_id="execution-dispatch-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-001",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="execution-dispatch-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="execution-dispatch-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason="Assessment should emit a governed execution dispatch boundary only after execution-request generation.",
            correlation_id=correlation_id,
            actor_id="execution-dispatch-test",
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
            action_instruction_context=self.helpers.helpers._action_instruction_context(),
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=self.helpers._direct_execution_request_context(),
            execution_dispatch_class_id="direct_dispatch_boundary",
            execution_dispatch_context=self._direct_execution_dispatch_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(
            payload["execution_dispatch_status"],
            "ready_for_downstream_use",
        )
        self.assertEqual(
            payload["execution_dispatch_class_id"],
            "direct_dispatch_boundary",
        )
        self.assertEqual(
            payload["execution_dispatch_boundary_posture"],
            "dispatch_boundary_ready_non_executing",
        )
        self.assertEqual(
            payload["execution_dispatch_readiness"],
            "dispatch_boundary_ready",
        )

    def test_audit_emission_for_execution_dispatch_outcomes(self) -> None:
        direct_execution_request = self._build_direct_execution_request(impact_score=0.76)
        prerequisite_execution_request = self._build_prerequisite_execution_request(
            impact_score=0.55
        )
        fallback_execution_request = self._build_fallback_execution_request()

        self.execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=direct_execution_request,
                execution_dispatch_class_id="direct_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context=self._direct_execution_dispatch_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-dispatch-test",
            )
        )
        self.execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=prerequisite_execution_request,
                execution_dispatch_class_id="conditioned_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context={
                    "dispatch_summary": "This dispatch boundary should block because required dispatch fields are missing."
                },
                correlation_id=str(uuid4()),
                actor_id="execution-dispatch-test",
            )
        )
        self.execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=fallback_execution_request,
                execution_dispatch_class_id="hold_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context=self._fallback_execution_dispatch_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-dispatch-test",
            )
        )

        event_types = self._event_types()
        self.assertIn("execution_dispatch_recorded", event_types)
        self.assertIn("execution_dispatch_blocked", event_types)
        self.assertIn("execution_dispatch_ready_for_downstream_use", event_types)
        self.assertIn("execution_dispatch_missing_context", event_types)
        self.assertIn("execution_dispatch_fallback_template_applied", event_types)

    def _build_execution_dispatch_service(self) -> ExecutionDispatchBoundaryService:
        execution_dispatch_registry = JsonExecutionDispatchRegistry(
            execution_dispatch_classes_path=(
                self.registry_root / "execution_dispatch_classes.json"
            ),
            execution_dispatch_templates_path=(
                self.registry_root / "execution_dispatch_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        execution_dispatch_audit_adapter = ExecutionDispatchAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ExecutionDispatchBoundaryService(
            execution_dispatch_registry=execution_dispatch_registry,
            execution_dispatch_audit_adapter=execution_dispatch_audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._execution_request_service = self.execution_request_service
        orchestrator._state_manager._execution_dispatch_service = (
            self.execution_dispatch_service
        )
        return orchestrator

    def _build_direct_execution_request(self, *, impact_score: float):
        action_instruction = self.helpers._build_direct_action_instruction(
            impact_score=impact_score
        )
        return self._build_execution_request(
            action_instruction=action_instruction,
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=self.helpers._direct_execution_request_context(),
        )

    def _build_prerequisite_execution_request(self, *, impact_score: float):
        action_instruction = self.helpers._build_prerequisite_action_instruction(
            impact_score=impact_score
        )
        return self._build_execution_request(
            action_instruction=action_instruction,
            execution_request_class_id="prerequisite_dispatch_request",
            execution_request_context=self.helpers._prerequisite_execution_request_context(),
        )

    def _build_fallback_execution_request(self):
        action_instruction = self.helpers._build_fallback_action_instruction()
        return self._build_execution_request(
            action_instruction=action_instruction,
            execution_request_class_id="hold_dispatch_request",
            execution_request_context=self.helpers._fallback_execution_request_context(),
        )

    def _build_execution_request(
        self,
        *,
        action_instruction,
        execution_request_class_id: str,
        execution_request_context: dict[str, object],
    ):
        return self.execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=action_instruction,
                execution_request_class_id=execution_request_class_id,
                execution_request_author_role="case_operator",
                execution_request_context=execution_request_context,
                correlation_id=str(uuid4()),
                actor_id="execution-dispatch-test",
            )
        )

    def _direct_execution_dispatch_context(self) -> dict[str, object]:
        return {
            "dispatch_summary": "Materialize a governed execution-dispatch boundary while keeping broker placement and actual execution separate.",
            "dispatch_reference": "execution-dispatch:direct-001",
            "dispatch_channel": "governed_dispatch_boundary_handoff",
            "dispatch_payload_reference": "dispatch-boundary-payload:direct-001",
            "dispatch_window_reference": "dispatch-window:price-adjustment-window",
            "dispatch_priority_reference": "dispatch-priority:high",
        }

    def _prerequisite_execution_dispatch_context(self) -> dict[str, object]:
        return {
            "dispatch_summary": "Preserve a governed clarification dispatch boundary until the prerequisite gap is resolved.",
            "dispatch_reference": "execution-dispatch:clarification-001",
            "dispatch_channel": "manual_clarification_boundary_handoff",
            "dispatch_payload_reference": "dispatch-boundary-payload:clarification-001",
            "dispatch_window_reference": "dispatch-window:clarification-loop",
            "dispatch_priority_reference": "dispatch-priority:clarification",
        }

    def _fallback_execution_dispatch_context(self) -> dict[str, object]:
        return {
            "dispatch_summary": "Preserve a governed hold-only execution-dispatch boundary until a later reviewer revisits the case.",
            "dispatch_reference": "execution-dispatch:hold-001",
            "dispatch_channel": "manual_hold_boundary_handoff",
            "dispatch_hold_reference": "dispatch-hold:manual-triage-001",
            "dispatch_window_reference": "dispatch-window:manual-triage-hold",
            "dispatch_priority_reference": "dispatch-priority:hold",
        }

    def _event_types(self) -> set[str]:
        return {event.event_type for event in self.audit_store.list_events()}


if __name__ == "__main__":
    unittest.main()
