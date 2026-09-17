"""Run traces (spec §4): one per encounter per run, written next to predictions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from codeloop.schemas.package import CodingPackage


class LLMCallTrace(BaseModel):
    prompt_name: str
    prompt_hash: str  # sha256 of the prompt file
    rendered_sha256: str = ""  # sha256 of the rendered system+user text
    response_hash: str
    model: str  # pinned model id
    served_model: str = ""  # model reported by the provider
    effort: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    latency_ms: int = 0
    seed: int | None = None  # provider-side seed; null when the provider has no seed parameter
    requested_seed: int | None = None  # run discriminator used in the cache key
    cache_hit: bool = False
    validation_retries: int = 0
    stop_reason: str = ""
    request_id: str | None = None


class StageTrace(BaseModel):
    name: str
    input_hash: str
    output: Any = None  # structured stage output (JSON-serializable)
    llm_calls: list[LLMCallTrace] = Field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    notes: list[str] = Field(default_factory=list)


class Trace(BaseModel):
    encounter_id: str
    version: str
    run_id: str
    models_hash: str
    scope_hash: str
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    tables_hash: str = ""
    stages: list[StageTrace] = Field(default_factory=list)
    package: CodingPackage
    started_at: str
    finished_at: str
