from __future__ import annotations

"""Registry-backed lifecycle state definitions for governed case progression.

Canon ownership:
- Holds governed state identity, transition classes, entry semantics, and
  fallback posture in machine-readable form.
- Does not perform authority checks, routing, or orchestration updates.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Protocol


class StateModelRegistryError(ValueError):
    """Base error for lifecycle registry failures."""


class StateModelNotFoundError(StateModelRegistryError):
    """Raised when a state model is not registered."""


class StateDefinitionNotFoundError(StateModelRegistryError):
    """Raised when a governed state is not registered inside a state model."""


class TransitionDefinitionNotFoundError(StateModelRegistryError):
    """Raised when a governed transition is not registered inside a state model."""


@dataclass(frozen=True)
class GovernedStateDefinition:
    state_name: str
    semantic_scope: str
    entry_basis: str
    exit_basis: str
    allowed_transition_classes: tuple[str, ...]
    blocked_transition_classes: tuple[str, ...]


@dataclass(frozen=True)
class GovernedTransitionDefinition:
    transition_name: str
    from_state: str
    to_state: str
    transition_class: str
    authority_rule_id: str
    router_rule: str
    resulting_status: str
    allowed_current_statuses: tuple[str, ...]


@dataclass(frozen=True)
class StateModelDefinition:
    state_model_name: str
    semantic_scope: str
    initial_state: str
    entry_transition_name: str
    states: Mapping[str, GovernedStateDefinition]
    transitions: Mapping[str, GovernedTransitionDefinition]


class StateModelRegistry(Protocol):
    def get_state_model(self, state_model_name: str) -> StateModelDefinition:
        """Return the named state model definition."""

    def get_state(self, state_model_name: str, state_name: str) -> GovernedStateDefinition:
        """Return the named state definition."""

    def get_transition(
        self,
        state_model_name: str,
        transition_name: str,
    ) -> GovernedTransitionDefinition:
        """Return the named transition definition."""


class JsonStateModelRegistry:
    """Loads lifecycle state models from a checked-in registry file."""

    def __init__(self, registry_path: Path) -> None:
        content = json.loads(registry_path.read_text(encoding="utf-8"))
        self._state_models: dict[str, StateModelDefinition] = {}

        for state_model_name, entry in content["state_models"].items():
            semantic_scope = entry["semantic_scope"]
            states = {
                state_name: GovernedStateDefinition(
                    state_name=state_name,
                    semantic_scope=semantic_scope,
                    entry_basis=state_entry["entry_basis"],
                    exit_basis=state_entry["exit_basis"],
                    allowed_transition_classes=tuple(state_entry["allowed_transition_classes"]),
                    blocked_transition_classes=tuple(state_entry["blocked_transition_classes"]),
                )
                for state_name, state_entry in entry["states"].items()
            }
            transitions = {
                transition_entry["transition_name"]: GovernedTransitionDefinition(
                    transition_name=transition_entry["transition_name"],
                    from_state=transition_entry["from_state"],
                    to_state=transition_entry["to_state"],
                    transition_class=transition_entry["transition_class"],
                    authority_rule_id=transition_entry["authority_rule_id"],
                    router_rule=transition_entry["router_rule"],
                    resulting_status=transition_entry["resulting_status"],
                    allowed_current_statuses=tuple(transition_entry["allowed_current_statuses"]),
                )
                for transition_entry in entry["transitions"]
            }
            model = StateModelDefinition(
                state_model_name=state_model_name,
                semantic_scope=semantic_scope,
                initial_state=entry["initial_state"],
                entry_transition_name=entry["entry_transition_name"],
                states=states,
                transitions=transitions,
            )
            self._validate_model(model)
            self._state_models[state_model_name] = model

    def get_state_model(self, state_model_name: str) -> StateModelDefinition:
        try:
            return self._state_models[state_model_name]
        except KeyError as error:
            raise StateModelNotFoundError(
                f"State model '{state_model_name}' is not registered."
            ) from error

    def get_state(self, state_model_name: str, state_name: str) -> GovernedStateDefinition:
        model = self.get_state_model(state_model_name)
        try:
            return model.states[state_name]
        except KeyError as error:
            raise StateDefinitionNotFoundError(
                f"State '{state_name}' is not registered in state model '{state_model_name}'."
            ) from error

    def get_transition(
        self,
        state_model_name: str,
        transition_name: str,
    ) -> GovernedTransitionDefinition:
        model = self.get_state_model(state_model_name)
        try:
            return model.transitions[transition_name]
        except KeyError as error:
            raise TransitionDefinitionNotFoundError(
                f"Transition '{transition_name}' is not registered in state model '{state_model_name}'."
            ) from error

    def _validate_model(self, model: StateModelDefinition) -> None:
        if model.initial_state not in model.states:
            raise StateModelRegistryError(
                f"State model '{model.state_model_name}' has unknown initial state '{model.initial_state}'."
            )
        if model.entry_transition_name not in model.transitions:
            raise StateModelRegistryError(
                f"State model '{model.state_model_name}' has unknown entry transition '{model.entry_transition_name}'."
            )

        for transition in model.transitions.values():
            if transition.from_state != "__entry__" and transition.from_state not in model.states:
                raise StateModelRegistryError(
                    f"Transition '{transition.transition_name}' references unknown from_state '{transition.from_state}'."
                )
            if transition.to_state not in model.states:
                raise StateModelRegistryError(
                    f"Transition '{transition.transition_name}' references unknown to_state '{transition.to_state}'."
                )
            if transition.from_state != "__entry__":
                from_state = model.states[transition.from_state]
                if transition.transition_class not in from_state.allowed_transition_classes:
                    raise StateModelRegistryError(
                        f"Transition '{transition.transition_name}' uses class '{transition.transition_class}' "
                        f"not allowed from state '{transition.from_state}'."
                    )
                if transition.transition_class in from_state.blocked_transition_classes:
                    raise StateModelRegistryError(
                        f"Transition '{transition.transition_name}' uses blocked class '{transition.transition_class}' "
                        f"from state '{transition.from_state}'."
                    )
