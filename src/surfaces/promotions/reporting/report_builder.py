from __future__ import annotations

"""Decision-useful reporting outputs for scored promotions."""

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths
from surfaces.promotions.reporting.aggregations import build_summary_tables


@dataclass(frozen=True)
class PromotionReportingArtifacts:
    report_paths: dict[str, str]


class PromotionReportBuilder:
    """Build persisted report tables from row-level scored promotions."""

    def write_reports(
        self,
        *,
        run_id: str,
        scored_rows: pd.DataFrame,
        artifact_paths: PromotionArtifactPaths,
    ) -> PromotionReportingArtifacts:
        """Persist promotion, risk, and opportunity reports for operator use."""

        report_root = artifact_paths.reports_run_root(run_id)
        report_root.mkdir(parents=True, exist_ok=True)
        summaries = build_summary_tables(scored_rows)
        report_tables = {
            "promotion_performance_forecast": summaries["promotion_summary"],
            "store_summary": summaries["store_summary"],
            "category_summary": summaries["category_summary"],
            "supplier_summary": summaries["supplier_summary"],
            "overallocation_watchlist": scored_rows.sort_values(
                ["predicted_overallocation_risk", "predicted_gross_profit_dollars"],
                ascending=[False, True],
            ).query("predicted_overallocation_risk >= 0.6"),
            "underallocation_opportunity_list": scored_rows.sort_values(
                ["predicted_underallocation_risk", "predicted_stockout_risk"],
                ascending=[False, False],
            ).query("predicted_underallocation_risk >= 0.6 or predicted_stockout_risk >= 0.6"),
            "low_margin_destructive_promo_list": summaries["promotion_summary"].sort_values(
                ["predicted_gross_profit_dollars", "predicted_overallocation_risk"],
                ascending=[True, False],
            ).query("predicted_gross_profit_dollars <= 0"),
            "strongest_expected_promotions": summaries["promotion_summary"].sort_values(
                ["predicted_gross_profit_dollars", "predicted_sell_through_pct"],
                ascending=[False, False],
            ),
            "weakest_promotions": summaries["promotion_summary"].sort_values(
                ["predicted_overallocation_risk", "predicted_sell_through_pct"],
                ascending=[False, True],
            ),
        }
        report_paths: dict[str, str] = {}
        for report_name, report_frame in report_tables.items():
            report_path = report_root / f"{report_name}.parquet"
            report_frame.to_parquet(report_path, index=False)
            report_paths[report_name] = str(report_path)
        manifest_path = artifact_paths.prediction_report_manifest_path(run_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(report_paths, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        report_paths["report_manifest"] = str(manifest_path)
        return PromotionReportingArtifacts(report_paths=report_paths)
