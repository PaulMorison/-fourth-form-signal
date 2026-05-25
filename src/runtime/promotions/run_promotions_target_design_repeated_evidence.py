from __future__ import annotations

"""CLI entrypoint for governed target-design repeated-evidence evaluation."""

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
    _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
    PromotionTargetDesignRepeatedEvidenceRunner,
    _expand_target_mode_shadow_slice_inputs_from_multi_slice_manifest,
    _resolve_promotion_trainer_target_mode,
)
from runtime.promotions.config import PromotionArtifactPaths


LOGGER = logging.getLogger(__name__)

_DEFAULT_TARGET_DESIGN_REPEATED_EVIDENCE_TARGET_MODE = "dual_contract_diagnostics"
_REPEATED_EVIDENCE_EVALUATOR_MODE_DESIGN_RUNTIME_MANIFEST = "design_runtime_manifest_path"
_REPEATED_EVIDENCE_EVALUATOR_MODE_EXPLICIT_PROPOSAL_INPUTS = "explicit_proposal_inputs"


@dataclass(frozen=True)
class PromotionTargetDesignRepeatedEvidenceRuntimeArtifacts:
    artifact_root: str
    runtime_manifest_path: str
    evaluator_manifest_path: str
    inventory_json_path: str
    summary_json_path: str
    gate_json_path: str
    residual_examples_json_path: str
    target_mode_multi_slice_manifest_path: str
    target_contract_design_proposal_path: str
    gate: dict[str, object]
    target_design_candidate: str
    requested_target_mode: str | None
    resolved_target_mode: str
    requested_evaluator_mode: str
    resolved_evaluator_mode: str
    source_design_runtime_manifest_path: str | None
    source_proposal_inputs: tuple[str, ...]
    resolved_source_proposals: tuple[dict[str, object], ...]
    resolved_discovery_inputs: tuple[str, ...]


@dataclass(frozen=True)
class PromotionTargetDesignRepeatedEvidenceRuntimeManifest:
    run_id: str
    artifact_root: str
    runtime_manifest_path: str
    requested_target_mode: str | None
    resolved_target_mode: str
    requested_evaluator_mode: str
    resolved_evaluator_mode: str
    source_design_runtime_manifest_path: str | None
    source_proposal_inputs: list[str]
    resolved_source_proposals: list[dict[str, object]]
    resolved_discovery_inputs: list[str]
    output_artifact_paths: dict[str, str]
    gate_outcome: dict[str, object]
    diagnostics_only_confirmation: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    artifacts = run_target_design_repeated_evidence(
        artifact_root=args.artifact_root,
        run_id=args.run_id,
        design_runtime_manifest_path=args.design_runtime_manifest_path,
        proposal_inputs=tuple(args.proposal_inputs or ()),
        target_mode=args.target_mode,
    )
    LOGGER.info(
        "Completed governed target-design repeated-evidence evaluation: run_id=%s decision=%s manifest=%s",
        args.run_id,
        artifacts.gate.get("decision"),
        artifacts.runtime_manifest_path,
    )


