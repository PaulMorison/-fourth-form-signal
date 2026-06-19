from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_join_spec_pack import (  # noqa: E402
    PromotionsMaterializedSourceJoinSpecPackError,
    SPEC_BLOCKED_LOW_COVERAGE,
    SPEC_BLOCKED_ROW_EXPLOSION_RISK,
    SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN,
    SPEC_READY_WITH_QUARANTINE,
    build_promotions_materialized_source_join_spec_pack,
    write_promotions_materialized_source_join_spec_pack,
)


PROMOTION_KEY = "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1"
PROMOTION_NAME = "Allocation Report - WK47&48 WINTER PART 1"
PROMOTION_FOLDER_NAME = "promotion_772-2026-05-21-2026-06-03-allocation-report-wk47-48-winter-part-1"

SECOND_PROMOTION_KEY = "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX"
SECOND_PROMOTION_NAME = "Allocation Report - WK45&46 BABY & YOU BOX"
SECOND_PROMOTION_FOLDER_NAME = "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_validation_inputs(
    packet_root: Path | None = None,
    *,
    validation_root: Path | None = None,
    promotion_key: str = PROMOTION_KEY,
    promotion_name: str = PROMOTION_NAME,
    promotion_folder_name: str = PROMOTION_FOLDER_NAME,
    actual_source: str = "/tmp/actual_outcome.csv",
    operator_source: str = "/tmp/operator_audit.csv",
    selected_promotion: str | None = None,
    actual_status: str = "JOIN_READY",
    operator_status: str = "JOIN_READY",
    actual_match_rate: float = 0.999722,
    operator_match_rate: float = 0.999722,
    duplicate_key_count_actual: int = 0,
    duplicate_key_count_operator: int = 0,
    row_explosion_actual: int = 0,
    row_explosion_operator: int = 0,
    include_failure: bool = True,
) -> None:
    if validation_root is None:
        if packet_root is None:
            raise ValueError("packet_root or validation_root is required")
        validation_root = packet_root / "materialized_source_join_key_validation"
    selected_promotion_key = selected_promotion or promotion_key
    join_key = "store_number + promotion_start_date + promotion_name + sku_number"
    _write_csv(
        validation_root / "materialized_source_join_key_validation_summary.csv",
        [
            {
                "metric_name": "SELECTED_PROMOTION",
                "metric_value": selected_promotion_key,
                "metric_display": selected_promotion_key,
                "notes": "selected promotion",
            },
            {
                "metric_name": "ACTUAL_SOURCE_STATUS",
                "metric_value": actual_status,
                "metric_display": actual_status,
                "notes": "actual status",
            },
            {
                "metric_name": "OPERATOR_SOURCE_STATUS",
                "metric_value": operator_status,
                "metric_display": operator_status,
                "notes": "operator status",
            },
            {
                "metric_name": "BEST_JOIN_KEY",
                "metric_value": join_key,
                "metric_display": join_key,
                "notes": "best join key",
            },
            {
                "metric_name": "DUPLICATE_RISK_FLAG",
                "metric_value": int(duplicate_key_count_actual > 0 or duplicate_key_count_operator > 0),
                "metric_display": str(int(duplicate_key_count_actual > 0 or duplicate_key_count_operator > 0)),
                "notes": "duplicate risk",
            },
            {
                "metric_name": "ROW_EXPLOSION_RISK_FLAG",
                "metric_value": int(row_explosion_actual > 0 or row_explosion_operator > 0),
                "metric_display": str(int(row_explosion_actual > 0 or row_explosion_operator > 0)),
                "notes": "row explosion risk",
            },
            {
                "metric_name": "JOIN_SAFE_TO_EXECUTE_NEXT_FLAG",
                "metric_value": int(row_explosion_actual == 0 and row_explosion_operator == 0),
                "metric_display": str(int(row_explosion_actual == 0 and row_explosion_operator == 0)),
                "notes": "join safe",
            },
        ],
    )
    _write_csv(
        validation_root / "materialized_source_join_key_validation_plan.csv",
        [
            {
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_folder_name": promotion_folder_name,
                "candidate_source_role": "ACTUAL_OUTCOME",
                "candidate_source_path": actual_source,
                "recommended_join_key": join_key,
                "source_row_count": 3598,
                "source_unique_sku_count": 3597,
                "candidate_source_row_count": 3597,
                "candidate_source_unique_sku_count": 3597,
                "matched_source_rows": int(round(3598 * actual_match_rate)),
                "unmatched_source_rows": 3598 - int(round(3598 * actual_match_rate)),
                "match_rate": actual_match_rate,
                "duplicate_key_count_source": 0,
                "duplicate_key_count_candidate": duplicate_key_count_actual,
                "one_to_one_join_safe_flag": 1 if actual_status == "JOIN_READY" else 0,
                "many_to_one_join_risk_flag": 0,
                "row_explosion_risk_flag": row_explosion_actual,
                "join_readiness_status": actual_status,
                "safe_to_execute_next_flag": 1 if actual_status in {"JOIN_READY", "JOIN_READY_WITH_DUPLICATE_REVIEW"} and row_explosion_actual == 0 else 0,
                "recommended_next_step": "author actual join spec",
                "reason": "actual plan",
            },
            {
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_folder_name": promotion_folder_name,
                "candidate_source_role": "OPERATOR_AUDIT",
                "candidate_source_path": operator_source,
                "recommended_join_key": join_key,
                "source_row_count": 3598,
                "source_unique_sku_count": 3597,
                "candidate_source_row_count": 3597,
                "candidate_source_unique_sku_count": 3597,
                "matched_source_rows": int(round(3598 * operator_match_rate)),
                "unmatched_source_rows": 3598 - int(round(3598 * operator_match_rate)),
                "match_rate": operator_match_rate,
                "duplicate_key_count_source": 0,
                "duplicate_key_count_candidate": duplicate_key_count_operator,
                "one_to_one_join_safe_flag": 1 if operator_status == "JOIN_READY" else 0,
                "many_to_one_join_risk_flag": 0,
                "row_explosion_risk_flag": row_explosion_operator,
                "join_readiness_status": operator_status,
                "safe_to_execute_next_flag": 1 if operator_status in {"JOIN_READY", "JOIN_READY_WITH_DUPLICATE_REVIEW"} and row_explosion_operator == 0 else 0,
                "recommended_next_step": "author operator join spec",
                "reason": "operator plan",
            },
        ],
    )
    if include_failure:
        _write_csv(
            validation_root / "materialized_source_join_key_validation_failures.csv",
            [
                {
                    "promotion_key": promotion_key,
                    "candidate_source_role": "ACTUAL_OUTCOME",
                    "candidate_source_path": actual_source,
                    "recommended_join_key": join_key,
                    "failure_type": "MISSING_SOURCE_KEY_VALUE",
                    "source_row_number": 48,
                    "store_number": "772",
                    "promotion_start_date": promotion_key.split("|", 3)[1],
                    "promotion_name": promotion_name,
                    "sku_number": "",
                    "normalized_join_key": "",
                    "failure_reason": "At least one required key field is blank after normalization.",
                },
                {
                    "promotion_key": promotion_key,
                    "candidate_source_role": "OPERATOR_AUDIT",
                    "candidate_source_path": operator_source,
                    "recommended_join_key": join_key,
                    "failure_type": "MISSING_SOURCE_KEY_VALUE",
                    "source_row_number": 48,
                    "store_number": "772",
                    "promotion_start_date": promotion_key.split("|", 3)[1],
                    "promotion_name": promotion_name,
                    "sku_number": "",
                    "normalized_join_key": "",
                    "failure_reason": "At least one required key field is blank after normalization.",
                },
            ],
        )
    else:
        _write_csv(
            validation_root / "materialized_source_join_key_validation_failures.csv",
            [],
        )
    duplicate_rows: list[dict[str, object]] = []
    if duplicate_key_count_actual > 0:
        duplicate_rows.append(
            {
                "promotion_key": promotion_key,
                "candidate_source_role": "ACTUAL_OUTCOME",
                "candidate_source_path": actual_source,
                "dataset_role": "CANDIDATE",
                "recommended_join_key": join_key,
                "normalized_join_key": f"772|{promotion_key.split('|', 3)[1]}|{promotion_name.upper()}|1002",
                "duplicate_row_count": duplicate_key_count_actual + 1,
                "store_number": "772",
                "promotion_start_date": promotion_key.split("|", 3)[1],
                "promotion_name": promotion_name,
                "sku_number": "1002",
            }
        )
    if duplicate_key_count_operator > 0:
        duplicate_rows.append(
            {
                "promotion_key": promotion_key,
                "candidate_source_role": "OPERATOR_AUDIT",
                "candidate_source_path": operator_source,
                "dataset_role": "CANDIDATE",
                "recommended_join_key": join_key,
                "normalized_join_key": f"772|{promotion_key.split('|', 3)[1]}|{promotion_name.upper()}|1002",
                "duplicate_row_count": duplicate_key_count_operator + 1,
                "store_number": "772",
                "promotion_start_date": promotion_key.split("|", 3)[1],
                "promotion_name": promotion_name,
                "sku_number": "1002",
            }
        )
    _write_csv(
        validation_root / "materialized_source_join_key_validation_duplicates.csv",
        duplicate_rows,
    )


