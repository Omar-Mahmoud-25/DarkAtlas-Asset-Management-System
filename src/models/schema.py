from pydantic import BaseModel, Field
from typing import Any, Optional, Literal
from uuid import UUID
from datetime import datetime
from src.models.enums import AssetType, AssetStatus


class CreateAssetRequest(BaseModel):
    type: AssetType
    status: AssetStatus = AssetStatus.active
    value: str
    source: Optional[str] = None
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
    source: Optional[str] = None
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    parent: Optional[str] = None
    covers: Optional[str] = None

class AssetResponse(BaseModel):
    id: UUID
    type: AssetType
    status: AssetStatus
    value: str
    source: Optional[str]
    tags: list[str]
    metadata: dict[str, Any]
    first_seen: datetime
    last_seen: datetime

    class Config:
        from_attributes = True


class ListAssetsResponse(BaseModel):
    total_count: int
    page: int
    page_size: int
    assets_count: int
    assets: list[AssetResponse]