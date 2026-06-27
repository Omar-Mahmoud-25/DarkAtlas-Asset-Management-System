from uuid import UUID

from sqlmodel import Session, select

from src.models import Asset, AssetRelation


class RelationshipsRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_relation(
        self, parent_id: UUID, child_id: UUID, relation_type: str
    ) -> AssetRelation:
        relation = AssetRelation(
            parent_id=parent_id,
            child_id=child_id,
            relation_type=relation_type,
        )
        self.session.add(relation)
        self.session.commit()
        self.session.refresh(relation)
        return relation

    def get_relations_by_asset_id(self, asset_id: UUID) -> list[AssetRelation]:
        """Return all relation rows where the asset is either parent or child."""
        statement = select(AssetRelation).where(
            (AssetRelation.parent_id == asset_id)
            | (AssetRelation.child_id == asset_id)
        )
        return list(self.session.exec(statement).all())

    def get_relation_by_id(self, relation_id: str) -> AssetRelation | None:
        statement = select(AssetRelation).where(AssetRelation.id == relation_id)
        return self.session.exec(statement).first()

    def delete_relation(self, relation_id: str) -> bool:
        relation = self.get_relation_by_id(relation_id)
        if relation:
            self.session.delete(relation)
            self.session.commit()
            return True
        return False