def _append_secondary_validation_inputs(validation_root: Path) -> None:
    def _read_optional_csv(path: Path) -> pd.DataFrame:
        try:
            return pd.read_csv(path, keep_default_na=False)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    plan_frame = pd.read_csv(validation_root / "materialized_source_join_key_validation_plan.csv")
    failures_frame = _read_optional_csv(
        validation_root / "materialized_source_join_key_validation_failures.csv"
    )
    duplicates_frame = _read_optional_csv(
        validation_root / "materialized_source_join_key_validation_duplicates.csv"
    )

    secondary_root = validation_root / "__secondary__"
    _write_validation_inputs(
        validation_root=secondary_root,
        promotion_key=SECOND_PROMOTION_KEY,
        promotion_name=SECOND_PROMOTION_NAME,
        promotion_folder_name=SECOND_PROMOTION_FOLDER_NAME,
        actual_source="/tmp/actual_outcome_second.csv",
        operator_source="/tmp/operator_audit_second.csv",
        include_failure=False,
    )
    secondary_plan_frame = pd.read_csv(
        secondary_root / "materialized_source_join_key_validation_plan.csv"
    )
    secondary_failures_frame = _read_optional_csv(
        secondary_root / "materialized_source_join_key_validation_failures.csv"
    )
    secondary_duplicates_frame = _read_optional_csv(
        secondary_root / "materialized_source_join_key_validation_duplicates.csv"
    )

    _write_csv(
        validation_root / "materialized_source_join_key_validation_plan.csv",
        pd.concat([plan_frame, secondary_plan_frame], ignore_index=True).to_dict("records"),
    )
    _write_csv(
        validation_root / "materialized_source_join_key_validation_failures.csv",
        pd.concat([failures_frame, secondary_failures_frame], ignore_index=True).to_dict("records"),
    )
    _write_csv(
        validation_root / "materialized_source_join_key_validation_duplicates.csv",
        pd.concat([duplicates_frame, secondary_duplicates_frame], ignore_index=True).to_dict("records"),
    )


