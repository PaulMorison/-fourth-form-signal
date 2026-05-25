from __future__ import annotations

"""Transparent similarity scoring from planned promotions to historical archetypes."""

from dataclasses import dataclass

import pandas as pd

from state.promotions.cohorts.archetype_signature_builder import (
    CATEGORICAL_REGIME_COLUMNS,
    ORDERED_REGIME_LEVELS,
    PRIMARY_SIGNATURE_COLUMNS,
    SECONDARY_SIGNATURE_COLUMNS,
)
from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


_ROW_TO_HISTORY_ANCHOR_COLUMNS = {
    "feature_discount_depth_pct": "anchor_mean_discount_depth_pct",
    "feature_price_gap_pct_vs_normal": "anchor_mean_price_gap_pct_vs_normal",
    "feature_effective_margin_compression_pct": "anchor_mean_margin_pressure",
    "feature_rebate_dependency_score": "anchor_mean_rebate_dependency",
    "feature_total_stock_pressure_ratio": "anchor_mean_stock_pressure",
    "feature_allocation_vs_baseline_demand_ratio": "anchor_mean_allocation_pressure",
    "feature_overhang_risk": "anchor_mean_overhang_risk",
    "feature_pre_promo_baseline_daily_units": "anchor_mean_baseline_demand",
    "feature_recent_acceleration_ratio": "anchor_mean_demand_acceleration",
    "feature_composite_promo_instability": "anchor_mean_zeta_instability",
    "feature_field_density_score": "anchor_mean_field_density",
    "feature_store_category_promo_density": "anchor_mean_context_density",
    "feature_category_sync_score": "anchor_mean_kuramoto_sync",
    "feature_category_gravity": "anchor_mean_gravity_score",
}


@dataclass(frozen=True)
class CohortSimilarityConfig:
    minimum_sample_size: int = 3
    similarity_threshold: float = 0.55
    exact_regime_match_weight: float = 0.35
    bucket_distance_weight: float = 0.30
    continuous_anchor_weight: float = 0.20
    recency_weight: float = 0.075
    sample_weight: float = 0.075
    secondary_granularity_bonus: float = 0.025


