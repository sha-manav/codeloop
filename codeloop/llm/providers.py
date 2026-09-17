"""Providers: the only code that talks to an LLM API. Content-free logging; no retries beyond the SDK's."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from codeloop.llm.config import ModelParams


class LLMProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


@dataclass
class ProviderResponse:
    text: str
    parsed: dict[str, Any] | None
    model_served: str
    stop_reason: str
    latency_ms: int
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    request_id: str | None = None
    refusal_category: str | None = None
    raw_usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "parsed": self.parsed, "model_served": self.model_served,
            "stop_reason": self.stop_reason, "latency_ms": self.latency_ms, "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out, "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens, "request_id": self.request_id,
            "refusal_category": self.refusal_category, "raw_usage": self.raw_usage,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProviderResponse:
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})  # type: ignore[arg-type]


class Provider(Protocol):
    name: str

    def generate(self, system: str, user: str, schema: type[BaseModel], params: ModelParams) -> ProviderResponse: ...


class FakeProvider:
    """Deterministic provider for tests: `responder(system, user, schema, params) -> dict | str`."""

    name = "fake"

    def __init__(
        self,
        responder: Callable[[str, str, type[BaseModel], ModelParams], dict[str, Any] | str],
        *,
        model: str = "fake-model",
    ):
        self._responder = responder
        self.model = model
        self.calls: list[dict[str, Any]] = []

    def generate(self, system: str, user: str, schema: type[BaseModel], params: ModelParams) -> ProviderResponse:
        self.calls.append({"system": system, "user": user, "schema": schema.__name__, "model": params.model})
        out = self._responder(system, user, schema, params)
        text = out if isinstance(out, str) else json.dumps(out)
        parsed: dict[str, Any] | None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        return ProviderResponse(
            text=text, parsed=parsed if isinstance(parsed, dict) else None, model_served=self.model,
            stop_reason="end_turn", latency_ms=1, tokens_in=len(system) // 4 + len(user) // 4,
            tokens_out=len(text) // 4,
        )


class AnthropicProvider:
    """Claude API via the official SDK. Structured output through `messages.parse(output_format=schema)`."""

    name = "anthropic"

    def __init__(self, client: Any | None = None):
        import anthropic

        self._anthropic = anthropic
        self._client = client or anthropic.Anthropic()

    def _request_kwargs(self, system: str, user: str, schema: type[BaseModel], params: ModelParams) -> dict[str, Any]:
        system_block: dict[str, Any] = {"type": "text", "text": system}
        if params.cache_system_prompt:
            system_block["cache_control"] = {"type": "ephemeral"}
        kwargs: dict[str, Any] = {
            "model": params.model,
            "max_tokens": params.max_tokens,
            "messages": [{"role": "user", "content": user}],
            "output_format": schema,
        }
        if system:
            kwargs["system"] = [system_block]
        if params.effort:
            kwargs["output_config"] = {"effort": params.effort}
        if params.thinking == "adaptive":
            kwargs["thinking"] = {"type": "adaptive"}
        if params.temperature is not None:
            kwargs["temperature"] = params.temperature
        return kwargs

    def generate(self, system: str, user: str, schema: type[BaseModel], params: ModelParams) -> ProviderResponse:
        a = self._anthropic
        kwargs = self._request_kwargs(system, user, schema, params)
        t0 = time.perf_counter()
        try:
            resp = self._client.messages.parse(**kwargs)
        except a.NotFoundError as e:
            raise LLMProviderError(f"model or endpoint not found: {e.message}", status=404) from e
        except a.RateLimitError as e:
            raise LLMProviderError("rate limited", retryable=True, status=429) from e
        except a.APIStatusError as e:
            raise LLMProviderError(
                f"API error {e.status_code}: {e.message}", retryable=e.status_code >= 500, status=e.status_code
            ) from e
        except a.APIConnectionError as e:
            raise LLMProviderError(f"connection error: {e}", retryable=True) from e
        latency_ms = int((time.perf_counter() - t0) * 1000)
        usage = getattr(resp, "usage", None)
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        parsed_obj = getattr(resp, "parsed_output", None)
        parsed = parsed_obj.model_dump(mode="json") if isinstance(parsed_obj, BaseModel) else None
        refusal = None
        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            refusal = getattr(details, "category", None) if details else None
        return ProviderResponse(
            text=text, parsed=parsed, model_served=str(getattr(resp, "model", params.model)),
            stop_reason=str(resp.stop_reason), latency_ms=latency_ms,
            tokens_in=int(getattr(usage, "input_tokens", 0) or 0),
            tokens_out=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            cache_creation_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            request_id=getattr(resp, "_request_id", None), refusal_category=refusal,
            raw_usage=usage.model_dump() if isinstance(usage, BaseModel) else {},
        )
