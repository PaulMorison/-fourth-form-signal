from __future__ import annotations

"""Thin operator-facing command surface for promotions runtime observation runs."""

from dataclasses import dataclass
from datetime import UTC, datetime
import argparse
from pathlib import Path
import shlex
import sys
from typing import TextIO

from runtime.promotions.config import PromotionRuntimeConfigError


class PromotionOperatorCliUsageError(ValueError):
    """Raised when operator CLI arguments are invalid before runtime dispatch."""


@dataclass(frozen=True)
class PromotionOperatorCliContext:
    command: str
    execution_mode: str
    run_id: str
    as_of_date: str | None
    artifact_root: str | None
    local_inspection_root: str | None
    connect_timeout_seconds: int | None
    connect_retry_attempts: int | None
    connect_retry_backoff_seconds: float | None
    query_timeout_seconds: int | None
    partition_strategy: str | None
    partition_count: int | None
    auto_repartition_completed: bool | None
    max_completed_repartition_attempts: int | None
    max_completed_partition_count: int | None
    dispatch_target: str
    received_command: str
    proof_mode: bool = False
    proof_max_partitions: int | None = None
    proof_stop_after_stage: int | None = None
    proof_max_future_promotions: int | None = None
    proof_future_fallback_mode: str | None = None
    proof_future_fallback_topn_limit: int | None = None
    proof_future_fallback_slice_promotions: int | None = None
    proof_completed_fallback_mode: str | None = None
    proof_completed_fallback_topn_limit: int | None = None
    proof_completed_fallback_slice_promotions: int | None = None


class _OperatorArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise PromotionOperatorCliUsageError(message)


def main(argv: list[str] | None = None, *, stream: TextIO | None = None) -> None:
    output_stream = stream or sys.stdout
    received_argv = list(argv) if argv is not None else sys.argv[1:]
    received_command = _build_received_command(received_argv)
    parser = _build_parser()
    context: PromotionOperatorCliContext | None = None
    try:
        args = parser.parse_args(argv)
        context = _build_context(args, received_command=received_command)
        _render_startup(context, stream=output_stream)
        _dispatch(args)
    except PromotionOperatorCliUsageError as error:
        _render_fatal(context, error, received_command=received_command, stream=output_stream)
        raise SystemExit(2) from error
    except Exception as error:
        if context is not None and _runtime_progress_artifacts_exist(context):
            _render_runtime_exit(context, error, stream=output_stream)
        else:
            _render_fatal(context, error, received_command=received_command, stream=output_stream)
        raise SystemExit(1) from error


