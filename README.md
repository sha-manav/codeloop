# CodeLoop

An outpatient professional-coding agent wrapped in a self-improvement harness. The agent reads a
doctor–patient dialogue plus the resulting clinical note and emits a coding package: ICD-10-CM
diagnoses (specificity, laterality, historical-vs-active), in-scope CPT/HCPCS lines with
modifiers, units and diagnosis pointers, and an evidence span for every predicted field. A
certified professional coder corrects drafts in a review UI; recurring corrections become
findings, findings become targeted evals, an improvement agent modifies the pipeline inside a
bounded task environment, and changes merge only through a gate. Four frozen versions (v0–v3)
are compared on 40 sealed, blind-coded holdout encounters.

The full specification is `CODELOOP_SPEC.md`; the rules for agents working here are `CLAUDE.md`;
decisions are `DECISIONS.md` (rendered from `config/project.yaml`); the chronology is `ledger.md`.

## Things to state plainly

- **Encounters are scripted or role-played** (ACI-Bench), not real patients; there is zero PHI.
- **Public ICD label sets exist for the holdout encounters.** They were filtered out at seal time
  and the improvement agent has no route to them, but underlying models may have seen them in
  pretraining. Holdout labels are produced fresh by the project's CPC under the project's scope.
- **Under the `note_only` evidence policy, dialogue drives provider queries, not billable fields.**
  That is the compliant reading and is what the showcase demonstrates.
- **Speaker tags in some ACI-Bench subsets are swapped by ASR**, so "who provided counseling" is
  unreliable evidence; the vaccine module treats it as such.
- **The 75/90/100 agreement tiers are descriptive**; the inferential claim rests on mean
  per-encounter agreement with paired bootstrap CIs at n = 40 (decision D9).
- **CodeLoop codes documented diagnoses and services.** ACI-Bench's stated intended use is
  benchmarking dialogue summarization, not training diagnostic models; nothing here trains a
  model or diagnoses anyone.
- **No CPT descriptors are stored or prompted.** Code numbers only.

## Data sources and licenses

| Source | Use | License |
|---|---|---|
| ACI-Bench (figshare v1, doi:10.6084/m9.figshare.22494601.v1; code: github.com/wyim/aci-bench) | all 207 encounters | CC BY 4.0 |
| amazon-science/toward-clinical-coding-verification-adaptation (EMNLP 2025 Industry) | ICD-10-CM calibration on the 167 dev encounters | CC BY-NC 4.0 |
| MedCodER dataset (Zenodo, doi:10.5281/zenodo.13308316) | ICD-10 + evidence calibration on the 167 | CC BY-NC-ND 4.0 |

Cite: Yim W, Fu Y, Ben Abacha A, Snider N, Lin T, Yetisgen M. *ACI-BENCH: a Novel Ambient Clinical
Intelligence Dataset for Benchmarking Automatic Visit Note Generation.* Sci Data 10, 586 (2023).

Normalized encounter text under `data/dev/` is gitignored by default and rebuilt with `make data`.
The committed public label files have the holdout rows removed; `reports/ingest.md` records the
license considerations for redistributing those subsets.

## Quick start

```bash
make install                     # uv sync (Python 3.12)
make test                        # pytest, including the holdout leakage test
export CODELOOP_SEAL_KEY='...'   # owner only; at least 16 characters; never stored in the repo
make seal                        # Phase 0, exactly once
make data                        # later: rebuild data/dev from upstream using the committed IDs
```

## Phases

| Phase | Deliverable | Gate |
|---|---|---|
| 0 | Seal: holdout drawn and encrypted before any encounter is read; dev + public labels; leakage test | owner confirms D0 seed, stores the key outside the repo |
| 1 | Schemas, canonicalizer, scorer, bootstrap, `codeloop score` | — |
| 2 | Prevalence audit over the 167; CPC spot-check; `scope.yaml` | CPC spot-check; owner commits scope |
| 3 | Freeze: dev split, difficulty index, hashes, `freeze` tag, `DECISIONS.md` | owner signs off D0–D10 |
| 4 | v0 agent on the `seed` split | — |
| 5 | Scrubber and compliance | — |
| 6 | Review UI, event store, `labels build` | — |
| 7 | Eval harness, findings, task environment, gate, versioning, sealed holdout predict; `version freeze v0` | v0 frozen; CPC onboarded |
| 8 | Three improvement cycles (v1–v3) | each triage and merge |
| 9 | Holdout: verify scorer, blind labeling, single-shot scoring | owner confirms sealed predictions and scorer hash |
| 10 | Reports | — |
