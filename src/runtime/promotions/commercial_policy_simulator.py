from __future__ import annotations

"""Authoritative governed policy simulation seam for pre-change impact assessment."""

from dataclasses import asdict, dataclass
from typing import Optional

import pandas as pd

SIMULATION_READY = "SIMULATION_READY"
SIMULATION_LOW_COVERAGE = "SIMULATION_LOW_COVERAGE"
SIMULATION_BLOCKED_DEFECT = "SIMULATION_BLOCKED_DEFECT"
SIMULATION_NOT_COMPARABLE = "SIMULATION_NOT_COMPARABLE"

SIMULATED_TIGHTEN = "SIMULATED_TIGHTEN"
SIMULATED_LOOSEN = "SIMULATED_LOOSEN"
SIMULATED_HOLD = "SIMULATED_HOLD"
SIMULATED_INCONCLUSIVE = "SIMULATED_INCONCLUSIVE"

SIMULATION_IMMATERIAL = "SIMULATION_IMMATERIAL"
SIMULATION_LOW_MATERIALITY = "SIMULATION_LOW_MATERIALITY"
SIMULATION_MEDIUM_MATERIALITY = "SIMULATION_MEDIUM_MATERIALITY"
SIMULATION_HIGH_MATERIALITY = "SIMULATION_HIGH_MATERIALITY"

SIMULATION_LOW_RISK = "SIMULATION_LOW_RISK"
SIMULATION_MODERATE_RISK = "SIMULATION_MODERATE_RISK"
SIMULATION_HIGH_RISK = "SIMULATION_HIGH_RISK"
SIMULATION_UNKNOWN_RISK = "SIMULATION_UNKNOWN_RISK"

_BASELINE_PUBLISH = "BASELINE_PUBLISH"
_BASELINE_REVIEW = "BASELINE_REVIEW"
_BASELINE_EXCLUDED = "BASELINE_EXCLUDED"

_SEGMENT_TYPES = [
    "store_number",
    "promotion_cycle",
    "operator_action_class",
    "publish_eligibility_class",
    "demand_evidence_class",
    "recommendation_effectiveness_class",
]

_MIN_EVIDENCE_ROWS = 8


@dataclass(frozen=True)
class CommercialPolicySimulationSummary:
    simulation_readiness_class: str
    simulation_readiness_reason: str
    simulated_policy_direction_class: str
    simulated_policy_direction_reason: str
    simulated_materiality_class: Optional[str]
    simulated_materiality_reason: Optional[str]
    simulated_risk_class: Optional[str]
    simulated_risk_reason: Optional[str]
    operator_review_recommended_flag: bool
    model_owner_review_recommended_flag: bool
    baseline_publish_row_count: int
    simulated_publish_row_count: int
    baseline_review_row_count: int
    simulated_review_row_count: int
    baseline_excluded_row_count: int
    simulated_excluded_row_count: int
    net_publish_delta: int
    net_review_delta: int
    net_excluded_delta: int
    affected_store_count: int
    affected_promotion_count: int
    affected_row_count: int
    affected_operator_action_count: int
    high_risk_affected_row_count: int
    low_confidence_affected_row_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialPolicySimulationArtifacts:
    summary: CommercialPolicySimulationSummary
    by_segment: pd.DataFrame
    watchlist: pd.DataFrame
    simulation_brief_markdown: str


def build_commercial_policy_simulation_artifacts(
    *,
    attribution: pd.DataFrame,
    calibration_summary: dict[str, object],
    current_commercial_outcome_class: str,
) -> CommercialPolicySimulationArtifacts:
    normalized = _normalize_attribution(attribution)

    simulation_input = _simulate_rows(
        attribution=normalized,
        calibration_summary=calibration_summary,
        current_commercial_outcome_class=current_commercial_outcome_class,
    )

    summary = _build_summary(
        attribution=normalized,
        simulation_input=simulation_input,
    )

    by_segment = _build_simulation_by_segment(simulation_input)
    watchlist = _build_watchlist(by_segment)

    _validate_simulation_consistency(
        summary=summary,
        simulation_input=simulation_input,
        by_segment=by_segment,
        watchlist=watchlist,
    )

    simulation_brief_markdown = build_commercial_policy_simulation_brief(
        summary=summary,
        by_segment=by_segment,
        watchlist=watchlist,
    )

    return CommercialPolicySimulationArtifacts(
        summary=summary,
        by_segment=by_segment,
        watchlist=watchlist,
        simulation_brief_markdown=simulation_brief_markdown,
    )


