from src.repositories import AssetsRepository
from src.models import Asset
from src.models.schema import CreateAssetRequest, UpdateAssetRequest, AssetFilters, BulkImportItem
from datetime import datetime
from pydantic import ValidationError

class AssetsService:
    def __init__(self, db_session):
        self.asset_repo = AssetsRepository(db_session)

    def get_assets(self, filters: AssetFilters) -> tuple[list[Asset], int]:
        return self.asset_repo.get_all_assets(filters)

    def get_asset_by_id(self, asset_id: str) -> Asset | None:
        return self.asset_repo.get_asset_by_id(asset_id)

    def bulk_create_assets(self, assets_data: list[dict]) -> tuple[int, int]:
        created_assets_count = 0
        updated_assets_count = 0
        errors = []
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
            except ValidationError as e:
                errors.append({"index": index + 1, "errors": e.errors()})
        return created_assets_count, updated_assets_count, errors

    def create_asset(self, asset_data: CreateAssetRequest) -> tuple[Asset, bool]:
        old_asset = self.asset_repo.get_asset_by_type_value(asset_data.type, asset_data.value)
        if old_asset:
            merged_asset = self._merge_assets(old_asset, asset_data)
            return self.asset_repo.update_asset(old_asset.id, merged_asset), True
        asset = Asset(
            type=asset_data.type,
            status=asset_data.status,
            value=asset_data.value,
            source=asset_data.source,
            tags=asset_data.tags,
            metadata_=asset_data.metadata,
        )
        return self.asset_repo.create_asset(asset), False
    
    def _merge_assets(self, existing_asset: Asset, updated_asset: CreateAssetRequest) -> Asset:
        existing_asset.status = updated_asset.status
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

    def delete_asset(self, asset_id: str) -> bool:
        return self.asset_repo.delete_asset(asset_id)