from __future__ import annotations

"""Authoritative governed policy calibration seam based on attributed outcomes."""

from dataclasses import asdict, dataclass
from typing import Optional

import pandas as pd

POLICY_SIGNAL_STRENGTHEN = "POLICY_SIGNAL_STRENGTHEN"
POLICY_SIGNAL_WEAKEN = "POLICY_SIGNAL_WEAKEN"
POLICY_SIGNAL_HOLD = "POLICY_SIGNAL_HOLD"
POLICY_SIGNAL_INCONCLUSIVE = "POLICY_SIGNAL_INCONCLUSIVE"
POLICY_SIGNAL_BLOCKED_DEFECT = "POLICY_SIGNAL_BLOCKED_DEFECT"

CALIBRATION_READY = "CALIBRATION_READY"
CALIBRATION_LOW_COVERAGE = "CALIBRATION_LOW_COVERAGE"
CALIBRATION_LOW_CONFIDENCE = "CALIBRATION_LOW_CONFIDENCE"
CALIBRATION_NOT_READY = "CALIBRATION_NOT_READY"

TIGHTEN_PUBLISH_POLICY = "TIGHTEN_PUBLISH_POLICY"
LOOSEN_PUBLISH_POLICY = "LOOSEN_PUBLISH_POLICY"
HOLD_POLICY = "HOLD_POLICY"
INVESTIGATE_SEGMENT = "INVESTIGATE_SEGMENT"
NO_THRESHOLD_RECOMMENDATION = "NO_THRESHOLD_RECOMMENDATION"

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_NONE = "NONE"

_EFFECTIVE_CLASSES = {"EFFECTIVE_STRONG", "EFFECTIVE_MODERATE"}
_HARMFUL_CLASSES = {"HARMFUL", "INEFFECTIVE"}

_SEGMENT_COLUMNS = [
    "operator_action_class",
    "publish_eligibility_class",
    "demand_evidence_class",
    "recommendation_effectiveness_class",
    "row_change_reason_code",
]

_MIN_GLOBAL_EVIDENCE = 10
_MIN_SEGMENT_EVIDENCE = 5


@dataclass(frozen=True)
class CommercialPolicyCalibrationSummary:
    policy_signal_class: str
    policy_signal_reason: str
    calibration_readiness_class: str
    calibration_readiness_reason: str
    threshold_direction_class: str
    threshold_direction_reason: str
    operator_action_recommendation: str
    model_owner_action_recommendation: str
    confidence_class: str
    evidence_row_count: int
    harmful_rate: Optional[float]
    effective_rate: Optional[float]
    neutral_rate: Optional[float]
    inconclusive_rate: Optional[float]
    effective_count: int
    harmful_count: int
    neutral_count: int
    inconclusive_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialPolicyCalibrationArtifacts:
    summary: CommercialPolicyCalibrationSummary
    by_segment: pd.DataFrame
    watchlist: pd.DataFrame
    calibration_brief_markdown: str


def build_commercial_policy_calibration_artifacts(
    *,
    attribution: pd.DataFrame,
    current_commercial_outcome_class: str,
) -> CommercialPolicyCalibrationArtifacts:
    normalized = _normalize_attribution(attribution)
    summary = _build_summary(
        attribution=normalized,
        current_commercial_outcome_class=current_commercial_outcome_class,
    )
    by_segment = _build_segment_table(
        attribution=normalized,
        blocked_defect=summary.policy_signal_class == POLICY_SIGNAL_BLOCKED_DEFECT,
    )
    watchlist = _build_watchlist(by_segment)

    _validate_policy_calibration_consistency(
        attribution=normalized,
        summary=summary,
        by_segment=by_segment,
        watchlist=watchlist,
    )

    calibration_brief_markdown = build_commercial_policy_calibration_brief(
        summary=summary,
        by_segment=by_segment,
        watchlist=watchlist,
    )

    return CommercialPolicyCalibrationArtifacts(
        summary=summary,
        by_segment=by_segment,
        watchlist=watchlist,
        calibration_brief_markdown=calibration_brief_markdown,
    )


