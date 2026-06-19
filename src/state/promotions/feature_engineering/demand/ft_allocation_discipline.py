from __future__ import annotations

"""Probability-backed allocation discipline ft module."""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


_TRUST_FLOOR_UNITS = 2.0


ALLOCATION_DISCIPLINE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_allocation_vs_probability_expected_units_ratio",
    "feature_allocated_units_minus_probability_expected_units",
    "feature_probability_expected_excess_units",
    "feature_probability_expected_excess_units_pct",
    "feature_probability_expected_sell_through_pct",
    "feature_probability_excess_capital_at_risk",
    "feature_probability_allocation_discipline_score",
    "feature_allocation_vs_uplift_supported_units_ratio",
    "feature_allocated_units_minus_uplift_supported_units",
    "feature_uplift_supported_excess_units",
    "feature_uplift_supported_excess_units_pct",
    "feature_uplift_supported_sell_through_pct",
    "feature_uplift_supported_excess_capital_at_risk",
    "feature_uplift_allocation_discipline_score",
    "feature_allocation_vs_baseline_gap_units",
    "feature_allocation_vs_uplift_supported_gap_units",
    "feature_allocation_vs_supported_total_gap_units",
    "feature_supported_sell_through_score",
    "feature_discount_evidence_strength_score",
    "feature_allocation_risk_over_uplift_score",
    "feature_launch_stock_support_score",
    "feature_total_window_pressure_vs_launch_support_conflict_score",
    "feature_base_soh_trust_floor_units",
    "feature_stock_below_trust_floor_flag",
    "feature_projected_stock_gap_to_trust_floor_units",
    "feature_units_needed_for_trust_floor",
    "feature_units_needed_for_high_demand_cover",
    "feature_trust_floor_missed_demand_risk_score",
    "feature_expected_lost_units_below_trust_floor",
    "feature_demand_pressure_vs_total_available_stock_ratio",
    "feature_units_above_trust_floor",
    "feature_units_above_trust_target",
    "feature_expected_residual_stock_units",
    "feature_expected_leftover_above_trust_floor_units",
    "feature_expected_bill_cycle_capital_drag_dollars",
    "feature_capital_tied_above_trust_target",
    "feature_expected_bill_cycle_capital_drag_ratio",
    "feature_expected_gp_on_trust_floor_units",
    "feature_expected_gp_on_speculative_units",
    "feature_expected_gp_per_capital_committed",
    "feature_risk_adjusted_value_of_speculative_units",
    "feature_speculative_above_trust_floor_risk_flag",
    "feature_pre_promo_cover_ratio",
    "feature_inventory_sufficiency_flag",
    "feature_capital_at_risk_per_expected_unit",
    "feature_gross_profit_per_incremental_unit_expected",
    "feature_weak_promo_low_value_flag",
)


