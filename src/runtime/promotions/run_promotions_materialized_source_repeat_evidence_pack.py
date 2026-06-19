from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_repeat_evidence_pack"
CALIBRATION_CANDIDATE_PACK_FOLDER_NAME = "materialized_source_calibration_candidate_pack"
SOURCE_MATERIALIZED_PROMOTIONS_FOLDER_NAME = "source_materialized_promotions"

CANDIDATE_PACK_ROWS_FILE_NAME = "calibration_candidate_pack_rows.csv"
CANDIDATE_PACK_BY_RULE_FAMILY_FILE_NAME = "calibration_candidate_pack_by_rule_family.csv"
CANDIDATE_PACK_PRIORITY_QUEUE_FILE_NAME = "calibration_candidate_pack_priority_queue.csv"
CANDIDATE_PACK_VALIDATION_FILE_NAME = "calibration_candidate_pack_validation.csv"
CANDIDATE_PACK_QUARANTINE_FILE_NAME = "calibration_candidate_pack_quarantine_rows.csv"
PACKET_INDEX_FILE_NAME = "last5_promotions_packet_index.csv"
SOURCE_ROWS_FILE_NAME = "promotion_source_rows.csv"
SOURCE_SUMMARY_FILE_NAME = "promotion_source_summary.csv"

REPEAT_EVIDENCE_PACK_READY = "REPEAT_EVIDENCE_PACK_READY"
REPEAT_EVIDENCE_PACK_REQUIRES_MORE_RECONSTRUCTION = (
    "REPEAT_EVIDENCE_PACK_REQUIRES_MORE_RECONSTRUCTION"
)
REPEAT_EVIDENCE_PACK_BLOCKED_GUARDRAIL_FAILURE = (
    "REPEAT_EVIDENCE_PACK_BLOCKED_GUARDRAIL_FAILURE"
)
REPEAT_EVIDENCE_PACK_BLOCKED_DATA_GAP = "REPEAT_EVIDENCE_PACK_BLOCKED_DATA_GAP"

REPEAT_EVIDENCE_STRONG = "REPEAT_EVIDENCE_STRONG"
REPEAT_EVIDENCE_PRESENT_BUT_WEAK = "REPEAT_EVIDENCE_PRESENT_BUT_WEAK"
REPEAT_EVIDENCE_SINGLE_PROMOTION_ONLY = "REPEAT_EVIDENCE_SINGLE_PROMOTION_ONLY"
REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD = (
    "REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD"
)
REPEAT_EVIDENCE_BLOCKED_DATA_GAP = "REPEAT_EVIDENCE_BLOCKED_DATA_GAP"

KEEP_RESEARCH_ONLY = "KEEP_RESEARCH_ONLY"
TEST_IN_SHADOW_AFTER_MORE_PROMOTIONS = "TEST_IN_SHADOW_AFTER_MORE_PROMOTIONS"
RECONSTRUCT_MORE_PROMOTIONS_FIRST = "RECONSTRUCT_MORE_PROMOTIONS_FIRST"
DEFER_NOISY_SIGNAL = "DEFER_NOISY_SIGNAL"
BLOCKED_GUARDRAIL_OR_DATA_GAP = "BLOCKED_GUARDRAIL_OR_DATA_GAP"

STATUS_PRIORITY = {
    REPEAT_EVIDENCE_STRONG: 1,
    REPEAT_EVIDENCE_PRESENT_BUT_WEAK: 2,
    REPEAT_EVIDENCE_SINGLE_PROMOTION_ONLY: 3,
    REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD: 4,
    REPEAT_EVIDENCE_BLOCKED_DATA_GAP: 5,
}

DETAIL_CHAIN_MARKERS = (
    "model_vs_actual_review",
    "action_layer_unresolved_inspection",
    "review_overlay_packet",
    "pretrain_readiness_inspection",
)

SUMMARY_COLUMNS = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)
VALIDATION_COLUMNS = (
    "check_name",
    "check_status",
    "check_flag",
    "details",
)
ROWS_COLUMNS = (
    "rule_family_candidate",
    "selected_promotion_key",
    "evidence_promotion_key",
    "evidence_promotion_name",
    "evidence_promotion_start_date",
    "evidence_promotion_end_date",
    "source_materialized_available_flag",
    "downstream_chain_available_flag",
    "family_comparable_evidence_available_flag",
    "source_row_count",
    "source_sku_count",
    "actual_units_proxy_total",
    "expected_demand_proxy_total",
    "gross_profit_proxy_total",
    "capital_left_proxy_total",
    "selected_candidate_row_count",
    "selected_tier_1_count",
    "selected_family_priority_score",
    "repeat_evidence_status",
    "candidate_recommendation",
    "notes",
)
BY_RULE_FAMILY_COLUMNS = (
    "rule_family_candidate",
    "selected_candidate_row_count",
    "selected_tier_1_count",
    "selected_tier_2_count",
    "selected_tier_3_count",
    "selected_family_priority_score",
    "promotion_count_considered",
    "supporting_promotion_count",
    "strong_repeat_evidence_count",
    "weak_repeat_evidence_count",
    "single_promotion_only_count",
    "unavailable_needs_rebuild_count",
    "blocked_data_gap_count",
    "repeat_evidence_status",
    "candidate_recommendation",
    "more_promotion_reconstruction_should_run_next",
    "notes",
)
BY_PROMOTION_COLUMNS = (
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_materialized_available_flag",
    "downstream_chain_available_flag",
    "family_comparable_evidence_available_flag",
    "rule_family_count_considered",
    "strong_repeat_evidence_count",
    "weak_repeat_evidence_count",
    "single_promotion_only_count",
    "unavailable_needs_rebuild_count",
    "blocked_data_gap_count",
    "promotion_recommendation",
    "notes",
)
CANDIDATE_PRIORITY_COLUMNS = (
    "queue_rank",
    "rule_family_candidate",
    "overlay_category",
    "sku_number",
    "sku_description",
    "calibration_candidate_tier",
    "review_signal_score",
    "actual_gross_profit",
    "capital_left_value",
    "calibration_priority_score",
    "repeat_evidence_status",
    "candidate_recommendation",
    "supporting_promotion_count",
    "more_promotion_reconstruction_should_run_next",
    "notes",
)
MISSING_PROMOTION_EVIDENCE_COLUMNS = (
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_materialized_available_flag",
    "downstream_chain_available_flag",
    "family_comparable_evidence_available_flag",
    "impacted_rule_family_count",
    "impacted_rule_families",
    "missing_reason",
    "candidate_recommendation",
)


class PromotionsMaterializedSourceRepeatEvidencePackError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str


