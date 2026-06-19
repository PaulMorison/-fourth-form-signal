from __future__ import annotations

"""Registry-backed review thresholds, trigger classes, and calibration profiles.

Canon ownership:
- Owns governed threshold identity, trigger-class identity, and calibration
  metadata for review-entry evaluation.
- Does not execute review workflow, routing, lifecycle validation, or
  recommendation meaning.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_REVIEW_MODES = {"required", "optional"}
_VALID_THRESHOLD_TYPES = {"numeric_comparison", "boolean_signal"}
_VALID_OPERATORS = {"gt", "gte", "lt", "lte", "eq", "neq"}
_VALID_ADJUSTMENT_KINDS = {"offset", "multiplier"}


class ReviewThresholdRegistryError(ValueError):
    """Base error for governed review-threshold registry failures."""


@dataclass(frozen=True)
class ReviewThresholdDefinition:
    threshold_id: str
    semantic_scope: str
    router_rule_id: str
    transition_name: str
    route_name: str | None
    trigger_class: str
    review_mode: str
    threshold_type: str
    operator: str
    value_source: str
    comparison_value: str
    calibration_profile_id: str | None
    required_context_fields: tuple[str, ...]
    fallback_review_mode: str | None
    playbook_reference: str | None
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class TriggerClassDefinition:
    trigger_class: str
    description: str
    allowed_review_modes: tuple[str, ...]
    allows_fallback_review_mode: bool
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class CalibrationProfileDefinition:
    calibration_profile_id: str
    threshold_type: str
    adjustment_kind: str
    adjustment_value: float
    status: str
    lineage: Mapping[str, str]


class ReviewThresholdRegistry(Protocol):
    def find_thresholds(
        self,
        *,
        semantic_scope: str,
        router_rule_id: str,
        transition_name: str,
        route_name: str | None,
    ) -> Sequence[ReviewThresholdDefinition]:
        """Return active thresholds applicable to the routed transition."""

    def get_trigger_class(self, trigger_class: str) -> TriggerClassDefinition:
        """Return the named trigger class."""

    def get_calibration_profile(
        self,
        calibration_profile_id: str,
    ) -> CalibrationProfileDefinition:
        """Return the named calibration profile."""


class JsonThresholdRegistry:
    """Loads review thresholds, trigger classes, and calibration profiles."""

    def __init__(
        self,
        *,
        review_thresholds_path: Path,
        trigger_classes_path: Path,
        calibration_profiles_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._trigger_classes = self._load_trigger_classes(trigger_classes_path)
        self._calibration_profiles = self._load_calibration_profiles(calibration_profiles_path)
        self._thresholds = self._load_thresholds(review_thresholds_path)
        self._validate_cross_registry_links()

    def find_thresholds(
        self,
        *,
        semantic_scope: str,
        router_rule_id: str,
        transition_name: str,
        route_name: str | None,
    ) -> Sequence[ReviewThresholdDefinition]:
        return tuple(
            threshold
            for threshold in self._thresholds
            if threshold.status == "active"
            and threshold.semantic_scope == semantic_scope
            and threshold.router_rule_id == router_rule_id
            and threshold.transition_name == transition_name
            and (threshold.route_name is None or threshold.route_name == route_name)
        )

    def get_trigger_class(self, trigger_class: str) -> TriggerClassDefinition:
        try:
            return self._trigger_classes[trigger_class]
        except KeyError as error:
            raise ReviewThresholdRegistryError(
                f"Trigger class '{trigger_class}' is not registered."
            ) from error

    def get_calibration_profile(
        self,
        calibration_profile_id: str,
    ) -> CalibrationProfileDefinition:
        try:
            return self._calibration_profiles[calibration_profile_id]
        except KeyError as error:
            raise ReviewThresholdRegistryError(
                f"Calibration profile '{calibration_profile_id}' is not registered."
            ) from error

    def _load_trigger_classes(
        self,
        trigger_classes_path: Path,
    ) -> dict[str, TriggerClassDefinition]:
        content = json.loads(trigger_classes_path.read_text(encoding="utf-8"))
        trigger_classes: dict[str, TriggerClassDefinition] = {}
        for trigger_class_id, entry in content["trigger_classes"].items():
            self._contract_validator.validate_or_raise(
                "trigger_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="trigger_class",
                entity_id=trigger_class_id,
                emit_audit_events=False,
            )
            if entry["trigger_class"] != trigger_class_id:
                raise ReviewThresholdRegistryError(
                    f"Trigger class key '{trigger_class_id}' must match trigger_class '{entry['trigger_class']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReviewThresholdRegistryError(
                    f"Trigger class '{trigger_class_id}' has invalid status '{entry['status']}'."
                )
            allowed_review_modes = tuple(entry["allowed_review_modes"])
            invalid_review_modes = set(allowed_review_modes).difference(_VALID_REVIEW_MODES)
            if invalid_review_modes:
                raise ReviewThresholdRegistryError(
                    f"Trigger class '{trigger_class_id}' has invalid allowed_review_modes {sorted(invalid_review_modes)}."
                )
            trigger_classes[trigger_class_id] = TriggerClassDefinition(
                trigger_class=entry["trigger_class"],
                description=entry["description"],
                allowed_review_modes=allowed_review_modes,
                allows_fallback_review_mode=bool(entry["allows_fallback_review_mode"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return trigger_classes

    def _load_calibration_profiles(
        self,
        calibration_profiles_path: Path,
    ) -> dict[str, CalibrationProfileDefinition]:
        content = json.loads(calibration_profiles_path.read_text(encoding="utf-8"))
        calibration_profiles: dict[str, CalibrationProfileDefinition] = {}
        for profile_id, entry in content["calibration_profiles"].items():
            self._contract_validator.validate_or_raise(
                "calibration_profile",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="calibration_profile",
                entity_id=profile_id,
                emit_audit_events=False,
            )
            if entry["calibration_profile_id"] != profile_id:
                raise ReviewThresholdRegistryError(
                    f"Calibration profile key '{profile_id}' must match calibration_profile_id '{entry['calibration_profile_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReviewThresholdRegistryError(
                    f"Calibration profile '{profile_id}' has invalid status '{entry['status']}'."
                )
            if entry["threshold_type"] not in _VALID_THRESHOLD_TYPES:
                raise ReviewThresholdRegistryError(
                    f"Calibration profile '{profile_id}' has invalid threshold_type '{entry['threshold_type']}'."
                )
            if entry["adjustment_kind"] not in _VALID_ADJUSTMENT_KINDS:
                raise ReviewThresholdRegistryError(
                    f"Calibration profile '{profile_id}' has invalid adjustment_kind '{entry['adjustment_kind']}'."
                )
            calibration_profiles[profile_id] = CalibrationProfileDefinition(
                calibration_profile_id=entry["calibration_profile_id"],
                threshold_type=entry["threshold_type"],
                adjustment_kind=entry["adjustment_kind"],
                adjustment_value=float(entry["adjustment_value"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return calibration_profiles

    def _load_thresholds(
        self,
        review_thresholds_path: Path,
    ) -> tuple[ReviewThresholdDefinition, ...]:
        content = json.loads(review_thresholds_path.read_text(encoding="utf-8"))
        thresholds: list[ReviewThresholdDefinition] = []
        threshold_ids: set[str] = set()
        for entry in content["review_thresholds"]:
            threshold_id = entry["threshold_id"]
            self._contract_validator.validate_or_raise(
                "review_threshold",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="review_threshold",
                entity_id=threshold_id,
                emit_audit_events=False,
            )
            if threshold_id in threshold_ids:
                raise ReviewThresholdRegistryError(
                    f"Duplicate threshold_id '{threshold_id}' found in review thresholds registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReviewThresholdRegistryError(
                    f"Review threshold '{threshold_id}' has invalid status '{entry['status']}'."
                )
            if entry["review_mode"] not in _VALID_REVIEW_MODES:
                raise ReviewThresholdRegistryError(
                    f"Review threshold '{threshold_id}' has invalid review_mode '{entry['review_mode']}'."
                )
            if entry["threshold_type"] not in _VALID_THRESHOLD_TYPES:
                raise ReviewThresholdRegistryError(
                    f"Review threshold '{threshold_id}' has invalid threshold_type '{entry['threshold_type']}'."
                )
            if entry["operator"] not in _VALID_OPERATORS:
                raise ReviewThresholdRegistryError(
                    f"Review threshold '{threshold_id}' has invalid operator '{entry['operator']}'."
                )
            thresholds.append(
                ReviewThresholdDefinition(
                    threshold_id=threshold_id,
                    semantic_scope=entry["semantic_scope"],
                    router_rule_id=entry["router_rule_id"],
                    transition_name=entry["transition_name"],
                    route_name=entry.get("route_name"),
                    trigger_class=entry["trigger_class"],
                    review_mode=entry["review_mode"],
                    threshold_type=entry["threshold_type"],
                    operator=entry["operator"],
                    value_source=entry["value_source"],
                    comparison_value=entry["comparison_value"],
                    calibration_profile_id=entry.get("calibration_profile_id"),
                    required_context_fields=tuple(entry["required_context_fields"]),
                    fallback_review_mode=entry.get("fallback_review_mode"),
                    playbook_reference=entry.get("playbook_reference"),
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                )
            )
            threshold_ids.add(threshold_id)
        return tuple(thresholds)

    def _validate_cross_registry_links(self) -> None:
        for threshold in self._thresholds:
            trigger_class = self._trigger_classes.get(threshold.trigger_class)
            if trigger_class is None:
                raise ReviewThresholdRegistryError(
                    f"Review threshold '{threshold.threshold_id}' references unknown trigger_class '{threshold.trigger_class}'."
                )
            if threshold.review_mode not in trigger_class.allowed_review_modes:
                raise ReviewThresholdRegistryError(
                    f"Review threshold '{threshold.threshold_id}' uses review_mode '{threshold.review_mode}' not allowed by trigger class '{threshold.trigger_class}'."
                )
            if threshold.fallback_review_mode is not None:
                if not trigger_class.allows_fallback_review_mode:
                    raise ReviewThresholdRegistryError(
                        f"Review threshold '{threshold.threshold_id}' declares fallback_review_mode but trigger class '{threshold.trigger_class}' does not allow fallback review modes."
                    )
                if threshold.fallback_review_mode not in trigger_class.allowed_review_modes:
                    raise ReviewThresholdRegistryError(
                        f"Review threshold '{threshold.threshold_id}' declares invalid fallback_review_mode '{threshold.fallback_review_mode}'."
                    )
            if threshold.calibration_profile_id is not None:
                calibration_profile = self._calibration_profiles.get(threshold.calibration_profile_id)
                if calibration_profile is None:
                    raise ReviewThresholdRegistryError(
                        f"Review threshold '{threshold.threshold_id}' references unknown calibration profile '{threshold.calibration_profile_id}'."
                    )
                if threshold.threshold_type != calibration_profile.threshold_type:
                    raise ReviewThresholdRegistryError(
                        f"Review threshold '{threshold.threshold_id}' threshold_type '{threshold.threshold_type}' does not match calibration profile '{calibration_profile.calibration_profile_id}' threshold_type '{calibration_profile.threshold_type}'."
                    )
            if threshold.threshold_type == "boolean_signal" and threshold.calibration_profile_id is not None:
                raise ReviewThresholdRegistryError(
                    f"Review threshold '{threshold.threshold_id}' cannot apply calibration to boolean_signal thresholds."
                )
