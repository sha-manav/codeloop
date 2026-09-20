# RESULTS — FIND-DX-0006

_Written by the improvement agent (claude-fable-5-1), 2026-09-20. Codes and counts only; no encounter text._

Gate: **PASS** (`tasks/FIND-DX-0006/GATE.md`), base `05b6e64` -> head `9d30187`, three runs (seeds 1, 2, 3), run inside the task
environment. The same head serves FIND-DX-0006, FIND-DX-0020, FIND-DX-0023 and FIND-DX-0030; each was gated separately.

| metric | before (base, v0) | after (head) |
|---|---|---|
| targeted error rate | 0.583 | 0.167 (runs [0.5, 0.0, 0.0]) |
| regression mean agreement | 0.6852 | 0.7195 |
| dx recall | 0.9021 | 0.9021 |
| line recall | 1.0 | 1.0 |
| scrubber errors | 0.667 | 0.667 |
| escalation failures | 0 | 0 |

grader_changed: false

The base figures are the mean of three stored v0 runs. v0 had only seed 1 stored when this task was packaged; seeds 2
and 3 were run at tag v0 (commit `05b6e64`, all cache hits) because a three-seed head was otherwise compared with the
single sample the coder's labels are anchored to (first gate attempt at `0b9b92c`: FAIL on dx recall and scrubber, with
no true positive lost on seed 1; recorded in the ledger and in commit `273e1e6`). The 0.667 scrubber errors on both
sides are one encounter on seeds 2 and 3 where v0 codes no diagnosis for a billed line to point at; the change neither
causes nor fixes it.

## Diff summary

`codeloop/rules/sections.py` (new), `codeloop/rules/dx_rules.py`, `codeloop/agent/pipeline.py`. Prompts, schemas and
extraction are untouched, so every code outside the rule's classes is exactly what v0 produces.

A deterministic rule after line mapping un-codes a diagnosis of a listed class (joint symptom codes (M25.3-M25.6) for this finding: joint symptoms from the HPI, review of systems or examination, coded beside the definitive diagnosis that explains them)
when none of its note evidence lies in an assessment/plan section. It fires only when the note has recognizable section
headers and the diagnosis has note evidence, when another diagnosis remains coded, and never leaves a billed line
without a pointer (for joint symptoms the line follows to the definitive diagnosis; otherwise the diagnosis stays).
The first-listed diagnosis is chosen again if it was the one dropped.

## What was tried first, and why this form

See `tasks/FIND-DX-0030/EXEC_PLAN.md`.
