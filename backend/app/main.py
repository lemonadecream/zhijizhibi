"""FastAPI application entrypoint.

Single monolith. AI calls are routed exclusively through the internal AI Gateway
module; no route or service imports a vendor SDK directly.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import ensure_production_ready, settings
from app.db.migrate import run_migrations
from app.errors.handlers import register_error_handlers
from app.logging_config import configure_logging, logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    ensure_production_ready()
    try:
        run_migrations()
        logger.info("migrations applied")
    except Exception as exc:  # noqa: BLE001
        # 开发（DEBUG）容忍迁移失败继续跑；生产快速失败——
        # 旧 schema 上跑新代码会把故障推迟到运行时，更难排查。
        if settings.DEBUG:
            logger.warning("migration run skipped/failed: %s", exc)
        else:
            raise
    try:
        from app.db.base import SessionLocal
        from app.services.explore_seed import seed_explore

        with SessionLocal() as db:
            report = seed_explore(db)
            logger.info("explore seed: %s", report)
    except Exception as exc:  # noqa: BLE001
        logger.warning("explore seed skipped/failed: %s", exc)
    try:
        from app.db.seed_city_cost import seed_city_costs

        with SessionLocal() as db:
            seed_city_costs(db.bind)
            logger.info("city_cost seed ensured")
    except Exception as exc:  # noqa: BLE001
        logger.warning("city_cost seed skipped/failed: %s", exc)
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.APP_NAME, version="0.3.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    register_error_handlers(app)
    return app


app = create_app()
