from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.core.auth import write_authorized
from src.core.database import get_db_session
from src.models.schema import (
    AssetGraphResponse, AssetResponse, CreateRelationRequest,
    RelatedAsset, RelationResponse, RelationsListResponse,
)
from src.services.relationships_service import RelationshipsService


relations_router = APIRouter(prefix="/api/v1/assets", tags=["relations"])


def get_relations_service(db_session=Depends(get_db_session)):
    return RelationshipsService(db_session)


# ── Create ────────────────────────────────────────────────────────────────────

@relations_router.post(
    "/{asset_id}/relations",
    status_code=201,
    dependencies=[Depends(write_authorized)],
    summary="Create a relation (asset_id is the parent)",
)
async def create_relation(
    asset_id: str,
    request: CreateRelationRequest,
    service: RelationshipsService = Depends(get_relations_service),
):
    relation, error = service.create_relation(asset_id, request.child_id, request.relation_type)

    if error == "parent_not_found":
        return JSONResponse(status_code=404, content={"message": "Parent asset not found"})
    if error == "child_not_found":
        return JSONResponse(status_code=404, content={"message": "Child asset not found"})

    return JSONResponse(
        status_code=201,
        content={
            "message": "Relation created successfully",
            "relation": RelationResponse.model_validate(relation).model_dump(mode="json"),
        },
    )


# ── Read — list all relations for an asset ────────────────────────────────────

@relations_router.get(
    "/{asset_id}/relations",
    response_model=RelationsListResponse,
    summary="List relations for an asset, split into parent and child directions",
)
async def get_relations(
    asset_id: str,
    service: RelationshipsService = Depends(get_relations_service),
):
    relations = service.get_relations(asset_id)
    if relations is None:
        return JSONResponse(status_code=404, content={"message": "Asset not found"})

    children = [r for r in relations if str(r.parent_id) == asset_id]
    parents = [r for r in relations if str(r.child_id)  == asset_id]

    return RelationsListResponse(
        children=[RelationResponse.model_validate(r) for r in children],
        parents=[RelationResponse.model_validate(r) for r in parents],
        total_count=len(relations),
    )


# ── Read — get single relation by ID ─────────────────────────────────────────

@relations_router.get(
    "/{asset_id}/relations/{relation_id}",
    summary="Get a specific relation by its ID",
)
async def get_relation_by_id(
    asset_id: str,
    relation_id: str,
    service: RelationshipsService = Depends(get_relations_service),
):
    relation = service.get_relation_by_id(relation_id)
    if not relation:
        return JSONResponse(status_code=404, content={"message": "Relation not found"})

    return RelationResponse.model_validate(relation).model_dump(mode="json")


# ── Delete ────────────────────────────────────────────────────────────────────

@relations_router.delete(
    "/{asset_id}/relations/{relation_id}",
    dependencies=[Depends(write_authorized)],
    summary="Delete a relation by its ID",
)
async def delete_relation(
    asset_id: str,
    relation_id: str,
    service: RelationshipsService = Depends(get_relations_service),
):
    deleted = service.delete_relation(relation_id)
    if deleted:
        return JSONResponse(status_code=200, content={"message": "Relation deleted successfully"})
    return JSONResponse(status_code=404, content={"message": "Relation not found"})


# ── Graph ─────────────────────────────────────────────────────────────────────

@relations_router.get(
    "/{asset_id}/graph",
    response_model=AssetGraphResponse,
    summary="Fetch an asset together with its full related-asset graph (one hop)",
)
async def get_asset_graph(
    asset_id: str,
    service: RelationshipsService = Depends(get_relations_service),
):
    result = service.get_asset_graph(asset_id)
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Asset not found"})

    asset, parents, children = result

    def to_asset_response(a) -> AssetResponse:
        return AssetResponse.model_validate(a.__dict__ | {"metadata": a.metadata_ or {}})

    return AssetGraphResponse(
        asset=to_asset_response(asset),
        parents=[RelatedAsset(asset=to_asset_response(p["asset"]), relation_type=p["relation_type"]) for p in parents],
        children=[RelatedAsset(asset=to_asset_response(c["asset"]), relation_type=c["relation_type"]) for c in children],
    )
