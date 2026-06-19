from __future__ import annotations

"""Diagnostics-first rebuild for the governed promotions training dataset."""

from dataclasses import asdict, dataclass
from datetime import date
import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from models.promotions.model_input_quality import (
    filter_model_use_engineered_feature_columns,
    iter_review_only_engineered_feature_columns,
)
from models.promotions.preprocessing import GOVERNED_CRITICAL_MODEL_USE_FEATURE_COLUMNS
from runtime.promotions.config import (
    PromotionArtifactPaths,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
)
from runtime.promotions.promotions_pipeline_runner import _extract_base_frame
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler
from state.promotions.datasets.dataset_validators import (
    DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_ABSOLUTE,
    DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_FRACTION,
    NegativeStockPosturePolicy,
)
from state.promotions.datasets.model_input_export import (
    FEATURE_FAMILY_SCOPE_MODEL_USE,
    FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY,
    PromotionTrainingDataExportError,
    PromotionTrainingDataSampleExportPaths,
    _build_feature_dataset_coverage_audit,
    _build_model_use_feature_coverage_summary,
    write_training_data_sample_artifacts,
)
from state.promotions.feature_engineering.feature_pipeline import PromotionFeatureEngineer
from state.promotions.targets.target_engineering import PromotionTargetEngineer


@dataclass(frozen=True)
class PromotionTrainingDatasetRebuildArtifacts:
    run_id: str
    source_run_id: str | None
    source_base_parquet_path: str
    source_manifest_path: str | None
    training_ready_parquet_path: str
    dataset_manifest_path: str
    inspection_output_root: str
    training_data_full_parquet_path: str
    training_data_sample_csv_path: str
    training_data_schema_csv_path: str
    training_data_quality_summary_json_path: str
    feature_coverage_audit_csv_path: str | None
    model_use_feature_coverage_summary_csv_path: str | None
    model_use_feature_coverage_summary_json_path: str | None
    feature_families_fully_present: tuple[str, ...]
    feature_families_partially_present: tuple[str, ...]
    feature_families_review_only: tuple[str, ...]
    feature_families_missing: tuple[str, ...]


