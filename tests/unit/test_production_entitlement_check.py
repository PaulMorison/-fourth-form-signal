from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from runtime.release import (  # noqa: E402
    JsonReleaseRegistry,
    ProductionEntitlementCheck,
    ProductionEntitlementCheckAuditAdapter,
    ProductionEntitlementCheckRequest,
)
from tests.unit import test_release_confirmation as release_confirmation_test_module  # noqa: E402


class ProductionEntitlementCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = release_confirmation_test_module.ReleaseConfirmationTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.production_entitlement_check = self._build_production_entitlement_check()

    def test_direct_approved_for_broader_trusted_production_entitlement(self) -> None:
        release_confirmation = self._build_ready_release_confirmation()

        production_entitlement_check = self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )

        self.assertEqual(
            production_entitlement_check.production_entitlement_check_status,
            "production_entitlement_checked",
        )
        self.assertEqual(
            production_entitlement_check.production_entitlement_check_outcome,
            "approved_for_broader_trusted_production_entitlement",
        )
        self.assertEqual(
            production_entitlement_check.production_entitlement_judgment,
            "production-entitlement-approved:store:001:price-band",
        )

    def test_conditionally_approved_for_bounded_production_entitlement(self) -> None:
        release_confirmation = self._build_conditional_release_confirmation()

        production_entitlement_check = self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=release_confirmation,
                production_entitlement_check_class_id="conditional_production_release",
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )

        self.assertEqual(
            production_entitlement_check.production_entitlement_check_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            production_entitlement_check.production_entitlement_check_outcome,
            "conditionally_approved_for_bounded_production_entitlement",
        )
        self.assertEqual(
            production_entitlement_check.promotion_scope_restriction_reference,
            "scope:store:001:promo-window",
        )

    def test_deferred_pending_production_entitlement_evidence(self) -> None:
        release_confirmation = self._build_ready_release_confirmation()

        production_entitlement_check = self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=release_confirmation,
                production_entitlement_check_class_id="deferred_release_state",
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )

        self.assertEqual(
            production_entitlement_check.production_entitlement_check_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            production_entitlement_check.production_entitlement_check_outcome,
            "deferred_pending_production_entitlement_evidence",
        )
        self.assertIn(
            "entitlement-authority-signoff",
            production_entitlement_check.outstanding_production_entitlement_prerequisites,
        )

    def test_blocked_missing_context(self) -> None:
        release_confirmation = self._build_ready_release_confirmation()

        production_entitlement_check = self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context={
                    "production_entitlement_judgment": (
                        "production-entitlement-approved:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )

        self.assertEqual(
            production_entitlement_check.production_entitlement_check_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "production_entitlement_evidence_reference",
            production_entitlement_check.missing_production_entitlement_check_fields,
        )
        self.assertIn(
            "production_entitlement_authority_reference",
            production_entitlement_check.missing_production_entitlement_check_fields,
        )

    def test_rejected_for_production_entitlement_use(self) -> None:
        release_confirmation = self._build_ready_release_confirmation()

        production_entitlement_check = self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Entitlement remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )

        self.assertEqual(
            production_entitlement_check.production_entitlement_check_status,
            "rejected_for_production_entitlement_use",
        )
        self.assertEqual(
            production_entitlement_check.production_entitlement_check_outcome,
            "rejected_for_production_entitlement_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        release_confirmation = self._build_ready_release_confirmation()

        production_entitlement_check = self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context={
                    **self._ready_context(),
                    "contained_rollback_reference": (
                        "contained-rollback:store:001:price-band"
                    ),
                    "monitoring_admission_reference": (
                        "monitoring-admission:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )

        self.assertEqual(
            production_entitlement_check.production_entitlement_check_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "contained_rollback_reference",
            production_entitlement_check.prohibited_production_entitlement_fields_present,
        )
        self.assertIn(
            "monitoring_admission_reference",
            production_entitlement_check.prohibited_production_entitlement_fields_present,
        )

    def test_lineage_preservation(self) -> None:
        release_confirmation = self._build_ready_release_confirmation()

        production_entitlement_check = self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )

        self.assertEqual(
            production_entitlement_check.lineage["release_confirmation_id"],
            release_confirmation.release_confirmation_id,
        )
        self.assertEqual(
            production_entitlement_check.lineage["release_watch_discipline_id"],
            release_confirmation.lineage["release_watch_discipline_id"],
        )

    def test_audit_emission(self) -> None:
        ready_release_confirmation = self._build_ready_release_confirmation()
        conditional_release_confirmation = self._build_conditional_release_confirmation()

        self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=ready_release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )
        self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=conditional_release_confirmation,
                production_entitlement_check_class_id="conditional_production_release",
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )
        self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=ready_release_confirmation,
                production_entitlement_check_class_id="deferred_release_state",
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )
        self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=ready_release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context={
                    "production_entitlement_judgment": (
                        "production-entitlement-approved:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )
        self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=ready_release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Entitlement remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )
        self.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=ready_release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context={
                    **self._ready_context(),
                    "contained_rollback_reference": (
                        "contained-rollback:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn(
            "runtime.release.production_entitlement_check_recorded",
            event_types,
        )
        self.assertIn(
            "runtime.release.production_entitlement_check_blocked",
            event_types,
        )
        self.assertIn(
            "runtime.release.production_entitlement_check_approved_for_broader_trusted_production_entitlement",
            event_types,
        )
        self.assertIn(
            "runtime.release.production_entitlement_check_conditionally_approved_for_bounded_production_entitlement",
            event_types,
        )
        self.assertIn(
            "runtime.release.production_entitlement_check_deferred_pending_production_entitlement_evidence",
            event_types,
        )
        self.assertIn(
            "runtime.release.production_entitlement_check_missing_context",
            event_types,
        )
        self.assertIn(
            "runtime.release.production_entitlement_check_rejected_for_production_entitlement_use",
            event_types,
        )
        self.assertIn(
            "runtime.release.production_entitlement_check_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "runtime.release.production_entitlement_check_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_production_entitlement_check(self) -> None:
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
            actor_id="production-entitlement-check-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": (
                    "Assess whether the elevated impact score warrants accountable manual review."
                )
            },
            reason=(
                "Assessment should emit governed production entitlement only after governed release confirmation exists."
            ),
            **self._ready_transition_controls(),
        )

        self.assertEqual(
            transition_result.production_entitlement_check_status,
            "production_entitlement_checked",
        )
        self.assertEqual(
            transition_result.production_entitlement_check_class_id,
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            transition_result.production_entitlement_check_context[
                "production_entitlement_check_outcome"
            ],
            "approved_for_broader_trusted_production_entitlement",
        )
        self.assertEqual(
            transition_result.production_entitlement_check_context[
                "production_entitlement_evidence_reference"
            ],
            "production-entitlement-evidence:store:001:price-band",
        )

    def test_production_entitlement_check_transport_visible_in_handoff_audit(self) -> None:
        orchestrator, feature_review, correlation_id = (
            self._prepare_feature_review_episode()
        )

        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should expose governed production entitlement in orchestrator transport."
            ),
            correlation_id=correlation_id,
            actor_id="production-entitlement-check-test",
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
            payload["production_entitlement_check_status"],
            "production_entitlement_checked",
        )
        self.assertEqual(
            payload["production_entitlement_check_class_id"],
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            payload["production_entitlement_check_context"][
                "production_entitlement_check_outcome"
            ],
            "approved_for_broader_trusted_production_entitlement",
        )
        self.assertEqual(
            payload["production_entitlement_check_context"][
                "production_entitlement_evidence_reference"
            ],
            "production-entitlement-evidence:store:001:price-band",
        )

    def _build_production_entitlement_check(self) -> ProductionEntitlementCheck:
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
            production_entitlement_check_classes_path=(
                self.registry_root / "production_entitlement_check_classes.json"
            ),
            production_entitlement_check_templates_path=(
                self.registry_root / "production_entitlement_check_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = ProductionEntitlementCheckAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ProductionEntitlementCheck(
            release_registry=registry,
            production_entitlement_check_audit_adapter=audit_adapter,
        )

    def _prepare_feature_review_episode(self):
        orchestrator, feature_review, correlation_id = (
            self.helpers._prepare_feature_review_episode()
        )
        orchestrator._state_manager._release_confirmation = self.helpers.release_confirmation
        orchestrator._state_manager._production_entitlement_check = (
            self.production_entitlement_check
        )
        return orchestrator, feature_review, correlation_id

    def _ready_transition_controls(self) -> dict[str, object]:
        return {
            **self.helpers._ready_transition_controls(),
            "production_entitlement_check_class_id": (
                "full_scope_production_promotion_candidate"
            ),
            "production_entitlement_check_context": self._ready_context(),
        }

    def _build_ready_release_confirmation(self):
        return self.helpers.release_confirmation.generate(
            release_confirmation_test_module.ReleaseConfirmationRequest(
                release_watch_discipline=(
                    self.helpers._build_ready_release_watch_discipline()
                ),
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="release_authority",
                release_confirmation_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )

    def _build_conditional_release_confirmation(self):
        return self.helpers.release_confirmation.generate(
            release_confirmation_test_module.ReleaseConfirmationRequest(
                release_watch_discipline=(
                    self.helpers._build_conditional_release_watch_discipline()
                ),
                release_confirmation_class_id="conditional_production_release",
                release_confirmation_author_role="release_authority",
                release_confirmation_context={
                    **self.helpers._ready_context(),
                    "restriction_summary": (
                        "Confirmation remains bounded to the approved local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="production-entitlement-check-test",
            )
        )

    def _ready_context(self) -> dict[str, object]:
        return {
            "production_entitlement_judgment": (
                "production-entitlement-approved:store:001:price-band"
            ),
            "production_entitlement_evidence_reference": (
                "production-entitlement-evidence:store:001:price-band"
            ),
            "production_entitlement_authority_reference": (
                "production-entitlement-authority:store:001:price-band"
            ),
        }

    def _deferred_context(self) -> dict[str, object]:
        return {
            **self._ready_context(),
            "production_entitlement_prerequisite_reference": (
                "production-entitlement-prerequisites:store:001:price-band"
            ),
            "outstanding_production_entitlement_prerequisites": [
                "entitlement-authority-signoff",
                "broader-use-evidence-reconciliation",
            ],
            "follow_up_review_reference": "review:production-entitlement:001",
        }


if __name__ == "__main__":
    unittest.main()