def apply_ft_allocation_discipline(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append allocation-discipline features for trust floor and capital exposure.

    Purpose:
        Compare supported promo demand to available stock, then separate
        trust-floor protection from speculative-above-floor exposure so later
        model and policy layers can suppress dead capital without masking genuine
        low-stock trust risk.

    Inputs:
        frame: row-grain promotion candidates with governed baseline, uplift,
            stock, and economics inputs.
        reference_frame: accepted for registry compatibility but unused because
            this feature family is row-local once upstream history features
            exist.

    Outputs:
        A copy of ``frame`` with the declared allocation-discipline
        ``feature_*`` columns appended.

    Important assumptions:
        Upstream baseline, uplift, stock, and cost fields have already been
        engineered or extracted. Historical actuals may only enter through the
        explicit prior-memory features already present on the row.

    Side effects:
        None. The function copies the input frame before appending columns.

    Failure behaviour:
        Missing optional inputs degrade to explicit ``NaN`` where the evidence
        is required. Legitimate zero outcomes remain zero, but the function does
        not infer future actuals or backfill hidden defaults for historical
        memory, cost, or committed-capital evidence.
    """

    del reference_frame
    working = frame.copy()
    stock_basis = _first_present_numeric_series(
        working,
        ("stock_basis_units", "total_stock_available", "pl_allocated"),
    ).clip(lower=0.0)
    unit_cost = _optional_numeric_series(working, "effective_cost_per_unit")
    baseline_expected_units = _first_present_numeric_series(
        working,
        ("feature_expected_baseline_units_promo_window", "feature_baseline_units_expected_promo_window"),
    )
    expected_units = _optional_numeric_series(working, "feature_probability_expected_units_consensus")
    demand_confidence = _optional_numeric_series(working, "feature_probability_demand_confidence_score").clip(
        lower=0.0,
        upper=1.0,
    )
    uplift_supported_units = _first_present_numeric_series(
        working,
        ("feature_expected_incremental_uplift_units_same_discount", "feature_probability_uplift_supported_units"),
    )
    uplift_upper_units = _first_present_numeric_series(
        working,
        ("feature_expected_incremental_uplift_units_same_discount", "feature_probability_uplift_upper_units"),
    )
    uplift_confidence = _first_present_numeric_series(
        working,
        ("feature_uplift_confidence_score", "feature_probability_uplift_confidence"),
    ).clip(
        lower=0.0,
        upper=1.0,
    )
    elasticity_confidence = _optional_numeric_series(working, "feature_discount_elasticity_confidence_score").clip(
        lower=0.0,
        upper=1.0,
    )
    same_discount_history_available = _optional_numeric_series(
        working,
        "feature_same_discount_history_available_flag",
    ).clip(lower=0.0, upper=1.0)
    same_discount_event_count = _first_present_numeric_series(
        working,
        ("feature_same_discount_prior_event_count", "feature_uplift_support_event_count"),
    )
    window_blend_conflict = _first_present_numeric_series(
        working,
        (
            "feature_total_window_pressure_vs_launch_support_conflict_score",
            "feature_window_blend_conflict_score",
        ),
    ).fillna(0.0).clip(
        lower=0.0,
        upper=1.0,
    )
    supported_total_units = _first_present_numeric_series(
        working,
        ("feature_expected_total_units_from_baseline_plus_uplift", "feature_probability_expected_units_consensus"),
    )
    expected_total_units = supported_total_units.where(supported_total_units.notna(), baseline_expected_units).clip(lower=0.0)
    launch_supported_units = _first_present_numeric_series(
        working,
        ("feature_expected_total_units_first_7_days", "feature_expected_baseline_units_first_7_days"),
    )
    model_use_flag = _optional_numeric_series(working, "feature_probability_model_use_flag")
    supported_probability = expected_units.gt(0.0) & model_use_flag.eq(1.0)
    supported_expected_units = expected_units.where(supported_probability)
    uplift_supported_total_units = (baseline_expected_units + uplift_supported_units).where(
        uplift_supported_units.notna(),
        supported_total_units.where(supported_total_units.notna(), supported_expected_units),
    )
    uplift_supported_upper_units = (baseline_expected_units + uplift_upper_units).where(
        uplift_upper_units.notna(),
        uplift_supported_total_units,
    )
    supported_uplift_probability = uplift_supported_total_units.gt(0.0) & (
        model_use_flag.eq(1.0) | same_discount_history_available.eq(1.0)
    )
    allocation_support_available = model_use_flag.eq(1.0) | same_discount_history_available.eq(1.0)
    uplift_supported_total_units = uplift_supported_total_units.where(supported_uplift_probability)
    uplift_supported_upper_units = uplift_supported_upper_units.where(supported_uplift_probability)
    discount_evidence_strength_score = _rowwise_nanmean(
        [
            same_discount_history_available,
            (same_discount_event_count / 4.0).clip(lower=0.0, upper=1.0),
            uplift_confidence,
            elasticity_confidence,
        ]
    ).fillna(0.0).clip(lower=0.0, upper=1.0)

    allocation_gap = stock_basis - supported_expected_units
    expected_excess_units = allocation_gap.clip(lower=0.0)
    stock_excess_share = _nan_ratio(expected_excess_units, stock_basis).clip(lower=0.0, upper=1.0)
    uplift_allocation_gap = stock_basis - uplift_supported_total_units
    uplift_supported_excess_units = (stock_basis - uplift_supported_upper_units).clip(lower=0.0)
    uplift_stock_excess_share = _nan_ratio(uplift_supported_excess_units, stock_basis).clip(lower=0.0, upper=1.0)
    allocation_vs_supported_total_gap_units = stock_basis - uplift_supported_total_units
    supported_sell_through_score = _nan_ratio(uplift_supported_total_units, stock_basis).clip(lower=0.0, upper=1.0)
    launch_stock_support_score = _nan_ratio(launch_supported_units, stock_basis).clip(lower=0.0, upper=1.0)
    total_window_pressure = _nan_ratio(uplift_supported_total_units, stock_basis).clip(lower=0.0, upper=20.0)
    legacy_uplift_allocation_discipline_score = (
        uplift_stock_excess_share
        * uplift_confidence.where(supported_uplift_probability, demand_confidence)
        * (1.0 - window_blend_conflict.where(supported_uplift_probability, 0.0))
    ).clip(lower=0.0, upper=1.0)
    total_window_vs_launch_conflict = _rowwise_nanmean(
        [
            (total_window_pressure - launch_stock_support_score).clip(lower=0.0, upper=1.0),
            (1.0 - uplift_confidence),
            (1.0 - discount_evidence_strength_score),
        ]
    ).clip(lower=0.0, upper=1.0)
    allocation_risk_over_uplift_score = _rowwise_nanmean(
        [
            _nan_ratio(
                allocation_vs_supported_total_gap_units.clip(lower=0.0),
                stock_basis,
            ).clip(lower=0.0, upper=1.0),
            (1.0 - discount_evidence_strength_score),
            (1.0 - launch_stock_support_score),
            total_window_vs_launch_conflict,
        ]
    ).clip(lower=0.0, upper=1.0)
    uplift_allocation_discipline_score = legacy_uplift_allocation_discipline_score
    legacy_allocation_discipline_score = (
        stock_excess_share * demand_confidence.where(supported_probability)
    ).clip(lower=0.0, upper=1.0)

    current_soh_units = _first_present_numeric_series(working, ("current_soh", "current_soh_units")).clip(lower=0.0)
    qty_on_order_units = _first_present_numeric_series(working, ("qty_on_order", "qty_on_order_units")).clip(lower=0.0)
    baseline_daily_units = _first_present_numeric_series(
        working,
        ("feature_pre_promo_baseline_daily_units", "baseline_daily_units"),
    ).clip(lower=0.0)
    as_of_dates = _first_present_datetime_series(working, ("as_of_date", "extraction_as_of_date"))
    promotion_start_dates = _first_present_datetime_series(working, ("promotion_start_date_date", "promotion_start_date"))
    days_until_promo_start = (promotion_start_dates - as_of_dates).dt.days.astype("float64")
    days_until_promo_start = days_until_promo_start.where(
        as_of_dates.notna() & promotion_start_dates.notna(),
        0.0,
    )
    lead_up_demand_units = baseline_daily_units.multiply(days_until_promo_start.clip(lower=0.0)).clip(lower=0.0)
    projected_available_units_at_promo_start = (
        current_soh_units + qty_on_order_units - lead_up_demand_units
    ).clip(lower=0.0)
    expected_total_units_denominator = expected_total_units.where(expected_total_units.gt(0.0), 1.0).where(
        expected_total_units.notna(),
    )
    pre_promo_cover_ratio = _nan_ratio(
        projected_available_units_at_promo_start,
        expected_total_units_denominator,
    ).clip(lower=0.0, upper=20.0)
    inventory_evidence_available = projected_available_units_at_promo_start.notna() & expected_total_units.notna()
    inventory_sufficiency_flag = projected_available_units_at_promo_start.ge(
        expected_total_units.clip(lower=0.0),
    ).astype(float).where(inventory_evidence_available)

    capital_at_risk = _first_present_numeric_series(working, ("feature_capital_at_risk",))
    capital_at_risk = capital_at_risk.where(capital_at_risk.ge(0.0)).clip(lower=0.0)
    capital_at_risk_per_expected_unit = capital_at_risk.divide(expected_total_units_denominator).replace([np.inf, -np.inf], np.nan)

    expected_incremental_units = uplift_supported_units.clip(lower=0.0)
    expected_incremental_share = _nan_ratio(expected_incremental_units, expected_total_units_denominator).clip(
        lower=0.0,
        upper=1.0,
    )
    promo_gm_unit = _first_present_numeric_series(working, ("promo_gm_unit",))
    gross_profit_total = _first_present_numeric_series(working, ("gross_profit_promo_dollars",))
    gross_profit_per_incremental_unit_expected = promo_gm_unit.where(
        promo_gm_unit.notna(),
        _nan_ratio(gross_profit_total, expected_total_units_denominator),
    )

    historical_under_floor_missed_demand_rate = _optional_numeric_series(
        working,
        "feature_historical_under_floor_missed_demand_rate",
    ).clip(lower=0.0, upper=1.0)
    trust_floor_metrics = _build_trust_floor_capital_metrics(
        projected_available_units_at_promo_start=projected_available_units_at_promo_start,
        expected_total_units=expected_total_units,
        expected_incremental_units=expected_incremental_units,
        target_end_stock_units=_first_present_numeric_series(
            working,
            ("feature_end_of_promo_target_units",),
        ),
        high_base_demand_flag=_optional_numeric_series(
            working,
            "feature_high_base_demand_end_cover_flag",
        ),
        capital_at_risk=capital_at_risk,
        unit_cost=unit_cost,
        gross_profit_per_incremental_unit_expected=gross_profit_per_incremental_unit_expected,
        historical_under_floor_missed_demand_rate=historical_under_floor_missed_demand_rate,
    )

    historical_zero_sale_after_buy_rate = _optional_numeric_series(
        working,
        "feature_historical_zero_sale_after_buy_rate",
    ).clip(lower=0.0, upper=1.0)
    same_discount_success_rate = _optional_numeric_series(
        working,
        "feature_same_discount_success_rate_56d",
    ).clip(lower=0.0, upper=1.0)
    historical_trapped_capital_rate = _optional_numeric_series(
        working,
        "feature_historical_trapped_capital_rate",
    ).clip(lower=0.0, upper=1.0)
    historical_sell_through = _optional_numeric_series(
        working,
        "feature_historical_sell_through_on_accepted_qty",
    ).clip(lower=0.0, upper=1.0)
    historical_overforecast_bias = _optional_numeric_series(
        working,
        "feature_historical_overforecast_bias",
    ).clip(lower=0.0, upper=1.0)
    historical_allocation_efficiency_rate = _optional_numeric_series(
        working,
        "feature_historical_allocation_efficiency_rate",
    ).clip(lower=0.0, upper=1.0)
    historical_overallocation_above_floor_rate = _optional_numeric_series(
        working,
        "feature_historical_overallocation_above_floor_rate",
    ).clip(lower=0.0, upper=1.0)
    historical_event_count = _optional_numeric_series(
        working,
        "feature_historical_comparable_promo_event_count",
    ).clip(lower=0.0)
    historical_signal_available = historical_event_count.ge(2.0)
    severe_history_failure_count = pd.concat(
        [
            historical_zero_sale_after_buy_rate.ge(0.25),
            same_discount_success_rate.le(0.35) & same_discount_success_rate.notna(),
            historical_trapped_capital_rate.ge(0.30),
            historical_sell_through.le(0.60) & historical_sell_through.notna(),
            historical_overforecast_bias.ge(0.25),
        ],
        axis=1,
    ).sum(axis=1).astype("float64")
    value_to_capital_ratio = _nan_ratio(
        gross_profit_per_incremental_unit_expected.clip(lower=0.0),
        capital_at_risk_per_expected_unit.where(capital_at_risk_per_expected_unit.gt(0.0)),
    )
    weak_promo_low_value_flag = _build_weak_promo_low_value_flag(
        inventory_sufficiency_flag=inventory_sufficiency_flag,
        expected_incremental_share=expected_incremental_share,
        expected_incremental_units=expected_incremental_units,
        gross_profit_per_incremental_unit_expected=gross_profit_per_incremental_unit_expected,
        capital_at_risk_per_expected_unit=capital_at_risk_per_expected_unit,
        expected_gp_per_capital_committed=trust_floor_metrics["feature_expected_gp_per_capital_committed"],
        stock_below_trust_floor_flag=trust_floor_metrics["feature_stock_below_trust_floor_flag"],
        trust_floor_missed_demand_risk_score=trust_floor_metrics["feature_trust_floor_missed_demand_risk_score"],
        speculative_above_trust_floor_risk_flag=trust_floor_metrics["feature_speculative_above_trust_floor_risk_flag"],
        historical_signal_available=historical_signal_available,
        historical_allocation_efficiency_rate=historical_allocation_efficiency_rate,
        historical_overallocation_above_floor_rate=historical_overallocation_above_floor_rate,
        historical_trapped_capital_rate=historical_trapped_capital_rate,
        historical_sell_through=historical_sell_through,
        severe_history_failure_count=severe_history_failure_count,
        value_to_capital_ratio=value_to_capital_ratio,
    )

    derived_columns = pd.DataFrame(
        {
            "feature_allocation_vs_probability_expected_units_ratio": _nan_ratio(
                stock_basis,
                supported_expected_units,
            ).clip(lower=0.0, upper=20.0),
            "feature_allocated_units_minus_probability_expected_units": allocation_gap,
            "feature_probability_expected_excess_units": expected_excess_units,
            "feature_probability_expected_excess_units_pct": _nan_ratio(
                expected_excess_units,
                supported_expected_units,
            ).clip(lower=0.0, upper=20.0),
            "feature_probability_expected_sell_through_pct": _nan_ratio(
                supported_expected_units,
                stock_basis,
            ).clip(lower=0.0, upper=1.0),
            "feature_probability_excess_capital_at_risk": expected_excess_units * unit_cost,
            "feature_probability_allocation_discipline_score": uplift_allocation_discipline_score.where(
                supported_uplift_probability & uplift_supported_units.notna(),
                legacy_allocation_discipline_score,
            ),
            "feature_allocation_vs_uplift_supported_units_ratio": _nan_ratio(
                stock_basis,
                uplift_supported_total_units,
            ).clip(lower=0.0, upper=20.0),
            "feature_allocated_units_minus_uplift_supported_units": uplift_allocation_gap,
            "feature_uplift_supported_excess_units": uplift_supported_excess_units,
            "feature_uplift_supported_excess_units_pct": _nan_ratio(
                uplift_supported_excess_units,
                uplift_supported_upper_units,
            ).clip(lower=0.0, upper=20.0),
            "feature_uplift_supported_sell_through_pct": supported_sell_through_score,
            "feature_uplift_supported_excess_capital_at_risk": uplift_supported_excess_units * unit_cost,
            "feature_uplift_allocation_discipline_score": uplift_allocation_discipline_score,
            "feature_allocation_vs_baseline_gap_units": (stock_basis - baseline_expected_units).where(
                allocation_support_available,
            ),
            "feature_allocation_vs_uplift_supported_gap_units": (stock_basis - uplift_supported_units).where(
                allocation_support_available,
            ),
            "feature_allocation_vs_supported_total_gap_units": allocation_vs_supported_total_gap_units.where(
                allocation_support_available,
            ),
            "feature_supported_sell_through_score": supported_sell_through_score.where(allocation_support_available),
            "feature_discount_evidence_strength_score": discount_evidence_strength_score.where(
                allocation_support_available,
            ),
            "feature_allocation_risk_over_uplift_score": allocation_risk_over_uplift_score.where(
                allocation_support_available,
            ),
            "feature_launch_stock_support_score": launch_stock_support_score.where(allocation_support_available),
            "feature_total_window_pressure_vs_launch_support_conflict_score": total_window_vs_launch_conflict.where(
                allocation_support_available,
            ),
            "feature_base_soh_trust_floor_units": trust_floor_metrics["feature_base_soh_trust_floor_units"],
            "feature_stock_below_trust_floor_flag": trust_floor_metrics["feature_stock_below_trust_floor_flag"],
            "feature_projected_stock_gap_to_trust_floor_units": trust_floor_metrics[
                "feature_projected_stock_gap_to_trust_floor_units"
            ],
            "feature_units_needed_for_trust_floor": trust_floor_metrics["feature_units_needed_for_trust_floor"],
            "feature_units_needed_for_high_demand_cover": trust_floor_metrics[
                "feature_units_needed_for_high_demand_cover"
            ],
            "feature_trust_floor_missed_demand_risk_score": trust_floor_metrics[
                "feature_trust_floor_missed_demand_risk_score"
            ],
            "feature_expected_lost_units_below_trust_floor": trust_floor_metrics[
                "feature_expected_lost_units_below_trust_floor"
            ],
            "feature_demand_pressure_vs_total_available_stock_ratio": trust_floor_metrics[
                "feature_demand_pressure_vs_total_available_stock_ratio"
            ],
            "feature_units_above_trust_floor": trust_floor_metrics["feature_units_above_trust_floor"],
            "feature_units_above_trust_target": trust_floor_metrics["feature_units_above_trust_target"],
            "feature_expected_residual_stock_units": trust_floor_metrics["feature_expected_residual_stock_units"],
            "feature_expected_leftover_above_trust_floor_units": trust_floor_metrics[
                "feature_expected_leftover_above_trust_floor_units"
            ],
            "feature_expected_bill_cycle_capital_drag_dollars": trust_floor_metrics[
                "feature_expected_bill_cycle_capital_drag_dollars"
            ],
            "feature_capital_tied_above_trust_target": trust_floor_metrics[
                "feature_capital_tied_above_trust_target"
            ],
            "feature_expected_bill_cycle_capital_drag_ratio": trust_floor_metrics[
                "feature_expected_bill_cycle_capital_drag_ratio"
            ],
            "feature_expected_gp_on_trust_floor_units": trust_floor_metrics[
                "feature_expected_gp_on_trust_floor_units"
            ],
            "feature_expected_gp_on_speculative_units": trust_floor_metrics[
                "feature_expected_gp_on_speculative_units"
            ],
            "feature_expected_gp_per_capital_committed": trust_floor_metrics[
                "feature_expected_gp_per_capital_committed"
            ],
            "feature_risk_adjusted_value_of_speculative_units": trust_floor_metrics[
                "feature_risk_adjusted_value_of_speculative_units"
            ],
            "feature_speculative_above_trust_floor_risk_flag": trust_floor_metrics[
                "feature_speculative_above_trust_floor_risk_flag"
            ],
            "feature_pre_promo_cover_ratio": pre_promo_cover_ratio,
            "feature_inventory_sufficiency_flag": inventory_sufficiency_flag,
            "feature_capital_at_risk_per_expected_unit": capital_at_risk_per_expected_unit,
            "feature_gross_profit_per_incremental_unit_expected": gross_profit_per_incremental_unit_expected,
            "feature_weak_promo_low_value_flag": weak_promo_low_value_flag,
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _build_trust_floor_capital_metrics(
    *,
    projected_available_units_at_promo_start: pd.Series,
    expected_total_units: pd.Series,
    expected_incremental_units: pd.Series,
    target_end_stock_units: pd.Series,
    high_base_demand_flag: pd.Series,
    capital_at_risk: pd.Series,
    unit_cost: pd.Series,
    gross_profit_per_incremental_unit_expected: pd.Series,
    historical_under_floor_missed_demand_rate: pd.Series,
) -> pd.DataFrame:
    """Build row-local trust-floor and speculative-capital exposure features.

    Purpose:
        Translate projected starting stock, expected demand, and governed
        historical under-floor memory into explicit floor-protection and
        above-floor capital-risk diagnostics.

    Inputs:
        projected_available_units_at_promo_start: expected stock available when
            the promotion starts after lead-up demand.
        expected_total_units: governed expected total promo demand.
        expected_incremental_units: expected promo-only uplift units.
        target_end_stock_units: governed end-of-promo stock target from the
            target-stock feature family.
        high_base_demand_flag: whether the target-stock family selected the
            high-demand cover regime.
        capital_at_risk: governed stock capital currently exposed on the row.
        unit_cost: effective cost per unit.
        gross_profit_per_incremental_unit_expected: expected gross profit per
            incremental unit.
        historical_under_floor_missed_demand_rate: prior-memory rate showing how
            often comparable under-floor promos likely missed demand.

    Outputs:
        A frame of explicit trust-floor and speculative-above-floor features.

    Important assumptions:
        The trust floor is a governed base floor of two units. Historical
        under-floor memory is already leakage-safe and row-local by the time it
        reaches this helper.

    Side effects:
        None.

    Failure behaviour:
        Missing required stock, demand, cost, or committed-capital inputs remain
        ``NaN`` in dependent outputs. The helper does not synthesize future
        outcomes or convert unknown economics into low-risk zeros.
    """

    trust_floor_units = pd.Series(_TRUST_FLOOR_UNITS, index=projected_available_units_at_promo_start.index, dtype="float64")
    projected_available = pd.to_numeric(projected_available_units_at_promo_start, errors="coerce").clip(lower=0.0)
    expected_total = pd.to_numeric(expected_total_units, errors="coerce").clip(lower=0.0)
    expected_incremental = pd.to_numeric(expected_incremental_units, errors="coerce").clip(lower=0.0)
    target_end_stock = pd.to_numeric(target_end_stock_units, errors="coerce")
    target_end_stock = target_end_stock.where(target_end_stock.notna(), trust_floor_units).clip(lower=0.0)
    high_demand_flag = pd.to_numeric(high_base_demand_flag, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    capital_exposed = pd.to_numeric(capital_at_risk, errors="coerce").clip(lower=0.0)
    unit_cost_numeric = pd.to_numeric(unit_cost, errors="coerce").clip(lower=0.0)
    gross_profit_per_incremental = pd.to_numeric(
        gross_profit_per_incremental_unit_expected,
        errors="coerce",
    )
    under_floor_history = pd.to_numeric(historical_under_floor_missed_demand_rate, errors="coerce").clip(0.0, 1.0)

    core_stock_demand_available = projected_available.notna() & expected_total.notna()
    projected_stock_gap_to_trust_floor_units = (trust_floor_units - projected_available).clip(lower=0.0)
    units_needed_for_trust_floor = (expected_total + trust_floor_units - projected_available).clip(lower=0.0)
    units_needed_for_high_demand_cover = (
        expected_total + target_end_stock - projected_available - units_needed_for_trust_floor
    ).clip(lower=0.0).where(high_demand_flag.ge(1.0), 0.0)
    stock_below_trust_floor_flag = projected_available.lt(_TRUST_FLOOR_UNITS).astype(float).where(
        projected_available.notna(),
    )
    available_stock_denominator = projected_available.where(projected_available.gt(0.0), 1.0).where(
        projected_available.notna(),
    )
    demand_pressure_vs_total_available_stock_ratio = _nan_ratio(expected_total, available_stock_denominator).clip(
        lower=0.0,
        upper=20.0,
    )
    demand_pressure_score = demand_pressure_vs_total_available_stock_ratio.divide(
        1.0 + demand_pressure_vs_total_available_stock_ratio,
    ).clip(lower=0.0, upper=1.0)
    trust_floor_gap_share = _nan_ratio(projected_stock_gap_to_trust_floor_units, trust_floor_units).clip(
        lower=0.0,
        upper=1.0,
    )
    trust_floor_missed_demand_risk_score = _rowwise_nanmean(
        [
            trust_floor_gap_share.where(stock_below_trust_floor_flag.ge(1.0)),
            demand_pressure_score.where(stock_below_trust_floor_flag.ge(1.0)),
            under_floor_history.where(stock_below_trust_floor_flag.ge(1.0)),
        ]
    ).fillna(0.0).where(core_stock_demand_available).clip(lower=0.0, upper=1.0)
    trust_floor_supported_demand_units = pd.concat([expected_total, trust_floor_units], axis=1).min(axis=1)
    expected_lost_units_below_trust_floor = (
        (trust_floor_supported_demand_units - projected_available).clip(lower=0.0)
        * trust_floor_missed_demand_risk_score
    ).clip(lower=0.0)
    units_above_trust_floor = (projected_available - trust_floor_units).clip(lower=0.0)
    expected_residual_stock_units = (projected_available - expected_total).clip(lower=0.0)
    units_above_trust_target = (expected_residual_stock_units - target_end_stock).clip(lower=0.0)
    expected_leftover_above_trust_floor_units = (expected_residual_stock_units - trust_floor_units).clip(lower=0.0)
    expected_bill_cycle_capital_drag_dollars = (expected_leftover_above_trust_floor_units * unit_cost_numeric).clip(lower=0.0)
    capital_tied_above_trust_target = (units_above_trust_target * unit_cost_numeric).clip(lower=0.0)
    expected_bill_cycle_capital_drag_ratio = _nan_ratio(
        expected_bill_cycle_capital_drag_dollars,
        capital_exposed.where(capital_exposed.gt(0.0), np.nan),
    ).clip(lower=0.0, upper=1.0)
    trust_floor_sales_units = pd.concat([expected_total, trust_floor_units], axis=1).min(axis=1)
    speculative_sales_capacity_units = units_above_trust_floor.where(units_above_trust_floor.notna())
    speculative_expected_sales_units = pd.concat(
        [(expected_total - trust_floor_sales_units).clip(lower=0.0), speculative_sales_capacity_units],
        axis=1,
    ).min(axis=1)
    expected_gp_on_trust_floor_units = (
        trust_floor_sales_units * gross_profit_per_incremental.clip(lower=0.0)
    ).clip(lower=0.0)
    expected_gp_on_speculative_units = (
        speculative_expected_sales_units * gross_profit_per_incremental.clip(lower=0.0)
    ).clip(lower=0.0)
    expected_gp_per_capital_committed = _nan_ratio(
        gross_profit_per_incremental.clip(lower=0.0) * expected_incremental,
        capital_exposed.where(capital_exposed.gt(0.0), np.nan),
    ).clip(lower=0.0)
    risk_adjusted_value_of_speculative_units = (
        expected_gp_on_speculative_units - capital_tied_above_trust_target
    )
    speculative_evidence_available = (
        units_above_trust_floor.notna()
        & expected_leftover_above_trust_floor_units.notna()
        & expected_bill_cycle_capital_drag_ratio.notna()
    )
    speculative_above_trust_floor_risk_flag = (
        units_above_trust_floor.ge(1.0)
        & expected_leftover_above_trust_floor_units.ge(1.0)
        & expected_bill_cycle_capital_drag_ratio.ge(0.15)
    ).astype(float).where(speculative_evidence_available)

    return pd.DataFrame(
        {
            "feature_base_soh_trust_floor_units": trust_floor_units,
            "feature_stock_below_trust_floor_flag": stock_below_trust_floor_flag,
            "feature_projected_stock_gap_to_trust_floor_units": projected_stock_gap_to_trust_floor_units,
            "feature_units_needed_for_trust_floor": units_needed_for_trust_floor,
            "feature_units_needed_for_high_demand_cover": units_needed_for_high_demand_cover,
            "feature_trust_floor_missed_demand_risk_score": trust_floor_missed_demand_risk_score,
            "feature_expected_lost_units_below_trust_floor": expected_lost_units_below_trust_floor,
            "feature_demand_pressure_vs_total_available_stock_ratio": demand_pressure_vs_total_available_stock_ratio,
            "feature_units_above_trust_floor": units_above_trust_floor,
            "feature_units_above_trust_target": units_above_trust_target,
            "feature_expected_residual_stock_units": expected_residual_stock_units,
            "feature_expected_leftover_above_trust_floor_units": expected_leftover_above_trust_floor_units,
            "feature_expected_bill_cycle_capital_drag_dollars": expected_bill_cycle_capital_drag_dollars,
            "feature_capital_tied_above_trust_target": capital_tied_above_trust_target,
            "feature_expected_bill_cycle_capital_drag_ratio": expected_bill_cycle_capital_drag_ratio,
            "feature_expected_gp_on_trust_floor_units": expected_gp_on_trust_floor_units,
            "feature_expected_gp_on_speculative_units": expected_gp_on_speculative_units,
            "feature_expected_gp_per_capital_committed": expected_gp_per_capital_committed,
            "feature_risk_adjusted_value_of_speculative_units": risk_adjusted_value_of_speculative_units,
            "feature_speculative_above_trust_floor_risk_flag": speculative_above_trust_floor_risk_flag,
        },
        index=projected_available_units_at_promo_start.index,
    )


def _build_weak_promo_low_value_flag(
    *,
    inventory_sufficiency_flag: pd.Series,
    expected_incremental_share: pd.Series,
    expected_incremental_units: pd.Series,
    gross_profit_per_incremental_unit_expected: pd.Series,
    capital_at_risk_per_expected_unit: pd.Series,
    expected_gp_per_capital_committed: pd.Series,
    stock_below_trust_floor_flag: pd.Series,
    trust_floor_missed_demand_risk_score: pd.Series,
    speculative_above_trust_floor_risk_flag: pd.Series,
    historical_signal_available: pd.Series,
    historical_allocation_efficiency_rate: pd.Series,
    historical_overallocation_above_floor_rate: pd.Series,
    historical_trapped_capital_rate: pd.Series,
    historical_sell_through: pd.Series,
    severe_history_failure_count: pd.Series,
    value_to_capital_ratio: pd.Series,
) -> pd.Series:
    """Build the governed low-value suppression flag from explicit risk layers.

    Purpose:
        Fire the low-value suppression flag only when the row has genuine
        speculative-above-floor exposure and dead-capital evidence, while
        protecting rows that still face trust-floor demand risk.

    Inputs:
        The current-row trust-floor metrics, incremental value metrics, and
        leakage-safe historical allocation memory signals.

    Outputs:
        A float flag series on ``0`` or ``1``.

    Important assumptions:
        Inventory sufficiency alone is not enough to mark a row low value. The
        row must also show material speculative above-floor exposure.

    Side effects:
        None.

    Failure behaviour:
        Missing historical metrics reduce the available evidence but do not
        create a false positive by themselves.
    """

    weak_incremental_support_flag = expected_incremental_share.le(0.35) | expected_incremental_units.le(1.0)
    low_incremental_value_flag = (
        gross_profit_per_incremental_unit_expected.le(0.0)
        | value_to_capital_ratio.le(0.35)
        | expected_gp_per_capital_committed.le(0.10)
    )
    trust_floor_protection_flag = stock_below_trust_floor_flag.ge(1.0) & trust_floor_missed_demand_risk_score.ge(0.35)
    dead_capital_history_flag = historical_signal_available & (
        historical_overallocation_above_floor_rate.ge(0.35)
        | historical_trapped_capital_rate.ge(0.30)
        | historical_allocation_efficiency_rate.le(0.60)
        | historical_sell_through.le(0.60)
        | severe_history_failure_count.ge(2.0)
    )
    core_evidence_available = (
        inventory_sufficiency_flag.notna()
        & expected_incremental_share.notna()
        & expected_incremental_units.notna()
        & gross_profit_per_incremental_unit_expected.notna()
        & capital_at_risk_per_expected_unit.notna()
        & expected_gp_per_capital_committed.notna()
        & stock_below_trust_floor_flag.notna()
        & trust_floor_missed_demand_risk_score.notna()
        & speculative_above_trust_floor_risk_flag.notna()
        & value_to_capital_ratio.notna()
    )
    low_value_flag = (
        inventory_sufficiency_flag.ge(1.0)
        & speculative_above_trust_floor_risk_flag.ge(1.0)
        & ~trust_floor_protection_flag
        & weak_incremental_support_flag
        & (low_incremental_value_flag | dead_capital_history_flag)
        & capital_at_risk_per_expected_unit.ge(0.0)
    ).astype(float)
    return low_value_flag.where(core_evidence_available)


def _optional_numeric_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce")


def _first_present_numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    candidate_frame = frame[present_columns].apply(pd.to_numeric, errors="coerce")
    return candidate_frame.bfill(axis=1).iloc[:, 0]


def _first_present_datetime_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    candidate_frame = frame[present_columns].apply(pd.to_datetime, errors="coerce")
    return pd.to_datetime(candidate_frame.bfill(axis=1).iloc[:, 0], errors="coerce")


def _nan_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator_clean = denominator.where(denominator.ne(0.0))
    return numerator.divide(denominator_clean).replace([np.inf, -np.inf], np.nan)


def _rowwise_nanmean(series_list: list[pd.Series]) -> pd.Series:
    combined = pd.concat([pd.to_numeric(series, errors="coerce") for series in series_list], axis=1)
    return combined.mean(axis=1, skipna=True).astype("float64")