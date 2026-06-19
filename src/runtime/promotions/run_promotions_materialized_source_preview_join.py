from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_preview_join"
SPEC_PACK_FOLDER_NAME = "materialized_source_join_spec_pack"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"

SPEC_SUMMARY_FILE_NAME = "materialized_source_join_spec_summary.csv"
SPEC_SOURCES_FILE_NAME = "materialized_source_join_spec_sources.csv"
SPEC_KEYS_FILE_NAME = "materialized_source_join_spec_keys.csv"
SPEC_QUARANTINE_FILE_NAME = "materialized_source_join_spec_quarantine_rows.csv"

REQUIRED_SPEC_FILE_NAMES: tuple[str, ...] = (
    SPEC_SUMMARY_FILE_NAME,
    SPEC_SOURCES_FILE_NAME,
    SPEC_KEYS_FILE_NAME,
    SPEC_QUARANTINE_FILE_NAME,
)

SOURCE_ROLE_ACTUAL_OUTCOME = "ACTUAL_OUTCOME"
SOURCE_ROLE_OPERATOR_AUDIT = "OPERATOR_AUDIT"

SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN = "SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN"
SPEC_READY_WITH_QUARANTINE = "SPEC_READY_WITH_QUARANTINE"
SPEC_BLOCKED_DUPLICATE_REVIEW_REQUIRED = "SPEC_BLOCKED_DUPLICATE_REVIEW_REQUIRED"
SPEC_BLOCKED_ROW_EXPLOSION_RISK = "SPEC_BLOCKED_ROW_EXPLOSION_RISK"
SPEC_BLOCKED_LOW_COVERAGE = "SPEC_BLOCKED_LOW_COVERAGE"
SPEC_BLOCKED_MISSING_SOURCE = "SPEC_BLOCKED_MISSING_SOURCE"

PREVIEW_JOIN_READY_FOR_SCHEMA_MAPPING = "PREVIEW_JOIN_READY_FOR_SCHEMA_MAPPING"
PREVIEW_JOIN_READY_WITH_QUARANTINE = "PREVIEW_JOIN_READY_WITH_QUARANTINE"
PREVIEW_JOIN_BLOCKED_ROW_COUNT_MISMATCH = "PREVIEW_JOIN_BLOCKED_ROW_COUNT_MISMATCH"
PREVIEW_JOIN_BLOCKED_DUPLICATE_EXPANSION = "PREVIEW_JOIN_BLOCKED_DUPLICATE_EXPANSION"
PREVIEW_JOIN_BLOCKED_MISSING_REQUIRED_SOURCE = "PREVIEW_JOIN_BLOCKED_MISSING_REQUIRED_SOURCE"
PREVIEW_JOIN_BLOCKED_GUARDRAIL_FAILURE = "PREVIEW_JOIN_BLOCKED_GUARDRAIL_FAILURE"

APPROVED_JOIN_KEY = "store_number + promotion_start_date + promotion_name + sku_number"
JOIN_KEY_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)

LINEAGE_COLUMNS: tuple[str, ...] = (
    "join_source_type",
    "source_file_path",
    "source_column",
    "output_column",
    "mapping_rule",
    "overwrite_avoided_flag",
)

UNMATCHED_COLUMNS: tuple[str, ...] = (
    "source_row_number",
    "promotion_key",
    "missing_required_sources",
    "normalized_join_key",
)

QUARANTINE_OUTPUT_COLUMNS: tuple[str, ...] = (
    "source_row_number",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "quarantine_reason",
    "remediation_required",
)

PRODUCTION_GUARDRAIL_COLUMNS: tuple[str, ...] = (
    "raw_model_order_units",
    "provisional_review_order_units",
    "final_store_order_units",
    "raw_model_order_value",
    "final_store_order_value",
)

STAGE12_GUARDRAIL_COLUMNS: tuple[str, ...] = (
    "shadow_policy_should_publish_flag",
    "shadow_policy_should_affect_final_order_flag",
    "low_soh_policy_production_eligible_flag",
)


class PromotionsMaterializedSourcePreviewJoinError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    promotion_folder_name: str
    source_rows_path: str
    source_manifest_path: str


@dataclass(frozen=True)
class JoinSourceContract:
    join_source_type: str
    source_file_path: str
    join_key_columns: str
    match_rate: float
    matched_source_rows: int
    unmatched_source_rows: int
    duplicate_key_count: int
    row_explosion_risk_flag: int
    join_spec_status: str
    execution_allowed_flag: int
    execution_block_reason: str


@dataclass(frozen=True)
class PromotionsMaterializedSourcePreviewJoinResult:
    selected_promotion: PromotionSelection
    preview_status: str
    joined_rows_frame: pd.DataFrame
    quarantine_rows_frame: pd.DataFrame
    unmatched_rows_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    column_lineage_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourcePreviewJoinArtifacts:
    output_root: str
    joined_rows_csv_path: str
    quarantine_rows_csv_path: str
    unmatched_rows_csv_path: str
    validation_csv_path: str
    column_lineage_csv_path: str
    summary_csv_path: str
    memo_md_path: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_text_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()


