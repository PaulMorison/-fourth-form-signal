from __future__ import annotations

"""CLI entrypoint for governed three-way target-contract comparison."""

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
    PromotionTargetContractThreeWayEvaluator,
    _expand_target_mode_shadow_slice_inputs_from_multi_slice_manifest,
    _resolve_promotion_trainer_target_mode,
)
from runtime.promotions.config import PromotionArtifactPaths


LOGGER = logging.getLogger(__name__)

_DEFAULT_TARGET_CONTRACT_THREE_WAY_TARGET_MODE = "dual_contract_diagnostics"
_THREE_WAY_SOURCE_MODE_RUNTIME_MANIFEST = "repeated_evidence_runtime_manifest_path"
_THREE_WAY_SOURCE_MODE_EXPLICIT_INPUTS = "explicit_source_inputs"


@dataclass(frozen=True)
class PromotionTargetContractThreeWayRuntimeArtifacts:
    artifact_root: str
    runtime_manifest_path: str
    evaluator_manifest_path: str
    summary_json_path: str
    bucket_ranking_json_path: str
    residual_examples_json_path: str
    proposal_json_path: str
    proposal: dict[str, object]
    requested_source_mode: str
    resolved_source_mode: str
    requested_target_mode_context: str | None
    resolved_target_mode_context: str
    source_repeated_evidence_runtime_manifest_path: str | None
    source_inputs: tuple[str, ...]
    source_repeated_evidence_manifest_path: str
    source_repeated_evidence_root: str
    source_target_contract_design_proposal_path: str


@dataclass(frozen=True)
class PromotionTargetContractThreeWayRuntimeManifest:
    run_id: str
    artifact_root: str
    runtime_manifest_path: str
    requested_source_mode: str
    resolved_source_mode: str
    requested_target_mode_context: str | None
    resolved_target_mode_context: str
    compared_contracts: list[dict[str, object]]
    source_repeated_evidence_runtime_manifest_path: str | None
    source_inputs: list[str]
    resolved_source_inputs: list[dict[str, object]]
    source_repeated_evidence_manifest_path: str
    source_repeated_evidence_root: str
    source_target_contract_design_proposal_path: str
    output_artifact_paths: dict[str, str]
    proposal_outcome: dict[str, object]
    diagnostics_only_confirmation: dict[str, object]
    live_default_unchanged_confirmation: bool
    policy_paused_confirmation: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    artifacts = run_target_contract_three_way_comparison(
        artifact_root=args.artifact_root,
        run_id=args.run_id,
        repeated_evidence_runtime_manifest_path=args.repeated_evidence_runtime_manifest_path,
        source_inputs=tuple(args.source_inputs or ()),
        target_mode=args.target_mode,
    )
    LOGGER.info(
        "Completed governed three-way target-contract comparison: run_id=%s decision=%s manifest=%s",
        args.run_id,
        artifacts.proposal.get("decision"),
        artifacts.runtime_manifest_path,
    )


