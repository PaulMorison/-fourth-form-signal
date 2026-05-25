from __future__ import annotations

"""Pilot and gold-standard validation for promotions execution outputs."""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths
from runtime.promotions.commercial_outcome import (
    PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED,
    PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
    STAGE13_SKIP_CLASS_STAGE12_NOOP_ALREADY_PUBLISHED,
    STAGE13_SKIP_CLASS_STAGE12_NOOP_NO_PUBLISHABLE_ROWS,
    classify_stage13_validation_skip,
)
from surfaces.promotions.reporting.pos_upload_schema import (
    PromotionPosUploadSchema,
    PromotionPosUploadSchemaValidationError,
)


class PromotionPilotValidationError(ValueError):
    """Raised when pilot validation identifies client-safety blocking failures."""


@dataclass(frozen=True)
class PromotionGoldStandardAcceptanceRecord:
    client_code: str
    store_number: str
    promotion_id: str
    promotion_header_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    expected_min_sku_count: int
    expected_exact_sku_count: int | None
    notes: str
    active_flag: bool


@dataclass(frozen=True)
class PromotionPilotValidationArtifacts:
    pilot_validation_summary_csv_path: str
    pilot_validation_summary_json_path: str
    pilot_validation_failures_csv_path: str
    gold_standard_acceptance_results_csv_path: str
    gold_standard_acceptance_results_json_path: str
    validation_manifest_path: str
    validation_failure_count: int
    gold_standard_failure_count: int
    validation_status: str
    validation_status_reason: str
    validation_skipped_flag: bool
    validation_reference_cycle_path: str
    validation_skip_class: str
    validation_skip_message: str
    validation_skip_summary_path: str


