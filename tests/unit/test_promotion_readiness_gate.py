from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from runtime.release import (  # noqa: E402
    JsonReleaseRegistry,
    PromotionReadinessAuditAdapter,
    PromotionReadinessGate,
    PromotionReadinessGateRequest,
)
from tests.unit import test_policy_learning_update_mutation_execution_layer as mutation_execution_test_module  # noqa: E402


class PromotionReadinessGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = (
            mutation_execution_test_module.PolicyLearningUpdateMutationExecutionLayerTests(
                methodName="runTest"
            )
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.promotion_readiness_gate = self._build_promotion_readiness_gate()

    def test_direct_ready_for_rollout_scope_control(self) -> None:
        mutation_execution = self._build_ready_update_mutation_execution()

        promotion_readiness = self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=mutation_execution,
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )

        self.assertEqual(
            promotion_readiness.promotion_readiness_status,
            "promotion_ready",
        )
        self.assertEqual(
            promotion_readiness.promotion_readiness_outcome,
            "ready_for_rollout_scope_control",
        )
        self.assertEqual(
            promotion_readiness.promotion_candidate_reference,
            "promotion-candidate:store:001:price-band",
        )

    def test_conditionally_ready_for_rollout_scope_control(self) -> None:
        mutation_execution = self._build_restricted_update_mutation_execution()

        promotion_readiness = self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=mutation_execution,
                promotion_readiness_class_id="local_scope_release_candidate",
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self._local_scope_context(),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )

        self.assertEqual(
            promotion_readiness.promotion_readiness_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            promotion_readiness.promotion_readiness_outcome,
            "conditionally_ready_for_rollout_scope_control",
        )
        self.assertEqual(
            promotion_readiness.promotion_scope_restriction_reference,
            "scope:store:001:promo-window",
        )

    def test_deferred_pending_promotion_readiness_evidence(self) -> None:
        mutation_execution = self._build_ready_update_mutation_execution()

        promotion_readiness = self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=mutation_execution,
                promotion_readiness_class_id="deferred_promotion_readiness_candidate",
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )

        self.assertEqual(
            promotion_readiness.promotion_readiness_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            promotion_readiness.promotion_readiness_outcome,
            "deferred_pending_promotion_readiness_evidence",
        )
        self.assertIn(
            "watch-coverage-confirmation",
            promotion_readiness.outstanding_promotion_prerequisites,
        )

    def test_blocked_missing_context(self) -> None:
        mutation_execution = self._build_ready_update_mutation_execution()

        promotion_readiness = self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=mutation_execution,
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context={
                    "promotion_candidate_reference": (
                        "promotion-candidate:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )

        self.assertEqual(
            promotion_readiness.promotion_readiness_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "promotion_readiness_summary",
            promotion_readiness.missing_promotion_readiness_fields,
        )
        self.assertIn(
            "validation_readiness",
            promotion_readiness.missing_promotion_readiness_fields,
        )

    def test_rejected_for_promotion_use(self) -> None:
        mutation_execution = self._build_ready_update_mutation_execution()

        promotion_readiness = self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=mutation_execution,
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self._rejected_context(),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )

        self.assertEqual(
            promotion_readiness.promotion_readiness_status,
            "rejected_for_promotion_use",
        )
        self.assertEqual(
            promotion_readiness.promotion_readiness_outcome,
            "rejected_for_promotion_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        mutation_execution = self._build_ready_update_mutation_execution()

        promotion_readiness = self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=mutation_execution,
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context={
                    **self._ready_context(),
                    "policy_rollout_reference": (
                        "policy-rollout:store:001:price-band"
                    ),
                    "rollback_trigger_reference": (
                        "rollback-trigger:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )

        self.assertEqual(
            promotion_readiness.promotion_readiness_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "policy_rollout_reference",
            promotion_readiness.prohibited_promotion_readiness_fields_present,
        )
        self.assertIn(
            "rollback_trigger_reference",
            promotion_readiness.prohibited_promotion_readiness_fields_present,
        )

    def test_lineage_preservation(self) -> None:
        mutation_execution = self._build_ready_update_mutation_execution()

        promotion_readiness = self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=mutation_execution,
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )

        self.assertEqual(
            promotion_readiness.lineage[
                "policy_learning_update_mutation_execution_id"
            ],
            mutation_execution.policy_learning_update_mutation_execution_id,
        )
        self.assertEqual(
            promotion_readiness.lineage["recommendation_id"],
            mutation_execution.lineage["recommendation_id"],
        )
        self.assertEqual(
            promotion_readiness.execution_outcome_id,
            mutation_execution.execution_outcome_id,
        )

    def test_audit_emission(self) -> None:
        ready_mutation_execution = self._build_ready_update_mutation_execution()
        restricted_mutation_execution = self._build_restricted_update_mutation_execution()

        self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=ready_mutation_execution,
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )
        self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=restricted_mutation_execution,
                promotion_readiness_class_id="local_scope_release_candidate",
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self._local_scope_context(),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )
        self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=ready_mutation_execution,
                promotion_readiness_class_id="deferred_promotion_readiness_candidate",
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )
        self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=ready_mutation_execution,
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context={
                    "promotion_candidate_reference": (
                        "promotion-candidate:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )
        self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=ready_mutation_execution,
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self._rejected_context(),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )
        self.promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=ready_mutation_execution,
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context={
                    **self._ready_context(),
                    "policy_rollout_reference": (
                        "policy-rollout:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn(
            "runtime.release.promotion_readiness_recorded",
            event_types,
        )
        self.assertIn(
            "runtime.release.promotion_readiness_blocked",
            event_types,
        )
        self.assertIn(
            "runtime.release.promotion_readiness_ready_for_rollout_scope_control",
            event_types,
        )
        self.assertIn(
            "runtime.release.promotion_readiness_conditionally_ready_for_rollout_scope_control",
            event_types,
        )
        self.assertIn(
            "runtime.release.promotion_readiness_deferred_pending_promotion_readiness_evidence",
            event_types,
        )
        self.assertIn(
            "runtime.release.promotion_readiness_missing_context",
            event_types,
        )
        self.assertIn(
            "runtime.release.promotion_readiness_rejected_for_promotion_use",
            event_types,
        )
        self.assertIn(
            "runtime.release.promotion_readiness_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "runtime.release.promotion_readiness_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_promotion_readiness(self) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.feature_registry.register_feature(
            mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.FeatureDefinition(
                name="shared.control.revenue_delta.promotion_readiness",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description=(
                    "Expected revenue delta used to seed promotion-readiness lifecycle tests."
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
                created_at=mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.datetime.now(
                    tz=mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.UTC
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="promotion-readiness-test",
        )
        raw_pipeline = (
            self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._build_raw_pipeline()
        )
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-017",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.datetime(
                        2026,
                        4,
                        22,
                        0,
                        0,
                        tzinfo=mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.UTC,
                    ),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-017",
                        "candidate_revenue": 1965.0,
                        "baseline_revenue": 1508.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="promotion-readiness-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-017",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="promotion-readiness-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="promotion-readiness-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should emit governed promotion readiness only after governed mutation execution exists."
            ),
            correlation_id=correlation_id,
            actor_id="promotion-readiness-test",
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
                "action_path_reference": "action-path:price-adjustment-017",
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
                "policy_output_reference": "policy-output:allowance-017",
                "policy_rationale": (
                    "Recommendation and review lineage justify bounded policy allowance while preserving action-boundary discipline."
                ),
                "action_boundary_summary": (
                    "Policy-shaped allowance only; downstream commitment and instruction remain separate."
                ),
                "allowance_reference": "allowance:store:001:price-adjustment-window-017",
            },
            portfolio_output_class_id="portfolio_bounded_allocation",
            portfolio_output_context={
                "portfolio_summary": (
                    "Preserve bounded allocation posture for downstream portfolio planning."
                ),
                "portfolio_output_reference": "portfolio-output:allocation-017",
                "portfolio_rationale": (
                    "Policy allowance lineage justifies bounded allocation posture for downstream planning."
                ),
                "action_boundary_summary": (
                    "Allocative only; downstream commitment and instruction remain separate."
                ),
                "allocation_reference": "allocation:store:001:price-adjustment-window-017",
                "allocation_weight_reference": "allocation-weight:store:001:0.75",
            },
            action_instruction_class_id="direct_action_instruction",
            action_instruction_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._action_instruction_context()
            ),
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._direct_execution_request_context()
            ),
            execution_dispatch_class_id="direct_dispatch_boundary",
            execution_dispatch_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._direct_execution_dispatch_context()
            ),
            execution_outcome_class_id="favorable_realized_outcome",
            execution_outcome_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._favorable_outcome_context()
            ),
            post_mortem_judgment_class_id="correct_recommendation_correct_execution",
            post_mortem_judgment_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers._ready_post_mortem_context()
            ),
            policy_learning_evidence_class_id="policy_learning_review_candidate",
            policy_learning_evidence_admission_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers._ready_admission_context()
            ),
            policy_learning_update_threshold_class_id="policy_update_candidate",
            policy_learning_update_threshold_context=(
                self.helpers.helpers.helpers.helpers.helpers._accepted_threshold_context()
            ),
            policy_learning_update_approval_class_id=(
                "policy_update_preparation_candidate"
            ),
            policy_learning_update_approval_context=self.helpers.helpers.helpers.helpers._approved_context(),
            policy_learning_update_preparation_class_id=(
                "policy_mutation_planning_candidate"
            ),
            policy_learning_update_preparation_context=self.helpers.helpers.helpers._prepared_context(),
            policy_learning_update_mutation_planning_class_id=(
                "policy_mutation_plan_candidate"
            ),
            policy_learning_update_mutation_planning_context=self.helpers.helpers._prepared_context(),
            policy_learning_update_mutation_execution_class_id=(
                "policy_mutation_execution_candidate"
            ),
            policy_learning_update_mutation_execution_context=(
                self.helpers._executed_context()
            ),
            promotion_readiness_class_id=(
                "full_scope_production_promotion_candidate"
            ),
            promotion_readiness_context=self._ready_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(
            payload["promotion_readiness_status"],
            "promotion_ready",
        )
        self.assertEqual(
            payload["promotion_readiness_class_id"],
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            payload["promotion_readiness_context"]["promotion_readiness_outcome"],
            "ready_for_rollout_scope_control",
        )
        self.assertEqual(
            payload["promotion_readiness_context"]["promotion_candidate_reference"],
            "promotion-candidate:store:001:price-band",
        )

    def _build_promotion_readiness_gate(self) -> PromotionReadinessGate:
        registry = JsonReleaseRegistry(
            promotion_readiness_classes_path=(
                self.registry_root / "promotion_readiness_classes.json"
            ),
            promotion_readiness_templates_path=(
                self.registry_root / "promotion_readiness_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = PromotionReadinessAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return PromotionReadinessGate(
            release_registry=registry,
            promotion_readiness_audit_adapter=audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._promotion_readiness_gate = (
            self.promotion_readiness_gate
        )
        return orchestrator

    def _build_ready_update_mutation_execution(self):
        return self.helpers.policy_learning_update_mutation_execution_service.generate(
            mutation_execution_test_module.PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=(
                    self.helpers._build_ready_update_mutation_planning()
                ),
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self.helpers._executed_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )

    def _build_restricted_update_mutation_execution(self):
        return self.helpers.policy_learning_update_mutation_execution_service.generate(
            mutation_execution_test_module.PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=(
                    self.helpers._build_restricted_update_mutation_planning()
                ),
                policy_learning_update_mutation_execution_class_id=(
                    "restricted_policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    self.helpers._restricted_execution_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="promotion-readiness-test",
            )
        )

    def _ready_context(self) -> dict[str, object]:
        return {
            "promotion_candidate_reference": "promotion-candidate:store:001:price-band",
            "promotion_readiness_summary": (
                "The mutated policy candidate has explicit readiness evidence, bounded entitlement, and reversible promotion posture without widening into rollout-scope or rollback-trigger control."
            ),
            "readiness_evidence_reference": (
                "promotion-evidence:store:001:price-band"
            ),
            "promotion_threshold_reference": (
                "promotion-threshold:shared_control_plane:price-band"
            ),
            "production_entitlement_boundary": (
                "entitlement-boundary:shared_control_plane:store-price-band"
            ),
            "rollback_posture_reference": (
                "rollback-posture:store:001:price-band"
            ),
            "release_watch_window": "watch-window:24h",
            "release_confirmation_threshold_reference": (
                "release-confirmation-threshold:shared_control_plane:price-band"
            ),
            "promotion_scope_reference": "scope:store:001",
            "promotion_boundary_summary": (
                "Promotion readiness remains bounded to readiness evidence, entitlement boundary, and downstream rollout-scope eligibility; rollout execution, rollback-trigger control, and live watch execution remain separately governed."
            ),
            "validation_readiness": "strong",
            "scope_transfer_readiness": "strong",
            "exposure_control_readiness": "strong",
            "security_posture_readiness": "strong",
            "performance_posture_readiness": "strong",
            "rollback_posture_readiness": "strong",
            "operational_reversibility_readiness": "strong",
            "confirmation_readiness": "strong"
        }

    def _local_scope_context(self) -> dict[str, object]:
        return {
            **self._ready_context(),
            "production_entitlement_boundary": (
                "entitlement-boundary:shared_control_plane:store-price-band:local-only"
            ),
            "promotion_scope_reference": "scope:store:001:promo-window",
            "validation_readiness": "moderate",
            "scope_transfer_readiness": "moderate",
            "exposure_control_readiness": "moderate",
            "security_posture_readiness": "moderate",
            "performance_posture_readiness": "moderate",
            "rollback_posture_readiness": "moderate",
            "operational_reversibility_readiness": "moderate",
            "confirmation_readiness": "moderate",
            "restriction_summary": (
                "Promotion readiness remains limited to the narrowed local scope carried forward from bounded mutation execution."
            ),
            "promotion_scope_restriction_reference": (
                "scope:store:001:promo-window"
            )
        }

    def _deferred_context(self) -> dict[str, object]:
        return {
            **self._ready_context(),
            "validation_readiness": "moderate",
            "scope_transfer_readiness": "moderate",
            "exposure_control_readiness": "moderate",
            "security_posture_readiness": "moderate",
            "performance_posture_readiness": "moderate",
            "rollback_posture_readiness": "moderate",
            "operational_reversibility_readiness": "moderate",
            "confirmation_readiness": "moderate",
            "promotion_prerequisite_reference": (
                "promotion-prerequisites:store:001:price-band"
            ),
            "outstanding_promotion_prerequisites": [
                "release-approval-review",
                "watch-coverage-confirmation"
            ],
            "follow_up_review_reference": "review:promotion-readiness:001"
        }

    def _rejected_context(self) -> dict[str, object]:
        return {
            **self._ready_context(),
            "validation_readiness": "weak",
            "scope_transfer_readiness": "weak",
            "exposure_control_readiness": "weak",
            "security_posture_readiness": "weak",
            "performance_posture_readiness": "weak",
            "rollback_posture_readiness": "weak",
            "operational_reversibility_readiness": "weak",
            "confirmation_readiness": "weak"
        }


if __name__ == "__main__":
    unittest.main()
