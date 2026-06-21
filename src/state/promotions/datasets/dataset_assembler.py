from __future__ import annotations

"""Assembly of train-ready promotions datasets.

Canon ownership:
- Merges the extracted base frame with governed targets and engineered features
  at the promotion x sku x store grain.
- Validates duplicate grains, invalid dates, negative stock posture, and target
  coverage before materializing a train-ready parquet package.
- Does not own target semantics, feature definitions, or model fitting.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import logging
import re

import numpy as np
import pandas as pd

from models.promotions.model_input_quality import iter_review_only_engineered_feature_columns
from models.promotions.preprocessing import (
    GOVERNED_CRITICAL_MODEL_USE_FEATURE_COLUMNS,
    GOVERNED_NUMERIC_TRAINING_INPUT_COLUMNS,
)
from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.targets.target_engineering import (
    TARGET_REPAIR_EVIDENCE_COLUMNS,
)
from models.promotions.sufficient_stock_demand_target import (
    SUFFICIENT_STOCK_DEMAND_TARGET_COLUMNS,
)
from state.promotions.datasets.dataset_validators import (
    DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_ABSOLUTE,
    DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_FRACTION,
    NegativeStockPosturePolicy,
    PromotionDatasetValidationError,
    PromotionDatasetValidationReport,
    validate_promotion_dataset,
)


LOGGER = logging.getLogger(__name__)

DISPLAY_SKU_COLUMN = "sku_number"
GOVERNED_SKU_KEY_COLUMN = "sku_number_key"
DISPLAY_IDENTIFIER_COLUMNS: tuple[str, ...] = ("promotional_sku_id",)
REQUIRED_NONNULL_MODEL_VISIBLE_FEATURE_COLUMNS: frozenset[str] = frozenset(
    {*GOVERNED_CRITICAL_MODEL_USE_FEATURE_COLUMNS}
)
ZERO_FILL_EXCLUDED_IDENTITY_COLUMNS: frozenset[str] = frozenset(
    {
        "promotion_row_key",
        "store_number",
        "store_number_key",
        "promotion_header_key",
        "promotional_sku_id_key",
        DISPLAY_SKU_COLUMN,
        GOVERNED_SKU_KEY_COLUMN,
        *DISPLAY_IDENTIFIER_COLUMNS,
    }
)
NUMERIC_ZERO_FILL_ROLE_MODEL_FEATURE = "numeric_feature_or_training_input"
NUMERIC_ZERO_FILL_ROLE_TARGET = "numeric_target"
ZERO_FILL_MISSINGNESS_STRUCTURAL = "structurally_unavailable"
ZERO_FILL_MISSINGNESS_HISTORY = "insufficient_history"
ZERO_FILL_MISSINGNESS_UNCLASSIFIED = "unclassified_missingness"
ZERO_FILL_MISSINGNESS_DATA_DEFECT = "data_defect"
ZERO_FILL_TEXTUAL_SUFFIX_TOKENS: tuple[str, ...] = (
    "_reason",
    "_state",
    "_regime",
    "_posture",
    "_summary",
    "_source_column",
)
ZERO_FILL_DATE_LIKE_NAME_PATTERN = re.compile(r"(^|_)(date|datetime|timestamp|time)(_|$)", re.IGNORECASE)

DEFAULT_PARALLEL_SUFFICIENT_STOCK_TARGET_COLUMNS: tuple[str, ...] = SUFFICIENT_STOCK_DEMAND_TARGET_COLUMNS


@dataclass(frozen=True)
class PromotionDatasetManifest:
    run_id: str
    created_at_utc: str
    row_count: int
    feature_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    validation_report: PromotionDatasetValidationReport

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["validation_report"] = self.validation_report.to_dict()
        return payload


@dataclass(frozen=True)
class AssembledPromotionDataset:
    frame: pd.DataFrame
    manifest: PromotionDatasetManifest
    dataset_path: str
    manifest_path: str


class PromotionDatasetAssembler:
    """Merge, validate, and persist train-ready promotions datasets."""

    def assemble_training_dataset(
        self,
        *,
        run_id: str,
        base_frame: pd.DataFrame,
        target_frame: pd.DataFrame,
        feature_frame: pd.DataFrame,
        target_columns: tuple[str, ...],
        feature_columns: tuple[str, ...],
        artifact_paths: PromotionArtifactPaths,
        max_target_null_rate: float = 0.05,
        negative_stock_policy: NegativeStockPosturePolicy | str = NegativeStockPosturePolicy.FAIL_LOUD,
        negative_stock_quarantine_max_fraction: float = DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_FRACTION,
        negative_stock_quarantine_max_absolute: int = DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_ABSOLUTE,
        repair_evidence_columns: tuple[str, ...] | None = None,
        parallel_sufficient_stock_target_columns: tuple[str, ...] | None = None,
    ) -> AssembledPromotionDataset:
        """Create a single governed training dataset and persist it as parquet.

        Under the QUARANTINE_AND_PROCEED negative-stock policy, classified
        failing rows are dropped from the training dataset and persisted as
        a governed quarantine artifact. The validator still raises if the
        quarantine count exceeds the configured safety guardrails.
        """

        training_feature_columns, excluded_review_only_feature_columns = _training_dataset_feature_columns(
            feature_columns
        )
        effective_repair_evidence_columns = repair_evidence_columns or TARGET_REPAIR_EVIDENCE_COLUMNS
        effective_parallel_target_columns = (
            parallel_sufficient_stock_target_columns or DEFAULT_PARALLEL_SUFFICIENT_STOCK_TARGET_COLUMNS
        )
        merged_target_columns = _target_frame_columns_to_persist(
            target_frame,
            target_columns=target_columns,
            repair_evidence_columns=effective_repair_evidence_columns,
            parallel_sufficient_stock_target_columns=effective_parallel_target_columns,
        )

        dataset = base_frame.copy()
        dataset = dataset.merge(
            target_frame.loc[:, merged_target_columns],
            on="promotion_row_key",
            how="left",
        )
        dataset = dataset.merge(
            feature_frame[["promotion_row_key", *training_feature_columns]],
            on="promotion_row_key",
            how="left",
        )
        dataset = _normalize_display_identifier_columns(dataset)
        validation_report = validate_promotion_dataset(
            dataset,
            grain_column="promotion_row_key",
            target_columns=target_columns,
            max_target_null_rate=max_target_null_rate,
            run_id=run_id,
            artifact_paths=artifact_paths,
            negative_stock_policy=negative_stock_policy,
            negative_stock_quarantine_max_fraction=negative_stock_quarantine_max_fraction,
            negative_stock_quarantine_max_absolute=negative_stock_quarantine_max_absolute,
        )

        # Honor QUARANTINE_AND_PROCEED policy: drop quarantined rows from the
        # train-ready dataset and persist them separately for audit.
        quarantine_artifact_path: str | None = None
        if validation_report.negative_stock_quarantined_rows > 0:
            quarantine_keys = list(validation_report.negative_stock_quarantined_grain_keys)
            if quarantine_keys:
                pre_quarantine_row_count = int(len(dataset.index))
                dataset = dataset.loc[
                    ~dataset["promotion_row_key"].astype(str).isin(quarantine_keys)
                ].reset_index(drop=True)
                post_quarantine_row_count = int(len(dataset.index))
                inspection_root = artifact_paths.inspection_run_root(run_id)
                inspection_root.mkdir(parents=True, exist_ok=True)
                quarantine_path = (
                    inspection_root / "negative_stock_posture_quarantine.parquet"
                )
                quarantine_keys_path = (
                    inspection_root / "negative_stock_posture_quarantined_keys.json"
                )
                pd.DataFrame({"promotion_row_key": quarantine_keys}).to_parquet(
                    quarantine_path,
                    index=False,
                )
                quarantine_keys_path.write_text(
                    json.dumps(
                        {
                            "run_id": run_id,
                            "policy": validation_report.negative_stock_policy,
                            "pre_quarantine_row_count": pre_quarantine_row_count,
                            "post_quarantine_row_count": post_quarantine_row_count,
                            "quarantined_row_count": pre_quarantine_row_count
                            - post_quarantine_row_count,
                            "classification_counts": validation_report.negative_stock_quarantine_classification_counts,
                            "quarantined_grain_keys": quarantine_keys,
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                quarantine_artifact_path = str(quarantine_path)
                LOGGER.info(
                    "Stage 4 negative stock posture: quarantined %s of %s rows; "
                    "training dataset proceeds with %s rows. classification=%s",
                    pre_quarantine_row_count - post_quarantine_row_count,
                    pre_quarantine_row_count,
                    post_quarantine_row_count,
                    validation_report.negative_stock_quarantine_classification_counts,
                )

        _assert_no_all_null_model_visible_features(
            dataset,
            feature_columns=training_feature_columns,
            excluded_review_only_feature_columns=excluded_review_only_feature_columns,
        )
        dataset, zero_fill_summary = apply_governed_training_numeric_zero_fill_contract(
            dataset,
            feature_columns=training_feature_columns,
            target_columns=target_columns,
        )
        _assert_no_nan_ml_ready_numeric_columns(
            dataset,
            feature_columns=training_feature_columns,
            target_columns=target_columns,
        )

        LOGGER.info(
            "Assembled promotions dataset: rows=%s features=%s targets=%s",
            int(len(dataset.index)),
            len(training_feature_columns),
            len(target_columns),
        )
        dataset_path = artifact_paths.training_dataset_path(run_id)
        manifest_path = artifact_paths.dataset_manifest_path(run_id)
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        dataset.to_parquet(dataset_path, index=False)
        manifest = PromotionDatasetManifest(
            run_id=run_id,
            created_at_utc=datetime.now(tz=UTC).isoformat(),
            row_count=int(len(dataset.index)),
            feature_columns=training_feature_columns,
            target_columns=target_columns,
            validation_report=validation_report,
        )
        manifest_payload = manifest.to_dict()
        if quarantine_artifact_path is not None:
            manifest_payload["negative_stock_posture_quarantine_path"] = quarantine_artifact_path
        if excluded_review_only_feature_columns:
            manifest_payload["excluded_review_only_feature_columns"] = list(
                excluded_review_only_feature_columns
            )
        manifest_payload["repair_evidence_columns"] = list(effective_repair_evidence_columns)
        manifest_payload["parallel_sufficient_stock_target_columns"] = list(
            effective_parallel_target_columns
        )
        manifest_payload["persisted_target_support_columns"] = [
            column_name
            for column_name in merged_target_columns
            if column_name != "promotion_row_key" and column_name not in target_columns
        ]
        manifest_payload["governed_numeric_zero_fill_summary"] = zero_fill_summary
        manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return AssembledPromotionDataset(
            frame=dataset,
            manifest=manifest,
            dataset_path=str(dataset_path),
            manifest_path=str(manifest_path),
        )


def _normalize_display_identifier_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    if GOVERNED_SKU_KEY_COLUMN in normalized.columns:
        normalized[DISPLAY_SKU_COLUMN] = _display_sku_from_key(
            normalized[GOVERNED_SKU_KEY_COLUMN]
        )
    elif DISPLAY_SKU_COLUMN in normalized.columns:
        normalized[DISPLAY_SKU_COLUMN] = normalized[DISPLAY_SKU_COLUMN].astype("string")
    for column_name in DISPLAY_IDENTIFIER_COLUMNS:
        if column_name in normalized.columns:
            normalized[column_name] = normalized[column_name].astype("string")
    return normalized


def _display_sku_from_key(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").astype("float64")
    finite_mask = pd.Series(np.isfinite(numeric.to_numpy()), index=series.index)
    integer_mask = finite_mask & numeric.mod(1).eq(0)
    display = pd.Series(pd.NA, index=series.index, dtype="string")
    if bool(integer_mask.any()):
        display.loc[integer_mask] = numeric.loc[integer_mask].astype("int64").astype("string")
    return display


def _target_frame_columns_to_persist(
    target_frame: pd.DataFrame,
    *,
    target_columns: tuple[str, ...],
    repair_evidence_columns: tuple[str, ...],
    parallel_sufficient_stock_target_columns: tuple[str, ...],
) -> tuple[str, ...]:
    """Return ordered target-frame columns to merge into training_ready.parquet."""

    ordered = tuple(
        dict.fromkeys(
            (
                "promotion_row_key",
                *target_columns,
                *repair_evidence_columns,
                *parallel_sufficient_stock_target_columns,
            )
        )
    )
    return tuple(
        column_name
        for column_name in ordered
        if column_name == "promotion_row_key" or column_name in target_frame.columns
    )


def _training_dataset_feature_columns(
    feature_columns: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    review_only_feature_columns = set(iter_review_only_engineered_feature_columns())
    training_feature_columns = tuple(
        column_name for column_name in feature_columns if column_name not in review_only_feature_columns
    )
    excluded_review_only_feature_columns = tuple(
        column_name for column_name in feature_columns if column_name in review_only_feature_columns
    )
    return training_feature_columns, excluded_review_only_feature_columns


def apply_governed_training_numeric_zero_fill_contract(
    frame: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    target_columns: Sequence[str],
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return an ML-ready training dataset with governed numeric blanks filled.

    Purpose:
        Make the persisted train-ready dataset deterministic for downstream ML
        use by filling permitted numeric feature/target blanks with zero while
        failing loud on invalid numeric coercion.

    Inputs:
        frame: assembled training dataset before ML-ready numeric hygiene.
        feature_columns: engineered feature columns retained in the training
            dataset contract.
        target_columns: governed supervised target columns retained in the
            training dataset.

    Outputs:
        A tuple of the zero-filled dataset and a serializable summary
        describing which numeric columns were filled, why missingness was
        accepted, and which non-numeric columns were intentionally untouched.

    Failure behavior:
        Raises ``PromotionDatasetValidationError`` when a governed numeric
        column contains non-numeric junk rather than missing values.
    """

    working = frame.copy()
    zero_fill_rows: list[dict[str, object]] = []
    invalid_numeric_columns: dict[str, dict[str, object]] = {}
    fill_columns = tuple(
        dict.fromkeys(
            column_name
            for column_name in (
                *GOVERNED_NUMERIC_TRAINING_INPUT_COLUMNS,
                *target_columns,
                *feature_columns,
            )
                if (
                    column_name in working.columns
                    and column_name not in ZERO_FILL_EXCLUDED_IDENTITY_COLUMNS
                    and _is_zero_fill_numeric_candidate(
                        column_name,
                        working[column_name],
                    )
                )
        )
    )
    for column_name in fill_columns:
        series = working[column_name]
        if column_name in target_columns:
            role = NUMERIC_ZERO_FILL_ROLE_TARGET
        else:
            role = NUMERIC_ZERO_FILL_ROLE_MODEL_FEATURE
        filled_series, summary_row, invalid_details = _zero_fill_numeric_series(
            frame=working,
            column_name=column_name,
            series=series,
            role=role,
        )
        if invalid_details is not None:
            invalid_numeric_columns[column_name] = invalid_details
            continue
        working[column_name] = filled_series
        zero_fill_rows.append(summary_row)

    if invalid_numeric_columns:
        raise PromotionDatasetValidationError(
            "Governed numeric zero-fill contract failed on non-numeric input values.",
            details={
                "rule": "numeric_zero_fill_contract",
                "invalid_numeric_columns": list(invalid_numeric_columns.keys()),
                "column_issues": invalid_numeric_columns,
                "repair_policy": "fail_loud_invalid_numeric_junk_not_zero_filled",
            },
        )

    non_numeric_nullable_columns = [
        str(column_name)
        for column_name in working.columns
        if column_name not in set(fill_columns) and bool(working[column_name].isna().any())
    ]
    zero_filled_cell_count = int(sum(int(row["zero_filled_count"]) for row in zero_fill_rows))
    summary = {
        "numeric_zero_fill_columns": [str(column_name) for column_name in fill_columns],
        "numeric_zero_fill_column_count": int(len(fill_columns)),
        "numeric_zero_filled_cell_count": zero_filled_cell_count,
        "columns_excluded_from_zero_fill_non_numeric": sorted(non_numeric_nullable_columns),
        "columns_intentionally_left_nullable": sorted(non_numeric_nullable_columns),
        "invalid_numeric_coercion_cases": [],
        "column_rows": zero_fill_rows,
    }
    return working, summary


