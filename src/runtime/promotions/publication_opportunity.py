from __future__ import annotations

"""Publication opportunity classification and reconciliation seams for promotions runtime."""

from dataclasses import asdict, dataclass
from typing import Optional

# Publication opportunity classification constants
PUBLICATION_OPPORTUNITY_FRESH = "FRESH_PUBLICATION_OPPORTUNITY_PRESENT"
PUBLICATION_OPPORTUNITY_DUPLICATE_ONLY = "NO_FRESH_PUBLICATION_OPPORTUNITY_DUPLICATE_ONLY"
PUBLICATION_OPPORTUNITY_LEGITIMATE_ZERO = "NO_FRESH_PUBLICATION_OPPORTUNITY_LEGITIMATE_ZERO"
PUBLICATION_OPPORTUNITY_REVIEW_ONLY = "NO_FRESH_PUBLICATION_OPPORTUNITY_REVIEW_ONLY"
PUBLICATION_OPPORTUNITY_FILTERED_OUT = "NO_FRESH_PUBLICATION_OPPORTUNITY_FILTERED_OUT"
PUBLICATION_OPPORTUNITY_BLOCKED_BY_DEFECT = "PUBLICATION_OPPORTUNITY_BLOCKED_BY_DEFECT"

# Commercial freshness classification constants
FRESHNESS_FRESH_NEW_PUBLICATIONS_CREATED = "FRESH_NEW_PUBLICATIONS_CREATED"
FRESHNESS_NO_NEW_PUBLICATIONS_DUPLICATE_ONLY = "NO_NEW_PUBLICATIONS_DUPLICATE_ONLY"
FRESHNESS_NO_NEW_PUBLICATIONS_REVIEW_ONLY = "NO_NEW_PUBLICATIONS_REVIEW_ONLY"
FRESHNESS_NO_NEW_PUBLICATIONS_LEGITIMATE_ZERO = "NO_NEW_PUBLICATIONS_LEGITIMATE_ZERO"
FRESHNESS_NO_NEW_PUBLICATIONS_FILTERED_OUT = "NO_NEW_PUBLICATIONS_FILTERED_OUT"
FRESHNESS_BLOCKED_BY_DEFECT = "BLOCKED_BY_DEFECT"

# Replay safety classification constants
REPLAY_SAFETY_SAFE_NEW_DATA_REQUIRED = "SAFE_NEW_DATA_REQUIRED"
REPLAY_SAFETY_SAFE_RERUN_EXPECTED_NO_CHANGE = "SAFE_RERUN_EXPECTED_NO_CHANGE"
REPLAY_SAFETY_SAFE_REVIEW_OR_INPUT_CHANGE_NEEDED = "SAFE_REVIEW_OR_INPUT_CHANGE_NEEDED"
REPLAY_SAFETY_UNSAFE_BLOCKED_BY_DEFECT = "UNSAFE_BLOCKED_BY_DEFECT"


@dataclass(frozen=True)
class PublicationOpportunityInput:
    """Normalized Stage 11/12 inputs for publication opportunity classification."""

    stage11_total_rows: int
    stage11_order_rows: int
    stage11_review_rows: int
    stage11_true_zero_rows: int
    stage11_cold_start_rows: int
    stage11_low_nonzero_rows: int
    stage11_healthy_nonzero_rows: int
    stage11_artificial_collapse_rows: int
    stage12_publish_status: str
    stage12_publish_status_reason: str
    stage12_candidate_row_count: int
    stage12_publishable_row_count: int
    stage12_review_only_row_count: int
    stage12_legitimate_excluded_row_count: int
    stage12_defect_excluded_row_count: int
    stage12_duplicate_registry_skip_count: int


