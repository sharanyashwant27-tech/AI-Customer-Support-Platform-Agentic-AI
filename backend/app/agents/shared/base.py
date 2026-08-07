"""Base agent interfaces and shared state for LangGraph orchestration."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class AgentName(str, Enum):
    MASTER = "master"
    INTENT = "intent"
    KNOWLEDGE = "knowledge"
    GRAPH_RAG = "graph_rag"
    ORDER = "order"
    REFUND = "refund"
    TICKET = "ticket"
    SENTIMENT = "sentiment"
    RECOMMENDATION = "recommendation"
    EMAIL = "email"
    HANDOFF = "handoff"
    SYNTHESIZER = "synthesizer"


class AgentResult(BaseModel):
    """Standardized output from a specialized agent."""

    agent_name: AgentName
    success: bool = True
    content: str = ""
    confidence: float = 0.0
    data: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class AgentState(TypedDict, total=False):
    """Shared LangGraph state passed between agents."""

    messages: Annotated[list, add_messages]
    session_id: str
    customer_id: str | None
    user_message: str
    intent: str
    confidence: float
    sentiment: str
    agents_used: list[str]
    agent_results: dict[str, dict[str, Any]]
    citations: list[dict[str, Any]]
    recommendations: list[str]
    handoff_required: bool
    final_response: str
    language: str
    metadata: dict[str, Any]


class BaseAgent(ABC):
    """Abstract base for specialized support agents."""

    name: AgentName

    @abstractmethod
    async def run(self, state: AgentState) -> AgentResult:
        """Execute the agent against the current graph state."""

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        """LangGraph node entrypoint — merges AgentResult into state."""
        result = await self.run(state)
        agents_used = list(state.get("agents_used") or [])
        agents_used.append(self.name.value)
        agent_results = dict(state.get("agent_results") or {})
        agent_results[self.name.value] = result.model_dump()

        update: dict[str, Any] = {
            "agents_used": agents_used,
            "agent_results": agent_results,
        }
        if result.citations:
            update["citations"] = list(state.get("citations") or []) + result.citations
        return update
