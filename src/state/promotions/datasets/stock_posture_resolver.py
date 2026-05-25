from __future__ import annotations

"""Authoritative Stage 4 stock-posture integrity resolver.

Canon ownership:
- Applies a single deterministic policy for stock-posture integrity failures.
- Classifies each failing row into source-data defects, transform inconsistencies,
  missing inputs, or explicit business edge cases requiring review.
- Writes governed diagnostics artifacts that preserve fail-loud traceability.
- Does not mutate train-ready rows or silently coerce stock signals.
"""

from dataclasses import dataclass
import json

import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.feature_engineering.shared.ft_group_windows import apply_ft_baseline_windows
from state.promotions.feature_engineering.stock.ft_stock_posture import apply_ft_stock_posture


_NEGATIVE_STOCK_INPUT_COLUMNS = (
    "current_soh",
    "qty_on_order",
    "pl_allocation_qty",
    "store_adjusted_qty",
    "total_units_commited",
    "total_stock_available",
    "stock_basis_units",
)

_NEGATIVE_STOCK_COMPUTED_COLUMNS = (
    "required_implied_units",
    "feature_total_stock_pressure_ratio",
    "feature_stock_sufficiency_gap_units",
    "feature_current_soh_ratio",
    "feature_stock_strain",
)

_NEGATIVE_STOCK_CORE_COLUMNS = (
    "promotion_row_key",
    "store_number",
    "sku_number",
    "promotion_start_date",
    "promotional_end_date",
)

_CLASS_SOURCE_DATA_NEGATIVE = "source_data_negative_inventory"
_CLASS_TRANSFORM_INCONSISTENCY = "transform_inconsistency"
_CLASS_MISSING_INPUTS = "missing_inventory_inputs"
_CLASS_BUSINESS_EDGE_CASE = "business_edge_case_requires_review"

_REPAIRS_STATUS_NOT_REPAIRED = "not_repaired_fail_loud"


@dataclass(frozen=True)
class StockPostureResolutionResult:
    """Resolved stock-posture validation state and diagnostics."""

    failing_row_count: int
    stock_input_columns: tuple[str, ...]
    classified_rows: pd.DataFrame
    summary: dict[str, object]
    details: dict[str, object]


