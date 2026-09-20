# EXEC_PLAN — FIND-DX-0030

_Written by the improvement agent (claude-fable-5-1), 2026-09-20. Codes, counts and section names only; no encounter text._

One change serves FIND-DX-0030, FIND-DX-0006, FIND-DX-0020 and FIND-DX-0023; triage recorded a shared root cause.
Branch `codeloop/FIND-DX-0030`. FIND-DX-0010 shares the cause but is not addressed here (last section).

## Root cause

v0 codes a diagnosis for anything documented anywhere in the note. The coder removed these under the outpatient rule
that a visit is coded for what was assessed, managed or affecting care (coder guidelines section 3). Where the draft's
note evidence for the removed codes sits, over the batch1 occurrences:

| finding | what v0 coded | evidence location |
|---|---|---|
| FIND-DX-0020 (R42) | a review-of-systems positive | REVIEW OF SYSTEMS in 3 of 3 |
| FIND-DX-0023 (R63) | weight-change symptoms | HPI / review of systems in 3 of 3 |
| FIND-DX-0006 (M25) | joint symptoms beside the diagnosis that explains them | HPI / review of systems / exam |
| FIND-DX-0030 (Z87) | personal history that is simply recorded | social history or another non-assessment section in 3 of 5 |

## pipeline_cause

model_reasoning: the extractor lists every documented condition as a problem and the mapper codes each one
(`prompts/map_dx.txt` also maps every historical problem to a history Z-code). No deterministic stage separated what
the visit assessed from what the note merely records.

## Plan (as built)

A deterministic rule in `codeloop/rules/dx_rules.py` (`NOT_ASSESSED_CLASSES`, `drop_not_assessed`), hooked in the
pipeline after line mapping: a diagnosis of a listed class is un-coded when none of its note evidence lies in an
assessment/plan section (`codeloop/rules/sections.py`). Guards: recognizable section headers, note evidence present,
another diagnosis remains, no billed line is left without a pointer, first-listed re-chosen. A class is one accepted
finding, keyed by the ICD-10-CM categories the coder removed; classes are added as findings are accepted.

## What was tried first, and why this form

1. An extraction-level distinction (branch `codeloop/FIND-DX-0010`, kept for the record): the extractor stated a basis
   per problem (assessed / affects_care / mentioned_only) and the rules never coded mentioned-only problems. On 30
   batch1 encounters, one seed: agreement 0.671 -> 0.728 and dx precision 0.544 -> 0.710, but dx recall 0.954 -> 0.754.
   Two causes: any prompt change perturbs the problem descriptions, and the lexical ICD retrieval is sensitive to their
   wording (the right code dropped out of the candidates); and the basis is applied to every code, including many the
   coder left in place.
2. The general form of the present rule (every sign or symptom code), simulated on v0's seed-1 output: 32 false
   positives removed, 12 codes the coder kept lost. The reviewed labels keep many drafted symptom codes that the same
   coder's four blind labels do not contain, so the regression gate cannot accept the general form.
3. The classes built here, simulated the same way: 12 false positives removed, no kept code lost. Gate: PASS for all
   four findings (RESULTS.md in each task folder).

## Left open

- FIND-DX-0010 (R01, n=7): the coder kept the examination-only murmur code in three encounters reviewed early in the
  batch (D2N039, D2N078, D2N097) and removed it in seven reviewed later; in none of the ten does the assessment and plan
  mention it. A rule cannot reproduce both. It is a question for the coder; if he removes the three, adding `("R01",)`
  as a class fixes 6 of 7 with no kept code lost.
- The candidates with the same pattern (R10, R20, R22, R53, Z84 at n=2) become eligible with two occurrences in batch2
  (D3) and are then one line each in `NOT_ASSESSED_CLASSES`.
- `tests/` is not writable for the improvement agent, so unit tests for `drop_not_assessed` and
  `codeloop/rules/sections.py` have to be added on main after the merge.
