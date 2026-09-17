"""Compliance static check and evidence policy (spec §9, decision D1)."""

from __future__ import annotations

from codeloop.schemas.encounter import Encounter
from codeloop.schemas.package import CodingPackage, ComplianceIssue, ComplianceResult, ProviderQuery, Span
from codeloop.scoring import Scope
from codeloop.tables import Tables


def allowed_sources(policy: str) -> set[str]:
    if policy == "note_only":
        return {"note"}
    if policy == "note_or_dialogue":
        return {"note", "dialogue"}
    raise ValueError(f"unknown evidence policy {policy!r}")


def _has_allowed(spans: list[Span], allowed: set[str]) -> bool:
    return any(s.source in allowed for s in spans)


def apply_evidence_policy(package: CodingPackage, policy: str) -> tuple[CodingPackage, list[str]]:
    """Remove billable fields whose only evidence comes from a disallowed source; each removal becomes a
    ProviderQuery carrying the disallowed spans. Returns the new package and the downgraded field refs."""
    allowed = allowed_sources(policy)
    downgraded: list[str] = []
    queries = list(package.provider_queries)
    diagnoses = []
    for d in package.diagnoses:
        if _has_allowed(d.evidence, allowed):
            diagnoses.append(d)
        else:
            ref = f"dx:{d.code}"
            downgraded.append(ref)
            queries.append(
                ProviderQuery(
                    field_ref=ref,
                    evidence=list(d.evidence),
                    suggested_value=d.code,
                    question=(
                        f"The transcript supports {d.code} but the note does not document it; please confirm."
                    ),
                )
            )
    kept_codes = {d.code for d in diagnoses}
    lines = []
    for i, ln in enumerate(package.lines):
        if _has_allowed(ln.evidence, allowed):
            pointers = [p for p in ln.pointers if p in kept_codes] or ln.pointers
            lines.append(ln.model_copy(update={"pointers": sorted(set(pointers))}))
        else:
            ref = f"line:{ln.code}:{i}"
            downgraded.append(ref)
            queries.append(
                ProviderQuery(
                    field_ref=ref,
                    evidence=list(ln.evidence),
                    suggested_value=ln.code,
                    question=(
                        f"The transcript indicates a service ({ln.code}) that the note does not document; "
                        "please document it if performed."
                    ),
                )
            )
    if any(d.first_listed for d in diagnoses) is False and diagnoses:
        diagnoses[0] = diagnoses[0].model_copy(update={"first_listed": True})
    new = package.model_copy(update={"diagnoses": diagnoses, "lines": lines, "provider_queries": queries})
    return new, downgraded


def check_package(
    package: CodingPackage, encounter: Encounter, scope: Scope, tables: Tables, policy: str
) -> ComplianceResult:
    allowed = allowed_sources(policy)
    issues: list[ComplianceIssue] = []

    def span_ok(span: Span) -> bool:
        text = encounter.note_text if span.source == "note" else encounter.dialogue_text
        return text[span.start : span.end] == span.text

    for d in package.diagnoses:
        ref = f"dx:{d.code}"
        if not _has_allowed(d.evidence, allowed):
            issues.append(
                ComplianceIssue(
                    field_ref=ref, kind="no_allowed_evidence", message=f"no {'/'.join(sorted(allowed))} evidence"
                )
            )
        for s in d.evidence:
            if not span_ok(s):
                issues.append(
                    ComplianceIssue(
                        field_ref=ref,
                        kind="span_mismatch",
                        message=f"{s.source}[{s.start}:{s.end}] does not match its text",
                    )
                )
        if not tables.icd_valid(d.code):
            issues.append(
                ComplianceIssue(
                    field_ref=ref, kind="unknown_code", message="not a valid ICD-10-CM code in the pinned release"
                )
            )
    for i, ln in enumerate(package.lines):
        ref = f"line:{ln.code}:{i}"
        if not _has_allowed(ln.evidence, allowed):
            issues.append(
                ComplianceIssue(
                    field_ref=ref, kind="no_allowed_evidence", message=f"no {'/'.join(sorted(allowed))} evidence"
                )
            )
        for s in ln.evidence:
            if not span_ok(s):
                issues.append(
                    ComplianceIssue(
                        field_ref=ref,
                        kind="span_mismatch",
                        message=f"{s.source}[{s.start}:{s.end}] does not match its text",
                    )
                )
        if not tables.line_code_exists(ln.code):
            issues.append(ComplianceIssue(field_ref=ref, kind="unknown_code", message="not in the pinned code sets"))
        if not scope.in_scope_line(ln.code):
            issues.append(
                ComplianceIssue(
                    field_ref=ref,
                    kind="out_of_scope_line",
                    message="line code is outside the scope allowlist",
                    severity="warn",
                )
            )
        for m in ln.modifiers:
            if not scope.allowed_modifier(m):
                issues.append(
                    ComplianceIssue(
                        field_ref=f"{ref}:modifiers",
                        kind="out_of_scope_modifier",
                        message=f"modifier {m} is out of scope",
                    )
                )
    return ComplianceResult(
        policy=policy, checked=True, passed=not any(i.severity == "error" for i in issues), issues=issues
    )
