from src.models import Asset
from src.models.schema import UpdateAssetRequest, AssetFilters
from sqlmodel import Session, select, func
from sqlalchemy import asc, desc
from datetime import datetime


class AssetsRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_all_assets(self, filters: AssetFilters):
        statement = select(Asset)

        # --- filtering ---
        if filters.type is not None:
            statement = statement.where(Asset.type == filters.type)
        if filters.status is not None:
            statement = statement.where(Asset.status == filters.status)
        if filters.source is not None:
            statement = statement.where(Asset.source == filters.source)
        if filters.value_contains is not None:
            statement = statement.where(Asset.value.ilike(f"%{filters.value_contains}%"))
        if filters.tag is not None:
            # value = ANY(tags) — checks if tag is present in the PostgreSQL ARRAY column
            statement = statement.where(Asset.tags.any(filters.tag))

        # --- total count (before pagination) ---
        count_statement = select(func.count()).select_from(statement.subquery())
        total_count = self.session.exec(count_statement).one()

        # --- sorting ---
        sort_col = {
            "value":      Asset.value,
            "type":       Asset.type,
            "status":     Asset.status,
            "first_seen": Asset.first_seen,
            "last_seen":  Asset.last_seen,
        }[filters.sort_by]
        order_fn = asc if filters.sort_order == "asc" else desc
        statement = statement.order_by(order_fn(sort_col))

        # --- pagination ---
        offset = (filters.page - 1) * filters.page_size
        statement = statement.offset(offset).limit(filters.page_size)

        assets = self.session.exec(statement).all()
        return assets, total_count

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
            asset.last_seen = datetime.now()
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