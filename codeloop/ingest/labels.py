"""Public ICD label sets (Amazon, MedCodER) and their crosswalk to ACI-Bench encounter IDs.

Amazon rows carry the ACI encounter ID directly. MedCodER documents carry their own IDs, so they
are joined by note text: exact match first, then trailing-whitespace-insensitive, then
whitespace-collapsed. Character offsets shipped with MedCodER refer to MedCodER's copy of the
text; snippets are re-located in our `note_text` (unique match required) and stored alongside.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from codeloop.config import Source
from codeloop.schemas.encounter import Encounter, normalize_newlines
from codeloop.util.codes import looks_like_icd10cm, normalize_icd10cm


class LabelIngestError(RuntimeError):
    pass


def _require(fieldnames: list[str] | None, required: set[str], name: str) -> None:
    missing = required - set(fieldnames or [])
    if missing:
        raise LabelIngestError(f"{name}: missing columns {sorted(missing)}; found {fieldnames}")


# ----------------------------------------------------------------------------- Amazon


class AmazonCodeRow(BaseModel):
    document_id: str
    code_raw: str
    description: str
    split_orig: str


def load_amazon(raw_dir: Path, source_id: str, source: Source) -> list[AmazonCodeRow]:
    rows: list[AmazonCodeRow] = []
    for f in source.files:
        path = Path(raw_dir) / source_id / f.name
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            _require(reader.fieldnames, {"Document ID", "ICD10", "Description"}, f.name)
            for r in reader:
                rows.append(
                    AmazonCodeRow(
                        document_id=(r["Document ID"] or "").strip(),
                        code_raw=(r["ICD10"] or "").strip(),
                        description=(r["Description"] or "").strip(),
                        split_orig=f.split_orig or "unknown",
                    )
                )
    return rows


@dataclass
class CrosswalkStats:
    source: str
    documents: int = 0
    rows: int = 0
    matched_documents: int = 0
    matched_by: dict[str, int] = field(default_factory=dict)
    unmatched_documents: int = 0
    unmatched_rows: int = 0
    duplicate_matches: int = 0
    encounters_without_record: list[str] = field(default_factory=list)
    extra: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["encounters_without_record"] = len(self.encounters_without_record)
        return d


def crosswalk_amazon(rows: list[AmazonCodeRow], encounters: list[Encounter]) -> tuple[list[dict], CrosswalkStats]:
    by_id = {e.id: e for e in encounters}
    grouped: dict[str, list[AmazonCodeRow]] = defaultdict(list)
    for r in rows:
        grouped[r.document_id].append(r)
    stats = CrosswalkStats(source="amazon", documents=len(grouped), rows=len(rows))
    records: list[dict] = []
    for doc_id in sorted(grouped):
        group = grouped[doc_id]
        if doc_id not in by_id:
            stats.unmatched_documents += 1
            stats.unmatched_rows += len(group)
            continue
        codes = sorted(
            (
                {
                    "code": normalize_icd10cm(r.code_raw),
                    "code_raw": r.code_raw,
                    "description": r.description,
                    "valid_shape": looks_like_icd10cm(r.code_raw),
                }
                for r in group
            ),
            key=lambda c: (c["code"], c["code_raw"]),
        )
        records.append(
            {
                "encounter_id": doc_id,
                "source": "amazon",
                "split_orig": group[0].split_orig,
                "match": "id",
                "codes": codes,
            }
        )
        stats.matched_documents += 1
    stats.matched_by = {"id": stats.matched_documents}
    covered = {r["encounter_id"] for r in records}
    stats.encounters_without_record = sorted(i for i in by_id if i not in covered)
    stats.extra = {"invalid_code_shapes": sum(1 for r in records for c in r["codes"] if not c["valid_shape"])}
    return records, stats


# ----------------------------------------------------------------------------- MedCodER


class MedCodERDoc(BaseModel):
    doc_id: str
    text: str
    aci_doc_id: str
    partition: str


class MedCodERDiagnosis(BaseModel):
    doc_id: str
    code_raw: str
    diagnosis: str
    start: int
    end: int
    partition: str


class MedCodEREvidence(BaseModel):
    doc_id: str
    code_raw: str
    text: str
    start: int
    end: int
    coordinate: str
    partition: str


@dataclass
class MedCodERData:
    docs: list[MedCodERDoc] = field(default_factory=list)
    diagnoses: list[MedCodERDiagnosis] = field(default_factory=list)
    evidence: list[MedCodEREvidence] = field(default_factory=list)


def _int(v: str | None) -> int:
    try:
        return int(float(v)) if v not in (None, "") else -1
    except ValueError:
        return -1


def load_medcoder(raw_dir: Path, source_id: str, source: Source) -> MedCodERData:
    data = MedCodERData()
    for f in source.files:
        path = Path(raw_dir) / source_id / f.name
        partition = f.partition or "unknown"
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if f.role == "text":
                _require(reader.fieldnames, {"Document ID", "medical_record_text", "aci_doc_id"}, f.name)
                for r in reader:
                    data.docs.append(
                        MedCodERDoc(
                            doc_id=r["Document ID"].strip(),
                            text=r["medical_record_text"] or "",
                            aci_doc_id=(r["aci_doc_id"] or "").strip(),
                            partition=partition,
                        )
                    )
            elif f.role == "diagnosis":
                _require(reader.fieldnames, {"Document ID", "ICD10", "Diagnosis", "Start", "End"}, f.name)
                for r in reader:
                    data.diagnoses.append(
                        MedCodERDiagnosis(
                            doc_id=r["Document ID"].strip(),
                            code_raw=(r["ICD10"] or "").strip(),
                            diagnosis=r["Diagnosis"] or "",
                            start=_int(r["Start"]),
                            end=_int(r["End"]),
                            partition=partition,
                        )
                    )
            elif f.role == "evidence":
                _require(
                    reader.fieldnames,
                    {"Document ID", "ICD-10-cm code", "Supporting Evidence Text", "Start", "End"},
                    f.name,
                )
                for r in reader:
                    data.evidence.append(
                        MedCodEREvidence(
                            doc_id=r["Document ID"].strip(),
                            code_raw=(r["ICD-10-cm code"] or "").strip(),
                            text=r["Supporting Evidence Text"] or "",
                            start=_int(r["Start"]),
                            end=_int(r["End"]),
                            coordinate=(r.get("Coordinate") or "").strip(),
                            partition=partition,
                        )
                    )
            else:
                raise LabelIngestError(f"{f.name}: unknown role {f.role!r}")
    return data


_WS = re.compile(r"\s+")


def collapse_ws(s: str) -> str:
    return _WS.sub(" ", s).strip()


def locate(note_text: str, snippet: str) -> tuple[int, int] | None:
    """Offsets of the unique occurrence of `snippet` in `note_text`, tolerating whitespace drift."""
    if not snippet.strip():
        return None
    exact = [m.start() for m in re.finditer(re.escape(snippet), note_text)]
    if len(exact) == 1:
        return exact[0], exact[0] + len(snippet)
    if len(exact) > 1:
        return None
    pattern = r"\s+".join(re.escape(tok) for tok in snippet.split())
    hits = list(re.finditer(pattern, note_text))
    if len(hits) == 1:
        return hits[0].start(), hits[0].end()
    return None


def crosswalk_medcoder(data: MedCodERData, encounters: list[Encounter]) -> tuple[list[dict], CrosswalkStats]:
    exact: dict[str, str] = {}
    rstripped: dict[str, str] = {}
    collapsed: dict[str, str] = {}
    for e in encounters:
        exact.setdefault(e.note_text, e.id)
        rstripped.setdefault(e.note_text.rstrip(), e.id)
        collapsed.setdefault(collapse_ws(e.note_text), e.id)
    by_id = {e.id: e for e in encounters}
    dx_by_doc: dict[str, list[MedCodERDiagnosis]] = defaultdict(list)
    for d in data.diagnoses:
        dx_by_doc[d.doc_id].append(d)
    ev_by_doc: dict[str, list[MedCodEREvidence]] = defaultdict(list)
    for ev in data.evidence:
        ev_by_doc[ev.doc_id].append(ev)

    stats = CrosswalkStats(source="medcoder", documents=len(data.docs), rows=len(data.diagnoses) + len(data.evidence))
    tiers = {"exact": 0, "rstrip": 0, "collapsed_ws": 0}
    extra = {
        "diagnosis_rows": len(data.diagnoses),
        "evidence_rows": len(data.evidence),
        "diagnoses_located_in_note": 0,
        "diagnoses_not_located": 0,
        "evidence_located_in_note": 0,
        "evidence_not_located": 0,
        "medcoder_diagnosis_offsets_verified": 0,
        "medcoder_evidence_offsets_verified": 0,
        "invalid_code_shapes": 0,
        "docs_partition_test": sum(1 for d in data.docs if d.partition == "test"),
        "docs_partition_holdout": sum(1 for d in data.docs if d.partition == "holdout"),
    }
    seen: dict[str, str] = {}
    records: list[dict] = []
    for doc in sorted(data.docs, key=lambda d: (d.partition, d.doc_id)):
        t = normalize_newlines(doc.text)
        if t in exact:
            eid, tier = exact[t], "exact"
        elif t.rstrip() in rstripped:
            eid, tier = rstripped[t.rstrip()], "rstrip"
        elif collapse_ws(t) in collapsed:
            eid, tier = collapsed[collapse_ws(t)], "collapsed_ws"
        else:
            stats.unmatched_documents += 1
            stats.unmatched_rows += len(dx_by_doc.get(doc.doc_id, [])) + len(ev_by_doc.get(doc.doc_id, []))
            continue
        tiers[tier] += 1
        if eid in seen:
            stats.duplicate_matches += 1
        seen[eid] = doc.doc_id
        enc = by_id[eid]
        diagnoses = []
        for d in dx_by_doc.get(doc.doc_id, []):
            verified = 0 <= d.start <= d.end <= len(doc.text) and doc.text[d.start : d.end] == d.diagnosis
            loc = locate(enc.note_text, d.diagnosis)
            extra["medcoder_diagnosis_offsets_verified"] += int(verified)
            extra["diagnoses_located_in_note" if loc else "diagnoses_not_located"] += 1
            extra["invalid_code_shapes"] += int(not looks_like_icd10cm(d.code_raw))
            diagnoses.append(
                {
                    "code": normalize_icd10cm(d.code_raw),
                    "code_raw": d.code_raw,
                    "diagnosis": d.diagnosis,
                    "medcoder_start": d.start,
                    "medcoder_end": d.end,
                    "medcoder_offsets_verified": verified,
                    "note_start": loc[0] if loc else None,
                    "note_end": loc[1] if loc else None,
                    "valid_shape": looks_like_icd10cm(d.code_raw),
                }
            )
        evidence = []
        for ev in ev_by_doc.get(doc.doc_id, []):
            verified = 0 <= ev.start <= ev.end <= len(doc.text) and doc.text[ev.start : ev.end] == ev.text
            loc = locate(enc.note_text, ev.text)
            extra["medcoder_evidence_offsets_verified"] += int(verified)
            extra["evidence_located_in_note" if loc else "evidence_not_located"] += 1
            evidence.append(
                {
                    "code": normalize_icd10cm(ev.code_raw),
                    "code_raw": ev.code_raw,
                    "text": ev.text,
                    "medcoder_start": ev.start,
                    "medcoder_end": ev.end,
                    "medcoder_offsets_verified": verified,
                    "note_start": loc[0] if loc else None,
                    "note_end": loc[1] if loc else None,
                }
            )
        records.append(
            {
                "encounter_id": eid,
                "source": "medcoder",
                "medcoder_doc_id": doc.doc_id,
                "medcoder_aci_doc_id": doc.aci_doc_id,
                "medcoder_partition": doc.partition,
                "match": tier,
                "diagnoses": sorted(diagnoses, key=lambda x: (x["code"], x["medcoder_start"])),
                "evidence": sorted(evidence, key=lambda x: (x["code"], x["medcoder_start"])),
            }
        )
        stats.matched_documents += 1
    stats.matched_by = tiers
    covered = {r["encounter_id"] for r in records}
    stats.encounters_without_record = sorted(i for i in by_id if i not in covered)
    orphans = sum(len(v) for k, v in dx_by_doc.items() if k not in {d.doc_id for d in data.docs})
    extra["diagnosis_rows_without_text_row"] = orphans
    stats.extra = extra
    records.sort(key=lambda r: (r["encounter_id"], r["medcoder_partition"], r["medcoder_doc_id"]))
    return records, stats
