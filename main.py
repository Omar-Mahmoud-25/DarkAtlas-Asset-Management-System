from fastapi import FastAPI, Depends
from sqlmodel import select
from sqlalchemy.exc import OperationalError
from src.core import get_db_session
from src.routes.asset_router import asset_router

app = FastAPI()
app.include_router(asset_router)

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