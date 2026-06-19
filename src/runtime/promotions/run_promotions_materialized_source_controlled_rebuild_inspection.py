from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_controlled_rebuild_inspection"
CONTROLLED_REBUILD_FOLDER_NAME = "materialized_source_controlled_governed_rebuild"

REVIEW_ROWS_FILE_NAME = "model_vs_actual_review_rows.csv"
SUMMARY_FILE_NAME = "model_vs_actual_summary.csv"
BY_ACTION_LABEL_FILE_NAME = "model_vs_actual_by_action_label.csv"
BY_DEPARTMENT_FILE_NAME = "model_vs_actual_by_department.csv"
TOP_ERRORS_FILE_NAME = "model_vs_actual_top_errors.csv"
VALIDATION_FILE_NAME = "controlled_governed_rebuild_validation.csv"
QUARANTINE_FILE_NAME = "controlled_governed_rebuild_quarantine_rows.csv"
LINEAGE_FILE_NAME = "controlled_governed_rebuild_lineage.csv"
MEMO_FILE_NAME = "model_vs_actual_memo.md"

REQUIRED_CONTROLLED_REBUILD_FILE_NAMES: tuple[str, ...] = (
    REVIEW_ROWS_FILE_NAME,
    SUMMARY_FILE_NAME,
    BY_ACTION_LABEL_FILE_NAME,
    BY_DEPARTMENT_FILE_NAME,
    TOP_ERRORS_FILE_NAME,
    VALIDATION_FILE_NAME,
    QUARANTINE_FILE_NAME,
    LINEAGE_FILE_NAME,
    MEMO_FILE_NAME,
)

CONTROLLED_REBUILD_INSPECTION_PASS = "CONTROLLED_REBUILD_INSPECTION_PASS"
CONTROLLED_REBUILD_INSPECTION_PASS_WITH_QUARANTINE = "CONTROLLED_REBUILD_INSPECTION_PASS_WITH_QUARANTINE"
CONTROLLED_REBUILD_INSPECTION_BLOCKED_METRIC_RECONCILIATION = (
    "CONTROLLED_REBUILD_INSPECTION_BLOCKED_METRIC_RECONCILIATION"
)
CONTROLLED_REBUILD_INSPECTION_BLOCKED_ARTIFACT_GAP = "CONTROLLED_REBUILD_INSPECTION_BLOCKED_ARTIFACT_GAP"
CONTROLLED_REBUILD_INSPECTION_BLOCKED_GUARDRAIL_FAILURE = "CONTROLLED_REBUILD_INSPECTION_BLOCKED_GUARDRAIL_FAILURE"
CONTROLLED_REBUILD_INSPECTION_BLOCKED_QUALITY_FAILURE = "CONTROLLED_REBUILD_INSPECTION_BLOCKED_QUALITY_FAILURE"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

METRIC_RECONCILIATION_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "expected_value",
    "observed_value",
    "absolute_difference",
    "tolerance",
    "reconciliation_status",
    "notes",
)

QUALITY_CHECK_COLUMNS: tuple[str, ...] = (
    "check_name",
    "check_status",
    "check_flag",
    "details",
)

EXPECTED_REVIEW_ROW_COUNT = 3597
EXPECTED_QUARANTINE_ROW_COUNT = 1
METRIC_TOLERANCE = 0.0001

EXPECTED_SUMMARY_METRICS: dict[str, float] = {
    "FORECAST_BIAS_UNITS_TOTAL": 1235.0,
    "FORECAST_MAE": 0.9938837920489296,
    "FORECAST_RMSE": 1.4243015739614635,
    "FORECAST_CORRELATION": 0.3433437146257653,
    "ACTUAL_GROSS_PROFIT_TOTAL": 11712.009999999998,
    "CAPITAL_LEFT_VALUE_TOTAL": 15064.869999999999,
}

