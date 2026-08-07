"""Prompt engineering + memory tests."""

import pytest

from app.agents.synthesizer.agent import ResponseSynthesizerAgent
from app.memory.conversation import reset_memory_for_tests, ensure_memory
from app.prompts.loader import load_prompt, default_prompts_dir
from app.prompts.registry import get_prompt_registry, reset_prompt_registry, SYSTEM_ALWAYS_RULES


def test_system_prompt_always_rules():
    reset_prompt_registry()
    path = default_prompts_dir() / "master_system_v1.json"
    tmpl = load_prompt(path)
    for rule in SYSTEM_ALWAYS_RULES:
        assert any(rule.lower() in r.lower() for r in tmpl.always_rules) or rule.split()[0] in tmpl.template
    assert "AI Customer Support Specialist" in tmpl.template
    assert tmpl.clarification_threshold() == 0.9


def test_payment_failed_few_shot():
    reset_prompt_registry()
    registry = get_prompt_registry()
    billing = registry.get("few_shot_billing")
    assert billing is not None
    text = billing.format_few_shot(intent="billing")
    assert "My payment failed." in text
    assert "Billing" in text
    assert "Payment Policy" in text
    assert "Offer retry" in text or "retry" in text.lower()


@pytest.mark.asyncio
async def test_memory_bundle_fields():
    reset_memory_for_tests()
    memory = await ensure_memory()
    bundle = await memory.get_customer_memory_bundle(
        customer_id="cust-prompt-1", session_id="sess-prompt-1"
    )
    assert "conversation_memory" in bundle
    assert "customer_profile" in bundle
    assert "purchase_history" in bundle
    assert "previous_tickets" in bundle
    assert "preferences" in bundle
    block = memory.format_memory_block(bundle)
    assert "Purchase history" in block or "Preferences" in block


@pytest.mark.asyncio
async def test_payment_failed_synthesizer_playbook():
    agent = ResponseSynthesizerAgent()
    result = await agent.run(
        {
            "user_message": "My payment failed.",
            "intent": "ticket",
            "confidence": 0.95,
            "sentiment": "frustrated",
            "session_id": "pay-1",
            "agent_results": {
                "ticket": {
                    "success": True,
                    "content": "Created ticket",
                    "confidence": 0.9,
                    "data": {"ticket_draft": {"ticket_number": "TKT-PAY1", "status": "open"}},
                }
            },
            "metadata": {},
        }
    )
    assert "Payment Policy" in result.content or "payment" in result.content.lower()
    assert "Summary:" in result.content
    assert "Next best action:" in result.content
    assert result.data.get("playbook") == "payment_failed"
