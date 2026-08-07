"""Master Agent — LangGraph orchestrator for the agentic support workflow.

Customer Question
        │
   Master Agent
        │
  Intent Detection
        │
   Need Knowledge? ──Yes──► RAG Search → GraphRAG → Vector Search
        │
  Customer History
        │
   Need Order? ──Yes──► Order Agent
        │
   Need Ticket? ──Yes──► Ticket Agent
        │
   Need Human? ──Yes──► Escalation Agent
        │
   Final Response
"""

from __future__ import annotations

import time
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.agents.email.agent import EmailAgent
from app.agents.graph_rag.agent import GraphRAGAgent
from app.agents.handoff.agent import HumanHandoffAgent
from app.agents.intent.agent import IntentClassificationAgent
from app.agents.knowledge.agent import KnowledgeAgent
from app.agents.order.agent import OrderManagementAgent
from app.agents.recommendation.agent import RecommendationAgent
from app.agents.refund.agent import RefundAgent
from app.agents.sentiment.agent import SentimentAnalysisAgent
from app.agents.shared.base import AgentState, BaseAgent
from app.agents.synthesizer.agent import ResponseSynthesizerAgent
from app.advanced.features import (
    publish_realtime,
    record_agent_metric,
    record_sentiment_event,
)
from app.agents.ticket.agent import TicketManagementAgent
from app.agents.workflows.package_delay import PackageDelayWorkflow
from app.channels.base import Channel, ChannelReply
from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.hub import integration_hub
from app.memory.conversation import ensure_memory
from app.observability.metrics import AGENT_DURATION, AGENT_INVOCATIONS_TOTAL

logger = get_logger(__name__)

KNOWLEDGE_INTENTS = {
    "knowledge",
    "product",
    "technical",
    "warranty",
    "general",
    "graph_rag",
}
ORDER_INTENTS = {
    "order_status",
    "shipping",
    "package_delay",
    "refund",
}
TICKET_INTENTS = {
    "ticket",
    "complaint",
    "billing",
    "account",
}


async def _run_agent(agent: BaseAgent, state: AgentState) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        update = await agent(state)
        latency_ms = (time.perf_counter() - start) * 1000
        AGENT_INVOCATIONS_TOTAL.labels(
            agent_name=agent.name.value, status="success"
        ).inc()
        AGENT_DURATION.labels(agent_name=agent.name.value).observe(
            time.perf_counter() - start
        )
        record_agent_metric(agent.name.value, success=True, latency_ms=latency_ms)
        return update
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        AGENT_INVOCATIONS_TOTAL.labels(
            agent_name=agent.name.value, status="error"
        ).inc()
        record_agent_metric(agent.name.value, success=False, latency_ms=latency_ms)
        logger.exception("agent_failed", agent=agent.name.value, error=str(exc))
        agents_used = list(state.get("agents_used") or [])
        agents_used.append(agent.name.value)
        return {
            "agents_used": agents_used,
            "agent_results": {
                **(state.get("agent_results") or {}),
                agent.name.value: {
                    "agent_name": agent.name.value,
                    "success": False,
                    "content": str(exc),
                    "confidence": 0.0,
                    "data": {},
                    "citations": [],
                    "error": str(exc),
                },
            },
        }


async def _merge(*updates: dict[str, Any], base: AgentState | None = None) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base or {})
    agents: list[str] = list(merged.get("agents_used") or [])
    results: dict[str, Any] = dict(merged.get("agent_results") or {})
    citations: list[Any] = list(merged.get("citations") or [])
    for update in updates:
        for key, value in update.items():
            if key == "agents_used":
                agents = list(dict.fromkeys(agents + list(value or [])))
            elif key == "agent_results":
                results = {**results, **(value or {})}
            elif key == "citations":
                citations = citations + list(value or [])
            elif key == "metadata":
                merged["metadata"] = {**(merged.get("metadata") or {}), **(value or {})}
            else:
                merged[key] = value
    merged["agents_used"] = agents
    merged["agent_results"] = results
    if citations:
        merged["citations"] = citations
    return merged


