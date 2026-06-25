from src.models import Asset
from src.models.schema import UpdateAssetRequest
from sqlmodel import Session, select


class AssetsRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_all_assets(self):
        statement = select(Asset)
        return self.session.exec(statement).all()

    def get_asset_by_id(self, asset_id: str):
        statement = select(Asset).where(Asset.id == asset_id)
        return self.session.exec(statement).first()

    def create_asset(self, asset: Asset):
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def update_asset(self, asset_id: str, updated_asset: UpdateAssetRequest):
        asset = self.get_asset_by_id(asset_id)
        if asset:
            update_data = updated_asset.model_dump(exclude_unset=True)
            if "metadata" in update_data:
                update_data["metadata_"] = update_data.pop("metadata")
            for key, value in update_data.items():
                setattr(asset, key, value)
            self.session.commit()
            self.session.refresh(asset)
            return asset
        return None

    def delete_asset(self, asset_id: str):
        asset = self.get_asset_by_id(asset_id)
        if asset:
            self.session.delete(asset)
            self.session.commit()
            return True
        return False