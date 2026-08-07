"""Advanced features REST API."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from app.advanced import features as adv
from app.api.browser_json import pretty_json_response

router = APIRouter(prefix="/advanced", tags=["advanced-features"])

_FEATURES = [
    "AI-generated ticket summaries",
    "Voice-to-text support",
    "Speech synthesis responses",
    "Customer sentiment dashboard",
    "SLA monitoring",
    "Auto-priority (P1/P2/P3)",
    "AI-powered quality assurance",
    "Agent performance analytics",
    "Customer satisfaction prediction",
    "Fraud detection for refunds",
    "Conversation summarization",
    "Multilingual support (50+ languages)",
    "AI-powered FAQ generation",
    "Continuous knowledge-base ingestion",
    "Real-time notifications",
    "Feedback-driven prompt optimization",
]

_QUICK_LINKS = [
    ("GET", "/api/v1/advanced/sentiment/dashboard", "Sentiment dashboard"),
    ("GET", "/api/v1/advanced/sla", "SLA monitoring"),
    ("GET", "/api/v1/advanced/analytics/agents", "Agent analytics"),
    ("GET", "/api/v1/advanced/languages", "50+ languages"),
    ("GET", "/api/v1/advanced/prompts/optimization", "Prompt optimization"),
    ("GET", "/api/v1/advanced/notifications/poll", "Notifications poll"),
]


def _features_payload() -> dict[str, Any]:
    return {
        "features": list(_FEATURES),
        "count": len(_FEATURES),
        "docs": "/docs#/advanced-features",
        "endpoints": [
            {"method": m, "path": p, "label": label} for m, p, label in _QUICK_LINKS
        ],
    }


def _features_html(payload: dict[str, Any]) -> str:
    feature_items = "".join(f"<li>{f}</li>" for f in payload["features"])
    link_items = "".join(
        f'<li><a href="{e["path"]}">{e["label"]}</a> '
        f'<code>{e["method"]} {e["path"]}</code></li>'
        for e in payload["endpoints"]
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Advanced Features</title>
  <style>
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:#0b1220; color:#e8eefc; }}
    main {{ max-width:760px; margin:0 auto; padding:2.5rem 1.25rem 3rem; }}
    h1 {{ margin:0 0 .4rem; }}
    p, li {{ color:#9db0d0; line-height:1.5; }}
    .card {{ background:#121a2b; border:1px solid #24314d; border-radius:14px;
      padding:1rem 1.15rem; margin-top:1rem; }}
    a {{ color:#2dd4bf; }}
    code {{ font-family:ui-monospace,Consolas,monospace; font-size:.85rem; color:#cbd5e1; }}
    .badge {{ display:inline-block; background:rgba(45,212,191,.15); color:#2dd4bf;
      padding:.3rem .65rem; border-radius:999px; font-weight:700; margin-bottom:.75rem; }}
  </style>
</head>
<body>
  <main>
    <div class="badge">{payload["count"]} features online</div>
    <h1>Advanced Features</h1>
    <p>Enterprise capabilities for summaries, SLA, sentiment, voice, fraud, and more.</p>
    <div class="card">
      <strong>Feature list</strong>
      <ul>{feature_items}</ul>
    </div>
    <div class="card">
      <strong>Try these GETs</strong>
      <ul>{link_items}</ul>
    </div>
    <p style="margin-top:1.25rem">
      <a href="/">Home</a> · <a href="/docs">Docs</a> ·
      <a href="/api/v1/advanced?format=json">JSON</a>
    </p>
  </main>
</body>
</html>"""


@router.get("", include_in_schema=False)
@router.get("/")
async def list_advanced_features(
    request: Request, format: str | None = None
) -> Response:
    """Catalog of advanced features. HTML for browsers, JSON for API clients."""
    payload = _features_payload()
    accept = (request.headers.get("accept") or "").lower()
    if format in {"json", "raw"}:
        return pretty_json_response(
            request,
            payload,
            title="Advanced Features JSON",
            force_raw=(format == "raw"),
        )
    if format == "html" or ("text/html" in accept and "application/json" not in accept):
        return HTMLResponse(_features_html(payload))
    return JSONResponse(payload)

@router.post("/ticket/summary")
async def ticket_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return await adv.summarize_ticket(
        subject=str(payload.get("subject") or "Support request"),
        description=str(payload.get("description") or payload.get("message") or ""),
        intent=payload.get("intent"),
        sentiment=payload.get("sentiment"),
    )


@router.post("/conversation/summary")
async def conversation_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return await adv.summarize_conversation(
        payload.get("turns"),
        session_id=payload.get("session_id"),
    )


