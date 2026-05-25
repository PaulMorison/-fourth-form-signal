from __future__ import annotations

"""CLI for exporting full promotions model-input diagnosis CSVs."""

import argparse
import json
from pathlib import Path
import re
from typing import Sequence

import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.datasets.model_input_export import (
    PromotionModelInputCsvExportError,
    write_model_input_csv_diagnosis_bundle,
)


def _parse_bool(raw_value: str) -> bool:
    normalized = str(raw_value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected true/false value, got {raw_value!r}")


def _slug_part(raw_value: object) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(raw_value).strip().lower()).strip("-")
    return slug[:80] or "blank"


def _context_slug(
    *,
    selection_mode: str,
    as_of_date: str | None,
    store_numbers: Sequence[str],
    promotion_names: Sequence[str],
    promotion_header_keys: Sequence[str],
    promotion_row_keys: Sequence[str],
) -> str:
    parts = [selection_mode]
    if as_of_date:
        parts.append(_slug_part(as_of_date))
    if store_numbers:
        parts.append("store-" + "-".join(_slug_part(value) for value in store_numbers[:3]))
    if promotion_names:
        parts.append("promotion-" + "-".join(_slug_part(value) for value in promotion_names[:2]))
    if promotion_header_keys:
        parts.append("promotion-key-" + "-".join(_slug_part(value) for value in promotion_header_keys[:2]))
    if promotion_row_keys:
        parts.append("row-key-" + "-".join(_slug_part(value) for value in promotion_row_keys[:2]))
    if len(parts) == 1:
        parts.append("all-rows")
    return "_".join(parts)


def _values(raw_values: Sequence[str] | None) -> list[str]:
    return [str(value) for value in (raw_values or []) if str(value).strip()]


def _build_filters(
    *,
    store_numbers: Sequence[str],
    promotion_names: Sequence[str],
    promotion_header_keys: Sequence[str],
    promotion_row_keys: Sequence[str],
) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    if store_numbers:
        filters["store_number"] = list(store_numbers)
    if promotion_names:
        filters["promotion_name"] = list(promotion_names)
    if promotion_header_keys:
        filters["promotion_header_key"] = list(promotion_header_keys)
    if promotion_row_keys:
        filters["promotion_row_key"] = list(promotion_row_keys)
    return filters


