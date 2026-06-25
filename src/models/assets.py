from typing import Any, Optional
from uuid import UUID, uuid4

from sqlmodel import (
    SQLModel, Field,
    UniqueConstraint, ARRAY, Column, String
)
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from .enums import AssetType, AssetStatus

class Asset(SQLModel, table=True):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("type", "value", name="uq_asset_type_value"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    type: AssetType
    value: str
    status: AssetStatus = Field(default=AssetStatus.active, index=True)
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)
    source: Optional[str] = Field(default=None, index=True)
    tags: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    metadata_: dict[str, Any] = Field(default_factory=dict, sa_column=Column("metadata", JSONB))

class AssetRelation(SQLModel, table=True):
    __tablename__ = "asset_relations"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    parent_id: UUID = Field(foreign_key="assets.id", index=True)
    child_id: UUID = Field(foreign_key="assets.id", index=True)
    relation_type: str