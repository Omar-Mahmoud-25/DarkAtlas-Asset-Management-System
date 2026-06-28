from uuid import UUID
from typing import Any

from src.models import Asset, AssetRelation
from src.repositories import AssetsRepository
from src.repositories.relationships_repository import RelationshipsRepository


class RelationshipsService:
    def __init__(self, db_session):
        self.relations_repo = RelationshipsRepository(db_session)
        self.assets_repo = AssetsRepository(db_session)

    def create_relation(
        self, parent_id: str, child_id: UUID, relation_type: str
    ) -> tuple[AssetRelation | None, str | None]:
        
        parent = self.assets_repo.get_asset_by_id(parent_id)
        if not parent:
            return None, "parent_not_found"

        child = self.assets_repo.get_asset_by_id(str(child_id))
        if not child:
            return None, "child_not_found"

        relation = self.relations_repo.create_relation(
            parent.id, child.id, relation_type
        )
        return relation, None

    def get_relations(self, asset_id: str) -> list[AssetRelation] | None:
        """Return all relations for an asset (both directions). None if asset not found."""
        asset = self.assets_repo.get_asset_by_id(asset_id)
        if not asset:
            return None
        return self.relations_repo.get_relations_by_asset_id(asset.id)

    def get_asset_graph(
        self, asset_id: str
    ) -> tuple[Asset, list[dict[str, Any]], list[dict[str, Any]]] | None:
        """
        Return (asset, parents, children) where each parent/child is:
            {"asset": Asset, "relation_type": str}
        Returns None if the asset does not exist.
        """
        asset = self.assets_repo.get_asset_by_id(asset_id)
        if not asset:
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

        return asset, parents, children

    def get_relation_by_id(self, relation_id: str) -> AssetRelation | None:
        return self.relations_repo.get_relation_by_id(relation_id)

    def delete_relation(self, relation_id: str) -> bool:
        return self.relations_repo.delete_relation(relation_id)

