"""Structured outputs of the agent's LLM call sites (extract, map_dx, map_lines)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["active", "historical", "ruled_out"]
Laterality = Literal["right", "left", "bilateral", "unspecified", "not_applicable"]
ServiceCategory = Literal[
    "in_office_injection",
    "joint_aspiration_injection",
    "laceration_repair",
    "lesion_destruction",
    "ecg",
    "spirometry",
    "nebulizer_treatment",
    "cerumen_removal",
    "waived_in_office_test",
    "immunization",
    "drug_administration_with_wastage",
    "in_office_imaging",
    "other_procedure",
]


class Problem(BaseModel):
    description: str
    status: Status
    laterality: Laterality
    qualifiers: list[str] = Field(default_factory=list)  # acuity, type, stage, complication, as documented
    note_quotes: list[str] = Field(default_factory=list)  # verbatim substrings of the note
    dialogue_quotes: list[str] = Field(default_factory=list)  # verbatim substrings of the transcript


class Service(BaseModel):
    category: ServiceCategory
    description: str
    body_part: str | None = None
    laterality: Laterality = "not_applicable"
    views: int | None = None
    note_quotes: list[str] = Field(default_factory=list)
    dialogue_quotes: list[str] = Field(default_factory=list)


class Administration(BaseModel):
    product_name: str
    kind: Literal["drug", "vaccine"] = "drug"
    dose: str | None = None
    route: str | None = None
    wastage: str | None = None  # amount discarded as documented, else null
    counseling: str | None = None  # who provided vaccine counseling as documented, else null
    note_quotes: list[str] = Field(default_factory=list)
    dialogue_quotes: list[str] = Field(default_factory=list)


class PatientFacts(BaseModel):
    age_years: int | None = None
    age_quote: str | None = None
    sex: Literal["male", "female"] | None = None
    sex_quote: str | None = None


class Extraction(BaseModel):
    problems: list[Problem] = Field(default_factory=list)
    services: list[Service] = Field(default_factory=list)
    administrations: list[Administration] = Field(default_factory=list)
    patient: PatientFacts = Field(default_factory=PatientFacts)


class DxSelection(BaseModel):
    problem_index: int
    code: str | None  # ICD-10-CM (dot optional); null when the problem should not be coded
    first_listed: bool = False
    laterality_basis: Literal["note", "dialogue", "none"] = "none"
    rationale: str = ""
    provider_query: str | None = None  # a question for the provider when documentation is insufficient


class DxMapping(BaseModel):
    selections: list[DxSelection] = Field(default_factory=list)


class LineSelection(BaseModel):
    service_index: int
    code: str | None  # CPT/HCPCS code number within the allowed ranges; null when not codeable
    units: int = 1
    pointer_problem_indices: list[int] = Field(default_factory=list)
    rationale: str = ""
    data_gap: str | None = None


class LineMapping(BaseModel):
    selections: list[LineSelection] = Field(default_factory=list)
