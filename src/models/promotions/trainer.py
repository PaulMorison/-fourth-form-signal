from __future__ import annotations

"""Reusable promotions model trainer.

Canon ownership:
- Fits one reusable promotions model family using time-aware splits, leakage-safe
  features, persisted metrics, explicit inference schema, and stable artifacts.
- Trains a regularized baseline regressor, a gradient-boosted regressor for the
  primary units target, and binary classifiers for allocation and stock risk.
- Does not own extraction, target semantics, or scoring/reporting outputs.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Literal, Sequence

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    brier_score_loss,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from models.promotions.allocation_calibration import compute_allocation_aware_cap_units
from models.promotions.model_bundle import (
    PromotionInferenceSchema,
    PromotionTrainingManifest,
    read_json,
    write_json,
)
from models.promotions.order_policy_adjustments import (
    ORDER_POLICY_MAJOR_BUCKET_COLUMNS,
    ORDER_POLICY_RULE_NAMES,
    ORDER_POLICY_RULE_STRENGTH_BY_NAME,
    build_order_policy_adjustments,
    build_order_policy_major_bucket_frame,
    build_order_policy_rule_trigger_frame,
)
from models.promotions.preprocessing import prepare_model_input_frame
from models.promotions.time_split import PromotionTimeSplitter
from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.datasets.model_input_export import (
    ModelInputAuditPaths,
    write_model_input_audit_artifacts,
)
from state.promotions.feature_engineering.demand.ft_order_decision_diagnostics import (
    BASE_DEMAND_GROWTH_BUCKET_ORDER,
    CONFIDENCE_BUCKET_ORDER,
    SAME_DISCOUNT_HISTORY_BUCKET_ORDER,
    WINDOW_CONFLICT_BUCKET_ORDER,
    build_live_order_decision_diagnostics,
)
from state.promotions.feature_engineering.targets.ft_target_historical_allocation import (
    HISTORICAL_ALLOCATION_SOURCE_COLUMNS,
    HISTORICAL_ALLOCATION_TARGET_COLUMNS,
    HISTORICAL_REALISED_PROMO_UNITS_SOURCE_COLUMNS,
    HISTORICAL_UNIT_COST_SOURCE_COLUMNS,
    apply_ft_target_historical_allocation,
)
from state.promotions.inspection.feature_environment_audit import (
    FeatureEnvironmentAuditPaths,
    write_feature_environment_audit_artifacts,
)


LOGGER = logging.getLogger(__name__)


POLICY_EFFECTIVENESS_BUCKET_ORDER: tuple[str, ...] = (
    "weak_same_discount_and_uplift",
    "weak_elasticity",
    "falling_base_launch_conflict",
    "stock_gap_high",
    "sparse_history_multi_driver",
)

_POLICY_BUCKET_BAD_RELATIVE_THRESHOLD = 1.25
_POLICY_BUCKET_BAD_MIN_ROWS = 3
_POLICY_RESIDUAL_ROW_LIMIT = 20
_POLICY_REPLAY_HISTORICAL_ALLOCATION_COLUMNS: tuple[str, ...] = (
    "pl_allocation_qty",
    "pl_allocated",
    "store_adjusted_qty",
    "total_units_commited",
)
_POLICY_REPLAY_REALISED_PROMO_UNITS_COLUMNS: tuple[str, ...] = (
    "actual_units_sold_promo",
    "target_actual_units_sold",
    "actual_units_sold",
)
_POLICY_REPLAY_UNIT_COST_COLUMNS: tuple[str, ...] = (
    "effective_cost_per_unit",
    "promo_effective_cost",
    "promo_cost_price",
    "last_received_cost",
)
_POLICY_REPLAY_EXCLUSION_REASON_ELIGIBLE = "eligible"
_POLICY_REPLAY_EXCLUSION_REASON_MISSING_HISTORICAL_ALLOCATION = "missing_historical_allocation_units"
_POLICY_REPLAY_EXCLUSION_REASON_MISSING_REALISED_PROMO_UNITS = "missing_realised_promo_units"
_POLICY_REPLAY_EXCLUSION_REASON_MISSING_EFFECTIVE_COST = "missing_effective_cost_per_unit"
_POLICY_REPLAY_EXCLUSION_REASON_MULTIPLE_MISSING_INPUTS = "multiple_missing_replay_inputs"
_POLICY_RULE_CONTRIBUTION_NOTE = "Rule contribution totals are overlap-inclusive and therefore non-additive across rules."
_POLICY_RULE_REFINEMENT_MIN_TRIGGERED_ROW_COUNT = 5
_POLICY_RULE_REFINEMENT_MIN_SOLO_TRIGGERED_ROW_COUNT = 3
_POLICY_RULE_REFINEMENT_MIN_SHARE_OF_TOTAL_CAPITAL_REMOVED = 0.15
_POLICY_RULE_REFINEMENT_MIN_RESIDUAL_TO_OVERALL_RATIO = 1.10
_POLICY_RULE_REFINEMENT_MIN_SOLO_CAPITAL_SHARE = 0.25
_POLICY_RULE_REFINEMENT_MAX_STRONGER_RULE_OVERLAP_SHARE = 0.60
_WEAK_SLICE_REPAIR_RESIDUAL_ROW_LIMIT = 20
_WEAK_SLICE_PRIMARY_BLOCKER_PRIORITY: tuple[str, ...] = (
    "insufficient_comparable_rows_per_slice",
    "historical_target_exclusions_not_acceptable",
    "coverage_below_threshold",
    "candidate_did_not_outperform_on_enough_slices",
    "candidate_did_not_improve_on_enough_slices",
    "candidate_median_improvement_trivial",
    "candidate_improvement_not_stable",
    "missing_governed_exclusion_attribution",
)
_WEAK_SLICE_REPAIR_FAMILY_BY_BLOCKER: dict[str, str] = {
    "insufficient_comparable_rows_per_slice": "row_count_repairs",
    "historical_target_exclusions_not_acceptable": "exclusion_rate_repairs",
    "coverage_below_threshold": "exclusion_rate_repairs",
    "candidate_did_not_outperform_on_enough_slices": "evidence_quality_repairs",
    "candidate_did_not_improve_on_enough_slices": "evidence_quality_repairs",
    "candidate_median_improvement_trivial": "evidence_quality_repairs",
    "candidate_improvement_not_stable": "evidence_quality_repairs",
    "missing_governed_exclusion_attribution": "source_chain_governance_repairs",
}
_TARGET_CONTRACT_DIVERGENCE_DRIVER_NO_MATERIAL = "no_material_divergence"
_TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS = "stock_basis_proxy_mismatch"
_TARGET_CONTRACT_DIVERGENCE_DRIVER_REALISED_PROMO = "realised_promo_units_mismatch"
_TARGET_CONTRACT_DIVERGENCE_DRIVER_COST = "cost_basis_mismatch"
_TARGET_CONTRACT_DIVERGENCE_DRIVER_DEMAND_REFERENCE = "demand_reference_mismatch"
_TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_HISTORICAL = "missing_historical_allocation_evidence"
_TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_REALISED = "missing_realised_promo_evidence"
_TARGET_CONTRACT_DIVERGENCE_DRIVER_ORDER: tuple[str, ...] = (
    _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS,
    _TARGET_CONTRACT_DIVERGENCE_DRIVER_REALISED_PROMO,
    _TARGET_CONTRACT_DIVERGENCE_DRIVER_COST,
    _TARGET_CONTRACT_DIVERGENCE_DRIVER_DEMAND_REFERENCE,
    _TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_HISTORICAL,
    _TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_REALISED,
    _TARGET_CONTRACT_DIVERGENCE_DRIVER_NO_MATERIAL,
)
_TARGET_CONTRACT_RESIDUAL_ROW_LIMIT = 20
_TARGET_CONTRACT_NEXT_CANDIDATE_MIN_ROW_COUNT = 5
_TARGET_CONTRACT_NEXT_CANDIDATE_MIN_CAPITAL_GAP_SHARE = 0.35
_TARGET_CONTRACT_NEXT_CANDIDATE_DIFFUSE_RELATIVE_SHARE = 0.85
_HISTORICAL_ALLOCATION_CANDIDATE_CORE_TARGET_COLUMNS: tuple[str, ...] = (
    "target_historical_allocation_units",
    "target_historical_replay_excess_units",
    "target_historical_replay_excess_capital",
    "target_historical_overallocation_flag",
)
_HISTORICAL_ALLOCATION_CANDIDATE_REQUIRED_COLUMNS: tuple[str, ...] = (
    *_HISTORICAL_ALLOCATION_CANDIDATE_CORE_TARGET_COLUMNS,
    "target_historical_allocation_target_valid_flag",
    "target_historical_allocation_exclusion_reason",
)
_TARGET_MODE_RESIDUAL_ROW_LIMIT = 20
_TARGET_MODE_PROMOTION_GATE_MIN_COVERAGE_RATE = 0.95
_TARGET_MODE_PROMOTION_GATE_MAX_EXCLUSION_RATE = 0.05
_TARGET_MODE_STABILITY_MIN_SLICE_COUNT = 3
_TARGET_MODE_STABILITY_MIN_COMPARABLE_ROWS_PER_SLICE = 100
_TARGET_MODE_STABILITY_MIN_POSITIVE_IMPROVEMENT_SHARE = 0.80
_TARGET_MODE_STABILITY_MAX_EXCLUSION_RATE = 0.05
_TARGET_MODE_STABILITY_MIN_STOCK_BASIS_DOMINANCE_SHARE = 0.67
_TARGET_MODE_STABILITY_MAX_RELATIVE_IMPROVEMENT_CV = 1.0
_TARGET_MODE_STABILITY_MIN_MEDIAN_RELATIVE_IMPROVEMENT = 0.01
_TARGET_MODE_MULTI_SLICE_RESIDUAL_ROW_LIMIT = 30
_TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE = "stock_basis_proxy_current_contract"
_TARGET_CONTRACT_DESIGN_CANDIDATE_ORDER: tuple[str, ...] = (
    _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE,
    "historical_allocated_units",
    "realised_promo_units",
    "historical_excess_units",
    "historical_excess_capital",
    "capped_historical_excess_units",
    "sell_through_aligned_allocation_error",
    "cost_weighted_allocation_error",
)
_TARGET_CONTRACT_DESIGN_PROPOSAL_PRIORITY: dict[str, int] = {
    "sell_through_aligned_allocation_error": 0,
    "historical_excess_units": 1,
    "cost_weighted_allocation_error": 2,
    "historical_excess_capital": 3,
    "capped_historical_excess_units": 4,
    "historical_allocated_units": 5,
    "realised_promo_units": 6,
    _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE: 99,
}
_TARGET_CONTRACT_DESIGN_MIN_SLICE_COUNT = 3
_TARGET_CONTRACT_DESIGN_MIN_COMPARABLE_ROWS_PER_SLICE = 100
_TARGET_CONTRACT_DESIGN_MIN_COVERAGE_RATE = 0.95
_TARGET_CONTRACT_DESIGN_MAX_EXCLUSION_RATE = 0.05
_TARGET_CONTRACT_DESIGN_MIN_POSITIVE_IMPROVEMENT_SHARE = 0.80
_TARGET_CONTRACT_DESIGN_MIN_CLEAN_BOUNDARY_SHARE = 0.80
_TARGET_CONTRACT_DESIGN_MAX_RELATIVE_IMPROVEMENT_CV = 1.0
_TARGET_CONTRACT_DESIGN_RESIDUAL_ROW_LIMIT = 30
_TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE = "sell_through_aligned_allocation_error"
_TARGET_DESIGN_REPEATED_MIN_SLICE_COUNT = 5
_TARGET_DESIGN_REPEATED_MIN_AGGREGATE_COMPARABLE_ROWS = 1000
_TARGET_DESIGN_REPEATED_MIN_COMPARABLE_ROWS_PER_SLICE = 100
_TARGET_DESIGN_REPEATED_MIN_COVERAGE_RATE = 0.95
_TARGET_DESIGN_REPEATED_MAX_EXCLUSION_RATE = 0.05
_TARGET_DESIGN_REPEATED_MIN_POSITIVE_IMPROVEMENT_SHARE = 0.80
_TARGET_DESIGN_REPEATED_MIN_MEDIAN_RELATIVE_IMPROVEMENT = 0.01
_TARGET_DESIGN_REPEATED_MAX_RELATIVE_IMPROVEMENT_CV = 1.0
_TARGET_DESIGN_REPEATED_MIN_STOCK_BASIS_DOMINANCE_SHARE = 0.67
_TARGET_DESIGN_REPEATED_MIN_BEST_CANDIDATE_SLICE_SHARE = 0.80
_TARGET_DESIGN_COMPLETED_SLICE_DISCOVERY_MIN_ROW_COUNT = 100
_TARGET_DESIGN_REPEATED_RESIDUAL_ROW_LIMIT = 30
_TARGET_CONTRACT_THREE_WAY_HISTORICAL_CANDIDATE = "historical_excess_units"
_TARGET_CONTRACT_THREE_WAY_RESIDUAL_ROW_LIMIT = 30
_PROMOTION_READINESS_DIRECT_BLOCKER_WEIGHT = 100.0
_PROMOTION_READINESS_INHERITED_BLOCKER_WEIGHT = 20.0
_PROMOTION_READINESS_BLOCKER_SCOPE_BONUS = 10.0
_PROMOTION_READINESS_CURRENT_BEST_BLOCKER_BONUS = 5.0
_PROMOTION_READINESS_RESIDUAL_ROW_LIMIT = 20
_PROMOTION_READINESS_BLOCKER_PRIORITY: dict[str, int] = {
    "candidate_did_not_improve_on_enough_slices": 0,
    "insufficient_comparable_rows_per_slice": 1,
    "insufficient_aggregate_comparable_rows": 2,
    "insufficient_completed_slice_count": 3,
    "insufficient_slice_count": 4,
    "coverage_below_threshold": 5,
    "exclusion_rate_above_threshold": 6,
    "candidate_median_improvement_trivial": 7,
    "candidate_improvement_not_stable": 8,
    "stock_basis_proxy_mismatch_not_persistent": 9,
    "design_candidate_not_consistently_best": 10,
    "candidate_boundary_not_cleaner_on_enough_slices": 11,
    "candidate_still_depends_on_stock_basis_proxy": 12,
    "best_candidate_tied_with_peer": 13,
    "current_live_contract_still_best_under_evidence": 14,
}
PromotionTrainerTargetMode = Literal[
    "current_trainer_contract",
    "historical_allocation_candidate",
    "dual_contract_diagnostics",
]
PROMOTION_TRAINER_TARGET_MODE_CHOICES: tuple[PromotionTrainerTargetMode, ...] = (
    "current_trainer_contract",
    "historical_allocation_candidate",
    "dual_contract_diagnostics",
)
DEFAULT_PROMOTION_TRAINER_TARGET_MODE: PromotionTrainerTargetMode = "current_trainer_contract"
_PROMOTION_TRAINER_TARGET_MODES: dict[str, PromotionTrainerTargetMode] = {
    mode: mode for mode in PROMOTION_TRAINER_TARGET_MODE_CHOICES
}


def _resolve_promotion_trainer_target_mode(
    target_mode: PromotionTrainerTargetMode | str | None,
) -> PromotionTrainerTargetMode:
    raw_mode = DEFAULT_PROMOTION_TRAINER_TARGET_MODE if target_mode is None else str(target_mode)
    try:
        return _PROMOTION_TRAINER_TARGET_MODES[raw_mode]
    except KeyError as exc:
        expected = ", ".join(_PROMOTION_TRAINER_TARGET_MODES)
        raise ValueError(f"Unsupported promotions trainer target_mode {raw_mode!r}. Expected one of: {expected}") from exc


class _ConstantProbabilityClassifier:
    def __init__(self, positive_probability: float) -> None:
        self.positive_probability = float(np.clip(positive_probability, 0.0, 1.0))

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        positive = np.full(len(features.index), self.positive_probability, dtype="float64")
        return np.column_stack([1.0 - positive, positive])


@dataclass(frozen=True)
class PromotionTrainingArtifacts:
    artifact_root: str
    manifest_path: str
    metrics_path: str
    inference_schema_path: str
    feature_list_path: str
    artifact_files: dict[str, str]
    metrics: dict[str, dict[str, object]]
    target_mode: str = DEFAULT_PROMOTION_TRAINER_TARGET_MODE
    model_input_audit_paths: ModelInputAuditPaths | None = None
    feature_environment_audit_paths: FeatureEnvironmentAuditPaths | None = None
    test_set_predictions_path: str | None = None
    allocation_decision_scoreboard_json_path: str | None = None
    allocation_decision_scoreboard_csv_path: str | None = None
    policy_effectiveness_artifact_paths: dict[str, str] | None = None
    policy_replay_effectiveness_artifact_paths: dict[str, str] | None = None
    policy_rule_contribution_artifact_paths: dict[str, str] | None = None
    target_contract_artifact_paths: dict[str, str] | None = None
    target_mode_artifact_paths: dict[str, str] | None = None


@dataclass(frozen=True)
class PromotionTargetModeMultiSliceArtifacts:
    artifact_root: str
    manifest_path: str
    summary_json_path: str
    summary_csv_path: str
    bucket_ranking_json_path: str
    bucket_ranking_csv_path: str
    residual_examples_json_path: str
    residual_examples_csv_path: str
    stability_gate_json_path: str
    stability_gate: dict[str, object]
    slice_run_artifact_paths: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class PromotionTargetContractDesignArtifacts:
    artifact_root: str
    summary_json_path: str
    summary_csv_path: str
    bucket_ranking_json_path: str
    bucket_ranking_csv_path: str
    residual_examples_json_path: str
    residual_examples_csv_path: str
    proposal_json_path: str
    proposal: dict[str, object]


@dataclass(frozen=True)
class PromotionTargetDesignRepeatedEvidenceArtifacts:
    artifact_root: str
    inventory_json_path: str
    inventory_csv_path: str
    summary_json_path: str
    summary_csv_path: str
    gate_json_path: str
    residual_examples_json_path: str
    residual_examples_csv_path: str
    manifest_json_path: str
    target_mode_multi_slice_manifest_path: str
    target_contract_design_proposal_path: str
    gate: dict[str, object]


@dataclass(frozen=True)
class PromotionTargetContractThreeWayArtifacts:
    artifact_root: str
    summary_json_path: str
    summary_csv_path: str
    bucket_ranking_json_path: str
    bucket_ranking_csv_path: str
    residual_examples_json_path: str
    residual_examples_csv_path: str
    proposal_json_path: str
    manifest_json_path: str
    proposal: dict[str, object]


@dataclass(frozen=True)
class PromotionTargetPromotionReadinessArtifacts:
    artifact_root: str
    scoreboard_json_path: str
    scoreboard_csv_path: str
    blocker_ranking_json_path: str
    residual_examples_json_path: str
    decision_packet_json_path: str
    decision_packet: dict[str, object]


@dataclass(frozen=True)
class PromotionTargetWeakSliceRepairArtifacts:
    artifact_root: str
    summary_json_path: str
    summary_csv_path: str
    plan_json_path: str
    plan_csv_path: str
    residual_examples_json_path: str
    decision_packet_json_path: str
    decision_packet: dict[str, object]


class PromotionModelTrainer:
    """Fit and persist the reusable promotions model family."""

    def __init__(self) -> None:
        self._time_splitter = PromotionTimeSplitter()

    def train(
        self,
        *,
        run_id: str,
        dataset: pd.DataFrame,
        dataset_path: str,
        artifact_paths: PromotionArtifactPaths,
        target_mode: PromotionTrainerTargetMode | str = DEFAULT_PROMOTION_TRAINER_TARGET_MODE,
    ) -> PromotionTrainingArtifacts:
        """Train the promotions model family and persist artifacts plus lineage."""

        resolved_target_mode = _resolve_promotion_trainer_target_mode(target_mode)
        if resolved_target_mode != DEFAULT_PROMOTION_TRAINER_TARGET_MODE:
            dataset = _ensure_historical_allocation_candidate_target_bundle(dataset)
        model_input, schema = prepare_model_input_frame(dataset)
        split = self._time_splitter.split(dataset)
        artifact_root = artifact_paths.model_family_root(run_id)
        artifact_root.mkdir(parents=True, exist_ok=True)

        units_linear = self._build_linear_regressor(schema)
        units_tree = self._build_tree_regressor(schema)
        gross_profit_linear = self._build_linear_regressor(schema)
        overallocation_classifier = self._build_tree_classifier(schema)
        underallocation_classifier = self._build_tree_classifier(schema)
        stockout_classifier = self._build_tree_classifier(schema)

        training_sets = self._training_sets(dataset, model_input, split)
        units_linear.fit(training_sets["train_features"], training_sets["train_targets"]["target_actual_units_sold"])
        units_tree.fit(training_sets["train_features"], training_sets["train_targets"]["target_actual_units_sold"])
        gross_profit_linear.fit(
            training_sets["train_features"],
            training_sets["train_targets"]["target_actual_gross_profit_dollars"],
        )
        overallocation_classifier.fit(
            training_sets["train_features"],
            training_sets["train_targets"]["target_overallocation_flag"],
        )
        underallocation_classifier.fit(
            training_sets["train_features"],
            training_sets["train_targets"]["target_underallocation_flag"],
        )
        stockout_classifier.fit(
            training_sets["train_features"],
            training_sets["train_targets"]["target_stockout_flag"],
        )

        allocation_outcome_metrics, allocation_diagnostic_rows = self._allocation_outcome_metrics(
            units_tree,
            overallocation_classifier,
            validation_features=training_sets["validation_features"],
            validation_dataset=dataset.loc[split.validation_mask],
            test_features=training_sets["test_features"],
            test_dataset=dataset.loc[split.test_mask],
        )
        metrics = {
            "units_linear": self._regression_metrics(
                units_linear,
                training_sets["validation_features"],
                training_sets["validation_targets"]["target_actual_units_sold"],
                training_sets["test_features"],
                training_sets["test_targets"]["target_actual_units_sold"],
            ),
            "units_gradient_boosting": self._regression_metrics(
                units_tree,
                training_sets["validation_features"],
                training_sets["validation_targets"]["target_actual_units_sold"],
                training_sets["test_features"],
                training_sets["test_targets"]["target_actual_units_sold"],
            ),
            "gross_profit_linear": self._regression_metrics(
                gross_profit_linear,
                training_sets["validation_features"],
                training_sets["validation_targets"]["target_actual_gross_profit_dollars"],
                training_sets["test_features"],
                training_sets["test_targets"]["target_actual_gross_profit_dollars"],
            ),
            "overallocation_classifier": self._classification_metrics(
                overallocation_classifier,
                training_sets["validation_features"],
                training_sets["validation_targets"]["target_overallocation_flag"],
                training_sets["test_features"],
                training_sets["test_targets"]["target_overallocation_flag"],
            ),
            "underallocation_classifier": self._classification_metrics(
                underallocation_classifier,
                training_sets["validation_features"],
                training_sets["validation_targets"]["target_underallocation_flag"],
                training_sets["test_features"],
                training_sets["test_targets"]["target_underallocation_flag"],
            ),
            "stockout_classifier": self._classification_metrics(
                stockout_classifier,
                training_sets["validation_features"],
                training_sets["validation_targets"]["target_stockout_flag"],
                training_sets["test_features"],
                training_sets["test_targets"]["target_stockout_flag"],
            ),
            "allocation_outcomes": allocation_outcome_metrics,
        }
        artifact_files = self._persist_models(
            artifact_root=artifact_root,
            models={
                "units_linear": units_linear,
                "units_gradient_boosting": units_tree,
                "gross_profit_linear": gross_profit_linear,
                "overallocation_classifier": overallocation_classifier,
                "underallocation_classifier": underallocation_classifier,
                "stockout_classifier": stockout_classifier,
            },
        )
        allocation_decision_scoreboard_json_path, allocation_decision_scoreboard_csv_path = self._write_allocation_decision_scoreboard(
            run_id=run_id,
            artifact_paths=artifact_paths,
            allocation_diagnostic_rows=allocation_diagnostic_rows,
        )
        artifact_files["allocation_decision_scoreboard_json"] = allocation_decision_scoreboard_json_path
        artifact_files["allocation_decision_scoreboard_csv"] = allocation_decision_scoreboard_csv_path
        policy_effectiveness_artifact_paths = self._write_policy_effectiveness_artifacts(
            run_id=run_id,
            artifact_paths=artifact_paths,
            allocation_diagnostic_rows=allocation_diagnostic_rows,
        )
        artifact_files.update(
            {
                "policy_effectiveness_summary_json": policy_effectiveness_artifact_paths["summary_json_path"],
                "policy_effectiveness_summary_csv": policy_effectiveness_artifact_paths["summary_csv_path"],
                "policy_bucket_ranking_json": policy_effectiveness_artifact_paths["bucket_ranking_json_path"],
                "policy_bucket_ranking_csv": policy_effectiveness_artifact_paths["bucket_ranking_csv_path"],
                "policy_worst_remaining_bucket_residual_json": policy_effectiveness_artifact_paths["worst_bucket_residual_json_path"],
                "policy_worst_remaining_bucket_residual_csv": policy_effectiveness_artifact_paths["worst_bucket_residual_csv_path"],
            }
        )
        policy_replay_effectiveness_artifact_paths = self._write_policy_replay_effectiveness_artifacts(
            run_id=run_id,
            artifact_paths=artifact_paths,
            allocation_diagnostic_rows=allocation_diagnostic_rows,
        )
        artifact_files.update(
            {
                "policy_replay_effectiveness_summary_json": policy_replay_effectiveness_artifact_paths["summary_json_path"],
                "policy_replay_effectiveness_summary_csv": policy_replay_effectiveness_artifact_paths["summary_csv_path"],
                "policy_replay_bucket_ranking_json": policy_replay_effectiveness_artifact_paths["bucket_ranking_json_path"],
                "policy_replay_bucket_ranking_csv": policy_replay_effectiveness_artifact_paths["bucket_ranking_csv_path"],
                "policy_replay_worst_remaining_bucket_residual_json": policy_replay_effectiveness_artifact_paths["worst_bucket_residual_json_path"],
                "policy_replay_worst_remaining_bucket_residual_csv": policy_replay_effectiveness_artifact_paths["worst_bucket_residual_csv_path"],
            }
        )
        policy_rule_contribution_artifact_paths = self._write_policy_rule_contribution_artifacts(
            run_id=run_id,
            artifact_paths=artifact_paths,
            allocation_diagnostic_rows=allocation_diagnostic_rows,
        )
        artifact_files.update(
            {
                "policy_rule_contribution_summary_json": policy_rule_contribution_artifact_paths["summary_json_path"],
                "policy_rule_contribution_summary_csv": policy_rule_contribution_artifact_paths["summary_csv_path"],
                "policy_rule_overlap_matrix_json": policy_rule_contribution_artifact_paths["overlap_matrix_json_path"],
                "policy_rule_overlap_matrix_csv": policy_rule_contribution_artifact_paths["overlap_matrix_csv_path"],
                "policy_rule_solo_vs_overlap_json": policy_rule_contribution_artifact_paths["solo_vs_overlap_json_path"],
                "policy_rule_solo_vs_overlap_csv": policy_rule_contribution_artifact_paths["solo_vs_overlap_csv_path"],
                "policy_rule_refinement_candidate_json": policy_rule_contribution_artifact_paths["refinement_candidate_json_path"],
            }
        )
        target_contract_artifact_paths = self._write_target_contract_artifacts(
            run_id=run_id,
            artifact_paths=artifact_paths,
            allocation_diagnostic_rows=allocation_diagnostic_rows,
        )
        artifact_files.update(
            {
                "target_contract_comparison_summary_json": target_contract_artifact_paths["summary_json_path"],
                "target_contract_comparison_summary_csv": target_contract_artifact_paths["summary_csv_path"],
                "target_contract_bucket_ranking_json": target_contract_artifact_paths["bucket_ranking_json_path"],
                "target_contract_bucket_ranking_csv": target_contract_artifact_paths["bucket_ranking_csv_path"],
                "target_contract_residual_examples_json": target_contract_artifact_paths["residual_examples_json_path"],
                "target_contract_residual_examples_csv": target_contract_artifact_paths["residual_examples_csv_path"],
                "target_contract_row_diagnostics_parquet": target_contract_artifact_paths["row_diagnostics_parquet_path"],
                "target_contract_divergence_diagnostics_csv": target_contract_artifact_paths["divergence_diagnostics_csv_path"],
                "target_contract_divergence_summary_json": target_contract_artifact_paths["divergence_summary_json_path"],
                "next_target_refinement_candidate_json": target_contract_artifact_paths["next_target_refinement_candidate_json_path"],
                "next_target_promotion_decision_json": target_contract_artifact_paths["next_target_promotion_decision_json_path"],
            }
        )
        target_mode_artifact_paths: dict[str, str] | None = None
        if resolved_target_mode != DEFAULT_PROMOTION_TRAINER_TARGET_MODE:
            target_mode_artifact_paths = self._write_target_mode_comparison_artifacts(
                run_id=run_id,
                artifact_paths=artifact_paths,
                target_mode=resolved_target_mode,
                dataset=dataset,
                model_input=model_input,
                schema=schema,
                split=split,
                allocation_diagnostic_rows=allocation_diagnostic_rows,
            )
            artifact_files.update(
                {
                    "target_mode_comparison_summary_json": target_mode_artifact_paths["summary_json_path"],
                    "target_mode_comparison_summary_csv": target_mode_artifact_paths["summary_csv_path"],
                    "target_mode_bucket_ranking_json": target_mode_artifact_paths["bucket_ranking_json_path"],
                    "target_mode_bucket_ranking_csv": target_mode_artifact_paths["bucket_ranking_csv_path"],
                    "target_mode_residual_examples_json": target_mode_artifact_paths["residual_examples_json_path"],
                    "target_mode_residual_examples_csv": target_mode_artifact_paths["residual_examples_csv_path"],
                    "target_contract_promotion_gate_json": target_mode_artifact_paths["promotion_gate_json_path"],
                    "target_mode_shadow_current_excess_units_model": target_mode_artifact_paths["shadow_current_excess_units_model_path"],
                    "target_mode_shadow_current_overallocation_classifier": target_mode_artifact_paths["shadow_current_overallocation_classifier_path"],
                    "target_mode_shadow_historical_excess_units_model": target_mode_artifact_paths["shadow_historical_excess_units_model_path"],
                    "target_mode_shadow_historical_overallocation_classifier": target_mode_artifact_paths["shadow_historical_overallocation_classifier_path"],
                }
            )
        trained_at = datetime.now(tz=UTC).isoformat()
        feature_list_path = artifact_root / "feature_list.json"
        metrics_path = artifact_root / "training_metrics.json"
        inference_schema_path = artifact_root / "inference_schema.json"
        manifest_path = artifact_root / "run_manifest.json"
        inference_schema = PromotionInferenceSchema(
            feature_columns=schema.feature_columns,
            numeric_columns=schema.numeric_columns,
            categorical_columns=schema.categorical_columns,
            target_columns=(
                "target_actual_units_sold",
                "target_actual_gross_profit_dollars",
                "target_overallocation_flag",
                "target_underallocation_flag",
                "target_stockout_flag",
            ),
        )
        write_json(feature_list_path, {"feature_columns": list(schema.feature_columns)})
        write_json(metrics_path, metrics)
        write_json(inference_schema_path, inference_schema.to_dict())
        write_json(
            manifest_path,
            PromotionTrainingManifest(
                run_id=run_id,
                trained_at_utc=trained_at,
                dataset_path=dataset_path,
                target_mode=resolved_target_mode,
                split_summary={
                    "train_rows": int(split.train_mask.sum()),
                    "validation_rows": int(split.validation_mask.sum()),
                    "test_rows": int(split.test_mask.sum()),
                    "train_last_date": split.train_last_date,
                    "validation_last_date": split.validation_last_date,
                    "test_last_date": split.test_last_date,
                },
                feature_list_path=str(feature_list_path),
                metrics_path=str(metrics_path),
                inference_schema_path=str(inference_schema_path),
                artifact_files=artifact_files,
            ).to_dict(),
        )
        # Governed model-input audit: write the EXACT frame handed to the model
        # for training, plus a 10k-row sample CSV with consistent 4dp rounding,
        # plus the feature-lineage and contract validation artifacts.
        engineered_columns = tuple(
            column_name
            for column_name in dataset.columns
            if str(column_name).startswith("feature_")
        )
        inspection_root = artifact_paths.inspection_run_root(run_id)
        model_input_audit_paths = write_model_input_audit_artifacts(
            run_id=run_id,
            stage_label="training",
            inspection_root=inspection_root,
            model_input=model_input,
            feature_columns=schema.feature_columns,
            target_columns=inference_schema.target_columns,
            raw_columns=tuple(dataset.columns),
            cleaned_columns=tuple(dataset.columns),
            engineered_columns=engineered_columns,
            source_artifact_path=dataset_path,
            quality_report=schema.quality_report,
        )
        # Governed feature-environment audit: per-row prior-promo memory and
        # intermittent-demand cadence diagnostic plus a contamination-prone
        # subset, written from the engineered training dataset.
        feature_environment_audit_paths = write_feature_environment_audit_artifacts(
            engineered_frame=dataset,
            inspection_root=inspection_root,
        )
        # Governed honest-out-of-sample test-set predictions parquet.
        # The completed-promotion demand backtest orchestrator consumes this
        # parquet to produce row-level forecast-vs-actual artifacts. Predictions
        # come from the units-gradient-boosting head after the same allocation-
        # aware cap used by scoring.
        test_set_predictions_path = self._write_test_set_predictions(
            artifact_root=artifact_root,
            dataset=dataset,
            model_input=model_input,
            split=split,
            units_model=units_tree,
        )
        LOGGER.info(
            "Trained promotions model family: run_id=%s rows=%s features=%s",
            run_id,
            len(dataset.index),
            len(schema.feature_columns),
        )
        return PromotionTrainingArtifacts(
            artifact_root=str(artifact_root),
            manifest_path=str(manifest_path),
            metrics_path=str(metrics_path),
            inference_schema_path=str(inference_schema_path),
            feature_list_path=str(feature_list_path),
            artifact_files=artifact_files,
            metrics=metrics,
            target_mode=resolved_target_mode,
            model_input_audit_paths=model_input_audit_paths,
            feature_environment_audit_paths=feature_environment_audit_paths,
            test_set_predictions_path=test_set_predictions_path,
            allocation_decision_scoreboard_json_path=allocation_decision_scoreboard_json_path,
            allocation_decision_scoreboard_csv_path=allocation_decision_scoreboard_csv_path,
            policy_effectiveness_artifact_paths=policy_effectiveness_artifact_paths,
            policy_replay_effectiveness_artifact_paths=policy_replay_effectiveness_artifact_paths,
            policy_rule_contribution_artifact_paths=policy_rule_contribution_artifact_paths,
            target_contract_artifact_paths=target_contract_artifact_paths,
            target_mode_artifact_paths=target_mode_artifact_paths,
        )

    def _write_allocation_decision_scoreboard(
        self,
        *,
        run_id: str,
        artifact_paths: PromotionArtifactPaths,
        allocation_diagnostic_rows: pd.DataFrame,
    ) -> tuple[str, str]:
        scoreboard_json_path = artifact_paths.allocation_decision_scoreboard_json_path(run_id)
        scoreboard_csv_path = artifact_paths.allocation_decision_scoreboard_csv_path(run_id)
        scoreboard_json_path.parent.mkdir(parents=True, exist_ok=True)
        scoreboard_csv_path.parent.mkdir(parents=True, exist_ok=True)

        scoreboard_csv_frame, scoreboard_payload = _build_allocation_decision_scoreboard(
            allocation_diagnostic_rows
        )
        scoreboard_csv_frame.to_csv(scoreboard_csv_path, index=False)
        write_json(scoreboard_json_path, scoreboard_payload)
        return str(scoreboard_json_path), str(scoreboard_csv_path)

    def _write_policy_effectiveness_artifacts(
        self,
        *,
        run_id: str,
        artifact_paths: PromotionArtifactPaths,
        allocation_diagnostic_rows: pd.DataFrame,
    ) -> dict[str, str]:
        summary_json_path = artifact_paths.policy_effectiveness_summary_json_path(run_id)
        summary_csv_path = artifact_paths.policy_effectiveness_summary_csv_path(run_id)
        bucket_ranking_json_path = artifact_paths.policy_bucket_ranking_json_path(run_id)
        bucket_ranking_csv_path = artifact_paths.policy_bucket_ranking_csv_path(run_id)
        worst_bucket_residual_json_path = artifact_paths.policy_worst_remaining_bucket_residual_json_path(run_id)
        worst_bucket_residual_csv_path = artifact_paths.policy_worst_remaining_bucket_residual_csv_path(run_id)

        for path in (
            summary_json_path,
            summary_csv_path,
            bucket_ranking_json_path,
            bucket_ranking_csv_path,
            worst_bucket_residual_json_path,
            worst_bucket_residual_csv_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        artifacts = _build_policy_effectiveness_artifacts(allocation_diagnostic_rows)
        artifacts["summary_csv_frame"].to_csv(summary_csv_path, index=False)
        write_json(summary_json_path, artifacts["summary_payload"])
        artifacts["bucket_ranking_frame"].to_csv(bucket_ranking_csv_path, index=False)
        write_json(bucket_ranking_json_path, artifacts["bucket_ranking_payload"])
        artifacts["worst_bucket_residual_frame"].to_csv(worst_bucket_residual_csv_path, index=False)
        write_json(worst_bucket_residual_json_path, artifacts["worst_bucket_residual_payload"])

        return {
            "summary_json_path": str(summary_json_path),
            "summary_csv_path": str(summary_csv_path),
            "bucket_ranking_json_path": str(bucket_ranking_json_path),
            "bucket_ranking_csv_path": str(bucket_ranking_csv_path),
            "worst_bucket_residual_json_path": str(worst_bucket_residual_json_path),
            "worst_bucket_residual_csv_path": str(worst_bucket_residual_csv_path),
        }

    def _write_policy_replay_effectiveness_artifacts(
        self,
        *,
        run_id: str,
        artifact_paths: PromotionArtifactPaths,
        allocation_diagnostic_rows: pd.DataFrame,
    ) -> dict[str, str]:
        summary_json_path = artifact_paths.policy_replay_effectiveness_summary_json_path(run_id)
        summary_csv_path = artifact_paths.policy_replay_effectiveness_summary_csv_path(run_id)
        bucket_ranking_json_path = artifact_paths.policy_replay_bucket_ranking_json_path(run_id)
        bucket_ranking_csv_path = artifact_paths.policy_replay_bucket_ranking_csv_path(run_id)
        worst_bucket_residual_json_path = artifact_paths.policy_replay_worst_remaining_bucket_residual_json_path(run_id)
        worst_bucket_residual_csv_path = artifact_paths.policy_replay_worst_remaining_bucket_residual_csv_path(run_id)

        for path in (
            summary_json_path,
            summary_csv_path,
            bucket_ranking_json_path,
            bucket_ranking_csv_path,
            worst_bucket_residual_json_path,
            worst_bucket_residual_csv_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        artifacts = _build_policy_replay_effectiveness_artifacts(allocation_diagnostic_rows)
        artifacts["summary_csv_frame"].to_csv(summary_csv_path, index=False)
        write_json(summary_json_path, artifacts["summary_payload"])
        artifacts["bucket_ranking_frame"].to_csv(bucket_ranking_csv_path, index=False)
        write_json(bucket_ranking_json_path, artifacts["bucket_ranking_payload"])
        artifacts["worst_bucket_residual_frame"].to_csv(worst_bucket_residual_csv_path, index=False)
        write_json(worst_bucket_residual_json_path, artifacts["worst_bucket_residual_payload"])

        return {
            "summary_json_path": str(summary_json_path),
            "summary_csv_path": str(summary_csv_path),
            "bucket_ranking_json_path": str(bucket_ranking_json_path),
            "bucket_ranking_csv_path": str(bucket_ranking_csv_path),
            "worst_bucket_residual_json_path": str(worst_bucket_residual_json_path),
            "worst_bucket_residual_csv_path": str(worst_bucket_residual_csv_path),
        }

    def _write_policy_rule_contribution_artifacts(
        self,
        *,
        run_id: str,
        artifact_paths: PromotionArtifactPaths,
        allocation_diagnostic_rows: pd.DataFrame,
    ) -> dict[str, str]:
        summary_json_path = artifact_paths.policy_rule_contribution_summary_json_path(run_id)
        summary_csv_path = artifact_paths.policy_rule_contribution_summary_csv_path(run_id)
        overlap_matrix_json_path = artifact_paths.policy_rule_overlap_matrix_json_path(run_id)
        overlap_matrix_csv_path = artifact_paths.policy_rule_overlap_matrix_csv_path(run_id)
        solo_vs_overlap_json_path = artifact_paths.policy_rule_solo_vs_overlap_json_path(run_id)
        solo_vs_overlap_csv_path = artifact_paths.policy_rule_solo_vs_overlap_csv_path(run_id)
        refinement_candidate_json_path = artifact_paths.policy_rule_refinement_candidate_json_path(run_id)

        for path in (
            summary_json_path,
            summary_csv_path,
            overlap_matrix_json_path,
            overlap_matrix_csv_path,
            solo_vs_overlap_json_path,
            solo_vs_overlap_csv_path,
            refinement_candidate_json_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        artifacts = _build_policy_rule_contribution_artifacts(allocation_diagnostic_rows)
        artifacts["summary_frame"].to_csv(summary_csv_path, index=False)
        write_json(summary_json_path, artifacts["summary_payload"])
        artifacts["overlap_matrix_frame"].to_csv(overlap_matrix_csv_path, index=False)
        write_json(overlap_matrix_json_path, artifacts["overlap_matrix_payload"])
        artifacts["solo_vs_overlap_frame"].to_csv(solo_vs_overlap_csv_path, index=False)
        write_json(solo_vs_overlap_json_path, artifacts["solo_vs_overlap_payload"])
        write_json(refinement_candidate_json_path, artifacts["refinement_candidate_payload"])

        return {
            "summary_json_path": str(summary_json_path),
            "summary_csv_path": str(summary_csv_path),
            "overlap_matrix_json_path": str(overlap_matrix_json_path),
            "overlap_matrix_csv_path": str(overlap_matrix_csv_path),
            "solo_vs_overlap_json_path": str(solo_vs_overlap_json_path),
            "solo_vs_overlap_csv_path": str(solo_vs_overlap_csv_path),
            "refinement_candidate_json_path": str(refinement_candidate_json_path),
        }

    def _write_target_contract_artifacts(
        self,
        *,
        run_id: str,
        artifact_paths: PromotionArtifactPaths,
        allocation_diagnostic_rows: pd.DataFrame,
    ) -> dict[str, str]:
        summary_json_path = artifact_paths.target_contract_comparison_summary_json_path(run_id)
        summary_csv_path = artifact_paths.target_contract_comparison_summary_csv_path(run_id)
        bucket_ranking_json_path = artifact_paths.target_contract_bucket_ranking_json_path(run_id)
        bucket_ranking_csv_path = artifact_paths.target_contract_bucket_ranking_csv_path(run_id)
        residual_examples_json_path = artifact_paths.target_contract_residual_examples_json_path(run_id)
        residual_examples_csv_path = artifact_paths.target_contract_residual_examples_csv_path(run_id)
        row_diagnostics_parquet_path = artifact_paths.target_contract_row_diagnostics_parquet_path(run_id)
        divergence_diagnostics_csv_path = artifact_paths.target_contract_divergence_diagnostics_csv_path(run_id)
        divergence_summary_json_path = artifact_paths.target_contract_divergence_summary_json_path(run_id)
        next_target_refinement_candidate_json_path = artifact_paths.next_target_refinement_candidate_json_path(run_id)
        next_target_promotion_decision_json_path = artifact_paths.next_target_promotion_decision_json_path(run_id)

        for path in (
            summary_json_path,
            summary_csv_path,
            bucket_ranking_json_path,
            bucket_ranking_csv_path,
            residual_examples_json_path,
            residual_examples_csv_path,
            row_diagnostics_parquet_path,
            divergence_diagnostics_csv_path,
            divergence_summary_json_path,
            next_target_refinement_candidate_json_path,
            next_target_promotion_decision_json_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        artifacts = _build_target_contract_artifacts(allocation_diagnostic_rows)
        artifacts["summary_frame"].to_csv(summary_csv_path, index=False)
        write_json(summary_json_path, artifacts["summary_payload"])
        artifacts["bucket_ranking_frame"].to_csv(bucket_ranking_csv_path, index=False)
        write_json(bucket_ranking_json_path, artifacts["bucket_ranking_payload"])
        artifacts["residual_examples_frame"].to_csv(residual_examples_csv_path, index=False)
        write_json(residual_examples_json_path, artifacts["residual_examples_payload"])
        artifacts["row_diagnostics_frame"].to_parquet(row_diagnostics_parquet_path, index=False)
        artifacts["divergence_diagnostics_frame"].to_csv(divergence_diagnostics_csv_path, index=False)
        write_json(divergence_summary_json_path, artifacts["divergence_summary_payload"])
        write_json(next_target_refinement_candidate_json_path, artifacts["next_target_refinement_candidate_payload"])
        write_json(next_target_promotion_decision_json_path, artifacts["next_target_promotion_decision_payload"])

        return {
            "summary_json_path": str(summary_json_path),
            "summary_csv_path": str(summary_csv_path),
            "bucket_ranking_json_path": str(bucket_ranking_json_path),
            "bucket_ranking_csv_path": str(bucket_ranking_csv_path),
            "residual_examples_json_path": str(residual_examples_json_path),
            "residual_examples_csv_path": str(residual_examples_csv_path),
            "row_diagnostics_parquet_path": str(row_diagnostics_parquet_path),
            "divergence_diagnostics_csv_path": str(divergence_diagnostics_csv_path),
            "divergence_summary_json_path": str(divergence_summary_json_path),
            "next_target_refinement_candidate_json_path": str(next_target_refinement_candidate_json_path),
            "next_target_promotion_decision_json_path": str(next_target_promotion_decision_json_path),
        }

    def _write_target_mode_comparison_artifacts(
        self,
        *,
        run_id: str,
        artifact_paths: PromotionArtifactPaths,
        target_mode: PromotionTrainerTargetMode,
        dataset: pd.DataFrame,
        model_input: pd.DataFrame,
        schema,
        split,
        allocation_diagnostic_rows: pd.DataFrame,
    ) -> dict[str, str]:
        summary_json_path = artifact_paths.target_mode_comparison_summary_json_path(run_id)
        summary_csv_path = artifact_paths.target_mode_comparison_summary_csv_path(run_id)
        bucket_ranking_json_path = artifact_paths.target_mode_bucket_ranking_json_path(run_id)
        bucket_ranking_csv_path = artifact_paths.target_mode_bucket_ranking_csv_path(run_id)
        residual_examples_json_path = artifact_paths.target_mode_residual_examples_json_path(run_id)
        residual_examples_csv_path = artifact_paths.target_mode_residual_examples_csv_path(run_id)
        promotion_gate_json_path = artifact_paths.target_contract_promotion_gate_json_path(run_id)
        shadow_current_excess_units_model_path = artifact_paths.target_mode_shadow_model_path(
            run_id,
            "shadow_current_excess_units_model",
        )
        shadow_current_overallocation_classifier_path = artifact_paths.target_mode_shadow_model_path(
            run_id,
            "shadow_current_overallocation_classifier",
        )
        shadow_historical_excess_units_model_path = artifact_paths.target_mode_shadow_model_path(
            run_id,
            "shadow_historical_excess_units_model",
        )
        shadow_historical_overallocation_classifier_path = artifact_paths.target_mode_shadow_model_path(
            run_id,
            "shadow_historical_overallocation_classifier",
        )

        for path in (
            summary_json_path,
            summary_csv_path,
            bucket_ranking_json_path,
            bucket_ranking_csv_path,
            residual_examples_json_path,
            residual_examples_csv_path,
            promotion_gate_json_path,
            shadow_current_excess_units_model_path,
            shadow_current_overallocation_classifier_path,
            shadow_historical_excess_units_model_path,
            shadow_historical_overallocation_classifier_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        artifacts = self._build_target_mode_shadow_training_artifacts(
            target_mode=target_mode,
            dataset=dataset,
            model_input=model_input,
            schema=schema,
            split=split,
            allocation_diagnostic_rows=allocation_diagnostic_rows,
        )
        artifacts["summary_frame"].to_csv(summary_csv_path, index=False)
        write_json(summary_json_path, artifacts["summary_payload"])
        artifacts["bucket_ranking_frame"].to_csv(bucket_ranking_csv_path, index=False)
        write_json(bucket_ranking_json_path, artifacts["bucket_ranking_payload"])
        artifacts["residual_examples_frame"].to_csv(residual_examples_csv_path, index=False)
        write_json(residual_examples_json_path, artifacts["residual_examples_payload"])
        write_json(promotion_gate_json_path, artifacts["promotion_gate_payload"])
        joblib.dump(artifacts["shadow_current_excess_units_model"], shadow_current_excess_units_model_path)
        joblib.dump(artifacts["shadow_current_overallocation_classifier"], shadow_current_overallocation_classifier_path)
        joblib.dump(artifacts["shadow_historical_excess_units_model"], shadow_historical_excess_units_model_path)
        joblib.dump(artifacts["shadow_historical_overallocation_classifier"], shadow_historical_overallocation_classifier_path)

        return {
            "summary_json_path": str(summary_json_path),
            "summary_csv_path": str(summary_csv_path),
            "bucket_ranking_json_path": str(bucket_ranking_json_path),
            "bucket_ranking_csv_path": str(bucket_ranking_csv_path),
            "residual_examples_json_path": str(residual_examples_json_path),
            "residual_examples_csv_path": str(residual_examples_csv_path),
            "promotion_gate_json_path": str(promotion_gate_json_path),
            "shadow_current_excess_units_model_path": str(shadow_current_excess_units_model_path),
            "shadow_current_overallocation_classifier_path": str(shadow_current_overallocation_classifier_path),
            "shadow_historical_excess_units_model_path": str(shadow_historical_excess_units_model_path),
            "shadow_historical_overallocation_classifier_path": str(shadow_historical_overallocation_classifier_path),
        }

    def _build_target_mode_shadow_training_artifacts(
        self,
        *,
        target_mode: PromotionTrainerTargetMode,
        dataset: pd.DataFrame,
        model_input: pd.DataFrame,
        schema,
        split,
        allocation_diagnostic_rows: pd.DataFrame,
    ) -> dict[str, object]:
        target_contract_artifacts = _build_target_contract_artifacts(allocation_diagnostic_rows)
        diagnostic_frame = target_contract_artifacts["row_diagnostics_frame"].reset_index(drop=True).copy()
        train_mask = _coerce_split_mask(split.train_mask, dataset.index)
        validation_mask = _coerce_split_mask(split.validation_mask, dataset.index)
        test_mask = _coerce_split_mask(split.test_mask, dataset.index)
        evaluation_mask = validation_mask | test_mask
        evaluation_features = pd.concat(
            [model_input.loc[validation_mask], model_input.loc[test_mask]],
            axis=0,
        )
        if len(evaluation_features.index) != len(diagnostic_frame.index):
            raise ValueError(
                "target mode comparison expected allocation diagnostics to match validation+test row count"
            )

        current_targets = _build_current_trainer_contract_target_frame(dataset)
        historical_targets = _build_historical_allocation_candidate_target_frame(dataset)
        current_train_mask = train_mask & current_targets["valid_flag"]
        historical_train_mask = train_mask & historical_targets["valid_flag"]
        if not current_train_mask.any():
            raise ValueError("target mode comparison requires at least one valid current-contract training row")
        if not historical_train_mask.any():
            raise ValueError("historical allocation candidate target mode requires at least one valid historical training row")

        current_excess_units_model = self._build_tree_regressor(schema)
        current_excess_units_model.fit(
            model_input.loc[current_train_mask],
            current_targets.loc[current_train_mask, "excess_units"],
        )
        historical_excess_units_model = self._build_tree_regressor(schema)
        historical_excess_units_model.fit(
            model_input.loc[historical_train_mask],
            historical_targets.loc[historical_train_mask, "excess_units"],
        )
        current_overallocation_classifier = self._fit_shadow_overallocation_classifier(
            schema,
            model_input.loc[current_train_mask],
            current_targets.loc[current_train_mask, "overallocation_flag"],
        )
        historical_overallocation_classifier = self._fit_shadow_overallocation_classifier(
            schema,
            model_input.loc[historical_train_mask],
            historical_targets.loc[historical_train_mask, "overallocation_flag"],
        )

        current_predicted_excess_units = pd.Series(
            current_excess_units_model.predict(evaluation_features),
            index=evaluation_features.index,
        ).clip(lower=0.0)
        historical_predicted_excess_units = pd.Series(
            historical_excess_units_model.predict(evaluation_features),
            index=evaluation_features.index,
        ).clip(lower=0.0)
        current_probability = pd.Series(
            current_overallocation_classifier.predict_proba(evaluation_features)[:, 1],
            index=evaluation_features.index,
        )
        historical_probability = pd.Series(
            historical_overallocation_classifier.predict_proba(evaluation_features)[:, 1],
            index=evaluation_features.index,
        )

        diagnostic_frame["current_contract_shadow_predicted_excess_units"] = current_predicted_excess_units.to_numpy()
        diagnostic_frame["historical_candidate_shadow_predicted_excess_units"] = historical_predicted_excess_units.to_numpy()
        diagnostic_frame["current_contract_shadow_overallocation_probability"] = current_probability.to_numpy()
        diagnostic_frame["historical_candidate_shadow_overallocation_probability"] = historical_probability.to_numpy()
        diagnostic_frame["current_contract_shadow_overallocation_flag"] = current_probability.ge(0.5).astype(float).to_numpy()
        diagnostic_frame["historical_candidate_shadow_overallocation_flag"] = historical_probability.ge(0.5).astype(float).to_numpy()
        replay_cost = pd.to_numeric(diagnostic_frame["replay_unit_cost"], errors="coerce").astype("Float64")
        current_cost = pd.to_numeric(diagnostic_frame["unit_cost"], errors="coerce").astype("Float64")
        diagnostic_frame["current_contract_shadow_predicted_excess_capital_on_current_cost"] = (
            diagnostic_frame["current_contract_shadow_predicted_excess_units"] * current_cost
        )
        diagnostic_frame["current_contract_shadow_predicted_excess_capital_on_historical_cost"] = (
            diagnostic_frame["current_contract_shadow_predicted_excess_units"] * replay_cost
        )
        diagnostic_frame["historical_candidate_shadow_predicted_excess_capital"] = (
            diagnostic_frame["historical_candidate_shadow_predicted_excess_units"] * replay_cost
        )

        artifacts = _build_target_mode_comparison_artifacts(
            target_mode=target_mode,
            diagnostic_frame=diagnostic_frame,
            target_contract_summary_payload=target_contract_artifacts["summary_payload"],
            train_row_counts={
                "current_contract_valid_training_rows": int(current_train_mask.sum()),
                "historical_candidate_valid_training_rows": int(historical_train_mask.sum()),
                "total_training_rows": int(train_mask.sum()),
            },
            evaluation_row_count=int(evaluation_mask.sum()),
        )
        artifacts.update(
            {
                "shadow_current_excess_units_model": current_excess_units_model,
                "shadow_current_overallocation_classifier": current_overallocation_classifier,
                "shadow_historical_excess_units_model": historical_excess_units_model,
                "shadow_historical_overallocation_classifier": historical_overallocation_classifier,
            }
        )
        return artifacts

    def _fit_shadow_overallocation_classifier(
        self,
        schema,
        features: pd.DataFrame,
        target: pd.Series,
    ):
        clean_target = pd.to_numeric(target, errors="coerce").dropna().astype(int)
        if clean_target.empty:
            raise ValueError("shadow overallocation classifier requires at least one valid target row")
        if clean_target.nunique(dropna=True) < 2:
            return _ConstantProbabilityClassifier(float(clean_target.mean()))
        model = self._build_tree_classifier(schema)
        model.fit(features.loc[clean_target.index], clean_target)
        return model

    def _training_sets(
        self,
        dataset: pd.DataFrame,
        model_input: pd.DataFrame,
        split,
    ) -> dict[str, pd.DataFrame]:
        target_columns = [
            "target_actual_units_sold",
            "target_actual_gross_profit_dollars",
            "target_overallocation_flag",
            "target_underallocation_flag",
            "target_stockout_flag",
        ]
        return {
            "train_features": model_input.loc[split.train_mask],
            "validation_features": model_input.loc[split.validation_mask],
            "test_features": model_input.loc[split.test_mask],
            "train_targets": dataset.loc[split.train_mask, target_columns],
            "validation_targets": dataset.loc[split.validation_mask, target_columns],
            "test_targets": dataset.loc[split.test_mask, target_columns],
        }

    def _build_linear_regressor(self, schema) -> Pipeline:
        preprocessor = ColumnTransformer(
            transformers=[
                (
                    "numeric",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="median")),
                            ("scaler", StandardScaler()),
                        ]
                    ),
                    list(schema.numeric_columns),
                ),
                (
                    "categorical",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            (
                                "onehot",
                                OneHotEncoder(handle_unknown="ignore", sparse_output=True),
                            ),
                        ]
                    ),
                    list(schema.categorical_columns),
                ),
            ],
        )
        return Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                (
                    "model",
                    Ridge(alpha=1.0),
                ),
            ]
        )

    def _build_tree_regressor(self, schema) -> Pipeline:
        preprocessor = ColumnTransformer(
            transformers=[
                (
                    "numeric",
                    Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]),
                    list(schema.numeric_columns),
                ),
                (
                    "categorical",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            (
                                "encoder",
                                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                            ),
                        ]
                    ),
                    list(schema.categorical_columns),
                ),
            ],
            sparse_threshold=0.0,
        )
        return Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        max_depth=6,
                        learning_rate=0.05,
                        max_iter=300,
                        random_state=42,
                    ),
                ),
            ]
        )

    def _build_tree_classifier(self, schema) -> Pipeline:
        preprocessor = ColumnTransformer(
            transformers=[
                (
                    "numeric",
                    Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]),
                    list(schema.numeric_columns),
                ),
                (
                    "categorical",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            (
                                "encoder",
                                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                            ),
                        ]
                    ),
                    list(schema.categorical_columns),
                ),
            ],
            sparse_threshold=0.0,
        )
        return Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        max_depth=6,
                        learning_rate=0.05,
                        max_iter=250,
                        random_state=42,
                    ),
                ),
            ]
        )

    def _persist_models(self, *, artifact_root: Path, models: dict[str, Pipeline]) -> dict[str, str]:
        artifact_files: dict[str, str] = {}
        for model_name, model in models.items():
            artifact_path = artifact_root / f"{model_name}.joblib"
            joblib.dump(model, artifact_path)
            artifact_files[model_name] = str(artifact_path)
        return artifact_files

    # Persist honest out-of-sample test-set predictions for the completed-promotion
    # demand backtest. Predictions follow the governed live scoring path: raw head,
    # allocation-aware calibration, then order-policy caps as separate columns.
    # `predicted_units_total_promo` is the demand export (= calibrated); policy caps
    # live in `policy_adjusted_predicted_units_total_promo` only. Output parquet uses
    # the `promotion_row_key` grain and carries through the segment columns the
    # backtest orchestrator splits on.
    _BACKTEST_PASSTHROUGH_COLUMNS: tuple[str, ...] = (
        "promotion_row_key",
        "store_number",
        "sku_number",
        "promotion_start_date",
        "promotional_end_date",
        "discount_percent",
        "promo_days",
        "live_promo_window_days",
        "actual_units_sold_promo",
        "actual_units_sold",
        "actual_sales_ex_gst_promo",
        "department",
        "category",
        "feature_intermittent_demand_flag",
        "feature_sparse_repeat_purchase_flag",
        "feature_prior_promo_14d_flag",
        "feature_prior_promo_28d_flag",
        "feature_prior_promo_56d_flag",
        "feature_prior_same_or_better_discount_56d_flag",
        "feature_historical_promo_events_same_discount",
        "feature_historical_units_same_discount_avg",
        "feature_basket_anchor_sku_score",
        "feature_basket_drag_along_dependency_score",
        "feature_basket_lone_random_purchase_score",
        "feature_basket_conditional_dependency_score",
        "feature_high_seller_companion_presence_probability",
        "feature_promo_anchor_absence_risk",
        "feature_top_20pct_driver_flag",
        "feature_long_tail_dependency_flag",
        "feature_basket_fragility_score",
        "feature_basket_convexity_support_score",
        "feature_basket_structure_evidence_available_flag",
        "feature_anchor_centrality_score",
        "feature_anchor_presence_support_score",
        "feature_top_anchor_dependency_score",
        "feature_anchor_absence_risk_score",
        "feature_companion_cluster_support_score",
        "feature_companion_concentration_score",
        "feature_multi_sku_promo_basket_rate",
        "feature_three_plus_promo_sku_basket_rate",
        "feature_solo_purchase_rate",
        "feature_sparse_random_purchase_score",
        "feature_basket_noise_score",
        "feature_transaction_object_uncertainty_score",
        "feature_conditional_sale_rate_with_anchor",
        "feature_conditional_sale_rate_without_anchor",
        "feature_conditional_lift_with_anchor",
        "feature_conditional_lift_with_companion_cluster",
        "feature_substitution_pressure_score",
        "feature_promo_basket_depth_alignment_score",
        "feature_anchor_mix_stability_score",
        "feature_conditional_lift_with_anchor",
        "feature_conditional_lift_with_companion_cluster",
        "feature_basket_equilibrium_regime_class",
        "feature_basket_equilibrium_score",
        "feature_basket_equilibrium_fragility_score",
        "feature_anchor_presence_dependency_score",
        "feature_anchor_absence_suppressed_demand_score",
        "feature_drag_along_probability",
        "feature_conditional_sale_probability_given_anchor",
        "feature_lone_purchase_noise_score",
        "feature_transaction_object_stability_score",
        "feature_basket_regime_class",
        "feature_basket_anchor_strength_score",
        "feature_basket_dependency_fragility_score",
        "feature_companion_presence_support_score",
        "feature_basket_depth_conditional_units_score",
        "feature_micro_market_clearing_pressure",
        "feature_local_equilibrium_gap_units",
        "feature_local_equilibrium_gap_dollars",
        "feature_substitute_pressure_score",
        "feature_complement_support_score",
        "feature_attention_competition_score",
        "feature_promo_field_equilibrium_state",
        "feature_inventory_constrained_demand_proxy",
        "feature_small_unit_option_value",
        "feature_convexity_to_capital_score",
        "feature_trust_floor_convexity_score",
        "feature_high_demand_underprotection_score",
        "feature_end_shape_fragility_score",
        "feature_sparse_demand_low_signal_flag",
        "feature_sparse_demand_stable_low_trust_flag",
        "feature_sparse_demand_random_tail_flag",
        "feature_sparse_demand_repeatability_score",
        "feature_sparse_demand_randomness_score",
        "feature_sparse_demand_one_off_likelihood_score",
        "feature_sparse_demand_daily_stability_score",
        "feature_sparse_demand_outlier_shape_score",
        "feature_sparse_demand_noise_regime_score",
        "feature_sparse_demand_evidence_available_flag",
        "feature_kalman_demand_state_level",
        "feature_kalman_demand_state_trend",
        "feature_kalman_demand_state_uncertainty",
        "feature_kalman_demand_state_shift_score",
        "feature_wasserstein_recent_vs_baseline_distance",
        "feature_distribution_shape_shift_score",
        "feature_distribution_tail_pressure_score",
        "feature_distribution_sparse_support_distance",
        "feature_fragility_adjusted_opportunity_score",
        "feature_convex_upside_small_unit_flag",
        "feature_dag_dependency_support_indicator",
        "feature_dependency_support_confidence_score",
        "feature_opportunity_tail_support_score",
        "feature_prior_promo_cannibalisation_risk_score",
        "promo_allocated_units",
        "pl_allocation_qty",
        "suggested_order_units",
        "recommended_order_units",
        "target_end_stock_units",
        "feature_promo_period_target_units",
        "feature_day_one_target_stock_units",
        "feature_end_of_promo_target_units",
        "feature_end_of_promo_target_floor_units",
        "feature_trust_floor_units_dynamic",
        "target_end_stock_floor_units",
        "feature_end_of_promo_target_days_cover",
        "feature_high_base_demand_end_cover_flag",
        "feature_month_end_inventory_efficiency_target",
        "feature_days_cover_vs_billing_cycle_target",
        "feature_units_needed_for_high_demand_cover",
        "feature_trust_floor_breach_risk_score",
        "feature_end_shape_success_target_flag",
        "feature_excess_month_end_capital_drag",
        "feature_cashflow_efficiency_score",
        "actual_end_stock_units",
        "ending_soh_units",
        "post_promo_soh_units",
        "high_demand_14d_cover_flag",
        "feature_no_promo_history_flag",
        "feature_month_end_cash_runoff_pressure_flag",
        "feature_units_needed_for_trust_floor",
        "feature_units_above_trust_target",
        "units_above_trust_target",
        "feature_capital_tied_above_trust_target",
        "capital_tied_above_trust_target",
        "feature_risk_adjusted_value_of_speculative_units",
        "effective_cost_per_unit",
        "promo_unit_cost",
        "unit_cost",
        "cost_per_unit",
        "promo_gm_unit",
        "unit_gross_profit",
        "gross_profit_per_unit",
        "actual_gross_profit_promo_dollars",
        "gross_profit_promo_dollars",
        "publish_eligibility_reason",
        "review_reason",
        "primary_review_reason",
    )

    def _write_test_set_predictions(
        self,
        *,
        artifact_root: Path,
        dataset: pd.DataFrame,
        model_input: pd.DataFrame,
        split,
        units_model: Pipeline,
    ) -> str | None:
        """Persist honest test-set predictions with governed backtest context.

        The output keeps the model prediction grain and adds only existing
        dataset columns needed by downstream diagnostics. Missing optional
        context is not invented here; the backtest scorecard remains fail-loud
        if a governed input is absent from the training dataset.
        """

        test_mask = split.test_mask
        if int(test_mask.sum()) == 0:
            return None
        test_features = model_input.loc[test_mask]
        raw_predicted_units = pd.Series(
            units_model.predict(test_features),
            index=test_features.index,
            dtype="float64",
        ).clip(lower=0.0)
        # Floor at zero — negative unit predictions are not commercially meaningful.
        test_dataset = dataset.loc[test_mask]
        allocation_cap_units = compute_allocation_aware_cap_units(
            test_dataset,
            raw_predicted_units,
        )
        # Phase 3: demand export uses raw model output; allocation cap is order-path only.
        calibrated_predicted_units = raw_predicted_units.clip(lower=0.0)
        diagnostics = build_live_order_decision_diagnostics(
            test_dataset,
            raw_predicted_units=raw_predicted_units,
            predicted_units=calibrated_predicted_units,
        )
        policy_adjustments = build_order_policy_adjustments(
            test_dataset,
            raw_predicted_units=raw_predicted_units,
            calibrated_predicted_units=calibrated_predicted_units,
            diagnostics_frame=diagnostics,
        )
        policy_adjusted_predicted_units = pd.to_numeric(
            policy_adjustments["adjusted_order_cap_units"],
            errors="coerce",
        ).fillna(calibrated_predicted_units).clip(lower=0.0)
        passthrough = [
            column_name
            for column_name in self._BACKTEST_PASSTHROUGH_COLUMNS
            if column_name in test_dataset.columns
        ]
        out = test_dataset.loc[:, passthrough].copy()
        out["raw_predicted_units_total_promo"] = raw_predicted_units.values
        out["calibrated_predicted_units_total_promo"] = calibrated_predicted_units.values
        out["allocation_cap_units"] = allocation_cap_units.values
        out["policy_adjusted_predicted_units_total_promo"] = policy_adjusted_predicted_units.values
        out["policy_adjustment_reason"] = policy_adjustments["policy_adjustment_reason"].values
        # Phase 2 demand/order separation: demand export follows calibrated path;
        # policy_adjusted_predicted_units_total_promo remains order-cap compatibility only.
        out["predicted_units_total_promo"] = calibrated_predicted_units.values
        # Make sure the canonical actual column is present even if only `actual_units_sold`
        # exists on this dataset variant.
        if "actual_units_sold_promo" not in out.columns and "actual_units_sold" in out.columns:
            out["actual_units_sold_promo"] = out["actual_units_sold"]
        target_path = artifact_root / "test_set_predictions.parquet"
        out.to_parquet(target_path, index=False)
        return str(target_path)

    def _regression_metrics(
        self,
        model: Pipeline,
        validation_features: pd.DataFrame,
        validation_target: pd.Series,
        test_features: pd.DataFrame,
        test_target: pd.Series,
    ) -> dict[str, float]:
        validation_prediction = model.predict(validation_features)
        test_prediction = model.predict(test_features)
        return {
            "validation_mae": float(mean_absolute_error(validation_target, validation_prediction)),
            "validation_rmse": float(np.sqrt(mean_squared_error(validation_target, validation_prediction))),
            "validation_r2": _safe_r2(validation_target, validation_prediction),
            "test_mae": float(mean_absolute_error(test_target, test_prediction)),
            "test_rmse": float(np.sqrt(mean_squared_error(test_target, test_prediction))),
            "test_r2": _safe_r2(test_target, test_prediction),
        }

    def _classification_metrics(
        self,
        model: Pipeline,
        validation_features: pd.DataFrame,
        validation_target: pd.Series,
        test_features: pd.DataFrame,
        test_target: pd.Series,
    ) -> dict[str, float]:
        validation_probability = model.predict_proba(validation_features)[:, 1]
        test_probability = model.predict_proba(test_features)[:, 1]
        validation_label = (validation_probability >= 0.5).astype(int)
        test_label = (test_probability >= 0.5).astype(int)
        return {
            "validation_roc_auc": _safe_roc_auc(validation_target, validation_probability),
            "validation_brier": float(brier_score_loss(validation_target, validation_probability)),
            "validation_precision": float(precision_score(validation_target, validation_label, zero_division=0)),
            "validation_recall": float(recall_score(validation_target, validation_label, zero_division=0)),
            "test_roc_auc": _safe_roc_auc(test_target, test_probability),
            "test_brier": float(brier_score_loss(test_target, test_probability)),
            "test_precision": float(precision_score(test_target, test_label, zero_division=0)),
            "test_recall": float(recall_score(test_target, test_label, zero_division=0)),
        }

    def _allocation_outcome_metrics(
        self,
        units_model: Pipeline,
        overallocation_model: Pipeline,
        *,
        validation_features: pd.DataFrame,
        validation_dataset: pd.DataFrame,
        test_features: pd.DataFrame,
        test_dataset: pd.DataFrame,
    ) -> tuple[dict[str, object], pd.DataFrame]:
        validation_rows = _build_allocation_split_diagnostic_rows(
            "validation",
            units_model=units_model,
            overallocation_model=overallocation_model,
            features=validation_features,
            dataset=validation_dataset,
        )
        test_rows = _build_allocation_split_diagnostic_rows(
            "test",
            units_model=units_model,
            overallocation_model=overallocation_model,
            features=test_features,
            dataset=test_dataset,
        )
        metrics: dict[str, object] = {}
        metrics.update(_allocation_split_metrics_from_rows("validation", validation_rows))
        metrics.update(_allocation_split_metrics_from_rows("test", test_rows))
        allocation_diagnostic_rows = pd.concat([validation_rows, test_rows], axis=0, ignore_index=True)
        return metrics, allocation_diagnostic_rows


class PromotionTargetModeShadowEvaluator:
    """Run governed target-mode shadow evidence across multiple completed slices."""

    def __init__(self) -> None:
        self._trainer = PromotionModelTrainer()

    def evaluate(
        self,
        *,
        run_id: str,
        slice_inputs: Sequence[str | Path],
        artifact_paths: PromotionArtifactPaths,
        target_mode: PromotionTrainerTargetMode | str = "dual_contract_diagnostics",
    ) -> PromotionTargetModeMultiSliceArtifacts:
        resolved_target_mode = _resolve_promotion_trainer_target_mode(target_mode)
        if resolved_target_mode == DEFAULT_PROMOTION_TRAINER_TARGET_MODE:
            raise ValueError("multi-slice shadow evaluation requires historical_allocation_candidate or dual_contract_diagnostics target_mode")
        slice_specs = _resolve_target_mode_shadow_slice_inputs(slice_inputs)
        if not slice_specs:
            raise ValueError("multi-slice shadow evaluation requires at least one governed slice input")

        artifact_root = artifact_paths.model_family_root(run_id)
        artifact_root.mkdir(parents=True, exist_ok=True)
        summary_json_path = artifact_paths.target_mode_multi_slice_summary_json_path(run_id)
        summary_csv_path = artifact_paths.target_mode_multi_slice_summary_csv_path(run_id)
        bucket_ranking_json_path = artifact_paths.target_mode_multi_slice_bucket_ranking_json_path(run_id)
        bucket_ranking_csv_path = artifact_paths.target_mode_multi_slice_bucket_ranking_csv_path(run_id)
        residual_examples_json_path = artifact_paths.target_mode_multi_slice_residual_examples_json_path(run_id)
        residual_examples_csv_path = artifact_paths.target_mode_multi_slice_residual_examples_csv_path(run_id)
        stability_gate_json_path = artifact_paths.target_mode_shadow_stability_gate_json_path(run_id)
        manifest_path = artifact_paths.target_mode_multi_slice_manifest_json_path(run_id)
        for path in (
            summary_json_path,
            summary_csv_path,
            bucket_ranking_json_path,
            bucket_ranking_csv_path,
            residual_examples_json_path,
            residual_examples_csv_path,
            stability_gate_json_path,
            manifest_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        slice_rows: list[dict[str, object]] = []
        bucket_records: list[dict[str, object]] = []
        residual_records: list[dict[str, object]] = []
        slice_run_artifact_paths: list[dict[str, str]] = []
        for slice_index, slice_spec in enumerate(slice_specs, start=1):
            dataset_path = Path(str(slice_spec["dataset_path"]))
            if not dataset_path.exists():
                raise FileNotFoundError(f"multi-slice target-mode input dataset not found: {dataset_path}")
            dataset = pd.read_parquet(dataset_path)
            child_run_id = f"{run_id}__slice_{slice_index:02d}_{_target_mode_slug(str(slice_spec['slice_identifier']))}"
            training_artifacts = self._trainer.train(
                run_id=child_run_id,
                dataset=dataset,
                dataset_path=str(dataset_path),
                artifact_paths=artifact_paths,
                target_mode=resolved_target_mode,
            )
            target_mode_paths = training_artifacts.target_mode_artifact_paths or {}
            target_contract_paths = training_artifacts.target_contract_artifact_paths or {}
            _require_target_mode_slice_artifact_paths(target_mode_paths, target_contract_paths)
            target_mode_summary_payload = read_json(Path(target_mode_paths["summary_json_path"]))
            slice_gate_payload = read_json(Path(target_mode_paths["promotion_gate_json_path"]))
            target_mode_bucket_payload = read_json(Path(target_mode_paths["bucket_ranking_json_path"]))
            target_mode_residual_payload = read_json(Path(target_mode_paths["residual_examples_json_path"]))
            trainer_manifest_payload = read_json(Path(training_artifacts.manifest_path))

            slice_row = _target_mode_multi_slice_summary_row(
                slice_index=slice_index,
                slice_spec=slice_spec,
                child_run_id=child_run_id,
                training_manifest_payload=trainer_manifest_payload,
                target_mode_summary_payload=target_mode_summary_payload,
                slice_gate_payload=slice_gate_payload,
                target_mode_paths=target_mode_paths,
                target_contract_paths=target_contract_paths,
            )
            slice_rows.append(slice_row)
            slice_run_artifact_paths.append(
                {
                    "slice_identifier": str(slice_spec["slice_identifier"]),
                    "child_run_id": child_run_id,
                    "manifest_path": training_artifacts.manifest_path,
                    "target_mode_summary_json_path": target_mode_paths["summary_json_path"],
                    "target_contract_promotion_gate_json_path": target_mode_paths["promotion_gate_json_path"],
                }
            )
            for bucket_row in target_mode_bucket_payload.get("ranking_rows", []):
                if isinstance(bucket_row, dict):
                    bucket_records.append(
                        {
                            **bucket_row,
                            "slice_identifier": str(slice_spec["slice_identifier"]),
                            "child_run_id": child_run_id,
                        }
                    )
            for residual_row in target_mode_residual_payload.get("rows", []):
                if isinstance(residual_row, dict):
                    residual_records.append(
                        {
                            **residual_row,
                            "slice_identifier": str(slice_spec["slice_identifier"]),
                            "child_run_id": child_run_id,
                        }
                    )

        artifacts = _build_target_mode_multi_slice_artifacts(
            run_id=run_id,
            target_mode=resolved_target_mode,
            slice_rows=slice_rows,
            bucket_records=bucket_records,
            residual_records=residual_records,
            slice_run_artifact_paths=slice_run_artifact_paths,
        )
        artifacts["summary_frame"].to_csv(summary_csv_path, index=False)
        artifacts["bucket_ranking_frame"].to_csv(bucket_ranking_csv_path, index=False)
        artifacts["residual_examples_frame"].to_csv(residual_examples_csv_path, index=False)
        write_json(summary_json_path, artifacts["summary_payload"])
        write_json(bucket_ranking_json_path, artifacts["bucket_ranking_payload"])
        write_json(residual_examples_json_path, artifacts["residual_examples_payload"])
        write_json(stability_gate_json_path, artifacts["stability_gate_payload"])
        write_json(
            manifest_path,
            {
                "run_id": run_id,
                "target_mode": resolved_target_mode,
                "artifact_root": str(artifact_root),
                "summary_json_path": str(summary_json_path),
                "summary_csv_path": str(summary_csv_path),
                "bucket_ranking_json_path": str(bucket_ranking_json_path),
                "bucket_ranking_csv_path": str(bucket_ranking_csv_path),
                "residual_examples_json_path": str(residual_examples_json_path),
                "residual_examples_csv_path": str(residual_examples_csv_path),
                "stability_gate_json_path": str(stability_gate_json_path),
                "slice_count": len(slice_rows),
                "slice_runs": slice_run_artifact_paths,
                "gate_inputs": artifacts["stability_gate_payload"]["gate_inputs"],
                "gate_outcome": artifacts["stability_gate_payload"],
            },
        )
        return PromotionTargetModeMultiSliceArtifacts(
            artifact_root=str(artifact_root),
            manifest_path=str(manifest_path),
            summary_json_path=str(summary_json_path),
            summary_csv_path=str(summary_csv_path),
            bucket_ranking_json_path=str(bucket_ranking_json_path),
            bucket_ranking_csv_path=str(bucket_ranking_csv_path),
            residual_examples_json_path=str(residual_examples_json_path),
            residual_examples_csv_path=str(residual_examples_csv_path),
            stability_gate_json_path=str(stability_gate_json_path),
            stability_gate=artifacts["stability_gate_payload"],
            slice_run_artifact_paths=tuple(slice_run_artifact_paths),
        )


class PromotionTargetContractDesignEvaluator:
    """Build governed target-design diagnostics from completed multi-slice shadow evidence."""

    def evaluate(
        self,
        *,
        run_id: str,
        multi_slice_manifest_path: str | Path | None = None,
        slice_inputs: Sequence[str | Path] = (),
        artifact_paths: PromotionArtifactPaths,
    ) -> PromotionTargetContractDesignArtifacts:
        has_multi_slice_manifest = multi_slice_manifest_path is not None
        has_slice_inputs = bool(slice_inputs)
        if has_multi_slice_manifest == has_slice_inputs:
            raise ValueError(
                "target contract design evaluator requires exactly one of multi_slice_manifest_path or slice_inputs"
            )
        if has_multi_slice_manifest:
            source_manifest_path_obj = Path(str(multi_slice_manifest_path)).expanduser()
            if not source_manifest_path_obj.exists():
                raise FileNotFoundError(
                    f"target contract design source manifest not found: {source_manifest_path_obj}"
                )
            source_manifest_path = str(source_manifest_path_obj.resolve())
            source_manifest_payload = read_json(source_manifest_path_obj)
            source_rows = _load_target_contract_design_source_rows(
                source_manifest_payload,
                source_manifest_path=source_manifest_path_obj,
            )
        else:
            evaluator_inputs = _resolve_target_contract_design_evaluator_inputs(
                multi_slice_manifest_path=multi_slice_manifest_path,
                slice_inputs=slice_inputs,
            )
            source_manifest_path = str(evaluator_inputs["source_manifest_path"])
            source_manifest_payload = evaluator_inputs["source_manifest_payload"]
            if not isinstance(source_manifest_payload, dict):
                raise ValueError("target contract design evaluator resolved invalid source manifest payload")
            source_rows = evaluator_inputs["source_rows"]
            if not isinstance(source_rows, pd.DataFrame):
                raise ValueError("target contract design evaluator resolved invalid source rows")

        artifact_root = artifact_paths.model_family_root(run_id)
        artifact_root.mkdir(parents=True, exist_ok=True)
        summary_json_path = artifact_paths.target_contract_design_summary_json_path(run_id)
        summary_csv_path = artifact_paths.target_contract_design_summary_csv_path(run_id)
        bucket_ranking_json_path = artifact_paths.target_contract_design_bucket_ranking_json_path(run_id)
        bucket_ranking_csv_path = artifact_paths.target_contract_design_bucket_ranking_csv_path(run_id)
        residual_examples_json_path = artifact_paths.target_contract_design_residual_examples_json_path(run_id)
        residual_examples_csv_path = artifact_paths.target_contract_design_residual_examples_csv_path(run_id)
        proposal_json_path = artifact_paths.target_contract_design_proposal_json_path(run_id)
        for path in (
            summary_json_path,
            summary_csv_path,
            bucket_ranking_json_path,
            bucket_ranking_csv_path,
            residual_examples_json_path,
            residual_examples_csv_path,
            proposal_json_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        artifacts = _build_target_contract_design_artifacts(
            run_id=run_id,
            source_manifest_path=source_manifest_path,
            source_manifest_payload=source_manifest_payload,
            source_rows=source_rows,
        )
        artifacts["summary_frame"].to_csv(summary_csv_path, index=False)
        artifacts["bucket_ranking_frame"].to_csv(bucket_ranking_csv_path, index=False)
        artifacts["residual_examples_frame"].to_csv(residual_examples_csv_path, index=False)
        write_json(summary_json_path, artifacts["summary_payload"])
        write_json(bucket_ranking_json_path, artifacts["bucket_ranking_payload"])
        write_json(residual_examples_json_path, artifacts["residual_examples_payload"])
        write_json(proposal_json_path, artifacts["proposal_payload"])
        return PromotionTargetContractDesignArtifacts(
            artifact_root=str(artifact_root),
            summary_json_path=str(summary_json_path),
            summary_csv_path=str(summary_csv_path),
            bucket_ranking_json_path=str(bucket_ranking_json_path),
            bucket_ranking_csv_path=str(bucket_ranking_csv_path),
            residual_examples_json_path=str(residual_examples_json_path),
            residual_examples_csv_path=str(residual_examples_csv_path),
            proposal_json_path=str(proposal_json_path),
            proposal=artifacts["proposal_payload"],
        )


class PromotionTargetDesignRepeatedEvidenceRunner:
    """Extend target-design evidence across discovered completed slices without changing live training."""

    def run(
        self,
        *,
        run_id: str,
        discovery_inputs: Sequence[str | Path],
        artifact_paths: PromotionArtifactPaths,
        target_design_candidate: str = _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE,
    ) -> PromotionTargetDesignRepeatedEvidenceArtifacts:
        if target_design_candidate != _TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE:
            raise ValueError(
                "target design repeated evidence currently governs only "
                f"{_TARGET_DESIGN_REPEATED_EVIDENCE_CANDIDATE!r}"
            )
        artifact_root = artifact_paths.model_family_root(run_id)
        artifact_root.mkdir(parents=True, exist_ok=True)
        inventory_json_path = artifact_paths.completed_slice_inventory_json_path(run_id)
        inventory_csv_path = artifact_paths.completed_slice_inventory_csv_path(run_id)
        summary_json_path = artifact_paths.target_design_repeated_evidence_summary_json_path(run_id)
        summary_csv_path = artifact_paths.target_design_repeated_evidence_summary_csv_path(run_id)
        gate_json_path = artifact_paths.target_design_repeated_evidence_gate_json_path(run_id)
        residual_examples_json_path = artifact_paths.target_design_repeated_evidence_residual_examples_json_path(run_id)
        residual_examples_csv_path = artifact_paths.target_design_repeated_evidence_residual_examples_csv_path(run_id)
        manifest_json_path = artifact_paths.target_design_repeated_evidence_manifest_json_path(run_id)
        for path in (
            inventory_json_path,
            inventory_csv_path,
            summary_json_path,
            summary_csv_path,
            gate_json_path,
            residual_examples_json_path,
            residual_examples_csv_path,
            manifest_json_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        inventory_frame = _build_completed_slice_inventory_frame(discovery_inputs)
        if inventory_frame.empty:
            raise ValueError("target design repeated evidence discovery found no completed-slice candidates")
        included = inventory_frame.loc[inventory_frame["included"].astype(bool)].copy()
        if included.empty:
            inventory_frame.to_csv(inventory_csv_path, index=False)
            write_json(inventory_json_path, _completed_slice_inventory_payload(run_id, inventory_frame))
            raise ValueError("target design repeated evidence has no included completed slices after governance filtering")
        inventory_frame.to_csv(inventory_csv_path, index=False)
        write_json(inventory_json_path, _completed_slice_inventory_payload(run_id, inventory_frame))

        target_mode_run_id = f"{run_id}__multi_slice_shadow"
        target_mode_artifacts = PromotionTargetModeShadowEvaluator().evaluate(
            run_id=target_mode_run_id,
            slice_inputs=tuple(included["slice_input_path"].astype(str).tolist()),
            artifact_paths=artifact_paths,
            target_mode="dual_contract_diagnostics",
        )
        target_design_run_id = f"{run_id}__target_contract_design"
        target_design_artifacts = PromotionTargetContractDesignEvaluator().evaluate(
            run_id=target_design_run_id,
            multi_slice_manifest_path=target_mode_artifacts.manifest_path,
            artifact_paths=artifact_paths,
        )

        summary_frame = _build_target_design_repeated_evidence_summary_frame(
            target_mode_summary_payload=read_json(Path(target_mode_artifacts.summary_json_path)),
            target_design_summary_payload=read_json(Path(target_design_artifacts.summary_json_path)),
            target_design_candidate=target_design_candidate,
        )
        gate_payload = _build_target_design_repeated_evidence_gate_payload(
            summary_frame,
            target_design_candidate=target_design_candidate,
        )
        residual_examples_frame = _build_target_design_repeated_evidence_residual_examples(
            target_design_residual_payload=read_json(Path(target_design_artifacts.residual_examples_json_path)),
            target_design_candidate=target_design_candidate,
        )
        summary_frame.to_csv(summary_csv_path, index=False)
        residual_examples_frame.to_csv(residual_examples_csv_path, index=False)
        write_json(
            summary_json_path,
            {
                "run_id": run_id,
                "row_scope": "out_of_sample_validation_and_test_by_completed_slice",
                "target_design_candidate": target_design_candidate,
                "slice_count": int(len(summary_frame.index)),
                "summary_rows": _json_ready_records(summary_frame),
                "gate": gate_payload,
                "current_trainer_contract_remains_live_default": True,
                "production_training_target_was_replaced": False,
                "policy_remains_paused": True,
                "stage_11_was_changed": False,
                "store_facing_csv_was_changed": False,
            },
        )
        write_json(gate_json_path, gate_payload)
        write_json(
            residual_examples_json_path,
            {
                "run_id": run_id,
                "row_scope": "out_of_sample_validation_and_test_by_completed_slice",
                "target_design_candidate": target_design_candidate,
                "top_row_limit": _TARGET_DESIGN_REPEATED_RESIDUAL_ROW_LIMIT,
                "row_count": int(len(residual_examples_frame.index)),
                "rows": _json_ready_records(residual_examples_frame),
            },
        )
        write_json(
            manifest_json_path,
            {
                "run_id": run_id,
                "artifact_root": str(artifact_root),
                "target_design_candidate": target_design_candidate,
                "inventory_json_path": str(inventory_json_path),
                "inventory_csv_path": str(inventory_csv_path),
                "summary_json_path": str(summary_json_path),
                "summary_csv_path": str(summary_csv_path),
                "gate_json_path": str(gate_json_path),
                "residual_examples_json_path": str(residual_examples_json_path),
                "residual_examples_csv_path": str(residual_examples_csv_path),
                "target_mode_multi_slice_manifest_path": target_mode_artifacts.manifest_path,
                "target_contract_design_proposal_path": target_design_artifacts.proposal_json_path,
                "included_slice_count": int(len(included.index)),
                "discovered_slice_count": int(len(inventory_frame.index)),
                "gate_outcome": gate_payload,
                "current_trainer_contract_remains_live_default": True,
                "production_training_target_was_replaced": False,
                "policy_remains_paused": True,
                "stage_11_was_changed": False,
                "store_facing_csv_was_changed": False,
            },
        )
        return PromotionTargetDesignRepeatedEvidenceArtifacts(
            artifact_root=str(artifact_root),
            inventory_json_path=str(inventory_json_path),
            inventory_csv_path=str(inventory_csv_path),
            summary_json_path=str(summary_json_path),
            summary_csv_path=str(summary_csv_path),
            gate_json_path=str(gate_json_path),
            residual_examples_json_path=str(residual_examples_json_path),
            residual_examples_csv_path=str(residual_examples_csv_path),
            manifest_json_path=str(manifest_json_path),
            target_mode_multi_slice_manifest_path=target_mode_artifacts.manifest_path,
            target_contract_design_proposal_path=target_design_artifacts.proposal_json_path,
            gate=gate_payload,
        )


class PromotionTargetContractThreeWayEvaluator:
    """Compare current, historical, and top design contracts on the same completed-slice evidence."""

    def evaluate(
        self,
        *,
        run_id: str,
        repeated_evidence_manifest_path: str | Path,
        artifact_paths: PromotionArtifactPaths,
    ) -> PromotionTargetContractThreeWayArtifacts:
        source_manifest_path = Path(repeated_evidence_manifest_path).expanduser().resolve()
        if not source_manifest_path.exists():
            raise FileNotFoundError(
                "target contract three-way comparison source repeated-evidence manifest not found: "
                f"{source_manifest_path}"
            )
        source_manifest_payload = read_json(source_manifest_path)
        source_multi_slice_manifest_value = source_manifest_payload.get("target_mode_multi_slice_manifest_path")
        if not isinstance(source_multi_slice_manifest_value, str) or not source_multi_slice_manifest_value:
            raise ValueError(
                "target contract three-way comparison requires target_mode_multi_slice_manifest_path evidence: "
                f"{source_manifest_path}"
            )
        source_multi_slice_manifest_path = _resolve_target_contract_design_existing_path(
            source_multi_slice_manifest_value,
            base_path=source_manifest_path.parent,
        )
        source_design_proposal_value = source_manifest_payload.get("target_contract_design_proposal_path")
        if not isinstance(source_design_proposal_value, str) or not source_design_proposal_value:
            raise ValueError(
                "target contract three-way comparison requires target_contract_design_proposal_path evidence: "
                f"{source_manifest_path}"
            )
        source_design_proposal_path = _resolve_target_contract_design_existing_path(
            source_design_proposal_value,
            base_path=source_manifest_path.parent,
        )
        source_rows = _load_target_contract_design_source_rows(
            read_json(source_multi_slice_manifest_path),
            source_manifest_path=source_multi_slice_manifest_path,
        )
        artifacts = _build_target_contract_three_way_artifacts(
            run_id=run_id,
            source_repeated_evidence_manifest_path=str(source_manifest_path),
            source_repeated_evidence_manifest_payload=source_manifest_payload,
            source_design_proposal_path=str(source_design_proposal_path),
            source_design_proposal_payload=read_json(source_design_proposal_path),
            source_rows=source_rows,
        )

        artifact_root = artifact_paths.model_family_root(run_id)
        artifact_root.mkdir(parents=True, exist_ok=True)
        summary_json_path = artifact_paths.target_contract_three_way_summary_json_path(run_id)
        summary_csv_path = artifact_paths.target_contract_three_way_summary_csv_path(run_id)
        bucket_ranking_json_path = artifact_paths.target_contract_three_way_bucket_ranking_json_path(run_id)
        bucket_ranking_csv_path = artifact_paths.target_contract_three_way_bucket_ranking_csv_path(run_id)
        residual_examples_json_path = artifact_paths.target_contract_three_way_residual_examples_json_path(run_id)
        residual_examples_csv_path = artifact_paths.target_contract_three_way_residual_examples_csv_path(run_id)
        proposal_json_path = artifact_paths.target_contract_three_way_proposal_json_path(run_id)
        manifest_json_path = artifact_paths.target_contract_three_way_manifest_json_path(run_id)
        for path in (
            summary_json_path,
            summary_csv_path,
            bucket_ranking_json_path,
            bucket_ranking_csv_path,
            residual_examples_json_path,
            residual_examples_csv_path,
            proposal_json_path,
            manifest_json_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        artifacts["summary_frame"].to_csv(summary_csv_path, index=False)
        artifacts["bucket_ranking_frame"].to_csv(bucket_ranking_csv_path, index=False)
        artifacts["residual_examples_frame"].to_csv(residual_examples_csv_path, index=False)
        write_json(summary_json_path, artifacts["summary_payload"])
        write_json(bucket_ranking_json_path, artifacts["bucket_ranking_payload"])
        write_json(residual_examples_json_path, artifacts["residual_examples_payload"])
        write_json(proposal_json_path, artifacts["proposal_payload"])
        manifest_payload = dict(artifacts["manifest_payload"])
        manifest_payload.update(
            {
                "artifact_root": str(artifact_root),
                "summary_json_path": str(summary_json_path),
                "summary_csv_path": str(summary_csv_path),
                "bucket_ranking_json_path": str(bucket_ranking_json_path),
                "bucket_ranking_csv_path": str(bucket_ranking_csv_path),
                "residual_examples_json_path": str(residual_examples_json_path),
                "residual_examples_csv_path": str(residual_examples_csv_path),
                "proposal_json_path": str(proposal_json_path),
                "manifest_json_path": str(manifest_json_path),
            }
        )
        write_json(manifest_json_path, manifest_payload)
        return PromotionTargetContractThreeWayArtifacts(
            artifact_root=str(artifact_root),
            summary_json_path=str(summary_json_path),
            summary_csv_path=str(summary_csv_path),
            bucket_ranking_json_path=str(bucket_ranking_json_path),
            bucket_ranking_csv_path=str(bucket_ranking_csv_path),
            residual_examples_json_path=str(residual_examples_json_path),
            residual_examples_csv_path=str(residual_examples_csv_path),
            proposal_json_path=str(proposal_json_path),
            manifest_json_path=str(manifest_json_path),
            proposal=artifacts["proposal_payload"],
        )


class PromotionTargetPromotionReadinessEvaluator:
    """Aggregate governed readiness evidence into a diagnostics-only shadow-promotion packet."""

    def evaluate(
        self,
        *,
        run_id: str,
        repeated_evidence_manifest_path: str | Path,
        artifact_paths: PromotionArtifactPaths,
        target_contract_three_way_manifest_path: str | Path | None = None,
        target_contract_three_way_summary_path: str | Path | None = None,
        target_contract_three_way_proposal_path: str | Path | None = None,
        target_contract_three_way_residual_examples_path: str | Path | None = None,
    ) -> PromotionTargetPromotionReadinessArtifacts:
        source_manifest_path = Path(repeated_evidence_manifest_path).expanduser().resolve()
        if not source_manifest_path.exists():
            raise FileNotFoundError(
                "promotion readiness source repeated-evidence manifest not found: "
                f"{source_manifest_path}"
            )
        source_manifest_payload = read_json(source_manifest_path)
        gate_outcome = source_manifest_payload.get("gate_outcome")
        if not isinstance(gate_outcome, dict):
            raise ValueError(
                "promotion readiness requires repeated-evidence gate_outcome evidence: "
                f"{source_manifest_path}"
            )
        source_multi_slice_manifest_value = source_manifest_payload.get("target_mode_multi_slice_manifest_path")
        if not isinstance(source_multi_slice_manifest_value, str) or not source_multi_slice_manifest_value:
            raise ValueError(
                "promotion readiness requires target_mode_multi_slice_manifest_path evidence: "
                f"{source_manifest_path}"
            )
        source_multi_slice_manifest_path = _resolve_target_contract_design_existing_path(
            source_multi_slice_manifest_value,
            base_path=source_manifest_path.parent,
        )
        source_multi_slice_manifest_payload = read_json(source_multi_slice_manifest_path)
        stability_gate = source_multi_slice_manifest_payload.get("stability_gate")
        if not isinstance(stability_gate, dict):
            gate_outcome = source_multi_slice_manifest_payload.get("gate_outcome")
            if isinstance(gate_outcome, dict):
                stability_gate = gate_outcome
        if not isinstance(stability_gate, dict):
            stability_gate_path_value = source_multi_slice_manifest_payload.get("stability_gate_json_path")
            if isinstance(stability_gate_path_value, str) and stability_gate_path_value:
                stability_gate_path = _resolve_target_contract_design_existing_path(
                    stability_gate_path_value,
                    base_path=source_multi_slice_manifest_path.parent,
                )
                stability_gate = read_json(stability_gate_path)
        if not isinstance(stability_gate, dict):
            raise ValueError(
                "promotion readiness requires multi-slice stability_gate evidence: "
                f"{source_multi_slice_manifest_path}"
            )
        normalized_multi_slice_manifest_payload = dict(source_multi_slice_manifest_payload)
        normalized_multi_slice_manifest_payload["stability_gate"] = stability_gate
        source_design_proposal_value = source_manifest_payload.get("target_contract_design_proposal_path")
        if not isinstance(source_design_proposal_value, str) or not source_design_proposal_value:
            raise ValueError(
                "promotion readiness requires target_contract_design_proposal_path evidence: "
                f"{source_manifest_path}"
            )
        source_design_proposal_path = _resolve_target_contract_design_existing_path(
            source_design_proposal_value,
            base_path=source_manifest_path.parent,
        )
        source_design_proposal_payload = read_json(source_design_proposal_path)

        three_way_source = _load_promotion_readiness_three_way_source(
            run_id=run_id,
            source_repeated_evidence_manifest_path=source_manifest_path,
            source_repeated_evidence_manifest_payload=source_manifest_payload,
            source_multi_slice_manifest_path=source_multi_slice_manifest_path,
            source_multi_slice_manifest_payload=source_multi_slice_manifest_payload,
            source_design_proposal_path=source_design_proposal_path,
            source_design_proposal_payload=source_design_proposal_payload,
            target_contract_three_way_manifest_path=target_contract_three_way_manifest_path,
            target_contract_three_way_summary_path=target_contract_three_way_summary_path,
            target_contract_three_way_proposal_path=target_contract_three_way_proposal_path,
            target_contract_three_way_residual_examples_path=target_contract_three_way_residual_examples_path,
        )
        artifacts = _build_promotion_readiness_artifacts(
            run_id=run_id,
            source_repeated_evidence_manifest_path=str(source_manifest_path),
            source_repeated_evidence_manifest_payload=source_manifest_payload,
            source_target_mode_multi_slice_manifest_path=str(source_multi_slice_manifest_path),
            source_target_mode_multi_slice_manifest_payload=normalized_multi_slice_manifest_payload,
            source_target_contract_design_proposal_path=str(source_design_proposal_path),
            source_target_contract_design_proposal_payload=source_design_proposal_payload,
            source_target_contract_three_way_manifest_path=three_way_source["source_target_contract_three_way_manifest_path"],
            source_target_contract_three_way_proposal_path=three_way_source["source_target_contract_three_way_proposal_path"],
            source_target_contract_three_way_proposal_payload=three_way_source["proposal_payload"],
            source_target_contract_three_way_residual_examples_path=three_way_source[
                "source_target_contract_three_way_residual_examples_path"
            ],
            source_target_contract_three_way_residual_examples_payload=three_way_source[
                "residual_examples_payload"
            ],
            used_existing_three_way_evidence=bool(three_way_source["used_existing_three_way_evidence"]),
        )

        artifact_root = artifact_paths.model_family_root(run_id)
        artifact_root.mkdir(parents=True, exist_ok=True)
        scoreboard_json_path = artifact_paths.promotion_readiness_scoreboard_json_path(run_id)
        scoreboard_csv_path = artifact_paths.promotion_readiness_scoreboard_csv_path(run_id)
        blocker_ranking_json_path = artifact_paths.promotion_readiness_blocker_ranking_json_path(run_id)
        residual_examples_json_path = artifact_paths.promotion_readiness_residual_examples_json_path(run_id)
        decision_packet_json_path = artifact_paths.promotion_readiness_decision_packet_json_path(run_id)
        for path in (
            scoreboard_json_path,
            scoreboard_csv_path,
            blocker_ranking_json_path,
            residual_examples_json_path,
            decision_packet_json_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        artifacts["scoreboard_frame"].to_csv(scoreboard_csv_path, index=False)
        write_json(scoreboard_json_path, artifacts["scoreboard_payload"])
        write_json(blocker_ranking_json_path, artifacts["blocker_ranking_payload"])
        write_json(residual_examples_json_path, artifacts["residual_examples_payload"])
        write_json(decision_packet_json_path, artifacts["decision_packet"])
        return PromotionTargetPromotionReadinessArtifacts(
            artifact_root=str(artifact_root),
            scoreboard_json_path=str(scoreboard_json_path),
            scoreboard_csv_path=str(scoreboard_csv_path),
            blocker_ranking_json_path=str(blocker_ranking_json_path),
            residual_examples_json_path=str(residual_examples_json_path),
            decision_packet_json_path=str(decision_packet_json_path),
            decision_packet=artifacts["decision_packet"],
        )


class PromotionTargetWeakSliceRepairPlanner:
    """Plan diagnostics-only governed repairs for completed slices blocking readiness."""

    def evaluate(
        self,
        *,
        run_id: str,
        source_target_mode_multi_slice_manifest_path: str | Path,
        artifact_paths: PromotionArtifactPaths,
        source_target_contract_three_way_runtime_manifest_path: str | Path | None = None,
        source_target_contract_three_way_proposal_path: str | Path | None = None,
        source_promotion_readiness_runtime_manifest_path: str | Path | None = None,
        source_promotion_readiness_decision_packet_path: str | Path | None = None,
        source_promotion_readiness_blocker_ranking_path: str | Path | None = None,
    ) -> PromotionTargetWeakSliceRepairArtifacts:
        multi_slice_source = _load_weak_slice_repair_multi_slice_source(
            source_target_mode_multi_slice_manifest_path,
        )
        promotion_readiness_decision_packet_payload = _load_optional_weak_slice_repair_json_payload(
            source_promotion_readiness_decision_packet_path,
            context_label="promotion readiness decision packet",
        )
        promotion_readiness_blocker_ranking_payload = _load_optional_weak_slice_repair_json_payload(
            source_promotion_readiness_blocker_ranking_path,
            context_label="promotion readiness blocker ranking",
        )
        three_way_proposal_payload = _load_optional_weak_slice_repair_json_payload(
            source_target_contract_three_way_proposal_path,
            context_label="target contract three-way proposal",
        )
        artifacts = _build_weak_slice_repair_artifacts(
            run_id=run_id,
            source_target_mode_multi_slice_manifest_path=str(multi_slice_source["manifest_path"]),
            source_target_mode_multi_slice_manifest_payload=multi_slice_source["manifest_payload"],
            source_target_mode_multi_slice_summary_path=str(multi_slice_source["summary_path"]),
            source_target_mode_multi_slice_summary_payload=multi_slice_source["summary_payload"],
            source_target_mode_multi_slice_residual_examples_path=(
                None
                if multi_slice_source["residual_examples_path"] is None
                else str(multi_slice_source["residual_examples_path"])
            ),
            source_target_mode_multi_slice_residual_examples_payload=multi_slice_source["residual_examples_payload"],
            source_promotion_readiness_runtime_manifest_path=(
                None
                if source_promotion_readiness_runtime_manifest_path is None
                else str(Path(source_promotion_readiness_runtime_manifest_path).expanduser().resolve())
            ),
            source_promotion_readiness_decision_packet_path=(
                None
                if source_promotion_readiness_decision_packet_path is None
                else str(Path(source_promotion_readiness_decision_packet_path).expanduser().resolve())
            ),
            source_promotion_readiness_decision_packet_payload=promotion_readiness_decision_packet_payload,
            source_promotion_readiness_blocker_ranking_path=(
                None
                if source_promotion_readiness_blocker_ranking_path is None
                else str(Path(source_promotion_readiness_blocker_ranking_path).expanduser().resolve())
            ),
            source_promotion_readiness_blocker_ranking_payload=promotion_readiness_blocker_ranking_payload,
            source_target_contract_three_way_runtime_manifest_path=(
                None
                if source_target_contract_three_way_runtime_manifest_path is None
                else str(Path(source_target_contract_three_way_runtime_manifest_path).expanduser().resolve())
            ),
            source_target_contract_three_way_proposal_path=(
                None
                if source_target_contract_three_way_proposal_path is None
                else str(Path(source_target_contract_three_way_proposal_path).expanduser().resolve())
            ),
            source_target_contract_three_way_proposal_payload=three_way_proposal_payload,
        )

        artifact_root = artifact_paths.model_family_root(run_id)
        artifact_root.mkdir(parents=True, exist_ok=True)
        summary_json_path = artifact_paths.weak_slice_repair_summary_json_path(run_id)
        summary_csv_path = artifact_paths.weak_slice_repair_summary_csv_path(run_id)
        plan_json_path = artifact_paths.weak_slice_repair_plan_json_path(run_id)
        plan_csv_path = artifact_paths.weak_slice_repair_plan_csv_path(run_id)
        residual_examples_json_path = artifact_paths.weak_slice_repair_residual_examples_json_path(run_id)
        decision_packet_json_path = artifact_paths.weak_slice_repair_decision_packet_json_path(run_id)
        for path in (
            summary_json_path,
            summary_csv_path,
            plan_json_path,
            plan_csv_path,
            residual_examples_json_path,
            decision_packet_json_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        artifacts["summary_frame"].to_csv(summary_csv_path, index=False)
        artifacts["plan_frame"].to_csv(plan_csv_path, index=False)
        write_json(summary_json_path, artifacts["summary_payload"])
        write_json(plan_json_path, artifacts["plan_payload"])
        write_json(residual_examples_json_path, artifacts["residual_examples_payload"])
        write_json(decision_packet_json_path, artifacts["decision_packet"])
        return PromotionTargetWeakSliceRepairArtifacts(
            artifact_root=str(artifact_root),
            summary_json_path=str(summary_json_path),
            summary_csv_path=str(summary_csv_path),
            plan_json_path=str(plan_json_path),
            plan_csv_path=str(plan_csv_path),
            residual_examples_json_path=str(residual_examples_json_path),
            decision_packet_json_path=str(decision_packet_json_path),
            decision_packet=artifacts["decision_packet"],
        )


def _safe_roc_auc(target: pd.Series, probabilities: np.ndarray) -> float:
    unique_values = pd.Series(target).dropna().unique().tolist()
    if len(unique_values) < 2:
        return 0.5
    return float(roc_auc_score(target, probabilities))


def _safe_r2(target: pd.Series, prediction: np.ndarray) -> float:
    if len(pd.Series(target).dropna()) < 2:
        return 0.0
    return float(r2_score(target, prediction))


def _build_allocation_split_diagnostic_rows(
    split_name: str,
    *,
    units_model: Pipeline,
    overallocation_model: Pipeline,
    features: pd.DataFrame,
    dataset: pd.DataFrame,
) -> pd.DataFrame:
    if len(features.index) == 0:
        return pd.DataFrame()
    raw_predicted_units = pd.Series(units_model.predict(features), index=features.index).clip(lower=0.0)
    allocation_cap_units = compute_allocation_aware_cap_units(dataset, raw_predicted_units)
    calibrated_predicted_units = raw_predicted_units.clip(lower=0.0)
    overallocation_probability = pd.Series(
        overallocation_model.predict_proba(features)[:, 1],
        index=features.index,
    )
    predicted_overallocation = overallocation_probability.ge(0.5)
    actual_overallocation = _metric_series(dataset, "target_overallocation_flag").ge(0.5)
    stock_basis = _metric_series(dataset, "stock_basis_units")
    demand_reference = _metric_series(dataset, "demand_reference_units")
    actual_units = _metric_series(dataset, "target_actual_units_sold")
    baseline_reference_units = _metric_series(dataset, "feature_expected_baseline_units_promo_window")
    if not baseline_reference_units.gt(0.0).any():
        baseline_reference_units = _metric_series(dataset, "feature_baseline_units_expected_promo_window")
    if not baseline_reference_units.gt(0.0).any():
        baseline_reference_units = _metric_series(dataset, "baseline_expected_units")
    unit_cost = _metric_series(dataset, "effective_cost_per_unit")
    unit_margin = (_metric_series(dataset, "promo_price_ex_gst_effective") - unit_cost).clip(lower=0.0)
    same_discount_history_available = _metric_series(dataset, "feature_same_discount_history_available_flag")
    elasticity_confidence_score = _metric_series(dataset, "feature_discount_elasticity_confidence_score")
    uplift_confidence_score = _metric_series(dataset, "feature_uplift_confidence_score")
    launch_total_conflict_score = _metric_series(dataset, "feature_total_window_pressure_vs_launch_support_conflict_score")
    stock_vs_supported_gap_units = _metric_series(dataset, "feature_allocation_vs_supported_total_gap_units")

    actual_excess_units = (stock_basis - actual_units).clip(lower=0.0)
    predicted_excess_units = (stock_basis - calibrated_predicted_units).clip(lower=0.0)
    raw_predicted_excess_units = (stock_basis - raw_predicted_units).clip(lower=0.0)
    actual_uplift_units = (actual_units - baseline_reference_units).clip(lower=0.0)
    predicted_uplift_units = (calibrated_predicted_units - baseline_reference_units).clip(lower=0.0)
    raw_predicted_uplift_units = (raw_predicted_units - baseline_reference_units).clip(lower=0.0)
    actual_excess_capital = actual_excess_units * unit_cost
    predicted_excess_capital = predicted_excess_units * unit_cost
    raw_predicted_excess_capital = raw_predicted_excess_units * unit_cost
    false_positive_mask = predicted_overallocation & ~actual_overallocation
    false_negative_mask = ~predicted_overallocation & actual_overallocation
    false_positive_missed_opportunity = (
        (actual_units - demand_reference).clip(lower=0.0) * unit_margin
    ).where(false_positive_mask, 0.0)
    false_negative_excess_capital = actual_excess_capital.where(false_negative_mask, 0.0)
    live_diagnostics = build_live_order_decision_diagnostics(
        dataset,
        raw_predicted_units=raw_predicted_units,
        predicted_units=calibrated_predicted_units,
    )
    policy_adjustments = build_order_policy_adjustments(
        dataset,
        raw_predicted_units=raw_predicted_units,
        calibrated_predicted_units=calibrated_predicted_units,
        diagnostics_frame=live_diagnostics,
    )
    policy_major_buckets = build_order_policy_major_bucket_frame(live_diagnostics)
    policy_rule_triggers = build_order_policy_rule_trigger_frame(
        dataset,
        diagnostics_frame=live_diagnostics,
    )
    policy_adjusted_units = pd.to_numeric(
        policy_adjustments["adjusted_order_cap_units"],
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    policy_adjusted_excess_units = (stock_basis - policy_adjusted_units).clip(lower=0.0)
    policy_adjusted_excess_capital = policy_adjusted_excess_units * unit_cost
    policy_replay_diagnostics = _build_policy_replay_diagnostic_frame(
        dataset,
        policy_adjustments=policy_adjustments,
    )
    target_historical_allocation_units = _optional_metric_series(
        dataset,
        "target_historical_allocation_units",
        fallback=policy_replay_diagnostics["historical_allocated_units"],
    )
    target_historical_replay_excess_units = _optional_metric_series(
        dataset,
        "target_historical_replay_excess_units",
        fallback=policy_replay_diagnostics["historical_excess_units"],
    )
    target_historical_replay_excess_capital = _optional_metric_series(
        dataset,
        "target_historical_replay_excess_capital",
        fallback=policy_replay_diagnostics["historical_excess_capital"],
    )
    target_historical_overallocation_flag = _optional_metric_series(
        dataset,
        "target_historical_overallocation_flag",
        fallback=policy_replay_diagnostics["historical_excess_units"].gt(0.0).astype(float),
    )
    target_historical_valid_flag = _optional_metric_series(
        dataset,
        "target_historical_allocation_target_valid_flag",
        fallback=policy_replay_diagnostics["replay_measurement_eligible_flag"],
    )
    return pd.concat(
        [
            live_diagnostics,
            policy_major_buckets,
            policy_adjustments,
            policy_rule_triggers,
            policy_replay_diagnostics,
            pd.DataFrame(
                {
                    "split_name": split_name,
                    "overallocation_probability": overallocation_probability,
                    "predicted_overallocation_flag": predicted_overallocation.astype(float),
                    "actual_overallocation_flag": actual_overallocation.astype(float),
                    "allocation_aware_units_cap_applied_flag": allocation_cap_units.lt(raw_predicted_units).astype(float),
                    "allocation_cap_units": allocation_cap_units,
                    "stock_basis_units": stock_basis,
                    "demand_reference_units": demand_reference,
                    "actual_units_sold": actual_units,
                    "unit_cost": unit_cost,
                    "raw_predicted_units_total_promo": raw_predicted_units,
                    "calibrated_predicted_units_total_promo": calibrated_predicted_units,
                    "policy_adjusted_predicted_units_total_promo": policy_adjusted_units,
                    "predicted_units_total_promo": calibrated_predicted_units,
                    "target_historical_allocation_units": target_historical_allocation_units,
                    "target_historical_replay_excess_units": target_historical_replay_excess_units,
                    "target_historical_replay_excess_capital": target_historical_replay_excess_capital,
                    "target_historical_overallocation_flag": target_historical_overallocation_flag,
                    "target_historical_allocation_target_valid_flag": target_historical_valid_flag,
                    "actual_excess_units": actual_excess_units,
                    "predicted_excess_units": predicted_excess_units,
                    "calibrated_predicted_excess_units": predicted_excess_units,
                    "raw_predicted_excess_units": raw_predicted_excess_units,
                    "policy_adjusted_excess_units": policy_adjusted_excess_units,
                    "excess_units_abs_error": (predicted_excess_units - actual_excess_units).abs(),
                    "calibrated_excess_units_abs_error": (predicted_excess_units - actual_excess_units).abs(),
                    "raw_excess_units_abs_error": (raw_predicted_excess_units - actual_excess_units).abs(),
                    "policy_adjusted_excess_units_abs_error": (policy_adjusted_excess_units - actual_excess_units).abs(),
                    "actual_uplift_units": actual_uplift_units,
                    "predicted_uplift_units": predicted_uplift_units,
                    "raw_predicted_uplift_units": raw_predicted_uplift_units,
                    "uplift_units_abs_error": (predicted_uplift_units - actual_uplift_units).abs(),
                    "raw_uplift_units_abs_error": (raw_predicted_uplift_units - actual_uplift_units).abs(),
                    "actual_excess_capital_at_risk": actual_excess_capital,
                    "predicted_excess_capital_at_risk": predicted_excess_capital,
                    "calibrated_predicted_excess_capital_at_risk": predicted_excess_capital,
                    "raw_predicted_excess_capital_at_risk": raw_predicted_excess_capital,
                    "policy_adjusted_excess_capital_at_risk": policy_adjusted_excess_capital,
                    "excess_capital_abs_error": (predicted_excess_capital - actual_excess_capital).abs(),
                    "calibrated_excess_capital_abs_error": (predicted_excess_capital - actual_excess_capital).abs(),
                    "raw_excess_capital_abs_error": (raw_predicted_excess_capital - actual_excess_capital).abs(),
                    "policy_adjusted_excess_capital_abs_error": (policy_adjusted_excess_capital - actual_excess_capital).abs(),
                    "false_positive_missed_opportunity_proxy": false_positive_missed_opportunity,
                    "false_negative_excess_capital_proxy": false_negative_excess_capital,
                    "same_discount_history_available_flag": same_discount_history_available,
                    "elasticity_confidence_score": elasticity_confidence_score,
                    "uplift_confidence_score": uplift_confidence_score,
                    "launch_vs_total_conflict_score": launch_total_conflict_score,
                    "stock_vs_supported_gap_units": stock_vs_supported_gap_units,
                },
                index=dataset.index,
            ),
        ],
        axis=1,
    )


def _allocation_split_metrics_from_rows(prefix: str, rows: pd.DataFrame) -> dict[str, object]:
    if rows.empty:
        return _empty_allocation_split_metrics(prefix)
    metrics: dict[str, object] = {
        f"{prefix}_allocation_aware_units_cap_count": float(rows["allocation_aware_units_cap_applied_flag"].sum()),
        f"{prefix}_policy_adjusted_row_count": float(pd.to_numeric(rows["policy_adjustment_fired_flag"], errors="coerce").sum()),
        f"{prefix}_policy_forced_review_row_count": float(pd.to_numeric(rows["review_override_flag"], errors="coerce").sum()),
        f"{prefix}_policy_units_removed_total": float(pd.to_numeric(rows["policy_units_removed"], errors="coerce").sum()),
        f"{prefix}_policy_capital_at_risk_removed_total": float(pd.to_numeric(rows["policy_capital_at_risk_removed"], errors="coerce").sum()),
        f"{prefix}_excess_units_mae_raw": float(rows["raw_excess_units_abs_error"].mean()),
        f"{prefix}_excess_units_mae_calibrated": float(rows["calibrated_excess_units_abs_error"].mean()),
        f"{prefix}_excess_units_mae_policy_adjusted": float(rows["policy_adjusted_excess_units_abs_error"].mean()),
        f"{prefix}_excess_capital_mae_raw": float(rows["raw_excess_capital_abs_error"].mean()),
        f"{prefix}_excess_capital_mae_calibrated": float(rows["calibrated_excess_capital_abs_error"].mean()),
        f"{prefix}_excess_capital_mae_policy_adjusted": float(rows["policy_adjusted_excess_capital_abs_error"].mean()),
        f"{prefix}_raw_excess_units_mae": float(rows["raw_excess_units_abs_error"].mean()),
        f"{prefix}_raw_excess_capital_at_risk_mae": float(rows["raw_excess_capital_abs_error"].mean()),
        f"{prefix}_excess_units_mae": float(rows["calibrated_excess_units_abs_error"].mean()),
        f"{prefix}_excess_capital_at_risk_mae": float(rows["calibrated_excess_capital_abs_error"].mean()),
        f"{prefix}_raw_uplift_units_mae": float(rows["raw_uplift_units_abs_error"].mean()),
        f"{prefix}_uplift_units_mae": float(rows["uplift_units_abs_error"].mean()),
        f"{prefix}_overallocation_false_positive_count": float(rows["predicted_overallocation_flag"].eq(1.0).sum() - (rows["predicted_overallocation_flag"].eq(1.0) & rows["actual_overallocation_flag"].eq(1.0)).sum()),
        f"{prefix}_overallocation_false_negative_count": float(rows["actual_overallocation_flag"].eq(1.0).sum() - (rows["predicted_overallocation_flag"].eq(1.0) & rows["actual_overallocation_flag"].eq(1.0)).sum()),
        f"{prefix}_overallocation_false_positive_cost_proxy": float(rows["false_positive_missed_opportunity_proxy"].sum()),
        f"{prefix}_overallocation_false_positive_missed_opportunity_proxy": float(rows["false_positive_missed_opportunity_proxy"].sum()),
        f"{prefix}_overallocation_false_negative_excess_capital_proxy": float(rows["false_negative_excess_capital_proxy"].sum()),
    }
    metrics.update(
        _allocation_calibration_metrics(
            prefix,
            probability=pd.to_numeric(rows["overallocation_probability"], errors="coerce"),
            target=pd.to_numeric(rows["actual_overallocation_flag"], errors="coerce").ge(0.5),
        )
    )
    metrics.update(
        {
            f"{prefix}_excess_units_mae_by_same_discount_history_bucket": _bucket_mae_map(
                rows,
                bucket_column="same_discount_history_bucket",
                bucket_order=SAME_DISCOUNT_HISTORY_BUCKET_ORDER,
                error_column="excess_units_abs_error",
            ),
            f"{prefix}_excess_capital_mae_by_same_discount_history_bucket": _bucket_mae_map(
                rows,
                bucket_column="same_discount_history_bucket",
                bucket_order=SAME_DISCOUNT_HISTORY_BUCKET_ORDER,
                error_column="excess_capital_abs_error",
            ),
            f"{prefix}_excess_units_mae_by_elasticity_confidence_bucket": _bucket_mae_map(
                rows,
                bucket_column="elasticity_confidence_bucket",
                bucket_order=CONFIDENCE_BUCKET_ORDER,
                error_column="excess_units_abs_error",
            ),
            f"{prefix}_excess_capital_mae_by_elasticity_confidence_bucket": _bucket_mae_map(
                rows,
                bucket_column="elasticity_confidence_bucket",
                bucket_order=CONFIDENCE_BUCKET_ORDER,
                error_column="excess_capital_abs_error",
            ),
            f"{prefix}_excess_units_mae_by_uplift_confidence_bucket": _bucket_mae_map(
                rows,
                bucket_column="uplift_confidence_bucket",
                bucket_order=CONFIDENCE_BUCKET_ORDER,
                error_column="excess_units_abs_error",
            ),
            f"{prefix}_excess_capital_mae_by_uplift_confidence_bucket": _bucket_mae_map(
                rows,
                bucket_column="uplift_confidence_bucket",
                bucket_order=CONFIDENCE_BUCKET_ORDER,
                error_column="excess_capital_abs_error",
            ),
            f"{prefix}_excess_units_mae_by_base_demand_growth_bucket": _bucket_mae_map(
                rows,
                bucket_column="base_demand_growth_bucket",
                bucket_order=BASE_DEMAND_GROWTH_BUCKET_ORDER,
                error_column="excess_units_abs_error",
            ),
            f"{prefix}_excess_capital_mae_by_base_demand_growth_bucket": _bucket_mae_map(
                rows,
                bucket_column="base_demand_growth_bucket",
                bucket_order=BASE_DEMAND_GROWTH_BUCKET_ORDER,
                error_column="excess_capital_abs_error",
            ),
            f"{prefix}_excess_units_mae_by_window_conflict_bucket": _bucket_mae_map(
                rows,
                bucket_column="window_conflict_bucket",
                bucket_order=WINDOW_CONFLICT_BUCKET_ORDER,
                error_column="excess_units_abs_error",
            ),
            f"{prefix}_excess_capital_mae_by_window_conflict_bucket": _bucket_mae_map(
                rows,
                bucket_column="window_conflict_bucket",
                bucket_order=WINDOW_CONFLICT_BUCKET_ORDER,
                error_column="excess_capital_abs_error",
            ),
        }
    )
    metrics[f"{prefix}_policy_metric_comparison_by_major_bucket"] = _major_policy_bucket_comparison(rows)
    return metrics


def _build_policy_replay_diagnostic_frame(
    dataset: pd.DataFrame,
    *,
    policy_adjustments: pd.DataFrame,
) -> pd.DataFrame:
    historical_allocated_units, historical_allocation_source = _first_present_nonnegative_numeric_series(
        dataset,
        _POLICY_REPLAY_HISTORICAL_ALLOCATION_COLUMNS,
    )
    realised_units_sold_promo, realised_units_source = _first_present_nonnegative_numeric_series(
        dataset,
        _POLICY_REPLAY_REALISED_PROMO_UNITS_COLUMNS,
    )
    replay_unit_cost, unit_cost_source = _first_present_nonnegative_numeric_series(
        dataset,
        _POLICY_REPLAY_UNIT_COST_COLUMNS,
    )

    missing_historical_allocation = historical_allocated_units.isna()
    missing_realised_units = realised_units_sold_promo.isna()
    missing_effective_cost = replay_unit_cost.isna()
    missing_input_count = (
        missing_historical_allocation.astype(int)
        + missing_realised_units.astype(int)
        + missing_effective_cost.astype(int)
    )
    replay_measurement_eligible = missing_input_count.eq(0)
    replay_exclusion_reason = pd.Series(
        _POLICY_REPLAY_EXCLUSION_REASON_ELIGIBLE,
        index=dataset.index,
        dtype="object",
    )
    replay_exclusion_reason = replay_exclusion_reason.mask(
        missing_input_count.gt(1),
        _POLICY_REPLAY_EXCLUSION_REASON_MULTIPLE_MISSING_INPUTS,
    )
    replay_exclusion_reason = replay_exclusion_reason.mask(
        missing_historical_allocation & missing_input_count.eq(1),
        _POLICY_REPLAY_EXCLUSION_REASON_MISSING_HISTORICAL_ALLOCATION,
    )
    replay_exclusion_reason = replay_exclusion_reason.mask(
        missing_realised_units & missing_input_count.eq(1),
        _POLICY_REPLAY_EXCLUSION_REASON_MISSING_REALISED_PROMO_UNITS,
    )
    replay_exclusion_reason = replay_exclusion_reason.mask(
        missing_effective_cost & missing_input_count.eq(1),
        _POLICY_REPLAY_EXCLUSION_REASON_MISSING_EFFECTIVE_COST,
    )

    policy_units_removed = pd.to_numeric(
        policy_adjustments.get("policy_units_removed", pd.Series(0.0, index=dataset.index)),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    replay_policy_units = (historical_allocated_units - policy_units_removed).clip(lower=0.0)
    historical_excess_units = (historical_allocated_units - realised_units_sold_promo).clip(lower=0.0)
    replay_policy_excess_units = (replay_policy_units - realised_units_sold_promo).clip(lower=0.0)
    historical_excess_capital = historical_excess_units * replay_unit_cost
    replay_policy_excess_capital = replay_policy_excess_units * replay_unit_cost
    replay_units_removed = (historical_excess_units - replay_policy_excess_units).clip(lower=0.0)
    replay_capital_removed = (historical_excess_capital - replay_policy_excess_capital).clip(lower=0.0)

    return pd.DataFrame(
        {
            "replay_measurement_eligible_flag": replay_measurement_eligible.astype(float),
            "replay_exclusion_reason": replay_exclusion_reason,
            "historical_allocated_units": historical_allocated_units.where(replay_measurement_eligible),
            "historical_allocation_source_column": historical_allocation_source.where(replay_measurement_eligible, ""),
            "realised_units_sold_promo": realised_units_sold_promo.where(replay_measurement_eligible),
            "realised_units_source_column": realised_units_source.where(replay_measurement_eligible, ""),
            "replay_unit_cost": replay_unit_cost.where(replay_measurement_eligible),
            "replay_unit_cost_source_column": unit_cost_source.where(replay_measurement_eligible, ""),
            "historical_excess_units": historical_excess_units.where(replay_measurement_eligible),
            "historical_excess_capital": historical_excess_capital.where(replay_measurement_eligible),
            "replay_policy_units": replay_policy_units.where(replay_measurement_eligible),
            "replay_policy_excess_units": replay_policy_excess_units.where(replay_measurement_eligible),
            "replay_policy_excess_capital": replay_policy_excess_capital.where(replay_measurement_eligible),
            "replay_units_removed": replay_units_removed.where(replay_measurement_eligible),
            "replay_capital_removed": replay_capital_removed.where(replay_measurement_eligible),
        },
        index=dataset.index,
    )


def _first_present_nonnegative_numeric_series(
    frame: pd.DataFrame,
    candidate_columns: tuple[str, ...],
) -> tuple[pd.Series, pd.Series]:
    values = pd.Series(np.nan, index=frame.index, dtype="float64")
    source_columns = pd.Series("", index=frame.index, dtype="object")
    for column_name in candidate_columns:
        if column_name not in frame.columns:
            continue
        numeric = pd.to_numeric(frame[column_name], errors="coerce")
        numeric = numeric.where(numeric.ge(0.0))
        take_mask = values.isna() & numeric.notna()
        values = values.where(~take_mask, numeric)
        source_columns = source_columns.where(~take_mask, column_name)
    return values, source_columns


def _empty_allocation_split_metrics(prefix: str) -> dict[str, object]:
    metrics: dict[str, object] = {
        f"{prefix}_allocation_aware_units_cap_count": 0.0,
        f"{prefix}_policy_adjusted_row_count": 0.0,
        f"{prefix}_policy_forced_review_row_count": 0.0,
        f"{prefix}_policy_units_removed_total": 0.0,
        f"{prefix}_policy_capital_at_risk_removed_total": 0.0,
        f"{prefix}_excess_units_mae_raw": 0.0,
        f"{prefix}_excess_units_mae_calibrated": 0.0,
        f"{prefix}_excess_units_mae_policy_adjusted": 0.0,
        f"{prefix}_excess_capital_mae_raw": 0.0,
        f"{prefix}_excess_capital_mae_calibrated": 0.0,
        f"{prefix}_excess_capital_mae_policy_adjusted": 0.0,
        f"{prefix}_raw_excess_units_mae": 0.0,
        f"{prefix}_raw_excess_capital_at_risk_mae": 0.0,
        f"{prefix}_excess_units_mae": 0.0,
        f"{prefix}_excess_capital_at_risk_mae": 0.0,
        f"{prefix}_raw_uplift_units_mae": 0.0,
        f"{prefix}_uplift_units_mae": 0.0,
        f"{prefix}_overallocation_false_positive_count": 0.0,
        f"{prefix}_overallocation_false_negative_count": 0.0,
        f"{prefix}_overallocation_false_positive_cost_proxy": 0.0,
        f"{prefix}_overallocation_false_positive_missed_opportunity_proxy": 0.0,
        f"{prefix}_overallocation_false_negative_excess_capital_proxy": 0.0,
        f"{prefix}_excess_units_mae_by_same_discount_history_bucket": _empty_bucket_metric_map(SAME_DISCOUNT_HISTORY_BUCKET_ORDER),
        f"{prefix}_excess_capital_mae_by_same_discount_history_bucket": _empty_bucket_metric_map(SAME_DISCOUNT_HISTORY_BUCKET_ORDER),
        f"{prefix}_excess_units_mae_by_elasticity_confidence_bucket": _empty_bucket_metric_map(CONFIDENCE_BUCKET_ORDER),
        f"{prefix}_excess_capital_mae_by_elasticity_confidence_bucket": _empty_bucket_metric_map(CONFIDENCE_BUCKET_ORDER),
        f"{prefix}_excess_units_mae_by_uplift_confidence_bucket": _empty_bucket_metric_map(CONFIDENCE_BUCKET_ORDER),
        f"{prefix}_excess_capital_mae_by_uplift_confidence_bucket": _empty_bucket_metric_map(CONFIDENCE_BUCKET_ORDER),
        f"{prefix}_excess_units_mae_by_base_demand_growth_bucket": _empty_bucket_metric_map(BASE_DEMAND_GROWTH_BUCKET_ORDER),
        f"{prefix}_excess_capital_mae_by_base_demand_growth_bucket": _empty_bucket_metric_map(BASE_DEMAND_GROWTH_BUCKET_ORDER),
        f"{prefix}_excess_units_mae_by_window_conflict_bucket": _empty_bucket_metric_map(WINDOW_CONFLICT_BUCKET_ORDER),
        f"{prefix}_excess_capital_mae_by_window_conflict_bucket": _empty_bucket_metric_map(WINDOW_CONFLICT_BUCKET_ORDER),
        f"{prefix}_policy_metric_comparison_by_major_bucket": _empty_major_policy_bucket_comparison(),
    }
    metrics.update(_empty_allocation_calibration_metrics(prefix))
    return metrics


def _empty_bucket_metric_map(bucket_order: tuple[str, ...]) -> dict[str, float]:
    return {bucket_name: 0.0 for bucket_name in bucket_order}


def _bucket_mae_map(
    rows: pd.DataFrame,
    *,
    bucket_column: str,
    bucket_order: tuple[str, ...],
    error_column: str,
) -> dict[str, float]:
    values: dict[str, float] = {}
    for bucket_name in bucket_order:
        bucket_rows = rows.loc[rows[bucket_column].astype(str).eq(bucket_name)]
        values[bucket_name] = float(bucket_rows[error_column].mean()) if not bucket_rows.empty else 0.0
    return values


def _empty_major_policy_bucket_comparison() -> dict[str, dict[str, float]]:
    return {
        bucket_name: {
            "row_count": 0.0,
            "excess_units_mae_raw": 0.0,
            "excess_units_mae_calibrated": 0.0,
            "excess_units_mae_policy_adjusted": 0.0,
            "excess_capital_mae_raw": 0.0,
            "excess_capital_mae_calibrated": 0.0,
            "excess_capital_mae_policy_adjusted": 0.0,
        }
        for bucket_name in ORDER_POLICY_MAJOR_BUCKET_COLUMNS
    }


def _major_policy_bucket_comparison(rows: pd.DataFrame) -> dict[str, dict[str, float]]:
    comparison = _empty_major_policy_bucket_comparison()
    for bucket_name in ORDER_POLICY_MAJOR_BUCKET_COLUMNS:
        bucket_rows = rows.loc[pd.to_numeric(rows[bucket_name], errors="coerce").fillna(0.0).ge(1.0)]
        comparison[bucket_name] = {
            "row_count": float(len(bucket_rows.index)),
            "excess_units_mae_raw": float(bucket_rows["raw_excess_units_abs_error"].mean()) if not bucket_rows.empty else 0.0,
            "excess_units_mae_calibrated": float(bucket_rows["calibrated_excess_units_abs_error"].mean()) if not bucket_rows.empty else 0.0,
            "excess_units_mae_policy_adjusted": float(bucket_rows["policy_adjusted_excess_units_abs_error"].mean()) if not bucket_rows.empty else 0.0,
            "excess_capital_mae_raw": float(bucket_rows["raw_excess_capital_abs_error"].mean()) if not bucket_rows.empty else 0.0,
            "excess_capital_mae_calibrated": float(bucket_rows["calibrated_excess_capital_abs_error"].mean()) if not bucket_rows.empty else 0.0,
            "excess_capital_mae_policy_adjusted": float(bucket_rows["policy_adjusted_excess_capital_abs_error"].mean()) if not bucket_rows.empty else 0.0,
        }
    return comparison


def _build_allocation_decision_scoreboard(
    rows: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if rows.empty:
        empty_payload = {
            "overall_summary": {"row_count": 0},
            "bucket_summaries": {},
            "policy_comparison_overall": {},
            "policy_comparison_by_major_bucket": {},
            "policy_adjustment_summary": {},
            "top_overallocation_patterns": [],
            "top_driver_combinations": [],
            "counts_and_capital_at_risk_by_driver": [],
            "evidence_coverage_report": {},
        }
        return pd.DataFrame(columns=["section"]), empty_payload

    overall_summary = {
        "row_count": int(len(rows.index)),
        "split_counts": {
            str(split_name): int(count)
            for split_name, count in rows["split_name"].astype(str).value_counts(dropna=False).to_dict().items()
        },
        "allocation_aware_units_cap_count": int(rows["allocation_aware_units_cap_applied_flag"].sum()),
        "excess_units_mae": float(rows["calibrated_excess_units_abs_error"].mean()),
        "excess_capital_mae": float(rows["calibrated_excess_capital_abs_error"].mean()),
        "weak_fallback_logic_row_count": int(rows["weak_fallback_logic_flag"].sum()),
        "evidence_conflict_review_candidate_row_count": int(rows["evidence_conflict_review_candidate_flag"].sum()),
    }
    policy_comparison_overall = {
        "excess_units_mae_raw": float(rows["raw_excess_units_abs_error"].mean()),
        "excess_units_mae_calibrated": float(rows["calibrated_excess_units_abs_error"].mean()),
        "excess_units_mae_policy_adjusted": float(rows["policy_adjusted_excess_units_abs_error"].mean()),
        "excess_capital_mae_raw": float(rows["raw_excess_capital_abs_error"].mean()),
        "excess_capital_mae_calibrated": float(rows["calibrated_excess_capital_abs_error"].mean()),
        "excess_capital_mae_policy_adjusted": float(rows["policy_adjusted_excess_capital_abs_error"].mean()),
    }
    policy_comparison_by_major_bucket = _major_policy_bucket_comparison(rows)
    top_policy_reasons = (
        rows.loc[rows["policy_adjustment_reason"].astype(str).ne("no_policy_adjustment"), "policy_adjustment_reason"]
        .astype(str)
        .value_counts(dropna=False)
        .head(10)
        .to_dict()
    )
    policy_adjustment_summary = {
        "policy_adjusted_row_count": int(pd.to_numeric(rows["policy_adjustment_fired_flag"], errors="coerce").sum()),
        "policy_forced_review_row_count": int(pd.to_numeric(rows["review_override_flag"], errors="coerce").sum()),
        "total_units_removed_by_policy": float(pd.to_numeric(rows["policy_units_removed"], errors="coerce").sum()),
        "total_capital_at_risk_removed_by_policy": float(pd.to_numeric(rows["policy_capital_at_risk_removed"], errors="coerce").sum()),
        "top_policy_reasons": top_policy_reasons,
    }

    bucket_specs = (
        ("same_discount_history_bucket", SAME_DISCOUNT_HISTORY_BUCKET_ORDER),
        ("elasticity_confidence_bucket", CONFIDENCE_BUCKET_ORDER),
        ("uplift_confidence_bucket", CONFIDENCE_BUCKET_ORDER),
        ("base_demand_growth_bucket", BASE_DEMAND_GROWTH_BUCKET_ORDER),
        ("window_conflict_bucket", WINDOW_CONFLICT_BUCKET_ORDER),
    )
    bucket_summaries: dict[str, list[dict[str, object]]] = {}
    bucket_summary_rows: list[dict[str, object]] = []
    for bucket_column, bucket_order in bucket_specs:
        summary_rows: list[dict[str, object]] = []
        for bucket_name in bucket_order:
            bucket_rows = rows.loc[rows[bucket_column].astype(str).eq(bucket_name)]
            row = {
                "bucket": bucket_name,
                "row_count": int(len(bucket_rows.index)),
                "row_share": float(len(bucket_rows.index) / len(rows.index)) if len(rows.index) else 0.0,
                "excess_units_mae": float(bucket_rows["excess_units_abs_error"].mean()) if not bucket_rows.empty else 0.0,
                "excess_capital_mae": float(bucket_rows["excess_capital_abs_error"].mean()) if not bucket_rows.empty else 0.0,
                "actual_excess_capital_at_risk_total": float(bucket_rows["actual_excess_capital_at_risk"].sum()) if not bucket_rows.empty else 0.0,
                "predicted_excess_capital_at_risk_total": float(bucket_rows["predicted_excess_capital_at_risk"].sum()) if not bucket_rows.empty else 0.0,
            }
            summary_rows.append(row)
            bucket_summary_rows.append(
                {
                    "section": "bucket_summary",
                    "bucket_dimension": bucket_column,
                    **row,
                }
            )
        bucket_summaries[bucket_column] = summary_rows

    top_overallocation_patterns = (
        rows.groupby(
            [
                "same_discount_history_bucket",
                "elasticity_confidence_bucket",
                "uplift_confidence_bucket",
                "base_demand_growth_bucket",
                "window_conflict_bucket",
                "order_sizing_driver",
                "order_cap_reason",
            ],
            dropna=False,
        )
        .agg(
            row_count=("split_name", "size"),
            excess_units_mae=("excess_units_abs_error", "mean"),
            excess_capital_mae=("excess_capital_abs_error", "mean"),
            actual_excess_capital_at_risk_total=("actual_excess_capital_at_risk", "sum"),
        )
        .reset_index()
        .sort_values(
            ["actual_excess_capital_at_risk_total", "excess_capital_mae", "row_count"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        .head(10)
    )

    top_driver_combinations = (
        rows.groupby(
            ["order_risk_driver_combination", "order_sizing_driver", "order_cap_reason"],
            dropna=False,
        )
        .agg(
            row_count=("split_name", "size"),
            excess_capital_mae=("excess_capital_abs_error", "mean"),
            actual_excess_capital_at_risk_total=("actual_excess_capital_at_risk", "sum"),
        )
        .reset_index()
        .sort_values(
            ["actual_excess_capital_at_risk_total", "row_count"],
            ascending=[False, False],
            kind="mergesort",
        )
        .head(10)
    )

    driver_flag_columns = (
        ("feature_order_risk_reason_same_discount_weak_flag", "same_discount_weak"),
        ("feature_order_risk_reason_elasticity_weak_flag", "elasticity_weak"),
        ("feature_order_risk_reason_uplift_weak_flag", "uplift_weak"),
        ("feature_order_risk_reason_base_trend_falling_flag", "base_trend_falling"),
        ("feature_order_risk_reason_launch_total_conflict_flag", "launch_total_conflict"),
        ("feature_order_risk_reason_stock_vs_supported_gap_high_flag", "stock_vs_supported_gap_high"),
        ("feature_order_risk_reason_sparse_history_flag", "sparse_history"),
    )
    driver_rows: list[dict[str, object]] = []
    for column_name, driver_name in driver_flag_columns:
        driver_subset = rows.loc[pd.to_numeric(rows[column_name], errors="coerce").ge(1.0)]
        driver_rows.append(
            {
                "driver_name": driver_name,
                "row_count": int(len(driver_subset.index)),
                "actual_excess_capital_at_risk_total": float(driver_subset["actual_excess_capital_at_risk"].sum()) if not driver_subset.empty else 0.0,
                "predicted_excess_capital_at_risk_total": float(driver_subset["predicted_excess_capital_at_risk"].sum()) if not driver_subset.empty else 0.0,
                "excess_capital_mae": float(driver_subset["excess_capital_abs_error"].mean()) if not driver_subset.empty else 0.0,
            }
        )

    evidence_coverage_report = {
        "same_discount_evidence_row_count": int(rows["evidence_same_discount_present_flag"].sum()),
        "usable_elasticity_row_count": int(rows["evidence_usable_elasticity_flag"].sum()),
        "strong_uplift_support_row_count": int(rows["evidence_strong_uplift_support_flag"].sum()),
        "probability_model_use_row_count": int(rows["evidence_probability_model_use_flag"].sum()),
        "weak_fallback_logic_row_count": int(rows["weak_fallback_logic_flag"].sum()),
    }

    scoreboard_payload = {
        "overall_summary": overall_summary,
        "bucket_summaries": bucket_summaries,
        "policy_comparison_overall": policy_comparison_overall,
        "policy_comparison_by_major_bucket": policy_comparison_by_major_bucket,
        "policy_adjustment_summary": policy_adjustment_summary,
        "top_overallocation_patterns": top_overallocation_patterns.to_dict(orient="records"),
        "top_driver_combinations": top_driver_combinations.to_dict(orient="records"),
        "counts_and_capital_at_risk_by_driver": driver_rows,
        "evidence_coverage_report": evidence_coverage_report,
    }

    csv_frames = [
        pd.DataFrame(
            [
                {"section": "overall_summary", "metric_name": key, "metric_value": value}
                for key, value in overall_summary.items()
                if key != "split_counts"
            ]
        ),
        pd.DataFrame(
            [
                {
                    "section": "overall_summary_split_count",
                    "metric_name": split_name,
                    "metric_value": split_count,
                }
                for split_name, split_count in overall_summary["split_counts"].items()
            ]
        ),
        pd.DataFrame(
            [
                {"section": "policy_comparison_overall", "metric_name": key, "metric_value": value}
                for key, value in policy_comparison_overall.items()
            ]
        ),
        pd.DataFrame(
            [
                {
                    "section": "policy_comparison_major_bucket",
                    "bucket_name": bucket_name,
                    **bucket_metrics,
                }
                for bucket_name, bucket_metrics in policy_comparison_by_major_bucket.items()
            ]
        ),
        pd.DataFrame(
            [
                {"section": "policy_adjustment_summary", "metric_name": key, "metric_value": value}
                for key, value in policy_adjustment_summary.items()
                if key != "top_policy_reasons"
            ]
        ),
        pd.DataFrame(
            [
                {
                    "section": "policy_adjustment_top_reason",
                    "metric_name": reason_name,
                    "metric_value": row_count,
                }
                for reason_name, row_count in top_policy_reasons.items()
            ]
        ),
        pd.DataFrame(bucket_summary_rows),
        top_overallocation_patterns.assign(section="top_overallocation_pattern"),
        top_driver_combinations.assign(section="top_driver_combination"),
        pd.DataFrame(driver_rows).assign(section="driver_capital_summary"),
        pd.DataFrame(
            [
                {"section": "evidence_coverage", "metric_name": key, "metric_value": value}
                for key, value in evidence_coverage_report.items()
            ]
        ),
    ]
    scoreboard_csv_frame = pd.concat(csv_frames, axis=0, ignore_index=True, sort=False)
    return scoreboard_csv_frame, scoreboard_payload


def _build_policy_effectiveness_artifacts(rows: pd.DataFrame) -> dict[str, object]:
    bucket_frame = _build_policy_effectiveness_bucket_frame(rows)
    overall_metric_block = _policy_effectiveness_metric_block(rows)
    overall_policy_adjusted_capital_mae = float(overall_metric_block["excess_capital_mae_policy_adjusted"])

    by_major_bucket: dict[str, dict[str, float]] = {}
    summary_bucket_rows: list[dict[str, object]] = []
    ranking_rows: list[dict[str, object]] = []
    for bucket_name in POLICY_EFFECTIVENESS_BUCKET_ORDER:
        bucket_rows = rows.loc[bucket_frame[bucket_name]]
        bucket_metrics = _policy_effectiveness_metric_block(bucket_rows)
        by_major_bucket[bucket_name] = bucket_metrics
        summary_bucket_rows.extend(
            {
                "section": "major_bucket",
                "bucket_name": bucket_name,
                "metric_name": metric_name,
                "metric_value": metric_value,
            }
            for metric_name, metric_value in bucket_metrics.items()
        )
        ranking_rows.append(
            _policy_bucket_ranking_row(
                bucket_name=bucket_name,
                bucket_rows=bucket_rows,
                overall_policy_adjusted_capital_mae=overall_policy_adjusted_capital_mae,
            )
        )

    summary_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "total_rows_scored": int(overall_metric_block["row_count"]),
        "total_rows_policy_adjusted": int(overall_metric_block["policy_adjusted_row_count"]),
        "total_rows_forced_to_review_by_policy": int(overall_metric_block["policy_forced_review_row_count"]),
        "units_removed_by_policy": float(overall_metric_block["units_removed_by_policy"]),
        "capital_at_risk_removed_by_policy": float(overall_metric_block["capital_at_risk_removed_by_policy"]),
        "excess_units_mae_raw": float(overall_metric_block["excess_units_mae_raw"]),
        "excess_units_mae_calibrated": float(overall_metric_block["excess_units_mae_calibrated"]),
        "excess_units_mae_policy_adjusted": float(overall_metric_block["excess_units_mae_policy_adjusted"]),
        "excess_capital_mae_raw": float(overall_metric_block["excess_capital_mae_raw"]),
        "excess_capital_mae_calibrated": float(overall_metric_block["excess_capital_mae_calibrated"]),
        "excess_capital_mae_policy_adjusted": float(overall_metric_block["excess_capital_mae_policy_adjusted"]),
        "by_major_bucket": by_major_bucket,
    }
    summary_csv_frame = pd.concat(
        [
            pd.DataFrame(
                [
                    {"section": "overall", "metric_name": key, "metric_value": value}
                    for key, value in summary_payload.items()
                    if key not in {"row_scope", "by_major_bucket"}
                ]
            ),
            pd.DataFrame(summary_bucket_rows),
        ],
        axis=0,
        ignore_index=True,
        sort=False,
    )

    bucket_ranking_frame = pd.DataFrame(ranking_rows)
    if not bucket_ranking_frame.empty:
        bucket_ranking_frame = bucket_ranking_frame.sort_values(
            ["policy_adjusted_excess_capital_mae", "row_count", "bucket_name"],
            ascending=[False, False, True],
            kind="mergesort",
        ).reset_index(drop=True)

    worst_bucket_name = None
    if not bucket_ranking_frame.empty:
        remaining_bad_ranking = bucket_ranking_frame.loc[
            bucket_ranking_frame["still_materially_bad_after_policy"].fillna(False).astype(bool)
        ]
        if not remaining_bad_ranking.empty:
            worst_bucket_name = str(remaining_bad_ranking.iloc[0]["bucket_name"])

    worst_bucket_residual_frame = _build_worst_bucket_residual_frame(
        rows,
        bucket_frame=bucket_frame,
        worst_bucket_name=worst_bucket_name,
    )
    worst_bucket_ranking_row = None
    if worst_bucket_name is not None and not bucket_ranking_frame.empty:
        matching_rows = bucket_ranking_frame.loc[bucket_ranking_frame["bucket_name"].astype(str).eq(worst_bucket_name)]
        if not matching_rows.empty:
            worst_bucket_ranking_row = matching_rows.iloc[0].to_dict()

    bucket_ranking_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "overall_policy_adjusted_excess_capital_mae": overall_policy_adjusted_capital_mae,
        "materially_bad_rule": {
            "min_row_count": _POLICY_BUCKET_BAD_MIN_ROWS,
            "relative_to_overall_policy_adjusted_excess_capital_mae": _POLICY_BUCKET_BAD_RELATIVE_THRESHOLD,
        },
        "ranking_rows": bucket_ranking_frame.to_dict(orient="records"),
        "worst_remaining_bucket": worst_bucket_name,
    }
    worst_bucket_residual_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "bucket_name": worst_bucket_name,
        "top_row_limit": _POLICY_RESIDUAL_ROW_LIMIT,
        "bucket_ranking_row": worst_bucket_ranking_row,
        "row_count": int(len(worst_bucket_residual_frame.index)),
        "rows": worst_bucket_residual_frame.to_dict(orient="records"),
    }

    return {
        "summary_csv_frame": summary_csv_frame,
        "summary_payload": summary_payload,
        "bucket_ranking_frame": bucket_ranking_frame,
        "bucket_ranking_payload": bucket_ranking_payload,
        "worst_bucket_residual_frame": worst_bucket_residual_frame,
        "worst_bucket_residual_payload": worst_bucket_residual_payload,
    }


def _build_policy_replay_effectiveness_artifacts(rows: pd.DataFrame) -> dict[str, object]:
    bucket_frame = _build_policy_effectiveness_bucket_frame(rows)
    overall_metric_block = _policy_replay_metric_block(rows)
    overall_replay_policy_excess_capital_mean = float(overall_metric_block["replay_policy_excess_capital_mean"])
    exclusion_reason_counts = _policy_replay_exclusion_reason_counts(rows)

    by_major_bucket: dict[str, dict[str, float]] = {}
    summary_bucket_rows: list[dict[str, object]] = []
    ranking_rows: list[dict[str, object]] = []
    for bucket_name in POLICY_EFFECTIVENESS_BUCKET_ORDER:
        bucket_rows = rows.loc[bucket_frame[bucket_name]]
        bucket_metrics = _policy_replay_metric_block(bucket_rows)
        by_major_bucket[bucket_name] = bucket_metrics
        summary_bucket_rows.extend(
            {
                "section": "major_bucket",
                "bucket_name": bucket_name,
                "metric_name": metric_name,
                "metric_value": metric_value,
            }
            for metric_name, metric_value in bucket_metrics.items()
        )
        ranking_rows.append(
            _policy_replay_bucket_ranking_row(
                bucket_name=bucket_name,
                bucket_rows=bucket_rows,
                overall_replay_policy_excess_capital_mean=overall_replay_policy_excess_capital_mean,
                overall_historical_excess_capital_total=float(overall_metric_block["historical_excess_capital_total"]),
            )
        )

    summary_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "total_rows_scored": int(len(rows.index)),
        "total_rows_replay_eligible": int(overall_metric_block["row_count"]),
        "total_rows_excluded_from_replay": int(len(rows.index) - int(overall_metric_block["row_count"])),
        "replay_policy_adjusted_row_count": int(overall_metric_block["policy_adjusted_row_count"]),
        "historical_excess_units_mean": float(overall_metric_block["historical_excess_units_mean"]),
        "historical_excess_capital_mean": float(overall_metric_block["historical_excess_capital_mean"]),
        "replay_policy_excess_units_mean": float(overall_metric_block["replay_policy_excess_units_mean"]),
        "replay_policy_excess_capital_mean": float(overall_metric_block["replay_policy_excess_capital_mean"]),
        "historical_excess_units_total": float(overall_metric_block["historical_excess_units_total"]),
        "historical_excess_capital_total": float(overall_metric_block["historical_excess_capital_total"]),
        "replay_policy_excess_units_total": float(overall_metric_block["replay_policy_excess_units_total"]),
        "replay_policy_excess_capital_total": float(overall_metric_block["replay_policy_excess_capital_total"]),
        "replay_units_removed_total": float(overall_metric_block["replay_units_removed_total"]),
        "replay_capital_removed_total": float(overall_metric_block["replay_capital_removed_total"]),
        "replay_exclusion_reason_counts": exclusion_reason_counts,
        "by_major_bucket": by_major_bucket,
    }
    summary_csv_frame = pd.concat(
        [
            pd.DataFrame(
                [
                    {"section": "overall", "metric_name": key, "metric_value": value}
                    for key, value in summary_payload.items()
                    if key not in {"row_scope", "by_major_bucket", "replay_exclusion_reason_counts"}
                ]
            ),
            pd.DataFrame(summary_bucket_rows),
            pd.DataFrame(
                [
                    {
                        "section": "replay_exclusion_reason",
                        "bucket_name": None,
                        "metric_name": reason,
                        "metric_value": row_count,
                    }
                    for reason, row_count in exclusion_reason_counts.items()
                ]
            ),
        ],
        axis=0,
        ignore_index=True,
        sort=False,
    )

    bucket_ranking_frame = pd.DataFrame(ranking_rows)
    if not bucket_ranking_frame.empty:
        bucket_ranking_frame = bucket_ranking_frame.sort_values(
            ["replay_policy_excess_capital_mean", "row_count", "bucket_name"],
            ascending=[False, False, True],
            kind="mergesort",
        ).reset_index(drop=True)

    worst_bucket_name = None
    if not bucket_ranking_frame.empty:
        remaining_bad_ranking = bucket_ranking_frame.loc[
            bucket_ranking_frame["materially_bad_flag"].fillna(False).astype(bool)
        ]
        if not remaining_bad_ranking.empty:
            worst_bucket_name = str(remaining_bad_ranking.iloc[0]["bucket_name"])

    worst_bucket_residual_frame = _build_policy_replay_worst_bucket_residual_frame(
        rows,
        bucket_frame=bucket_frame,
        worst_bucket_name=worst_bucket_name,
    )
    worst_bucket_ranking_row = None
    if worst_bucket_name is not None and not bucket_ranking_frame.empty:
        matching_rows = bucket_ranking_frame.loc[bucket_ranking_frame["bucket_name"].astype(str).eq(worst_bucket_name)]
        if not matching_rows.empty:
            worst_bucket_ranking_row = matching_rows.iloc[0].to_dict()

    bucket_ranking_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "overall_replay_policy_excess_capital_mean": overall_replay_policy_excess_capital_mean,
        "materially_bad_rule": {
            "min_row_count": _POLICY_BUCKET_BAD_MIN_ROWS,
            "relative_to_overall_replay_policy_excess_capital_mean": _POLICY_BUCKET_BAD_RELATIVE_THRESHOLD,
        },
        "ranking_rows": bucket_ranking_frame.to_dict(orient="records"),
        "worst_remaining_bucket": worst_bucket_name,
    }
    worst_bucket_residual_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "bucket_name": worst_bucket_name,
        "top_row_limit": _POLICY_RESIDUAL_ROW_LIMIT,
        "bucket_ranking_row": worst_bucket_ranking_row,
        "row_count": int(len(worst_bucket_residual_frame.index)),
        "rows": worst_bucket_residual_frame.to_dict(orient="records"),
    }

    return {
        "summary_csv_frame": summary_csv_frame,
        "summary_payload": summary_payload,
        "bucket_ranking_frame": bucket_ranking_frame,
        "bucket_ranking_payload": bucket_ranking_payload,
        "worst_bucket_residual_frame": worst_bucket_residual_frame,
        "worst_bucket_residual_payload": worst_bucket_residual_payload,
    }


def _build_policy_effectiveness_bucket_frame(rows: pd.DataFrame) -> pd.DataFrame:
    weak_same_discount_history = _metric_series(rows, "weak_same_discount_history").ge(1.0)
    weak_uplift = _metric_series(rows, "weak_uplift").ge(1.0)
    weak_elasticity = _metric_series(rows, "weak_elasticity").ge(1.0)
    falling_base = _metric_series(rows, "falling_base").ge(1.0)
    launch_total_conflict = _metric_series(rows, "launch_total_conflict").ge(1.0)
    stock_gap_high = _metric_series(rows, "feature_order_risk_reason_stock_vs_supported_gap_high_flag").ge(1.0)
    sparse_history_multi_driver = _metric_series(rows, "sparse_history_multi_driver").ge(1.0)
    return pd.DataFrame(
        {
            "weak_same_discount_and_uplift": (weak_same_discount_history & weak_uplift).astype(bool),
            "weak_elasticity": weak_elasticity.astype(bool),
            "falling_base_launch_conflict": (falling_base & launch_total_conflict).astype(bool),
            "stock_gap_high": stock_gap_high.astype(bool),
            "sparse_history_multi_driver": sparse_history_multi_driver.astype(bool),
        },
        index=rows.index,
    )


def _policy_effectiveness_metric_block(rows: pd.DataFrame) -> dict[str, float]:
    return {
        "row_count": int(len(rows.index)),
        "policy_adjusted_row_count": int(_metric_series(rows, "policy_adjustment_fired_flag").sum()),
        "policy_forced_review_row_count": int(_metric_series(rows, "review_override_flag").sum()),
        "units_removed_by_policy": float(_metric_series(rows, "policy_units_removed").sum()),
        "capital_at_risk_removed_by_policy": float(_metric_series(rows, "policy_capital_at_risk_removed").sum()),
        "excess_units_mae_raw": float(_metric_series(rows, "raw_excess_units_abs_error").mean()) if not rows.empty else 0.0,
        "excess_units_mae_calibrated": float(_metric_series(rows, "calibrated_excess_units_abs_error").mean()) if not rows.empty else 0.0,
        "excess_units_mae_policy_adjusted": float(_metric_series(rows, "policy_adjusted_excess_units_abs_error").mean()) if not rows.empty else 0.0,
        "excess_capital_mae_raw": float(_metric_series(rows, "raw_excess_capital_abs_error").mean()) if not rows.empty else 0.0,
        "excess_capital_mae_calibrated": float(_metric_series(rows, "calibrated_excess_capital_abs_error").mean()) if not rows.empty else 0.0,
        "excess_capital_mae_policy_adjusted": float(_metric_series(rows, "policy_adjusted_excess_capital_abs_error").mean()) if not rows.empty else 0.0,
    }


def _policy_replay_measured_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty or "replay_measurement_eligible_flag" not in rows.columns:
        return pd.DataFrame(columns=rows.columns)
    measured_mask = pd.to_numeric(rows["replay_measurement_eligible_flag"], errors="coerce").fillna(0.0).ge(1.0)
    return rows.loc[measured_mask].copy()


def _policy_replay_exclusion_reason_counts(rows: pd.DataFrame) -> dict[str, int]:
    if rows.empty or "replay_exclusion_reason" not in rows.columns:
        return {
            _POLICY_REPLAY_EXCLUSION_REASON_ELIGIBLE: 0,
            _POLICY_REPLAY_EXCLUSION_REASON_MISSING_HISTORICAL_ALLOCATION: 0,
            _POLICY_REPLAY_EXCLUSION_REASON_MISSING_REALISED_PROMO_UNITS: 0,
            _POLICY_REPLAY_EXCLUSION_REASON_MISSING_EFFECTIVE_COST: 0,
            _POLICY_REPLAY_EXCLUSION_REASON_MULTIPLE_MISSING_INPUTS: 0,
        }
    reason_counts = rows["replay_exclusion_reason"].astype(str).value_counts(dropna=False).to_dict()
    return {
        reason: int(reason_counts.get(reason, 0))
        for reason in (
            _POLICY_REPLAY_EXCLUSION_REASON_ELIGIBLE,
            _POLICY_REPLAY_EXCLUSION_REASON_MISSING_HISTORICAL_ALLOCATION,
            _POLICY_REPLAY_EXCLUSION_REASON_MISSING_REALISED_PROMO_UNITS,
            _POLICY_REPLAY_EXCLUSION_REASON_MISSING_EFFECTIVE_COST,
            _POLICY_REPLAY_EXCLUSION_REASON_MULTIPLE_MISSING_INPUTS,
        )
    }


def _policy_replay_metric_block(rows: pd.DataFrame) -> dict[str, float]:
    measured_rows = _policy_replay_measured_rows(rows)
    return {
        "row_count": int(len(measured_rows.index)),
        "policy_adjusted_row_count": int(_metric_series(measured_rows, "policy_adjustment_fired_flag").sum()),
        "historical_excess_units_mean": float(_metric_series(measured_rows, "historical_excess_units").mean()) if not measured_rows.empty else 0.0,
        "historical_excess_capital_mean": float(_metric_series(measured_rows, "historical_excess_capital").mean()) if not measured_rows.empty else 0.0,
        "replay_policy_excess_units_mean": float(_metric_series(measured_rows, "replay_policy_excess_units").mean()) if not measured_rows.empty else 0.0,
        "replay_policy_excess_capital_mean": float(_metric_series(measured_rows, "replay_policy_excess_capital").mean()) if not measured_rows.empty else 0.0,
        "historical_excess_units_total": float(_metric_series(measured_rows, "historical_excess_units").sum()),
        "historical_excess_capital_total": float(_metric_series(measured_rows, "historical_excess_capital").sum()),
        "replay_policy_excess_units_total": float(_metric_series(measured_rows, "replay_policy_excess_units").sum()),
        "replay_policy_excess_capital_total": float(_metric_series(measured_rows, "replay_policy_excess_capital").sum()),
        "replay_units_removed_total": float(_metric_series(measured_rows, "replay_units_removed").sum()),
        "replay_capital_removed_total": float(_metric_series(measured_rows, "replay_capital_removed").sum()),
    }


def _build_policy_rule_contribution_artifacts(rows: pd.DataFrame) -> dict[str, object]:
    measured_rows = _policy_rule_contribution_measured_rows(rows)
    trigger_frame = _policy_rule_trigger_frame_from_rows(measured_rows)
    capital_removed_series = pd.to_numeric(measured_rows["replay_capital_removed"], errors="coerce").fillna(0.0).clip(lower=0.0)
    units_removed_series = pd.to_numeric(measured_rows["replay_units_removed"], errors="coerce").fillna(0.0).clip(lower=0.0)
    overall_replay_policy_excess_capital_mean = float(
        pd.to_numeric(measured_rows["replay_policy_excess_capital"], errors="coerce").fillna(0.0).mean()
    ) if not measured_rows.empty else 0.0
    total_replay_capital_removed = float(capital_removed_series.sum())
    total_replay_units_removed = float(units_removed_series.sum())

    summary_rows = [
        _policy_rule_contribution_summary_row(
            rule_name=rule_name,
            measured_rows=measured_rows,
            trigger_frame=trigger_frame,
            total_replay_capital_removed=total_replay_capital_removed,
        )
        for rule_name in ORDER_POLICY_RULE_NAMES
    ]
    summary_frame = pd.DataFrame(summary_rows)

    overlap_matrix_rows = [
        _policy_rule_overlap_matrix_row(
            rule_name=rule_name,
            overlap_rule_name=overlap_rule_name,
            measured_rows=measured_rows,
            trigger_frame=trigger_frame,
            summary_frame=summary_frame,
        )
        for rule_name in ORDER_POLICY_RULE_NAMES
        for overlap_rule_name in ORDER_POLICY_RULE_NAMES
    ]
    overlap_matrix_frame = pd.DataFrame(overlap_matrix_rows)

    solo_vs_overlap_rows = [
        _policy_rule_solo_vs_overlap_row(
            rule_name=rule_name,
            measured_rows=measured_rows,
            trigger_frame=trigger_frame,
            summary_frame=summary_frame,
        )
        for rule_name in ORDER_POLICY_RULE_NAMES
    ]
    solo_vs_overlap_frame = pd.DataFrame(solo_vs_overlap_rows)

    refinement_candidate_payload = _build_policy_rule_refinement_candidate_payload(
        summary_frame=summary_frame,
        solo_vs_overlap_frame=solo_vs_overlap_frame,
        overall_replay_policy_excess_capital_mean=overall_replay_policy_excess_capital_mean,
    )

    top_capital_removing_rule = _top_policy_rule_name(
        summary_frame,
        value_column="capital_removed_total",
    )
    top_solo_effect_rule = _top_policy_rule_name(
        solo_vs_overlap_frame,
        value_column="solo_capital_removed_total",
    )
    most_overlap_dependent_rule = _top_policy_rule_name(
        solo_vs_overlap_frame,
        value_column="overlap_capital_removed_share_of_rule_total",
    )

    summary_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "overlap_accounting_note": _POLICY_RULE_CONTRIBUTION_NOTE,
        "rule_order": list(ORDER_POLICY_RULE_NAMES),
        "total_rows_scored": int(len(rows.index)),
        "total_rows_replay_eligible": int(len(measured_rows.index)),
        "total_rows_excluded_from_rule_contribution": int(len(rows.index) - len(measured_rows.index)),
        "total_replay_capital_removed": total_replay_capital_removed,
        "total_replay_units_removed": total_replay_units_removed,
        "top_capital_removing_rule": top_capital_removing_rule,
        "top_solo_effect_rule": top_solo_effect_rule,
        "most_overlap_dependent_rule": most_overlap_dependent_rule,
        "rule_rows": summary_frame.to_dict(orient="records"),
    }
    overlap_matrix_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "overlap_accounting_note": _POLICY_RULE_CONTRIBUTION_NOTE,
        "rule_order": list(ORDER_POLICY_RULE_NAMES),
        "matrix": _policy_rule_overlap_matrix_payload(overlap_matrix_frame),
    }
    solo_vs_overlap_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "overlap_accounting_note": _POLICY_RULE_CONTRIBUTION_NOTE,
        "rows": solo_vs_overlap_frame.to_dict(orient="records"),
    }
    return {
        "summary_frame": summary_frame,
        "summary_payload": summary_payload,
        "overlap_matrix_frame": overlap_matrix_frame,
        "overlap_matrix_payload": overlap_matrix_payload,
        "solo_vs_overlap_frame": solo_vs_overlap_frame,
        "solo_vs_overlap_payload": solo_vs_overlap_payload,
        "refinement_candidate_payload": refinement_candidate_payload,
    }


def _policy_rule_contribution_measured_rows(rows: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        rows,
        (
            "replay_measurement_eligible_flag",
            "replay_capital_removed",
            "replay_units_removed",
            "replay_policy_excess_capital",
            "replay_policy_excess_units",
            *ORDER_POLICY_RULE_NAMES,
        ),
        context="policy rule contribution analysis",
    )
    return _policy_replay_measured_rows(rows)


def _policy_rule_trigger_frame_from_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(
            {rule_name: pd.Series(dtype=bool) for rule_name in ORDER_POLICY_RULE_NAMES},
            index=rows.index,
        )
    return pd.DataFrame(
        {
            rule_name: pd.to_numeric(rows[rule_name], errors="coerce").fillna(0.0).ge(1.0)
            for rule_name in ORDER_POLICY_RULE_NAMES
        },
        index=rows.index,
    )


def _policy_rule_contribution_summary_row(
    *,
    rule_name: str,
    measured_rows: pd.DataFrame,
    trigger_frame: pd.DataFrame,
    total_replay_capital_removed: float,
) -> dict[str, object]:
    triggered_mask = trigger_frame[rule_name] if rule_name in trigger_frame.columns else pd.Series(False, index=measured_rows.index)
    triggered_rows = measured_rows.loc[triggered_mask]
    capital_removed_series = pd.to_numeric(triggered_rows.get("replay_capital_removed", pd.Series(0.0, index=triggered_rows.index)), errors="coerce").fillna(0.0).clip(lower=0.0)
    units_removed_series = pd.to_numeric(triggered_rows.get("replay_units_removed", pd.Series(0.0, index=triggered_rows.index)), errors="coerce").fillna(0.0).clip(lower=0.0)
    residual_capital_series = pd.to_numeric(triggered_rows.get("replay_policy_excess_capital", pd.Series(0.0, index=triggered_rows.index)), errors="coerce").fillna(0.0).clip(lower=0.0)
    residual_units_series = pd.to_numeric(triggered_rows.get("replay_policy_excess_units", pd.Series(0.0, index=triggered_rows.index)), errors="coerce").fillna(0.0).clip(lower=0.0)
    capital_removed_total = float(capital_removed_series.sum())

    stronger_rules = [
        candidate_rule
        for candidate_rule in ORDER_POLICY_RULE_NAMES
        if ORDER_POLICY_RULE_STRENGTH_BY_NAME.get(candidate_rule, 0.0) > ORDER_POLICY_RULE_STRENGTH_BY_NAME.get(rule_name, 0.0)
    ]
    stronger_overlap_mask = pd.Series(False, index=measured_rows.index)
    if stronger_rules:
        stronger_overlap_mask = triggered_mask & trigger_frame.loc[:, stronger_rules].any(axis=1)
    stronger_overlap_rows = measured_rows.loc[stronger_overlap_mask]
    stronger_overlap_capital_removed_total = float(
        pd.to_numeric(
            stronger_overlap_rows.get("replay_capital_removed", pd.Series(0.0, index=stronger_overlap_rows.index)),
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0).sum()
    )
    stronger_overlap_share = (
        stronger_overlap_capital_removed_total / capital_removed_total
        if capital_removed_total > 0.0 else 0.0
    )

    return {
        "rule_name": rule_name,
        "triggered_row_count": int(len(triggered_rows.index)),
        "capital_removed_total": capital_removed_total,
        "units_removed_total": float(units_removed_series.sum()),
        "average_capital_removed_per_triggered_row": float(capital_removed_series.mean()) if not triggered_rows.empty else 0.0,
        "median_capital_removed_per_triggered_row": float(capital_removed_series.median()) if not triggered_rows.empty else 0.0,
        "average_units_removed_per_triggered_row": float(units_removed_series.mean()) if not triggered_rows.empty else 0.0,
        "median_units_removed_per_triggered_row": float(units_removed_series.median()) if not triggered_rows.empty else 0.0,
        "share_of_total_replay_capital_removed": (capital_removed_total / total_replay_capital_removed) if total_replay_capital_removed > 0.0 else 0.0,
        "residual_replay_excess_capital_mean_on_triggered_rows": float(residual_capital_series.mean()) if not triggered_rows.empty else 0.0,
        "residual_replay_excess_units_mean_on_triggered_rows": float(residual_units_series.mean()) if not triggered_rows.empty else 0.0,
        "stronger_rule_overlap_capital_removed_total": stronger_overlap_capital_removed_total,
        "stronger_rule_overlap_capital_removed_share_of_rule_total": stronger_overlap_share,
        "policy_strength": float(ORDER_POLICY_RULE_STRENGTH_BY_NAME.get(rule_name, 0.0)),
    }


def _policy_rule_overlap_matrix_row(
    *,
    rule_name: str,
    overlap_rule_name: str,
    measured_rows: pd.DataFrame,
    trigger_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
) -> dict[str, object]:
    rule_mask = trigger_frame[rule_name] if rule_name in trigger_frame.columns else pd.Series(False, index=measured_rows.index)
    overlap_mask = trigger_frame[overlap_rule_name] if overlap_rule_name in trigger_frame.columns else pd.Series(False, index=measured_rows.index)
    pair_rows = measured_rows.loc[rule_mask & overlap_mask]
    rule_summary = summary_frame.loc[summary_frame["rule_name"].astype(str).eq(rule_name)]
    rule_row_count = int(rule_summary.iloc[0]["triggered_row_count"]) if not rule_summary.empty else 0
    rule_capital_removed_total = float(rule_summary.iloc[0]["capital_removed_total"]) if not rule_summary.empty else 0.0
    pair_capital_removed_total = float(
        pd.to_numeric(
            pair_rows.get("replay_capital_removed", pd.Series(0.0, index=pair_rows.index)),
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0).sum()
    )
    pair_units_removed_total = float(
        pd.to_numeric(
            pair_rows.get("replay_units_removed", pd.Series(0.0, index=pair_rows.index)),
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0).sum()
    )
    return {
        "rule_name": rule_name,
        "overlap_rule_name": overlap_rule_name,
        "overlap_row_count": int(len(pair_rows.index)),
        "overlap_capital_removed_total": pair_capital_removed_total,
        "overlap_units_removed_total": pair_units_removed_total,
        "overlap_row_share_of_rule_total": (float(len(pair_rows.index)) / rule_row_count) if rule_row_count > 0 else 0.0,
        "overlap_capital_removed_share_of_rule_total": (pair_capital_removed_total / rule_capital_removed_total) if rule_capital_removed_total > 0.0 else 0.0,
    }


def _policy_rule_solo_vs_overlap_row(
    *,
    rule_name: str,
    measured_rows: pd.DataFrame,
    trigger_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
) -> dict[str, object]:
    trigger_count = trigger_frame.sum(axis=1) if not trigger_frame.empty else pd.Series(0.0, index=measured_rows.index)
    rule_mask = trigger_frame[rule_name] if rule_name in trigger_frame.columns else pd.Series(False, index=measured_rows.index)
    solo_rows = measured_rows.loc[rule_mask & trigger_count.eq(1)]
    overlap_rows = measured_rows.loc[rule_mask & trigger_count.ge(2)]
    rule_summary = summary_frame.loc[summary_frame["rule_name"].astype(str).eq(rule_name)]
    rule_capital_removed_total = float(rule_summary.iloc[0]["capital_removed_total"]) if not rule_summary.empty else 0.0

    solo_capital_removed_total = float(
        pd.to_numeric(
            solo_rows.get("replay_capital_removed", pd.Series(0.0, index=solo_rows.index)),
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0).sum()
    )
    overlap_capital_removed_total = float(
        pd.to_numeric(
            overlap_rows.get("replay_capital_removed", pd.Series(0.0, index=overlap_rows.index)),
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0).sum()
    )
    return {
        "rule_name": rule_name,
        "solo_trigger_row_count": int(len(solo_rows.index)),
        "overlap_trigger_row_count": int(len(overlap_rows.index)),
        "solo_capital_removed_total": solo_capital_removed_total,
        "overlap_capital_removed_total": overlap_capital_removed_total,
        "solo_units_removed_total": float(pd.to_numeric(solo_rows.get("replay_units_removed", pd.Series(0.0, index=solo_rows.index)), errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "overlap_units_removed_total": float(pd.to_numeric(overlap_rows.get("replay_units_removed", pd.Series(0.0, index=overlap_rows.index)), errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "solo_capital_removed_share_of_rule_total": (solo_capital_removed_total / rule_capital_removed_total) if rule_capital_removed_total > 0.0 else 0.0,
        "overlap_capital_removed_share_of_rule_total": (overlap_capital_removed_total / rule_capital_removed_total) if rule_capital_removed_total > 0.0 else 0.0,
    }


def _build_policy_rule_refinement_candidate_payload(
    *,
    summary_frame: pd.DataFrame,
    solo_vs_overlap_frame: pd.DataFrame,
    overall_replay_policy_excess_capital_mean: float,
) -> dict[str, object]:
    evaluation_frame = summary_frame.merge(solo_vs_overlap_frame, on="rule_name", how="left", sort=False)
    residual_threshold = (
        overall_replay_policy_excess_capital_mean * _POLICY_RULE_REFINEMENT_MIN_RESIDUAL_TO_OVERALL_RATIO
        if overall_replay_policy_excess_capital_mean > 0.0 else 0.0
    )
    evaluated_rules: list[dict[str, object]] = []
    eligible_rules: list[dict[str, object]] = []

    for _, row in evaluation_frame.iterrows():
        blockers: list[str] = []
        if float(row.get("capital_removed_total", 0.0)) <= 0.0:
            blockers.append("no_measured_capital_removed")
        if int(row.get("triggered_row_count", 0)) < _POLICY_RULE_REFINEMENT_MIN_TRIGGERED_ROW_COUNT:
            blockers.append("insufficient_triggered_row_count")
        if float(row.get("share_of_total_replay_capital_removed", 0.0)) < _POLICY_RULE_REFINEMENT_MIN_SHARE_OF_TOTAL_CAPITAL_REMOVED:
            blockers.append("insufficient_capital_removed_share")
        if float(row.get("residual_replay_excess_capital_mean_on_triggered_rows", 0.0)) < residual_threshold:
            blockers.append("insufficient_residual_replay_excess")
        if int(row.get("solo_trigger_row_count", 0)) < _POLICY_RULE_REFINEMENT_MIN_SOLO_TRIGGERED_ROW_COUNT:
            blockers.append("insufficient_solo_trigger_count")
        if float(row.get("solo_capital_removed_share_of_rule_total", 0.0)) < _POLICY_RULE_REFINEMENT_MIN_SOLO_CAPITAL_SHARE:
            blockers.append("overlap_dominant")
        if float(row.get("stronger_rule_overlap_capital_removed_share_of_rule_total", 0.0)) > _POLICY_RULE_REFINEMENT_MAX_STRONGER_RULE_OVERLAP_SHARE:
            blockers.append("mostly_explained_by_stronger_rules")

        evaluated_rule = {
            **row.to_dict(),
            "eligible_for_refinement": len(blockers) == 0,
            "blockers": blockers,
        }
        evaluated_rules.append(evaluated_rule)
        if not blockers:
            eligible_rules.append(evaluated_rule)

    eligible_frame = pd.DataFrame(eligible_rules)
    refinement_candidate = None
    candidate_metrics = None
    explanation = _policy_rule_null_candidate_explanation(evaluated_rules)
    recommended_next_move = "stop_policy_work"
    if not eligible_frame.empty:
        eligible_frame = eligible_frame.sort_values(
            [
                "capital_removed_total",
                "solo_capital_removed_total",
                "residual_replay_excess_capital_mean_on_triggered_rows",
                "triggered_row_count",
                "rule_name",
            ],
            ascending=[False, False, False, False, True],
            kind="mergesort",
        ).reset_index(drop=True)
        candidate_metrics = eligible_frame.iloc[0].to_dict()
        refinement_candidate = str(candidate_metrics["rule_name"])
        explanation = (
            f"{refinement_candidate} removes a meaningful share of replay capital, still leaves above-baseline residual replay excess on its triggered rows, and is not mostly explained by overlap with stronger rules."
        )
        recommended_next_move = "rule_refinement"

    return {
        "row_scope": "out_of_sample_validation_and_test",
        "selection_rule": {
            "min_triggered_row_count": _POLICY_RULE_REFINEMENT_MIN_TRIGGERED_ROW_COUNT,
            "min_solo_triggered_row_count": _POLICY_RULE_REFINEMENT_MIN_SOLO_TRIGGERED_ROW_COUNT,
            "min_share_of_total_replay_capital_removed": _POLICY_RULE_REFINEMENT_MIN_SHARE_OF_TOTAL_CAPITAL_REMOVED,
            "min_residual_to_overall_ratio": _POLICY_RULE_REFINEMENT_MIN_RESIDUAL_TO_OVERALL_RATIO,
            "min_solo_capital_share": _POLICY_RULE_REFINEMENT_MIN_SOLO_CAPITAL_SHARE,
            "max_stronger_rule_overlap_share": _POLICY_RULE_REFINEMENT_MAX_STRONGER_RULE_OVERLAP_SHARE,
        },
        "refinement_candidate": refinement_candidate,
        "recommended_next_move": recommended_next_move,
        "explanation": explanation,
        "candidate_rule_metrics": candidate_metrics,
        "evaluated_rules": evaluated_rules,
    }


def _policy_rule_null_candidate_explanation(evaluated_rules: list[dict[str, object]]) -> str:
    if not evaluated_rules:
        return "No replay-eligible rule rows were available for contribution analysis."
    blocker_counts: Counter[str] = Counter(
        blocker
        for rule in evaluated_rules
        for blocker in rule.get("blockers", [])
    )
    overlap_blockers = blocker_counts["overlap_dominant"] + blocker_counts["mostly_explained_by_stronger_rules"]
    if overlap_blockers >= len(evaluated_rules):
        return "Overlap dominates and no rule stands alone enough to justify tightening."
    if blocker_counts["insufficient_capital_removed_share"] >= len(evaluated_rules):
        return "Replay benefit is too diffuse across rules to justify tightening any single existing rule."
    if blocker_counts["insufficient_residual_replay_excess"] >= len(evaluated_rules):
        return "Rules that remove replay capital do not leave enough residual replay excess on their triggered rows to justify a tighter rule."
    if blocker_counts["insufficient_triggered_row_count"] >= len(evaluated_rules):
        return "No rule fires often enough on replay-eligible rows to justify a governed tightening decision."
    return "No rule met the governed refinement thresholds without relying mostly on overlap or diffuse effect."


def _policy_rule_overlap_matrix_payload(overlap_matrix_frame: pd.DataFrame) -> dict[str, dict[str, dict[str, object]]]:
    payload: dict[str, dict[str, dict[str, object]]] = {}
    for rule_name in ORDER_POLICY_RULE_NAMES:
        payload[rule_name] = {}
        rule_rows = overlap_matrix_frame.loc[overlap_matrix_frame["rule_name"].astype(str).eq(rule_name)]
        for overlap_rule_name in ORDER_POLICY_RULE_NAMES:
            matching_rows = rule_rows.loc[rule_rows["overlap_rule_name"].astype(str).eq(overlap_rule_name)]
            payload[rule_name][overlap_rule_name] = matching_rows.iloc[0].to_dict() if not matching_rows.empty else {
                "rule_name": rule_name,
                "overlap_rule_name": overlap_rule_name,
                "overlap_row_count": 0,
                "overlap_capital_removed_total": 0.0,
                "overlap_units_removed_total": 0.0,
                "overlap_row_share_of_rule_total": 0.0,
                "overlap_capital_removed_share_of_rule_total": 0.0,
            }
    return payload


def _build_target_contract_artifacts(rows: pd.DataFrame) -> dict[str, object]:
    diagnostic_frame = _build_target_contract_diagnostic_frame(rows)
    comparable_rows = diagnostic_frame.loc[
        pd.to_numeric(diagnostic_frame["both_contract_valid_flag"], errors="coerce").fillna(0.0).ge(1.0)
    ].copy()
    current_valid_mask = pd.to_numeric(diagnostic_frame["current_contract_valid_flag"], errors="coerce").fillna(0.0).ge(1.0)
    historical_valid_mask = pd.to_numeric(diagnostic_frame["historical_contract_valid_flag"], errors="coerce").fillna(0.0).ge(1.0)
    valid_row_counts = {
        "valid_under_both_contracts": int((current_valid_mask & historical_valid_mask).sum()),
        "valid_only_under_current_contract": int((current_valid_mask & ~historical_valid_mask).sum()),
        "valid_only_under_historical_contract": int((~current_valid_mask & historical_valid_mask).sum()),
        "excluded_from_both_contracts": int((~current_valid_mask & ~historical_valid_mask).sum()),
    }
    excluded_reason_counts = (
        diagnostic_frame.loc[~historical_valid_mask, "replay_exclusion_reason"]
        .astype(str)
        .value_counts(dropna=False)
        .to_dict()
    )

    contract_blocks = {
        "current_trainer_excess_contract": _target_contract_metric_block(
            comparable_rows,
            signed_units_column="trainer_current_signed_units_delta",
            excess_units_column="trainer_current_excess_units",
            excess_capital_column="trainer_current_excess_capital",
        ),
        "historical_allocation_replay_contract": _target_contract_metric_block(
            comparable_rows,
            signed_units_column="historical_allocation_signed_units_delta",
            excess_units_column="historical_allocation_excess_units",
            excess_capital_column="historical_allocation_excess_capital",
        ),
        "calibrated_forecast_vs_realised_promo_contract": _target_contract_metric_block(
            comparable_rows,
            signed_units_column="calibrated_prediction_minus_realised_promo_units",
            excess_units_column="calibrated_prediction_excess_units",
            excess_capital_column="calibrated_prediction_excess_capital",
        ),
        "policy_replay_vs_realised_promo_contract": _target_contract_metric_block(
            comparable_rows,
            signed_units_column="policy_adjusted_prediction_minus_realised_promo_units",
            excess_units_column="policy_adjusted_prediction_excess_units",
            excess_capital_column="policy_adjusted_prediction_excess_capital",
        ),
    }
    comparison_blocks = {
        "current_trainer_vs_historical_allocation_contract": _target_contract_gap_metric_block(
            comparable_rows,
            units_gap_column="trainer_vs_historical_excess_units_gap",
            capital_gap_column="trainer_vs_historical_excess_capital_gap",
        ),
        "calibrated_forecast_vs_historical_allocation_contract": _target_contract_gap_metric_block(
            comparable_rows,
            units_gap_column="calibrated_vs_historical_excess_units_gap",
            capital_gap_column="calibrated_vs_historical_excess_capital_gap",
        ),
        "policy_replay_vs_historical_allocation_contract": _target_contract_gap_metric_block(
            comparable_rows,
            units_gap_column="policy_vs_historical_excess_units_gap",
            capital_gap_column="policy_vs_historical_excess_capital_gap",
        ),
        "current_target_flag_vs_historical_allocation_contract": {
            "row_count": int(len(comparable_rows.index)),
            "disagreement_row_count": int(
                pd.to_numeric(comparable_rows["overallocation_flag_disagreement_flag"], errors="coerce").fillna(0.0).sum()
            ),
            "disagreement_rate": float(
                pd.to_numeric(comparable_rows["overallocation_flag_disagreement_flag"], errors="coerce").fillna(0.0).mean()
            ) if not comparable_rows.empty else 0.0,
        },
    }
    contract_prediction_metrics = {
        "current_trainer_excess_contract": _target_contract_prediction_metric_block(
            diagnostic_frame.loc[current_valid_mask].copy(),
            target_excess_units_column="trainer_current_excess_units",
            target_excess_capital_column="trainer_current_excess_capital",
            target_flag_column="current_overallocation_flag",
            prediction_specs=(
                ("raw_units_model", "raw_current_predicted_excess_units", "raw_current_predicted_excess_capital"),
                ("calibrated_units_model", "calibrated_current_predicted_excess_units", "calibrated_current_predicted_excess_capital"),
                ("policy_adjusted_overlay", "policy_current_predicted_excess_units", "policy_current_predicted_excess_capital"),
            ),
        ),
        "historical_allocation_replay_contract": _target_contract_prediction_metric_block(
            diagnostic_frame.loc[historical_valid_mask].copy(),
            target_excess_units_column="historical_allocation_excess_units",
            target_excess_capital_column="historical_allocation_excess_capital",
            target_flag_column="historical_overallocation_flag",
            prediction_specs=(
                ("raw_units_model", "raw_historical_predicted_excess_units", "raw_historical_predicted_excess_capital"),
                ("calibrated_units_model", "calibrated_historical_predicted_excess_units", "calibrated_historical_predicted_excess_capital"),
                ("policy_adjusted_overlay", "policy_historical_predicted_excess_units", "policy_historical_predicted_excess_capital"),
            ),
        ),
    }

    total_capital_gap_abs = float(
        pd.to_numeric(comparable_rows["trainer_vs_historical_excess_capital_gap_abs"], errors="coerce").fillna(0.0).sum()
    )
    bucket_ranking_rows = [
        _target_contract_bucket_ranking_row(
            bucket_name=bucket_name,
            bucket_rows=diagnostic_frame.loc[
                diagnostic_frame["dominant_divergence_driver"].astype(str).eq(bucket_name)
            ],
            total_capital_gap_abs=total_capital_gap_abs,
        )
        for bucket_name in _TARGET_CONTRACT_DIVERGENCE_DRIVER_ORDER
    ]
    bucket_ranking_frame = pd.DataFrame(bucket_ranking_rows)
    if not bucket_ranking_frame.empty:
        bucket_ranking_frame = bucket_ranking_frame.sort_values(
            ["trainer_vs_historical_excess_capital_gap_abs_total", "row_count", "bucket_name"],
            ascending=[False, False, True],
            kind="mergesort",
        ).reset_index(drop=True)

    divergence_summary_payload = _build_target_contract_divergence_summary_payload(
        diagnostic_frame,
        bucket_ranking_frame=bucket_ranking_frame,
    )
    current_trainer_target_misaligned = bool(
        float(comparison_blocks["current_trainer_vs_historical_allocation_contract"]["capital_gap_abs_mean"]) > 0.0
        or float(comparison_blocks["current_target_flag_vs_historical_allocation_contract"]["disagreement_rate"]) > 0.0
    )
    top_divergence_driver = _top_target_contract_bucket_name(
        bucket_ranking_frame,
        value_column="trainer_vs_historical_excess_capital_gap_abs_total",
    )
    summary_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "total_rows_scored": int(len(rows.index)),
        "total_rows_replay_comparable": int(pd.to_numeric(diagnostic_frame["target_contract_replay_comparable_flag"], errors="coerce").fillna(0.0).ge(1.0).sum()),
        "total_rows_valid_under_both_contracts": int(len(comparable_rows.index)),
        "total_rows_excluded_from_contract_comparison": int(len(rows.index) - len(comparable_rows.index)),
        "current_trainer_target_misaligned_with_business_mistake": current_trainer_target_misaligned,
        "top_divergence_driver": top_divergence_driver,
        "valid_row_counts": valid_row_counts,
        "excluded_historical_contract_reason_counts": {str(key): int(value) for key, value in excluded_reason_counts.items()},
        "contract_blocks": contract_blocks,
        "comparison_blocks": comparison_blocks,
        "contract_prediction_metrics": contract_prediction_metrics,
        "policy_pause_conclusion": {
            "policy_remains_paused": True,
            "policy_is_dominant_bottleneck": False,
            "target_contract_misalignment_is_dominant_bottleneck": current_trainer_target_misaligned,
            "explanation": "Historical allocation target disagreement dominates this pass; policy artifacts remain diagnostic and policy rules are unchanged.",
        },
    }
    summary_frame = pd.concat(
        [
            pd.DataFrame(
                [
                    {"section": "headline", "block_name": "summary", "metric_name": key, "metric_value": value}
                    for key, value in summary_payload.items()
                    if key not in {"row_scope", "valid_row_counts", "excluded_historical_contract_reason_counts", "contract_blocks", "comparison_blocks", "contract_prediction_metrics", "policy_pause_conclusion"}
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "section": "valid_row_count",
                        "block_name": "contract_validity",
                        "metric_name": metric_name,
                        "metric_value": metric_value,
                    }
                    for metric_name, metric_value in valid_row_counts.items()
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "section": "historical_contract_exclusion_reason",
                        "block_name": "contract_validity",
                        "metric_name": reason,
                        "metric_value": row_count,
                    }
                    for reason, row_count in excluded_reason_counts.items()
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "section": "contract_block",
                        "block_name": block_name,
                        "metric_name": metric_name,
                        "metric_value": metric_value,
                    }
                    for block_name, block in contract_blocks.items()
                    for metric_name, metric_value in block.items()
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "section": "comparison_block",
                        "block_name": block_name,
                        "metric_name": metric_name,
                        "metric_value": metric_value,
                    }
                    for block_name, block in comparison_blocks.items()
                    for metric_name, metric_value in block.items()
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "section": "contract_prediction_metric",
                        "block_name": contract_name,
                        "prediction_name": prediction_name,
                        "metric_name": metric_name,
                        "metric_value": metric_value,
                    }
                    for contract_name, prediction_blocks in contract_prediction_metrics.items()
                    for prediction_name, metric_block in prediction_blocks.items()
                    for metric_name, metric_value in metric_block.items()
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "section": "policy_pause_conclusion",
                        "block_name": "policy_pause",
                        "metric_name": metric_name,
                        "metric_value": metric_value,
                    }
                    for metric_name, metric_value in summary_payload["policy_pause_conclusion"].items()
                ]
            ),
        ],
        axis=0,
        ignore_index=True,
        sort=False,
    )

    residual_examples_frame = _build_target_contract_residual_examples_frame(diagnostic_frame)
    residual_examples_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "top_row_limit": _TARGET_CONTRACT_RESIDUAL_ROW_LIMIT,
        "row_count": int(len(residual_examples_frame.index)),
        "rows": residual_examples_frame.to_dict(orient="records"),
    }
    bucket_ranking_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "ranking_rows": bucket_ranking_frame.to_dict(orient="records"),
        "top_divergence_driver": top_divergence_driver,
    }
    next_target_refinement_candidate_payload = _build_next_target_refinement_candidate_payload(
        bucket_ranking_frame=bucket_ranking_frame,
        current_trainer_target_misaligned=current_trainer_target_misaligned,
        total_rows_replay_comparable=int(len(comparable_rows.index)),
    )
    next_target_promotion_decision_payload = _build_next_target_promotion_decision_payload(
        summary_payload=summary_payload,
        next_target_refinement_candidate_payload=next_target_refinement_candidate_payload,
    )

    return {
        "summary_frame": summary_frame,
        "summary_payload": summary_payload,
        "bucket_ranking_frame": bucket_ranking_frame,
        "bucket_ranking_payload": bucket_ranking_payload,
        "residual_examples_frame": residual_examples_frame,
        "residual_examples_payload": residual_examples_payload,
        "row_diagnostics_frame": diagnostic_frame,
        "divergence_diagnostics_frame": diagnostic_frame,
        "divergence_summary_payload": divergence_summary_payload,
        "next_target_refinement_candidate_payload": next_target_refinement_candidate_payload,
        "next_target_promotion_decision_payload": next_target_promotion_decision_payload,
    }


def _build_target_contract_diagnostic_frame(rows: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        rows,
        (
            "stock_basis_units",
            "demand_reference_units",
            "actual_units_sold",
            "unit_cost",
            "raw_predicted_units_total_promo",
            "calibrated_predicted_units_total_promo",
            "policy_adjusted_predicted_units_total_promo",
            "actual_overallocation_flag",
            "replay_measurement_eligible_flag",
            "replay_exclusion_reason",
            "historical_allocated_units",
            "realised_units_sold_promo",
            "replay_unit_cost",
        ),
        context="target contract analysis",
    )

    stock_basis_units = pd.to_numeric(rows["stock_basis_units"], errors="coerce")
    demand_reference_units = pd.to_numeric(rows["demand_reference_units"], errors="coerce")
    actual_units_sold = pd.to_numeric(rows["actual_units_sold"], errors="coerce")
    unit_cost = pd.to_numeric(rows["unit_cost"], errors="coerce").fillna(0.0).clip(lower=0.0)
    raw_predicted_units = pd.to_numeric(rows["raw_predicted_units_total_promo"], errors="coerce")
    calibrated_predicted_units = pd.to_numeric(rows["calibrated_predicted_units_total_promo"], errors="coerce")
    policy_adjusted_predicted_units = pd.to_numeric(rows["policy_adjusted_predicted_units_total_promo"], errors="coerce")
    historical_allocated_units = pd.to_numeric(rows["historical_allocated_units"], errors="coerce")
    realised_units_sold_promo = pd.to_numeric(rows["realised_units_sold_promo"], errors="coerce")
    replay_unit_cost = pd.to_numeric(rows["replay_unit_cost"], errors="coerce").fillna(0.0).clip(lower=0.0)
    unit_cost = unit_cost.where(unit_cost.gt(0.0), replay_unit_cost).fillna(0.0).clip(lower=0.0)
    actual_overallocation_flag = pd.to_numeric(rows["actual_overallocation_flag"], errors="coerce").fillna(0.0).ge(0.5)
    replay_comparable_flag = pd.to_numeric(rows["replay_measurement_eligible_flag"], errors="coerce").fillna(0.0).ge(1.0)
    historical_target_valid_flag = pd.to_numeric(
        rows.get("target_historical_allocation_target_valid_flag", rows["replay_measurement_eligible_flag"]),
        errors="coerce",
    ).fillna(0.0).ge(1.0)
    replay_exclusion_reason = rows["replay_exclusion_reason"].astype(str)

    trainer_current_signed_units_delta = stock_basis_units - actual_units_sold
    trainer_current_excess_units = trainer_current_signed_units_delta.clip(lower=0.0)
    trainer_current_excess_capital = trainer_current_excess_units * unit_cost

    historical_allocation_signed_units_delta = (historical_allocated_units - realised_units_sold_promo).where(historical_target_valid_flag)
    historical_allocation_excess_units = pd.to_numeric(
        rows.get("target_historical_replay_excess_units", historical_allocation_signed_units_delta.clip(lower=0.0)),
        errors="coerce",
    ).where(historical_target_valid_flag)
    historical_allocation_excess_capital = pd.to_numeric(
        rows.get("target_historical_replay_excess_capital", historical_allocation_excess_units * replay_unit_cost),
        errors="coerce",
    ).where(historical_target_valid_flag)
    historical_overallocation_flag = pd.to_numeric(
        rows.get("target_historical_overallocation_flag", historical_allocation_signed_units_delta.gt(0.0).astype(float)),
        errors="coerce",
    ).where(historical_target_valid_flag).ge(0.5)

    raw_current_predicted_excess_units = (stock_basis_units - raw_predicted_units).clip(lower=0.0)
    raw_current_predicted_excess_capital = raw_current_predicted_excess_units * unit_cost
    calibrated_current_predicted_excess_units = (stock_basis_units - calibrated_predicted_units).clip(lower=0.0)
    calibrated_current_predicted_excess_capital = calibrated_current_predicted_excess_units * unit_cost
    policy_current_predicted_excess_units = (stock_basis_units - policy_adjusted_predicted_units).clip(lower=0.0)
    policy_current_predicted_excess_capital = policy_current_predicted_excess_units * unit_cost

    raw_historical_predicted_excess_units = (historical_allocated_units - raw_predicted_units).clip(lower=0.0).where(historical_target_valid_flag)
    raw_historical_predicted_excess_capital = raw_historical_predicted_excess_units * replay_unit_cost
    calibrated_historical_predicted_excess_units = (historical_allocated_units - calibrated_predicted_units).clip(lower=0.0).where(historical_target_valid_flag)
    calibrated_historical_predicted_excess_capital = calibrated_historical_predicted_excess_units * replay_unit_cost
    policy_historical_predicted_excess_units = (historical_allocated_units - policy_adjusted_predicted_units).clip(lower=0.0).where(historical_target_valid_flag)
    policy_historical_predicted_excess_capital = policy_historical_predicted_excess_units * replay_unit_cost

    raw_prediction_minus_realised_promo_units = (raw_predicted_units - realised_units_sold_promo).where(historical_target_valid_flag)
    calibrated_prediction_minus_realised_promo_units = (calibrated_predicted_units - realised_units_sold_promo).where(replay_comparable_flag)
    calibrated_prediction_excess_units = calibrated_prediction_minus_realised_promo_units.clip(lower=0.0)
    calibrated_prediction_excess_capital = calibrated_prediction_excess_units * replay_unit_cost

    policy_adjusted_prediction_minus_realised_promo_units = (policy_adjusted_predicted_units - realised_units_sold_promo).where(replay_comparable_flag)
    policy_adjusted_prediction_excess_units = policy_adjusted_prediction_minus_realised_promo_units.clip(lower=0.0)
    policy_adjusted_prediction_excess_capital = policy_adjusted_prediction_excess_units * replay_unit_cost

    current_contract_valid_flag = stock_basis_units.notna() & actual_units_sold.notna() & unit_cost.gt(0.0)
    both_contract_valid_flag = current_contract_valid_flag & historical_target_valid_flag

    trainer_vs_historical_excess_units_gap = (trainer_current_excess_units - historical_allocation_excess_units).where(both_contract_valid_flag)
    trainer_vs_historical_excess_capital_gap = (trainer_current_excess_capital - historical_allocation_excess_capital).where(both_contract_valid_flag)
    calibrated_vs_historical_excess_units_gap = (calibrated_prediction_excess_units - historical_allocation_excess_units).where(both_contract_valid_flag)
    calibrated_vs_historical_excess_capital_gap = (calibrated_prediction_excess_capital - historical_allocation_excess_capital).where(both_contract_valid_flag)
    policy_vs_historical_excess_units_gap = (policy_adjusted_prediction_excess_units - historical_allocation_excess_units).where(both_contract_valid_flag)
    policy_vs_historical_excess_capital_gap = (policy_adjusted_prediction_excess_capital - historical_allocation_excess_capital).where(both_contract_valid_flag)

    stock_basis_proxy_mismatch_units = (stock_basis_units - historical_allocated_units).where(both_contract_valid_flag)
    realised_promo_units_mismatch_units = (actual_units_sold - realised_units_sold_promo).where(both_contract_valid_flag)
    cost_basis_mismatch_per_unit = (unit_cost - replay_unit_cost).where(both_contract_valid_flag)
    demand_reference_mismatch_units = (demand_reference_units - realised_units_sold_promo).where(both_contract_valid_flag)

    overallocation_flag_disagreement_flag = (
        actual_overallocation_flag.ne(historical_overallocation_flag.fillna(False))
        & both_contract_valid_flag
    )
    target_contract_signed_units_difference = (trainer_current_excess_units - historical_allocation_excess_units).where(both_contract_valid_flag)
    target_contract_absolute_units_difference = target_contract_signed_units_difference.abs()

    stock_basis_proxy_mismatch_capital_component_abs = (stock_basis_proxy_mismatch_units.abs() * replay_unit_cost).fillna(0.0)
    realised_promo_units_mismatch_capital_component_abs = (realised_promo_units_mismatch_units.abs() * replay_unit_cost).fillna(0.0)
    cost_basis_mismatch_capital_component_abs = (cost_basis_mismatch_per_unit.abs() * historical_allocation_excess_units.fillna(0.0)).fillna(0.0)
    demand_reference_mismatch_capital_component_abs = (
        demand_reference_mismatch_units.abs() * replay_unit_cost
    ).where(overallocation_flag_disagreement_flag, 0.0).fillna(0.0)

    dominant_divergence_driver = pd.Series(
        _TARGET_CONTRACT_DIVERGENCE_DRIVER_NO_MATERIAL,
        index=rows.index,
        dtype="object",
    )
    dominant_divergence_driver = dominant_divergence_driver.mask(
        historical_allocated_units.isna(),
        _TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_HISTORICAL,
    )
    dominant_divergence_driver = dominant_divergence_driver.mask(
        historical_allocated_units.notna() & realised_units_sold_promo.isna(),
        _TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_REALISED,
    )
    dominant_divergence_driver = dominant_divergence_driver.mask(
        dominant_divergence_driver.eq(_TARGET_CONTRACT_DIVERGENCE_DRIVER_NO_MATERIAL)
        & replay_comparable_flag.eq(False)
        & replay_unit_cost.le(0.0),
        _TARGET_CONTRACT_DIVERGENCE_DRIVER_COST,
    )

    driver_scores = pd.DataFrame(
        {
            _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS: stock_basis_proxy_mismatch_capital_component_abs,
            _TARGET_CONTRACT_DIVERGENCE_DRIVER_REALISED_PROMO: realised_promo_units_mismatch_capital_component_abs,
            _TARGET_CONTRACT_DIVERGENCE_DRIVER_COST: cost_basis_mismatch_capital_component_abs,
            _TARGET_CONTRACT_DIVERGENCE_DRIVER_DEMAND_REFERENCE: demand_reference_mismatch_capital_component_abs,
        },
        index=rows.index,
    )
    top_driver = driver_scores.idxmax(axis=1)
    top_driver_score = driver_scores.max(axis=1)
    material_divergence_mask = (
        both_contract_valid_flag
        & (
            trainer_vs_historical_excess_units_gap.abs().fillna(0.0).gt(0.0)
            | trainer_vs_historical_excess_capital_gap.abs().fillna(0.0).gt(0.0)
            | overallocation_flag_disagreement_flag
        )
        & top_driver_score.gt(0.0)
    )
    dominant_divergence_driver = dominant_divergence_driver.where(~material_divergence_mask, top_driver)
    divergence_severity_bucket = pd.Series("not_comparable", index=rows.index, dtype="object")
    divergence_severity_bucket = divergence_severity_bucket.mask(both_contract_valid_flag & target_contract_absolute_units_difference.fillna(0.0).eq(0.0), "none")
    divergence_severity_bucket = divergence_severity_bucket.mask(both_contract_valid_flag & target_contract_absolute_units_difference.fillna(0.0).gt(0.0) & target_contract_absolute_units_difference.fillna(0.0).le(1.0), "low")
    divergence_severity_bucket = divergence_severity_bucket.mask(both_contract_valid_flag & target_contract_absolute_units_difference.fillna(0.0).gt(1.0) & target_contract_absolute_units_difference.fillna(0.0).le(5.0), "medium")
    divergence_severity_bucket = divergence_severity_bucket.mask(both_contract_valid_flag & target_contract_absolute_units_difference.fillna(0.0).gt(5.0), "high")

    return pd.DataFrame(
        {
            "promotion_row_key": rows.get("promotion_row_key", pd.Series("", index=rows.index)).astype(str),
            "store_number": rows.get("store_number", pd.Series("", index=rows.index)).astype(str),
            "sku_number": rows.get("sku_number", pd.Series("", index=rows.index)).astype(str),
            "split_name": rows.get("split_name", pd.Series("", index=rows.index)).astype(str),
            "target_contract_replay_comparable_flag": replay_comparable_flag.astype(float),
            "current_contract_valid_flag": current_contract_valid_flag.astype(float),
            "historical_contract_valid_flag": historical_target_valid_flag.astype(float),
            "both_contract_valid_flag": both_contract_valid_flag.astype(float),
            "replay_exclusion_reason": replay_exclusion_reason,
            "dominant_divergence_driver": dominant_divergence_driver,
            "divergence_driver": dominant_divergence_driver,
            "divergence_severity_bucket": divergence_severity_bucket,
            "stock_basis_units": stock_basis_units,
            "historical_allocated_units": historical_allocated_units,
            "target_historical_allocation_units": pd.to_numeric(rows.get("target_historical_allocation_units", historical_allocated_units), errors="coerce"),
            "actual_units_sold": actual_units_sold,
            "realised_units_sold_promo": realised_units_sold_promo,
            "demand_reference_units": demand_reference_units,
            "unit_cost": unit_cost,
            "replay_unit_cost": replay_unit_cost,
            "raw_predicted_units_total_promo": raw_predicted_units,
            "calibrated_predicted_units_total_promo": calibrated_predicted_units,
            "policy_adjusted_predicted_units_total_promo": policy_adjusted_predicted_units,
            "current_trainer_target_value": trainer_current_excess_units,
            "historical_allocation_target_value": historical_allocation_excess_units,
            "target_contract_signed_difference": target_contract_signed_units_difference,
            "target_contract_absolute_difference": target_contract_absolute_units_difference,
            "trainer_current_signed_units_delta": trainer_current_signed_units_delta,
            "historical_allocation_signed_units_delta": historical_allocation_signed_units_delta,
            "raw_prediction_minus_realised_promo_units": raw_prediction_minus_realised_promo_units,
            "calibrated_prediction_minus_realised_promo_units": calibrated_prediction_minus_realised_promo_units,
            "policy_adjusted_prediction_minus_realised_promo_units": policy_adjusted_prediction_minus_realised_promo_units,
            "trainer_current_excess_units": trainer_current_excess_units,
            "historical_allocation_excess_units": historical_allocation_excess_units,
            "raw_current_predicted_excess_units": raw_current_predicted_excess_units,
            "calibrated_current_predicted_excess_units": calibrated_current_predicted_excess_units,
            "policy_current_predicted_excess_units": policy_current_predicted_excess_units,
            "raw_historical_predicted_excess_units": raw_historical_predicted_excess_units,
            "calibrated_historical_predicted_excess_units": calibrated_historical_predicted_excess_units,
            "policy_historical_predicted_excess_units": policy_historical_predicted_excess_units,
            "calibrated_prediction_excess_units": calibrated_prediction_excess_units,
            "policy_adjusted_prediction_excess_units": policy_adjusted_prediction_excess_units,
            "trainer_current_excess_capital": trainer_current_excess_capital,
            "historical_allocation_excess_capital": historical_allocation_excess_capital,
            "raw_current_predicted_excess_capital": raw_current_predicted_excess_capital,
            "calibrated_current_predicted_excess_capital": calibrated_current_predicted_excess_capital,
            "policy_current_predicted_excess_capital": policy_current_predicted_excess_capital,
            "raw_historical_predicted_excess_capital": raw_historical_predicted_excess_capital,
            "calibrated_historical_predicted_excess_capital": calibrated_historical_predicted_excess_capital,
            "policy_historical_predicted_excess_capital": policy_historical_predicted_excess_capital,
            "calibrated_prediction_excess_capital": calibrated_prediction_excess_capital,
            "policy_adjusted_prediction_excess_capital": policy_adjusted_prediction_excess_capital,
            "trainer_vs_historical_excess_units_gap": trainer_vs_historical_excess_units_gap,
            "trainer_vs_historical_excess_units_gap_abs": trainer_vs_historical_excess_units_gap.abs(),
            "trainer_vs_historical_excess_capital_gap": trainer_vs_historical_excess_capital_gap,
            "trainer_vs_historical_excess_capital_gap_abs": trainer_vs_historical_excess_capital_gap.abs(),
            "calibrated_vs_historical_excess_units_gap": calibrated_vs_historical_excess_units_gap,
            "calibrated_vs_historical_excess_units_gap_abs": calibrated_vs_historical_excess_units_gap.abs(),
            "calibrated_vs_historical_excess_capital_gap": calibrated_vs_historical_excess_capital_gap,
            "calibrated_vs_historical_excess_capital_gap_abs": calibrated_vs_historical_excess_capital_gap.abs(),
            "policy_vs_historical_excess_units_gap": policy_vs_historical_excess_units_gap,
            "policy_vs_historical_excess_units_gap_abs": policy_vs_historical_excess_units_gap.abs(),
            "policy_vs_historical_excess_capital_gap": policy_vs_historical_excess_capital_gap,
            "policy_vs_historical_excess_capital_gap_abs": policy_vs_historical_excess_capital_gap.abs(),
            "stock_basis_proxy_mismatch_units": stock_basis_proxy_mismatch_units,
            "realised_promo_units_mismatch_units": realised_promo_units_mismatch_units,
            "cost_basis_mismatch_per_unit": cost_basis_mismatch_per_unit,
            "demand_reference_mismatch_units": demand_reference_mismatch_units,
            "stock_basis_proxy_mismatch_capital_component_abs": stock_basis_proxy_mismatch_capital_component_abs,
            "realised_promo_units_mismatch_capital_component_abs": realised_promo_units_mismatch_capital_component_abs,
            "cost_basis_mismatch_capital_component_abs": cost_basis_mismatch_capital_component_abs,
            "demand_reference_mismatch_capital_component_abs": demand_reference_mismatch_capital_component_abs,
            "current_overallocation_flag": actual_overallocation_flag.astype(float),
            "historical_overallocation_flag": historical_overallocation_flag.fillna(False).astype(float),
            "overallocation_flag_disagreement_flag": overallocation_flag_disagreement_flag.astype(float),
        },
        index=rows.index,
    )


def _target_contract_metric_block(
    rows: pd.DataFrame,
    *,
    signed_units_column: str,
    excess_units_column: str,
    excess_capital_column: str,
) -> dict[str, float]:
    signed_units = pd.to_numeric(rows.get(signed_units_column, pd.Series(dtype="float64")), errors="coerce")
    excess_units = pd.to_numeric(rows.get(excess_units_column, pd.Series(dtype="float64")), errors="coerce")
    excess_capital = pd.to_numeric(rows.get(excess_capital_column, pd.Series(dtype="float64")), errors="coerce")
    valid_rows = rows.loc[signed_units.notna() & excess_units.notna() & excess_capital.notna()]
    signed_units = pd.to_numeric(valid_rows.get(signed_units_column, pd.Series(dtype="float64")), errors="coerce")
    excess_units = pd.to_numeric(valid_rows.get(excess_units_column, pd.Series(dtype="float64")), errors="coerce")
    excess_capital = pd.to_numeric(valid_rows.get(excess_capital_column, pd.Series(dtype="float64")), errors="coerce")
    return {
        "row_count": int(len(valid_rows.index)),
        "mean_signed_units_delta": float(signed_units.mean()) if not valid_rows.empty else 0.0,
        "median_signed_units_delta": float(signed_units.median()) if not valid_rows.empty else 0.0,
        "mean_abs_units_delta": float(signed_units.abs().mean()) if not valid_rows.empty else 0.0,
        "median_abs_units_delta": float(signed_units.abs().median()) if not valid_rows.empty else 0.0,
        "excess_units_mean": float(excess_units.mean()) if not valid_rows.empty else 0.0,
        "excess_units_total": float(excess_units.sum()) if not valid_rows.empty else 0.0,
        "excess_capital_mean": float(excess_capital.mean()) if not valid_rows.empty else 0.0,
        "excess_capital_total": float(excess_capital.sum()) if not valid_rows.empty else 0.0,
        "positive_excess_row_count": int(excess_units.gt(0.0).sum()) if not valid_rows.empty else 0,
        "under_target_row_count": int(signed_units.lt(0.0).sum()) if not valid_rows.empty else 0,
    }


def _target_contract_prediction_metric_block(
    rows: pd.DataFrame,
    *,
    target_excess_units_column: str,
    target_excess_capital_column: str,
    target_flag_column: str,
    prediction_specs: tuple[tuple[str, str, str], ...],
) -> dict[str, dict[str, float]]:
    target_excess_units = pd.to_numeric(rows.get(target_excess_units_column, pd.Series(dtype="float64")), errors="coerce")
    target_excess_capital = pd.to_numeric(rows.get(target_excess_capital_column, pd.Series(dtype="float64")), errors="coerce")
    target_flag = pd.to_numeric(rows.get(target_flag_column, pd.Series(dtype="float64")), errors="coerce")
    metric_blocks: dict[str, dict[str, float]] = {}
    for prediction_name, predicted_excess_units_column, predicted_excess_capital_column in prediction_specs:
        predicted_excess_units = pd.to_numeric(rows.get(predicted_excess_units_column, pd.Series(dtype="float64")), errors="coerce")
        predicted_excess_capital = pd.to_numeric(rows.get(predicted_excess_capital_column, pd.Series(dtype="float64")), errors="coerce")
        valid_mask = (
            target_excess_units.notna()
            & target_excess_capital.notna()
            & target_flag.notna()
            & predicted_excess_units.notna()
            & predicted_excess_capital.notna()
        )
        if not bool(valid_mask.any()):
            metric_blocks[prediction_name] = {
                "row_count": 0,
                "mae": 0.0,
                "rmse": 0.0,
                "mean_signed_error": 0.0,
                "excess_units_error_mae": 0.0,
                "excess_units_error_rmse": 0.0,
                "excess_units_error_mean_signed": 0.0,
                "excess_capital_error_mae": 0.0,
                "excess_capital_error_rmse": 0.0,
                "excess_capital_error_mean_signed": 0.0,
                "overallocation_flag_precision": 0.0,
                "overallocation_flag_recall": 0.0,
            }
            continue
        units_error = predicted_excess_units.loc[valid_mask] - target_excess_units.loc[valid_mask]
        capital_error = predicted_excess_capital.loc[valid_mask] - target_excess_capital.loc[valid_mask]
        predicted_flag = predicted_excess_units.loc[valid_mask].gt(0.0).astype(int)
        actual_flag = target_flag.loc[valid_mask].ge(0.5).astype(int)
        metric_blocks[prediction_name] = {
            "row_count": int(valid_mask.sum()),
            "mae": float(units_error.abs().mean()),
            "rmse": float(np.sqrt(np.mean(np.square(units_error)))),
            "mean_signed_error": float(units_error.mean()),
            "excess_units_error_mae": float(units_error.abs().mean()),
            "excess_units_error_rmse": float(np.sqrt(np.mean(np.square(units_error)))),
            "excess_units_error_mean_signed": float(units_error.mean()),
            "excess_capital_error_mae": float(capital_error.abs().mean()),
            "excess_capital_error_rmse": float(np.sqrt(np.mean(np.square(capital_error)))),
            "excess_capital_error_mean_signed": float(capital_error.mean()),
            "overallocation_flag_precision": float(precision_score(actual_flag, predicted_flag, zero_division=0)),
            "overallocation_flag_recall": float(recall_score(actual_flag, predicted_flag, zero_division=0)),
        }
    return metric_blocks


def _target_contract_gap_metric_block(
    rows: pd.DataFrame,
    *,
    units_gap_column: str,
    capital_gap_column: str,
) -> dict[str, float]:
    units_gap = pd.to_numeric(rows.get(units_gap_column, pd.Series(dtype="float64")), errors="coerce")
    capital_gap = pd.to_numeric(rows.get(capital_gap_column, pd.Series(dtype="float64")), errors="coerce")
    valid_rows = rows.loc[units_gap.notna() & capital_gap.notna()]
    units_gap = pd.to_numeric(valid_rows.get(units_gap_column, pd.Series(dtype="float64")), errors="coerce")
    capital_gap = pd.to_numeric(valid_rows.get(capital_gap_column, pd.Series(dtype="float64")), errors="coerce")
    return {
        "row_count": int(len(valid_rows.index)),
        "units_gap_mean": float(units_gap.mean()) if not valid_rows.empty else 0.0,
        "units_gap_abs_mean": float(units_gap.abs().mean()) if not valid_rows.empty else 0.0,
        "units_gap_abs_total": float(units_gap.abs().sum()) if not valid_rows.empty else 0.0,
        "capital_gap_mean": float(capital_gap.mean()) if not valid_rows.empty else 0.0,
        "capital_gap_abs_mean": float(capital_gap.abs().mean()) if not valid_rows.empty else 0.0,
        "capital_gap_abs_total": float(capital_gap.abs().sum()) if not valid_rows.empty else 0.0,
    }


def _target_contract_bucket_ranking_row(
    *,
    bucket_name: str,
    bucket_rows: pd.DataFrame,
    total_capital_gap_abs: float,
) -> dict[str, object]:
    comparable_rows = bucket_rows.loc[
        pd.to_numeric(bucket_rows.get("target_contract_replay_comparable_flag", pd.Series(0.0, index=bucket_rows.index)), errors="coerce").fillna(0.0).ge(1.0)
    ].copy()
    trainer_gap_abs = pd.to_numeric(comparable_rows.get("trainer_vs_historical_excess_capital_gap_abs", pd.Series(0.0, index=comparable_rows.index)), errors="coerce").fillna(0.0)
    trainer_units_gap_abs = pd.to_numeric(comparable_rows.get("trainer_vs_historical_excess_units_gap_abs", pd.Series(0.0, index=comparable_rows.index)), errors="coerce").fillna(0.0)
    current_flag_disagreement = pd.to_numeric(comparable_rows.get("overallocation_flag_disagreement_flag", pd.Series(0.0, index=comparable_rows.index)), errors="coerce").fillna(0.0)
    return {
        "bucket_name": bucket_name,
        "row_count": int(len(bucket_rows.index)),
        "replay_comparable_row_count": int(len(comparable_rows.index)),
        "trainer_current_excess_capital_mean": float(pd.to_numeric(comparable_rows.get("trainer_current_excess_capital", pd.Series(0.0, index=comparable_rows.index)), errors="coerce").fillna(0.0).mean()) if not comparable_rows.empty else 0.0,
        "historical_allocation_excess_capital_mean": float(pd.to_numeric(comparable_rows.get("historical_allocation_excess_capital", pd.Series(0.0, index=comparable_rows.index)), errors="coerce").fillna(0.0).mean()) if not comparable_rows.empty else 0.0,
        "calibrated_prediction_excess_capital_mean": float(pd.to_numeric(comparable_rows.get("calibrated_prediction_excess_capital", pd.Series(0.0, index=comparable_rows.index)), errors="coerce").fillna(0.0).mean()) if not comparable_rows.empty else 0.0,
        "policy_adjusted_prediction_excess_capital_mean": float(pd.to_numeric(comparable_rows.get("policy_adjusted_prediction_excess_capital", pd.Series(0.0, index=comparable_rows.index)), errors="coerce").fillna(0.0).mean()) if not comparable_rows.empty else 0.0,
        "trainer_vs_historical_excess_units_gap_abs_mean": float(trainer_units_gap_abs.mean()) if not comparable_rows.empty else 0.0,
        "trainer_vs_historical_excess_capital_gap_abs_mean": float(trainer_gap_abs.mean()) if not comparable_rows.empty else 0.0,
        "trainer_vs_historical_excess_capital_gap_abs_total": float(trainer_gap_abs.sum()) if not comparable_rows.empty else 0.0,
        "share_of_total_trainer_vs_historical_excess_capital_gap_abs": (float(trainer_gap_abs.sum()) / total_capital_gap_abs) if total_capital_gap_abs > 0.0 else 0.0,
        "overallocation_flag_disagreement_rate": float(current_flag_disagreement.mean()) if not comparable_rows.empty else 0.0,
    }


def _build_target_contract_residual_examples_frame(diagnostic_frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "dominant_divergence_driver",
        "promotion_row_key",
        "store_number",
        "sku_number",
        "split_name",
        "stock_basis_units",
        "historical_allocated_units",
        "actual_units_sold",
        "realised_units_sold_promo",
        "demand_reference_units",
        "unit_cost",
        "replay_unit_cost",
        "trainer_current_signed_units_delta",
        "historical_allocation_signed_units_delta",
        "calibrated_prediction_minus_realised_promo_units",
        "policy_adjusted_prediction_minus_realised_promo_units",
        "trainer_vs_historical_excess_units_gap_abs",
        "trainer_vs_historical_excess_capital_gap_abs",
        "calibrated_vs_historical_excess_capital_gap_abs",
        "policy_vs_historical_excess_capital_gap_abs",
        "overallocation_flag_disagreement_flag",
    ]
    residual_rows = diagnostic_frame.loc[
        pd.to_numeric(diagnostic_frame.get("target_contract_replay_comparable_flag", pd.Series(0.0, index=diagnostic_frame.index)), errors="coerce").fillna(0.0).ge(1.0)
        & diagnostic_frame.get("dominant_divergence_driver", pd.Series(_TARGET_CONTRACT_DIVERGENCE_DRIVER_NO_MATERIAL, index=diagnostic_frame.index)).astype(str).ne(_TARGET_CONTRACT_DIVERGENCE_DRIVER_NO_MATERIAL)
    ].copy()
    if residual_rows.empty:
        return pd.DataFrame(columns=columns)
    residual_rows = residual_rows.sort_values(
        ["trainer_vs_historical_excess_capital_gap_abs", "trainer_vs_historical_excess_units_gap_abs", "policy_vs_historical_excess_capital_gap_abs"],
        ascending=[False, False, False],
        kind="mergesort",
    ).head(_TARGET_CONTRACT_RESIDUAL_ROW_LIMIT)
    return residual_rows.loc[:, columns].reset_index(drop=True)


def _build_target_contract_divergence_summary_payload(
    diagnostic_frame: pd.DataFrame,
    *,
    bucket_ranking_frame: pd.DataFrame,
) -> dict[str, object]:
    comparable_rows = diagnostic_frame.loc[
        pd.to_numeric(diagnostic_frame.get("target_contract_replay_comparable_flag", pd.Series(0.0, index=diagnostic_frame.index)), errors="coerce").fillna(0.0).ge(1.0)
    ].copy()
    material_rows = comparable_rows.loc[
        comparable_rows.get("dominant_divergence_driver", pd.Series(_TARGET_CONTRACT_DIVERGENCE_DRIVER_NO_MATERIAL, index=comparable_rows.index)).astype(str).ne(_TARGET_CONTRACT_DIVERGENCE_DRIVER_NO_MATERIAL)
    ]
    top_divergence_driver = _top_target_contract_bucket_name(
        bucket_ranking_frame,
        value_column="trainer_vs_historical_excess_capital_gap_abs_total",
    )
    return {
        "row_scope": "out_of_sample_validation_and_test",
        "total_rows_scored": int(len(diagnostic_frame.index)),
        "total_rows_replay_comparable": int(len(comparable_rows.index)),
        "total_rows_excluded_from_contract_comparison": int(len(diagnostic_frame.index) - len(comparable_rows.index)),
        "material_trainer_vs_historical_divergence_row_count": int(len(material_rows.index)),
        "top_divergence_driver": top_divergence_driver,
        "by_driver": {
            str(row["bucket_name"]): row.to_dict()
            for _, row in bucket_ranking_frame.iterrows()
        },
    }


def _build_next_target_refinement_candidate_payload(
    *,
    bucket_ranking_frame: pd.DataFrame,
    current_trainer_target_misaligned: bool,
    total_rows_replay_comparable: int,
) -> dict[str, object]:
    considered_rows = bucket_ranking_frame.loc[
        bucket_ranking_frame["bucket_name"].astype(str).isin(
            [
                _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS,
                _TARGET_CONTRACT_DIVERGENCE_DRIVER_REALISED_PROMO,
                _TARGET_CONTRACT_DIVERGENCE_DRIVER_COST,
                _TARGET_CONTRACT_DIVERGENCE_DRIVER_DEMAND_REFERENCE,
                _TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_HISTORICAL,
                _TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_REALISED,
            ]
        )
    ].copy()
    considered_rows["trainer_vs_historical_excess_capital_gap_abs_total"] = pd.to_numeric(
        considered_rows["trainer_vs_historical_excess_capital_gap_abs_total"], errors="coerce"
    ).fillna(0.0)
    considered_rows["share_of_total_trainer_vs_historical_excess_capital_gap_abs"] = pd.to_numeric(
        considered_rows["share_of_total_trainer_vs_historical_excess_capital_gap_abs"], errors="coerce"
    ).fillna(0.0)
    considered_rows["replay_comparable_row_count"] = pd.to_numeric(
        considered_rows["replay_comparable_row_count"], errors="coerce"
    ).fillna(0.0)
    considered_rows = considered_rows.sort_values(
        ["trainer_vs_historical_excess_capital_gap_abs_total", "replay_comparable_row_count", "bucket_name"],
        ascending=[False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)

    next_target_refinement_candidate = "none"
    explanation = _target_contract_null_candidate_explanation(considered_rows)
    replay_target_design_position = "diagnostics_only_for_now"
    if not considered_rows.empty:
        top_row = considered_rows.iloc[0].to_dict()
        second_total = float(considered_rows.iloc[1]["trainer_vs_historical_excess_capital_gap_abs_total"]) if len(considered_rows.index) > 1 else 0.0
        top_bucket = str(top_row["bucket_name"])
        top_share = float(top_row["share_of_total_trainer_vs_historical_excess_capital_gap_abs"])
        top_row_count = int(top_row["replay_comparable_row_count"])

        if top_bucket in {
            _TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_HISTORICAL,
            _TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_REALISED,
        }:
            explanation = "Missing historical allocation or realised promo evidence dominates, so no honest target refinement candidate can be nominated from this pass."
        elif top_row_count < _TARGET_CONTRACT_NEXT_CANDIDATE_MIN_ROW_COUNT:
            explanation = "No divergence driver has enough comparable rows to justify a target refinement decision."
        elif top_share < _TARGET_CONTRACT_NEXT_CANDIDATE_MIN_CAPITAL_GAP_SHARE:
            explanation = "Target-contract disagreement is too diffuse across drivers to justify a single refinement candidate."
        elif second_total >= (float(top_row["trainer_vs_historical_excess_capital_gap_abs_total"]) * _TARGET_CONTRACT_NEXT_CANDIDATE_DIFFUSE_RELATIVE_SHARE):
            explanation = "Multiple divergence drivers are too close in weight, so the next target refinement candidate remains diffuse."
        else:
            if top_bucket == _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS:
                next_target_refinement_candidate = "historical_allocation_target_refinement"
                replay_target_design_position = "candidate_for_target_design"
                explanation = "Stock-basis proxy mismatch is the leading cause of contract disagreement, so the next honest refinement is to move target design closer to historical allocation truth."
            elif top_bucket in {
                _TARGET_CONTRACT_DIVERGENCE_DRIVER_REALISED_PROMO,
                _TARGET_CONTRACT_DIVERGENCE_DRIVER_DEMAND_REFERENCE,
            }:
                next_target_refinement_candidate = "realised_promo_units_target_refinement"
                replay_target_design_position = "candidate_for_target_design"
                explanation = "Realised-promo-unit disagreement dominates the contract gap, so the next honest refinement is to tighten target design around realised promo truth rather than the current proxy contract."
            elif top_bucket == _TARGET_CONTRACT_DIVERGENCE_DRIVER_COST:
                next_target_refinement_candidate = "cost_basis_refinement"
                replay_target_design_position = "diagnostics_only_for_now"
                explanation = "Cost basis noise dominates the contract disagreement, so the next honest refinement is cost basis cleanup rather than target redesign or policy changes."

    return {
        "row_scope": "out_of_sample_validation_and_test",
        "current_trainer_target_misaligned_with_business_mistake": current_trainer_target_misaligned,
        "total_rows_replay_comparable": int(total_rows_replay_comparable),
        "next_target_refinement_candidate": next_target_refinement_candidate,
        "replay_target_design_position": replay_target_design_position,
        "policy_work_should_remain_paused": True,
        "explanation": explanation,
        "considered_buckets": considered_rows.to_dict(orient="records"),
    }


def _build_next_target_promotion_decision_payload(
    *,
    summary_payload: dict[str, object],
    next_target_refinement_candidate_payload: dict[str, object],
) -> dict[str, object]:
    valid_row_counts = summary_payload.get("valid_row_counts", {})
    comparison_blocks = summary_payload.get("comparison_blocks", {})
    current_gap_block = comparison_blocks.get("current_trainer_vs_historical_allocation_contract", {}) if isinstance(comparison_blocks, dict) else {}
    total_rows = int(summary_payload.get("total_rows_scored", 0))
    valid_both_rows = int(valid_row_counts.get("valid_under_both_contracts", 0)) if isinstance(valid_row_counts, dict) else 0
    evidence_coverage_rate = (valid_both_rows / total_rows) if total_rows > 0 else 0.0
    current_gap_abs_total = float(current_gap_block.get("capital_gap_abs_total", 0.0)) if isinstance(current_gap_block, dict) else 0.0
    current_gap_abs_mean = float(current_gap_block.get("capital_gap_abs_mean", 0.0)) if isinstance(current_gap_block, dict) else 0.0
    current_misaligned = bool(summary_payload.get("current_trainer_target_misaligned_with_business_mistake", False))
    candidate = str(next_target_refinement_candidate_payload.get("next_target_refinement_candidate", "none"))
    replay_target_design_position = str(next_target_refinement_candidate_payload.get("replay_target_design_position", "diagnostics_only_for_now"))

    decision = "diagnostics_only"
    should_become_candidate = False
    should_replace_now = False
    more_evidence_needed = True
    explanation = "Historical allocation target evidence is not strong enough to move beyond diagnostics."
    if (
        current_misaligned
        and candidate == "historical_allocation_target_refinement"
        and replay_target_design_position == "candidate_for_target_design"
        and evidence_coverage_rate >= 0.95
        and current_gap_abs_total > 0.0
    ):
        decision = "candidate_for_target_design"
        should_become_candidate = True
        more_evidence_needed = False
        explanation = "Historical allocation evidence is broad and the current stock-basis target materially disagrees with the observed allocation mistake, so this should become the next target-design candidate."

    return {
        "row_scope": "out_of_sample_validation_and_test",
        "should_historical_allocation_target_refinement_remain_diagnostics_only": decision == "diagnostics_only",
        "should_historical_allocation_target_refinement_become_candidate_for_target_design": should_become_candidate,
        "should_historical_allocation_target_refinement_replace_current_trainer_contract_now": should_replace_now,
        "more_evidence_needed_before_replacement": more_evidence_needed,
        "decision": decision,
        "evidence_coverage_rate": evidence_coverage_rate,
        "valid_under_both_contracts": valid_both_rows,
        "total_rows_scored": total_rows,
        "current_trainer_vs_historical_capital_gap_abs_total": current_gap_abs_total,
        "current_trainer_vs_historical_capital_gap_abs_mean": current_gap_abs_mean,
        "top_divergence_driver": summary_payload.get("top_divergence_driver"),
        "policy_remains_paused": True,
        "policy_is_dominant_bottleneck": False,
        "target_contract_misalignment_is_dominant_bottleneck": current_misaligned,
        "explanation": explanation,
    }


def _target_contract_null_candidate_explanation(considered_rows: pd.DataFrame) -> str:
    if considered_rows.empty:
        return "No replay-comparable rows were available for target-contract analysis."
    top_row = considered_rows.iloc[0]
    top_bucket = str(top_row["bucket_name"])
    if top_bucket in {
        _TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_HISTORICAL,
        _TARGET_CONTRACT_DIVERGENCE_DRIVER_MISSING_REALISED,
    }:
        return "Missing replay evidence dominates, so target refinement should not be forced from this pass."
    if float(top_row["share_of_total_trainer_vs_historical_excess_capital_gap_abs"]) < _TARGET_CONTRACT_NEXT_CANDIDATE_MIN_CAPITAL_GAP_SHARE:
        return "Target-contract disagreement is too diffuse across drivers to justify a single refinement candidate."
    if len(considered_rows.index) > 1:
        second_total = float(considered_rows.iloc[1]["trainer_vs_historical_excess_capital_gap_abs_total"])
        if second_total >= (float(top_row["trainer_vs_historical_excess_capital_gap_abs_total"]) * _TARGET_CONTRACT_NEXT_CANDIDATE_DIFFUSE_RELATIVE_SHARE):
            return "Multiple divergence drivers are too close in weight, so no single next refinement area is honest."
    return "No single target-contract driver met the governed thresholds for an actionable refinement candidate."


def _top_target_contract_bucket_name(frame: pd.DataFrame, *, value_column: str) -> str | None:
    if frame.empty or value_column not in frame.columns:
        return None
    candidate_rows = frame.loc[
        frame["bucket_name"].astype(str).ne(_TARGET_CONTRACT_DIVERGENCE_DRIVER_NO_MATERIAL)
        & pd.to_numeric(frame[value_column], errors="coerce").fillna(0.0).gt(0.0)
    ].copy()
    if candidate_rows.empty:
        return None
    candidate_rows[value_column] = pd.to_numeric(candidate_rows[value_column], errors="coerce").fillna(0.0)
    if "row_count" in candidate_rows.columns:
        candidate_rows["row_count"] = pd.to_numeric(candidate_rows["row_count"], errors="coerce").fillna(0.0)
        candidate_rows = candidate_rows.sort_values(
            [value_column, "row_count", "bucket_name"],
            ascending=[False, False, True],
            kind="mergesort",
        )
    else:
        candidate_rows = candidate_rows.sort_values(
            [value_column, "bucket_name"],
            ascending=[False, True],
            kind="mergesort",
        )
    return str(candidate_rows.iloc[0]["bucket_name"])


def _top_policy_rule_name(frame: pd.DataFrame, *, value_column: str) -> str | None:
    if frame.empty or value_column not in frame.columns:
        return None
    positive_rows = frame.loc[pd.to_numeric(frame[value_column], errors="coerce").fillna(0.0).gt(0.0)].copy()
    if positive_rows.empty:
        return None
    positive_rows[value_column] = pd.to_numeric(positive_rows[value_column], errors="coerce").fillna(0.0)
    if "triggered_row_count" in positive_rows.columns:
        positive_rows["triggered_row_count"] = pd.to_numeric(positive_rows["triggered_row_count"], errors="coerce").fillna(0.0)
        positive_rows = positive_rows.sort_values(
            [value_column, "triggered_row_count", "rule_name"],
            ascending=[False, False, True],
            kind="mergesort",
        )
    else:
        positive_rows = positive_rows.sort_values(
            [value_column, "rule_name"],
            ascending=[False, True],
            kind="mergesort",
        )
    return str(positive_rows.iloc[0]["rule_name"])


def _require_columns(frame: pd.DataFrame, required_columns: tuple[str, ...], *, context: str) -> None:
    missing_columns = [column_name for column_name in required_columns if column_name not in frame.columns]
    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(f"{context} requires columns: {missing_text}")


def _ensure_historical_allocation_candidate_target_bundle(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    if any(column_name not in working.columns for column_name in _HISTORICAL_ALLOCATION_CANDIDATE_REQUIRED_COLUMNS):
        working = apply_ft_target_historical_allocation(working)
    _require_columns(
        working,
        _HISTORICAL_ALLOCATION_CANDIDATE_REQUIRED_COLUMNS,
        context="historical allocation candidate target mode",
    )
    valid_mask = pd.to_numeric(
        working["target_historical_allocation_target_valid_flag"],
        errors="coerce",
    ).fillna(0.0).ge(1.0)
    if not valid_mask.any():
        reason_counts = (
            working["target_historical_allocation_exclusion_reason"]
            .astype(str)
            .value_counts(dropna=False)
            .to_dict()
        )
        raise ValueError(
            "historical allocation candidate target mode has no valid historical allocation target rows; "
            f"exclusion reasons: {reason_counts}"
        )
    null_valid_columns = [
        column_name
        for column_name in _HISTORICAL_ALLOCATION_CANDIDATE_CORE_TARGET_COLUMNS
        if pd.to_numeric(working.loc[valid_mask, column_name], errors="coerce").isna().any()
    ]
    if null_valid_columns:
        raise ValueError(
            "historical allocation candidate target mode found null candidate target values on valid rows: "
            + ", ".join(sorted(null_valid_columns))
        )
    return working


def _coerce_split_mask(mask: pd.Series | np.ndarray, index: pd.Index) -> pd.Series:
    if isinstance(mask, pd.Series):
        return mask.reindex(index, fill_value=False).astype(bool)
    return pd.Series(mask, index=index).astype(bool)


def _first_available_numeric_candidate(frame: pd.DataFrame, candidate_columns: tuple[str, ...]) -> pd.Series:
    result = pd.Series(pd.NA, index=frame.index, dtype="Float64")
    for column_name in candidate_columns:
        if column_name in frame.columns:
            result = result.fillna(pd.to_numeric(frame[column_name], errors="coerce").astype("Float64"))
    return result


def _build_current_trainer_contract_target_frame(dataset: pd.DataFrame) -> pd.DataFrame:
    stock_basis_units = _first_available_numeric_candidate(
        dataset,
        (
            "stock_basis_units",
            "pl_allocation_qty",
            "pl_allocated",
            "store_adjusted_qty",
            "total_units_commited",
            "current_soh",
        ),
    )
    actual_units = _first_available_numeric_candidate(
        dataset,
        ("target_actual_units_sold", "actual_units_sold", "actual_units_sold_promo"),
    )
    if "target_overallocation_flag" in dataset.columns:
        overallocation_flag = pd.to_numeric(dataset["target_overallocation_flag"], errors="coerce").astype("Float64")
    else:
        overallocation_flag = stock_basis_units.gt(actual_units).astype("Float64")
    valid_flag = stock_basis_units.notna() & actual_units.notna() & overallocation_flag.notna()
    excess_units = (stock_basis_units - actual_units).clip(lower=0.0).where(valid_flag)
    return pd.DataFrame(
        {
            "valid_flag": valid_flag,
            "excess_units": excess_units,
            "overallocation_flag": overallocation_flag.where(valid_flag),
        },
        index=dataset.index,
    )


def _build_historical_allocation_candidate_target_frame(dataset: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        dataset,
        _HISTORICAL_ALLOCATION_CANDIDATE_REQUIRED_COLUMNS,
        context="historical allocation candidate target mode",
    )
    valid_flag = pd.to_numeric(
        dataset["target_historical_allocation_target_valid_flag"],
        errors="coerce",
    ).fillna(0.0).ge(1.0)
    excess_units = pd.to_numeric(dataset["target_historical_replay_excess_units"], errors="coerce").astype("Float64")
    overallocation_flag = pd.to_numeric(dataset["target_historical_overallocation_flag"], errors="coerce").astype("Float64")
    valid_flag = valid_flag & excess_units.notna() & overallocation_flag.notna()
    return pd.DataFrame(
        {
            "valid_flag": valid_flag,
            "excess_units": excess_units.where(valid_flag),
            "overallocation_flag": overallocation_flag.where(valid_flag),
        },
        index=dataset.index,
    )


def _build_target_mode_comparison_artifacts(
    *,
    target_mode: PromotionTrainerTargetMode,
    diagnostic_frame: pd.DataFrame,
    target_contract_summary_payload: dict[str, object],
    train_row_counts: dict[str, int],
    evaluation_row_count: int,
) -> dict[str, object]:
    comparable_mask = pd.to_numeric(
        diagnostic_frame["both_contract_valid_flag"],
        errors="coerce",
    ).fillna(0.0).ge(1.0)
    comparable_rows = diagnostic_frame.loc[comparable_mask].copy()
    valid_row_counts = target_contract_summary_payload.get("valid_row_counts", {})
    excluded_reason_counts = target_contract_summary_payload.get("excluded_historical_contract_reason_counts", {})
    comparison_blocks = {
        "current_trainer_contract_label_vs_historical_business_target": _target_mode_label_gap_metric_block(
            comparable_rows,
            units_gap_column="trainer_vs_historical_excess_units_gap_abs",
            capital_gap_column="trainer_vs_historical_excess_capital_gap_abs",
            flag_gap_column="overallocation_flag_disagreement_flag",
        ),
        "historical_allocation_candidate_label_vs_historical_business_target": _target_mode_zero_label_metric_block(
            comparable_rows
        ),
        "current_trainer_contract_shadow_model_vs_current_contract": _target_mode_shadow_metric_block(
            comparable_rows,
            prediction_units_column="current_contract_shadow_predicted_excess_units",
            prediction_capital_column="current_contract_shadow_predicted_excess_capital_on_current_cost",
            prediction_flag_column="current_contract_shadow_overallocation_flag",
            target_units_column="trainer_current_excess_units",
            target_capital_column="trainer_current_excess_capital",
            target_flag_column="current_overallocation_flag",
        ),
        "current_trainer_contract_shadow_model_vs_historical_business_target": _target_mode_shadow_metric_block(
            comparable_rows,
            prediction_units_column="current_contract_shadow_predicted_excess_units",
            prediction_capital_column="current_contract_shadow_predicted_excess_capital_on_historical_cost",
            prediction_flag_column="current_contract_shadow_overallocation_flag",
            target_units_column="historical_allocation_excess_units",
            target_capital_column="historical_allocation_excess_capital",
            target_flag_column="historical_overallocation_flag",
        ),
        "historical_allocation_candidate_shadow_model_vs_historical_business_target": _target_mode_shadow_metric_block(
            comparable_rows,
            prediction_units_column="historical_candidate_shadow_predicted_excess_units",
            prediction_capital_column="historical_candidate_shadow_predicted_excess_capital",
            prediction_flag_column="historical_candidate_shadow_overallocation_flag",
            target_units_column="historical_allocation_excess_units",
            target_capital_column="historical_allocation_excess_capital",
            target_flag_column="historical_overallocation_flag",
        ),
    }
    current_shadow_capital_mae = float(
        comparison_blocks["current_trainer_contract_shadow_model_vs_historical_business_target"]["excess_capital_mae"]
    )
    historical_shadow_capital_mae = float(
        comparison_blocks["historical_allocation_candidate_shadow_model_vs_historical_business_target"]["excess_capital_mae"]
    )
    shadow_capital_mae_improvement = current_shadow_capital_mae - historical_shadow_capital_mae
    total_current_label_capital_gap = float(
        comparison_blocks["current_trainer_contract_label_vs_historical_business_target"]["excess_capital_error_total"]
    )
    bucket_ranking_rows = [
        _target_mode_bucket_ranking_row(
            bucket_name=bucket_name,
            bucket_rows=diagnostic_frame.loc[
                diagnostic_frame["dominant_divergence_driver"].astype(str).eq(bucket_name)
            ],
            total_current_label_capital_gap=total_current_label_capital_gap,
        )
        for bucket_name in _TARGET_CONTRACT_DIVERGENCE_DRIVER_ORDER
    ]
    bucket_ranking_frame = pd.DataFrame(bucket_ranking_rows)
    if not bucket_ranking_frame.empty:
        bucket_ranking_frame = bucket_ranking_frame.sort_values(
            ["current_label_vs_historical_excess_capital_error_total", "row_count", "bucket_name"],
            ascending=[False, False, True],
            kind="mergesort",
        ).reset_index(drop=True)
    residual_examples_frame = _build_target_mode_residual_examples_frame(diagnostic_frame)
    summary_payload = {
        "row_scope": "out_of_sample_validation_and_test",
        "target_mode": target_mode,
        "target_modes_compared": ["current_trainer_contract", "historical_allocation_candidate"],
        "candidate_target_family": list(_HISTORICAL_ALLOCATION_CANDIDATE_CORE_TARGET_COLUMNS),
        "production_training_target_contract": DEFAULT_PROMOTION_TRAINER_TARGET_MODE,
        "production_training_target_was_replaced": False,
        "evaluation_row_count": int(evaluation_row_count),
        "valid_row_counts": valid_row_counts,
        "excluded_historical_contract_reason_counts": excluded_reason_counts,
        "shadow_training_row_counts": train_row_counts,
        "current_trainer_target_misaligned_with_business_mistake": bool(
            target_contract_summary_payload.get("current_trainer_target_misaligned_with_business_mistake", False)
        ),
        "top_divergence_driver": target_contract_summary_payload.get("top_divergence_driver"),
        "comparison_blocks": comparison_blocks,
        "shadow_model_candidate_vs_current_on_historical_business_target": {
            "current_shadow_excess_capital_mae": current_shadow_capital_mae,
            "historical_candidate_shadow_excess_capital_mae": historical_shadow_capital_mae,
            "candidate_capital_mae_improvement": shadow_capital_mae_improvement,
            "candidate_capital_mae_improvement_rate": (
                shadow_capital_mae_improvement / current_shadow_capital_mae
            ) if current_shadow_capital_mae > 0.0 else 0.0,
            "candidate_shadow_model_outperformed_current_shadow_model": bool(shadow_capital_mae_improvement > 0.0),
        },
        "policy_pause_conclusion": {
            "policy_remains_paused": True,
            "policy_is_dominant_bottleneck": False,
            "target_contract_misalignment_is_dominant_bottleneck": bool(
                target_contract_summary_payload.get("current_trainer_target_misaligned_with_business_mistake", False)
            ),
            "explanation": "Target-mode comparison is trainer-owned shadow evidence; policy rules remain unchanged and paused.",
        },
    }
    promotion_gate_payload = _build_target_contract_promotion_gate_payload(summary_payload)
    summary_payload["target_contract_promotion_gate"] = promotion_gate_payload
    return {
        "summary_payload": summary_payload,
        "summary_frame": _flatten_target_mode_summary_payload(summary_payload),
        "bucket_ranking_payload": {
            "row_scope": "out_of_sample_validation_and_test",
            "target_mode": target_mode,
            "ranking_rows": _json_ready_records(bucket_ranking_frame),
            "top_divergence_driver": summary_payload["top_divergence_driver"],
        },
        "bucket_ranking_frame": bucket_ranking_frame,
        "residual_examples_payload": {
            "row_scope": "out_of_sample_validation_and_test",
            "target_mode": target_mode,
            "top_row_limit": _TARGET_MODE_RESIDUAL_ROW_LIMIT,
            "row_count": int(len(residual_examples_frame.index)),
            "rows": _json_ready_records(residual_examples_frame),
        },
        "residual_examples_frame": residual_examples_frame,
        "promotion_gate_payload": promotion_gate_payload,
    }


def _target_mode_label_gap_metric_block(
    rows: pd.DataFrame,
    *,
    units_gap_column: str,
    capital_gap_column: str,
    flag_gap_column: str,
) -> dict[str, object]:
    row_count = int(len(rows.index))
    units_gap = pd.to_numeric(rows.get(units_gap_column, pd.Series(pd.NA, index=rows.index)), errors="coerce")
    capital_gap = pd.to_numeric(rows.get(capital_gap_column, pd.Series(pd.NA, index=rows.index)), errors="coerce")
    flag_gap = pd.to_numeric(rows.get(flag_gap_column, pd.Series(pd.NA, index=rows.index)), errors="coerce")
    return {
        "row_count": row_count,
        "predictive_error_mae": float(units_gap.mean()) if row_count else 0.0,
        "excess_units_mae": float(units_gap.mean()) if row_count else 0.0,
        "excess_units_error_total": float(units_gap.sum()) if row_count else 0.0,
        "excess_capital_mae": float(capital_gap.mean()) if row_count else 0.0,
        "excess_capital_error_total": float(capital_gap.sum()) if row_count else 0.0,
        "flag_disagreement_rate": float(flag_gap.mean()) if row_count else 0.0,
        "flag_disagreement_count": int(flag_gap.fillna(0.0).sum()) if row_count else 0,
    }


def _target_mode_zero_label_metric_block(rows: pd.DataFrame) -> dict[str, object]:
    row_count = int(len(rows.index))
    return {
        "row_count": row_count,
        "predictive_error_mae": 0.0,
        "excess_units_mae": 0.0,
        "excess_units_error_total": 0.0,
        "excess_capital_mae": 0.0,
        "excess_capital_error_total": 0.0,
        "flag_disagreement_rate": 0.0,
        "flag_disagreement_count": 0,
    }


def _target_mode_shadow_metric_block(
    rows: pd.DataFrame,
    *,
    prediction_units_column: str,
    prediction_capital_column: str,
    prediction_flag_column: str,
    target_units_column: str,
    target_capital_column: str,
    target_flag_column: str,
) -> dict[str, object]:
    prediction_units = pd.to_numeric(rows.get(prediction_units_column, pd.Series(pd.NA, index=rows.index)), errors="coerce")
    prediction_capital = pd.to_numeric(rows.get(prediction_capital_column, pd.Series(pd.NA, index=rows.index)), errors="coerce")
    prediction_flag = pd.to_numeric(rows.get(prediction_flag_column, pd.Series(pd.NA, index=rows.index)), errors="coerce")
    target_units = pd.to_numeric(rows.get(target_units_column, pd.Series(pd.NA, index=rows.index)), errors="coerce")
    target_capital = pd.to_numeric(rows.get(target_capital_column, pd.Series(pd.NA, index=rows.index)), errors="coerce")
    target_flag = pd.to_numeric(rows.get(target_flag_column, pd.Series(pd.NA, index=rows.index)), errors="coerce")
    valid_mask = prediction_units.notna() & prediction_capital.notna() & target_units.notna() & target_capital.notna()
    valid_rows = rows.loc[valid_mask]
    if valid_rows.empty:
        return {
            "row_count": 0,
            "predictive_error_mae": 0.0,
            "excess_units_mae": 0.0,
            "excess_units_error_total": 0.0,
            "excess_capital_mae": 0.0,
            "excess_capital_error_total": 0.0,
            "flag_precision": 0.0,
            "flag_recall": 0.0,
            "predicted_flag_rate": 0.0,
            "target_flag_rate": 0.0,
        }
    unit_error = (prediction_units.loc[valid_mask] - target_units.loc[valid_mask]).abs()
    capital_error = (prediction_capital.loc[valid_mask] - target_capital.loc[valid_mask]).abs()
    flag_valid_mask = valid_mask & prediction_flag.notna() & target_flag.notna()
    if flag_valid_mask.any():
        predicted_labels = prediction_flag.loc[flag_valid_mask].ge(0.5).astype(int)
        target_labels = target_flag.loc[flag_valid_mask].ge(0.5).astype(int)
        flag_precision = float(precision_score(target_labels, predicted_labels, zero_division=0))
        flag_recall = float(recall_score(target_labels, predicted_labels, zero_division=0))
        predicted_flag_rate = float(predicted_labels.mean())
        target_flag_rate = float(target_labels.mean())
    else:
        flag_precision = 0.0
        flag_recall = 0.0
        predicted_flag_rate = 0.0
        target_flag_rate = 0.0
    return {
        "row_count": int(len(valid_rows.index)),
        "predictive_error_mae": float(unit_error.mean()),
        "excess_units_mae": float(unit_error.mean()),
        "excess_units_error_total": float(unit_error.sum()),
        "excess_capital_mae": float(capital_error.mean()),
        "excess_capital_error_total": float(capital_error.sum()),
        "flag_precision": flag_precision,
        "flag_recall": flag_recall,
        "predicted_flag_rate": predicted_flag_rate,
        "target_flag_rate": target_flag_rate,
    }


def _target_mode_bucket_ranking_row(
    *,
    bucket_name: str,
    bucket_rows: pd.DataFrame,
    total_current_label_capital_gap: float,
) -> dict[str, object]:
    comparable_rows = bucket_rows.loc[
        pd.to_numeric(bucket_rows.get("both_contract_valid_flag", pd.Series(0.0, index=bucket_rows.index)), errors="coerce").fillna(0.0).ge(1.0)
    ].copy()
    current_label_capital_error = pd.to_numeric(
        comparable_rows.get("trainer_vs_historical_excess_capital_gap_abs", pd.Series(0.0, index=comparable_rows.index)),
        errors="coerce",
    ).fillna(0.0)
    current_shadow_capital_error = (
        pd.to_numeric(comparable_rows.get("current_contract_shadow_predicted_excess_capital_on_historical_cost", pd.Series(0.0, index=comparable_rows.index)), errors="coerce")
        - pd.to_numeric(comparable_rows.get("historical_allocation_excess_capital", pd.Series(0.0, index=comparable_rows.index)), errors="coerce")
    ).abs().fillna(0.0)
    candidate_shadow_capital_error = (
        pd.to_numeric(comparable_rows.get("historical_candidate_shadow_predicted_excess_capital", pd.Series(0.0, index=comparable_rows.index)), errors="coerce")
        - pd.to_numeric(comparable_rows.get("historical_allocation_excess_capital", pd.Series(0.0, index=comparable_rows.index)), errors="coerce")
    ).abs().fillna(0.0)
    flag_disagreement = pd.to_numeric(
        comparable_rows.get("overallocation_flag_disagreement_flag", pd.Series(0.0, index=comparable_rows.index)),
        errors="coerce",
    ).fillna(0.0)
    return {
        "bucket_name": bucket_name,
        "row_count": int(len(bucket_rows.index)),
        "comparable_row_count": int(len(comparable_rows.index)),
        "current_label_vs_historical_excess_capital_error_total": float(current_label_capital_error.sum()),
        "current_label_vs_historical_excess_capital_error_mean": float(current_label_capital_error.mean()) if not comparable_rows.empty else 0.0,
        "share_of_total_current_label_capital_error": (
            float(current_label_capital_error.sum()) / total_current_label_capital_gap
        ) if total_current_label_capital_gap > 0.0 else 0.0,
        "current_shadow_vs_historical_excess_capital_mae": float(current_shadow_capital_error.mean()) if not comparable_rows.empty else 0.0,
        "historical_candidate_shadow_vs_historical_excess_capital_mae": float(candidate_shadow_capital_error.mean()) if not comparable_rows.empty else 0.0,
        "candidate_shadow_capital_mae_improvement": (
            float(current_shadow_capital_error.mean() - candidate_shadow_capital_error.mean())
            if not comparable_rows.empty else 0.0
        ),
        "current_vs_historical_flag_disagreement_rate": float(flag_disagreement.mean()) if not comparable_rows.empty else 0.0,
    }


def _build_target_mode_residual_examples_frame(diagnostic_frame: pd.DataFrame) -> pd.DataFrame:
    working = diagnostic_frame.loc[
        pd.to_numeric(diagnostic_frame.get("both_contract_valid_flag", pd.Series(0.0, index=diagnostic_frame.index)), errors="coerce").fillna(0.0).ge(1.0)
    ].copy()
    columns = [
        "dominant_divergence_driver",
        "promotion_row_key",
        "store_number",
        "sku_number",
        "split_name",
        "current_trainer_target_value",
        "historical_allocation_target_value",
        "trainer_vs_historical_excess_units_gap_abs",
        "trainer_vs_historical_excess_capital_gap_abs",
        "current_contract_shadow_predicted_excess_units",
        "historical_candidate_shadow_predicted_excess_units",
        "current_contract_shadow_predicted_excess_capital_on_historical_cost",
        "historical_candidate_shadow_predicted_excess_capital",
        "historical_allocation_excess_capital",
        "overallocation_flag_disagreement_flag",
    ]
    if working.empty:
        return pd.DataFrame(columns=columns)
    working["current_shadow_historical_capital_error_abs"] = (
        pd.to_numeric(working["current_contract_shadow_predicted_excess_capital_on_historical_cost"], errors="coerce")
        - pd.to_numeric(working["historical_allocation_excess_capital"], errors="coerce")
    ).abs()
    working["historical_shadow_historical_capital_error_abs"] = (
        pd.to_numeric(working["historical_candidate_shadow_predicted_excess_capital"], errors="coerce")
        - pd.to_numeric(working["historical_allocation_excess_capital"], errors="coerce")
    ).abs()
    working["candidate_shadow_capital_error_improvement"] = (
        working["current_shadow_historical_capital_error_abs"]
        - working["historical_shadow_historical_capital_error_abs"]
    )
    columns.extend(
        [
            "current_shadow_historical_capital_error_abs",
            "historical_shadow_historical_capital_error_abs",
            "candidate_shadow_capital_error_improvement",
        ]
    )
    working = working.sort_values(
        ["trainer_vs_historical_excess_capital_gap_abs", "current_shadow_historical_capital_error_abs"],
        ascending=[False, False],
        kind="mergesort",
    ).head(_TARGET_MODE_RESIDUAL_ROW_LIMIT)
    return working.loc[:, columns].reset_index(drop=True)


def _build_target_contract_promotion_gate_payload(summary_payload: dict[str, object]) -> dict[str, object]:
    valid_row_counts = summary_payload.get("valid_row_counts", {})
    comparison_blocks = summary_payload.get("comparison_blocks", {})
    total_rows = int(summary_payload.get("evaluation_row_count", 0))
    valid_under_both = int(valid_row_counts.get("valid_under_both_contracts", 0)) if isinstance(valid_row_counts, dict) else 0
    historical_invalid_rows = 0
    if isinstance(valid_row_counts, dict):
        historical_invalid_rows = int(valid_row_counts.get("valid_only_under_current_contract", 0)) + int(
            valid_row_counts.get("excluded_from_both_contracts", 0)
        )
    coverage_rate = (valid_under_both / total_rows) if total_rows > 0 else 0.0
    historical_exclusion_rate = (historical_invalid_rows / total_rows) if total_rows > 0 else 1.0
    current_label_block = comparison_blocks.get(
        "current_trainer_contract_label_vs_historical_business_target",
        {},
    ) if isinstance(comparison_blocks, dict) else {}
    candidate_label_block = comparison_blocks.get(
        "historical_allocation_candidate_label_vs_historical_business_target",
        {},
    ) if isinstance(comparison_blocks, dict) else {}
    current_label_capital_mae = float(current_label_block.get("excess_capital_mae", 0.0)) if isinstance(current_label_block, dict) else 0.0
    candidate_label_capital_mae = float(candidate_label_block.get("excess_capital_mae", 0.0)) if isinstance(candidate_label_block, dict) else 0.0
    candidate_better = bool(candidate_label_capital_mae < current_label_capital_mae and current_label_capital_mae > 0.0)
    coverage_sufficient = bool(coverage_rate >= _TARGET_MODE_PROMOTION_GATE_MIN_COVERAGE_RATE)
    exclusions_acceptable = bool(historical_exclusion_rate <= _TARGET_MODE_PROMOTION_GATE_MAX_EXCLUSION_RATE)
    target_misalignment_dominant = bool(summary_payload.get("current_trainer_target_misaligned_with_business_mistake", False))
    should_promote_shadow = bool(candidate_better and coverage_sufficient and exclusions_acceptable and target_misalignment_dominant)
    should_promote_primary = False
    blockers: list[str] = []
    if not candidate_better:
        blockers.append("historical_candidate_not_better_than_current_on_comparable_rows")
    if not coverage_sufficient:
        blockers.append("insufficient_valid_comparable_coverage")
    if not exclusions_acceptable:
        blockers.append("historical_target_exclusions_not_acceptable")
    if not target_misalignment_dominant:
        blockers.append("target_contract_misalignment_not_dominant")
    primary_blockers = ["requires_repeated_stable_shadow_training_evidence"]
    decision = "candidate_for_shadow_training" if should_promote_shadow else "diagnostics_only"
    return {
        "row_scope": "out_of_sample_validation_and_test",
        "target_mode": summary_payload.get("target_mode"),
        "historical_allocation_candidate_better_than_current_on_comparable_rows": candidate_better,
        "coverage_sufficient": coverage_sufficient,
        "coverage_rate": coverage_rate,
        "minimum_coverage_rate": _TARGET_MODE_PROMOTION_GATE_MIN_COVERAGE_RATE,
        "historical_target_exclusions_acceptable": exclusions_acceptable,
        "historical_exclusion_rate": historical_exclusion_rate,
        "maximum_historical_exclusion_rate": _TARGET_MODE_PROMOTION_GATE_MAX_EXCLUSION_RATE,
        "should_remain_diagnostics_only": not should_promote_shadow,
        "should_promote_to_candidate_for_shadow_training": should_promote_shadow,
        "should_promote_to_candidate_for_primary_training": should_promote_primary,
        "should_current_trainer_contract_remain_primary": True,
        "current_trainer_contract_remains_live_default": True,
        "policy_remains_paused": True,
        "policy_is_dominant_bottleneck": False,
        "target_contract_misalignment_is_dominant_bottleneck": target_misalignment_dominant,
        "decision": decision,
        "shadow_promotion_blockers": blockers,
        "primary_promotion_blockers": primary_blockers,
        "explanation": (
            "Historical allocation is eligible for shadow training, but current remains primary until repeated stable shadow evidence exists."
            if should_promote_shadow else
            "Historical allocation remains diagnostics-only because one or more governed promotion gates failed."
        ),
    }


def _flatten_target_mode_summary_payload(summary_payload: dict[str, object]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    nested_keys = {
        "valid_row_counts",
        "excluded_historical_contract_reason_counts",
        "shadow_training_row_counts",
        "comparison_blocks",
        "shadow_model_candidate_vs_current_on_historical_business_target",
        "policy_pause_conclusion",
        "target_contract_promotion_gate",
        "target_modes_compared",
        "candidate_target_family",
    }
    for key, value in summary_payload.items():
        if key not in nested_keys:
            rows.append({"section": "headline", "block_name": "summary", "metric_name": key, "metric_value": value})
    for section_name in ("valid_row_counts", "excluded_historical_contract_reason_counts", "shadow_training_row_counts"):
        block = summary_payload.get(section_name, {})
        if isinstance(block, dict):
            rows.extend(
                {"section": section_name, "block_name": section_name, "metric_name": key, "metric_value": value}
                for key, value in block.items()
            )
    comparison_blocks = summary_payload.get("comparison_blocks", {})
    if isinstance(comparison_blocks, dict):
        rows.extend(
            {
                "section": "comparison_block",
                "block_name": block_name,
                "metric_name": metric_name,
                "metric_value": metric_value,
            }
            for block_name, block in comparison_blocks.items()
            if isinstance(block, dict)
            for metric_name, metric_value in block.items()
        )
    for section_name in (
        "shadow_model_candidate_vs_current_on_historical_business_target",
        "policy_pause_conclusion",
        "target_contract_promotion_gate",
    ):
        block = summary_payload.get(section_name, {})
        if isinstance(block, dict):
            rows.extend(
                {"section": section_name, "block_name": section_name, "metric_name": key, "metric_value": value}
                for key, value in block.items()
            )
    return pd.DataFrame(rows)


def _json_ready_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")


_TARGET_MODE_SHADOW_EVALUATOR_MODE_MULTI_SLICE_MANIFEST = "multi_slice_manifest_path"
_TARGET_MODE_SHADOW_EVALUATOR_MODE_EXPLICIT_SLICE_INPUTS = "explicit_slice_inputs"


def _resolve_target_mode_shadow_evaluator_inputs(
    *,
    multi_slice_manifest_path: str | Path | None,
    slice_inputs: Sequence[str | Path],
) -> dict[str, object]:
    has_multi_slice_manifest = multi_slice_manifest_path is not None
    has_slice_inputs = bool(slice_inputs)
    if has_multi_slice_manifest == has_slice_inputs:
        raise ValueError(
            "target-mode multi-slice runtime requires exactly one of multi_slice_manifest_path or slice_inputs"
        )

    if has_multi_slice_manifest:
        source_manifest_path = Path(str(multi_slice_manifest_path)).expanduser()
        if not source_manifest_path.exists():
            raise FileNotFoundError(
                f"target-mode multi-slice source manifest not found: {source_manifest_path}"
            )
        source_slice_inputs = _expand_target_mode_shadow_slice_inputs_from_multi_slice_manifest(
            source_manifest_path
        )
        resolved_slice_inputs = _resolve_target_mode_shadow_slice_inputs(source_slice_inputs)
        return {
            "requested_evaluator_mode": _TARGET_MODE_SHADOW_EVALUATOR_MODE_MULTI_SLICE_MANIFEST,
            "resolved_evaluator_mode": _TARGET_MODE_SHADOW_EVALUATOR_MODE_MULTI_SLICE_MANIFEST,
            "source_multi_slice_manifest_path": str(source_manifest_path.resolve()),
            "source_slice_inputs": source_slice_inputs,
            "resolved_slice_inputs": resolved_slice_inputs,
        }

    resolved_slice_inputs = _resolve_target_mode_shadow_slice_inputs(slice_inputs)
    return {
        "requested_evaluator_mode": _TARGET_MODE_SHADOW_EVALUATOR_MODE_EXPLICIT_SLICE_INPUTS,
        "resolved_evaluator_mode": _TARGET_MODE_SHADOW_EVALUATOR_MODE_EXPLICIT_SLICE_INPUTS,
        "source_multi_slice_manifest_path": None,
        "source_slice_inputs": [str(slice_spec["source_path"]) for slice_spec in resolved_slice_inputs],
        "resolved_slice_inputs": resolved_slice_inputs,
    }


def _expand_target_mode_shadow_slice_inputs_from_multi_slice_manifest(
    source_manifest_path: Path,
) -> list[str]:
    manifest_payload = read_json(source_manifest_path)
    slice_runs = manifest_payload.get("slice_runs")
    if not isinstance(slice_runs, list) or not slice_runs:
        raise ValueError(
            "target-mode multi-slice source manifest must contain at least one governed slice run: "
            f"{source_manifest_path}"
        )

    source_slice_inputs: list[str] = []
    for slice_index, raw_slice_run in enumerate(slice_runs, start=1):
        if not isinstance(raw_slice_run, dict):
            raise ValueError(
                "target-mode multi-slice source manifest contains an invalid slice run record at index "
                f"{slice_index}: {source_manifest_path}"
            )
        child_manifest_raw = raw_slice_run.get("manifest_path")
        if not isinstance(child_manifest_raw, str) or not child_manifest_raw.strip():
            raise ValueError(
                "target-mode multi-slice source manifest is missing slice run manifest_path at index "
                f"{slice_index}: {source_manifest_path}"
            )
        child_manifest_path = _resolve_target_mode_shadow_source_artifact_path(
            child_manifest_raw,
            source_manifest_path=source_manifest_path,
            artifact_name=f"slice_runs[{slice_index}].manifest_path",
        )

        for artifact_key in ("target_mode_summary_json_path", "target_contract_promotion_gate_json_path"):
            artifact_raw = raw_slice_run.get(artifact_key)
            if not isinstance(artifact_raw, str) or not artifact_raw.strip():
                raise ValueError(
                    "target-mode multi-slice source manifest is missing governed slice artifact "
                    f"{artifact_key!r} at index {slice_index}: {source_manifest_path}"
                )
            _resolve_target_mode_shadow_source_artifact_path(
                artifact_raw,
                source_manifest_path=source_manifest_path,
                artifact_name=f"slice_runs[{slice_index}].{artifact_key}",
            )

        child_manifest_payload = read_json(child_manifest_path)
        _extract_training_ready_dataset_path_from_manifest(
            child_manifest_payload,
            manifest_path=child_manifest_path,
        )
        artifact_files = child_manifest_payload.get("artifact_files")
        if not isinstance(artifact_files, dict):
            raise ValueError(
                "target-mode multi-slice child run manifest is missing artifact_files: "
                f"{child_manifest_path}"
            )
        for artifact_key in (
            "target_mode_bucket_ranking_json",
            "target_mode_residual_examples_json",
            "target_contract_row_diagnostics_parquet",
        ):
            artifact_raw = artifact_files.get(artifact_key)
            if not isinstance(artifact_raw, str) or not artifact_raw.strip():
                raise ValueError(
                    "target-mode multi-slice child run manifest is missing required governed artifact "
                    f"{artifact_key!r}: {child_manifest_path}"
                )
            _resolve_target_mode_shadow_source_artifact_path(
                artifact_raw,
                source_manifest_path=child_manifest_path,
                artifact_name=f"artifact_files.{artifact_key}",
            )
        source_slice_inputs.append(str(child_manifest_path))
    return source_slice_inputs


def _resolve_target_mode_shadow_source_artifact_path(
    raw_path: str | Path,
    *,
    source_manifest_path: Path,
    artifact_name: str,
) -> Path:
    candidate_path = Path(raw_path).expanduser()
    search_paths = [candidate_path]
    if not candidate_path.is_absolute():
        search_paths.extend((source_manifest_path.parent / candidate_path, Path.cwd() / candidate_path))
    for search_path in search_paths:
        if search_path.exists():
            return search_path.resolve()
    raise FileNotFoundError(
        "target-mode multi-slice source artifact not found "
        f"for {artifact_name}: {raw_path}"
    )


def _resolve_target_mode_shadow_slice_inputs(slice_inputs: Sequence[str | Path]) -> list[dict[str, object]]:
    if not slice_inputs:
        raise ValueError("multi-slice shadow evaluation requires at least one slice input")
    resolved: list[dict[str, object]] = []
    for slice_index, raw_input in enumerate(slice_inputs, start=1):
        source_path = Path(raw_input).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f"multi-slice shadow evaluation slice input not found: {source_path}")
        if source_path.suffix.lower() == ".parquet":
            dataset_path = source_path.resolve()
            slice_identifier = _target_mode_slice_identifier_from_parquet(source_path)
            source_type = "training_ready_parquet"
            source_manifest_path: str | None = None
        elif source_path.suffix.lower() == ".json":
            manifest_payload = read_json(source_path)
            dataset_path = _extract_training_ready_dataset_path_from_manifest(
                manifest_payload,
                manifest_path=source_path,
            )
            slice_identifier = str(
                manifest_payload.get("slice_identifier")
                or manifest_payload.get("run_id")
                or manifest_payload.get("dataset_run_id")
                or source_path.stem
            )
            source_type = "governed_slice_manifest"
            source_manifest_path = str(source_path.resolve())
        else:
            raise ValueError(
                "multi-slice shadow evaluation inputs must be training-ready parquet files or governed JSON manifests: "
                f"{source_path}"
            )
        if not dataset_path.exists():
            raise FileNotFoundError(f"multi-slice shadow evaluation training-ready dataset not found: {dataset_path}")
        resolved.append(
            {
                "slice_index": slice_index,
                "slice_identifier": slice_identifier,
                "source_type": source_type,
                "source_path": str(source_path.resolve()),
                "source_manifest_path": source_manifest_path,
                "dataset_path": str(dataset_path.resolve()),
            }
        )
    return resolved


def _target_mode_slice_identifier_from_parquet(source_path: Path) -> str:
    if source_path.name == "training_ready.parquet" and source_path.parent.name:
        return source_path.parent.name
    return source_path.stem


def _extract_training_ready_dataset_path_from_manifest(
    manifest_payload: dict[str, object],
    *,
    manifest_path: Path,
) -> Path:
    candidate_keys = {
        "training_ready_dataset_path",
        "training_ready_parquet_path",
        "training_ready_path",
        "dataset_path",
    }
    candidates: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if key in candidate_keys and isinstance(nested_value, str):
                    candidates.append(nested_value)
                collect(nested_value)
        elif isinstance(value, list):
            for nested_value in value:
                collect(nested_value)

    collect(manifest_payload)
    for candidate in candidates:
        candidate_path = Path(candidate).expanduser()
        search_paths = [candidate_path]
        if not candidate_path.is_absolute():
            search_paths = [manifest_path.parent / candidate_path, Path.cwd() / candidate_path]
        for search_path in search_paths:
            if search_path.suffix.lower() == ".parquet" and search_path.exists():
                return search_path.resolve()
    raise ValueError(
        "governed slice manifest does not reference an existing training-ready parquet dataset: "
        f"{manifest_path}"
    )


def _target_mode_slug(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in normalized.split("-") if part)[:80] or "slice"


def _require_target_mode_slice_artifact_paths(
    target_mode_paths: dict[str, str],
    target_contract_paths: dict[str, str],
) -> None:
    missing_target_mode = [
        key
        for key in (
            "summary_json_path",
            "bucket_ranking_json_path",
            "residual_examples_json_path",
            "promotion_gate_json_path",
        )
        if key not in target_mode_paths or not Path(target_mode_paths[key]).exists()
    ]
    missing_target_contract = [
        key
        for key in ("summary_json_path", "divergence_summary_json_path")
        if key not in target_contract_paths or not Path(target_contract_paths[key]).exists()
    ]
    if missing_target_mode or missing_target_contract:
        raise ValueError(
            "multi-slice shadow evaluation missing per-slice trainer-owned evidence artifacts; "
            f"target_mode_missing={missing_target_mode}, target_contract_missing={missing_target_contract}"
        )


def _target_mode_multi_slice_summary_row(
    *,
    slice_index: int,
    slice_spec: dict[str, object],
    child_run_id: str,
    training_manifest_payload: dict[str, object],
    target_mode_summary_payload: dict[str, object],
    slice_gate_payload: dict[str, object],
    target_mode_paths: dict[str, str],
    target_contract_paths: dict[str, str],
) -> dict[str, object]:
    comparison_blocks = target_mode_summary_payload.get("comparison_blocks", {})
    if not isinstance(comparison_blocks, dict):
        raise ValueError("target mode slice summary is missing comparison_blocks")
    current_label_block = comparison_blocks.get("current_trainer_contract_label_vs_historical_business_target", {})
    current_shadow_block = comparison_blocks.get("current_trainer_contract_shadow_model_vs_historical_business_target", {})
    historical_shadow_block = comparison_blocks.get(
        "historical_allocation_candidate_shadow_model_vs_historical_business_target",
        {},
    )
    shadow_comparison = target_mode_summary_payload.get(
        "shadow_model_candidate_vs_current_on_historical_business_target",
        {},
    )
    valid_row_counts = target_mode_summary_payload.get("valid_row_counts", {})
    for block_name, block in (
        ("current_label_block", current_label_block),
        ("current_shadow_block", current_shadow_block),
        ("historical_shadow_block", historical_shadow_block),
        ("shadow_comparison", shadow_comparison),
        ("valid_row_counts", valid_row_counts),
    ):
        if not isinstance(block, dict):
            raise ValueError(f"target mode slice summary has invalid {block_name}")
    comparable_rows = int(valid_row_counts.get("valid_under_both_contracts", 0))
    evidence_outcome = _target_mode_evidence_outcome(slice_gate_payload)
    return {
        "slice_index": int(slice_index),
        "slice_identifier": str(slice_spec["slice_identifier"]),
        "source_type": str(slice_spec["source_type"]),
        "source_path": str(slice_spec["source_path"]),
        "source_manifest_path": slice_spec.get("source_manifest_path"),
        "dataset_path": str(slice_spec["dataset_path"]),
        "child_run_id": child_run_id,
        "target_mode": target_mode_summary_payload.get("target_mode"),
        "training_manifest_target_mode": training_manifest_payload.get("target_mode"),
        "comparison_cohort_size": comparable_rows,
        "comparable_rows": comparable_rows,
        "evaluation_row_count": int(target_mode_summary_payload.get("evaluation_row_count", 0)),
        "coverage_rate": slice_gate_payload.get("coverage_rate"),
        "historical_exclusion_rate": slice_gate_payload.get("historical_exclusion_rate"),
        "current_vs_historical_disagreement_rate": current_label_block.get("flag_disagreement_rate"),
        "current_vs_historical_capital_gap_total": current_label_block.get("excess_capital_error_total"),
        "current_shadow_excess_capital_mae_on_historical_target": current_shadow_block.get("excess_capital_mae"),
        "historical_shadow_excess_capital_mae_on_historical_target": historical_shadow_block.get("excess_capital_mae"),
        "candidate_capital_mae_improvement": shadow_comparison.get("candidate_capital_mae_improvement"),
        "candidate_capital_mae_improvement_rate": shadow_comparison.get("candidate_capital_mae_improvement_rate"),
        "candidate_shadow_model_outperformed_current_shadow_model": shadow_comparison.get(
            "candidate_shadow_model_outperformed_current_shadow_model"
        ),
        "current_shadow_flag_precision_on_historical_target": current_shadow_block.get("flag_precision"),
        "current_shadow_flag_recall_on_historical_target": current_shadow_block.get("flag_recall"),
        "historical_shadow_flag_precision_on_historical_target": historical_shadow_block.get("flag_precision"),
        "historical_shadow_flag_recall_on_historical_target": historical_shadow_block.get("flag_recall"),
        "dominant_divergence_driver": target_mode_summary_payload.get("top_divergence_driver"),
        "slice_gate_decision": slice_gate_payload.get("decision"),
        "slice_should_promote_to_shadow": slice_gate_payload.get("should_promote_to_candidate_for_shadow_training"),
        "slice_should_promote_to_primary": slice_gate_payload.get("should_promote_to_candidate_for_primary_training"),
        "slice_should_remain_diagnostics_only": slice_gate_payload.get("should_remain_diagnostics_only"),
        "current_trainer_contract_remains_live_default": slice_gate_payload.get("current_trainer_contract_remains_live_default"),
        "policy_remains_paused": slice_gate_payload.get("policy_remains_paused"),
        "policy_is_dominant_bottleneck": slice_gate_payload.get("policy_is_dominant_bottleneck"),
        "target_contract_misalignment_is_dominant_bottleneck": slice_gate_payload.get(
            "target_contract_misalignment_is_dominant_bottleneck"
        ),
        "evidence_outcome": evidence_outcome,
        "target_mode_summary_json_path": target_mode_paths["summary_json_path"],
        "target_contract_summary_json_path": target_contract_paths["summary_json_path"],
        "target_contract_promotion_gate_json_path": target_mode_paths["promotion_gate_json_path"],
    }


def _target_mode_evidence_outcome(slice_gate_payload: dict[str, object]) -> str:
    if bool(slice_gate_payload.get("should_promote_to_candidate_for_primary_training", False)):
        return "primary-candidate"
    if bool(slice_gate_payload.get("should_promote_to_candidate_for_shadow_training", False)):
        return "shadow-only"
    return "evidence-only"


def _build_target_mode_multi_slice_artifacts(
    *,
    run_id: str,
    target_mode: PromotionTrainerTargetMode,
    slice_rows: list[dict[str, object]],
    bucket_records: list[dict[str, object]],
    residual_records: list[dict[str, object]],
    slice_run_artifact_paths: list[dict[str, str]],
) -> dict[str, object]:
    summary_frame = pd.DataFrame(slice_rows)
    if summary_frame.empty:
        raise ValueError("multi-slice stability gate requires at least one slice row")
    stability_gate_payload = _build_target_mode_shadow_stability_gate_payload(summary_frame)
    bucket_ranking_frame = _aggregate_target_mode_multi_slice_buckets(bucket_records)
    residual_examples_frame = _build_target_mode_multi_slice_residual_frame(residual_records)
    summary_payload = {
        "run_id": run_id,
        "target_mode": target_mode,
        "row_scope": "out_of_sample_validation_and_test_by_slice",
        "slice_count": int(len(summary_frame.index)),
        "production_training_target_contract": DEFAULT_PROMOTION_TRAINER_TARGET_MODE,
        "production_training_target_was_replaced": False,
        "slice_rows": _json_ready_records(summary_frame),
        "slice_run_artifact_paths": slice_run_artifact_paths,
        "aggregate_metrics": {
            "total_comparable_rows": int(pd.to_numeric(summary_frame["comparable_rows"], errors="coerce").sum()),
            "mean_candidate_capital_mae_improvement": float(
                pd.to_numeric(summary_frame["candidate_capital_mae_improvement"], errors="coerce").mean()
            ),
            "median_candidate_capital_mae_improvement_rate": float(
                pd.to_numeric(summary_frame["candidate_capital_mae_improvement_rate"], errors="coerce").median()
            ),
            "dominant_divergence_driver_counts": {
                str(key): int(value)
                for key, value in summary_frame["dominant_divergence_driver"].astype(str).value_counts(dropna=False).to_dict().items()
            },
        },
        "stability_gate": stability_gate_payload,
    }
    return {
        "summary_payload": summary_payload,
        "summary_frame": summary_frame,
        "bucket_ranking_payload": {
            "run_id": run_id,
            "target_mode": target_mode,
            "row_scope": "out_of_sample_validation_and_test_by_slice",
            "ranking_rows": _json_ready_records(bucket_ranking_frame),
            "top_persistent_divergence_driver": stability_gate_payload["gate_inputs"]["top_persistent_divergence_driver"],
        },
        "bucket_ranking_frame": bucket_ranking_frame,
        "residual_examples_payload": {
            "run_id": run_id,
            "target_mode": target_mode,
            "row_scope": "out_of_sample_validation_and_test_by_slice",
            "top_row_limit": _TARGET_MODE_MULTI_SLICE_RESIDUAL_ROW_LIMIT,
            "row_count": int(len(residual_examples_frame.index)),
            "rows": _json_ready_records(residual_examples_frame),
        },
        "residual_examples_frame": residual_examples_frame,
        "stability_gate_payload": stability_gate_payload,
    }


def _build_target_mode_shadow_stability_gate_payload(summary_frame: pd.DataFrame) -> dict[str, object]:
    required_columns = (
        "slice_identifier",
        "comparable_rows",
        "coverage_rate",
        "historical_exclusion_rate",
        "candidate_capital_mae_improvement",
        "candidate_capital_mae_improvement_rate",
        "candidate_shadow_model_outperformed_current_shadow_model",
        "dominant_divergence_driver",
        "slice_gate_decision",
        "slice_should_promote_to_shadow",
    )
    _require_columns(summary_frame, required_columns, context="target mode multi-slice stability gate")
    numeric_columns = (
        "comparable_rows",
        "coverage_rate",
        "historical_exclusion_rate",
        "candidate_capital_mae_improvement",
        "candidate_capital_mae_improvement_rate",
    )
    numeric_values: dict[str, pd.Series] = {}
    missing_numeric_columns: list[str] = []
    for column_name in numeric_columns:
        series = pd.to_numeric(summary_frame[column_name], errors="coerce")
        if series.isna().any():
            missing_numeric_columns.append(column_name)
        numeric_values[column_name] = series
    if missing_numeric_columns:
        raise ValueError(
            "target mode multi-slice stability gate missing required numeric slice evidence: "
            + ", ".join(sorted(missing_numeric_columns))
        )
    if summary_frame["dominant_divergence_driver"].isna().any() or summary_frame["slice_gate_decision"].isna().any():
        raise ValueError("target mode multi-slice stability gate missing required categorical slice evidence")

    slice_count = int(len(summary_frame.index))
    comparable_rows = numeric_values["comparable_rows"]
    exclusion_rate = numeric_values["historical_exclusion_rate"]
    improvement = numeric_values["candidate_capital_mae_improvement"]
    relative_improvement = numeric_values["candidate_capital_mae_improvement_rate"]
    positive_improvement = improvement.gt(0.0) & summary_frame["candidate_shadow_model_outperformed_current_shadow_model"].astype(bool)
    positive_slice_count = int(positive_improvement.sum())
    positive_slice_share = float(positive_improvement.mean()) if slice_count else 0.0
    shadow_slice_share = float(summary_frame["slice_should_promote_to_shadow"].astype(bool).mean()) if slice_count else 0.0
    stock_basis_mask = summary_frame["dominant_divergence_driver"].astype(str).eq(_TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS)
    stock_basis_dominance_share = float(stock_basis_mask.mean()) if slice_count else 0.0
    top_driver_counts = summary_frame["dominant_divergence_driver"].astype(str).value_counts(dropna=False).to_dict()
    top_persistent_driver = str(max(top_driver_counts, key=top_driver_counts.get)) if top_driver_counts else None
    positive_relative_improvement = relative_improvement.loc[positive_improvement]
    median_relative_improvement = float(positive_relative_improvement.median()) if not positive_relative_improvement.empty else 0.0
    mean_relative_improvement = float(positive_relative_improvement.mean()) if not positive_relative_improvement.empty else 0.0
    relative_improvement_cv = (
        float(positive_relative_improvement.std(ddof=0) / mean_relative_improvement)
        if len(positive_relative_improvement.index) > 1 and mean_relative_improvement > 0.0 else 0.0
    )
    criteria = {
        "minimum_slice_count": _TARGET_MODE_STABILITY_MIN_SLICE_COUNT,
        "minimum_comparable_rows_per_slice": _TARGET_MODE_STABILITY_MIN_COMPARABLE_ROWS_PER_SLICE,
        "minimum_positive_improvement_slice_share": _TARGET_MODE_STABILITY_MIN_POSITIVE_IMPROVEMENT_SHARE,
        "maximum_historical_exclusion_rate": _TARGET_MODE_STABILITY_MAX_EXCLUSION_RATE,
        "minimum_stock_basis_dominance_share": _TARGET_MODE_STABILITY_MIN_STOCK_BASIS_DOMINANCE_SHARE,
        "maximum_relative_improvement_coefficient_of_variation": _TARGET_MODE_STABILITY_MAX_RELATIVE_IMPROVEMENT_CV,
        "minimum_median_relative_improvement": _TARGET_MODE_STABILITY_MIN_MEDIAN_RELATIVE_IMPROVEMENT,
    }
    slice_count_sufficient = slice_count >= _TARGET_MODE_STABILITY_MIN_SLICE_COUNT
    comparable_rows_large_enough = bool(comparable_rows.ge(_TARGET_MODE_STABILITY_MIN_COMPARABLE_ROWS_PER_SLICE).all())
    exclusions_acceptable = bool(exclusion_rate.le(_TARGET_MODE_STABILITY_MAX_EXCLUSION_RATE).all())
    outperformed_enough_slices = bool(positive_slice_share >= _TARGET_MODE_STABILITY_MIN_POSITIVE_IMPROVEMENT_SHARE)
    stock_basis_persistent = bool(stock_basis_dominance_share >= _TARGET_MODE_STABILITY_MIN_STOCK_BASIS_DOMINANCE_SHARE)
    improvement_stable = bool(
        outperformed_enough_slices
        and positive_slice_count > 1
        and median_relative_improvement >= _TARGET_MODE_STABILITY_MIN_MEDIAN_RELATIVE_IMPROVEMENT
        and relative_improvement_cv <= _TARGET_MODE_STABILITY_MAX_RELATIVE_IMPROVEMENT_CV
    )
    should_promote_primary = bool(
        slice_count_sufficient
        and comparable_rows_large_enough
        and exclusions_acceptable
        and stock_basis_persistent
        and improvement_stable
        and shadow_slice_share >= _TARGET_MODE_STABILITY_MIN_POSITIVE_IMPROVEMENT_SHARE
    )
    should_remain_shadow_only = bool(
        not should_promote_primary
        and positive_slice_count > 0
        and shadow_slice_share > 0.0
        and exclusions_acceptable
    )
    should_remain_diagnostics_only = not should_promote_primary and not should_remain_shadow_only
    decision = "candidate_for_primary_training" if should_promote_primary else (
        "candidate_for_shadow_training" if should_remain_shadow_only else "diagnostics_only"
    )
    primary_blockers: list[str] = []
    if not slice_count_sufficient:
        primary_blockers.append("insufficient_slice_count")
    if not comparable_rows_large_enough:
        primary_blockers.append("insufficient_comparable_rows_per_slice")
    if not exclusions_acceptable:
        primary_blockers.append("historical_target_exclusions_not_acceptable")
    if not outperformed_enough_slices:
        primary_blockers.append("candidate_did_not_outperform_on_enough_slices")
    if not improvement_stable:
        primary_blockers.append("candidate_improvement_not_stable")
    if not stock_basis_persistent:
        primary_blockers.append("dominant_divergence_driver_not_persistent")
    gate_inputs = {
        "slice_count": slice_count,
        "positive_improvement_slice_count": positive_slice_count,
        "positive_improvement_slice_share": positive_slice_share,
        "shadow_ready_slice_share": shadow_slice_share,
        "minimum_comparable_rows_observed": int(comparable_rows.min()) if slice_count else 0,
        "maximum_historical_exclusion_rate_observed": float(exclusion_rate.max()) if slice_count else 0.0,
        "median_relative_improvement": median_relative_improvement,
        "mean_relative_improvement": mean_relative_improvement,
        "relative_improvement_coefficient_of_variation": relative_improvement_cv,
        "stock_basis_proxy_mismatch_slice_share": stock_basis_dominance_share,
        "top_persistent_divergence_driver": top_persistent_driver,
        "dominant_divergence_driver_counts": {str(key): int(value) for key, value in top_driver_counts.items()},
        "per_slice_gate_inputs": _json_ready_records(
            summary_frame.loc[
                :,
                [
                    "slice_identifier",
                    "comparable_rows",
                    "coverage_rate",
                    "historical_exclusion_rate",
                    "candidate_capital_mae_improvement",
                    "candidate_capital_mae_improvement_rate",
                    "dominant_divergence_driver",
                    "slice_gate_decision",
                    "evidence_outcome",
                ],
            ]
        ),
    }
    return {
        "row_scope": "out_of_sample_validation_and_test_by_slice",
        "promotion_criteria": criteria,
        "gate_inputs": gate_inputs,
        "historical_allocation_candidate_outperformed_current_on_enough_slices": outperformed_enough_slices,
        "candidate_improvement_stable_not_single_lucky_slice": improvement_stable,
        "comparable_row_counts_large_enough": comparable_rows_large_enough,
        "historical_target_exclusions_acceptable": exclusions_acceptable,
        "stock_basis_proxy_mismatch_persistent": stock_basis_persistent,
        "should_candidate_remain_diagnostics_only": should_remain_diagnostics_only,
        "should_candidate_remain_shadow_only": should_remain_shadow_only,
        "should_promote_to_candidate_for_primary_training": should_promote_primary,
        "should_current_trainer_contract_remain_default_primary": True,
        "current_trainer_contract_remains_live_default": True,
        "policy_remains_paused": True,
        "policy_is_dominant_bottleneck": False,
        "target_contract_misalignment_is_dominant_bottleneck": bool(stock_basis_persistent),
        "decision": decision,
        "primary_promotion_blockers": primary_blockers,
        "explanation": (
            "Historical allocation has stable multi-slice shadow superiority and may advance to candidate_for_primary_training; current remains the default until an explicit later primary switch."
            if should_promote_primary else
            "Historical allocation remains shadow-only until multi-slice superiority is stronger and more stable."
            if should_remain_shadow_only else
            "Historical allocation remains diagnostics-only because the multi-slice shadow evidence is insufficient."
        ),
    }


_TARGET_CONTRACT_DESIGN_EVALUATOR_MODE_MULTI_SLICE_MANIFEST = "multi_slice_manifest_path"
_TARGET_CONTRACT_DESIGN_EVALUATOR_MODE_EXPLICIT_SLICE_INPUTS = "explicit_slice_inputs"
_TARGET_CONTRACT_DESIGN_EXPLICIT_SOURCE_MANIFEST_PATH = "<explicit_slice_inputs>"


def _resolve_target_contract_design_evaluator_inputs(
    *,
    multi_slice_manifest_path: str | Path | None,
    slice_inputs: Sequence[str | Path],
) -> dict[str, object]:
    has_multi_slice_manifest = multi_slice_manifest_path is not None
    has_slice_inputs = bool(slice_inputs)
    if has_multi_slice_manifest == has_slice_inputs:
        raise ValueError(
            "target contract design runtime requires exactly one of multi_slice_manifest_path or slice_inputs"
        )

    if has_multi_slice_manifest:
        source_manifest_path = Path(str(multi_slice_manifest_path)).expanduser()
        if not source_manifest_path.exists():
            raise FileNotFoundError(
                f"target contract design source manifest not found: {source_manifest_path}"
            )
        source_manifest_path = source_manifest_path.resolve()
        source_manifest_payload = read_json(source_manifest_path)
        source_rows = _load_target_contract_design_source_rows(
            source_manifest_payload,
            source_manifest_path=source_manifest_path,
        )
        source_slice_inputs = _expand_target_contract_design_slice_inputs_from_multi_slice_manifest(
            source_manifest_path
        )
        resolved_slice_data = _resolve_target_contract_design_slice_inputs(source_slice_inputs)
        resolved_slice_inputs = resolved_slice_data["resolved_slice_inputs"]
        if not isinstance(resolved_slice_inputs, list):
            raise ValueError("target contract design resolved slice inputs must be a list")
        source_target_mode = _resolve_target_contract_design_source_target_mode(
            manifest_target_mode=source_manifest_payload.get("target_mode"),
            resolved_slice_inputs=resolved_slice_inputs,
        )
        return {
            "requested_evaluator_mode": _TARGET_CONTRACT_DESIGN_EVALUATOR_MODE_MULTI_SLICE_MANIFEST,
            "resolved_evaluator_mode": _TARGET_CONTRACT_DESIGN_EVALUATOR_MODE_MULTI_SLICE_MANIFEST,
            "source_manifest_path": str(source_manifest_path),
            "source_manifest_payload": source_manifest_payload,
            "source_rows": source_rows,
            "source_multi_slice_manifest_path": str(source_manifest_path),
            "source_slice_inputs": source_slice_inputs,
            "resolved_slice_inputs": resolved_slice_inputs,
            "source_target_mode": source_target_mode,
        }

    resolved_slice_data = _resolve_target_contract_design_slice_inputs(slice_inputs)
    resolved_slice_inputs = resolved_slice_data["resolved_slice_inputs"]
    if not isinstance(resolved_slice_inputs, list):
        raise ValueError("target contract design resolved slice inputs must be a list")
    slice_rows = resolved_slice_data["slice_rows"]
    if not isinstance(slice_rows, list):
        raise ValueError("target contract design resolved slice rows must be a list")
    source_manifest_payload = _build_target_contract_design_explicit_source_manifest_payload(
        resolved_slice_inputs=resolved_slice_inputs,
        slice_rows=slice_rows,
    )
    source_rows = _load_target_contract_design_source_rows_from_explicit_slice_inputs(resolved_slice_inputs)
    source_target_mode = _resolve_target_contract_design_source_target_mode(
        manifest_target_mode=source_manifest_payload.get("target_mode"),
        resolved_slice_inputs=resolved_slice_inputs,
    )
    return {
        "requested_evaluator_mode": _TARGET_CONTRACT_DESIGN_EVALUATOR_MODE_EXPLICIT_SLICE_INPUTS,
        "resolved_evaluator_mode": _TARGET_CONTRACT_DESIGN_EVALUATOR_MODE_EXPLICIT_SLICE_INPUTS,
        "source_manifest_path": _TARGET_CONTRACT_DESIGN_EXPLICIT_SOURCE_MANIFEST_PATH,
        "source_manifest_payload": source_manifest_payload,
        "source_rows": source_rows,
        "source_multi_slice_manifest_path": None,
        "source_slice_inputs": [str(slice_spec["source_path"]) for slice_spec in resolved_slice_inputs],
        "resolved_slice_inputs": resolved_slice_inputs,
        "source_target_mode": source_target_mode,
    }


def _expand_target_contract_design_slice_inputs_from_multi_slice_manifest(
    source_manifest_path: Path,
) -> list[str]:
    manifest_payload = read_json(source_manifest_path)
    slice_runs = manifest_payload.get("slice_runs")
    if not isinstance(slice_runs, list) or not slice_runs:
        raise ValueError(
            "target contract design source manifest must contain at least one governed slice run: "
            f"{source_manifest_path}"
        )

    source_slice_inputs: list[str] = []
    for slice_index, raw_slice_run in enumerate(slice_runs, start=1):
        if not isinstance(raw_slice_run, dict):
            raise ValueError(
                "target contract design source manifest contains an invalid slice run record at index "
                f"{slice_index}: {source_manifest_path}"
            )
        child_manifest_raw = raw_slice_run.get("manifest_path")
        if not isinstance(child_manifest_raw, str) or not child_manifest_raw.strip():
            raise ValueError(
                "target contract design source manifest is missing slice run manifest_path at index "
                f"{slice_index}: {source_manifest_path}"
            )
        child_manifest_path = _resolve_target_contract_design_existing_path(
            child_manifest_raw,
            base_path=source_manifest_path.parent,
        )
        source_slice_inputs.append(str(child_manifest_path))
    return source_slice_inputs


def _resolve_target_contract_design_slice_inputs(
    slice_inputs: Sequence[str | Path],
) -> dict[str, list[dict[str, object]]]:
    if not slice_inputs:
        raise ValueError("target contract design evaluation requires at least one slice input")
    resolved_slice_inputs: list[dict[str, object]] = []
    slice_rows: list[dict[str, object]] = []
    for slice_index, raw_input in enumerate(slice_inputs, start=1):
        resolved_slice_input, slice_row = _resolve_target_contract_design_slice_input(
            raw_input,
            slice_index=slice_index,
        )
        resolved_slice_inputs.append(resolved_slice_input)
        slice_rows.append(slice_row)
    return {
        "resolved_slice_inputs": resolved_slice_inputs,
        "slice_rows": slice_rows,
    }


def _resolve_target_contract_design_slice_input(
    raw_input: str | Path,
    *,
    slice_index: int,
) -> tuple[dict[str, object], dict[str, object]]:
    source_path = Path(raw_input).expanduser()
    if not source_path.exists():
        raise FileNotFoundError(f"target contract design slice input not found: {source_path}")
    source_path = source_path.resolve()

    row_diagnostics_override: Path | None = None
    if source_path.is_dir():
        child_root = source_path
        child_manifest_path = child_root / "run_manifest.json"
        source_type = "child_run_root"
    elif source_path.suffix.lower() == ".json":
        child_manifest_path = source_path
        child_root = child_manifest_path.parent
        source_type = "governed_slice_manifest"
    elif source_path.suffix.lower() == ".parquet":
        row_diagnostics_override = source_path
        child_root = source_path.parent
        child_manifest_path = child_root / "run_manifest.json"
        source_type = "target_contract_row_diagnostics_parquet"
    else:
        raise ValueError(
            "target contract design explicit inputs must be governed JSON manifests, child run directories, "
            f"or target_contract_row_diagnostics.parquet files: {source_path}"
        )

    if not child_manifest_path.exists():
        raise FileNotFoundError(
            "target contract design explicit slice input requires governed child run manifest: "
            f"{child_manifest_path}"
        )

    child_manifest_path = child_manifest_path.resolve()
    child_manifest_payload = read_json(child_manifest_path)
    artifact_files = child_manifest_payload.get("artifact_files")
    if not isinstance(artifact_files, dict):
        raise ValueError(
            "target contract design child manifest has invalid artifact_files: "
            f"{child_manifest_path}"
        )

    row_diagnostics_path = (
        row_diagnostics_override.resolve()
        if row_diagnostics_override is not None else
        _resolve_target_contract_design_child_artifact_path(
            child_manifest_payload,
            child_manifest_path=child_manifest_path,
            artifact_key="target_contract_row_diagnostics_parquet",
            default_name="target_contract_row_diagnostics.parquet",
        )
    )
    target_mode_paths = {
        "summary_json_path": str(
            _resolve_target_contract_design_child_artifact_path(
                child_manifest_payload,
                child_manifest_path=child_manifest_path,
                artifact_key="target_mode_comparison_summary_json",
                default_name="target_mode_comparison_summary.json",
            )
        ),
        "bucket_ranking_json_path": str(
            _resolve_target_contract_design_child_artifact_path(
                child_manifest_payload,
                child_manifest_path=child_manifest_path,
                artifact_key="target_mode_bucket_ranking_json",
                default_name="target_mode_bucket_ranking.json",
            )
        ),
        "residual_examples_json_path": str(
            _resolve_target_contract_design_child_artifact_path(
                child_manifest_payload,
                child_manifest_path=child_manifest_path,
                artifact_key="target_mode_residual_examples_json",
                default_name="target_mode_residual_examples.json",
            )
        ),
        "promotion_gate_json_path": str(
            _resolve_target_contract_design_child_artifact_path(
                child_manifest_payload,
                child_manifest_path=child_manifest_path,
                artifact_key="target_contract_promotion_gate_json",
                default_name="target_contract_promotion_gate.json",
            )
        ),
    }
    target_contract_paths = {
        "summary_json_path": str(
            _resolve_target_contract_design_child_artifact_path(
                child_manifest_payload,
                child_manifest_path=child_manifest_path,
                artifact_key="target_contract_comparison_summary_json",
                default_name="target_contract_comparison_summary.json",
            )
        ),
        "divergence_summary_json_path": str(
            _resolve_target_contract_design_child_artifact_path(
                child_manifest_payload,
                child_manifest_path=child_manifest_path,
                artifact_key="target_contract_divergence_summary_json",
                default_name="target_contract_divergence_summary.json",
            )
        ),
    }
    _require_target_mode_slice_artifact_paths(target_mode_paths, target_contract_paths)

    dataset_path = _extract_training_ready_dataset_path_from_manifest(
        child_manifest_payload,
        manifest_path=child_manifest_path,
    )
    child_run_id = str(child_manifest_payload.get("run_id") or child_root.name)
    slice_identifier = str(
        child_manifest_payload.get("slice_identifier")
        or child_manifest_payload.get("dataset_run_id")
        or child_manifest_payload.get("run_id")
        or child_root.name
    )
    target_mode_summary_payload = read_json(Path(target_mode_paths["summary_json_path"]))
    slice_gate_payload = read_json(Path(target_mode_paths["promotion_gate_json_path"]))
    source_target_mode = _resolve_target_contract_design_slice_target_mode(
        child_manifest_payload=child_manifest_payload,
        target_mode_summary_payload=target_mode_summary_payload,
        child_manifest_path=child_manifest_path,
    )

    slice_spec = {
        "slice_identifier": slice_identifier,
        "source_type": source_type,
        "source_path": str(source_path),
        "source_manifest_path": str(child_manifest_path),
        "dataset_path": str(dataset_path),
    }
    slice_row = _target_mode_multi_slice_summary_row(
        slice_index=slice_index,
        slice_spec=slice_spec,
        child_run_id=child_run_id,
        training_manifest_payload=child_manifest_payload,
        target_mode_summary_payload=target_mode_summary_payload,
        slice_gate_payload=slice_gate_payload,
        target_mode_paths=target_mode_paths,
        target_contract_paths=target_contract_paths,
    )
    return {
        "slice_index": slice_index,
        "slice_identifier": slice_identifier,
        "source_type": source_type,
        "source_path": str(source_path),
        "source_manifest_path": str(child_manifest_path),
        "child_run_root": str(child_root.resolve()),
        "child_run_id": child_run_id,
        "dataset_path": str(dataset_path),
        "row_diagnostics_path": str(row_diagnostics_path),
        "target_mode_summary_json_path": target_mode_paths["summary_json_path"],
        "target_contract_promotion_gate_json_path": target_mode_paths["promotion_gate_json_path"],
        "target_contract_summary_json_path": target_contract_paths["summary_json_path"],
        "target_contract_divergence_summary_json_path": target_contract_paths["divergence_summary_json_path"],
        "source_target_mode": source_target_mode,
    }, slice_row


def _resolve_target_contract_design_child_artifact_path(
    child_manifest_payload: dict[str, object],
    *,
    child_manifest_path: Path,
    artifact_key: str,
    default_name: str,
) -> Path:
    artifact_files = child_manifest_payload.get("artifact_files")
    if not isinstance(artifact_files, dict):
        raise ValueError(
            f"target contract design child manifest has invalid artifact_files: {child_manifest_path}"
        )
    artifact_value = artifact_files.get(artifact_key)
    if isinstance(artifact_value, str) and artifact_value.strip():
        return _resolve_target_contract_design_existing_path(
            artifact_value,
            base_path=child_manifest_path.parent,
        )
    default_path = child_manifest_path.parent / default_name
    if default_path.exists():
        return default_path.resolve()
    raise FileNotFoundError(
        "target contract design requires governed child artifact "
        f"{artifact_key!r}: {default_path}"
    )


def _resolve_target_contract_design_slice_target_mode(
    *,
    child_manifest_payload: dict[str, object],
    target_mode_summary_payload: dict[str, object],
    child_manifest_path: Path,
) -> PromotionTrainerTargetMode:
    raw_target_mode = target_mode_summary_payload.get("target_mode") or child_manifest_payload.get("target_mode")
    if not isinstance(raw_target_mode, str) or not raw_target_mode:
        raise ValueError(
            "target contract design explicit slice input is missing target_mode evidence: "
            f"{child_manifest_path}"
        )
    return _resolve_promotion_trainer_target_mode(raw_target_mode)


def _resolve_target_contract_design_source_target_mode(
    *,
    manifest_target_mode: object,
    resolved_slice_inputs: Sequence[dict[str, object]],
) -> PromotionTrainerTargetMode:
    resolved_modes: set[PromotionTrainerTargetMode] = set()
    if isinstance(manifest_target_mode, str) and manifest_target_mode:
        resolved_modes.add(_resolve_promotion_trainer_target_mode(manifest_target_mode))
    for slice_spec in resolved_slice_inputs:
        raw_mode = slice_spec.get("source_target_mode")
        if isinstance(raw_mode, str) and raw_mode:
            resolved_modes.add(_resolve_promotion_trainer_target_mode(raw_mode))
    if not resolved_modes:
        raise ValueError("target contract design evaluator could not resolve a source target_mode")
    if len(resolved_modes) != 1:
        raise ValueError(
            "target contract design evaluator requires a single consistent source target_mode across all slices"
        )
    return next(iter(resolved_modes))


def _build_target_contract_design_explicit_source_manifest_payload(
    *,
    resolved_slice_inputs: Sequence[dict[str, object]],
    slice_rows: Sequence[dict[str, object]],
) -> dict[str, object]:
    summary_frame = pd.DataFrame(list(slice_rows))
    if summary_frame.empty:
        raise ValueError("target contract design explicit slice inputs produced no source summary rows")
    gate_outcome = _build_target_mode_shadow_stability_gate_payload(summary_frame)
    gate_inputs = gate_outcome.get("gate_inputs")
    if not isinstance(gate_inputs, dict):
        raise ValueError("target contract design explicit slice inputs produced invalid gate inputs")
    top_driver = gate_inputs.get("top_persistent_divergence_driver")
    if top_driver != _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS:
        raise ValueError(
            "target contract design requires persistent stock_basis_proxy_mismatch evidence; "
            f"top_persistent_divergence_driver={top_driver!r}"
        )
    source_target_mode = _resolve_target_contract_design_source_target_mode(
        manifest_target_mode=None,
        resolved_slice_inputs=resolved_slice_inputs,
    )
    return {
        "run_id": _TARGET_CONTRACT_DESIGN_EXPLICIT_SOURCE_MANIFEST_PATH,
        "target_mode": source_target_mode,
        "gate_inputs": gate_inputs,
        "gate_outcome": gate_outcome,
        "slice_runs": [
            {
                "slice_identifier": str(slice_spec["slice_identifier"]),
                "child_run_id": str(slice_spec["child_run_id"]),
                "manifest_path": str(slice_spec["source_manifest_path"]),
                "target_mode_summary_json_path": str(slice_spec["target_mode_summary_json_path"]),
                "target_contract_promotion_gate_json_path": str(
                    slice_spec["target_contract_promotion_gate_json_path"]
                ),
            }
            for slice_spec in resolved_slice_inputs
        ],
    }


def _load_target_contract_design_source_rows(
    multi_slice_manifest_payload: dict[str, object],
    *,
    source_manifest_path: Path,
) -> pd.DataFrame:
    gate_inputs = _target_contract_design_source_gate_inputs(multi_slice_manifest_payload)
    top_driver = gate_inputs.get("top_persistent_divergence_driver")
    if top_driver != _TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS:
        raise ValueError(
            "target contract design requires persistent stock_basis_proxy_mismatch evidence; "
            f"top_persistent_divergence_driver={top_driver!r}"
        )
    slice_runs = multi_slice_manifest_payload.get("slice_runs")
    if not isinstance(slice_runs, list) or not slice_runs:
        raise ValueError("target contract design requires multi-slice manifest slice_runs evidence")

    resolved_slice_runs: list[dict[str, object]] = []
    for slice_run in slice_runs:
        if not isinstance(slice_run, dict):
            raise ValueError("target contract design slice_runs entries must be objects")
        manifest_value = slice_run.get("manifest_path")
        if not isinstance(manifest_value, str) or not manifest_value:
            raise ValueError("target contract design slice run is missing manifest_path")
        child_manifest_path = _resolve_target_contract_design_existing_path(
            manifest_value,
            base_path=source_manifest_path.parent,
        )
        child_manifest_payload = read_json(child_manifest_path)
        artifact_files = child_manifest_payload.get("artifact_files", {})
        if not isinstance(artifact_files, dict):
            raise ValueError(f"target contract design child manifest has invalid artifact_files: {child_manifest_path}")
        row_path_value = artifact_files.get("target_contract_row_diagnostics_parquet")
        row_diagnostics_path = (
            _resolve_target_contract_design_existing_path(str(row_path_value), base_path=child_manifest_path.parent)
            if isinstance(row_path_value, str) and row_path_value else
            child_manifest_path.parent / "target_contract_row_diagnostics.parquet"
        )
        if not row_diagnostics_path.exists():
            raise FileNotFoundError(
                "target contract design requires per-slice target_contract_row_diagnostics.parquet evidence: "
                f"{row_diagnostics_path}"
            )
        slice_identifier = str(
            slice_run.get("slice_identifier")
            or child_manifest_payload.get("run_id")
            or child_manifest_path.parent.name
        )
        child_run_id = str(
            slice_run.get("child_run_id") or child_manifest_payload.get("run_id") or child_manifest_path.parent.name
        )
        resolved_slice_runs.append(
            {
                "slice_identifier": slice_identifier,
                "child_run_id": child_run_id,
                "row_diagnostics_path": str(row_diagnostics_path.resolve()),
            }
        )
    return _load_target_contract_design_rows_from_slice_specs(resolved_slice_runs)


def _load_target_contract_design_source_rows_from_explicit_slice_inputs(
    resolved_slice_inputs: Sequence[dict[str, object]],
) -> pd.DataFrame:
    return _load_target_contract_design_rows_from_slice_specs(resolved_slice_inputs)


def _load_target_contract_design_rows_from_slice_specs(
    slice_specs: Sequence[dict[str, object]],
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for slice_spec in slice_specs:
        row_diagnostics_path = Path(str(slice_spec["row_diagnostics_path"]))
        if not row_diagnostics_path.exists():
            raise FileNotFoundError(
                "target contract design requires per-slice target_contract_row_diagnostics.parquet evidence: "
                f"{row_diagnostics_path}"
            )
        frame = pd.read_parquet(row_diagnostics_path).copy()
        if frame.empty:
            raise ValueError(f"target contract design row diagnostics are empty: {row_diagnostics_path}")
        frame["slice_identifier"] = str(slice_spec["slice_identifier"])
        frame["child_run_id"] = str(slice_spec["child_run_id"])
        frame["source_row_diagnostics_path"] = str(row_diagnostics_path.resolve())
        frames.append(frame)
    return pd.concat(frames, axis=0, ignore_index=True, sort=False)


def _build_completed_slice_inventory_frame(discovery_inputs: Sequence[str | Path]) -> pd.DataFrame:
    if not discovery_inputs:
        raise ValueError("target design repeated evidence discovery requires at least one input path")
    candidates = _iter_completed_slice_candidates(discovery_inputs)
    rows = [_completed_slice_inventory_row(candidate) for candidate in candidates]
    inventory_frame = pd.DataFrame(rows)
    if inventory_frame.empty:
        return inventory_frame
    seen_fingerprints: set[str] = set()
    for row_index, row in inventory_frame.iterrows():
        fingerprint = str(row.get("completed_slice_fingerprint", ""))
        if bool(row.get("included", False)) and fingerprint in seen_fingerprints:
            inventory_frame.loc[row_index, "included"] = False
            inventory_frame.loc[row_index, "exclusion_reason"] = "duplicate_completed_slice_fingerprint"
        if bool(inventory_frame.loc[row_index, "included"]):
            seen_fingerprints.add(fingerprint)
    return inventory_frame.sort_values(
        ["included", "row_count", "slice_identifier"],
        ascending=[False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def _iter_completed_slice_candidates(discovery_inputs: Sequence[str | Path]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen_paths: set[Path] = set()
    for raw_input in discovery_inputs:
        input_path = Path(raw_input).expanduser()
        if not input_path.exists():
            raise FileNotFoundError(f"target design repeated evidence discovery input not found: {input_path}")
        if input_path.is_dir():
            for dataset_path in sorted(input_path.rglob("training_ready.parquet")):
                resolved = dataset_path.resolve()
                if resolved not in seen_paths:
                    candidates.append(
                        {
                            "source_input_path": str(input_path.resolve()),
                            "slice_input_path": str(resolved),
                            "source_type": "training_ready_parquet",
                            "source_manifest_path": None,
                        }
                    )
                    seen_paths.add(resolved)
        elif input_path.suffix.lower() == ".parquet":
            resolved = input_path.resolve()
            if resolved not in seen_paths:
                candidates.append(
                    {
                        "source_input_path": str(resolved),
                        "slice_input_path": str(resolved),
                        "source_type": "training_ready_parquet",
                        "source_manifest_path": None,
                    }
                )
                seen_paths.add(resolved)
        elif input_path.suffix.lower() == ".json":
            manifest_payload = read_json(input_path)
            dataset_path = _extract_training_ready_dataset_path_from_manifest(manifest_payload, manifest_path=input_path)
            resolved = dataset_path.resolve()
            if resolved not in seen_paths:
                candidates.append(
                    {
                        "source_input_path": str(input_path.resolve()),
                        "slice_input_path": str(resolved),
                        "source_type": "governed_slice_manifest",
                        "source_manifest_path": str(input_path.resolve()),
                    }
                )
                seen_paths.add(resolved)
        else:
            raise ValueError(
                "target design repeated evidence discovery inputs must be directories, training-ready parquet files, "
                f"or governed JSON manifests: {input_path}"
            )
    return candidates


def _completed_slice_inventory_row(candidate: dict[str, object]) -> dict[str, object]:
    dataset_path = Path(str(candidate["slice_input_path"]))
    slice_identifier = _target_mode_slice_identifier_from_parquet(dataset_path)
    base_row = {
        "slice_identifier": slice_identifier,
        "source_type": str(candidate["source_type"]),
        "source_input_path": str(candidate["source_input_path"]),
        "source_manifest_path": candidate.get("source_manifest_path"),
        "slice_input_path": str(dataset_path),
        "row_count": 0,
        "historical_allocation_evidence_column": None,
        "historical_allocation_non_null_count": 0,
        "realised_promo_units_evidence_column": None,
        "realised_promo_units_non_null_count": 0,
        "unit_cost_evidence_column": None,
        "unit_cost_positive_count": 0,
        "historical_target_valid_row_count": 0,
        "completed_slice_fingerprint": None,
        "included": False,
        "exclusion_reason": "not_evaluated",
    }
    try:
        dataset = pd.read_parquet(dataset_path)
        base_row["row_count"] = int(len(dataset.index))
        allocation_column, allocation_count = _first_available_evidence_count(dataset, HISTORICAL_ALLOCATION_SOURCE_COLUMNS)
        realised_column, realised_count = _first_available_evidence_count(dataset, HISTORICAL_REALISED_PROMO_UNITS_SOURCE_COLUMNS)
        cost_column, cost_count = _first_available_evidence_count(dataset, HISTORICAL_UNIT_COST_SOURCE_COLUMNS, positive_only=True)
        base_row.update(
            {
                "historical_allocation_evidence_column": allocation_column,
                "historical_allocation_non_null_count": allocation_count,
                "realised_promo_units_evidence_column": realised_column,
                "realised_promo_units_non_null_count": realised_count,
                "unit_cost_evidence_column": cost_column,
                "unit_cost_positive_count": cost_count,
                "completed_slice_fingerprint": _completed_slice_fingerprint(dataset),
            }
        )
        with_target = apply_ft_target_historical_allocation(dataset)
        valid_rows = int(
            pd.to_numeric(with_target["target_historical_allocation_target_valid_flag"], errors="coerce")
            .fillna(0.0)
            .ge(1.0)
            .sum()
        )
        base_row["historical_target_valid_row_count"] = valid_rows
        exclusion_reasons: list[str] = []
        if len(dataset.index) < _TARGET_DESIGN_COMPLETED_SLICE_DISCOVERY_MIN_ROW_COUNT:
            exclusion_reasons.append("row_count_below_minimum")
        if allocation_count <= 0:
            exclusion_reasons.append("missing_historical_allocation_evidence")
        if realised_count <= 0:
            exclusion_reasons.append("missing_realised_promo_units_evidence")
        if cost_count <= 0:
            exclusion_reasons.append("missing_positive_unit_cost_evidence")
        if valid_rows <= 0:
            exclusion_reasons.append("no_valid_historical_target_rows")
        base_row["included"] = not exclusion_reasons
        base_row["exclusion_reason"] = "included" if not exclusion_reasons else ";".join(exclusion_reasons)
    except Exception as exc:
        base_row["exclusion_reason"] = f"evidence_read_or_target_build_failed:{type(exc).__name__}:{exc}"
    return base_row


def _first_available_evidence_count(
    frame: pd.DataFrame,
    candidate_columns: tuple[str, ...],
    *,
    positive_only: bool = False,
) -> tuple[str | None, int]:
    for column_name in candidate_columns:
        if column_name in frame.columns:
            values = pd.to_numeric(frame[column_name], errors="coerce")
            valid_mask = values.gt(0.0) if positive_only else values.notna()
            return column_name, int(valid_mask.sum())
    return None, 0


def _completed_slice_fingerprint(frame: pd.DataFrame) -> str:
    row_count = len(frame.index)
    date_column = next(
        (column_name for column_name in ("promotion_start_date_date", "promotion_start_date") if column_name in frame.columns),
        None,
    )
    if date_column is not None:
        dates = pd.to_datetime(frame[date_column], errors="coerce")
        date_min = str(dates.min().date()) if dates.notna().any() else "missing"
        date_max = str(dates.max().date()) if dates.notna().any() else "missing"
    else:
        date_min = "missing"
        date_max = "missing"
    fingerprint_columns = [
        column_name
        for column_name in (
            "store_number",
            "sku_number",
            "promotion_start_date_date",
            "promotional_end_date_date",
            "promotion_name",
        )
        if column_name in frame.columns
    ]
    if fingerprint_columns:
        hashed = pd.util.hash_pandas_object(frame.loc[:, fingerprint_columns].astype(str), index=False).sum()
        content_hash = str(int(hashed))
    else:
        content_hash = "no_key_columns"
    return f"rows={row_count}|start={date_min}|end={date_max}|hash={content_hash}"


def _completed_slice_inventory_payload(run_id: str, inventory_frame: pd.DataFrame) -> dict[str, object]:
    included_count = int(inventory_frame["included"].astype(bool).sum()) if "included" in inventory_frame.columns else 0
    reason_counts = (
        inventory_frame["exclusion_reason"].astype(str).value_counts(dropna=False).to_dict()
        if "exclusion_reason" in inventory_frame.columns else {}
    )
    return {
        "run_id": run_id,
        "row_scope": "completed_training_ready_slice_inventory",
        "candidate_slice_count": int(len(inventory_frame.index)),
        "included_slice_count": included_count,
        "excluded_slice_count": int(len(inventory_frame.index) - included_count),
        "minimum_row_count": _TARGET_DESIGN_COMPLETED_SLICE_DISCOVERY_MIN_ROW_COUNT,
        "exclusion_reason_counts": {str(key): int(value) for key, value in reason_counts.items()},
        "rows": _json_ready_records(inventory_frame),
    }


def _build_target_design_repeated_evidence_summary_frame(
    *,
    target_mode_summary_payload: dict[str, object],
    target_design_summary_payload: dict[str, object],
    target_design_candidate: str,
) -> pd.DataFrame:
    shadow_rows = target_mode_summary_payload.get("slice_rows")
    design_rows = target_design_summary_payload.get("slice_candidate_rows")
    if not isinstance(shadow_rows, list) or not shadow_rows:
        raise ValueError("target design repeated evidence requires target-mode multi-slice slice_rows")
    if not isinstance(design_rows, list) or not design_rows:
        raise ValueError("target design repeated evidence requires target-design slice_candidate_rows")
    shadow_frame = pd.DataFrame(shadow_rows)
    design_frame = pd.DataFrame(design_rows)
    _require_columns(
        shadow_frame,
        (
            "slice_identifier",
            "evaluation_row_count",
            "comparable_rows",
            "coverage_rate",
            "historical_exclusion_rate",
            "current_shadow_excess_capital_mae_on_historical_target",
            "historical_shadow_excess_capital_mae_on_historical_target",
            "candidate_capital_mae_improvement",
            "candidate_capital_mae_improvement_rate",
            "dominant_divergence_driver",
            "slice_gate_decision",
        ),
        context="target design repeated evidence target-mode summary",
    )
    _require_columns(
        design_frame,
        (
            "candidate_name",
            "slice_identifier",
            "candidate_units_mae_against_business_mistake",
            "candidate_capital_mae_against_business_mistake",
            "candidate_units_mae_improvement_rate_vs_stock_basis",
            "cleaner_promotion_decision_boundary",
            "reduces_dependence_on_stock_basis_proxy_mismatch",
            "design_priority",
        ),
        context="target design repeated evidence target-design summary",
    )
    candidate_design_frame = design_frame.loc[design_frame["candidate_name"].astype(str).eq(target_design_candidate)].copy()
    if candidate_design_frame.empty:
        raise ValueError(f"target design repeated evidence missing candidate slice rows for {target_design_candidate!r}")
    best_by_slice = _target_design_candidate_best_by_slice(design_frame)
    candidate_design_frame = candidate_design_frame.merge(best_by_slice, on="slice_identifier", how="left")
    merged = shadow_frame.merge(candidate_design_frame, on="slice_identifier", how="left", suffixes=("", "_design"))
    if merged["candidate_name"].isna().any():
        missing_slices = sorted(merged.loc[merged["candidate_name"].isna(), "slice_identifier"].astype(str).tolist())
        raise ValueError("target design repeated evidence missing candidate design metrics for slices: " + ", ".join(missing_slices))
    return pd.DataFrame(
        {
            "slice_identifier": merged["slice_identifier"].astype(str),
            "row_count": pd.to_numeric(merged["evaluation_row_count"], errors="coerce"),
            "comparable_rows": pd.to_numeric(merged["comparable_rows"], errors="coerce"),
            "coverage_rate": pd.to_numeric(merged["coverage_rate"], errors="coerce"),
            "exclusion_rate": pd.to_numeric(merged["historical_exclusion_rate"], errors="coerce"),
            "current_shadow_mae_on_historical_target": pd.to_numeric(
                merged["current_shadow_excess_capital_mae_on_historical_target"], errors="coerce"
            ),
            "candidate_shadow_mae_on_historical_target": pd.to_numeric(
                merged["historical_shadow_excess_capital_mae_on_historical_target"], errors="coerce"
            ),
            "absolute_improvement": pd.to_numeric(merged["candidate_capital_mae_improvement"], errors="coerce"),
            "relative_improvement": pd.to_numeric(merged["candidate_capital_mae_improvement_rate"], errors="coerce"),
            "dominant_divergence_driver": merged["dominant_divergence_driver"].astype(str),
            "slice_gate_decision": merged["slice_gate_decision"].astype(str),
            "target_design_candidate": target_design_candidate,
            "candidate_units_mae_against_business_mistake": pd.to_numeric(
                merged["candidate_units_mae_against_business_mistake"], errors="coerce"
            ),
            "candidate_capital_mae_against_business_mistake": pd.to_numeric(
                merged["candidate_capital_mae_against_business_mistake"], errors="coerce"
            ),
            "candidate_units_mae_improvement_rate_vs_stock_basis": pd.to_numeric(
                merged["candidate_units_mae_improvement_rate_vs_stock_basis"], errors="coerce"
            ),
            "cleaner_promotion_decision_boundary": merged["cleaner_promotion_decision_boundary"].astype(bool),
            "reduces_dependence_on_stock_basis_proxy_mismatch": merged[
                "reduces_dependence_on_stock_basis_proxy_mismatch"
            ].astype(bool),
            "best_candidate_name_for_slice": merged["best_candidate_name_for_slice"].astype(str),
            "candidate_is_best_for_slice": merged["best_candidate_name_for_slice"].astype(str).eq(target_design_candidate),
        }
    )


def _target_design_candidate_best_by_slice(design_frame: pd.DataFrame) -> pd.DataFrame:
    non_stock_frame = design_frame.loc[~design_frame["candidate_name"].astype(str).eq(_TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE)].copy()
    non_stock_frame["_units_mae_sort"] = pd.to_numeric(
        non_stock_frame["candidate_units_mae_against_business_mistake"], errors="coerce"
    ).fillna(np.inf)
    non_stock_frame["_capital_mae_sort"] = pd.to_numeric(
        non_stock_frame["candidate_capital_mae_against_business_mistake"], errors="coerce"
    ).fillna(np.inf)
    non_stock_frame["_design_priority_sort"] = pd.to_numeric(non_stock_frame["design_priority"], errors="coerce").fillna(999)
    ranked = non_stock_frame.sort_values(
        ["slice_identifier", "_units_mae_sort", "_capital_mae_sort", "_design_priority_sort", "candidate_name"],
        ascending=[True, True, True, True, True],
        kind="mergesort",
    )
    return ranked.groupby("slice_identifier", as_index=False).first().loc[:, ["slice_identifier", "candidate_name"]].rename(
        columns={"candidate_name": "best_candidate_name_for_slice"}
    )


def _build_target_design_repeated_evidence_gate_payload(
    summary_frame: pd.DataFrame,
    *,
    target_design_candidate: str,
) -> dict[str, object]:
    required_columns = (
        "slice_identifier",
        "comparable_rows",
        "coverage_rate",
        "exclusion_rate",
        "absolute_improvement",
        "relative_improvement",
        "dominant_divergence_driver",
        "candidate_is_best_for_slice",
        "cleaner_promotion_decision_boundary",
        "reduces_dependence_on_stock_basis_proxy_mismatch",
    )
    _require_columns(summary_frame, required_columns, context="target design repeated evidence gate")
    numeric_columns = (
        "comparable_rows",
        "coverage_rate",
        "exclusion_rate",
        "absolute_improvement",
        "relative_improvement",
    )
    numeric_values: dict[str, pd.Series] = {}
    missing_numeric_columns: list[str] = []
    for column_name in numeric_columns:
        series = pd.to_numeric(summary_frame[column_name], errors="coerce")
        if series.isna().any():
            missing_numeric_columns.append(column_name)
        numeric_values[column_name] = series
    if missing_numeric_columns:
        raise ValueError(
            "target design repeated evidence gate missing required numeric slice evidence: "
            + ", ".join(sorted(missing_numeric_columns))
        )
    slice_count = int(len(summary_frame.index))
    comparable_rows = numeric_values["comparable_rows"]
    coverage_rate = numeric_values["coverage_rate"]
    exclusion_rate = numeric_values["exclusion_rate"]
    absolute_improvement = numeric_values["absolute_improvement"]
    relative_improvement = numeric_values["relative_improvement"]
    positive_improvement = absolute_improvement.gt(0.0) & relative_improvement.gt(0.0)
    positive_relative_improvement = relative_improvement.loc[positive_improvement]
    positive_improvement_slice_share = float(positive_improvement.mean()) if slice_count else 0.0
    median_relative_improvement = float(positive_relative_improvement.median()) if not positive_relative_improvement.empty else 0.0
    mean_relative_improvement = float(positive_relative_improvement.mean()) if not positive_relative_improvement.empty else 0.0
    relative_improvement_cv = (
        float(positive_relative_improvement.std(ddof=0) / mean_relative_improvement)
        if len(positive_relative_improvement.index) > 1 and mean_relative_improvement > 0.0 else 0.0
    )
    stock_basis_mask = summary_frame["dominant_divergence_driver"].astype(str).eq(_TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS)
    stock_basis_share = float(stock_basis_mask.mean()) if slice_count else 0.0
    best_candidate_slice_share = float(summary_frame["candidate_is_best_for_slice"].astype(bool).mean()) if slice_count else 0.0
    clean_boundary_slice_share = float(summary_frame["cleaner_promotion_decision_boundary"].astype(bool).mean()) if slice_count else 0.0
    dependency_reduced_slice_share = float(
        summary_frame["reduces_dependence_on_stock_basis_proxy_mismatch"].astype(bool).mean()
    ) if slice_count else 0.0
    criteria = {
        "minimum_slice_count": _TARGET_DESIGN_REPEATED_MIN_SLICE_COUNT,
        "minimum_aggregate_comparable_rows": _TARGET_DESIGN_REPEATED_MIN_AGGREGATE_COMPARABLE_ROWS,
        "minimum_comparable_rows_per_slice": _TARGET_DESIGN_REPEATED_MIN_COMPARABLE_ROWS_PER_SLICE,
        "minimum_coverage_rate": _TARGET_DESIGN_REPEATED_MIN_COVERAGE_RATE,
        "maximum_exclusion_rate": _TARGET_DESIGN_REPEATED_MAX_EXCLUSION_RATE,
        "minimum_positive_improvement_slice_share": _TARGET_DESIGN_REPEATED_MIN_POSITIVE_IMPROVEMENT_SHARE,
        "minimum_median_relative_improvement": _TARGET_DESIGN_REPEATED_MIN_MEDIAN_RELATIVE_IMPROVEMENT,
        "maximum_relative_improvement_coefficient_of_variation": _TARGET_DESIGN_REPEATED_MAX_RELATIVE_IMPROVEMENT_CV,
        "minimum_stock_basis_dominance_share": _TARGET_DESIGN_REPEATED_MIN_STOCK_BASIS_DOMINANCE_SHARE,
        "minimum_best_candidate_slice_share": _TARGET_DESIGN_REPEATED_MIN_BEST_CANDIDATE_SLICE_SHARE,
    }
    blockers: list[str] = []
    if slice_count < _TARGET_DESIGN_REPEATED_MIN_SLICE_COUNT:
        blockers.append("insufficient_completed_slice_count")
    if int(comparable_rows.sum()) < _TARGET_DESIGN_REPEATED_MIN_AGGREGATE_COMPARABLE_ROWS:
        blockers.append("insufficient_aggregate_comparable_rows")
    if not bool(comparable_rows.ge(_TARGET_DESIGN_REPEATED_MIN_COMPARABLE_ROWS_PER_SLICE).all()):
        blockers.append("insufficient_comparable_rows_per_slice")
    if not bool(coverage_rate.ge(_TARGET_DESIGN_REPEATED_MIN_COVERAGE_RATE).all()):
        blockers.append("coverage_below_threshold")
    if not bool(exclusion_rate.le(_TARGET_DESIGN_REPEATED_MAX_EXCLUSION_RATE).all()):
        blockers.append("exclusion_rate_above_threshold")
    if positive_improvement_slice_share < _TARGET_DESIGN_REPEATED_MIN_POSITIVE_IMPROVEMENT_SHARE:
        blockers.append("candidate_did_not_improve_on_enough_slices")
    if median_relative_improvement < _TARGET_DESIGN_REPEATED_MIN_MEDIAN_RELATIVE_IMPROVEMENT:
        blockers.append("candidate_median_improvement_trivial")
    if relative_improvement_cv > _TARGET_DESIGN_REPEATED_MAX_RELATIVE_IMPROVEMENT_CV:
        blockers.append("candidate_improvement_not_stable")
    if stock_basis_share < _TARGET_DESIGN_REPEATED_MIN_STOCK_BASIS_DOMINANCE_SHARE:
        blockers.append("stock_basis_proxy_mismatch_not_persistent")
    if best_candidate_slice_share < _TARGET_DESIGN_REPEATED_MIN_BEST_CANDIDATE_SLICE_SHARE:
        blockers.append("design_candidate_not_consistently_best")
    if clean_boundary_slice_share < _TARGET_CONTRACT_DESIGN_MIN_CLEAN_BOUNDARY_SHARE:
        blockers.append("candidate_boundary_not_cleaner_on_enough_slices")
    if dependency_reduced_slice_share < _TARGET_DESIGN_REPEATED_MIN_BEST_CANDIDATE_SLICE_SHARE:
        blockers.append("candidate_still_depends_on_stock_basis_proxy")
    should_shadow = not blockers
    return {
        "row_scope": "out_of_sample_validation_and_test_by_completed_slice",
        "target_design_candidate": target_design_candidate,
        "decision": "candidate_for_shadow_training" if should_shadow else "diagnostics_only",
        "should_remain_diagnostics_only": not should_shadow,
        "should_promote_to_candidate_for_shadow_training": should_shadow,
        "should_promote_to_candidate_for_primary_training": False,
        "primary_promotion_allowed_in_this_pass": False,
        "primary_promotion_blockers": ["target_design_repeated_evidence_pass_cannot_promote_primary"],
        "shadow_promotion_blockers": blockers,
        "promotion_criteria": criteria,
        "gate_inputs": {
            "slice_count": slice_count,
            "total_comparable_rows": int(comparable_rows.sum()),
            "minimum_comparable_rows_observed": int(comparable_rows.min()) if slice_count else 0,
            "minimum_coverage_rate_observed": float(coverage_rate.min()) if slice_count else 0.0,
            "maximum_exclusion_rate_observed": float(exclusion_rate.max()) if slice_count else 0.0,
            "positive_improvement_slice_share": positive_improvement_slice_share,
            "median_relative_improvement": median_relative_improvement,
            "mean_relative_improvement": mean_relative_improvement,
            "relative_improvement_coefficient_of_variation": relative_improvement_cv,
            "stock_basis_proxy_mismatch_slice_share": stock_basis_share,
            "best_candidate_slice_share": best_candidate_slice_share,
            "clean_boundary_slice_share": clean_boundary_slice_share,
            "stock_basis_dependency_reduced_slice_share": dependency_reduced_slice_share,
            "dominant_divergence_driver_counts": {
                str(key): int(value)
                for key, value in summary_frame["dominant_divergence_driver"].astype(str).value_counts(dropna=False).to_dict().items()
            },
            "per_slice_gate_inputs": _json_ready_records(summary_frame),
        },
        "current_trainer_contract_remains_live_default": True,
        "production_training_target_was_replaced": False,
        "policy_remains_paused": True,
        "policy_rules_were_changed": False,
        "stage_11_was_changed": False,
        "store_facing_csv_was_changed": False,
        "explanation": (
            "sell_through_aligned_allocation_error has repeated stable completed-slice evidence for shadow-training candidacy; primary remains blocked."
            if should_shadow else
            "sell_through_aligned_allocation_error remains diagnostics-only because repeated completed-slice evidence is not yet strong enough."
        ),
    }


def _build_target_design_repeated_evidence_residual_examples(
    *,
    target_design_residual_payload: dict[str, object],
    target_design_candidate: str,
) -> pd.DataFrame:
    residual_rows = target_design_residual_payload.get("rows", [])
    if not isinstance(residual_rows, list) or not residual_rows:
        return pd.DataFrame()
    frame = pd.DataFrame([row for row in residual_rows if isinstance(row, dict)])
    if frame.empty:
        return frame
    frame["target_design_candidate"] = target_design_candidate
    sort_columns = [
        column_name
        for column_name in ("stock_basis_capital_error_abs", "stock_basis_units_error_abs")
        if column_name in frame.columns
    ]
    for column_name in sort_columns:
        frame[column_name] = pd.to_numeric(frame[column_name], errors="coerce")
    if sort_columns:
        frame = frame.sort_values(sort_columns, ascending=[False] * len(sort_columns), kind="mergesort")
    return frame.head(_TARGET_DESIGN_REPEATED_RESIDUAL_ROW_LIMIT).reset_index(drop=True)


def _resolve_target_contract_design_existing_path(path_value: str, *, base_path: Path) -> Path:
    candidate_path = Path(path_value).expanduser()
    search_paths = [candidate_path] if candidate_path.is_absolute() else [base_path / candidate_path, Path.cwd() / candidate_path]
    for search_path in search_paths:
        if search_path.exists():
            return search_path.resolve()
    raise FileNotFoundError(f"target contract design evidence path not found: {path_value}")


def _target_contract_design_source_gate_inputs(multi_slice_manifest_payload: dict[str, object]) -> dict[str, object]:
    gate_outcome = multi_slice_manifest_payload.get("gate_outcome")
    if not isinstance(gate_outcome, dict):
        raise ValueError("target contract design requires multi-slice gate_outcome evidence")
    gate_inputs = gate_outcome.get("gate_inputs") or multi_slice_manifest_payload.get("gate_inputs")
    if not isinstance(gate_inputs, dict):
        raise ValueError("target contract design requires multi-slice gate_inputs evidence")
    return gate_inputs


def _build_target_contract_design_artifacts(
    *,
    run_id: str,
    source_manifest_path: str,
    source_manifest_payload: dict[str, object],
    source_rows: pd.DataFrame,
) -> dict[str, object]:
    _require_target_contract_design_source_columns(source_rows)
    gate_outcome = source_manifest_payload.get("gate_outcome", {})
    if not isinstance(gate_outcome, dict):
        raise ValueError("target contract design requires multi-slice gate_outcome evidence")
    gate_inputs = _target_contract_design_source_gate_inputs(source_manifest_payload)
    candidate_slice_frame = _build_target_contract_design_slice_candidate_frame(source_rows)
    summary_frame = _aggregate_target_contract_design_candidate_summary(candidate_slice_frame)
    if summary_frame.empty:
        raise ValueError("target contract design produced no candidate summary rows")
    proposal_payload = _build_target_contract_design_proposal_payload(
        run_id=run_id,
        source_manifest_path=source_manifest_path,
        source_gate_outcome=gate_outcome,
        source_gate_inputs=gate_inputs,
        summary_frame=summary_frame,
    )
    best_candidate_name = str(proposal_payload["best_target_design_candidate"]["candidate_name"])
    bucket_ranking_frame = _build_target_contract_design_bucket_ranking(source_rows)
    residual_examples_frame = _build_target_contract_design_residual_examples(source_rows, best_candidate_name=best_candidate_name)
    summary_payload = {
        "run_id": run_id,
        "row_scope": "out_of_sample_validation_and_test_by_slice",
        "source_multi_slice_manifest_path": source_manifest_path,
        "source_multi_slice_run_id": source_manifest_payload.get("run_id"),
        "source_multi_slice_gate_decision": gate_outcome.get("decision"),
        "dominant_divergence_driver": gate_inputs.get("top_persistent_divergence_driver"),
        "candidate_count": int(len(summary_frame.index)),
        "candidate_rows": _json_ready_records(summary_frame),
        "slice_candidate_rows": _json_ready_records(candidate_slice_frame),
        "production_training_target_contract": DEFAULT_PROMOTION_TRAINER_TARGET_MODE,
        "production_training_target_was_replaced": False,
        "policy_remains_paused": True,
        "stage_11_was_changed": False,
        "store_facing_csv_was_changed": False,
        "proposal": proposal_payload,
    }
    return {
        "summary_payload": summary_payload,
        "summary_frame": summary_frame,
        "bucket_ranking_payload": {
            "run_id": run_id,
            "row_scope": "out_of_sample_validation_and_test_by_slice",
            "ranking_rows": _json_ready_records(bucket_ranking_frame),
            "dominant_divergence_driver": gate_inputs.get("top_persistent_divergence_driver"),
        },
        "bucket_ranking_frame": bucket_ranking_frame,
        "residual_examples_payload": {
            "run_id": run_id,
            "row_scope": "out_of_sample_validation_and_test_by_slice",
            "best_target_design_candidate": best_candidate_name,
            "top_row_limit": _TARGET_CONTRACT_DESIGN_RESIDUAL_ROW_LIMIT,
            "row_count": int(len(residual_examples_frame.index)),
            "rows": _json_ready_records(residual_examples_frame),
        },
        "residual_examples_frame": residual_examples_frame,
        "proposal_payload": proposal_payload,
    }


def _build_target_contract_three_way_artifacts(
    *,
    run_id: str,
    source_repeated_evidence_manifest_path: str,
    source_repeated_evidence_manifest_payload: dict[str, object],
    source_design_proposal_path: str,
    source_design_proposal_payload: dict[str, object],
    source_rows: pd.DataFrame,
) -> dict[str, object]:
    _require_target_contract_design_source_columns(source_rows)
    gate_outcome = source_repeated_evidence_manifest_payload.get("gate_outcome")
    if not isinstance(gate_outcome, dict):
        raise ValueError("target contract three-way comparison requires repeated-evidence gate_outcome evidence")
    source_multi_slice_manifest_path = source_repeated_evidence_manifest_payload.get("target_mode_multi_slice_manifest_path")
    if not isinstance(source_multi_slice_manifest_path, str) or not source_multi_slice_manifest_path:
        raise ValueError(
            "target contract three-way comparison requires target_mode_multi_slice_manifest_path evidence"
        )
    top_target_design_candidate = _target_contract_three_way_top_design_candidate_name(
        source_design_proposal_payload,
        context=source_design_proposal_path,
    )
    compared_contracts = _target_contract_three_way_compared_contracts(top_target_design_candidate)
    compared_contract_names = {str(contract["candidate_name"]) for contract in compared_contracts}
    contract_role_map = {
        str(contract["candidate_name"]): str(contract["contract_role"])
        for contract in compared_contracts
    }

    candidate_slice_frame = _build_target_contract_design_slice_candidate_frame(source_rows)
    candidate_slice_frame = candidate_slice_frame.loc[
        candidate_slice_frame["candidate_name"].astype(str).isin(compared_contract_names)
    ].copy()
    candidate_slice_frame["contract_role"] = candidate_slice_frame["candidate_name"].astype(str).map(contract_role_map)
    summary_frame = _aggregate_target_contract_design_candidate_summary(candidate_slice_frame)
    if summary_frame.empty:
        raise ValueError("target contract three-way comparison produced no summary rows")
    summary_frame["contract_role"] = summary_frame["candidate_name"].astype(str).map(contract_role_map)
    summary_frame = _annotate_target_contract_three_way_summary_ties(summary_frame)

    bucket_ranking_frame = _build_target_contract_design_bucket_ranking(source_rows)
    bucket_ranking_frame = bucket_ranking_frame.loc[
        bucket_ranking_frame["candidate_name"].astype(str).isin(compared_contract_names)
    ].copy()
    bucket_ranking_frame["contract_role"] = bucket_ranking_frame["candidate_name"].astype(str).map(contract_role_map)
    bucket_ranking_frame = bucket_ranking_frame.merge(
        summary_frame.loc[:, ["candidate_name", "candidate_rank", "has_metric_tie", "tied_contract_names"]],
        on="candidate_name",
        how="left",
    ).sort_values(
        ["dominant_divergence_driver", "candidate_rank", "design_priority", "candidate_name"],
        ascending=[True, True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)

    residual_examples_frame = _build_target_contract_three_way_residual_examples(
        source_rows,
        top_target_design_candidate=top_target_design_candidate,
    )
    proposal_payload = _build_target_contract_three_way_proposal_payload(
        run_id=run_id,
        source_repeated_evidence_manifest_path=source_repeated_evidence_manifest_path,
        source_multi_slice_manifest_path=source_multi_slice_manifest_path,
        source_design_proposal_path=source_design_proposal_path,
        source_repeated_evidence_gate_outcome=gate_outcome,
        summary_frame=summary_frame,
        compared_contracts=compared_contracts,
        top_target_design_candidate=top_target_design_candidate,
    )
    summary_payload = {
        "run_id": run_id,
        "row_scope": "out_of_sample_validation_and_test_by_completed_slice",
        "source_repeated_evidence_manifest_path": source_repeated_evidence_manifest_path,
        "source_multi_slice_manifest_path": source_multi_slice_manifest_path,
        "source_target_contract_design_proposal_path": source_design_proposal_path,
        "compared_contracts": compared_contracts,
        "contract_count": int(len(summary_frame.index)),
        "candidate_rows": _json_ready_records(summary_frame),
        "slice_candidate_rows": _json_ready_records(candidate_slice_frame),
        "proposal": proposal_payload,
        "current_trainer_contract_remains_live_default": True,
        "production_training_target_was_replaced": False,
        "policy_remains_paused": True,
        "stage_11_was_changed": False,
        "store_facing_csv_was_changed": False,
    }
    bucket_ranking_payload = {
        "run_id": run_id,
        "row_scope": "out_of_sample_validation_and_test_by_completed_slice",
        "compared_contracts": compared_contracts,
        "ranking_rows": _json_ready_records(bucket_ranking_frame),
    }
    residual_examples_payload = {
        "run_id": run_id,
        "row_scope": "out_of_sample_validation_and_test_by_completed_slice",
        "top_target_design_candidate": top_target_design_candidate,
        "top_row_limit": _TARGET_CONTRACT_THREE_WAY_RESIDUAL_ROW_LIMIT,
        "row_count": int(len(residual_examples_frame.index)),
        "rows": _json_ready_records(residual_examples_frame),
    }
    manifest_payload = {
        "run_id": run_id,
        "source_repeated_evidence_manifest_path": source_repeated_evidence_manifest_path,
        "source_multi_slice_manifest_path": source_multi_slice_manifest_path,
        "source_target_contract_design_proposal_path": source_design_proposal_path,
        "compared_contracts": compared_contracts,
        "best_contract_under_evidence": proposal_payload.get("best_contract_under_evidence"),
        "decision": proposal_payload.get("decision"),
        "current_trainer_contract_remains_live_default": True,
        "production_training_target_was_replaced": False,
        "policy_remains_paused": True,
        "stage_11_was_changed": False,
        "store_facing_csv_was_changed": False,
    }
    return {
        "summary_payload": summary_payload,
        "summary_frame": summary_frame,
        "bucket_ranking_payload": bucket_ranking_payload,
        "bucket_ranking_frame": bucket_ranking_frame,
        "residual_examples_payload": residual_examples_payload,
        "residual_examples_frame": residual_examples_frame,
        "proposal_payload": proposal_payload,
        "manifest_payload": manifest_payload,
    }


def _require_target_contract_design_source_columns(source_rows: pd.DataFrame) -> None:
    _require_columns(
        source_rows,
        (
            "slice_identifier",
            "child_run_id",
            "promotion_row_key",
            "store_number",
            "sku_number",
            "split_name",
            "target_contract_replay_comparable_flag",
            "both_contract_valid_flag",
            "dominant_divergence_driver",
            "stock_basis_units",
            "historical_allocated_units",
            "target_historical_allocation_units",
            "actual_units_sold",
            "realised_units_sold_promo",
            "unit_cost",
            "replay_unit_cost",
            "trainer_current_excess_units",
            "trainer_current_excess_capital",
            "historical_allocation_excess_units",
            "historical_allocation_excess_capital",
            "current_overallocation_flag",
            "historical_overallocation_flag",
        ),
        context="target contract design evidence",
    )


def _build_target_contract_design_slice_candidate_frame(source_rows: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for slice_identifier, slice_frame in source_rows.groupby("slice_identifier", dropna=False):
        for candidate_name in _TARGET_CONTRACT_DESIGN_CANDIDATE_ORDER:
            rows.append(
                _target_contract_design_slice_candidate_row(
                    candidate_name=candidate_name,
                    slice_identifier=str(slice_identifier),
                    slice_rows=slice_frame,
                )
            )
    return pd.DataFrame(rows)


def _target_contract_design_slice_candidate_row(
    *,
    candidate_name: str,
    slice_identifier: str,
    slice_rows: pd.DataFrame,
) -> dict[str, object]:
    values = _target_contract_design_candidate_values(slice_rows, candidate_name)
    comparison_mask = values["comparison_mask"]
    total_rows = int(len(slice_rows.index))
    comparable_rows = int(comparison_mask.sum())
    stock_units_error = (values["stock_basis_proxy_units"] - values["business_mistake_units"]).abs().loc[comparison_mask]
    stock_capital_error = (values["stock_basis_proxy_capital"] - values["business_mistake_capital"]).abs().loc[comparison_mask]
    candidate_units_error = (values["candidate_units"] - values["business_mistake_units"]).abs().loc[comparison_mask]
    candidate_capital_error = (values["candidate_capital"] - values["business_mistake_capital"]).abs().loc[comparison_mask]
    business_flag = values["business_mistake_flag"].loc[comparison_mask]
    current_flag = values["stock_basis_proxy_flag"].loc[comparison_mask]
    candidate_flag = values["candidate_flag"].loc[comparison_mask]
    stock_units_mae = _target_contract_design_mean(stock_units_error)
    stock_capital_mae = _target_contract_design_mean(stock_capital_error)
    candidate_units_mae = _target_contract_design_mean(candidate_units_error)
    candidate_capital_mae = _target_contract_design_mean(candidate_capital_error)
    current_flag_disagreement_rate = _target_contract_design_mean(current_flag.ne(business_flag).astype(float))
    candidate_flag_disagreement_rate = _target_contract_design_mean(candidate_flag.ne(business_flag).astype(float))
    units_improvement = _target_contract_design_difference(stock_units_mae, candidate_units_mae)
    capital_improvement = _target_contract_design_difference(stock_capital_mae, candidate_capital_mae)
    units_improvement_rate = _target_contract_design_rate(units_improvement, stock_units_mae)
    capital_improvement_rate = _target_contract_design_rate(capital_improvement, stock_capital_mae)
    flag_reduction = _target_contract_design_difference(current_flag_disagreement_rate, candidate_flag_disagreement_rate)
    flag_reduction_rate = _target_contract_design_rate(flag_reduction, current_flag_disagreement_rate)
    uses_stock_basis_proxy = candidate_name == _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE
    return {
        "candidate_name": candidate_name,
        "candidate_description": _target_contract_design_candidate_description(candidate_name),
        "slice_identifier": slice_identifier,
        "row_count": total_rows,
        "comparable_rows": comparable_rows,
        "coverage_rate": comparable_rows / total_rows if total_rows else 0.0,
        "exclusion_rate": 1.0 - (comparable_rows / total_rows) if total_rows else 1.0,
        "business_mistake_units_mean": _target_contract_design_mean(values["business_mistake_units"].loc[comparison_mask]),
        "business_mistake_units_median": _target_contract_design_median(values["business_mistake_units"].loc[comparison_mask]),
        "candidate_target_value_mean": _target_contract_design_mean(values["candidate_value"].loc[comparison_mask]),
        "candidate_target_value_median": _target_contract_design_median(values["candidate_value"].loc[comparison_mask]),
        "stock_basis_units_mae_against_business_mistake": stock_units_mae,
        "stock_basis_capital_mae_against_business_mistake": stock_capital_mae,
        "candidate_units_mae_against_business_mistake": candidate_units_mae,
        "candidate_units_median_abs_error_against_business_mistake": _target_contract_design_median(candidate_units_error),
        "candidate_capital_mae_against_business_mistake": candidate_capital_mae,
        "candidate_capital_median_abs_error_against_business_mistake": _target_contract_design_median(candidate_capital_error),
        "candidate_units_mae_improvement_vs_stock_basis": units_improvement,
        "candidate_units_mae_improvement_rate_vs_stock_basis": units_improvement_rate,
        "candidate_capital_mae_improvement_vs_stock_basis": capital_improvement,
        "candidate_capital_mae_improvement_rate_vs_stock_basis": capital_improvement_rate,
        "current_stock_basis_flag_disagreement_rate": current_flag_disagreement_rate,
        "candidate_flag_disagreement_rate": candidate_flag_disagreement_rate,
        "flag_disagreement_reduction_rate_vs_stock_basis": flag_reduction_rate,
        "reduces_dependence_on_stock_basis_proxy_mismatch": bool(
            not uses_stock_basis_proxy
            and units_improvement_rate is not None
            and units_improvement_rate > 0.0
        ),
        "cleaner_promotion_decision_boundary": bool(
            candidate_flag_disagreement_rate is not None
            and current_flag_disagreement_rate is not None
            and candidate_flag_disagreement_rate < current_flag_disagreement_rate
        ),
        "uses_stock_basis_proxy": uses_stock_basis_proxy,
        "dominant_stock_basis_row_count": int(
            slice_rows["dominant_divergence_driver"].astype(str).eq(_TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS).sum()
        ),
        "dominant_stock_basis_row_share": float(
            slice_rows["dominant_divergence_driver"].astype(str).eq(_TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS).mean()
        ) if total_rows else 0.0,
        "design_priority": _TARGET_CONTRACT_DESIGN_PROPOSAL_PRIORITY[candidate_name],
        "cap_value_units": values.get("cap_value_units"),
    }


def _target_contract_design_candidate_values(rows: pd.DataFrame, candidate_name: str) -> dict[str, object]:
    historical_allocated_units = pd.to_numeric(rows["historical_allocated_units"], errors="coerce")
    realised_units = pd.to_numeric(rows["realised_units_sold_promo"], errors="coerce")
    replay_unit_cost = pd.to_numeric(rows["replay_unit_cost"], errors="coerce")
    business_units = pd.to_numeric(rows["historical_allocation_excess_units"], errors="coerce")
    business_capital = pd.to_numeric(rows["historical_allocation_excess_capital"], errors="coerce")
    stock_basis_units = pd.to_numeric(rows["trainer_current_excess_units"], errors="coerce")
    stock_basis_capital = pd.to_numeric(rows["trainer_current_excess_capital"], errors="coerce")
    stock_basis_flag = pd.to_numeric(rows["current_overallocation_flag"], errors="coerce")
    business_flag = pd.to_numeric(rows["historical_overallocation_flag"], errors="coerce")
    base_valid_mask = (
        pd.to_numeric(rows["both_contract_valid_flag"], errors="coerce").eq(1.0)
        & business_units.notna()
        & business_capital.notna()
        & business_flag.notna()
        & replay_unit_cost.gt(0.0)
    )
    cap_value_units: float | None = None
    if candidate_name == _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE:
        candidate_value = stock_basis_units
        candidate_units = stock_basis_units
        candidate_capital = stock_basis_capital
        candidate_flag = stock_basis_flag
    elif candidate_name == "historical_allocated_units":
        candidate_value = historical_allocated_units
        candidate_units = historical_allocated_units
        candidate_capital = candidate_units * replay_unit_cost
        candidate_flag = _target_contract_design_flag_from_units(candidate_units)
    elif candidate_name == "realised_promo_units":
        candidate_value = realised_units
        candidate_units = realised_units
        candidate_capital = candidate_units * replay_unit_cost
        candidate_flag = _target_contract_design_flag_from_units(candidate_units)
    elif candidate_name == "historical_excess_units":
        candidate_value = business_units
        candidate_units = business_units
        candidate_capital = business_capital
        candidate_flag = _target_contract_design_flag_from_units(candidate_units)
    elif candidate_name == "historical_excess_capital":
        candidate_value = business_capital
        candidate_units = business_capital / replay_unit_cost.where(replay_unit_cost.gt(0.0))
        candidate_capital = business_capital
        candidate_flag = _target_contract_design_flag_from_units(candidate_capital)
    elif candidate_name == "capped_historical_excess_units":
        valid_business_units = business_units.loc[base_valid_mask].dropna()
        cap_value_units = float(valid_business_units.quantile(0.95)) if not valid_business_units.empty else None
        candidate_units = business_units.clip(upper=cap_value_units) if cap_value_units is not None else business_units.where(False)
        candidate_value = candidate_units
        candidate_capital = candidate_units * replay_unit_cost
        candidate_flag = _target_contract_design_flag_from_units(candidate_units)
    elif candidate_name == "sell_through_aligned_allocation_error":
        signed_error = historical_allocated_units - realised_units
        candidate_units = signed_error.clip(lower=0.0)
        candidate_value = candidate_units
        candidate_capital = candidate_units * replay_unit_cost
        candidate_flag = _target_contract_design_flag_from_units(signed_error)
    elif candidate_name == "cost_weighted_allocation_error":
        candidate_units = business_capital / replay_unit_cost.where(replay_unit_cost.gt(0.0))
        candidate_value = business_capital
        candidate_capital = business_capital
        candidate_flag = _target_contract_design_flag_from_units(candidate_capital)
    else:
        raise ValueError(f"Unsupported target contract design candidate {candidate_name!r}")

    comparison_mask = (
        base_valid_mask
        & stock_basis_units.notna()
        & stock_basis_capital.notna()
        & stock_basis_flag.notna()
        & candidate_units.notna()
        & candidate_capital.notna()
        & candidate_flag.notna()
    )
    return {
        "business_mistake_units": business_units,
        "business_mistake_capital": business_capital,
        "business_mistake_flag": business_flag.ge(0.5),
        "stock_basis_proxy_units": stock_basis_units,
        "stock_basis_proxy_capital": stock_basis_capital,
        "stock_basis_proxy_flag": stock_basis_flag.ge(0.5),
        "candidate_value": candidate_value,
        "candidate_units": candidate_units,
        "candidate_capital": candidate_capital,
        "candidate_flag": candidate_flag.ge(0.5),
        "comparison_mask": comparison_mask,
        "cap_value_units": cap_value_units,
    }


def _target_contract_design_flag_from_units(units: pd.Series) -> pd.Series:
    flag = pd.Series(np.nan, index=units.index, dtype="float64")
    valid_mask = units.notna()
    flag.loc[valid_mask] = units.loc[valid_mask].gt(0.0).astype(float)
    return flag


def _target_contract_design_candidate_description(candidate_name: str) -> str:
    descriptions = {
        _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE: "Current trainer stock-basis excess proxy used as the live baseline comparator.",
        "historical_allocated_units": "Raw historical allocation quantity before realised promo sales are considered.",
        "realised_promo_units": "Realised promotion-period unit sales as a decomposition component.",
        "historical_excess_units": "Historical allocated units minus realised promo units, clipped at zero.",
        "historical_excess_capital": "Historical excess units multiplied by replay unit cost.",
        "capped_historical_excess_units": "Historical excess units capped at the per-slice 95th percentile to test outlier sensitivity.",
        "sell_through_aligned_allocation_error": "Allocation error expressed as unsold allocated units after realised promo sell-through.",
        "cost_weighted_allocation_error": "Allocation error weighted by replay unit cost to align with excess capital.",
    }
    return descriptions[candidate_name]


def _aggregate_target_contract_design_candidate_summary(candidate_slice_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for candidate_name, candidate_frame in candidate_slice_frame.groupby("candidate_name", dropna=False):
        comparable_rows = pd.to_numeric(candidate_frame["comparable_rows"], errors="coerce")
        coverage = pd.to_numeric(candidate_frame["coverage_rate"], errors="coerce")
        exclusion = pd.to_numeric(candidate_frame["exclusion_rate"], errors="coerce")
        units_improvement_rate = pd.to_numeric(candidate_frame["candidate_units_mae_improvement_rate_vs_stock_basis"], errors="coerce")
        capital_improvement_rate = pd.to_numeric(candidate_frame["candidate_capital_mae_improvement_rate_vs_stock_basis"], errors="coerce")
        cleaner_boundary = candidate_frame["cleaner_promotion_decision_boundary"].astype(bool)
        reduces_dependency = candidate_frame["reduces_dependence_on_stock_basis_proxy_mismatch"].astype(bool)
        positive_improvement = units_improvement_rate.gt(0.0)
        rows.append(
            {
                "candidate_name": str(candidate_name),
                "candidate_description": str(candidate_frame["candidate_description"].iloc[0]),
                "slice_count": int(candidate_frame["slice_identifier"].nunique()),
                "total_comparable_rows": int(comparable_rows.sum()),
                "minimum_comparable_rows_per_slice": int(comparable_rows.min()) if not comparable_rows.empty else 0,
                "minimum_coverage_rate": float(coverage.min()) if not coverage.empty else 0.0,
                "maximum_exclusion_rate": float(exclusion.max()) if not exclusion.empty else 1.0,
                "candidate_units_mae_mean": _target_contract_design_mean(candidate_frame["candidate_units_mae_against_business_mistake"]),
                "candidate_units_mae_median": _target_contract_design_median(candidate_frame["candidate_units_mae_against_business_mistake"]),
                "candidate_capital_mae_mean": _target_contract_design_mean(candidate_frame["candidate_capital_mae_against_business_mistake"]),
                "candidate_capital_mae_median": _target_contract_design_median(candidate_frame["candidate_capital_mae_against_business_mistake"]),
                "stock_basis_units_mae_mean": _target_contract_design_mean(candidate_frame["stock_basis_units_mae_against_business_mistake"]),
                "stock_basis_capital_mae_mean": _target_contract_design_mean(candidate_frame["stock_basis_capital_mae_against_business_mistake"]),
                "candidate_units_mae_improvement_rate_mean": _target_contract_design_mean(units_improvement_rate),
                "candidate_units_mae_improvement_rate_median": _target_contract_design_median(units_improvement_rate),
                "candidate_capital_mae_improvement_rate_mean": _target_contract_design_mean(capital_improvement_rate),
                "candidate_flag_disagreement_rate_mean": _target_contract_design_mean(candidate_frame["candidate_flag_disagreement_rate"]),
                "stock_basis_flag_disagreement_rate_mean": _target_contract_design_mean(candidate_frame["current_stock_basis_flag_disagreement_rate"]),
                "positive_improvement_slice_count": int(positive_improvement.sum()),
                "positive_improvement_slice_share": float(positive_improvement.mean()) if not positive_improvement.empty else 0.0,
                "relative_improvement_coefficient_of_variation": _target_contract_design_cv(units_improvement_rate.loc[positive_improvement]),
                "clean_boundary_slice_share": float(cleaner_boundary.mean()) if not cleaner_boundary.empty else 0.0,
                "stock_basis_dependency_reduced_slice_share": float(reduces_dependency.mean()) if not reduces_dependency.empty else 0.0,
                "reduces_dependence_on_stock_basis_proxy_mismatch": bool(reduces_dependency.all()) if not reduces_dependency.empty else False,
                "creates_cleaner_promotion_decision_boundary": bool(cleaner_boundary.all()) if not cleaner_boundary.empty else False,
                "uses_stock_basis_proxy": bool(candidate_frame["uses_stock_basis_proxy"].astype(bool).iloc[0]),
                "design_priority": int(candidate_frame["design_priority"].iloc[0]),
            }
        )
    summary_frame = pd.DataFrame(rows)
    return _rank_target_contract_design_candidates(summary_frame)


def _rank_target_contract_design_candidates(summary_frame: pd.DataFrame) -> pd.DataFrame:
    ranking = summary_frame.copy()
    ranking["proposal_rankable"] = ~ranking["uses_stock_basis_proxy"].astype(bool)
    ranking["_units_mae_sort"] = pd.to_numeric(ranking["candidate_units_mae_mean"], errors="coerce").fillna(np.inf)
    ranking["_capital_mae_sort"] = pd.to_numeric(ranking["candidate_capital_mae_mean"], errors="coerce").fillna(np.inf)
    ranking["_flag_sort"] = pd.to_numeric(ranking["candidate_flag_disagreement_rate_mean"], errors="coerce").fillna(np.inf)
    ranking = ranking.sort_values(
        ["proposal_rankable", "_units_mae_sort", "_capital_mae_sort", "_flag_sort", "design_priority", "candidate_name"],
        ascending=[False, True, True, True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    ranking["candidate_rank"] = range(1, len(ranking.index) + 1)
    return ranking.drop(columns=["_units_mae_sort", "_capital_mae_sort", "_flag_sort"])


def _build_target_contract_design_bucket_ranking(source_rows: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for candidate_name in _TARGET_CONTRACT_DESIGN_CANDIDATE_ORDER:
        values = _target_contract_design_candidate_values(source_rows, candidate_name)
        comparison_mask = values["comparison_mask"]
        candidate_units_error = (values["candidate_units"] - values["business_mistake_units"]).abs()
        candidate_capital_error = (values["candidate_capital"] - values["business_mistake_capital"]).abs()
        stock_units_error = (values["stock_basis_proxy_units"] - values["business_mistake_units"]).abs()
        stock_capital_error = (values["stock_basis_proxy_capital"] - values["business_mistake_capital"]).abs()
        for bucket_name, bucket_frame in source_rows.groupby("dominant_divergence_driver", dropna=False):
            bucket_mask = source_rows.index.isin(bucket_frame.index) & comparison_mask
            row_count = int(len(bucket_frame.index))
            comparable_rows = int(bucket_mask.sum())
            stock_units_mae = _target_contract_design_mean(stock_units_error.loc[bucket_mask])
            candidate_units_mae = _target_contract_design_mean(candidate_units_error.loc[bucket_mask])
            stock_capital_mae = _target_contract_design_mean(stock_capital_error.loc[bucket_mask])
            candidate_capital_mae = _target_contract_design_mean(candidate_capital_error.loc[bucket_mask])
            rows.append(
                {
                    "candidate_name": candidate_name,
                    "candidate_description": _target_contract_design_candidate_description(candidate_name),
                    "dominant_divergence_driver": str(bucket_name),
                    "row_count": row_count,
                    "comparable_rows": comparable_rows,
                    "candidate_units_mae_against_business_mistake": candidate_units_mae,
                    "stock_basis_units_mae_against_business_mistake": stock_units_mae,
                    "candidate_units_mae_improvement_rate_vs_stock_basis": _target_contract_design_rate(
                        _target_contract_design_difference(stock_units_mae, candidate_units_mae),
                        stock_units_mae,
                    ),
                    "candidate_capital_mae_against_business_mistake": candidate_capital_mae,
                    "stock_basis_capital_mae_against_business_mistake": stock_capital_mae,
                    "candidate_capital_mae_improvement_rate_vs_stock_basis": _target_contract_design_rate(
                        _target_contract_design_difference(stock_capital_mae, candidate_capital_mae),
                        stock_capital_mae,
                    ),
                    "uses_stock_basis_proxy": candidate_name == _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE,
                    "design_priority": _TARGET_CONTRACT_DESIGN_PROPOSAL_PRIORITY[candidate_name],
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["_driver_sort"] = frame["dominant_divergence_driver"].astype(str).ne(_TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS)
    frame["_improvement_sort"] = pd.to_numeric(frame["candidate_units_mae_improvement_rate_vs_stock_basis"], errors="coerce").fillna(-np.inf)
    return frame.sort_values(
        ["_driver_sort", "_improvement_sort", "comparable_rows", "design_priority", "candidate_name"],
        ascending=[True, False, False, True, True],
        kind="mergesort",
    ).drop(columns=["_driver_sort", "_improvement_sort"]).reset_index(drop=True)


def _build_target_contract_design_residual_examples(
    source_rows: pd.DataFrame,
    *,
    best_candidate_name: str,
) -> pd.DataFrame:
    values = _target_contract_design_candidate_values(source_rows, best_candidate_name)
    comparison_mask = (
        values["comparison_mask"]
        & source_rows["dominant_divergence_driver"].astype(str).eq(_TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS)
    )
    if not comparison_mask.any():
        return pd.DataFrame()
    frame = source_rows.loc[comparison_mask].copy()
    frame["best_target_design_candidate"] = best_candidate_name
    frame["business_mistake_units"] = values["business_mistake_units"].loc[comparison_mask]
    frame["business_mistake_capital"] = values["business_mistake_capital"].loc[comparison_mask]
    frame["best_candidate_units"] = values["candidate_units"].loc[comparison_mask]
    frame["best_candidate_capital"] = values["candidate_capital"].loc[comparison_mask]
    frame["stock_basis_proxy_units"] = values["stock_basis_proxy_units"].loc[comparison_mask]
    frame["stock_basis_proxy_capital"] = values["stock_basis_proxy_capital"].loc[comparison_mask]
    frame["stock_basis_units_error_abs"] = (frame["stock_basis_proxy_units"] - frame["business_mistake_units"]).abs()
    frame["stock_basis_capital_error_abs"] = (frame["stock_basis_proxy_capital"] - frame["business_mistake_capital"]).abs()
    frame["best_candidate_units_error_abs"] = (frame["best_candidate_units"] - frame["business_mistake_units"]).abs()
    frame["best_candidate_capital_error_abs"] = (frame["best_candidate_capital"] - frame["business_mistake_capital"]).abs()
    output_columns = [
        "slice_identifier",
        "child_run_id",
        "promotion_row_key",
        "store_number",
        "sku_number",
        "split_name",
        "dominant_divergence_driver",
        "best_target_design_candidate",
        "stock_basis_units",
        "historical_allocated_units",
        "realised_units_sold_promo",
        "replay_unit_cost",
        "business_mistake_units",
        "business_mistake_capital",
        "stock_basis_proxy_units",
        "stock_basis_proxy_capital",
        "best_candidate_units",
        "best_candidate_capital",
        "stock_basis_units_error_abs",
        "stock_basis_capital_error_abs",
        "best_candidate_units_error_abs",
        "best_candidate_capital_error_abs",
        "source_row_diagnostics_path",
    ]
    return frame.sort_values(
        ["stock_basis_capital_error_abs", "stock_basis_units_error_abs"],
        ascending=[False, False],
        kind="mergesort",
    ).loc[:, output_columns].head(_TARGET_CONTRACT_DESIGN_RESIDUAL_ROW_LIMIT).reset_index(drop=True)


def _build_target_contract_design_proposal_payload(
    *,
    run_id: str,
    source_manifest_path: str,
    source_gate_outcome: dict[str, object],
    source_gate_inputs: dict[str, object],
    summary_frame: pd.DataFrame,
) -> dict[str, object]:
    rankable = summary_frame.loc[~summary_frame["uses_stock_basis_proxy"].astype(bool)].copy()
    if rankable.empty:
        raise ValueError("target contract design proposal requires at least one non-stock-basis candidate")
    best_row = rankable.iloc[0].to_dict()
    blockers: list[str] = []
    if source_gate_outcome.get("decision") == "diagnostics_only":
        blockers.append("source_multi_slice_shadow_gate_is_diagnostics_only")
    if int(best_row.get("slice_count", 0)) < _TARGET_CONTRACT_DESIGN_MIN_SLICE_COUNT:
        blockers.append("insufficient_slice_count")
    if int(best_row.get("minimum_comparable_rows_per_slice", 0)) < _TARGET_CONTRACT_DESIGN_MIN_COMPARABLE_ROWS_PER_SLICE:
        blockers.append("insufficient_comparable_rows_per_slice")
    if float(best_row.get("minimum_coverage_rate", 0.0)) < _TARGET_CONTRACT_DESIGN_MIN_COVERAGE_RATE:
        blockers.append("candidate_coverage_below_threshold")
    if float(best_row.get("maximum_exclusion_rate", 1.0)) > _TARGET_CONTRACT_DESIGN_MAX_EXCLUSION_RATE:
        blockers.append("candidate_exclusion_rate_above_threshold")
    if float(best_row.get("positive_improvement_slice_share", 0.0)) < _TARGET_CONTRACT_DESIGN_MIN_POSITIVE_IMPROVEMENT_SHARE:
        blockers.append("candidate_does_not_reduce_stock_basis_error_on_enough_slices")
    if float(best_row.get("clean_boundary_slice_share", 0.0)) < _TARGET_CONTRACT_DESIGN_MIN_CLEAN_BOUNDARY_SHARE:
        blockers.append("candidate_boundary_not_cleaner_on_enough_slices")
    improvement_cv = best_row.get("relative_improvement_coefficient_of_variation")
    if improvement_cv is None or float(improvement_cv) > _TARGET_CONTRACT_DESIGN_MAX_RELATIVE_IMPROVEMENT_CV:
        blockers.append("candidate_improvement_not_stable")
    if not bool(best_row.get("reduces_dependence_on_stock_basis_proxy_mismatch", False)):
        blockers.append("candidate_still_depends_on_stock_basis_proxy")

    should_shadow = not blockers
    decision = "candidate_for_shadow_training" if should_shadow else "diagnostics_only"
    return {
        "run_id": run_id,
        "row_scope": "out_of_sample_validation_and_test_by_slice",
        "source_multi_slice_manifest_path": source_manifest_path,
        "source_multi_slice_gate_decision": source_gate_outcome.get("decision"),
        "dominant_divergence_driver": source_gate_inputs.get("top_persistent_divergence_driver"),
        "best_target_design_candidate": {
            key: _json_ready_value(value)
            for key, value in best_row.items()
            if not str(key).startswith("_")
        },
        "decision": decision,
        "should_remain_diagnostics_only": not should_shadow,
        "should_become_candidate_for_shadow_training": should_shadow,
        "should_become_candidate_for_primary_training": False,
        "primary_promotion_allowed_in_this_pass": False,
        "primary_promotion_blockers": ["target_design_pass_cannot_promote_primary"],
        "shadow_promotion_blockers": blockers,
        "promotion_criteria": {
            "minimum_slice_count": _TARGET_CONTRACT_DESIGN_MIN_SLICE_COUNT,
            "minimum_comparable_rows_per_slice": _TARGET_CONTRACT_DESIGN_MIN_COMPARABLE_ROWS_PER_SLICE,
            "minimum_coverage_rate": _TARGET_CONTRACT_DESIGN_MIN_COVERAGE_RATE,
            "maximum_exclusion_rate": _TARGET_CONTRACT_DESIGN_MAX_EXCLUSION_RATE,
            "minimum_positive_improvement_slice_share": _TARGET_CONTRACT_DESIGN_MIN_POSITIVE_IMPROVEMENT_SHARE,
            "minimum_clean_boundary_slice_share": _TARGET_CONTRACT_DESIGN_MIN_CLEAN_BOUNDARY_SHARE,
            "maximum_relative_improvement_coefficient_of_variation": _TARGET_CONTRACT_DESIGN_MAX_RELATIVE_IMPROVEMENT_CV,
        },
        "current_trainer_contract_remains_live_default": True,
        "production_training_target_was_replaced": False,
        "policy_remains_paused": True,
        "policy_rules_were_changed": False,
        "stage_11_was_changed": False,
        "store_facing_csv_was_changed": False,
        "explanation": (
            "The design candidate is clean enough for shadow training, but primary promotion is disallowed in this target-design pass."
            if should_shadow else
            "The design candidate remains diagnostics-only because governed evidence is not yet sufficient for a shadow-training promotion."
        ),
    }


def _target_contract_three_way_top_design_candidate_name(
    proposal_payload: dict[str, object],
    *,
    context: str,
) -> str:
    best_candidate = proposal_payload.get("best_target_design_candidate")
    if not isinstance(best_candidate, dict):
        raise ValueError(
            "target contract three-way comparison requires best_target_design_candidate evidence: "
            f"{context}"
        )
    candidate_name = best_candidate.get("candidate_name")
    if not isinstance(candidate_name, str) or not candidate_name:
        raise ValueError(
            "target contract three-way comparison requires best_target_design_candidate.candidate_name evidence: "
            f"{context}"
        )
    if candidate_name not in _TARGET_CONTRACT_DESIGN_CANDIDATE_ORDER:
        raise ValueError(
            "target contract three-way comparison received an unsupported target-design candidate: "
            f"{candidate_name!r} from {context}"
        )
    return candidate_name


def _target_contract_three_way_compared_contracts(
    top_target_design_candidate: str,
) -> list[dict[str, object]]:
    compared_contracts = [
        {
            "contract_role": "current_live_trainer_contract",
            "candidate_name": _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE,
            "candidate_description": _target_contract_design_candidate_description(
                _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE
            ),
        },
        {
            "contract_role": "historical_allocation_candidate",
            "candidate_name": _TARGET_CONTRACT_THREE_WAY_HISTORICAL_CANDIDATE,
            "candidate_description": _target_contract_design_candidate_description(
                _TARGET_CONTRACT_THREE_WAY_HISTORICAL_CANDIDATE
            ),
        },
        {
            "contract_role": "top_target_design_candidate",
            "candidate_name": top_target_design_candidate,
            "candidate_description": _target_contract_design_candidate_description(top_target_design_candidate),
        },
    ]
    candidate_names = [str(contract["candidate_name"]) for contract in compared_contracts]
    if len(set(candidate_names)) != len(candidate_names):
        raise ValueError(
            "target contract three-way comparison requires three distinct contract candidates, got: "
            f"{candidate_names}"
        )
    return compared_contracts


def _annotate_target_contract_three_way_summary_ties(summary_frame: pd.DataFrame) -> pd.DataFrame:
    if summary_frame.empty:
        return summary_frame

    def _metric_key(row: pd.Series) -> tuple[float | None, ...]:
        values: list[float | None] = []
        for column_name in (
            "candidate_units_mae_mean",
            "candidate_capital_mae_mean",
            "candidate_flag_disagreement_rate_mean",
        ):
            numeric_value = pd.to_numeric(pd.Series([row.get(column_name)]), errors="coerce").iloc[0]
            values.append(None if pd.isna(numeric_value) else round(float(numeric_value), 12))
        return tuple(values)

    key_to_names: dict[tuple[float | None, ...], list[str]] = {}
    name_to_key: dict[str, tuple[float | None, ...]] = {}
    for _, row in summary_frame.iterrows():
        candidate_name = str(row["candidate_name"])
        metric_key = _metric_key(row)
        name_to_key[candidate_name] = metric_key
        key_to_names.setdefault(metric_key, []).append(candidate_name)

    annotated = summary_frame.copy()
    has_metric_tie: list[bool] = []
    tied_contract_names: list[str] = []
    tied_contract_count: list[int] = []
    for _, row in annotated.iterrows():
        candidate_name = str(row["candidate_name"])
        tied_names = [
            name for name in key_to_names[name_to_key[candidate_name]]
            if name != candidate_name
        ]
        has_metric_tie.append(bool(tied_names))
        tied_contract_names.append("|".join(tied_names))
        tied_contract_count.append(len(tied_names) + 1 if tied_names else 1)
    annotated["has_metric_tie"] = has_metric_tie
    annotated["tied_contract_names"] = tied_contract_names
    annotated["tied_contract_count"] = tied_contract_count
    return annotated


def _build_target_contract_three_way_residual_examples(
    source_rows: pd.DataFrame,
    *,
    top_target_design_candidate: str,
) -> pd.DataFrame:
    current_values = _target_contract_design_candidate_values(source_rows, _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE)
    historical_values = _target_contract_design_candidate_values(source_rows, _TARGET_CONTRACT_THREE_WAY_HISTORICAL_CANDIDATE)
    design_values = _target_contract_design_candidate_values(source_rows, top_target_design_candidate)
    comparison_mask = (
        current_values["comparison_mask"]
        & historical_values["comparison_mask"]
        & design_values["comparison_mask"]
        & source_rows["dominant_divergence_driver"].astype(str).eq(_TARGET_CONTRACT_DIVERGENCE_DRIVER_STOCK_BASIS)
    )
    if not comparison_mask.any():
        return pd.DataFrame()
    frame = source_rows.loc[comparison_mask].copy()
    frame["top_target_design_candidate"] = top_target_design_candidate
    frame["business_mistake_units"] = design_values["business_mistake_units"].loc[comparison_mask]
    frame["business_mistake_capital"] = design_values["business_mistake_capital"].loc[comparison_mask]
    frame["current_live_trainer_contract_units"] = current_values["candidate_units"].loc[comparison_mask]
    frame["current_live_trainer_contract_capital"] = current_values["candidate_capital"].loc[comparison_mask]
    frame["historical_allocation_candidate_units"] = historical_values["candidate_units"].loc[comparison_mask]
    frame["historical_allocation_candidate_capital"] = historical_values["candidate_capital"].loc[comparison_mask]
    frame["top_target_design_candidate_units"] = design_values["candidate_units"].loc[comparison_mask]
    frame["top_target_design_candidate_capital"] = design_values["candidate_capital"].loc[comparison_mask]
    frame["current_live_trainer_contract_units_error_abs"] = (
        frame["current_live_trainer_contract_units"] - frame["business_mistake_units"]
    ).abs()
    frame["current_live_trainer_contract_capital_error_abs"] = (
        frame["current_live_trainer_contract_capital"] - frame["business_mistake_capital"]
    ).abs()
    frame["historical_allocation_candidate_units_error_abs"] = (
        frame["historical_allocation_candidate_units"] - frame["business_mistake_units"]
    ).abs()
    frame["historical_allocation_candidate_capital_error_abs"] = (
        frame["historical_allocation_candidate_capital"] - frame["business_mistake_capital"]
    ).abs()
    frame["top_target_design_candidate_units_error_abs"] = (
        frame["top_target_design_candidate_units"] - frame["business_mistake_units"]
    ).abs()
    frame["top_target_design_candidate_capital_error_abs"] = (
        frame["top_target_design_candidate_capital"] - frame["business_mistake_capital"]
    ).abs()
    frame["top_target_design_candidate_capital_error_improvement_vs_current"] = (
        frame["current_live_trainer_contract_capital_error_abs"]
        - frame["top_target_design_candidate_capital_error_abs"]
    )
    output_columns = [
        "slice_identifier",
        "child_run_id",
        "promotion_row_key",
        "store_number",
        "sku_number",
        "split_name",
        "dominant_divergence_driver",
        "top_target_design_candidate",
        "business_mistake_units",
        "business_mistake_capital",
        "current_live_trainer_contract_units",
        "current_live_trainer_contract_capital",
        "current_live_trainer_contract_units_error_abs",
        "current_live_trainer_contract_capital_error_abs",
        "historical_allocation_candidate_units",
        "historical_allocation_candidate_capital",
        "historical_allocation_candidate_units_error_abs",
        "historical_allocation_candidate_capital_error_abs",
        "top_target_design_candidate_units",
        "top_target_design_candidate_capital",
        "top_target_design_candidate_units_error_abs",
        "top_target_design_candidate_capital_error_abs",
        "top_target_design_candidate_capital_error_improvement_vs_current",
        "source_row_diagnostics_path",
    ]
    return frame.sort_values(
        [
            "current_live_trainer_contract_capital_error_abs",
            "top_target_design_candidate_capital_error_improvement_vs_current",
            "current_live_trainer_contract_units_error_abs",
        ],
        ascending=[False, False, False],
        kind="mergesort",
    ).loc[:, output_columns].head(_TARGET_CONTRACT_THREE_WAY_RESIDUAL_ROW_LIMIT).reset_index(drop=True)


def _compare_target_contract_three_way_summary_rows(
    left_row: dict[str, object],
    right_row: dict[str, object],
) -> str:
    for column_name in (
        "candidate_units_mae_mean",
        "candidate_capital_mae_mean",
        "candidate_flag_disagreement_rate_mean",
    ):
        left_value = pd.to_numeric(pd.Series([left_row.get(column_name)]), errors="coerce").iloc[0]
        right_value = pd.to_numeric(pd.Series([right_row.get(column_name)]), errors="coerce").iloc[0]
        if pd.isna(left_value) and pd.isna(right_value):
            continue
        if np.isclose(left_value, right_value, equal_nan=True):
            continue
        return "better" if float(left_value) < float(right_value) else "worse"
    return "tied"


def _dedupe_string_list(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def _build_target_contract_three_way_proposal_payload(
    *,
    run_id: str,
    source_repeated_evidence_manifest_path: str,
    source_multi_slice_manifest_path: str,
    source_design_proposal_path: str,
    source_repeated_evidence_gate_outcome: dict[str, object],
    summary_frame: pd.DataFrame,
    compared_contracts: Sequence[dict[str, object]],
    top_target_design_candidate: str,
) -> dict[str, object]:
    summary_rows = {
        str(row["candidate_name"]): row
        for row in summary_frame.to_dict(orient="records")
    }
    current_row = summary_rows[_TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE]
    historical_row = summary_rows[_TARGET_CONTRACT_THREE_WAY_HISTORICAL_CANDIDATE]
    design_row = summary_rows[top_target_design_candidate]
    best_row = summary_frame.iloc[0].to_dict()
    relative_to_current = _compare_target_contract_three_way_summary_rows(design_row, current_row)
    repeated_evidence_decision = str(source_repeated_evidence_gate_outcome.get("decision") or "")
    repeated_evidence_shadow_blockers = [
        str(value)
        for value in source_repeated_evidence_gate_outcome.get("shadow_promotion_blockers", [])
        if isinstance(value, str) and value
    ]
    if repeated_evidence_decision == "candidate_for_shadow_training":
        if relative_to_current != "better":
            raise ValueError(
                "target contract three-way comparison source repeated-evidence gate promotes the top design candidate "
                "to shadow-only candidacy, but the three-way comparison does not show it outperforming the current contract"
            )
        top_design_candidate_assessment = "strong_enough_for_shadow_only_candidacy"
        decision = "candidate_for_shadow_training"
        shadow_promotion_blockers: list[str] = []
    elif relative_to_current == "better":
        top_design_candidate_assessment = "better_than_current_but_not_promotable"
        decision = "diagnostics_only"
        shadow_promotion_blockers = repeated_evidence_shadow_blockers
    elif relative_to_current == "tied":
        top_design_candidate_assessment = "ties_current"
        decision = "diagnostics_only"
        shadow_promotion_blockers = _dedupe_string_list(
            ["top_design_candidate_ties_current", *repeated_evidence_shadow_blockers]
        )
    else:
        top_design_candidate_assessment = "worse_than_current"
        decision = "diagnostics_only"
        shadow_promotion_blockers = _dedupe_string_list(
            ["top_design_candidate_worse_than_current", *repeated_evidence_shadow_blockers]
        )
    explanation = {
        "strong_enough_for_shadow_only_candidacy": (
            f"{top_target_design_candidate} outperforms the current live trainer contract on the governed completed-slice evidence, "
            "and the repeated-evidence gate already supports shadow-only candidacy; primary remains blocked."
        ),
        "better_than_current_but_not_promotable": (
            f"{top_target_design_candidate} outperforms the current live trainer contract on the governed completed-slice evidence, "
            "but repeated-evidence governance still keeps it diagnostics-only."
        ),
        "ties_current": (
            f"{top_target_design_candidate} ties the current live trainer contract on the governed completed-slice evidence, "
            "so it remains diagnostics-only."
        ),
        "worse_than_current": (
            f"{top_target_design_candidate} underperforms the current live trainer contract on the governed completed-slice evidence, "
            "so it remains diagnostics-only."
        ),
    }[top_design_candidate_assessment]
    return {
        "run_id": run_id,
        "row_scope": "out_of_sample_validation_and_test_by_completed_slice",
        "source_repeated_evidence_manifest_path": source_repeated_evidence_manifest_path,
        "source_multi_slice_manifest_path": source_multi_slice_manifest_path,
        "source_target_contract_design_proposal_path": source_design_proposal_path,
        "source_repeated_evidence_gate_decision": repeated_evidence_decision,
        "compared_contracts": list(compared_contracts),
        "best_contract_under_evidence": {
            key: _json_ready_value(value)
            for key, value in best_row.items()
            if not str(key).startswith("_")
        },
        "current_live_trainer_contract": {
            key: _json_ready_value(value)
            for key, value in current_row.items()
            if not str(key).startswith("_")
        },
        "historical_allocation_candidate": {
            key: _json_ready_value(value)
            for key, value in historical_row.items()
            if not str(key).startswith("_")
        },
        "top_target_design_candidate": {
            key: _json_ready_value(value)
            for key, value in design_row.items()
            if not str(key).startswith("_")
        },
        "top_design_candidate_relative_to_current": relative_to_current,
        "top_design_candidate_assessment": top_design_candidate_assessment,
        "decision": decision,
        "should_remain_diagnostics_only": decision == "diagnostics_only",
        "should_become_candidate_for_shadow_training": decision == "candidate_for_shadow_training",
        "should_become_candidate_for_primary_training": False,
        "primary_promotion_allowed_in_this_pass": False,
        "primary_promotion_blockers": ["target_contract_three_way_pass_cannot_promote_primary"],
        "shadow_promotion_blockers": shadow_promotion_blockers,
        "promotion_criteria": source_repeated_evidence_gate_outcome.get("promotion_criteria", {}),
        "current_trainer_contract_remains_live_default": True,
        "production_training_target_was_replaced": False,
        "policy_remains_paused": True,
        "policy_rules_were_changed": False,
        "stage_11_was_changed": False,
        "store_facing_csv_was_changed": False,
        "explanation": explanation,
    }


def _load_promotion_readiness_three_way_source(
    *,
    run_id: str,
    source_repeated_evidence_manifest_path: Path,
    source_repeated_evidence_manifest_payload: dict[str, object],
    source_multi_slice_manifest_path: Path,
    source_multi_slice_manifest_payload: dict[str, object],
    source_design_proposal_path: Path,
    source_design_proposal_payload: dict[str, object],
    target_contract_three_way_manifest_path: str | Path | None,
    target_contract_three_way_summary_path: str | Path | None,
    target_contract_three_way_proposal_path: str | Path | None,
    target_contract_three_way_residual_examples_path: str | Path | None,
) -> dict[str, object]:
    resolved_manifest_path = _resolve_optional_promotion_readiness_existing_path(
        target_contract_three_way_manifest_path,
        base_path=source_repeated_evidence_manifest_path.parent,
        context="promotion readiness target_contract_three_way_manifest_path",
    )
    resolved_summary_path = _resolve_optional_promotion_readiness_existing_path(
        target_contract_three_way_summary_path,
        base_path=source_repeated_evidence_manifest_path.parent,
        context="promotion readiness target_contract_three_way_summary_path",
    )
    resolved_proposal_path = _resolve_optional_promotion_readiness_existing_path(
        target_contract_three_way_proposal_path,
        base_path=source_repeated_evidence_manifest_path.parent,
        context="promotion readiness target_contract_three_way_proposal_path",
    )
    resolved_residual_examples_path = _resolve_optional_promotion_readiness_existing_path(
        target_contract_three_way_residual_examples_path,
        base_path=source_repeated_evidence_manifest_path.parent,
        context="promotion readiness target_contract_three_way_residual_examples_path",
    )

    if not any(
        path is not None
        for path in (
            resolved_manifest_path,
            resolved_summary_path,
            resolved_proposal_path,
            resolved_residual_examples_path,
        )
    ):
        source_rows = _load_target_contract_design_source_rows(
            source_multi_slice_manifest_payload,
            source_manifest_path=source_multi_slice_manifest_path,
        )
        artifacts = _build_target_contract_three_way_artifacts(
            run_id=run_id,
            source_repeated_evidence_manifest_path=str(source_repeated_evidence_manifest_path),
            source_repeated_evidence_manifest_payload=source_repeated_evidence_manifest_payload,
            source_design_proposal_path=str(source_design_proposal_path),
            source_design_proposal_payload=source_design_proposal_payload,
            source_rows=source_rows,
        )
        return {
            "source_target_contract_three_way_manifest_path": None,
            "source_target_contract_three_way_proposal_path": None,
            "source_target_contract_three_way_residual_examples_path": None,
            "proposal_payload": artifacts["proposal_payload"],
            "residual_examples_payload": artifacts["residual_examples_payload"],
            "used_existing_three_way_evidence": False,
        }

    manifest_payload: dict[str, object] = {}
    if resolved_manifest_path is not None:
        manifest_payload = read_json(resolved_manifest_path)
        if resolved_summary_path is None:
            resolved_summary_path = _resolve_optional_promotion_readiness_existing_path(
                manifest_payload.get("summary_json_path"),
                base_path=resolved_manifest_path.parent,
                context=f"{resolved_manifest_path} summary_json_path",
            )
        if resolved_proposal_path is None:
            resolved_proposal_path = _resolve_optional_promotion_readiness_existing_path(
                manifest_payload.get("proposal_json_path"),
                base_path=resolved_manifest_path.parent,
                context=f"{resolved_manifest_path} proposal_json_path",
            )
        if resolved_residual_examples_path is None:
            resolved_residual_examples_path = _resolve_optional_promotion_readiness_existing_path(
                manifest_payload.get("residual_examples_json_path"),
                base_path=resolved_manifest_path.parent,
                context=f"{resolved_manifest_path} residual_examples_json_path",
            )

    summary_payload = read_json(resolved_summary_path) if resolved_summary_path is not None else {}
    proposal_payload = read_json(resolved_proposal_path) if resolved_proposal_path is not None else {}
    if not proposal_payload:
        summary_proposal = summary_payload.get("proposal")
        if isinstance(summary_proposal, dict):
            proposal_payload = dict(summary_proposal)
    if not proposal_payload:
        raise ValueError(
            "promotion readiness requires target-contract three-way proposal evidence when explicit three-way sources are supplied"
        )
    residual_examples_payload = (
        read_json(resolved_residual_examples_path)
        if resolved_residual_examples_path is not None else
        {}
    )

    _validate_promotion_readiness_three_way_source_alignment(
        proposal_payload=proposal_payload,
        summary_payload=summary_payload,
        source_repeated_evidence_manifest_path=source_repeated_evidence_manifest_path,
        source_design_proposal_path=source_design_proposal_path,
        source_design_proposal_payload=source_design_proposal_payload,
    )
    return {
        "source_target_contract_three_way_manifest_path": (
            None if resolved_manifest_path is None else str(resolved_manifest_path)
        ),
        "source_target_contract_three_way_proposal_path": (
            None if resolved_proposal_path is None else str(resolved_proposal_path)
        ),
        "source_target_contract_three_way_residual_examples_path": (
            None if resolved_residual_examples_path is None else str(resolved_residual_examples_path)
        ),
        "proposal_payload": proposal_payload,
        "residual_examples_payload": residual_examples_payload,
        "used_existing_three_way_evidence": True,
    }


def _build_promotion_readiness_artifacts(
    *,
    run_id: str,
    source_repeated_evidence_manifest_path: str,
    source_repeated_evidence_manifest_payload: dict[str, object],
    source_target_mode_multi_slice_manifest_path: str,
    source_target_mode_multi_slice_manifest_payload: dict[str, object],
    source_target_contract_design_proposal_path: str,
    source_target_contract_design_proposal_payload: dict[str, object],
    source_target_contract_three_way_manifest_path: str | None,
    source_target_contract_three_way_proposal_path: str | None,
    source_target_contract_three_way_proposal_payload: dict[str, object],
    source_target_contract_three_way_residual_examples_path: str | None,
    source_target_contract_three_way_residual_examples_payload: dict[str, object],
    used_existing_three_way_evidence: bool,
) -> dict[str, object]:
    repeated_gate_outcome = source_repeated_evidence_manifest_payload.get("gate_outcome")
    if not isinstance(repeated_gate_outcome, dict):
        raise ValueError("promotion readiness requires repeated-evidence gate_outcome evidence")
    stability_gate = source_target_mode_multi_slice_manifest_payload.get("stability_gate")
    if not isinstance(stability_gate, dict):
        raise ValueError("promotion readiness requires target-mode multi-slice stability_gate evidence")
    compared_contracts = source_target_contract_three_way_proposal_payload.get("compared_contracts")
    if not isinstance(compared_contracts, list) or not compared_contracts:
        raise ValueError("promotion readiness requires compared_contracts evidence from the three-way proposal")
    best_contract_under_evidence = source_target_contract_three_way_proposal_payload.get("best_contract_under_evidence")
    historical_contract = source_target_contract_three_way_proposal_payload.get("historical_allocation_candidate")
    top_design_contract = source_target_contract_three_way_proposal_payload.get("top_target_design_candidate")
    current_live_contract = source_target_contract_three_way_proposal_payload.get("current_live_trainer_contract")
    if not isinstance(best_contract_under_evidence, dict):
        raise ValueError("promotion readiness requires best_contract_under_evidence evidence")
    if not isinstance(historical_contract, dict):
        raise ValueError("promotion readiness requires historical_allocation_candidate evidence")
    if not isinstance(top_design_contract, dict):
        raise ValueError("promotion readiness requires top_target_design_candidate evidence")
    if not isinstance(current_live_contract, dict):
        raise ValueError("promotion readiness requires current_live_trainer_contract evidence")

    design_candidate_name = _target_contract_three_way_top_design_candidate_name(
        source_target_contract_design_proposal_payload,
        context=source_target_contract_design_proposal_path,
    )
    proposal_design_candidate_name = str(top_design_contract.get("candidate_name") or "")
    if proposal_design_candidate_name != design_candidate_name:
        raise ValueError(
            "promotion readiness design proposal and three-way proposal disagree on the top design candidate: "
            f"{source_target_contract_design_proposal_path}"
        )

    historical_candidate_name = _TARGET_CONTRACT_THREE_WAY_HISTORICAL_CANDIDATE
    current_best_candidate_name = str(best_contract_under_evidence.get("candidate_name") or "")
    historical_shadow_ready = str(stability_gate.get("decision") or "") in {
        "candidate_for_shadow_training",
        "candidate_for_primary_training",
    }
    design_shadow_ready = (
        str(source_target_contract_three_way_proposal_payload.get("decision") or "") == "candidate_for_shadow_training"
        and str(source_target_contract_three_way_proposal_payload.get("top_design_candidate_assessment") or "")
        == "strong_enough_for_shadow_only_candidacy"
    )

    blocker_records = [
        *_build_promotion_readiness_historical_blocker_records(
            gate_payload=stability_gate,
            candidate_name=historical_candidate_name,
            contract_role=str(historical_contract.get("contract_role") or "historical_allocation_candidate"),
        ),
        *_build_promotion_readiness_design_blocker_records(
            gate_payload=repeated_gate_outcome,
            candidate_name=design_candidate_name,
            contract_role=str(top_design_contract.get("contract_role") or "top_target_design_candidate"),
        ),
        *_build_promotion_readiness_governance_blocker_records(
            proposal_payload=source_target_contract_three_way_proposal_payload,
            current_best_candidate_name=current_best_candidate_name,
            historical_candidate_name=historical_candidate_name,
            design_candidate_name=design_candidate_name,
            live_default_candidate_name=str(current_live_contract.get("candidate_name") or _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE),
        ),
    ]
    historical_candidate_blockers = _sort_promotion_readiness_blocker_records(
        [record for record in blocker_records if record["candidate_name"] == historical_candidate_name],
        current_best_candidate_name=current_best_candidate_name,
    )
    design_candidate_blockers = _sort_promotion_readiness_blocker_records(
        [record for record in blocker_records if record["candidate_name"] == design_candidate_name],
        current_best_candidate_name=current_best_candidate_name,
    )
    blocker_ranking_rows = _aggregate_promotion_readiness_blockers(
        blocker_records,
        current_best_candidate_name=current_best_candidate_name,
    )

    scoreboard_frame = pd.DataFrame(
        [
            _build_promotion_readiness_candidate_scoreboard_row(
                candidate_payload=historical_contract,
                shadow_ready=historical_shadow_ready,
                source_decision=str(stability_gate.get("decision") or ""),
                source_assessment=str(stability_gate.get("explanation") or ""),
                sorted_blockers=historical_candidate_blockers,
                current_best_candidate_name=current_best_candidate_name,
            ),
            _build_promotion_readiness_candidate_scoreboard_row(
                candidate_payload=top_design_contract,
                shadow_ready=design_shadow_ready,
                source_decision=str(source_target_contract_three_way_proposal_payload.get("decision") or ""),
                source_assessment=str(
                    source_target_contract_three_way_proposal_payload.get("top_design_candidate_assessment") or ""
                ),
                sorted_blockers=design_candidate_blockers,
                current_best_candidate_name=current_best_candidate_name,
            ),
        ]
    )
    blocker_ranking_payload = {
        "run_id": run_id,
        "row_scope": "shadow_promotion_readiness_scoreboard",
        "source_repeated_evidence_manifest_path": source_repeated_evidence_manifest_path,
        "source_target_mode_multi_slice_manifest_path": source_target_mode_multi_slice_manifest_path,
        "source_target_contract_design_proposal_path": source_target_contract_design_proposal_path,
        "source_target_contract_three_way_manifest_path": source_target_contract_three_way_manifest_path,
        "source_target_contract_three_way_proposal_path": source_target_contract_three_way_proposal_path,
        "used_existing_three_way_evidence": used_existing_three_way_evidence,
        "current_best_candidate_name": current_best_candidate_name,
        "dominant_blocker_family": (
            blocker_ranking_rows[0]["blocker_family"] if blocker_ranking_rows else None
        ),
        "dominant_blocker": blocker_ranking_rows[0]["blocker_name"] if blocker_ranking_rows else None,
        "ranked_blockers": blocker_ranking_rows,
    }
    residual_examples_payload = _build_promotion_readiness_residual_examples_payload(
        run_id=run_id,
        blocker_ranking_rows=blocker_ranking_rows,
        historical_candidate_name=historical_candidate_name,
        design_candidate_name=design_candidate_name,
        source_target_mode_multi_slice_manifest_path=Path(source_target_mode_multi_slice_manifest_path),
        source_repeated_evidence_manifest_path=Path(source_repeated_evidence_manifest_path),
        source_target_contract_three_way_residual_examples_path=(
            None
            if source_target_contract_three_way_residual_examples_path is None else
            Path(source_target_contract_three_way_residual_examples_path)
        ),
        source_target_contract_three_way_residual_examples_payload=source_target_contract_three_way_residual_examples_payload,
    )
    decision_packet = _build_promotion_readiness_decision_packet(
        compared_contracts=compared_contracts,
        current_live_contract=current_live_contract,
        best_contract_under_evidence=best_contract_under_evidence,
        stability_gate=stability_gate,
        repeated_gate_outcome=repeated_gate_outcome,
        three_way_proposal_payload=source_target_contract_three_way_proposal_payload,
        blocker_ranking_rows=blocker_ranking_rows,
        historical_candidate_shadow_ready=historical_shadow_ready,
        design_candidate_shadow_ready=design_shadow_ready,
        current_best_candidate_name=current_best_candidate_name,
    )
    scoreboard_payload = {
        "run_id": run_id,
        "row_scope": "shadow_promotion_readiness_scoreboard",
        "source_repeated_evidence_manifest_path": source_repeated_evidence_manifest_path,
        "source_target_mode_multi_slice_manifest_path": source_target_mode_multi_slice_manifest_path,
        "source_target_contract_design_proposal_path": source_target_contract_design_proposal_path,
        "source_target_contract_three_way_manifest_path": source_target_contract_three_way_manifest_path,
        "source_target_contract_three_way_proposal_path": source_target_contract_three_way_proposal_path,
        "used_existing_three_way_evidence": used_existing_three_way_evidence,
        "compared_candidates": list(compared_contracts),
        "candidate_rows": _json_ready_records(scoreboard_frame),
        "decision_packet": decision_packet,
    }
    return {
        "scoreboard_frame": scoreboard_frame,
        "scoreboard_payload": scoreboard_payload,
        "blocker_ranking_payload": blocker_ranking_payload,
        "residual_examples_payload": residual_examples_payload,
        "decision_packet": decision_packet,
    }


def _load_optional_weak_slice_repair_json_payload(
    path_value: str | Path | None,
    *,
    context_label: str,
) -> dict[str, object]:
    if path_value is None:
        return {}
    payload_path = Path(path_value).expanduser().resolve()
    if not payload_path.exists():
        raise FileNotFoundError(f"{context_label} not found: {payload_path}")
    payload = read_json(payload_path)
    if not isinstance(payload, dict):
        raise ValueError(f"{context_label} must be a JSON object: {payload_path}")
    return payload


def _load_weak_slice_repair_multi_slice_source(
    source_target_mode_multi_slice_manifest_path: str | Path,
) -> dict[str, object]:
    manifest_path = Path(source_target_mode_multi_slice_manifest_path).expanduser().resolve()
    if not manifest_path.exists():
        raise FileNotFoundError(f"weak-slice repair source multi-slice manifest not found: {manifest_path}")
    manifest_payload = read_json(manifest_path)
    if not isinstance(manifest_payload, dict):
        raise ValueError(f"weak-slice repair multi-slice manifest must be a JSON object: {manifest_path}")
    summary_path_value = manifest_payload.get("summary_json_path")
    if not isinstance(summary_path_value, str) or not summary_path_value:
        raise ValueError(
            "weak-slice repair requires summary_json_path evidence from the target-mode multi-slice manifest: "
            f"{manifest_path}"
        )
    summary_path = _resolve_target_contract_design_existing_path(
        summary_path_value,
        base_path=manifest_path.parent,
    )
    summary_payload = read_json(summary_path)
    if not isinstance(summary_payload, dict):
        raise ValueError(f"weak-slice repair multi-slice summary must be a JSON object: {summary_path}")
    residual_examples_path: Path | None = None
    residual_examples_payload: dict[str, object] = {}
    residual_examples_value = manifest_payload.get("residual_examples_json_path")
    if isinstance(residual_examples_value, str) and residual_examples_value:
        residual_examples_path = _resolve_target_contract_design_existing_path(
            residual_examples_value,
            base_path=manifest_path.parent,
        )
        residual_examples_payload = read_json(residual_examples_path)
        if not isinstance(residual_examples_payload, dict):
            raise ValueError(
                "weak-slice repair multi-slice residual examples must be a JSON object: "
                f"{residual_examples_path}"
            )
    stability_gate = manifest_payload.get("stability_gate")
    if not isinstance(stability_gate, dict):
        gate_outcome = manifest_payload.get("gate_outcome")
        if isinstance(gate_outcome, dict):
            stability_gate = gate_outcome
    if not isinstance(stability_gate, dict):
        stability_gate = summary_payload.get("stability_gate")
    if not isinstance(stability_gate, dict):
        stability_gate_path_value = manifest_payload.get("stability_gate_json_path")
        if isinstance(stability_gate_path_value, str) and stability_gate_path_value:
            stability_gate_path = _resolve_target_contract_design_existing_path(
                stability_gate_path_value,
                base_path=manifest_path.parent,
            )
            stability_gate = read_json(stability_gate_path)
    if not isinstance(stability_gate, dict):
        raise ValueError(
            "weak-slice repair requires stability_gate evidence from the target-mode multi-slice manifest: "
            f"{manifest_path}"
        )
    normalized_manifest_payload = dict(manifest_payload)
    normalized_manifest_payload["stability_gate"] = stability_gate
    return {
        "manifest_path": manifest_path,
        "manifest_payload": normalized_manifest_payload,
        "summary_path": summary_path,
        "summary_payload": summary_payload,
        "residual_examples_path": residual_examples_path,
        "residual_examples_payload": residual_examples_payload,
    }


def _build_weak_slice_repair_artifacts(
    *,
    run_id: str,
    source_target_mode_multi_slice_manifest_path: str,
    source_target_mode_multi_slice_manifest_payload: dict[str, object],
    source_target_mode_multi_slice_summary_path: str,
    source_target_mode_multi_slice_summary_payload: dict[str, object],
    source_target_mode_multi_slice_residual_examples_path: str | None,
    source_target_mode_multi_slice_residual_examples_payload: dict[str, object],
    source_promotion_readiness_runtime_manifest_path: str | None,
    source_promotion_readiness_decision_packet_path: str | None,
    source_promotion_readiness_decision_packet_payload: dict[str, object],
    source_promotion_readiness_blocker_ranking_path: str | None,
    source_promotion_readiness_blocker_ranking_payload: dict[str, object],
    source_target_contract_three_way_runtime_manifest_path: str | None,
    source_target_contract_three_way_proposal_path: str | None,
    source_target_contract_three_way_proposal_payload: dict[str, object],
) -> dict[str, object]:
    summary_slice_rows = source_target_mode_multi_slice_summary_payload.get("slice_rows")
    if not isinstance(summary_slice_rows, list) or not summary_slice_rows:
        raise ValueError("weak-slice repair requires slice_rows evidence from the target-mode multi-slice summary")
    stability_gate = source_target_mode_multi_slice_manifest_payload.get("stability_gate")
    if not isinstance(stability_gate, dict):
        raise ValueError("weak-slice repair requires target-mode multi-slice stability_gate evidence")
    promotion_criteria = stability_gate.get("promotion_criteria")
    gate_inputs = stability_gate.get("gate_inputs")
    if not isinstance(promotion_criteria, dict) or not isinstance(gate_inputs, dict):
        raise ValueError("weak-slice repair requires promotion_criteria and gate_inputs from the multi-slice gate")

    blocker_ranking_rows = source_promotion_readiness_blocker_ranking_payload.get("ranked_blockers")
    readiness_ranked_blockers = []
    if isinstance(blocker_ranking_rows, list):
        readiness_ranked_blockers = [
            str(record.get("blocker_name") or "")
            for record in blocker_ranking_rows
            if isinstance(record, dict) and str(record.get("blocker_name") or "")
        ]
    current_global_dominant_blocker = str(
        source_promotion_readiness_decision_packet_payload.get("dominant_blocker")
        or (readiness_ranked_blockers[0] if readiness_ranked_blockers else "")
    )
    current_global_dominant_blocker_family = str(
        source_promotion_readiness_decision_packet_payload.get("dominant_blocker_family")
        or _WEAK_SLICE_REPAIR_FAMILY_BY_BLOCKER.get(current_global_dominant_blocker, "")
    )
    slice_run_artifact_paths = source_target_mode_multi_slice_summary_payload.get("slice_run_artifact_paths")
    slice_run_manifest_paths: dict[str, str] = {}
    if isinstance(slice_run_artifact_paths, list):
        for record in slice_run_artifact_paths:
            if not isinstance(record, dict):
                continue
            slice_identifier = str(record.get("slice_identifier") or "")
            manifest_path = str(record.get("manifest_path") or "")
            if slice_identifier and manifest_path:
                slice_run_manifest_paths[slice_identifier] = manifest_path

    summary_rows: list[dict[str, object]] = []
    plan_rows: list[dict[str, object]] = []
    for slice_payload in summary_slice_rows:
        if not isinstance(slice_payload, dict):
            continue
        slice_context = _build_weak_slice_repair_slice_context(
            slice_payload=slice_payload,
            promotion_criteria=promotion_criteria,
            gate_inputs=gate_inputs,
            source_summary_base_path=Path(source_target_mode_multi_slice_summary_path).parent,
            slice_run_manifest_path_value=slice_run_manifest_paths.get(str(slice_payload.get("slice_identifier") or "")),
            current_global_dominant_blocker=current_global_dominant_blocker,
            readiness_ranked_blockers=readiness_ranked_blockers,
        )
        summary_rows.append(slice_context["summary_row"])
        plan_rows.extend(
            _build_weak_slice_repair_options(
                slice_context=slice_context,
                current_global_dominant_blocker=current_global_dominant_blocker,
                readiness_ranked_blockers=readiness_ranked_blockers,
            )
        )

    if not current_global_dominant_blocker:
        current_global_dominant_blocker = _infer_weak_slice_global_blocker(summary_rows)
        current_global_dominant_blocker_family = _WEAK_SLICE_REPAIR_FAMILY_BY_BLOCKER.get(
            current_global_dominant_blocker,
            current_global_dominant_blocker_family,
        )
    if not readiness_ranked_blockers:
        readiness_ranked_blockers = [
            blocker_name
            for blocker_name in _WEAK_SLICE_PRIMARY_BLOCKER_PRIORITY
            if blocker_name in {str(row.get("weak_slice_blocker") or "") for row in summary_rows if row.get("weak_slice")}
        ]

    weak_rows = [row for row in summary_rows if bool(row.get("weak_slice"))]
    weak_rows.sort(
        key=lambda row: (
            _weak_slice_blocker_priority(str(row.get("weak_slice_blocker") or "")),
            -_weak_slice_float(row.get("comparable_row_shortfall")),
            -_weak_slice_float(row.get("exclusion_gap")),
            -_weak_slice_float(row.get("coverage_gap")),
            -_weak_slice_float(row.get("current_candidate_capital_mae_improvement") <= 0.0),
            str(row.get("slice_identifier") or ""),
        )
    )
    weak_slice_rank_by_identifier: dict[str, int] = {}
    for index, row in enumerate(weak_rows, start=1):
        weak_slice_rank_by_identifier[str(row.get("slice_identifier") or "")] = index
        row["weak_slice_rank"] = index
    for row in summary_rows:
        if str(row.get("slice_identifier") or "") not in weak_slice_rank_by_identifier:
            row["weak_slice_rank"] = None
    for row in plan_rows:
        row["weak_slice_rank"] = weak_slice_rank_by_identifier.get(str(row.get("slice_identifier") or ""))
        row["option_score"] = _build_weak_slice_repair_option_score(
            option_row=row,
            current_global_dominant_blocker=current_global_dominant_blocker,
        )
    plan_rows.sort(
        key=lambda row: (
            -(float(row.get("option_score") or 0.0)),
            int(row.get("weak_slice_rank") or 10**6),
            _weak_slice_float(row.get("work_units")),
            str(row.get("slice_identifier") or ""),
            str(row.get("repair_category") or ""),
        )
    )
    for index, row in enumerate(plan_rows, start=1):
        row["repair_option_rank"] = index
    best_repair_option = plan_rows[0] if plan_rows else None
    for row in plan_rows:
        row["recommended"] = bool(best_repair_option is row)
        row["recommended_for_slice"] = bool(
            row.get("repair_option_rank")
            == min(
                option.get("repair_option_rank")
                for option in plan_rows
                if option.get("slice_identifier") == row.get("slice_identifier")
            )
        )

    summary_columns = [
        "weak_slice_rank",
        "slice_identifier",
        "weak_slice",
        "weakness_driver",
        "current_comparable_rows",
        "required_comparable_rows",
        "comparable_row_shortfall",
        "current_exclusion_rate",
        "allowed_exclusion_rate",
        "exclusion_gap",
        "current_coverage_rate",
        "required_coverage_rate",
        "coverage_gap",
        "excluded_row_count",
        "current_candidate_capital_mae_improvement",
        "current_candidate_shadow_model_outperformed_current_shadow_model",
        "current_slice_gate_decision",
        "current_evidence_outcome",
        "weak_slice_blocker_family",
        "weak_slice_blocker",
        "row_count_repair_needed",
        "exclusion_rate_repair_needed",
        "evidence_quality_repair_needed",
        "source_chain_governance_repair_needed",
        "source_chain_attribution_complete",
        "exclusion_reason_counts",
        "target_contract_summary_json_path",
        "target_contract_promotion_gate_json_path",
        "slice_run_manifest_path",
    ]
    plan_columns = [
        "repair_option_rank",
        "weak_slice_rank",
        "slice_identifier",
        "repair_category",
        "blocker_family",
        "blocker_name",
        "current_value",
        "threshold_value",
        "delta_to_threshold",
        "work_units",
        "work_unit_type",
        "projected_comparable_rows",
        "projected_exclusion_rate",
        "projected_coverage_rate",
        "clears_blockers",
        "clears_slice_primary_blocker",
        "clears_global_dominant_blocker",
        "projected_next_blocker",
        "expected_readiness_gain",
        "minimum_next_evidence_required",
        "note",
        "option_score",
        "recommended",
        "recommended_for_slice",
    ]
    summary_frame = pd.DataFrame(summary_rows, columns=summary_columns)
    plan_frame = pd.DataFrame(plan_rows, columns=plan_columns)
    summary_frame.sort_values(
        by=["weak_slice", "weak_slice_rank", "slice_identifier"],
        ascending=[False, True, True],
        inplace=True,
        na_position="last",
    )
    if not plan_frame.empty:
        plan_frame.sort_values(
            by=["repair_option_rank"],
            ascending=[True],
            inplace=True,
            na_position="last",
        )

    weakest_slice = weak_rows[0] if weak_rows else None
    residual_examples_payload = _build_weak_slice_repair_residual_examples_payload(
        run_id=run_id,
        weakest_slice=weakest_slice,
        source_target_mode_multi_slice_summary_path=source_target_mode_multi_slice_summary_path,
        source_target_mode_multi_slice_manifest_path=source_target_mode_multi_slice_manifest_path,
        source_target_mode_multi_slice_residual_examples_path=source_target_mode_multi_slice_residual_examples_path,
        source_target_mode_multi_slice_residual_examples_payload=source_target_mode_multi_slice_residual_examples_payload,
    )

    best_repair_option_payload = _weak_slice_plan_row_to_payload(best_repair_option)
    decision_packet = {
        "run_id": run_id,
        "row_scope": "completed_slice_repair_planning",
        "source_target_mode_multi_slice_manifest_path": source_target_mode_multi_slice_manifest_path,
        "source_target_mode_multi_slice_summary_path": source_target_mode_multi_slice_summary_path,
        "source_promotion_readiness_runtime_manifest_path": source_promotion_readiness_runtime_manifest_path,
        "source_promotion_readiness_decision_packet_path": source_promotion_readiness_decision_packet_path,
        "source_promotion_readiness_blocker_ranking_path": source_promotion_readiness_blocker_ranking_path,
        "source_target_contract_three_way_runtime_manifest_path": source_target_contract_three_way_runtime_manifest_path,
        "source_target_contract_three_way_proposal_path": source_target_contract_three_way_proposal_path,
        "current_dominant_readiness_blocker_family": current_global_dominant_blocker_family or None,
        "current_dominant_readiness_blocker": current_global_dominant_blocker or None,
        "weak_slice_count": int(len(weak_rows)),
        "weakest_slice_identifier": None if weakest_slice is None else weakest_slice.get("slice_identifier"),
        "weakest_slice_blocker_family": None if weakest_slice is None else weakest_slice.get("weak_slice_blocker_family"),
        "weakest_slice_blocker": None if weakest_slice is None else weakest_slice.get("weak_slice_blocker"),
        "current_comparable_rows": None if weakest_slice is None else weakest_slice.get("current_comparable_rows"),
        "required_comparable_rows": None if weakest_slice is None else weakest_slice.get("required_comparable_rows"),
        "comparable_row_shortfall": None if weakest_slice is None else weakest_slice.get("comparable_row_shortfall"),
        "current_exclusion_rate": None if weakest_slice is None else weakest_slice.get("current_exclusion_rate"),
        "allowed_exclusion_rate": None if weakest_slice is None else weakest_slice.get("allowed_exclusion_rate"),
        "exclusion_gap": None if weakest_slice is None else weakest_slice.get("exclusion_gap"),
        "best_repair_option": best_repair_option_payload,
        "minimum_next_evidence_required": (
            None
            if best_repair_option is None
            else {
                "summary": best_repair_option.get("minimum_next_evidence_required"),
                "work_units": best_repair_option.get("work_units"),
                "work_unit_type": best_repair_option.get("work_unit_type"),
                "delta_to_threshold": best_repair_option.get("delta_to_threshold"),
            }
        ),
        "expected_readiness_gain": (
            None
            if best_repair_option is None
            else {
                "summary": best_repair_option.get("expected_readiness_gain"),
                "clears_blockers": _split_pipe_values(best_repair_option.get("clears_blockers")),
                "projected_next_blocker": best_repair_option.get("projected_next_blocker"),
            }
        ),
        "ranked_repair_options": [_weak_slice_plan_row_to_payload(row) for row in plan_rows],
        "diagnostics_only": True,
        "live_default_unchanged": True,
        "policy_remains_paused": True,
        "store_facing_csv_changed": False,
        "publish_tree_created": False,
    }
    summary_payload = {
        "run_id": run_id,
        "row_scope": "completed_slice_repair_planning",
        "source_target_mode_multi_slice_manifest_path": source_target_mode_multi_slice_manifest_path,
        "source_target_mode_multi_slice_summary_path": source_target_mode_multi_slice_summary_path,
        "source_target_mode_multi_slice_residual_examples_path": source_target_mode_multi_slice_residual_examples_path,
        "source_promotion_readiness_runtime_manifest_path": source_promotion_readiness_runtime_manifest_path,
        "source_target_contract_three_way_runtime_manifest_path": source_target_contract_three_way_runtime_manifest_path,
        "current_dominant_readiness_blocker_family": current_global_dominant_blocker_family or None,
        "current_dominant_readiness_blocker": current_global_dominant_blocker or None,
        "weak_slice_count": int(len(weak_rows)),
        "weakest_slice_identifier": None if weakest_slice is None else weakest_slice.get("slice_identifier"),
        "slice_rows": _json_ready_records(summary_frame),
        "decision_packet": decision_packet,
    }
    plan_payload = {
        "run_id": run_id,
        "row_scope": "completed_slice_repair_planning",
        "source_target_mode_multi_slice_manifest_path": source_target_mode_multi_slice_manifest_path,
        "source_target_mode_multi_slice_summary_path": source_target_mode_multi_slice_summary_path,
        "source_promotion_readiness_runtime_manifest_path": source_promotion_readiness_runtime_manifest_path,
        "source_target_contract_three_way_runtime_manifest_path": source_target_contract_three_way_runtime_manifest_path,
        "current_dominant_readiness_blocker_family": current_global_dominant_blocker_family or None,
        "current_dominant_readiness_blocker": current_global_dominant_blocker or None,
        "weak_slice_count": int(len(weak_rows)),
        "repair_option_count": int(len(plan_rows)),
        "best_repair_option": best_repair_option_payload,
        "ranked_repair_options": [_weak_slice_plan_row_to_payload(row) for row in plan_rows],
        "repair_options_by_category": {
            category: [
                _weak_slice_plan_row_to_payload(row)
                for row in plan_rows
                if row.get("repair_category") == category
            ]
            for category in (
                "row_count_repairs",
                "exclusion_rate_repairs",
                "evidence_quality_repairs",
                "source_chain_governance_repairs",
            )
        },
    }
    return {
        "summary_frame": summary_frame,
        "summary_payload": summary_payload,
        "plan_frame": plan_frame,
        "plan_payload": plan_payload,
        "residual_examples_payload": residual_examples_payload,
        "decision_packet": decision_packet,
    }


def _build_weak_slice_repair_slice_context(
    *,
    slice_payload: dict[str, object],
    promotion_criteria: dict[str, object],
    gate_inputs: dict[str, object],
    source_summary_base_path: Path,
    slice_run_manifest_path_value: str | None,
    current_global_dominant_blocker: str,
    readiness_ranked_blockers: Sequence[str],
) -> dict[str, object]:
    slice_identifier = str(slice_payload.get("slice_identifier") or "")
    required_comparable_rows = _weak_slice_int(promotion_criteria.get("minimum_comparable_rows_per_slice"))
    current_comparable_rows = _weak_slice_int(slice_payload.get("comparable_rows"))
    evaluation_row_count = max(
        _weak_slice_int(slice_payload.get("evaluation_row_count")),
        current_comparable_rows,
    )
    excluded_row_count = max(evaluation_row_count - current_comparable_rows, 0)
    current_exclusion_rate = _weak_slice_float(
        slice_payload.get("historical_exclusion_rate"),
        default=(excluded_row_count / evaluation_row_count if evaluation_row_count else 0.0),
    )
    allowed_exclusion_rate = _weak_slice_float(
        promotion_criteria.get("maximum_historical_exclusion_rate"),
        default=0.0,
    )
    current_coverage_rate = _weak_slice_float(
        slice_payload.get("coverage_rate"),
        default=(current_comparable_rows / evaluation_row_count if evaluation_row_count else 0.0),
    )
    required_coverage_rate = _weak_slice_float(
        slice_payload.get("minimum_valid_comparable_coverage"),
        default=0.95,
    )
    target_contract_summary_path = _resolve_optional_weak_slice_repair_path(
        slice_payload.get("target_contract_summary_json_path"),
        base_path=source_summary_base_path,
    )
    target_contract_summary_payload = _load_optional_weak_slice_repair_json_payload(
        target_contract_summary_path,
        context_label="weak-slice target contract summary",
    ) if target_contract_summary_path is not None else {}
    target_contract_gate_path = _resolve_optional_weak_slice_repair_path(
        slice_payload.get("target_contract_promotion_gate_json_path"),
        base_path=source_summary_base_path,
    )
    target_contract_gate_payload = _load_optional_weak_slice_repair_json_payload(
        target_contract_gate_path,
        context_label="weak-slice target contract promotion gate",
    ) if target_contract_gate_path is not None else {}
    if target_contract_gate_payload:
        gate_criteria = target_contract_gate_payload.get("promotion_criteria")
        if isinstance(gate_criteria, dict):
            required_coverage_rate = _weak_slice_float(
                gate_criteria.get("minimum_valid_comparable_coverage"),
                default=required_coverage_rate,
            )

    candidate_improvement = _weak_slice_float(slice_payload.get("candidate_capital_mae_improvement"))
    candidate_outperformed = _weak_slice_bool(
        slice_payload.get("candidate_shadow_model_outperformed_current_shadow_model"),
    )
    slice_gate_decision = str(slice_payload.get("slice_gate_decision") or "")
    evidence_outcome = str(slice_payload.get("evidence_outcome") or "")
    comparable_row_shortfall = max(required_comparable_rows - current_comparable_rows, 0)
    exclusion_gap = max(current_exclusion_rate - allowed_exclusion_rate, 0.0)
    coverage_gap = max(required_coverage_rate - current_coverage_rate, 0.0)
    row_count_blocker = comparable_row_shortfall > 0
    exclusion_blocker = exclusion_gap > 0.0
    coverage_blocker = coverage_gap > 0.0
    evidence_quality_blocker = (candidate_improvement <= 0.0) or (not candidate_outperformed)

    run_artifacts = _load_weak_slice_run_artifacts(slice_run_manifest_path_value)
    exclusion_reason_counts = _normalize_weak_slice_reason_counts(
        run_artifacts.get("replay_exclusion_reason_counts") or target_contract_summary_payload.get("excluded_historical_contract_reason_counts")
    )
    source_chain_attribution_complete = excluded_row_count == 0 or any(
        key != _POLICY_REPLAY_EXCLUSION_REASON_ELIGIBLE and value > 0
        for key, value in exclusion_reason_counts.items()
    )
    source_chain_governance_repair_needed = excluded_row_count > 0 and not source_chain_attribution_complete
    blocker_names: list[str] = []
    if row_count_blocker:
        blocker_names.append("insufficient_comparable_rows_per_slice")
    if exclusion_blocker:
        blocker_names.append("historical_target_exclusions_not_acceptable")
    if coverage_blocker:
        blocker_names.append("coverage_below_threshold")
    if evidence_quality_blocker:
        blocker_names.append("candidate_did_not_improve_on_enough_slices")
    if source_chain_governance_repair_needed:
        blocker_names.append("missing_governed_exclusion_attribution")
    weak_slice = row_count_blocker or exclusion_blocker or coverage_blocker or evidence_quality_blocker
    weak_slice_blocker = _select_weak_slice_primary_blocker(blocker_names)
    weak_slice_blocker_family = _WEAK_SLICE_REPAIR_FAMILY_BY_BLOCKER.get(weak_slice_blocker, None)
    weakness_driver = _build_weak_slice_weakness_driver(
        row_count_blocker=row_count_blocker,
        exclusion_blocker=exclusion_blocker,
        coverage_blocker=coverage_blocker,
        evidence_quality_blocker=evidence_quality_blocker,
    )
    current_positive_improvement_slice_share = _weak_slice_float(gate_inputs.get("positive_improvement_slice_share"))
    current_slice_count = max(_weak_slice_int(gate_inputs.get("slice_count")), 1)

    summary_row = {
        "weak_slice_rank": None,
        "slice_identifier": slice_identifier,
        "weak_slice": weak_slice,
        "weakness_driver": weakness_driver,
        "current_comparable_rows": current_comparable_rows,
        "required_comparable_rows": required_comparable_rows,
        "comparable_row_shortfall": comparable_row_shortfall,
        "current_exclusion_rate": current_exclusion_rate,
        "allowed_exclusion_rate": allowed_exclusion_rate,
        "exclusion_gap": exclusion_gap,
        "current_coverage_rate": current_coverage_rate,
        "required_coverage_rate": required_coverage_rate,
        "coverage_gap": coverage_gap,
        "excluded_row_count": excluded_row_count,
        "current_candidate_capital_mae_improvement": candidate_improvement,
        "current_candidate_shadow_model_outperformed_current_shadow_model": candidate_outperformed,
        "current_slice_gate_decision": slice_gate_decision,
        "current_evidence_outcome": evidence_outcome,
        "weak_slice_blocker_family": weak_slice_blocker_family,
        "weak_slice_blocker": weak_slice_blocker,
        "row_count_repair_needed": row_count_blocker,
        "exclusion_rate_repair_needed": exclusion_blocker or coverage_blocker,
        "evidence_quality_repair_needed": evidence_quality_blocker,
        "source_chain_governance_repair_needed": source_chain_governance_repair_needed,
        "source_chain_attribution_complete": source_chain_attribution_complete,
        "exclusion_reason_counts": _stringify_weak_slice_reason_counts(exclusion_reason_counts),
        "target_contract_summary_json_path": None if target_contract_summary_path is None else str(target_contract_summary_path),
        "target_contract_promotion_gate_json_path": None if target_contract_gate_path is None else str(target_contract_gate_path),
        "slice_run_manifest_path": None if slice_run_manifest_path_value is None else str(Path(slice_run_manifest_path_value).expanduser().resolve()),
    }
    return {
        "summary_row": summary_row,
        "slice_identifier": slice_identifier,
        "weak_slice": weak_slice,
        "weak_slice_blocker": weak_slice_blocker,
        "weak_slice_blocker_family": weak_slice_blocker_family,
        "blocker_names": blocker_names,
        "current_comparable_rows": current_comparable_rows,
        "required_comparable_rows": required_comparable_rows,
        "comparable_row_shortfall": comparable_row_shortfall,
        "current_exclusion_rate": current_exclusion_rate,
        "allowed_exclusion_rate": allowed_exclusion_rate,
        "exclusion_gap": exclusion_gap,
        "current_coverage_rate": current_coverage_rate,
        "required_coverage_rate": required_coverage_rate,
        "coverage_gap": coverage_gap,
        "evaluation_row_count": evaluation_row_count,
        "excluded_row_count": excluded_row_count,
        "candidate_improvement": candidate_improvement,
        "candidate_outperformed": candidate_outperformed,
        "slice_gate_decision": slice_gate_decision,
        "evidence_outcome": evidence_outcome,
        "source_chain_governance_repair_needed": source_chain_governance_repair_needed,
        "source_chain_attribution_complete": source_chain_attribution_complete,
        "exclusion_reason_counts": exclusion_reason_counts,
        "replay_exclusion_reason_counts": exclusion_reason_counts,
        "current_positive_improvement_slice_share": current_positive_improvement_slice_share,
        "minimum_positive_improvement_slice_share": _weak_slice_float(
            promotion_criteria.get("minimum_positive_improvement_slice_share"),
        ),
        "current_slice_count": current_slice_count,
        "current_positive_improvement_slice_count": max(
            _weak_slice_int(round(current_positive_improvement_slice_share * current_slice_count)),
            0,
        ),
        "slice_run_manifest_path": None if slice_run_manifest_path_value is None else str(Path(slice_run_manifest_path_value).expanduser().resolve()),
        "run_artifacts": run_artifacts,
        "current_global_dominant_blocker": current_global_dominant_blocker,
        "readiness_ranked_blockers": list(readiness_ranked_blockers),
    }


def _build_weak_slice_repair_options(
    *,
    slice_context: dict[str, object],
    current_global_dominant_blocker: str,
    readiness_ranked_blockers: Sequence[str],
) -> list[dict[str, object]]:
    if not bool(slice_context.get("weak_slice")):
        return []

    slice_identifier = str(slice_context.get("slice_identifier") or "")
    current_primary_blocker = str(slice_context.get("weak_slice_blocker") or "")
    blocker_order = list(readiness_ranked_blockers) if readiness_ranked_blockers else list(_WEAK_SLICE_PRIMARY_BLOCKER_PRIORITY)
    if current_primary_blocker and current_primary_blocker not in blocker_order:
        blocker_order.insert(0, current_primary_blocker)

    current_comparable_rows = _weak_slice_int(slice_context.get("current_comparable_rows"))
    required_comparable_rows = _weak_slice_int(slice_context.get("required_comparable_rows"))
    comparable_row_shortfall = _weak_slice_int(slice_context.get("comparable_row_shortfall"))
    current_exclusion_rate = _weak_slice_float(slice_context.get("current_exclusion_rate"))
    allowed_exclusion_rate = _weak_slice_float(slice_context.get("allowed_exclusion_rate"))
    exclusion_gap = _weak_slice_float(slice_context.get("exclusion_gap"))
    current_coverage_rate = _weak_slice_float(slice_context.get("current_coverage_rate"))
    required_coverage_rate = _weak_slice_float(slice_context.get("required_coverage_rate"))
    coverage_gap = _weak_slice_float(slice_context.get("coverage_gap"))
    evaluation_row_count = _weak_slice_int(slice_context.get("evaluation_row_count"))
    excluded_row_count = _weak_slice_int(slice_context.get("excluded_row_count"))
    candidate_improvement = _weak_slice_float(slice_context.get("candidate_improvement"))
    minimum_positive_improvement_slice_share = _weak_slice_float(
        slice_context.get("minimum_positive_improvement_slice_share"),
    )
    current_positive_improvement_slice_count = _weak_slice_int(
        slice_context.get("current_positive_improvement_slice_count"),
    )
    current_slice_count = max(_weak_slice_int(slice_context.get("current_slice_count")), 1)

    options: list[dict[str, object]] = []
    if comparable_row_shortfall > 0:
        projected_comparable_rows = current_comparable_rows + comparable_row_shortfall
        projected_exclusion_rate = (
            excluded_row_count / (evaluation_row_count + comparable_row_shortfall)
            if (evaluation_row_count + comparable_row_shortfall) > 0 else 0.0
        )
        projected_coverage_rate = (
            projected_comparable_rows / (evaluation_row_count + comparable_row_shortfall)
            if (evaluation_row_count + comparable_row_shortfall) > 0 else 1.0
        )
        cleared_blockers = ["insufficient_comparable_rows_per_slice"]
        if exclusion_gap > 0.0 and projected_exclusion_rate <= allowed_exclusion_rate:
            cleared_blockers.append("historical_target_exclusions_not_acceptable")
        if coverage_gap > 0.0 and projected_coverage_rate >= required_coverage_rate:
            cleared_blockers.append("coverage_below_threshold")
        projected_next_blocker = _next_weak_slice_blocker(
            blocker_order=blocker_order,
            current_blockers=slice_context.get("blocker_names") or [],
            cleared_blockers=cleared_blockers,
        )
        options.append(
            {
                "slice_identifier": slice_identifier,
                "repair_category": "row_count_repairs",
                "blocker_family": "row_count_repairs",
                "blocker_name": "insufficient_comparable_rows_per_slice",
                "current_value": current_comparable_rows,
                "threshold_value": required_comparable_rows,
                "delta_to_threshold": comparable_row_shortfall,
                "work_units": comparable_row_shortfall,
                "work_unit_type": "additional_comparable_rows",
                "projected_comparable_rows": projected_comparable_rows,
                "projected_exclusion_rate": projected_exclusion_rate,
                "projected_coverage_rate": projected_coverage_rate,
                "clears_blockers": "|".join(cleared_blockers),
                "clears_slice_primary_blocker": current_primary_blocker in cleared_blockers,
                "clears_global_dominant_blocker": current_global_dominant_blocker in cleared_blockers,
                "projected_next_blocker": projected_next_blocker,
                "expected_readiness_gain": _build_weak_slice_gain_summary(
                    slice_identifier=slice_identifier,
                    cleared_blockers=cleared_blockers,
                    projected_next_blocker=projected_next_blocker,
                ),
                "minimum_next_evidence_required": (
                    f"Add at least {comparable_row_shortfall} governed comparable rows to {slice_identifier} "
                    f"so comparable_rows reaches {required_comparable_rows}."
                ),
                "note": (
                    "Directly repairs the weakest slice row-count shortfall and can absorb fixed excluded rows into a "
                    "safe exclusion rate when the denominator grows."
                ),
            }
        )

    if exclusion_gap > 0.0 or coverage_gap > 0.0:
        excluded_rows_to_resolve = max(
            excluded_row_count - int(np.floor(allowed_exclusion_rate * evaluation_row_count + 1e-12)),
            0,
        )
        if excluded_rows_to_resolve == 0 and coverage_gap > 0.0:
            excluded_rows_to_resolve = max(
                int(np.ceil((required_coverage_rate * evaluation_row_count) - current_comparable_rows - 1e-12)),
                0,
            )
        projected_excluded_row_count = max(excluded_row_count - excluded_rows_to_resolve, 0)
        projected_comparable_rows = current_comparable_rows + excluded_rows_to_resolve
        projected_exclusion_rate = (
            projected_excluded_row_count / evaluation_row_count if evaluation_row_count > 0 else 0.0
        )
        projected_coverage_rate = (
            projected_comparable_rows / evaluation_row_count if evaluation_row_count > 0 else 1.0
        )
        cleared_blockers: list[str] = []
        if exclusion_gap > 0.0 and projected_exclusion_rate <= allowed_exclusion_rate:
            cleared_blockers.append("historical_target_exclusions_not_acceptable")
        if coverage_gap > 0.0 and projected_coverage_rate >= required_coverage_rate:
            cleared_blockers.append("coverage_below_threshold")
        if comparable_row_shortfall > 0 and projected_comparable_rows >= required_comparable_rows:
            cleared_blockers.append("insufficient_comparable_rows_per_slice")
        projected_next_blocker = _next_weak_slice_blocker(
            blocker_order=blocker_order,
            current_blockers=slice_context.get("blocker_names") or [],
            cleared_blockers=cleared_blockers,
        )
        options.append(
            {
                "slice_identifier": slice_identifier,
                "repair_category": "exclusion_rate_repairs",
                "blocker_family": "exclusion_rate_repairs",
                "blocker_name": (
                    "historical_target_exclusions_not_acceptable"
                    if exclusion_gap > 0.0 else
                    "coverage_below_threshold"
                ),
                "current_value": current_exclusion_rate if exclusion_gap > 0.0 else current_coverage_rate,
                "threshold_value": allowed_exclusion_rate if exclusion_gap > 0.0 else required_coverage_rate,
                "delta_to_threshold": excluded_rows_to_resolve,
                "work_units": excluded_rows_to_resolve,
                "work_unit_type": "excluded_rows_resolved",
                "projected_comparable_rows": projected_comparable_rows,
                "projected_exclusion_rate": projected_exclusion_rate,
                "projected_coverage_rate": projected_coverage_rate,
                "clears_blockers": "|".join(cleared_blockers),
                "clears_slice_primary_blocker": current_primary_blocker in cleared_blockers,
                "clears_global_dominant_blocker": current_global_dominant_blocker in cleared_blockers,
                "projected_next_blocker": projected_next_blocker,
                "expected_readiness_gain": _build_weak_slice_gain_summary(
                    slice_identifier=slice_identifier,
                    cleared_blockers=cleared_blockers,
                    projected_next_blocker=projected_next_blocker,
                ),
                "minimum_next_evidence_required": (
                    f"Recover or govern away at least {excluded_rows_to_resolve} excluded historical rows on {slice_identifier} "
                    f"so exclusion_rate falls to {allowed_exclusion_rate:.4f} or lower."
                ),
                "note": (
                    "This is the smallest direct exclusion repair, but it depends on the excluded rows being concretely "
                    "attributable and recoverable under governed evidence rules."
                ),
            }
        )

    if bool(slice_context.get("summary_row", {}).get("evidence_quality_repair_needed") or slice_context.get("candidate_improvement", 0.0) <= 0.0 or not bool(slice_context.get("candidate_outperformed"))):
        projected_positive_slice_count = current_positive_improvement_slice_count + (0 if candidate_improvement > 0.0 else 1)
        projected_positive_share = projected_positive_slice_count / current_slice_count if current_slice_count else 0.0
        cleared_blockers: list[str] = []
        if projected_positive_share >= minimum_positive_improvement_slice_share:
            cleared_blockers.append("candidate_did_not_improve_on_enough_slices")
        projected_next_blocker = _next_weak_slice_blocker(
            blocker_order=blocker_order,
            current_blockers=slice_context.get("blocker_names") or [],
            cleared_blockers=cleared_blockers,
        )
        options.append(
            {
                "slice_identifier": slice_identifier,
                "repair_category": "evidence_quality_repairs",
                "blocker_family": "evidence_quality_repairs",
                "blocker_name": "candidate_did_not_improve_on_enough_slices",
                "current_value": candidate_improvement,
                "threshold_value": 0.0,
                "delta_to_threshold": max(0.0, 0.0 - candidate_improvement),
                "work_units": 1,
                "work_unit_type": "slice_positive_improvement_flip",
                "projected_comparable_rows": current_comparable_rows,
                "projected_exclusion_rate": current_exclusion_rate,
                "projected_coverage_rate": current_coverage_rate,
                "clears_blockers": "|".join(cleared_blockers),
                "clears_slice_primary_blocker": current_primary_blocker in cleared_blockers,
                "clears_global_dominant_blocker": current_global_dominant_blocker in cleared_blockers,
                "projected_next_blocker": projected_next_blocker,
                "expected_readiness_gain": _build_weak_slice_gain_summary(
                    slice_identifier=slice_identifier,
                    cleared_blockers=cleared_blockers,
                    projected_next_blocker=projected_next_blocker,
                ),
                "minimum_next_evidence_required": (
                    f"Flip {slice_identifier} to positive candidate improvement so the positive-improvement slice share reaches "
                    f"at least {minimum_positive_improvement_slice_share:.4f}."
                ),
                "note": (
                    "This clears the slice's candidate-quality contribution only if the governed evidence on the repaired slice "
                    "turns materially positive."
                ),
            }
        )

    if bool(slice_context.get("source_chain_governance_repair_needed")):
        attribution_rows = max(excluded_row_count, 1)
        projected_next_blocker = _next_weak_slice_blocker(
            blocker_order=blocker_order,
            current_blockers=slice_context.get("blocker_names") or [],
            cleared_blockers=["missing_governed_exclusion_attribution"],
        )
        options.append(
            {
                "slice_identifier": slice_identifier,
                "repair_category": "source_chain_governance_repairs",
                "blocker_family": "source_chain_governance_repairs",
                "blocker_name": "missing_governed_exclusion_attribution",
                "current_value": 0,
                "threshold_value": attribution_rows,
                "delta_to_threshold": attribution_rows,
                "work_units": attribution_rows,
                "work_unit_type": "excluded_rows_attributed",
                "projected_comparable_rows": current_comparable_rows,
                "projected_exclusion_rate": current_exclusion_rate,
                "projected_coverage_rate": current_coverage_rate,
                "clears_blockers": "missing_governed_exclusion_attribution",
                "clears_slice_primary_blocker": current_primary_blocker == "missing_governed_exclusion_attribution",
                "clears_global_dominant_blocker": current_global_dominant_blocker == "missing_governed_exclusion_attribution",
                "projected_next_blocker": projected_next_blocker,
                "expected_readiness_gain": (
                    f"Does not clear a readiness threshold by itself, but it turns {slice_identifier} into an attributable exclusion repair "
                    "instead of a blind governed replay."
                ),
                "minimum_next_evidence_required": (
                    f"Persist governed exclusion lineage for the {attribution_rows} excluded rows on {slice_identifier}; "
                    "current replay exclusion reasons collapse to non-diagnostic values."
                ),
                "note": (
                    f"Observed exclusion reasons: {_stringify_weak_slice_reason_counts(slice_context.get('replay_exclusion_reason_counts') or {})}."
                ),
            }
        )
    return options


def _build_weak_slice_repair_option_score(
    *,
    option_row: dict[str, object],
    current_global_dominant_blocker: str,
) -> float:
    cleared_blockers = _split_pipe_values(option_row.get("clears_blockers"))
    score = 0.0
    if bool(option_row.get("clears_slice_primary_blocker")):
        score += 100.0
    if current_global_dominant_blocker and current_global_dominant_blocker in cleared_blockers:
        score += 50.0
    score += 12.0 * len(cleared_blockers)
    if str(option_row.get("repair_category") or "") == "source_chain_governance_repairs":
        score -= 20.0
    score -= _weak_slice_float(option_row.get("work_units")) / 10.0
    return score


def _build_weak_slice_repair_residual_examples_payload(
    *,
    run_id: str,
    weakest_slice: dict[str, object] | None,
    source_target_mode_multi_slice_summary_path: str,
    source_target_mode_multi_slice_manifest_path: str,
    source_target_mode_multi_slice_residual_examples_path: str | None,
    source_target_mode_multi_slice_residual_examples_payload: dict[str, object],
) -> dict[str, object]:
    if weakest_slice is None:
        return {
            "run_id": run_id,
            "row_scope": "completed_slice_repair_planning",
            "source_target_mode_multi_slice_manifest_path": source_target_mode_multi_slice_manifest_path,
            "source_target_mode_multi_slice_summary_path": source_target_mode_multi_slice_summary_path,
            "source_target_mode_multi_slice_residual_examples_path": source_target_mode_multi_slice_residual_examples_path,
            "row_count": 0,
            "rows": [],
        }
    slice_identifier = str(weakest_slice.get("slice_identifier") or "")
    slice_run_manifest_path_value = weakest_slice.get("slice_run_manifest_path")
    run_artifacts = _load_weak_slice_run_artifacts(
        None if slice_run_manifest_path_value is None else str(slice_run_manifest_path_value),
    )
    residual_rows = []
    for row in run_artifacts.get("target_mode_residual_rows") or []:
        if len(residual_rows) >= _WEAK_SLICE_REPAIR_RESIDUAL_ROW_LIMIT:
            break
        residual_rows.append({"example_type": "comparable_residual", **row})
    for row in run_artifacts.get("excluded_row_examples") or []:
        if len(residual_rows) >= _WEAK_SLICE_REPAIR_RESIDUAL_ROW_LIMIT:
            break
        residual_rows.append({"example_type": "excluded_row", **row})
    if not residual_rows and isinstance(source_target_mode_multi_slice_residual_examples_payload, dict):
        for row in source_target_mode_multi_slice_residual_examples_payload.get("rows") or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("slice_identifier") or "") != slice_identifier:
                continue
            residual_rows.append({"example_type": "multi_slice_residual", **row})
            if len(residual_rows) >= _WEAK_SLICE_REPAIR_RESIDUAL_ROW_LIMIT:
                break
    return {
        "run_id": run_id,
        "row_scope": "completed_slice_repair_planning",
        "source_target_mode_multi_slice_manifest_path": source_target_mode_multi_slice_manifest_path,
        "source_target_mode_multi_slice_summary_path": source_target_mode_multi_slice_summary_path,
        "source_target_mode_multi_slice_residual_examples_path": source_target_mode_multi_slice_residual_examples_path,
        "weakest_slice_identifier": slice_identifier,
        "weakest_slice_blocker_family": weakest_slice.get("weak_slice_blocker_family"),
        "weakest_slice_blocker": weakest_slice.get("weak_slice_blocker"),
        "top_row_limit": _WEAK_SLICE_REPAIR_RESIDUAL_ROW_LIMIT,
        "row_count": int(len(residual_rows)),
        "rows": residual_rows,
    }


def _load_weak_slice_run_artifacts(slice_run_manifest_path_value: str | None) -> dict[str, object]:
    if not slice_run_manifest_path_value:
        return {
            "excluded_row_examples": [],
            "replay_exclusion_reason_counts": {},
            "target_mode_residual_rows": [],
        }
    run_manifest_path = Path(slice_run_manifest_path_value).expanduser().resolve()
    if not run_manifest_path.exists():
        return {
            "excluded_row_examples": [],
            "replay_exclusion_reason_counts": {},
            "target_mode_residual_rows": [],
        }
    run_manifest_payload = read_json(run_manifest_path)
    if not isinstance(run_manifest_payload, dict):
        return {
            "excluded_row_examples": [],
            "replay_exclusion_reason_counts": {},
            "target_mode_residual_rows": [],
        }
    artifact_files = run_manifest_payload.get("artifact_files")
    if not isinstance(artifact_files, dict):
        return {
            "excluded_row_examples": [],
            "replay_exclusion_reason_counts": {},
            "target_mode_residual_rows": [],
        }
    excluded_row_examples: list[dict[str, object]] = []
    replay_exclusion_reason_counts: dict[str, int] = {}
    row_diagnostics_value = artifact_files.get("target_contract_row_diagnostics_parquet")
    if isinstance(row_diagnostics_value, str) and row_diagnostics_value:
        row_diagnostics_path = _resolve_target_contract_design_existing_path(
            row_diagnostics_value,
            base_path=run_manifest_path.parent,
        )
        row_diagnostics_frame = pd.read_parquet(row_diagnostics_path)
        if "historical_contract_valid_flag" in row_diagnostics_frame.columns:
            historical_valid = pd.to_numeric(
                row_diagnostics_frame["historical_contract_valid_flag"],
                errors="coerce",
            ).fillna(0.0)
            excluded_frame = row_diagnostics_frame.loc[historical_valid.lt(1.0)].copy()
            if "replay_exclusion_reason" in excluded_frame.columns:
                replay_exclusion_reason_counts = {
                    str(key): int(value)
                    for key, value in excluded_frame["replay_exclusion_reason"].fillna("<NA>").astype(str).value_counts(dropna=False).to_dict().items()
                }
            example_columns = [
                column_name
                for column_name in (
                    "promotion_row_key",
                    "replay_exclusion_reason",
                    "target_contract_replay_comparable_flag",
                    "split_name",
                )
                if column_name in excluded_frame.columns
            ]
            if example_columns:
                excluded_row_examples = _json_ready_records(
                    excluded_frame.loc[:, example_columns].head(_WEAK_SLICE_REPAIR_RESIDUAL_ROW_LIMIT)
                )
    target_mode_residual_rows: list[dict[str, object]] = []
    target_mode_residual_examples_value = artifact_files.get("target_mode_residual_examples_json")
    if isinstance(target_mode_residual_examples_value, str) and target_mode_residual_examples_value:
        target_mode_residual_examples_path = _resolve_target_contract_design_existing_path(
            target_mode_residual_examples_value,
            base_path=run_manifest_path.parent,
        )
        target_mode_residual_examples_payload = read_json(target_mode_residual_examples_path)
        if isinstance(target_mode_residual_examples_payload, dict):
            rows = target_mode_residual_examples_payload.get("rows")
            if isinstance(rows, list):
                target_mode_residual_rows = [
                    row
                    for row in rows[:_WEAK_SLICE_REPAIR_RESIDUAL_ROW_LIMIT]
                    if isinstance(row, dict)
                ]
    return {
        "excluded_row_examples": excluded_row_examples,
        "replay_exclusion_reason_counts": replay_exclusion_reason_counts,
        "target_mode_residual_rows": target_mode_residual_rows,
    }


def _weak_slice_plan_row_to_payload(plan_row: dict[str, object] | None) -> dict[str, object] | None:
    if plan_row is None:
        return None
    payload = dict(plan_row)
    payload["clears_blockers"] = _split_pipe_values(plan_row.get("clears_blockers"))
    return payload


def _resolve_optional_weak_slice_repair_path(path_value: object, *, base_path: Path) -> Path | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    return _resolve_target_contract_design_existing_path(path_value, base_path=base_path)


def _weak_slice_float(value: object, *, default: float = 0.0) -> float:
    series = pd.to_numeric(pd.Series([value]), errors="coerce")
    if series.empty or pd.isna(series.iloc[0]):
        return default
    return float(series.iloc[0])


def _weak_slice_int(value: object) -> int:
    return int(round(_weak_slice_float(value)))


def _weak_slice_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _weak_slice_blocker_priority(blocker_name: str) -> int:
    try:
        return _WEAK_SLICE_PRIMARY_BLOCKER_PRIORITY.index(blocker_name)
    except ValueError:
        return len(_WEAK_SLICE_PRIMARY_BLOCKER_PRIORITY)


def _select_weak_slice_primary_blocker(blocker_names: Sequence[str]) -> str | None:
    for blocker_name in _WEAK_SLICE_PRIMARY_BLOCKER_PRIORITY:
        if blocker_name in blocker_names:
            return blocker_name
    return blocker_names[0] if blocker_names else None


def _build_weak_slice_weakness_driver(
    *,
    row_count_blocker: bool,
    exclusion_blocker: bool,
    coverage_blocker: bool,
    evidence_quality_blocker: bool,
) -> str:
    if row_count_blocker and (exclusion_blocker or coverage_blocker):
        return "too_few_rows_and_too_much_exclusion"
    if row_count_blocker:
        return "too_few_rows"
    if exclusion_blocker or coverage_blocker:
        return "too_much_exclusion"
    if evidence_quality_blocker:
        return "evidence_quality_not_positive"
    return "not_blocking"


def _infer_weak_slice_global_blocker(summary_rows: Sequence[dict[str, object]]) -> str:
    for blocker_name in _WEAK_SLICE_PRIMARY_BLOCKER_PRIORITY:
        if any(str(row.get("weak_slice_blocker") or "") == blocker_name for row in summary_rows if row.get("weak_slice")):
            return blocker_name
    return ""


def _next_weak_slice_blocker(
    *,
    blocker_order: Sequence[str],
    current_blockers: Sequence[str],
    cleared_blockers: Sequence[str],
) -> str | None:
    current_blocker_set = {str(blocker_name) for blocker_name in current_blockers}
    cleared_blocker_set = {str(blocker_name) for blocker_name in cleared_blockers}
    for blocker_name in blocker_order:
        if blocker_name in current_blocker_set and blocker_name not in cleared_blocker_set:
            return blocker_name
    return None


def _build_weak_slice_gain_summary(
    *,
    slice_identifier: str,
    cleared_blockers: Sequence[str],
    projected_next_blocker: str | None,
) -> str:
    if not cleared_blockers:
        if projected_next_blocker:
            return f"Leaves {slice_identifier} blocked by {projected_next_blocker}."
        return f"Does not clear a persisted blocker on {slice_identifier}."
    blocker_summary = ", ".join(cleared_blockers)
    if projected_next_blocker:
        return (
            f"Clears {blocker_summary} on {slice_identifier}; next persisted blocker becomes "
            f"{projected_next_blocker}."
        )
    return f"Clears {blocker_summary} on {slice_identifier} with no persisted weak-slice blocker remaining."


def _normalize_weak_slice_reason_counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, count in value.items():
        reason = str(key or "<NA>")
        normalized[reason] = int(round(_weak_slice_float(count)))
    return normalized


def _stringify_weak_slice_reason_counts(reason_counts: object) -> str:
    counts = _normalize_weak_slice_reason_counts(reason_counts)
    if not counts:
        return ""
    return "|".join(f"{reason}:{count}" for reason, count in sorted(counts.items()))


def _split_pipe_values(value: object) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    return [part for part in value.split("|") if part]


def _build_promotion_readiness_historical_blocker_records(
    *,
    gate_payload: dict[str, object],
    candidate_name: str,
    contract_role: str,
) -> list[dict[str, object]]:
    criteria = gate_payload.get("promotion_criteria")
    gate_inputs = gate_payload.get("gate_inputs")
    if not isinstance(criteria, dict) or not isinstance(gate_inputs, dict):
        raise ValueError("promotion readiness historical gate requires promotion_criteria and gate_inputs")
    records: list[dict[str, object]] = []
    records.extend(
        _build_promotion_readiness_threshold_blocker_records(
            candidate_name=candidate_name,
            contract_role=contract_role,
            source_artifact_type="target_mode_multi_slice_gate",
            source_decision=str(gate_payload.get("decision") or ""),
            thresholds=(
                (
                    "insufficient_slice_count",
                    "evidence_depth",
                    gate_inputs.get("slice_count"),
                    criteria.get("minimum_slice_count"),
                    "minimum",
                    "completed_slices",
                ),
                (
                    "insufficient_comparable_rows_per_slice",
                    "slice_quality",
                    gate_inputs.get("minimum_comparable_rows_observed"),
                    criteria.get("minimum_comparable_rows_per_slice"),
                    "minimum",
                    "comparable_rows",
                ),
                (
                    "exclusion_rate_above_threshold",
                    "slice_quality",
                    gate_inputs.get("maximum_historical_exclusion_rate_observed"),
                    criteria.get("maximum_historical_exclusion_rate"),
                    "maximum",
                    "share",
                ),
                (
                    "candidate_did_not_improve_on_enough_slices",
                    "candidate_quality",
                    gate_inputs.get("positive_improvement_slice_share"),
                    criteria.get("minimum_positive_improvement_slice_share"),
                    "minimum",
                    "share",
                ),
                (
                    "candidate_median_improvement_trivial",
                    "candidate_quality",
                    gate_inputs.get("median_relative_improvement"),
                    criteria.get("minimum_median_relative_improvement"),
                    "minimum",
                    "relative_improvement_rate",
                ),
                (
                    "candidate_improvement_not_stable",
                    "candidate_quality",
                    gate_inputs.get("relative_improvement_coefficient_of_variation"),
                    criteria.get("maximum_relative_improvement_coefficient_of_variation"),
                    "maximum",
                    "coefficient_of_variation",
                ),
                (
                    "stock_basis_proxy_mismatch_not_persistent",
                    "candidate_quality",
                    gate_inputs.get("stock_basis_proxy_mismatch_slice_share"),
                    criteria.get("minimum_stock_basis_dominance_share"),
                    "minimum",
                    "share",
                ),
            ),
        )
    )
    return records


def _build_promotion_readiness_design_blocker_records(
    *,
    gate_payload: dict[str, object],
    candidate_name: str,
    contract_role: str,
) -> list[dict[str, object]]:
    criteria = gate_payload.get("promotion_criteria")
    gate_inputs = gate_payload.get("gate_inputs")
    if not isinstance(criteria, dict) or not isinstance(gate_inputs, dict):
        raise ValueError("promotion readiness design gate requires promotion_criteria and gate_inputs")
    return _build_promotion_readiness_threshold_blocker_records(
        candidate_name=candidate_name,
        contract_role=contract_role,
        source_artifact_type="target_design_repeated_evidence_gate",
        source_decision=str(gate_payload.get("decision") or ""),
        thresholds=(
            (
                "insufficient_completed_slice_count",
                "evidence_depth",
                gate_inputs.get("slice_count"),
                criteria.get("minimum_slice_count"),
                "minimum",
                "completed_slices",
            ),
            (
                "insufficient_aggregate_comparable_rows",
                "evidence_depth",
                gate_inputs.get("total_comparable_rows"),
                criteria.get("minimum_aggregate_comparable_rows"),
                "minimum",
                "comparable_rows",
            ),
            (
                "insufficient_comparable_rows_per_slice",
                "slice_quality",
                gate_inputs.get("minimum_comparable_rows_observed"),
                criteria.get("minimum_comparable_rows_per_slice"),
                "minimum",
                "comparable_rows",
            ),
            (
                "coverage_below_threshold",
                "slice_quality",
                gate_inputs.get("minimum_coverage_rate_observed"),
                criteria.get("minimum_coverage_rate"),
                "minimum",
                "share",
            ),
            (
                "exclusion_rate_above_threshold",
                "slice_quality",
                gate_inputs.get("maximum_exclusion_rate_observed"),
                criteria.get("maximum_exclusion_rate"),
                "maximum",
                "share",
            ),
            (
                "candidate_did_not_improve_on_enough_slices",
                "candidate_quality",
                gate_inputs.get("positive_improvement_slice_share"),
                criteria.get("minimum_positive_improvement_slice_share"),
                "minimum",
                "share",
            ),
            (
                "candidate_median_improvement_trivial",
                "candidate_quality",
                gate_inputs.get("median_relative_improvement"),
                criteria.get("minimum_median_relative_improvement"),
                "minimum",
                "relative_improvement_rate",
            ),
            (
                "candidate_improvement_not_stable",
                "candidate_quality",
                gate_inputs.get("relative_improvement_coefficient_of_variation"),
                criteria.get("maximum_relative_improvement_coefficient_of_variation"),
                "maximum",
                "coefficient_of_variation",
            ),
            (
                "stock_basis_proxy_mismatch_not_persistent",
                "candidate_quality",
                gate_inputs.get("stock_basis_proxy_mismatch_slice_share"),
                criteria.get("minimum_stock_basis_dominance_share"),
                "minimum",
                "share",
            ),
            (
                "design_candidate_not_consistently_best",
                "candidate_quality",
                gate_inputs.get("best_candidate_slice_share"),
                criteria.get("minimum_best_candidate_slice_share"),
                "minimum",
                "share",
            ),
            (
                "candidate_boundary_not_cleaner_on_enough_slices",
                "candidate_quality",
                gate_inputs.get("clean_boundary_slice_share"),
                _TARGET_CONTRACT_DESIGN_MIN_CLEAN_BOUNDARY_SHARE,
                "minimum",
                "share",
            ),
            (
                "candidate_still_depends_on_stock_basis_proxy",
                "candidate_quality",
                gate_inputs.get("stock_basis_dependency_reduced_slice_share"),
                criteria.get("minimum_best_candidate_slice_share"),
                "minimum",
                "share",
            ),
        ),
    )


def _build_promotion_readiness_threshold_blocker_records(
    *,
    candidate_name: str,
    contract_role: str,
    source_artifact_type: str,
    source_decision: str,
    thresholds: Sequence[tuple[str, str, object, object, str, str]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for blocker_name, blocker_family, observed_value, required_value, comparison, unit in thresholds:
        numeric_observed = _promotion_readiness_numeric_value(observed_value)
        numeric_required = _promotion_readiness_numeric_value(required_value)
        if numeric_observed is None or numeric_required is None:
            continue
        gap = _promotion_readiness_threshold_gap(
            observed_value=numeric_observed,
            required_value=numeric_required,
            comparison=comparison,
        )
        if gap <= 0.0:
            continue
        records.append(
            {
                "candidate_name": candidate_name,
                "contract_role": contract_role,
                "blocker_name": blocker_name,
                "blocker_family": blocker_family,
                "source_artifact_type": source_artifact_type,
                "source_decision": source_decision,
                "observed_value": numeric_observed,
                "required_value": numeric_required,
                "comparison": comparison,
                "unit": unit,
                "delta_to_threshold": gap,
                "severity_score": _promotion_readiness_threshold_severity(
                    observed_value=numeric_observed,
                    required_value=numeric_required,
                    comparison=comparison,
                ),
                "current_best_candidate_blocker": False,
                "inherited_from_upstream_runtime": False,
            }
        )
    return records


def _build_promotion_readiness_governance_blocker_records(
    *,
    proposal_payload: dict[str, object],
    current_best_candidate_name: str,
    historical_candidate_name: str,
    design_candidate_name: str,
    live_default_candidate_name: str,
) -> list[dict[str, object]]:
    best_contract = proposal_payload.get("best_contract_under_evidence")
    if not isinstance(best_contract, dict):
        return []
    records: list[dict[str, object]] = []
    tied_contract_names = _promotion_readiness_string_list(best_contract.get("tied_contract_names"))
    if bool(best_contract.get("has_metric_tie", False)):
        affected_candidates = _dedupe_string_list(
            [
                current_best_candidate_name,
                *[name for name in tied_contract_names if name in {historical_candidate_name, design_candidate_name}],
            ]
        )
        for candidate_name in affected_candidates:
            contract_role = (
                "historical_allocation_candidate"
                if candidate_name == historical_candidate_name else
                "top_target_design_candidate"
            )
            records.append(
                {
                    "candidate_name": candidate_name,
                    "contract_role": contract_role,
                    "blocker_name": "best_candidate_tied_with_peer",
                    "blocker_family": "governance",
                    "source_artifact_type": "target_contract_three_way_proposal",
                    "source_decision": str(proposal_payload.get("decision") or ""),
                    "observed_value": float(len(affected_candidates)),
                    "required_value": 1.0,
                    "comparison": "tie_break",
                    "unit": "candidate_count",
                    "delta_to_threshold": float(max(len(affected_candidates) - 1, 1)),
                    "severity_score": 0.25,
                    "current_best_candidate_blocker": candidate_name == current_best_candidate_name,
                    "inherited_from_upstream_runtime": True,
                }
            )
    if current_best_candidate_name == live_default_candidate_name:
        for candidate_name, contract_role in (
            (historical_candidate_name, "historical_allocation_candidate"),
            (design_candidate_name, "top_target_design_candidate"),
        ):
            records.append(
                {
                    "candidate_name": candidate_name,
                    "contract_role": contract_role,
                    "blocker_name": "current_live_contract_still_best_under_evidence",
                    "blocker_family": "governance",
                    "source_artifact_type": "target_contract_three_way_proposal",
                    "source_decision": str(proposal_payload.get("decision") or ""),
                    "observed_value": 1.0,
                    "required_value": 0.0,
                    "comparison": "strictly_better_than_live_default",
                    "unit": "boolean",
                    "delta_to_threshold": 1.0,
                    "severity_score": 0.35,
                    "current_best_candidate_blocker": False,
                    "inherited_from_upstream_runtime": True,
                }
            )
    return records


def _sort_promotion_readiness_blocker_records(
    blocker_records: Sequence[dict[str, object]],
    *,
    current_best_candidate_name: str,
) -> list[dict[str, object]]:
    return sorted(
        [
            {
                **record,
                "current_best_candidate_blocker": record["candidate_name"] == current_best_candidate_name,
                "impact_score": _promotion_readiness_blocker_impact_score(
                    record,
                    affected_candidate_count=1,
                    current_best_candidate_name=current_best_candidate_name,
                ),
                "minimum_next_evidence_required": _build_promotion_readiness_minimum_next_evidence_required(
                    record,
                    affected_candidates=[str(record["candidate_name"])],
                ),
            }
            for record in blocker_records
        ],
        key=lambda record: (
            -float(record["impact_score"]),
            _promotion_readiness_blocker_priority(str(record["blocker_name"])),
            str(record["blocker_family"]),
            str(record["blocker_name"]),
            str(record["candidate_name"]),
        ),
    )


def _aggregate_promotion_readiness_blockers(
    blocker_records: Sequence[dict[str, object]],
    *,
    current_best_candidate_name: str,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for record in blocker_records:
        key = (str(record["blocker_name"]), str(record["blocker_family"]))
        group = grouped.setdefault(
            key,
            {
                "blocker_name": str(record["blocker_name"]),
                "blocker_family": str(record["blocker_family"]),
                "affected_candidates": [],
                "source_artifact_types": [],
                "representative_record": record,
                "max_severity_score": float(record["severity_score"]),
                "inherited_from_upstream_runtime": bool(record["inherited_from_upstream_runtime"]),
            },
        )
        candidate_name = str(record["candidate_name"])
        if candidate_name not in group["affected_candidates"]:
            group["affected_candidates"].append(candidate_name)
        source_artifact_type = str(record["source_artifact_type"])
        if source_artifact_type not in group["source_artifact_types"]:
            group["source_artifact_types"].append(source_artifact_type)
        if float(record["severity_score"]) >= float(group["max_severity_score"]):
            group["representative_record"] = record
            group["max_severity_score"] = float(record["severity_score"])
        group["inherited_from_upstream_runtime"] = bool(group["inherited_from_upstream_runtime"]) and bool(
            record["inherited_from_upstream_runtime"]
        )

    ranking_rows: list[dict[str, object]] = []
    for group in grouped.values():
        representative_record = dict(group["representative_record"])
        affected_candidates = list(group["affected_candidates"])
        impact_score = _promotion_readiness_blocker_impact_score(
            representative_record,
            affected_candidate_count=len(affected_candidates),
            current_best_candidate_name=current_best_candidate_name,
            current_best_candidate_blocker=current_best_candidate_name in affected_candidates,
        )
        ranking_rows.append(
            {
                "blocker_name": str(group["blocker_name"]),
                "blocker_family": str(group["blocker_family"]),
                "affected_candidates": affected_candidates,
                "affected_candidate_count": int(len(affected_candidates)),
                "source_artifact_types": list(group["source_artifact_types"]),
                "observed_value": _json_ready_value(representative_record.get("observed_value")),
                "required_value": _json_ready_value(representative_record.get("required_value")),
                "comparison": representative_record.get("comparison"),
                "unit": representative_record.get("unit"),
                "delta_to_threshold": _json_ready_value(representative_record.get("delta_to_threshold")),
                "severity_score": _json_ready_value(group["max_severity_score"]),
                "impact_score": _json_ready_value(impact_score),
                "inherited_from_upstream_runtime": bool(group["inherited_from_upstream_runtime"]),
                "minimum_next_evidence_required": _build_promotion_readiness_minimum_next_evidence_required(
                    representative_record,
                    affected_candidates=affected_candidates,
                ),
            }
        )
    return sorted(
        ranking_rows,
        key=lambda record: (
            -float(record["impact_score"]),
            _promotion_readiness_blocker_priority(str(record["blocker_name"])),
            str(record["blocker_family"]),
            str(record["blocker_name"]),
        ),
    )


def _build_promotion_readiness_candidate_scoreboard_row(
    *,
    candidate_payload: dict[str, object],
    shadow_ready: bool,
    source_decision: str,
    source_assessment: str,
    sorted_blockers: Sequence[dict[str, object]],
    current_best_candidate_name: str,
) -> dict[str, object]:
    candidate_name = str(candidate_payload.get("candidate_name") or "")
    top_blocker = sorted_blockers[0] if sorted_blockers else None
    top_evidence_required = None if top_blocker is None else top_blocker["minimum_next_evidence_required"]
    blocker_names = [str(record["blocker_name"]) for record in sorted_blockers]
    governance_blocker_count = int(sum(bool(record["inherited_from_upstream_runtime"]) for record in sorted_blockers))
    return {
        "candidate_name": candidate_name,
        "contract_role": str(candidate_payload.get("contract_role") or ""),
        "current_best_under_evidence": candidate_name == current_best_candidate_name,
        "shadow_ready": shadow_ready,
        "source_decision": source_decision,
        "source_assessment": source_assessment,
        "candidate_rank": candidate_payload.get("candidate_rank"),
        "has_metric_tie": bool(candidate_payload.get("has_metric_tie", False)),
        "tied_contract_names": "|".join(_promotion_readiness_string_list(candidate_payload.get("tied_contract_names"))),
        "blocker_count": int(len(sorted_blockers)),
        "governance_blocker_count": governance_blocker_count,
        "blocker_names": "|".join(blocker_names),
        "dominant_blocker_family": None if top_blocker is None else top_blocker["blocker_family"],
        "dominant_blocker": None if top_blocker is None else top_blocker["blocker_name"],
        "minimum_next_evidence_summary": (
            None if top_evidence_required is None else top_evidence_required.get("requirement")
        ),
    }


def _build_promotion_readiness_decision_packet(
    *,
    compared_contracts: Sequence[dict[str, object]],
    current_live_contract: dict[str, object],
    best_contract_under_evidence: dict[str, object],
    stability_gate: dict[str, object],
    repeated_gate_outcome: dict[str, object],
    three_way_proposal_payload: dict[str, object],
    blocker_ranking_rows: Sequence[dict[str, object]],
    historical_candidate_shadow_ready: bool,
    design_candidate_shadow_ready: bool,
    current_best_candidate_name: str,
) -> dict[str, object]:
    best_candidate_payload = {
        key: _json_ready_value(value)
        for key, value in best_contract_under_evidence.items()
        if not str(key).startswith("_")
    }
    current_best_shadow_ready = (
        historical_candidate_shadow_ready
        if current_best_candidate_name == _TARGET_CONTRACT_THREE_WAY_HISTORICAL_CANDIDATE else
        design_candidate_shadow_ready
        if current_best_candidate_name == str(
            three_way_proposal_payload.get("top_target_design_candidate", {}).get("candidate_name") or ""
        ) else
        False
    )
    current_decision = (
        "candidate_for_shadow_training"
        if current_best_shadow_ready and not bool(best_contract_under_evidence.get("has_metric_tie", False)) else
        "diagnostics_only"
    )
    dominant_blocker = blocker_ranking_rows[0] if blocker_ranking_rows else None
    policy_remains_paused = all(
        bool(payload.get("policy_remains_paused", False))
        for payload in (stability_gate, repeated_gate_outcome, three_way_proposal_payload)
    )
    policy_status = {
        "policy_remains_paused": policy_remains_paused,
        "policy_rules_were_changed": bool(
            repeated_gate_outcome.get("policy_rules_were_changed", False)
            or three_way_proposal_payload.get("policy_rules_were_changed", False)
        ),
        "stage_11_was_changed": bool(
            repeated_gate_outcome.get("stage_11_was_changed", False)
            or three_way_proposal_payload.get("stage_11_was_changed", False)
        ),
        "runtime_path_has_no_primary_promotion_authority": True,
    }
    live_default_unchanged = all(
        bool(payload.get("current_trainer_contract_remains_live_default", False))
        for payload in (stability_gate, repeated_gate_outcome, three_way_proposal_payload)
    )
    store_facing_csv_changed = bool(
        repeated_gate_outcome.get("store_facing_csv_was_changed", False)
        or three_way_proposal_payload.get("store_facing_csv_was_changed", False)
    )
    return {
        "compared_candidates": list(compared_contracts),
        "live_default_contract": str(current_live_contract.get("candidate_name") or _TARGET_CONTRACT_DESIGN_BASELINE_CANDIDATE),
        "policy_status": policy_status,
        "current_best_candidate": {
            **best_candidate_payload,
            "shadow_ready_under_current_governance": current_best_shadow_ready,
        },
        "historical_candidate_shadow_ready": historical_candidate_shadow_ready,
        "design_candidate_shadow_ready": design_candidate_shadow_ready,
        "primary_promotion_allowed": False,
        "dominant_blocker_family": None if dominant_blocker is None else dominant_blocker["blocker_family"],
        "dominant_blocker": None if dominant_blocker is None else dominant_blocker["blocker_name"],
        "blocker_ranking": list(blocker_ranking_rows),
        "minimum_next_evidence_required": (
            None if dominant_blocker is None else dominant_blocker.get("minimum_next_evidence_required")
        ),
        "current_decision": current_decision,
        "live_default_unchanged": live_default_unchanged,
        "store_facing_csv_changed": store_facing_csv_changed,
        "publish_tree_created": False,
    }


def _build_promotion_readiness_residual_examples_payload(
    *,
    run_id: str,
    blocker_ranking_rows: Sequence[dict[str, object]],
    historical_candidate_name: str,
    design_candidate_name: str,
    source_target_mode_multi_slice_manifest_path: Path,
    source_repeated_evidence_manifest_path: Path,
    source_target_contract_three_way_residual_examples_path: Path | None,
    source_target_contract_three_way_residual_examples_payload: dict[str, object],
) -> dict[str, object]:
    dominant_blocker = blocker_ranking_rows[0] if blocker_ranking_rows else None
    rows: list[dict[str, object]] = []
    sources: list[dict[str, object]] = []
    if dominant_blocker is not None:
        remaining = _PROMOTION_READINESS_RESIDUAL_ROW_LIMIT
        for candidate_name in dominant_blocker.get("affected_candidates", []):
            if remaining <= 0:
                break
            if candidate_name == historical_candidate_name:
                source_path = source_target_mode_multi_slice_manifest_path.parent / "target_mode_multi_slice_residual_examples.json"
                payload = _load_optional_promotion_readiness_json_payload(source_path)
                source_artifact_type = "target_mode_multi_slice_residual_examples"
            elif (
                candidate_name == design_candidate_name
                and source_target_contract_three_way_residual_examples_payload
            ):
                payload = source_target_contract_three_way_residual_examples_payload
                source_path = source_target_contract_three_way_residual_examples_path
                source_artifact_type = "target_contract_three_way_residual_examples"
            elif candidate_name == design_candidate_name:
                source_path = source_repeated_evidence_manifest_path.parent / "target_design_repeated_evidence_residual_examples.json"
                payload = _load_optional_promotion_readiness_json_payload(source_path)
                source_artifact_type = "target_design_repeated_evidence_residual_examples"
            else:
                continue
            candidate_rows = payload.get("rows", []) if isinstance(payload, dict) else []
            if not isinstance(candidate_rows, list) or not candidate_rows:
                continue
            selected_rows = []
            for row in candidate_rows:
                if not isinstance(row, dict):
                    continue
                selected_rows.append(
                    {
                        **row,
                        "candidate_name": candidate_name,
                        "source_artifact_type": source_artifact_type,
                    }
                )
                if len(selected_rows) >= remaining:
                    break
            if not selected_rows:
                continue
            rows.extend(selected_rows)
            remaining = _PROMOTION_READINESS_RESIDUAL_ROW_LIMIT - len(rows)
            sources.append(
                {
                    "candidate_name": candidate_name,
                    "source_artifact_type": source_artifact_type,
                    "source_path": None if source_path is None else str(source_path),
                    "row_count": int(len(selected_rows)),
                }
            )
    return {
        "run_id": run_id,
        "row_scope": "shadow_promotion_readiness_scoreboard",
        "dominant_blocker_family": None if dominant_blocker is None else dominant_blocker["blocker_family"],
        "dominant_blocker": None if dominant_blocker is None else dominant_blocker["blocker_name"],
        "top_row_limit": _PROMOTION_READINESS_RESIDUAL_ROW_LIMIT,
        "row_count": int(len(rows)),
        "source_artifacts": sources,
        "rows": _json_ready_records(pd.DataFrame(rows)) if rows else [],
    }


def _resolve_optional_promotion_readiness_existing_path(
    raw_path: object,
    *,
    base_path: Path,
    context: str,
) -> Path | None:
    if raw_path is None:
        return None
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"promotion readiness source path is invalid for {context}")
    return _resolve_target_contract_design_existing_path(raw_path, base_path=base_path)


def _validate_promotion_readiness_three_way_source_alignment(
    *,
    proposal_payload: dict[str, object],
    summary_payload: dict[str, object],
    source_repeated_evidence_manifest_path: Path,
    source_design_proposal_path: Path,
    source_design_proposal_payload: dict[str, object],
) -> None:
    proposal_source_manifest_path = proposal_payload.get("source_repeated_evidence_manifest_path")
    if isinstance(proposal_source_manifest_path, str) and proposal_source_manifest_path:
        resolved_source_manifest_path = _resolve_target_contract_design_existing_path(
            proposal_source_manifest_path,
            base_path=source_repeated_evidence_manifest_path.parent,
        )
        if resolved_source_manifest_path != source_repeated_evidence_manifest_path:
            raise ValueError(
                "promotion readiness explicit three-way source resolves to a different repeated-evidence manifest than the requested source"
            )
    proposal_source_design_path = proposal_payload.get("source_target_contract_design_proposal_path")
    if isinstance(proposal_source_design_path, str) and proposal_source_design_path:
        resolved_source_design_path = _resolve_target_contract_design_existing_path(
            proposal_source_design_path,
            base_path=source_design_proposal_path.parent,
        )
        if resolved_source_design_path != source_design_proposal_path:
            raise ValueError(
                "promotion readiness explicit three-way source resolves to a different design proposal than the requested source"
            )
    if summary_payload:
        summary_proposal = summary_payload.get("proposal")
        if isinstance(summary_proposal, dict):
            summary_candidate_name = str(
                summary_proposal.get("top_target_design_candidate", {}).get("candidate_name") or ""
            )
            proposal_candidate_name = str(
                proposal_payload.get("top_target_design_candidate", {}).get("candidate_name") or ""
            )
            if summary_candidate_name and summary_candidate_name != proposal_candidate_name:
                raise ValueError(
                    "promotion readiness three-way summary and proposal disagree on the top design candidate"
                )
    design_candidate_name = _target_contract_three_way_top_design_candidate_name(
        source_design_proposal_payload,
        context=str(source_design_proposal_path),
    )
    proposal_candidate_name = str(
        proposal_payload.get("top_target_design_candidate", {}).get("candidate_name") or ""
    )
    if proposal_candidate_name and proposal_candidate_name != design_candidate_name:
        raise ValueError(
            "promotion readiness design proposal and explicit three-way proposal disagree on the top design candidate"
        )


def _load_optional_promotion_readiness_json_payload(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    return read_json(path)


def _promotion_readiness_numeric_value(value: object) -> float | None:
    series = pd.to_numeric(pd.Series([value]), errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.iloc[0])


def _promotion_readiness_threshold_gap(
    *,
    observed_value: float,
    required_value: float,
    comparison: str,
) -> float:
    if comparison == "minimum":
        return max(required_value - observed_value, 0.0)
    if comparison == "maximum":
        return max(observed_value - required_value, 0.0)
    return 1.0


def _promotion_readiness_threshold_severity(
    *,
    observed_value: float,
    required_value: float,
    comparison: str,
) -> float:
    if comparison == "minimum":
        denominator = required_value if required_value > 0.0 else 1.0
        return max((required_value - observed_value) / denominator, 0.0)
    if comparison == "maximum":
        denominator = required_value if required_value > 0.0 else 1.0
        return max((observed_value - required_value) / denominator, 0.0)
    return 1.0


def _promotion_readiness_blocker_impact_score(
    blocker_record: dict[str, object],
    *,
    affected_candidate_count: int,
    current_best_candidate_name: str,
    current_best_candidate_blocker: bool | None = None,
) -> float:
    inherited_from_upstream_runtime = bool(blocker_record.get("inherited_from_upstream_runtime", False))
    base_weight = (
        _PROMOTION_READINESS_INHERITED_BLOCKER_WEIGHT
        if inherited_from_upstream_runtime else
        _PROMOTION_READINESS_DIRECT_BLOCKER_WEIGHT
    )
    affects_current_best_candidate = (
        bool(current_best_candidate_blocker)
        if current_best_candidate_blocker is not None else
        str(blocker_record.get("candidate_name") or "") == current_best_candidate_name
    )
    return (
        base_weight
        + (_PROMOTION_READINESS_BLOCKER_SCOPE_BONUS * float(affected_candidate_count))
        + (_PROMOTION_READINESS_CURRENT_BEST_BLOCKER_BONUS if affects_current_best_candidate else 0.0)
        + float(blocker_record.get("severity_score", 0.0))
    )


def _promotion_readiness_blocker_priority(blocker_name: str) -> int:
    return _PROMOTION_READINESS_BLOCKER_PRIORITY.get(blocker_name, 999)


def _build_promotion_readiness_minimum_next_evidence_required(
    blocker_record: dict[str, object],
    *,
    affected_candidates: Sequence[str],
) -> dict[str, object]:
    blocker_name = str(blocker_record.get("blocker_name") or "")
    observed_value = blocker_record.get("observed_value")
    required_value = blocker_record.get("required_value")
    delta_to_threshold = blocker_record.get("delta_to_threshold")
    unit = str(blocker_record.get("unit") or "")
    requirement = _promotion_readiness_requirement_message(
        blocker_name=blocker_name,
        observed_value=observed_value,
        required_value=required_value,
        delta_to_threshold=delta_to_threshold,
    )
    return {
        "blocker": blocker_name,
        "blocker_family": blocker_record.get("blocker_family"),
        "affected_candidates": list(affected_candidates),
        "requirement": requirement,
        "observed_value": _json_ready_value(observed_value),
        "required_value": _json_ready_value(required_value),
        "delta_to_threshold": _json_ready_value(delta_to_threshold),
        "comparison": blocker_record.get("comparison"),
        "unit": unit,
    }


def _promotion_readiness_requirement_message(
    *,
    blocker_name: str,
    observed_value: object,
    required_value: object,
    delta_to_threshold: object,
) -> str:
    if blocker_name in {"insufficient_slice_count", "insufficient_completed_slice_count"}:
        return (
            f"Need at least {required_value:g} independent completed slices; observed {observed_value:g}, "
            f"shortfall {delta_to_threshold:g}."
        )
    if blocker_name == "insufficient_aggregate_comparable_rows":
        return (
            f"Need at least {required_value:g} governed comparable rows in aggregate; observed {observed_value:g}, "
            f"shortfall {delta_to_threshold:g}."
        )
    if blocker_name == "insufficient_comparable_rows_per_slice":
        return (
            f"Need weakest governed slice comparable rows >= {required_value:g}; observed {observed_value:g}, "
            f"shortfall {delta_to_threshold:g}."
        )
    if blocker_name == "coverage_below_threshold":
        return (
            f"Need weakest governed slice coverage >= {required_value:.4f}; observed {observed_value:.4f}, "
            f"gap {delta_to_threshold:.4f}."
        )
    if blocker_name == "exclusion_rate_above_threshold":
        return (
            f"Need worst governed exclusion rate <= {required_value:.4f}; observed {observed_value:.4f}, "
            f"excess {delta_to_threshold:.4f}."
        )
    if blocker_name == "candidate_did_not_improve_on_enough_slices":
        return (
            f"Need candidate improvement on at least {required_value:.4f} of slices; observed {observed_value:.4f}, "
            f"gap {delta_to_threshold:.4f}."
        )
    if blocker_name == "candidate_median_improvement_trivial":
        return (
            f"Need median relative improvement >= {required_value:.4f}; observed {observed_value:.4f}, "
            f"gap {delta_to_threshold:.4f}."
        )
    if blocker_name == "candidate_improvement_not_stable":
        return (
            f"Need relative-improvement coefficient of variation <= {required_value:.4f}; observed {observed_value:.4f}, "
            f"excess {delta_to_threshold:.4f}."
        )
    if blocker_name in {
        "stock_basis_proxy_mismatch_not_persistent",
        "design_candidate_not_consistently_best",
        "candidate_boundary_not_cleaner_on_enough_slices",
        "candidate_still_depends_on_stock_basis_proxy",
    }:
        return (
            f"Need governed share >= {required_value:.4f}; observed {observed_value:.4f}, gap {delta_to_threshold:.4f}."
        )
    if blocker_name == "best_candidate_tied_with_peer":
        return "Need one additional governed evidence pass that breaks the top-candidate metric tie."
    if blocker_name == "current_live_contract_still_best_under_evidence":
        return "Need governed evidence showing a non-live candidate strictly outperforming the current live default."
    return f"Need blocker {blocker_name} to clear its governed threshold before the decision can change."


def _promotion_readiness_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        if not value:
            return []
        return [part for part in value.split("|") if part]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _target_contract_design_mean(values: object) -> float | None:
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    return float(series.mean()) if not series.empty else None


def _target_contract_design_median(values: object) -> float | None:
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    return float(series.median()) if not series.empty else None


def _target_contract_design_difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return float(left - right)


def _target_contract_design_rate(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    return float(numerator / denominator)


def _target_contract_design_cv(values: object) -> float | None:
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if len(series.index) <= 1:
        return 0.0 if len(series.index) == 1 else None
    mean_value = float(series.mean())
    if mean_value <= 0.0:
        return None
    return float(series.std(ddof=0) / mean_value)


def _json_ready_value(value: object) -> object:
    if isinstance(value, np.generic):
        value = value.item()
    if value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return value
    return value


def _aggregate_target_mode_multi_slice_buckets(bucket_records: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        "bucket_name",
        "slice_count",
        "row_count_total",
        "comparable_row_count_total",
        "current_label_vs_historical_excess_capital_error_total",
        "share_of_total_current_label_capital_error",
        "current_shadow_vs_historical_excess_capital_mae_mean",
        "historical_candidate_shadow_vs_historical_excess_capital_mae_mean",
        "candidate_shadow_capital_mae_improvement_mean",
        "positive_improvement_slice_count",
        "positive_improvement_slice_share",
    ]
    if not bucket_records:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(bucket_records)
    grouped_rows: list[dict[str, object]] = []
    total_error = float(pd.to_numeric(frame["current_label_vs_historical_excess_capital_error_total"], errors="coerce").sum())
    for bucket_name, bucket_frame in frame.groupby("bucket_name", dropna=False):
        improvement = pd.to_numeric(bucket_frame["candidate_shadow_capital_mae_improvement"], errors="coerce")
        error_total = float(pd.to_numeric(bucket_frame["current_label_vs_historical_excess_capital_error_total"], errors="coerce").sum())
        positive_count = int(improvement.gt(0.0).sum())
        slice_count = int(bucket_frame["slice_identifier"].nunique()) if "slice_identifier" in bucket_frame.columns else int(len(bucket_frame.index))
        grouped_rows.append(
            {
                "bucket_name": str(bucket_name),
                "slice_count": slice_count,
                "row_count_total": int(pd.to_numeric(bucket_frame["row_count"], errors="coerce").sum()),
                "comparable_row_count_total": int(pd.to_numeric(bucket_frame["comparable_row_count"], errors="coerce").sum()),
                "current_label_vs_historical_excess_capital_error_total": error_total,
                "share_of_total_current_label_capital_error": error_total / total_error if total_error > 0.0 else 0.0,
                "current_shadow_vs_historical_excess_capital_mae_mean": float(pd.to_numeric(bucket_frame["current_shadow_vs_historical_excess_capital_mae"], errors="coerce").mean()),
                "historical_candidate_shadow_vs_historical_excess_capital_mae_mean": float(pd.to_numeric(bucket_frame["historical_candidate_shadow_vs_historical_excess_capital_mae"], errors="coerce").mean()),
                "candidate_shadow_capital_mae_improvement_mean": float(improvement.mean()),
                "positive_improvement_slice_count": positive_count,
                "positive_improvement_slice_share": positive_count / slice_count if slice_count else 0.0,
            }
        )
    return pd.DataFrame(grouped_rows, columns=columns).sort_values(
        ["current_label_vs_historical_excess_capital_error_total", "comparable_row_count_total", "bucket_name"],
        ascending=[False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def _build_target_mode_multi_slice_residual_frame(residual_records: list[dict[str, object]]) -> pd.DataFrame:
    if not residual_records:
        return pd.DataFrame()
    frame = pd.DataFrame(residual_records)
    sort_columns = [
        column_name
        for column_name in (
            "trainer_vs_historical_excess_capital_gap_abs",
            "current_shadow_historical_capital_error_abs",
            "candidate_shadow_capital_error_improvement",
        )
        if column_name in frame.columns
    ]
    for column_name in sort_columns:
        frame[column_name] = pd.to_numeric(frame[column_name], errors="coerce")
    if sort_columns:
        frame = frame.sort_values(sort_columns, ascending=[False] * len(sort_columns), kind="mergesort")
    return frame.head(_TARGET_MODE_MULTI_SLICE_RESIDUAL_ROW_LIMIT).reset_index(drop=True)


def _policy_bucket_ranking_row(
    *,
    bucket_name: str,
    bucket_rows: pd.DataFrame,
    overall_policy_adjusted_capital_mae: float,
) -> dict[str, object]:
    row_count = int(len(bucket_rows.index))
    raw_excess_capital_mae = float(_metric_series(bucket_rows, "raw_excess_capital_abs_error").mean()) if row_count else 0.0
    calibrated_excess_capital_mae = float(_metric_series(bucket_rows, "calibrated_excess_capital_abs_error").mean()) if row_count else 0.0
    policy_adjusted_excess_capital_mae = float(_metric_series(bucket_rows, "policy_adjusted_excess_capital_abs_error").mean()) if row_count else 0.0
    improvement_amount = calibrated_excess_capital_mae - policy_adjusted_excess_capital_mae
    improvement_percent = None
    if calibrated_excess_capital_mae > 0.0:
        improvement_percent = (improvement_amount / calibrated_excess_capital_mae) * 100.0
    top_policy_reason = "no_policy_adjustment"
    if row_count:
        top_reason_counts = (
            bucket_rows.loc[
                bucket_rows["policy_adjustment_reason"].astype(str).ne("no_policy_adjustment"),
                "policy_adjustment_reason",
            ]
            .astype(str)
            .value_counts(dropna=False)
        )
        if not top_reason_counts.empty:
            top_policy_reason = str(top_reason_counts.index[0])
    still_materially_bad_after_policy = bool(
        row_count >= _POLICY_BUCKET_BAD_MIN_ROWS
        and overall_policy_adjusted_capital_mae > 0.0
        and policy_adjusted_excess_capital_mae >= (overall_policy_adjusted_capital_mae * _POLICY_BUCKET_BAD_RELATIVE_THRESHOLD)
    )
    return {
        "bucket_name": bucket_name,
        "row_count": row_count,
        "raw_excess_capital_mae": raw_excess_capital_mae,
        "calibrated_excess_capital_mae": calibrated_excess_capital_mae,
        "policy_adjusted_excess_capital_mae": policy_adjusted_excess_capital_mae,
        "improvement_amount": improvement_amount,
        "improvement_percent": improvement_percent,
        "top_policy_reason": top_policy_reason,
        "still_materially_bad_after_policy": still_materially_bad_after_policy,
    }


def _policy_replay_bucket_ranking_row(
    *,
    bucket_name: str,
    bucket_rows: pd.DataFrame,
    overall_replay_policy_excess_capital_mean: float,
    overall_historical_excess_capital_total: float,
) -> dict[str, object]:
    measured_rows = _policy_replay_measured_rows(bucket_rows)
    metric_block = _policy_replay_metric_block(bucket_rows)
    row_count = int(metric_block["row_count"])
    share_of_total_historical_excess_capital = 0.0
    if overall_historical_excess_capital_total > 0.0:
        share_of_total_historical_excess_capital = (
            float(metric_block["historical_excess_capital_total"]) / overall_historical_excess_capital_total
        )
    top_policy_reason = "no_policy_adjustment"
    if not measured_rows.empty:
        top_reason_counts = (
            measured_rows.loc[
                measured_rows["policy_adjustment_reason"].astype(str).ne("no_policy_adjustment"),
                "policy_adjustment_reason",
            ]
            .astype(str)
            .value_counts(dropna=False)
        )
        if not top_reason_counts.empty:
            top_policy_reason = str(top_reason_counts.index[0])
    materially_bad_flag = bool(
        row_count >= _POLICY_BUCKET_BAD_MIN_ROWS
        and overall_replay_policy_excess_capital_mean > 0.0
        and float(metric_block["replay_policy_excess_capital_mean"])
        >= (overall_replay_policy_excess_capital_mean * _POLICY_BUCKET_BAD_RELATIVE_THRESHOLD)
    )
    return {
        "bucket_name": bucket_name,
        "row_count": row_count,
        "historical_excess_units_mean": float(metric_block["historical_excess_units_mean"]),
        "historical_excess_capital_mean": float(metric_block["historical_excess_capital_mean"]),
        "replay_policy_excess_units_mean": float(metric_block["replay_policy_excess_units_mean"]),
        "replay_policy_excess_capital_mean": float(metric_block["replay_policy_excess_capital_mean"]),
        "replay_units_removed_total": float(metric_block["replay_units_removed_total"]),
        "replay_capital_removed_total": float(metric_block["replay_capital_removed_total"]),
        "share_of_total_historical_excess_capital": float(share_of_total_historical_excess_capital),
        "top_policy_reason": top_policy_reason,
        "materially_bad_flag": materially_bad_flag,
    }


def _build_worst_bucket_residual_frame(
    rows: pd.DataFrame,
    *,
    bucket_frame: pd.DataFrame,
    worst_bucket_name: str | None,
) -> pd.DataFrame:
    columns = [
        "bucket_name",
        "promotion_row_key",
        "store_number",
        "sku_number",
        "split_name",
        "policy_adjusted_excess_capital_abs_error",
        "calibrated_excess_capital_abs_error",
        "raw_excess_capital_abs_error",
        "policy_fired_flag",
        "policy_adjustment_reason",
        "review_override_flag",
        "same_discount_history_available_flag",
        "elasticity_confidence_score",
        "uplift_confidence_score",
        "base_trend_state",
        "launch_vs_total_conflict_score",
        "stock_vs_supported_gap_units",
    ]
    if worst_bucket_name is None or worst_bucket_name not in bucket_frame.columns:
        return pd.DataFrame(columns=columns)

    bucket_rows = rows.loc[bucket_frame[worst_bucket_name]].copy()
    if bucket_rows.empty:
        return pd.DataFrame(columns=columns)

    residual_frame = pd.DataFrame(
        {
            "bucket_name": worst_bucket_name,
            "promotion_row_key": bucket_rows.get("promotion_row_key", pd.Series("", index=bucket_rows.index)).astype(str),
            "store_number": bucket_rows.get("store_number", pd.Series("", index=bucket_rows.index)).astype(str),
            "sku_number": bucket_rows.get("sku_number", pd.Series("", index=bucket_rows.index)).astype(str),
            "split_name": bucket_rows.get("split_name", pd.Series("", index=bucket_rows.index)).astype(str),
            "policy_adjusted_excess_capital_abs_error": _metric_series(bucket_rows, "policy_adjusted_excess_capital_abs_error"),
            "calibrated_excess_capital_abs_error": _metric_series(bucket_rows, "calibrated_excess_capital_abs_error"),
            "raw_excess_capital_abs_error": _metric_series(bucket_rows, "raw_excess_capital_abs_error"),
            "policy_fired_flag": _metric_series(bucket_rows, "policy_adjustment_fired_flag"),
            "policy_adjustment_reason": bucket_rows.get(
                "policy_adjustment_reason",
                pd.Series("no_policy_adjustment", index=bucket_rows.index),
            ).astype(str),
            "review_override_flag": _metric_series(bucket_rows, "review_override_flag"),
            "same_discount_history_available_flag": _metric_series(bucket_rows, "same_discount_history_available_flag"),
            "elasticity_confidence_score": _metric_series(bucket_rows, "elasticity_confidence_score"),
            "uplift_confidence_score": _metric_series(bucket_rows, "uplift_confidence_score"),
            "base_trend_state": bucket_rows.get(
                "base_demand_growth_bucket",
                pd.Series("UNKNOWN", index=bucket_rows.index),
            ).astype(str),
            "launch_vs_total_conflict_score": _metric_series(bucket_rows, "launch_vs_total_conflict_score"),
            "stock_vs_supported_gap_units": _metric_series(bucket_rows, "stock_vs_supported_gap_units"),
        },
        index=bucket_rows.index,
    )
    residual_frame = residual_frame.sort_values(
        ["policy_adjusted_excess_capital_abs_error", "calibrated_excess_capital_abs_error", "raw_excess_capital_abs_error"],
        ascending=[False, False, False],
        kind="mergesort",
    ).head(_POLICY_RESIDUAL_ROW_LIMIT)
    return residual_frame.reset_index(drop=True)


def _build_policy_replay_worst_bucket_residual_frame(
    rows: pd.DataFrame,
    *,
    bucket_frame: pd.DataFrame,
    worst_bucket_name: str | None,
) -> pd.DataFrame:
    columns = [
        "bucket_name",
        "promotion_row_key",
        "store_number",
        "sku_number",
        "split_name",
        "historical_allocation_source_column",
        "realised_units_source_column",
        "replay_unit_cost_source_column",
        "historical_allocated_units",
        "realised_units_sold_promo",
        "historical_excess_units",
        "historical_excess_capital",
        "replay_policy_units",
        "replay_policy_excess_units",
        "replay_policy_excess_capital",
        "replay_units_removed",
        "replay_capital_removed",
        "policy_fired_flag",
        "policy_adjustment_reason",
        "review_override_flag",
        "stock_vs_supported_gap_units",
    ]
    if worst_bucket_name is None or worst_bucket_name not in bucket_frame.columns:
        return pd.DataFrame(columns=columns)

    bucket_rows = _policy_replay_measured_rows(rows.loc[bucket_frame[worst_bucket_name]])
    if bucket_rows.empty:
        return pd.DataFrame(columns=columns)

    residual_frame = pd.DataFrame(
        {
            "bucket_name": worst_bucket_name,
            "promotion_row_key": bucket_rows.get("promotion_row_key", pd.Series("", index=bucket_rows.index)).astype(str),
            "store_number": bucket_rows.get("store_number", pd.Series("", index=bucket_rows.index)).astype(str),
            "sku_number": bucket_rows.get("sku_number", pd.Series("", index=bucket_rows.index)).astype(str),
            "split_name": bucket_rows.get("split_name", pd.Series("", index=bucket_rows.index)).astype(str),
            "historical_allocation_source_column": bucket_rows.get(
                "historical_allocation_source_column",
                pd.Series("", index=bucket_rows.index),
            ).astype(str),
            "realised_units_source_column": bucket_rows.get(
                "realised_units_source_column",
                pd.Series("", index=bucket_rows.index),
            ).astype(str),
            "replay_unit_cost_source_column": bucket_rows.get(
                "replay_unit_cost_source_column",
                pd.Series("", index=bucket_rows.index),
            ).astype(str),
            "historical_allocated_units": _metric_series(bucket_rows, "historical_allocated_units"),
            "realised_units_sold_promo": _metric_series(bucket_rows, "realised_units_sold_promo"),
            "historical_excess_units": _metric_series(bucket_rows, "historical_excess_units"),
            "historical_excess_capital": _metric_series(bucket_rows, "historical_excess_capital"),
            "replay_policy_units": _metric_series(bucket_rows, "replay_policy_units"),
            "replay_policy_excess_units": _metric_series(bucket_rows, "replay_policy_excess_units"),
            "replay_policy_excess_capital": _metric_series(bucket_rows, "replay_policy_excess_capital"),
            "replay_units_removed": _metric_series(bucket_rows, "replay_units_removed"),
            "replay_capital_removed": _metric_series(bucket_rows, "replay_capital_removed"),
            "policy_fired_flag": _metric_series(bucket_rows, "policy_adjustment_fired_flag"),
            "policy_adjustment_reason": bucket_rows.get(
                "policy_adjustment_reason",
                pd.Series("no_policy_adjustment", index=bucket_rows.index),
            ).astype(str),
            "review_override_flag": _metric_series(bucket_rows, "review_override_flag"),
            "stock_vs_supported_gap_units": _metric_series(bucket_rows, "stock_vs_supported_gap_units"),
        },
        index=bucket_rows.index,
    )
    residual_frame = residual_frame.sort_values(
        ["replay_policy_excess_capital", "historical_excess_capital", "replay_capital_removed"],
        ascending=[False, False, False],
        kind="mergesort",
    ).head(_POLICY_RESIDUAL_ROW_LIMIT)
    return residual_frame.reset_index(drop=True)


def _allocation_calibration_metrics(
    prefix: str,
    *,
    probability: pd.Series,
    target: pd.Series,
) -> dict[str, float]:
    metrics: dict[str, float] = {}
    bands = (
        ("0_25", 0.0, 0.25),
        ("25_50", 0.25, 0.5),
        ("50_75", 0.5, 0.75),
        ("75_100", 0.75, 1.0000001),
    )
    for label, lower_bound, upper_bound in bands:
        mask = probability.ge(lower_bound) & probability.lt(upper_bound)
        row_count = int(mask.sum())
        key_prefix = f"{prefix}_overallocation_calibration_{label}"
        metrics[f"{key_prefix}_row_count"] = float(row_count)
        metrics[f"{key_prefix}_predicted_rate"] = float(probability.loc[mask].mean()) if row_count else 0.0
        metrics[f"{key_prefix}_observed_rate"] = float(target.loc[mask].mean()) if row_count else 0.0
    return metrics


def _empty_allocation_calibration_metrics(prefix: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for label in ("0_25", "25_50", "50_75", "75_100"):
        key_prefix = f"{prefix}_overallocation_calibration_{label}"
        metrics[f"{key_prefix}_row_count"] = 0.0
        metrics[f"{key_prefix}_predicted_rate"] = 0.0
        metrics[f"{key_prefix}_observed_rate"] = 0.0
    return metrics


def _metric_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0)


def _optional_metric_series(
    frame: pd.DataFrame,
    column_name: str,
    *,
    fallback: pd.Series | None = None,
) -> pd.Series:
    if column_name not in frame.columns:
        if fallback is None:
            return pd.Series(pd.NA, index=frame.index, dtype="Float64")
        return pd.to_numeric(fallback, errors="coerce").astype("Float64")
    return pd.to_numeric(frame[column_name], errors="coerce").astype("Float64")