@router.post("/priority")
async def compute_priority(payload: dict[str, Any]) -> dict[str, Any]:
    return adv.auto_priority(
        intent=str(payload.get("intent") or ""),
        sentiment=str(payload.get("sentiment") or "neutral"),
        message=str(payload.get("message") or ""),
    )


@router.post("/sla/register")
async def sla_register(payload: dict[str, Any]) -> dict[str, Any]:
    return adv.register_sla(
        str(payload.get("ticket_number") or "TKT-UNKNOWN"),
        priority=str(payload.get("priority") or "P2"),
    )


@router.get("/sla")
async def sla_monitor(ticket_number: str | None = None) -> dict[str, Any]:
    return {"items": adv.sla_status(ticket_number)}


@router.get("/sentiment/dashboard")
async def sentiment_dash(hours: int = Query(default=24, ge=1, le=168)) -> dict[str, Any]:
    return adv.sentiment_dashboard(hours=hours)


@router.post("/csat/predict")
async def csat_predict(payload: dict[str, Any]) -> dict[str, Any]:
    return adv.predict_csat(
        sentiment=str(payload.get("sentiment") or "neutral"),
        handoff=bool(payload.get("handoff")),
        resolved=bool(payload.get("resolved")),
        response_seconds=payload.get("response_seconds"),
    )


@router.get("/analytics/agents")
async def agent_analytics() -> dict[str, Any]:
    return adv.agent_performance_analytics()


@router.post("/qa/score")
async def qa_score(payload: dict[str, Any]) -> dict[str, Any]:
    return await adv.quality_assurance_score(
        reply=str(payload.get("reply") or ""),
        user_message=str(payload.get("user_message") or ""),
        citations=payload.get("citations"),
        handoff_required=bool(payload.get("handoff_required")),
    )


@router.post("/fraud/refund")
async def fraud_refund(payload: dict[str, Any]) -> dict[str, Any]:
    return adv.detect_refund_fraud(
        message=str(payload.get("message") or ""),
        order_age_days=payload.get("order_age_days"),
        prior_refunds=int(payload.get("prior_refunds") or 0),
    )


@router.post("/voice/stt")
async def voice_stt(payload: dict[str, Any]) -> dict[str, Any]:
    return await adv.voice_to_text(
        audio_b64=payload.get("audio_b64"),
        transcript_hint=payload.get("transcript_hint") or payload.get("text"),
        language=str(payload.get("language") or "en"),
    )


@router.post("/voice/tts")
async def voice_tts(payload: dict[str, Any]) -> dict[str, Any]:
    return await adv.speech_synthesis(
        text=str(payload.get("text") or ""),
        voice=payload.get("voice"),
        language=str(payload.get("language") or "en"),
    )


@router.get("/languages")
async def languages() -> dict[str, Any]:
    return adv.list_languages()


@router.post("/faq/generate")
async def faq_generate(payload: dict[str, Any]) -> dict[str, Any]:
    return await adv.generate_faqs(
        topic=str(payload.get("topic") or "support"),
        source_text=payload.get("source_text"),
        count=int(payload.get("count") or 5),
    )


@router.post("/knowledge/continuous-ingest")
async def continuous_ingest(payload: dict[str, Any]) -> dict[str, Any]:
    return await adv.continuous_ingest_path(
        title=str(payload.get("title") or "Untitled"),
        content=str(payload.get("content") or ""),
        source=str(payload.get("source") or "continuous"),
        knowledge_source=payload.get("knowledge_source"),
    )


@router.get("/knowledge/ingest-jobs")
async def ingest_jobs() -> dict[str, Any]:
    return {"jobs": adv.ingest_job_history()}


@router.post("/notifications/publish")
async def notify_publish(payload: dict[str, Any]) -> dict[str, Any]:
    return adv.publish_realtime(
        str(payload.get("event") or "update"),
        dict(payload.get("payload") or payload),
        channel=str(payload.get("channel") or "support"),
    )


@router.get("/notifications/poll")
async def notify_poll(
    channel: str = "support",
    after_ts: str | None = None,
) -> dict[str, Any]:
    return {"events": adv.notification_bus.poll(channel, after_ts=after_ts)}


@router.get("/notifications/stream")
async def notify_stream(channel: str = "support") -> StreamingResponse:
    """Server-Sent Events stream for real-time notifications."""

    async def event_generator():
        last_ts = None
        for _ in range(120):  # ~2 minutes of polling for demo clients
            events = adv.notification_bus.poll(channel, after_ts=last_ts)
            for ev in events:
                last_ts = ev.get("ts")
                yield f"data: {json.dumps(ev)}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/prompts/optimization")
async def prompts_optimization() -> dict[str, Any]:
    return adv.prompt_optimization_status()
