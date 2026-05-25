from __future__ import annotations

"""Validation helpers for promotions training and scoring datasets."""

from dataclasses import asdict, dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.datasets.stock_posture_resolver import resolve_stock_posture_integrity


# Default safety guardrails for QUARANTINE_AND_PROCEED policy. These exist so a
# systemic upstream regression (e.g., entire stock feed broken) still trips
# fail-loud instead of silently shipping a degraded training dataset.
DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_FRACTION = 0.05
DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_ABSOLUTE = 5000
REQUIRED_GOVERNED_NUMERIC_KEY_COLUMNS: tuple[str, ...] = (
    "store_number_key",
    "sku_number_key",
)


class NegativeStockPosturePolicy(str, Enum):
    """Governed treatment for negative stock-posture rows.

    FAIL_LOUD: legacy behavior. Any negative stock row raises immediately.
    QUARANTINE_AND_PROCEED: classify and quarantine failing rows into governed
        diagnostics, then drop them from the training dataset and proceed.
        Still raises if the quarantine count exceeds the configured
        absolute or fractional safety guardrail (treated as systemic
        upstream regression rather than tolerable defect).
    """

    FAIL_LOUD = "fail_loud"
    QUARANTINE_AND_PROCEED = "quarantine_and_proceed"


class PromotionDatasetValidationError(ValueError):
    """Raised when a promotions dataset violates a governed validation rule."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class PromotionDatasetValidationReport:
    row_count: int
    duplicate_grain_rows: int
    invalid_date_rows: int
    negative_stock_rows: int
    target_null_rates: dict[str, float]
    negative_stock_policy: str = NegativeStockPosturePolicy.FAIL_LOUD.value
    negative_stock_quarantined_rows: int = 0
    negative_stock_quarantine_classification_counts: dict[str, int] = field(default_factory=dict)
    negative_stock_quarantined_grain_keys: tuple[str, ...] = ()
    negative_stock_diagnostics: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["negative_stock_quarantined_grain_keys"] = list(
            self.negative_stock_quarantined_grain_keys
        )
        return payload


def validate_promotion_dataset(
    frame: pd.DataFrame,
    *,
    grain_column: str,
    target_columns: tuple[str, ...],
    max_target_null_rate: float,
    run_id: str | None = None,
    artifact_paths: PromotionArtifactPaths | None = None,
    negative_stock_policy: NegativeStockPosturePolicy | str = NegativeStockPosturePolicy.FAIL_LOUD,
    negative_stock_quarantine_max_fraction: float = DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_FRACTION,
    negative_stock_quarantine_max_absolute: int = DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_ABSOLUTE,
) -> PromotionDatasetValidationReport:
    """Validate grain uniqueness, date ranges, stock posture, and target coverage.

    The negative stock posture treatment is selectable via
    ``negative_stock_policy``. Under FAIL_LOUD (default) any failing row
    raises immediately. Under QUARANTINE_AND_PROCEED failing rows are
    classified into governed diagnostics and reported back so the caller
    (the assembler) can drop them from the training dataset; the validator
    still raises if the quarantine count exceeds either the absolute or
    fractional safety guardrail (a systemic upstream regression).
    """

    if isinstance(negative_stock_policy, str):
        negative_stock_policy = NegativeStockPosturePolicy(negative_stock_policy)

    duplicate_rows = int(frame[grain_column].duplicated().sum()) if grain_column in frame.columns else len(frame.index)
    invalid_date_rows = int(
        (
            pd.to_datetime(frame.get("promotion_start_date_date"), errors="coerce")
            > pd.to_datetime(frame.get("promotional_end_date_date"), errors="coerce")
        ).fillna(False).sum()
    )
    stock_resolution = resolve_stock_posture_integrity(
        frame,
        run_id=run_id,
        artifact_paths=artifact_paths,
    )
    negative_stock_rows = stock_resolution.failing_row_count
    target_null_rates = {
        column_name: float(frame[column_name].isna().mean())
        for column_name in target_columns
        if column_name in frame.columns
    }
    if duplicate_rows > 0:
        raise PromotionDatasetValidationError(
            f"Duplicate promotion grain rows detected: {duplicate_rows}"
        )
    if invalid_date_rows > 0:
        raise PromotionDatasetValidationError(
            f"Invalid promotion date ranges detected: {invalid_date_rows}"
        )
    governed_key_issues = _governed_numeric_key_issues(frame)
    if governed_key_issues:
        issue_text = ", ".join(
            f"{column_name}={details['invalid_row_count']}"
            for column_name, details in governed_key_issues.items()
        )
        raise PromotionDatasetValidationError(
            f"Invalid governed numeric key rows detected: {issue_text}",
            details={
                "rule": "governed_numeric_key",
                "invalid_key_columns": list(governed_key_issues.keys()),
                "invalid_key_row_count": int(
                    max(details["invalid_row_count"] for details in governed_key_issues.values())
                ),
                "column_issues": governed_key_issues,
                "repair_policy": "fail_loud_no_silent_key_coercion",
            },
        )

    quarantined_rows = 0
    quarantined_keys: tuple[str, ...] = ()
    quarantine_class_counts: dict[str, int] = {}
    if negative_stock_rows > 0:
        if negative_stock_policy is NegativeStockPosturePolicy.FAIL_LOUD:
            raise PromotionDatasetValidationError(
                f"Negative stock posture rows detected: {negative_stock_rows}",
                details=stock_resolution.details,
            )
        # QUARANTINE_AND_PROCEED policy: enforce absolute + fractional
        # guardrails so a systemic upstream regression still trips fail-loud.
        denominator = max(int(len(frame.index)), 1)
        observed_fraction = float(negative_stock_rows) / float(denominator)
        guardrail_breached_reason: str | None = None
        if negative_stock_rows > negative_stock_quarantine_max_absolute:
            guardrail_breached_reason = (
                f"absolute quarantine guardrail breached: {negative_stock_rows} "
                f"failing rows exceeds max_absolute={negative_stock_quarantine_max_absolute}"
            )
        elif observed_fraction > negative_stock_quarantine_max_fraction:
            guardrail_breached_reason = (
                f"fractional quarantine guardrail breached: "
                f"{observed_fraction:.6f} of dataset is failing, exceeds "
                f"max_fraction={negative_stock_quarantine_max_fraction:.6f} "
                f"(absolute={negative_stock_rows} of {denominator})"
            )
        if guardrail_breached_reason is not None:
            raise PromotionDatasetValidationError(
                (
                    f"Negative stock posture rows detected: {negative_stock_rows}; "
                    f"quarantine policy refused to proceed because {guardrail_breached_reason}"
                ),
                details={
                    **stock_resolution.details,
                    "negative_stock_policy": negative_stock_policy.value,
                    "quarantine_guardrail_breached_reason": guardrail_breached_reason,
                    "negative_stock_quarantine_max_absolute": int(
                        negative_stock_quarantine_max_absolute
                    ),
                    "negative_stock_quarantine_max_fraction": float(
                        negative_stock_quarantine_max_fraction
                    ),
                },
            )
        # Within guardrails: capture grain keys and classification counts so
        # the assembler can drop these rows from the training dataset.
        if grain_column in stock_resolution.classified_rows.columns:
            quarantined_keys = tuple(
                str(value)
                for value in stock_resolution.classified_rows[grain_column].tolist()
            )
        quarantined_rows = int(negative_stock_rows)
        quarantine_class_counts = {
            str(class_name): int(count)
            for class_name, count in stock_resolution.summary.get(
                "classification_counts", {}
            ).items()
        }

    excessive_null_targets = {
        column_name: null_rate
        for column_name, null_rate in target_null_rates.items()
        if null_rate > max_target_null_rate
    }
    if excessive_null_targets:
        raise PromotionDatasetValidationError(
            f"Target null-rate threshold exceeded: {excessive_null_targets}"
        )
    return PromotionDatasetValidationReport(
        row_count=len(frame.index),
        duplicate_grain_rows=duplicate_rows,
        invalid_date_rows=invalid_date_rows,
        negative_stock_rows=negative_stock_rows,
        target_null_rates=target_null_rates,
        negative_stock_policy=negative_stock_policy.value,
        negative_stock_quarantined_rows=quarantined_rows,
        negative_stock_quarantine_classification_counts=quarantine_class_counts,
        negative_stock_quarantined_grain_keys=quarantined_keys,
        negative_stock_diagnostics=dict(stock_resolution.details) if quarantined_rows > 0 else {},
    )


def _governed_numeric_key_issues(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    issues: dict[str, dict[str, object]] = {}
    for column_name in REQUIRED_GOVERNED_NUMERIC_KEY_COLUMNS:
        if column_name not in frame.columns:
            continue
        series = frame[column_name]
        numeric = pd.to_numeric(series, errors="coerce").astype("float64")
        finite_mask = pd.Series(np.isfinite(numeric.to_numpy()), index=series.index)
        null_mask = series.isna()
        non_numeric_mask = series.notna() & numeric.isna()
        non_integer_mask = series.notna() & numeric.notna() & (
            ~finite_mask | ~numeric.mod(1).eq(0)
        )
        invalid_mask = null_mask | non_numeric_mask | non_integer_mask
        if not bool(invalid_mask.any()):
            continue
        issues[column_name] = {
            "invalid_row_count": int(invalid_mask.sum()),
            "null_count": int(null_mask.sum()),
            "non_numeric_count": int(non_numeric_mask.sum()),
            "non_integer_count": int(non_integer_mask.sum()),
            "sample_invalid_values": [
                str(value)
                for value in series.loc[invalid_mask].drop_duplicates().head(5).tolist()
            ],
        }
    return issues
