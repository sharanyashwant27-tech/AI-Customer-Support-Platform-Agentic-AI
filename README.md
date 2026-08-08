# Enterprise AI Customer Support Platform

Production-oriented multi-agent customer support platform built with **FastAPI**, **React + Tailwind**, **LangGraph**, **PostgreSQL**, **Redis**, **RabbitMQ**, **Qdrant**, and **Neo4j**.

## Technology stack

| Layer | Technology |
| ----- | ---------- |
| Language | Python 3.12 |
| IDE | Cursor |
| Backend | FastAPI |
| AI Framework | LangGraph + LangChain |
| Workflow | n8n |
| Models | GPT-5.x / Claude / Gemini / Llama |
| Embeddings | OpenAI text embeddings / BGE Large / E5 Large / Sentence Transformers |
| Vector DB | Qdrant / Pinecone / Chroma |
| Graph DB | Neo4j |
| GraphRAG | LangChain GraphRAG |
| Database | PostgreSQL |
| Cache | Redis |
| Queue | RabbitMQ |
| Monitoring | Prometheus + Grafana |
| Authentication | JWT + OAuth2 |
| UI | React + Tailwind |
| Deployment | Docker + Kubernetes |

## Quick start (localhost:8917)

```bash
# 1. Create virtualenv and install backend deps
cd backend
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Copy env (already present at repo root as .env)
cd ..
copy .env.example .env   # if needed

# 3. Run the API on port 8917
cd backend
python run.py
# or: uvicorn app.main:app --host 0.0.0.0 --port 8917 --reload
```

Open:
- Customer chat UI: http://localhost:8917/
- API console: http://localhost:8917/console
- Swagger docs: http://localhost:8917/docs
- Health: http://localhost:8917/api/v1/health
- Metrics: http://localhost:8917/metrics/

### Smoke-test chat

```bash
curl -X POST http://localhost:8917/api/v1/chat/message ^
  -H "Content-Type: application/json" ^
  -d "{\"message\": \"Where is my order ORD-1001?\"}"
```

## Architecture (high level)

```text
Customer → React Chat UI → FastAPI Gateway → Master AI Agent
                              │
        ┌─────────┬───────────┼───────────┬──────────┐
        ▼         ▼           ▼           ▼          ▼
   Intent    Knowledge     Order       Ticket   Sentiment
        └─────────┴───────────┴───────────┴──────────┘
                              │
                   Response Synthesizer Agent
                              │
                             LLM
                              │
                          Response
```

Full diagram: [docs/architecture/complete_architecture.md](docs/architecture/complete_architecture.md) · Agentic workflow: [docs/architecture/agentic_workflow.md](docs/architecture/agentic_workflow.md) · RAG pipeline: [docs/architecture/rag_pipeline.md](docs/architecture/rag_pipeline.md) · Embeddings: [docs/architecture/embeddings.md](docs/architecture/embeddings.md) · GraphRAG: [docs/architecture/graphrag.md](docs/architecture/graphrag.md) · Prompt engineering: [docs/architecture/prompt_engineering.md](docs/architecture/prompt_engineering.md) · n8n Customer Chat: [docs/architecture/n8n_customer_chat.md](docs/architecture/n8n_customer_chat.md) · Database: [docs/architecture/database.md](docs/architecture/database.md) · REST + structure: [docs/architecture/rest_and_structure.md](docs/architecture/rest_and_structure.md) · Tickets: [docs/architecture/tickets.md](docs/architecture/tickets.md) · Advanced features: [docs/architecture/advanced_features.md](docs/architecture/advanced_features.md) · Roadmap: [docs/roadmap.md](docs/roadmap.md) · Agent specs: [docs/agents.md](docs/agents.md)

## Capabilities

