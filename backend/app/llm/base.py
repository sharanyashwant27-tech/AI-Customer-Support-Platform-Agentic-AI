"""LLM provider adapter protocol and factory."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.exceptions import LLMProviderError


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    LLAMA = "llama"


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMResponse(BaseModel):
    content: str
    provider: LLMProvider
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)


class BaseLLMAdapter(ABC):
    """Interchangeable LLM backend adapter."""

    provider: LLMProvider

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class StubLLMAdapter(BaseLLMAdapter):
    """Deterministic stub used when API keys are not configured."""

    provider = LLMProvider.OPENAI

    def __init__(self, model: str = "stub-model") -> None:
        self.model = model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        user_msgs = [m.content for m in messages if m.role == "user"]
        last = user_msgs[-1] if user_msgs else ""
        reply = (
            "Thank you for contacting support. I've received your message: "
            f'"{last[:200]}". Our AI agents are initializing — '
            "full multi-agent orchestration will handle this shortly."
        )
        return LLMResponse(
            content=reply,
            provider=self.provider,
            model=self.model,
            prompt_tokens=0,
            completion_tokens=0,
        )

    async def health_check(self) -> bool:
        return True


def get_llm_adapter(
    provider: str | None = None,
    settings: Settings | None = None,
) -> BaseLLMAdapter:
    """Factory returning the configured LLM adapter (stub until keys are set)."""
    settings = settings or get_settings()
    chosen = provider or settings.default_llm_provider

    # Adapters are loaded lazily; fall back to stub when keys are missing.
    if chosen == LLMProvider.OPENAI.value and settings.openai_api_key:
        from app.llm.adapters.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(api_key=settings.openai_api_key, model=settings.openai_model)
    if chosen == LLMProvider.ANTHROPIC.value and settings.anthropic_api_key:
        from app.llm.adapters.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(
            api_key=settings.anthropic_api_key, model=settings.anthropic_model
        )
    if chosen == LLMProvider.GEMINI.value and settings.google_api_key:
        from app.llm.adapters.gemini_adapter import GeminiAdapter

        return GeminiAdapter(api_key=settings.google_api_key, model=settings.gemini_model)
    if chosen == LLMProvider.LLAMA.value:
        from app.llm.adapters.llama_adapter import LlamaAdapter

        return LlamaAdapter(base_url=settings.llama_base_url, model=settings.llama_model)

    return StubLLMAdapter(model=f"stub-{chosen}")


async def require_llm(provider: str | None = None) -> BaseLLMAdapter:
    adapter = get_llm_adapter(provider)
    if isinstance(adapter, StubLLMAdapter) and provider:
        raise LLMProviderError(
            f"LLM provider '{provider}' is not configured. Set the corresponding API key."
        )
    return adapter