# ---------------------------------------------------------------------------
# Decision gates (Need Knowledge? / Order? / Ticket? / Human?)
# ---------------------------------------------------------------------------


def needs_knowledge(state: AgentState) -> bool:
    intent = state.get("intent") or "general"
    if intent in ORDER_INTENTS | TICKET_INTENTS | {"escalation", "recommendation", "email"}:
        msg = (state.get("user_message") or "").lower()
        if any(w in msg for w in ("policy", "how do i", "faq", "warranty", "guide")):
            return True
        return False
    return intent in KNOWLEDGE_INTENTS or intent not in (
        ORDER_INTENTS | TICKET_INTENTS | {"escalation", "recommendation", "email"}
    )


def needs_order(state: AgentState) -> bool:
    intent = state.get("intent") or ""
    if intent in ORDER_INTENTS:
        return True
    msg = (state.get("user_message") or "").lower()
    return any(w in msg for w in ("ord-", "order", "tracking", "shipment", "delivery"))


def needs_ticket(state: AgentState) -> bool:
    # Skip if a prior stage (e.g. package-delay playbook) already opened one
    results = state.get("agent_results") or {}
    if results.get("ticket"):
        return False
    pkg = results.get("package_delay") or {}
    if (pkg.get("data") or {}).get("ticket"):
        return False

    intent = state.get("intent") or ""
    if intent in TICKET_INTENTS | {"escalation"}:
        return True
    sentiment = state.get("sentiment") or ""
    if sentiment in {"angry", "frustrated", "urgent"}:
        return True
    msg = (state.get("user_message") or "").lower()
    return any(w in msg for w in ("ticket", "complaint", "open a case", "file a"))


def needs_human(state: AgentState) -> bool:
    settings = get_settings()
    intent = state.get("intent") or ""
    sentiment = state.get("sentiment") or ""
    confidence = float(state.get("confidence") or 0.0)
    meta = state.get("metadata") or {}
    pkg = (state.get("agent_results") or {}).get("package_delay") or {}
    pkg_data = pkg.get("data") or {}

    if intent == "escalation":
        return True
    if state.get("handoff_required") or meta.get("force_handoff") or pkg_data.get("escalate"):
        return True
    if confidence and confidence < settings.handoff_confidence_threshold:
        results = state.get("agent_results") or {}
        has_answer = any(
            bool((results.get(k) or {}).get("content"))
            for k in (
                "knowledge",
                "graph_rag",
                "order",
                "refund",
                "ticket",
                "package_delay",
                "recommendation",
            )
        )
        if not has_answer:
            return True
    if sentiment in {"angry", "urgent"}:
        return True
    # Frustrated alone does not force human if we already have a solid specialist answer
    if sentiment == "frustrated":
        results = state.get("agent_results") or {}
        if not any(
            bool((results.get(k) or {}).get("content"))
            for k in ("knowledge", "order", "refund", "package_delay", "ticket")
        ):
            return True
    msg = (state.get("user_message") or "").lower()
    return any(w in msg for w in ("human", "manager", "representative", "lawyer", "lawsuit"))


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def intent_node(state: AgentState) -> dict[str, Any]:
    """Intent Detection."""
    update = await _run_agent(IntentClassificationAgent(), state)
    result = update["agent_results"]["intent"]
    update["intent"] = (result.get("data") or {}).get("intent", "general")
    update["confidence"] = float((result.get("data") or {}).get("confidence") or 0.0)
    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.append("intent_detection")
    meta["workflow_path"] = path
    meta["primary_label"] = (result.get("data") or {}).get("primary_label")
    update["metadata"] = meta
    return update


