from __future__ import annotations

"""Audit reporting for completed promotions operational cycles."""

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths


class PromotionOperationalCycleAuditError(ValueError):
    """Raised when a completed operational cycle cannot be audited safely."""


@dataclass(frozen=True)
class PromotionOperationalCycleAuditArtifacts:
    summary_json_path: str
    summary_csv_path: str
    report_paths: dict[str, dict[str, str]]
    manifest_path: str


@dataclass(frozen=True)
class PromotionOperationalAuditArtifactResolution:
    artifact_name: str
    artifact_path: str
    artifact_required_flag: bool
    artifact_exists_flag: bool
    artifact_status: str
    artifact_status_reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_path": self.artifact_path,
            "artifact_required_flag": self.artifact_required_flag,
            "artifact_exists_flag": self.artifact_exists_flag,
            "artifact_status": self.artifact_status,
            "artifact_status_reason": self.artifact_status_reason,
        }


class PromotionOperationalCycleAuditBuilder:
    """Build compact operator-facing audit outputs from a completed operational cycle."""

    @staticmethod
    def _build_report_tables(
        *,
        review_packet: pd.DataFrame,
        decision_surface_frame: pd.DataFrame,
        supplier_summary: pd.DataFrame,
        department_summary: pd.DataFrame,
        store_summary: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        """Build audit report tables from decision and review surfaces."""
        return {
            "top_predicted_opportunities": review_packet.sort_values(
                ["final_decision_score", "final_confidence_score"],
                ascending=[False, False],
            ).head(50),
            "top_margin_traps": review_packet.sort_values(
                ["margin_risk_penalty", "predicted_gross_profit"],
                ascending=[False, True],
            ).head(50),
            "top_leftover_risks": review_packet.sort_values(
                ["leftover_risk_penalty", "final_decision_score"],
                ascending=[False, True],
            ).head(50),
            "top_stockout_risks": review_packet.sort_values(
                ["stockout_risk_penalty", "final_decision_score"],
                ascending=[False, True],
            ).head(50),
            "top_row_vs_cohort_disagreements": decision_surface_frame.sort_values(
                ["row_cohort_disagreement_score", "final_confidence_score"],
                ascending=[False, False],
            ).head(50),
            "supplier_run_summary": supplier_summary.sort_values(
                ["failure_rate", "row_count"],
                ascending=[False, False],
            ).reset_index(drop=True),
            "department_run_summary": department_summary.sort_values(
                ["failure_rate", "row_count"],
                ascending=[False, False],
            ).reset_index(drop=True),
            "store_run_summary": store_summary.sort_values(
                ["failure_rate", "row_count"],
                ascending=[False, False],
            ).reset_index(drop=True),
        }

    @staticmethod
    def _write_report_tables(
        *,
        report_root: Path,
        report_tables: dict[str, pd.DataFrame],
    ) -> dict[str, dict[str, str]]:
        """Write all report tables to csv/parquet and return path mapping."""
        report_paths: dict[str, dict[str, str]] = {}
        for report_name, report_frame in report_tables.items():
            csv_path = report_root / f"{report_name}.csv"
            parquet_path = report_root / f"{report_name}.parquet"
            report_frame.to_csv(csv_path, index=False)
            report_frame.to_parquet(parquet_path, index=False)
            report_paths[report_name] = {
                "csv": str(csv_path),
                "parquet": str(parquet_path),
            }
        return report_paths

    @staticmethod
    def _summary_metric_rows(
        *,
        completed_row_count: int,
        future_row_count: int,
        trained_row_count: int,
        scored_row_count: int,
        sparse_history_rows: int,
        low_confidence_rows: int,
        thresholds_used: dict[str, object],
        recommendation_reason_counts: pd.Series,
    ) -> list[dict[str, object]]:
        """Build compact summary-csv metric rows for the audit package."""
        return [
            {
                "metric_group": "rows",
                "metric_name": "rows_extracted_completed",
                "metric_value": completed_row_count,
            },
            {
                "metric_group": "rows",
                "metric_name": "rows_extracted_future",
                "metric_value": future_row_count,
            },
            {
                "metric_group": "rows",
                "metric_name": "rows_trained",
                "metric_value": trained_row_count,
            },
            {
                "metric_group": "rows",
                "metric_name": "rows_scored",
                "metric_value": scored_row_count,
            },
            {
                "metric_group": "rows",
                "metric_name": "rows_with_sparse_history",
                "metric_value": sparse_history_rows,
            },
            {
                "metric_group": "rows",
                "metric_name": "rows_with_low_confidence",
                "metric_value": low_confidence_rows,
            },
            {
                "metric_group": "thresholds",
                "metric_name": "similarity_threshold",
                "metric_value": float(
                    thresholds_used.get("similarity_threshold", 0.55) or 0.55
                ),
            },
            {
                "metric_group": "thresholds",
                "metric_name": "archetype_confidence_floor",
                "metric_value": float(
                    thresholds_used.get("archetype_confidence_floor", 0.45) or 0.45
                ),
            },
            {
                "metric_group": "thresholds",
                "metric_name": "row_model_confidence_floor",
                "metric_value": float(
                    thresholds_used.get("row_model_confidence_floor", 0.45) or 0.45
                ),
            },
            {
                "metric_group": "recommendations",
                "metric_name": "most_common_recommendation_reason",
                "metric_value": str(recommendation_reason_counts.index[0])
                if not recommendation_reason_counts.empty
                else "",
            },
        ]

    def write_reports(
        self,
        *,
        operational_cycle_manifest_path: str | Path,
        artifact_paths: PromotionArtifactPaths,
    ) -> PromotionOperationalCycleAuditArtifacts:
        """Build Stage 14 operational cycle audit tables, summaries, and manifest outputs."""
        manifest_path = Path(operational_cycle_manifest_path)
        if not manifest_path.exists():
            raise PromotionOperationalCycleAuditError(
                f"Missing operational cycle manifest: {manifest_path}"
            )
        operational_cycle_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run_id = str(operational_cycle_manifest.get("run_id") or "").strip()
        if not run_id:
            raise PromotionOperationalCycleAuditError("Operational cycle manifest is missing run_id.")

        completed_extraction = _dict_value(operational_cycle_manifest, "completed_extraction")
        future_extraction = _dict_value(operational_cycle_manifest, "future_extraction")
        training_dataset = _dict_value(operational_cycle_manifest, "training_dataset")
        scoring_section = _dict_value(operational_cycle_manifest, "scoring")
        decision_surface_section = _dict_value(operational_cycle_manifest, "decision_surface")
        store_outputs = operational_cycle_manifest.get("store_outputs")
        execution_mode = str(operational_cycle_manifest.get("execution_mode") or "").strip().lower()

        artifact_contract = _resolve_stage10_audit_artifacts(
            execution_mode=execution_mode,
            training_dataset=training_dataset,
        )
        training_dataset_artifact = artifact_contract["training_ready_parquet"]
        if (
            training_dataset_artifact.artifact_required_flag
            and not training_dataset_artifact.artifact_exists_flag
        ):
            missing_path = training_dataset_artifact.artifact_path
            if not missing_path:
                raise PromotionOperationalCycleAuditError(
                    "Operational cycle payload is missing path field 'training_dataset.dataset_path'."
                )
            raise PromotionOperationalCycleAuditError(
                f"Operational cycle artifact path does not exist: {missing_path}"
            )

        decision_surface_manifest_path = _required_existing_path(
            decision_surface_section, "manifest_path"
        )
        decision_surface_manifest = json.loads(
            decision_surface_manifest_path.read_text(encoding="utf-8")
        )
        decision_surface_report_paths = _dict_value(decision_surface_manifest, "report_paths")
        decision_surface_frame = _read_table(
            _dict_value(decision_surface_report_paths, "promotion_decision_surface")
        )
        supplier_summary = _read_table(
            _dict_value(decision_surface_report_paths, "promotion_supplier_summary")
        )
        department_summary = _read_table(
            _dict_value(decision_surface_report_paths, "promotion_department_summary")
        )
        store_summary = _read_table(
            _dict_value(decision_surface_report_paths, "promotion_store_summary")
        )

        inspection_manifest_path = _required_existing_path(
            decision_surface_section,
            "inspection_manifest_path",
        )
        inspection_manifest = json.loads(
            inspection_manifest_path.read_text(encoding="utf-8")
        )
        inspection_report_paths = _dict_value(inspection_manifest, "report_paths")
        review_packet = _read_table(
            _dict_value(inspection_report_paths, "inspection_promotion_review_packet")
        )

        thresholds_used = _dict_value(decision_surface_manifest, "thresholds_used")
        low_confidence_floor = max(
            float(thresholds_used.get("row_model_confidence_floor", 0.45) or 0.45),
            float(thresholds_used.get("archetype_confidence_floor", 0.45) or 0.45),
        )
        sparse_history_rows = int(
            pd.to_numeric(
                decision_surface_frame.get("sparse_history_penalty"),
                errors="coerce",
            )
            .fillna(0.0)
            .ge(0.50)
            .sum()
        )
        low_confidence_rows = int(
            pd.to_numeric(
                decision_surface_frame.get("final_confidence_score"),
                errors="coerce",
            )
            .fillna(0.0)
            .lt(low_confidence_floor)
            .sum()
        )
        recommendation_reason_counts = (
            decision_surface_frame.get(
                "decision_recommendation_reason",
                pd.Series("", index=decision_surface_frame.index),
            )
            .astype(str)
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .head(10)
        )
        completed_row_count = int(
            _dict_value(completed_extraction, "manifest").get("row_count", 0) or 0
        )
        future_row_count = int(
            _dict_value(future_extraction, "manifest").get("row_count", 0) or 0
        )
        trained_row_count = int(
            _dict_value(training_dataset, "manifest").get("row_count", 0) or 0
        )
        scored_row_count = int(scoring_section.get("row_count", 0) or 0)
        if scored_row_count <= 0:
            scored_row_count = int(len(decision_surface_frame.index))

        report_root = artifact_paths.operational_cycle_run_root(run_id)
        report_root.mkdir(parents=True, exist_ok=True)
        report_tables = self._build_report_tables(
            review_packet=review_packet,
            decision_surface_frame=decision_surface_frame,
            supplier_summary=supplier_summary,
            department_summary=department_summary,
            store_summary=store_summary,
        )
        report_paths = self._write_report_tables(
            report_root=report_root,
            report_tables=report_tables,
        )

        summary_payload = {
            "run_id": run_id,
            "score_run_id": str(operational_cycle_manifest.get("score_run_id") or ""),
            "decision_surface_run_id": str(
                operational_cycle_manifest.get("decision_surface_run_id") or ""
            ),
            "rows_extracted_completed": completed_row_count,
            "rows_extracted_future": future_row_count,
            "rows_trained": trained_row_count,
            "rows_scored": scored_row_count,
            "rows_with_sparse_history": sparse_history_rows,
            "rows_with_low_confidence": low_confidence_rows,
            "strongest_opportunities": _records(
                report_tables["top_predicted_opportunities"],
                columns=(
                    "promotion_row_key",
                    "promotion_name",
                    "final_decision_score",
                    "final_confidence_score",
                    "decision_recommendation",
                ),
            ),
            "biggest_trap_promotions": _records(
                report_tables["top_margin_traps"],
                columns=(
                    "promotion_row_key",
                    "promotion_name",
                    "predicted_gross_profit",
                    "margin_risk_penalty",
                    "decision_recommendation",
                ),
            ),
            "biggest_disagreement_promotions": _records(
                report_tables["top_row_vs_cohort_disagreements"],
                columns=(
                    "promotion_row_key",
                    "promotion_name",
                    "row_cohort_disagreement_score",
                    "final_confidence_score",
                    "decision_recommendation",
                ),
            ),
            "highest_risk_suppliers": _summary_records(
                report_tables["supplier_run_summary"],
                key_column="inferred_supplier_number",
            ),
            "highest_risk_departments": _summary_records(
                report_tables["department_run_summary"],
                key_column="department",
            ),
            "highest_risk_stores": _summary_records(
                report_tables["store_run_summary"],
                key_column="store_number",
            ),
            "most_common_recommendation_reasons": [
                {"reason": str(reason), "row_count": int(count)}
                for reason, count in recommendation_reason_counts.items()
            ],
            "calibration_thresholds_used": thresholds_used,
            "artifact_paths_produced": {
                "operational_cycle_manifest_path": str(manifest_path),
                "training_dataset_path": training_dataset_artifact.artifact_path,
                "scoring_manifest_path": str(
                    _required_existing_path(scoring_section, "manifest_path")
                ),
                "score_report_manifest_path": str(
                    Path(str(_dict_value(scoring_section, "report_paths").get("report_manifest")))
                ),
                "decision_surface_manifest_path": str(decision_surface_manifest_path),
                "decision_surface_execution_summary_path": str(
                    _required_existing_path(decision_surface_section, "execution_summary_path")
                ),
                "decision_surface_inspection_manifest_path": str(inspection_manifest_path),
                "inspection_review_packet_csv_path": str(
                    _dict_value(inspection_report_paths, "inspection_promotion_review_packet").get("csv", "")
                ),
                "store_prediction_download_path": str(
                    store_outputs.get("csv_path")
                    or store_outputs.get("nas_store_prediction_csv_path", "")
                    or store_outputs.get("master_csv_path", "")
                )
                if isinstance(store_outputs, dict)
                else "",
                "store_prediction_manifest_path": str(store_outputs.get("manifest_path", ""))
                if isinstance(store_outputs, dict)
                else "",
                "audit_report_paths": report_paths,
            },
            "audit_artifact_contract": [
                resolved_artifact.to_dict()
                for resolved_artifact in artifact_contract.values()
            ],
        }
        summary_json_path = report_root / "operational_cycle_run_summary.json"
        summary_json_path.write_text(
            json.dumps(summary_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        summary_csv_path = report_root / "operational_cycle_run_summary.csv"
        pd.DataFrame(
            self._summary_metric_rows(
                completed_row_count=completed_row_count,
                future_row_count=future_row_count,
                trained_row_count=trained_row_count,
                scored_row_count=scored_row_count,
                sparse_history_rows=sparse_history_rows,
                low_confidence_rows=low_confidence_rows,
                thresholds_used=thresholds_used,
                recommendation_reason_counts=recommendation_reason_counts,
            )
        ).to_csv(summary_csv_path, index=False)
        report_paths["operational_cycle_run_summary"] = {
            "json": str(summary_json_path),
            "csv": str(summary_csv_path),
        }
        audit_manifest_path = artifact_paths.audit_manifest_path(run_id)
        audit_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        audit_manifest_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "summary_json_path": str(summary_json_path),
                    "summary_csv_path": str(summary_csv_path),
                    "report_paths": report_paths,
                    "audit_artifact_contract": [
                        resolved_artifact.to_dict()
                        for resolved_artifact in artifact_contract.values()
                    ],
                    "source_operational_cycle_manifest_path": str(manifest_path),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return PromotionOperationalCycleAuditArtifacts(
            summary_json_path=str(summary_json_path),
            summary_csv_path=str(summary_csv_path),
            report_paths=report_paths,
            manifest_path=str(audit_manifest_path),
        )


def _dict_value(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise PromotionOperationalCycleAuditError(
            f"Operational cycle payload is missing object field '{key}'."
        )
    return value


def _required_existing_path(payload: dict[str, object], key: str) -> Path:
    raw_value = payload.get(key)
    if raw_value is None:
        raise PromotionOperationalCycleAuditError(
            f"Operational cycle payload is missing path field '{key}'."
        )
    path = Path(str(raw_value))
    if not path.exists():
        raise PromotionOperationalCycleAuditError(
            f"Operational cycle artifact path does not exist: {path}"
        )
    return path


def _resolve_stage10_audit_artifacts(
    *,
    execution_mode: str,
    training_dataset: dict[str, object],
) -> dict[str, PromotionOperationalAuditArtifactResolution]:
    """Resolve Stage 10 artifact contract for this run mode.

    Contract rationale:
    - `training_ready.parquet` is optional for governed live operational runs, where
      scoring and decision-surface reporting remain auditable from downstream artifacts.
    - `training_ready.parquet` remains required for training/hybrid modes where the
      run's primary contract includes training dataset persistence lineage.
    """

    training_dataset_path = str(training_dataset.get("dataset_path") or "").strip()
    training_dataset_exists = bool(training_dataset_path) and Path(training_dataset_path).exists()
    training_dataset_required = _is_training_dataset_required_for_mode(execution_mode)

    if training_dataset_required:
        status = "available" if training_dataset_exists else "missing_required_artifact"
        reason = (
            "required_for_training_or_hybrid_mode"
            if training_dataset_exists
            else "required_for_training_or_hybrid_mode_but_missing"
        )
    else:
        status = "available" if training_dataset_exists else "unavailable_for_run_mode"
        reason = (
            "artifact_available_in_live_mode"
            if training_dataset_exists
            else "not_produced_in_live_mode"
        )

    return {
        "training_ready_parquet": PromotionOperationalAuditArtifactResolution(
            artifact_name="training_ready.parquet",
            artifact_path=training_dataset_path,
            artifact_required_flag=training_dataset_required,
            artifact_exists_flag=training_dataset_exists,
            artifact_status=status,
            artifact_status_reason=reason,
        )
    }


def _is_training_dataset_required_for_mode(execution_mode: str) -> bool:
    normalized_mode = str(execution_mode or "").strip().lower()
    if normalized_mode in {"", "live_sql", "smoke", "smoke_patched_extraction"}:
        return False
    return True


def _read_table(path_payload: dict[str, object]) -> pd.DataFrame:
    parquet_path = path_payload.get("parquet")
    csv_path = path_payload.get("csv")
    if parquet_path and Path(str(parquet_path)).exists():
        return pd.read_parquet(Path(str(parquet_path)))
    if csv_path and Path(str(csv_path)).exists():
        return pd.read_csv(Path(str(csv_path)))
    raise PromotionOperationalCycleAuditError(
        "Audit could not resolve a readable report table path."
    )


def _records(frame: pd.DataFrame, *, columns: tuple[str, ...]) -> list[dict[str, object]]:
    available_columns = [column_name for column_name in columns if column_name in frame.columns]
    if not available_columns:
        return []
    rows = frame.loc[:, available_columns].fillna("").to_dict(orient="records")
    return [{key: _python_value(value) for key, value in row.items()} for row in rows]


def _summary_records(frame: pd.DataFrame, *, key_column: str) -> list[dict[str, object]]:
    if frame.empty or key_column not in frame.columns:
        return []
    rows = frame.head(10).fillna("").to_dict(orient="records")
    return [{key: _python_value(value) for key, value in row.items()} for row in rows]


def _python_value(value: object) -> object:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value