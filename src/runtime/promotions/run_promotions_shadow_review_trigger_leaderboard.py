from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Sequence

import pandas as pd

from runtime.promotions.input_source_provenance import (
    add_provenance_columns,
    certification_failed,
)
from runtime.promotions.run_promotions_action_layer_shadow_vs_baseline_simulation import (
    FAVOURS_SHADOW_REVIEW_TRIGGER,
)


OUTPUT_FOLDER_NAME = "shadow_review_trigger_leaderboard"
INPUT_ROWS_RELATIVE_PATH = Path(
    "action_layer_shadow_vs_baseline_simulation/action_layer_shadow_vs_baseline_rows.csv"
)
INPUT_BY_RULE_FAMILY_RELATIVE_PATH = Path(
    "action_layer_shadow_vs_baseline_simulation/action_layer_shadow_vs_baseline_by_rule_family.csv"
)
INPUT_SUMMARY_RELATIVE_PATH = Path(
    "action_layer_shadow_vs_baseline_simulation/action_layer_shadow_vs_baseline_summary.csv"
)
READINESS_SUMMARY_RELATIVE_PATH = Path(
    "pretrain_readiness_inspection/pretrain_readiness_summary.csv"
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    str(INPUT_ROWS_RELATIVE_PATH),
    str(INPUT_BY_RULE_FAMILY_RELATIVE_PATH),
    str(INPUT_SUMMARY_RELATIVE_PATH),
    str(READINESS_SUMMARY_RELATIVE_PATH),
)

CORE_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
)

PRESERVED_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
    "operator_decision",
    "operator_action",
    "actual_units_sold",
    "expected_promo_demand",
    "forecast_error_units",
    "actual_gross_profit",
    "capital_left_in_unsold_store_allocation",
    "shadow_calibration_rule_candidate",
    "shadow_rule_family",
    "shadow_rule_strength",
    "shadow_rule_risk_level",
    "commercial_priority",
    "shadow_notional_commercial_opportunity",
    "shadow_notional_capital_risk",
    "shadow_net_review_value_proxy",
    "simulation_reason",
    "recommended_next_action",
    "production_order_change_flag",
    "stage_12_change_flag",
)

FILTER_COLUMNS: tuple[str, ...] = (
    "shadow_incremental_review_trigger_flag",
    "shadow_simulation_status",
    "production_order_change_flag",
    "stage_12_change_flag",
)

LEADERBOARD_COLUMNS: tuple[str, ...] = (
    "leaderboard_rank",
    "shadow_review_trigger_score",
    "commercial_value_score",
    "risk_safety_score",
    "repeatability_score",
    "priority_score",
    "leaderboard_tier",
    "leaderboard_reason",
    "recommended_leaderboard_action",
)

BY_RULE_FAMILY_COLUMNS: tuple[str, ...] = (
    "shadow_rule_family",
    "row_count",
    "unique_skus",
    "share_of_rows",
    "tier_1_count",
    "high_priority_tier_1_count",
    "average_trigger_score",
    "average_commercial_value_score",
    "average_risk_safety_score",
    "average_repeatability_score",
    "average_priority_score",
    "gross_profit_represented",
    "capital_left_represented",
    "net_review_value_proxy",
    "first_leaderboard_rank",
    "sample_skus",
)

BY_DEPARTMENT_COLUMNS: tuple[str, ...] = (
    "department",
    "row_count",
    "unique_skus",
    "share_of_rows",
    "tier_1_count",
    "high_priority_tier_1_count",
    "average_trigger_score",
    "gross_profit_represented",
    "capital_left_represented",
    "net_review_value_proxy",
    "rule_families_present",
    "first_leaderboard_rank",
    "sample_skus",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "notes",
)

TIER_1_TEST_FIRST = "TIER_1_TEST_FIRST"
TIER_2_KEEP_IN_SHADOW = "TIER_2_KEEP_IN_SHADOW"
TIER_3_REQUIRE_MORE_EVIDENCE = "TIER_3_REQUIRE_MORE_EVIDENCE"

TEST_FIRST_ACROSS_MORE_PROMOTIONS = "TEST_FIRST_ACROSS_MORE_PROMOTIONS"
KEEP_AS_SHADOW_REVIEW_TRIGGER = "KEEP_AS_SHADOW_REVIEW_TRIGGER"
REQUIRE_MORE_EVIDENCE = "REQUIRE_MORE_EVIDENCE"
DO_NOT_PROMOTE_TO_PRODUCTION = "DO_NOT_PROMOTE_TO_PRODUCTION"

TIER_ORDER: dict[str, int] = {
    TIER_1_TEST_FIRST: 1,
    TIER_2_KEEP_IN_SHADOW: 2,
    TIER_3_REQUIRE_MORE_EVIDENCE: 3,
}

PRIORITY_SCORE_MAP: dict[str, float] = {
    "HIGH": 100.0,
    "MEDIUM": 70.0,
    "LOW": 40.0,
}

RISK_LEVEL_PENALTY_MAP: dict[str, float] = {
    "LOW": 0.0,
    "MEDIUM": 10.0,
    "HIGH": 20.0,
}

FINAL_RECOMMENDATION = TEST_FIRST_ACROSS_MORE_PROMOTIONS


class PromotionsShadowReviewTriggerLeaderboardError(RuntimeError):
    """Raised when the shadow review-trigger leaderboard cannot run safely."""


@dataclass(frozen=True)
class PromotionsShadowReviewTriggerLeaderboardResult:
    rows_frame: pd.DataFrame
    by_rule_family_frame: pd.DataFrame
    by_department_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsShadowReviewTriggerLeaderboardArtifacts:
    rows_csv_path: str
    by_rule_family_csv_path: str
    by_department_csv_path: str
    summary_csv_path: str
    memo_md_path: str


def _read_csv(
    path: str | Path,
    *,
    allow_empty: bool = False,
    empty_columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame(columns=list(empty_columns or ()))
        raise PromotionsShadowReviewTriggerLeaderboardError(f"CSV is empty: {path}")
    if frame.empty and not allow_empty:
        raise PromotionsShadowReviewTriggerLeaderboardError(f"CSV is empty: {path}")
    if frame.empty and empty_columns is not None:
        for column_name in empty_columns:
            if column_name not in frame.columns:
                frame[column_name] = pd.Series(dtype="object")
        frame = frame.loc[:, list(dict.fromkeys([*frame.columns.tolist(), *empty_columns]))]
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsShadowReviewTriggerLeaderboardError(
            f"Manifest must be a JSON object: {path}"
        )
    return payload


def _validate_review_artifact_root(review_artifact_root: Path) -> None:
    missing = [
        artifact_name
        for artifact_name in REQUIRED_REVIEW_ARTIFACTS
        if not (review_artifact_root / artifact_name).exists()
    ]
    if missing:
        raise PromotionsShadowReviewTriggerLeaderboardError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsShadowReviewTriggerLeaderboardError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _format_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}"


