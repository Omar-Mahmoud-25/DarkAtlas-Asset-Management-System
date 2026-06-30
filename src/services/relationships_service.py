import logging
from uuid import UUID
from typing import Any

from src.models import Asset, AssetRelation
from src.repositories import AssetsRepository
from src.repositories.relationships_repository import RelationshipsRepository

logger = logging.getLogger(__name__)


class RelationshipsService:
    def __init__(self, db_session):
        self.relations_repo = RelationshipsRepository(db_session)
        self.assets_repo = AssetsRepository(db_session)

    def create_relation(
        self, parent_id: str, child_id: UUID, relation_type: str
    ) -> tuple[AssetRelation | None, str | None]:
        logger.info("service: Creating relation: parent_id=%s, child_id=%s, type=%s", parent_id, child_id, relation_type)
        parent = self.assets_repo.get_asset_by_id(parent_id)
        if not parent:
            logger.warning("service: Parent asset %s not found", parent_id)
            return None, "parent_not_found"

        child = self.assets_repo.get_asset_by_id(str(child_id))
        if not child:
            logger.warning("service: Child asset %s not found", child_id)
            return None, "child_not_found"

        relation = self.relations_repo.create_relation(
            parent.id, child.id, relation_type
        )
        logger.info("service: Successfully created relation ID=%s", relation.id)
        return relation, None

    def get_relations(self, asset_id: str) -> list[AssetRelation] | None:
        """Return all relations for an asset (both directions). None if asset not found."""
        logger.debug("service: Getting relations for asset ID: %s", asset_id)
        asset = self.assets_repo.get_asset_by_id(asset_id)
        if not asset:
            logger.warning("service: Asset %s not found for listing relations", asset_id)
            return None
        relations = self.relations_repo.get_relations_by_asset_id(asset.id)
        logger.debug("service: Found %d relations for asset ID: %s", len(relations), asset_id)
        return relations

    def get_asset_graph(
        self, asset_id: str
    ) -> tuple[Asset, list[dict[str, Any]], list[dict[str, Any]]] | None:
        """
        Return (asset, parents, children) where each parent/child is:
            {"asset": Asset, "relation_type": str}
        Returns None if the asset does not exist.
        """
        logger.debug("service: Fetching asset graph for ID: %s", asset_id)
        asset = self.assets_repo.get_asset_by_id(asset_id)
        if not asset:
            logger.warning("service: Asset %s not found for graph fetching", asset_id)
            return None

        relations = self.relations_repo.get_relations_by_asset_id(asset.id)

        parents: list[dict[str, Any]] = []
        children: list[dict[str, Any]] = []

        for relation in relations:
            if str(relation.child_id) == str(asset.id):
                # This asset is the child → the other end is a parent
                related = self.assets_repo.get_asset_by_id(str(relation.parent_id))
                if related:
                    parents.append({"asset": related, "relation_type": relation.relation_type})
            else:
                # This asset is the parent → the other end is a child
                related = self.assets_repo.get_asset_by_id(str(relation.child_id))
                if related:
                    children.append({"asset": related, "relation_type": relation.relation_type})

        logger.debug("service: Graph constructed for ID: %s. Parents count=%d, Children count=%d", asset_id, len(parents), len(children))
        return asset, parents, children

    def get_relation_by_id(self, relation_id: str) -> AssetRelation | None:
        logger.debug("service: Fetching relation by ID: %s", relation_id)
        return self.relations_repo.get_relation_by_id(relation_id)

    def delete_relation(self, relation_id: str) -> bool:
        logger.info("service: Deleting relation ID: %s", relation_id)
        deleted = self.relations_repo.delete_relation(relation_id)
        if deleted:
            logger.info("service: Successfully deleted relation ID: %s", relation_id)
        else:
            logger.warning("service: Relation ID: %s not found for deletion", relation_id)
        return deleted
