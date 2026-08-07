# Embeddings & Vector Stores

## Embeddings — use

| Provider | Model (default) | Config |
|----------|-----------------|--------|
| **OpenAI text embeddings** | `text-embedding-3-large` | `DEFAULT_EMBEDDING_PROVIDER=openai` |
| **BGE Large** | `BAAI/bge-large-en-v1.5` | `DEFAULT_EMBEDDING_PROVIDER=bge` |
| **E5 Large** | `intfloat/e5-large-v2` | `DEFAULT_EMBEDDING_PROVIDER=e5` |
| **Sentence Transformers** | `sentence-transformers/all-mpnet-base-v2` | `DEFAULT_EMBEDDING_PROVIDER=sentence_transformers` |

Code: `backend/app/rag/embeddings/factory.py`

Without an OpenAI key or local model install, the pipeline falls back to a deterministic hash embedding stub so ingest/retrieve still works offline.

### E5 / BGE prefixes

- E5 documents use `passage: …`, queries use `query: …`
- BGE queries use the recommended retrieval instruction prefix

## Store inside

| Vector DB | When to use | Config |
|-----------|-------------|--------|
| **Qdrant** | Default local / self-hosted | `VECTOR_STORE=qdrant` |
| **Pinecone** | Managed cloud | `VECTOR_STORE=pinecone` + `PINECONE_API_KEY` |
| **Chroma** | Embedded persistent local | `VECTOR_STORE=chroma` + `CHROMA_PERSIST_DIR` |

Code: `backend/app/rag/vectorstores/`

```bash
# Qdrant (default)
VECTOR_STORE=qdrant
QDRANT_HOST=localhost
QDRANT_PORT=26333

# Pinecone
VECTOR_STORE=pinecone
PINECONE_API_KEY=...
PINECONE_INDEX=aics-knowledge
PINECONE_ENVIRONMENT=us-east-1

# Chroma
VECTOR_STORE=chroma
CHROMA_PERSIST_DIR=./data/chroma
```

## API

`GET /api/v1/knowledge/backends` — active embedding provider + vector store catalog

## Flow

```text
Documents → Chunking → Cleaning → Embeddings (OpenAI / BGE / E5 / ST)
                                 → Vector DB (Qdrant / Pinecone / Chroma)
                                 → Retriever → LLM → Answer
```
