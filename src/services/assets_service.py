from src.repositories import AssetsRepository
from src.models import Asset
from src.models.schema import CreateAssetRequest, UpdateAssetRequest, AssetFilters


class AssetsService:
    def __init__(self, db_session):
        self.asset_repo = AssetsRepository(db_session)

    def get_assets(self, filters: AssetFilters):
        return self.asset_repo.get_all_assets(filters)

    def get_asset_by_id(self, asset_id: str):
        return self.asset_repo.get_asset_by_id(asset_id)

    def create_asset(self, asset_data: CreateAssetRequest):
        asset = Asset(
            type=asset_data.type,
            status=asset_data.status,
            value=asset_data.value,
            source=asset_data.source,
            tags=asset_data.tags,
            metadata_=asset_data.metadata,
        )
        return self.asset_repo.create_asset(asset)

    def update_asset(self, asset_id: str, updated_asset: UpdateAssetRequest):
        return self.asset_repo.update_asset(asset_id, updated_asset)

    def delete_asset(self, asset_id: str):
        return self.asset_repo.delete_asset(asset_id)