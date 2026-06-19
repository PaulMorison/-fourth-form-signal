from __future__ import annotations

"""CLI for exporting a governed promotions training-data inspection sample."""

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.datasets.model_input_export import (
    PromotionTrainingDataExportError,
    write_training_data_sample_artifacts,
)


def _required_parquet(path: Path, *, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{label} parquet does not exist: {path}")
    return pd.read_parquet(path)


def _load_manifest_columns(path: Path | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if path is None:
        return (), ()
    if not path.exists():
        raise FileNotFoundError(f"dataset manifest does not exist: {path}")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a governed parquet + CSV + schema + quality summary for promotions training data."
    )
    parser.add_argument("--env-file", help="Optional .env file to load before resolving artifact roots.")
    parser.add_argument("--artifact-root", help="Override governed promotions artifact root.")
    parser.add_argument("--run-id", required=True, help="Run id used to resolve default artifact paths.")
    parser.add_argument(
        "--source-dataset-path",
        "--dataset-parquet",
        dest="source_dataset_path",
        help="Override the source training dataset parquet. Default is training_ready.parquet for --run-id.",
    )
    parser.add_argument(
        "--dataset-manifest-path",
        help="Override the dataset manifest JSON. Required when using default governed run-id paths.",
    )
    parser.add_argument(
        "--output-root",
        help="Override the governed inspection output root. Default is inspection/<run-id>/training_data_export.",
    )
    parser.add_argument(
        "--row-limit",
        type=int,
        default=10_000,
        help="Row cap for the inspection CSV sample. Default 10000.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    artifacts = PromotionArtifactPaths.from_env(
        root=args.artifact_root,
        env_file=args.env_file,
    )
    dataset_path = (
        Path(args.source_dataset_path)
        if args.source_dataset_path
        else artifacts.training_dataset_path(args.run_id)
    )
    manifest_path: Path | None
    if args.dataset_manifest_path:
        manifest_path = Path(args.dataset_manifest_path)
    elif args.source_dataset_path:
        manifest_path = None
    else:
        manifest_path = artifacts.dataset_manifest_path(args.run_id)
    output_root = (
        Path(args.output_root)
        if args.output_root
        else artifacts.inspection_run_root(args.run_id) / "training_data_export"
    )

    try:
        dataset_frame = _required_parquet(dataset_path, label="training dataset")
        feature_columns, target_columns = _load_manifest_columns(manifest_path)
        paths = write_training_data_sample_artifacts(
            run_id=args.run_id,
            dataset_frame=dataset_frame,
            output_root=output_root,
            source_dataset_path=dataset_path,
            source_manifest_path=manifest_path,
            row_limit=args.row_limit,
            feature_columns=feature_columns or None,
            target_columns=target_columns or None,
        )
    except (FileNotFoundError, json.JSONDecodeError, PromotionTrainingDataExportError) as error:
        parser.error(str(error))

    print(json.dumps(paths.__dict__, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())