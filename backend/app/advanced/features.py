"""Advanced platform features — summaries, SLA, analytics, fraud, voice, QA, etc."""

from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.logging import get_logger
from app.llm.base import LLMMessage, StubLLMAdapter, get_llm_adapter
from app.memory.conversation import ensure_memory
from app.prompts.registry import prompt_optimizer
from app.rag.pipeline import rag_pipeline
from app.rag.sources import infer_knowledge_source

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Auto-priority P1 / P2 / P3
# ---------------------------------------------------------------------------

PRIORITY_MAP = {
    "P1": {"label": "P1 — Critical", "sla_minutes": 60, "db": "urgent"},
    "P2": {"label": "P2 — High", "sla_minutes": 240, "db": "high"},
    "P3": {"label": "P3 — Normal", "sla_minutes": 1440, "db": "medium"},
}


def auto_priority(
    *,
    intent: str = "",
    sentiment: str = "neutral",
    message: str = "",
) -> dict[str, Any]:
    """Assign P1/P2/P3 from intent, sentiment, and risk keywords."""
    lower = message.lower()
    score = 0
    if sentiment in {"urgent", "angry"}:
        score += 3
    elif sentiment == "frustrated":
        score += 2
    if intent in {"package_delay", "shipping", "refund", "billing", "escalation"}:
        score += 2
    if intent in {"complaint", "warranty", "technical"}:
        score += 1
    if any(w in lower for w in ("lawsuit", "attorney", "fraud", "chargeback", "asap", "immediately")):
        score += 3
    if any(w in lower for w in ("broken", "not working", "double charged")):
        score += 1

    if score >= 5:
        level = "P1"
    elif score >= 2:
        level = "P2"
    else:
        level = "P3"
    meta = PRIORITY_MAP[level]
    return {
        "priority": level,
        "label": meta["label"],
        "sla_minutes": meta["sla_minutes"],
        "db_priority": meta["db"],
        "score": score,
    }


# ---------------------------------------------------------------------------
# AI ticket + conversation summarization
# ---------------------------------------------------------------------------


async def summarize_ticket(
    *,
    subject: str,
    description: str,
    intent: str | None = None,
    sentiment: str | None = None,
) -> dict[str, Any]:
    llm = get_llm_adapter()
    prompt = (
        "Summarize this support ticket in 2 short sentences for an agent. "
        "Include likely intent and urgency.\n\n"
        f"Subject: {subject}\nDescription: {description}\n"
        f"Intent: {intent}\nSentiment: {sentiment}"
    )
    if isinstance(llm, StubLLMAdapter):
        summary = (
            f"Customer issue: {subject[:120]}. "
            f"Intent appears to be {intent or 'general'} "
            f"with {sentiment or 'neutral'} sentiment."
        )
        llm_used = False
    else:
        resp = await llm.complete([LLMMessage(role="user", content=prompt)])
        summary = resp.content
        llm_used = True
    return {"summary": summary, "llm_used": llm_used, "type": "ticket_summary"}


