"""`codeloop export labels --release` (spec §16): the ACI-Bench-Claims file.

One record per CPC-labeled dev encounter: encounter id, canonical codes only (no descriptors), evidence
spans as offsets into the released texts (from the accepted draft fields), and a single-coder disclosure.
Holdout encounters are never exported before the holdout is scored and never by this command.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codeloop.config import ProjectConfig
from codeloop.paths import Paths
from codeloop.scoring import Scope, canonicalize
from codeloop.util.jsonl import read_jsonl, write_jsonl

ALLOWED_LICENSES = ("CC BY 4.0",)


class ExportError(RuntimeError):
    pass


def license_check(config: ProjectConfig) -> str:
    lic = config.sources["aci_bench"].license
    if not any(lic.startswith(a) for a in ALLOWED_LICENSES):
        raise ExportError(f"ACI-Bench license {lic!r} does not permit redistribution of derived labels without review")
    return lic


def export_release(paths: Paths, config: ProjectConfig, *, out: Path | None = None) -> tuple[Path, int]:
    lic = license_check(config)
    scope = Scope.load(paths.scope_yaml)
    holdout = set(paths.holdout_ids.read_text().split()) if paths.holdout_ids.exists() else set()
    records: list[dict[str, Any]] = []
    for label_file in sorted(paths.labels.glob("batch*.jsonl")):
        for rec in read_jsonl(label_file):
            eid = rec["encounter_id"]
            if eid in holdout:
                raise ExportError("label file contains a holdout id")
            version = rec.get("version_reviewed", "")
            pred_path = paths.runs / version / label_file.stem / "predictions.jsonl"
            drafts = {r["encounter_id"]: r for r in read_jsonl(pred_path)} if pred_path.exists() else {}
            draft = drafts.get(eid, {})
            canon = canonicalize(rec["label"], scope)
            spans: dict[str, list[dict[str, Any]]] = {}
            for d in draft.get("diagnoses", []):
                if d["code"] in canon.diagnoses:
                    spans[f"dx:{d['code']}"] = [
                        {"source": s["source"], "start": s["start"], "end": s["end"]} for s in d.get("evidence", [])
                    ]
            for ln in draft.get("lines", []):
                if any(c.code == ln["code"] for c in canon.lines):
                    spans.setdefault(
                        f"line:{ln['code']}",
                        [{"source": s["source"], "start": s["start"], "end": s["end"]} for s in ln.get("evidence", [])],
                    )
            records.append(
                {
                    "encounter_id": eid,
                    "batch": label_file.stem,
                    "coder_id": rec["coder_id"],
                    "coders": 1,
                    "diagnoses": sorted(canon.diagnoses),
                    "first_listed": canon.first_listed,
                    "lines": [
                        {
                            "code": c.code,
                            "modifiers": list(c.modifiers),
                            "units": c.units,
                            "pointers": sorted(c.pointers),
                        }
                        for c in canon.lines
                    ],
                    "evidence_spans": spans,
                    "disclosure": "single CPC label produced by reviewing an agent draft (v0-anchored); see CodeLoop README",
                    "source_license": lic,
                    "scope_sha256": None,
                }
            )
    out = out or (paths.reports / "aci-bench-claims.jsonl")
    n = write_jsonl(out, records)
    return out, n
