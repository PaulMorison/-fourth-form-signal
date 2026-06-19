from __future__ import annotations

"""Registry of reusable promotions feature modules."""

from dataclasses import dataclass
from typing import Callable, Iterable

import pandas as pd

from state.promotions.feature_engineering.behavioural.ft_compensation_signals import apply_ft_compensation_signals
from state.promotions.feature_engineering.behavioural.ft_friction_signals import apply_ft_friction_signals
from state.promotions.feature_engineering.behavioural.ft_gravity_field import apply_ft_gravity_field
from state.promotions.feature_engineering.behavioural.ft_kuramoto_sync import apply_ft_kuramoto_sync
from state.promotions.feature_engineering.behavioural.ft_reality_gap import apply_ft_reality_gap
from state.promotions.feature_engineering.behavioural.ft_zeta_instability import apply_ft_zeta_instability
from state.promotions.feature_engineering.context.ft_category_context import apply_ft_category_context
from state.promotions.feature_engineering.context.ft_promo_field_context import apply_ft_promo_field_context
from state.promotions.feature_engineering.context.ft_store_context import apply_ft_store_context
from state.promotions.feature_engineering.context.ft_supplier_context import apply_ft_supplier_context
from state.promotions.feature_engineering.demand.ft_allocation_discipline import (
    ALLOCATION_DISCIPLINE_FEATURE_COLUMNS,
    apply_ft_allocation_discipline,
)
from state.promotions.feature_engineering.demand.ft_pca_residual_structure import (
    PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS,
    apply_ft_pca_residual_structure,
)
from state.promotions.feature_engineering.demand.ft_promotion_situational_awareness import (
    PROMOTION_SITUATIONAL_AWARENESS_FEATURE_COLUMNS,
    apply_ft_promotion_situational_awareness,
)
from state.promotions.feature_engineering.demand.ft_baseline_demand_orientation import (
    BASELINE_DEMAND_ORIENTATION_FEATURE_COLUMNS,
    apply_ft_baseline_demand_orientation,
)
from state.promotions.feature_engineering.demand.ft_discount_conditioned_demand import (
    DISCOUNT_CONDITIONED_DEMAND_FEATURE_COLUMNS,
    apply_ft_discount_conditioned_demand,
)
from state.promotions.feature_engineering.demand.ft_discount_elasticity import (
    DISCOUNT_ELASTICITY_FEATURE_COLUMNS,
    apply_ft_discount_elasticity,
)
from state.promotions.feature_engineering.demand.ft_growth_curve_shape import (
    GROWTH_CURVE_SHAPE_FEATURE_COLUMNS,
    apply_ft_growth_curve_shape,
)
from state.promotions.feature_engineering.demand.ft_growth_survival_interactions import (
    GROWTH_SURVIVAL_INTERACTION_FEATURE_COLUMNS,
    apply_ft_growth_survival_interactions,
)
from state.promotions.feature_engineering.demand.ft_order_decision_diagnostics import (
    ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS,
    apply_ft_order_decision_diagnostics,
)
from state.promotions.feature_engineering.demand.ft_baseline_demand import apply_ft_baseline_demand
from state.promotions.feature_engineering.demand.ft_basket_context_feature_bundle import (
    BASKET_HISTORY_FEATURE_BUNDLE_COLUMNS,
    apply_ft_basket_context_feature_bundle,
)
from state.promotions.feature_engineering.demand.ft_basket_structure_dependency import (
    BASKET_STRUCTURE_DEPENDENCY_FEATURE_COLUMNS,
    apply_ft_basket_structure_dependency,
)
from state.promotions.feature_engineering.demand.ft_basket_equilibrium import (
    BASKET_EQUILIBRIUM_FEATURE_COLUMNS,
    apply_ft_basket_equilibrium,
)
from state.promotions.feature_engineering.demand.ft_distribution_shape_distance import (
    DISTRIBUTION_SHAPE_DISTANCE_FEATURE_COLUMNS,
    apply_ft_distribution_shape_distance,
)
from state.promotions.feature_engineering.demand.ft_fragility_adjusted_opportunity import (
    FRAGILITY_ADJUSTED_OPPORTUNITY_FEATURE_COLUMNS,
    apply_ft_fragility_adjusted_opportunity,
)
from state.promotions.feature_engineering.demand.ft_history_regime import apply_ft_history_regime
from state.promotions.feature_engineering.demand.ft_intermittent_demand import (
    INTERMITTENT_DEMAND_FEATURE_COLUMNS,
    apply_ft_intermittent_demand,
)
from state.promotions.feature_engineering.demand.ft_kalman_state import (
    KALMAN_STATE_FEATURE_COLUMNS,
    apply_ft_kalman_state,
)
from state.promotions.feature_engineering.demand.ft_micro_market_equilibrium import (
    MICRO_MARKET_EQUILIBRIUM_FEATURE_COLUMNS,
    apply_ft_micro_market_equilibrium,
)
from state.promotions.feature_engineering.demand.ft_near_term_demand_shift import apply_ft_near_term_demand_shift
from state.promotions.feature_engineering.demand.ft_prior_promo_memory import (
    PRIOR_PROMO_MEMORY_FEATURE_COLUMNS,
    apply_ft_prior_promo_memory,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_feature_bundle import (
    PROBABILITY_FEATURE_BUNDLE_COLUMNS,
    apply_ft_probability_feature_bundle,
)
from state.promotions.feature_engineering.demand.ft_uplift_decomposition import (
    UPLIFT_DECOMPOSITION_FEATURE_COLUMNS,
    apply_ft_uplift_decomposition,
)
from state.promotions.feature_engineering.demand.ft_survival_convexity import (
    SURVIVAL_CONVEXITY_FEATURE_COLUMNS,
    apply_ft_survival_convexity,
)
from state.promotions.feature_engineering.demand.ft_sales_velocity import apply_ft_sales_velocity
from state.promotions.feature_engineering.demand.ft_sparse_demand_noise import (
    SPARSE_DEMAND_NOISE_FEATURE_COLUMNS,
    apply_ft_sparse_demand_noise,
)
from state.promotions.feature_engineering.economics.ft_fee_burden import apply_ft_fee_burden
from state.promotions.feature_engineering.economics.ft_inventory_capital_risk import apply_ft_inventory_capital_risk
from state.promotions.feature_engineering.economics.ft_margin_pressure import apply_ft_margin_pressure
from state.promotions.feature_engineering.economics.ft_rebate_economics import apply_ft_rebate_economics
from state.promotions.feature_engineering.economics.ft_unit_profitability import apply_ft_unit_profitability
from state.promotions.feature_engineering.stock.ft_allocation_pressure import apply_ft_allocation_pressure
from state.promotions.feature_engineering.stock.ft_commitment_pressure import apply_ft_commitment_pressure
from state.promotions.feature_engineering.stock.ft_cover_and_exposure import apply_ft_cover_and_exposure
from state.promotions.feature_engineering.stock.ft_overhang_risk import apply_ft_overhang_risk
from state.promotions.feature_engineering.stock.ft_stock_posture import apply_ft_stock_posture
from state.promotions.feature_engineering.stock.ft_target_stock_logic import (
    TARGET_STOCK_FEATURE_COLUMNS,
    apply_ft_target_stock_logic,
)
from state.promotions.feature_engineering.pricing.ft_catalogue_position import apply_ft_catalogue_position
from state.promotions.feature_engineering.pricing.ft_discount_depth import apply_ft_discount_depth
from state.promotions.feature_engineering.pricing.ft_offer_strength import apply_ft_offer_strength
from state.promotions.feature_engineering.pricing.ft_offer_text_flags import apply_ft_offer_text_flags
from state.promotions.feature_engineering.pricing.ft_price_gap import apply_ft_price_gap


PromotionFeatureApplyFn = Callable[[pd.DataFrame], pd.DataFrame]


@dataclass(frozen=True)
class PromotionFeatureModuleDefinition:
    name: str
    group: str
    apply_fn: Callable[..., pd.DataFrame]
    output_columns: tuple[str, ...]


FEATURE_MODULE_REGISTRY: tuple[PromotionFeatureModuleDefinition, ...] = (
    PromotionFeatureModuleDefinition("ft_discount_depth", "pricing", apply_ft_discount_depth, ("feature_discount_depth_pct",)),
    PromotionFeatureModuleDefinition("ft_price_gap", "pricing", apply_ft_price_gap, ("feature_price_gap_ex_gst", "feature_price_gap_pct_vs_normal", "feature_promo_price_ratio_vs_normal")),
    PromotionFeatureModuleDefinition("ft_offer_strength", "pricing", apply_ft_offer_strength, ("feature_offer_strength_score", "feature_low_ticket_flag", "feature_mid_ticket_flag", "feature_high_ticket_flag")),
    PromotionFeatureModuleDefinition("ft_offer_text_flags", "pricing", apply_ft_offer_text_flags, ("feature_offer_text_percent_flag", "feature_offer_text_amount_flag", "feature_offer_text_multi_buy_flag", "feature_offer_text_bonus_flag")),
    PromotionFeatureModuleDefinition("ft_catalogue_position", "pricing", apply_ft_catalogue_position, ("feature_catalogue_position_score", "feature_catalogue_top_quartile_flag", "feature_catalogue_front_half_flag")),
    PromotionFeatureModuleDefinition("ft_margin_pressure", "economics", apply_ft_margin_pressure, ("feature_effective_margin_compression_pct", "feature_margin_dollars_at_risk", "feature_expected_gm_change_dollars", "feature_margin_delta_per_unit", "feature_discount_to_margin_tradeoff")),
    PromotionFeatureModuleDefinition("ft_rebate_economics", "economics", apply_ft_rebate_economics, ("feature_rebate_adjusted_margin_pct", "feature_rebate_dependency_score", "feature_effective_cost_ratio")),
    PromotionFeatureModuleDefinition("ft_unit_profitability", "economics", apply_ft_unit_profitability, ("feature_unit_profit_after_fees", "feature_unit_profitability_ratio", "feature_margin_sacrifice_per_expected_unit")),
    PromotionFeatureModuleDefinition("ft_fee_burden", "economics", apply_ft_fee_burden, ("feature_fee_burden_ratio", "feature_fee_share_of_unit_margin")),
    PromotionFeatureModuleDefinition("ft_inventory_capital_risk", "economics", apply_ft_inventory_capital_risk, ("feature_capital_at_risk", "feature_inventory_carry_cost_burden", "feature_profit_risk_asymmetry", "feature_promo_capital_efficiency", "feature_gmroi_regime_score")),
    PromotionFeatureModuleDefinition("ft_allocation_pressure", "stock", apply_ft_allocation_pressure, ("feature_allocation_vs_baseline_demand_ratio", "feature_allocation_vs_required_implied_demand_ratio", "feature_allocation_to_baseline_gap", "feature_required_vs_allocation_gap")),
    PromotionFeatureModuleDefinition("ft_stock_posture", "stock", apply_ft_stock_posture, ("feature_total_stock_pressure_ratio", "feature_stock_sufficiency_gap_units", "feature_current_soh_ratio", "feature_stock_strain")),
    PromotionFeatureModuleDefinition("ft_cover_and_exposure", "stock", apply_ft_cover_and_exposure, ("feature_stock_to_promo_days_ratio", "feature_stock_exposure_vs_promo_days", "feature_sellthrough_pressure_index")),
    PromotionFeatureModuleDefinition("ft_commitment_pressure", "stock", apply_ft_commitment_pressure, ("feature_commitment_pressure_ratio", "feature_on_order_support_ratio", "feature_inventory_congestion")),
    PromotionFeatureModuleDefinition("ft_overhang_risk", "stock", apply_ft_overhang_risk, ("feature_overhang_risk", "feature_underallocation_risk", "feature_overhang_capital_risk")),
    PromotionFeatureModuleDefinition("ft_baseline_demand", "demand", apply_ft_baseline_demand, ("feature_pre_promo_rolling_demand_units", "feature_pre_promo_baseline_daily_units", "feature_baseline_volatility_cv")),
    PromotionFeatureModuleDefinition("ft_near_term_demand_shift", "demand", apply_ft_near_term_demand_shift, ("feature_short_vs_long_baseline_acceleration", "feature_recent_acceleration_ratio", "feature_required_vs_baseline_demand_gap")),
    PromotionFeatureModuleDefinition("ft_sales_velocity", "demand", apply_ft_sales_velocity, ("feature_sales_velocity_units_per_day", "feature_sales_velocity_ratio_short_to_long", "feature_pre_promo_sales_per_selling_day", "feature_slow_seller_flag", "feature_medium_seller_flag", "feature_fast_seller_flag")),
    PromotionFeatureModuleDefinition("ft_history_regime", "demand", apply_ft_history_regime, ("feature_prior_promo_response_same_sku_store", "feature_prior_promo_response_same_sku_network", "feature_prior_markdown_dependence", "feature_promo_recurrence_density", "feature_history_regime_score")),
    PromotionFeatureModuleDefinition("ft_prior_promo_memory", "demand", apply_ft_prior_promo_memory, PRIOR_PROMO_MEMORY_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_target_stock_logic", "stock", apply_ft_target_stock_logic, TARGET_STOCK_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_baseline_demand_orientation", "demand", apply_ft_baseline_demand_orientation, BASELINE_DEMAND_ORIENTATION_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_growth_curve_shape", "demand", apply_ft_growth_curve_shape, GROWTH_CURVE_SHAPE_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_discount_conditioned_demand", "demand", apply_ft_discount_conditioned_demand, DISCOUNT_CONDITIONED_DEMAND_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_discount_elasticity", "demand", apply_ft_discount_elasticity, DISCOUNT_ELASTICITY_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_intermittent_demand", "demand", apply_ft_intermittent_demand, INTERMITTENT_DEMAND_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_probability_feature_bundle", "demand", apply_ft_probability_feature_bundle, PROBABILITY_FEATURE_BUNDLE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_basket_context_feature_bundle", "demand", apply_ft_basket_context_feature_bundle, BASKET_HISTORY_FEATURE_BUNDLE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_basket_structure_dependency", "demand", apply_ft_basket_structure_dependency, BASKET_STRUCTURE_DEPENDENCY_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_sparse_demand_noise", "demand", apply_ft_sparse_demand_noise, SPARSE_DEMAND_NOISE_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_micro_market_equilibrium", "demand", apply_ft_micro_market_equilibrium, MICRO_MARKET_EQUILIBRIUM_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_kalman_state", "demand", apply_ft_kalman_state, KALMAN_STATE_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_distribution_shape_distance", "demand", apply_ft_distribution_shape_distance, DISTRIBUTION_SHAPE_DISTANCE_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_uplift_decomposition", "demand", apply_ft_uplift_decomposition, UPLIFT_DECOMPOSITION_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_allocation_discipline", "demand", apply_ft_allocation_discipline, ALLOCATION_DISCIPLINE_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_pca_residual_structure", "demand", apply_ft_pca_residual_structure, PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_promotion_situational_awareness", "demand", apply_ft_promotion_situational_awareness, PROMOTION_SITUATIONAL_AWARENESS_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_order_decision_diagnostics", "demand", apply_ft_order_decision_diagnostics, ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_survival_convexity", "demand", apply_ft_survival_convexity, SURVIVAL_CONVEXITY_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_growth_survival_interactions", "demand", apply_ft_growth_survival_interactions, GROWTH_SURVIVAL_INTERACTION_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_fragility_adjusted_opportunity", "demand", apply_ft_fragility_adjusted_opportunity, FRAGILITY_ADJUSTED_OPPORTUNITY_FEATURE_COLUMNS),
    PromotionFeatureModuleDefinition("ft_store_context", "context", apply_ft_store_context, ("feature_store_event_baseline_units", "feature_store_baseline_share_in_event", "feature_store_level_promo_load")),
    PromotionFeatureModuleDefinition("ft_category_context", "context", apply_ft_category_context, ("feature_category_share_in_store", "feature_sku_rank_within_category_within_store")),
    PromotionFeatureModuleDefinition("ft_supplier_context", "context", apply_ft_supplier_context, ("feature_supplier_concentration",)),
    PromotionFeatureModuleDefinition("ft_promo_field_context", "context", apply_ft_promo_field_context, ("feature_store_overlap_count", "feature_category_overlap_discount_sum", "feature_supplier_overlap_discount_sum", "feature_substitute_overlap_discount_sum", "feature_local_promotional_field_density_score", "feature_store_category_promo_density", "feature_supplier_promo_density", "feature_promotion_name_cohort_size", "feature_promo_type_cohort_size", "feature_source_file_cohort_size", "feature_field_density_by_store_category_week")),
    PromotionFeatureModuleDefinition("ft_zeta_instability", "behavioural", apply_ft_zeta_instability, ("feature_baseline_instability_ratio", "feature_uplift_fragility_score", "feature_margin_fragility_score", "feature_stock_fragility_score", "feature_composite_promo_instability")),
    PromotionFeatureModuleDefinition("ft_kuramoto_sync", "behavioural", apply_ft_kuramoto_sync, ("feature_short_long_demand_phase_alignment", "feature_promo_window_alignment_score", "feature_category_sync_score", "feature_store_sync_score", "feature_sync_misalignment_penalty")),
    PromotionFeatureModuleDefinition("ft_gravity_field", "behavioural", apply_ft_gravity_field, ("feature_category_gravity", "feature_supplier_gravity", "feature_promo_crowding_gravity", "feature_stock_capital_gravity", "feature_field_density_score", "feature_local_competition_pressure")),
    PromotionFeatureModuleDefinition("ft_friction_signals", "behavioural", apply_ft_friction_signals, ("feature_stock_tie_up_vs_expected_sales", "feature_friction_to_conversion_burden", "feature_margin_sacrifice_vs_expected_flow")),
    PromotionFeatureModuleDefinition("ft_compensation_signals", "behavioural", apply_ft_compensation_signals, ("feature_compensation_needed_score", "feature_forced_sellthrough_discount_dependence", "feature_value_gap_score")),
    PromotionFeatureModuleDefinition("ft_reality_gap", "behavioural", apply_ft_reality_gap, ("feature_uplift_feasibility_gap", "feature_reality_gap_score", "feature_needs_breakout_response_flag")),
    PromotionFeatureModuleDefinition("ft_basket_equilibrium", "demand", apply_ft_basket_equilibrium, BASKET_EQUILIBRIUM_FEATURE_COLUMNS),
)


def iter_registered_feature_modules(
    *,
    selected_groups: Iterable[str] | None = None,
    selected_modules: Iterable[str] | None = None,
) -> tuple[PromotionFeatureModuleDefinition, ...]:
    """Return the registry entries filtered by group or module name."""

    group_filter = {group_name for group_name in (selected_groups or ())}
    module_filter = {module_name for module_name in (selected_modules or ())}
    if not group_filter and not module_filter:
        return FEATURE_MODULE_REGISTRY
    return tuple(
        definition
        for definition in FEATURE_MODULE_REGISTRY
        if definition.group in group_filter or definition.name in module_filter
    )
