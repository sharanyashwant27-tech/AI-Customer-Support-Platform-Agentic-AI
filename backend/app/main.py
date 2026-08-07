"""FastAPI application factory and ASGI entrypoint."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from prometheus_client import make_asgi_app

from app import __version__
from app.api.browser_json import accepts_html, pretty_json_response
from app.api.rest import router as rest_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.middleware.request_context import RequestContextMiddleware
from app.observability.metrics import init_app_info

logger = get_logger(__name__)

_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="6" fill="#0f766e"/>'
    '<text x="16" y="22" text-anchor="middle" fill="white" '
    'font-size="14" font-family="Segoe UI,Arial,sans-serif">AI</text></svg>'
)


def _root_payload(settings) -> dict[str, object]:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
        "port": str(settings.port),
        "rest": {
            "POST /chat": "Customer chat (Master Agent)",
            "POST /ticket": "Create ticket",
            "GET /ticket/{id}": "Get ticket",
            "GET /orders/{id}": "Get order",
            "POST /upload": "Upload knowledge file",
            "POST /knowledge/index": "Index knowledge text",
            "GET /customer/{id}": "Customer history",
            "POST /feedback": "Submit feedback",
        },
        "advanced": f"{settings.api_prefix}/advanced",
    }


def _landing_html(settings) -> str:
    name = settings.app_name
    health = f"{settings.api_prefix}/health"
    advanced = f"{settings.api_prefix}/advanced"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{name}</title>
  <link rel="icon" href="/favicon.ico" type="image/svg+xml"/>
  <style>
    :root {{
      --bg: #0b1220;
      --panel: #121a2b;
      --text: #e8eefc;
      --muted: #9db0d0;
      --accent: #2dd4bf;
      --line: #24314d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; min-height: 100vh; font-family: "Segoe UI", system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(1200px 600px at 10% -10%, #134e4a 0%, transparent 55%),
        radial-gradient(900px 500px at 100% 0%, #1e3a5f 0%, transparent 50%),
        var(--bg);
    }}
    main {{
      max-width: 820px; margin: 0 auto; padding: 3.5rem 1.25rem 4rem;
    }}
    h1 {{ font-size: clamp(1.8rem, 4vw, 2.6rem); margin: 0 0 0.5rem; letter-spacing: -0.02em; }}
    p {{ color: var(--muted); line-height: 1.55; margin: 0 0 1.5rem; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 2rem; }}
    a.btn {{
      display: inline-block; text-decoration: none; color: #042f2e; background: var(--accent);
      padding: 0.7rem 1rem; border-radius: 10px; font-weight: 600;
    }}
    a.ghost {{
      display: inline-block; text-decoration: none; color: var(--text);
      border: 1px solid var(--line); padding: 0.7rem 1rem; border-radius: 10px;
      background: rgba(18,26,43,0.7);
    }}
    .card {{
      background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
      padding: 1.1rem 1.2rem; margin-top: 0.75rem;
    }}
    code, .mono {{ font-family: ui-monospace, Consolas, monospace; font-size: 0.92rem; }}
    ul {{ margin: 0.4rem 0 0; padding-left: 1.1rem; color: var(--muted); }}
    li {{ margin: 0.25rem 0; }}
    .ok {{ color: var(--accent); font-weight: 600; }}
  </style>
</head>
<body>
  <main>
    <p class="ok">API online · port {settings.port}</p>
    <h1>{name}</h1>
    <p>Enterprise multi-agent customer support API. Use the docs to explore endpoints, or open the React UI separately.</p>
    <div class="links">
      <a class="btn" href="/docs">OpenAPI Docs</a>
      <a class="ghost" href="/redoc">ReDoc</a>
      <a class="ghost" href="{health}">Health</a>
      <a class="ghost" href="{advanced}">Advanced features</a>
      <a class="ghost" href="/?format=json">JSON</a>
    </div>
    <div class="card">
      <strong>Quick links</strong>
      <ul>
        <li><span class="mono">POST /chat</span> — customer chat</li>
        <li><span class="mono">POST /ticket</span> · <span class="mono">GET /orders/{{id}}</span></li>
        <li><span class="mono">{settings.api_prefix}/advanced</span> — SLA, sentiment, voice, fraud</li>
        <li>UI (Vite): <span class="mono">http://localhost:3000</span> or Docker <span class="mono">:3017</span></li>
      </ul>
    </div>
  </main>
</body>
</html>"""


