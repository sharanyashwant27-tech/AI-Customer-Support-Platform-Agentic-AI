"""Agent evaluation suite against sample dataset."""

import json
from pathlib import Path

import pytest

from app.agents.intent.agent import IntentClassificationAgent
from app.agents.master.graph import MasterAgent

EVAL_PATH = (
    Path(__file__).resolve().parents[3]
    / "sample_data"
    / "evaluation"
    / "intent_eval.json"
)


@pytest.mark.asyncio
async def test_intent_eval_dataset():
    assert EVAL_PATH.exists(), f"Missing eval dataset at {EVAL_PATH}"
    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    agent = IntentClassificationAgent()
    for case in cases:
        result = await agent.run({"user_message": case["input"]})
        assert result.data["intent"] == case["expected_intent"], case["id"]


@pytest.mark.asyncio
async def test_master_handoff_eval():
    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    master = MasterAgent()
    for case in cases:
        if not case["expected_handoff"]:
            continue
        result = await master.process(
            user_message=case["input"],
            session_id=f"eval-{case['id']}",
        )
        assert result.get("handoff_required") is True, case["id"]
