from __future__ import annotations

"""Local operator inspection copies for the promotions operational cycle."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil

from runtime.promotions.config import PromotionArtifactPaths


@dataclass(frozen=True)
class PromotionLocalInspectionArtifacts:
    root: str
    store_prediction_csv_path: str
    decision_surface_csv_path: str
    review_packet_csv_path: str
    audit_summary_json_path: str
    audit_summary_csv_path: str
    operator_summary_json_path: str | None
    operator_summary_csv_path: str | None
    run_summary_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def write_local_inspection_outputs(
    *,
    run_id: str,
    as_of_date: str,
    execution_mode: str,
    artifact_paths: PromotionArtifactPaths,
    nas_store_prediction_csv_path: str,
    nas_decision_surface_csv_path: str,
    nas_review_packet_csv_path: str,
    operational_cycle_manifest_path: str,
    operator_log_path: str,
    audit_summary_json_path: str,
    audit_summary_csv_path: str,
    operator_summary_json_path: str | None = None,
    operator_summary_csv_path: str | None = None,
) -> PromotionLocalInspectionArtifacts | None:
    """Copy final operator-facing outputs into a single local review folder."""

    if not artifact_paths.has_local_inspection_root:
        return None

    run_root = artifact_paths.local_inspection_run_root(run_id)
    run_root.mkdir(parents=True, exist_ok=True)
    local_store_prediction_csv_path = _local_store_prediction_copy_path(
        artifact_paths=artifact_paths,
        run_id=run_id,
        as_of_date=as_of_date,
        nas_store_prediction_csv_path=nas_store_prediction_csv_path,
    )
    local_decision_surface_csv_path = artifact_paths.local_decision_surface_csv_path(run_id)
    local_review_packet_csv_path = artifact_paths.local_review_packet_csv_path(run_id)
    local_audit_summary_json_path = artifact_paths.local_audit_summary_json_path(run_id)
    local_audit_summary_csv_path = artifact_paths.local_audit_summary_csv_path(run_id)
    _copy_file(nas_store_prediction_csv_path, local_store_prediction_csv_path)
    _copy_file(nas_decision_surface_csv_path, local_decision_surface_csv_path)
    _copy_file(nas_review_packet_csv_path, local_review_packet_csv_path)
    _copy_file(audit_summary_json_path, local_audit_summary_json_path)
    _copy_file(audit_summary_csv_path, local_audit_summary_csv_path)

    local_operator_summary_json_path = artifact_paths.local_operator_summary_json_path(run_id)
    local_operator_summary_csv_path = artifact_paths.local_operator_summary_csv_path(run_id)
    copied_operator_summary_json_path = _copy_optional_file(
        operator_summary_json_path,
        local_operator_summary_json_path,
    )
    copied_operator_summary_csv_path = _copy_optional_file(
        operator_summary_csv_path,
        local_operator_summary_csv_path,
    )

    run_summary_path = artifact_paths.local_run_summary_path(run_id)
    run_summary_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "as_of_date": as_of_date,
                "execution_mode": execution_mode,
                "nas_root": str(artifact_paths.root),
                "local_inspection_root": str(artifact_paths.local_inspection_root),
                "nas_store_prediction_csv_path": nas_store_prediction_csv_path,
                "local_store_prediction_csv_path": str(local_store_prediction_csv_path),
                "nas_decision_surface_csv_path": nas_decision_surface_csv_path,
                "local_decision_surface_csv_path": str(local_decision_surface_csv_path),
                "nas_review_packet_csv_path": nas_review_packet_csv_path,
                "local_review_packet_csv_path": str(local_review_packet_csv_path),
                "audit_summary_json_path": audit_summary_json_path,
                "audit_summary_csv_path": audit_summary_csv_path,
                "local_audit_summary_json_path": str(local_audit_summary_json_path),
                "local_audit_summary_csv_path": str(local_audit_summary_csv_path),
                "operator_summary_json_path": operator_summary_json_path,
                "operator_summary_csv_path": operator_summary_csv_path,
                "local_operator_summary_json_path": copied_operator_summary_json_path,
                "local_operator_summary_csv_path": copied_operator_summary_csv_path,
                "operator_log_path": operator_log_path,
                "operational_cycle_manifest_path": operational_cycle_manifest_path,
                "derived_metrics": {
                    "predicted_units_first_day": {
                        "formula": "predicted_units_sold / max(live_promo_window_days or promo_days, 1)",
                        "description": "Transparent first-day demand estimate used in the store download and operator review outputs.",
                    }
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return PromotionLocalInspectionArtifacts(
        root=str(run_root),
        store_prediction_csv_path=str(local_store_prediction_csv_path),
        decision_surface_csv_path=str(local_decision_surface_csv_path),
        review_packet_csv_path=str(local_review_packet_csv_path),
        audit_summary_json_path=str(local_audit_summary_json_path),
        audit_summary_csv_path=str(local_audit_summary_csv_path),
        operator_summary_json_path=copied_operator_summary_json_path,
        operator_summary_csv_path=copied_operator_summary_csv_path,
        run_summary_path=str(run_summary_path),
    )


def _copy_file(source_path: str | Path, destination_path: Path) -> None:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Local inspection source file does not exist: {source}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination_path)


def _local_store_prediction_copy_path(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    as_of_date: str,
    nas_store_prediction_csv_path: str,
) -> Path:
    source = Path(nas_store_prediction_csv_path)
    try:
        relative_path = source.relative_to(artifact_paths.root)
    except ValueError:
        return artifact_paths.local_store_prediction_download_path(run_id, as_of_date=as_of_date)
    if relative_path.parts and relative_path.parts[0] == "promotions":
        return artifact_paths.local_inspection_run_root(run_id) / relative_path
    return artifact_paths.local_store_prediction_download_path(run_id, as_of_date=as_of_date)


def _copy_optional_file(source_path: str | Path | None, destination_path: Path) -> str | None:
    if source_path is None:
        return None
    source = Path(source_path)
    if not source.exists():
        return None
    _copy_file(source, destination_path)
    return str(destination_path)