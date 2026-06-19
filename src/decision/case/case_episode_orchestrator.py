from __future__ import annotations

"""Governed episode orchestration for the first shared control-plane batch.

Canon ownership:
- Implements episode identity, entry legitimacy, handoff legitimacy,
  interruption legitimacy, resumption legitimacy, and fallback legitimacy for a
  minimal shared control-plane case flow.
- Does not absorb state-model, review, or routing ownership that the canon keeps
  in adjacent modules.
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from decision.case.case_state_manager import CaseStateManager
from ff_platform.audit.audit_event_store import AuditEventStore
from ff_platform.validation.contract_schema_validator import ContractSchemaValidator


class CaseEpisodeRepositoryError(ValueError):
    """Base error for episode-orchestration failures."""


class EpisodeEntryValidationError(CaseEpisodeRepositoryError):
    """Raised when a case cannot enter a governed episode."""


class HandoffValidationError(CaseEpisodeRepositoryError):
    """Raised when a stage handoff is not allowed by the orchestration registry."""


@dataclass(frozen=True)
class CaseTypeDefinition:
    case_type: str
    state_model_name: str
    initial_stage: str
    allowed_stages: tuple[str, ...]
    allowed_stage_transitions: Mapping[str, tuple[str, ...]]
    allowed_feature_namespaces: tuple[str, ...]


@dataclass(frozen=True)
class CaseHandoffRecord:
    from_stage: str
    to_stage: str
    reason: str
    actor_id: str
    occurred_at: datetime

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "from_stage": self.from_stage,
            "to_stage": self.to_stage,
            "reason": self.reason,
            "actor_id": self.actor_id,
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True)
class CaseEpisode:
    episode_id: str
    case_type: str
    case_key: str
    state_model_name: str
    current_state: str
    status: str
    current_stage: str
    opened_at: datetime
    last_updated_at: datetime
    raw_record_ids: tuple[str, ...]
    feature_names: tuple[str, ...]
    interruption_reason: str | None
    handoffs: tuple[CaseHandoffRecord, ...]

    def to_contract_dict(self) -> dict[str, Any]:
        contract = {
            "episode_id": self.episode_id,
            "case_type": self.case_type,
            "case_key": self.case_key,
            "state_model_name": self.state_model_name,
            "current_state": self.current_state,
            "status": self.status,
            "current_stage": self.current_stage,
            "opened_at": self.opened_at.isoformat(),
            "last_updated_at": self.last_updated_at.isoformat(),
            "raw_record_ids": list(self.raw_record_ids),
            "feature_names": list(self.feature_names),
            "handoff_count": len(self.handoffs),
        }
        if self.interruption_reason is not None:
            contract["interruption_reason"] = self.interruption_reason
        return contract


class CaseEpisodeRepository(Protocol):
    def save(self, episode: CaseEpisode) -> None:
        """Persist a case episode."""

    def get(self, episode_id: str) -> CaseEpisode | None:
        """Return an episode by identifier."""

    def list_episodes(self) -> Sequence[CaseEpisode]:
        """Return all persisted episodes."""


class CaseTypeRegistry(Protocol):
    def get_case_type(self, case_type: str) -> CaseTypeDefinition:
        """Return the governing case-type definition."""


class FeatureLookup(Protocol):
    def get_feature(self, feature_name: str) -> Any:
        """Return a feature when it exists."""


class InMemoryCaseEpisodeRepository:
    """Deterministic persistence seam for the first orchestration flow."""

    def __init__(self) -> None:
        self._episodes: dict[str, CaseEpisode] = {}

    def save(self, episode: CaseEpisode) -> None:
        self._episodes[episode.episode_id] = episode

    def get(self, episode_id: str) -> CaseEpisode | None:
        return self._episodes.get(episode_id)

    def list_episodes(self) -> Sequence[CaseEpisode]:
        return tuple(self._episodes.values())


class JsonCaseTypeRegistry:
    """Loads the initial case flow from a checked-in orchestration registry."""

    def __init__(self, registry_path: Path) -> None:
        content = json.loads(registry_path.read_text(encoding="utf-8"))
        self._case_types = {
            case_type: CaseTypeDefinition(
                case_type=case_type,
                state_model_name=entry["state_model_name"],
                initial_stage=entry["initial_stage"],
                allowed_stages=tuple(entry["allowed_stages"]),
                allowed_stage_transitions={
                    stage: tuple(targets)
                    for stage, targets in entry["allowed_stage_transitions"].items()
                },
                allowed_feature_namespaces=tuple(entry["allowed_feature_namespaces"]),
            )
            for case_type, entry in content["case_types"].items()
        }

    def get_case_type(self, case_type: str) -> CaseTypeDefinition:
        try:
            return self._case_types[case_type]
        except KeyError as error:
            raise EpisodeEntryValidationError(f"Case type '{case_type}' is not registered.") from error


class CaseEpisodeOrchestrator:
    """Creates and advances governed decision episodes.

    The orchestrator is intentionally narrow: it owns episode entry, handoff,
    interruption, resumption, and fallback for the first control-plane batch.
    It does not own review routing, recommendation meaning, policy-output
    meaning, portfolio-output meaning, action-instruction meaning,
    execution-request meaning, execution-dispatch meaning, decision rights, or
    lifecycle composition.
    """

    def __init__(
        self,
        *,
        case_type_registry: CaseTypeRegistry,
        repository: CaseEpisodeRepository,
        contract_validator: ContractSchemaValidator,
        audit_event_store: AuditEventStore,
        feature_lookup: FeatureLookup,
        state_manager: CaseStateManager,
    ) -> None:
        self._case_type_registry = case_type_registry
        self._repository = repository
        self._contract_validator = contract_validator
        self._audit_event_store = audit_event_store
        self._feature_lookup = feature_lookup
        self._state_manager = state_manager

    def open_episode(
        self,
        *,
        case_type: str,
        case_key: str,
        raw_record_ids: Sequence[str],
        feature_names: Sequence[str],
        correlation_id: str,
        actor_id: str,
        actor_role: str,
        threshold_context: Mapping[str, object] | None = None,
        packet_context: Mapping[str, object] | None = None,
        review_resolution_class_id: str | None = None,
        review_resolution_context: Mapping[str, object] | None = None,
        recommendation_class_id: str | None = None,
        recommendation_context: Mapping[str, object] | None = None,
        policy_output_class_id: str | None = None,
        policy_output_context: Mapping[str, object] | None = None,
        portfolio_output_class_id: str | None = None,
        portfolio_output_context: Mapping[str, object] | None = None,
        action_instruction_class_id: str | None = None,
        action_instruction_context: Mapping[str, object] | None = None,
        execution_request_class_id: str | None = None,
        execution_request_context: Mapping[str, object] | None = None,
        execution_dispatch_class_id: str | None = None,
        execution_dispatch_context: Mapping[str, object] | None = None,
        execution_outcome_class_id: str | None = None,
        execution_outcome_context: Mapping[str, object] | None = None,
        post_mortem_judgment_class_id: str | None = None,
        post_mortem_judgment_context: Mapping[str, object] | None = None,
        policy_learning_evidence_class_id: str | None = None,
        policy_learning_evidence_admission_context: Mapping[str, object] | None = None,
        policy_learning_update_threshold_class_id: str | None = None,
        policy_learning_update_threshold_context: Mapping[str, object] | None = None,
        policy_learning_update_approval_class_id: str | None = None,
        policy_learning_update_approval_context: Mapping[str, object] | None = None,
        policy_learning_update_preparation_class_id: str | None = None,
        policy_learning_update_preparation_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_planning_class_id: str | None = None,
        policy_learning_update_mutation_planning_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_execution_class_id: str | None = None,
        policy_learning_update_mutation_execution_context: Mapping[str, object] | None = None,
        promotion_readiness_class_id: str | None = None,
        promotion_readiness_context: Mapping[str, object] | None = None,
        rollout_scope_class_id: str | None = None,
        rollout_scope_context: Mapping[str, object] | None = None,
        rollback_trigger_class_id: str | None = None,
        rollback_trigger_context: Mapping[str, object] | None = None,
        release_watch_discipline_class_id: str | None = None,
        release_watch_discipline_context: Mapping[str, object] | None = None,
        release_confirmation_class_id: str | None = None,
        release_confirmation_context: Mapping[str, object] | None = None,
        production_entitlement_check_class_id: str | None = None,
        production_entitlement_check_context: Mapping[str, object] | None = None,
        contained_rollback_class_id: str | None = None,
        contained_rollback_context: Mapping[str, object] | None = None,
        release_audit_trace_class_id: str | None = None,
        release_audit_trace_context: Mapping[str, object] | None = None,
    ) -> CaseEpisode:
        case_type_definition = self._case_type_registry.get_case_type(case_type)
        if not raw_record_ids:
            raise EpisodeEntryValidationError("At least one raw record id is required.")
        self._validate_features(feature_names, case_type_definition)

        episode_id = str(uuid4())
        initial_state = self._state_manager.initialize_case_state(
            case_type=case_type,
            case_key=case_key,
            state_model_name=case_type_definition.state_model_name,
            correlation_id=correlation_id,
            episode_id=episode_id,
            actor_id=actor_id,
            actor_role=actor_role,
            route_target_stage=case_type_definition.initial_stage,
            threshold_context=threshold_context,
            packet_context=packet_context,
            reason="Episode entry legitimized through the lifecycle guard layer.",
            review_resolution_class_id=review_resolution_class_id,
            review_resolution_context=review_resolution_context,
            recommendation_class_id=recommendation_class_id,
            recommendation_context=recommendation_context,
            policy_output_class_id=policy_output_class_id,
            policy_output_context=policy_output_context,
            portfolio_output_class_id=portfolio_output_class_id,
            portfolio_output_context=portfolio_output_context,
            action_instruction_class_id=action_instruction_class_id,
            action_instruction_context=action_instruction_context,
            execution_request_class_id=execution_request_class_id,
            execution_request_context=execution_request_context,
            execution_dispatch_class_id=execution_dispatch_class_id,
            execution_dispatch_context=execution_dispatch_context,
            execution_outcome_class_id=execution_outcome_class_id,
            execution_outcome_context=execution_outcome_context,
            post_mortem_judgment_class_id=post_mortem_judgment_class_id,
            post_mortem_judgment_context=post_mortem_judgment_context,
            policy_learning_evidence_class_id=policy_learning_evidence_class_id,
            policy_learning_evidence_admission_context=(
                policy_learning_evidence_admission_context
            ),
            policy_learning_update_threshold_class_id=(
                policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_context=(
                policy_learning_update_threshold_context
            ),
            policy_learning_update_approval_class_id=(
                policy_learning_update_approval_class_id
            ),
            policy_learning_update_approval_context=(
                policy_learning_update_approval_context
            ),
            policy_learning_update_preparation_class_id=(
                policy_learning_update_preparation_class_id
            ),
            policy_learning_update_preparation_context=(
                policy_learning_update_preparation_context
            ),
            policy_learning_update_mutation_planning_class_id=(
                policy_learning_update_mutation_planning_class_id
            ),
            policy_learning_update_mutation_planning_context=(
                policy_learning_update_mutation_planning_context
            ),
            policy_learning_update_mutation_execution_class_id=(
                policy_learning_update_mutation_execution_class_id
            ),
            policy_learning_update_mutation_execution_context=(
                policy_learning_update_mutation_execution_context
            ),
            promotion_readiness_class_id=promotion_readiness_class_id,
            promotion_readiness_context=promotion_readiness_context,
            rollout_scope_class_id=rollout_scope_class_id,
            rollout_scope_context=rollout_scope_context,
            rollback_trigger_class_id=rollback_trigger_class_id,
            rollback_trigger_context=rollback_trigger_context,
            release_watch_discipline_class_id=release_watch_discipline_class_id,
            release_watch_discipline_context=release_watch_discipline_context,
            release_confirmation_class_id=release_confirmation_class_id,
            release_confirmation_context=release_confirmation_context,
            production_entitlement_check_class_id=(
                production_entitlement_check_class_id
            ),
            production_entitlement_check_context=production_entitlement_check_context,
            contained_rollback_class_id=contained_rollback_class_id,
            contained_rollback_context=contained_rollback_context,
            release_audit_trace_class_id=release_audit_trace_class_id,
            release_audit_trace_context=release_audit_trace_context,
        )
        now = datetime.now(tz=UTC)
        episode = CaseEpisode(
            episode_id=episode_id,
            case_type=case_type,
            case_key=case_key,
            state_model_name=case_type_definition.state_model_name,
            current_state=initial_state.current_state,
            status=initial_state.resulting_status,
            current_stage=case_type_definition.initial_stage,
            opened_at=now,
            last_updated_at=now,
            raw_record_ids=tuple(raw_record_ids),
            feature_names=tuple(feature_names),
            interruption_reason=None,
            handoffs=(),
        )
        self._persist_episode(episode, correlation_id=correlation_id, actor_id=actor_id)
        self._audit_event_store.record_event(
            event_type="decision.case.episode_opened",
            owner="decision.case.case_episode_orchestrator",
            correlation_id=correlation_id,
            entity_type="case_episode",
            entity_id=episode.episode_id,
            actor_id=actor_id,
            payload={
                "case_type": case_type,
                "case_key": case_key,
                "initial_stage": case_type_definition.initial_stage,
                "initial_state": initial_state.current_state,
                "route_name": initial_state.route_name,
                "routing_review_required": initial_state.routing_review_required,
                "review_outcome": initial_state.review_outcome,
                **self._review_payload(
                    review_mode=initial_state.review_mode,
                    review_threshold_id=initial_state.review_threshold_id,
                    review_playbook_reference=initial_state.review_playbook_reference,
                ),
                **self._review_packet_payload(
                    review_packet_status=initial_state.review_packet_status,
                    review_packet_handoff_ready=initial_state.review_packet_handoff_ready,
                    review_packet_id=initial_state.review_packet_id,
                    review_packet_template_id=initial_state.review_packet_template_id,
                    review_packet_reason_class=initial_state.review_packet_reason_class,
                    review_packet_scope=initial_state.review_packet_scope,
                    review_packet_handoff_channel=initial_state.review_packet_handoff_channel,
                ),
                **self._review_resolution_payload(
                    review_resolution_status=initial_state.review_resolution_status,
                    review_resolution_id=initial_state.review_resolution_id,
                    review_resolution_class_id=initial_state.review_resolution_class_id,
                    review_resolution_outcome=initial_state.review_resolution_outcome,
                    review_resolution_state=initial_state.review_resolution_state,
                    review_disposition_class_id=initial_state.review_disposition_class_id,
                    review_disposition_state=initial_state.review_disposition_state,
                    review_closure_state=initial_state.review_closure_state,
                    review_closure_quality=initial_state.review_closure_quality,
                    review_resolution_terminality=initial_state.review_resolution_terminality,
                ),
                **self._recommendation_payload(
                    recommendation_status=initial_state.recommendation_status,
                    recommendation_id=initial_state.recommendation_id,
                    recommendation_class_id=initial_state.recommendation_class_id,
                    recommendation_template_id=initial_state.recommendation_template_id,
                    recommendation_action_class=initial_state.recommendation_action_class,
                    recommendation_advisory_status=initial_state.recommendation_advisory_status,
                    recommendation_commitment_readiness=(
                        initial_state.recommendation_commitment_readiness
                    ),
                ),
                **self._policy_output_payload(
                    policy_output_status=initial_state.policy_output_status,
                    policy_output_id=initial_state.policy_output_id,
                    policy_output_class_id=initial_state.policy_output_class_id,
                    policy_output_template_id=initial_state.policy_output_template_id,
                    policy_output_bounded_policy_posture=(
                        initial_state.policy_output_bounded_policy_posture
                    ),
                    policy_output_action_boundary_posture=(
                        initial_state.policy_output_action_boundary_posture
                    ),
                    policy_output_promotion_safe_use=(
                        initial_state.policy_output_promotion_safe_use
                    ),
                ),
                **self._portfolio_output_payload(
                    portfolio_output_status=initial_state.portfolio_output_status,
                    portfolio_output_id=initial_state.portfolio_output_id,
                    portfolio_output_class_id=initial_state.portfolio_output_class_id,
                    portfolio_output_template_id=(
                        initial_state.portfolio_output_template_id
                    ),
                    portfolio_output_allocation_posture=(
                        initial_state.portfolio_output_allocation_posture
                    ),
                    portfolio_output_weight_posture=(
                        initial_state.portfolio_output_weight_posture
                    ),
                    portfolio_output_action_boundary_posture=(
                        initial_state.portfolio_output_action_boundary_posture
                    ),
                    portfolio_output_promotion_safe_use=(
                        initial_state.portfolio_output_promotion_safe_use
                    ),
                ),
                **self._action_instruction_payload(
                    action_instruction_status=initial_state.action_instruction_status,
                    action_instruction_id=initial_state.action_instruction_id,
                    action_instruction_class_id=(
                        initial_state.action_instruction_class_id
                    ),
                    action_instruction_template_id=(
                        initial_state.action_instruction_template_id
                    ),
                    action_instruction_instruction_status=(
                        initial_state.action_instruction_instruction_status
                    ),
                    action_instruction_bounded_action_posture=(
                        initial_state.action_instruction_bounded_action_posture
                    ),
                    action_instruction_execution_boundary_posture=(
                        initial_state.action_instruction_execution_boundary_posture
                    ),
                    action_instruction_promotion_safe_use=(
                        initial_state.action_instruction_promotion_safe_use
                    ),
                ),
                **self._execution_request_payload(
                    execution_request_status=initial_state.execution_request_status,
                    execution_request_id=initial_state.execution_request_id,
                    execution_request_class_id=(
                        initial_state.execution_request_class_id
                    ),
                    execution_request_template_id=(
                        initial_state.execution_request_template_id
                    ),
                    execution_request_readiness=(
                        initial_state.execution_request_readiness
                    ),
                    execution_request_action_boundary_posture=(
                        initial_state.execution_request_action_boundary_posture
                    ),
                ),
                **self._execution_dispatch_payload(
                    execution_dispatch_status=initial_state.execution_dispatch_status,
                    execution_dispatch_id=initial_state.execution_dispatch_id,
                    execution_dispatch_class_id=(
                        initial_state.execution_dispatch_class_id
                    ),
                    execution_dispatch_template_id=(
                        initial_state.execution_dispatch_template_id
                    ),
                    execution_dispatch_readiness=(
                        initial_state.execution_dispatch_readiness
                    ),
                    execution_dispatch_boundary_posture=(
                        initial_state.execution_dispatch_boundary_posture
                    ),
                ),
                **self._execution_outcome_payload(
                    execution_outcome_status=initial_state.execution_outcome_status,
                    execution_outcome_id=initial_state.execution_outcome_id,
                    execution_outcome_class_id=(
                        initial_state.execution_outcome_class_id
                    ),
                    execution_outcome_template_id=(
                        initial_state.execution_outcome_template_id
                    ),
                    execution_outcome_realized_result_class=(
                        initial_state.execution_outcome_realized_result_class
                    ),
                    execution_outcome_feedback_capture_readiness=(
                        initial_state.execution_outcome_feedback_capture_readiness
                    ),
                    execution_outcome_expected_relation=(
                        initial_state.execution_outcome_expected_relation
                    ),
                    execution_outcome_comparison_posture=(
                        initial_state.execution_outcome_comparison_posture
                    ),
                ),
                **self._post_mortem_payload(
                    post_mortem_judgment_status=(
                        initial_state.post_mortem_judgment_status
                    ),
                    post_mortem_judgment_id=initial_state.post_mortem_judgment_id,
                    post_mortem_judgment_class_id=(
                        initial_state.post_mortem_judgment_class_id
                    ),
                    post_mortem_judgment_template_id=(
                        initial_state.post_mortem_judgment_template_id
                    ),
                    post_mortem_primary_attribution_category=(
                        initial_state.post_mortem_primary_attribution_category
                    ),
                    post_mortem_evidence_quality=(
                        initial_state.post_mortem_evidence_quality
                    ),
                    post_mortem_confidence_posture=(
                        initial_state.post_mortem_confidence_posture
                    ),
                    post_mortem_learning_direction=(
                        initial_state.post_mortem_learning_direction
                    ),
                    post_mortem_comparison_posture=(
                        initial_state.post_mortem_comparison_posture
                    ),
                ),
                **self._policy_learning_evidence_payload(
                    policy_learning_evidence_admission_status=(
                        initial_state.policy_learning_evidence_admission_status
                    ),
                    policy_learning_evidence_admission_id=(
                        initial_state.policy_learning_evidence_admission_id
                    ),
                    policy_learning_evidence_class_id=(
                        initial_state.policy_learning_evidence_class_id
                    ),
                    policy_learning_evidence_template_id=(
                        initial_state.policy_learning_evidence_template_id
                    ),
                    policy_learning_evidence_admission_context=(
                        initial_state.policy_learning_evidence_admission_context
                    ),
                ),
                **self._policy_learning_update_threshold_payload(
                    policy_learning_update_threshold_status=(
                        initial_state.policy_learning_update_threshold_status
                    ),
                    policy_learning_update_threshold_id=(
                        initial_state.policy_learning_update_threshold_id
                    ),
                    policy_learning_update_threshold_class_id=(
                        initial_state.policy_learning_update_threshold_class_id
                    ),
                    policy_learning_update_threshold_template_id=(
                        initial_state.policy_learning_update_threshold_template_id
                    ),
                    policy_learning_update_threshold_context=(
                        initial_state.policy_learning_update_threshold_context
                    ),
                ),
                **self._policy_learning_update_approval_payload(
                    policy_learning_update_approval_status=(
                        initial_state.policy_learning_update_approval_status
                    ),
                    policy_learning_update_approval_class_id=(
                        initial_state.policy_learning_update_approval_class_id
                    ),
                    policy_learning_update_approval_context=(
                        initial_state.policy_learning_update_approval_context
                    ),
                ),
                **self._policy_learning_update_preparation_payload(
                    policy_learning_update_preparation_status=(
                        initial_state.policy_learning_update_preparation_status
                    ),
                    policy_learning_update_preparation_class_id=(
                        initial_state.policy_learning_update_preparation_class_id
                    ),
                    policy_learning_update_preparation_context=(
                        initial_state.policy_learning_update_preparation_context
                    ),
                ),
                **self._policy_learning_update_mutation_planning_payload(
                    policy_learning_update_mutation_planning_status=(
                        initial_state.policy_learning_update_mutation_planning_status
                    ),
                    policy_learning_update_mutation_planning_class_id=(
                        initial_state.policy_learning_update_mutation_planning_class_id
                    ),
                    policy_learning_update_mutation_planning_context=(
                        initial_state.policy_learning_update_mutation_planning_context
                    ),
                ),
                **self._policy_learning_update_mutation_execution_payload(
                    policy_learning_update_mutation_execution_status=(
                        initial_state.policy_learning_update_mutation_execution_status
                    ),
                    policy_learning_update_mutation_execution_class_id=(
                        initial_state.policy_learning_update_mutation_execution_class_id
                    ),
                    policy_learning_update_mutation_execution_context=(
                        initial_state.policy_learning_update_mutation_execution_context
                    ),
                ),
                **self._promotion_readiness_payload(
                    promotion_readiness_status=(
                        initial_state.promotion_readiness_status
                    ),
                    promotion_readiness_class_id=(
                        initial_state.promotion_readiness_class_id
                    ),
                    promotion_readiness_context=(
                        initial_state.promotion_readiness_context
                    ),
                ),
                **self._rollout_scope_payload(
                    rollout_scope_status=initial_state.rollout_scope_status,
                    rollout_scope_class_id=initial_state.rollout_scope_class_id,
                    rollout_scope_context=initial_state.rollout_scope_context,
                ),
                **self._rollback_trigger_payload(
                    rollback_trigger_status=initial_state.rollback_trigger_status,
                    rollback_trigger_class_id=initial_state.rollback_trigger_class_id,
                    rollback_trigger_context=initial_state.rollback_trigger_context,
                ),
                **self._release_watch_discipline_payload(
                    release_watch_discipline_status=(
                        initial_state.release_watch_discipline_status
                    ),
                    release_watch_discipline_class_id=(
                        initial_state.release_watch_discipline_class_id
                    ),
                    release_watch_discipline_context=(
                        initial_state.release_watch_discipline_context
                    ),
                ),
                **self._release_confirmation_payload(
                    release_confirmation_status=(
                        initial_state.release_confirmation_status
                    ),
                    release_confirmation_class_id=(
                        initial_state.release_confirmation_class_id
                    ),
                    release_confirmation_context=(
                        initial_state.release_confirmation_context
                    ),
                ),
                **self._production_entitlement_check_payload(
                    production_entitlement_check_status=(
                        initial_state.production_entitlement_check_status
                    ),
                    production_entitlement_check_class_id=(
                        initial_state.production_entitlement_check_class_id
                    ),
                    production_entitlement_check_context=(
                        initial_state.production_entitlement_check_context
                    ),
                ),
                **self._contained_rollback_payload(
                    contained_rollback_status=(
                        initial_state.contained_rollback_status
                    ),
                    contained_rollback_class_id=(
                        initial_state.contained_rollback_class_id
                    ),
                    contained_rollback_context=(
                        initial_state.contained_rollback_context
                    ),
                ),
                **self._release_audit_trace_payload(
                    release_audit_trace_status=(
                        initial_state.release_audit_trace_status
                    ),
                    release_audit_trace_class_id=(
                        initial_state.release_audit_trace_class_id
                    ),
                    release_audit_trace_context=(
                        initial_state.release_audit_trace_context
                    ),
                ),
            },
            tags=("case-episode", case_type),
        )
        return episode

    def record_handoff(
        self,
        episode_id: str,
        *,
        to_stage: str,
        transition_name: str,
        reason: str,
        correlation_id: str,
        actor_id: str,
        actor_role: str,
        threshold_context: Mapping[str, object] | None = None,
        packet_context: Mapping[str, object] | None = None,
        review_resolution_class_id: str | None = None,
        review_resolution_context: Mapping[str, object] | None = None,
        recommendation_class_id: str | None = None,
        recommendation_context: Mapping[str, object] | None = None,
        policy_output_class_id: str | None = None,
        policy_output_context: Mapping[str, object] | None = None,
        portfolio_output_class_id: str | None = None,
        portfolio_output_context: Mapping[str, object] | None = None,
        action_instruction_class_id: str | None = None,
        action_instruction_context: Mapping[str, object] | None = None,
        execution_request_class_id: str | None = None,
        execution_request_context: Mapping[str, object] | None = None,
        execution_dispatch_class_id: str | None = None,
        execution_dispatch_context: Mapping[str, object] | None = None,
        execution_outcome_class_id: str | None = None,
        execution_outcome_context: Mapping[str, object] | None = None,
        post_mortem_judgment_class_id: str | None = None,
        post_mortem_judgment_context: Mapping[str, object] | None = None,
        policy_learning_evidence_class_id: str | None = None,
        policy_learning_evidence_admission_context: Mapping[str, object] | None = None,
        policy_learning_update_threshold_class_id: str | None = None,
        policy_learning_update_threshold_context: Mapping[str, object] | None = None,
        policy_learning_update_approval_class_id: str | None = None,
        policy_learning_update_approval_context: Mapping[str, object] | None = None,
        policy_learning_update_preparation_class_id: str | None = None,
        policy_learning_update_preparation_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_planning_class_id: str | None = None,
        policy_learning_update_mutation_planning_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_execution_class_id: str | None = None,
        policy_learning_update_mutation_execution_context: Mapping[str, object] | None = None,
        promotion_readiness_class_id: str | None = None,
        promotion_readiness_context: Mapping[str, object] | None = None,
        rollout_scope_class_id: str | None = None,
        rollout_scope_context: Mapping[str, object] | None = None,
        rollback_trigger_class_id: str | None = None,
        rollback_trigger_context: Mapping[str, object] | None = None,
        release_watch_discipline_class_id: str | None = None,
        release_watch_discipline_context: Mapping[str, object] | None = None,
        release_confirmation_class_id: str | None = None,
        release_confirmation_context: Mapping[str, object] | None = None,
        production_entitlement_check_class_id: str | None = None,
        production_entitlement_check_context: Mapping[str, object] | None = None,
        contained_rollback_class_id: str | None = None,
        contained_rollback_context: Mapping[str, object] | None = None,
        release_audit_trace_class_id: str | None = None,
        release_audit_trace_context: Mapping[str, object] | None = None,
    ) -> CaseEpisode:
        episode = self._require_episode(episode_id)
        if episode.status != "active":
            raise HandoffValidationError(
                f"Episode '{episode_id}' is not active and cannot be handed off."
            )

        case_type_definition = self._case_type_registry.get_case_type(episode.case_type)
        allowed_targets = case_type_definition.allowed_stage_transitions.get(episode.current_stage, ())
        if to_stage not in allowed_targets:
            raise HandoffValidationError(
                f"Stage '{episode.current_stage}' cannot hand off to '{to_stage}'."
            )

        state_result = self._state_manager.apply_transition(
            case_type=episode.case_type,
            case_key=episode.case_key,
            state_model_name=episode.state_model_name,
            current_state=episode.current_state,
            current_status=episode.status,
            transition_name=transition_name,
            source_stage=episode.current_stage,
            target_stage=to_stage,
            correlation_id=correlation_id,
            episode_id=episode_id,
            actor_id=actor_id,
            actor_role=actor_role,
            threshold_context=threshold_context,
            packet_context=packet_context,
            reason=reason,
            review_resolution_class_id=review_resolution_class_id,
            review_resolution_context=review_resolution_context,
            recommendation_class_id=recommendation_class_id,
            recommendation_context=recommendation_context,
            policy_output_class_id=policy_output_class_id,
            policy_output_context=policy_output_context,
            portfolio_output_class_id=portfolio_output_class_id,
            portfolio_output_context=portfolio_output_context,
            action_instruction_class_id=action_instruction_class_id,
            action_instruction_context=action_instruction_context,
            execution_request_class_id=execution_request_class_id,
            execution_request_context=execution_request_context,
            execution_dispatch_class_id=execution_dispatch_class_id,
            execution_dispatch_context=execution_dispatch_context,
            execution_outcome_class_id=execution_outcome_class_id,
            execution_outcome_context=execution_outcome_context,
            post_mortem_judgment_class_id=post_mortem_judgment_class_id,
            post_mortem_judgment_context=post_mortem_judgment_context,
            policy_learning_evidence_class_id=policy_learning_evidence_class_id,
            policy_learning_evidence_admission_context=(
                policy_learning_evidence_admission_context
            ),
            policy_learning_update_threshold_class_id=(
                policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_context=(
                policy_learning_update_threshold_context
            ),
            policy_learning_update_approval_class_id=(
                policy_learning_update_approval_class_id
            ),
            policy_learning_update_approval_context=(
                policy_learning_update_approval_context
            ),
            policy_learning_update_preparation_class_id=(
                policy_learning_update_preparation_class_id
            ),
            policy_learning_update_preparation_context=(
                policy_learning_update_preparation_context
            ),
            policy_learning_update_mutation_planning_class_id=(
                policy_learning_update_mutation_planning_class_id
            ),
            policy_learning_update_mutation_planning_context=(
                policy_learning_update_mutation_planning_context
            ),
            policy_learning_update_mutation_execution_class_id=(
                policy_learning_update_mutation_execution_class_id
            ),
            policy_learning_update_mutation_execution_context=(
                policy_learning_update_mutation_execution_context
            ),
            promotion_readiness_class_id=promotion_readiness_class_id,
            promotion_readiness_context=promotion_readiness_context,
            rollout_scope_class_id=rollout_scope_class_id,
            rollout_scope_context=rollout_scope_context,
            rollback_trigger_class_id=rollback_trigger_class_id,
            rollback_trigger_context=rollback_trigger_context,
            release_watch_discipline_class_id=release_watch_discipline_class_id,
            release_watch_discipline_context=release_watch_discipline_context,
            release_confirmation_class_id=release_confirmation_class_id,
            release_confirmation_context=release_confirmation_context,
            production_entitlement_check_class_id=(
                production_entitlement_check_class_id
            ),
            production_entitlement_check_context=production_entitlement_check_context,
            contained_rollback_class_id=contained_rollback_class_id,
            contained_rollback_context=contained_rollback_context,
            release_audit_trace_class_id=release_audit_trace_class_id,
            release_audit_trace_context=release_audit_trace_context,
        )
        handoff = CaseHandoffRecord(
            from_stage=episode.current_stage,
            to_stage=to_stage,
            reason=reason,
            actor_id=actor_id,
            occurred_at=datetime.now(tz=UTC),
        )
        updated = replace(
            episode,
            current_stage=to_stage,
            current_state=state_result.to_state,
            status=state_result.resulting_status,
            interruption_reason=state_result.next_interruption_reason,
            last_updated_at=handoff.occurred_at,
            handoffs=episode.handoffs + (handoff,),
        )
        self._persist_episode(updated, correlation_id=correlation_id, actor_id=actor_id)
        self._audit_event_store.record_event(
            event_type="decision.case.handoff_recorded",
            owner="decision.case.case_episode_orchestrator",
            correlation_id=correlation_id,
            entity_type="case_episode",
            entity_id=episode_id,
            actor_id=actor_id,
            payload={
                **handoff.to_contract_dict(),
                "route_name": state_result.route_name,
                "routing_review_required": state_result.routing_review_required,
                "routing_resolution_status": state_result.routing_resolution_status,
                "review_outcome": state_result.review_outcome,
                **self._review_payload(
                    review_mode=state_result.review_mode,
                    review_threshold_id=state_result.review_threshold_id,
                    review_playbook_reference=state_result.review_playbook_reference,
                ),
                **self._review_packet_payload(
                    review_packet_status=state_result.review_packet_status,
                    review_packet_handoff_ready=state_result.review_packet_handoff_ready,
                    review_packet_id=state_result.review_packet_id,
                    review_packet_template_id=state_result.review_packet_template_id,
                    review_packet_reason_class=state_result.review_packet_reason_class,
                    review_packet_scope=state_result.review_packet_scope,
                    review_packet_handoff_channel=state_result.review_packet_handoff_channel,
                ),
                **self._review_resolution_payload(
                    review_resolution_status=state_result.review_resolution_status,
                    review_resolution_id=state_result.review_resolution_id,
                    review_resolution_class_id=state_result.review_resolution_class_id,
                    review_resolution_outcome=state_result.review_resolution_outcome,
                    review_resolution_state=state_result.review_resolution_state,
                    review_disposition_class_id=state_result.review_disposition_class_id,
                    review_disposition_state=state_result.review_disposition_state,
                    review_closure_state=state_result.review_closure_state,
                    review_closure_quality=state_result.review_closure_quality,
                    review_resolution_terminality=state_result.review_resolution_terminality,
                ),
                **self._recommendation_payload(
                    recommendation_status=state_result.recommendation_status,
                    recommendation_id=state_result.recommendation_id,
                    recommendation_class_id=state_result.recommendation_class_id,
                    recommendation_template_id=state_result.recommendation_template_id,
                    recommendation_action_class=state_result.recommendation_action_class,
                    recommendation_advisory_status=state_result.recommendation_advisory_status,
                    recommendation_commitment_readiness=(
                        state_result.recommendation_commitment_readiness
                    ),
                ),
                **self._policy_output_payload(
                    policy_output_status=state_result.policy_output_status,
                    policy_output_id=state_result.policy_output_id,
                    policy_output_class_id=state_result.policy_output_class_id,
                    policy_output_template_id=state_result.policy_output_template_id,
                    policy_output_bounded_policy_posture=(
                        state_result.policy_output_bounded_policy_posture
                    ),
                    policy_output_action_boundary_posture=(
                        state_result.policy_output_action_boundary_posture
                    ),
                    policy_output_promotion_safe_use=(
                        state_result.policy_output_promotion_safe_use
                    ),
                ),
                **self._portfolio_output_payload(
                    portfolio_output_status=state_result.portfolio_output_status,
                    portfolio_output_id=state_result.portfolio_output_id,
                    portfolio_output_class_id=state_result.portfolio_output_class_id,
                    portfolio_output_template_id=(
                        state_result.portfolio_output_template_id
                    ),
                    portfolio_output_allocation_posture=(
                        state_result.portfolio_output_allocation_posture
                    ),
                    portfolio_output_weight_posture=(
                        state_result.portfolio_output_weight_posture
                    ),
                    portfolio_output_action_boundary_posture=(
                        state_result.portfolio_output_action_boundary_posture
                    ),
                    portfolio_output_promotion_safe_use=(
                        state_result.portfolio_output_promotion_safe_use
                    ),
                ),
                **self._action_instruction_payload(
                    action_instruction_status=state_result.action_instruction_status,
                    action_instruction_id=state_result.action_instruction_id,
                    action_instruction_class_id=(
                        state_result.action_instruction_class_id
                    ),
                    action_instruction_template_id=(
                        state_result.action_instruction_template_id
                    ),
                    action_instruction_instruction_status=(
                        state_result.action_instruction_instruction_status
                    ),
                    action_instruction_bounded_action_posture=(
                        state_result.action_instruction_bounded_action_posture
                    ),
                    action_instruction_execution_boundary_posture=(
                        state_result.action_instruction_execution_boundary_posture
                    ),
                    action_instruction_promotion_safe_use=(
                        state_result.action_instruction_promotion_safe_use
                    ),
                ),
                **self._execution_request_payload(
                    execution_request_status=state_result.execution_request_status,
                    execution_request_id=state_result.execution_request_id,
                    execution_request_class_id=(
                        state_result.execution_request_class_id
                    ),
                    execution_request_template_id=(
                        state_result.execution_request_template_id
                    ),
                    execution_request_readiness=(
                        state_result.execution_request_readiness
                    ),
                    execution_request_action_boundary_posture=(
                        state_result.execution_request_action_boundary_posture
                    ),
                ),
                **self._execution_dispatch_payload(
                    execution_dispatch_status=state_result.execution_dispatch_status,
                    execution_dispatch_id=state_result.execution_dispatch_id,
                    execution_dispatch_class_id=(
                        state_result.execution_dispatch_class_id
                    ),
                    execution_dispatch_template_id=(
                        state_result.execution_dispatch_template_id
                    ),
                    execution_dispatch_readiness=(
                        state_result.execution_dispatch_readiness
                    ),
                    execution_dispatch_boundary_posture=(
                        state_result.execution_dispatch_boundary_posture
                    ),
                ),
                **self._execution_outcome_payload(
                    execution_outcome_status=state_result.execution_outcome_status,
                    execution_outcome_id=state_result.execution_outcome_id,
                    execution_outcome_class_id=(
                        state_result.execution_outcome_class_id
                    ),
                    execution_outcome_template_id=(
                        state_result.execution_outcome_template_id
                    ),
                    execution_outcome_realized_result_class=(
                        state_result.execution_outcome_realized_result_class
                    ),
                    execution_outcome_feedback_capture_readiness=(
                        state_result.execution_outcome_feedback_capture_readiness
                    ),
                    execution_outcome_expected_relation=(
                        state_result.execution_outcome_expected_relation
                    ),
                    execution_outcome_comparison_posture=(
                        state_result.execution_outcome_comparison_posture
                    ),
                ),
                **self._post_mortem_payload(
                    post_mortem_judgment_status=(
                        state_result.post_mortem_judgment_status
                    ),
                    post_mortem_judgment_id=state_result.post_mortem_judgment_id,
                    post_mortem_judgment_class_id=(
                        state_result.post_mortem_judgment_class_id
                    ),
                    post_mortem_judgment_template_id=(
                        state_result.post_mortem_judgment_template_id
                    ),
                    post_mortem_primary_attribution_category=(
                        state_result.post_mortem_primary_attribution_category
                    ),
                    post_mortem_evidence_quality=(
                        state_result.post_mortem_evidence_quality
                    ),
                    post_mortem_confidence_posture=(
                        state_result.post_mortem_confidence_posture
                    ),
                    post_mortem_learning_direction=(
                        state_result.post_mortem_learning_direction
                    ),
                    post_mortem_comparison_posture=(
                        state_result.post_mortem_comparison_posture
                    ),
                ),
                **self._policy_learning_evidence_payload(
                    policy_learning_evidence_admission_status=(
                        state_result.policy_learning_evidence_admission_status
                    ),
                    policy_learning_evidence_admission_id=(
                        state_result.policy_learning_evidence_admission_id
                    ),
                    policy_learning_evidence_class_id=(
                        state_result.policy_learning_evidence_class_id
                    ),
                    policy_learning_evidence_template_id=(
                        state_result.policy_learning_evidence_template_id
                    ),
                    policy_learning_evidence_admission_context=(
                        state_result.policy_learning_evidence_admission_context
                    ),
                ),
                **self._policy_learning_update_threshold_payload(
                    policy_learning_update_threshold_status=(
                        state_result.policy_learning_update_threshold_status
                    ),
                    policy_learning_update_threshold_id=(
                        state_result.policy_learning_update_threshold_id
                    ),
                    policy_learning_update_threshold_class_id=(
                        state_result.policy_learning_update_threshold_class_id
                    ),
                    policy_learning_update_threshold_template_id=(
                        state_result.policy_learning_update_threshold_template_id
                    ),
                    policy_learning_update_threshold_context=(
                        state_result.policy_learning_update_threshold_context
                    ),
                ),
                **self._policy_learning_update_approval_payload(
                    policy_learning_update_approval_status=(
                        state_result.policy_learning_update_approval_status
                    ),
                    policy_learning_update_approval_class_id=(
                        state_result.policy_learning_update_approval_class_id
                    ),
                    policy_learning_update_approval_context=(
                        state_result.policy_learning_update_approval_context
                    ),
                ),
                **self._policy_learning_update_preparation_payload(
                    policy_learning_update_preparation_status=(
                        state_result.policy_learning_update_preparation_status
                    ),
                    policy_learning_update_preparation_class_id=(
                        state_result.policy_learning_update_preparation_class_id
                    ),
                    policy_learning_update_preparation_context=(
                        state_result.policy_learning_update_preparation_context
                    ),
                ),
                **self._policy_learning_update_mutation_planning_payload(
                    policy_learning_update_mutation_planning_status=(
                        state_result.policy_learning_update_mutation_planning_status
                    ),
                    policy_learning_update_mutation_planning_class_id=(
                        state_result.policy_learning_update_mutation_planning_class_id
                    ),
                    policy_learning_update_mutation_planning_context=(
                        state_result.policy_learning_update_mutation_planning_context
                    ),
                ),
                **self._policy_learning_update_mutation_execution_payload(
                    policy_learning_update_mutation_execution_status=(
                        state_result.policy_learning_update_mutation_execution_status
                    ),
                    policy_learning_update_mutation_execution_class_id=(
                        state_result.policy_learning_update_mutation_execution_class_id
                    ),
                    policy_learning_update_mutation_execution_context=(
                        state_result.policy_learning_update_mutation_execution_context
                    ),
                ),
                **self._promotion_readiness_payload(
                    promotion_readiness_status=(
                        state_result.promotion_readiness_status
                    ),
                    promotion_readiness_class_id=(
                        state_result.promotion_readiness_class_id
                    ),
                    promotion_readiness_context=(
                        state_result.promotion_readiness_context
                    ),
                ),
                **self._rollout_scope_payload(
                    rollout_scope_status=state_result.rollout_scope_status,
                    rollout_scope_class_id=state_result.rollout_scope_class_id,
                    rollout_scope_context=state_result.rollout_scope_context,
                ),
                **self._rollback_trigger_payload(
                    rollback_trigger_status=state_result.rollback_trigger_status,
                    rollback_trigger_class_id=state_result.rollback_trigger_class_id,
                    rollback_trigger_context=state_result.rollback_trigger_context,
                ),
                **self._release_watch_discipline_payload(
                    release_watch_discipline_status=(
                        state_result.release_watch_discipline_status
                    ),
                    release_watch_discipline_class_id=(
                        state_result.release_watch_discipline_class_id
                    ),
                    release_watch_discipline_context=(
                        state_result.release_watch_discipline_context
                    ),
                ),
                **self._release_confirmation_payload(
                    release_confirmation_status=(
                        state_result.release_confirmation_status
                    ),
                    release_confirmation_class_id=(
                        state_result.release_confirmation_class_id
                    ),
                    release_confirmation_context=(
                        state_result.release_confirmation_context
                    ),
                ),
                **self._production_entitlement_check_payload(
                    production_entitlement_check_status=(
                        state_result.production_entitlement_check_status
                    ),
                    production_entitlement_check_class_id=(
                        state_result.production_entitlement_check_class_id
                    ),
                    production_entitlement_check_context=(
                        state_result.production_entitlement_check_context
                    ),
                ),
                **self._contained_rollback_payload(
                    contained_rollback_status=state_result.contained_rollback_status,
                    contained_rollback_class_id=(
                        state_result.contained_rollback_class_id
                    ),
                    contained_rollback_context=(
                        state_result.contained_rollback_context
                    ),
                ),
                **self._release_audit_trace_payload(
                    release_audit_trace_status=(
                        state_result.release_audit_trace_status
                    ),
                    release_audit_trace_class_id=(
                        state_result.release_audit_trace_class_id
                    ),
                    release_audit_trace_context=(
                        state_result.release_audit_trace_context
                    ),
                ),
            },
            tags=("case-episode", "handoff"),
        )
        return updated

    def interrupt_episode(
        self,
        episode_id: str,
        *,
        transition_name: str,
        reason: str,
        correlation_id: str,
        actor_id: str,
        actor_role: str,
        threshold_context: Mapping[str, object] | None = None,
        packet_context: Mapping[str, object] | None = None,
        review_resolution_class_id: str | None = None,
        review_resolution_context: Mapping[str, object] | None = None,
        recommendation_class_id: str | None = None,
        recommendation_context: Mapping[str, object] | None = None,
        policy_output_class_id: str | None = None,
        policy_output_context: Mapping[str, object] | None = None,
        portfolio_output_class_id: str | None = None,
        portfolio_output_context: Mapping[str, object] | None = None,
        action_instruction_class_id: str | None = None,
        action_instruction_context: Mapping[str, object] | None = None,
        execution_request_class_id: str | None = None,
        execution_request_context: Mapping[str, object] | None = None,
        execution_dispatch_class_id: str | None = None,
        execution_dispatch_context: Mapping[str, object] | None = None,
        execution_outcome_class_id: str | None = None,
        execution_outcome_context: Mapping[str, object] | None = None,
        post_mortem_judgment_class_id: str | None = None,
        post_mortem_judgment_context: Mapping[str, object] | None = None,
        policy_learning_evidence_class_id: str | None = None,
        policy_learning_evidence_admission_context: Mapping[str, object] | None = None,
        policy_learning_update_threshold_class_id: str | None = None,
        policy_learning_update_threshold_context: Mapping[str, object] | None = None,
        policy_learning_update_approval_class_id: str | None = None,
        policy_learning_update_approval_context: Mapping[str, object] | None = None,
        policy_learning_update_preparation_class_id: str | None = None,
        policy_learning_update_preparation_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_planning_class_id: str | None = None,
        policy_learning_update_mutation_planning_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_execution_class_id: str | None = None,
        policy_learning_update_mutation_execution_context: Mapping[str, object] | None = None,
        promotion_readiness_class_id: str | None = None,
        promotion_readiness_context: Mapping[str, object] | None = None,
        rollout_scope_class_id: str | None = None,
        rollout_scope_context: Mapping[str, object] | None = None,
        rollback_trigger_class_id: str | None = None,
        rollback_trigger_context: Mapping[str, object] | None = None,
        release_watch_discipline_class_id: str | None = None,
        release_watch_discipline_context: Mapping[str, object] | None = None,
        release_confirmation_class_id: str | None = None,
        release_confirmation_context: Mapping[str, object] | None = None,
        production_entitlement_check_class_id: str | None = None,
        production_entitlement_check_context: Mapping[str, object] | None = None,
        contained_rollback_class_id: str | None = None,
        contained_rollback_context: Mapping[str, object] | None = None,
        release_audit_trace_class_id: str | None = None,
        release_audit_trace_context: Mapping[str, object] | None = None,
    ) -> CaseEpisode:
        episode = self._require_episode(episode_id)
        if episode.status == "interrupted":
            raise EpisodeEntryValidationError(f"Episode '{episode_id}' is already interrupted.")

        state_result = self._state_manager.apply_transition(
            case_type=episode.case_type,
            case_key=episode.case_key,
            state_model_name=episode.state_model_name,
            current_state=episode.current_state,
            current_status=episode.status,
            transition_name=transition_name,
            source_stage=episode.current_stage,
            target_stage=episode.current_stage,
            correlation_id=correlation_id,
            episode_id=episode_id,
            actor_id=actor_id,
            actor_role=actor_role,
            threshold_context=threshold_context,
            packet_context=packet_context,
            reason=reason,
            review_resolution_class_id=review_resolution_class_id,
            review_resolution_context=review_resolution_context,
            recommendation_class_id=recommendation_class_id,
            recommendation_context=recommendation_context,
            policy_output_class_id=policy_output_class_id,
            policy_output_context=policy_output_context,
            portfolio_output_class_id=portfolio_output_class_id,
            portfolio_output_context=portfolio_output_context,
            action_instruction_class_id=action_instruction_class_id,
            action_instruction_context=action_instruction_context,
            execution_request_class_id=execution_request_class_id,
            execution_request_context=execution_request_context,
            execution_dispatch_class_id=execution_dispatch_class_id,
            execution_dispatch_context=execution_dispatch_context,
            execution_outcome_class_id=execution_outcome_class_id,
            execution_outcome_context=execution_outcome_context,
            post_mortem_judgment_class_id=post_mortem_judgment_class_id,
            post_mortem_judgment_context=post_mortem_judgment_context,
            policy_learning_evidence_class_id=policy_learning_evidence_class_id,
            policy_learning_evidence_admission_context=(
                policy_learning_evidence_admission_context
            ),
            policy_learning_update_threshold_class_id=(
                policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_context=(
                policy_learning_update_threshold_context
            ),
            policy_learning_update_approval_class_id=(
                policy_learning_update_approval_class_id
            ),
            policy_learning_update_approval_context=(
                policy_learning_update_approval_context
            ),
            policy_learning_update_preparation_class_id=(
                policy_learning_update_preparation_class_id
            ),
            policy_learning_update_preparation_context=(
                policy_learning_update_preparation_context
            ),
            policy_learning_update_mutation_planning_class_id=(
                policy_learning_update_mutation_planning_class_id
            ),
            policy_learning_update_mutation_planning_context=(
                policy_learning_update_mutation_planning_context
            ),
            policy_learning_update_mutation_execution_class_id=(
                policy_learning_update_mutation_execution_class_id
            ),
            policy_learning_update_mutation_execution_context=(
                policy_learning_update_mutation_execution_context
            ),
            promotion_readiness_class_id=promotion_readiness_class_id,
            promotion_readiness_context=promotion_readiness_context,
            rollout_scope_class_id=rollout_scope_class_id,
            rollout_scope_context=rollout_scope_context,
            rollback_trigger_class_id=rollback_trigger_class_id,
            rollback_trigger_context=rollback_trigger_context,
            release_watch_discipline_class_id=release_watch_discipline_class_id,
            release_watch_discipline_context=release_watch_discipline_context,
            release_confirmation_class_id=release_confirmation_class_id,
            release_confirmation_context=release_confirmation_context,
            production_entitlement_check_class_id=(
                production_entitlement_check_class_id
            ),
            production_entitlement_check_context=production_entitlement_check_context,
            contained_rollback_class_id=contained_rollback_class_id,
            contained_rollback_context=contained_rollback_context,
            release_audit_trace_class_id=release_audit_trace_class_id,
            release_audit_trace_context=release_audit_trace_context,
        )
        updated = replace(
            episode,
            current_state=state_result.to_state,
            status=state_result.resulting_status,
            interruption_reason=state_result.next_interruption_reason,
            last_updated_at=datetime.now(tz=UTC),
        )
        self._persist_episode(updated, correlation_id=correlation_id, actor_id=actor_id)
        self._audit_event_store.record_event(
            event_type="decision.case.interruption_recorded",
            owner="decision.case.case_episode_orchestrator",
            correlation_id=correlation_id,
            entity_type="case_episode",
            entity_id=episode_id,
            actor_id=actor_id,
            payload={
                "reason": reason,
                "current_stage": episode.current_stage,
                "route_name": state_result.route_name,
                "routing_review_required": state_result.routing_review_required,
                "routing_resolution_status": state_result.routing_resolution_status,
                "review_outcome": state_result.review_outcome,
                **self._review_payload(
                    review_mode=state_result.review_mode,
                    review_threshold_id=state_result.review_threshold_id,
                    review_playbook_reference=state_result.review_playbook_reference,
                ),
                **self._review_packet_payload(
                    review_packet_status=state_result.review_packet_status,
                    review_packet_handoff_ready=state_result.review_packet_handoff_ready,
                    review_packet_id=state_result.review_packet_id,
                    review_packet_template_id=state_result.review_packet_template_id,
                    review_packet_reason_class=state_result.review_packet_reason_class,
                    review_packet_scope=state_result.review_packet_scope,
                    review_packet_handoff_channel=state_result.review_packet_handoff_channel,
                ),
                **self._review_resolution_payload(
                    review_resolution_status=state_result.review_resolution_status,
                    review_resolution_id=state_result.review_resolution_id,
                    review_resolution_class_id=state_result.review_resolution_class_id,
                    review_resolution_outcome=state_result.review_resolution_outcome,
                    review_resolution_state=state_result.review_resolution_state,
                    review_disposition_class_id=state_result.review_disposition_class_id,
                    review_disposition_state=state_result.review_disposition_state,
                    review_closure_state=state_result.review_closure_state,
                    review_closure_quality=state_result.review_closure_quality,
                    review_resolution_terminality=state_result.review_resolution_terminality,
                ),
                **self._recommendation_payload(
                    recommendation_status=state_result.recommendation_status,
                    recommendation_id=state_result.recommendation_id,
                    recommendation_class_id=state_result.recommendation_class_id,
                    recommendation_template_id=state_result.recommendation_template_id,
                    recommendation_action_class=state_result.recommendation_action_class,
                    recommendation_advisory_status=state_result.recommendation_advisory_status,
                    recommendation_commitment_readiness=(
                        state_result.recommendation_commitment_readiness
                    ),
                ),
                **self._policy_output_payload(
                    policy_output_status=state_result.policy_output_status,
                    policy_output_id=state_result.policy_output_id,
                    policy_output_class_id=state_result.policy_output_class_id,
                    policy_output_template_id=state_result.policy_output_template_id,
                    policy_output_bounded_policy_posture=(
                        state_result.policy_output_bounded_policy_posture
                    ),
                    policy_output_action_boundary_posture=(
                        state_result.policy_output_action_boundary_posture
                    ),
                    policy_output_promotion_safe_use=(
                        state_result.policy_output_promotion_safe_use
                    ),
                ),
                **self._portfolio_output_payload(
                    portfolio_output_status=state_result.portfolio_output_status,
                    portfolio_output_id=state_result.portfolio_output_id,
                    portfolio_output_class_id=state_result.portfolio_output_class_id,
                    portfolio_output_template_id=(
                        state_result.portfolio_output_template_id
                    ),
                    portfolio_output_allocation_posture=(
                        state_result.portfolio_output_allocation_posture
                    ),
                    portfolio_output_weight_posture=(
                        state_result.portfolio_output_weight_posture
                    ),
                    portfolio_output_action_boundary_posture=(
                        state_result.portfolio_output_action_boundary_posture
                    ),
                    portfolio_output_promotion_safe_use=(
                        state_result.portfolio_output_promotion_safe_use
                    ),
                ),
                **self._action_instruction_payload(
                    action_instruction_status=state_result.action_instruction_status,
                    action_instruction_id=state_result.action_instruction_id,
                    action_instruction_class_id=(
                        state_result.action_instruction_class_id
                    ),
                    action_instruction_template_id=(
                        state_result.action_instruction_template_id
                    ),
                    action_instruction_instruction_status=(
                        state_result.action_instruction_instruction_status
                    ),
                    action_instruction_bounded_action_posture=(
                        state_result.action_instruction_bounded_action_posture
                    ),
                    action_instruction_execution_boundary_posture=(
                        state_result.action_instruction_execution_boundary_posture
                    ),
                    action_instruction_promotion_safe_use=(
                        state_result.action_instruction_promotion_safe_use
                    ),
                ),
                **self._execution_request_payload(
                    execution_request_status=state_result.execution_request_status,
                    execution_request_id=state_result.execution_request_id,
                    execution_request_class_id=(
                        state_result.execution_request_class_id
                    ),
                    execution_request_template_id=(
                        state_result.execution_request_template_id
                    ),
                    execution_request_readiness=(
                        state_result.execution_request_readiness
                    ),
                    execution_request_action_boundary_posture=(
                        state_result.execution_request_action_boundary_posture
                    ),
                ),
                **self._execution_dispatch_payload(
                    execution_dispatch_status=state_result.execution_dispatch_status,
                    execution_dispatch_id=state_result.execution_dispatch_id,
                    execution_dispatch_class_id=(
                        state_result.execution_dispatch_class_id
                    ),
                    execution_dispatch_template_id=(
                        state_result.execution_dispatch_template_id
                    ),
                    execution_dispatch_readiness=(
                        state_result.execution_dispatch_readiness
                    ),
                    execution_dispatch_boundary_posture=(
                        state_result.execution_dispatch_boundary_posture
                    ),
                ),
                **self._execution_outcome_payload(
                    execution_outcome_status=state_result.execution_outcome_status,
                    execution_outcome_id=state_result.execution_outcome_id,
                    execution_outcome_class_id=(
                        state_result.execution_outcome_class_id
                    ),
                    execution_outcome_template_id=(
                        state_result.execution_outcome_template_id
                    ),
                    execution_outcome_realized_result_class=(
                        state_result.execution_outcome_realized_result_class
                    ),
                    execution_outcome_feedback_capture_readiness=(
                        state_result.execution_outcome_feedback_capture_readiness
                    ),
                    execution_outcome_expected_relation=(
                        state_result.execution_outcome_expected_relation
                    ),
                    execution_outcome_comparison_posture=(
                        state_result.execution_outcome_comparison_posture
                    ),
                ),
                **self._post_mortem_payload(
                    post_mortem_judgment_status=(
                        state_result.post_mortem_judgment_status
                    ),
                    post_mortem_judgment_id=state_result.post_mortem_judgment_id,
                    post_mortem_judgment_class_id=(
                        state_result.post_mortem_judgment_class_id
                    ),
                    post_mortem_judgment_template_id=(
                        state_result.post_mortem_judgment_template_id
                    ),
                    post_mortem_primary_attribution_category=(
                        state_result.post_mortem_primary_attribution_category
                    ),
                    post_mortem_evidence_quality=(
                        state_result.post_mortem_evidence_quality
                    ),
                    post_mortem_confidence_posture=(
                        state_result.post_mortem_confidence_posture
                    ),
                    post_mortem_learning_direction=(
                        state_result.post_mortem_learning_direction
                    ),
                    post_mortem_comparison_posture=(
                        state_result.post_mortem_comparison_posture
                    ),
                ),
                **self._policy_learning_evidence_payload(
                    policy_learning_evidence_admission_status=(
                        state_result.policy_learning_evidence_admission_status
                    ),
                    policy_learning_evidence_admission_id=(
                        state_result.policy_learning_evidence_admission_id
                    ),
                    policy_learning_evidence_class_id=(
                        state_result.policy_learning_evidence_class_id
                    ),
                    policy_learning_evidence_template_id=(
                        state_result.policy_learning_evidence_template_id
                    ),
                    policy_learning_evidence_admission_context=(
                        state_result.policy_learning_evidence_admission_context
                    ),
                ),
                **self._policy_learning_update_threshold_payload(
                    policy_learning_update_threshold_status=(
                        state_result.policy_learning_update_threshold_status
                    ),
                    policy_learning_update_threshold_id=(
                        state_result.policy_learning_update_threshold_id
                    ),
                    policy_learning_update_threshold_class_id=(
                        state_result.policy_learning_update_threshold_class_id
                    ),
                    policy_learning_update_threshold_template_id=(
                        state_result.policy_learning_update_threshold_template_id
                    ),
                    policy_learning_update_threshold_context=(
                        state_result.policy_learning_update_threshold_context
                    ),
                ),
                **self._policy_learning_update_approval_payload(
                    policy_learning_update_approval_status=(
                        state_result.policy_learning_update_approval_status
                    ),
                    policy_learning_update_approval_class_id=(
                        state_result.policy_learning_update_approval_class_id
                    ),
                    policy_learning_update_approval_context=(
                        state_result.policy_learning_update_approval_context
                    ),
                ),
                **self._policy_learning_update_preparation_payload(
                    policy_learning_update_preparation_status=(
                        state_result.policy_learning_update_preparation_status
                    ),
                    policy_learning_update_preparation_class_id=(
                        state_result.policy_learning_update_preparation_class_id
                    ),
                    policy_learning_update_preparation_context=(
                        state_result.policy_learning_update_preparation_context
                    ),
                ),
                **self._policy_learning_update_mutation_planning_payload(
                    policy_learning_update_mutation_planning_status=(
                        state_result.policy_learning_update_mutation_planning_status
                    ),
                    policy_learning_update_mutation_planning_class_id=(
                        state_result.policy_learning_update_mutation_planning_class_id
                    ),
                    policy_learning_update_mutation_planning_context=(
                        state_result.policy_learning_update_mutation_planning_context
                    ),
                ),
                **self._policy_learning_update_mutation_execution_payload(
                    policy_learning_update_mutation_execution_status=(
                        state_result.policy_learning_update_mutation_execution_status
                    ),
                    policy_learning_update_mutation_execution_class_id=(
                        state_result.policy_learning_update_mutation_execution_class_id
                    ),
                    policy_learning_update_mutation_execution_context=(
                        state_result.policy_learning_update_mutation_execution_context
                    ),
                ),
                **self._promotion_readiness_payload(
                    promotion_readiness_status=(
                        state_result.promotion_readiness_status
                    ),
                    promotion_readiness_class_id=(
                        state_result.promotion_readiness_class_id
                    ),
                    promotion_readiness_context=(
                        state_result.promotion_readiness_context
                    ),
                ),
                **self._rollout_scope_payload(
                    rollout_scope_status=state_result.rollout_scope_status,
                    rollout_scope_class_id=state_result.rollout_scope_class_id,
                    rollout_scope_context=state_result.rollout_scope_context,
                ),
                **self._rollback_trigger_payload(
                    rollback_trigger_status=state_result.rollback_trigger_status,
                    rollback_trigger_class_id=state_result.rollback_trigger_class_id,
                    rollback_trigger_context=state_result.rollback_trigger_context,
                ),
                **self._release_watch_discipline_payload(
                    release_watch_discipline_status=(
                        state_result.release_watch_discipline_status
                    ),
                    release_watch_discipline_class_id=(
                        state_result.release_watch_discipline_class_id
                    ),
                    release_watch_discipline_context=(
                        state_result.release_watch_discipline_context
                    ),
                ),
                **self._release_confirmation_payload(
                    release_confirmation_status=(
                        state_result.release_confirmation_status
                    ),
                    release_confirmation_class_id=(
                        state_result.release_confirmation_class_id
                    ),
                    release_confirmation_context=(
                        state_result.release_confirmation_context
                    ),
                ),
                **self._production_entitlement_check_payload(
                    production_entitlement_check_status=(
                        state_result.production_entitlement_check_status
                    ),
                    production_entitlement_check_class_id=(
                        state_result.production_entitlement_check_class_id
                    ),
                    production_entitlement_check_context=(
                        state_result.production_entitlement_check_context
                    ),
                ),
                **self._contained_rollback_payload(
                    contained_rollback_status=state_result.contained_rollback_status,
                    contained_rollback_class_id=(
                        state_result.contained_rollback_class_id
                    ),
                    contained_rollback_context=(
                        state_result.contained_rollback_context
                    ),
                ),
                **self._release_audit_trace_payload(
                    release_audit_trace_status=(
                        state_result.release_audit_trace_status
                    ),
                    release_audit_trace_class_id=(
                        state_result.release_audit_trace_class_id
                    ),
                    release_audit_trace_context=(
                        state_result.release_audit_trace_context
                    ),
                ),
            },
            tags=("case-episode", "interruption"),
        )
        return updated

    def resume_episode(
        self,
        episode_id: str,
        *,
        transition_name: str,
        reason: str,
        correlation_id: str,
        actor_id: str,
        actor_role: str,
        threshold_context: Mapping[str, object] | None = None,
        packet_context: Mapping[str, object] | None = None,
        review_resolution_class_id: str | None = None,
        review_resolution_context: Mapping[str, object] | None = None,
        recommendation_class_id: str | None = None,
        recommendation_context: Mapping[str, object] | None = None,
        policy_output_class_id: str | None = None,
        policy_output_context: Mapping[str, object] | None = None,
        portfolio_output_class_id: str | None = None,
        portfolio_output_context: Mapping[str, object] | None = None,
        action_instruction_class_id: str | None = None,
        action_instruction_context: Mapping[str, object] | None = None,
        execution_request_class_id: str | None = None,
        execution_request_context: Mapping[str, object] | None = None,
        execution_dispatch_class_id: str | None = None,
        execution_dispatch_context: Mapping[str, object] | None = None,
        execution_outcome_class_id: str | None = None,
        execution_outcome_context: Mapping[str, object] | None = None,
        post_mortem_judgment_class_id: str | None = None,
        post_mortem_judgment_context: Mapping[str, object] | None = None,
        policy_learning_evidence_class_id: str | None = None,
        policy_learning_evidence_admission_context: Mapping[str, object] | None = None,
        policy_learning_update_threshold_class_id: str | None = None,
        policy_learning_update_threshold_context: Mapping[str, object] | None = None,
        policy_learning_update_approval_class_id: str | None = None,
        policy_learning_update_approval_context: Mapping[str, object] | None = None,
        policy_learning_update_preparation_class_id: str | None = None,
        policy_learning_update_preparation_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_planning_class_id: str | None = None,
        policy_learning_update_mutation_planning_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_execution_class_id: str | None = None,
        policy_learning_update_mutation_execution_context: Mapping[str, object] | None = None,
        promotion_readiness_class_id: str | None = None,
        promotion_readiness_context: Mapping[str, object] | None = None,
        rollout_scope_class_id: str | None = None,
        rollout_scope_context: Mapping[str, object] | None = None,
        rollback_trigger_class_id: str | None = None,
        rollback_trigger_context: Mapping[str, object] | None = None,
        release_watch_discipline_class_id: str | None = None,
        release_watch_discipline_context: Mapping[str, object] | None = None,
        release_confirmation_class_id: str | None = None,
        release_confirmation_context: Mapping[str, object] | None = None,
        production_entitlement_check_class_id: str | None = None,
        production_entitlement_check_context: Mapping[str, object] | None = None,
        contained_rollback_class_id: str | None = None,
        contained_rollback_context: Mapping[str, object] | None = None,
        release_audit_trace_class_id: str | None = None,
        release_audit_trace_context: Mapping[str, object] | None = None,
    ) -> CaseEpisode:
        episode = self._require_episode(episode_id)
        if episode.status != "interrupted":
            raise EpisodeEntryValidationError(
                f"Episode '{episode_id}' is not interrupted and cannot be resumed."
            )

        state_result = self._state_manager.apply_transition(
            case_type=episode.case_type,
            case_key=episode.case_key,
            state_model_name=episode.state_model_name,
            current_state=episode.current_state,
            current_status=episode.status,
            transition_name=transition_name,
            source_stage=episode.current_stage,
            target_stage=episode.current_stage,
            correlation_id=correlation_id,
            episode_id=episode_id,
            actor_id=actor_id,
            actor_role=actor_role,
            threshold_context=threshold_context,
            packet_context=packet_context,
            reason=reason,
            review_resolution_class_id=review_resolution_class_id,
            review_resolution_context=review_resolution_context,
            recommendation_class_id=recommendation_class_id,
            recommendation_context=recommendation_context,
            policy_output_class_id=policy_output_class_id,
            policy_output_context=policy_output_context,
            portfolio_output_class_id=portfolio_output_class_id,
            portfolio_output_context=portfolio_output_context,
            action_instruction_class_id=action_instruction_class_id,
            action_instruction_context=action_instruction_context,
            execution_request_class_id=execution_request_class_id,
            execution_request_context=execution_request_context,
            execution_dispatch_class_id=execution_dispatch_class_id,
            execution_dispatch_context=execution_dispatch_context,
            execution_outcome_class_id=execution_outcome_class_id,
            execution_outcome_context=execution_outcome_context,
            post_mortem_judgment_class_id=post_mortem_judgment_class_id,
            post_mortem_judgment_context=post_mortem_judgment_context,
            policy_learning_evidence_class_id=policy_learning_evidence_class_id,
            policy_learning_evidence_admission_context=(
                policy_learning_evidence_admission_context
            ),
            policy_learning_update_threshold_class_id=(
                policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_context=(
                policy_learning_update_threshold_context
            ),
            policy_learning_update_approval_class_id=(
                policy_learning_update_approval_class_id
            ),
            policy_learning_update_approval_context=(
                policy_learning_update_approval_context
            ),
            policy_learning_update_preparation_class_id=(
                policy_learning_update_preparation_class_id
            ),
            policy_learning_update_preparation_context=(
                policy_learning_update_preparation_context
            ),
            policy_learning_update_mutation_planning_class_id=(
                policy_learning_update_mutation_planning_class_id
            ),
            policy_learning_update_mutation_planning_context=(
                policy_learning_update_mutation_planning_context
            ),
            policy_learning_update_mutation_execution_class_id=(
                policy_learning_update_mutation_execution_class_id
            ),
            policy_learning_update_mutation_execution_context=(
                policy_learning_update_mutation_execution_context
            ),
            promotion_readiness_class_id=promotion_readiness_class_id,
            promotion_readiness_context=promotion_readiness_context,
            rollout_scope_class_id=rollout_scope_class_id,
            rollout_scope_context=rollout_scope_context,
            rollback_trigger_class_id=rollback_trigger_class_id,
            rollback_trigger_context=rollback_trigger_context,
            release_watch_discipline_class_id=release_watch_discipline_class_id,
            release_watch_discipline_context=release_watch_discipline_context,
            release_confirmation_class_id=release_confirmation_class_id,
            release_confirmation_context=release_confirmation_context,
            production_entitlement_check_class_id=(
                production_entitlement_check_class_id
            ),
            production_entitlement_check_context=production_entitlement_check_context,
            contained_rollback_class_id=contained_rollback_class_id,
            contained_rollback_context=contained_rollback_context,
            release_audit_trace_class_id=release_audit_trace_class_id,
            release_audit_trace_context=release_audit_trace_context,
        )
        updated = replace(
            episode,
            current_state=state_result.to_state,
            status=state_result.resulting_status,
            interruption_reason=state_result.next_interruption_reason,
            last_updated_at=datetime.now(tz=UTC),
        )
        self._persist_episode(updated, correlation_id=correlation_id, actor_id=actor_id)
        self._audit_event_store.record_event(
            event_type="decision.case.resumption_recorded",
            owner="decision.case.case_episode_orchestrator",
            correlation_id=correlation_id,
            entity_type="case_episode",
            entity_id=episode_id,
            actor_id=actor_id,
            payload={
                "reason": reason,
                "resumed_stage": episode.current_stage,
                "route_name": state_result.route_name,
                "routing_review_required": state_result.routing_review_required,
                "routing_resolution_status": state_result.routing_resolution_status,
                "review_outcome": state_result.review_outcome,
                **self._review_payload(
                    review_mode=state_result.review_mode,
                    review_threshold_id=state_result.review_threshold_id,
                    review_playbook_reference=state_result.review_playbook_reference,
                ),
                **self._review_packet_payload(
                    review_packet_status=state_result.review_packet_status,
                    review_packet_handoff_ready=state_result.review_packet_handoff_ready,
                    review_packet_id=state_result.review_packet_id,
                    review_packet_template_id=state_result.review_packet_template_id,
                    review_packet_reason_class=state_result.review_packet_reason_class,
                    review_packet_scope=state_result.review_packet_scope,
                    review_packet_handoff_channel=state_result.review_packet_handoff_channel,
                ),
                **self._review_resolution_payload(
                    review_resolution_status=state_result.review_resolution_status,
                    review_resolution_id=state_result.review_resolution_id,
                    review_resolution_class_id=state_result.review_resolution_class_id,
                    review_resolution_outcome=state_result.review_resolution_outcome,
                    review_resolution_state=state_result.review_resolution_state,
                    review_disposition_class_id=state_result.review_disposition_class_id,
                    review_disposition_state=state_result.review_disposition_state,
                    review_closure_state=state_result.review_closure_state,
                    review_closure_quality=state_result.review_closure_quality,
                    review_resolution_terminality=state_result.review_resolution_terminality,
                ),
                **self._recommendation_payload(
                    recommendation_status=state_result.recommendation_status,
                    recommendation_id=state_result.recommendation_id,
                    recommendation_class_id=state_result.recommendation_class_id,
                    recommendation_template_id=state_result.recommendation_template_id,
                    recommendation_action_class=state_result.recommendation_action_class,
                    recommendation_advisory_status=state_result.recommendation_advisory_status,
                    recommendation_commitment_readiness=(
                        state_result.recommendation_commitment_readiness
                    ),
                ),
                **self._policy_output_payload(
                    policy_output_status=state_result.policy_output_status,
                    policy_output_id=state_result.policy_output_id,
                    policy_output_class_id=state_result.policy_output_class_id,
                    policy_output_template_id=state_result.policy_output_template_id,
                    policy_output_bounded_policy_posture=(
                        state_result.policy_output_bounded_policy_posture
                    ),
                    policy_output_action_boundary_posture=(
                        state_result.policy_output_action_boundary_posture
                    ),
                    policy_output_promotion_safe_use=(
                        state_result.policy_output_promotion_safe_use
                    ),
                ),
                **self._portfolio_output_payload(
                    portfolio_output_status=state_result.portfolio_output_status,
                    portfolio_output_id=state_result.portfolio_output_id,
                    portfolio_output_class_id=state_result.portfolio_output_class_id,
                    portfolio_output_template_id=(
                        state_result.portfolio_output_template_id
                    ),
                    portfolio_output_allocation_posture=(
                        state_result.portfolio_output_allocation_posture
                    ),
                    portfolio_output_weight_posture=(
                        state_result.portfolio_output_weight_posture
                    ),
                    portfolio_output_action_boundary_posture=(
                        state_result.portfolio_output_action_boundary_posture
                    ),
                    portfolio_output_promotion_safe_use=(
                        state_result.portfolio_output_promotion_safe_use
                    ),
                ),
                **self._action_instruction_payload(
                    action_instruction_status=state_result.action_instruction_status,
                    action_instruction_id=state_result.action_instruction_id,
                    action_instruction_class_id=(
                        state_result.action_instruction_class_id
                    ),
                    action_instruction_template_id=(
                        state_result.action_instruction_template_id
                    ),
                    action_instruction_instruction_status=(
                        state_result.action_instruction_instruction_status
                    ),
                    action_instruction_bounded_action_posture=(
                        state_result.action_instruction_bounded_action_posture
                    ),
                    action_instruction_execution_boundary_posture=(
                        state_result.action_instruction_execution_boundary_posture
                    ),
                    action_instruction_promotion_safe_use=(
                        state_result.action_instruction_promotion_safe_use
                    ),
                ),
                **self._execution_request_payload(
                    execution_request_status=state_result.execution_request_status,
                    execution_request_id=state_result.execution_request_id,
                    execution_request_class_id=(
                        state_result.execution_request_class_id
                    ),
                    execution_request_template_id=(
                        state_result.execution_request_template_id
                    ),
                    execution_request_readiness=(
                        state_result.execution_request_readiness
                    ),
                    execution_request_action_boundary_posture=(
                        state_result.execution_request_action_boundary_posture
                    ),
                ),
                **self._execution_dispatch_payload(
                    execution_dispatch_status=state_result.execution_dispatch_status,
                    execution_dispatch_id=state_result.execution_dispatch_id,
                    execution_dispatch_class_id=(
                        state_result.execution_dispatch_class_id
                    ),
                    execution_dispatch_template_id=(
                        state_result.execution_dispatch_template_id
                    ),
                    execution_dispatch_readiness=(
                        state_result.execution_dispatch_readiness
                    ),
                    execution_dispatch_boundary_posture=(
                        state_result.execution_dispatch_boundary_posture
                    ),
                ),
                **self._execution_outcome_payload(
                    execution_outcome_status=state_result.execution_outcome_status,
                    execution_outcome_id=state_result.execution_outcome_id,
                    execution_outcome_class_id=(
                        state_result.execution_outcome_class_id
                    ),
                    execution_outcome_template_id=(
                        state_result.execution_outcome_template_id
                    ),
                    execution_outcome_realized_result_class=(
                        state_result.execution_outcome_realized_result_class
                    ),
                    execution_outcome_feedback_capture_readiness=(
                        state_result.execution_outcome_feedback_capture_readiness
                    ),
                    execution_outcome_expected_relation=(
                        state_result.execution_outcome_expected_relation
                    ),
                    execution_outcome_comparison_posture=(
                        state_result.execution_outcome_comparison_posture
                    ),
                ),
                **self._post_mortem_payload(
                    post_mortem_judgment_status=(
                        state_result.post_mortem_judgment_status
                    ),
                    post_mortem_judgment_id=state_result.post_mortem_judgment_id,
                    post_mortem_judgment_class_id=(
                        state_result.post_mortem_judgment_class_id
                    ),
                    post_mortem_judgment_template_id=(
                        state_result.post_mortem_judgment_template_id
                    ),
                    post_mortem_primary_attribution_category=(
                        state_result.post_mortem_primary_attribution_category
                    ),
                    post_mortem_evidence_quality=(
                        state_result.post_mortem_evidence_quality
                    ),
                    post_mortem_confidence_posture=(
                        state_result.post_mortem_confidence_posture
                    ),
                    post_mortem_learning_direction=(
                        state_result.post_mortem_learning_direction
                    ),
                    post_mortem_comparison_posture=(
                        state_result.post_mortem_comparison_posture
                    ),
                ),
                **self._policy_learning_evidence_payload(
                    policy_learning_evidence_admission_status=(
                        state_result.policy_learning_evidence_admission_status
                    ),
                    policy_learning_evidence_admission_id=(
                        state_result.policy_learning_evidence_admission_id
                    ),
                    policy_learning_evidence_class_id=(
                        state_result.policy_learning_evidence_class_id
                    ),
                    policy_learning_evidence_template_id=(
                        state_result.policy_learning_evidence_template_id
                    ),
                    policy_learning_evidence_admission_context=(
                        state_result.policy_learning_evidence_admission_context
                    ),
                ),
                **self._policy_learning_update_threshold_payload(
                    policy_learning_update_threshold_status=(
                        state_result.policy_learning_update_threshold_status
                    ),
                    policy_learning_update_threshold_id=(
                        state_result.policy_learning_update_threshold_id
                    ),
                    policy_learning_update_threshold_class_id=(
                        state_result.policy_learning_update_threshold_class_id
                    ),
                    policy_learning_update_threshold_template_id=(
                        state_result.policy_learning_update_threshold_template_id
                    ),
                    policy_learning_update_threshold_context=(
                        state_result.policy_learning_update_threshold_context
                    ),
                ),
                **self._policy_learning_update_approval_payload(
                    policy_learning_update_approval_status=(
                        state_result.policy_learning_update_approval_status
                    ),
                    policy_learning_update_approval_class_id=(
                        state_result.policy_learning_update_approval_class_id
                    ),
                    policy_learning_update_approval_context=(
                        state_result.policy_learning_update_approval_context
                    ),
                ),
                **self._policy_learning_update_preparation_payload(
                    policy_learning_update_preparation_status=(
                        state_result.policy_learning_update_preparation_status
                    ),
                    policy_learning_update_preparation_class_id=(
                        state_result.policy_learning_update_preparation_class_id
                    ),
                    policy_learning_update_preparation_context=(
                        state_result.policy_learning_update_preparation_context
                    ),
                ),
                **self._policy_learning_update_mutation_planning_payload(
                    policy_learning_update_mutation_planning_status=(
                        state_result.policy_learning_update_mutation_planning_status
                    ),
                    policy_learning_update_mutation_planning_class_id=(
                        state_result.policy_learning_update_mutation_planning_class_id
                    ),
                    policy_learning_update_mutation_planning_context=(
                        state_result.policy_learning_update_mutation_planning_context
                    ),
                ),
                **self._policy_learning_update_mutation_execution_payload(
                    policy_learning_update_mutation_execution_status=(
                        state_result.policy_learning_update_mutation_execution_status
                    ),
                    policy_learning_update_mutation_execution_class_id=(
                        state_result.policy_learning_update_mutation_execution_class_id
                    ),
                    policy_learning_update_mutation_execution_context=(
                        state_result.policy_learning_update_mutation_execution_context
                    ),
                ),
                **self._promotion_readiness_payload(
                    promotion_readiness_status=(
                        state_result.promotion_readiness_status
                    ),
                    promotion_readiness_class_id=(
                        state_result.promotion_readiness_class_id
                    ),
                    promotion_readiness_context=(
                        state_result.promotion_readiness_context
                    ),
                ),
                **self._rollout_scope_payload(
                    rollout_scope_status=state_result.rollout_scope_status,
                    rollout_scope_class_id=state_result.rollout_scope_class_id,
                    rollout_scope_context=state_result.rollout_scope_context,
                ),
                **self._rollback_trigger_payload(
                    rollback_trigger_status=state_result.rollback_trigger_status,
                    rollback_trigger_class_id=state_result.rollback_trigger_class_id,
                    rollback_trigger_context=state_result.rollback_trigger_context,
                ),
                **self._release_watch_discipline_payload(
                    release_watch_discipline_status=(
                        state_result.release_watch_discipline_status
                    ),
                    release_watch_discipline_class_id=(
                        state_result.release_watch_discipline_class_id
                    ),
                    release_watch_discipline_context=(
                        state_result.release_watch_discipline_context
                    ),
                ),
                **self._release_confirmation_payload(
                    release_confirmation_status=(
                        state_result.release_confirmation_status
                    ),
                    release_confirmation_class_id=(
                        state_result.release_confirmation_class_id
                    ),
                    release_confirmation_context=(
                        state_result.release_confirmation_context
                    ),
                ),
                **self._production_entitlement_check_payload(
                    production_entitlement_check_status=(
                        state_result.production_entitlement_check_status
                    ),
                    production_entitlement_check_class_id=(
                        state_result.production_entitlement_check_class_id
                    ),
                    production_entitlement_check_context=(
                        state_result.production_entitlement_check_context
                    ),
                ),
                **self._contained_rollback_payload(
                    contained_rollback_status=state_result.contained_rollback_status,
                    contained_rollback_class_id=(
                        state_result.contained_rollback_class_id
                    ),
                    contained_rollback_context=(
                        state_result.contained_rollback_context
                    ),
                ),
                **self._release_audit_trace_payload(
                    release_audit_trace_status=(
                        state_result.release_audit_trace_status
                    ),
                    release_audit_trace_class_id=(
                        state_result.release_audit_trace_class_id
                    ),
                    release_audit_trace_context=(
                        state_result.release_audit_trace_context
                    ),
                ),
            },
            tags=("case-episode", "resumption"),
        )
        return updated

    def fallback_episode(
        self,
        episode_id: str,
        *,
        to_stage: str,
        transition_name: str,
        reason: str,
        correlation_id: str,
        actor_id: str,
        actor_role: str,
        threshold_context: Mapping[str, object] | None = None,
        packet_context: Mapping[str, object] | None = None,
        review_resolution_class_id: str | None = None,
        review_resolution_context: Mapping[str, object] | None = None,
        recommendation_class_id: str | None = None,
        recommendation_context: Mapping[str, object] | None = None,
        policy_output_class_id: str | None = None,
        policy_output_context: Mapping[str, object] | None = None,
        portfolio_output_class_id: str | None = None,
        portfolio_output_context: Mapping[str, object] | None = None,
        action_instruction_class_id: str | None = None,
        action_instruction_context: Mapping[str, object] | None = None,
        execution_request_class_id: str | None = None,
        execution_request_context: Mapping[str, object] | None = None,
        execution_dispatch_class_id: str | None = None,
        execution_dispatch_context: Mapping[str, object] | None = None,
        execution_outcome_class_id: str | None = None,
        execution_outcome_context: Mapping[str, object] | None = None,
        post_mortem_judgment_class_id: str | None = None,
        post_mortem_judgment_context: Mapping[str, object] | None = None,
        policy_learning_evidence_class_id: str | None = None,
        policy_learning_evidence_admission_context: Mapping[str, object] | None = None,
        policy_learning_update_threshold_class_id: str | None = None,
        policy_learning_update_threshold_context: Mapping[str, object] | None = None,
        policy_learning_update_approval_class_id: str | None = None,
        policy_learning_update_approval_context: Mapping[str, object] | None = None,
        policy_learning_update_preparation_class_id: str | None = None,
        policy_learning_update_preparation_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_planning_class_id: str | None = None,
        policy_learning_update_mutation_planning_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_execution_class_id: str | None = None,
        policy_learning_update_mutation_execution_context: Mapping[str, object] | None = None,
        promotion_readiness_class_id: str | None = None,
        promotion_readiness_context: Mapping[str, object] | None = None,
        rollout_scope_class_id: str | None = None,
        rollout_scope_context: Mapping[str, object] | None = None,
        rollback_trigger_class_id: str | None = None,
        rollback_trigger_context: Mapping[str, object] | None = None,
        release_watch_discipline_class_id: str | None = None,
        release_watch_discipline_context: Mapping[str, object] | None = None,
        release_confirmation_class_id: str | None = None,
        release_confirmation_context: Mapping[str, object] | None = None,
        production_entitlement_check_class_id: str | None = None,
        production_entitlement_check_context: Mapping[str, object] | None = None,
        contained_rollback_class_id: str | None = None,
        contained_rollback_context: Mapping[str, object] | None = None,
        release_audit_trace_class_id: str | None = None,
        release_audit_trace_context: Mapping[str, object] | None = None,
    ) -> CaseEpisode:
        episode = self._require_episode(episode_id)
        case_type_definition = self._case_type_registry.get_case_type(episode.case_type)
        if to_stage not in case_type_definition.allowed_stages:
            raise HandoffValidationError(
                f"Fallback stage '{to_stage}' is not registered for case type '{episode.case_type}'."
            )

        state_result = self._state_manager.apply_transition(
            case_type=episode.case_type,
            case_key=episode.case_key,
            state_model_name=episode.state_model_name,
            current_state=episode.current_state,
            current_status=episode.status,
            transition_name=transition_name,
            source_stage=episode.current_stage,
            target_stage=to_stage,
            correlation_id=correlation_id,
            episode_id=episode_id,
            actor_id=actor_id,
            actor_role=actor_role,
            threshold_context=threshold_context,
            packet_context=packet_context,
            reason=reason,
            review_resolution_class_id=review_resolution_class_id,
            review_resolution_context=review_resolution_context,
            recommendation_class_id=recommendation_class_id,
            recommendation_context=recommendation_context,
            policy_output_class_id=policy_output_class_id,
            policy_output_context=policy_output_context,
            portfolio_output_class_id=portfolio_output_class_id,
            portfolio_output_context=portfolio_output_context,
            action_instruction_class_id=action_instruction_class_id,
            action_instruction_context=action_instruction_context,
            execution_request_class_id=execution_request_class_id,
            execution_request_context=execution_request_context,
            execution_dispatch_class_id=execution_dispatch_class_id,
            execution_dispatch_context=execution_dispatch_context,
            execution_outcome_class_id=execution_outcome_class_id,
            execution_outcome_context=execution_outcome_context,
            post_mortem_judgment_class_id=post_mortem_judgment_class_id,
            post_mortem_judgment_context=post_mortem_judgment_context,
            policy_learning_evidence_class_id=policy_learning_evidence_class_id,
            policy_learning_evidence_admission_context=(
                policy_learning_evidence_admission_context
            ),
            policy_learning_update_threshold_class_id=(
                policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_context=(
                policy_learning_update_threshold_context
            ),
            policy_learning_update_approval_class_id=(
                policy_learning_update_approval_class_id
            ),
            policy_learning_update_approval_context=(
                policy_learning_update_approval_context
            ),
            policy_learning_update_preparation_class_id=(
                policy_learning_update_preparation_class_id
            ),
            policy_learning_update_preparation_context=(
                policy_learning_update_preparation_context
            ),
            policy_learning_update_mutation_planning_class_id=(
                policy_learning_update_mutation_planning_class_id
            ),
            policy_learning_update_mutation_planning_context=(
                policy_learning_update_mutation_planning_context
            ),
            policy_learning_update_mutation_execution_class_id=(
                policy_learning_update_mutation_execution_class_id
            ),
            policy_learning_update_mutation_execution_context=(
                policy_learning_update_mutation_execution_context
            ),
            promotion_readiness_class_id=promotion_readiness_class_id,
            promotion_readiness_context=promotion_readiness_context,
            rollout_scope_class_id=rollout_scope_class_id,
            rollout_scope_context=rollout_scope_context,
            rollback_trigger_class_id=rollback_trigger_class_id,
            rollback_trigger_context=rollback_trigger_context,
            release_watch_discipline_class_id=release_watch_discipline_class_id,
            release_watch_discipline_context=release_watch_discipline_context,
            release_confirmation_class_id=release_confirmation_class_id,
            release_confirmation_context=release_confirmation_context,
            production_entitlement_check_class_id=(
                production_entitlement_check_class_id
            ),
            production_entitlement_check_context=production_entitlement_check_context,
            contained_rollback_class_id=contained_rollback_class_id,
            contained_rollback_context=contained_rollback_context,
            release_audit_trace_class_id=release_audit_trace_class_id,
            release_audit_trace_context=release_audit_trace_context,
        )
        updated = replace(
            episode,
            current_stage=to_stage,
            current_state=state_result.to_state,
            status=state_result.resulting_status,
            interruption_reason=state_result.next_interruption_reason,
            last_updated_at=datetime.now(tz=UTC),
        )
        self._persist_episode(updated, correlation_id=correlation_id, actor_id=actor_id)
        self._audit_event_store.record_event(
            event_type="decision.case.fallback_recorded",
            owner="decision.case.case_episode_orchestrator",
            correlation_id=correlation_id,
            entity_type="case_episode",
            entity_id=episode_id,
            actor_id=actor_id,
            payload={
                "to_stage": to_stage,
                "reason": reason,
                "route_name": state_result.route_name,
                "routing_review_required": state_result.routing_review_required,
                "routing_resolution_status": state_result.routing_resolution_status,
                "review_outcome": state_result.review_outcome,
                **self._review_payload(
                    review_mode=state_result.review_mode,
                    review_threshold_id=state_result.review_threshold_id,
                    review_playbook_reference=state_result.review_playbook_reference,
                ),
                **self._review_packet_payload(
                    review_packet_status=state_result.review_packet_status,
                    review_packet_handoff_ready=state_result.review_packet_handoff_ready,
                    review_packet_id=state_result.review_packet_id,
                    review_packet_template_id=state_result.review_packet_template_id,
                    review_packet_reason_class=state_result.review_packet_reason_class,
                    review_packet_scope=state_result.review_packet_scope,
                    review_packet_handoff_channel=state_result.review_packet_handoff_channel,
                ),
                **self._review_resolution_payload(
                    review_resolution_status=state_result.review_resolution_status,
                    review_resolution_id=state_result.review_resolution_id,
                    review_resolution_class_id=state_result.review_resolution_class_id,
                    review_resolution_outcome=state_result.review_resolution_outcome,
                    review_resolution_state=state_result.review_resolution_state,
                    review_disposition_class_id=state_result.review_disposition_class_id,
                    review_disposition_state=state_result.review_disposition_state,
                    review_closure_state=state_result.review_closure_state,
                    review_closure_quality=state_result.review_closure_quality,
                    review_resolution_terminality=state_result.review_resolution_terminality,
                ),
                **self._recommendation_payload(
                    recommendation_status=state_result.recommendation_status,
                    recommendation_id=state_result.recommendation_id,
                    recommendation_class_id=state_result.recommendation_class_id,
                    recommendation_template_id=state_result.recommendation_template_id,
                    recommendation_action_class=state_result.recommendation_action_class,
                    recommendation_advisory_status=state_result.recommendation_advisory_status,
                    recommendation_commitment_readiness=(
                        state_result.recommendation_commitment_readiness
                    ),
                ),
                **self._policy_output_payload(
                    policy_output_status=state_result.policy_output_status,
                    policy_output_id=state_result.policy_output_id,
                    policy_output_class_id=state_result.policy_output_class_id,
                    policy_output_template_id=state_result.policy_output_template_id,
                    policy_output_bounded_policy_posture=(
                        state_result.policy_output_bounded_policy_posture
                    ),
                    policy_output_action_boundary_posture=(
                        state_result.policy_output_action_boundary_posture
                    ),
                    policy_output_promotion_safe_use=(
                        state_result.policy_output_promotion_safe_use
                    ),
                ),
                **self._portfolio_output_payload(
                    portfolio_output_status=state_result.portfolio_output_status,
                    portfolio_output_id=state_result.portfolio_output_id,
                    portfolio_output_class_id=state_result.portfolio_output_class_id,
                    portfolio_output_template_id=(
                        state_result.portfolio_output_template_id
                    ),
                    portfolio_output_allocation_posture=(
                        state_result.portfolio_output_allocation_posture
                    ),
                    portfolio_output_weight_posture=(
                        state_result.portfolio_output_weight_posture
                    ),
                    portfolio_output_action_boundary_posture=(
                        state_result.portfolio_output_action_boundary_posture
                    ),
                    portfolio_output_promotion_safe_use=(
                        state_result.portfolio_output_promotion_safe_use
                    ),
                ),
                **self._action_instruction_payload(
                    action_instruction_status=state_result.action_instruction_status,
                    action_instruction_id=state_result.action_instruction_id,
                    action_instruction_class_id=(
                        state_result.action_instruction_class_id
                    ),
                    action_instruction_template_id=(
                        state_result.action_instruction_template_id
                    ),
                    action_instruction_instruction_status=(
                        state_result.action_instruction_instruction_status
                    ),
                    action_instruction_bounded_action_posture=(
                        state_result.action_instruction_bounded_action_posture
                    ),
                    action_instruction_execution_boundary_posture=(
                        state_result.action_instruction_execution_boundary_posture
                    ),
                    action_instruction_promotion_safe_use=(
                        state_result.action_instruction_promotion_safe_use
                    ),
                ),
                **self._execution_request_payload(
                    execution_request_status=state_result.execution_request_status,
                    execution_request_id=state_result.execution_request_id,
                    execution_request_class_id=(
                        state_result.execution_request_class_id
                    ),
                    execution_request_template_id=(
                        state_result.execution_request_template_id
                    ),
                    execution_request_readiness=(
                        state_result.execution_request_readiness
                    ),
                    execution_request_action_boundary_posture=(
                        state_result.execution_request_action_boundary_posture
                    ),
                ),
                **self._execution_dispatch_payload(
                    execution_dispatch_status=state_result.execution_dispatch_status,
                    execution_dispatch_id=state_result.execution_dispatch_id,
                    execution_dispatch_class_id=(
                        state_result.execution_dispatch_class_id
                    ),
                    execution_dispatch_template_id=(
                        state_result.execution_dispatch_template_id
                    ),
                    execution_dispatch_readiness=(
                        state_result.execution_dispatch_readiness
                    ),
                    execution_dispatch_boundary_posture=(
                        state_result.execution_dispatch_boundary_posture
                    ),
                ),
                **self._execution_outcome_payload(
                    execution_outcome_status=state_result.execution_outcome_status,
                    execution_outcome_id=state_result.execution_outcome_id,
                    execution_outcome_class_id=(
                        state_result.execution_outcome_class_id
                    ),
                    execution_outcome_template_id=(
                        state_result.execution_outcome_template_id
                    ),
                    execution_outcome_realized_result_class=(
                        state_result.execution_outcome_realized_result_class
                    ),
                    execution_outcome_feedback_capture_readiness=(
                        state_result.execution_outcome_feedback_capture_readiness
                    ),
                    execution_outcome_expected_relation=(
                        state_result.execution_outcome_expected_relation
                    ),
                    execution_outcome_comparison_posture=(
                        state_result.execution_outcome_comparison_posture
                    ),
                ),
                **self._post_mortem_payload(
                    post_mortem_judgment_status=(
                        state_result.post_mortem_judgment_status
                    ),
                    post_mortem_judgment_id=state_result.post_mortem_judgment_id,
                    post_mortem_judgment_class_id=(
                        state_result.post_mortem_judgment_class_id
                    ),
                    post_mortem_judgment_template_id=(
                        state_result.post_mortem_judgment_template_id
                    ),
                    post_mortem_primary_attribution_category=(
                        state_result.post_mortem_primary_attribution_category
                    ),
                    post_mortem_evidence_quality=(
                        state_result.post_mortem_evidence_quality
                    ),
                    post_mortem_confidence_posture=(
                        state_result.post_mortem_confidence_posture
                    ),
                    post_mortem_learning_direction=(
                        state_result.post_mortem_learning_direction
                    ),
                    post_mortem_comparison_posture=(
                        state_result.post_mortem_comparison_posture
                    ),
                ),
                **self._policy_learning_evidence_payload(
                    policy_learning_evidence_admission_status=(
                        state_result.policy_learning_evidence_admission_status
                    ),
                    policy_learning_evidence_admission_id=(
                        state_result.policy_learning_evidence_admission_id
                    ),
                    policy_learning_evidence_class_id=(
                        state_result.policy_learning_evidence_class_id
                    ),
                    policy_learning_evidence_template_id=(
                        state_result.policy_learning_evidence_template_id
                    ),
                    policy_learning_evidence_admission_context=(
                        state_result.policy_learning_evidence_admission_context
                    ),
                ),
                **self._policy_learning_update_threshold_payload(
                    policy_learning_update_threshold_status=(
                        state_result.policy_learning_update_threshold_status
                    ),
                    policy_learning_update_threshold_id=(
                        state_result.policy_learning_update_threshold_id
                    ),
                    policy_learning_update_threshold_class_id=(
                        state_result.policy_learning_update_threshold_class_id
                    ),
                    policy_learning_update_threshold_template_id=(
                        state_result.policy_learning_update_threshold_template_id
                    ),
                    policy_learning_update_threshold_context=(
                        state_result.policy_learning_update_threshold_context
                    ),
                ),
                **self._policy_learning_update_approval_payload(
                    policy_learning_update_approval_status=(
                        state_result.policy_learning_update_approval_status
                    ),
                    policy_learning_update_approval_class_id=(
                        state_result.policy_learning_update_approval_class_id
                    ),
                    policy_learning_update_approval_context=(
                        state_result.policy_learning_update_approval_context
                    ),
                ),
                **self._policy_learning_update_preparation_payload(
                    policy_learning_update_preparation_status=(
                        state_result.policy_learning_update_preparation_status
                    ),
                    policy_learning_update_preparation_class_id=(
                        state_result.policy_learning_update_preparation_class_id
                    ),
                    policy_learning_update_preparation_context=(
                        state_result.policy_learning_update_preparation_context
                    ),
                ),
                **self._policy_learning_update_mutation_planning_payload(
                    policy_learning_update_mutation_planning_status=(
                        state_result.policy_learning_update_mutation_planning_status
                    ),
                    policy_learning_update_mutation_planning_class_id=(
                        state_result.policy_learning_update_mutation_planning_class_id
                    ),
                    policy_learning_update_mutation_planning_context=(
                        state_result.policy_learning_update_mutation_planning_context
                    ),
                ),
                **self._policy_learning_update_mutation_execution_payload(
                    policy_learning_update_mutation_execution_status=(
                        state_result.policy_learning_update_mutation_execution_status
                    ),
                    policy_learning_update_mutation_execution_class_id=(
                        state_result.policy_learning_update_mutation_execution_class_id
                    ),
                    policy_learning_update_mutation_execution_context=(
                        state_result.policy_learning_update_mutation_execution_context
                    ),
                ),
                **self._promotion_readiness_payload(
                    promotion_readiness_status=(
                        state_result.promotion_readiness_status
                    ),
                    promotion_readiness_class_id=(
                        state_result.promotion_readiness_class_id
                    ),
                    promotion_readiness_context=(
                        state_result.promotion_readiness_context
                    ),
                ),
                **self._rollout_scope_payload(
                    rollout_scope_status=state_result.rollout_scope_status,
                    rollout_scope_class_id=state_result.rollout_scope_class_id,
                    rollout_scope_context=state_result.rollout_scope_context,
                ),
                **self._rollback_trigger_payload(
                    rollback_trigger_status=state_result.rollback_trigger_status,
                    rollback_trigger_class_id=state_result.rollback_trigger_class_id,
                    rollback_trigger_context=state_result.rollback_trigger_context,
                ),
                **self._release_watch_discipline_payload(
                    release_watch_discipline_status=(
                        state_result.release_watch_discipline_status
                    ),
                    release_watch_discipline_class_id=(
                        state_result.release_watch_discipline_class_id
                    ),
                    release_watch_discipline_context=(
                        state_result.release_watch_discipline_context
                    ),
                ),
                **self._release_confirmation_payload(
                    release_confirmation_status=(
                        state_result.release_confirmation_status
                    ),
                    release_confirmation_class_id=(
                        state_result.release_confirmation_class_id
                    ),
                    release_confirmation_context=(
                        state_result.release_confirmation_context
                    ),
                ),
                **self._production_entitlement_check_payload(
                    production_entitlement_check_status=(
                        state_result.production_entitlement_check_status
                    ),
                    production_entitlement_check_class_id=(
                        state_result.production_entitlement_check_class_id
                    ),
                    production_entitlement_check_context=(
                        state_result.production_entitlement_check_context
                    ),
                ),
                **self._contained_rollback_payload(
                    contained_rollback_status=state_result.contained_rollback_status,
                    contained_rollback_class_id=(
                        state_result.contained_rollback_class_id
                    ),
                    contained_rollback_context=(
                        state_result.contained_rollback_context
                    ),
                ),
                **self._release_audit_trace_payload(
                    release_audit_trace_status=(
                        state_result.release_audit_trace_status
                    ),
                    release_audit_trace_class_id=(
                        state_result.release_audit_trace_class_id
                    ),
                    release_audit_trace_context=(
                        state_result.release_audit_trace_context
                    ),
                ),
            },
            tags=("case-episode", "fallback"),
        )
        return updated

    def _review_payload(
        self,
        *,
        review_mode: str | None,
        review_threshold_id: str | None,
        review_playbook_reference: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if review_mode is not None:
            payload["review_mode"] = review_mode
        if review_threshold_id is not None:
            payload["review_threshold_id"] = review_threshold_id
        if review_playbook_reference is not None:
            payload["review_playbook_reference"] = review_playbook_reference
        return payload

    def _review_packet_payload(
        self,
        *,
        review_packet_status: str | None,
        review_packet_handoff_ready: bool | None,
        review_packet_id: str | None,
        review_packet_template_id: str | None,
        review_packet_reason_class: str | None,
        review_packet_scope: str | None,
        review_packet_handoff_channel: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if review_packet_status is not None:
            payload["review_packet_status"] = review_packet_status
        if review_packet_handoff_ready is not None:
            payload["review_packet_handoff_ready"] = review_packet_handoff_ready
        if review_packet_id is not None:
            payload["review_packet_id"] = review_packet_id
        if review_packet_template_id is not None:
            payload["review_packet_template_id"] = review_packet_template_id
        if review_packet_reason_class is not None:
            payload["review_packet_reason_class"] = review_packet_reason_class
        if review_packet_scope is not None:
            payload["review_packet_scope"] = review_packet_scope
        if review_packet_handoff_channel is not None:
            payload["review_packet_handoff_channel"] = review_packet_handoff_channel
        return payload

    def _review_resolution_payload(
        self,
        *,
        review_resolution_status: str | None,
        review_resolution_id: str | None,
        review_resolution_class_id: str | None,
        review_resolution_outcome: str | None,
        review_resolution_state: str | None,
        review_disposition_class_id: str | None,
        review_disposition_state: str | None,
        review_closure_state: str | None,
        review_closure_quality: str | None,
        review_resolution_terminality: bool | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if review_resolution_status is not None:
            payload["review_resolution_status"] = review_resolution_status
        if review_resolution_id is not None:
            payload["review_resolution_id"] = review_resolution_id
        if review_resolution_class_id is not None:
            payload["review_resolution_class_id"] = review_resolution_class_id
        if review_resolution_outcome is not None:
            payload["review_resolution_outcome"] = review_resolution_outcome
        if review_resolution_state is not None:
            payload["review_resolution_state"] = review_resolution_state
        if review_disposition_class_id is not None:
            payload["review_disposition_class_id"] = review_disposition_class_id
        if review_disposition_state is not None:
            payload["review_disposition_state"] = review_disposition_state
        if review_closure_state is not None:
            payload["review_closure_state"] = review_closure_state
        if review_closure_quality is not None:
            payload["review_closure_quality"] = review_closure_quality
        if review_resolution_terminality is not None:
            payload["review_resolution_terminality"] = review_resolution_terminality
        return payload

    def _recommendation_payload(
        self,
        *,
        recommendation_status: str | None,
        recommendation_id: str | None,
        recommendation_class_id: str | None,
        recommendation_template_id: str | None,
        recommendation_action_class: str | None,
        recommendation_advisory_status: str | None,
        recommendation_commitment_readiness: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if recommendation_status is not None:
            payload["recommendation_status"] = recommendation_status
        if recommendation_id is not None:
            payload["recommendation_id"] = recommendation_id
        if recommendation_class_id is not None:
            payload["recommendation_class_id"] = recommendation_class_id
        if recommendation_template_id is not None:
            payload["recommendation_template_id"] = recommendation_template_id
        if recommendation_action_class is not None:
            payload["recommendation_action_class"] = recommendation_action_class
        if recommendation_advisory_status is not None:
            payload["recommendation_advisory_status"] = recommendation_advisory_status
        if recommendation_commitment_readiness is not None:
            payload["recommendation_commitment_readiness"] = recommendation_commitment_readiness
        return payload

    def _policy_output_payload(
        self,
        *,
        policy_output_status: str | None,
        policy_output_id: str | None,
        policy_output_class_id: str | None,
        policy_output_template_id: str | None,
        policy_output_bounded_policy_posture: str | None,
        policy_output_action_boundary_posture: str | None,
        policy_output_promotion_safe_use: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if policy_output_status is not None:
            payload["policy_output_status"] = policy_output_status
        if policy_output_id is not None:
            payload["policy_output_id"] = policy_output_id
        if policy_output_class_id is not None:
            payload["policy_output_class_id"] = policy_output_class_id
        if policy_output_template_id is not None:
            payload["policy_output_template_id"] = policy_output_template_id
        if policy_output_bounded_policy_posture is not None:
            payload["policy_output_bounded_policy_posture"] = (
                policy_output_bounded_policy_posture
            )
        if policy_output_action_boundary_posture is not None:
            payload["policy_output_action_boundary_posture"] = (
                policy_output_action_boundary_posture
            )
        if policy_output_promotion_safe_use is not None:
            payload["policy_output_promotion_safe_use"] = policy_output_promotion_safe_use
        return payload

    def _portfolio_output_payload(
        self,
        *,
        portfolio_output_status: str | None,
        portfolio_output_id: str | None,
        portfolio_output_class_id: str | None,
        portfolio_output_template_id: str | None,
        portfolio_output_allocation_posture: str | None,
        portfolio_output_weight_posture: str | None,
        portfolio_output_action_boundary_posture: str | None,
        portfolio_output_promotion_safe_use: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if portfolio_output_status is not None:
            payload["portfolio_output_status"] = portfolio_output_status
        if portfolio_output_id is not None:
            payload["portfolio_output_id"] = portfolio_output_id
        if portfolio_output_class_id is not None:
            payload["portfolio_output_class_id"] = portfolio_output_class_id
        if portfolio_output_template_id is not None:
            payload["portfolio_output_template_id"] = portfolio_output_template_id
        if portfolio_output_allocation_posture is not None:
            payload["portfolio_output_allocation_posture"] = (
                portfolio_output_allocation_posture
            )
        if portfolio_output_weight_posture is not None:
            payload["portfolio_output_weight_posture"] = portfolio_output_weight_posture
        if portfolio_output_action_boundary_posture is not None:
            payload["portfolio_output_action_boundary_posture"] = (
                portfolio_output_action_boundary_posture
            )
        if portfolio_output_promotion_safe_use is not None:
            payload["portfolio_output_promotion_safe_use"] = (
                portfolio_output_promotion_safe_use
            )
        return payload

    def _action_instruction_payload(
        self,
        *,
        action_instruction_status: str | None,
        action_instruction_id: str | None,
        action_instruction_class_id: str | None,
        action_instruction_template_id: str | None,
        action_instruction_instruction_status: str | None,
        action_instruction_bounded_action_posture: str | None,
        action_instruction_execution_boundary_posture: str | None,
        action_instruction_promotion_safe_use: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if action_instruction_status is not None:
            payload["action_instruction_status"] = action_instruction_status
        if action_instruction_id is not None:
            payload["action_instruction_id"] = action_instruction_id
        if action_instruction_class_id is not None:
            payload["action_instruction_class_id"] = action_instruction_class_id
        if action_instruction_template_id is not None:
            payload["action_instruction_template_id"] = action_instruction_template_id
        if action_instruction_instruction_status is not None:
            payload["action_instruction_instruction_status"] = (
                action_instruction_instruction_status
            )
        if action_instruction_bounded_action_posture is not None:
            payload["action_instruction_bounded_action_posture"] = (
                action_instruction_bounded_action_posture
            )
        if action_instruction_execution_boundary_posture is not None:
            payload["action_instruction_execution_boundary_posture"] = (
                action_instruction_execution_boundary_posture
            )
        if action_instruction_promotion_safe_use is not None:
            payload["action_instruction_promotion_safe_use"] = (
                action_instruction_promotion_safe_use
            )
        return payload

    def _execution_request_payload(
        self,
        *,
        execution_request_status: str | None,
        execution_request_id: str | None,
        execution_request_class_id: str | None,
        execution_request_template_id: str | None,
        execution_request_readiness: str | None,
        execution_request_action_boundary_posture: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if execution_request_status is not None:
            payload["execution_request_status"] = execution_request_status
        if execution_request_id is not None:
            payload["execution_request_id"] = execution_request_id
        if execution_request_class_id is not None:
            payload["execution_request_class_id"] = execution_request_class_id
        if execution_request_template_id is not None:
            payload["execution_request_template_id"] = execution_request_template_id
        if execution_request_readiness is not None:
            payload["execution_request_readiness"] = execution_request_readiness
        if execution_request_action_boundary_posture is not None:
            payload["execution_request_action_boundary_posture"] = (
                execution_request_action_boundary_posture
            )
        return payload

    def _execution_dispatch_payload(
        self,
        *,
        execution_dispatch_status: str | None,
        execution_dispatch_id: str | None,
        execution_dispatch_class_id: str | None,
        execution_dispatch_template_id: str | None,
        execution_dispatch_readiness: str | None,
        execution_dispatch_boundary_posture: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if execution_dispatch_status is not None:
            payload["execution_dispatch_status"] = execution_dispatch_status
        if execution_dispatch_id is not None:
            payload["execution_dispatch_id"] = execution_dispatch_id
        if execution_dispatch_class_id is not None:
            payload["execution_dispatch_class_id"] = execution_dispatch_class_id
        if execution_dispatch_template_id is not None:
            payload["execution_dispatch_template_id"] = execution_dispatch_template_id
        if execution_dispatch_readiness is not None:
            payload["execution_dispatch_readiness"] = execution_dispatch_readiness
        if execution_dispatch_boundary_posture is not None:
            payload["execution_dispatch_boundary_posture"] = (
                execution_dispatch_boundary_posture
            )
        return payload

    def _execution_outcome_payload(
        self,
        *,
        execution_outcome_status: str | None,
        execution_outcome_id: str | None,
        execution_outcome_class_id: str | None,
        execution_outcome_template_id: str | None,
        execution_outcome_realized_result_class: str | None,
        execution_outcome_feedback_capture_readiness: str | None,
        execution_outcome_expected_relation: str | None,
        execution_outcome_comparison_posture: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if execution_outcome_status is not None:
            payload["execution_outcome_status"] = execution_outcome_status
        if execution_outcome_id is not None:
            payload["execution_outcome_id"] = execution_outcome_id
        if execution_outcome_class_id is not None:
            payload["execution_outcome_class_id"] = execution_outcome_class_id
        if execution_outcome_template_id is not None:
            payload["execution_outcome_template_id"] = execution_outcome_template_id
        if execution_outcome_realized_result_class is not None:
            payload["execution_outcome_realized_result_class"] = (
                execution_outcome_realized_result_class
            )
        if execution_outcome_feedback_capture_readiness is not None:
            payload["execution_outcome_feedback_capture_readiness"] = (
                execution_outcome_feedback_capture_readiness
            )
        if execution_outcome_expected_relation is not None:
            payload["execution_outcome_expected_relation"] = (
                execution_outcome_expected_relation
            )
        if execution_outcome_comparison_posture is not None:
            payload["execution_outcome_comparison_posture"] = (
                execution_outcome_comparison_posture
            )
        return payload

    def _post_mortem_payload(
        self,
        *,
        post_mortem_judgment_status: str | None,
        post_mortem_judgment_id: str | None,
        post_mortem_judgment_class_id: str | None,
        post_mortem_judgment_template_id: str | None,
        post_mortem_primary_attribution_category: str | None,
        post_mortem_evidence_quality: str | None,
        post_mortem_confidence_posture: str | None,
        post_mortem_learning_direction: str | None,
        post_mortem_comparison_posture: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if post_mortem_judgment_status is not None:
            payload["post_mortem_judgment_status"] = post_mortem_judgment_status
        if post_mortem_judgment_id is not None:
            payload["post_mortem_judgment_id"] = post_mortem_judgment_id
        if post_mortem_judgment_class_id is not None:
            payload["post_mortem_judgment_class_id"] = (
                post_mortem_judgment_class_id
            )
        if post_mortem_judgment_template_id is not None:
            payload["post_mortem_judgment_template_id"] = (
                post_mortem_judgment_template_id
            )
        if post_mortem_primary_attribution_category is not None:
            payload["post_mortem_primary_attribution_category"] = (
                post_mortem_primary_attribution_category
            )
        if post_mortem_evidence_quality is not None:
            payload["post_mortem_evidence_quality"] = post_mortem_evidence_quality
        if post_mortem_confidence_posture is not None:
            payload["post_mortem_confidence_posture"] = (
                post_mortem_confidence_posture
            )
        if post_mortem_learning_direction is not None:
            payload["post_mortem_learning_direction"] = (
                post_mortem_learning_direction
            )
        if post_mortem_comparison_posture is not None:
            payload["post_mortem_comparison_posture"] = (
                post_mortem_comparison_posture
            )
        return payload

    def _policy_learning_evidence_payload(
        self,
        *,
        policy_learning_evidence_admission_status: str | None,
        policy_learning_evidence_admission_id: str | None,
        policy_learning_evidence_class_id: str | None,
        policy_learning_evidence_template_id: str | None,
        policy_learning_evidence_admission_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if policy_learning_evidence_admission_status is not None:
            payload["policy_learning_evidence_admission_status"] = (
                policy_learning_evidence_admission_status
            )
        if policy_learning_evidence_admission_id is not None:
            payload["policy_learning_evidence_admission_id"] = (
                policy_learning_evidence_admission_id
            )
        if policy_learning_evidence_class_id is not None:
            payload["policy_learning_evidence_class_id"] = (
                policy_learning_evidence_class_id
            )
        if policy_learning_evidence_template_id is not None:
            payload["policy_learning_evidence_template_id"] = (
                policy_learning_evidence_template_id
            )
        if policy_learning_evidence_admission_context is not None:
            payload["policy_learning_evidence_admission_context"] = dict(
                policy_learning_evidence_admission_context
            )
        return payload

    def _policy_learning_update_threshold_payload(
        self,
        *,
        policy_learning_update_threshold_status: str | None,
        policy_learning_update_threshold_id: str | None,
        policy_learning_update_threshold_class_id: str | None,
        policy_learning_update_threshold_template_id: str | None,
        policy_learning_update_threshold_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if policy_learning_update_threshold_status is not None:
            payload["policy_learning_update_threshold_status"] = (
                policy_learning_update_threshold_status
            )
        if policy_learning_update_threshold_id is not None:
            payload["policy_learning_update_threshold_id"] = (
                policy_learning_update_threshold_id
            )
        if policy_learning_update_threshold_class_id is not None:
            payload["policy_learning_update_threshold_class_id"] = (
                policy_learning_update_threshold_class_id
            )
        if policy_learning_update_threshold_template_id is not None:
            payload["policy_learning_update_threshold_template_id"] = (
                policy_learning_update_threshold_template_id
            )
        if policy_learning_update_threshold_context is not None:
            payload["policy_learning_update_threshold_context"] = dict(
                policy_learning_update_threshold_context
            )
        return payload

    def _policy_learning_update_approval_payload(
        self,
        *,
        policy_learning_update_approval_status: str | None,
        policy_learning_update_approval_class_id: str | None,
        policy_learning_update_approval_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if policy_learning_update_approval_status is not None:
            payload["policy_learning_update_approval_status"] = (
                policy_learning_update_approval_status
            )
        if policy_learning_update_approval_class_id is not None:
            payload["policy_learning_update_approval_class_id"] = (
                policy_learning_update_approval_class_id
            )
        if policy_learning_update_approval_context is not None:
            payload["policy_learning_update_approval_context"] = dict(
                policy_learning_update_approval_context
            )
        return payload

    def _policy_learning_update_preparation_payload(
        self,
        *,
        policy_learning_update_preparation_status: str | None,
        policy_learning_update_preparation_class_id: str | None,
        policy_learning_update_preparation_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if policy_learning_update_preparation_status is not None:
            payload["policy_learning_update_preparation_status"] = (
                policy_learning_update_preparation_status
            )
        if policy_learning_update_preparation_class_id is not None:
            payload["policy_learning_update_preparation_class_id"] = (
                policy_learning_update_preparation_class_id
            )
        if policy_learning_update_preparation_context is not None:
            payload["policy_learning_update_preparation_context"] = dict(
                policy_learning_update_preparation_context
            )
        return payload

    def _policy_learning_update_mutation_planning_payload(
        self,
        *,
        policy_learning_update_mutation_planning_status: str | None,
        policy_learning_update_mutation_planning_class_id: str | None,
        policy_learning_update_mutation_planning_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if policy_learning_update_mutation_planning_status is not None:
            payload["policy_learning_update_mutation_planning_status"] = (
                policy_learning_update_mutation_planning_status
            )
        if policy_learning_update_mutation_planning_class_id is not None:
            payload["policy_learning_update_mutation_planning_class_id"] = (
                policy_learning_update_mutation_planning_class_id
            )
        if policy_learning_update_mutation_planning_context is not None:
            payload["policy_learning_update_mutation_planning_context"] = dict(
                policy_learning_update_mutation_planning_context
            )
        return payload

    def _policy_learning_update_mutation_execution_payload(
        self,
        *,
        policy_learning_update_mutation_execution_status: str | None,
        policy_learning_update_mutation_execution_class_id: str | None,
        policy_learning_update_mutation_execution_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if policy_learning_update_mutation_execution_status is not None:
            payload["policy_learning_update_mutation_execution_status"] = (
                policy_learning_update_mutation_execution_status
            )
        if policy_learning_update_mutation_execution_class_id is not None:
            payload["policy_learning_update_mutation_execution_class_id"] = (
                policy_learning_update_mutation_execution_class_id
            )
        if policy_learning_update_mutation_execution_context is not None:
            payload["policy_learning_update_mutation_execution_context"] = dict(
                policy_learning_update_mutation_execution_context
            )
        return payload

    def _promotion_readiness_payload(
        self,
        *,
        promotion_readiness_status: str | None,
        promotion_readiness_class_id: str | None,
        promotion_readiness_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if promotion_readiness_status is not None:
            payload["promotion_readiness_status"] = promotion_readiness_status
        if promotion_readiness_class_id is not None:
            payload["promotion_readiness_class_id"] = promotion_readiness_class_id
        if promotion_readiness_context is not None:
            payload["promotion_readiness_context"] = dict(
                promotion_readiness_context
            )
        return payload

    def _rollout_scope_payload(
        self,
        *,
        rollout_scope_status: str | None,
        rollout_scope_class_id: str | None,
        rollout_scope_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if rollout_scope_status is not None:
            payload["rollout_scope_status"] = rollout_scope_status
        if rollout_scope_class_id is not None:
            payload["rollout_scope_class_id"] = rollout_scope_class_id
        if rollout_scope_context is not None:
            payload["rollout_scope_context"] = dict(rollout_scope_context)
        return payload

    def _rollback_trigger_payload(
        self,
        *,
        rollback_trigger_status: str | None,
        rollback_trigger_class_id: str | None,
        rollback_trigger_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if rollback_trigger_status is not None:
            payload["rollback_trigger_status"] = rollback_trigger_status
        if rollback_trigger_class_id is not None:
            payload["rollback_trigger_class_id"] = rollback_trigger_class_id
        if rollback_trigger_context is not None:
            payload["rollback_trigger_context"] = dict(rollback_trigger_context)
        return payload

    def _release_watch_discipline_payload(
        self,
        *,
        release_watch_discipline_status: str | None,
        release_watch_discipline_class_id: str | None,
        release_watch_discipline_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if release_watch_discipline_status is not None:
            payload["release_watch_discipline_status"] = (
                release_watch_discipline_status
            )
        if release_watch_discipline_class_id is not None:
            payload["release_watch_discipline_class_id"] = (
                release_watch_discipline_class_id
            )
        if release_watch_discipline_context is not None:
            payload["release_watch_discipline_context"] = dict(
                release_watch_discipline_context
            )
        return payload

    def _release_confirmation_payload(
        self,
        *,
        release_confirmation_status: str | None,
        release_confirmation_class_id: str | None,
        release_confirmation_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if release_confirmation_status is not None:
            payload["release_confirmation_status"] = release_confirmation_status
        if release_confirmation_class_id is not None:
            payload["release_confirmation_class_id"] = release_confirmation_class_id
        if release_confirmation_context is not None:
            payload["release_confirmation_context"] = dict(
                release_confirmation_context
            )
        return payload

    def _production_entitlement_check_payload(
        self,
        *,
        production_entitlement_check_status: str | None,
        production_entitlement_check_class_id: str | None,
        production_entitlement_check_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if production_entitlement_check_status is not None:
            payload["production_entitlement_check_status"] = (
                production_entitlement_check_status
            )
        if production_entitlement_check_class_id is not None:
            payload["production_entitlement_check_class_id"] = (
                production_entitlement_check_class_id
            )
        if production_entitlement_check_context is not None:
            payload["production_entitlement_check_context"] = dict(
                production_entitlement_check_context
            )
        return payload

    def _contained_rollback_payload(
        self,
        *,
        contained_rollback_status: str | None,
        contained_rollback_class_id: str | None,
        contained_rollback_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if contained_rollback_status is not None:
            payload["contained_rollback_status"] = contained_rollback_status
        if contained_rollback_class_id is not None:
            payload["contained_rollback_class_id"] = contained_rollback_class_id
        if contained_rollback_context is not None:
            payload["contained_rollback_context"] = dict(contained_rollback_context)
        return payload

    def _release_audit_trace_payload(
        self,
        *,
        release_audit_trace_status: str | None,
        release_audit_trace_class_id: str | None,
        release_audit_trace_context: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if release_audit_trace_status is not None:
            payload["release_audit_trace_status"] = release_audit_trace_status
        if release_audit_trace_class_id is not None:
            payload["release_audit_trace_class_id"] = (
                release_audit_trace_class_id
            )
        if release_audit_trace_context is not None:
            payload["release_audit_trace_context"] = dict(
                release_audit_trace_context
            )
        return payload

    def _validate_features(
        self,
        feature_names: Sequence[str],
        case_type_definition: CaseTypeDefinition,
    ) -> None:
        for feature_name in feature_names:
            feature = self._feature_lookup.get_feature(feature_name)
            if feature is None:
                raise EpisodeEntryValidationError(
                    f"Feature '{feature_name}' is not registered and cannot be attached to an episode."
                )
            if feature.namespace not in case_type_definition.allowed_feature_namespaces:
                raise EpisodeEntryValidationError(
                    f"Feature '{feature_name}' is outside the allowed namespaces for case type '{case_type_definition.case_type}'."
                )

    def _persist_episode(
        self,
        episode: CaseEpisode,
        *,
        correlation_id: str,
        actor_id: str,
    ) -> None:
        self._contract_validator.validate_or_raise(
            "case_episode",
            episode.to_contract_dict(),
            correlation_id=correlation_id,
            entity_type="case_episode",
            entity_id=episode.episode_id,
            actor_id=actor_id,
        )
        self._repository.save(episode)

    def _require_episode(self, episode_id: str) -> CaseEpisode:
        episode = self._repository.get(episode_id)
        if episode is None:
            raise CaseEpisodeRepositoryError(f"Episode '{episode_id}' was not found.")
        return episode