def _build_parser() -> argparse.ArgumentParser:
    parser = _OperatorArgumentParser(
        description="Run the promotions runtime in an operator-observation mode with thin wrappers over the existing runtime seams."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke_parser = subparsers.add_parser(
        "smoke",
        help="Run a synthetic or patched smoke observation run end to end.",
        description="Run the governed smoke observation flow and keep the existing smoke/runtime ownership unchanged.",
    )
    _add_shared_runtime_args(smoke_parser, include_local_inspection=True)
    smoke_parser.add_argument(
        "--mode",
        choices=("smoke_synthetic", "smoke_patched_extraction"),
        default="smoke_synthetic",
        help="Smoke execution mode. Use smoke_patched_extraction only when you want to feed saved completed/future extracts.",
    )
    smoke_parser.add_argument("--completed-base-path")
    smoke_parser.add_argument("--future-base-path")

    live_parser = subparsers.add_parser(
        "live",
        help="Run the live SQL observation flow end to end.",
        description="Run the governed live SQL operational cycle with readable operator output.",
    )
    _add_shared_runtime_args(live_parser, include_local_inspection=True)
    live_parser.add_argument(
        "--mode",
        choices=("live_sql",),
        default="live_sql",
        help="Live operator mode. The current operator surface intentionally keeps live execution on the governed live_sql seam.",
    )
    _add_partition_args(live_parser, include_partition_index=False)
    live_parser.add_argument(
        "--auto-repartition-completed",
        choices=("true", "false"),
        default="true",
    )
    live_parser.add_argument("--max-completed-repartition-attempts", type=int, default=3)
    live_parser.add_argument("--max-completed-partition-count", type=int, default=512)
    live_parser.add_argument("--proof-mode", action="store_true", help="Enable live-proof mode: real SQL extraction, real Stage 4 logic, but bounded to proof-max-partitions")
    live_parser.add_argument("--proof-max-partitions", type=int, help="Maximum partition count for proof-mode runs (overrides max-completed-partition-count)")
    live_parser.add_argument("--proof-stop-after-stage", type=int, help="Stop after this stage number in proof-mode (e.g., 4 stops after Stage 4 validation)")
    live_parser.add_argument("--proof-max-future-promotions", type=int, help="Bound Stage 6 future extraction to top-N rows for proof-mode runs")
    live_parser.add_argument(
        "--proof-future-fallback-mode",
        choices=("diagnostic_topn", "proof_slice"),
        help="In proof mode only, Stage 6 future fallback mode when no explicit proof-max-future-promotions is provided.",
    )
    live_parser.add_argument(
        "--proof-future-fallback-topn-limit",
        type=int,
        help="In proof mode Stage 6 diagnostic_topn fallback mode, top-N future promotions limit.",
    )
    live_parser.add_argument(
        "--proof-future-fallback-slice-promotions",
        type=int,
        help="In proof mode Stage 6 proof_slice fallback mode, bounded promotion count.",
    )
    live_parser.add_argument(
        "--proof-completed-fallback-mode",
        choices=("diagnostic_topn", "proof_slice"),
        help="In proof mode only, completed extraction fallback mode when preflight rejects full scope.",
    )
    live_parser.add_argument(
        "--proof-completed-fallback-topn-limit",
        type=int,
        help="In proof mode fallback diagnostic_topn mode, top-N completed promotions limit.",
    )
    live_parser.add_argument(
        "--proof-completed-fallback-slice-promotions",
        type=int,
        help="In proof mode fallback proof_slice mode, bounded promotion count.",
    )
    live_parser.add_argument("--planner-only", action="store_true")
    live_parser.add_argument("--run-preflight", action="store_true")

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Run the SQL planner/inspection surface without the downstream runtime stages.",
        description="Inspect SQL rendering, planner verdicts, row-count probes, or bounded extraction using the current inspection seam.",
    )
    _add_shared_runtime_args(inspect_parser, include_local_inspection=False)
    inspect_parser.add_argument(
        "--mode",
        choices=("live_sql", "diagnostic_topn"),
        default="live_sql",
        help="Inspection extraction mode. Use diagnostic_topn only for bounded extractor diagnosis.",
    )
    inspect_parser.add_argument("--selection-mode", choices=("completed", "future"), default="completed")
    _add_partition_args(inspect_parser, include_partition_index=True)
    inspect_parser.add_argument("--planner-only", action="store_true")
    inspect_parser.add_argument("--run-preflight", action="store_true")
    inspect_parser.add_argument("--run-row-count-probe", action="store_true")
    inspect_parser.add_argument("--run-extraction", action="store_true")
    inspect_parser.add_argument("--test-connection", action="store_true")
    inspect_parser.add_argument("--save-rendered-sql", action="store_true")
    inspect_parser.add_argument("--limit-promotions", type=int)
    inspect_parser.add_argument("--promotion-name-like")
    inspect_parser.add_argument("--store-number", type=int)
    inspect_parser.add_argument("--supplier-number", type=int)
    return parser


