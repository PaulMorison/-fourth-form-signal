from __future__ import annotations

"""CLI for exporting exact promotions model-input inspection artifacts."""

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.datasets.model_input_export import write_model_input_inspection_artifacts


def _parse_filters(raw_filters: Sequence[str]) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for raw_filter in raw_filters:
        if "=" not in raw_filter:
            raise ValueError(f"Filter must use column=value syntax: {raw_filter}")
        column_name, raw_values = raw_filter.split("=", 1)
        column_name = column_name.strip()
        if not column_name:
            raise ValueError(f"Filter column cannot be blank: {raw_filter}")
        values = [value.strip() for value in raw_values.split(",") if value.strip()]
        filters[column_name] = values
    return filters


def _default_source_path(*, run_id: str, stage: str, artifact_root: str | None) -> Path:
    artifacts = PromotionArtifactPaths.from_env(root=artifact_root)
    filename_by_stage = {
        "training": "model_training_input.parquet",
        "scoring": "model_scoring_input.parquet",
    }
    return artifacts.inspection_run_root(run_id) / filename_by_stage[stage]


def _default_output_root(*, run_id: str, stage: str, artifact_root: str | None) -> Path:
    artifacts = PromotionArtifactPaths.from_env(root=artifact_root)
    return artifacts.inspection_run_root(run_id) / f"{stage}_model_input_inspection"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export exact promotions model-input parquet plus inspection profiles."
    )
    parser.add_argument("--run-id", help="Run id used to resolve default inspection artifact paths.")
    parser.add_argument(
        "--stage",
        choices=("training", "scoring"),
        default="scoring",
        help="Default source model-input artifact when --source-parquet is omitted.",
    )
    parser.add_argument("--artifact-root", help="Override promotions artifact root used with --run-id.")
    parser.add_argument("--source-parquet", help="Exact model-input parquet to inspect.")
    parser.add_argument("--output-root", help="Directory for model_input_* inspection artifacts.")
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Exact filter in column=value1,value2 form. Repeat for multiple columns.",
    )
    parser.add_argument("--sample-rows", type=int, default=10_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.source_parquet:
        source_path = Path(args.source_parquet)
    else:
        if not args.run_id:
            parser.error("--run-id is required when --source-parquet is omitted")
        source_path = _default_source_path(
            run_id=args.run_id,
            stage=args.stage,
            artifact_root=args.artifact_root,
        )
    if not source_path.exists():
        parser.error(f"source parquet does not exist: {source_path}")

    if args.output_root:
        output_root = Path(args.output_root)
    else:
        if not args.run_id:
            output_root = source_path.parent / "model_input_inspection"
        else:
            output_root = _default_output_root(
                run_id=args.run_id,
                stage=args.stage,
                artifact_root=args.artifact_root,
            )

    frame = pd.read_parquet(source_path)
    filters = _parse_filters(args.filter)
    paths = write_model_input_inspection_artifacts(
        model_input_frame=frame,
        output_root=output_root,
        run_id=args.run_id,
        source_path=source_path,
        stage=args.stage,
        filters=filters,
        sample_rows=args.sample_rows,
    )
    print(json.dumps(paths.__dict__, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