def build_commercial_policy_simulation_brief(
    *,
    summary: CommercialPolicySimulationSummary,
    by_segment: pd.DataFrame,
    watchlist: pd.DataFrame,
) -> str:
    winners = _segment_preview_lines(by_segment, is_winner=True)
    risks = _segment_preview_lines(by_segment, is_winner=False)
    watch_lines = _watchlist_preview_lines(watchlist)

    return f"""# Commercial Policy Simulation Brief

## Simulation Readiness

- **Readiness Class**: {summary.simulation_readiness_class}
- **Readiness Reason**: {summary.simulation_readiness_reason}
- **Direction Class**: {summary.simulated_policy_direction_class}
- **Direction Reason**: {summary.simulated_policy_direction_reason}
- **Materiality Class**: {summary.simulated_materiality_class}
- **Risk Class**: {summary.simulated_risk_class}

## Baseline vs Simulated Outcome

- **Baseline Publish Rows**: {summary.baseline_publish_row_count}
- **Simulated Publish Rows**: {summary.simulated_publish_row_count}
- **Net Publish Delta**: {summary.net_publish_delta}
- **Baseline Review Rows**: {summary.baseline_review_row_count}
- **Simulated Review Rows**: {summary.simulated_review_row_count}
- **Net Review Delta**: {summary.net_review_delta}
- **Baseline Excluded Rows**: {summary.baseline_excluded_row_count}
- **Simulated Excluded Rows**: {summary.simulated_excluded_row_count}
- **Net Excluded Delta**: {summary.net_excluded_delta}
- **Affected Rows**: {summary.affected_row_count}
- **Affected Stores**: {summary.affected_store_count}
- **Affected Promotions**: {summary.affected_promotion_count}

## Biggest Winners

{chr(10).join([f"- {line}" for line in winners])}

## Biggest Risks

{chr(10).join([f"- {line}" for line in risks])}

## Watchlist

{chr(10).join([f"- {line}" for line in watch_lines])}

## Recommended Next Actions

- **Operator Review Recommended**: {summary.operator_review_recommended_flag}
- **Model Owner Review Recommended**: {summary.model_owner_review_recommended_flag}
"""


def _simulate_rows(
    *,
    attribution: pd.DataFrame,
    calibration_summary: dict[str, object],
    current_commercial_outcome_class: str,
) -> pd.DataFrame:
    simulated = attribution.copy()

    simulated["promotion_cycle"] = (
        simulated["promotion_start_date"].astype(str)
        + "_to_"
        + simulated["promotion_end_date"].astype(str)
    )

    simulated["baseline_state"] = simulated.apply(_baseline_state, axis=1)

    readiness_class, readiness_reason = _simulation_readiness(
        attribution=simulated,
        current_commercial_outcome_class=current_commercial_outcome_class,
    )

    direction_class, direction_reason = _simulation_direction(
        readiness_class=readiness_class,
        calibration_summary=calibration_summary,
    )

    simulated["simulated_state"] = simulated.apply(
        lambda row: _simulate_state(
            row=row,
            readiness_class=readiness_class,
            direction_class=direction_class,
        ),
        axis=1,
    )

    simulated["affected_flag"] = simulated["baseline_state"] != simulated["simulated_state"]

    simulated.attrs["simulation_readiness_class"] = readiness_class
    simulated.attrs["simulation_readiness_reason"] = readiness_reason
    simulated.attrs["simulated_policy_direction_class"] = direction_class
    simulated.attrs["simulated_policy_direction_reason"] = direction_reason

    return simulated


