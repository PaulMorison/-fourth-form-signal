from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from runtime.release import (  # noqa: E402
    JsonReleaseRegistry,
    ReleaseWatchDiscipline,
    ReleaseWatchDisciplineAuditAdapter,
    ReleaseWatchDisciplineRequest,
)
from tests.unit import test_rollback_trigger_guard as rollback_trigger_test_module  # noqa: E402


class ReleaseWatchDisciplineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = rollback_trigger_test_module.RollbackTriggerGuardTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.release_watch_discipline = self._build_release_watch_discipline()

    def test_direct_ready_for_release_confirmation(self) -> None:
        rollback_trigger = self._build_ready_rollback_trigger()

        release_watch_discipline = self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )

        self.assertEqual(
            release_watch_discipline.release_watch_discipline_status,
            "release_watch_discipline_defined",
        )
        self.assertEqual(
            release_watch_discipline.release_watch_discipline_outcome,
            "ready_for_release_confirmation",
        )
        self.assertEqual(
            release_watch_discipline.release_confirmation_window,
            "release-confirmation-window:store:001:t-plus-7d",
        )

    def test_conditionally_ready_for_release_confirmation(self) -> None:
        rollback_trigger = self._build_conditional_rollback_trigger()

        release_watch_discipline = self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=rollback_trigger,
                release_watch_discipline_class_id="conditional_production_release",
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )

        self.assertEqual(
            release_watch_discipline.release_watch_discipline_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            release_watch_discipline.release_watch_discipline_outcome,
            "conditionally_ready_for_release_confirmation",
        )
        self.assertEqual(
            release_watch_discipline.release_watch_owner_reference,
            "release-owner:store:001:price-band",
        )

    def test_deferred_pending_release_watch_discipline_evidence(self) -> None:
        rollback_trigger = self._build_ready_rollback_trigger()

        release_watch_discipline = self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=rollback_trigger,
                release_watch_discipline_class_id="deferred_release_state",
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )

        self.assertEqual(
            release_watch_discipline.release_watch_discipline_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            release_watch_discipline.release_watch_discipline_outcome,
            "deferred_pending_release_watch_discipline_evidence",
        )
        self.assertIn(
            "release-watch-owner-confirmation",
            release_watch_discipline.outstanding_release_watch_prerequisites,
        )

    def test_blocked_missing_context(self) -> None:
        rollback_trigger = self._build_ready_rollback_trigger()

        release_watch_discipline = self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context={
                    "release_confirmation_window": (
                        "release-confirmation-window:store:001:t-plus-7d"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )

        self.assertEqual(
            release_watch_discipline.release_watch_discipline_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "release_response_threshold_reference",
            release_watch_discipline.missing_release_watch_discipline_fields,
        )
        self.assertIn(
            "release_watch_owner_reference",
            release_watch_discipline.missing_release_watch_discipline_fields,
        )

    def test_rejected_for_release_watch_discipline_use(self) -> None:
        rollback_trigger = self._build_ready_rollback_trigger()

        release_watch_discipline = self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Exposure remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )

        self.assertEqual(
            release_watch_discipline.release_watch_discipline_status,
            "rejected_for_release_watch_discipline_use",
        )
        self.assertEqual(
            release_watch_discipline.release_watch_discipline_outcome,
            "rejected_for_release_watch_discipline_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        rollback_trigger = self._build_ready_rollback_trigger()

        release_watch_discipline = self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context={
                    **self._ready_context(),
                    "release_observation_reference": (
                        "release-observation:store:001:price-band"
                    ),
                    "monitor_alert_reference": (
                        "monitor-alert:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )

        self.assertEqual(
            release_watch_discipline.release_watch_discipline_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "release_observation_reference",
            release_watch_discipline.prohibited_release_watch_discipline_fields_present,
        )
        self.assertIn(
            "monitor_alert_reference",
            release_watch_discipline.prohibited_release_watch_discipline_fields_present,
        )

    def test_lineage_preservation(self) -> None:
        rollback_trigger = self._build_ready_rollback_trigger()

        release_watch_discipline = self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )

        self.assertEqual(
            release_watch_discipline.lineage["rollback_trigger_id"],
            rollback_trigger.rollback_trigger_id,
        )
        self.assertEqual(
            release_watch_discipline.lineage["rollout_scope_id"],
            rollback_trigger.lineage["rollout_scope_id"],
        )

    def test_audit_emission(self) -> None:
        ready_rollback_trigger = self._build_ready_rollback_trigger()
        conditional_rollback_trigger = self._build_conditional_rollback_trigger()

        self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=ready_rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )
        self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=conditional_rollback_trigger,
                release_watch_discipline_class_id="conditional_production_release",
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )
        self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=ready_rollback_trigger,
                release_watch_discipline_class_id="deferred_release_state",
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )
        self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=ready_rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context={
                    "release_confirmation_window": (
                        "release-confirmation-window:store:001:t-plus-7d"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )
        self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=ready_rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Exposure remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )
        self.release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=ready_rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context={
                    **self._ready_context(),
                    "release_observation_reference": (
                        "release-observation:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn(
            "runtime.release.release_watch_discipline_recorded",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_watch_discipline_blocked",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_watch_discipline_ready_for_release_confirmation",
            event_types,
        )
        self.assertIn(
            (
                "runtime.release.release_watch_discipline_conditionally_ready_for_release_confirmation"
            ),
            event_types,
        )
        self.assertIn(
            (
                "runtime.release.release_watch_discipline_deferred_pending_release_watch_discipline_evidence"
            ),
            event_types,
        )
        self.assertIn(
            "runtime.release.release_watch_discipline_missing_context",
            event_types,
        )
        self.assertIn(
            (
                "runtime.release.release_watch_discipline_rejected_for_release_watch_discipline_use"
            ),
            event_types,
        )
        self.assertIn(
            (
                "runtime.release.release_watch_discipline_fallback_template_applied"
            ),
            event_types,
        )
        self.assertIn(
            (
                "runtime.release.release_watch_discipline_prohibited_overlap_blocked"
            ),
            event_types,
        )

    def test_integration_with_lifecycle_through_release_watch_discipline(self) -> None:
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
            actor_id="release-watch-discipline-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": (
                    "Assess whether the elevated impact score warrants accountable manual review."
                )
            },
            reason=(
                "Assessment should emit governed release-watch discipline only after governed rollback triggers exist."
            ),
            **self._ready_transition_controls(),
        )

        self.assertEqual(
            transition_result.release_watch_discipline_status,
            "release_watch_discipline_defined",
        )
        self.assertEqual(
            transition_result.release_watch_discipline_class_id,
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            transition_result.release_watch_discipline_context[
                "release_watch_discipline_outcome"
            ],
            "ready_for_release_confirmation",
        )
        self.assertEqual(
            transition_result.release_watch_discipline_context[
                "release_confirmation_window"
            ],
            "release-confirmation-window:store:001:t-plus-7d",
        )

    def test_release_watch_discipline_transport_visible_in_handoff_audit(
        self,
    ) -> None:
        orchestrator, feature_review, correlation_id = (
            self._prepare_feature_review_episode()
        )

        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should expose governed release-watch discipline in orchestrator transport."
            ),
            correlation_id=correlation_id,
            actor_id="release-watch-discipline-test",
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
            payload["release_watch_discipline_status"],
            "release_watch_discipline_defined",
        )
        self.assertEqual(
            payload["release_watch_discipline_class_id"],
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            payload["release_watch_discipline_context"][
                "release_watch_discipline_outcome"
            ],
            "ready_for_release_confirmation",
        )
        self.assertEqual(
            payload["release_watch_discipline_context"][
                "release_confirmation_window"
            ],
            "release-confirmation-window:store:001:t-plus-7d",
        )

    def _prepare_feature_review_episode(self):
        orchestrator, feature_review, correlation_id = (
            self.helpers._prepare_feature_review_episode()
        )
        orchestrator._state_manager._release_watch_discipline = (
            self.release_watch_discipline
        )
        return orchestrator, feature_review, correlation_id

    def _ready_transition_controls(self) -> dict[str, object]:
        return {
            **self.helpers._ready_transition_controls(),
            "release_watch_discipline_class_id": (
                "full_scope_production_promotion_candidate"
            ),
            "release_watch_discipline_context": self._ready_context(),
        }

    def _build_release_watch_discipline(self) -> ReleaseWatchDiscipline:
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
            release_watch_discipline_classes_path=(
                self.registry_root / "release_watch_discipline_classes.json"
            ),
            release_watch_discipline_templates_path=(
                self.registry_root / "release_watch_discipline_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = ReleaseWatchDisciplineAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ReleaseWatchDiscipline(
            release_registry=registry,
            release_watch_discipline_audit_adapter=audit_adapter,
        )

    def _build_ready_rollback_trigger(self):
        return self.helpers.rollback_trigger_guard.generate(
            rollback_trigger_test_module.RollbackTriggerGuardRequest(
                rollout_scope=self.helpers._build_ready_rollout_scope(),
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )

    def _build_conditional_rollback_trigger(self):
        return self.helpers.rollback_trigger_guard.generate(
            rollback_trigger_test_module.RollbackTriggerGuardRequest(
                rollout_scope=self.helpers._build_conditional_rollout_scope(),
                rollback_trigger_class_id="conditional_production_release",
                rollback_trigger_author_role="release_authority",
                rollback_trigger_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-watch-discipline-test",
            )
        )

    def _ready_context(self) -> dict[str, object]:
        return {
            "release_watch_discipline_summary": (
                "Post-release watch discipline remains explicit through named watch and confirmation windows, explicit response thresholds, and a named owning surface without widening into watch execution or monitoring."
            ),
            "release_confirmation_window": (
                "release-confirmation-window:store:001:t-plus-7d"
            ),
            "release_response_threshold_reference": (
                "release-response-threshold:store:001:price-band"
            ),
            "release_watch_owner_reference": (
                "release-owner:store:001:price-band"
            ),
            "release_escalation_path_reference": (
                "release-escalation-path:store:001:price-band"
            ),
        }

    def _deferred_context(self) -> dict[str, object]:
        return {
            **self._ready_context(),
            "release_watch_prerequisite_reference": (
                "release-watch-prerequisites:store:001:price-band"
            ),
            "outstanding_release_watch_prerequisites": [
                "release-watch-owner-confirmation",
                "release-confirmation-window-confirmation"
            ],
            "follow_up_review_reference": "review:release-watch-discipline:001",
        }


if __name__ == "__main__":
    unittest.main()