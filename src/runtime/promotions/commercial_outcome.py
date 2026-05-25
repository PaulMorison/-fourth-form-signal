from __future__ import annotations

"""Authoritative commercial outcome seams for promotions runtime runs."""

from dataclasses import asdict, dataclass

COMMERCIAL_SUCCESS_NEW_PUBLICATIONS = "COMMERCIAL_SUCCESS_NEW_PUBLICATIONS"
COMMERCIAL_SUCCESS_GOVERNED_NOOP_ALREADY_PUBLISHED = "COMMERCIAL_SUCCESS_GOVERNED_NOOP_ALREADY_PUBLISHED"
COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS = "COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS"
COMMERCIAL_FAILURE_DEFECT = "COMMERCIAL_FAILURE_DEFECT"
COMMERCIAL_FAILURE_VALIDATION = "COMMERCIAL_FAILURE_VALIDATION"
COMMERCIAL_FAILURE_RUNTIME = "COMMERCIAL_FAILURE_RUNTIME"

STAGE13_SKIP_CLASS_STAGE12_NOOP_ALREADY_PUBLISHED = "STAGE12_NOOP_ALREADY_PUBLISHED"
STAGE13_SKIP_CLASS_STAGE12_NOOP_NO_PUBLISHABLE_ROWS = "STAGE12_NOOP_NO_PUBLISHABLE_ROWS"
STAGE13_SKIP_CLASS_VALIDATION_EXECUTED = "VALIDATION_EXECUTED"
STAGE13_SKIP_CLASS_VALIDATION_NOT_REQUESTED = "VALIDATION_NOT_REQUESTED"
STAGE13_SKIP_CLASS_VALIDATION_BLOCKED_BY_FAILURE = "VALIDATION_BLOCKED_BY_FAILURE"

VALIDATION_STATUS_PASS = "PASS"
VALIDATION_STATUS_PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
VALIDATION_STATUS_FAIL = "FAIL"

PUBLISH_STATUS_PASS = "PASS"
PUBLISH_STATUS_PASS_WITH_EXCLUSIONS = "PASS_WITH_EXCLUSIONS"
PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED = "NOOP_ALREADY_PUBLISHED"
PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS = "NOOP_VALID_NO_PUBLISHABLE_ROWS"
PUBLISH_STATUS_FAIL = "FAIL"
PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS = "FAIL_NO_ELIGIBLE_ROWS"


@dataclass(frozen=True)
class CommercialOutcomeInput:
    """Normalized Stage 11/12/13 runtime inputs for final commercial outcome classification."""

    run_completed_successfully_flag: bool
    stage12_publish_status: str
    stage12_publish_status_reason: str
    stage12_pos_upload_row_count: int
    stage12_candidate_row_count: int
    stage12_duplicate_registry_skip_count: int
    stage13_validation_status: str
    stage13_validation_status_reason: str
    stage13_skip_class: str
    runtime_failure_reason: str = ""


@dataclass(frozen=True)
class CommercialOutcomeClassification:
    """Authoritative final commercial outcome classification for the operator run."""

    commercial_outcome_class: str
    commercial_outcome_reason: str
    commercial_outcome_message: str
    commercial_new_publication_count: int
    commercial_noop_flag: bool
    commercial_failure_flag: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PublicationFreshnessDiagnostic:
    """Diagnostic-only assessment of whether a cycle has fresh publications behind duplicate protection."""

    candidate_row_count: int
    duplicate_registry_skip_count: int
    fresh_publication_candidate_count: int
    all_candidates_already_published_flag: bool
    ready_for_fresh_publication_test_flag: bool
    recommended_next_action: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_commercial_outcome(payload: CommercialOutcomeInput) -> CommercialOutcomeClassification:
    """Classify the final run outcome into one authoritative commercial class."""
    if not payload.run_completed_successfully_flag:
        return CommercialOutcomeClassification(
            commercial_outcome_class=COMMERCIAL_FAILURE_RUNTIME,
            commercial_outcome_reason=payload.runtime_failure_reason or "runtime_stage_failure",
            commercial_outcome_message=(
                "Runtime failed before a complete commercial publish/validation cycle finished."
            ),
            commercial_new_publication_count=0,
            commercial_noop_flag=False,
            commercial_failure_flag=True,
        )

    if payload.stage12_publish_status in {PUBLISH_STATUS_FAIL, PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS}:
        return CommercialOutcomeClassification(
            commercial_outcome_class=COMMERCIAL_FAILURE_DEFECT,
            commercial_outcome_reason=payload.stage12_publish_status_reason or "stage12_defect",
            commercial_outcome_message=(
                "Stage 12 failed a commercial publication guardrail and requires defect remediation."
            ),
            commercial_new_publication_count=0,
            commercial_noop_flag=False,
            commercial_failure_flag=True,
        )

    if payload.stage13_validation_status == VALIDATION_STATUS_FAIL:
        return CommercialOutcomeClassification(
            commercial_outcome_class=COMMERCIAL_FAILURE_VALIDATION,
            commercial_outcome_reason=payload.stage13_validation_status_reason or "stage13_validation_fail",
            commercial_outcome_message=(
                "Stage 13 validation failed and commercial outputs are not publish-ready."
            ),
            commercial_new_publication_count=0,
            commercial_noop_flag=False,
            commercial_failure_flag=True,
        )

    if payload.stage12_publish_status in {PUBLISH_STATUS_PASS, PUBLISH_STATUS_PASS_WITH_EXCLUSIONS}:
        publication_count = max(int(payload.stage12_pos_upload_row_count), 0)
        return CommercialOutcomeClassification(
            commercial_outcome_class=COMMERCIAL_SUCCESS_NEW_PUBLICATIONS,
            commercial_outcome_reason=payload.stage12_publish_status_reason or "new_publications_written",
            commercial_outcome_message=(
                "Commercial run succeeded with new Stage 12 publication outputs."
            ),
            commercial_new_publication_count=publication_count,
            commercial_noop_flag=False,
            commercial_failure_flag=False,
        )

    if payload.stage12_publish_status == PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED:
        return CommercialOutcomeClassification(
            commercial_outcome_class=COMMERCIAL_SUCCESS_GOVERNED_NOOP_ALREADY_PUBLISHED,
            commercial_outcome_reason=payload.stage12_publish_status_reason or "all_candidates_already_published",
            commercial_outcome_message=(
                "Commercial run succeeded with governed NOOP because all Stage 12 candidates were already published."
            ),
            commercial_new_publication_count=0,
            commercial_noop_flag=True,
            commercial_failure_flag=False,
        )

    if payload.stage12_publish_status == PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS:
        return CommercialOutcomeClassification(
            commercial_outcome_class=COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS,
            commercial_outcome_reason=payload.stage12_publish_status_reason or "no_publishable_rows",
            commercial_outcome_message=(
                "Commercial run succeeded with governed NOOP because no publishable Stage 12 rows remained after policy."
            ),
            commercial_new_publication_count=0,
            commercial_noop_flag=True,
            commercial_failure_flag=False,
        )

    raise ValueError(
        "Unsupported Stage 12 publish status for commercial outcome classification: "
        f"{payload.stage12_publish_status}"
    )


