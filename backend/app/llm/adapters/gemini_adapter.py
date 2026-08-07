"""Google Gemini LLM adapter."""

from typing import Any

from app.llm.base import BaseLLMAdapter, LLMMessage, LLMProvider, LLMResponse
from app.observability.metrics import LLM_TOKENS_TOTAL


class GeminiAdapter(BaseLLMAdapter):
    provider = LLMProvider.GEMINI

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self._model = None

    def _ensure_client(self) -> Any:
        if self._model is None:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(self.model)
        return self._model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        model = self._ensure_client()
        prompt = "\n".join(f"{m.role}: {m.content}" for m in messages)
        # google-generativeai is sync; run in thread via to_thread when needed
        import asyncio

        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        content = getattr(response, "text", "") or ""
        LLM_TOKENS_TOTAL.labels(
            provider="gemini", model=self.model, token_type="completion"
        ).inc(len(content.split()))
        return LLMResponse(
            content=content,
            provider=self.provider,
            model=self.model,
        )

    async def health_check(self) -> bool:
        try:
            self._ensure_client()
            return True
        except Exception:
            return False
