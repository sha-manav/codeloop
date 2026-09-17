"""Provider-agnostic LLM client (spec §6): `complete(prompt_name, variables, schema, seed) -> Completion`.

Hashes the rendered prompt, validates the response against the Pydantic schema (one retry on
validation failure), records tokens and latency, and uses the SQLite cache keyed on
(model, params, rendered_prompt_sha256, seed, schema). Never logs prompt or response content.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from codeloop.llm.cache import LLMCache, cache_key
from codeloop.llm.config import ModelsConfig
from codeloop.llm.prompts import PromptStore, rendered_sha256
from codeloop.llm.providers import AnthropicProvider, FakeProvider, LLMProviderError, Provider, ProviderResponse
from codeloop.schemas.trace import LLMCallTrace
from codeloop.util.hashing import sha256_text

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMValidationError(LLMError):
    pass


class LLMRefusalError(LLMError):
    def __init__(self, message: str, category: str | None):
        super().__init__(message)
        self.category = category


@dataclass
class Completion:
    parsed: Any
    trace: LLMCallTrace
    response: ProviderResponse


def schema_sha256(schema: type[BaseModel]) -> str:
    return sha256_text(json.dumps(schema.model_json_schema(), sort_keys=True))


class LLMClient:
    def __init__(
        self,
        config: ModelsConfig,
        prompts: PromptStore,
        *,
        provider: Provider | None = None,
        cache: LLMCache | None = None,
        cache_enabled: bool = True,
        max_provider_retries: int = 2,
        retry_backoff_s: float = 2.0,
    ):
        self.config = config
        self.prompts = prompts
        self.cache = cache
        self.cache_enabled = cache_enabled and cache is not None
        self.max_provider_retries = max_provider_retries
        self.retry_backoff_s = retry_backoff_s
        self._provider = provider

    @property
    def provider(self) -> Provider:
        if self._provider is None:
            name = self.config.default.provider
            if name == "anthropic":
                self._provider = AnthropicProvider()
            elif name == "fake":
                self._provider = FakeProvider(lambda *_: "{}")
            else:  # pragma: no cover
                raise LLMError(f"unknown provider {name!r}")
        return self._provider

    @property
    def models_hash(self) -> str:
        return self.config.source_sha256 or ""

    def _call_provider(self, system: str, user: str, schema: type[BaseModel], params) -> ProviderResponse:
        attempt = 0
        while True:
            try:
                return self.provider.generate(system, user, schema, params)
            except LLMProviderError as e:
                attempt += 1
                if not e.retryable or attempt > self.max_provider_retries:
                    raise
                time.sleep(self.retry_backoff_s * attempt)

    def complete(
        self,
        prompt_name: str,
        variables: dict[str, Any],
        schema: type[T],
        *,
        seed: int | None = None,
        call_site: str | None = None,
    ) -> Completion:
        prompt = self.prompts.load(prompt_name)
        system, user = prompt.render(variables)
        params = self.config.params_for(call_site or prompt_name)
        rendered = rendered_sha256(system, user)
        s_hash = schema_sha256(schema)
        key = cache_key(params.model, params.cache_fields(), rendered, seed, s_hash)

        cache_hit = False
        retries = 0
        response: ProviderResponse | None = None
        parsed: T | None = None
        if self.cache_enabled and self.cache is not None:
            rec = self.cache.get(key)
            if rec is not None:
                response = ProviderResponse.from_dict(rec.response)
                cache_hit = True
                payload = response.parsed if response.parsed is not None else json.loads(response.text)
                parsed = schema.model_validate(payload)
        if response is None or parsed is None:
            while True:
                response = self._call_provider(system, user, schema, params)
                if response.stop_reason == "refusal":
                    raise LLMRefusalError(
                        f"{prompt_name}: model refused (category={response.refusal_category})",
                        response.refusal_category,
                    )
                try:
                    payload = response.parsed if response.parsed is not None else json.loads(response.text or "")
                    parsed = schema.model_validate(payload)
                    break
                except (ValidationError, json.JSONDecodeError, TypeError) as e:
                    if retries >= 1:
                        raise LLMValidationError(
                            f"{prompt_name}: response failed schema validation after retry: {type(e).__name__}"
                        ) from e
                    retries += 1
            if self.cache_enabled and self.cache is not None:
                self.cache.put(
                    key, model=params.model, params=params.cache_fields(), prompt_sha256=rendered, seed=seed,
                    schema_name=schema.__name__, response=response.to_dict(),
                )
        assert response is not None and parsed is not None
        trace = LLMCallTrace(
            prompt_name=prompt_name, prompt_hash=prompt.file_sha256, rendered_sha256=rendered,
            response_hash=sha256_text(response.text or json.dumps(response.parsed, sort_keys=True)),
            model=params.model, served_model=response.model_served, effort=params.effort,
            tokens_in=response.tokens_in, tokens_out=response.tokens_out,
            cache_read_tokens=response.cache_read_tokens, cache_creation_tokens=response.cache_creation_tokens,
            latency_ms=response.latency_ms, seed=None, requested_seed=seed, cache_hit=cache_hit,
            validation_retries=retries, stop_reason=response.stop_reason, request_id=response.request_id,
        )
        return Completion(parsed=parsed, trace=trace, response=response)


def build_client(
    root: Path, *, provider: Provider | None = None, cache_enabled: bool = True, cache_path: Path | None = None
) -> LLMClient:
    """Standard wiring: config/models.yaml, prompts/, .cache/llm_cache.sqlite."""
    from codeloop.llm.config import load_models_config

    config = load_models_config(root / "config" / "models.yaml")
    prompts = PromptStore(root / "prompts")
    cache = None
    if cache_enabled:
        cache = LLMCache(cache_path if cache_path is not None else root / ".cache" / "llm_cache.sqlite")
    return LLMClient(config, prompts, provider=provider, cache=cache, cache_enabled=cache_enabled)
