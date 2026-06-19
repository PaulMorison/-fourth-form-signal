from __future__ import annotations

"""Governed PCA residual structure feature module.

Canon ownership:
- Adds leak-safe structure-anomaly features from row-local and prior-safe
  engineered inputs only.
- Fits one global prior-only PCA basis per candidate promotion-start date and
  feature family so no row is scored against future reference rows.
- Emits explicit unavailable outputs when safe fitting is not possible rather
  than converting missing evidence into weak evidence.
- Supports caution and capital-discipline interpretation without directly
  changing live policy rules.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA


PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_pca_structure_residual_score",
    "feature_pca_structure_fit_score",
    "feature_pca_structure_outlier_flag",
    "feature_pca_allocation_residual_score",
    "feature_pca_allocation_outlier_flag",
)

PCA_RESIDUAL_STRUCTURE_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = (
    *PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS,
)

_PCA_STRUCTURE_SOURCE_COLUMNS: tuple[str, ...] = (
    "feature_pre_promo_cover_ratio",
    "feature_inventory_sufficiency_flag",
    "feature_units_above_trust_floor",
    "feature_expected_residual_stock_units",
    "feature_expected_bill_cycle_capital_drag_ratio",
    "feature_expected_gp_per_capital_committed",
    "feature_capital_at_risk_per_expected_unit",
    "feature_gross_profit_per_incremental_unit_expected",
    "feature_trust_floor_missed_demand_risk_score",
    "feature_historical_allocation_efficiency_rate",
    "feature_historical_overallocation_above_floor_rate",
)

_PCA_ALLOCATION_SOURCE_COLUMNS: tuple[str, ...] = (
    "feature_pre_promo_cover_ratio",
    "feature_units_above_trust_floor",
    "feature_expected_residual_stock_units",
    "feature_expected_bill_cycle_capital_drag_ratio",
    "feature_capital_at_risk_per_expected_unit",
    "feature_trust_floor_missed_demand_risk_score",
    "feature_historical_allocation_efficiency_rate",
    "feature_historical_overallocation_above_floor_rate",
)

_PROMOTION_START_DATE_COLUMN = "promotion_start_date_date"
_PROMOTION_END_DATE_CANDIDATES: tuple[str, ...] = (
    "promotional_end_date_date",
    "promotion_end_date_date",
)
_MIN_REFERENCE_ROW_COUNT = 24
_MIN_FITTED_COLUMN_COUNT = 4
_MAX_COMPONENT_COUNT = 3
_REFERENCE_OUTLIER_QUANTILE = 0.95
_MIN_RESIDUAL_THRESHOLD = 0.25
_MIN_COLUMN_SCALE = 1e-6


@dataclass(frozen=True)
class _PcaReferenceFit:
    """Immutable PCA fit metadata for one prior-safe feature family."""

    column_names: tuple[str, ...]
    column_means: pd.Series
    column_scales: pd.Series
    pca_model: PCA
    residual_threshold: float


def apply_ft_pca_residual_structure(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
    allow_candidate_history_fallback: bool = False,
) -> pd.DataFrame:
    """Append leak-safe PCA residual structure features.

    Purpose:
        Score each row against the stable structure of strictly prior comparable
        engineered rows so downstream model and review surfaces can detect
        abnormal demand-capital shapes without touching future outcomes.

    Inputs:
        frame: candidate rows that already carry the prerequisite stock,
            capital, trust-floor, and historical-memory features.
        reference_frame: optional historical frame. When it already carries the
            required engineered inputs, it is used as the prior-safe fitting
            source.
        allow_candidate_history_fallback: governed escape hatch for completed-
            row contexts only. When ``False`` and an explicit
            ``reference_frame`` lacks the required engineered PCA inputs, the
            module emits unavailable outputs instead of fitting from the
            current candidate frame. Thresholds in this module are initial
            governed heuristics, not calibrated truth.

    Outputs:
        A copy of ``frame`` with the PCA residual, fit, and outlier features
        appended.

    Important assumptions:
        The selected input columns are already leak-safe. PCA fitting is always
        filtered to rows whose promotion end date is strictly before the scored
        row's promotion start date. An explicit but unusable reference frame is
        treated as missing safe evidence unless candidate fallback is
        intentionally enabled.

    Side effects:
        None. The function copies the input frame before appending features.

    Failure behaviour:
        If the module cannot find enough safe reference rows or enough complete
        input columns, it emits explicit unavailable ``NaN`` outputs instead of
        fabricating normality or outlier status. By default it will not fit from
        the candidate frame when an explicit historical reference was supplied
        but lacks the required engineered PCA inputs.
    """

    working = frame.copy()
    structure_columns = _select_structure_feature_columns(working)
    allocation_columns = _select_allocation_feature_columns(working)
    structure_outputs = _build_residual_feature_family(
        candidate_frame=working,
        reference_frame=reference_frame,
        feature_columns=structure_columns,
        residual_column_name="feature_pca_structure_residual_score",
        fit_column_name="feature_pca_structure_fit_score",
        flag_column_name="feature_pca_structure_outlier_flag",
        allow_candidate_history_fallback=allow_candidate_history_fallback,
    )
    allocation_outputs = _build_residual_feature_family(
        candidate_frame=working,
        reference_frame=reference_frame,
        feature_columns=allocation_columns,
        residual_column_name="feature_pca_allocation_residual_score",
        fit_column_name=None,
        flag_column_name="feature_pca_allocation_outlier_flag",
        allow_candidate_history_fallback=allow_candidate_history_fallback,
    )
    derived = pd.concat([structure_outputs, allocation_outputs], axis=1)
    base_columns = working.drop(columns=list(derived.columns), errors="ignore")
    return pd.concat([base_columns, derived], axis=1)


def _select_structure_feature_columns(frame: pd.DataFrame) -> tuple[str, ...]:
    """Return the stable structure inputs that are present on the frame.

    Purpose:
        Keep the PCA structure family tied to a small governed set of existing
        capital-discipline and trust-floor inputs.

    Inputs:
        frame: candidate frame whose available columns determine the usable PCA
            inputs.

    Outputs:
        The ordered tuple of present structure columns.

    Important assumptions:
        Missing columns are treated as unavailable evidence, not as zeros.

    Failure behaviour:
        Returns a shorter tuple when prerequisites are absent; the caller then
        emits unavailable outputs.
    """

    return tuple(column_name for column_name in _PCA_STRUCTURE_SOURCE_COLUMNS if column_name in frame.columns)


def _select_allocation_feature_columns(frame: pd.DataFrame) -> tuple[str, ...]:
    """Return the stock-capital relationship inputs that are present on the frame.

    Purpose:
        Keep the allocation PCA family focused on trust-floor, stock, and
        capital-shape relationships rather than broad demand magnitude.

    Inputs:
        frame: candidate frame whose available columns determine the usable PCA
            inputs.

    Outputs:
        The ordered tuple of present allocation columns.

    Important assumptions:
        Missing columns remain unavailable evidence.

    Failure behaviour:
        Returns a shorter tuple when prerequisites are absent; the caller then
        emits unavailable outputs.
    """

    return tuple(column_name for column_name in _PCA_ALLOCATION_SOURCE_COLUMNS if column_name in frame.columns)


def _build_residual_feature_family(
    *,
    candidate_frame: pd.DataFrame,
    reference_frame: pd.DataFrame | None,
    feature_columns: tuple[str, ...],
    residual_column_name: str,
    fit_column_name: str | None,
    flag_column_name: str,
    allow_candidate_history_fallback: bool,
) -> pd.DataFrame:
    """Compute one PCA residual feature family with strict-prior safety.

    Purpose:
        Fit a prior-only PCA basis for each candidate promotion-start date and
        map the resulting reconstruction error into auditable residual and
        outlier outputs.

    Inputs:
        candidate_frame: rows being scored.
        reference_frame: optional historical source frame.
        feature_columns: ordered safe numeric inputs for this family.
        residual_column_name: output column for the bounded residual score.
        fit_column_name: optional output column for the inverse fit score.
        flag_column_name: output column for the binary outlier flag.
        allow_candidate_history_fallback: whether an unusable explicit
            reference may fall back to the current candidate frame.

    Outputs:
        A frame indexed like ``candidate_frame`` containing only this family's
        outputs.

    Important assumptions:
        Candidate grouping by promotion start date is sufficient for this first
        governed global PCA pass.

    Failure behaviour:
        Any date group without enough safe prior rows or enough complete inputs
        remains ``NaN`` for every output in the family.
    """

    output_columns = [residual_column_name, flag_column_name]
    if fit_column_name is not None:
        output_columns.insert(1, fit_column_name)
    outputs = _empty_feature_frame(candidate_frame.index, tuple(output_columns))
    if len(feature_columns) < _MIN_FITTED_COLUMN_COUNT:
        return outputs

    reference_source = _resolve_reference_source(
        candidate_frame=candidate_frame,
        reference_frame=reference_frame,
        feature_columns=feature_columns,
        allow_candidate_history_fallback=allow_candidate_history_fallback,
    )
    if reference_source is None:
        return outputs
    candidate_start_dates = _candidate_start_dates(candidate_frame)
    for candidate_start, row_index in candidate_start_dates.groupby(candidate_start_dates).groups.items():
        if pd.isna(candidate_start):
            continue
        reference_numeric = _prepare_pca_reference_frame(
            reference_frame=reference_source,
            candidate_start=candidate_start,
            feature_columns=feature_columns,
        )
        reference_fit = _fit_reference_pca(reference_numeric)
        if reference_fit is None:
            continue
        candidate_numeric = _prepare_pca_candidate_frame(
            candidate_frame.loc[row_index],
            feature_columns=reference_fit.column_names,
        )
        if candidate_numeric.empty:
            continue
        standardized_candidate = _standardize_columns(
            candidate_numeric,
            column_means=reference_fit.column_means,
            column_scales=reference_fit.column_scales,
        )
        residual = _compute_reconstruction_residual(
            standardized_candidate,
            pca_model=reference_fit.pca_model,
        )
        residual_score = (residual / reference_fit.residual_threshold).clip(lower=0.0, upper=1.0)
        outputs.loc[residual_score.index, residual_column_name] = residual_score
        outputs.loc[residual_score.index, flag_column_name] = _compute_outlier_flag(
            residual,
            residual_threshold=reference_fit.residual_threshold,
        )
        if fit_column_name is not None:
            outputs.loc[residual_score.index, fit_column_name] = _compute_fit_score(residual_score)
    return outputs


def _resolve_reference_source(
    *,
    candidate_frame: pd.DataFrame,
    reference_frame: pd.DataFrame | None,
    feature_columns: tuple[str, ...],
    allow_candidate_history_fallback: bool,
) -> pd.DataFrame | None:
    """Choose the safest reference source that has the required inputs.

    Purpose:
        Prefer an explicit historical reference frame when it already carries
        the prerequisite engineered columns. Candidate-frame fallback is an
        explicit opt-in escape hatch for controlled completed-row contexts only;
        the safe default is to emit unavailable outputs when an explicit
        historical reference lacks the required engineered PCA inputs.

    Inputs:
        candidate_frame: current engineered candidate rows.
        reference_frame: optional external history frame.
        feature_columns: required PCA inputs.
        allow_candidate_history_fallback: whether an explicit but unusable
            reference may fall back to the candidate frame.

    Outputs:
        The frame used for strict-prior filtering and PCA fitting, or ``None``
        when no safe governed reference exists.

    Important assumptions:
        The chosen reference source still goes through strict-prior date
        filtering before any fit occurs.

    Failure behaviour:
        Returns ``None`` when the provided reference frame does not carry the
        required engineered columns and candidate fallback is not explicitly
        enabled.
    """

    if reference_frame is None:
        return candidate_frame if allow_candidate_history_fallback else None
    if all(column_name in reference_frame.columns for column_name in feature_columns):
        return reference_frame
    if allow_candidate_history_fallback:
        return candidate_frame
    return None


def _prepare_pca_reference_frame(
    *,
    reference_frame: pd.DataFrame,
    candidate_start: pd.Timestamp,
    feature_columns: tuple[str, ...],
) -> pd.DataFrame:
    """Return the complete prior-only numeric reference rows for one date group.

    Purpose:
        Enforce strict-prior filtering and full-input completeness before PCA is
        fitted for a candidate date group.

    Inputs:
        reference_frame: chosen history source.
        candidate_start: promotion start timestamp for the scored group.
        feature_columns: required safe numeric inputs.

    Outputs:
        A numeric frame ready for PCA fitting.

    Important assumptions:
        A reference row is admissible only when its promotion end date is
        strictly before ``candidate_start``.

    Failure behaviour:
        Returns an empty frame when required columns or dates are missing.
    """

    if any(column_name not in reference_frame.columns for column_name in feature_columns):
        return pd.DataFrame(columns=list(feature_columns), dtype="float64")
    reference_end_dates = _reference_end_dates(reference_frame)
    if reference_end_dates is None:
        return pd.DataFrame(columns=list(feature_columns), dtype="float64")
    prior_mask = reference_end_dates.notna() & reference_end_dates.lt(candidate_start)
    prior_rows = reference_frame.loc[prior_mask, list(feature_columns)].apply(pd.to_numeric, errors="coerce")
    complete_rows = prior_rows.loc[prior_rows.notna().all(axis=1)]
    return complete_rows.astype("float64")


def _prepare_pca_candidate_frame(
    candidate_frame: pd.DataFrame,
    *,
    feature_columns: tuple[str, ...],
) -> pd.DataFrame:
    """Return the complete candidate rows that can be scored safely.

    Purpose:
        Preserve neutral unavailable outputs for candidate rows whose PCA input
        evidence is incomplete.

    Inputs:
        candidate_frame: candidate rows for one promotion-start group.
        feature_columns: required PCA inputs.

    Outputs:
        A numeric frame containing only rows with complete inputs.

    Important assumptions:
        Missing candidate inputs mean unavailable evidence, not weak evidence.

    Failure behaviour:
        Returns an empty frame when no row has complete safe inputs.
    """

    if any(column_name not in candidate_frame.columns for column_name in feature_columns):
        return pd.DataFrame(columns=list(feature_columns), dtype="float64")
    candidate_numeric = candidate_frame.loc[:, list(feature_columns)].apply(pd.to_numeric, errors="coerce")
    return candidate_numeric.loc[candidate_numeric.notna().all(axis=1)].astype("float64")


def _fit_reference_pca(reference_frame: pd.DataFrame) -> _PcaReferenceFit | None:
    """Fit a PCA basis on one prior-safe numeric reference frame.

    Purpose:
        Standardize the reference rows, drop degenerate columns, fit the PCA
        model, and derive the governed residual threshold used for scoring.

    Inputs:
        reference_frame: complete prior-only numeric rows for one feature
            family.

    Outputs:
        A fitted PCA metadata object, or ``None`` when the reference set is too
        small or too degenerate.

    Important assumptions:
        PCA is fitted only after strict-prior filtering and full-row
        completeness have already been enforced.

    Failure behaviour:
        Returns ``None`` instead of fitting on structurally weak reference data.
    """

    if len(reference_frame.index) < _MIN_REFERENCE_ROW_COUNT:
        return None
    standardized_reference = _standardize_columns(reference_frame)
    if standardized_reference.shape[1] < _MIN_FITTED_COLUMN_COUNT:
        return None
    component_count = min(
        _MAX_COMPONENT_COUNT,
        standardized_reference.shape[1],
        standardized_reference.shape[0] - 1,
    )
    if component_count < 1:
        return None
    pca_model = PCA(n_components=component_count, svd_solver="full")
    pca_model.fit(standardized_reference)
    reference_residual = _compute_reconstruction_residual(
        standardized_reference,
        pca_model=pca_model,
    )
    residual_threshold = max(
        float(reference_residual.quantile(_REFERENCE_OUTLIER_QUANTILE)),
        _MIN_RESIDUAL_THRESHOLD,
    )
    column_means = reference_frame.loc[:, standardized_reference.columns].mean(axis=0).astype("float64")
    column_scales = (
        reference_frame.loc[:, standardized_reference.columns].std(axis=0, ddof=0)
        .replace(0.0, np.nan)
        .astype("float64")
    )
    valid_scales = column_scales.where(column_scales.ge(_MIN_COLUMN_SCALE))
    return _PcaReferenceFit(
        column_names=tuple(standardized_reference.columns),
        column_means=column_means,
        column_scales=valid_scales,
        pca_model=pca_model,
        residual_threshold=residual_threshold,
    )


def _standardize_columns(
    frame: pd.DataFrame,
    *,
    column_means: pd.Series | None = None,
    column_scales: pd.Series | None = None,
) -> pd.DataFrame:
    """Return the standardized numeric frame with degenerate columns removed.

    Purpose:
        Keep the PCA fit stable by centering and scaling numeric inputs while
        dropping columns that carry no usable variation.

    Inputs:
        frame: complete numeric feature frame.
        column_means: optional precomputed means from a reference fit.
        column_scales: optional precomputed scales from a reference fit.

    Outputs:
        A standardized frame with only non-degenerate columns.

    Important assumptions:
        The caller has already enforced row completeness.

    Failure behaviour:
        Returns an empty frame when every column is degenerate.
    """

    if frame.empty:
        return frame.astype("float64")
    means = frame.mean(axis=0).astype("float64") if column_means is None else column_means.astype("float64")
    scales = frame.std(axis=0, ddof=0).astype("float64") if column_scales is None else column_scales.astype("float64")
    valid_columns = scales.loc[scales.fillna(0.0).ge(_MIN_COLUMN_SCALE)].index.tolist()
    if not valid_columns:
        return pd.DataFrame(index=frame.index, dtype="float64")
    valid_means = means.loc[valid_columns]
    valid_scales = scales.loc[valid_columns]
    standardized = frame.loc[:, valid_columns].subtract(valid_means, axis=1).divide(valid_scales, axis=1)
    return standardized.astype("float64")


def _compute_reconstruction_residual(
    standardized_frame: pd.DataFrame,
    *,
    pca_model: PCA,
) -> pd.Series:
    """Return the row-wise reconstruction residual in standardized units.

    Purpose:
        Measure how far each row sits from the PCA reconstruction manifold for
        the fitted reference basis.

    Inputs:
        standardized_frame: centered and scaled rows aligned to the fitted PCA
            columns.
        pca_model: fitted PCA model.

    Outputs:
        A non-negative residual series indexed like ``standardized_frame``.

    Important assumptions:
        ``standardized_frame`` already matches the PCA fit's column order.

    Failure behaviour:
        Returns an empty series when the input frame is empty.
    """

    if standardized_frame.empty:
        return pd.Series(index=standardized_frame.index, dtype="float64")
    transformed = pca_model.transform(standardized_frame)
    reconstructed = pca_model.inverse_transform(transformed)
    residual_matrix = standardized_frame.to_numpy(dtype="float64") - reconstructed
    residual = np.sqrt(np.mean(np.square(residual_matrix), axis=1))
    return pd.Series(residual, index=standardized_frame.index, dtype="float64")


def _compute_fit_score(residual_score: pd.Series) -> pd.Series:
    """Return the inverse bounded fit score for a residual score.

    Purpose:
        Provide an operator-friendly fit measure where larger values indicate a
        row that better matches the prior-safe reference structure.

    Inputs:
        residual_score: bounded residual score on ``[0, 1]``.

    Outputs:
        The inverse fit score on ``[0, 1]``.

    Failure behaviour:
        Propagates ``NaN`` unavailable states unchanged.
    """

    return (1.0 - residual_score).clip(lower=0.0, upper=1.0)


def _compute_outlier_flag(
    residual: pd.Series,
    *,
    residual_threshold: float,
) -> pd.Series:
    """Return the governed binary outlier flag from a raw residual.

    Purpose:
        Mark only rows whose reconstruction error breaches the governed
        residual threshold derived from the prior-safe reference set.

    Inputs:
        residual: raw reconstruction residual in standardized units.
        residual_threshold: non-zero threshold for this feature family.

    Outputs:
        A float series on ``0`` or ``1``.

    Failure behaviour:
        Propagates ``NaN`` unavailable states unchanged.
    """

    return residual.ge(residual_threshold).astype("float64").where(residual.notna())


def _candidate_start_dates(frame: pd.DataFrame) -> pd.Series:
    """Return candidate promotion start dates as timestamps."""

    return pd.to_datetime(frame.get(_PROMOTION_START_DATE_COLUMN), errors="coerce")


def _reference_end_dates(frame: pd.DataFrame) -> pd.Series | None:
    """Return reference promotion end dates from the governed date candidates."""

    for column_name in _PROMOTION_END_DATE_CANDIDATES:
        if column_name in frame.columns:
            return pd.to_datetime(frame[column_name], errors="coerce")
    return None


def _empty_feature_frame(index: pd.Index, output_columns: tuple[str, ...]) -> pd.DataFrame:
    """Return an unavailable-output frame for one feature family.

    Purpose:
        Provide one explicit neutral fallback for groups that cannot be scored
        safely.

    Inputs:
        index: output index.
        output_columns: family output column names.

    Outputs:
        A frame filled with ``NaN`` unavailable values.

    Failure behaviour:
        None.
    """

    return pd.DataFrame(
        {
            column_name: pd.Series(np.nan, index=index, dtype="float64")
            for column_name in output_columns
        },
        index=index,
    )