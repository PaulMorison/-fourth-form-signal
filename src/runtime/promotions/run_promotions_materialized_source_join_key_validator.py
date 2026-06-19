from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_join_key_validation"
QUEUE_FOLDER_NAME = "materialized_source_rebuild_queue"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"

QUEUE_BY_PROMOTION_FILE_NAME = "materialized_source_rebuild_queue_by_promotion.csv"
QUEUE_JOIN_PLAN_FILE_NAME = "materialized_source_join_execution_plan.csv"

JOIN_READY = "JOIN_READY"
JOIN_READY_WITH_DUPLICATE_REVIEW = "JOIN_READY_WITH_DUPLICATE_REVIEW"
JOIN_BLOCKED_LOW_COVERAGE = "JOIN_BLOCKED_LOW_COVERAGE"
JOIN_BLOCKED_ROW_EXPLOSION_RISK = "JOIN_BLOCKED_ROW_EXPLOSION_RISK"
JOIN_BLOCKED_MISSING_KEYS = "JOIN_BLOCKED_MISSING_KEYS"
JOIN_SOURCE_NOT_AVAILABLE = "JOIN_SOURCE_NOT_AVAILABLE"

SOURCE_ROLE_ACTUAL_OUTCOME = "ACTUAL_OUTCOME"
SOURCE_ROLE_OPERATOR_AUDIT = "OPERATOR_AUDIT"

ACTION_JOIN_ACTUAL_OUTCOME_SOURCE = "JOIN_ACTUAL_OUTCOME_SOURCE"
ACTION_JOIN_OPERATOR_AUDIT_SOURCE = "JOIN_OPERATOR_AUDIT_SOURCE"

DISCOVERY_SOURCE_QUEUE_PLAN = "QUEUE_PLAN_SOURCE"
DISCOVERY_SOURCE_PROMOTION_SCOPED_GOVERNED_FILE = "PROMOTION_SCOPED_GOVERNED_FILE"
DISCOVERY_SOURCE_NOT_AVAILABLE = "NOT_AVAILABLE"
OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"

JOIN_KEY_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "store_number + promotion_start_date + promotion_name + sku_number",
        ("store_number", "promotion_start_date", "promotion_name", "sku_number"),
    ),
    (
        "store_number + promotion_start_date + sku_number",
        ("store_number", "promotion_start_date", "sku_number"),
    ),
    (
        "store_number + promotion_name + sku_number",
        ("store_number", "promotion_name", "sku_number"),
    ),
    (
        "store_number + sku_number",
        ("store_number", "sku_number"),
    ),
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

ROWS_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_name",
    "promotion_folder_name",
    "candidate_source_role",
    "candidate_source_path",
    "join_key_priority_rank",
    "join_key_name",
    "join_key_columns",
    "source_row_count",
    "source_unique_sku_count",
    "candidate_source_row_count",
    "candidate_source_unique_sku_count",
    "source_missing_key_row_count",
    "candidate_missing_key_row_count",
    "matched_source_rows",
    "unmatched_source_rows",
    "match_rate",
    "duplicate_key_count_source",
    "duplicate_key_count_candidate",
    "joined_row_count",
    "one_to_one_join_safe_flag",
    "many_to_one_join_risk_flag",
    "row_explosion_risk_flag",
    "join_readiness_status",
    "recommended_join_key_flag",
    "reason",
)

FAILURES_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "candidate_source_role",
    "candidate_source_path",
    "recommended_join_key",
    "failure_type",
    "source_row_number",
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
    "normalized_join_key",
    "failure_reason",
)

DUPLICATES_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "candidate_source_role",
    "candidate_source_path",
    "dataset_role",
    "recommended_join_key",
    "normalized_join_key",
    "duplicate_row_count",
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
)

PLAN_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_name",
    "promotion_folder_name",
    "candidate_source_role",
    "operator_audit_discovery_source",
    "operator_audit_source_path",
    "candidate_source_path",
    "recommended_join_key",
    "source_row_count",
    "source_unique_sku_count",
    "candidate_source_row_count",
    "candidate_source_unique_sku_count",
    "matched_source_rows",
    "unmatched_source_rows",
    "match_rate",
    "duplicate_key_count_source",
    "duplicate_key_count_candidate",
    "one_to_one_join_safe_flag",
    "many_to_one_join_risk_flag",
    "row_explosion_risk_flag",
    "join_readiness_status",
    "safe_to_execute_next_flag",
    "recommended_next_step",
    "reason",
)


class PromotionsMaterializedSourceJoinKeyValidatorError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    promotion_folder_name: str
    source_file_path: str
    source_rows_path: str
    source_manifest_path: str


@dataclass(frozen=True)
class JoinKeyEvaluation:
    promotion_key: str
    promotion_name: str
    promotion_folder_name: str
    candidate_source_role: str
    candidate_source_path: str
    join_key_priority_rank: int
    join_key_name: str
    join_key_columns: tuple[str, ...]
    source_row_count: int
    source_unique_sku_count: int
    candidate_source_row_count: int
    candidate_source_unique_sku_count: int
    source_missing_key_row_count: int
    candidate_missing_key_row_count: int
    matched_source_rows: int
    unmatched_source_rows: int
    match_rate: float
    duplicate_key_count_source: int
    duplicate_key_count_candidate: int
    joined_row_count: int
    one_to_one_join_safe_flag: int
    many_to_one_join_risk_flag: int
    row_explosion_risk_flag: int
    join_readiness_status: str
    reason: str


@dataclass(frozen=True)
class CandidateValidation:
    candidate_source_role: str
    candidate_source_path: str
    discovery_source: str
    recommended_evaluation: JoinKeyEvaluation
    evaluations: tuple[JoinKeyEvaluation, ...]


@dataclass(frozen=True)
class PromotionsMaterializedSourceJoinKeyValidatorResult:
    selected_promotion: PromotionSelection
    actual_validation: CandidateValidation
    operator_validation: CandidateValidation
    summary_frame: pd.DataFrame
    rows_frame: pd.DataFrame
    failures_frame: pd.DataFrame
    duplicates_frame: pd.DataFrame
    plan_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceJoinKeyValidatorArtifacts:
    output_root: str
    summary_csv_path: str
    rows_csv_path: str
    failures_csv_path: str
    duplicates_csv_path: str
    plan_csv_path: str
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
        normalized = f"{rounded:.12f}".rstrip("0").rstrip(".")
        return normalized
    return text.upper()