def _zero_fill_numeric_series(
    *,
    frame: pd.DataFrame,
    column_name: str,
    series: pd.Series,
    role: str,
) -> tuple[pd.Series, dict[str, object], dict[str, object] | None]:
    """Coerce one governed numeric series and fill permitted blanks with zero."""

    if pd.api.types.is_bool_dtype(series):
        coerced = series.astype("Int64")
        invalid_mask = pd.Series(False, index=series.index)
    else:
        coerced = pd.to_numeric(series, errors="coerce")
        invalid_mask = series.notna() & coerced.isna()
    if bool(invalid_mask.any()):
        invalid_values = [
            str(value)
            for value in series.loc[invalid_mask].drop_duplicates().head(5).tolist()
        ]
        return series, {}, {
            "invalid_row_count": int(invalid_mask.sum()),
            "sample_invalid_values": invalid_values,
            "role": role,
        }

    missing_mask = coerced.isna()
    structural_mask = _structural_missingness_mask(frame, column_name).reindex(series.index, fill_value=False)
    history_mask = _insufficient_history_missingness_mask(frame, column_name).reindex(series.index, fill_value=False)
    structural_missing_count = int((missing_mask & structural_mask).sum())
    insufficient_history_count = int((missing_mask & ~structural_mask & history_mask).sum())
    unclassified_missing_count = int((missing_mask & ~structural_mask & ~history_mask).sum())

    if column_name.lower().endswith("_flag") or pd.api.types.is_bool_dtype(series):
        filled = coerced.fillna(0).astype("Int64")
    else:
        filled = coerced.fillna(0.0).astype("float64")

    summary_row = {
        "column_name": str(column_name),
        "role": role,
        "pre_zero_fill_null_count": int(missing_mask.sum()),
        "zero_filled_count": int(missing_mask.sum()),
        "post_zero_fill_null_count": int(filled.isna().sum()),
        "structurally_unavailable_count": structural_missing_count,
        "insufficient_history_count": insufficient_history_count,
        "unclassified_missingness_count": unclassified_missing_count,
    }
    return filled, summary_row, None


