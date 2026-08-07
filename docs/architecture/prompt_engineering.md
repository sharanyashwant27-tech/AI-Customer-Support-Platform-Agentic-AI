# Prompt Engineering

## System Prompt

```text
You are an AI Customer Support Specialist.

Always:
- Be polite.
- Use retrieved knowledge.
- Never hallucinate.
- If confidence <90%, ask clarification.
- Escalate when required.
- Summarize conversation.
- Suggest next best action.
```

Templates: `sample_prompts/master_system_v1.json` (+ A/B `master_system_b.json`)  
Rendered by `backend/app/prompts/registry.py` → Response Synthesizer.

Clarification threshold: `CLARIFICATION_CONFIDENCE_THRESHOLD=0.9`

## Prompt Tuning (few-shot)

Example — Customer: **"My payment failed."**

```text
Detect → Billing
Retrieve → Payment Policy
Answer
Offer retry
Create ticket if needed
```

Files:

- `sample_prompts/few_shot_billing.json`
- Payment policy seed: `sample_data/documents/payment_policy.md`

## Memory

Maintain:

| Store | Purpose |
|-------|---------|
| Conversation Memory | Recent turns + summary |
| Customer Profile | Tier, last intent/sentiment |
| Purchase History | Orders / products |
| Previous Tickets | Ticket numbers & status |
| Preferences | Channel, language, contact method |

Code: `backend/app/memory/conversation.py`  
Loaded in Master workflow at **Customer History** (`customer_history_node`).
