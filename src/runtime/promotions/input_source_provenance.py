from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pandas as pd


SOURCE_WARNING_TEXT = (
    "SOURCE WARNING: This run used a substitute actual-review source and should not be treated as final "
    "certified evidence until rerun with the exact actual review file."
)

ACTUAL_REVIEW_SOURCE_STATUSES = frozenset(
    {
        "EXACT_REQUESTED_FILE_USED",
        "SUBSTITUTE_MATCHED_SOURCE_USED",
        "INFERRED_EXISTING_BACKTEST_SOURCE_USED",
        "MISSING",
        "UNKNOWN",
    }
)

SOURCE_CERTIFICATION_STATUSES = frozenset(
    {
        "CERTIFIED_EXACT",
        "CERTIFIED_EQUIVALENT",
        "DEVELOPMENT_ONLY_SUBSTITUTE",
        "FAILED_MISSING_SOURCE",
        "FAILED_ROW_MISMATCH",
        "FAILED_SKU_MISMATCH",
    }
)

INPUT_SOURCE_MANIFEST_COLUMNS: tuple[str, ...] = (
    "run_id",
    "created_at",
    "feature_inspection_csv_path",
    "feature_inspection_file_exists",
    "feature_inspection_file_hash_sha256",
    "feature_inspection_modified_time",
    "feature_inspection_row_count",
    "feature_inspection_sku_count",
    "allocation_report_csv_path",
    "allocation_report_file_exists",
    "allocation_report_file_hash_sha256",
    "allocation_report_modified_time",
    "allocation_report_row_count",
    "allocation_report_sku_count",
    "actual_review_csv_path_requested",
    "actual_review_csv_path_used",
    "actual_review_source_status",
    "actual_review_file_exists",
    "actual_review_file_hash_sha256",
    "actual_review_modified_time",
    "actual_review_row_count",
    "actual_review_sku_count",
    "matched_sku_count",
    "unmatched_feature_sku_count",
    "unmatched_actual_sku_count",
    "source_certification_status",
    "source_certification_reason",
)

SOURCE_CERTIFICATION_OUTPUT_COLUMNS: tuple[str, ...] = (
    "actual_review_source_status",
    "source_certification_status",
    "source_certification_reason",
    "actual_review_csv_path_used",
    "actual_review_file_hash_sha256",
)


@dataclass(frozen=True)
class SourceResolution:
    requested_actual_review_csv_path: Path
    used_actual_review_csv_path: Path | None
    actual_review_source_status: str
    warning: str


def read_csv_input(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False, low_memory=False)


def resolve_actual_review_source(
    *,
    requested_actual_review_csv_path: str | Path,
    allow_substitute_actual_review: bool = False,
    substitute_actual_review_csv_path: str | Path | None = None,
) -> SourceResolution:
    requested = Path(requested_actual_review_csv_path)
    if requested.exists():
        return SourceResolution(
            requested_actual_review_csv_path=requested,
            used_actual_review_csv_path=requested,
            actual_review_source_status="EXACT_REQUESTED_FILE_USED",
            warning="",
        )
    if not allow_substitute_actual_review:
        raise FileNotFoundError(
            f"Requested actual review CSV does not exist: {requested}. "
            "Pass --allow-substitute-actual-review with --actual-review-substitute-csv only for development-only substitute runs."
        )
    if substitute_actual_review_csv_path is None:
        raise FileNotFoundError(
            f"Requested actual review CSV does not exist: {requested}; no substitute source was provided."
        )
    substitute = Path(substitute_actual_review_csv_path)
    if not substitute.exists():
        raise FileNotFoundError(f"Substitute actual review CSV does not exist: {substitute}")
    source_status = (
        "INFERRED_EXISTING_BACKTEST_SOURCE_USED"
        if "actual_outcome_backtest" in substitute.name.lower()
        else "SUBSTITUTE_MATCHED_SOURCE_USED"
    )
    return SourceResolution(
        requested_actual_review_csv_path=requested,
        used_actual_review_csv_path=substitute,
        actual_review_source_status=source_status,
        warning=SOURCE_WARNING_TEXT,
    )