class PromotionCohortSimilarity:
    """Score planned promotions against historical cohort archetypes."""

    def score(
        self,
        planned_rows: pd.DataFrame,
        archetype_history_frame: pd.DataFrame,
        *,
        config: CohortSimilarityConfig | None = None,
    ) -> pd.DataFrame:
        """Return nearest historical archetype matches and expected outcomes."""

        resolved_config = config or CohortSimilarityConfig()
        candidate_history = archetype_history_frame.loc[
            archetype_history_frame["promo_count"].fillna(0).astype(float)
            >= float(resolved_config.minimum_sample_size)
        ].copy()
        if candidate_history.empty:
            return self._empty_match_frame(planned_rows, sparse_cohort_flag=1)
        planned_numeric = planned_rows.copy()
        for column_name in _ROW_TO_HISTORY_ANCHOR_COLUMNS:
            planned_numeric[column_name] = ensure_numeric_series(planned_numeric, column_name)
        results = []
        for row_index, row in planned_numeric.iterrows():
            best_match = None
            best_similarity = -1.0
            for _, candidate in candidate_history.iterrows():
                signature_columns = (
                    SECONDARY_SIGNATURE_COLUMNS
                    if candidate.get("cohort_family") == "cohort_key_archetype_secondary"
                    else PRIMARY_SIGNATURE_COLUMNS
                )
                exact_match_score = self._exact_regime_match_score(row, candidate, signature_columns)
                bucket_score = self._bucket_distance_score(row, candidate, signature_columns)
                continuous_score = self._continuous_anchor_score(row, candidate)
                candidate_similarity = (
                    resolved_config.exact_regime_match_weight * exact_match_score
                    + resolved_config.bucket_distance_weight * bucket_score
                    + resolved_config.continuous_anchor_weight * continuous_score
                    + resolved_config.recency_weight * float(candidate.get("cohort_recency_weight", 0.0) or 0.0)
                    + resolved_config.sample_weight * float(candidate.get("cohort_sample_weight", 0.0) or 0.0)
                )
                if candidate.get("cohort_family") == "cohort_key_archetype_secondary":
                    candidate_similarity += resolved_config.secondary_granularity_bonus
                candidate_similarity = max(0.0, min(1.0, candidate_similarity))
                if candidate_similarity > best_similarity:
                    best_similarity = candidate_similarity
                    best_match = candidate
            if best_match is None:
                results.append(self._default_match_payload(row, sparse_cohort_flag=1))
                continue
            results.append(
                {
                    "promotion_row_key": row["promotion_row_key"],
                    "nearest_archetype_key": str(best_match.get("cohort_key", "") or ""),
                    "nearest_archetype_family": str(best_match.get("cohort_family", "") or ""),
                    "nearest_archetype_similarity": float(best_similarity),
                    "nearest_archetype_sample_size": int(float(best_match.get("promo_count", 0.0) or 0.0)),
                    "nearest_archetype_expected_units": float(best_match.get("avg_units_sold", 0.0) or 0.0),
                    "nearest_archetype_expected_sales_ex_gst": float(best_match.get("avg_sales_ex_gst", 0.0) or 0.0),
                    "nearest_archetype_expected_sell_through": float(best_match.get("avg_sell_through_pct", 0.0) or 0.0),
                    "nearest_archetype_expected_leftover": float(best_match.get("avg_leftover_stock_pct", 0.0) or 0.0),
                    "nearest_archetype_expected_gp": float(best_match.get("avg_gross_profit", 0.0) or 0.0),
                    "nearest_archetype_expected_uplift": float(best_match.get("avg_realised_uplift", 0.0) or 0.0),
                    "nearest_archetype_expected_stockout_rate": float(best_match.get("stockout_rate", 0.0) or 0.0),
                    "nearest_archetype_expected_overallocation_rate": float(best_match.get("overallocation_rate", 0.0) or 0.0),
                    "nearest_archetype_expected_underallocation_rate": float(best_match.get("underallocation_rate", 0.0) or 0.0),
                    "cohort_coverage_flag": int(best_similarity >= resolved_config.similarity_threshold),
                    "sparse_cohort_flag": 0,
                }
            )
        return pd.DataFrame(results, index=planned_rows.index)

    def _default_match_payload(self, row: pd.Series, *, sparse_cohort_flag: int) -> dict[str, object]:
        return {
            "promotion_row_key": row["promotion_row_key"],
            "nearest_archetype_key": "",
            "nearest_archetype_family": "",
            "nearest_archetype_similarity": 0.0,
            "nearest_archetype_sample_size": 0,
            "nearest_archetype_expected_units": float("nan"),
            "nearest_archetype_expected_sales_ex_gst": float("nan"),
            "nearest_archetype_expected_sell_through": float("nan"),
            "nearest_archetype_expected_leftover": float("nan"),
            "nearest_archetype_expected_gp": float("nan"),
            "nearest_archetype_expected_uplift": float("nan"),
            "nearest_archetype_expected_stockout_rate": float("nan"),
            "nearest_archetype_expected_overallocation_rate": float("nan"),
            "nearest_archetype_expected_underallocation_rate": float("nan"),
            "cohort_coverage_flag": 0,
            "sparse_cohort_flag": sparse_cohort_flag,
        }

    def _empty_match_frame(self, planned_rows: pd.DataFrame, *, sparse_cohort_flag: int) -> pd.DataFrame:
        return pd.DataFrame(
            [
                self._default_match_payload(row, sparse_cohort_flag=sparse_cohort_flag)
                for _, row in planned_rows.iterrows()
            ],
            index=planned_rows.index,
        )

    def _exact_regime_match_score(
        self,
        row: pd.Series,
        candidate: pd.Series,
        signature_columns: tuple[str, ...],
    ) -> float:
        matches = []
        for column_name in signature_columns:
            row_value = str(row.get(column_name, "") or "")
            candidate_value = str(candidate.get(column_name, "") or "")
            if not row_value or not candidate_value or row_value == "unknown" or candidate_value == "unknown":
                continue
            matches.append(float(row_value == candidate_value))
        return float(sum(matches) / len(matches)) if matches else 0.0

    def _bucket_distance_score(
        self,
        row: pd.Series,
        candidate: pd.Series,
        signature_columns: tuple[str, ...],
    ) -> float:
        scores = []
        for column_name in signature_columns:
            if column_name in CATEGORICAL_REGIME_COLUMNS:
                continue
            levels = ORDERED_REGIME_LEVELS.get(column_name)
            if not levels:
                continue
            row_value = str(row.get(column_name, "") or "")
            candidate_value = str(candidate.get(column_name, "") or "")
            if row_value not in levels or candidate_value not in levels:
                continue
            distance = abs(levels.index(row_value) - levels.index(candidate_value))
            scores.append(1.0 - distance / max(len(levels) - 1, 1))
        return float(sum(scores) / len(scores)) if scores else 0.0

    def _continuous_anchor_score(self, row: pd.Series, candidate: pd.Series) -> float:
        scores = []
        for row_column, history_column in _ROW_TO_HISTORY_ANCHOR_COLUMNS.items():
            row_value = float(row.get(row_column, 0.0) or 0.0)
            candidate_value = float(candidate.get(history_column, 0.0) or 0.0)
            scale = max(abs(row_value), abs(candidate_value), 1.0)
            scores.append(max(0.0, 1.0 - abs(row_value - candidate_value) / scale))
        return float(sum(scores) / len(scores)) if scores else 0.0