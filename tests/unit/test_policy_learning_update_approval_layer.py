from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from decision.policy_learning import (  # noqa: E402
    JsonPolicyLearningUpdateApprovalRegistry,
    PolicyLearningUpdateApprovalAuditAdapter,
    PolicyLearningUpdateApprovalRequest,
    PolicyLearningUpdateApprovalService,
)
from tests.unit import test_policy_learning_update_threshold_layer as threshold_test_module  # noqa: E402


class PolicyLearningUpdateApprovalLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = threshold_test_module.PolicyLearningUpdateThresholdLayerTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.policy_learning_update_approval_service = (
            self._build_policy_learning_update_approval_service()
        )

    def test_direct_approved_update_preparation(self) -> None:
        threshold = self._build_ready_update_threshold()

        approval = self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=self._approved_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

        self.assertEqual(
            approval.policy_learning_update_approval_status,
            "approval_ready",
        )
        self.assertEqual(
            approval.policy_learning_update_approval_outcome,
            "approved_for_policy_update_preparation",
        )

    def test_approved_with_restrictions(self) -> None:
        threshold = self._build_restricted_update_threshold()

        approval = self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=threshold,
                policy_learning_update_approval_class_id=(
                    "restricted_policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=(
                    self._restricted_approval_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

        self.assertEqual(
            approval.policy_learning_update_approval_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            approval.policy_learning_update_approval_outcome,
            "approved_with_restrictions",
        )
        self.assertEqual(
            approval.preparation_scope_restriction_reference,
            "scope:store:001:promo-window",
        )

    def test_deferred_pending_additional_governance(self) -> None:
        threshold = self._build_deferred_update_threshold()

        approval = self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=threshold,
                policy_learning_update_approval_class_id=(
                    "deferred_policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=self._deferred_approval_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

        self.assertEqual(
            approval.policy_learning_update_approval_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            approval.policy_learning_update_approval_outcome,
            "deferred_pending_additional_governance",
        )
        self.assertIn(
            "governance_board_recheck",
            approval.additional_governance_requirements,
        )

    def test_blocked_missing_context(self) -> None:
        threshold = self._build_ready_update_threshold()

        approval = self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context={
                    "candidate_update_reference": "candidate-update:store:001"
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

        self.assertEqual(
            approval.policy_learning_update_approval_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "approval_summary",
            approval.missing_update_approval_fields,
        )
        self.assertIn(
            "change_control_readiness",
            approval.missing_update_approval_fields,
        )

    def test_rejected_for_policy_update_use(self) -> None:
        threshold = self._build_ready_update_threshold()

        approval = self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=self._rejected_approval_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

        self.assertEqual(
            approval.policy_learning_update_approval_status,
            "rejected_for_policy_update_use",
        )
        self.assertEqual(
            approval.policy_learning_update_approval_outcome,
            "rejected_for_policy_update_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        threshold = self._build_ready_update_threshold()

        approval = self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context={
                    **self._approved_context(),
                    "policy_mutation_payload": "mutate-policy:price-floor",
                    "model_deployment_reference": "deploy:model:2026-04-23"
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

        self.assertEqual(
            approval.policy_learning_update_approval_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "policy_mutation_payload",
            approval.prohibited_update_approval_fields_present,
        )
        self.assertIn(
            "model_deployment_reference",
            approval.prohibited_update_approval_fields_present,
        )

    def test_lineage_preservation(self) -> None:
        threshold = self._build_ready_update_threshold()

        approval = self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=self._approved_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

        self.assertEqual(
            approval.lineage["policy_learning_update_threshold_id"],
            threshold.policy_learning_update_threshold_id,
        )
        self.assertEqual(
            approval.lineage["recommendation_id"],
            threshold.lineage["recommendation_id"],
        )
        self.assertEqual(
            approval.execution_outcome_id,
            threshold.execution_outcome_id,
        )

    def test_audit_emission(self) -> None:
        ready_threshold = self._build_ready_update_threshold()
        restricted_threshold = self._build_restricted_update_threshold()
        deferred_threshold = self._build_deferred_update_threshold()

        self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=ready_threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=self._approved_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )
        self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=restricted_threshold,
                policy_learning_update_approval_class_id=(
                    "restricted_policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=(
                    self._restricted_approval_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )
        self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=deferred_threshold,
                policy_learning_update_approval_class_id=(
                    "deferred_policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=self._deferred_approval_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )
        self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=ready_threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context={
                    "candidate_update_reference": "candidate-update:store:001"
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )
        self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=ready_threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=self._rejected_approval_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )
        self.policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=ready_threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context={
                    **self._approved_context(),
                    "policy_mutation_payload": "mutate-policy:price-floor"
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn(
            "decision.policy_learning.policy_learning_update_approval_recorded",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_approval_blocked",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_approval_approved_for_policy_update_preparation",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_approval_approved_with_restrictions",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_approval_deferred_pending_additional_governance",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_approval_missing_context",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_approval_rejected_for_policy_update_use",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_approval_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_approval_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_policy_learning_update_approval(
        self,
    ) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.helpers.helpers.helpers.helpers.helpers.feature_registry.register_feature(
            threshold_test_module.FeatureDefinition(
                name="shared.control.revenue_delta.policy_learning_update_approval",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description=(
                    "Expected revenue delta used to seed policy-learning update-approval tests."
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
                created_at=threshold_test_module.datetime.now(
                    tz=threshold_test_module.UTC
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="policy-learning-update-approval-test",
        )
        raw_pipeline = (
            self.helpers.helpers.helpers.helpers.helpers.helpers.helpers._build_raw_pipeline()
        )
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                threshold_test_module.RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-005",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=threshold_test_module.datetime(
                        2026,
                        4,
                        22,
                        0,
                        0,
                        tzinfo=threshold_test_module.UTC,
                    ),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-005",
                        "candidate_revenue": 1740.0,
                        "baseline_revenue": 1510.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="policy-learning-update-approval-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-005",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="policy-learning-update-approval-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="policy-learning-update-approval-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should emit governed policy-learning update approval only after governed threshold approval exists."
            ),
            correlation_id=correlation_id,
            actor_id="policy-learning-update-approval-test",
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
                "action_path_reference": "action-path:price-adjustment-005",
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
                "policy_output_reference": "policy-output:allowance-005",
                "policy_rationale": (
                    "Recommendation and review lineage justify bounded policy allowance while preserving action-boundary discipline."
                ),
                "action_boundary_summary": (
                    "Policy-shaped allowance only; downstream commitment and instruction remain separate."
                ),
                "allowance_reference": "allowance:store:001:price-adjustment-window-005",
            },
            portfolio_output_class_id="portfolio_bounded_allocation",
            portfolio_output_context={
                "portfolio_summary": (
                    "Preserve bounded allocation posture for downstream portfolio planning."
                ),
                "portfolio_output_reference": "portfolio-output:allocation-005",
                "portfolio_rationale": (
                    "Policy allowance lineage justifies bounded allocation posture for downstream planning."
                ),
                "action_boundary_summary": (
                    "Allocative only; downstream commitment and instruction remain separate."
                ),
                "allocation_reference": "allocation:store:001:price-adjustment-window-005",
                "allocation_weight_reference": "allocation-weight:store:001:0.75",
            },
            action_instruction_class_id="direct_action_instruction",
            action_instruction_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers._action_instruction_context()
            ),
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers._direct_execution_request_context()
            ),
            execution_dispatch_class_id="direct_dispatch_boundary",
            execution_dispatch_context=(
                self.helpers.helpers.helpers.helpers.helpers._direct_execution_dispatch_context()
            ),
            execution_outcome_class_id="favorable_realized_outcome",
            execution_outcome_context=(
                self.helpers.helpers.helpers.helpers._favorable_outcome_context()
            ),
            post_mortem_judgment_class_id="correct_recommendation_correct_execution",
            post_mortem_judgment_context=(
                self.helpers.helpers.helpers._ready_post_mortem_context()
            ),
            policy_learning_evidence_class_id="policy_learning_review_candidate",
            policy_learning_evidence_admission_context=(
                self.helpers.helpers._ready_admission_context()
            ),
            policy_learning_update_threshold_class_id="policy_update_candidate",
            policy_learning_update_threshold_context=(
                self.helpers._accepted_threshold_context()
            ),
            policy_learning_update_approval_class_id=(
                "policy_update_preparation_candidate"
            ),
            policy_learning_update_approval_context=self._approved_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(
            payload["policy_learning_update_approval_status"],
            "approval_ready",
        )
        self.assertEqual(
            payload["policy_learning_update_approval_class_id"],
            "policy_update_preparation_candidate",
        )
        self.assertEqual(
            payload["policy_learning_update_approval_context"][
                "policy_learning_update_approval_outcome"
            ],
            "approved_for_policy_update_preparation",
        )
        self.assertEqual(
            payload["policy_learning_update_approval_context"][
                "candidate_update_reference"
            ],
            "candidate-update:store:001:price-band",
        )

    def _build_policy_learning_update_approval_service(
        self,
    ) -> PolicyLearningUpdateApprovalService:
        registry = JsonPolicyLearningUpdateApprovalRegistry(
            policy_learning_update_approval_classes_path=(
                self.registry_root / "policy_learning_update_approval_classes.json"
            ),
            policy_learning_update_approval_templates_path=(
                self.registry_root / "policy_learning_update_approval_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = PolicyLearningUpdateApprovalAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return PolicyLearningUpdateApprovalService(
            policy_learning_update_approval_registry=registry,
            policy_learning_update_approval_audit_adapter=audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._policy_learning_update_approval_service = (
            self.policy_learning_update_approval_service
        )
        return orchestrator

    def _build_ready_update_threshold(self):
        return self.helpers.policy_learning_update_threshold_service.generate(
            threshold_test_module.PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=self.helpers._build_ready_evidence_admission(),
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=(
                    self.helpers._accepted_threshold_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

    def _build_restricted_update_threshold(self):
        return self.helpers.policy_learning_update_threshold_service.generate(
            threshold_test_module.PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=(
                    self.helpers._build_restricted_evidence_admission()
                ),
                policy_learning_update_threshold_class_id=(
                    "narrowed_policy_update_candidate"
                ),
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=(
                    self.helpers._narrowed_threshold_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

    def _build_deferred_update_threshold(self):
        return self.helpers.policy_learning_update_threshold_service.generate(
            threshold_test_module.PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=(
                    self.helpers._build_deferred_evidence_admission()
                ),
                policy_learning_update_threshold_class_id=(
                    "deferred_policy_update_candidate"
                ),
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=(
                    self.helpers._deferred_threshold_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-approval-test",
            )
        )

    def _approved_context(self) -> dict[str, object]:
        return {
            "candidate_update_reference": "candidate-update:store:001:price-band",
            "approval_summary": (
                "Threshold evidence and governance controls support preparation of a bounded policy update package."
            ),
            "change_control_reference": "change-control:store:001:price-band",
            "preparation_scope_reference": "scope:store:001",
            "preparation_boundary_summary": (
                "Approval covers preparation only; actual mutation, deployment, and monitoring remain separately governed."
            ),
            "governance_readiness": "strong",
            "change_control_readiness": "strong",
            "boundary_control_strength": "strong",
            "preparation_readiness": "strong"
        }

    def _restricted_approval_context(self) -> dict[str, object]:
        return {
            **self._approved_context(),
            "preparation_scope_reference": "scope:store:001:promo-window",
            "governance_readiness": "moderate",
            "change_control_readiness": "moderate",
            "boundary_control_strength": "moderate",
            "preparation_readiness": "moderate",
            "restriction_summary": (
                "Preparation is limited to the narrowed local scope supported by the governed threshold evidence."
            ),
            "preparation_scope_restriction_reference": "scope:store:001:promo-window"
        }

    def _deferred_approval_context(self) -> dict[str, object]:
        return {
            **self._approved_context(),
            "governance_readiness": "moderate",
            "change_control_readiness": "weak",
            "boundary_control_strength": "moderate",
            "preparation_readiness": "weak",
            "additional_governance_requirements": [
                "governance_board_recheck",
                "policy_risk_review"
            ],
            "unresolved_governance_gaps": [
                "cross_region_change_control_pending"
            ],
            "follow_up_review_reference": "review:policy-governance:001"
        }

    def _rejected_approval_context(self) -> dict[str, object]:
        return {
            **self._approved_context(),
            "governance_readiness": "weak",
            "change_control_readiness": "weak",
            "boundary_control_strength": "moderate",
            "preparation_readiness": "weak"
        }


if __name__ == "__main__":
    unittest.main()