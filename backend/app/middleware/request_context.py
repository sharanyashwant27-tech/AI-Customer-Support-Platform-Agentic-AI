"""Request timing and metrics middleware."""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger
from app.observability.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request ID and record Prometheus HTTP metrics."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        start = time.perf_counter()

        response = await call_next(request)

        duration = time.perf_counter() - start
        endpoint = request.url.path
        method = request.method
        status = str(response.status_code)

        HTTP_REQUESTS_TOTAL.labels(
            method=method, endpoint=endpoint, status_code=status
        ).inc()
        HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration:.4f}"

        if not endpoint.startswith("/metrics"):
            logger.info(
                "http_request",
                method=method,
                path=endpoint,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
                request_id=request_id,
            )
        return response
