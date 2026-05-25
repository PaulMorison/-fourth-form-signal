"""Governed Stage 11/12 publishability transparency split.

Computes a single, easy-to-trust 7-tier split that explains exactly why the
commercial publish stage produced the row counts it did. Designed to be the
authoritative answer to "why was nothing auto-published?" without forcing an
operator to cross-reference five separate stage diagnostics.

The classifier is deliberately deterministic and uses only columns already
present in the Stage 11 master CSV (`store_download_frame`) plus the Stage 12
publisher artifact counts. It does NOT mutate any decision, exclusion, or
publish status — it only describes them.

Tier definitions (mutually exclusive, exhaustive across the master frame):

  1. true_zero_demand_rows
       Zero forecast that the model classifies as a TRUE_ZERO commercial
       outcome (no historical signal AND no expected lift). These are
       legitimately zero-demand SKUs and are NOT a defect.

  2. evidence_supported_zero_rows
       Zero or near-zero forecast supported by upstream evidence
       (cold_start, low_nonzero with corroboration). Not artificial.

  3. artificial_collapse_rows
       Zero or collapsed forecast that the demand evidence classifier flags
       as suspicious (`DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE`). These
       are the rows that genuinely warrant operator investigation.

  4. registry_duplicate_rows
      Rows removed by the Stage 12 registry duplicate policy. These are
      prior-publication evidence, not fresh review or publishable rows.

  5. review_required_rows
      Fresh post-registry rows held for human commercial review before any
      order is released.

  6. policy_excluded_legitimate_rows
      Non-review Stage 12 policy exclusions that remained after registry,
      review-only, defect, mapping, and schema gates.

  7. final_publishable_rows
       Decision recommendation == ORDER and the row was actually written
       to a Stage 12 POS upload artifact (i.e., counted in
       `pos_upload_row_count`).

Hold/DO_NOT_ORDER rows that are neither REVIEW nor publishable land in
`other_non_actionable_rows` so the split remains row-conserving.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

import pandas as pd

DEMAND_EVIDENCE_CLASS_TRUE_ZERO = "TRUE_ZERO"
DEMAND_EVIDENCE_CLASS_COLD_START = "COLD_START"
DEMAND_EVIDENCE_CLASS_LOW_NONZERO = "LOW_NONZERO"
DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE = "ARTIFICIAL_COLLAPSE"

# Operator headline classes derived from the split.
HEADLINE_PUBLISHED = "PUBLISHED_NEW_ORDERS"
HEADLINE_REVIEW_ONLY = "REVIEW_ONLY_NO_AUTO_PUBLISH"
HEADLINE_VALID_ZEROS_ONLY = "LEGITIMATELY_NOTHING_TO_PUBLISH"
HEADLINE_SUSPICIOUS_COLLAPSE = "SUSPICIOUS_COLLAPSE_BLOCKED_PUBLISH"
HEADLINE_POLICY_EXCLUDED_ALL = "POLICY_EXCLUDED_OTHERWISE_PUBLISHABLE"
HEADLINE_ALREADY_PUBLISHED_ONLY = "ALREADY_PUBLISHED_NO_FRESH_ROWS"
HEADLINE_NO_DECISION_SURFACE = "NO_DECISION_SURFACE_ROWS"


@dataclass(frozen=True)
class CommercialPublishabilitySplit:
    """Authoritative governed split of every Stage 11 row by why it ended where it did."""

    total_decision_surface_rows: int
    true_zero_demand_rows: int
    evidence_supported_zero_rows: int
    artificial_collapse_rows: int
    registry_duplicate_rows: int
    review_required_rows: int
    policy_excluded_legitimate_rows: int
    final_publishable_rows: int
    other_non_actionable_rows: int
    headline_class: str
    headline_message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _norm(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def build_commercial_publishability_split(
    *,
    store_download_frame: pd.DataFrame,
    pos_upload_row_count: int,
    pos_excluded_row_count: int,
    stage12_review_only_row_count: int | None = None,
    registry_duplicate_row_count: int = 0,
) -> CommercialPublishabilitySplit:
    """Build the governed publish/review/exclusion split.

    Inputs are intentionally small so this can be unit-tested without
    depending on Stage 11 or Stage 12 state.
    """
    total_rows = int(len(store_download_frame.index))
    if total_rows == 0:
        return CommercialPublishabilitySplit(
            total_decision_surface_rows=0,
            true_zero_demand_rows=0,
            evidence_supported_zero_rows=0,
            artificial_collapse_rows=0,
            registry_duplicate_rows=max(int(registry_duplicate_row_count), 0),
            review_required_rows=0,
            policy_excluded_legitimate_rows=max(int(pos_excluded_row_count), 0),
            final_publishable_rows=max(int(pos_upload_row_count), 0),
            other_non_actionable_rows=0,
            headline_class=HEADLINE_NO_DECISION_SURFACE,
            headline_message=(
                "Stage 11 produced no decision-surface rows; nothing was available "
                "to publish or review."
            ),
        )

    if "decision_recommendation" in store_download_frame.columns:
        decision = _norm(store_download_frame["decision_recommendation"])
    else:
        decision = pd.Series([""] * total_rows, index=store_download_frame.index)

    if "demand_evidence_class" in store_download_frame.columns:
        evidence = _norm(store_download_frame["demand_evidence_class"])
    else:
        evidence = pd.Series([""] * total_rows, index=store_download_frame.index)

    is_review = decision == "REVIEW"
    is_order = decision == "ORDER"

    # Tier 3 first so it cannot be hidden by REVIEW: a row that is
    # ARTIFICIAL_COLLAPSE deserves to be counted as suspicious even if its
    # decision happens to be REVIEW. We then subtract from REVIEW.
    is_artificial = evidence == DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE
    artificial_collapse_rows = int(is_artificial.sum())

    is_true_zero = (evidence == DEMAND_EVIDENCE_CLASS_TRUE_ZERO) & ~is_artificial
    true_zero_demand_rows = int(is_true_zero.sum())

    is_evidence_zero = (
        evidence.isin({DEMAND_EVIDENCE_CLASS_COLD_START, DEMAND_EVIDENCE_CLASS_LOW_NONZERO})
        & ~is_artificial
    )
    evidence_supported_zero_rows = int(is_evidence_zero.sum())

    # REVIEW rows that are NOT already counted as artificial collapse. When
    # Stage 12 provides review-only skip counts, use that post-registry grain
    # so prior publications are not reported as fresh review work.
    stage11_review_required_rows = int((is_review & ~is_artificial).sum())
    if stage12_review_only_row_count is None:
        review_required_rows = stage11_review_required_rows
    else:
        review_required_rows = max(int(stage12_review_only_row_count), 0)

    # Final publishable rows are bounded by what Stage 12 actually wrote.
    final_publishable_rows = max(int(pos_upload_row_count), 0)
    registry_duplicate_rows = max(int(registry_duplicate_row_count), 0)
    policy_excluded_legitimate_rows = max(
        int(pos_excluded_row_count) - review_required_rows,
        0,
    )

    # Residual: HOLD / DO_NOT_ORDER / anything else not already accounted for.
    accounted = (
        true_zero_demand_rows
        + evidence_supported_zero_rows
        + artificial_collapse_rows
        + registry_duplicate_rows
        + review_required_rows
        + final_publishable_rows
        + policy_excluded_legitimate_rows
    )
    other_non_actionable_rows = max(total_rows - accounted, 0)

    if final_publishable_rows > 0:
        headline_class = HEADLINE_PUBLISHED
        headline_message = (
            f"{final_publishable_rows} row(s) published as POS-ready; "
            f"{review_required_rows} row(s) require manager review."
        )
    elif artificial_collapse_rows > 0 and (
        artificial_collapse_rows
        >= max(review_required_rows, true_zero_demand_rows + evidence_supported_zero_rows)
    ):
        headline_class = HEADLINE_SUSPICIOUS_COLLAPSE
        headline_message = (
            f"No new orders published. {artificial_collapse_rows} row(s) flagged as "
            "artificial demand collapse and require investigation before any "
            "publish action can clear policy gates."
        )
    elif review_required_rows > 0:
        headline_class = HEADLINE_REVIEW_ONLY
        headline_message = (
            f"No new orders auto-published. {review_required_rows} row(s) need "
            "manager review before any order can be released."
        )
    elif registry_duplicate_rows > 0 and registry_duplicate_rows >= total_rows:
        headline_class = HEADLINE_ALREADY_PUBLISHED_ONLY
        headline_message = (
            f"No new orders published because all {registry_duplicate_rows} row(s) "
            "were already published in prior cycles."
        )
    elif policy_excluded_legitimate_rows > 0 and (
        true_zero_demand_rows + evidence_supported_zero_rows + artificial_collapse_rows == 0
    ):
        headline_class = HEADLINE_POLICY_EXCLUDED_ALL
        headline_message = (
            f"No new orders published because {policy_excluded_legitimate_rows} "
            "otherwise-publishable row(s) were excluded by Stage 12 policy gates."
        )
    elif true_zero_demand_rows + evidence_supported_zero_rows > 0:
        headline_class = HEADLINE_VALID_ZEROS_ONLY
        headline_message = (
            "No orders published because every candidate row resolved to a "
            "legitimate zero-demand outcome — this is not a defect."
        )
    else:
        headline_class = HEADLINE_NO_DECISION_SURFACE
        headline_message = (
            "No new orders published and no review-required rows; inspect "
            "Stage 11/12 diagnostics for detail."
        )

    return CommercialPublishabilitySplit(
        total_decision_surface_rows=total_rows,
        true_zero_demand_rows=true_zero_demand_rows,
        evidence_supported_zero_rows=evidence_supported_zero_rows,
        artificial_collapse_rows=artificial_collapse_rows,
        registry_duplicate_rows=registry_duplicate_rows,
        review_required_rows=review_required_rows,
        policy_excluded_legitimate_rows=policy_excluded_legitimate_rows,
        final_publishable_rows=final_publishable_rows,
        other_non_actionable_rows=other_non_actionable_rows,
        headline_class=headline_class,
        headline_message=headline_message,
    )


def split_to_manifest_payload(
    split: CommercialPublishabilitySplit,
) -> Mapping[str, object]:
    """Flatten the split into the operator-manifest key/value shape."""
    return {
        "commercial_publishability_total_rows": split.total_decision_surface_rows,
        "commercial_publishability_true_zero_demand_rows": split.true_zero_demand_rows,
        "commercial_publishability_evidence_supported_zero_rows": split.evidence_supported_zero_rows,
        "commercial_publishability_artificial_collapse_rows": split.artificial_collapse_rows,
        "commercial_publishability_registry_duplicate_rows": split.registry_duplicate_rows,
        "commercial_publishability_review_required_rows": split.review_required_rows,
        "commercial_publishability_policy_excluded_rows": split.policy_excluded_legitimate_rows,
        "commercial_publishability_final_publishable_rows": split.final_publishable_rows,
        "commercial_publishability_other_non_actionable_rows": split.other_non_actionable_rows,
        "commercial_publishability_headline_class": split.headline_class,
        "commercial_publishability_headline_message": split.headline_message,
    }
