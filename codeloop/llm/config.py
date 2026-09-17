"""config/models.yaml: pinned provider, model and sampling settings per call site."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from codeloop.util.hashing import sha256_file


class ModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["anthropic", "fake"] = "anthropic"
    model: str
    temperature: float | None = None
    seeds: list[int] = Field(default_factory=lambda: [1, 2, 3])
    max_tokens: int = 16000
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = "high"
    thinking: Literal["adaptive", "off"] = "adaptive"
    fallbacks: Literal["none", "default"] = "none"
    cache_system_prompt: bool = True

    def cache_fields(self) -> dict[str, Any]:
        """The parameters that change model behaviour and therefore the cache key."""
        return {
            "provider": self.provider, "model": self.model, "temperature": self.temperature,
            "max_tokens": self.max_tokens, "effort": self.effort, "thinking": self.thinking,
        }


class Pricing(BaseModel):
    """USD per 1M tokens; used only for cost estimates in reports and the ledger."""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0

    def cost(self, tokens_in: int, tokens_out: int, cache_read: int = 0, cache_write: int = 0) -> float:
        return (
            tokens_in * self.input
            + tokens_out * self.output
            + cache_read * self.cache_read
            + cache_write * self.cache_write
        ) / 1_000_000


class ModelsConfig(BaseModel):
    default: ModelParams
    call_sites: dict[str, dict[str, Any]] = Field(default_factory=dict)
    pricing: dict[str, Pricing] = Field(default_factory=dict)
    source_sha256: str | None = None

    def params_for(self, call_site: str) -> ModelParams:
        override = self.call_sites.get(call_site) or {}
        return self.default.model_copy(update=override)


def load_models_config(path: Path) -> ModelsConfig:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    cfg = ModelsConfig.model_validate(raw)
    cfg.source_sha256 = sha256_file(path)
    return cfg