EXPECTED_CONTROLLED_REBUILD_ARTIFACTS: tuple[str, ...] = (
    REVIEW_ROWS_FILE_NAME,
    SUMMARY_FILE_NAME,
    BY_ACTION_LABEL_FILE_NAME,
    BY_DEPARTMENT_FILE_NAME,
    TOP_ERRORS_FILE_NAME,
    VALIDATION_FILE_NAME,
    QUARANTINE_FILE_NAME,
    LINEAGE_FILE_NAME,
    MEMO_FILE_NAME,
)

ACTUAL_FIELDS: tuple[str, ...] = (
    "actual_units",
    "actual_gross_profit",
    "actual_sell_through_pct",
    "capital_left",
    "capital_left_value",
)


class PromotionsMaterializedSourceControlledRebuildInspectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceControlledRebuildInspectionResult:
    selected_promotion: PromotionSelection
    inspection_status: str
    metric_reconciliation_status: str
    review_rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    metric_reconciliation_frame: pd.DataFrame
    quality_checks_frame: pd.DataFrame
    top_error_review_frame: pd.DataFrame
    action_label_review_frame: pd.DataFrame
    department_review_frame: pd.DataFrame
    quarantine_review_frame: pd.DataFrame
    memo_markdown: str
    downstream_overlay_reconstruction_can_be_authored_next: int


@dataclass(frozen=True)
class PromotionsMaterializedSourceControlledRebuildInspectionArtifacts:
    output_root: str
    summary_csv_path: str
    metric_reconciliation_csv_path: str
    quality_checks_csv_path: str
    top_error_review_csv_path: str
    action_label_review_csv_path: str
    department_review_csv_path: str
    quarantine_review_csv_path: str
    memo_md_path: str


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
        raise PromotionsMaterializedSourceControlledRebuildInspectionError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceControlledRebuildInspectionError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceControlledRebuildInspectionError(f"CSV is empty: {csv_path}")
    return frame


def _has_required_controlled_rebuild_files(rebuild_root: Path) -> bool:
    return all((rebuild_root / file_name).exists() for file_name in REQUIRED_CONTROLLED_REBUILD_FILE_NAMES)


def _resolve_rebuild_root(*, packet_root: Path, upstream_root: str | Path | None) -> Path:
    if upstream_root is None:
        return packet_root / CONTROLLED_REBUILD_FOLDER_NAME
    upstream_root_path = Path(upstream_root)
    candidate_roots = (
        upstream_root_path / CONTROLLED_REBUILD_FOLDER_NAME,
        upstream_root_path,
    )
    for candidate_root in candidate_roots:
        if _has_required_controlled_rebuild_files(candidate_root):
            return candidate_root
    candidate_locations = ", ".join(str(path) for path in candidate_roots)
    expected_files = ", ".join(REQUIRED_CONTROLLED_REBUILD_FILE_NAMES)
    raise PromotionsMaterializedSourceControlledRebuildInspectionError(
        "--upstream-root was provided, but required controlled-governed-rebuild artifacts were not found. "
        f"Looked under: {candidate_locations}. Expected files: {expected_files}."
    )


