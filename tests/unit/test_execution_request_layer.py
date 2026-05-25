from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from data.ingestion.raw_ingestion_pipeline import (  # noqa: E402
    RawIngestionCommand,
)
from decision.output import ActionInstructionRequest  # noqa: E402
from execution import (  # noqa: E402
    ExecutionRequestAuditAdapter,
    ExecutionRequestRequest,
    ExecutionRequestService,
    JsonExecutionRequestRegistry,
)
from state.features.feature_registry import FeatureDefinition  # noqa: E402
from tests.unit import test_action_instruction_layer as action_instruction_test_module  # noqa: E402


class ExecutionRequestLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = action_instruction_test_module.ActionInstructionLayerTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.review_service = self.helpers.review_service
        self.packet_builder = self.helpers.packet_builder
        self.resolution_service = self.helpers.resolution_service
        self.recommendation_service = self.helpers.recommendation_service
        self.policy_output_service = self.helpers.policy_output_service
        self.portfolio_output_service = self.helpers.portfolio_output_service
        self.action_instruction_service = self.helpers.action_instruction_service
        self.feature_registry = self.helpers.feature_registry
        self.execution_request_service = self._build_execution_request_service()

    def test_successful_execution_request_from_legitimate_action_instruction(self) -> None:
        action_instruction = self._build_direct_action_instruction(impact_score=0.76)

        execution_request = self.execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=action_instruction,
                execution_request_class_id="direct_dispatch_request",
                execution_request_author_role="case_operator",
                execution_request_context=self._direct_execution_request_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-request-test",
            )
        )

        self.assertEqual(
            execution_request.execution_request_status,
            "ready_for_downstream_use",
        )
        self.assertEqual(execution_request.execution_request_readiness, "dispatch_ready")
        self.assertEqual(
            execution_request.action_boundary_posture,
            "request_ready_non_executing",
        )

    def test_blocked_execution_request_due_to_missing_required_context(self) -> None:
        action_instruction = self._build_prerequisite_action_instruction(impact_score=0.55)

        execution_request = self.execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=action_instruction,
                execution_request_class_id="prerequisite_dispatch_request",
                execution_request_author_role="case_operator",
                execution_request_context={
                    "execution_request_summary": "Preserve a governed clarification dispatch request until the missing prerequisite is resolved."
                },
                correlation_id=str(uuid4()),
                actor_id="execution-request-test",
            )
        )

        self.assertEqual(execution_request.execution_request_status, "blocked")
        self.assertIn(
            "execution_target_reference",
            execution_request.missing_execution_request_fields,
        )

    def test_fallback_template_usage(self) -> None:
        action_instruction = self._build_fallback_action_instruction()

        execution_request = self.execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=action_instruction,
                execution_request_class_id="hold_dispatch_request",
                execution_request_author_role="case_operator",
                execution_request_context=self._fallback_execution_request_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-request-test",
            )
        )

        self.assertEqual(
            execution_request.execution_request_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            execution_request.execution_request_template_id,
            "hold_execution_request_fallback",
        )

    def test_execution_request_completeness_and_lineage_mapping(self) -> None:
        action_instruction = self._build_prerequisite_action_instruction(impact_score=0.55)

        execution_request = self.execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=action_instruction,
                execution_request_class_id="prerequisite_dispatch_request",
                execution_request_author_role="case_operator",
                execution_request_context=self._prerequisite_execution_request_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-request-test",
            )
        )

        self.assertEqual(
            execution_request.required_execution_request_snapshot[
                "clarification_reference"
            ],
            "clarification-placeholder-001",
        )
        self.assertEqual(
            execution_request.execution_request_readiness,
            "dispatch_blocked_pending_prerequisite",
        )
        self.assertEqual(
            execution_request.lineage["action_instruction_id"],
            action_instruction.action_instruction_id,
        )
        self.assertEqual(
            execution_request.lineage["execution_request_template_id"],
            execution_request.execution_request_template_id,
        )

    def test_integration_with_lifecycle_authority_router_review_policy_portfolio_action_instruction_and_execution_request_path(
        self,
    ) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description="Expected revenue delta used to seed execution-request tests.",
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
            actor_id="execution-request-test",
        )
        raw_pipeline = self.helpers._build_raw_pipeline()
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
            actor_id="execution-request-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-001",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="execution-request-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="execution-request-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason="Assessment should emit a governed execution request only after action-instruction generation.",
            correlation_id=correlation_id,
            actor_id="execution-request-test",
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
            action_instruction_context=self.helpers._action_instruction_context(),
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=self._direct_execution_request_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(payload["execution_request_status"], "ready_for_downstream_use")
        self.assertEqual(
            payload["execution_request_class_id"],
            "direct_dispatch_request",
        )
        self.assertEqual(
            payload["execution_request_action_boundary_posture"],
            "request_ready_non_executing",
        )
        self.assertEqual(payload["execution_request_readiness"], "dispatch_ready")

    def test_audit_emission_for_execution_request_outcomes(self) -> None:
        direct_action_instruction = self._build_direct_action_instruction(impact_score=0.76)
        prerequisite_action_instruction = self._build_prerequisite_action_instruction(
            impact_score=0.55
        )
        fallback_action_instruction = self._build_fallback_action_instruction()

        self.execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=direct_action_instruction,
                execution_request_class_id="direct_dispatch_request",
                execution_request_author_role="case_operator",
                execution_request_context=self._direct_execution_request_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-request-test",
            )
        )
        self.execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=prerequisite_action_instruction,
                execution_request_class_id="prerequisite_dispatch_request",
                execution_request_author_role="case_operator",
                execution_request_context={
                    "execution_request_summary": "This request should block because required execution-request fields are missing."
                },
                correlation_id=str(uuid4()),
                actor_id="execution-request-test",
            )
        )
        self.execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=fallback_action_instruction,
                execution_request_class_id="hold_dispatch_request",
                execution_request_author_role="case_operator",
                execution_request_context=self._fallback_execution_request_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-request-test",
            )
        )

        event_types = self._event_types()
        self.assertIn("execution_request_recorded", event_types)
        self.assertIn("execution_request_blocked", event_types)
        self.assertIn("execution_request_ready_for_downstream_use", event_types)
        self.assertIn("execution_request_missing_context", event_types)
        self.assertIn("execution_request_fallback_template_applied", event_types)

    def _build_execution_request_service(self) -> ExecutionRequestService:
        execution_request_registry = JsonExecutionRequestRegistry(
            execution_request_classes_path=(
                self.registry_root / "execution_request_classes.json"
            ),
            execution_request_templates_path=(
                self.registry_root / "execution_request_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        execution_request_audit_adapter = ExecutionRequestAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ExecutionRequestService(
            execution_request_registry=execution_request_registry,
            execution_request_audit_adapter=execution_request_audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._execution_request_service = self.execution_request_service
        return orchestrator

    def _build_direct_action_instruction(self, *, impact_score: float):
        portfolio_output = self.helpers._build_action_portfolio_output(
            impact_score=impact_score
        )
        return self.action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=portfolio_output,
                action_instruction_class_id="direct_action_instruction",
                instruction_author_role="case_operator",
                action_instruction_context=self.helpers._action_instruction_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-request-test",
            )
        )

    def _build_prerequisite_action_instruction(self, *, impact_score: float):
        portfolio_output = self.helpers._build_information_portfolio_output(
            impact_score=impact_score
        )
        return self.action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=portfolio_output,
                action_instruction_class_id="prerequisite_bounded_instruction",
                instruction_author_role="case_operator",
                action_instruction_context=self.helpers._prerequisite_action_instruction_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-request-test",
            )
        )

    def _build_fallback_action_instruction(self):
        portfolio_output = self.helpers._build_fallback_portfolio_output()
        return self.action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=portfolio_output,
                action_instruction_class_id="suppression_hold_instruction",
                instruction_author_role="case_operator",
                action_instruction_context=self.helpers._fallback_action_instruction_context(),
                correlation_id=str(uuid4()),
                actor_id="execution-request-test",
            )
        )

    def _direct_execution_request_context(self) -> dict[str, object]:
        return {
            "execution_request_summary": "Prepare a governed dispatch request while keeping execution separate from request legitimacy.",
            "execution_request_reference": "execution-request:direct-001",
            "execution_target_reference": "execution-target:price-adjustment-001",
            "execution_scope_reference": "scope:store:001:price-adjustment-window",
            "execution_timing_reference": "timing:price-adjustment-window",
            "execution_request_channel": "governed_dispatch_handoff",
            "execution_payload_reference": "dispatch-payload:price-adjustment-001",
            "execution_priority_reference": "dispatch-priority:high",
        }

    def _prerequisite_execution_request_context(self) -> dict[str, object]:
        return {
            "execution_request_summary": "Preserve a governed clarification dispatch request until the prerequisite gap is resolved.",
            "execution_request_reference": "execution-request:clarification-001",
            "execution_target_reference": "execution-target:clarification-request-001",
            "execution_scope_reference": "scope:store:001:clarification-loop",
            "execution_timing_reference": "timing:clarification-window",
            "execution_request_channel": "manual_clarification_handoff",
            "execution_payload_reference": "dispatch-payload:clarification-request-001",
            "execution_priority_reference": "dispatch-priority:clarification",
        }

    def _fallback_execution_request_context(self) -> dict[str, object]:
        return {
            "execution_request_summary": "Preserve a governed hold-only execution request until a later governed reviewer revisits the case.",
            "execution_request_reference": "execution-request:fallback-001",
            "execution_target_reference": "execution-target:manual-triage-hold-001",
            "execution_scope_reference": "scope:store:001:manual-triage-hold",
            "execution_timing_reference": "timing:manual-triage-window",
            "execution_request_channel": "manual_triage_handoff",
            "execution_payload_reference": "dispatch-payload:manual-triage-hold-001",
            "execution_priority_reference": "dispatch-priority:hold",
        }

    def _event_types(self) -> list[str]:
        return [event.event_type for event in self.audit_store.list_events()]


if __name__ == "__main__":
    unittest.main()