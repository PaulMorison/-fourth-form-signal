from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
from typing import Iterable, Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "last5_promotions_diagnostic_packets"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
MODEL_VS_ACTUAL_PACKET_FOLDER = "model_vs_actual_review"

DISCOVERY_MODE_AUTO = "auto"
DISCOVERY_MODE_GOVERNED_REVIEW_ROOTS = "governed_review_roots"
DISCOVERY_MODE_SOURCE_ROWS = "source_rows"

SOURCE_KIND_GOVERNED_REVIEW_ROOT = "GOVERNED_REVIEW_ROOT"
SOURCE_KIND_SOURCE_ROWS = "SOURCE_ROWS"

SOURCE_FILE_TYPE_GOVERNED_REVIEW_ROOT = "GOVERNED_REVIEW_ROOT"
SOURCE_FILE_TYPE_DECISION_SURFACE = "DECISION_SURFACE"
SOURCE_FILE_TYPE_INSPECTION_REVIEW_PACKET = "INSPECTION_REVIEW_PACKET"
SOURCE_FILE_TYPE_ACTUAL_OUTCOME_BACKTEST = "ACTUAL_OUTCOME_BACKTEST"
SOURCE_FILE_TYPE_OPERATOR_AUDIT = "OPERATOR_AUDIT"
SOURCE_FILE_TYPE_UNKNOWN = "UNKNOWN"

PACKET_WRITTEN = "PACKET_WRITTEN"
MATERIALIZED_SOURCE_ONLY = "MATERIALIZED_SOURCE_ONLY"
NOT_PROCESSED = "NOT_PROCESSED"

AUTO_DISCOVERED = "AUTO_DISCOVERED"
SOURCE_ROW_DISCOVERED = "SOURCE_ROW_DISCOVERED"
REQUESTED_PROMOTION_NOT_FOUND = "REQUESTED_PROMOTION_NOT_FOUND"

MATERIALIZATION_STATUS_GOVERNED_PACKET_COPIED = "GOVERNED_PACKET_COPIED"
MATERIALIZATION_STATUS_SOURCE_ROWS_WRITTEN = "SOURCE_ROWS_WRITTEN"

DOWNSTREAM_CHAIN_ALREADY_AVAILABLE = "DOWNSTREAM_CHAIN_ALREADY_AVAILABLE"
SOURCE_ROWS_NEED_GOVERNED_REBUILD = "SOURCE_ROWS_NEED_GOVERNED_REBUILD"

HARD_FAIL_GUARDRAIL_BREACH = "HARD_FAIL_GUARDRAIL_BREACH"
NO_COMPLETED_PROMOTION_PACKETS_AVAILABLE = "NO_COMPLETED_PROMOTION_PACKETS_AVAILABLE"
REQUIRE_MORE_REPEAT_EVIDENCE = "REQUIRE_MORE_REPEAT_EVIDENCE"
KEEP_SHADOW_ONLY_TEST_FIRST_ACROSS_MORE_PROMOTIONS = (
    "KEEP_SHADOW_ONLY_TEST_FIRST_ACROSS_MORE_PROMOTIONS"
)

PACKET_STAGE_DIRECTORIES: tuple[str, ...] = (
    "pretrain_readiness_inspection",
    "review_overlay_packet",
    "action_layer_unresolved_inspection",
    "action_layer_shadow_calibration_candidates",
    "action_layer_shadow_vs_baseline_simulation",
    "shadow_review_trigger_leaderboard",
)
COMPLETENESS_SUMMARY_PATHS: tuple[str, ...] = (
    "pretrain_readiness_inspection/pretrain_readiness_summary.csv",
    "review_overlay_packet/review_overlay_packet_summary.csv",
    "action_layer_unresolved_inspection/action_layer_unresolved_inspection_summary.csv",
    "action_layer_shadow_calibration_candidates/action_layer_shadow_calibration_candidate_summary.csv",
    "action_layer_shadow_vs_baseline_simulation/action_layer_shadow_vs_baseline_summary.csv",
    "shadow_review_trigger_leaderboard/shadow_review_trigger_leaderboard_summary.csv",
)

PACKET_INDEX_COLUMNS: tuple[str, ...] = (
    "selection_rank",
    "promotion_key",
    "promotion_identifier",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_kind",
    "source_file_type",
    "source_review_root",
    "source_file_path",
    "packet_completeness_score",
    "discovery_status",
    "processing_status",
    "materialization_status",
    "packet_output_path",
    "row_count",
    "sku_count",
    "actual_units",
    "expected_demand",
    "forecast_correlation",
    "forecast_bias_units",
    "forecast_reliability_status",
    "action_layer_unresolved_flags",
    "action_layer_over_suppression_rows",
    "shadow_calibration_candidate_rows",
    "shadow_vs_baseline_incremental_review_triggers",
    "shadow_vs_baseline_high_priority_triggers",
    "tier_1_leaderboard_rows",
    "high_priority_tier_1_rows",
    "gross_profit_represented",
    "capital_left_represented",
    "net_review_value_proxy",
    "production_order_changes",
    "stage_12_changes",
    "downstream_full_diagnostic_chain_available_flag",
    "downstream_full_packet_reason",
    "missing_canonical_fields",
    "final_recommendation",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

FORECAST_RELIABILITY_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_name",
    "promotion_end_date",
    "forecast_correlation",
    "forecast_bias_units",
    "forecast_reliability_status",
    "forecast_reliability_reason",
    "readiness_allows_full_train_flag",
)

ACTION_LAYER_CALIBRATION_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_name",
    "promotion_end_date",
    "action_layer_unresolved_flags",
    "action_layer_over_suppression_rows",
    "shadow_calibration_candidate_rows",
    "shadow_vs_baseline_incremental_review_triggers",
    "shadow_vs_baseline_high_priority_triggers",
    "action_layer_status",
    "action_layer_reason",
    "production_order_changes",
    "stage_12_changes",
)

SHADOW_TRIGGER_REPEATABILITY_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_name",
    "promotion_end_date",
    "shadow_vs_baseline_incremental_review_triggers",
    "tier_1_leaderboard_rows",
    "high_priority_tier_1_rows",
    "gross_profit_represented",
    "capital_left_represented",
    "net_review_value_proxy",
    "repeated_rule_families_in_portfolio",
    "repeated_departments_in_portfolio",
    "repeated_skus_in_portfolio",
    "tier_1_repeatability_status",
)

RULE_FAMILY_REPEAT_EVIDENCE_COLUMNS: tuple[str, ...] = (
    "shadow_rule_family",
    "promotion_count",
    "total_rows",
    "total_tier_1_rows",
    "total_high_priority_tier_1_rows",
    "total_net_review_value_proxy",
    "average_trigger_score",
    "repeat_evidence_level",
    "promotion_keys",
    "promotion_names",
)

SOURCE_SUMMARY_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "row_count",
    "sku_count",
    "actual_units_proxy_total",
    "expected_demand_proxy_total",
    "gross_profit_proxy_total",
    "capital_left_proxy_total",
    "packet_completeness_score",
)

SOURCE_MANIFEST_COLUMNS: tuple[str, ...] = (
    "source_file_path",
    "source_file_type",
    "row_count",
    "sku_count",
    "store_number",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_discovery_status",
    "materialization_status",
    "downstream_full_diagnostic_chain_available_flag",
    "downstream_full_packet_reason",
    "missing_canonical_fields",
)

SOURCE_FILE_PRIORITIES: dict[str, int] = {
    SOURCE_FILE_TYPE_DECISION_SURFACE: 60,
    SOURCE_FILE_TYPE_ACTUAL_OUTCOME_BACKTEST: 55,
    SOURCE_FILE_TYPE_INSPECTION_REVIEW_PACKET: 45,
    SOURCE_FILE_TYPE_OPERATOR_AUDIT: 35,
    SOURCE_FILE_TYPE_UNKNOWN: 0,
}


class PromotionsLast5DiagnosticPacketRunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceColumnMapping:
    store_column: str | None
    promotion_name_column: str | None
    promotion_start_date_column: str | None
    promotion_end_date_column: str | None
    sort_date_column: str | None
    sku_column: str | None
    promotion_identifier_column: str | None
    expected_demand_column: str | None
    actual_units_column: str | None
    gross_profit_column: str | None
    capital_left_column: str | None
    promotion_key_columns: tuple[str, ...]
    missing_canonical_fields: tuple[str, ...]


@dataclass(frozen=True)
class SourceFileInspection:
    path: Path
    source_file_type: str
    score: int
    mapping: SourceColumnMapping


@dataclass(frozen=True)
class PromotionPacketCandidate:
    promotion_key: str
    promotion_slug: str
    promotion_identifier: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    store_number: str
    row_count: int
    sku_count: int
    actual_units: float
    expected_demand: float
    gross_profit_represented: float
    capital_left_represented: float
    source_kind: str
    source_file_type: str
    source_review_root: Path | None
    source_file_path: Path
    packet_completeness_score: int
    source_created_at: str
    downstream_full_diagnostic_chain_available_flag: int
    downstream_full_packet_reason: str
    missing_canonical_fields: tuple[str, ...]


@dataclass(frozen=True)
class PromotionsLast5DiagnosticPacketRunnerResult:
    packet_index_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    forecast_reliability_frame: pd.DataFrame
    action_layer_calibration_frame: pd.DataFrame
    shadow_trigger_repeatability_frame: pd.DataFrame
    rule_family_repeat_evidence_frame: pd.DataFrame
    portfolio_memo_markdown: str


@dataclass(frozen=True)
class PromotionsLast5DiagnosticPacketRunnerArtifacts:
    output_root: str
    packet_index_csv_path: str
    summary_csv_path: str
    forecast_reliability_csv_path: str
    action_layer_calibration_csv_path: str
    shadow_trigger_repeatability_csv_path: str
    rule_family_repeat_evidence_csv_path: str
    portfolio_memo_md_path: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_text_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()


def _normalize_identifier_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    normalized = numeric.round(0).astype("Int64").astype(str).replace("<NA>", "")
    fallback = _normalize_text_series(series)
    return normalized.where(normalized.ne(""), fallback)


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


def _normalize_date_series(series: pd.Series) -> pd.Series:
    raw_text = _normalize_text_series(series)
    parsed = raw_text.apply(_parse_date_text)
    return parsed.dt.strftime("%Y-%m-%d").fillna(raw_text)


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])


def _as_int(value: object) -> int:
    return int(round(_as_float(value)))


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "promotion"


def _sortable_date(value: object) -> pd.Timestamp:
    return _parse_date_text(value)


