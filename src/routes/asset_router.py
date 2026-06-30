from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from src.core.database import get_db_session
from src.services.assets_service import AssetsService
from src.models.schema import (
    ListAssetsResponse, AssetResponse,
    CreateAssetRequest, UpdateAssetRequest, AssetFilters
)
from src.models.enums import AssetType, AssetStatus
from typing import Optional, Literal
from src.core.auth import write_authorized
from src.services.risk_service import RiskService

asset_router = APIRouter(prefix="/api/v1/assets", tags=["Assets"])


def get_assets_service(db_session=Depends(get_db_session)):
    return AssetsService(db_session)


@asset_router.get(
    "/",
    response_model=ListAssetsResponse,
    summary="List assets",
    description="Retrieve a paginated list of assets with optional filtering by type, status, tag, source, or value substring. Supports sorting and pagination.",
)
async def get_assets(
    type: Optional[AssetType] = Query(default=None, description="Filter by asset type"),
    status: Optional[AssetStatus] = Query(default=None, description="Filter by asset status"),
    tag: Optional[str] = Query(default=None, description="Filter assets that contain this tag"),
    value_contains: Optional[str] = Query(default=None, description="Substring search on asset value"),
    source: Optional[str] = Query(default=None, description="Filter by source"),
    sort_by: Literal["value", "type", "status", "first_seen", "last_seen"] = Query(
        default="last_seen", description="Field to sort by"
    ),
    sort_order: Literal["asc", "desc"] = Query(default="desc", description="Sort direction"),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=200, description="Results per page"),
    service: AssetsService = Depends(get_assets_service),
):
    filters = AssetFilters(
        type=type,
        status=status,
        tag=tag,
        value_contains=value_contains,
        source=source,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    assets, total_count = service.get_assets(filters)
    asset_responses = [
        AssetResponse.model_validate(a.__dict__ | {"metadata": a.metadata_ or {}})
        for a in assets
    ]
    return ListAssetsResponse(
        total_count=total_count,
        page=page,
        page_size=page_size,
        assets_count=len(asset_responses),
        assets=asset_responses,
    )


@asset_router.get(
    "/{asset_id}",
    response_model=AssetResponse,
    summary="Get asset by ID",
    description="Retrieve a single asset by its UUID.",
)
async def get_asset_by_id(asset_id: str, service: AssetsService = Depends(get_assets_service)):
    asset = service.get_asset_by_id(asset_id)
    if asset:
        return AssetResponse.model_validate(asset.__dict__ | {"metadata": asset.metadata_ or {}})
    return JSONResponse(status_code=404, content={"message": "Asset not found"})

@asset_router.post(
    "/bulk",
    status_code=201,
    dependencies=[Depends(write_authorized)],
    summary="Bulk import assets",
    description="Import a batch of assets in one request. Performs upsert (dedup by type+value), merges tags/metadata, and resolves `parent`/`covers` relationships. Malformed records are skipped; the rest of the batch proceeds.",
)
async def bulk_create_assets(
    assets_data: list[dict],
    service: AssetsService = Depends(get_assets_service)
):
    try:
        created_count, updated_count, errors = service.bulk_create_assets(assets_data)
        return JSONResponse(
            status_code=201,
            content={
                "created_assets_count": created_count,
                "updated_assets_count": updated_count,
                "errors": errors
            }
        )
    except Exception as e:
        return JSONResponse(status_code=400, content={"message": str(e)})

@asset_router.post(
    "/",
    status_code=201,
    dependencies=[Depends(write_authorized)],
    summary="Create or upsert an asset",
    description="Create a new asset or update an existing one if the (type, value) pair already exists. On upsert: tags are merged (set-union), metadata is shallow-merged (newer wins), status is forced to active, and last_seen is bumped.",
)
async def create_asset(request: CreateAssetRequest, service: AssetsService = Depends(get_assets_service)):
    try:
        created_asset, merged = service.create_asset(request)
        response = AssetResponse(
            id=created_asset.id,
            type=created_asset.type,
            status=created_asset.status,
            value=created_asset.value,
            source=created_asset.source,
            tags=created_asset.tags,
            metadata=created_asset.metadata_ or {},
            first_seen=created_asset.first_seen,
            last_seen=created_asset.last_seen,
        )
        action = "updated" if merged else "created"
        return JSONResponse(
            status_code=201,
            content={"message": f"Asset {action} successfully", "asset": response.model_dump(mode="json")}
        )
    except Exception as e:
        return JSONResponse(status_code=400, content={"message": str(e)})


@asset_router.put(
    "/{asset_id}",
    status_code=200,
    dependencies=[Depends(write_authorized)],
    summary="Update an asset",
    description="Partially update an asset by ID. Only provided fields are overwritten; `first_seen` is always preserved.",
)
async def update_asset(
    asset_id: str,
    updated_asset: UpdateAssetRequest,
    service: AssetsService = Depends(get_assets_service)
):
    try:
        asset = service.update_asset(asset_id, updated_asset)
        if asset:
            response = AssetResponse(
                id=asset.id,
                type=asset.type,
                status=asset.status,
                value=asset.value,
                source=asset.source,
                tags=asset.tags,
                metadata=asset.metadata_ or {},
                first_seen=asset.first_seen,
                last_seen=asset.last_seen,
            )
            return JSONResponse(
                status_code=200,
                content={"message": "Asset updated successfully", "asset": response.model_dump(mode="json")}
            )
        return JSONResponse(status_code=404, content={"message": "Asset not found"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"message": str(e)})


@asset_router.delete(
    "/{asset_id}",
    status_code=200,
    dependencies=[Depends(write_authorized)],
    summary="Delete an asset",
    description="Permanently delete an asset by ID. To soft-delete, use PATCH /status to set it to `archived` instead.",
)
async def delete_asset(asset_id: str, service: AssetsService = Depends(get_assets_service)):
    deleted = service.delete_asset(asset_id)
    if deleted:
        return JSONResponse(status_code=200, content={"message": "Asset deleted successfully"})
    return JSONResponse(status_code=404, content={"message": "Asset not found"})


@asset_router.patch(
    "/{asset_id}/status",
    status_code=200,
    dependencies=[Depends(write_authorized)],
    summary="Change asset status",
    description="Set an asset's status to `active`, `stale`, or `archived`.",
)
async def update_asset_status(
    asset_id: str,
    status: AssetStatus = Query(..., description="New status to set"),
    service: AssetsService = Depends(get_assets_service),
):
    asset = service.set_asset_status(asset_id, status)
    if not asset:
        return JSONResponse(status_code=404, content={"message": "Asset not found"})
    return JSONResponse(status_code=200, content={"message": f"Asset marked {status.value}"})


def get_risk_service(db_session=Depends(get_db_session)):
    return RiskService(db_session)

@asset_router.get("/{asset_id}/risk", status_code=200)
async def get_asset_risk(
    asset_id: str,
    model: Optional[str] = Query(default=None, description="The Gemini model to use (e.g. gemini-1.5-pro-latest)"),
    service = Depends(get_risk_service)
):
    """Evaluate cybersecurity risk for an asset using LangChain + Google Gemini."""
    try:
        assessment = service.evaluate_asset_risk(asset_id, model_name=model)
        if assessment is None:
            return JSONResponse(status_code=404, content={"message": "Asset not found"})
        return JSONResponse(status_code=200, content=assessment)
    except ValueError as ve:
        return JSONResponse(status_code=503, content={"message": str(ve)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})
