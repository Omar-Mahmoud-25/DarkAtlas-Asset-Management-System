import logging
from uuid import UUID

from sqlmodel import Session, select

from src.models import Asset, AssetRelation

logger = logging.getLogger(__name__)


class RelationshipsRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_relation(
        self, parent_id: UUID, child_id: UUID, relation_type: str
    ) -> AssetRelation:
        logger.debug("repo: Creating relation parent_id=%s, child_id=%s, type=%s", parent_id, child_id, relation_type)
        relation = AssetRelation(
            parent_id=parent_id,
            child_id=child_id,
            relation_type=relation_type,
        )
        try:
            self.session.add(relation)
            self.session.commit()
            self.session.refresh(relation)
            logger.debug("repo: Relation created successfully: ID=%s", relation.id)
            return relation
        except Exception as e:
            logger.error("repo: Error creating relation: %s", str(e), exc_info=True)
            self.session.rollback()
            raise

    def relation_exists(
        self, parent_id: UUID, child_id: UUID, relation_type: str
    ) -> bool:
        """Return True if an identical relation already exists (idempotency check)."""
        logger.debug("repo: Checking if relation exists parent_id=%s, child_id=%s, type=%s", parent_id, child_id, relation_type)
        statement = select(AssetRelation).where(
            AssetRelation.parent_id == parent_id,
            AssetRelation.child_id == child_id,
            AssetRelation.relation_type == relation_type,
        )
        exists = self.session.exec(statement).first() is not None
        logger.debug("repo: Relation exists status: %s", exists)
        return exists

    def get_relations_by_asset_id(self, asset_id: UUID) -> list[AssetRelation]:
        """Return all relation rows where the asset is either parent or child."""
        logger.debug("repo: Querying all relations for asset ID: %s", asset_id)
        statement = select(AssetRelation).where(
            (AssetRelation.parent_id == asset_id)
            | (AssetRelation.child_id == asset_id)
        )
        results = list(self.session.exec(statement).all())
        logger.debug("repo: Found %d relations for asset ID: %s", len(results), asset_id)
        return results

    def get_relation_by_id(self, relation_id: str) -> AssetRelation | None:
        logger.debug("repo: Querying relation by ID: %s", relation_id)
        statement = select(AssetRelation).where(AssetRelation.id == relation_id)
        result = self.session.exec(statement).first()
        if result:
            logger.debug("repo: Relation ID: %s found in DB", relation_id)
        else:
            logger.debug("repo: Relation ID: %s not found in DB", relation_id)
        return result

    def delete_relation(self, relation_id: str) -> bool:
        logger.debug("repo: Deleting relation ID: %s", relation_id)
        relation = self.get_relation_by_id(relation_id)
        if relation:
            try:
                self.session.delete(relation)
                self.session.commit()
                logger.debug("repo: Successfully deleted relation ID: %s", relation_id)
                return True
            except Exception as e:
                logger.error("repo: Error deleting relation ID: %s - %s", relation_id, str(e), exc_info=True)
                self.session.rollback()
                raise
        logger.warning("repo: Relation ID: %s not found for deletion", relation_id)
        return False