def _add_shared_runtime_args(parser: argparse.ArgumentParser, *, include_local_inspection: bool) -> None:
    parser.add_argument("--env-file")
    parser.add_argument("--server")
    parser.add_argument("--database")
    parser.add_argument("--schema")
    parser.add_argument("--promotion-advice-table")
    parser.add_argument("--pwlogd-table")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--odbc-driver")
    parser.add_argument("--connect-timeout-seconds", type=int)
    parser.add_argument("--connect-retry-attempts", type=int)
    parser.add_argument("--connect-retry-backoff-seconds", type=float)
    parser.add_argument("--query-timeout-seconds", type=int)
    parser.add_argument("--enable-landed-batches", choices=("true", "false"))
    parser.add_argument("--batch-row-count", type=int)
    parser.add_argument("--completed-sales-history-start-date")
    parser.add_argument("--enable-chunked-fetch", choices=("true", "false"))
    parser.add_argument("--chunk-row-count", type=int)
    parser.add_argument("--resume-completed-partitions", choices=("true", "false"))
    parser.add_argument("--stage-temp-chunk-files", choices=("true", "false"))
    parser.add_argument("--encrypt", choices=("yes", "no"))
    parser.add_argument("--trust-server-certificate", choices=("yes", "no"))
    parser.add_argument("--artifact-root")
    if include_local_inspection:
        parser.add_argument("--local-inspection-root")
        parser.add_argument("--disable-local-inspection-copy", action="store_true")
    parser.add_argument("--as-of-date")
    parser.add_argument(
        "--run-id",
        default=f"promotions-operator-{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}",
    )


def _add_partition_args(parser: argparse.ArgumentParser, *, include_partition_index: bool) -> None:
    parser.add_argument(
        "--partition-strategy",
        choices=(
            "store_number",
            "supplier_number",
            "store_sku_hash_bucket",
            "promotion_name_hash_bucket",
            "promotion_row_key_hash_bucket",
        ),
    )
    parser.add_argument("--partition-count", type=int)
    if include_partition_index:
        parser.add_argument("--partition-index", type=int)


def _build_smoke_argv(args: argparse.Namespace) -> list[str]:
    argv: list[str] = []
    _append_shared_runtime_args(argv, args, include_local_inspection=True)
    _append_option(argv, "--mode", args.mode)
    _append_option(argv, "--completed-base-path", args.completed_base_path)
    _append_option(argv, "--future-base-path", args.future_base_path)
    return argv


def _build_live_argv(args: argparse.Namespace) -> list[str]:
    argv: list[str] = []
    _append_shared_runtime_args(argv, args, include_local_inspection=True)
    _append_option(argv, "--partition-strategy", args.partition_strategy)
    _append_option(argv, "--partition-count", args.partition_count)
    _append_option(argv, "--auto-repartition-completed", args.auto_repartition_completed)
    _append_option(
        argv,
        "--max-completed-repartition-attempts",
        args.max_completed_repartition_attempts,
    )
    _append_option(
        argv,
        "--max-completed-partition-count",
        args.max_completed_partition_count,
    )
    _append_flag(argv, "--proof-mode", getattr(args, "proof_mode", False))
    _append_option(argv, "--proof-max-partitions", getattr(args, "proof_max_partitions", None))
    _append_option(argv, "--proof-stop-after-stage", getattr(args, "proof_stop_after_stage", None))
    _append_option(argv, "--proof-max-future-promotions", getattr(args, "proof_max_future_promotions", None))
    _append_option(
        argv,
        "--proof-future-fallback-mode",
        getattr(args, "proof_future_fallback_mode", None),
    )
    _append_option(
        argv,
        "--proof-future-fallback-topn-limit",
        getattr(args, "proof_future_fallback_topn_limit", None),
    )
    _append_option(
        argv,
        "--proof-future-fallback-slice-promotions",
        getattr(args, "proof_future_fallback_slice_promotions", None),
    )
    _append_option(
        argv,
        "--proof-completed-fallback-mode",
        getattr(args, "proof_completed_fallback_mode", None),
    )
    _append_option(
        argv,
        "--proof-completed-fallback-topn-limit",
        getattr(args, "proof_completed_fallback_topn_limit", None),
    )
    _append_option(
        argv,
        "--proof-completed-fallback-slice-promotions",
        getattr(args, "proof_completed_fallback_slice_promotions", None),
    )
    _append_flag(argv, "--planner-only", args.planner_only)
    _append_flag(argv, "--run-preflight", args.run_preflight)
    return argv


