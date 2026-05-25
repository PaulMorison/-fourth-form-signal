from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from runtime.release import (  # noqa: E402
    ContainedRollbackRequest,
    JsonReleaseRegistry,
    ReleaseAuditTrace,
    ReleaseAuditTraceAuditAdapter,
    ReleaseAuditTraceRequest,
)
from tests.unit import test_contained_rollback as contained_rollback_test_module  # noqa: E402


class ReleaseAuditTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = contained_rollback_test_module.ContainedRollbackTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.release_audit_trace = self._build_release_audit_trace()

    def test_direct_release_control_lineage_preserved(self) -> None:
        contained_rollback = self._build_ready_contained_rollback()

        release_audit_trace = self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

        self.assertEqual(
            release_audit_trace.release_audit_trace_status,
            "release_audit_trace_recorded",
        )
        self.assertEqual(
            release_audit_trace.release_audit_trace_outcome,
            "release_control_lineage_preserved",
        )
        self.assertEqual(
            release_audit_trace.release_control_lineage_reference,
            "release-control-lineage:store:001:price-band",
        )

    def test_invalid_exposure_visibility_preserved(self) -> None:
        contained_rollback = self._build_conditional_contained_rollback()

        release_audit_trace = self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=contained_rollback,
                release_audit_trace_class_id="conditional_production_release",
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

        self.assertEqual(
            release_audit_trace.release_audit_trace_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            release_audit_trace.release_audit_trace_outcome,
            "invalid_exposure_visibility_preserved",
        )
        self.assertEqual(
            release_audit_trace.promotion_scope_restriction_reference,
            "scope:store:001:promo-window",
        )

    def test_deferred_pending_release_audit_trace_evidence(self) -> None:
        contained_rollback = self._build_deferred_contained_rollback()

        release_audit_trace = self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=contained_rollback,
                release_audit_trace_class_id="deferred_release_state",
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

        self.assertEqual(
            release_audit_trace.release_audit_trace_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            release_audit_trace.release_audit_trace_outcome,
            "deferred_pending_release_audit_trace_evidence",
        )
        self.assertIn(
            "later-final-disposition-reference",
            release_audit_trace.outstanding_release_audit_trace_prerequisites,
        )

    def test_blocked_missing_context(self) -> None:
        contained_rollback = self._build_ready_contained_rollback()

        release_audit_trace = self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context={
                    "release_audit_trace_judgment": (
                        "release-audit-trace:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

        self.assertEqual(
            release_audit_trace.release_audit_trace_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "release_control_lineage_reference",
            release_audit_trace.missing_release_audit_trace_fields,
        )
        self.assertIn(
            "invalid_exposure_visibility_reference",
            release_audit_trace.missing_release_audit_trace_fields,
        )

    def test_rejected_for_release_audit_trace_use(self) -> None:
        contained_rollback = self._build_ready_contained_rollback()

        release_audit_trace = self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Trace remains narrowed to a bounded conditional production exposure."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

        self.assertEqual(
            release_audit_trace.release_audit_trace_status,
            "rejected_for_release_audit_trace_use",
        )
        self.assertEqual(
            release_audit_trace.release_audit_trace_outcome,
            "rejected_for_release_audit_trace_use",
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        contained_rollback = self._build_ready_contained_rollback()

        release_audit_trace = self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context={
                    **self._ready_context(),
                    "runtime_verification_reference": (
                        "runtime-verification:store:001:price-band"
                    ),
                    "monitoring_admission_reference": (
                        "monitoring-admission:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

        self.assertEqual(
            release_audit_trace.release_audit_trace_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "runtime_verification_reference",
            release_audit_trace.prohibited_release_audit_trace_fields_present,
        )
        self.assertIn(
            "monitoring_admission_reference",
            release_audit_trace.prohibited_release_audit_trace_fields_present,
        )

    def test_lineage_preservation(self) -> None:
        contained_rollback = self._build_ready_contained_rollback()

        release_audit_trace = self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

        self.assertEqual(
            release_audit_trace.lineage["contained_rollback_id"],
            contained_rollback.contained_rollback_id,
        )
        self.assertEqual(
            release_audit_trace.lineage["production_entitlement_check_id"],
            contained_rollback.lineage["production_entitlement_check_id"],
        )

    def test_audit_emission(self) -> None:
        ready_contained_rollback = self._build_ready_contained_rollback()
        conditional_contained_rollback = self._build_conditional_contained_rollback()
        deferred_contained_rollback = self._build_deferred_contained_rollback()

        self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=ready_contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )
        self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=conditional_contained_rollback,
                release_audit_trace_class_id="conditional_production_release",
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context=self._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )
        self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=deferred_contained_rollback,
                release_audit_trace_class_id="deferred_release_state",
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context=self._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )
        self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=ready_contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context={
                    "release_audit_trace_judgment": (
                        "release-audit-trace:store:001:price-band"
                    )
                },
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )
        self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=ready_contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context={
                    **self._ready_context(),
                    "restriction_summary": (
                        "Trace remains narrowed to a bounded conditional production exposure."
                    ),
                    "promotion_scope_restriction_reference": (
                        "scope:store:001:promo-window"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )
        self.release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=ready_contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="release_authority",
                release_audit_trace_context={
                    **self._ready_context(),
                    "runtime_verification_reference": (
                        "runtime-verification:store:001:price-band"
                    ),
                },
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn("runtime.release.release_audit_trace_recorded", event_types)
        self.assertIn("runtime.release.release_audit_trace_blocked", event_types)
        self.assertIn(
            "runtime.release.release_audit_trace_release_control_lineage_preserved",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_audit_trace_invalid_release_state_visible",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_audit_trace_invalid_exposure_visible",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_audit_trace_no_silent_promotion_preserved",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_audit_trace_deferred_pending_release_audit_trace_evidence",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_audit_trace_missing_context",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_audit_trace_rejected_for_release_audit_trace_use",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_audit_trace_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "runtime.release.release_audit_trace_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_release_audit_trace(self) -> None:
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
            actor_id="release-audit-trace-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": (
                    "Assess whether the elevated impact score warrants accountable manual review."
                )
            },
            reason=(
                "Assessment should emit governed release audit trace only after contained rollback exists."
            ),
            **self._ready_transition_controls(),
        )

        self.assertEqual(
            transition_result.release_audit_trace_status,
            "release_audit_trace_recorded",
        )
        self.assertEqual(
            transition_result.release_audit_trace_class_id,
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            transition_result.release_audit_trace_context[
                "release_audit_trace_outcome"
            ],
            "release_control_lineage_preserved",
        )
        self.assertEqual(
            transition_result.release_audit_trace_context[
                "release_control_lineage_reference"
            ],
            "release-control-lineage:store:001:price-band",
        )

    def test_release_audit_trace_transport_visible_in_handoff_audit(self) -> None:
        orchestrator, feature_review, correlation_id = (
            self._prepare_feature_review_episode()
        )

        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should expose governed release audit trace in orchestrator transport."
            ),
            correlation_id=correlation_id,
            actor_id="release-audit-trace-test",
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
            payload["release_audit_trace_status"],
            "release_audit_trace_recorded",
        )
        self.assertEqual(
            payload["release_audit_trace_class_id"],
            "full_scope_production_promotion_candidate",
        )
        self.assertEqual(
            payload["release_audit_trace_context"]["release_audit_trace_outcome"],
            "release_control_lineage_preserved",
        )
        self.assertEqual(
            payload["release_audit_trace_context"][
                "release_control_lineage_reference"
            ],
            "release-control-lineage:store:001:price-band",
        )

    def _build_release_audit_trace(self) -> ReleaseAuditTrace:
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
            release_audit_trace_classes_path=(
                self.registry_root / "release_audit_trace_classes.json"
            ),
            release_audit_trace_templates_path=(
                self.registry_root / "release_audit_trace_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = ReleaseAuditTraceAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ReleaseAuditTrace(
            release_registry=registry,
            release_audit_trace_audit_adapter=audit_adapter,
        )

    def _build_ready_contained_rollback(self):
        return self.helpers.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=(
                    self.helpers._build_ready_production_entitlement_check()
                ),
                contained_rollback_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                contained_rollback_author_role="release_authority",
                contained_rollback_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

    def _build_conditional_contained_rollback(self):
        return self.helpers.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=(
                    self.helpers._build_conditional_production_entitlement_check()
                ),
                contained_rollback_class_id="conditional_production_release",
                contained_rollback_author_role="release_authority",
                contained_rollback_context=self.helpers._ready_context(),
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

    def _build_deferred_contained_rollback(self):
        return self.helpers.contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=(
                    self.helpers._build_ready_production_entitlement_check()
                ),
                contained_rollback_class_id="deferred_release_state",
                contained_rollback_author_role="release_authority",
                contained_rollback_context=self.helpers._deferred_context(),
                correlation_id=str(uuid4()),
                actor_id="release-audit-trace-test",
            )
        )

    def _prepare_feature_review_episode(self):
        orchestrator, feature_review, correlation_id = (
            self.helpers._prepare_feature_review_episode()
        )
        orchestrator._state_manager._contained_rollback = self.helpers.contained_rollback
        orchestrator._state_manager._release_audit_trace = self.release_audit_trace
        return orchestrator, feature_review, correlation_id

    def _ready_transition_controls(self) -> dict[str, object]:
        return {
            **self.helpers._ready_transition_controls(),
            "release_audit_trace_class_id": (
                "full_scope_production_promotion_candidate"
            ),
            "release_audit_trace_context": self._ready_context(),
        }

    def _ready_context(self) -> dict[str, object]:
        return {
            "release_audit_trace_judgment": (
                "release-audit-trace:store:001:price-band"
            ),
            "release_control_lineage_reference": (
                "release-control-lineage:store:001:price-band"
            ),
            "invalid_release_state_visibility_reference": (
                "invalid-release-state-visibility:store:001:price-band"
            ),
            "invalid_exposure_visibility_reference": (
                "invalid-exposure-visibility:store:001:price-band"
            ),
            "no_silent_promotion_preservation_reference": (
                "no-silent-promotion-preservation:store:001:price-band"
            ),
            "release_audit_trace_authority_reference": (
                "release-audit-trace-authority:store:001:price-band"
            ),
        }

    def _deferred_context(self) -> dict[str, object]:
        return {
            **self._ready_context(),
            "release_audit_trace_prerequisite_reference": (
                "release-audit-trace-prerequisites:store:001:price-band"
            ),
            "outstanding_release_audit_trace_prerequisites": [
                "later-final-disposition-reference",
                "invalid-release-state-visibility-confirmation",
            ],
            "later_final_disposition_reference": (
                "final-disposition:store:001:price-band"
            ),
            "follow_up_review_reference": "review:release-audit-trace:001",
        }


if __name__ == "__main__":
    unittest.main()