@dataclass(frozen=True)
class PromotionInventoryEntry:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    source_materialized_available_flag: int
    downstream_chain_available_flag: int
    family_comparable_evidence_available_flag: int
    source_row_count: int
    source_sku_count: int
    actual_units_proxy_total: float
    expected_demand_proxy_total: float
    gross_profit_proxy_total: float
    capital_left_proxy_total: float
    packet_completeness_score: int
    missing_reason: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceRepeatEvidencePackResult:
    selected_promotion: PromotionSelection
    repeat_evidence_pack_status: str
    candidate_row_count: int
    rule_family_count: int
    strong_repeat_evidence_count: int
    single_promotion_only_count: int
    unavailable_needs_rebuild_count: int
    missing_promotion_evidence_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    more_promotion_reconstruction_should_run_next: int
    rows_frame: pd.DataFrame
    by_rule_family_frame: pd.DataFrame
    by_promotion_frame: pd.DataFrame
    candidate_priority_frame: pd.DataFrame
    missing_promotion_evidence_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str
    recommendation: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceRepeatEvidencePackArtifacts:
    output_root: str
    rows_csv_path: str
    by_rule_family_csv_path: str
    by_promotion_csv_path: str
    candidate_priority_csv_path: str
    missing_promotion_evidence_csv_path: str
    validation_csv_path: str
    summary_csv_path: str
    memo_md_path: str
    selected_promotion: str
    repeat_evidence_pack_status: str
    candidate_row_count: int
    rule_family_count: int
    strong_repeat_evidence_count: int
    single_promotion_only_count: int
    unavailable_needs_rebuild_count: int
    missing_promotion_evidence_count: int
    production_guardrail_status: str
    stage12_guardrail_status: str
    more_promotion_reconstruction_should_run_next: int
    recommendation: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceRepeatEvidencePackError(
            f"CSV not found: {csv_path}"
        )
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceRepeatEvidencePackError(
            f"CSV is empty: {csv_path}"
        )
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceRepeatEvidencePackError(
            f"CSV is empty: {csv_path}"
        )
    return frame


