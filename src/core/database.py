from src.core.config import get_config
from sqlmodel import create_engine, Session

settings = get_config()
engine = create_engine(settings.DATABASE_URL)

def get_db_session():
    with Session(engine) as session:
        yield session