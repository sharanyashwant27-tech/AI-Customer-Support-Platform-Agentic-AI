# Support tickets

## Create

### Chat UI
1. Open http://localhost:8917/
2. Describe the issue → **Send**, or click **Create support ticket**

### REST
```bash
curl -X POST http://localhost:8917/api/v1/tickets \
  -H "Content-Type: application/json" \
  -d "{\"subject\":\"Package delayed\",\"description\":\"ORD-1001 not delivered\",\"priority\":\"high\"}"
```

## Close when resolved

### Chat UI
- In the **Tickets** list, click **Mark resolved** next to an open ticket  
- Or chat: `Please close ticket TKT-XXXXXXXX — issue resolved`

### REST
```bash
# Mark resolved (recommended when the customer confirms the fix)
curl -X POST "http://localhost:8917/api/v1/tickets/TKT-XXXXXXXX/close?resolve=true"

# Mark closed
curl -X POST "http://localhost:8917/ticket/TKT-XXXXXXXX/close"

# Or PATCH status
curl -X PATCH http://localhost:8917/api/v1/tickets/TKT-XXXXXXXX \
  -H "Content-Type: application/json" \
  -d "{\"status\":\"resolved\"}"
```

Statuses: `open` → `in_progress` → `resolved` / `closed` (also `escalated`, `waiting_customer`).

Implementation: `ticket_service.close_ticket`, `POST /tickets/{id}/close`, Ticket Agent action `close`.
