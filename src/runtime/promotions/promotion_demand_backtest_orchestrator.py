from __future__ import annotations

"""Completed-promotion demand backtest orchestrator.

Production wrapper that turns the trainer's honest out-of-sample test-set
predictions into the seven governed backtest artifacts the operator brief and
operational-cycle manifest depend on:

    promotion_demand_backtest.csv
    promotion_demand_backtest.parquet
    promotion_demand_backtest_summary.json
    promotion_demand_backtest_by_segment.csv
    promotion_demand_backtest_watchlist.csv
    promotion_demand_backtest_brief.md
    promotion_demand_backtest_manifest.json

INSERTION POINT
---------------
Called from `run_promotions_operational_cycle.run_operational_cycle` between
Stage 9 (decision-surface manifest write) and Stage 10 (audit). The trainer at
Stage 5 emits `test_set_predictions.parquet`; this module reads that parquet
and writes the seven artifacts under
`{artifact_paths.operational_cycle_run_root(run_id)}/completed_promotions_demand_backtest/`.

JOIN GRAIN
----------
The comparison grain is `promotion_row_key` (canonical, governed string key
formed at extraction as `store_number|sku_number|promotion_start_date|
promotional_end_date`). It is deduped on read; if duplicates appear the run
fails loud.

SKIP CLASSES
------------
Skip is allowed (NOT a fatal error) when:
- `test_set_predictions.parquet` does not exist (e.g. fresh repo, no completed
  side data),
- the parquet has zero rows,
- the parquet has zero rows where actual demand is observable.

In all skip cases a manifest is still written with a non-null `skip_reason`
and `skip_class` so the operational-cycle manifest carries an honest record.

FAIL-LOUD CLASSES
-----------------
Fail when:
- the parquet exists but is missing required columns
  (promotion_row_key / predicted_units_total_promo / actual_units_sold_promo),
- duplicate `promotion_row_key` values are present (ambiguous join),
- write of any artifact raises.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from models.promotions.promotion_demand_backtest import (
    PromotionBacktestContractError,
    compute_backtest_rows,
    compute_backtest_summary,
)
from models.promotions.promotion_execution_scorecard import (
    PromotionExecutionScorecardError,
    empty_promotion_execution_scorecard_artifacts,
    write_promotion_execution_scorecard_artifacts,
)
from runtime.promotions.promotion_demand_backtest_calibration import (
    assign_calibration_actions,
    classify_segment_harm,
    compose_commercial_calibration_brief,
    compute_commercial_calibration_summary,
    compute_row_economics,
    enrich_segment_table,
    materially_rank_watchlist,
)


LOGGER = logging.getLogger(__name__)

BACKTEST_DIRECTORY_NAME = "completed_promotions_demand_backtest"

# Watchlist thresholds. Kept conservative and explicit so an operator can
# review them in the brief and tune later from a single source of truth.
WATCHLIST_MIN_ROWS = 30
WATCHLIST_WITHIN_10PCT_BREACH = 0.30
WATCHLIST_MAPE_BREACH = 50.0
WATCHLIST_OVERFORECAST_BREACH = 0.65
WATCHLIST_UNDERFORECAST_BREACH = 0.65

REQUIRED_INPUT_COLUMNS: tuple[str, ...] = (
    "promotion_row_key",
    "predicted_units_total_promo",
    "actual_units_sold_promo",
)


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    """Tiny dependency-free markdown table renderer (no `tabulate` required)."""
    if frame.empty:
        return "_(no rows)_"
    header = "| " + " | ".join(str(c) for c in frame.columns) + " |"
    sep = "| " + " | ".join("---" for _ in frame.columns) + " |"
    body_lines = []
    for _, row in frame.iterrows():
        cells = []
        for value in row.tolist():
            if isinstance(value, float):
                cells.append(f"{value:g}")
            else:
                cells.append(str(value))
        body_lines.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep, *body_lines])



class PromotionBacktestOrchestratorError(RuntimeError):
    """Raised when backtest orchestration cannot continue safely."""


@dataclass(frozen=True)
class PromotionBacktestArtifactPaths:
    rows_csv_path: str
    rows_parquet_path: str
    summary_json_path: str
    summary_csv_path: str
    by_segment_csv_path: str
    watchlist_csv_path: str
    brief_md_path: str
    manifest_json_path: str
    calibration_summary_json_path: str
    calibration_brief_md_path: str
    execution_scorecard_csv_path: str
    execution_scorecard_summary_json_path: str
    trust_floor_shape_policy_audit_csv_path: str
    trust_floor_shape_policy_audit_json_path: str
    skip_reason: str | None = None
    skip_class: str | None = None
    row_count_evaluated: int = 0
    within_10pct_rate: float = 0.0
    within_20pct_rate: float = 0.0


# Segment definitions. Each entry maps (segment_dimension_label) -> callable
# that produces a pd.Series of segment values keyed on the row index. Each
# returns a string label per row (or "unavailable" when the underlying column
# does not exist on the engineered frame). Designed so the segment table is
# always commercially readable in CSV.
def _safe_numeric(frame: pd.DataFrame, column_name: str) -> pd.Series | None:
    if column_name not in frame.columns:
        return None
    return pd.to_numeric(frame[column_name], errors="coerce")


def _band_discount(frame: pd.DataFrame) -> pd.Series:
    series = _safe_numeric(frame, "discount_percent")
    if series is None:
        return pd.Series("unavailable", index=frame.index)
    bins = [-0.001, 10.0, 20.0, 30.0, 50.0, 1000.0]
    labels = ["0-10pct", "10-20pct", "20-30pct", "30-50pct", "50pct_plus"]
    return pd.cut(series.fillna(-1.0), bins=bins, labels=labels).astype(str).fillna("unavailable")


def _band_promo_duration(frame: pd.DataFrame) -> pd.Series:
    series = _safe_numeric(frame, "promo_days")
    if series is None:
        series = _safe_numeric(frame, "live_promo_window_days")
    if series is None:
        return pd.Series("unavailable", index=frame.index)
    bins = [-0.001, 3.0, 7.0, 14.0, 28.0, 1000.0]
    labels = ["1-3d", "4-7d", "8-14d", "15-28d", "29d_plus"]
    return pd.cut(series.fillna(-1.0), bins=bins, labels=labels).astype(str).fillna("unavailable")


def _band_cannibalisation_risk(frame: pd.DataFrame) -> pd.Series:
    series = _safe_numeric(frame, "feature_prior_promo_cannibalisation_risk_score")
    if series is None:
        return pd.Series("unavailable", index=frame.index)
    bins = [-0.001, 0.2, 0.4, 0.6, 1.0001]
    labels = ["low_0_to_0.2", "moderate_0.2_to_0.4", "elevated_0.4_to_0.6", "high_above_0.6"]
    return pd.cut(series.fillna(0.0), bins=bins, labels=labels).astype(str).fillna("unavailable")


def _flag_label(frame: pd.DataFrame, column_name: str) -> pd.Series:
    series = _safe_numeric(frame, column_name)
    if series is None:
        return pd.Series("unavailable", index=frame.index)
    return series.fillna(0).astype(int).map({1: "yes", 0: "no"}).fillna("unavailable")


def _string_label(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series("unavailable", index=frame.index)
    return frame[column_name].astype("string").fillna("unspecified").astype(str)


SegmentBuilder = "tuple[str, callable[[pd.DataFrame], pd.Series]]"


def _segment_builders() -> list[tuple[str, object]]:
    return [
        ("intermittent_demand_flag", lambda f: _flag_label(f, "feature_intermittent_demand_flag")),
        ("sparse_repeat_purchase_flag", lambda f: _flag_label(f, "feature_sparse_repeat_purchase_flag")),
        ("prior_promo_14d_flag", lambda f: _flag_label(f, "feature_prior_promo_14d_flag")),
        ("prior_promo_28d_flag", lambda f: _flag_label(f, "feature_prior_promo_28d_flag")),
        ("prior_same_or_better_discount_56d_flag",
            lambda f: _flag_label(f, "feature_prior_same_or_better_discount_56d_flag")),
        ("prior_promo_cannibalisation_risk_band", _band_cannibalisation_risk),
        ("discount_band", _band_discount),
        ("promo_duration_band", _band_promo_duration),
        ("store_number", lambda f: _string_label(f, "store_number")),
        ("department", lambda f: _string_label(f, "department")),
        ("category", lambda f: _string_label(f, "category")),
    ]


def _validate_input_frame(frame: pd.DataFrame) -> None:
    missing = [name for name in REQUIRED_INPUT_COLUMNS if name not in frame.columns]
    if missing:
        raise PromotionBacktestOrchestratorError(
            f"Backtest input parquet missing required columns: {missing}"
        )
    if frame["promotion_row_key"].duplicated().any():
        offending = (
            frame.loc[frame["promotion_row_key"].duplicated(keep=False), "promotion_row_key"]
            .head(10)
            .tolist()
        )
        raise PromotionBacktestOrchestratorError(
            "Duplicate promotion_row_key values in backtest input "
            f"(first up to 10): {offending}"
        )


def _build_segment_table(
    *,
    backtest_rows: pd.DataFrame,
    enriched_frame: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for dimension, builder in _segment_builders():
        labels = builder(enriched_frame)
        if (labels == "unavailable").all():
            continue
        joined = backtest_rows.assign(_segment_value=labels.values)
        for segment_value, group in joined.groupby("_segment_value", dropna=False):
            comparable_rows = int(len(group.index))
            if comparable_rows == 0:
                continue
            rows.append(
                {
                    "segment_dimension": dimension,
                    "segment_value": str(segment_value),
                    "comparable_rows": comparable_rows,
                    "within_10pct_rate": round(float(group["within_10pct_flag"].mean()), 4),
                    "within_20pct_rate": round(float(group["within_20pct_flag"].mean()), 4),
                    "mean_absolute_percentage_error": round(float(group["absolute_pct_error"].mean()), 2),
                    "median_absolute_percentage_error": round(float(group["absolute_pct_error"].median()), 2),
                    "mean_absolute_error_units": round(float(group["absolute_error_units"].mean()), 2),
                    "overforecast_rate": round(float(group["overforecast_flag"].mean()), 4),
                    "underforecast_rate": round(float(group["underforecast_flag"].mean()), 4),
                }
            )
    if not rows:
        return pd.DataFrame(
            columns=[
                "segment_dimension",
                "segment_value",
                "comparable_rows",
                "within_10pct_rate",
                "within_20pct_rate",
                "mean_absolute_percentage_error",
                "median_absolute_percentage_error",
                "mean_absolute_error_units",
                "overforecast_rate",
                "underforecast_rate",
            ]
        )
    return pd.DataFrame(rows).sort_values(
        ["segment_dimension", "segment_value"]
    ).reset_index(drop=True)


def _build_watchlist(segment_table: pd.DataFrame) -> pd.DataFrame:
    if segment_table.empty:
        return segment_table.assign(watchlist_reason=pd.Series(dtype=str))

    reasons: list[str] = []
    flags: list[bool] = []
    for _, row in segment_table.iterrows():
        row_reasons: list[str] = []
        if int(row["comparable_rows"]) >= WATCHLIST_MIN_ROWS:
            if float(row["within_10pct_rate"]) < WATCHLIST_WITHIN_10PCT_BREACH:
                row_reasons.append(
                    f"within_10pct_rate<{WATCHLIST_WITHIN_10PCT_BREACH:.2f}"
                )
            if float(row["mean_absolute_percentage_error"]) > WATCHLIST_MAPE_BREACH:
                row_reasons.append(f"mape>{WATCHLIST_MAPE_BREACH:.0f}pct")
            if float(row["overforecast_rate"]) > WATCHLIST_OVERFORECAST_BREACH:
                row_reasons.append(
                    f"overforecast_rate>{WATCHLIST_OVERFORECAST_BREACH:.2f}"
                )
            if float(row["underforecast_rate"]) > WATCHLIST_UNDERFORECAST_BREACH:
                row_reasons.append(
                    f"underforecast_rate>{WATCHLIST_UNDERFORECAST_BREACH:.2f}"
                )
        flags.append(bool(row_reasons))
        reasons.append(";".join(row_reasons))
    out = segment_table.copy()
    out["watchlist_reason"] = reasons
    return out.loc[pd.Series(flags, index=out.index)].reset_index(drop=True)


def _build_brief(
    *,
    summary: dict[str, object],
    segment_table: pd.DataFrame,
    watchlist: pd.DataFrame,
    run_id: str,
    as_of_date: str | None,
    comparison_grain: str,
    skip_reason: str | None,
    skip_class: str | None,
) -> str:
    lines: list[str] = []
    lines.append(f"# Promotion demand backtest brief — run {run_id}")
    if as_of_date:
        lines.append(f"As-of date: {as_of_date}")
    lines.append("")
    lines.append(f"Comparison grain: `{comparison_grain}`")
    lines.append("")
    if skip_reason:
        lines.append(f"**Backtest skipped:** {skip_class} — {skip_reason}")
        lines.append("")
        lines.append("No actuals-vs-forecast comparison was possible this run.")
        return "\n".join(lines) + "\n"

    n = int(summary.get("comparable_rows", summary.get("completed_promotions_evaluated", 0)))
    lines.append(f"Comparable rows: **{n}**")
    lines.append(
        f"Within 10%: **{float(summary['within_10pct_rate']) * 100:.1f}%** | "
        f"Within 20%: **{float(summary['within_20pct_rate']) * 100:.1f}%**"
    )
    lines.append(
        f"MAPE — mean: **{float(summary['mean_absolute_percentage_error']):.1f}%**, "
        f"median: **{float(summary['median_absolute_percentage_error']):.1f}%**"
    )
    lines.append(
        f"Overforecast rate: **{float(summary['overforecast_rate']) * 100:.1f}%** | "
        f"Underforecast rate: **{float(summary['underforecast_rate']) * 100:.1f}%**"
    )
    lines.append("")

    if float(summary["overforecast_rate"]) - float(summary["underforecast_rate"]) > 0.20:
        lines.append("**Bias:** systematic overforecasting.")
    elif float(summary["underforecast_rate"]) - float(summary["overforecast_rate"]) > 0.20:
        lines.append("**Bias:** systematic underforecasting.")
    else:
        lines.append("**Bias:** no clear directional bias.")
    lines.append("")

    sized = segment_table[segment_table["comparable_rows"] >= WATCHLIST_MIN_ROWS]
    if not sized.empty:
        strongest = sized.sort_values("within_10pct_rate", ascending=False).head(5)
        weakest = sized.sort_values("within_10pct_rate", ascending=True).head(5)
        lines.append("## Strongest segments (highest within-10%)")
        lines.append(_frame_to_markdown(strongest[["segment_dimension", "segment_value", "comparable_rows",
                                                   "within_10pct_rate", "mean_absolute_percentage_error"]]))
        lines.append("")
        lines.append("## Weakest segments (lowest within-10%)")
        lines.append(_frame_to_markdown(weakest[["segment_dimension", "segment_value", "comparable_rows",
                                                 "within_10pct_rate", "mean_absolute_percentage_error"]]))
        lines.append("")

    lines.append("## Watchlist")
    if watchlist.empty:
        lines.append(
            f"No segments breach the calibration thresholds "
            f"(min_rows={WATCHLIST_MIN_ROWS}, "
            f"within_10pct<{WATCHLIST_WITHIN_10PCT_BREACH:.2f}, "
            f"mape>{WATCHLIST_MAPE_BREACH:.0f}, "
            f"over/under>{WATCHLIST_OVERFORECAST_BREACH:.2f})."
        )
    else:
        lines.append(
            f"{len(watchlist.index)} segment(s) breach calibration thresholds. "
            f"See `promotion_demand_backtest_watchlist.csv`."
        )
        lines.append(
            _frame_to_markdown(
                watchlist[["segment_dimension", "segment_value", "comparable_rows",
                           "within_10pct_rate", "mean_absolute_percentage_error",
                           "overforecast_rate", "underforecast_rate", "watchlist_reason"]]
                .head(20)
            )
        )
    lines.append("")

    # Targeted commentary on whether the new prior-promo / intermittent features
    # appear to be helping. Compare flagged-yes vs flagged-no within each
    # dimension; report deltas only when both groups are sized.
    lines.append("## Demand-pattern feature signal")
    feature_dimensions = (
        "intermittent_demand_flag",
        "sparse_repeat_purchase_flag",
        "prior_promo_28d_flag",
        "prior_same_or_better_discount_56d_flag",
    )
    signal_lines: list[str] = []
    for dimension in feature_dimensions:
        slice_df = segment_table[segment_table["segment_dimension"] == dimension]
        if {"yes", "no"}.issubset(set(slice_df["segment_value"])):
            yes = slice_df[slice_df["segment_value"] == "yes"].iloc[0]
            no_row = slice_df[slice_df["segment_value"] == "no"].iloc[0]
            if int(yes["comparable_rows"]) >= 10 and int(no_row["comparable_rows"]) >= 10:
                delta = float(yes["within_10pct_rate"]) - float(no_row["within_10pct_rate"])
                signal_lines.append(
                    f"- `{dimension}`: within-10% yes={float(yes['within_10pct_rate']):.2f} "
                    f"(n={int(yes['comparable_rows'])}) vs no={float(no_row['within_10pct_rate']):.2f} "
                    f"(n={int(no_row['comparable_rows'])}); delta={delta:+.2f}"
                )
    if signal_lines:
        lines.extend(signal_lines)
    else:
        lines.append("Insufficient row counts to compare flagged vs un-flagged segments.")
    lines.append("")
    lines.append("## Threshold review")
    lines.append(
        "Watchlist thresholds (held in `promotion_demand_backtest_orchestrator.py`):"
    )
    lines.append(f"- minimum comparable rows: {WATCHLIST_MIN_ROWS}")
    lines.append(f"- within-10% breach: < {WATCHLIST_WITHIN_10PCT_BREACH:.2f}")
    lines.append(f"- MAPE breach: > {WATCHLIST_MAPE_BREACH:.0f}%")
    lines.append(f"- overforecast breach: > {WATCHLIST_OVERFORECAST_BREACH:.2f}")
    lines.append(f"- underforecast breach: > {WATCHLIST_UNDERFORECAST_BREACH:.2f}")
    return "\n".join(lines) + "\n"


def _empty_skip_paths(
    *,
    output_root: Path,
    run_id: str,
    as_of_date: str | None,
    comparison_grain: str,
    skip_reason: str,
    skip_class: str,
) -> PromotionBacktestArtifactPaths:
    output_root.mkdir(parents=True, exist_ok=True)
    rows_csv_path = output_root / "promotion_demand_backtest.csv"
    rows_parquet_path = output_root / "promotion_demand_backtest.parquet"
    summary_json_path = output_root / "promotion_demand_backtest_summary.json"
    summary_csv_path = output_root / "promotion_demand_backtest_summary.csv"
    by_segment_csv_path = output_root / "promotion_demand_backtest_by_segment.csv"
    watchlist_csv_path = output_root / "promotion_demand_backtest_watchlist.csv"
    brief_md_path = output_root / "promotion_demand_backtest_brief.md"
    manifest_json_path = output_root / "promotion_demand_backtest_manifest.json"
    calibration_summary_json_path = output_root / "promotion_demand_backtest_calibration_summary.json"
    calibration_brief_md_path = output_root / "promotion_demand_backtest_calibration_brief.md"
    scorecard_paths = empty_promotion_execution_scorecard_artifacts(
        output_root=output_root,
        run_id=run_id,
        as_of_date=as_of_date,
        skip_reason=skip_reason,
        skip_class=skip_class,
    )

    empty_rows = pd.DataFrame(
        columns=[
            "promotion_row_key",
            "predicted_units_total_promo",
            "actual_units_sold_promo",
            "absolute_error_units",
            "absolute_pct_error",
            "within_10pct_flag",
            "within_20pct_flag",
            "overforecast_flag",
            "underforecast_flag",
        ]
    )
    empty_rows.to_csv(rows_csv_path, index=False)
    empty_rows.to_parquet(rows_parquet_path, index=False)
    pd.DataFrame(
        columns=[
            "segment_dimension", "segment_value", "comparable_rows",
            "within_10pct_rate", "within_20pct_rate",
            "mean_absolute_percentage_error",
            "median_absolute_percentage_error",
            "mean_absolute_error_units",
            "overforecast_rate", "underforecast_rate",
        ]
    ).to_csv(by_segment_csv_path, index=False)
    pd.DataFrame(
        columns=[
            "segment_dimension", "segment_value", "comparable_rows",
            "within_10pct_rate", "within_20pct_rate",
            "mean_absolute_percentage_error",
            "median_absolute_percentage_error",
            "mean_absolute_error_units",
            "overforecast_rate", "underforecast_rate",
            "watchlist_reason",
        ]
    ).to_csv(watchlist_csv_path, index=False)

    summary_payload = {
        "run_id": run_id,
        "as_of_date": as_of_date,
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "comparison_grain": comparison_grain,
        "total_rows": 0,
        "comparable_rows": 0,
        "excluded_rows": 0,
        "exclusion_reasons": {},
        "within_10pct_rate": 0.0,
        "within_20pct_rate": 0.0,
        "mean_absolute_error_units": 0.0,
        "median_absolute_error_units": 0.0,
        "mean_absolute_percentage_error": 0.0,
        "median_absolute_percentage_error": 0.0,
        "overforecast_rate": 0.0,
        "underforecast_rate": 0.0,
        "floor_breach_rate": 0.0,
        "target_hit_rate": 0.0,
        "end_shape_success_rate": 0.0,
        "zero_oos_rate": 0.0,
        "zero_oos_success_rate": 0.0,
        "high_demand_14d_success_rate": 0.0,
        "total_capital_above_trust_target": 0.0,
        "total_speculative_capital_drag_dollars": 0.0,
        "total_speculative_units_sold": 0.0,
        "total_missed_trust_units": 0.0,
        "total_missed_upside_units": 0.0,
        "gp_per_capital_committed": 0.0,
        "gp_per_speculative_capital": 0.0,
        "sell_through_on_accepted_capital": 0.0,
        "period_absolute_error_units_per_day_mean": 0.0,
        "skip_reason": skip_reason,
        "skip_class": skip_class,
    }
    summary_json_path.write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    pd.DataFrame([summary_payload]).to_csv(summary_csv_path, index=False)
    brief_md_path.write_text(
        _build_brief(
            summary=summary_payload,
            segment_table=pd.DataFrame(),
            watchlist=pd.DataFrame(),
            run_id=run_id,
            as_of_date=as_of_date,
            comparison_grain=comparison_grain,
            skip_reason=skip_reason,
            skip_class=skip_class,
        ),
        encoding="utf-8",
    )
    manifest_payload = {
        "run_id": run_id,
        "as_of_date": as_of_date,
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "comparison_grain": comparison_grain,
        "rows_csv_path": str(rows_csv_path),
        "rows_parquet_path": str(rows_parquet_path),
        "summary_json_path": str(summary_json_path),
        "summary_csv_path": str(summary_csv_path),
        "by_segment_csv_path": str(by_segment_csv_path),
        "watchlist_csv_path": str(watchlist_csv_path),
        "brief_md_path": str(brief_md_path),
        "calibration_summary_json_path": str(calibration_summary_json_path),
        "calibration_brief_md_path": str(calibration_brief_md_path),
        "execution_scorecard_csv_path": scorecard_paths["scorecard_csv_path"],
        "execution_scorecard_summary_json_path": scorecard_paths["scorecard_summary_json_path"],
        "trust_floor_shape_policy_audit_csv_path": scorecard_paths["policy_audit_csv_path"],
        "trust_floor_shape_policy_audit_json_path": scorecard_paths["policy_audit_json_path"],
        "row_count_evaluated": 0,
        "watchlist_segment_count": 0,
        "skip_reason": skip_reason,
        "skip_class": skip_class,
    }
    manifest_json_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    # Skip-path calibration artifacts: empty + honest skip note so downstream
    # consumers always see the same artifact set.
    skip_calibration_summary = {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "overall_within_10pct_rate": 0.0,
        "overall_within_20pct_rate": 0.0,
        "total_comparable_rows": 0,
        "total_material_exposure_dollars": 0.0,
        "total_estimated_leftover_cost_dollars": 0.0,
        "total_estimated_lost_sales_dollars": 0.0,
        "dominant_bias_class": "NO_DOMINANT_BIAS",
        "highest_risk_segment": None,
        "highest_opportunity_segment": None,
        "review_recommended_segment_count": 0,
        "threshold_change_recommended_flag": False,
        "skip_reason": skip_reason,
        "skip_class": skip_class,
    }
    calibration_summary_json_path.write_text(
        json.dumps(skip_calibration_summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    calibration_brief_md_path.write_text(
        compose_commercial_calibration_brief(
            summary=skip_calibration_summary,
            segment_table_enriched=pd.DataFrame(),
            watchlist_ranked=pd.DataFrame(),
            run_id=run_id,
            as_of_date=as_of_date,
            skip_reason=skip_reason,
            skip_class=skip_class,
        ),
        encoding="utf-8",
    )

    return PromotionBacktestArtifactPaths(
        rows_csv_path=str(rows_csv_path),
        rows_parquet_path=str(rows_parquet_path),
        summary_json_path=str(summary_json_path),
        summary_csv_path=str(summary_csv_path),
        by_segment_csv_path=str(by_segment_csv_path),
        watchlist_csv_path=str(watchlist_csv_path),
        brief_md_path=str(brief_md_path),
        manifest_json_path=str(manifest_json_path),
        calibration_summary_json_path=str(calibration_summary_json_path),
        calibration_brief_md_path=str(calibration_brief_md_path),
        execution_scorecard_csv_path=scorecard_paths["scorecard_csv_path"],
        execution_scorecard_summary_json_path=scorecard_paths["scorecard_summary_json_path"],
        trust_floor_shape_policy_audit_csv_path=scorecard_paths["policy_audit_csv_path"],
        trust_floor_shape_policy_audit_json_path=scorecard_paths["policy_audit_json_path"],
        skip_reason=skip_reason,
        skip_class=skip_class,
    )


def write_completed_promotion_demand_backtest(
    *,
    test_set_predictions_path: str | Path | None,
    output_root: Path,
    run_id: str,
    as_of_date: str | None = None,
) -> PromotionBacktestArtifactPaths:
    """Run the completed-promotion demand backtest end-to-end.

    `test_set_predictions_path` is the parquet emitted by `PromotionModelTrainer`
    containing the honest test-split rows (model never trained on these), with
    `predicted_units_total_promo` and `actual_units_sold_promo` plus segment
    columns.
    """

    comparison_grain = "promotion_row_key"
    output_root.mkdir(parents=True, exist_ok=True)

    if test_set_predictions_path is None or not Path(test_set_predictions_path).exists():
        return _empty_skip_paths(
            output_root=output_root,
            run_id=run_id,
            as_of_date=as_of_date,
            comparison_grain=comparison_grain,
            skip_reason="test_set_predictions parquet not present",
            skip_class="no_test_set_predictions_artifact",
        )

    enriched = pd.read_parquet(test_set_predictions_path)
    if enriched.empty:
        return _empty_skip_paths(
            output_root=output_root,
            run_id=run_id,
            as_of_date=as_of_date,
            comparison_grain=comparison_grain,
            skip_reason="test_set_predictions parquet has zero rows",
            skip_class="empty_test_set",
        )

    _validate_input_frame(enriched)

    total_rows = int(len(enriched.index))
    actuals = pd.to_numeric(enriched["actual_units_sold_promo"], errors="coerce")
    comparable_mask = actuals.notna()
    excluded_actual_missing = int((~comparable_mask).sum())
    if not comparable_mask.any():
        return _empty_skip_paths(
            output_root=output_root,
            run_id=run_id,
            as_of_date=as_of_date,
            comparison_grain=comparison_grain,
            skip_reason="all rows have null actual_units_sold_promo",
            skip_class="no_observable_actuals",
        )

    enriched = enriched.loc[comparable_mask].reset_index(drop=True)
    try:
        backtest_rows = compute_backtest_rows(enriched)
    except PromotionBacktestContractError as exc:  # propagate as fail-loud
        raise PromotionBacktestOrchestratorError(str(exc)) from exc

    summary_core = compute_backtest_summary(backtest_rows)
    abs_err = pd.to_numeric(backtest_rows["absolute_error_units"], errors="coerce").fillna(0.0)
    summary = {
        "run_id": run_id,
        "as_of_date": as_of_date,
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "comparison_grain": comparison_grain,
        "source_test_set_predictions_path": str(test_set_predictions_path),
        "total_rows": total_rows,
        "comparable_rows": int(summary_core["completed_promotions_evaluated"]),
        "excluded_rows": excluded_actual_missing,
        "exclusion_reasons": {"null_actual_units_sold_promo": excluded_actual_missing},
        "within_10pct_rate": summary_core["within_10pct_rate"],
        "within_20pct_rate": summary_core["within_20pct_rate"],
        "mean_absolute_error_units": round(float(abs_err.mean()), 2),
        "median_absolute_error_units": round(float(abs_err.median()), 2),
        "mean_absolute_percentage_error": summary_core["mean_absolute_pct_error"],
        "median_absolute_percentage_error": summary_core["median_absolute_pct_error"],
        "overforecast_rate": summary_core["overforecast_rate"],
        "underforecast_rate": summary_core["underforecast_rate"],
        "floor_breach_rate": summary_core["floor_breach_rate"],
        "target_hit_rate": summary_core["target_hit_rate"],
        "end_shape_success_rate": summary_core["end_shape_success_rate"],
        "zero_oos_rate": summary_core["zero_oos_rate"],
        "zero_oos_success_rate": summary_core["zero_oos_success_rate"],
        "high_demand_14d_success_rate": summary_core["high_demand_14d_success_rate"],
        "total_capital_above_trust_target": summary_core["total_capital_above_trust_target"],
        "total_speculative_capital_drag_dollars": summary_core["total_speculative_capital_drag_dollars"],
        "total_speculative_units_sold": summary_core["total_speculative_units_sold"],
        "total_missed_trust_units": summary_core["total_missed_trust_units"],
        "total_missed_upside_units": summary_core["total_missed_upside_units"],
        "gp_per_capital_committed": summary_core["gp_per_capital_committed"],
        "gp_per_speculative_capital": summary_core["gp_per_speculative_capital"],
        "sell_through_on_accepted_capital": summary_core["sell_through_on_accepted_capital"],
        "period_absolute_error_units_per_day_mean": summary_core["period_absolute_error_units_per_day_mean"],
        "skip_reason": None,
        "skip_class": None,
    }

    segment_table = _build_segment_table(
        backtest_rows=backtest_rows, enriched_frame=enriched
    )

    # ----- Commercial calibration layer -----
    row_economics = compute_row_economics(enriched)
    segment_table_enriched = enrich_segment_table(
        segment_table=segment_table,
        backtest_rows=backtest_rows,
        enriched_frame=enriched,
        segment_builders=_segment_builders(),
        row_economics=row_economics,
    )
    segment_table_enriched["commercial_harm_class"] = classify_segment_harm(
        segment_table_enriched
    )
    segment_table_enriched = assign_calibration_actions(segment_table_enriched)

    # Build the watchlist on the enriched table (so calibration columns ride along)
    # then materially-rank it instead of leaving it in arbitrary order.
    watchlist = _build_watchlist(segment_table_enriched)
    watchlist_ranked = materially_rank_watchlist(watchlist)

    calibration_summary = compute_commercial_calibration_summary(
        segment_table_enriched=segment_table_enriched,
        backtest_summary=summary,
        row_economics=row_economics,
    )
    calibration_brief_text = compose_commercial_calibration_brief(
        summary=calibration_summary,
        segment_table_enriched=segment_table_enriched,
        watchlist_ranked=watchlist_ranked,
        run_id=run_id,
        as_of_date=as_of_date,
        skip_reason=None,
        skip_class=None,
    )
    try:
        scorecard_paths = write_promotion_execution_scorecard_artifacts(
            backtest_rows=backtest_rows,
            source_frame=enriched,
            output_root=output_root,
            run_id=run_id,
            as_of_date=as_of_date,
        )
    except PromotionExecutionScorecardError as exc:
        raise PromotionBacktestOrchestratorError(str(exc)) from exc

    brief_text = _build_brief(
        summary=summary,
        segment_table=segment_table_enriched,
        watchlist=watchlist_ranked,
        run_id=run_id,
        as_of_date=as_of_date,
        comparison_grain=comparison_grain,
        skip_reason=None,
        skip_class=None,
    )

    rows_csv_path = output_root / "promotion_demand_backtest.csv"
    rows_parquet_path = output_root / "promotion_demand_backtest.parquet"
    summary_json_path = output_root / "promotion_demand_backtest_summary.json"
    summary_csv_path = output_root / "promotion_demand_backtest_summary.csv"
    by_segment_csv_path = output_root / "promotion_demand_backtest_by_segment.csv"
    watchlist_csv_path = output_root / "promotion_demand_backtest_watchlist.csv"
    brief_md_path = output_root / "promotion_demand_backtest_brief.md"
    manifest_json_path = output_root / "promotion_demand_backtest_manifest.json"
    calibration_summary_json_path = output_root / "promotion_demand_backtest_calibration_summary.json"
    calibration_brief_md_path = output_root / "promotion_demand_backtest_calibration_brief.md"

    backtest_rows.to_csv(rows_csv_path, index=False)
    backtest_rows.to_parquet(rows_parquet_path, index=False)
    summary_json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    pd.DataFrame([summary]).to_csv(summary_csv_path, index=False)
    segment_table_enriched.to_csv(by_segment_csv_path, index=False)
    watchlist_ranked.to_csv(watchlist_csv_path, index=False)
    brief_md_path.write_text(brief_text, encoding="utf-8")
    calibration_summary_json_path.write_text(
        json.dumps(calibration_summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    calibration_brief_md_path.write_text(calibration_brief_text, encoding="utf-8")

    manifest_payload = {
        "run_id": run_id,
        "as_of_date": as_of_date,
        "created_at_utc": summary["created_at_utc"],
        "comparison_grain": comparison_grain,
        "source_test_set_predictions_path": str(test_set_predictions_path),
        "rows_csv_path": str(rows_csv_path),
        "rows_parquet_path": str(rows_parquet_path),
        "summary_json_path": str(summary_json_path),
        "summary_csv_path": str(summary_csv_path),
        "by_segment_csv_path": str(by_segment_csv_path),
        "watchlist_csv_path": str(watchlist_csv_path),
        "brief_md_path": str(brief_md_path),
        "calibration_summary_json_path": str(calibration_summary_json_path),
        "calibration_brief_md_path": str(calibration_brief_md_path),
        "execution_scorecard_csv_path": scorecard_paths["scorecard_csv_path"],
        "execution_scorecard_summary_json_path": scorecard_paths["scorecard_summary_json_path"],
        "trust_floor_shape_policy_audit_csv_path": scorecard_paths["policy_audit_csv_path"],
        "trust_floor_shape_policy_audit_json_path": scorecard_paths["policy_audit_json_path"],
        "row_count_evaluated": int(summary["comparable_rows"]),
        "watchlist_segment_count": int(len(watchlist_ranked.index)),
        "within_10pct_rate": summary["within_10pct_rate"],
        "within_20pct_rate": summary["within_20pct_rate"],
        "dominant_bias_class": calibration_summary["dominant_bias_class"],
        "review_recommended_segment_count": calibration_summary["review_recommended_segment_count"],
        "threshold_change_recommended_flag": calibration_summary["threshold_change_recommended_flag"],
        "skip_reason": None,
        "skip_class": None,
    }
    manifest_json_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    LOGGER.info(
        "Completed-promotion demand backtest written: comparable_rows=%s within_10pct=%.4f bias=%s",
        summary["comparable_rows"],
        float(summary["within_10pct_rate"]),
        calibration_summary["dominant_bias_class"],
    )
    return PromotionBacktestArtifactPaths(
        rows_csv_path=str(rows_csv_path),
        rows_parquet_path=str(rows_parquet_path),
        summary_json_path=str(summary_json_path),
        summary_csv_path=str(summary_csv_path),
        by_segment_csv_path=str(by_segment_csv_path),
        watchlist_csv_path=str(watchlist_csv_path),
        brief_md_path=str(brief_md_path),
        manifest_json_path=str(manifest_json_path),
        calibration_summary_json_path=str(calibration_summary_json_path),
        calibration_brief_md_path=str(calibration_brief_md_path),
        execution_scorecard_csv_path=scorecard_paths["scorecard_csv_path"],
        execution_scorecard_summary_json_path=scorecard_paths["scorecard_summary_json_path"],
        trust_floor_shape_policy_audit_csv_path=scorecard_paths["policy_audit_csv_path"],
        trust_floor_shape_policy_audit_json_path=scorecard_paths["policy_audit_json_path"],
        row_count_evaluated=int(summary["comparable_rows"]),
        within_10pct_rate=float(summary["within_10pct_rate"]),
        within_20pct_rate=float(summary["within_20pct_rate"]),
    )
