"""Span location for LLM quotes and prompt-block rendering (content goes to the model, never to logs)."""

from __future__ import annotations

from codeloop.ingest.labels import locate
from codeloop.schemas.encounter import Encounter
from codeloop.schemas.package import Span


def spans_for_quotes(
    encounter: Encounter, note_quotes: list[str], dialogue_quotes: list[str]
) -> tuple[list[Span], list[Span], int]:
    """Locate verbatim quotes; returns (note spans, dialogue spans, number of quotes that could not be located)."""
    note: list[Span] = []
    dialogue: list[Span] = []
    missing = 0
    seen: set[tuple[str, int, int]] = set()
    for source, quotes, text, bucket in (
        ("note", note_quotes, encounter.note_text, note),
        ("dialogue", dialogue_quotes, encounter.dialogue_text, dialogue),
    ):
        for q in quotes:
            loc = locate(text, q)
            if loc is None:
                missing += 1
                continue
            key = (source, loc[0], loc[1])
            if key in seen:
                continue
            seen.add(key)
            bucket.append(Span.from_source(source, text, loc[0], loc[1]))  # type: ignore[arg-type]
    return note, dialogue, missing


def _q(spans: list[Span], limit: int = 3) -> str:
    return " | ".join(f'"{s.text}"' for s in spans[:limit]) or "(none)"


def problems_block(problems, note_spans: list[list[Span]], dialogue_spans: list[list[Span]], candidates=None) -> str:
    lines = []
    for i, p in enumerate(problems):
        lines.append(
            f"[{i}] {p.description}; status: {p.status}; laterality: {p.laterality}; qualifiers: {p.qualifiers or []}"
        )
        lines.append(f"    note evidence: {_q(note_spans[i])}")
        lines.append(f"    transcript evidence: {_q(dialogue_spans[i])}")
        if candidates is not None:
            cands = candidates[i]
            if cands:
                lines.append("    candidates: " + "; ".join(f"{c.code} — {c.description}" for c in cands))
            else:
                lines.append("    candidates: (none retrieved)")
    return "\n".join(lines) if lines else "(no problems extracted)"


def services_block(services, note_spans: list[list[Span]], allowed_ranges: dict[int, list[str]]) -> str:
    lines = []
    for i, s in enumerate(services):
        if i not in allowed_ranges:
            continue
        lines.append(
            f"[{i}] category: {s.category}; description: {s.description}; body part: {s.body_part}; "
            f"laterality: {s.laterality}; views: {s.views}"
        )
        lines.append(f"    note evidence: {_q(note_spans[i])}")
        lines.append(f"    allowed code ranges: {', '.join(allowed_ranges[i]) or '(none)'}")
    return "\n".join(lines) if lines else "(no mappable services)"
