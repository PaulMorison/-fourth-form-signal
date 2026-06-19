from __future__ import annotations

"""Diagnostics-only promotions policy slice replay harness."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from state.promotions.feature_engineering.demand.ft_order_decision_diagnostics import (
    ORDER_DECISION_DIAGNOSTICS_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_pca_residual_structure import (
    PCA_RESIDUAL_STRUCTURE_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_promotion_situational_awareness import (
    PROMOTION_SITUATIONAL_AWARENESS_REVIEW_ONLY_FEATURE_COLUMNS,
)


REPLAY_MODE_HISTORICAL_ONLY = "historical_only"
REPLAY_MODE_FUTURE_STAGE11 = "future_stage11"
REPLAY_MODE_FUTURE_STAGE12 = "future_stage12"
REPLAY_MODE_BASELINE_COMPARISON = "baseline_comparison"
REPLAY_MODE_CHOICES: tuple[str, ...] = (
    REPLAY_MODE_HISTORICAL_ONLY,
    REPLAY_MODE_FUTURE_STAGE11,
    REPLAY_MODE_FUTURE_STAGE12,
    REPLAY_MODE_BASELINE_COMPARISON,
)

_NO_POLICY_REASON_VALUES = {
    "",
    "nan",
    "none",
    "no_policy_adjustment",
    "no_policy_reason",
    "no_review_override",
    "unavailable",
}
_BUY_ORDER_ACTIONS = {"BUY", "ORDER", "PUBLISH", "RECOMMEND_ORDER", "AUTO_ORDER", "ACTION_PUBLISH_NOW"}
_REVIEW_ACTIONS = {"REVIEW", "ACTION_REVIEW_NOW", "MANUAL_REVIEW"}
_OPERATOR_ACTION_CLASSES: tuple[str, ...] = ("BUY", "HOLD", "DO NOT BUY", "REVIEW")
_DECISION_RECOMMENDATION_CLASSES: tuple[str, ...] = ("ORDER", "HOLD", "DO_NOT_ORDER", "REVIEW")
_STAGE12_PUBLISHABILITY_CLASSES: tuple[str, ...] = ("publishable", "review_only", "excluded")
_GOVERNED_ORDER_UNIT_COLUMNS: tuple[str, ...] = (
    "suggested_order_units",
    "recommended_order_units",
    "adjusted_order_cap_units",
    "recommended_order_units_to_min_base_stock",
    "allocation_units",
)
_GOVERNED_ORDER_VALUE_COLUMNS: tuple[str, ...] = (
    "suggested_order_value",
    "recommended_order_value",
    "suggested_order_value_dollars",
    "recommended_order_value_dollars",
    "suggested_order_cost_dollars",
    "recommended_order_cost_dollars",
    "capital_at_risk_adjusted_dollars",
)
_REVIEW_ONLY_COLUMNS = (
    *PCA_RESIDUAL_STRUCTURE_REVIEW_ONLY_FEATURE_COLUMNS,
    *PROMOTION_SITUATIONAL_AWARENESS_REVIEW_ONLY_FEATURE_COLUMNS,
    *ORDER_DECISION_DIAGNOSTICS_REVIEW_ONLY_FEATURE_COLUMNS,
)
_TRUST_FLOOR_CONTEXT_COLUMNS: tuple[str, ...] = (
    "feature_units_needed_for_trust_floor",
    "feature_end_of_promo_target_floor_units",
    "target_floor_units",
    "feature_end_of_promo_target_units",
    "target_end_stock_units",
)
_SPECULATIVE_CAPITAL_CONTEXT_COLUMNS: tuple[str, ...] = (
    "feature_capital_tied_above_trust_target",
    "capital_tied_above_trust_target",
    "feature_risk_adjusted_value_of_speculative_units",
    "units_above_trust_target",
    "feature_units_above_trust_target",
)
_SAME_DISCOUNT_CONTEXT_COLUMNS: tuple[str, ...] = (
    "feature_historical_promo_events_same_discount",
    "feature_historical_units_same_discount_avg",
    "feature_prior_same_or_better_discount_56d_flag",
    "feature_prior_same_discount_56d_flag",
)
_NO_HISTORY_SPARSE_CONTEXT_COLUMNS: tuple[str, ...] = (
    "feature_no_promo_history_flag",
    "feature_sparse_demand_low_signal_flag",
    "feature_sparse_repeat_purchase_flag",
    "feature_sparse_demand_random_tail_flag",
)
_EQUILIBRIUM_CONTEXT_COLUMNS: tuple[str, ...] = (
    "feature_anchor_presence_dependency_score",
    "feature_drag_along_probability",
    "feature_micro_market_clearing_pressure",
    "feature_high_demand_underprotection_score",
    "feature_basket_anchor_strength_score",
)
WIDENED_ROW_ATTRIBUTION_COLUMNS: tuple[str, ...] = (
    "row_key",
    "baseline_decision_action",
    "baseline_review_reason",
    "baseline_policy_adjustment_reason",
    "current_decision_action",
    "current_review_reason",
    "current_policy_adjustment_reason",
    "baseline_suggested_order_units",
    "current_suggested_order_units",
    "suggested_order_units_delta",
    "baseline_order_value",
    "current_order_value",
    "order_value_delta",
    "trust_floor_state",
    "speculative_capital_state",
    "same_discount_evidence",
    "no_history_sparse_state",
    "equilibrium_signal_state",
    "missing_evidence",
    "diagnostics_only",
)


class GovernedReplayAttributionError(ValueError):
    """Raised when replay attribution cannot be computed from governed evidence.

    Purpose:
        Distinguish governed replay attribution failures from generic parser
        errors so callers and tests can assert fail-loud behavior.

    Required inputs:
        A human-readable message naming the missing or unsafe evidence.

    Outputs:
        A ValueError subclass with no extra payload.

    Assumptions:
        The replay harness must not replace missing governed evidence with
        technical forecasts or zero-valued commercial defaults.

    Failure behavior:
        Propagates to the CLI and prevents evidence artifacts from being
        written for untrustworthy replay inputs.
    """


@dataclass(frozen=True)
class PromotionPolicySliceReplaySummary:
    replay_mode: str
    current_row_count: int
    baseline_row_count: int
    comparable_row_count: int
    affected_row_count: int
    current_buy_order_row_count: int
    baseline_buy_order_row_count: int
    buy_order_row_delta: int
    current_publishable_row_count: int
    baseline_publishable_row_count: int
    publishable_row_delta: int
    current_review_only_row_count: int
    baseline_review_only_row_count: int
    review_only_row_delta: int
    operator_action_deltas: dict[str, int]
    decision_recommendation_deltas: dict[str, int]
    stage12_publishability_deltas: dict[str, int]
    rows_hit_by_policy_reason_count: int
    units_removed_total: float
    capital_removed_total: float
    review_only_delta_row_count: int
    buy_order_widening_flag: bool
    diagnostics_only: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionPolicySliceReplayArtifacts:
    output_root: str
    runtime_manifest_path: str
    summary_json_path: str
    action_delta_csv_path: str
    publishability_delta_csv_path: str
    policy_reason_delta_csv_path: str
    row_deltas_csv_path: str
    widened_row_attribution_csv_path: str
    widened_row_attribution_json_path: str
    policy_reason_summary_csv_path: str
    review_only_deltas_csv_path: str
    summary: PromotionPolicySliceReplaySummary
    action_deltas: pd.DataFrame
    publishability_deltas: pd.DataFrame
    row_deltas: pd.DataFrame
    widened_row_attribution: pd.DataFrame
    policy_reason_summary: pd.DataFrame
    review_only_deltas: pd.DataFrame


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    run_policy_slice_replay(
        current_csv_path=args.current_csv_path,
        baseline_csv_path=args.baseline_csv_path,
        output_root=args.output_root,
        run_id=args.run_id,
        replay_mode=args.replay_mode,
    )


def run_policy_slice_replay(
    *,
    current_csv_path: str | Path,
    baseline_csv_path: str | Path | None = None,
    output_root: str | Path | None = None,
    run_id: str | None = None,
    replay_mode: str = REPLAY_MODE_HISTORICAL_ONLY,
) -> PromotionPolicySliceReplayArtifacts:
    """Run diagnostics-only policy replay from persisted current/baseline CSVs.

    Purpose:
        Compare persisted governed baseline artifacts with a current-code replay
        slice and write analyst evidence tables only.

    Inputs:
        Paths to current and optional baseline CSV artifacts, output root,
        replay mode, and optional run id.

    Outputs:
        Artifact paths plus in-memory summary and evidence tables.

    Failure behaviour:
        Fails loud when required current or baseline artifacts are missing. The
        runner does not publish, mutate live manifests, or rewrite store CSVs.
    """

    if replay_mode not in REPLAY_MODE_CHOICES:
        raise ValueError(f"Unsupported policy slice replay mode: {replay_mode}")
    resolved_run_id = run_id or datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    resolved_output_root = Path(output_root or Path("tmp") / "promotions_policy_slice_replay" / resolved_run_id)
    resolved_output_root.mkdir(parents=True, exist_ok=True)

    current_path = Path(current_csv_path).expanduser().resolve()
    if not current_path.exists():
        raise FileNotFoundError(f"Current replay CSV not found: {current_path}")
    baseline_path = Path(baseline_csv_path).expanduser().resolve() if baseline_csv_path else None
    if baseline_path is not None and not baseline_path.exists():
        raise FileNotFoundError(f"Baseline replay CSV not found: {baseline_path}")
    if replay_mode != REPLAY_MODE_HISTORICAL_ONLY and baseline_path is None:
        raise ValueError(f"{replay_mode} replay mode requires baseline_csv_path")

    current_frame = pd.read_csv(current_path, encoding="utf-8")
    baseline_frame = pd.read_csv(baseline_path, encoding="utf-8") if baseline_path is not None else None

    summary, row_deltas, policy_reason_summary, review_only_deltas = build_policy_slice_replay_tables(
        current_frame=current_frame,
        baseline_frame=baseline_frame,
        replay_mode=replay_mode,
    )
    action_deltas = _build_action_delta_table(row_deltas)
    publishability_deltas = _build_publishability_delta_table(row_deltas)
    widened_row_attribution = _build_widened_row_attribution(
        row_deltas=row_deltas,
        current_frame=current_frame,
        baseline_frame=baseline_frame,
    )

    summary_json_path = resolved_output_root / "policy_slice_replay_summary.json"
    action_delta_csv_path = resolved_output_root / "policy_slice_replay_action_deltas.csv"
    publishability_delta_csv_path = resolved_output_root / "policy_slice_replay_publishability_deltas.csv"
    policy_reason_delta_csv_path = resolved_output_root / "policy_slice_replay_policy_reason_deltas.csv"
    row_deltas_csv_path = resolved_output_root / "policy_slice_replay_row_deltas.csv"
    widened_row_attribution_csv_path = resolved_output_root / "policy_slice_replay_widened_row_attribution.csv"
    widened_row_attribution_json_path = resolved_output_root / "policy_slice_replay_widened_row_attribution.json"
    review_only_deltas_csv_path = resolved_output_root / "policy_slice_replay_review_only_deltas.csv"
    runtime_manifest_path = resolved_output_root / "policy_slice_replay_runtime_manifest.json"

    action_deltas.to_csv(action_delta_csv_path, index=False)
    publishability_deltas.to_csv(publishability_delta_csv_path, index=False)
    policy_reason_summary.to_csv(policy_reason_delta_csv_path, index=False)
    row_deltas.to_csv(row_deltas_csv_path, index=False)
    widened_row_attribution.to_csv(widened_row_attribution_csv_path, index=False)
    widened_row_attribution_json_path.write_text(
        json.dumps(
            {
                "run_id": resolved_run_id,
                "replay_mode": replay_mode,
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "diagnostics_only": True,
                "widened_row_count": int(len(widened_row_attribution.index)),
                "missing_evidence_row_count": int(widened_row_attribution["missing_evidence"].astype(str).ne("").sum())
                if not widened_row_attribution.empty
                else 0,
                "rows": widened_row_attribution.to_dict(orient="records"),
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    review_only_deltas.to_csv(review_only_deltas_csv_path, index=False)
    summary_json_path.write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    runtime_manifest = {
        "run_id": resolved_run_id,
        "replay_mode": replay_mode,
        "diagnostics_only": True,
        "current_csv_path": str(current_path),
        "baseline_csv_path": str(baseline_path) if baseline_path is not None else None,
        "output_artifact_paths": {
            "summary_json_path": str(summary_json_path),
            "action_delta_csv_path": str(action_delta_csv_path),
            "publishability_delta_csv_path": str(publishability_delta_csv_path),
            "policy_reason_delta_csv_path": str(policy_reason_delta_csv_path),
            "row_deltas_csv_path": str(row_deltas_csv_path),
            "widened_row_attribution_csv_path": str(widened_row_attribution_csv_path),
            "widened_row_attribution_json_path": str(widened_row_attribution_json_path),
            "review_only_deltas_csv_path": str(review_only_deltas_csv_path),
        },
        "live_default_unchanged_confirmation": True,
        "publish_tree_created": False,
        "store_facing_csv_changed": False,
    }
    runtime_manifest_path.write_text(json.dumps(runtime_manifest, indent=2, sort_keys=True), encoding="utf-8")

    return PromotionPolicySliceReplayArtifacts(
        output_root=str(resolved_output_root),
        runtime_manifest_path=str(runtime_manifest_path),
        summary_json_path=str(summary_json_path),
        action_delta_csv_path=str(action_delta_csv_path),
        publishability_delta_csv_path=str(publishability_delta_csv_path),
        policy_reason_delta_csv_path=str(policy_reason_delta_csv_path),
        row_deltas_csv_path=str(row_deltas_csv_path),
        widened_row_attribution_csv_path=str(widened_row_attribution_csv_path),
        widened_row_attribution_json_path=str(widened_row_attribution_json_path),
        policy_reason_summary_csv_path=str(policy_reason_delta_csv_path),
        review_only_deltas_csv_path=str(review_only_deltas_csv_path),
        summary=summary,
        action_deltas=action_deltas,
        publishability_deltas=publishability_deltas,
        row_deltas=row_deltas,
        widened_row_attribution=widened_row_attribution,
        policy_reason_summary=policy_reason_summary,
        review_only_deltas=review_only_deltas,
    )


def build_policy_slice_replay_tables(
    *,
    current_frame: pd.DataFrame,
    baseline_frame: pd.DataFrame | None = None,
    replay_mode: str = REPLAY_MODE_HISTORICAL_ONLY,
) -> tuple[PromotionPolicySliceReplaySummary, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build replay summary and evidence tables without writing files.

    Purpose:
        Normalize persisted replay slices and compute row, policy-reason, and
        review-only deltas for tests and CLI artifact writing.

    Inputs:
        Current and optional baseline frames plus a governed replay mode.

    Outputs:
        Summary, row delta table, policy-reason delta table, and review-only
        delta table.

    Failure behaviour:
        Rejects unsupported replay modes. Historical-only mode may omit a
        baseline; all other modes fail loud without one.
    """

    if replay_mode not in REPLAY_MODE_CHOICES:
        raise ValueError(f"Unsupported policy slice replay mode: {replay_mode}")
    if replay_mode != REPLAY_MODE_HISTORICAL_ONLY and baseline_frame is None:
        raise GovernedReplayAttributionError(f"{replay_mode} replay mode requires baseline_frame")
    current = _normalize_replay_frame(current_frame, prefix="current")
    baseline = _normalize_replay_frame(baseline_frame, prefix="baseline") if baseline_frame is not None else None
    row_deltas = _build_row_deltas(current=current, baseline=baseline, replay_mode=replay_mode)
    action_deltas = _build_action_delta_table(row_deltas)
    publishability_deltas = _build_publishability_delta_table(row_deltas)
    policy_reason_summary = _build_policy_reason_delta(row_deltas=row_deltas)
    review_only_deltas = _build_review_only_deltas(
        current_frame=current_frame,
        baseline_frame=baseline_frame,
    )

    current_buy_order_count = int(current["current_buy_order_flag"].sum())
    current_publishable_count = int(current["current_publishable_flag"].sum())
    current_review_only_count = int(current["current_review_only_flag"].sum())
    baseline_buy_order_count = int(baseline["baseline_buy_order_flag"].sum()) if baseline is not None else 0
    baseline_publishable_count = int(baseline["baseline_publishable_flag"].sum()) if baseline is not None else 0
    baseline_review_only_count = int(baseline["baseline_review_only_flag"].sum()) if baseline is not None else 0
    buy_order_widened_rows = row_deltas[
        row_deltas["baseline_buy_order_flag"].eq(False) & row_deltas["current_buy_order_flag"].eq(True)
    ]

    summary = PromotionPolicySliceReplaySummary(
        replay_mode=replay_mode,
        current_row_count=int(len(current.index)),
        baseline_row_count=int(len(baseline.index)) if baseline is not None else 0,
        comparable_row_count=int(row_deltas["comparable_row_flag"].sum()),
        affected_row_count=int(row_deltas["affected_row_flag"].sum()),
        current_buy_order_row_count=current_buy_order_count,
        baseline_buy_order_row_count=baseline_buy_order_count,
        buy_order_row_delta=current_buy_order_count - baseline_buy_order_count,
        current_publishable_row_count=current_publishable_count,
        baseline_publishable_row_count=baseline_publishable_count,
        publishable_row_delta=current_publishable_count - baseline_publishable_count,
        current_review_only_row_count=current_review_only_count,
        baseline_review_only_row_count=baseline_review_only_count,
        review_only_row_delta=current_review_only_count - baseline_review_only_count,
        operator_action_deltas=_delta_dict(action_deltas, family="operator_action"),
        decision_recommendation_deltas=_delta_dict(action_deltas, family="decision_recommendation"),
        stage12_publishability_deltas=_delta_dict(publishability_deltas),
        rows_hit_by_policy_reason_count=int(current["current_policy_reason_active_flag"].sum()),
        units_removed_total=float(row_deltas["current_policy_units_removed"].sum()),
        capital_removed_total=float(row_deltas["current_policy_capital_at_risk_removed"].sum()),
        review_only_delta_row_count=int(len(review_only_deltas.index)),
        buy_order_widening_flag=bool((current_buy_order_count > baseline_buy_order_count) or not buy_order_widened_rows.empty),
        diagnostics_only=True,
    )
    return summary, row_deltas, policy_reason_summary, review_only_deltas