def _structural_missingness_mask(frame: pd.DataFrame, column_name: str) -> pd.Series:
    """Return rows where missingness is structurally valid for the column."""

    lowered = column_name.lower()
    mask = pd.Series(False, index=frame.index, dtype="bool")
    if any(token in lowered for token in ("month_end", "cashflow", "billing_cycle")):
        pressure = pd.to_numeric(
            frame.get("feature_month_end_cash_runoff_pressure_flag"),
            errors="coerce",
        ).fillna(0.0)
        mask = mask | pressure.lt(1.0)
    if any(token in lowered for token in ("high_demand", "high_base_demand")):
        high_demand_flag = pd.to_numeric(
            frame.get("feature_high_base_demand_end_cover_flag"),
            errors="coerce",
        ).fillna(0.0)
        mask = mask | high_demand_flag.lt(1.0)
    return mask


def _insufficient_history_missingness_mask(frame: pd.DataFrame, column_name: str) -> pd.Series:
    """Return rows where missingness reflects limited historical evidence."""

    lowered = column_name.lower()
    if not any(
        token in lowered
        for token in (
            "probability",
            "same_discount",
            "historical",
            "under_floor",
            "basket",
            "companion",
            "uplift",
            "support",
        )
    ):
        return pd.Series(False, index=frame.index, dtype="bool")
    no_history = _optional_numeric_fill_series(frame, "feature_no_promo_history_flag")
    sparse_history = _optional_numeric_fill_series(frame, "feature_sparse_history_penalty")
    same_discount_available = _optional_numeric_fill_series(frame, "feature_same_discount_history_available_flag")
    basket_missing_evidence = _optional_numeric_fill_series(frame, "feature_basket_history_missing_evidence_flag")
    probability_model_use = _optional_numeric_fill_series(frame, "feature_probability_model_use_flag")
    return (
        no_history.ge(1.0)
        | sparse_history.gt(0.0)
        | same_discount_available.lt(1.0)
        | basket_missing_evidence.ge(1.0)
        | probability_model_use.lt(1.0)
    )


