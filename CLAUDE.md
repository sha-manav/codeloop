# CLAUDE.md — rules for any agent working in this repository

This file governs the build-time agent (constructing CodeLoop from `CODELOOP_SPEC.md`) and the
improvement agent (working inside a bounded task environment in Phase 8). `AGENTS.md` is a symlink
to this file. Read `CODELOOP_SPEC.md` §0 before doing anything; the invariants there are the point.

## What this repository is

CodeLoop is an outpatient professional-coding agent (ICD-10-CM diagnoses plus in-scope CPT/HCPCS
lines with evidence spans) wrapped in a self-improvement harness: coder corrections become
findings, findings become targeted evals, an improvement agent changes the pipeline, a gate
decides what merges, and four frozen versions are compared on 40 sealed holdout encounters.
The evidentiary value depends on process integrity more than on the agent.

## Hard rules (every agent, every phase)

1. **The holdout is opaque.** Never decrypt, read, print, summarize, sample from, or reason about
   the 40 holdout encounters, their predictions, or their labels. `data/sealed/` holds ciphertext
   and content hashes only. `data/splits/holdout_ids.txt` is a deny-list: never write a holdout
   ID anywhere except `data/splits/` and `data/sealed/`. `tests/test_no_holdout_leakage.py`
   enforces this and must stay green.
2. **`codeloop seal` runs once.** Never delete or regenerate `data/splits/holdout_ids.txt`,
   `data/sealed/*`, or `ledger.md` entries. If the owner decides to re-seal, that is their action,
   recorded in the ledger.
3. **No encounter text in output.** CLI output, logs, reports, test fixtures, commit messages and
   findings carry counts, IDs (non-holdout), codes, offsets and hashes; never note or dialogue
   text from the corpus. Tests use synthetic text only.
4. **No CPT descriptors.** CPT descriptor text is AMA-licensed: code numbers only in code, prompts,
   tables, fixtures, docs and commit messages. ICD-10-CM and HCPCS Level II descriptions (public
   domain) are fine.
5. **Frozen scorer.** After the `freeze` tag exists, `codeloop/scoring/` is read-only; its tree hash
   is recorded in `ledger.md` and checked by `tests/test_scoring_frozen.py`.
6. **Holdout scored once.** `codeloop holdout score` writes `data/sealed/SCORED.lock` and refuses to
   run again. Never remove the lock.
7. **`ledger.md` is append-only.** Corrections are new entries.
8. **Decisions live in `config/project.yaml`.** `DECISIONS.md` is rendered from it
   (`make decisions`). After the Phase 3 freeze, decisions D0–D10 are locked.
9. **Pin everything.** Model IDs, sampling settings, prompt hashes, scope hash, table versions and
   dataset URLs/hashes are recorded, never implied. Verify a model ID against provider docs
   before pinning it.
10. **`data/raw/` is never committed** and is deleted after filtering. `make data` rebuilds
    `data/dev/` from upstream using the committed holdout IDs and verifies the sealed hashes.

## Improvement-agent rules (Phase 8 task environment; spec §13.1)

- **Writable:** `codeloop/agent/`, `codeloop/schemas/`, `codeloop/mappers/`, `codeloop/rules/`,
  `codeloop/tools/`, `prompts/`, `tasks/<this task>/`.
- **Writable with human sign-off:** `evals/graders/` — any change sets `grader_changed: true` in
  `RESULTS.md` and fails the automatic gate into human review.
- **Read-only:** `codeloop/scoring/`, `codeloop/compliance/`, `codeloop/scrubber/` rule semantics
  (table parsers may be fixed), `config/`, `data/`, `runs/`, `evals/datasets/`, `evals/suites/`,
  `findings/`.
- **Not mounted:** `data/sealed/`.
- **Network:** egress only to the LLM provider API host(s) through the allowlist proxy in `docker/`.
- **Commands:** `make eval-targeted TASK=…`, `make eval-regression`, `make gate TASK=…`.
- **Definition of done:** `RESULTS.md` complete (targeted before/after, regression before/after,
  scrubber delta, escalations, diff summary), gate PASS or an explicit ambiguity note, branch
  `codeloop/<finding-id>` pushed.
- **Prohibited:** changing scope, touching scoring, adding CPT descriptors, reading holdout
  material, weakening the compliance policy, editing `config/`, editing findings or datasets.

## Build conventions

- Python 3.12, `uv`. `uv run pytest` and `uv run ruff check codeloop tests` must pass before a
  commit. `make install` creates the environment.
- Pydantic v2 models in `codeloop/schemas/` are the contract between components; field references
  use the strings defined in spec §4 (`dx:<code>`, `line:<code>[:<idx>]:units`, …).
- Codes are normalized on entry: ICD-10-CM uppercase without the dot; CPT/HCPCS uppercase, five
  characters; modifiers stored sorted.
- Every LLM call goes through `codeloop/llm/client.py`; prompts are plain-text files under
  `prompts/`, one per call site, hashed into traces. No agent frameworks.
- Determinism first: no randomness without a seed recorded in config and in the ledger/trace.
- Encounter text is never re-normalized after ingest; `note_sha256` and `dialogue_sha256` are
  re-verified on every load.
- Commit messages: imperative summary line, body explains why; end with the configured
  `Co-Authored-By` trailer when an agent authored the change.

## Phase status

See `ledger.md` for what has happened and `README.md` for the phase table. Do not start a phase
whose preceding HUMAN GATE has not cleared.
