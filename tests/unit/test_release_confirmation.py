from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from runtime.release import (  # noqa: E402
    JsonReleaseRegistry,
    ReleaseConfirmation,
    ReleaseConfirmationAuditAdapter,
    ReleaseConfirmationRequest,
)
from tests.unit import test_release_watch_discipline as release_watch_test_module  # noqa: E402


class ReleaseConfirmationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = release_watch_test_module.ReleaseWatchDisciplineTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.release_confirmation = self._build_release_confirmation()

    def test_direct_confirmed_for_broader_trusted_production_use(self) -> None:
        release_watch_discipline = self._build_ready_release_watch_discipline()

        release_confirmation = self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="release_authority",
                release_confirmation_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )

        self.assertEqual(
            release_confirmation.release_confirmation_status,
            "release_confirmation_judged",
        )
        self.assertEqual(
            release_confirmation.release_confirmation_outcome,
            "confirmed_for_broader_trusted_production_use",
        )
        self.assertEqual(
            release_confirmation.release_confirmation_judgment,
            "release-confirmed:store:001:price-band",
        )

    def test_conditionally_confirmed_for_bounded_production_use(self) -> None:
        release_watch_discipline = self._build_conditional_release_watch_discipline()

        release_confirmation = self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=release_watch_discipline,
                release_confirmation_class_id="conditional_production_release",
                release_confirmation_author_role="release_authority",
                release_confirmation_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Confirmation remains bounded to the approved local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )

        self.assertEqual(
            release_confirmation.release_confirmation_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            release_confirmation.release_confirmation_outcome,
            "conditionally_confirmed_for_bounded_production_use",
        )
        self.assertEqual(
            release_confirmation.promotion_scope_restriction_reference,
            "scope:store:001:promo-window",
        )

    def test_deferred_pending_release_confirmation_evidence(self) -> None:
        release_watch_discipline = self._build_ready_release_watch_discipline()

        release_confirmation = self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=release_watch_discipline,
                release_confirmation_class_id="deferred_release_state",
                release_confirmation_author_role="release_authority",
                release_confirmation_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )

        self.assertEqual(
            release_confirmation.release_confirmation_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            release_confirmation.release_confirmation_outcome,
            "deferred_pending_release_confirmation_evidence",
        )
        self.assertIn(
            "confirmation-authority-signoff",
            release_confirmation.outstanding_release_confirmation_prerequisites,
        )

    def test_blocked_missing_context(self) -> None:
        release_watch_discipline = self._build_ready_release_watch_discipline()

        release_confirmation = self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="release_authority",
                release_confirmation_context={
                    "release_confirmation_judgment": (
                        "release-confirmed:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )

        self.assertEqual(
            release_confirmation.release_confirmation_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "release_confirmation_threshold_evidence_reference",
            release_confirmation.missing_release_confirmation_fields,
        )
        self.assertIn(
            "release_confirmation_authority_reference",
            release_confirmation.missing_release_confirmation_fields,
        )

    def test_rejected_for_release_confirmation_use(self) -> None:
        release_watch_discipline = self._build_ready_release_watch_discipline()

        release_confirmation = self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="release_authority",
                release_confirmation_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Confirmation remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )

        self.assertEqual(
            release_confirmation.release_confirmation_status,
            "rejected_for_release_confirmation_use",
        )
        self.assertEqual(
            release_confirmation.release_confirmation_outcome,
            "rejected_for_release_confirmation_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        release_watch_discipline = self._build_ready_release_watch_discipline()

        release_confirmation = self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="release_authority",
                release_confirmation_context={
                    **self._ready_context(),
                    "release_observation_reference": (
                        "release-observation:store:001:price-band"
                    ),
                    "contained_rollback_reference": (
                        "contained-rollback:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )

        self.assertEqual(
            release_confirmation.release_confirmation_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "release_observation_reference",
            release_confirmation.prohibited_release_confirmation_fields_present,
        )
        self.assertIn(
            "contained_rollback_reference",
            release_confirmation.prohibited_release_confirmation_fields_present,
        )

    def test_lineage_preservation(self) -> None:
        release_watch_discipline = self._build_ready_release_watch_discipline()

        release_confirmation = self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="release_authority",
                release_confirmation_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )

        self.assertEqual(
            release_confirmation.lineage["release_watch_discipline_id"],
            release_watch_discipline.release_watch_discipline_id,
        )
        self.assertEqual(
            release_confirmation.lineage["rollback_trigger_id"],
            release_watch_discipline.lineage["rollback_trigger_id"],
        )

    def test_audit_emission(self) -> None:
        ready_release_watch_discipline = self._build_ready_release_watch_discipline()
        conditional_release_watch_discipline = (
            self._build_conditional_release_watch_discipline()
        )

        self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=ready_release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="release_authority",
                release_confirmation_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )
        self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=conditional_release_watch_discipline,
                release_confirmation_class_id="conditional_production_release",
                release_confirmation_author_role="release_authority",
                release_confirmation_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Confirmation remains bounded to the approved local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )
        self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=ready_release_watch_discipline,
                release_confirmation_class_id="deferred_release_state",
                release_confirmation_author_role="release_authority",
                release_confirmation_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )
        self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=ready_release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="release_authority",
                release_confirmation_context={
                    "release_confirmation_judgment": (
                        "release-confirmed:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )
        self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=ready_release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="release_authority",
                release_confirmation_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Confirmation remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )
        self.release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=ready_release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="release_authority",
                release_confirmation_context={
                    **self._ready_context(),
                    "release_observation_reference": (
                        "release-observation:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn("runtime.release.release_confirmation_recorded", event_types)
        self.assertIn("runtime.release.release_confirmation_blocked", event_types)
        self.assertIn(
            (
                "runtime.release.release_confirmation_confirmed_for_broader_trusted_production_use"
            ),
            event_types,
        )
        self.assertIn(
            (
                "runtime.release.release_confirmation_conditionally_confirmed_for_bounded_production_use"
            ),
            event_types,
        )
        self.assertIn(
            (
                "runtime.release.release_confirmation_deferred_pending_release_confirmation_evidence"
            ),
            event_types,
        )
        self.assertIn(
            "runtime.release.release_confirmation_missing_context",
            event_types,
        )
        self.assertIn(
            (
                "runtime.release.release_confirmation_rejected_for_release_confirmation_use"
            ),
            event_types,
        )
        self.assertIn(
            "runtime.release.release_confirmation_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_confirmation_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_release_confirmation(self) -> None:
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
            actor_id="release-confirmation-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": (
                    "Assess whether the elevated impact score warrants accountable manual review."
                )
            },
            reason=(
                "Assessment should emit governed release confirmation only after governed release-watch discipline exists."
            ),
            **self._ready_transition_controls(),
        )

        self.assertEqual(
            transition_result.release_confirmation_status,
            "release_confirmation_judged",
        )
        self.assertEqual(
            transition_result.release_confirmation_class_id,
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            transition_result.release_confirmation_context[
                "release_confirmation_outcome"
            ],
            "confirmed_for_broader_trusted_production_use",
        )
        self.assertEqual(
            transition_result.release_confirmation_context[
                "release_confirmation_threshold_evidence_reference"
            ],
            "release-confirmation-evidence:store:001:price-band",
        )

    def test_release_confirmation_transport_visible_in_handoff_audit(self) -> None:
        orchestrator, feature_review, correlation_id = (
            self._prepare_feature_review_episode()
        )

        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should expose governed release confirmation in orchestrator transport."
            ),
            correlation_id=correlation_id,
            actor_id="release-confirmation-test",
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
            payload["release_confirmation_status"],
            "release_confirmation_judged",
        )
        self.assertEqual(
            payload["release_confirmation_class_id"],
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            payload["release_confirmation_context"][
                "release_confirmation_outcome"
            ],
            "confirmed_for_broader_trusted_production_use",
        )
        self.assertEqual(
            payload["release_confirmation_context"][
                "release_confirmation_threshold_evidence_reference"
            ],
            "release-confirmation-evidence:store:001:price-band",
        )

    def _prepare_feature_review_episode(self):
        orchestrator, feature_review, correlation_id = (
            self.helpers._prepare_feature_review_episode()
        )
        orchestrator._state_manager._release_confirmation = self.release_confirmation
        return orchestrator, feature_review, correlation_id

    def _ready_transition_controls(self) -> dict[str, object]:
        return {
            **self.helpers._ready_transition_controls(),
            "release_confirmation_class_id": (
                "full_scope_production_promotion_candidate"
            ),
            "release_confirmation_context": self._ready_context(),
        }

    def _build_release_confirmation(self) -> ReleaseConfirmation:
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
            release_confirmation_classes_path=(
                self.registry_root / "release_confirmation_classes.json"
            ),
            release_confirmation_templates_path=(
                self.registry_root / "release_confirmation_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = ReleaseConfirmationAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ReleaseConfirmation(
            release_registry=registry,
            release_confirmation_audit_adapter=audit_adapter,
        )

    def _build_ready_release_watch_discipline(self):
        return self.helpers.release_watch_discipline.generate(
            release_watch_test_module.ReleaseWatchDisciplineRequest(
                rollback_trigger=self.helpers._build_ready_rollback_trigger(),
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )

    def _build_conditional_release_watch_discipline(self):
        return self.helpers.release_watch_discipline.generate(
            release_watch_test_module.ReleaseWatchDisciplineRequest(
                rollback_trigger=self.helpers._build_conditional_rollback_trigger(),
                release_watch_discipline_class_id="conditional_production_release",
                release_watch_discipline_author_role="release_authority",
                release_watch_discipline_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-confirmation-test",
            )
        )

    def _ready_context(self) -> dict[str, object]:
        return {
            "release_confirmation_judgment": (
                "release-confirmed:store:001:price-band"
            ),
            "release_confirmation_threshold_evidence_reference": (
                "release-confirmation-evidence:store:001:price-band"
            ),
            "release_confirmation_authority_reference": (
                "release-confirmation-authority:store:001:price-band"
            ),
        }

    def _deferred_context(self) -> dict[str, object]:
        return {
            **self._ready_context(),
            "release_confirmation_prerequisite_reference": (
                "release-confirmation-prerequisites:store:001:price-band"
            ),
            "outstanding_release_confirmation_prerequisites": [
                "confirmation-authority-signoff",
                "threshold-evidence-reconciliation"
            ],
            "follow_up_review_reference": "review:release-confirmation:001",
        }


if __name__ == "__main__":
    unittest.main()