async def sentiment_node(state: AgentState) -> dict[str, Any]:
    update = await _run_agent(SentimentAnalysisAgent(), state)
    result = update["agent_results"]["sentiment"]
    data = result.get("data") or {}
    sentiment = data.get("sentiment") or result.get("content") or "neutral"
    update["sentiment"] = sentiment
    meta = dict(state.get("metadata") or {})
    meta["sentiment_polarity"] = data.get("polarity")
    meta["sentiment_urgent"] = data.get("urgent")
    update["metadata"] = meta
    record_sentiment_event(
        session_id=str(state.get("session_id") or "unknown"),
        sentiment=str(sentiment),
        intent=state.get("intent"),
        customer_id=state.get("customer_id"),
    )
    publish_realtime(
        "sentiment.updated",
        {
            "session_id": state.get("session_id"),
            "sentiment": sentiment,
            "polarity": data.get("polarity"),
        },
    )
    return update


async def knowledge_pipeline_node(state: AgentState) -> dict[str, Any]:
    """Need Knowledge? Yes → RAG Search → GraphRAG → Vector Search."""
    know = await _run_agent(KnowledgeAgent(), state)
    citations = list(know.get("citations") or [])
    if know.get("agent_results", {}).get("knowledge", {}).get("citations"):
        citations = know["agent_results"]["knowledge"]["citations"]

    interim = {**state, **know, "citations": citations}
    graph = await _run_agent(GraphRAGAgent(), interim)

    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.extend(["need_knowledge:yes", "rag_search", "graphrag", "vector_search"])
    meta["workflow_path"] = path
    meta["need_knowledge"] = True

    merged = await _merge(know, graph, base=state)
    merged["citations"] = citations
    merged["metadata"] = meta
    return merged


async def skip_knowledge_node(state: AgentState) -> dict[str, Any]:
    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.append("need_knowledge:no")
    meta["workflow_path"] = path
    meta["need_knowledge"] = False
    return {"metadata": meta}


async def customer_history_node(state: AgentState) -> dict[str, Any]:
    """Load conversation + customer profile / purchases / tickets / preferences."""
    memory = await ensure_memory()
    session_id = state.get("session_id") or ""
    customer_id = state.get("customer_id")

    await memory.add_turn(
        session_id,
        role="user",
        content=state.get("user_message") or "",
        metadata={"intent": state.get("intent")},
    )

    bundle = await memory.get_customer_memory_bundle(
        customer_id=customer_id, session_id=session_id
    )
    if customer_id:
        await memory.update_profile(
            customer_id,
            {
                "last_intent": state.get("intent"),
                "last_sentiment": state.get("sentiment"),
            },
        )
        bundle["customer_profile"] = await memory.get_profile(customer_id)

    memory_block = memory.format_memory_block(bundle)
    meta = dict(state.get("metadata") or {})
    meta["conversation_history"] = bundle.get("conversation_memory") or []
    meta["conversation_summary"] = bundle.get("conversation_summary")
    meta["profile"] = bundle.get("customer_profile") or {}
    meta["purchase_history"] = bundle.get("purchase_history") or []
    meta["previous_tickets"] = bundle.get("previous_tickets") or []
    meta["preferences"] = bundle.get("preferences") or {}
    meta["long_term_memory"] = bundle.get("long_term_memory") or []
    meta["memory_block"] = memory_block
    path = list(meta.get("workflow_path") or [])
    path.append("customer_history")
    meta["workflow_path"] = path
    return {
        "metadata": meta,
        "agents_used": list(state.get("agents_used") or []) + ["memory", "customer_history"],
    }


async def order_node(state: AgentState) -> dict[str, Any]:
    update = await _run_agent(OrderManagementAgent(), state)
    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.extend(["need_order:yes", "order_agent"])
    meta["workflow_path"] = path
    meta["need_order"] = True
    update["metadata"] = meta
    return update