def build_commercial_policy_calibration_brief(
    *,
    summary: CommercialPolicyCalibrationSummary,
    by_segment: pd.DataFrame,
    watchlist: pd.DataFrame,
) -> str:
    tighten_lines = _segment_preview_lines(by_segment, TIGHTEN_PUBLISH_POLICY)
    loosen_lines = _segment_preview_lines(by_segment, LOOSEN_PUBLISH_POLICY)
    hold_lines = _segment_preview_lines(by_segment, HOLD_POLICY)
    watch_lines = _watchlist_preview_lines(watchlist)

    return f"""# Commercial Policy Calibration Brief

## Calibration Readiness

- **Readiness Class**: {summary.calibration_readiness_class}
- **Readiness Reason**: {summary.calibration_readiness_reason}
- **Policy Signal**: {summary.policy_signal_class}
- **Policy Signal Reason**: {summary.policy_signal_reason}
- **Threshold Direction**: {summary.threshold_direction_class}
- **Threshold Reason**: {summary.threshold_direction_reason}
- **Confidence Class**: {summary.confidence_class}
- **Evidence Rows**: {summary.evidence_row_count}

## What to tighten

{chr(10).join([f"- {line}" for line in tighten_lines])}

## What to loosen

{chr(10).join([f"- {line}" for line in loosen_lines])}

## What to leave unchanged

{chr(10).join([f"- {line}" for line in hold_lines])}

## Watchlist

{chr(10).join([f"- {line}" for line in watch_lines])}

## Recommended next actions

- **Operator**: {summary.operator_action_recommendation}
- **Model Owner**: {summary.model_owner_action_recommendation}
"""