async def summarize_conversation(
    turns: list[dict[str, Any]] | None = None,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    if turns is None and session_id:
        memory = await ensure_memory()
        turns = await memory.get_history(session_id, limit=20)
    turns = turns or []
    blob = "\n".join(
        f"{t.get('role', 'user')}: {str(t.get('content') or '')[:200]}" for t in turns[-12:]
    )
    if not blob:
        return {"summary": "No conversation turns yet.", "llm_used": False}

    llm = get_llm_adapter()
    if isinstance(llm, StubLLMAdapter):
        summary = f"Conversation ({len(turns)} turns). Latest topics covered in recent messages."
        if turns:
            summary += f" Last: {str(turns[-1].get('content') or '')[:160]}"
        llm_used = False
    else:
        resp = await llm.complete(
            [
                LLMMessage(
                    role="user",
                    content="Summarize this customer support conversation for handoff:\n" + blob,
                )
            ]
        )
        summary = resp.content
        llm_used = True
    return {
        "summary": summary,
        "turn_count": len(turns),
        "llm_used": llm_used,
        "type": "conversation_summary",
    }


# ---------------------------------------------------------------------------
# SLA monitoring
# ---------------------------------------------------------------------------

_sla_store: dict[str, dict[str, Any]] = {}


def register_sla(
    ticket_number: str,
    *,
    priority: str = "P2",
    created_at: datetime | None = None,
) -> dict[str, Any]:
    created = created_at or datetime.now(UTC)
    mins = PRIORITY_MAP.get(priority, PRIORITY_MAP["P2"])["sla_minutes"]
    due = created + timedelta(minutes=mins)
    row = {
        "ticket_number": ticket_number,
        "priority": priority,
        "created_at": created.isoformat(),
        "due_at": due.isoformat(),
        "sla_minutes": mins,
        "status": "open",
    }
    _sla_store[ticket_number] = row
    return row


def sla_status(ticket_number: str | None = None) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    rows = list(_sla_store.values()) if not ticket_number else (
        [_sla_store[ticket_number]] if ticket_number in _sla_store else []
    )
    out = []
    for row in rows:
        due = datetime.fromisoformat(row["due_at"])
        remaining = (due - now).total_seconds() / 60
        breached = remaining < 0 and row.get("status") == "open"
        out.append(
            {
                **row,
                "remaining_minutes": round(remaining, 1),
                "breached": breached,
                "state": "breached" if breached else ("at_risk" if remaining < 30 else "ok"),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Sentiment dashboard + CSAT prediction
# ---------------------------------------------------------------------------

_sentiment_events: list[dict[str, Any]] = []


def record_sentiment_event(
    *,
    session_id: str,
    sentiment: str,
    intent: str | None = None,
    customer_id: str | None = None,
) -> None:
    _sentiment_events.append(
        {
            "ts": datetime.now(UTC).isoformat(),
            "session_id": session_id,
            "sentiment": sentiment,
            "intent": intent,
            "customer_id": customer_id,
        }
    )
    if len(_sentiment_events) > 5000:
        del _sentiment_events[:-2000]


def sentiment_dashboard(*, hours: int = 24) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    counts: dict[str, int] = defaultdict(int)
    recent = []
    for ev in _sentiment_events:
        ts = datetime.fromisoformat(ev["ts"])
        if ts >= cutoff:
            counts[ev["sentiment"]] += 1
            recent.append(ev)
    total = sum(counts.values()) or 1
    return {
        "window_hours": hours,
        "total": sum(counts.values()),
        "distribution": dict(counts),
        "percentages": {k: round(100 * v / total, 1) for k, v in counts.items()},
        "recent": recent[-20:],
    }


def predict_csat(
    *,
    sentiment: str = "neutral",
    handoff: bool = False,
    resolved: bool = False,
    response_seconds: float | None = None,
) -> dict[str, Any]:
    """Lightweight CSAT prediction (1–5)."""
    score = 3.5
    score += {
        "happy": 1.2,
        "neutral": 0.2,
        "frustrated": -0.8,
        "angry": -1.5,
        "urgent": -0.6,
        "negative": -1.0,
        "positive": 1.0,
    }.get(sentiment, 0)
    if handoff:
        score -= 0.3
    if resolved:
        score += 0.8
    if response_seconds is not None:
        if response_seconds < 5:
            score += 0.3
        elif response_seconds > 30:
            score -= 0.4
    score = max(1.0, min(5.0, score))
    return {
        "predicted_csat": round(score, 2),
        "band": "high" if score >= 4 else ("medium" if score >= 3 else "low"),
        "drivers": {
            "sentiment": sentiment,
            "handoff": handoff,
            "resolved": resolved,
            "response_seconds": response_seconds,
        },
    }


# ---------------------------------------------------------------------------
# Agent performance analytics + AI QA
# ---------------------------------------------------------------------------

_agent_metrics: dict[str, dict[str, float]] = defaultdict(
    lambda: {"invocations": 0, "success": 0, "errors": 0, "latency_ms_sum": 0.0}
)


def record_agent_metric(agent: str, *, success: bool, latency_ms: float) -> None:
    m = _agent_metrics[agent]
    m["invocations"] += 1
    m["success" if success else "errors"] += 1
    m["latency_ms_sum"] += latency_ms


def agent_performance_analytics() -> dict[str, Any]:
    agents = {}
    for name, m in _agent_metrics.items():
        inv = m["invocations"] or 1
        agents[name] = {
            "invocations": int(m["invocations"]),
            "success_rate": round(m["success"] / inv, 3),
            "error_rate": round(m["errors"] / inv, 3),
            "avg_latency_ms": round(m["latency_ms_sum"] / inv, 1),
        }
    return {"agents": agents, "prompt_optimization": {
        "best_variant": prompt_optimizer.best_variant(["master_system", "master_system_b"]),
        "scores": prompt_optimizer.scores,
    }}


async def quality_assurance_score(
    *,
    reply: str,
    user_message: str,
    citations: list[dict[str, Any]] | None = None,
    handoff_required: bool = False,
) -> dict[str, Any]:
    """AI-powered QA checklist for a support reply."""
    checks = {
        "non_empty": bool(reply and reply.strip()),
        "has_summary": "summary:" in reply.lower(),
        "has_next_action": "next best action" in reply.lower(),
        "grounded": bool(citations) or "knowledge" in reply.lower() or "policy" in reply.lower(),
        "polite": not any(w in reply.lower() for w in ("stupid", "idiot", "shut up")),
        "no_hallucinated_order": not (
            re.search(r"ORD-\d+", reply) and not re.search(r"ORD-\d+", user_message)
            and "ord-" not in user_message.lower()
        ),
    }
    score = round(100 * sum(1 for v in checks.values() if v) / len(checks), 1)
    return {
        "qa_score": score,
        "pass": score >= 70,
        "checks": checks,
        "handoff_required": handoff_required,
        "type": "ai_quality_assurance",
    }


# ---------------------------------------------------------------------------
# Fraud detection for refunds
# ---------------------------------------------------------------------------

_FRAUD_PATTERNS = [
    (r"\b(chargeback|dispute with bank)\b", 0.35, "chargeback_language"),
    (r"\b(never received|didn't get|did not get).{0,40}(refund|already)\b", 0.25, "repeat_claim"),
    (r"\b(gift card|crypto|wire transfer)\b", 0.3, "payout_channel_risk"),
    (r"\b(urgent refund|immediately refund|right now)\b", 0.15, "urgency_pressure"),
    (r"\b(different (card|account)|send to)\b", 0.25, "destination_change"),
]


def detect_refund_fraud(
    *,
    message: str,
    order_age_days: int | None = None,
    prior_refunds: int = 0,
) -> dict[str, Any]:
    score = 0.0
    signals: list[str] = []
    lower = message.lower()
    for pattern, weight, label in _FRAUD_PATTERNS:
        if re.search(pattern, lower, re.I):
            score += weight
            signals.append(label)
    if order_age_days is not None and order_age_days > 45:
        score += 0.2
        signals.append("outside_typical_window")
    if prior_refunds >= 3:
        score += 0.25
        signals.append("high_refund_frequency")
    score = min(1.0, score)
    risk = "high" if score >= 0.6 else ("medium" if score >= 0.3 else "low")
    return {
        "fraud_score": round(score, 2),
        "risk": risk,
        "signals": signals,
        "recommend_manual_review": risk in {"medium", "high"},
        "type": "refund_fraud_detection",
    }


# ---------------------------------------------------------------------------
# Voice STT / TTS
# ---------------------------------------------------------------------------


async def voice_to_text(
    *,
    audio_b64: str | None = None,
    transcript_hint: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Voice-to-text — uses hint offline; hooks to provider when configured."""
    if transcript_hint:
        return {
            "text": transcript_hint,
            "language": language,
            "provider": "client_hint",
            "type": "voice_to_text",
        }
    if not audio_b64:
        return {"text": "", "error": "audio_b64 or transcript_hint required", "type": "voice_to_text"}
    # Placeholder for Whisper / cloud STT
    digest = hashlib.sha1(audio_b64[:200].encode()).hexdigest()[:8]
    return {
        "text": f"[stt pending — audio received ref={digest}]",
        "language": language,
        "provider": "stub",
        "type": "voice_to_text",
    }


async def speech_synthesis(
    *,
    text: str,
    voice: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.integrations.hub import integration_hub
    from app.channels.base import Channel, ChannelReply

    settings = get_settings()
    voice = voice or settings.voice_default_voice
    reply = ChannelReply(
        text=text,
        channel=Channel.VOICE,
        session_id="tts",
        language=language,
        metadata={"voice": voice},
    )
    outbound = await integration_hub.send_voice_tts(reply)
    return {
        "text": text,
        "voice": voice,
        "language": language,
        "outbound": outbound,
        "audio_url": None,
        "type": "speech_synthesis",
    }


# ---------------------------------------------------------------------------
# Multilingual (50+ languages)
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": c, "name": n}
    for c, n in [
        ("en", "English"), ("es", "Spanish"), ("fr", "French"), ("de", "German"),
        ("it", "Italian"), ("pt", "Portuguese"), ("nl", "Dutch"), ("pl", "Polish"),
        ("ru", "Russian"), ("uk", "Ukrainian"), ("cs", "Czech"), ("sk", "Slovak"),
        ("ro", "Romanian"), ("hu", "Hungarian"), ("bg", "Bulgarian"), ("el", "Greek"),
        ("sv", "Swedish"), ("no", "Norwegian"), ("da", "Danish"), ("fi", "Finnish"),
        ("tr", "Turkish"), ("ar", "Arabic"), ("he", "Hebrew"), ("fa", "Persian"),
        ("hi", "Hindi"), ("bn", "Bengali"), ("ur", "Urdu"), ("ta", "Tamil"),
        ("te", "Telugu"), ("mr", "Marathi"), ("gu", "Gujarati"), ("kn", "Kannada"),
        ("ml", "Malayalam"), ("pa", "Punjabi"), ("th", "Thai"), ("vi", "Vietnamese"),
        ("id", "Indonesian"), ("ms", "Malay"), ("fil", "Filipino"), ("zh", "Chinese"),
        ("zh-tw", "Chinese Traditional"), ("ja", "Japanese"), ("ko", "Korean"),
        ("sw", "Swahili"), ("af", "Afrikaans"), ("zu", "Zulu"), ("am", "Amharic"),
        ("ha", "Hausa"), ("yo", "Yoruba"), ("ig", "Igbo"), ("ca", "Catalan"),
        ("eu", "Basque"), ("gl", "Galician"), ("sr", "Serbian"), ("hr", "Croatian"),
        ("bs", "Bosnian"), ("sl", "Slovenian"), ("lt", "Lithuanian"), ("lv", "Latvian"),
        ("et", "Estonian"),
    ]
]


def list_languages() -> dict[str, Any]:
    return {"count": len(SUPPORTED_LANGUAGES), "languages": SUPPORTED_LANGUAGES}


# ---------------------------------------------------------------------------
# AI FAQ generation + continuous KB ingestion
# ---------------------------------------------------------------------------


async def generate_faqs(
    *,
    topic: str,
    source_text: str | None = None,
    count: int = 5,
) -> dict[str, Any]:
    llm = get_llm_adapter()
    context = source_text or topic
    if isinstance(llm, StubLLMAdapter):
        faqs = [
            {
                "q": f"What should I know about {topic}?",
                "a": f"Based on our knowledge: {(context[:180] or topic)}",
            }
            for _ in range(min(count, 3))
        ]
        llm_used = False
    else:
        resp = await llm.complete(
            [
                LLMMessage(
                    role="user",
                    content=(
                        f"Generate {count} concise FAQ Q&A pairs about '{topic}' "
                        f"from this context:\n{context[:3000]}\n"
                        "Return plain Q:/A: lines."
                    ),
                )
            ]
        )
        faqs = [{"raw": resp.content}]
        llm_used = True
    return {"topic": topic, "faqs": faqs, "llm_used": llm_used, "type": "faq_generation"}


_ingest_jobs: list[dict[str, Any]] = []


async def continuous_ingest_path(
    *,
    title: str,
    content: str,
    source: str,
    knowledge_source: str | None = None,
) -> dict[str, Any]:
    """Continuous knowledge-base ingestion job step."""
    result = await rag_pipeline.ingest_text(
        title=title,
        content=content,
        source=source,
        knowledge_source=knowledge_source
        or infer_knowledge_source(filename=source),
    )
    job = {
        "ts": datetime.now(UTC).isoformat(),
        "title": title,
        "source": source,
        "document_id": result.get("document_id"),
        "chunks_created": result.get("chunks_created"),
        "status": result.get("status"),
        "knowledge_source": result.get("knowledge_source"),
    }
    _ingest_jobs.append(job)
    return {"job": job, "recent_jobs": _ingest_jobs[-10:], "type": "continuous_ingestion"}


def ingest_job_history() -> list[dict[str, Any]]:
    return list(_ingest_jobs[-50:])


# ---------------------------------------------------------------------------
# Real-time notifications (in-memory fan-out for SSE)
# ---------------------------------------------------------------------------

@dataclass
class NotificationBus:
    subscribers: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))

    def publish(self, channel: str, event: dict[str, Any]) -> dict[str, Any]:
        payload = {**event, "ts": datetime.now(UTC).isoformat(), "channel": channel}
        self.subscribers[channel].append(payload)
        # cap buffer
        if len(self.subscribers[channel]) > 200:
            self.subscribers[channel] = self.subscribers[channel][-100:]
        return payload

    def poll(self, channel: str, *, after_ts: str | None = None) -> list[dict[str, Any]]:
        events = self.subscribers.get(channel, [])
        if not after_ts:
            return events[-20:]
        return [e for e in events if e.get("ts", "") > after_ts]


notification_bus = NotificationBus()


def publish_realtime(event_type: str, payload: dict[str, Any], *, channel: str = "support") -> dict[str, Any]:
    return notification_bus.publish(channel, {"event": event_type, "payload": payload})


# ---------------------------------------------------------------------------
# Feedback-driven prompt optimization (facade)
# ---------------------------------------------------------------------------


def prompt_optimization_status() -> dict[str, Any]:
    candidates = ["master_system", "master_system_b"]
    return {
        "best_variant": prompt_optimizer.best_variant(candidates),
        "suggested_weights": prompt_optimizer.suggest_weights(candidates),
        "scores": prompt_optimizer.scores,
        "type": "feedback_driven_prompt_optimization",
    }
