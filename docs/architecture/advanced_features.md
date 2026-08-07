# Advanced Features

Enterprise capabilities beyond the core agentic support loop.

Implementation: `backend/app/advanced/features.py`  
API: `/api/v1/advanced/*` (`backend/app/api/v1/endpoints/advanced.py`)

## Feature matrix

| Feature | Status | How |
|---------|--------|-----|
| AI-generated ticket summaries | Done | Ticket Agent + `POST /api/v1/advanced/ticket/summary` |
| Voice-to-text support | Done | `POST /api/v1/advanced/voice/stt` (+ channel voice utterance) |
| Speech synthesis responses | Done | `POST /api/v1/advanced/voice/tts` |
| Customer sentiment dashboard | Done | Master records events → `GET /api/v1/advanced/sentiment/dashboard` |
| SLA monitoring | Done | Auto-register on ticket create → `GET /api/v1/advanced/sla` |
| Auto-priority (P1/P2/P3) | Done | Ticket Agent `auto_priority` (maps to DB urgent/high/medium) |
| AI-powered quality assurance | Done | `POST /api/v1/advanced/qa/score` |
| Agent performance analytics | Done | Metrics from Master `_run_agent` → `GET /api/v1/advanced/analytics/agents` |
| Customer satisfaction prediction | Done | `POST /api/v1/advanced/csat/predict` |
| Fraud detection for refunds | Done | Refund Agent + `POST /api/v1/advanced/fraud/refund` |
| Conversation summarization | Done | `POST /api/v1/advanced/conversation/summary` |
| Multilingual support (50+ languages) | Done | `GET /api/v1/advanced/languages` + `app/i18n` |
| AI-powered FAQ generation | Done | `POST /api/v1/advanced/faq/generate` |
| Continuous knowledge-base ingestion | Done | `POST /api/v1/advanced/knowledge/continuous-ingest` |
| Real-time notifications | Done | SSE `GET /api/v1/advanced/notifications/stream` + poll/publish |
| Feedback-driven prompt optimization | Done | Feedback API + `GET /api/v1/advanced/prompts/optimization` |

## Priority mapping

| Level | Meaning | SLA target | DB enum |
|-------|---------|------------|---------|
| P1 | Critical | 60 min | `urgent` |
| P2 | High | 4 hours | `high` |
| P3 | Normal | 24 hours | `medium` |

## Example calls

```bash
curl http://localhost:8917/api/v1/advanced

curl -X POST http://localhost:8917/api/v1/advanced/priority \
  -H "Content-Type: application/json" \
  -d '{"intent":"refund","sentiment":"angry","message":"chargeback immediately"}'

curl http://localhost:8917/api/v1/advanced/sentiment/dashboard?hours=24

curl http://localhost:8917/api/v1/advanced/notifications/stream
```

Roadmap: [docs/roadmap.md](../roadmap.md)
