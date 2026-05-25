from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from data.ingestion.raw_ingestion_pipeline import RawIngestionCommand  # noqa: E402
from decision.post_mortem import (  # noqa: E402
    JsonPostMortemJudgmentRegistry,
    PostMortemJudgmentAuditAdapter,
    PostMortemJudgmentRequest,
    PostMortemJudgmentService,
)
from state.features.feature_registry import FeatureDefinition  # noqa: E402
from tests.unit import test_execution_outcome_layer as execution_outcome_test_module  # noqa: E402


class PostMortemJudgmentLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = execution_outcome_test_module.ExecutionOutcomeLayerTests(
            methodName="runTest"
        )
        self.helpers.setUp()
        self.registry_root = self.helpers.registry_root
        self.contract_validator = self.helpers.contract_validator
        self.audit_store = self.helpers.audit_store
        self.post_mortem_service = self._build_post_mortem_service()

    def test_successful_post_mortem_judgment_from_legitimate_outcome(self) -> None:
        execution_outcome = self._build_favorable_execution_outcome()

        judgment = self.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=execution_outcome,
                post_mortem_judgment_class_id=(
                    "correct_recommendation_correct_execution"
                ),
                post_mortem_author_role="case_operator",
                post_mortem_context=self._ready_post_mortem_context(),
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )

        self.assertEqual(judgment.post_mortem_status, "ready_for_downstream_use")
        self.assertEqual(
            judgment.primary_attribution_category,
            "correct_recommendation_correct_execution",
        )
        self.assertEqual(
            judgment.comparison_posture,
            "post_mortem_ready_expected_vs_realized",
        )

    def test_blocked_post_mortem_due_to_missing_required_context(self) -> None:
        execution_outcome = self._build_negative_execution_outcome()

        judgment = self.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=execution_outcome,
                post_mortem_judgment_class_id="correct_recommendation_weak_execution",
                post_mortem_author_role="case_operator",
                post_mortem_context={
                    "evidence_quality": "mixed_evidence_requires_caution",
                    "confidence_posture": "cautious_for_review_only",
                },
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )

        self.assertEqual(judgment.post_mortem_status, "blocked")
        self.assertIn("rationale_snapshot", judgment.missing_post_mortem_fields)
        self.assertIn("learning_direction", judgment.missing_post_mortem_fields)

    def test_fallback_template_usage_for_immature_outcome(self) -> None:
        execution_outcome = self._build_deferred_execution_outcome()

        judgment = self.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=execution_outcome,
                post_mortem_judgment_class_id=(
                    "insufficient_evidence_for_confident_judgment"
                ),
                post_mortem_author_role="case_operator",
                post_mortem_context=self._fallback_post_mortem_context(),
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )

        self.assertEqual(judgment.post_mortem_status, "fallback_template_applied")
        self.assertEqual(
            judgment.post_mortem_judgment_template_id,
            "insufficient_evidence_for_confident_judgment_fallback",
        )
        self.assertEqual(
            judgment.evidence_quality,
            "immature_observation_horizon",
        )

    def test_lineage_and_upstream_references_are_preserved(self) -> None:
        execution_outcome = self._build_favorable_execution_outcome()

        judgment = self.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=execution_outcome,
                post_mortem_judgment_class_id=(
                    "correct_recommendation_correct_execution"
                ),
                post_mortem_author_role="case_operator",
                post_mortem_context=self._ready_post_mortem_context(),
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )

        self.assertEqual(
            judgment.lineage["execution_outcome_id"],
            execution_outcome.execution_outcome_id,
        )
        self.assertEqual(
            judgment.recommendation_id,
            execution_outcome.lineage["recommendation_id"],
        )
        self.assertEqual(
            judgment.required_post_mortem_snapshot["outcome_summary"],
            execution_outcome.required_execution_outcome_snapshot["outcome_summary"],
        )

    def test_prohibited_reopen_and_learning_fields_are_blocked(self) -> None:
        execution_outcome = self._build_favorable_execution_outcome()

        judgment = self.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=execution_outcome,
                post_mortem_judgment_class_id=(
                    "correct_recommendation_correct_execution"
                ),
                post_mortem_author_role="case_operator",
                post_mortem_context={
                    **self._ready_post_mortem_context(),
                    "policy_learning_admission": "admit_to_policy_learning",
                    "reopen_context": "reopen:case:001",
                },
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )

        self.assertEqual(judgment.post_mortem_status, "blocked")
        self.assertIn(
            "policy_learning_admission",
            judgment.prohibited_judgment_fields_present,
        )
        self.assertIn("reopen_context", judgment.prohibited_judgment_fields_present)

    def test_audit_emission_for_post_mortem_outcomes(self) -> None:
        favorable_execution_outcome = self._build_favorable_execution_outcome()
        negative_execution_outcome = self._build_negative_execution_outcome()
        deferred_execution_outcome = self._build_deferred_execution_outcome()

        self.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=favorable_execution_outcome,
                post_mortem_judgment_class_id=(
                    "correct_recommendation_correct_execution"
                ),
                post_mortem_author_role="case_operator",
                post_mortem_context=self._ready_post_mortem_context(),
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )
        self.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=negative_execution_outcome,
                post_mortem_judgment_class_id="correct_recommendation_weak_execution",
                post_mortem_author_role="case_operator",
                post_mortem_context={
                    "evidence_quality": "mixed_evidence_requires_caution",
                    "confidence_posture": "cautious_for_review_only",
                },
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )
        self.post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=deferred_execution_outcome,
                post_mortem_judgment_class_id=(
                    "insufficient_evidence_for_confident_judgment"
                ),
                post_mortem_author_role="case_operator",
                post_mortem_context=self._fallback_post_mortem_context(),
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )

        event_types = {event.event_type for event in self.audit_store.list_events()}
        self.assertIn(
            "decision.post_mortem.post_mortem_judgment_recorded",
            event_types,
        )
        self.assertIn(
            "decision.post_mortem.post_mortem_judgment_blocked",
            event_types,
        )
        self.assertIn(
            "decision.post_mortem.post_mortem_judgment_ready_for_downstream_use",
            event_types,
        )
        self.assertIn(
            "decision.post_mortem.post_mortem_judgment_missing_context",
            event_types,
        )
        self.assertIn(
            "decision.post_mortem.post_mortem_judgment_fallback_template_applied",
            event_types,
        )

    def test_integration_with_lifecycle_through_post_mortem(self) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.helpers.helpers.feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta.post_mortem",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description="Expected revenue delta used to seed post-mortem tests.",
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
            actor_id="post-mortem-test",
        )
        raw_pipeline = self.helpers.helpers.helpers.helpers._build_raw_pipeline()
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-002",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-002",
                        "candidate_revenue": 1640.0,
                        "baseline_revenue": 1520.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="post-mortem-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-002",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="post-mortem-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="post-mortem-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason="Assessment should emit a governed post-mortem judgment only after legitimate execution outcome capture.",
            correlation_id=correlation_id,
            actor_id="post-mortem-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": "Assess whether the elevated impact score warrants accountable manual review."
            },
            review_resolution_class_id="resolved_with_action",
            review_resolution_context={
                "review_summary": "The reviewer confirmed downstream action preparation is warranted.",
                "resolution_rationale": "The required review threshold and packet lineage support action routing.",
            },
            recommendation_class_id="recommend_act_now",
            recommendation_context={
                "recommendation_summary": "Act now while preserving the recommendation boundary.",
                "action_path_reference": "action-path:price-adjustment-002",
                "scope_reference": "scope:store:001",
                "confidence_summary": "high_confidence",
                "constraint_summary": "inventory_and_margin_checked",
                "uncertainty_summary": "remaining_regime_uncertainty_is_bounded",
                "failure_state_context": "no_active_failure_state_detected",
            },
            policy_output_class_id="policy_shaped_allowance",
            policy_output_context={
                "policy_summary": "Preserve bounded allowance for downstream action preparation.",
                "policy_output_reference": "policy-output:allowance-002",
                "policy_rationale": "Recommendation and review lineage justify bounded policy allowance while preserving action-boundary discipline.",
                "action_boundary_summary": "Policy-shaped allowance only; downstream commitment and instruction remain separate.",
                "allowance_reference": "allowance:store:001:price-adjustment-window-002",
            },
            portfolio_output_class_id="portfolio_bounded_allocation",
            portfolio_output_context={
                "portfolio_summary": "Preserve bounded allocation posture for downstream portfolio planning.",
                "portfolio_output_reference": "portfolio-output:allocation-002",
                "portfolio_rationale": "Policy allowance lineage justifies bounded allocation posture for downstream planning.",
                "action_boundary_summary": "Allocative only; downstream commitment and instruction remain separate.",
                "allocation_reference": "allocation:store:001:price-adjustment-window-002",
                "allocation_weight_reference": "allocation-weight:store:001:0.74",
            },
            action_instruction_class_id="direct_action_instruction",
            action_instruction_context=(
                self.helpers.helpers.helpers.helpers._action_instruction_context()
            ),
            execution_request_class_id="direct_dispatch_request",
            execution_request_context=(
                self.helpers.helpers.helpers._direct_execution_request_context()
            ),
            execution_dispatch_class_id="direct_dispatch_boundary",
            execution_dispatch_context=(
                self.helpers.helpers._direct_execution_dispatch_context()
            ),
            execution_outcome_class_id="favorable_realized_outcome",
            execution_outcome_context=self.helpers._favorable_outcome_context(),
            post_mortem_judgment_class_id="correct_recommendation_correct_execution",
            post_mortem_judgment_context=self._ready_post_mortem_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(
            payload["post_mortem_judgment_status"],
            "ready_for_downstream_use",
        )
        self.assertEqual(
            payload["post_mortem_judgment_class_id"],
            "correct_recommendation_correct_execution",
        )
        self.assertEqual(
            payload["post_mortem_primary_attribution_category"],
            "correct_recommendation_correct_execution",
        )
        self.assertEqual(
            payload["post_mortem_comparison_posture"],
            "post_mortem_ready_expected_vs_realized",
        )

    def _build_post_mortem_service(self) -> PostMortemJudgmentService:
        registry = JsonPostMortemJudgmentRegistry(
            post_mortem_judgment_classes_path=(
                self.registry_root / "post_mortem_judgment_classes.json"
            ),
            post_mortem_judgment_templates_path=(
                self.registry_root / "post_mortem_judgment_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        audit_adapter = PostMortemJudgmentAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return PostMortemJudgmentService(
            post_mortem_judgment_registry=registry,
            post_mortem_judgment_audit_adapter=audit_adapter,
        )

    def _build_case_orchestrator(self):
        orchestrator = self.helpers._build_case_orchestrator()
        orchestrator._state_manager._post_mortem_judgment_service = (
            self.post_mortem_service
        )
        return orchestrator

    def _build_favorable_execution_outcome(self):
        return self.helpers.execution_outcome_service.generate(
            execution_outcome_test_module.ExecutionOutcomeCaptureRequest(
                execution_dispatch=self.helpers._build_direct_execution_dispatch(
                    impact_score=0.76
                ),
                execution_outcome_class_id="favorable_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context=self.helpers._favorable_outcome_context(),
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )

    def _build_negative_execution_outcome(self):
        return self.helpers.execution_outcome_service.generate(
            execution_outcome_test_module.ExecutionOutcomeCaptureRequest(
                execution_dispatch=self.helpers._build_direct_execution_dispatch(
                    impact_score=0.76
                ),
                execution_outcome_class_id="negative_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context=(
                    self.helpers._negative_deviation_outcome_context()
                ),
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )

    def _build_deferred_execution_outcome(self):
        return self.helpers.execution_outcome_service.generate(
            execution_outcome_test_module.ExecutionOutcomeCaptureRequest(
                execution_dispatch=self.helpers._build_fallback_execution_dispatch(),
                execution_outcome_class_id="deferred_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context=self.helpers._deferred_outcome_context(),
                correlation_id=str(uuid4()),
                actor_id="post-mortem-test",
            )
        )

    def _ready_post_mortem_context(self) -> dict[str, object]:
        return {
            "evidence_quality": "strong_reconstructible_evidence",
            "confidence_posture": "confident_for_attribution",
            "rationale_snapshot": (
                "Recommendation intent, execution realization, and observed outcome "
                "remain aligned enough to preserve the disciplined path."
            ),
            "evidence_basis_summary": (
                "Case, recommendation, execution, and outcome lineage remain "
                "complete enough to support strong attribution."
            ),
            "learning_direction": "preserve_current_path",
            "secondary_contributing_factors": [
                "stable_execution_conditions"
            ]
        }

    def _fallback_post_mortem_context(self) -> dict[str, object]:
        return {
            "evidence_quality": "immature_observation_horizon",
            "confidence_posture": "insufficient_for_confident_judgment",
            "rationale_snapshot": (
                "The governed observation horizon remains immature, so the platform "
                "must preserve insufficient-evidence posture rather than claim a "
                "confident attribution."
            ),
            "evidence_basis_summary": (
                "Outcome lineage is preserved, but the deferred observation posture "
                "does not yet support strong attribution."
            ),
            "learning_direction": "defer_learning_until_evidence_matures",
            "evidence_gaps": [
                "mature_realized_execution_observation"
            ]
        }


if __name__ == "__main__":
    unittest.main()