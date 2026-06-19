from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from data.ingestion.raw_ingestion_pipeline import (  # noqa: E402
    InMemoryRawRecordRepository,
    JsonIngestionSourceRegistry,
    RawIngestionCommand,
    RawIngestionPipeline,
)
from decision.authority import (  # noqa: E402
    AuthorityAuditAdapter,
    AuthorityResolutionService,
    JsonAuthorityRegistry,
    JsonDelegationPolicyRegistry,
)
from decision.case.case_state_manager import CaseStateManager  # noqa: E402
from decision.case.case_transition_audit_adapter import CaseTransitionAuditAdapter  # noqa: E402
from decision.case.case_episode_orchestrator import (  # noqa: E402
    CaseEpisodeOrchestrator,
    InMemoryCaseEpisodeRepository,
    JsonCaseTypeRegistry,
)
from decision.review import (  # noqa: E402
    HumanReviewPacketBuilder,
    JsonReviewPacketRegistry,
    JsonThresholdRegistry,
    ReviewAuditAdapter,
    ReviewPacketAuditAdapter,
    ReviewTriggerRequest,
    ReviewTriggerService,
    ThresholdEvaluator,
)
from decision.router import (  # noqa: E402
    ConflictClassifier,
    JsonRouterRegistry,
    RouterAuditAdapter,
    RouterService,
)
from ff_platform.audit.audit_event_store import (  # noqa: E402
    AuditEventStore,
    InMemoryAuditEventRepository,
    JsonAuditEventTypeRegistry,
)
from ff_platform.validation.contract_schema_validator import (  # noqa: E402
    ContractSchemaValidator,
    JsonContractSchemaRepository,
)
from state.features.feature_registry import (  # noqa: E402
    FeatureDefinition,
    FeatureRegistry,
    InMemoryFeatureDefinitionRepository,
    JsonFeatureOwnerRegistry,
)
from state.lifecycle.state_model_registry import JsonStateModelRegistry  # noqa: E402
from state.lifecycle.transition_validator import TransitionValidator  # noqa: E402


class ReviewThresholdLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry_root = REPO_ROOT / "registries" / "control_plane"
        schema_repository = JsonContractSchemaRepository(
            REPO_ROOT,
            self.registry_root / "contract_schemas.json",
        )
        self.contract_validator = ContractSchemaValidator(schema_repository=schema_repository)
        self.audit_store = AuditEventStore(
            event_type_registry=JsonAuditEventTypeRegistry(
                self.registry_root / "audit_event_types.json"
            ),
            repository=InMemoryAuditEventRepository(),
            contract_validator=self.contract_validator,
        )
        self.contract_validator.set_audit_sink(self.audit_store)
        self.review_service = self._build_review_service()
        self.feature_registry = self._build_feature_registry()

    def test_threshold_trigger_required(self) -> None:
        decision = self.review_service.evaluate(
            self._review_request(route_name="primary_case_path", impact_score=0.76)
        )

        self.assertEqual(decision.outcome_kind, "required")
        self.assertEqual(decision.threshold_id, "assessment_review_required")

    def test_threshold_trigger_optional(self) -> None:
        decision = self.review_service.evaluate(
            self._review_request(route_name="primary_case_path", impact_score=0.55)
        )

        self.assertEqual(decision.outcome_kind, "optional")
        self.assertEqual(decision.threshold_id, "assessment_review_optional")

    def test_threshold_not_triggered(self) -> None:
        decision = self.review_service.evaluate(
            self._review_request(route_name="primary_case_path", impact_score=0.20)
        )

        self.assertEqual(decision.outcome_kind, "not_triggered")

    def test_blocked_evaluation_due_to_missing_context(self) -> None:
        decision = self.review_service.evaluate(
            self._review_request(route_name="primary_case_path")
        )

        self.assertEqual(decision.outcome_kind, "blocked")
        self.assertEqual(decision.threshold_id, "assessment_review_optional")

    def test_calibration_profile_application(self) -> None:
        self.review_service.evaluate(
            self._review_request(route_name="primary_case_path", impact_score=0.76)
        )

        self.assertIn("decision.review.calibration_profile_applied", self._event_types())

    def test_fallback_review_mode_application(self) -> None:
        decision = self.review_service.evaluate(
            self._review_request(
                route_name="review_gate_path",
                impact_score=0.60,
                routing_review_required=True,
            )
        )

        self.assertEqual(decision.outcome_kind, "optional")
        self.assertEqual(decision.threshold_id, "review_gate_fallback_optional")

    def test_integration_with_lifecycle_authority_router_path(self) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description="Expected revenue delta used to seed review tests.",
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
            actor_id="review-test",
        )
        raw_pipeline = self._build_raw_pipeline()
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-001",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-001",
                        "candidate_revenue": 1200.0,
                        "baseline_revenue": 1000.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="review-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-001",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="review-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="review-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason="Assessment should carry governed threshold review metadata.",
            correlation_id=correlation_id,
            actor_id="review-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": "Assess whether the elevated impact score warrants accountable manual review."
            },
        )

        self.assertIn("decision.review.review_trigger_required", self._event_types())

    def test_audit_emission_for_threshold_outcomes(self) -> None:
        self.review_service.evaluate(
            self._review_request(route_name="primary_case_path", impact_score=0.76)
        )
        self.review_service.evaluate(
            self._review_request(route_name="primary_case_path", impact_score=0.55)
        )
        self.review_service.evaluate(
            self._review_request(route_name="primary_case_path", impact_score=0.20)
        )
        self.review_service.evaluate(self._review_request(route_name="primary_case_path"))
        self.review_service.evaluate(
            self._review_request(
                route_name="review_gate_path",
                impact_score=0.60,
                routing_review_required=True,
            )
        )

        event_types = self._event_types()
        self.assertIn("decision.review.threshold_evaluation_succeeded", event_types)
        self.assertIn("decision.review.threshold_triggered", event_types)
        self.assertIn("decision.review.threshold_not_triggered", event_types)
        self.assertIn("decision.review.threshold_evaluation_blocked", event_types)
        self.assertIn("decision.review.calibration_profile_applied", event_types)
        self.assertIn("decision.review.fallback_review_mode_applied", event_types)
        self.assertIn("decision.review.review_trigger_required", event_types)
        self.assertIn("decision.review.review_trigger_optional", event_types)

    def _build_review_service(self) -> ReviewTriggerService:
        threshold_registry = JsonThresholdRegistry(
            review_thresholds_path=self.registry_root / "review_thresholds.json",
            trigger_classes_path=self.registry_root / "trigger_classes.json",
            calibration_profiles_path=self.registry_root / "calibration_profiles.json",
            contract_validator=self.contract_validator,
        )
        review_audit_adapter = ReviewAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ReviewTriggerService(
            threshold_registry=threshold_registry,
            threshold_evaluator=ThresholdEvaluator(),
            review_audit_adapter=review_audit_adapter,
        )

    def _build_packet_builder(self) -> HumanReviewPacketBuilder:
        review_packet_registry = JsonReviewPacketRegistry(
            review_packet_templates_path=self.registry_root / "review_packet_templates.json",
            review_reason_classes_path=self.registry_root / "review_reason_classes.json",
            contract_validator=self.contract_validator,
        )
        review_packet_audit_adapter = ReviewPacketAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return HumanReviewPacketBuilder(
            review_packet_registry=review_packet_registry,
            review_packet_audit_adapter=review_packet_audit_adapter,
        )

    def _build_case_orchestrator(self) -> CaseEpisodeOrchestrator:
        authority_registry = JsonAuthorityRegistry(
            rules_path=self.registry_root / "authority_rules.json",
            roles_path=self.registry_root / "authority_roles.json",
            contract_validator=self.contract_validator,
        )
        delegation_policy_registry = JsonDelegationPolicyRegistry(
            registry_path=self.registry_root / "delegation_policies.json",
            contract_validator=self.contract_validator,
        )
        authority_audit_adapter = AuthorityAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        authority_resolution_service = AuthorityResolutionService(
            authority_registry=authority_registry,
            delegation_policy_registry=delegation_policy_registry,
            authority_audit_adapter=authority_audit_adapter,
        )
        state_model_registry = JsonStateModelRegistry(self.registry_root / "lifecycle_state_models.json")
        transition_validator = TransitionValidator(
            state_model_registry=state_model_registry,
            authority_resolution_service=authority_resolution_service,
        )
        router_registry = JsonRouterRegistry(
            router_rules_path=self.registry_root / "router_rules.json",
            conflict_classes_path=self.registry_root / "conflict_classes.json",
            route_precedence_path=self.registry_root / "route_precedence.json",
            contract_validator=self.contract_validator,
        )
        router_audit_adapter = RouterAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        router_service = RouterService(
            router_registry=router_registry,
            conflict_classifier=ConflictClassifier(router_registry),
            router_audit_adapter=router_audit_adapter,
        )
        transition_audit_adapter = CaseTransitionAuditAdapter(self.audit_store)
        state_manager = CaseStateManager(
            state_model_registry=state_model_registry,
            transition_validator=transition_validator,
            router_service=router_service,
            review_trigger_service=self.review_service,
            human_review_packet_builder=self._build_packet_builder(),
            transition_audit_adapter=transition_audit_adapter,
        )
        return CaseEpisodeOrchestrator(
            case_type_registry=JsonCaseTypeRegistry(self.registry_root / "case_episode_registry.json"),
            repository=InMemoryCaseEpisodeRepository(),
            contract_validator=self.contract_validator,
            audit_event_store=self.audit_store,
            feature_lookup=self.feature_registry,
            state_manager=state_manager,
        )

    def _build_feature_registry(self) -> FeatureRegistry:
        return FeatureRegistry(
            owner_registry=JsonFeatureOwnerRegistry(self.registry_root / "feature_owners.json"),
            repository=InMemoryFeatureDefinitionRepository(),
            contract_validator=self.contract_validator,
            audit_event_store=self.audit_store,
        )

    def _build_raw_pipeline(self) -> RawIngestionPipeline:
        return RawIngestionPipeline(
            source_registry=JsonIngestionSourceRegistry(self.registry_root / "ingestion_sources.json"),
            repository=InMemoryRawRecordRepository(),
            contract_validator=self.contract_validator,
            audit_event_store=self.audit_store,
        )

    def _review_request(
        self,
        *,
        route_name: str,
        impact_score: float | None = None,
        routing_review_required: bool = False,
    ) -> ReviewTriggerRequest:
        decision_context: dict[str, object] = {}
        if impact_score is not None:
            decision_context["impact_score"] = impact_score
        return ReviewTriggerRequest(
            semantic_scope="shared_control_plane",
            state_model_name="shared_control_plane_lifecycle",
            transition_name="promote_to_case_assessment",
            transition_class="forward_progression",
            source_stage="feature_registry",
            target_stage="case_orchestration",
            actor_role="case_operator",
            authority_resolution_kind="direct",
            authority_review_required=False,
            router_rule_id=(
                "fallback_resolution_case_route"
                if route_name == "contained_manual_fallback_path"
                else "default_case_route"
            ),
            route_name=route_name,
            routing_resolution_status="resolved",
            routing_conflict_class="precedence_required_conflict",
            routing_candidate_count=2,
            routing_review_required=routing_review_required,
            decision_context=decision_context,
            correlation_id=str(uuid4()),
            episode_id=str(uuid4()),
            actor_id="review-test",
        )

    def _event_types(self) -> list[str]:
        return [event.event_type for event in self.audit_store.list_events()]


if __name__ == "__main__":
    unittest.main()