def _build_summary(*, attribution: pd.DataFrame, simulation_input: pd.DataFrame) -> CommercialPolicySimulationSummary:
    readiness_class = str(simulation_input.attrs.get("simulation_readiness_class", SIMULATION_NOT_COMPARABLE))
    readiness_reason = str(simulation_input.attrs.get("simulation_readiness_reason", "Simulation readiness unavailable."))
    direction_class = str(simulation_input.attrs.get("simulated_policy_direction_class", SIMULATED_INCONCLUSIVE))
    direction_reason = str(simulation_input.attrs.get("simulated_policy_direction_reason", "Simulation direction unavailable."))

    baseline_publish = int((simulation_input["baseline_state"] == _BASELINE_PUBLISH).sum())
    simulated_publish = int((simulation_input["simulated_state"] == _BASELINE_PUBLISH).sum())
    baseline_review = int((simulation_input["baseline_state"] == _BASELINE_REVIEW).sum())
    simulated_review = int((simulation_input["simulated_state"] == _BASELINE_REVIEW).sum())
    baseline_excluded = int((simulation_input["baseline_state"] == _BASELINE_EXCLUDED).sum())
    simulated_excluded = int((simulation_input["simulated_state"] == _BASELINE_EXCLUDED).sum())

    net_publish_delta = simulated_publish - baseline_publish
    net_review_delta = simulated_review - baseline_review
    net_excluded_delta = simulated_excluded - baseline_excluded

    affected = simulation_input[simulation_input["affected_flag"] == True]
    affected_row_count = int(len(affected.index))

    affected_store_count = int(affected["store_number"].astype(str).nunique()) if not affected.empty else 0
    affected_promotion_count = int(affected["promotion_cycle"].astype(str).nunique()) if not affected.empty else 0
    affected_operator_action_count = int(affected["operator_action_class"].astype(str).nunique()) if not affected.empty else 0

    high_risk_affected_row_count = int(
        affected["recommendation_effectiveness_class"].isin(["HARMFUL", "INEFFECTIVE"]).sum()
    )
    low_confidence_affected_row_count = int(
        affected["attribution_confidence_class"].isin(["LOW", "NONE"]).sum()
    )

    if readiness_class != SIMULATION_READY:
        materiality_class = None
        materiality_reason = None
        risk_class = None
        risk_reason = None
    else:
        materiality_class, materiality_reason = _materiality(
            total_rows=int(len(simulation_input.index)),
            affected_rows=affected_row_count,
            net_publish_delta=net_publish_delta,
        )
        risk_class, risk_reason = _risk(
            affected_rows=affected_row_count,
            high_risk_rows=high_risk_affected_row_count,
            low_confidence_rows=low_confidence_affected_row_count,
        )

    operator_review_recommended_flag = bool(
        readiness_class == SIMULATION_READY
        and (
            (materiality_class in {SIMULATION_MEDIUM_MATERIALITY, SIMULATION_HIGH_MATERIALITY})
            or (risk_class in {SIMULATION_MODERATE_RISK, SIMULATION_HIGH_RISK})
        )
    )
    model_owner_review_recommended_flag = bool(
        readiness_class == SIMULATION_READY
        and (
            risk_class == SIMULATION_HIGH_RISK
            or abs(net_publish_delta) >= 25
            or affected_operator_action_count >= 3
        )
    )

    return CommercialPolicySimulationSummary(
        simulation_readiness_class=readiness_class,
        simulation_readiness_reason=readiness_reason,
        simulated_policy_direction_class=direction_class,
        simulated_policy_direction_reason=direction_reason,
        simulated_materiality_class=materiality_class,
        simulated_materiality_reason=materiality_reason,
        simulated_risk_class=risk_class,
        simulated_risk_reason=risk_reason,
        operator_review_recommended_flag=operator_review_recommended_flag,
        model_owner_review_recommended_flag=model_owner_review_recommended_flag,
        baseline_publish_row_count=baseline_publish,
        simulated_publish_row_count=simulated_publish,
        baseline_review_row_count=baseline_review,
        simulated_review_row_count=simulated_review,
        baseline_excluded_row_count=baseline_excluded,
        simulated_excluded_row_count=simulated_excluded,
        net_publish_delta=net_publish_delta,
        net_review_delta=net_review_delta,
        net_excluded_delta=net_excluded_delta,
        affected_store_count=affected_store_count,
        affected_promotion_count=affected_promotion_count,
        affected_row_count=affected_row_count,
        affected_operator_action_count=affected_operator_action_count,
        high_risk_affected_row_count=high_risk_affected_row_count,
        low_confidence_affected_row_count=low_confidence_affected_row_count,
    )


