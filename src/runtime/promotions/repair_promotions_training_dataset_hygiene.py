from __future__ import annotations

"""Governed hygiene + model-family repair for an existing promotions training dataset."""

from datetime import UTC, datetime
import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from models.promotions.model_input_quality import iter_review_only_engineered_feature_columns
from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.datasets.dataset_assembler import (
    _assert_no_all_null_model_visible_features,
    _assert_no_nan_ml_ready_numeric_columns,
    _training_dataset_feature_columns,
    apply_governed_training_numeric_zero_fill_contract,
)
from state.promotions.datasets.dataset_validators import PromotionDatasetValidationError
from state.promotions.datasets.model_input_export import (
    PromotionTrainingDataExportError,
    write_training_data_sample_artifacts,
)
from state.promotions.feature_engineering.demand.ft_allocation_discipline import (
    ALLOCATION_DISCIPLINE_FEATURE_COLUMNS,
    apply_ft_allocation_discipline,
)
from state.promotions.feature_engineering.demand.ft_basket_structure_dependency import (
    BASKET_STRUCTURE_DEPENDENCY_FEATURE_COLUMNS,
    apply_ft_basket_structure_dependency,
)
from state.promotions.feature_engineering.demand.ft_micro_market_equilibrium import (
    MICRO_MARKET_EQUILIBRIUM_FEATURE_COLUMNS,
    apply_ft_micro_market_equilibrium,
)
from state.promotions.feature_engineering.demand.ft_sparse_demand_noise import (
    SPARSE_DEMAND_NOISE_FEATURE_COLUMNS,
    apply_ft_sparse_demand_noise,
)
from state.promotions.feature_engineering.stock.ft_target_stock_logic import (
    TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS,
    apply_ft_target_stock_logic,
)


MODEL_PASS_FEATURE_COLUMNS: tuple[str, ...] = (
    *TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS,
    *BASKET_STRUCTURE_DEPENDENCY_FEATURE_COLUMNS,
    *SPARSE_DEMAND_NOISE_FEATURE_COLUMNS,
    *MICRO_MARKET_EQUILIBRIUM_FEATURE_COLUMNS,
)


def _required_path(path: Path, *, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    return path


def _atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temp_path, index=False)
    temp_path.replace(path)


