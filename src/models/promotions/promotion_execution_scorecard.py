from __future__ import annotations

"""Diagnostics-only execution scorecards for completed promotions."""

from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd


TRUST_POLICY_BELOW_FLOOR = "below_trust_floor_missed_opportunity"
TRUST_POLICY_HEALTHY_PROTECTION = "healthy_trust_floor_protection"
TRUST_POLICY_SPECULATIVE_CAPITAL = "speculative_above_floor_capital"
TRUST_POLICY_HEALTHY_RUN_DOWN = "healthy_run_down"
TRUST_POLICY_EXCESSIVE_END_SHAPE = "excessive_end_shape"
TRUST_POLICY_ACCEPTABLE_NEW_LINE = "acceptable_new_line_shape"
TRUST_POLICY_HIGH_DEMAND_UNDERPROTECTED = "high_demand_underprotected"

TRUST_FLOOR_DEFAULT_SHAPE_UNITS = 2.0
NEW_LINE_ACCEPTED_SHAPE_UNITS = 1.0
MONTH_END_MAX_DAYS_COVER = 7.0

REQUIRED_BACKTEST_SCORECARD_COLUMNS: tuple[str, ...] = (
    "promotion_row_key",
    "predicted_units_total_promo",
    "actual_units_sold_promo",
    "absolute_pct_error",
    "within_10pct_flag",
    "within_20pct_flag",
    "period_absolute_error_units_per_day",
    "accepted_capital_units",
    "target_end_stock_units",
    "target_floor_units",
    "actual_end_stock_units",
    "floor_breach_flag",
    "zero_oos_flag",
    "end_shape_success_flag",
    "high_demand_14d_flag",
    "high_demand_14d_success_flag",
    "units_above_trust_target",
    "capital_tied_above_trust_target",
    "speculative_capital_drag_dollars",
    "missed_trust_units",
    "missed_upside_units",
    "realised_gp_proxy_dollars",
    "gp_per_capital_committed",
    "gp_per_speculative_capital",
    "sell_through_on_accepted_capital",
)

REQUIRED_SOURCE_CONTEXT_COLUMN_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("unit_gross_profit", ("promo_gm_unit", "unit_gross_profit", "gross_profit_per_unit")),
    ("no_promo_history_flag", ("feature_no_promo_history_flag", "no_promo_history_flag")),
    ("month_end_cash_runoff_pressure_flag", ("feature_month_end_cash_runoff_pressure_flag", "month_end_cash_runoff_pressure_flag")),
    ("target_end_days_cover", ("feature_end_of_promo_target_days_cover", "target_end_days_cover")),
    ("target_start_stock_units", ("feature_day_one_target_stock_units", "target_soh_at_promo_start_units")),
    ("same_discount_event_count", ("feature_historical_promo_events_same_discount", "historical_promo_events_same_discount")),
)

SCORECARD_ROW_COLUMNS: tuple[str, ...] = (
    "promotion_row_key",
    "trust_floor_shape_policy_class",
    "below_trust_floor_missed_opportunity_flag",
    "healthy_trust_floor_protection_flag",
    "speculative_above_floor_capital_flag",
    "healthy_run_down_flag",
    "excessive_end_shape_flag",
    "acceptable_new_line_shape_flag",
    "high_demand_underprotected_flag",
    "predicted_units_total_promo",
    "actual_units_sold_promo",
    "absolute_pct_error",
    "within_10pct_flag",
    "within_20pct_flag",
    "period_absolute_error_units_per_day",
    "accepted_capital_units",
    "target_start_stock_units",
    "recommended_order_units_success_flag",
    "target_soh_at_promo_start_success_flag",
    "stockout_avoidance_success_flag",
    "target_floor_units",
    "target_end_stock_units",
    "target_end_days_cover",
    "actual_end_stock_units",
    "end_shape_success_flag",
    "missed_trust_units",
    "estimated_gross_profit_missed_from_below_floor_stockouts",
    "units_above_trust_target",
    "capital_tied_above_trust_target",
    "capital_drag_dollars",
    "gross_profit_captured_proxy_dollars",
    "missed_upside_units",
    "effective_sharpe_like_gp_per_drag",
    "gp_per_capital_committed",
    "gp_per_speculative_capital",
    "sell_through_on_accepted_capital",
    "convex_upside_captured_flag",
    "dead_capital_burden_flag",
    "high_demand_14d_flag",
    "high_demand_14d_success_flag",
    "no_promo_history_flag",
    "month_end_cash_runoff_pressure_flag",
    "same_discount_event_count",
    "same_discount_history_available_flag",
    "review_only_flag",
    "published_flag",
    "publish_mix_available_flag",
)


