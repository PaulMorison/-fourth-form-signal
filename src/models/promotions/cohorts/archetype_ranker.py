from __future__ import annotations

"""Transparent ranking formulas for promotions cohort archetypes."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PromotionArchetypeRankingResult:
    rankings_frame: pd.DataFrame
    failure_watchlist_frame: pd.DataFrame


class PromotionArchetypeRanker:
    """Identify repeatable winners, failures, and fragile cohort archetypes."""

    def rank(
        self,
        archetype_history_frame: pd.DataFrame,
        *,
        minimum_sample_size: int = 3,
    ) -> PromotionArchetypeRankingResult:
        """Return scored archetype rankings and a failure watchlist."""

        candidates = archetype_history_frame.loc[
            archetype_history_frame["cohort_family"] == "cohort_key_archetype_secondary"
        ].copy()
        if candidates.empty:
            candidates = archetype_history_frame.copy()
        candidates = candidates.loc[candidates["promo_count"].fillna(0).astype(float) >= float(minimum_sample_size)].copy()
        if candidates.empty:
            return PromotionArchetypeRankingResult(
                rankings_frame=pd.DataFrame(),
                failure_watchlist_frame=pd.DataFrame(),
            )
        candidates["_sellthrough_score"] = self._percentile_score(candidates["avg_sell_through_pct"], higher_is_better=True)
        candidates["_gross_profit_score"] = self._percentile_score(candidates["avg_gross_profit"], higher_is_better=True)
        candidates["_uplift_score"] = self._percentile_score(candidates["avg_realised_uplift"], higher_is_better=True)
        candidates["_leftover_safety_score"] = self._percentile_score(
            candidates["avg_leftover_stock_pct"],
            higher_is_better=False,
        )
        candidates["_overallocation_safety_score"] = self._percentile_score(
            candidates["overallocation_rate"],
            higher_is_better=False,
        )
        candidates["_underallocation_risk_score"] = self._percentile_score(
            candidates["underallocation_rate"],
            higher_is_better=True,
        )
        candidates["_stockout_risk_score"] = self._percentile_score(
            candidates["stockout_rate"],
            higher_is_better=True,
        )
        candidates["_margin_pressure_score"] = self._percentile_score(
            candidates["avg_margin_pressure"],
            higher_is_better=True,
        )
        candidates["_fragility_score"] = self._percentile_score(
            candidates["avg_zeta_instability"],
            higher_is_better=True,
        )
        candidates["_kuramoto_score"] = self._percentile_score(
            candidates["avg_kuramoto_sync"],
            higher_is_better=True,
        )
        candidates["_gravity_score"] = self._percentile_score(
            candidates["avg_gravity_score"],
            higher_is_better=True,
        )
        candidates["archetype_confidence_score"] = (
            0.60 * candidates["cohort_sample_weight"].fillna(0.0)
            + 0.40 * candidates["cohort_recency_weight"].fillna(0.0)
        ).clip(lower=0.0, upper=1.0)
        candidates["archetype_strength_score"] = (
            0.30 * candidates["_sellthrough_score"]
            + 0.25 * candidates["_gross_profit_score"]
            + 0.20 * candidates["_uplift_score"]
            + 0.15 * candidates["_leftover_safety_score"]
            + 0.10 * candidates["_overallocation_safety_score"]
        ).clip(lower=0.0, upper=1.0)
        candidates["archetype_destructiveness_score"] = (
            0.30 * (1.0 - candidates["_gross_profit_score"])
            + 0.25 * (1.0 - candidates["_leftover_safety_score"])
            + 0.20 * (1.0 - candidates["_overallocation_safety_score"])
            + 0.15 * candidates["_margin_pressure_score"]
            + 0.10 * candidates["_gravity_score"]
        ).clip(lower=0.0, upper=1.0)
        candidates["archetype_fragility_score"] = (
            0.45 * candidates["_fragility_score"]
            + 0.20 * (1.0 - candidates["_kuramoto_score"])
            + 0.20 * candidates["_stockout_risk_score"]
            + 0.15 * candidates["_underallocation_risk_score"]
        ).clip(lower=0.0, upper=1.0)
        candidates["archetype_repeatability_score"] = (
            0.50 * candidates["archetype_strength_score"]
            + 0.25 * candidates["archetype_confidence_score"]
            + 0.15 * candidates["_kuramoto_score"]
            + 0.10 * (1.0 - candidates["archetype_fragility_score"])
        ).clip(lower=0.0, upper=1.0)
        candidates["strongest_archetype_flag"] = (
            (candidates["archetype_strength_score"] >= 0.75)
            & (candidates["archetype_confidence_score"] >= 0.50)
        ).astype(int)
        candidates["destructive_archetype_flag"] = (
            candidates["archetype_destructiveness_score"] >= 0.75
        ).astype(int)
        candidates["margin_trap_flag"] = (
            (candidates["avg_gross_profit"] <= 0.0)
            | (
                (candidates["_margin_pressure_score"] >= 0.75)
                & (candidates["_gross_profit_score"] <= 0.35)
            )
        ).astype(int)
        candidates["over_allocation_trap_flag"] = (
            (candidates["overallocation_rate"] >= 0.35)
            | (
                (candidates["avg_leftover_stock_pct"] >= 0.20)
                & (candidates["overallocation_rate"] >= 0.20)
            )
        ).astype(int)
        candidates["under_allocation_trap_flag"] = (
            (candidates["underallocation_rate"] >= 0.35)
            | (candidates["stockout_rate"] >= 0.35)
        ).astype(int)
        candidates["fragile_archetype_flag"] = (
            candidates["archetype_fragility_score"] >= 0.75
        ).astype(int)
        candidates["synchronised_winner_flag"] = (
            (candidates["archetype_strength_score"] >= 0.65)
            & (candidates["_kuramoto_score"] >= 0.65)
            & (candidates["archetype_fragility_score"] <= 0.45)
        ).astype(int)
        candidates["gravity_crowded_failure_flag"] = (
            (candidates["archetype_destructiveness_score"] >= 0.65)
            & (candidates["_gravity_score"] >= 0.65)
            & (candidates["avg_leftover_stock_pct"] >= 0.20)
        ).astype(int)
        failure_watchlist = candidates.loc[
            candidates[
                [
                    "destructive_archetype_flag",
                    "margin_trap_flag",
                    "over_allocation_trap_flag",
                    "under_allocation_trap_flag",
                    "fragile_archetype_flag",
                    "gravity_crowded_failure_flag",
                ]
            ].any(axis=1)
        ].copy()
        return PromotionArchetypeRankingResult(
            rankings_frame=candidates.sort_values(
                ["archetype_repeatability_score", "archetype_strength_score"],
                ascending=[False, False],
            ).reset_index(drop=True),
            failure_watchlist_frame=failure_watchlist.sort_values(
                ["archetype_destructiveness_score", "archetype_fragility_score"],
                ascending=[False, False],
            ).reset_index(drop=True),
        )

    def _percentile_score(self, series: pd.Series, *, higher_is_better: bool) -> pd.Series:
        if len(series.index) <= 1 or series.nunique(dropna=False) <= 1:
            return pd.Series(0.5, index=series.index, dtype="float64")
        raw_rank = series.rank(method="average", pct=True)
        if higher_is_better:
            return raw_rank.astype(float)
        floor = 1.0 / float(len(series.index))
        return (1.0 - raw_rank + floor).clip(lower=0.0, upper=1.0).astype(float)