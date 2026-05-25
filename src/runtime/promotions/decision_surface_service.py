from __future__ import annotations

"""Runtime-side helpers for governed promotions decision-surface execution.

Canon ownership:
- Loads persisted training-ready artifacts and their adjacent manifests.
- Scores an already-assembled dataset directly from a persisted promotions model
  bundle without re-running feature engineering.
- Surfaces schema mismatches and missing runtime inputs loudly at the boundary so
  later decision-fusion and reporting layers do not operate on ambiguous state.
- Does not own cohort logic, decision fusion, diagnostics policy, or reporting
  table formatting.
"""

from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd

from models.promotions.model_bundle import read_json
from models.promotions.preprocessing import prepare_model_input_frame
from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.promotion_frame_schema import safe_ratio


class PromotionDecisionSurfaceArtifactError(FileNotFoundError):
    """Raised when a required decision-surface runtime artifact is missing."""


class PromotionDecisionSurfaceSchemaError(ValueError):
    """Raised when a training-ready artifact does not match the model schema."""


@dataclass(frozen=True)
class PromotionTrainingReadyArtifact:
    frame: pd.DataFrame
    dataset_path: str
    dataset_manifest_path: str | None
    dataset_manifest: dict[str, object] | None


@dataclass(frozen=True)
class PromotionDecisionSurfaceRowModelArtifacts:
    scored_frame: pd.DataFrame
    model_bundle_path: str
    model_manifest_path: str
    inference_schema_path: str
    model_reliability_score: float
    feature_column_count: int


def load_training_ready_artifact(dataset_path: str | Path) -> PromotionTrainingReadyArtifact:
    """Load a persisted training-ready dataset plus its governed manifest if present."""

    resolved_dataset_path = Path(dataset_path)
    if not resolved_dataset_path.exists():
        raise PromotionDecisionSurfaceArtifactError(
            f"Missing training-ready promotions dataset artifact: {resolved_dataset_path}"
        )
    frame = pd.read_parquet(resolved_dataset_path)
    dataset_manifest_path = _resolve_dataset_manifest_path(resolved_dataset_path)
    dataset_manifest = None
    if dataset_manifest_path.exists():
        dataset_manifest = read_json(dataset_manifest_path)
    return PromotionTrainingReadyArtifact(
        frame=frame,
        dataset_path=str(resolved_dataset_path),
        dataset_manifest_path=str(dataset_manifest_path) if dataset_manifest_path.exists() else None,
        dataset_manifest=dataset_manifest,
    )


def _resolve_dataset_manifest_path(dataset_path: Path) -> Path:
    run_id = dataset_path.parent.name
    governed_manifest_path: Path | None = None
    if len(dataset_path.parents) >= 4:
        datasets_root = dataset_path.parents[1]
        training_root = dataset_path.parents[2]
        artifact_root = dataset_path.parents[3]
        if datasets_root.name == "datasets" and training_root.name == "training":
            governed_manifest_path = PromotionArtifactPaths(root=artifact_root).dataset_manifest_path(run_id)
    if governed_manifest_path is not None and governed_manifest_path.exists():
        return governed_manifest_path
    return dataset_path.with_name("dataset_manifest.json")


def score_training_ready_rows(
    frame: pd.DataFrame,
    *,
    model_bundle_path: str | Path,
) -> PromotionDecisionSurfaceRowModelArtifacts:
    """Score a persisted training-ready dataset directly from a trained model bundle."""

    model_root = Path(model_bundle_path)
    manifest_path = model_root / "run_manifest.json"
    inference_schema_path = model_root / "inference_schema.json"
    if not model_root.exists():
        raise PromotionDecisionSurfaceArtifactError(
            f"Missing promotions model bundle path: {model_root}"
        )
    if not manifest_path.exists() or not inference_schema_path.exists():
        raise PromotionDecisionSurfaceArtifactError(
            "Promotions model bundle is incomplete. Expected run_manifest.json and inference_schema.json."
        )
    manifest = read_json(manifest_path)
    inference_schema = read_json(inference_schema_path)
    expected_feature_columns = tuple(str(column_name) for column_name in inference_schema["feature_columns"])
    model_input, runtime_schema = prepare_model_input_frame(
        frame,
        feature_columns=tuple(
            column_name
            for column_name in expected_feature_columns
            if str(column_name).startswith("feature_")
        ),
        preserve_columns=expected_feature_columns,
    )
    missing_columns = [column_name for column_name in expected_feature_columns if column_name not in model_input.columns]
    if missing_columns:
        raise PromotionDecisionSurfaceSchemaError(
            f"Decision-surface model schema mismatch. Missing columns: {missing_columns}"
        )
    model_input = model_input.loc[:, expected_feature_columns]
    scored_rows = frame.copy()
    units_model = joblib.load(manifest["artifact_files"]["units_gradient_boosting"])
    gross_profit_model = joblib.load(manifest["artifact_files"]["gross_profit_linear"])
    overallocation_model = joblib.load(manifest["artifact_files"]["overallocation_classifier"])
    underallocation_model = joblib.load(manifest["artifact_files"]["underallocation_classifier"])
    stockout_model = joblib.load(manifest["artifact_files"]["stockout_classifier"])
    scored_rows["predicted_units_sold"] = pd.Series(
        units_model.predict(model_input),
        index=scored_rows.index,
    ).clip(lower=0.0)
    scored_rows["predicted_sales_ex_gst"] = (
        scored_rows["predicted_units_sold"]
        * scored_rows.get(
            "promo_price_ex_gst_effective",
            pd.Series(0.0, index=scored_rows.index, dtype="float64"),
        ).fillna(0.0)
    )
    scored_rows["predicted_gross_profit_dollars"] = pd.Series(
        gross_profit_model.predict(model_input),
        index=scored_rows.index,
    )
    scored_rows["predicted_sell_through_pct"] = safe_ratio(
        scored_rows["predicted_units_sold"],
        scored_rows.get(
            "stock_basis_units",
            pd.Series(0.0, index=scored_rows.index, dtype="float64"),
        ).fillna(0.0),
    ).clip(lower=0.0, upper=1.0)
    scored_rows["predicted_overallocation_risk"] = overallocation_model.predict_proba(model_input)[:, 1]
    scored_rows["predicted_underallocation_risk"] = underallocation_model.predict_proba(model_input)[:, 1]
    scored_rows["predicted_stockout_risk"] = stockout_model.predict_proba(model_input)[:, 1]
    model_reliability_score = _model_reliability_score(manifest)
    scored_rows["row_model_confidence_score"] = _row_model_confidence_score(
        scored_rows,
        model_reliability_score=model_reliability_score,
    )
    return PromotionDecisionSurfaceRowModelArtifacts(
        scored_frame=scored_rows,
        model_bundle_path=str(model_root),
        model_manifest_path=str(manifest_path),
        inference_schema_path=str(inference_schema_path),
        model_reliability_score=model_reliability_score,
        feature_column_count=len(runtime_schema.feature_columns),
    )


