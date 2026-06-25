from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from src.core.database import get_db_session
from src.services.assets_service import AssetsService
from src.models.schema import (
    ListAssetsResponse, AssetResponse,
    CreateAssetRequest, UpdateAssetRequest
)


asset_router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


def get_assets_service(db_session=Depends(get_db_session)):
    return AssetsService(db_session)


@asset_router.get("/", response_model=ListAssetsResponse)
async def get_assets(service: AssetsService = Depends(get_assets_service)):
    assets = service.get_assets()
    response = ListAssetsResponse(
        assets=[AssetResponse.model_validate(a.__dict__ | {"metadata": a.metadata_ or {}}) for a in assets],
        assets_count=len(assets)
    )
    return response


@asset_router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset_by_id(asset_id: str, service: AssetsService = Depends(get_assets_service)):
    asset = service.get_asset_by_id(asset_id)
    if asset:
        return AssetResponse.model_validate(asset.__dict__ | {"metadata": asset.metadata_ or {}})
    return JSONResponse(status_code=404, content={"message": "Asset not found"})


@asset_router.post("/", status_code=201)
async def create_asset(request: CreateAssetRequest, service: AssetsService = Depends(get_assets_service)):
    try:
        created_asset = service.create_asset(request)
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
        return JSONResponse(
            status_code=201,
            content={"message": "Asset created successfully", "asset": response.model_dump(mode="json")}
        )
    except Exception as e:
        return JSONResponse(status_code=400, content={"message": str(e)})


@asset_router.put("/{asset_id}")
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


@asset_router.delete("/{asset_id}")
async def delete_asset(asset_id: str, service: AssetsService = Depends(get_assets_service)):
    deleted = service.delete_asset(asset_id)
    if deleted:
        return JSONResponse(status_code=200, content={"message": "Asset deleted successfully"})
    return JSONResponse(status_code=404, content={"message": "Asset not found"})