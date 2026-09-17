"""Coder-produced labels (spec §10.2): CodingPackage-shaped without rationale or evidence requirements."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from codeloop.schemas.package import normalize_line_code, normalize_modifiers
from codeloop.util.codes import normalize_icd10cm


class LabelDiagnosis(BaseModel):
    code: str
    status: Literal["active", "historical"] = "active"
    first_listed: bool = False

    @field_validator("code")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize_icd10cm(v)


class LabelLine(BaseModel):
    code: str
    modifiers: list[str] = Field(default_factory=list)
    units: int = Field(default=1, ge=1)
    pointers: list[str] = Field(default_factory=list)  # codes, or letters A.. resolved by the canonicalizer

    @field_validator("code")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize_line_code(v)

    @field_validator("modifiers")
    @classmethod
    def _mods(cls, v: list[str]) -> list[str]:
        return normalize_modifiers(v)


class LabelPackage(BaseModel):
    diagnoses: list[LabelDiagnosis] = Field(default_factory=list)
    lines: list[LabelLine] = Field(default_factory=list)


class LabelRecord(BaseModel):
    """One line of data/labels/batchB.jsonl."""

    encounter_id: str
    coder_id: str
    label: LabelPackage
    blind_label: LabelPackage | None = None
    touches: int = 0
    review_minutes: float = 0.0
    evidence_grades: dict[str, str] = Field(default_factory=dict)  # span_id -> supported|unsupported
    query_grades: dict[str, str] = Field(default_factory=dict)  # query ref -> warranted|unwarranted