def _format_share(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _summary_row(
    metric_group: str,
    metric_name: str,
    metric_value: object,
    metric_unit: str,
    metric_display: str,
    notes: str,
) -> dict[str, object]:
    return {
        "metric_group": metric_group,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_unit": metric_unit,
        "metric_display": metric_display,
        "notes": notes,
    }


def _sample_values(values: pd.Series, *, limit: int = 5) -> str:
    unique_values: list[str] = []
    for value in values.astype(str).tolist():
        cleaned = value.strip()
        if not cleaned or cleaned in unique_values:
            continue
        unique_values.append(cleaned)
        if len(unique_values) >= limit:
            break
    return ", ".join(unique_values)


def _all_missing_or_blank(values: pd.Series) -> bool:
    normalized = values.fillna("").astype(str).str.strip()
    return normalized.eq("").all()


def _metric_lookup(frame: pd.DataFrame | None) -> dict[str, object]:
    if frame is None or frame.empty or "metric_name" not in frame.columns:
        return {}
    lookup: dict[str, object] = {}
    for row in frame.itertuples(index=False):
        lookup[str(getattr(row, "metric_name"))] = getattr(row, "metric_value")
    return lookup


def _readiness_reason(frame: pd.DataFrame | None, readiness_check: str) -> str:
    if frame is None or frame.empty:
        return ""
    if "readiness_check" not in frame.columns or "reason" not in frame.columns:
        return ""
    matched = frame.loc[frame["readiness_check"].astype(str).eq(readiness_check)]
    if matched.empty:
        return ""
    return _normalize_text(matched.iloc[0]["reason"])


def _ensure_columns(source_frame: pd.DataFrame) -> pd.DataFrame:
    frame = source_frame.copy()

    for column_name in [*PRESERVED_COLUMNS, *FILTER_COLUMNS]:
        if column_name not in frame.columns:
            frame[column_name] = pd.Series(dtype="object")

    numeric_columns = (
        "actual_units_sold",
        "expected_promo_demand",
        "forecast_error_units",
        "actual_gross_profit",
        "capital_left_in_unsold_store_allocation",
        "shadow_notional_commercial_opportunity",
        "shadow_notional_capital_risk",
        "shadow_net_review_value_proxy",
        "shadow_incremental_review_trigger_flag",
        "production_order_change_flag",
        "stage_12_change_flag",
    )
    for column_name in numeric_columns:
        frame[column_name] = pd.to_numeric(frame.get(column_name), errors="coerce")

    if not frame.empty:
        if _all_missing_or_blank(frame["shadow_notional_commercial_opportunity"]):
            frame["shadow_notional_commercial_opportunity"] = frame["actual_gross_profit"].fillna(0.0)
        else:
            frame["shadow_notional_commercial_opportunity"] = frame[
                "shadow_notional_commercial_opportunity"
            ].fillna(frame["actual_gross_profit"]).fillna(0.0)

        if _all_missing_or_blank(frame["shadow_notional_capital_risk"]):
            frame["shadow_notional_capital_risk"] = frame[
                "capital_left_in_unsold_store_allocation"
            ].fillna(0.0)
        else:
            frame["shadow_notional_capital_risk"] = frame[
                "shadow_notional_capital_risk"
            ].fillna(frame["capital_left_in_unsold_store_allocation"]).fillna(0.0)

        if _all_missing_or_blank(frame["shadow_net_review_value_proxy"]):
            frame["shadow_net_review_value_proxy"] = (
                frame["shadow_notional_commercial_opportunity"]
                - frame["shadow_notional_capital_risk"]
            )
        else:
            frame["shadow_net_review_value_proxy"] = frame[
                "shadow_net_review_value_proxy"
            ].fillna(
                frame["shadow_notional_commercial_opportunity"]
                - frame["shadow_notional_capital_risk"]
            )

    for column_name in numeric_columns:
        frame[column_name] = pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0)

    frame["shadow_incremental_review_trigger_flag"] = (
        frame["shadow_incremental_review_trigger_flag"].fillna(0).astype(int)
    )
    frame["production_order_change_flag"] = frame["production_order_change_flag"].fillna(0).astype(int)
    frame["stage_12_change_flag"] = frame["stage_12_change_flag"].fillna(0).astype(int)

    return frame


def _expected_input_rows(summary_frame: pd.DataFrame | None) -> int:
    if summary_frame is None or summary_frame.empty:
        return 0
    _require_columns(
        summary_frame,
        ("metric_name", "metric_value"),
        frame_name="action_layer_shadow_vs_baseline_summary_frame",
    )
    matched = summary_frame.loc[summary_frame["metric_name"].astype(str).eq("INPUT_CANDIDATE_ROWS")]
    if matched.empty:
        return 0
    return int(pd.to_numeric(matched.iloc[0]["metric_value"], errors="coerce"))


def _description_pattern(value: object) -> str:
    tokens = re.findall(r"[A-Z0-9]+", _normalize_text(value).upper())
    stopwords = {"THE", "AND", "WITH", "FOR", "PACK", "PROMO"}
    for token in tokens:
        if len(token) >= 3 and token not in stopwords:
            return token
    return tokens[0] if tokens else ""


def _eligible_rows(simulation_rows_frame: pd.DataFrame) -> pd.DataFrame:
    rows = _ensure_columns(simulation_rows_frame)
    filtered = rows.loc[
        rows["shadow_incremental_review_trigger_flag"].eq(1)
        & rows["shadow_simulation_status"].astype(str).eq(FAVOURS_SHADOW_REVIEW_TRIGGER)
        & rows["production_order_change_flag"].eq(0)
        & rows["stage_12_change_flag"].eq(0)
    ].copy()
    return filtered.reset_index(drop=True)


def _commercial_value_score(row: pd.Series, *, max_gross_profit: float, max_units: float) -> float:
    gross_profit_component = 0.0 if max_gross_profit <= 0.0 else _as_float(row["actual_gross_profit"]) / max_gross_profit
    units_component = 0.0 if max_units <= 0.0 else _as_float(row["actual_units_sold"]) / max_units
    return round((gross_profit_component * 70.0) + (units_component * 30.0), 2)


def _risk_safety_score(row: pd.Series) -> float:
    capital_risk = _as_float(row["shadow_notional_capital_risk"])
    risk_level = _normalize_text(row["shadow_rule_risk_level"]).upper()
    if capital_risk <= 1.0:
        base_score = 100.0
    elif capital_risk <= 5.0:
        base_score = 85.0
    elif capital_risk <= 15.0:
        base_score = 65.0
    else:
        base_score = 40.0
    penalty = RISK_LEVEL_PENALTY_MAP.get(risk_level, 5.0)
    return round(max(base_score - penalty, 0.0), 2)


def _repeatability_score(
    row: pd.Series,
    *,
    family_counts: pd.Series,
    department_counts: pd.Series,
    pattern_counts: pd.Series,
) -> float:
    family_count = float(family_counts.get(_normalize_text(row["shadow_rule_family"]), 0.0))
    department_count = float(department_counts.get(_normalize_text(row["department"]), 0.0))
    description_pattern = _normalize_text(row["_description_pattern"])
    pattern_count = float(pattern_counts.get(description_pattern, 0.0)) if description_pattern else 0.0

    max_family = float(family_counts.max()) if not family_counts.empty else 0.0
    max_department = float(department_counts.max()) if not department_counts.empty else 0.0
    max_pattern = float(pattern_counts.max()) if not pattern_counts.empty else 0.0

    family_component = 0.0 if max_family <= 0.0 else family_count / max_family
    department_component = 0.0 if max_department <= 0.0 else department_count / max_department
    pattern_component = 0.0 if max_pattern <= 0.0 else pattern_count / max_pattern

    return round(
        ((family_component * 0.50) + (department_component * 0.30) + (pattern_component * 0.20))
        * 100.0,
        2,
    )


def _priority_score(row: pd.Series) -> float:
    return PRIORITY_SCORE_MAP.get(_normalize_text(row["commercial_priority"]).upper(), 55.0)


def _shadow_review_trigger_score(row: pd.Series) -> float:
    return round(
        (_as_float(row["commercial_value_score"]) * 0.40)
        + (_as_float(row["risk_safety_score"]) * 0.25)
        + (_as_float(row["repeatability_score"]) * 0.20)
        + (_as_float(row["priority_score"]) * 0.15),
        2,
    )


def _leaderboard_tier(row: pd.Series) -> str:
    score = _as_float(row["shadow_review_trigger_score"])
    risk_safety = _as_float(row["risk_safety_score"])
    repeatability = _as_float(row["repeatability_score"])
    if score >= 80.0 and risk_safety >= 70.0 and repeatability >= 55.0:
        return TIER_1_TEST_FIRST
    if score >= 60.0 and risk_safety >= 50.0:
        return TIER_2_KEEP_IN_SHADOW
    return TIER_3_REQUIRE_MORE_EVIDENCE


def _recommended_leaderboard_action(row: pd.Series) -> str:
    leaderboard_tier = _normalize_text(row["leaderboard_tier"])
    risk_safety = _as_float(row["risk_safety_score"])
    if leaderboard_tier == TIER_1_TEST_FIRST:
        return TEST_FIRST_ACROSS_MORE_PROMOTIONS
    if leaderboard_tier == TIER_2_KEEP_IN_SHADOW:
        return KEEP_AS_SHADOW_REVIEW_TRIGGER
    if risk_safety < 35.0:
        return DO_NOT_PROMOTE_TO_PRODUCTION
    return REQUIRE_MORE_EVIDENCE


def _leaderboard_reason(row: pd.Series) -> str:
    return (
        f"Commercial value {round(_as_float(row['commercial_value_score']), 1)}, "
        f"risk safety {round(_as_float(row['risk_safety_score']), 1)}, "
        f"repeatability {round(_as_float(row['repeatability_score']), 1)}, "
        f"priority {round(_as_float(row['priority_score']), 1)} combine into a shadow review-trigger score of "
        f"{round(_as_float(row['shadow_review_trigger_score']), 1)}."
    )


