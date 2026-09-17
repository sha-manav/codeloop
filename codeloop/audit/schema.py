"""Structured output of the Phase 2 prevalence audit (spec §18, Phase 2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CATEGORIES: tuple[str, ...] = (
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
    "other_procedure",
)
Category = Literal[
    "in_office_injection", "joint_aspiration_injection", "laceration_repair", "lesion_destruction", "ecg",
    "spirometry", "nebulizer_treatment", "cerumen_removal", "waived_in_office_test", "immunization",
    "drug_administration_with_wastage", "other_procedure",
]
Source = Literal["note", "dialogue"]


class FlagFacts(BaseModel):
    product: str | None = None
    dose: str | None = None
    route: str | None = None
    counseling_documented: bool | None = None
    counseling_by: str | None = None
    wastage_documented: bool | None = None
    wastage_amount: str | None = None
    test_name: str | None = None
    components: int | None = None


class ServiceFlag(BaseModel):
    category: Category
    description: str
    evidence_quote: str
    evidence_source: Source
    confidence: Literal["high", "medium", "low"]
    facts: FlagFacts = Field(default_factory=FlagFacts)


class PatientFacts(BaseModel):
    age_years: int | None = None
    age_evidence: str | None = None
    age_source: Source | None = None
    sex: Literal["male", "female"] | None = None
    sex_evidence: str | None = None
    sex_source: Source | None = None


class AuditResult(BaseModel):
    flags: list[ServiceFlag] = Field(default_factory=list)
    patient: PatientFacts = Field(default_factory=PatientFacts)


# Category -> optional module it activates (decision D10); the rest feed core_lines.
MODULE_CATEGORY: dict[str, str] = {
    "vaccine_admin": "immunization",
    "jw_jz": "drug_administration_with_wastage",
    "qw": "waived_in_office_test",
}
PROCEDURE_CATEGORIES: tuple[str, ...] = tuple(c for c in CATEGORIES if c != "waived_in_office_test")

# Proposed CPT/HCPCS allowlist ranges per confirmed category (code numbers only; owner decides).
PROPOSED_RANGES: dict[str, list[str]] = {
    "in_office_injection": ["96372-96379"],
    "joint_aspiration_injection": ["20600-20611"],
    "laceration_repair": ["12001-12007", "12011-12018", "12031-12057"],
    "lesion_destruction": ["17000-17004", "17110-17111", "11300-11313", "11400-11446"],
    "ecg": ["93000-93010"],
    "spirometry": ["94010-94010", "94060-94060"],
    "nebulizer_treatment": ["94640-94640"],
    "cerumen_removal": ["69209-69210"],
    "waived_in_office_test": [
        "81002-81002", "81025-81025", "82962-82962", "83036-83036", "86308-86308", "87804-87804",
        "87811-87811", "87880-87880",
    ],
    "immunization": ["90460-90461", "90471-90474", "90476-90759", "91300-91322"],
    "drug_administration_with_wastage": ["96372-96379", "J0000-J9999"],
    "other_procedure": [],
}
