from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from runtime.release import (  # noqa: E402
    JsonReleaseRegistry,
    RolloutScopeAuditAdapter,
    RolloutScopeController,
    RolloutScopeControllerRequest,
)
from tests.unit import test_promotion_readiness_gate as promotion_readiness_test_module  # noqa: E402


class RolloutScopeControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = promotion_readiness_test_module.PromotionReadinessGateTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.rollout_scope_controller = self._build_rollout_scope_controller()

    def test_direct_ready_for_rollback_trigger_guard(self) -> None:
        promotion_readiness = self._build_ready_promotion_readiness()

        rollout_scope = self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="release_authority",
                rollout_scope_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )

        self.assertEqual(rollout_scope.rollout_scope_status, "rollout_scope_defined")
        self.assertEqual(
            rollout_scope.rollout_scope_outcome,
            "ready_for_rollback_trigger_guard",
        )
        self.assertEqual(
            rollout_scope.rollout_scope_boundary_reference,
            "rollout-scope:store:001:full",
        )

    def test_conditionally_ready_for_rollback_trigger_guard(self) -> None:
        promotion_readiness = self._build_conditional_promotion_readiness()

        rollout_scope = self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=promotion_readiness,
                rollout_scope_class_id="conditional_production_release",
                rollout_scope_author_role="release_authority",
                rollout_scope_context=self._conditional_context(),
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )

        self.assertEqual(
            rollout_scope.rollout_scope_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            rollout_scope.rollout_scope_outcome,
            "conditionally_ready_for_rollback_trigger_guard",
        )
        self.assertEqual(
            rollout_scope.exposure_boundary_reference,
            "exposure-boundary:store:001:promo-window",
        )

    def test_deferred_pending_rollout_scope_evidence(self) -> None:
        promotion_readiness = self._build_ready_promotion_readiness()

        rollout_scope = self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=promotion_readiness,
                rollout_scope_class_id="deferred_release_state",
                rollout_scope_author_role="release_authority",
                rollout_scope_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )

        self.assertEqual(
            rollout_scope.rollout_scope_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            rollout_scope.rollout_scope_outcome,
            "deferred_pending_rollout_scope_evidence",
        )
        self.assertIn(
            "release-watch-observer-confirmation",
            rollout_scope.outstanding_rollout_scope_prerequisites,
        )

    def test_blocked_missing_context(self) -> None:
        promotion_readiness = self._build_ready_promotion_readiness()

        rollout_scope = self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="release_authority",
                rollout_scope_context={
                    "rollout_scope_boundary_reference": "rollout-scope:store:001:full"
                },
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )

        self.assertEqual(
            rollout_scope.rollout_scope_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "exposure_boundary_reference",
            rollout_scope.missing_rollout_scope_fields,
        )

    def test_rejected_for_rollout_scope_use(self) -> None:
        promotion_readiness = self._build_ready_promotion_readiness()

        rollout_scope = self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="release_authority",
                rollout_scope_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Exposure remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )

        self.assertEqual(
            rollout_scope.rollout_scope_status,
            "rejected_for_rollout_scope_use",
        )
        self.assertEqual(
            rollout_scope.rollout_scope_outcome,
            "rejected_for_rollout_scope_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        promotion_readiness = self._build_ready_promotion_readiness()

        rollout_scope = self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="release_authority",
                rollout_scope_context={
                    **self._ready_context(),
                    "rollback_trigger_reference": (
                        "rollback-trigger:store:001:price-band"
                    ),
                    "release_observation_reference": (
                        "release-observation:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )

        self.assertEqual(
            rollout_scope.rollout_scope_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "rollback_trigger_reference",
            rollout_scope.prohibited_rollout_scope_fields_present,
        )
        self.assertIn(
            "release_observation_reference",
            rollout_scope.prohibited_rollout_scope_fields_present,
        )

    def test_audit_emission(self) -> None:
        ready_promotion_readiness = self._build_ready_promotion_readiness()
        conditional_promotion_readiness = self._build_conditional_promotion_readiness()

        self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=ready_promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="release_authority",
                rollout_scope_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )
        self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=conditional_promotion_readiness,
                rollout_scope_class_id="conditional_production_release",
                rollout_scope_author_role="release_authority",
                rollout_scope_context=self._conditional_context(),
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )
        self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=ready_promotion_readiness,
                rollout_scope_class_id="deferred_release_state",
                rollout_scope_author_role="release_authority",
                rollout_scope_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )
        self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=ready_promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="release_authority",
                rollout_scope_context={
                    "rollout_scope_boundary_reference": "rollout-scope:store:001:full"
                },
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )
        self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=ready_promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="release_authority",
                rollout_scope_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Exposure remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )
        self.rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=ready_promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="release_authority",
                rollout_scope_context={
                    **self._ready_context(),
                    "rollback_trigger_reference": (
                        "rollback-trigger:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn("runtime.release.rollout_scope_recorded", event_types)
        self.assertIn("runtime.release.rollout_scope_blocked", event_types)
        self.assertIn(
            "runtime.release.rollout_scope_ready_for_rollback_trigger_guard",
            event_types,
        )
        self.assertIn(
            "runtime.release.rollout_scope_conditionally_ready_for_rollback_trigger_guard",
            event_types,
        )
        self.assertIn(
            "runtime.release.rollout_scope_deferred_pending_rollout_scope_evidence",
            event_types,
        )
        self.assertIn("runtime.release.rollout_scope_missing_context", event_types)
        self.assertIn(
            "runtime.release.rollout_scope_rejected_for_rollout_scope_use",
            event_types,
        )
        self.assertIn(
            "runtime.release.rollout_scope_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "runtime.release.rollout_scope_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_rollout_scope(self) -> None:
        orchestrator, feature_review, correlation_id = (
            self._prepare_feature_review_episode()
        )

        transition_result = orchestrator._state_manager.apply_transition(
            case_type=feature_review.case_type,
            case_key=feature_review.case_key,
            state_model_name=feature_review.state_model_name,
            current_state=feature_review.current_state,
            current_status=feature_review.status,
            transition_name="promote_to_case_assessment",
            source_stage=feature_review.current_stage,
            target_stage="case_orchestration",
            correlation_id=correlation_id,
            episode_id=feature_review.episode_id,
            actor_id="rollout-scope-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": (
                    "Assess whether the elevated impact score warrants accountable manual review."
                )
            },
            reason=(
                "Assessment should emit governed rollout scope only after promotion readiness exists."
            ),
            **self._ready_transition_controls(),
        )

        self.assertEqual(
            transition_result.rollout_scope_status,
            "rollout_scope_defined",
        )
        self.assertEqual(
            transition_result.rollout_scope_class_id,
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            transition_result.rollout_scope_context["rollout_scope_outcome"],
            "ready_for_rollback_trigger_guard",
        )
        self.assertEqual(
            transition_result.rollout_scope_context[
                "rollout_scope_boundary_reference"
            ],
            "rollout-scope:store:001:full",
        )

    def test_rollout_scope_transport_visible_in_handoff_audit(self) -> None:
        orchestrator, feature_review, correlation_id = (
            self._prepare_feature_review_episode()
        )

        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should expose governed rollout scope in orchestrator transport."
            ),
            correlation_id=correlation_id,
            actor_id="rollout-scope-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": (
                    "Assess whether the elevated impact score warrants accountable manual review."
                )
            },
            **self._ready_transition_controls(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(
            payload["rollout_scope_status"],
            "rollout_scope_defined",
        )
        self.assertEqual(
            payload["rollout_scope_class_id"],
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            payload["rollout_scope_context"]["rollout_scope_outcome"],
            "ready_for_rollback_trigger_guard",
        )
        self.assertEqual(
            payload["rollout_scope_context"][
                "rollout_scope_boundary_reference"
            ],
            "rollout-scope:store:001:full",
        )

    def _prepare_feature_review_episode(self):
        orchestrator = self._build_case_orchestrator()
        feature = self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.feature_registry.register_feature(
            promotion_readiness_test_module.mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.FeatureDefinition(
                name="shared.control.revenue_delta.rollout_scope",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description=(
                    "Expected revenue delta used to seed rollout-scope lifecycle tests."
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
                created_at=promotion_readiness_test_module.mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.datetime.now(
                    tz=promotion_readiness_test_module.mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.UTC
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="rollout-scope-test",
        )
        raw_pipeline = (
            self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._build_raw_pipeline()
        )
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                promotion_readiness_test_module.mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-027",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=promotion_readiness_test_module.mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.datetime(
                        2026,
                        4,
                        22,
                        0,
                        0,
                        tzinfo=promotion_readiness_test_module.mutation_execution_test_module.mutation_planning_test_module.approval_test_module.threshold_test_module.UTC,
                    ),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-027",
                        "candidate_revenue": 2065.0,
                        "baseline_revenue": 1508.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="rollout-scope-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-027",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="rollout-scope-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="rollout-scope-test",
            actor_role="assistant_case_operator",
        )
        return orchestrator, feature_review, correlation_id

    def _ready_transition_controls(self) -> dict[str, object]:
        return {
            "review_resolution_class_id": "resolved_with_action",
            "review_resolution_context": {
                "review_summary": (
                    "The reviewer confirmed downstream action preparation is warranted."
                ),
                "resolution_rationale": (
                    "The required review threshold and packet lineage support action routing."
                ),
            },
            "recommendation_class_id": "recommend_act_now",
            "recommendation_context": {
                "recommendation_summary": (
                    "Act now while preserving the recommendation boundary."
                ),
                "action_path_reference": "action-path:price-adjustment-027",
                "scope_reference": "scope:store:001",
                "confidence_summary": "high_confidence",
                "constraint_summary": "inventory_and_margin_checked",
                "uncertainty_summary": "remaining_regime_uncertainty_is_bounded",
                "failure_state_context": "no_active_failure_state_detected",
            },
            "policy_output_class_id": "policy_shaped_allowance",
            "policy_output_context": {
                "policy_summary": (
                    "Preserve bounded allowance for downstream action preparation."
                ),
                "policy_output_reference": "policy-output:allowance-027",
                "policy_rationale": (
                    "Recommendation and review lineage justify bounded policy allowance while preserving action-boundary discipline."
                ),
                "action_boundary_summary": (
                    "Policy-shaped allowance only; downstream commitment and instruction remain separate."
                ),
                "allowance_reference": "allowance:store:001:price-adjustment-window-027",
            },
            "portfolio_output_class_id": "portfolio_bounded_allocation",
            "portfolio_output_context": {
                "portfolio_summary": (
                    "Preserve bounded allocation posture for downstream portfolio planning."
                ),
                "portfolio_output_reference": "portfolio-output:allocation-027",
                "portfolio_rationale": (
                    "Policy allowance lineage justifies bounded allocation posture for downstream planning."
                ),
                "action_boundary_summary": (
                    "Allocative only; downstream commitment and instruction remain separate."
                ),
                "allocation_reference": "allocation:store:001:price-adjustment-window-027",
                "allocation_weight_reference": "allocation-weight:store:001:0.75",
            },
            "action_instruction_class_id": "direct_action_instruction",
            "action_instruction_context": (
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._action_instruction_context()
            ),
            "execution_request_class_id": "direct_dispatch_request",
            "execution_request_context": (
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._direct_execution_request_context()
            ),
            "execution_dispatch_class_id": "direct_dispatch_boundary",
            "execution_dispatch_context": (
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._direct_execution_dispatch_context()
            ),
            "execution_outcome_class_id": "favorable_realized_outcome",
            "execution_outcome_context": (
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._favorable_outcome_context()
            ),
            "post_mortem_judgment_class_id": (
                "correct_recommendation_correct_execution"
            ),
            "post_mortem_judgment_context": (
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers.helpers._ready_post_mortem_context()
            ),
            "policy_learning_evidence_class_id": "policy_learning_review_candidate",
            "policy_learning_evidence_admission_context": (
                self.helpers.helpers.helpers.helpers.helpers.helpers.helpers._ready_admission_context()
            ),
            "policy_learning_update_threshold_class_id": "policy_update_candidate",
            "policy_learning_update_threshold_context": (
                self.helpers.helpers.helpers.helpers.helpers.helpers._accepted_threshold_context()
            ),
            "policy_learning_update_approval_class_id": (
                "policy_update_preparation_candidate"
            ),
            "policy_learning_update_approval_context": (
                self.helpers.helpers.helpers.helpers.helpers._approved_context()
            ),
            "policy_learning_update_preparation_class_id": (
                "policy_mutation_planning_candidate"
            ),
            "policy_learning_update_preparation_context": (
                self.helpers.helpers.helpers.helpers._prepared_context()
            ),
            "policy_learning_update_mutation_planning_class_id": (
                "policy_mutation_plan_candidate"
            ),
            "policy_learning_update_mutation_planning_context": (
                self.helpers.helpers.helpers._prepared_context()
            ),
            "policy_learning_update_mutation_execution_class_id": (
                "policy_mutation_execution_candidate"
            ),
            "policy_learning_update_mutation_execution_context": (
                self.helpers.helpers._executed_context()
            ),
            "promotion_readiness_class_id": (
                "full_scope_production_promotion_candidate"
            ),
            "promotion_readiness_context": self.helpers._ready_context(),
            "rollout_scope_class_id": "full_scope_production_promotion_candidate",
            "rollout_scope_context": self._ready_context(),
        }

    def _build_rollout_scope_controller(self) -> RolloutScopeController:
        registry = JsonReleaseRegistry(
            promotion_readiness_classes_path=(
                self.registry_root / "promotion_readiness_classes.json"
            ),
            promotion_readiness_templates_path=(
                self.registry_root / "promotion_readiness_templates.json"
            ),
            rollout_scope_classes_path=(
                self.registry_root / "rollout_scope_classes.json"
            ),
            rollout_scope_templates_path=(
                self.registry_root / "rollout_scope_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = RolloutScopeAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return RolloutScopeController(
            release_registry=registry,
            rollout_scope_audit_adapter=audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._rollout_scope_controller = (
            self.rollout_scope_controller
        )
        return orchestrator

    def _build_ready_promotion_readiness(self):
        return self.helpers.promotion_readiness_gate.generate(
            promotion_readiness_test_module.PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=(
                    self.helpers._build_ready_update_mutation_execution()
                ),
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )

    def _build_conditional_promotion_readiness(self):
        return self.helpers.promotion_readiness_gate.generate(
            promotion_readiness_test_module.PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=(
                    self.helpers._build_restricted_update_mutation_execution()
                ),
                promotion_readiness_class_id="local_scope_release_candidate",
                promotion_readiness_author_role="release_authority",
                promotion_readiness_context=self.helpers._local_scope_context(),
                correlation_id=str(uuid4()),
                actor_id="rollout-scope-test",
            )
        )

    def _ready_context(self) -> dict[str, object]:
        return {
            "rollout_scope_boundary_reference": "rollout-scope:store:001:full",
            "exposure_boundary_reference": "exposure-boundary:store:001:full",
            "rollout_boundary_summary": (
                "Rollout scope remains explicit, bounded, and exposure-controlled without widening into rollback-trigger control or post-release watch execution."
            ),
        }

    def _conditional_context(self) -> dict[str, object]:
        return {
            "rollout_scope_boundary_reference": (
                "rollout-scope:store:001:promo-window"
            ),
            "exposure_boundary_reference": (
                "exposure-boundary:store:001:promo-window"
            ),
            "rollout_boundary_summary": (
                "Conditional production exposure remains explicitly narrowed to the approved local scope while broader entitlement stays ungranted."
            ),
        }

    def _deferred_context(self) -> dict[str, object]:
        return {
            **self._ready_context(),
            "rollout_scope_prerequisite_reference": (
                "rollout-prerequisites:store:001:price-band"
            ),
            "outstanding_rollout_scope_prerequisites": [
                "release-watch-observer-confirmation",
                "exposure-review-cadence-confirmation"
            ],
            "follow_up_review_reference": "review:rollout-scope:001",
        }


if __name__ == "__main__":
    unittest.main()