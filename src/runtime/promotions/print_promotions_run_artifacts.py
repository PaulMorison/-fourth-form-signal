from __future__ import annotations

"""Print the key governed artifacts produced by a promotions operational run."""

from dataclasses import asdict, dataclass
import argparse
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from runtime.promotions.config import PromotionArtifactPaths


@dataclass(frozen=True)
class PromotionRunArtifactIndex:
    run_id: str
    operational_cycle_manifest_path: str
    operator_log_path: str | None
    operator_summary_json_path: str | None
    operator_summary_csv_path: str | None
    store_prediction_download_path: str | None
    decision_surface_csv_path: str | None
    inspection_review_packet_csv_path: str | None
    audit_summary_json_path: str | None
    audit_summary_csv_path: str | None
    completed_sql_telemetry_json_path: str | None
    completed_sql_telemetry_csv_path: str | None
    completed_sql_diagnostics_summary_path: str | None
    future_sql_telemetry_json_path: str | None
    future_sql_telemetry_csv_path: str | None
    future_sql_diagnostics_summary_path: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    artifact_paths = PromotionArtifactPaths.from_env(
        root=Path(args.artifact_root) if args.artifact_root else None,
        enable_local_inspection_copy=False,
        env_file=args.env_file,
    )
    index = collect_run_artifact_index(
        run_id=args.run_id,
        artifact_paths=artifact_paths,
    )
    if args.json:
        print(json.dumps(index.to_dict(), indent=2, sort_keys=True))
        return
    render_run_artifact_index(index, stream=sys.stdout)


