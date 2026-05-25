from __future__ import annotations

"""CLI entrypoint for promotions cohort backtesting and archetype reporting."""

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from models.promotions.cohorts import PromotionArchetypeRanker, PromotionCohortBacktester
from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.cohorts import PromotionCohortHistoryBuilder
from surfaces.promotions.reporting.cohort_report_builder import PromotionCohortReportBuilder


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromotionCohortBacktestManifest:
    run_id: str
    dataset_run_id: str
    dataset_path: str
    as_of_date: str
    minimum_sample_size: int
    similarity_threshold: float
    metrics_path: str
    report_manifest_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    artifact_paths = PromotionArtifactPaths.from_env(root=Path(args.artifact_root) if args.artifact_root else None)
    dataset_path = (
        Path(args.dataset_path)
        if args.dataset_path
        else artifact_paths.training_dataset_path(args.dataset_run_id)
    )
    dataset = pd.read_parquet(dataset_path)
    as_of_date = date.fromisoformat(args.as_of_date) if args.as_of_date else datetime.now(tz=UTC).date()
    history_builder = PromotionCohortHistoryBuilder()
    cohort_history = history_builder.build(
        dataset,
        as_of_date=as_of_date,
        minimum_sample_size=args.minimum_sample_size,
    )
    backtest_result = PromotionCohortBacktester().backtest(
        cohort_history.assigned_frame,
        as_of_date=as_of_date,
        minimum_sample_size=args.minimum_sample_size,
        similarity_threshold=args.similarity_threshold,
    )
    ranking_result = PromotionArchetypeRanker().rank(
        cohort_history.archetype_history_frame,
        minimum_sample_size=args.minimum_sample_size,
    )
    reporting_artifacts = PromotionCohortReportBuilder().write_reports(
        run_id=args.run_id,
        cohort_history=cohort_history,
        backtest_result=backtest_result,
        ranking_result=ranking_result,
        artifact_paths=artifact_paths,
    )
    manifest_path = artifact_paths.cohort_manifest_path(args.run_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            PromotionCohortBacktestManifest(
                run_id=args.run_id,
                dataset_run_id=args.dataset_run_id,
                dataset_path=str(dataset_path),
                as_of_date=str(as_of_date),
                minimum_sample_size=args.minimum_sample_size,
                similarity_threshold=args.similarity_threshold,
                metrics_path=reporting_artifacts.metrics_path,
                report_manifest_path=reporting_artifacts.manifest_path,
            ).to_dict(),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    LOGGER.info(
        "Completed promotions cohort backtest: run_id=%s dataset_run_id=%s rows=%s",
        args.run_id,
        args.dataset_run_id,
        len(backtest_result.row_matches_frame.index),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backtest promotions cohorts and archetype learning.")
    parser.add_argument("--dataset-run-id", required=True)
    parser.add_argument("--dataset-path")
    parser.add_argument("--artifact-root")
    parser.add_argument("--as-of-date")
    parser.add_argument("--minimum-sample-size", type=int, default=3)
    parser.add_argument("--similarity-threshold", type=float, default=0.55)
    parser.add_argument(
        "--run-id",
        default=datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
    )
    return parser


if __name__ == "__main__":
    main()