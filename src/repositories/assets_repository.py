from src.models import Asset
from src.models.enums import AssetType, AssetStatus
from src.models.schema import UpdateAssetRequest, AssetFilters
from sqlmodel import Session, select, func
from sqlalchemy import asc, desc
from datetime import datetime, timedelta


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
    
    def get_asset_by_type_value(self, asset_type: str, asset_value: str):
        statement = select(Asset).where(Asset.type == asset_type, Asset.value == asset_value)
        return self.session.exec(statement).first()

    def create_asset(self, asset: Asset):
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def update_asset(self, asset_id: str, updated_asset: Asset):
        old_asset = self.get_asset_by_id(asset_id)
        if old_asset:
            update_data = updated_asset.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if key != "id" and key != "first_seen":
                    setattr(old_asset, key, value)
            old_asset.last_seen = datetime.now()
            self.session.commit()
            self.session.refresh(old_asset)
            return old_asset
        return None

    def delete_asset(self, asset_id: str):
        asset = self.get_asset_by_id(asset_id)
        if asset:
            self.session.delete(asset)
            self.session.commit()
            return True
        return False

    def set_status(self, asset_id: str, status):
        asset = self.get_asset_by_id(asset_id)
        if asset:
            asset.status = status
            self.session.commit()
            self.session.refresh(asset)
            return asset
        return None

    def mark_stale_assets(self, days_interval: float):
        cutoff_date = datetime.now() - timedelta(days=days_interval)
        statement = select(Asset).where(Asset.last_seen < cutoff_date, Asset.status == AssetStatus.active)
        stale_assets = self.session.exec(statement).all()

        for asset in stale_assets:
            asset.status = AssetStatus.stale
            self.session.add(asset)

        self.session.commit()
        return stale_assets