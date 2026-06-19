from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_readiness_audit"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"

READY_FOR_FULL_REVIEW_REBUILD = "READY_FOR_FULL_REVIEW_REBUILD"
NEEDS_ACTUAL_OUTCOME_JOIN = "NEEDS_ACTUAL_OUTCOME_JOIN"
NEEDS_OPERATOR_AUDIT_JOIN = "NEEDS_OPERATOR_AUDIT_JOIN"
NEEDS_CANONICAL_REVIEW_SCHEMA_MAPPING = "NEEDS_CANONICAL_REVIEW_SCHEMA_MAPPING"
SOURCE_ONLY_NOT_REVIEW_READY = "SOURCE_ONLY_NOT_REVIEW_READY"

JOIN_ROLE_ACTUAL_OUTCOME = "ACTUAL_OUTCOME"
JOIN_ROLE_OPERATOR_AUDIT = "OPERATOR_AUDIT"
JOIN_ROLE_INSPECTION_REVIEW_PACKET = "INSPECTION_REVIEW_PACKET"
JOIN_ROLE_UNKNOWN = "UNKNOWN"

READINESS_ROWS_COLUMNS: tuple[str, ...] = (
    "promotion_folder_name",
    "promotion_key",
    "promotion_name",
    "store_number",
    "promotion_start_date",
    "promotion_end_date",
    "source_file_path",
    "source_file_type",
    "source_row_path",
    "source_manifest_path",
    "row_count",
    "sku_count",
    "identity_columns_present_count",
    "prediction_action_columns_present_count",
    "economics_columns_present_count",
    "actual_outcome_columns_present_count",
    "identity_columns_missing",
    "prediction_action_columns_missing",
    "economics_columns_missing",
    "actual_outcome_columns_missing",
    "actual_outcome_fields_present_but_blank_count",
    "join_keys_available",
    "candidate_join_source_count",
    "candidate_actual_outcome_source_count",
    "candidate_operator_audit_source_count",
    "candidate_review_packet_source_count",
    "needs_actual_outcome_join_flag",
    "needs_operator_audit_join_flag",
    "needs_canonical_review_schema_mapping_flag",
    "missing_actual_outcome_fields",
    "candidate_actual_join_sources",
    "candidate_operator_join_sources",
    "critical_missing_column_count",
    "readiness_status",
    "readiness_reason",
    "recommended_rebuild_path",
    "production_order_changes",
    "stage_12_changes",
)

MISSING_COLUMNS_COLUMNS: tuple[str, ...] = (
    "promotion_folder_name",
    "promotion_key",
    "field_group",
    "required_field_name",
    "present_in_source_rows_flag",
    "non_blank_values_present_flag",
    "notes",
)

CANDIDATE_JOIN_SOURCES_COLUMNS: tuple[str, ...] = (
    "source_path",
    "source_role",
    "columns_available",
    "possible_join_keys",
    "matching_promotion_count",
    "matched_promotion_keys",
    "can_supply_actual_outcome_fields_flag",
    "can_supply_operator_action_fields_flag",
    "can_supply_review_packet_fields_flag",
    "missing_field_groups_addressed",
    "file_exists_flag",
)

REBUILD_PLAN_COLUMNS: tuple[str, ...] = (
    "promotion_folder_name",
    "promotion_key",
    "readiness_status",
    "recommended_rebuild_path",
    "step_rank",
    "step_action",
    "step_inputs",
    "step_reason",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

IDENTITY_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "store_number": ("store_number", "store_number_actual", "store_number_master"),
    "promotion_name": ("promotion_name", "promotion_name_actual", "promotion_name_master"),
    "promotion_start_date": ("promotion_start_date", "promotion_start_date_actual", "promotion_start_date_master"),
    "promotion_end_date": ("promotion_end_date", "promotional_end_date", "promotion_end_date_actual", "promotion_end_date_master"),
    "sku_number": ("sku_number", "sku_number_actual", "sku_number_master"),
    "sku_description": ("sku_description", "sku_description_actual"),
}

PREDICTION_ACTION_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "expected_promo_demand": ("expected_promo_demand", "expected_units_total_promo", "projected_promotional_units"),
    "recommended_order_units": ("recommended_order_units", "final_store_order_units", "store_adjusted_qty"),
    "store_action": ("store_action", "store_action_label", "recommended_action"),
    "demand_evidence_label": ("demand_evidence_label", "demand_evidence_class"),
}

ECONOMICS_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "gross_profit_promo": ("gross_profit_promo", "gross_profit_promo_dollars"),
    "promo_gm_unit": ("promo_gm_unit", "promo_effective_cost"),
    "promo_price": ("promo_price", "promo_price_ex_gst"),
    "capital_proxy": ("capital_left_in_unsold_store_allocation", "capital_left", "capital_at_risk_adjusted_dollars", "promo_cost_price"),
}

ACTUAL_OUTCOME_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "actual_units_sold": ("actual_units_sold", "actual_units_sold_promo"),
    "actual_gross_profit": ("actual_gross_profit", "gross_profit_actual", "realised_gross_profit"),
    "capital_left": ("capital_left", "capital_left_in_unsold_store_allocation", "actual_capital_left", "unsold_allocation_value"),
    "sell_through": ("sell_through_pct", "actual_sell_through_pct", "actual_units_vs_allocated_units"),
    "actual_outcome_date_window": ("promotion_end_date", "promotional_end_date", "actual_outcome_date_window"),
}

