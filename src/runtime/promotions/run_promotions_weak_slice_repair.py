from __future__ import annotations

"""CLI entrypoint for the diagnostics-only weak-slice repair planner."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from models.promotions.model_bundle import read_json
from models.promotions.trainer import (
    DEFAULT_PROMOTION_TRAINER_TARGET_MODE,
    PROMOTION_TRAINER_TARGET_MODE_CHOICES,
    PromotionTargetWeakSliceRepairPlanner,
    _resolve_promotion_trainer_target_mode,
)
from runtime.promotions.config import PromotionArtifactPaths


LOGGER = logging.getLogger(__name__)

_DEFAULT_WEAK_SLICE_REPAIR_TARGET_MODE = "dual_contract_diagnostics"
_WEAK_SLICE_REPAIR_SOURCE_MODE_PROMOTION_READINESS_RUNTIME_MANIFEST = "promotion_readiness_runtime_manifest_path"
_WEAK_SLICE_REPAIR_SOURCE_MODE_THREE_WAY_RUNTIME_MANIFEST = "three_way_runtime_manifest_path"


@dataclass(frozen=True)
class PromotionWeakSliceRepairRuntimeArtifacts:
    artifact_root: str
    runtime_manifest_path: str
    summary_json_path: str
    plan_json_path: str
    residual_examples_json_path: str
    decision_packet_json_path: str
    decision_packet: dict[str, object]
    requested_source_mode: str
    resolved_source_mode: str
    requested_target_mode_context: str | None
    resolved_target_mode_context: str
    source_promotion_readiness_runtime_manifest_path: str | None
    source_three_way_runtime_manifest_path: str | None
    source_target_mode_multi_slice_manifest_path: str
    source_target_contract_three_way_proposal_path: str | None


@dataclass(frozen=True)
class PromotionWeakSliceRepairRuntimeManifest:
    run_id: str
    artifact_root: str
    runtime_manifest_path: str
    requested_source_mode: str
    resolved_source_mode: str
    requested_target_mode_context: str | None
    resolved_target_mode_context: str
    source_inputs: list[str]
    resolved_source_inputs: list[dict[str, object]]
    source_promotion_readiness_runtime_manifest_path: str | None
    source_promotion_readiness_decision_packet_path: str | None
    source_promotion_readiness_blocker_ranking_path: str | None
    source_three_way_runtime_manifest_path: str | None
    source_target_contract_three_way_manifest_path: str | None
    source_target_contract_three_way_proposal_path: str | None
    source_repeated_evidence_manifest_path: str | None
    source_target_mode_multi_slice_manifest_path: str
    output_artifact_paths: dict[str, str]
    decision_packet: dict[str, object]
    diagnostics_only_confirmation: dict[str, object]
    live_default_unchanged_confirmation: bool
    policy_paused_confirmation: bool
    publish_tree_created: bool
    store_facing_csv_changed: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    artifacts = run_weak_slice_repair(
        artifact_root=args.artifact_root,
        run_id=args.run_id,
        promotion_readiness_runtime_manifest_path=args.promotion_readiness_runtime_manifest_path,
        three_way_runtime_manifest_path=args.three_way_runtime_manifest_path,
        target_mode=args.target_mode,
    )
    LOGGER.info(
        "Completed diagnostics-only weak-slice repair planner: run_id=%s weakest_slice=%s manifest=%s",
        args.run_id,
        artifacts.decision_packet.get("weakest_slice_identifier"),
        artifacts.runtime_manifest_path,
    )


def run_weak_slice_repair(
    *,
    artifact_root: str | None,
    run_id: str,
    promotion_readiness_runtime_manifest_path: str | Path | None = None,
    three_way_runtime_manifest_path: str | Path | None = None,
    target_mode: str | None = None,
) -> PromotionWeakSliceRepairRuntimeArtifacts:
    artifact_paths = PromotionArtifactPaths.from_env(root=Path(artifact_root) if artifact_root else None)
    resolved_inputs = _resolve_weak_slice_repair_inputs(
        promotion_readiness_runtime_manifest_path=promotion_readiness_runtime_manifest_path,
        three_way_runtime_manifest_path=three_way_runtime_manifest_path,
    )
    requested_target_mode_context = target_mode
    resolved_target_mode_context = _resolve_promotion_trainer_target_mode(
        _DEFAULT_WEAK_SLICE_REPAIR_TARGET_MODE if target_mode is None else target_mode
    )
    if (
        resolved_target_mode_context == DEFAULT_PROMOTION_TRAINER_TARGET_MODE
        or resolved_target_mode_context != _DEFAULT_WEAK_SLICE_REPAIR_TARGET_MODE
    ):
        raise ValueError(
            "diagnostics-only weak-slice repair runtime requires dual_contract_diagnostics"
        )
    source_target_mode = str(resolved_inputs["source_target_mode"])
    if source_target_mode != resolved_target_mode_context:
        raise ValueError(
            "weak-slice repair runtime source target_mode mismatch: "
            f"requested={requested_target_mode_context!r} resolved={resolved_target_mode_context!r} source={source_target_mode!r}"
        )

    evaluator_artifacts = PromotionTargetWeakSliceRepairPlanner().evaluate(
        run_id=run_id,
        source_target_mode_multi_slice_manifest_path=str(resolved_inputs["source_target_mode_multi_slice_manifest_path"]),
        artifact_paths=artifact_paths,
        source_target_contract_three_way_runtime_manifest_path=resolved_inputs.get(
            "source_three_way_runtime_manifest_path"
        ),
        source_target_contract_three_way_proposal_path=resolved_inputs.get(
            "source_target_contract_three_way_proposal_path"
        ),
        source_promotion_readiness_runtime_manifest_path=resolved_inputs.get(
            "source_promotion_readiness_runtime_manifest_path"
        ),
        source_promotion_readiness_decision_packet_path=resolved_inputs.get(
            "source_promotion_readiness_decision_packet_path"
        ),
        source_promotion_readiness_blocker_ranking_path=resolved_inputs.get(
            "source_promotion_readiness_blocker_ranking_path"
        ),
    )
    if not bool(evaluator_artifacts.decision_packet.get("diagnostics_only", False)):
        raise ValueError("weak-slice repair runtime requires a diagnostics-only decision packet")

    runtime_manifest_path = artifact_paths.weak_slice_repair_runtime_manifest_json_path(run_id)
    runtime_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output_artifact_paths = {
        "weak_slice_repair_summary_json_path": evaluator_artifacts.summary_json_path,
        "weak_slice_repair_summary_csv_path": evaluator_artifacts.summary_csv_path,
        "weak_slice_repair_plan_json_path": evaluator_artifacts.plan_json_path,
        "weak_slice_repair_plan_csv_path": evaluator_artifacts.plan_csv_path,
        "weak_slice_repair_residual_examples_json_path": evaluator_artifacts.residual_examples_json_path,
        "weak_slice_repair_decision_packet_json_path": evaluator_artifacts.decision_packet_json_path,
    }
    diagnostics_only_confirmation = {
        "runtime_path_has_no_shadow_or_primary_promotion_authority": True,
        "final_decision_is_diagnostics_only": bool(evaluator_artifacts.decision_packet.get("diagnostics_only", False)),
        "publish_tree_created": False,
    }
    runtime_manifest = PromotionWeakSliceRepairRuntimeManifest(
        run_id=run_id,
        artifact_root=evaluator_artifacts.artifact_root,
        runtime_manifest_path=str(runtime_manifest_path),
        requested_source_mode=str(resolved_inputs["requested_source_mode"]),
        resolved_source_mode=str(resolved_inputs["resolved_source_mode"]),
        requested_target_mode_context=requested_target_mode_context,
        resolved_target_mode_context=resolved_target_mode_context,
        source_inputs=[str(value) for value in resolved_inputs["source_inputs"]],
        resolved_source_inputs=[dict(value) for value in resolved_inputs["resolved_source_inputs"]],
        source_promotion_readiness_runtime_manifest_path=resolved_inputs.get(
            "source_promotion_readiness_runtime_manifest_path"
        ),
        source_promotion_readiness_decision_packet_path=resolved_inputs.get(
            "source_promotion_readiness_decision_packet_path"
        ),
        source_promotion_readiness_blocker_ranking_path=resolved_inputs.get(
            "source_promotion_readiness_blocker_ranking_path"
        ),
        source_three_way_runtime_manifest_path=resolved_inputs.get("source_three_way_runtime_manifest_path"),
        source_target_contract_three_way_manifest_path=resolved_inputs.get(
            "source_target_contract_three_way_manifest_path"
        ),
        source_target_contract_three_way_proposal_path=resolved_inputs.get(
            "source_target_contract_three_way_proposal_path"
        ),
        source_repeated_evidence_manifest_path=resolved_inputs.get("source_repeated_evidence_manifest_path"),
        source_target_mode_multi_slice_manifest_path=str(resolved_inputs["source_target_mode_multi_slice_manifest_path"]),
        output_artifact_paths=output_artifact_paths,
        decision_packet=dict(evaluator_artifacts.decision_packet),
        diagnostics_only_confirmation=diagnostics_only_confirmation,
        live_default_unchanged_confirmation=bool(evaluator_artifacts.decision_packet.get("live_default_unchanged", False)),
        policy_paused_confirmation=bool(evaluator_artifacts.decision_packet.get("policy_remains_paused", False)),
        publish_tree_created=bool(evaluator_artifacts.decision_packet.get("publish_tree_created", False)),
        store_facing_csv_changed=bool(evaluator_artifacts.decision_packet.get("store_facing_csv_changed", False)),
    )
    runtime_manifest_path.write_text(
        json.dumps(runtime_manifest.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return PromotionWeakSliceRepairRuntimeArtifacts(
        artifact_root=evaluator_artifacts.artifact_root,
        runtime_manifest_path=str(runtime_manifest_path),
        summary_json_path=evaluator_artifacts.summary_json_path,
        plan_json_path=evaluator_artifacts.plan_json_path,
        residual_examples_json_path=evaluator_artifacts.residual_examples_json_path,
        decision_packet_json_path=evaluator_artifacts.decision_packet_json_path,
        decision_packet=dict(evaluator_artifacts.decision_packet),
        requested_source_mode=str(resolved_inputs["requested_source_mode"]),
        resolved_source_mode=str(resolved_inputs["resolved_source_mode"]),
        requested_target_mode_context=requested_target_mode_context,
        resolved_target_mode_context=resolved_target_mode_context,
        source_promotion_readiness_runtime_manifest_path=resolved_inputs.get(
            "source_promotion_readiness_runtime_manifest_path"
        ),
        source_three_way_runtime_manifest_path=resolved_inputs.get("source_three_way_runtime_manifest_path"),
        source_target_mode_multi_slice_manifest_path=str(resolved_inputs["source_target_mode_multi_slice_manifest_path"]),
        source_target_contract_three_way_proposal_path=resolved_inputs.get(
            "source_target_contract_three_way_proposal_path"
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the diagnostics-only weak-slice repair planner over persisted governed artifacts."
    )
    parser.add_argument("--artifact-root")
    parser.add_argument("--run-id", default=datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--target-mode", choices=PROMOTION_TRAINER_TARGET_MODE_CHOICES)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--promotion-readiness-runtime-manifest-path")
    source_group.add_argument("--three-way-runtime-manifest-path")
    return parser


def _resolve_weak_slice_repair_inputs(
    *,
    promotion_readiness_runtime_manifest_path: str | Path | None,
    three_way_runtime_manifest_path: str | Path | None,
) -> dict[str, object]:
    provided_modes = int(promotion_readiness_runtime_manifest_path is not None) + int(
        three_way_runtime_manifest_path is not None
    )
    if provided_modes != 1:
        raise ValueError(
            "weak-slice repair runtime requires exactly one of promotion_readiness_runtime_manifest_path or three_way_runtime_manifest_path"
        )
    if promotion_readiness_runtime_manifest_path is not None:
        runtime_manifest_path = Path(str(promotion_readiness_runtime_manifest_path)).expanduser().resolve()
        if not runtime_manifest_path.exists():
            raise FileNotFoundError(
                "weak-slice repair source promotion readiness runtime manifest not found: "
                f"{runtime_manifest_path}"
            )
        return _resolve_promotion_readiness_runtime_source(runtime_manifest_path)

    runtime_manifest_path = Path(str(three_way_runtime_manifest_path)).expanduser().resolve()
    if not runtime_manifest_path.exists():
        raise FileNotFoundError(
            "weak-slice repair source three-way runtime manifest not found: "
            f"{runtime_manifest_path}"
        )
    return _resolve_three_way_runtime_source(runtime_manifest_path)


def _resolve_promotion_readiness_runtime_source(runtime_manifest_path: Path) -> dict[str, object]:
    manifest_payload = _read_json_object(runtime_manifest_path)
    _validate_runtime_source_diagnostics_contract(
        runtime_manifest_path=runtime_manifest_path,
        runtime_manifest_payload=manifest_payload,
        context="promotion readiness runtime",
    )
    output_artifact_paths = manifest_payload.get("output_artifact_paths")
    if not isinstance(output_artifact_paths, dict):
        raise ValueError(
            "weak-slice repair promotion readiness runtime manifest is missing output_artifact_paths: "
            f"{runtime_manifest_path}"
        )
    decision_packet_path = _resolve_existing_path(
        output_artifact_paths.get("promotion_readiness_decision_packet_json_path"),
        base_path=runtime_manifest_path.parent,
        context=f"{runtime_manifest_path} promotion_readiness_decision_packet_json_path",
    )
    blocker_ranking_path = _resolve_existing_path(
        output_artifact_paths.get("promotion_readiness_blocker_ranking_json_path"),
        base_path=runtime_manifest_path.parent,
        context=f"{runtime_manifest_path} promotion_readiness_blocker_ranking_json_path",
    )
    source_three_way_runtime_manifest_path = _resolve_optional_existing_path(
        manifest_payload.get("source_three_way_runtime_manifest_path"),
        base_path=runtime_manifest_path.parent,
    )
    three_way_source: dict[str, object] = {}
    if source_three_way_runtime_manifest_path is not None:
        three_way_source = _resolve_three_way_runtime_source(source_three_way_runtime_manifest_path)
    source_repeated_evidence_manifest_path = _resolve_optional_existing_path(
        manifest_payload.get("source_repeated_evidence_manifest_path"),
        base_path=runtime_manifest_path.parent,
    )
    source_target_mode_multi_slice_manifest_path = _resolve_multi_slice_manifest_from_runtime_manifest(
        runtime_manifest_path=runtime_manifest_path,
        runtime_manifest_payload=manifest_payload,
        source_repeated_evidence_manifest_path=source_repeated_evidence_manifest_path,
        fallback_three_way_source=three_way_source,
    )
    source_target_contract_three_way_proposal_path = _resolve_optional_existing_path(
        manifest_payload.get("source_target_contract_three_way_proposal_path"),
        base_path=runtime_manifest_path.parent,
    )
    if three_way_source:
        three_way_proposal_path = three_way_source.get("source_target_contract_three_way_proposal_path")
        if source_target_contract_three_way_proposal_path is not None and source_target_contract_three_way_proposal_path != Path(str(three_way_proposal_path)):
            raise ValueError(
                "weak-slice repair readiness runtime manifest and linked three-way runtime manifest disagree on source_target_contract_three_way_proposal_path: "
                f"{runtime_manifest_path}"
            )
        source_target_contract_three_way_proposal_path = None if three_way_proposal_path is None else Path(str(three_way_proposal_path))
        if source_target_mode_multi_slice_manifest_path != Path(str(three_way_source["source_target_mode_multi_slice_manifest_path"])):
            raise ValueError(
                "weak-slice repair readiness runtime manifest and linked three-way runtime manifest disagree on source_target_mode_multi_slice_manifest_path: "
                f"{runtime_manifest_path}"
            )
    resolved_target_mode_context = str(manifest_payload.get("resolved_target_mode_context") or "")
    if not resolved_target_mode_context:
        resolved_target_mode_context = _resolve_source_target_mode_from_multi_slice_manifest(
            source_target_mode_multi_slice_manifest_path
        )
    resolved_source_input = {
        "source_type": _WEAK_SLICE_REPAIR_SOURCE_MODE_PROMOTION_READINESS_RUNTIME_MANIFEST,
        "source_input_path": str(runtime_manifest_path),
        "source_target_mode_multi_slice_manifest_path": str(source_target_mode_multi_slice_manifest_path),
        "source_target_mode": resolved_target_mode_context,
        "source_promotion_readiness_decision_packet_path": str(decision_packet_path),
        "source_promotion_readiness_blocker_ranking_path": str(blocker_ranking_path),
    }
    return {
        "requested_source_mode": _WEAK_SLICE_REPAIR_SOURCE_MODE_PROMOTION_READINESS_RUNTIME_MANIFEST,
        "resolved_source_mode": _WEAK_SLICE_REPAIR_SOURCE_MODE_PROMOTION_READINESS_RUNTIME_MANIFEST,
        "source_inputs": (str(runtime_manifest_path),),
        "resolved_source_inputs": [resolved_source_input],
        "source_promotion_readiness_runtime_manifest_path": str(runtime_manifest_path),
        "source_promotion_readiness_decision_packet_path": str(decision_packet_path),
        "source_promotion_readiness_blocker_ranking_path": str(blocker_ranking_path),
        "source_three_way_runtime_manifest_path": None if source_three_way_runtime_manifest_path is None else str(source_three_way_runtime_manifest_path),
        "source_target_contract_three_way_manifest_path": three_way_source.get("source_target_contract_three_way_manifest_path"),
        "source_target_contract_three_way_proposal_path": None if source_target_contract_three_way_proposal_path is None else str(source_target_contract_three_way_proposal_path),
        "source_repeated_evidence_manifest_path": None if source_repeated_evidence_manifest_path is None else str(source_repeated_evidence_manifest_path),
        "source_target_mode_multi_slice_manifest_path": str(source_target_mode_multi_slice_manifest_path),
        "source_target_mode": resolved_target_mode_context,
    }


def _resolve_three_way_runtime_source(runtime_manifest_path: Path) -> dict[str, object]:
    manifest_payload = _read_json_object(runtime_manifest_path)
    _validate_runtime_source_diagnostics_contract(
        runtime_manifest_path=runtime_manifest_path,
        runtime_manifest_payload=manifest_payload,
        context="target contract three-way runtime",
    )
    output_artifact_paths = manifest_payload.get("output_artifact_paths")
    if not isinstance(output_artifact_paths, dict):
        raise ValueError(
            "weak-slice repair three-way runtime manifest is missing output_artifact_paths: "
            f"{runtime_manifest_path}"
        )
    source_target_contract_three_way_manifest_path = _resolve_existing_path(
        output_artifact_paths.get("target_contract_three_way_manifest_json_path"),
        base_path=runtime_manifest_path.parent,
        context=f"{runtime_manifest_path} target_contract_three_way_manifest_json_path",
    )
    source_target_contract_three_way_proposal_path = _resolve_existing_path(
        output_artifact_paths.get("target_contract_three_way_proposal_json_path"),
        base_path=runtime_manifest_path.parent,
        context=f"{runtime_manifest_path} target_contract_three_way_proposal_json_path",
    )
    source_repeated_evidence_manifest_path = _resolve_optional_existing_path(
        manifest_payload.get("source_repeated_evidence_manifest_path"),
        base_path=runtime_manifest_path.parent,
    )
    source_target_mode_multi_slice_manifest_path = _resolve_multi_slice_manifest_from_runtime_manifest(
        runtime_manifest_path=runtime_manifest_path,
        runtime_manifest_payload=manifest_payload,
        source_repeated_evidence_manifest_path=source_repeated_evidence_manifest_path,
        fallback_three_way_source={},
    )
    resolved_target_mode_context = str(manifest_payload.get("resolved_target_mode_context") or "")
    if not resolved_target_mode_context:
        resolved_target_mode_context = _resolve_source_target_mode_from_multi_slice_manifest(
            source_target_mode_multi_slice_manifest_path
        )
    resolved_source_input = {
        "source_type": _WEAK_SLICE_REPAIR_SOURCE_MODE_THREE_WAY_RUNTIME_MANIFEST,
        "source_input_path": str(runtime_manifest_path),
        "source_target_mode_multi_slice_manifest_path": str(source_target_mode_multi_slice_manifest_path),
        "source_target_contract_three_way_manifest_path": str(source_target_contract_three_way_manifest_path),
        "source_target_contract_three_way_proposal_path": str(source_target_contract_three_way_proposal_path),
        "source_target_mode": resolved_target_mode_context,
    }
    return {
        "requested_source_mode": _WEAK_SLICE_REPAIR_SOURCE_MODE_THREE_WAY_RUNTIME_MANIFEST,
        "resolved_source_mode": _WEAK_SLICE_REPAIR_SOURCE_MODE_THREE_WAY_RUNTIME_MANIFEST,
        "source_inputs": (str(runtime_manifest_path),),
        "resolved_source_inputs": [resolved_source_input],
        "source_promotion_readiness_runtime_manifest_path": None,
        "source_promotion_readiness_decision_packet_path": None,
        "source_promotion_readiness_blocker_ranking_path": None,
        "source_three_way_runtime_manifest_path": str(runtime_manifest_path),
        "source_target_contract_three_way_manifest_path": str(source_target_contract_three_way_manifest_path),
        "source_target_contract_three_way_proposal_path": str(source_target_contract_three_way_proposal_path),
        "source_repeated_evidence_manifest_path": None if source_repeated_evidence_manifest_path is None else str(source_repeated_evidence_manifest_path),
        "source_target_mode_multi_slice_manifest_path": str(source_target_mode_multi_slice_manifest_path),
        "source_target_mode": resolved_target_mode_context,
    }


def _resolve_multi_slice_manifest_from_runtime_manifest(
    *,
    runtime_manifest_path: Path,
    runtime_manifest_payload: dict[str, object],
    source_repeated_evidence_manifest_path: Path | None,
    fallback_three_way_source: dict[str, object],
) -> Path:
    resolved_source_inputs = runtime_manifest_payload.get("resolved_source_inputs")
    if isinstance(resolved_source_inputs, list):
        for record in resolved_source_inputs:
            if not isinstance(record, dict):
                continue
            source_multi_slice_manifest_path = _resolve_optional_existing_path(
                record.get("source_multi_slice_manifest_path"),
                base_path=runtime_manifest_path.parent,
            )
            if source_multi_slice_manifest_path is not None:
                return source_multi_slice_manifest_path
    if source_repeated_evidence_manifest_path is not None:
        return _resolve_multi_slice_manifest_from_repeated_evidence_manifest(source_repeated_evidence_manifest_path)
    fallback_multi_slice_manifest_path = fallback_three_way_source.get("source_target_mode_multi_slice_manifest_path")
    if fallback_multi_slice_manifest_path is not None:
        return Path(str(fallback_multi_slice_manifest_path)).expanduser().resolve()
    raise ValueError(
        "weak-slice repair runtime source is missing source_target_mode_multi_slice_manifest_path evidence: "
        f"{runtime_manifest_path}"
    )


def _resolve_multi_slice_manifest_from_repeated_evidence_manifest(repeated_evidence_manifest_path: Path) -> Path:
    manifest_payload = _read_json_object(repeated_evidence_manifest_path)
    return _resolve_existing_path(
        manifest_payload.get("target_mode_multi_slice_manifest_path"),
        base_path=repeated_evidence_manifest_path.parent,
        context=f"{repeated_evidence_manifest_path} target_mode_multi_slice_manifest_path",
    )


def _resolve_source_target_mode_from_multi_slice_manifest(source_target_mode_multi_slice_manifest_path: Path) -> str:
    manifest_payload = _read_json_object(source_target_mode_multi_slice_manifest_path)
    target_mode = manifest_payload.get("target_mode")
    if not isinstance(target_mode, str) or not target_mode:
        raise ValueError(
            "weak-slice repair source multi-slice manifest is missing target_mode evidence: "
            f"{source_target_mode_multi_slice_manifest_path}"
        )
    return _resolve_promotion_trainer_target_mode(target_mode)


def _validate_runtime_source_diagnostics_contract(
    *,
    runtime_manifest_path: Path,
    runtime_manifest_payload: dict[str, object],
    context: str,
) -> None:
    diagnostics_only_confirmation = runtime_manifest_payload.get("diagnostics_only_confirmation")
    if isinstance(diagnostics_only_confirmation, dict):
        for key in (
            "runtime_path_has_no_primary_promotion_authority",
            "runtime_path_has_no_shadow_or_primary_promotion_authority",
        ):
            if key in diagnostics_only_confirmation and not bool(diagnostics_only_confirmation.get(key)):
                raise ValueError(
                    f"weak-slice repair requires diagnostics-only {context} source evidence: {runtime_manifest_path}"
                )
    if not bool(runtime_manifest_payload.get("live_default_unchanged_confirmation", False)):
        raise ValueError(
            f"weak-slice repair source {context} changed the live default: {runtime_manifest_path}"
        )
    if not bool(runtime_manifest_payload.get("policy_paused_confirmation", False)):
        raise ValueError(
            f"weak-slice repair source {context} did not remain policy-paused: {runtime_manifest_path}"
        )
    if bool(runtime_manifest_payload.get("publish_tree_created", False)):
        raise ValueError(
            f"weak-slice repair source {context} unexpectedly created a publish tree: {runtime_manifest_path}"
        )
    if bool(runtime_manifest_payload.get("store_facing_csv_changed", False)):
        raise ValueError(
            f"weak-slice repair source {context} unexpectedly changed the store-facing CSV: {runtime_manifest_path}"
        )


def _read_json_object(path: Path) -> dict[str, object]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object payload: {path}")
    return payload


def _resolve_existing_path(path_value: object, *, base_path: Path, context: str) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"missing path for {context}")
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        candidate = (base_path / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"{context} not found: {candidate}")
    return candidate


def _resolve_optional_existing_path(path_value: object, *, base_path: Path) -> Path | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    return _resolve_existing_path(path_value, base_path=base_path, context=str(path_value))


if __name__ == "__main__":
    main()