class PromotionTrainingDatasetRebuildError(ValueError):
    """Raised when the governed rebuild contract fails before persistence."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


def _required_parquet(path: Path, *, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{label} parquet does not exist: {path}")
    return pd.read_parquet(path)


def _load_manifest_feature_columns(path: Path | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if path is None or not path.exists():
        return (), ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    feature_columns = tuple(
        str(column_name)
        for column_name in payload.get("feature_columns", [])
        if str(column_name)
    )
    target_columns = tuple(
        str(column_name)
        for column_name in payload.get("target_columns", [])
        if str(column_name)
    )
    return feature_columns, target_columns


def _build_settings(args: argparse.Namespace) -> PromotionPipelineSettings:
    runtime_date = date.fromisoformat(args.as_of_date) if args.as_of_date else None
    artifact_paths = PromotionArtifactPaths.from_env(
        root=Path(args.artifact_root) if args.artifact_root else None,
        env_file=args.env_file,
    )
    return PromotionPipelineSettings.for_runtime_date(
        sql=PromotionMssqlSettings.from_env(
            promotion_advice_table=args.promotion_advice_table,
            pwlogd_table=args.pwlogd_table,
            env_file=args.env_file,
            server=args.server,
            database=args.database,
            schema=args.schema,
            username=args.username,
            password=args.password,
            odbc_driver=args.odbc_driver,
            encrypt=args.encrypt,
            trust_server_certificate=args.trust_server_certificate,
        ),
        runtime_date=runtime_date,
        artifacts=artifact_paths,
    )


def _resolve_source_manifest_path(
    *,
    artifacts: PromotionArtifactPaths,
    source_run_id: str | None,
    source_manifest_path: str | None,
) -> Path | None:
    if source_manifest_path:
        return Path(source_manifest_path)
    if source_run_id is None:
        return None
    candidate = artifacts.dataset_manifest_path(source_run_id)
    return candidate if candidate.exists() else None


def _resolve_base_frame(
    *,
    args: argparse.Namespace,
    artifacts: PromotionArtifactPaths,
) -> tuple[pd.DataFrame, Path, Path | None, str | None]:
    source_run_id = args.source_run_id or args.run_id
    source_manifest_path = _resolve_source_manifest_path(
        artifacts=artifacts,
        source_run_id=source_run_id,
        source_manifest_path=args.source_manifest_path,
    )
    if args.source_base_parquet:
        source_base_path = Path(args.source_base_parquet)
        return (
            _required_parquet(source_base_path, label="completed base extraction"),
            source_base_path,
            source_manifest_path,
            source_run_id,
        )

    if args.refresh_completed_extraction:
        settings = _build_settings(args)
        base_frame = _extract_base_frame(
            settings=settings,
            run_id=source_run_id,
            selection_mode="completed",
        )
        source_base_path = artifacts.extracted_base_path(source_run_id)
        return base_frame, source_base_path, source_manifest_path, source_run_id

    source_base_path = artifacts.extracted_base_path(source_run_id)
    return (
        _required_parquet(source_base_path, label="completed base extraction"),
        source_base_path,
        source_manifest_path,
        source_run_id,
    )


def _feature_family_categories(summary_frame: pd.DataFrame) -> dict[str, tuple[str, ...]]:
    fully_present: list[str] = []
    partially_present: list[str] = []
    review_only: list[str] = []
    missing: list[str] = []
    for row in summary_frame.itertuples(index=False):
        family_name = str(row.feature_family)
        required_presence_scope = str(row.required_presence_scope)
        feature_count = int(row.feature_count)
        ready_count = int(row.present_in_training_ready_count)
        model_use_count = int(row.present_in_model_use_count)
        missing_model_use_count = int(row.missing_model_use_feature_count)
        if required_presence_scope == FEATURE_FAMILY_SCOPE_MODEL_USE:
            if feature_count == 0 or ready_count == 0:
                missing.append(family_name)
            elif missing_model_use_count == 0:
                fully_present.append(family_name)
            else:
                partially_present.append(family_name)
            continue
        if required_presence_scope == FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY:
            if ready_count > 0:
                review_only.append(family_name)
            else:
                missing.append(family_name)
            continue
        if ready_count == 0:
            missing.append(family_name)
        elif feature_count > 0 and model_use_count == feature_count:
            fully_present.append(family_name)
        else:
            partially_present.append(family_name)
    return {
        "feature_families_fully_present": tuple(sorted(dict.fromkeys(fully_present))),
        "feature_families_partially_present": tuple(sorted(dict.fromkeys(partially_present))),
        "feature_families_review_only": tuple(sorted(dict.fromkeys(review_only))),
        "feature_families_missing": tuple(sorted(dict.fromkeys(missing))),
    }


def _validate_feature_contract(feature_columns: Sequence[str]) -> dict[str, object]:
    feature_column_set = {str(column_name) for column_name in feature_columns}
    review_only_features = set(iter_review_only_engineered_feature_columns())
    model_use_feature_columns = set(filter_model_use_engineered_feature_columns(feature_columns))
    missing_critical_model_use_features = sorted(
        feature_name
        for feature_name in GOVERNED_CRITICAL_MODEL_USE_FEATURE_COLUMNS
        if feature_name not in feature_column_set
    )
    review_only_features_leaking_into_model_use_set = sorted(model_use_feature_columns & review_only_features)
    review_only_features_leaking_into_critical_model_use_contract = sorted(
        set(GOVERNED_CRITICAL_MODEL_USE_FEATURE_COLUMNS) & review_only_features
    )
    return {
        "missing_critical_model_use_features": missing_critical_model_use_features,
        "review_only_features_leaking_into_model_use_set": review_only_features_leaking_into_model_use_set,
        "review_only_features_leaking_into_critical_model_use_contract": review_only_features_leaking_into_critical_model_use_contract,
        "model_use_feature_columns": sorted(model_use_feature_columns),
    }


def rebuild_training_dataset(
    *,
    run_id: str,
    artifacts: PromotionArtifactPaths,
    base_frame: pd.DataFrame,
    source_base_path: Path,
    source_manifest_path: Path | None,
    source_run_id: str | None,
    row_limit: int,
    negative_stock_policy: NegativeStockPosturePolicy | str = NegativeStockPosturePolicy.QUARANTINE_AND_PROCEED,
    negative_stock_quarantine_max_fraction: float = DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_FRACTION,
    negative_stock_quarantine_max_absolute: int = DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_ABSOLUTE,
) -> PromotionTrainingDatasetRebuildArtifacts:
    target_result = PromotionTargetEngineer().engineer(base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

    feature_contract = _validate_feature_contract(feature_result.feature_columns)
    coverage_audit_frame = _build_feature_dataset_coverage_audit(
        stage_label="training",
        engineered_columns=feature_result.feature_columns,
        model_input_columns=tuple(feature_contract["model_use_feature_columns"]),
    )
    coverage_summary_frame = _build_model_use_feature_coverage_summary(
        audit_frame=coverage_audit_frame,
        stage_label="training",
    )
    family_categories = _feature_family_categories(coverage_summary_frame)

    if (
        feature_contract["missing_critical_model_use_features"]
        or feature_contract["review_only_features_leaking_into_model_use_set"]
        or feature_contract["review_only_features_leaking_into_critical_model_use_contract"]
    ):
        raise PromotionTrainingDatasetRebuildError(
            "Training-dataset rebuild feature contract failed.",
            details={
                **feature_contract,
                **family_categories,
            },
        )

    dataset = PromotionDatasetAssembler().assemble_training_dataset(
        run_id=run_id,
        base_frame=base_frame,
        target_frame=target_result.frame,
        feature_frame=feature_result.frame,
        target_columns=target_result.target_columns,
        feature_columns=feature_result.feature_columns,
        artifact_paths=artifacts,
        negative_stock_policy=negative_stock_policy,
        negative_stock_quarantine_max_fraction=negative_stock_quarantine_max_fraction,
        negative_stock_quarantine_max_absolute=negative_stock_quarantine_max_absolute,
    )
    prior_feature_columns, _prior_target_columns = _load_manifest_feature_columns(source_manifest_path)
    inspection_root = artifacts.inspection_run_root(run_id) / "training_data_export"
    sample_paths: PromotionTrainingDataSampleExportPaths = write_training_data_sample_artifacts(
        run_id=run_id,
        dataset_frame=dataset.frame,
        output_root=inspection_root,
        source_dataset_path=dataset.dataset_path,
        source_manifest_path=source_manifest_path,
        row_limit=row_limit,
        feature_columns=dataset.manifest.feature_columns,
        target_columns=dataset.manifest.target_columns,
        prior_feature_columns=prior_feature_columns,
    )

    return PromotionTrainingDatasetRebuildArtifacts(
        run_id=run_id,
        source_run_id=source_run_id,
        source_base_parquet_path=str(source_base_path),
        source_manifest_path=str(source_manifest_path) if source_manifest_path is not None else None,
        training_ready_parquet_path=dataset.dataset_path,
        dataset_manifest_path=dataset.manifest_path,
        inspection_output_root=str(inspection_root),
        training_data_full_parquet_path=sample_paths.full_parquet_path,
        training_data_sample_csv_path=sample_paths.sample_csv_path,
        training_data_schema_csv_path=sample_paths.schema_csv_path,
        training_data_quality_summary_json_path=sample_paths.quality_summary_json_path,
        feature_coverage_audit_csv_path=sample_paths.feature_coverage_audit_csv_path,
        model_use_feature_coverage_summary_csv_path=sample_paths.model_use_feature_coverage_summary_csv_path,
        model_use_feature_coverage_summary_json_path=sample_paths.model_use_feature_coverage_summary_json_path,
        feature_families_fully_present=family_categories["feature_families_fully_present"],
        feature_families_partially_present=family_categories["feature_families_partially_present"],
        feature_families_review_only=family_categories["feature_families_review_only"],
        feature_families_missing=family_categories["feature_families_missing"],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild the governed promotions training dataset from completed base extraction and write inspection artifacts."
    )
    parser.add_argument("--run-id", required=True, help="Output run id for the rebuilt training dataset.")
    parser.add_argument("--source-run-id", help="Source run id used to resolve completed base extraction and prior dataset manifest. Defaults to --run-id.")
    parser.add_argument("--source-base-parquet", help="Override the completed base extraction parquet path.")
    parser.add_argument("--source-manifest-path", help="Override the prior dataset manifest path used for feature comparison.")
    parser.add_argument("--artifact-root", help="Override the governed promotions artifact root.")
    parser.add_argument("--env-file", help="Optional .env file to load before resolving artifact roots.")
    parser.add_argument("--row-limit", type=int, default=10_000, help="Inspection CSV row cap. Default 10000.")
    parser.add_argument(
        "--negative-stock-policy",
        choices=tuple(policy.value for policy in NegativeStockPosturePolicy),
        default=NegativeStockPosturePolicy.QUARANTINE_AND_PROCEED.value,
        help="Governed Stage 4 treatment for negative stock posture rows. Default quarantine_and_proceed.",
    )
    parser.add_argument(
        "--negative-stock-quarantine-max-fraction",
        type=float,
        default=DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_FRACTION,
        help="Maximum quarantined-row fraction allowed under quarantine_and_proceed. Default 0.05.",
    )
    parser.add_argument(
        "--negative-stock-quarantine-max-absolute",
        type=int,
        default=DEFAULT_NEGATIVE_STOCK_QUARANTINE_MAX_ABSOLUTE,
        help="Maximum quarantined-row count allowed under quarantine_and_proceed. Default 5000.",
    )
    parser.add_argument("--refresh-completed-extraction", action="store_true", help="Re-extract completed promotions before rebuilding the dataset.")
    parser.add_argument("--as-of-date", help="Runtime date used when refreshing completed extraction.")
    parser.add_argument("--server")
    parser.add_argument("--database")
    parser.add_argument("--schema")
    parser.add_argument("--promotion-advice-table")
    parser.add_argument("--pwlogd-table")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--odbc-driver")
    parser.add_argument("--encrypt", choices=("yes", "no"))
    parser.add_argument("--trust-server-certificate", choices=("yes", "no"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    artifacts = PromotionArtifactPaths.from_env(
        root=Path(args.artifact_root) if args.artifact_root else None,
        env_file=args.env_file,
    )
    try:
        base_frame, source_base_path, source_manifest_path, source_run_id = _resolve_base_frame(
            args=args,
            artifacts=artifacts,
        )
        rebuilt = rebuild_training_dataset(
            run_id=args.run_id,
            artifacts=artifacts,
            base_frame=base_frame,
            source_base_path=source_base_path,
            source_manifest_path=source_manifest_path,
            source_run_id=source_run_id,
            row_limit=args.row_limit,
            negative_stock_policy=args.negative_stock_policy,
            negative_stock_quarantine_max_fraction=args.negative_stock_quarantine_max_fraction,
            negative_stock_quarantine_max_absolute=args.negative_stock_quarantine_max_absolute,
        )
    except (FileNotFoundError, PromotionTrainingDataExportError, PromotionTrainingDatasetRebuildError) as error:
        parser.error(str(error))

    print(json.dumps(asdict(rebuilt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())