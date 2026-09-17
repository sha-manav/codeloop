import json

import pytest
from pydantic import BaseModel

from codeloop.llm import (
    FakeProvider,
    LLMCache,
    LLMClient,
    LLMRefusalError,
    LLMValidationError,
    PromptStore,
    load_models_config,
)
from codeloop.llm.providers import LLMProviderError, ProviderResponse
from tests.synthetic import REAL_ROOT


class Out(BaseModel):
    answer: str
    n: int


def _client(tmp_path, responder, cache=True):
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "q.txt").write_text("=== SYSTEM ===\nsys\n=== USER ===\nq: {{q}}", encoding="utf-8")
    config = load_models_config(REAL_ROOT / "config" / "models.yaml")
    provider = FakeProvider(responder)
    return LLMClient(config, PromptStore(tmp_path / "prompts"), provider=provider, cache=LLMCache(None) if cache else None, cache_enabled=cache), provider


def test_complete_validates_and_traces(tmp_path):
    client, provider = _client(tmp_path, lambda s, u, schema, p: {"answer": u, "n": 1})
    c = client.complete("q", {"q": "hello"}, Out, seed=1)
    assert c.parsed == Out(answer="q: hello", n=1)
    t = c.trace
    assert t.prompt_name == "q" and len(t.prompt_hash) == 64 and len(t.rendered_sha256) == 64
    assert t.model == "claude-opus-5" and t.served_model == "fake-model" and t.requested_seed == 1 and t.seed is None
    assert t.cache_hit is False and t.validation_retries == 0 and t.effort == "high"
    assert provider.calls[0]["system"] == "sys"


def test_cache_hit_miss_semantics(tmp_path):
    client, provider = _client(tmp_path, lambda s, u, schema, p: {"answer": "a", "n": 1})
    client.complete("q", {"q": "x"}, Out, seed=1)
    hit = client.complete("q", {"q": "x"}, Out, seed=1)
    assert hit.trace.cache_hit and len(provider.calls) == 1
    client.complete("q", {"q": "x"}, Out, seed=2)  # different requested seed -> miss
    client.complete("q", {"q": "y"}, Out, seed=1)  # different prompt -> miss
    assert len(provider.calls) == 3 and client.cache.hits == 1 and client.cache.misses == 3

    class Out2(BaseModel):
        answer: str
        n: int
        extra: bool = False

    client.complete("q", {"q": "x"}, Out2, seed=1)  # different schema -> miss
    assert len(provider.calls) == 4


def test_cache_disabled_calls_every_time(tmp_path):
    client, provider = _client(tmp_path, lambda s, u, schema, p: {"answer": "a", "n": 1}, cache=False)
    client.complete("q", {"q": "x"}, Out, seed=1)
    client.complete("q", {"q": "x"}, Out, seed=1)
    assert len(provider.calls) == 2


def test_one_retry_on_validation_failure_then_error(tmp_path):
    answers = iter(["not json", {"answer": "ok", "n": 2}])
    client, provider = _client(tmp_path, lambda *_: next(answers))
    c = client.complete("q", {"q": "x"}, Out, seed=1)
    assert c.parsed.n == 2 and c.trace.validation_retries == 1 and len(provider.calls) == 2
    client2, provider2 = _client(tmp_path, lambda *_: {"answer": "missing n"})
    with pytest.raises(LLMValidationError):
        client2.complete("q", {"q": "x"}, Out, seed=1)
    assert len(provider2.calls) == 2


def test_refusal_and_provider_errors(tmp_path):
    class Refusing:
        name = "fake"

        def generate(self, system, user, schema, params):
            return ProviderResponse(text="", parsed=None, model_served="m", stop_reason="refusal", latency_ms=1, refusal_category="bio")

    config = load_models_config(REAL_ROOT / "config" / "models.yaml")
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "q.txt").write_text("q {{q}}", encoding="utf-8")
    client = LLMClient(config, PromptStore(tmp_path / "prompts"), provider=Refusing(), cache=LLMCache(None))
    with pytest.raises(LLMRefusalError) as ei:
        client.complete("q", {"q": "x"}, Out, seed=1)
    assert ei.value.category == "bio" and len(client.cache) == 0

    class Flaky:
        name = "fake"
        calls = 0

        def generate(self, system, user, schema, params):
            self.calls += 1
            if self.calls < 3:
                raise LLMProviderError("rate limited", retryable=True, status=429)
            return ProviderResponse(text=json.dumps({"answer": "a", "n": 1}), parsed={"answer": "a", "n": 1}, model_served="m", stop_reason="end_turn", latency_ms=1)

    flaky = Flaky()
    client = LLMClient(config, PromptStore(tmp_path / "prompts"), provider=flaky, cache=LLMCache(None), retry_backoff_s=0.0)
    assert client.complete("q", {"q": "x"}, Out, seed=1).parsed.n == 1 and flaky.calls == 3

    class Broken:
        name = "fake"

        def generate(self, system, user, schema, params):
            raise LLMProviderError("bad request", retryable=False, status=400)

    client = LLMClient(config, PromptStore(tmp_path / "prompts"), provider=Broken(), cache=LLMCache(None), retry_backoff_s=0.0)
    with pytest.raises(LLMProviderError):
        client.complete("q", {"q": "x"}, Out, seed=1)


def test_models_config_pins_and_overrides():
    config = load_models_config(REAL_ROOT / "config" / "models.yaml")
    assert config.default.model == "claude-opus-5" and config.default.temperature is None and config.default.seeds == [1, 2, 3]
    assert config.params_for("cluster_findings").effort == "medium" and config.params_for("audit").effort == "high"
    assert config.pricing["claude-opus-5"].cost(1_000_000, 0) == 5.0 and len(config.source_sha256) == 64


def test_anthropic_request_shape():
    from codeloop.llm.config import ModelParams
    from codeloop.llm.providers import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    kwargs = provider._request_kwargs("sys", "usr", Out, ModelParams(model="claude-opus-5"))
    assert kwargs["model"] == "claude-opus-5" and kwargs["output_format"] is Out and "temperature" not in kwargs
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"} and kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"] == {"effort": "high"} and kwargs["max_tokens"] == 16000