def _build_inspect_argv(args: argparse.Namespace) -> list[str]:
    argv: list[str] = []
    _append_shared_runtime_args(argv, args, include_local_inspection=False)
    _append_option(argv, "--selection-mode", args.selection_mode)
    _append_option(argv, "--extraction-mode", args.mode)
    _append_option(argv, "--partition-strategy", args.partition_strategy)
    _append_option(argv, "--partition-count", args.partition_count)
    _append_option(argv, "--partition-index", args.partition_index)
    _append_flag(argv, "--planner-only", args.planner_only)
    _append_flag(argv, "--run-preflight", args.run_preflight)
    _append_flag(argv, "--run-row-count-probe", args.run_row_count_probe)
    _append_flag(argv, "--run-extraction", args.run_extraction)
    _append_flag(argv, "--test-connection", args.test_connection)
    _append_flag(argv, "--save-rendered-sql", args.save_rendered_sql)
    _append_option(argv, "--limit-promotions", args.limit_promotions)
    _append_option(argv, "--promotion-name-like", args.promotion_name_like)
    _append_option(argv, "--store-number", args.store_number)
    _append_option(argv, "--supplier-number", args.supplier_number)
    return argv


def _append_shared_runtime_args(
    argv: list[str],
    args: argparse.Namespace,
    *,
    include_local_inspection: bool,
) -> None:
    _append_option(argv, "--env-file", args.env_file)
    _append_option(argv, "--server", args.server)
    _append_option(argv, "--database", args.database)
    _append_option(argv, "--schema", args.schema)
    _append_option(argv, "--promotion-advice-table", args.promotion_advice_table)
    _append_option(argv, "--pwlogd-table", args.pwlogd_table)
    _append_option(argv, "--username", args.username)
    _append_option(argv, "--password", args.password)
    _append_option(argv, "--odbc-driver", args.odbc_driver)
    _append_option(argv, "--connect-timeout-seconds", args.connect_timeout_seconds)
    _append_option(argv, "--connect-retry-attempts", args.connect_retry_attempts)
    _append_option(argv, "--connect-retry-backoff-seconds", args.connect_retry_backoff_seconds)
    _append_option(argv, "--query-timeout-seconds", args.query_timeout_seconds)
    _append_option(argv, "--enable-landed-batches", args.enable_landed_batches)
    _append_option(argv, "--batch-row-count", args.batch_row_count)
    _append_option(
        argv,
        "--completed-sales-history-start-date",
        args.completed_sales_history_start_date,
    )
    _append_option(argv, "--enable-chunked-fetch", args.enable_chunked_fetch)
    _append_option(argv, "--chunk-row-count", args.chunk_row_count)
    _append_option(argv, "--resume-completed-partitions", args.resume_completed_partitions)
    _append_option(argv, "--stage-temp-chunk-files", args.stage_temp_chunk_files)
    _append_option(argv, "--encrypt", args.encrypt)
    _append_option(argv, "--trust-server-certificate", args.trust_server_certificate)
    _append_option(argv, "--artifact-root", args.artifact_root)
    if include_local_inspection:
        _append_option(argv, "--local-inspection-root", getattr(args, "local_inspection_root", None))
        _append_flag(
            argv,
            "--disable-local-inspection-copy",
            getattr(args, "disable_local_inspection_copy", False),
        )
    _append_option(argv, "--as-of-date", args.as_of_date)
    _append_option(argv, "--run-id", args.run_id)


def _append_option(argv: list[str], flag: str, value: object | None) -> None:
    if value is None:
        return
    argv.extend([flag, str(value)])


