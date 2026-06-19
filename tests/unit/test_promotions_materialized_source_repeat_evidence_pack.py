from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_repeat_evidence_pack as module  # noqa: E402


PROMOTION_KEY = "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1"
OTHER_PROMOTION_KEY = "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX"


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _candidate_rows() -> list[dict[str, object]]:
    return [
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "source_row_id": 1,
            "sku_number": "1001",
            "sku_description": "Strong Conversion One",
            "overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
            "rule_family_candidate": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
            "review_signal_score": 12.0,
            "review_signal_label": "HIGH_EVIDENCE",
            "actual_units": 8.0,
            "expected_promo_demand": 1.0,
            "absolute_error_units": 7.0,
            "actual_gross_profit": 28.0,
            "capital_left_value": 3.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "calibration_candidate_tier": "CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST",
            "calibration_priority_score": 26.0,
            "repeat_evidence_required_flag": 1,
            "calibration_candidate_status": "CANDIDATE",
            "row_recommendation": "Carry into repeat-evidence pack next.",
            "calibration_notes": "ok",
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "source_row_id": 2,
            "sku_number": "1002",
            "sku_description": "No Prior One",
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "rule_family_candidate": "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
            "review_signal_score": 9.0,
            "review_signal_label": "HIGH_EVIDENCE",
            "actual_units": 6.0,
            "expected_promo_demand": 1.0,
            "absolute_error_units": 5.0,
            "actual_gross_profit": 18.0,
            "capital_left_value": 0.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "calibration_candidate_tier": "CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE",
            "calibration_priority_score": 21.0,
            "repeat_evidence_required_flag": 1,
            "calibration_candidate_status": "CANDIDATE",
            "row_recommendation": "Carry into repeat-evidence pack next.",
            "calibration_notes": "ok",
        },
    ]


def _candidate_by_rule_family(review_row_count_total: int = 108) -> list[dict[str, object]]:
    return [
        {
            "rule_family_candidate": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
            "review_row_count": 45,
            "candidate_row_count": 30,
            "tier_1_count": 20,
            "tier_2_count": 5,
            "tier_3_count": 5,
            "deferred_count": 15,
            "rejected_count": 0,
            "row_share_pct": 41.67,
            "mean_review_signal_score": 11.0,
            "mean_actual_gross_profit": 22.0,
            "mean_capital_left_value": 2.0,
            "sample_skus": "1001",
            "family_priority_score": 26.0,
            "family_readiness_tier": "CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST",
            "repeat_evidence_required_flag": 1,
            "quality_notes": "ok",
        },
        {
            "rule_family_candidate": "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
            "review_row_count": review_row_count_total - 45,
            "candidate_row_count": 53,
            "tier_1_count": 33,
            "tier_2_count": 10,
            "tier_3_count": 10,
            "deferred_count": 10,
            "rejected_count": 0,
            "row_share_pct": 58.33,
            "mean_review_signal_score": 10.0,
            "mean_actual_gross_profit": 18.0,
            "mean_capital_left_value": 0.0,
            "sample_skus": "1002",
            "family_priority_score": 21.0,
            "family_readiness_tier": "CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE",
            "repeat_evidence_required_flag": 1,
            "quality_notes": "ok",
        },
    ]


def _candidate_priority_rows() -> list[dict[str, object]]:
    return [
        {
            "queue_rank": 1,
            "rule_family_candidate": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
            "overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
            "sku_number": "1001",
            "sku_description": "Strong Conversion One",
            "calibration_candidate_tier": "CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST",
            "review_signal_score": 12.0,
            "actual_gross_profit": 28.0,
            "capital_left_value": 3.0,
            "calibration_priority_score": 26.0,
        },
        {
            "queue_rank": 2,
            "rule_family_candidate": "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "sku_number": "1002",
            "sku_description": "No Prior One",
            "calibration_candidate_tier": "CALIBRATION_CANDIDATE_TIER_2_NEEDS_REPEAT_EVIDENCE",
            "review_signal_score": 9.0,
            "actual_gross_profit": 18.0,
            "capital_left_value": 0.0,
            "calibration_priority_score": 21.0,
        },
    ]