def _build_rows_frame(simulation_rows_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        simulation_rows_frame,
        CORE_COLUMNS,
        frame_name="action_layer_shadow_vs_baseline_rows_frame",
    )
    rows = _eligible_rows(simulation_rows_frame)

    if rows.empty:
        for column_name in LEADERBOARD_COLUMNS:
            if column_name not in rows.columns:
                rows[column_name] = pd.Series(dtype="object")
        output_columns = list(dict.fromkeys([*PRESERVED_COLUMNS, *LEADERBOARD_COLUMNS]))
        return rows.loc[:, output_columns].reset_index(drop=True)

    rows["_description_pattern"] = rows["sku_description"].map(_description_pattern)

    max_gross_profit = float(rows["actual_gross_profit"].max()) if not rows.empty else 0.0
    max_units = float(rows["actual_units_sold"].max()) if not rows.empty else 0.0
    family_counts = rows["shadow_rule_family"].astype(str).value_counts(dropna=False)
    department_counts = rows["department"].astype(str).value_counts(dropna=False)
    pattern_counts = rows["_description_pattern"].astype(str).replace("", pd.NA).dropna().value_counts(dropna=False)

    rows["commercial_value_score"] = rows.apply(
        lambda row: _commercial_value_score(
            row,
            max_gross_profit=max_gross_profit,
            max_units=max_units,
        ),
        axis=1,
    )
    rows["risk_safety_score"] = rows.apply(_risk_safety_score, axis=1)
    rows["repeatability_score"] = rows.apply(
        lambda row: _repeatability_score(
            row,
            family_counts=family_counts,
            department_counts=department_counts,
            pattern_counts=pattern_counts,
        ),
        axis=1,
    )
    rows["priority_score"] = rows.apply(_priority_score, axis=1)
    rows["shadow_review_trigger_score"] = rows.apply(_shadow_review_trigger_score, axis=1)
    rows["leaderboard_tier"] = rows.apply(_leaderboard_tier, axis=1)
    rows["recommended_leaderboard_action"] = rows.apply(_recommended_leaderboard_action, axis=1)
    rows["leaderboard_reason"] = rows.apply(_leaderboard_reason, axis=1)

    rows["_tier_order"] = rows["leaderboard_tier"].map(TIER_ORDER)
    rows = rows.sort_values(
        by=[
            "_tier_order",
            "shadow_review_trigger_score",
            "priority_score",
            "shadow_net_review_value_proxy",
            "shadow_rule_family",
            "sku_number",
        ],
        ascending=[True, False, False, False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    rows["leaderboard_rank"] = list(range(1, len(rows.index) + 1))

    output_columns = list(dict.fromkeys([*PRESERVED_COLUMNS, *LEADERBOARD_COLUMNS]))
    return rows.loc[:, output_columns].reset_index(drop=True)


def _build_grouped_frame(rows_frame: pd.DataFrame, *, group_column: str, output_columns: Sequence[str]) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=list(output_columns))

    total_rows = float(len(rows_frame.index))
    records: list[dict[str, object]] = []
    for group_value, group in rows_frame.groupby(group_column, sort=False, dropna=False):
        records.append(
            {
                group_column: str(group_value),
                "row_count": int(len(group.index)),
                "unique_skus": int(group["sku_number"].astype(str).nunique()),
                "share_of_rows": float(len(group.index)) / total_rows,
                "tier_1_count": int(group["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST).sum()),
                "tier_2_count": int(group["leaderboard_tier"].astype(str).eq(TIER_2_KEEP_IN_SHADOW).sum()),
                "tier_3_count": int(group["leaderboard_tier"].astype(str).eq(TIER_3_REQUIRE_MORE_EVIDENCE).sum()),
                "high_priority_tier_1_count": int(
                    (group["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST)
                     & group["commercial_priority"].astype(str).eq("HIGH")).sum()
                ),
                "average_shadow_review_trigger_score": float(
                    pd.to_numeric(group["shadow_review_trigger_score"], errors="coerce").fillna(0.0).mean()
                ),
                "gross_profit_represented": float(
                    pd.to_numeric(group["shadow_notional_commercial_opportunity"], errors="coerce").fillna(0.0).sum()
                ),
                "capital_left_represented": float(
                    pd.to_numeric(group["shadow_notional_capital_risk"], errors="coerce").fillna(0.0).sum()
                ),
                "net_review_value_proxy": float(
                    pd.to_numeric(group["shadow_net_review_value_proxy"], errors="coerce").fillna(0.0).sum()
                ),
                "top_rank": int(pd.to_numeric(group["leaderboard_rank"], errors="coerce").fillna(0).min()),
                "sample_skus": _sample_values(group["sku_number"]),
            }
        )

    frame = pd.DataFrame(records, columns=list(output_columns))
    return frame.sort_values(
        by=["tier_1_count", "row_count", "average_shadow_review_trigger_score", group_column],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _dominant_value(values: pd.Series) -> str:
    counts = values.astype(str).value_counts(dropna=False)
    if counts.empty:
        return ""
    return str(counts.index[0])


def _final_recommendation(rows_frame: pd.DataFrame) -> str:
    if rows_frame.empty:
        return REQUIRE_MORE_EVIDENCE
    tier_1_count = int(rows_frame["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST).sum())
    if tier_1_count > 0:
        return TEST_FIRST_ACROSS_MORE_PROMOTIONS
    return KEEP_AS_SHADOW_REVIEW_TRIGGER


def _build_summary_frame(rows_frame: pd.DataFrame, source_rows_frame: pd.DataFrame) -> pd.DataFrame:
    input_simulation_rows = int(len(source_rows_frame.index))
    eligible_rows = int(len(rows_frame.index))
    unique_skus = int(rows_frame["sku_number"].astype(str).nunique()) if eligible_rows > 0 else 0
    tier_1_count = int(rows_frame["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST).sum()) if eligible_rows > 0 else 0
    high_priority_tier_1_count = int(
        (rows_frame["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST)
         & rows_frame["commercial_priority"].astype(str).eq("HIGH")).sum()
    ) if eligible_rows > 0 else 0
    gross_profit_represented = float(
        pd.to_numeric(rows_frame["shadow_notional_commercial_opportunity"], errors="coerce").fillna(0.0).sum()
    ) if eligible_rows > 0 else 0.0
    capital_left_represented = float(
        pd.to_numeric(rows_frame["shadow_notional_capital_risk"], errors="coerce").fillna(0.0).sum()
    ) if eligible_rows > 0 else 0.0
    net_review_value_proxy = float(
        pd.to_numeric(rows_frame["shadow_net_review_value_proxy"], errors="coerce").fillna(0.0).sum()
    ) if eligible_rows > 0 else 0.0
    dominant_rule_family = _dominant_value(rows_frame["shadow_rule_family"]) if eligible_rows > 0 else ""
    dominant_department = _dominant_value(rows_frame["department"]) if eligible_rows > 0 else ""
    production_order_changes = int(
        pd.to_numeric(rows_frame["production_order_change_flag"], errors="coerce").fillna(0).sum()
    ) if eligible_rows > 0 else 0
    stage_12_changes = int(
        pd.to_numeric(rows_frame["stage_12_change_flag"], errors="coerce").fillna(0).sum()
    ) if eligible_rows > 0 else 0
    final_recommendation = _final_recommendation(rows_frame)

    rows: list[dict[str, object]] = [
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "INPUT_SIMULATION_ROWS",
            input_simulation_rows,
            "rows",
            _format_int(input_simulation_rows),
            "Rows available from the shadow-vs-baseline simulation input.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "ELIGIBLE_LEADERBOARD_ROWS",
            eligible_rows,
            "rows",
            _format_int(eligible_rows),
            "Rows eligible for the governed shadow review-trigger leaderboard.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "UNIQUE_SKUS",
            unique_skus,
            "rows",
            _format_int(unique_skus),
            "Unique SKUs represented in the leaderboard slice.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "TIER_1_COUNT",
            tier_1_count,
            "rows",
            _format_int(tier_1_count),
            "Top shadow review-trigger opportunities to test first across more promotions.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "HIGH_PRIORITY_TIER_1_COUNT",
            high_priority_tier_1_count,
            "rows",
            _format_int(high_priority_tier_1_count),
            "Rows that are both HIGH priority and Tier 1.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "GROSS_PROFIT_REPRESENTED",
            gross_profit_represented,
            "dollars",
            _format_money(gross_profit_represented),
            "Historical gross profit represented by the eligible leaderboard slice.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "CAPITAL_LEFT_REPRESENTED",
            capital_left_represented,
            "dollars",
            _format_money(capital_left_represented),
            "Historical capital-left exposure represented by the eligible leaderboard slice.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "NET_REVIEW_VALUE_PROXY",
            net_review_value_proxy,
            "dollars",
            _format_money(net_review_value_proxy),
            "Net commercial opportunity proxy across eligible leaderboard rows.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "DOMINANT_RULE_FAMILY",
            dominant_rule_family,
            "label",
            dominant_rule_family,
            "Most common shadow rule family in the eligible leaderboard slice.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "DOMINANT_DEPARTMENT",
            dominant_department,
            "label",
            dominant_department,
            "Most common department in the eligible leaderboard slice.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            production_order_changes,
            "rows",
            _format_int(production_order_changes),
            "This diagnostics-only leaderboard does not change production ordering logic.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            stage_12_changes,
            "rows",
            _format_int(stage_12_changes),
            "This diagnostics-only leaderboard does not change Stage 12.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "FINAL_RECOMMENDATION",
            final_recommendation,
            "label",
            final_recommendation,
            "Governed recommendation after ranking shadow review-trigger candidates.",
        ),
    ]

    if eligible_rows > 0:
        for tier_name in (TIER_1_TEST_FIRST, TIER_2_KEEP_IN_SHADOW, TIER_3_REQUIRE_MORE_EVIDENCE):
            rows.append(
                _summary_row(
                    "COUNT_BY_LEADERBOARD_TIER",
                    tier_name,
                    int(rows_frame["leaderboard_tier"].astype(str).eq(tier_name).sum()),
                    "rows",
                    _format_int(int(rows_frame["leaderboard_tier"].astype(str).eq(tier_name).sum())),
                    "Row count for this leaderboard tier.",
                )
            )

    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_memo(
    *,
    rows_frame: pd.DataFrame,
    by_rule_family_frame: pd.DataFrame,
    by_department_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    pretrain_readiness_summary_frame: pd.DataFrame | None,
) -> str:
    summary_lookup = _metric_lookup(summary_frame)
    eligible_rows = int(_as_float(summary_lookup.get("ELIGIBLE_LEADERBOARD_ROWS", 0)))
    unique_skus = int(_as_float(summary_lookup.get("UNIQUE_SKUS", 0)))
    tier_1_count = int(_as_float(summary_lookup.get("TIER_1_COUNT", 0)))
    high_priority_tier_1_count = int(_as_float(summary_lookup.get("HIGH_PRIORITY_TIER_1_COUNT", 0)))
    net_review_value_proxy = _format_money(_as_float(summary_lookup.get("NET_REVIEW_VALUE_PROXY", 0.0)))
    dominant_rule_family = _normalize_text(summary_lookup.get("DOMINANT_RULE_FAMILY"))
    dominant_department = _normalize_text(summary_lookup.get("DOMINANT_DEPARTMENT"))
    recommendation = _normalize_text(summary_lookup.get("FINAL_RECOMMENDATION"))

    action_layer_reason = _readiness_reason(pretrain_readiness_summary_frame, "action_layer_calibration_ready")
    forecast_reason = _readiness_reason(pretrain_readiness_summary_frame, "forecast_head_reliability")

    family_lines: list[str] = []
    for row in by_rule_family_frame.head(5).itertuples(index=False):
        family_lines.append(
            f"- {getattr(row, 'shadow_rule_family')}: {getattr(row, 'row_count')} rows, "
            f"tier_1={getattr(row, 'tier_1_count')}, net_proxy={_format_money(_as_float(getattr(row, 'net_review_value_proxy')))}"
        )
    if not family_lines:
        family_lines.append("- No leaderboard rule-family rows were available.")

    department_lines: list[str] = []
    for row in by_department_frame.head(5).itertuples(index=False):
        department_lines.append(
            f"- {getattr(row, 'department')}: {getattr(row, 'row_count')} rows, "
            f"tier_1={getattr(row, 'tier_1_count')}, net_proxy={_format_money(_as_float(getattr(row, 'net_review_value_proxy')))}"
        )
    if not department_lines:
        department_lines.append("- No leaderboard department rows were available.")

    return "\n".join(
        [
            "# Governed Shadow Review-Trigger Leaderboard",
            "",
            "This is not an order file.",
            "No training was started.",
            "Production order changes = 0.",
            "Stage 12 changes = 0.",
            "The leaderboard ranks review-trigger candidates only.",
            "The leaderboard does not create buy recommendations.",
            "Tier 1 means test first in shadow, not promote to production.",
            "Repeated evidence across more promotions is required before production consideration.",
            "",
            "## 1. Executive conclusion",
            f"Eligible leaderboard rows = {eligible_rows} across {unique_skus} unique SKUs.",
            f"Tier 1 rows = {tier_1_count}, including {high_priority_tier_1_count} high-priority Tier 1 rows.",
            f"Dominant rule family = {dominant_rule_family or 'none'}.",
            f"Dominant department = {dominant_department or 'none'}.",
            f"Net review value proxy = {net_review_value_proxy}.",
            f"Recommendation = {recommendation or FINAL_RECOMMENDATION}.",
            "",
            "## 2. Rule-family view",
            *family_lines,
            "",
            "## 3. Department view",
            *department_lines,
            "",
            "## 4. Governance boundary",
            "Tier 1 rows are only the first candidates to test across more promotions in shadow.",
            "No shadow rule in this leaderboard is production-ready.",
            "No production ordering logic, Stage 12 logic, or auto-ordering behavior is changed by this pass.",
            "",
            "## 5. Readiness connection",
            (action_layer_reason or "Action-layer calibration remains an open readiness blocker."),
            (forecast_reason or "Forecast-head reliability remains a separate readiness blocker."),
            "This leaderboard helps decide which governed shadow review triggers deserve repetition first, not production promotion.",
        ]
    )


def build_promotions_shadow_review_trigger_leaderboard(
    *,
    action_layer_shadow_vs_baseline_rows_frame: pd.DataFrame,
    action_layer_shadow_vs_baseline_by_rule_family_frame: pd.DataFrame | None = None,
    action_layer_shadow_vs_baseline_summary_frame: pd.DataFrame | None = None,
    pretrain_readiness_summary_frame: pd.DataFrame | None = None,
) -> PromotionsShadowReviewTriggerLeaderboardResult:
    rows_frame = _build_rows_frame(action_layer_shadow_vs_baseline_rows_frame)

    expected_input_rows = _expected_input_rows(action_layer_shadow_vs_baseline_summary_frame)
    if expected_input_rows > 0 and expected_input_rows != int(len(action_layer_shadow_vs_baseline_rows_frame.index)):
        raise PromotionsShadowReviewTriggerLeaderboardError(
            "Leaderboard source rows do not match the shadow-vs-baseline summary count: "
            f"expected {expected_input_rows}, found {len(action_layer_shadow_vs_baseline_rows_frame.index)}."
        )

    if action_layer_shadow_vs_baseline_by_rule_family_frame is not None and not action_layer_shadow_vs_baseline_by_rule_family_frame.empty:
        _require_columns(
            action_layer_shadow_vs_baseline_by_rule_family_frame,
            ("shadow_rule_family", "row_count"),
            frame_name="action_layer_shadow_vs_baseline_by_rule_family_frame",
        )

    by_rule_family_frame = _build_grouped_frame(
        rows_frame,
        group_column="shadow_rule_family",
        output_columns=BY_RULE_FAMILY_COLUMNS,
    )
    by_department_frame = _build_grouped_frame(
        rows_frame,
        group_column="department",
        output_columns=BY_DEPARTMENT_COLUMNS,
    )
    summary_frame = _build_summary_frame(rows_frame, action_layer_shadow_vs_baseline_rows_frame)
    memo_markdown = _build_memo(
        rows_frame=rows_frame,
        by_rule_family_frame=by_rule_family_frame,
        by_department_frame=by_department_frame,
        summary_frame=summary_frame,
        pretrain_readiness_summary_frame=pretrain_readiness_summary_frame,
    )

    return PromotionsShadowReviewTriggerLeaderboardResult(
        rows_frame=rows_frame,
        by_rule_family_frame=by_rule_family_frame,
        by_department_frame=by_department_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_shadow_review_trigger_leaderboard(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsShadowReviewTriggerLeaderboardArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsShadowReviewTriggerLeaderboardError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_shadow_review_trigger_leaderboard(
        action_layer_shadow_vs_baseline_rows_frame=_read_csv(
            review_artifact_path / INPUT_ROWS_RELATIVE_PATH,
            allow_empty=True,
            empty_columns=[*CORE_COLUMNS],
        ),
        action_layer_shadow_vs_baseline_by_rule_family_frame=_read_csv(
            review_artifact_path / INPUT_BY_RULE_FAMILY_RELATIVE_PATH,
            allow_empty=True,
        ),
        action_layer_shadow_vs_baseline_summary_frame=_read_csv(
            review_artifact_path / INPUT_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
        pretrain_readiness_summary_frame=_read_csv(
            review_artifact_path / READINESS_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
    )

    destination_root = (
        Path(output_root) if output_root is not None else review_artifact_path / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    rows_csv_path = destination_root / "shadow_review_trigger_leaderboard_rows.csv"
    by_rule_family_csv_path = destination_root / "shadow_review_trigger_leaderboard_by_rule_family.csv"
    by_department_csv_path = destination_root / "shadow_review_trigger_leaderboard_by_department.csv"
    summary_csv_path = destination_root / "shadow_review_trigger_leaderboard_summary.csv"
    memo_md_path = destination_root / "shadow_review_trigger_leaderboard_memo.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.by_rule_family_frame.copy(), manifest).to_csv(
        by_rule_family_csv_path,
        index=False,
    )
    add_provenance_columns(result.by_department_frame.copy(), manifest).to_csv(
        by_department_csv_path,
        index=False,
    )
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsShadowReviewTriggerLeaderboardArtifacts(
        rows_csv_path=str(rows_csv_path),
        by_rule_family_csv_path=str(by_rule_family_csv_path),
        by_department_csv_path=str(by_department_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a governed shadow review-trigger leaderboard without starting training "
            "or changing production logic."
        )
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_shadow_review_trigger_leaderboard(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("shadow_review_trigger_leaderboard_rows", artifacts.rows_csv_path)
    print("shadow_review_trigger_leaderboard_by_rule_family", artifacts.by_rule_family_csv_path)
    print("shadow_review_trigger_leaderboard_by_department", artifacts.by_department_csv_path)
    print("shadow_review_trigger_leaderboard_summary", artifacts.summary_csv_path)
    print("shadow_review_trigger_leaderboard_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _format_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}"


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _format_share(value: float) -> str:
    return f"{value * 100:.1f}%"


def _summary_row(
    metric_group: str,
    metric_name: str,
    metric_value: object,
    metric_unit: str,
    metric_display: str,
    notes: str,
) -> dict[str, object]:
    return {
        "metric_group": metric_group,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_unit": metric_unit,
        "metric_display": metric_display,
        "notes": notes,
    }


def _sample_values(values: pd.Series, *, limit: int = 5) -> str:
    unique_values: list[str] = []
    for value in values.astype(str).tolist():
        cleaned = value.strip()
        if not cleaned or cleaned in unique_values:
            continue
        unique_values.append(cleaned)
        if len(unique_values) >= limit:
            break
    return ", ".join(unique_values)


def _all_missing_or_blank(values: pd.Series) -> bool:
    normalized = values.fillna("").astype(str).str.strip()
    return normalized.eq("").all()


def _metric_lookup(frame: pd.DataFrame | None) -> dict[str, object]:
    if frame is None or frame.empty or "metric_name" not in frame.columns:
        return {}
    lookup: dict[str, object] = {}
    for row in frame.itertuples(index=False):
        lookup[str(getattr(row, "metric_name"))] = getattr(row, "metric_value")
    return lookup


def _readiness_reason(frame: pd.DataFrame | None, readiness_check: str) -> str:
    if frame is None or frame.empty:
        return ""
    if "readiness_check" not in frame.columns or "reason" not in frame.columns:
        return ""
    matched = frame.loc[frame["readiness_check"].astype(str).eq(readiness_check)]
    if matched.empty:
        return ""
    return _normalize_text(matched.iloc[0]["reason"])


def _description_pattern(value: object) -> str:
    cleaned = re.sub(r"[^A-Z0-9 ]+", " ", _normalize_text(value).upper())
    tokens = [token for token in cleaned.split() if token]
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0]
    return " ".join(tokens[:2])


def _priority_score_from_label(priority_label: object) -> float:
    normalized = _normalize_text(priority_label).upper()
    return {
        "HIGH": 100.0,
        "MEDIUM": 65.0,
        "LOW": 35.0,
    }.get(normalized, 50.0)


def _risk_safety_score(row: pd.Series) -> float:
    capital_risk = _as_float(row.get("shadow_notional_capital_risk"))
    capital_component = 10.0
    if capital_risk <= 0.5:
        capital_component = 60.0
    elif capital_risk <= 5.0:
        capital_component = 45.0
    elif capital_risk <= 15.0:
        capital_component = 25.0

    risk_label = _normalize_text(row.get("shadow_rule_risk_level")).upper()
    risk_component = {
        "LOW": 40.0,
        "MEDIUM": 25.0,
        "HIGH": 10.0,
    }.get(risk_label, 20.0)
    return round(capital_component + risk_component, 2)


def _leaderboard_tier(score: float) -> str:
    if score >= 75.0:
        return TIER_1_TEST_FIRST
    if score >= 60.0:
        return TIER_2_KEEP_IN_SHADOW
    return TIER_3_REQUIRE_MORE_EVIDENCE


def _recommended_leaderboard_action(row: pd.Series) -> str:
    tier = _normalize_text(row.get("leaderboard_tier"))
    risk_safety_score = _as_float(row.get("risk_safety_score"))
    if tier == TIER_1_TEST_FIRST:
        return TEST_FIRST_ACROSS_MORE_PROMOTIONS
    if tier == TIER_2_KEEP_IN_SHADOW:
        return KEEP_AS_SHADOW_REVIEW_TRIGGER
    if risk_safety_score < 35.0:
        return DO_NOT_PROMOTE_TO_PRODUCTION
    return REQUIRE_MORE_EVIDENCE


def _leaderboard_reason(row: pd.Series) -> str:
    reasons: list[str] = []
    if _as_float(row.get("commercial_value_score")) >= 75.0:
        reasons.append("commercial value is strong")
    if _as_float(row.get("repeatability_score")) >= 70.0:
        reasons.append(
            f"repeatability appears across { _normalize_text(row.get('department')) or 'the department' } and { _normalize_text(row.get('shadow_rule_family')) or 'the rule family' }"
        )
    if _as_float(row.get("risk_safety_score")) >= 75.0:
        reasons.append("governance safety remains strong")
    if _as_float(row.get("priority_score")) >= 90.0:
        reasons.append("commercial priority is already HIGH")
    if not reasons:
        reasons.append("more repeated evidence is still needed before moving this trigger up the queue")
    return "; ".join(reasons) + "."


def _final_recommendation(rows_frame: pd.DataFrame) -> str:
    if rows_frame.empty:
        return REQUIRE_MORE_EVIDENCE
    if rows_frame["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST).any():
        return TEST_FIRST_ACROSS_MORE_PROMOTIONS
    if rows_frame["leaderboard_tier"].astype(str).eq(TIER_2_KEEP_IN_SHADOW).any():
        return KEEP_AS_SHADOW_REVIEW_TRIGGER
    return REQUIRE_MORE_EVIDENCE


def _ensure_columns(source_frame: pd.DataFrame) -> pd.DataFrame:
    frame = source_frame.copy()

    for column_name in [*PRESERVED_COLUMNS, *FILTER_COLUMNS]:
        if column_name not in frame.columns:
            frame[column_name] = pd.Series(dtype="object")

    text_columns = (
        "sku_number",
        "sku_description",
        "department",
        "operator_decision",
        "operator_action",
        "shadow_calibration_rule_candidate",
        "shadow_rule_family",
        "shadow_rule_strength",
        "shadow_rule_risk_level",
        "commercial_priority",
        "simulation_reason",
        "recommended_next_action",
        "shadow_simulation_status",
    )
    for column_name in text_columns:
        frame[column_name] = frame[column_name].fillna("")

    if not frame.empty:
        if _all_missing_or_blank(frame["shadow_notional_commercial_opportunity"]):
            frame["shadow_notional_commercial_opportunity"] = frame.get(
                "actual_gross_profit",
                pd.Series(0.0, index=frame.index),
            )
        if _all_missing_or_blank(frame["shadow_notional_capital_risk"]):
            frame["shadow_notional_capital_risk"] = frame.get(
                "capital_left_in_unsold_store_allocation",
                pd.Series(0.0, index=frame.index),
            )

    numeric_columns = (
        "actual_units_sold",
        "expected_promo_demand",
        "forecast_error_units",
        "actual_gross_profit",
        "capital_left_in_unsold_store_allocation",
        "shadow_notional_commercial_opportunity",
        "shadow_notional_capital_risk",
        "shadow_net_review_value_proxy",
    )
    for column_name in numeric_columns:
        frame[column_name] = pd.to_numeric(frame.get(column_name), errors="coerce").fillna(0.0)

    if not frame.empty and _all_missing_or_blank(frame["shadow_net_review_value_proxy"]):
        frame["shadow_net_review_value_proxy"] = (
            frame["shadow_notional_commercial_opportunity"] - frame["shadow_notional_capital_risk"]
        )

    frame["shadow_incremental_review_trigger_flag"] = pd.to_numeric(
        frame.get("shadow_incremental_review_trigger_flag"),
        errors="coerce",
    ).fillna(0).astype(int)
    frame["production_order_change_flag"] = pd.to_numeric(
        frame.get("production_order_change_flag"),
        errors="coerce",
    ).fillna(0).astype(int)
    frame["stage_12_change_flag"] = pd.to_numeric(
        frame.get("stage_12_change_flag"),
        errors="coerce",
    ).fillna(0).astype(int)
    source_row_numbers = (
        frame["source_row_number"]
        if "source_row_number" in frame.columns
        else pd.Series(0, index=frame.index)
    )
    frame["source_row_number"] = pd.to_numeric(
        source_row_numbers,
        errors="coerce",
    ).fillna(0).astype(int)

    return frame


def _expected_input_rows(summary_frame: pd.DataFrame | None) -> int:
    if summary_frame is None or summary_frame.empty:
        return 0
    _require_columns(
        summary_frame,
        ("metric_name", "metric_value"),
        frame_name="action_layer_shadow_vs_baseline_summary_frame",
    )
    matched = summary_frame.loc[summary_frame["metric_name"].astype(str).eq("INPUT_CANDIDATE_ROWS")]
    if matched.empty:
        return 0
    return int(pd.to_numeric(matched.iloc[0]["metric_value"], errors="coerce"))


def _expected_eligible_rows(summary_frame: pd.DataFrame | None) -> int:
    if summary_frame is None or summary_frame.empty:
        return 0
    _require_columns(
        summary_frame,
        ("metric_name", "metric_value"),
        frame_name="action_layer_shadow_vs_baseline_summary_frame",
    )
    matched = summary_frame.loc[
        summary_frame["metric_name"].astype(str).eq(FAVOURS_SHADOW_REVIEW_TRIGGER)
    ]
    if matched.empty:
        return 0
    return int(pd.to_numeric(matched.iloc[0]["metric_value"], errors="coerce"))


def _build_rows_frame(simulation_rows_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        simulation_rows_frame,
        [*CORE_COLUMNS, *FILTER_COLUMNS],
        frame_name="action_layer_shadow_vs_baseline_rows_frame",
    )
    rows = _ensure_columns(simulation_rows_frame)
    eligible = rows.loc[
        rows["shadow_incremental_review_trigger_flag"].eq(1)
        & rows["shadow_simulation_status"].astype(str).eq(FAVOURS_SHADOW_REVIEW_TRIGGER)
        & rows["production_order_change_flag"].eq(0)
        & rows["stage_12_change_flag"].eq(0)
    ].copy()

    if eligible.empty:
        for column_name in LEADERBOARD_COLUMNS:
            eligible[column_name] = pd.Series(dtype="object")
        return eligible.loc[:, list(dict.fromkeys([*PRESERVED_COLUMNS, *LEADERBOARD_COLUMNS]))]

    eligible["_description_pattern"] = eligible["sku_description"].apply(_description_pattern)

    gross_profit_rank = pd.to_numeric(
        eligible["shadow_notional_commercial_opportunity"],
        errors="coerce",
    ).rank(method="average", pct=True).fillna(0.0)
    units_rank = pd.to_numeric(
        eligible["actual_units_sold"],
        errors="coerce",
    ).rank(method="average", pct=True).fillna(0.0)
    eligible["commercial_value_score"] = ((gross_profit_rank * 0.7) + (units_rank * 0.3)) * 100.0

    family_counts = eligible["shadow_rule_family"].astype(str).value_counts(dropna=False)
    department_counts = eligible["department"].astype(str).value_counts(dropna=False)
    pattern_counts = eligible["_description_pattern"].astype(str).value_counts(dropna=False)
    max_family_count = max(int(family_counts.max()), 1) if not family_counts.empty else 1
    max_department_count = max(int(department_counts.max()), 1) if not department_counts.empty else 1
    max_pattern_count = max(int(pattern_counts.max()), 1) if not pattern_counts.empty else 1

    eligible["risk_safety_score"] = eligible.apply(_risk_safety_score, axis=1)
    eligible["repeatability_score"] = eligible.apply(
        lambda row: round(
            (
                (family_counts.get(str(row["shadow_rule_family"]), 0) / max_family_count) * 45.0
                + (department_counts.get(str(row["department"]), 0) / max_department_count) * 35.0
                + (pattern_counts.get(str(row["_description_pattern"]), 0) / max_pattern_count) * 20.0
            ),
            2,
        ),
        axis=1,
    )
    eligible["priority_score"] = eligible["commercial_priority"].map(_priority_score_from_label)
    eligible["shadow_review_trigger_score"] = (
        (eligible["commercial_value_score"] * 0.40)
        + (eligible["risk_safety_score"] * 0.25)
        + (eligible["repeatability_score"] * 0.20)
        + (eligible["priority_score"] * 0.15)
    ).round(2)
    eligible["leaderboard_tier"] = eligible["shadow_review_trigger_score"].apply(_leaderboard_tier)
    eligible["leaderboard_reason"] = eligible.apply(_leaderboard_reason, axis=1)
    eligible["recommended_leaderboard_action"] = eligible.apply(
        _recommended_leaderboard_action,
        axis=1,
    )

    eligible = eligible.sort_values(
        by=[
            "shadow_review_trigger_score",
            "commercial_value_score",
            "repeatability_score",
            "priority_score",
            "shadow_net_review_value_proxy",
            "department",
            "sku_number",
        ],
        ascending=[False, False, False, False, False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    eligible["leaderboard_rank"] = range(1, len(eligible.index) + 1)

    return eligible.loc[:, list(dict.fromkeys([*PRESERVED_COLUMNS, *LEADERBOARD_COLUMNS]))]


def _build_by_rule_family_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=BY_RULE_FAMILY_COLUMNS)

    records: list[dict[str, object]] = []
    total_rows = float(len(rows_frame.index))
    for rule_family, group in rows_frame.groupby("shadow_rule_family", sort=False, dropna=False):
        records.append(
            {
                "shadow_rule_family": str(rule_family),
                "row_count": int(len(group.index)),
                "unique_skus": int(group["sku_number"].astype(str).nunique()),
                "share_of_rows": float(len(group.index)) / total_rows,
                "tier_1_count": int(group["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST).sum()),
                "high_priority_tier_1_count": int(
                    (group["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST)
                     & group["commercial_priority"].astype(str).eq("HIGH")).sum()
                ),
                "average_trigger_score": float(pd.to_numeric(group["shadow_review_trigger_score"], errors="coerce").fillna(0.0).mean()),
                "average_commercial_value_score": float(pd.to_numeric(group["commercial_value_score"], errors="coerce").fillna(0.0).mean()),
                "average_risk_safety_score": float(pd.to_numeric(group["risk_safety_score"], errors="coerce").fillna(0.0).mean()),
                "average_repeatability_score": float(pd.to_numeric(group["repeatability_score"], errors="coerce").fillna(0.0).mean()),
                "average_priority_score": float(pd.to_numeric(group["priority_score"], errors="coerce").fillna(0.0).mean()),
                "gross_profit_represented": float(pd.to_numeric(group["shadow_notional_commercial_opportunity"], errors="coerce").fillna(0.0).sum()),
                "capital_left_represented": float(pd.to_numeric(group["shadow_notional_capital_risk"], errors="coerce").fillna(0.0).sum()),
                "net_review_value_proxy": float(pd.to_numeric(group["shadow_net_review_value_proxy"], errors="coerce").fillna(0.0).sum()),
                "first_leaderboard_rank": int(pd.to_numeric(group["leaderboard_rank"], errors="coerce").fillna(0).min()),
                "sample_skus": _sample_values(group["sku_number"]),
            }
        )

    frame = pd.DataFrame(records, columns=BY_RULE_FAMILY_COLUMNS)
    return frame.sort_values(
        by=["average_trigger_score", "row_count", "shadow_rule_family"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_by_department_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=BY_DEPARTMENT_COLUMNS)

    records: list[dict[str, object]] = []
    total_rows = float(len(rows_frame.index))
    for department, group in rows_frame.groupby("department", sort=False, dropna=False):
        records.append(
            {
                "department": str(department),
                "row_count": int(len(group.index)),
                "unique_skus": int(group["sku_number"].astype(str).nunique()),
                "share_of_rows": float(len(group.index)) / total_rows,
                "tier_1_count": int(group["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST).sum()),
                "high_priority_tier_1_count": int(
                    (group["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST)
                     & group["commercial_priority"].astype(str).eq("HIGH")).sum()
                ),
                "average_trigger_score": float(pd.to_numeric(group["shadow_review_trigger_score"], errors="coerce").fillna(0.0).mean()),
                "gross_profit_represented": float(pd.to_numeric(group["shadow_notional_commercial_opportunity"], errors="coerce").fillna(0.0).sum()),
                "capital_left_represented": float(pd.to_numeric(group["shadow_notional_capital_risk"], errors="coerce").fillna(0.0).sum()),
                "net_review_value_proxy": float(pd.to_numeric(group["shadow_net_review_value_proxy"], errors="coerce").fillna(0.0).sum()),
                "rule_families_present": _sample_values(group["shadow_rule_family"], limit=10),
                "first_leaderboard_rank": int(pd.to_numeric(group["leaderboard_rank"], errors="coerce").fillna(0).min()),
                "sample_skus": _sample_values(group["sku_number"]),
            }
        )

    frame = pd.DataFrame(records, columns=BY_DEPARTMENT_COLUMNS)
    return frame.sort_values(
        by=["average_trigger_score", "row_count", "department"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_summary_frame(rows_frame: pd.DataFrame, *, input_simulation_rows: int) -> pd.DataFrame:
    eligible_rows = int(len(rows_frame.index))
    unique_skus = int(rows_frame["sku_number"].astype(str).nunique()) if eligible_rows > 0 else 0
    tier_1_count = int(rows_frame["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST).sum()) if eligible_rows > 0 else 0
    high_priority_tier_1_count = int(
        (rows_frame["leaderboard_tier"].astype(str).eq(TIER_1_TEST_FIRST)
         & rows_frame["commercial_priority"].astype(str).eq("HIGH")).sum()
    ) if eligible_rows > 0 else 0
    gross_profit_represented = float(pd.to_numeric(rows_frame["shadow_notional_commercial_opportunity"], errors="coerce").fillna(0.0).sum()) if eligible_rows > 0 else 0.0
    capital_left_represented = float(pd.to_numeric(rows_frame["shadow_notional_capital_risk"], errors="coerce").fillna(0.0).sum()) if eligible_rows > 0 else 0.0
    net_review_value_proxy = float(pd.to_numeric(rows_frame["shadow_net_review_value_proxy"], errors="coerce").fillna(0.0).sum()) if eligible_rows > 0 else 0.0
    rule_family_counts = rows_frame["shadow_rule_family"].astype(str).value_counts(dropna=False) if eligible_rows > 0 else pd.Series(dtype="int64")
    department_counts = rows_frame["department"].astype(str).value_counts(dropna=False) if eligible_rows > 0 else pd.Series(dtype="int64")
    dominant_rule_family = str(rule_family_counts.index[0]) if not rule_family_counts.empty else ""
    dominant_department = str(department_counts.index[0]) if not department_counts.empty else ""
    production_order_changes = int(pd.to_numeric(rows_frame["production_order_change_flag"], errors="coerce").fillna(0).sum()) if eligible_rows > 0 else 0
    stage12_changes = int(pd.to_numeric(rows_frame["stage_12_change_flag"], errors="coerce").fillna(0).sum()) if eligible_rows > 0 else 0
    final_recommendation = _final_recommendation(rows_frame)

    rows: list[dict[str, object]] = [
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "INPUT_SIMULATION_ROWS",
            input_simulation_rows,
            "rows",
            _format_int(input_simulation_rows),
            "Input rows from the shadow-vs-baseline simulation output.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "ELIGIBLE_LEADERBOARD_ROWS",
            eligible_rows,
            "rows",
            _format_int(eligible_rows),
            "Rows eligible for ranking after applying the governed shadow-only leaderboard filter.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "UNIQUE_SKUS",
            unique_skus,
            "rows",
            _format_int(unique_skus),
            "Unique SKUs represented in the leaderboard.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "TIER_1_COUNT",
            tier_1_count,
            "rows",
            _format_int(tier_1_count),
            "Rows ranked as test-first shadow review triggers.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "HIGH_PRIORITY_TIER_1_COUNT",
            high_priority_tier_1_count,
            "rows",
            _format_int(high_priority_tier_1_count),
            "High-priority rows inside Tier 1.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "GROSS_PROFIT_REPRESENTED",
            gross_profit_represented,
            "dollars",
            _format_money(gross_profit_represented),
            "Historical gross profit represented by the eligible leaderboard slice.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "CAPITAL_LEFT_REPRESENTED",
            capital_left_represented,
            "dollars",
            _format_money(capital_left_represented),
            "Historical capital-left exposure represented by the eligible leaderboard slice.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "NET_REVIEW_VALUE_PROXY",
            net_review_value_proxy,
            "dollars",
            _format_money(net_review_value_proxy),
            "Shadow-only review-trigger value proxy across the eligible leaderboard slice.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "DOMINANT_RULE_FAMILY",
            dominant_rule_family,
            "label",
            dominant_rule_family,
            "Most common rule family among eligible leaderboard rows.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "DOMINANT_DEPARTMENT",
            dominant_department,
            "label",
            dominant_department,
            "Most common department among eligible leaderboard rows.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            production_order_changes,
            "rows",
            _format_int(production_order_changes),
            "This diagnostics-only leaderboard does not change production ordering logic.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            stage12_changes,
            "rows",
            _format_int(stage12_changes),
            "This diagnostics-only leaderboard does not change Stage 12.",
        ),
        _summary_row(
            "SHADOW_REVIEW_TRIGGER_LEADERBOARD",
            "FINAL_RECOMMENDATION",
            final_recommendation,
            "label",
            final_recommendation,
            "Governed next action after ranking shadow-only review-trigger opportunities.",
        ),
    ]

    tier_counts = rows_frame["leaderboard_tier"].astype(str).value_counts(dropna=False) if eligible_rows > 0 else pd.Series(dtype="int64")
    for tier_name, count in tier_counts.items():
        rows.append(
            _summary_row(
                "COUNT_BY_LEADERBOARD_TIER",
                str(tier_name),
                int(count),
                "rows",
                _format_int(int(count)),
                "Leaderboard row count for this tier.",
            )
        )

    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_memo(
    *,
    rows_frame: pd.DataFrame,
    by_rule_family_frame: pd.DataFrame,
    by_department_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    pretrain_readiness_summary_frame: pd.DataFrame | None,
) -> str:
    summary_lookup = _metric_lookup(summary_frame)
    input_rows = int(_as_float(summary_lookup.get("INPUT_SIMULATION_ROWS", 0)))
    eligible_rows = int(_as_float(summary_lookup.get("ELIGIBLE_LEADERBOARD_ROWS", 0)))
    unique_skus = int(_as_float(summary_lookup.get("UNIQUE_SKUS", 0)))
    tier_1_count = int(_as_float(summary_lookup.get("TIER_1_COUNT", 0)))
    high_priority_tier_1_count = int(_as_float(summary_lookup.get("HIGH_PRIORITY_TIER_1_COUNT", 0)))
    net_review_value_proxy = _format_money(_as_float(summary_lookup.get("NET_REVIEW_VALUE_PROXY", 0.0)))
    dominant_rule_family = _normalize_text(summary_lookup.get("DOMINANT_RULE_FAMILY"))
    dominant_department = _normalize_text(summary_lookup.get("DOMINANT_DEPARTMENT"))
    recommendation = _normalize_text(summary_lookup.get("FINAL_RECOMMENDATION"))

    forecast_reason = _readiness_reason(pretrain_readiness_summary_frame, "forecast_head_reliability")
    action_layer_reason = _readiness_reason(pretrain_readiness_summary_frame, "action_layer_calibration_ready")

    tier_lines = [
        f"- {tier}: {int(count)} rows"
        for tier, count in rows_frame["leaderboard_tier"].astype(str).value_counts(dropna=False).items()
    ] or ["- No eligible leaderboard rows were available."]
    family_lines = [
        f"- {getattr(row, 'shadow_rule_family')}: {getattr(row, 'row_count')} rows, tier_1={getattr(row, 'tier_1_count')}, avg_score={_as_float(getattr(row, 'average_trigger_score')):.1f}"
        for row in by_rule_family_frame.head(5).itertuples(index=False)
    ] or ["- No rule-family leaderboard rows were available."]
    department_lines = [
        f"- {getattr(row, 'department')}: {getattr(row, 'row_count')} rows, tier_1={getattr(row, 'tier_1_count')}, net_proxy={_format_money(_as_float(getattr(row, 'net_review_value_proxy')))}"
        for row in by_department_frame.head(5).itertuples(index=False)
    ] or ["- No department leaderboard rows were available."]

    return "\n".join(
        [
            "# Governed Shadow Review-Trigger Leaderboard",
            "",
            "This is not an order file.",
            "No training was started.",
            "Production order changes = 0.",
            "Stage 12 changes = 0.",
            "Leaderboard ranks review-trigger candidates only.",
            "Leaderboard does not create buy recommendations.",
            "Tier 1 means test first in shadow, not promote to production.",
            "Repeated evidence across more promotions is required before production consideration.",
            "",
            "## 1. Executive conclusion",
            "The purpose of this leaderboard is to rank governed shadow-only review-trigger opportunities by commercial value, repeatability, and safety.",
            f"Input simulation rows = {input_rows}; eligible leaderboard rows = {eligible_rows} across {unique_skus} unique SKUs.",
            f"Tier 1 count = {tier_1_count}, including {high_priority_tier_1_count} high-priority Tier 1 rows.",
            f"Dominant rule family = {dominant_rule_family or 'none'}; dominant department = {dominant_department or 'none'}.",
            f"Net review value proxy = {net_review_value_proxy}.",
            f"Recommendation = {recommendation or REQUIRE_MORE_EVIDENCE}.",
            "",
            "## 2. Tier view",
            *tier_lines,
            "",
            "## 3. Rule-family view",
            *family_lines,
            "",
            "## 4. Department view",
            *department_lines,
            "",
            "## 5. Governance boundary",
            "This leaderboard ranks only review-trigger candidates and does not create any buy or order recommendation.",
            "No shadow rule in this leaderboard is production-ready.",
            "Use Tier 1 to decide what to test first in shadow across more promotions, not what to promote.",
            "",
            "## 6. Readiness connection",
            (action_layer_reason or "Action-layer calibration remains an open readiness blocker."),
            (forecast_reason or "Forecast-head reliability remains a separate readiness blocker."),
            "This leaderboard helps sequence the safest and most repeatable shadow review-trigger tests before any future production discussion.",
        ]
    )


def build_promotions_shadow_review_trigger_leaderboard(
    *,
    action_layer_shadow_vs_baseline_rows_frame: pd.DataFrame,
    action_layer_shadow_vs_baseline_by_rule_family_frame: pd.DataFrame | None = None,
    action_layer_shadow_vs_baseline_summary_frame: pd.DataFrame | None = None,
    pretrain_readiness_summary_frame: pd.DataFrame | None = None,
) -> PromotionsShadowReviewTriggerLeaderboardResult:
    expected_input_rows = _expected_input_rows(action_layer_shadow_vs_baseline_summary_frame)
    if expected_input_rows > 0 and expected_input_rows != int(len(action_layer_shadow_vs_baseline_rows_frame.index)):
        raise PromotionsShadowReviewTriggerLeaderboardError(
            "Leaderboard input rows do not match the shadow-vs-baseline summary count: "
            f"expected {expected_input_rows}, found {len(action_layer_shadow_vs_baseline_rows_frame.index)}."
        )

    if action_layer_shadow_vs_baseline_by_rule_family_frame is not None and not action_layer_shadow_vs_baseline_by_rule_family_frame.empty:
        _require_columns(
            action_layer_shadow_vs_baseline_by_rule_family_frame,
            ("shadow_rule_family", "row_count"),
            frame_name="action_layer_shadow_vs_baseline_by_rule_family_frame",
        )

    rows_frame = _build_rows_frame(action_layer_shadow_vs_baseline_rows_frame)

    expected_eligible_rows = _expected_eligible_rows(action_layer_shadow_vs_baseline_summary_frame)
    if expected_eligible_rows > 0 and expected_eligible_rows != int(len(rows_frame.index)):
        raise PromotionsShadowReviewTriggerLeaderboardError(
            "Eligible leaderboard rows do not match the shadow-vs-baseline favours count: "
            f"expected {expected_eligible_rows}, found {len(rows_frame.index)}."
        )

    by_rule_family_frame = _build_by_rule_family_frame(rows_frame)
    by_department_frame = _build_by_department_frame(rows_frame)
    summary_frame = _build_summary_frame(
        rows_frame,
        input_simulation_rows=int(len(action_layer_shadow_vs_baseline_rows_frame.index)),
    )
    memo_markdown = _build_memo(
        rows_frame=rows_frame,
        by_rule_family_frame=by_rule_family_frame,
        by_department_frame=by_department_frame,
        summary_frame=summary_frame,
        pretrain_readiness_summary_frame=pretrain_readiness_summary_frame,
    )

    return PromotionsShadowReviewTriggerLeaderboardResult(
        rows_frame=rows_frame,
        by_rule_family_frame=by_rule_family_frame,
        by_department_frame=by_department_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_shadow_review_trigger_leaderboard(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsShadowReviewTriggerLeaderboardArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsShadowReviewTriggerLeaderboardError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_shadow_review_trigger_leaderboard(
        action_layer_shadow_vs_baseline_rows_frame=_read_csv(
            review_artifact_path / INPUT_ROWS_RELATIVE_PATH,
            allow_empty=True,
            empty_columns=[*CORE_COLUMNS, *FILTER_COLUMNS],
        ),
        action_layer_shadow_vs_baseline_by_rule_family_frame=_read_csv(
            review_artifact_path / INPUT_BY_RULE_FAMILY_RELATIVE_PATH,
            allow_empty=True,
        ),
        action_layer_shadow_vs_baseline_summary_frame=_read_csv(
            review_artifact_path / INPUT_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
        pretrain_readiness_summary_frame=_read_csv(
            review_artifact_path / READINESS_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
    )

    destination_root = (
        Path(output_root) if output_root is not None else review_artifact_path / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    rows_csv_path = destination_root / "shadow_review_trigger_leaderboard_rows.csv"
    by_rule_family_csv_path = destination_root / "shadow_review_trigger_leaderboard_by_rule_family.csv"
    by_department_csv_path = destination_root / "shadow_review_trigger_leaderboard_by_department.csv"
    summary_csv_path = destination_root / "shadow_review_trigger_leaderboard_summary.csv"
    memo_md_path = destination_root / "shadow_review_trigger_leaderboard_memo.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.by_rule_family_frame.copy(), manifest).to_csv(
        by_rule_family_csv_path,
        index=False,
    )
    add_provenance_columns(result.by_department_frame.copy(), manifest).to_csv(
        by_department_csv_path,
        index=False,
    )
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsShadowReviewTriggerLeaderboardArtifacts(
        rows_csv_path=str(rows_csv_path),
        by_rule_family_csv_path=str(by_rule_family_csv_path),
        by_department_csv_path=str(by_department_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a governed shadow review-trigger leaderboard without starting training "
            "or changing production logic."
        )
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_shadow_review_trigger_leaderboard(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("shadow_review_trigger_leaderboard_rows", artifacts.rows_csv_path)
    print("shadow_review_trigger_leaderboard_by_rule_family", artifacts.by_rule_family_csv_path)
    print("shadow_review_trigger_leaderboard_by_department", artifacts.by_department_csv_path)
    print("shadow_review_trigger_leaderboard_summary", artifacts.summary_csv_path)
    print("shadow_review_trigger_leaderboard_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())