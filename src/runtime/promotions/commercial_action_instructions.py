from __future__ import annotations

"""Authoritative governed commercial action-instruction seam.

This module converts governed diagnostics into a recommendation-only ranked
human action pack. It does not mutate thresholds, publish rules, registry
state, or model behavior.
"""

from dataclasses import asdict, dataclass
from typing import Optional

import pandas as pd

from runtime.promotions.commercial_outcome_attribution import (
    ATTRIBUTION_BLOCKED_INCONSISTENT_KEYS,
    ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA,
    ATTRIBUTION_NOT_YET_MATURE,
    ATTRIBUTION_READY,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_NONE,
    HARMFUL,
    INEFFECTIVE,
)
from runtime.promotions.commercial_policy_calibration import (
    CALIBRATION_LOW_COVERAGE,
    CALIBRATION_NOT_READY,
    HOLD_POLICY,
    LOOSEN_PUBLISH_POLICY,
    TIGHTEN_PUBLISH_POLICY,
)
from runtime.promotions.commercial_policy_simulator import (
    SIMULATION_BLOCKED_DEFECT,
    SIMULATION_LOW_COVERAGE,
    SIMULATION_NOT_COMPARABLE,
)

ACTION_PACK_READY = "ACTION_PACK_READY"
ACTION_PACK_LOW_EVIDENCE = "ACTION_PACK_LOW_EVIDENCE"
ACTION_PACK_BLOCKED_DEFECT = "ACTION_PACK_BLOCKED_DEFECT"
ACTION_PACK_NOT_COMPARABLE = "ACTION_PACK_NOT_COMPARABLE"

ATTENTION_IMMEDIATE = "ATTENTION_IMMEDIATE"
ATTENTION_HIGH = "ATTENTION_HIGH"
ATTENTION_NORMAL = "ATTENTION_NORMAL"
ATTENTION_LOW = "ATTENTION_LOW"

EVIDENCE_HIGH = "EVIDENCE_HIGH"
EVIDENCE_MEDIUM = "EVIDENCE_MEDIUM"
EVIDENCE_LOW = "EVIDENCE_LOW"
EVIDENCE_NONE = "EVIDENCE_NONE"

OWNER_OPERATOR = "OPERATOR"
OWNER_MODEL_OWNER = "MODEL_OWNER"

ACTION_REVIEW_HIGH_RISK_SEGMENT = "REVIEW_HIGH_RISK_SEGMENT"
ACTION_REVIEW_HIGH_IMPACT_SIMULATION = "REVIEW_HIGH_IMPACT_SIMULATION"
ACTION_TIGHTEN_POLICY_REVIEW = "TIGHTEN_POLICY_REVIEW"
ACTION_LOOSEN_POLICY_REVIEW = "LOOSEN_POLICY_REVIEW"
ACTION_HOLD_POLICY_MONITOR = "HOLD_POLICY_MONITOR"
ACTION_INVESTIGATE_HARMFUL_RECOMMENDATIONS = "INVESTIGATE_HARMFUL_RECOMMENDATIONS"
ACTION_INVESTIGATE_ARTIFICIAL_COLLAPSE = "INVESTIGATE_ARTIFICIAL_COLLAPSE"
ACTION_REVIEW_DUPLICATE_ONLY_NOOP = "REVIEW_DUPLICATE_ONLY_NOOP"
ACTION_REVIEW_LOW_COVERAGE_SEGMENT = "REVIEW_LOW_COVERAGE_SEGMENT"
ACTION_MONITOR_TRUE_ZERO_SEGMENT = "MONITOR_TRUE_ZERO_SEGMENT"
ACTION_MONITOR_COLD_START_SEGMENT = "MONITOR_COLD_START_SEGMENT"
ACTION_VALIDATE_STORE_OUTLIER = "VALIDATE_STORE_OUTLIER"
ACTION_MODEL_OWNER_THRESHOLD_REVIEW = "MODEL_OWNER_THRESHOLD_REVIEW"
ACTION_MODEL_OWNER_FEATURE_REVIEW = "MODEL_OWNER_FEATURE_REVIEW"
ACTION_MODEL_OWNER_DATA_QUALITY_REVIEW = "MODEL_OWNER_DATA_QUALITY_REVIEW"
ACTION_NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"

_REQUIRED_PRIORITY_QUEUE_COLUMNS = [
    "action_priority_rank",
    "action_class",
    "action_owner_class",
    "action_reason",
    "evidence_strength_class",
    "requires_human_review_flag",
    "safe_to_execute_as_manual_review_flag",
    "linked_segment_type",
    "linked_segment_value",
    "linked_store_number",
    "linked_promotion_id",
    "supporting_metric_summary",
]

_ACTION_BASE_SCORES = {
    ACTION_MODEL_OWNER_DATA_QUALITY_REVIEW: 100,
    ACTION_INVESTIGATE_HARMFUL_RECOMMENDATIONS: 97,
    ACTION_INVESTIGATE_ARTIFICIAL_COLLAPSE: 95,
    ACTION_REVIEW_HIGH_RISK_SEGMENT: 93,
    ACTION_REVIEW_HIGH_IMPACT_SIMULATION: 91,
    ACTION_TIGHTEN_POLICY_REVIEW: 88,
    ACTION_LOOSEN_POLICY_REVIEW: 87,
    ACTION_MODEL_OWNER_THRESHOLD_REVIEW: 85,
    ACTION_MODEL_OWNER_FEATURE_REVIEW: 83,
    ACTION_HOLD_POLICY_MONITOR: 79,
    ACTION_REVIEW_LOW_COVERAGE_SEGMENT: 74,
    ACTION_REVIEW_DUPLICATE_ONLY_NOOP: 68,
    ACTION_VALIDATE_STORE_OUTLIER: 61,
    ACTION_MONITOR_COLD_START_SEGMENT: 44,
    ACTION_MONITOR_TRUE_ZERO_SEGMENT: 42,
    ACTION_NO_ACTION_REQUIRED: 0,
}

_ACTION_ORDER = [
    ACTION_MODEL_OWNER_DATA_QUALITY_REVIEW,
    ACTION_INVESTIGATE_HARMFUL_RECOMMENDATIONS,
    ACTION_INVESTIGATE_ARTIFICIAL_COLLAPSE,
    ACTION_REVIEW_HIGH_RISK_SEGMENT,
    ACTION_REVIEW_HIGH_IMPACT_SIMULATION,
    ACTION_TIGHTEN_POLICY_REVIEW,
    ACTION_LOOSEN_POLICY_REVIEW,
    ACTION_MODEL_OWNER_THRESHOLD_REVIEW,
    ACTION_MODEL_OWNER_FEATURE_REVIEW,
    ACTION_HOLD_POLICY_MONITOR,
    ACTION_REVIEW_LOW_COVERAGE_SEGMENT,
    ACTION_REVIEW_DUPLICATE_ONLY_NOOP,
    ACTION_VALIDATE_STORE_OUTLIER,
    ACTION_MONITOR_COLD_START_SEGMENT,
    ACTION_MONITOR_TRUE_ZERO_SEGMENT,
    ACTION_NO_ACTION_REQUIRED,
]