@dataclass(frozen=True)
class PublicationOpportunityClassification:
    """Authoritative publication opportunity classification for the cycle."""

    publication_opportunity_class: str
    publication_opportunity_reason: str
    publication_opportunity_message: str
    fresh_publication_candidate_count: int
    duplicate_only_noop_flag: bool
    review_only_cycle_flag: bool
    legitimate_zero_cycle_flag: bool
    filtered_out_cycle_flag: bool
    blocked_by_defect_flag: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialFreshnessClassification:
    """Authoritative commercial freshness classification for the cycle."""

    freshness_class: str
    freshness_reason: str
    freshness_message: str
    commercially_new_value_created_flag: bool
    operator_next_action: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialReplaySafetySummary:
    """Replay safety assessment for the cycle."""

    replay_safety_class: str
    replay_safety_reason: str
    exact_rerun_expected_outcome: str
    operator_guidance_message: str
    safe_to_rerun_without_input_change_flag: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PublicationFreshnessDiagnostic:
    """Comprehensive publication freshness diagnostic artifact."""

    freshness_class: str
    freshness_reason: str
    commercially_new_value_created_flag: bool
    duplicate_registry_skip_count: int
    newly_published_row_count: int
    review_only_row_count: int
    legitimate_zero_row_count: int
    filtered_out_row_count: int
    defect_blocked_row_count: int
    first_publication_date_if_any: Optional[str]
    last_publication_date_if_any: Optional[str]
    replay_safety_status: str
    replay_safety_reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PublishReconciliationSummary:
    """Reconciliation summary for Stage 11 → Stage 12 flow."""

    stage11_total_rows: int
    stage11_order_rows: int
    stage11_review_rows: int
    stage11_true_zero_rows: int
    stage11_cold_start_rows: int
    stage11_low_nonzero_rows: int
    stage11_healthy_nonzero_rows: int
    stage11_artificial_collapse_rows: int
    stage12_candidate_row_count: int
    stage12_publishable_row_count: int
    stage12_review_only_row_count: int
    stage12_legitimate_excluded_row_count: int
    stage12_defect_excluded_row_count: int
    stage12_duplicate_registry_skip_count: int
    stage12_new_publication_row_count: int
    reconciled_flag: bool
    reconciliation_message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialStageTiming:
    """Execution timing summary for commercial stages."""

    run_id: str
    stage6_elapsed_seconds: float
    stage8_elapsed_seconds: float
    stage11_elapsed_seconds: float
    stage12_elapsed_seconds: float
    stage13_elapsed_seconds: float
    longest_commercial_stage: str
    longest_commercial_stage_elapsed_seconds: float
    operator_guidance_message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DuplicateRegistrySkipSummary:
    """Diagnostic summary for duplicate registry skip events."""

    skipped_row_count: int
    unique_store_count: int
    unique_promotion_count: int
    unique_sku_count: int
    first_seen_publication_date_min: Optional[str]
    first_seen_publication_date_max: Optional[str]
    all_rows_previously_published_flag: bool
    recommended_next_action: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_publication_opportunity(payload: PublicationOpportunityInput) -> PublicationOpportunityClassification:
    """
    Classify the cycle's publication opportunity into one authoritative category.

    Returns exactly one of:
    - FRESH_PUBLICATION_OPPORTUNITY_PRESENT
    - NO_FRESH_PUBLICATION_OPPORTUNITY_DUPLICATE_ONLY
    - NO_FRESH_PUBLICATION_OPPORTUNITY_LEGITIMATE_ZERO
    - NO_FRESH_PUBLICATION_OPPORTUNITY_REVIEW_ONLY
    - NO_FRESH_PUBLICATION_OPPORTUNITY_FILTERED_OUT
    - PUBLICATION_OPPORTUNITY_BLOCKED_BY_DEFECT
    """
    # Defect path: Stage 12 publication failed or was blocked
    if payload.stage12_publish_status in {"FAIL", "FAIL_NO_ELIGIBLE_ROWS"}:
        return PublicationOpportunityClassification(
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_BLOCKED_BY_DEFECT,
            publication_opportunity_reason=payload.stage12_publish_status_reason or "stage12_defect",
            publication_opportunity_message=(
                "Commercial cycle was blocked by Stage 12 publication defect. "
                "Requires defect remediation before next cycle."
            ),
            fresh_publication_candidate_count=0,
            duplicate_only_noop_flag=False,
            review_only_cycle_flag=False,
            legitimate_zero_cycle_flag=False,
            filtered_out_cycle_flag=False,
            blocked_by_defect_flag=True,
        )

    # Fresh publication path: Stage 12 published new rows successfully
    if payload.stage12_publish_status in {"PASS", "PASS_WITH_EXCLUSIONS"} and payload.stage12_publishable_row_count > 0:
        return PublicationOpportunityClassification(
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_FRESH,
            publication_opportunity_reason=payload.stage12_publish_status_reason or "fresh_publications_written",
            publication_opportunity_message=(
                f"Commercial cycle succeeded with {payload.stage12_publishable_row_count} fresh publication(s)."
            ),
            fresh_publication_candidate_count=payload.stage12_publishable_row_count,
            duplicate_only_noop_flag=False,
            review_only_cycle_flag=False,
            legitimate_zero_cycle_flag=False,
            filtered_out_cycle_flag=False,
            blocked_by_defect_flag=False,
        )

    # NOOP paths: Stage 12 completed without new publications
    if payload.stage12_publish_status == "NOOP_ALREADY_PUBLISHED":
        return PublicationOpportunityClassification(
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_DUPLICATE_ONLY,
            publication_opportunity_reason=payload.stage12_publish_status_reason or "all_candidates_already_published",
            publication_opportunity_message=(
                f"Commercial cycle completed with governed NOOP because all {payload.stage12_candidate_row_count} "
                "candidates were already published in prior cycles. No fresh publication opportunity."
            ),
            fresh_publication_candidate_count=0,
            duplicate_only_noop_flag=True,
            review_only_cycle_flag=False,
            legitimate_zero_cycle_flag=False,
            filtered_out_cycle_flag=False,
            blocked_by_defect_flag=False,
        )

    # Legitimate zero rows (all rows are true-zero demand or similar)
    if (
        payload.stage12_publish_status == "NOOP_VALID_NO_PUBLISHABLE_ROWS"
        and payload.stage11_true_zero_rows > 0
        and payload.stage12_legitimate_excluded_row_count > 0
        and payload.stage12_defect_excluded_row_count == 0
    ):
        return PublicationOpportunityClassification(
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_LEGITIMATE_ZERO,
            publication_opportunity_reason=payload.stage12_publish_status_reason or "no_publishable_rows_legitimate",
            publication_opportunity_message=(
                f"Commercial cycle completed with governed NOOP. "
                f"{payload.stage11_true_zero_rows} row(s) have true-zero demand; "
                f"{payload.stage12_legitimate_excluded_row_count} row(s) excluded by policy. "
                "No fresh publication opportunity in this cycle."
            ),
            fresh_publication_candidate_count=0,
            duplicate_only_noop_flag=False,
            review_only_cycle_flag=False,
            legitimate_zero_cycle_flag=True,
            filtered_out_cycle_flag=False,
            blocked_by_defect_flag=False,
        )

    # Review-only cycle: rows exist but all are review-gated
    if (
        payload.stage12_publish_status == "NOOP_VALID_NO_PUBLISHABLE_ROWS"
        and payload.stage12_review_only_row_count > 0
        and payload.stage12_publishable_row_count == 0
    ):
        return PublicationOpportunityClassification(
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_REVIEW_ONLY,
            publication_opportunity_reason=payload.stage12_publish_status_reason or "review_only_rows",
            publication_opportunity_message=(
                f"Commercial cycle completed with governed NOOP. "
                f"{payload.stage12_review_only_row_count} row(s) passed eligibility but are held for review. "
                "No automated publication opportunity; awaiting manual review."
            ),
            fresh_publication_candidate_count=0,
            duplicate_only_noop_flag=False,
            review_only_cycle_flag=True,
            legitimate_zero_cycle_flag=False,
            filtered_out_cycle_flag=False,
            blocked_by_defect_flag=False,
        )

    # Filtered out: candidates existed but were removed by policy gates
    if (
        payload.stage12_publish_status == "NOOP_VALID_NO_PUBLISHABLE_ROWS"
        and payload.stage12_candidate_row_count > 0
        and payload.stage12_legitimate_excluded_row_count > 0
    ):
        return PublicationOpportunityClassification(
            publication_opportunity_class=PUBLICATION_OPPORTUNITY_FILTERED_OUT,
            publication_opportunity_reason=payload.stage12_publish_status_reason or "filtered_out_by_policy",
            publication_opportunity_message=(
                f"Commercial cycle completed with governed NOOP. "
                f"{payload.stage12_candidate_row_count} candidate(s) were filtered out by publication policy. "
                "Commercially interesting rows exist but do not meet current business gates."
            ),
            fresh_publication_candidate_count=payload.stage12_candidate_row_count,
            duplicate_only_noop_flag=False,
            review_only_cycle_flag=False,
            legitimate_zero_cycle_flag=False,
            filtered_out_cycle_flag=True,
            blocked_by_defect_flag=False,
        )

    # Fallback: legitimate zero if no other path matched
    return PublicationOpportunityClassification(
        publication_opportunity_class=PUBLICATION_OPPORTUNITY_LEGITIMATE_ZERO,
        publication_opportunity_reason="unclassified_noop",
        publication_opportunity_message=(
            "Commercial cycle completed with governed NOOP. No fresh publication opportunity identified."
        ),
        fresh_publication_candidate_count=0,
        duplicate_only_noop_flag=False,
        review_only_cycle_flag=False,
        legitimate_zero_cycle_flag=True,
        filtered_out_cycle_flag=False,
        blocked_by_defect_flag=False,
    )


