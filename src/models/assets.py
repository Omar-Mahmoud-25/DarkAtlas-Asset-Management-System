from sqlmodel import (
    SQLModel, Field, UUID, JSON, 
    UniqueConstraint, ARRAY, Column, String
)
from datetime import datetime 
from .enums import AssetType, AssetStatus

class Asset(SQLModel, table=True):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("type", "value", name="uq_asset_type_value"),
    )
    id: UUID = Field(default=None, primary_key=True)
    type: AssetType
    value: str
    status: AssetStatus = Field(default=AssetStatus.active, index=True)
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)
    source: str = Field(default=None, index=True)
    tags: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    metadata: JSON

class AssetRelation(SQLModel, table=True):
    __tablename__ = "asset_relations"
    id: UUID = Field(default=None, primary_key=True)
    parent_id: UUID = Field(foreign_key="assets.id", index=True)
    child_id: UUID = Field(foreign_key="assets.id", index=True)
    relation_type: str