JOIN_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "store_number": ("store_number", "store_number_actual", "store_number_master", "_key_store_number"),
    "promotion_start_date": ("promotion_start_date", "promotion_start_date_actual", "promotion_start_date_master", "_key_promotion_start_date"),
    "promotion_name": ("promotion_name", "promotion_name_actual", "promotion_name_master", "_key_promotion_name"),
    "sku_number": ("sku_number", "sku_number_actual", "sku_number_master", "_key_sku_number"),
}

ACTUAL_OUTCOME_JOIN_SOURCE_CANDIDATES: tuple[str, ...] = (
    "tmp/shadow_policy_stage11_replay_20260612/actual_outcome_backtest/store_allocation_actual_outcome_backtest.csv",
)
OPERATOR_AUDIT_JOIN_SOURCE_CANDIDATES: tuple[str, ...] = (
    "tmp/stage11_clean_visible_replay_20260614/combined_store_promotion_operator_audit.csv",
)

REQUIRED_IDENTITY_FIELDS: tuple[str, ...] = (
    "store_number",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "sku_number",
    "sku_description",
)
REQUIRED_PREDICTION_ACTION_FIELDS: tuple[str, ...] = (
    "expected_promo_demand",
    "recommended_order_units",
    "store_action",
    "demand_evidence_label",
)
REQUIRED_ECONOMICS_FIELDS: tuple[str, ...] = (
    "gross_profit_promo",
    "promo_gm_unit",
    "promo_price",
)
REQUIRED_ACTUAL_OUTCOME_FIELDS: tuple[str, ...] = (
    "actual_units_sold",
    "actual_gross_profit",
)


class PromotionsMaterializedSourceReadinessAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateJoinSource:
    source_path: Path
    source_role: str
    columns: tuple[str, ...]
    possible_join_keys: tuple[str, ...]
    matching_promotion_count: int
    matching_promotion_keys: tuple[str, ...]
    can_supply_actual_outcome_fields_flag: int
    can_supply_operator_action_fields_flag: int
    can_supply_review_packet_fields_flag: int
    missing_field_groups_addressed: tuple[str, ...]
    file_exists_flag: int


@dataclass(frozen=True)
class PromotionsMaterializedSourceReadinessAuditResult:
    readiness_rows_frame: pd.DataFrame
    missing_columns_frame: pd.DataFrame
    candidate_join_sources_frame: pd.DataFrame
    rebuild_plan_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceReadinessAuditArtifacts:
    output_root: str
    readiness_rows_csv_path: str
    missing_columns_csv_path: str
    candidate_join_sources_csv_path: str
    rebuild_plan_csv_path: str
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


def _iso_date_text(value: object) -> str:
    parsed = _parse_date_text(value)
    if pd.isna(parsed):
        return _normalize_text(value)
    return str(parsed.date())


def _as_int(value: object) -> int:
    return int(round(float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])))


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _read_csv(path: str | Path, *, allow_empty: bool = False, nrows: int | None = None) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceReadinessAuditError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False, nrows=nrows)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceReadinessAuditError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty and nrows is None:
        raise PromotionsMaterializedSourceReadinessAuditError(f"CSV is empty: {csv_path}")
    return frame


def _field_presence(columns: Iterable[str], aliases: dict[str, tuple[str, ...]]) -> tuple[dict[str, str | None], list[str]]:
    available = set(columns)
    resolved: dict[str, str | None] = {}
    missing: list[str] = []
    for logical_name, candidates in aliases.items():
        matched = next((column_name for column_name in candidates if column_name in available), None)
        resolved[logical_name] = matched
        if matched is None:
            missing.append(logical_name)
    return resolved, missing


def _field_blankness(frame: pd.DataFrame, resolved: dict[str, str | None]) -> dict[str, bool]:
    blankness: dict[str, bool] = {}
    for logical_name, column_name in resolved.items():
        if column_name is None or column_name not in frame.columns:
            blankness[logical_name] = True
            continue
        blankness[logical_name] = _normalize_text_series(frame[column_name]).eq("").all()
    return blankness


def _join_keys_present(columns: Iterable[str]) -> list[str]:
    available = set(columns)
    present: list[str] = []
    for logical_name, candidates in JOIN_KEY_ALIASES.items():
        if any(column_name in available for column_name in candidates):
            present.append(logical_name)
    return present


def _detect_candidate_join_sources(
    *,
    repo_root: Path,
    candidate_source_paths: Sequence[str | Path] | None,
) -> list[Path]:
    if candidate_source_paths is None:
        candidates = [repo_root / relative_path for relative_path in ACTUAL_OUTCOME_JOIN_SOURCE_CANDIDATES]
        candidates.extend(repo_root / relative_path for relative_path in OPERATOR_AUDIT_JOIN_SOURCE_CANDIDATES)
    else:
        candidates = [Path(path) if Path(path).is_absolute() else repo_root / Path(path) for path in candidate_source_paths]
    inspection_root = repo_root / "tmp/promotions_local_inspection"
    if inspection_root.exists():
        candidates.extend(sorted(inspection_root.rglob("*_inspection_review_packet.csv")))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _candidate_source_role(path: Path) -> str:
    lowered = path.name.casefold()
    if "actual_outcome_backtest" in lowered:
        return JOIN_ROLE_ACTUAL_OUTCOME
    if "operator_audit" in lowered:
        return JOIN_ROLE_OPERATOR_AUDIT
    if "inspection_review_packet" in lowered:
        return JOIN_ROLE_INSPECTION_REVIEW_PACKET
    return JOIN_ROLE_UNKNOWN