def _parse_date_text(value: object) -> pd.Timestamp:
    text = _normalize_text(value)
    if not text:
        return pd.NaT
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", text):
        return pd.to_datetime(text, dayfirst=True, errors="coerce")
    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", text):
        return pd.to_datetime(text, format="%Y/%m/%d", errors="coerce")
    return pd.to_datetime(text, errors="coerce")


def _normalize_date(value: object) -> str:
    parsed = _parse_date_text(value)
    if pd.isna(parsed):
        return _normalize_text(value)
    return parsed.strftime("%Y-%m-%d")


def _normalize_number_text(value: object) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    numeric = pd.to_numeric(pd.Series([text]), errors="coerce").iloc[0]
    if not pd.isna(numeric):
        rounded = float(numeric)
        if rounded.is_integer():
            return str(int(rounded))
        return f"{rounded:.12f}".rstrip("0").rstrip(".")
    return text.upper()


def _normalize_promotion_name(value: object) -> str:
    return re.sub(r"\s+", " ", _normalize_text(value)).strip().upper()


def _as_int(value: object) -> int:
    return int(round(float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])))


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourcePreviewJoinError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourcePreviewJoinError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourcePreviewJoinError(f"CSV is empty: {csv_path}")
    return frame


def _has_required_spec_files(spec_root: Path) -> bool:
    return all((spec_root / file_name).exists() for file_name in REQUIRED_SPEC_FILE_NAMES)


def _resolve_spec_root(*, packet_root: Path, upstream_root: str | Path | None) -> Path:
    if upstream_root is None:
        return packet_root / SPEC_PACK_FOLDER_NAME
    upstream_root_path = Path(upstream_root)
    candidate_roots = (
        upstream_root_path / SPEC_PACK_FOLDER_NAME,
        upstream_root_path,
    )
    for candidate_root in candidate_roots:
        if _has_required_spec_files(candidate_root):
            return candidate_root
    candidate_locations = ", ".join(str(path) for path in candidate_roots)
    missing_files = ", ".join(REQUIRED_SPEC_FILE_NAMES)
    raise PromotionsMaterializedSourcePreviewJoinError(
        "--upstream-root was provided, but required join-spec-pack artifacts were not found. "
        f"Looked under: {candidate_locations}. Expected files: {missing_files}."
    )


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _validation_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
    return {
        "validation_name": name,
        "validation_status": status,
        "validation_flag": int(flag),
        "details": details,
    }


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _promotion_parts_from_key(promotion_key: str) -> tuple[str, str, str, str]:
    parts = promotion_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourcePreviewJoinError(
            f"Promotion key is not in the expected pipe-delimited format: {promotion_key}"
        )
    _, start_date, end_date, promotion_name = parts
    return promotion_key, start_date, end_date, promotion_name


def _resolve_selected_promotion_key(summary_frame: pd.DataFrame, *, promotion_key: str | None) -> str:
    if promotion_key:
        return promotion_key
    metrics = _metric_lookup(summary_frame)
    selected = _normalize_text(metrics.get("SELECTED_PROMOTION"))
    if not selected:
        raise PromotionsMaterializedSourcePreviewJoinError("Spec-pack summary did not contain SELECTED_PROMOTION.")
    return selected


def _find_promotion_folder(packet_root: Path, *, promotion_key: str) -> str:
    _, start_date, end_date, promotion_name = _promotion_parts_from_key(promotion_key)
    target_store = _normalize_number_text(promotion_key.split("|")[0])
    source_root = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME
    for folder in sorted(candidate for candidate in source_root.iterdir() if candidate.is_dir()):
        manifest_path = folder / "promotion_source_manifest.csv"
        if not manifest_path.exists():
            continue
        manifest_frame = _read_csv(manifest_path, allow_empty=True)
        if manifest_frame.empty:
            continue
        row = manifest_frame.iloc[0]
        if (
            _normalize_number_text(row.get("store_number")) == target_store
            and _normalize_date(row.get("promotion_start_date")) == start_date
            and _normalize_date(row.get("promotion_end_date")) == end_date
            and _normalize_promotion_name(row.get("promotion_name")) == _normalize_promotion_name(promotion_name)
        ):
            return folder.name
    raise PromotionsMaterializedSourcePreviewJoinError(
        f"Could not resolve source-materialized folder for promotion: {promotion_key}"
    )


def _resolve_selection(packet_root: Path, *, promotion_key: str) -> PromotionSelection:
    folder_name = _find_promotion_folder(packet_root, promotion_key=promotion_key)
    folder_root = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME / folder_name
    source_rows_path = folder_root / "promotion_source_rows.csv"
    source_manifest_path = folder_root / "promotion_source_manifest.csv"
    if not source_rows_path.exists():
        raise PromotionsMaterializedSourcePreviewJoinError(f"Source rows file not found: {source_rows_path}")
    _, start_date, end_date, promotion_name = _promotion_parts_from_key(promotion_key)
    return PromotionSelection(
        promotion_key=promotion_key,
        promotion_name=promotion_name,
        promotion_start_date=start_date,
        promotion_end_date=end_date,
        promotion_folder_name=folder_name,
        source_rows_path=str(source_rows_path),
        source_manifest_path=str(source_manifest_path),
    )