async def package_delay_node(state: AgentState) -> dict[str, Any]:
    """Order-path playbook for delayed packages (may draft ticket + email)."""
    update = await _run_agent(PackageDelayWorkflow(), state)
    result = (update.get("agent_results") or {}).get("order", {})
    data = result.get("data") or {}

    ticket_state = {**state, **update}
    if data.get("ticket"):
        ticket_state["user_message"] = (
            f"{state.get('user_message')}\n\n"
            f"[Auto ticket] {data['ticket'].get('subject')} "
            f"({data['ticket'].get('ticket_number')})"
        )
    ticket_update = await _run_agent(TicketManagementAgent(), ticket_state)
    email_update = await _run_agent(EmailAgent(), {**ticket_state, **ticket_update})

    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.extend(["need_order:yes", "order_agent", "package_delay"])
    meta["workflow_path"] = path
    meta["need_order"] = True
    if data.get("escalate"):
        update["handoff_required"] = True
        meta["force_handoff"] = True
        meta["escalate_reasons"] = data.get("escalate_reasons") or []
        meta["package_delay_ticket"] = data.get("ticket")
        meta["refund_offer"] = {
            "offer_refund": data.get("offer_refund"),
            "refund_id": data.get("refund_id"),
        }

    merged = await _merge(update, ticket_update, email_update, base=state)
    merged["agents_used"] = list(
        dict.fromkeys(
            list(merged.get("agents_used") or []) + ["package_delay_workflow"]
        )
    )
    merged["agent_results"] = {
        **(merged.get("agent_results") or {}),
        "package_delay": result,
    }
    merged["metadata"] = meta
    if data.get("escalate"):
        merged["handoff_required"] = True
    return merged


async def refund_node(state: AgentState) -> dict[str, Any]:
    update = await _run_agent(RefundAgent(), state)
    email_update = await _run_agent(EmailAgent(), {**state, **update})
    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.extend(["need_order:yes", "order_agent", "refund"])
    meta["workflow_path"] = path
    meta["need_order"] = True
    merged = await _merge(update, email_update, base=state)
    merged["metadata"] = meta
    return merged


async def recommendation_node(state: AgentState) -> dict[str, Any]:
    update = await _run_agent(RecommendationAgent(), state)
    result = update["agent_results"].get("recommendation", {})
    recs = (result.get("data") or {}).get("recommendations") or []
    update["recommendations"] = list(recs)
    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.append("recommendation_agent")
    meta["workflow_path"] = path
    update["metadata"] = meta
    return update


async def email_node(state: AgentState) -> dict[str, Any]:
    update = await _run_agent(EmailAgent(), state)
    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.append("email_agent")
    meta["workflow_path"] = path
    update["metadata"] = meta
    return update


async def skip_order_node(state: AgentState) -> dict[str, Any]:
    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.append("need_order:no")
    meta["workflow_path"] = path
    meta["need_order"] = False
    return {"metadata": meta}


async def ticket_node(state: AgentState) -> dict[str, Any]:
    update = await _run_agent(TicketManagementAgent(), state)
    email_update = await _run_agent(EmailAgent(), {**state, **update})
    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.extend(["need_ticket:yes", "ticket_agent"])
    meta["workflow_path"] = path
    meta["need_ticket"] = True

    # Persist ticket into customer memory (Previous Tickets)
    customer_id = state.get("customer_id")
    draft = (
        ((update.get("agent_results") or {}).get("ticket") or {})
        .get("data", {})
        .get("ticket_draft")
    )
    if customer_id and draft:
        memory = await ensure_memory()
        await memory.remember_ticket(customer_id, draft)
        tickets = await memory.get_previous_tickets(customer_id)
        meta["previous_tickets"] = tickets

    merged = await _merge(update, email_update, base=state)
    merged["metadata"] = meta
    return merged


async def skip_ticket_node(state: AgentState) -> dict[str, Any]:
    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.append("need_ticket:no")
    meta["workflow_path"] = path
    meta["need_ticket"] = False
    return {"metadata": meta}


