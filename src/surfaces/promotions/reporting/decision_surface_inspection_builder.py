from __future__ import annotations

"""Sibling inspection reporting for governed promotions decision surfaces."""

from dataclasses import dataclass
import json

import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths


@dataclass(frozen=True)
class PromotionDecisionSurfaceInspectionArtifacts:
    report_paths: dict[str, dict[str, str]]
    manifest_path: str


class PromotionDecisionSurfaceInspectionBuilder:
    """Write inspection-focused decision-surface tables for commercial review."""

    def write_reports(
        self,
        *,
        run_id: str,
        decision_surface_frame: pd.DataFrame,
        calibration_summary: dict[str, object],
        thresholds_used: dict[str, object],
        diagnostics_summary: dict[str, object],
        artifact_paths: PromotionArtifactPaths,
    ) -> PromotionDecisionSurfaceInspectionArtifacts:
        report_root = artifact_paths.inspection_run_root(run_id)
        report_root.mkdir(parents=True, exist_ok=True)
        ranked_surface = decision_surface_frame.copy()
        report_tables = {
            "inspection_top_100_strongest_promotions": ranked_surface.sort_values(
                ["final_decision_score", "final_confidence_score"],
                ascending=[False, False],
            ).head(100),
            "inspection_top_100_weakest_promotions": ranked_surface.sort_values(
                ["final_decision_score", "final_confidence_score"],
                ascending=[True, True],
            ).head(100),
            "inspection_top_margin_traps": ranked_surface.sort_values(
                ["margin_risk_penalty", "final_decision_score"],
                ascending=[False, True],
            ).head(100),
            "inspection_top_leftover_risk_rows": ranked_surface.sort_values(
                ["leftover_risk_penalty", "final_decision_score"],
                ascending=[False, True],
            ).head(100),
            "inspection_top_row_vs_cohort_disagreement_rows": ranked_surface.sort_values(
                ["row_cohort_disagreement_score", "final_confidence_score"],
                ascending=[False, False],
            ).head(100),
            "inspection_top_sparse_history_rows": ranked_surface.sort_values(
                ["sparse_history_penalty", "final_confidence_score"],
                ascending=[False, False],
            ).head(100),
            "inspection_promotion_review_packet": self._promotion_review_packet(ranked_surface),
            "inspection_summary_by_promotion_name": self._summary_table(
                ranked_surface,
                group_columns=["promotion_name"],
            ),
            "inspection_summary_by_promo_type": self._summary_table(
                ranked_surface,
                group_columns=["promo_type"],
            ),
            "inspection_summary_by_supplier": self._summary_table(
                ranked_surface,
                group_columns=["inferred_supplier_number"],
            ),
            "inspection_summary_by_department": self._summary_table(
                ranked_surface,
                group_columns=["department"],
            ),
            "inspection_summary_by_store": self._summary_table(
                ranked_surface,
                group_columns=["store_number"],
            ),
            "inspection_summary_by_archetype_primary": self._summary_table(
                ranked_surface,
                group_columns=["cohort_key_archetype_primary"],
            ),
            "inspection_summary_by_archetype_secondary": self._summary_table(
                ranked_surface,
                group_columns=["cohort_key_archetype_secondary"],
            ),
            "inspection_management_review_rollup": self._management_rollup(
                ranked_surface,
                calibration_summary=calibration_summary,
                thresholds_used=thresholds_used,
                diagnostics_summary=diagnostics_summary,
            ),
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
        manifest_path = artifact_paths.decision_surface_inspection_manifest_path(run_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "report_paths": report_paths,
                    "calibration_summary": calibration_summary,
                    "thresholds_used": thresholds_used,
                    "diagnostics_summary": diagnostics_summary,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return PromotionDecisionSurfaceInspectionArtifacts(
            report_paths=report_paths,
            manifest_path=str(manifest_path),
        )

    def _summary_table(
        self,
        frame: pd.DataFrame,
        *,
        group_columns: list[str],
    ) -> pd.DataFrame:
        available_group_columns = [column_name for column_name in group_columns if column_name in frame.columns]
        if not available_group_columns:
            return pd.DataFrame()
        grouped = frame.groupby(available_group_columns, dropna=False).agg(
            row_count=("promotion_row_key", "count"),
            average_final_decision_score=("final_decision_score", "mean"),
            average_final_confidence_score=("final_confidence_score", "mean"),
            average_decision_alignment_score=("decision_alignment_score", "mean"),
            average_margin_risk_penalty=("margin_risk_penalty", "mean"),
            average_leftover_risk_penalty=("leftover_risk_penalty", "mean"),
            average_sparse_history_penalty=("sparse_history_penalty", "mean"),
            average_row_cohort_disagreement_score=("row_cohort_disagreement_score", "mean"),
            strong_go_rate=(
                "decision_recommendation",
                lambda series: float(series.astype(str).eq("strong_go").mean()),
            ),
            watch_rate=(
                "decision_recommendation",
                lambda series: float(series.astype(str).eq("watch").mean()),
            ),
            high_risk_rate=(
                "decision_recommendation",
                lambda series: float(series.astype(str).eq("high_risk").mean()),
            ),
            avoid_rate=(
                "decision_recommendation",
                lambda series: float(series.astype(str).eq("avoid").mean()),
            ),
        )
        return grouped.reset_index().sort_values(
            ["row_count", "average_final_decision_score"],
            ascending=[False, False],
        ).reset_index(drop=True)

    def _promotion_review_packet(self, frame: pd.DataFrame) -> pd.DataFrame:
        review_packet = pd.DataFrame(
            {
                "promotion_row_key": _text_series(frame, ("promotion_row_key",)),
                "promotion_name": _text_series(frame, ("promotion_name",)),
                "supplier": _raw_series(frame, ("supplier", "inferred_supplier_number")),
                "department": _text_series(frame, ("department",)),
                "store_number": _raw_series(frame, ("store_number", "store_number_key")),
                "promotion_start_date": _date_series(
                    frame,
                    ("promotion_start_date_date", "promotion_start_date"),
                ),
                "promotion_end_date": _date_series(
                    frame,
                    ("promotional_end_date_date", "promotional_end_date"),
                ),
                "predicted_units_first_day": _numeric_series(
                    frame,
                    ("predicted_units_first_day",),
                ),
                "predicted_sell_through_pct": _numeric_series(frame, ("predicted_sell_through_pct",)),
                "predicted_sales_ex_gst": _numeric_series(frame, ("predicted_sales_ex_gst",)),
                "predicted_gross_profit": _numeric_series(
                    frame,
                    ("predicted_gross_profit_dollars",),
                ),
                "margin_risk_penalty": _numeric_series(frame, ("margin_risk_penalty",)),
                "leftover_risk_penalty": _numeric_series(
                    frame,
                    ("leftover_risk_penalty", "leftover_risk", "nearest_archetype_expected_leftover"),
                ),
                "stockout_risk_penalty": _numeric_series(
                    frame,
                    ("stockout_risk_penalty", "predicted_stockout_risk"),
                ),
                "overallocation_risk_penalty": _numeric_series(
                    frame,
                    ("overallocation_risk_penalty", "predicted_overallocation_risk"),
                ),
                "underallocation_risk_penalty": _numeric_series(
                    frame,
                    ("underallocation_risk_penalty", "predicted_underallocation_risk"),
                ),
                "archetype_primary": _text_series(
                    frame,
                    ("cohort_key_archetype_primary", "nearest_archetype_key"),
                ),
                "archetype_secondary": _text_series(
                    frame,
                    ("cohort_key_archetype_secondary", "nearest_archetype_key"),
                ),
                "final_decision_score": _numeric_series(frame, ("final_decision_score",)),
                "final_confidence_score": _numeric_series(frame, ("final_confidence_score",)),
                "decision_recommendation": _text_series(frame, ("decision_recommendation",)),
                "decision_recommendation_reason": _text_series(
                    frame,
                    ("decision_recommendation_reason",),
                ),
            }
        )
        return review_packet.sort_values(
            ["final_decision_score", "final_confidence_score"],
            ascending=[False, False],
        ).reset_index(drop=True)

    def _management_rollup(
        self,
        frame: pd.DataFrame,
        *,
        calibration_summary: dict[str, object],
        thresholds_used: dict[str, object],
        diagnostics_summary: dict[str, object],
    ) -> pd.DataFrame:
        row_count = int(len(frame.index))
        recommendation_series = frame.get("decision_recommendation", pd.Series("", index=frame.index)).astype(str)
        rows = [
            {
                "metric_group": "decision_surface",
                "metric_name": "row_count",
                "metric_value": float(row_count),
            },
            {
                "metric_group": "decision_surface",
                "metric_name": "average_final_decision_score",
                "metric_value": float(pd.to_numeric(frame.get("final_decision_score"), errors="coerce").fillna(0.0).mean()),
            },
            {
                "metric_group": "decision_surface",
                "metric_name": "average_final_confidence_score",
                "metric_value": float(pd.to_numeric(frame.get("final_confidence_score"), errors="coerce").fillna(0.0).mean()),
            },
            {
                "metric_group": "decision_surface",
                "metric_name": "strong_go_rate",
                "metric_value": float(recommendation_series.eq("strong_go").mean()),
            },
            {
                "metric_group": "decision_surface",
                "metric_name": "high_risk_rate",
                "metric_value": float(recommendation_series.eq("high_risk").mean()),
            },
            {
                "metric_group": "decision_surface",
                "metric_name": "avoid_rate",
                "metric_value": float(recommendation_series.eq("avoid").mean()),
            },
            {
                "metric_group": "calibration",
                "metric_name": "rows_with_similarity",
                "metric_value": float(calibration_summary.get("rows_with_similarity", 0) or 0),
            },
            {
                "metric_group": "calibration",
                "metric_name": "similarity_threshold",
                "metric_value": float(thresholds_used.get("similarity_threshold", 0.55) or 0.55),
            },
            {
                "metric_group": "calibration",
                "metric_name": "archetype_confidence_floor",
                "metric_value": float(thresholds_used.get("archetype_confidence_floor", 0.45) or 0.45),
            },
            {
                "metric_group": "calibration",
                "metric_name": "row_model_confidence_floor",
                "metric_value": float(thresholds_used.get("row_model_confidence_floor", 0.45) or 0.45),
            },
            {
                "metric_group": "diagnostics",
                "metric_name": "sparse_cohort_rate",
                "metric_value": float(diagnostics_summary.get("sparse_cohort_rate", 0.0) or 0.0),
            },
            {
                "metric_group": "diagnostics",
                "metric_name": "low_confidence_row_rate",
                "metric_value": float(diagnostics_summary.get("low_confidence_row_rate", 0.0) or 0.0),
            },
            {
                "metric_group": "diagnostics",
                "metric_name": "row_cohort_disagreement_rate",
                "metric_value": float(diagnostics_summary.get("row_cohort_disagreement_rate", 0.0) or 0.0),
            },
        ]
        return pd.DataFrame(rows)


def _text_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            values = frame[column_name]
            return values.where(values.notna(), "").astype(str)
    return pd.Series("", index=frame.index, dtype="object")


def _raw_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            return frame[column_name].copy()
    return pd.Series(pd.NA, index=frame.index, dtype="object")


def _numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            return pd.to_numeric(frame[column_name], errors="coerce")
    return pd.Series(0.0, index=frame.index, dtype="float64")


def _date_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            values = pd.to_datetime(frame[column_name], errors="coerce")
            return values.dt.strftime("%Y-%m-%d").fillna("")
    return pd.Series("", index=frame.index, dtype="object")