from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from decision.policy_learning import (  # noqa: E402
    JsonPolicyLearningUpdateMutationExecutionRegistry,
    PolicyLearningUpdateMutationExecutionAuditAdapter,
    PolicyLearningUpdateMutationExecutionRequest,
    PolicyLearningUpdateMutationExecutionService,
)
from tests.unit import test_policy_learning_update_mutation_planning_layer as mutation_planning_test_module  # noqa: E402


class PolicyLearningUpdateMutationExecutionLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = (
            mutation_planning_test_module.PolicyLearningUpdateMutationPlanningLayerTests(
                methodName="runTest"
            )
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.policy_learning_update_mutation_execution_service = (
            self._build_policy_learning_update_mutation_execution_service()
        )

    def test_direct_ready_for_policy_mutation_execution(self) -> None:
        mutation_planning_record = self._build_ready_update_mutation_planning()

        mutation_execution = self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=mutation_planning_record,
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self._executed_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )

        self.assertEqual(
            mutation_execution.policy_learning_update_mutation_execution_status,
            "mutation_execution_ready",
        )
        self.assertEqual(
            mutation_execution.policy_learning_update_mutation_execution_outcome,
            "ready_for_policy_mutation_execution",
        )
        self.assertEqual(
            mutation_execution.policy_mutation_execution_reference,
            "policy-mutation-execution:store:001:price-band",
        )

    def test_ready_for_policy_mutation_execution_with_restrictions(self) -> None:
        mutation_planning_record = self._build_restricted_update_mutation_planning()

        mutation_execution = self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=mutation_planning_record,
                policy_learning_update_mutation_execution_class_id=(
                    "restricted_policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self._restricted_execution_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )

        self.assertEqual(
            mutation_execution.policy_learning_update_mutation_execution_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            mutation_execution.policy_learning_update_mutation_execution_outcome,
            "ready_for_policy_mutation_execution_with_restrictions",
        )
        self.assertEqual(
            mutation_execution.mutation_execution_scope_restriction_reference,
            "scope:store:001:promo-window",
        )

    def test_deferred_pending_mutation_execution_prerequisites(self) -> None:
        mutation_planning_record = self._build_ready_update_mutation_planning()

        mutation_execution = self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=mutation_planning_record,
                policy_learning_update_mutation_execution_class_id=(
                    "deferred_policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self._deferred_execution_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )

        self.assertEqual(
            mutation_execution.policy_learning_update_mutation_execution_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            mutation_execution.policy_learning_update_mutation_execution_outcome,
            "deferred_pending_mutation_execution_prerequisites",
        )
        self.assertIn(
            "validation_checkpoint_confirmation",
            mutation_execution.outstanding_mutation_execution_prerequisites,
        )

    def test_blocked_missing_context(self) -> None:
        mutation_planning_record = self._build_ready_update_mutation_planning()

        mutation_execution = self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=mutation_planning_record,
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context={
                    "policy_mutation_execution_reference": (
                        "policy-mutation-execution:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )

        self.assertEqual(
            mutation_execution.policy_learning_update_mutation_execution_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "policy_mutation_payload",
            mutation_execution.missing_update_mutation_execution_fields,
        )
        self.assertIn(
            "mutation_execution_summary",
            mutation_execution.missing_update_mutation_execution_fields,
        )

    def test_rejected_for_mutation_execution_use(self) -> None:
        mutation_planning_record = self._build_ready_update_mutation_planning()

        mutation_execution = self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=mutation_planning_record,
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self._rejected_execution_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )

        self.assertEqual(
            mutation_execution.policy_learning_update_mutation_execution_status,
            "rejected_for_mutation_execution_use",
        )
        self.assertEqual(
            mutation_execution.policy_learning_update_mutation_execution_outcome,
            "rejected_for_mutation_execution_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        mutation_planning_record = self._build_ready_update_mutation_planning()

        mutation_execution = self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=mutation_planning_record,
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context={
                    **self._executed_context(),
                    "policy_rollout_reference": "policy-rollout:store:001:price-band",
                    "model_update_execution_reference": "model-update:policy:2026-04-24",
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )

        self.assertEqual(
            mutation_execution.policy_learning_update_mutation_execution_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "policy_rollout_reference",
            mutation_execution.prohibited_update_mutation_execution_fields_present,
        )
        self.assertIn(
            "model_update_execution_reference",
            mutation_execution.prohibited_update_mutation_execution_fields_present,
        )

    def test_lineage_preservation(self) -> None:
        mutation_planning_record = self._build_ready_update_mutation_planning()

        mutation_execution = self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=mutation_planning_record,
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self._executed_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )

        self.assertEqual(
            mutation_execution.lineage["policy_learning_update_mutation_planning_id"],
            mutation_planning_record.policy_learning_update_mutation_planning_id,
        )
        self.assertEqual(
            mutation_execution.lineage["recommendation_id"],
            mutation_planning_record.lineage["recommendation_id"],
        )
        self.assertEqual(
            mutation_execution.execution_outcome_id,
            mutation_planning_record.execution_outcome_id,
        )

    def test_audit_emission(self) -> None:
        ready_mutation_planning = self._build_ready_update_mutation_planning()
        restricted_mutation_planning = self._build_restricted_update_mutation_planning()

        self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=ready_mutation_planning,
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self._executed_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )
        self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=restricted_mutation_planning,
                policy_learning_update_mutation_execution_class_id=(
                    "restricted_policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self._restricted_execution_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )
        self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=ready_mutation_planning,
                policy_learning_update_mutation_execution_class_id=(
                    "deferred_policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self._deferred_execution_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )
        self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=ready_mutation_planning,
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context={
                    "policy_mutation_execution_reference": (
                        "policy-mutation-execution:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )
        self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=ready_mutation_planning,
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self._rejected_execution_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )
        self.policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=ready_mutation_planning,
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context={
                    **self._executed_context(),
                    "policy_rollout_reference": "policy-rollout:store:001:price-band"
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn(
            "decision.policy_learning.policy_learning_update_mutation_execution_recorded",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_mutation_execution_blocked",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_mutation_execution_ready_for_policy_mutation_execution",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_mutation_execution_ready_for_policy_mutation_execution_with_restrictions",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_mutation_execution_deferred_pending_mutation_execution_prerequisites",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_mutation_execution_missing_context",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_mutation_execution_rejected_for_mutation_execution_use",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_mutation_execution_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_mutation_execution_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_policy_learning_update_mutation_execution(
        self,
    ) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.feature_registry.register_feature(
            mutation_planning_test_module.approval_test_module.threshold_test_module.FeatureDefinition(
                name="shared.control.revenue_delta.policy_learning_update_mutation_execution",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description=(
                    "Expected revenue delta used to seed policy-learning update-mutation-execution tests."
                ),
                semantic_scope="shared_control_plane",
                formula="candidate_revenue - baseline_revenue",
                unit="currency",
                denominator=None,
                time_basis="event_time",
                window="7d",
                data_type="float",
                status="active",
                source_fields=("candidate_revenue", "baseline_revenue"),
                created_at=mutation_planning_test_module.approval_test_module.threshold_test_module.datetime.now(
                    tz=mutation_planning_test_module.approval_test_module.threshold_test_module.UTC
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="policy-learning-update-mutation-execution-test",
        )
        raw_pipeline = (
            self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._build_raw_pipeline()
        )
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                mutation_planning_test_module.approval_test_module.threshold_test_module.RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-007",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=mutation_planning_test_module.approval_test_module.threshold_test_module.datetime(
                        2026,
                        4,
                        22,
                        0,
                        0,
                        tzinfo=mutation_planning_test_module.approval_test_module.threshold_test_module.UTC,
                    ),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-007",
                        "candidate_revenue": 1865.0,
                        "baseline_revenue": 1508.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="policy-learning-update-mutation-execution-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-007",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="policy-learning-update-mutation-execution-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="policy-learning-update-mutation-execution-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should emit governed policy-learning update mutation execution only after governed mutation planning exists."
            ),
            correlation_id=correlation_id,
            actor_id="policy-learning-update-mutation-execution-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": (
                    "Assess whether the elevated impact score warrants accountable manual review."
                )
            },
            review_resolution_class_id="resolved_with_action",
            review_resolution_context={
                "review_summary": (
                    "The reviewer confirmed downstream action preparation is warranted."
                ),
                "resolution_rationale": (
                    "The required review threshold and packet lineage support action routing."
                ),
            },
            recommendation_class_id="recommend_act_now",
            recommendation_context={
                "recommendation_summary": (
                    "Act now while preserving the recommendation boundary."
                ),
                "action_path_reference": "action-path:price-adjustment-007",
                "scope_reference": "scope:store:001",
                "confidence_summary": "high_confidence",
                "constraint_summary": "inventory_and_margin_checked",
                "uncertainty_summary": "remaining_regime_uncertainty_is_bounded",
                "failure_state_context": "no_active_failure_state_detected",
            },
            policy_output_class_id="policy_shaped_allowance",
            policy_output_context={
                "policy_summary": (
                    "Preserve bounded allowance for downstream action preparation."
                ),
                "policy_output_reference": "policy-output:allowance-007",
                "policy_rationale": (
                    "Recommendation and review lineage justify bounded policy allowance while preserving action-boundary discipline."
                ),
                "action_boundary_summary": (
                    "Policy-shaped allowance only; downstream commitment and instruction remain separate."
                ),
                "allowance_reference": "allowance:store:001:price-adjustment-window-007",
            },
            portfolio_output_class_id="portfolio_bounded_allocation",
            portfolio_output_context={
                "portfolio_summary": (
                    "Preserve bounded allocation posture for downstream portfolio planning."
                ),
                "portfolio_output_reference": "portfolio-output:allocation-007",
                "portfolio_rationale": (
                    "Policy allowance lineage justifies bounded allocation posture for downstream planning."
                ),
                "action_boundary_summary": (
                    "Allocative only; downstream commitment and instruction remain separate."
                ),
                "allocation_reference": "allocation:store:001:price-adjustment-window-007",
                "allocation_weight_reference": "allocation-weight:store:001:0.75",
            },
            action_instruction_class_id="direct_action_instruction",
            action_instruction_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._action_instruction_context()
            ),
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._direct_execution_request_context()
            ),
            execution_dispatch_class_id="direct_dispatch_boundary",
            execution_dispatch_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._direct_execution_dispatch_context()
            ),
            execution_outcome_class_id="favorable_realized_outcome",
            execution_outcome_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers._favorable_outcome_context()
            ),
            post_mortem_judgment_class_id="correct_recommendation_correct_execution",
            post_mortem_judgment_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers._ready_post_mortem_context()
            ),
            policy_learning_evidence_class_id="policy_learning_review_candidate",
            policy_learning_evidence_admission_context=(
                self.helpers.helpers.helpers.helpers.helpers._ready_admission_context()
            ),
            policy_learning_update_threshold_class_id="policy_update_candidate",
            policy_learning_update_threshold_context=(
                self.helpers.helpers.helpers.helpers._accepted_threshold_context()
            ),
            policy_learning_update_approval_class_id=(
                "policy_update_preparation_candidate"
            ),
            policy_learning_update_approval_context=self.helpers.helpers.helpers._approved_context(),
            policy_learning_update_preparation_class_id=(
                "policy_mutation_planning_candidate"
            ),
            policy_learning_update_preparation_context=self.helpers.helpers._prepared_context(),
            policy_learning_update_mutation_planning_class_id=(
                "policy_mutation_plan_candidate"
            ),
            policy_learning_update_mutation_planning_context=self.helpers._prepared_context(),
            policy_learning_update_mutation_execution_class_id=(
                "policy_mutation_execution_candidate"
            ),
            policy_learning_update_mutation_execution_context=self._executed_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(
            payload["policy_learning_update_mutation_execution_status"],
            "mutation_execution_ready",
        )
        self.assertEqual(
            payload["policy_learning_update_mutation_execution_class_id"],
            "policy_mutation_execution_candidate",
        )
        self.assertEqual(
            payload["policy_learning_update_mutation_execution_context"][
                "policy_learning_update_mutation_execution_outcome"
            ],
            "ready_for_policy_mutation_execution",
        )
        self.assertEqual(
            payload["policy_learning_update_mutation_execution_context"][
                "policy_mutation_execution_reference"
            ],
            "policy-mutation-execution:store:001:price-band",
        )

    def _build_policy_learning_update_mutation_execution_service(
        self,
    ) -> PolicyLearningUpdateMutationExecutionService:
        registry = JsonPolicyLearningUpdateMutationExecutionRegistry(
            policy_learning_update_mutation_execution_classes_path=(
                self.registry_root / "policy_learning_update_mutation_execution_classes.json"
            ),
            policy_learning_update_mutation_execution_templates_path=(
                self.registry_root / "policy_learning_update_mutation_execution_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = PolicyLearningUpdateMutationExecutionAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return PolicyLearningUpdateMutationExecutionService(
            policy_learning_update_mutation_execution_registry=registry,
            policy_learning_update_mutation_execution_audit_adapter=audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._policy_learning_update_mutation_planning_service = (
            self.helpers.policy_learning_update_mutation_planning_service
        )
        orchestrator._state_manager._policy_learning_update_mutation_execution_service = (
            self.policy_learning_update_mutation_execution_service
        )
        return orchestrator

    def _build_ready_update_mutation_planning(self):
        return self.helpers.policy_learning_update_mutation_planning_service.generate(
            mutation_planning_test_module.PolicyLearningUpdateMutationPlanningRequest(
                policy_learning_update_preparation=self.helpers._build_ready_update_preparation(),
                policy_learning_update_mutation_planning_class_id=(
                    "policy_mutation_plan_candidate"
                ),
                policy_learning_update_mutation_planning_author_role="case_operator",
                policy_learning_update_mutation_planning_context=self.helpers._prepared_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )

    def _build_restricted_update_mutation_planning(self):
        return self.helpers.policy_learning_update_mutation_planning_service.generate(
            mutation_planning_test_module.PolicyLearningUpdateMutationPlanningRequest(
                policy_learning_update_preparation=self.helpers._build_restricted_update_preparation(),
                policy_learning_update_mutation_planning_class_id=(
                    "restricted_policy_mutation_plan_candidate"
                ),
                policy_learning_update_mutation_planning_author_role="case_operator",
                policy_learning_update_mutation_planning_context=(
                    self.helpers._restricted_preparation_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-mutation-execution-test",
            )
        )

    def _executed_context(self) -> dict[str, object]:
        return {
            "policy_mutation_payload": "mutation-payload:store:001:price-band:v1",
            "policy_mutation_execution_reference": (
                "policy-mutation-execution:store:001:price-band"
            ),
            "mutated_policy_reference": "policy-version:store:001:price-band:v2",
            "mutation_execution_summary": (
                "The governed mutation plan has been executed against the bounded policy asset without widening into deployment or retraining semantics."
            ),
            "mutation_execution_scope_reference": "scope:store:001",
            "mutation_execution_boundary_summary": (
                "Mutation execution remains bounded to the policy asset mutation itself; rollout, deployment, retraining, model update, and monitoring remain separately governed."
            ),
            "mutation_readiness": "strong",
            "safeguard_readiness": "strong",
            "rollback_readiness": "strong",
            "execution_readiness": "strong",
            "verification_readiness": "strong",
            "rollback_execution_readiness": "strong"
        }

    def _restricted_execution_context(self) -> dict[str, object]:
        return {
            **self._executed_context(),
            "mutation_execution_scope_reference": "scope:store:001:promo-window",
            "mutation_readiness": "moderate",
            "safeguard_readiness": "moderate",
            "rollback_readiness": "moderate",
            "execution_readiness": "moderate",
            "verification_readiness": "moderate",
            "rollback_execution_readiness": "moderate",
            "restriction_summary": (
                "Mutation execution remains limited to the narrowed local scope carried forward from mutation planning."
            ),
            "mutation_execution_scope_restriction_reference": (
                "scope:store:001:promo-window"
            )
        }

    def _deferred_execution_context(self) -> dict[str, object]:
        return {
            **self._executed_context(),
            "mutation_readiness": "moderate",
            "safeguard_readiness": "moderate",
            "rollback_readiness": "moderate",
            "execution_readiness": "moderate",
            "verification_readiness": "moderate",
            "rollback_execution_readiness": "moderate",
            "mutation_execution_prerequisite_reference": (
                "mutation-execution-prerequisites:store:001:price-band"
            ),
            "outstanding_mutation_execution_prerequisites": [
                "validation_checkpoint_confirmation",
                "rollback_rehearsal_confirmation"
            ],
            "follow_up_review_reference": "review:mutation-execution-readiness:001"
        }

    def _rejected_execution_context(self) -> dict[str, object]:
        return {
            **self._executed_context(),
            "mutation_readiness": "weak",
            "safeguard_readiness": "weak",
            "rollback_readiness": "weak",
            "execution_readiness": "weak",
            "verification_readiness": "weak",
            "rollback_execution_readiness": "weak"
        }


if __name__ == "__main__":
    unittest.main()
