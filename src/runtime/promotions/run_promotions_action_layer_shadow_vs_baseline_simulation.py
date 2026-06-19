from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from runtime.promotions.input_source_provenance import (
    add_provenance_columns,
    certification_failed,
)


OUTPUT_FOLDER_NAME = "action_layer_shadow_vs_baseline_simulation"
INPUT_ROWS_RELATIVE_PATH = Path(
    "action_layer_shadow_calibration_candidates/action_layer_shadow_calibration_candidate_rows.csv"
)
INPUT_RULES_RELATIVE_PATH = Path(
    "action_layer_shadow_calibration_candidates/action_layer_shadow_calibration_candidate_rules.csv"
)
INPUT_SUMMARY_RELATIVE_PATH = Path(
    "action_layer_shadow_calibration_candidates/action_layer_shadow_calibration_candidate_summary.csv"
)
UNRESOLVED_ROWS_RELATIVE_PATH = Path(
    "action_layer_unresolved_inspection/action_layer_unresolved_inspection_rows.csv"
)
READINESS_SUMMARY_RELATIVE_PATH = Path(
    "pretrain_readiness_inspection/pretrain_readiness_summary.csv"
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    str(INPUT_ROWS_RELATIVE_PATH),
    str(INPUT_RULES_RELATIVE_PATH),
    str(INPUT_SUMMARY_RELATIVE_PATH),
    str(UNRESOLVED_ROWS_RELATIVE_PATH),
    str(READINESS_SUMMARY_RELATIVE_PATH),
)

CORE_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
)

PRESERVED_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
    "source_rule_flag",
    "operator_decision",
    "operator_action",
    "order_units",
    "actual_units_sold",
    "expected_promo_demand",
    "forecast_error_units",
    "actual_gross_profit",
    "capital_left_in_unsold_store_allocation",
    "commercial_priority",
    "action_layer_inspection_bucket",
    "shadow_calibration_rule_candidate",
    "shadow_rule_family",
    "shadow_rule_strength",
    "shadow_rule_risk_level",
    "shadow_rule_test_status",
    "production_order_change_flag",
    "stage_12_change_flag",
    "source_row_number",
    "recommended_shadow_test_action",
)

SIMULATION_COLUMNS: tuple[str, ...] = (
    "baseline_action_layer_outcome",
    "shadow_review_trigger_outcome",
    "shadow_incremental_review_trigger_flag",
    "shadow_notional_commercial_opportunity",
    "shadow_notional_capital_risk",
    "shadow_net_review_value_proxy",
    "shadow_simulation_status",
    "simulation_reason",
    "recommended_next_action",
)

BY_RULE_FAMILY_COLUMNS: tuple[str, ...] = (
    "shadow_rule_family",
    "row_count",
    "unique_skus",
    "share_of_rows",
    "incremental_shadow_review_triggers",
    "high_priority_incremental_triggers",
    "gross_profit_represented",
    "capital_left_represented",
    "net_review_value_proxy",
    "favours_shadow_review_trigger_rows",
    "baseline_conservatism_supported_rows",
    "inconclusive_rows",
    "sample_skus",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "notes",
)

OVER_SUPPRESSION_CANDIDATE = "OVER_SUPPRESSION_CANDIDATE"

BASELINE_SUPPRESSED_OR_UNDER_REVIEW = "BASELINE_SUPPRESSED_OR_UNDER_REVIEW"
BASELINE_REVIEW_ONLY = "BASELINE_REVIEW_ONLY"
BASELINE_BUY_OR_ORDERED = "BASELINE_BUY_OR_ORDERED"
BASELINE_UNKNOWN = "BASELINE_UNKNOWN"

SHADOW_REVIEW_TRIGGERED = "SHADOW_REVIEW_TRIGGERED"
SHADOW_NO_CHANGE = "SHADOW_NO_CHANGE"
SHADOW_REJECTED = "SHADOW_REJECTED"
SHADOW_ONLY_NOT_PRODUCTION = "SHADOW_ONLY_NOT_PRODUCTION"

FAVOURS_SHADOW_REVIEW_TRIGGER = "FAVOURS_SHADOW_REVIEW_TRIGGER"
BASELINE_CONSERVATISM_SUPPORTED = "BASELINE_CONSERVATISM_SUPPORTED"
INCONCLUSIVE = "INCONCLUSIVE"

