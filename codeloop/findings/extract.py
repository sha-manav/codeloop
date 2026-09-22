"""`codeloop findings extract --batch B` (spec §11): group coder corrections into candidate findings."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from codeloop.config import ProjectConfig
from codeloop.paths import Paths
from codeloop.review_ui.replay import ineffective_touch_ids
from codeloop.review_ui.store import EventStore
from codeloop.schemas.event import Event
from codeloop.schemas.field_ref import parse_field_ref
from codeloop.schemas.finding import Finding, Occurrence
from codeloop.scoring import Scope
from codeloop.util.jsonl import read_jsonl

MODULE_TAG = {
    "core_dx": "DX",
    "core_lines": "LINES",
    "vaccine_admin": "VAX",
    "distinct_59x": "MOD59",
    "qw": "QW",
    "jw_jz": "JWJZ",
}


@dataclass
class Group:
    key: str
    reason: str
    field_type: str
    module: str
    code_category: str
    occurrences: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    field_refs: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    sample_refs: list[str] = field(default_factory=list)


def grouping_key(event: Event, scope: Scope) -> tuple[str, str, str, str] | None:
    if (
        event.type not in ("edit", "add", "remove")
        or event.mode != "review"
        or not event.reason
        or event.reason == "judgment"
    ):
        return None
    if not event.field_ref:
        return None
    try:
        ref = parse_field_ref(event.field_ref)
    except ValueError:
        return None
    if ref.kind == "dx":
        field_type = "dx"
        module = "core_dx"
        code = (event.after or {}).get("code") if event.type == "add" else ref.code
        code = str(code or ref.code or "").upper().replace(".", "")
        category = code[:3]
    elif ref.kind == "line":
        field_type = ref.sub or "line"
        code = str(((event.after or {}).get("code") if event.type == "add" else ref.code) or "").upper()
        module = scope.module_for_line(code) or "core_lines"
        category = next((r for m in scope.modules.values() for r in m.code_ranges if _in_range(code, r)), code)
    elif ref.kind == "first_listed":
        field_type, module, category = "first_listed", "core_dx", "first_listed"
    else:
        return None
    return event.reason, field_type, module, category


def _in_range(code: str, spec: str) -> bool:
    lo, _, hi = spec.partition("-")
    hi = hi or lo
    return lo <= code <= hi


def ineffective_ids(paths: Paths, events: list[tuple[int, Event]]) -> set[int]:
    """Ids of edit/add/remove events that changed nothing when replayed over the draft they were made on (an Edit
    pressed on unchanged values still carries a reason, but there is no correction behind it). Encounters whose
    draft cannot be found are left alone."""
    by_enc: dict[str, list[tuple[int, Event]]] = defaultdict(list)
    for rid, e in events:
        by_enc[e.encounter_id].append((rid, e))
    drafts: dict[tuple[str, str], dict[str, dict]] = {}
    out: set[int] = set()
    for eid, evs in by_enc.items():
        key = (evs[0][1].version, evs[0][1].batch)
        if key not in drafts:
            path = paths.runs / key[0] / key[1] / "predictions.jsonl"
            drafts[key] = {r["encounter_id"]: r for r in read_jsonl(path)} if path.exists() else {}
        if eid in drafts[key]:
            out |= ineffective_touch_ids(drafts[key][eid], evs)
    return out


def group_events(
    events: list[tuple[int, Event]], scope: Scope, skip: set[int] | frozenset[int] = frozenset()
) -> dict[str, Group]:
    groups: dict[str, Group] = {}
    for eid_num, e in events:
        key = grouping_key(e, scope) if eid_num not in skip else None
        if key is None:
            continue
        reason, field_type, module, category = key
        k = f"{reason}|{field_type}|{module}|{category}"
        g = groups.setdefault(
            k, Group(key=k, reason=reason, field_type=field_type, module=module, code_category=category)
        )
        g.occurrences[e.encounter_id].append(eid_num)
        g.field_refs[e.encounter_id].add(e.field_ref or "")
    return groups


def load_existing(paths: Paths) -> list[Finding]:
    out = []
    for p in sorted(paths.findings.glob("FIND-*.yaml")):
        with open(p, encoding="utf-8") as fh:
            out.append(Finding.model_validate(yaml.safe_load(fh)))
    return out


def next_number(existing: list[Finding], tag: str) -> int:
    nums = [int(m.group(1)) for f in existing if (m := re.match(rf"FIND-{tag}-(\d+)$", f.id))]
    return (max(nums) + 1) if nums else 1


def save_finding(paths: Paths, f: Finding) -> Path:
    p = paths.findings / f"{f.id}.yaml"
    p.write_text(yaml.safe_dump(f.model_dump(mode="json"), sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


def extract_findings(
    paths: Paths, config: ProjectConfig, *, batch: str, store: EventStore | None = None
) -> list[Finding]:
    labels = read_jsonl(paths.labels_file(batch)) if paths.labels_file(batch).exists() else []
    version = labels[0].get("version_reviewed") if labels else None
    if store is None:
        if version is None:
            raise RuntimeError(f"no labels for {batch}; run `codeloop labels build` first")
        jsonl = paths.review_dir(version, batch) / "events.jsonl"
        if not jsonl.exists():
            raise RuntimeError(f"{jsonl} missing; run `codeloop labels build --batch {batch}`")
        store = EventStore.from_jsonl(jsonl)
    scope = Scope.load(paths.scope_yaml)
    events = store.all()
    groups = group_events(events, scope, skip=ineffective_ids(paths, events))
    rule = config.decisions["D3"].value
    min_new, min_repeat = int(rule.get("in_batch", 3)), int(rule.get("if_seen_in_prior_batch", 2))
    existing = load_existing(paths)
    by_key = {f.grouping_key: f for f in existing if f.grouping_key}
    out: list[Finding] = []
    for k, g in sorted(groups.items()):
        n = len(g.occurrences)
        prior = by_key.get(k)
        # D3: the lower threshold applies only when the key was seen in an earlier batch; a finding this same run
        # created (or a re-run over the same batch) does not count as prior evidence
        seen_before = prior is not None and (
            prior.batch_discovered != batch or any(b != batch for b in prior.batches_seen)
        )
        threshold = min_repeat if seen_before else min_new
        occ = [Occurrence(encounter_id=eid, event_ids=sorted(ids)) for eid, ids in sorted(g.occurrences.items())]
        if prior is not None:
            seen = {o.encounter_id for o in prior.occurrences}
            prior.occurrences.extend(o for o in occ if o.encounter_id not in seen)
            prior.count = len({o.encounter_id for o in prior.occurrences})
            if prior.status in ("candidate", "eligible") and prior.batch_discovered == batch and not seen_before:
                prior.status = "eligible" if n >= threshold else "candidate"  # idempotent re-run of this batch
            elif prior.status == "candidate" and n >= threshold:
                prior.status = "eligible"
            prior.batches_seen = sorted(set(prior.batches_seen) | {batch})
            save_finding(paths, prior)
            out.append(prior)
            continue
        tag = MODULE_TAG.get(g.module, g.module.upper())
        fid = f"FIND-{tag}-{next_number(existing + out, tag):04d}"
        f = Finding(
            id=fid,
            title=f"{g.reason} corrections on {g.field_type} fields in {g.module} ({g.code_category})",
            batch_discovered=batch,
            status="eligible" if n >= threshold else "candidate",
            pattern=f"reason={g.reason}, field_type={g.field_type}, module={g.module}, code_category={g.code_category}",
            reasons=[g.reason],
            field_types=[g.field_type],
            module=g.module,
            code_category=g.code_category,
            grouping_key=k,
            occurrences=occ,
            count=n,
        )
        save_finding(paths, f)
        out.append(f)
    return out


def field_refs_for(store: EventStore, finding: Finding, scope: Scope) -> dict[str, list[str]]:
    """encounter_id -> field refs (for the targeted dataset), derived from the finding's events."""
    refs: dict[str, set[str]] = defaultdict(set)
    wanted = {(o.encounter_id, i) for o in finding.occurrences for i in o.event_ids}
    for eid_num, e in store.all():
        if (e.encounter_id, eid_num) in wanted and e.field_ref:
            ref = e.field_ref
            refs[e.encounter_id].add(_scorer_ref(ref))
            if e.type in ("add", "edit") and e.after and e.after.get("code"):
                code = str(e.after["code"]).upper().replace(".", "")
                new_ref = f"dx:{code}" if ref.startswith("dx") else f"line:{code}"
                refs[e.encounter_id].add(_scorer_ref(new_ref))
                if e.type == "add":
                    refs[e.encounter_id].discard(_scorer_ref(ref))
    return {k: sorted(v) for k, v in refs.items()}


def _scorer_ref(ref: str) -> str:
    """UI refs carry line indices always; the scorer only indexes when a code has several lines."""
    parts = ref.split(":")
    if parts[0] == "line" and len(parts) >= 3 and parts[2] == "0":
        return ":".join([parts[0], parts[1], *parts[3:]])
    if parts[0] == "dx" and len(parts) == 3 and parts[2] == "status":
        return f"dx:{parts[1]}"
    return ref