async def _seed_knowledge() -> None:
    """Ingest sample docs into the vector store on startup (all knowledge sources)."""
    from app.rag.pipeline import rag_pipeline
    from app.rag.sources import infer_knowledge_source

    candidates = [
        Path(__file__).resolve().parents[2] / "sample_data" / "documents",
        Path("/sample_data/documents"),
        Path(__file__).resolve().parents[3] / "sample_data" / "documents",
    ]
    docs_dir = next((p for p in candidates if p.exists()), None)
    if not docs_dir:
        return
    for path in sorted(docs_dir.glob("*.md")):
        try:
            await rag_pipeline.ingest_text(
                title=path.stem.replace("_", " ").title(),
                content=path.read_text(encoding="utf-8"),
                source=path.name,
                file_type="markdown",
                knowledge_source=infer_knowledge_source(filename=path.name),
            )
        except Exception as exc:
            logger.warning("seed_knowledge_failed", path=str(path), error=str(exc))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging()
    init_app_info(version=settings.app_version, environment=settings.environment)
    logger.info(
        "application_startup",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        port=settings.port,
    )
    try:
        from app.db.session import init_db
        from app.rag.vectorstores.factory import reset_vector_store
        from app.agents.master.graph import reset_master_agent
        from app.memory.conversation import reset_memory_for_tests

        reset_vector_store()
        reset_master_agent()
        reset_memory_for_tests()
        try:
            from app.rag.embeddings.factory import reset_embedding_adapter

            reset_embedding_adapter()
        except Exception:
            pass
        await init_db()
        logger.info("database_schema_ready")
    except Exception as exc:
        logger.warning("database_init_skipped", error=str(exc))

    try:
        await _seed_knowledge()
        logger.info("knowledge_seed_complete")
    except Exception as exc:
        logger.warning("knowledge_seed_skipped", error=str(exc))

    yield
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Enterprise AI Customer Support Platform with LangGraph multi-agent "
            "orchestration, RAG, GraphRAG, and interchangeable LLM providers."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestContextMiddleware)
    register_exception_handlers(application)
    application.include_router(api_router, prefix=settings.api_prefix)
    # Public REST contract (POST /chat, POST /ticket, …)
    application.include_router(rest_router)
    application.include_router(rest_router, prefix="/api")

    if settings.enable_metrics:
        # Trailing slash avoids Starlette's 307 redirect on /metrics
        metrics_path = settings.prometheus_metrics_path.rstrip("/") + "/"
        application.mount(metrics_path, make_asgi_app())

        @application.get(settings.prometheus_metrics_path.rstrip("/"), include_in_schema=False)
        async def metrics_redirect() -> RedirectResponse:
            return RedirectResponse(url=metrics_path, status_code=307)

    @application.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(content=_FAVICON_SVG, media_type="image/svg+xml")

    @application.get("/api", include_in_schema=False)
    @application.get("/api/", include_in_schema=False)
    async def api_index() -> dict[str, object]:
        return {
            "message": "Public REST API",
            "docs": "/docs",
            "v1": settings.api_prefix,
            "endpoints": _root_payload(settings)["rest"],
        }

    @application.get(settings.api_prefix, include_in_schema=False)
    @application.get(f"{settings.api_prefix}/", include_in_schema=False)
    async def api_v1_index() -> dict[str, object]:
        return {
            "message": "API v1",
            "docs": "/docs",
            "health": f"{settings.api_prefix}/health",
            "advanced": f"{settings.api_prefix}/advanced",
            "chat": f"{settings.api_prefix}/chat/message",
        }

    @application.get("/", response_model=None)
    async def root(request: Request, format: str | None = None) -> Response:
        """HTML landing for browsers; JSON (pretty-wrapped in browser) on demand."""
        payload = _root_payload(settings)
        if format in {"json", "raw"}:
            return pretty_json_response(
                request,
                payload,
                title="API Root JSON",
                force_raw=(format == "raw"),
            )
        if format == "html" or accepts_html(request):
            return HTMLResponse(_landing_html(settings))
        return JSONResponse(payload)

    return application


app = create_app()