| Capability | Implementation |
|------------|----------------|
| Answer questions | Master Agent + LLM adapters |
| Product documentation | RAG (Qdrant) + GraphRAG (Neo4j) |
| Track orders | Order Management Agent + `/orders` |
| Process refunds | Refund Agent (`/channels/*/message`, intent `refund`) |
| Create tickets | Ticket Agent + `/tickets` (Postgres) |
| Human escalation | Handoff Agent + Slack/Teams alerts |
| Customer history | Redis memory + `/customers/{id}/history` |
| Sentiment | Sentiment Analysis Agent |
| Multi-language | Detect/translate via `app/i18n` + channel `language` |
| Email | `/channels/email/inbound` + outbound webhook |
| Chat / Web | `/chat/message` + React UI |
| WhatsApp | `/channels/whatsapp/webhook` |
| Voice | `/channels/voice/utterance` (STT in → TTS out) |
| Slack | `/channels/slack/events` + n8n `aics-slack` |
| MS Teams | `/channels/teams/webhook` + n8n `aics-teams` |

| Layer | Technology |
|-------|------------|
| API | FastAPI on port **8917** |
| Frontend | React + Tailwind CSS |
| Auth | JWT + OAuth2 password flow |
| DB / Cache / Queue | PostgreSQL, Redis, RabbitMQ |
| Orchestration | LangGraph Master Agent |
| RAG | Chunking → Embeddings → Qdrant (Pinecone/Chroma adapters) |
| GraphRAG | Neo4j entity/relationship extraction |
| LLMs | OpenAI, Anthropic, Gemini, local Llama adapters |
| Observability | structlog, Prometheus, Grafana |
| Automation | n8n workflow exports |
| Deploy | Docker Compose, Kubernetes, GitHub Actions |

## Project layout

```
backend/app/          agents, workflows, rag, graphrag, prompts, embeddings,
                      vector_db, memory, api, services, models, main.py
backend/tests/        Unit / integration / eval tests
frontend/             React + Tailwind chat UI
n8n/                  Customer Chat + alert workflows
docker/               Compose / image pointers
docs/                 Architecture + API docs
k8s/                  Kubernetes manifests
grafana/              Dashboard provisioning
sample_data/          Sample docs, orders, eval sets
sample_prompts/       Versioned prompt templates
docker-compose.yml    Local infra + optional full stack
```

## Incremental delivery plan

1. **Done (this phase):** folder structure, architecture docs, config, foundational FastAPI + Master Agent graph, Docker Compose, samples
2. Full RAG ingestion + embedding adapters
3. GraphRAG + remaining specialized agents
4. Memory layers + prompt tuning pipeline
5. React frontend + n8n flows
6. Full test suite + K8s + CI/CD hardening

## Infrastructure (Docker)

Host ports are remapped to avoid clashes with other local Docker stacks.

### Build API image (includes this README)

Build from the **repository root** so `README.md` and `docs/` are packaged into the image at `/app/README.md`:

```bash
docker build -f backend/Dockerfile -t aics-api:latest .

# Confirm README is inside the image
docker run --rm aics-api:latest cat /app/README.md | more
```

### Compose

```bash
# Infra only
docker compose up -d postgres redis rabbitmq qdrant neo4j

# Rebuild & start API (image: aics-api:latest)
docker compose up -d --build api

# Full stack (+ frontend on :3017, n8n)
docker compose --profile full up -d --build

# Observability (Prometheus :9090, Grafana :3001)
docker compose --profile observability up -d
```

| URL | Purpose |
|-----|---------|
| http://localhost:8917/ | **Customer chat UI** (React) |
| http://localhost:8917/console | API developer console |
| http://localhost:8917/docs | OpenAPI |
| http://localhost:8917/api/v1/health | Health |
| http://localhost:8917/api/v1/advanced | Advanced features |
| http://localhost:3017/ | Standalone frontend container (`--profile full`) |

Details: [docker/README.md](docker/README.md)

### Local API without containers (dev)

```bash
# After infra containers are up, point .env at remapped ports:
# POSTGRES_PORT=25433 REDIS_PORT=26379 QDRANT_PORT=26333
# NEO4J_URI=bolt://localhost:27687 RABBITMQ_PORT=25672
cd backend
python run.py
```

## License

Proprietary — internal enterprise use.
