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

Normalized encounter text under `data/dev/` is committed (ACI-Bench is CC BY 4.0) and can be rebuilt with `make data`.
The committed public label files have the holdout rows removed; `reports/ingest.md` records the
license considerations for redistributing those subsets.

## Quick start

```bash
make install                     # uv sync (Python 3.12)
make test                        # pytest, including the holdout leakage and frozen-scorer tests
export CODELOOP_SEAL_KEY='...'   # owner only; at least 16 characters; never stored in the repo
export ANTHROPIC_API_KEY='...'   # LLM provider credential (never stored in the repo)
make tables                      # download pinned CMS/CDC tables and build data/tables/tables.sqlite
make data                        # rebuild data/dev from upstream using the committed holdout IDs
```

Key commands (see `codeloop --help` and `CODELOOP_SPEC.md` Appendix A):

```bash
codeloop run --version v0 --batch batch1 --seeds 1,2,3   # draft packages (code must match the tag; three seeds, see Operating notes)
codeloop review serve --batch batch1 --version v0 --coder-id cpc1   # CPC review UI (blind subset first)
codeloop labels build --batch batch1 --version v0   # replay events into data/labels/batch1.jsonl
codeloop findings extract --batch batch1            # candidate findings (D3 thresholds)
codeloop findings package FIND-DX-0001              # dataset + suites + task folder for the improvement agent
make gate TASK=FIND-DX-0001                          # merge gate (D5) -> tasks/FIND-DX-0001/GATE.md
codeloop version freeze v1                          # VERSION.md, tag, sealed holdout predictions (D7)
codeloop review serve --holdout-labeling --coder-id cpc1   # Phase 9 blind labeling of the sealed holdout
codeloop holdout verify-scorer && codeloop holdout score  # single-shot holdout scoring
codeloop report                                     # regenerate reports/
```

## Operating notes

- **Protecting the local UIs.** Set `CODELOOP_UI_USER` and `CODELOOP_UI_PASSWORD` before `codeloop review serve` or
  `codeloop audit serve` to require HTTP basic auth on every request (useful when the coder connects over a tunnel).
  Leave both unset for single-user local use; setting only one is refused.
- **Correcting a freeze.** Decisions and scope are locked at the freeze, and a version is frozen once. If a correction is
  unavoidable (for example the CPC's spot-check changes the scope before any batch is reviewed), run
  `codeloop freeze --supersede --reason "..."` or `codeloop version freeze v0 --supersede --reason "..."`. The previous
  tag survives as `freeze-provisional` / `v0-provisional` (numbered if repeated), the previous split, VERSION.md, sealed
  predictions and run outputs are renamed with the same suffix, a correction entry is appended to `ledger.md`, and a
  fresh freeze proceeds. Push with `git push --force origin --tags` afterwards.
- **Free-text ledger entries.** `codeloop ledger note "CPC onboarded"` appends a timestamped, attributed note.
- **Run batch drafts with three seeds** (`codeloop run --version vK --batch batchN --seeds 1,2,3`). The coder reviews the
  seed-1 drafts and mostly keeps them, so the labels are anchored to that one sample: on batch1, v0's dx recall is 0.946
  on seed 1 and 0.859 / 0.902 on seeds 2 and 3 of the identical pipeline. The gate reads every stored seed of the base
  version as one run; with only seed 1 stored, any three-seed head fails on recall for no reason of its own. Never
  leave a partial seed file in `runs/`: it would be read as a full base run.
- **Gating an improvement.** Work on a branch from main; `make gate TASK=…` takes the branch point as base (the
  `base_commit` in `task.yaml` predates the packaging commit, and the path check diffs base..head). Gate at the commit
  that holds only the code change, then commit `EXEC_PLAN.md`, `RESULTS.md`, `GATE.*` and the ledger entries. When one
  change serves several findings, gate each task at that same commit: another task's folder in the diff is a forbidden
  path. `tests/` is not writable for the improvement agent; tests for the change follow on main after the merge.
- **Task environment.** Start Docker, then
  `ANTHROPIC_API_KEY=… docker compose -f docker/compose.yaml run --rm -T task bash -lc '<command>'`. Inside it
  `data/sealed/` is empty, `codeloop/scoring`, `config/`, `data/labels` and the eval definitions are read-only, and
  the only reachable host is the LLM provider. Dependencies are baked into the image, so rebuild it
  (`docker compose -f docker/compose.yaml build task`) after `uv.lock` changes.
- **Pulling review events when `fly ssh` cannot connect:** `make fly-pull-events-exec BATCH=… VERSION=…` copies the
  store through the Machines API and verifies it by checksum (`scripts/fly_pull_events.py`).
- **Never try the hosted UI out by hand.** The coder id on every event is fixed by the deployment, so anything done on
  the live site is recorded as the coder's work, and a blind submit is final. Use `make ui-e2e` (headless Chrome on the
  synthetic corpus); `make fly-deploy-review` runs it first.