async def escalation_node(state: AgentState) -> dict[str, Any]:
    """Need Human? Yes → Escalation / Human Handoff Agent."""
    meta = state.get("metadata") or {}
    pkg = (state.get("agent_results") or {}).get("package_delay") or {}
    pkg_data = pkg.get("data") or {}
    force = bool(
        meta.get("force_handoff")
        or pkg_data.get("escalate")
        or state.get("handoff_required")
    )

    update = await _run_agent(HumanHandoffAgent(), state)
    result = update["agent_results"]["handoff"]
    handoff = bool((result.get("data") or {}).get("handoff_required")) or force
    update["handoff_required"] = handoff

    path = list(meta.get("workflow_path") or [])
    path.extend(["need_human:yes", "escalation_agent"])
    meta = dict(meta)
    meta["workflow_path"] = path
    meta["need_human"] = True
    update["metadata"] = meta

    if handoff:
        reasons = list((result.get("data") or {}).get("reasons") or [])
        reasons.extend(meta.get("escalate_reasons") or pkg_data.get("escalate_reasons") or [])
        try:
            ch = Channel(meta.get("channel") or "web")
        except ValueError:
            ch = Channel.WEB
        reply = ChannelReply(
            text=result.get("content")
            or "Connecting you with a human support specialist.",
            channel=ch,
            session_id=state.get("session_id") or "",
            language=str(state.get("language") or meta.get("language") or "en"),
            handoff_required=True,
            intent=state.get("intent"),
            sentiment=state.get("sentiment"),
            metadata={"reasons": reasons, "workflow": pkg_data.get("workflow")},
        )
        try:
            await integration_hub.notify_slack(reply)
            await integration_hub.notify_teams(reply)
        except Exception:
            pass
        update["agent_results"]["handoff"]["data"]["reasons"] = reasons
        update["agent_results"]["handoff"]["data"]["handoff_required"] = True
    return update


async def skip_human_node(state: AgentState) -> dict[str, Any]:
    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.append("need_human:no")
    meta["workflow_path"] = path
    meta["need_human"] = False
    return {"metadata": meta, "handoff_required": False}


async def final_response_node(state: AgentState) -> dict[str, Any]:
    """Final Response — Response Synthesizer → LLM."""
    update = await _run_agent(ResponseSynthesizerAgent(), state)
    synth = (update.get("agent_results") or {}).get("synthesizer") or {}
    final = synth.get("content") or "I'm here to help."
    data = synth.get("data") or {}

    memory = await ensure_memory()
    await memory.add_turn(
        state.get("session_id") or "",
        role="assistant",
        content=final,
        metadata={
            "prompt_variant": data.get("prompt_variant"),
            "mode": data.get("mode"),
            "workflow": data.get("workflow"),
        },
    )

    meta = dict(state.get("metadata") or {})
    path = list(meta.get("workflow_path") or [])
    path.append("final_response")
    meta["workflow_path"] = path
    meta.update(
        {
            "prompt_variant": data.get("prompt_variant"),
            "synthesizer_mode": data.get("mode"),
            "llm_used": data.get("llm_used"),
        }
    )
    if data.get("workflow") == "package_delay":
        meta["workflow"] = "package_delay"
        meta["workflow_steps"] = data.get("steps")

    agents = list(
        dict.fromkeys(
            list(state.get("agents_used") or [])
            + list(update.get("agents_used") or [])
            + ["response_synthesizer"]
            + (["llm"] if data.get("llm_used") else [])
        )
    )
    return {
        "final_response": final,
        "metadata": meta,
        "agents_used": agents,
        "agent_results": {
            **(state.get("agent_results") or {}),
            **(update.get("agent_results") or {}),
        },
    }


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


def route_knowledge(state: AgentState) -> Literal["knowledge", "skip_knowledge"]:
    return "knowledge" if needs_knowledge(state) else "skip_knowledge"


def route_order(
    state: AgentState,
) -> Literal[
    "order",
    "package_delay",
    "refund",
    "recommendation",
    "email",
    "skip_order",
]:
    intent = state.get("intent") or ""
    if intent == "package_delay":
        return "package_delay"
    if intent == "refund":
        return "refund"
    if intent == "recommendation":
        return "recommendation"
    if intent == "email":
        return "email"
    if needs_order(state):
        return "order"
    return "skip_order"


def route_ticket(state: AgentState) -> Literal["ticket", "skip_ticket"]:
    return "ticket" if needs_ticket(state) else "skip_ticket"


def route_human(state: AgentState) -> Literal["escalation", "skip_human"]:
    return "escalation" if needs_human(state) else "skip_human"


