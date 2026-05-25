from __future__ import annotations

"""CLI entrypoint for governed target-mode multi-slice shadow evaluation."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from models.promotions.trainer import (
    DEFAULT_PROMOTION_TRAINER_TARGET_MODE,
    PROMOTION_TRAINER_TARGET_MODE_CHOICES,
    PromotionTargetModeShadowEvaluator,
    _resolve_promotion_trainer_target_mode,
    _resolve_target_mode_shadow_evaluator_inputs,
)
from runtime.promotions.config import PromotionArtifactPaths


LOGGER = logging.getLogger(__name__)

_DEFAULT_MULTI_SLICE_TARGET_MODE = "dual_contract_diagnostics"


@dataclass(frozen=True)
class PromotionTargetModeMultiSliceRuntimeArtifacts:
    artifact_root: str
    runtime_manifest_path: str
    evaluator_manifest_path: str
    summary_json_path: str
    bucket_ranking_json_path: str
    residual_examples_json_path: str
    stability_gate_json_path: str
    gate: dict[str, object]
    requested_target_mode: str | None
    resolved_target_mode: str
    requested_evaluator_mode: str
    resolved_evaluator_mode: str
    source_multi_slice_manifest_path: str | None
    source_slice_inputs: tuple[str, ...]
    resolved_slice_inputs: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class PromotionTargetModeMultiSliceRuntimeManifest:
    run_id: str
    artifact_root: str
    runtime_manifest_path: str
    requested_target_mode: str | None
    resolved_target_mode: str
    requested_evaluator_mode: str
    resolved_evaluator_mode: str
    source_multi_slice_manifest_path: str | None
    source_slice_inputs: list[str]
    resolved_slice_inputs: list[dict[str, object]]
    output_artifact_paths: dict[str, str]
    gate_outcome: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    artifacts = run_target_mode_multi_slice(
        artifact_root=args.artifact_root,
        run_id=args.run_id,
        multi_slice_manifest_path=args.multi_slice_manifest_path,
        slice_inputs=tuple(args.slice_inputs or ()),
        target_mode=args.target_mode,
    )
    LOGGER.info(
        "Completed governed target-mode multi-slice evaluation: run_id=%s decision=%s manifest=%s",
        args.run_id,
        artifacts.gate.get("decision"),
        artifacts.runtime_manifest_path,
    )


def run_target_mode_multi_slice(
    *,
    artifact_root: str | None,
    run_id: str,
    multi_slice_manifest_path: str | Path | None = None,
    slice_inputs: Sequence[str | Path] = (),
    target_mode: str | None = None,
) -> PromotionTargetModeMultiSliceRuntimeArtifacts:
    artifact_paths = PromotionArtifactPaths.from_env(root=Path(artifact_root) if artifact_root else None)
    evaluator_inputs = _resolve_target_mode_shadow_evaluator_inputs(
        multi_slice_manifest_path=multi_slice_manifest_path,
        slice_inputs=slice_inputs,
    )
    requested_target_mode = target_mode
    resolved_target_mode = _resolve_promotion_trainer_target_mode(
        _DEFAULT_MULTI_SLICE_TARGET_MODE if target_mode is None else target_mode
    )
    if resolved_target_mode == DEFAULT_PROMOTION_TRAINER_TARGET_MODE:
        raise ValueError(
            "diagnostics-only target-mode multi-slice runtime requires dual_contract_diagnostics "
            "or historical_allocation_candidate"
        )

    evaluator_artifacts = PromotionTargetModeShadowEvaluator().evaluate(
        run_id=run_id,
        slice_inputs=tuple(evaluator_inputs["source_slice_inputs"]),
        artifact_paths=artifact_paths,
        target_mode=resolved_target_mode,
    )
    runtime_manifest_path = Path(evaluator_artifacts.artifact_root) / "target_mode_multi_slice_runtime_manifest.json"
    runtime_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output_artifact_paths = {
        "target_mode_multi_slice_manifest_path": evaluator_artifacts.manifest_path,
        "target_mode_multi_slice_summary_json_path": evaluator_artifacts.summary_json_path,
        "target_mode_multi_slice_bucket_ranking_json_path": evaluator_artifacts.bucket_ranking_json_path,
        "target_mode_multi_slice_residual_examples_json_path": evaluator_artifacts.residual_examples_json_path,
        "target_mode_shadow_stability_gate_json_path": evaluator_artifacts.stability_gate_json_path,
    }
    runtime_manifest = PromotionTargetModeMultiSliceRuntimeManifest(
        run_id=run_id,
        artifact_root=evaluator_artifacts.artifact_root,
        runtime_manifest_path=str(runtime_manifest_path),
        requested_target_mode=requested_target_mode,
        resolved_target_mode=resolved_target_mode,
        requested_evaluator_mode=str(evaluator_inputs["requested_evaluator_mode"]),
        resolved_evaluator_mode=str(evaluator_inputs["resolved_evaluator_mode"]),
        source_multi_slice_manifest_path=(
            None
            if evaluator_inputs["source_multi_slice_manifest_path"] is None
            else str(evaluator_inputs["source_multi_slice_manifest_path"])
        ),
        source_slice_inputs=list(evaluator_inputs["source_slice_inputs"]),
        resolved_slice_inputs=list(evaluator_inputs["resolved_slice_inputs"]),
        output_artifact_paths=output_artifact_paths,
        gate_outcome=evaluator_artifacts.stability_gate,
    )
    runtime_manifest_path.write_text(
        json.dumps(runtime_manifest.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return PromotionTargetModeMultiSliceRuntimeArtifacts(
        artifact_root=evaluator_artifacts.artifact_root,
        runtime_manifest_path=str(runtime_manifest_path),
        evaluator_manifest_path=evaluator_artifacts.manifest_path,
        summary_json_path=evaluator_artifacts.summary_json_path,
        bucket_ranking_json_path=evaluator_artifacts.bucket_ranking_json_path,
        residual_examples_json_path=evaluator_artifacts.residual_examples_json_path,
        stability_gate_json_path=evaluator_artifacts.stability_gate_json_path,
        gate=evaluator_artifacts.stability_gate,
        requested_target_mode=requested_target_mode,
        resolved_target_mode=resolved_target_mode,
        requested_evaluator_mode=str(evaluator_inputs["requested_evaluator_mode"]),
        resolved_evaluator_mode=str(evaluator_inputs["resolved_evaluator_mode"]),
        source_multi_slice_manifest_path=(
            None
            if evaluator_inputs["source_multi_slice_manifest_path"] is None
            else str(evaluator_inputs["source_multi_slice_manifest_path"])
        ),
        source_slice_inputs=tuple(str(value) for value in evaluator_inputs["source_slice_inputs"]),
        resolved_slice_inputs=tuple(dict(value) for value in evaluator_inputs["resolved_slice_inputs"]),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run governed diagnostics-only target-mode multi-slice shadow evaluation."
    )
    parser.add_argument("--artifact-root")
    parser.add_argument(
        "--run-id",
        default=datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
    )
    parser.add_argument("--target-mode", choices=PROMOTION_TRAINER_TARGET_MODE_CHOICES)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--multi-slice-manifest-path")
    source_group.add_argument("--slice-input", action="append", dest="slice_inputs")
    return parser


if __name__ == "__main__":
    main()