# PostgreSQL Database Schema

Core tables:

| Table | Purpose |
|-------|---------|
| `customers` | Customer CRM profiles |
| `orders` | Purchase / shipment records |
| `tickets` | Support tickets |
| `products` | Catalog SKUs |
| `knowledge_docs` | Indexed knowledge source documents |
| `chat_history` | Conversation turns |
| `agents` | AI + human agent registry |
| `feedback` | Ratings / prompt optimization signals |

Auth uses a separate `users` table linked via `users.customer_id → customers.id`.

```text
customers ─┬─< orders >─┬─ order_items >─ products
           ├─< tickets >──── agents
           ├─< chat_history
           └─< feedback
knowledge_docs
```

## Models

| Table | Code |
|-------|------|
| customers | `backend/app/db/models/customer.py` |
| orders | `backend/app/db/models/order.py` |
| tickets | `backend/app/db/models/ticket.py` |
| products | `backend/app/db/models/product.py` |
| knowledge_docs | `backend/app/db/models/knowledge_doc.py` |
| chat_history | `backend/app/db/models/chat_history.py` |
| agents | `backend/app/db/models/agent.py` |
| feedback | `backend/app/db/models/feedback.py` |

Created on API startup by `init_db()` (`Base.metadata.create_all`). Agents + sample products are seeded automatically.

## Connection

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=25433
POSTGRES_DB=aics
POSTGRES_USER=aics
POSTGRES_PASSWORD=aics_secret
```
