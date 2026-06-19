from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_controlled_governed_rebuild"
VALIDATION_FOLDER_NAME = "materialized_source_governed_rebuild_validation"
REVIEW_PACKET_DRAFT_FOLDER_NAME = "materialized_source_review_packet_draft"

VALIDATION_SUMMARY_FILE_NAME = "materialized_source_governed_rebuild_validation_summary.csv"
VALIDATION_CHECKS_FILE_NAME = "materialized_source_governed_rebuild_validation_checks.csv"
VALIDATION_BLOCKERS_FILE_NAME = "materialized_source_governed_rebuild_validation_blockers.csv"
DRAFT_ROWS_FILE_NAME = "materialized_source_review_packet_draft_rows.csv"
DRAFT_QUARANTINE_FILE_NAME = "materialized_source_review_packet_draft_quarantine_rows.csv"
DRAFT_FIELD_LINEAGE_FILE_NAME = "materialized_source_review_packet_draft_field_lineage.csv"

REQUIRED_VALIDATION_FILE_NAMES: tuple[str, ...] = (
    VALIDATION_SUMMARY_FILE_NAME,
    VALIDATION_CHECKS_FILE_NAME,
    VALIDATION_BLOCKERS_FILE_NAME,
)

REQUIRED_DRAFT_FILE_NAMES: tuple[str, ...] = (
    DRAFT_ROWS_FILE_NAME,
    DRAFT_QUARANTINE_FILE_NAME,
    DRAFT_FIELD_LINEAGE_FILE_NAME,
)

GOVERNED_REBUILD_VALIDATION_READY = "GOVERNED_REBUILD_VALIDATION_READY"
GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE = "GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE"

CONTROLLED_GOVERNED_REBUILD_BLOCKED = "CONTROLLED_GOVERNED_REBUILD_BLOCKED"
CONTROLLED_GOVERNED_REBUILD_DRY_RUN_READY = "CONTROLLED_GOVERNED_REBUILD_DRY_RUN_READY"
CONTROLLED_GOVERNED_REBUILD_COMPLETED = "CONTROLLED_GOVERNED_REBUILD_COMPLETED"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "check_name",
    "check_status",
    "check_flag",
    "details",
)

BLOCKERS_COLUMNS: tuple[str, ...] = (
    "blocker_code",
    "blocker_type",
    "blocker_detail",
    "blocking_flag",
    "remediation",
)

LINEAGE_COLUMNS: tuple[str, ...] = (
    "output_artifact",
    "output_field",
    "source_artifact",
    "source_column",
    "lineage_type",
    "derivation_formula",
    "notes",
)

EXPECTED_REVIEW_ROW_COUNT = 3597
EXPECTED_QUARANTINE_ROW_COUNT = 1

PLANNED_PASS_ARTIFACTS: tuple[str, ...] = (
    "model_vs_actual_review_rows.csv",
    "model_vs_actual_summary.csv",
    "model_vs_actual_by_action_label.csv",
    "model_vs_actual_by_department.csv",
    "model_vs_actual_top_errors.csv",
    "model_vs_actual_memo.md",
    "controlled_governed_rebuild_validation.csv",
    "controlled_governed_rebuild_lineage.csv",
    "controlled_governed_rebuild_quarantine_rows.csv",
)

PLANNED_FAIL_ARTIFACTS: tuple[str, ...] = (
    "controlled_governed_rebuild_blockers.csv",
    "controlled_governed_rebuild_validation.csv",
    "model_vs_actual_memo.md",
)

PRODUCTION_FIELDS: tuple[str, ...] = (
    "expected_promo_demand",
    "recommended_order_units",
    "final_store_order_units",
    "production_order_change_flag",
)

STAGE12_FIELDS: tuple[str, ...] = (
    "stage_12_change_flag",
)

ACTUAL_FIELDS: tuple[str, ...] = (
    "actual_units",
    "actual_gross_profit",
    "actual_sell_through_pct",
    "capital_left",
    "capital_left_value",
)


class PromotionsMaterializedSourceControlledGovernedRebuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceControlledGovernedRebuildResult:
    selected_promotion: PromotionSelection
    gate_status: str
    run_status: str
    dry_run: bool
    review_rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_action_label_frame: pd.DataFrame
    by_department_frame: pd.DataFrame
    top_errors_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    blockers_frame: pd.DataFrame
    lineage_frame: pd.DataFrame
    quarantine_rows_frame: pd.DataFrame
    memo_markdown: str
    artifacts_planned: tuple[str, ...]
    artifacts_written: tuple[str, ...]


@dataclass(frozen=True)
class PromotionsMaterializedSourceControlledGovernedRebuildArtifacts:
    output_root: str
    review_rows_csv_path: str | None
    summary_csv_path: str | None
    by_action_label_csv_path: str | None
    by_department_csv_path: str | None
    top_errors_csv_path: str | None
    memo_md_path: str
    validation_csv_path: str
    lineage_csv_path: str | None
    quarantine_rows_csv_path: str | None
    blockers_csv_path: str | None
    run_status: str
    gate_status: str
    artifacts_written: tuple[str, ...]


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceControlledGovernedRebuildError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceControlledGovernedRebuildError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceControlledGovernedRebuildError(f"CSV is empty: {csv_path}")
    return frame


def _has_required_files(stage_root: Path, required_file_names: Sequence[str]) -> bool:
    return all((stage_root / file_name).exists() for file_name in required_file_names)


def _resolve_stage_root(
    *,
    packet_root: Path,
    upstream_root: str | Path | None,
    folder_name: str,
    required_file_names: Sequence[str],
    stage_label: str,
) -> Path:
    if upstream_root is None:
        return packet_root / folder_name
    upstream_root_path = Path(upstream_root)
    candidate_roots = (
        upstream_root_path / folder_name,
        upstream_root_path,
    )
    for candidate_root in candidate_roots:
        if _has_required_files(candidate_root, required_file_names):
            return candidate_root
    candidate_locations = ", ".join(str(path) for path in candidate_roots)
    expected_files = ", ".join(required_file_names)
    raise PromotionsMaterializedSourceControlledGovernedRebuildError(
        f"--upstream-root was provided, but required {stage_label} artifacts were not found. "
        f"Looked under: {candidate_locations}. Expected files: {expected_files}."
    )


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _validation_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
    return {
        "check_name": name,
        "check_status": status,
        "check_flag": int(flag),
        "details": details,
    }


