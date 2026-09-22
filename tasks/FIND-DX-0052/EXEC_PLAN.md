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

`codeloop/tools/icd_retrieval.py` only. `candidates_for_problem` keeps its previous list unchanged (same codes, same
order) and appends up to ten more candidates for non-historical problems:

1. the best hits for the description's **head term** — the text before its first comma, semicolon, colon, "with",
   "without", "due to", "secondary to", "status post", or parenthetical ("Diabetes, currently under control" ->
   "Diabetes"; "Hypertension (high blood pressure), well controlled" -> "Hypertension"), at most five;
2. the **category defaults** of the categories already retrieved (the first six base hits and the first three head hits,
   at most five categories): the 3-character category itself when billable (I10), then the nearest descendants whose
   description says "unspecified" or "without complications" (E119, I509), at most two per category.

Checked offline on the 262 batch2 seed-1 problems: every previous candidate is retained in its position; the mean list
grows from 14.9 to 18.8 (max 28); the missing code is offered in 8 of 8 cases. Prompts, schemas, rules and extraction are
untouched, so the only change the mapper sees is a few more candidates at the end of each list.

## Why this form

- The cycle-0 lesson holds: any prompt change perturbs problem descriptions and the lexical retrieval, costing recall.
  Extending the candidate list is the smallest intervention that lets the mapper make the choice it already says it
  wants to make.
- A hand list of condition -> default code (diabetes -> E119, hypertension -> I10) would fix these eight and nothing
  else; the head-term and category-default mechanism is general across chapters.
- Appending rather than re-ranking keeps every existing correct selection reachable; the gate's regression checks
  whether the longer lists disturb the mapper elsewhere.

## Left open

- `tests/` is not writable here; unit tests for `head_term` and `category_defaults` go on main after the merge.
- Whether the coder's E119 on D2N046 (dialogue-only evidence) is consistent with the note-only policy is a question for
  the owner and coder, not for the pipeline.
