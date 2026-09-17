"""`codeloop labels build --batch B --version vK`: replay events into data/labels/<batch>.jsonl."""

from __future__ import annotations

from dataclasses import dataclass, field

from codeloop.ledger import append_entry
from codeloop.paths import Paths
from codeloop.review_ui.replay import replay, status_of
from codeloop.review_ui.store import EventStore
from codeloop.util.hashing import sha256_file
from codeloop.util.jsonl import read_jsonl, write_jsonl
from codeloop.versioning.freeze import load_dev_split


class LabelsError(RuntimeError):
    pass


@dataclass
class LabelsBuildResult:
    batch: str
    version: str
    approved: int
    pending: list[str] = field(default_factory=list)
    labels_path: str = ""
    events_path: str = ""
    coders: list[str] = field(default_factory=list)


def build_labels(
    paths: Paths, *, batch: str, version: str, store: EventStore | None = None, actor: str | None = None
) -> LabelsBuildResult:
    d = paths.review_dir(version, batch)
    store = store or (EventStore(d / "events.sqlite") if (d / "events.sqlite").exists() else None)
    if store is None:
        raise LabelsError(f"no event store for {version}/{batch}; run `codeloop review serve` first")
    split = load_dev_split(paths)
    ids = list(split["sets"][batch])
    pred_path = paths.runs / version / batch / "predictions.jsonl"
    drafts = {r["encounter_id"]: r for r in read_jsonl(pred_path)} if pred_path.exists() else {}
    records = []
    pending = []
    coders: set[str] = set()
    for eid in ids:
        events = store.for_encounter(eid)
        if status_of(events) != "approved":
            pending.append(eid)
            continue
        coder = events[-1].coder_id
        coders.add(coder)
        rec = replay(eid, coder, drafts.get(eid), events)
        blind = eid in set(split.get("blind", {}).get(batch, []))
        records.append({**rec.model_dump(mode="json"), "version_reviewed": version, "blind_subset": blind})
    out = paths.labels_file(batch)
    write_jsonl(out, records)
    events_path = d / "events.jsonl"
    store.export_jsonl(events_path)
    append_entry(paths.ledger, f"labels build {batch}", {
        "version_reviewed": version, "approved": len(records), "pending": len(pending), "coders": sorted(coders),
        "labels_sha256": sha256_file(out), "events_sha256": sha256_file(events_path),
        "mean_touches": round(sum(r["touches"] for r in records) / len(records), 3) if records else None,
        "mean_review_minutes": round(sum(r["review_minutes"] for r in records) / len(records), 3) if records else None,
    }, actor=actor)
    return LabelsBuildResult(
        batch=batch, version=version, approved=len(records), pending=pending,
        labels_path=out.relative_to(paths.root).as_posix(), events_path=events_path.relative_to(paths.root).as_posix(),
        coders=sorted(coders),
    )