def _build_summary(
    *,
    attribution: pd.DataFrame,
    current_commercial_outcome_class: str,
) -> CommercialPolicyCalibrationSummary:
    blocked_defect = "FAILURE" in str(current_commercial_outcome_class) or "DEFECT" in str(current_commercial_outcome_class)

    ready = attribution[attribution["attribution_status"] == "ATTRIBUTION_READY"]
    evidence_row_count = int(len(ready.index))

    effective_count = int(ready["recommendation_effectiveness_class"].isin(_EFFECTIVE_CLASSES).sum())
    harmful_count = int(ready["recommendation_effectiveness_class"].isin(_HARMFUL_CLASSES).sum())
    neutral_count = int((ready["recommendation_effectiveness_class"] == "NEUTRAL").sum())
    inconclusive_count = int((ready["recommendation_effectiveness_class"] == "INCONCLUSIVE").sum())

    effective_rate = _ratio_or_none(effective_count, evidence_row_count)
    harmful_rate = _ratio_or_none(harmful_count, evidence_row_count)
    neutral_rate = _ratio_or_none(neutral_count, evidence_row_count)
    inconclusive_rate = _ratio_or_none(inconclusive_count, evidence_row_count)

    high_conf_count = int((ready["attribution_confidence_class"] == CONFIDENCE_HIGH).sum())
    high_conf_share = (high_conf_count / evidence_row_count) if evidence_row_count > 0 else 0.0

    if blocked_defect:
        readiness_class = CALIBRATION_NOT_READY
        readiness_reason = "Commercial cycle is defect-blocked; calibration cannot produce tighten/loosen advice."
    elif evidence_row_count == 0:
        readiness_class = CALIBRATION_NOT_READY
        readiness_reason = "No attribution-ready evidence rows are available for governed calibration."
    elif evidence_row_count < _MIN_GLOBAL_EVIDENCE:
        readiness_class = CALIBRATION_LOW_COVERAGE
        readiness_reason = "Attribution-ready evidence exists but row coverage is below minimum confidence threshold."
    elif high_conf_share < 0.25:
        readiness_class = CALIBRATION_LOW_CONFIDENCE
        readiness_reason = "Evidence coverage is present but confidence quality is too low for threshold movement advice."
    else:
        readiness_class = CALIBRATION_READY
        readiness_reason = "Sufficient attributed and confidence-qualified evidence is available for policy calibration recommendations."

    confidence_class = _confidence_from_evidence(
        evidence_row_count=evidence_row_count,
        high_conf_share=high_conf_share,
    )

    if blocked_defect:
        policy_signal_class = POLICY_SIGNAL_BLOCKED_DEFECT
        policy_signal_reason = "Defect-blocked state suppresses calibration signal generation."
        threshold_direction_class = NO_THRESHOLD_RECOMMENDATION
        threshold_direction_reason = "Defect-blocked cycles cannot safely generate tighten/loosen threshold advice."
    elif readiness_class == CALIBRATION_NOT_READY:
        policy_signal_class = POLICY_SIGNAL_INCONCLUSIVE
        policy_signal_reason = "Calibration not ready because no attribution-ready evidence exists."
        threshold_direction_class = NO_THRESHOLD_RECOMMENDATION
        threshold_direction_reason = "No threshold recommendation because calibration readiness is not ready."
    elif harmful_rate is not None and effective_rate is not None and harmful_rate >= 0.45 and harmful_count >= effective_count:
        policy_signal_class = POLICY_SIGNAL_WEAKEN
        policy_signal_reason = "Attributed harmful outcomes dominate effective outcomes at meaningful evidence volume."
        threshold_direction_class = TIGHTEN_PUBLISH_POLICY
        threshold_direction_reason = "Tighten publish policy where harmful attributed performance is concentrated."
    elif effective_rate is not None and harmful_rate is not None and effective_rate >= 0.60 and harmful_rate <= 0.15:
        policy_signal_class = POLICY_SIGNAL_STRENGTHEN
        policy_signal_reason = "Effective attributed outcomes dominate with low harmful incidence."
        threshold_direction_class = LOOSEN_PUBLISH_POLICY
        threshold_direction_reason = "Loosen publish policy where high-confidence attributable performance is consistently positive."
    elif readiness_class in {CALIBRATION_LOW_COVERAGE, CALIBRATION_LOW_CONFIDENCE}:
        policy_signal_class = POLICY_SIGNAL_INCONCLUSIVE
        policy_signal_reason = "Evidence exists but is not yet robust enough for broad threshold movement recommendations."
        threshold_direction_class = INVESTIGATE_SEGMENT
        threshold_direction_reason = "Use segment-level investigation rather than global threshold change under weak readiness."
    else:
        policy_signal_class = POLICY_SIGNAL_HOLD
        policy_signal_reason = "Attributed evidence is mixed and does not support broad tighten or loosen shifts."
        threshold_direction_class = HOLD_POLICY
        threshold_direction_reason = "Hold current policy thresholds while targeting specific weak segments for investigation."

    operator_action_recommendation = _operator_recommendation(
        threshold_direction_class=threshold_direction_class,
        readiness_class=readiness_class,
        blocked_defect=blocked_defect,
    )
    model_owner_action_recommendation = _model_owner_recommendation(
        threshold_direction_class=threshold_direction_class,
        readiness_class=readiness_class,
        blocked_defect=blocked_defect,
    )

    return CommercialPolicyCalibrationSummary(
        policy_signal_class=policy_signal_class,
        policy_signal_reason=policy_signal_reason,
        calibration_readiness_class=readiness_class,
        calibration_readiness_reason=readiness_reason,
        threshold_direction_class=threshold_direction_class,
        threshold_direction_reason=threshold_direction_reason,
        operator_action_recommendation=operator_action_recommendation,
        model_owner_action_recommendation=model_owner_action_recommendation,
        confidence_class=confidence_class,
        evidence_row_count=evidence_row_count,
        harmful_rate=harmful_rate,
        effective_rate=effective_rate,
        neutral_rate=neutral_rate,
        inconclusive_rate=inconclusive_rate,
        effective_count=effective_count,
        harmful_count=harmful_count,
        neutral_count=neutral_count,
        inconclusive_count=inconclusive_count,
    )


