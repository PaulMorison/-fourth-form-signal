from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Sequence

import pandas as pd

from runtime.promotions.input_source_provenance import (
    add_provenance_columns,
    certification_failed,
)
from runtime.promotions.run_promotions_model_vs_actual_review import (
    LOW_SELL_THROUGH_THRESHOLD,
    MATERIAL_ACTUAL_UNITS,
    MATERIAL_CAPITAL_LEFT,
    MATERIAL_UNIT_DELTA,
    SHADOW_POLICY_COLUMNS,
    STRONG_SELL_THROUGH_THRESHOLD,
    build_promotions_model_vs_actual_review,
)
from surfaces.promotions.reporting.store_prediction_download_builder import (
    STORE_FACING_OUTPUT_COLUMNS,
)


REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    "model_vs_actual_summary.csv",
    "model_vs_actual_by_action_label.csv",
    "model_vs_actual_by_demand_label.csv",
    "model_vs_actual_by_department.csv",
    "model_vs_actual_top_missed_demand.csv",
    "model_vs_actual_top_capital_drag.csv",
    "model_vs_actual_report_cleanup_issues.csv",
    "model_vs_actual_decision_memo.md",
)

SIMPLIFIED_OPERATOR_FIELDS: tuple[str, ...] = (
    "operator_decision",
    "operator_action",
    "order_units",
    "reason_short",
    "risk_flag",
    "review_flag",
    "audit_notes",
)

NO_PRIOR_OR_WEAK_EVIDENCE_TOKENS: tuple[str, ...] = (
    "no_prior",
    "never_sold",
    "no_demand",
    "low_nonzero",
    "sparse_history",
    "weak",
)

REVIEW_TOKENS: tuple[str, ...] = (
    "review",
    "borderline",
)

NO_BUY_TOKENS: tuple[str, ...] = (
    "no_auto_buy",
    "do_not_buy",
    "do_not_order",
    "hold_stock",
    "reduce_holding",
    "no_demand",
    "never_sold",
    "no_prior",
)

BUY_TOKENS: tuple[str, ...] = (
    "buy",
    "protect_availability",
    "order",
)

FIX_PRIORITY_BY_ISSUE_TYPE: dict[str, int] = {
    "BUY_OR_ORDER_TEXT_WITH_ZERO_ORDER_UNITS": 1,
    "MULTIPLE_ACTION_COLUMNS_CONFLICT": 2,
    "LOW_SOH_OR_FLOOR_RISK_WITH_MATERIAL_DEMAND_NO_REVIEW_ACTION": 3,
    "NO_PRIOR_PROMO_EVIDENCE_WITH_MATERIAL_ACTUAL_UNITS": 3,
    "NO_DEMAND_WITH_MATERIAL_ACTUAL_UNITS": 3,
    "SHADOW_FIELDS_VISIBLE_IN_OPERATOR_REPORT": 4,
    "CAPITAL_DRAG_HIGH_WITH_STRONG_SELL_THROUGH": 5,
}


class PromotionsModelReliabilityNextPassError(RuntimeError):
    """Raised when the governed next-pass diagnostics cannot continue safely."""


@dataclass(frozen=True)
class PromotionsModelReliabilityNextPassArtifacts:
    report_contract_cleanup_plan_csv_path: str
    report_contract_cleanup_summary_csv_path: str
    report_contract_cleanup_memo_md_path: str
    action_layer_recalibration_rows_csv_path: str
    action_layer_recalibration_summary_csv_path: str
    action_layer_recalibration_memo_md_path: str
    no_prior_demand_surprise_rows_csv_path: str
    no_prior_demand_surprise_summary_csv_path: str
    model_reliability_next_step_memo_md_path: str


@dataclass(frozen=True)
class PromotionsModelReliabilityNextPassResult:
    review_rows_frame: pd.DataFrame
    review_summary_frame: pd.DataFrame
    cleanup_plan_frame: pd.DataFrame
    cleanup_issue_rows_frame: pd.DataFrame
    cleanup_summary_frame: pd.DataFrame
    cleanup_memo_markdown: str
    action_layer_recalibration_rows_frame: pd.DataFrame
    action_layer_recalibration_summary_frame: pd.DataFrame
    action_layer_recalibration_memo_markdown: str
    no_prior_demand_surprise_rows_frame: pd.DataFrame
    no_prior_demand_surprise_summary_frame: pd.DataFrame
    model_reliability_next_step_memo_markdown: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsModelReliabilityNextPassError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsModelReliabilityNextPassError(
            f"Manifest must be a JSON object: {path}"
        )
    return payload


def _normalize_token(value: object) -> str:
    return re.sub(r"\s+", "_", str(value).strip().casefold())


def _text_implies_order(value: object) -> bool:
    token = _normalize_token(value)
    if not token:
        return False
    if any(blocked in token for blocked in ("do_not", "no_order", "no_auto_buy", "suppressed")):
        return False
    return any(keyword in token for keyword in ("buy", "order", "allocate", "recommended"))


def _label_contains_no_prior(value: object) -> bool:
    token = _normalize_token(value)
    return "no_prior" in token or "never_sold" in token


def _label_contains_no_demand(value: object) -> bool:
    token = _normalize_token(value)
    return "no_demand" in token


def _label_contains_weak_or_no_prior(value: object) -> bool:
    token = _normalize_token(value)
    return any(keyword in token for keyword in NO_PRIOR_OR_WEAK_EVIDENCE_TOKENS)


def _label_contains_low_soh_or_floor_risk(*values: object) -> bool:
    for value in values:
        token = _normalize_token(value)
        if not token:
            continue
        if "low_soh" in token:
            return True
        if "floor" in token:
            return True
        if "availability" in token:
            return True
        if token.startswith("below_") and "risk" in token:
            return True
    return False


def _is_review_action(row: pd.Series) -> bool:
    action_token = _normalize_token(row["store_action_label"])
    reason_token = _normalize_token(row["order_reconciliation_reason"])
    if float(row.get("human_review_required_flag", 0.0) or 0.0) >= 1.0:
        return True
    return any(keyword in action_token for keyword in REVIEW_TOKENS) or "review" in reason_token


def _is_no_buy_action(row: pd.Series) -> bool:
    token = _normalize_token(row["store_action_label"])
    return any(keyword in token for keyword in NO_BUY_TOKENS)


