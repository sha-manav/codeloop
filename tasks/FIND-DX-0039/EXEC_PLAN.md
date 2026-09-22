# EXEC_PLAN — FIND-DX-0039

_Written by the improvement agent (claude-fable-5-1), 2026-09-22. Codes, counts and section names only; no encounter text._

Branch `codeloop/FIND-DX-0039`. Third and last improvement cycle (v2 -> v3).

## Root cause

The coder replaced the nasal-congestion symptom code (R0981) with allergic rhinitis (J309) in D2N095 and D2N130 (batch3)
and recoded J309 to J302 in D2N138 (batch1). In the v2 traces the extractor frames each of these problems as the
symptom and names its documented cause in the same description ("Nasal congestion attributed to seasonal allergies");
candidates are retrieved for the whole description, the symptom code ranks first, and the mapper selects it. The same
shape appears in the pain-with-a-documented-injury cases (D2N054 foot pain due to a fracture -> M79671; D2N150 knee pain
after an injury -> M25561; FIND-DX-0077/-0078/-0083/-0084, candidates).

The finding was first set to ambiguous: in the same batch the coder kept R0981 in D2N008 and D2N089, whose descriptions
have the same shape and whose evidence sits in the same kind of section (outside the assessment and plan in all four).
The owner relayed the question and the coder answered: "I usually code the cause if the cause is documented." The
finding was accepted on that rule; the two labels that kept the symptom stand as labeled and are expected to move
against their labels.

Across the v2 seed-1 drafts of all three batches, 16 symptom-coded problems carry a causal phrase. Six of them the coder
replaced or removed; the ten kept include five where the "cause" is not a condition at all (murmur "unchanged from prior
exam", pain "from elbow up to the neck", cough "attributed to recent congestion", blood pressure "attributed to pain",
knee pain "attributed to lifting heavy bags") and the two allergy cases above.

## pipeline_cause

model_reasoning, with a retrieval contribution: the mapper is offered the symptom's candidates, not the cause's.

## Plan (as built)

`codeloop/tools/icd_retrieval.py`: `cause_term` (the text after "attributed to", "due to", "secondary to", "caused by",
"related to", or "from" when it is not "unchanged from" / "shifted from" / "changed from" and the phrase has no "to";
parentheticals stripped; at most six words), `is_symptom_code` (R chapter, M255, M256, M796), `is_definitive_code`
(chapters A–Q and S–T, never a symptom, U, V–Y or Z code), `cause_candidates` (FTS hits for the cause term with light
inflection variants, since the index has no stemmer and "allergies" alone retrieves nothing, plus the retrieved
categories' default codes; definitive codes only).

`codeloop/agent/pipeline.py`, inside the `map_dx_retry` stage after the cycle-1 retry: a symptom-coded active problem
with a cause term and note evidence goes to a separate, small `map_dx` call (same prompt file) offering the cause
candidates. The symptom decision is replaced only when the mapper selects a definitive condition code different from the
symptom; line pointers follow the recode; first-listed is inherited; the stage records `symptoms with a documented cause
retried: n, recoded: m`. The first mapping call and the cycle-1 retry call are unchanged, so nothing outside the
triggered problems can move.

## Why this form

- The cycle-1 lesson: never change the input of a call that already gives right answers; add a call for the failing
  cases. The trigger is narrow (six problems per 135 encounters) and the acceptance filter narrower.
- Offering the cause's candidates and letting the mapper decide keeps the choice evidence-bound: for "lifting heavy
  bags" or "recent congestion" the candidates do not describe the documented problem and the mapper is expected to
  return null, which leaves the symptom code in place.
- A hand rule (R0981 with allergies -> J309) would fix these three and nothing else.

## Left open

- The pain-with-injury cases depend on the mapper choosing an injury code from the cause candidates; "Lisfranc
  fracture" retrieves stress-fracture codes only (no index term match), so D2N054 may stay as it is.
- Two symptoms coded by the cycle-1 retry and removed by the coder as integral to the coded diagnosis (FIND-DX-0080,
  FIND-DX-0082): the retry call does not see the encounter's coded diagnoses. Not addressed here; a candidate for a
  later change would pass the coded diagnoses as context into that call.
- Unit tests for `cause_term`, `is_definitive_code` and `cause_candidates` go on main after the merge.