def _normalize_promotion_name(value: object) -> str:
    return re.sub(r"\s+", " ", _normalize_text(value)).strip().upper()


def _as_int(value: object) -> int:
    return int(round(float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])))


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceJoinKeyValidatorError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceJoinKeyValidatorError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceJoinKeyValidatorError(f"CSV is empty: {csv_path}")
    return frame


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _format_join_key(columns: Iterable[str]) -> str:
    return " + ".join(columns)


def _safe_to_execute_status(status: str) -> bool:
    return status in {JOIN_READY, JOIN_READY_WITH_DUPLICATE_REVIEW}


def _key_availability(frame: pd.DataFrame, columns: tuple[str, ...]) -> bool:
    return all(column in frame.columns for column in columns)


def _build_normalized_key_frame(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    key_frame = pd.DataFrame(index=frame.index)
    for column in columns:
        if column == "store_number":
            key_frame[column] = frame[column].map(_normalize_number_text)
        elif column == "sku_number":
            key_frame[column] = frame[column].map(_normalize_number_text)
        elif column == "promotion_start_date":
            key_frame[column] = frame[column].map(_normalize_date)
        elif column == "promotion_name":
            key_frame[column] = frame[column].map(_normalize_promotion_name)
        else:
            key_frame[column] = _normalize_text_series(frame[column])
    return key_frame


def _build_join_key_series(frame: pd.DataFrame, columns: tuple[str, ...]) -> tuple[pd.Series, pd.Series]:
    normalized = _build_normalized_key_frame(frame, columns)
    valid_mask = normalized.ne("").all(axis=1)
    key_series = normalized.astype(str).agg("|".join, axis=1)
    key_series = key_series.where(valid_mask, "")
    return key_series, valid_mask


def _distinct_duplicate_count(key_series: pd.Series) -> int:
    nonblank = key_series[key_series.ne("")]
    if nonblank.empty:
        return 0
    counts = nonblank.value_counts()
    return int(counts.gt(1).sum())


def _status_rank(status: str) -> int:
    ordering = {
        JOIN_READY: 0,
        JOIN_READY_WITH_DUPLICATE_REVIEW: 1,
        JOIN_BLOCKED_LOW_COVERAGE: 2,
        JOIN_BLOCKED_ROW_EXPLOSION_RISK: 3,
        JOIN_BLOCKED_MISSING_KEYS: 4,
        JOIN_SOURCE_NOT_AVAILABLE: 5,
    }
    return ordering.get(status, 99)


def _evaluate_join_key(
    *,
    selection: PromotionSelection,
    candidate_source_role: str,
    candidate_source_path: str,
    source_frame: pd.DataFrame,
    candidate_frame: pd.DataFrame,
    join_key_priority_rank: int,
    join_key_name: str,
    join_key_columns: tuple[str, ...],
) -> JoinKeyEvaluation:
    source_row_count = int(len(source_frame.index))
    source_unique_sku_count = int(
        source_frame.get("sku_number", pd.Series(dtype="object")).map(_normalize_number_text).replace("", pd.NA).dropna().nunique()
    )
    candidate_source_row_count = int(len(candidate_frame.index))
    candidate_source_unique_sku_count = int(
        candidate_frame.get("sku_number", pd.Series(dtype="object")).map(_normalize_number_text).replace("", pd.NA).dropna().nunique()
    )

    if not _key_availability(source_frame, join_key_columns) or not _key_availability(candidate_frame, join_key_columns):
        missing_columns = [
            column
            for column in join_key_columns
            if column not in source_frame.columns or column not in candidate_frame.columns
        ]
        reason = f"Required join-key columns are missing for this key: {', '.join(missing_columns)}."
        return JoinKeyEvaluation(
            promotion_key=selection.promotion_key,
            promotion_name=selection.promotion_name,
            promotion_folder_name=selection.promotion_folder_name,
            candidate_source_role=candidate_source_role,
            candidate_source_path=candidate_source_path,
            join_key_priority_rank=join_key_priority_rank,
            join_key_name=join_key_name,
            join_key_columns=join_key_columns,
            source_row_count=source_row_count,
            source_unique_sku_count=source_unique_sku_count,
            candidate_source_row_count=candidate_source_row_count,
            candidate_source_unique_sku_count=candidate_source_unique_sku_count,
            source_missing_key_row_count=source_row_count,
            candidate_missing_key_row_count=candidate_source_row_count,
            matched_source_rows=0,
            unmatched_source_rows=source_row_count,
            match_rate=0.0,
            duplicate_key_count_source=0,
            duplicate_key_count_candidate=0,
            joined_row_count=0,
            one_to_one_join_safe_flag=0,
            many_to_one_join_risk_flag=0,
            row_explosion_risk_flag=0,
            join_readiness_status=JOIN_BLOCKED_MISSING_KEYS,
            reason=reason,
        )

    source_key_series, source_valid_mask = _build_join_key_series(source_frame, join_key_columns)
    candidate_key_series, candidate_valid_mask = _build_join_key_series(candidate_frame, join_key_columns)

    source_counts = source_key_series[source_key_series.ne("")].value_counts()
    candidate_counts = candidate_key_series[candidate_key_series.ne("")].value_counts()
    matched_keys = sorted(set(source_counts.index).intersection(candidate_counts.index))

    matched_source_rows = int(source_counts[source_counts.index.isin(matched_keys)].sum()) if matched_keys else 0
    unmatched_source_rows = int(source_row_count - matched_source_rows)
    joined_row_count = int(
        sum(int(source_counts[key]) * int(candidate_counts[key]) for key in matched_keys)
    )
    source_missing_key_row_count = int((~source_valid_mask).sum())
    candidate_missing_key_row_count = int((~candidate_valid_mask).sum())
    duplicate_key_count_source = _distinct_duplicate_count(source_key_series)
    duplicate_key_count_candidate = _distinct_duplicate_count(candidate_key_series)
    match_rate = float(matched_source_rows / source_row_count) if source_row_count else 0.0

    row_explosion_risk_flag = int(joined_row_count > matched_source_rows)
    many_to_one_join_risk_flag = int(any(int(source_counts[key]) > 1 for key in matched_keys))
    one_to_one_join_safe_flag = int(
        source_missing_key_row_count == 0
        and candidate_missing_key_row_count == 0
        and match_rate >= 0.95
        and duplicate_key_count_source == 0
        and duplicate_key_count_candidate == 0
        and row_explosion_risk_flag == 0
        and matched_source_rows == source_row_count
    )

    if source_valid_mask.sum() == 0 or candidate_valid_mask.sum() == 0:
        join_readiness_status = JOIN_BLOCKED_MISSING_KEYS
        reason = "No complete join keys are available for this candidate source under the tested key."
    elif row_explosion_risk_flag:
        join_readiness_status = JOIN_BLOCKED_ROW_EXPLOSION_RISK
        reason = "Joining on this key would duplicate at least one matched source row."
    elif match_rate >= 0.95 and duplicate_key_count_source == 0 and duplicate_key_count_candidate == 0:
        join_readiness_status = JOIN_READY
        reason = "Coverage is at or above 95% and the key is row-stable on both sides."
    elif match_rate >= 0.90 and row_explosion_risk_flag == 0 and (
        duplicate_key_count_source > 0 or duplicate_key_count_candidate > 0 or many_to_one_join_risk_flag > 0
    ):
        join_readiness_status = JOIN_READY_WITH_DUPLICATE_REVIEW
        reason = "Coverage is high enough, but duplicate review is required before executing the join."
    else:
        join_readiness_status = JOIN_BLOCKED_LOW_COVERAGE
        reason = "Coverage is below the minimum threshold for a safe diagnostics-only join specification."

    return JoinKeyEvaluation(
        promotion_key=selection.promotion_key,
        promotion_name=selection.promotion_name,
        promotion_folder_name=selection.promotion_folder_name,
        candidate_source_role=candidate_source_role,
        candidate_source_path=candidate_source_path,
        join_key_priority_rank=join_key_priority_rank,
        join_key_name=join_key_name,
        join_key_columns=join_key_columns,
        source_row_count=source_row_count,
        source_unique_sku_count=source_unique_sku_count,
        candidate_source_row_count=candidate_source_row_count,
        candidate_source_unique_sku_count=candidate_source_unique_sku_count,
        source_missing_key_row_count=source_missing_key_row_count,
        candidate_missing_key_row_count=candidate_missing_key_row_count,
        matched_source_rows=matched_source_rows,
        unmatched_source_rows=unmatched_source_rows,
        match_rate=match_rate,
        duplicate_key_count_source=duplicate_key_count_source,
        duplicate_key_count_candidate=duplicate_key_count_candidate,
        joined_row_count=joined_row_count,
        one_to_one_join_safe_flag=one_to_one_join_safe_flag,
        many_to_one_join_risk_flag=many_to_one_join_risk_flag,
        row_explosion_risk_flag=row_explosion_risk_flag,
        join_readiness_status=join_readiness_status,
        reason=reason,
    )


def _pick_recommended_evaluation(evaluations: tuple[JoinKeyEvaluation, ...]) -> JoinKeyEvaluation:
    safe_evaluations = [
        evaluation
        for evaluation in evaluations
        if evaluation.join_readiness_status in {JOIN_READY, JOIN_READY_WITH_DUPLICATE_REVIEW}
    ]
    if safe_evaluations:
        return safe_evaluations[0]
    return sorted(
        evaluations,
        key=lambda evaluation: (
            _status_rank(evaluation.join_readiness_status),
            -evaluation.match_rate,
            evaluation.join_key_priority_rank,
        ),
    )[0]


def _evaluate_candidate_validation(
    *,
    selection: PromotionSelection,
    candidate_source_role: str,
    candidate_source_path: str,
    source_frame: pd.DataFrame,
) -> CandidateValidation:
    normalized_candidate_path = _normalize_text(candidate_source_path)
    if not normalized_candidate_path:
        unavailable_evaluation = JoinKeyEvaluation(
            promotion_key=selection.promotion_key,
            promotion_name=selection.promotion_name,
            promotion_folder_name=selection.promotion_folder_name,
            candidate_source_role=candidate_source_role,
            candidate_source_path=normalized_candidate_path,
            join_key_priority_rank=0,
            join_key_name="",
            join_key_columns=(),
            source_row_count=int(len(source_frame.index)),
            source_unique_sku_count=int(
                source_frame.get("sku_number", pd.Series(dtype="object")).map(_normalize_number_text).replace("", pd.NA).dropna().nunique()
            ),
            candidate_source_row_count=0,
            candidate_source_unique_sku_count=0,
            source_missing_key_row_count=0,
            candidate_missing_key_row_count=0,
            matched_source_rows=0,
            unmatched_source_rows=int(len(source_frame.index)),
            match_rate=0.0,
            duplicate_key_count_source=0,
            duplicate_key_count_candidate=0,
            joined_row_count=0,
            one_to_one_join_safe_flag=0,
            many_to_one_join_risk_flag=0,
            row_explosion_risk_flag=0,
            join_readiness_status=JOIN_SOURCE_NOT_AVAILABLE,
            reason="No candidate source path was available for this join role.",
        )
        return CandidateValidation(
            candidate_source_role=candidate_source_role,
            candidate_source_path=normalized_candidate_path,
            discovery_source=DISCOVERY_SOURCE_NOT_AVAILABLE,
            recommended_evaluation=unavailable_evaluation,
            evaluations=(unavailable_evaluation,),
        )

    candidate_path = Path(normalized_candidate_path)
    if not candidate_path.exists():
        unavailable_evaluation = JoinKeyEvaluation(
            promotion_key=selection.promotion_key,
            promotion_name=selection.promotion_name,
            promotion_folder_name=selection.promotion_folder_name,
            candidate_source_role=candidate_source_role,
            candidate_source_path=normalized_candidate_path,
            join_key_priority_rank=0,
            join_key_name="",
            join_key_columns=(),
            source_row_count=int(len(source_frame.index)),
            source_unique_sku_count=int(
                source_frame.get("sku_number", pd.Series(dtype="object")).map(_normalize_number_text).replace("", pd.NA).dropna().nunique()
            ),
            candidate_source_row_count=0,
            candidate_source_unique_sku_count=0,
            source_missing_key_row_count=0,
            candidate_missing_key_row_count=0,
            matched_source_rows=0,
            unmatched_source_rows=int(len(source_frame.index)),
            match_rate=0.0,
            duplicate_key_count_source=0,
            duplicate_key_count_candidate=0,
            joined_row_count=0,
            one_to_one_join_safe_flag=0,
            many_to_one_join_risk_flag=0,
            row_explosion_risk_flag=0,
            join_readiness_status=JOIN_SOURCE_NOT_AVAILABLE,
            reason="The candidate source path does not exist on disk.",
        )
        return CandidateValidation(
            candidate_source_role=candidate_source_role,
            candidate_source_path=normalized_candidate_path,
            discovery_source=DISCOVERY_SOURCE_NOT_AVAILABLE,
            recommended_evaluation=unavailable_evaluation,
            evaluations=(unavailable_evaluation,),
        )

    candidate_frame = _read_csv(candidate_path)
    evaluations = tuple(
        _evaluate_join_key(
            selection=selection,
            candidate_source_role=candidate_source_role,
            candidate_source_path=normalized_candidate_path,
            source_frame=source_frame,
            candidate_frame=candidate_frame,
            join_key_priority_rank=index,
            join_key_name=join_key_name,
            join_key_columns=join_key_columns,
        )
        for index, (join_key_name, join_key_columns) in enumerate(JOIN_KEY_SPECS, start=1)
    )
    return CandidateValidation(
        candidate_source_role=candidate_source_role,
        candidate_source_path=normalized_candidate_path,
        discovery_source=DISCOVERY_SOURCE_QUEUE_PLAN,
        recommended_evaluation=_pick_recommended_evaluation(evaluations),
        evaluations=evaluations,
    )


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _resolve_selected_promotion_row(
    by_promotion_frame: pd.DataFrame,
    *,
    promotion_key: str | None,
) -> pd.Series:
    if by_promotion_frame.empty:
        raise PromotionsMaterializedSourceJoinKeyValidatorError("Queue by-promotion file is empty.")
    if promotion_key:
        matches = by_promotion_frame.loc[
            by_promotion_frame["promotion_key"].astype(str).eq(promotion_key)
        ]
        if matches.empty:
            raise PromotionsMaterializedSourceJoinKeyValidatorError(
                f"Promotion key not found in queue: {promotion_key}"
            )
        return matches.iloc[0]
    sorted_frame = by_promotion_frame.sort_values(
        by=["promotion_priority_rank", "promotion_start_date", "promotion_name"],
        ascending=[True, False, True],
    )
    return sorted_frame.iloc[0]


def _find_promotion_folder(
    packet_root: Path,
    *,
    selected_row: pd.Series,
    promotion_folder: str | None,
) -> str:
    if promotion_folder:
        candidate_folder = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME / promotion_folder
        if not candidate_folder.exists():
            raise PromotionsMaterializedSourceJoinKeyValidatorError(
                f"Promotion folder not found: {candidate_folder}"
            )
        return promotion_folder

    target_store = _normalize_number_text(selected_row.get("promotion_key", "").split("|")[0])
    target_start = _normalize_date(selected_row.get("promotion_start_date"))
    target_end = _normalize_date(selected_row.get("promotion_end_date"))
    target_name = _normalize_promotion_name(selected_row.get("promotion_name"))
    source_root = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME
    for folder in sorted(candidate for candidate in source_root.iterdir() if candidate.is_dir()):
        manifest_path = folder / "promotion_source_manifest.csv"
        if not manifest_path.exists():
            continue
        manifest_frame = _read_csv(manifest_path, allow_empty=True)
        if manifest_frame.empty:
            continue
        manifest_row = manifest_frame.iloc[0]
        if (
            _normalize_number_text(manifest_row.get("store_number")) == target_store
            and _normalize_date(manifest_row.get("promotion_start_date")) == target_start
            and _normalize_date(manifest_row.get("promotion_end_date")) == target_end
            and _normalize_promotion_name(manifest_row.get("promotion_name")) == target_name
        ):
            return folder.name
    raise PromotionsMaterializedSourceJoinKeyValidatorError(
        "Could not resolve a materialized promotion folder for the selected promotion."
    )


def _resolve_selection(
    packet_root: Path,
    *,
    promotion_key: str | None,
    promotion_folder: str | None,
) -> PromotionSelection:
    queue_root = packet_root / QUEUE_FOLDER_NAME
    by_promotion_frame = _read_csv(queue_root / QUEUE_BY_PROMOTION_FILE_NAME)
    selected_row = _resolve_selected_promotion_row(by_promotion_frame, promotion_key=promotion_key)
    folder_name = _find_promotion_folder(
        packet_root,
        selected_row=selected_row,
        promotion_folder=promotion_folder,
    )
    folder_root = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME / folder_name
    manifest_path = folder_root / "promotion_source_manifest.csv"
    source_rows_path = folder_root / "promotion_source_rows.csv"
    if not source_rows_path.exists():
        raise PromotionsMaterializedSourceJoinKeyValidatorError(
            f"Source rows file not found: {source_rows_path}"
        )
    manifest_frame = _read_csv(manifest_path)
    manifest_row = manifest_frame.iloc[0]
    resolved_promotion_key = promotion_key or _normalize_text(selected_row.get("promotion_key"))
    return PromotionSelection(
        promotion_key=resolved_promotion_key,
        promotion_name=_normalize_text(selected_row.get("promotion_name")),
        promotion_start_date=_normalize_date(selected_row.get("promotion_start_date")),
        promotion_end_date=_normalize_date(selected_row.get("promotion_end_date")),
        promotion_folder_name=folder_name,
        source_file_path=_normalize_text(manifest_row.get("source_file_path"))
        or _normalize_text(selected_row.get("source_file_path")),
        source_rows_path=str(source_rows_path),
        source_manifest_path=str(manifest_path),
    )


def _candidate_source_from_join_plan(
    join_plan_frame: pd.DataFrame,
    *,
    promotion_key: str,
    required_action: str,
) -> str:
    matches = join_plan_frame.loc[
        join_plan_frame["promotion_key"].astype(str).eq(promotion_key)
        & join_plan_frame["required_action"].astype(str).eq(required_action)
    ]
    if matches.empty:
        return ""
    return _normalize_text(matches.iloc[0].get("candidate_join_source_path"))


def _promotion_scoped_operator_audit_source_path(
    packet_root: Path,
    *,
    selection: PromotionSelection,
) -> str:
    candidate_path = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME / selection.promotion_folder_name / OPERATOR_AUDIT_FILE_NAME
    if candidate_path.exists():
        return str(candidate_path)
    return ""


def _resolve_candidate_source(
    packet_root: Path,
    *,
    selection: PromotionSelection,
    join_plan_frame: pd.DataFrame,
    candidate_source_role: str,
    required_action: str,
    override_source: str | None,
) -> tuple[str, str]:
    normalized_override = _normalize_text(override_source)
    if normalized_override:
        return normalized_override, DISCOVERY_SOURCE_QUEUE_PLAN

    queue_plan_source = _candidate_source_from_join_plan(
        join_plan_frame,
        promotion_key=selection.promotion_key,
        required_action=required_action,
    )
    if queue_plan_source:
        if candidate_source_role != SOURCE_ROLE_OPERATOR_AUDIT or Path(queue_plan_source).exists():
            return queue_plan_source, DISCOVERY_SOURCE_QUEUE_PLAN

    if candidate_source_role == SOURCE_ROLE_OPERATOR_AUDIT:
        governed_source = _promotion_scoped_operator_audit_source_path(
            packet_root,
            selection=selection,
        )
        if governed_source:
            return governed_source, DISCOVERY_SOURCE_PROMOTION_SCOPED_GOVERNED_FILE

    return "", DISCOVERY_SOURCE_NOT_AVAILABLE


def _rows_from_validation(validation: CandidateValidation) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    recommended = validation.recommended_evaluation
    for evaluation in validation.evaluations:
        rows.append(
            {
                "promotion_key": evaluation.promotion_key,
                "promotion_name": evaluation.promotion_name,
                "promotion_folder_name": evaluation.promotion_folder_name,
                "candidate_source_role": evaluation.candidate_source_role,
                "operator_audit_discovery_source": (
                    validation.discovery_source if validation.candidate_source_role == SOURCE_ROLE_OPERATOR_AUDIT else ""
                ),
                "operator_audit_source_path": (
                    validation.candidate_source_path if validation.candidate_source_role == SOURCE_ROLE_OPERATOR_AUDIT else ""
                ),
                "candidate_source_path": evaluation.candidate_source_path,
                "join_key_priority_rank": evaluation.join_key_priority_rank,
                "join_key_name": evaluation.join_key_name,
                "join_key_columns": "; ".join(evaluation.join_key_columns),
                "source_row_count": evaluation.source_row_count,
                "source_unique_sku_count": evaluation.source_unique_sku_count,
                "candidate_source_row_count": evaluation.candidate_source_row_count,
                "candidate_source_unique_sku_count": evaluation.candidate_source_unique_sku_count,
                "source_missing_key_row_count": evaluation.source_missing_key_row_count,
                "candidate_missing_key_row_count": evaluation.candidate_missing_key_row_count,
                "matched_source_rows": evaluation.matched_source_rows,
                "unmatched_source_rows": evaluation.unmatched_source_rows,
                "match_rate": round(evaluation.match_rate, 6),
                "duplicate_key_count_source": evaluation.duplicate_key_count_source,
                "duplicate_key_count_candidate": evaluation.duplicate_key_count_candidate,
                "joined_row_count": evaluation.joined_row_count,
                "one_to_one_join_safe_flag": evaluation.one_to_one_join_safe_flag,
                "many_to_one_join_risk_flag": evaluation.many_to_one_join_risk_flag,
                "row_explosion_risk_flag": evaluation.row_explosion_risk_flag,
                "join_readiness_status": evaluation.join_readiness_status,
                "recommended_join_key_flag": int(
                    evaluation.join_key_name == recommended.join_key_name
                    and evaluation.join_key_priority_rank == recommended.join_key_priority_rank
                ),
                "reason": evaluation.reason,
            }
        )
    return rows


def _failures_from_validation(
    *,
    selection: PromotionSelection,
    validation: CandidateValidation,
    source_frame: pd.DataFrame,
) -> list[dict[str, object]]:
    evaluation = validation.recommended_evaluation
    failures: list[dict[str, object]] = []
    if evaluation.join_readiness_status == JOIN_SOURCE_NOT_AVAILABLE:
        failures.append(
            {
                "promotion_key": selection.promotion_key,
                "candidate_source_role": validation.candidate_source_role,
                "candidate_source_path": validation.candidate_source_path,
                "recommended_join_key": evaluation.join_key_name,
                "failure_type": "SOURCE_NOT_AVAILABLE",
                "source_row_number": "",
                "store_number": "",
                "promotion_start_date": selection.promotion_start_date,
                "promotion_name": selection.promotion_name,
                "sku_number": "",
                "normalized_join_key": "",
                "failure_reason": evaluation.reason,
            }
        )
        return failures

    candidate_frame = _read_csv(validation.candidate_source_path)
    if not evaluation.join_key_columns:
        return failures
    if not _key_availability(source_frame, evaluation.join_key_columns) or not _key_availability(candidate_frame, evaluation.join_key_columns):
        failures.append(
            {
                "promotion_key": selection.promotion_key,
                "candidate_source_role": validation.candidate_source_role,
                "candidate_source_path": validation.candidate_source_path,
                "recommended_join_key": evaluation.join_key_name,
                "failure_type": "MISSING_KEY_COLUMNS",
                "source_row_number": "",
                "store_number": "",
                "promotion_start_date": selection.promotion_start_date,
                "promotion_name": selection.promotion_name,
                "sku_number": "",
                "normalized_join_key": "",
                "failure_reason": evaluation.reason,
            }
        )
        return failures

    source_key_series, source_valid_mask = _build_join_key_series(source_frame, evaluation.join_key_columns)
    candidate_key_series, _ = _build_join_key_series(candidate_frame, evaluation.join_key_columns)
    candidate_keys = set(candidate_key_series[candidate_key_series.ne("")])
    source_rows = source_frame.reset_index(drop=True).copy()
    source_rows["_normalized_join_key"] = source_key_series.reset_index(drop=True)
    source_rows["_valid_join_key"] = source_valid_mask.reset_index(drop=True)

    for row_number, row in source_rows.iterrows():
        if not bool(row["_valid_join_key"]):
            failures.append(
                {
                    "promotion_key": selection.promotion_key,
                    "candidate_source_role": validation.candidate_source_role,
                    "candidate_source_path": validation.candidate_source_path,
                    "recommended_join_key": evaluation.join_key_name,
                    "failure_type": "MISSING_SOURCE_KEY_VALUE",
                    "source_row_number": row_number + 1,
                    "store_number": _normalize_number_text(row.get("store_number")),
                    "promotion_start_date": _normalize_date(row.get("promotion_start_date")),
                    "promotion_name": _normalize_text(row.get("promotion_name")),
                    "sku_number": _normalize_number_text(row.get("sku_number")),
                    "normalized_join_key": "",
                    "failure_reason": "At least one required key field is blank after normalization.",
                }
            )
            continue
        if row["_normalized_join_key"] not in candidate_keys:
            failures.append(
                {
                    "promotion_key": selection.promotion_key,
                    "candidate_source_role": validation.candidate_source_role,
                    "candidate_source_path": validation.candidate_source_path,
                    "recommended_join_key": evaluation.join_key_name,
                    "failure_type": "UNMATCHED_SOURCE_ROW",
                    "source_row_number": row_number + 1,
                    "store_number": _normalize_number_text(row.get("store_number")),
                    "promotion_start_date": _normalize_date(row.get("promotion_start_date")),
                    "promotion_name": _normalize_text(row.get("promotion_name")),
                    "sku_number": _normalize_number_text(row.get("sku_number")),
                    "normalized_join_key": row["_normalized_join_key"],
                    "failure_reason": "The normalized source join key was not found in the candidate source.",
                }
            )
    return failures


def _duplicates_from_validation(
    *,
    selection: PromotionSelection,
    validation: CandidateValidation,
    source_frame: pd.DataFrame,
) -> list[dict[str, object]]:
    evaluation = validation.recommended_evaluation
    if evaluation.join_readiness_status == JOIN_SOURCE_NOT_AVAILABLE or not evaluation.join_key_columns:
        return []
    if not Path(validation.candidate_source_path).exists():
        return []
    candidate_frame = _read_csv(validation.candidate_source_path)
    if not _key_availability(source_frame, evaluation.join_key_columns) or not _key_availability(candidate_frame, evaluation.join_key_columns):
        return []

    duplicate_rows: list[dict[str, object]] = []
    for dataset_role, frame in (("SOURCE", source_frame), ("CANDIDATE", candidate_frame)):
        key_series, valid_mask = _build_join_key_series(frame, evaluation.join_key_columns)
        work = frame.reset_index(drop=True).copy()
        work["_normalized_join_key"] = key_series.reset_index(drop=True)
        work = work.loc[valid_mask.reset_index(drop=True) & work["_normalized_join_key"].ne("")].copy()
        if work.empty:
            continue
        work["_duplicate_row_count"] = work.groupby("_normalized_join_key")["_normalized_join_key"].transform("size")
        duplicate_subset = work.loc[work["_duplicate_row_count"].gt(1)]
        if duplicate_subset.empty:
            continue
        duplicate_subset = duplicate_subset.drop_duplicates(subset=["_normalized_join_key"])
        for _, row in duplicate_subset.iterrows():
            duplicate_rows.append(
                {
                    "promotion_key": selection.promotion_key,
                    "candidate_source_role": validation.candidate_source_role,
                    "candidate_source_path": validation.candidate_source_path,
                    "dataset_role": dataset_role,
                    "recommended_join_key": evaluation.join_key_name,
                    "normalized_join_key": row["_normalized_join_key"],
                    "duplicate_row_count": int(row["_duplicate_row_count"]),
                    "store_number": _normalize_number_text(row.get("store_number")),
                    "promotion_start_date": _normalize_date(row.get("promotion_start_date")),
                    "promotion_name": _normalize_text(row.get("promotion_name")),
                    "sku_number": _normalize_number_text(row.get("sku_number")),
                }
            )
    return duplicate_rows


def _plan_row_from_validation(
    *,
    selection: PromotionSelection,
    validation: CandidateValidation,
) -> dict[str, object]:
    evaluation = validation.recommended_evaluation
    safe_to_execute_next_flag = int(_safe_to_execute_status(evaluation.join_readiness_status))
    if evaluation.join_readiness_status == JOIN_READY:
        recommended_next_step = "Author the diagnostics-only join spec on the recommended key without mutating the source packet."
    elif evaluation.join_readiness_status == JOIN_READY_WITH_DUPLICATE_REVIEW:
        recommended_next_step = "Review duplicate keys on the recommended key before authoring the diagnostics-only join spec."
    elif evaluation.join_readiness_status == JOIN_BLOCKED_ROW_EXPLOSION_RISK:
        recommended_next_step = "Do not author the join yet; resolve duplicate candidate keys to remove row-explosion risk."
    elif evaluation.join_readiness_status == JOIN_BLOCKED_MISSING_KEYS:
        recommended_next_step = "Restore the missing join-key fields before any join specification is attempted."
    elif evaluation.join_readiness_status == JOIN_SOURCE_NOT_AVAILABLE:
        recommended_next_step = "Locate the candidate source before validating or authoring any join spec."
    else:
        recommended_next_step = "Do not author the join yet; coverage is below threshold on the recommended key."

    return {
        "promotion_key": selection.promotion_key,
        "promotion_name": selection.promotion_name,
        "promotion_folder_name": selection.promotion_folder_name,
        "candidate_source_role": validation.candidate_source_role,
        "operator_audit_discovery_source": (
            validation.discovery_source if validation.candidate_source_role == SOURCE_ROLE_OPERATOR_AUDIT else ""
        ),
        "operator_audit_source_path": (
            validation.candidate_source_path if validation.candidate_source_role == SOURCE_ROLE_OPERATOR_AUDIT else ""
        ),
        "candidate_source_path": validation.candidate_source_path,
        "recommended_join_key": evaluation.join_key_name,
        "source_row_count": evaluation.source_row_count,
        "source_unique_sku_count": evaluation.source_unique_sku_count,
        "candidate_source_row_count": evaluation.candidate_source_row_count,
        "candidate_source_unique_sku_count": evaluation.candidate_source_unique_sku_count,
        "matched_source_rows": evaluation.matched_source_rows,
        "unmatched_source_rows": evaluation.unmatched_source_rows,
        "match_rate": round(evaluation.match_rate, 6),
        "duplicate_key_count_source": evaluation.duplicate_key_count_source,
        "duplicate_key_count_candidate": evaluation.duplicate_key_count_candidate,
        "one_to_one_join_safe_flag": evaluation.one_to_one_join_safe_flag,
        "many_to_one_join_risk_flag": evaluation.many_to_one_join_risk_flag,
        "row_explosion_risk_flag": evaluation.row_explosion_risk_flag,
        "join_readiness_status": evaluation.join_readiness_status,
        "safe_to_execute_next_flag": safe_to_execute_next_flag,
        "recommended_next_step": recommended_next_step,
        "reason": evaluation.reason,
    }


def _summary_rows(
    *,
    selection: PromotionSelection,
    actual_validation: CandidateValidation,
    operator_validation: CandidateValidation,
) -> list[dict[str, object]]:
    actual = actual_validation.recommended_evaluation
    operator = operator_validation.recommended_evaluation
    overall_best_join_key = actual.join_key_name or operator.join_key_name
    duplicate_risk = int(
        actual.duplicate_key_count_source > 0
        or actual.duplicate_key_count_candidate > 0
        or operator.duplicate_key_count_source > 0
        or operator.duplicate_key_count_candidate > 0
        or actual.many_to_one_join_risk_flag > 0
        or operator.many_to_one_join_risk_flag > 0
    )
    row_explosion_risk = int(actual.row_explosion_risk_flag > 0 or operator.row_explosion_risk_flag > 0)
    join_safe_to_execute_next = int(
        _safe_to_execute_status(actual.join_readiness_status)
        and _safe_to_execute_status(operator.join_readiness_status)
    )

    return [
        _summary_row("SELECTED_PROMOTION", selection.promotion_key, "Promotion selected for diagnostics-only join-key validation."),
        _summary_row("PROMOTION_FOLDER", selection.promotion_folder_name, "Materialized promotion folder used for the validation."),
        _summary_row("ACTUAL_SOURCE_STATUS", actual.join_readiness_status, "Recommended join-readiness status for the actual-outcome candidate source."),
        _summary_row("OPERATOR_SOURCE_STATUS", operator.join_readiness_status, "Recommended join-readiness status for the operator-audit candidate source."),
        _summary_row("OPERATOR_AUDIT_DISCOVERY_SOURCE", operator_validation.discovery_source, "How the operator-audit candidate source path was resolved for this promotion."),
        _summary_row("OPERATOR_AUDIT_SOURCE_PATH", operator_validation.candidate_source_path, "Resolved operator-audit candidate source path for this promotion."),
        _summary_row("ACTUAL_SOURCE_MATCH_RATE", round(actual.match_rate, 6), "Recommended actual-outcome join-key coverage rate."),
        _summary_row("OPERATOR_SOURCE_MATCH_RATE", round(operator.match_rate, 6), "Recommended operator-audit join-key coverage rate."),
        _summary_row("ACTUAL_RECOMMENDED_JOIN_KEY", actual.join_key_name, "Recommended actual-outcome join key."),
        _summary_row("OPERATOR_RECOMMENDED_JOIN_KEY", operator.join_key_name, "Recommended operator-audit join key."),
        _summary_row("BEST_JOIN_KEY", overall_best_join_key, "Best available join key across the required sources."),
        _summary_row("DUPLICATE_RISK_FLAG", duplicate_risk, "Whether duplicate-key review is required on any recommended join key."),
        _summary_row("ROW_EXPLOSION_RISK_FLAG", row_explosion_risk, "Whether any recommended join key would duplicate matched source rows."),
        _summary_row("JOIN_SAFE_TO_EXECUTE_NEXT_FLAG", join_safe_to_execute_next, "Whether both required sources are ready for a diagnostics-only join specification next."),
    ]


def _memo_markdown(
    *,
    selection: PromotionSelection,
    actual_validation: CandidateValidation,
    operator_validation: CandidateValidation,
    summary_frame: pd.DataFrame,
) -> str:
    metrics = _metric_lookup(summary_frame)
    actual = actual_validation.recommended_evaluation
    operator = operator_validation.recommended_evaluation
    return "\n".join(
        [
            "# Materialized Source Join-Key Validation",
            "",
            "This is not a rebuild.",
            "This is not training.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "This does not promote auto-ordering or shadow rules.",
            "This does not mutate the source packet.",
            "Missing actuals remain missing until a later governed join specification is explicitly executed.",
            "",
            "## 1. Selected promotion",
            f"Promotion key: {selection.promotion_key}",
            f"Promotion folder: {selection.promotion_folder_name}",
            "",
            "## 2. Recommended source statuses",
            f"Actual source status: {actual.join_readiness_status} on {actual.join_key_name or 'no available key'} with match rate {round(actual.match_rate, 6)}.",
            f"Operator source status: {operator.join_readiness_status} on {operator.join_key_name or 'no available key'} with match rate {round(operator.match_rate, 6)}.",
            "",
            "## 3. Risks",
            f"Duplicate risk flag: {metrics.get('DUPLICATE_RISK_FLAG', 0)}.",
            f"Row explosion risk flag: {metrics.get('ROW_EXPLOSION_RISK_FLAG', 0)}.",
            f"Join safe to execute next flag: {metrics.get('JOIN_SAFE_TO_EXECUTE_NEXT_FLAG', 0)}.",
            "",
            "## 4. Recommendation",
            (
                "Author the diagnostics-only join specification next using the recommended keys, but do not execute the full join yet."
                if _as_int(metrics.get("JOIN_SAFE_TO_EXECUTE_NEXT_FLAG", 0)) > 0
                else "Do not author or execute the join yet; resolve the blocking coverage, key, or duplicate issues first."
            ),
        ]
    ).strip()


def build_promotions_materialized_source_join_key_validator(
    *,
    packet_root: str | Path,
    promotion_key: str | None = None,
    promotion_folder: str | None = None,
    actual_source: str | None = None,
    operator_source: str | None = None,
) -> PromotionsMaterializedSourceJoinKeyValidatorResult:
    packet_root_path = Path(packet_root)
    selection = _resolve_selection(
        packet_root_path,
        promotion_key=promotion_key,
        promotion_folder=promotion_folder,
    )
    queue_root = packet_root_path / QUEUE_FOLDER_NAME
    join_plan_frame = _read_csv(queue_root / QUEUE_JOIN_PLAN_FILE_NAME)
    resolved_actual_source, actual_discovery_source = _resolve_candidate_source(
        packet_root_path,
        selection=selection,
        join_plan_frame=join_plan_frame,
        candidate_source_role=SOURCE_ROLE_ACTUAL_OUTCOME,
        required_action=ACTION_JOIN_ACTUAL_OUTCOME_SOURCE,
        override_source=actual_source,
    )
    resolved_operator_source, operator_discovery_source = _resolve_candidate_source(
        packet_root_path,
        selection=selection,
        join_plan_frame=join_plan_frame,
        candidate_source_role=SOURCE_ROLE_OPERATOR_AUDIT,
        required_action=ACTION_JOIN_OPERATOR_AUDIT_SOURCE,
        override_source=operator_source,
    )

    source_frame = _read_csv(selection.source_rows_path)
    actual_validation = _evaluate_candidate_validation(
        selection=selection,
        candidate_source_role=SOURCE_ROLE_ACTUAL_OUTCOME,
        candidate_source_path=resolved_actual_source,
        source_frame=source_frame,
    )
    actual_validation = CandidateValidation(
        candidate_source_role=actual_validation.candidate_source_role,
        candidate_source_path=actual_validation.candidate_source_path,
        discovery_source=actual_discovery_source,
        recommended_evaluation=actual_validation.recommended_evaluation,
        evaluations=actual_validation.evaluations,
    )
    operator_validation = _evaluate_candidate_validation(
        selection=selection,
        candidate_source_role=SOURCE_ROLE_OPERATOR_AUDIT,
        candidate_source_path=resolved_operator_source,
        source_frame=source_frame,
    )
    operator_validation = CandidateValidation(
        candidate_source_role=operator_validation.candidate_source_role,
        candidate_source_path=operator_validation.candidate_source_path,
        discovery_source=operator_discovery_source,
        recommended_evaluation=operator_validation.recommended_evaluation,
        evaluations=operator_validation.evaluations,
    )

    rows = _rows_from_validation(actual_validation) + _rows_from_validation(operator_validation)
    failures = _failures_from_validation(
        selection=selection,
        validation=actual_validation,
        source_frame=source_frame,
    ) + _failures_from_validation(
        selection=selection,
        validation=operator_validation,
        source_frame=source_frame,
    )
    duplicates = _duplicates_from_validation(
        selection=selection,
        validation=actual_validation,
        source_frame=source_frame,
    ) + _duplicates_from_validation(
        selection=selection,
        validation=operator_validation,
        source_frame=source_frame,
    )
    plan_rows = [
        _plan_row_from_validation(selection=selection, validation=actual_validation),
        _plan_row_from_validation(selection=selection, validation=operator_validation),
    ]
    summary_frame = pd.DataFrame(
        _summary_rows(
            selection=selection,
            actual_validation=actual_validation,
            operator_validation=operator_validation,
        ),
        columns=SUMMARY_COLUMNS,
    )

    rows_frame = pd.DataFrame(rows, columns=ROWS_COLUMNS)
    failures_frame = pd.DataFrame(failures, columns=FAILURES_COLUMNS)
    duplicates_frame = pd.DataFrame(duplicates, columns=DUPLICATES_COLUMNS)
    plan_frame = pd.DataFrame(plan_rows, columns=PLAN_COLUMNS)
    memo_markdown = _memo_markdown(
        selection=selection,
        actual_validation=actual_validation,
        operator_validation=operator_validation,
        summary_frame=summary_frame,
    )

    return PromotionsMaterializedSourceJoinKeyValidatorResult(
        selected_promotion=selection,
        actual_validation=actual_validation,
        operator_validation=operator_validation,
        summary_frame=summary_frame,
        rows_frame=rows_frame,
        failures_frame=failures_frame,
        duplicates_frame=duplicates_frame,
        plan_frame=plan_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_join_key_validator(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    promotion_key: str | None = None,
    promotion_folder: str | None = None,
    actual_source: str | None = None,
    operator_source: str | None = None,
) -> PromotionsMaterializedSourceJoinKeyValidatorArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_join_key_validator(
        packet_root=packet_root_path,
        promotion_key=promotion_key,
        promotion_folder=promotion_folder,
        actual_source=actual_source,
        operator_source=operator_source,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_root_path / "materialized_source_join_key_validation_summary.csv"
    rows_csv_path = output_root_path / "materialized_source_join_key_validation_rows.csv"
    failures_csv_path = output_root_path / "materialized_source_join_key_validation_failures.csv"
    duplicates_csv_path = output_root_path / "materialized_source_join_key_validation_duplicates.csv"
    plan_csv_path = output_root_path / "materialized_source_join_key_validation_plan.csv"
    memo_md_path = output_root_path / "materialized_source_join_key_validation_memo.md"

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.rows_frame.to_csv(rows_csv_path, index=False)
    result.failures_frame.to_csv(failures_csv_path, index=False)
    result.duplicates_frame.to_csv(duplicates_csv_path, index=False)
    result.plan_frame.to_csv(plan_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceJoinKeyValidatorArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_csv_path),
        rows_csv_path=str(rows_csv_path),
        failures_csv_path=str(failures_csv_path),
        duplicates_csv_path=str(duplicates_csv_path),
        plan_csv_path=str(plan_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only join-key coverage validator for a materialized promotion packet."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--promotion-key")
    parser.add_argument("--promotion-folder")
    parser.add_argument("--actual-source")
    parser.add_argument("--operator-source")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_join_key_validator(
        packet_root=args.packet_root,
        output_root=args.output_root,
        promotion_key=args.promotion_key,
        promotion_folder=args.promotion_folder,
        actual_source=args.actual_source,
        operator_source=args.operator_source,
    )
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary_frame)
    print("selected_promotion", _normalize_text(metrics.get("SELECTED_PROMOTION", "")))
    print("actual_source_status", _normalize_text(metrics.get("ACTUAL_SOURCE_STATUS", "")))
    print("operator_source_status", _normalize_text(metrics.get("OPERATOR_SOURCE_STATUS", "")))
    print("best_join_key", _normalize_text(metrics.get("BEST_JOIN_KEY", "")))
    print("actual_source_match_rate", _normalize_text(metrics.get("ACTUAL_SOURCE_MATCH_RATE", 0)))
    print("operator_source_match_rate", _normalize_text(metrics.get("OPERATOR_SOURCE_MATCH_RATE", 0)))
    print("duplicate_risk_flag", _normalize_text(metrics.get("DUPLICATE_RISK_FLAG", 0)))
    print("row_explosion_risk_flag", _normalize_text(metrics.get("ROW_EXPLOSION_RISK_FLAG", 0)))
    print("join_safe_to_execute_next_flag", _normalize_text(metrics.get("JOIN_SAFE_TO_EXECUTE_NEXT_FLAG", 0)))
    print("materialized_source_join_key_validation_summary", artifacts.summary_csv_path)
    print("materialized_source_join_key_validation_rows", artifacts.rows_csv_path)
    print("materialized_source_join_key_validation_failures", artifacts.failures_csv_path)
    print("materialized_source_join_key_validation_duplicates", artifacts.duplicates_csv_path)
    print("materialized_source_join_key_validation_plan", artifacts.plan_csv_path)
    print("materialized_source_join_key_validation_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())