def build_publish_reconciliation_summary(payload: PublicationOpportunityInput) -> PublishReconciliationSummary:
    """
    Build a reconciliation summary for Stage 11 → Stage 12 flow.

    Verifies that counts reconcile exactly. Raises ValueError if reconciliation fails.
    """
    # Stage 11 demand evidence classifications should sum to total rows.
    # Stage 11 action rows and Stage 12 publishability rows are separate
    # dimensions; do not hide a final review-only hold inside a generic
    # "demand-classified" bucket.
    stage11_demand_classes_sum = (
        payload.stage11_true_zero_rows
        + payload.stage11_cold_start_rows
        + payload.stage11_low_nonzero_rows
        + payload.stage11_healthy_nonzero_rows
        + payload.stage11_artificial_collapse_rows
    )
    stage12_publishability_sum = (
        payload.stage12_publishable_row_count
        + payload.stage12_review_only_row_count
        + payload.stage12_legitimate_excluded_row_count
        + payload.stage12_defect_excluded_row_count
        + payload.stage12_duplicate_registry_skip_count
    )
    failures: list[str] = []
    if stage11_demand_classes_sum != payload.stage11_total_rows:
        failures.append(
            f"Stage 11 demand classes sum to {stage11_demand_classes_sum} but stage11_total_rows is {payload.stage11_total_rows}"
        )
    if payload.stage11_order_rows + payload.stage11_review_rows > payload.stage11_total_rows:
        failures.append(
            "Stage 11 action counts exceed total rows: "
            f"order={payload.stage11_order_rows}, review={payload.stage11_review_rows}, total={payload.stage11_total_rows}"
        )
    if stage12_publishability_sum != payload.stage12_candidate_row_count:
        failures.append(
            f"Stage 12 publishability classes sum to {stage12_publishability_sum} but stage12_candidate_row_count is {payload.stage12_candidate_row_count}"
        )

    if failures:
        raise ValueError("Reconciliation FAILED: " + "; ".join(failures))

    stage11_order_held_for_review_count = max(
        int(payload.stage11_order_rows)
        - int(payload.stage12_publishable_row_count)
        - int(payload.stage12_duplicate_registry_skip_count),
        0,
    )
    semantic_review_hold = (
        stage11_order_held_for_review_count > 0
        and payload.stage12_review_only_row_count > 0
        and payload.stage12_publishable_row_count == 0
    )
    reconciled_flag = not semantic_review_hold
    if reconciled_flag:
        reconciliation_message = (
            f"Stage 11→12 flow reconciled: {payload.stage11_total_rows} total, "
            f"{payload.stage11_order_rows} Stage 11 order, {payload.stage11_review_rows} Stage 11 review, "
            f"{stage11_demand_classes_sum} demand-classified, "
            f"{payload.stage12_publishable_row_count} Stage 12 publishable, "
            f"{payload.stage12_review_only_row_count} Stage 12 review-only."
        )
    else:
        reconciliation_message = (
            "Stage 11→12 flow NOT auto-publish reconciled: "
            f"{stage11_order_held_for_review_count} Stage 11 order row(s) are held by Stage 12 review-only gates; "
            f"Stage 12 publishable rows={payload.stage12_publishable_row_count}, "
            f"Stage 12 review-only rows={payload.stage12_review_only_row_count}."
        )

    return PublishReconciliationSummary(
        stage11_total_rows=payload.stage11_total_rows,
        stage11_order_rows=payload.stage11_order_rows,
        stage11_review_rows=payload.stage11_review_rows,
        stage11_true_zero_rows=payload.stage11_true_zero_rows,
        stage11_cold_start_rows=payload.stage11_cold_start_rows,
        stage11_low_nonzero_rows=payload.stage11_low_nonzero_rows,
        stage11_healthy_nonzero_rows=payload.stage11_healthy_nonzero_rows,
        stage11_artificial_collapse_rows=payload.stage11_artificial_collapse_rows,
        stage12_candidate_row_count=payload.stage12_candidate_row_count,
        stage12_publishable_row_count=payload.stage12_publishable_row_count,
        stage12_review_only_row_count=payload.stage12_review_only_row_count,
        stage12_legitimate_excluded_row_count=payload.stage12_legitimate_excluded_row_count,
        stage12_defect_excluded_row_count=payload.stage12_defect_excluded_row_count,
        stage12_duplicate_registry_skip_count=payload.stage12_duplicate_registry_skip_count,
        stage12_new_publication_row_count=payload.stage12_publishable_row_count,
        reconciled_flag=reconciled_flag,
        reconciliation_message=reconciliation_message,
    )


def build_commercial_stage_timing(
    *,
    run_id: str,
    stage6_elapsed_seconds: float,
    stage8_elapsed_seconds: float,
    stage11_elapsed_seconds: float,
    stage12_elapsed_seconds: float,
    stage13_elapsed_seconds: float,
) -> CommercialStageTiming:
    """Build a simple execution timing summary for commercial stages."""
    stages = {
        "Stage 6": stage6_elapsed_seconds,
        "Stage 8": stage8_elapsed_seconds,
        "Stage 11": stage11_elapsed_seconds,
        "Stage 12": stage12_elapsed_seconds,
        "Stage 13": stage13_elapsed_seconds,
    }

    longest_stage = max(stages.items(), key=lambda x: x[1])
    longest_stage_name = longest_stage[0]
    longest_stage_time = longest_stage[1]

    total_commercial_time = sum(stages.values())
    if total_commercial_time > 300:  # 5+ minutes
        guidance = (
            f"Long commercial run detected ({total_commercial_time:.1f}s total). "
            f"{longest_stage_name} took {longest_stage_time:.1f}s ({longest_stage_time/total_commercial_time*100:.1f}% of cycle). "
            "Monitor Stage 6 SQL extraction and Stage 8 decision-surface build for live proof cycles."
        )
    elif longest_stage_time > 120:  # Single stage > 2min
        guidance = (
            f"{longest_stage_name} is the commercial bottleneck ({longest_stage_time:.1f}s). "
            "Investigate query optimization or input scale for next cycle."
        )
    else:
        guidance = "Commercial stages completed within healthy timing windows."

    return CommercialStageTiming(
        run_id=run_id,
        stage6_elapsed_seconds=stage6_elapsed_seconds,
        stage8_elapsed_seconds=stage8_elapsed_seconds,
        stage11_elapsed_seconds=stage11_elapsed_seconds,
        stage12_elapsed_seconds=stage12_elapsed_seconds,
        stage13_elapsed_seconds=stage13_elapsed_seconds,
        longest_commercial_stage=longest_stage_name,
        longest_commercial_stage_elapsed_seconds=longest_stage_time,
        operator_guidance_message=guidance,
    )


