"""Anthropic Claude LLM adapter."""

from typing import Any

from anthropic import AsyncAnthropic

from app.llm.base import BaseLLMAdapter, LLMMessage, LLMProvider, LLMResponse
from app.observability.metrics import LLM_TOKENS_TOTAL


class AnthropicAdapter(BaseLLMAdapter):
    provider = LLMProvider.ANTHROPIC

    def __init__(self, api_key: str, model: str) -> None:
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        system = "\n".join(m.content for m in messages if m.role == "system")
        chat_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        response = await self.client.messages.create(
            model=self.model,
            system=system or "You are a helpful customer support assistant.",
            messages=chat_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
        LLM_TOKENS_TOTAL.labels(
            provider="anthropic", model=self.model, token_type="prompt"
        ).inc(prompt_tokens)
        LLM_TOKENS_TOTAL.labels(
            provider="anthropic", model=self.model, token_type="completion"
        ).inc(completion_tokens)
        return LLMResponse(
            content=content,
            provider=self.provider,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def health_check(self) -> bool:
        return bool(self.client)