def run_target_contract_three_way_comparison(
    *,
    artifact_root: str | None,
    run_id: str,
    repeated_evidence_runtime_manifest_path: str | Path | None = None,
    source_inputs: Sequence[str | Path] = (),
    target_mode: str | None = None,
) -> PromotionTargetContractThreeWayRuntimeArtifacts:
    artifact_paths = PromotionArtifactPaths.from_env(root=Path(artifact_root) if artifact_root else None)
    resolved_inputs = _resolve_target_contract_three_way_inputs(
        repeated_evidence_runtime_manifest_path=repeated_evidence_runtime_manifest_path,
        source_inputs=source_inputs,
    )
    requested_target_mode_context = target_mode
    resolved_target_mode_context = _resolve_promotion_trainer_target_mode(
        _DEFAULT_TARGET_CONTRACT_THREE_WAY_TARGET_MODE if target_mode is None else target_mode
    )
    if (
        resolved_target_mode_context == DEFAULT_PROMOTION_TRAINER_TARGET_MODE
        or resolved_target_mode_context != "dual_contract_diagnostics"
    ):
        raise ValueError(
            "diagnostics-only target-contract three-way runtime requires dual_contract_diagnostics"
        )
    source_target_mode = str(resolved_inputs["source_target_mode"])
    if source_target_mode != resolved_target_mode_context:
        raise ValueError(
            "target-contract three-way runtime source target_mode mismatch: "
            f"requested={requested_target_mode_context!r} resolved={resolved_target_mode_context!r} source={source_target_mode!r}"
        )

    evaluator_artifacts = PromotionTargetContractThreeWayEvaluator().evaluate(
        run_id=run_id,
        repeated_evidence_manifest_path=str(resolved_inputs["source_repeated_evidence_manifest_path"]),
        artifact_paths=artifact_paths,
    )
    decision = str(evaluator_artifacts.proposal.get("decision") or "")
    if decision not in {"diagnostics_only", "candidate_for_shadow_training"}:
        raise ValueError(
            "target-contract three-way runtime requires a non-primary decision, got "
            f"{decision!r}"
        )

    runtime_manifest_path = Path(evaluator_artifacts.artifact_root) / "target_contract_three_way_runtime_manifest.json"
    runtime_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output_artifact_paths = {
        "target_contract_three_way_manifest_json_path": evaluator_artifacts.manifest_json_path,
        "target_contract_three_way_summary_json_path": evaluator_artifacts.summary_json_path,
        "target_contract_three_way_bucket_ranking_json_path": evaluator_artifacts.bucket_ranking_json_path,
        "target_contract_three_way_residual_examples_json_path": evaluator_artifacts.residual_examples_json_path,
        "target_contract_three_way_proposal_json_path": evaluator_artifacts.proposal_json_path,
    }
    diagnostics_only_confirmation = {
        "runtime_path_has_no_primary_promotion_authority": True,
        "final_decision_is_shadow_only_or_diagnostics_only": decision in {"diagnostics_only", "candidate_for_shadow_training"},
        "primary_promotion_disallowed": True,
    }
    live_default_unchanged_confirmation = bool(
        evaluator_artifacts.proposal.get("current_trainer_contract_remains_live_default", False)
    )
    policy_paused_confirmation = bool(evaluator_artifacts.proposal.get("policy_remains_paused", False))
    runtime_manifest = PromotionTargetContractThreeWayRuntimeManifest(
        run_id=run_id,
        artifact_root=evaluator_artifacts.artifact_root,
        runtime_manifest_path=str(runtime_manifest_path),
        requested_source_mode=str(resolved_inputs["requested_source_mode"]),
        resolved_source_mode=str(resolved_inputs["resolved_source_mode"]),
        requested_target_mode_context=requested_target_mode_context,
        resolved_target_mode_context=resolved_target_mode_context,
        compared_contracts=[dict(value) for value in evaluator_artifacts.proposal.get("compared_contracts", [])],
        source_repeated_evidence_runtime_manifest_path=(
            None
            if resolved_inputs["source_repeated_evidence_runtime_manifest_path"] is None else
            str(resolved_inputs["source_repeated_evidence_runtime_manifest_path"])
        ),
        source_inputs=[str(value) for value in resolved_inputs["source_inputs"]],
        resolved_source_inputs=[dict(value) for value in resolved_inputs["resolved_source_inputs"]],
        source_repeated_evidence_manifest_path=str(resolved_inputs["source_repeated_evidence_manifest_path"]),
        source_repeated_evidence_root=str(resolved_inputs["source_repeated_evidence_root"]),
        source_target_contract_design_proposal_path=str(resolved_inputs["source_target_contract_design_proposal_path"]),
        output_artifact_paths=output_artifact_paths,
        proposal_outcome=dict(evaluator_artifacts.proposal),
        diagnostics_only_confirmation=diagnostics_only_confirmation,
        live_default_unchanged_confirmation=live_default_unchanged_confirmation,
        policy_paused_confirmation=policy_paused_confirmation,
    )
    runtime_manifest_path.write_text(
        json.dumps(runtime_manifest.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return PromotionTargetContractThreeWayRuntimeArtifacts(
        artifact_root=evaluator_artifacts.artifact_root,
        runtime_manifest_path=str(runtime_manifest_path),
        evaluator_manifest_path=evaluator_artifacts.manifest_json_path,
        summary_json_path=evaluator_artifacts.summary_json_path,
        bucket_ranking_json_path=evaluator_artifacts.bucket_ranking_json_path,
        residual_examples_json_path=evaluator_artifacts.residual_examples_json_path,
        proposal_json_path=evaluator_artifacts.proposal_json_path,
        proposal=dict(evaluator_artifacts.proposal),
        requested_source_mode=str(resolved_inputs["requested_source_mode"]),
        resolved_source_mode=str(resolved_inputs["resolved_source_mode"]),
        requested_target_mode_context=requested_target_mode_context,
        resolved_target_mode_context=resolved_target_mode_context,
        source_repeated_evidence_runtime_manifest_path=(
            None
            if resolved_inputs["source_repeated_evidence_runtime_manifest_path"] is None else
            str(resolved_inputs["source_repeated_evidence_runtime_manifest_path"])
        ),
        source_inputs=tuple(str(value) for value in resolved_inputs["source_inputs"]),
        source_repeated_evidence_manifest_path=str(resolved_inputs["source_repeated_evidence_manifest_path"]),
        source_repeated_evidence_root=str(resolved_inputs["source_repeated_evidence_root"]),
        source_target_contract_design_proposal_path=str(resolved_inputs["source_target_contract_design_proposal_path"]),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run governed diagnostics-only three-way target-contract comparison."
    )
    parser.add_argument("--artifact-root")
    parser.add_argument(
        "--run-id",
        default=datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
    )
    parser.add_argument("--target-mode", choices=PROMOTION_TRAINER_TARGET_MODE_CHOICES)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--repeated-evidence-runtime-manifest-path")
    source_group.add_argument("--source-input", action="append", dest="source_inputs")
    return parser


def _resolve_target_contract_three_way_inputs(
    *,
    repeated_evidence_runtime_manifest_path: str | Path | None,
    source_inputs: Sequence[str | Path],
) -> dict[str, object]:
    has_runtime_manifest = repeated_evidence_runtime_manifest_path is not None
    has_source_inputs = bool(source_inputs)
    if has_runtime_manifest == has_source_inputs:
        raise ValueError(
            "target-contract three-way runtime requires exactly one of repeated_evidence_runtime_manifest_path "
            "or source_inputs"
        )

    if has_runtime_manifest:
        source_manifest_path = Path(str(repeated_evidence_runtime_manifest_path)).expanduser()
        if not source_manifest_path.exists():
            raise FileNotFoundError(
                "target-contract three-way source repeated-evidence runtime manifest not found: "
                f"{source_manifest_path}"
            )
        resolved_source = _resolve_repeated_evidence_runtime_manifest_source(source_manifest_path.resolve())
        return {
            "requested_source_mode": _THREE_WAY_SOURCE_MODE_RUNTIME_MANIFEST,
            "resolved_source_mode": _THREE_WAY_SOURCE_MODE_RUNTIME_MANIFEST,
            "source_repeated_evidence_runtime_manifest_path": str(source_manifest_path.resolve()),
            "source_inputs": [],
            "resolved_source_inputs": [resolved_source],
            **resolved_source,
        }

    resolved_sources = [_resolve_explicit_target_contract_three_way_source(raw_input) for raw_input in source_inputs]
    repeated_evidence_manifest_paths = {
        str(source["source_repeated_evidence_manifest_path"]) for source in resolved_sources
    }
    if len(repeated_evidence_manifest_paths) != 1:
        raise ValueError(
            "target-contract three-way runtime explicit sources must resolve to a single repeated-evidence manifest"
        )
    baseline_source = resolved_sources[0]
    for field_name in (
        "source_repeated_evidence_manifest_path",
        "source_repeated_evidence_root",
        "source_target_contract_design_proposal_path",
        "source_multi_slice_manifest_path",
        "top_target_design_candidate",
        "source_target_mode",
    ):
        if len({str(source[field_name]) for source in resolved_sources}) != 1:
            raise ValueError(
                "target-contract three-way runtime explicit sources are inconsistent for "
                f"{field_name}"
            )
    resolved_source_mode = (
        str(baseline_source["source_type"])
        if len({str(source["source_type"]) for source in resolved_sources}) == 1 else
        "mixed_explicit_inputs"
    )
    return {
        "requested_source_mode": _THREE_WAY_SOURCE_MODE_EXPLICIT_INPUTS,
        "resolved_source_mode": resolved_source_mode,
        "source_repeated_evidence_runtime_manifest_path": None,
        "source_inputs": _dedupe_preserving_order(str(Path(value).expanduser().resolve()) for value in source_inputs),
        "resolved_source_inputs": resolved_sources,
        **baseline_source,
    }


def _resolve_repeated_evidence_runtime_manifest_source(source_manifest_path: Path) -> dict[str, object]:
    manifest_payload = read_json(source_manifest_path)
    output_artifact_paths = manifest_payload.get("output_artifact_paths")
    if not isinstance(output_artifact_paths, dict):
        raise ValueError(
            "target-contract three-way source runtime manifest has invalid output_artifact_paths: "
            f"{source_manifest_path}"
        )
    repeated_evidence_manifest_path = _resolve_existing_path(
        output_artifact_paths.get("target_design_repeated_evidence_manifest_path"),
        base_path=source_manifest_path.parent,
        context=f"{source_manifest_path} output_artifact_paths.target_design_repeated_evidence_manifest_path",
    )
    proposal_path = _resolve_existing_path(
        output_artifact_paths.get("target_contract_design_proposal_path"),
        base_path=source_manifest_path.parent,
        context=f"{source_manifest_path} output_artifact_paths.target_contract_design_proposal_path",
    )
    resolved_source = _resolve_repeated_evidence_manifest_source(
        repeated_evidence_manifest_path,
        source_input_path=source_manifest_path,
        source_type=_THREE_WAY_SOURCE_MODE_RUNTIME_MANIFEST,
        expected_proposal_path=proposal_path,
    )
    resolved_target_mode_raw = manifest_payload.get("resolved_target_mode")
    if not isinstance(resolved_target_mode_raw, str) or not resolved_target_mode_raw:
        raise ValueError(
            "target-contract three-way source runtime manifest is missing resolved_target_mode: "
            f"{source_manifest_path}"
        )
    manifest_target_mode = _resolve_promotion_trainer_target_mode(resolved_target_mode_raw)
    if manifest_target_mode != resolved_source["source_target_mode"]:
        raise ValueError(
            "target-contract three-way source runtime manifest target_mode is inconsistent with the linked repeated-evidence evidence: "
            f"{source_manifest_path}"
        )
    return resolved_source


def _resolve_explicit_target_contract_three_way_source(raw_input: str | Path) -> dict[str, object]:
    source_input_path = Path(raw_input).expanduser()
    if not source_input_path.exists():
        raise FileNotFoundError(f"target-contract three-way source input not found: {source_input_path}")
    source_input_path = source_input_path.resolve()
    if source_input_path.is_dir():
        repeated_evidence_manifest_path = source_input_path / "target_design_repeated_evidence_manifest.json"
        proposal_path = source_input_path / "target_contract_design_proposal.json"
        summary_path = source_input_path / "target_contract_design_summary.json"
        if repeated_evidence_manifest_path.exists():
            return _resolve_repeated_evidence_manifest_source(
                repeated_evidence_manifest_path.resolve(),
                source_input_path=source_input_path,
                source_type="explicit_repeated_evidence_root",
            )
        if proposal_path.exists() or summary_path.exists():
            return _resolve_explicit_design_proposal_source(source_input_path)
        raise ValueError(
            "target-contract three-way explicit source inputs must be repeated-evidence roots or repeated-evidence design proposal roots: "
            f"{source_input_path}"
        )

    if source_input_path.suffix.lower() != ".json":
        raise ValueError(
            "target-contract three-way explicit source inputs must be repeated-evidence manifests or repeated-evidence design proposal JSON files: "
            f"{source_input_path}"
        )
    if source_input_path.name == "target_design_repeated_evidence_manifest.json":
        return _resolve_repeated_evidence_manifest_source(
            source_input_path,
            source_input_path=source_input_path,
            source_type="explicit_repeated_evidence_manifest",
        )
    if source_input_path.name == "target_design_repeated_evidence_runtime_manifest.json":
        raise ValueError(
            "target-contract three-way runtime manifest replay must use --repeated-evidence-runtime-manifest-path, "
            f"not --source-input: {source_input_path}"
        )
    if source_input_path.name in {"target_contract_design_proposal.json", "target_contract_design_summary.json"}:
        return _resolve_explicit_design_proposal_source(source_input_path)
    raise ValueError(
        "target-contract three-way explicit source inputs must be repeated-evidence manifests or repeated-evidence design proposal JSON files: "
        f"{source_input_path}"
    )


def _resolve_explicit_design_proposal_source(source_input_path: Path) -> dict[str, object]:
    if source_input_path.is_dir():
        proposal_path = source_input_path / "target_contract_design_proposal.json"
        summary_path = source_input_path / "target_contract_design_summary.json"
        source_type = "explicit_design_proposal_root"
    elif source_input_path.name == "target_contract_design_proposal.json":
        proposal_path = source_input_path
        summary_path = source_input_path.parent / "target_contract_design_summary.json"
        source_type = "explicit_design_proposal_json"
    else:
        proposal_path = source_input_path.parent / "target_contract_design_proposal.json"
        summary_path = source_input_path
        source_type = "explicit_design_summary_json"
    if not proposal_path.exists():
        raise FileNotFoundError(
            "target-contract three-way explicit design proposal source is missing target_contract_design_proposal.json: "
            f"{proposal_path}"
        )
    if not summary_path.exists():
        raise FileNotFoundError(
            "target-contract three-way explicit design proposal source is missing target_contract_design_summary.json: "
            f"{summary_path}"
        )
    proposal_payload = read_json(proposal_path)
    summary_payload = read_json(summary_path)
    summary_proposal = summary_payload.get("proposal")
    if not isinstance(summary_proposal, dict):
        raise ValueError(
            "target-contract three-way explicit design summary is missing proposal evidence: "
            f"{summary_path}"
        )
    proposal_candidate = _extract_best_candidate_name(proposal_payload, context=str(proposal_path))
    summary_candidate = _extract_best_candidate_name(summary_proposal, context=f"{summary_path} proposal")
    if proposal_candidate != summary_candidate:
        raise ValueError(
            "target-contract three-way explicit design proposal and summary disagree on the best target design candidate: "
            f"{proposal_path}"
        )
    repeated_evidence_manifest_path = _resolve_repeated_evidence_manifest_for_design_proposal_root(proposal_path.parent)
    return _resolve_repeated_evidence_manifest_source(
        repeated_evidence_manifest_path,
        source_input_path=source_input_path,
        source_type=source_type,
        expected_proposal_path=proposal_path,
    )


def _resolve_repeated_evidence_manifest_for_design_proposal_root(proposal_root: Path) -> Path:
    direct_candidate = proposal_root / "target_design_repeated_evidence_manifest.json"
    if direct_candidate.exists():
        return direct_candidate.resolve()
    suffix = "__target_contract_design"
    proposal_root_name = proposal_root.name
    if proposal_root_name.endswith(suffix):
        repeated_evidence_root = proposal_root.parent / proposal_root_name.removesuffix(suffix)
        candidate_manifest_path = repeated_evidence_root / "target_design_repeated_evidence_manifest.json"
        if candidate_manifest_path.exists():
            return candidate_manifest_path.resolve()
    raise FileNotFoundError(
        "target-contract three-way explicit design proposal source requires a sibling target_design_repeated_evidence_manifest.json: "
        f"{proposal_root}"
    )


def _resolve_repeated_evidence_manifest_source(
    repeated_evidence_manifest_path: Path,
    *,
    source_input_path: Path,
    source_type: str,
    expected_proposal_path: Path | None = None,
) -> dict[str, object]:
    manifest_payload = read_json(repeated_evidence_manifest_path)
    gate_outcome = manifest_payload.get("gate_outcome")
    if not isinstance(gate_outcome, dict):
        raise ValueError(
            "target-contract three-way source repeated-evidence manifest has invalid gate_outcome: "
            f"{repeated_evidence_manifest_path}"
        )
    source_multi_slice_manifest_path = _resolve_existing_path(
        manifest_payload.get("target_mode_multi_slice_manifest_path"),
        base_path=repeated_evidence_manifest_path.parent,
        context=f"{repeated_evidence_manifest_path} target_mode_multi_slice_manifest_path",
    )
    proposal_path = _resolve_existing_path(
        manifest_payload.get("target_contract_design_proposal_path"),
        base_path=repeated_evidence_manifest_path.parent,
        context=f"{repeated_evidence_manifest_path} target_contract_design_proposal_path",
    )
    if expected_proposal_path is not None and proposal_path != expected_proposal_path.resolve():
        raise ValueError(
            "target-contract three-way explicit source resolves to a different design proposal than the repeated-evidence manifest: "
            f"{source_input_path}"
        )
    proposal_payload = read_json(proposal_path)
    return {
        "source_type": source_type,
        "source_input_path": str(source_input_path),
        "source_repeated_evidence_manifest_path": str(repeated_evidence_manifest_path.resolve()),
        "source_repeated_evidence_root": str(repeated_evidence_manifest_path.parent.resolve()),
        "source_target_contract_design_proposal_path": str(proposal_path),
        "source_multi_slice_manifest_path": str(source_multi_slice_manifest_path),
        "top_target_design_candidate": _extract_best_candidate_name(proposal_payload, context=str(proposal_path)),
        "source_target_mode": _resolve_source_target_mode_from_multi_slice_manifest(source_multi_slice_manifest_path),
    }


def _extract_best_candidate_name(payload: dict[str, object], *, context: str) -> str:
    best_candidate = payload.get("best_target_design_candidate")
    if not isinstance(best_candidate, dict):
        raise ValueError(
            f"target-contract three-way source payload is missing best_target_design_candidate: {context}"
        )
    candidate_name = best_candidate.get("candidate_name")
    if not isinstance(candidate_name, str) or not candidate_name:
        raise ValueError(
            f"target-contract three-way source payload has invalid best_target_design_candidate.candidate_name: {context}"
        )
    return candidate_name


def _resolve_source_target_mode_from_multi_slice_manifest(source_multi_slice_manifest_path: Path) -> str:
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
            "target-contract three-way source multi-slice manifest is missing target_mode evidence: "
            f"{source_multi_slice_manifest_path}"
        )
    if len(resolved_modes) != 1:
        raise ValueError(
            "target-contract three-way source multi-slice manifest has inconsistent target_mode values across slices: "
            f"{source_multi_slice_manifest_path}"
        )
    return next(iter(resolved_modes))


def _resolve_existing_path(raw_path: object, *, base_path: Path, context: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"target-contract three-way source path is missing for {context}")
    candidate_path = Path(raw_path).expanduser()
    search_paths = [candidate_path] if candidate_path.is_absolute() else [base_path / candidate_path, Path.cwd() / candidate_path]
    for search_path in search_paths:
        if search_path.exists():
            return search_path.resolve()
    raise FileNotFoundError(f"target-contract three-way source path not found for {context}: {raw_path}")


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