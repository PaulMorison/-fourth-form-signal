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
    JsonPolicyLearningUpdateThresholdRegistry,
    PolicyLearningUpdateThresholdAuditAdapter,
    PolicyLearningUpdateThresholdRequest,
    PolicyLearningUpdateThresholdService,
)
from decision.post_mortem import PostMortemJudgmentRequest  # noqa: E402
from state.features.feature_registry import FeatureDefinition  # noqa: E402
from tests.unit import test_policy_learning_evidence_admission_layer as evidence_test_module  # noqa: E402


class PolicyLearningUpdateThresholdLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = evidence_test_module.PolicyLearningEvidenceAdmissionLayerTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.policy_learning_update_threshold_service = (
            self._build_policy_learning_update_threshold_service()
        )

    def test_direct_accepted_update_threshold(self) -> None:
        evidence_admission = self._build_ready_evidence_admission()

        threshold = self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=evidence_admission,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=self._accepted_threshold_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

        self.assertEqual(
            threshold.policy_learning_update_threshold_status,
            "threshold_met",
        )
        self.assertEqual(
            threshold.policy_learning_update_decision_outcome,
            "accepted",
        )
        self.assertEqual(
            threshold.evidence_sufficiency,
            "sufficient_for_proposed_update",
        )

    def test_blocked_missing_context(self) -> None:
        evidence_admission = self._build_ready_evidence_admission()

        threshold = self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=evidence_admission,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context={
                    "policy_behavior_change": "narrow_price_response_band"
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

        self.assertEqual(
            threshold.policy_learning_update_threshold_status,
            "blocked_missing_context",
        )
        self.assertIn(
            "update_severity",
            threshold.missing_update_threshold_fields,
        )
        self.assertIn(
            "evidence_completeness",
            threshold.missing_update_threshold_fields,
        )

    def test_blocked_below_threshold(self) -> None:
        evidence_admission = self._build_ready_evidence_admission()

        threshold = self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=evidence_admission,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=self._below_threshold_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

        self.assertEqual(
            threshold.policy_learning_update_threshold_status,
            "blocked_below_threshold",
        )
        self.assertEqual(
            threshold.policy_learning_update_decision_outcome,
            "rejected",
        )
        self.assertEqual(
            threshold.weak_evidence_check,
            "weak_evidence_check_failed",
        )

    def test_narrowed_scope_path(self) -> None:
        evidence_admission = self._build_restricted_evidence_admission()

        threshold = self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=evidence_admission,
                policy_learning_update_threshold_class_id=(
                    "narrowed_policy_update_candidate"
                ),
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=self._narrowed_threshold_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

        self.assertEqual(
            threshold.policy_learning_update_threshold_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            threshold.policy_learning_update_decision_outcome,
            "accepted_with_narrowed_scope",
        )
        self.assertEqual(
            threshold.narrowed_scope_reference,
            "scope:store:001:promo-window",
        )

    def test_deferred_monitoring_path(self) -> None:
        evidence_admission = self._build_deferred_evidence_admission()

        threshold = self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=evidence_admission,
                policy_learning_update_threshold_class_id="deferred_policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=self._deferred_threshold_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

        self.assertEqual(
            threshold.policy_learning_update_threshold_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            threshold.policy_learning_update_decision_outcome,
            "deferred_for_continued_monitoring",
        )
        self.assertEqual(
            threshold.monitoring_recommendation,
            "continue_monitoring_and_accumulate_comparable_cases",
        )

    def test_lineage_preservation(self) -> None:
        evidence_admission = self._build_ready_evidence_admission()

        threshold = self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=evidence_admission,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=self._accepted_threshold_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

        self.assertEqual(
            threshold.lineage["policy_learning_evidence_admission_id"],
            evidence_admission.policy_learning_evidence_admission_id,
        )
        self.assertEqual(
            threshold.lineage["recommendation_id"],
            evidence_admission.lineage["recommendation_id"],
        )
        self.assertEqual(
            threshold.execution_outcome_id,
            evidence_admission.execution_outcome_id,
        )

    def test_prohibited_overlap_fields_are_blocked(self) -> None:
        evidence_admission = self._build_ready_evidence_admission()

        threshold = self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=evidence_admission,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context={
                    **self._accepted_threshold_context(),
                    "policy_mutation_payload": "mutate-policy:price-floor",
                    "model_retraining_reference": "model-train:2026-04-23",
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

        self.assertEqual(
            threshold.policy_learning_update_threshold_status,
            "prohibited_overlap_blocked",
        )
        self.assertIn(
            "policy_mutation_payload",
            threshold.prohibited_update_threshold_fields_present,
        )
        self.assertIn(
            "model_retraining_reference",
            threshold.prohibited_update_threshold_fields_present,
        )

    def test_audit_emission(self) -> None:
        ready_evidence_admission = self._build_ready_evidence_admission()
        restricted_evidence_admission = self._build_restricted_evidence_admission()
        deferred_evidence_admission = self._build_deferred_evidence_admission()

        self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=ready_evidence_admission,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=self._accepted_threshold_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )
        self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=ready_evidence_admission,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context={
                    "policy_behavior_change": "narrow_price_response_band"
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )
        self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=ready_evidence_admission,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=self._below_threshold_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )
        self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=restricted_evidence_admission,
                policy_learning_update_threshold_class_id=(
                    "narrowed_policy_update_candidate"
                ),
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=self._narrowed_threshold_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )
        self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=deferred_evidence_admission,
                policy_learning_update_threshold_class_id="deferred_policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=self._deferred_threshold_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )
        self.policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=ready_evidence_admission,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context={
                    **self._accepted_threshold_context(),
                    "policy_mutation_payload": "mutate-policy:price-floor"
                },
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn(
            "decision.policy_learning.policy_learning_update_threshold_recorded",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_threshold_blocked",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_threshold_accepted",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_threshold_accepted_with_narrowed_scope",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_threshold_deferred_for_continued_monitoring",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_threshold_missing_context",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_threshold_rejected",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_threshold_fallback_template_applied",
            event_types,
        )
        self.assertIn(
            "decision.policy_learning.policy_learning_update_threshold_prohibited_overlap_blocked",
            event_types,
        )

    def test_integration_with_lifecycle_through_policy_learning_update_threshold(
        self,
    ) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.helpers.helpers.helpers.helpers.feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta.policy_learning_threshold",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description=(
                    "Expected revenue delta used to seed policy-learning update-threshold tests."
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
            actor_id="policy-learning-threshold-test",
        )
        raw_pipeline = (
            self.helpers.helpers.helpers.helpers.helpers.helpers._build_raw_pipeline()
        )
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-004",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-004",
                        "candidate_revenue": 1710.0,
                        "baseline_revenue": 1505.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="policy-learning-threshold-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-004",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="policy-learning-threshold-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="policy-learning-threshold-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason=(
                "Assessment should emit governed policy-learning update-threshold review only after admitted evidence exists."
            ),
            correlation_id=correlation_id,
            actor_id="policy-learning-threshold-test",
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
                "action_path_reference": "action-path:price-adjustment-004",
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
                "policy_output_reference": "policy-output:allowance-004",
                "policy_rationale": (
                    "Recommendation and review lineage justify bounded policy allowance while preserving action-boundary discipline."
                ),
                "action_boundary_summary": (
                    "Policy-shaped allowance only; downstream commitment and instruction remain separate."
                ),
                "allowance_reference": "allowance:store:001:price-adjustment-window-004",
            },
            portfolio_output_class_id="portfolio_bounded_allocation",
            portfolio_output_context={
                "portfolio_summary": (
                    "Preserve bounded allocation posture for downstream portfolio planning."
                ),
                "portfolio_output_reference": "portfolio-output:allocation-004",
                "portfolio_rationale": (
                    "Policy allowance lineage justifies bounded allocation posture for downstream planning."
                ),
                "action_boundary_summary": (
                    "Allocative only; downstream commitment and instruction remain separate."
                ),
                "allocation_reference": "allocation:store:001:price-adjustment-window-004",
                "allocation_weight_reference": "allocation-weight:store:001:0.75",
            },
            action_instruction_class_id="direct_action_instruction",
            action_instruction_context=(
                self.helpers.helpers.helpers.helpers.helpers.helpers._action_instruction_context()
            ),
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=(
                self.helpers.helpers.helpers.helpers.helpers._direct_execution_request_context()
            ),
            execution_dispatch_class_id="direct_dispatch_boundary",
            execution_dispatch_context=(
                self.helpers.helpers.helpers.helpers._direct_execution_dispatch_context()
            ),
            execution_outcome_class_id="favorable_realized_outcome",
            execution_outcome_context=(
                self.helpers.helpers.helpers._favorable_outcome_context()
            ),
            post_mortem_judgment_class_id="correct_recommendation_correct_execution",
            post_mortem_judgment_context=(
                self.helpers.helpers._ready_post_mortem_context()
            ),
            policy_learning_evidence_class_id="policy_learning_review_candidate",
            policy_learning_evidence_admission_context=(
                self.helpers._ready_admission_context()
            ),
            policy_learning_update_threshold_class_id="policy_update_candidate",
            policy_learning_update_threshold_context=self._accepted_threshold_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(
            payload["policy_learning_update_threshold_status"],
            "threshold_met",
        )
        self.assertEqual(
            payload["policy_learning_update_threshold_class_id"],
            "policy_update_candidate",
        )
        self.assertEqual(
            payload["policy_learning_update_threshold_context"][
                "policy_learning_update_decision_outcome"
            ],
            "accepted",
        )
        self.assertEqual(
            payload["policy_learning_update_threshold_context"][
                "evidence_sufficiency"
            ],
            "sufficient_for_proposed_update",
        )

    def _build_policy_learning_update_threshold_service(
        self,
    ) -> PolicyLearningUpdateThresholdService:
        registry = JsonPolicyLearningUpdateThresholdRegistry(
            policy_learning_update_threshold_classes_path=(
                self.registry_root / "policy_learning_update_threshold_classes.json"
            ),
            policy_learning_update_threshold_templates_path=(
                self.registry_root / "policy_learning_update_threshold_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = PolicyLearningUpdateThresholdAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return PolicyLearningUpdateThresholdService(
            policy_learning_update_threshold_registry=registry,
            policy_learning_update_threshold_audit_adapter=audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._policy_learning_update_threshold_service = (
            self.policy_learning_update_threshold_service
        )
        return orchestrator

    def _build_ready_evidence_admission(self):
        return self.helpers.policy_learning_service.generate(
            evidence_test_module.PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=self.helpers._build_ready_post_mortem_judgment(),
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=(
                    self.helpers._ready_admission_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

    def _build_restricted_evidence_admission(self):
        post_mortem_judgment = self.helpers.helpers.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=self.helpers.helpers._build_negative_execution_outcome(),
                post_mortem_judgment_class_id="correct_recommendation_weak_execution",
                post_mortem_author_role="case_operator",
                post_mortem_context=self.helpers.helpers._ready_post_mortem_context(),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )
        return self.helpers.policy_learning_service.generate(
            evidence_test_module.PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=post_mortem_judgment,
                policy_learning_evidence_class_id=(
                    "restricted_policy_learning_review_candidate"
                ),
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=(
                    self.helpers._ready_admission_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

    def _build_deferred_evidence_admission(self):
        return self.helpers.policy_learning_service.generate(
            evidence_test_module.PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=(
                    self.helpers._build_deferred_post_mortem_judgment()
                ),
                policy_learning_evidence_class_id=(
                    "deferred_policy_learning_review_candidate"
                ),
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=(
                    self.helpers._fallback_admission_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="policy-learning-threshold-test",
            )
        )

    def _accepted_threshold_context(self) -> dict[str, object]:
        return {
            "policy_behavior_change": "narrow_price_response_band",
            "update_severity": "local_policy_adjustment",
            "update_scope": "scope:store:001",
            "evidence_base_summary": (
                "Repeated comparable cases, strong attribution, and bounded local scope support a governed local adjustment."
            ),
            "evidence_completeness": "strong",
            "evidence_consistency": "strong",
            "evidence_comparability": "strong",
            "attribution_quality": "strong",
            "scope_legitimacy": "strong",
            "transfer_validity": "strong",
            "magnitude_alignment": "strong",
            "repetition_posture": "repeated_comparable_cases",
            "commercial_significance": "high",
            "governance_sensitivity": "moderate"
        }

    def _below_threshold_context(self) -> dict[str, object]:
        return {
            **self._accepted_threshold_context(),
            "update_severity": "broad_policy_change",
            "evidence_consistency": "moderate",
            "transfer_validity": "moderate",
            "magnitude_alignment": "moderate",
            "repetition_posture": "single_case_only",
            "unresolved_competing_explanations": [
                "execution_noise_not_fully_excluded"
            ]
        }

    def _narrowed_threshold_context(self) -> dict[str, object]:
        return {
            **self._accepted_threshold_context(),
            "update_scope": "scope:store:001:promo-window",
            "evidence_consistency": "moderate",
            "transfer_validity": "moderate",
            "magnitude_alignment": "moderate",
            "repetition_posture": "limited_repetition",
            "local_contradiction_posture": "local_scope_contradiction_requires_narrowing",
            "narrowed_scope_reference": "scope:store:001:promo-window"
        }

    def _deferred_threshold_context(self) -> dict[str, object]:
        return {
            **self._accepted_threshold_context(),
            "update_severity": "broad_policy_change",
            "update_scope": "scope:network:banner-a",
            "evidence_base_summary": (
                "The evidence is meaningful enough to preserve, but the observation horizon and case repetition remain too weak for present change."
            ),
            "evidence_completeness": "moderate",
            "evidence_consistency": "weak",
            "evidence_comparability": "moderate",
            "attribution_quality": "weak",
            "scope_legitimacy": "moderate",
            "transfer_validity": "weak",
            "magnitude_alignment": "weak",
            "repetition_posture": "single_case_only",
            "commercial_significance": "moderate",
            "governance_sensitivity": "high",
            "monitoring_recommendation": "continue_monitoring_and_accumulate_comparable_cases",
            "unresolved_competing_explanations": [
                "regime_shift_not_yet_excluded",
                "execution_variance_not_fully_separated"
            ]
        }


if __name__ == "__main__":
    unittest.main()