@dataclass(frozen=True)
class CommercialActionInstructionSummary:
    action_instruction_readiness_class: str
    action_instruction_readiness_reason: str
    top_operator_action_class: str
    top_operator_action_reason: str
    top_model_owner_action_class: str
    top_model_owner_action_reason: str
    operator_attention_class: str
    operator_attention_reason: str
    action_pack_materiality_class: str
    action_pack_materiality_reason: str
    total_action_count: int
    operator_action_count: int
    model_owner_action_count: int
    immediate_action_count: int
    high_priority_action_count: int
    low_evidence_action_count: int
    safe_manual_review_action_count: int
    blocked_action_count: int
    affected_store_count: int
    affected_promotion_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialActionInstructionArtifacts:
    instruction_rows: pd.DataFrame
    operator_action_summary: pd.DataFrame
    model_owner_action_summary: pd.DataFrame
    priority_queue: pd.DataFrame
    by_segment: pd.DataFrame
    summary: CommercialActionInstructionSummary
    brief_markdown: str


def build_commercial_action_instruction_artifacts(
    *,
    run_id: str,
    current_store_prediction_csv_path: str,
    commercial_change_explanations: pd.DataFrame,
    commercial_outcome_attribution: pd.DataFrame,
    commercial_delta_top_changes: pd.DataFrame,
    commercial_delta_store_summary: pd.DataFrame,
    commercial_delta_summary: dict[str, object],
    commercial_policy_calibration_summary: dict[str, object],
    commercial_policy_calibration_by_segment: pd.DataFrame,
    commercial_policy_watchlist: pd.DataFrame,
    commercial_policy_simulation_summary: dict[str, object],
    commercial_policy_simulation_by_segment: pd.DataFrame,
    commercial_policy_simulation_watchlist: pd.DataFrame,
    commercial_outcome_class: str,
    current_freshness_class: str,
    current_commercial_failure_flag: bool,
) -> CommercialActionInstructionArtifacts:
    current_frame = _normalize_current_frame(pd.read_csv(current_store_prediction_csv_path, encoding="utf-8"))
    explanations = _normalize_explanations_frame(commercial_change_explanations)
    attribution = _normalize_attribution_frame(commercial_outcome_attribution)
    delta_top_changes = _normalize_delta_top_changes(commercial_delta_top_changes)
    delta_store_summary = _normalize_delta_store_summary(commercial_delta_store_summary)

    merged = explanations.merge(
        attribution,
        on=["store_number", "sku_number", "promotion_start_date", "promotion_end_date"],
        how="left",
        suffixes=("", "_attr"),
    ).merge(
        current_frame,
        on=["store_number", "sku_number", "promotion_start_date", "promotion_end_date"],
        how="left",
        suffixes=("", "_current"),
    ).merge(
        delta_top_changes,
        on=["store_number", "sku_number", "promotion_start_date", "promotion_end_date"],
        how="left",
        suffixes=("", "_delta"),
    )

    calibration_by_segment_lookup = _build_segment_lookup(commercial_policy_calibration_by_segment)
    calibration_watch_lookup = _build_segment_lookup(commercial_policy_watchlist)
    simulation_by_segment_lookup = _build_segment_lookup(commercial_policy_simulation_by_segment)
    simulation_watch_lookup = _build_segment_lookup(commercial_policy_simulation_watchlist)

    row_records: list[dict[str, object]] = []
    for _, row in merged.iterrows():
        row_records.append(
            _classify_action_row(
                row=row,
                run_id=run_id,
                current_freshness_class=current_freshness_class,
                current_commercial_failure_flag=bool(current_commercial_failure_flag),
                commercial_outcome_class=commercial_outcome_class,
                commercial_delta_summary=commercial_delta_summary,
                commercial_policy_calibration_summary=commercial_policy_calibration_summary,
                commercial_policy_simulation_summary=commercial_policy_simulation_summary,
                calibration_by_segment_lookup=calibration_by_segment_lookup,
                calibration_watch_lookup=calibration_watch_lookup,
                simulation_by_segment_lookup=simulation_by_segment_lookup,
                simulation_watch_lookup=simulation_watch_lookup,
                delta_store_summary=delta_store_summary,
            )
        )

    instruction_rows = pd.DataFrame(row_records)
    if instruction_rows.empty:
        instruction_rows = pd.DataFrame(columns=_instruction_columns())

    instruction_rows = _rank_action_rows(instruction_rows)
    priority_queue = instruction_rows.copy()

    operator_action_summary = _build_owner_summary(priority_queue, OWNER_OPERATOR)
    model_owner_action_summary = _build_owner_summary(priority_queue, OWNER_MODEL_OWNER)
    by_segment = _build_segment_summary(priority_queue)

    summary = _build_summary(
        instruction_frame=priority_queue,
        commercial_delta_summary=commercial_delta_summary,
        commercial_policy_calibration_summary=commercial_policy_calibration_summary,
        commercial_policy_simulation_summary=commercial_policy_simulation_summary,
        current_freshness_class=current_freshness_class,
        current_commercial_failure_flag=bool(current_commercial_failure_flag),
    )

    _validate_instruction_consistency(
        instruction_frame=priority_queue,
        operator_action_summary=operator_action_summary,
        model_owner_action_summary=model_owner_action_summary,
        by_segment=by_segment,
        summary=summary,
    )

    brief_markdown = build_commercial_action_instruction_brief(
        summary=summary,
        priority_queue=priority_queue,
        by_segment=by_segment,
    )

    return CommercialActionInstructionArtifacts(
        instruction_rows=priority_queue,
        operator_action_summary=operator_action_summary,
        model_owner_action_summary=model_owner_action_summary,
        priority_queue=priority_queue,
        by_segment=by_segment,
        summary=summary,
        brief_markdown=brief_markdown,
    )


def build_commercial_action_instruction_brief(
    *,
    summary: CommercialActionInstructionSummary,
    priority_queue: pd.DataFrame,
    by_segment: pd.DataFrame,
) -> str:
    immediate_preview = _preview_lines(priority_queue, attention=ATTENTION_IMMEDIATE)
    operator_preview = _preview_lines(priority_queue, owner=OWNER_OPERATOR)
    model_owner_preview = _preview_lines(priority_queue, owner=OWNER_MODEL_OWNER)
    segment_preview = _segment_preview_lines(by_segment)

    return f"""# Commercial Action Instruction Brief

## Action Pack Readiness

- **Readiness Class**: {summary.action_instruction_readiness_class}
- **Readiness Reason**: {summary.action_instruction_readiness_reason}
- **Operator Attention**: {summary.operator_attention_class}
- **Operator Attention Reason**: {summary.operator_attention_reason}
- **Materiality Class**: {summary.action_pack_materiality_class}
- **Materiality Reason**: {summary.action_pack_materiality_reason}

## Top Operator Actions

{chr(10).join([f"- {line}" for line in operator_preview])}

## Top Model Owner Actions

{chr(10).join([f"- {line}" for line in model_owner_preview])}

## Immediate Priorities

{chr(10).join([f"- {line}" for line in immediate_preview])}

## Segment Watchlist

{chr(10).join([f"- {line}" for line in segment_preview])}

## Recommended Next Steps

{chr(10).join([f"- {line}" for line in _next_step_lines(summary)])}
"""


