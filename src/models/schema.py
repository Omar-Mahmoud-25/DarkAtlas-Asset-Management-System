from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Optional, Literal
from uuid import UUID
from datetime import datetime
from src.models.enums import AssetType, AssetStatus

# ----------- Requests ----------------

class CreateAssetRequest(BaseModel):
    type: AssetType
    value: str
    source: str
    tags: list[str] = []
    metadata: dict[str, Any] = {}

class UpdateAssetRequest(BaseModel):
    type: Optional[AssetType] = None
    status: Optional[AssetStatus] = None
    value: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None

class AssetFilters(BaseModel):
    """Query parameters for filtering, sorting, and paginating the asset list."""
    type: Optional[AssetType] = None
    status: Optional[AssetStatus] = None
    tag: Optional[str] = None
    value_contains: Optional[str] = None
    source: Optional[str] = None
    sort_by: Literal["value", "type", "status", "first_seen", "last_seen"] = "last_seen"
    sort_order: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

class BulkImportItem(BaseModel):
    id: str
    type: AssetType
    status: AssetStatus = AssetStatus.active
    value: str
    source: str
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    parent: Optional[str] = None
    covers: Optional[str] = None

class CreateRelationRequest(BaseModel):
    child_id: UUID
    relation_type: str


# ----------- Responses ----------------

class AssetResponse(BaseModel):
    id: UUID
    type: AssetType
    status: AssetStatus
    value: str
    source: str
    tags: list[str]
    metadata: dict[str, Any]
    first_seen: datetime
    last_seen: datetime

    model_config = ConfigDict(from_attributes=True)


class ListAssetsResponse(BaseModel):
    total_count: int
    page: int
    page_size: int
    assets_count: int
    assets: list[AssetResponse]


class RelationResponse(BaseModel):
    id: UUID
    parent_id: UUID
    child_id: UUID
    relation_type: str

    model_config = ConfigDict(from_attributes=True)

class RelationsListResponse(BaseModel):
    """Relations separated by direction relative to the queried asset."""
    children: list[RelationResponse]
    parents : list[RelationResponse]
    total_count: int

class RelatedAsset(BaseModel):
    asset: AssetResponse
    relation_type: str

    model_config = ConfigDict(from_attributes=True)

class AssetGraphResponse(BaseModel):
    asset: AssetResponse
    parents: list[RelatedAsset]
    children: list[RelatedAsset]

    model_config = ConfigDict(from_attributes=True)