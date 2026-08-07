"""Versioned prompt template loader with few-shot support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PromptTemplate(BaseModel):
    version: str
    name: str
    template: str
    description: str | None = None
    variables: list[str] = Field(default_factory=list)
    few_shot: list[dict[str, Any]] = Field(default_factory=list)
    always_rules: list[str] = Field(default_factory=list)
    guardrails: dict[str, Any] = Field(default_factory=dict)

    def render(self, **kwargs: Any) -> str:
        text = self.template
        for key, value in kwargs.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))
        return text

    def format_few_shot(self, *, intent: str | None = None, limit: int = 2) -> str:
        """Render few-shot examples for prompt tuning."""
        examples = list(self.few_shot or [])
        if intent:
            intent_l = intent.lower()
            preferred = [
                ex
                for ex in examples
                if intent_l in str(ex.get("detect") or "").lower()
                or intent_l in str(ex.get("id") or "").lower()
            ]
            if preferred:
                examples = preferred + [e for e in examples if e not in preferred]
        parts: list[str] = []
        for ex in examples[:limit]:
            flow = ex.get("flow")
            flow_txt = ""
            if isinstance(flow, list) and flow:
                flow_txt = "\nFlow: " + " → ".join(str(s) for s in flow)
            detect = ex.get("detect")
            retrieve = ex.get("retrieve")
            meta = ""
            if detect or retrieve:
                meta = f"\nDetect: {detect or '—'} | Retrieve: {retrieve or '—'}"
            parts.append(
                f"Customer: {ex.get('user', '')}{meta}{flow_txt}\n"
                f"Specialist: {ex.get('assistant', '')}"
            )
        return "\n\n".join(parts)

    def clarification_threshold(self) -> float:
        raw = self.guardrails.get("clarification_threshold")
        if raw is None:
            raw = self.guardrails.get("confidence_threshold", 0.9)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.9


def load_prompt(path: Path) -> PromptTemplate:
    data = json.loads(path.read_text(encoding="utf-8"))
    return PromptTemplate(**data)


def default_prompts_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "sample_prompts"
