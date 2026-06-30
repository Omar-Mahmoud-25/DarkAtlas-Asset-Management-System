import logging
from src.models import Asset
from src.models.enums import AssetType, AssetStatus
from src.models.schema import UpdateAssetRequest, AssetFilters
from sqlmodel import Session, select, func
from sqlalchemy import asc, desc
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AssetsRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_all_assets(self, filters: AssetFilters):
        logger.debug("repo: Listing assets from DB with filters")
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
        logger.debug("repo: Successfully listed %d assets from DB (total: %d)", len(assets), total_count)
        return assets, total_count

    def get_asset_by_id(self, asset_id: str):
        logger.debug("repo: Querying asset by ID: %s", asset_id)
        statement = select(Asset).where(Asset.id == asset_id)
        result = self.session.exec(statement).first()
        if result:
            logger.debug("repo: Asset ID: %s found in DB", asset_id)
        else:
            logger.debug("repo: Asset ID: %s not found in DB", asset_id)
        return result
    
    def get_asset_by_type_value(self, asset_type: str, asset_value: str):
        logger.debug("repo: Querying asset by type=%s and value=%s", asset_type, asset_value)
        statement = select(Asset).where(Asset.type == asset_type, Asset.value == asset_value)
        result = self.session.exec(statement).first()
        if result:
            logger.debug("repo: Asset found in DB: ID=%s", result.id)
        else:
            logger.debug("repo: Asset not found in DB for type=%s and value=%s", asset_type, asset_value)
        return result

    def create_asset(self, asset: Asset):
        logger.debug("repo: Inserting new asset: type=%s, value=%s", asset.type, asset.value)
        try:
            self.session.add(asset)
            self.session.commit()
            self.session.refresh(asset)
            logger.debug("repo: Successfully committed and created asset: ID=%s", asset.id)
            return asset
        except Exception as e:
            logger.error("repo: Error creating asset: %s", str(e), exc_info=True)
            self.session.rollback()
            raise

    def update_asset(self, asset_id: str, updated_asset: Asset):
        logger.debug("repo: Updating asset ID=%s", asset_id)
        old_asset = self.get_asset_by_id(asset_id)
        if old_asset:
            update_data = updated_asset.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if key != "id" and key != "first_seen":
                    setattr(old_asset, key, value)
            old_asset.last_seen = datetime.now()
            try:
                self.session.commit()
                self.session.refresh(old_asset)
                logger.debug("repo: Successfully updated asset ID=%s", asset_id)
                return old_asset
            except Exception as e:
                logger.error("repo: Error updating asset ID=%s: %s", asset_id, str(e), exc_info=True)
                self.session.rollback()
                raise
        logger.warning("repo: Asset ID=%s not found for update", asset_id)
        return None

    def delete_asset(self, asset_id: str):
        logger.debug("repo: Deleting asset ID=%s", asset_id)
        asset = self.get_asset_by_id(asset_id)
        if asset:
            try:
                self.session.delete(asset)
                self.session.commit()
                logger.debug("repo: Successfully deleted asset ID=%s", asset_id)
                return True
            except Exception as e:
                logger.error("repo: Error deleting asset ID=%s: %s", asset_id, str(e), exc_info=True)
                self.session.rollback()
                raise
        logger.warning("repo: Asset ID=%s not found for deletion", asset_id)
        return False

    def set_status(self, asset_id: str, status):
        logger.debug("repo: Setting status for asset ID=%s to %s", asset_id, status)
        asset = self.get_asset_by_id(asset_id)
        if asset:
            asset.status = status
            try:
                self.session.commit()
                self.session.refresh(asset)
                logger.debug("repo: Successfully updated status for asset ID=%s", asset_id)
                return asset
            except Exception as e:
                logger.error("repo: Error updating status for asset ID=%s: %s", asset_id, str(e), exc_info=True)
                self.session.rollback()
                raise
        logger.warning("repo: Asset ID=%s not found for status update", asset_id)
        return None

    def mark_stale_assets(self, days_interval: float):
        cutoff_date = datetime.now() - timedelta(days=days_interval)
        logger.debug("repo: Querying assets active and last_seen before %s", cutoff_date)
        statement = select(Asset).where(Asset.last_seen < cutoff_date, Asset.status == AssetStatus.active)
        stale_assets = self.session.exec(statement).all()

        if stale_assets:
            logger.info("repo: Marking %d assets as stale", len(stale_assets))
            for asset in stale_assets:
                asset.status = AssetStatus.stale
                self.session.add(asset)
            try:
                self.session.commit()
                logger.debug("repo: Successfully updated stale assets in DB")
            except Exception as e:
                logger.error("repo: Error committing stale status updates: %s", str(e), exc_info=True)
                self.session.rollback()
                raise
        else:
            logger.debug("repo: No stale assets found to mark")
        return stale_assets