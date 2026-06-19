from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from runtime.promotions.promotion_run_mode_decider import (
    PromotionRunDecision,
    PromotionRunDecisionInput,
    decide_run_mode,
)
from runtime.promotions.promotion_run_registry import (
    expected_artifact_locations,
    inspect_registry_state,
    resolve_artifact_paths,
)
from runtime.promotions.run_promotions_operational_cycle import main as operational_cycle_main


DEFAULT_ARTIFACT_ROOT = "/Users/paulmorison/promotions_runtime_governed"
DEFAULT_SUMMARY_ROOT = "tmp/promotions_runs"


class PromotionRunControllerError(RuntimeError):
    """Raised when orchestration cannot proceed safely."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Governed promotions orchestration entrypoint for one-command execution."
    )
    parser.add_argument("--mode", choices=("auto", "train", "skip-train", "validate-only"), default="auto")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--local-inspection-root")
    parser.add_argument("--connect-timeout-seconds", type=int, default=60)
    parser.add_argument("--query-timeout-seconds", type=int)
    parser.add_argument("--score-run-id")
    parser.add_argument("--decision-surface-run-id")
    parser.add_argument("--skip-publisher", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-training-placeholder", action="store_true")
    parser.add_argument("--summary-root", default=DEFAULT_SUMMARY_ROOT)
    return parser


def _build_operational_cycle_argv(args: argparse.Namespace) -> list[str]:
    argv = [
        "--env-file",
        args.env_file,
        "--artifact-root",
        args.artifact_root,
        "--run-id",
        args.run_id,
        "--as-of-date",
        args.as_of_date,
        "--connect-timeout-seconds",
        str(args.connect_timeout_seconds),
    ]

    if args.local_inspection_root:
        argv.extend(["--local-inspection-root", args.local_inspection_root])

    if args.query_timeout_seconds is not None:
        argv.extend(["--query-timeout-seconds", str(args.query_timeout_seconds)])

    if args.score_run_id:
        argv.extend(["--score-run-id", args.score_run_id])

    if args.decision_surface_run_id:
        argv.extend(["--decision-surface-run-id", args.decision_surface_run_id])

    return argv


def _write_summary(*, summary_path: Path, payload: dict[str, Any]) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _log(message: str) -> None:
    print(f"[promotions-run] {message}")


def _run_training_placeholder(*, allow_training_placeholder: bool) -> None:
    if allow_training_placeholder:
        _log("training placeholder explicitly allowed; no-op training stub executed")
        return
    raise PromotionRunControllerError(
        "Training path selected but no training workflow is wired in this orchestration layer. "
        "Re-run with --allow-training-placeholder to acknowledge no-op training for now."
    )


def _execute_selected_mode(
    *,
    args: argparse.Namespace,
    decision: PromotionRunDecision,
    operational_cycle_argv: list[str],
) -> list[str]:
    actions_executed: list[str] = []

    if decision.selected_mode == "validate-only":
        _log("executing validate-only flow via operational preflight/planner")
        run_argv = [*operational_cycle_argv, "--run-preflight", "--planner-only"]
        if args.skip_publisher:
            # Runtime has no direct skip-publisher flag, so stop proof-mode before Stage 12.
            run_argv.extend(["--proof-mode", "--proof-stop-after-stage", "11"])
        operational_cycle_main(run_argv)
        actions_executed.append("operational_cycle_validate_only")
        return actions_executed

    if decision.should_train:
        _log("executing training path")
        _run_training_placeholder(
            allow_training_placeholder=args.allow_training_placeholder,
        )
        actions_executed.append("training_placeholder")

    _log("executing prediction cycle")
    run_argv = list(operational_cycle_argv)
    if args.skip_publisher:
        run_argv.extend(["--proof-mode", "--proof-stop-after-stage", "11"])
    operational_cycle_main(run_argv)
    actions_executed.append("operational_cycle_prediction")
    return actions_executed


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    started_at = datetime.now(tz=UTC)
    summary_path = Path(args.summary_root) / args.run_id / "run_summary.json"

    _log(f"starting promotions run controller: run_id={args.run_id} mode={args.mode}")

    local_inspection_root = args.local_inspection_root
    if not local_inspection_root:
        local_inspection_root = f"/tmp/promotions_{args.run_id}/local_inspection"

    artifact_paths = resolve_artifact_paths(
        artifact_root=args.artifact_root,
        env_file=args.env_file,
        local_inspection_root=local_inspection_root,
    )

    registry_snapshot = inspect_registry_state(
        artifact_paths=artifact_paths,
        run_id=args.run_id,
        as_of_date=args.as_of_date,
    )

    decision = decide_run_mode(
        PromotionRunDecisionInput(
            requested_mode=args.mode,
            drift_signal=registry_snapshot.drift_signal,
            model_approved=registry_snapshot.model_approved,
            schema_approved=registry_snapshot.schema_approved,
            training_permitted=args.allow_training_placeholder,
        )
    )

    warnings = [*registry_snapshot.warnings, *decision.warnings]
    blockers = list(decision.blockers)
    if args.skip_publisher:
        warnings.append(
            "skip-publisher requested; controller maps this to proof stop at stage 11."
        )

    if blockers:
        _log(f"blockers detected: {len(blockers)}")
    if warnings:
        _log(f"warnings detected: {len(warnings)}")

    operational_cycle_argv = _build_operational_cycle_argv(args)
    actions_planned = [f"mode:{decision.selected_mode}", "runtime:run_promotions_operational_cycle"]

    status = "ready"
    actions_executed: list[str] = []
    exit_code = 0

    if args.dry_run:
        status = "dry_run_ready"
        _log("dry-run enabled; runtime execution skipped")
    else:
        if blockers and decision.selected_mode != "validate-only":
            status = "blocked"
            exit_code = 2
            _log("execution blocked due to governance blockers")
        else:
            try:
                actions_executed = _execute_selected_mode(
                    args=args,
                    decision=decision,
                    operational_cycle_argv=operational_cycle_argv,
                )
                status = "completed"
            except Exception as error:
                status = "failed"
                exit_code = 1
                blockers.append(str(error))
                _log(f"run failed: {error}")

    summary_payload: dict[str, Any] = {
        "run_id": args.run_id,
        "as_of_date": args.as_of_date,
        "requested_mode": args.mode,
        "selected_mode": decision.selected_mode,
        "should_train": decision.should_train,
        "dry_run": bool(args.dry_run),
        "status": status,
        "timestamp_utc": started_at.isoformat(),
        "warnings": warnings,
        "blockers": blockers,
        "drift_signal": registry_snapshot.drift_signal,
        "model_approved": registry_snapshot.model_approved,
        "schema_approved": registry_snapshot.schema_approved,
        "env_file": args.env_file,
        "artifact_root": str(artifact_paths.root),
        "local_inspection_root": str(artifact_paths.local_inspection_root) if artifact_paths.local_inspection_root else None,
        "connect_timeout_seconds": args.connect_timeout_seconds,
        "query_timeout_seconds": args.query_timeout_seconds,
        "skip_publisher": bool(args.skip_publisher),
        "allow_training_placeholder": bool(args.allow_training_placeholder),
        "actions_planned": actions_planned,
        "actions_executed": actions_executed,
        "operational_cycle_args": operational_cycle_argv,
        "expected_artifacts": expected_artifact_locations(
            artifact_paths=artifact_paths,
            run_id=args.run_id,
        ),
    }

    _write_summary(summary_path=summary_path, payload=summary_payload)
    _log(f"summary written: {summary_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