def build_duplicate_registry_skip_summary(
    *,
    skipped_row_count: int,
    unique_store_count: int,
    unique_promotion_count: int,
    unique_sku_count: int,
    first_seen_publication_date_min: Optional[str] = None,
    first_seen_publication_date_max: Optional[str] = None,
) -> DuplicateRegistrySkipSummary:
    """Build diagnostic summary for duplicate registry skip events."""
    all_previously_published = skipped_row_count > 0
    recommended_action = (
        "All candidates were already published in prior cycles. "
        "Next commercial opportunity requires new candidates from fresh promotions or store contexts."
    )

    return DuplicateRegistrySkipSummary(
        skipped_row_count=skipped_row_count,
        unique_store_count=unique_store_count,
        unique_promotion_count=unique_promotion_count,
        unique_sku_count=unique_sku_count,
        first_seen_publication_date_min=first_seen_publication_date_min,
        first_seen_publication_date_max=first_seen_publication_date_max,
        all_rows_previously_published_flag=all_previously_published,
        recommended_next_action=recommended_action,
    )


def build_commercial_operator_brief(
    *,
    run_id: str,
    as_of_date: str,
    commercial_outcome_class: str,
    commercial_outcome_message: str,
    publication_opportunity_class: str,
    publication_opportunity_message: str,
    stage12_publish_status: str,
    stage12_publish_status_reason: str,
    stage13_skip_class: str,
    stage11_total_rows: int,
    stage12_candidate_row_count: int,
    stage12_publishable_row_count: int,
    stage12_duplicate_registry_skip_count: int,
    freshness_class: str = "",
    freshness_reason: str = "",
    freshness_message: str = "",
    commercially_new_value_created_flag: bool = False,
    replay_safety_class: str = "",
    replay_safety_reason: str = "",
    exact_rerun_expected_outcome: str = "",
    operator_guidance_message_replay: str = "",
    delta_class: str = "",
    delta_reason: str = "",
    delta_message: str = "",
    comparable_prior_cycle_found_flag: bool = False,
    comparable_prior_cycle_run_id: Optional[str] = None,
    materiality_class: str = "",
    materiality_reason: str = "",
    materially_changed_flag: bool = False,
    operator_attention_recommended_flag: bool = False,
    changed_store_count: Optional[int] = None,
    changed_promotion_count: Optional[int] = None,
    changed_store_sku_count: Optional[int] = None,
    action_publish_now_count: int = 0,
    action_review_now_count: int = 0,
    action_monitor_count: int = 0,
    action_no_action_duplicate_count: int = 0,
    action_no_action_true_zero_count: int = 0,
    action_investigate_defect_count: int = 0,
    top_operator_action_class: str = "NONE",
    top_operator_priority_band: str = "NONE",
    priority_queue_preview_lines: Optional[list[str]] = None,
    attribution_ready_count: int = 0,
    attribution_not_yet_mature_count: int = 0,
    blocked_missing_outcome_data_count: int = 0,
    effective_strong_count: int = 0,
    effective_moderate_count: int = 0,
    neutral_count: int = 0,
    ineffective_count: int = 0,
    harmful_count: int = 0,
    inconclusive_count: int = 0,
    average_effectiveness_score: Optional[float] = None,
    publish_now_average_effectiveness_score: Optional[float] = None,
    review_now_average_effectiveness_score: Optional[float] = None,
    commercial_learning_signal_strength_class: str = "LEARNING_SIGNAL_NOT_READY",
    learning_priority_preview_lines: Optional[list[str]] = None,
    policy_signal_class: str = "POLICY_SIGNAL_INCONCLUSIVE",
    calibration_readiness_class: str = "CALIBRATION_NOT_READY",
    threshold_direction_class: str = "NO_THRESHOLD_RECOMMENDATION",
    commercial_policy_confidence_class: str = "NONE",
    policy_tighten_preview_lines: Optional[list[str]] = None,
    policy_loosen_preview_lines: Optional[list[str]] = None,
    policy_hold_preview_lines: Optional[list[str]] = None,
    policy_watchlist_preview_lines: Optional[list[str]] = None,
    simulation_readiness_class: str = "SIMULATION_NOT_COMPARABLE",
    simulated_policy_direction_class: str = "SIMULATED_INCONCLUSIVE",
    simulated_materiality_class: Optional[str] = None,
    simulated_risk_class: Optional[str] = None,
    baseline_publish_row_count: int = 0,
    simulated_publish_row_count: int = 0,
    net_publish_delta: int = 0,
    baseline_review_row_count: int = 0,
    simulated_review_row_count: int = 0,
    net_review_delta: int = 0,
    baseline_excluded_row_count: int = 0,
    simulated_excluded_row_count: int = 0,
    net_excluded_delta: int = 0,
    simulated_affected_row_count: int = 0,
    simulated_affected_store_count: int = 0,
    simulated_affected_promotion_count: int = 0,
    simulation_winners_preview_lines: Optional[list[str]] = None,
    simulation_risks_preview_lines: Optional[list[str]] = None,
    simulation_watchlist_preview_lines: Optional[list[str]] = None,
    action_instruction_readiness_class: str = "ACTION_PACK_NOT_COMPARABLE",
    action_instruction_readiness_reason: str = "Action instruction pack not available.",
    immediate_priorities_preview_lines: Optional[list[str]] = None,
    top_operator_action_preview_lines: Optional[list[str]] = None,
    top_model_owner_action_preview_lines: Optional[list[str]] = None,
    action_queue_preview_lines: Optional[list[str]] = None,
) -> str:
    """
    Build a short, executive-friendly markdown brief for the commercial run.

    Returns markdown text suitable for management review and operator guidance.
    Now includes Freshness and Replay Safety sections.
    """
    publication_opportunity_class_short = publication_opportunity_class.replace(
        "NO_FRESH_PUBLICATION_OPPORTUNITY_", ""
    ).replace("FRESH_PUBLICATION_OPPORTUNITY_", "").replace("PUBLICATION_OPPORTUNITY_", "")

    freshness_flag_emoji = "✅" if commercially_new_value_created_flag else "⚠️"

    brief = f"""# Commercial Operator Brief

**Run ID**: {run_id}  
**As Of Date**: {as_of_date}

## Commercial Outcome

**Status**: {commercial_outcome_class}

{commercial_outcome_message}

## Publication Opportunity

**Opportunity Class**: {publication_opportunity_class_short}

{publication_opportunity_message}

## Freshness

**Status**: {freshness_flag_emoji} {freshness_class.replace('_', ' ')}

{freshness_message}

**New Commercial Value Created**: {commercially_new_value_created_flag}

## Replay Safety

**Status**: {replay_safety_class.replace('_', ' ')}

**Expected Outcome on Exact Rerun**:

{exact_rerun_expected_outcome}

{operator_guidance_message_replay}

## Delta vs Prior Cycle

**Comparable Prior Found**: {comparable_prior_cycle_found_flag}

**Prior Cycle Run ID**: {comparable_prior_cycle_run_id or "None (first baseline)"}

**Delta Class**: {delta_class}

{delta_message}

## Materiality

- **Materiality Class**: {materiality_class}
- **Materiality Reason**: {materiality_reason}
- **Materially Changed**: {materially_changed_flag}
- **Operator Attention Recommended**: {operator_attention_recommended_flag}

## Top Commercial Changes

- **Changed Stores**: {changed_store_count if changed_store_count is not None else "N/A"}
- **Changed Promotions**: {changed_promotion_count if changed_promotion_count is not None else "N/A"}
- **Changed Store-SKU Rows**: {changed_store_sku_count if changed_store_sku_count is not None else "N/A"}

## Why Rows Changed

- **Delta Reason**: {delta_reason}
- **Most Common Drivers**: recommendation changes, eligibility shifts, demand-evidence shifts, and order-unit swings (see reason codes in commercial_change_explanations.csv)

## Immediate Operator Actions

- **Publish Now**: {action_publish_now_count}
- **Review Now**: {action_review_now_count}
- **Monitor**: {action_monitor_count}
- **No Action (Duplicate)**: {action_no_action_duplicate_count}
- **No Action (True Zero)**: {action_no_action_true_zero_count}
- **Investigate Defect**: {action_investigate_defect_count}

## Priority Queue

- **Top Action Class**: {top_operator_action_class}
- **Top Priority Band**: {top_operator_priority_band}
{chr(10).join([f"- {line}" for line in (priority_queue_preview_lines or ["No high-priority rows queued."])])}

## Outcome Attribution

- **Attribution Ready Rows**: {attribution_ready_count}
- **Attribution Not Yet Mature**: {attribution_not_yet_mature_count}
- **Blocked Missing Outcome Data**: {blocked_missing_outcome_data_count}
- **Learning Signal Strength**: {commercial_learning_signal_strength_class}

## What Worked

- **Effective Strong**: {effective_strong_count}
- **Effective Moderate**: {effective_moderate_count}
- **Publish-Now Average Effectiveness Score**: {publish_now_average_effectiveness_score if publish_now_average_effectiveness_score is not None else "N/A"}

## What Failed

- **Ineffective**: {ineffective_count}
- **Harmful**: {harmful_count}
- **Review-Now Average Effectiveness Score**: {review_now_average_effectiveness_score if review_now_average_effectiveness_score is not None else "N/A"}

## What to Learn Next

- **Neutral**: {neutral_count}
- **Inconclusive**: {inconclusive_count}
- **Overall Average Effectiveness Score**: {average_effectiveness_score if average_effectiveness_score is not None else "N/A"}
{chr(10).join([f"- {line}" for line in (learning_priority_preview_lines or ["No high-confidence learning rows queued."])])}

## Policy Calibration

- **Policy Signal Class**: {policy_signal_class}
- **Calibration Readiness Class**: {calibration_readiness_class}
- **Threshold Direction Class**: {threshold_direction_class}
- **Policy Confidence Class**: {commercial_policy_confidence_class}

## What to tighten

{chr(10).join([f"- {line}" for line in (policy_tighten_preview_lines or ["No tighten recommendations currently flagged."])])}

## What to loosen

{chr(10).join([f"- {line}" for line in (policy_loosen_preview_lines or ["No loosen recommendations currently flagged."])])}

## What to leave unchanged

{chr(10).join([f"- {line}" for line in (policy_hold_preview_lines or ["No explicit hold recommendations currently flagged."])])}

## Watchlist

{chr(10).join([f"- {line}" for line in (policy_watchlist_preview_lines or ["No policy watchlist segments currently flagged."])])}

## Policy Simulation

- **Simulation Readiness Class**: {simulation_readiness_class}
- **Simulated Policy Direction Class**: {simulated_policy_direction_class}
- **Simulated Materiality Class**: {simulated_materiality_class if simulated_materiality_class is not None else "N/A"}
- **Simulated Risk Class**: {simulated_risk_class if simulated_risk_class is not None else "N/A"}

## Baseline vs Simulated Outcome

- **Baseline Publish Rows**: {baseline_publish_row_count}
- **Simulated Publish Rows**: {simulated_publish_row_count}
- **Net Publish Delta**: {net_publish_delta}
- **Baseline Review Rows**: {baseline_review_row_count}
- **Simulated Review Rows**: {simulated_review_row_count}
- **Net Review Delta**: {net_review_delta}
- **Baseline Excluded Rows**: {baseline_excluded_row_count}
- **Simulated Excluded Rows**: {simulated_excluded_row_count}
- **Net Excluded Delta**: {net_excluded_delta}
- **Affected Rows**: {simulated_affected_row_count}
- **Affected Stores**: {simulated_affected_store_count}
- **Affected Promotions**: {simulated_affected_promotion_count}

## Biggest Winners

{chr(10).join([f"- {line}" for line in (simulation_winners_preview_lines or ["No winners identified in current simulation."])])}

## Biggest Risks

{chr(10).join([f"- {line}" for line in (simulation_risks_preview_lines or ["No major risks identified in current simulation."])])}

## Simulation Watchlist

{chr(10).join([f"- {line}" for line in (simulation_watchlist_preview_lines or ["No simulation watchlist segments currently flagged."])])}

## Action Instructions

- **Readiness Class**: {action_instruction_readiness_class}
- **Readiness Reason**: {action_instruction_readiness_reason}

### Immediate Priorities

{chr(10).join([f"- {line}" for line in (immediate_priorities_preview_lines or ["No immediate action priorities currently flagged."])])}

### Top Operator Actions

{chr(10).join([f"- {line}" for line in (top_operator_action_preview_lines or ["No operator action rows currently flagged."])])}

### Top Model Owner Actions

{chr(10).join([f"- {line}" for line in (top_model_owner_action_preview_lines or ["No model-owner action rows currently flagged."])])}

### Action Queue Preview

{chr(10).join([f"- {line}" for line in (action_queue_preview_lines or ["No action queue rows currently flagged."])])}

## Publish Result

- **Status**: {stage12_publish_status} ({stage12_publish_status_reason})
- **Candidates Processed**: {stage12_candidate_row_count}
- **New Publications**: {stage12_publishable_row_count}
- **Duplicate Registry Skips**: {stage12_duplicate_registry_skip_count}

## Validation Result

- **Skip Classification**: {stage13_skip_class.replace('STAGE12_', '').replace('VALIDATION_', '')}
- **Validation Executed**: {"Yes" if stage13_skip_class == "VALIDATION_EXECUTED" else "No (governed NOOP)"}

## Key Counts

- **Stage 11 Total Rows**: {stage11_total_rows}
- **Stage 12 Candidate Rows**: {stage12_candidate_row_count}
- **Stage 12 Publishable Rows**: {stage12_publishable_row_count}
- **Duplicate Skips**: {stage12_duplicate_registry_skip_count}

## Recommended Next Action

{_get_operator_guidance_message(
    commercial_outcome_class=commercial_outcome_class,
    publication_opportunity_class=publication_opportunity_class,
    stage12_publish_status=stage12_publish_status,
    stage12_publishable_row_count=stage12_publishable_row_count,
)}

---
*Generated from governed runtime diagnostics. Use alongside commercial_run_outcome_summary.json, publish_reconciliation_summary.json, and publication_freshness_diagnostic.json for full operational context.*
"""
    return brief