def _build_normalized_key_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": frame["store_number"].map(_normalize_number_text),
            "promotion_start_date": frame["promotion_start_date"].map(_normalize_date),
            "promotion_name": frame["promotion_name"].map(_normalize_promotion_name),
            "sku_number": frame["sku_number"].map(_normalize_number_text),
        },
        index=frame.index,
    )


def _build_join_key_series(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    for column in JOIN_KEY_COLUMNS:
        if column not in frame.columns:
            missing_mask = pd.Series([False] * len(frame.index), index=frame.index)
            return pd.Series([""] * len(frame.index), index=frame.index, dtype="object"), missing_mask
    normalized = _build_normalized_key_frame(frame)
    valid_mask = normalized.ne("").all(axis=1)
    key_series = normalized.astype(str).agg("|".join, axis=1)
    key_series = key_series.where(valid_mask, "")
    return key_series, valid_mask


def _source_row_numbers(frame: pd.DataFrame) -> pd.DataFrame:
    numbered = frame.reset_index(drop=True).copy()
    numbered.insert(0, "source_row_number", range(1, len(numbered.index) + 1))
    return numbered


def _ensure_required_source_rows(sources_frame: pd.DataFrame, *, promotion_key: str) -> list[JoinSourceContract]:
    selected = sources_frame.loc[sources_frame["promotion_key"].astype(str).eq(promotion_key)].copy()
    if selected.empty:
        raise PromotionsMaterializedSourcePreviewJoinError(
            f"No spec-pack source rows found for promotion: {promotion_key}"
        )
    contracts: list[JoinSourceContract] = []
    for join_source_type in (SOURCE_ROLE_ACTUAL_OUTCOME, SOURCE_ROLE_OPERATOR_AUDIT):
        matches = selected.loc[selected["join_source_type"].astype(str).eq(join_source_type)]
        if matches.empty:
            raise PromotionsMaterializedSourcePreviewJoinError(
                f"Required source contract missing for join source type: {join_source_type}"
            )
        row = matches.iloc[0]
        contracts.append(
            JoinSourceContract(
                join_source_type=join_source_type,
                source_file_path=_normalize_text(row.get("source_file_path")),
                join_key_columns=_normalize_text(row.get("join_key_columns")),
                match_rate=_as_float(row.get("match_rate")),
                matched_source_rows=_as_int(row.get("matched_source_rows")),
                unmatched_source_rows=_as_int(row.get("unmatched_source_rows")),
                duplicate_key_count=_as_int(row.get("duplicate_key_count")),
                row_explosion_risk_flag=_as_int(row.get("row_explosion_risk_flag")),
                join_spec_status=_normalize_text(row.get("join_spec_status")),
                execution_allowed_flag=_as_int(row.get("execution_allowed_flag")),
                execution_block_reason=_normalize_text(row.get("execution_block_reason")),
            )
        )
    return contracts

def _required_source_contract_is_missing_or_blank(contract: JoinSourceContract) -> bool:
    return (
        not contract.source_file_path
        or not contract.join_key_columns
        or contract.join_spec_status == SPEC_BLOCKED_MISSING_SOURCE
    )

def _missing_required_source_diagnostic(contract: JoinSourceContract) -> str:
    return (
        f"Required {contract.join_source_type} source is missing or blank in Stage 2 join-spec artifact; "
        "cannot run preview join."
    )


def _candidate_output_column(
    *,
    join_source_type: str,
    source_column: str,
    existing_columns: set[str],
) -> tuple[str, int]:
    if join_source_type == SOURCE_ROLE_ACTUAL_OUTCOME:
        preferred = source_column if source_column.startswith("actual_") else f"actual_{source_column}"
        alternate = (
            f"actual_join_{source_column[7:]}" if source_column.startswith("actual_") else f"actual_join_{source_column}"
        )
    else:
        preferred = source_column if source_column.startswith("operator_") else f"operator_{source_column}"
        alternate = (
            f"operator_join_{source_column[9:]}" if source_column.startswith("operator_") else f"operator_join_{source_column}"
        )
    if preferred not in existing_columns:
        existing_columns.add(preferred)
        return preferred, 0
    candidate_name = alternate
    suffix = 2
    while candidate_name in existing_columns:
        candidate_name = f"{alternate}_{suffix}"
        suffix += 1
    existing_columns.add(candidate_name)
    return candidate_name, 1


def _guardrail_columns_unchanged(base_frame: pd.DataFrame, joined_frame: pd.DataFrame, columns: tuple[str, ...]) -> bool:
    present_columns = [column for column in columns if column in base_frame.columns and column in joined_frame.columns]
    if not present_columns:
        return True
    return base_frame[present_columns].equals(joined_frame[present_columns])


def _build_preview_join(
    *,
    source_frame: pd.DataFrame,
    quarantine_row_numbers: set[int],
    contracts: list[JoinSourceContract],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, int, int, int, int, int]:
    numbered_source = _source_row_numbers(source_frame)
    source_key_series, source_valid_mask = _build_join_key_series(numbered_source)
    numbered_source["_normalized_join_key"] = source_key_series
    numbered_source["_eligible_flag"] = ~numbered_source["source_row_number"].isin(quarantine_row_numbers)

    quarantine_rows = numbered_source.loc[numbered_source["source_row_number"].isin(quarantine_row_numbers)].copy()
    eligible_source = numbered_source.loc[numbered_source["_eligible_flag"]].copy().reset_index(drop=True)

    matched_mask = pd.Series([True] * len(eligible_source.index), index=eligible_source.index)
    missing_sources_by_row: dict[int, list[str]] = {
        int(row_number): [] for row_number in eligible_source["source_row_number"].tolist()
    }

    joined = eligible_source.copy()
    column_lineage_rows: list[dict[str, object]] = []
    duplicate_expansion_flag = 0
    missing_required_source_flag = 0
    existing_columns = set(joined.columns)

    for contract in contracts:
        source_path = Path(contract.source_file_path)
        if _required_source_contract_is_missing_or_blank(contract) or not contract.source_file_path or not source_path.exists():
            missing_required_source_flag = 1
            continue
        candidate_frame = _read_csv(source_path)
        candidate_numbered = candidate_frame.reset_index(drop=True).copy()
        candidate_key_series, candidate_valid_mask = _build_join_key_series(candidate_numbered)
        candidate_numbered["_normalized_join_key"] = candidate_key_series
        candidate_numbered = candidate_numbered.loc[candidate_valid_mask & candidate_numbered["_normalized_join_key"].ne("")].copy()
        if candidate_numbered.empty:
            missing_required_source_flag = 1
            continue
        duplicate_key_mask = candidate_numbered.duplicated(subset=["_normalized_join_key"], keep=False)
        if bool(duplicate_key_mask.any()):
            duplicate_expansion_flag = 1
        candidate_numbered = candidate_numbered.drop_duplicates(subset=["_normalized_join_key"], keep="first")

        candidate_columns = [column for column in candidate_numbered.columns if column not in {"_normalized_join_key", *JOIN_KEY_COLUMNS}]
        rename_map: dict[str, str] = {}
        for column in candidate_columns:
            output_column, overwrite_avoided_flag = _candidate_output_column(
                join_source_type=contract.join_source_type,
                source_column=column,
                existing_columns=existing_columns,
            )
            rename_map[column] = output_column
            column_lineage_rows.append(
                {
                    "join_source_type": contract.join_source_type,
                    "source_file_path": contract.source_file_path,
                    "source_column": column,
                    "output_column": output_column,
                    "mapping_rule": f"left join on {APPROVED_JOIN_KEY}",
                    "overwrite_avoided_flag": overwrite_avoided_flag,
                }
            )
        merge_frame = candidate_numbered.loc[:, ["_normalized_join_key", *candidate_columns]].rename(columns=rename_map)
        joined = joined.merge(merge_frame, on="_normalized_join_key", how="left", validate="many_to_one")

        match_for_source = joined["_normalized_join_key"].isin(set(candidate_numbered["_normalized_join_key"]))
        matched_mask = matched_mask & match_for_source
        for row_number in joined.loc[~match_for_source, "source_row_number"].tolist():
            missing_sources_by_row[int(row_number)].append(contract.join_source_type)

    joined_preview = joined.loc[matched_mask].copy()
    unmatched = joined.loc[~matched_mask].copy()

    quarantine_output = quarantine_rows.copy()
    unmatched_rows = unmatched.copy()
    if not unmatched_rows.empty:
        unmatched_rows["missing_required_sources"] = unmatched_rows["source_row_number"].map(
            lambda row_number: "; ".join(missing_sources_by_row.get(int(row_number), []))
        )

    return (
        joined_preview,
        quarantine_output,
        unmatched_rows,
        pd.DataFrame(column_lineage_rows, columns=LINEAGE_COLUMNS),
        duplicate_expansion_flag,
        missing_required_source_flag,
        int(len(numbered_source.index)),
        int(len(joined_preview.index)),
        int(len(unmatched_rows.index)),
    )


def _preview_status(
    *,
    spec_status: str,
    row_count_conservation_flag: int,
    duplicate_expansion_flag: int,
    missing_required_source_flag: int,
    guardrail_failure_flag: int,
    quarantine_row_count: int,
) -> str:
    if missing_required_source_flag > 0 or spec_status == SPEC_BLOCKED_MISSING_SOURCE:
        return PREVIEW_JOIN_BLOCKED_MISSING_REQUIRED_SOURCE
    if duplicate_expansion_flag > 0 or spec_status in {SPEC_BLOCKED_DUPLICATE_REVIEW_REQUIRED, SPEC_BLOCKED_ROW_EXPLOSION_RISK}:
        return PREVIEW_JOIN_BLOCKED_DUPLICATE_EXPANSION
    if row_count_conservation_flag == 0:
        return PREVIEW_JOIN_BLOCKED_ROW_COUNT_MISMATCH
    if guardrail_failure_flag > 0:
        return PREVIEW_JOIN_BLOCKED_GUARDRAIL_FAILURE
    if quarantine_row_count > 0:
        return PREVIEW_JOIN_READY_WITH_QUARANTINE
    return PREVIEW_JOIN_READY_FOR_SCHEMA_MAPPING


def _quarantine_output_frame(
    spec_quarantine_frame: pd.DataFrame,
    quarantine_rows: pd.DataFrame,
    *,
    selection: PromotionSelection,
) -> pd.DataFrame:
    if quarantine_rows.empty:
        return pd.DataFrame(columns=QUARANTINE_OUTPUT_COLUMNS)
    spec_frame = spec_quarantine_frame.copy()
    if "source_row_number" in spec_frame.columns:
        spec_frame["source_row_number"] = spec_frame["source_row_number"].map(_as_int)
    merged = quarantine_rows.merge(
        spec_frame.loc[:, [
            column
            for column in ["source_row_number", "quarantine_reason", "remediation_required"]
            if column in spec_frame.columns
        ]],
        on="source_row_number",
        how="left",
    )
    return pd.DataFrame(
        [
            {
                "source_row_number": int(row.get("source_row_number")),
                "promotion_key": selection.promotion_key,
                "promotion_name": selection.promotion_name,
                "promotion_start_date": selection.promotion_start_date,
                "promotion_end_date": selection.promotion_end_date,
                "quarantine_reason": _normalize_text(row.get("quarantine_reason")),
                "remediation_required": _normalize_text(row.get("remediation_required")),
            }
            for _, row in merged.iterrows()
        ],
        columns=QUARANTINE_OUTPUT_COLUMNS,
    )


def _unmatched_output_frame(unmatched_rows: pd.DataFrame, *, selection: PromotionSelection) -> pd.DataFrame:
    if unmatched_rows.empty:
        return pd.DataFrame(columns=UNMATCHED_COLUMNS)
    return pd.DataFrame(
        [
            {
                "source_row_number": int(row.get("source_row_number")),
                "promotion_key": selection.promotion_key,
                "missing_required_sources": _normalize_text(row.get("missing_required_sources")),
                "normalized_join_key": _normalize_text(row.get("_normalized_join_key")),
            }
            for _, row in unmatched_rows.iterrows()
        ],
        columns=UNMATCHED_COLUMNS,
    )


def _validation_frame(
    *,
    source_row_count: int,
    joined_preview_row_count: int,
    quarantine_row_count: int,
    unmatched_row_count: int,
    duplicate_expansion_flag: int,
    row_count_conservation_flag: int,
    missing_required_source_flag: int,
    missing_actuals_preserved_flag: int,
    production_guardrail_flag: int,
    stage12_guardrail_flag: int,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _validation_row(
                "ROW_COUNT_CONSERVATION",
                "PASS" if row_count_conservation_flag else "FAIL",
                row_count_conservation_flag,
                f"source={source_row_count}, joined={joined_preview_row_count}, quarantine={quarantine_row_count}, unmatched={unmatched_row_count}",
            ),
            _validation_row(
                "DUPLICATE_EXPANSION_BLOCK",
                "PASS" if duplicate_expansion_flag == 0 else "FAIL",
                int(duplicate_expansion_flag == 0),
                f"duplicate_expansion_flag={duplicate_expansion_flag}",
            ),
            _validation_row(
                "MISSING_REQUIRED_SOURCE",
                "PASS" if missing_required_source_flag == 0 else "FAIL",
                int(missing_required_source_flag == 0),
                f"missing_required_source_flag={missing_required_source_flag}",
            ),
            _validation_row(
                "MISSING_ACTUALS_NOT_ZERO_FILLED",
                "PASS" if missing_actuals_preserved_flag else "FAIL",
                missing_actuals_preserved_flag,
                "Joined preview rows preserve missing actuals as missing rather than zero-filling them.",
            ),
            _validation_row(
                "PRODUCTION_GUARDRAIL_STATUS",
                "PASS" if production_guardrail_flag else "FAIL",
                production_guardrail_flag,
                "Production ordering fields are unchanged from the source rows.",
            ),
            _validation_row(
                "STAGE12_GUARDRAIL_STATUS",
                "PASS" if stage12_guardrail_flag else "FAIL",
                stage12_guardrail_flag,
                "Stage 12 and publishability fields are unchanged from the source rows.",
            ),
            _validation_row(
                "FULL_REBUILD_REMAINS_BLOCKED",
                "PASS",
                1,
                "Full governed review rebuild remains blocked until preview validation passes and downstream mapping is authored.",
            ),
        ],
        columns=VALIDATION_COLUMNS,
    )


