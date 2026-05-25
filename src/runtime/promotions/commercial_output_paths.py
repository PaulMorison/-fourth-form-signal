from __future__ import annotations

"""Authoritative commercial output paths for promotions store prediction files."""

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
from pathlib import Path
import re


DEFAULT_RETAILER_SLUG = "priceline"


@dataclass(frozen=True)
class PromotionCommercialOutputPathBuilder:
    """Build stable retailer/store/prediction paths for commercial CSVs."""

    artifact_root: Path
    retailer_slug: str = DEFAULT_RETAILER_SLUG

    def retailer_root(self) -> Path:
        return self.artifact_root / "promotions" / _slug(self.retailer_slug, fallback=DEFAULT_RETAILER_SLUG)

    def retailer_prediction_root(self) -> Path:
        return self.retailer_root() / "prediction"

    def store_root(self, *, store_number: object) -> Path:
        return self.retailer_root() / _store_number_token(store_number)

    def store_prediction_root(self, *, store_number: object) -> Path:
        return self.store_root(store_number=store_number) / "prediction"

    def store_prediction_summary_csv_path(
        self,
        *,
        store_number: object,
        as_of_date: object,
    ) -> Path:
        store_token = _store_number_token(store_number)
        iso_date = _iso_date_token(as_of_date)
        return (
            self.store_prediction_root(store_number=store_token)
            / iso_date
            / f"{store_token}_{iso_date}_all-predictions.csv"
        )

    def store_promotion_prediction_csv_path(
        self,
        *,
        store_number: object,
        promotion_start_date: object,
        promotion_name: object,
        collision_key: object | None = None,
    ) -> Path:
        return self.store_promotion_prediction_directory(
            store_number=store_number,
            promotion_start_date=promotion_start_date,
        ) / f"{self.store_promotion_prediction_file_stem(
            store_number=store_number,
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            collision_key=collision_key,
        )}.csv"

    def store_promotion_prediction_artifact_path(
        self,
        *,
        store_number: object,
        promotion_start_date: object,
        promotion_name: object,
        artifact_name: object,
        extension: object,
        collision_key: object | None = None,
    ) -> Path:
        artifact_slug = _slug(artifact_name, fallback="artifact", max_length=64)
        extension_slug = _slug(extension, fallback="txt", max_length=16)
        filename = (
            f"{self.store_promotion_prediction_file_stem(
                store_number=store_number,
                promotion_start_date=promotion_start_date,
                promotion_name=promotion_name,
                collision_key=collision_key,
            )}_{artifact_slug}.{extension_slug}"
        )
        return self.store_promotion_prediction_directory(
            store_number=store_number,
            promotion_start_date=promotion_start_date,
        ) / filename

    def store_promotion_prediction_directory(
        self,
        *,
        store_number: object,
        promotion_start_date: object,
    ) -> Path:
        store_token = _store_number_token(store_number)
        iso_date = _iso_date_token(promotion_start_date)
        return self.store_prediction_root(store_number=store_token) / iso_date

    def store_promotion_prediction_file_stem(
        self,
        *,
        store_number: object,
        promotion_start_date: object,
        promotion_name: object,
        collision_key: object | None = None,
    ) -> str:
        store_token = _store_number_token(store_number)
        iso_date = _iso_date_token(promotion_start_date)
        promotion_slug = _slug(promotion_name, fallback="unknown-promotion", max_length=96)
        suffix = f"-{_short_suffix(collision_key)}" if collision_key not in (None, "") else ""
        return f"{store_token}_{iso_date}_{promotion_slug}{suffix}"


def commercial_prediction_collision_suffix(value: object) -> str:
    return _short_suffix(value)


def _slug(value: object, *, fallback: str, max_length: int = 64) -> str:
    candidate = str(value or "").strip().lower()
    candidate = re.sub(r"[^a-z0-9]+", "-", candidate)
    candidate = re.sub(r"-+", "-", candidate).strip("-")
    if not candidate:
        candidate = fallback
    return candidate[:max_length].strip("-") or fallback


def _store_number_token(value: object) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    return _slug(text, fallback="unknown-store", max_length=32)


def _iso_date_token(value: object) -> str:
    text = str(value or "").strip().replace("_", "-")
    parsed_date: date | None = None
    try:
        parsed_date = date.fromisoformat(text[:10])
    except ValueError:
        try:
            parsed_date = datetime.fromisoformat(text[:10]).date()
        except ValueError:
            parsed_date = None
    if parsed_date is not None:
        return parsed_date.isoformat()
    return _slug(text, fallback="unknown-date", max_length=16)


def _short_suffix(value: object) -> str:
    digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()
    return digest[:8]