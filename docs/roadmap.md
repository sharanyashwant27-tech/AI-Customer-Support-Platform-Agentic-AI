# Development Roadmap

Phased delivery for the AI Customer Support Platform.

| Phase | Deliverables | Status |
|-------|--------------|--------|
| **Phase 1** | FastAPI backend, React UI, JWT authentication | **Done** |
| **Phase 2** | Master Agent and Intent Agent | **Done** |
| **Phase 3** | RAG pipeline with embeddings and vector database | **Done** |
| **Phase 4** | GraphRAG with Neo4j knowledge graph | **Done** |
| **Phase 5** | Order, Ticket, and Sentiment agents | **Done** |
| **Phase 6** | n8n automation for CRM, email, and notifications | **Done** |
| **Phase 7** | Memory, analytics, monitoring, and human handoff | **Done** |
| **Phase 8** | Docker, Kubernetes deployment, CI/CD, load testing | **Mostly done** |

## Phase details

### Phase 1 — Platform foundation
- FastAPI app (`backend/app/main.py`), JWT auth, React + Tailwind frontend
- Postgres / Redis / RabbitMQ via Docker Compose (remapped host ports)

### Phase 2 — Orchestration core
- LangGraph Master Agent (`backend/app/agents/master/graph.py`)
- Intent Classification Agent (Refund / Complaint / Shipping / Product / …)

### Phase 3 — Retrieval
- Document chunking → cleaning → embeddings → Qdrant (Pinecone/Chroma adapters)
- Docs: [rag_pipeline.md](architecture/rag_pipeline.md), [embeddings.md](architecture/embeddings.md)

### Phase 4 — GraphRAG
- Neo4j entity graph (Customer → Product → Warranty → Policy → FAQ)
- Docs: [graphrag.md](architecture/graphrag.md)

### Phase 5 — Domain agents
- Order, Ticket (P1/P2/P3), Sentiment, Refund, Recommendation, Email agents
- Specs: [agents.md](agents.md)

### Phase 6 — Automation
- n8n Customer Chat workflow + step APIs
- Docs: [n8n_customer_chat.md](architecture/n8n_customer_chat.md)

### Phase 7 — Memory, analytics, handoff
- Conversation / profile memory (`app/memory`)
- Human Handoff Agent + Slack/Teams alerts
- Advanced analytics: sentiment dashboard, SLA, agent performance, CSAT prediction, QA scoring
- Docs: [advanced_features.md](architecture/advanced_features.md)

### Phase 8 — Production ops
- Docker Compose + Kubernetes manifests (`k8s/`)
- CI/CD workflows and Prometheus/Grafana
- Load testing: expand Locust/k6 suites (remaining polish)

## Advanced features checklist

See [architecture/advanced_features.md](architecture/advanced_features.md) for the full feature matrix (summaries, voice, SLA, fraud, multilingual, FAQ gen, continuous ingest, realtime SSE, prompt optimization).