def classify_commercial_freshness(
    publication_opportunity_class: str,
    newly_published_row_count: int,
    duplicate_registry_skip_count: int,
    review_only_row_count: int,
    legitimate_zero_row_count: int,
    filtered_out_row_count: int,
    defect_blocked_row_count: int,
    validation_status: str,
) -> CommercialFreshnessClassification:
    """
    Classify the commercial freshness of the run into one authoritative category.

    Returns exactly one of:
    - FRESH_NEW_PUBLICATIONS_CREATED
    - NO_NEW_PUBLICATIONS_DUPLICATE_ONLY
    - NO_NEW_PUBLICATIONS_REVIEW_ONLY
    - NO_NEW_PUBLICATIONS_LEGITIMATE_ZERO
    - NO_NEW_PUBLICATIONS_FILTERED_OUT
    - BLOCKED_BY_DEFECT

    This classifier uses actual runtime facts only from Stage 12 publish outcomes
    and Stage 13 validation results.
    """
    # Defect path: commercial run is blocked by defect
    if defect_blocked_row_count > 0 or "FAIL" in validation_status:
        return CommercialFreshnessClassification(
            freshness_class=FRESHNESS_BLOCKED_BY_DEFECT,
            freshness_reason="defect_blocked",
            freshness_message=(
                "Commercial cycle is blocked by defect. "
                "No commercial freshness; requires remediation before next cycle."
            ),
            commercially_new_value_created_flag=False,
            operator_next_action=(
                "Inspect logs for defect root cause, fix, and rerun. "
                "Contact platform team if blocker persists."
            ),
        )

    # Fresh path: new publications were created
    if newly_published_row_count > 0:
        return CommercialFreshnessClassification(
            freshness_class=FRESHNESS_FRESH_NEW_PUBLICATIONS_CREATED,
            freshness_reason="fresh_publications_written",
            freshness_message=(
                f"Commercial cycle created {newly_published_row_count} new publication(s). "
                "Fresh commercial value delivered."
            ),
            commercially_new_value_created_flag=True,
            operator_next_action=(
                f"✅ **{newly_published_row_count} fresh publication(s) ready**. "
                "Verify client execution and monitor store delivery within scheduled window."
            ),
        )

    # NOOP paths: no new publications. Prior publication evidence must not
    # hide fresh post-registry rows that are held by review or policy.
    if review_only_row_count > 0 and newly_published_row_count == 0:
        duplicate_context = (
            f" {duplicate_registry_skip_count} row(s) were also skipped as prior publications."
            if duplicate_registry_skip_count > 0
            else ""
        )
        return CommercialFreshnessClassification(
            freshness_class=FRESHNESS_NO_NEW_PUBLICATIONS_REVIEW_ONLY,
            freshness_reason="review_only_rows",
            freshness_message=(
                f"{review_only_row_count} commercially interesting row(s) are held for manual review. "
                "No automated publication; awaiting escalation."
                f"{duplicate_context}"
            ),
            commercially_new_value_created_flag=False,
            operator_next_action=(
                f"Rows are commercially interesting but held for manual review. "
                f"Escalate {review_only_row_count} row(s) to commercial team for approval."
            ),
        )

    if legitimate_zero_row_count > 0 and newly_published_row_count == 0:
        return CommercialFreshnessClassification(
            freshness_class=FRESHNESS_NO_NEW_PUBLICATIONS_LEGITIMATE_ZERO,
            freshness_reason="no_publishable_rows_legitimate",
            freshness_message=(
                f"{legitimate_zero_row_count} row(s) have true-zero demand or other legitimate exclusion. "
                "No fresh commercial value in this cycle."
            ),
            commercially_new_value_created_flag=False,
            operator_next_action=(
                "No fresh publication opportunity (true-zero demand or legitimate exclusions). "
                "Re-run next cycle when fresh candidates expected."
            ),
        )

    if filtered_out_row_count > 0 and newly_published_row_count == 0:
        return CommercialFreshnessClassification(
            freshness_class=FRESHNESS_NO_NEW_PUBLICATIONS_FILTERED_OUT,
            freshness_reason="filtered_out_by_policy",
            freshness_message=(
                f"{filtered_out_row_count} commercially interesting row(s) were filtered out by "
                "publication policy gates. No fresh commercial value in this cycle."
            ),
            commercially_new_value_created_flag=False,
            operator_next_action=(
                "Candidates exist but filtered by policy. "
                "Review publication_noop_diagnostics.json for gate-by-gate breakdown and thresholds."
            ),
        )

    if (
        publication_opportunity_class == PUBLICATION_OPPORTUNITY_DUPLICATE_ONLY
        or duplicate_registry_skip_count > 0
    ):
        return CommercialFreshnessClassification(
            freshness_class=FRESHNESS_NO_NEW_PUBLICATIONS_DUPLICATE_ONLY,
            freshness_reason="all_candidates_already_published",
            freshness_message=(
                f"{duplicate_registry_skip_count} row(s) were skipped because they were already "
                "published in prior cycles. No fresh commercial value in this cycle."
            ),
            commercially_new_value_created_flag=False,
            operator_next_action=(
                "All candidates were already published. "
                "Next opportunity requires new promotion contexts. "
                "Check fresh_promotions upstream cycle."
            ),
        )

    # Fallback: legitimate zero
    return CommercialFreshnessClassification(
        freshness_class=FRESHNESS_NO_NEW_PUBLICATIONS_LEGITIMATE_ZERO,
        freshness_reason="unclassified_noop",
        freshness_message="Commercial cycle completed with NOOP. No fresh commercial value.",
        commercially_new_value_created_flag=False,
        operator_next_action=(
            "No fresh commercial value in this cycle. "
            "Review cycle diagnostics for context and re-run when fresh candidates expected."
        ),
    )


