"""Health and readiness endpoints with live dependency probes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.api.browser_json import pretty_json_response
from app.core.config import get_settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])

_PROBE_TIMEOUT_S = 1.5


async def _probe_postgres() -> str:
    try:
        from sqlalchemy import text

        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return "up"
    except Exception:
        return "down"


async def _probe_redis() -> str:
    try:
        from app.memory.conversation import RedisMemoryStore

        store = RedisMemoryStore()
        try:
            return "up" if await store.ping() else "down"
        finally:
            try:
                await store._client.aclose()
            except Exception:
                pass
    except Exception:
        return "down"


async def _probe_qdrant() -> str:
    try:
        from qdrant_client import QdrantClient

        settings = get_settings()
        client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=1.0,
            check_compatibility=False,
        )
        client.get_collections()
        return "up"
    except Exception:
        return "down"


async def _probe_rabbitmq() -> str:
    try:
        from app.workflows.events import event_publisher

        ok = await event_publisher.connect()
        return "up" if ok else "down"
    except Exception:
        return "down"


async def _timed(name: str, coro) -> tuple[str, str]:
    try:
        status = await asyncio.wait_for(coro, timeout=_PROBE_TIMEOUT_S)
        return name, status if isinstance(status, str) else "down"
    except Exception:
        return name, "down"


async def _collect_services() -> dict[str, str]:
    settings = get_settings()
    results = await asyncio.gather(
        _timed("postgres", _probe_postgres()),
        _timed("redis", _probe_redis()),
        _timed("rabbitmq", _probe_rabbitmq()),
        _timed("qdrant", _probe_qdrant()),
    )
    services = {name: status for name, status in results}
    services.update(
        {
            "api": "up",
            "neo4j": "configured",
            "llm": settings.default_llm_provider,
            "vector_store": settings.vector_store,
        }
    )
    return services


def _health_html(payload: dict) -> str:
    rows = []
    for key, value in (payload.get("services") or {}).items():
        tone = "#16a34a" if value in {"up", "configured"} or key in {"llm", "vector_store"} else "#dc2626"
        if value == "down":
            tone = "#dc2626"
        elif value == "up":
            tone = "#16a34a"
        else:
            tone = "#0f766e"
        rows.append(
            f"<tr><td>{key}</td><td style='color:{tone};font-weight:600'>{value}</td></tr>"
        )
    status = payload.get("status", "ok")
    status_color = "#16a34a" if status == "ok" else "#ca8a04"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Health · {payload.get('version', '')}</title>
  <style>
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:#0b1220; color:#e8eefc; }}
    main {{ max-width:640px; margin:0 auto; padding:2.5rem 1.25rem; }}
    h1 {{ margin:0 0 .4rem; }}
    p {{ color:#9db0d0; }}
    .badge {{ display:inline-block; padding:.35rem .7rem; border-radius:999px;
      background:rgba(22,163,74,.15); color:{status_color}; font-weight:700; }}
    table {{ width:100%; border-collapse:collapse; margin-top:1.25rem;
      background:#121a2b; border:1px solid #24314d; border-radius:12px; overflow:hidden; }}
    td {{ padding:.7rem .9rem; border-bottom:1px solid #24314d; }}
    tr:last-child td {{ border-bottom:none; }}
    a {{ color:#2dd4bf; }}
  </style>
</head>
<body>
  <main>
    <span class="badge">{status}</span>
    <h1>API Health</h1>
    <p>version {payload.get('version')} · {payload.get('environment')}</p>
    <table>{''.join(rows)}</table>
    <p style="margin-top:1.25rem"><a href="/">Home</a> · <a href="/docs">Docs</a> ·
      <a href="/api/v1/health?format=json">JSON</a></p>
  </main>
</body>
</html>"""


@router.get("/health", response_model=None)
async def health(request: Request, format: str | None = None) -> Response:
    """Liveness/dependency status. HTML for browsers, JSON for API clients."""
    settings = get_settings()
    services = await _collect_services()
    critical = ("postgres", "redis", "qdrant")
    degraded = any(services.get(k) == "down" for k in critical)
    payload = HealthResponse(
        status="degraded" if degraded else "ok",
        version=settings.app_version,
        environment=settings.environment,
        services=services,
    ).model_dump()

    accept = (request.headers.get("accept") or "").lower()
    if format in {"json", "raw"}:
        return pretty_json_response(
            request,
            payload,
            title="API Health JSON",
            force_raw=(format == "raw"),
        )
    if format == "html" or ("text/html" in accept and "application/json" not in accept):
        return HTMLResponse(_health_html(payload))
    return JSONResponse(payload)


@router.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}
