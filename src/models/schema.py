from pydantic import BaseModel
from typing import Any, Optional
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
    assets_count: int
    assets: list[AssetResponse]