def _classify_action_row(
    *,
    row: pd.Series,
    run_id: str,
    current_freshness_class: str,
    current_commercial_failure_flag: bool,
    commercial_outcome_class: str,
    commercial_delta_summary: dict[str, object],
    commercial_policy_calibration_summary: dict[str, object],
    commercial_policy_simulation_summary: dict[str, object],
    calibration_by_segment_lookup: dict[tuple[str, str], dict[str, object]],
    calibration_watch_lookup: dict[tuple[str, str], dict[str, object]],
    simulation_by_segment_lookup: dict[tuple[str, str], dict[str, object]],
    simulation_watch_lookup: dict[tuple[str, str], dict[str, object]],
    delta_store_summary: pd.DataFrame,
) -> dict[str, object]:
    row_dict = row.to_dict()

    store_number = _string_or_none(row_dict.get("store_number"))
    promotion_id = _promotion_identifier(row_dict)
    demand_class = _string_or_none(row_dict.get("current_demand_evidence_class")) or _string_or_none(
        row_dict.get("demand_evidence_class")
    )
    effectiveness = _string_or_none(row_dict.get("recommendation_effectiveness_class"))
    confidence = _string_or_none(row_dict.get("attribution_confidence_class"))
    attribution_status = _string_or_none(row_dict.get("attribution_status"))
    row_change_class = _string_or_none(row_dict.get("row_change_class"))
    duplicate_blocked_flag = bool(row_dict.get("duplicate_blocked_flag", False))
    changed_flag = bool(row_dict.get("changed_flag", False))

    calibration_match = _match_segment_lookup(row_dict, calibration_watch_lookup) or _match_segment_lookup(
        row_dict, calibration_by_segment_lookup
    )
    simulation_match = _match_segment_lookup(row_dict, simulation_watch_lookup) or _match_segment_lookup(
        row_dict, simulation_by_segment_lookup
    )

    calibration_readiness = str(commercial_policy_calibration_summary.get("calibration_readiness_class") or "")
    simulation_readiness = str(commercial_policy_simulation_summary.get("simulation_readiness_class") or "")
    threshold_direction = str(commercial_policy_calibration_summary.get("threshold_direction_class") or "")

    blocked_defect = bool(
        current_commercial_failure_flag
        or ("FAILURE" in str(commercial_outcome_class))
        or ("DEFECT" in str(commercial_outcome_class))
        or row_change_class == "DEFECT_BLOCKED_ROW"
        or attribution_status in {
            ATTRIBUTION_BLOCKED_INCONSISTENT_KEYS,
            ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA,
        }
        or simulation_readiness == SIMULATION_BLOCKED_DEFECT
    )

    action_class = ACTION_NO_ACTION_REQUIRED
    action_owner_class = OWNER_OPERATOR
    action_reason = "No immediate operator or model-owner action is required."
    evidence_strength_class = EVIDENCE_NONE
    requires_human_review_flag = False
    safe_to_execute_as_manual_review_flag = False
    operator_attention_class = ATTENTION_LOW
    blocked_action_flag = False
    linked_segment_type: Optional[str] = "operator_action_class"
    linked_segment_value: Optional[str] = _string_or_none(row_dict.get("operator_action_class"))

    if blocked_defect:
        action_class = ACTION_MODEL_OWNER_DATA_QUALITY_REVIEW
        action_owner_class = OWNER_MODEL_OWNER
        action_reason = "Cycle or row is blocked by defect/inconsistent attribution keys and requires model-owner data quality review."
        evidence_strength_class = EVIDENCE_NONE
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = False
        operator_attention_class = ATTENTION_IMMEDIATE
        blocked_action_flag = True
        linked_segment_type = "attribution_status"
        linked_segment_value = attribution_status or row_change_class
    elif effectiveness in {HARMFUL, INEFFECTIVE} and confidence in {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM}:
        action_class = ACTION_INVESTIGATE_HARMFUL_RECOMMENDATIONS
        action_reason = "High-confidence harmful/ineffective recommendation evidence requires immediate operator investigation."
        evidence_strength_class = EVIDENCE_HIGH if confidence == CONFIDENCE_HIGH else EVIDENCE_MEDIUM
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_IMMEDIATE
        linked_segment_type = "recommendation_effectiveness_class"
        linked_segment_value = effectiveness
    elif demand_class == "artificial_collapse":
        action_class = ACTION_INVESTIGATE_ARTIFICIAL_COLLAPSE
        action_reason = "Artificial-collapse demand evidence requires immediate investigation before trusting recommendation behavior."
        evidence_strength_class = EVIDENCE_HIGH
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_IMMEDIATE
        linked_segment_type = "demand_evidence_class"
        linked_segment_value = demand_class
    elif simulation_match is not None and str(simulation_match.get("simulated_risk_class")) in {
        "SIMULATION_HIGH_RISK",
        "SIMULATION_MODERATE_RISK",
    }:
        action_class = ACTION_REVIEW_HIGH_RISK_SEGMENT
        action_reason = "Simulation watch diagnostics identify a high-risk segment that requires immediate governed review."
        evidence_strength_class = EVIDENCE_HIGH if str(simulation_match.get("simulated_risk_class")) == "SIMULATION_HIGH_RISK" else EVIDENCE_MEDIUM
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_IMMEDIATE
        linked_segment_type = _string_or_none(simulation_match.get("segment_type")) or "simulated_risk_class"
        linked_segment_value = _string_or_none(simulation_match.get("segment_value")) or _string_or_none(
            simulation_match.get("simulated_risk_class")
        )
    elif simulation_match is not None and str(simulation_match.get("simulated_materiality_class")) == "SIMULATION_HIGH_MATERIALITY":
        action_class = ACTION_REVIEW_HIGH_IMPACT_SIMULATION
        action_reason = "Simulation indicates high-impact policy movement and requires immediate operator review."
        evidence_strength_class = EVIDENCE_HIGH
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_IMMEDIATE
        linked_segment_type = _string_or_none(simulation_match.get("segment_type")) or "simulated_materiality_class"
        linked_segment_value = _string_or_none(simulation_match.get("segment_value")) or "SIMULATION_HIGH_MATERIALITY"
    elif threshold_direction == TIGHTEN_PUBLISH_POLICY:
        action_class = ACTION_TIGHTEN_POLICY_REVIEW
        action_owner_class = OWNER_MODEL_OWNER
        action_reason = "Calibration threshold direction recommends tighten posture review by model owner."
        evidence_strength_class = _evidence_from_row_count(commercial_policy_calibration_summary.get("evidence_row_count"))
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_IMMEDIATE
        linked_segment_type = _string_or_none((calibration_match or {}).get("segment_type")) or "threshold_direction_class"
        linked_segment_value = _string_or_none((calibration_match or {}).get("segment_value")) or threshold_direction
    elif threshold_direction == LOOSEN_PUBLISH_POLICY:
        action_class = ACTION_LOOSEN_POLICY_REVIEW
        action_owner_class = OWNER_MODEL_OWNER
        action_reason = "Calibration threshold direction recommends loosen posture review by model owner."
        evidence_strength_class = _evidence_from_row_count(commercial_policy_calibration_summary.get("evidence_row_count"))
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_IMMEDIATE
        linked_segment_type = _string_or_none((calibration_match or {}).get("segment_type")) or "threshold_direction_class"
        linked_segment_value = _string_or_none((calibration_match or {}).get("segment_value")) or threshold_direction
    elif threshold_direction == HOLD_POLICY:
        action_class = ACTION_HOLD_POLICY_MONITOR
        action_owner_class = OWNER_MODEL_OWNER
        action_reason = "Calibration recommends hold posture; monitor policy behavior under governed review."
        evidence_strength_class = _evidence_from_row_count(commercial_policy_calibration_summary.get("evidence_row_count"))
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_HIGH
        linked_segment_type = _string_or_none((calibration_match or {}).get("segment_type")) or "threshold_direction_class"
        linked_segment_value = _string_or_none((calibration_match or {}).get("segment_value")) or threshold_direction
    elif effectiveness in {HARMFUL, INEFFECTIVE} and confidence in {CONFIDENCE_LOW, CONFIDENCE_NONE}:
        action_class = ACTION_MODEL_OWNER_FEATURE_REVIEW
        action_owner_class = OWNER_MODEL_OWNER
        action_reason = "Low-confidence harmful signal requires model-owner feature and attribution-quality review before policy changes."
        evidence_strength_class = EVIDENCE_LOW
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_HIGH
        linked_segment_type = "recommendation_effectiveness_class"
        linked_segment_value = effectiveness
    elif current_freshness_class == "NO_NEW_PUBLICATIONS_DUPLICATE_ONLY" or duplicate_blocked_flag:
        action_class = ACTION_REVIEW_DUPLICATE_ONLY_NOOP
        action_reason = "Duplicate-only NOOP cycle should be reviewed under freshness/replay governance with no automated mutation."
        evidence_strength_class = _evidence_strength(confidence=confidence, attribution_status=attribution_status)
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_HIGH
        linked_segment_type = "freshness_class"
        linked_segment_value = current_freshness_class
    elif demand_class == "true_zero_demand":
        action_class = ACTION_MONITOR_TRUE_ZERO_SEGMENT
        action_reason = "True-zero demand segment should be monitored and not converted into decisive policy mutation."
        evidence_strength_class = EVIDENCE_MEDIUM
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_NORMAL
        linked_segment_type = "demand_evidence_class"
        linked_segment_value = demand_class
    elif demand_class == "cold_start_new_line":
        action_class = ACTION_MONITOR_COLD_START_SEGMENT
        action_reason = "Cold-start segment should be monitored until sufficient governed evidence accumulates."
        evidence_strength_class = EVIDENCE_MEDIUM
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_NORMAL
        linked_segment_type = "demand_evidence_class"
        linked_segment_value = demand_class
    elif _is_store_outlier(store_number, delta_store_summary):
        action_class = ACTION_VALIDATE_STORE_OUTLIER
        action_reason = "Store-level delta indicates an outlier that should be validated by operator review."
        evidence_strength_class = EVIDENCE_MEDIUM if changed_flag else EVIDENCE_LOW
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_NORMAL
        linked_segment_type = "store_number"
        linked_segment_value = store_number
    elif (
        attribution_status in {ATTRIBUTION_NOT_YET_MATURE, ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA}
        or calibration_readiness in {CALIBRATION_LOW_COVERAGE, CALIBRATION_NOT_READY}
        or simulation_readiness in {SIMULATION_LOW_COVERAGE, SIMULATION_NOT_COMPARABLE}
    ):
        action_class = ACTION_REVIEW_LOW_COVERAGE_SEGMENT
        action_reason = "Low-evidence diagnostics require review/monitor posture, not decisive policy action."
        evidence_strength_class = EVIDENCE_LOW
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_HIGH
        linked_segment_type = "attribution_status"
        linked_segment_value = attribution_status or calibration_readiness or simulation_readiness
    elif str(commercial_delta_summary.get("materiality_class") or "") in {"HIGH_CHANGE", "MATERIAL_CHANGE"}:
        action_class = ACTION_MODEL_OWNER_THRESHOLD_REVIEW
        action_owner_class = OWNER_MODEL_OWNER
        action_reason = "Material commercial delta warrants model-owner threshold review under recommendation-only governance."
        evidence_strength_class = EVIDENCE_MEDIUM
        requires_human_review_flag = True
        safe_to_execute_as_manual_review_flag = True
        operator_attention_class = ATTENTION_HIGH
        linked_segment_type = "commercial_delta_class"
        linked_segment_value = _string_or_none(commercial_delta_summary.get("delta_class"))

    if linked_segment_type is None and action_class != ACTION_NO_ACTION_REQUIRED:
        linked_segment_type = "action_class"
    if linked_segment_value is None and action_class != ACTION_NO_ACTION_REQUIRED:
        linked_segment_value = action_class

    base_score = _ACTION_BASE_SCORES.get(action_class, 0)
    rank_tie_break = int(_coerce_int(row_dict.get("operator_priority_score"), default=0))
    action_priority_score = base_score * 1000 + rank_tie_break

    supporting_metric_summary = _build_supporting_metric_summary(
        row=row_dict,
        action_class=action_class,
        action_reason=action_reason,
        commercial_delta_summary=commercial_delta_summary,
        commercial_policy_calibration_summary=commercial_policy_calibration_summary,
        commercial_policy_simulation_summary=commercial_policy_simulation_summary,
    )

    return {
        "action_priority_rank": 0,
        "action_class": action_class,
        "action_owner_class": action_owner_class,
        "action_reason": action_reason,
        "evidence_strength_class": evidence_strength_class,
        "requires_human_review_flag": bool(requires_human_review_flag),
        "safe_to_execute_as_manual_review_flag": bool(safe_to_execute_as_manual_review_flag),
        "linked_segment_type": linked_segment_type,
        "linked_segment_value": linked_segment_value,
        "linked_store_number": store_number,
        "linked_promotion_id": promotion_id,
        "linked_run_id": run_id,
        "supporting_metric_summary": supporting_metric_summary,
        "operator_attention_class": operator_attention_class,
        "action_priority_score": action_priority_score,
        "blocked_action_flag": bool(blocked_action_flag),
        "attribution_status": attribution_status,
        "store_number": store_number,
        "sku_number": _string_or_none(row_dict.get("sku_number")),
        "promotion_start_date": _string_or_none(row_dict.get("promotion_start_date")),
        "promotion_end_date": _string_or_none(row_dict.get("promotion_end_date")),
        "row_change_class": row_change_class,
        "row_change_reason_code": _string_or_none(row_dict.get("row_change_reason_code")),
        "operator_action_class_source": _string_or_none(row_dict.get("operator_action_class")),
        "operator_priority_score": _coerce_int(row_dict.get("operator_priority_score"), default=0),
        "operator_priority_band": _string_or_none(row_dict.get("operator_priority_band")),
        "recommendation_effectiveness_class": effectiveness,
        "attribution_confidence_class": confidence,
        "current_demand_evidence_class": demand_class,
        "current_publish_eligibility_class": _string_or_none(row_dict.get("current_publish_eligibility_class")),
        "changed_flag": bool(changed_flag),
    }


