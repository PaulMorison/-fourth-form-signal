from __future__ import annotations

"""Thin end-to-end promotions system smoke entrypoint."""

from datetime import UTC, date, datetime
import argparse
import logging
from pathlib import Path

from models.promotions.trainer import PROMOTION_TRAINER_TARGET_MODE_CHOICES
from runtime.promotions.config import (
    PromotionArtifactPaths,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
)
from runtime.promotions.run_promotions_operational_cycle import (
    PromotionOperationalCycleArtifacts,
    run_operational_cycle,
)
from runtime.promotions.smoke_support import (
    build_smoke_extraction_provider,
    smoke_synthetic_default_as_of_date,
)


LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    artifacts = run_system_smoke(
        settings=_build_settings(args),
        run_id=args.run_id,
        score_run_id=args.score_run_id,
        decision_surface_run_id=args.decision_surface_run_id,
        target_mode=args.target_mode,
        minimum_cohort_sample_size=args.minimum_cohort_sample_size,
        similarity_threshold=args.similarity_threshold,
        archetype_confidence_floor=args.archetype_confidence_floor,
        row_model_confidence_floor=args.row_model_confidence_floor,
        execution_mode=args.mode,
        completed_base_path=args.completed_base_path,
        future_base_path=args.future_base_path,
    )
    LOGGER.info(
        "Completed promotions system smoke run: manifest=%s store_csv=%s",
        artifacts.manifest_path,
        artifacts.store_prediction_download_path,
    )


def run_system_smoke(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    score_run_id: str | None = None,
    decision_surface_run_id: str | None = None,
    target_mode: str | None = None,
    minimum_cohort_sample_size: int = 1,
    similarity_threshold: float | None = 0.50,
    archetype_confidence_floor: float | None = 0.35,
    row_model_confidence_floor: float | None = 0.35,
    execution_mode: str = "smoke_synthetic",
    completed_base_path: str | None = None,
    future_base_path: str | None = None,
) -> PromotionOperationalCycleArtifacts:
    extraction_provider = build_smoke_extraction_provider(
        execution_mode=execution_mode,
        completed_base_path=completed_base_path,
        future_base_path=future_base_path,
    )
    return run_operational_cycle(
        settings=settings,
        run_id=run_id,
        score_run_id=score_run_id,
        decision_surface_run_id=decision_surface_run_id,
        target_mode=target_mode,
        minimum_cohort_sample_size=minimum_cohort_sample_size,
        similarity_threshold=similarity_threshold,
        archetype_confidence_floor=archetype_confidence_floor,
        row_model_confidence_floor=row_model_confidence_floor,
        execution_mode=execution_mode,
        extraction_provider=extraction_provider,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the promotions end-to-end system smoke test.")
    parser.add_argument("--env-file")
    parser.add_argument("--server")
    parser.add_argument("--database")
    parser.add_argument("--schema")
    parser.add_argument("--promotion-advice-table")
    parser.add_argument("--pwlogd-table")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--odbc-driver")
    parser.add_argument("--query-timeout-seconds", type=int)
    parser.add_argument("--encrypt", choices=("yes", "no"))
    parser.add_argument("--trust-server-certificate", choices=("yes", "no"))
    parser.add_argument("--artifact-root")
    parser.add_argument("--local-inspection-root")
    parser.add_argument("--disable-local-inspection-copy", action="store_true")
    parser.add_argument("--as-of-date")
    parser.add_argument("--target-mode", choices=PROMOTION_TRAINER_TARGET_MODE_CHOICES)
    parser.add_argument(
        "--run-id",
        default=f"promotions-system-smoke-{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}",
    )
    parser.add_argument("--score-run-id")
    parser.add_argument("--decision-surface-run-id")
    parser.add_argument("--minimum-cohort-sample-size", type=int, default=1)
    parser.add_argument("--similarity-threshold", type=float, default=0.50)
    parser.add_argument("--archetype-confidence-floor", type=float, default=0.35)
    parser.add_argument("--row-model-confidence-floor", type=float, default=0.35)
    parser.add_argument(
        "--mode",
        choices=("live_sql", "smoke_synthetic", "smoke_patched_extraction"),
        default="smoke_synthetic",
    )
    parser.add_argument("--completed-base-path")
    parser.add_argument("--future-base-path")
    return parser


def _build_settings(args: argparse.Namespace) -> PromotionPipelineSettings:
    runtime_date = date.fromisoformat(args.as_of_date) if args.as_of_date else None
    if runtime_date is None and args.mode == "smoke_synthetic":
        runtime_date = smoke_synthetic_default_as_of_date()
    artifact_paths = PromotionArtifactPaths.from_env(
        root=Path(args.artifact_root) if args.artifact_root else None,
        local_inspection_root=(
            Path(args.local_inspection_root) if args.local_inspection_root else None
        ),
        enable_local_inspection_copy=not args.disable_local_inspection_copy,
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
            query_timeout_seconds=args.query_timeout_seconds,
            encrypt=args.encrypt,
            trust_server_certificate=args.trust_server_certificate,
        ),
        runtime_date=runtime_date,
        artifacts=artifact_paths,
    )


if __name__ == "__main__":
    main()
