from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.commercial_delta import (  # noqa: E402
    CommercialDeltaSummary,
    DELTA_CLASS_BLOCKED_BY_DEFECT,
    DELTA_CLASS_FIRST_OBSERVATION,
    DELTA_CLASS_HIGH_CHANGE,
    DELTA_CLASS_LOW_CHANGE,
    DELTA_CLASS_MATERIAL_CHANGE,
    DELTA_CLASS_NO_CHANGE,
    _validate_delta_consistency,
    build_commercial_delta_intelligence,
)


def _build_frame(row_count: int, *, recommendation: str = "ORDER") -> pd.DataFrame:
    rows = []
    for idx in range(row_count):
        rows.append(
            {
                "store_number": (idx % 5) + 1,
                "promotion_header_key": f"promo-{idx % 3}",
                "promotion_name": f"Promo {idx % 3}",
                "promotion_start_date": "2024-09-01",
                "promotion_end_date": "2024-09-07",
                "sku_number": 1000 + idx,
                "suggested_order_units": 10,
                "demand_evidence_class": "healthy_nonzero_demand",
                "publish_eligibility_reason": "publishable",
                "review_reason": "",
                "decision_recommendation": recommendation,
            }
        )
    return pd.DataFrame(rows)


def _write_prior_cycle(
    manifests_root: Path,
    *,
    run_id: str,
    as_of_date: str,
    stage12_pos_upload_row_count: int,
    frame: pd.DataFrame,
) -> None:
    run_root = manifests_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    master_csv_path = run_root / "store_prediction_master.csv"
    frame.to_csv(master_csv_path, index=False, encoding="utf-8")

    store_manifest_path = run_root / "store_prediction_download_manifest.json"
    store_manifest_path.write_text(
        json.dumps(
            {
                "master_csv_path": str(master_csv_path),
            }
        ),
        encoding="utf-8",
    )

    summary_path = run_root / "commercial_run_outcome_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "as_of_date": as_of_date,
                "commercial_outcome_class": "COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
                "store_prediction_download_manifest_path": str(store_manifest_path),
                "stage12_pos_upload_row_count": stage12_pos_upload_row_count,
                "stage12_publish_status": "PASS",
            }
        ),
        encoding="utf-8",
    )