def _append_flag(argv: list[str], flag: str, enabled: bool) -> None:
    if enabled:
        argv.append(flag)


def _build_context(
    args: argparse.Namespace,
    *,
    received_command: str,
) -> PromotionOperatorCliContext:
    execution_mode = getattr(args, "mode", None)
    if args.command == "live":
        execution_mode = "live_sql"
    if execution_mode is None and args.command == "inspect":
        execution_mode = getattr(args, "mode", "live_sql")
    return PromotionOperatorCliContext(
        command=args.command,
        execution_mode=str(execution_mode),
        run_id=args.run_id,
        as_of_date=getattr(args, "as_of_date", None),
        artifact_root=getattr(args, "artifact_root", None),
        local_inspection_root=getattr(args, "local_inspection_root", None),
        connect_timeout_seconds=getattr(args, "connect_timeout_seconds", None),
        connect_retry_attempts=getattr(args, "connect_retry_attempts", None),
        connect_retry_backoff_seconds=getattr(args, "connect_retry_backoff_seconds", None),
        query_timeout_seconds=getattr(args, "query_timeout_seconds", None),
        partition_strategy=getattr(args, "partition_strategy", None),
        partition_count=getattr(args, "partition_count", None),
        auto_repartition_completed=_optional_bool_arg(
            getattr(args, "auto_repartition_completed", None)
        ),
        max_completed_repartition_attempts=getattr(
            args,
            "max_completed_repartition_attempts",
            None,
        ),
        max_completed_partition_count=getattr(args, "max_completed_partition_count", None),
        proof_mode=getattr(args, "proof_mode", False),
        proof_max_partitions=getattr(args, "proof_max_partitions", None),
        proof_stop_after_stage=getattr(args, "proof_stop_after_stage", None),
        proof_max_future_promotions=getattr(args, "proof_max_future_promotions", None),
        proof_future_fallback_mode=getattr(args, "proof_future_fallback_mode", None),
        proof_future_fallback_topn_limit=getattr(
            args,
            "proof_future_fallback_topn_limit",
            None,
        ),
        proof_future_fallback_slice_promotions=getattr(
            args,
            "proof_future_fallback_slice_promotions",
            None,
        ),
        proof_completed_fallback_mode=getattr(args, "proof_completed_fallback_mode", None),
        proof_completed_fallback_topn_limit=getattr(
            args,
            "proof_completed_fallback_topn_limit",
            None,
        ),
        proof_completed_fallback_slice_promotions=getattr(
            args,
            "proof_completed_fallback_slice_promotions",
            None,
        ),
        dispatch_target=_dispatch_target(args.command),
        received_command=received_command,
    )


