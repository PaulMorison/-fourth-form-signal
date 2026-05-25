from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from runtime.release import (  # noqa: E402
    JsonReleaseRegistry,
    RollbackTriggerAuditAdapter,
    RollbackTriggerGuard,
    RollbackTriggerGuardRequest,
)
from tests.unit import test_rollout_scope_controller as rollout_scope_test_module  # noqa: E402


class RollbackTriggerGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = rollout_scope_test_module.RolloutScopeControllerTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.rollback_trigger_guard = self._build_rollback_trigger_guard()

    def test_direct_ready_for_release_watch_discipline(self) -> None:
        rollout_scope = self._build_ready_rollout_scope()

        rollback_trigger = self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )

        self.assertEqual(
            rollback_trigger.rollback_trigger_status,
            "rollback_trigger_named",
        )
        self.assertEqual(
            rollback_trigger.rollback_trigger_outcome,
            "ready_for_release_watch_discipline",
        )
        self.assertEqual(
            rollback_trigger.rollback_trigger_reference,
            "rollback-trigger:store:001:price-band",
        )

    def test_conditionally_ready_for_release_watch_discipline(self) -> None:
        rollout_scope = self._build_conditional_rollout_scope()

        rollback_trigger = self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=rollout_scope,
                rollback_trigger_class_id="conditional_production_release",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )

        self.assertEqual(
            rollback_trigger.rollback_trigger_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            rollback_trigger.rollback_trigger_outcome,
            "conditionally_ready_for_release_watch_discipline",
        )
        self.assertEqual(
            rollback_trigger.rollback_plan_reference,
            "rollback-plan:store:001:price-band",
        )

    def test_deferred_pending_rollback_trigger_evidence(self) -> None:
        rollout_scope = self._build_ready_rollout_scope()

        rollback_trigger = self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=rollout_scope,
                rollback_trigger_class_id="deferred_release_state",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )

        self.assertEqual(
            rollback_trigger.rollback_trigger_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            rollback_trigger.rollback_trigger_outcome,
            "deferred_pending_rollback_trigger_evidence",
        )
        self.assertIn(
            "named-watch-response-threshold",
            rollback_trigger.outstanding_rollback_trigger_prerequisites,
        )

    def test_blocked_missing_context(self) -> None:
        rollout_scope = self._build_ready_rollout_scope()

        rollback_trigger = self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context={
                    "rollback_trigger_reference": (
                        "rollback-trigger:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )

        self.assertEqual(
            rollback_trigger.rollback_trigger_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "rollback_plan_reference",
            rollback_trigger.missing_rollback_trigger_fields,
        )

    def test_rejected_for_rollback_trigger_use(self) -> None:
        rollout_scope = self._build_ready_rollout_scope()

        rollback_trigger = self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Exposure remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )

        self.assertEqual(
            rollback_trigger.rollback_trigger_status,
            "rejected_for_rollback_trigger_use",
        )
        self.assertEqual(
            rollback_trigger.rollback_trigger_outcome,
            "rejected_for_rollback_trigger_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        rollout_scope = self._build_ready_rollout_scope()

        rollback_trigger = self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context={
                    **self._ready_context(),
                    "release_observation_reference": (
                        "release-observation:store:001:price-band"
                    ),
                    "rollback_decision_reference": (
                        "rollback-decision:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )

        self.assertEqual(
            rollback_trigger.rollback_trigger_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "release_observation_reference",
            rollback_trigger.prohibited_rollback_trigger_fields_present,
        )
        self.assertIn(
            "rollback_decision_reference",
            rollback_trigger.prohibited_rollback_trigger_fields_present,
        )

    def test_lineage_preservation(self) -> None:
        rollout_scope = self._build_ready_rollout_scope()

        rollback_trigger = self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )

        self.assertEqual(
            rollback_trigger.lineage["rollout_scope_id"],
            rollout_scope.rollout_scope_id,
        )
        self.assertEqual(
            rollback_trigger.lineage["promotion_readiness_id"],
            rollout_scope.lineage["promotion_readiness_id"],
        )

    def test_audit_emission(self) -> None:
        ready_rollout_scope = self._build_ready_rollout_scope()
        conditional_rollout_scope = self._build_conditional_rollout_scope()

        self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=ready_rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )
        self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=conditional_rollout_scope,
                rollback_trigger_class_id="conditional_production_release",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )
        self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=ready_rollout_scope,
                rollback_trigger_class_id="deferred_release_state",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )
        self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=ready_rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context={
                    "rollback_trigger_reference": (
                        "rollback-trigger:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )
        self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=ready_rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Exposure remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )
        self.rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=ready_rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context={
                    **self._ready_context(),
                    "release_observation_reference": (
                        "release-observation:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn("runtime.release.rollback_trigger_recorded", event_types)
        self.assertIn("runtime.release.rollback_trigger_blocked", event_types)
        self.assertIn(
            "runtime.release.rollback_trigger_ready_for_release_watch_discipline",
            event_types,
        )
        self.assertIn(
            (
                "runtime.release.rollback_trigger_conditionally_ready_for_release_watch_discipline"
            ),
            event_types,
        )
        self.assertIn(
            "runtime.release.rollback_trigger_deferred_pending_rollback_trigger_evidence",
            event_types,
        )
        self.assertIn(
            "runtime.release.rollback_trigger_missing_context",
            event_types,
        )
        self.assertIn(
            "runtime.release.rollback_trigger_rejected_for_rollback_trigger_use",
            event_types,
        )
        self.assertIn(
            "runtime.release.rollback_trigger_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "runtime.release.rollback_trigger_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_rollback_trigger(self) -> None:
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
            actor_id="rollback-trigger-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": (
                    "Assess whether the elevated impact score warrants accountable manual review."
                )
            },
            reason=(
                "Assessment should emit governed rollback triggers only after governed rollout scope exists."
            ),
            **self._ready_transition_controls(),
        )

        self.assertEqual(
            transition_result.rollback_trigger_status,
            "rollback_trigger_named",
        )
        self.assertEqual(
            transition_result.rollback_trigger_class_id,
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            transition_result.rollback_trigger_context["rollback_trigger_outcome"],
            "ready_for_release_watch_discipline",
        )
        self.assertEqual(
            transition_result.rollback_trigger_context["rollback_trigger_reference"],
            "rollback-trigger:store:001:price-band",
        )

    def test_rollback_trigger_transport_visible_in_handoff_audit(self) -> None:
        orchestrator, feature_review, correlation_id = (
            self._prepare_feature_review_episode()
        )

        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should expose governed rollback triggers in orchestrator transport."
            ),
            correlation_id=correlation_id,
            actor_id="rollback-trigger-test",
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
            payload["rollback_trigger_status"],
            "rollback_trigger_named",
        )
        self.assertEqual(
            payload["rollback_trigger_class_id"],
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            payload["rollback_trigger_context"]["rollback_trigger_outcome"],
            "ready_for_release_watch_discipline",
        )
        self.assertEqual(
            payload["rollback_trigger_context"]["rollback_trigger_reference"],
            "rollback-trigger:store:001:price-band",
        )

    def _prepare_feature_review_episode(self):
        orchestrator, feature_review, correlation_id = (
            self.helpers._prepare_feature_review_episode()
        )
        orchestrator._state_manager._rollback_trigger_guard = (
            self.rollback_trigger_guard
        )
        return orchestrator, feature_review, correlation_id

    def _ready_transition_controls(self) -> dict[str, object]:
        return {
            **self.helpers._ready_transition_controls(),
            "rollback_trigger_class_id": (
                "full_scope_production_promotion_candidate"
            ),
            "rollback_trigger_context": self._ready_context(),
        }

    def _build_rollback_trigger_guard(self) -> RollbackTriggerGuard:
        registry = JsonReleaseRegistry(
            promotion_readiness_classes_path=(
                self.registry_root / "promotion_readiness_classes.json"
            ),
            promotion_readiness_templates_path=(
                self.registry_root / "promotion_readiness_templates.json"
            ),
            rollout_scope_classes_path=(self.registry_root / "rollout_scope_classes.json"),
            rollout_scope_templates_path=(
                self.registry_root / "rollout_scope_templates.json"
            ),
            rollback_trigger_classes_path=(
                self.registry_root / "rollback_trigger_classes.json"
            ),
            rollback_trigger_templates_path=(
                self.registry_root / "rollback_trigger_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = RollbackTriggerAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return RollbackTriggerGuard(
            release_registry=registry,
            rollback_trigger_audit_adapter=audit_adapter,
        )

    def _build_ready_rollout_scope(self):
        return self.helpers.rollout_scope_controller.generate(
            rollout_scope_test_module.RolloutScopeControllerRequest(
                promotion_readiness=self.helpers._build_ready_promotion_readiness(),
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="release_authority",
                rollout_scope_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )

    def _build_conditional_rollout_scope(self):
        return self.helpers.rollout_scope_controller.generate(
            rollout_scope_test_module.RolloutScopeControllerRequest(
                promotion_readiness=self.helpers._build_conditional_promotion_readiness(),
                rollout_scope_class_id="conditional_production_release",
                rollout_scope_author_role="release_authority",
                rollout_scope_context=self.helpers._conditional_context(),
                correlation_id=str(uuid4()),
                actor_id="rollback-trigger-test",
            )
        )

    def _ready_context(self) -> dict[str, object]:
        return {
            "rollback_trigger_reference": "rollback-trigger:store:001:price-band",
            "rollback_plan_reference": "rollback-plan:store:001:price-band",
        }

    def _deferred_context(self) -> dict[str, object]:
        return {
            **self._ready_context(),
            "rollback_trigger_prerequisite_reference": (
                "rollback-trigger-prerequisites:store:001:price-band"
            ),
            "outstanding_rollback_trigger_prerequisites": [
                "named-watch-response-threshold",
                "release-owner-escalation-confirmation"
            ],
            "follow_up_review_reference": "review:rollback-trigger:001",
        }


if __name__ == "__main__":
    unittest.main()