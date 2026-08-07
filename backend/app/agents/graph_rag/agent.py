"""GraphRAG specialist — knowledge-graph path discovery + hybrid retrieval."""

from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent
from app.graphrag.langchain_graphrag import langchain_graphrag


class GraphRAGAgent(BaseAgent):
    """
    Discovers support answers via the knowledge graph:

    Customer → Product → Warranty → Policy → FAQ
    (and issue/resolution branches such as Battery Issue → Replacement Process)
    """

    name = AgentName.GRAPH_RAG

    async def run(self, state: AgentState) -> AgentResult:
        query = state.get("user_message") or ""
        customer_id = state.get("customer_id")
        result = await langchain_graphrag.ainvoke(query, customer_id=customer_id)
        citations = result.get("citations") or list(state.get("citations") or [])
        path = result.get("discovery_path") or []
        chain = result.get("discovery_chain") or ""
        discovery = result.get("discovery") or {}

        confidence = 0.4
        if path:
            confidence = 0.9
        elif result.get("documents") or result.get("entities"):
            confidence = 0.75

        content = result.get("summary") or "No graph context found."
        if chain:
            tips = discovery.get("guidance") or []
            content = f"**GraphRAG path:** {chain}"
            if tips:
                content += "\n\n" + "\n".join(f"- {t}" for t in tips[:4])

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=content,
            confidence=confidence,
            citations=citations if isinstance(citations, list) else [],
            data={
                "entities": result.get("entities") or [],
                "graph_nodes": result.get("graph_nodes") or [],
                "documents": result.get("documents") or [],
                "discovery_path": path,
                "discovery_chain": chain,
                "in_warranty": discovery.get("in_warranty"),
                "months_since_purchase": discovery.get("months_since_purchase"),
                "schema": discovery.get("schema")
                or [
                    "Customer",
                    "Purchased",
                    "Product",
                    "Covered by",
                    "Warranty",
                    "Linked to",
                    "Support Policy",
                    "Linked to",
                    "FAQ",
                ],
                "framework": "langchain_graphrag",
            },
        )
