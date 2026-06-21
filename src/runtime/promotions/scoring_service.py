from __future__ import annotations

"""Reusable scoring service for future promotions.

Canon ownership:
- Loads the persisted promotions model family, engineers the same feature set for
  future advice rows, validates inference-schema compatibility, scores each
  promotion x sku x store row, and persists row-level plus aggregated outputs.
- Keeps recommendation flags explicit and auditable at the scoring boundary.
- Does not own extraction, model fitting, or report formatting policy.
"""

from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path

import joblib
import pandas as pd

from models.promotions.allocation_calibration import apply_allocation_aware_units_cap
from models.promotions.model_bundle import read_json
from models.promotions.order_policy_adjustments import build_order_policy_adjustments
from models.promotions.preprocessing import prepare_model_input_frame
from runtime.promotions.config import PromotionArtifactPaths
from runtime.promotions.decision_surface_service import (
    build_row_model_confidence_score,
    model_reliability_score_from_manifest,
)
from state.promotions.datasets.model_input_export import (
    write_model_input_audit_artifacts,
)
from state.promotions.feature_engineering.demand.ft_order_decision_diagnostics import (
    build_live_order_decision_diagnostics,
)
from state.promotions.feature_engineering.feature_pipeline import PromotionFeatureEngineer
from state.promotions.promotion_frame_schema import safe_ratio
from surfaces.promotions.reporting.aggregations import build_summary_tables


LOGGER = logging.getLogger(__name__)

_ROW_OUTPUT_LEGACY_COMPATIBILITY_COLUMNS: tuple[str, ...] = (
    "promo_gm_pct",
    "promo_days",
    "gmroi_8w",
    "sales_promo_period_avg",
    "required_implied_daily",
)


class PromotionScoringSchemaError(ValueError):
    """Raised when inference-time features do not match the trained model schema."""


@dataclass(frozen=True)
class PromotionScoringManifest:
    run_id: str
    model_run_id: str
    row_count: int
    input_feature_count: int
    row_predictions_path: str
    summary_paths: dict[str, str]
    diagnostic_paths: dict[str, str] | None = None
    derived_fields: dict[str, dict[str, object]] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionScoringArtifacts:
    row_frame: pd.DataFrame
    summary_frames: dict[str, pd.DataFrame]
    row_predictions_path: str
    summary_paths: dict[str, str]
    manifest_path: str
    diagnostic_paths: dict[str, str] | None = None