def model_reliability_score_from_manifest(manifest: dict[str, object]) -> float:
    return _model_reliability_score(manifest)


def build_row_model_confidence_score(
    frame: pd.DataFrame,
    *,
    model_reliability_score: float,
) -> pd.Series:
    return _row_model_confidence_score(
        frame,
        model_reliability_score=model_reliability_score,
    )


def empty_cohort_match_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a default cohort-match payload for rows with no usable history."""

    return pd.DataFrame(
        {
            "promotion_row_key": frame["promotion_row_key"],
            "nearest_archetype_key": "",
            "nearest_archetype_family": "",
            "nearest_archetype_similarity": 0.0,
            "nearest_archetype_sample_size": 0,
            "nearest_archetype_expected_units": float("nan"),
            "nearest_archetype_expected_sales_ex_gst": float("nan"),
            "nearest_archetype_expected_sell_through": float("nan"),
            "nearest_archetype_expected_leftover": float("nan"),
            "nearest_archetype_expected_gp": float("nan"),
            "nearest_archetype_expected_uplift": float("nan"),
            "nearest_archetype_expected_stockout_rate": float("nan"),
            "nearest_archetype_expected_overallocation_rate": float("nan"),
            "nearest_archetype_expected_underallocation_rate": float("nan"),
            "cohort_coverage_flag": 0,
            "sparse_cohort_flag": 1,
        },
        index=frame.index,
    )


def _model_reliability_score(manifest: dict[str, object]) -> float:
    metrics_path = Path(str(manifest.get("metrics_path", "") or ""))
    if not metrics_path.exists():
        return 0.5
    metrics = read_json(metrics_path)
    regression_scores = []
    for metric_name in ("units_gradient_boosting", "gross_profit_linear"):
        model_metrics = metrics.get(metric_name, {})
        if not isinstance(model_metrics, dict):
            continue
        regression_scores.append(
            max(
                0.0,
                min(
                    1.0,
                    (
                        float(model_metrics.get("validation_r2", 0.0) or 0.0)
                        + float(model_metrics.get("test_r2", 0.0) or 0.0)
                    )
                    / 2.0,
                ),
            )
        )
    classifier_scores = []
    for metric_name in (
        "overallocation_classifier",
        "underallocation_classifier",
        "stockout_classifier",
    ):
        model_metrics = metrics.get(metric_name, {})
        if not isinstance(model_metrics, dict):
            continue
        roc_auc = float(model_metrics.get("test_roc_auc", 0.5) or 0.5)
        brier = float(model_metrics.get("test_brier", 0.25) or 0.25)
        classifier_scores.append(max(0.0, min(1.0, 0.7 * roc_auc + 0.3 * (1.0 - brier))))
    component_scores = [*regression_scores, *classifier_scores]
    if not component_scores:
        return 0.5
    return float(sum(component_scores) / len(component_scores))


def _row_model_confidence_score(
    frame: pd.DataFrame,
    *,
    model_reliability_score: float,
) -> pd.Series:
    classifier_certainty = (
        (
            frame["predicted_overallocation_risk"].sub(0.5).abs()
            + frame["predicted_underallocation_risk"].sub(0.5).abs()
            + frame["predicted_stockout_risk"].sub(0.5).abs()
        )
        / 1.5
    ).clip(lower=0.0, upper=0.5) * 2.0
    sell_through_certainty = frame["predicted_sell_through_pct"].sub(0.5).abs().clip(lower=0.0, upper=0.5) * 2.0
    profit_ratio = (
        frame["predicted_gross_profit_dollars"].abs()
        / frame["predicted_sales_ex_gst"].abs().clip(lower=1.0)
    ).clip(lower=0.0, upper=1.0)
    return (
        float(model_reliability_score)
        * (
            0.60 * classifier_certainty
            + 0.25 * sell_through_certainty
            + 0.15 * profit_ratio
        )
    ).clip(lower=0.0, upper=1.0)