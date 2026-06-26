from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader
from .config import get_config

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def write_authorized(api_key: str = Security(api_key_header)):
    config = get_config()
    if api_key is None:
        raise HTTPException(status_code=401, detail="API key is missing")
    if api_key != config.API_KEY:
        raise HTTPException(status_code=403, detail="Not authorized to write assets")