def _atomic_write_json(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    temp_path.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repair a persisted promotions training dataset in place by dropping review-only features, repopulating required hygiene columns, and adding the next governed model-visible family pass."
    )
    parser.add_argument("--run-id", required=True, help="Training dataset run id to repair in place.")
    parser.add_argument("--artifact-root", help="Override governed promotions artifact root.")
    parser.add_argument("--env-file", help="Optional .env file to load before resolving artifact roots.")
    parser.add_argument("--row-limit", type=int, default=10_000, help="Inspection CSV row cap. Default 10000.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    artifacts = PromotionArtifactPaths.from_env(
        root=Path(args.artifact_root) if args.artifact_root else None,
        env_file=args.env_file,
    )
    dataset_path = _required_path(
        artifacts.training_dataset_path(args.run_id),
        label="training dataset parquet",
    )
    manifest_path = _required_path(
        artifacts.dataset_manifest_path(args.run_id),
        label="dataset manifest",
    )

    try:
        frame = pd.read_parquet(dataset_path)
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        original_feature_columns = tuple(
            str(column_name)
            for column_name in manifest_payload.get("feature_columns", [])
            if str(column_name)
        )
        prior_excluded_review_only_feature_columns = tuple(
            str(column_name)
            for column_name in manifest_payload.get("excluded_review_only_feature_columns", [])
            if str(column_name)
        )
        target_columns = tuple(
            str(column_name)
            for column_name in manifest_payload.get("target_columns", [])
            if str(column_name)
        )

        repaired_frame = frame.copy()
        repaired_frame = apply_ft_target_stock_logic(repaired_frame)
        repaired_frame = apply_ft_basket_structure_dependency(repaired_frame)
        repaired_frame = apply_ft_sparse_demand_noise(repaired_frame)
        repaired_frame = apply_ft_micro_market_equilibrium(repaired_frame)
        refreshed_allocation_discipline = apply_ft_allocation_discipline(repaired_frame)
        repaired_frame["feature_uplift_allocation_discipline_score"] = refreshed_allocation_discipline[
            "feature_uplift_allocation_discipline_score"
        ]
        augmented_feature_columns = tuple(
            dict.fromkeys(
                [
                    *original_feature_columns,
                    *MODEL_PASS_FEATURE_COLUMNS,
                    *ALLOCATION_DISCIPLINE_FEATURE_COLUMNS,
                ]
            )
        )
        training_feature_columns, excluded_review_only_feature_columns = _training_dataset_feature_columns(
            augmented_feature_columns
        )
        excluded_review_only_feature_columns = tuple(
            dict.fromkeys(
                [
                    *prior_excluded_review_only_feature_columns,
                    *iter_review_only_engineered_feature_columns(),
                    *excluded_review_only_feature_columns,
                ]
            )
        )
        repaired_frame = repaired_frame.drop(columns=list(excluded_review_only_feature_columns), errors="ignore")
        _assert_added_model_pass_features(repaired_frame)
        _assert_no_all_null_model_visible_features(
            repaired_frame,
            feature_columns=training_feature_columns,
            excluded_review_only_feature_columns=excluded_review_only_feature_columns,
        )
        repaired_frame, zero_fill_summary = apply_governed_training_numeric_zero_fill_contract(
            repaired_frame,
            feature_columns=training_feature_columns,
            target_columns=target_columns,
        )
        _assert_no_nan_ml_ready_numeric_columns(
            repaired_frame,
            feature_columns=training_feature_columns,
            target_columns=target_columns,
        )

        inspection_root = artifacts.inspection_run_root(args.run_id) / "training_data_export"
        export_paths = write_training_data_sample_artifacts(
            run_id=args.run_id,
            dataset_frame=repaired_frame,
            output_root=inspection_root,
            source_dataset_path=dataset_path,
            source_manifest_path=manifest_path,
            row_limit=args.row_limit,
            feature_columns=training_feature_columns,
            target_columns=target_columns,
            prior_feature_columns=original_feature_columns,
        )
    except (PromotionDatasetValidationError, PromotionTrainingDataExportError, json.JSONDecodeError) as error:
        parser.error(str(error))

    updated_manifest_payload = dict(manifest_payload)
    updated_manifest_payload["feature_columns"] = list(training_feature_columns)
    updated_manifest_payload["excluded_review_only_feature_columns"] = list(excluded_review_only_feature_columns)
    updated_manifest_payload["governed_numeric_zero_fill_summary"] = zero_fill_summary
    updated_manifest_payload["training_dataset_hygiene_repaired_at_utc"] = datetime.now(tz=UTC).isoformat()
    updated_manifest_payload["training_dataset_hygiene_repair_notes"] = {
        "repaired_model_visible_features": [
            "feature_uplift_allocation_discipline_score",
            *MODEL_PASS_FEATURE_COLUMNS,
        ],
        "numeric_zero_fill_columns": zero_fill_summary["numeric_zero_fill_columns"],
        "numeric_zero_filled_cell_count": zero_fill_summary["numeric_zero_filled_cell_count"],
        "excluded_review_only_feature_columns": list(excluded_review_only_feature_columns),
        "training_data_export_quality_summary_json_path": export_paths.quality_summary_json_path,
    }

    _atomic_write_parquet(repaired_frame, dataset_path)
    _atomic_write_json(updated_manifest_payload, manifest_path)

    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "training_ready_parquet_path": str(dataset_path),
                "dataset_manifest_path": str(manifest_path),
                "added_model_pass_feature_columns": list(MODEL_PASS_FEATURE_COLUMNS),
                "excluded_review_only_feature_columns": list(excluded_review_only_feature_columns),
                "feature_coverage_audit_csv_path": export_paths.feature_coverage_audit_csv_path,
                "model_use_feature_coverage_summary_csv_path": export_paths.model_use_feature_coverage_summary_csv_path,
                "model_use_feature_coverage_summary_json_path": export_paths.model_use_feature_coverage_summary_json_path,
                "training_data_full_parquet_path": export_paths.full_parquet_path,
                "training_data_sample_csv_path": export_paths.sample_csv_path,
                "training_data_schema_csv_path": export_paths.schema_csv_path,
                "training_data_quality_summary_json_path": export_paths.quality_summary_json_path,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _assert_added_model_pass_features(frame: pd.DataFrame) -> None:
    all_null_columns = [
        column_name
        for column_name in MODEL_PASS_FEATURE_COLUMNS
        if column_name not in frame.columns or bool(frame[column_name].isna().all())
    ]
    if not all_null_columns:
        return
    raise PromotionDatasetValidationError(
        "Missing or all-null governed model-pass feature columns: " + ", ".join(all_null_columns),
        details={
            "rule": "model_pass_feature_missing_or_all_null",
            "all_null_feature_columns": all_null_columns,
            "repair_policy": "fail_loud_no_silent_model_pass_regression",
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())