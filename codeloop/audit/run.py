"""`codeloop audit run`: one structured LLM call per dev encounter; results to runs/audit/results.jsonl."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeloop.audit.schema import AuditResult
from codeloop.ingest.labels import locate
from codeloop.ledger import utc_now
from codeloop.llm.client import LLMClient
from codeloop.paths import Paths
from codeloop.schemas.encounter import Encounter
from codeloop.util.jsonl import read_jsonl, write_jsonl


def audit_dir(paths: Paths) -> Path:
    return paths.runs / "audit"


def results_path(paths: Paths) -> Path:
    return audit_dir(paths) / "results.jsonl"


@dataclass
class AuditRunSummary:
    run_id: str
    n_encounters: int
    n_flags: int
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_hits: int = 0
    validation_retries: int = 0
    failures: list[str] = field(default_factory=list)
    model: str = ""
    prompt_hash: str = ""
    per_category_flags: dict[str, int] = field(default_factory=dict)


def _span_for(enc: Encounter, quote: str | None, source: str | None) -> dict[str, Any] | None:
    if not quote or not source:
        return None
    text = enc.note_text if source == "note" else enc.dialogue_text
    loc = locate(text, quote)
    if loc is None:
        return None
    return {"source": source, "start": loc[0], "end": loc[1], "text": text[loc[0] : loc[1]]}


def audit_one(client: LLMClient, enc: Encounter, *, seed: int, run_id: str) -> dict[str, Any]:
    completion = client.complete(
        "audit",
        {"encounter_id": enc.id, "subset": enc.subset, "note_text": enc.note_text, "dialogue_text": enc.dialogue_text},
        AuditResult,
        seed=seed,
    )
    result: AuditResult = completion.parsed
    spans = [_span_for(enc, f.evidence_quote, f.evidence_source) for f in result.flags]
    patient_spans = {
        "age": _span_for(enc, result.patient.age_evidence, result.patient.age_source),
        "sex": _span_for(enc, result.patient.sex_evidence, result.patient.sex_source),
    }
    return {
        "encounter_id": enc.id,
        "subset": enc.subset,
        "run_id": run_id,
        "audited_at": utc_now(),
        "result": result.model_dump(mode="json"),
        "flag_spans": spans,
        "patient_spans": patient_spans,
        "llm": completion.trace.model_dump(mode="json"),
    }


def run_audit(
    paths: Paths,
    client: LLMClient,
    encounters: list[Encounter],
    *,
    seed: int = 1,
    concurrency: int = 4,
    run_id: str | None = None,
) -> AuditRunSummary:
    run_id = run_id or f"audit-{utc_now().replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:6]}"
    out = results_path(paths)
    existing: dict[str, dict[str, Any]] = {}
    if out.exists():
        existing = {r["encounter_id"]: r for r in read_jsonl(out)}
    summary = AuditRunSummary(run_id=run_id, n_encounters=0, n_flags=0, model=client.config.default.model)
    summary.prompt_hash = client.prompts.load("audit").file_sha256

    def work(enc: Encounter) -> tuple[str, dict[str, Any] | None, str | None]:
        try:
            return enc.id, audit_one(client, enc, seed=seed, run_id=run_id), None
        except Exception as e:  # noqa: BLE001 - recorded, never content
            return enc.id, None, f"{enc.id}: {type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for eid, record, err in pool.map(work, encounters):
            if err:
                summary.failures.append(err)
                continue
            assert record is not None
            existing[eid] = record
            summary.n_encounters += 1
            flags = record["result"]["flags"]
            summary.n_flags += len(flags)
            for f in flags:
                summary.per_category_flags[f["category"]] = summary.per_category_flags.get(f["category"], 0) + 1
            llm = record["llm"]
            summary.tokens_in += llm["tokens_in"]
            summary.tokens_out += llm["tokens_out"]
            summary.cache_read_tokens += llm["cache_read_tokens"]
            summary.cache_creation_tokens += llm["cache_creation_tokens"]
            summary.cache_hits += int(llm["cache_hit"])
            summary.validation_retries += llm["validation_retries"]
    write_jsonl(out, [existing[k] for k in sorted(existing)])
    return summary


def load_results(paths: Paths) -> dict[str, dict[str, Any]]:
    p = results_path(paths)
    if not p.exists():
        return {}
    return {r["encounter_id"]: r for r in read_jsonl(p)}