def _build_segment_table(*, attribution: pd.DataFrame, blocked_defect: bool) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for segment_type in _SEGMENT_COLUMNS:
        grouped = attribution.groupby(segment_type, dropna=False)
        for raw_value, segment in grouped:
            segment_value = _segment_value(raw_value)
            total_count = int(len(segment.index))
            effective_count = int(segment["recommendation_effectiveness_class"].isin(_EFFECTIVE_CLASSES).sum())
            harmful_count = int(segment["recommendation_effectiveness_class"].isin(_HARMFUL_CLASSES).sum())
            neutral_count = int((segment["recommendation_effectiveness_class"] == "NEUTRAL").sum())
            inconclusive_count = int((segment["recommendation_effectiveness_class"] == "INCONCLUSIVE").sum())

            effective_rate = _ratio_or_none(effective_count, total_count)
            harmful_rate = _ratio_or_none(harmful_count, total_count)

            evidence_rows = int((segment["attribution_status"] == "ATTRIBUTION_READY").sum())
            high_conf_share = _high_confidence_share(segment)
            confidence_class = _confidence_from_evidence(
                evidence_row_count=evidence_rows,
                high_conf_share=high_conf_share,
            )

            if blocked_defect:
                signal_class = POLICY_SIGNAL_BLOCKED_DEFECT
                threshold_direction_class = NO_THRESHOLD_RECOMMENDATION
                recommended_action = "Resolve defect state before segment calibration."
            elif evidence_rows < _MIN_SEGMENT_EVIDENCE:
                signal_class = POLICY_SIGNAL_INCONCLUSIVE
                threshold_direction_class = NO_THRESHOLD_RECOMMENDATION
                recommended_action = "Segment evidence is sparse; collect more attributed outcomes first."
            elif harmful_rate is not None and harmful_rate >= 0.50 and harmful_count >= 3:
                signal_class = POLICY_SIGNAL_WEAKEN
                threshold_direction_class = TIGHTEN_PUBLISH_POLICY
                recommended_action = "Tighten publish policy controls for this segment."
            elif (
                effective_rate is not None
                and harmful_rate is not None
                and effective_rate >= 0.65
                and harmful_rate <= 0.15
                and effective_count >= 3
            ):
                signal_class = POLICY_SIGNAL_STRENGTHEN
                threshold_direction_class = LOOSEN_PUBLISH_POLICY
                recommended_action = "Consider loosening publish policy controls for this segment."
            elif (
                harmful_rate is not None
                and effective_rate is not None
                and harmful_rate >= 0.25
                and effective_rate >= 0.25
            ):
                signal_class = POLICY_SIGNAL_HOLD
                threshold_direction_class = INVESTIGATE_SEGMENT
                recommended_action = "Mixed outcomes; investigate segment mechanics before threshold movement."
            else:
                signal_class = POLICY_SIGNAL_HOLD
                threshold_direction_class = HOLD_POLICY
                recommended_action = "Hold threshold settings for this segment under current evidence."

            rows.append(
                {
                    "segment_type": segment_type,
                    "segment_value": segment_value,
                    "evidence_row_count": evidence_rows,
                    "effective_count": effective_count,
                    "harmful_count": harmful_count,
                    "neutral_count": neutral_count,
                    "inconclusive_count": inconclusive_count,
                    "effective_rate": effective_rate,
                    "harmful_rate": harmful_rate,
                    "signal_class": signal_class,
                    "threshold_direction_class": threshold_direction_class,
                    "confidence_class": confidence_class,
                    "recommended_action": recommended_action,
                }
            )

    return pd.DataFrame(rows, columns=_segment_columns())


def _build_watchlist(by_segment: pd.DataFrame) -> pd.DataFrame:
    if by_segment.empty:
        return by_segment.copy()

    watch_rows: list[dict[str, object]] = []
    for _, row in by_segment.iterrows():
        harmful_rate = _nullable_float(row.get("harmful_rate")) or 0.0
        effective_rate = _nullable_float(row.get("effective_rate")) or 0.0
        evidence_count = int(row.get("evidence_row_count", 0) or 0)
        confidence_class = str(row.get("confidence_class", CONFIDENCE_NONE))
        segment_type = str(row.get("segment_type", ""))
        segment_value = str(row.get("segment_value", ""))

        reason: Optional[str] = None
        if harmful_rate >= 0.40 and evidence_count >= _MIN_SEGMENT_EVIDENCE:
            reason = "HIGH_HARM_SEGMENT"
        elif evidence_count >= 10 and effective_rate < 0.35:
            reason = "HIGH_VOLUME_WEAK_SEGMENT"
        elif confidence_class in {CONFIDENCE_LOW, CONFIDENCE_NONE} and evidence_count >= 8:
            reason = "LOW_CONFIDENCE_STRATEGIC_SEGMENT"
        elif segment_type == "operator_action_class" and segment_value == "ACTION_PUBLISH_NOW" and harmful_rate > effective_rate and evidence_count >= _MIN_SEGMENT_EVIDENCE:
            reason = "SURPRISING_REVERSAL"

        if reason is None:
            continue

        watch_rows.append(
            {
                "segment_type": segment_type,
                "segment_value": segment_value,
                "watch_reason": reason,
                "evidence_row_count": evidence_count,
                "harmful_rate": harmful_rate,
                "effective_rate": effective_rate,
                "signal_class": str(row.get("signal_class", "")),
                "threshold_direction_class": str(row.get("threshold_direction_class", "")),
                "confidence_class": confidence_class,
                "recommended_action": str(row.get("recommended_action", "")),
            }
        )

    watchlist = pd.DataFrame(watch_rows)
    if watchlist.empty:
        return watchlist

    return watchlist.sort_values(
        by=["harmful_rate", "evidence_row_count"],
        ascending=[False, False],
    )