def _build_simulation_by_segment(simulation_input: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for segment_type in _SEGMENT_TYPES:
        grouped = simulation_input.groupby(segment_type, dropna=False)
        for segment_value_raw, seg in grouped:
            segment_value = _segment_value(segment_value_raw)
            baseline_publish = int((seg["baseline_state"] == _BASELINE_PUBLISH).sum())
            simulated_publish = int((seg["simulated_state"] == _BASELINE_PUBLISH).sum())
            baseline_review = int((seg["baseline_state"] == _BASELINE_REVIEW).sum())
            simulated_review = int((seg["simulated_state"] == _BASELINE_REVIEW).sum())
            affected = int((seg["affected_flag"] == True).sum())

            materiality_class = _segment_materiality(
                total_rows=int(len(seg.index)),
                affected_rows=affected,
                net_publish_delta=simulated_publish - baseline_publish,
            )
            risk_class = _segment_risk(seg)

            rows.append(
                {
                    "segment_type": segment_type,
                    "segment_value": segment_value,
                    "baseline_publish_row_count": baseline_publish,
                    "simulated_publish_row_count": simulated_publish,
                    "net_publish_delta": simulated_publish - baseline_publish,
                    "baseline_review_row_count": baseline_review,
                    "simulated_review_row_count": simulated_review,
                    "net_review_delta": simulated_review - baseline_review,
                    "affected_row_count": affected,
                    "simulated_materiality_class": materiality_class,
                    "simulated_risk_class": risk_class,
                    "recommended_attention_flag": bool(
                        materiality_class in {SIMULATION_MEDIUM_MATERIALITY, SIMULATION_HIGH_MATERIALITY}
                        or risk_class in {SIMULATION_MODERATE_RISK, SIMULATION_HIGH_RISK}
                    ),
                }
            )

    return pd.DataFrame(rows, columns=_segment_columns())


def _build_watchlist(by_segment: pd.DataFrame) -> pd.DataFrame:
    if by_segment.empty:
        return by_segment.copy()

    watch_rows: list[dict[str, object]] = []
    for _, row in by_segment.iterrows():
        affected = int(row.get("affected_row_count", 0) or 0)
        abs_delta = abs(int(row.get("net_publish_delta", 0) or 0))
        risk = str(row.get("simulated_risk_class", ""))
        materiality = str(row.get("simulated_materiality_class", ""))
        segment_type = str(row.get("segment_type", ""))
        segment_value = str(row.get("segment_value", ""))

        reason: Optional[str] = None
        if risk == SIMULATION_HIGH_RISK:
            reason = "HIGHEST_RISK_SEGMENT"
        elif materiality == SIMULATION_HIGH_MATERIALITY:
            reason = "HIGHEST_IMPACT_SEGMENT"
        elif abs_delta >= 5:
            reason = "LARGE_PUBLISH_DELTA_SEGMENT"
        elif risk == SIMULATION_UNKNOWN_RISK and affected >= 5:
            reason = "WEAK_EVIDENCE_LARGE_EFFECT_SEGMENT"

        if reason is None:
            continue

        watch_rows.append(
            {
                "segment_type": segment_type,
                "segment_value": segment_value,
                "watch_reason": reason,
                "affected_row_count": affected,
                "net_publish_delta": int(row.get("net_publish_delta", 0) or 0),
                "simulated_materiality_class": materiality,
                "simulated_risk_class": risk,
                "recommended_attention_flag": bool(row.get("recommended_attention_flag", False)),
            }
        )

    watchlist = pd.DataFrame(watch_rows)
    if watchlist.empty:
        return watchlist

    return watchlist.sort_values(
        by=["affected_row_count", "net_publish_delta"],
        ascending=[False, False],
    )


def _validate_simulation_consistency(
    *,
    summary: CommercialPolicySimulationSummary,
    simulation_input: pd.DataFrame,
    by_segment: pd.DataFrame,
    watchlist: pd.DataFrame,
) -> None:
    errors: list[str] = []

    source_count = int(len(simulation_input.index))
    baseline_total = (
        summary.baseline_publish_row_count
        + summary.baseline_review_row_count
        + summary.baseline_excluded_row_count
    )
    simulated_total = (
        summary.simulated_publish_row_count
        + summary.simulated_review_row_count
        + summary.simulated_excluded_row_count
    )
    if baseline_total != source_count:
        errors.append("Baseline publish/review/excluded row counts do not reconcile to source rows")
    if simulated_total != source_count:
        errors.append("Simulated publish/review/excluded row counts do not reconcile to source rows")

    if summary.affected_row_count > source_count:
        errors.append("affected_row_count exceeds source row count")
    if summary.affected_store_count > int(simulation_input["store_number"].astype(str).nunique()):
        errors.append("affected_store_count exceeds source store count")
    if summary.affected_promotion_count > int(simulation_input["promotion_cycle"].astype(str).nunique()):
        errors.append("affected_promotion_count exceeds source promotion count")

    if summary.simulated_policy_direction_class == SIMULATED_TIGHTEN and summary.net_publish_delta > 0:
        errors.append("SIMULATED_TIGHTEN produced positive net_publish_delta")
    if summary.simulated_policy_direction_class == SIMULATED_LOOSEN and summary.net_publish_delta < 0:
        errors.append("SIMULATED_LOOSEN produced negative net_publish_delta")

    if summary.simulation_readiness_class == SIMULATION_READY and _ready_evidence_count(simulation_input) == 0:
        errors.append("SIMULATION_READY cannot be reported when attribution-ready evidence rows are zero")

    if summary.simulation_readiness_class != SIMULATION_READY:
        if summary.simulated_materiality_class is not None or summary.simulated_risk_class is not None:
            errors.append("simulated materiality/risk must be null when simulation readiness is not ready")

    if not watchlist.empty:
        by_segment_keys = set(
            by_segment.apply(
                lambda r: (str(r["segment_type"]), str(r["segment_value"])),
                axis=1,
            )
        )
        watch_keys = set(
            watchlist.apply(
                lambda r: (str(r["segment_type"]), str(r["segment_value"])),
                axis=1,
            )
        )
        if not watch_keys.issubset(by_segment_keys):
            errors.append("Watchlist rows are absent from simulation-by-segment source set")

    if errors:
        raise ValueError("Commercial policy simulation consistency check failed:\n" + "\n".join(errors))


def _baseline_state(row: pd.Series) -> str:
    action = str(row.get("operator_action_class", ""))
    eligibility = str(row.get("publish_eligibility_class", "")).lower()

    if action == "ACTION_PUBLISH_NOW" and not eligibility.startswith("review"):
        return _BASELINE_PUBLISH
    if action == "ACTION_REVIEW_NOW" or eligibility.startswith("review"):
        return _BASELINE_REVIEW
    return _BASELINE_EXCLUDED


def _simulation_readiness(*, attribution: pd.DataFrame, current_commercial_outcome_class: str) -> tuple[str, str]:
    if "FAILURE" in str(current_commercial_outcome_class) or "DEFECT" in str(current_commercial_outcome_class):
        return (
            SIMULATION_BLOCKED_DEFECT,
            "Commercial outcome indicates defect/failure state; simulation is blocked.",
        )

    if attribution.empty:
        return (
            SIMULATION_NOT_COMPARABLE,
            "Attribution input is empty; simulation is not comparable.",
        )

    ready_count = _ready_evidence_count(attribution)
    if ready_count == 0:
        return (
            SIMULATION_NOT_COMPARABLE,
            "No attribution-ready rows available to support governed simulation.",
        )

    if ready_count < _MIN_EVIDENCE_ROWS:
        return (
            SIMULATION_LOW_COVERAGE,
            "Attribution-ready evidence exists but coverage is below simulation confidence floor.",
        )

    return (
        SIMULATION_READY,
        "Sufficient attribution-ready evidence is available for governed policy simulation.",
    )


def _simulation_direction(*, readiness_class: str, calibration_summary: dict[str, object]) -> tuple[str, str]:
    if readiness_class in {SIMULATION_BLOCKED_DEFECT, SIMULATION_NOT_COMPARABLE, SIMULATION_LOW_COVERAGE}:
        return (
            SIMULATED_INCONCLUSIVE,
            "Simulation is not ready for directional policy movement due to readiness constraints.",
        )

    threshold_direction = str(calibration_summary.get("threshold_direction_class", ""))
    policy_signal = str(calibration_summary.get("policy_signal_class", ""))

    if threshold_direction == "TIGHTEN_PUBLISH_POLICY" and policy_signal in {"POLICY_SIGNAL_WEAKEN", "POLICY_SIGNAL_HOLD"}:
        return (SIMULATED_TIGHTEN, "Calibration indicates tighten-path simulation should be assessed.")

    if threshold_direction == "LOOSEN_PUBLISH_POLICY" and policy_signal in {"POLICY_SIGNAL_STRENGTHEN", "POLICY_SIGNAL_HOLD"}:
        return (SIMULATED_LOOSEN, "Calibration indicates loosen-path simulation should be assessed.")

    if threshold_direction in {"HOLD_POLICY", "INVESTIGATE_SEGMENT", "NO_THRESHOLD_RECOMMENDATION"}:
        return (SIMULATED_HOLD, "Calibration indicates hold/investigate posture; simulation applies hold scenario.")

    return (
        SIMULATED_INCONCLUSIVE,
        "Calibration direction is inconclusive for tighten/loosen simulation.",
    )


def _simulate_state(*, row: pd.Series, readiness_class: str, direction_class: str) -> str:
    baseline_state = str(row.get("baseline_state", _BASELINE_EXCLUDED))
    if readiness_class != SIMULATION_READY:
        return baseline_state

    confidence = str(row.get("attribution_confidence_class", "NONE"))
    effectiveness = str(row.get("recommendation_effectiveness_class", "INCONCLUSIVE"))
    demand = str(row.get("demand_evidence_class", ""))

    if direction_class == SIMULATED_TIGHTEN:
        if baseline_state == _BASELINE_PUBLISH and (
            confidence in {"LOW", "NONE"}
            or effectiveness in {"HARMFUL", "INEFFECTIVE", "INCONCLUSIVE"}
            or demand in {"artificial_collapse", "low_nonzero_demand"}
        ):
            return _BASELINE_REVIEW
        return baseline_state

    if direction_class == SIMULATED_LOOSEN:
        if baseline_state in {_BASELINE_REVIEW, _BASELINE_EXCLUDED} and (
            confidence in {"HIGH", "MEDIUM"}
            and effectiveness in {"EFFECTIVE_STRONG", "EFFECTIVE_MODERATE", "NEUTRAL"}
            and demand in {"healthy_nonzero_demand", "low_nonzero_demand", "cold_start_new_line"}
        ):
            return _BASELINE_PUBLISH
        return baseline_state

    return baseline_state


def _materiality(*, total_rows: int, affected_rows: int, net_publish_delta: int) -> tuple[str, str]:
    if total_rows <= 0:
        return (SIMULATION_IMMATERIAL, "No rows available for materiality assessment.")

    share = affected_rows / max(total_rows, 1)
    publish_delta_abs = abs(net_publish_delta)

    if affected_rows == 0:
        return (SIMULATION_IMMATERIAL, "No rows are affected by the simulated policy change.")
    if share < 0.05 and publish_delta_abs < 5:
        return (SIMULATION_LOW_MATERIALITY, "Simulated impact is low relative to total governed output volume.")
    if share < 0.20 and publish_delta_abs < 20:
        return (SIMULATION_MEDIUM_MATERIALITY, "Simulated impact is commercially meaningful but not broad-scale.")
    return (SIMULATION_HIGH_MATERIALITY, "Simulated impact is broad and materially shifts publish/review posture.")


def _risk(*, affected_rows: int, high_risk_rows: int, low_confidence_rows: int) -> tuple[str, str]:
    if affected_rows <= 0:
        return (SIMULATION_LOW_RISK, "No affected rows implies low simulation risk.")

    high_risk_share = high_risk_rows / max(affected_rows, 1)
    low_conf_share = low_confidence_rows / max(affected_rows, 1)

    if high_risk_share >= 0.40 or low_conf_share >= 0.50:
        return (SIMULATION_HIGH_RISK, "Affected rows contain high harmful or low-confidence concentration.")
    if high_risk_share >= 0.20 or low_conf_share >= 0.30:
        return (SIMULATION_MODERATE_RISK, "Affected rows include moderate harmful/low-confidence concentration.")
    return (SIMULATION_LOW_RISK, "Affected rows are mostly confidence-qualified with low harmful concentration.")


def _segment_materiality(*, total_rows: int, affected_rows: int, net_publish_delta: int) -> str:
    klass, _ = _materiality(
        total_rows=total_rows,
        affected_rows=affected_rows,
        net_publish_delta=net_publish_delta,
    )
    return klass


def _segment_risk(segment: pd.DataFrame) -> str:
    affected = segment[segment["affected_flag"] == True]
    if affected.empty:
        return SIMULATION_LOW_RISK

    high_risk_rows = int(affected["recommendation_effectiveness_class"].isin(["HARMFUL", "INEFFECTIVE"]).sum())
    low_conf_rows = int(affected["attribution_confidence_class"].isin(["LOW", "NONE"]).sum())

    risk, _ = _risk(
        affected_rows=int(len(affected.index)),
        high_risk_rows=high_risk_rows,
        low_confidence_rows=low_conf_rows,
    )
    return risk


def _normalize_attribution(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in [
        "store_number",
        "promotion_start_date",
        "promotion_end_date",
        "operator_action_class",
        "publish_eligibility_class",
        "demand_evidence_class",
        "recommendation_effectiveness_class",
        "attribution_confidence_class",
        "attribution_status",
    ]:
        if column not in normalized.columns:
            normalized[column] = None

    normalized["store_number"] = normalized["store_number"].fillna("unknown").astype(str)
    normalized["promotion_start_date"] = normalized["promotion_start_date"].fillna("unknown").astype(str)
    normalized["promotion_end_date"] = normalized["promotion_end_date"].fillna("unknown").astype(str)
    normalized["operator_action_class"] = normalized["operator_action_class"].fillna("unknown").astype(str)
    normalized["publish_eligibility_class"] = normalized["publish_eligibility_class"].fillna("unknown").astype(str)
    normalized["demand_evidence_class"] = normalized["demand_evidence_class"].fillna("unknown").astype(str)
    normalized["recommendation_effectiveness_class"] = normalized["recommendation_effectiveness_class"].fillna("INCONCLUSIVE").astype(str)
    normalized["attribution_confidence_class"] = normalized["attribution_confidence_class"].fillna("NONE").astype(str)
    normalized["attribution_status"] = normalized["attribution_status"].fillna("unknown").astype(str)
    return normalized


def _ready_evidence_count(frame: pd.DataFrame) -> int:
    return int((frame["attribution_status"] == "ATTRIBUTION_READY").sum())


def _segment_columns() -> list[str]:
    return [
        "segment_type",
        "segment_value",
        "baseline_publish_row_count",
        "simulated_publish_row_count",
        "net_publish_delta",
        "baseline_review_row_count",
        "simulated_review_row_count",
        "net_review_delta",
        "affected_row_count",
        "simulated_materiality_class",
        "simulated_risk_class",
        "recommended_attention_flag",
    ]


def _segment_value(value: object) -> str:
    if value is None:
        return "null"
    text = str(value).strip()
    return text if text else "null"


def _segment_preview_lines(by_segment: pd.DataFrame, *, is_winner: bool) -> list[str]:
    if by_segment.empty:
        return ["No segment simulation results available."]

    if is_winner:
        subset = by_segment.sort_values(by=["net_publish_delta", "affected_row_count"], ascending=[False, False])
        subset = subset[subset["net_publish_delta"] > 0]
        if subset.empty:
            return ["No publish-expansion winners identified in this simulation."]
    else:
        subset = by_segment.sort_values(by=["affected_row_count", "net_publish_delta"], ascending=[False, True])
        subset = subset[
            (subset["simulated_risk_class"].isin([SIMULATION_MODERATE_RISK, SIMULATION_HIGH_RISK]))
            | (subset["net_publish_delta"] < 0)
        ]
        if subset.empty:
            return ["No major risk segments identified in this simulation."]

    lines: list[str] = []
    for _, row in subset.head(10).iterrows():
        lines.append(
            f"{row['segment_type']}={row['segment_value']} | net_publish_delta={int(row['net_publish_delta'])} | affected_rows={int(row['affected_row_count'])} | risk={row['simulated_risk_class']}"
        )
    return lines


def _watchlist_preview_lines(watchlist: pd.DataFrame) -> list[str]:
    if watchlist.empty:
        return ["No simulation watchlist segments are currently flagged."]

    lines: list[str] = []
    for _, row in watchlist.head(10).iterrows():
        lines.append(
            f"{row['segment_type']}={row['segment_value']} | reason={row['watch_reason']} | net_publish_delta={int(row['net_publish_delta'])} | affected_rows={int(row['affected_row_count'])}"
        )
    return lines
