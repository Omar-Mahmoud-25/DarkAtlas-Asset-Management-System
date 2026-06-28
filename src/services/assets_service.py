from src.repositories import AssetsRepository
from src.repositories.relationships_repository import RelationshipsRepository
from src.models import Asset
from src.models.enums import AssetType, AssetStatus
from src.models.schema import CreateAssetRequest, UpdateAssetRequest, AssetFilters, BulkImportItem
from datetime import datetime
from uuid import UUID
from pydantic import ValidationError

class AssetsService:
    def __init__(self, db_session):
        self.asset_repo = AssetsRepository(db_session)
        self.relations_repo = RelationshipsRepository(db_session)

    def get_assets(self, filters: AssetFilters) -> tuple[list[Asset], int]:
        return self.asset_repo.get_all_assets(filters)

    def get_asset_by_id(self, asset_id: str) -> Asset | None:
        return self.asset_repo.get_asset_by_id(asset_id)

    def bulk_create_assets(self, assets_data: list[dict]) -> tuple[int, int, list]:
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
            except ValidationError as e:
                errors.append({"index": index + 1, "input": dic, "errors": e.errors()})

        # ── Pass 2: resolve and create relationships ──────────────────────────
        # Only runs for items that passed validation in Pass 1.
        for batch_id, (db_uuid, asset_data) in processed.items():

            # "parent" field — the referenced asset is the parent of this one
            # Relation: parent_id = referenced_db_uuid, child_id = this db_uuid
            if asset_data.parent:
                if asset_data.parent not in processed:
                    errors.append({
                        "batch_id": batch_id,
                        "relation": "parent",
                        "error": (
                            f"Referenced batch id '{asset_data.parent}' "
                            "was not found in this batch or failed validation."
                        ),
                    })
                else:
                    parent_db_uuid = processed[asset_data.parent][0]
                    if not self.relations_repo.relation_exists(parent_db_uuid, db_uuid, "parent"):
                        try:
                            self.relations_repo.create_relation(parent_db_uuid, db_uuid, "parent")
                        except Exception as e:
                            errors.append({"batch_id": batch_id, "relation": "parent", "error": str(e)})

            # "covers" field — this asset (e.g. certificate) covers the referenced one (e.g. subdomain)
            # Relation: parent_id = this db_uuid, child_id = referenced_db_uuid
            if asset_data.covers:
                if asset_data.covers not in processed:
                    errors.append({
                        "batch_id": batch_id,
                        "relation": "covers",
                        "error": (
                            f"Referenced batch id '{asset_data.covers}' "
                            "was not found in this batch or failed validation."
                        ),
                    })
                else:
                    covered_db_uuid = processed[asset_data.covers][0]
                    if not self.relations_repo.relation_exists(db_uuid, covered_db_uuid, "covers"):
                        try:
                            self.relations_repo.create_relation(db_uuid, covered_db_uuid, "covers")
                        except Exception as e:
                            errors.append({"batch_id": batch_id, "relation": "covers", "error": str(e)})

        return created_assets_count, updated_assets_count, errors

    def create_asset(self, asset_data: CreateAssetRequest) -> tuple[Asset, bool]:
        old_asset = self.asset_repo.get_asset_by_type_value(asset_data.type, asset_data.value)
        if old_asset:
            merged_asset = self._merge_assets(old_asset, asset_data)
            return self.asset_repo.update_asset(old_asset.id, merged_asset), True
        asset = Asset(
            type=asset_data.type,
            value=asset_data.value,
            source=asset_data.source,
            tags=asset_data.tags,
            metadata_=asset_data.metadata,
        )
        return self.asset_repo.create_asset(asset), False
    
    def _merge_assets(self, existing_asset: Asset, updated_asset: CreateAssetRequest) -> Asset:
        existing_asset.status = AssetStatus.active
        existing_asset.tags = list(set(existing_asset.tags + updated_asset.tags))
        existing_asset.metadata_ = {**existing_asset.metadata_, **updated_asset.metadata}
        existing_asset.last_seen = datetime.now()
        return existing_asset

    def update_asset(self, asset_id: str, updated_asset: UpdateAssetRequest) -> Asset:
        updated_asset = Asset(
            type=updated_asset.type,
            status=updated_asset.status,
            value=updated_asset.value,
            source=updated_asset.source,
            tags=updated_asset.tags,
            metadata_=updated_asset.metadata,
        )
        return self.asset_repo.update_asset(asset_id, updated_asset)

    def mark_stale_assets(self, days_interval:float) -> Asset | None:
        return self.asset_repo.mark_stale_assets(days_interval)


    def delete_asset(self, asset_id: str) -> bool:
        return self.asset_repo.delete_asset(asset_id)