def _to_numeric(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(
        series.map(lambda value: _normalize_text(value) or None),
        errors="coerce",
    )


def _to_int(value: object, *, default: int = 0) -> int:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return default
    return int(numeric)


def _to_float(value: object, *, default: float = 0.0) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return default
    return float(numeric)


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _validation_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
    return {
        "check_name": name,
        "check_status": status,
        "check_flag": int(flag),
        "details": details,
    }


def _check_lookup(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty or "check_name" not in frame.columns:
        return {}
    return {
        _normalize_text(row.get("check_name")): _normalize_text(row.get("check_status"))
        for row in frame.to_dict("records")
    }


def _selection_from_candidate_rows(
    rows_frame: pd.DataFrame,
    requested_promotion_key: str | None,
) -> PromotionSelection:
    if rows_frame.empty or "promotion_key" not in rows_frame.columns:
        raise PromotionsMaterializedSourceRepeatEvidencePackError(
            "Candidate rows are missing promotion_key."
        )
    keys = [
        _normalize_text(value)
        for value in rows_frame["promotion_key"].drop_duplicates().tolist()
        if _normalize_text(value)
    ]
    if not keys:
        raise PromotionsMaterializedSourceRepeatEvidencePackError(
            "Candidate rows did not contain a promotion key."
        )
    resolved_key = requested_promotion_key or keys[0]
    parts = resolved_key.split("|", 3)
    if len(parts) != 4:
        return PromotionSelection(resolved_key, "", "", "")
    return PromotionSelection(
        promotion_key=resolved_key,
        promotion_name=parts[3],
        promotion_start_date=parts[1],
        promotion_end_date=parts[2],
    )


def _filter_for_promotion(frame: pd.DataFrame, promotion_key: str) -> pd.DataFrame:
    if frame.empty or "promotion_key" not in frame.columns or not promotion_key:
        return frame.copy()
    return (
        frame.loc[frame["promotion_key"].astype(str) == promotion_key]
        .reset_index(drop=True)
        .copy()
    )


def _sample_values(values: list[str], *, limit: int = 5) -> str:
    unique_values: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in unique_values:
            continue
        unique_values.append(cleaned)
        if len(unique_values) >= limit:
            break
    return ", ".join(unique_values)


def _parse_summary_row(summary_path: Path) -> dict[str, object]:
    if not summary_path.exists():
        return {}
    summary_frame = _read_csv(summary_path)
    if summary_frame.empty:
        return {}
    return summary_frame.iloc[0].to_dict()


def _build_inventory_from_packet_index(
    *,
    packet_root: Path,
    selected_promotion_key: str,
) -> list[PromotionInventoryEntry]:
    packet_index_path = packet_root / PACKET_INDEX_FILE_NAME
    if not packet_index_path.exists():
        return []
    frame = _read_csv(packet_index_path)
    entries: list[PromotionInventoryEntry] = []
    for row in frame.to_dict("records"):
        promotion_key = _normalize_text(row.get("promotion_key"))
        if not promotion_key:
            continue
        packet_output_path = _normalize_text(row.get("packet_output_path"))
        packet_name = Path(packet_output_path).name if packet_output_path else ""
        source_packet_dir = packet_root / SOURCE_MATERIALIZED_PROMOTIONS_FOLDER_NAME / packet_name
        detailed_dir = packet_root / packet_name
        source_summary = _parse_summary_row(source_packet_dir / SOURCE_SUMMARY_FILE_NAME)
        source_materialized_available_flag = int(
            source_packet_dir.exists()
            and (source_packet_dir / SOURCE_ROWS_FILE_NAME).exists()
            and (source_packet_dir / SOURCE_SUMMARY_FILE_NAME).exists()
        )
        detailed_chain_present = detailed_dir.exists() and any(
            (detailed_dir / marker).exists() for marker in DETAIL_CHAIN_MARKERS
        )
        downstream_chain_available_flag = int(
            promotion_key == selected_promotion_key
            or _to_int(row.get("downstream_full_diagnostic_chain_available_flag")) == 1
            or detailed_chain_present
        )
        family_comparable_evidence_available_flag = int(
            promotion_key == selected_promotion_key
        )
        row_count = _to_int(source_summary.get("row_count", row.get("row_count", 0)))
        sku_count = _to_int(source_summary.get("sku_count", row.get("sku_count", 0)))
        actual_units_proxy_total = _to_float(
            source_summary.get("actual_units_proxy_total", row.get("actual_units", 0.0))
        )
        expected_demand_proxy_total = _to_float(
            source_summary.get(
                "expected_demand_proxy_total",
                row.get("expected_demand", 0.0),
            )
        )
        gross_profit_proxy_total = _to_float(
            source_summary.get(
                "gross_profit_proxy_total",
                row.get("gross_profit_represented", 0.0),
            )
        )
        capital_left_proxy_total = _to_float(
            source_summary.get(
                "capital_left_proxy_total",
                row.get("capital_left_represented", 0.0),
            )
        )
        missing_reason = ""
        if source_materialized_available_flag == 0:
            missing_reason = "Source-materialized promotion packet is missing."
        elif downstream_chain_available_flag == 0:
            missing_reason = _normalize_text(
                row.get("downstream_full_packet_reason")
            ) or "Promotion only has source-materialized rows and still needs reconstruction through the downstream governed action-layer chain."
        elif family_comparable_evidence_available_flag == 0:
            missing_reason = (
                "Downstream packet exists, but comparable family-level calibration evidence is not yet available for this promotion."
            )
        entries.append(
            PromotionInventoryEntry(
                promotion_key=promotion_key,
                promotion_name=_normalize_text(row.get("promotion_name")),
                promotion_start_date=_normalize_text(row.get("promotion_start_date")),
                promotion_end_date=_normalize_text(row.get("promotion_end_date")),
                source_materialized_available_flag=source_materialized_available_flag,
                downstream_chain_available_flag=downstream_chain_available_flag,
                family_comparable_evidence_available_flag=family_comparable_evidence_available_flag,
                source_row_count=row_count,
                source_sku_count=sku_count,
                actual_units_proxy_total=actual_units_proxy_total,
                expected_demand_proxy_total=expected_demand_proxy_total,
                gross_profit_proxy_total=gross_profit_proxy_total,
                capital_left_proxy_total=capital_left_proxy_total,
                packet_completeness_score=_to_int(row.get("packet_completeness_score", 0)),
                missing_reason=missing_reason,
            )
        )
    return entries


def _build_inventory_from_source_packets(
    *,
    packet_root: Path,
    selected_promotion_key: str,
) -> list[PromotionInventoryEntry]:
    source_root = packet_root / SOURCE_MATERIALIZED_PROMOTIONS_FOLDER_NAME
    if not source_root.exists():
        return []
    entries: list[PromotionInventoryEntry] = []
    for source_dir in sorted(child for child in source_root.iterdir() if child.is_dir()):
        summary_row = _parse_summary_row(source_dir / SOURCE_SUMMARY_FILE_NAME)
        promotion_key = _normalize_text(summary_row.get("promotion_key"))
        if not promotion_key:
            continue
        detailed_dir = packet_root / source_dir.name
        detailed_chain_present = detailed_dir.exists() and any(
            (detailed_dir / marker).exists() for marker in DETAIL_CHAIN_MARKERS
        )
        downstream_chain_available_flag = int(
            promotion_key == selected_promotion_key or detailed_chain_present
        )
        family_comparable_evidence_available_flag = int(
            promotion_key == selected_promotion_key
        )
        missing_reason = ""
        if downstream_chain_available_flag == 0:
            missing_reason = (
                "Promotion only has source-materialized rows and still needs reconstruction through the downstream governed action-layer chain."
            )
        elif family_comparable_evidence_available_flag == 0:
            missing_reason = (
                "Downstream packet exists, but comparable family-level calibration evidence is not yet available for this promotion."
            )
        parts = promotion_key.split("|", 3)
        entries.append(
            PromotionInventoryEntry(
                promotion_key=promotion_key,
                promotion_name=_normalize_text(summary_row.get("promotion_name") or (parts[3] if len(parts) == 4 else "")),
                promotion_start_date=_normalize_text(summary_row.get("promotion_start_date") or (parts[1] if len(parts) == 4 else "")),
                promotion_end_date=_normalize_text(summary_row.get("promotion_end_date") or (parts[2] if len(parts) == 4 else "")),
                source_materialized_available_flag=1,
                downstream_chain_available_flag=downstream_chain_available_flag,
                family_comparable_evidence_available_flag=family_comparable_evidence_available_flag,
                source_row_count=_to_int(summary_row.get("row_count", 0)),
                source_sku_count=_to_int(summary_row.get("sku_count", 0)),
                actual_units_proxy_total=_to_float(summary_row.get("actual_units_proxy_total", 0.0)),
                expected_demand_proxy_total=_to_float(summary_row.get("expected_demand_proxy_total", 0.0)),
                gross_profit_proxy_total=_to_float(summary_row.get("gross_profit_proxy_total", 0.0)),
                capital_left_proxy_total=_to_float(summary_row.get("capital_left_proxy_total", 0.0)),
                packet_completeness_score=_to_int(summary_row.get("packet_completeness_score", 0)),
                missing_reason=missing_reason,
            )
        )
    return entries


def _promotion_inventory(
    *,
    packet_root: Path,
    selected_promotion_key: str,
) -> list[PromotionInventoryEntry]:
    entries = _build_inventory_from_packet_index(
        packet_root=packet_root,
        selected_promotion_key=selected_promotion_key,
    )
    if not entries:
        entries = _build_inventory_from_source_packets(
            packet_root=packet_root,
            selected_promotion_key=selected_promotion_key,
        )
    if not any(entry.promotion_key == selected_promotion_key for entry in entries):
        parts = selected_promotion_key.split("|", 3)
        entries.insert(
            0,
            PromotionInventoryEntry(
                promotion_key=selected_promotion_key,
                promotion_name=parts[3] if len(parts) == 4 else "",
                promotion_start_date=parts[1] if len(parts) == 4 else "",
                promotion_end_date=parts[2] if len(parts) == 4 else "",
                source_materialized_available_flag=1,
                downstream_chain_available_flag=1,
                family_comparable_evidence_available_flag=1,
                source_row_count=0,
                source_sku_count=0,
                actual_units_proxy_total=0.0,
                expected_demand_proxy_total=0.0,
                gross_profit_proxy_total=0.0,
                capital_left_proxy_total=0.0,
                packet_completeness_score=0,
                missing_reason="",
            ),
        )
    return entries


def _family_repeat_status(
    *,
    selected_family_row: dict[str, object],
    other_rows: list[dict[str, object]],
) -> tuple[str, str, int, str]:
    strong_count = sum(
        row["repeat_evidence_status"] == REPEAT_EVIDENCE_STRONG for row in other_rows
    )
    weak_count = sum(
        row["repeat_evidence_status"] == REPEAT_EVIDENCE_PRESENT_BUT_WEAK for row in other_rows
    )
    unavailable_count = sum(
        row["repeat_evidence_status"] == REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD
        for row in other_rows
    )
    blocked_count = sum(
        row["repeat_evidence_status"] == REPEAT_EVIDENCE_BLOCKED_DATA_GAP
        for row in other_rows
    )
    supporting_promotion_count = 1 + strong_count + weak_count
    readiness_tier = _normalize_text(selected_family_row.get("family_readiness_tier"))
    if strong_count > 0:
        return (
            REPEAT_EVIDENCE_STRONG,
            TEST_IN_SHADOW_AFTER_MORE_PROMOTIONS,
            supporting_promotion_count,
            "Family shows repeat evidence across more than one promotion and can stay on the diagnostics-only path toward later shadow testing.",
        )
    if weak_count > 0:
        recommendation = (
            KEEP_RESEARCH_ONLY
            if readiness_tier != "CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY"
            else DEFER_NOISY_SIGNAL
        )
        return (
            REPEAT_EVIDENCE_PRESENT_BUT_WEAK,
            recommendation,
            supporting_promotion_count,
            "Family shows some cross-promotion support, but the evidence is still weak and should remain research-only.",
        )
    if unavailable_count > 0:
        return (
            REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD,
            RECONSTRUCT_MORE_PROMOTIONS_FIRST,
            supporting_promotion_count,
            "Other materialised promotions exist, but they do not yet have comparable downstream evidence for this family.",
        )
    if blocked_count > 0:
        return (
            REPEAT_EVIDENCE_BLOCKED_DATA_GAP,
            BLOCKED_GUARDRAIL_OR_DATA_GAP,
            supporting_promotion_count,
            "Comparable downstream evidence is blocked by data gaps for this family.",
        )
    recommendation = (
        KEEP_RESEARCH_ONLY
        if readiness_tier != "CALIBRATION_CANDIDATE_TIER_3_OPERATOR_REVIEW_ONLY"
        else DEFER_NOISY_SIGNAL
    )
    return (
        REPEAT_EVIDENCE_SINGLE_PROMOTION_ONLY,
        recommendation,
        supporting_promotion_count,
        "Only the selected promotion currently contributes comparable evidence for this family.",
    )


def _selected_promotion_row(
    *,
    selected_promotion_key: str,
    selected_family_row: dict[str, object],
    selected_promotion: PromotionSelection,
) -> dict[str, object]:
    return {
        "rule_family_candidate": _normalize_text(selected_family_row.get("rule_family_candidate")),
        "selected_promotion_key": selected_promotion_key,
        "evidence_promotion_key": selected_promotion_key,
        "evidence_promotion_name": selected_promotion.promotion_name,
        "evidence_promotion_start_date": selected_promotion.promotion_start_date,
        "evidence_promotion_end_date": selected_promotion.promotion_end_date,
        "source_materialized_available_flag": 1,
        "downstream_chain_available_flag": 1,
        "family_comparable_evidence_available_flag": 1,
        "source_row_count": 0,
        "source_sku_count": 0,
        "actual_units_proxy_total": 0.0,
        "expected_demand_proxy_total": 0.0,
        "gross_profit_proxy_total": 0.0,
        "capital_left_proxy_total": 0.0,
        "selected_candidate_row_count": _to_int(selected_family_row.get("candidate_row_count", 0)),
        "selected_tier_1_count": _to_int(selected_family_row.get("tier_1_count", 0)),
        "selected_family_priority_score": _to_float(selected_family_row.get("family_priority_score", 0.0)),
        "repeat_evidence_status": REPEAT_EVIDENCE_SINGLE_PROMOTION_ONLY,
        "candidate_recommendation": KEEP_RESEARCH_ONLY,
        "notes": "Selected-promotion baseline evidence from the diagnostics-only calibration candidate pack.",
    }


def _other_promotion_row(
    *,
    selected_promotion_key: str,
    selected_family_row: dict[str, object],
    entry: PromotionInventoryEntry,
) -> dict[str, object]:
    if entry.source_materialized_available_flag == 0:
        status = REPEAT_EVIDENCE_BLOCKED_DATA_GAP
        recommendation = BLOCKED_GUARDRAIL_OR_DATA_GAP
        notes = entry.missing_reason or "Source-materialized promotion packet is missing."
    elif entry.downstream_chain_available_flag == 0:
        status = REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD
        recommendation = RECONSTRUCT_MORE_PROMOTIONS_FIRST
        notes = entry.missing_reason or "Source-only promotion still needs downstream reconstruction before repeat evidence can be evaluated."
    elif entry.family_comparable_evidence_available_flag == 0:
        status = REPEAT_EVIDENCE_BLOCKED_DATA_GAP
        recommendation = BLOCKED_GUARDRAIL_OR_DATA_GAP
        notes = entry.missing_reason or "Comparable family-level evidence is not yet available."
    else:
        status = REPEAT_EVIDENCE_PRESENT_BUT_WEAK
        recommendation = KEEP_RESEARCH_ONLY
        notes = "Comparable downstream evidence exists, but the family-level signal is still weak."
    return {
        "rule_family_candidate": _normalize_text(selected_family_row.get("rule_family_candidate")),
        "selected_promotion_key": selected_promotion_key,
        "evidence_promotion_key": entry.promotion_key,
        "evidence_promotion_name": entry.promotion_name,
        "evidence_promotion_start_date": entry.promotion_start_date,
        "evidence_promotion_end_date": entry.promotion_end_date,
        "source_materialized_available_flag": entry.source_materialized_available_flag,
        "downstream_chain_available_flag": entry.downstream_chain_available_flag,
        "family_comparable_evidence_available_flag": entry.family_comparable_evidence_available_flag,
        "source_row_count": entry.source_row_count,
        "source_sku_count": entry.source_sku_count,
        "actual_units_proxy_total": entry.actual_units_proxy_total,
        "expected_demand_proxy_total": entry.expected_demand_proxy_total,
        "gross_profit_proxy_total": entry.gross_profit_proxy_total,
        "capital_left_proxy_total": entry.capital_left_proxy_total,
        "selected_candidate_row_count": _to_int(selected_family_row.get("candidate_row_count", 0)),
        "selected_tier_1_count": _to_int(selected_family_row.get("tier_1_count", 0)),
        "selected_family_priority_score": _to_float(selected_family_row.get("family_priority_score", 0.0)),
        "repeat_evidence_status": status,
        "candidate_recommendation": recommendation,
        "notes": notes,
    }


def _build_rows_frame(
    *,
    selected_promotion: PromotionSelection,
    by_rule_family_frame: pd.DataFrame,
    inventory: list[PromotionInventoryEntry],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for family_row in by_rule_family_frame.to_dict("records"):
        rows.append(
            _selected_promotion_row(
                selected_promotion_key=selected_promotion.promotion_key,
                selected_family_row=family_row,
                selected_promotion=selected_promotion,
            )
        )
        for entry in inventory:
            if entry.promotion_key == selected_promotion.promotion_key:
                continue
            rows.append(
                _other_promotion_row(
                    selected_promotion_key=selected_promotion.promotion_key,
                    selected_family_row=family_row,
                    entry=entry,
                )
            )
    frame = pd.DataFrame(rows, columns=ROWS_COLUMNS)
    if frame.empty:
        return frame
    frame["_status_rank"] = frame["repeat_evidence_status"].map(STATUS_PRIORITY).fillna(99)
    frame = frame.sort_values(
        by=["rule_family_candidate", "_status_rank", "evidence_promotion_start_date", "evidence_promotion_key"],
        ascending=[True, True, True, True],
        kind="stable",
    ).drop(columns=["_status_rank"]).reset_index(drop=True)
    return frame


def _build_by_rule_family_frame(rows_frame: pd.DataFrame, by_rule_family_frame: pd.DataFrame) -> pd.DataFrame:
    if by_rule_family_frame.empty:
        return pd.DataFrame(columns=BY_RULE_FAMILY_COLUMNS)
    rows: list[dict[str, object]] = []
    for family_row in by_rule_family_frame.to_dict("records"):
        rule_family = _normalize_text(family_row.get("rule_family_candidate"))
        family_rows = rows_frame.loc[
            rows_frame["rule_family_candidate"].astype(str) == rule_family
        ].reset_index(drop=True)
        other_rows = family_rows.loc[
            family_rows["evidence_promotion_key"].astype(str)
            != family_rows["selected_promotion_key"].astype(str)
        ].to_dict("records")
        repeat_status, recommendation, supporting_promotion_count, notes = _family_repeat_status(
            selected_family_row=family_row,
            other_rows=other_rows,
        )
        strong_count = int(family_rows["repeat_evidence_status"].eq(REPEAT_EVIDENCE_STRONG).sum())
        weak_count = int(
            family_rows["repeat_evidence_status"].eq(REPEAT_EVIDENCE_PRESENT_BUT_WEAK).sum()
        )
        single_count = int(
            family_rows["repeat_evidence_status"].eq(REPEAT_EVIDENCE_SINGLE_PROMOTION_ONLY).sum()
        )
        unavailable_count = int(
            family_rows["repeat_evidence_status"].eq(REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD).sum()
        )
        blocked_count = int(
            family_rows["repeat_evidence_status"].eq(REPEAT_EVIDENCE_BLOCKED_DATA_GAP).sum()
        )
        rows.append(
            {
                "rule_family_candidate": rule_family,
                "selected_candidate_row_count": _to_int(family_row.get("candidate_row_count", 0)),
                "selected_tier_1_count": _to_int(family_row.get("tier_1_count", 0)),
                "selected_tier_2_count": _to_int(family_row.get("tier_2_count", 0)),
                "selected_tier_3_count": _to_int(family_row.get("tier_3_count", 0)),
                "selected_family_priority_score": _to_float(family_row.get("family_priority_score", 0.0)),
                "promotion_count_considered": len(family_rows.index),
                "supporting_promotion_count": supporting_promotion_count,
                "strong_repeat_evidence_count": strong_count,
                "weak_repeat_evidence_count": weak_count,
                "single_promotion_only_count": single_count,
                "unavailable_needs_rebuild_count": unavailable_count,
                "blocked_data_gap_count": blocked_count,
                "repeat_evidence_status": repeat_status,
                "candidate_recommendation": recommendation,
                "more_promotion_reconstruction_should_run_next": int(
                    repeat_status in {
                        REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD,
                        REPEAT_EVIDENCE_BLOCKED_DATA_GAP,
                    }
                ),
                "notes": notes,
            }
        )
    frame = pd.DataFrame(rows, columns=BY_RULE_FAMILY_COLUMNS)
    frame["_status_rank"] = frame["repeat_evidence_status"].map(STATUS_PRIORITY).fillna(99)
    frame = frame.sort_values(
        by=["_status_rank", "selected_family_priority_score", "rule_family_candidate"],
        ascending=[True, False, True],
        kind="stable",
    ).drop(columns=["_status_rank"]).reset_index(drop=True)
    return frame


def _build_by_promotion_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=BY_PROMOTION_COLUMNS)
    rows: list[dict[str, object]] = []
    for promotion_key, group in rows_frame.groupby("evidence_promotion_key", sort=False):
        strong_count = int(group["repeat_evidence_status"].eq(REPEAT_EVIDENCE_STRONG).sum())
        weak_count = int(
            group["repeat_evidence_status"].eq(REPEAT_EVIDENCE_PRESENT_BUT_WEAK).sum()
        )
        single_count = int(
            group["repeat_evidence_status"].eq(REPEAT_EVIDENCE_SINGLE_PROMOTION_ONLY).sum()
        )
        unavailable_count = int(
            group["repeat_evidence_status"].eq(REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD).sum()
        )
        blocked_count = int(
            group["repeat_evidence_status"].eq(REPEAT_EVIDENCE_BLOCKED_DATA_GAP).sum()
        )
        if unavailable_count > 0:
            promotion_recommendation = RECONSTRUCT_MORE_PROMOTIONS_FIRST
            notes = "Promotion exists as a source-materialized packet but still needs downstream reconstruction for comparable repeat-evidence work."
        elif blocked_count > 0:
            promotion_recommendation = BLOCKED_GUARDRAIL_OR_DATA_GAP
            notes = "Promotion has a downstream or data-gap blocker for comparable family-level evidence."
        elif strong_count > 0:
            promotion_recommendation = TEST_IN_SHADOW_AFTER_MORE_PROMOTIONS
            notes = "Promotion contributes strong repeat evidence."
        else:
            promotion_recommendation = KEEP_RESEARCH_ONLY
            notes = "Promotion contributes only baseline or weak repeat evidence."
        rows.append(
            {
                "promotion_key": _normalize_text(promotion_key),
                "promotion_name": _normalize_text(group.iloc[0]["evidence_promotion_name"]),
                "promotion_start_date": _normalize_text(group.iloc[0]["evidence_promotion_start_date"]),
                "promotion_end_date": _normalize_text(group.iloc[0]["evidence_promotion_end_date"]),
                "source_materialized_available_flag": _to_int(group.iloc[0]["source_materialized_available_flag"]),
                "downstream_chain_available_flag": _to_int(group.iloc[0]["downstream_chain_available_flag"]),
                "family_comparable_evidence_available_flag": _to_int(group.iloc[0]["family_comparable_evidence_available_flag"]),
                "rule_family_count_considered": len(group.index),
                "strong_repeat_evidence_count": strong_count,
                "weak_repeat_evidence_count": weak_count,
                "single_promotion_only_count": single_count,
                "unavailable_needs_rebuild_count": unavailable_count,
                "blocked_data_gap_count": blocked_count,
                "promotion_recommendation": promotion_recommendation,
                "notes": notes,
            }
        )
    frame = pd.DataFrame(rows, columns=BY_PROMOTION_COLUMNS)
    return frame.sort_values(
        by=["unavailable_needs_rebuild_count", "blocked_data_gap_count", "promotion_start_date", "promotion_key"],
        ascending=[False, False, True, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_candidate_priority_frame(
    candidate_priority_input_frame: pd.DataFrame,
    by_rule_family_frame: pd.DataFrame,
) -> pd.DataFrame:
    if candidate_priority_input_frame.empty:
        return pd.DataFrame(columns=CANDIDATE_PRIORITY_COLUMNS)
    lookup = by_rule_family_frame.set_index("rule_family_candidate").to_dict("index")
    rows: list[dict[str, object]] = []
    for row in candidate_priority_input_frame.to_dict("records"):
        rule_family = _normalize_text(row.get("rule_family_candidate"))
        family_row = lookup.get(rule_family, {})
        rows.append(
            {
                "queue_rank": _to_int(row.get("queue_rank", 0)),
                "rule_family_candidate": rule_family,
                "overlay_category": _normalize_text(row.get("overlay_category")),
                "sku_number": _normalize_text(row.get("sku_number")),
                "sku_description": _normalize_text(row.get("sku_description")),
                "calibration_candidate_tier": _normalize_text(row.get("calibration_candidate_tier")),
                "review_signal_score": _to_float(row.get("review_signal_score", 0.0)),
                "actual_gross_profit": _to_float(row.get("actual_gross_profit", 0.0)),
                "capital_left_value": _to_float(row.get("capital_left_value", 0.0)),
                "calibration_priority_score": _to_float(row.get("calibration_priority_score", 0.0)),
                "repeat_evidence_status": _normalize_text(family_row.get("repeat_evidence_status")),
                "candidate_recommendation": _normalize_text(family_row.get("candidate_recommendation")),
                "supporting_promotion_count": _to_int(family_row.get("supporting_promotion_count", 1)),
                "more_promotion_reconstruction_should_run_next": _to_int(
                    family_row.get("more_promotion_reconstruction_should_run_next", 0)
                ),
                "notes": _normalize_text(family_row.get("notes")),
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_PRIORITY_COLUMNS).sort_values(
        by=["queue_rank", "rule_family_candidate", "sku_number"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_missing_promotion_evidence_frame(
    by_promotion_frame: pd.DataFrame,
    by_rule_family_frame: pd.DataFrame,
    *,
    selected_promotion_key: str,
) -> pd.DataFrame:
    if by_promotion_frame.empty:
        return pd.DataFrame(columns=MISSING_PROMOTION_EVIDENCE_COLUMNS)
    impacted_rule_families = by_rule_family_frame.loc[
        by_rule_family_frame["repeat_evidence_status"].isin(
            [REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD, REPEAT_EVIDENCE_BLOCKED_DATA_GAP]
        ),
        "rule_family_candidate",
    ].astype(str).tolist()
    rows: list[dict[str, object]] = []
    for row in by_promotion_frame.to_dict("records"):
        promotion_key = _normalize_text(row.get("promotion_key"))
        if promotion_key == selected_promotion_key:
            continue
        unavailable = _to_int(row.get("unavailable_needs_rebuild_count", 0)) > 0
        blocked = _to_int(row.get("blocked_data_gap_count", 0)) > 0
        if not unavailable and not blocked:
            continue
        rows.append(
            {
                "promotion_key": promotion_key,
                "promotion_name": _normalize_text(row.get("promotion_name")),
                "promotion_start_date": _normalize_text(row.get("promotion_start_date")),
                "promotion_end_date": _normalize_text(row.get("promotion_end_date")),
                "source_materialized_available_flag": _to_int(row.get("source_materialized_available_flag", 0)),
                "downstream_chain_available_flag": _to_int(row.get("downstream_chain_available_flag", 0)),
                "family_comparable_evidence_available_flag": _to_int(
                    row.get("family_comparable_evidence_available_flag", 0)
                ),
                "impacted_rule_family_count": len(impacted_rule_families),
                "impacted_rule_families": ", ".join(impacted_rule_families),
                "missing_reason": _normalize_text(row.get("notes")),
                "candidate_recommendation": (
                    RECONSTRUCT_MORE_PROMOTIONS_FIRST if unavailable else BLOCKED_GUARDRAIL_OR_DATA_GAP
                ),
            }
        )
    return pd.DataFrame(rows, columns=MISSING_PROMOTION_EVIDENCE_COLUMNS).sort_values(
        by=["promotion_start_date", "promotion_key"],
        ascending=[True, True],
        kind="stable",
    ).reset_index(drop=True)


def build_promotions_materialized_source_repeat_evidence_pack(
    *,
    packet_root: str | Path,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceRepeatEvidencePackResult:
    packet_root_path = Path(packet_root)
    candidate_root = packet_root_path / CALIBRATION_CANDIDATE_PACK_FOLDER_NAME

    candidate_rows_frame = _read_csv(candidate_root / CANDIDATE_PACK_ROWS_FILE_NAME)
    candidate_by_rule_family_frame = _read_csv(
        candidate_root / CANDIDATE_PACK_BY_RULE_FAMILY_FILE_NAME
    )
    candidate_priority_input_frame = _read_csv(
        candidate_root / CANDIDATE_PACK_PRIORITY_QUEUE_FILE_NAME
    )
    candidate_validation_frame = _read_csv(
        candidate_root / CANDIDATE_PACK_VALIDATION_FILE_NAME
    )
    candidate_quarantine_frame = _read_csv(
        candidate_root / CANDIDATE_PACK_QUARANTINE_FILE_NAME,
        allow_empty=True,
    )

    selected_promotion = _selection_from_candidate_rows(
        candidate_rows_frame,
        promotion_key,
    )
    candidate_rows_frame = _filter_for_promotion(
        candidate_rows_frame,
        selected_promotion.promotion_key,
    )
    candidate_quarantine_frame = _filter_for_promotion(
        candidate_quarantine_frame,
        selected_promotion.promotion_key,
    )

    inventory = _promotion_inventory(
        packet_root=packet_root_path,
        selected_promotion_key=selected_promotion.promotion_key,
    )
    rows_frame = _build_rows_frame(
        selected_promotion=selected_promotion,
        by_rule_family_frame=candidate_by_rule_family_frame,
        inventory=inventory,
    )
    by_rule_family_frame = _build_by_rule_family_frame(
        rows_frame,
        candidate_by_rule_family_frame,
    )
    by_promotion_frame = _build_by_promotion_frame(rows_frame)
    candidate_priority_frame = _build_candidate_priority_frame(
        candidate_priority_input_frame,
        by_rule_family_frame,
    )
    missing_promotion_evidence_frame = _build_missing_promotion_evidence_frame(
        by_promotion_frame,
        by_rule_family_frame,
        selected_promotion_key=selected_promotion.promotion_key,
    )

    validation_lookup = _check_lookup(candidate_validation_frame)
    candidate_row_count = len(candidate_rows_frame.index)
    rule_family_count = len(candidate_by_rule_family_frame.index)
    input_review_surface_rows = int(
        _to_numeric(candidate_by_rule_family_frame.get("review_row_count")).fillna(0).sum()
    )
    strong_repeat_evidence_count = int(
        by_rule_family_frame.get("repeat_evidence_status", pd.Series(dtype="object"))
        .eq(REPEAT_EVIDENCE_STRONG)
        .sum()
    )
    single_promotion_only_count = int(
        by_rule_family_frame.get("repeat_evidence_status", pd.Series(dtype="object"))
        .eq(REPEAT_EVIDENCE_SINGLE_PROMOTION_ONLY)
        .sum()
    )
    unavailable_needs_rebuild_count = int(
        by_rule_family_frame.get("repeat_evidence_status", pd.Series(dtype="object"))
        .eq(REPEAT_EVIDENCE_UNAVAILABLE_NEEDS_REBUILD)
        .sum()
    )
    blocked_data_gap_count = int(
        by_rule_family_frame.get("repeat_evidence_status", pd.Series(dtype="object"))
        .eq(REPEAT_EVIDENCE_BLOCKED_DATA_GAP)
        .sum()
    )
    missing_promotion_evidence_count = len(missing_promotion_evidence_frame.index)
    production_guardrail_status = (
        "PASS"
        if validation_lookup.get("PRODUCTION_GUARDRAIL_PASS", "FAIL") == "PASS"
        else "FAIL"
    )
    stage12_guardrail_status = (
        "PASS"
        if validation_lookup.get("STAGE12_GUARDRAIL_PASS", "FAIL") == "PASS"
        else "FAIL"
    )
    candidate_pack_status_acceptable_flag = int(
        validation_lookup.get("PRODUCTION_GUARDRAIL_PASS", "FAIL") == "PASS"
        and validation_lookup.get("STAGE12_GUARDRAIL_PASS", "FAIL") == "PASS"
        and validation_lookup.get("NO_ORDER_RECOMMENDATION_FIELDS_GENERATED", "FAIL") == "PASS"
        and candidate_row_count > 0
    )
    no_quarantine_rows_included_flag = int(
        _to_numeric(candidate_rows_frame.get("quarantine_flag")).fillna(0).eq(0).all()
        and candidate_quarantine_frame.empty
    )
    more_promotion_reconstruction_should_run_next = int(
        unavailable_needs_rebuild_count > 0 or blocked_data_gap_count > 0
    )

    if production_guardrail_status != "PASS" or stage12_guardrail_status != "PASS":
        repeat_evidence_pack_status = REPEAT_EVIDENCE_PACK_BLOCKED_GUARDRAIL_FAILURE
    elif candidate_pack_status_acceptable_flag == 0:
        repeat_evidence_pack_status = REPEAT_EVIDENCE_PACK_BLOCKED_DATA_GAP
    elif more_promotion_reconstruction_should_run_next:
        repeat_evidence_pack_status = REPEAT_EVIDENCE_PACK_REQUIRES_MORE_RECONSTRUCTION
    else:
        repeat_evidence_pack_status = REPEAT_EVIDENCE_PACK_READY

    if repeat_evidence_pack_status == REPEAT_EVIDENCE_PACK_BLOCKED_GUARDRAIL_FAILURE:
        recommendation = (
            "Keep repeat-evidence work blocked until upstream guardrail failures are repaired."
        )
    elif repeat_evidence_pack_status == REPEAT_EVIDENCE_PACK_BLOCKED_DATA_GAP:
        recommendation = (
            "Keep repeat-evidence work blocked until the upstream candidate-pack data gaps are repaired."
        )
    elif more_promotion_reconstruction_should_run_next:
        recommendation = (
            "Run more promotion reconstruction next. Do not invent repeat evidence for source-only promotions; rebuild their downstream governed action-layer chain first."
        )
    elif strong_repeat_evidence_count > 0:
        recommendation = (
            "Keep the strongest families on a diagnostics-only research path and consider shadow testing only after more promotions confirm the pattern."
        )
    else:
        recommendation = (
            "Keep these families research-only for now because repeat evidence is still limited."
        )

    validation_frame = pd.DataFrame(
        [
            _validation_row(
                "CANDIDATE_PACK_STATUS_ACCEPTABLE",
                "PASS" if candidate_pack_status_acceptable_flag else "FAIL",
                candidate_pack_status_acceptable_flag,
                "Derived from the upstream candidate-pack validation and candidate-row presence.",
            ),
            _validation_row(
                "INPUT_REVIEW_SURFACE_ROWS",
                "PASS" if input_review_surface_rows == 108 else "FAIL",
                int(input_review_surface_rows == 108),
                f"input_review_surface_rows={input_review_surface_rows}",
            ),
            _validation_row(
                "NO_QUARANTINE_ROWS_INCLUDED",
                "PASS" if no_quarantine_rows_included_flag else "FAIL",
                no_quarantine_rows_included_flag,
                "Candidate rows exclude quarantine row 48.",
            ),
            _validation_row(
                "PRODUCTION_GUARDRAIL_PASS",
                production_guardrail_status,
                int(production_guardrail_status == "PASS"),
                f"production_guardrail_status={production_guardrail_status}",
            ),
            _validation_row(
                "STAGE12_GUARDRAIL_PASS",
                stage12_guardrail_status,
                int(stage12_guardrail_status == "PASS"),
                f"stage12_guardrail_status={stage12_guardrail_status}",
            ),
            _validation_row(
                "NO_RECALIBRATION_EXECUTED",
                "PASS",
                1,
                "This runtime inspects evidence only and does not recalibrate.",
            ),
            _validation_row(
                "NO_SHADOW_SIMULATION_EXECUTED",
                "PASS",
                1,
                "This runtime does not run shadow-vs-baseline simulation.",
            ),
            _validation_row(
                "NO_TRAINING_EXECUTED",
                "PASS",
                1,
                "This runtime does not start training.",
            ),
            _validation_row(
                "REPEAT_EVIDENCE_ROWS_WRITTEN",
                "PASS" if not rows_frame.empty else "FAIL",
                int(not rows_frame.empty),
                f"repeat_evidence_rows={len(rows_frame.index)}",
            ),
            _validation_row(
                "MISSING_PROMOTION_EVIDENCE_RECORDED",
                "PASS" if missing_promotion_evidence_count >= 0 else "FAIL",
                1,
                f"missing_promotion_evidence_count={missing_promotion_evidence_count}",
            ),
        ],
        columns=VALIDATION_COLUMNS,
    )

    summary_frame = pd.DataFrame(
        [
            _summary_row(
                "SELECTED_PROMOTION",
                selected_promotion.promotion_key,
                "Promotion selected for the diagnostics-only repeat-evidence pack.",
            ),
            _summary_row(
                "REPEAT_EVIDENCE_PACK_STATUS",
                repeat_evidence_pack_status,
                "Overall diagnostics-only repeat-evidence pack status.",
            ),
            _summary_row(
                "CANDIDATE_ROW_COUNT",
                candidate_row_count,
                "Rows carried from the calibration candidate pack.",
            ),
            _summary_row(
                "RULE_FAMILY_COUNT",
                rule_family_count,
                "Candidate rule families evaluated for repeat evidence.",
            ),
            _summary_row(
                "STRONG_REPEAT_EVIDENCE_COUNT",
                strong_repeat_evidence_count,
                "Rule families with strong repeat evidence across more than one promotion.",
            ),
            _summary_row(
                "SINGLE_PROMOTION_ONLY_COUNT",
                single_promotion_only_count,
                "Rule families supported only by the selected promotion.",
            ),
            _summary_row(
                "UNAVAILABLE_NEEDS_REBUILD_COUNT",
                unavailable_needs_rebuild_count,
                "Rule families blocked by missing downstream reconstruction on other promotions.",
            ),
            _summary_row(
                "MISSING_PROMOTION_EVIDENCE_COUNT",
                missing_promotion_evidence_count,
                "Promotions explicitly recorded as missing comparable repeat evidence.",
            ),
            _summary_row(
                "PRODUCTION_GUARDRAIL_STATUS",
                production_guardrail_status,
                "Production ordering logic remains unchanged.",
            ),
            _summary_row(
                "STAGE12_GUARDRAIL_STATUS",
                stage12_guardrail_status,
                "Stage 12 remains unchanged.",
            ),
            _summary_row(
                "MORE_PROMOTION_RECONSTRUCTION_SHOULD_RUN_NEXT",
                more_promotion_reconstruction_should_run_next,
                "Whether more promotions should be reconstructed before repeat-evidence work can strengthen.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Repeat-Evidence Pack",
            "",
            "This is a diagnostics-only repeat-evidence pack for calibration candidates across materialised promotions.",
            "This does not recalibrate action-layer logic.",
            "This does not run shadow-vs-baseline simulation.",
            "This does not start training.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "This does not promote auto-ordering.",
            "This does not promote shadow rules.",
            "This does not mutate source packets.",
            "This does not fill missing actuals with zero.",
            "This keeps quarantine row 48 separate.",
            "",
            f"Selected promotion: {selected_promotion.promotion_key}",
            f"Repeat-evidence pack status: {repeat_evidence_pack_status}",
            f"Candidate row count: {candidate_row_count}",
            f"Rule family count: {rule_family_count}",
            f"Strong repeat-evidence count: {strong_repeat_evidence_count}",
            f"Single-promotion-only count: {single_promotion_only_count}",
            f"Unavailable-needs-rebuild count: {unavailable_needs_rebuild_count}",
            f"Missing promotion evidence count: {missing_promotion_evidence_count}",
            f"Production guardrail status: {production_guardrail_status}",
            f"Stage 12 guardrail status: {stage12_guardrail_status}",
            f"Whether more promotion reconstruction should run next: {more_promotion_reconstruction_should_run_next}",
            "",
            "## Recommendation",
            recommendation,
        ]
    ).strip()

    return PromotionsMaterializedSourceRepeatEvidencePackResult(
        selected_promotion=selected_promotion,
        repeat_evidence_pack_status=repeat_evidence_pack_status,
        candidate_row_count=candidate_row_count,
        rule_family_count=rule_family_count,
        strong_repeat_evidence_count=strong_repeat_evidence_count,
        single_promotion_only_count=single_promotion_only_count,
        unavailable_needs_rebuild_count=unavailable_needs_rebuild_count,
        missing_promotion_evidence_count=missing_promotion_evidence_count,
        production_guardrail_status=production_guardrail_status,
        stage12_guardrail_status=stage12_guardrail_status,
        more_promotion_reconstruction_should_run_next=more_promotion_reconstruction_should_run_next,
        rows_frame=rows_frame,
        by_rule_family_frame=by_rule_family_frame,
        by_promotion_frame=by_promotion_frame,
        candidate_priority_frame=candidate_priority_frame,
        missing_promotion_evidence_frame=missing_promotion_evidence_frame,
        validation_frame=validation_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
        recommendation=recommendation,
    )


def write_promotions_materialized_source_repeat_evidence_pack(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceRepeatEvidencePackArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = (
        Path(output_root)
        if output_root is not None
        else packet_root_path / OUTPUT_FOLDER_NAME
    )
    result = build_promotions_materialized_source_repeat_evidence_pack(
        packet_root=packet_root_path,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    rows_csv_path = output_root_path / "repeat_evidence_pack_rows.csv"
    by_rule_family_csv_path = output_root_path / "repeat_evidence_pack_by_rule_family.csv"
    by_promotion_csv_path = output_root_path / "repeat_evidence_pack_by_promotion.csv"
    candidate_priority_csv_path = output_root_path / "repeat_evidence_pack_candidate_priority.csv"
    missing_promotion_evidence_csv_path = (
        output_root_path / "repeat_evidence_pack_missing_promotion_evidence.csv"
    )
    validation_csv_path = output_root_path / "repeat_evidence_pack_validation.csv"
    summary_csv_path = output_root_path / "repeat_evidence_pack_summary.csv"
    memo_md_path = output_root_path / "repeat_evidence_pack_memo.md"

    result.rows_frame.to_csv(rows_csv_path, index=False)
    result.by_rule_family_frame.to_csv(by_rule_family_csv_path, index=False)
    result.by_promotion_frame.to_csv(by_promotion_csv_path, index=False)
    result.candidate_priority_frame.to_csv(candidate_priority_csv_path, index=False)
    result.missing_promotion_evidence_frame.to_csv(
        missing_promotion_evidence_csv_path,
        index=False,
    )
    result.validation_frame.to_csv(validation_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceRepeatEvidencePackArtifacts(
        output_root=str(output_root_path),
        rows_csv_path=str(rows_csv_path),
        by_rule_family_csv_path=str(by_rule_family_csv_path),
        by_promotion_csv_path=str(by_promotion_csv_path),
        candidate_priority_csv_path=str(candidate_priority_csv_path),
        missing_promotion_evidence_csv_path=str(missing_promotion_evidence_csv_path),
        validation_csv_path=str(validation_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
        selected_promotion=result.selected_promotion.promotion_key,
        repeat_evidence_pack_status=result.repeat_evidence_pack_status,
        candidate_row_count=result.candidate_row_count,
        rule_family_count=result.rule_family_count,
        strong_repeat_evidence_count=result.strong_repeat_evidence_count,
        single_promotion_only_count=result.single_promotion_only_count,
        unavailable_needs_rebuild_count=result.unavailable_needs_rebuild_count,
        missing_promotion_evidence_count=result.missing_promotion_evidence_count,
        production_guardrail_status=result.production_guardrail_status,
        stage12_guardrail_status=result.stage12_guardrail_status,
        more_promotion_reconstruction_should_run_next=result.more_promotion_reconstruction_should_run_next,
        recommendation=result.recommendation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only repeat-evidence pack across materialised promotions."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_repeat_evidence_pack(
        packet_root=args.packet_root,
        output_root=args.output_root,
        promotion_key=args.promotion_key,
    )
    print("selected_promotion", artifacts.selected_promotion)
    print("repeat_evidence_pack_status", artifacts.repeat_evidence_pack_status)
    print("candidate_row_count", artifacts.candidate_row_count)
    print("rule_family_count", artifacts.rule_family_count)
    print("strong_repeat_evidence_count", artifacts.strong_repeat_evidence_count)
    print("single_promotion_only_count", artifacts.single_promotion_only_count)
    print(
        "unavailable_needs_rebuild_count",
        artifacts.unavailable_needs_rebuild_count,
    )
    print(
        "missing_promotion_evidence_count",
        artifacts.missing_promotion_evidence_count,
    )
    print("production_guardrail_status", artifacts.production_guardrail_status)
    print("stage12_guardrail_status", artifacts.stage12_guardrail_status)
    print(
        "more_promotion_reconstruction_should_run_next",
        artifacts.more_promotion_reconstruction_should_run_next,
    )
    print("recommendation", artifacts.recommendation)
    print("repeat_evidence_pack_rows", artifacts.rows_csv_path)
    print("repeat_evidence_pack_by_rule_family", artifacts.by_rule_family_csv_path)
    print("repeat_evidence_pack_by_promotion", artifacts.by_promotion_csv_path)
    print("repeat_evidence_pack_candidate_priority", artifacts.candidate_priority_csv_path)
    print(
        "repeat_evidence_pack_missing_promotion_evidence",
        artifacts.missing_promotion_evidence_csv_path,
    )
    print("repeat_evidence_pack_validation", artifacts.validation_csv_path)
    print("repeat_evidence_pack_summary", artifacts.summary_csv_path)
    print("repeat_evidence_pack_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())