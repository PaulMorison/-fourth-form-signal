from __future__ import annotations

"""Persisted reporting outputs for promotions cohort history and archetype backtests."""

from dataclasses import dataclass
import json

import pandas as pd

from models.promotions.cohorts.archetype_ranker import PromotionArchetypeRankingResult
from models.promotions.cohorts.cohort_backtester import PromotionCohortBacktestResult
from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.cohorts.cohort_history_builder import PromotionCohortHistoryResult


@dataclass(frozen=True)
class PromotionCohortReportingArtifacts:
    report_paths: dict[str, dict[str, str]]
    metrics_path: str
    manifest_path: str


class PromotionCohortReportBuilder:
    """Write cohort summary, ranking, and backtest outputs for operator use."""

    def write_reports(
        self,
        *,
        run_id: str,
        cohort_history: PromotionCohortHistoryResult,
        backtest_result: PromotionCohortBacktestResult,
        ranking_result: PromotionArchetypeRankingResult,
        artifact_paths: PromotionArtifactPaths,
    ) -> PromotionCohortReportingArtifacts:
        """Persist cohort summaries, archetype rankings, matches, and metrics."""

        report_root = artifact_paths.cohort_run_root(run_id)
        report_root.mkdir(parents=True, exist_ok=True)
        summary_frame = cohort_history.summary_frame.copy()
        report_tables = {
            "cohort_summary_by_promotion_name": self._family_summary(summary_frame, "cohort_key_promotion_name"),
            "cohort_summary_by_supplier": self._family_summary(summary_frame, "cohort_key_supplier"),
            "cohort_summary_by_department": self._family_summary(summary_frame, "cohort_key_department"),
            "archetype_rankings": ranking_result.rankings_frame.copy(),
            "archetype_failure_watchlist": ranking_result.failure_watchlist_frame.copy(),
            "nearest_archetype_matches": backtest_result.row_matches_frame.copy(),
            "top_repeatable_winners": ranking_result.rankings_frame.sort_values(
                ["archetype_repeatability_score", "archetype_confidence_score"],
                ascending=[False, False],
            ).head(20),
            "top_destructive_repeat_promotions": self._destructive_promotions_table(summary_frame),
            "suppliers_with_strongest_promo_cohort_performance": self._supplier_strength_table(summary_frame),
            "departments_with_weakest_historical_sell_through": self._department_weakness_table(summary_frame),
            "promotion_types_with_best_uplift_to_leftover_tradeoff": self._promo_type_tradeoff_table(summary_frame),
        }
        report_paths: dict[str, dict[str, str]] = {}
        for report_name, report_frame in report_tables.items():
            parquet_path = report_root / f"{report_name}.parquet"
            csv_path = report_root / f"{report_name}.csv"
            report_frame.to_parquet(parquet_path, index=False)
            report_frame.to_csv(csv_path, index=False)
            report_paths[report_name] = {
                "parquet": str(parquet_path),
                "csv": str(csv_path),
            }
        metrics_path = artifact_paths.cohort_backtest_metrics_path(run_id)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(
            json.dumps(backtest_result.metrics, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest_path = artifact_paths.cohort_report_manifest_path(run_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "as_of_date": cohort_history.as_of_date,
                    "minimum_sample_size": cohort_history.minimum_sample_size,
                    "metrics_path": str(metrics_path),
                    "report_paths": report_paths,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return PromotionCohortReportingArtifacts(
            report_paths=report_paths,
            metrics_path=str(metrics_path),
            manifest_path=str(manifest_path),
        )

    def _family_summary(self, summary_frame: pd.DataFrame, cohort_family: str) -> pd.DataFrame:
        return summary_frame.loc[summary_frame["cohort_family"] == cohort_family].copy().reset_index(drop=True)

    def _destructive_promotions_table(self, summary_frame: pd.DataFrame) -> pd.DataFrame:
        promotion_summary = self._family_summary(summary_frame, "cohort_key_promotion_name")
        if promotion_summary.empty:
            return promotion_summary
        promotion_summary = promotion_summary.copy()
        promotion_summary["destructiveness_proxy_score"] = (
            promotion_summary["avg_leftover_stock_pct"].fillna(0.0)
            + promotion_summary["overallocation_rate"].fillna(0.0)
            + (promotion_summary["avg_gross_profit"].fillna(0.0) <= 0.0).astype(float)
        ) / 3.0
        return promotion_summary.sort_values(
            ["destructiveness_proxy_score", "promo_count"],
            ascending=[False, False],
        ).head(20)

    def _supplier_strength_table(self, summary_frame: pd.DataFrame) -> pd.DataFrame:
        supplier_summary = self._family_summary(summary_frame, "cohort_key_supplier")
        if supplier_summary.empty:
            return supplier_summary
        supplier_summary = supplier_summary.copy()
        supplier_summary["supplier_strength_proxy_score"] = (
            supplier_summary["avg_sell_through_pct"].fillna(0.0)
            + supplier_summary["avg_realised_uplift"].fillna(0.0)
            + supplier_summary["avg_gross_profit"].rank(method="average", pct=True)
        ) / 3.0
        return supplier_summary.sort_values(
            ["supplier_strength_proxy_score", "promo_count"],
            ascending=[False, False],
        ).head(20)

    def _department_weakness_table(self, summary_frame: pd.DataFrame) -> pd.DataFrame:
        department_summary = self._family_summary(summary_frame, "cohort_key_department")
        if department_summary.empty:
            return department_summary
        return department_summary.sort_values(
            ["avg_sell_through_pct", "avg_leftover_stock_pct"],
            ascending=[True, False],
        ).head(20)

    def _promo_type_tradeoff_table(self, summary_frame: pd.DataFrame) -> pd.DataFrame:
        promo_type_summary = self._family_summary(summary_frame, "cohort_key_promo_type")
        if promo_type_summary.empty:
            return promo_type_summary
        promo_type_summary = promo_type_summary.copy()
        promo_type_summary["uplift_to_leftover_tradeoff_score"] = (
            promo_type_summary["avg_realised_uplift"].fillna(0.0)
            - promo_type_summary["avg_leftover_stock_pct"].fillna(0.0)
        )
        return promo_type_summary.sort_values(
            ["uplift_to_leftover_tradeoff_score", "promo_count"],
            ascending=[False, False],
        ).head(20)