def _promotion_rows_from_materialized_root(packet_root: Path) -> list[tuple[Path, Path]]:
    source_root = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME
    if not source_root.exists():
        return []
    pairs: list[tuple[Path, Path]] = []
    for folder in sorted(path for path in source_root.iterdir() if path.is_dir()):
        rows_path = folder / "promotion_source_rows.csv"
        manifest_path = folder / "promotion_source_manifest.csv"
        if rows_path.exists() and manifest_path.exists():
            pairs.append((rows_path, manifest_path))
    return pairs


def _possible_join_matches(candidate_frame: pd.DataFrame, promotions_frame: pd.DataFrame) -> tuple[int, tuple[str, ...]]:
    if candidate_frame.empty or promotions_frame.empty:
        return 0, ()
    candidate = candidate_frame.copy()
    promotions = promotions_frame.copy()
    candidate_columns = candidate.columns.tolist()
    promotions_columns = promotions.columns.tolist()
    resolved_candidate, _ = _field_presence(candidate_columns, {
        "store_number": JOIN_KEY_ALIASES["store_number"],
        "promotion_start_date": JOIN_KEY_ALIASES["promotion_start_date"],
        "promotion_name": JOIN_KEY_ALIASES["promotion_name"],
    })
    resolved_promotions, _ = _field_presence(promotions_columns, {
        "store_number": ("store_number",),
        "promotion_start_date": ("promotion_start_date",),
        "promotion_name": ("promotion_name",),
    })
    if any(value is None for value in resolved_candidate.values()) or any(value is None for value in resolved_promotions.values()):
        return 0, ()
    candidate["__store"] = _normalize_text_series(candidate[resolved_candidate["store_number"]])
    candidate["__start"] = candidate[resolved_candidate["promotion_start_date"]].map(_iso_date_text)
    candidate["__name"] = _normalize_text_series(candidate[resolved_candidate["promotion_name"]]).str.casefold()
    promotions["__store"] = _normalize_text_series(promotions[resolved_promotions["store_number"]])
    promotions["__start"] = promotions[resolved_promotions["promotion_start_date"]].map(_iso_date_text)
    promotions["__name"] = _normalize_text_series(promotions[resolved_promotions["promotion_name"]]).str.casefold()
    merged = promotions[["promotion_key", "__store", "__start", "__name"]].drop_duplicates().merge(
        candidate[["__store", "__start", "__name"]].drop_duplicates(),
        on=["__store", "__start", "__name"],
        how="inner",
    )
    matched_promotion_keys = tuple(merged["promotion_key"].astype(str).drop_duplicates().tolist())
    return int(len(matched_promotion_keys)), matched_promotion_keys


def _candidate_join_source_record(path: Path, promotions_frame: pd.DataFrame) -> CandidateJoinSource:
    if not path.exists():
        return CandidateJoinSource(
            source_path=path,
            source_role=_candidate_source_role(path),
            columns=(),
            possible_join_keys=(),
            matching_promotion_count=0,
            matching_promotion_keys=(),
            can_supply_actual_outcome_fields_flag=0,
            can_supply_operator_action_fields_flag=0,
            can_supply_review_packet_fields_flag=0,
            missing_field_groups_addressed=(),
            file_exists_flag=0,
        )
    frame = _read_csv(path, allow_empty=True, nrows=2000)
    columns = tuple(frame.columns.astype(str).tolist())
    possible_join_keys = tuple(_join_keys_present(columns))
    actual_resolved, actual_missing = _field_presence(columns, ACTUAL_OUTCOME_FIELD_ALIASES)
    action_resolved, action_missing = _field_presence(columns, PREDICTION_ACTION_FIELD_ALIASES)
    review_packet_resolved, review_packet_missing = _field_presence(columns, {
        "predicted_gross_profit": ("predicted_gross_profit",),
        "decision_recommendation": ("decision_recommendation",),
        "promotion_row_key": ("promotion_row_key",),
    })
    missing_groups: list[str] = []
    if len(actual_missing) < len(ACTUAL_OUTCOME_FIELD_ALIASES):
        missing_groups.append("actual_outcome")
    if len(action_missing) < len(PREDICTION_ACTION_FIELD_ALIASES):
        missing_groups.append("operator_action")
    if len(review_packet_missing) < len(review_packet_resolved):
        missing_groups.append("review_packet")
    matching_promotion_count, matching_promotion_keys = _possible_join_matches(frame, promotions_frame)
    return CandidateJoinSource(
        source_path=path,
        source_role=_candidate_source_role(path),
        columns=columns,
        possible_join_keys=possible_join_keys,
        matching_promotion_count=matching_promotion_count,
        matching_promotion_keys=matching_promotion_keys,
        can_supply_actual_outcome_fields_flag=int(any(value is not None for value in actual_resolved.values())),
        can_supply_operator_action_fields_flag=int(any(value is not None for value in action_resolved.values())),
        can_supply_review_packet_fields_flag=int(any(value is not None for value in review_packet_resolved.values())),
        missing_field_groups_addressed=tuple(missing_groups),
        file_exists_flag=1,
    )


def _required_missing_fields(missing_fields: list[str], required_fields: Sequence[str]) -> list[str]:
    required = set(required_fields)
    return [field_name for field_name in missing_fields if field_name in required]


def _matching_candidate_sources(
    candidate_sources: Sequence[CandidateJoinSource],
    promotion_key: str,
) -> list[CandidateJoinSource]:
    return [source for source in candidate_sources if promotion_key in source.matching_promotion_keys]


def _format_paths(paths: Iterable[Path]) -> str:
    return "; ".join(str(path) for path in paths)