def build_master_graph():
    """Compile the Master Agent decision-tree workflow."""
    graph = StateGraph(AgentState)

    graph.add_node("intent", intent_node)
    graph.add_node("sentiment", sentiment_node)
    graph.add_node("knowledge", knowledge_pipeline_node)
    graph.add_node("skip_knowledge", skip_knowledge_node)
    graph.add_node("customer_history", customer_history_node)
    graph.add_node("order", order_node)
    graph.add_node("package_delay", package_delay_node)
    graph.add_node("refund", refund_node)
    graph.add_node("recommendation", recommendation_node)
    graph.add_node("email", email_node)
    graph.add_node("skip_order", skip_order_node)
    graph.add_node("ticket", ticket_node)
    graph.add_node("skip_ticket", skip_ticket_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("skip_human", skip_human_node)
    graph.add_node("respond", final_response_node)

    # Customer Question → Master → Intent Detection → Sentiment
    graph.set_entry_point("intent")
    graph.add_edge("intent", "sentiment")

    # Need Knowledge?
    graph.add_conditional_edges(
        "sentiment",
        route_knowledge,
        {"knowledge": "knowledge", "skip_knowledge": "skip_knowledge"},
    )
    graph.add_edge("knowledge", "customer_history")
    graph.add_edge("skip_knowledge", "customer_history")

    # Customer History → Need Order?
    graph.add_conditional_edges(
        "customer_history",
        route_order,
        {
            "order": "order",
            "package_delay": "package_delay",
            "refund": "refund",
            "recommendation": "recommendation",
            "email": "email",
            "skip_order": "skip_order",
        },
    )
    for node in (
        "order",
        "package_delay",
        "refund",
        "recommendation",
        "email",
        "skip_order",
    ):
        graph.add_conditional_edges(
            node,
            route_ticket,
            {"ticket": "ticket", "skip_ticket": "skip_ticket"},
        )

    # Need Ticket? → Need Human?
    for node in ("ticket", "skip_ticket"):
        graph.add_conditional_edges(
            node,
            route_human,
            {"escalation": "escalation", "skip_human": "skip_human"},
        )

    # Escalation / skip → Final Response
    graph.add_edge("escalation", "respond")
    graph.add_edge("skip_human", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


class MasterAgent:
    """Facade around the compiled LangGraph master workflow."""

    def __init__(self) -> None:
        self.graph = build_master_graph()

    async def process(
        self,
        *,
        user_message: str,
        session_id: str,
        customer_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentState:
        initial: AgentState = {
            "messages": [{"role": "user", "content": user_message}],
            "session_id": session_id,
            "customer_id": customer_id,
            "user_message": user_message,
            "intent": "",
            "confidence": 0.0,
            "sentiment": "neutral",
            "agents_used": ["master"],
            "agent_results": {},
            "citations": [],
            "recommendations": [],
            "handoff_required": False,
            "final_response": "",
            "language": (metadata or {}).get("language") or "en",
            "metadata": {**(metadata or {}), "workflow_path": ["master_agent"]},
        }
        logger.info(
            "master_agent_start",
            session_id=session_id,
            message_preview=user_message[:80],
        )
        result = await self.graph.ainvoke(initial)
        publish_realtime(
            "chat.completed",
            {
                "session_id": session_id,
                "intent": result.get("intent"),
                "sentiment": result.get("sentiment"),
                "handoff": result.get("handoff_required"),
                "agents": result.get("agents_used"),
            },
        )
        logger.info(
            "master_agent_complete",
            session_id=session_id,
            intent=result.get("intent"),
            handoff=result.get("handoff_required"),
            agents=result.get("agents_used"),
            workflow_path=(result.get("metadata") or {}).get("workflow_path"),
        )
        return result  # type: ignore[return-value]


_master_agent: MasterAgent | None = None


def get_master_agent() -> MasterAgent:
    global _master_agent
    if _master_agent is None:
        _master_agent = MasterAgent()
    return _master_agent


def reset_master_agent() -> None:
    global _master_agent
    _master_agent = None