def collect_run_artifact_index(
    *,
    run_id: str,
    artifact_paths: PromotionArtifactPaths,
) -> PromotionRunArtifactIndex:
    manifest_path = artifact_paths.operational_cycle_manifest_path(run_id)
    operator_summary_path = artifact_paths.operator_summary_path(run_id)
    operator_summary_payload = _load_json_if_exists(operator_summary_path)
    manifest_payload = _load_json_if_exists(manifest_path)
    if not manifest_payload and not operator_summary_payload:
        raise FileNotFoundError(
            "Neither the operational cycle manifest nor the operator summary exists for "
            f"run_id={run_id}: checked {manifest_path} and {operator_summary_path}"
        )

    summary_context = _as_mapping(operator_summary_payload.get("context"))
    summary_final_outputs = _as_mapping(operator_summary_payload.get("final_outputs"))
    final_outputs = _as_mapping(manifest_payload.get("final_outputs"))
    operator_progress = _as_mapping(manifest_payload.get("operator_progress"))
    if not operator_progress:
        operator_progress = {
            "log_path": str(artifact_paths.operator_log_path(run_id)),
            "summary_path": str(operator_summary_path),
            "summary_csv_path": str(artifact_paths.operator_summary_csv_path(run_id)),
        }

    if not final_outputs:
        final_outputs = summary_final_outputs

    as_of_date = _coalesce(
        _as_string(summary_context.get("as_of_date")),
        _as_string(_as_mapping(manifest_payload.get("runtime_settings")).get("as_of_date")),
    )
    score_run_id = _coalesce(
        _as_string(manifest_payload.get("score_run_id")),
        f"{run_id}-score",
    )
    decision_surface_run_id = _coalesce(
        _as_string(manifest_payload.get("decision_surface_run_id")),
        f"{run_id}-decision-surface",
    )

    final_outputs = _as_mapping(manifest_payload.get("final_outputs"))
    decision_surface = _as_mapping(manifest_payload.get("decision_surface"))
    decision_surface_report_paths = _as_mapping(decision_surface.get("report_paths"))
    promotion_decision_surface = _as_mapping(
        decision_surface_report_paths.get("promotion_decision_surface")
    )
    decision_surface_inspection_paths = _as_mapping(decision_surface.get("inspection_report_paths"))
    inspection_review_packet = _as_mapping(
        decision_surface_inspection_paths.get("inspection_promotion_review_packet")
    )
    audit = _as_mapping(manifest_payload.get("audit"))

    return PromotionRunArtifactIndex(
        run_id=run_id,
        operational_cycle_manifest_path=str(manifest_path),
        operator_log_path=_coalesce(
            _as_string(operator_progress.get("log_path")),
            _as_string(final_outputs.get("operator_log_path")),
        ),
        operator_summary_json_path=_coalesce(
            _as_string(operator_progress.get("summary_path")),
            _as_string(final_outputs.get("operator_summary_json_path")),
        ),
        operator_summary_csv_path=_coalesce(
            _as_string(operator_progress.get("summary_csv_path")),
            _as_string(final_outputs.get("operator_summary_csv_path")),
            str(artifact_paths.operator_summary_csv_path(run_id)),
        ),
        store_prediction_download_path=_coalesce(
            _as_string(final_outputs.get("store_prediction_download_path")),
            _as_string(final_outputs.get("nas_store_prediction_download_path")),
            _existing_path_or_none(artifact_paths.store_prediction_download_path(run_id, as_of_date=as_of_date)),
        ),
        decision_surface_csv_path=_coalesce(
            _as_string(final_outputs.get("decision_surface_csv_path")),
            _as_string(promotion_decision_surface.get("csv")),
            _existing_path_or_none(
                artifact_paths.decision_surface_run_root(decision_surface_run_id)
                / "promotion_decision_surface.csv"
            ),
        ),
        inspection_review_packet_csv_path=_coalesce(
            _as_string(final_outputs.get("inspection_review_packet_csv_path")),
            _as_string(inspection_review_packet.get("csv")),
            _existing_path_or_none(
                artifact_paths.inspection_run_root(decision_surface_run_id)
                / "inspection_promotion_review_packet.csv"
            ),
        ),
        audit_summary_json_path=_coalesce(
            _as_string(final_outputs.get("audit_summary_json_path")),
            _as_string(audit.get("summary_json_path")),
            _existing_path_or_none(
                artifact_paths.operational_cycle_run_root(run_id) / "operational_cycle_run_summary.json"
            ),
        ),
        audit_summary_csv_path=_coalesce(
            _as_string(final_outputs.get("audit_summary_csv_path")),
            _as_string(audit.get("summary_csv_path")),
            _existing_path_or_none(
                artifact_paths.operational_cycle_run_root(run_id) / "operational_cycle_run_summary.csv"
            ),
        ),
        completed_sql_telemetry_json_path=_coalesce(
            _as_string(final_outputs.get("completed_extraction_telemetry_json_path")),
            _existing_path_or_none(artifact_paths.extraction_telemetry_json_path(run_id)),
        ),
        completed_sql_telemetry_csv_path=_coalesce(
            _as_string(final_outputs.get("completed_extraction_telemetry_csv_path")),
            _existing_path_or_none(artifact_paths.extraction_telemetry_csv_path(run_id)),
        ),
        completed_sql_diagnostics_summary_path=_coalesce(
            _as_string(final_outputs.get("completed_sql_diagnostics_summary_path")),
            _existing_path_or_none(artifact_paths.sql_diagnostics_summary_json_path(run_id)),
            _existing_path_or_none(artifact_paths.completed_partition_summary_path(run_id)),
        ),
        future_sql_telemetry_json_path=_coalesce(
            _as_string(final_outputs.get("future_extraction_telemetry_json_path")),
            _existing_path_or_none(artifact_paths.extraction_telemetry_json_path(score_run_id)),
        ),
        future_sql_telemetry_csv_path=_coalesce(
            _as_string(final_outputs.get("future_extraction_telemetry_csv_path")),
            _existing_path_or_none(artifact_paths.extraction_telemetry_csv_path(score_run_id)),
        ),
        future_sql_diagnostics_summary_path=_coalesce(
            _as_string(final_outputs.get("future_sql_diagnostics_summary_path")),
            _existing_path_or_none(artifact_paths.sql_diagnostics_summary_json_path(score_run_id)),
        ),
    )


def render_run_artifact_index(index: PromotionRunArtifactIndex, *, stream: TextIO) -> None:
    print("PROMOTIONS RUN ARTIFACTS", file=stream)
    for key, value in index.to_dict().items():
        print(f"{key}: {value or 'unavailable'}", file=stream)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print the key operator-facing artifacts for one promotions run id."
    )
    parser.add_argument("--env-file")
    parser.add_argument("--artifact-root")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def _as_mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json_if_exists(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _as_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _coalesce(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _existing_path_or_none(path: Path) -> str | None:
    if path.exists():
        return str(path)
    return None


if __name__ == "__main__":
    main()