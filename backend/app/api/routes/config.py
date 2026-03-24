from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.config import ConfigResponse, ConfigUpdate
from app.services.config_service import get_config_bundle, update_config_bundle


router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=ConfigResponse)
def get_config(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> ConfigResponse:
    return get_config_bundle(db)


@router.put("", response_model=ConfigResponse)
def put_config(
    payload: ConfigUpdate,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfigResponse:
    bundle = update_config_bundle(db, payload)
    return bundle