def _is_buy_action(row: pd.Series) -> bool:
    token = _normalize_token(row["store_action_label"])
    return any(keyword in token for keyword in BUY_TOKENS) and not _is_no_buy_action(row)


def _derive_operator_decision(row: pd.Series) -> str:
    if float(row["recommended_order_units"]) > 0.0:
        return "BUY"
    if _is_review_action(row):
        return "REVIEW"
    if _is_no_buy_action(row):
        return "DO_NOT_BUY"
    return "HOLD"


def _derive_operator_action(row: pd.Series) -> str:
    decision = _derive_operator_decision(row)
    if decision == "BUY":
        return f"ORDER_{int(round(float(row['recommended_order_units'])))}_UNITS"
    if decision == "REVIEW":
        return "MANUAL_REVIEW"
    if decision == "DO_NOT_BUY":
        return "NO_ORDER"
    return "HOLD_STOCK"


def _derive_reason_short(row: pd.Series) -> str:
    reason = str(row["order_reconciliation_reason"] or "").strip()
    if not reason:
        return "No governed reason was recorded."
    sentence = reason.split(". ", 1)[0].strip()
    if not sentence.endswith("."):
        sentence += "."
    return sentence


def _derive_risk_flag(row: pd.Series) -> str:
    availability = str(row["availability_risk_label"] or "").strip()
    capital = str(row["capital_drag_label"] or "").strip()
    demand = str(row["demand_label"] or "").strip()
    if _label_contains_low_soh_or_floor_risk(availability, row["store_action_label"]):
        return availability or "LOW_SOH_OR_FLOOR_RISK"
    if capital:
        return capital
    if demand:
        return demand
    return ""


def _derive_review_flag(row: pd.Series) -> str:
    return "REVIEW" if _is_review_action(row) else ""


def _derive_audit_notes(row: pd.Series) -> str:
    parts = [
        f"demand_label={row['demand_label']}",
        f"availability_risk_label={row['availability_risk_label']}",
        f"capital_drag_label={row['capital_drag_label']}",
        f"raw_model_order_units={int(round(float(row['raw_model_order_units'])))}",
        f"provisional_review_order_units={int(round(float(row['provisional_review_order_units'])))}",
    ]
    return "; ".join(parts)


def _resolve_manifest_path(path_value: object, review_artifact_root: Path) -> Path:
    candidate = Path(str(path_value))
    if candidate.exists():
        return candidate
    if not candidate.is_absolute():
        cwd_candidate = (Path.cwd() / candidate).resolve()
        if cwd_candidate.exists():
            return cwd_candidate
        review_candidate = (review_artifact_root / candidate).resolve()
        if review_candidate.exists():
            return review_candidate
    return candidate


def _validate_review_artifact_root(review_artifact_root: Path) -> None:
    missing = [
        artifact_name
        for artifact_name in REQUIRED_REVIEW_ARTIFACTS
        if not (review_artifact_root / artifact_name).exists()
    ]
    if missing:
        raise PromotionsModelReliabilityNextPassError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _build_cleanup_plan_frame() -> pd.DataFrame:
    plan_rows = [
        {
            "fix_priority": 1,
            "proposed_field": "operator_decision",
            "source_columns": "store_action_label|store_action_label_v2|store_action",
            "retain_context_columns": "priority_rank|priority_band|sku_number|sku_description",
            "audit_only_columns": "",
            "cleanup_action": "Collapse competing action labels into one operator_decision.",
            "rationale": "The current store-facing report exposes multiple visible decision labels for the same row.",
        },
        {
            "fix_priority": 2,
            "proposed_field": "operator_action",
            "source_columns": "operator_status|human_review_required_flag|recommended_order_units",
            "retain_context_columns": "",
            "audit_only_columns": "",
            "cleanup_action": "Derive one visible action verb from decision state plus order quantity.",
            "rationale": "Operator action should not require reconciling status text, review flags, and quantity fields by hand.",
        },
        {
            "fix_priority": 3,
            "proposed_field": "order_units",
            "source_columns": "recommended_order_units",
            "retain_context_columns": "current_soh|on_order_at_advice_time|projected_SOH_at_promo_start|target_SOH_at_promo_start",
            "audit_only_columns": "raw_model_order_units|provisional_review_order_units|final_store_order_units|shadow_policy_order_units",
            "cleanup_action": "Keep one visible quantity field and move duplicate order-state quantities to audit-only outputs.",
            "rationale": "Visible quantity should always match the visible decision hierarchy.",
        },
        {
            "fix_priority": 4,
            "proposed_field": "reason_short",
            "source_columns": "order_reconciliation_reason|model_reason_summary|decision_reason",
            "retain_context_columns": "",
            "audit_only_columns": "primary_review_reason|blocker_reason",
            "cleanup_action": "Collapse multiple prose reason fields into one short operator sentence.",
            "rationale": "Contradictory reason strings currently imply buying on zero-order rows and hide the governed reason hierarchy.",
        },
        {
            "fix_priority": 5,
            "proposed_field": "risk_flag",
            "source_columns": "availability_risk_label|capital_drag_label|demand_evidence_label|end_of_promo_residual_risk",
            "retain_context_columns": "floor_units_required|expected_promo_demand|available_to_sell_before_floor",
            "audit_only_columns": "",
            "cleanup_action": "Collapse risk labels into one highest-priority risk_flag and keep supporting context columns unchanged.",
            "rationale": "Operators need one visible risk headline instead of multiple competing risk vocabularies.",
        },
        {
            "fix_priority": 6,
            "proposed_field": "review_flag",
            "source_columns": "human_review_required_flag|operator_status|primary_review_reason",
            "retain_context_columns": "",
            "audit_only_columns": "",
            "cleanup_action": "Emit one review_flag driven by governed review criteria.",
            "rationale": "Rows with low-SOH or weak evidence need a single visible review signal, not implied review buried across fields.",
        },
        {
            "fix_priority": 7,
            "proposed_field": "audit_notes",
            "source_columns": "primary_review_reason|blocker_reason|model_confidence_percent|capital_at_risk_adjusted_dollars|retail_risk_reward_ratio|SKU_MAE|SKU_MSE|SKU_bias|weeks_of_cover_entering_promo|low_nonzero_value_relief_delta",
            "retain_context_columns": "",
            "audit_only_columns": "",
            "cleanup_action": "Keep supporting diagnostics in audit_notes without widening the visible decision hierarchy.",
            "rationale": "Diagnostic support is still useful, but it should not compete with the visible operator decision fields.",
        },
        {
            "fix_priority": 8,
            "proposed_field": "audit_only_shadow_fields",
            "source_columns": "",
            "retain_context_columns": "",
            "audit_only_columns": "|".join(SHADOW_POLICY_COLUMNS),
            "cleanup_action": "Remove shadow-policy internals from the store-facing report and keep them in audit-only artifacts.",
            "rationale": "Shadow policy remains diagnostics-only and must not appear in operator-facing ordering reports.",
        },
        {
            "fix_priority": 9,
            "proposed_field": "retained_context_fields",
            "source_columns": "",
            "retain_context_columns": "current_soh|on_order_at_advice_time|expected_units_before_promo_start|projected_SOH_at_promo_start|target_SOH_at_promo_start|floor_units_required|expected_promo_demand|available_to_sell_before_floor|projected_stock_gap_units|discount_percent",
            "audit_only_columns": "",
            "cleanup_action": "Retain commercial stock context outside the simplified decision hierarchy.",
            "rationale": "Cleaning the operator contract should simplify decision fields without dropping the stock context operators still need.",
        },
    ]
    plan = pd.DataFrame(plan_rows)
    plan["current_contract_owner"] = (
        "src/surfaces/promotions/reporting/store_prediction_download_builder.py::STORE_FACING_OUTPUT_COLUMNS"
    )
    plan["current_output_column_count"] = len(STORE_FACING_OUTPUT_COLUMNS)
    plan["simplified_operator_fields"] = "|".join(SIMPLIFIED_OPERATOR_FIELDS)
    return plan