def _render_startup(context: PromotionOperatorCliContext, *, stream: TextIO) -> None:
    print("PROMOTIONS OPERATOR CLI", file=stream, flush=True)
    print(f"command: {context.command}", file=stream, flush=True)
    print(f"execution_mode: {context.execution_mode}", file=stream, flush=True)
    print(f"run_id: {context.run_id}", file=stream, flush=True)
    print(f"as_of_date: {context.as_of_date or 'default'}", file=stream, flush=True)
    print(f"artifact_root: {context.artifact_root or 'env/default'}", file=stream, flush=True)
    print(
        f"local_inspection_root: {context.local_inspection_root or 'disabled'}",
        file=stream,
        flush=True,
    )
    if context.proof_mode:
        print(f"PROOF_MODE: true", file=stream, flush=True)
        if context.proof_max_partitions is not None:
            print(f"proof_max_partitions: {context.proof_max_partitions}", file=stream, flush=True)
        if context.proof_stop_after_stage is not None:
            print(f"proof_stop_after_stage: {context.proof_stop_after_stage}", file=stream, flush=True)
        if context.proof_max_future_promotions is not None:
            print(f"proof_max_future_promotions: {context.proof_max_future_promotions}", file=stream, flush=True)
        if context.proof_future_fallback_mode is not None:
            print(
                f"proof_future_fallback_mode: {context.proof_future_fallback_mode}",
                file=stream,
                flush=True,
            )
        if context.proof_future_fallback_topn_limit is not None:
            print(
                "proof_future_fallback_topn_limit: "
                f"{context.proof_future_fallback_topn_limit}",
                file=stream,
                flush=True,
            )
        if context.proof_future_fallback_slice_promotions is not None:
            print(
                "proof_future_fallback_slice_promotions: "
                f"{context.proof_future_fallback_slice_promotions}",
                file=stream,
                flush=True,
            )
        if context.proof_completed_fallback_mode is not None:
            print(
                f"proof_completed_fallback_mode: {context.proof_completed_fallback_mode}",
                file=stream,
                flush=True,
            )
        if context.proof_completed_fallback_topn_limit is not None:
            print(
                "proof_completed_fallback_topn_limit: "
                f"{context.proof_completed_fallback_topn_limit}",
                file=stream,
                flush=True,
            )
        if context.proof_completed_fallback_slice_promotions is not None:
            print(
                "proof_completed_fallback_slice_promotions: "
                f"{context.proof_completed_fallback_slice_promotions}",
                file=stream,
                flush=True,
            )
    print(f"dispatch_target: {context.dispatch_target}", file=stream, flush=True)
    print(f"command_line: {context.received_command}", file=stream, flush=True)


def _render_fatal(
    context: PromotionOperatorCliContext | None,
    error: BaseException,
    *,
    received_command: str,
    stream: TextIO,
) -> None:
    print("FATAL OPERATOR CLI ERROR", file=stream, flush=True)
    print(f"  command_received: {received_command}", file=stream, flush=True)
    if context is not None:
        print(f"  command: {context.command}", file=stream, flush=True)
        print(f"  execution_mode: {context.execution_mode}", file=stream, flush=True)
        print(f"  run_id: {context.run_id}", file=stream, flush=True)
        print(f"  artifact_root: {context.artifact_root or 'env/default'}", file=stream, flush=True)
        print(
            f"  local_inspection_root: {context.local_inspection_root or 'disabled'}",
            file=stream,
            flush=True,
        )
        print(
            "  connect_timeout_seconds: "
            f"{context.connect_timeout_seconds if context.connect_timeout_seconds is not None else 'disabled'}",
            file=stream,
            flush=True,
        )
        print(
            "  connect_retry_attempts: "
            f"{context.connect_retry_attempts if context.connect_retry_attempts is not None else 'default'}",
            file=stream,
            flush=True,
        )
        print(
            "  connect_retry_backoff_seconds: "
            f"{context.connect_retry_backoff_seconds if context.connect_retry_backoff_seconds is not None else 'default'}",
            file=stream,
            flush=True,
        )
        if context.auto_repartition_completed is not None:
            print(
                f"  auto_repartition_completed: {str(context.auto_repartition_completed).lower()}",
                file=stream,
                flush=True,
            )
            print(
                "  max_completed_repartition_attempts: "
                f"{context.max_completed_repartition_attempts if context.max_completed_repartition_attempts is not None else 'default'}",
                file=stream,
                flush=True,
            )
            print(
                "  max_completed_partition_count: "
                f"{context.max_completed_partition_count if context.max_completed_partition_count is not None else 'default'}",
                file=stream,
                flush=True,
            )
    print(f"  cause_type: {type(error).__name__}", file=stream, flush=True)
    if isinstance(error, PromotionRuntimeConfigError):
        if error.field_name:
            print(f"  field: {error.field_name}", file=stream, flush=True)
        if error.source:
            print(f"  source: {error.source}", file=stream, flush=True)
        if error.expected_from:
            print(
                f"  expected_from: {', '.join(error.expected_from)}",
                file=stream,
                flush=True,
            )
    print(f"  cause: {_normalize_error_message(error)}", file=stream, flush=True)
    print(f"  next_action: {_next_action_for_error(error)}", file=stream, flush=True)