def file_sha256(path: str | Path | None) -> str:
    if path is None:
        return ""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return ""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_modified_time(path: str | Path | None) -> str:
    if path is None:
        return ""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return ""
    return datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC).replace(microsecond=0).isoformat()


def _normalize_identifier(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    normalized = numeric.round(0).astype("Int64").astype(str).replace("<NA>", "")
    fallback = series.fillna("").astype(str).str.strip()
    return normalized.where(normalized.ne(""), fallback).astype(str).str.strip()


def sku_series(frame: pd.DataFrame) -> pd.Series:
    if "sku_number" not in frame.columns:
        return pd.Series("", index=frame.index, dtype="object")
    return _normalize_identifier(frame["sku_number"])


def sku_count(frame: pd.DataFrame | None) -> int:
    if frame is None or frame.empty or "sku_number" not in frame.columns:
        return 0
    return int(sku_series(frame).replace("", pd.NA).dropna().nunique())


def _file_info(prefix: str, path: str | Path | None, frame: pd.DataFrame | None) -> dict[str, object]:
    file_path = Path(path) if path else None
    exists = bool(file_path is not None and file_path.exists() and file_path.is_file())
    return {
        f"{prefix}_csv_path": str(file_path) if file_path is not None else "",
        f"{prefix}_file_exists": exists,
        f"{prefix}_file_hash_sha256": file_sha256(file_path),
        f"{prefix}_modified_time": file_modified_time(file_path),
        f"{prefix}_row_count": int(len(frame.index)) if frame is not None else 0,
        f"{prefix}_sku_count": sku_count(frame),
    }


def match_counts(feature_frame: pd.DataFrame, actual_frame: pd.DataFrame) -> tuple[int, int, int]:
    feature_skus = sku_series(feature_frame)
    actual_skus = sku_series(actual_frame)
    actual_sku_set = set(actual_skus[actual_skus.ne("")])
    feature_sku_set = set(feature_skus[feature_skus.ne("")])
    feature_match_mask = feature_skus.isin(actual_sku_set) & feature_skus.ne("")
    actual_unmatched_mask = (~actual_skus.isin(feature_sku_set)) | actual_skus.eq("")
    return int(feature_match_mask.sum()), int((~feature_match_mask).sum()), int(actual_unmatched_mask.sum())


def certify_source(
    *,
    actual_review_source_status: str,
    feature_row_count: int,
    actual_row_count: int,
    matched_sku_count: int,
    unmatched_feature_sku_count: int,
    unmatched_actual_sku_count: int,
) -> tuple[str, str]:
    if actual_review_source_status == "MISSING":
        return "FAILED_MISSING_SOURCE", "Actual review source is missing."
    if unmatched_feature_sku_count > 0 or unmatched_actual_sku_count > 0:
        return (
            "FAILED_SKU_MISMATCH",
            f"SKU coverage mismatch: matched={matched_sku_count}, unmatched_feature={unmatched_feature_sku_count}, unmatched_actual={unmatched_actual_sku_count}.",
        )
    if feature_row_count != actual_row_count:
        return (
            "FAILED_ROW_MISMATCH",
            f"Row count mismatch: feature_rows={feature_row_count}, actual_rows={actual_row_count}.",
        )
    if actual_review_source_status == "EXACT_REQUESTED_FILE_USED":
        return "CERTIFIED_EXACT", "Requested actual review file exists and row/SKU coverage matches the feature inspection input."
    if actual_review_source_status in {"SUBSTITUTE_MATCHED_SOURCE_USED", "INFERRED_EXISTING_BACKTEST_SOURCE_USED"}:
        return "DEVELOPMENT_ONLY_SUBSTITUTE", SOURCE_WARNING_TEXT
    return "CERTIFIED_EQUIVALENT", "Actual review source matched row/SKU counts but exact source status was not explicit."


def build_input_source_manifest(
    *,
    run_id: str,
    feature_inspection_csv_path: str | Path,
    feature_inspection_frame: pd.DataFrame,
    allocation_report_csv_path: str | Path | None,
    allocation_report_frame: pd.DataFrame | None,
    actual_review_csv_path_requested: str | Path,
    actual_review_csv_path_used: str | Path | None,
    actual_review_source_status: str,
    actual_review_frame: pd.DataFrame | None,
) -> dict[str, object]:
    actual_frame = actual_review_frame if actual_review_frame is not None else pd.DataFrame()
    matched_skus, unmatched_feature_skus, unmatched_actual_skus = match_counts(feature_inspection_frame, actual_frame)
    source_certification_status, source_certification_reason = certify_source(
        actual_review_source_status=actual_review_source_status,
        feature_row_count=int(len(feature_inspection_frame.index)),
        actual_row_count=int(len(actual_frame.index)),
        matched_sku_count=matched_skus,
        unmatched_feature_sku_count=unmatched_feature_skus,
        unmatched_actual_sku_count=unmatched_actual_skus,
    )
    manifest: dict[str, object] = {
        "run_id": run_id,
        "created_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
    }
    manifest.update(_file_info("feature_inspection", feature_inspection_csv_path, feature_inspection_frame))
    manifest.update(_file_info("allocation_report", allocation_report_csv_path, allocation_report_frame))
    actual_path = Path(actual_review_csv_path_used) if actual_review_csv_path_used else None
    manifest.update(
        {
            "actual_review_csv_path_requested": str(Path(actual_review_csv_path_requested)),
            "actual_review_csv_path_used": str(actual_path) if actual_path else "",
            "actual_review_source_status": actual_review_source_status,
            "actual_review_file_exists": bool(actual_path is not None and actual_path.exists() and actual_path.is_file()),
            "actual_review_file_hash_sha256": file_sha256(actual_path),
            "actual_review_modified_time": file_modified_time(actual_path),
            "actual_review_row_count": int(len(actual_frame.index)),
            "actual_review_sku_count": sku_count(actual_frame),
            "matched_sku_count": matched_skus,
            "unmatched_feature_sku_count": unmatched_feature_skus,
            "unmatched_actual_sku_count": unmatched_actual_skus,
            "source_certification_status": source_certification_status,
            "source_certification_reason": source_certification_reason,
        }
    )
    return {column_name: manifest.get(column_name, "") for column_name in INPUT_SOURCE_MANIFEST_COLUMNS}


def provenance_fields(manifest: dict[str, object]) -> dict[str, object]:
    return {
        "actual_review_source_status": manifest.get("actual_review_source_status", "UNKNOWN"),
        "source_certification_status": manifest.get("source_certification_status", "FAILED_MISSING_SOURCE"),
        "source_certification_reason": manifest.get("source_certification_reason", "Source certification was not available."),
        "actual_review_csv_path_used": manifest.get("actual_review_csv_path_used", ""),
        "actual_review_file_hash_sha256": manifest.get("actual_review_file_hash_sha256", ""),
    }


def add_provenance_columns(frame: pd.DataFrame, manifest: dict[str, object]) -> pd.DataFrame:
    out = frame.copy()
    for column_name, value in provenance_fields(manifest).items():
        out[column_name] = value
    return out


def write_input_source_manifest(manifest: dict[str, object], output_root: str | Path) -> tuple[Path, Path]:
    output_path = Path(output_root)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "input_source_manifest.json"
    csv_path = output_path / "input_source_manifest.csv"
    json_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pd.DataFrame([manifest], columns=INPUT_SOURCE_MANIFEST_COLUMNS).to_csv(csv_path, index=False)
    return json_path, csv_path


def source_warning(manifest: dict[str, object]) -> str:
    if manifest.get("source_certification_status") == "DEVELOPMENT_ONLY_SUBSTITUTE":
        return SOURCE_WARNING_TEXT
    return ""


def certification_failed(manifest: dict[str, object]) -> bool:
    return str(manifest.get("source_certification_status", "")).startswith("FAILED_")
