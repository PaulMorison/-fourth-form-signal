from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from data.ingestion.raw_ingestion_pipeline import RawIngestionCommand  # noqa: E402
from decision.policy_learning import (  # noqa: E402
    JsonPolicyLearningEvidenceAdmissionRegistry,
    PolicyLearningEvidenceAdmissionAuditAdapter,
    PolicyLearningEvidenceAdmissionRequest,
    PolicyLearningEvidenceAdmissionService,
)
from decision.post_mortem import PostMortemJudgmentRequest  # noqa: E402
from state.features.feature_registry import FeatureDefinition  # noqa: E402
from tests.unit import test_post_mortem_judgment_layer as post_mortem_test_module  # noqa: E402


class PolicyLearningEvidenceAdmissionLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = post_mortem_test_module.PostMortemJudgmentLayerTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.policy_learning_service = self._build_policy_learning_service()

    def test_direct_ready_admission(self) -> None:
        post_mortem_judgment = self._build_ready_post_mortem_judgment()

        admission = self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=post_mortem_judgment,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=self._ready_admission_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )

        self.assertEqual(
            admission.policy_learning_evidence_admission_status,
            "admitted_ready",
        )
        self.assertEqual(
            admission.policy_learning_evidence_admission_outcome,
            "admitted_for_update_consideration",
        )
        self.assertEqual(
            admission.attribution_readiness,
            "attribution_ready_for_learning",
        )

    def test_blocked_missing_context(self) -> None:
        post_mortem_judgment = self._build_ready_post_mortem_judgment()

        admission = self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=post_mortem_judgment,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context={
                    "candidate_update_direction": "preserve_current_path"
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )

        self.assertEqual(
            admission.policy_learning_evidence_admission_status,
            "blocked_missing_context",
        )
        self.assertIn("learning_scope_reference", admission.missing_evidence_fields)
        self.assertIn("comparability_judgment", admission.missing_evidence_fields)

    def test_blocked_insufficient_evidence(self) -> None:
        post_mortem_judgment = self._build_deferred_post_mortem_judgment()

        admission = self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=post_mortem_judgment,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=self._ready_admission_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )

        self.assertEqual(
            admission.policy_learning_evidence_admission_status,
            "blocked_insufficient_evidence",
        )
        self.assertEqual(
            admission.policy_learning_evidence_admission_outcome,
            "rejected_for_learning_use",
        )
        self.assertEqual(
            admission.evidence_sufficiency,
            "insufficient_for_learning_admission",
        )

    def test_fallback_template_path(self) -> None:
        post_mortem_judgment = self._build_deferred_post_mortem_judgment()

        admission = self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=post_mortem_judgment,
                policy_learning_evidence_class_id=(
                    "deferred_policy_learning_review_candidate"
                ),
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=(
                    self._fallback_admission_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )

        self.assertEqual(
            admission.policy_learning_evidence_admission_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            admission.policy_learning_evidence_template_id,
            "deferred_policy_learning_review_candidate_fallback",
        )
        self.assertEqual(
            admission.policy_learning_evidence_admission_outcome,
            "deferred_pending_more_evidence",
        )

    def test_lineage_preservation(self) -> None:
        post_mortem_judgment = self._build_ready_post_mortem_judgment()

        admission = self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=post_mortem_judgment,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=self._ready_admission_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )

        self.assertEqual(
            admission.lineage["execution_outcome_id"],
            post_mortem_judgment.lineage["execution_outcome_id"],
        )
        self.assertEqual(
            admission.recommendation_id,
            post_mortem_judgment.lineage["recommendation_id"],
        )
        self.assertEqual(
            admission.action_instruction_id,
            post_mortem_judgment.lineage["action_instruction_id"],
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        post_mortem_judgment = self._build_ready_post_mortem_judgment()

        admission = self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=post_mortem_judgment,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context={
                    **self._ready_admission_context(),
                    "model_update_reference": "model:update:2026-04-23",
                    "reopen_context": "reopen:case:001",
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )

        self.assertEqual(
            admission.policy_learning_evidence_admission_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "model_update_reference",
            admission.prohibited_evidence_fields_present,
        )
        self.assertIn(
            "reopen_context",
            admission.prohibited_evidence_fields_present,
        )

    def test_audit_emission(self) -> None:
        ready_post_mortem = self._build_ready_post_mortem_judgment()
        deferred_post_mortem = self._build_deferred_post_mortem_judgment()

        self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=ready_post_mortem,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=self._ready_admission_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )
        self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=ready_post_mortem,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context={
                    "candidate_update_direction": "preserve_current_path"
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )
        self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=deferred_post_mortem,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=self._ready_admission_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )
        self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=deferred_post_mortem,
                policy_learning_evidence_class_id=(
                    "deferred_policy_learning_review_candidate"
                ),
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=(
                    self._fallback_admission_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )
        self.policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=ready_post_mortem,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context={
                    **self._ready_admission_context(),
                    "model_update_reference": "model:update:2026-04-23",
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn(
            "decision.policy_learning.policy_learning_evidence_admission_recorded",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_evidence_admission_blocked",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_evidence_admission_admitted_for_update_consideration",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_evidence_admission_missing_context",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_evidence_admission_rejected_for_learning_use",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_evidence_admission_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_evidence_admission_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_policy_learning_evidence_admission(
        self,
    ) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.helpers.helpers.helpers.feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta.policy_learning",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description=(
                    "Expected revenue delta used to seed policy-learning evidence "
                    "admission tests."
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
                created_at=datetime.now(tz=UTC),
            ),
            correlation_id=str(uuid4()),
            actor_id="policy-learning-test",
        )
        raw_pipeline = self.helpers.helpers.helpers.helpers.helpers._build_raw_pipeline()
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-003",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-003",
                        "candidate_revenue": 1685.0,
                        "baseline_revenue": 1510.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="policy-learning-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-003",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="policy-learning-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="policy-learning-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should emit a governed policy-learning evidence admission "
                "only after legitimate execution outcome capture and post-mortem judgment."
            ),
            correlation_id=correlation_id,
            actor_id="policy-learning-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": (
                    "Assess whether the elevated impact score warrants accountable "
                    "manual review."
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
                "action_path_reference": "action-path:price-adjustment-003",
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
                "policy_output_reference": "policy-output:allowance-003",
                "policy_rationale": (
                    "Recommendation and review lineage justify bounded policy allowance "
                    "while preserving action-boundary discipline."
                ),
                "action_boundary_summary": (
                    "Policy-shaped allowance only; downstream commitment and instruction "
                    "remain separate."
                ),
                "allowance_reference": "allowance:store:001:price-adjustment-window-003",
            },
            portfolio_output_class_id="portfolio_bounded_allocation",
            portfolio_output_context={
                "portfolio_summary": (
                    "Preserve bounded allocation posture for downstream portfolio planning."
                ),
                "portfolio_output_reference": "portfolio-output:allocation-003",
                "portfolio_rationale": (
                    "Policy allowance lineage justifies bounded allocation posture for "
                    "downstream planning."
                ),
                "action_boundary_summary": (
                    "Allocative only; downstream commitment and instruction remain separate."
                ),
                "allocation_reference": "allocation:store:001:price-adjustment-window-003",
                "allocation_weight_reference": "allocation-weight:store:001:0.74",
            },
            action_instruction_class_id="direct_action_instruction",
            action_instruction_context=(
                self.helpers.helpers.helpers.helpers.helpers._action_instruction_context()
            ),
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=(
                self.helpers.helpers.helpers.helpers._direct_execution_request_context()
            ),
            execution_dispatch_class_id="direct_dispatch_boundary",
            execution_dispatch_context=(
                self.helpers.helpers.helpers._direct_execution_dispatch_context()
            ),
            execution_outcome_class_id="favorable_realized_outcome",
            execution_outcome_context=self.helpers.helpers._favorable_outcome_context(),
            post_mortem_judgment_class_id="correct_recommendation_correct_execution",
            post_mortem_judgment_context=self.helpers._ready_post_mortem_context(),
            policy_learning_evidence_class_id="policy_learning_review_candidate",
            policy_learning_evidence_admission_context=self._ready_admission_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(
            payload["policy_learning_evidence_admission_status"],
            "admitted_ready",
        )
        self.assertEqual(
            payload["policy_learning_evidence_class_id"],
            "policy_learning_review_candidate",
        )
        self.assertEqual(
            payload["policy_learning_evidence_admission_context"][
                "policy_learning_evidence_admission_outcome"
            ],
            "admitted_for_update_consideration",
        )
        self.assertEqual(
            payload["policy_learning_evidence_admission_context"][
                "candidate_update_direction"
            ],
            "preserve_current_path",
        )
        self.assertEqual(
            payload["post_mortem_judgment_status"],
            "ready_for_downstream_use",
        )

    def _build_policy_learning_service(self) -> PolicyLearningEvidenceAdmissionService:
        registry = JsonPolicyLearningEvidenceAdmissionRegistry(
            policy_learning_evidence_classes_path=(
                self.registry_root / "policy_learning_evidence_admission_classes.json"
            ),
            policy_learning_evidence_templates_path=(
                self.registry_root / "policy_learning_evidence_admission_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = PolicyLearningEvidenceAdmissionAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return PolicyLearningEvidenceAdmissionService(
            policy_learning_evidence_admission_registry=registry,
            policy_learning_evidence_admission_audit_adapter=audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._post_mortem_judgment_service = (
            self.helpers.post_mortem_service
        )
        orchestrator._state_manager._policy_learning_evidence_admission_service = (
            self.policy_learning_service
        )
        return orchestrator

    def _build_ready_post_mortem_judgment(self):
        return self.helpers.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=self.helpers._build_favorable_execution_outcome(),
                post_mortem_judgment_class_id=(
                    "correct_recommendation_correct_execution"
                ),
                post_mortem_author_role="case_operator",
                post_mortem_context=self.helpers._ready_post_mortem_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )

    def _build_deferred_post_mortem_judgment(self):
        return self.helpers.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=self.helpers._build_deferred_execution_outcome(),
                post_mortem_judgment_class_id=(
                    "insufficient_evidence_for_confident_judgment"
                ),
                post_mortem_author_role="case_operator",
                post_mortem_context=self.helpers._fallback_post_mortem_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-test",
            )
        )

    def _ready_admission_context(self) -> dict[str, object]:
        return {
            "learning_scope_reference": "learning-scope:shared-control:store-001",
            "candidate_update_direction": "preserve_current_path",
            "comparability_judgment": "comparable_case_set_confirmed",
            "commercial_interpretability_summary": (
                "The admitted evidence preserves decision-loop lineage, stable store "
                "scope, and commercially interpretable realized consequence."
            ),
            "proposed_update_scope": "scope:store:001",
            "comparable_case_set_reference": "case-set:store-001:stable-window",
            "memory_object_reference": "decision-memory:store-001:episode-cluster",
        }

    def _fallback_admission_context(self) -> dict[str, object]:
        return {
            "learning_scope_reference": "learning-scope:shared-control:store-001",
            "candidate_update_direction": "defer_adaptation_pending_more_evidence",
            "comparability_judgment": "comparable_case_set_pending_more_cases",
            "commercial_interpretability_summary": (
                "The evidence is structurally interpretable, but the observation horizon "
                "is still immature for update-threshold review."
            ),
            "proposed_update_scope": "scope:store:001",
            "restriction_summary": "defer_learning_until_evidence_matures",
            "comparable_case_set_reference": "case-set:store-001:pending-horizon",
        }


if __name__ == "__main__":
    unittest.main()