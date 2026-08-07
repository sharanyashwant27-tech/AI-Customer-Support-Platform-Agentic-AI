# Docker

Compose and image entrypoints for the AI Customer Support Platform.

| Spec | Location |
|------|----------|
| Compose | [`docker-compose.yml`](../docker-compose.yml) (repo root) |
| Backend image | [`backend/Dockerfile`](../backend/Dockerfile) — includes **`README.md`** + `docs/` |
| Frontend image | [`frontend/Dockerfile`](../frontend/Dockerfile) |
| Root ignore rules | [`.dockerignore`](../.dockerignore) |
| Kubernetes | [`k8s/`](../k8s/) |

## Build API image (ships README.md)

Build **from the repository root** so `README.md` is copied into `/app/README.md`:

```bash
docker build -f backend/Dockerfile -t aics-api:latest .
```

Verify:

```bash
docker run --rm aics-api:latest cat /app/README.md | head
docker images aics-api
```

## Compose

Host ports are remapped to avoid clashes with other local stacks:

| Service | Host port |
|---------|-----------|
| API | **8917** |
| Frontend (profile `full`) | **3017** |
| Postgres | 25433 |
| Redis | 26379 |
| Qdrant | 26333 |
| Neo4j HTTP / Bolt | 27474 / 27687 |
| RabbitMQ / Mgmt | 25672 / 25673 |
| n8n (profile `full`) | 5678 |

```bash
# Infra only
docker compose up -d postgres redis rabbitmq qdrant neo4j

# API image + infra
docker compose up -d --build api

# Full stack (+ frontend on :3017, n8n)
docker compose --profile full up -d --build

# Observability
docker compose --profile observability up -d
```

Open after API is up:

- http://localhost:8917/
- http://localhost:8917/docs
- http://localhost:8917/api/v1/health
- http://localhost:8917/api/v1/advanced

See also [environment setup](../docs/setup/environment.md) and the root [README.md](../README.md).
