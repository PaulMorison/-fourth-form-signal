from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.commercial_change_explainer import (  # noqa: E402
    ACTION_INVESTIGATE_DEFECT,
    ACTION_NO_ACTION_DUPLICATE,
    ACTION_NO_ACTION_TRUE_ZERO,
    ACTION_PUBLISH_NOW,
    ACTION_REVIEW_NOW,
    ROW_CHANGE_DEFECT_BLOCKED,
    ROW_CHANGE_NEW_PUBLICATION,
    ROW_CHANGE_UNCHANGED,
    _validate_explanation_consistency,
    build_commercial_change_explainability_artifacts,
)


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _row(
    *,
    store_number: int,
    sku_number: int,
    reco: str,
    demand: str,
    eligibility: str = "publishable",
    review_reason: str = "",
    units: int = 10,
) -> dict[str, object]:
    return {
        "store_number": store_number,
        "sku_number": sku_number,
        "promotion_start_date": "2024-09-01",
        "promotion_end_date": "2024-09-07",
        "decision_recommendation": reco,
        "demand_evidence_class": demand,
        "publish_eligibility_reason": eligibility,
        "review_reason": review_reason,
        "suggested_order_units": units,
    }


def _write_prior_run(manifests_root: Path, run_id: str, as_of_date: str, frame: pd.DataFrame) -> None:
    run_root = manifests_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    master_csv = run_root / "prior_master.csv"
    frame.to_csv(master_csv, index=False, encoding="utf-8")

    store_manifest = run_root / "store_prediction_download_manifest.json"
    store_manifest.write_text(json.dumps({"master_csv_path": str(master_csv)}), encoding="utf-8")

    summary = run_root / "commercial_run_outcome_summary.json"
    summary.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "as_of_date": as_of_date,
                "commercial_outcome_class": "COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
                "store_prediction_download_manifest_path": str(store_manifest),
                "stage12_pos_upload_row_count": int(len(frame.index)),
                "stage12_publish_status": "PASS",
            }
        ),
        encoding="utf-8",
    )


