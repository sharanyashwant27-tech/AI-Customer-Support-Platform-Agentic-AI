"""Placeholder specialized agents — implemented in subsequent increments."""

from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent


class KnowledgeAgent(BaseAgent):
    name = AgentName.KNOWLEDGE

    async def run(self, state: AgentState) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            content="Knowledge agent not fully wired — RAG pipeline coming next.",
            confidence=0.0,
            data={"status": "stub"},
        )


class GraphRAGAgent(BaseAgent):
    name = AgentName.GRAPH_RAG

    async def run(self, state: AgentState) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            content="GraphRAG agent stub.",
            confidence=0.0,
            data={"status": "stub"},
        )


class OrderManagementAgent(BaseAgent):
    name = AgentName.ORDER

    async def run(self, state: AgentState) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            content="Order agent stub — use /api/v1/orders/lookup for now.",
            confidence=0.0,
            data={"status": "stub"},
        )


class TicketManagementAgent(BaseAgent):
    name = AgentName.TICKET

    async def run(self, state: AgentState) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            content="Ticket agent stub — use /api/v1/tickets for now.",
            confidence=0.0,
            data={"status": "stub"},
        )


class RecommendationAgent(BaseAgent):
    name = AgentName.RECOMMENDATION

    async def run(self, state: AgentState) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            content="Recommendation agent stub.",
            confidence=0.0,
            data={"status": "stub", "recommendations": []},
        )


class EmailAgent(BaseAgent):
    name = AgentName.EMAIL

    async def run(self, state: AgentState) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            content="Email agent stub.",
            confidence=0.0,
            data={"status": "stub"},
        )