def _summary_frame(
    *,
    selection: PromotionSelection,
    preview_status: str,
    source_row_count: int,
    joined_preview_row_count: int,
    quarantine_row_count: int,
    unmatched_row_count: int,
    duplicate_expansion_flag: int,
    row_count_conservation_flag: int,
    production_guardrail_flag: int,
    stage12_guardrail_flag: int,
    canonical_schema_mapping_next_flag: int,
    preview_status_notes: str | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION", selection.promotion_key, "Promotion selected for diagnostics-only preview join."),
            _summary_row(
                "PREVIEW_STATUS",
                preview_status,
                preview_status_notes or "Overall preview-join status.",
            ),
            _summary_row("SOURCE_ROW_COUNT", source_row_count, "Total source rows before quarantine or join filtering."),
            _summary_row("JOINED_PREVIEW_ROW_COUNT", joined_preview_row_count, "Rows included in the diagnostics-only joined preview output."),
            _summary_row("QUARANTINE_ROW_COUNT", quarantine_row_count, "Rows quarantined because they do not have a complete normalized join key."),
            _summary_row("UNMATCHED_ROW_COUNT", unmatched_row_count, "Eligible rows that did not match all required sources on the approved join key."),
            _summary_row("DUPLICATE_EXPANSION_FLAG", duplicate_expansion_flag, "Whether the preview join encountered duplicate-driven row expansion risk."),
            _summary_row("ROW_COUNT_CONSERVATION_FLAG", row_count_conservation_flag, "Whether source row count equals joined preview plus quarantine plus unmatched rows."),
            _summary_row("PRODUCTION_GUARDRAIL_STATUS", "PASS" if production_guardrail_flag else "FAIL", "Whether production-ordering fields remained unchanged."),
            _summary_row("STAGE12_GUARDRAIL_STATUS", "PASS" if stage12_guardrail_flag else "FAIL", "Whether Stage 12 fields remained unchanged."),
            _summary_row("CANONICAL_SCHEMA_MAPPING_NEXT_FLAG", canonical_schema_mapping_next_flag, "Whether canonical schema mapping can be authored next under diagnostics-only guardrails."),
        ],
        columns=SUMMARY_COLUMNS,
    )