def classify_replay_safety(
    freshness_class: str,
    commercial_outcome_blocked_by_defect_flag: bool,
    stage12_publish_status: str,
) -> CommercialReplaySafetySummary:
    """
    Classify the replay safety of the cycle.

    Tells the operator whether rerunning the exact same inputs should be expected to:
    - create new files
    - produce NOOP_ALREADY_PUBLISHED
    - require upstream data/model change
    - be unsafe due to unresolved defect

    Returns exactly one of:
    - SAFE_NEW_DATA_REQUIRED
    - SAFE_RERUN_EXPECTED_NO_CHANGE
    - SAFE_REVIEW_OR_INPUT_CHANGE_NEEDED
    - UNSAFE_BLOCKED_BY_DEFECT
    """
    # Unsafe path: blocked by defect
    if commercial_outcome_blocked_by_defect_flag or "FAIL" in stage12_publish_status:
        return CommercialReplaySafetySummary(
            replay_safety_class=REPLAY_SAFETY_UNSAFE_BLOCKED_BY_DEFECT,
            replay_safety_reason="defect_blocks_rerun",
            exact_rerun_expected_outcome="RERUN WILL FAIL identically until defect is fixed.",
            operator_guidance_message=(
                "This cycle is blocked by a defect. Rerunning will fail. "
                "Fix root cause and rerun."
            ),
            safe_to_rerun_without_input_change_flag=False,
        )

    # Fresh publications: next rerun may produce duplicate-only NOOP
    if freshness_class == FRESHNESS_FRESH_NEW_PUBLICATIONS_CREATED:
        return CommercialReplaySafetySummary(
            replay_safety_class=REPLAY_SAFETY_SAFE_NEW_DATA_REQUIRED,
            replay_safety_reason="fresh_publications_will_not_rerun_fresh",
            exact_rerun_expected_outcome=(
                "Exact rerun of this cycle will produce NOOP_ALREADY_PUBLISHED "
                "(all newly published rows are now in registry). "
                "Fresh value requires new candidates."
            ),
            operator_guidance_message=(
                "Exact rerun will skip all newly published rows (now duplicates). "
                "New commercial value requires new promotion contexts or fresh data. "
                "This is the normal, expected behavior."
            ),
            safe_to_rerun_without_input_change_flag=True,
        )

    # Duplicate-only: rerun will produce identical NOOP
    if freshness_class == FRESHNESS_NO_NEW_PUBLICATIONS_DUPLICATE_ONLY:
        return CommercialReplaySafetySummary(
            replay_safety_class=REPLAY_SAFETY_SAFE_RERUN_EXPECTED_NO_CHANGE,
            replay_safety_reason="duplicate_only_will_rerun_identical",
            exact_rerun_expected_outcome=(
                "Exact rerun will produce NOOP_ALREADY_PUBLISHED identically. "
                "No outcome change expected."
            ),
            operator_guidance_message=(
                "Rerunning with exact same inputs will produce identical NOOP result. "
                "To change outcome, provide new promotion contexts (upstream cycle). "
                "This is safe to rerun for testing or verification."
            ),
            safe_to_rerun_without_input_change_flag=True,
        )

    # Review-only: rerun will produce identical NOOP unless manual review changes input
    if freshness_class == FRESHNESS_NO_NEW_PUBLICATIONS_REVIEW_ONLY:
        return CommercialReplaySafetySummary(
            replay_safety_class=REPLAY_SAFETY_SAFE_REVIEW_OR_INPUT_CHANGE_NEEDED,
            replay_safety_reason="review_only_may_change_with_approval",
            exact_rerun_expected_outcome=(
                "Exact rerun will produce identical NOOP_VALID_NO_PUBLISHABLE_ROWS "
                "unless manual review approval changes candidate eligibility. "
                "Outcome depends on review team action."
            ),
            operator_guidance_message=(
                "Exact rerun will produce identical review-only NOOP unless "
                "the review team approves the held rows. "
                "Coordinate with commercial team on review outcomes."
            ),
            safe_to_rerun_without_input_change_flag=True,
        )

    # Legitimate zero: rerun will produce identical NOOP unless upstream data changes
    if freshness_class == FRESHNESS_NO_NEW_PUBLICATIONS_LEGITIMATE_ZERO:
        return CommercialReplaySafetySummary(
            replay_safety_class=REPLAY_SAFETY_SAFE_REVIEW_OR_INPUT_CHANGE_NEEDED,
            replay_safety_reason="legitimate_zero_requires_data_change",
            exact_rerun_expected_outcome=(
                "Exact rerun will produce identical NOOP result (legitimate exclusions remain). "
                "Outcome change requires upstream data or model change."
            ),
            operator_guidance_message=(
                "Rows remain legitimately excluded (true-zero demand, etc.). "
                "Exact rerun will produce identical NOOP. "
                "To change outcome, provide fresh candidates or updated demand evidence."
            ),
            safe_to_rerun_without_input_change_flag=True,
        )

    # Filtered out: rerun will produce identical NOOP unless policy gates change
    if freshness_class == FRESHNESS_NO_NEW_PUBLICATIONS_FILTERED_OUT:
        return CommercialReplaySafetySummary(
            replay_safety_class=REPLAY_SAFETY_SAFE_REVIEW_OR_INPUT_CHANGE_NEEDED,
            replay_safety_reason="filtered_out_requires_policy_or_data_change",
            exact_rerun_expected_outcome=(
                "Exact rerun will produce identical NOOP (policy filters remain active). "
                "Outcome change requires policy relaxation or upstream data change."
            ),
            operator_guidance_message=(
                "Candidates remain filtered by policy gates. "
                "Exact rerun will produce identical NOOP. "
                "To unblock, adjust publication policy or provide updated candidates."
            ),
            safe_to_rerun_without_input_change_flag=True,
        )

    # Fallback
    return CommercialReplaySafetySummary(
        replay_safety_class=REPLAY_SAFETY_SAFE_REVIEW_OR_INPUT_CHANGE_NEEDED,
        replay_safety_reason="unclassified_noop",
        exact_rerun_expected_outcome="Exact rerun expected to produce similar NOOP outcome.",
        operator_guidance_message=(
            "Review cycle diagnostics for context. "
            "Exact rerun likely to produce similar result unless inputs change."
        ),
        safe_to_rerun_without_input_change_flag=True,
    )