def _build_summary(
    *,
    instruction_frame: pd.DataFrame,
    commercial_delta_summary: dict[str, object],
    commercial_policy_calibration_summary: dict[str, object],
    commercial_policy_simulation_summary: dict[str, object],
    current_freshness_class: str,
    current_commercial_failure_flag: bool,
) -> CommercialActionInstructionSummary:
    total_action_count = int(len(instruction_frame.index))
    operator_rows = instruction_frame[instruction_frame["action_owner_class"] == OWNER_OPERATOR]
    model_owner_rows = instruction_frame[instruction_frame["action_owner_class"] == OWNER_MODEL_OWNER]

    immediate_action_count = int((instruction_frame["operator_attention_class"] == ATTENTION_IMMEDIATE).sum())
    high_priority_action_count = int((instruction_frame["operator_attention_class"] == ATTENTION_HIGH).sum())
    low_evidence_action_count = int(instruction_frame["evidence_strength_class"].isin([EVIDENCE_LOW, EVIDENCE_NONE]).sum())
    safe_manual_review_action_count = int(instruction_frame["safe_to_execute_as_manual_review_flag"].sum())
    blocked_action_count = int(instruction_frame["blocked_action_flag"].sum())

    actionable = instruction_frame[instruction_frame["action_class"] != ACTION_NO_ACTION_REQUIRED]
    affected_store_count = int(actionable["linked_store_number"].dropna().astype(str).nunique())
    affected_promotion_count = int(actionable["linked_promotion_id"].dropna().astype(str).nunique())

    readiness_class = _readiness_class(
        instruction_frame=instruction_frame,
        current_freshness_class=current_freshness_class,
        current_commercial_failure_flag=current_commercial_failure_flag,
        commercial_policy_calibration_summary=commercial_policy_calibration_summary,
        commercial_policy_simulation_summary=commercial_policy_simulation_summary,
    )
    readiness_reason = _readiness_reason(readiness_class)

    top_operator = _top_owner_action(operator_rows)
    top_model_owner = _top_owner_action(model_owner_rows)
    queue_top = instruction_frame.iloc[0] if not instruction_frame.empty else None

    operator_attention_class = str(queue_top["operator_attention_class"]) if queue_top is not None else ATTENTION_LOW
    operator_attention_reason = str(queue_top["action_reason"]) if queue_top is not None else "No action pack rows are present."

    materiality_class, materiality_reason = _materiality(
        instruction_frame=instruction_frame,
        commercial_delta_summary=commercial_delta_summary,
        commercial_policy_simulation_summary=commercial_policy_simulation_summary,
        immediate_action_count=immediate_action_count,
        high_priority_action_count=high_priority_action_count,
    )

    return CommercialActionInstructionSummary(
        action_instruction_readiness_class=readiness_class,
        action_instruction_readiness_reason=readiness_reason,
        top_operator_action_class=(
            str(queue_top["action_class"]) if queue_top is not None else ACTION_NO_ACTION_REQUIRED
        ),
        top_operator_action_reason=(
            str(queue_top["action_reason"]) if queue_top is not None else "No operator action rows were produced."
        ),
        top_model_owner_action_class=(
            str(top_model_owner["action_class"]) if top_model_owner is not None else (str(queue_top["action_class"]) if queue_top is not None else ACTION_NO_ACTION_REQUIRED)
        ),
        top_model_owner_action_reason=(
            str(top_model_owner["action_reason"]) if top_model_owner is not None else (str(queue_top["action_reason"]) if queue_top is not None else "No model-owner action rows were produced.")
        ),
        operator_attention_class=operator_attention_class,
        operator_attention_reason=operator_attention_reason,
        action_pack_materiality_class=materiality_class,
        action_pack_materiality_reason=materiality_reason,
        total_action_count=total_action_count,
        operator_action_count=int(len(operator_rows.index)),
        model_owner_action_count=int(len(model_owner_rows.index)),
        immediate_action_count=immediate_action_count,
        high_priority_action_count=high_priority_action_count,
        low_evidence_action_count=low_evidence_action_count,
        safe_manual_review_action_count=safe_manual_review_action_count,
        blocked_action_count=blocked_action_count,
        affected_store_count=affected_store_count,
        affected_promotion_count=affected_promotion_count,
    )