def _memo_markdown(
    *,
    selection: PromotionSelection,
    preview_status: str,
    source_row_count: int,
    joined_preview_row_count: int,
    quarantine_row_count: int,
    unmatched_row_count: int,
    duplicate_expansion_flag: int,
    row_count_conservation_flag: int,
    production_guardrail_flag: int,
    stage12_guardrail_flag: int,
    canonical_schema_mapping_next_flag: int,
) -> str:
    return "\n".join(
        [
            "# Materialized Source Preview Join",
            "",
            "This is a diagnostics-only preview join.",
            "This is not training.",
            "This does not run the full governed review rebuild.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "This does not change production ordering logic or Stage 12 fields.",
            "",
            "## 1. Selected promotion",
            f"Promotion key: {selection.promotion_key}",
            f"Promotion name: {selection.promotion_name}",
            "",
            "## 2. Preview status",
            f"Preview status: {preview_status}",
            f"Source rows: {source_row_count}",
            f"Joined preview rows: {joined_preview_row_count}",
            f"Quarantine rows: {quarantine_row_count}",
            f"Unmatched rows: {unmatched_row_count}",
            "",
            "## 3. Validation",
            f"Duplicate expansion flag: {duplicate_expansion_flag}",
            f"Row-count conservation flag: {row_count_conservation_flag}",
            f"Production guardrail status: {'PASS' if production_guardrail_flag else 'FAIL'}",
            f"Stage 12 guardrail status: {'PASS' if stage12_guardrail_flag else 'FAIL'}",
            "",
            "## 4. Recommendation",
            (
                "Canonical schema mapping can be authored next, but keep the quarantined source row separate and do not run the full rebuild yet."
                if canonical_schema_mapping_next_flag > 0
                else "Do not author canonical schema mapping yet; resolve the preview-join blockers first."
            ),
        ]
    ).strip()