DO_NOT_PROMOTE_TO_AUTO_ORDER = "DO_NOT_PROMOTE_TO_AUTO_ORDER"
KEEP_SHADOW_REVIEW_TRIGGER_FOR_MORE_PROMOTIONS = (
    "KEEP_SHADOW_REVIEW_TRIGGER_FOR_MORE_PROMOTIONS"
)
REQUIRE_REPEAT_EVIDENCE = "REQUIRE_REPEAT_EVIDENCE"
DO_NOT_PROMOTE_TO_PRODUCTION = "DO_NOT_PROMOTE_TO_PRODUCTION"
REMOVE_WEAK_SHADOW_RULE = "REMOVE_WEAK_SHADOW_RULE"

FINAL_RECOMMENDATION = KEEP_SHADOW_REVIEW_TRIGGER_FOR_MORE_PROMOTIONS


class PromotionsActionLayerShadowVsBaselineSimulationError(RuntimeError):
    """Raised when the shadow-vs-baseline simulation cannot run safely."""


@dataclass(frozen=True)
class PromotionsActionLayerShadowVsBaselineSimulationResult:
    rows_frame: pd.DataFrame
    by_rule_family_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsActionLayerShadowVsBaselineSimulationArtifacts:
    rows_csv_path: str
    by_rule_family_csv_path: str
    summary_csv_path: str
    memo_md_path: str


def _read_csv(
    path: str | Path,
    *,
    allow_empty: bool = False,
    empty_columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame(columns=list(empty_columns or ()))
        raise PromotionsActionLayerShadowVsBaselineSimulationError(f"CSV is empty: {path}")
    if frame.empty and not allow_empty:
        raise PromotionsActionLayerShadowVsBaselineSimulationError(f"CSV is empty: {path}")
    if frame.empty and empty_columns is not None:
        for column_name in empty_columns:
            if column_name not in frame.columns:
                frame[column_name] = pd.Series(dtype="object")
        frame = frame.loc[:, list(dict.fromkeys([*frame.columns.tolist(), *empty_columns]))]
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsActionLayerShadowVsBaselineSimulationError(
            f"Manifest must be a JSON object: {path}"
        )
    return payload


def _validate_review_artifact_root(review_artifact_root: Path) -> None:
    missing = [
        artifact_name
        for artifact_name in REQUIRED_REVIEW_ARTIFACTS
        if not (review_artifact_root / artifact_name).exists()
    ]
    if missing:
        raise PromotionsActionLayerShadowVsBaselineSimulationError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsActionLayerShadowVsBaselineSimulationError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _format_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}"


