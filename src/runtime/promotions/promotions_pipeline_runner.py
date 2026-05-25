from __future__ import annotations

"""Orchestrated promotions workflow runner.

Modes:
- extract_only: build and persist the completed-promotions base extraction.
- build_dataset: extract completed promotions, engineer targets and features,
  validate the grain, and materialize the train-ready parquet package.
- train: build the dataset and train the reusable promotions model family.
- score: extract future promotion advice rows, engineer the training-compatible
  feature set, score them with an existing model family, and build reports.
- full_pipeline: build the dataset, train the model family, score future rows,
  and emit decision-useful reports in one run.
"""

import argparse
from datetime import UTC, date, datetime
import json
import logging
from pathlib import Path

import pandas as pd

from data.promotions.extracted_dataset_writer import PromotionExtractionWriter
from data.promotions.mssql_query_executor import SqlAlchemyMssqlQueryExecutor
from data.promotions.promotion_base_extractor import PromotionBaseExtractor
from models.promotions.trainer import PromotionModelTrainer
from runtime.promotions.config import (
    PromotionArtifactPaths,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
)
from runtime.promotions.scoring_service import PromotionModelScorer
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler
from state.promotions.feature_engineering.feature_pipeline import PromotionFeatureEngineer
from state.promotions.targets.target_engineering import PromotionTargetEngineer
from surfaces.promotions.reporting.report_builder import PromotionReportBuilder


LOGGER = logging.getLogger(__name__)


def main(*, default_mode: str | None = None) -> None:
    parser = _build_parser(default_mode=default_mode)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = _build_settings(args)
    if args.mode == "extract_only":
        _run_extract_only(settings=settings, run_id=args.run_id)
        return
    if args.mode == "build_dataset":
        _run_build_dataset(settings=settings, run_id=args.run_id)
        return
    if args.mode == "train":
        _run_train(settings=settings, run_id=args.run_id)
        return
    if args.mode == "score":
        _run_score(
            settings=settings,
            score_run_id=args.run_id,
            model_run_id=args.model_run_id,
        )
        return
    if args.mode == "full_pipeline":
        _run_full_pipeline(
            settings=settings,
            train_run_id=args.run_id,
            score_run_id=args.score_run_id or f"{args.run_id}-score",
        )


def _build_parser(*, default_mode: str | None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the governed promotions modelling pipeline.")
    parser.add_argument(
        "--mode",
        choices=("extract_only", "build_dataset", "train", "score", "full_pipeline"),
        default=default_mode or "full_pipeline",
    )
    parser.add_argument("--env-file")
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
    parser.add_argument("--artifact-root")
    parser.add_argument("--as-of-date")
    parser.add_argument(
        "--run-id",
        default=datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
    )
    parser.add_argument("--score-run-id")
    parser.add_argument("--model-run-id")
    return parser


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


def _run_extract_only(*, settings: PromotionPipelineSettings, run_id: str) -> None:
    base_frame = _extract_base_frame(settings=settings, run_id=run_id, selection_mode="completed")
    LOGGER.info("Completed extraction only run: rows=%s", len(base_frame.index))


def _run_build_dataset(*, settings: PromotionPipelineSettings, run_id: str):
    base_frame = _extract_base_frame(settings=settings, run_id=run_id, selection_mode="completed")
    dataset = _build_training_dataset(base_frame=base_frame, settings=settings, run_id=run_id)
    LOGGER.info("Completed dataset build: dataset_path=%s", dataset.dataset_path)
    return dataset


def _run_train(*, settings: PromotionPipelineSettings, run_id: str):
    dataset = _run_build_dataset(settings=settings, run_id=run_id)
    trainer = PromotionModelTrainer()
    artifacts = trainer.train(
        run_id=run_id,
        dataset=dataset.frame,
        dataset_path=dataset.dataset_path,
        artifact_paths=settings.artifacts,
    )
    LOGGER.info("Completed model training: manifest=%s", artifacts.manifest_path)
    return artifacts


def _run_score(*, settings: PromotionPipelineSettings, score_run_id: str, model_run_id: str | None):
    if not model_run_id:
        raise ValueError("--model-run-id is required for score mode.")
    future_base_frame = _extract_base_frame(
        settings=settings,
        run_id=score_run_id,
        selection_mode="future",
    )
    historical_dataset = _load_historical_dataset(settings=settings, model_run_id=model_run_id)
    scorer = PromotionModelScorer()
    scoring_artifacts = scorer.score(
        run_id=score_run_id,
        model_run_id=model_run_id,
        future_base_frame=future_base_frame,
        historical_reference_frame=historical_dataset,
        artifact_paths=settings.artifacts,
    )
    report_builder = PromotionReportBuilder()
    reporting_artifacts = report_builder.write_reports(
        run_id=score_run_id,
        scored_rows=scoring_artifacts.row_frame,
        artifact_paths=settings.artifacts,
    )
    LOGGER.info(
        "Completed scoring and reporting: scoring_manifest=%s reports=%s",
        scoring_artifacts.manifest_path,
        reporting_artifacts.report_paths.get("report_manifest"),
    )
    return scoring_artifacts, reporting_artifacts


def _run_full_pipeline(
    *,
    settings: PromotionPipelineSettings,
    train_run_id: str,
    score_run_id: str,
):
    training_artifacts = _run_train(settings=settings, run_id=train_run_id)
    scoring_artifacts = _run_score(
        settings=settings,
        score_run_id=score_run_id,
        model_run_id=train_run_id,
    )
    return training_artifacts, scoring_artifacts


def _extract_base_frame(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    selection_mode: str,
) -> pd.DataFrame:
    executor = SqlAlchemyMssqlQueryExecutor.from_settings(settings.sql)
    extractor = PromotionBaseExtractor(executor=executor)
    extraction_result = extractor.extract(
        run_id=run_id,
        settings=settings,
        selection_mode=selection_mode,
    )
    writer = PromotionExtractionWriter()
    writer.write(
        base_frame=extraction_result.base_frame,
        manifest=extraction_result.manifest,
        artifact_paths=settings.artifacts,
    )
    return extraction_result.base_frame


def _build_training_dataset(*, base_frame: pd.DataFrame, settings: PromotionPipelineSettings, run_id: str):
    target_result = PromotionTargetEngineer().engineer(base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    assembler = PromotionDatasetAssembler()
    return assembler.assemble_training_dataset(
        run_id=run_id,
        base_frame=base_frame,
        target_frame=target_result.frame,
        feature_frame=feature_result.frame,
        target_columns=target_result.target_columns,
        feature_columns=feature_result.feature_columns,
        artifact_paths=settings.artifacts,
    )


def _load_historical_dataset(*, settings: PromotionPipelineSettings, model_run_id: str) -> pd.DataFrame:
    manifest_path = settings.artifacts.model_family_root(model_run_id) / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_path = Path(manifest["dataset_path"])
    return pd.read_parquet(dataset_path)