def _validate_instruction_consistency(
    *,
    instruction_frame: pd.DataFrame,
    operator_action_summary: pd.DataFrame,
    model_owner_action_summary: pd.DataFrame,
    by_segment: pd.DataFrame,
    summary: CommercialActionInstructionSummary,
) -> None:
    errors: list[str] = []

    if summary.total_action_count != int(len(instruction_frame.index)):
        errors.append("action counts do not reconcile")
    if summary.operator_action_count + summary.model_owner_action_count != summary.total_action_count:
        errors.append("action counts do not reconcile")

    if not instruction_frame.empty:
        ranks = instruction_frame["action_priority_rank"].astype(int).tolist()
        expected = list(range(1, len(ranks) + 1))
        if ranks != expected:
            errors.append("action priority ranks are duplicated or non-contiguous")

        if (
            instruction_frame["blocked_action_flag"]
            & instruction_frame["safe_to_execute_as_manual_review_flag"]
        ).any():
            errors.append("blocked actions are marked safe_to_execute_as_manual_review_flag=true")

        actionable = instruction_frame[instruction_frame["action_class"] != ACTION_NO_ACTION_REQUIRED]
        if not actionable.empty:
            missing_links = actionable[
                actionable[[
                    "linked_segment_type",
                    "linked_segment_value",
                    "linked_store_number",
                    "linked_promotion_id",
                    "linked_run_id",
                ]]
                .isna()
                .any(axis=1)
            ]
            if not missing_links.empty:
                errors.append("segment/store/promotion-linked actions reference missing segment values")

        evidence_ready_rows = int((instruction_frame["attribution_status"] == ATTRIBUTION_READY).sum())
        if summary.action_instruction_readiness_class == ACTION_PACK_READY and evidence_ready_rows == 0:
            errors.append("readiness says READY while evidence rows are zero")

        queue_action_classes = set(instruction_frame["action_class"].astype(str).tolist())
        if summary.top_operator_action_class not in queue_action_classes:
            errors.append("operator/model-owner top actions are absent from the queue")
        if summary.top_model_owner_action_class not in queue_action_classes:
            errors.append("operator/model-owner top actions are absent from the queue")

        actionable_high_or_immediate = instruction_frame[
            (instruction_frame["operator_attention_class"].isin([ATTENTION_IMMEDIATE, ATTENTION_HIGH]))
            & (instruction_frame["action_class"] != ACTION_NO_ACTION_REQUIRED)
        ]
        if summary.top_operator_action_class == ACTION_NO_ACTION_REQUIRED and not actionable_high_or_immediate.empty:
            errors.append("NO_ACTION_REQUIRED coexists with immediate/high-priority actions as the top action")

    if summary.total_action_count > 0 and by_segment.empty:
        errors.append("segment summary is unexpectedly empty")
    if summary.operator_action_count > 0 and operator_action_summary.empty:
        errors.append("operator action summary is unexpectedly empty")
    if (
        summary.model_owner_action_count > 0
        and model_owner_action_summary.empty
    ):
        errors.append("model-owner action summary is unexpectedly empty")

    if errors:
        raise ValueError("Commercial action instruction consistency check failed:\n" + "\n".join(errors))