def _format_share(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _summary_row(
    metric_group: str,
    metric_name: str,
    metric_value: object,
    metric_unit: str,
    metric_display: str,
    notes: str,
) -> dict[str, object]:
    return {
        "metric_group": metric_group,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_unit": metric_unit,
        "metric_display": metric_display,
        "notes": notes,
    }


def _sample_values(values: pd.Series, *, limit: int = 5) -> str:
    unique_values: list[str] = []
    for value in values.astype(str).tolist():
        cleaned = value.strip()
        if not cleaned or cleaned in unique_values:
            continue
        unique_values.append(cleaned)
        if len(unique_values) >= limit:
            break
    return ", ".join(unique_values)


def _all_missing_or_blank(values: pd.Series) -> bool:
    normalized = values.fillna("").astype(str).str.strip()
    return normalized.eq("").all()


def _metric_lookup(frame: pd.DataFrame | None) -> dict[str, object]:
    if frame is None or frame.empty or "metric_name" not in frame.columns:
        return {}
    lookup: dict[str, object] = {}
    for row in frame.itertuples(index=False):
        lookup[str(getattr(row, "metric_name"))] = getattr(row, "metric_value")
    return lookup


def _readiness_reason(frame: pd.DataFrame | None, readiness_check: str) -> str:
    if frame is None or frame.empty:
        return ""
    if "readiness_check" not in frame.columns or "reason" not in frame.columns:
        return ""
    matched = frame.loc[frame["readiness_check"].astype(str).eq(readiness_check)]
    if matched.empty:
        return ""
    return _normalize_text(matched.iloc[0]["reason"])


def _ensure_columns(source_frame: pd.DataFrame) -> pd.DataFrame:
    frame = source_frame.copy()

    for column_name in PRESERVED_COLUMNS:
        if column_name not in frame.columns:
            frame[column_name] = pd.Series(dtype="object")

    if not frame.empty:
        if _all_missing_or_blank(frame["order_units"]):
            recommended_order_units = (
                frame["recommended_order_units"]
                if "recommended_order_units" in frame.columns
                else pd.Series(0.0, index=frame.index)
            )
            frame["order_units"] = pd.to_numeric(
                recommended_order_units,
                errors="coerce",
            ).fillna(0.0)
        if _all_missing_or_blank(frame["action_layer_inspection_bucket"]):
            frame["action_layer_inspection_bucket"] = OVER_SUPPRESSION_CANDIDATE
        if _all_missing_or_blank(frame["source_row_number"]):
            frame["source_row_number"] = range(1, len(frame.index) + 1)

    numeric_columns = (
        "order_units",
        "actual_units_sold",
        "expected_promo_demand",
        "forecast_error_units",
        "actual_gross_profit",
        "capital_left_in_unsold_store_allocation",
    )
    for column_name in numeric_columns:
        frame[column_name] = pd.to_numeric(frame.get(column_name), errors="coerce").fillna(0.0)

    frame["production_order_change_flag"] = pd.to_numeric(
        frame.get("production_order_change_flag"),
        errors="coerce",
    ).fillna(0).astype(int)
    frame["stage_12_change_flag"] = pd.to_numeric(
        frame.get("stage_12_change_flag"),
        errors="coerce",
    ).fillna(0).astype(int)
    frame["source_row_number"] = pd.to_numeric(
        frame.get("source_row_number"),
        errors="coerce",
    ).fillna(0).astype(int)

    return frame


def _expected_candidate_rows(summary_frame: pd.DataFrame | None) -> int:
    if summary_frame is None or summary_frame.empty:
        return 0
    _require_columns(
        summary_frame,
        ("metric_name", "metric_value"),
        frame_name="action_layer_shadow_calibration_candidate_summary_frame",
    )
    matched = summary_frame.loc[
        summary_frame["metric_name"].astype(str).eq("OVER_SUPPRESSION_CANDIDATE_ROWS_SELECTED")
    ]
    if matched.empty:
        return 0
    return int(pd.to_numeric(matched.iloc[0]["metric_value"], errors="coerce"))


def _validate_against_unresolved_rows(
    candidate_rows_frame: pd.DataFrame,
    unresolved_rows_frame: pd.DataFrame | None,
) -> None:
    if unresolved_rows_frame is None or unresolved_rows_frame.empty or candidate_rows_frame.empty:
        return
    _require_columns(
        unresolved_rows_frame,
        ("sku_number", "source_row_number"),
        frame_name="action_layer_unresolved_inspection_rows_frame",
    )
    unresolved_keys = set(
        zip(
            unresolved_rows_frame["sku_number"].astype(str),
            pd.to_numeric(unresolved_rows_frame["source_row_number"], errors="coerce").fillna(0).astype(int),
        )
    )
    missing_keys = [
        (sku, row_number)
        for sku, row_number in zip(
            candidate_rows_frame["sku_number"].astype(str),
            candidate_rows_frame["source_row_number"].astype(int),
        )
        if (sku, row_number) not in unresolved_keys
    ]
    if missing_keys:
        raise PromotionsActionLayerShadowVsBaselineSimulationError(
            "Candidate rows are not fully traceable to unresolved inspection rows."
        )


def _baseline_action_layer_outcome(row: pd.Series) -> str:
    operator_decision = _normalize_text(row.get("operator_decision")).upper()
    operator_action = _normalize_text(row.get("operator_action")).upper()
    order_units = _as_float(row.get("order_units"))

    if operator_decision == "REVIEW" or operator_action == "MANUAL_REVIEW":
        return BASELINE_REVIEW_ONLY
    if operator_decision == "BUY" or operator_action.startswith("ORDER_") or order_units > 0.0:
        return BASELINE_BUY_OR_ORDERED
    if operator_decision in {"DO_NOT_BUY", "HOLD"} or operator_action in {"NO_ORDER", "HOLD_STOCK"}:
        return BASELINE_SUPPRESSED_OR_UNDER_REVIEW
    return BASELINE_UNKNOWN


def _shadow_review_trigger_outcome(row: pd.Series) -> str:
    recommended_shadow_test_action = _normalize_text(row.get("recommended_shadow_test_action"))
    baseline_outcome = _normalize_text(row.get("baseline_action_layer_outcome"))

    if recommended_shadow_test_action == DO_NOT_PROMOTE_TO_AUTO_ORDER:
        return SHADOW_REJECTED
    if baseline_outcome == BASELINE_SUPPRESSED_OR_UNDER_REVIEW:
        return SHADOW_REVIEW_TRIGGERED
    if baseline_outcome == BASELINE_REVIEW_ONLY:
        return SHADOW_NO_CHANGE
    return SHADOW_REJECTED if recommended_shadow_test_action == DO_NOT_PROMOTE_TO_AUTO_ORDER else SHADOW_NO_CHANGE


def _shadow_incremental_review_trigger_flag(row: pd.Series) -> int:
    return int(
        _normalize_text(row.get("baseline_action_layer_outcome")) == BASELINE_SUPPRESSED_OR_UNDER_REVIEW
        and _normalize_text(row.get("shadow_review_trigger_outcome")) == SHADOW_REVIEW_TRIGGERED
    )


def _shadow_notional_commercial_opportunity(row: pd.Series) -> float:
    return max(_as_float(row.get("actual_gross_profit")), 0.0)


def _shadow_notional_capital_risk(row: pd.Series) -> float:
    return max(_as_float(row.get("capital_left_in_unsold_store_allocation")), 0.0)


def _shadow_simulation_status(row: pd.Series) -> str:
    trigger_outcome = _normalize_text(row.get("shadow_review_trigger_outcome"))
    net_value = _as_float(row.get("shadow_net_review_value_proxy"))
    incremental_flag = int(row.get("shadow_incremental_review_trigger_flag", 0) or 0)
    if trigger_outcome == SHADOW_REJECTED:
        return BASELINE_CONSERVATISM_SUPPORTED
    if incremental_flag == 1 and net_value > 0.0:
        return FAVOURS_SHADOW_REVIEW_TRIGGER
    if trigger_outcome == SHADOW_NO_CHANGE:
        return INCONCLUSIVE
    if net_value <= 0.0:
        return BASELINE_CONSERVATISM_SUPPORTED
    return INCONCLUSIVE


def _simulation_reason(row: pd.Series) -> str:
    baseline_outcome = _normalize_text(row.get("baseline_action_layer_outcome"))
    shadow_outcome = _normalize_text(row.get("shadow_review_trigger_outcome"))
    net_value = _as_float(row.get("shadow_net_review_value_proxy"))
    gross_profit = _format_money(_as_float(row.get("shadow_notional_commercial_opportunity")))
    capital_risk = _format_money(_as_float(row.get("shadow_notional_capital_risk")))

    if shadow_outcome == SHADOW_REVIEW_TRIGGERED:
        return (
            f"Baseline state {baseline_outcome} would become a shadow-only review trigger; historical commercial opportunity {gross_profit} exceeds capital risk {capital_risk}."
        )
    if shadow_outcome == SHADOW_NO_CHANGE:
        return (
            f"Baseline state {baseline_outcome} is already review-oriented, so the shadow rule does not add a new trigger; net proxy = { _format_money(net_value) }."
        )
    return (
        f"Shadow rule stays rejected for comparison because the candidate remains too weak for even review-only promotion; net proxy = { _format_money(net_value) }."
    )


def _recommended_next_action(row: pd.Series) -> str:
    simulation_status = _normalize_text(row.get("shadow_simulation_status"))
    shadow_outcome = _normalize_text(row.get("shadow_review_trigger_outcome"))
    if shadow_outcome == SHADOW_REJECTED:
        return REMOVE_WEAK_SHADOW_RULE
    if simulation_status == FAVOURS_SHADOW_REVIEW_TRIGGER:
        return KEEP_SHADOW_REVIEW_TRIGGER_FOR_MORE_PROMOTIONS
    if simulation_status == BASELINE_CONSERVATISM_SUPPORTED:
        return DO_NOT_PROMOTE_TO_PRODUCTION
    return REQUIRE_REPEAT_EVIDENCE


def _build_rows_frame(candidate_rows_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        candidate_rows_frame,
        CORE_COLUMNS,
        frame_name="action_layer_shadow_calibration_candidate_rows_frame",
    )
    rows = _ensure_columns(candidate_rows_frame)

    if rows.empty:
        for column_name in SIMULATION_COLUMNS:
            if column_name not in rows.columns:
                rows[column_name] = pd.Series(dtype="object")
        output_columns = list(dict.fromkeys([*PRESERVED_COLUMNS, *SIMULATION_COLUMNS]))
        return rows.loc[:, output_columns].reset_index(drop=True)

    rows["baseline_action_layer_outcome"] = rows.apply(_baseline_action_layer_outcome, axis=1)
    rows["shadow_review_trigger_outcome"] = rows.apply(_shadow_review_trigger_outcome, axis=1)
    rows["shadow_incremental_review_trigger_flag"] = rows.apply(
        _shadow_incremental_review_trigger_flag,
        axis=1,
    )
    rows["shadow_notional_commercial_opportunity"] = rows.apply(
        _shadow_notional_commercial_opportunity,
        axis=1,
    )
    rows["shadow_notional_capital_risk"] = rows.apply(_shadow_notional_capital_risk, axis=1)
    rows["shadow_net_review_value_proxy"] = (
        rows["shadow_notional_commercial_opportunity"] - rows["shadow_notional_capital_risk"]
    )
    rows["shadow_simulation_status"] = rows.apply(_shadow_simulation_status, axis=1)
    rows["simulation_reason"] = rows.apply(_simulation_reason, axis=1)
    rows["recommended_next_action"] = rows.apply(_recommended_next_action, axis=1)

    output_columns = list(dict.fromkeys([*PRESERVED_COLUMNS, *SIMULATION_COLUMNS]))
    return rows.loc[:, output_columns].reset_index(drop=True)


def _build_by_rule_family_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=BY_RULE_FAMILY_COLUMNS)

    records: list[dict[str, object]] = []
    total_rows = float(len(rows_frame.index))

    for family, group in rows_frame.groupby("shadow_rule_family", sort=False, dropna=False):
        unique_group = group.drop_duplicates(subset=["source_row_number"])
        records.append(
            {
                "shadow_rule_family": str(family),
                "row_count": int(len(group.index)),
                "unique_skus": int(group["sku_number"].astype(str).nunique()),
                "share_of_rows": float(len(group.index)) / total_rows,
                "incremental_shadow_review_triggers": int(group["shadow_incremental_review_trigger_flag"].sum()),
                "high_priority_incremental_triggers": int(
                    (group["shadow_incremental_review_trigger_flag"].eq(1)
                     & group["commercial_priority"].astype(str).eq("HIGH")).sum()
                ),
                "gross_profit_represented": float(pd.to_numeric(unique_group["shadow_notional_commercial_opportunity"], errors="coerce").fillna(0.0).sum()),
                "capital_left_represented": float(pd.to_numeric(unique_group["shadow_notional_capital_risk"], errors="coerce").fillna(0.0).sum()),
                "net_review_value_proxy": float(pd.to_numeric(unique_group["shadow_net_review_value_proxy"], errors="coerce").fillna(0.0).sum()),
                "favours_shadow_review_trigger_rows": int(group["shadow_simulation_status"].astype(str).eq(FAVOURS_SHADOW_REVIEW_TRIGGER).sum()),
                "baseline_conservatism_supported_rows": int(group["shadow_simulation_status"].astype(str).eq(BASELINE_CONSERVATISM_SUPPORTED).sum()),
                "inconclusive_rows": int(group["shadow_simulation_status"].astype(str).eq(INCONCLUSIVE).sum()),
                "sample_skus": _sample_values(group["sku_number"]),
            }
        )

    frame = pd.DataFrame(records, columns=BY_RULE_FAMILY_COLUMNS)
    return frame.sort_values(
        by=["row_count", "incremental_shadow_review_triggers", "shadow_rule_family"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_summary_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    input_rows = int(len(rows_frame.index))
    unique_skus = int(rows_frame["sku_number"].astype(str).nunique()) if input_rows > 0 else 0
    incremental_triggers = int(rows_frame["shadow_incremental_review_trigger_flag"].sum()) if input_rows > 0 else 0
    high_priority_incremental = int(
        (rows_frame["shadow_incremental_review_trigger_flag"].eq(1)
         & rows_frame["commercial_priority"].astype(str).eq("HIGH")).sum()
    ) if input_rows > 0 else 0
    gross_profit_represented = float(pd.to_numeric(rows_frame["shadow_notional_commercial_opportunity"], errors="coerce").fillna(0.0).sum()) if input_rows > 0 else 0.0
    capital_left_represented = float(pd.to_numeric(rows_frame["shadow_notional_capital_risk"], errors="coerce").fillna(0.0).sum()) if input_rows > 0 else 0.0
    net_value_proxy = float(pd.to_numeric(rows_frame["shadow_net_review_value_proxy"], errors="coerce").fillna(0.0).sum()) if input_rows > 0 else 0.0
    family_counts = rows_frame["shadow_rule_family"].astype(str).value_counts(dropna=False) if input_rows > 0 else pd.Series(dtype="int64")
    dominant_rule_family = str(family_counts.index[0]) if not family_counts.empty else ""
    status_counts = rows_frame["shadow_simulation_status"].astype(str).value_counts(dropna=False) if input_rows > 0 else pd.Series(dtype="int64")
    production_changes = int(pd.to_numeric(rows_frame["production_order_change_flag"], errors="coerce").fillna(0).sum()) if input_rows > 0 else 0
    stage12_changes = int(pd.to_numeric(rows_frame["stage_12_change_flag"], errors="coerce").fillna(0).sum()) if input_rows > 0 else 0

    rows: list[dict[str, object]] = [
        _summary_row(
            "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION",
            "INPUT_CANDIDATE_ROWS",
            input_rows,
            "rows",
            _format_int(input_rows),
            "Input rows from the shadow calibration candidate pack.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION",
            "UNIQUE_SKUS",
            unique_skus,
            "rows",
            _format_int(unique_skus),
            "Unique SKUs represented in the shadow-vs-baseline simulation.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION",
            "INCREMENTAL_SHADOW_REVIEW_TRIGGERS",
            incremental_triggers,
            "rows",
            _format_int(incremental_triggers),
            "Rows where shadow-only review triggers would have elevated a suppressed baseline row into review.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION",
            "HIGH_PRIORITY_INCREMENTAL_TRIGGERS",
            high_priority_incremental,
            "rows",
            _format_int(high_priority_incremental),
            "High-priority rows among the incremental shadow review triggers.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION",
            "GROSS_PROFIT_REPRESENTED",
            gross_profit_represented,
            "dollars",
            _format_money(gross_profit_represented),
            "Historical gross profit represented by the simulated shadow review slice.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION",
            "CAPITAL_LEFT_REPRESENTED",
            capital_left_represented,
            "dollars",
            _format_money(capital_left_represented),
            "Historical capital-left exposure represented by the simulated shadow review slice.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION",
            "NET_REVIEW_VALUE_PROXY",
            net_value_proxy,
            "dollars",
            _format_money(net_value_proxy),
            "Shadow notional commercial opportunity less capital risk across the simulation slice.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION",
            "DOMINANT_RULE_FAMILY",
            dominant_rule_family,
            "label",
            dominant_rule_family,
            "Most common shadow rule family in the simulation input.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            production_changes,
            "rows",
            _format_int(production_changes),
            "This diagnostics-only simulation does not change production ordering logic.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            stage12_changes,
            "rows",
            _format_int(stage12_changes),
            "This diagnostics-only simulation does not change Stage 12.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION",
            "FINAL_RECOMMENDATION",
            FINAL_RECOMMENDATION,
            "label",
            FINAL_RECOMMENDATION,
            "Shadow-only recommendation after comparing baseline action handling against review-trigger-only candidates.",
        ),
    ]

    for family_name, count in family_counts.items():
        rows.append(
            _summary_row(
                "COUNT_BY_SHADOW_RULE_FAMILY",
                str(family_name),
                int(count),
                "rows",
                _format_int(int(count)),
                "Simulation input row count for this shadow rule family.",
            )
        )

    for status_name, count in status_counts.items():
        rows.append(
            _summary_row(
                "COUNT_BY_SIMULATION_STATUS",
                str(status_name),
                int(count),
                "rows",
                _format_int(int(count)),
                "Simulation row count for this shadow-vs-baseline status.",
            )
        )

    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_memo(
    *,
    rows_frame: pd.DataFrame,
    by_rule_family_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    pretrain_readiness_summary_frame: pd.DataFrame | None,
) -> str:
    summary_lookup = _metric_lookup(summary_frame)
    input_rows = int(_as_float(summary_lookup.get("INPUT_CANDIDATE_ROWS", 0)))
    unique_skus = int(_as_float(summary_lookup.get("UNIQUE_SKUS", 0)))
    incremental_triggers = int(_as_float(summary_lookup.get("INCREMENTAL_SHADOW_REVIEW_TRIGGERS", 0)))
    high_priority_incremental = int(_as_float(summary_lookup.get("HIGH_PRIORITY_INCREMENTAL_TRIGGERS", 0)))
    net_value_proxy = _format_money(_as_float(summary_lookup.get("NET_REVIEW_VALUE_PROXY", 0.0)))
    dominant_rule_family = _normalize_text(summary_lookup.get("DOMINANT_RULE_FAMILY"))
    recommendation = _normalize_text(summary_lookup.get("FINAL_RECOMMENDATION"))

    forecast_reason = _readiness_reason(pretrain_readiness_summary_frame, "forecast_head_reliability")
    action_layer_reason = _readiness_reason(pretrain_readiness_summary_frame, "action_layer_calibration_ready")

    status_counts = rows_frame["shadow_simulation_status"].astype(str).value_counts(dropna=False)
    status_lines = [
        f"- {status}: {int(count)} rows"
        for status, count in status_counts.items()
    ] or ["- No simulation rows were available."]

    family_lines = []
    for row in by_rule_family_frame.head(5).itertuples(index=False):
        family_lines.append(
            f"- {getattr(row, 'shadow_rule_family')}: {getattr(row, 'row_count')} rows, "
            f"incremental_triggers={getattr(row, 'incremental_shadow_review_triggers')}, "
            f"net_proxy={_format_money(_as_float(getattr(row, 'net_review_value_proxy')))}"
        )
    if not family_lines:
        family_lines.append("- No rule-family simulation rows were available.")

    return "\n".join(
        [
            "# Governed Shadow-vs-Baseline Action-Layer Simulation",
            "",
            "This is not an order file.",
            "No training was started.",
            "Production order changes = 0.",
            "Stage 12 changes = 0.",
            "Shadow rules only create review triggers, not buy orders.",
            "",
            "## 1. Executive conclusion",
            "The purpose of this pass is to test whether baseline conservatism is too blunt by comparing the current action layer against shadow-only review-trigger candidates.",
            f"Input candidate rows = {input_rows} across {unique_skus} unique SKUs.",
            f"Incremental shadow review triggers = {incremental_triggers}, including {high_priority_incremental} high-priority triggers.",
            f"Dominant rule family = {dominant_rule_family or 'none'}.",
            f"Net review value proxy = {net_value_proxy}.",
            f"Recommendation = {recommendation or FINAL_RECOMMENDATION}.",
            "",
            "## 2. Simulation status view",
            *status_lines,
            "",
            "## 3. Rule-family view",
            *family_lines,
            "",
            "## 4. Governance boundary",
            "This is a review-trigger-only simulation and does not create or simulate buy orders.",
            "Production promotion still requires repeated evidence across more promotions.",
            "No shadow rule in this pass is production-ready.",
            "",
            "## 5. Readiness connection",
            (action_layer_reason or "Action-layer calibration remains an open readiness blocker."),
            (forecast_reason or "Forecast-head reliability remains a separate readiness blocker."),
            "This layer helps decide whether shadow-only review triggers deserve more governed evidence before any production consideration.",
        ]
    )


def build_promotions_action_layer_shadow_vs_baseline_simulation(
    *,
    action_layer_shadow_calibration_candidate_rows_frame: pd.DataFrame,
    action_layer_shadow_calibration_candidate_summary_frame: pd.DataFrame | None = None,
    action_layer_shadow_calibration_candidate_rules_frame: pd.DataFrame | None = None,
    action_layer_unresolved_inspection_rows_frame: pd.DataFrame | None = None,
    pretrain_readiness_summary_frame: pd.DataFrame | None = None,
) -> PromotionsActionLayerShadowVsBaselineSimulationResult:
    rows_frame = _build_rows_frame(action_layer_shadow_calibration_candidate_rows_frame)

    expected_rows = _expected_candidate_rows(action_layer_shadow_calibration_candidate_summary_frame)
    if expected_rows > 0 and expected_rows != int(len(rows_frame.index)):
        raise PromotionsActionLayerShadowVsBaselineSimulationError(
            "Simulation input rows do not match the shadow calibration candidate summary count: "
            f"expected {expected_rows}, found {len(rows_frame.index)}."
        )

    if action_layer_shadow_calibration_candidate_rules_frame is not None and not action_layer_shadow_calibration_candidate_rules_frame.empty:
        _require_columns(
            action_layer_shadow_calibration_candidate_rules_frame,
            ("shadow_rule_family", "row_count"),
            frame_name="action_layer_shadow_calibration_candidate_rules_frame",
        )

    _validate_against_unresolved_rows(rows_frame, action_layer_unresolved_inspection_rows_frame)

    by_rule_family_frame = _build_by_rule_family_frame(rows_frame)
    summary_frame = _build_summary_frame(rows_frame)
    memo_markdown = _build_memo(
        rows_frame=rows_frame,
        by_rule_family_frame=by_rule_family_frame,
        summary_frame=summary_frame,
        pretrain_readiness_summary_frame=pretrain_readiness_summary_frame,
    )

    return PromotionsActionLayerShadowVsBaselineSimulationResult(
        rows_frame=rows_frame,
        by_rule_family_frame=by_rule_family_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_action_layer_shadow_vs_baseline_simulation(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsActionLayerShadowVsBaselineSimulationArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsActionLayerShadowVsBaselineSimulationError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_action_layer_shadow_vs_baseline_simulation(
        action_layer_shadow_calibration_candidate_rows_frame=_read_csv(
            review_artifact_path / INPUT_ROWS_RELATIVE_PATH,
            allow_empty=True,
            empty_columns=[*CORE_COLUMNS],
        ),
        action_layer_shadow_calibration_candidate_summary_frame=_read_csv(
            review_artifact_path / INPUT_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
        action_layer_shadow_calibration_candidate_rules_frame=_read_csv(
            review_artifact_path / INPUT_RULES_RELATIVE_PATH,
            allow_empty=True,
        ),
        action_layer_unresolved_inspection_rows_frame=_read_csv(
            review_artifact_path / UNRESOLVED_ROWS_RELATIVE_PATH,
            allow_empty=True,
        ),
        pretrain_readiness_summary_frame=_read_csv(
            review_artifact_path / READINESS_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
    )

    destination_root = (
        Path(output_root) if output_root is not None else review_artifact_path / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    rows_csv_path = destination_root / "action_layer_shadow_vs_baseline_rows.csv"
    by_rule_family_csv_path = destination_root / "action_layer_shadow_vs_baseline_by_rule_family.csv"
    summary_csv_path = destination_root / "action_layer_shadow_vs_baseline_summary.csv"
    memo_md_path = destination_root / "action_layer_shadow_vs_baseline_memo.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.by_rule_family_frame.copy(), manifest).to_csv(
        by_rule_family_csv_path,
        index=False,
    )
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsActionLayerShadowVsBaselineSimulationArtifacts(
        rows_csv_path=str(rows_csv_path),
        by_rule_family_csv_path=str(by_rule_family_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a governed shadow-vs-baseline action-layer simulation pass "
            "without starting training or changing production logic."
        )
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_action_layer_shadow_vs_baseline_simulation(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("action_layer_shadow_vs_baseline_rows", artifacts.rows_csv_path)
    print("action_layer_shadow_vs_baseline_by_rule_family", artifacts.by_rule_family_csv_path)
    print("action_layer_shadow_vs_baseline_summary", artifacts.summary_csv_path)
    print("action_layer_shadow_vs_baseline_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())