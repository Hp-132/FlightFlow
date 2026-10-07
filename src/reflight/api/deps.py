from collections.abc import Generator

from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from reflight.core.config import get_settings
from reflight.core.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_api_key(x_api_key: str = Header(...)) -> None:
    settings = get_settings()
    if x_api_key != settings.api_static_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