def _rank_action_rows(frame: pd.DataFrame) -> pd.DataFrame:
    ranked = frame.copy()
    if ranked.empty:
        ranked = pd.DataFrame(columns=_instruction_columns())
        return ranked

    ranked["_action_order"] = ranked["action_class"].map({v: i for i, v in enumerate(_ACTION_ORDER)}).fillna(len(_ACTION_ORDER))
    ranked = ranked.sort_values(
        by=["_action_order", "action_priority_score", "linked_store_number", "linked_promotion_id"],
        ascending=[True, False, True, True],
    ).reset_index(drop=True)
    ranked["action_priority_rank"] = range(1, len(ranked.index) + 1)
    ranked = ranked.drop(columns=["_action_order"])
    return ranked[_instruction_columns()]


def _build_owner_summary(frame: pd.DataFrame, owner_class: str) -> pd.DataFrame:
    subset = frame[frame["action_owner_class"] == owner_class]
    if subset.empty:
        return pd.DataFrame(columns=_summary_group_columns())
    grouped = (
        subset.groupby(["action_class", "action_owner_class"], dropna=False)
        .agg(
            action_count=("action_class", "count"),
            highest_priority_rank=("action_priority_rank", "min"),
            immediate_action_count=("operator_attention_class", lambda s: int((s == ATTENTION_IMMEDIATE).sum())),
            high_priority_action_count=("operator_attention_class", lambda s: int((s == ATTENTION_HIGH).sum())),
            low_evidence_action_count=("evidence_strength_class", lambda s: int(s.isin([EVIDENCE_LOW, EVIDENCE_NONE]).sum())),
            safe_manual_review_action_count=("safe_to_execute_as_manual_review_flag", "sum"),
            blocked_action_count=("blocked_action_flag", "sum"),
        )
        .reset_index()
        .sort_values(by=["highest_priority_rank", "action_count"], ascending=[True, False])
    )
    return grouped


def _build_segment_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=_segment_summary_columns())

    rows: list[dict[str, object]] = []
    for (segment_type, segment_value), subset in frame.groupby(["linked_segment_type", "linked_segment_value"], dropna=False):
        top = subset.sort_values(by=["action_priority_rank", "action_priority_score"], ascending=[True, False]).iloc[0]
        rows.append(
            {
                "segment_type": _string_or_none(segment_type) or "UNKNOWN",
                "segment_value": _string_or_none(segment_value) or "UNKNOWN",
                "action_count": int(len(subset.index)),
                "top_action_class": str(top["action_class"]),
                "top_action_reason": str(top["action_reason"]),
                "highest_priority_rank": int(top["action_priority_rank"]),
                "evidence_strength_class": str(top["evidence_strength_class"]),
                "operator_attention_class": str(top["operator_attention_class"]),
            }
        )

    return pd.DataFrame(rows, columns=_segment_summary_columns()).sort_values(
        by=["highest_priority_rank", "action_count"],
        ascending=[True, False],
    )


def _build_segment_lookup(frame: pd.DataFrame) -> dict[tuple[str, str], dict[str, object]]:
    if frame.empty:
        return {}
    lookup: dict[tuple[str, str], dict[str, object]] = {}
    for _, row in frame.iterrows():
        segment_type = _string_or_none(row.get("segment_type"))
        segment_value = _string_or_none(row.get("segment_value"))
        if segment_type is None or segment_value is None:
            continue
        lookup[(segment_type, segment_value)] = row.to_dict()
    return lookup


def _match_segment_lookup(
    row: dict[str, object],
    lookup: dict[tuple[str, str], dict[str, object]],
) -> Optional[dict[str, object]]:
    if not lookup:
        return None
    for (segment_type, segment_value), segment_row in lookup.items():
        if segment_type in row and _string_or_none(row.get(segment_type)) == segment_value:
            return segment_row
    return None


def _readiness_class(
    *,
    instruction_frame: pd.DataFrame,
    current_freshness_class: str,
    current_commercial_failure_flag: bool,
    commercial_policy_calibration_summary: dict[str, object],
    commercial_policy_simulation_summary: dict[str, object],
) -> str:
    if instruction_frame.empty:
        return ACTION_PACK_NOT_COMPARABLE

    if bool(current_commercial_failure_flag) or current_freshness_class == "BLOCKED_BY_DEFECT":
        return ACTION_PACK_BLOCKED_DEFECT

    if bool(instruction_frame["blocked_action_flag"].any()):
        return ACTION_PACK_BLOCKED_DEFECT

    simulation_readiness = str(commercial_policy_simulation_summary.get("simulation_readiness_class") or "")
    if simulation_readiness == SIMULATION_NOT_COMPARABLE:
        return ACTION_PACK_NOT_COMPARABLE

    calibration_readiness = str(commercial_policy_calibration_summary.get("calibration_readiness_class") or "")
    ready_rows = int((instruction_frame["attribution_status"] == ATTRIBUTION_READY).sum())

    if ready_rows == 0:
        return ACTION_PACK_LOW_EVIDENCE

    if calibration_readiness in {CALIBRATION_NOT_READY, CALIBRATION_LOW_COVERAGE}:
        return ACTION_PACK_LOW_EVIDENCE

    if simulation_readiness in {SIMULATION_LOW_COVERAGE, SIMULATION_NOT_COMPARABLE}:
        return ACTION_PACK_LOW_EVIDENCE

    return ACTION_PACK_READY


def _readiness_reason(readiness_class: str) -> str:
    if readiness_class == ACTION_PACK_BLOCKED_DEFECT:
        return "Action pack is blocked by commercial failure/defect diagnostics and requires human defect review first."
    if readiness_class == ACTION_PACK_NOT_COMPARABLE:
        return "Action pack is not comparable because simulation or prior-cycle comparability evidence is unavailable."
    if readiness_class == ACTION_PACK_LOW_EVIDENCE:
        return "Action pack is low evidence; keep actions in monitor/review posture and avoid decisive policy recommendations."
    return "Action pack has sufficient governed evidence for ranked operator and model-owner review actions."


