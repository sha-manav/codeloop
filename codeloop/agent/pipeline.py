"""Agent pipeline (spec §6): ingest → extract → map_dx → map_lines → assemble → validate → emit."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codeloop.agent.blocks import problems_block, services_block, spans_for_quotes
from codeloop.agent.schemas import DxMapping, Extraction, LineMapping, LineSelection
from codeloop.compliance import apply_evidence_policy, check_package
from codeloop.ledger import utc_now
from codeloop.llm.client import LLMClient
from codeloop.mappers import imaging
from codeloop.mappers.registry import CATEGORY_MODULE, mappable_categories
from codeloop.paths import Paths
from codeloop.rules.dx_rules import apply_dx_rules, choose_first_listed, drop_not_assessed
from codeloop.schemas.encounter import Encounter
from codeloop.schemas.package import CodingPackage, DataGap, DiagnosisPred, LinePred, ProviderQuery
from codeloop.schemas.trace import StageTrace, Trace
from codeloop.scoring import Scope
from codeloop.scrubber import scrub
from codeloop.tables import Tables
from codeloop.tools.icd_retrieval import IcdRetriever, cause_term, is_definitive_code, is_symptom_code
from codeloop.tools.product_data import ProductResolution, resolve_product
from codeloop.util.hashing import sha256_text


@dataclass
class RunContext:
    paths: Paths
    version: str
    run_id: str
    llm: LLMClient
    tables: Tables
    scope: Scope
    scope_hash: str
    evidence_policy: str
    on_date: str
    seed: int
    prompt_hashes: dict[str, str] = field(default_factory=dict)

    @property
    def retriever(self) -> IcdRetriever:
        return IcdRetriever(self.tables)


def _stage(name: str, input_obj: Any) -> StageTrace:
    return StageTrace(name=name, input_hash=sha256_text(str(input_obj)), started_at=utc_now())


def _finish(stage: StageTrace, output: Any = None, notes: list[str] | None = None) -> StageTrace:
    stage.finished_at = utc_now()
    stage.output = output
    if notes:
        stage.notes.extend(notes)
    return stage


def run_encounter(enc: Encounter, ctx: RunContext) -> Trace:
    started = utc_now()
    stages: list[StageTrace] = []

    # 1. ingest (Encounter validation re-verified the hashes on load)
    st = _stage("ingest", enc.note_sha256 + enc.dialogue_sha256)
    stages.append(_finish(st, {"note_sha256": enc.note_sha256, "dialogue_sha256": enc.dialogue_sha256}))

    # 2. extract
    st = _stage("extract", enc.id)
    comp = ctx.llm.complete(
        "extract",
        {"encounter_id": enc.id, "subset": enc.subset, "note_text": enc.note_text, "dialogue_text": enc.dialogue_text},
        Extraction,
        seed=ctx.seed,
    )
    st.llm_calls.append(comp.trace)
    ex: Extraction = comp.parsed
    p_note, p_dlg, missing = [], [], 0
    for p in ex.problems:
        n, d, m = spans_for_quotes(enc, p.note_quotes, p.dialogue_quotes)
        p_note.append(n)
        p_dlg.append(d)
        missing += m
    s_note, s_dlg = [], []
    for s in ex.services:
        n, d, m = spans_for_quotes(enc, s.note_quotes, s.dialogue_quotes)
        s_note.append(n)
        s_dlg.append(d)
        missing += m
    stages.append(_finish(st, ex.model_dump(mode="json"), [f"unlocated quotes: {missing}"]))

    # 3. map_dx
    st = _stage("map_dx", [p.description for p in ex.problems])
    retriever = ctx.retriever
    candidates = []
    for p in ex.problems:
        if p.status == "ruled_out":
            candidates.append([])
        else:
            candidates.append(retriever.candidates_for_problem(p.description, p.qualifiers, p.laterality, p.status))
    decisions = []
    gaps: list[DataGap] = []
    queries: list[ProviderQuery] = []
    if ex.problems:
        comp = ctx.llm.complete(
            "map_dx",
            {
                "encounter_id": enc.id,
                "evidence_policy": ctx.evidence_policy,
                "problems_block": problems_block(ex.problems, p_note, p_dlg, candidates),
            },
            DxMapping,
            seed=ctx.seed,
        )
        st.llm_calls.append(comp.trace)
        mapping: DxMapping = comp.parsed
        by_index = {s.problem_index: s for s in mapping.selections}
        for i, p in enumerate(ex.problems):
            sel = by_index.get(i)
            d = apply_dx_rules(
                problem_index=i,
                problem_status=p.status,
                problem_laterality=p.laterality,
                selected_code=sel.code if sel else None,
                first_listed=bool(sel and sel.first_listed),
                rationale=sel.rationale if sel else "no selection returned",
                laterality_basis=sel.laterality_basis if sel else "none",
                provider_query=sel.provider_query if sel else None,
                note_spans=p_note[i],
                dialogue_spans=p_dlg[i],
                retriever=retriever,
                evidence_policy=ctx.evidence_policy,
            )
            decisions.append(d)
            gaps.extend(d.gaps)
            queries.extend(d.queries)
        choose_first_listed(decisions)
    stages.append(
        _finish(
            st,
            [
                {"problem_index": d.problem_index, "code": d.code, "first_listed": d.first_listed, "notes": d.notes}
                for d in decisions
            ],
            [f"candidates retrieved: {sum(len(c) for c in candidates)}"],
        )
    )
    problem_codes = {d.problem_index: d.code for d in decisions if d.code}

    # 4. map_lines (module mappers; deterministic product resolution for administrations)
    st = _stage("map_lines", [s.description for s in ex.services])
    mappable = mappable_categories(ctx.scope)
    allowed: dict[int, list[str]] = {}
    for i, s in enumerate(ex.services):
        if s.category in mappable:
            allowed[i] = ctx.scope.modules[CATEGORY_MODULE[s.category]].code_ranges
    line_decisions = []
    pointer_indices: dict[int, list[int]] = {}
    if allowed:
        comp = ctx.llm.complete(
            "map_lines",
            {
                "encounter_id": enc.id,
                "problems_block": problems_block(ex.problems, p_note, p_dlg),
                "services_block": services_block(ex.services, s_note, allowed),
            },
            LineMapping,
            seed=ctx.seed,
        )
        st.llm_calls.append(comp.trace)
        lm: LineMapping = comp.parsed
        by_index = {s.service_index: s for s in lm.selections}
        for i in allowed:
            sel: LineSelection | None = by_index.get(i)
            pointer_indices[i] = list(sel.pointer_problem_indices) if sel else []
            d = apply_line_rules(
                service=ex.services[i],
                selection=sel,
                note_spans=s_note[i] + s_dlg[i],
                scope=ctx.scope,
                tables=ctx.tables,
                problem_codes=problem_codes,
            )
            d.service_index = i
            line_decisions.append(d)
            gaps.extend(d.gaps)
    product_notes = []
    for i, a in enumerate(ex.administrations):
        res = resolve_product(ctx.tables, a.product_name, a.dose, a.route, a.kind, field_ref=f"administration:{i}")
        if isinstance(res, ProductResolution):
            product_notes.append(
                {
                    "index": i,
                    "kind": res.kind,
                    "hcpcs": res.hcpcs,
                    "cvx": res.cvx,
                    "units": res.billing_units,
                    "arithmetic": res.arithmetic,
                }
            )
        else:
            gaps.append(res)
    stages.append(
        _finish(
            st,
            {
                "lines": [
                    {
                        "service_index": d.service_index,
                        "code": d.code,
                        "modifiers": d.modifiers,
                        "units": d.units,
                        "pointers": d.pointers,
                        "notes": d.notes,
                    }
                    for d in line_decisions
                ],
                "administrations": product_notes,
            },
            [f"mappable services: {len(allowed)}/{len(ex.services)}"],
        )
    )

    # 4a. FIND-DX-0052: a second, smaller map_dx call for active problems the first pass left uncoded. The first call
    # and every decision it made stay as they were; only a null can become a code. Two groups: uncoded problems with
    # note evidence get the head term's candidates that were not offered; problems a billed line points at get a wider
    # net, because a line without a coded indication is structurally invalid (spec section 8).
    st = _stage("map_dx_retry", [d.code for d in decisions])
    pointed = {
        j for ld in line_decisions if ld.code and not ld.pointers for j in pointer_indices.get(ld.service_index, [])
    }
    retry_cands: dict[int, list] = {}
    retry_kind: dict[int, str] = {}
    for i, p in enumerate(ex.problems):
        if decisions[i].code is not None or p.status in ("ruled_out", "historical"):
            continue
        if not p_note[i] and ctx.evidence_policy == "note_only":
            continue
        offered = {c.code for c in candidates[i]}
        if i in pointed:
            cands = retriever.wide_candidates(p.description, p.qualifiers, offered)
            retry_kind[i] = "line_indication"
        else:
            cands = retriever.retry_candidates(p.description, offered)
            retry_kind[i] = "uncoded"
        if cands:
            retry_cands[i] = cands
    retry_idx = sorted(retry_cands)
    retry_out = []
    repointed = defaulted = dropped_lines = 0
    if retry_idx:
        comp = ctx.llm.complete(
            "map_dx",
            {
                "encounter_id": enc.id,
                "evidence_policy": ctx.evidence_policy,
                "problems_block": problems_block(
                    [ex.problems[i] for i in retry_idx],
                    [p_note[i] for i in retry_idx],
                    [p_dlg[i] for i in retry_idx],
                    [retry_cands[i] for i in retry_idx],
                ),
            },
            DxMapping,
            seed=ctx.seed,
        )
        st.llm_calls.append(comp.trace)
        by_local = {s.problem_index: s for s in comp.parsed.selections}
        for local, i in enumerate(retry_idx):
            sel = by_local.get(local)
            code = None
            if sel is not None and sel.code:
                p = ex.problems[i]
                d = apply_dx_rules(
                    problem_index=i,
                    problem_status=p.status,
                    problem_laterality=p.laterality,
                    selected_code=sel.code,
                    first_listed=False,  # the first pass chose the first-listed diagnosis
                    rationale=sel.rationale,
                    laterality_basis=sel.laterality_basis,
                    provider_query=sel.provider_query,
                    note_spans=p_note[i],
                    dialogue_spans=p_dlg[i],
                    retriever=retriever,
                    evidence_policy=ctx.evidence_policy,
                )
                if d.code is not None:
                    old = decisions[i]
                    queries = [x for x in queries if x not in old.queries]
                    gaps = [g for g in gaps if g not in old.gaps]
                    d.notes.append(f"coded on retry ({retry_kind[i]}, FIND-DX-0052): {len(retry_cands[i])} candidates")
                    decisions[i] = d
                    gaps.extend(d.gaps)
                    queries.extend(d.queries)
                    code = d.code
            retry_out.append(
                {"problem_index": i, "kind": retry_kind[i], "candidates": len(retry_cands[i]), "code": code}
            )
        choose_first_listed(decisions)
        problem_codes = {d.problem_index: d.code for d in decisions if d.code}
    # 4a-ii. FIND-DX-0039: a symptom coded where its documented cause is named in the same description. A separate,
    # small map_dx call offers candidates for the cause term; the symptom decision is replaced only when the mapper
    # selects a definitive condition code (never a symptom, status or external-cause code). The first call and the
    # 4a retry above are unchanged.
    cause_idx = [
        i
        for i, p in enumerate(ex.problems)
        if decisions[i].code
        and is_symptom_code(decisions[i].code)
        and p.status == "active"
        and cause_term(p.description)
        and (p_note[i] or ctx.evidence_policy != "note_only")
    ]
    cause_cands = {i: retriever.cause_candidates(cause_term(ex.problems[i].description) or "") for i in cause_idx}
    cause_idx = [i for i in cause_idx if cause_cands[i]]
    recoded = 0
    if cause_idx:
        comp = ctx.llm.complete(
            "map_dx",
            {
                "encounter_id": enc.id,
                "evidence_policy": ctx.evidence_policy,
                "problems_block": problems_block(
                    [ex.problems[i] for i in cause_idx],
                    [p_note[i] for i in cause_idx],
                    [p_dlg[i] for i in cause_idx],
                    [cause_cands[i] for i in cause_idx],
                ),
            },
            DxMapping,
            seed=ctx.seed,
        )
        st.llm_calls.append(comp.trace)
        by_local = {s.problem_index: s for s in comp.parsed.selections}
        for local, i in enumerate(cause_idx):
            sel = by_local.get(local)
            old = decisions[i]
            new_code = None
            if sel is not None and sel.code:
                p = ex.problems[i]
                d = apply_dx_rules(
                    problem_index=i,
                    problem_status=p.status,
                    problem_laterality=p.laterality,
                    selected_code=sel.code,
                    first_listed=old.first_listed,
                    rationale=sel.rationale,
                    laterality_basis=sel.laterality_basis,
                    provider_query=sel.provider_query,
                    note_spans=p_note[i],
                    dialogue_spans=p_dlg[i],
                    retriever=retriever,
                    evidence_policy=ctx.evidence_policy,
                )
                if d.code and d.code != old.code and is_definitive_code(d.code):
                    queries = [x for x in queries if x not in old.queries]
                    gaps = [g for g in gaps if g not in old.gaps]
                    d.notes.append(f"recoded to the documented cause (FIND-DX-0039): {old.code} -> {d.code}")
                    decisions[i] = d
                    gaps.extend(d.gaps)
                    queries.extend(d.queries)
                    for ld in line_decisions:
                        ld.pointers = sorted({d.code if ptr == old.code else ptr for ptr in ld.pointers})
                    new_code = d.code
                    recoded += 1
            retry_out.append({"problem_index": i, "kind": "cause", "candidates": len(cause_cands[i]), "code": new_code})
        if recoded:
            choose_first_listed(decisions)
            problem_codes = {d.problem_index: d.code for d in decisions if d.code}

    # a line whose indication was coded on retry gets its pointer. One whose indication still has no code points at
    # the first-listed diagnosis with a data gap saying so (the coder re-points it in review); a package with a
    # pointer-less line is structurally invalid (spec section 8), and dropping the line would bill nothing for a
    # documented, evidenced service. Only when no diagnosis is coded at all is the line dropped.
    first_listed = next((d.code for d in decisions if d.code and d.first_listed), None)
    kept_lines = []
    for ld in line_decisions:
        if ld.code and not ld.pointers:
            ld.pointers = sorted(
                {problem_codes[j] for j in pointer_indices.get(ld.service_index, []) if j in problem_codes}
            )
            if ld.pointers:
                ld.notes.append("pointer resolved after the retry (FIND-DX-0052)")
                repointed += 1
            elif first_listed:
                ld.pointers = [first_listed]
                ld.notes.append("indication uncoded; pointer defaulted to the first-listed diagnosis (FIND-DX-0052)")
                gaps.append(
                    DataGap(
                        field_ref=f"line:{ld.code}:pointers",
                        missing="indication not codable; pointer defaulted to the first-listed diagnosis",
                    )
                )
                defaulted += 1
            else:
                gaps.append(DataGap(field_ref=f"line:{ld.code}", missing="no coded diagnosis supports this line"))
                dropped_lines += 1
                continue
        kept_lines.append(ld)
    line_decisions = kept_lines
    if retry_idx or cause_idx or repointed or defaulted or dropped_lines:  # the stage appears only when it acted
        stages.append(
            _finish(
                st,
                retry_out,
                [
                    f"retried uncoded problems: {len(retry_idx)}",
                    f"symptoms with a documented cause retried: {len(cause_idx)}, recoded: {recoded}",
                    f"lines re-pointed: {repointed}",
                    f"lines pointed at the first-listed diagnosis: {defaulted}",
                    f"lines dropped for want of any coded diagnosis: {dropped_lines}",
                ],
            )
        )

    # 4b. documented-but-not-assessed diagnoses (rules/dx_rules.NOT_ASSESSED_CLASSES); after the lines are mapped so
    # that a diagnosis a billed line depends on is never taken away
    not_assessed = drop_not_assessed(decisions, enc.note_text, [d.pointers for d in line_decisions if d.code])
    if not_assessed:
        for ld in line_decisions:
            kept = [ptr for ptr in ld.pointers if ptr not in not_assessed]
            # a line that pointed only at dropped joint symptoms follows to the diagnosis that explains them
            ld.pointers = kept or sorted({r for ptr in ld.pointers for r in not_assessed.get(ptr, [])})

        def about_dropped(field_ref: str) -> bool:
            return any(field_ref == f"dx:{c}" or field_ref.startswith(f"dx:{c}:") for c in not_assessed)

        queries = [q for q in queries if not about_dropped(q.field_ref)]
        gaps = [g for g in gaps if not about_dropped(g.field_ref)]
        choose_first_listed(decisions)

    # 5. assemble
    st = _stage("assemble", [d.code for d in decisions] + [d.code for d in line_decisions])
    diagnoses: list[DiagnosisPred] = []
    seen_dx: set[str] = set()
    for d in decisions:
        if not d.code or d.code in seen_dx:
            continue
        seen_dx.add(d.code)
        p = ex.problems[d.problem_index]
        diagnoses.append(
            DiagnosisPred(
                code=d.code,
                status="historical" if p.status == "historical" else "active",
                first_listed=d.first_listed,
                evidence=p_note[d.problem_index] + p_dlg[d.problem_index],
                rationale=d.rationale,
            )
        )
    merged: dict[tuple[str, tuple[str, ...]], LinePred] = {}
    for d in line_decisions:
        if not d.code:
            continue
        pointers = list(d.pointers)  # no fallback: a line without a resolvable pointer surfaces as a scrubber error
        key = (d.code, tuple(sorted(d.modifiers)))
        if key in merged:
            prev = merged[key]
            merged[key] = prev.model_copy(
                update={
                    "units": prev.units + d.units,
                    "pointers": sorted(set(prev.pointers) | set(pointers)),
                    "evidence": prev.evidence + [s for s in d.evidence if s not in prev.evidence],
                }
            )
        else:
            merged[key] = LinePred(
                code=d.code,
                modifiers=list(d.modifiers),
                units=d.units,
                pointers=pointers,
                module=d.module,
                evidence=d.evidence,
                rationale=d.rationale,
            )
    package = CodingPackage(
        encounter_id=enc.id,
        version=ctx.version,
        run_id=ctx.run_id,
        diagnoses=diagnoses,
        lines=[merged[k] for k in sorted(merged)],
        provider_queries=queries,
        data_gaps=gaps,
    )
    stages.append(_finish(st, {"diagnoses": len(diagnoses), "lines": len(package.lines)}))

    # 6. validate: evidence policy, compliance static check, scrubber
    st = _stage("validate", package.model_dump_json())
    package, downgraded = apply_evidence_policy(package, ctx.evidence_policy)
    compliance = check_package(package, enc, ctx.scope, ctx.tables, ctx.evidence_policy)
    compliance.downgraded_fields = downgraded
    failures = scrub(package, ctx.tables, ctx.scope, ctx.on_date)
    package = package.model_copy(update={"scrubber": failures, "compliance": compliance})
    stages.append(
        _finish(
            st,
            {
                "downgraded": downgraded,
                "compliance_passed": compliance.passed,
                "scrubber_errors": sum(1 for f in failures if f.severity == "error"),
            },
        )
    )

    return Trace(
        encounter_id=enc.id,
        version=ctx.version,
        run_id=ctx.run_id,
        models_hash=ctx.llm.models_hash,
        scope_hash=ctx.scope_hash,
        prompt_hashes=ctx.prompt_hashes,
        tables_hash=ctx.tables.version,
        stages=stages,
        package=package,
        started_at=started,
        finished_at=utc_now(),
    )


apply_line_rules = imaging.apply_line_rules
