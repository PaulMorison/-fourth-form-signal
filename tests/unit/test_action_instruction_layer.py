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
from decision.case.case_episode_orchestrator import (  # noqa: E402
    CaseEpisodeOrchestrator,
    InMemoryCaseEpisodeRepository,
    JsonCaseTypeRegistry,
)
from decision.case.case_state_manager import CaseStateManager  # noqa: E402
from decision.case.case_transition_audit_adapter import CaseTransitionAuditAdapter  # noqa: E402
from decision.output import (  # noqa: E402
    ActionInstructionAuditAdapter,
    ActionInstructionRequest,
    ActionInstructionService,
    JsonActionInstructionRegistry,
    JsonPolicyOutputRegistry,
    JsonPortfolioOutputRegistry,
    JsonRecommendationRegistry,
    PolicyOutputAuditAdapter,
    PolicyOutputRequest,
    PolicyOutputService,
    PortfolioOutputAuditAdapter,
    PortfolioOutputRequest,
    PortfolioOutputService,
    RecommendationAuditAdapter,
    RecommendationRequest,
    RecommendationService,
)
from decision.review import (  # noqa: E402
    HumanReviewPacketBuildRequest,
    HumanReviewPacketBuilder,
    JsonReviewPacketRegistry,
    JsonReviewResolutionRegistry,
    JsonThresholdRegistry,
    ReviewAuditAdapter,
    ReviewPacketAuditAdapter,
    ReviewResolutionAuditAdapter,
    ReviewResolutionRequest,
    ReviewResolutionService,
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
from platform.audit.audit_event_store import (  # noqa: E402
    AuditEventStore,
    InMemoryAuditEventRepository,
    JsonAuditEventTypeRegistry,
)
from platform.validation.contract_schema_validator import (  # noqa: E402
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


class ActionInstructionLayerTests(unittest.TestCase):
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
        self.packet_builder = self._build_packet_builder()
        self.resolution_service = self._build_resolution_service()
        self.recommendation_service = self._build_recommendation_service()
        self.policy_output_service = self._build_policy_output_service()
        self.portfolio_output_service = self._build_portfolio_output_service()
        self.action_instruction_service = self._build_action_instruction_service()
        self.feature_registry = self._build_feature_registry()

    def test_successful_action_instruction_from_legitimate_portfolio_output(self) -> None:
        portfolio_output = self._build_action_portfolio_output(impact_score=0.76)

        action_instruction = self.action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=portfolio_output,
                action_instruction_class_id="direct_action_instruction",
                instruction_author_role="case_operator",
                action_instruction_context=self._action_instruction_context(),
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

        self.assertEqual(
            action_instruction.action_instruction_status,
            "ready_for_downstream_use",
        )
        self.assertEqual(
            action_instruction.instruction_status,
            "executable_instruction_ready",
        )
        self.assertEqual(
            action_instruction.execution_boundary_posture,
            "instruction_not_executed",
        )

    def test_blocked_action_instruction_due_to_missing_required_context(self) -> None:
        portfolio_output = self._build_information_portfolio_output(impact_score=0.55)

        action_instruction = self.action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=portfolio_output,
                action_instruction_class_id="prerequisite_bounded_instruction",
                instruction_author_role="case_operator",
                action_instruction_context={
                    "instruction_summary": "Preserve a governed clarification instruction posture until the missing prerequisite is satisfied."
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

        self.assertEqual(action_instruction.action_instruction_status, "blocked")
        self.assertIn(
            "blocking_condition_reference",
            action_instruction.missing_instruction_fields,
        )

    def test_fallback_template_usage(self) -> None:
        portfolio_output = self._build_fallback_portfolio_output()

        action_instruction = self.action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=portfolio_output,
                action_instruction_class_id="suppression_hold_instruction",
                instruction_author_role="case_operator",
                action_instruction_context=self._fallback_action_instruction_context(),
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

        self.assertEqual(
            action_instruction.action_instruction_status,
            "fallback_template_applied",
        )
        self.assertEqual(
            action_instruction.action_instruction_template_id,
            "suppression_hold_instruction_fallback",
        )

    def test_action_instruction_completeness_and_lineage_mapping(self) -> None:
        portfolio_output = self._build_information_portfolio_output(impact_score=0.55)

        action_instruction = self.action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=portfolio_output,
                action_instruction_class_id="prerequisite_bounded_instruction",
                instruction_author_role="case_operator",
                action_instruction_context=self._prerequisite_action_instruction_context(),
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

        self.assertEqual(
            action_instruction.required_instruction_snapshot["clarification_reference"],
            "clarification-placeholder-001",
        )
        self.assertEqual(
            action_instruction.instruction_status,
            "instruction_blocked_pending_prerequisite",
        )
        self.assertEqual(
            action_instruction.lineage["portfolio_output_id"],
            portfolio_output.portfolio_output_id,
        )
        self.assertEqual(
            action_instruction.lineage["action_instruction_template_id"],
            action_instruction.action_instruction_template_id,
        )

    def test_integration_with_lifecycle_authority_router_review_policy_portfolio_and_action_instruction_path(
        self,
    ) -> None:
        orchestrator = self._build_case_orchestrator()
        feature = self.feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description="Expected revenue delta used to seed action-instruction tests.",
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
            actor_id="action-instruction-test",
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
            actor_id="action-instruction-test",
        )
        correlation_id = str(uuid4())
        episode = orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-001",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="action-instruction-test",
            actor_role="case_operator",
            threshold_context={"impact_score": 0.10},
        )
        feature_review = orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=correlation_id,
            actor_id="action-instruction-test",
            actor_role="assistant_case_operator",
        )
        orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason="Assessment should emit a governed action instruction only after portfolio output generation.",
            correlation_id=correlation_id,
            actor_id="action-instruction-test",
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
                "action_path_reference": "action-path:price-adjustment-001",
                "scope_reference": "scope:store:001",
                "confidence_summary": "high_confidence",
                "constraint_summary": "inventory_and_margin_checked",
                "uncertainty_summary": "remaining_regime_uncertainty_is_bounded",
                "failure_state_context": "no_active_failure_state_detected",
            },
            policy_output_class_id="policy_shaped_allowance",
            policy_output_context={
                "policy_summary": "Preserve bounded allowance for downstream action preparation.",
                "policy_output_reference": "policy-output:allowance-001",
                "policy_rationale": "Recommendation and review lineage justify bounded policy allowance while preserving action-boundary discipline.",
                "action_boundary_summary": "Policy-shaped allowance only; downstream commitment and instruction remain separate.",
                "allowance_reference": "allowance:store:001:price-adjustment-window",
            },
            portfolio_output_class_id="portfolio_bounded_allocation",
            portfolio_output_context={
                "portfolio_summary": "Preserve bounded allocation posture for downstream portfolio planning.",
                "portfolio_output_reference": "portfolio-output:allocation-001",
                "portfolio_rationale": "Policy allowance lineage justifies bounded allocation posture for downstream planning.",
                "action_boundary_summary": "Allocative only; downstream commitment and instruction remain separate.",
                "allocation_reference": "allocation:store:001:price-adjustment-window",
                "allocation_weight_reference": "allocation-weight:store:001:0.72",
            },
            action_instruction_class_id="direct_action_instruction",
            action_instruction_context=self._action_instruction_context(),
        )

        handoff_events = [
            event
            for event in self.audit_store.list_events()
            if event.event_type == "decision.case.handoff_recorded"
        ]
        self.assertTrue(handoff_events)
        payload = handoff_events[-1].payload
        self.assertEqual(payload["action_instruction_status"], "ready_for_downstream_use")
        self.assertEqual(
            payload["action_instruction_class_id"],
            "direct_action_instruction",
        )
        self.assertEqual(
            payload["action_instruction_execution_boundary_posture"],
            "instruction_not_executed",
        )

    def test_audit_emission_for_action_instruction_outcomes(self) -> None:
        action_portfolio_output = self._build_action_portfolio_output(impact_score=0.76)
        information_portfolio_output = self._build_information_portfolio_output(
            impact_score=0.55
        )
        fallback_portfolio_output = self._build_fallback_portfolio_output()

        self.action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=action_portfolio_output,
                action_instruction_class_id="direct_action_instruction",
                instruction_author_role="case_operator",
                action_instruction_context=self._action_instruction_context(),
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )
        self.action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=information_portfolio_output,
                action_instruction_class_id="prerequisite_bounded_instruction",
                instruction_author_role="case_operator",
                action_instruction_context={
                    "instruction_summary": "Preserve a governed clarification instruction posture until the missing prerequisite is satisfied."
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )
        self.action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=fallback_portfolio_output,
                action_instruction_class_id="suppression_hold_instruction",
                instruction_author_role="case_operator",
                action_instruction_context=self._fallback_action_instruction_context(),
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

        event_types = self._event_types()
        self.assertIn("decision.output.action_instruction_recorded", event_types)
        self.assertIn("decision.output.action_instruction_blocked", event_types)
        self.assertIn(
            "decision.output.action_instruction_ready_for_downstream_use",
            event_types,
        )
        self.assertIn("decision.output.action_instruction_missing_context", event_types)
        self.assertIn(
            "decision.output.action_instruction_fallback_template_applied",
            event_types,
        )

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

    def _build_resolution_service(self) -> ReviewResolutionService:
        review_resolution_registry = JsonReviewResolutionRegistry(
            review_resolution_classes_path=self.registry_root / "review_resolution_classes.json",
            case_disposition_classes_path=self.registry_root / "case_disposition_classes.json",
            contract_validator=self.contract_validator,
        )
        review_resolution_audit_adapter = ReviewResolutionAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ReviewResolutionService(
            review_resolution_registry=review_resolution_registry,
            review_resolution_audit_adapter=review_resolution_audit_adapter,
        )

    def _build_recommendation_service(self) -> RecommendationService:
        recommendation_registry = JsonRecommendationRegistry(
            recommendation_classes_path=self.registry_root / "recommendation_classes.json",
            recommendation_templates_path=self.registry_root / "recommendation_templates.json",
            contract_validator=self.contract_validator,
        )
        recommendation_audit_adapter = RecommendationAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return RecommendationService(
            recommendation_registry=recommendation_registry,
            recommendation_audit_adapter=recommendation_audit_adapter,
        )

    def _build_policy_output_service(self) -> PolicyOutputService:
        policy_output_registry = JsonPolicyOutputRegistry(
            policy_output_classes_path=self.registry_root / "policy_output_classes.json",
            policy_output_templates_path=self.registry_root / "policy_output_templates.json",
            contract_validator=self.contract_validator,
        )
        policy_output_audit_adapter = PolicyOutputAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return PolicyOutputService(
            policy_output_registry=policy_output_registry,
            policy_output_audit_adapter=policy_output_audit_adapter,
        )

    def _build_portfolio_output_service(self) -> PortfolioOutputService:
        portfolio_output_registry = JsonPortfolioOutputRegistry(
            portfolio_output_classes_path=self.registry_root / "portfolio_output_classes.json",
            portfolio_output_templates_path=self.registry_root / "portfolio_output_templates.json",
            contract_validator=self.contract_validator,
        )
        portfolio_output_audit_adapter = PortfolioOutputAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return PortfolioOutputService(
            portfolio_output_registry=portfolio_output_registry,
            portfolio_output_audit_adapter=portfolio_output_audit_adapter,
        )

    def _build_action_instruction_service(self) -> ActionInstructionService:
        action_instruction_registry = JsonActionInstructionRegistry(
            action_instruction_classes_path=(
                self.registry_root / "action_instruction_classes.json"
            ),
            action_instruction_templates_path=(
                self.registry_root / "action_instruction_templates.json"
            ),
            contract_validator=self.contract_validator,
        )
        action_instruction_audit_adapter = ActionInstructionAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return ActionInstructionService(
            action_instruction_registry=action_instruction_registry,
            action_instruction_audit_adapter=action_instruction_audit_adapter,
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
        state_model_registry = JsonStateModelRegistry(
            self.registry_root / "lifecycle_state_models.json"
        )
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
            human_review_packet_builder=self.packet_builder,
            review_resolution_service=self.resolution_service,
            recommendation_service=self.recommendation_service,
            policy_output_service=self.policy_output_service,
            portfolio_output_service=self.portfolio_output_service,
            action_instruction_service=self.action_instruction_service,
            transition_audit_adapter=transition_audit_adapter,
        )
        return CaseEpisodeOrchestrator(
            case_type_registry=JsonCaseTypeRegistry(
                self.registry_root / "case_episode_registry.json"
            ),
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
            source_registry=JsonIngestionSourceRegistry(
                self.registry_root / "ingestion_sources.json"
            ),
            repository=InMemoryRawRecordRepository(),
            contract_validator=self.contract_validator,
            audit_event_store=self.audit_store,
        )

    def _build_action_portfolio_output(self, *, impact_score: float):
        policy_output = self._build_action_policy_output(impact_score=impact_score)
        return self.portfolio_output_service.generate(
            PortfolioOutputRequest(
                policy_output=policy_output,
                portfolio_output_class_id="portfolio_bounded_allocation",
                portfolio_author_role="case_operator",
                portfolio_output_context={
                    "portfolio_summary": "Preserve bounded allocation posture for downstream portfolio planning.",
                    "portfolio_output_reference": "portfolio-output:allocation-001",
                    "portfolio_rationale": "Policy allowance lineage justifies bounded allocation posture for downstream planning.",
                    "action_boundary_summary": "Allocative only; downstream commitment and instruction remain separate.",
                    "allocation_reference": "allocation:store:001:price-adjustment-window",
                    "allocation_weight_reference": "allocation-weight:store:001:0.72",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_information_portfolio_output(self, *, impact_score: float):
        policy_output = self._build_information_policy_output(impact_score=impact_score)
        return self.portfolio_output_service.generate(
            PortfolioOutputRequest(
                policy_output=policy_output,
                portfolio_output_class_id="portfolio_ranked_preference",
                portfolio_author_role="case_operator",
                portfolio_output_context={
                    "portfolio_summary": "Preserve ranked clarification preference until ambiguity is resolved.",
                    "portfolio_output_reference": "portfolio-output:clarification-001",
                    "portfolio_rationale": "Policy output lineage supports explicit ranked clarification priority before stronger downstream handling.",
                    "action_boundary_summary": "Allocative only; downstream commitment and instruction remain separate.",
                    "preference_rank_reference": "clarification-rank:store:001:1",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_fallback_portfolio_output(self):
        policy_output = self._build_fallback_policy_output()
        return self.portfolio_output_service.generate(
            PortfolioOutputRequest(
                policy_output=policy_output,
                portfolio_output_class_id="portfolio_suppression_hold",
                portfolio_author_role="case_operator",
                portfolio_output_context={
                    "portfolio_summary": "Preserve fallback suppression hold posture until a later governed reviewer revisits the case.",
                    "portfolio_output_reference": "portfolio-output:fallback-hold-001",
                    "portfolio_rationale": "Fallback policy output remains explicit until stronger downstream evidence or authority changes the bounded portfolio posture.",
                    "action_boundary_summary": "Policy-shaped suppression only; no downstream instruction is authorized by this output.",
                    "suppression_reference": "suppression:manual-triage-hold-001",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_action_policy_output(self, *, impact_score: float):
        recommendation = self._build_action_recommendation(impact_score=impact_score)
        return self.policy_output_service.generate(
            PolicyOutputRequest(
                recommendation=recommendation,
                policy_output_class_id="policy_shaped_allowance",
                policy_author_role="case_operator",
                policy_output_context={
                    "policy_summary": "Preserve bounded allowance for downstream action preparation.",
                    "policy_output_reference": "policy-output:allowance-001",
                    "policy_rationale": "Recommendation and review lineage justify bounded policy allowance for downstream preparation.",
                    "action_boundary_summary": "Policy-shaped allowance only; downstream commitment and instruction remain separate.",
                    "allowance_reference": "allowance:store:001:price-adjustment-window",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_information_policy_output(self, *, impact_score: float):
        recommendation = self._build_information_recommendation(impact_score=impact_score)
        return self.policy_output_service.generate(
            PolicyOutputRequest(
                recommendation=recommendation,
                policy_output_class_id="policy_shaped_information_requirement",
                policy_author_role="case_operator",
                policy_output_context={
                    "policy_summary": "Preserve clarification-first policy posture until ambiguity is resolved.",
                    "policy_output_reference": "policy-output:clarification-001",
                    "policy_rationale": "Clarification remains required before stronger policy posture is legitimate.",
                    "action_boundary_summary": "Policy-shaped information requirement only; further governance remains required before action.",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_fallback_policy_output(self):
        recommendation = self._build_fallback_recommendation()
        return self.policy_output_service.generate(
            PolicyOutputRequest(
                recommendation=recommendation,
                policy_output_class_id="policy_shaped_suppression",
                policy_author_role="case_operator",
                policy_output_context={
                    "policy_summary": "Preserve fallback suppression posture until a later governed reviewer revisits the case.",
                    "policy_output_reference": "policy-output:fallback-hold-001",
                    "policy_rationale": "Fallback handling remains explicit until stronger downstream evidence or authority changes the bounded policy posture.",
                    "action_boundary_summary": "Policy-shaped suppression only; no downstream instruction is authorized by this output.",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_action_recommendation(self, *, impact_score: float):
        resolution = self._build_resolved_action_resolution(impact_score=impact_score)
        return self.recommendation_service.recommend(
            RecommendationRequest(
                review_resolution=resolution,
                recommendation_class_id="recommend_act_now",
                recommender_role="case_operator",
                recommendation_context={
                    "recommendation_summary": "Act now while preserving the recommendation boundary.",
                    "action_path_reference": "action-path:price-adjustment-001",
                    "scope_reference": "scope:store:001",
                    "confidence_summary": "high_confidence",
                    "constraint_summary": "inventory_and_margin_checked",
                    "uncertainty_summary": "remaining_regime_uncertainty_is_bounded",
                    "failure_state_context": "no_active_failure_state_detected",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_information_recommendation(self, *, impact_score: float):
        resolution = self._build_clarification_resolution(impact_score=impact_score)
        return self.recommendation_service.recommend(
            RecommendationRequest(
                review_resolution=resolution,
                recommendation_class_id="recommend_gather_more_information",
                recommender_role="case_operator",
                recommendation_context={
                    "recommendation_summary": "Gather more information before stronger downstream action is considered.",
                    "action_path_reference": "action-path:clarification-request-001",
                    "scope_reference": "scope:store:001",
                    "confidence_summary": "moderate_confidence",
                    "constraint_summary": "scope_and_evidence_must_be_clarified",
                    "uncertainty_summary": "important_customer_scope_gap_remains",
                    "failure_state_context": "no_failure_state_detected",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_fallback_recommendation(self):
        resolution = self._build_manual_fallback_resolution()
        return self.recommendation_service.recommend(
            RecommendationRequest(
                review_resolution=resolution,
                recommendation_class_id="abstain_from_strong_recommendation",
                recommender_role="case_operator",
                recommendation_context={
                    "recommendation_summary": "Preserve abstention until stronger downstream evidence exists.",
                    "action_path_reference": "action-path:manual-triage-hold-001",
                    "scope_reference": "scope:store:001",
                    "confidence_summary": "low_confidence",
                    "constraint_summary": "manual_triage_required_before_stronger_advice",
                    "uncertainty_summary": "evidence_and_scope_remain_open",
                    "failure_state_context": "fallback_manual_triage_active",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_resolved_action_resolution(self, *, impact_score: float):
        packet = self._build_ready_packet(impact_score=impact_score)
        return self.resolution_service.resolve(
            ReviewResolutionRequest(
                packet=packet,
                resolution_class_id="resolved_with_action",
                reviewer_role="case_operator",
                resolution_context={
                    "review_summary": "The reviewer fixed a governed downstream action path.",
                    "resolution_rationale": "The required review threshold and preserved packet context justify action routing.",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_clarification_resolution(self, *, impact_score: float):
        packet = self._build_ready_packet(impact_score=impact_score)
        return self.resolution_service.resolve(
            ReviewResolutionRequest(
                packet=packet,
                resolution_class_id="returned_for_clarification",
                reviewer_role="case_operator",
                resolution_context={
                    "review_summary": "The optional packet remains materially ambiguous.",
                    "resolution_rationale": "Clarification is required before a valid settlement may stand.",
                    "clarification_reference": "clarification-placeholder-001",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_manual_fallback_resolution(self):
        decision = self.review_service.evaluate(
            self._review_request(
                route_name="review_gate_path",
                impact_score=0.60,
                routing_review_required=True,
            )
        )
        packet = self.packet_builder.build(
            self._packet_request(
                review_decision=decision,
                route_name="review_gate_path",
                routing_review_required=True,
                packet_context={
                    "review_focus": "Preserve fallback review handling for later manual triage.",
                    "impact_score": 0.60,
                },
            )
        )
        return self.resolution_service.resolve(
            ReviewResolutionRequest(
                packet=packet,
                resolution_class_id="manual_fallback_resolution",
                reviewer_role="case_operator",
                resolution_context={
                    "review_summary": "Fallback packet is preserved for later manual triage.",
                    "resolution_rationale": "Fallback handling remains explicit until a later governed reviewer resolves the case.",
                    "fallback_reference": "manual-triage-placeholder-001",
                },
                correlation_id=str(uuid4()),
                actor_id="action-instruction-test",
            )
        )

    def _build_ready_packet(self, *, impact_score: float):
        decision = self.review_service.evaluate(
            self._review_request(route_name="primary_case_path", impact_score=impact_score)
        )
        return self.packet_builder.build(
            self._packet_request(
                review_decision=decision,
                route_name="primary_case_path",
                packet_context={
                    "review_focus": "Assess whether the governed review threshold warrants accountable manual review.",
                    "impact_score": impact_score,
                },
            )
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
            state_model_name="shared_control_plane_case_model",
            transition_name="promote_to_case_assessment",
            transition_class="forward_progression",
            source_stage="feature_registry",
            target_stage="case_orchestration",
            actor_role="case_operator",
            authority_resolution_kind="direct",
            authority_review_required=False,
            router_rule_id="default_case_route",
            route_name=route_name,
            routing_resolution_status="resolved",
            routing_conflict_class="precedence_required_conflict",
            routing_candidate_count=2,
            routing_review_required=routing_review_required,
            decision_context=decision_context,
            correlation_id=str(uuid4()),
            episode_id=str(uuid4()),
            actor_id="action-instruction-test",
        )

    def _packet_request(
        self,
        *,
        review_decision,
        route_name: str,
        packet_context: dict[str, object],
        routing_review_required: bool = False,
    ) -> HumanReviewPacketBuildRequest:
        return HumanReviewPacketBuildRequest(
            semantic_scope="shared_control_plane",
            case_type="shared_control_plane_case",
            case_key="case:promo-001",
            state_model_name="shared_control_plane_case_model",
            episode_id=str(uuid4()),
            transition_name="promote_to_case_assessment",
            transition_class="forward_progression",
            source_stage="feature_registry",
            target_stage="case_orchestration",
            actor_role="case_operator",
            authority_resolution_kind="direct",
            authority_review_required=False,
            router_rule_id="default_case_route",
            route_name=route_name,
            routing_resolution_status="resolved",
            routing_review_required=routing_review_required,
            review_decision=review_decision,
            packet_context=packet_context,
            correlation_id=str(uuid4()),
            actor_id="action-instruction-test",
        )

    def _action_instruction_context(self) -> dict[str, object]:
        return {
            "instruction_summary": "Issue a governed downstream preparation instruction while keeping execution separate from instruction legitimacy.",
            "action_instruction_reference": "action-instruction:direct-001",
            "upstream_commitment_reference": "commitment-placeholder:direct-001",
            "instruction_authority_reference": "instruction-authority:case-operator",
            "executable_scope_reference": "scope:store:001:price-adjustment-window",
            "intended_action_reference": "intended-action:price-adjustment-001",
            "action_delivery_channel": "downstream_preparation_handoff",
        }

    def _prerequisite_action_instruction_context(self) -> dict[str, object]:
        return {
            "instruction_summary": "Preserve a governed clarification instruction posture until the missing prerequisite is satisfied.",
            "action_instruction_reference": "action-instruction:clarification-001",
            "upstream_commitment_reference": "commitment-placeholder:clarification-001",
            "instruction_authority_reference": "instruction-authority:case-operator",
            "executable_scope_reference": "scope:store:001:clarification-loop",
            "intended_action_reference": "intended-action:clarification-request-001",
            "action_delivery_channel": "manual_clarification_handoff",
            "blocking_condition_reference": "clarification-gap:store-001",
            "clarification_reference": "clarification-placeholder-001",
            "blocking_condition_kind": "prerequisite",
        }

    def _fallback_action_instruction_context(self) -> dict[str, object]:
        return {
            "instruction_summary": "Preserve a governed suppression-hold instruction posture until a later governed reviewer revisits the case.",
            "action_instruction_reference": "action-instruction:fallback-001",
            "upstream_commitment_reference": "commitment-placeholder:fallback-001",
            "instruction_authority_reference": "instruction-authority:case-operator",
            "executable_scope_reference": "scope:store:001:manual-triage-hold",
            "intended_action_reference": "intended-action:manual-triage-hold-001",
            "action_delivery_channel": "manual_triage_handoff",
            "fallback_reference": "manual-triage-placeholder-001",
        }

    def _event_types(self) -> list[str]:
        return [event.event_type for event in self.audit_store.list_events()]


if __name__ == "__main__":
    unittest.main()