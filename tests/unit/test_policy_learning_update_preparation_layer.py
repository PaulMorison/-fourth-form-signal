from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from decision.policy_learning import (  # noqa: E402
    JsonPolicyLearningUpdatePreparationRegistry,
    PolicyLearningUpdatePreparationAuditAdapter,
    PolicyLearningUpdatePreparationRequest,
    PolicyLearningUpdatePreparationService,
)
from tests.unit import test_policy_learning_update_approval_layer as approval_test_module  # noqa: E402


class PolicyLearningUpdatePreparationLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = approval_test_module.PolicyLearningUpdateApprovalLayerTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.policy_learning_update_preparation_service = (
            self._build_policy_learning_update_preparation_service()
        )

    def test_direct_prepared_for_policy_mutation_planning(self) -> None:
        approval = self._build_ready_update_approval()

        preparation = self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    self._prepared_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )

        self.assertEqual(
            preparation.policy_learning_update_preparation_status,
            "preparation_ready",
        )
        self.assertEqual(
            preparation.policy_learning_update_preparation_outcome,
            "prepared_for_policy_mutation_planning",
        )

    def test_prepared_with_restrictions(self) -> None:
        approval = self._build_restricted_update_approval()

        preparation = self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approval,
                policy_learning_update_preparation_class_id=(
                    "restricted_policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    self._restricted_preparation_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )

        self.assertEqual(
            preparation.policy_learning_update_preparation_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            preparation.policy_learning_update_preparation_outcome,
            "prepared_with_restrictions",
        )
        self.assertEqual(
            preparation.preparation_scope_restriction_reference,
            "scope:store:001:promo-window",
        )

    def test_deferred_pending_preparation_prerequisites(self) -> None:
        approval = self._build_ready_update_approval()

        preparation = self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approval,
                policy_learning_update_preparation_class_id=(
                    "deferred_policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    self._deferred_preparation_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )

        self.assertEqual(
            preparation.policy_learning_update_preparation_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            preparation.policy_learning_update_preparation_outcome,
            "deferred_pending_preparation_prerequisites",
        )
        self.assertIn(
            "change_window_confirmation",
            preparation.outstanding_preparation_prerequisites,
        )

    def test_blocked_missing_context(self) -> None:
        approval = self._build_ready_update_approval()

        preparation = self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context={
                    "preparation_package_reference": (
                        "preparation-package:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )

        self.assertEqual(
            preparation.policy_learning_update_preparation_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "preparation_summary",
            preparation.missing_update_preparation_fields,
        )
        self.assertIn(
            "planning_readiness",
            preparation.missing_update_preparation_fields,
        )

    def test_rejected_for_preparation_use(self) -> None:
        approval = self._build_ready_update_approval()

        preparation = self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    self._rejected_preparation_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )

        self.assertEqual(
            preparation.policy_learning_update_preparation_status,
            "rejected_for_preparation_use",
        )
        self.assertEqual(
            preparation.policy_learning_update_preparation_outcome,
            "rejected_for_preparation_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        approval = self._build_ready_update_approval()

        preparation = self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context={
                    **self._prepared_context(),
                    "policy_mutation_payload": "mutate-policy:price-floor",
                    "model_deployment_reference": "deploy:model:2026-04-23",
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )

        self.assertEqual(
            preparation.policy_learning_update_preparation_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "policy_mutation_payload",
            preparation.prohibited_update_preparation_fields_present,
        )
        self.assertIn(
            "model_deployment_reference",
            preparation.prohibited_update_preparation_fields_present,
        )

    def test_lineage_preservation(self) -> None:
        approval = self._build_ready_update_approval()

        preparation = self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    self._prepared_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )

        self.assertEqual(
            preparation.lineage["policy_learning_update_approval_id"],
            approval.policy_learning_update_approval_id,
        )
        self.assertEqual(
            preparation.lineage["recommendation_id"],
            approval.lineage["recommendation_id"],
        )
        self.assertEqual(
            preparation.execution_outcome_id,
            approval.execution_outcome_id,
        )

    def test_audit_emission(self) -> None:
        ready_approval = self._build_ready_update_approval()
        restricted_approval = self._build_restricted_update_approval()

        self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=ready_approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    self._prepared_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )
        self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=restricted_approval,
                policy_learning_update_preparation_class_id=(
                    "restricted_policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    self._restricted_preparation_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )
        self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=ready_approval,
                policy_learning_update_preparation_class_id=(
                    "deferred_policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    self._deferred_preparation_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )
        self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=ready_approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context={
                    "preparation_package_reference": (
                        "preparation-package:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )
        self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=ready_approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    self._rejected_preparation_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )
        self.policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=ready_approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context={
                    **self._prepared_context(),
                    "policy_mutation_payload": "mutate-policy:price-floor",
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn(
            "decision.policy_learning.policy_learning_update_preparation_recorded",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_preparation_blocked",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_preparation_prepared_for_policy_mutation_planning",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_preparation_prepared_with_restrictions",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_preparation_deferred_pending_preparation_prerequisites",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_preparation_missing_context",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_preparation_rejected_for_preparation_use",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_preparation_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_preparation_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_policy_learning_update_preparation(
        self,
    ) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.helpers.helpers.helpers.helpers.helpers.helpers.feature_registry.register_feature(
            approval_test_module.threshold_test_module.FeatureDefinition(
                name="shared.control.revenue_delta.policy_learning_update_preparation",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description=(
                    "Expected revenue delta used to seed policy-learning update-preparation tests."
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
                created_at=approval_test_module.threshold_test_module.datetime.now(
                    tz=approval_test_module.threshold_test_module.UTC
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="policy-learning-update-preparation-test",
        )
        raw_pipeline = (
            self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._build_raw_pipeline()
        )
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                approval_test_module.threshold_test_module.RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-006",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=approval_test_module.threshold_test_module.datetime(
                        2026,
                        4,
                        22,
                        0,
                        0,
                        tzinfo=approval_test_module.threshold_test_module.UTC,
                    ),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-006",
                        "candidate_revenue": 1765.0,
                        "baseline_revenue": 1508.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="policy-learning-update-preparation-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-006",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="policy-learning-update-preparation-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="policy-learning-update-preparation-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should emit governed policy-learning update preparation only after governed update approval exists."
            ),
            correlation_id=correlation_id,
            actor_id="policy-learning-update-preparation-test",
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
                "action_path_reference": "action-path:price-adjustment-006",
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
                "policy_output_reference": "policy-output:allowance-006",
                "policy_rationale": (
                    "Recommendation and review lineage justify bounded policy allowance while preserving action-boundary discipline."
                ),
                "action_boundary_summary": (
                    "Policy-shaped allowance only; downstream commitment and instruction remain separate."
                ),
                "allowance_reference": "allowance:store:001:price-adjustment-window-006",
            },
            portfolio_output_class_id="portfolio_bounded_allocation",
            portfolio_output_context={
                "portfolio_summary": (
                    "Preserve bounded allocation posture for downstream portfolio planning."
                ),
                "portfolio_output_reference": "portfolio-output:allocation-006",
                "portfolio_rationale": (
                    "Policy allowance lineage justifies bounded allocation posture for downstream planning."
                ),
                "action_boundary_summary": (
                    "Allocative only; downstream commitment and instruction remain separate."
                ),
                "allocation_reference": "allocation:store:001:price-adjustment-window-006",
                "allocation_weight_reference": "allocation-weight:store:001:0.75",
            },
            action_instruction_class_id="direct_action_instruction",
            action_instruction_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._action_instruction_context()
            ),
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers._direct_execution_request_context()
            ),
            execution_dispatch_class_id="direct_dispatch_boundary",
            execution_dispatch_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers._direct_execution_dispatch_context()
            ),
            execution_outcome_class_id="favorable_realized_outcome",
            execution_outcome_context=(
                self.helpers.helpers.helpers.helpers.helpers._favorable_outcome_context()
            ),
            post_mortem_judgment_class_id="correct_recommendation_correct_execution",
            post_mortem_judgment_context=(
                self.helpers.helpers.helpers.helpers._ready_post_mortem_context()
            ),
            policy_learning_evidence_class_id="policy_learning_review_candidate",
            policy_learning_evidence_admission_context=(
                self.helpers.helpers.helpers._ready_admission_context()
            ),
            policy_learning_update_threshold_class_id="policy_update_candidate",
            policy_learning_update_threshold_context=(
                self.helpers.helpers._accepted_threshold_context()
            ),
            policy_learning_update_approval_class_id=(
                "policy_update_preparation_candidate"
            ),
            policy_learning_update_approval_context=self.helpers._approved_context(),
            policy_learning_update_preparation_class_id=(
                "policy_mutation_planning_candidate"
            ),
            policy_learning_update_preparation_context=self._prepared_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(
            payload["policy_learning_update_preparation_status"],
            "preparation_ready",
        )
        self.assertEqual(
            payload["policy_learning_update_preparation_class_id"],
            "policy_mutation_planning_candidate",
        )
        self.assertEqual(
            payload["policy_learning_update_preparation_context"][
                "policy_learning_update_preparation_outcome"
            ],
            "prepared_for_policy_mutation_planning",
        )
        self.assertEqual(
            payload["policy_learning_update_preparation_context"][
                "preparation_package_reference"
            ],
            "preparation-package:store:001:price-band",
        )

    def _build_policy_learning_update_preparation_service(
        self,
    ) -> PolicyLearningUpdatePreparationService:
        registry = JsonPolicyLearningUpdatePreparationRegistry(
            policy_learning_update_preparation_classes_path=(
                self.registry_root / "policy_learning_update_preparation_classes.json"
            ),
            policy_learning_update_preparation_templates_path=(
                self.registry_root / "policy_learning_update_preparation_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = PolicyLearningUpdatePreparationAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return PolicyLearningUpdatePreparationService(
            policy_learning_update_preparation_registry=registry,
            policy_learning_update_preparation_audit_adapter=audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._policy_learning_update_preparation_service = (
            self.policy_learning_update_preparation_service
        )
        return orchestrator

    def _build_ready_update_approval(self):
        return self.helpers.policy_learning_update_approval_service.generate(
            approval_test_module.PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=self.helpers._build_ready_update_threshold(),
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=(
                    self.helpers._approved_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )

    def _build_restricted_update_approval(self):
        return self.helpers.policy_learning_update_approval_service.generate(
            approval_test_module.PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=(
                    self.helpers._build_restricted_update_threshold()
                ),
                policy_learning_update_approval_class_id=(
                    "restricted_policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=(
                    self.helpers._restricted_approval_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-update-preparation-test",
            )
        )

    def _prepared_context(self) -> dict[str, object]:
        return {
            "preparation_package_reference": (
                "preparation-package:store:001:price-band"
            ),
            "preparation_summary": (
                "Approved update evidence has been packaged for bounded policy-mutation planning."
            ),
            "mutation_planning_scope_reference": "scope:store:001",
            "preparation_artifact_boundary_summary": (
                "Preparation package supports mutation planning only; actual mutation, deployment, and monitoring remain separately governed."
            ),
            "artifact_readiness": "strong",
            "planning_readiness": "strong",
            "prerequisite_readiness": "strong",
        }

    def _restricted_preparation_context(self) -> dict[str, object]:
        return {
            **self._prepared_context(),
            "mutation_planning_scope_reference": "scope:store:001:promo-window",
            "artifact_readiness": "moderate",
            "planning_readiness": "moderate",
            "prerequisite_readiness": "moderate",
            "restriction_summary": (
                "Prepared package remains limited to the narrowed local scope approved upstream."
            ),
            "preparation_scope_restriction_reference": (
                "scope:store:001:promo-window"
            ),
        }

    def _deferred_preparation_context(self) -> dict[str, object]:
        return {
            **self._prepared_context(),
            "artifact_readiness": "moderate",
            "planning_readiness": "moderate",
            "prerequisite_readiness": "weak",
            "preparation_prerequisite_reference": (
                "preparation-prerequisites:store:001:price-band"
            ),
            "outstanding_preparation_prerequisites": [
                "change_window_confirmation",
                "rollback_validation",
            ],
            "follow_up_review_reference": "review:preparation-readiness:001",
        }

    def _rejected_preparation_context(self) -> dict[str, object]:
        return {
            **self._prepared_context(),
            "artifact_readiness": "weak",
            "planning_readiness": "weak",
            "prerequisite_readiness": "weak",
        }


if __name__ == "__main__":
    unittest.main()