- **Coder guidelines** live in `docs/CODER_GUIDELINES.md` and must state the same evidence policy as decision D1.

## Hosting the coder UIs on Fly.io

`codeloop serve` is a single container entrypoint for either UI, configured by environment variables and always behind
basic auth (`CODELOOP_UI_USER` / `CODELOOP_UI_PASS`, refused if unset). State is written under `CODELOOP_DATA_DIR`
(`/data`, a Fly volume): review events to `/data/events/<version>_<batch>.sqlite`, audit responses to
`/data/audit/spot_check_responses.jsonl` (seeded from the repo copy on first start). The image (`Dockerfile.ui`) excludes
`data/sealed/` and `data/raw/`; the entrypoint never reads `CODELOOP_SEAL_KEY` and never serves holdout labeling.

```bash
fly auth login && fly apps create codeloop-ui && fly volumes create codeloop_data --size 1 --region iad
fly secrets set CODELOOP_UI_USER=cpc CODELOOP_UI_PASS='<strong password>'
make fly-deploy-audit                              # spot-check UI
make fly-pull-audit && uv run codeloop audit report
make fly-deploy-review BATCH=batch1 VERSION=v0     # review UI (blind subset first)
make fly-pull-events BATCH=batch1 VERSION=v0 && uv run codeloop labels build --batch batch1 --version v0
```

Pull events after a session ends (the coder tells you), not while they are working.

## Status

| Phase | State |
|---|---|
| 0 Seal | done (seed 20260917 confirmed by the owner) |
| 1 Contract and scorer | done |
| 2 Audit | done; CPC spot-check completed 2026-09-18 (imaging 9/15 confirmed, everything else below threshold) |
| 3 Freeze | done (`freeze` tag, superseded twice with ledger corrections); scope final: core_lines = in-office imaging billed as professional component (modifier 26), optional modules off |
| 4 v0 agent | done on `seed` and `spare` (`reports/calibration_dev_seed.md`) |
| 5 Scrubber and compliance | done (NCCI 2026Q4, MUE, MPFS RVU26D, ICD-10-CM FY2027) |
| 6 Review UI | done; deployed on Fly.io (`codeloop serve`) |
| 7 Harness | done; `v0` frozen with sealed holdout predictions |
| 8 Cycles | Cycle 0 done: batch1 reviewed by the CPC (45/45, 2026-09-20), 57 findings, four resolved in `v1` through the gate (PR #1: diagnoses documented only outside the assessment and plan), one ambiguous (FIND-DX-0010, a question for the coder); `v1` frozen with sealed holdout predictions. Cycle 1: v1 drafts for batch2 served at https://codeloop-ui.fly.dev; **CPC review of batch2 pending**. Open: v1 seeds 2 and 3 on batch2 (base runs for the next gate) |
| 9 Holdout | blind labeling and single-shot scoring await the CPC after v3 |
| 10 Reports | `codeloop report` regenerates everything that exists |

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