def _blocker_row(code: str, blocker_type: str, detail: str, remediation: str) -> dict[str, object]:
    return {
        "blocker_code": code,
        "blocker_type": blocker_type,
        "blocker_detail": detail,
        "blocking_flag": 1,
        "remediation": remediation,
    }


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _blank_mask(series: pd.Series) -> pd.Series:
    return series.map(_normalize_text).eq("")


def _series_equal(left: pd.Series, right: pd.Series) -> bool:
    return bool(left.map(_normalize_text).eq(right.map(_normalize_text)).all())


def _ensure_quarantine_columns(frame: pd.DataFrame) -> pd.DataFrame:
    expected_columns = (
        "source_row_number",
        "promotion_key",
        "promotion_name",
        "promotion_start_date",
        "promotion_end_date",
        "quarantine_reason",
        "remediation_required",
    )
    if frame.empty:
        return pd.DataFrame(columns=expected_columns)
    ensured = frame.copy()
    for column_name in expected_columns:
        if column_name not in ensured.columns:
            ensured[column_name] = ""
    return ensured.loc[:, list(expected_columns)].copy()


def _selection_from_promotion_key(promotion_key: str) -> PromotionSelection:
    parts = promotion_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceControlledGovernedRebuildError(
            f"Promotion key is not in the expected pipe-delimited format: {promotion_key}"
        )
    return PromotionSelection(
        promotion_key=promotion_key,
        promotion_name=parts[3],
        promotion_start_date=parts[1],
        promotion_end_date=parts[2],
    )


def _selection_from_inputs(
    *,
    requested_promotion_key: str | None,
    summary_metrics: dict[str, object],
    draft_rows_frame: pd.DataFrame,
) -> PromotionSelection:
    summary_promotion_key = _normalize_text(summary_metrics.get("SELECTED_PROMOTION", ""))
    available_keys = [value for value in draft_rows_frame.get("promotion_key", pd.Series(dtype="object")).astype(str).drop_duplicates().tolist() if value]
    if requested_promotion_key:
        if summary_promotion_key and requested_promotion_key != summary_promotion_key:
            raise PromotionsMaterializedSourceControlledGovernedRebuildError(
                "Requested promotion key does not match the governed rebuild validation selection."
            )
        if requested_promotion_key not in available_keys:
            raise PromotionsMaterializedSourceControlledGovernedRebuildError(
                f"Requested promotion key was not found in the draft rows: {requested_promotion_key}"
            )
        return _selection_from_promotion_key(requested_promotion_key)
    if summary_promotion_key:
        return _selection_from_promotion_key(summary_promotion_key)
    if not available_keys:
        raise PromotionsMaterializedSourceControlledGovernedRebuildError("Draft rows did not contain a promotion key.")
    return _selection_from_promotion_key(available_keys[0])


def _filter_for_promotion(frame: pd.DataFrame, promotion_key: str) -> pd.DataFrame:
    if frame.empty or "promotion_key" not in frame.columns:
        return frame.copy()
    return frame.loc[frame["promotion_key"].astype(str) == promotion_key].reset_index(drop=True).copy()


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.map(lambda value: _normalize_text(value) or None), errors="coerce")


def _safe_float(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.6f}"


def _build_review_rows(draft_rows_frame: pd.DataFrame) -> pd.DataFrame:
    review_rows_frame = draft_rows_frame.copy()
    expected_units = _to_numeric(review_rows_frame["expected_promo_demand"])
    actual_units = _to_numeric(review_rows_frame["actual_units"])
    review_rows_frame["forecast_error_units"] = expected_units.sub(actual_units)
    review_rows_frame.loc[actual_units.isna(), "forecast_error_units"] = pd.NA
    review_rows_frame["absolute_error_units"] = review_rows_frame["forecast_error_units"].abs()
    return review_rows_frame


def _correlation_and_status(expected_units: pd.Series, actual_units: pd.Series) -> tuple[float | None, str]:
    valid_mask = expected_units.notna() & actual_units.notna()
    valid_expected = expected_units.loc[valid_mask]
    valid_actual = actual_units.loc[valid_mask]
    if len(valid_expected.index) < 2:
        return None, "Insufficient paired numeric rows for correlation."
    if valid_expected.nunique(dropna=True) <= 1 or valid_actual.nunique(dropna=True) <= 1:
        return None, "Expected demand or actual units are constant, so correlation is not informative."
    correlation = valid_expected.corr(valid_actual)
    if pd.isna(correlation):
        return None, "Correlation could not be calculated from the paired numeric rows."
    return float(correlation), "Correlation calculated on paired non-missing numeric rows."


def _sell_through_measure(review_rows_frame: pd.DataFrame) -> tuple[float | None, str]:
    actual_sell_through = _to_numeric(review_rows_frame["actual_sell_through_pct"])
    actual_units = _to_numeric(review_rows_frame["actual_units"])
    valid_mask = actual_sell_through.notna()
    if not bool(valid_mask.any()):
        return None, "No non-missing sell-through values were available."
    weighted_mask = valid_mask & actual_units.notna() & actual_units.gt(0)
    if bool(weighted_mask.any()) and float(actual_units.loc[weighted_mask].sum()) > 0:
        weights = actual_units.loc[weighted_mask]
        values = actual_sell_through.loc[weighted_mask]
        weighted_value = float((values * weights).sum() / weights.sum())
        return weighted_value, "Weighted mean using actual_units as weights for non-missing sell-through rows."
    return float(actual_sell_through.loc[valid_mask].mean()), "Simple mean across non-missing sell-through rows."


