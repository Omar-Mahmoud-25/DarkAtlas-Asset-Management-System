from fastapi import FastAPI, Depends
from sqlmodel import select
from sqlalchemy.exc import OperationalError
from src.core import get_db_session
from src.core.database import engine
from src.routes.asset_router import asset_router
from src.routes.relationships_router import relations_router
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from sqlmodel import Session

def run_scheduler():
    from src.services.assets_service import AssetsService
    from src.core.config import get_config

    config = get_config()
    with Session(engine) as session:
        assets_service = AssetsService(session)
        assets_service.mark_stale_assets(config.STALE_ASSET_DAYS_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.core.config import get_config
    config = get_config()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scheduler, 'interval', hours=config.STALE_JOB_INTERVAL_HOURS)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()

app = FastAPI(
    lifespan=lifespan,
    title="DarkAtlas Asset Management System",
    version="1.0.0",
    description=(
        "Attack Surface Management API — track digital assets (domains, subdomains, IPs, "
        "certificates, services, technologies), manage their lifecycle, model relationships, "
        "and enforce deduplication on every import."
    ),
    openapi_tags=[
        {"name": "Assets", "description": "CRUD, filtering, sorting, pagination, and bulk import of assets."},
        {"name": "Relations", "description": "Directed relationships between assets and graph traversal."},
        {"name": "Health", "description": "Service and database health checks."},
    ],
)
app.include_router(asset_router)
app.include_router(relations_router)

@app.get("/health", tags=["Health"], summary="Service health check")
async def health_check():
    return {"status": "healthy"}

@app.get("/db-health", tags=["Health"], summary="Database health check")
async def db_health_check(session = Depends(get_db_session)):
    try:
        statement = select(1)
        return {"status": f"healthy {list(session.exec(statement).all())}"}
    except OperationalError:
        return {"status": "unhealthy"}