def _render_runtime_exit(
    context: PromotionOperatorCliContext,
    error: BaseException,
    *,
    stream: TextIO,
) -> None:
    print("OPERATOR CLI EXIT", file=stream, flush=True)
    print("  status: failed", file=stream, flush=True)
    print(f"  command: {context.command}", file=stream, flush=True)
    print(f"  run_id: {context.run_id}", file=stream, flush=True)
    print(f"  cause_type: {type(error).__name__}", file=stream, flush=True)
    print(f"  cause: {_normalize_error_message(error)}", file=stream, flush=True)
    print(
        "  next_action: Inspect the FAILED STAGE block above, then use "
        "python -m runtime.promotions.print_promotions_run_artifacts with this run id for the governed artifact links.",
        file=stream,
        flush=True,
    )


def _dispatch(args: argparse.Namespace) -> None:
    if args.command == "smoke":
        _dispatch_smoke(_build_smoke_argv(args))
        return
    if args.command == "live":
        _dispatch_live(_build_live_argv(args))
        return
    if args.command == "inspect":
        _dispatch_inspect(_build_inspect_argv(args))
        return
    raise ValueError(f"Unsupported operator command: {args.command}")


def _dispatch_smoke(argv: list[str]) -> None:
    from runtime.promotions.run_promotions_system_smoke import main as smoke_main

    smoke_main(argv)


def _dispatch_live(argv: list[str]) -> None:
    from runtime.promotions.run_promotions_operational_cycle import main as live_main

    live_main(argv)


def _dispatch_inspect(argv: list[str]) -> None:
    from runtime.promotions.inspect_promotions_sql_extraction import main as inspect_main

    inspect_main(argv)


def _dispatch_target(command: str) -> str:
    if command == "smoke":
        return "runtime.promotions.run_promotions_system_smoke"
    if command == "live":
        return "runtime.promotions.run_promotions_operational_cycle"
    if command == "inspect":
        return "runtime.promotions.inspect_promotions_sql_extraction"
    return "unknown"


def _runtime_progress_artifacts_exist(context: PromotionOperatorCliContext) -> bool:
    if context.artifact_root is None:
        return False
    manifest_root = Path(context.artifact_root) / "manifests" / context.run_id
    log_root = Path(context.artifact_root) / "logs" / context.run_id
    return (manifest_root / "operator_run_summary.json").exists() or (log_root / "operator_run.log").exists()


def _normalize_error_message(error: BaseException) -> str:
    message = str(error).strip() or type(error).__name__
    return " ".join(message.split())


def _next_action_for_error(error: BaseException) -> str:
    if isinstance(error, PromotionOperatorCliUsageError):
        return "Run the operator command with --help to verify the required flags, then rerun."
    if isinstance(error, PromotionRuntimeConfigError) and error.next_action:
        return error.next_action
    if isinstance(error, ModuleNotFoundError):
        return "Ensure the active .venv has this repo installed in editable mode with '/Users/paulmorison/Library/CloudStorage/OneDrive-Management4HealthPtyLtd/Coding & Data/Fourth Form Signal/.venv/bin/python -m pip install -e .' from the repo root, then rerun."
    return "Fix the reported cause and rerun the operator command."


def _build_received_command(received_argv: list[str]) -> str:
    quoted_args = " ".join(shlex.quote(argument) for argument in received_argv)
    if quoted_args:
        return f"{shlex.quote(sys.executable)} -m runtime.promotions.run_promotions_operator {quoted_args}"
    return f"{shlex.quote(sys.executable)} -m runtime.promotions.run_promotions_operator"


def _optional_bool_arg(raw_value: str | None) -> bool | None:
    if raw_value is None:
        return None
    return raw_value == "true"


if __name__ == "__main__":
    main()