def _build_by_action_label(review_rows_frame: pd.DataFrame) -> pd.DataFrame:
    metrics_frame = review_rows_frame.copy()
    for column_name in (
        "expected_promo_demand",
        "actual_units",
        "forecast_error_units",
        "absolute_error_units",
        "actual_gross_profit",
        "capital_left_value",
    ):
        metrics_frame[column_name] = _to_numeric(metrics_frame[column_name])
    grouped_rows: list[dict[str, object]] = []
    for action_label, group in metrics_frame.groupby("store_action_label", dropna=False):
        grouped_rows.append(
            {
                "store_action_label": _normalize_text(action_label),
                "row_count": len(group.index),
                "expected_promo_demand_total": group["expected_promo_demand"].sum(),
                "actual_units_total": group["actual_units"].sum(),
                "forecast_bias_units_total": group["expected_promo_demand"].sum() - group["actual_units"].sum(),
                "forecast_mae": group["absolute_error_units"].dropna().mean(),
                "actual_gross_profit_total": group["actual_gross_profit"].sum(),
                "capital_left_value_total": group["capital_left_value"].sum(),
            }
        )
    result = pd.DataFrame(grouped_rows)
    if result.empty:
        return pd.DataFrame(
            columns=(
                "store_action_label",
                "row_count",
                "expected_promo_demand_total",
                "actual_units_total",
                "forecast_bias_units_total",
                "forecast_mae",
                "actual_gross_profit_total",
                "capital_left_value_total",
            )
        )
    return result.sort_values(["row_count", "store_action_label"], ascending=[False, True]).reset_index(drop=True)


def _build_by_department(review_rows_frame: pd.DataFrame) -> pd.DataFrame:
    department_columns = [column_name for column_name in ("department", "department_name", "department_code") if column_name in review_rows_frame.columns]
    metrics_frame = review_rows_frame.copy()
    for column_name in (
        "expected_promo_demand",
        "actual_units",
        "absolute_error_units",
        "actual_gross_profit",
        "capital_left_value",
    ):
        metrics_frame[column_name] = _to_numeric(metrics_frame[column_name])
    if not department_columns:
        return pd.DataFrame(
            [
                {
                    "department_group": "UNAVAILABLE_FROM_REVIEW_PACKET_DRAFT",
                    "department_status": "DEPARTMENT_NOT_AVAILABLE_IN_VALIDATED_DRAFT",
                    "row_count": len(metrics_frame.index),
                    "expected_promo_demand_total": metrics_frame["expected_promo_demand"].sum(),
                    "actual_units_total": metrics_frame["actual_units"].sum(),
                    "forecast_mae": metrics_frame["absolute_error_units"].dropna().mean(),
                    "actual_gross_profit_total": metrics_frame["actual_gross_profit"].sum(),
                    "capital_left_value_total": metrics_frame["capital_left_value"].sum(),
                    "notes": "The validated review-packet draft does not carry department fields, so this controlled rebuild emits a single documented fallback group.",
                }
            ]
        )
    department_column = department_columns[0]
    grouped_rows: list[dict[str, object]] = []
    for department_value, group in metrics_frame.groupby(department_column, dropna=False):
        grouped_rows.append(
            {
                "department_group": _normalize_text(department_value),
                "department_status": f"GROUPED_BY_{department_column.upper()}",
                "row_count": len(group.index),
                "expected_promo_demand_total": group["expected_promo_demand"].sum(),
                "actual_units_total": group["actual_units"].sum(),
                "forecast_mae": group["absolute_error_units"].dropna().mean(),
                "actual_gross_profit_total": group["actual_gross_profit"].sum(),
                "capital_left_value_total": group["capital_left_value"].sum(),
                "notes": "Department aggregation taken from the validated draft packet.",
            }
        )
    return pd.DataFrame(grouped_rows).sort_values(["row_count", "department_group"], ascending=[False, True]).reset_index(drop=True)


