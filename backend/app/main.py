from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.init_db import create_tables, seed_defaults
from app.db.session import SessionLocal
from app.scheduler.engine import scheduler_manager
from app.services.agent_service import autonomous_agent


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    create_tables()
    with SessionLocal() as db:
        seed_defaults(db)
    autonomous_agent.prepare_startup()
    scheduler_manager.start()
    try:
        yield
    finally:
        scheduler_manager.shutdown()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/")
def root() -> dict:
    return {"app": settings.app_name, "status": "ok"}