def _candidate_validation_rows(
    *,
    production_guardrail_status: str = "PASS",
    stage12_guardrail_status: str = "PASS",
    no_order_status: str = "PASS",
) -> list[dict[str, object]]:
    return [
        {
            "check_name": "NO_ORDER_RECOMMENDATION_FIELDS_GENERATED",
            "check_status": no_order_status,
            "check_flag": int(no_order_status == "PASS"),
            "details": "ok",
        },
        {
            "check_name": "PRODUCTION_GUARDRAIL_PASS",
            "check_status": production_guardrail_status,
            "check_flag": int(production_guardrail_status == "PASS"),
            "details": "ok",
        },
        {
            "check_name": "STAGE12_GUARDRAIL_PASS",
            "check_status": stage12_guardrail_status,
            "check_flag": int(stage12_guardrail_status == "PASS"),
            "details": "ok",
        },
    ]


def _packet_index_rows(include_other: bool = True) -> list[dict[str, object]]:
    rows = [
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "packet_output_path": "tmp/last5_promotions_diagnostic_packets/source_materialized_promotions/promotion_772-2026-05-21-2026-06-03-allocation-report-wk47-48-winter-part-1",
            "row_count": 3598,
            "sku_count": 3597,
            "expected_demand": 253.0,
            "gross_profit_represented": 7886.11,
            "capital_left_represented": 0.0,
            "packet_completeness_score": 8,
            "downstream_full_diagnostic_chain_available_flag": 0,
            "downstream_full_packet_reason": "Source-row materialization is available, but the downstream governed review and action-layer chain requires validated review-root artifacts that were not rebuilt in this runner.",
        }
    ]
    if include_other:
        rows.append(
            {
                "promotion_key": OTHER_PROMOTION_KEY,
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                "promotion_start_date": "2026-05-07",
                "promotion_end_date": "2026-05-20",
                "packet_output_path": "tmp/last5_promotions_diagnostic_packets/source_materialized_promotions/promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box",
                "row_count": 3275,
                "sku_count": 3274,
                "expected_demand": 221.53,
                "gross_profit_represented": 7135.11,
                "capital_left_represented": 0.0,
                "packet_completeness_score": 8,
                "downstream_full_diagnostic_chain_available_flag": 0,
                "downstream_full_packet_reason": "Source-row materialization is available, but the downstream governed review and action-layer chain requires validated review-root artifacts that were not rebuilt in this runner.",
            }
        )
    return rows


def _source_summary_row(promotion_key: str, promotion_name: str, start_date: str, end_date: str, row_count: int, sku_count: int) -> list[dict[str, object]]:
    return [
        {
            "promotion_key": promotion_key,
            "promotion_name": promotion_name,
            "promotion_start_date": start_date,
            "promotion_end_date": end_date,
            "row_count": row_count,
            "sku_count": sku_count,
            "actual_units_proxy_total": 0.0,
            "expected_demand_proxy_total": 100.0,
            "gross_profit_proxy_total": 1000.0,
            "capital_left_proxy_total": 0.0,
            "packet_completeness_score": 8,
        }
    ]


