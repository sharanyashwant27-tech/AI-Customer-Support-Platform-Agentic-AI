# Environment Setup

## Prerequisites

- Python 3.11+
- Node.js 20+ (frontend)
- Docker Desktop (optional infrastructure)
- Git

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example ..\.env
python run.py
```

API listens on **http://localhost:8917**.

### Optional LLM keys

Set in `.env`:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- or run Ollama and set `DEFAULT_LLM_PROVIDER=llama`

Without keys, the platform uses a deterministic **StubLLMAdapter** so local development works offline.

## Infrastructure

Host ports are remapped to avoid clashes with other local stacks:

| Service | Host port |
|---------|-----------|
| API | 8917 |
| Frontend | 3017 (`--profile full`) |
| Postgres | 25433 |
| Redis | 26379 |
| RabbitMQ | 25672 (UI 25673) |
| Qdrant | 26333 |
| Neo4j | 27687 (HTTP 27474) |

```powershell
docker compose up -d postgres redis rabbitmq qdrant neo4j
```

RabbitMQ UI: http://localhost:25673 (aics / aics_secret)

## Frontend (later phase)

```powershell
cd frontend
npm install
npm run dev
```

## Tests

```powershell
cd backend
pytest -q
```