class PromotionPilotValidationService:
    """Validate Stage 11 and Stage 13 outputs for pilot and gold-standard promotion safety."""

    REVIEW_REQUIRED_COLUMNS = (
        "store_number",
        "promotion_id",
        "promotion_header_key",
        "sku_number",
        "sku_description",
        "recommended_order_quantity",
        "decision_action",
    )

    @staticmethod
    def _resolve_output_paths(
        *,
        run_id: str,
        artifact_paths: PromotionArtifactPaths,
    ) -> dict[str, Path]:
        """Resolve and create all output paths used by pilot validation."""
        paths = {
            "pilot_summary_csv_path": artifact_paths.pilot_validation_summary_csv_path(run_id),
            "pilot_summary_json_path": artifact_paths.pilot_validation_summary_json_path(run_id),
            "pilot_failures_csv_path": artifact_paths.pilot_validation_failures_csv_path(run_id),
            "gold_results_csv_path": artifact_paths.gold_standard_acceptance_results_csv_path(run_id),
            "gold_results_json_path": artifact_paths.gold_standard_acceptance_results_json_path(run_id),
            "validation_manifest_path": artifact_paths.validation_manifest_path(run_id),
            "validation_skip_summary_path": artifact_paths.validation_skip_summary_path(run_id),
        }
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        return paths

    def _write_noop_validation_outputs(
        self,
        *,
        run_id: str,
        as_of_date: str,
        created_at: str,
        acceptance_path: Path,
        stage12_publish_status: str,
        stage12_publish_status_reason: str,
        validation_reference_cycle_path: str,
        output_paths: dict[str, Path],
        validation_skip_class: str,
        validation_skip_message: str,
    ) -> PromotionPilotValidationArtifacts:
        """Persist deterministic skipped-validation artifacts for Stage 12 NOOP reruns."""
        pilot_frame = pd.DataFrame(columns=[
            "validation_status",
            "failure_reason",
            "publish_ready",
            "commercial_comment",
        ])
        failures_frame = pilot_frame.copy()
        gold_frame = pd.DataFrame(columns=pilot_frame.columns)
        pilot_frame.to_csv(output_paths["pilot_summary_csv_path"], index=False)
        failures_frame.to_csv(output_paths["pilot_failures_csv_path"], index=False)
        gold_frame.to_csv(output_paths["gold_results_csv_path"], index=False)
        output_paths["pilot_summary_json_path"].write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "as_of_date": as_of_date,
                    "created_at": created_at,
                    "rows": [],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        output_paths["gold_results_json_path"].write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "as_of_date": as_of_date,
                    "created_at": created_at,
                    "rows": [],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        validation_manifest = {
            "run_id": run_id,
            "as_of_date": as_of_date,
            "created_at": created_at,
            "acceptance_config_path": str(acceptance_path),
            "pilot_summary_row_count": 0,
            "pilot_failure_row_count": 0,
            "gold_standard_row_count": 0,
            "gold_standard_failure_row_count": 0,
            "validation_status": "SKIPPED_NO_NEW_PUBLICATIONS",
            "validation_status_reason": (
                "stage12_noop_no_publishable_rows"
                if stage12_publish_status == PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS
                else "stage12_noop_already_published"
            ),
            "validation_skipped_flag": True,
            "validation_skip_class": validation_skip_class,
            "validation_skip_message": validation_skip_message,
            "validation_reference_cycle_path": validation_reference_cycle_path,
            "stage12_publish_status": stage12_publish_status,
            "stage12_publish_status_reason": stage12_publish_status_reason,
            "output_files": {
                "pilot_validation_summary_csv": str(output_paths["pilot_summary_csv_path"]),
                "pilot_validation_summary_json": str(output_paths["pilot_summary_json_path"]),
                "pilot_validation_failures_csv": str(output_paths["pilot_failures_csv_path"]),
                "gold_standard_acceptance_results_csv": str(output_paths["gold_results_csv_path"]),
                "gold_standard_acceptance_results_json": str(output_paths["gold_results_json_path"]),
            },
        }
        output_paths["validation_manifest_path"].write_text(
            json.dumps(validation_manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        output_paths["validation_skip_summary_path"].write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "as_of_date": as_of_date,
                    "created_at": created_at,
                    "validation_skip_class": validation_skip_class,
                    "validation_skip_message": validation_skip_message,
                    "stage12_publish_status": stage12_publish_status,
                    "stage12_publish_status_reason": stage12_publish_status_reason,
                    "validation_status": "SKIPPED_NO_NEW_PUBLICATIONS",
                    "validation_status_reason": (
                        "stage12_noop_no_publishable_rows"
                        if stage12_publish_status == PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS
                        else "stage12_noop_already_published"
                    ),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return PromotionPilotValidationArtifacts(
            pilot_validation_summary_csv_path=str(output_paths["pilot_summary_csv_path"]),
            pilot_validation_summary_json_path=str(output_paths["pilot_summary_json_path"]),
            pilot_validation_failures_csv_path=str(output_paths["pilot_failures_csv_path"]),
            gold_standard_acceptance_results_csv_path=str(output_paths["gold_results_csv_path"]),
            gold_standard_acceptance_results_json_path=str(output_paths["gold_results_json_path"]),
            validation_manifest_path=str(output_paths["validation_manifest_path"]),
            validation_failure_count=0,
            gold_standard_failure_count=0,
            validation_status="SKIPPED_NO_NEW_PUBLICATIONS",
            validation_status_reason=(
                "stage12_noop_no_publishable_rows"
                if stage12_publish_status == PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS
                else "stage12_noop_already_published"
            ),
            validation_skipped_flag=True,
            validation_reference_cycle_path=validation_reference_cycle_path,
            validation_skip_class=validation_skip_class,
            validation_skip_message=validation_skip_message,
            validation_skip_summary_path=str(output_paths["validation_skip_summary_path"]),
        )

    def _finalize_validation_outputs(
        self,
        *,
        run_id: str,
        as_of_date: str,
        created_at: str,
        acceptance_path: Path,
        stage12_publish_status: str,
        stage12_publish_status_reason: str,
        validation_reference_cycle_path: str,
        pilot_frame: pd.DataFrame,
        failures_frame: pd.DataFrame,
        gold_frame: pd.DataFrame,
        output_paths: dict[str, Path],
        validation_skip_class: str,
        validation_skip_message: str,
    ) -> PromotionPilotValidationArtifacts:
        """Write normal validation outputs and return final artifact summary."""
        pilot_frame.to_csv(output_paths["pilot_summary_csv_path"], index=False)
        failures_frame.to_csv(output_paths["pilot_failures_csv_path"], index=False)
        gold_frame.to_csv(output_paths["gold_results_csv_path"], index=False)
        output_paths["pilot_summary_json_path"].write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "as_of_date": as_of_date,
                    "created_at": created_at,
                    "rows": pilot_frame.to_dict(orient="records"),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        output_paths["gold_results_json_path"].write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "as_of_date": as_of_date,
                    "created_at": created_at,
                    "rows": gold_frame.to_dict(orient="records"),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        pilot_failures = int(len(failures_frame.index))
        gold_failures = int(
            (~gold_frame.get("publish_ready", pd.Series(dtype="bool")).fillna(False).astype(bool)).sum()
        )

        validation_status = "PASS"
        validation_status_reason = "all_validation_checks_passed"
        if pilot_failures > 0 or gold_failures > 0:
            validation_status = "FAIL"
            validation_status_reason = "pilot_or_gold_standard_failures_detected"
        elif stage12_publish_status == "PASS_WITH_EXCLUSIONS":
            validation_status = "PASS_WITH_WARNINGS"
            validation_status_reason = "stage12_pass_with_exclusions"

        validation_manifest = {
            "run_id": run_id,
            "as_of_date": as_of_date,
            "created_at": created_at,
            "acceptance_config_path": str(acceptance_path),
            "pilot_summary_row_count": int(len(pilot_frame.index)),
            "pilot_failure_row_count": pilot_failures,
            "gold_standard_row_count": int(len(gold_frame.index)),
            "gold_standard_failure_row_count": gold_failures,
            "validation_status": validation_status,
            "validation_status_reason": validation_status_reason,
            "validation_skipped_flag": False,
            "validation_skip_class": validation_skip_class,
            "validation_skip_message": validation_skip_message,
            "validation_reference_cycle_path": validation_reference_cycle_path,
            "stage12_publish_status": stage12_publish_status,
            "stage12_publish_status_reason": stage12_publish_status_reason,
            "output_files": {
                "pilot_validation_summary_csv": str(output_paths["pilot_summary_csv_path"]),
                "pilot_validation_summary_json": str(output_paths["pilot_summary_json_path"]),
                "pilot_validation_failures_csv": str(output_paths["pilot_failures_csv_path"]),
                "gold_standard_acceptance_results_csv": str(output_paths["gold_results_csv_path"]),
                "gold_standard_acceptance_results_json": str(output_paths["gold_results_json_path"]),
            },
        }
        output_paths["validation_manifest_path"].write_text(
            json.dumps(validation_manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        output_paths["validation_skip_summary_path"].write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "as_of_date": as_of_date,
                    "created_at": created_at,
                    "validation_skip_class": validation_skip_class,
                    "validation_skip_message": validation_skip_message,
                    "stage12_publish_status": stage12_publish_status,
                    "stage12_publish_status_reason": stage12_publish_status_reason,
                    "validation_status": validation_status,
                    "validation_status_reason": validation_status_reason,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        artifacts = PromotionPilotValidationArtifacts(
            pilot_validation_summary_csv_path=str(output_paths["pilot_summary_csv_path"]),
            pilot_validation_summary_json_path=str(output_paths["pilot_summary_json_path"]),
            pilot_validation_failures_csv_path=str(output_paths["pilot_failures_csv_path"]),
            gold_standard_acceptance_results_csv_path=str(output_paths["gold_results_csv_path"]),
            gold_standard_acceptance_results_json_path=str(output_paths["gold_results_json_path"]),
            validation_manifest_path=str(output_paths["validation_manifest_path"]),
            validation_failure_count=pilot_failures,
            gold_standard_failure_count=gold_failures,
            validation_status=validation_status,
            validation_status_reason=validation_status_reason,
            validation_skipped_flag=False,
            validation_reference_cycle_path=validation_reference_cycle_path,
            validation_skip_class=validation_skip_class,
            validation_skip_message=validation_skip_message,
            validation_skip_summary_path=str(output_paths["validation_skip_summary_path"]),
        )
        if pilot_failures > 0 or gold_failures > 0:
            raise PromotionPilotValidationError(
                "Pilot validation failed for one or more store-promotion groups. "
                f"Manifest: {output_paths['validation_manifest_path']}"
            )
        return artifacts

    def write_validation_outputs(
        self,
        *,
        run_id: str,
        as_of_date: str,
        source_frame: pd.DataFrame,
        stage11_store_promotion_paths: tuple[str, ...],
        stage13_review_paths: tuple[str, ...],
        stage13_pos_upload_paths: tuple[str, ...],
        stage13_reconciliation_paths: tuple[str, ...],
        artifact_paths: PromotionArtifactPaths,
        acceptance_config_path: Path | None = None,
        stage12_publish_status: str = "PASS",
        stage12_publish_status_reason: str = "",
        validation_reference_cycle_path: str = "",
    ) -> PromotionPilotValidationArtifacts:
        """Validate Stage 11/13 outputs and emit pilot plus gold-standard acceptance artifacts."""
        created_at = datetime.now(tz=UTC).replace(microsecond=0).isoformat()
        acceptance_path = acceptance_config_path or artifact_paths.promotion_gold_standard_acceptance_config_path()
        acceptance_records = load_gold_standard_acceptance_config(acceptance_path)
        output_paths = self._resolve_output_paths(run_id=run_id, artifact_paths=artifact_paths)

        validation_skip_class, validation_skip_message = classify_stage13_validation_skip(
            stage12_publish_status=stage12_publish_status,
            stage13_review_paths_present=bool(stage13_review_paths),
            stage13_pos_paths_present=bool(stage13_pos_upload_paths),
            stage13_reconciliation_paths_present=bool(stage13_reconciliation_paths),
        )

        if stage12_publish_status in {"FAIL", "FAIL_NO_ELIGIBLE_ROWS"}:
            raise PromotionPilotValidationError(
                "Stage 13 validation aborted because Stage 12 publish status is "
                f"{stage12_publish_status} ({stage12_publish_status_reason or 'unspecified'})."
            )

        if (
            validation_skip_class
            in {
                STAGE13_SKIP_CLASS_STAGE12_NOOP_ALREADY_PUBLISHED,
                STAGE13_SKIP_CLASS_STAGE12_NOOP_NO_PUBLISHABLE_ROWS,
            }
        ):
            return self._write_noop_validation_outputs(
                run_id=run_id,
                as_of_date=as_of_date,
                created_at=created_at,
                acceptance_path=acceptance_path,
                stage12_publish_status=stage12_publish_status,
                stage12_publish_status_reason=stage12_publish_status_reason,
                validation_reference_cycle_path=validation_reference_cycle_path,
                output_paths=output_paths,
                validation_skip_class=validation_skip_class,
                validation_skip_message=validation_skip_message,
            )

        source_groups = _build_source_group_map(source_frame)
        stage11_groups = _build_stage11_group_map(stage11_store_promotion_paths, source_groups=source_groups)
        review_groups, review_schema_by_key = _build_stage13_review_group_map(stage13_review_paths)
        pos_schema_by_cycle = _validate_pos_schema_by_cycle(stage13_pos_upload_paths)
        reconciliation_by_key = _build_reconciliation_map(stage13_reconciliation_paths)

        selected_keys = _select_pilot_keys(source_groups, acceptance_records)
        if not selected_keys:
            selected_keys = [key for key in review_groups.keys() if key in source_groups]
        if not selected_keys:
            selected_keys = list(source_groups.keys())
        pilot_rows = [
            _evaluate_group(
                key=key,
                source_groups=source_groups,
                stage11_groups=stage11_groups,
                review_groups=review_groups,
                review_schema_by_key=review_schema_by_key,
                pos_schema_by_cycle=pos_schema_by_cycle,
                reconciliation_by_key=reconciliation_by_key,
                acceptance_record=None,
            )
            for key in selected_keys
        ]

        gold_rows: list[dict[str, object]] = []
        for record in acceptance_records:
            if not record.active_flag:
                continue
            resolved_key, resolution_reason = _resolve_acceptance_key(record, source_groups)
            if resolved_key is None:
                gold_rows.append(
                    _acceptance_failure_row(
                        record=record,
                        failure_reason=resolution_reason,
                    )
                )
                continue
            gold_rows.append(
                _evaluate_group(
                    key=resolved_key,
                    source_groups=source_groups,
                    stage11_groups=stage11_groups,
                    review_groups=review_groups,
                    review_schema_by_key=review_schema_by_key,
                    pos_schema_by_cycle=pos_schema_by_cycle,
                    reconciliation_by_key=reconciliation_by_key,
                    acceptance_record=record,
                )
            )

        pilot_frame = pd.DataFrame(pilot_rows)
        gold_frame = pd.DataFrame(gold_rows)
        failures_frame = pilot_frame.loc[
            ~pilot_frame["publish_ready"].fillna(False).astype(bool)
        ].copy()
        return self._finalize_validation_outputs(
            run_id=run_id,
            as_of_date=as_of_date,
            created_at=created_at,
            acceptance_path=acceptance_path,
            stage12_publish_status=stage12_publish_status,
            stage12_publish_status_reason=stage12_publish_status_reason,
            validation_reference_cycle_path=validation_reference_cycle_path,
            pilot_frame=pilot_frame,
            failures_frame=failures_frame,
            gold_frame=gold_frame,
            output_paths=output_paths,
            validation_skip_class=validation_skip_class,
            validation_skip_message=validation_skip_message,
        )


def load_gold_standard_acceptance_config(
    config_path: Path,
) -> tuple[PromotionGoldStandardAcceptanceRecord, ...]:
    if not config_path.exists():
        return tuple()

    if config_path.suffix.lower() == ".csv":
        frame = pd.read_csv(config_path, dtype="string")
    elif config_path.suffix.lower() == ".json":
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        records = raw.get("records", raw)
        frame = pd.DataFrame(records)
    else:
        raise PromotionPilotValidationError(
            f"Unsupported acceptance config format: {config_path}"
        )

    required = (
        "client_code",
        "store_number",
        "promotion_name",
        "promotion_start_date",
        "promotion_end_date",
        "expected_min_sku_count",
        "active_flag",
    )
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise PromotionPilotValidationError(
            "Acceptance config missing required columns: " + ", ".join(missing)
        )

    frame = frame.copy()
    for column in (
        "promotion_id",
        "promotion_header_key",
        "expected_exact_sku_count",
        "notes",
    ):
        if column not in frame.columns:
            frame[column] = ""

    frame["expected_min_sku_count"] = pd.to_numeric(
        frame["expected_min_sku_count"],
        errors="coerce",
    )
    if frame["expected_min_sku_count"].isna().any() or (frame["expected_min_sku_count"] < 0).any():
        raise PromotionPilotValidationError(
            "Acceptance config expected_min_sku_count must be non-negative integers."
        )

    frame["expected_exact_sku_count"] = pd.to_numeric(
        frame["expected_exact_sku_count"],
        errors="coerce",
    )
    frame["active_flag"] = frame["active_flag"].astype(str).str.strip().str.lower().isin(
        {"1", "true", "yes", "y", "t"}
    )

    records: list[PromotionGoldStandardAcceptanceRecord] = []
    for row in frame.itertuples(index=False):
        record = PromotionGoldStandardAcceptanceRecord(
            client_code=str(getattr(row, "client_code", "")).strip(),
            store_number=str(getattr(row, "store_number", "")).strip(),
            promotion_id=str(getattr(row, "promotion_id", "") or "").strip(),
            promotion_header_key=str(getattr(row, "promotion_header_key", "") or "").strip(),
            promotion_name=str(getattr(row, "promotion_name", "") or "").strip(),
            promotion_start_date=str(getattr(row, "promotion_start_date", "") or "").strip(),
            promotion_end_date=str(getattr(row, "promotion_end_date", "") or "").strip(),
            expected_min_sku_count=int(float(getattr(row, "expected_min_sku_count", 0))),
            expected_exact_sku_count=(
                None
                if pd.isna(getattr(row, "expected_exact_sku_count", pd.NA))
                else int(float(getattr(row, "expected_exact_sku_count")))
            ),
            notes=str(getattr(row, "notes", "") or "").strip(),
            active_flag=bool(getattr(row, "active_flag", False)),
        )
        if not record.promotion_id and not record.promotion_header_key and not record.promotion_name:
            raise PromotionPilotValidationError(
                "Acceptance config record must include promotion_header_key, promotion_id, or promotion_name."
            )
        records.append(record)
    return tuple(records)


def _build_source_group_map(source_frame: pd.DataFrame) -> dict[tuple[str, str], dict[str, object]]:
    required = (
        "store_number",
        "promotion_header_key",
        "promotion_name",
        "promotion_start_date",
        "promotion_end_date",
        "sku_number",
    )
    missing = [column for column in required if column not in source_frame.columns]
    if missing:
        raise PromotionPilotValidationError(
            "Source frame is missing required columns: " + ", ".join(missing)
        )

    groups: dict[tuple[str, str], dict[str, object]] = {}
    grouped = source_frame.groupby(["store_number", "promotion_header_key"], sort=False, dropna=False)
    for (store_number, promotion_header_key), group in grouped:
        key = (_normalize_store_number(store_number), _normalize_text(promotion_header_key))
        skus = set(group["sku_number"].astype(str).tolist())
        promotion_id = str(
            group.iloc[0].get("promotion_id", "")
            or group.iloc[0].get("promotional_sku_id_key", "")
            or group.iloc[0].get("promotion_header_key", "")
        )
        groups[key] = {
            "store_number": _normalize_store_number(store_number),
            "promotion_header_key": _normalize_text(promotion_header_key),
            "promotion_id": promotion_id,
            "promotion_name": str(group.iloc[0].get("promotion_name", "")),
            "promotion_start_date": str(group.iloc[0].get("promotion_start_date", "")),
            "promotion_end_date": str(group.iloc[0].get("promotion_end_date", "")),
            "source_row_count": int(len(group.index)),
            "source_unique_sku_count": int(len(skus)),
            "source_skus": skus,
        }
    return groups


def _build_stage11_group_map(
    paths: tuple[str, ...],
    *,
    source_groups: dict[tuple[str, str], dict[str, object]] | None = None,
) -> dict[tuple[str, str], dict[str, object]]:
    groups: dict[tuple[str, str], dict[str, object]] = {}
    for path_text in paths:
        path = Path(path_text)
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        if "store_number" not in frame.columns:
            inferred_store_number = _infer_stage11_store_number_from_path(path)
            if inferred_store_number == "":
                continue
            frame = frame.copy()
            frame["store_number"] = inferred_store_number
        if "promotion_header_key" in frame.columns:
            key = (
                _normalize_store_number(frame.iloc[0]["store_number"]),
                _normalize_text(frame.iloc[0]["promotion_header_key"]),
            )
        else:
            key = _resolve_stage11_store_facing_key(frame=frame, source_groups=source_groups or {})
            if key is None:
                continue
        groups[key] = {
            "path": str(path),
            "frame": frame,
        }
    return groups


def _infer_stage11_store_number_from_path(path: Path) -> str:
    name = path.name
    if "_" not in name:
        return ""
    return _normalize_store_number(name.split("_", 1)[0])


def _resolve_stage11_store_facing_key(
    *,
    frame: pd.DataFrame,
    source_groups: dict[tuple[str, str], dict[str, object]],
) -> tuple[str, str] | None:
    required = ("store_number", "promotion_name", "promotion_start_date", "promotion_end_date")
    if any(column not in frame.columns for column in required):
        return None
    store_number = _normalize_store_number(frame.iloc[0]["store_number"])
    promotion_name = _normalize_text(frame.iloc[0]["promotion_name"])
    promotion_start_date = _normalize_text(frame.iloc[0]["promotion_start_date"])
    promotion_end_date = _normalize_text(frame.iloc[0]["promotion_end_date"])
    matches = [
        key
        for key, source in source_groups.items()
        if _normalize_store_number(source["store_number"]) == store_number
        and _normalize_text(source["promotion_name"]) == promotion_name
        and _normalize_text(source["promotion_start_date"]) == promotion_start_date
        and _normalize_text(source["promotion_end_date"]) == promotion_end_date
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _build_stage13_review_group_map(
    review_paths: tuple[str, ...],
) -> tuple[dict[tuple[str, str], dict[str, object]], dict[tuple[str, str], bool]]:
    groups: dict[tuple[str, str], dict[str, object]] = {}
    schema_by_key: dict[tuple[str, str], bool] = {}
    for path_text in review_paths:
        path = Path(path_text)
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if frame.empty or "promotion_header_key" not in frame.columns or "store_number" not in frame.columns:
            continue
        grouped = frame.groupby(["store_number", "promotion_header_key"], sort=False, dropna=False)
        for (store_number, promotion_header_key), group in grouped:
            key = (_normalize_store_number(store_number), _normalize_text(promotion_header_key))
            groups[key] = {
                "path": str(path),
                "frame": group.copy(),
            }
            schema_by_key[key] = _review_frame_is_human_usable(group)
    return groups, schema_by_key


def _validate_pos_schema_by_cycle(paths: tuple[str, ...]) -> dict[str, bool]:
    schema = PromotionPosUploadSchema()
    output: dict[str, bool] = {}
    for path_text in paths:
        path = Path(path_text)
        cycle_key = str(path.parent)
        if not path.exists():
            output[cycle_key] = False
            continue
        frame = pd.read_csv(path)
        try:
            schema.validate(frame)
            output[cycle_key] = True
        except PromotionPosUploadSchemaValidationError:
            output[cycle_key] = False
    return output


def _build_reconciliation_map(paths: tuple[str, ...]) -> dict[tuple[str, str], str]:
    output: dict[tuple[str, str], str] = {}
    for path_text in paths:
        path = Path(path_text)
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        if "store_number" not in frame.columns or "promotion_header_key" not in frame.columns:
            continue
        for row in frame.itertuples(index=False):
            key = (
                _normalize_store_number(getattr(row, "store_number", "")),
                _normalize_text(getattr(row, "promotion_header_key", "")),
            )
            output[key] = str(getattr(row, "status", "FAIL"))
    return output


def _select_pilot_keys(
    source_groups: dict[tuple[str, str], dict[str, object]],
    acceptance_records: tuple[PromotionGoldStandardAcceptanceRecord, ...],
) -> list[tuple[str, str]]:
    active_records = [record for record in acceptance_records if record.active_flag]
    if not active_records:
        return []

    selected: list[tuple[str, str]] = []
    for record in active_records:
        resolved_key, _ = _resolve_acceptance_key(record, source_groups)
        if resolved_key is not None and resolved_key not in selected:
            selected.append(resolved_key)
    return selected


def _resolve_acceptance_key(
    record: PromotionGoldStandardAcceptanceRecord,
    source_groups: dict[tuple[str, str], dict[str, object]],
) -> tuple[tuple[str, str] | None, str]:
    matches: list[tuple[str, str]] = []
    for key, row in source_groups.items():
        if _normalize_store_number(row["store_number"]) != _normalize_store_number(record.store_number):
            continue
        if record.promotion_header_key and _normalize_text(row["promotion_header_key"]) != _normalize_text(record.promotion_header_key):
            continue
        if record.promotion_id and str(row["promotion_id"]).strip() != record.promotion_id:
            continue
        if record.promotion_name and str(row["promotion_name"]).strip() != record.promotion_name:
            continue
        if record.promotion_start_date and str(row["promotion_start_date"]).strip() != record.promotion_start_date:
            continue
        if record.promotion_end_date and str(row["promotion_end_date"]).strip() != record.promotion_end_date:
            continue
        matches.append(key)

    if not matches:
        return None, "acceptance_group_not_found_in_source"
    if len(matches) > 1:
        return None, "acceptance_group_ambiguous_in_source"
    return matches[0], ""


def _evaluate_group(
    *,
    key: tuple[str, str],
    source_groups: dict[tuple[str, str], dict[str, object]],
    stage11_groups: dict[tuple[str, str], dict[str, object]],
    review_groups: dict[tuple[str, str], dict[str, object]],
    review_schema_by_key: dict[tuple[str, str], bool],
    pos_schema_by_cycle: dict[str, bool],
    reconciliation_by_key: dict[tuple[str, str], str],
    acceptance_record: PromotionGoldStandardAcceptanceRecord | None,
) -> dict[str, object]:
    source = source_groups[key]
    base = {
        "client_code": acceptance_record.client_code if acceptance_record else "",
        "store_number": str(source["store_number"]),
        "promotion_id": str(source["promotion_id"]),
        "promotion_header_key": str(source["promotion_header_key"]),
        "promotion_name": str(source["promotion_name"]),
        "promotion_start_date": str(source["promotion_start_date"]),
        "promotion_end_date": str(source["promotion_end_date"]),
        "source_row_count": int(source["source_row_count"]),
        "source_unique_sku_count": int(source["source_unique_sku_count"]),
    }

    stage11_group = stage11_groups.get(key)
    if stage11_group is None:
        return {
            **base,
            "validation_status": "FAIL",
            "failure_reason": "missing_store_promotion_output_file",
            "output_row_count": 0,
            "output_unique_sku_count": 0,
            "missing_sku_count": int(source["source_unique_sku_count"]),
            "unexpected_sku_count": 0,
            "duplicate_row_count": 0,
            "review_row_count": 0,
            "manual_review_row_count": 0,
            "action_distribution": "{}",
            "pos_schema_valid": False,
            "reconciliation_valid": False,
            "review_human_usable": False,
            "publish_ready": False,
            "commercial_comment": "Missing Stage 11 store-promotion CSV output for this promotion.",
        }

    output_frame = stage11_group["frame"].copy()
    output_skus = set(output_frame["sku_number"].astype(str).tolist()) if "sku_number" in output_frame.columns else set()
    source_skus = set(source["source_skus"])
    missing_skus = sorted(source_skus - output_skus)
    unexpected_skus = sorted(output_skus - source_skus)
    duplicate_subset = [column for column in ("store_number", "promotion_header_key", "sku_number") if column in output_frame.columns]
    duplicate_count = int(
        output_frame[output_frame["sku_number"].notna()].duplicated(subset=duplicate_subset, keep=False).sum()
    )

    action_counts = output_frame["action_code"].astype(str).value_counts(dropna=False).to_dict() if "action_code" in output_frame.columns else {}
    review_row_count = int(
        output_frame.get("review_required_flag", pd.Series(dtype="bool")).fillna(False).astype(bool).sum()
    )
    manual_review_row_count = int(
        output_frame.get("manual_review_flag", pd.Series(dtype="bool")).fillna(False).astype(bool).sum()
    )

    review_group = review_groups.get(key)
    review_human_usable = bool(review_schema_by_key.get(key, False)) and review_group is not None
    cycle_key = str(Path(review_group["path"]).parent) if review_group is not None else ""
    pos_schema_valid = bool(pos_schema_by_cycle.get(cycle_key, False))
    reconciliation_valid = str(reconciliation_by_key.get(key, "FAIL")).upper() == "PASS"

    failure_reasons: list[str] = []
    output_unique = int(len(output_skus))
    source_unique = int(source["source_unique_sku_count"])
    if output_unique < source_unique:
        failure_reasons.append("output_has_fewer_skus_than_source")
    if duplicate_count > 0:
        failure_reasons.append("duplicate_store_promotion_sku_rows")
    if not pos_schema_valid:
        failure_reasons.append("pos_upload_schema_invalid")
    if not reconciliation_valid:
        failure_reasons.append("reconciliation_invalid")
    if not review_human_usable:
        failure_reasons.append("review_file_not_human_usable")

    if acceptance_record is not None:
        if output_unique < acceptance_record.expected_min_sku_count:
            failure_reasons.append("acceptance_min_sku_count_not_met")
        if (
            acceptance_record.expected_exact_sku_count is not None
            and output_unique != acceptance_record.expected_exact_sku_count
        ):
            failure_reasons.append("acceptance_exact_sku_count_mismatch")

    publish_ready = len(failure_reasons) == 0
    return {
        **base,
        "validation_status": "PASS" if publish_ready else "FAIL",
        "failure_reason": ";".join(failure_reasons),
        "output_row_count": int(len(output_frame.index)),
        "output_unique_sku_count": output_unique,
        "missing_sku_count": int(len(missing_skus)),
        "unexpected_sku_count": int(len(unexpected_skus)),
        "duplicate_row_count": duplicate_count,
        "review_row_count": review_row_count,
        "manual_review_row_count": manual_review_row_count,
        "action_distribution": json.dumps(action_counts, sort_keys=True),
        "pos_schema_valid": bool(pos_schema_valid),
        "reconciliation_valid": bool(reconciliation_valid),
        "review_human_usable": bool(review_human_usable),
        "publish_ready": bool(publish_ready),
        "commercial_comment": (
            "Pilot-safe output set for client/store promotion execution."
            if publish_ready
            else "Validation failed; review failure_reason and failure file before publishing."
        ),
    }


def _acceptance_failure_row(
    *,
    record: PromotionGoldStandardAcceptanceRecord,
    failure_reason: str,
) -> dict[str, object]:
    return {
        "client_code": record.client_code,
        "store_number": _normalize_store_number(record.store_number),
        "promotion_id": record.promotion_id,
        "promotion_header_key": record.promotion_header_key,
        "promotion_name": record.promotion_name,
        "promotion_start_date": record.promotion_start_date,
        "promotion_end_date": record.promotion_end_date,
        "validation_status": "FAIL",
        "failure_reason": failure_reason,
        "source_row_count": 0,
        "output_row_count": 0,
        "source_unique_sku_count": 0,
        "output_unique_sku_count": 0,
        "missing_sku_count": 0,
        "unexpected_sku_count": 0,
        "duplicate_row_count": 0,
        "review_row_count": 0,
        "manual_review_row_count": 0,
        "action_distribution": "{}",
        "pos_schema_valid": False,
        "reconciliation_valid": False,
        "review_human_usable": False,
        "publish_ready": False,
        "commercial_comment": "Gold-standard acceptance record could not be resolved to a source promotion group.",
    }


def _review_frame_is_human_usable(frame: pd.DataFrame) -> bool:
    if frame.empty:
        return False
    for column in PromotionPilotValidationService.REVIEW_REQUIRED_COLUMNS:
        if column not in frame.columns:
            return False
    for column in ("promotion_name", "decision_reason", "sku_description"):
        if column not in frame.columns:
            return False
        values = frame[column].astype(str).str.strip()
        if values.eq("").all():
            return False
    return True


def _normalize_text(value: object) -> str:
    return str(value).strip()


def _normalize_store_number(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if text.isdigit():
        return str(int(text))
    return text
