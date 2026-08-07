# Technology Stack Alignment

| Layer | Technology | Project mapping |
| ----- | ---------- | --------------- |
| Language | Python 3.12 | `backend/.venv`, `Dockerfile` |
| IDE | Cursor | this repo |
| Backend | FastAPI | `backend/app/main.py` · port **8917** |
| AI Framework | LangGraph + LangChain | `agents/master/graph.py`, `graphrag/langchain_graphrag.py` |
| Workflow | n8n | `n8n/workflows/*` + RabbitMQ events |
| Models | GPT-5.x / Claude / Gemini / Llama | `llm/adapters/*` (`OPENAI_MODEL=gpt-5`) |
| Embeddings | OpenAI text embeddings / BGE Large / E5 Large / Sentence Transformers | `rag/embeddings/factory.py` |
| Vector DB | Qdrant / Pinecone / Chroma | `VECTOR_STORE=qdrant\|pinecone\|chroma` |
| Graph DB | Neo4j | Compose `aics-neo4j` · `NEO4J_URI` |
| GraphRAG | LangChain GraphRAG | `graphrag/langchain_graphrag.py` |
| Database | PostgreSQL | SQLAlchemy async · port **25433** host-mapped |
| Cache | Redis | conversation/profile memory · **26379** |
| Queue | RabbitMQ | `workflows/events.py` topic exchange `aics.events` |
| Monitoring | Prometheus + Grafana | `/metrics` + `grafana/` + compose profile `observability` |
| Authentication | JWT + OAuth2 | `/api/v1/auth/token` |
| UI | React + Tailwind | `frontend/` |
| Deployment | Docker + Kubernetes | `docker-compose.yml` + `k8s/` |

## Switching vector backends

```bash
# Qdrant (default)
VECTOR_STORE=qdrant

# Pinecone
pip install pinecone
VECTOR_STORE=pinecone
PINECONE_API_KEY=...
PINECONE_INDEX=aics-knowledge

# Chroma
pip install chromadb
VECTOR_STORE=chroma
CHROMA_PERSIST_DIR=./data/chroma
```

## Switching embedding providers

```bash
# OpenAI text embeddings (default)
DEFAULT_EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_API_KEY=...

# BGE Large
pip install sentence-transformers
DEFAULT_EMBEDDING_PROVIDER=bge
BGE_MODEL_NAME=BAAI/bge-large-en-v1.5

# E5 Large
DEFAULT_EMBEDDING_PROVIDER=e5
E5_MODEL_NAME=intfloat/e5-large-v2

# Sentence Transformers
DEFAULT_EMBEDDING_PROVIDER=sentence_transformers
SENTENCE_TRANSFORMER_MODEL=sentence-transformers/all-mpnet-base-v2
```

See [embeddings.md](embeddings.md) for the full catalog.
