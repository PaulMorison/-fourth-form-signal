from __future__ import annotations

"""Deterministic cohort-key construction for promotions history and backtesting."""

import math
import re

import pandas as pd


_NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")

COHORT_KEY_COLUMNS = (
    "cohort_key_promotion_name",
    "cohort_key_promo_type",
    "cohort_key_supplier",
    "cohort_key_department",
    "cohort_key_store",
    "cohort_key_offer_mechanic",
    "cohort_key_name_supplier",
    "cohort_key_type_department",
    "cohort_key_type_supplier",
    "cohort_key_type_store",
    "cohort_key_archetype_primary",
    "cohort_key_archetype_secondary",
)


def normalize_key_component(value: object) -> str:
    """Return a stable cohort-key token for text, numeric, or null inputs."""

    if value is None:
        return "unknown"
    if isinstance(value, float):
        if math.isnan(value):
            return "unknown"
        if value.is_integer():
            value = int(value)
    normalized = str(value).strip().lower()
    normalized = _NON_ALPHANUMERIC_PATTERN.sub("_", normalized).strip("_")
    return normalized or "unknown"


def normalize_key_series(series: pd.Series) -> pd.Series:
    """Return a stable string series suitable for deterministic cohort keys."""

    return series.map(normalize_key_component).astype("object")


def compose_cohort_key(prefix: str, components: dict[str, pd.Series]) -> pd.Series:
    """Compose a stable cohort key from named normalized component series."""

    if not components:
        raise ValueError("Cohort keys require at least one component.")
    key_index = next(iter(components.values())).index
    key_series = pd.Series(prefix, index=key_index, dtype="object")
    for component_name, component_values in components.items():
        key_series = key_series + "|" + component_name + "=" + normalize_key_series(component_values)
    return key_series