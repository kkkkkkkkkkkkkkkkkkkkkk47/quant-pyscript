"""FastAPI application factory for the Quant Ratings API.

Production usage::

    uvicorn quant_ratings.api.app:app --host 0.0.0.0 --port 8000

The app wires itself to the live RatingEngine on startup via the
``build_live_engine`` factory.  Dependency overrides are still supported
for testing::

    from quant_ratings.api.app import app
    from quant_ratings.api.router import get_store, get_security_registry, get_rating_engine

    app.dependency_overrides[get_store] = lambda: my_mock_store
    app.dependency_overrides[get_security_registry] = lambda: my_mock_registry
    app.dependency_overrides[get_rating_engine] = lambda: my_mock_engine
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from quant_ratings.api.router import (
    get_rating_engine,
    get_security_registry,
    get_store,
    router,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Wire the live RatingEngine into FastAPI on startup.

    If the live engine cannot be constructed (e.g. missing dependencies),
    the app falls back to the stub providers that raise NotImplementedError —
    tests override these anyway via ``app.dependency_overrides``.
    """
    try:
        from quant_ratings.config.engine_factory import build_live_engine

        engine = build_live_engine()
        store = engine._store  # type: ignore[attr-defined]
        registry = engine._security_registry  # type: ignore[attr-defined]

        application.dependency_overrides[get_store] = lambda: store
        application.dependency_overrides[get_security_registry] = lambda: registry
        application.dependency_overrides[get_rating_engine] = lambda: engine

        logger.info(
            "Live RatingEngine wired: %d securities registered",
            len(registry.all_securities()),
        )
    except Exception as exc:
        logger.warning(
            "Could not wire live RatingEngine — API will return 503 until "
            "dependencies are overridden: %s",
            exc,
        )

    yield  # application runs here

    # Shutdown: nothing to clean up for now
    logger.info("API server shutting down.")


app = FastAPI(
    title="Basilica III API",
    description="Multi-dimensional quantitative ratings for FX, equities, indices, commodities, and crypto.",
    version="0.1.0",
    lifespan=_lifespan,
)
app.include_router(router)

# ---------------------------------------------------------------------------
# Serve the React frontend from frontend/dist/
# The SPA catch-all must come AFTER the API router so /ratings/* and /health
# are handled by the API, and everything else falls through to index.html.
# ---------------------------------------------------------------------------
_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
_DIST = os.path.normpath(_DIST)

if os.path.isdir(_DIST):
    # Serve static assets (JS, CSS, images) at their exact paths
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        """Return index.html for any non-API path so React Router works."""
        index = os.path.join(_DIST, "index.html")
        return FileResponse(index)
else:
    logger.warning(
        "frontend/dist not found — run 'npm run build' in the frontend/ directory "
        "to enable the React UI at http://localhost:8000/"
    )
