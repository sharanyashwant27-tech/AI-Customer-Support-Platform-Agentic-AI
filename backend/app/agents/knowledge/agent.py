"""Knowledge Agent — RAG pipeline over indexed knowledge sources."""

from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent
from app.rag.pipeline import PIPELINE_STAGES, rag_pipeline
from app.rag.sources import KNOWLEDGE_SOURCES


class KnowledgeAgent(BaseAgent):
    """
    Uses the RAG pipeline:
    Documents → Chunking → Cleaning → Embeddings → Vector DB
    → Retriever → LLM → Answer

    Knowledge sources: PDFs, Product Manuals, FAQs, Policies,
    Knowledge Base, Emails, Release Notes, Internal Documentation.
    """

    name = AgentName.KNOWLEDGE

    async def run(self, state: AgentState) -> AgentResult:
        query = state.get("user_message") or ""
        language = str(state.get("language") or "en")
        result = await rag_pipeline.answer(query, language=language)
        citations = result.get("citations") or []

        if not citations:
            return AgentResult(
                agent_name=self.name,
                success=True,
                content=result.get("answer")
                or "I couldn't find matching knowledge articles yet.",
                confidence=float(result.get("confidence") or 0.35),
                data={
                    "hit_count": 0,
                    "sources": KNOWLEDGE_SOURCES,
                    "pipeline": PIPELINE_STAGES,
                    "stages": result.get("stages") or [],
                    "methods": ["rag", "embeddings", "retriever", "llm"],
                },
            )

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=result["answer"],
            confidence=float(result.get("confidence") or 0.85),
            citations=citations,
            data={
                "hit_count": len(citations),
                "top_score": float((citations[0] or {}).get("score") or 0.0),
                "sources": KNOWLEDGE_SOURCES,
                "pipeline": PIPELINE_STAGES,
                "stages": result.get("stages") or [],
                "llm_used": result.get("llm_used"),
                "methods": ["rag", "embeddings", "retriever", "llm"],
            },
        )
