# EXEC_PLAN — FIND-DX-0010

_Written by the improvement agent (claude-fable-5-1), 2026-09-20. Codes, counts and section names only; no encounter text._

This plan also covers FIND-DX-0006, FIND-DX-0020, FIND-DX-0023 and FIND-DX-0030: triage recorded one shared root
cause for the five, and one change addresses them. The work lives on branch `codeloop/FIND-DX-0010`; each of the five
tasks is gated against the same head.

## Root cause

v0 codes a diagnosis for anything documented anywhere in the note. The coder removed these under the outpatient rule
that a visit is coded for what was assessed, managed or affecting care (coder guidelines §3):

| finding | what v0 coded | where its note evidence sits (batch1 occurrences) |
|---|---|---|
| FIND-DX-0010 (R01) | a murmur heard on examination | PHYSICAL EXAM in 7 of 7 (one also in the assessment) |
| FIND-DX-0020 (R42) | a review-of-systems positive | REVIEW OF SYSTEMS in 3 of 3 |
| FIND-DX-0023 (R63) | weight-change symptoms | HPI / review of systems |
| FIND-DX-0006 (M25) | joint symptoms beside the diagnosis that explains them | HPI / review of systems / exam |
| FIND-DX-0030 (Z87) | personal history that is simply recorded | social history or a passing mention; status historical |

`prompts/extract.txt` asked for "every condition the clinician assessed or addressed … plus documented personal history",
but the extractor listed everything it saw and nothing downstream separated assessed from mentioned.
`prompts/map_dx.txt` told the mapper to give every historical problem a history Z-code.

## pipeline_cause

model_reasoning (the extractor does not separate assessed from mentioned), with a rule gap: no deterministic stage
enforced the distinction.

## Plan

1. Extraction states, per problem, the basis on which it would be coded: `assessed`, `affects_care`,
   `mentioned_only`, each defined in the prompt; and `integral_to`, the index of the assessed problem that explains a
   symptom or sign.
2. Deterministic rules, not the mapper, decide: a `mentioned_only` problem is never coded and never reaches the
   mapper; a symptom marked `integral_to` another problem goes to the mapper and is dropped only if that problem ends
   up coded (a symptom is integral to a *coded* diagnosis), otherwise it is what the documentation supports; a line
   that pointed at a dropped symptom points at the explaining diagnosis.
3. Keep both prompts as the v0 text plus these additions, and keep the description a look-up term, because the lexical
   ICD retrieval is sensitive to its wording.

## Status (head bdc89ac, base ba0a30d; one seed; not yet gated)

Targeted error rate, measured at 8243dd6 (bdc89ac only adds the pointer redirection, which does not touch diagnoses;
base is 1.0 on every suite by construction): FIND-DX-0010 0.00, FIND-DX-0030 0.00, FIND-DX-0020 0.00,
FIND-DX-0023 0.00, FIND-DX-0006 0.50.

Regression, on the 30 of 45 batch1 encounters that completed before the provider account ran out of credit
(`LLMProviderError … credit balance is too low` on the other 15), scored with the frozen scorer:

| metric | base (v0) | head |
|---|---|---|
| mean agreement | 0.671 | 0.728 |
| dx precision | 0.544 (fp 52) | 0.710 (fp 20) |
| dx recall | 0.954 (fn 3) | 0.754 (fn 16) |
| line recall | 1.000 | 0.900 |
| first-listed accuracy | 0.800 | 0.900 |
| scrubber errors | 0 | 0 |

The head would fail the gate on `regression_dx_recall` (allowed drop 2.0 pp). What the diagnostics
(`trace_basis.py`, `compare_extractions.py`) show about the lost true positives so far:

- retrieval: a longer description drops the right code from the candidates. Fixed for the cases seen (8243dd6);
  needs re-checking on the full batch.
- mapper variation between sibling codes once the extraction wording shifts (E119/E1165, R310/R319, Z9849/Z98890).
- conditions the extractor marks `mentioned_only` that the coder kept (for example I517, F419). Some of these may be
  codes the coder left in place rather than confirmed; the gate counts them either way.

## Next steps

1. Provider credit restored, then the full regression suite with one seed on the current head.
2. List every lost true positive with its basis and whether the gold code was among the candidates; tighten the
   `assessed` definition for chronic conditions and results findings only where the evidence supports it.
3. Three seeds, then `make gate` for each of the five tasks with `BASE=ba0a30d`, the commit on main this branch starts
   from (`task.yaml` records the commit before the packaging outputs and the task-environment fix existed, and the
   path check diffs base..head, so it would reject those files).
4. RESULTS.md per task; branch pushed; PR for the owner to review and merge.