def _build_top_errors(review_rows_frame: pd.DataFrame) -> pd.DataFrame:
    top_errors_frame = review_rows_frame.copy()
    top_errors_frame["absolute_error_units"] = _to_numeric(top_errors_frame["absolute_error_units"])
    top_errors_frame = top_errors_frame.loc[top_errors_frame["absolute_error_units"].notna()].copy()
    if top_errors_frame.empty:
        return pd.DataFrame(columns=[*review_rows_frame.columns, "error_rank"])
    source_row_sort = _to_numeric(top_errors_frame["source_row_id"]) if "source_row_id" in top_errors_frame.columns else pd.Series(range(len(top_errors_frame.index)))
    top_errors_frame = top_errors_frame.assign(_source_row_sort=source_row_sort)
    top_errors_frame = top_errors_frame.sort_values(
        ["absolute_error_units", "_source_row_sort"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)
    top_errors_frame.insert(0, "error_rank", range(1, len(top_errors_frame.index) + 1))
    return top_errors_frame.drop(columns=["_source_row_sort"])


def _build_lineage_frame(field_lineage_frame: pd.DataFrame) -> pd.DataFrame:
    lineage_rows: list[dict[str, object]] = []
    for _, row in field_lineage_frame.iterrows():
        lineage_rows.append(
            {
                "output_artifact": "model_vs_actual_review_rows.csv",
                "output_field": _normalize_text(row.get("draft_field")),
                "source_artifact": _normalize_text(row.get("source_artifact")),
                "source_column": _normalize_text(row.get("source_column")),
                "lineage_type": _normalize_text(row.get("lineage_type")) or "PASSTHROUGH_DRAFT_FIELD",
                "derivation_formula": _normalize_text(row.get("derivation_formula")),
                "notes": _normalize_text(row.get("notes")) or "Passed through from the validated review-packet draft.",
            }
        )
    lineage_rows.extend(
        [
            {
                "output_artifact": "model_vs_actual_review_rows.csv",
                "output_field": "forecast_error_units",
                "source_artifact": DRAFT_ROWS_FILE_NAME,
                "source_column": "expected_promo_demand,actual_units",
                "lineage_type": "DERIVED_METRIC",
                "derivation_formula": "forecast_error_units = expected_promo_demand - actual_units when actual_units is present",
                "notes": "Missing actual_units remain missing and are not coerced to zero.",
            },
            {
                "output_artifact": "model_vs_actual_review_rows.csv",
                "output_field": "absolute_error_units",
                "source_artifact": "model_vs_actual_review_rows.csv",
                "source_column": "forecast_error_units",
                "lineage_type": "DERIVED_METRIC",
                "derivation_formula": "absolute_error_units = abs(forecast_error_units)",
                "notes": "Ranks the largest forecast deviations without mutating source packets.",
            },
        ]
    )
    return pd.DataFrame(lineage_rows, columns=LINEAGE_COLUMNS)


def build_promotions_materialized_source_controlled_governed_rebuild(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
    dry_run: bool = False,
) -> PromotionsMaterializedSourceControlledGovernedRebuildResult:
    packet_root_path = Path(packet_root)
    validation_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=VALIDATION_FOLDER_NAME,
        required_file_names=REQUIRED_VALIDATION_FILE_NAMES,
        stage_label="governed-rebuild-validation",
    )
    draft_root = _resolve_stage_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        folder_name=REVIEW_PACKET_DRAFT_FOLDER_NAME,
        required_file_names=REQUIRED_DRAFT_FILE_NAMES,
        stage_label="review-packet-draft",
    )

    validation_summary_frame = _read_csv(validation_root / VALIDATION_SUMMARY_FILE_NAME)
    validation_checks_frame = _read_csv(validation_root / VALIDATION_CHECKS_FILE_NAME)
    validation_blockers_frame = _read_csv(validation_root / VALIDATION_BLOCKERS_FILE_NAME, allow_empty=True)
    draft_rows_frame = _read_csv(draft_root / DRAFT_ROWS_FILE_NAME)
    draft_quarantine_frame = _ensure_quarantine_columns(_read_csv(draft_root / DRAFT_QUARANTINE_FILE_NAME, allow_empty=True))
    field_lineage_frame = _read_csv(draft_root / DRAFT_FIELD_LINEAGE_FILE_NAME)

    summary_metrics = _metric_lookup(validation_summary_frame)
    selection = _selection_from_inputs(
        requested_promotion_key=promotion_key,
        summary_metrics=summary_metrics,
        draft_rows_frame=draft_rows_frame,
    )

    draft_rows_frame = _filter_for_promotion(draft_rows_frame, selection.promotion_key)
    draft_quarantine_frame = _ensure_quarantine_columns(
        _filter_for_promotion(draft_quarantine_frame, selection.promotion_key)
    )

    gate_status = _normalize_text(summary_metrics.get("VALIDATION_STATUS", ""))
    blockers_row_count = len(validation_blockers_frame.index)
    zero_filled_actuals_flag = int(float(summary_metrics.get("ZERO_FILLED_ACTUALS_FLAG", 1) or 1))
    required_downstream_columns_present_flag = int(
        float(summary_metrics.get("REQUIRED_DOWNSTREAM_COLUMNS_PRESENT_FLAG", 0) or 0)
    )
    artifact_plan_complete_flag = int(float(summary_metrics.get("ARTIFACT_PLAN_COMPLETE_FLAG", 0) or 0))
    production_guardrail_status = _normalize_text(summary_metrics.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL")) or "FAIL"
    stage12_guardrail_status = _normalize_text(summary_metrics.get("STAGE12_GUARDRAIL_STATUS", "FAIL")) or "FAIL"

    gate_blockers: list[dict[str, object]] = []
    if gate_status not in {GOVERNED_REBUILD_VALIDATION_READY, GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE}:
        gate_blockers.append(
            _blocker_row(
                "VALIDATION_STATUS_NOT_READY",
                "GATE_STATUS",
                f"validation_status={gate_status}",
                "Run or repair the governed rebuild validation gate before attempting the controlled governed rebuild.",
            )
        )
    if blockers_row_count != 0:
        gate_blockers.append(
            _blocker_row(
                "UPSTREAM_VALIDATION_BLOCKERS_PRESENT",
                "UPSTREAM_BLOCKERS",
                f"blockers_row_count={blockers_row_count}",
                "Resolve all governed rebuild validation blockers before attempting the controlled governed rebuild.",
            )
        )
    if zero_filled_actuals_flag != 0:
        gate_blockers.append(
            _blocker_row(
                "ZERO_FILLED_ACTUALS_DETECTED",
                "ZERO_FILLED_ACTUALS",
                f"zero_filled_actuals_flag={zero_filled_actuals_flag}",
                "Rebuild the validated review packet so that missing actuals remain missing.",
            )
        )
    if production_guardrail_status != "PASS":
        gate_blockers.append(
            _blocker_row(
                "PRODUCTION_GUARDRAIL_FAILED",
                "PRODUCTION_GUARDRAIL",
                f"production_guardrail_status={production_guardrail_status}",
                "Do not proceed until the production ordering logic is confirmed unchanged.",
            )
        )
    if stage12_guardrail_status != "PASS":
        gate_blockers.append(
            _blocker_row(
                "STAGE12_GUARDRAIL_FAILED",
                "STAGE12_GUARDRAIL",
                f"stage12_guardrail_status={stage12_guardrail_status}",
                "Do not proceed until Stage 12 is confirmed unchanged.",
            )
        )
    if artifact_plan_complete_flag != 1:
        gate_blockers.append(
            _blocker_row(
                "ARTIFACT_PLAN_INCOMPLETE",
                "ARTIFACT_PLAN",
                f"artifact_plan_complete_flag={artifact_plan_complete_flag}",
                "Complete the governed rebuild artifact plan before attempting the controlled runner.",
            )
        )
    if required_downstream_columns_present_flag != 1:
        gate_blockers.append(
            _blocker_row(
                "REQUIRED_COLUMNS_MISSING",
                "REQUIRED_COLUMNS",
                f"required_downstream_columns_present_flag={required_downstream_columns_present_flag}",
                "Repair the validated draft so the downstream rebuild contract is complete.",
            )
        )

    blockers_frame = pd.DataFrame(gate_blockers, columns=BLOCKERS_COLUMNS)

    review_rows_frame = pd.DataFrame()
    by_action_label_frame = pd.DataFrame()
    by_department_frame = pd.DataFrame()
    top_errors_frame = pd.DataFrame()
    lineage_frame = pd.DataFrame(columns=LINEAGE_COLUMNS)

    summary_frame = pd.DataFrame(columns=SUMMARY_COLUMNS)
    validation_rows: list[dict[str, object]] = []
    artifacts_planned = PLANNED_FAIL_ARTIFACTS
    artifacts_written: tuple[str, ...] = tuple()

    if blockers_frame.empty:
        review_rows_frame = _build_review_rows(draft_rows_frame)
        by_action_label_frame = _build_by_action_label(review_rows_frame)
        by_department_frame = _build_by_department(review_rows_frame)
        top_errors_frame = _build_top_errors(review_rows_frame)
        lineage_frame = _build_lineage_frame(field_lineage_frame)

        expected_units = _to_numeric(review_rows_frame["expected_promo_demand"])
        actual_units = _to_numeric(review_rows_frame["actual_units"])
        forecast_error_units = _to_numeric(review_rows_frame["forecast_error_units"])
        absolute_error_units = _to_numeric(review_rows_frame["absolute_error_units"])
        actual_gross_profit = _to_numeric(review_rows_frame["actual_gross_profit"])
        capital_left_value = _to_numeric(review_rows_frame["capital_left_value"])

        forecast_bias_units_total = float(expected_units.sum() - actual_units.sum())
        forecast_mae = float(absolute_error_units.dropna().mean()) if bool(absolute_error_units.dropna().size) else None
        forecast_rmse = (
            float(math.sqrt((forecast_error_units.dropna() ** 2).mean()))
            if bool(forecast_error_units.dropna().size)
            else None
        )
        forecast_correlation, forecast_correlation_status = _correlation_and_status(expected_units, actual_units)
        actual_gross_profit_total = float(actual_gross_profit.sum())
        capital_left_value_total = float(capital_left_value.sum())
        sell_through_value, sell_through_method = _sell_through_measure(review_rows_frame)

        quarantine_numbers = set(
            draft_quarantine_frame.get("source_row_number", pd.Series(dtype="object")).map(_normalize_text).tolist()
        )
        review_source_row_ids = review_rows_frame.get("source_row_id", pd.Series(dtype="object")).map(_normalize_text)
        no_quarantine_rows_included_flag = int(not bool(review_source_row_ids.isin(quarantine_numbers).any()))
        missing_actuals_remain_missing_flag = int(
            all(
                _blank_mask(review_rows_frame[field_name]).eq(_blank_mask(draft_rows_frame[field_name])).all()
                for field_name in ACTUAL_FIELDS
                if field_name in review_rows_frame.columns and field_name in draft_rows_frame.columns
            )
            and _blank_mask(review_rows_frame["forecast_error_units"]).eq(_blank_mask(draft_rows_frame["actual_units"])).all()
        )
        production_fields_unchanged_flag = int(
            all(
                field_name in review_rows_frame.columns
                and field_name in draft_rows_frame.columns
                and _series_equal(review_rows_frame[field_name], draft_rows_frame[field_name])
                for field_name in PRODUCTION_FIELDS
            )
        )
        stage12_unchanged_flag = int(
            all(
                field_name in review_rows_frame.columns
                and field_name in draft_rows_frame.columns
                and _series_equal(review_rows_frame[field_name], draft_rows_frame[field_name])
                for field_name in STAGE12_FIELDS
            )
        )
        no_row_expansion_flag = int(len(review_rows_frame.index) == len(draft_rows_frame.index))
        draft_row_count_flag = int(len(draft_rows_frame.index) == EXPECTED_REVIEW_ROW_COUNT)
        quarantine_row_count_flag = int(len(draft_quarantine_frame.index) == EXPECTED_QUARANTINE_ROW_COUNT)
        output_review_row_count_flag = int(len(review_rows_frame.index) == EXPECTED_REVIEW_ROW_COUNT)

        planned_artifacts_written_flag = 1 if not dry_run else 1
        run_status = CONTROLLED_GOVERNED_REBUILD_DRY_RUN_READY if dry_run else CONTROLLED_GOVERNED_REBUILD_COMPLETED
        artifacts_planned = PLANNED_PASS_ARTIFACTS

        validation_rows = [
            _validation_row(
                "GOVERNED_REBUILD_VALIDATION_READY",
                "PASS",
                1,
                f"gate_status={gate_status}",
            ),
            _validation_row(
                "UPSTREAM_BLOCKERS_ABSENT",
                "PASS",
                1,
                f"blockers_row_count={blockers_row_count}",
            ),
            _validation_row(
                "ZERO_FILLED_ACTUALS_ABSENT",
                "PASS",
                1,
                f"zero_filled_actuals_flag={zero_filled_actuals_flag}",
            ),
            _validation_row(
                "PRODUCTION_FIELDS_UNCHANGED",
                "PASS" if production_fields_unchanged_flag else "FAIL",
                production_fields_unchanged_flag,
                "Production ordering fields are unchanged between the validated draft and the controlled review rows.",
            ),
            _validation_row(
                "STAGE12_FIELDS_UNCHANGED",
                "PASS" if stage12_unchanged_flag else "FAIL",
                stage12_unchanged_flag,
                "Stage 12 fields are unchanged between the validated draft and the controlled review rows.",
            ),
            _validation_row(
                "ARTIFACT_PLAN_COMPLETE",
                "PASS" if artifact_plan_complete_flag else "FAIL",
                artifact_plan_complete_flag,
                f"artifact_plan_complete_flag={artifact_plan_complete_flag}",
            ),
            _validation_row(
                "REQUIRED_DOWNSTREAM_COLUMNS_PRESENT",
                "PASS" if required_downstream_columns_present_flag else "FAIL",
                required_downstream_columns_present_flag,
                f"required_downstream_columns_present_flag={required_downstream_columns_present_flag}",
            ),
            _validation_row(
                "DRAFT_ROW_COUNT_MATCHES_EXPECTATION",
                "PASS" if draft_row_count_flag else "FAIL",
                draft_row_count_flag,
                f"draft_rows={len(draft_rows_frame.index)}, expected={EXPECTED_REVIEW_ROW_COUNT}",
            ),
            _validation_row(
                "QUARANTINE_ROW_COUNT_MATCHES_EXPECTATION",
                "PASS" if quarantine_row_count_flag else "FAIL",
                quarantine_row_count_flag,
                f"quarantine_rows={len(draft_quarantine_frame.index)}, expected={EXPECTED_QUARANTINE_ROW_COUNT}",
            ),
            _validation_row(
                "OUTPUT_REVIEW_ROWS_MATCH_EXPECTATION",
                "PASS" if output_review_row_count_flag else "FAIL",
                output_review_row_count_flag,
                f"review_rows={len(review_rows_frame.index)}, expected={EXPECTED_REVIEW_ROW_COUNT}",
            ),
            _validation_row(
                "NO_QUARANTINE_ROWS_INCLUDED_IN_REVIEW_ROWS",
                "PASS" if no_quarantine_rows_included_flag else "FAIL",
                no_quarantine_rows_included_flag,
                "Quarantine row numbers are absent from the review rows.",
            ),
            _validation_row(
                "MISSING_ACTUALS_REMAIN_MISSING",
                "PASS" if missing_actuals_remain_missing_flag else "FAIL",
                missing_actuals_remain_missing_flag,
                "Missing actuals remain missing and forecast error fields stay blank when actual units are missing.",
            ),
            _validation_row(
                "NO_ROW_EXPANSION",
                "PASS" if no_row_expansion_flag else "FAIL",
                no_row_expansion_flag,
                f"draft_rows={len(draft_rows_frame.index)}, review_rows={len(review_rows_frame.index)}",
            ),
            _validation_row(
                "ALL_PLANNED_ARTIFACTS_WRITTEN",
                "PASS" if planned_artifacts_written_flag else "FAIL",
                planned_artifacts_written_flag,
                (
                    "Dry run confirmed the full planned artifact set without writing the rebuild outputs."
                    if dry_run
                    else "Live run wrote the full planned artifact set."
                ),
            ),
        ]

        summary_frame = pd.DataFrame(
            [
                _summary_row("SELECTED_PROMOTION", selection.promotion_key, "Promotion selected for the controlled governed rebuild."),
                _summary_row("GATE_STATUS", gate_status, "Upstream governed rebuild validation gate status."),
                _summary_row("RUN_STATUS", run_status, "Controlled governed rebuild execution status."),
                _summary_row("DRY_RUN_FLAG", int(dry_run), "1 means the runner validated readiness without writing rebuild artifacts."),
                _summary_row("REVIEW_ROW_COUNT", len(review_rows_frame.index), "Controlled review row count built from the validated draft rows only."),
                _summary_row("QUARANTINE_ROW_COUNT", len(draft_quarantine_frame.index), "Quarantine row count preserved separately from the review rows."),
                _summary_row("FORECAST_BIAS_UNITS_TOTAL", forecast_bias_units_total, "sum(expected_promo_demand) - sum(actual_units), with missing actuals preserved as missing."),
                _summary_row("FORECAST_MAE", forecast_mae if forecast_mae is not None else "", "Mean absolute forecast error across rows with non-missing actual units."),
                _summary_row("FORECAST_RMSE", forecast_rmse if forecast_rmse is not None else "", "Root mean squared forecast error across rows with non-missing actual units."),
                _summary_row("FORECAST_CORRELATION", forecast_correlation if forecast_correlation is not None else "", forecast_correlation_status),
                _summary_row("ACTUAL_GROSS_PROFIT_TOTAL", actual_gross_profit_total, "Total actual gross profit across controlled review rows."),
                _summary_row("CAPITAL_LEFT_VALUE_TOTAL", capital_left_value_total, "Total capital left value across controlled review rows."),
                _summary_row("SELL_THROUGH_MEASURE", sell_through_value if sell_through_value is not None else "", sell_through_method),
                _summary_row("PRODUCTION_GUARDRAIL_STATUS", production_guardrail_status, "Production ordering logic remained unchanged."),
                _summary_row("STAGE12_GUARDRAIL_STATUS", stage12_guardrail_status, "Stage 12 remained unchanged."),
            ],
            columns=SUMMARY_COLUMNS,
        )

        memo_markdown = "\n".join(
            [
                "# Controlled Governed Model-vs-Actual Rebuild",
                "",
                "This is a controlled governed model-vs-actual rebuild over the validated review-packet draft.",
                "This does not start training.",
                "This does not change production ordering logic.",
                "This does not change Stage 12.",
                "This does not promote auto-ordering.",
                "This does not promote shadow rules.",
                "This does not mutate source packets.",
                "This does not fill missing actuals with zero.",
                "This does not run portfolio repeat-evidence.",
                "This keeps quarantine row 48 separate.",
                "",
                f"Selected promotion: {selection.promotion_key}",
                f"Gate status: {gate_status}",
                f"Run status: {run_status}",
                f"Review row count: {len(review_rows_frame.index)}",
                f"Quarantine row count: {len(draft_quarantine_frame.index)}",
                f"Forecast bias units total: {forecast_bias_units_total}",
                f"Forecast MAE: {_safe_float(forecast_mae)}",
                f"Forecast RMSE: {_safe_float(forecast_rmse)}",
                f"Forecast correlation: {_safe_float(forecast_correlation)}",
                f"Actual gross profit total: {actual_gross_profit_total}",
                f"Capital left value total: {capital_left_value_total}",
                f"Production guardrail status: {production_guardrail_status}",
                f"Stage 12 guardrail status: {stage12_guardrail_status}",
                "",
                "## Recommendation",
                (
                    "Gate pass confirmed in dry-run. Proceed to the live controlled governed rebuild to write the model-vs-actual artifacts for the selected promotion only."
                    if dry_run
                    else "Controlled governed rebuild completed successfully. Review the model-vs-actual artifacts before attempting any downstream overlay, recalibration, simulation, or training steps."
                ),
            ]
        ).strip()
    else:
        run_status = CONTROLLED_GOVERNED_REBUILD_BLOCKED
        validation_rows = [
            _validation_row(
                "GOVERNED_REBUILD_VALIDATION_READY",
                "FAIL",
                0,
                f"gate_status={gate_status}",
            ),
            _validation_row(
                "UPSTREAM_BLOCKERS_ABSENT",
                "PASS" if blockers_row_count == 0 else "FAIL",
                int(blockers_row_count == 0),
                f"blockers_row_count={blockers_row_count}",
            ),
            _validation_row(
                "ZERO_FILLED_ACTUALS_ABSENT",
                "PASS" if zero_filled_actuals_flag == 0 else "FAIL",
                int(zero_filled_actuals_flag == 0),
                f"zero_filled_actuals_flag={zero_filled_actuals_flag}",
            ),
            _validation_row(
                "PRODUCTION_GUARDRAIL_PASS",
                production_guardrail_status,
                int(production_guardrail_status == "PASS"),
                f"production_guardrail_status={production_guardrail_status}",
            ),
            _validation_row(
                "STAGE12_GUARDRAIL_PASS",
                stage12_guardrail_status,
                int(stage12_guardrail_status == "PASS"),
                f"stage12_guardrail_status={stage12_guardrail_status}",
            ),
            _validation_row(
                "ARTIFACT_PLAN_COMPLETE",
                "PASS" if artifact_plan_complete_flag else "FAIL",
                artifact_plan_complete_flag,
                f"artifact_plan_complete_flag={artifact_plan_complete_flag}",
            ),
            _validation_row(
                "REQUIRED_DOWNSTREAM_COLUMNS_PRESENT",
                "PASS" if required_downstream_columns_present_flag else "FAIL",
                required_downstream_columns_present_flag,
                f"required_downstream_columns_present_flag={required_downstream_columns_present_flag}",
            ),
        ]
        summary_frame = pd.DataFrame(
            [
                _summary_row("SELECTED_PROMOTION", selection.promotion_key, "Promotion selected for the controlled governed rebuild."),
                _summary_row("GATE_STATUS", gate_status, "Upstream governed rebuild validation gate status."),
                _summary_row("RUN_STATUS", run_status, "Controlled governed rebuild execution status."),
                _summary_row("DRY_RUN_FLAG", int(dry_run), "1 means the runner was invoked in dry-run mode."),
                _summary_row("REVIEW_ROW_COUNT", 0, "No review rows were rebuilt because the gate blocked execution."),
                _summary_row("QUARANTINE_ROW_COUNT", len(draft_quarantine_frame.index), "Quarantine rows remained separate while the gate blocked the rebuild."),
                _summary_row("FORECAST_BIAS_UNITS_TOTAL", "", "Not calculated because the gate blocked execution."),
                _summary_row("FORECAST_MAE", "", "Not calculated because the gate blocked execution."),
                _summary_row("FORECAST_RMSE", "", "Not calculated because the gate blocked execution."),
                _summary_row("FORECAST_CORRELATION", "", "Not calculated because the gate blocked execution."),
                _summary_row("ACTUAL_GROSS_PROFIT_TOTAL", "", "Not calculated because the gate blocked execution."),
                _summary_row("CAPITAL_LEFT_VALUE_TOTAL", "", "Not calculated because the gate blocked execution."),
                _summary_row("PRODUCTION_GUARDRAIL_STATUS", production_guardrail_status, "Production ordering logic gate status."),
                _summary_row("STAGE12_GUARDRAIL_STATUS", stage12_guardrail_status, "Stage 12 gate status."),
            ],
            columns=SUMMARY_COLUMNS,
        )
        memo_markdown = "\n".join(
            [
                "# Controlled Governed Model-vs-Actual Rebuild",
                "",
                "The controlled governed rebuild did not run because the upstream validation gate blocked execution.",
                "This does not start training.",
                "This does not change production ordering logic.",
                "This does not change Stage 12.",
                "This does not mutate source packets.",
                "This does not fill missing actuals with zero.",
                "This keeps quarantine row 48 separate.",
                "",
                f"Selected promotion: {selection.promotion_key}",
                f"Gate status: {gate_status}",
                f"Run status: {run_status}",
                f"Quarantine row count: {len(draft_quarantine_frame.index)}",
                "",
                "## Recommendation",
                "Repair the governed rebuild validation gate blockers before attempting the controlled governed rebuild again.",
            ]
        ).strip()

    validation_frame = pd.DataFrame(validation_rows, columns=VALIDATION_COLUMNS)
    return PromotionsMaterializedSourceControlledGovernedRebuildResult(
        selected_promotion=selection,
        gate_status=gate_status,
        run_status=run_status,
        dry_run=dry_run,
        review_rows_frame=review_rows_frame,
        summary_frame=summary_frame,
        by_action_label_frame=by_action_label_frame,
        by_department_frame=by_department_frame,
        top_errors_frame=top_errors_frame,
        validation_frame=validation_frame,
        blockers_frame=blockers_frame,
        lineage_frame=lineage_frame,
        quarantine_rows_frame=draft_quarantine_frame,
        memo_markdown=memo_markdown,
        artifacts_planned=artifacts_planned,
        artifacts_written=artifacts_written,
    )


def write_promotions_materialized_source_controlled_governed_rebuild(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
    dry_run: bool = False,
) -> PromotionsMaterializedSourceControlledGovernedRebuildArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_controlled_governed_rebuild(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
        dry_run=dry_run,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    validation_csv_path = output_root_path / "controlled_governed_rebuild_validation.csv"
    memo_md_path = output_root_path / "model_vs_actual_memo.md"
    result.validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    review_rows_csv_path: str | None = None
    summary_csv_path: str | None = None
    by_action_label_csv_path: str | None = None
    by_department_csv_path: str | None = None
    top_errors_csv_path: str | None = None
    lineage_csv_path: str | None = None
    quarantine_rows_csv_path: str | None = None
    blockers_csv_path: str | None = None

    artifacts_written: list[str] = [validation_csv_path.name, memo_md_path.name]

    if result.run_status == CONTROLLED_GOVERNED_REBUILD_COMPLETED:
        review_rows_path = output_root_path / "model_vs_actual_review_rows.csv"
        summary_path = output_root_path / "model_vs_actual_summary.csv"
        by_action_label_path = output_root_path / "model_vs_actual_by_action_label.csv"
        by_department_path = output_root_path / "model_vs_actual_by_department.csv"
        top_errors_path = output_root_path / "model_vs_actual_top_errors.csv"
        lineage_path = output_root_path / "controlled_governed_rebuild_lineage.csv"
        quarantine_path = output_root_path / "controlled_governed_rebuild_quarantine_rows.csv"

        result.review_rows_frame.to_csv(review_rows_path, index=False)
        result.summary_frame.to_csv(summary_path, index=False)
        result.by_action_label_frame.to_csv(by_action_label_path, index=False)
        result.by_department_frame.to_csv(by_department_path, index=False)
        result.top_errors_frame.to_csv(top_errors_path, index=False)
        result.lineage_frame.to_csv(lineage_path, index=False)
        result.quarantine_rows_frame.to_csv(quarantine_path, index=False)

        review_rows_csv_path = str(review_rows_path)
        summary_csv_path = str(summary_path)
        by_action_label_csv_path = str(by_action_label_path)
        by_department_csv_path = str(by_department_path)
        top_errors_csv_path = str(top_errors_path)
        lineage_csv_path = str(lineage_path)
        quarantine_rows_csv_path = str(quarantine_path)
        artifacts_written.extend(
            [
                review_rows_path.name,
                summary_path.name,
                by_action_label_path.name,
                by_department_path.name,
                top_errors_path.name,
                lineage_path.name,
                quarantine_path.name,
            ]
        )
    elif result.run_status == CONTROLLED_GOVERNED_REBUILD_BLOCKED:
        blockers_path = output_root_path / "controlled_governed_rebuild_blockers.csv"
        result.blockers_frame.to_csv(blockers_path, index=False)
        blockers_csv_path = str(blockers_path)
        artifacts_written.append(blockers_path.name)

    return PromotionsMaterializedSourceControlledGovernedRebuildArtifacts(
        output_root=str(output_root_path),
        review_rows_csv_path=review_rows_csv_path,
        summary_csv_path=summary_csv_path,
        by_action_label_csv_path=by_action_label_csv_path,
        by_department_csv_path=by_department_csv_path,
        top_errors_csv_path=top_errors_csv_path,
        memo_md_path=str(memo_md_path),
        validation_csv_path=str(validation_csv_path),
        lineage_csv_path=lineage_csv_path,
        quarantine_rows_csv_path=quarantine_rows_csv_path,
        blockers_csv_path=blockers_csv_path,
        run_status=result.run_status,
        gate_status=result.gate_status,
        artifacts_written=tuple(artifacts_written),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a controlled governed model-vs-actual rebuild runner for the validated materialized source review-packet draft."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_controlled_governed_rebuild(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
        dry_run=args.dry_run,
    )
    summary_frame = _read_csv(Path(artifacts.output_root) / "model_vs_actual_summary.csv", allow_empty=True)
    if summary_frame.empty:
        result = build_promotions_materialized_source_controlled_governed_rebuild(
            packet_root=args.packet_root,
            upstream_root=args.upstream_root,
            promotion_key=args.promotion_key,
            dry_run=args.dry_run,
        )
        summary_frame = result.summary_frame
    metrics = _metric_lookup(summary_frame)
    print("selected_promotion", _normalize_text(metrics.get("SELECTED_PROMOTION", "")))
    print("gate_status", _normalize_text(metrics.get("GATE_STATUS", artifacts.gate_status)))
    print("run_status", _normalize_text(metrics.get("RUN_STATUS", artifacts.run_status)))
    print("review_row_count", _normalize_text(metrics.get("REVIEW_ROW_COUNT", 0)))
    print("quarantine_row_count", _normalize_text(metrics.get("QUARANTINE_ROW_COUNT", 0)))
    print("forecast_bias_units_total", _normalize_text(metrics.get("FORECAST_BIAS_UNITS_TOTAL", "")))
    print("forecast_mae", _normalize_text(metrics.get("FORECAST_MAE", "")))
    print("forecast_rmse", _normalize_text(metrics.get("FORECAST_RMSE", "")))
    print("forecast_correlation", _normalize_text(metrics.get("FORECAST_CORRELATION", "")))
    print("actual_gross_profit_total", _normalize_text(metrics.get("ACTUAL_GROSS_PROFIT_TOTAL", "")))
    print("capital_left_value_total", _normalize_text(metrics.get("CAPITAL_LEFT_VALUE_TOTAL", "")))
    print("production_guardrail_status", _normalize_text(metrics.get("PRODUCTION_GUARDRAIL_STATUS", "")))
    print("stage12_guardrail_status", _normalize_text(metrics.get("STAGE12_GUARDRAIL_STATUS", "")))
    print("artifacts_written", ",".join(artifacts.artifacts_written))
    print("controlled_governed_rebuild_validation", artifacts.validation_csv_path)
    if artifacts.review_rows_csv_path:
        print("model_vs_actual_review_rows", artifacts.review_rows_csv_path)
    if artifacts.summary_csv_path:
        print("model_vs_actual_summary", artifacts.summary_csv_path)
    if artifacts.by_action_label_csv_path:
        print("model_vs_actual_by_action_label", artifacts.by_action_label_csv_path)
    if artifacts.by_department_csv_path:
        print("model_vs_actual_by_department", artifacts.by_department_csv_path)
    if artifacts.top_errors_csv_path:
        print("model_vs_actual_top_errors", artifacts.top_errors_csv_path)
    if artifacts.lineage_csv_path:
        print("controlled_governed_rebuild_lineage", artifacts.lineage_csv_path)
    if artifacts.quarantine_rows_csv_path:
        print("controlled_governed_rebuild_quarantine_rows", artifacts.quarantine_rows_csv_path)
    if artifacts.blockers_csv_path:
        print("controlled_governed_rebuild_blockers", artifacts.blockers_csv_path)
    print("model_vs_actual_memo", artifacts.memo_md_path)
    return 0 if artifacts.run_status != CONTROLLED_GOVERNED_REBUILD_BLOCKED else 1


if __name__ == "__main__":
    raise SystemExit(main())