def _readiness_status_for_promotion(
    *,
    identity_missing: list[str],
    prediction_missing: list[str],
    economics_missing: list[str],
    actual_missing: list[str],
    actual_blank_count: int,
    candidate_sources: Sequence[CandidateJoinSource],
) -> tuple[str, str, str]:
    has_actual_join = any(source.can_supply_actual_outcome_fields_flag for source in candidate_sources)
    has_operator_join = any(source.can_supply_operator_action_fields_flag for source in candidate_sources)
    if not identity_missing and not prediction_missing and not economics_missing and not actual_missing and actual_blank_count == 0:
        return (
            READY_FOR_FULL_REVIEW_REBUILD,
            "Materialized source rows already expose the required identity, action, economics, and actual-outcome fields for a governed rebuild.",
            "Map the materialized source rows into the canonical review schema and rebuild the governed diagnostic chain.",
        )
    if (actual_missing or actual_blank_count > 0) and has_actual_join:
        return (
            NEEDS_ACTUAL_OUTCOME_JOIN,
            "Materialized source rows are missing or blank on one or more actual-outcome fields, but an actual-outcome join source is available.",
            "Join actual-outcome backtest fields first, then map the enriched frame into the canonical review schema before rebuilding the governed diagnostic chain.",
        )
    if prediction_missing and has_operator_join:
        return (
            NEEDS_OPERATOR_AUDIT_JOIN,
            "Materialized source rows are missing operator/action evidence fields, but an operator-audit style join source is available.",
            "Join operator-audit action fields, then map the enriched frame into the canonical review schema before rebuilding the governed diagnostic chain.",
        )
    if not identity_missing:
        return (
            NEEDS_CANONICAL_REVIEW_SCHEMA_MAPPING,
            "Core promotion identity is present, but the materialized source rows still need governed review-schema mapping and possibly supplemental joins.",
            "Define canonical review-schema mapping, then add any missing joins for actual outcomes or operator evidence before rebuilding the governed diagnostic chain.",
        )
    return (
        SOURCE_ONLY_NOT_REVIEW_READY,
        "Materialized source rows are missing core identity fields required to rebuild a governed review packet.",
        "Do not attempt a governed rebuild yet; recover missing canonical identity fields first and only then reassess joins.",
    )


def _missing_rows_for_group(
    *,
    promotion_folder_name: str,
    promotion_key: str,
    field_group: str,
    resolved: dict[str, str | None],
    blankness: dict[str, bool],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for logical_name, column_name in resolved.items():
        rows.append(
            {
                "promotion_folder_name": promotion_folder_name,
                "promotion_key": promotion_key,
                "field_group": field_group,
                "required_field_name": logical_name,
                "present_in_source_rows_flag": int(column_name is not None),
                "non_blank_values_present_flag": int(column_name is not None and not blankness.get(logical_name, True)),
                "notes": "",
            }
        )
    return rows


def _build_rebuild_plan_rows(
    *,
    promotion_folder_name: str,
    promotion_key: str,
    readiness_status: str,
    recommended_rebuild_path: str,
    candidate_sources: Sequence[CandidateJoinSource],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "promotion_folder_name": promotion_folder_name,
            "promotion_key": promotion_key,
            "readiness_status": readiness_status,
            "recommended_rebuild_path": recommended_rebuild_path,
            "step_rank": 1,
            "step_action": "LOAD_MATERIALIZED_SOURCE_ROWS",
            "step_inputs": "promotion_source_rows.csv",
            "step_reason": "Start from the materialized source packet without altering production logic or Stage 12.",
        }
    ]
    next_rank = 2
    if readiness_status == NEEDS_ACTUAL_OUTCOME_JOIN:
        actual_paths = [str(source.source_path) for source in candidate_sources if source.can_supply_actual_outcome_fields_flag]
        rows.append(
            {
                "promotion_folder_name": promotion_folder_name,
                "promotion_key": promotion_key,
                "readiness_status": readiness_status,
                "recommended_rebuild_path": recommended_rebuild_path,
                "step_rank": next_rank,
                "step_action": "JOIN_ACTUAL_OUTCOME_FIELDS",
                "step_inputs": "; ".join(actual_paths),
                "step_reason": "Actual outcome fields are missing or blank and must be joined rather than assumed as zero actual sales.",
            }
        )
        next_rank += 1
    if readiness_status == NEEDS_OPERATOR_AUDIT_JOIN:
        operator_paths = [str(source.source_path) for source in candidate_sources if source.can_supply_operator_action_fields_flag]
        rows.append(
            {
                "promotion_folder_name": promotion_folder_name,
                "promotion_key": promotion_key,
                "readiness_status": readiness_status,
                "recommended_rebuild_path": recommended_rebuild_path,
                "step_rank": next_rank,
                "step_action": "JOIN_OPERATOR_ACTION_FIELDS",
                "step_inputs": "; ".join(operator_paths),
                "step_reason": "Operator/action evidence fields are missing and should be recovered from an audit or review packet source.",
            }
        )
        next_rank += 1
    rows.append(
        {
            "promotion_folder_name": promotion_folder_name,
            "promotion_key": promotion_key,
            "readiness_status": readiness_status,
            "recommended_rebuild_path": recommended_rebuild_path,
            "step_rank": next_rank,
            "step_action": "MAP_TO_CANONICAL_REVIEW_SCHEMA",
            "step_inputs": "materialized source rows plus optional joins",
            "step_reason": "A governed review rebuild still requires canonical review packet column mapping.",
        }
    )
    rows.append(
        {
            "promotion_folder_name": promotion_folder_name,
            "promotion_key": promotion_key,
            "readiness_status": readiness_status,
            "recommended_rebuild_path": recommended_rebuild_path,
            "step_rank": next_rank + 1,
            "step_action": "REBUILD_GOVERNED_DIAGNOSTIC_CHAIN",
            "step_inputs": "review packet, readiness inspection, unresolved inspection, calibration, simulation, leaderboard",
            "step_reason": "Rebuild only the governed diagnostics chain; do not start training or change production ordering logic.",
        }
    )
    return rows


