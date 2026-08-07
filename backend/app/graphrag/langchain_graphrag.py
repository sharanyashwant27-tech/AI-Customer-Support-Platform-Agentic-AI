"""LangChain / LangGraph-compatible GraphRAG facade over Neo4j hybrid retrieval."""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.graphrag.service import graph_rag_service
from app.rag.pipeline import rag_pipeline

logger = get_logger(__name__)


class LangChainGraphRAG:
    """
    GraphRAG layer: vector retrieval + knowledge-graph path discovery.

    Knowledge graph:
      Customer → Purchased → Product → Covered by → Warranty
               → Linked to → Support Policy → Linked to → FAQ
    """

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        citations = await rag_pipeline.retrieve(query, top_k=top_k)
        await graph_rag_service.ingest_text(query, source="graphrag")
        hybrid = await graph_rag_service.hybrid_retrieve(
            query,
            vector_citations=citations,
            top_k=top_k,
            customer_id=customer_id,
        )
        documents = [
            {
                "page_content": c.get("excerpt") or "",
                "metadata": {
                    "source": c.get("source"),
                    "score": c.get("score"),
                    **(c.get("metadata") or {}),
                },
            }
            for c in citations
        ]
        discovery = hybrid.get("discovery") or {}
        if hybrid.get("discovery_chain"):
            documents.insert(
                0,
                {
                    "page_content": (
                        f"GraphRAG path: {hybrid['discovery_chain']}. "
                        + " ".join(discovery.get("guidance") or [])
                    ),
                    "metadata": {
                        "source": "graphrag",
                        "discovery_path": hybrid.get("discovery_path"),
                    },
                },
            )
        for node in hybrid.get("graph_nodes") or []:
            documents.append(
                {
                    "page_content": (
                        f"Graph node [{node.get('label')}]: "
                        f"{node.get('display') or node.get('name') or node.get('id')}"
                    ),
                    "metadata": {"source": "neo4j", **node},
                }
            )
        logger.info(
            "langchain_graphrag_retrieve",
            docs=len(documents),
            entities=len(hybrid.get("entities") or []),
            path=hybrid.get("discovery_chain"),
        )
        return {
            "documents": documents,
            "entities": hybrid.get("entities") or [],
            "graph_nodes": hybrid.get("graph_nodes") or [],
            "discovery_path": hybrid.get("discovery_path") or [],
            "discovery_chain": hybrid.get("discovery_chain") or "",
            "discovery": discovery,
            "summary": hybrid.get("summary") or "",
            "citations": citations,
        }

    async def ainvoke(
        self,
        query: str,
        *,
        top_k: int = 5,
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        """LangChain Runnable-like async entrypoint."""
        return await self.retrieve(query, top_k=top_k, customer_id=customer_id)


langchain_graphrag = LangChainGraphRAG()
