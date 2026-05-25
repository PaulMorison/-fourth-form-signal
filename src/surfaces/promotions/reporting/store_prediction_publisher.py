from __future__ import annotations

"""Commercial execution publisher for store prediction outputs."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths
from surfaces.promotions.reporting.demand_evidence_classifier import (
    DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE,
    DEMAND_EVIDENCE_CLASS_COLD_START,
    DEMAND_EVIDENCE_CLASS_TRUE_ZERO,
    classify_demand_evidence_row,
)
from surfaces.promotions.reporting.pos_upload_schema import (
    PromotionPosUploadSchema,
    PromotionPosUploadSchemaValidationError,
)
from surfaces.promotions.reporting.store_client_resolver import (
    PromotionStoreClientMappingError,
    PromotionStoreClientResolver,
)


DEFAULT_PLANNING_HORIZON_DAYS = 35


class PromotionStoreExecutionValidationError(ValueError):
    """Raised when commercial execution publishing validation fails."""


@dataclass(frozen=True)
class PromotionStoreExecutionPublishArtifacts:
    """Artifact paths and aggregate counts produced by Stage 12 publication."""

    prediction_registry_path: str
    store_cycle_manifest_paths: tuple[str, ...]
    pos_upload_paths: tuple[str, ...]
    review_paths: tuple[str, ...]
    summary_paths: tuple[str, ...]
    reconciliation_paths: tuple[str, ...]
    diagnostics_paths: tuple[str, ...]
    skipped_paths: tuple[str, ...]
    publication_summary_path: str
    stores_published: int
    promotion_cycles_published: int
    pos_upload_row_count: int
    pos_excluded_row_count: int
    skipped_duplicate_prediction_count: int
    skipped_due_to_registry_duplicate_count: int
    skipped_due_to_review_count: int
    skipped_due_to_schema_count: int
    skipped_due_to_mapping_count: int
    skipped_due_to_null_sku_count: int
    candidate_row_count: int
    pos_candidate_row_count: int
    prior_publication_detected_flag: bool
    noop_already_published_flag: bool
    publish_status: str
    publish_status_reason: str


@dataclass(frozen=True)
class PromotionPosExclusionThresholdPolicy:
    """Governed thresholds for handling POS row exclusions during publication."""

    fail_if_zero_published: bool = True
    max_excluded_ratio: float = 1.0
    max_excluded_count: int = 1_000_000


PUBLISH_STATUS_PASS = "PASS"
PUBLISH_STATUS_PASS_WITH_EXCLUSIONS = "PASS_WITH_EXCLUSIONS"
PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED = "NOOP_ALREADY_PUBLISHED"
PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS = "NOOP_VALID_NO_PUBLISHABLE_ROWS"
PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS = "FAIL_NO_ELIGIBLE_ROWS"
PUBLISH_STATUS_FAIL = "FAIL"

PUBLISH_ELIGIBILITY_CLASS_PUBLISH_ELIGIBLE = "publish_eligible"
PUBLISH_ELIGIBILITY_CLASS_REVIEW_ONLY = "review_only"
PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_LEGITIMATE = "excluded_legitimate"
PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_DEFECT = "excluded_defect"


@dataclass(frozen=True)
class PublishEligibilityEvaluation:
    """Authoritative Stage 12 publish eligibility decision for one row."""

    publish_eligibility_class: str
    publish_eligibility_reason: str
    publish_noop_reason: str
    review_required_flag: int
    excluded_from_publish_flag: int
    excluded_from_publish_reason: str
    pos_eligible_flag: int
    exclusion_reason_primary: str
    exclusion_reason_secondary: str
    defect_flag: int
    policy_contradiction_flag: int


class StorePredictionPublisher:
    """Publish scored predictions into retailer/store/prediction execution folders."""

    def publish(
        self,
        *,
        run_id: str,
        as_of_date: str,
        scored_decision_surface_frame: pd.DataFrame,
        store_download_frame: pd.DataFrame,
        artifact_paths: PromotionArtifactPaths,
        model_version: str,
        planning_horizon_days: int = DEFAULT_PLANNING_HORIZON_DAYS,
        allow_reprediction: bool = False,
        allow_republish_same_cycle: bool = False,
        strict_store_mapping: bool = False,
        exclusion_threshold_policy: PromotionPosExclusionThresholdPolicy | None = None,
    ) -> PromotionStoreExecutionPublishArtifacts:
        """Build Stage 12 execution uploads, enforce policy gates, and persist publish outputs."""
        cutoff_date = date.fromisoformat(as_of_date)
        horizon_date = cutoff_date + timedelta(days=planning_horizon_days)
        created_at = datetime.now(tz=UTC).replace(microsecond=0).isoformat()
        threshold_policy = exclusion_threshold_policy or PromotionPosExclusionThresholdPolicy()
        scored_input_row_count = int(len(scored_decision_surface_frame.index))
        store_download_input_row_count = int(len(store_download_frame.index))

        eligible_scored = self._eligible_scored_rows(
            frame=scored_decision_surface_frame,
            cutoff_date=cutoff_date,
            horizon_date=horizon_date,
        )
        resolver = PromotionStoreClientResolver(
            mapping_path=artifact_paths.promotion_store_client_mapping_path(),
            strict=strict_store_mapping,
        )
        pos_schema = PromotionPosUploadSchema()
        publish_base, candidate_gate_counts = self._build_publish_base(
            run_id=run_id,
            created_at=created_at,
            scored_frame=eligible_scored,
            store_download_frame=store_download_frame,
            resolver=resolver,
        )
        candidate_gate_counts.update(
            {
                "scored_input_row_count": scored_input_row_count,
                "scored_eligible_row_count": int(len(eligible_scored.index)),
                "store_download_input_row_count": store_download_input_row_count,
            }
        )
        self._validate_no_duplicate_prediction_rows(publish_base)

        registry_path = artifact_paths.prediction_registry_path()
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_frame = _load_registry(registry_path)

        publish_rows, skipped_rows, registry_frame = self._apply_registry_policy(
            candidate_rows=publish_base,
            registry_frame=registry_frame,
            allow_reprediction=(allow_reprediction or allow_republish_same_cycle),
            model_version=model_version,
            run_id=run_id,
            cutoff_date=cutoff_date,
            created_at=created_at,
        )
        _write_registry(registry_path, registry_frame)

        run_skip_counts = self._classify_run_skip_reasons(
            candidate_rows=publish_base,
            skipped_rows=skipped_rows,
        )
        prior_publication_detected_flag = run_skip_counts["skipped_due_to_registry_duplicate_count"] > 0

        publish_frame = pd.DataFrame(publish_rows)
        if publish_frame.empty:
            artifacts = self._build_noop_publish_artifacts(
                run_id=run_id,
                created_at=created_at,
                candidate_row_count=len(publish_base),
                skipped_rows=skipped_rows,
                run_skip_counts=run_skip_counts,
                prior_publication_detected_flag=prior_publication_detected_flag,
                registry_path=str(registry_path),
                artifact_paths=artifact_paths,
                candidate_gate_counts=candidate_gate_counts,
            )
            if artifacts.publish_status in {PUBLISH_STATUS_FAIL, PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS}:
                raise PromotionStoreExecutionValidationError(
                    "Validation failed: Stage 12 publish status is "
                    f"{artifacts.publish_status} ({artifacts.publish_status_reason})."
                )
            return artifacts

        manifest_paths: list[str] = []
        pos_paths: list[str] = []
        review_paths: list[str] = []
        summary_paths: list[str] = []
        reconciliation_paths: list[str] = []
        diagnostics_paths: list[str] = []
        skipped_paths: list[str] = []
        publication_summary_rows: list[dict[str, object]] = []
        cycle_review_frames: list[pd.DataFrame] = []
        stores_published: set[str] = set()
        cycle_count = 0
        total_pos_published_row_count = 0
        total_pos_excluded_row_count = 0
        total_pos_candidate_row_count = 0
        total_source_row_count = 0
        total_skip_reason_counts = {
            "skipped_due_to_registry_duplicate_count": 0,
            "skipped_due_to_review_count": 0,
            "skipped_due_to_schema_count": 0,
            "skipped_due_to_mapping_count": 0,
            "skipped_due_to_null_sku_count": 0,
        }

        grouped = list(
            publish_frame.groupby(["client_name", "store_number", "promotion_header_key"], sort=False, dropna=False)
        )
        base_prediction_paths = [
            str(
                artifact_paths.store_prediction_store_promotion_csv_path(
                    run_id=run_id,
                    store_number=str(store_number),
                    promotion_start_date=_first_non_empty(group, "promotion_start_date"),
                    promotion_name=_first_non_empty(group, "promotion_name"),
                )
            )
            for (_, store_number, _), group in grouped
        ]
        base_prediction_path_counts = Counter(base_prediction_paths)
        for ((client_name, store_number, promotion_header_key), group), base_prediction_path in zip(grouped, base_prediction_paths, strict=False):
            cycle_count += 1
            stores_published.add(str(store_number))
            collision_key = str(promotion_header_key) if base_prediction_path_counts[base_prediction_path] > 1 else None
            cycle_result = self._publish_cycle_package(
                run_id=run_id,
                as_of_date=as_of_date,
                created_at=created_at,
                model_version=model_version,
                planning_horizon_days=planning_horizon_days,
                artifact_paths=artifact_paths,
                pos_schema=pos_schema,
                threshold_policy=threshold_policy,
                skipped_rows=skipped_rows,
                client_name=client_name,
                store_number=store_number,
                promotion_header_key=promotion_header_key,
                collision_key=collision_key,
                group=group,
            )

            manifest_paths.append(cycle_result["manifest_path"])
            pos_paths.append(cycle_result["pos_path"])
            review_paths.append(cycle_result["review_path"])
            summary_paths.append(cycle_result["summary_path"])
            reconciliation_paths.append(cycle_result["reconciliation_path"])
            diagnostics_paths.append(cycle_result["diagnostics_path"])
            publication_summary_rows.extend(cycle_result["publication_summary_rows"])
            cycle_review_frames.append(cycle_result["review_frame"])

            total_pos_published_row_count += int(cycle_result["cycle_summary"]["pos_published_row_count"])
            total_pos_excluded_row_count += int(cycle_result["cycle_summary"]["pos_excluded_row_count"])
            total_pos_candidate_row_count += int(cycle_result["cycle_summary"]["pos_candidate_row_count"])
            total_source_row_count += int(cycle_result["cycle_summary"]["source_row_count"])
            for key in total_skip_reason_counts:
                total_skip_reason_counts[key] += int(cycle_result["cycle_summary"].get(key, 0))

        publication_summary_path = artifact_paths.commercial_publication_summary_csv_path(run_id)
        publication_summary_path.parent.mkdir(parents=True, exist_ok=True)
        publication_summary_frame = pd.DataFrame(publication_summary_rows)
        publication_summary_frame.to_csv(publication_summary_path, index=False)

        run_publish_diagnostics = self._write_publish_eligibility_run_diagnostics(
            diagnostics_root=publication_summary_path.parent,
            review_frames=cycle_review_frames,
            source_row_count=store_download_input_row_count,
            post_identity_row_count=int(len(publish_base)),
            post_policy_row_count=int(total_pos_candidate_row_count),
            final_published_row_count=int(total_pos_published_row_count),
            publication_summary_frame=publication_summary_frame,
            run_id=run_id,
            created_at=created_at,
        )
        diagnostics_paths.extend(run_publish_diagnostics)

        overall_status, overall_reason = self._build_overall_publish_status(publication_summary_frame)
        if overall_status in {PUBLISH_STATUS_FAIL, PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS}:
            raise PromotionStoreExecutionValidationError(
                f"Validation failed: Stage 12 publish status is {overall_status} ({overall_reason})."
            )

        return PromotionStoreExecutionPublishArtifacts(
            prediction_registry_path=str(registry_path),
            store_cycle_manifest_paths=tuple(manifest_paths),
            pos_upload_paths=tuple(pos_paths),
            review_paths=tuple(review_paths),
            summary_paths=tuple(summary_paths),
            reconciliation_paths=tuple(reconciliation_paths),
            diagnostics_paths=tuple(diagnostics_paths),
            skipped_paths=tuple(skipped_paths),
            publication_summary_path=str(publication_summary_path),
            stores_published=len(stores_published),
            promotion_cycles_published=cycle_count,
            pos_upload_row_count=total_pos_published_row_count,
            pos_excluded_row_count=total_pos_excluded_row_count,
            skipped_duplicate_prediction_count=len(skipped_rows),
            skipped_due_to_registry_duplicate_count=int(total_skip_reason_counts["skipped_due_to_registry_duplicate_count"]),
            skipped_due_to_review_count=int(total_skip_reason_counts["skipped_due_to_review_count"]),
            skipped_due_to_schema_count=int(total_skip_reason_counts["skipped_due_to_schema_count"]),
            skipped_due_to_mapping_count=int(total_skip_reason_counts["skipped_due_to_mapping_count"]),
            skipped_due_to_null_sku_count=int(total_skip_reason_counts["skipped_due_to_null_sku_count"]),
            candidate_row_count=total_source_row_count,
            pos_candidate_row_count=total_pos_candidate_row_count,
            prior_publication_detected_flag=(total_skip_reason_counts["skipped_due_to_registry_duplicate_count"] > 0),
            noop_already_published_flag=False,
            publish_status=overall_status,
            publish_status_reason=overall_reason,
        )

    def _publish_cycle_package(
        self,
        *,
        run_id: str,
        as_of_date: str,
        created_at: str,
        model_version: str,
        planning_horizon_days: int,
        artifact_paths: PromotionArtifactPaths,
        pos_schema: PromotionPosUploadSchema,
        threshold_policy: PromotionPosExclusionThresholdPolicy,
        skipped_rows: list[dict[str, object]],
        client_name: object,
        store_number: object,
        promotion_header_key: object,
        collision_key: str | None,
        group: pd.DataFrame,
    ) -> dict[str, object]:
        """Publish one store+promotion execution package and return cycle artifacts/counters."""
        store_slug = _slug(_first_non_empty(group, "store_name") or f"store_{store_number}")
        client_slug = _slug(str(client_name or "Priceline"))
        store_number_token = _slug(str(store_number), fallback="unknown")
        promotion_start_date = _first_non_empty(group, "promotion_start_date")
        promotion_name = _first_non_empty(group, "promotion_name")
        prediction_stem = artifact_paths.commercial_output_path_builder().store_promotion_prediction_file_stem(
            store_number=store_number,
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            collision_key=collision_key,
        )
        cycle_root = artifact_paths.client_store_prediction_cycle_root(
            client_name=client_slug,
            store_slug=store_slug,
            store_number=store_number_token,
            promotion_cycle_id=prediction_stem,
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            collision_key=collision_key,
        )
        cycle_root.mkdir(parents=True, exist_ok=True)

        review_frame = self._build_review_frame(group)
        review_frame = self._annotate_pos_eligibility(review_frame)
        pos_eligible_frame = review_frame.loc[
            review_frame["pos_eligible_flag"].astype(int).eq(1)
        ].reset_index(drop=True)
        pos_frame = self._build_pos_upload_frame(pos_eligible_frame, pos_schema=pos_schema)

        self._validate_cycle_frames(
            review_frame=review_frame,
            pos_frame=pos_frame,
            pos_eligible_frame=pos_eligible_frame,
            expected_group=group,
            pos_schema=pos_schema,
        )

        group_skipped = [
            row
            for row in skipped_rows
            if row["store_number"] == str(store_number)
            and str(row.get("promotion_header_key", "")) == str(promotion_header_key)
        ]

        cycle_summary = self._build_cycle_publication_summary(
            source_row_count=int(len(group.index)) + int(len(group_skipped)),
            review_frame=review_frame,
            skipped_duplicate_count=int(len(group_skipped)),
            threshold_policy=threshold_policy,
            group_skipped=group_skipped,
        )

        review_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="store-prediction-review",
            extension="csv",
            collision_key=collision_key,
        )
        pos_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="pos-order-upload",
            extension="csv",
            collision_key=collision_key,
        )
        summary_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="promotion-summary",
            extension="csv",
            collision_key=collision_key,
        )
        reconciliation_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="reconciliation",
            extension="csv",
            collision_key=collision_key,
        )
        diagnostics_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="diagnostics",
            extension="json",
            collision_key=collision_key,
        )
        manifest_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="prediction-manifest",
            extension="json",
            collision_key=collision_key,
        )
        rows_by_demand_evidence_class_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="rows-by-demand-evidence-class",
            extension="csv",
            collision_key=collision_key,
        )
        cold_start_new_line_rows_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="cold-start-new-line-rows",
            extension="csv",
            collision_key=collision_key,
        )
        true_zero_demand_rows_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="true-zero-demand-rows",
            extension="csv",
            collision_key=collision_key,
        )
        artificial_collapse_rows_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="artificial-collapse-rows",
            extension="csv",
            collision_key=collision_key,
        )
        publish_exclusion_reasons_path = artifact_paths.store_prediction_store_promotion_artifact_path(
            run_id=run_id,
            store_number=str(store_number),
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name="publish-exclusion-reasons",
            extension="csv",
            collision_key=collision_key,
        )

        review_frame.to_csv(review_path, index=False)
        pos_frame.to_csv(pos_path, index=False)
        summary_frame = self._build_promotion_summary_frame(review_frame)
        summary_frame.to_csv(summary_path, index=False)
        self._write_demand_evidence_cycle_diagnostics(
            review_frame=review_frame,
            rows_by_demand_evidence_class_path=rows_by_demand_evidence_class_path,
            cold_start_new_line_rows_path=cold_start_new_line_rows_path,
            true_zero_demand_rows_path=true_zero_demand_rows_path,
            artificial_collapse_rows_path=artificial_collapse_rows_path,
            publish_exclusion_reasons_path=publish_exclusion_reasons_path,
        )
        reconciliation_frame = self._build_cycle_reconciliation_frame(
            expected_group=group,
            review_frame=review_frame,
            cycle_summary=cycle_summary,
        )
        reconciliation_frame.to_csv(reconciliation_path, index=False)
        diagnostics_payload = {
            "client_name": str(client_name),
            "store_number": str(store_number),
            "promotion_cycle_id": prediction_stem,
            "promotion_header_key": str(promotion_header_key),
            "publication_summary": cycle_summary,
            "pos_exclusion_reason_counts": self._build_pos_exclusion_reason_counts(review_frame),
            "skip_reason_counts": self._build_skip_reason_counts(
                review_frame=review_frame,
                group_skipped=group_skipped,
            ),
            "demand_evidence_counts": self._build_demand_evidence_counts(review_frame),
            "validation": {
                "status": "passed",
                "duplicate_key_check": "passed",
                "required_fields_check": "passed",
                "row_count_check": "passed",
                "upload_schema_check": "passed",
            },
            "reconciliation_status": _reconciliation_status(reconciliation_frame),
            "skipped_duplicate_predictions": int(len(group_skipped)),
            "created_at": created_at,
        }
        diagnostics_path.write_text(
            json.dumps(diagnostics_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        manifest_payload = {
            "client_name": str(client_name),
            "store_name": _first_non_empty(group, "store_name"),
            "store_number": str(store_number),
            "promotion_cycle_id": prediction_stem,
            "promotion_header_key": str(promotion_header_key),
            "prediction_run_id": run_id,
            "model_version": model_version,
            "prediction_cutoff_date": as_of_date,
            "planning_horizon_days": planning_horizon_days,
            "row_count": int(len(review_frame.index)),
            "sku_count": int(review_frame["sku_number"].astype(str).nunique(dropna=True)),
            "promotion_count": int(review_frame["promotion_header_key"].astype(str).nunique(dropna=True)),
            "publication_summary": cycle_summary,
            "output_files": {
                "pos_order_upload_csv": str(pos_path),
                "store_prediction_review_csv": str(review_path),
                "promotion_summary_csv": str(summary_path),
                "reconciliation_csv": str(reconciliation_path),
                "diagnostics_json": str(diagnostics_path),
                "rows_by_demand_evidence_class_csv": str(rows_by_demand_evidence_class_path),
                "cold_start_new_line_rows_csv": str(cold_start_new_line_rows_path),
                "true_zero_demand_rows_csv": str(true_zero_demand_rows_path),
                "artificial_collapse_rows_csv": str(artificial_collapse_rows_path),
                "publish_exclusion_reasons_csv": str(publish_exclusion_reasons_path),
            },
            "reconciliation_status": _reconciliation_status(reconciliation_frame),
            "upload_schema_valid": True,
            "created_at": created_at,
        }
        manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        self._validate_manifest_row_counts(
            manifest_payload=manifest_payload,
            review_frame=review_frame,
            summary_frame=summary_frame,
            pos_frame=pos_frame,
        )

        publication_summary_rows = self._build_publication_summary_rows(
            run_id=run_id,
            created_at=created_at,
            reconciliation_frame=reconciliation_frame,
            store_number=str(store_number),
            client_name=str(client_name),
            review_path=str(review_path),
            manifest_payload=manifest_payload,
            cycle_summary=cycle_summary,
            skipped_row_count=int(cycle_summary["skipped_row_count"]),
        )

        return {
            "manifest_path": str(manifest_path),
            "pos_path": str(pos_path),
            "review_path": str(review_path),
            "summary_path": str(summary_path),
            "reconciliation_path": str(reconciliation_path),
            "diagnostics_path": str(diagnostics_path),
            "publication_summary_rows": publication_summary_rows,
            "cycle_summary": cycle_summary,
            "review_frame": review_frame,
        }

    def _build_noop_publish_artifacts(
        self,
        *,
        run_id: str,
        created_at: str,
        candidate_row_count: int,
        skipped_rows: list[dict[str, object]],
        run_skip_counts: dict[str, int],
        prior_publication_detected_flag: bool,
        registry_path: str,
        artifact_paths: PromotionArtifactPaths,
        candidate_gate_counts: dict[str, int] | None = None,
    ) -> PromotionStoreExecutionPublishArtifacts:
        """Write NOOP diagnostics and build publish artifacts when no rows are publishable."""
        publication_summary_path = artifact_paths.commercial_publication_summary_csv_path(run_id)
        publication_summary_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostics_path = publication_summary_path.parent / "publication_noop_diagnostics.json"

        publish_status, publish_status_reason = self._classify_zero_publish_outcome(
            candidate_row_count=candidate_row_count,
            skipped_rows=skipped_rows,
        )
        source_row_count = int((candidate_gate_counts or {}).get("store_download_input_row_count", candidate_row_count))
        registry_duplicate_count = int(run_skip_counts["skipped_due_to_registry_duplicate_count"])
        all_candidates_already_published = publish_status == PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED
        pos_candidate_row_count = 0 if all_candidates_already_published else int(candidate_row_count)
        pos_excluded_row_count = 0 if all_candidates_already_published else int(candidate_row_count)
        review_only_row_count = 0 if all_candidates_already_published else int(run_skip_counts["skipped_due_to_review_count"])
        skipped_due_to_review_count = 0 if all_candidates_already_published else int(run_skip_counts["skipped_due_to_review_count"])
        skipped_due_to_schema_count = 0 if all_candidates_already_published else int(run_skip_counts["skipped_due_to_schema_count"])
        skipped_due_to_mapping_count = 0 if all_candidates_already_published else int(run_skip_counts["skipped_due_to_mapping_count"])
        skipped_due_to_null_sku_count = 0 if all_candidates_already_published else int(run_skip_counts["skipped_due_to_null_sku_count"])
        excluded_defect_row_count = 0 if all_candidates_already_published else int(
            candidate_row_count - run_skip_counts["skipped_due_to_review_count"]
        )
        summary_row = {
            "run_id": run_id,
            "client_name": "",
            "store_number": "",
            "promotion_cycle_id": "",
            "file_type": "store_promotion_pack",
            "file_path": "",
            "source_row_count": source_row_count,
            "candidate_row_count": int(candidate_row_count),
            "pos_candidate_row_count": pos_candidate_row_count,
            "pos_published_row_count": 0,
            "pos_excluded_row_count": pos_excluded_row_count,
            "publish_eligible_row_count": 0,
            "review_only_row_count": review_only_row_count,
            "excluded_legitimate_row_count": 0,
            "excluded_defect_row_count": excluded_defect_row_count,
            "null_sku_excluded_row_count": skipped_due_to_null_sku_count,
            "review_row_count": review_only_row_count,
            "skipped_row_count": int(len(skipped_rows)),
            "skipped_due_to_registry_duplicate_count": registry_duplicate_count,
            "skipped_due_to_review_count": skipped_due_to_review_count,
            "skipped_due_to_schema_count": skipped_due_to_schema_count,
            "skipped_due_to_mapping_count": skipped_due_to_mapping_count,
            "skipped_due_to_null_sku_count": skipped_due_to_null_sku_count,
            "demand_true_zero_count": 0,
            "demand_cold_start_count": 0,
            "demand_low_nonzero_count": 0,
            "demand_artificial_collapse_count": 0,
            "publish_status": publish_status,
            "publish_status_reason": publish_status_reason,
            "publish_status_message": _publish_status_message(
                publish_status=publish_status,
                publish_status_reason=publish_status_reason,
            ),
            "reconciliation_status": "FAIL" if publish_status != PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED else "PASS",
            "upload_schema_valid": False,
            "cycle_identity_present_flag": 0,
            "prior_publication_detected_flag": 1 if prior_publication_detected_flag else 0,
            "generated_at": created_at,
        }
        pd.DataFrame([summary_row]).to_csv(publication_summary_path, index=False)

        run_diagnostics_paths = self._write_publish_eligibility_run_diagnostics(
            diagnostics_root=publication_summary_path.parent,
            review_frames=[],
            source_row_count=source_row_count,
            post_identity_row_count=int(candidate_row_count),
            post_policy_row_count=pos_candidate_row_count,
            final_published_row_count=0,
            publication_summary_frame=pd.DataFrame([summary_row]),
            run_id=run_id,
            created_at=created_at,
        )

        diagnostics_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "publish_status": publish_status,
                    "publish_status_reason": publish_status_reason,
                    "operator_message": (
                        _publish_status_message(
                            publish_status=publish_status,
                            publish_status_reason=publish_status_reason,
                        )
                    ),
                    "source_row_count": source_row_count,
                    "skipped_row_count": int(len(skipped_rows)),
                    "skip_reason_counts": run_skip_counts,
                    "candidate_gate_counts": candidate_gate_counts or {},
                    "prior_publication_detected_flag": prior_publication_detected_flag,
                    "created_at": created_at,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        return PromotionStoreExecutionPublishArtifacts(
            prediction_registry_path=registry_path,
            store_cycle_manifest_paths=tuple(),
            pos_upload_paths=tuple(),
            review_paths=tuple(),
            summary_paths=tuple(),
            reconciliation_paths=tuple(),
            diagnostics_paths=(str(diagnostics_path), *run_diagnostics_paths),
            skipped_paths=tuple(),
            publication_summary_path=str(publication_summary_path),
            stores_published=0,
            promotion_cycles_published=0,
            pos_upload_row_count=0,
            pos_excluded_row_count=pos_excluded_row_count,
            skipped_duplicate_prediction_count=len(skipped_rows),
            skipped_due_to_registry_duplicate_count=registry_duplicate_count,
            skipped_due_to_review_count=skipped_due_to_review_count,
            skipped_due_to_schema_count=skipped_due_to_schema_count,
            skipped_due_to_mapping_count=skipped_due_to_mapping_count,
            skipped_due_to_null_sku_count=skipped_due_to_null_sku_count,
            candidate_row_count=int(candidate_row_count),
            pos_candidate_row_count=pos_candidate_row_count,
            prior_publication_detected_flag=prior_publication_detected_flag,
            noop_already_published_flag=(publish_status == PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED),
            publish_status=publish_status,
            publish_status_reason=publish_status_reason,
        )

    def _eligible_scored_rows(
        self,
        *,
        frame: pd.DataFrame,
        cutoff_date: date,
        horizon_date: date,
    ) -> pd.DataFrame:
        work = frame.copy()
        promotion_start = pd.to_datetime(
            work.get("promotion_start_date_date", work.get("promotion_start_date")),
            errors="coerce",
        )
        work["_promotion_start"] = promotion_start.dt.date
        valid_scope = work.get("store_number", pd.Series(pd.NA, index=work.index)).notna()
        eligible = (
            work["_promotion_start"].notna()
            & (work["_promotion_start"] > cutoff_date)
            & (work["_promotion_start"] <= horizon_date)
            & valid_scope
        )
        return work.loc[eligible].reset_index(drop=True)

    def _build_publish_base(
        self,
        *,
        run_id: str,
        created_at: str,
        scored_frame: pd.DataFrame,
        store_download_frame: pd.DataFrame,
        resolver: PromotionStoreClientResolver,
    ) -> tuple[list[dict[str, object]], dict[str, int]]:
        download_work = self._prepare_download_publish_work(store_download_frame)
        eligible_keys = self._build_eligible_identity_keys(download_work)
        scored_identity, scored_scope_identity = self._build_scored_identity_sets(scored_frame)

        filtered: list[dict[str, object]] = []
        rejected_not_in_scored_scope_count = 0
        rejected_not_in_eligible_key_count = 0
        for row in download_work.to_dict(orient="records"):
            decision = self._download_row_gate_decision(
                row=row,
                scored_identity=scored_identity,
                scored_scope_identity=scored_scope_identity,
                eligible_keys=eligible_keys,
            )
            if decision["include"]:
                filtered.append(row)
                continue
            if not decision["in_scored_scope"]:
                rejected_not_in_scored_scope_count += 1
            if not decision["in_eligible_keys"]:
                rejected_not_in_eligible_key_count += 1

        for row in filtered:
            self._enrich_publish_row_with_mapping(
                row=row,
                resolver=resolver,
                run_id=run_id,
                created_at=created_at,
            )
        candidate_gate_counts = {
            "download_work_row_count": int(len(download_work.index)),
            "eligible_identity_key_count": int(len(eligible_keys)),
            "scored_identity_key_count": int(len(scored_identity)),
            "scored_scope_identity_count": int(len(scored_scope_identity)),
            "publish_base_row_count": int(len(filtered)),
            "rejected_not_in_scored_scope_count": int(rejected_not_in_scored_scope_count),
            "rejected_not_in_eligible_key_count": int(rejected_not_in_eligible_key_count),
        }
        return filtered, candidate_gate_counts

    def _prepare_download_publish_work(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Normalize Stage 11 dates into publisher-friendly columns."""
        download_work = frame.copy()
        download_work["promotion_start_date"] = pd.to_datetime(
            download_work["promotion_start_date"],
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")
        download_work["promotion_break_date"] = pd.to_datetime(
            download_work["promotion_end_date"],
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")
        return download_work

    def _build_eligible_identity_keys(self, download_work: pd.DataFrame) -> set[str]:
        """Build publish identity keys from eligible Stage 11 store rows."""
        return {
            _publish_identity_key(
                store_number=row.store_number,
                promotion_id=_coalesce(
                    getattr(row, "promotion_id", None),
                    getattr(row, "promotional_sku_id_key", None),
                    getattr(row, "promotion_header_key", None),
                ),
                promotion_start_date=row.promotion_start_date,
                promotion_break_date=row.promotion_break_date,
                sku_number=row.sku_number,
            )
            for row in download_work.itertuples(index=False)
            if row.promotion_start_date is not None
        }

    def _build_scored_identity_sets(
        self,
        scored_frame: pd.DataFrame,
    ) -> tuple[set[str], set[tuple[str, str, str, str]]]:
        """Build scored identity sets used to reconcile Stage 12 publish scope."""
        scored_identity = {
            _publish_identity_key(
                store_number=row.store_number,
                promotion_id=_coalesce(
                    getattr(row, "promotion_id", None),
                    getattr(row, "promotional_sku_id_key", None),
                ),
                promotion_start_date=_as_date_string(
                    _coalesce(getattr(row, "promotion_start_date_date", None), getattr(row, "promotion_start_date", None))
                ),
                promotion_break_date=_as_date_string(
                    _coalesce(getattr(row, "promotional_end_date_date", None), getattr(row, "promotion_end_date", None))
                ),
                sku_number=getattr(row, "sku_number", None),
            )
            for row in scored_frame.itertuples(index=False)
        }
        scored_scope_identity = {
            (
                _identity_token(getattr(row, "store_number", "")),
                _as_date_string(_coalesce(getattr(row, "promotion_start_date_date", None), getattr(row, "promotion_start_date", None))),
                _as_date_string(_coalesce(getattr(row, "promotional_end_date_date", None), getattr(row, "promotion_end_date", None))),
                _identity_token(getattr(row, "sku_number", "")),
            )
            for row in scored_frame.itertuples(index=False)
        }
        return scored_identity, scored_scope_identity

    def _is_download_row_scored_and_eligible(
        self,
        *,
        row: dict[str, object],
        scored_identity: set[str],
        scored_scope_identity: set[tuple[str, str, str, str]],
        eligible_keys: set[str],
    ) -> bool:
        """Return whether a Stage 11 row is in the scored scope and eligible publish key set."""
        decision = self._download_row_gate_decision(
            row=row,
            scored_identity=scored_identity,
            scored_scope_identity=scored_scope_identity,
            eligible_keys=eligible_keys,
        )
        return bool(decision["include"])

    def _download_row_gate_decision(
        self,
        *,
        row: dict[str, object],
        scored_identity: set[str],
        scored_scope_identity: set[tuple[str, str, str, str]],
        eligible_keys: set[str],
    ) -> dict[str, object]:
        """Classify whether a Stage 11 row survives scored-scope and eligibility-key gates."""
        identity_key = _publish_identity_key(
            store_number=row.get("store_number"),
            promotion_id=_coalesce(
                row.get("promotion_id"),
                row.get("promotional_sku_id_key"),
                row.get("promotion_header_key"),
            ),
            promotion_start_date=row.get("promotion_start_date"),
            promotion_break_date=row.get("promotion_break_date"),
            sku_number=row.get("sku_number"),
        )
        in_scored_scope = (
            identity_key in scored_identity
            or (
                _identity_token(row.get("store_number", "")),
                _as_date_string(row.get("promotion_start_date")),
                _as_date_string(row.get("promotion_break_date")),
                _identity_token(row.get("sku_number", "")),
            )
            in scored_scope_identity
        )
        in_eligible_keys = identity_key in eligible_keys
        return {
            "identity_key": identity_key,
            "in_scored_scope": in_scored_scope,
            "in_eligible_keys": in_eligible_keys,
            "include": in_scored_scope and in_eligible_keys,
        }

    def _enrich_publish_row_with_mapping(
        self,
        *,
        row: dict[str, object],
        resolver: PromotionStoreClientResolver,
        run_id: str,
        created_at: str,
    ) -> None:
        """Hydrate a publish row with store mapping and canonical Stage 12 fields."""
        try:
            mapping = resolver.resolve(row.get("store_number"))
        except PromotionStoreClientMappingError as exc:
            raise PromotionStoreExecutionValidationError(str(exc)) from exc

        row["store_mapping_resolved_flag"] = 1
        row["store_mapping_active_flag"] = 1
        row["store_mapping_error"] = ""

        row["client_code"] = mapping.client_code
        row["client_name"] = mapping.client_name
        row["banner_code"] = mapping.client_code
        row["store_name"] = mapping.store_name
        row["store_slug"] = mapping.store_slug
        row["upload_target_name"] = mapping.upload_target_name
        row["pos_format_name"] = mapping.pos_format_name
        row["promotion_id"] = _coalesce(row.get("promotion_id"), row.get("promotional_sku_id_key"), row.get("promotion_header_key"))
        row["promotion_header_key"] = _coalesce(row.get("promotion_header_key"), row.get("promotion_id"), row.get("promotional_sku_id_key"))
        row["promotion_break_date"] = row.get("promotion_break_date")
        row["expected_sales_to_break_date"] = float(
            row.get("predicted_units_until_promo_start")
            or row.get("predicted_units_sold")
            or 0.0
        )
        row["forecast_promo_units"] = float(
            row.get("predicted_units_total_promo")
            or row.get("predicted_units_sold")
            or 0.0
        )
        row["recommended_order_quantity"] = float(
            row.get("suggested_order_units")
            or row.get("recommended_order_units")
            or 0.0
        )
        row["target_soh_on_break_date"] = float(
            (row.get("promo_start_target_soh_units") or 0.0)
        )
        row["decision_action"] = _coalesce(
            row.get("decision_recommendation"),
            row.get("action_code"),
            "HOLD",
        )
        row["confidence_score"] = float(row.get("final_confidence_score") or 0.0)
        row["prediction_run_id"] = run_id
        row["prediction_created_at"] = created_at
        decision_text = str(row.get("decision_action", "")).strip().upper()
        row["manual_review_flag"] = _review_flag_value(row.get("manual_review_flag"))
        if decision_text == "REVIEW":
            row["manual_review_flag"] = 1
        row["review_required_flag"] = _review_flag_value(row.get("review_required_flag"))
        if decision_text == "REVIEW":
            row["review_required_flag"] = 1

        demand_classification = classify_demand_evidence_row(
            {
                "predicted_units_total_promo": row.get("predicted_units_total_promo"),
                "forecast_promo_units": row.get("forecast_promo_units"),
                "forecast_zero_demand_classification": row.get("forecast_zero_demand_classification"),
                "forecast_collapse_requires_review_flag": row.get("forecast_collapse_requires_review_flag"),
                "raw_history_units": row.get("raw_history_units"),
                "raw_predicted_units_sold": row.get("raw_predicted_units_sold"),
                "raw_demand_reference_units": row.get("raw_demand_reference_units"),
                "raw_baseline_expected_units": row.get("raw_baseline_expected_units"),
                "promotion_name": row.get("promotion_name"),
                "promo_type": row.get("promo_type"),
                "promotion_header_key": row.get("promotion_header_key"),
                "insufficient_history_flag": row.get("insufficient_history_flag"),
                "cold_start_flag": row.get("cold_start_flag"),
            }
        )
        row["demand_evidence_class"] = str(
            row.get("demand_evidence_class") or demand_classification.demand_evidence_class
        )
        row["cold_start_flag"] = int(_review_flag_value(row.get("cold_start_flag")) or demand_classification.cold_start_flag)
        row["insufficient_history_flag"] = int(
            _review_flag_value(row.get("insufficient_history_flag")) or demand_classification.insufficient_history_flag
        )
        row["artificial_collapse_flag"] = int(demand_classification.artificial_collapse_flag)
        row["publish_eligibility_reason"] = str(
            row.get("publish_eligibility_reason") or demand_classification.publish_eligibility_reason
        )
        row["review_reason"] = str(row.get("review_reason") or demand_classification.review_reason)
        if demand_classification.requires_review == 1:
            row["review_required_flag"] = 1

    def _apply_registry_policy(
        self,
        *,
        candidate_rows: list[dict[str, object]],
        registry_frame: pd.DataFrame,
        allow_reprediction: bool,
        model_version: str,
        run_id: str,
        cutoff_date: date,
        created_at: str,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]], pd.DataFrame]:
        publish_rows: list[dict[str, object]] = []
        skipped_rows: list[dict[str, object]] = []

        existing = registry_frame.copy()
        if existing.empty:
            existing = pd.DataFrame(columns=_registry_columns())

        for row in candidate_rows:
            identity_key = _prediction_identity_key(
                client_code=row.get("client_code"),
                store_number=row.get("store_number"),
                promotion_id=row.get("promotion_id"),
                promotion_start_date=row.get("promotion_start_date"),
                promotion_break_date=row.get("promotion_break_date"),
                sku_number=row.get("sku_number"),
                prediction_cutoff_date=cutoff_date.isoformat(),
            )
            prior = existing.loc[existing["prediction_identity_key"] == identity_key]
            if not prior.empty and not allow_reprediction:
                skipped_rows.append(
                    {
                        "prediction_identity_key": identity_key,
                        "store_number": str(row.get("store_number")),
                        "promotion_cycle_id": _promotion_cycle_id(row.get("promotion_start_date")),
                        "promotion_header_key": str(row.get("promotion_header_key", "")),
                        "promotion_id": str(row.get("promotion_id")),
                        "sku_number": str(row.get("sku_number")),
                        "reason": "already_predicted",
                    }
                )
                continue

            prior_versions = prior["prediction_version"].tolist() if not prior.empty else []
            next_version = int(max(prior_versions)) + 1 if prior_versions else 1
            prediction_key = _sha256(
                f"{identity_key}|v{next_version}|{model_version}|{created_at}"
            )
            supersedes_prediction_key = ""
            if not prior.empty and allow_reprediction:
                active_prior = prior.loc[prior["status"] == "active"]
                if not active_prior.empty:
                    supersedes_prediction_key = str(active_prior.iloc[-1]["prediction_key"])
                    existing.loc[
                        existing["prediction_key"].eq(supersedes_prediction_key),
                        ["status"],
                    ] = "superseded"

            registry_row = {
                "prediction_identity_key": identity_key,
                "prediction_key": prediction_key,
                "prediction_version": next_version,
                "supersedes_prediction_key": supersedes_prediction_key,
                "client_code": str(row.get("client_code")),
                "store_number": str(row.get("store_number")),
                "promotion_id": str(row.get("promotion_id")),
                "sku_number": str(row.get("sku_number")),
                "promotion_start_date": str(row.get("promotion_start_date")),
                "promotion_break_date": str(row.get("promotion_break_date")),
                "prediction_run_id": run_id,
                "prediction_created_at": created_at,
                "output_file_path": "",
                "model_version": model_version,
                "prediction_cutoff_date": cutoff_date.isoformat(),
                "status": "active",
            }
            existing = pd.concat([existing, pd.DataFrame([registry_row])], ignore_index=True)
            row["prediction_identity_key"] = identity_key
            row["prediction_key"] = prediction_key
            row["prediction_version"] = next_version
            row["model_version"] = model_version
            publish_rows.append(row)

        return publish_rows, skipped_rows, existing

    def _build_review_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        recommended_order_quantity = pd.to_numeric(frame["recommended_order_quantity"], errors="coerce")
        upload_ready_order_units = recommended_order_quantity.round(0)
        upload_ready_order_units = upload_ready_order_units.where(
            recommended_order_quantity.notna(),
            pd.NA,
        )
        sku_number_series = frame["sku_number"]
        raw_description = frame.get("product_description", frame.get("sku_description", ""))
        sku_description_series = pd.Series(raw_description, index=frame.index).astype(str)
        blank_description = sku_description_series.str.strip().isin({"", "nan", "none", "<na>"})
        sku_description_series = sku_description_series.where(
            ~blank_description,
            "SKU " + sku_number_series.astype(str),
        )
        review_frame = pd.DataFrame(
            {
                "client_code": frame["client_code"].astype(str),
                "banner_code": frame["banner_code"].astype(str),
                "store_number": frame["store_number"],
                "store_name": frame["store_name"].astype(str),
                "promotion_id": frame["promotion_id"].astype(str),
                "promotion_name": frame["promotion_name"].astype(str),
                "promotion_start_date": frame["promotion_start_date"].astype(str),
                "promotion_break_date": frame["promotion_break_date"].astype(str),
                "promotion_header_key": frame["promotion_header_key"].astype(str),
                "sku_number": frame["sku_number"],
                "sku_description": sku_description_series,
                "current_soh": pd.to_numeric(frame.get("current_soh", frame.get("current_soh_units")), errors="coerce"),
                "expected_sales_to_break_date": pd.to_numeric(frame["expected_sales_to_break_date"], errors="coerce"),
                "forecast_promo_units": pd.to_numeric(frame["forecast_promo_units"], errors="coerce"),
                "recommended_order_quantity": recommended_order_quantity,
                "upload_ready_order_units": upload_ready_order_units,
                "target_soh_on_break_date": pd.to_numeric(frame["target_soh_on_break_date"], errors="coerce"),
                "decision_action": frame["decision_action"].astype(str),
                "decision_reason": frame["client_reason"].astype(str),
                "confidence_score": pd.to_numeric(frame["confidence_score"], errors="coerce"),
                "manual_review_flag": frame.get("manual_review_flag", 0),
                "review_required_flag": frame.get("review_required_flag", 0),
                "store_mapping_resolved_flag": frame.get("store_mapping_resolved_flag", 1),
                "store_mapping_active_flag": frame.get("store_mapping_active_flag", 1),
                "store_mapping_error": frame.get("store_mapping_error", ""),
                "model_version": frame["model_version"].astype(str),
                "prediction_run_id": frame["prediction_run_id"].astype(str),
                "prediction_created_at": frame["prediction_created_at"].astype(str),
                "demand_evidence_class": frame.get("demand_evidence_class", "").astype(str),
                "cold_start_flag": frame.get("cold_start_flag", 0),
                "insufficient_history_flag": frame.get("insufficient_history_flag", 0),
                "publish_eligibility_reason": frame.get("publish_eligibility_reason", "").astype(str),
                "review_reason": frame.get("review_reason", "").astype(str),
            }
        )
        review_frame["manual_review_flag"] = review_frame["manual_review_flag"].apply(_review_flag_value)
        review_frame["review_required_flag"] = review_frame["review_required_flag"].apply(_review_flag_value)
        review_frame["store_mapping_resolved_flag"] = review_frame["store_mapping_resolved_flag"].apply(_review_flag_value)
        review_frame["store_mapping_active_flag"] = review_frame["store_mapping_active_flag"].apply(_review_flag_value)
        return review_frame

    def _annotate_pos_eligibility(self, review_frame: pd.DataFrame) -> pd.DataFrame:
        frame = review_frame.copy()
        evaluations = [
            self._evaluate_publish_eligibility_row(row)
            for row in frame.itertuples(index=False)
        ]
        frame["pos_eligible_flag"] = [entry.pos_eligible_flag for entry in evaluations]
        frame["missing_required_pos_field_flag"] = [
            1 if entry.exclusion_reason_primary == "missing_required_pos_field" else 0
            for entry in evaluations
        ]
        frame["null_sku_flag"] = [
            1 if entry.exclusion_reason_primary == "null_sku" else 0
            for entry in evaluations
        ]
        frame["invalid_order_quantity_flag"] = [
            1 if entry.exclusion_reason_primary == "invalid_order_quantity" else 0
            for entry in evaluations
        ]
        frame["unresolved_store_mapping_flag"] = [
            1 if entry.exclusion_reason_primary == "unresolved_store_mapping" else 0
            for entry in evaluations
        ]
        frame["exclusion_reason_primary"] = [entry.exclusion_reason_primary for entry in evaluations]
        frame["exclusion_reason_secondary"] = [entry.exclusion_reason_secondary for entry in evaluations]
        frame["publish_eligibility_class"] = [entry.publish_eligibility_class for entry in evaluations]
        frame["publish_eligibility_reason"] = [entry.publish_eligibility_reason for entry in evaluations]
        frame["publish_noop_reason"] = [entry.publish_noop_reason for entry in evaluations]
        frame["review_required_flag"] = [entry.review_required_flag for entry in evaluations]
        frame["excluded_from_publish_flag"] = [entry.excluded_from_publish_flag for entry in evaluations]
        frame["excluded_from_publish_reason"] = [entry.excluded_from_publish_reason for entry in evaluations]
        frame["publish_defect_flag"] = [entry.defect_flag for entry in evaluations]
        frame["publish_policy_contradiction_flag"] = [entry.policy_contradiction_flag for entry in evaluations]
        return frame

    def _evaluate_publish_eligibility_row(self, row: object) -> PublishEligibilityEvaluation:
        required_pos_fields = ("store_number", "sku_description", "target_soh_on_break_date")
        defect_reasons: list[str] = []

        if _is_blank(getattr(row, "sku_number", None)):
            defect_reasons.append("null_sku")

        if any(_is_blank(getattr(row, field, None)) for field in required_pos_fields):
            defect_reasons.append("missing_required_pos_field")

        upload_qty = pd.to_numeric(getattr(row, "upload_ready_order_units", None), errors="coerce")
        invalid_order_quantity = bool(
            pd.isna(upload_qty)
            or upload_qty < 0
            or upload_qty != round(float(upload_qty), 0)
        )
        if invalid_order_quantity:
            defect_reasons.append("invalid_order_quantity")

        unresolved_mapping = (
            _review_flag_value(getattr(row, "store_mapping_resolved_flag", 1)) != 1
            or _review_flag_value(getattr(row, "store_mapping_active_flag", 1)) != 1
        )
        if unresolved_mapping:
            defect_reasons.append("unresolved_store_mapping")

        demand_class = str(getattr(row, "demand_evidence_class", "") or "").strip()
        decision_action = str(getattr(row, "decision_action", "") or "").strip().upper()
        review_reason_text = str(getattr(row, "review_reason", "") or "").strip()
        publish_reason_text = str(getattr(row, "publish_eligibility_reason", "") or "").strip()
        manual_review = _review_flag_value(getattr(row, "manual_review_flag", 0)) == 1
        review_required = _review_flag_value(getattr(row, "review_required_flag", 0)) == 1

        if defect_reasons:
            primary = defect_reasons[0]
            secondary = defect_reasons[1] if len(defect_reasons) > 1 else ""
            return PublishEligibilityEvaluation(
                publish_eligibility_class=PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_DEFECT,
                publish_eligibility_reason=primary,
                publish_noop_reason="defect_rows_present",
                review_required_flag=1 if (manual_review or review_required) else 0,
                excluded_from_publish_flag=1,
                excluded_from_publish_reason=primary,
                pos_eligible_flag=0,
                exclusion_reason_primary=primary,
                exclusion_reason_secondary=secondary,
                defect_flag=1,
                policy_contradiction_flag=0,
            )

        review_only_reason = ""
        if manual_review:
            review_only_reason = "manual_review"
        elif review_required:
            review_only_reason = "review_required"
        elif decision_action == "REVIEW":
            review_only_reason = "review_action"
        elif demand_class == DEMAND_EVIDENCE_CLASS_COLD_START:
            review_only_reason = "cold_start_new_line"
        elif demand_class == DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE:
            review_only_reason = "artificial_collapse"
        elif review_reason_text:
            review_only_reason = review_reason_text

        if review_only_reason:
            return PublishEligibilityEvaluation(
                publish_eligibility_class=PUBLISH_ELIGIBILITY_CLASS_REVIEW_ONLY,
                publish_eligibility_reason=review_only_reason,
                publish_noop_reason="review_only_rows_present",
                review_required_flag=1,
                excluded_from_publish_flag=1,
                excluded_from_publish_reason=review_only_reason,
                pos_eligible_flag=0,
                exclusion_reason_primary=review_only_reason,
                exclusion_reason_secondary="",
                defect_flag=0,
                policy_contradiction_flag=0,
            )

        legitimate_reason = ""
        if demand_class == DEMAND_EVIDENCE_CLASS_TRUE_ZERO:
            legitimate_reason = "true_zero_demand"
        elif publish_reason_text.startswith("excluded_true_zero"):
            legitimate_reason = "true_zero_demand"

        if legitimate_reason:
            return PublishEligibilityEvaluation(
                publish_eligibility_class=PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_LEGITIMATE,
                publish_eligibility_reason=legitimate_reason,
                publish_noop_reason="legitimate_non_publishable_rows",
                review_required_flag=0,
                excluded_from_publish_flag=1,
                excluded_from_publish_reason=legitimate_reason,
                pos_eligible_flag=0,
                exclusion_reason_primary=legitimate_reason,
                exclusion_reason_secondary="",
                defect_flag=0,
                policy_contradiction_flag=0,
            )

        publish_reason = publish_reason_text if publish_reason_text.startswith("eligible") else "eligible_publish"
        return PublishEligibilityEvaluation(
            publish_eligibility_class=PUBLISH_ELIGIBILITY_CLASS_PUBLISH_ELIGIBLE,
            publish_eligibility_reason=publish_reason,
            publish_noop_reason="",
            review_required_flag=0,
            excluded_from_publish_flag=0,
            excluded_from_publish_reason="",
            pos_eligible_flag=1,
            exclusion_reason_primary="",
            exclusion_reason_secondary="",
            defect_flag=0,
            policy_contradiction_flag=0,
        )

    def _build_demand_evidence_counts(self, review_frame: pd.DataFrame) -> dict[str, int]:
        if "demand_evidence_class" not in review_frame.columns:
            return {}
        counts = review_frame["demand_evidence_class"].astype(str).value_counts(dropna=False).to_dict()
        return {str(key): int(value) for key, value in counts.items() if str(key).strip()}

    def _write_demand_evidence_cycle_diagnostics(
        self,
        *,
        review_frame: pd.DataFrame,
        rows_by_demand_evidence_class_path: Path,
        cold_start_new_line_rows_path: Path,
        true_zero_demand_rows_path: Path,
        artificial_collapse_rows_path: Path,
        publish_exclusion_reasons_path: Path,
    ) -> None:
        work = review_frame.copy()
        if "demand_evidence_class" not in work.columns:
            work["demand_evidence_class"] = ""
        demand_counts = (
            work.groupby("demand_evidence_class", dropna=False)
            .size()
            .rename("row_count")
            .reset_index()
        )
        demand_counts.to_csv(rows_by_demand_evidence_class_path, index=False)

        work.loc[work["demand_evidence_class"].astype(str).eq(DEMAND_EVIDENCE_CLASS_COLD_START)].to_csv(
            cold_start_new_line_rows_path,
            index=False,
        )
        work.loc[work["demand_evidence_class"].astype(str).eq(DEMAND_EVIDENCE_CLASS_TRUE_ZERO)].to_csv(
            true_zero_demand_rows_path,
            index=False,
        )
        work.loc[work["demand_evidence_class"].astype(str).eq(DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE)].to_csv(
            artificial_collapse_rows_path,
            index=False,
        )

        if "exclusion_reason_primary" in work.columns:
            exclusion_counts = (
                work.loc[work["pos_eligible_flag"].astype(int).eq(0), "exclusion_reason_primary"]
                .astype(str)
                .value_counts(dropna=False)
                .rename_axis("publish_exclusion_reason")
                .reset_index(name="row_count")
            )
        else:
            exclusion_counts = pd.DataFrame(columns=["publish_exclusion_reason", "row_count"])
        exclusion_counts.to_csv(publish_exclusion_reasons_path, index=False)

    def _build_pos_upload_frame(
        self,
        review_frame: pd.DataFrame,
        *,
        pos_schema: PromotionPosUploadSchema,
    ) -> pd.DataFrame:
        return pos_schema.build_frame(review_frame)

    def _build_skipped_frame(
        self,
        *,
        review_frame: pd.DataFrame,
        group_skipped: list[dict[str, object]],
    ) -> pd.DataFrame:
        excluded = review_frame.loc[
            review_frame["pos_eligible_flag"].astype(int).eq(0)
        ].copy()
        excluded["reason"] = excluded["exclusion_reason_primary"].astype(str)
        excluded["source"] = "pos_eligibility_exclusion"
        excluded_columns = [
            "source",
            "store_number",
            "promotion_id",
            "promotion_header_key",
            "sku_number",
            "reason",
            "exclusion_reason_primary",
            "exclusion_reason_secondary",
            "pos_eligible_flag",
            "missing_required_pos_field_flag",
            "null_sku_flag",
            "invalid_order_quantity_flag",
            "unresolved_store_mapping_flag",
        ]
        excluded = excluded[excluded_columns]

        registry_skipped = pd.DataFrame(group_skipped)
        if registry_skipped.empty:
            return excluded.reset_index(drop=True)

        registry_skipped = registry_skipped.copy()
        registry_skipped["source"] = "registry_duplicate_skip"
        registry_skipped["promotion_header_key"] = ""
        registry_skipped["exclusion_reason_primary"] = ""
        registry_skipped["exclusion_reason_secondary"] = ""
        registry_skipped["pos_eligible_flag"] = 0
        registry_skipped["missing_required_pos_field_flag"] = 0
        registry_skipped["null_sku_flag"] = 0
        registry_skipped["invalid_order_quantity_flag"] = 0
        registry_skipped["unresolved_store_mapping_flag"] = 0
        registry_skipped = registry_skipped[
            [
                "source",
                "store_number",
                "promotion_id",
                "promotion_header_key",
                "sku_number",
                "reason",
                "exclusion_reason_primary",
                "exclusion_reason_secondary",
                "pos_eligible_flag",
                "missing_required_pos_field_flag",
                "null_sku_flag",
                "invalid_order_quantity_flag",
                "unresolved_store_mapping_flag",
            ]
        ]
        return pd.concat([excluded, registry_skipped], ignore_index=True)

    def _build_promotion_summary_frame(self, review_frame: pd.DataFrame) -> pd.DataFrame:
        grouped = review_frame.groupby(
            ["store_number", "promotion_id", "promotion_name", "promotion_start_date", "promotion_break_date"],
            sort=False,
            dropna=False,
        )
        rows: list[dict[str, object]] = []
        for (_, _, _, _, _), group in grouped:
            rows.append(
                {
                    "store_number": str(group.iloc[0]["store_number"]),
                    "promotion_id": str(group.iloc[0]["promotion_id"]),
                    "promotion_name": str(group.iloc[0]["promotion_name"]),
                    "promotion_start_date": str(group.iloc[0]["promotion_start_date"]),
                    "promotion_break_date": str(group.iloc[0]["promotion_break_date"]),
                    "row_count": int(len(group.index)),
                    "sku_count": int(group["sku_number"].astype(str).nunique(dropna=True)),
                    "recommended_order_quantity_total": float(
                        pd.to_numeric(group["recommended_order_quantity"], errors="coerce").fillna(0.0).sum()
                    ),
                }
            )
        return pd.DataFrame(rows)

    def _validate_cycle_frames(
        self,
        *,
        review_frame: pd.DataFrame,
        pos_frame: pd.DataFrame,
        pos_eligible_frame: pd.DataFrame,
        expected_group: pd.DataFrame,
        pos_schema: PromotionPosUploadSchema,
    ) -> None:
        expected_keys = {
            _publish_identity_key(
                store_number=row.store_number,
                promotion_id=row.promotion_id,
                promotion_start_date=row.promotion_start_date,
                promotion_break_date=row.promotion_break_date,
                sku_number=row.sku_number,
            )
            for row in expected_group.itertuples(index=False)
        }
        review_keys = {
            _publish_identity_key(
                store_number=row.store_number,
                promotion_id=row.promotion_id,
                promotion_start_date=row.promotion_start_date,
                promotion_break_date=row.promotion_break_date,
                sku_number=row.sku_number,
            )
            for row in review_frame.itertuples(index=False)
        }
        if expected_keys != review_keys:
            raise PromotionStoreExecutionValidationError(
                "Validation failed: review CSV does not contain every eligible promotion SKU row."
            )

        if not pos_frame.empty:
            try:
                pos_schema.validate(pos_frame)
            except PromotionPosUploadSchemaValidationError as exc:
                raise PromotionStoreExecutionValidationError(str(exc)) from exc

        duplicate_count = int(
            pos_eligible_frame[pos_eligible_frame["sku_number"].notna()].duplicated(
                subset=["store_number", "promotion_header_key", "sku_number"],
                keep=False,
            ).sum()
        )
        if duplicate_count > 0:
            raise PromotionStoreExecutionValidationError(
                "Validation failed: duplicate store_number + promotion_header_key + sku_number rows detected."
            )

    def _build_cycle_reconciliation_frame(
        self,
        *,
        expected_group: pd.DataFrame,
        review_frame: pd.DataFrame,
        cycle_summary: dict[str, object],
    ) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        grouped_expected = expected_group.groupby(["promotion_header_key"], sort=False, dropna=False)
        for (promotion_header_key,), source_group in grouped_expected:
            review_group = review_frame.loc[
                review_frame["promotion_header_key"].astype(str).eq(str(promotion_header_key))
            ]
            source_count = int(len(source_group.index))
            output_count = int(len(review_group.index))
            source_sku_count = int(source_group["sku_number"].astype(str).nunique(dropna=True))
            output_sku_count = int(review_group["sku_number"].astype(str).nunique(dropna=True))
            duplicate_count = int(
                review_group[review_group["sku_number"].notna()].duplicated(subset=["store_number", "promotion_header_key", "sku_number"]).sum()
            )
            missing_row_count = max(source_count - output_count, 0)
            status = "PASS"
            reason = "counts_match"
            if duplicate_count > 0:
                status = "FAIL"
                reason = "duplicate_rows_in_output"
            elif source_count != output_count or source_sku_count != output_sku_count:
                status = "FAIL"
                reason = "source_output_count_mismatch"

            action_counts = review_group["decision_action"].astype(str).value_counts(dropna=False).to_dict()
            excluded_count = int(review_group["pos_eligible_flag"].astype(int).eq(0).sum())
            published_count = int(review_group["pos_eligible_flag"].astype(int).eq(1).sum())
            rows.append(
                {
                    "store_number": str(source_group.iloc[0]["store_number"]),
                    "promotion_header_key": str(promotion_header_key),
                    "promotion_id": str(source_group.iloc[0].get("promotion_id", "")),
                    "source_row_count": source_count,
                    "output_row_count": output_count,
                    "source_sku_count": source_sku_count,
                    "output_sku_count": output_sku_count,
                    "order_row_count": int(action_counts.get("ORDER", 0)),
                    "hold_row_count": int(action_counts.get("HOLD", 0)),
                    "review_row_count": int(action_counts.get("REVIEW", 0)),
                    "do_not_order_row_count": int(action_counts.get("DO_NOT_ORDER", 0)),
                    "monitor_row_count": int(action_counts.get("MONITOR", 0)),
                    "missing_row_count": missing_row_count,
                    "duplicate_row_count": duplicate_count,
                    "pos_published_row_count": published_count,
                    "pos_excluded_row_count": excluded_count,
                    "null_sku_excluded_row_count": int(review_group["null_sku_flag"].astype(int).sum()),
                    "status": status,
                    "reason": reason,
                    "publish_status": str(cycle_summary.get("publish_status", "FAIL")),
                    "publish_status_reason": str(cycle_summary.get("publish_status_reason", "")),
                }
            )
        return pd.DataFrame(rows)

    def _build_cycle_publication_summary(
        self,
        *,
        source_row_count: int,
        review_frame: pd.DataFrame,
        skipped_duplicate_count: int,
        threshold_policy: PromotionPosExclusionThresholdPolicy,
        group_skipped: list[dict[str, object]],
    ) -> dict[str, object]:
        pos_candidate_row_count = int(len(review_frame.index))
        pos_published_row_count = int(review_frame["pos_eligible_flag"].astype(int).eq(1).sum())
        pos_excluded_row_count = int(review_frame["pos_eligible_flag"].astype(int).eq(0).sum())
        class_counts = self._build_publish_eligibility_class_counts(review_frame)
        null_sku_excluded_row_count = int(review_frame["null_sku_flag"].astype(int).sum())
        review_row_count = int(class_counts.get(PUBLISH_ELIGIBILITY_CLASS_REVIEW_ONLY, 0))
        demand_counts = self._build_demand_evidence_counts(review_frame)
        publish_status, publish_status_reason = self._evaluate_publish_status(
            pos_candidate_row_count=pos_candidate_row_count,
            pos_published_row_count=pos_published_row_count,
            pos_excluded_row_count=pos_excluded_row_count,
            class_counts=class_counts,
            threshold_policy=threshold_policy,
        )
        skip_reason_counts = self._build_skip_reason_counts(
            review_frame=review_frame,
            group_skipped=group_skipped,
        )
        all_source_rows_are_registry_duplicates = (
            pos_candidate_row_count == 0
            and source_row_count > 0
            and skip_reason_counts["skipped_due_to_registry_duplicate_count"] == source_row_count
        )
        if pos_published_row_count == 0 and all_source_rows_are_registry_duplicates:
            publish_status = PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED
            publish_status_reason = "all_candidates_already_published"
        skipped_row_count = pos_excluded_row_count + int(skipped_duplicate_count)
        return {
            "source_row_count": source_row_count,
            "candidate_row_count": source_row_count,
            "pos_candidate_row_count": pos_candidate_row_count,
            "pos_published_row_count": pos_published_row_count,
            "pos_excluded_row_count": pos_excluded_row_count,
            "publish_eligible_row_count": int(class_counts.get(PUBLISH_ELIGIBILITY_CLASS_PUBLISH_ELIGIBLE, 0)),
            "review_only_row_count": int(class_counts.get(PUBLISH_ELIGIBILITY_CLASS_REVIEW_ONLY, 0)),
            "excluded_legitimate_row_count": int(class_counts.get(PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_LEGITIMATE, 0)),
            "excluded_defect_row_count": int(class_counts.get(PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_DEFECT, 0)),
            "null_sku_excluded_row_count": null_sku_excluded_row_count,
            "review_row_count": review_row_count,
            "skipped_row_count": int(skipped_row_count),
            "skipped_due_to_registry_duplicate_count": int(skip_reason_counts["skipped_due_to_registry_duplicate_count"]),
            "skipped_due_to_review_count": int(skip_reason_counts["skipped_due_to_review_count"]),
            "skipped_due_to_schema_count": int(skip_reason_counts["skipped_due_to_schema_count"]),
            "skipped_due_to_mapping_count": int(skip_reason_counts["skipped_due_to_mapping_count"]),
            "skipped_due_to_null_sku_count": int(skip_reason_counts["skipped_due_to_null_sku_count"]),
            "demand_true_zero_count": int(demand_counts.get(DEMAND_EVIDENCE_CLASS_TRUE_ZERO, 0)),
            "demand_cold_start_count": int(demand_counts.get(DEMAND_EVIDENCE_CLASS_COLD_START, 0)),
            "demand_low_nonzero_count": int(demand_counts.get("low_nonzero_demand", 0)),
            "demand_artificial_collapse_count": int(demand_counts.get(DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE, 0)),
            "publish_status": publish_status,
            "publish_status_reason": publish_status_reason,
            "cycle_identity_present_flag": 1,
            "prior_publication_detected_flag": (
                1 if skip_reason_counts["skipped_due_to_registry_duplicate_count"] > 0 else 0
            ),
        }

    def _evaluate_publish_status(
        self,
        *,
        pos_candidate_row_count: int,
        pos_published_row_count: int,
        pos_excluded_row_count: int,
        class_counts: dict[str, int],
        threshold_policy: PromotionPosExclusionThresholdPolicy,
    ) -> tuple[str, str]:
        if pos_candidate_row_count == 0:
            return PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS, "no_pos_candidates"
        excluded_defect_count = int(class_counts.get(PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_DEFECT, 0))
        review_only_count = int(class_counts.get(PUBLISH_ELIGIBILITY_CLASS_REVIEW_ONLY, 0))
        legitimate_exclusion_count = int(class_counts.get(PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_LEGITIMATE, 0))
        policy_contradiction_count = int(
            review_only_count + legitimate_exclusion_count + excluded_defect_count + pos_published_row_count
            != pos_candidate_row_count
        )
        if policy_contradiction_count > 0:
            return PUBLISH_STATUS_FAIL, "policy_gate_count_contradiction"

        if threshold_policy.fail_if_zero_published and pos_published_row_count == 0:
            if excluded_defect_count == pos_candidate_row_count:
                return PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS, "all_rows_excluded_defect"
            if review_only_count > 0 and legitimate_exclusion_count == 0:
                return PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS, "review_only_rows_no_publish"
            if legitimate_exclusion_count > 0 and review_only_count == 0:
                return PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS, "legitimate_non_publishable_rows"
            if review_only_count > 0 and legitimate_exclusion_count > 0:
                return PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS, "review_and_legitimate_non_publishable_rows"
            return PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS, "no_valid_pos_rows"
        if pos_excluded_row_count > threshold_policy.max_excluded_count:
            return PUBLISH_STATUS_FAIL, "excluded_row_count_above_threshold"
        exclusion_ratio = pos_excluded_row_count / max(pos_candidate_row_count, 1)
        if exclusion_ratio > threshold_policy.max_excluded_ratio:
            return PUBLISH_STATUS_FAIL, "excluded_row_ratio_above_threshold"
        if pos_excluded_row_count > 0:
            return PUBLISH_STATUS_PASS_WITH_EXCLUSIONS, "rows_excluded_by_pos_eligibility"
        return PUBLISH_STATUS_PASS, "all_candidate_rows_published"

    def _build_pos_exclusion_reason_counts(self, review_frame: pd.DataFrame) -> dict[str, int]:
        excluded = review_frame.loc[review_frame["pos_eligible_flag"].astype(int).eq(0)]
        counts = excluded["exclusion_reason_primary"].astype(str).value_counts(dropna=False).to_dict()
        return {str(key): int(value) for key, value in counts.items() if str(key).strip()}

    def _build_publish_eligibility_class_counts(self, review_frame: pd.DataFrame) -> dict[str, int]:
        if "publish_eligibility_class" not in review_frame.columns:
            return {}
        counts = review_frame["publish_eligibility_class"].astype(str).value_counts(dropna=False).to_dict()
        return {str(key): int(value) for key, value in counts.items() if str(key).strip()}

    def _build_skip_reason_counts(
        self,
        *,
        review_frame: pd.DataFrame,
        group_skipped: list[dict[str, object]],
    ) -> dict[str, int]:
        excluded = review_frame.loc[review_frame["pos_eligible_flag"].astype(int).eq(0)]
        registry_duplicate_count = sum(
            1 for row in group_skipped if _reason_matches(row.get("reason", ""), "already_predicted")
        )
        return {
            "skipped_due_to_registry_duplicate_count": int(registry_duplicate_count),
            "skipped_due_to_review_count": int(
                excluded["publish_eligibility_class"].astype(str).eq(PUBLISH_ELIGIBILITY_CLASS_REVIEW_ONLY).sum()
            ) if "publish_eligibility_class" in excluded.columns else 0,
            "skipped_due_to_schema_count": int(
                excluded["exclusion_reason_primary"].astype(str).isin(["missing_required_pos_field", "invalid_order_quantity"]).sum()
            ),
            "skipped_due_to_mapping_count": int(
                excluded["exclusion_reason_primary"].astype(str).eq("unresolved_store_mapping").sum()
            ),
            "skipped_due_to_null_sku_count": int(
                excluded["exclusion_reason_primary"].astype(str).eq("null_sku").sum()
            ),
        }

    def _classify_run_skip_reasons(
        self,
        *,
        candidate_rows: list[dict[str, object]],
        skipped_rows: list[dict[str, object]],
    ) -> dict[str, int]:
        registry_duplicate_count = sum(
            1 for row in skipped_rows if _reason_matches(row.get("reason", ""), "already_predicted")
        )
        review_count = 0
        schema_count = 0
        mapping_count = 0
        null_sku_count = 0
        for row in candidate_rows:
            if _is_blank(row.get("sku_number")):
                null_sku_count += 1
            if _review_flag_value(row.get("manual_review_flag", 0)) == 1 or _review_flag_value(row.get("review_required_flag", 0)) == 1:
                review_count += 1
            order_qty = pd.to_numeric(row.get("recommended_order_quantity"), errors="coerce")
            if pd.isna(order_qty) or order_qty < 0:
                schema_count += 1
            if _review_flag_value(row.get("store_mapping_resolved_flag", 1)) != 1 or _review_flag_value(row.get("store_mapping_active_flag", 1)) != 1:
                mapping_count += 1
        return {
            "skipped_due_to_registry_duplicate_count": int(registry_duplicate_count),
            "skipped_due_to_review_count": int(review_count),
            "skipped_due_to_schema_count": int(schema_count),
            "skipped_due_to_mapping_count": int(mapping_count),
            "skipped_due_to_null_sku_count": int(null_sku_count),
        }

    def _classify_zero_publish_outcome(
        self,
        *,
        candidate_row_count: int,
        skipped_rows: list[dict[str, object]],
    ) -> tuple[str, str]:
        if candidate_row_count == 0:
            return PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS, "no_candidate_rows"
        if len(skipped_rows) == candidate_row_count and all(
            _reason_matches(row.get("reason", ""), "already_predicted")
            for row in skipped_rows
        ):
            return PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED, "all_candidates_already_published"
        return PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS, "no_eligible_rows_after_filters"

    def _build_overall_publish_status(self, publication_summary_frame: pd.DataFrame) -> tuple[str, str]:
        if publication_summary_frame.empty:
            return PUBLISH_STATUS_FAIL, "no_publication_summary_rows"
        statuses = publication_summary_frame["publish_status"].astype(str)
        if statuses.eq(PUBLISH_STATUS_FAIL).any():
            reasons = publication_summary_frame.loc[
                statuses.eq(PUBLISH_STATUS_FAIL),
                "publish_status_reason",
            ].astype(str)
            return PUBLISH_STATUS_FAIL, ";".join(sorted(set(reasons.tolist())))
        if statuses.eq(PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS).any():
            reasons = publication_summary_frame.loc[
                statuses.eq(PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS),
                "publish_status_reason",
            ].astype(str)
            return PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS, ";".join(sorted(set(reasons.tolist())))
        if statuses.eq(PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED).any() and statuses.isin({PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED}).all():
            return PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED, "all_cycles_already_published"
        if statuses.eq(PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS).any() and statuses.isin(
            {PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS, PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED}
        ).all():
            return PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS, "all_cycles_valid_no_publishable_rows"
        if statuses.eq(PUBLISH_STATUS_PASS_WITH_EXCLUSIONS).any():
            return PUBLISH_STATUS_PASS_WITH_EXCLUSIONS, "one_or_more_cycles_excluded_rows"
        return PUBLISH_STATUS_PASS, "all_cycles_published"

    def _build_publication_summary_rows(
        self,
        *,
        run_id: str,
        created_at: str,
        reconciliation_frame: pd.DataFrame,
        store_number: str,
        client_name: str,
        review_path: str,
        manifest_payload: dict[str, object],
        cycle_summary: dict[str, object],
        skipped_row_count: int,
    ) -> list[dict[str, object]]:
        summary_row = {
            "run_id": run_id,
            "client_name": client_name,
            "store_number": store_number,
            "promotion_cycle_id": str(manifest_payload.get("promotion_cycle_id", "")),
            "file_type": "store_promotion_pack",
            "file_path": review_path,
            "source_row_count": int(cycle_summary.get("source_row_count", 0)),
            "candidate_row_count": int(cycle_summary.get("candidate_row_count", 0)),
            "pos_candidate_row_count": int(cycle_summary.get("pos_candidate_row_count", 0)),
            "pos_published_row_count": int(cycle_summary.get("pos_published_row_count", 0)),
            "pos_excluded_row_count": int(cycle_summary.get("pos_excluded_row_count", 0)),
            "publish_eligible_row_count": int(cycle_summary.get("publish_eligible_row_count", 0)),
            "review_only_row_count": int(cycle_summary.get("review_only_row_count", 0)),
            "excluded_legitimate_row_count": int(cycle_summary.get("excluded_legitimate_row_count", 0)),
            "excluded_defect_row_count": int(cycle_summary.get("excluded_defect_row_count", 0)),
            "null_sku_excluded_row_count": int(cycle_summary.get("null_sku_excluded_row_count", 0)),
            "review_row_count": int(cycle_summary.get("review_row_count", 0)),
            "skipped_row_count": int(skipped_row_count),
            "skipped_due_to_registry_duplicate_count": int(cycle_summary.get("skipped_due_to_registry_duplicate_count", 0)),
            "skipped_due_to_review_count": int(cycle_summary.get("skipped_due_to_review_count", 0)),
            "skipped_due_to_schema_count": int(cycle_summary.get("skipped_due_to_schema_count", 0)),
            "skipped_due_to_mapping_count": int(cycle_summary.get("skipped_due_to_mapping_count", 0)),
            "skipped_due_to_null_sku_count": int(cycle_summary.get("skipped_due_to_null_sku_count", 0)),
            "demand_true_zero_count": int(cycle_summary.get("demand_true_zero_count", 0)),
            "demand_cold_start_count": int(cycle_summary.get("demand_cold_start_count", 0)),
            "demand_low_nonzero_count": int(cycle_summary.get("demand_low_nonzero_count", 0)),
            "demand_artificial_collapse_count": int(cycle_summary.get("demand_artificial_collapse_count", 0)),
            "publish_status": str(cycle_summary.get("publish_status", "FAIL")),
            "publish_status_reason": str(cycle_summary.get("publish_status_reason", "")),
            "publish_status_message": _publish_status_message(
                publish_status=str(cycle_summary.get("publish_status", "FAIL")),
                publish_status_reason=str(cycle_summary.get("publish_status_reason", "")),
            ),
            "reconciliation_status": _reconciliation_status(reconciliation_frame),
            "upload_schema_valid": bool(manifest_payload.get("upload_schema_valid", False)),
            "cycle_identity_present_flag": int(cycle_summary.get("cycle_identity_present_flag", 0)),
            "prior_publication_detected_flag": int(cycle_summary.get("prior_publication_detected_flag", 0)),
            "generated_at": created_at,
        }
        self._validate_publication_summary_counts(summary_row)
        return [summary_row]

    def _write_publish_eligibility_run_diagnostics(
        self,
        *,
        diagnostics_root: Path,
        review_frames: list[pd.DataFrame],
        source_row_count: int,
        post_identity_row_count: int,
        post_policy_row_count: int,
        final_published_row_count: int,
        publication_summary_frame: pd.DataFrame,
        run_id: str,
        created_at: str,
    ) -> tuple[str, ...]:
        diagnostics_root.mkdir(parents=True, exist_ok=True)
        combined_review = pd.concat(review_frames, ignore_index=True) if review_frames else pd.DataFrame()

        if combined_review.empty:
            combined_review = pd.DataFrame(
                columns=[
                    "publish_eligibility_class",
                    "publish_eligibility_reason",
                    "publish_noop_reason",
                    "excluded_from_publish_flag",
                ]
            )

        breakdown = (
            combined_review["publish_eligibility_class"].astype(str).value_counts(dropna=False)
            .rename_axis("publish_eligibility_class")
            .reset_index(name="row_count")
        ) if "publish_eligibility_class" in combined_review.columns else pd.DataFrame(
            columns=["publish_eligibility_class", "row_count"]
        )

        publish_gate_counts_path = diagnostics_root / "publish_gate_counts.json"
        publish_eligibility_breakdown_path = diagnostics_root / "publish_eligibility_breakdown.csv"
        publish_review_only_rows_path = diagnostics_root / "publish_review_only_rows.csv"
        publish_excluded_legitimate_rows_path = diagnostics_root / "publish_excluded_legitimate_rows.csv"
        publish_excluded_defect_rows_path = diagnostics_root / "publish_excluded_defect_rows.csv"
        publish_noop_summary_path = diagnostics_root / "publish_noop_summary.json"

        breakdown.to_csv(publish_eligibility_breakdown_path, index=False)

        class_series = (
            combined_review["publish_eligibility_class"].astype(str)
            if "publish_eligibility_class" in combined_review.columns
            else pd.Series("", index=combined_review.index, dtype=object)
        )
        review_only_rows = combined_review.loc[class_series.eq(PUBLISH_ELIGIBILITY_CLASS_REVIEW_ONLY)]
        excluded_legitimate_rows = combined_review.loc[class_series.eq(PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_LEGITIMATE)]
        excluded_defect_rows = combined_review.loc[class_series.eq(PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_DEFECT)]
        review_only_rows.to_csv(publish_review_only_rows_path, index=False)
        excluded_legitimate_rows.to_csv(publish_excluded_legitimate_rows_path, index=False)
        excluded_defect_rows.to_csv(publish_excluded_defect_rows_path, index=False)

        class_count_map = {
            str(row.publish_eligibility_class): int(row.row_count)
            for row in breakdown.itertuples(index=False)
            if str(row.publish_eligibility_class).strip()
        }
        gate_counts_payload = {
            "run_id": run_id,
            "source_row_count": int(source_row_count),
            "post_identity_row_count": int(post_identity_row_count),
            "post_policy_row_count": int(post_policy_row_count),
            "final_published_row_count": int(final_published_row_count),
            "publish_eligibility_class_counts": class_count_map,
            "counts_reconciled_flag": bool(post_policy_row_count == final_published_row_count + int(
                class_count_map.get(PUBLISH_ELIGIBILITY_CLASS_REVIEW_ONLY, 0)
                + class_count_map.get(PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_LEGITIMATE, 0)
                + class_count_map.get(PUBLISH_ELIGIBILITY_CLASS_EXCLUDED_DEFECT, 0)
            )),
            "created_at": created_at,
        }
        publish_gate_counts_path.write_text(
            json.dumps(gate_counts_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        noop_rows = publication_summary_frame.loc[
            publication_summary_frame.get("publish_status", "").astype(str).isin(
                {PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS, PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED}
            )
        ] if not publication_summary_frame.empty else pd.DataFrame()
        noop_reason_counts = (
            noop_rows.get("publish_status_reason", pd.Series(dtype=object)).astype(str).value_counts(dropna=False).to_dict()
            if not noop_rows.empty
            else {}
        )
        publish_noop_reason_counts = (
            combined_review.get("publish_noop_reason", pd.Series(dtype=object))
            .astype(str)
            .loc[lambda s: s.str.strip().ne("")]
            .value_counts(dropna=False)
            .to_dict()
        )
        publish_noop_summary_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "noop_cycle_count": int(len(noop_rows.index)),
                    "noop_reason_counts": {str(key): int(value) for key, value in noop_reason_counts.items()},
                    "publish_noop_reasons_from_rows": {
                        str(key): int(value) for key, value in publish_noop_reason_counts.items()
                    },
                    "created_at": created_at,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        return (
            str(publish_gate_counts_path),
            str(publish_eligibility_breakdown_path),
            str(publish_review_only_rows_path),
            str(publish_excluded_legitimate_rows_path),
            str(publish_excluded_defect_rows_path),
            str(publish_noop_summary_path),
        )

    def _validate_publication_summary_counts(self, summary_row: dict[str, object]) -> None:
        source_count = int(summary_row["source_row_count"])
        candidate_count = int(summary_row["candidate_row_count"])
        pos_candidate_count = int(summary_row["pos_candidate_row_count"])
        published_count = int(summary_row["pos_published_row_count"])
        excluded_count = int(summary_row["pos_excluded_row_count"])
        registry_duplicate_count = int(summary_row["skipped_due_to_registry_duplicate_count"])
        skipped_count = int(summary_row["skipped_row_count"])
        if source_count != candidate_count:
            raise PromotionStoreExecutionValidationError(
                "Validation failed: publication summary source_row_count does not equal candidate_row_count."
            )
        if candidate_count != (pos_candidate_count + registry_duplicate_count):
            raise PromotionStoreExecutionValidationError(
                "Validation failed: publication summary candidate counts do not reconcile with registry duplicates."
            )
        if pos_candidate_count != (published_count + excluded_count):
            raise PromotionStoreExecutionValidationError(
                "Validation failed: publication summary POS counts do not reconcile."
            )
        if skipped_count != (excluded_count + registry_duplicate_count):
            raise PromotionStoreExecutionValidationError(
                "Validation failed: publication summary skipped counts do not reconcile."
            )

    def _validate_manifest_row_counts(
        self,
        *,
        manifest_payload: dict[str, object],
        review_frame: pd.DataFrame,
        summary_frame: pd.DataFrame,
        pos_frame: pd.DataFrame,
    ) -> None:
        if int(manifest_payload["row_count"]) != int(len(review_frame.index)):
            raise PromotionStoreExecutionValidationError(
                "Validation failed: manifest row_count does not match review rows."
            )
        if int(manifest_payload["sku_count"]) != int(review_frame["sku_number"].astype(str).nunique(dropna=True)):
            raise PromotionStoreExecutionValidationError(
                "Validation failed: manifest sku_count does not match review file."
            )
        _ = summary_frame
        _ = pos_frame

    def _validate_no_duplicate_prediction_rows(
        self,
        rows: list[dict[str, object]],
    ) -> None:
        if not rows:
            return
        frame = pd.DataFrame(rows)
        duplicate_count = int(
            frame[frame["sku_number"].notna()].duplicated(
                subset=["store_number", "promotion_header_key", "sku_number"],
                keep=False,
            ).sum()
        )
        if duplicate_count > 0:
            raise PromotionStoreExecutionValidationError(
                "Validation failed: duplicate store_number + promotion_header_key + sku_number rows detected in publish candidate set."
            )


def _reconciliation_status(reconciliation_frame: pd.DataFrame) -> str:
    if reconciliation_frame.empty:
        return "FAIL"
    if reconciliation_frame["status"].astype(str).eq("PASS").all():
        return "PASS"
    return "FAIL"


def _registry_columns() -> list[str]:
    return [
        "prediction_identity_key",
        "prediction_key",
        "prediction_version",
        "supersedes_prediction_key",
        "client_code",
        "store_number",
        "promotion_id",
        "sku_number",
        "promotion_start_date",
        "promotion_break_date",
        "prediction_run_id",
        "prediction_created_at",
        "output_file_path",
        "model_version",
        "prediction_cutoff_date",
        "status",
    ]


def _load_registry(path: str | Path) -> pd.DataFrame:
    parquet_path = Path(path)
    if not parquet_path.exists():
        return pd.DataFrame(columns=_registry_columns())
    frame = pd.read_parquet(parquet_path)
    for column in _registry_columns():
        if column not in frame.columns:
            frame[column] = ""
    return frame[_registry_columns()].copy()


def _write_registry(path: str | Path, frame: pd.DataFrame) -> None:
    frame = frame.copy()
    for column in _registry_columns():
        if column not in frame.columns:
            frame[column] = ""
    frame.to_parquet(Path(path), index=False)


def _publish_identity_key(
    *,
    store_number: object,
    promotion_id: object,
    promotion_start_date: object,
    promotion_break_date: object,
    sku_number: object,
) -> str:
    return "|".join(
        [
            _identity_token(store_number),
            _identity_token(promotion_id),
            _identity_token(promotion_start_date),
            _identity_token(promotion_break_date),
            _identity_token(sku_number),
        ]
    )


def _prediction_identity_key(
    *,
    client_code: object,
    store_number: object,
    promotion_id: object,
    promotion_start_date: object,
    promotion_break_date: object,
    sku_number: object,
    prediction_cutoff_date: str,
) -> str:
    return _sha256(
        "|".join(
            [
                _identity_token(client_code),
                _identity_token(store_number),
                _identity_token(promotion_id),
                _identity_token(promotion_start_date),
                _identity_token(promotion_break_date),
                _identity_token(sku_number),
                prediction_cutoff_date,
            ]
        )
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _coalesce(*values: object) -> object:
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and pd.isna(value):
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "<na>"}:
            return value
    return ""


def _as_date_string(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _identity_token(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return str(value)
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "<na>"}:
        return ""
    if re.fullmatch(r"-?\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def _promotion_cycle_id(promotion_start_date: object) -> str:
    parsed = pd.to_datetime(promotion_start_date, errors="coerce")
    if pd.isna(parsed):
        return "unknown_cycle"
    iso = parsed.isocalendar()
    return f"{int(iso.year)}_WK{int(iso.week):02d}"


def _slug(value: str, *, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned or fallback


def _first_non_empty(frame: pd.DataFrame, column_name: str) -> str:
    if column_name not in frame.columns:
        return ""
    for value in frame[column_name].tolist():
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "<na>"}:
            return text
    return ""


def _review_flag_value(value: object) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return 0
        return 1 if float(value) >= 1.0 else 0
    text = str(value).strip().lower()
    if text in {"1.0", "1.00"}:
        return 1
    if text in {"1", "true", "yes", "y", "t"}:
        return 1
    return 0


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "<na>"}


def _reason_matches(reason_value: object, expected: str) -> bool:
    return str(reason_value).strip().lower() == expected.lower()


def _publish_status_message(*, publish_status: str, publish_status_reason: str) -> str:
    if publish_status == PUBLISH_STATUS_PASS:
        return "Publish completed successfully for all promotion packages."
    if publish_status == PUBLISH_STATUS_PASS_WITH_EXCLUSIONS:
        return "Publish completed with exclusions; review excluded rows before re-run."
    if publish_status == PUBLISH_STATUS_NOOP_ALREADY_PUBLISHED:
        return "No new publication required because every candidate row was already published for this cutoff."
    if publish_status == PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS:
        return (
            "No publish file was produced because Stage 12 candidates were all validly non-publishable"
            f" ({publish_status_reason or 'unspecified reason'})."
        )
    if publish_status == PUBLISH_STATUS_FAIL_NO_ELIGIBLE_ROWS:
        return (
            "Publish failed because no eligible rows remained after Stage 12 policy and validation gates"
            f" ({publish_status_reason or 'unspecified reason'})."
        )
    return (
        "Publish failed due to a validation or policy defect"
        f" ({publish_status_reason or 'unspecified reason'})."
    )
