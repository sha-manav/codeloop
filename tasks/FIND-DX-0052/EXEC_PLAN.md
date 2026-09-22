# EXEC_PLAN — FIND-DX-0052

_Written by the improvement agent (claude-fable-5-1), 2026-09-22. Codes, counts and section names only; no encounter text._

Branch `codeloop/FIND-DX-0052`. One change; the candidates FIND-DX-0055 (I10), FIND-DX-0056 (I50) and FIND-DX-0069 (R73)
share the cause and are expected to move with it, but only FIND-DX-0052 is packaged and gated.

## Root cause

The coder added E119 in four batch2 encounters (D2N046, D2N135, D2N152, D2N193) that v1 drafted without it. The v1
seed-1 traces show the loss is not in extraction: the diabetes problem is listed in 4 of 4 (status active, note quotes
in 3 of 4). It is in ICD-10-CM candidate retrieval. `IcdRetriever.candidates_for_problem` runs FTS5 BM25 with every
token of the description OR-ed, and a description that carries a qualifier ("..., currently under control", "... with
elevated blood glucose and hemoglobin A1c", "Type 2 diabetes, stable with medication") retrieves the qualifier's codes:
gestational diabetes by "control", abnormal-glucose codes by the lab words, diabetic retinopathy by a long token
overlap. E119 is never among the 12–18 candidates offered. `prompts/map_dx.txt` tells the mapper to choose only from
the candidates, and its cached rationale says so in each case: the code it wanted was not offered, so it returned null
(D2N152, D2N193) or settled for R7309 (D2N135, later recoded to E119 by the coder).

The same mechanism, on the same batch: I10 missing in D2N168 and D2N172 ("Hypertension, not controlled",
"Hypertension (high blood pressure), well controlled"), I509 missing in D2N004 and D2N093 (every heart-failure
candidate specified a type). Re-running the retriever offline on the eight problem descriptions reproduced all eight
misses.

D2N046 is the exception: the note does not mention diabetes (dialogue only), so under the note-only evidence policy the
mapper's null is by design. The change offers E119 there too; whether the mapper codes it is the policy's call, and the
targeted error floor for this finding is therefore 0.25 if the policy holds.

## pipeline_cause

tool_data_gap (recorded on the finding as `retrieval`): the deterministic candidate search, not the model and not a rule.

## Plan (as built)

Two files: `codeloop/tools/icd_retrieval.py` (`head_term`, `retry_candidates`, `category_defaults`, `wide_candidates`)
and `codeloop/agent/pipeline.py` (a retry stage between line mapping and the not-assessed rule).

The first `map_dx` call is exactly v1's: same candidates, same prompt, same decisions (and, for stored seeds, the same
cached response). After line mapping, active problems the first pass left uncoded — and, under the note-only policy,
only those with note evidence — go to one second, smaller `map_dx` call:

- an uncoded problem gets the best hits for its **head term**, the text before its first comma, semicolon, colon,
  "with", "without", "due to", "secondary to", "status post" or parenthetical ("Diabetes, currently under control" ->
  "Diabetes"; "Hypertension (high blood pressure), well controlled" -> "Hypertension"), minus anything already offered
  (at most eight);
- an uncoded problem that a billed line points at gets a **wider net** (deeper hits with and without qualifiers, the
  head term, the retrieved categories' "unspecified" / "without complications" defaults; at most 24), because a line
  without a coded indication is structurally invalid (spec section 8).

A coded retry replaces the null decision through the same `apply_dx_rules`; the first-listed diagnosis stays with the
first pass. A line whose indication is coded on retry gets its pointer. A line whose indication still has no code
points at the first-listed diagnosis with a data gap saying so; dropping it would bill nothing for a documented,
evidenced service, and the coder kept and re-pointed every such line in batches 1 and 2. The retry stage
(`map_dx_retry`) appears in the trace only when it did something, so v1 traces are unchanged.

On the v1 batch2 seed-1 traces this retries 31 of 262 problems in 24 of 45 encounters. The retry candidates carry E119
or I10 for the four target problems whose note names the condition (D2N152, D2N193, D2N168, D2N172). D2N046
(dialogue-only evidence) is not retried, and D2N135 (coded R7309 on the first pass) is not retried either, so the
targeted error rate for this finding cannot fall below 0.5 by this change alone.

## What was tried first, and why this form

1. **Appending candidates to every list** (commit `4c94745`, gated at `2904fa8 -> 4c94745`): head-term hits plus the
   "unspecified" / "without complications" defaults of every retrieved category, appended after the unchanged base list
   (mean list 14.9 -> 18.8, the missing code offered in 8 of 8 cases). Targeted error 0.917 -> 0.333, but the gate
   FAILED on regression agreement 0.741 -> 0.702 and on one compliance escalation. Two causes, both visible in the
   per-encounter diff of base against head (codes and counts only):
   - a longer candidate list changes the mapping prompt for the whole encounter, so every decision is re-sampled; the
     labels are anchored to the stored seed-1 drafts, and seed 1 alone fell from 0.805 to 0.733;
   - the "unspecified" defaults pulled the mapper from typed heart-failure codes to I509 in encounters the coder had left
     alone (D2N014 I5020 -> I509, D2N035 I5030 -> I509), and offered I10 for hypertension the coder does not code when it
     is only in the history (D2N087, D2N131, D2N175).
2. **Retry of uncoded problems, head term only** (commit `c347e89`, gated at `2904fa8 -> c347e89`): agreement
   0.741 -> 0.732, dx recall 0.833 -> 0.867, line recall and scrubber unchanged, targeted 0.917 -> 0.333; FAILED only
   on compliance escalation (2). Both failures were v1's own pointer-less imaging lines (D2N093 seed 2, D2N195 seed 3):
   the check fails any new diagnosis in an encounter with a scrubber error, and the retry had added a correct diagnosis
   (E109, I10) there. The stored v1 runs hold five such line-seeds (D2N093, D2N116, D2N195); in every one the coder kept
   the line and gave it a pointer.
3. **This form**: the retry moves after line mapping so it knows which uncoded problems a line depends on, tries harder
   for those, and no line leaves the pipeline without a pointer.

A hand list of condition -> default code would fix these eight and nothing else; the head-term mechanism is general.

## Left open

- `tests/` is not writable here; unit tests for `head_term` and `category_defaults` go on main after the merge.
- Whether the coder's E119 on D2N046 (dialogue-only evidence) is consistent with the note-only policy is a question for
  the owner and coder, not for the pipeline.