def _validate_policy_calibration_consistency(
    *,
    attribution: pd.DataFrame,
    summary: CommercialPolicyCalibrationSummary,
    by_segment: pd.DataFrame,
    watchlist: pd.DataFrame,
) -> None:
    errors: list[str] = []

    if summary.calibration_readiness_class == CALIBRATION_READY and summary.evidence_row_count == 0:
        errors.append("CALIBRATION_READY cannot be reported when evidence_row_count is zero")

    if (
        summary.calibration_readiness_class == CALIBRATION_NOT_READY
        and summary.threshold_direction_class != NO_THRESHOLD_RECOMMENDATION
    ):
        errors.append("Threshold direction must be NO_THRESHOLD_RECOMMENDATION when readiness is CALIBRATION_NOT_READY")

    ready = attribution[attribution["attribution_status"] == "ATTRIBUTION_READY"]
    expected_effective = int(ready["recommendation_effectiveness_class"].isin(_EFFECTIVE_CLASSES).sum())
    expected_harmful = int(ready["recommendation_effectiveness_class"].isin(_HARMFUL_CLASSES).sum())
    expected_neutral = int((ready["recommendation_effectiveness_class"] == "NEUTRAL").sum())
    expected_inconclusive = int((ready["recommendation_effectiveness_class"] == "INCONCLUSIVE").sum())

    if summary.effective_count != expected_effective:
        errors.append("effective_count does not reconcile to attribution-ready rows")
    if summary.harmful_count != expected_harmful:
        errors.append("harmful_count does not reconcile to attribution-ready rows")
    if summary.neutral_count != expected_neutral:
        errors.append("neutral_count does not reconcile to attribution-ready rows")
    if summary.inconclusive_count != expected_inconclusive:
        errors.append("inconclusive_count does not reconcile to attribution-ready rows")

    if not watchlist.empty:
        source_keys = set(
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
        if not watch_keys.issubset(source_keys):
            errors.append("watchlist contains rows absent from calibration-by-segment source set")

    if summary.policy_signal_class == POLICY_SIGNAL_BLOCKED_DEFECT and summary.threshold_direction_class in {TIGHTEN_PUBLISH_POLICY, LOOSEN_PUBLISH_POLICY}:
        errors.append("Blocked/defect calibration state cannot emit tighten or loosen threshold recommendations")

    if errors:
        raise ValueError("Commercial policy calibration consistency check failed:\n" + "\n".join(errors))


def _normalize_attribution(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    if normalized.empty:
        return pd.DataFrame(
            columns=[
                "attribution_status",
                "recommendation_effectiveness_class",
                "attribution_confidence_class",
                "operator_action_class",
                "publish_eligibility_class",
                "demand_evidence_class",
                "row_change_reason_code",
            ]
        )

    for col in [
        "attribution_status",
        "recommendation_effectiveness_class",
        "attribution_confidence_class",
        "operator_action_class",
        "publish_eligibility_class",
        "demand_evidence_class",
        "row_change_reason_code",
    ]:
        if col not in normalized.columns:
            normalized[col] = None

    normalized["attribution_status"] = normalized["attribution_status"].fillna("unknown").astype(str)
    normalized["recommendation_effectiveness_class"] = normalized["recommendation_effectiveness_class"].fillna("INCONCLUSIVE").astype(str)
    normalized["attribution_confidence_class"] = normalized["attribution_confidence_class"].fillna(CONFIDENCE_NONE).astype(str)
    normalized["operator_action_class"] = normalized["operator_action_class"].fillna("unknown").astype(str)
    normalized["publish_eligibility_class"] = normalized["publish_eligibility_class"].fillna("unknown").astype(str)
    normalized["demand_evidence_class"] = normalized["demand_evidence_class"].fillna("unknown").astype(str)
    normalized["row_change_reason_code"] = normalized["row_change_reason_code"].fillna("unknown").astype(str)
    return normalized


def _confidence_from_evidence(*, evidence_row_count: int, high_conf_share: float) -> str:
    if evidence_row_count == 0:
        return CONFIDENCE_NONE
    if evidence_row_count >= 20 and high_conf_share >= 0.40:
        return CONFIDENCE_HIGH
    if evidence_row_count >= 10 and high_conf_share >= 0.25:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _high_confidence_share(segment: pd.DataFrame) -> float:
    ready = segment[segment["attribution_status"] == "ATTRIBUTION_READY"]
    if ready.empty:
        return 0.0
    high = int((ready["attribution_confidence_class"] == CONFIDENCE_HIGH).sum())
    return high / max(int(len(ready.index)), 1)


def _ratio_or_none(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def _operator_recommendation(*, threshold_direction_class: str, readiness_class: str, blocked_defect: bool) -> str:
    if blocked_defect:
        return "Hold operations for defect triage; calibration recommendations are blocked until defect resolution."
    if readiness_class == CALIBRATION_NOT_READY:
        return "No threshold movement; gather more mature attributed outcomes before acting."
    if threshold_direction_class == TIGHTEN_PUBLISH_POLICY:
        return "Increase review scrutiny for weak segments and reduce automatic publish exposure."
    if threshold_direction_class == LOOSEN_PUBLISH_POLICY:
        return "Prioritize publish-now execution for consistently effective segments with high confidence."
    if threshold_direction_class == INVESTIGATE_SEGMENT:
        return "Investigate mixed segments and route uncertain classes through operator review."
    return "Hold policy thresholds and monitor attribution drift in subsequent cycles."


def _model_owner_recommendation(*, threshold_direction_class: str, readiness_class: str, blocked_defect: bool) -> str:
    if blocked_defect:
        return "Address defect root cause and refresh attribution integrity checks before any calibration action."
    if readiness_class == CALIBRATION_NOT_READY:
        return "Do not change model or thresholds; improve outcome coverage and confidence first."
    if threshold_direction_class == TIGHTEN_PUBLISH_POLICY:
        return "Review feature/policy thresholds for high-harm segments and add stronger gating diagnostics."
    if threshold_direction_class == LOOSEN_PUBLISH_POLICY:
        return "Evaluate safe policy relaxation candidates in high-performing segments via governed review."
    if threshold_direction_class == INVESTIGATE_SEGMENT:
        return "Run segment-level diagnostics to isolate reversal drivers before recommending threshold edits."
    return "Maintain current thresholds and continue evidence collection for next calibration window."


def _segment_value(value: object) -> str:
    if value is None:
        return "null"
    text = str(value).strip()
    return text if text != "" else "null"


def _segment_columns() -> list[str]:
    return [
        "segment_type",
        "segment_value",
        "evidence_row_count",
        "effective_count",
        "harmful_count",
        "neutral_count",
        "inconclusive_count",
        "effective_rate",
        "harmful_rate",
        "signal_class",
        "threshold_direction_class",
        "confidence_class",
        "recommended_action",
    ]


def _nullable_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def _segment_preview_lines(by_segment: pd.DataFrame, threshold_direction_class: str) -> list[str]:
    subset = by_segment[by_segment["threshold_direction_class"] == threshold_direction_class]
    if subset.empty:
        if threshold_direction_class == HOLD_POLICY:
            return ["No hold-policy segments currently flagged."]
        if threshold_direction_class == TIGHTEN_PUBLISH_POLICY:
            return ["No tighten candidates currently flagged."]
        return ["No loosen candidates currently flagged."]

    lines: list[str] = []
    for _, row in subset.head(10).iterrows():
        lines.append(
            f"{row['segment_type']}={row['segment_value']} | evidence={int(row['evidence_row_count'])} | effective_rate={row['effective_rate']} | harmful_rate={row['harmful_rate']}"
        )
    return lines


def _watchlist_preview_lines(watchlist: pd.DataFrame) -> list[str]:
    if watchlist.empty:
        return ["No watchlist segments are currently flagged."]

    lines: list[str] = []
    for _, row in watchlist.head(10).iterrows():
        lines.append(
            f"{row['segment_type']}={row['segment_value']} | reason={row['watch_reason']} | evidence={int(row['evidence_row_count'])} | harmful_rate={row['harmful_rate']}"
        )
    return lines
