import logging
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.core.auth import write_authorized
from src.core.database import get_db_session
from src.models.schema import (
    AssetGraphResponse, AssetResponse, CreateRelationRequest,
    RelatedAsset, RelationResponse, RelationsListResponse,
)
from src.services.relationships_service import RelationshipsService

logger = logging.getLogger(__name__)

relations_router = APIRouter(prefix="/api/v1/assets", tags=["Relations"])


def get_relations_service(db_session=Depends(get_db_session)):
    return RelationshipsService(db_session)


# ── Create ────────────────────────────────────────────────────────────────────

@relations_router.post(
    "/{asset_id}/relations",
    status_code=201,
    dependencies=[Depends(write_authorized)],
    summary="Create a relation",
    description="Create a directed relation where `asset_id` is the parent and `child_id` is the child. `relation_type` is a free-form string (e.g. `parent`, `covers`).",
)
async def create_relation(
    asset_id: str,
    request: CreateRelationRequest,
    service: RelationshipsService = Depends(get_relations_service),
):
    logger.info("Creating relation: parent=%s, child=%s, type=%s", asset_id, request.child_id, request.relation_type)
    relation, error = service.create_relation(asset_id, request.child_id, request.relation_type)

    if error == "parent_not_found":
        logger.warning("Failed to create relation: Parent asset %s not found", asset_id)
        return JSONResponse(status_code=404, content={"message": "Parent asset not found"})
    if error == "child_not_found":
        logger.warning("Failed to create relation: Child asset %s not found", request.child_id)
        return JSONResponse(status_code=404, content={"message": "Child asset not found"})

    logger.info("Successfully created relation: ID=%s", relation.id)
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
    summary="List relations for an asset",
    description="Return all relations involving this asset, split into `parents` (where this asset is the child) and `children` (where this asset is the parent).",
)
async def get_relations(
    asset_id: str,
    service: RelationshipsService = Depends(get_relations_service),
):
    logger.debug("Listing relations for asset ID: %s", asset_id)
    relations = service.get_relations(asset_id)
    if relations is None:
        logger.warning("Asset not found for listing relations: ID=%s", asset_id)
        return JSONResponse(status_code=404, content={"message": "Asset not found"})

    children = [r for r in relations if str(r.parent_id) == asset_id]
    parents = [r for r in relations if str(r.child_id)  == asset_id]

    logger.debug("Found %d children and %d parents for asset ID: %s", len(children), len(parents), asset_id)
    return RelationsListResponse(
        children=[RelationResponse.model_validate(r) for r in children],
        parents=[RelationResponse.model_validate(r) for r in parents],
        total_count=len(relations),
    )


# ── Read — get single relation by ID ─────────────────────────────────────────

@relations_router.get(
    "/{asset_id}/relations/{relation_id}",
    summary="Get a relation by ID",
    description="Retrieve a single relation by its UUID.",
)
async def get_relation_by_id(
    asset_id: str,
    relation_id: str,
    service: RelationshipsService = Depends(get_relations_service),
):
    logger.debug("Getting relation ID: %s for asset ID: %s", relation_id, asset_id)
    relation = service.get_relation_by_id(relation_id)
    if not relation:
        logger.warning("Relation ID=%s not found", relation_id)
        return JSONResponse(status_code=404, content={"message": "Relation not found"})

    return RelationResponse.model_validate(relation).model_dump(mode="json")


# ── Delete ────────────────────────────────────────────────────────────────────

@relations_router.delete(
    "/{asset_id}/relations/{relation_id}",
    dependencies=[Depends(write_authorized)],
    summary="Delete a relation",
    description="Permanently delete a relation by its UUID.",
)
async def delete_relation(
    asset_id: str,
    relation_id: str,
    service: RelationshipsService = Depends(get_relations_service),
):
    logger.info("Deleting relation ID: %s for asset ID: %s", relation_id, asset_id)
    deleted = service.delete_relation(relation_id)
    if deleted:
        logger.info("Relation ID=%s deleted successfully", relation_id)
        return JSONResponse(status_code=200, content={"message": "Relation deleted successfully"})
    logger.warning("Relation ID=%s not found for deletion", relation_id)
    return JSONResponse(status_code=404, content={"message": "Relation not found"})


# ── Graph ─────────────────────────────────────────────────────────────────────

@relations_router.get(
    "/{asset_id}/graph",
    response_model=AssetGraphResponse,
    summary="Get asset graph",
    description="Return an asset together with its immediate parents and children (one-hop graph). Each related entry includes the full asset object and the relation type.",
)
async def get_asset_graph(
    asset_id: str,
    service: RelationshipsService = Depends(get_relations_service),
):
    logger.debug("Getting asset graph for asset ID: %s", asset_id)
    result = service.get_asset_graph(asset_id)
    if result is None:
        logger.warning("Asset ID=%s not found for graph retrieval", asset_id)
        return JSONResponse(status_code=404, content={"message": "Asset not found"})

    asset, parents, children = result

    def to_asset_response(a) -> AssetResponse:
        return AssetResponse.model_validate(a.__dict__ | {"metadata": a.metadata_ or {}})

    logger.debug(
        "Successfully retrieved graph for asset ID: %s. Parents count: %d, Children count: %d",
        asset_id, len(parents), len(children)
    )
    return AssetGraphResponse(
        asset=to_asset_response(asset),
        parents=[RelatedAsset(asset=to_asset_response(p["asset"]), relation_type=p["relation_type"]) for p in parents],
        children=[RelatedAsset(asset=to_asset_response(c["asset"]), relation_type=c["relation_type"]) for c in children],
    )