def _write_inputs(
    packet_root: Path,
    *,
    include_other_promotion: bool = True,
    production_guardrail_status: str = "PASS",
    stage12_guardrail_status: str = "PASS",
    no_order_status: str = "PASS",
) -> None:
    candidate_root = packet_root / module.CALIBRATION_CANDIDATE_PACK_FOLDER_NAME
    _write_csv(candidate_root / module.CANDIDATE_PACK_ROWS_FILE_NAME, _candidate_rows())
    _write_csv(
        candidate_root / module.CANDIDATE_PACK_BY_RULE_FAMILY_FILE_NAME,
        _candidate_by_rule_family(),
    )
    _write_csv(
        candidate_root / module.CANDIDATE_PACK_PRIORITY_QUEUE_FILE_NAME,
        _candidate_priority_rows(),
    )
    _write_csv(
        candidate_root / module.CANDIDATE_PACK_VALIDATION_FILE_NAME,
        _candidate_validation_rows(
            production_guardrail_status=production_guardrail_status,
            stage12_guardrail_status=stage12_guardrail_status,
            no_order_status=no_order_status,
        ),
    )
    _write_csv(packet_root / module.PACKET_INDEX_FILE_NAME, _packet_index_rows(include_other=include_other_promotion))

    selected_dir = (
        packet_root
        / module.SOURCE_MATERIALIZED_PROMOTIONS_FOLDER_NAME
        / "promotion_772-2026-05-21-2026-06-03-allocation-report-wk47-48-winter-part-1"
    )
    _write_csv(
        selected_dir / module.SOURCE_SUMMARY_FILE_NAME,
        _source_summary_row(
            PROMOTION_KEY,
            "Allocation Report - WK47&48 WINTER PART 1",
            "2026-05-21",
            "2026-06-03",
            3598,
            3597,
        ),
    )
    _write_csv(selected_dir / module.SOURCE_ROWS_FILE_NAME, [{"sku_number": "1001"}])

    if include_other_promotion:
        other_dir = (
            packet_root
            / module.SOURCE_MATERIALIZED_PROMOTIONS_FOLDER_NAME
            / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"
        )
        _write_csv(
            other_dir / module.SOURCE_SUMMARY_FILE_NAME,
            _source_summary_row(
                OTHER_PROMOTION_KEY,
                "Allocation Report - WK45&46 BABY & YOU BOX",
                "2026-05-07",
                "2026-05-20",
                3275,
                3274,
            ),
        )
        _write_csv(other_dir / module.SOURCE_ROWS_FILE_NAME, [{"sku_number": "2001"}])


class PromotionsMaterializedSourceRepeatEvidencePackTests(unittest.TestCase):
    def test_repeat_evidence_unavailable_when_other_promotions_lack_rebuild_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_repeat_evidence_pack(
                packet_root=packet_root
            )

            self.assertEqual(
                result.repeat_evidence_pack_status,
                module.REPEAT_EVIDENCE_PACK_REQUIRES_MORE_RECONSTRUCTION,
            )
            self.assertEqual(result.strong_repeat_evidence_count, 0)
            self.assertEqual(result.unavailable_needs_rebuild_count, 2)
            self.assertEqual(result.missing_promotion_evidence_count, 1)
            self.assertEqual(result.more_promotion_reconstruction_should_run_next, 1)

    def test_single_promotion_only_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, include_other_promotion=False)

            result = module.build_promotions_materialized_source_repeat_evidence_pack(
                packet_root=packet_root
            )

            self.assertEqual(result.repeat_evidence_pack_status, module.REPEAT_EVIDENCE_PACK_READY)
            self.assertEqual(result.single_promotion_only_count, 2)
            self.assertEqual(result.unavailable_needs_rebuild_count, 0)

    def test_no_quarantine_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_repeat_evidence_pack(
                packet_root=packet_root
            )
            validation_lookup = result.validation_frame.set_index("check_name")

            self.assertEqual(
                validation_lookup.loc["NO_QUARANTINE_ROWS_INCLUDED", "check_status"],
                "PASS",
            )

    def test_missing_evidence_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            artifacts = module.write_promotions_materialized_source_repeat_evidence_pack(
                packet_root=packet_root
            )
            frame = pd.read_csv(artifacts.missing_promotion_evidence_csv_path)

            self.assertTrue(Path(artifacts.missing_promotion_evidence_csv_path).exists())
            self.assertEqual(len(frame.index), 1)
            self.assertEqual(
                str(frame.iloc[0]["candidate_recommendation"]),
                module.RECONSTRUCT_MORE_PROMOTIONS_FIRST,
            )

    def test_validation_confirms_no_recalibration_simulation_training(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_repeat_evidence_pack(
                packet_root=packet_root
            )
            validation_lookup = result.validation_frame.set_index("check_name")

            self.assertEqual(
                validation_lookup.loc["NO_RECALIBRATION_EXECUTED", "check_status"],
                "PASS",
            )
            self.assertEqual(
                validation_lookup.loc["NO_SHADOW_SIMULATION_EXECUTED", "check_status"],
                "PASS",
            )
            self.assertEqual(
                validation_lookup.loc["NO_TRAINING_EXECUTED", "check_status"],
                "PASS",
            )


if __name__ == "__main__":
    unittest.main()