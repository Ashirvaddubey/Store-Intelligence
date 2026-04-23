"""
Store Intelligence API — FastAPI entrypoint
"""
import os
import uuid
import time
import structlog
from contextlib import asynccontextmanager

from app.logging_config import configure_logging
configure_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import init_db, close_db
from app.cache import init_cache, close_cache
from app.routers import events, stores, health, ws

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    await init_db()
    await init_cache()

    # Auto-load POS transactions if CSV is available
    pos_csv = os.getenv("POS_CSV_PATH", "data/pos_transactions.csv")
    try:
        from app.pos_correlation import load_pos_transactions
        from app.db import AsyncSessionLocal
        import pathlib
        if pathlib.Path(pos_csv).exists():
            async with AsyncSessionLocal() as db:
                n = await load_pos_transactions(pos_csv, db)
                await db.commit()
            log.info("pos_transactions_autoloaded", count=n, path=pos_csv)
    except Exception as exc:
        log.warning("pos_autoload_skipped", reason=str(exc))

    log.info("store_intelligence_api_started")
    yield
    await close_db()
    await close_cache()
    log.info("store_intelligence_api_stopped")


_TAGS_METADATA = [
    {
        "name": "Events",
        "description": (
            "**Batch event ingestion** — accepts up to 500 CCTV-derived tracking events per request. "
            "Idempotent by `event_id`; partial-success on malformed items."
        ),
    },
    {
        "name": "Stores",
        "description": (
            "**Store analytics** — real-time KPIs, conversion funnel, zone heatmap, and anomaly detection. "
            "All endpoints exclude `is_staff=true` events and support a configurable `window_hours` lookback."
        ),
    },
    {
        "name": "WebSocket",
        "description": (
            "**Live feed** — connect to `ws://host/ws/{store_id}` to receive `metrics_snapshot` (every 30 s) "
            "and `event` messages in real time."
        ),
    },
    {
        "name": "Health",
        "description": (
            "**Readiness probe** — DB + Redis connectivity check plus per-store feed-lag indicator. "
            "Returns `STALE_FEED` if no events have arrived for > 10 minutes."
        ),
    },
]

app = FastAPI(
    title="Store Intelligence API",
    description=(
        "## Apex Retail — Store Intelligence\n\n"
        "Real-time retail analytics pipeline built on CCTV tracking events.\n\n"
        "### Quick links\n"
        "- **Live dashboard** (Docker): http://localhost:3000\n"
        "- **Demo dashboard** (no backend): open `dashboard/public/demo.html` in a browser\n"
        "- **API reference**: [docs/API.md](https://github.com/Ashirvaddubey/Store-Intelligence/blob/main/docs/API.md)\n\n"
        "### Auth\n"
        "No authentication required — all endpoints are open.\n\n"
        "### Trace ID\n"
        "Every response includes `X-Trace-Id` header for log correlation."
    ),
    version="1.0.0",
    openapi_tags=_TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    """Log every request with trace_id, latency, store_id, status."""
    trace_id = str(uuid.uuid4())
    store_id = request.path_params.get("store_id", "N/A")
    start = time.perf_counter()

    request.state.trace_id = trace_id
    request.state.event_count = None

    try:
        response: Response = await call_next(request)
    except Exception as exc:
        log.error(
            "unhandled_exception",
            trace_id=trace_id,
            path=request.url.path,
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "trace_id": trace_id},
        )

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    log.info(
        "http_request",
        trace_id=trace_id,
        store_id=store_id,
        endpoint=request.url.path,
        method=request.method,
        status_code=response.status_code,
        latency_ms=latency_ms,
        event_count=getattr(request.state, "event_count", None),
    )
    response.headers["X-Trace-Id"] = trace_id
    return response


# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(events.router, prefix="/events", tags=["Events"])
app.include_router(stores.router, prefix="/stores", tags=["Stores"])
app.include_router(health.router, tags=["Health"])
app.include_router(ws.router, tags=["WebSocket"])


# ── Root landing page ─────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    """Human-friendly landing page listing all key URLs."""
    return JSONResponse({
        "service": "Store Intelligence API",
        "version": "1.0.0",
        "links": {
            "swagger_ui":       "/docs",
            "redoc":            "/redoc",
            "openapi_json":     "/openapi.json",
            "health":           "/health",
            "sample_metrics":   "/stores/STORE_BLR_002/metrics",
            "sample_funnel":    "/stores/STORE_BLR_002/funnel",
            "sample_heatmap":   "/stores/STORE_BLR_002/heatmap",
            "sample_anomalies": "/stores/STORE_BLR_002/anomalies",
            "live_dashboard":   "http://localhost:3000",
        },
    })