def _build_summary_frame(readiness_rows_frame: pd.DataFrame, candidate_join_sources_frame: pd.DataFrame) -> pd.DataFrame:
    if readiness_rows_frame.empty:
        rows = [
            _summary_row("PROMOTIONS_AUDITED", 0, "Materialized promotions audited."),
            _summary_row("PROMOTIONS_READY_FOR_FULL_REVIEW_REBUILD", 0, "Promotions already ready for governed rebuild."),
            _summary_row("PROMOTIONS_NEEDING_ACTUAL_OUTCOME_JOIN", 0, "Promotions needing actual-outcome joins."),
            _summary_row("PROMOTIONS_NEEDING_OPERATOR_AUDIT_JOIN", 0, "Promotions needing operator-audit joins."),
            _summary_row("PROMOTIONS_NEEDING_CANONICAL_REVIEW_SCHEMA_MAPPING", 0, "Promotions still needing canonical review-schema mapping."),
            _summary_row("SOURCE_ONLY_NOT_REVIEW_READY_PROMOTIONS", 0, "Promotions that are still not review-ready from source only."),
            _summary_row("CANDIDATE_JOIN_SOURCES_FOUND", 0, "Candidate join sources discovered."),
            _summary_row("PRODUCTION_ORDER_CHANGES_TOTAL", 0, "Diagnostics only; production ordering remains unchanged."),
            _summary_row("STAGE_12_CHANGES_TOTAL", 0, "Diagnostics only; Stage 12 remains unchanged."),
        ]
        return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    rows = [
        _summary_row("PROMOTIONS_AUDITED", len(readiness_rows_frame.index), "Materialized promotions audited."),
        _summary_row("PROMOTIONS_READY_FOR_FULL_REVIEW_REBUILD", int(readiness_rows_frame["readiness_status"].astype(str).eq(READY_FOR_FULL_REVIEW_REBUILD).sum()), "Promotions already ready for governed rebuild."),
        _summary_row("PROMOTIONS_NEEDING_ACTUAL_OUTCOME_JOIN", int(pd.to_numeric(readiness_rows_frame["needs_actual_outcome_join_flag"], errors="coerce").fillna(0).sum()), "Promotions needing actual-outcome joins."),
        _summary_row("PROMOTIONS_NEEDING_OPERATOR_AUDIT_JOIN", int(pd.to_numeric(readiness_rows_frame["needs_operator_audit_join_flag"], errors="coerce").fillna(0).sum()), "Promotions needing operator-audit joins."),
        _summary_row("PROMOTIONS_NEEDING_CANONICAL_REVIEW_SCHEMA_MAPPING", int(pd.to_numeric(readiness_rows_frame["needs_canonical_review_schema_mapping_flag"], errors="coerce").fillna(0).sum()), "Promotions still needing canonical review-schema mapping."),
        _summary_row("SOURCE_ONLY_NOT_REVIEW_READY_PROMOTIONS", int(readiness_rows_frame["readiness_status"].astype(str).eq(SOURCE_ONLY_NOT_REVIEW_READY).sum()), "Promotions that are still not review-ready from source only."),
        _summary_row("CANDIDATE_JOIN_SOURCES_FOUND", int(candidate_join_sources_frame["file_exists_flag"].astype(int).sum()) if not candidate_join_sources_frame.empty else 0, "Candidate join sources discovered."),
        _summary_row("PRODUCTION_ORDER_CHANGES_TOTAL", int(pd.to_numeric(readiness_rows_frame["production_order_changes"], errors="coerce").fillna(0).sum()), "Diagnostics only; production ordering remains unchanged."),
        _summary_row("STAGE_12_CHANGES_TOTAL", int(pd.to_numeric(readiness_rows_frame["stage_12_changes"], errors="coerce").fillna(0).sum()), "Diagnostics only; Stage 12 remains unchanged."),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_memo(summary_frame: pd.DataFrame, readiness_rows_frame: pd.DataFrame, candidate_join_sources_frame: pd.DataFrame, missing_columns_frame: pd.DataFrame) -> str:
    summary_lookup = dict(zip(summary_frame["metric_name"].astype(str), summary_frame["metric_value"]))
    status_lines = [
        f"- {status}: {int(count)} promotion(s)"
        for status, count in readiness_rows_frame["readiness_status"].astype(str).value_counts(dropna=False).items()
    ] or ["- No materialized promotions were audited."]
    missing_lines = []
    if not missing_columns_frame.empty:
        grouped = missing_columns_frame.loc[
            missing_columns_frame["non_blank_values_present_flag"].astype(int).eq(0)
        ].groupby("required_field_name", dropna=False).size().sort_values(ascending=False)
        missing_lines = [f"- {field_name}: {int(count)} promotion(s)" for field_name, count in grouped.head(8).items()]
    if not missing_lines:
        missing_lines = ["- No critical missing-column hotspots were detected across the audited promotions."]
    join_lines = []
    if not candidate_join_sources_frame.empty:
        for row in candidate_join_sources_frame.loc[candidate_join_sources_frame["file_exists_flag"].astype(int).eq(1)].head(8).itertuples(index=False):
            join_lines.append(
                f"- {getattr(row, 'source_role')}: {getattr(row, 'source_path')} (matching promotions={getattr(row, 'matching_promotion_count')}, join keys={getattr(row, 'possible_join_keys')})"
            )
    if not join_lines:
        join_lines = ["- No candidate join sources were found."]
    recommended_path = ""
    if not readiness_rows_frame.empty:
        most_common = readiness_rows_frame["recommended_rebuild_path"].astype(str).mode()
        if not most_common.empty:
            recommended_path = most_common.iloc[0]
    return "\n".join(
        [
            "# Materialized Source Readiness Audit",
            "",
            "This is not an order file.",
            "No training was started.",
            "Production ordering logic remains unchanged.",
            "Stage 12 remains unchanged.",
            "Shadow rules remain diagnostics-only.",
            "Missing actual outcome fields are treated as missing, not as zero actual sales.",
            "",
            "## 1. Audit summary",
            f"Promotions audited = {int(summary_lookup.get('PROMOTIONS_AUDITED', 0))}.",
            f"Ready for full review rebuild = {int(summary_lookup.get('PROMOTIONS_READY_FOR_FULL_REVIEW_REBUILD', 0))}.",
            f"Need actual outcome join = {int(summary_lookup.get('PROMOTIONS_NEEDING_ACTUAL_OUTCOME_JOIN', 0))}.",
            f"Need operator audit join = {int(summary_lookup.get('PROMOTIONS_NEEDING_OPERATOR_AUDIT_JOIN', 0))}.",
            f"Need canonical review schema mapping = {int(summary_lookup.get('PROMOTIONS_NEEDING_CANONICAL_REVIEW_SCHEMA_MAPPING', 0))}.",
            f"Source-only not review ready = {int(summary_lookup.get('SOURCE_ONLY_NOT_REVIEW_READY_PROMOTIONS', 0))}.",
            "",
            "## 2. Readiness status mix",
            *status_lines,
            "",
            "## 3. Candidate join sources",
            *join_lines,
            "",
            "## 4. Missing critical columns",
            *missing_lines,
            "",
            "## 5. Recommended rebuild path",
            recommended_path or "Define a canonical review-schema mapping, then enrich each promotion with any required actual-outcome or operator-audit joins before rebuilding the governed diagnostics chain.",
        ]
    ).strip()


def build_promotions_materialized_source_readiness_audit(
    *,
    packet_root: str | Path,
    candidate_source_paths: Sequence[str | Path] | None = None,
    repo_root: str | Path | None = None,
) -> PromotionsMaterializedSourceReadinessAuditResult:
    packet_root_path = Path(packet_root)
    pairs = _promotion_rows_from_materialized_root(packet_root_path)
    promotions_frame_rows: list[dict[str, object]] = []
    for rows_path, manifest_path in pairs:
        manifest_frame = _read_csv(manifest_path)
        manifest_row = manifest_frame.iloc[0].to_dict() if not manifest_frame.empty else {}
        summary_path = rows_path.parent / "promotion_source_summary.csv"
        summary_frame = _read_csv(summary_path, allow_empty=True)
        summary_row = summary_frame.iloc[0].to_dict() if not summary_frame.empty else {}
        promotions_frame_rows.append(
            {
                "promotion_key": _normalize_text(summary_row.get("promotion_key")) or _normalize_text(manifest_row.get("promotion_name")) or rows_path.parent.name,
                "store_number": _normalize_text(manifest_row.get("store_number")),
                "promotion_start_date": _iso_date_text(manifest_row.get("promotion_start_date")),
                "promotion_name": _normalize_text(manifest_row.get("promotion_name")),
            }
        )
    promotions_frame = pd.DataFrame(promotions_frame_rows)

    resolved_repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    candidate_sources = [
        _candidate_join_source_record(path, promotions_frame)
        for path in _detect_candidate_join_sources(
            repo_root=resolved_repo_root,
            candidate_source_paths=candidate_source_paths,
        )
    ]
    candidate_join_sources_frame = pd.DataFrame([
        {
            "source_path": str(source.source_path),
            "source_role": source.source_role,
            "columns_available": "; ".join(source.columns),
            "possible_join_keys": "; ".join(source.possible_join_keys),
            "matching_promotion_count": source.matching_promotion_count,
            "matched_promotion_keys": "; ".join(source.matching_promotion_keys),
            "can_supply_actual_outcome_fields_flag": source.can_supply_actual_outcome_fields_flag,
            "can_supply_operator_action_fields_flag": source.can_supply_operator_action_fields_flag,
            "can_supply_review_packet_fields_flag": source.can_supply_review_packet_fields_flag,
            "missing_field_groups_addressed": "; ".join(source.missing_field_groups_addressed),
            "file_exists_flag": source.file_exists_flag,
        }
        for source in candidate_sources
    ], columns=CANDIDATE_JOIN_SOURCES_COLUMNS)

    readiness_rows: list[dict[str, object]] = []
    missing_rows: list[dict[str, object]] = []
    rebuild_plan_rows: list[dict[str, object]] = []

    for rows_path, manifest_path in pairs:
        rows_frame = _read_csv(rows_path, allow_empty=True)
        manifest_frame = _read_csv(manifest_path, allow_empty=True)
        manifest_row = manifest_frame.iloc[0].to_dict() if not manifest_frame.empty else {}
        summary_frame = _read_csv(rows_path.parent / "promotion_source_summary.csv", allow_empty=True)
        summary_row = summary_frame.iloc[0].to_dict() if not summary_frame.empty else {}
        folder_name = rows_path.parent.name
        promotion_key = (
            _normalize_text(summary_row.get("promotion_key"))
            or (_normalize_text(rows_frame.iloc[0].get("promotion_key")) if not rows_frame.empty and "promotion_key" in rows_frame.columns else "")
            or _normalize_text(manifest_row.get("promotion_name"))
        )
        identity_resolved, identity_missing = _field_presence(rows_frame.columns, IDENTITY_FIELD_ALIASES)
        prediction_resolved, prediction_missing = _field_presence(rows_frame.columns, PREDICTION_ACTION_FIELD_ALIASES)
        economics_resolved, economics_missing = _field_presence(rows_frame.columns, ECONOMICS_FIELD_ALIASES)
        actual_resolved, actual_missing = _field_presence(rows_frame.columns, ACTUAL_OUTCOME_FIELD_ALIASES)
        identity_blankness = _field_blankness(rows_frame, identity_resolved)
        prediction_blankness = _field_blankness(rows_frame, prediction_resolved)
        economics_blankness = _field_blankness(rows_frame, economics_resolved)
        actual_blankness = _field_blankness(rows_frame, actual_resolved)
        required_identity_missing = _required_missing_fields(identity_missing, REQUIRED_IDENTITY_FIELDS)
        required_prediction_missing = _required_missing_fields(prediction_missing, REQUIRED_PREDICTION_ACTION_FIELDS)
        required_economics_missing = _required_missing_fields(economics_missing, REQUIRED_ECONOMICS_FIELDS)
        required_actual_missing = _required_missing_fields(actual_missing, REQUIRED_ACTUAL_OUTCOME_FIELDS)
        actual_blank_count = int(sum(1 for logical_name in REQUIRED_ACTUAL_OUTCOME_FIELDS if actual_resolved.get(logical_name) is not None and actual_blankness.get(logical_name, True)))
        matching_candidate_sources = _matching_candidate_sources(candidate_sources, promotion_key)
        candidate_actual_sources = [source.source_path for source in matching_candidate_sources if source.can_supply_actual_outcome_fields_flag]
        candidate_operator_sources = [source.source_path for source in matching_candidate_sources if source.can_supply_operator_action_fields_flag]

        status, reason, recommended_path = _readiness_status_for_promotion(
            identity_missing=required_identity_missing,
            prediction_missing=required_prediction_missing,
            economics_missing=required_economics_missing,
            actual_missing=required_actual_missing,
            actual_blank_count=actual_blank_count,
            candidate_sources=matching_candidate_sources,
        )
        needs_actual_outcome_join_flag = int(bool(required_actual_missing or actual_blank_count > 0) and bool(candidate_actual_sources))
        needs_operator_audit_join_flag = int(bool(required_prediction_missing) and bool(candidate_operator_sources))
        needs_canonical_review_schema_mapping_flag = int(bool(required_identity_missing or required_prediction_missing or required_economics_missing))
        critical_missing_column_count = len(required_identity_missing) + len(required_prediction_missing) + len(required_economics_missing) + len(required_actual_missing)
        readiness_rows.append(
            {
                "promotion_folder_name": folder_name,
                "promotion_key": promotion_key or _normalize_text(manifest_row.get("promotion_name")),
                "promotion_name": _normalize_text(manifest_row.get("promotion_name")),
                "store_number": _normalize_text(manifest_row.get("store_number")),
                "promotion_start_date": _iso_date_text(manifest_row.get("promotion_start_date")),
                "promotion_end_date": _iso_date_text(manifest_row.get("promotion_end_date")),
                "source_file_path": _normalize_text(manifest_row.get("source_file_path")),
                "source_file_type": _normalize_text(manifest_row.get("source_file_type")),
                "source_row_path": str(rows_path),
                "source_manifest_path": str(manifest_path),
                "row_count": int(len(rows_frame.index)),
                "sku_count": int(rows_frame[identity_resolved["sku_number"]].astype(str).nunique()) if identity_resolved.get("sku_number") in rows_frame.columns else 0,
                "identity_columns_present_count": len(IDENTITY_FIELD_ALIASES) - len(identity_missing),
                "prediction_action_columns_present_count": len(PREDICTION_ACTION_FIELD_ALIASES) - len(prediction_missing),
                "economics_columns_present_count": len(ECONOMICS_FIELD_ALIASES) - len(economics_missing),
                "actual_outcome_columns_present_count": len(ACTUAL_OUTCOME_FIELD_ALIASES) - len(actual_missing),
                "identity_columns_missing": "; ".join(identity_missing),
                "prediction_action_columns_missing": "; ".join(prediction_missing),
                "economics_columns_missing": "; ".join(economics_missing),
                "actual_outcome_columns_missing": "; ".join(actual_missing),
                "actual_outcome_fields_present_but_blank_count": actual_blank_count,
                "join_keys_available": "; ".join(_join_keys_present(rows_frame.columns)),
                "candidate_join_source_count": len(matching_candidate_sources),
                "candidate_actual_outcome_source_count": len(candidate_actual_sources),
                "candidate_operator_audit_source_count": len(candidate_operator_sources),
                "candidate_review_packet_source_count": int(sum(source.can_supply_review_packet_fields_flag for source in matching_candidate_sources)),
                "needs_actual_outcome_join_flag": needs_actual_outcome_join_flag,
                "needs_operator_audit_join_flag": needs_operator_audit_join_flag,
                "needs_canonical_review_schema_mapping_flag": needs_canonical_review_schema_mapping_flag,
                "missing_actual_outcome_fields": "; ".join(required_actual_missing),
                "candidate_actual_join_sources": _format_paths(candidate_actual_sources),
                "candidate_operator_join_sources": _format_paths(candidate_operator_sources),
                "critical_missing_column_count": critical_missing_column_count,
                "readiness_status": status,
                "readiness_reason": reason,
                "recommended_rebuild_path": recommended_path,
                "production_order_changes": 0,
                "stage_12_changes": 0,
            }
        )
        missing_rows.extend(_missing_rows_for_group(
            promotion_folder_name=folder_name,
            promotion_key=promotion_key,
            field_group="identity",
            resolved=identity_resolved,
            blankness=identity_blankness,
        ))
        missing_rows.extend(_missing_rows_for_group(
            promotion_folder_name=folder_name,
            promotion_key=promotion_key,
            field_group="prediction_action",
            resolved=prediction_resolved,
            blankness=prediction_blankness,
        ))
        missing_rows.extend(_missing_rows_for_group(
            promotion_folder_name=folder_name,
            promotion_key=promotion_key,
            field_group="economics",
            resolved=economics_resolved,
            blankness=economics_blankness,
        ))
        missing_rows.extend(_missing_rows_for_group(
            promotion_folder_name=folder_name,
            promotion_key=promotion_key,
            field_group="actual_outcome",
            resolved=actual_resolved,
            blankness=actual_blankness,
        ))
        rebuild_plan_rows.extend(_build_rebuild_plan_rows(
            promotion_folder_name=folder_name,
            promotion_key=promotion_key,
            readiness_status=status,
            recommended_rebuild_path=recommended_path,
            candidate_sources=matching_candidate_sources,
        ))

    readiness_rows_frame = pd.DataFrame(readiness_rows, columns=READINESS_ROWS_COLUMNS)
    missing_columns_frame = pd.DataFrame(missing_rows, columns=MISSING_COLUMNS_COLUMNS)
    rebuild_plan_frame = pd.DataFrame(rebuild_plan_rows, columns=REBUILD_PLAN_COLUMNS)
    summary_frame = _build_summary_frame(readiness_rows_frame, candidate_join_sources_frame)
    memo_markdown = _build_memo(summary_frame, readiness_rows_frame, candidate_join_sources_frame, missing_columns_frame)
    return PromotionsMaterializedSourceReadinessAuditResult(
        readiness_rows_frame=readiness_rows_frame,
        missing_columns_frame=missing_columns_frame,
        candidate_join_sources_frame=candidate_join_sources_frame,
        rebuild_plan_frame=rebuild_plan_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_readiness_audit(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    candidate_source_paths: Sequence[str | Path] | None = None,
    repo_root: str | Path | None = None,
) -> PromotionsMaterializedSourceReadinessAuditArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_readiness_audit(
        packet_root=packet_root_path,
        candidate_source_paths=candidate_source_paths,
        repo_root=repo_root,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)
    readiness_rows_csv_path = output_root_path / "materialized_source_readiness_rows.csv"
    missing_columns_csv_path = output_root_path / "materialized_source_missing_columns.csv"
    candidate_join_sources_csv_path = output_root_path / "materialized_source_candidate_join_sources.csv"
    rebuild_plan_csv_path = output_root_path / "materialized_source_rebuild_plan.csv"
    summary_csv_path = output_root_path / "materialized_source_readiness_summary.csv"
    memo_md_path = output_root_path / "materialized_source_readiness_memo.md"
    result.readiness_rows_frame.to_csv(readiness_rows_csv_path, index=False)
    result.missing_columns_frame.to_csv(missing_columns_csv_path, index=False)
    result.candidate_join_sources_frame.to_csv(candidate_join_sources_csv_path, index=False)
    result.rebuild_plan_frame.to_csv(rebuild_plan_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")
    return PromotionsMaterializedSourceReadinessAuditArtifacts(
        output_root=str(output_root_path),
        readiness_rows_csv_path=str(readiness_rows_csv_path),
        missing_columns_csv_path=str(missing_columns_csv_path),
        candidate_join_sources_csv_path=str(candidate_join_sources_csv_path),
        rebuild_plan_csv_path=str(rebuild_plan_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit materialized source-only promotion packets for governed rebuild readiness.")
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_readiness_audit(packet_root=args.packet_root, output_root=args.output_root)
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    summary_lookup = dict(zip(summary_frame.get("metric_name", pd.Series(dtype="object")).astype(str), summary_frame.get("metric_value", pd.Series(dtype="object"))))
    print("promotions_audited", _as_int(summary_lookup.get("PROMOTIONS_AUDITED", 0)))
    print("promotions_ready_for_full_review_rebuild", _as_int(summary_lookup.get("PROMOTIONS_READY_FOR_FULL_REVIEW_REBUILD", 0)))
    print("promotions_needing_actual_outcome_join", _as_int(summary_lookup.get("PROMOTIONS_NEEDING_ACTUAL_OUTCOME_JOIN", 0)))
    print("promotions_needing_operator_audit_join", _as_int(summary_lookup.get("PROMOTIONS_NEEDING_OPERATOR_AUDIT_JOIN", 0)))
    print("candidate_join_sources_found", _as_int(summary_lookup.get("CANDIDATE_JOIN_SOURCES_FOUND", 0)))
    print("materialized_source_readiness_rows", artifacts.readiness_rows_csv_path)
    print("materialized_source_missing_columns", artifacts.missing_columns_csv_path)
    print("materialized_source_candidate_join_sources", artifacts.candidate_join_sources_csv_path)
    print("materialized_source_rebuild_plan", artifacts.rebuild_plan_csv_path)
    print("materialized_source_readiness_summary", artifacts.summary_csv_path)
    print("materialized_source_readiness_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())