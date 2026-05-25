from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import dataclass

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from data.promotions.partition_rollup_validator import (  # noqa: E402
    PartitionRollupValidationError,
    validate_partition_completion_for_rollup,
)


@dataclass
class _StubArtifact:
    """Mirrors the subset of PromotionOperationalCycleExtractionArtifacts the
    validator inspects."""

    partition_index: int
    partition_count: int
    base_path: str | None
    manifest_path: str | None
    partition_completion_marker_path: str | None


def _write_partition(
    *,
    root: Path,
    partition_index: int,
    partition_count: int,
    columns: tuple[str, ...] = ("promotion_row_key", "store_number", "sku_number"),
    row_count: int = 3,
    finalized: bool = True,
    write_parquet: bool = True,
    write_marker: bool = True,
    write_manifest: bool = True,
) -> _StubArtifact:
    partition_dir = root / f"partition_{partition_index:02d}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    base_path = partition_dir / "promotion_base.parquet"
    manifest_path = partition_dir / "extraction_manifest.json"
    marker_path = partition_dir / "extraction_partition_completion.json"
    if write_parquet:
        base_path.write_bytes(b"PAR1\x00\x00fake-parquet")
    if write_manifest:
        manifest_path.write_text(
            json.dumps({"row_count": row_count, "columns": list(columns)}),
            encoding="utf-8",
        )
    if write_marker:
        marker_path.write_text(
            json.dumps(
                {
                    "partition_completion_state": "finalized" if finalized else "in_progress",
                    "row_count": row_count,
                    "completed_at_utc": "2026-05-16T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
    return _StubArtifact(
        partition_index=partition_index,
        partition_count=partition_count,
        base_path=str(base_path),
        manifest_path=str(manifest_path),
        partition_completion_marker_path=str(marker_path),
    )


class PartitionRollupValidatorTests(unittest.TestCase):
    def test_validator_passes_when_all_partitions_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = [
                _write_partition(root=root, partition_index=i, partition_count=3)
                for i in range(1, 4)
            ]
            registry_path = root / "partition_rollup_registry.json"
            registry = validate_partition_completion_for_rollup(
                run_id="run-ok",
                partition_strategy="store_sku_hash_bucket",
                expected_partition_count=3,
                partition_artifacts=artifacts,
                registry_output_path=registry_path,
                max_reconciliation_retries=0,
                reconciliation_backoff_seconds=0.0,
            )
            self.assertTrue(registry.rollup_ready_flag)
            self.assertEqual(registry.completed_partition_count, 3)
            self.assertEqual(registry.missing_partition_ids, ())
            self.assertEqual(registry.schema_mismatch_partition_ids, ())
            self.assertTrue(registry_path.exists())
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["rollup_ready_flag"])
            self.assertEqual(payload["expected_partition_count"], 3)
            self.assertEqual(len(payload["partitions"]), 3)
            self.assertEqual(payload["partitions"][0]["completion_status"], "COMPLETE")

    def test_validator_blocks_when_partition_parquet_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = [
                _write_partition(root=root, partition_index=1, partition_count=2),
                _write_partition(
                    root=root,
                    partition_index=2,
                    partition_count=2,
                    write_parquet=False,
                ),
            ]
            registry_path = root / "partition_rollup_registry.json"
            with self.assertRaises(PartitionRollupValidationError) as ctx:
                validate_partition_completion_for_rollup(
                    run_id="run-missing-parquet",
                    partition_strategy="store_sku_hash_bucket",
                    expected_partition_count=2,
                    partition_artifacts=artifacts,
                    registry_output_path=registry_path,
                    max_reconciliation_retries=0,
                    reconciliation_backoff_seconds=0.0,
                )
            registry = ctx.exception.registry
            self.assertFalse(registry.rollup_ready_flag)
            self.assertEqual(len(registry.missing_partition_ids), 1)
            self.assertIn("partition-02-of-02", registry.missing_partition_ids[0])
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertFalse(payload["rollup_ready_flag"])
            self.assertEqual(len(payload["missing_partition_ids"]), 1)
            partition2 = next(
                p for p in payload["partitions"] if p["partition_index"] == 2
            )
            self.assertEqual(partition2["completion_status"], "INCOMPLETE")
            self.assertTrue(any("promotion_base.parquet" in mf for mf in partition2["missing_files"]))

    def test_validator_blocks_when_completion_state_not_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = [
                _write_partition(root=root, partition_index=1, partition_count=2),
                _write_partition(
                    root=root,
                    partition_index=2,
                    partition_count=2,
                    finalized=False,
                ),
            ]
            registry_path = root / "partition_rollup_registry.json"
            with self.assertRaises(PartitionRollupValidationError):
                validate_partition_completion_for_rollup(
                    run_id="run-not-finalized",
                    partition_strategy="store_sku_hash_bucket",
                    expected_partition_count=2,
                    partition_artifacts=artifacts,
                    registry_output_path=registry_path,
                    max_reconciliation_retries=0,
                    reconciliation_backoff_seconds=0.0,
                )

    def test_validator_blocks_when_schema_fingerprints_differ(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = [
                _write_partition(
                    root=root,
                    partition_index=1,
                    partition_count=3,
                    columns=("a", "b", "c"),
                ),
                _write_partition(
                    root=root,
                    partition_index=2,
                    partition_count=3,
                    columns=("a", "b", "c"),
                ),
                _write_partition(
                    root=root,
                    partition_index=3,
                    partition_count=3,
                    columns=("a", "b", "DIFFERENT"),
                ),
            ]
            registry_path = root / "partition_rollup_registry.json"
            with self.assertRaises(PartitionRollupValidationError) as ctx:
                validate_partition_completion_for_rollup(
                    run_id="run-schema-mismatch",
                    partition_strategy="store_sku_hash_bucket",
                    expected_partition_count=3,
                    partition_artifacts=artifacts,
                    registry_output_path=registry_path,
                    max_reconciliation_retries=0,
                    reconciliation_backoff_seconds=0.0,
                )
            registry = ctx.exception.registry
            self.assertEqual(len(registry.schema_mismatch_partition_ids), 1)
            self.assertIn("partition-03-of-03", registry.schema_mismatch_partition_ids[0])

    def test_validator_blocks_when_partition_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = [
                _write_partition(root=root, partition_index=1, partition_count=3),
                _write_partition(root=root, partition_index=2, partition_count=3),
            ]
            registry_path = root / "partition_rollup_registry.json"
            with self.assertRaises(PartitionRollupValidationError) as ctx:
                validate_partition_completion_for_rollup(
                    run_id="run-count-mismatch",
                    partition_strategy="store_sku_hash_bucket",
                    expected_partition_count=3,
                    partition_artifacts=artifacts,
                    registry_output_path=registry_path,
                    max_reconciliation_retries=0,
                    reconciliation_backoff_seconds=0.0,
                )
            registry = ctx.exception.registry
            self.assertFalse(registry.rollup_ready_flag)
            self.assertIn("expected 3", registry.rollup_ready_reason)

    def test_validator_retries_then_succeeds_when_marker_appears(self) -> None:
        # Simulate filesystem visibility lag: marker missing on attempt 1,
        # appears before retry 2.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = [
                _write_partition(root=root, partition_index=1, partition_count=2),
                _write_partition(
                    root=root,
                    partition_index=2,
                    partition_count=2,
                    write_marker=False,
                ),
            ]
            # Now write the marker that was originally absent, then run the
            # validator with retries enabled.
            marker_path = Path(artifacts[1].partition_completion_marker_path)
            marker_path.write_text(
                json.dumps(
                    {
                        "partition_completion_state": "finalized",
                        "row_count": 3,
                        "completed_at_utc": "2026-05-16T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            registry_path = root / "partition_rollup_registry.json"
            registry = validate_partition_completion_for_rollup(
                run_id="run-retry",
                partition_strategy="store_sku_hash_bucket",
                expected_partition_count=2,
                partition_artifacts=artifacts,
                registry_output_path=registry_path,
                max_reconciliation_retries=3,
                reconciliation_backoff_seconds=0.0,
            )
            self.assertTrue(registry.rollup_ready_flag)
            self.assertEqual(registry.reconciliation_attempts, 1)


if __name__ == "__main__":
    unittest.main()