def build_publication_freshness_diagnostic(
    *,
    freshness_class: str,
    commercially_new_value_created_flag: bool,
    duplicate_registry_skip_count: int,
    newly_published_row_count: int,
    review_only_row_count: int,
    legitimate_zero_row_count: int,
    filtered_out_row_count: int,
    defect_blocked_row_count: int,
    replay_safety_class: str,
    replay_safety_reason: str,
    first_publication_date_if_any: Optional[str] = None,
    last_publication_date_if_any: Optional[str] = None,
) -> PublicationFreshnessDiagnostic:
    """Build comprehensive publication freshness diagnostic artifact."""
    return PublicationFreshnessDiagnostic(
        freshness_class=freshness_class,
        freshness_reason=(
            "fresh_publications_written"
            if commercially_new_value_created_flag
            else "no_new_publications"
        ),
        commercially_new_value_created_flag=commercially_new_value_created_flag,
        duplicate_registry_skip_count=duplicate_registry_skip_count,
        newly_published_row_count=newly_published_row_count,
        review_only_row_count=review_only_row_count,
        legitimate_zero_row_count=legitimate_zero_row_count,
        filtered_out_row_count=filtered_out_row_count,
        defect_blocked_row_count=defect_blocked_row_count,
        first_publication_date_if_any=first_publication_date_if_any,
        last_publication_date_if_any=last_publication_date_if_any,
        replay_safety_status=replay_safety_class,
        replay_safety_reason=replay_safety_reason,
    )


