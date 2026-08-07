# Project Structure & REST APIs

## REST APIs

Public contract (also mirrored under `/api/...`):

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/chat` | Customer chat → Master Agent |
| `POST` | `/ticket` | Create support ticket |
| `GET` | `/ticket/{id}` | Get ticket by UUID or `TKT-…` |
| `GET` | `/orders/{id}` | Get order (e.g. `ORD-1001`) |
| `POST` | `/upload` | Upload knowledge file into RAG |
| `POST` | `/knowledge/index` | Index knowledge text |
| `GET` | `/customer/{id}` | Customer profile + history |
| `POST` | `/feedback` | CSAT / prompt feedback |

OpenAPI: `http://localhost:8917/docs`  
Implementation: `backend/app/api/rest.py`

Extended routes remain under `/api/v1/*` (auth, channels, workflows, health, **advanced**).

Advanced features (summaries, SLA, sentiment dashboard, voice, fraud, FAQ gen, SSE):  
[advanced_features.md](advanced_features.md) · Roadmap: [../roadmap.md](../roadmap.md)

### Examples

```bash
curl -X POST http://localhost:8917/chat -H "Content-Type: application/json" \
  -d '{"message":"Where is my order ORD-1001?","session_id":"s1"}'

curl -X POST http://localhost:8917/ticket -H "Content-Type: application/json" \
  -d '{"subject":"Payment failed","description":"Card declined twice","priority":"high"}'

curl http://localhost:8917/orders/ORD-1001

curl -X POST http://localhost:8917/knowledge/index -H "Content-Type: application/json" \
  -d '{"title":"Payment Policy","content":"Failed charges are not captured.","knowledge_source":"policies"}'

curl -X POST http://localhost:8917/upload -F "file=@manual.pdf"

curl http://localhost:8917/customer/cust-1

curl -X POST http://localhost:8917/feedback -H "Content-Type: application/json" \
  -d '{"rating":5,"comment":"Helpful","session_id":"s1"}'
```

## Folder Structure

Target layout vs this repo:

```text
AI-Customer-Support/          (repo root)
│
├── backend/
│   ├── app/                  ← Python package (import path: app.*)
│   │   ├── agents/           ← agents/
│   │   ├── workflows/        ← workflows/
│   │   ├── rag/              ← rag/ (+ embeddings, vectorstores)
│   │   ├── graphrag/         ← graphrag/
│   │   ├── prompts/          ← prompts/
│   │   ├── embeddings/       ← alias → rag.embeddings
│   │   ├── vector_db/        ← alias → rag.vectorstores
│   │   ├── memory/           ← memory/
│   │   ├── api/              ← api/  (rest.py + v1/)
│   │   ├── services/         ← services/
│   │   ├── models/           ← alias → db.models
│   │   ├── db/models/        ← SQLAlchemy tables
│   │   └── main.py           ← main.py
│   ├── tests/                ← tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
├── n8n/
├── docs/
├── sample_data/
├── sample_prompts/
├── k8s/                      ← kubernetes docker/ + kubernetes manifests
├── grafana/ · prometheus/
├── docker-compose.yml
└── README.md
```

| Spec folder | Location in repo |
|-------------|------------------|
| `backend/agents` | `backend/app/agents` |
| `backend/workflows` | `backend/app/workflows` |
| `backend/rag` | `backend/app/rag` |
| `backend/graphrag` | `backend/app/graphrag` |
| `backend/prompts` | `backend/app/prompts` |
| `backend/embeddings` | `backend/app/embeddings` (alias) |
| `backend/vector_db` | `backend/app/vector_db` (alias) |
| `backend/memory` | `backend/app/memory` |
| `backend/api` | `backend/app/api` |
| `backend/services` | `backend/app/services` |
| `backend/models` | `backend/app/models` + `backend/app/db/models` |
| `backend/main.py` | `backend/app/main.py` |
| `docker/` | `docker-compose.yml` + `backend/Dockerfile` + `frontend/Dockerfile` + `k8s/` |
| `tests/` | `backend/tests/` |
