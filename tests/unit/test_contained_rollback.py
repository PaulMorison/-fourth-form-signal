from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from runtime.release import (  # noqa: E402
    ContainedRollback,
    ContainedRollbackAuditAdapter,
    ContainedRollbackRequest,
    JsonReleaseRegistry,
    ProductionEntitlementCheckRequest,
)
from tests.unit import test_production_entitlement_check as entitlement_test_module  # noqa: E402


class ContainedRollbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = entitlement_test_module.ProductionEntitlementCheckTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.contained_rollback = self._build_contained_rollback()

    def test_direct_bounded_exposure_preserved(self) -> None:
        production_entitlement_check = self._build_ready_production_entitlement_check()

        contained_rollback = self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=production_entitlement_check,
                contained_rollback_class_id="full_scope_production_promotion_candidate",
                contained_rollback_author_role="release_authority",
                contained_rollback_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )

        self.assertEqual(
            contained_rollback.contained_rollback_status,
            "contained_rollback_bounded",
        )
        self.assertEqual(
            contained_rollback.contained_rollback_outcome,
            "bounded_exposure_preserved",
        )
        self.assertEqual(
            contained_rollback.containment_evidence_reference,
            "containment-evidence:store:001:price-band",
        )

    def test_partial_reversal_bounded(self) -> None:
        production_entitlement_check = (
            self._build_conditional_production_entitlement_check()
        )

        contained_rollback = self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=production_entitlement_check,
                contained_rollback_class_id="conditional_production_release",
                contained_rollback_author_role="release_authority",
                contained_rollback_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )

        self.assertEqual(
            contained_rollback.contained_rollback_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            contained_rollback.contained_rollback_outcome,
            "partial_reversal_bounded",
        )
        self.assertEqual(
            contained_rollback.promotion_scope_restriction_reference,
            "scope:store:001:promo-window",
        )

    def test_deferred_pending_contained_rollback_evidence(self) -> None:
        production_entitlement_check = self._build_ready_production_entitlement_check()

        contained_rollback = self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=production_entitlement_check,
                contained_rollback_class_id="deferred_release_state",
                contained_rollback_author_role="release_authority",
                contained_rollback_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )

        self.assertEqual(
            contained_rollback.contained_rollback_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            contained_rollback.contained_rollback_outcome,
            "deferred_pending_contained_rollback_evidence",
        )
        self.assertIn(
            "lineage-reconstruction-confirmation",
            contained_rollback.outstanding_contained_rollback_prerequisites,
        )

    def test_blocked_missing_context(self) -> None:
        production_entitlement_check = self._build_ready_production_entitlement_check()

        contained_rollback = self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=production_entitlement_check,
                contained_rollback_class_id="full_scope_production_promotion_candidate",
                contained_rollback_author_role="release_authority",
                contained_rollback_context={
                    "contained_rollback_judgment": (
                        "contained-rollback:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )

        self.assertEqual(
            contained_rollback.contained_rollback_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "rollback_execution_reference",
            contained_rollback.missing_contained_rollback_fields,
        )
        self.assertIn(
            "containment_evidence_reference",
            contained_rollback.missing_contained_rollback_fields,
        )

    def test_rejected_for_contained_rollback_use(self) -> None:
        production_entitlement_check = self._build_ready_production_entitlement_check()

        contained_rollback = self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=production_entitlement_check,
                contained_rollback_class_id="full_scope_production_promotion_candidate",
                contained_rollback_author_role="release_authority",
                contained_rollback_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Rollback containment remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )

        self.assertEqual(
            contained_rollback.contained_rollback_status,
            "rejected_for_contained_rollback_use",
        )
        self.assertEqual(
            contained_rollback.contained_rollback_outcome,
            "rejected_for_contained_rollback_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        production_entitlement_check = self._build_ready_production_entitlement_check()

        contained_rollback = self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=production_entitlement_check,
                contained_rollback_class_id="full_scope_production_promotion_candidate",
                contained_rollback_author_role="release_authority",
                contained_rollback_context={
                    **self._ready_context(),
                    "release_closure_reference": (
                        "release-closure:store:001:price-band"
                    ),
                    "monitoring_admission_reference": (
                        "monitoring-admission:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )

        self.assertEqual(
            contained_rollback.contained_rollback_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "release_closure_reference",
            contained_rollback.prohibited_contained_rollback_fields_present,
        )
        self.assertIn(
            "monitoring_admission_reference",
            contained_rollback.prohibited_contained_rollback_fields_present,
        )

    def test_lineage_preservation(self) -> None:
        production_entitlement_check = self._build_ready_production_entitlement_check()

        contained_rollback = self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=production_entitlement_check,
                contained_rollback_class_id="full_scope_production_promotion_candidate",
                contained_rollback_author_role="release_authority",
                contained_rollback_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )

        self.assertEqual(
            contained_rollback.lineage["production_entitlement_check_id"],
            production_entitlement_check.production_entitlement_check_id,
        )
        self.assertEqual(
            contained_rollback.lineage["release_confirmation_id"],
            production_entitlement_check.lineage["release_confirmation_id"],
        )

    def test_audit_emission(self) -> None:
        ready_production_entitlement_check = (
            self._build_ready_production_entitlement_check()
        )
        conditional_production_entitlement_check = (
            self._build_conditional_production_entitlement_check()
        )

        self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=ready_production_entitlement_check,
                contained_rollback_class_id="full_scope_production_promotion_candidate",
                contained_rollback_author_role="release_authority",
                contained_rollback_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )
        self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=conditional_production_entitlement_check,
                contained_rollback_class_id="conditional_production_release",
                contained_rollback_author_role="release_authority",
                contained_rollback_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )
        self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=ready_production_entitlement_check,
                contained_rollback_class_id="deferred_release_state",
                contained_rollback_author_role="release_authority",
                contained_rollback_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )
        self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=ready_production_entitlement_check,
                contained_rollback_class_id="full_scope_production_promotion_candidate",
                contained_rollback_author_role="release_authority",
                contained_rollback_context={
                    "contained_rollback_judgment": (
                        "contained-rollback:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )
        self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=ready_production_entitlement_check,
                contained_rollback_class_id="full_scope_production_promotion_candidate",
                contained_rollback_author_role="release_authority",
                contained_rollback_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Rollback containment remains narrowed to a local production window."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )
        self.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=ready_production_entitlement_check,
                contained_rollback_class_id="full_scope_production_promotion_candidate",
                contained_rollback_author_role="release_authority",
                contained_rollback_context={
                    **self._ready_context(),
                    "release_closure_reference": (
                        "release-closure:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn("runtime.release.contained_rollback_recorded", event_types)
        self.assertIn("runtime.release.contained_rollback_blocked", event_types)
        self.assertIn(
            "runtime.release.contained_rollback_bounded_exposure_preserved",
            event_types,
        )
        self.assertIn(
            "runtime.release.contained_rollback_partial_reversal_bounded",
            event_types,
        )
        self.assertIn(
            "runtime.release.contained_rollback_deferred_pending_contained_rollback_evidence",
            event_types,
        )
        self.assertIn(
            "runtime.release.contained_rollback_missing_context",
            event_types,
        )
        self.assertIn(
            "runtime.release.contained_rollback_rejected_for_contained_rollback_use",
            event_types,
        )
        self.assertIn(
            "runtime.release.contained_rollback_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "runtime.release.contained_rollback_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_contained_rollback(self) -> None:
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
            actor_id="contained-rollback-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": (
                    "Assess whether the elevated impact score warrants accountable manual review."
                )
            },
            reason=(
                "Assessment should emit governed contained rollback only after production entitlement exists."
            ),
            **self._ready_transition_controls(),
        )

        self.assertEqual(
            transition_result.contained_rollback_status,
            "contained_rollback_bounded",
        )
        self.assertEqual(
            transition_result.contained_rollback_class_id,
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            transition_result.contained_rollback_context[
                "contained_rollback_outcome"
            ],
            "bounded_exposure_preserved",
        )
        self.assertEqual(
            transition_result.contained_rollback_context[
                "containment_evidence_reference"
            ],
            "containment-evidence:store:001:price-band",
        )

    def test_contained_rollback_transport_visible_in_handoff_audit(self) -> None:
        orchestrator, feature_review, correlation_id = (
            self._prepare_feature_review_episode()
        )

        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should expose governed contained rollback in orchestrator transport."
            ),
            correlation_id=correlation_id,
            actor_id="contained-rollback-test",
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
            payload["contained_rollback_status"],
            "contained_rollback_bounded",
        )
        self.assertEqual(
            payload["contained_rollback_class_id"],
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            payload["contained_rollback_context"]["contained_rollback_outcome"],
            "bounded_exposure_preserved",
        )
        self.assertEqual(
            payload["contained_rollback_context"]["containment_evidence_reference"],
            "containment-evidence:store:001:price-band",
        )

    def _build_contained_rollback(self) -> ContainedRollback:
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
            contained_rollback_classes_path=(
                self.registry_root / "contained_rollback_classes.json"
            ),
            contained_rollback_templates_path=(
                self.registry_root / "contained_rollback_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = ContainedRollbackAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ContainedRollback(
            release_registry=registry,
            contained_rollback_audit_adapter=audit_adapter,
        )

    def _build_ready_production_entitlement_check(self):
        return self.helpers.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=self.helpers._build_ready_release_confirmation(),
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )

    def _build_conditional_production_entitlement_check(self):
        return self.helpers.production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=(
                    self.helpers._build_conditional_release_confirmation()
                ),
                production_entitlement_check_class_id="conditional_production_release",
                production_entitlement_check_author_role="release_authority",
                production_entitlement_check_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="contained-rollback-test",
            )
        )

    def _prepare_feature_review_episode(self):
        orchestrator, feature_review, correlation_id = (
            self.helpers._prepare_feature_review_episode()
        )
        orchestrator._state_manager._contained_rollback = self.contained_rollback
        return orchestrator, feature_review, correlation_id

    def _ready_transition_controls(self) -> dict[str, object]:
        return {
            **self.helpers._ready_transition_controls(),
            "contained_rollback_class_id": (
                "full_scope_production_promotion_candidate"
            ),
            "contained_rollback_context": self._ready_context(),
        }

    def _ready_context(self) -> dict[str, object]:
        return {
            "contained_rollback_judgment": (
                "contained-rollback:store:001:price-band"
            ),
            "rollback_execution_reference": (
                "rollback-execution:store:001:price-band"
            ),
            "containment_evidence_reference": (
                "containment-evidence:store:001:price-band"
            ),
            "bounded_exposure_reference": (
                "bounded-exposure:store:001:price-band"
            ),
            "downstream_effects_boundary_reference": (
                "downstream-effects-boundary:store:001:price-band"
            ),
            "release_lineage_reconstruction_reference": (
                "release-lineage:store:001:price-band:reconstructible"
            ),
            "contained_rollback_authority_reference": (
                "contained-rollback-authority:store:001:price-band"
            ),
        }

    def _deferred_context(self) -> dict[str, object]:
        return {
            **self._ready_context(),
            "contained_rollback_prerequisite_reference": (
                "contained-rollback-prerequisites:store:001:price-band"
            ),
            "outstanding_contained_rollback_prerequisites": [
                "lineage-reconstruction-confirmation",
                "downstream-effects-boundary-review",
            ],
            "follow_up_review_reference": "review:contained-rollback:001",
        }


if __name__ == "__main__":
    unittest.main()