def _normalize_replay_frame(frame: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    """Return row-level replay evidence with normalized action classes.

    Purpose:
        Convert a persisted replay input into row-level governed action,
        publishability, order-unit, and order-value evidence.

    Required inputs:
        A replay DataFrame and a prefix identifying whether it is current or
        baseline evidence.

    Outputs:
        A normalized frame keyed by row_key with action classes and nullable
        governed order/removal fields.

    Assumptions:
        Technical forecast columns such as predicted units are not commercial
        action evidence and are intentionally ignored.

    Failure behavior:
        Duplicate row identities raise GovernedReplayAttributionError instead
        of being collapsed.
    """

    working = frame.copy()
    row_key = _row_key_series(working)
    _assert_unique_row_keys(row_key, prefix=prefix)
    decision_action = _first_present_text_series(
        working,
        ("decision_recommendation", "store_action", "operator_action_class"),
    ).str.strip()
    operator_action = _first_present_text_series(
        working,
        ("store_action", "operator_action_class", "decision_recommendation"),
    ).str.strip()
    decision_recommendation = _first_present_text_series(
        working,
        ("decision_recommendation", "store_action", "operator_action_class"),
    ).str.strip()
    suggested_units, suggested_units_available = _first_present_numeric_evidence(
        working,
        _GOVERNED_ORDER_UNIT_COLUMNS,
    )
    order_value, order_value_available = _first_present_numeric_evidence(
        working,
        _GOVERNED_ORDER_VALUE_COLUMNS,
    )
    review_reason = _first_present_text_series(
        working,
        ("review_reason", "primary_review_reason", "review_override_reason"),
    ).str.strip()
    publish_eligibility = _first_present_text_series(
        working,
        ("publish_eligibility_reason", "publish_eligibility_class"),
    ).str.strip()
    policy_reason = _first_present_text_series(
        working,
        ("policy_adjustment_reason", "row_change_reason_code", "primary_review_reason"),
    ).str.strip()
    policy_units_removed, policy_units_removed_available = _first_present_numeric_evidence(
        working,
        ("policy_units_removed",),
    )
    policy_capital_removed, policy_capital_removed_available = _first_present_numeric_evidence(
        working,
        ("policy_capital_at_risk_removed",),
    )

    review_reason_lower = review_reason.str.lower()
    operator_action_class = _normalize_operator_action_series(operator_action)
    decision_recommendation_class = _normalize_decision_recommendation_series(decision_recommendation)
    eligibility_lower = publish_eligibility.str.lower()
    blocked_by_review = review_reason_lower.ne("") & review_reason_lower.ne("no_review_override")
    buy_order_flag = operator_action_class.eq("BUY") | decision_recommendation_class.eq("ORDER")
    publishability_class = _stage12_publishability_class_series(
        operator_action_class=operator_action_class,
        decision_recommendation_class=decision_recommendation_class,
        publish_eligibility=publish_eligibility,
        explicit_review_flag=blocked_by_review,
    )
    review_only_flag = publishability_class.eq("review_only")
    publishable_flag = publishability_class.eq("publishable")
    policy_reason_active_flag = ~policy_reason.str.lower().isin(_NO_POLICY_REASON_VALUES)

    normalized = pd.DataFrame(
        {
            "row_key": row_key,
            f"{prefix}_row_present": True,
            f"{prefix}_decision_action": decision_action,
            f"{prefix}_operator_action_class": operator_action_class,
            f"{prefix}_decision_recommendation_class": decision_recommendation_class,
            f"{prefix}_suggested_order_units": suggested_units,
            f"{prefix}_suggested_order_units_available": suggested_units_available.astype(bool),
            f"{prefix}_order_value": order_value,
            f"{prefix}_order_value_available": order_value_available.astype(bool),
            f"{prefix}_buy_order_flag": buy_order_flag.astype(bool),
            f"{prefix}_publishable_flag": publishable_flag.astype(bool),
            f"{prefix}_stage12_publishability_class": publishability_class,
            f"{prefix}_review_only_flag": review_only_flag.astype(bool),
            f"{prefix}_policy_adjustment_reason": policy_reason,
            f"{prefix}_policy_reason_active_flag": policy_reason_active_flag.astype(bool),
            f"{prefix}_policy_units_removed": policy_units_removed,
            f"{prefix}_policy_units_removed_available": policy_units_removed_available.astype(bool),
            f"{prefix}_policy_capital_at_risk_removed": policy_capital_removed,
            f"{prefix}_policy_capital_at_risk_removed_available": policy_capital_removed_available.astype(bool),
        },
        index=working.index,
    )
    return normalized


def _build_row_deltas(
    *,
    current: pd.DataFrame,
    baseline: pd.DataFrame | None,
    replay_mode: str,
) -> pd.DataFrame:
    """Build one row-level comparison table from normalized replay frames.

    Purpose:
        Join current and baseline replay rows and resolve governed removal
        attribution from explicit policy columns or safe baseline-current
        commercial deltas.

    Required inputs:
        Normalized current evidence, optional normalized baseline evidence,
        and replay mode.

    Outputs:
        A row delta frame with action, publishability, unit, capital, and
        attribution-source columns.

    Assumptions:
        BUY/ORDER widening is action-class based only; quantity deltas do not
        create action widening.

    Failure behavior:
        Missing governed action or removal evidence raises
        GovernedReplayAttributionError.
    """

    if baseline is None:
        row_deltas = current.copy()
        row_deltas["baseline_row_present"] = False
        row_deltas["baseline_decision_action"] = ""
        row_deltas["baseline_operator_action_class"] = ""
        row_deltas["baseline_decision_recommendation_class"] = ""
        row_deltas["baseline_suggested_order_units"] = float("nan")
        row_deltas["baseline_suggested_order_units_available"] = False
        row_deltas["baseline_order_value"] = float("nan")
        row_deltas["baseline_order_value_available"] = False
        row_deltas["baseline_buy_order_flag"] = False
        row_deltas["baseline_publishable_flag"] = False
        row_deltas["baseline_stage12_publishability_class"] = "excluded"
        row_deltas["baseline_review_only_flag"] = False
        row_deltas["baseline_policy_adjustment_reason"] = ""
        row_deltas["baseline_policy_reason_active_flag"] = False
        row_deltas["baseline_policy_units_removed"] = float("nan")
        row_deltas["baseline_policy_units_removed_available"] = False
        row_deltas["baseline_policy_capital_at_risk_removed"] = float("nan")
        row_deltas["baseline_policy_capital_at_risk_removed_available"] = False
    else:
        row_deltas = baseline.merge(current, on="row_key", how="outer")

    for column_name in (
        "baseline_row_present",
        "current_row_present",
        "baseline_buy_order_flag",
        "current_buy_order_flag",
        "baseline_publishable_flag",
        "current_publishable_flag",
        "baseline_review_only_flag",
        "current_review_only_flag",
        "baseline_policy_reason_active_flag",
        "current_policy_reason_active_flag",
        "baseline_suggested_order_units_available",
        "current_suggested_order_units_available",
        "baseline_order_value_available",
        "current_order_value_available",
        "baseline_policy_units_removed_available",
        "current_policy_units_removed_available",
        "baseline_policy_capital_at_risk_removed_available",
        "current_policy_capital_at_risk_removed_available",
    ):
        row_deltas[column_name] = row_deltas.get(column_name, False).fillna(False).astype(bool)
    for column_name in ("baseline_stage12_publishability_class", "current_stage12_publishability_class"):
        row_deltas[column_name] = row_deltas.get(column_name, "excluded").fillna("excluded").astype(str)
    for column_name in (
        "baseline_decision_action",
        "current_decision_action",
        "baseline_operator_action_class",
        "current_operator_action_class",
        "baseline_decision_recommendation_class",
        "current_decision_recommendation_class",
        "baseline_policy_adjustment_reason",
        "current_policy_adjustment_reason",
    ):
        row_deltas[column_name] = row_deltas.get(column_name, "").fillna("").astype(str)
    for column_name in (
        "baseline_suggested_order_units",
        "current_suggested_order_units",
        "baseline_order_value",
        "current_order_value",
        "baseline_policy_units_removed",
        "current_policy_units_removed",
        "baseline_policy_capital_at_risk_removed",
        "current_policy_capital_at_risk_removed",
    ):
        row_deltas[column_name] = pd.to_numeric(row_deltas.get(column_name, float("nan")), errors="coerce")

    _assert_action_classes_available(row_deltas)

    row_deltas["comparable_row_flag"] = row_deltas["baseline_row_present"] & row_deltas["current_row_present"]
    units_delta_available = (
        row_deltas["baseline_suggested_order_units_available"]
        & row_deltas["current_suggested_order_units_available"]
        & row_deltas["comparable_row_flag"]
    )
    order_value_delta_available = (
        row_deltas["baseline_order_value_available"]
        & row_deltas["current_order_value_available"]
        & row_deltas["comparable_row_flag"]
    )
    row_deltas["suggested_order_units_delta"] = pd.NA
    row_deltas.loc[units_delta_available, "suggested_order_units_delta"] = (
        row_deltas["current_suggested_order_units"] - row_deltas["baseline_suggested_order_units"]
    )
    row_deltas["order_value_delta"] = pd.NA
    row_deltas.loc[order_value_delta_available, "order_value_delta"] = (
        row_deltas["current_order_value"] - row_deltas["baseline_order_value"]
    )
    row_deltas["publishable_delta"] = (
        row_deltas["current_publishable_flag"].astype(int) - row_deltas["baseline_publishable_flag"].astype(int)
    )
    row_deltas["review_only_delta"] = (
        row_deltas["current_review_only_flag"].astype(int) - row_deltas["baseline_review_only_flag"].astype(int)
    )
    row_deltas["buy_order_widened_flag"] = row_deltas["current_buy_order_flag"] & ~row_deltas["baseline_buy_order_flag"]
    row_deltas["affected_row_flag"] = (
        row_deltas["baseline_decision_action"].ne(row_deltas["current_decision_action"])
        | row_deltas["publishable_delta"].ne(0)
        | row_deltas["review_only_delta"].ne(0)
        | row_deltas["suggested_order_units_delta"].fillna(0.0).ne(0.0)
        | row_deltas["order_value_delta"].fillna(0.0).ne(0.0)
        | row_deltas["baseline_policy_adjustment_reason"].ne(row_deltas["current_policy_adjustment_reason"])
    )
    _resolve_removal_attribution(row_deltas, replay_mode=replay_mode)

    ordered_columns = (
        "row_key",
        "baseline_row_present",
        "current_row_present",
        "baseline_decision_action",
        "current_decision_action",
        "baseline_operator_action_class",
        "current_operator_action_class",
        "baseline_decision_recommendation_class",
        "current_decision_recommendation_class",
        "baseline_suggested_order_units",
        "current_suggested_order_units",
        "suggested_order_units_delta",
        "baseline_order_value",
        "current_order_value",
        "order_value_delta",
        "baseline_buy_order_flag",
        "current_buy_order_flag",
        "baseline_publishable_flag",
        "current_publishable_flag",
        "publishable_delta",
        "baseline_stage12_publishability_class",
        "current_stage12_publishability_class",
        "baseline_review_only_flag",
        "current_review_only_flag",
        "review_only_delta",
        "baseline_policy_adjustment_reason",
        "current_policy_adjustment_reason",
        "baseline_policy_reason_active_flag",
        "current_policy_reason_active_flag",
        "baseline_policy_units_removed",
        "baseline_policy_capital_at_risk_removed",
        "current_policy_units_removed",
        "current_policy_units_removed_source",
        "current_policy_capital_at_risk_removed",
        "current_policy_capital_at_risk_removed_source",
        "buy_order_widened_flag",
        "affected_row_flag",
        "comparable_row_flag",
    )
    return row_deltas.loc[:, ordered_columns].sort_values("row_key").reset_index(drop=True)


def _build_action_delta_table(row_deltas: pd.DataFrame) -> pd.DataFrame:
    """Aggregate BUY/HOLD/REVIEW and ORDER/HOLD/REVIEW deltas."""

    rows: list[dict[str, object]] = []
    for family, classes, baseline_column, current_column in (
        (
            "operator_action",
            _OPERATOR_ACTION_CLASSES,
            "baseline_operator_action_class",
            "current_operator_action_class",
        ),
        (
            "decision_recommendation",
            _DECISION_RECOMMENDATION_CLASSES,
            "baseline_decision_recommendation_class",
            "current_decision_recommendation_class",
        ),
    ):
        for action_class in classes:
            baseline_count = int(row_deltas[baseline_column].astype(str).eq(action_class).sum())
            current_count = int(row_deltas[current_column].astype(str).eq(action_class).sum())
            rows.append(
                {
                    "action_family": family,
                    "action_class": action_class,
                    "baseline_count": baseline_count,
                    "current_count": current_count,
                    "delta_count": current_count - baseline_count,
                }
            )
    return pd.DataFrame(rows)


def _build_publishability_delta_table(row_deltas: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Stage 12 publishable, review-only, and excluded deltas."""

    rows: list[dict[str, object]] = []
    for publishability_class in _STAGE12_PUBLISHABILITY_CLASSES:
        baseline_count = int(
            row_deltas["baseline_stage12_publishability_class"].astype(str).eq(publishability_class).sum()
        )
        current_count = int(
            row_deltas["current_stage12_publishability_class"].astype(str).eq(publishability_class).sum()
        )
        rows.append(
            {
                "stage12_publishability_class": publishability_class,
                "baseline_count": baseline_count,
                "current_count": current_count,
                "delta_count": current_count - baseline_count,
            }
        )
    return pd.DataFrame(rows)


def _build_policy_reason_delta(*, row_deltas: pd.DataFrame) -> pd.DataFrame:
    """Aggregate baseline-vs-current policy reason hit and removal deltas.

    Purpose:
        Summarize attributable policy reason changes using the same resolved
        row-level removal values that feed the replay summary.

    Required inputs:
        A row delta frame produced by _build_row_deltas.

    Outputs:
        One row per policy reason with baseline/current counts and removal
        deltas.

    Assumptions:
        Removal attribution has already failed loud if explicit policy-removal
        fields or safe baseline-current commercial deltas were unavailable.

    Failure behavior:
        Propagates missing required row-delta columns as normal KeyError because
        such a frame is not a valid replay table.
    """

    current_summary = _policy_reason_aggregate(row_deltas, prefix="current")
    baseline_summary = _policy_reason_aggregate(row_deltas, prefix="baseline")
    merged = baseline_summary.merge(current_summary, on="policy_adjustment_reason", how="outer")
    for column_name in (
        "baseline_row_count",
        "baseline_units_removed_total",
        "baseline_capital_removed_total",
        "baseline_publishable_row_count",
        "baseline_review_only_row_count",
        "current_row_count",
        "current_units_removed_total",
        "current_capital_removed_total",
        "current_publishable_row_count",
        "current_review_only_row_count",
    ):
        merged[column_name] = pd.to_numeric(merged.get(column_name, 0.0), errors="coerce").fillna(0.0)
    if merged.empty:
        return merged.assign(
            row_count_delta=pd.Series(dtype="float64"),
            units_removed_delta=pd.Series(dtype="float64"),
            capital_removed_delta=pd.Series(dtype="float64"),
        )
    merged["row_count_delta"] = merged["current_row_count"] - merged["baseline_row_count"]
    merged["units_removed_delta"] = merged["current_units_removed_total"] - merged["baseline_units_removed_total"]
    merged["capital_removed_delta"] = merged["current_capital_removed_total"] - merged["baseline_capital_removed_total"]
    return merged.sort_values("policy_adjustment_reason").reset_index(drop=True)


def _policy_reason_aggregate(frame: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    """Summarize active policy reasons for one side of a row-delta frame.

    Purpose:
        Convert row-level policy reason hits into compact aggregate evidence.

    Required inputs:
        The row-delta frame and a prefix of either current or baseline.

    Outputs:
        A policy-reason aggregate table for the requested side.

    Assumptions:
        The frame contains normalized policy reason flags and resolved removal
        totals for the requested prefix.

    Failure behavior:
        Returns an empty typed table when no active policy reasons exist.
    """

    active = frame[frame[f"{prefix}_policy_reason_active_flag"]].copy()
    output_columns = (
        "policy_adjustment_reason",
        f"{prefix}_row_count",
        f"{prefix}_units_removed_total",
        f"{prefix}_capital_removed_total",
        f"{prefix}_publishable_row_count",
        f"{prefix}_review_only_row_count",
    )
    if active.empty:
        return pd.DataFrame(columns=output_columns)
    grouped = active.groupby(f"{prefix}_policy_adjustment_reason", dropna=False).agg(
        **{
            f"{prefix}_row_count": ("row_key", "count"),
            f"{prefix}_units_removed_total": (f"{prefix}_policy_units_removed", "sum"),
            f"{prefix}_capital_removed_total": (f"{prefix}_policy_capital_at_risk_removed", "sum"),
            f"{prefix}_publishable_row_count": (f"{prefix}_publishable_flag", "sum"),
            f"{prefix}_review_only_row_count": (f"{prefix}_review_only_flag", "sum"),
        }
    )
    return grouped.reset_index().rename(columns={f"{prefix}_policy_adjustment_reason": "policy_adjustment_reason"})


def _build_review_only_deltas(
    *,
    current_frame: pd.DataFrame,
    baseline_frame: pd.DataFrame | None,
) -> pd.DataFrame:
    """Return cell-level deltas for shared, added, and removed review-only columns.

    Purpose:
        Surface analyst-only evidence changes, including newly added or removed
        review-only feature families.

    Required inputs:
        Current and optional baseline replay input frames.

    Outputs:
        A cell-level delta table with row key, column name, baseline value, and
        current value.

    Assumptions:
        Only columns registered as review-only evidence are compared.

    Failure behavior:
        Duplicate row identities raise GovernedReplayAttributionError; missing
        baseline in historical-only mode returns an empty delta table.
    """

    if baseline_frame is None:
        return pd.DataFrame(columns=("row_key", "column_name", "baseline_value", "current_value"))
    current = current_frame.copy()
    baseline = baseline_frame.copy()
    current["row_key"] = _row_key_series(current)
    baseline["row_key"] = _row_key_series(baseline)
    _assert_unique_row_keys(current["row_key"], prefix="current review-only")
    _assert_unique_row_keys(baseline["row_key"], prefix="baseline review-only")
    comparable_columns = [
        column_name
        for column_name in _REVIEW_ONLY_COLUMNS
        if column_name in current.columns or column_name in baseline.columns
    ]
    if not comparable_columns:
        return pd.DataFrame(columns=("row_key", "column_name", "baseline_value", "current_value"))
    for column_name in comparable_columns:
        if column_name not in current.columns:
            current[column_name] = pd.NA
        if column_name not in baseline.columns:
            baseline[column_name] = pd.NA
    merged = baseline[["row_key", *comparable_columns]].merge(
        current[["row_key", *comparable_columns]],
        on="row_key",
        how="outer",
        suffixes=("_baseline", "_current"),
    )
    rows: list[dict[str, object]] = []
    for _, merged_row in merged.iterrows():
        for column_name in comparable_columns:
            baseline_value = merged_row.get(f"{column_name}_baseline")
            current_value = merged_row.get(f"{column_name}_current")
            if _values_equal(baseline_value, current_value):
                continue
            rows.append(
                {
                    "row_key": str(merged_row["row_key"]),
                    "column_name": column_name,
                    "baseline_value": baseline_value,
                    "current_value": current_value,
                }
            )
    return pd.DataFrame(rows, columns=("row_key", "column_name", "baseline_value", "current_value"))


def _build_widened_row_attribution(
    *,
    row_deltas: pd.DataFrame,
    current_frame: pd.DataFrame,
    baseline_frame: pd.DataFrame | None,
) -> pd.DataFrame:
    """Return contextual evidence for rows widened into BUY/ORDER actions."""

    widened = row_deltas.loc[row_deltas["buy_order_widened_flag"].astype(bool)].copy()
    if widened.empty:
        return pd.DataFrame(columns=WIDENED_ROW_ATTRIBUTION_COLUMNS)
    current_context = _build_widening_context_frame(current_frame, prefix="current")
    if baseline_frame is None:
        baseline_context = pd.DataFrame({"row_key": widened["row_key"].astype(str)})
        baseline_context["baseline_review_reason"] = ""
    else:
        baseline_context = _build_widening_context_frame(baseline_frame, prefix="baseline")
    joined = widened.merge(baseline_context, on="row_key", how="left").merge(current_context, on="row_key", how="left")
    missing_evidence = joined.apply(_widened_row_missing_evidence, axis=1)
    out = pd.DataFrame(
        {
            "row_key": joined["row_key"].astype(str),
            "baseline_decision_action": joined["baseline_decision_action"].astype(str),
            "baseline_review_reason": joined.get("baseline_review_reason", "").fillna("").astype(str),
            "baseline_policy_adjustment_reason": joined["baseline_policy_adjustment_reason"].astype(str),
            "current_decision_action": joined["current_decision_action"].astype(str),
            "current_review_reason": joined.get("current_review_reason", "").fillna("").astype(str),
            "current_policy_adjustment_reason": joined["current_policy_adjustment_reason"].astype(str),
            "baseline_suggested_order_units": joined["baseline_suggested_order_units"],
            "current_suggested_order_units": joined["current_suggested_order_units"],
            "suggested_order_units_delta": joined["suggested_order_units_delta"],
            "baseline_order_value": joined["baseline_order_value"],
            "current_order_value": joined["current_order_value"],
            "order_value_delta": joined["order_value_delta"],
            "trust_floor_state": _context_state_series(
                joined["current_trust_floor_value"],
                joined["current_trust_floor_available"],
                positive_label="trust_floor_signal_present",
                zero_label="trust_floor_signal_zero",
                missing_label="missing_governed_trust_floor_evidence",
            ),
            "speculative_capital_state": _context_state_series(
                joined["current_speculative_capital_value"],
                joined["current_speculative_capital_available"],
                positive_label="speculative_capital_signal_present",
                zero_label="no_speculative_capital_signal",
                missing_label="missing_speculative_capital_evidence",
            ),
            "same_discount_evidence": _context_state_series(
                joined["current_same_discount_value"],
                joined["current_same_discount_available"],
                positive_label="same_discount_history_present",
                zero_label="same_discount_history_absent",
                missing_label="missing_same_discount_evidence",
            ),
            "no_history_sparse_state": _context_state_series(
                joined["current_no_history_sparse_value"],
                joined["current_no_history_sparse_available"],
                positive_label="no_history_or_sparse_signal_present",
                zero_label="history_and_density_supported",
                missing_label="missing_no_history_sparse_evidence",
            ),
            "equilibrium_signal_state": _context_state_series(
                joined["current_equilibrium_value"],
                joined["current_equilibrium_available"],
                positive_label="equilibrium_signal_present",
                zero_label="equilibrium_signal_not_present",
                missing_label="missing_equilibrium_signal_evidence",
            ),
            "missing_evidence": missing_evidence,
            "diagnostics_only": True,
        },
        columns=WIDENED_ROW_ATTRIBUTION_COLUMNS,
    )
    return out.sort_values("row_key").reset_index(drop=True)


def _build_widening_context_frame(frame: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    """Extract replay context columns used only for widened-row attribution."""

    working = frame.copy()
    working["row_key"] = _row_key_series(working)
    _assert_unique_row_keys(working["row_key"], prefix=f"{prefix} widened-row context")
    trust_value, trust_available = _first_present_numeric_evidence(working, _TRUST_FLOOR_CONTEXT_COLUMNS)
    speculative_value, speculative_available = _first_present_numeric_evidence(
        working,
        _SPECULATIVE_CAPITAL_CONTEXT_COLUMNS,
    )
    same_discount_value, same_discount_available = _first_present_numeric_evidence(
        working,
        _SAME_DISCOUNT_CONTEXT_COLUMNS,
    )
    no_history_sparse_value, no_history_sparse_available = _max_present_numeric_evidence(
        working,
        _NO_HISTORY_SPARSE_CONTEXT_COLUMNS,
    )
    equilibrium_value, equilibrium_available = _max_present_numeric_evidence(
        working,
        _EQUILIBRIUM_CONTEXT_COLUMNS,
    )
    review_reason = _first_present_text_series(
        working,
        ("review_reason", "primary_review_reason", "review_override_reason"),
    ).str.strip()
    return pd.DataFrame(
        {
            "row_key": working["row_key"].astype(str),
            f"{prefix}_review_reason": review_reason,
            f"{prefix}_trust_floor_value": trust_value,
            f"{prefix}_trust_floor_available": trust_available.astype(bool),
            f"{prefix}_speculative_capital_value": speculative_value,
            f"{prefix}_speculative_capital_available": speculative_available.astype(bool),
            f"{prefix}_same_discount_value": same_discount_value,
            f"{prefix}_same_discount_available": same_discount_available.astype(bool),
            f"{prefix}_no_history_sparse_value": no_history_sparse_value,
            f"{prefix}_no_history_sparse_available": no_history_sparse_available.astype(bool),
            f"{prefix}_equilibrium_value": equilibrium_value,
            f"{prefix}_equilibrium_available": equilibrium_available.astype(bool),
        }
    )


def _context_state_series(
    value: pd.Series,
    available: pd.Series,
    *,
    positive_label: str,
    zero_label: str,
    missing_label: str,
) -> pd.Series:
    """Label contextual evidence without converting missing values into zeros."""

    numeric_value = pd.to_numeric(value, errors="coerce")
    available_flag = available.fillna(False).astype(bool)
    out = pd.Series(missing_label, index=value.index, dtype="object")
    out.loc[available_flag & numeric_value.le(0.0)] = zero_label
    out.loc[available_flag & numeric_value.gt(0.0)] = positive_label
    return out


def _widened_row_missing_evidence(row: pd.Series) -> str:
    """Return semicolon-separated context gaps for a widened replay row."""

    missing: list[str] = []
    if not bool(row.get("current_trust_floor_available", False)):
        missing.append("trust_floor_state")
    if not bool(row.get("current_speculative_capital_available", False)):
        missing.append("speculative_capital_state")
    if not bool(row.get("current_same_discount_available", False)):
        missing.append("same_discount_evidence")
    if not bool(row.get("current_no_history_sparse_available", False)):
        missing.append("no_history_sparse_state")
    if not bool(row.get("current_equilibrium_available", False)):
        missing.append("equilibrium_signal_state")
    if pd.isna(row.get("suggested_order_units_delta")):
        missing.append("suggested_order_units_delta")
    if pd.isna(row.get("order_value_delta")):
        missing.append("order_value_delta")
    return ";".join(missing)


def _assert_unique_row_keys(row_key: pd.Series, *, prefix: str) -> None:
    """Fail loud when replay row identity is not unique.

    Purpose:
        Prevent governed replay attribution from silently dropping rows through
        duplicate-key collapse.

    Required inputs:
        A resolved row-key series and a prefix naming the input side.

    Outputs:
        None when keys are unique.

    Assumptions:
        The caller has already resolved row identity using promotion_row_key or
        deterministic row-grain fallback.

    Failure behavior:
        Raises GovernedReplayAttributionError with duplicate key context.
    """

    duplicate_keys = row_key[row_key.duplicated(keep=False)].astype(str).unique().tolist()
    if duplicate_keys:
        preview = ", ".join(duplicate_keys[:5])
        raise GovernedReplayAttributionError(f"Duplicate replay row_key values in {prefix}: {preview}")


def _assert_action_classes_available(row_deltas: pd.DataFrame) -> None:
    """Fail loud when governed action classes cannot be inferred from action fields.

    Purpose:
        Ensure action deltas and BUY/ORDER widening are based on governed
        action text, not technical forecasts or quantities.

    Required inputs:
        Row-delta frame containing current/baseline action class columns.

    Outputs:
        None when every present row has an operator or decision action class.

    Assumptions:
        Missing rows from an outer comparison are allowed; present rows must
        carry governed action evidence.

    Failure behavior:
        Raises GovernedReplayAttributionError with row-key context.
    """

    for prefix in ("baseline", "current"):
        present = row_deltas[f"{prefix}_row_present"]
        missing = (
            present
            & row_deltas[f"{prefix}_operator_action_class"].eq("")
            & row_deltas[f"{prefix}_decision_recommendation_class"].eq("")
        )
        if missing.any():
            preview = ", ".join(row_deltas.loc[missing, "row_key"].astype(str).head(5).tolist())
            raise GovernedReplayAttributionError(
                f"Governed replay action unavailable for {prefix} rows: {preview}"
            )


def _resolve_removal_attribution(row_deltas: pd.DataFrame, *, replay_mode: str) -> None:
    """Resolve units and capital removed from explicit or comparable governed evidence.

    Purpose:
        Populate effective current removal fields without silently defaulting
        missing commercial evidence to zero.

    Required inputs:
        A mutable row-delta frame and replay mode.

    Outputs:
        Adds effective current policy removal values and source labels in place.

    Assumptions:
        Explicit policy-removal fields take precedence; otherwise comparable
        baseline-current governed order units/value fields are safe to use.

    Failure behavior:
        Raises GovernedReplayAttributionError when affected or policy-hit rows
        lack both explicit and derived removal evidence.
    """

    explicit_units = row_deltas["current_policy_units_removed_available"]
    explicit_capital = row_deltas["current_policy_capital_at_risk_removed_available"]
    comparable_units = row_deltas["suggested_order_units_delta"].notna()
    comparable_capital = row_deltas["order_value_delta"].notna()
    requires_removal = row_deltas["current_policy_reason_active_flag"] | row_deltas["affected_row_flag"]
    if replay_mode == REPLAY_MODE_HISTORICAL_ONLY:
        requires_removal = row_deltas["current_policy_reason_active_flag"]

    missing_units = requires_removal & ~explicit_units & ~comparable_units
    if missing_units.any():
        preview = ", ".join(row_deltas.loc[missing_units, "row_key"].astype(str).head(5).tolist())
        raise GovernedReplayAttributionError(
            f"Governed units removed unavailable; provide policy_units_removed or comparable governed order units for rows: {preview}"
        )
    missing_capital = requires_removal & ~explicit_capital & ~comparable_capital
    if missing_capital.any():
        preview = ", ".join(row_deltas.loc[missing_capital, "row_key"].astype(str).head(5).tolist())
        raise GovernedReplayAttributionError(
            "Governed capital removed unavailable; provide policy_capital_at_risk_removed or comparable governed order value "
            f"for rows: {preview}"
        )

    derived_units_removed = (-pd.to_numeric(row_deltas["suggested_order_units_delta"], errors="coerce")).clip(lower=0.0)
    derived_capital_removed = (-pd.to_numeric(row_deltas["order_value_delta"], errors="coerce")).clip(lower=0.0)
    explicit_units_removed = row_deltas["current_policy_units_removed"].clip(lower=0.0)
    explicit_capital_removed = row_deltas["current_policy_capital_at_risk_removed"].clip(lower=0.0)
    row_deltas["current_policy_units_removed"] = 0.0
    row_deltas["current_policy_units_removed_source"] = "none"
    row_deltas.loc[comparable_units, "current_policy_units_removed"] = derived_units_removed.loc[comparable_units]
    row_deltas.loc[comparable_units, "current_policy_units_removed_source"] = "baseline_current_order_units_delta"
    row_deltas.loc[explicit_units, "current_policy_units_removed"] = explicit_units_removed.loc[explicit_units]
    row_deltas.loc[explicit_units, "current_policy_units_removed_source"] = "policy_units_removed"

    row_deltas["current_policy_capital_at_risk_removed"] = 0.0
    row_deltas["current_policy_capital_at_risk_removed_source"] = "none"
    row_deltas.loc[comparable_capital, "current_policy_capital_at_risk_removed"] = derived_capital_removed.loc[
        comparable_capital
    ]
    row_deltas.loc[
        comparable_capital,
        "current_policy_capital_at_risk_removed_source",
    ] = "baseline_current_order_value_delta"
    row_deltas.loc[explicit_capital, "current_policy_capital_at_risk_removed"] = explicit_capital_removed.loc[
        explicit_capital
    ]
    row_deltas.loc[explicit_capital, "current_policy_capital_at_risk_removed_source"] = (
        "policy_capital_at_risk_removed"
    )


def _row_key_series(frame: pd.DataFrame) -> pd.Series:
    """Resolve stable replay row identity from promotion row keys or row grain."""

    if "promotion_row_key" in frame.columns:
        row_key = frame["promotion_row_key"].fillna("").astype(str).str.strip()
        missing_key = row_key.eq("")
        if not missing_key.any():
            return row_key
    else:
        row_key = pd.Series("", index=frame.index, dtype="object")
        missing_key = pd.Series(True, index=frame.index, dtype=bool)

    identity_columns = [
        column_name
        for column_name in ("store_number", "sku_number", "promotion_start_date", "promotion_end_date")
        if column_name in frame.columns
    ]
    if len(identity_columns) >= 2:
        fallback_key = frame[identity_columns].fillna("").astype(str).agg("|".join, axis=1)
    else:
        fallback_key = pd.Series([f"row_index|{index_value}" for index_value in frame.index], index=frame.index)
    row_key.loc[missing_key] = fallback_key.loc[missing_key]
    return row_key.astype(str)


def _first_present_text_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    """Return first non-empty text value from the available column list."""

    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series("", index=frame.index, dtype="object")
    candidate_frame = frame[present_columns].fillna("").astype(str).replace("", pd.NA)
    return candidate_frame.bfill(axis=1).iloc[:, 0].fillna("")


def _first_present_numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    """Return first numeric value from the available column list."""

    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    candidate_frame = frame[present_columns].apply(pd.to_numeric, errors="coerce")
    return candidate_frame.bfill(axis=1).iloc[:, 0]


def _first_present_numeric_evidence(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
) -> tuple[pd.Series, pd.Series]:
    """Return first numeric governed value plus row-level availability.

    Purpose:
        Preserve the difference between genuine zero and missing governed
        commercial evidence.

    Required inputs:
        A replay input frame and ordered candidate column names.

    Outputs:
        Numeric value series and a boolean availability series.

    Assumptions:
        The caller supplies only governed commercial columns, never technical
        forecast proxies.

    Failure behavior:
        Missing candidate columns produce all-NaN values with availability
        false; callers decide whether that is allowed for their replay mode.
    """

    values = _first_present_numeric_series(frame, column_names)
    return values, values.notna()


def _max_present_numeric_evidence(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
) -> tuple[pd.Series, pd.Series]:
    """Return max governed numeric evidence plus row-level availability.

    Purpose:
        Preserve additive analyst context where multiple governed columns can
        independently indicate the same state, such as sparse history or local
        equilibrium pressure.

    Required inputs:
        Replay frame and ordered candidate governed numeric columns.

    Outputs:
        Max numeric signal across present columns and a boolean availability
        series stating whether any governed evidence column was present.

    Failure behavior:
        Missing candidate columns produce all-NaN values with availability
        false so callers can surface the absence explicitly.
    """

    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return (
            pd.Series(float("nan"), index=frame.index, dtype="float64"),
            pd.Series(False, index=frame.index, dtype="bool"),
        )
    candidate_frame = frame[present_columns].apply(pd.to_numeric, errors="coerce")
    values = candidate_frame.max(axis=1, skipna=True)
    return values, candidate_frame.notna().any(axis=1)


def _values_equal(left_value: object, right_value: object) -> bool:
    """Compare replay cell values while treating paired nulls as equal."""

    if pd.isna(left_value) and pd.isna(right_value):
        return True
    return str(left_value) == str(right_value)


def _normalize_operator_action_series(action: pd.Series) -> pd.Series:
    """Map governed store-facing action text to BUY/HOLD/DO NOT BUY/REVIEW.

    Purpose:
        Normalize action labels without using order quantities or forecasts.

    Required inputs:
        A text series from governed action columns.

    Outputs:
        Canonical operator action classes, or blank when unavailable.

    Assumptions:
        Quantity alone cannot create a BUY action.

    Failure behavior:
        Unknown labels stay blank and are rejected by the row-delta validator
        when the row is present.
    """

    normalized = action.fillna("").astype(str).str.strip().str.upper().str.replace("_", " ", regex=False)
    output = pd.Series("", index=action.index, dtype="object")
    output.loc[
        normalized.isin(
            {
                "BUY",
                "BUY NOW",
                "ORDER",
                "PUBLISH",
                "RECOMMEND ORDER",
                "AUTO ORDER",
                "ACTION PUBLISH NOW",
            }
        )
    ] = "BUY"
    output.loc[normalized.isin({"HOLD", "HOLD MONITOR", "WATCH", "MONITOR", "ACTION MONITOR"})] = "HOLD"
    output.loc[normalized.isin({"DO NOT BUY", "DO NOT ORDER", "NO BUY"})] = "DO NOT BUY"
    output.loc[normalized.str.contains("REVIEW", regex=False)] = "REVIEW"
    return output


def _normalize_decision_recommendation_series(action: pd.Series) -> pd.Series:
    """Map governed decision text to ORDER/HOLD/DO_NOT_ORDER/REVIEW.

    Purpose:
        Normalize decision labels without quantity-based action inference.

    Required inputs:
        A text series from governed recommendation/action columns.

    Outputs:
        Canonical decision recommendation classes, or blank when unavailable.

    Assumptions:
        Positive units or predictions cannot create ORDER.

    Failure behavior:
        Unknown labels stay blank and are rejected by the row-delta validator
        when no alternate governed action class exists.
    """

    normalized = action.fillna("").astype(str).str.strip().str.upper().str.replace(" ", "_", regex=False)
    output = pd.Series("", index=action.index, dtype="object")
    output.loc[
        normalized.isin(
            {
                "ORDER",
                "BUY",
                "BUY_NOW",
                "PUBLISH",
                "RECOMMEND_ORDER",
                "AUTO_ORDER",
                "ACTION_PUBLISH_NOW",
            }
        )
    ] = "ORDER"
    output.loc[normalized.isin({"HOLD", "HOLD_MONITOR", "WATCH", "MONITOR", "ACTION_MONITOR"})] = "HOLD"
    output.loc[normalized.isin({"DO_NOT_BUY", "DO_NOT_ORDER", "NO_BUY"})] = "DO_NOT_ORDER"
    output.loc[normalized.str.contains("REVIEW", regex=False)] = "REVIEW"
    return output


def _stage12_publishability_class_series(
    *,
    operator_action_class: pd.Series,
    decision_recommendation_class: pd.Series,
    publish_eligibility: pd.Series,
    explicit_review_flag: pd.Series,
) -> pd.Series:
    """Classify rows into governed Stage 12 publishability buckets.

    Purpose:
        Preserve publishable/review-only/excluded distinctions from governed
        action and publishability evidence without using quantities.

    Required inputs:
        Canonical operator and decision action classes, raw publish eligibility
        text, and an explicit review-reason flag.

    Outputs:
        Stage 12 class values: publishable, review_only, or excluded.

    Assumptions:
        Plain excluded values remain excluded; review-only requires explicit
        review action/reason/eligibility evidence.

    Failure behavior:
        Missing publishability text falls back only to governed action class:
        BUY/ORDER becomes publishable, REVIEW becomes review_only, and all
        other actions remain excluded.
    """

    eligibility_lower = publish_eligibility.fillna("").astype(str).str.strip().str.lower()
    buy_order_flag = operator_action_class.eq("BUY") | decision_recommendation_class.eq("ORDER")
    action_review_flag = operator_action_class.eq("REVIEW") | decision_recommendation_class.eq("REVIEW")
    eligibility_review_flag = eligibility_lower.isin({"review_only", "manual_review", "review_required"}) | eligibility_lower.str.contains(
        "review",
        regex=False,
    )
    eligibility_publishable_flag = eligibility_lower.isin({"publishable", "eligible", "ready_to_publish"}) | (
        eligibility_lower.str.contains("publish", regex=False)
        & ~eligibility_lower.str.contains("not_publish", regex=False)
        & ~eligibility_lower.str.contains("review", regex=False)
        & ~eligibility_lower.str.startswith("excluded")
    )

    output = pd.Series("excluded", index=publish_eligibility.index, dtype="object")
    output.loc[buy_order_flag & (eligibility_lower.eq("") | eligibility_publishable_flag)] = "publishable"
    output.loc[action_review_flag | explicit_review_flag.astype(bool) | eligibility_review_flag] = "review_only"
    return output


def _delta_dict(delta_frame: pd.DataFrame, *, family: str | None = None) -> dict[str, int]:
    """Convert an action or publishability delta table into a JSON summary map."""

    source = delta_frame
    key_column = "stage12_publishability_class"
    if family is not None:
        source = source[source["action_family"].astype(str).eq(family)]
        key_column = "action_class"
    return {
        str(row[key_column]): int(row["delta_count"])
        for row in source.to_dict(orient="records")
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run diagnostics-only promotions policy slice replay over persisted CSV slices."
    )
    parser.add_argument("--current-csv-path", required=True)
    parser.add_argument("--baseline-csv-path")
    parser.add_argument("--output-root")
    parser.add_argument("--run-id", default=datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--replay-mode", choices=REPLAY_MODE_CHOICES, default=REPLAY_MODE_HISTORICAL_ONLY)
    return parser


if __name__ == "__main__":
    main()