def _optional_numeric_fill_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    """Return a numeric series for optional evidence flags with zero default."""

    if column_name not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0)


def _is_zero_fill_numeric_candidate(column_name: str, series: pd.Series) -> bool:
    """Return whether a training-dataset column is governed numeric fill scope."""

    lowered = column_name.lower()
    if ZERO_FILL_DATE_LIKE_NAME_PATTERN.search(lowered):
        return False
    if any(lowered.endswith(token) for token in ZERO_FILL_TEXTUAL_SUFFIX_TOKENS):
        return False
    if column_name in GOVERNED_NUMERIC_TRAINING_INPUT_COLUMNS:
        return True
    if column_name.startswith("feature_") or column_name.startswith("target_"):
        return True
    if pd.api.types.is_bool_dtype(series) or pd.api.types.is_numeric_dtype(series):
        return True
    return lowered.endswith("_flag") or lowered.startswith("is_")


def _assert_no_nan_ml_ready_numeric_columns(
    frame: pd.DataFrame,
    *,
    feature_columns: tuple[str, ...],
    target_columns: tuple[str, ...],
) -> None:
    """Fail loud if numeric model-use or target columns still contain NaN."""

    checked_columns = tuple(
        dict.fromkeys(
            column_name
            for column_name in (
                *GOVERNED_NUMERIC_TRAINING_INPUT_COLUMNS,
                *feature_columns,
                *target_columns,
            )
                if (
                    column_name in frame.columns
                    and column_name not in ZERO_FILL_EXCLUDED_IDENTITY_COLUMNS
                    and _is_zero_fill_numeric_candidate(column_name, frame[column_name])
                )
        )
    )
    remaining_null_columns = [
        column_name
        for column_name in checked_columns
        if bool(pd.to_numeric(frame[column_name], errors="coerce").isna().any())
    ]
    if not remaining_null_columns:
        return
    raise PromotionDatasetValidationError(
        "ML-ready numeric columns still contain NaN after governed zero-fill.",
        details={
            "rule": "ml_ready_numeric_nan_after_zero_fill",
            "columns": remaining_null_columns,
            "repair_policy": "fail_loud_no_post_fill_numeric_nans",
        },
    )