class PromotionsMaterializedSourceJoinSpecPackTests(unittest.TestCase):
    def test_build_join_spec_pack_marks_ready_with_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_validation_inputs(packet_root)

            result = build_promotions_materialized_source_join_spec_pack(packet_root=packet_root)

            self.assertEqual(
                result.selected_promotion_key,
                "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
            )
            self.assertEqual(result.overall_spec_status, SPEC_READY_WITH_QUARANTINE)
            self.assertEqual(result.execution_allowed_flag, 1)
            self.assertEqual(len(result.quarantine_rows_frame.index), 1)
            self.assertTrue(result.sources_frame["join_source_type"].astype(str).eq("ACTUAL_OUTCOME").any())
            self.assertTrue(result.sources_frame["join_source_type"].astype(str).eq("OPERATOR_AUDIT").any())

    def test_build_join_spec_pack_blocks_row_explosion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_validation_inputs(
                packet_root,
                operator_status="JOIN_BLOCKED_ROW_EXPLOSION_RISK",
                row_explosion_operator=1,
                include_failure=False,
            )

            result = build_promotions_materialized_source_join_spec_pack(packet_root=packet_root)

            self.assertEqual(result.overall_spec_status, SPEC_BLOCKED_ROW_EXPLOSION_RISK)
            self.assertEqual(result.execution_allowed_flag, 0)

    def test_build_join_spec_pack_blocks_low_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_validation_inputs(
                packet_root,
                actual_status="JOIN_BLOCKED_LOW_COVERAGE",
                actual_match_rate=0.81,
                include_failure=False,
            )

            result = build_promotions_materialized_source_join_spec_pack(packet_root=packet_root)

            self.assertEqual(result.overall_spec_status, SPEC_BLOCKED_LOW_COVERAGE)
            self.assertEqual(result.execution_allowed_flag, 0)

    def test_write_join_spec_pack_writes_guardrails_and_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_validation_inputs(packet_root)

            artifacts = write_promotions_materialized_source_join_spec_pack(packet_root=packet_root)

            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.sources_csv_path).exists())
            self.assertTrue(Path(artifacts.keys_csv_path).exists())
            self.assertTrue(Path(artifacts.quarantine_rows_csv_path).exists())
            self.assertTrue(Path(artifacts.guardrails_csv_path).exists())
            self.assertTrue(Path(artifacts.execution_checklist_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())

            guardrails_frame = pd.read_csv(artifacts.guardrails_csv_path)
            checklist_frame = pd.read_csv(artifacts.execution_checklist_csv_path)
            self.assertGreaterEqual(len(guardrails_frame.index), 7)
            self.assertGreaterEqual(len(checklist_frame.index), 10)

    def test_build_join_spec_pack_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_validation_inputs(
                packet_root,
                actual_status="JOIN_BLOCKED_LOW_COVERAGE",
                actual_match_rate=0.81,
                include_failure=False,
            )
            _write_validation_inputs(
                validation_root=upstream_root / "materialized_source_join_key_validation",
            )

            result = build_promotions_materialized_source_join_spec_pack(
                packet_root=packet_root,
                upstream_root=upstream_root,
            )

            self.assertEqual(result.selected_promotion_key, PROMOTION_KEY)
            self.assertEqual(result.overall_spec_status, SPEC_READY_WITH_QUARANTINE)
            self.assertEqual(result.execution_allowed_flag, 1)

    def test_build_join_spec_pack_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_validation_inputs(packet_root)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(PromotionsMaterializedSourceJoinSpecPackError) as error_context:
                build_promotions_materialized_source_join_spec_pack(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_write_join_spec_pack_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / "materialized_source_join_spec_pack"
            _write_validation_inputs(
                validation_root=upstream_root / "materialized_source_join_key_validation",
            )

            artifacts = write_promotions_materialized_source_join_spec_pack(
                packet_root=packet_root,
                upstream_root=upstream_root,
                output_root=output_root,
            )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "materialized_source_join_spec_summary.csv").exists())
            self.assertTrue((output_root / "materialized_source_join_spec_guardrails.csv").exists())

    def test_build_join_spec_pack_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            validation_root = packet_root / "materialized_source_join_key_validation"
            _write_validation_inputs(packet_root)
            _append_secondary_validation_inputs(validation_root)

            result = build_promotions_materialized_source_join_spec_pack(
                packet_root=packet_root,
                promotion_key=SECOND_PROMOTION_KEY,
            )

            self.assertEqual(result.selected_promotion_key, SECOND_PROMOTION_KEY)
            self.assertEqual(result.selected_promotion_name, SECOND_PROMOTION_NAME)
            self.assertEqual(result.overall_spec_status, SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN)
            self.assertTrue(result.sources_frame["promotion_key"].astype(str).eq(SECOND_PROMOTION_KEY).all())

    def test_join_spec_pack_guardrails_keep_production_and_stage12_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_validation_inputs(packet_root)

            result = build_promotions_materialized_source_join_spec_pack(packet_root=packet_root)
            guardrails_lookup = result.guardrails_frame.set_index("guardrail_name")
            checklist_row = result.execution_checklist_frame.loc[
                result.execution_checklist_frame["checklist_step"].astype(str)
                == "Confirm no production/Stage 12 mutation."
            ].iloc[0]

            self.assertEqual(
                str(guardrails_lookup.loc["NO_PRODUCTION_ORDER_MUTATION", "guardrail_status"]),
                "REQUIRED",
            )
            self.assertEqual(
                str(guardrails_lookup.loc["NO_STAGE12_MUTATION", "guardrail_status"]),
                "REQUIRED",
            )
            self.assertEqual(int(guardrails_lookup.loc["NO_PRODUCTION_ORDER_MUTATION", "enforced_flag"]), 1)
            self.assertEqual(int(guardrails_lookup.loc["NO_STAGE12_MUTATION", "enforced_flag"]), 1)
            self.assertEqual(str(checklist_row["check_status"]), "CONFIRMED")
            self.assertIn("Stage 12 fields remain unchanged", str(checklist_row["notes"]))


if __name__ == "__main__":
    unittest.main()