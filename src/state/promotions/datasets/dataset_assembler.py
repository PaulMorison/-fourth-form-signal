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

import numpy as np
import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.datasets.dataset_validators import (
    DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_ABSOLUTE,
    DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_FRACTION,
    NegativeStockPosturePolicy,
    PromotionDatasetValidationReport,
    validate_promotion_dataset,
)


LOGGER = logging.getLogger(__name__)

DISPLAY_SKU_COLUMN = "sku_number"
GOVERNED_SKU_KEY_COLUMN = "sku_number_key"
DISPLAY_IDENTIFIER_COLUMNS: tuple[str, ...] = ("promotional_sku_id",)


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
    ) -> AssembledPromotionDataset:
        """Create a single governed training dataset and persist it as parquet.

        Under the QUARANTINE_AND_PROCEED negative-stock policy, classified
        failing rows are dropped from the training dataset and persisted as
        a governed quarantine artifact. The validator still raises if the
        quarantine count exceeds the configured safety guardrails.
        """

        dataset = base_frame.copy()
        dataset = dataset.merge(
            target_frame[["promotion_row_key", *target_columns]],
            on="promotion_row_key",
            how="left",
        )
        dataset = dataset.merge(
            feature_frame[["promotion_row_key", *feature_columns]],
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

        LOGGER.info(
            "Assembled promotions dataset: rows=%s features=%s targets=%s",
            int(len(dataset.index)),
            len(feature_columns),
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
            feature_columns=feature_columns,
            target_columns=target_columns,
            validation_report=validation_report,
        )
        manifest_payload = manifest.to_dict()
        if quarantine_artifact_path is not None:
            manifest_payload["negative_stock_posture_quarantine_path"] = quarantine_artifact_path
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