def _materiality(
    *,
    instruction_frame: pd.DataFrame,
    commercial_delta_summary: dict[str, object],
    commercial_policy_simulation_summary: dict[str, object],
    immediate_action_count: int,
    high_priority_action_count: int,
) -> tuple[str, str]:
    delta_materiality = str(commercial_delta_summary.get("materiality_class") or "")
    simulation_materiality = str(commercial_policy_simulation_summary.get("simulated_materiality_class") or "")

    if delta_materiality in {"HIGH_CHANGE", "MATERIAL_CHANGE"} or simulation_materiality == "SIMULATION_HIGH_MATERIALITY":
        return (
            "ACTION_PACK_HIGH_MATERIALITY",
            "Commercial delta/simulation indicates high material impact requiring immediate governed attention.",
        )
    if immediate_action_count > 0:
        return (
            "ACTION_PACK_HIGH_MATERIALITY",
            "At least one immediate-priority action exists in the queue.",
        )
    if high_priority_action_count > 0:
        return (
            "ACTION_PACK_MATERIAL",
            "High-priority actions exist and require active review.",
        )
    actionable = int((instruction_frame["action_class"] != ACTION_NO_ACTION_REQUIRED).sum())
    if actionable == 0:
        return (
            "ACTION_PACK_IMMATERIAL",
            "Only NO_ACTION_REQUIRED rows were produced.",
        )
    return (
        "ACTION_PACK_LOW_MATERIALITY",
        "Only low-intensity review/monitor actions were produced.",
    )


def _top_owner_action(frame: pd.DataFrame) -> Optional[pd.Series]:
    if frame.empty:
        return None
    actionable = frame[frame["action_class"] != ACTION_NO_ACTION_REQUIRED]
    source = actionable if not actionable.empty else frame
    return source.sort_values(
        by=["action_priority_rank", "action_priority_score", "linked_store_number", "linked_promotion_id"],
        ascending=[True, False, True, True],
    ).iloc[0]


def _preview_lines(
    frame: pd.DataFrame,
    *,
    owner: Optional[str] = None,
    attention: Optional[str] = None,
    limit: int = 5,
) -> list[str]:
    if frame.empty:
        return ["No action rows available."]

    subset = frame.copy()
    if owner is not None:
        subset = subset[subset["action_owner_class"] == owner]
    if attention is not None:
        subset = subset[subset["operator_attention_class"] == attention]
    if subset.empty:
        return ["No matching action rows available."]

    lines: list[str] = []
    for _, row in subset.head(limit).iterrows():
        lines.append(
            f"#{int(row['action_priority_rank'])} {row['action_class']} | owner={row['action_owner_class']} | store={row['linked_store_number']} | promotion={row['linked_promotion_id']} | reason={row['action_reason']}"
        )
    return lines


def _segment_preview_lines(by_segment: pd.DataFrame, limit: int = 5) -> list[str]:
    if by_segment.empty:
        return ["No segment watchlist rows available."]
    lines: list[str] = []
    for _, row in by_segment.head(limit).iterrows():
        lines.append(
            f"{row['segment_type']}={row['segment_value']} | top_action={row['top_action_class']} | count={int(row['action_count'])} | attention={row['operator_attention_class']}"
        )
    return lines


def _next_step_lines(summary: CommercialActionInstructionSummary) -> list[str]:
    if summary.action_instruction_readiness_class == ACTION_PACK_BLOCKED_DEFECT:
        return [
            "Investigate blocking defects/data quality issues before any policy review decision.",
            "Use the queue only for manual triage while defect posture remains active.",
        ]
    if summary.action_instruction_readiness_class == ACTION_PACK_LOW_EVIDENCE:
        return [
            "Keep actions in monitor/review posture until stronger attribution/calibration evidence is available.",
            "Do not apply decisive policy recommendations from low-evidence rows.",
        ]
    if (
        summary.top_operator_action_class == ACTION_NO_ACTION_REQUIRED
        and summary.top_model_owner_action_class == ACTION_NO_ACTION_REQUIRED
    ):
        return [
            "No immediate actions required; maintain governed posture and monitor next cycle.",
            "Re-run cycle with fresh evidence before considering policy review changes.",
        ]
    return [
        "Execute immediate operator reviews first, then route top model-owner reviews.",
        "Treat every action as recommendation-only and preserve mutation boundaries.",
    ]


def _build_supporting_metric_summary(
    *,
    row: dict[str, object],
    action_class: str,
    action_reason: str,
    commercial_delta_summary: dict[str, object],
    commercial_policy_calibration_summary: dict[str, object],
    commercial_policy_simulation_summary: dict[str, object],
) -> str:
    parts = [
        f"action={action_class}",
        f"row_change={_string_or_none(row.get('row_change_class'))}",
        f"effectiveness={_string_or_none(row.get('recommendation_effectiveness_class'))}",
        f"confidence={_string_or_none(row.get('attribution_confidence_class'))}",
        f"demand={_string_or_none(row.get('current_demand_evidence_class') or row.get('demand_evidence_class'))}",
        f"eligibility={_string_or_none(row.get('current_publish_eligibility_class') or row.get('publish_eligibility_class'))}",
        f"delta_class={_string_or_none(commercial_delta_summary.get('delta_class'))}",
        f"delta_materiality={_string_or_none(commercial_delta_summary.get('materiality_class'))}",
        f"policy_direction={_string_or_none(commercial_policy_calibration_summary.get('threshold_direction_class'))}",
        f"policy_signal={_string_or_none(commercial_policy_calibration_summary.get('policy_signal_class'))}",
        f"simulation_readiness={_string_or_none(commercial_policy_simulation_summary.get('simulation_readiness_class'))}",
        f"simulation_direction={_string_or_none(commercial_policy_simulation_summary.get('simulated_policy_direction_class'))}",
        f"simulation_materiality={_string_or_none(commercial_policy_simulation_summary.get('simulated_materiality_class'))}",
        f"simulation_risk={_string_or_none(commercial_policy_simulation_summary.get('simulated_risk_class'))}",
        f"reason={action_reason}",
    ]
    return " | ".join(parts)


def _is_store_outlier(store_number: Optional[str], delta_store_summary: pd.DataFrame) -> bool:
    if store_number is None or delta_store_summary.empty:
        return False
    matching = delta_store_summary[
        (delta_store_summary["store_number"].astype(str) == store_number)
        & (delta_store_summary["materially_changed_flag"] == True)
    ]
    return not matching.empty


def _evidence_strength(*, confidence: Optional[str], attribution_status: Optional[str]) -> str:
    if attribution_status in {
        ATTRIBUTION_NOT_YET_MATURE,
        ATTRIBUTION_BLOCKED_MISSING_OUTCOME_DATA,
        ATTRIBUTION_BLOCKED_INCONSISTENT_KEYS,
    }:
        return EVIDENCE_NONE
    if confidence == CONFIDENCE_HIGH:
        return EVIDENCE_HIGH
    if confidence == CONFIDENCE_MEDIUM:
        return EVIDENCE_MEDIUM
    if confidence == CONFIDENCE_LOW:
        return EVIDENCE_LOW
    return EVIDENCE_NONE


def _evidence_from_row_count(value: object) -> str:
    count = _coerce_int(value, default=0)
    if count >= 20:
        return EVIDENCE_HIGH
    if count >= 10:
        return EVIDENCE_MEDIUM
    if count > 0:
        return EVIDENCE_LOW
    return EVIDENCE_NONE


