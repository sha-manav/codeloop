"""Optional LLM pass (spec §11 step 3): proposes merges/splits of candidate findings. Output is a proposal."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from codeloop.findings.extract import load_existing
from codeloop.ledger import utc_now
from codeloop.llm.client import LLMClient
from codeloop.paths import Paths
from codeloop.review_ui.store import EventStore


class Proposal(BaseModel):
    kind: str  # merge | split | keep
    finding_ids: list[str]
    pattern: str
    rationale: str


class ClusterProposal(BaseModel):
    proposals: list[Proposal] = Field(default_factory=list)


def candidates_block(paths: Paths, batch: str, store: EventStore) -> str:
    events = {rid: e for rid, e in store.all()}
    lines = []
    for f in load_existing(paths):
        if f.batch_discovered != batch and batch not in f.batches_seen:
            continue
        examples = []
        for o in f.occurrences[:4]:
            for rid in o.event_ids[:2]:
                e = events.get(rid)
                if e is None:
                    continue
                before = (e.before or {}).get("code") if e.before else None
                after = (e.after or {}).get("code") if e.after else None
                examples.append(f"{e.type} {e.field_ref} before={before} after={after}")
        lines.append(
            f"- {f.id} [{f.status}] key={f.grouping_key} count={f.count}\n"
            f"    examples: {'; '.join(examples) or '(none)'}"
        )
    return "\n".join(lines) if lines else "(no candidates)"


def cluster_findings(paths: Paths, llm: LLMClient, *, batch: str, store: EventStore) -> Path:
    block = candidates_block(paths, batch, store)
    comp = llm.complete(
        "cluster_findings",
        {"batch": batch, "candidates_block": block},
        ClusterProposal,
        seed=1,
        call_site="cluster_findings",
    )
    out_dir = paths.findings / "proposals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{batch}.md"
    lines = [
        f"# Clustering proposal for {batch}",
        "",
        f"Generated {utc_now()} by {comp.trace.model} (prompt {comp.trace.prompt_hash[:12]}…). "
        "This is a proposal; the owner applies merges/splits by editing findings/*.yaml at triage.",
        "",
        "| kind | findings | pattern | rationale |",
        "|---|---|---|---|",
    ]
    for p in comp.parsed.proposals:
        lines.append(f"| {p.kind} | {', '.join(p.finding_ids)} | {p.pattern} | {p.rationale} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