class PromotionModelScorer:
    """Score future promotions with the persisted reusable model family."""

    def __init__(self, *, feature_engineer: PromotionFeatureEngineer | None = None) -> None:
        self._feature_engineer = feature_engineer or PromotionFeatureEngineer()

    def score(
        self,
        *,
        run_id: str,
        model_run_id: str,
        future_base_frame: pd.DataFrame,
        historical_reference_frame: pd.DataFrame,
        artifact_paths: PromotionArtifactPaths,
    ) -> PromotionScoringArtifacts:
        """Engineer features, validate schema, score rows, and persist outputs."""

        model_root = artifact_paths.model_family_root(model_run_id)
        manifest = read_json(model_root / "run_manifest.json")
        inference_schema = read_json(model_root / "inference_schema.json")
        engineered_rows = self._feature_engineer.engineer(
            future_base_frame,
            historical_reference_frame=historical_reference_frame,
        ).frame
        expected_columns = tuple(str(column_name) for column_name in inference_schema["feature_columns"])
        engineered_rows = _project_legacy_inference_columns(
            engineered_rows,
            expected_columns=expected_columns,
        )
        engineered_feature_columns = tuple(
            column_name
            for column_name in expected_columns
            if str(column_name).startswith("feature_")
        )
        model_input, runtime_schema = prepare_model_input_frame(
            engineered_rows,
            feature_columns=engineered_feature_columns,
            preserve_columns=expected_columns,
        )
        model_input = _restore_expected_raw_inference_columns(
            model_input,
            projected_frame=engineered_rows,
            expected_columns=expected_columns,
        )
        missing_columns = [column_name for column_name in expected_columns if column_name not in model_input.columns]
        if missing_columns:
            raise PromotionScoringSchemaError(
                f"Scoring feature mismatch. Missing columns: {missing_columns}"
            )
        model_input = model_input.loc[:, expected_columns]
        # Governed model-input audit: write the EXACT frame handed to the model
        # for scoring, plus a 10k-row sample CSV with consistent 4dp rounding,
        # plus the feature-lineage and contract validation artifacts.
        write_model_input_audit_artifacts(
            run_id=run_id,
            stage_label="scoring",
            inspection_root=artifact_paths.inspection_run_root(run_id),
            model_input=model_input,
            feature_columns=expected_columns,
            target_columns=tuple(inference_schema.get("target_columns", ())),
            raw_columns=tuple(future_base_frame.columns),
            cleaned_columns=tuple(future_base_frame.columns),
            engineered_columns=tuple(engineered_rows.columns),
            source_artifact_path=str(model_root / "run_manifest.json"),
            quality_report=runtime_schema.quality_report,
        )
        if model_input.empty:
            scored_rows = _build_empty_scored_rows(
                engineered_rows,
                model_manifest=manifest,
            )
            raw_predicted_units_sold = scored_rows["raw_predicted_units_sold"]
            calibrated_predicted_units_sold = scored_rows["calibrated_predicted_units_sold"]
            allocation_decision_diagnostics = build_live_order_decision_diagnostics(
                scored_rows,
                raw_predicted_units=raw_predicted_units_sold,
                predicted_units=calibrated_predicted_units_sold,
            )
            policy_adjustments = build_order_policy_adjustments(
                scored_rows,
                raw_predicted_units=raw_predicted_units_sold,
                calibrated_predicted_units=calibrated_predicted_units_sold,
                diagnostics_frame=allocation_decision_diagnostics,
            )
            for column_name in policy_adjustments.columns:
                scored_rows[column_name] = policy_adjustments[column_name]
            scored_rows["policy_adjusted_predicted_units_sold"] = pd.to_numeric(
                policy_adjustments["adjusted_order_cap_units"],
                errors="coerce",
            ).fillna(0.0)
            # Phase 1 demand/order separation: predicted_units_sold is the demand
            # forecast (calibrated model output). Order caps live in
            # policy_adjusted_predicted_units_sold / adjusted_order_cap_units only.
            scored_rows["predicted_units_sold"] = scored_rows["calibrated_predicted_units_sold"]
            recommendation_frame = _build_recommendation_columns(scored_rows)
            scored_rows["recommendation_flag"] = recommendation_frame["recommendation_flag"]
            scored_rows["recommendation_reason"] = recommendation_frame["recommendation_reason"]
            allocation_decision_diagnostics = pd.concat(
                [allocation_decision_diagnostics, policy_adjustments],
                axis=1,
            )
            diagnostic_paths = _write_allocation_decision_diagnostics(
                run_id=run_id,
                diagnostics_frame=allocation_decision_diagnostics,
                artifact_paths=artifact_paths,
            )
            summary_frames = build_summary_tables(scored_rows)
            return _persist_scoring_artifacts(
                run_id=run_id,
                model_run_id=model_run_id,
                scored_rows=scored_rows,
                summary_frames=summary_frames,
                diagnostic_paths=diagnostic_paths,
                runtime_schema=runtime_schema,
                artifact_paths=artifact_paths,
            )
        units_model = joblib.load(manifest["artifact_files"]["units_gradient_boosting"])
        gross_profit_model = joblib.load(manifest["artifact_files"]["gross_profit_linear"])
        overallocation_model = joblib.load(manifest["artifact_files"]["overallocation_classifier"])
        underallocation_model = joblib.load(manifest["artifact_files"]["underallocation_classifier"])
        stockout_model = joblib.load(manifest["artifact_files"]["stockout_classifier"])
        scored_rows = engineered_rows.copy()
        raw_predicted_units_sold = pd.Series(
            units_model.predict(model_input),
            index=scored_rows.index,
        ).clip(lower=0.0)
        scored_rows["raw_predicted_units_sold"] = raw_predicted_units_sold
        calibrated_predicted_units_sold = apply_allocation_aware_units_cap(
            scored_rows,
            raw_predicted_units_sold,
        )
        allocation_decision_diagnostics = build_live_order_decision_diagnostics(
            scored_rows,
            raw_predicted_units=raw_predicted_units_sold,
            predicted_units=calibrated_predicted_units_sold,
        )
        policy_adjustments = build_order_policy_adjustments(
            scored_rows,
            raw_predicted_units=raw_predicted_units_sold,
            calibrated_predicted_units=calibrated_predicted_units_sold,
            diagnostics_frame=allocation_decision_diagnostics,
        )
        scored_rows["calibrated_predicted_units_sold"] = calibrated_predicted_units_sold
        scored_rows["policy_adjusted_predicted_units_sold"] = pd.to_numeric(
            policy_adjustments["adjusted_order_cap_units"],
            errors="coerce",
        ).fillna(0.0)
        # Phase 1 demand/order separation: demand forecast stays on the calibrated
        # path; order/risk caps remain in adjusted_order_cap_units and the
        # deprecated-compat alias policy_adjusted_predicted_units_sold.
        scored_rows["predicted_units_sold"] = scored_rows["calibrated_predicted_units_sold"]
        for column_name in policy_adjustments.columns:
            scored_rows[column_name] = policy_adjustments[column_name]
        # The model forecasts total promo-window units. First-day demand stays transparent and
        # governed by deriving it as an even daily allocation across the live promo window.
        promo_window_days = _promo_window_days_series(scored_rows)
        scored_rows["predicted_units_first_day"] = (
            scored_rows["predicted_units_sold"] / promo_window_days
        ).clip(lower=0.0)
        scored_rows["predicted_sales_ex_gst"] = (
            scored_rows["predicted_units_sold"]
            * scored_rows.get("promo_price_ex_gst_effective", pd.Series(0.0, index=scored_rows.index)).fillna(0.0)
        )
        scored_rows["predicted_gross_profit_dollars"] = gross_profit_model.predict(model_input)
        scored_rows["predicted_sell_through_pct"] = safe_ratio(
            scored_rows["predicted_units_sold"],
            scored_rows.get("stock_basis_units", pd.Series(0.0, index=scored_rows.index)).fillna(0.0),
        ).clip(lower=0.0, upper=1.0)
        scored_rows["predicted_overallocation_risk"] = overallocation_model.predict_proba(model_input)[:, 1]
        scored_rows["predicted_underallocation_risk"] = underallocation_model.predict_proba(model_input)[:, 1]
        scored_rows["predicted_stockout_risk"] = stockout_model.predict_proba(model_input)[:, 1]
        model_reliability_score = model_reliability_score_from_manifest(manifest)
        scored_rows["row_model_confidence_score"] = build_row_model_confidence_score(
            scored_rows,
            model_reliability_score=model_reliability_score,
        )
        recommendation_frame = _build_recommendation_columns(scored_rows)
        policy_review_mask = pd.to_numeric(
            policy_adjustments["review_override_flag"],
            errors="coerce",
        ).fillna(0.0).ge(1.0)
        policy_adjusted_mask = pd.to_numeric(
            policy_adjustments["policy_adjustment_fired_flag"],
            errors="coerce",
        ).fillna(0.0).ge(1.0)
        recommendation_frame.loc[policy_review_mask, "recommendation_flag"] = "review_policy"
        recommendation_frame.loc[policy_review_mask, "recommendation_reason"] = (
            "governed policy review override: "
            + policy_adjustments.loc[policy_review_mask, "review_override_reason"].astype(str)
            + "; adjustment="
            + policy_adjustments.loc[policy_review_mask, "policy_adjustment_reason"].astype(str)
        )
        recommendation_frame.loc[policy_adjusted_mask & ~policy_review_mask, "recommendation_reason"] = (
            recommendation_frame.loc[policy_adjusted_mask & ~policy_review_mask, "recommendation_reason"].astype(str)
            + "; governed policy cap: "
            + policy_adjustments.loc[policy_adjusted_mask & ~policy_review_mask, "policy_adjustment_reason"].astype(str)
        )
        scored_rows["recommendation_flag"] = recommendation_frame["recommendation_flag"]
        scored_rows["recommendation_reason"] = recommendation_frame["recommendation_reason"]
        allocation_decision_diagnostics = pd.concat(
            [allocation_decision_diagnostics, policy_adjustments],
            axis=1,
        )
        diagnostic_paths = _write_allocation_decision_diagnostics(
            run_id=run_id,
            diagnostics_frame=allocation_decision_diagnostics,
            artifact_paths=artifact_paths,
        )
        summary_frames = build_summary_tables(scored_rows)
        return _persist_scoring_artifacts(
            run_id=run_id,
            model_run_id=model_run_id,
            scored_rows=scored_rows,
            summary_frames=summary_frames,
            diagnostic_paths=diagnostic_paths,
            runtime_schema=runtime_schema,
            artifact_paths=artifact_paths,
        )


