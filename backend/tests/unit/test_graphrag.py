"""GraphRAG knowledge-graph discovery tests."""

import pytest

from app.agents.graph_rag.agent import GraphRAGAgent
from app.graphrag.service import graph_rag_service


def test_knowledge_graph_schema_seeded():
    nodes = graph_rag_service._memory.nodes
    assert "CUSTOMER:default" in nodes
    assert "PRODUCT:laptop" in nodes
    assert "WARRANTY:laptop-12m" in nodes
    assert "POLICY:warranty-support" in nodes
    assert "FAQ:battery-charging" in nodes
    assert "ISSUE:battery" in nodes
    assert "PROCESS:replacement" in nodes


def test_battery_example_discovery_path():
    query = "My laptop battery stopped charging after 7 months."
    discovery = graph_rag_service.discover_path(query)
    assert discovery["discovery_path"] == [
        "Customer",
        "Laptop",
        "Warranty",
        "Battery Issue",
        "Policy",
        "Replacement Process",
    ]
    assert discovery["months_since_purchase"] == 7
    assert discovery["in_warranty"] is True
    assert "Customer → Laptop → Warranty → Battery Issue → Policy → Replacement Process" in (
        discovery["discovery_chain"]
    )


@pytest.mark.asyncio
async def test_graphrag_agent_battery_query():
    agent = GraphRAGAgent()
    result = await agent.run(
        {"user_message": "My laptop battery stopped charging after 7 months."}
    )
    assert result.success
    assert result.data["discovery_path"][0] == "Customer"
    assert result.data["discovery_path"][-1] == "Replacement Process"
    assert result.data["in_warranty"] is True
    assert "GraphRAG path" in result.content
    assert result.confidence >= 0.9
