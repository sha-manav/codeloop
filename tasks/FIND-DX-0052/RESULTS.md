# RESULTS — FIND-DX-0052

_Written by the improvement agent (claude-fable-5-1), 2026-09-22. Codes and counts only; no encounter text._

Gate: **PASS** (`tasks/FIND-DX-0052/GATE.md`), base `2904fa8` -> head `5b4e825`, three runs (seeds 1, 2, 3), run inside the
task environment. Third attempt; the two failed attempts and their causes are in `EXEC_PLAN.md` and the ledger.

| metric | before (base, v1) | after (head) |
|---|---|---|
| targeted error rate | 0.917 (runs [1.0, 0.75, 1.0]) | 0.333 (runs [0.5, 0.25, 0.25]) |
| regression mean agreement | 0.7407 (runs [0.805, 0.701, 0.716]) | 0.7348 (runs [0.792, 0.705, 0.708]) |
| dx recall | 0.833 | 0.867 |
| line recall | 0.988 | 0.988 |
| scrubber errors (mean per run) | 1.667 | 0.0 |
| escalation failures | 0 | 0 |

grader_changed: false

The base is v1's stored predictions on batch1 and batch2 for seeds 1–3 (batch1 was run at tag v1 for this suite; all
cache hits). The regression suite is `regression-through-batch2` (90 labeled encounters).

## What the head changes, against the base, over the three seeds

- Nothing is removed: no diagnosis or line present in the base is absent from the head (the first `map_dx` call is
  unchanged, and only a null can become a code).
- 62 of 270 encounter-seeds gain at least one diagnosis. 71 codes are added: 24 are in the coder's label, 47 are not.
  The additions the coder also made are E11 (11), I10 (10) and E10 (3). The additions he did not make are led by I10
  (14): hypertension documented in the history of an encounter about something else, which the coder does not code.
  That is the precision cost of the retry and the reason mean agreement moves by -0.6pp while dx recall moves by +3.4pp.
- The five pointer-less imaging lines of the base (D2N093, D2N116, D2N195 across seeds 2 and 3) are gone: two got their
  pointer because the retry coded the line's indication, three point at the first-listed diagnosis with a data gap
  saying the indication could not be coded. Scrubber errors go from 1.667 per run to 0.
- Targeted: E119 is now drafted in D2N152 and D2N193 on every seed and in D2N046 on seeds 2 and 3 (where the extraction
  quoted the note). D2N135 stays wrong on every seed: the first pass codes R7309 there, and a coded problem is not
  retried (FIND-DX-0069, candidate).

## Diff summary

`codeloop/tools/icd_retrieval.py`: `head_term`, `retry_candidates` (head-term hits not offered on the first pass),
`category_defaults`, `wide_candidates` (for a problem a billed line depends on). `candidates_for_problem` is unchanged.

`codeloop/agent/pipeline.py`: a `map_dx_retry` stage after line mapping, present in the trace only when it acted. One
extra `map_dx` call (same prompt file) for active, note-evidenced problems the first pass left uncoded; a coded retry
replaces the null through the same `apply_dx_rules`; first-listed stays with the first pass. Lines whose indication is
coded on retry get their pointer; lines whose indication still has no code point at the first-listed diagnosis with a
data gap; a line is dropped only when the encounter has no coded diagnosis at all (did not occur).

Prompts, schemas, rules, extraction, scoring, compliance and the scrubber are untouched.

## Escalations

None. The head adds diagnoses only with note evidence under the note-only policy, and no head package has a scrubber
error.

## What was tried first, and why this form

See `tasks/FIND-DX-0052/EXEC_PLAN.md`. Two lessons for the next cycle, recorded there: changing the input of an LLM call
that already gives right answers re-samples every decision (the labels are anchored to the stored seed-1 drafts), and a
pre-existing scrubber error blocks any new diagnosis in that encounter at the escalation check.

## Left open

- The I10 additions the coder does not make (history-only hypertension) are the same "documented but not assessed"
  family as v1's rule classes; whether I10 joins `NOT_ASSESSED_CLASSES` is a question for a future finding, not for
  this task (14 not in label against 10 in label over three seeds).
- Unit tests for `head_term`, `retry_candidates`, `category_defaults` and `wide_candidates` go on main after the merge
  (`tests/` is not writable here); a draft exists.
- FIND-DX-0055 (I10) and FIND-DX-0056 (I50) are expected to move on batch3; FIND-DX-0069 (R7309 for diabetes) is not
  addressed.