def classify_stage13_validation_skip(
    *,
    stage12_publish_status: str,
    stage13_review_paths_present: bool,
    stage13_pos_paths_present: bool,
    stage13_reconciliation_paths_present: bool,
) -> tuple[str, str]:
    """Classify Stage 13 validation execution vs skip semantics from Stage 12 outcome and Stage 13 inputs."""
    has_stage13_inputs = (
        stage13_review_paths_present
        or stage13_pos_paths_present
        or stage13_reconciliation_paths_present
    )

    if stage12_publish_status in {PUBLISH_STATUS_FAIL, PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS}:
        return (
            STAGE13_SKIP_CLASS_VALIDATION_BLOCKED_BY_FAILURE,
            "Stage 13 validation blocked because Stage 12 failed.",
        )

    if stage12_publish_status == PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED:
        return (
            STAGE13_SKIP_CLASS_STAGE12_NOOP_ALREADY_PUBLISHED,
            "Stage 13 validation skipped because Stage 12 produced governed NOOP_ALREADY_PUBLISHED.",
        )

    if stage12_publish_status == PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS:
        return (
            STAGE13_SKIP_CLASS_STAGE12_NOOP_NO_PUBLISHABLE_ROWS,
            "Stage 13 validation skipped because Stage 12 produced governed NOOP_NO_PUBLISHABLE_ROWS.",
        )

    if has_stage13_inputs:
        return (
            STAGE13_SKIP_CLASS_VALIDATION_EXECUTED,
            "Stage 13 validation executed against generated Stage 12 artifacts.",
        )

    return (
        STAGE13_SKIP_CLASS_VALIDATION_NOT_REQUESTED,
        "Stage 13 validation was not requested because no validation inputs were provided.",
    )


def build_publication_freshness_diagnostic(
    *,
    candidate_row_count: int,
    duplicate_registry_skip_count: int,
) -> PublicationFreshnessDiagnostic:
    """Build the governed Stage 12 freshness diagnostic without altering publication policy."""
    candidates = max(int(candidate_row_count), 0)
    duplicate_skips = max(int(duplicate_registry_skip_count), 0)
    fresh_candidates = max(candidates - duplicate_skips, 0)
    all_already_published = candidates > 0 and duplicate_skips >= candidates and fresh_candidates == 0
    ready_for_fresh_test = fresh_candidates > 0

    if all_already_published:
        action = (
            "All candidates were duplicate-protected by registry policy. Re-run with a new commercial cycle context "
            "when fresh candidates are expected."
        )
    elif ready_for_fresh_test:
        action = (
            "Fresh publication candidates exist behind current policy gates. Run the next governed live cycle and monitor Stage 12 publication outputs."
        )
    elif candidates == 0:
        action = (
            "No Stage 12 candidates were produced. Investigate upstream eligibility and gating diagnostics before re-running."
        )
    else:
        action = (
            "No fresh publication candidates remain after policy gates. Review Stage 12 exclusion and NOOP diagnostics."
        )

    return PublicationFreshnessDiagnostic(
        candidate_row_count=candidates,
        duplicate_registry_skip_count=duplicate_skips,
        fresh_publication_candidate_count=fresh_candidates,
        all_candidates_already_published_flag=all_already_published,
        ready_for_fresh_publication_test_flag=ready_for_fresh_test,
        recommended_next_action=action,
    )
