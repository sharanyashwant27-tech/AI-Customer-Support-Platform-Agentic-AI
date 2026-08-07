# API Documentation

Interactive OpenAPI: [http://localhost:8917/docs](http://localhost:8917/docs)

## Chat

```http
POST /api/v1/chat/message
Content-Type: application/json

{
  "message": "I need a refund for order ORD-1001",
  "session_id": "optional-session-id",
  "channel": "web"
}
```

Response includes `reply`, `intent`, `confidence`, `agents_used`, `citations`, `handoff_required`, and `sentiment`.

## Auth (OAuth2 password)

```http
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded

username=user@example.com&password=secret123
```

Use `Authorization: Bearer <access_token>` on protected routes.

## Orders

```http
POST /api/v1/orders/lookup
{"order_id": "ORD-1001"}
```

## Tickets

```http
POST /api/v1/tickets
{"subject": "Damaged item", "description": "...", "priority": "high"}
```

## Knowledge

```http
POST /api/v1/knowledge/ingest
{"title": "Return Policy", "content": "..."}
```

## Feedback

```http
POST /api/v1/feedback
{"rating": 5, "comment": "Resolved quickly"}
```