class PromotionExecutionScorecardError(ValueError):
    """Raised when scorecard diagnostics cannot be computed from governed evidence."""


def build_promotion_execution_scorecard_rows(
    *,
    backtest_rows: pd.DataFrame,
    source_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Return row-level trust-floor, shape, and capital-discipline diagnostics."""

    _raise_for_missing_columns(
        backtest_rows,
        REQUIRED_BACKTEST_SCORECARD_COLUMNS,
        frame_name="backtest_rows",
    )
    source_context = _build_source_context(source_frame)
    working = backtest_rows.merge(source_context, on="promotion_row_key", how="left", validate="one_to_one")
    if working[list(_source_context_value_columns())].isna().any(axis=None):
        missing_rows = working.loc[
            working[list(_source_context_value_columns())].isna().any(axis=1),
            "promotion_row_key",
        ].astype(str).head(5).tolist()
        raise PromotionExecutionScorecardError(
            "Scorecard source context missing for promotion_row_key values: " + ", ".join(missing_rows)
        )

    target_floor_units = _numeric(working["target_floor_units"])
    target_end_stock_units = _numeric(working["target_end_stock_units"])
    target_start_stock_units = _numeric(working["target_start_stock_units"]).clip(lower=0.0)
    actual_end_stock_units = _numeric(working["actual_end_stock_units"])
    missed_trust_units = _numeric(working["missed_trust_units"]).clip(lower=0.0)
    units_above_trust_target = _numeric(working["units_above_trust_target"]).clip(lower=0.0)
    capital_above_trust_target = _numeric(working["capital_tied_above_trust_target"]).clip(lower=0.0)
    capital_drag_dollars = _numeric(working["speculative_capital_drag_dollars"]).clip(lower=0.0)
    missed_upside_units = _numeric(working["missed_upside_units"]).clip(lower=0.0)
    gross_profit_captured = _numeric(working["realised_gp_proxy_dollars"]).clip(lower=0.0)
    gp_per_capital_committed = _numeric(working["gp_per_capital_committed"]).clip(lower=0.0)
    gp_per_speculative_capital = _numeric(working["gp_per_speculative_capital"]).clip(lower=0.0)
    sell_through_on_accepted_capital = _numeric(working["sell_through_on_accepted_capital"]).clip(lower=0.0)
    high_demand_flag = _numeric(working["high_demand_14d_flag"]).clip(lower=0.0, upper=1.0)
    high_demand_success_flag = _numeric(working["high_demand_14d_success_flag"]).clip(lower=0.0, upper=1.0)
    no_history_flag = _numeric(working["no_promo_history_flag"]).clip(lower=0.0, upper=1.0)
    month_end_flag = _numeric(working["month_end_cash_runoff_pressure_flag"]).clip(lower=0.0, upper=1.0)
    target_end_days_cover = _numeric(working["target_end_days_cover"])
    unit_gross_profit = _numeric(working["unit_gross_profit"]).clip(lower=0.0)

    below_floor = _numeric(working["floor_breach_flag"]).ge(1.0) | missed_trust_units.gt(0.0)
    high_demand_underprotected = high_demand_flag.ge(1.0) & high_demand_success_flag.lt(1.0)
    speculative_capital = units_above_trust_target.gt(0.0) & capital_above_trust_target.gt(0.0)
    healthy_run_down = (
        month_end_flag.ge(1.0)
        & actual_end_stock_units.ge(target_floor_units)
        & target_end_days_cover.le(MONTH_END_MAX_DAYS_COVER)
        & actual_end_stock_units.le(target_end_stock_units)
    )
    acceptable_new_line = (
        no_history_flag.ge(1.0)
        & target_floor_units.le(NEW_LINE_ACCEPTED_SHAPE_UNITS)
        & actual_end_stock_units.ge(target_floor_units)
    )
    excessive_end_shape = actual_end_stock_units.gt(target_end_stock_units) & speculative_capital
    healthy_protection = actual_end_stock_units.ge(target_floor_units) & ~below_floor
    recommended_success = _numeric(working["accepted_capital_units"]).ge(_numeric(working["actual_units_sold_promo"])) & actual_end_stock_units.ge(target_floor_units)
    target_start_success = _numeric(working["accepted_capital_units"]).ge(target_start_stock_units)
    stockout_avoidance_success = _numeric(working["zero_oos_flag"]).lt(1.0) & ~below_floor
    convex_upside_captured = missed_upside_units.le(0.0) & stockout_avoidance_success
    dead_capital_burden = capital_drag_dollars.gt(0.0) | (units_above_trust_target.gt(0.0) & capital_above_trust_target.gt(0.0))
    effective_sharpe_like = gross_profit_captured.divide(
        capital_drag_dollars.add(missed_trust_units * unit_gross_profit).add(1.0)
    ).replace([float("inf"), float("-inf")], 0.0).fillna(0.0)

    policy_class = _primary_policy_class(
        below_floor=below_floor,
        high_demand_underprotected=high_demand_underprotected,
        healthy_run_down=healthy_run_down,
        acceptable_new_line=acceptable_new_line,
        excessive_end_shape=excessive_end_shape,
        speculative_capital=speculative_capital,
        healthy_protection=healthy_protection,
        index=working.index,
    )
    publish_mix = _publish_mix_flags(source_frame=source_frame, row_keys=working["promotion_row_key"])

    out = pd.DataFrame(
        {
            "promotion_row_key": working["promotion_row_key"].astype(str),
            "trust_floor_shape_policy_class": policy_class,
            "below_trust_floor_missed_opportunity_flag": below_floor.astype(int),
            "healthy_trust_floor_protection_flag": healthy_protection.astype(int),
            "speculative_above_floor_capital_flag": speculative_capital.astype(int),
            "healthy_run_down_flag": healthy_run_down.astype(int),
            "excessive_end_shape_flag": excessive_end_shape.astype(int),
            "acceptable_new_line_shape_flag": acceptable_new_line.astype(int),
            "high_demand_underprotected_flag": high_demand_underprotected.astype(int),
            "predicted_units_total_promo": _numeric(working["predicted_units_total_promo"]).round(2),
            "actual_units_sold_promo": _numeric(working["actual_units_sold_promo"]).round(2),
            "absolute_pct_error": _numeric(working["absolute_pct_error"]).round(2),
            "within_10pct_flag": _numeric(working["within_10pct_flag"]).round(0).astype(int),
            "within_20pct_flag": _numeric(working["within_20pct_flag"]).round(0).astype(int),
            "period_absolute_error_units_per_day": _numeric(working["period_absolute_error_units_per_day"]).round(4),
            "accepted_capital_units": _numeric(working["accepted_capital_units"]).round(2),
            "target_start_stock_units": target_start_stock_units.round(2),
            "recommended_order_units_success_flag": recommended_success.astype(int),
            "target_soh_at_promo_start_success_flag": target_start_success.astype(int),
            "stockout_avoidance_success_flag": stockout_avoidance_success.astype(int),
            "target_floor_units": target_floor_units.round(2),
            "target_end_stock_units": target_end_stock_units.round(2),
            "target_end_days_cover": target_end_days_cover.round(2),
            "actual_end_stock_units": actual_end_stock_units.round(2),
            "end_shape_success_flag": _numeric(working["end_shape_success_flag"]).round(0).astype(int),
            "missed_trust_units": missed_trust_units.round(2),
            "estimated_gross_profit_missed_from_below_floor_stockouts": (missed_trust_units * unit_gross_profit).round(2),
            "units_above_trust_target": units_above_trust_target.round(2),
            "capital_tied_above_trust_target": capital_above_trust_target.round(2),
            "capital_drag_dollars": capital_drag_dollars.round(2),
            "gross_profit_captured_proxy_dollars": gross_profit_captured.round(2),
            "missed_upside_units": missed_upside_units.round(2),
            "effective_sharpe_like_gp_per_drag": effective_sharpe_like.round(4),
            "gp_per_capital_committed": gp_per_capital_committed.round(4),
            "gp_per_speculative_capital": gp_per_speculative_capital.round(4),
            "sell_through_on_accepted_capital": sell_through_on_accepted_capital.round(4),
            "convex_upside_captured_flag": convex_upside_captured.astype(int),
            "dead_capital_burden_flag": dead_capital_burden.astype(int),
            "high_demand_14d_flag": high_demand_flag.round(0).astype(int),
            "high_demand_14d_success_flag": high_demand_success_flag.round(0).astype(int),
            "no_promo_history_flag": no_history_flag.round(0).astype(int),
            "month_end_cash_runoff_pressure_flag": month_end_flag.round(0).astype(int),
            "same_discount_event_count": _numeric(working["same_discount_event_count"]).round(0).astype(int),
            "same_discount_history_available_flag": _numeric(working["same_discount_event_count"]).gt(0.0).astype(int),
            **publish_mix,
        },
        columns=SCORECARD_ROW_COLUMNS,
    )
    return out


def build_promotion_execution_scorecard_summary(*, scorecard_rows: pd.DataFrame) -> dict[str, object]:
    """Aggregate scorecard rows into a compact commercial execution summary."""

    _raise_for_missing_columns(scorecard_rows, SCORECARD_ROW_COLUMNS, frame_name="scorecard_rows")
    evaluated_count = int(len(scorecard_rows.index))
    if evaluated_count == 0:
        return _empty_scorecard_summary()
    high_demand = scorecard_rows.loc[_numeric(scorecard_rows["high_demand_14d_flag"]).ge(1.0)]
    same_discount_available = scorecard_rows.loc[_numeric(scorecard_rows["same_discount_history_available_flag"]).ge(1.0)]
    same_discount_missing = scorecard_rows.loc[_numeric(scorecard_rows["same_discount_history_available_flag"]).lt(1.0)]
    month_end = scorecard_rows.loc[_numeric(scorecard_rows["month_end_cash_runoff_pressure_flag"]).ge(1.0)]
    publish_mix_available = bool(_numeric(scorecard_rows["publish_mix_available_flag"]).ge(1.0).any())
    return {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "diagnostics_only": True,
        "completed_promotions_evaluated": evaluated_count,
        "trust_floor_breach_count": int(_numeric(scorecard_rows["below_trust_floor_missed_opportunity_flag"]).sum()),
        "trust_floor_breach_rate": _rate(scorecard_rows, "below_trust_floor_missed_opportunity_flag"),
        "missed_demand_units_below_trust_floor": round(float(_numeric(scorecard_rows["missed_trust_units"]).sum()), 2),
        "estimated_gross_profit_missed_from_below_floor_stockouts": round(float(_numeric(scorecard_rows["estimated_gross_profit_missed_from_below_floor_stockouts"]).sum()), 2),
        "over_allocation_units_above_trust_floor": round(float(_numeric(scorecard_rows["units_above_trust_target"]).sum()), 2),
        "over_allocation_capital_tied_up": round(float(_numeric(scorecard_rows["capital_tied_above_trust_target"]).sum()), 2),
        "capital_drag_dollars": round(float(_numeric(scorecard_rows["capital_drag_dollars"]).sum()), 2),
        "gross_profit_captured_proxy_dollars": round(float(_numeric(scorecard_rows["gross_profit_captured_proxy_dollars"]).sum()), 2),
        "missed_upside_units": round(float(_numeric(scorecard_rows["missed_upside_units"]).sum()), 2),
        "effective_sharpe_like_gp_per_drag_mean": round(float(_numeric(scorecard_rows["effective_sharpe_like_gp_per_drag"]).mean()), 4),
        "gp_per_capital_committed_mean": round(float(_numeric(scorecard_rows["gp_per_capital_committed"]).mean()), 4),
        "gp_per_speculative_capital_mean": round(float(_numeric(scorecard_rows["gp_per_speculative_capital"]).mean()), 4),
        "sell_through_on_accepted_capital_mean": round(float(_numeric(scorecard_rows["sell_through_on_accepted_capital"]).mean()), 4),
        "recommended_order_units_success_rate": _rate(scorecard_rows, "recommended_order_units_success_flag"),
        "target_soh_at_promo_start_success_rate": _rate(scorecard_rows, "target_soh_at_promo_start_success_flag"),
        "stockout_avoidance_success_rate": _rate(scorecard_rows, "stockout_avoidance_success_flag"),
        "convex_upside_captured_rate": _rate(scorecard_rows, "convex_upside_captured_flag"),
        "dead_capital_burden_count": int(_numeric(scorecard_rows["dead_capital_burden_flag"]).sum()),
        "high_demand_underprotection_count": int(_numeric(scorecard_rows["high_demand_underprotected_flag"]).sum()),
        "end_shape_success_rate": _rate(scorecard_rows, "end_shape_success_flag"),
        "shape_2_achieved_count": int(_numeric(scorecard_rows["actual_end_stock_units"]).ge(TRUST_FLOOR_DEFAULT_SHAPE_UNITS).sum()),
        "acceptable_new_line_shape_count": int(_numeric(scorecard_rows["acceptable_new_line_shape_flag"]).sum()),
        "high_demand_14d_success_rate": _rate(high_demand, "high_demand_14d_success_flag"),
        "month_end_run_down_success_rate": _rate(month_end, "healthy_run_down_flag"),
        "mean_absolute_pct_error": round(float(_numeric(scorecard_rows["absolute_pct_error"]).mean()), 2),
        "within_10pct_rate": _rate(scorecard_rows, "within_10pct_flag"),
        "within_20pct_rate": _rate(scorecard_rows, "within_20pct_flag"),
        "period_absolute_error_units_per_day_mean": round(float(_numeric(scorecard_rows["period_absolute_error_units_per_day"]).mean()), 4),
        "same_discount_history_available_row_count": int(len(same_discount_available.index)),
        "same_discount_history_missing_row_count": int(len(same_discount_missing.index)),
        "same_discount_available_within_20pct_rate": _rate(same_discount_available, "within_20pct_flag"),
        "same_discount_missing_within_20pct_rate": _rate(same_discount_missing, "within_20pct_flag"),
        "publish_mix_available_flag": publish_mix_available,
        "published_row_count": int(_numeric(scorecard_rows["published_flag"]).sum()) if publish_mix_available else None,
        "review_only_row_count": int(_numeric(scorecard_rows["review_only_flag"]).sum()) if publish_mix_available else None,
    }


def write_promotion_execution_scorecard_artifacts(
    *,
    backtest_rows: pd.DataFrame,
    source_frame: pd.DataFrame,
    output_root: Path,
    run_id: str,
    as_of_date: str | None,
) -> dict[str, str]:
    """Write execution scorecard CSV/JSON and trust-floor policy audit artifacts."""

    output_root.mkdir(parents=True, exist_ok=True)
    scorecard_rows = build_promotion_execution_scorecard_rows(
        backtest_rows=backtest_rows,
        source_frame=source_frame,
    )
    summary = build_promotion_execution_scorecard_summary(scorecard_rows=scorecard_rows)
    policy_audit = scorecard_rows.loc[
        :,
        [
            "promotion_row_key",
            "trust_floor_shape_policy_class",
            "below_trust_floor_missed_opportunity_flag",
            "healthy_trust_floor_protection_flag",
            "speculative_above_floor_capital_flag",
            "healthy_run_down_flag",
            "excessive_end_shape_flag",
            "acceptable_new_line_shape_flag",
            "high_demand_underprotected_flag",
            "target_floor_units",
            "target_end_stock_units",
            "target_end_days_cover",
            "actual_end_stock_units",
            "missed_trust_units",
            "units_above_trust_target",
            "capital_tied_above_trust_target",
            "capital_drag_dollars",
            "missed_upside_units",
            "recommended_order_units_success_flag",
            "target_soh_at_promo_start_success_flag",
            "stockout_avoidance_success_flag",
            "same_discount_event_count",
        ],
    ].copy()
    scorecard_csv_path = output_root / "promotion_execution_scorecard.csv"
    scorecard_summary_json_path = output_root / "promotion_execution_scorecard_summary.json"
    policy_audit_csv_path = output_root / "promotion_trust_floor_shape_policy_audit.csv"
    policy_audit_json_path = output_root / "promotion_trust_floor_shape_policy_audit.json"
    scorecard_rows.to_csv(scorecard_csv_path, index=False)
    policy_audit.to_csv(policy_audit_csv_path, index=False)
    scorecard_summary_json_path.write_text(
        json.dumps(
            {"run_id": run_id, "as_of_date": as_of_date, **summary},
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    policy_audit_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "as_of_date": as_of_date,
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "diagnostics_only": True,
                "policy_class_counts": _policy_class_counts(policy_audit),
                "rows": policy_audit.to_dict(orient="records"),
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    return {
        "scorecard_csv_path": str(scorecard_csv_path),
        "scorecard_summary_json_path": str(scorecard_summary_json_path),
        "policy_audit_csv_path": str(policy_audit_csv_path),
        "policy_audit_json_path": str(policy_audit_json_path),
    }


def empty_promotion_execution_scorecard_artifacts(
    *,
    output_root: Path,
    run_id: str,
    as_of_date: str | None,
    skip_reason: str,
    skip_class: str,
) -> dict[str, str]:
    """Write empty diagnostics artifacts for skipped completed-promotion backtests."""

    output_root.mkdir(parents=True, exist_ok=True)
    scorecard_csv_path = output_root / "promotion_execution_scorecard.csv"
    scorecard_summary_json_path = output_root / "promotion_execution_scorecard_summary.json"
    policy_audit_csv_path = output_root / "promotion_trust_floor_shape_policy_audit.csv"
    policy_audit_json_path = output_root / "promotion_trust_floor_shape_policy_audit.json"
    pd.DataFrame(columns=SCORECARD_ROW_COLUMNS).to_csv(scorecard_csv_path, index=False)
    pd.DataFrame(columns=["promotion_row_key", "trust_floor_shape_policy_class"]).to_csv(policy_audit_csv_path, index=False)
    summary = {
        "run_id": run_id,
        "as_of_date": as_of_date,
        **_empty_scorecard_summary(),
        "skip_reason": skip_reason,
        "skip_class": skip_class,
    }
    scorecard_summary_json_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
    policy_audit_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "as_of_date": as_of_date,
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "diagnostics_only": True,
                "policy_class_counts": {},
                "rows": [],
                "skip_reason": skip_reason,
                "skip_class": skip_class,
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    return {
        "scorecard_csv_path": str(scorecard_csv_path),
        "scorecard_summary_json_path": str(scorecard_summary_json_path),
        "policy_audit_csv_path": str(policy_audit_csv_path),
        "policy_audit_json_path": str(policy_audit_json_path),
    }


def _build_source_context(source_frame: pd.DataFrame) -> pd.DataFrame:
    """Return governed scorecard context keyed by promotion_row_key."""

    _raise_for_missing_columns(source_frame, ("promotion_row_key",), frame_name="source_frame")
    context = pd.DataFrame({"promotion_row_key": source_frame["promotion_row_key"].astype(str)})
    for output_name, candidate_columns in REQUIRED_SOURCE_CONTEXT_COLUMN_GROUPS:
        context[output_name] = _first_required_numeric_series(
            source_frame,
            candidate_columns,
            output_name=output_name,
        )
    if context["promotion_row_key"].duplicated().any():
        duplicate_key = context.loc[context["promotion_row_key"].duplicated(), "promotion_row_key"].iloc[0]
        raise PromotionExecutionScorecardError(f"Duplicate promotion_row_key in source_frame: {duplicate_key}")
    return context


def _primary_policy_class(
    *,
    below_floor: pd.Series,
    high_demand_underprotected: pd.Series,
    healthy_run_down: pd.Series,
    acceptable_new_line: pd.Series,
    excessive_end_shape: pd.Series,
    speculative_capital: pd.Series,
    healthy_protection: pd.Series,
    index: pd.Index,
) -> pd.Series:
    """Resolve one primary trust-floor/shape class from ordered diagnostic flags."""

    policy_class = pd.Series(TRUST_POLICY_HEALTHY_PROTECTION, index=index, dtype="object")
    policy_class = policy_class.where(~speculative_capital, TRUST_POLICY_SPECULATIVE_CAPITAL)
    policy_class = policy_class.where(~excessive_end_shape, TRUST_POLICY_EXCESSIVE_END_SHAPE)
    policy_class = policy_class.where(~acceptable_new_line, TRUST_POLICY_ACCEPTABLE_NEW_LINE)
    policy_class = policy_class.where(~healthy_run_down, TRUST_POLICY_HEALTHY_RUN_DOWN)
    policy_class = policy_class.where(~high_demand_underprotected, TRUST_POLICY_HIGH_DEMAND_UNDERPROTECTED)
    policy_class = policy_class.where(~below_floor, TRUST_POLICY_BELOW_FLOOR)
    policy_class = policy_class.where(healthy_protection | below_floor | high_demand_underprotected | speculative_capital, TRUST_POLICY_HEALTHY_PROTECTION)
    return policy_class


def _publish_mix_flags(*, source_frame: pd.DataFrame, row_keys: pd.Series) -> dict[str, pd.Series]:
    """Return review-only and published flags when governed publish fields exist."""

    source = source_frame.copy()
    source["promotion_row_key"] = source["promotion_row_key"].astype(str)
    publish_columns = [
        column_name
        for column_name in ("publish_eligibility_reason", "publish_eligibility_class", "review_reason", "primary_review_reason")
        if column_name in source.columns
    ]
    if not publish_columns:
        empty = pd.Series(0, index=row_keys.index, dtype="int64")
        return {
            "review_only_flag": empty,
            "published_flag": empty,
            "publish_mix_available_flag": empty,
        }
    context = source[["promotion_row_key", *publish_columns]].drop_duplicates("promotion_row_key")
    merged = pd.DataFrame({"promotion_row_key": row_keys.astype(str)}).merge(context, on="promotion_row_key", how="left")
    eligibility = _first_present_text_series(merged, ("publish_eligibility_reason", "publish_eligibility_class")).str.lower()
    review_reason = _first_present_text_series(merged, ("review_reason", "primary_review_reason")).str.lower()
    review_only = eligibility.str.contains("review", na=False) | review_reason.str.contains("review", na=False)
    published = eligibility.str.contains("publish", na=False) & ~review_only
    return {
        "review_only_flag": review_only.astype(int),
        "published_flag": published.astype(int),
        "publish_mix_available_flag": pd.Series(1, index=row_keys.index, dtype="int64"),
    }


def _empty_scorecard_summary() -> dict[str, object]:
    """Return a typed empty summary for skipped or empty scorecard outputs."""

    return {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "diagnostics_only": True,
        "completed_promotions_evaluated": 0,
        "trust_floor_breach_count": 0,
        "trust_floor_breach_rate": 0.0,
        "missed_demand_units_below_trust_floor": 0.0,
        "estimated_gross_profit_missed_from_below_floor_stockouts": 0.0,
        "over_allocation_units_above_trust_floor": 0.0,
        "over_allocation_capital_tied_up": 0.0,
        "capital_drag_dollars": 0.0,
        "gross_profit_captured_proxy_dollars": 0.0,
        "missed_upside_units": 0.0,
        "effective_sharpe_like_gp_per_drag_mean": 0.0,
        "gp_per_capital_committed_mean": 0.0,
        "gp_per_speculative_capital_mean": 0.0,
        "sell_through_on_accepted_capital_mean": 0.0,
        "recommended_order_units_success_rate": 0.0,
        "target_soh_at_promo_start_success_rate": 0.0,
        "stockout_avoidance_success_rate": 0.0,
        "convex_upside_captured_rate": 0.0,
        "dead_capital_burden_count": 0,
        "high_demand_underprotection_count": 0,
        "end_shape_success_rate": 0.0,
        "shape_2_achieved_count": 0,
        "acceptable_new_line_shape_count": 0,
        "high_demand_14d_success_rate": 0.0,
        "month_end_run_down_success_rate": 0.0,
        "mean_absolute_pct_error": 0.0,
        "within_10pct_rate": 0.0,
        "within_20pct_rate": 0.0,
        "period_absolute_error_units_per_day_mean": 0.0,
        "same_discount_history_available_row_count": 0,
        "same_discount_history_missing_row_count": 0,
        "same_discount_available_within_20pct_rate": 0.0,
        "same_discount_missing_within_20pct_rate": 0.0,
        "publish_mix_available_flag": False,
        "published_row_count": None,
        "review_only_row_count": None,
    }


def _policy_class_counts(policy_audit: pd.DataFrame) -> dict[str, int]:
    """Count primary trust-floor/shape policy classes for JSON summaries."""

    if policy_audit.empty:
        return {}
    counts = policy_audit["trust_floor_shape_policy_class"].astype(str).value_counts().sort_index()
    return {str(policy_class): int(count) for policy_class, count in counts.items()}


def _source_context_value_columns() -> tuple[str, ...]:
    """Return source context column names that must merge onto every scorecard row."""

    return tuple(output_name for output_name, _ in REQUIRED_SOURCE_CONTEXT_COLUMN_GROUPS)


def _first_required_numeric_series(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
    *,
    output_name: str,
) -> pd.Series:
    """Return the first available numeric evidence column or fail loud."""

    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        raise PromotionExecutionScorecardError(
            f"Scorecard missing governed input for {output_name}: expected one of {column_names}"
        )
    candidate_frame = frame[present_columns].apply(pd.to_numeric, errors="coerce")
    values = candidate_frame.bfill(axis=1).iloc[:, 0]
    if values.isna().any():
        missing_count = int(values.isna().sum())
        raise PromotionExecutionScorecardError(
            f"Scorecard governed input {output_name} has {missing_count} null row(s)"
        )
    return values


def _first_present_text_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    """Return the first non-empty text series from candidate columns."""

    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series("", index=frame.index, dtype="object")
    candidate_frame = frame[present_columns].fillna("").astype(str).replace("", pd.NA)
    return candidate_frame.bfill(axis=1).iloc[:, 0].fillna("")


def _raise_for_missing_columns(frame: pd.DataFrame, required_columns: tuple[str, ...], *, frame_name: str) -> None:
    """Raise a scorecard error when a required diagnostics column is absent."""

    missing = [column_name for column_name in required_columns if column_name not in frame.columns]
    if missing:
        raise PromotionExecutionScorecardError(f"{frame_name} missing required columns: {missing}")


def _numeric(series: pd.Series) -> pd.Series:
    """Convert a governed diagnostics series to numeric without inventing zeros."""

    return pd.to_numeric(series, errors="coerce")


def _rate(frame: pd.DataFrame, column_name: str) -> float:
    """Return a rounded mean rate for a binary diagnostics column."""

    if frame.empty:
        return 0.0
    return round(float(_numeric(frame[column_name]).mean()), 4)