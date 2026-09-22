# RESULTS — FIND-DX-0039

_Written by the improvement agent (claude-fable-5-1), 2026-09-22. Codes and counts only; no encounter text._

Gate: **PASS** (`tasks/FIND-DX-0039/GATE.md`), base `78a2317` -> head `330e940`, three runs (seeds 1, 2, 3), run inside the
task environment. Second gate run: the first (base `45c7bee`) reported PASS with a base agreement of 0.228, because the
packaged task carried the base version of the batch the finding was first seen in (v0 on batch1, 45 encounters) against
a 135-encounter head; that result is void and recorded as such in the ledger. Packaging now uses the version under
review (v2), and the gate was rerun. The head runs were identical (cache hits).

| metric | before (base, v2) | after (head) |
|---|---|---|
| targeted error rate | 1.000 (runs [1.0, 1.0, 1.0]) | 0.750 (runs [0.75, 0.75, 0.75]) |
| regression mean agreement | 0.7637 (runs [0.827, 0.728, 0.737]) | 0.7631 (runs [0.825, 0.726, 0.739]) |
| dx recall | 0.860 | 0.860 |
| line recall | 0.977 | 0.977 |
| scrubber errors (mean per run) | 0.0 | 0.0 |
| escalation failures | 0 | 0 |

grader_changed: false

The base is v2's stored predictions on batch1, batch2 and batch3 for seeds 1–3 (batch1 and batch2 run at tag v2 in a
worktree; all cache hits). The regression suite is `regression-through-batch3` (135 labeled encounters).

## What the head changes, against the base, over the three seeds

- Twelve encounter-seeds change, all by one recode of a symptom to the documented cause; nothing is added or removed
  otherwise. R0981 -> J302 or J309 in D2N008, D2N089, D2N095, D2N130 (every seed where the cause phrase was extracted),
  R0981 -> J302 in D2N168 (seed 3, in the coder's label), R0602 -> J309 in D2N170 (seed 2).
- Against the labels: D2N130 becomes right on every seed (J309); D2N168 on seed 3. D2N095 gets J302 where the coder
  chose J309 (still one wrong field). D2N008 and D2N089 move against their labels, as expected from the coder's stated
  rule ("I usually code the cause if the cause is documented") and accepted at triage. Net agreement -0.06pp.
- The targeted error rate falls from 1.0 to 0.75 and meets the 25% relative-reduction requirement exactly. Of the four
  fields, D2N130's J309 is fixed; D2N095's J309 is missed by specificity (J302 selected); D2N138's two fields (J309 ->
  J302 by the coder in batch1) are a specificity edit between two rhinitis codes, not a symptom-to-cause case, and this
  change cannot reach them. The finding's key (specificity, J30) lumps two different corrections; the cause-term retry
  addresses the one the coder confirmed as a rule.
- The pain-with-injury cases (D2N054, D2N150) did not recode: the cause candidates for "Lisfranc fracture" are stress
  fractures (no index match) and the knee case names no cause phrase; the mapper returned null, so the symptom stayed.
  That is the acceptance filter working as intended.

## Diff summary

`codeloop/tools/icd_retrieval.py`: `cause_term`, `is_symptom_code`, `is_definitive_code`, `cause_candidates` (FTS hits
for the cause term with inflection variants, plus category defaults; definitive codes only).

`codeloop/agent/pipeline.py`: inside the `map_dx_retry` stage, after the cycle-1 retry, a separate `map_dx` call (same
prompt file) for symptom-coded active problems whose description names a cause; the decision is replaced only when the
mapper selects a definitive condition code different from the symptom; line pointers follow; first-listed is inherited.
The first mapping call and the cycle-1 retry call are unchanged.

Prompts, schemas, rules, extraction, scoring, compliance and the scrubber are untouched.

## Escalations

None. Every recode carries the problem's note evidence; no head package has a scrubber error.

## Left open

- The two labels that kept the symptom code (D2N008, D2N089) now disagree with the draft; if the coder reviews them
  again under his stated rule they would change, but labels are final for this study.
- FIND-DX-0080 / FIND-DX-0082 (symptoms coded by the cycle-1 retry beside a coded diagnosis) are not addressed.
- Unit tests for the new functions go on main after the merge (`tests/` is not writable here); a draft exists.