def run_target_design_repeated_evidence(
    *,
    artifact_root: str | None,
    run_id: str,
    design_runtime_manifest_path: str | Path | None = None,
    proposal_inputs: Sequence[str | Path] = (),
    target_mode: str | None = None,
) -> PromotionTargetDesignRepeatedEvidenceRuntimeArtifacts:
    artifact_paths = PromotionArtifactPaths.from_env(root=Path(artifact_root) if artifact_root else None)
    evaluator_inputs = _resolve_target_design_repeated_evidence_inputs(
        design_runtime_manifest_path=design_runtime_manifest_path,
        proposal_inputs=proposal_inputs,
    )
    requested_target_mode = target_mode
    resolved_target_mode = _resolve_promotion_trainer_target_mode(
        _DEFAULT_TARGET_DESIGN_REPEATED_EVIDENCE_TARGET_MODE if target_mode is None else target_mode
    )
    if resolved_target_mode == DEFAULT_PROMOTION_TRAINER_TARGET_MODE or resolved_target_mode != "dual_contract_diagnostics":
        raise ValueError(
            "diagnostics-only target-design repeated-evidence runtime requires dual_contract_diagnostics"
        )
    source_target_mode = str(evaluator_inputs["source_target_mode"])
    if source_target_mode != resolved_target_mode:
        raise ValueError(
            "target-design repeated-evidence runtime source target_mode mismatch: "
            f"requested={requested_target_mode!r} resolved={resolved_target_mode!r} source={source_target_mode!r}"
        )

    evaluator_artifacts = PromotionTargetDesignRepeatedEvidenceRunner().run(
        run_id=run_id,
        discovery_inputs=tuple(evaluator_inputs["resolved_discovery_inputs"]),
        artifact_paths=artifact_paths,
    )
    if evaluator_artifacts.gate.get("decision") != "diagnostics_only":
        raise ValueError(
            "diagnostics-only target-design repeated-evidence runtime requires repeated-evidence gate decision "
            f"diagnostics_only, got {evaluator_artifacts.gate.get('decision')!r}"
        )

    runtime_manifest_path = (
        Path(evaluator_artifacts.artifact_root) / "target_design_repeated_evidence_runtime_manifest.json"
    )
    runtime_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output_artifact_paths = {
        "target_design_repeated_evidence_manifest_path": evaluator_artifacts.manifest_json_path,
        "completed_slice_inventory_json_path": evaluator_artifacts.inventory_json_path,
        "target_design_repeated_evidence_summary_json_path": evaluator_artifacts.summary_json_path,
        "target_design_repeated_evidence_gate_json_path": evaluator_artifacts.gate_json_path,
        "target_design_repeated_evidence_residual_examples_json_path": (
            evaluator_artifacts.residual_examples_json_path
        ),
        "target_mode_multi_slice_manifest_path": evaluator_artifacts.target_mode_multi_slice_manifest_path,
        "target_contract_design_proposal_path": evaluator_artifacts.target_contract_design_proposal_path,
    }
    diagnostics_only_confirmation = {
        "runtime_path_is_diagnostics_only": True,
        "source_proposals_are_diagnostics_only": all(
            str(source.get("proposal_decision")) == "diagnostics_only"
            for source in evaluator_inputs["resolved_source_proposals"]
        ),
        "repeated_evidence_gate_decision": evaluator_artifacts.gate.get("decision"),
        "repeated_evidence_gate_is_diagnostics_only": evaluator_artifacts.gate.get("decision") == "diagnostics_only",
    }
    runtime_manifest = PromotionTargetDesignRepeatedEvidenceRuntimeManifest(
        run_id=run_id,
        artifact_root=evaluator_artifacts.artifact_root,
        runtime_manifest_path=str(runtime_manifest_path),
        requested_target_mode=requested_target_mode,
        resolved_target_mode=resolved_target_mode,
        requested_evaluator_mode=str(evaluator_inputs["requested_evaluator_mode"]),
        resolved_evaluator_mode=str(evaluator_inputs["resolved_evaluator_mode"]),
        source_design_runtime_manifest_path=(
            None
            if evaluator_inputs["source_design_runtime_manifest_path"] is None else
            str(evaluator_inputs["source_design_runtime_manifest_path"])
        ),
        source_proposal_inputs=[str(value) for value in evaluator_inputs["source_proposal_inputs"]],
        resolved_source_proposals=[dict(value) for value in evaluator_inputs["resolved_source_proposals"]],
        resolved_discovery_inputs=[str(value) for value in evaluator_inputs["resolved_discovery_inputs"]],
        output_artifact_paths=output_artifact_paths,
        gate_outcome=evaluator_artifacts.gate,
        diagnostics_only_confirmation=diagnostics_only_confirmation,
    )
    runtime_manifest_path.write_text(
        json.dumps(runtime_manifest.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return PromotionTargetDesignRepeatedEvidenceRuntimeArtifacts(
        artifact_root=evaluator_artifacts.artifact_root,
        runtime_manifest_path=str(runtime_manifest_path),
        evaluator_manifest_path=evaluator_artifacts.manifest_json_path,
        inventory_json_path=evaluator_artifacts.inventory_json_path,
        summary_json_path=evaluator_artifacts.summary_json_path,
        gate_json_path=evaluator_artifacts.gate_json_path,
        residual_examples_json_path=evaluator_artifacts.residual_examples_json_path,
        target_mode_multi_slice_manifest_path=evaluator_artifacts.target_mode_multi_slice_manifest_path,
        target_contract_design_proposal_path=evaluator_artifacts.target_contract_design_proposal_path,
        gate=evaluator_artifacts.gate,
        target_design_candidate=_TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
        requested_target_mode=requested_target_mode,
        resolved_target_mode=resolved_target_mode,
        requested_evaluator_mode=str(evaluator_inputs["requested_evaluator_mode"]),
        resolved_evaluator_mode=str(evaluator_inputs["resolved_evaluator_mode"]),
        source_design_runtime_manifest_path=(
            None
            if evaluator_inputs["source_design_runtime_manifest_path"] is None else
            str(evaluator_inputs["source_design_runtime_manifest_path"])
        ),
        source_proposal_inputs=tuple(str(value) for value in evaluator_inputs["source_proposal_inputs"]),
        resolved_source_proposals=tuple(dict(value) for value in evaluator_inputs["resolved_source_proposals"]),
        resolved_discovery_inputs=tuple(str(value) for value in evaluator_inputs["resolved_discovery_inputs"]),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run governed diagnostics-only target-design repeated-evidence evaluation."
    )
    parser.add_argument("--artifact-root")
    parser.add_argument(
        "--run-id",
        default=datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
    )
    parser.add_argument("--target-mode", choices=PROMOTION_TRAINER_TARGET_MODE_CHOICES)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--design-runtime-manifest-path")
    source_group.add_argument("--proposal-input", action="append", dest="proposal_inputs")
    return parser


def _resolve_target_design_repeated_evidence_inputs(
    *,
    design_runtime_manifest_path: str | Path | None,
    proposal_inputs: Sequence[str | Path],
) -> dict[str, object]:
    has_design_runtime_manifest = design_runtime_manifest_path is not None
    has_proposal_inputs = bool(proposal_inputs)
    if has_design_runtime_manifest == has_proposal_inputs:
        raise ValueError(
            "target-design repeated-evidence runtime requires exactly one of design_runtime_manifest_path "
            "or proposal_inputs"
        )

    if has_design_runtime_manifest:
        source_manifest_path = Path(str(design_runtime_manifest_path)).expanduser()
        if not source_manifest_path.exists():
            raise FileNotFoundError(
                f"target-design repeated-evidence source design runtime manifest not found: {source_manifest_path}"
            )
        resolved_source = _resolve_target_design_runtime_manifest_source(source_manifest_path.resolve())
        return {
            "requested_evaluator_mode": _REPEATED_EVIDENCE_EVALUATOR_MODE_DESIGN_RUNTIME_MANIFEST,
            "resolved_evaluator_mode": _REPEATED_EVIDENCE_EVALUATOR_MODE_DESIGN_RUNTIME_MANIFEST,
            "source_design_runtime_manifest_path": str(source_manifest_path.resolve()),
            "source_proposal_inputs": [],
            "resolved_source_proposals": [resolved_source],
            "resolved_discovery_inputs": list(resolved_source["resolved_discovery_inputs"]),
            "source_target_mode": str(resolved_source["source_target_mode"]),
        }

    resolved_sources = [
        _resolve_target_contract_design_proposal_source(raw_input)
        for raw_input in proposal_inputs
    ]
    resolved_discovery_inputs = _dedupe_preserving_order(
        [
            str(discovery_input)
            for source in resolved_sources
            for discovery_input in source["resolved_discovery_inputs"]
        ]
    )
    source_target_mode = _resolve_repeated_evidence_source_target_mode(resolved_sources)
    return {
        "requested_evaluator_mode": _REPEATED_EVIDENCE_EVALUATOR_MODE_EXPLICIT_PROPOSAL_INPUTS,
        "resolved_evaluator_mode": _REPEATED_EVIDENCE_EVALUATOR_MODE_EXPLICIT_PROPOSAL_INPUTS,
        "source_design_runtime_manifest_path": None,
        "source_proposal_inputs": [str(Path(value).expanduser().resolve()) for value in proposal_inputs],
        "resolved_source_proposals": resolved_sources,
        "resolved_discovery_inputs": resolved_discovery_inputs,
        "source_target_mode": source_target_mode,
    }


def _resolve_target_design_runtime_manifest_source(
    source_manifest_path: Path,
) -> dict[str, object]:
    manifest_payload = read_json(source_manifest_path)
    output_artifact_paths = manifest_payload.get("output_artifact_paths")
    if not isinstance(output_artifact_paths, dict):
        raise ValueError(
            "target-design repeated-evidence source runtime manifest has invalid output_artifact_paths: "
            f"{source_manifest_path}"
        )
    proposal_path = _resolve_existing_path(
        output_artifact_paths.get("target_contract_design_proposal_json_path"),
        base_path=source_manifest_path.parent,
        context=f"{source_manifest_path} output_artifact_paths.target_contract_design_proposal_json_path",
    )
    summary_path = _resolve_existing_path(
        output_artifact_paths.get("target_contract_design_summary_json_path"),
        base_path=source_manifest_path.parent,
        context=f"{source_manifest_path} output_artifact_paths.target_contract_design_summary_json_path",
    )
    resolved_source = _resolve_target_contract_design_proposal_pair(
        proposal_path=proposal_path,
        summary_path=summary_path,
        source_input_path=source_manifest_path,
        source_type="design_runtime_manifest",
        runtime_manifest_path=source_manifest_path,
    )
    resolved_target_mode_raw = manifest_payload.get("resolved_target_mode")
    if not isinstance(resolved_target_mode_raw, str) or not resolved_target_mode_raw:
        raise ValueError(
            "target-design repeated-evidence source runtime manifest is missing resolved_target_mode: "
            f"{source_manifest_path}"
        )
    manifest_target_mode = _resolve_promotion_trainer_target_mode(resolved_target_mode_raw)
    if manifest_target_mode != resolved_source["source_target_mode"]:
        raise ValueError(
            "target-design repeated-evidence source runtime manifest target_mode is inconsistent with the "
            f"linked design proposal: {source_manifest_path}"
        )
    manifest_source_multi_slice = manifest_payload.get("source_multi_slice_manifest_path")
    if (
        isinstance(manifest_source_multi_slice, str)
        and manifest_source_multi_slice
        and str(Path(manifest_source_multi_slice).expanduser().resolve()) != resolved_source["source_multi_slice_manifest_path"]
    ):
        raise ValueError(
            "target-design repeated-evidence source runtime manifest references a different source_multi_slice_manifest_path "
            f"than the linked design proposal: {source_manifest_path}"
        )

    expected_source_inputs = [
        str(Path(value).expanduser().resolve())
        for value in manifest_payload.get("source_slice_inputs", [])
        if isinstance(value, str) and value
    ]
    if expected_source_inputs and expected_source_inputs != resolved_source["resolved_discovery_inputs"]:
        raise ValueError(
            "target-design repeated-evidence source runtime manifest source_slice_inputs do not match the "
            f"linked design proposal source manifest expansion: {source_manifest_path}"
        )

    resolved_slice_inputs = manifest_payload.get("resolved_slice_inputs", [])
    manifest_resolved_inputs = [
        str(
            Path(str(slice_spec.get("source_manifest_path") or slice_spec.get("source_path"))).expanduser().resolve()
        )
        for slice_spec in resolved_slice_inputs
        if isinstance(slice_spec, dict) and (slice_spec.get("source_manifest_path") or slice_spec.get("source_path"))
    ]
    if manifest_resolved_inputs and manifest_resolved_inputs != resolved_source["resolved_discovery_inputs"]:
        raise ValueError(
            "target-design repeated-evidence source runtime manifest resolved_slice_inputs do not match the "
            f"linked design proposal source manifest expansion: {source_manifest_path}"
        )
    return resolved_source


def _resolve_target_contract_design_proposal_source(
    raw_input: str | Path,
) -> dict[str, object]:
    source_input_path = Path(raw_input).expanduser()
    if not source_input_path.exists():
        raise FileNotFoundError(
            f"target-design repeated-evidence source proposal input not found: {source_input_path}"
        )
    source_input_path = source_input_path.resolve()
    runtime_manifest_path: Path | None = None
    if source_input_path.is_dir():
        proposal_path = source_input_path / "target_contract_design_proposal.json"
        summary_path = source_input_path / "target_contract_design_summary.json"
        runtime_candidate = source_input_path / "target_contract_design_runtime_manifest.json"
        if runtime_candidate.exists():
            runtime_manifest_path = runtime_candidate.resolve()
        source_type = "proposal_root"
    elif source_input_path.suffix.lower() == ".json":
        if source_input_path.name == "target_contract_design_proposal.json":
            proposal_path = source_input_path
            summary_path = source_input_path.parent / "target_contract_design_summary.json"
            runtime_candidate = source_input_path.parent / "target_contract_design_runtime_manifest.json"
            if runtime_candidate.exists():
                runtime_manifest_path = runtime_candidate.resolve()
            source_type = "proposal_json"
        elif source_input_path.name == "target_contract_design_summary.json":
            proposal_path = source_input_path.parent / "target_contract_design_proposal.json"
            summary_path = source_input_path
            runtime_candidate = source_input_path.parent / "target_contract_design_runtime_manifest.json"
            if runtime_candidate.exists():
                runtime_manifest_path = runtime_candidate.resolve()
            source_type = "proposal_summary_json"
        elif source_input_path.name == "target_contract_design_runtime_manifest.json":
            raise ValueError(
                "target-design repeated-evidence runtime manifest replay must use --design-runtime-manifest-path, "
                f"not --proposal-input: {source_input_path}"
            )
        else:
            raise ValueError(
                "target-design repeated-evidence proposal inputs must be proposal roots or governed design proposal/summary JSON files: "
                f"{source_input_path}"
            )
    else:
        raise ValueError(
            "target-design repeated-evidence proposal inputs must be proposal roots or governed design proposal/summary JSON files: "
            f"{source_input_path}"
        )

    proposal_path = proposal_path.resolve()
    summary_path = summary_path.resolve()
    return _resolve_target_contract_design_proposal_pair(
        proposal_path=proposal_path,
        summary_path=summary_path,
        source_input_path=source_input_path,
        source_type=source_type,
        runtime_manifest_path=runtime_manifest_path,
    )


def _resolve_target_contract_design_proposal_pair(
    *,
    proposal_path: Path,
    summary_path: Path,
    source_input_path: Path,
    source_type: str,
    runtime_manifest_path: Path | None,
) -> dict[str, object]:
    if not proposal_path.exists():
        raise FileNotFoundError(
            f"target-design repeated-evidence source design proposal not found: {proposal_path}"
        )
    if not summary_path.exists():
        raise FileNotFoundError(
            f"target-design repeated-evidence source design summary not found: {summary_path}"
        )
    proposal_payload = read_json(proposal_path)
    summary_payload = read_json(summary_path)
    summary_proposal = summary_payload.get("proposal")
    if not isinstance(summary_proposal, dict):
        raise ValueError(
            "target-design repeated-evidence source design summary is missing proposal evidence: "
            f"{summary_path}"
        )
    best_candidate_name = _extract_best_candidate_name(
        proposal_payload,
        context=f"{proposal_path}",
    )
    summary_best_candidate_name = _extract_best_candidate_name(
        summary_proposal,
        context=f"{summary_path} proposal",
    )
    if best_candidate_name != summary_best_candidate_name:
        raise ValueError(
            "target-design repeated-evidence source design proposal and summary disagree on the best candidate: "
            f"{proposal_path}"
        )
    if best_candidate_name != _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE:
        raise ValueError(
            "target-design repeated-evidence runtime currently governs only "
            f"{_TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE!r}, got {best_candidate_name!r} from {proposal_path}"
        )

    proposal_decision = str(proposal_payload.get("decision") or "")
    summary_proposal_decision = str(summary_proposal.get("decision") or "")
    if proposal_decision != summary_proposal_decision:
        raise ValueError(
            "target-design repeated-evidence source design proposal and summary disagree on the proposal decision: "
            f"{proposal_path}"
        )
    if proposal_decision != "diagnostics_only":
        raise ValueError(
            "diagnostics-only target-design repeated-evidence runtime requires diagnostics_only source design proposals, "
            f"got {proposal_decision!r} from {proposal_path}"
        )

    source_multi_slice_manifest_path = _resolve_existing_path(
        proposal_payload.get("source_multi_slice_manifest_path"),
        base_path=proposal_path.parent,
        context=f"{proposal_path} source_multi_slice_manifest_path",
    )
    summary_source_multi_slice_manifest_path = _resolve_existing_path(
        summary_payload.get("source_multi_slice_manifest_path"),
        base_path=summary_path.parent,
        context=f"{summary_path} source_multi_slice_manifest_path",
    )
    if source_multi_slice_manifest_path != summary_source_multi_slice_manifest_path:
        raise ValueError(
            "target-design repeated-evidence source design proposal and summary disagree on the source multi-slice manifest: "
            f"{proposal_path}"
        )

    resolved_discovery_inputs = _expand_target_mode_shadow_slice_inputs_from_multi_slice_manifest(
        source_multi_slice_manifest_path
    )
    source_target_mode = _resolve_source_target_mode_from_multi_slice_manifest(source_multi_slice_manifest_path)

    if runtime_manifest_path is not None:
        runtime_manifest_payload = read_json(runtime_manifest_path)
        runtime_output_artifact_paths = runtime_manifest_payload.get("output_artifact_paths")
        if not isinstance(runtime_output_artifact_paths, dict):
            raise ValueError(
                "target-design repeated-evidence source runtime manifest has invalid output_artifact_paths: "
                f"{runtime_manifest_path}"
            )
        runtime_proposal_path = _resolve_existing_path(
            runtime_output_artifact_paths.get("target_contract_design_proposal_json_path"),
            base_path=runtime_manifest_path.parent,
            context=(
                f"{runtime_manifest_path} output_artifact_paths.target_contract_design_proposal_json_path"
            ),
        )
        if runtime_proposal_path != proposal_path:
            raise ValueError(
                "target-design repeated-evidence source runtime manifest points to a different design proposal than the explicit proposal input: "
                f"{runtime_manifest_path}"
            )

    return {
        "source_type": source_type,
        "source_input_path": str(source_input_path),
        "proposal_root": str(proposal_path.parent.resolve()),
        "proposal_json_path": str(proposal_path),
        "summary_json_path": str(summary_path),
        "runtime_manifest_path": None if runtime_manifest_path is None else str(runtime_manifest_path.resolve()),
        "source_multi_slice_manifest_path": str(source_multi_slice_manifest_path),
        "best_target_design_candidate": best_candidate_name,
        "proposal_decision": proposal_decision,
        "source_target_mode": source_target_mode,
        "resolved_discovery_inputs": resolved_discovery_inputs,
    }


def _extract_best_candidate_name(
    payload: dict[str, object],
    *,
    context: str,
) -> str:
    best_candidate = payload.get("best_target_design_candidate")
    if not isinstance(best_candidate, dict):
        raise ValueError(
            f"target-design repeated-evidence source payload is missing best_target_design_candidate: {context}"
        )
    candidate_name = best_candidate.get("candidate_name")
    if not isinstance(candidate_name, str) or not candidate_name:
        raise ValueError(
            f"target-design repeated-evidence source payload has invalid best_target_design_candidate.candidate_name: {context}"
        )
    return candidate_name


def _resolve_source_target_mode_from_multi_slice_manifest(
    source_multi_slice_manifest_path: Path,
) -> str:
    manifest_payload = read_json(source_multi_slice_manifest_path)
    raw_target_mode = manifest_payload.get("target_mode")
    if isinstance(raw_target_mode, str) and raw_target_mode:
        return _resolve_promotion_trainer_target_mode(raw_target_mode)

    source_slice_inputs = _expand_target_mode_shadow_slice_inputs_from_multi_slice_manifest(
        source_multi_slice_manifest_path
    )
    resolved_modes: set[str] = set()
    for source_slice_input in source_slice_inputs:
        child_manifest_payload = read_json(Path(source_slice_input))
        child_target_mode = child_manifest_payload.get("target_mode")
        if isinstance(child_target_mode, str) and child_target_mode:
            resolved_modes.add(_resolve_promotion_trainer_target_mode(child_target_mode))
    if not resolved_modes:
        raise ValueError(
            "target-design repeated-evidence source multi-slice manifest is missing target_mode evidence: "
            f"{source_multi_slice_manifest_path}"
        )
    if len(resolved_modes) != 1:
        raise ValueError(
            "target-design repeated-evidence source multi-slice manifest has inconsistent target_mode values across slices: "
            f"{source_multi_slice_manifest_path}"
        )
    return next(iter(resolved_modes))


def _resolve_repeated_evidence_source_target_mode(
    resolved_sources: Sequence[dict[str, object]],
) -> str:
    resolved_modes = {str(source["source_target_mode"]) for source in resolved_sources}
    if not resolved_modes:
        raise ValueError("target-design repeated-evidence runtime could not resolve a source target_mode")
    if len(resolved_modes) != 1:
        raise ValueError(
            "target-design repeated-evidence runtime requires a single consistent source target_mode across all sources"
        )
    return next(iter(resolved_modes))


def _resolve_existing_path(
    raw_path: object,
    *,
    base_path: Path,
    context: str,
) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"target-design repeated-evidence source path is missing for {context}")
    candidate_path = Path(raw_path).expanduser()
    search_paths = [candidate_path] if candidate_path.is_absolute() else [base_path / candidate_path, Path.cwd() / candidate_path]
    for search_path in search_paths:
        if search_path.exists():
            return search_path.resolve()
    raise FileNotFoundError(f"target-design repeated-evidence source path not found for {context}: {raw_path}")


def _dedupe_preserving_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = str(Path(value).expanduser().resolve())
        if normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped


if __name__ == "__main__":
    main()