class CommercialDeltaTests(unittest.TestCase):
    def test_no_prior_cycle_emits_first_observation_with_null_prior_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifests_root = Path(temp_dir) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)

            current_csv = Path(temp_dir) / "current.csv"
            _build_frame(5).to_csv(current_csv, index=False, encoding="utf-8")

            result = build_commercial_delta_intelligence(
                run_id="current",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_publishable_row_count=5,
                current_stage12_publish_status="PASS",
                current_commercial_failure_flag=False,
            )

            self.assertEqual(result.summary.delta_class, DELTA_CLASS_FIRST_OBSERVATION)
            self.assertFalse(result.summary.comparable_prior_cycle_found_flag)
            self.assertIsNone(result.summary.prior_publishable_row_count)
            self.assertIsNone(result.summary.publishable_row_count_delta)

    def test_exact_duplicate_emits_no_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifests_root = Path(temp_dir) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)

            prior_frame = _build_frame(6)
            _write_prior_cycle(
                manifests_root,
                run_id="prior",
                as_of_date="2024-09-01",
                stage12_pos_upload_row_count=6,
                frame=prior_frame,
            )

            current_csv = Path(temp_dir) / "current.csv"
            prior_frame.to_csv(current_csv, index=False, encoding="utf-8")

            result = build_commercial_delta_intelligence(
                run_id="current",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_publishable_row_count=6,
                current_stage12_publish_status="PASS",
                current_commercial_failure_flag=False,
            )

            self.assertEqual(result.summary.delta_class, DELTA_CLASS_NO_CHANGE)
            self.assertFalse(result.summary.materially_changed_flag)

    def test_small_change_emits_low_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifests_root = Path(temp_dir) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)

            _write_prior_cycle(
                manifests_root,
                run_id="prior",
                as_of_date="2024-09-01",
                stage12_pos_upload_row_count=20,
                frame=_build_frame(20),
            )

            current_frame = _build_frame(22)
            current_csv = Path(temp_dir) / "current.csv"
            current_frame.to_csv(current_csv, index=False, encoding="utf-8")

            result = build_commercial_delta_intelligence(
                run_id="current",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_publishable_row_count=22,
                current_stage12_publish_status="PASS",
                current_commercial_failure_flag=False,
            )

            self.assertEqual(result.summary.delta_class, DELTA_CLASS_LOW_CHANGE)

    def test_meaningful_shift_emits_material_or_high(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifests_root = Path(temp_dir) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)

            _write_prior_cycle(
                manifests_root,
                run_id="prior",
                as_of_date="2024-09-01",
                stage12_pos_upload_row_count=10,
                frame=_build_frame(10),
            )

            current_frame = _build_frame(45)
            current_csv = Path(temp_dir) / "current.csv"
            current_frame.to_csv(current_csv, index=False, encoding="utf-8")

            result = build_commercial_delta_intelligence(
                run_id="current",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_publishable_row_count=45,
                current_stage12_publish_status="PASS",
                current_commercial_failure_flag=False,
            )

            self.assertIn(
                result.summary.delta_class,
                {DELTA_CLASS_MATERIAL_CHANGE, DELTA_CLASS_HIGH_CHANGE},
            )

    def test_recommendation_changes_register_meaningful_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifests_root = Path(temp_dir) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)

            prior_frame = _build_frame(25, recommendation="ORDER")
            _write_prior_cycle(
                manifests_root,
                run_id="prior",
                as_of_date="2024-09-01",
                stage12_pos_upload_row_count=25,
                frame=prior_frame,
            )

            current_frame = _build_frame(25, recommendation="PUBLISH")
            current_csv = Path(temp_dir) / "current.csv"
            current_frame.to_csv(current_csv, index=False, encoding="utf-8")

            result = build_commercial_delta_intelligence(
                run_id="current",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_publishable_row_count=25,
                current_stage12_publish_status="PASS",
                current_commercial_failure_flag=False,
            )

            self.assertTrue((result.summary.changed_recommendation_row_count or 0) > 0)
            self.assertIn(
                result.summary.delta_class,
                {DELTA_CLASS_MATERIAL_CHANGE, DELTA_CLASS_HIGH_CHANGE, DELTA_CLASS_LOW_CHANGE},
            )

    def test_defect_blocked_emits_blocked_by_defect(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifests_root = Path(temp_dir) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)

            current_csv = Path(temp_dir) / "current.csv"
            _build_frame(6).to_csv(current_csv, index=False, encoding="utf-8")

            result = build_commercial_delta_intelligence(
                run_id="current",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_publishable_row_count=0,
                current_stage12_publish_status="FAIL",
                current_commercial_failure_flag=True,
            )

            self.assertEqual(result.summary.delta_class, DELTA_CLASS_BLOCKED_BY_DEFECT)

    def test_summary_contains_required_fields_and_truthful_nulls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifests_root = Path(temp_dir) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)

            current_csv = Path(temp_dir) / "current.csv"
            _build_frame(3).to_csv(current_csv, index=False, encoding="utf-8")

            result = build_commercial_delta_intelligence(
                run_id="current",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_publishable_row_count=3,
                current_stage12_publish_status="PASS",
                current_commercial_failure_flag=False,
            )
            payload = result.summary.to_dict()

            required = {
                "delta_class",
                "delta_reason",
                "delta_message",
                "prior_cycle_run_id",
                "comparable_prior_cycle_found_flag",
                "materially_changed_flag",
                "operator_attention_recommended_flag",
                "materiality_class",
                "materiality_reason",
            }
            self.assertTrue(required.issubset(set(payload.keys())))
            self.assertIsNone(payload["prior_cycle_run_id"])
            self.assertIsNone(payload["prior_publishable_row_count"])

    def test_top_changes_contains_expected_changed_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifests_root = Path(temp_dir) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)

            prior = _build_frame(6)
            _write_prior_cycle(
                manifests_root,
                run_id="prior",
                as_of_date="2024-09-01",
                stage12_pos_upload_row_count=6,
                frame=prior,
            )

            current = prior.copy()
            current.loc[0, "decision_recommendation"] = "PUBLISH"
            current.loc[0, "suggested_order_units"] = 25
            current_csv = Path(temp_dir) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            result = build_commercial_delta_intelligence(
                run_id="current",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_publishable_row_count=6,
                current_stage12_publish_status="PASS",
                current_commercial_failure_flag=False,
            )

            self.assertFalse(result.top_changes.empty)
            self.assertIn("change_reason", result.top_changes.columns)
            self.assertTrue((result.top_changes["changed_flag"] == True).any())

    def test_store_summary_reconciles_to_current_prior_totals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifests_root = Path(temp_dir) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)

            prior = _build_frame(8)
            _write_prior_cycle(
                manifests_root,
                run_id="prior",
                as_of_date="2024-09-01",
                stage12_pos_upload_row_count=8,
                frame=prior,
            )

            current = _build_frame(10)
            current_csv = Path(temp_dir) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            result = build_commercial_delta_intelligence(
                run_id="current",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_publishable_row_count=10,
                current_stage12_publish_status="PASS",
                current_commercial_failure_flag=False,
            )

            self.assertEqual(
                int(result.store_summary["current_order_rows"].sum()),
                int(result.summary.current_order_row_count),
            )
            self.assertEqual(
                int(result.store_summary["prior_order_rows"].sum()),
                int(result.summary.prior_order_row_count or 0),
            )

    def test_contradictory_delta_facts_fail_loud(self) -> None:
        with self.assertRaises(ValueError):
            _validate_delta_consistency(
                CommercialDeltaSummary(
                    delta_class=DELTA_CLASS_NO_CHANGE,
                    delta_reason="test",
                    delta_message="test",
                    prior_cycle_run_id="prior",
                    comparable_prior_cycle_found_flag=True,
                    materially_changed_flag=False,
                    operator_attention_recommended_flag=False,
                    materiality_class="NO_MATERIAL_CHANGE",
                    materiality_reason="test",
                    current_publishable_row_count=10,
                    prior_publishable_row_count=10,
                    publishable_row_count_delta=0,
                    current_order_row_count=10,
                    prior_order_row_count=10,
                    order_row_count_delta=0,
                    current_review_row_count=0,
                    prior_review_row_count=0,
                    review_row_count_delta=0,
                    current_true_zero_row_count=0,
                    prior_true_zero_row_count=0,
                    true_zero_row_count_delta=0,
                    changed_store_count=1,
                    changed_promotion_count=0,
                    changed_store_sku_count=0,
                    newly_publishable_row_count=0,
                    no_longer_publishable_row_count=0,
                    changed_recommendation_row_count=0,
                )
            )


if __name__ == "__main__":
    unittest.main()