def _build_cleanup_issue_rows(
    review_rows: pd.DataFrame,
    *,
    model_report_columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    issue_rows: list[dict[str, object]] = []
    visible_model_columns = set([] if model_report_columns is None else model_report_columns)
    visible_action_columns = [
        column_name
        for column_name in ("raw_model_order_units", "provisional_review_order_units", "recommended_order_units")
        if column_name in visible_model_columns
    ]

    def add_issue(
        *,
        issue_type: str,
        row: pd.Series | None,
        proposed_field: str,
        cleanup_fix: str,
        severity: str,
        detail: str,
    ) -> None:
        issue_rows.append(
            {
                "issue_type": issue_type,
                "sku_number": "" if row is None else str(row["sku_number"]),
                "sku_description": "SCHEMA_LEVEL" if row is None else str(row["sku_description"]),
                "proposed_field": proposed_field,
                "cleanup_fix": cleanup_fix,
                "severity": severity,
                "detail": detail,
                "fix_priority": FIX_PRIORITY_BY_ISSUE_TYPE.get(issue_type, 99),
            }
        )

    for _, row in review_rows.iterrows():
        buy_or_order_implied = _is_buy_action(row) or _text_implies_order(row["order_reconciliation_reason"])
        if buy_or_order_implied and float(row["recommended_order_units"]) <= 0.0:
            add_issue(
                issue_type="BUY_OR_ORDER_TEXT_WITH_ZERO_ORDER_UNITS",
                row=row,
                proposed_field="operator_action",
                cleanup_fix="Zero-order rows must not present BUY or ORDER language in visible action or reason fields.",
                severity="HIGH",
                detail=(
                    f"store_action_label={row['store_action_label']}; "
                    f"recommended_order_units={row['recommended_order_units']}; "
                    f"reason={row['order_reconciliation_reason']}"
                ),
            )

        action_states = {
            column_name: float(row[column_name]) > 0.0
            for column_name in visible_action_columns
        }
        if len(visible_action_columns) > 1 and len(set(action_states.values())) > 1:
            add_issue(
                issue_type="MULTIPLE_ACTION_COLUMNS_CONFLICT",
                row=row,
                proposed_field="order_units",
                cleanup_fix="Keep one visible order_units field and move raw or provisional quantity states to audit-only outputs.",
                severity="HIGH",
                detail=(
                    "; ".join(
                        f"{column_name}={row[column_name]}"
                        for column_name in visible_action_columns
                    )
                ),
            )

        if _label_contains_no_demand(row["demand_label"]) and float(row["actual_units_sold"]) >= MATERIAL_ACTUAL_UNITS:
            add_issue(
                issue_type="NO_DEMAND_WITH_MATERIAL_ACTUAL_UNITS",
                row=row,
                proposed_field="review_flag",
                cleanup_fix="Weak-evidence rows with material realized demand should route to review instead of a hard no-demand operator decision.",
                severity="HIGH",
                detail=(
                    f"demand_label={row['demand_label']}; actual_units_sold={row['actual_units_sold']}"
                ),
            )

        if _label_contains_no_prior(row["demand_label"]) and float(row["actual_units_sold"]) >= MATERIAL_ACTUAL_UNITS:
            add_issue(
                issue_type="NO_PRIOR_PROMO_EVIDENCE_WITH_MATERIAL_ACTUAL_UNITS",
                row=row,
                proposed_field="review_flag",
                cleanup_fix="No-prior-promo rows with material realized demand should route to a diagnostic review path instead of a hard suppression outcome.",
                severity="HIGH",
                detail=(
                    f"demand_label={row['demand_label']}; actual_units_sold={row['actual_units_sold']}"
                ),
            )

        if (
            _normalize_token(row["capital_drag_label"]) == "capital_drag_high"
            and float(row["actual_sell_through_vs_store_adjusted"]) >= STRONG_SELL_THROUGH_THRESHOLD
        ):
            add_issue(
                issue_type="CAPITAL_DRAG_HIGH_WITH_STRONG_SELL_THROUGH",
                row=row,
                proposed_field="risk_flag",
                cleanup_fix="Escalate strong converting rows out of the high capital-drag headline and into review or keep-visible context.",
                severity="MEDIUM",
                detail=(
                    f"capital_drag_label={row['capital_drag_label']}; "
                    f"actual_sell_through_vs_store_adjusted={round(float(row['actual_sell_through_vs_store_adjusted']), 4)}"
                ),
            )

        if (
            _label_contains_low_soh_or_floor_risk(row["store_action_label"], row["availability_risk_label"])
            and float(row["actual_units_sold"]) >= MATERIAL_ACTUAL_UNITS
            and not _is_review_action(row)
        ):
            add_issue(
                issue_type="LOW_SOH_OR_FLOOR_RISK_WITH_MATERIAL_DEMAND_NO_REVIEW_ACTION",
                row=row,
                proposed_field="review_flag",
                cleanup_fix="Low-SOH or floor-risk rows with realized demand should surface a clear review flag even when ordering stays suppressed.",
                severity="HIGH",
                detail=(
                    f"store_action_label={row['store_action_label']}; "
                    f"availability_risk_label={row['availability_risk_label']}; "
                    f"actual_units_sold={row['actual_units_sold']}"
                ),
            )

    for shadow_column in SHADOW_POLICY_COLUMNS:
        if shadow_column in visible_model_columns:
            add_issue(
                issue_type="SHADOW_FIELDS_VISIBLE_IN_OPERATOR_REPORT",
                row=None,
                proposed_field="audit_only_shadow_fields",
                cleanup_fix="Move shadow-policy internals to audit-only artifacts.",
                severity="HIGH",
                detail=shadow_column,
            )

    if not issue_rows:
        return pd.DataFrame(
            columns=[
                "issue_type",
                "sku_number",
                "sku_description",
                "proposed_field",
                "cleanup_fix",
                "severity",
                "detail",
                "fix_priority",
            ]
        )
    issue_frame = pd.DataFrame(issue_rows)
    return issue_frame.sort_values(
        by=["fix_priority", "issue_type", "sku_number"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)


def _summarize_cleanup_issues(issue_rows: pd.DataFrame) -> pd.DataFrame:
    if issue_rows.empty:
        return pd.DataFrame(
            [
                {
                    "issue_type": "TOTAL_REMAINING_CLEANUP_ISSUES",
                    "issue_count": 0,
                    "severity": "NONE",
                    "proposed_field": "",
                    "cleanup_fix": "",
                    "fix_priority": 99,
                    "sample_skus": "",
                }
            ]
        )

    records: list[dict[str, object]] = []
    grouped = issue_rows.groupby("issue_type", sort=False, dropna=False)
    for issue_type, group in grouped:
        sample_skus = ", ".join(
            group.loc[group["sku_number"].ne(""), "sku_number"].astype(str).head(5).tolist()
        )
        records.append(
            {
                "issue_type": str(issue_type),
                "issue_count": int(len(group.index)),
                "severity": str(group["severity"].iloc[0]),
                "proposed_field": str(group["proposed_field"].iloc[0]),
                "cleanup_fix": str(group["cleanup_fix"].iloc[0]),
                "fix_priority": int(group["fix_priority"].iloc[0]),
                "sample_skus": sample_skus,
            }
        )

    summary = pd.DataFrame(records).sort_values(
        by=["fix_priority", "issue_count", "issue_type"],
        ascending=[True, False, True],
        kind="stable",
    )
    total_row = pd.DataFrame(
        [
            {
                "issue_type": "TOTAL_REMAINING_CLEANUP_ISSUES",
                "issue_count": int(len(issue_rows.index)),
                "severity": "SUMMARY",
                "proposed_field": "",
                "cleanup_fix": "",
                "fix_priority": 0,
                "sample_skus": "",
            }
        ]
    )
    return pd.concat([total_row, summary], ignore_index=True)


def _build_action_layer_recalibration_rows(review_rows: pd.DataFrame) -> pd.DataFrame:
    rows = review_rows.copy()
    rows["accepted_allocation_covered_demand_flag"] = (
        (rows["store_adjusted_units"] > 0.0)
        & (rows["store_adjusted_units"] >= rows["actual_units_sold"])
    ).astype(int)
    rows["weak_evidence_label_flag"] = rows["demand_label"].map(_label_contains_weak_or_no_prior).astype(int)
    rows["clear_review_action_flag"] = rows.apply(_is_review_action, axis=1).astype(int)

    rows["capital_guardrail_correct_flag"] = (
        (rows["recommended_order_units"] <= 0.0)
        & (rows["capital_left_unsold"] >= MATERIAL_CAPITAL_LEFT)
        & (rows["actual_sell_through_vs_store_adjusted"] < LOW_SELL_THROUGH_THRESHOLD)
    ).astype(int)

    rows["action_too_conservative_flag"] = (
        (rows["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS)
        & (rows["recommended_order_units"] <= 0.0)
        & (rows["capital_guardrail_correct_flag"] == 0)
        & (rows["accepted_allocation_covered_demand_flag"] == 0)
    ).astype(int)

    rows["review_should_have_triggered_flag"] = (
        (rows["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS)
        & (rows["weak_evidence_label_flag"] == 1)
        & (rows["capital_guardrail_correct_flag"] == 0)
    ).astype(int)

    rows["action_too_aggressive_flag"] = (
        (rows["recommended_order_units"] > 0.0)
        & (
            (rows["actual_units_sold"] <= 0.0)
            | (rows["actual_sell_through_vs_store_adjusted"] < LOW_SELL_THROUGH_THRESHOLD)
        )
    ).astype(int)

    rows["forecast_head_error_not_action_error_flag"] = (
        (rows["forecast_abs_error_units"] >= MATERIAL_UNIT_DELTA)
        & (rows["recommended_order_units"] <= 0.0)
        & (rows["action_too_conservative_flag"] == 0)
        & (rows["review_should_have_triggered_flag"] == 0)
        & (
            (rows["capital_guardrail_correct_flag"] == 1)
            | rows.apply(
                lambda row: _label_contains_low_soh_or_floor_risk(
                    row["store_action_label"], row["availability_risk_label"]
                ),
                axis=1,
            )
        )
    ).astype(int)

    rows["action_layer_recalibration_label"] = "ACTION_OK"
    rows.loc[
        rows["forecast_head_error_not_action_error_flag"] == 1,
        "action_layer_recalibration_label",
    ] = "FORECAST_HEAD_ERROR_NOT_ACTION_ERROR"
    rows.loc[
        rows["action_too_conservative_flag"] == 1,
        "action_layer_recalibration_label",
    ] = "ACTION_TOO_CONSERVATIVE"
    rows.loc[
        rows["capital_guardrail_correct_flag"] == 1,
        "action_layer_recalibration_label",
    ] = "CAPITAL_GUARDRAIL_CORRECT"
    rows.loc[
        rows["action_too_aggressive_flag"] == 1,
        "action_layer_recalibration_label",
    ] = "ACTION_TOO_AGGRESSIVE"
    rows.loc[
        rows["review_should_have_triggered_flag"] == 1,
        "action_layer_recalibration_label",
    ] = "REVIEW_SHOULD_HAVE_TRIGGERED"

    rows["proposed_next_model_action"] = "NO_CHANGE"
    rows.loc[
        rows["forecast_head_error_not_action_error_flag"] == 1,
        "proposed_next_model_action",
    ] = "FIX_FORECAST_HEAD_KEEP_ACTION_GUARDRAIL"
    rows.loc[
        rows["action_too_conservative_flag"] == 1,
        "proposed_next_model_action",
    ] = "ADD_DIAGNOSTIC_REVIEW_OR_SMALL_ORDER_OVERRIDE"
    rows.loc[
        rows["capital_guardrail_correct_flag"] == 1,
        "proposed_next_model_action",
    ] = "KEEP_CAPITAL_GUARDRAIL_ACTIVE"
    rows.loc[
        rows["action_too_aggressive_flag"] == 1,
        "proposed_next_model_action",
    ] = "SUPPRESS_OR_REDUCE_ORDER_UNITS"
    rows.loc[
        rows["review_should_have_triggered_flag"] == 1,
        "proposed_next_model_action",
    ] = "FORCE_REVIEW_ON_WEAK_EVIDENCE_SURPRISE"
    rows.loc[
        rows["review_should_have_triggered_flag"].eq(1)
        & rows["demand_label"].map(_label_contains_no_prior),
        "proposed_next_model_action",
    ] = "ADD_NO_PRIOR_DEMAND_SURPRISE_REVIEW"

    rows["operator_decision"] = rows.apply(_derive_operator_decision, axis=1)
    rows["operator_action"] = rows.apply(_derive_operator_action, axis=1)
    rows["reason_short"] = rows.apply(_derive_reason_short, axis=1)
    rows["risk_flag"] = rows.apply(_derive_risk_flag, axis=1)
    rows["review_flag"] = rows.apply(_derive_review_flag, axis=1)
    rows["audit_notes"] = rows.apply(_derive_audit_notes, axis=1)

    ordered_columns = [
        "sku_number",
        "sku_description",
        "department",
        "operator_decision",
        "operator_action",
        "recommended_order_units",
        "reason_short",
        "risk_flag",
        "review_flag",
        "audit_notes",
        "store_action_label",
        "human_review_required_flag",
        "demand_label",
        "availability_risk_label",
        "capital_drag_label",
        "expected_promo_demand",
        "actual_units_sold",
        "forecast_bias_units",
        "forecast_abs_error_units",
        "order_reconciliation_reason",
        "raw_model_order_units",
        "provisional_review_order_units",
        "pl_allocation_units",
        "store_adjusted_units",
        "actual_sell_through_vs_store_adjusted",
        "estimated_actual_gross_profit",
        "capital_left_unsold",
        "accepted_allocation_covered_demand_flag",
        "weak_evidence_label_flag",
        "action_too_conservative_flag",
        "review_should_have_triggered_flag",
        "capital_guardrail_correct_flag",
        "action_too_aggressive_flag",
        "forecast_head_error_not_action_error_flag",
        "action_layer_recalibration_label",
        "proposed_next_model_action",
    ]
    return rows.loc[:, ordered_columns].copy()


def _summarize_action_layer_recalibration(rows: pd.DataFrame) -> pd.DataFrame:
    total_row = pd.DataFrame(
        [
            {
                "summary_kind": "TOTAL",
                "label_name": "ALL_ROWS",
                "row_count": int(len(rows.index)),
                "actual_units_total": float(rows["actual_units_sold"].sum()),
                "recommended_order_units_total": float(rows["recommended_order_units"].sum()),
                "capital_left_unsold_total": float(rows["capital_left_unsold"].sum()),
                "estimated_actual_gross_profit_total": float(rows["estimated_actual_gross_profit"].sum()),
            }
        ]
    )

    primary_records: list[dict[str, object]] = []
    for label_name, group in rows.groupby("action_layer_recalibration_label", sort=False, dropna=False):
        primary_records.append(
            {
                "summary_kind": "PRIMARY_LABEL",
                "label_name": str(label_name),
                "row_count": int(len(group.index)),
                "actual_units_total": float(group["actual_units_sold"].sum()),
                "recommended_order_units_total": float(group["recommended_order_units"].sum()),
                "capital_left_unsold_total": float(group["capital_left_unsold"].sum()),
                "estimated_actual_gross_profit_total": float(group["estimated_actual_gross_profit"].sum()),
            }
        )

    flag_specs = (
        ("ACTION_TOO_CONSERVATIVE", "action_too_conservative_flag"),
        ("REVIEW_SHOULD_HAVE_TRIGGERED", "review_should_have_triggered_flag"),
        ("CAPITAL_GUARDRAIL_CORRECT", "capital_guardrail_correct_flag"),
        ("ACTION_TOO_AGGRESSIVE", "action_too_aggressive_flag"),
        (
            "FORECAST_HEAD_ERROR_NOT_ACTION_ERROR",
            "forecast_head_error_not_action_error_flag",
        ),
    )
    flag_records: list[dict[str, object]] = []
    for label_name, column_name in flag_specs:
        subset = rows.loc[rows[column_name] == 1]
        flag_records.append(
            {
                "summary_kind": "RULE_FLAG",
                "label_name": label_name,
                "row_count": int(len(subset.index)),
                "actual_units_total": float(subset["actual_units_sold"].sum()),
                "recommended_order_units_total": float(subset["recommended_order_units"].sum()),
                "capital_left_unsold_total": float(subset["capital_left_unsold"].sum()),
                "estimated_actual_gross_profit_total": float(subset["estimated_actual_gross_profit"].sum()),
            }
        )

    summary = pd.concat(
        [total_row, pd.DataFrame(primary_records), pd.DataFrame(flag_records)],
        ignore_index=True,
    )
    return summary.round(6)


def _build_no_prior_demand_surprise_rows(
    recalibration_rows: pd.DataFrame,
) -> pd.DataFrame:
    surprise_mask = (
        recalibration_rows["demand_label"].map(_label_contains_weak_or_no_prior)
        & (recalibration_rows["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS)
        & (
            (recalibration_rows["recommended_order_units"] <= 0.0)
            | recalibration_rows.apply(_is_review_action, axis=1)
            | recalibration_rows.apply(_is_no_buy_action, axis=1)
        )
    )
    surprise_rows = recalibration_rows.loc[surprise_mask].copy()
    if surprise_rows.empty:
        return pd.DataFrame(
            columns=[
                "sku_number",
                "sku_description",
                "department",
                "demand_evidence_label",
                "actual_units_sold",
                "expected_promo_demand",
                "forecast_error_units",
                "pl_allocation_units",
                "store_adjusted_units",
                "actual_gross_profit",
                "capital_left",
                "proposed_next_model_action",
            ]
        )

    surprise_rows["demand_evidence_label"] = surprise_rows["demand_label"]
    surprise_rows["forecast_error_units"] = surprise_rows["forecast_bias_units"]
    surprise_rows["actual_gross_profit"] = surprise_rows["estimated_actual_gross_profit"]
    surprise_rows["capital_left"] = surprise_rows["capital_left_unsold"]
    ordered = surprise_rows.loc[
        :,
        [
            "sku_number",
            "sku_description",
            "department",
            "demand_evidence_label",
            "actual_units_sold",
            "expected_promo_demand",
            "forecast_error_units",
            "pl_allocation_units",
            "store_adjusted_units",
            "actual_gross_profit",
            "capital_left",
            "proposed_next_model_action",
        ],
    ].copy()
    return ordered.sort_values(
        by=["actual_units_sold", "actual_gross_profit", "sku_number"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _summarize_no_prior_demand_surprise_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(
            [
                {
                    "demand_evidence_label": "TOTAL",
                    "proposed_next_model_action": "",
                    "row_count": 0,
                    "actual_units_total": 0.0,
                    "expected_promo_demand_total": 0.0,
                    "actual_gross_profit_total": 0.0,
                    "capital_left_total": 0.0,
                }
            ]
        )

    grouped = (
        rows.groupby(["demand_evidence_label", "proposed_next_model_action"], dropna=False)
        .agg(
            row_count=("sku_number", "size"),
            actual_units_total=("actual_units_sold", "sum"),
            expected_promo_demand_total=("expected_promo_demand", "sum"),
            actual_gross_profit_total=("actual_gross_profit", "sum"),
            capital_left_total=("capital_left", "sum"),
        )
        .reset_index()
        .sort_values(
            by=["row_count", "actual_units_total", "demand_evidence_label"],
            ascending=[False, False, True],
            kind="stable",
        )
    )
    total_row = pd.DataFrame(
        [
            {
                "demand_evidence_label": "TOTAL",
                "proposed_next_model_action": "",
                "row_count": int(len(rows.index)),
                "actual_units_total": float(rows["actual_units_sold"].sum()),
                "expected_promo_demand_total": float(rows["expected_promo_demand"].sum()),
                "actual_gross_profit_total": float(rows["actual_gross_profit"].sum()),
                "capital_left_total": float(rows["capital_left"].sum()),
            }
        ]
    )
    return pd.concat([total_row, grouped], ignore_index=True).round(6)


def _top_cleanup_fix_lines(cleanup_plan: pd.DataFrame, max_items: int = 5) -> list[str]:
    lines: list[str] = []
    for _, row in cleanup_plan.sort_values("fix_priority", kind="stable").head(max_items).iterrows():
        lines.append(
            f"- P{int(row['fix_priority'])}: {row['cleanup_action']}"
        )
    return lines


def _build_report_contract_cleanup_memo(
    *,
    cleanup_plan: pd.DataFrame,
    cleanup_summary: pd.DataFrame,
    manifest: dict[str, object],
) -> str:
    total_issues = int(
        cleanup_summary.loc[
            cleanup_summary["issue_type"] == "TOTAL_REMAINING_CLEANUP_ISSUES", "issue_count"
        ].iloc[0]
    )
    top_issue_rows = cleanup_summary.loc[
        cleanup_summary["issue_type"] != "TOTAL_REMAINING_CLEANUP_ISSUES"
    ].head(5)
    lines = [
        "# Report Contract Cleanup Memo",
        "",
        "## Current owner",
        "- The current store-facing contract is owned by STORE_FACING_OUTPUT_COLUMNS in src/surfaces/promotions/reporting/store_prediction_download_builder.py.",
        f"- The current operator output exposes {len(STORE_FACING_OUTPUT_COLUMNS)} visible columns.",
        "",
        "## Simplified operator hierarchy",
        "- The next store-facing hierarchy should be operator_decision, operator_action, order_units, reason_short, risk_flag, review_flag, and audit_notes.",
        "- Shadow-policy fields stay diagnostics-only and must move to audit-only outputs.",
        "",
        "## Remaining cleanup findings",
        f"- Remaining cleanup issues flagged by this pass: {total_issues}.",
    ]
    for _, row in top_issue_rows.iterrows():
        lines.append(
            f"- {row['issue_type']}: {int(row['issue_count'])} findings. {row['cleanup_fix']}"
        )
    lines.extend(
        [
            "",
            "## First cleanup sequence",
            *_top_cleanup_fix_lines(cleanup_plan),
            "",
            f"Source certification: {manifest.get('source_certification_status', 'UNKNOWN')}.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _build_action_layer_recalibration_memo(
    *,
    recalibration_summary: pd.DataFrame,
    manifest: dict[str, object],
) -> str:
    def count_for(label_name: str) -> int:
        match = recalibration_summary.loc[
            (recalibration_summary["summary_kind"] == "RULE_FLAG")
            & (recalibration_summary["label_name"] == label_name),
            "row_count",
        ]
        return 0 if match.empty else int(match.iloc[0])

    lines = [
        "# Action Layer Recalibration Memo",
        "",
        "## Diagnostic scope",
        "- This pass does not change production ordering logic or Stage 12 publication behavior.",
        "- It only classifies where the action layer was too conservative, too aggressive, correctly guarded, or blocked by forecast-head error.",
        "",
        "## Rule counts",
        f"- ACTION_TOO_CONSERVATIVE: {count_for('ACTION_TOO_CONSERVATIVE')} rows.",
        f"- REVIEW_SHOULD_HAVE_TRIGGERED: {count_for('REVIEW_SHOULD_HAVE_TRIGGERED')} rows.",
        f"- CAPITAL_GUARDRAIL_CORRECT: {count_for('CAPITAL_GUARDRAIL_CORRECT')} rows.",
        f"- ACTION_TOO_AGGRESSIVE: {count_for('ACTION_TOO_AGGRESSIVE')} rows.",
        f"- FORECAST_HEAD_ERROR_NOT_ACTION_ERROR: {count_for('FORECAST_HEAD_ERROR_NOT_ACTION_ERROR')} rows.",
        "",
        "## Interpretation",
        "- Keep capital guardrails active where weak sell-through and material unsold capital validate the suppression outcome.",
        "- Fix action-layer conservatism before any attempt to promote auto-ordering.",
        "- Keep forecast-head repair separate from decision-layer repair when the order suppression outcome was directionally correct.",
        "",
        f"Source certification: {manifest.get('source_certification_status', 'UNKNOWN')}.",
    ]
    return "\n".join(lines).strip() + "\n"


def _build_model_reliability_next_step_memo(
    *,
    review_summary: pd.DataFrame,
    cleanup_plan: pd.DataFrame,
    cleanup_summary: pd.DataFrame,
    recalibration_summary: pd.DataFrame,
    no_prior_summary: pd.DataFrame,
    manifest: dict[str, object],
) -> str:
    review = review_summary.iloc[0]

    def recalibration_count(label_name: str) -> int:
        match = recalibration_summary.loc[
            (recalibration_summary["summary_kind"] == "RULE_FLAG")
            & (recalibration_summary["label_name"] == label_name),
            "row_count",
        ]
        return 0 if match.empty else int(match.iloc[0])

    cleanup_total = int(
        cleanup_summary.loc[
            cleanup_summary["issue_type"] == "TOTAL_REMAINING_CLEANUP_ISSUES", "issue_count"
        ].iloc[0]
    )
    no_prior_total = int(no_prior_summary.iloc[0]["row_count"])
    lines = [
        "# Model Reliability Next Step Memo",
        "",
        "## 1. Executive conclusion",
        f"- The forecast head remains too broad for auto-ordering: MAE is {float(review['forecast_mae']):.3f}, RMSE is {float(review['forecast_rmse']):.3f}, and correlation is {float(review['forecast_correlation']):.3f}.",
        f"- The action layer is still materially too conservative, with only {float(review['recommended_order_units_total']):.1f} recommended units against {float(review['actual_units_total']):.1f} realized units.",
        "",
        "## 2. What the model got right",
        f"- Accepted allocation still converted at {float(review['actual_sell_through_vs_store_adjusted']) * 100.0:.1f}% sell-through against store-adjusted units.",
        f"- Capital left unsold is still measurable at ${float(review['capital_left_unsold_total']):.2f}, so capital-drag guardrails remain directionally useful as a safety control.",
        "",
        "## 3. What the model got wrong",
        f"- Forecast bias is {float(review['forecast_bias_units']):+.1f} units across {int(review['row_count'])} reviewed rows.",
        f"- The recalibration pass found {recalibration_count('ACTION_TOO_CONSERVATIVE')} too-conservative rows and {recalibration_count('REVIEW_SHOULD_HAVE_TRIGGERED')} rows where weak-evidence review should have triggered.",
        "",
        "## 4. Why auto-ordering is not ready",
        "- Forecast-head error and action-layer error are still materially confounded.",
        "- Near-zero recommended order units against material realized demand means the current action layer is not a safe auto-ordering surface.",
        "",
        "## 5. Why the action layer is too conservative",
        f"- {recalibration_count('ACTION_TOO_CONSERVATIVE')} rows sold at least {int(MATERIAL_ACTUAL_UNITS)} units after a zero-order outcome that was not explained by capital drag or accepted allocation cover.",
        f"- {recalibration_count('REVIEW_SHOULD_HAVE_TRIGGERED')} rows landed material demand under weak-evidence or no-prior labels without a clear governed recalibration path.",
        "",
        "## 6. No-prior-demand surprise findings",
        f"- {no_prior_total} rows met the no-prior or weak-evidence surprise criteria for this next-pass review.",
        "- These rows should feed a diagnostic review override before any attempt to relax the demand proxy in production logic.",
        "",
        "## 7. Report cleanup required",
        f"- {cleanup_total} cleanup issues remain across row-level contradictions and schema-level shadow-field exposure.",
        *_top_cleanup_fix_lines(cleanup_plan),
        "",
        "## 8. What must not change yet",
        "- Do not change production ordering logic.",
        "- Do not change Stage 12 publication logic.",
        "- Do not relax the demand proxy.",
        "- Do not promote shadow policy.",
        "- Do not add downstream feature families into the units-head core.",
        "",
        "## 9. Next implementation recommendation",
        "- Keep units-head core unchanged.",
        "- Keep downstream families downstream-only.",
        "- Keep capital-drag guardrails active.",
        "- Do not promote auto-ordering.",
        "- Do not relax demand proxy.",
        "- Build a diagnostic action-layer recalibration pass first.",
        "- Clean the operator report into one decision hierarchy.",
        "",
        f"Source certification: {manifest.get('source_certification_status', 'UNKNOWN')}.",
    ]
    return "\n".join(lines).strip() + "\n"


def build_promotions_model_reliability_next_pass(
    *,
    model_allocation_report_frame: pd.DataFrame,
    actual_outcome_report_frame: pd.DataFrame,
    manifest: dict[str, object] | None = None,
    audit_only_report_frame: pd.DataFrame | None = None,
    model_report_columns: Sequence[str] | None = None,
) -> PromotionsModelReliabilityNextPassResult:
    review_result = build_promotions_model_vs_actual_review(
        model_allocation_report_frame=model_allocation_report_frame,
        actual_outcome_report_frame=actual_outcome_report_frame,
        manifest=manifest,
        audit_only_report_frame=audit_only_report_frame,
        model_report_columns=model_report_columns,
    )
    review_rows = review_result.rows_frame.copy()
    cleanup_source_columns = (
        model_allocation_report_frame.columns if model_report_columns is None else model_report_columns
    )
    cleanup_plan = _build_cleanup_plan_frame()
    cleanup_issue_rows = _build_cleanup_issue_rows(
        review_rows,
        model_report_columns=cleanup_source_columns,
    )
    cleanup_summary = _summarize_cleanup_issues(cleanup_issue_rows)
    recalibration_rows = _build_action_layer_recalibration_rows(review_rows)
    recalibration_summary = _summarize_action_layer_recalibration(recalibration_rows)
    no_prior_rows = _build_no_prior_demand_surprise_rows(recalibration_rows)
    no_prior_summary = _summarize_no_prior_demand_surprise_rows(no_prior_rows)
    memo_manifest = manifest or {}
    cleanup_memo = _build_report_contract_cleanup_memo(
        cleanup_plan=cleanup_plan,
        cleanup_summary=cleanup_summary,
        manifest=memo_manifest,
    )
    recalibration_memo = _build_action_layer_recalibration_memo(
        recalibration_summary=recalibration_summary,
        manifest=memo_manifest,
    )
    next_step_memo = _build_model_reliability_next_step_memo(
        review_summary=review_result.summary_frame,
        cleanup_plan=cleanup_plan,
        cleanup_summary=cleanup_summary,
        recalibration_summary=recalibration_summary,
        no_prior_summary=no_prior_summary,
        manifest=memo_manifest,
    )
    return PromotionsModelReliabilityNextPassResult(
        review_rows_frame=review_rows,
        review_summary_frame=review_result.summary_frame.copy(),
        cleanup_plan_frame=cleanup_plan,
        cleanup_issue_rows_frame=cleanup_issue_rows,
        cleanup_summary_frame=cleanup_summary,
        cleanup_memo_markdown=cleanup_memo,
        action_layer_recalibration_rows_frame=recalibration_rows,
        action_layer_recalibration_summary_frame=recalibration_summary,
        action_layer_recalibration_memo_markdown=recalibration_memo,
        no_prior_demand_surprise_rows_frame=no_prior_rows,
        no_prior_demand_surprise_summary_frame=no_prior_summary,
        model_reliability_next_step_memo_markdown=next_step_memo,
    )


def write_promotions_model_reliability_next_pass(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsModelReliabilityNextPassArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsModelReliabilityNextPassError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    model_path = _resolve_manifest_path(manifest.get("allocation_report_csv_path", ""), review_artifact_path)
    actual_path = _resolve_manifest_path(manifest.get("actual_review_csv_path_used", ""), review_artifact_path)
    audit_path_value = str(manifest.get("audit_only_report_csv_path", "")).strip()
    if not model_path.exists():
        raise PromotionsModelReliabilityNextPassError(
            f"Model allocation report from manifest does not exist: {model_path}"
        )
    if not actual_path.exists():
        raise PromotionsModelReliabilityNextPassError(
            f"Actual outcome report from manifest does not exist: {actual_path}"
        )
    audit_frame: pd.DataFrame | None = None
    if audit_path_value:
        audit_path = _resolve_manifest_path(audit_path_value, review_artifact_path)
        if not audit_path.exists():
            raise PromotionsModelReliabilityNextPassError(
                f"Audit-only model report from manifest does not exist: {audit_path}"
            )
        audit_frame = _read_csv(audit_path)

    model_frame = _read_csv(model_path)
    actual_frame = _read_csv(actual_path)
    result = build_promotions_model_reliability_next_pass(
        model_allocation_report_frame=model_frame,
        actual_outcome_report_frame=actual_frame,
        manifest=manifest,
        audit_only_report_frame=audit_frame,
        model_report_columns=model_frame.columns,
    )

    destination_root = Path(output_root) if output_root is not None else review_artifact_path
    destination_root.mkdir(parents=True, exist_ok=True)

    cleanup_plan_path = destination_root / "report_contract_cleanup_plan.csv"
    cleanup_summary_path = destination_root / "report_contract_cleanup_summary.csv"
    cleanup_memo_path = destination_root / "report_contract_cleanup_memo.md"
    recalibration_rows_path = destination_root / "action_layer_recalibration_rows.csv"
    recalibration_summary_path = destination_root / "action_layer_recalibration_summary.csv"
    recalibration_memo_path = destination_root / "action_layer_recalibration_memo.md"
    no_prior_rows_path = destination_root / "no_prior_demand_surprise_rows.csv"
    no_prior_summary_path = destination_root / "no_prior_demand_surprise_summary.csv"
    next_step_memo_path = destination_root / "model_reliability_next_step_memo.md"

    result.cleanup_plan_frame.to_csv(cleanup_plan_path, index=False)
    add_provenance_columns(result.cleanup_summary_frame.copy(), manifest).to_csv(
        cleanup_summary_path,
        index=False,
    )
    cleanup_memo_path.write_text(result.cleanup_memo_markdown, encoding="utf-8")
    result.action_layer_recalibration_rows_frame.to_csv(recalibration_rows_path, index=False)
    add_provenance_columns(result.action_layer_recalibration_summary_frame.copy(), manifest).to_csv(
        recalibration_summary_path,
        index=False,
    )
    recalibration_memo_path.write_text(
        result.action_layer_recalibration_memo_markdown,
        encoding="utf-8",
    )
    result.no_prior_demand_surprise_rows_frame.to_csv(no_prior_rows_path, index=False)
    add_provenance_columns(result.no_prior_demand_surprise_summary_frame.copy(), manifest).to_csv(
        no_prior_summary_path,
        index=False,
    )
    next_step_memo_path.write_text(
        result.model_reliability_next_step_memo_markdown,
        encoding="utf-8",
    )

    return PromotionsModelReliabilityNextPassArtifacts(
        report_contract_cleanup_plan_csv_path=str(cleanup_plan_path),
        report_contract_cleanup_summary_csv_path=str(cleanup_summary_path),
        report_contract_cleanup_memo_md_path=str(cleanup_memo_path),
        action_layer_recalibration_rows_csv_path=str(recalibration_rows_path),
        action_layer_recalibration_summary_csv_path=str(recalibration_summary_path),
        action_layer_recalibration_memo_md_path=str(recalibration_memo_path),
        no_prior_demand_surprise_rows_csv_path=str(no_prior_rows_path),
        no_prior_demand_surprise_summary_csv_path=str(no_prior_summary_path),
        model_reliability_next_step_memo_md_path=str(next_step_memo_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the governed promotions model-reliability next pass: "
            "report cleanup plus action-layer recalibration."
        )
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_model_reliability_next_pass(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("report_contract_cleanup_summary", artifacts.report_contract_cleanup_summary_csv_path)
    print(
        "action_layer_recalibration_summary",
        artifacts.action_layer_recalibration_summary_csv_path,
    )
    print("model_reliability_next_step_memo", artifacts.model_reliability_next_step_memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())