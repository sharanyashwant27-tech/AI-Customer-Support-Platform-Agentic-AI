"""Prompt registry — system prompts, few-shot tuning, A/B assignment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.prompts.loader import PromptTemplate, default_prompts_dir, load_prompt

logger = get_logger(__name__)

SYSTEM_ALWAYS_RULES = [
    "Be polite.",
    "Use retrieved knowledge.",
    "Never hallucinate.",
    "If confidence <90%, ask clarification.",
    "Escalate when required.",
    "Summarize conversation.",
    "Suggest next best action.",
]


class PromptRegistry:
    def __init__(self, prompts_dir: Path | None = None) -> None:
        self.prompts_dir = prompts_dir or default_prompts_dir()
        self._cache: dict[str, PromptTemplate] = {}
        self._experiments: dict[str, dict[str, Any]] = {}
        self._load_all()
        self._load_experiments()

    def _load_all(self) -> None:
        if not self.prompts_dir.exists():
            alt = Path("/sample_prompts")
            if alt.exists():
                self.prompts_dir = alt
        if not self.prompts_dir.exists():
            logger.warning("prompts_dir_missing", path=str(self.prompts_dir))
            return
        for path in self.prompts_dir.glob("*.json"):
            if path.name.startswith("experiment_"):
                continue
            try:
                tmpl = load_prompt(path)
                self._cache[tmpl.name] = tmpl
                self._cache[f"{tmpl.name}@{tmpl.version}"] = tmpl
            except Exception as exc:
                logger.warning("prompt_load_failed", path=str(path), error=str(exc))

    def _load_experiments(self) -> None:
        exp_path = self.prompts_dir / "experiment_master_ab.json"
        if not exp_path.exists():
            self._experiments["master_system"] = {
                "name": "master_system_ab",
                "variants": ["master_system", "master_system_b"],
                "weights": [0.5, 0.5],
            }
            return
        try:
            self._experiments = json.loads(exp_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("experiment_load_failed", error=str(exc))

    def get(self, name: str, version: str | None = None) -> PromptTemplate | None:
        if version:
            return self._cache.get(f"{name}@{version}") or self._cache.get(name)
        return self._cache.get(name)

    def assign_variant(self, experiment: str, session_id: str) -> str:
        exp = self._experiments.get(experiment)
        if not exp:
            return experiment
        variants: list[str] = exp.get("variants") or [experiment]
        weights: list[float] = exp.get("weights") or [1.0] * len(variants)
        digest = hashlib.sha256(f"{experiment}:{session_id}".encode()).hexdigest()
        bucket = int(digest[:8], 16) / 0xFFFFFFFF
        cumulative = 0.0
        total = sum(weights) or 1.0
        for variant, weight in zip(variants, weights, strict=False):
            cumulative += weight / total
            if bucket <= cumulative:
                return variant
        return variants[-1]

    def render_master_system(
        self,
        *,
        session_id: str,
        app_name: str,
        intent: str,
        sentiment: str,
        confidence: float,
        handoff_threshold: float,
        clarification_threshold: float = 0.9,
        context_block: str = "",
        memory_block: str = "",
    ) -> tuple[str, str, PromptTemplate | None]:
        """
        Build the system prompt for the AI Customer Support Specialist.

        Returns (system_text, variant_name, template).
        """
        variant = self.assign_variant("master_system", session_id)
        tmpl = self.get(variant) or self.get("master_system")
        if tmpl is None:
            rules = "\n".join(f"- {r}" for r in SYSTEM_ALWAYS_RULES)
            text = (
                f"You are an AI Customer Support Specialist for {app_name}.\n\n"
                f"Always:\n{rules}\n\n"
                f"Intent={intent}, sentiment={sentiment}, confidence={confidence}. "
                f"Ask clarification if confidence < {clarification_threshold}."
            )
            if memory_block:
                text += f"\n\nMemory:\n{memory_block}"
            if context_block:
                text += f"\n\nContext:\n{context_block}"
            return text, "inline", None

        threshold = tmpl.clarification_threshold()
        if clarification_threshold:
            threshold = clarification_threshold

        rendered = tmpl.render(
            app_name=app_name,
            intent=intent,
            sentiment=sentiment,
            confidence=confidence,
            handoff_threshold=handoff_threshold,
            clarification_threshold=threshold,
        )
        few_shot = tmpl.format_few_shot(intent=intent)
        # Merge dedicated billing few-shot when intent is billing/ticket
        if intent in {"ticket", "billing", "complaint"}:
            billing = self.get("few_shot_billing")
            if billing:
                extra = billing.format_few_shot(intent="billing", limit=1)
                if extra and extra not in few_shot:
                    few_shot = f"{extra}\n\n{few_shot}".strip() if few_shot else extra

        if few_shot:
            rendered = f"{rendered}\n\nFew-shot examples (prompt tuning):\n{few_shot}"
        if memory_block:
            rendered = f"{rendered}\n\nCustomer memory:\n{memory_block}"
        if context_block:
            rendered = f"{rendered}\n\nRetrieved / specialist context:\n{context_block}"
        return rendered, variant, tmpl


_registry: PromptRegistry | None = None


def get_prompt_registry() -> PromptRegistry:
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry


def reset_prompt_registry() -> None:
    global _registry
    _registry = None


class PromptOptimizer:
    """Lightweight automatic optimization using feedback ratings."""

    def __init__(self) -> None:
        self.scores: dict[str, list[int]] = {}

    def record(self, variant: str, rating: int) -> None:
        self.scores.setdefault(variant, []).append(rating)

    def best_variant(self, candidates: list[str]) -> str:
        best = candidates[0]
        best_avg = -1.0
        for name in candidates:
            vals = self.scores.get(name) or []
            if not vals:
                continue
            avg = sum(vals) / len(vals)
            if avg > best_avg:
                best_avg = avg
                best = name
        return best

    def suggest_weights(self, candidates: list[str]) -> list[float]:
        avgs = []
        for name in candidates:
            vals = self.scores.get(name) or [3]
            avgs.append(sum(vals) / len(vals))
        total = sum(avgs) or 1.0
        return [a / total for a in avgs]


prompt_optimizer = PromptOptimizer()