def _get_operator_guidance_message(
    *,
    commercial_outcome_class: str,
    publication_opportunity_class: str,
    stage12_publish_status: str,
    stage12_publishable_row_count: int,
) -> str:
    """Derive operator-friendly next-action guidance from run state."""
    if "FAILURE" in commercial_outcome_class:
        return "**Action**: Inspect operator_run.log for root cause. Fix defect and rerun. Contact platform team if blocker persists."

    if publication_opportunity_class == PUBLICATION_OPPORTUNITY_FRESH:
        return f"**Action**: ✅ **{stage12_publishable_row_count} fresh publication(s) ready**. Verify client execution manifests and monitor store delivery within scheduled window."

    if publication_opportunity_class == PUBLICATION_OPPORTUNITY_DUPLICATE_ONLY:
        return "**Action**: All candidates already published. Next opportunity requires new promotion contexts. Check fresh_promotions upstream cycle."

    if publication_opportunity_class == PUBLICATION_OPPORTUNITY_REVIEW_ONLY:
        return "**Action**: Rows are commercially interesting but held for manual review. Escalate to commercial team for review approval."

    if publication_opportunity_class == PUBLICATION_OPPORTUNITY_FILTERED_OUT:
        return "**Action**: Candidates exist but filtered by policy. Review stage12 publication_noop_diagnostics.json for gate-by-gate breakdown and business thresholds."

    if publication_opportunity_class == PUBLICATION_OPPORTUNITY_LEGITIMATE_ZERO:
        return "**Action**: No fresh publication opportunity in this cycle (true-zero demand or no publishable rows). Re-run next cycle when fresh candidates expected."

    return "**Action**: Review cycle diagnostics for unexpected state. Contact platform team if uncertain."


def validate_freshness_replay_consistency(
    publication_opportunity_class: str,
    freshness_class: str,
    commercially_new_value_created_flag: bool,
    replay_safety_class: str,
    safe_to_rerun_without_input_change_flag: bool,
    stage12_publish_status: str,
    defect_blocked_row_count: int,
) -> None:
    """
    Validate consistency of freshness and replay-safety classifications.

    Raises ValueError if contradictions are detected.
    """
    errors = []

    # If publish status says new publications, freshness cannot be duplicate-only
    if "PASS" in stage12_publish_status and "POS_UPLOAD" in stage12_publish_status:
        if freshness_class == FRESHNESS_NO_NEW_PUBLICATIONS_DUPLICATE_ONLY:
            errors.append(
                f"Contradiction: publish_status indicates new publications but "
                f"freshness_class is {freshness_class}"
            )

    # If duplicate-only NOOP, new value flag must be false
    if freshness_class == FRESHNESS_NO_NEW_PUBLICATIONS_DUPLICATE_ONLY:
        if commercially_new_value_created_flag:
            errors.append(
                "Contradiction: freshness_class is duplicate-only but "
                "commercially_new_value_created_flag is true"
            )

    # If blocked by defect, replay-safe-without-input-change must be false
    if defect_blocked_row_count > 0:
        if safe_to_rerun_without_input_change_flag:
            errors.append(
                "Contradiction: defect_blocked_row_count > 0 but "
                "safe_to_rerun_without_input_change_flag is true"
            )
        if replay_safety_class != REPLAY_SAFETY_UNSAFE_BLOCKED_BY_DEFECT:
            errors.append(
                f"Contradiction: defect blocked but replay_safety_class is {replay_safety_class}"
            )

    # Fresh publications must have matching freshness flag
    if freshness_class == FRESHNESS_FRESH_NEW_PUBLICATIONS_CREATED:
        if not commercially_new_value_created_flag:
            errors.append(
                "Contradiction: freshness_class is fresh but "
                "commercially_new_value_created_flag is false"
            )
        if replay_safety_class != REPLAY_SAFETY_SAFE_NEW_DATA_REQUIRED:
            errors.append(
                f"Contradiction: freshness is fresh but replay_safety_class is {replay_safety_class}"
            )

    if errors:
        raise ValueError(
            f"Freshness/replay-safety consistency check failed:\n" + "\n".join(errors)
        )
