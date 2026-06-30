import logging
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
from src.core.config import get_config
from src.services.assets_service import AssetsService

# Initialize logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

def run_scheduler():
    config = get_config()
    logger.info("Running stale assets identification scheduler job...")
    try:
        with Session(engine) as session:
            assets_service = AssetsService(session)
            assets_service.mark_stale_assets(config.STALE_ASSET_DAYS_INTERVAL)
        logger.info("Scheduler job finished successfully.")
    except Exception as e:
        logger.error("Failed to run stale assets scheduler job: %s", str(e), exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    logger.info("Initializing application background scheduler...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scheduler, 'interval', hours=config.STALE_JOB_INTERVAL_HOURS)
    scheduler.start()
    logger.info("Background scheduler started successfully.")
    try:
        yield
    finally:
        logger.info("Shutting down background scheduler...")
        scheduler.shutdown()
        logger.info("Background scheduler shut down successfully.")

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