def _iso_date_text(value: object) -> str:
    parsed = _sortable_date(value)
    if pd.isna(parsed):
        return _normalize_text(value)
    return str(parsed.date())


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _format_int(value: int | float) -> str:
    return f"{int(round(float(value))):,}"


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsLast5DiagnosticPacketRunnerError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsLast5DiagnosticPacketRunnerError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsLast5DiagnosticPacketRunnerError(f"CSV is empty: {csv_path}")
    return frame


def _read_json(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsLast5DiagnosticPacketRunnerError(f"JSON payload must be an object: {path}")
    return payload


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    if {"metric_name", "metric_value"}.issubset(frame.columns):
        return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))
    if {"readiness_check", "metric_value"}.issubset(frame.columns):
        return dict(zip(frame["readiness_check"].astype(str), frame["metric_value"]))
    return {}


def _metric_value(frame: pd.DataFrame, names: Iterable[str], default: object = 0.0) -> object:
    lookup = _metric_lookup(frame)
    for name in names:
        if name in lookup:
            return lookup[name]
    return default


def _readiness_row(frame: pd.DataFrame, readiness_check: str) -> dict[str, object]:
    if frame.empty or "readiness_check" not in frame.columns:
        return {}
    rows = frame.loc[frame["readiness_check"].astype(str).eq(readiness_check)]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def _copy_path(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _packet_output_path(output_root: Path, candidate: PromotionPacketCandidate) -> Path:
    if candidate.source_kind == SOURCE_KIND_SOURCE_ROWS:
        return output_root / SOURCE_MATERIALIZED_FOLDER_NAME / f"promotion_{candidate.promotion_slug}"
    return output_root / f"promotion_{candidate.promotion_slug}"


def _promotion_key(store_number: str, start_date: str, end_date: str, promotion_name: str) -> str:
    return "|".join([store_number, start_date, end_date, promotion_name])


def _safe_source_path(manifest: dict[str, object]) -> Path:
    source = _normalize_text(
        manifest.get("actual_review_csv_path_used")
        or manifest.get("actual_review_csv_path_requested")
    )
    return Path(source) if source else Path()


def _read_actual_review_groups(path: Path, cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cache_key = str(path)
    if cache_key in cache:
        return cache[cache_key]
    header = pd.read_csv(path, nrows=0, low_memory=False).columns.tolist()
    required = [
        "store_number",
        "promotion_name",
        "promotion_start_date",
        "promotional_end_date",
        "sku_number",
        "actual_units_sold",
        "expected_units_during_promo",
    ]
    missing = [column_name for column_name in required if column_name not in header]
    if missing:
        raise PromotionsLast5DiagnosticPacketRunnerError(
            "Actual review source is missing required promotion columns: " + ", ".join(missing)
        )
    optional_ids = [
        column_name
        for column_name in ("promotion_id", "stage11_promotion_id", "promotion_header_key")
        if column_name in header
    ]
    frame = pd.read_csv(path, usecols=[*required, *optional_ids], low_memory=False)
    frame["promotion_start_date"] = pd.to_datetime(frame["promotion_start_date"], dayfirst=True, errors="coerce")
    frame["promotional_end_date"] = pd.to_datetime(frame["promotional_end_date"], dayfirst=True, errors="coerce")
    grouped = frame.groupby(
        ["store_number", "promotion_name", "promotion_start_date", "promotional_end_date"],
        dropna=False,
    ).agg(
        row_count=("sku_number", "size"),
        sku_count=("sku_number", lambda series: series.astype(str).nunique()),
        actual_units=("actual_units_sold", lambda series: pd.to_numeric(series, errors="coerce").fillna(0.0).sum()),
        expected_demand=("expected_units_during_promo", lambda series: pd.to_numeric(series, errors="coerce").fillna(0.0).sum()),
    ).reset_index()
    if optional_ids:
        identifier_column = optional_ids[0]
        identifiers = frame.groupby(
            ["store_number", "promotion_name", "promotion_start_date", "promotional_end_date"],
            dropna=False,
        )[identifier_column].agg(
            lambda series: _normalize_text(next((value for value in series if _normalize_text(value)), ""))
        ).reset_index(name="promotion_identifier")
        grouped = grouped.merge(
            identifiers,
            on=["store_number", "promotion_name", "promotion_start_date", "promotional_end_date"],
            how="left",
        )
    else:
        grouped["promotion_identifier"] = ""
    cache[cache_key] = grouped
    return grouped


def _discover_governed_review_candidate(review_root: Path, cache: dict[str, pd.DataFrame]) -> PromotionPacketCandidate | None:
    manifest_path = review_root / "input_source_manifest.json"
    if not manifest_path.exists() or not (review_root / "model_vs_actual_summary.csv").exists():
        return None
    manifest = _read_json(manifest_path)
    source_file_path = _safe_source_path(manifest)
    if not source_file_path.exists():
        return None
    groups = _read_actual_review_groups(source_file_path, cache)
    if len(groups.index) != 1:
        return None
    row = groups.iloc[0]
    promotion_name = _normalize_text(row.get("promotion_name"))
    start_date = _iso_date_text(row.get("promotion_start_date"))
    end_date = _iso_date_text(row.get("promotional_end_date"))
    store_number = _normalize_text(row.get("store_number"))
    promotion_identifier = _normalize_text(row.get("promotion_identifier")) or _normalize_text(manifest.get("run_id"))
    completeness = sum(int((review_root / relative_path).exists()) for relative_path in COMPLETENESS_SUMMARY_PATHS)
    return PromotionPacketCandidate(
        promotion_key=_promotion_key(store_number, start_date, end_date, promotion_name),
        promotion_slug=_slugify("_".join([store_number, start_date, end_date, promotion_name])),
        promotion_identifier=promotion_identifier,
        promotion_name=promotion_name,
        promotion_start_date=start_date,
        promotion_end_date=end_date,
        store_number=store_number,
        row_count=_as_int(row.get("row_count")),
        sku_count=_as_int(row.get("sku_count")),
        actual_units=_as_float(row.get("actual_units")),
        expected_demand=_as_float(row.get("expected_demand")),
        gross_profit_represented=0.0,
        capital_left_represented=0.0,
        source_kind=SOURCE_KIND_GOVERNED_REVIEW_ROOT,
        source_file_type=SOURCE_FILE_TYPE_GOVERNED_REVIEW_ROOT,
        source_review_root=review_root,
        source_file_path=source_file_path,
        packet_completeness_score=completeness,
        source_created_at=_normalize_text(manifest.get("created_at")),
        downstream_full_diagnostic_chain_available_flag=1,
        downstream_full_packet_reason=DOWNSTREAM_CHAIN_ALREADY_AVAILABLE,
        missing_canonical_fields=(),
    )


def _discover_governed_review_candidates(source_root: Path, output_root: Path | None) -> tuple[list[PromotionPacketCandidate], dict[str, int]]:
    if not source_root.exists():
        raise PromotionsLast5DiagnosticPacketRunnerError(f"Source root does not exist: {source_root}")
    output_root_resolved = output_root.resolve() if output_root is not None and output_root.exists() else None
    cache: dict[str, pd.DataFrame] = {}
    candidates: list[PromotionPacketCandidate] = []
    scanned_roots = 0
    ignored_output_roots = 0
    for manifest_path in source_root.rglob("input_source_manifest.json"):
        scanned_roots += 1
        if output_root_resolved is not None and manifest_path.parent.resolve().is_relative_to(output_root_resolved):
            ignored_output_roots += 1
            continue
        candidate = _discover_governed_review_candidate(manifest_path.parent, cache)
        if candidate is not None:
            candidates.append(candidate)
    return candidates, {
        "scanned_roots": scanned_roots,
        "ignored_output_roots": ignored_output_roots,
    }


def _first_present(columns: Sequence[str], names: Sequence[str | None]) -> str | None:
    available = set(columns)
    for name in names:
        if name and name in available:
            return name
    return None


def _file_type_for_path(path: Path) -> str:
    lowered = path.name.casefold()
    if "decision_surface" in lowered:
        return SOURCE_FILE_TYPE_DECISION_SURFACE
    if "inspection_review_packet" in lowered:
        return SOURCE_FILE_TYPE_INSPECTION_REVIEW_PACKET
    if "actual_outcome_backtest" in lowered:
        return SOURCE_FILE_TYPE_ACTUAL_OUTCOME_BACKTEST
    if "operator_audit" in lowered:
        return SOURCE_FILE_TYPE_OPERATOR_AUDIT
    return SOURCE_FILE_TYPE_UNKNOWN


def _infer_source_mapping(
    columns: Sequence[str],
    *,
    promotion_key_columns: Sequence[str] | None,
    date_column: str | None,
    store_column: str | None,
    sku_column: str | None,
) -> SourceColumnMapping:
    start_date_column = _first_present(
        columns,
        ["promotion_start_date_date", "promotion_start_date", "promotion_start_date_actual", date_column],
    )
    end_date_column = _first_present(
        columns,
        [date_column, "promotion_end_date", "promotional_end_date", "promotional_end_date_date", "promotion_end_date_date"],
    )
    resolved_store_column = _first_present(
        columns,
        [store_column, "store_number", "store_number_actual", "store_number_master", "store_number_key"],
    )
    promotion_name_column = _first_present(columns, ["promotion_name", "promotion_name_actual", "promotion_name_master"])
    resolved_sku_column = _first_present(
        columns,
        [sku_column, "sku_number", "sku_number_actual", "sku_number_master", "sku_number_key", "promotional_sku_id", "promotion_row_key"],
    )
    promotion_identifier_column = _first_present(
        columns,
        ["promotion_id", "stage11_promotion_id", "promotion_store_event_key", "promotion_row_key"],
    )
    expected_demand_column = _first_present(
        columns,
        ["expected_promo_demand", "expected_units_during_promo", "baseline_expected_units", "predicted_units_total_promo"],
    )
    actual_units_column = _first_present(
        columns,
        ["actual_units_sold_promo", "actual_units_sold", "bar_units", "sales_promo_period_avg"],
    )
    gross_profit_column = _first_present(
        columns,
        ["gross_profit_promo_dollars", "gross_profit_promo", "predicted_gross_profit", "estimated_actual_gross_profit", "promo_gm_unit"],
    )
    capital_left_column = _first_present(columns, ["capital_left_in_unsold_store_allocation", "capital_left_unsold"])
    resolved_key_columns = tuple(column_name for column_name in (promotion_key_columns or []) if column_name in set(columns))
    if not resolved_key_columns:
        resolved_key_columns = tuple(
            column_name
            for column_name in (resolved_store_column, start_date_column, end_date_column, promotion_name_column)
            if column_name
        )
    missing_canonical_fields = tuple(
        logical_name
        for logical_name, column_name in (
            ("store_number", resolved_store_column),
            ("promotion_name", promotion_name_column),
            ("promotion_start_date", start_date_column),
            ("promotion_end_date", end_date_column),
            ("sku_number", resolved_sku_column),
        )
        if not column_name
    )
    return SourceColumnMapping(
        store_column=resolved_store_column,
        promotion_name_column=promotion_name_column,
        promotion_start_date_column=start_date_column,
        promotion_end_date_column=end_date_column,
        sort_date_column=end_date_column or start_date_column,
        sku_column=resolved_sku_column,
        promotion_identifier_column=promotion_identifier_column,
        expected_demand_column=expected_demand_column,
        actual_units_column=actual_units_column,
        gross_profit_column=gross_profit_column,
        capital_left_column=capital_left_column,
        promotion_key_columns=resolved_key_columns,
        missing_canonical_fields=missing_canonical_fields,
    )


def _score_source_file(path: Path, mapping: SourceColumnMapping) -> int:
    score = SOURCE_FILE_PRIORITIES.get(_file_type_for_path(path), 0)
    for column_name in (
        mapping.store_column,
        mapping.promotion_name_column,
        mapping.promotion_start_date_column,
        mapping.promotion_end_date_column,
        mapping.sku_column,
    ):
        if column_name:
            score += 6
    for column_name in (
        mapping.expected_demand_column,
        mapping.actual_units_column,
        mapping.gross_profit_column,
        mapping.capital_left_column,
    ):
        if column_name:
            score += 2
    if len(mapping.promotion_key_columns) >= 3:
        score += 10
    return score


def _inspect_source_row_file(
    path: Path,
    *,
    promotion_key_columns: Sequence[str] | None,
    date_column: str | None,
    store_column: str | None,
    sku_column: str | None,
) -> SourceFileInspection | None:
    if not path.exists():
        return None
    columns = pd.read_csv(path, nrows=0, low_memory=False).columns.tolist()
    mapping = _infer_source_mapping(
        columns,
        promotion_key_columns=promotion_key_columns,
        date_column=date_column,
        store_column=store_column,
        sku_column=sku_column,
    )
    score = _score_source_file(path, mapping)
    if score <= 0 or len(mapping.promotion_key_columns) < 3:
        return None
    return SourceFileInspection(
        path=path,
        source_file_type=_file_type_for_path(path),
        score=score,
        mapping=mapping,
    )


def _choose_source_file_inspection(
    *,
    source_root: Path,
    output_root: Path | None,
    source_file: str | Path | None,
    promotion_key_columns: Sequence[str] | None,
    date_column: str | None,
    store_column: str | None,
    sku_column: str | None,
) -> tuple[list[SourceFileInspection], SourceFileInspection | None]:
    if source_file is not None:
        explicit = Path(source_file)
        if not explicit.exists() and not explicit.is_absolute():
            explicit = (Path.cwd() / explicit).resolve()
        inspection = _inspect_source_row_file(
            explicit,
            promotion_key_columns=promotion_key_columns,
            date_column=date_column,
            store_column=store_column,
            sku_column=sku_column,
        )
        if inspection is None:
            raise PromotionsLast5DiagnosticPacketRunnerError(
                f"Explicit source file is missing required grouping columns: {explicit}"
            )
        return [inspection], inspection

    output_root_resolved = output_root.resolve() if output_root is not None and output_root.exists() else None
    inspections: list[SourceFileInspection] = []
    for path in source_root.rglob("*.csv"):
        if output_root_resolved is not None and path.resolve().is_relative_to(output_root_resolved):
            continue
        inspection = _inspect_source_row_file(
            path,
            promotion_key_columns=promotion_key_columns,
            date_column=date_column,
            store_column=store_column,
            sku_column=sku_column,
        )
        if inspection is not None:
            inspections.append(inspection)
    if not inspections:
        return [], None
    selected = sorted(inspections, key=lambda inspection: (inspection.score, str(inspection.path)), reverse=True)[0]
    return inspections, selected


def _numeric_series(frame: pd.DataFrame, column_name: str | None) -> pd.Series:
    if column_name is None or column_name not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0)


def _text_series(frame: pd.DataFrame, column_name: str | None) -> pd.Series:
    if column_name is None or column_name not in frame.columns:
        return pd.Series("", index=frame.index, dtype="object")
    return _normalize_text_series(frame[column_name])


def _id_series(frame: pd.DataFrame, column_name: str | None) -> pd.Series:
    if column_name is None or column_name not in frame.columns:
        return pd.Series("", index=frame.index, dtype="object")
    return _normalize_identifier_series(frame[column_name])


def _date_series(frame: pd.DataFrame, column_name: str | None) -> pd.Series:
    if column_name is None or column_name not in frame.columns:
        return pd.Series("", index=frame.index, dtype="object")
    return _normalize_date_series(frame[column_name])


def _source_packet_completeness_score(mapping: SourceColumnMapping) -> int:
    return sum(
        int(bool(column_name))
        for column_name in (
            mapping.store_column,
            mapping.promotion_name_column,
            mapping.promotion_start_date_column,
            mapping.promotion_end_date_column,
            mapping.sku_column,
            mapping.expected_demand_column,
            mapping.actual_units_column,
            mapping.gross_profit_column,
            mapping.capital_left_column,
        )
    )


def _source_only_reason(mapping: SourceColumnMapping) -> str:
    if mapping.missing_canonical_fields:
        return (
            f"Source-row materialization is missing canonical fields: {', '.join(mapping.missing_canonical_fields)}. "
            "The downstream governed review and action-layer chain cannot run yet."
        )
    return (
        "Source-row materialization is available, but the downstream governed review and action-layer chain "
        "requires validated review-root artifacts that were not rebuilt in this runner."
    )


def _discover_source_row_candidates(inspection: SourceFileInspection) -> list[PromotionPacketCandidate]:
    frame = _read_csv(inspection.path)
    mapping = inspection.mapping
    work = frame.copy()
    work["__store"] = _id_series(work, mapping.store_column)
    work["__promotion_name"] = _text_series(work, mapping.promotion_name_column)
    work["__start_date"] = _date_series(work, mapping.promotion_start_date_column)
    work["__end_date"] = _date_series(work, mapping.promotion_end_date_column or mapping.sort_date_column)
    work["__promotion_identifier"] = _text_series(work, mapping.promotion_identifier_column)
    work["__sku"] = _id_series(work, mapping.sku_column)
    if work["__sku"].eq("").all():
        work["__sku"] = pd.Series([f"row_{index}" for index in range(len(work.index))], index=work.index)
    group_columns = ["__store", "__start_date", "__end_date", "__promotion_name"]
    grouped = work.groupby(group_columns, dropna=False, sort=False)
    candidates: list[PromotionPacketCandidate] = []
    for _, group in grouped:
        store_number = _normalize_text(group["__store"].iloc[0])
        start_date = _normalize_text(group["__start_date"].iloc[0])
        end_date = _normalize_text(group["__end_date"].iloc[0])
        promotion_name = _normalize_text(group["__promotion_name"].iloc[0])
        if not promotion_name or not start_date or not end_date:
            continue
        promotion_key = _promotion_key(store_number, start_date, end_date, promotion_name)
        promotion_identifier = _normalize_text(group["__promotion_identifier"].iloc[0]) or promotion_key
        candidates.append(
            PromotionPacketCandidate(
                promotion_key=promotion_key,
                promotion_slug=_slugify("_".join([store_number, start_date, end_date, promotion_name])),
                promotion_identifier=promotion_identifier,
                promotion_name=promotion_name,
                promotion_start_date=start_date,
                promotion_end_date=end_date,
                store_number=store_number,
                row_count=int(len(group.index)),
                sku_count=int(group["__sku"].astype(str).nunique()),
                actual_units=float(_numeric_series(group, mapping.actual_units_column).sum()),
                expected_demand=float(_numeric_series(group, mapping.expected_demand_column).sum()),
                gross_profit_represented=float(_numeric_series(group, mapping.gross_profit_column).sum()),
                capital_left_represented=float(_numeric_series(group, mapping.capital_left_column).sum()),
                source_kind=SOURCE_KIND_SOURCE_ROWS,
                source_file_type=inspection.source_file_type,
                source_review_root=None,
                source_file_path=inspection.path,
                packet_completeness_score=_source_packet_completeness_score(mapping),
                source_created_at="",
                downstream_full_diagnostic_chain_available_flag=0,
                downstream_full_packet_reason=_source_only_reason(mapping),
                missing_canonical_fields=mapping.missing_canonical_fields,
            )
        )
    return sorted(
        candidates,
        key=lambda candidate: (_sortable_date(candidate.promotion_end_date), _sortable_date(candidate.promotion_start_date), candidate.promotion_key),
        reverse=True,
    )


def _canonical_candidates(candidates: Sequence[PromotionPacketCandidate]) -> list[PromotionPacketCandidate]:
    by_key: dict[str, list[PromotionPacketCandidate]] = {}
    for candidate in candidates:
        by_key.setdefault(candidate.promotion_key, []).append(candidate)
    canonical: list[PromotionPacketCandidate] = []
    for group in by_key.values():
        chosen = sorted(
            group,
            key=lambda candidate: (
                candidate.source_kind == SOURCE_KIND_GOVERNED_REVIEW_ROOT,
                candidate.packet_completeness_score,
                candidate.source_created_at,
                str(candidate.source_review_root or ""),
                str(candidate.source_file_path),
            ),
            reverse=True,
        )[0]
        canonical.append(chosen)
    return sorted(
        canonical,
        key=lambda candidate: (_sortable_date(candidate.promotion_end_date), _sortable_date(candidate.promotion_start_date), candidate.promotion_key),
        reverse=True,
    )


def _lookup_keys_for_candidate(candidate: PromotionPacketCandidate) -> set[str]:
    keys = {candidate.promotion_key, candidate.promotion_slug, candidate.promotion_identifier}
    if candidate.source_review_root is not None:
        keys.add(candidate.source_review_root.name)
    return {value for value in keys if _normalize_text(value)}


def _select_candidates(
    *,
    discovery_mode: str,
    governed_candidates: Sequence[PromotionPacketCandidate],
    source_candidates: Sequence[PromotionPacketCandidate],
    max_promotions: int,
    promotion_keys: Sequence[str] | None,
) -> tuple[list[PromotionPacketCandidate], list[str]]:
    limit = max(0, max_promotions)
    if promotion_keys:
        lookup: dict[str, PromotionPacketCandidate] = {}
        for candidate in [*governed_candidates, *source_candidates]:
            for key in _lookup_keys_for_candidate(candidate):
                existing = lookup.get(key)
                if existing is None:
                    lookup[key] = candidate
                    continue
                if (
                    existing.source_kind != SOURCE_KIND_GOVERNED_REVIEW_ROOT
                    and candidate.source_kind == SOURCE_KIND_GOVERNED_REVIEW_ROOT
                ):
                    lookup[key] = candidate
        selected: list[PromotionPacketCandidate] = []
        missing: list[str] = []
        for key in promotion_keys:
            cleaned = _normalize_text(key)
            if not cleaned:
                continue
            candidate = lookup.get(cleaned)
            if candidate is None:
                missing.append(cleaned)
                continue
            if candidate not in selected:
                selected.append(candidate)
        return selected[:limit], missing
    if discovery_mode == DISCOVERY_MODE_GOVERNED_REVIEW_ROOTS:
        return list(governed_candidates[:limit]), []
    if discovery_mode == DISCOVERY_MODE_SOURCE_ROWS:
        return list(source_candidates[:limit]), []
    selected = list(governed_candidates[:limit])
    selected_keys = {candidate.promotion_key for candidate in selected}
    for candidate in source_candidates:
        if len(selected) >= limit:
            break
        if candidate.promotion_key in selected_keys:
            continue
        selected.append(candidate)
        selected_keys.add(candidate.promotion_key)
    return selected, []


def _extract_governed_record(candidate: PromotionPacketCandidate, packet_output_root: Path) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if candidate.source_review_root is None:
        raise PromotionsLast5DiagnosticPacketRunnerError("Governed candidate missing source review root")
    review_root = candidate.source_review_root
    model_summary_frame = _read_csv(review_root / "model_vs_actual_summary.csv")
    model_summary_row = model_summary_frame.iloc[0].to_dict() if not model_summary_frame.empty else {}
    readiness_frame = _read_csv(review_root / "pretrain_readiness_inspection" / "pretrain_readiness_summary.csv", allow_empty=True)
    unresolved_summary = _read_csv(review_root / "action_layer_unresolved_inspection" / "action_layer_unresolved_inspection_summary.csv", allow_empty=True)
    calibration_summary = _read_csv(review_root / "action_layer_shadow_calibration_candidates" / "action_layer_shadow_calibration_candidate_summary.csv", allow_empty=True)
    simulation_summary = _read_csv(review_root / "action_layer_shadow_vs_baseline_simulation" / "action_layer_shadow_vs_baseline_summary.csv", allow_empty=True)
    leaderboard_summary = _read_csv(review_root / "shadow_review_trigger_leaderboard" / "shadow_review_trigger_leaderboard_summary.csv", allow_empty=True)
    leaderboard_rows = _read_csv(review_root / "shadow_review_trigger_leaderboard" / "shadow_review_trigger_leaderboard_rows.csv", allow_empty=True)
    leaderboard_family = _read_csv(review_root / "shadow_review_trigger_leaderboard" / "shadow_review_trigger_leaderboard_by_rule_family.csv", allow_empty=True)

    forecast_row = _readiness_row(readiness_frame, "forecast_head_reliability")
    action_row = _readiness_row(readiness_frame, "action_layer_calibration_ready")
    production_guardrail_row = _readiness_row(readiness_frame, "production_order_guardrails_unchanged")
    stage12_guardrail_row = _readiness_row(readiness_frame, "stage_12_unchanged")
    readiness_allows_full_train_flag = int(
        readiness_frame.empty or not pd.to_numeric(readiness_frame.get("blocking_flag"), errors="coerce").fillna(0).gt(0).any()
    )
    production_order_changes = _as_int(
        _metric_value(leaderboard_summary, ["PRODUCTION_ORDER_CHANGES"], default=_metric_value(simulation_summary, ["PRODUCTION_ORDER_CHANGES"], default=production_guardrail_row.get("metric_value", 0)))
    )
    stage12_changes = _as_int(
        _metric_value(leaderboard_summary, ["STAGE12_CHANGES"], default=_metric_value(simulation_summary, ["STAGE12_CHANGES"], default=stage12_guardrail_row.get("metric_value", 0)))
    )
    final_recommendation = _normalize_text(
        _metric_value(
            leaderboard_summary,
            ["FINAL_RECOMMENDATION"],
            default=_metric_value(
                simulation_summary,
                ["FINAL_RECOMMENDATION"],
                default=_metric_value(
                    calibration_summary,
                    ["FINAL_RECOMMENDATION"],
                    default=_metric_value(unresolved_summary, ["RECOMMENDATION"], default=REQUIRE_MORE_REPEAT_EVIDENCE),
                ),
            ),
        )
    )
    record = {
        "promotion_key": candidate.promotion_key,
        "promotion_identifier": candidate.promotion_identifier,
        "promotion_name": candidate.promotion_name,
        "promotion_start_date": candidate.promotion_start_date,
        "promotion_end_date": candidate.promotion_end_date,
        "source_kind": candidate.source_kind,
        "source_file_type": candidate.source_file_type,
        "source_review_root": str(review_root),
        "source_file_path": str(candidate.source_file_path),
        "packet_completeness_score": candidate.packet_completeness_score,
        "packet_output_path": str(_packet_output_path(packet_output_root, candidate)),
        "row_count": _as_int(model_summary_row.get("row_count", candidate.row_count)),
        "sku_count": _as_int(model_summary_row.get("matched_sku_count", candidate.sku_count)),
        "actual_units": _as_float(model_summary_row.get("actual_units_total", candidate.actual_units)),
        "expected_demand": _as_float(model_summary_row.get("expected_promo_demand_total", candidate.expected_demand)),
        "forecast_correlation": _as_float(model_summary_row.get("forecast_correlation", 0.0)),
        "forecast_bias_units": _as_float(model_summary_row.get("forecast_bias_units", 0.0)),
        "forecast_reliability_status": _normalize_text(forecast_row.get("status")),
        "forecast_reliability_reason": _normalize_text(forecast_row.get("reason")),
        "readiness_allows_full_train_flag": readiness_allows_full_train_flag,
        "action_layer_unresolved_flags": _as_int(_metric_value(unresolved_summary, ["EXPECTED_UNRESOLVED_RULE_FLAG_ROWS", "ROWS_INSPECTED"], default=0)),
        "action_layer_over_suppression_rows": _as_int(_metric_value(unresolved_summary, ["OVER_SUPPRESSION_CANDIDATE_ROWS"], default=0)),
        "shadow_calibration_candidate_rows": _as_int(_metric_value(calibration_summary, ["OVER_SUPPRESSION_CANDIDATE_ROWS_SELECTED"], default=0)),
        "shadow_vs_baseline_incremental_review_triggers": _as_int(_metric_value(simulation_summary, ["INCREMENTAL_SHADOW_REVIEW_TRIGGERS"], default=0)),
        "shadow_vs_baseline_high_priority_triggers": _as_int(_metric_value(simulation_summary, ["HIGH_PRIORITY_INCREMENTAL_TRIGGERS"], default=0)),
        "tier_1_leaderboard_rows": _as_int(_metric_value(leaderboard_summary, ["TIER_1_COUNT"], default=0)),
        "high_priority_tier_1_rows": _as_int(_metric_value(leaderboard_summary, ["HIGH_PRIORITY_TIER_1_COUNT"], default=0)),
        "gross_profit_represented": _as_float(_metric_value(leaderboard_summary, ["GROSS_PROFIT_REPRESENTED"], default=_metric_value(simulation_summary, ["GROSS_PROFIT_REPRESENTED"], default=0.0))),
        "capital_left_represented": _as_float(_metric_value(leaderboard_summary, ["CAPITAL_LEFT_REPRESENTED"], default=_metric_value(simulation_summary, ["CAPITAL_LEFT_REPRESENTED"], default=0.0))),
        "net_review_value_proxy": _as_float(_metric_value(leaderboard_summary, ["NET_REVIEW_VALUE_PROXY"], default=_metric_value(simulation_summary, ["NET_REVIEW_VALUE_PROXY"], default=0.0))),
        "production_order_changes": production_order_changes,
        "stage_12_changes": stage12_changes,
        "downstream_full_diagnostic_chain_available_flag": 1,
        "downstream_full_packet_reason": DOWNSTREAM_CHAIN_ALREADY_AVAILABLE,
        "missing_canonical_fields": "",
        "final_recommendation": final_recommendation,
        "action_layer_status": _normalize_text(action_row.get("status")),
        "action_layer_reason": _normalize_text(action_row.get("reason")),
    }
    family_frame = leaderboard_family.copy()
    if not family_frame.empty:
        family_frame["promotion_key"] = candidate.promotion_key
        family_frame["promotion_name"] = candidate.promotion_name
    rows_frame = leaderboard_rows.copy()
    if not rows_frame.empty:
        rows_frame["promotion_key"] = candidate.promotion_key
        rows_frame["promotion_name"] = candidate.promotion_name
    return record, readiness_frame, family_frame, rows_frame


def _extract_source_only_record(candidate: PromotionPacketCandidate, packet_output_root: Path) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    record = {
        "promotion_key": candidate.promotion_key,
        "promotion_identifier": candidate.promotion_identifier,
        "promotion_name": candidate.promotion_name,
        "promotion_start_date": candidate.promotion_start_date,
        "promotion_end_date": candidate.promotion_end_date,
        "source_kind": candidate.source_kind,
        "source_file_type": candidate.source_file_type,
        "source_review_root": "",
        "source_file_path": str(candidate.source_file_path),
        "packet_completeness_score": candidate.packet_completeness_score,
        "packet_output_path": str(_packet_output_path(packet_output_root, candidate)),
        "row_count": candidate.row_count,
        "sku_count": candidate.sku_count,
        "actual_units": candidate.actual_units,
        "expected_demand": candidate.expected_demand,
        "forecast_correlation": 0.0,
        "forecast_bias_units": 0.0,
        "forecast_reliability_status": "SOURCE_ROWS_ONLY",
        "forecast_reliability_reason": "Forecast reliability cannot be derived from source-row materialization alone.",
        "readiness_allows_full_train_flag": 0,
        "action_layer_unresolved_flags": 0,
        "action_layer_over_suppression_rows": 0,
        "shadow_calibration_candidate_rows": 0,
        "shadow_vs_baseline_incremental_review_triggers": 0,
        "shadow_vs_baseline_high_priority_triggers": 0,
        "tier_1_leaderboard_rows": 0,
        "high_priority_tier_1_rows": 0,
        "gross_profit_represented": candidate.gross_profit_represented,
        "capital_left_represented": candidate.capital_left_represented,
        "net_review_value_proxy": candidate.gross_profit_represented - candidate.capital_left_represented,
        "production_order_changes": 0,
        "stage_12_changes": 0,
        "downstream_full_diagnostic_chain_available_flag": candidate.downstream_full_diagnostic_chain_available_flag,
        "downstream_full_packet_reason": candidate.downstream_full_packet_reason,
        "missing_canonical_fields": "; ".join(candidate.missing_canonical_fields),
        "final_recommendation": REQUIRE_MORE_REPEAT_EVIDENCE,
        "action_layer_status": "SOURCE_ROWS_ONLY",
        "action_layer_reason": candidate.downstream_full_packet_reason,
    }
    return record, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()


def _repeat_level(promotion_count: int) -> str:
    if promotion_count >= 3:
        return "APPEARS_IN_3_PLUS_PROMOTIONS"
    if promotion_count >= 2:
        return "APPEARS_IN_2_PLUS_PROMOTIONS"
    return "SINGLE_PROMOTION_ONLY"


def _build_rule_family_repeat_evidence_frame(family_frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in family_frames if not frame.empty]
    if not non_empty:
        return pd.DataFrame(columns=RULE_FAMILY_REPEAT_EVIDENCE_COLUMNS)
    combined = pd.concat(non_empty, ignore_index=True)
    grouped = combined.groupby("shadow_rule_family", dropna=False).agg(
        promotion_count=("promotion_key", lambda series: series.astype(str).nunique()),
        total_rows=("row_count", lambda series: pd.to_numeric(series, errors="coerce").fillna(0).sum()),
        total_tier_1_rows=("tier_1_count", lambda series: pd.to_numeric(series, errors="coerce").fillna(0).sum()),
        total_high_priority_tier_1_rows=("high_priority_tier_1_count", lambda series: pd.to_numeric(series, errors="coerce").fillna(0).sum()),
        total_net_review_value_proxy=("net_review_value_proxy", lambda series: pd.to_numeric(series, errors="coerce").fillna(0.0).sum()),
        average_trigger_score=("average_trigger_score", lambda series: pd.to_numeric(series, errors="coerce").fillna(0.0).mean()),
        promotion_keys=("promotion_key", lambda series: "; ".join(sorted({value for value in series.astype(str) if value.strip()}))),
        promotion_names=("promotion_name", lambda series: "; ".join(sorted({value for value in series.astype(str) if value.strip()}))),
    ).reset_index()
    grouped["repeat_evidence_level"] = grouped["promotion_count"].astype(int).map(_repeat_level)
    return grouped.loc[:, RULE_FAMILY_REPEAT_EVIDENCE_COLUMNS].sort_values(
        by=["promotion_count", "total_tier_1_rows", "total_net_review_VALUE_PROXY", "shadow_rule_family"] if "total_net_review_VALUE_PROXY" in grouped.columns else ["promotion_count", "total_tier_1_rows", "total_net_review_value_proxy", "shadow_rule_family"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_repeat_sets(rows_frames: Sequence[pd.DataFrame]) -> tuple[set[str], set[str], set[str]]:
    non_empty = [frame for frame in rows_frames if not frame.empty]
    if not non_empty:
        return set(), set(), set()
    combined = pd.concat(non_empty, ignore_index=True)
    repeated_families = set(
        combined.groupby("shadow_rule_family", dropna=False)["promotion_key"].nunique().loc[lambda series: series >= 2].index.astype(str).tolist()
    )
    repeated_departments = set(
        combined.groupby("department", dropna=False)["promotion_key"].nunique().loc[lambda series: series >= 2].index.astype(str).tolist()
    )
    repeated_skus = set(
        combined.groupby("sku_number", dropna=False)["promotion_key"].nunique().loc[lambda series: series >= 2].index.astype(str).tolist()
    )
    return repeated_families, repeated_departments, repeated_skus


def _forecast_trend_label(frame: pd.DataFrame) -> str:
    if frame.empty or len(frame.index) < 2:
        if not frame.empty and pd.to_numeric(frame["forecast_correlation"], errors="coerce").fillna(0.0).lt(0.5).any():
            return "INSUFFICIENT_TREND_EVIDENCE_STILL_WEAK"
        return "INSUFFICIENT_TREND_EVIDENCE"
    ordered = frame.sort_values("promotion_end_date")
    first_corr = _as_float(ordered.iloc[0]["forecast_correlation"])
    last_corr = _as_float(ordered.iloc[-1]["forecast_correlation"])
    first_bias = abs(_as_float(ordered.iloc[0]["forecast_bias_units"]))
    last_bias = abs(_as_float(ordered.iloc[-1]["forecast_bias_units"]))
    if last_corr >= 0.5 and last_corr >= first_corr and last_bias <= first_bias:
        return "IMPROVING_TOWARD_RELIABLE"
    if last_corr > first_corr and last_bias <= first_bias:
        return "IMPROVING_BUT_STILL_BELOW_FLOOR"
    return "STILL_WEAK"


def _action_layer_trend_label(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "NO_ACTION_LAYER_EVIDENCE"
    positive = pd.to_numeric(frame["action_layer_over_suppression_rows"], errors="coerce").fillna(0).gt(0)
    if len(frame.index) >= 2 and positive.all():
        return "CONSISTENT_OVER_CONSERVATIVE_SIGNAL"
    if positive.sum() >= 2:
        return "REPEATED_OVER_CONSERVATIVE_SIGNAL"
    if positive.any():
        return "SINGLE_PROMOTION_OVER_CONSERVATIVE_SIGNAL"
    return "NO_OVER_CONSERVATIVE_SIGNAL"


def _portfolio_final_recommendation(processed_index_frame: pd.DataFrame, rule_family_frame: pd.DataFrame) -> str:
    if processed_index_frame.empty:
        return NO_COMPLETED_PROMOTION_PACKETS_AVAILABLE
    production_changes = pd.to_numeric(processed_index_frame["production_order_changes"], errors="coerce").fillna(0)
    stage12_changes = pd.to_numeric(processed_index_frame["stage_12_changes"], errors="coerce").fillna(0)
    if production_changes.gt(0).any() or stage12_changes.gt(0).any():
        return HARD_FAIL_GUARDRAIL_BREACH
    governed_packet_count = int(processed_index_frame["processing_status"].astype(str).eq(PACKET_WRITTEN).sum())
    repeated_rule_families = int(rule_family_frame["promotion_count"].ge(2).sum()) if not rule_family_frame.empty else 0
    tier1_positive_promotions = int(pd.to_numeric(processed_index_frame["tier_1_leaderboard_rows"], errors="coerce").fillna(0).gt(0).sum())
    if governed_packet_count >= 2 and (repeated_rule_families > 0 or tier1_positive_promotions >= 2):
        return KEEP_SHADOW_ONLY_TEST_FIRST_ACROSS_MORE_PROMOTIONS
    return REQUIRE_MORE_REPEAT_EVIDENCE


def _build_summary_frame(
    *,
    discovery_mode: str,
    discovered_unique_promotions: int,
    scanned_root_count: int,
    ignored_output_roots: int,
    selected_count: int,
    missing_requested_keys: Sequence[str],
    processed_index_frame: pd.DataFrame,
    forecast_frame: pd.DataFrame,
    action_frame: pd.DataFrame,
    rule_family_frame: pd.DataFrame,
    repeated_departments: set[str],
    repeated_skus: set[str],
    source_file_inspections: Sequence[SourceFileInspection],
    selected_source_file: SourceFileInspection | None,
) -> pd.DataFrame:
    average_gp = float(pd.to_numeric(processed_index_frame.get("gross_profit_represented"), errors="coerce").fillna(0.0).mean() if not processed_index_frame.empty else 0.0)
    average_capital = float(pd.to_numeric(processed_index_frame.get("capital_left_represented"), errors="coerce").fillna(0.0).mean() if not processed_index_frame.empty else 0.0)
    average_net = float(pd.to_numeric(processed_index_frame.get("net_review_value_proxy"), errors="coerce").fillna(0.0).mean() if not processed_index_frame.empty else 0.0)
    repeated_rule_families_2plus = int(rule_family_frame["promotion_count"].ge(2).sum()) if not rule_family_frame.empty else 0
    repeated_rule_families_3plus = int(rule_family_frame["promotion_count"].ge(3).sum()) if not rule_family_frame.empty else 0
    production_changes_total = int(pd.to_numeric(processed_index_frame.get("production_order_changes"), errors="coerce").fillna(0).sum() if not processed_index_frame.empty else 0)
    stage12_changes_total = int(pd.to_numeric(processed_index_frame.get("stage_12_changes"), errors="coerce").fillna(0).sum() if not processed_index_frame.empty else 0)
    final_recommendation = _portfolio_final_recommendation(processed_index_frame, rule_family_frame)
    governed_packet_count = int(processed_index_frame["processing_status"].astype(str).eq(PACKET_WRITTEN).sum()) if not processed_index_frame.empty else 0
    source_only_count = int(processed_index_frame["processing_status"].astype(str).eq(MATERIALIZED_SOURCE_ONLY).sum()) if not processed_index_frame.empty else 0
    rows = [
        _summary_row("DISCOVERY_MODE_USED", discovery_mode, "Discovery mode used for this run."),
        _summary_row("SOURCE_FILES_INSPECTED", len(source_file_inspections), "Source-row CSV files inspected for materialization."),
        _summary_row("SELECTED_SOURCE_FILE", str(selected_source_file.path) if selected_source_file is not None else "", "Selected source-row file when applicable."),
        _summary_row("PROMOTIONS_FOUND", discovered_unique_promotions, "Unique promotions discovered across governed review roots and source-row discovery."),
        _summary_row("SOURCE_REVIEW_ROOTS_SCANNED", scanned_root_count, "Review-root manifests scanned under the source root."),
        _summary_row("OUTPUT_ROOTS_IGNORED_DURING_DISCOVERY", ignored_output_roots, "Candidate manifests ignored because they were already inside the output root."),
        _summary_row("PROMOTIONS_SELECTED", selected_count, "Promotions selected after limits and optional explicit key filtering."),
        _summary_row("PROMOTIONS_PROCESSED", len(processed_index_frame.index), "Promotions for which a packet or materialized source folder was produced."),
        _summary_row("FULL_GOVERNED_PACKETS_WRITTEN", governed_packet_count, "Promotions with an already-available governed packet chain."),
        _summary_row("MATERIALIZED_SOURCE_ONLY_PROMOTIONS", source_only_count, "Promotions materialized from source rows without the governed chain."),
        _summary_row("MISSING_REQUESTED_PROMOTIONS", len(missing_requested_keys), "Explicit promotion keys requested but not resolved."),
        _summary_row("REPEATED_RULE_FAMILIES_2_PLUS", repeated_rule_families_2plus, "Rule families repeating across two or more governed packets."),
        _summary_row("REPEATED_RULE_FAMILIES_3_PLUS", repeated_rule_families_3plus, "Rule families repeating across three or more governed packets."),
        _summary_row("RECURRING_DEPARTMENTS_2_PLUS", len(repeated_departments), "Departments recurring across two or more shadow-trigger leaderboards."),
        _summary_row("RECURRING_SKUS_2_PLUS", len(repeated_skus), "SKUs recurring across two or more shadow-trigger leaderboards."),
        _summary_row("AVERAGE_GROSS_PROFIT_REPRESENTED", round(average_gp, 2), "Average gross profit represented by processed promotions."),
        _summary_row("AVERAGE_CAPITAL_LEFT_REPRESENTED", round(average_capital, 2), "Average capital-left exposure represented by processed promotions."),
        _summary_row("AVERAGE_NET_REVIEW_VALUE_PROXY", round(average_net, 2), "Average net review value proxy across processed promotions."),
        _summary_row("FORECAST_RELIABILITY_TREND", _forecast_trend_label(forecast_frame), "Portfolio-level trend assessment of forecast reliability."),
        _summary_row("ACTION_LAYER_OVER_SUPPRESSION_TREND", _action_layer_trend_label(action_frame), "Portfolio-level assessment of action-layer over-conservatism."),
        _summary_row("PRODUCTION_ORDER_CHANGES_TOTAL", production_changes_total, "Any value above 0 is a hard governance failure."),
        _summary_row("STAGE_12_CHANGES_TOTAL", stage12_changes_total, "Any value above 0 is a hard governance failure."),
        _summary_row("FINAL_RECOMMENDATION", final_recommendation, "Portfolio-level governed recommendation."),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_repeatability_frame(
    processed_index_frame: pd.DataFrame,
    rows_frames: Sequence[pd.DataFrame],
    repeated_families: set[str],
    repeated_departments: set[str],
    repeated_skus: set[str],
) -> pd.DataFrame:
    if processed_index_frame.empty:
        return pd.DataFrame(columns=SHADOW_TRIGGER_REPEATABILITY_COLUMNS)
    per_promotion_counts: dict[str, dict[str, int]] = {}
    for frame in rows_frames:
        if frame.empty:
            continue
        promotion_key = _normalize_text(frame.iloc[0].get("promotion_key"))
        if not promotion_key:
            continue
        per_promotion_counts[promotion_key] = {
            "repeated_rule_families_in_portfolio": len({value for value in frame.get("shadow_rule_family", pd.Series(dtype="object")).astype(str) if value in repeated_families}),
            "repeated_departments_in_portfolio": len({value for value in frame.get("department", pd.Series(dtype="object")).astype(str) if value in repeated_departments}),
            "repeated_skus_in_portfolio": len({value for value in frame.get("sku_number", pd.Series(dtype="object")).astype(str) if value in repeated_skus}),
        }
    records: list[dict[str, object]] = []
    for row in processed_index_frame.to_dict(orient="records"):
        counts = per_promotion_counts.get(_normalize_text(row.get("promotion_key")), {})
        repeated_family_count = int(counts.get("repeated_rule_families_in_portfolio", 0))
        tier1_rows = _as_int(row.get("tier_1_leaderboard_rows"))
        records.append(
            {
                "promotion_key": row.get("promotion_key", ""),
                "promotion_name": row.get("promotion_name", ""),
                "promotion_end_date": row.get("promotion_end_date", ""),
                "shadow_vs_baseline_incremental_review_triggers": _as_int(row.get("shadow_vs_baseline_incremental_review_triggers")),
                "tier_1_leaderboard_rows": tier1_rows,
                "high_priority_tier_1_rows": _as_int(row.get("high_priority_tier_1_rows")),
                "gross_profit_represented": _as_float(row.get("gross_profit_represented")),
                "capital_left_represented": _as_float(row.get("capital_left_represented")),
                "net_review_value_proxy": _as_float(row.get("net_review_value_proxy")),
                "repeated_rule_families_in_portfolio": repeated_family_count,
                "repeated_departments_in_portfolio": int(counts.get("repeated_departments_in_portfolio", 0)),
                "repeated_skus_in_portfolio": int(counts.get("repeated_skus_in_portfolio", 0)),
                "tier_1_repeatability_status": "REPEATED_TIER1_SIGNAL" if tier1_rows > 0 and repeated_family_count > 0 else "SINGLE_PROMOTION_ONLY",
            }
        )
    return pd.DataFrame(records, columns=SHADOW_TRIGGER_REPEATABILITY_COLUMNS)


def _build_portfolio_memo(
    *,
    summary_frame: pd.DataFrame,
    rule_family_frame: pd.DataFrame,
    missing_requested_keys: Sequence[str],
) -> str:
    lookup = dict(zip(summary_frame["metric_name"].astype(str), summary_frame["metric_value"]))
    discovered_promotions = _as_int(lookup.get("PROMOTIONS_FOUND", 0))
    processed_promotions = _as_int(lookup.get("PROMOTIONS_PROCESSED", 0))
    source_only_count = _as_int(lookup.get("MATERIALIZED_SOURCE_ONLY_PROMOTIONS", 0))
    final_recommendation = _normalize_text(lookup.get("FINAL_RECOMMENDATION"))
    repeated_family_lines = [
        f"- {getattr(row, 'shadow_rule_family')}: {getattr(row, 'promotion_count')} promotion(s), tier_1_rows={int(_as_float(getattr(row, 'total_tier_1_rows')))}, net_proxy={_format_money(_as_float(getattr(row, 'total_net_review_value_proxy')))}"
        for row in rule_family_frame.head(5).itertuples(index=False)
        if _as_int(getattr(row, "promotion_count")) >= 2
    ] or ["- No shadow rule families repeat across two or more completed governed promotions yet."]
    missing_line = (
        f"Missing explicit promotion keys: {', '.join(missing_requested_keys)}."
        if missing_requested_keys
        else "No explicit promotion-key misses were recorded in this run."
    )
    source_only_sentence = (
        f"{source_only_count} promotion(s) were only materialized from source rows, so their full governed downstream diagnostic chain could not run yet."
        if source_only_count > 0
        else "All processed promotions already had full governed review-root packets available."
    )
    return "\n".join(
        [
            "# Last 5 Completed Promotions Diagnostic Portfolio",
            "",
            "This is not an order file.",
            "No training was started.",
            "This is a repeat-evidence diagnostic packet.",
            "Shadow rules remain shadow-only.",
            "Auto-ordering remains blocked.",
            "",
            "## 1. Portfolio status",
            f"Completed promotions found = {discovered_promotions}; processed into packets = {processed_promotions}.",
            missing_line,
            source_only_sentence,
            f"Recommendation = {final_recommendation or REQUIRE_MORE_REPEAT_EVIDENCE}.",
            "",
            "## 2. Repeat evidence",
            *repeated_family_lines,
            "",
            "## 3. Governance reminder",
            "This portfolio packet is diagnostics-only. It does not promote shadow rules to production, does not change production ordering logic, does not change Stage 12, and does not relax the demand proxy.",
        ]
    ).strip()


def _build_final_promotion_learning_memo(record: dict[str, object]) -> str:
    return "\n".join(
        [
            f"# Promotion Packet: {_normalize_text(record.get('promotion_name'))}",
            "",
            "This is not an order file.",
            "No training was started.",
            "This is a repeat-evidence diagnostic packet.",
            "Shadow rules remain shadow-only.",
            "Auto-ordering remains blocked.",
            "",
            f"Promotion identifier = {_normalize_text(record.get('promotion_identifier'))}.",
            f"Promotion window = {_normalize_text(record.get('promotion_start_date'))} to {_normalize_text(record.get('promotion_end_date'))}.",
            f"Rows = {_format_int(_as_int(record.get('row_count')))}; SKUs = {_format_int(_as_int(record.get('sku_count')))}.",
            f"Forecast correlation = {_as_float(record.get('forecast_correlation')):.3f}; forecast bias = {_format_int(_as_int(record.get('forecast_bias_units')))} units.",
            f"Action-layer unresolved flags = {_format_int(_as_int(record.get('action_layer_unresolved_flags')))}; shadow-vs-baseline incremental review triggers = {_format_int(_as_int(record.get('shadow_vs_baseline_incremental_review_triggers')))}.",
            f"Tier 1 leaderboard rows = {_format_int(_as_int(record.get('tier_1_leaderboard_rows')))}; high-priority Tier 1 rows = {_format_int(_as_int(record.get('high_priority_tier_1_rows')))}.",
            f"Gross profit represented = {_format_money(_as_float(record.get('gross_profit_represented')))}; capital left represented = {_format_money(_as_float(record.get('capital_left_represented')))}.",
            f"Production order changes = {_format_int(_as_int(record.get('production_order_changes')))}; Stage 12 changes = {_format_int(_as_int(record.get('stage_12_changes')))}.",
            f"Recommendation = {_normalize_text(record.get('final_recommendation')) or REQUIRE_MORE_REPEAT_EVIDENCE}.",
            "Before any production consideration, this promotion still requires repeat evidence across more completed promotions, shadow-only validation, and readiness that explicitly allows training.",
        ]
    ).strip()


def build_promotions_last5_diagnostic_packet_runner(
    *,
    source_root: str | Path,
    output_root: str | Path | None = None,
    max_promotions: int = 5,
    promotion_keys: Sequence[str] | None = None,
    discovery_mode: str = DISCOVERY_MODE_AUTO,
    source_file: str | Path | None = None,
    promotion_key_columns: Sequence[str] | None = None,
    date_column: str | None = None,
    store_column: str | None = None,
    sku_column: str | None = None,
) -> PromotionsLast5DiagnosticPacketRunnerResult:
    source_root_path = Path(source_root)
    output_root_path = Path(output_root) if output_root is not None else Path("tmp") / OUTPUT_FOLDER_NAME
    governed_candidates, governed_stats = _discover_governed_review_candidates(source_root_path, output_root_path)
    canonical_governed = _canonical_candidates(governed_candidates)

    source_file_inspections: list[SourceFileInspection] = []
    selected_source_file: SourceFileInspection | None = None
    canonical_source_candidates: list[PromotionPacketCandidate] = []
    if discovery_mode in {DISCOVERY_MODE_AUTO, DISCOVERY_MODE_SOURCE_ROWS} or source_file is not None:
        source_file_inspections, selected_source_file = _choose_source_file_inspection(
            source_root=source_root_path,
            output_root=output_root_path,
            source_file=source_file,
            promotion_key_columns=promotion_key_columns,
            date_column=date_column,
            store_column=store_column,
            sku_column=sku_column,
        )
        if selected_source_file is not None:
            canonical_source_candidates = _canonical_candidates(_discover_source_row_candidates(selected_source_file))

    selected_candidates, missing_requested_keys = _select_candidates(
        discovery_mode=discovery_mode,
        governed_candidates=canonical_governed,
        source_candidates=canonical_source_candidates,
        max_promotions=max_promotions,
        promotion_keys=promotion_keys,
    )

    processed_records: list[dict[str, object]] = []
    family_frames: list[pd.DataFrame] = []
    rows_frames: list[pd.DataFrame] = []
    for selection_rank, candidate in enumerate(selected_candidates, start=1):
        if candidate.source_kind == SOURCE_KIND_GOVERNED_REVIEW_ROOT:
            record, _, family_frame, rows_frame = _extract_governed_record(candidate, output_root_path)
            record.update(
                {
                    "selection_rank": selection_rank,
                    "discovery_status": AUTO_DISCOVERED,
                    "processing_status": PACKET_WRITTEN,
                    "materialization_status": MATERIALIZATION_STATUS_GOVERNED_PACKET_COPIED,
                }
            )
        else:
            record, _, family_frame, rows_frame = _extract_source_only_record(candidate, output_root_path)
            record.update(
                {
                    "selection_rank": selection_rank,
                    "discovery_status": SOURCE_ROW_DISCOVERED,
                    "processing_status": MATERIALIZED_SOURCE_ONLY,
                    "materialization_status": MATERIALIZATION_STATUS_SOURCE_ROWS_WRITTEN,
                }
            )
        processed_records.append(record)
        family_frames.append(family_frame)
        rows_frames.append(rows_frame)

    for missing_key in missing_requested_keys:
        processed_records.append(
            {
                "selection_rank": len(processed_records) + 1,
                "promotion_key": missing_key,
                "promotion_identifier": "",
                "promotion_name": "",
                "promotion_start_date": "",
                "promotion_end_date": "",
                "source_kind": "",
                "source_file_type": "",
                "source_review_root": "",
                "source_file_path": "",
                "packet_completeness_score": 0,
                "discovery_status": REQUESTED_PROMOTION_NOT_FOUND,
                "processing_status": NOT_PROCESSED,
                "materialization_status": "",
                "packet_output_path": str(output_root_path / f"promotion_{_slugify(missing_key)}"),
                "row_count": 0,
                "sku_count": 0,
                "actual_units": 0.0,
                "expected_demand": 0.0,
                "forecast_correlation": 0.0,
                "forecast_bias_units": 0.0,
                "forecast_reliability_status": "",
                "action_layer_unresolved_flags": 0,
                "action_layer_over_suppression_rows": 0,
                "shadow_calibration_candidate_rows": 0,
                "shadow_vs_baseline_incremental_review_triggers": 0,
                "shadow_vs_baseline_high_PRIORITY_TRIGGERS": 0,
                "tier_1_leaderboard_rows": 0,
                "high_priority_tier_1_rows": 0,
                "gross_profit_represented": 0.0,
                "capital_left_represented": 0.0,
                "net_review_value_proxy": 0.0,
                "production_order_changes": 0,
                "stage_12_changes": 0,
                "downstream_full_diagnostic_chain_available_flag": 0,
                "downstream_full_packet_reason": "",
                "missing_canonical_fields": "",
                "final_recommendation": REQUIRE_MORE_REPEAT_EVIDENCE,
                "forecast_reliability_reason": "",
                "readiness_allows_full_train_flag": 0,
                "action_layer_status": "",
                "action_layer_reason": "",
            }
        )

    packet_index_frame = pd.DataFrame(processed_records)
    extended_columns = [
        *PACKET_INDEX_COLUMNS,
        "forecast_reliability_reason",
        "readiness_allows_full_train_flag",
        "action_layer_status",
        "action_layer_reason",
    ]
    if packet_index_frame.empty:
        packet_index_frame = pd.DataFrame(columns=extended_columns)
    else:
        for column_name in extended_columns:
            if column_name not in packet_index_frame.columns:
                packet_index_frame[column_name] = ""
            if column_name == "shadow_vs_baseline_high_priority_triggers" and "shadow_vs_baseline_high_PRIORITY_TRIGGERS" in packet_index_frame.columns:
                packet_index_frame[column_name] = packet_index_frame["shadow_vs_baseline_high_PRIORITY_TRIGGERS"]
        packet_index_frame = packet_index_frame.loc[:, extended_columns]

    processed_index_frame = packet_index_frame.loc[
        packet_index_frame["processing_status"].astype(str).isin([PACKET_WRITTEN, MATERIALIZED_SOURCE_ONLY])
    ].copy()
    rule_family_frame = _build_rule_family_repeat_evidence_frame(family_frames)
    repeated_families, repeated_departments, repeated_skus = _build_repeat_sets(rows_frames)
    forecast_frame = processed_index_frame.loc[:, FORECAST_RELIABILITY_COLUMNS].copy() if not processed_index_frame.empty else pd.DataFrame(columns=FORECAST_RELIABILITY_COLUMNS)
    action_frame = processed_index_frame.loc[:, ACTION_LAYER_CALIBRATION_COLUMNS].copy() if not processed_index_frame.empty else pd.DataFrame(columns=ACTION_LAYER_CALIBRATION_COLUMNS)
    repeatability_frame = _build_repeatability_frame(processed_index_frame, rows_frames, repeated_families, repeated_departments, repeated_skus)

    all_discovered = _canonical_candidates([*canonical_governed, *canonical_source_candidates])
    summary_frame = _build_summary_frame(
        discovery_mode=discovery_mode,
        discovered_unique_promotions=len(all_discovered),
        scanned_root_count=governed_stats["scanned_roots"],
        ignored_output_roots=governed_stats["ignored_output_roots"],
        selected_count=len(selected_candidates),
        missing_requested_keys=missing_requested_keys,
        processed_index_frame=processed_index_frame,
        forecast_frame=forecast_frame,
        action_frame=action_frame,
        rule_family_frame=rule_family_frame,
        repeated_departments=repeated_departments,
        repeated_skus=repeated_skus,
        source_file_inspections=source_file_inspections,
        selected_source_file=selected_source_file,
    )
    portfolio_memo = _build_portfolio_memo(
        summary_frame=summary_frame,
        rule_family_frame=rule_family_frame,
        missing_requested_keys=missing_requested_keys,
    )

    return PromotionsLast5DiagnosticPacketRunnerResult(
        packet_index_frame=packet_index_frame.drop(columns=["forecast_reliability_reason", "readiness_allows_full_train_flag", "action_layer_status", "action_layer_reason", "shadow_vs_baseline_high_PRIORITY_TRIGGERS"], errors="ignore"),
        summary_frame=summary_frame,
        forecast_reliability_frame=forecast_frame,
        action_layer_calibration_frame=action_frame,
        shadow_trigger_repeatability_frame=repeatability_frame,
        rule_family_repeat_evidence_frame=rule_family_frame,
        portfolio_memo_markdown=portfolio_memo,
    )


def _copy_governed_promotion_packet(candidate: PromotionPacketCandidate, packet_output_path: Path) -> None:
    if candidate.source_review_root is None:
        raise PromotionsLast5DiagnosticPacketRunnerError("Governed candidate missing source review root.")
    model_destination = packet_output_path / MODEL_VS_ACTUAL_PACKET_FOLDER
    model_destination.mkdir(parents=True, exist_ok=True)
    for child in candidate.source_review_root.iterdir():
        if child.name in PACKET_STAGE_DIRECTORIES:
            continue
        _copy_path(child, model_destination / child.name)
    for directory_name in PACKET_STAGE_DIRECTORIES:
        source_directory = candidate.source_review_root / directory_name
        if source_directory.exists():
            _copy_path(source_directory, packet_output_path / directory_name)


def _filter_source_rows_for_promotion(
    *,
    source_file_path: Path,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
    store_number: str,
    promotion_key_columns: Sequence[str] | None,
    date_column: str | None,
    store_column: str | None,
    sku_column: str | None,
) -> pd.DataFrame:
    columns = pd.read_csv(source_file_path, nrows=0, low_memory=False).columns.tolist()
    mapping = _infer_source_mapping(
        columns,
        promotion_key_columns=promotion_key_columns,
        date_column=date_column,
        store_column=store_column,
        sku_column=sku_column,
    )
    frame = _read_csv(source_file_path)
    work = frame.copy()
    work["__store"] = _id_series(work, mapping.store_column)
    work["__promotion_name"] = _text_series(work, mapping.promotion_name_column)
    work["__start_date"] = _date_series(work, mapping.promotion_start_date_column)
    work["__end_date"] = _date_series(work, mapping.promotion_end_date_column or mapping.sort_date_column)
    mask = (
        work["__store"].astype(str).eq(store_number)
        & work["__promotion_name"].astype(str).eq(promotion_name)
        & work["__start_date"].astype(str).eq(promotion_start_date)
        & work["__end_date"].astype(str).eq(promotion_end_date)
    )
    filtered = frame.loc[mask].copy()
    if filtered.empty:
        alt_mask = (
            work["__promotion_name"].astype(str).eq(promotion_name)
            & work["__start_date"].astype(str).eq(promotion_start_date)
            & work["__end_date"].astype(str).eq(promotion_end_date)
        )
        filtered = frame.loc[alt_mask].copy()
    if filtered.empty:
        raise PromotionsLast5DiagnosticPacketRunnerError(
            f"Could not re-materialize promotion rows for {store_number}|{promotion_start_date}|{promotion_end_date}|{promotion_name} from source file {source_file_path}"
        )
    return filtered


def _write_source_materialized_promotion(
    *,
    row: dict[str, object],
    promotion_key_columns: Sequence[str] | None,
    date_column: str | None,
    store_column: str | None,
    sku_column: str | None,
) -> None:
    packet_output_path = Path(_normalize_text(row.get("packet_output_path")))
    source_file_path = Path(_normalize_text(row.get("source_file_path")))
    store_number = _normalize_text(row.get("promotion_key", "").split("|", 1)[0] if _normalize_text(row.get("promotion_key")) else "")
    source_rows = _filter_source_rows_for_promotion(
        source_file_path=source_file_path,
        promotion_name=_normalize_text(row.get("promotion_name")),
        promotion_start_date=_normalize_text(row.get("promotion_start_date")),
        promotion_end_date=_normalize_text(row.get("promotion_end_date")),
        store_number=store_number,
        promotion_key_columns=promotion_key_columns,
        date_column=date_column,
        store_column=store_column,
        sku_column=sku_column,
    )
    packet_output_path.mkdir(parents=True, exist_ok=True)
    source_rows.to_csv(packet_output_path / "promotion_source_rows.csv", index=False)
    pd.DataFrame(
        [{
            "promotion_key": row.get("promotion_key", ""),
            "promotion_name": row.get("promotion_name", ""),
            "promotion_start_date": row.get("promotion_start_date", ""),
            "promotion_end_date": row.get("promotion_end_date", ""),
            "row_count": _as_int(row.get("row_count")),
            "sku_count": _as_int(row.get("sku_count")),
            "actual_units_proxy_total": _as_float(row.get("actual_units")),
            "expected_demand_proxy_total": _as_float(row.get("expected_demand")),
            "gross_profit_proxy_total": _as_float(row.get("gross_profit_represented")),
            "capital_left_proxy_total": _as_float(row.get("capital_left_represented")),
            "packet_completeness_score": _as_int(row.get("packet_completeness_score")),
        }],
        columns=SOURCE_SUMMARY_COLUMNS,
    ).to_csv(packet_output_path / "promotion_source_summary.csv", index=False)
    pd.DataFrame(
        [{
            "source_file_path": str(source_file_path),
            "source_file_type": row.get("source_file_type", ""),
            "row_count": _as_int(row.get("row_count")),
            "sku_count": _as_int(row.get("sku_count")),
            "store_number": store_number,
            "promotion_name": row.get("promotion_name", ""),
            "promotion_start_date": row.get("promotion_start_date", ""),
            "promotion_end_date": row.get("promotion_end_date", ""),
            "source_discovery_status": row.get("discovery_status", ""),
            "materialization_status": MATERIALIZATION_STATUS_SOURCE_ROWS_WRITTEN,
            "downstream_full_diagnostic_chain_available_flag": _as_int(row.get("downstream_full_diagnostic_chain_available_flag")),
            "downstream_full_packet_reason": row.get("downstream_full_packet_reason", ""),
            "missing_canonical_fields": row.get("missing_canonical_fields", ""),
        }],
        columns=SOURCE_MANIFEST_COLUMNS,
    ).to_csv(packet_output_path / "promotion_source_manifest.csv", index=False)


def write_promotions_last5_diagnostic_packet_runner(
    *,
    source_root: str | Path,
    output_root: str | Path | None = None,
    max_promotions: int = 5,
    promotion_keys: Sequence[str] | None = None,
    dry_run: bool = False,
    discovery_mode: str = DISCOVERY_MODE_AUTO,
    source_file: str | Path | None = None,
    promotion_key_columns: Sequence[str] | None = None,
    date_column: str | None = None,
    store_column: str | None = None,
    sku_column: str | None = None,
) -> PromotionsLast5DiagnosticPacketRunnerArtifacts:
    output_root_path = Path(output_root) if output_root is not None else Path("tmp") / OUTPUT_FOLDER_NAME
    result = build_promotions_last5_diagnostic_packet_runner(
        source_root=source_root,
        output_root=output_root_path,
        max_promotions=max_promotions,
        promotion_keys=promotion_keys,
        discovery_mode=discovery_mode,
        source_file=source_file,
        promotion_key_columns=promotion_key_columns,
        date_column=date_column,
        store_column=store_column,
        sku_column=sku_column,
    )
    if dry_run:
        return PromotionsLast5DiagnosticPacketRunnerArtifacts(
            output_root=str(output_root_path),
            packet_index_csv_path="",
            summary_csv_path="",
            forecast_reliability_csv_path="",
            action_layer_calibration_csv_path="",
            shadow_trigger_repeatability_csv_path="",
            rule_family_repeat_evidence_csv_path="",
            portfolio_memo_md_path="",
        )

    output_root_path.mkdir(parents=True, exist_ok=True)
    for row in result.packet_index_frame.to_dict(orient="records"):
        status = _normalize_text(row.get("processing_status"))
        if status == PACKET_WRITTEN:
            source_root_path = Path(_normalize_text(row.get("source_review_root")))
            candidate = PromotionPacketCandidate(
                promotion_key=_normalize_text(row.get("promotion_key")),
                promotion_slug=_slugify(Path(_normalize_text(row.get("packet_output_path"))).name.removeprefix("promotion_")),
                promotion_identifier=_normalize_text(row.get("promotion_identifier")),
                promotion_name=_normalize_text(row.get("promotion_name")),
                promotion_start_date=_normalize_text(row.get("promotion_start_date")),
                promotion_end_date=_normalize_text(row.get("promotion_end_date")),
                store_number=_normalize_text(row.get("promotion_key", "").split("|", 1)[0] if _normalize_text(row.get("promotion_key")) else ""),
                row_count=_as_int(row.get("row_count")),
                sku_count=_as_int(row.get("sku_count")),
                actual_units=_as_float(row.get("actual_units")),
                expected_demand=_as_float(row.get("expected_demand")),
                gross_profit_represented=_as_float(row.get("gross_profit_represented")),
                capital_left_represented=_as_float(row.get("capital_left_represented")),
                source_kind=SOURCE_KIND_GOVERNED_REVIEW_ROOT,
                source_file_type=_normalize_text(row.get("source_file_type")),
                source_review_root=source_root_path,
                source_file_path=Path(_normalize_text(row.get("source_file_path"))),
                packet_completeness_score=_as_int(row.get("packet_completeness_score")),
                source_created_at="",
                downstream_full_diagnostic_chain_available_flag=1,
                downstream_full_packet_reason=DOWNSTREAM_CHAIN_ALREADY_AVAILABLE,
                missing_canonical_fields=(),
            )
            packet_output_path = Path(_normalize_text(row.get("packet_output_path")))
            _copy_governed_promotion_packet(candidate, packet_output_path)
            (packet_output_path / "final_promotion_learning_memo.md").write_text(
                _build_final_promotion_learning_memo(row),
                encoding="utf-8",
            )
        elif status == MATERIALIZED_SOURCE_ONLY:
            _write_source_materialized_promotion(
                row=row,
                promotion_key_columns=promotion_key_columns,
                date_column=date_column,
                store_column=store_column,
                sku_column=sku_column,
            )

    packet_index_csv_path = output_root_path / "last5_promotions_packet_index.csv"
    summary_csv_path = output_root_path / "last5_promotions_summary.csv"
    forecast_csv_path = output_root_path / "last5_forecast_reliability_by_promotion.csv"
    action_csv_path = output_root_path / "last5_action_layer_calibration_by_promotion.csv"
    shadow_csv_path = output_root_path / "last5_shadow_trigger_repeatability.csv"
    rule_family_csv_path = output_root_path / "last5_rule_family_repeat_evidence.csv"
    portfolio_memo_md_path = output_root_path / "last5_promotion_portfolio_memo.md"

    result.packet_index_frame.to_csv(packet_index_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.forecast_reliability_frame.to_csv(forecast_csv_path, index=False)
    result.action_layer_calibration_frame.to_csv(action_csv_path, index=False)
    result.shadow_trigger_repeatability_frame.to_csv(shadow_csv_path, index=False)
    result.rule_family_repeat_evidence_frame.to_csv(rule_family_csv_path, index=False)
    portfolio_memo_md_path.write_text(result.portfolio_memo_markdown, encoding="utf-8")

    return PromotionsLast5DiagnosticPacketRunnerArtifacts(
        output_root=str(output_root_path),
        packet_index_csv_path=str(packet_index_csv_path),
        summary_csv_path=str(summary_csv_path),
        forecast_reliability_csv_path=str(forecast_csv_path),
        action_layer_calibration_csv_path=str(action_csv_path),
        shadow_trigger_repeatability_csv_path=str(shadow_csv_path),
        rule_family_repeat_evidence_csv_path=str(rule_family_csv_path),
        portfolio_memo_md_path=str(portfolio_memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build governed diagnostic packets for the last completed promotions without starting training or changing production ordering logic."
    )
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", default=str(Path("tmp") / OUTPUT_FOLDER_NAME))
    parser.add_argument("--max-promotions", type=int, default=5)
    parser.add_argument("--promotion-keys")
    parser.add_argument(
        "--discovery-mode",
        choices=(DISCOVERY_MODE_AUTO, DISCOVERY_MODE_GOVERNED_REVIEW_ROOTS, DISCOVERY_MODE_SOURCE_ROWS),
        default=DISCOVERY_MODE_AUTO,
    )
    parser.add_argument("--source-file")
    parser.add_argument("--promotion-key-columns")
    parser.add_argument("--date-column")
    parser.add_argument("--store-column")
    parser.add_argument("--sku-column")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    promotion_keys = [value.strip() for value in _normalize_text(args.promotion_keys).split(",") if value.strip()] or None
    promotion_key_columns = [value.strip() for value in _normalize_text(args.promotion_key_columns).split(",") if value.strip()] or None
    result = build_promotions_last5_diagnostic_packet_runner(
        source_root=args.source_root,
        output_root=args.output_root,
        max_promotions=args.max_promotions,
        promotion_keys=promotion_keys,
        discovery_mode=args.discovery_mode,
        source_file=args.source_file,
        promotion_key_columns=promotion_key_columns,
        date_column=args.date_column,
        store_column=args.store_column,
        sku_column=args.sku_column,
    )
    artifacts = write_promotions_last5_diagnostic_packet_runner(
        source_root=args.source_root,
        output_root=args.output_root,
        max_promotions=args.max_promotions,
        promotion_keys=promotion_keys,
        dry_run=args.dry_run,
        discovery_mode=args.discovery_mode,
        source_file=args.source_file,
        promotion_key_columns=promotion_key_columns,
        date_column=args.date_column,
        store_column=args.store_column,
        sku_column=args.sku_column,
    )
    summary_lookup = dict(zip(result.summary_frame["metric_name"].astype(str), result.summary_frame["metric_value"]))
    print("source_files_inspected", _as_int(summary_lookup.get("SOURCE_FILES_INSPECTED", 0)))
    print("selected_source_file", _normalize_text(summary_lookup.get("SELECTED_SOURCE_FILE")))
    print("promotions_found", _as_int(summary_lookup.get("PROMOTIONS_FOUND", 0)))
    print("promotions_selected", _as_int(summary_lookup.get("PROMOTIONS_SELECTED", 0)))
    print("promotions_processed", _as_int(summary_lookup.get("PROMOTIONS_PROCESSED", 0)))
    print("output_root", artifacts.output_root)
    if args.dry_run:
        for row in result.packet_index_frame.to_dict(orient="records"):
            if _normalize_text(row.get("processing_status")) == NOT_PROCESSED:
                continue
            print("planned_packet", row.get("packet_output_path", ""))
            print("planned_status", row.get("processing_status", ""))
        return 0
    print("last5_promotions_packet_index", artifacts.packet_index_csv_path)
    print("last5_promotions_summary", artifacts.summary_csv_path)
    print("last5_forecast_reliability_by_promotion", artifacts.forecast_reliability_csv_path)
    print("last5_action_layer_calibration_by_promotion", artifacts.action_layer_calibration_csv_path)
    print("last5_shadow_trigger_repeatability", artifacts.shadow_trigger_repeatability_csv_path)
    print("last5_rule_family_repeat_evidence", artifacts.rule_family_repeat_evidence_csv_path)
    print("last5_promotion_portfolio_memo", artifacts.portfolio_memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
