"""CodingPackage and its parts (spec §4): the agent's output and the shape of labels.

Normalization on construction: ICD-10-CM codes uppercased without the dot, line codes uppercased,
modifiers uppercased and stored sorted. Spans carry the SHA-256 of their text and are verified
against the encounter text with `verify_package_spans`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from codeloop.schemas.encounter import Encounter
from codeloop.util.codes import normalize_icd10cm
from codeloop.util.hashing import sha256_text

Severity = Literal["error", "warn"]


def normalize_line_code(code: str) -> str:
    return code.strip().upper()


def normalize_modifiers(mods: list[str] | None) -> list[str]:
    return sorted({m.strip().upper() for m in (mods or []) if m and m.strip()})


class Span(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: Literal["note", "dialogue"]
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
    sha256: str

    @model_validator(mode="after")
    def _check(self) -> Span:
        if self.end < self.start:
            raise ValueError("span end precedes start")
        if len(self.text) != self.end - self.start:
            raise ValueError("span text length does not match offsets")
        if sha256_text(self.text) != self.sha256:
            raise ValueError("span sha256 does not match text")
        return self

    @classmethod
    def make(cls, source: Literal["note", "dialogue"], start: int, end: int, text: str) -> Span:
        return cls(source=source, start=start, end=end, text=text, sha256=sha256_text(text))

    @classmethod
    def from_source(cls, source: Literal["note", "dialogue"], source_text: str, start: int, end: int) -> Span:
        return cls.make(source, start, end, source_text[start:end])

    def verify(self, encounter: Encounter) -> bool:
        source_text = encounter.note_text if self.source == "note" else encounter.dialogue_text
        return source_text[self.start : self.end] == self.text


class DiagnosisPred(BaseModel):
    code: str  # ICD-10-CM, normalized: uppercase, dot removed (e.g. "M1711")
    status: Literal["active", "historical"] = "active"
    first_listed: bool = False
    evidence: list[Span] = Field(default_factory=list)  # at least one for billable fields (§9)
    rationale: str = ""  # model-generated, never scored

    @field_validator("code")
    @classmethod
    def _norm_code(cls, v: str) -> str:
        v = normalize_icd10cm(v)
        if not v:
            raise ValueError("empty diagnosis code")
        return v


class LinePred(BaseModel):
    code: str  # CPT/HCPCS, uppercase, 5 chars
    modifiers: list[str] = Field(default_factory=list)  # stored sorted
    units: int = Field(default=1, ge=1)
    pointers: list[str] = Field(default_factory=list)  # ICD-10-CM codes (resolved, not letters)
    module: str = "core_lines"
    evidence: list[Span] = Field(default_factory=list)
    rationale: str = ""

    @field_validator("code")
    @classmethod
    def _norm_code(cls, v: str) -> str:
        v = normalize_line_code(v)
        if len(v) != 5:
            raise ValueError(f"line code must be 5 characters: {v!r}")
        return v

    @field_validator("modifiers")
    @classmethod
    def _norm_mods(cls, v: list[str]) -> list[str]:
        return normalize_modifiers(v)

    @field_validator("pointers")
    @classmethod
    def _norm_pointers(cls, v: list[str]) -> list[str]:
        return sorted({normalize_icd10cm(p) for p in v if p and p.strip()})


class ProviderQuery(BaseModel):
    field_ref: str  # e.g. "dx:M1710:laterality"
    question: str
    evidence: list[Span] = Field(default_factory=list)  # typically dialogue spans
    suggested_value: str | None = None


class DataGap(BaseModel):
    field_ref: str
    missing: str  # e.g. "NDC not resolvable from product name"


class ScrubFailure(BaseModel):
    rule_id: str  # "NCCI_PTP", "MUE", "MOD_LATERALITY", ...
    field_ref: str
    message: str
    severity: Severity
    table_version: str


class ComplianceIssue(BaseModel):
    field_ref: str
    kind: str  # "no_allowed_evidence", "span_mismatch", "unknown_code", "out_of_scope_modifier", ...
    message: str
    severity: Severity = "error"


class ComplianceResult(BaseModel):
    policy: str = "note_only"  # decision D1
    checked: bool = False
    passed: bool = True
    issues: list[ComplianceIssue] = Field(default_factory=list)
    downgraded_fields: list[str] = Field(default_factory=list)  # fields whose only evidence was dialogue


class CodingPackage(BaseModel):
    encounter_id: str
    version: str  # "v0"… or "dev"
    run_id: str
    diagnoses: list[DiagnosisPred] = Field(default_factory=list)
    lines: list[LinePred] = Field(default_factory=list)
    provider_queries: list[ProviderQuery] = Field(default_factory=list)
    data_gaps: list[DataGap] = Field(default_factory=list)
    scrubber: list[ScrubFailure] = Field(default_factory=list)
    compliance: ComplianceResult = Field(default_factory=ComplianceResult)

    @property
    def first_listed_code(self) -> str | None:
        for d in self.diagnoses:
            if d.first_listed:
                return d.code
        return None

    def scrubber_errors(self) -> list[ScrubFailure]:
        return [f for f in self.scrubber if f.severity == "error"]


def iter_spans(package: CodingPackage):
    """Yield (field_ref, span) for every evidence span in the package."""
    for d in package.diagnoses:
        for s in d.evidence:
            yield f"dx:{d.code}", s
    for i, ln in enumerate(package.lines):
        for s in ln.evidence:
            yield f"line:{ln.code}:{i}", s
    for i, q in enumerate(package.provider_queries):
        for s in q.evidence:
            yield f"query:{i}", s


def verify_package_spans(package: CodingPackage, encounter: Encounter) -> list[str]:
    """Return a list of violations ('<field_ref>: <reason>'); empty means every span verifies."""
    problems: list[str] = []
    if package.encounter_id != encounter.id:
        problems.append(f"package encounter_id {package.encounter_id} != encounter {encounter.id}")
    for ref, span in iter_spans(package):
        source_text = encounter.note_text if span.source == "note" else encounter.dialogue_text
        if span.end > len(source_text):
            problems.append(f"{ref}: span [{span.start}, {span.end}) exceeds {span.source} length {len(source_text)}")
        elif source_text[span.start : span.end] != span.text:
            problems.append(f"{ref}: span text does not match {span.source}[{span.start}:{span.end}]")
    return problems
