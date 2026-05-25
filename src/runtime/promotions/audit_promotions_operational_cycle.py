from __future__ import annotations

"""Runtime entrypoint for auditing a completed promotions operational cycle."""

from dataclasses import dataclass
import argparse
import json
import logging
from pathlib import Path

from runtime.promotions.config import PromotionArtifactPaths
from surfaces.promotions.reporting.operational_cycle_audit_builder import (
    PromotionOperationalCycleAuditArtifacts,
    PromotionOperationalCycleAuditBuilder,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromotionOperationalCycleAuditRuntimeArtifacts:
    summary_json_path: str
    summary_csv_path: str
    report_paths: dict[str, dict[str, str]]
    audit_manifest_path: str
    updated_operational_cycle_manifest_path: str


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    artifacts = audit_operational_cycle(
        run_id=args.run_id,
        operational_cycle_manifest_path=args.operational_cycle_manifest_path,
        artifact_root=args.artifact_root,
        env_file=args.env_file,
    )
    LOGGER.info(
        "Completed promotions operational-cycle audit: summary=%s manifest=%s",
        artifacts.summary_json_path,
        artifacts.updated_operational_cycle_manifest_path,
    )


def audit_operational_cycle(
    *,
    run_id: str | None = None,
    operational_cycle_manifest_path: str | None = None,
    artifact_root: str | None = None,
    env_file: str | None = None,
) -> PromotionOperationalCycleAuditRuntimeArtifacts:
    artifact_paths = PromotionArtifactPaths.from_env(
        root=Path(artifact_root) if artifact_root else None,
        env_file=env_file,
    )
    manifest_path = _resolve_manifest_path(
        run_id=run_id,
        operational_cycle_manifest_path=operational_cycle_manifest_path,
        artifact_paths=artifact_paths,
    )
    audit_artifacts: PromotionOperationalCycleAuditArtifacts = (
        PromotionOperationalCycleAuditBuilder().write_reports(
            operational_cycle_manifest_path=manifest_path,
            artifact_paths=artifact_paths,
        )
    )
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload["audit"] = {
        "summary_json_path": audit_artifacts.summary_json_path,
        "summary_csv_path": audit_artifacts.summary_csv_path,
        "report_paths": audit_artifacts.report_paths,
        "manifest_path": audit_artifacts.manifest_path,
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")
    return PromotionOperationalCycleAuditRuntimeArtifacts(
        summary_json_path=audit_artifacts.summary_json_path,
        summary_csv_path=audit_artifacts.summary_csv_path,
        report_paths=audit_artifacts.report_paths,
        audit_manifest_path=audit_artifacts.manifest_path,
        updated_operational_cycle_manifest_path=str(manifest_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a completed promotions operational cycle.")
    parser.add_argument("--run-id")
    parser.add_argument("--operational-cycle-manifest-path")
    parser.add_argument("--artifact-root")
    parser.add_argument("--env-file")
    return parser


def _resolve_manifest_path(
    *,
    run_id: str | None,
    operational_cycle_manifest_path: str | None,
    artifact_paths: PromotionArtifactPaths,
) -> Path:
    if operational_cycle_manifest_path:
        manifest_path = Path(operational_cycle_manifest_path)
    elif run_id:
        manifest_path = artifact_paths.operational_cycle_manifest_path(run_id)
    else:
        raise ValueError(
            "Provide --run-id or --operational-cycle-manifest-path for the operational-cycle audit."
        )
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing operational cycle manifest: {manifest_path}")
    return manifest_path


if __name__ == "__main__":
    main()