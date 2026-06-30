import logging
from src.repositories import AssetsRepository
from src.repositories.relationships_repository import RelationshipsRepository
from src.models import Asset
from src.models.enums import AssetType, AssetStatus
from src.models.schema import CreateAssetRequest, UpdateAssetRequest, AssetFilters, BulkImportItem
from datetime import datetime
from uuid import UUID
from pydantic import ValidationError

logger = logging.getLogger(__name__)

class AssetsService:
    def __init__(self, db_session):
        self.asset_repo = AssetsRepository(db_session)
        self.relations_repo = RelationshipsRepository(db_session)

    def get_assets(self, filters: AssetFilters) -> tuple[list[Asset], int]:
        logger.debug("service: Fetching assets with filters: %s", filters)
        return self.asset_repo.get_all_assets(filters)

    def get_asset_by_id(self, asset_id: str) -> Asset | None:
        logger.debug("service: Fetching asset by ID: %s", asset_id)
        return self.asset_repo.get_asset_by_id(asset_id)

    def bulk_create_assets(self, assets_data: list[dict]) -> tuple[int, int, list]:
        logger.info("service: Starting bulk import of %d items", len(assets_data))
        created_assets_count = 0
        updated_assets_count = 0
        errors = []

        # batch_local_id → (db_uuid, BulkImportItem) for every successfully processed item
        processed: dict[str, tuple[UUID, BulkImportItem]] = {}

        # ── Pass 1: create / update every asset ──────────────────────────────
        for index, dic in enumerate(assets_data):
            try:
                asset_data = BulkImportItem.model_validate(dic)
                create_model = CreateAssetRequest(
                    type=asset_data.type,
                    status=asset_data.status,
                    value=asset_data.value,
                    source=asset_data.source,
                    tags=asset_data.tags,
                    metadata=asset_data.metadata,
                )
                created_asset, merged = self.create_asset(create_model)
                if merged:
                    updated_assets_count += 1
                else:
                    created_assets_count += 1
                processed[asset_data.id] = (created_asset.id, asset_data)
                logger.debug("service: Processed batch item index=%d, db_id=%s, merged=%s", index, created_asset.id, merged)
            except ValidationError as e:
                logger.warning("service: Validation error at batch index=%d. Input: %s. Errors: %s", index, dic, e.errors())
                errors.append({"index": index + 1, "input": dic, "errors": e.errors()})

        # ── Pass 2: resolve and create relationships ──────────────────────────
        # Only runs for items that passed validation in Pass 1.
        for batch_id, (db_uuid, asset_data) in processed.items():

            # "parent" field — the referenced asset is the parent of this one
            # Relation: parent_id = referenced_db_uuid, child_id = this db_uuid
            if asset_data.parent:
                if asset_data.parent not in processed:
                    err_msg = f"Referenced batch id '{asset_data.parent}' was not found in this batch or failed validation."
                    logger.warning("service: Relation error for batch_id=%s: %s", batch_id, err_msg)
                    errors.append({
                        "batch_id": batch_id,
                        "relation": "parent",
                        "error": err_msg,
                    })
                else:
                    parent_db_uuid = processed[asset_data.parent][0]
                    if not self.relations_repo.relation_exists(parent_db_uuid, db_uuid, "parent"):
                        try:
                            self.relations_repo.create_relation(parent_db_uuid, db_uuid, "parent")
                            logger.debug("service: Created parent relation between %s and %s", parent_db_uuid, db_uuid)
                        except Exception as e:
                            logger.error("service: Failed to create parent relation between %s and %s: %s", parent_db_uuid, db_uuid, str(e))
                            errors.append({"batch_id": batch_id, "relation": "parent", "error": str(e)})

            # "covers" field — this asset (e.g. certificate) covers the referenced one (e.g. subdomain)
            # Relation: parent_id = this db_uuid, child_id = referenced_db_uuid
            if asset_data.covers:
                if asset_data.covers not in processed:
                    err_msg = f"Referenced batch id '{asset_data.covers}' was not found in this batch or failed validation."
                    logger.warning("service: Relation error for batch_id=%s: %s", batch_id, err_msg)
                    errors.append({
                        "batch_id": batch_id,
                        "relation": "covers",
                        "error": err_msg,
                    })
                else:
                    covered_db_uuid = processed[asset_data.covers][0]
                    if not self.relations_repo.relation_exists(db_uuid, covered_db_uuid, "covers"):
                        try:
                            self.relations_repo.create_relation(db_uuid, covered_db_uuid, "covers")
                            logger.debug("service: Created covers relation between %s and %s", db_uuid, covered_db_uuid)
                        except Exception as e:
                            logger.error("service: Failed to create covers relation between %s and %s: %s", db_uuid, covered_db_uuid, str(e))
                            errors.append({"batch_id": batch_id, "relation": "covers", "error": str(e)})

        logger.info("service: Bulk import finished. Created=%d, Updated=%d, Errors=%d", created_assets_count, updated_assets_count, len(errors))
        return created_assets_count, updated_assets_count, errors

    def create_asset(self, asset_data: CreateAssetRequest) -> tuple[Asset, bool]:
        logger.debug("service: Creating/upserting asset value=%s, type=%s", asset_data.value, asset_data.type)
        old_asset = self.asset_repo.get_asset_by_type_value(asset_data.type, asset_data.value)
        if old_asset:
            logger.debug("service: Asset already exists, merging changes: ID=%s", old_asset.id)
            merged_asset = self._merge_assets(old_asset, asset_data)
            updated = self.asset_repo.update_asset(old_asset.id, merged_asset)
            return updated, True
        asset = Asset(
            type=asset_data.type,
            value=asset_data.value,
            source=asset_data.source,
            tags=asset_data.tags,
            metadata_=asset_data.metadata,
        )
        created = self.asset_repo.create_asset(asset)
        logger.debug("service: Asset created successfully: ID=%s", created.id)
        return created, False
    
    def _merge_assets(self, existing_asset: Asset, updated_asset: CreateAssetRequest) -> Asset:
        existing_asset.status = AssetStatus.active
        existing_asset.tags = list(set(existing_asset.tags + updated_asset.tags))
        existing_asset.metadata_ = {**existing_asset.metadata_, **updated_asset.metadata}
        existing_asset.last_seen = datetime.now()
        return existing_asset

    def update_asset(self, asset_id: str, updated_asset: UpdateAssetRequest) -> Asset | None:
        logger.info("service: Updating asset ID=%s", asset_id)
        # Only forward fields that were explicitly provided — passing None for
        # required Asset fields (e.g. status) causes a validation error.
        data = updated_asset.model_dump(exclude_none=True)
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")
        patch_asset = Asset(**data)
        updated = self.asset_repo.update_asset(asset_id, patch_asset)
        if updated:
            logger.info("service: Successfully updated asset ID=%s", asset_id)
        else:
            logger.warning("service: Asset not found for update ID=%s", asset_id)
        return updated

    def set_asset_status(self, asset_id: str, status: AssetStatus) -> Asset | None:
        logger.info("service: Setting asset status: ID=%s, status=%s", asset_id, status.value)
        updated = self.asset_repo.set_status(asset_id, status)
        if updated:
            logger.info("service: Successfully updated status for asset ID=%s", asset_id)
        else:
            logger.warning("service: Asset not found for status update ID=%s", asset_id)
        return updated

    def mark_stale_assets(self, days_interval: float) -> int:
        logger.info("service: Identifying and marking assets stale older than %f days", days_interval)
        stale_assets = self.asset_repo.mark_stale_assets(days_interval)
        logger.info("service: Marked %d assets as stale", len(stale_assets))
        return len(stale_assets)

    def delete_asset(self, asset_id: str) -> bool:
        logger.info("service: Deleting asset ID=%s", asset_id)
        deleted = self.asset_repo.delete_asset(asset_id)
        if deleted:
            logger.info("service: Successfully deleted asset ID=%s", asset_id)
        else:
            logger.warning("service: Asset ID=%s not found for deletion", asset_id)
        return deleted