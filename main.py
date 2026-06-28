from fastapi import FastAPI, Depends
from sqlmodel import select
from sqlalchemy.exc import OperationalError
from src.core import get_db_session
from src.routes.asset_router import asset_router
from src.routes.relationships_router import relations_router
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager

def run_scheduler():
    from src.services.assets_service import AssetsService
    from src.core.config import get_config

    config = get_config()
    db_session = next(get_db_session())
    assets_service = AssetsService(db_session)
    assets_service.mark_stale_assets(config.STALE_ASSET_DAYS_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scheduler, 'interval', hours=0.1)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()

app = FastAPI(lifespan=lifespan, title="DarkAtlas Asset Management System", version="1.0.0")
app.include_router(asset_router)
app.include_router(relations_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/db-health")
async def db_health_check(session = Depends(get_db_session)):
    try:
        statement = select(1)
        return {"status": f"healthy {list(session.exec(statement).all())}"}
    except OperationalError:
        return {"status": "unhealthy"}