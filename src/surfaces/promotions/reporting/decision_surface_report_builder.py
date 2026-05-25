from __future__ import annotations

"""Persisted decision-surface outputs for promotions evaluation and diagnostics."""

from dataclasses import dataclass
import json

import pandas as pd

from models.promotions.cohorts.diagnostics import PromotionDecisionDiagnosticsResult
from runtime.promotions.config import PromotionArtifactPaths


@dataclass(frozen=True)
class PromotionDecisionSurfaceReportingArtifacts:
    report_paths: dict[str, dict[str, str]]
    metrics_path: str
    diagnostics_summary_path: str
    manifest_path: str


class PromotionDecisionSurfaceReportBuilder:
    """Write final decision-surface, watchlist, and diagnostics artifacts."""

    def write_reports(
        self,
        *,
        run_id: str,
        decision_surface_frame: pd.DataFrame,
        diagnostics_result: PromotionDecisionDiagnosticsResult,
        metrics: dict[str, object],
        disagreement_cutoff: float,
        artifact_paths: PromotionArtifactPaths,
        manifest_payload: dict[str, object],
    ) -> PromotionDecisionSurfaceReportingArtifacts:
        """Persist final decision tables, diagnostics views, metrics, and manifest lineage."""

        report_root = artifact_paths.decision_surface_run_root(run_id)
        report_root.mkdir(parents=True, exist_ok=True)
        ranked_surface = decision_surface_frame.copy().sort_values(
            ["final_decision_score", "final_confidence_score"],
            ascending=[False, False],
        )
        report_tables = {
            "promotion_decision_surface": ranked_surface,
            "promotion_decision_watchlist": self._watchlist(ranked_surface),
            "promotion_strong_go_list": ranked_surface.loc[
                ranked_surface["decision_recommendation"] == "strong_go"
            ].copy(),
            "promotion_margin_trap_list": ranked_surface.loc[
                pd.to_numeric(ranked_surface.get("margin_risk_penalty"), errors="coerce").fillna(0.0) >= 0.60
            ].copy(),
            "promotion_leftover_risk_list": ranked_surface.loc[
                pd.to_numeric(ranked_surface.get("leftover_risk_penalty"), errors="coerce").fillna(0.0) >= 0.60
            ].copy(),
            "promotion_sparse_history_list": ranked_surface.loc[
                pd.to_numeric(ranked_surface.get("sparse_history_penalty"), errors="coerce").fillna(0.0) >= 0.50
            ].copy(),
            "promotion_row_vs_cohort_disagreement_list": ranked_surface.loc[
                pd.to_numeric(ranked_surface.get("row_cohort_disagreement_score"), errors="coerce").fillna(0.0)
                >= float(disagreement_cutoff)
            ].copy(),
            "promotion_supplier_summary": diagnostics_result.by_supplier_frame.copy(),
            "promotion_department_summary": diagnostics_result.by_department_frame.copy(),
            "promotion_store_summary": diagnostics_result.by_store_frame.copy(),
            "diagnostics_by_store": diagnostics_result.by_store_frame.copy(),
            "diagnostics_by_supplier": diagnostics_result.by_supplier_frame.copy(),
            "diagnostics_by_department": diagnostics_result.by_department_frame.copy(),
            "diagnostics_by_archetype": diagnostics_result.by_archetype_frame.copy(),
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
        metrics_path = artifact_paths.decision_surface_metrics_path(run_id)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
        diagnostics_summary_path = artifact_paths.decision_surface_diagnostics_summary_path(run_id)
        diagnostics_summary_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostics_summary_path.write_text(
            json.dumps(diagnostics_result.summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest_path = artifact_paths.decision_surface_manifest_path(run_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    **manifest_payload,
                    "metrics_path": str(metrics_path),
                    "diagnostics_summary_path": str(diagnostics_summary_path),
                    "report_paths": report_paths,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return PromotionDecisionSurfaceReportingArtifacts(
            report_paths=report_paths,
            metrics_path=str(metrics_path),
            diagnostics_summary_path=str(diagnostics_summary_path),
            manifest_path=str(manifest_path),
        )

    def _watchlist(self, frame: pd.DataFrame) -> pd.DataFrame:
        watch_mask = frame["decision_recommendation"].isin(["watch", "high_risk", "avoid"])
        risk_mask = (
            pd.to_numeric(frame.get("margin_risk_penalty"), errors="coerce").fillna(0.0) >= 0.60
        ) | (
            pd.to_numeric(frame.get("leftover_risk_penalty"), errors="coerce").fillna(0.0) >= 0.60
        ) | (
            pd.to_numeric(frame.get("overallocation_risk_penalty"), errors="coerce").fillna(0.0) >= 0.60
        ) | (
            pd.to_numeric(frame.get("sparse_history_penalty"), errors="coerce").fillna(0.0) >= 0.50
        )
        return frame.loc[watch_mask | risk_mask].copy()