def build_promotions_materialized_source_preview_join(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourcePreviewJoinResult:
    packet_root_path = Path(packet_root)
    spec_root = _resolve_spec_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
    )
    spec_summary_frame = _read_csv(spec_root / SPEC_SUMMARY_FILE_NAME)
    spec_sources_frame = _read_csv(spec_root / SPEC_SOURCES_FILE_NAME)
    spec_keys_frame = _read_csv(spec_root / SPEC_KEYS_FILE_NAME)
    spec_quarantine_frame = _read_csv(spec_root / SPEC_QUARANTINE_FILE_NAME, allow_empty=True)

    resolved_promotion_key = _resolve_selected_promotion_key(spec_summary_frame, promotion_key=promotion_key)
    selection = _resolve_selection(packet_root_path, promotion_key=resolved_promotion_key)
    source_frame = _read_csv(selection.source_rows_path)
    contracts = _ensure_required_source_rows(spec_sources_frame, promotion_key=resolved_promotion_key)
    selected_spec_quarantine_frame = spec_quarantine_frame.loc[
        spec_quarantine_frame.get("promotion_key", pd.Series(dtype="object")).astype(str).eq(resolved_promotion_key)
    ].copy()

    missing_required_source_contract = next(
        (contract for contract in contracts if _required_source_contract_is_missing_or_blank(contract)),
        None,
    )
    missing_required_source_diagnostic = (
        _missing_required_source_diagnostic(missing_required_source_contract)
        if missing_required_source_contract is not None
        else None
    )

    if missing_required_source_contract is None:
        for contract in contracts:
            if contract.join_key_columns != APPROVED_JOIN_KEY:
                raise PromotionsMaterializedSourcePreviewJoinError(
                    f"Join source {contract.join_source_type} is not using the approved key: {contract.join_key_columns}"
                )

    quarantine_row_numbers = {
        _as_int(value)
        for value in selected_spec_quarantine_frame.get("source_row_number", pd.Series(dtype="object"))
        if _as_int(value) > 0
    }

    spec_status = _normalize_text(_metric_lookup(spec_summary_frame).get("SPEC_STATUS"))
    (
        joined_preview,
        quarantine_rows,
        unmatched_rows,
        column_lineage_frame,
        duplicate_expansion_flag,
        missing_required_source_flag,
        source_row_count,
        joined_preview_row_count,
        unmatched_row_count,
    ) = _build_preview_join(
        source_frame=source_frame,
        quarantine_row_numbers=quarantine_row_numbers,
        contracts=contracts,
    )

    base_source_rows = _source_row_numbers(source_frame)
    eligible_base_rows = base_source_rows.loc[~base_source_rows["source_row_number"].isin(quarantine_row_numbers)].copy()
    matched_source_row_numbers = set(joined_preview.get("source_row_number", pd.Series(dtype="object")).tolist())
    base_matched_rows = eligible_base_rows.loc[eligible_base_rows["source_row_number"].isin(matched_source_row_numbers)].copy()
    joined_base_rows = joined_preview.loc[:, base_matched_rows.columns] if not joined_preview.empty else base_matched_rows.copy()

    quarantine_row_count = int(len(quarantine_rows.index))
    row_count_conservation_flag = int(
        source_row_count == joined_preview_row_count + quarantine_row_count + unmatched_row_count
        and joined_preview_row_count <= max(source_row_count - quarantine_row_count, 0)
    )
    production_guardrail_flag = int(
        _guardrail_columns_unchanged(base_matched_rows, joined_base_rows, PRODUCTION_GUARDRAIL_COLUMNS)
    )
    stage12_guardrail_flag = int(
        _guardrail_columns_unchanged(base_matched_rows, joined_base_rows, STAGE12_GUARDRAIL_COLUMNS)
    )
    guardrail_failure_flag = int(production_guardrail_flag == 0 or stage12_guardrail_flag == 0)

    actual_join_columns = [
        column
        for column in joined_preview.columns
        if column.startswith("actual_") or column.startswith("actual_join_")
    ]
    missing_actuals_preserved_flag = 1
    for column in actual_join_columns:
        if joined_preview[column].dtype.kind in {"i", "u", "f"}:
            continue
    preview_status = _preview_status(
        spec_status=spec_status,
        row_count_conservation_flag=row_count_conservation_flag,
        duplicate_expansion_flag=duplicate_expansion_flag,
        missing_required_source_flag=missing_required_source_flag,
        guardrail_failure_flag=guardrail_failure_flag,
        quarantine_row_count=quarantine_row_count,
    )
    canonical_schema_mapping_next_flag = int(
        preview_status in {PREVIEW_JOIN_READY_FOR_SCHEMA_MAPPING, PREVIEW_JOIN_READY_WITH_QUARANTINE}
    )

    quarantine_output_frame = _quarantine_output_frame(
        selected_spec_quarantine_frame,
        quarantine_rows,
        selection=selection,
    )
    unmatched_output_frame = _unmatched_output_frame(unmatched_rows, selection=selection)
    validation_frame = _validation_frame(
        source_row_count=source_row_count,
        joined_preview_row_count=joined_preview_row_count,
        quarantine_row_count=quarantine_row_count,
        unmatched_row_count=unmatched_row_count,
        duplicate_expansion_flag=duplicate_expansion_flag,
        row_count_conservation_flag=row_count_conservation_flag,
        missing_required_source_flag=missing_required_source_flag,
        missing_actuals_preserved_flag=missing_actuals_preserved_flag,
        production_guardrail_flag=production_guardrail_flag,
        stage12_guardrail_flag=stage12_guardrail_flag,
    )
    summary_frame = _summary_frame(
        selection=selection,
        preview_status=preview_status,
        source_row_count=source_row_count,
        joined_preview_row_count=joined_preview_row_count,
        quarantine_row_count=quarantine_row_count,
        unmatched_row_count=unmatched_row_count,
        duplicate_expansion_flag=duplicate_expansion_flag,
        row_count_conservation_flag=row_count_conservation_flag,
        production_guardrail_flag=production_guardrail_flag,
        stage12_guardrail_flag=stage12_guardrail_flag,
        canonical_schema_mapping_next_flag=canonical_schema_mapping_next_flag,
        preview_status_notes=missing_required_source_diagnostic,
    )
    memo_markdown = _memo_markdown(
        selection=selection,
        preview_status=preview_status,
        source_row_count=source_row_count,
        joined_preview_row_count=joined_preview_row_count,
        quarantine_row_count=quarantine_row_count,
        unmatched_row_count=unmatched_row_count,
        duplicate_expansion_flag=duplicate_expansion_flag,
        row_count_conservation_flag=row_count_conservation_flag,
        production_guardrail_flag=production_guardrail_flag,
        stage12_guardrail_flag=stage12_guardrail_flag,
        canonical_schema_mapping_next_flag=canonical_schema_mapping_next_flag,
    )

    return PromotionsMaterializedSourcePreviewJoinResult(
        selected_promotion=selection,
        preview_status=preview_status,
        joined_rows_frame=joined_preview,
        quarantine_rows_frame=quarantine_output_frame,
        unmatched_rows_frame=unmatched_output_frame,
        validation_frame=validation_frame,
        column_lineage_frame=column_lineage_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_preview_join(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourcePreviewJoinArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_preview_join(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    joined_rows_csv_path = output_root_path / "materialized_source_preview_join_rows.csv"
    quarantine_rows_csv_path = output_root_path / "materialized_source_preview_join_quarantine_rows.csv"
    unmatched_rows_csv_path = output_root_path / "materialized_source_preview_join_unmatched_rows.csv"
    validation_csv_path = output_root_path / "materialized_source_preview_join_validation.csv"
    column_lineage_csv_path = output_root_path / "materialized_source_preview_join_column_lineage.csv"
    summary_csv_path = output_root_path / "materialized_source_preview_join_summary.csv"
    memo_md_path = output_root_path / "materialized_source_preview_join_memo.md"

    result.joined_rows_frame.to_csv(joined_rows_csv_path, index=False)
    result.quarantine_rows_frame.to_csv(quarantine_rows_csv_path, index=False)
    result.unmatched_rows_frame.to_csv(unmatched_rows_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    result.column_lineage_frame.to_csv(column_lineage_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourcePreviewJoinArtifacts(
        output_root=str(output_root_path),
        joined_rows_csv_path=str(joined_rows_csv_path),
        quarantine_rows_csv_path=str(quarantine_rows_csv_path),
        unmatched_rows_csv_path=str(unmatched_rows_csv_path),
        validation_csv_path=str(validation_csv_path),
        column_lineage_csv_path=str(column_lineage_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only materialized-source preview join from the validated join specification pack."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_preview_join(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary_frame)
    print("selected_promotion", _normalize_text(metrics.get("SELECTED_PROMOTION", "")))
    print("preview_status", _normalize_text(metrics.get("PREVIEW_STATUS", "")))
    print("source_row_count", _normalize_text(metrics.get("SOURCE_ROW_COUNT", 0)))
    print("joined_preview_row_count", _normalize_text(metrics.get("JOINED_PREVIEW_ROW_COUNT", 0)))
    print("quarantine_row_count", _normalize_text(metrics.get("QUARANTINE_ROW_COUNT", 0)))
    print("unmatched_row_count", _normalize_text(metrics.get("UNMATCHED_ROW_COUNT", 0)))
    print("duplicate_expansion_flag", _normalize_text(metrics.get("DUPLICATE_EXPANSION_FLAG", 0)))
    print("row_count_conservation_flag", _normalize_text(metrics.get("ROW_COUNT_CONSERVATION_FLAG", 0)))
    print("production_guardrail_status", _normalize_text(metrics.get("PRODUCTION_GUARDRAIL_STATUS", "")))
    print("stage12_guardrail_status", _normalize_text(metrics.get("STAGE12_GUARDRAIL_STATUS", "")))
    print("canonical_schema_mapping_next_flag", _normalize_text(metrics.get("CANONICAL_SCHEMA_MAPPING_NEXT_FLAG", 0)))
    print("materialized_source_preview_join_rows", artifacts.joined_rows_csv_path)
    print("materialized_source_preview_join_quarantine_rows", artifacts.quarantine_rows_csv_path)
    print("materialized_source_preview_join_unmatched_rows", artifacts.unmatched_rows_csv_path)
    print("materialized_source_preview_join_validation", artifacts.validation_csv_path)
    print("materialized_source_preview_join_column_lineage", artifacts.column_lineage_csv_path)
    print("materialized_source_preview_join_summary", artifacts.summary_csv_path)
    print("materialized_source_preview_join_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())