class CommercialChangeExplainerTests(unittest.TestCase):
    def test_new_publishable_row_is_publish_now(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)

            current = _frame([_row(store_number=1, sku_number=101, reco="ORDER", demand="healthy_nonzero_demand")])
            current_csv = Path(tmp) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-a",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
                current_freshness_class="FRESH_NEW_PUBLICATIONS_CREATED",
                current_delta_class="FIRST_OBSERVATION_NO_PRIOR_BASELINE",
                duplicate_registry_skip_count=0,
                prior_cycle_run_id=None,
            )

            row = artifacts.explanations.iloc[0]
            self.assertEqual(row["row_change_class"], ROW_CHANGE_NEW_PUBLICATION)
            self.assertEqual(row["operator_action_class"], ACTION_PUBLISH_NOW)

    def test_review_only_change_is_review_now(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            prior = _frame([_row(store_number=1, sku_number=101, reco="ORDER", demand="healthy_nonzero_demand")])
            _write_prior_run(manifests_root, "prior-1", "2024-09-01", prior)

            current = _frame([
                _row(
                    store_number=1,
                    sku_number=101,
                    reco="ORDER",
                    demand="healthy_nonzero_demand",
                    eligibility="review_only",
                    review_reason="requires_review",
                )
            ])
            current_csv = Path(tmp) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-b",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS",
                current_freshness_class="NO_NEW_PUBLICATIONS_REVIEW_ONLY",
                current_delta_class="LOW_COMMERCIAL_CHANGE",
                duplicate_registry_skip_count=0,
                prior_cycle_run_id="prior-1",
            )

            row = artifacts.explanations.iloc[0]
            self.assertIn(row["row_change_class"], {"RECOMMENDATION_CHANGED", "ELIGIBILITY_CHANGED"})
            self.assertEqual(row["operator_action_class"], ACTION_REVIEW_NOW)

    def test_review_only_no_publish_cycle_suppresses_publish_now_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)
            current = _frame([_row(store_number=1, sku_number=102, reco="ORDER", demand="healthy_nonzero_demand")])
            current_csv = Path(tmp) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-review-only-no-publish",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS",
                current_freshness_class="NO_NEW_PUBLICATIONS_REVIEW_ONLY",
                current_delta_class="FIRST_OBSERVATION_NO_PRIOR_BASELINE",
                duplicate_registry_skip_count=0,
                prior_cycle_run_id=None,
            )

            row = artifacts.explanations.iloc[0]
            self.assertEqual(row["operator_action_class"], ACTION_REVIEW_NOW)
            self.assertTrue(bool(row["excluded_from_publish_flag"]))
            self.assertEqual(artifacts.action_summary.action_publish_now_count, 0)
            self.assertEqual(artifacts.action_summary.action_review_now_count, 1)

    def test_true_zero_row_is_no_action_true_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)
            current = _frame([_row(store_number=1, sku_number=201, reco="MONITOR", demand="true_zero_demand", units=0)])
            current_csv = Path(tmp) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-c",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS",
                current_freshness_class="NO_NEW_PUBLICATIONS_LEGITIMATE_ZERO",
                current_delta_class="LOW_COMMERCIAL_CHANGE",
                duplicate_registry_skip_count=0,
                prior_cycle_run_id=None,
            )
            self.assertEqual(artifacts.explanations.iloc[0]["operator_action_class"], ACTION_NO_ACTION_TRUE_ZERO)

    def test_duplicate_only_row_is_no_action_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)
            current = _frame([_row(store_number=2, sku_number=301, reco="ORDER", demand="healthy_nonzero_demand")])
            current_csv = Path(tmp) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-d",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_GOVERNED_NOOP_ALREADY_PUBLISHED",
                current_freshness_class="NO_NEW_PUBLICATIONS_DUPLICATE_ONLY",
                current_delta_class="NO_COMMERCIAL_CHANGE_DETECTED",
                duplicate_registry_skip_count=1,
                prior_cycle_run_id=None,
            )
            self.assertEqual(artifacts.explanations.iloc[0]["operator_action_class"], ACTION_NO_ACTION_DUPLICATE)

    def test_defect_blocked_row_is_investigate_defect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)
            current = _frame([_row(store_number=3, sku_number=401, reco="ORDER", demand="healthy_nonzero_demand")])
            current_csv = Path(tmp) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-e",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_FAILURE_DEFECT",
                current_freshness_class="BLOCKED_BY_DEFECT",
                current_delta_class="CHANGE_BLOCKED_BY_DEFECT",
                duplicate_registry_skip_count=0,
                prior_cycle_run_id=None,
            )
            row = artifacts.explanations.iloc[0]
            self.assertEqual(row["row_change_class"], ROW_CHANGE_DEFECT_BLOCKED)
            self.assertEqual(row["operator_action_class"], ACTION_INVESTIGATE_DEFECT)

    def test_material_units_shift_increases_priority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            prior = _frame([_row(store_number=4, sku_number=501, reco="ORDER", demand="healthy_nonzero_demand", units=5)])
            _write_prior_run(manifests_root, "prior-2", "2024-09-01", prior)

            current = _frame([_row(store_number=4, sku_number=501, reco="ORDER", demand="healthy_nonzero_demand", units=55)])
            current_csv = Path(tmp) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-f",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
                current_freshness_class="FRESH_NEW_PUBLICATIONS_CREATED",
                current_delta_class="MATERIAL_COMMERCIAL_CHANGE",
                duplicate_registry_skip_count=0,
                prior_cycle_run_id="prior-2",
            )
            self.assertGreaterEqual(int(artifacts.explanations.iloc[0]["operator_priority_score"]), 70)

    def test_unchanged_row_has_unchanged_class(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            prior = _frame([_row(store_number=5, sku_number=601, reco="ORDER", demand="healthy_nonzero_demand", units=10)])
            _write_prior_run(manifests_root, "prior-3", "2024-09-01", prior)

            current_csv = Path(tmp) / "current.csv"
            prior.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-g",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
                current_freshness_class="FRESH_NEW_PUBLICATIONS_CREATED",
                current_delta_class="NO_COMMERCIAL_CHANGE_DETECTED",
                duplicate_registry_skip_count=0,
                prior_cycle_run_id="prior-3",
            )
            row = artifacts.explanations.iloc[0]
            self.assertEqual(row["row_change_class"], ROW_CHANGE_UNCHANGED)
            self.assertIn(row["operator_priority_band"], {"NONE", "LOW"})

    def test_explanations_csv_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)
            current = _frame([_row(store_number=1, sku_number=701, reco="ORDER", demand="healthy_nonzero_demand")])
            current_csv = Path(tmp) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-h",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
                current_freshness_class="FRESH_NEW_PUBLICATIONS_CREATED",
                current_delta_class="FIRST_OBSERVATION_NO_PRIOR_BASELINE",
                duplicate_registry_skip_count=0,
                prior_cycle_run_id=None,
            )

            required = {
                "store_number",
                "sku_number",
                "promotion_start_date",
                "promotion_end_date",
                "prior_decision_recommendation",
                "current_decision_recommendation",
                "row_change_class",
                "row_change_reason_code",
                "operator_action_class",
                "operator_priority_score",
                "operator_priority_band",
                "changed_fields",
            }
            self.assertTrue(required.issubset(set(artifacts.explanations.columns)))

    def test_priority_queue_sorted_and_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)
            current = _frame([
                _row(store_number=1, sku_number=801, reco="ORDER", demand="healthy_nonzero_demand", units=80),
                _row(store_number=1, sku_number=802, reco="ORDER", demand="healthy_nonzero_demand", units=10),
            ])
            current_csv = Path(tmp) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-i",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
                current_freshness_class="FRESH_NEW_PUBLICATIONS_CREATED",
                current_delta_class="MATERIAL_COMMERCIAL_CHANGE",
                duplicate_registry_skip_count=0,
                prior_cycle_run_id=None,
            )

            if not artifacts.priority_queue.empty:
                scores = list(artifacts.priority_queue["operator_priority_score"].astype(int))
                self.assertEqual(scores, sorted(scores, reverse=True))
                keys_all = set(
                    artifacts.explanations.apply(
                        lambda r: (str(r["store_number"]), str(r["sku_number"]), str(r["promotion_start_date"]), str(r["promotion_end_date"])),
                        axis=1,
                    )
                )
                keys_queue = set(
                    artifacts.priority_queue.apply(
                        lambda r: (str(r["store_number"]), str(r["sku_number"]), str(r["promotion_start_date"]), str(r["promotion_end_date"])),
                        axis=1,
                    )
                )
                self.assertTrue(keys_queue.issubset(keys_all))

    def test_action_summary_reconciles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifests_root = Path(tmp) / "manifests"
            manifests_root.mkdir(parents=True, exist_ok=True)
            current = _frame([
                _row(store_number=1, sku_number=901, reco="ORDER", demand="healthy_nonzero_demand"),
                _row(store_number=1, sku_number=902, reco="MONITOR", demand="true_zero_demand", units=0),
            ])
            current_csv = Path(tmp) / "current.csv"
            current.to_csv(current_csv, index=False, encoding="utf-8")

            artifacts = build_commercial_change_explainability_artifacts(
                run_id="run-j",
                as_of_date="2024-09-01",
                manifests_root=manifests_root,
                current_store_prediction_csv_path=str(current_csv),
                current_commercial_outcome_class="COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
                current_freshness_class="FRESH_NEW_PUBLICATIONS_CREATED",
                current_delta_class="LOW_COMMERCIAL_CHANGE",
                duplicate_registry_skip_count=0,
                prior_cycle_run_id=None,
            )

            summary = artifacts.action_summary
            self.assertEqual(
                summary.action_publish_now_count,
                int((artifacts.explanations["operator_action_class"] == "ACTION_PUBLISH_NOW").sum()),
            )
            self.assertEqual(
                summary.action_no_action_true_zero_count,
                int((artifacts.explanations["operator_action_class"] == "ACTION_NO_ACTION_TRUE_ZERO").sum()),
            )

    def test_contradictory_states_fail_loud(self) -> None:
        bogus = pd.DataFrame(
            [
                {
                    "store_number": "1",
                    "sku_number": "100",
                    "promotion_start_date": "2024-09-01",
                    "promotion_end_date": "2024-09-07",
                    "row_change_class": "UNCHANGED_ROW",
                    "changed_fields": "decision_recommendation",
                    "operator_action_class": "ACTION_PUBLISH_NOW",
                    "excluded_from_publish_flag": True,
                    "duplicate_blocked_flag": False,
                    "current_demand_evidence_class": "healthy_nonzero_demand",
                    "operator_priority_band": "HIGH",
                }
            ]
        )
        with self.assertRaises(ValueError):
            _validate_explanation_consistency(
                explanations=bogus,
                priority_queue=bogus,
                action_summary=type(
                    "S",
                    (),
                    {
                        "action_publish_now_count": 0,
                        "action_review_now_count": 0,
                        "action_monitor_count": 0,
                        "action_no_action_duplicate_count": 0,
                        "action_no_action_true_zero_count": 0,
                        "action_investigate_defect_count": 0,
                    },
                )(),
            )


if __name__ == "__main__":
    unittest.main()
