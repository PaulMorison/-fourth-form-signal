from __future__ import annotations

"""Deterministic evaluation for governed review thresholds.

Canon ownership:
- Evaluates threshold-trigger conditions against explicit routed and actor
  context.
- Does not execute review workflow, escalation handling, or playbook meaning.
"""

from dataclasses import dataclass
from typing import Mapping

from decision.review.threshold_registry import (
    CalibrationProfileDefinition,
    ReviewThresholdDefinition,
)


@dataclass(frozen=True)
class ReviewThresholdEvaluation:
    threshold_id: str
    trigger_class: str
    configured_review_mode: str
    outcome_kind: str
    reason: str
    value_source: str
    comparison_value_text: str
    actual_value_text: str | None = None
    calibrated_comparison_value_text: str | None = None
    calibration_profile_id: str | None = None
    fallback_review_mode: str | None = None
    playbook_reference: str | None = None
    required_context_fields: tuple[str, ...] = ()
    calibration_applied: bool = False
    fallback_review_mode_applied: bool = False


class ThresholdEvaluator:
    """Evaluates a single governed review threshold against explicit context."""

    def evaluate(
        self,
        threshold: ReviewThresholdDefinition,
        *,
        context: Mapping[str, object],
        routing_review_required: bool,
        authority_review_required: bool,
        calibration_profile: CalibrationProfileDefinition | None,
    ) -> ReviewThresholdEvaluation:
        missing_fields = tuple(
            field for field in threshold.required_context_fields if field not in context
        )
        if missing_fields:
            return ReviewThresholdEvaluation(
                threshold_id=threshold.threshold_id,
                trigger_class=threshold.trigger_class,
                configured_review_mode=threshold.review_mode,
                outcome_kind="blocked",
                reason=(
                    f"Threshold '{threshold.threshold_id}' requires context fields {list(missing_fields)}."
                ),
                value_source=threshold.value_source,
                comparison_value_text=threshold.comparison_value,
                fallback_review_mode=threshold.fallback_review_mode,
                playbook_reference=threshold.playbook_reference,
                required_context_fields=threshold.required_context_fields,
            )

        if threshold.value_source not in context:
            return ReviewThresholdEvaluation(
                threshold_id=threshold.threshold_id,
                trigger_class=threshold.trigger_class,
                configured_review_mode=threshold.review_mode,
                outcome_kind="blocked",
                reason=(
                    f"Threshold '{threshold.threshold_id}' cannot resolve value_source '{threshold.value_source}'."
                ),
                value_source=threshold.value_source,
                comparison_value_text=threshold.comparison_value,
                fallback_review_mode=threshold.fallback_review_mode,
                playbook_reference=threshold.playbook_reference,
                required_context_fields=threshold.required_context_fields,
            )

        actual_value = context[threshold.value_source]
        if threshold.threshold_type == "numeric_comparison":
            return self._evaluate_numeric(
                threshold,
                actual_value=actual_value,
                routing_review_required=routing_review_required,
                authority_review_required=authority_review_required,
                calibration_profile=calibration_profile,
            )

        return self._evaluate_boolean(
            threshold,
            actual_value=actual_value,
            routing_review_required=routing_review_required,
            authority_review_required=authority_review_required,
        )

    def _evaluate_numeric(
        self,
        threshold: ReviewThresholdDefinition,
        *,
        actual_value: object,
        routing_review_required: bool,
        authority_review_required: bool,
        calibration_profile: CalibrationProfileDefinition | None,
    ) -> ReviewThresholdEvaluation:
        actual_number = self._parse_number(actual_value)
        if actual_number is None:
            return self._type_blocked(threshold, actual_value)

        comparison_number = self._parse_number(threshold.comparison_value)
        if comparison_number is None:
            return ReviewThresholdEvaluation(
                threshold_id=threshold.threshold_id,
                trigger_class=threshold.trigger_class,
                configured_review_mode=threshold.review_mode,
                outcome_kind="blocked",
                reason=(
                    f"Threshold '{threshold.threshold_id}' comparison_value '{threshold.comparison_value}' is not a valid numeric threshold."
                ),
                value_source=threshold.value_source,
                comparison_value_text=threshold.comparison_value,
                actual_value_text=self._to_text(actual_value),
                fallback_review_mode=threshold.fallback_review_mode,
                playbook_reference=threshold.playbook_reference,
                required_context_fields=threshold.required_context_fields,
            )

        calibrated_number = comparison_number
        calibration_applied = False
        if calibration_profile is not None:
            calibrated_number = self._apply_calibration(comparison_number, calibration_profile)
            calibration_applied = True

        if self._compare_numeric(actual_number, calibrated_number, threshold.operator):
            return ReviewThresholdEvaluation(
                threshold_id=threshold.threshold_id,
                trigger_class=threshold.trigger_class,
                configured_review_mode=threshold.review_mode,
                outcome_kind=threshold.review_mode,
                reason=(
                    f"Threshold '{threshold.threshold_id}' triggered governed review mode '{threshold.review_mode}'."
                ),
                value_source=threshold.value_source,
                comparison_value_text=threshold.comparison_value,
                actual_value_text=self._to_text(actual_value),
                calibrated_comparison_value_text=self._to_text(calibrated_number),
                calibration_profile_id=(
                    calibration_profile.calibration_profile_id if calibration_profile is not None else None
                ),
                fallback_review_mode=threshold.fallback_review_mode,
                playbook_reference=threshold.playbook_reference,
                required_context_fields=threshold.required_context_fields,
                calibration_applied=calibration_applied,
            )

        if threshold.fallback_review_mode is not None and (
            routing_review_required or authority_review_required
        ):
            return ReviewThresholdEvaluation(
                threshold_id=threshold.threshold_id,
                trigger_class=threshold.trigger_class,
                configured_review_mode=threshold.review_mode,
                outcome_kind=threshold.fallback_review_mode,
                reason=(
                    f"Threshold '{threshold.threshold_id}' did not cross its calibrated comparison value and therefore applied fallback review mode '{threshold.fallback_review_mode}'."
                ),
                value_source=threshold.value_source,
                comparison_value_text=threshold.comparison_value,
                actual_value_text=self._to_text(actual_value),
                calibrated_comparison_value_text=self._to_text(calibrated_number),
                calibration_profile_id=(
                    calibration_profile.calibration_profile_id if calibration_profile is not None else None
                ),
                fallback_review_mode=threshold.fallback_review_mode,
                playbook_reference=threshold.playbook_reference,
                required_context_fields=threshold.required_context_fields,
                calibration_applied=calibration_applied,
                fallback_review_mode_applied=True,
            )

        return ReviewThresholdEvaluation(
            threshold_id=threshold.threshold_id,
            trigger_class=threshold.trigger_class,
            configured_review_mode=threshold.review_mode,
            outcome_kind="not_triggered",
            reason=(
                f"Threshold '{threshold.threshold_id}' did not trigger review mode '{threshold.review_mode}'."
            ),
            value_source=threshold.value_source,
            comparison_value_text=threshold.comparison_value,
            actual_value_text=self._to_text(actual_value),
            calibrated_comparison_value_text=self._to_text(calibrated_number),
            calibration_profile_id=(
                calibration_profile.calibration_profile_id if calibration_profile is not None else None
            ),
            fallback_review_mode=threshold.fallback_review_mode,
            playbook_reference=threshold.playbook_reference,
            required_context_fields=threshold.required_context_fields,
            calibration_applied=calibration_applied,
        )

    def _evaluate_boolean(
        self,
        threshold: ReviewThresholdDefinition,
        *,
        actual_value: object,
        routing_review_required: bool,
        authority_review_required: bool,
    ) -> ReviewThresholdEvaluation:
        actual_boolean = self._parse_boolean(actual_value)
        comparison_boolean = self._parse_boolean(threshold.comparison_value)
        if actual_boolean is None or comparison_boolean is None:
            return self._type_blocked(threshold, actual_value)

        if self._compare_boolean(actual_boolean, comparison_boolean, threshold.operator):
            return ReviewThresholdEvaluation(
                threshold_id=threshold.threshold_id,
                trigger_class=threshold.trigger_class,
                configured_review_mode=threshold.review_mode,
                outcome_kind=threshold.review_mode,
                reason=(
                    f"Threshold '{threshold.threshold_id}' triggered governed review mode '{threshold.review_mode}'."
                ),
                value_source=threshold.value_source,
                comparison_value_text=threshold.comparison_value,
                actual_value_text=self._to_text(actual_value),
                fallback_review_mode=threshold.fallback_review_mode,
                playbook_reference=threshold.playbook_reference,
                required_context_fields=threshold.required_context_fields,
            )

        if threshold.fallback_review_mode is not None and (
            routing_review_required or authority_review_required
        ):
            return ReviewThresholdEvaluation(
                threshold_id=threshold.threshold_id,
                trigger_class=threshold.trigger_class,
                configured_review_mode=threshold.review_mode,
                outcome_kind=threshold.fallback_review_mode,
                reason=(
                    f"Threshold '{threshold.threshold_id}' did not fire and therefore applied fallback review mode '{threshold.fallback_review_mode}'."
                ),
                value_source=threshold.value_source,
                comparison_value_text=threshold.comparison_value,
                actual_value_text=self._to_text(actual_value),
                fallback_review_mode=threshold.fallback_review_mode,
                playbook_reference=threshold.playbook_reference,
                required_context_fields=threshold.required_context_fields,
                fallback_review_mode_applied=True,
            )

        return ReviewThresholdEvaluation(
            threshold_id=threshold.threshold_id,
            trigger_class=threshold.trigger_class,
            configured_review_mode=threshold.review_mode,
            outcome_kind="not_triggered",
            reason=(
                f"Threshold '{threshold.threshold_id}' did not trigger review mode '{threshold.review_mode}'."
            ),
            value_source=threshold.value_source,
            comparison_value_text=threshold.comparison_value,
            actual_value_text=self._to_text(actual_value),
            fallback_review_mode=threshold.fallback_review_mode,
            playbook_reference=threshold.playbook_reference,
            required_context_fields=threshold.required_context_fields,
        )

    def _apply_calibration(
        self,
        comparison_value: float,
        calibration_profile: CalibrationProfileDefinition,
    ) -> float:
        if calibration_profile.adjustment_kind == "offset":
            return comparison_value + calibration_profile.adjustment_value
        return comparison_value * calibration_profile.adjustment_value

    def _compare_numeric(self, actual: float, comparison: float, operator: str) -> bool:
        if operator == "gt":
            return actual > comparison
        if operator == "gte":
            return actual >= comparison
        if operator == "lt":
            return actual < comparison
        if operator == "lte":
            return actual <= comparison
        if operator == "eq":
            return actual == comparison
        return actual != comparison

    def _compare_boolean(self, actual: bool, comparison: bool, operator: str) -> bool:
        if operator == "eq":
            return actual is comparison
        if operator == "neq":
            return actual is not comparison
        return False

    def _parse_number(self, value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _parse_boolean(self, value: object) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "true":
                return True
            if normalized == "false":
                return False
        return None

    def _type_blocked(
        self,
        threshold: ReviewThresholdDefinition,
        actual_value: object,
    ) -> ReviewThresholdEvaluation:
        return ReviewThresholdEvaluation(
            threshold_id=threshold.threshold_id,
            trigger_class=threshold.trigger_class,
            configured_review_mode=threshold.review_mode,
            outcome_kind="blocked",
            reason=(
                f"Threshold '{threshold.threshold_id}' cannot compare value_source '{threshold.value_source}' with provided value '{self._to_text(actual_value)}'."
            ),
            value_source=threshold.value_source,
            comparison_value_text=threshold.comparison_value,
            actual_value_text=self._to_text(actual_value),
            fallback_review_mode=threshold.fallback_review_mode,
            playbook_reference=threshold.playbook_reference,
            required_context_fields=threshold.required_context_fields,
        )

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
