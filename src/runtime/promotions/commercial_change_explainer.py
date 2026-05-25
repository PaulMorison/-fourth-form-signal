from __future__ import annotations

"""Authoritative row-level commercial change explainability seam."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from runtime.promotions.commercial_delta import load_comparable_prior_cycle


# Row change classes
ROW_CHANGE_NEW_PUBLICATION = "NEW_PUBLICATION_ROW"
ROW_CHANGE_NO_LONGER_PUBLISHABLE = "NO_LONGER_PUBLISHABLE_ROW"
ROW_CHANGE_RECOMMENDATION_CHANGED = "RECOMMENDATION_CHANGED"
ROW_CHANGE_ELIGIBILITY_CHANGED = "ELIGIBILITY_CHANGED"
ROW_CHANGE_DEMAND_EVIDENCE_CHANGED = "DEMAND_EVIDENCE_CHANGED"
ROW_CHANGE_UNCHANGED = "UNCHANGED_ROW"
ROW_CHANGE_DEFECT_BLOCKED = "DEFECT_BLOCKED_ROW"

# Operator action classes
ACTION_PUBLISH_NOW = "ACTION_PUBLISH_NOW"
ACTION_REVIEW_NOW = "ACTION_REVIEW_NOW"
ACTION_MONITOR = "ACTION_MONITOR"
ACTION_NO_ACTION_DUPLICATE = "ACTION_NO_ACTION_DUPLICATE"
ACTION_NO_ACTION_TRUE_ZERO = "ACTION_NO_ACTION_TRUE_ZERO"
ACTION_INVESTIGATE_DEFECT = "ACTION_INVESTIGATE_DEFECT"

# Priority bands
PRIORITY_CRITICAL = "CRITICAL"
PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"
PRIORITY_NONE = "NONE"

# Transparent scoring constants
PRIORITY_SCORE_INVESTIGATE_DEFECT = 95
PRIORITY_SCORE_PUBLISH_NOW = 70
PRIORITY_SCORE_REVIEW_NOW = 65
PRIORITY_SCORE_MONITOR = 25
PRIORITY_SCORE_NO_ACTION_DUPLICATE = 5
PRIORITY_SCORE_NO_ACTION_TRUE_ZERO = 0

MATERIAL_UNITS_DELTA_THRESHOLD = 10
STRONG_UNITS_SWING_THRESHOLD = 25


@dataclass(frozen=True)
class RowChangeExplanation:
    """Typed row-level explanation for commercial change/actionability."""

    store_number: str
    sku_number: str
    promotion_start_date: str
    promotion_end_date: str
    prior_decision_recommendation: Optional[str]
    current_decision_recommendation: Optional[str]
    prior_publish_eligibility_class: Optional[str]
    current_publish_eligibility_class: Optional[str]
    prior_demand_evidence_class: Optional[str]
    current_demand_evidence_class: Optional[str]
    prior_recommended_order_units: Optional[float]
    current_recommended_order_units: Optional[float]
    recommended_order_units_delta: Optional[float]
    row_change_class: str
    row_change_reason_code: str
    row_change_reason: str
    operator_action_class: str
    operator_action_reason: str
    operator_priority_score: int
    operator_priority_band: str
    materially_changed_flag: bool
    changed_fields: str
    review_required_flag: bool
    excluded_from_publish_flag: bool
    duplicate_blocked_flag: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialActionSummary:
    """Run-level grouped action and priority counts."""

    action_publish_now_count: int
    action_review_now_count: int
    action_monitor_count: int
    action_no_action_duplicate_count: int
    action_no_action_true_zero_count: int
    action_investigate_defect_count: int
    critical_priority_count: int
    high_priority_count: int
    medium_priority_count: int
    low_priority_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialChangeExplainabilityArtifacts:
    """Explainability output tables and grouped summary."""

    explanations: pd.DataFrame
    priority_queue: pd.DataFrame
    action_summary: CommercialActionSummary


def build_commercial_change_explainability_artifacts(
    *,
    run_id: str,
    as_of_date: str,
    manifests_root: Path,
    current_store_prediction_csv_path: str,
    current_commercial_outcome_class: str,
    current_freshness_class: str,
    current_delta_class: str,
    duplicate_registry_skip_count: int,
    prior_cycle_run_id: Optional[str],
) -> CommercialChangeExplainabilityArtifacts:
    """Build authoritative row-level explanations, priority queue, and action summary."""
    current_frame = pd.read_csv(current_store_prediction_csv_path, encoding="utf-8")

    prior_frame: Optional[pd.DataFrame] = None
    if prior_cycle_run_id:
        prior_summary_path = manifests_root / prior_cycle_run_id / "commercial_run_outcome_summary.json"
        if prior_summary_path.exists():
            prior_payload = pd.read_json(prior_summary_path, typ="series")
            prior_download_manifest = prior_payload.get("store_prediction_download_manifest_path")
            if prior_download_manifest:
                manifest_payload = pd.read_json(Path(str(prior_download_manifest)), typ="series")
                prior_master_csv = manifest_payload.get("master_csv_path")
                if prior_master_csv and Path(str(prior_master_csv)).exists():
                    prior_frame = pd.read_csv(str(prior_master_csv), encoding="utf-8")

    if prior_frame is None:
        prior_cycle = load_comparable_prior_cycle(
            manifests_root=manifests_root,
            current_run_id=run_id,
            current_as_of_date=as_of_date,
        )
        if prior_cycle is not None:
            prior_frame = pd.read_csv(prior_cycle.store_prediction_master_csv_path, encoding="utf-8")

    duplicate_only_cycle = current_freshness_class == "NO_NEW_PUBLICATIONS_DUPLICATE_ONLY"
    defect_blocked_cycle = "FAILURE" in current_commercial_outcome_class or "DEFECT" in current_commercial_outcome_class

    explanations_frame = _build_explanations_frame(
        current_frame=current_frame,
        prior_frame=prior_frame,
        duplicate_only_cycle=duplicate_only_cycle,
        defect_blocked_cycle=defect_blocked_cycle,
        duplicate_registry_skip_count=int(duplicate_registry_skip_count),
        current_delta_class=current_delta_class,
    )

    action_summary = _build_action_summary(explanations_frame)
    priority_queue = _build_priority_queue(explanations_frame)

    _validate_explanation_consistency(
        explanations=explanations_frame,
        priority_queue=priority_queue,
        action_summary=action_summary,
    )

    return CommercialChangeExplainabilityArtifacts(
        explanations=explanations_frame,
        priority_queue=priority_queue,
        action_summary=action_summary,
    )


def _build_explanations_frame(
    *,
    current_frame: pd.DataFrame,
    prior_frame: Optional[pd.DataFrame],
    duplicate_only_cycle: bool,
    defect_blocked_cycle: bool,
    duplicate_registry_skip_count: int,
    current_delta_class: str,
) -> pd.DataFrame:
    current_norm = _normalize_frame(current_frame, prefix="current")
    if prior_frame is None:
        merged = current_norm.copy()
        for column in (
            "prior_decision_recommendation",
            "prior_publish_eligibility_class",
            "prior_demand_evidence_class",
            "prior_recommended_order_units",
            "prior_publishable_flag",
            "prior_review_required_flag",
            "prior_excluded_from_publish_flag",
            "prior_row_present",
        ):
            merged[column] = None
        merged["prior_row_present"] = False
    else:
        prior_norm = _normalize_frame(prior_frame, prefix="prior")
        merged = prior_norm.merge(
            current_norm,
            on=["store_number", "sku_number", "promotion_start_date", "promotion_end_date"],
            how="outer",
        )
        merged["prior_row_present"] = merged["prior_row_present"].fillna(False).astype(bool)
        merged["current_row_present"] = merged["current_row_present"].fillna(False).astype(bool)

    explanations: list[RowChangeExplanation] = []
    for _, row in merged.iterrows():
        explanation = _explain_row(
            row=row,
            duplicate_only_cycle=duplicate_only_cycle,
            defect_blocked_cycle=defect_blocked_cycle,
            duplicate_registry_skip_count=duplicate_registry_skip_count,
            current_delta_class=current_delta_class,
        )
        explanations.append(explanation)

    return pd.DataFrame([item.to_dict() for item in explanations], columns=_explanations_columns())


def _explain_row(
    *,
    row: pd.Series,
    duplicate_only_cycle: bool,
    defect_blocked_cycle: bool,
    duplicate_registry_skip_count: int,
    current_delta_class: str,
) -> RowChangeExplanation:
    prior_exists = bool(row.get("prior_row_present", False))
    current_exists = bool(row.get("current_row_present", True))

    prior_reco = _nullable_string(row.get("prior_decision_recommendation"))
    current_reco = _nullable_string(row.get("current_decision_recommendation"))
    prior_elig = _nullable_string(row.get("prior_publish_eligibility_class"))
    current_elig = _nullable_string(row.get("current_publish_eligibility_class"))
    prior_demand = _nullable_string(row.get("prior_demand_evidence_class"))
    current_demand = _nullable_string(row.get("current_demand_evidence_class"))

    prior_units = _nullable_float(row.get("prior_recommended_order_units"))
    current_units = _nullable_float(row.get("current_recommended_order_units"))
    units_delta = (current_units - prior_units) if prior_units is not None and current_units is not None else None

    prior_publishable = bool(row.get("prior_publishable_flag", False)) if prior_exists else False
    current_publishable = bool(row.get("current_publishable_flag", False)) if current_exists else False
    review_required = bool(row.get("current_review_required_flag", False)) if current_exists else False
    excluded_from_publish = bool(row.get("current_excluded_from_publish_flag", True)) if current_exists else True

    changed_fields: list[str] = []
    if prior_exists and current_exists:
        if prior_reco != current_reco:
            changed_fields.append("decision_recommendation")
        if prior_elig != current_elig:
            changed_fields.append("publish_eligibility_class")
        if prior_demand != current_demand:
            changed_fields.append("demand_evidence_class")
        if units_delta is not None and units_delta != 0:
            changed_fields.append("recommended_order_units")
        if prior_publishable != current_publishable:
            changed_fields.append("publishable_flag")
    elif (not prior_exists) and current_exists:
        changed_fields.append("new_row")
    elif prior_exists and (not current_exists):
        changed_fields.append("removed_row")

    if defect_blocked_cycle:
        row_change_class = ROW_CHANGE_DEFECT_BLOCKED
        reason_code = "defect_blocked_row_requires_investigation"
        reason = "Row belongs to a cycle blocked by defect; explanation limited to governed failure state."
    elif (not prior_exists) and current_exists and current_publishable:
        row_change_class = ROW_CHANGE_NEW_PUBLICATION
        reason_code = "recommendation_newly_appears"
        reason = "Row is newly publishable in current cycle and did not exist in prior comparable run."
    elif (not prior_exists) and current_exists:
        row_change_class = ROW_CHANGE_RECOMMENDATION_CHANGED
        reason_code = "first_observation_non_publishable_row"
        reason = "Row appears in current cycle without prior baseline but is not publishable under governed rules."
    elif prior_exists and (not current_exists):
        row_change_class = ROW_CHANGE_NO_LONGER_PUBLISHABLE
        reason_code = "recommendation_disappears_or_filtered_out"
        reason = "Row existed in prior comparable run but is absent in current cycle."
    elif prior_exists and current_exists and prior_demand != current_demand:
        row_change_class = ROW_CHANGE_DEMAND_EVIDENCE_CHANGED
        reason_code = f"demand_evidence_changed_{_slug(prior_demand)}_to_{_slug(current_demand)}"
        reason = "Demand evidence class changed between comparable runs."
    elif prior_exists and current_exists and prior_elig != current_elig:
        row_change_class = ROW_CHANGE_ELIGIBILITY_CHANGED
        reason_code = f"eligibility_changed_{_slug(prior_elig)}_to_{_slug(current_elig)}"
        reason = "Publish eligibility class changed between comparable runs."
    elif prior_exists and current_exists and (
        prior_reco != current_reco or (units_delta is not None and units_delta != 0)
    ):
        row_change_class = ROW_CHANGE_RECOMMENDATION_CHANGED
        if prior_reco != current_reco:
            reason_code = f"recommendation_changed_{_slug(prior_reco)}_to_{_slug(current_reco)}"
            reason = "Decision recommendation changed between comparable runs."
        elif units_delta is not None and abs(units_delta) >= MATERIAL_UNITS_DELTA_THRESHOLD:
            direction = "increase" if units_delta > 0 else "decrease"
            reason_code = f"recommended_order_units_{direction}_material"
            reason = "Recommended order units changed materially with recommendation unchanged."
        else:
            direction = "increase" if (units_delta or 0) > 0 else "decrease"
            reason_code = f"recommended_order_units_{direction}_minor"
            reason = "Recommended order units changed modestly with recommendation unchanged."
    else:
        row_change_class = ROW_CHANGE_UNCHANGED
        reason_code = "unchanged_against_prior_baseline"
        reason = "Row is unchanged versus prior comparable run across governed explanation fields."

    duplicate_blocked_flag = bool(duplicate_only_cycle and duplicate_registry_skip_count > 0 and current_publishable)
    action_class, action_reason = _classify_action(
        row_change_class=row_change_class,
        review_required=review_required,
        current_publishable=current_publishable,
        current_demand_evidence_class=current_demand,
        duplicate_blocked_flag=duplicate_blocked_flag,
        excluded_from_publish_flag=excluded_from_publish,
    )

    materially_changed_flag = row_change_class != ROW_CHANGE_UNCHANGED and (
        abs(units_delta or 0) >= MATERIAL_UNITS_DELTA_THRESHOLD
        or row_change_class in {
            ROW_CHANGE_NEW_PUBLICATION,
            ROW_CHANGE_NO_LONGER_PUBLISHABLE,
            ROW_CHANGE_ELIGIBILITY_CHANGED,
            ROW_CHANGE_DEFECT_BLOCKED,
        }
    )

    priority_score = _score_priority(
        action_class=action_class,
        row_change_class=row_change_class,
        units_delta=units_delta,
        materially_changed_flag=materially_changed_flag,
        duplicate_blocked_flag=duplicate_blocked_flag,
        current_demand_evidence_class=current_demand,
        current_delta_class=current_delta_class,
    )
    priority_band = _priority_band(priority_score)

    return RowChangeExplanation(
        store_number=str(row.get("store_number", "")),
        sku_number=str(row.get("sku_number", "")),
        promotion_start_date=str(row.get("promotion_start_date", "")),
        promotion_end_date=str(row.get("promotion_end_date", "")),
        prior_decision_recommendation=prior_reco,
        current_decision_recommendation=current_reco,
        prior_publish_eligibility_class=prior_elig,
        current_publish_eligibility_class=current_elig,
        prior_demand_evidence_class=prior_demand,
        current_demand_evidence_class=current_demand,
        prior_recommended_order_units=prior_units,
        current_recommended_order_units=current_units,
        recommended_order_units_delta=units_delta,
        row_change_class=row_change_class,
        row_change_reason_code=reason_code,
        row_change_reason=reason,
        operator_action_class=action_class,
        operator_action_reason=action_reason,
        operator_priority_score=priority_score,
        operator_priority_band=priority_band,
        materially_changed_flag=materially_changed_flag,
        changed_fields="|".join(changed_fields),
        review_required_flag=review_required,
        excluded_from_publish_flag=excluded_from_publish,
        duplicate_blocked_flag=duplicate_blocked_flag,
    )


def _classify_action(
    *,
    row_change_class: str,
    review_required: bool,
    current_publishable: bool,
    current_demand_evidence_class: Optional[str],
    duplicate_blocked_flag: bool,
    excluded_from_publish_flag: bool,
) -> tuple[str, str]:
    if row_change_class == ROW_CHANGE_DEFECT_BLOCKED:
        return (
            ACTION_INVESTIGATE_DEFECT,
            "Cycle is defect-blocked; this row requires defect investigation before commercial action.",
        )

    if duplicate_blocked_flag:
        return (
            ACTION_NO_ACTION_DUPLICATE,
            "Row is duplicate-blocked by governed registry state in this cycle.",
        )

    if current_demand_evidence_class == "true_zero_demand":
        return (
            ACTION_NO_ACTION_TRUE_ZERO,
            "Row is true-zero demand and should not trigger publish action.",
        )

    if review_required or excluded_from_publish_flag:
        return (
            ACTION_REVIEW_NOW,
            "Row is not currently publishable and requires review/policy decision.",
        )

    if current_publishable and row_change_class in {
        ROW_CHANGE_NEW_PUBLICATION,
        ROW_CHANGE_RECOMMENDATION_CHANGED,
        ROW_CHANGE_ELIGIBILITY_CHANGED,
        ROW_CHANGE_DEMAND_EVIDENCE_CHANGED,
    }:
        return (
            ACTION_PUBLISH_NOW,
            "Row is publishable and changed in a commercially relevant way.",
        )

    return (
        ACTION_MONITOR,
        "No immediate intervention required; monitor in normal commercial cadence.",
    )


def _score_priority(
    *,
    action_class: str,
    row_change_class: str,
    units_delta: Optional[float],
    materially_changed_flag: bool,
    duplicate_blocked_flag: bool,
    current_demand_evidence_class: Optional[str],
    current_delta_class: str,
) -> int:
    if action_class == ACTION_INVESTIGATE_DEFECT:
        return PRIORITY_SCORE_INVESTIGATE_DEFECT

    score = 0
    if action_class == ACTION_PUBLISH_NOW:
        score += PRIORITY_SCORE_PUBLISH_NOW
    elif action_class == ACTION_REVIEW_NOW:
        score += PRIORITY_SCORE_REVIEW_NOW
    elif action_class == ACTION_MONITOR:
        score += PRIORITY_SCORE_MONITOR
    elif action_class == ACTION_NO_ACTION_DUPLICATE:
        score += PRIORITY_SCORE_NO_ACTION_DUPLICATE
    elif action_class == ACTION_NO_ACTION_TRUE_ZERO:
        score += PRIORITY_SCORE_NO_ACTION_TRUE_ZERO

    if row_change_class == ROW_CHANGE_NEW_PUBLICATION:
        score += 20
    elif row_change_class == ROW_CHANGE_NO_LONGER_PUBLISHABLE:
        score += 25
    elif row_change_class == ROW_CHANGE_ELIGIBILITY_CHANGED:
        score += 15
    elif row_change_class == ROW_CHANGE_RECOMMENDATION_CHANGED:
        score += 12
    elif row_change_class == ROW_CHANGE_DEMAND_EVIDENCE_CHANGED:
        score += 8
    elif row_change_class == ROW_CHANGE_UNCHANGED:
        score -= 25

    if materially_changed_flag:
        score += 15

    if units_delta is not None:
        abs_delta = abs(units_delta)
        score += min(int(abs_delta // 2), 25)
        if abs_delta >= STRONG_UNITS_SWING_THRESHOLD:
            score += 8

    if duplicate_blocked_flag:
        score = min(score, 15)

    if current_demand_evidence_class == "true_zero_demand":
        score = min(score, 10)

    if current_delta_class in {"HIGH_COMMERCIAL_CHANGE", "MATERIAL_COMMERCIAL_CHANGE"}:
        score += 5

    return max(0, min(int(score), 100))


def _priority_band(score: int) -> str:
    if score >= 90:
        return PRIORITY_CRITICAL
    if score >= 70:
        return PRIORITY_HIGH
    if score >= 40:
        return PRIORITY_MEDIUM
    if score >= 15:
        return PRIORITY_LOW
    return PRIORITY_NONE


def _build_priority_queue(explanations: pd.DataFrame) -> pd.DataFrame:
    if explanations.empty:
        return explanations.copy()

    actionable = explanations[
        explanations["operator_action_class"].isin(
            [ACTION_PUBLISH_NOW, ACTION_REVIEW_NOW, ACTION_INVESTIGATE_DEFECT]
        )
        | explanations["operator_priority_band"].isin([PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM])
    ].copy()

    if actionable.empty:
        return actionable

    actionable["_publishability_rank"] = (
        actionable["operator_action_class"] == ACTION_PUBLISH_NOW
    ).astype(int)
    actionable["_materiality_rank"] = actionable["materially_changed_flag"].astype(int)

    actionable = actionable.sort_values(
        by=["operator_priority_score", "_materiality_rank", "_publishability_rank"],
        ascending=[False, False, False],
    )

    return actionable.drop(columns=["_publishability_rank", "_materiality_rank"])


def _build_action_summary(explanations: pd.DataFrame) -> CommercialActionSummary:
    return CommercialActionSummary(
        action_publish_now_count=int((explanations["operator_action_class"] == ACTION_PUBLISH_NOW).sum()),
        action_review_now_count=int((explanations["operator_action_class"] == ACTION_REVIEW_NOW).sum()),
        action_monitor_count=int((explanations["operator_action_class"] == ACTION_MONITOR).sum()),
        action_no_action_duplicate_count=int((explanations["operator_action_class"] == ACTION_NO_ACTION_DUPLICATE).sum()),
        action_no_action_true_zero_count=int((explanations["operator_action_class"] == ACTION_NO_ACTION_TRUE_ZERO).sum()),
        action_investigate_defect_count=int((explanations["operator_action_class"] == ACTION_INVESTIGATE_DEFECT).sum()),
        critical_priority_count=int((explanations["operator_priority_band"] == PRIORITY_CRITICAL).sum()),
        high_priority_count=int((explanations["operator_priority_band"] == PRIORITY_HIGH).sum()),
        medium_priority_count=int((explanations["operator_priority_band"] == PRIORITY_MEDIUM).sum()),
        low_priority_count=int((explanations["operator_priority_band"] == PRIORITY_LOW).sum()),
    )


def _validate_explanation_consistency(
    *,
    explanations: pd.DataFrame,
    priority_queue: pd.DataFrame,
    action_summary: CommercialActionSummary,
) -> None:
    errors: list[str] = []

    unchanged_with_fields = explanations[
        (explanations["row_change_class"] == ROW_CHANGE_UNCHANGED)
        & (explanations["changed_fields"].fillna("").astype(str).str.strip() != "")
    ]
    if not unchanged_with_fields.empty:
        errors.append("UNCHANGED_ROW rows contain non-empty changed_fields")

    invalid_publish_action = explanations[
        (explanations["operator_action_class"] == ACTION_PUBLISH_NOW)
        & (explanations["excluded_from_publish_flag"] == True)
    ]
    if not invalid_publish_action.empty:
        errors.append("ACTION_PUBLISH_NOW assigned while excluded_from_publish_flag is true")

    invalid_duplicate_action = explanations[
        (explanations["operator_action_class"] == ACTION_NO_ACTION_DUPLICATE)
        & (explanations["duplicate_blocked_flag"] != True)
    ]
    if not invalid_duplicate_action.empty:
        errors.append("ACTION_NO_ACTION_DUPLICATE assigned without duplicate_blocked_flag")

    invalid_true_zero_action = explanations[
        (explanations["operator_action_class"] == ACTION_NO_ACTION_TRUE_ZERO)
        & (explanations["current_demand_evidence_class"] != "true_zero_demand")
    ]
    if not invalid_true_zero_action.empty:
        errors.append("ACTION_NO_ACTION_TRUE_ZERO assigned when demand_evidence_class is not true_zero_demand")

    # Action summary count reconciliation
    if action_summary.action_publish_now_count != int((explanations["operator_action_class"] == ACTION_PUBLISH_NOW).sum()):
        errors.append("action_publish_now_count does not reconcile")
    if action_summary.action_review_now_count != int((explanations["operator_action_class"] == ACTION_REVIEW_NOW).sum()):
        errors.append("action_review_now_count does not reconcile")
    if action_summary.action_monitor_count != int((explanations["operator_action_class"] == ACTION_MONITOR).sum()):
        errors.append("action_monitor_count does not reconcile")
    if action_summary.action_no_action_duplicate_count != int((explanations["operator_action_class"] == ACTION_NO_ACTION_DUPLICATE).sum()):
        errors.append("action_no_action_duplicate_count does not reconcile")
    if action_summary.action_no_action_true_zero_count != int((explanations["operator_action_class"] == ACTION_NO_ACTION_TRUE_ZERO).sum()):
        errors.append("action_no_action_true_zero_count does not reconcile")
    if action_summary.action_investigate_defect_count != int((explanations["operator_action_class"] == ACTION_INVESTIGATE_DEFECT).sum()):
        errors.append("action_investigate_defect_count does not reconcile")

    # Priority queue rows must be subset of explanations
    explanation_keys = set(
        explanations.apply(
            lambda r: (
                str(r["store_number"]),
                str(r["sku_number"]),
                str(r["promotion_start_date"]),
                str(r["promotion_end_date"]),
            ),
            axis=1,
        )
    )
    queue_keys = set(
        priority_queue.apply(
            lambda r: (
                str(r["store_number"]),
                str(r["sku_number"]),
                str(r["promotion_start_date"]),
                str(r["promotion_end_date"]),
            ),
            axis=1,
        )
    )
    if not queue_keys.issubset(explanation_keys):
        errors.append("priority queue contains rows not present in commercial_change_explanations")

    if errors:
        raise ValueError(
            "Commercial change explanation consistency check failed:\n" + "\n".join(errors)
        )


def _normalize_frame(frame: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    normalized = frame.copy()

    normalized["store_number"] = normalized.get("store_number", pd.Series(dtype="object")).astype(str)
    normalized["sku_number"] = normalized.get("sku_number", pd.Series(dtype="object")).astype(str)
    normalized["promotion_start_date"] = normalized.get("promotion_start_date", pd.Series(dtype="object")).astype(str)
    normalized["promotion_end_date"] = normalized.get("promotion_end_date", pd.Series(dtype="object")).astype(str)

    decision = normalized.get("decision_recommendation", pd.Series("", index=normalized.index)).fillna("").astype(str)
    publish_eligibility = normalized.get("publish_eligibility_reason", pd.Series("", index=normalized.index)).fillna("").astype(str)
    demand_evidence = normalized.get("demand_evidence_class", pd.Series("", index=normalized.index)).fillna("").astype(str)
    review_reason = normalized.get("review_reason", pd.Series("", index=normalized.index)).fillna("").astype(str)
    suggested_units = pd.to_numeric(
        normalized.get("suggested_order_units", pd.Series(0, index=normalized.index)),
        errors="coerce",
    ).fillna(0.0)

    publishable_flag = _infer_publishable(decision, review_reason, suggested_units)
    review_required_flag = (review_reason.str.strip() != "")
    excluded_from_publish_flag = ~publishable_flag

    return pd.DataFrame(
        {
            "store_number": normalized["store_number"],
            "sku_number": normalized["sku_number"],
            "promotion_start_date": normalized["promotion_start_date"],
            "promotion_end_date": normalized["promotion_end_date"],
            f"{prefix}_row_present": True,
            f"{prefix}_decision_recommendation": decision,
            f"{prefix}_publish_eligibility_class": publish_eligibility,
            f"{prefix}_demand_evidence_class": demand_evidence,
            f"{prefix}_recommended_order_units": suggested_units,
            f"{prefix}_publishable_flag": publishable_flag,
            f"{prefix}_review_required_flag": review_required_flag,
            f"{prefix}_excluded_from_publish_flag": excluded_from_publish_flag,
        }
    )


def _infer_publishable(
    decision: pd.Series,
    review_reason: pd.Series,
    suggested_order_units: pd.Series,
) -> pd.Series:
    decision_upper = decision.str.upper()
    publishable_decision = decision_upper.isin({"ORDER", "PUBLISH", "RECOMMEND_ORDER", "AUTO_ORDER"})
    positive_units = suggested_order_units > 0
    blocked_by_review = review_reason.str.strip() != ""
    return ((publishable_decision | positive_units) & (~blocked_by_review)).astype(bool)


def _nullable_string(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if text == "nan" or text == "None" or text == "":
        return None
    return text


def _nullable_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(as_float):
        return None
    return as_float


def _slug(value: Optional[str]) -> str:
    if value is None:
        return "none"
    return value.strip().lower().replace(" ", "_") if value.strip() else "none"


def _explanations_columns() -> list[str]:
    return [
        "store_number",
        "sku_number",
        "promotion_start_date",
        "promotion_end_date",
        "prior_decision_recommendation",
        "current_decision_recommendation",
        "prior_publish_eligibility_class",
        "current_publish_eligibility_class",
        "prior_demand_evidence_class",
        "current_demand_evidence_class",
        "prior_recommended_order_units",
        "current_recommended_order_units",
        "recommended_order_units_delta",
        "row_change_class",
        "row_change_reason_code",
        "row_change_reason",
        "operator_action_class",
        "operator_action_reason",
        "operator_priority_score",
        "operator_priority_band",
        "materially_changed_flag",
        "changed_fields",
        "review_required_flag",
        "excluded_from_publish_flag",
        "duplicate_blocked_flag",
    ]
