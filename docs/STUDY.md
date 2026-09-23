# CodeLoop: what the study found

_Written 2026-09-23 by the build agent after the single-shot holdout score. Numbers come from `reports/holdout.md`,
`reports/index.md` and `ledger.md`. Codes and counts only; no encounter text._

## The question

Does a self-improvement loop, in which a certified professional coder (CPC) corrects an agent's coding drafts and an
improvement agent turns recurring corrections into gated pipeline changes, produce an agent that codes better on
encounters nobody has looked at? Four frozen versions (v0 to v3) were compared on 40 holdout encounters that were
encrypted before any encounter was read and coded blind by the same CPC at the end.

## The setup in one paragraph

167 development encounters (ACI-Bench dialogue plus note; scripted, no PHI) were split into three batches of 45 plus
seed and spare sets; 40 more were sealed as the holdout. Scope after the prevalence audit and the CPC's spot-check:
ICD-10-CM diagnoses and in-office imaging lines billed as the professional component. Each cycle: the current version
drafted a batch, the CPC reviewed every draft in a web UI (five encounters per batch coded blind first, for the
anchoring analysis), corrections were grouped into findings, findings that recurred were packaged as targeted evals,
an improvement agent changed the pipeline in a bounded container, and a gate (targeted error down at least 25%,
regression agreement down at most 1 point, recall down at most 2 points, scrubber and compliance clean) decided what
merged. Every merge, freeze, re-run and correction is in the ledger. The scorer was frozen before cycle 0 and its hash
verified before the holdout was opened.

## What each cycle changed

| cycle | finding | change | targeted error | regression agreement |
|---|---|---|---|---|
| 0 -> v1 | four findings, one cause: diagnoses documented only outside the assessment and plan were coded | deterministic rule after line mapping, one class per accepted finding | 1.0 -> 0.4 (and 0.58 -> 0.17, 0.89 -> 0.22, 1.0 -> 0.0) | 0.685 -> 0.720 |
| 1 -> v2 | E11 missed: the ICD candidate search dropped the condition's default code when the description carried qualifiers | a second, small mapping call for uncoded problems with the head term's candidates; no pointer-less lines | 0.917 -> 0.333 | 0.741 -> 0.735 |
| 2 -> v3 | a symptom coded where its documented cause was named (the CPC: "I usually code the cause if the cause is documented") | a separate mapping call offering candidates for the cause; recode only to a definitive code | 1.0 -> 0.75 | 0.764 -> 0.763 |

Each change passed the gate against a base of the previous version's stored drafts for every labeled batch (three
seeds). Two gate attempts in cycle 1 failed first and taught two things: changing the input of an LLM call that
already gives right answers re-samples every decision, so improvements have to be separate calls for the failing
cases; and a pre-existing scrubber error blocks any new diagnosis in that encounter at the compliance check.

## What the live batches showed

| version | batch | mean agreement with the reviewed label | zero-touch encounters | median review minutes |
|---|---|---|---|---|
| v0 | batch1 | 0.706 | 13 / 45 | 3.5 |
| v1 | batch2 | 0.873 | 28 / 45 | 2.4 |
| v2 | batch3 | 0.896 | 28 / 45 | 2.4 |

Agreement rose by 19 points across the cycles and the CPC touched fewer drafts. The error profile also moved: batch1
was dominated by removals (56 of 78 corrections removed a symptom or history code), batch2 by missed chronic
conditions (16 adds), batch3 by specificity swaps (7). Each cycle's fix held on the next batch: the four v1 rule
classes recurred at rates of 0.25, 0, 0 and 0 in batch2; the E11 fix left one miss in 13 drafted in batch3.

## What the holdout showed

| version | mean agreement with the blind label | hierarchical | dx recall | line recall |
|---|---|---|---|---|
| v0 | 0.369 | 0.416 | 0.535 | 1.000 |
| v1 | 0.362 | 0.408 | 0.509 | 0.833 |
| v2 | 0.368 | 0.422 | 0.553 | 1.000 |
| v3 | 0.346 | 0.395 | 0.518 | 1.000 |

Every pairwise difference has a paired-bootstrap 95% interval that includes zero; the largest is v0 to v3 at -0.023
(-0.061 to +0.015). With n = 40 the study can detect differences of roughly 4 points and larger, so the result is "no
detectable difference", not "equal".

## Why the two pictures differ: anchoring

The live agreements were measured against labels the CPC produced while looking at the version's own draft. The
holdout labels were produced with no draft in existence. The five-per-batch blind subset measured this gap before the
holdout was opened:

| batch | n | blind label vs reviewed label (same coder, same encounter) | agent vs blind | agent vs reviewed |
|---|---|---|---|---|
| batch1 (v0) | 4 | 0.510 | 0.308 | 0.527 |
| batch2 (v1) | 5 | 0.455 | 0.254 | 0.674 |
| batch3 (v2) | 5 | 0.524 | 0.367 | 0.798 |

The same coder agrees with himself at about 0.5 when he codes an encounter twice, once blind and once with a draft in
front of him. Against his blind labels the agent scores about 0.3, whichever version; against his reviewed labels it
scores 0.5 to 0.8, rising with each version. The improvements were real against reviewed labels and invisible against
blind ones. The holdout reproduced the blind number.

Two readings are compatible with the data, and the study cannot separate them:

1. The draft anchors the reviewer. He accepts what is drafted and adds little (few adds, one to three minutes per
   encounter against the eight to twelve the guidelines anticipated), so reviewed labels drift toward the draft and
   agreement measured against them overstates quality. The improvements then mostly moved drafts toward what the
   reviewer would accept, not toward what he codes unprompted.
2. The blind labels are themselves noisy. A single coder's blind-versus-reviewed agreement of 0.5 puts a low ceiling on
   any agent-versus-blind number; a second coder on part of the holdout (the spec's optional step, not arranged) would
   have shown whether 0.35 is far from or close to human-human agreement.

Either way, the pre-registered inferential claim rests on the holdout, and the holdout shows no version difference.

## What held up

- Process integrity: the holdout was sealed before anything else, never read, opened once; the scorer hash never
  changed; every gate result including the failed and void ones is in the ledger with hashes; the seal key left the
  owner's keychain only for the labeling window on a separate host, recorded and destroyed.
- The findings pipeline worked mechanically: corrections became findings, findings became evals, two of three cycles
  produced a change that passed a gate and held on the next batch.
- The cost was small: about 100 dollars of LLM calls in total by the ledger's estimates, less than that in fact since
  many re-runs were cache hits.

## What to do differently

- Measure against blind labels throughout, not only on five encounters per batch and the holdout. The anchoring gap
  was visible from batch1 and should have been the primary metric earlier.
- Use a second coder on a fixed subset from the start, to know the human ceiling.
- Size the holdout for the effect that matters: detecting a 3-point difference in mean agreement needs several times
  40 encounters.
- Keep review time honest: the guidelines expected 8 to 12 minutes per encounter; the coder spent 2 to 4. A pace or
  effort signal, or blind coding before every review, would have made the reviewed labels more independent of the
  draft.

## Where things are

- `reports/holdout.md`, `reports/holdout.json`: the scored holdout and bootstrap intervals; `runs/holdout/`: the
  plaintext export written at scoring time.
- `reports/index.md`: version by batch table, anchoring table, evidence support and query precision, findings log.
- `tasks/FIND-*/EXEC_PLAN.md` and `RESULTS.md`: what each cycle tried and why it took the form it did.
- `ledger.md`: the chronology, with hashes.
