# AI Agents

Nine agents coordinated by the Master Agent (LangGraph).

## 1. Master Agent

**Responsibilities:** understand request · delegate work · maintain context · manage memory

Orchestrates the agentic decision tree:

Intent → Need Knowledge? (RAG/GraphRAG/Vector) → Customer History → Need Order? → Need Ticket? → Need Human? → Final Response

See [architecture/agentic_workflow.md](architecture/agentic_workflow.md).

## 2. Intent Classification Agent

**Classifies:** Refund · Complaint · Shipping · Product · Technical · Billing · Warranty

Shipping delays map to the package-delay playbook (`subtype: package_delay`). Human requests map to escalation/handoff.

## 3. Knowledge Agent

**Uses:** RAG · GraphRAG · embeddings

**Pipeline:** Documents → Chunking → Cleaning → Embeddings → Vector DB → Retriever → LLM → Answer

**GraphRAG:** Customer → Product → Warranty → Support Policy → FAQ (see [architecture/graphrag.md](architecture/graphrag.md))

**Searches:** PDFs · Product Manuals · FAQs · Policies · Knowledge Base · Emails · Release Notes · Internal Documentation

See [architecture/rag_pipeline.md](architecture/rag_pipeline.md).

## 4. Order Management Agent

**Checks:** order status — Delivered · Delayed · Returned · Cancelled (also shipped/processing)

## 5. Ticket Agent

**Automatically:** creates · updates · closes · escalates tickets

## 6. Sentiment Agent

**Detects:** Happy · Neutral · Angry · Frustrated · Urgent

Also exposes polarity (`positive` / `neutral` / `negative`) for handoff heuristics.

## 7. Recommendation Agent

**Suggests:** products · coupons · offers · upgrades

## 8. Email Agent

**Generates:** professional replies · follow-ups · escalation emails

## 9. Human Handoff Agent

**Transfers chat including:** entire conversation · summary · suggested resolution
