from __future__ import annotations

"""Diagnostics-only low-nonzero-demand specialist promotions models.

Canon ownership:
- Trains a conservative specialist regressor for rows whose demand profile is
  consistent with the governed `low_nonzero_demand` seam.
- Keeps the default slim units head unchanged by operating as a side-car
  diagnostics workflow with its own gated feature-family contract.
- Provides only diagnostics-owned publishability and calibration comparisons; it
  does not own Stage 11/12 policy movement or production model promotion.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from models.promotions.model_bundle import PromotionInferenceSchema, PromotionTrainingManifest, write_json
from models.promotions.model_input_quality import (
    _feature_family_for_column,
    _registered_feature_module_by_column,
    iter_downstream_decision_support_feature_columns,
    iter_units_head_core_feature_columns,
)
from models.promotions.preprocessing import prepare_model_input_frame


LOW_NONZERO_SPECIALIST_DEFAULT_FEATURE_FAMILIES: tuple[str, ...] = (
    "basket_structure_dependency",
    "sparse_demand_noise",
    "probability",
    "same_discount_promo_history",
)
LOW_NONZERO_SPECIALIST_ALLOWED_OPTIONAL_FAMILIES: tuple[str, ...] = (
    "target_stock_shape",
    "allocation_discipline",
    "micro_market_equilibrium",
    "basket_equilibrium",
    "other_engineered_feature",
)
LOW_NONZERO_SPECIALIST_MAX_UNITS = 1.0
LOW_NONZERO_SPECIALIST_LABEL_PUBLISH_NOW = "likely_publish_now"
LOW_NONZERO_SPECIALIST_LABEL_REVIEW = "likely_review"
LOW_NONZERO_SPECIALIST_LABEL_NO_ORDER = "likely_no_order"
LOW_NONZERO_SPECIALIST_LABELS: tuple[str, ...] = (
    LOW_NONZERO_SPECIALIST_LABEL_PUBLISH_NOW,
    LOW_NONZERO_SPECIALIST_LABEL_REVIEW,
    LOW_NONZERO_SPECIALIST_LABEL_NO_ORDER,
)


@dataclass(frozen=True)
class LowNonzeroSpecialistConfig:
    quantile_alpha: float = 0.35
    learning_rate: float = 0.05
    n_estimators: int = 300
    num_leaves: int = 31
    max_depth: int = 6
    min_child_samples: int = 20
    enabled_optional_families: tuple[str, ...] = ()
    multiclass_learning_rate: float = 0.05
    multiclass_n_estimators: int = 250


@dataclass(frozen=True)
class LowNonzeroSpecialistBundleArtifacts:
    bundle_root: str
    manifest_path: str
    inference_schema_path: str
    metrics_path: str
    feature_list_path: str
    artifact_files: dict[str, str]


@dataclass(frozen=True)
class LowNonzeroSpecialistClassifierDiagnostics:
    label_count: int
    train_row_count: int
    evaluation_row_count: int
    macro_f1: float | None
    accuracy: float | None
    class_counts: dict[str, int]
    label_source: str


class _ConstantBinaryProbabilityClassifier:
    def __init__(self, positive_probability: float) -> None:
        self.positive_probability = float(np.clip(positive_probability, 0.0, 1.0))

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        positive = np.full(len(features.index), self.positive_probability, dtype="float64")
        return np.column_stack([1.0 - positive, positive])


class _ConstantMulticlassClassifier:
    def __init__(self, classes: tuple[str, ...], dominant_label: str) -> None:
        self.classes_ = np.asarray(classes, dtype=object)
        self._dominant_label = dominant_label

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.full(len(features.index), self._dominant_label, dtype=object)

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        probabilities = np.zeros((len(features.index), len(self.classes_)), dtype="float64")
        dominant_index = int(np.where(self.classes_ == self._dominant_label)[0][0])
        probabilities[:, dominant_index] = 1.0
        return probabilities


def build_low_nonzero_mask(units: pd.Series) -> pd.Series:
    values = pd.to_numeric(units, errors="coerce").fillna(0.0)
    return values.gt(0.0) & values.le(LOW_NONZERO_SPECIALIST_MAX_UNITS)


def resolve_specialist_feature_columns(
    *,
    config: LowNonzeroSpecialistConfig | None = None,
) -> tuple[str, ...]:
    resolved_config = config or LowNonzeroSpecialistConfig()
    feature_columns = list(iter_units_head_core_feature_columns())
    optional_families = tuple(dict.fromkeys(str(name) for name in resolved_config.enabled_optional_families))
    unsupported = [
        family_name
        for family_name in optional_families
        if family_name not in LOW_NONZERO_SPECIALIST_ALLOWED_OPTIONAL_FAMILIES
    ]
    if unsupported:
        raise ValueError(
            "Unsupported low-nonzero specialist optional families: " + ", ".join(unsupported)
        )
    if not optional_families:
        return tuple(feature_columns)
    module_by_feature = _registered_feature_module_by_column()
    for column_name in iter_downstream_decision_support_feature_columns():
        family_name = _feature_family_for_column(column_name, module_by_feature.get(column_name, ""))
        if family_name in optional_families and column_name not in feature_columns:
            feature_columns.append(column_name)
    return tuple(feature_columns)


def specialist_feature_family_names(
    feature_columns: Sequence[str],
) -> tuple[str, ...]:
    module_by_feature = _registered_feature_module_by_column()
    family_names = []
    seen: set[str] = set()
    for column_name in feature_columns:
        family_name = _feature_family_for_column(str(column_name), module_by_feature.get(str(column_name), ""))
        if family_name in seen:
            continue
        seen.add(family_name)
        family_names.append(family_name)
    return tuple(family_names)


def build_specialist_model_input(
    frame: pd.DataFrame,
    *,
    config: LowNonzeroSpecialistConfig | None = None,
):
    feature_columns = resolve_specialist_feature_columns(config=config)
    return prepare_model_input_frame(frame, feature_columns=feature_columns)


def build_lightgbm_regressor(schema, config: LowNonzeroSpecialistConfig | None = None) -> Pipeline:
    resolved_config = config or LowNonzeroSpecialistConfig()
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
                LGBMRegressor(
                    objective="quantile",
                    alpha=resolved_config.quantile_alpha,
                    learning_rate=resolved_config.learning_rate,
                    n_estimators=resolved_config.n_estimators,
                    num_leaves=resolved_config.num_leaves,
                    max_depth=resolved_config.max_depth,
                    min_child_samples=resolved_config.min_child_samples,
                    random_state=42,
                    verbosity=-1,
                ),
            ),
        ]
    )


def build_lightgbm_binary_classifier(schema, config: LowNonzeroSpecialistConfig | None = None) -> Pipeline:
    resolved_config = config or LowNonzeroSpecialistConfig()
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
                LGBMClassifier(
                    objective="binary",
                    learning_rate=resolved_config.multiclass_learning_rate,
                    n_estimators=resolved_config.multiclass_n_estimators,
                    num_leaves=resolved_config.num_leaves,
                    max_depth=resolved_config.max_depth,
                    min_child_samples=resolved_config.min_child_samples,
                    random_state=42,
                    verbosity=-1,
                ),
            ),
        ]
    )


def build_lightgbm_multiclass_classifier(schema, config: LowNonzeroSpecialistConfig | None = None) -> Pipeline:
    resolved_config = config or LowNonzeroSpecialistConfig()
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
                LGBMClassifier(
                    objective="multiclass",
                    num_class=len(LOW_NONZERO_SPECIALIST_LABELS),
                    learning_rate=resolved_config.multiclass_learning_rate,
                    n_estimators=resolved_config.multiclass_n_estimators,
                    num_leaves=resolved_config.num_leaves,
                    max_depth=resolved_config.max_depth,
                    min_child_samples=resolved_config.min_child_samples,
                    random_state=42,
                    verbosity=-1,
                ),
            ),
        ]
    )


def fit_binary_classifier_or_constant(
    schema,
    features: pd.DataFrame,
    target: pd.Series,
    *,
    config: LowNonzeroSpecialistConfig | None = None,
):
    clean_target = pd.to_numeric(target, errors="coerce").dropna().astype(int)
    if clean_target.empty:
        return _ConstantBinaryProbabilityClassifier(0.0)
    if clean_target.nunique(dropna=True) < 2:
        return _ConstantBinaryProbabilityClassifier(float(clean_target.mean()))
    model = build_lightgbm_binary_classifier(schema, config=config)
    model.fit(features.loc[clean_target.index], clean_target)
    return model


def fit_multiclass_classifier_or_constant(
    schema,
    features: pd.DataFrame,
    labels: pd.Series,
    *,
    config: LowNonzeroSpecialistConfig | None = None,
):
    clean_labels = labels.dropna().astype(str)
    if clean_labels.empty:
        return _ConstantMulticlassClassifier(LOW_NONZERO_SPECIALIST_LABELS, LOW_NONZERO_SPECIALIST_LABEL_REVIEW)
    label_counts = clean_labels.value_counts(dropna=False)
    if len(label_counts.index) < 2:
        return _ConstantMulticlassClassifier(LOW_NONZERO_SPECIALIST_LABELS, str(label_counts.index[0]))
    model = build_lightgbm_multiclass_classifier(schema, config=config)
    model.fit(features.loc[clean_labels.index], clean_labels)
    return model


def compute_backtest_like_metrics(rows: pd.DataFrame) -> dict[str, float | int | None]:
    if rows.empty:
        return {
            "row_count": 0,
            "mae": None,
            "mape": None,
            "overforecast_rate": None,
        }
    predicted = pd.to_numeric(rows["predicted_units_total_promo"], errors="coerce").fillna(0.0)
    actual = pd.to_numeric(rows["actual_units_sold_promo"], errors="coerce").fillna(0.0)
    abs_error = (predicted - actual).abs()
    smape_denom = ((predicted.abs() + actual.abs()) / 2.0).replace(0.0, np.nan)
    abs_pct_error = (abs_error / smape_denom * 100.0).fillna(0.0).clip(lower=0.0, upper=200.0)
    return {
        "row_count": int(len(rows.index)),
        "mae": float(abs_error.mean()),
        "mape": float(abs_pct_error.mean()),
        "overforecast_rate": float((predicted > actual).mean()),
    }


def map_publishability_labels(review_frame: pd.DataFrame) -> pd.Series:
    publish_class = review_frame.get("publish_eligibility_class", pd.Series("", index=review_frame.index)).fillna("")
    mapped = pd.Series(LOW_NONZERO_SPECIALIST_LABEL_REVIEW, index=review_frame.index, dtype="object")
    mapped = mapped.where(
        ~publish_class.astype(str).eq("publish_eligible"),
        LOW_NONZERO_SPECIALIST_LABEL_PUBLISH_NOW,
    )
    mapped = mapped.where(
        ~publish_class.astype(str).eq("excluded_legitimate"),
        LOW_NONZERO_SPECIALIST_LABEL_NO_ORDER,
    )
    return mapped.astype("string")


def evaluate_multiclass_classifier(
    model,
    features: pd.DataFrame,
    labels: pd.Series,
    *,
    label_source: str,
) -> LowNonzeroSpecialistClassifierDiagnostics:
    clean_labels = labels.dropna().astype(str)
    if clean_labels.empty:
        return LowNonzeroSpecialistClassifierDiagnostics(
            label_count=0,
            train_row_count=0,
            evaluation_row_count=0,
            macro_f1=None,
            accuracy=None,
            class_counts={},
            label_source=label_source,
        )
    predicted = pd.Series(model.predict(features.loc[clean_labels.index]), index=clean_labels.index, dtype="object")
    return LowNonzeroSpecialistClassifierDiagnostics(
        label_count=int(len(clean_labels.index)),
        train_row_count=0,
        evaluation_row_count=int(len(clean_labels.index)),
        macro_f1=float(f1_score(clean_labels, predicted, average="macro", zero_division=0)),
        accuracy=float(accuracy_score(clean_labels, predicted)),
        class_counts={str(key): int(value) for key, value in clean_labels.value_counts(dropna=False).to_dict().items()},
        label_source=label_source,
    )


def persist_specialist_bundle(
    *,
    run_id: str,
    dataset_path: str,
    artifact_root: Path,
    schema,
    metrics: dict[str, object],
    units_model,
    gross_profit_model,
    overallocation_classifier,
    underallocation_classifier,
    stockout_classifier,
) -> LowNonzeroSpecialistBundleArtifacts:
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_files: dict[str, str] = {}
    model_files = {
        "units_gradient_boosting": units_model,
        "gross_profit_linear": gross_profit_model,
        "overallocation_classifier": overallocation_classifier,
        "underallocation_classifier": underallocation_classifier,
        "stockout_classifier": stockout_classifier,
    }
    for model_name, model in model_files.items():
        artifact_path = artifact_root / f"{model_name}.joblib"
        joblib.dump(model, artifact_path)
        artifact_files[model_name] = str(artifact_path)

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
            trained_at_utc=pd.Timestamp.now(tz="UTC").isoformat(),
            dataset_path=dataset_path,
            target_mode="current_trainer_contract",
            split_summary={},
            feature_list_path=str(feature_list_path),
            metrics_path=str(metrics_path),
            inference_schema_path=str(inference_schema_path),
            artifact_files=artifact_files,
        ).to_dict(),
    )
    return LowNonzeroSpecialistBundleArtifacts(
        bundle_root=str(artifact_root),
        manifest_path=str(manifest_path),
        inference_schema_path=str(inference_schema_path),
        metrics_path=str(metrics_path),
        feature_list_path=str(feature_list_path),
        artifact_files=artifact_files,
    )