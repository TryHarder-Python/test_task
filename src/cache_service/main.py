from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cache_service.api import router
from cache_service.config import Settings, get_settings
from cache_service.db import create_engine, create_session_factory
from cache_service.transformer import make_transformer


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Resolved here rather than at import time so importing the app never touches the DB.
        resolved = settings or get_settings()
        engine = create_engine(resolved.database_url)
        app.state.session_factory = create_session_factory(engine)
        app.state.transformer = make_transformer(resolved.transformer_delay_seconds)
        yield
        await engine.dispose()

    app = FastAPI(title="Caching Service", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