def _required_parquet(path: Path, *, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{label} parquet does not exist: {path}")
    return pd.read_parquet(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export full CSVs for completed/future promotions model-input diagnosis."
    )
    parser.add_argument("--env-file", help="Optional .env file to load before resolving artifact roots.")
    parser.add_argument("--artifact-root", help="Override governed promotions artifact root.")
    parser.add_argument("--run-id", required=True, help="Primary run id used in the default output path.")
    parser.add_argument("--training-run-id", help="Training run id. Defaults to --run-id.")
    parser.add_argument("--scoring-run-id", help="Scoring/future run id. Defaults to --run-id.")
    parser.add_argument("--as-of-date", help="Optional context date recorded in the export manifest/path.")
    parser.add_argument(
        "--selection-mode",
        choices=("completed", "future", "both"),
        default="both",
        help="Which model-input sides to export.",
    )
    parser.add_argument("--store-number", action="append", default=[], help="Filter by store_number. Repeat for multiple stores.")
    parser.add_argument("--promotion-name", action="append", default=[], help="Filter by promotion_name. Repeat for multiple names.")
    parser.add_argument("--promotion-header-key", action="append", default=[], help="Filter by promotion_header_key. Repeat for multiple keys.")
    parser.add_argument("--promotion-row-key", action="append", default=[], help="Filter by promotion_row_key. Repeat for multiple keys.")
    parser.add_argument("--promotion-key", action="append", default=[], help="Alias for --promotion-header-key.")
    parser.add_argument("--completed-raw-parquet", help="Override completed raw/source parquet. Default is training_ready.parquet.")
    parser.add_argument("--completed-feature-parquet", help="Override completed exact model-input parquet.")
    parser.add_argument("--future-raw-parquet", help="Override future raw/source parquet. Default is extracted promotion_base.parquet for the scoring run.")
    parser.add_argument("--future-feature-parquet", help="Override future exact model-input parquet.")
    parser.add_argument("--output-root", help="Override output directory for CSV exports.")
    parser.add_argument("--export-raw", type=_parse_bool, default=True, help="Write *_raw.csv files. Default true.")
    parser.add_argument("--export-features", type=_parse_bool, default=True, help="Write *_features.csv files. Default true.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing export files.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    artifacts = PromotionArtifactPaths.from_env(
        root=args.artifact_root,
        env_file=args.env_file,
    )
    training_run_id = args.training_run_id or args.run_id
    scoring_run_id = args.scoring_run_id or args.run_id

    store_numbers = _values(args.store_number)
    promotion_names = _values(args.promotion_name)
    promotion_header_keys = [*_values(args.promotion_header_key), *_values(args.promotion_key)]
    promotion_row_keys = _values(args.promotion_row_key)
    filters = _build_filters(
        store_numbers=store_numbers,
        promotion_names=promotion_names,
        promotion_header_keys=promotion_header_keys,
        promotion_row_keys=promotion_row_keys,
    )

    if args.output_root:
        output_root = Path(args.output_root)
    else:
        output_root = (
            artifacts.inspection_run_root(args.run_id)
            / "model_input_csv_export"
            / _context_slug(
                selection_mode=args.selection_mode,
                as_of_date=args.as_of_date,
                store_numbers=store_numbers,
                promotion_names=promotion_names,
                promotion_header_keys=promotion_header_keys,
                promotion_row_keys=promotion_row_keys,
            )
        )

    completed_raw_frame: pd.DataFrame | None = None
    completed_feature_frame: pd.DataFrame | None = None
    future_raw_frame: pd.DataFrame | None = None
    future_feature_frame: pd.DataFrame | None = None
    source_paths: dict[str, str | None] = {}

    try:
        if args.selection_mode in {"completed", "both"}:
            completed_raw_path = Path(args.completed_raw_parquet) if args.completed_raw_parquet else artifacts.training_dataset_path(training_run_id)
            completed_feature_path = (
                Path(args.completed_feature_parquet)
                if args.completed_feature_parquet
                else artifacts.inspection_run_root(training_run_id) / "model_training_input.parquet"
            )
            completed_raw_frame = _required_parquet(completed_raw_path, label="completed raw/source")
            source_paths["completed_raw_parquet"] = str(completed_raw_path)
            if args.export_features:
                completed_feature_frame = _required_parquet(completed_feature_path, label="completed exact model input")
                source_paths["completed_feature_parquet"] = str(completed_feature_path)

        if args.selection_mode in {"future", "both"}:
            future_raw_path = Path(args.future_raw_parquet) if args.future_raw_parquet else artifacts.extracted_base_path(scoring_run_id)
            future_feature_path = (
                Path(args.future_feature_parquet)
                if args.future_feature_parquet
                else artifacts.inspection_run_root(scoring_run_id) / "model_scoring_input.parquet"
            )
            future_raw_frame = _required_parquet(future_raw_path, label="future raw/source")
            source_paths["future_raw_parquet"] = str(future_raw_path)
            if args.export_features:
                future_feature_frame = _required_parquet(future_feature_path, label="future exact model input")
                source_paths["future_feature_parquet"] = str(future_feature_path)

        paths = write_model_input_csv_diagnosis_bundle(
            output_root=output_root,
            run_id=args.run_id,
            completed_raw_frame=completed_raw_frame,
            completed_feature_frame=completed_feature_frame,
            future_raw_frame=future_raw_frame,
            future_feature_frame=future_feature_frame,
            filters=filters,
            source_paths=source_paths,
            as_of_date=args.as_of_date,
            export_raw=args.export_raw,
            export_features=args.export_features,
            overwrite=args.overwrite,
        )
    except (FileNotFoundError, PromotionModelInputCsvExportError) as error:
        parser.error(str(error))

    print(json.dumps(paths.__dict__, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