def _build_empty_scored_rows(
    engineered_rows: pd.DataFrame,
    *,
    model_manifest: dict[str, object],
) -> pd.DataFrame:
    scored_rows = engineered_rows.copy()
    empty_numeric = pd.Series(index=scored_rows.index, dtype="float64")
    for column_name in (
        "raw_predicted_units_sold",
        "calibrated_predicted_units_sold",
        "policy_adjusted_predicted_units_sold",
        "predicted_units_sold",
        "predicted_units_first_day",
        "predicted_sales_ex_gst",
        "predicted_gross_profit_dollars",
        "predicted_sell_through_pct",
        "predicted_overallocation_risk",
        "predicted_underallocation_risk",
        "predicted_stockout_risk",
    ):
        scored_rows[column_name] = empty_numeric
    scored_rows["row_model_confidence_score"] = build_row_model_confidence_score(
        scored_rows,
        model_reliability_score=model_reliability_score_from_manifest(model_manifest),
    )
    return scored_rows


def _persist_scoring_artifacts(
    *,
    run_id: str,
    model_run_id: str,
    scored_rows: pd.DataFrame,
    summary_frames: dict[str, pd.DataFrame],
    diagnostic_paths: dict[str, str],
    runtime_schema,
    artifact_paths: PromotionArtifactPaths,
) -> PromotionScoringArtifacts:
    summary_paths = _persist_outputs(
        run_id=run_id,
        row_frame=scored_rows,
        summary_frames=summary_frames,
        artifact_paths=artifact_paths,
    )
    row_predictions_path = artifact_paths.scoring_rows_path(run_id)
    manifest_path = artifact_paths.scoring_manifest_path(run_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            PromotionScoringManifest(
                run_id=run_id,
                model_run_id=model_run_id,
                row_count=len(scored_rows.index),
                input_feature_count=len(runtime_schema.feature_columns),
                row_predictions_path=str(row_predictions_path),
                summary_paths=summary_paths,
                diagnostic_paths=diagnostic_paths,
                derived_fields={
                    "predicted_units_first_day": {
                        "formula": "predicted_units_sold / max(live_promo_window_days or promo_days, 1)",
                        "source_columns": ["predicted_units_sold", "live_promo_window_days", "promo_days"],
                        "description": "Transparent first-day demand estimate derived from total predicted promo units and the live promo duration.",
                    }
                },
            ).to_dict(),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    LOGGER.info(
        "Scored promotions rows: model_run_id=%s scoring_run_id=%s rows=%s",
        model_run_id,
        run_id,
        len(scored_rows.index),
    )
    return PromotionScoringArtifacts(
        row_frame=scored_rows,
        summary_frames=summary_frames,
        row_predictions_path=str(row_predictions_path),
        summary_paths=summary_paths,
        manifest_path=str(manifest_path),
        diagnostic_paths=diagnostic_paths,
    )


def _write_allocation_decision_diagnostics(
    *,
    run_id: str,
    diagnostics_frame: pd.DataFrame,
    artifact_paths: PromotionArtifactPaths,
) -> dict[str, str]:
    diagnostics_csv_path = artifact_paths.scoring_allocation_decision_diagnostics_csv_path(run_id)
    diagnostics_json_path = artifact_paths.scoring_allocation_decision_diagnostics_json_path(run_id)
    diagnostics_csv_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_json_path.parent.mkdir(parents=True, exist_ok=True)

    diagnostics_frame.to_csv(diagnostics_csv_path, index=False)
    diagnostics_payload = {
        "run_id": run_id,
        "row_count": int(len(diagnostics_frame.index)),
        "evidence_coverage_report": {
            "same_discount_present_row_count": int(diagnostics_frame["evidence_same_discount_present_flag"].sum()),
            "usable_elasticity_row_count": int(diagnostics_frame["evidence_usable_elasticity_flag"].sum()),
            "strong_uplift_support_row_count": int(diagnostics_frame["evidence_strong_uplift_support_flag"].sum()),
            "probability_model_use_row_count": int(diagnostics_frame["evidence_probability_model_use_flag"].sum()),
            "weak_fallback_logic_row_count": int(diagnostics_frame["weak_fallback_logic_flag"].sum()),
        },
        "order_sizing_driver_counts": {
            str(driver_name): int(count)
            for driver_name, count in diagnostics_frame["order_sizing_driver"].astype(str).value_counts(dropna=False).to_dict().items()
        },
        "order_cap_reason_counts": {
            str(reason): int(count)
            for reason, count in diagnostics_frame["order_cap_reason"].astype(str).value_counts(dropna=False).to_dict().items()
        },
        "evidence_conflict_review_candidate_row_count": int(
            diagnostics_frame["evidence_conflict_review_candidate_flag"].sum()
        ),
        "policy_adjustment_summary": {
            "policy_adjusted_row_count": int(pd.to_numeric(diagnostics_frame["policy_adjustment_fired_flag"], errors="coerce").sum()),
            "policy_forced_review_row_count": int(pd.to_numeric(diagnostics_frame["review_override_flag"], errors="coerce").sum()),
            "total_units_removed_by_policy": float(pd.to_numeric(diagnostics_frame["policy_units_removed"], errors="coerce").sum()),
            "total_capital_at_risk_removed_by_policy": float(pd.to_numeric(diagnostics_frame["policy_capital_at_risk_removed"], errors="coerce").sum()),
            "policy_adjustment_reason_counts": {
                str(reason_name): int(count)
                for reason_name, count in diagnostics_frame.loc[
                    diagnostics_frame["policy_adjustment_reason"].astype(str).ne("no_policy_adjustment"),
                    "policy_adjustment_reason",
                ].astype(str).value_counts(dropna=False).to_dict().items()
            },
            "review_override_reason_counts": {
                str(reason_name): int(count)
                for reason_name, count in diagnostics_frame.loc[
                    diagnostics_frame["review_override_reason"].astype(str).ne("no_review_override"),
                    "review_override_reason",
                ].astype(str).value_counts(dropna=False).to_dict().items()
            },
        },
    }
    diagnostics_json_path.write_text(
        json.dumps(diagnostics_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "allocation_decision_diagnostics_csv_path": str(diagnostics_csv_path),
        "allocation_decision_diagnostics_json_path": str(diagnostics_json_path),
    }


def _project_legacy_inference_columns(
    frame: pd.DataFrame,
    *,
    expected_columns: tuple[str, ...],
) -> pd.DataFrame:
    expected_column_set = set(expected_columns)
    projection_column_set = expected_column_set.union(_ROW_OUTPUT_LEGACY_COMPATIBILITY_COLUMNS)
    projected = frame.copy()

    if "promo_days" in projection_column_set and "promo_days" not in projected.columns:
        promo_days = _first_numeric_column(projected, ("live_promo_window_days",))
        if promo_days is not None:
            projected["promo_days"] = promo_days

    if "promo_gm_pct" in projection_column_set and "promo_gm_pct" not in projected.columns:
        promo_gm_unit = _numeric_column(projected, "promo_gm_unit")
        promo_price = _first_numeric_column(
            projected,
            ("promo_price_ex_gst_effective", "promo_price_ex_gst", "promo_price"),
        )
        if promo_gm_unit is not None and promo_price is not None:
            projected["promo_gm_pct"] = safe_ratio(promo_gm_unit, promo_price)

    if "sales_promo_period_avg" in projection_column_set and "sales_promo_period_avg" not in projected.columns:
        average_units = _first_numeric_column(
            projected,
            ("avg_8_wk_unit_sales", "pre_56d_units"),
        )
        promo_price = _first_numeric_column(
            projected,
            ("promo_price_ex_gst_effective", "promo_price_ex_gst", "promo_price"),
        )
        if average_units is not None and promo_price is not None:
            projected["sales_promo_period_avg"] = average_units * promo_price

    if "gmroi_8w" in projection_column_set and "gmroi_8w" not in projected.columns:
        gross_profit = _first_numeric_column(projected, ("gross_profit_promo_dollars",))
        if gross_profit is None:
            promo_gm_unit = _numeric_column(projected, "promo_gm_unit")
            average_units = _first_numeric_column(projected, ("avg_8_wk_unit_sales", "pre_56d_units"))
            if promo_gm_unit is not None and average_units is not None:
                gross_profit = promo_gm_unit * average_units
        inventory_cost = _first_numeric_column(projected, ("pl_extended_cost",))
        if inventory_cost is None:
            stock_basis = _numeric_column(projected, "stock_basis_units")
            unit_cost = _first_numeric_column(
                projected,
                ("promo_effective_cost", "promo_cost_price", "last_received_cost"),
            )
            if stock_basis is not None and unit_cost is not None:
                inventory_cost = stock_basis * unit_cost
        if gross_profit is not None and inventory_cost is not None:
            projected["gmroi_8w"] = safe_ratio(gross_profit, inventory_cost)

    if "required_implied_daily" in projection_column_set and "required_implied_daily" not in projected.columns:
        required_units = _numeric_column(projected, "required_implied_units")
        promo_days = _first_numeric_column(projected, ("promo_days", "live_promo_window_days"))
        if required_units is not None and promo_days is not None:
            projected["required_implied_daily"] = safe_ratio(required_units, promo_days)

    return projected


def _restore_expected_raw_inference_columns(
    model_input: pd.DataFrame,
    *,
    projected_frame: pd.DataFrame,
    expected_columns: tuple[str, ...],
) -> pd.DataFrame:
    restored = model_input.copy()
    for column_name in expected_columns:
        if column_name.startswith("feature_") or column_name in restored.columns:
            continue
        if column_name in projected_frame.columns:
            restored[column_name] = pd.to_numeric(projected_frame[column_name], errors="coerce").fillna(0.0)
    return restored


def _numeric_column(frame: pd.DataFrame, column_name: str) -> pd.Series | None:
    if column_name not in frame.columns:
        return None
    return pd.to_numeric(frame[column_name], errors="coerce")


def _first_numeric_column(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
) -> pd.Series | None:
    for column_name in column_names:
        series = _numeric_column(frame, column_name)
        if series is not None:
            return series
    return None


def _promo_window_days_series(frame: pd.DataFrame) -> pd.Series:
    raw_days = frame.get("live_promo_window_days")
    if raw_days is None:
        raw_days = frame.get("promo_days", pd.Series(1.0, index=frame.index))
    return pd.to_numeric(raw_days, errors="coerce").replace(0.0, pd.NA).fillna(1.0)


def _persist_outputs(
    *,
    run_id: str,
    row_frame: pd.DataFrame,
    summary_frames: dict[str, pd.DataFrame],
    artifact_paths: PromotionArtifactPaths,
) -> dict[str, str]:
    row_path = artifact_paths.scoring_rows_path(run_id)
    row_path.parent.mkdir(parents=True, exist_ok=True)
    row_frame.to_parquet(row_path, index=False)
    summary_paths: dict[str, str] = {}
    for summary_name, summary_frame in summary_frames.items():
        summary_path = row_path.parent / f"{summary_name}.parquet"
        summary_frame.to_parquet(summary_path, index=False)
        summary_paths[summary_name] = str(summary_path)
    return summary_paths


def _build_recommendation_columns(frame: pd.DataFrame) -> pd.DataFrame:
    recommendation_flag = []
    recommendation_reason = []
    for row in frame.itertuples(index=False):
        reasons: list[str] = []
        flag = "support"
        if row.predicted_gross_profit_dollars <= 0:
            flag = "review_margin"
            reasons.append("predicted gross profit is non-positive")
        if row.predicted_overallocation_risk >= 0.6:
            flag = "reduce_allocation"
            reasons.append("overallocation risk is elevated")
        if row.predicted_underallocation_risk >= 0.6 or row.predicted_stockout_risk >= 0.6:
            flag = "increase_allocation"
            reasons.append("underallocation or stockout risk is elevated")
        if not reasons:
            reasons.append("predicted sell-through and margin remain acceptable")
        recommendation_flag.append(flag)
        recommendation_reason.append("; ".join(reasons))
    return pd.DataFrame(
        {
            "recommendation_flag": recommendation_flag,
            "recommendation_reason": recommendation_reason,
        },
        index=frame.index,
    )