def _read_csv_if_present(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return _read_csv(path, allow_empty=True)


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _quality_check_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
    return {
        "check_name": name,
        "check_status": status,
        "check_flag": int(flag),
        "details": details,
    }


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _blank_mask(series: pd.Series) -> pd.Series:
    return series.map(_normalize_text).eq("")


def _selection_from_inputs(
    *,
    requested_promotion_key: str | None,
    summary_metrics: dict[str, object],
    review_rows_frame: pd.DataFrame,
) -> PromotionSelection:
    resolved_key = requested_promotion_key or _normalize_text(summary_metrics.get("SELECTED_PROMOTION", ""))
    if not resolved_key and "promotion_key" in review_rows_frame.columns:
        keys = [value for value in review_rows_frame["promotion_key"].astype(str).drop_duplicates().tolist() if value]
        resolved_key = keys[0] if keys else "UNKNOWN|||UNKNOWN"
    parts = resolved_key.split("|", 3)
    if len(parts) != 4:
        return PromotionSelection(
            promotion_key=resolved_key,
            promotion_name="",
            promotion_start_date="",
            promotion_end_date="",
        )
    return PromotionSelection(
        promotion_key=resolved_key,
        promotion_name=parts[3],
        promotion_start_date=parts[1],
        promotion_end_date=parts[2],
    )


def _filter_for_promotion(frame: pd.DataFrame, promotion_key: str) -> pd.DataFrame:
    if frame.empty or "promotion_key" not in frame.columns or not promotion_key:
        return frame.copy()
    return frame.loc[frame["promotion_key"].astype(str) == promotion_key].reset_index(drop=True).copy()


def _metric_reconciliation_frame(summary_metrics: dict[str, object]) -> tuple[pd.DataFrame, str]:
    rows: list[dict[str, object]] = []
    all_pass = 1
    for metric_name, expected_value in EXPECTED_SUMMARY_METRICS.items():
        observed_raw = summary_metrics.get(metric_name, "")
        observed_value = pd.to_numeric(pd.Series([observed_raw]), errors="coerce").iloc[0]
        if pd.isna(observed_value):
            all_pass = 0
            rows.append(
                {
                    "metric_name": metric_name,
                    "expected_value": expected_value,
                    "observed_value": _normalize_text(observed_raw),
                    "absolute_difference": "",
                    "tolerance": METRIC_TOLERANCE,
                    "reconciliation_status": "FAIL",
                    "notes": "Observed summary metric is missing or non-numeric.",
                }
            )
            continue
        absolute_difference = abs(float(observed_value) - expected_value)
        within_tolerance = int(absolute_difference <= METRIC_TOLERANCE)
        if not within_tolerance:
            all_pass = 0
        rows.append(
            {
                "metric_name": metric_name,
                "expected_value": expected_value,
                "observed_value": float(observed_value),
                "absolute_difference": absolute_difference,
                "tolerance": METRIC_TOLERANCE,
                "reconciliation_status": "PASS" if within_tolerance else "FAIL",
                "notes": "Observed controlled rebuild summary metric reconciles to the known expected value."
                if within_tolerance
                else "Observed controlled rebuild summary metric does not reconcile to the known expected value.",
            }
        )
    return pd.DataFrame(rows, columns=METRIC_RECONCILIATION_COLUMNS), "PASS" if all_pass else "FAIL"


def _top_error_review_frame(top_errors_frame: pd.DataFrame) -> pd.DataFrame:
    if top_errors_frame.empty:
        return pd.DataFrame(columns=["top_error_review_status", "rank_position_matches", *top_errors_frame.columns])
    review_frame = top_errors_frame.copy()
    review_frame["rank_position_matches"] = [
        int(_normalize_text(value) == str(index + 1))
        for index, value in enumerate(review_frame.get("error_rank", pd.Series(dtype="object")))
    ]
    review_frame["top_error_review_status"] = "TOP_ERROR_REVIEW_READY"
    return review_frame


def _action_label_review_frame(by_action_label_frame: pd.DataFrame) -> pd.DataFrame:
    if by_action_label_frame.empty:
        return pd.DataFrame(columns=["action_label_review_status", *by_action_label_frame.columns])
    review_frame = by_action_label_frame.copy()
    review_frame["action_label_review_status"] = "ACTION_LABEL_OUTCOME_REVIEW_READY"
    return review_frame


def _department_review_frame(by_department_frame: pd.DataFrame) -> pd.DataFrame:
    if by_department_frame.empty:
        return pd.DataFrame(columns=["department_review_status", *by_department_frame.columns])
    review_frame = by_department_frame.copy()
    review_frame["department_review_status"] = "DEPARTMENT_OUTCOME_REVIEW_READY"
    return review_frame


def _quarantine_review_frame(quarantine_rows_frame: pd.DataFrame) -> pd.DataFrame:
    if quarantine_rows_frame.empty:
        return pd.DataFrame(columns=["quarantine_preserved_flag", "quarantine_review_status", *quarantine_rows_frame.columns])
    review_frame = quarantine_rows_frame.copy()
    quarantine_row_numbers = set(
        pd.to_numeric(review_frame.get("source_row_number", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    preserved_flag = int(48 in quarantine_row_numbers and len(review_frame.index) == EXPECTED_QUARANTINE_ROW_COUNT)
    review_frame["quarantine_preserved_flag"] = preserved_flag
    review_frame["quarantine_review_status"] = (
        "QUARANTINE_ROW_48_PRESERVED" if preserved_flag else "QUARANTINE_REVIEW_FAILED"
    )
    return review_frame


def build_promotions_materialized_source_controlled_rebuild_inspection(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceControlledRebuildInspectionResult:
    packet_root_path = Path(packet_root)
    rebuild_root = _resolve_rebuild_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
    )

    artifact_presence = {
        artifact_name: (rebuild_root / artifact_name).exists() for artifact_name in EXPECTED_CONTROLLED_REBUILD_ARTIFACTS
    }
    missing_artifacts = [artifact_name for artifact_name, present in artifact_presence.items() if not present]

    review_rows_frame = _read_csv_if_present(rebuild_root / REVIEW_ROWS_FILE_NAME)
    summary_metrics = _metric_lookup(_read_csv_if_present(rebuild_root / SUMMARY_FILE_NAME))
    by_action_label_frame = _read_csv_if_present(rebuild_root / BY_ACTION_LABEL_FILE_NAME)
    by_department_frame = _read_csv_if_present(rebuild_root / BY_DEPARTMENT_FILE_NAME)
    top_errors_frame = _read_csv_if_present(rebuild_root / TOP_ERRORS_FILE_NAME)
    validation_frame = _read_csv_if_present(rebuild_root / VALIDATION_FILE_NAME)
    quarantine_rows_frame = _read_csv_if_present(rebuild_root / QUARANTINE_FILE_NAME)
    lineage_frame = _read_csv_if_present(rebuild_root / LINEAGE_FILE_NAME)

    selection = _selection_from_inputs(
        requested_promotion_key=promotion_key,
        summary_metrics=summary_metrics,
        review_rows_frame=review_rows_frame,
    )
    review_rows_frame = _filter_for_promotion(review_rows_frame, selection.promotion_key)
    quarantine_rows_frame = _filter_for_promotion(quarantine_rows_frame, selection.promotion_key)
    top_errors_frame = _filter_for_promotion(top_errors_frame, selection.promotion_key)

    top_error_review_frame = _top_error_review_frame(top_errors_frame)
    action_label_review_frame = _action_label_review_frame(by_action_label_frame)
    department_review_frame = _department_review_frame(by_department_frame)
    quarantine_review_frame = _quarantine_review_frame(quarantine_rows_frame)

    metric_reconciliation_frame, metric_reconciliation_status = _metric_reconciliation_frame(summary_metrics)

    review_row_count = len(review_rows_frame.index)
    quarantine_row_count = len(quarantine_rows_frame.index)
    top_error_count = len(top_errors_frame.index)
    action_label_row_count = len(by_action_label_frame.index)
    department_row_count = len(by_department_frame.index)
    production_guardrail_status = _normalize_text(summary_metrics.get("PRODUCTION_GUARDRAIL_STATUS", "FAIL")) or "FAIL"
    stage12_guardrail_status = _normalize_text(summary_metrics.get("STAGE12_GUARDRAIL_STATUS", "FAIL")) or "FAIL"

    review_source_row_ids = review_rows_frame.get("source_row_id", pd.Series(dtype="object")).map(_normalize_text)
    quarantine_row_numbers = set(
        pd.to_numeric(quarantine_rows_frame.get("source_row_number", pd.Series(dtype="object")), errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )
    no_quarantine_rows_included_flag = int(
        not bool(review_source_row_ids.isin({str(value) for value in quarantine_row_numbers}).any())
    )
    no_row_expansion_flag = int(review_row_count == EXPECTED_REVIEW_ROW_COUNT)
    missing_actuals_zero_filled_flag = 0
    if not review_rows_frame.empty:
        missing_actual_units_mask = _blank_mask(review_rows_frame.get("actual_units", pd.Series(dtype="object")))
        if bool(missing_actual_units_mask.any()):
            for field_name in ACTUAL_FIELDS:
                if field_name in review_rows_frame.columns and not bool(
                    _blank_mask(review_rows_frame.loc[missing_actual_units_mask, field_name]).all()
                ):
                    missing_actuals_zero_filled_flag = 1
                    break
            if not missing_actuals_zero_filled_flag and "forecast_error_units" in review_rows_frame.columns:
                if not bool(_blank_mask(review_rows_frame.loc[missing_actual_units_mask, "forecast_error_units"]).all()):
                    missing_actuals_zero_filled_flag = 1
            if not missing_actuals_zero_filled_flag and "absolute_error_units" in review_rows_frame.columns:
                if not bool(_blank_mask(review_rows_frame.loc[missing_actual_units_mask, "absolute_error_units"]).all()):
                    missing_actuals_zero_filled_flag = 1
    lineage_present_flag = int(not lineage_frame.empty)
    expected_artifacts_present_flag = int(not missing_artifacts)
    top_errors_non_empty_flag = int(top_error_count > 0)
    action_label_non_empty_flag = int(action_label_row_count > 0)
    department_non_empty_flag = int(department_row_count > 0)
    quarantine_preserved_flag = int(
        48 in quarantine_row_numbers and quarantine_row_count == EXPECTED_QUARANTINE_ROW_COUNT
    )
    validation_checks_lookup: dict[str, str] = {}
    if not validation_frame.empty and "check_name" in validation_frame.columns and "check_status" in validation_frame.columns:
        validation_checks_lookup = dict(
            zip(validation_frame["check_name"].astype(str), validation_frame["check_status"].astype(str))
        )

    quality_checks_frame = pd.DataFrame(
        [
            _quality_check_row(
                "REVIEW_ROW_COUNT_MATCHES_EXPECTATION",
                "PASS" if review_row_count == EXPECTED_REVIEW_ROW_COUNT else "FAIL",
                int(review_row_count == EXPECTED_REVIEW_ROW_COUNT),
                f"review_rows={review_row_count}, expected={EXPECTED_REVIEW_ROW_COUNT}",
            ),
            _quality_check_row(
                "QUARANTINE_ROW_COUNT_MATCHES_EXPECTATION",
                "PASS" if quarantine_row_count == EXPECTED_QUARANTINE_ROW_COUNT else "FAIL",
                int(quarantine_row_count == EXPECTED_QUARANTINE_ROW_COUNT),
                f"quarantine_rows={quarantine_row_count}, expected={EXPECTED_QUARANTINE_ROW_COUNT}",
            ),
            _quality_check_row(
                "NO_QUARANTINE_ROWS_IN_REVIEW_ROWS",
                "PASS" if no_quarantine_rows_included_flag else "FAIL",
                no_quarantine_rows_included_flag,
                "Quarantine row numbers are absent from the controlled review rows.",
            ),
            _quality_check_row(
                "NO_ROW_EXPANSION",
                "PASS" if no_row_expansion_flag else "FAIL",
                no_row_expansion_flag,
                f"review_rows={review_row_count}, expected={EXPECTED_REVIEW_ROW_COUNT}",
            ),
            _quality_check_row(
                "NO_MISSING_ACTUALS_ZERO_FILLED",
                "PASS" if not missing_actuals_zero_filled_flag else "FAIL",
                int(not missing_actuals_zero_filled_flag),
                "Rows with missing actual units retain blank actual outcome and error fields.",
            ),
            _quality_check_row(
                "PRODUCTION_GUARDRAIL_PASS",
                production_guardrail_status,
                int(production_guardrail_status == "PASS"),
                f"production_guardrail_status={production_guardrail_status}",
            ),
            _quality_check_row(
                "STAGE12_GUARDRAIL_PASS",
                stage12_guardrail_status,
                int(stage12_guardrail_status == "PASS"),
                f"stage12_guardrail_status={stage12_guardrail_status}",
            ),
            _quality_check_row(
                "LINEAGE_PRESENT",
                "PASS" if lineage_present_flag else "FAIL",
                lineage_present_flag,
                f"lineage_rows={len(lineage_frame.index)}",
            ),
            _quality_check_row(
                "ALL_EXPECTED_ARTIFACTS_PRESENT",
                "PASS" if expected_artifacts_present_flag else "FAIL",
                expected_artifacts_present_flag,
                "All expected controlled rebuild artifacts are present."
                if expected_artifacts_present_flag
                else f"missing_artifacts={'; '.join(missing_artifacts)}",
            ),
            _quality_check_row(
                "TOP_ERRORS_ARTIFACT_NON_EMPTY",
                "PASS" if top_errors_non_empty_flag else "FAIL",
                top_errors_non_empty_flag,
                f"top_error_rows={top_error_count}",
            ),
            _quality_check_row(
                "ACTION_LABEL_ARTIFACT_NON_EMPTY",
                "PASS" if action_label_non_empty_flag else "FAIL",
                action_label_non_empty_flag,
                f"action_label_rows={action_label_row_count}",
            ),
            _quality_check_row(
                "DEPARTMENT_ARTIFACT_NON_EMPTY",
                "PASS" if department_non_empty_flag else "FAIL",
                department_non_empty_flag,
                f"department_rows={department_row_count}",
            ),
            _quality_check_row(
                "QUARANTINE_ROW_48_PRESERVED",
                "PASS" if quarantine_preserved_flag else "FAIL",
                quarantine_preserved_flag,
                "Quarantine row 48 remains separate in the controlled rebuild quarantine artifact.",
            ),
            _quality_check_row(
                "UPSTREAM_CONTROLLED_REBUILD_VALIDATION_PASSED",
                "PASS"
                if validation_checks_lookup.get("ALL_PLANNED_ARTIFACTS_WRITTEN", "FAIL") == "PASS"
                else "FAIL",
                int(validation_checks_lookup.get("ALL_PLANNED_ARTIFACTS_WRITTEN", "FAIL") == "PASS"),
                "Controlled governed rebuild validation confirms all planned artifacts were written.",
            ),
        ],
        columns=QUALITY_CHECK_COLUMNS,
    )

    quality_failures = quality_checks_frame.loc[quality_checks_frame["check_status"].astype(str) != "PASS"]
    if missing_artifacts:
        inspection_status = CONTROLLED_REBUILD_INSPECTION_BLOCKED_ARTIFACT_GAP
    elif production_guardrail_status != "PASS" or stage12_guardrail_status != "PASS":
        inspection_status = CONTROLLED_REBUILD_INSPECTION_BLOCKED_GUARDRAIL_FAILURE
    elif metric_reconciliation_status != "PASS":
        inspection_status = CONTROLLED_REBUILD_INSPECTION_BLOCKED_METRIC_RECONCILIATION
    elif not quality_failures.empty:
        inspection_status = CONTROLLED_REBUILD_INSPECTION_BLOCKED_QUALITY_FAILURE
    elif quarantine_row_count > 0:
        inspection_status = CONTROLLED_REBUILD_INSPECTION_PASS_WITH_QUARANTINE
    else:
        inspection_status = CONTROLLED_REBUILD_INSPECTION_PASS

    downstream_overlay_reconstruction_can_be_authored_next = int(
        inspection_status
        in {
            CONTROLLED_REBUILD_INSPECTION_PASS,
            CONTROLLED_REBUILD_INSPECTION_PASS_WITH_QUARANTINE,
        }
    )

    summary_frame = pd.DataFrame(
        [
            _summary_row(
                "SELECTED_PROMOTION",
                selection.promotion_key,
                "Promotion selected for the diagnostics-only controlled rebuild inspection pack.",
            ),
            _summary_row(
                "INSPECTION_STATUS",
                inspection_status,
                "Overall diagnostics-only controlled rebuild inspection status.",
            ),
            _summary_row(
                "METRIC_RECONCILIATION_STATUS",
                metric_reconciliation_status,
                "Whether the persisted controlled rebuild summary metrics reconcile to the known expected values.",
            ),
            _summary_row("REVIEW_ROW_COUNT", review_row_count, "Controlled rebuild review row count."),
            _summary_row(
                "QUARANTINE_ROW_COUNT",
                quarantine_row_count,
                "Controlled rebuild quarantine row count preserved separately.",
            ),
            _summary_row("TOP_ERROR_COUNT", top_error_count, "Controlled rebuild top error review row count."),
            _summary_row(
                "ACTION_LABEL_ROW_COUNT",
                action_label_row_count,
                "Controlled rebuild action-label review row count.",
            ),
            _summary_row(
                "DEPARTMENT_ROW_COUNT",
                department_row_count,
                "Controlled rebuild department review row count.",
            ),
            _summary_row(
                "PRODUCTION_GUARDRAIL_STATUS",
                production_guardrail_status,
                "Production ordering logic remained unchanged through the controlled rebuild inspection.",
            ),
            _summary_row(
                "STAGE12_GUARDRAIL_STATUS",
                stage12_guardrail_status,
                "Stage 12 remained unchanged through the controlled rebuild inspection.",
            ),
            _summary_row(
                "DOWNSTREAM_OVERLAY_RECONSTRUCTION_CAN_BE_AUTHORED_NEXT",
                downstream_overlay_reconstruction_can_be_authored_next,
                "Whether downstream overlay reconstruction can be authored next without running overlay or recalibration yet.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Controlled Rebuild Inspection Pack",
            "",
            "This is a diagnostics-only inspection pack for the controlled governed rebuild outputs.",
            "This does not run review overlay.",
            "This does not run action-layer recalibration.",
            "This does not run shadow-vs-baseline simulation.",
            "This does not run repeat-evidence.",
            "This does not start training.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "This keeps quarantine row 48 separate.",
            "",
            f"Selected promotion: {selection.promotion_key}",
            f"Inspection status: {inspection_status}",
            f"Metric reconciliation status: {metric_reconciliation_status}",
            f"Review row count: {review_row_count}",
            f"Quarantine row count: {quarantine_row_count}",
            f"Top error count: {top_error_count}",
            f"Action label row count: {action_label_row_count}",
            f"Department row count: {department_row_count}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Downstream overlay reconstruction can be authored next: {downstream_overlay_reconstruction_can_be_authored_next}",
            "",
            "## Recommendation",
            (
                "Inspection pack pass confirmed. Author diagnostics-only downstream overlay reconstruction next if needed, but do not run overlay or recalibration yet."
                if downstream_overlay_reconstruction_can_be_authored_next
                else "Do not author downstream overlay reconstruction yet; repair the blocked inspection findings first."
            ),
        ]
    ).strip()

    return PromotionsMaterializedSourceControlledRebuildInspectionResult(
        selected_promotion=selection,
        inspection_status=inspection_status,
        metric_reconciliation_status=metric_reconciliation_status,
        review_rows_frame=review_rows_frame,
        summary_frame=summary_frame,
        metric_reconciliation_frame=metric_reconciliation_frame,
        quality_checks_frame=quality_checks_frame,
        top_error_review_frame=top_error_review_frame,
        action_label_review_frame=action_label_review_frame,
        department_review_frame=department_review_frame,
        quarantine_review_frame=quarantine_review_frame,
        memo_markdown=memo_markdown,
        downstream_overlay_reconstruction_can_be_authored_next=downstream_overlay_reconstruction_can_be_authored_next,
    )


def write_promotions_materialized_source_controlled_rebuild_inspection(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceControlledRebuildInspectionArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_controlled_rebuild_inspection(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_root_path / "controlled_rebuild_inspection_summary.csv"
    metric_reconciliation_csv_path = output_root_path / "controlled_rebuild_inspection_metric_reconciliation.csv"
    quality_checks_csv_path = output_root_path / "controlled_rebuild_inspection_quality_checks.csv"
    top_error_review_csv_path = output_root_path / "controlled_rebuild_inspection_top_error_review.csv"
    action_label_review_csv_path = output_root_path / "controlled_rebuild_inspection_action_label_review.csv"
    department_review_csv_path = output_root_path / "controlled_rebuild_inspection_department_review.csv"
    quarantine_review_csv_path = output_root_path / "controlled_rebuild_inspection_quarantine_review.csv"
    memo_md_path = output_root_path / "controlled_rebuild_inspection_memo.md"

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.metric_reconciliation_frame.to_csv(metric_reconciliation_csv_path, index=False)
    result.quality_checks_frame.to_csv(quality_checks_csv_path, index=False)
    result.top_error_review_frame.to_csv(top_error_review_csv_path, index=False)
    result.action_label_review_frame.to_csv(action_label_review_csv_path, index=False)
    result.department_review_frame.to_csv(department_review_csv_path, index=False)
    result.quarantine_review_frame.to_csv(quarantine_review_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceControlledRebuildInspectionArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_csv_path),
        metric_reconciliation_csv_path=str(metric_reconciliation_csv_path),
        quality_checks_csv_path=str(quality_checks_csv_path),
        top_error_review_csv_path=str(top_error_review_csv_path),
        action_label_review_csv_path=str(action_label_review_csv_path),
        department_review_csv_path=str(department_review_csv_path),
        quarantine_review_csv_path=str(quarantine_review_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only inspection pack for the controlled governed rebuild outputs."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_controlled_rebuild_inspection(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary_frame)
    print("selected_promotion", _normalize_text(metrics.get("SELECTED_PROMOTION", "")))
    print("inspection_status", _normalize_text(metrics.get("INSPECTION_STATUS", "")))
    print("metric_reconciliation_status", _normalize_text(metrics.get("METRIC_RECONCILIATION_STATUS", "")))
    print("review_row_count", _normalize_text(metrics.get("REVIEW_ROW_COUNT", 0)))
    print("quarantine_row_count", _normalize_text(metrics.get("QUARANTINE_ROW_COUNT", 0)))
    print("top_error_count", _normalize_text(metrics.get("TOP_ERROR_COUNT", 0)))
    print("action_label_row_count", _normalize_text(metrics.get("ACTION_LABEL_ROW_COUNT", 0)))
    print("department_row_count", _normalize_text(metrics.get("DEPARTMENT_ROW_COUNT", 0)))
    print("production_guardrail_status", _normalize_text(metrics.get("PRODUCTION_GUARDRAIL_STATUS", "")))
    print("stage12_guardrail_status", _normalize_text(metrics.get("STAGE12_GUARDRAIL_STATUS", "")))
    print(
        "downstream_overlay_reconstruction_can_be_authored_next",
        _normalize_text(metrics.get("DOWNSTREAM_OVERLAY_RECONSTRUCTION_CAN_BE_AUTHORED_NEXT", 0)),
    )
    print("controlled_rebuild_inspection_summary", artifacts.summary_csv_path)
    print("controlled_rebuild_inspection_metric_reconciliation", artifacts.metric_reconciliation_csv_path)
    print("controlled_rebuild_inspection_quality_checks", artifacts.quality_checks_csv_path)
    print("controlled_rebuild_inspection_top_error_review", artifacts.top_error_review_csv_path)
    print("controlled_rebuild_inspection_action_label_review", artifacts.action_label_review_csv_path)
    print("controlled_rebuild_inspection_department_review", artifacts.department_review_csv_path)
    print("controlled_rebuild_inspection_quarantine_review", artifacts.quarantine_review_csv_path)
    print("controlled_rebuild_inspection_memo", artifacts.memo_md_path)
    inspection_status = _normalize_text(metrics.get("INSPECTION_STATUS", ""))
    return 0 if inspection_status in {CONTROLLED_REBUILD_INSPECTION_PASS, CONTROLLED_REBUILD_INSPECTION_PASS_WITH_QUARANTINE} else 1


if __name__ == "__main__":
    raise SystemExit(main())