def resolve_stock_posture_integrity(
    frame: pd.DataFrame,
    *,
    run_id: str | None,
    artifact_paths: PromotionArtifactPaths | None,
) -> StockPostureResolutionResult:
    """Classify and persist Stage 4 stock-posture integrity failures.

    Deterministic policy notes:
    - Source negatives remain fail-loud and are never clipped.
    - Business edge cases are still fail-loud in Stage 4; they are only
      classified separately so review workflows can distinguish temporary
      commercial states from hard source defects.
    """

    stock_columns = tuple(
        column_name
        for column_name in _NEGATIVE_STOCK_INPUT_COLUMNS
        if column_name in frame.columns
    )
    negative_mask = _build_negative_stock_mask(frame, list(stock_columns))
    failing_frame = _build_negative_stock_debug_frame(
        frame,
        negative_stock_mask=negative_mask,
    )
    failing_frame = _classify_failing_rows(failing_frame)

    reason_counts = (
        failing_frame.groupby(
            ["stock_posture_failure_class", "stock_posture_failure_reason"], dropna=False
        )
        .size()
        .reset_index(name="row_count")
        .sort_values(["row_count", "stock_posture_failure_class"], ascending=[False, True])
    )
    observed_class_counts = (
        failing_frame["stock_posture_failure_class"].value_counts(dropna=False).to_dict()
    )
    class_counts = {
        _CLASS_SOURCE_DATA_NEGATIVE: int(observed_class_counts.get(_CLASS_SOURCE_DATA_NEGATIVE, 0)),
        _CLASS_TRANSFORM_INCONSISTENCY: int(observed_class_counts.get(_CLASS_TRANSFORM_INCONSISTENCY, 0)),
        _CLASS_MISSING_INPUTS: int(observed_class_counts.get(_CLASS_MISSING_INPUTS, 0)),
        _CLASS_BUSINESS_EDGE_CASE: int(observed_class_counts.get(_CLASS_BUSINESS_EDGE_CASE, 0)),
    }
    summary = {
        "rule": "negative_stock_posture",
        "failing_row_count": int(len(failing_frame.index)),
        "stock_input_columns": list(stock_columns),
        "classification_counts": class_counts,
        "classification_reason_counts": reason_counts.to_dict(orient="records"),
        "computed_stock_posture_column": "computed_stock_posture_value",
        "effective_total_stock_column": "computed_stock_posture_total_stock_available_effective",
        "resolver": "resolve_stock_posture_integrity",
        "repair_policy": "fail_loud_no_silent_repair",
    }

    details = {
        "rule": "negative_stock_posture",
        "row_count": int(len(failing_frame.index)),
        "stock_input_columns": list(stock_columns),
        "computed_stock_posture_column": "computed_stock_posture_value",
        "report_columns": list(failing_frame.columns),
        "classification_counts": summary["classification_counts"],
        "resolver": "resolve_stock_posture_integrity",
    }
    if run_id is not None:
        details["run_id"] = run_id

    if run_id is not None and artifact_paths is not None:
        inspection_root = artifact_paths.inspection_run_root(run_id)
        inspection_root.mkdir(parents=True, exist_ok=True)

        rows_csv_path = inspection_root / "negative_stock_posture_rows.csv"
        rows_parquet_path = inspection_root / "negative_stock_posture_rows.parquet"
        summary_json_path = inspection_root / "negative_stock_posture_summary.json"
        by_reason_csv_path = inspection_root / "negative_stock_posture_by_reason.csv"
        stage4_diagnostics_json_path = inspection_root / "stage4_stock_posture_diagnostics.json"
        repairs_or_escalations_csv_path = inspection_root / "negative_stock_posture_repairs_or_escalations.csv"

        failing_frame.to_csv(rows_csv_path, index=False)
        failing_frame.to_parquet(rows_parquet_path, index=False)
        reason_counts.to_csv(by_reason_csv_path, index=False)
        _build_repairs_or_escalations_frame(failing_frame).to_csv(
            repairs_or_escalations_csv_path,
            index=False,
        )
        summary_json_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        diagnostics_payload = {
            **summary,
            "run_id": run_id,
            "negative_stock_posture_rows_csv_path": str(rows_csv_path),
            "negative_stock_posture_rows_parquet_path": str(rows_parquet_path),
            "negative_stock_posture_summary_path": str(summary_json_path),
            "negative_stock_posture_by_reason_path": str(by_reason_csv_path),
            "negative_stock_posture_repairs_or_escalations_path": str(repairs_or_escalations_csv_path),
        }
        stage4_diagnostics_json_path.write_text(
            json.dumps(diagnostics_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        details.update(
            {
                "csv_path": str(rows_csv_path),
                "parquet_path": str(rows_parquet_path),
                "report_path": str(summary_json_path),
                "negative_stock_posture_rows_csv_path": str(rows_csv_path),
                "negative_stock_posture_rows_parquet_path": str(rows_parquet_path),
                "negative_stock_posture_summary_path": str(summary_json_path),
                "negative_stock_posture_by_reason_path": str(by_reason_csv_path),
                "stage4_stock_posture_diagnostics_path": str(stage4_diagnostics_json_path),
                "negative_stock_posture_repairs_or_escalations_path": str(repairs_or_escalations_csv_path),
            }
        )

    return StockPostureResolutionResult(
        failing_row_count=int(len(failing_frame.index)),
        stock_input_columns=stock_columns,
        classified_rows=failing_frame,
        summary=summary,
        details=details,
    )


def _classify_failing_rows(frame: pd.DataFrame) -> pd.DataFrame:
    classified = frame.copy()
    source_flags = _negative_source_flags(classified)

    missing_required_columns = [
        column_name
        for column_name in (
            "current_soh",
            "qty_on_order",
            "total_stock_available",
            "stock_basis_units",
            "required_implied_units",
        )
        if column_name in classified.columns
    ]
    missing_inputs_flag = (
        classified[missing_required_columns].isna().any(axis=1)
        if missing_required_columns
        else pd.Series(False, index=classified.index)
    )
    business_edge_case_flag = (
        _numeric_series(classified, "current_soh") < -1.0
    ) & (
        _numeric_series(classified, "total_stock_available") >= 0.0
    ) & (
        _numeric_series(classified, "qty_on_order") > 0.0
    )
    transform_inconsistency_flag = (
        _numeric_series(classified, "current_soh") < -1.0
    ) & (
        _numeric_series(classified, "total_stock_available") >= 0.0
    ) & (
        _numeric_series(classified, "qty_on_order") <= 0.0
    )
    source_data_negative_flag = source_flags & ~(missing_inputs_flag | business_edge_case_flag | transform_inconsistency_flag)

    failure_class = pd.Series(_CLASS_SOURCE_DATA_NEGATIVE, index=classified.index, dtype="object")
    failure_reason = pd.Series(
        "negative stock inputs detected in source inventory fields",
        index=classified.index,
        dtype="object",
    )
    failure_class = failure_class.mask(transform_inconsistency_flag, _CLASS_TRANSFORM_INCONSISTENCY)
    failure_reason = failure_reason.mask(
        transform_inconsistency_flag,
        "current_soh is negative while total_stock_available is non-negative without on-order coverage",
    )
    failure_class = failure_class.mask(business_edge_case_flag, _CLASS_BUSINESS_EDGE_CASE)
    failure_reason = failure_reason.mask(
        business_edge_case_flag,
        "current_soh is negative but on-order inventory yields a non-negative total stock state",
    )
    failure_class = failure_class.mask(missing_inputs_flag, _CLASS_MISSING_INPUTS)
    failure_reason = failure_reason.mask(
        missing_inputs_flag,
        "required inventory inputs are missing or non-numeric",
    )

    classified["stock_posture_failure_class"] = failure_class
    classified["stock_posture_failure_reason"] = failure_reason
    classified["source_data_negative_flag"] = source_data_negative_flag.fillna(False)
    classified["transform_inconsistency_flag"] = transform_inconsistency_flag.fillna(False)
    classified["missing_inventory_inputs_flag"] = missing_inputs_flag.fillna(False)
    classified["business_edge_case_flag"] = business_edge_case_flag.fillna(False)
    classified["repair_status"] = _REPAIRS_STATUS_NOT_REPAIRED
    classified["escalation_status"] = "escalated_stage4_fail_loud"
    classified["row_outcome"] = "blocked"
    return classified


def _negative_source_flags(frame: pd.DataFrame) -> pd.Series:
    stock_columns = [
        column_name for column_name in _NEGATIVE_STOCK_INPUT_COLUMNS if column_name in frame.columns
    ]
    if not stock_columns:
        return pd.Series(False, index=frame.index)
    negative_flags = pd.DataFrame(False, index=frame.index, columns=stock_columns)
    for column_name in stock_columns:
        values = _numeric_series(frame, column_name)
        if column_name in {"current_soh", "total_stock_available"}:
            negative_flags[column_name] = values < -1.0
        else:
            negative_flags[column_name] = values < 0.0
    return negative_flags.any(axis=1).fillna(False)


def _build_repairs_or_escalations_frame(failing_frame: pd.DataFrame) -> pd.DataFrame:
    selected_columns: list[str] = []
    for column_name in (
        *_NEGATIVE_STOCK_CORE_COLUMNS,
        "stock_posture_failure_class",
        "stock_posture_failure_reason",
        "repair_status",
        "escalation_status",
        "row_outcome",
        "source_data_negative_flag",
        "transform_inconsistency_flag",
        "missing_inventory_inputs_flag",
        "business_edge_case_flag",
    ):
        if column_name in failing_frame.columns and column_name not in selected_columns:
            selected_columns.append(column_name)
    return failing_frame.loc[:, selected_columns]


def _build_negative_stock_mask(
    frame: pd.DataFrame,
    stock_columns: list[str],
) -> pd.Series:
    if not stock_columns:
        return pd.Series(False, index=frame.index)
    negative_flags = pd.DataFrame(False, index=frame.index, columns=stock_columns)
    for column_name in stock_columns:
        values = _numeric_series(frame, column_name)
        if column_name in {"current_soh", "total_stock_available"}:
            # Source systems encode unknown stock state as -1; keep this
            # compatibility sentinel while still blocking values below -1.
            negative_flags[column_name] = values < -1.0
        else:
            negative_flags[column_name] = values < 0.0
    return negative_flags.any(axis=1).fillna(False)


def _build_negative_stock_debug_frame(
    frame: pd.DataFrame,
    *,
    negative_stock_mask: pd.Series,
) -> pd.DataFrame:
    debug_frame = frame.loc[negative_stock_mask].copy()
    debug_frame = apply_ft_baseline_windows(debug_frame)
    debug_frame = apply_ft_stock_posture(debug_frame)
    if "promotion_start_date" not in debug_frame.columns and "promotion_start_date_date" in debug_frame.columns:
        debug_frame["promotion_start_date"] = debug_frame["promotion_start_date_date"]
    if "promotional_end_date" not in debug_frame.columns and "promotional_end_date_date" in debug_frame.columns:
        debug_frame["promotional_end_date"] = debug_frame["promotional_end_date_date"]

    effective_total_stock = _numeric_series(debug_frame, "total_stock_available").where(
        lambda values: values > 0.0,
        _numeric_series(debug_frame, "stock_basis_units"),
    )
    debug_frame["computed_stock_posture_total_stock_available_effective"] = effective_total_stock
    debug_frame["computed_stock_posture_value"] = debug_frame.get(
        "feature_stock_sufficiency_gap_units",
        effective_total_stock - _numeric_series(debug_frame, "required_implied_units"),
    )
    debug_stock_columns = [
        column_name for column_name in _NEGATIVE_STOCK_INPUT_COLUMNS if column_name in debug_frame.columns
    ]
    negative_flags = pd.DataFrame(False, index=debug_frame.index, columns=debug_stock_columns)
    for column_name in debug_stock_columns:
        values = _numeric_series(debug_frame, column_name)
        if column_name in {"current_soh", "total_stock_available"}:
            negative_flags[column_name] = values < -1.0
        else:
            negative_flags[column_name] = values < 0.0
    debug_frame["negative_stock_source_columns"] = negative_flags.apply(
        lambda row: ",".join(
            column_name for column_name, is_negative in row.items() if bool(is_negative)
        ),
        axis=1,
    )

    selected_columns: list[str] = []
    for column_name in (
        *_NEGATIVE_STOCK_CORE_COLUMNS,
        *_NEGATIVE_STOCK_INPUT_COLUMNS,
        *_NEGATIVE_STOCK_COMPUTED_COLUMNS,
        "computed_stock_posture_total_stock_available_effective",
        "computed_stock_posture_value",
        "negative_stock_source_columns",
    ):
        if column_name in debug_frame.columns and column_name not in selected_columns:
            selected_columns.append(column_name)
    return debug_frame.loc[:, selected_columns]


def _numeric_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(pd.NA, index=frame.index, dtype="Float64")
    return pd.to_numeric(frame[column_name], errors="coerce")
