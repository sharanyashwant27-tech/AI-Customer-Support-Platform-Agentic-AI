"""Local Llama (OpenAI-compatible) LLM adapter — works with Ollama/vLLM."""

from typing import Any

from openai import AsyncOpenAI

from app.llm.base import BaseLLMAdapter, LLMMessage, LLMProvider, LLMResponse
from app.observability.metrics import LLM_TOKENS_TOTAL


class LlamaAdapter(BaseLLMAdapter):
    provider = LLMProvider.LLAMA

    def __init__(self, base_url: str, model: str, api_key: str = "ollama") -> None:
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        choice = response.choices[0].message
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        LLM_TOKENS_TOTAL.labels(
            provider="llama", model=self.model, token_type="prompt"
        ).inc(prompt_tokens)
        LLM_TOKENS_TOTAL.labels(
            provider="llama", model=self.model, token_type="completion"
        ).inc(completion_tokens)
        return LLMResponse(
            content=choice.content or "",
            provider=self.provider,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def health_check(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False