def _promotion_identifier(row: dict[str, object]) -> Optional[str]:
    promotion_id = _string_or_none(row.get("promotion_id"))
    if promotion_id is not None:
        return promotion_id
    promotion_row_key = _string_or_none(row.get("promotion_row_key"))
    if promotion_row_key is not None:
        return promotion_row_key
    promotion_header_key = _string_or_none(row.get("promotion_header_key"))
    if promotion_header_key is not None:
        return promotion_header_key

    store = _string_or_none(row.get("store_number"))
    sku = _string_or_none(row.get("sku_number"))
    start = _string_or_none(row.get("promotion_start_date"))
    end = _string_or_none(row.get("promotion_end_date"))
    if None in {store, sku, start, end}:
        return None
    return f"{store}|{sku}|{start}|{end}"


def _normalize_current_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in [
        "store_number",
        "sku_number",
        "promotion_start_date",
        "promotion_end_date",
        "promotion_row_key",
        "promotion_id",
        "promotion_header_key",
        "demand_evidence_class",
        "publish_eligibility_class",
    ]:
        if column not in normalized.columns:
            normalized[column] = None

    normalized["store_number"] = normalized["store_number"].astype("string")
    normalized["sku_number"] = normalized["sku_number"].astype("string")
    normalized["promotion_start_date"] = normalized["promotion_start_date"].astype("string")
    normalized["promotion_end_date"] = normalized["promotion_end_date"].astype("string")
    normalized["promotion_row_key"] = normalized["promotion_row_key"].astype("string")
    normalized["promotion_id"] = normalized["promotion_id"].astype("string")
    normalized["promotion_header_key"] = normalized["promotion_header_key"].astype("string")
    normalized["demand_evidence_class"] = normalized["demand_evidence_class"].astype("string")
    normalized["publish_eligibility_class"] = normalized["publish_eligibility_class"].astype("string")
    return normalized


def _normalize_explanations_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in [
        "store_number",
        "sku_number",
        "promotion_start_date",
        "promotion_end_date",
        "row_change_class",
        "row_change_reason_code",
        "operator_action_class",
        "operator_priority_score",
        "operator_priority_band",
        "review_required_flag",
        "duplicate_blocked_flag",
        "current_publish_eligibility_class",
        "current_demand_evidence_class",
    ]:
        if column not in normalized.columns:
            normalized[column] = None

    normalized["store_number"] = normalized["store_number"].astype("string")
    normalized["sku_number"] = normalized["sku_number"].astype("string")
    normalized["promotion_start_date"] = normalized["promotion_start_date"].astype("string")
    normalized["promotion_end_date"] = normalized["promotion_end_date"].astype("string")
    normalized["row_change_class"] = normalized["row_change_class"].astype("string")
    normalized["row_change_reason_code"] = normalized["row_change_reason_code"].astype("string")
    normalized["operator_action_class"] = normalized["operator_action_class"].astype("string")
    normalized["operator_priority_score"] = pd.to_numeric(normalized["operator_priority_score"], errors="coerce").fillna(0).astype(int)
    normalized["operator_priority_band"] = normalized["operator_priority_band"].astype("string")
    normalized["review_required_flag"] = normalized["review_required_flag"].fillna(False).astype(bool)
    normalized["duplicate_blocked_flag"] = normalized["duplicate_blocked_flag"].fillna(False).astype(bool)
    normalized["current_publish_eligibility_class"] = normalized["current_publish_eligibility_class"].astype("string")
    normalized["current_demand_evidence_class"] = normalized["current_demand_evidence_class"].astype("string")
    return normalized


def _normalize_attribution_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in [
        "store_number",
        "sku_number",
        "promotion_start_date",
        "promotion_end_date",
        "attribution_status",
        "recommendation_effectiveness_class",
        "attribution_confidence_class",
    ]:
        if column not in normalized.columns:
            normalized[column] = None

    normalized["store_number"] = normalized["store_number"].astype("string")
    normalized["sku_number"] = normalized["sku_number"].astype("string")
    normalized["promotion_start_date"] = normalized["promotion_start_date"].astype("string")
    normalized["promotion_end_date"] = normalized["promotion_end_date"].astype("string")
    normalized["attribution_status"] = normalized["attribution_status"].astype("string")
    normalized["recommendation_effectiveness_class"] = normalized["recommendation_effectiveness_class"].astype("string")
    normalized["attribution_confidence_class"] = normalized["attribution_confidence_class"].astype("string")
    return normalized


def _normalize_delta_top_changes(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in [
        "store_number",
        "sku_number",
        "promotion_start_date",
        "promotion_end_date",
        "changed_flag",
    ]:
        if column not in normalized.columns:
            normalized[column] = None

    normalized["store_number"] = normalized["store_number"].astype("string")
    normalized["sku_number"] = normalized["sku_number"].astype("string")
    normalized["promotion_start_date"] = normalized["promotion_start_date"].astype("string")
    normalized["promotion_end_date"] = normalized["promotion_end_date"].astype("string")
    normalized["changed_flag"] = normalized["changed_flag"].fillna(False).astype(bool)
    return normalized


def _normalize_delta_store_summary(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ["store_number", "materially_changed_flag"]:
        if column not in normalized.columns:
            normalized[column] = None

    normalized["store_number"] = normalized["store_number"].astype("string")
    normalized["materially_changed_flag"] = normalized["materially_changed_flag"].fillna(False).astype(bool)
    return normalized


def _coerce_int(value: object, *, default: int) -> int:
    try:
        if value is None:
            return default
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


def _string_or_none(value: object) -> Optional[str]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).strip()
    if text == "" or text.lower() in {"none", "nan", "nat", "<na>"}:
        return None
    return text


def _instruction_columns() -> list[str]:
    return [
        "action_priority_rank",
        "action_class",
        "action_owner_class",
        "action_reason",
        "evidence_strength_class",
        "requires_human_review_flag",
        "safe_to_execute_as_manual_review_flag",
        "linked_segment_type",
        "linked_segment_value",
        "linked_store_number",
        "linked_promotion_id",
        "linked_run_id",
        "supporting_metric_summary",
        "operator_attention_class",
        "action_priority_score",
        "blocked_action_flag",
        "attribution_status",
        "store_number",
        "sku_number",
        "promotion_start_date",
        "promotion_end_date",
        "row_change_class",
        "row_change_reason_code",
        "operator_action_class_source",
        "operator_priority_score",
        "operator_priority_band",
        "recommendation_effectiveness_class",
        "attribution_confidence_class",
        "current_demand_evidence_class",
        "current_publish_eligibility_class",
        "changed_flag",
    ]


def _summary_group_columns() -> list[str]:
    return [
        "action_class",
        "action_owner_class",
        "action_count",
        "highest_priority_rank",
        "immediate_action_count",
        "high_priority_action_count",
        "low_evidence_action_count",
        "safe_manual_review_action_count",
        "blocked_action_count",
    ]


def _segment_summary_columns() -> list[str]:
    return [
        "segment_type",
        "segment_value",
        "action_count",
        "top_action_class",
        "top_action_reason",
        "highest_priority_rank",
        "evidence_strength_class",
        "operator_attention_class",
    ]
