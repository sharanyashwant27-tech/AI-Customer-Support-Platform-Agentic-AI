"""Prometheus metrics registry and helpers."""

from prometheus_client import Counter, Gauge, Histogram, Info

APP_INFO = Info("aics_app", "AI Customer Support Platform application info")

HTTP_REQUESTS_TOTAL = Counter(
    "aics_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION = Histogram(
    "aics_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

AGENT_INVOCATIONS_TOTAL = Counter(
    "aics_agent_invocations_total",
    "Total agent invocations",
    ["agent_name", "status"],
)

AGENT_DURATION = Histogram(
    "aics_agent_duration_seconds",
    "Agent execution duration in seconds",
    ["agent_name"],
)

LLM_TOKENS_TOTAL = Counter(
    "aics_llm_tokens_total",
    "Total LLM tokens consumed",
    ["provider", "model", "token_type"],
)

CHAT_MESSAGES_TOTAL = Counter(
    "aics_chat_messages_total",
    "Total chat messages processed",
    ["intent", "handoff"],
)

ACTIVE_SESSIONS = Gauge(
    "aics_active_sessions",
    "Number of active chat sessions",
)

RAG_RETRIEVALS_TOTAL = Counter(
    "aics_rag_retrievals_total",
    "Total RAG retrieval operations",
    ["store", "status"],
)


def init_app_info(version: str, environment: str) -> None:
    APP_INFO.info({"version": version, "environment": environment})