def _assert_no_all_null_model_visible_features(
    frame: pd.DataFrame,
    *,
    feature_columns: tuple[str, ...],
    excluded_review_only_feature_columns: tuple[str, ...],
) -> None:
    if frame.empty:
        return
    all_null_feature_columns = [
        column_name
        for column_name in feature_columns
        if column_name in REQUIRED_NONNULL_MODEL_VISIBLE_FEATURE_COLUMNS
        and column_name in frame.columns
        and bool(frame[column_name].isna().all())
    ]
    all_null_feature_columns.extend(_conditionally_required_all_null_feature_columns(frame))
    all_null_feature_columns = list(dict.fromkeys(all_null_feature_columns))
    if not all_null_feature_columns:
        return
    raise PromotionDatasetValidationError(
        (
            "All-null model-visible engineered features detected in the training dataset: "
            + ", ".join(all_null_feature_columns)
        ),
        details={
            "rule": "model_visible_feature_all_null",
            "all_null_feature_columns": all_null_feature_columns,
            "excluded_review_only_feature_columns": list(excluded_review_only_feature_columns),
            "repair_policy": "fail_loud_no_silent_model_feature_nulls",
        },
    )


def _conditionally_required_all_null_feature_columns(frame: pd.DataFrame) -> list[str]:
    required_columns: list[str] = []
    uplift_score_column = "feature_uplift_allocation_discipline_score"
    if uplift_score_column in frame.columns and bool(frame[uplift_score_column].isna().all()):
        uplift_units = pd.to_numeric(
            frame.get("feature_expected_incremental_uplift_units_same_discount"),
            errors="coerce",
        ).fillna(0.0)
        total_stock_available = pd.to_numeric(
            frame.get("total_stock_available"),
            errors="coerce",
        ).fillna(0.0)
        model_use_flag = pd.to_numeric(
            frame.get("feature_probability_model_use_flag"),
            errors="coerce",
        ).fillna(0.0)
        same_discount_history_available = pd.to_numeric(
            frame.get("feature_same_discount_history_available_flag"),
            errors="coerce",
        ).fillna(0.0)
        support_rows = (
            uplift_units.gt(0.0)
            & total_stock_available.gt(0.0)
            & (model_use_flag.eq(1.0) | same_discount_history_available.eq(1.0))
        )
        if bool(support_rows.any()):
            required_columns.append(uplift_score_column)
    return required_columns