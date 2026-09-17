# CodeLoop — Implementation Spec (from product spec v1.2)

**Audience:** Claude Code, building this repository from scratch.
**How to use:** Read the whole document once. Then execute the phases in §18 in order. Every phase ends with an acceptance check; some end with a **HUMAN GATE** where you stop and wait for the project owner. Do not start a later phase before the gate clears. Sections 0, 2.3, 5, 13 and 15 contain hard constraints.

Where this document sets a default the product spec left open, it is marked **DECISION Dn** and is registered in §19 and stored in `config/project.yaml`. The owner confirms or changes those during Phases 0–3. After the freeze (Phase 3) they are locked.

---

## 0. What we are building, and what must not break

CodeLoop is an outpatient professional-coding agent wrapped in a self-improvement harness. The agent reads a doctor–patient dialogue plus the resulting clinical note and emits a **coding package**: ICD-10-CM diagnoses (with specificity, laterality, historical-vs-active), in-scope CPT/HCPCS lines with modifiers, units and diagnosis pointers, and an evidence span for every predicted field. A certified professional coder (CPC) corrects drafts in a review UI, giving a reason per edit. Recurring corrections become **findings**, findings become **targeted evals**, and an improvement agent (Codex or Claude Code) modifies the pipeline inside a bounded task environment; changes merge only through a **gate**. Four frozen versions (v0–v3) are finally compared on 40 sealed, blind-coded holdout encounters.

The project's evidentiary value depends on process integrity more than on the agent. These invariants are enforced in code and tests wherever possible:

| # | Invariant | Enforcement |
|---|---|---|
| I1 | The 40 holdout encounters are drawn by seeded random selection before any content is read, and are never inspected, passed through the audit, or used in any scope or improvement decision until v3 is frozen. | `codeloop seal` is Phase 0. Holdout content is stored only. `test_no_holdout_leakage`. |
| I2 | Both public ICD label sets cover all 207 ACI-Bench encounters. Holdout rows are removed before those files enter the repo. Raw downloads are deleted after filtering. | `codeloop seal` does the filtering; leakage test compares content hashes. |
| I3 | The canonical representation and scorer (`codeloop/scoring/`) are committed at the freeze and never change afterward. | Directory is read-only in task environments; its tree hash is recorded in `ledger.md`; CI fails if the hash changes after the `freeze` tag. |
| I4 | The holdout is scored exactly once. | `codeloop holdout score` writes a lock file and refuses to run again. |
| I5 | The improvement agent's environment has egress only to the LLM provider API and cannot read `data/sealed/`. | Container with an allowlist proxy; sealed directory not mounted. |
| I6 | No CPT descriptors (AMA-licensed text) are stored in the repo or loaded into prompts. Code numbers only. | Rule in `CLAUDE.md`; reviewed at PR time. |
| I7 | Every frozen version records exact model IDs, sampling settings, prompt hashes, scope hash and pinned table versions. | `codeloop version freeze`. |

**Stack:** Python 3.12, Pydantic v2, Typer CLI, FastAPI + vanilla HTML/JS review UI (no build step), SQLite for the review event store and the LLM cache, pytest, `cryptography` for the sealed store. Prompts are plain text files under `prompts/`. No agent frameworks; every LLM call is explicit and traced.

---

## 1. Repository layout

```
codeloop/
├── CLAUDE.md                 # rules for any agent working in this repo (build-time and improvement-time); AGENTS.md is a symlink to it
├── CODELOOP_SPEC.md          # this file
├── DECISIONS.md              # rendered from config/project.yaml decisions + rationale
├── ledger.md                 # append-only chronology: UTC timestamp, event, hashes, actor
├── Makefile
├── pyproject.toml
├── config/
│   ├── project.yaml          # decisions (D1–D10), seeds, run parameters
│   ├── models.yaml           # provider, exact model ID, temperature, seeds, max_tokens — pinned per version
│   ├── scope.yaml            # modules on/off, code allowlists per module, exclusions (E/M, modifier 25)
│   └── tables.yaml           # pinned versions/filenames of every external table
├── data/
│   ├── raw/                  # gitignored downloads; deleted by `seal` after filtering
│   ├── dev/                  # 167 normalized encounters (gitignored by default, rebuilt by `make data`)
│   ├── labels_public/        # Amazon + MedCodER labels, holdout rows removed (committed)
│   ├── labels/               # CPC-approved labels per batch (committed)
│   ├── splits/               # holdout_ids.txt, holdout_ids.sha256, dev_split.json (committed)
│   ├── sealed/               # encrypted holdout content, predictions, labels; content hashes (committed, encrypted)
│   └── tables/               # parsed CMS/CDC tables (committed if license permits; CMS data is public domain)
├── codeloop/                 # Python package
│   ├── ingest/               # download, normalize, crosswalk to public labels
│   ├── seal/                 # holdout draw, encryption, filtering, leakage checks
│   ├── schemas/              # Pydantic models: Encounter, Span, CodingPackage, Trace, Event, Finding …
│   ├── llm/                  # provider-agnostic client, cache, structured-output validation
│   ├── agent/                # pipeline stages: extract → map → assemble → validate → emit
│   ├── mappers/              # deterministic mapping rules per module (code numbers only)
│   ├── tools/                # ICD-10-CM retrieval, product-data tool, code-set validators
│   ├── rules/                # coding-guideline rules the agent applies (history vs active, laterality, etc.)
│   ├── scrubber/             # NCCI PTP, MUE, modifier rules
│   ├── compliance/           # static evidence checks + diff-based escalation gate
│   ├── scoring/              # canonicalizer + scorer + bootstrap — FROZEN at Phase 3
│   ├── evals/                # eval runner, suites, targeted-metric computation
│   ├── findings/             # grouping, packaging into evals and tasks
│   ├── review_ui/            # FastAPI app + static assets; event store
│   ├── audit/                # Week-1 prevalence audit
│   ├── holdout/              # sealed prediction, blind labeling session, single-shot scoring
│   ├── versioning/           # freeze, VERSION.md, tag checks
│   └── reporting/            # tables, curve chart, anchoring, holdout report
├── prompts/                  # one file per LLM call site; hashed into traces
├── evals/
│   ├── datasets/             # FIND-*.yaml targeted datasets
│   ├── suites/               # targeted-*.yaml, regression-*.yaml
│   └── graders/              # grader configs (editable by the improvement agent only with human sign-off)
├── findings/                 # FIND-*.yaml (status, occurrences, hypothesis, resolution)
├── tasks/                    # one folder per finding handed to the improvement agent
├── runs/                     # predictions + traces per version × batch (predictions committed, traces gitignored)
├── versions/                 # v0/VERSION.md … v3/VERSION.md
├── reports/
├── docker/                   # task-env.Dockerfile, allowlist proxy config
└── tests/
```

---

## 2. Data

### 2.1 Sources

| Source | Content | Use | Notes |
|---|---|---|---|
| ACI-Bench (figshare release; code at github.com/wyim/aci-bench) | 207 encounters: full dialogue + clinical note; subsets `aci`, `virtassist`, `virtscribe`; original splits 67/20/40/40/40 | All encounters | Cite the Nature Scientific Data paper. Keep ASR-swapped speaker tags as they are. Check the dataset license before committing normalized text; default is gitignored and rebuilt by `make data`. |
| Amazon `toward-clinical-coding-verification-adaptation` (GitHub) | Double-annotated, adjudicated ICD-10-CM gold codes for the 207 ACI-Bench notes | Calibration only, on the 167 | Holdout rows removed at seal. |
| MedCodER dataset (Zenodo DOI 10.5281/zenodo.13308316) | ICD-10 codes, diagnoses and supporting-evidence text for ACI-Bench notes | Calibration only, on the 167 | Verify record count on download. Holdout rows removed at seal. |
| ICD-10-CM tabular + index (CMS/CDC) | Diagnosis code set | Retrieval tool; code validation | Pin one annual release in `tables.yaml`; never change it mid-run. |
| HCPCS Level II (CMS) | Code set | Validation | Pin quarter. |
| NCCI PTP practitioner edits (CMS) | Code-pair edits with modifier indicator | Scrubber | Pin quarter. |
| NCCI MUE practitioner table (CMS) | Unit ceilings and adjudication indicator | Scrubber | Pin quarter. |
| MPFS RVU file (CMS) | Bilateral-surgery indicator | Modifier 50/RT/LT rules | Pin release. |
| ASP NDC-HCPCS crosswalk (CMS) | Drug HCPCS ↔ NDC with billing units | Product-data tool | Pin quarter. |
| CDC CVX and NDC↔CVX crosswalk | Vaccine identification | Product-data tool (vaccine module) | Pin download date. |

CPT is not downloaded. Mappers reference code numbers only. If descriptors are ever needed at runtime, that is an AMA-licensing question for the owner, not a default.

Note the ACI-Bench authors' stated intended use (benchmarking dialogue summarization, not training diagnostic models). CodeLoop codes *documented* diagnoses and services; say so in the README.

### 2.2 Ingest and normalization

`codeloop ingest` produces one record per encounter:

```python
class Turn(BaseModel):
    speaker: str            # as given, e.g. "doctor", "patient"; do not correct swapped tags
    text: str

class Encounter(BaseModel):
    id: str                 # ACI-Bench encounter id
    subset: Literal["aci", "virtassist", "virtscribe"]
    split_orig: str         # train/valid/test1/test2/test3 — provenance only
    dialogue: list[Turn]
    dialogue_text: str      # canonical flattening: "\n".join(f"[{speaker}] {text}")
    note_text: str          # exactly as released, normalized to "\n" newlines only
    dialogue_sha256: str
    note_sha256: str
```

Spans (§4) are character offsets into `note_text` or `dialogue_text`. Never re-normalize these strings after ingest; the hashes are the guard.

Public-label crosswalk: join Amazon and MedCodER records to encounter IDs by ID where present, otherwise by exact match on normalized note text. Report unmatched records in `reports/ingest.md`. Adapt the parser to whatever column names the releases actually use; do not assume.

### 2.3 Phase 0: sealing the holdout (`codeloop seal`)

This is the first command ever run, before anyone reads any encounter. It performs, in one process, in a temp directory:

1. Download ACI-Bench, Amazon labels, MedCodER labels into `data/raw/`.
2. Ingest all 207 encounters in memory (no files written yet).
3. Draw the holdout: seed from `config/project.yaml` (`seal_seed`, **DECISION D0 default 20260917**). Stratify on `subset` only: `n_s = round(40 * N_s / 207)`, adjust the largest subset so the total is 40, then `random.Random(seed).sample(sorted_ids_in_subset, n_s)`.
4. Write `data/splits/holdout_ids.txt` (plaintext IDs, committed — IDs reveal no content and the deny-list tooling needs them) and `data/splits/holdout_ids.sha256`.
5. Write `data/sealed/holdout_content_hashes.json`: `{id: {note_sha256, dialogue_sha256}}` (committed; used by the leakage test).
6. Encrypt the 40 `Encounter` records to `data/sealed/holdout_encounters.enc` using AES-256-GCM with a key derived by scrypt from env var `CODELOOP_SEAL_KEY` (salt stored beside the file). The key is never written to disk in the repo.
7. Write `data/dev/encounters.jsonl` with the 167 non-holdout encounters.
8. Write `data/labels_public/amazon.jsonl` and `data/labels_public/medcoder.jsonl` with holdout rows removed.
9. Delete `data/raw/` contents that contain holdout rows (all three downloads). `make data` later re-downloads and re-filters using the committed ID list, never writing holdout content to `data/dev/`.
10. Append a `ledger.md` entry: timestamp, seed, ID-list hash, content-hash file hash, download URLs and file hashes.

`codeloop seal` refuses to run if `data/splits/holdout_ids.txt` exists.

**Leakage test** (`tests/test_no_holdout_leakage.py`, run in CI): walks `data/dev/`, `data/labels_public/`, `data/labels/`, `evals/`, `runs/`, `findings/`, `tasks/`, `reports/`, and asserts (a) no holdout ID string appears in any file and (b) no note or dialogue text hash in any JSONL record matches a holdout content hash.

### 2.4 Splits within the 167 (`codeloop freeze`, Phase 3)

Committed to `data/splits/dev_split.json` at the freeze, drawn with `split_seed`:

| Set | n | Purpose |
|---|---|---|
| `seed` | 20 | v0 development, prompt work, pipeline debugging. Public ICD labels available as reference. |
| `batch1`, `batch2`, `batch3` | 45 each | Production batches, stratified-random on subset and on the difficulty index. |
| `spare` | 12 | UI piloting and ambiguous-case work. |

**Difficulty index** (computed after the audit, before the split): z-scored sum of note length in characters, number of Amazon gold ICD codes, and number of audit-flagged candidate services. Each batch's mean difficulty is recorded and reported beside the curve.

**Blind subset:** 5 encounters per batch (11%), pre-selected at the freeze (**DECISION D8**). The coder codes these blind before the draft is revealed, then reviews as usual. The reviewed label is the official label; the blind label is kept for the anchoring analysis.

---

## 3. Scope and configuration

`config/scope.yaml` is decided by the audit (Phase 2) and frozen in Phase 3. Shape:

```yaml
icd10cm_release: "<pinned annual release>"
modules:
  core_dx:        {on: true}                       # all ICD-10-CM codes are in scope
  core_lines:     {on: true, code_ranges: []}      # filled by the audit: allowlist of CPT/HCPCS ranges for confirmed service categories
  vaccine_admin:  {on: false, threshold: 15, evaluable_n_est: null, code_ranges: ["90460-90461", "90471-90474", "<vaccine product range(s)>"]}
  distinct_59x:   {on: false, threshold: 15, evaluable_n_est: null, modifiers: ["59", "XE", "XS", "XP", "XU"]}
  qw:             {on: false, threshold: 15, evaluable_n_est: null, modifiers: ["QW"]}
  jw_jz:          {on: false, threshold: 15, evaluable_n_est: null, modifiers: ["JW", "JZ"]}
exclusions:
  em_code_ranges: ["99202-99205", "99211-99215", "G2211"]   # Phase 2; stripped from both sides before scoring
  modifiers: ["25"]
holdout_module_min_n: 10                                    # DECISION D6
```

Scoring applies the scope filter symmetrically to gold and predicted packages: keep only lines whose code is in an *on* module's allowlist; strip excluded modifiers and any modifier owned by an *off* module; diagnoses are always kept. The coder may code whatever they would normally code (including E/M); the scorer removes out-of-scope fields.

`config/models.yaml` (pinned per version):

```yaml
default:
  provider: anthropic | openai
  model: "<exact model ID string — verify against provider docs before pinning>"
  temperature: 0
  seeds: [1, 2, 3]          # used when the provider supports seeding; otherwise recorded as null
  max_tokens: 4096
call_sites:                 # optional overrides per prompt file
  extract: {}
  map_dx: {}
```

`config/tables.yaml` records, for every external table, the release name, download date, file sha256 and parser version.

---

## 4. Schemas (the contract between every component)

```python
class Span(BaseModel):
    source: Literal["note", "dialogue"]
    start: int
    end: int
    text: str                  # must equal source_text[start:end]; verified on load
    sha256: str                # of text

class DiagnosisPred(BaseModel):
    code: str                  # ICD-10-CM, normalized: uppercase, dot removed (e.g. "M1711")
    status: Literal["active", "historical"]
    first_listed: bool
    evidence: list[Span]       # at least one; see evidence policy §9
    rationale: str             # one or two sentences, model-generated, never scored

class LinePred(BaseModel):
    code: str                  # CPT/HCPCS, uppercase, 5 chars
    modifiers: list[str]       # stored sorted
    units: int
    pointers: list[str]        # ICD-10-CM codes (resolved, not letters)
    module: str                # scope.yaml module name
    evidence: list[Span]
    rationale: str

class ProviderQuery(BaseModel):
    field_ref: str             # e.g. "dx:M1710:laterality"
    question: str
    evidence: list[Span]       # typically dialogue spans
    suggested_value: str | None

class DataGap(BaseModel):
    field_ref: str
    missing: str               # e.g. "NDC not resolvable from product name"

class CodingPackage(BaseModel):
    encounter_id: str
    version: str               # "v0"… or "dev"
    run_id: str
    diagnoses: list[DiagnosisPred]
    lines: list[LinePred]
    provider_queries: list[ProviderQuery]
    data_gaps: list[DataGap]
    scrubber: list["ScrubFailure"]
    compliance: "ComplianceResult"

class ScrubFailure(BaseModel):
    rule_id: str               # "NCCI_PTP", "MUE", "MOD_LATERALITY", ...
    field_ref: str
    message: str
    severity: Literal["error", "warn"]
    table_version: str

class Trace(BaseModel):
    encounter_id: str; version: str; run_id: str
    models_hash: str; scope_hash: str; prompt_hashes: dict[str, str]; tables_hash: str
    stages: list["StageTrace"]  # name, input hash, structured output, llm_calls: [{prompt_hash, response_hash, tokens_in, tokens_out, latency_ms, seed}]
    package: CodingPackage
    started_at: str; finished_at: str
```

**Field references** are strings used everywhere (scorer, UI events, findings, evals):
`dx:<code>`, `dx:<code>:status`, `first_listed`, `line:<code>[:<idx>]`, `line:<code>[:<idx>]:modifiers`, `line:<code>[:<idx>]:units`, `line:<code>[:<idx>]:pointers`, `query:<n>`.

---

## 5. Canonical representation and scorer — `codeloop/scoring/` (frozen at Phase 3)

### 5.1 Canonicalization

```python
class CanonicalLine(BaseModel):
    code: str; modifiers: tuple[str, ...]; units: int; pointers: frozenset[str]

class Canonical(BaseModel):
    diagnoses: frozenset[str]
    first_listed: str | None
    lines: list[CanonicalLine]
```

Rules: codes uppercased, ICD dots removed; modifiers sorted; pointer letters resolved to codes; lines with identical `(code, modifiers)` merged with units summed; scope filter (§3) applied; ordering discarded. The same function canonicalizes predictions and labels.

### 5.2 Field-level agreement (primary structure of every metric)

Given gold `G` and predicted `P` (both canonical, scope-filtered), enumerate fields:

1. For each code `c` in `G.diagnoses ∪ P.diagnoses`: field `dx:c`, correct iff `c` is in both.
2. Field `first_listed`, present whenever either side has any diagnosis: correct iff equal (both `None` counts as correct).
3. Lines are matched by code. For each code, pair G-lines and P-lines greedily by number of agreeing sub-fields (n is tiny). Each unmatched line (either side) contributes one wrong field `line:c`. Each matched pair contributes `line:c` (correct) plus three fields `:modifiers`, `:units`, `:pointers`, each correct iff equal.

Per-encounter **agreement** = correct fields / total fields. If both sides have zero fields, agreement = 1.0 and the encounter is flagged `no_in_scope_fields`. Tiers: `≥0.75`, `≥0.90`, `==1.0`.

**Secondary (pre-registered) hierarchical metric:** as above, but an unmatched diagnosis earns 0.5 credit if a code on the other side shares its first three characters and is not itself matched (greedy, one-to-one).

**Per-type micro metrics:** precision/recall for `dx` and `line` codes; accuracy for `first_listed`, `modifiers`, `units`, `pointers` over matched lines.

### 5.3 Other metrics

- **Touches per encounter:** count of `edit`, `add`, `remove` events (not `accept`) per encounter in review mode.
- **Review minutes:** sum of gaps between consecutive UI events for the encounter, each gap capped at 120 s (idle cap), from `open` to `approve`.
- **Evidence-support rate:** graded-supported spans / graded spans, per version and per field type. Not part of agreement.
- **Provider-query precision:** queries graded `warranted` / queries graded.
- **Scrubber acceptance:** share of packages with zero `error`-severity scrubber failures. Reported once per version as a gate, not a curve.
- **Anchoring:** on blind-subset encounters, agreement(blind label, reviewed label); agreement(agent, blind); agreement(agent, reviewed).

**DECISION D9 — primary inferential metric:** mean per-encounter agreement (continuous), with paired bootstrap 95% CIs (10,000 resamples over encounters) for each version difference on the holdout. Tier shares are headline descriptives with Wilson intervals. Rationale: with n = 40, a binary 100% tier has ±15 pp intervals and cannot separate versions.

### 5.4 Output

`ScoreResult { encounter_id, fields: [{ref, type, correct, gold, pred}], n_fields, n_correct, agreement, tiers, hier_agreement, per_type }` plus a batch-level aggregator. `codeloop score --gold <path> --pred <path>` is the only entry point and is what the holdout uses.

Unit tests must cover: extras, missings, partial line matches, merged duplicate lines, empty encounters, scope stripping of E/M and off-module modifiers, pointer resolution, hierarchical credit, and idempotence of canonicalization.

---

## 6. Agent pipeline (`codeloop/agent/`)

Stages run in order; each writes a `StageTrace`. Every LLM call goes through `codeloop/llm/client.py` (`complete(prompt_name, variables, schema, seed) -> Parsed`), which hashes the rendered prompt, validates the response against the Pydantic schema (one retry on validation failure), records tokens/latency, and uses the SQLite cache keyed on `(model, params, rendered_prompt_sha256, seed)`.

1. **ingest** — load `Encounter`, verify hashes.
2. **extract** — one structured LLM call (`prompts/extract.txt`) over note and dialogue producing:
   - problems: `{description, status: active|historical|ruled_out, laterality, qualifiers, note_spans, dialogue_spans}`
   - services performed in-visit: `{category, description, note_spans, dialogue_spans}`
   - administrations: medications/vaccines given: `{product_name, dose, route, wastage_documented, counseling: {occurred, by_whom}, note_spans, dialogue_spans}`
   - patient facts needed by modules: age, sex (with spans)
   - in-office tests: `{description, spans}`
   The extractor records note and dialogue spans separately; the evidence policy (§9) decides which may support billable fields.
3. **map_dx** — for each active problem: retrieve top-k ICD-10-CM candidates with the retrieval tool (§7.1); LLM (`prompts/map_dx.txt`) selects one code or `none`, sets specificity/laterality from *allowed* evidence, and marks `first_listed`. Rules in `codeloop/rules/` are applied deterministically after selection: history-of Z-code handling for `historical` problems, laterality suffix validation against the code set, code-set existence check.
4. **map_lines** — module mappers (`codeloop/mappers/<module>.py`) turn services and administrations into lines. Deterministic where the tool can resolve it (drug HCPCS, units, NDC via §7.2; vaccine product via CVX); LLM-assisted selection (`prompts/map_lines.txt`) only within the module's allowlisted code ranges. Vaccine-admin logic (if the module is on): age, whether qualifying counseling occurred and who provided it, route, component count → 90460/90461 vs the 90471–90474 lines. Unresolvable structured facts become `DataGap`s, never guesses.
5. **assemble** — set pointers (each line points to the diagnoses that justify it), sort modifiers, merge duplicate lines, choose `first_listed` if not set.
6. **validate** — run the scrubber (§8) and the compliance static check (§9); attach results; under `note_only` policy, any field whose only evidence is dialogue is downgraded and a `ProviderQuery` emitted.
7. **emit** — write `CodingPackage` and `Trace` to `runs/<version>/<batch>/`.

`codeloop run --version vK --batch B [--limit N] [--seeds 1,2,3]` refuses to run unless the working tree is at the tag `vK` (or `--version dev` is used on `seed`/`spare` only).

---

## 7. Tools (`codeloop/tools/`)

### 7.1 ICD-10-CM retrieval
Build a local index over the pinned ICD-10-CM tabular descriptions and index terms (public domain): SQLite FTS5 (BM25) by default; optional local embedding index behind the same interface. `search(query: str, k: int) -> list[{code, description, chapter}]`. Also `exists(code)`, `laterality_variants(code)`, `is_billable(code)` (leaf check).

### 7.2 Product-data tool
`resolve_product(name, dose, route, kind: drug|vaccine) -> ProductResolution | DataGap`. Drugs: ASP NDC-HCPCS crosswalk → HCPCS code, billing units per dose (unit conversion is deterministic arithmetic, recorded in the trace). Vaccines: CVX/NDC crosswalk → product identity; product CPT code range from `scope.yaml` allowlist. Returns `DataGap` when the evidence does not identify the product or dose unambiguously.

### 7.3 Code-set validators
HCPCS Level II existence; modifier validity list (RT, LT, 50, 59, XE, XS, XP, XU, QW, JW, JZ, 25); bilateral indicator lookup from the MPFS RVU file.

---

## 8. Scrubber (`codeloop/scrubber/`) — one capped week

Deterministic, table-driven, no LLM. Interface: `scrub(package: CodingPackage, tables: Tables) -> list[ScrubFailure]`.

Rules for v1:
- **NCCI PTP (practitioner):** for every pair of line codes, look up column-1/column-2 edits; if an edit exists and modifier indicator is 0 → `error`; if indicator is 1 and no bypass modifier (59/X{E,S,P,U}) is present on the column-2 line → `error`; indicator 9 → ignore. Respect effective/deletion dates against the pinned quarter.
- **MUE (practitioner):** units > MUE value → `error` (report MAI).
- **Modifier rules:** 50 only where the bilateral indicator permits; RT/LT never together with 50 on the same line; 59 and X-modifiers never on the same line; QW only on codes flagged as waived (if the QW module is on); JW/JZ only on drug lines (if that module is on); modifier 25 never asserted by the agent (out of scope).
- **Structural:** every line has ≥1 pointer; every pointer resolves to a diagnosis in the package; units ≥ 1.

Each failure joins back to a `field_ref`. Report how often each rule fired per batch; with few procedure lines the scrubber may fire rarely, and that number should be visible.

Design note for the write-up: define a `ScrubSignal` adapter interface so that in production, clearinghouse and payer responses (277CA, 835) could feed the same `ScrubFailure` type. Do not implement parsers for those transactions.

---

## 9. Compliance (`codeloop/compliance/`)

**DECISION D1 — evidence policy, default `note_only`.** Billable fields (any diagnosis, any line, any modifier, units, specificity/laterality) must carry at least one span whose `source == "note"`. Dialogue spans may be attached as supplementary context but cannot be the sole support. A clinically relevant fact found only in dialogue produces a `ProviderQuery` with the dialogue span, and the agent codes the note-supported version (e.g., unspecified laterality). Rationale: the signed note is the medical record; a compliant coder does not code from the transcript. Alternative value `note_or_dialogue` allows dialogue as sole support; the coder guidelines must then say the same, or every dialogue-supported field will be marked unsupported.

**Static check** (`check_package`): every billable field has ≥1 allowed-source span; each span's `text` equals the source substring at its offsets; codes exist in the pinned code sets; no out-of-scope modifiers asserted.

**Escalation gate** (`check_escalation(base: CodingPackage, cand: CodingPackage)`): for each encounter in the regression suite, compare the candidate version's output to the base version's. Any *addition or escalation of a billable element* — a new line, higher units, a 59/X modifier added, a diagnosis replaced by a more specific code (same first three characters, longer or different suffix) — must (a) have allowed-source evidence and (b) pass the scrubber with zero `error` failures. Otherwise the gate fails and lists the escalations.

---

## 10. Review UI and event store (`codeloop/review_ui/`)

Local FastAPI app, single coder at a time, no auth beyond a `coder_id` chosen at start. Screens:

- **Queue:** encounters in the batch, with status (`unopened`, `in_progress`, `approved`) and mode (`review` or `blind`).
- **Encounter (review mode):** note on the left (dialogue collapsible below it), draft package on the right. Clicking a field highlights its spans. Per field: **Accept**, **Edit** (value change), **Remove**; per section: **Add**. Every edit/add/remove requires exactly one reason (§10.1). Per cited span: **Supported / Unsupported**. Per provider query: **Warranted / Unwarranted**. **Approve** finishes the encounter.
- **Encounter (blind mode):** note and dialogue only; the server does not load or transmit any prediction. The coder builds the package from scratch and submits. Then the server switches the encounter to review mode and shows the draft; the coder reviews as usual. Blind labels and reviewed labels are stored separately.
- **Holdout-labeling mode** (`--holdout-labeling`): loads decrypted holdout encounters using `CODELOOP_SEAL_KEY`, blind mode only, no predictions exist on the server at all, labels written encrypted to `data/sealed/holdout_labels.enc`. Used in Phase 9 and by the optional second CPC.

### 10.1 Coder-facing reason taxonomy (**DECISION D2**)

One click per edit. Reasons describe the coding error, not the software:

| Reason | Meaning |
|---|---|
| `missed` | Documentation supports a code/field that was not predicted |
| `unsupported` | Predicted code/field is not supported by the documentation (over-coded) |
| `specificity` | Right concept, wrong specificity, laterality, or active/historical status |
| `wrong_value` | Wrong code, units, modifier, or pointer (field type comes from the edit itself) |
| `guideline` | Coding-guideline or convention violation (code-first, excludes notes, sequencing) |
| `query_needed` | Documentation insufficient; a provider query is the right action |
| `judgment` | Coder judgment or preference; not a clear error |

Pipeline causes (`extraction_miss`, `mapper_gap`, `tool_data_gap`, `rule_bug`, `grader_bug`, `model_reasoning`) are assigned at triage (§11), never by the coder.

### 10.2 Event store

SQLite, append-only table of events:

```python
class Event(BaseModel):
    ts: str; coder_id: str; encounter_id: str; batch: str; version: str
    mode: Literal["review", "blind", "holdout"]
    type: Literal["open", "accept", "edit", "add", "remove", "grade_evidence", "grade_query", "approve", "blind_submit"]
    field_ref: str | None
    before: dict | None; after: dict | None
    reason: str | None         # required for edit/add/remove in review mode
    span_id: str | None; grade: str | None
```

`codeloop labels build --batch B` replays events into `data/labels/batchB.jsonl` (`{encounter_id, coder_id, label: CodingPackage-shaped without rationale/evidence requirements, blind_label?, touches, review_minutes, evidence_grades, query_grades}`). Labels keep out-of-scope codes; the scorer strips them.

---

## 11. Findings (`codeloop/findings/`)

`codeloop findings extract --batch B`:

1. Collect all `edit/add/remove` events with reason ≠ `judgment` from batch B.
2. Deterministic grouping key: `(reason, field_type, module, code_category)` where `code_category` is the ICD first-three characters or the CPT/HCPCS range name.
3. Optional LLM pass (`prompts/cluster_findings.txt`) proposes merges/splits of groups with a one-line pattern description; output is a *proposal*.
4. Write candidate `findings/FIND-<MODULE>-<NNNN>.yaml` with `status: candidate`.

**DECISION D3 — minimum occurrences:** a candidate becomes eligible when it appears in ≥3 encounters of the batch, or ≥2 if the same key appeared in a prior batch. Below that it stays `candidate` and is re-checked next batch.

Human triage (the owner, assisted by an LLM if they choose — record which): set `status` to `accepted`, `ambiguous` (routed back to the owner; not automated), or `rejected`; write `hypothesis`. The improvement agent fills `pipeline_cause` during the task.

```yaml
id: FIND-DX-0003
title: Laterality missing when note states side in exam section only
batch_discovered: batch1
status: accepted
pattern: ...
reasons: [specificity]
field_types: [dx]
occurrences:
  - {encounter_id: D2N0xx, event_ids: [..]}
count: 4
hypothesis: extractor only reads the assessment/plan section for laterality
pipeline_cause: null            # filled by the improvement agent
targeted_eval: evals/datasets/FIND-DX-0003.yaml
task: tasks/FIND-DX-0003/
resolution: {version: null, pr: null, before_error_rate: null, after_error_rate: null, batch_next_error_rate: null}
```

`codeloop findings package FIND-…` creates the targeted dataset, the targeted suite, the regression suite (all CPC-labeled batches so far), and the task folder (§13).

---

## 12. Eval harness (`codeloop/evals/`)

Dataset format:

```yaml
# evals/datasets/FIND-DX-0003.yaml
finding: FIND-DX-0003
cases:
  - encounter_id: D2N0xx
    gold: data/labels/batch1.jsonl#D2N0xx
    field_refs: ["dx:M1711", "dx:M1710"]     # fields whose correctness defines the finding's error rate
```

Suites: `evals/suites/targeted-FIND-DX-0003.yaml` and `evals/suites/regression-through-batch1.yaml` (every in-scope field of every labeled encounter so far).

`codeloop eval run --suite <path> --runs N --seeds 1,2,3 [--limit]`:
- **DECISION D4 — runs per eval: 3**, temperature 0, seeds `[1,2,3]` where supported. Reports mean and per-run values plus run-to-run variance.
- Targeted metric: error rate over `field_refs` across cases (mean over runs).
- Regression metrics: mean encounter agreement, per-type recall, scrubber `error` count, compliance escalation check against the base version's stored outputs.
- Output: `evals/results/<suite>/<commit>.json` and a Markdown summary.

The LLM cache makes re-running unchanged prompts free and deterministic; a changed prompt or model config changes the key automatically.

---

## 13. Improvement-agent task environment and merge gate

### 13.1 Task folder

```
tasks/FIND-DX-0003/
├── task.yaml          # finding id, writable paths, read-only paths, commands, success criteria, base commit
├── EXEC_PLAN.md       # written by the agent: root cause found, pipeline_cause, plan
└── RESULTS.md         # written by the agent: targeted before/after, regression before/after, scrubber delta, escalations, diff summary
```

`CLAUDE.md` (with `AGENTS.md` → symlink) states the rules for the improvement agent:

- **Writable:** `codeloop/agent/`, `codeloop/schemas/`, `codeloop/mappers/`, `codeloop/rules/`, `codeloop/tools/`, `prompts/`, `tasks/<this task>/`.
- **Writable with human sign-off flag:** `evals/graders/` (any change sets `grader_changed: true` in RESULTS.md and fails the automatic gate into human review).
- **Read-only:** `codeloop/scoring/`, `codeloop/compliance/`, `codeloop/scrubber/` rule semantics (table parsers may be fixed), `config/`, `data/`, `runs/`, `evals/datasets/`, `evals/suites/`, `findings/`.
- **Not mounted:** `data/sealed/`.
- **Network:** egress allowed only to the LLM provider API host(s) via the allowlist proxy in `docker/`.
- Commands: `make eval-targeted TASK=…`, `make eval-regression`, `make gate TASK=…`.
- Definition of done: RESULTS.md complete, gate PASS or an explicit ambiguity note, branch `codeloop/<finding-id>` pushed.
- Prohibited: changing scope, touching scoring, adding CPT descriptors, reading holdout material, weakening the compliance policy.

### 13.2 Merge gate (`codeloop gate check --task … --base <commit> --head <commit>`)

Runs on the head commit inside the task environment, writes `tasks/<id>/GATE.md` with PASS/FAIL and numbers:

| Check | Pass condition (defaults, **DECISION D5**) |
|---|---|
| Targeted eval | error rate falls by ≥25% relative to base (mean over runs) and does not rise on any run |
| Regression | mean encounter agreement on the regression suite drops by no more than 1.0 pp; no per-type recall drops more than 2.0 pp |
| Scrubber | total `error`-severity failures on regression outputs do not increase |
| Compliance | `check_escalation(base, head)` passes for every regression encounter |
| Paths | only permitted paths changed; `grader_changed` false (else route to human) |

A human reviews the PR and merges. Ambiguous findings never enter the gate; they are recorded as `ambiguous` with a note.

---

## 14. Versioning and freezing (`codeloop/versioning/`)

`codeloop version freeze vK`:
1. Requires a clean tree on `main` after the merges for cycle K.
2. Writes `versions/vK/VERSION.md`: commit, `models.yaml` contents and hash, every prompt file hash, `scope.yaml` hash, `tables.yaml` hash, `project.yaml` decisions hash, `codeloop/scoring/` tree hash (must equal the freeze hash).
3. Tags `vK`.
4. **DECISION D7 — sealed predictions at freeze time:** runs `codeloop holdout predict --version vK --sealed` (§15) immediately, so a model retirement between versions cannot break the final comparison.
5. Appends a ledger entry.

Batch runs and eval runs verify `git describe --tags --exact-match` equals the version they claim.

---

## 15. Holdout protocol (`codeloop/holdout/`)

Fixed chronology; every step appends to `ledger.md` with hashes.

1. **Sealed predictions** (at each freeze, per D7): `codeloop holdout predict --version vK --sealed` decrypts the 40 encounters in memory, runs the pipeline with tracing routed to an encrypted trace store, with the LLM cache disabled (or a separate encrypted cache), with content-free logging, and writes `data/sealed/predictions_vK.enc` plus a committed sha256. Nothing about the outputs is displayed. After v3 is frozen, optionally re-run all four versions if every pinned model is still available and record whether outputs match.
2. **Scorer commit check:** `codeloop holdout verify-scorer` confirms the `codeloop/scoring/` tree hash equals the freeze hash and records it again.
3. **Blind labeling:** `codeloop review serve --holdout-labeling` (§10). The CPC codes all 40 with no agent output in existence on the server. Optional second CPC codes ~15 (**seeded selection, recorded**) under a different `coder_id`.
4. **Reveal and score:** `codeloop holdout score` decrypts predictions and labels, applies the frozen scorer, computes the pre-registered metrics (D9), paired bootstrap CIs for every pairwise version difference, module-level results only where evaluable n ≥ `holdout_module_min_n` (else the literal string `insufficient (n=…)`), human–human agreement on the second-CPC subset if present, and writes `reports/holdout.md` and `reports/holdout.json`. It then writes `data/sealed/SCORED.lock` and commits. A second invocation exits with an error. Labels and predictions are exported in plaintext alongside the results at this point and not before.

---

## 16. Reporting (`codeloop/reporting/`)

`codeloop report` regenerates everything under `reports/`:

- **Curve chart:** x = cycle (v0 on batch 1, v1 on batch 2, v2 on batch 3 — the live diagonal — plus the holdout column for all four); series = share of encounters at ≥75%, ≥90%, 100% agreement; panels for touches per encounter and review minutes; batch difficulty printed under each x tick. Caption states the in-scope field set and that E/M is excluded.
- **Version × batch table:** rows v0–v3, columns Batch 1–3 and Holdout. Each cell is tagged `live`, `in-sample`, `unseen (labels anchored to vK)`, or `holdout`. The headline table shows `live` and `holdout` cells only; the full table with tags is an appendix.
- **Anchoring report:** blind vs reviewed label agreement; agent vs each; per batch.
- **Evidence-support rate, provider-query precision, scrubber acceptance and rule-fire counts, per version.**
- **Audit report:** prevalence per category, spot-check precision, module decisions with the arithmetic.
- **Findings log:** every finding with status, before/after targeted error rate, and the error rate of that pattern on the next unseen batch.
- **Holdout report:** from §15.

Optional: `codeloop export labels --release` produces the "ACI-Bench-Claims" file: encounter id, canonical codes only (no descriptors), evidence spans as offsets, single-coder v0 disclosure, license check against ACI-Bench terms before writing.

---

## 17. Tests (`tests/`)

Required, run in CI on every PR:

- `test_no_holdout_leakage` (§2.3).
- `test_scoring_frozen`: after the `freeze` tag exists, `codeloop/scoring/` tree hash equals the ledger hash.
- Canonicalizer and scorer cases listed in §5.4.
- Span integrity: every span in every committed prediction/label equals its source substring.
- Scrubber: PTP indicator 0/1/9 cases, MUE ceiling, modifier conflicts, pointer resolution, table-version presence.
- Compliance: `note_only` policy rejects dialogue-only support; escalation gate catches new line / higher units / 59 added / specificity increase; passes when evidence and scrubber are clean.
- Review UI: blind mode never serves predictions (assert on the API response); reasons required; event replay is deterministic.
- Findings: grouping key stability; occurrence thresholds.
- Eval runner: cache hit/miss behavior; mean/variance across runs.
- Versioning: `run` refuses when not at the claimed tag.
- Holdout: `score` refuses a second run; `predict --sealed` writes no plaintext under `runs/` or `traces/`.

---

## 18. Build order and human gates

Each phase lists acceptance criteria. **HUMAN GATE** means stop and wait.

**Phase 0 — Seal.** Implement `codeloop/seal/`, `codeloop/ingest/`, `Encounter`, the leakage test, `ledger.md`. Owner sets `CODELOOP_SEAL_KEY`. Run `codeloop seal`. *Accept:* 40 IDs committed with hash; encrypted content present; 167 dev encounters; both label files filtered; raw deleted; leakage test green; ledger entry. **HUMAN GATE:** owner confirms D0 seed and stores the key outside the repo.

**Phase 1 — Contract and scorer.** Schemas (§4), canonicalizer, scorer, bootstrap, `codeloop score`, tests (§5.4). Scope filter reads `scope.yaml` even before the audit fills it. *Accept:* all scorer tests green; `codeloop score` runs on synthetic fixtures.

**Phase 2 — Audit.** `codeloop audit run` over the 167: one structured LLM call per encounter flagging candidate services by category (in-office injections, joint aspiration/injection, laceration repair, lesion destruction, ECG, spirometry, nebulizer treatment, cerumen removal, waived in-office tests, immunizations with counseling/route/product facts, drug administrations with wastage), plus patient age/sex. `codeloop audit sample --n 30` draws 15 flagged + 15 random (seeded) for the CPC's two-hour spot-check; a minimal UI page collects confirm/deny per flag. `reports/audit.md` computes per-category precision and `evaluable_n_est = flagged × precision`. Module rule (**DECISION D10**): on iff `evaluable_n_est ≥ 15` and ≥5 confirmed in the spot-check. *Accept:* report written; owner fills `scope.yaml` code allowlists. **HUMAN GATE:** CPC spot-check done; owner commits `scope.yaml`.

**Phase 3 — Freeze.** `codeloop freeze`: validates `scope.yaml` and `project.yaml`, computes the difficulty index, writes `dev_split.json` including blind subsets, records hashes of `config/`, `data/splits/`, `codeloop/scoring/`, tags `freeze`. Renders `DECISIONS.md`. *Accept:* tag exists; `test_scoring_frozen` active. **HUMAN GATE:** owner signs off on decisions D0–D10.

**Phase 4 — v0 agent.** LLM client + cache, prompts, extract/map/assemble/emit, ICD retrieval tool, product-data tool, rules, mappers for on-modules. Develop only on `seed` (and `spare` for UI). *Accept:* runs end-to-end on all 20 seed encounters with valid packages, every span verifies, no crashes; calibration report of dx agreement against the two public label sets (reference only); `codeloop run --version dev --batch seed` works.

**Phase 5 — Scrubber and compliance.** §8 and §9 with tests. Tables parsed and pinned in `tables.yaml`. *Accept:* scrubber and compliance tests green; v0 packages carry results.

**Phase 6 — Review UI.** §10 including blind and holdout-labeling modes, event store, `labels build`. Pilot on `spare` with the owner acting as coder. *Accept:* UI tests green; a full pilot pass produces a valid label file with touches and minutes.

**Phase 7 — Harness.** Eval runner (§12), findings extract/package (§11), task environment and container (§13), gate (§13.2), versioning (§14), sealed holdout predict (§15.1). *Accept:* a synthetic finding flows from `findings package` → task folder → `gate check` end-to-end on `seed` labels. Then `codeloop version freeze v0` (which seals v0 holdout predictions). **HUMAN GATE:** v0 frozen; CPC hired and onboarded on the pilot UI.

**Phase 8 — Three cycles.** For K in 0,1,2: `run vK batchK+1` → CPC review (blind subset first) → `labels build` → `findings extract` → owner triage → `findings package` per accepted finding → improvement agent tasks → `gate check` → owner merges → `version freeze v(K+1)`. *Accept per cycle:* labels committed; findings log updated with next-batch error rates for prior findings; VERSION.md written; sealed predictions hash committed. **HUMAN GATE** at each triage and each merge.

**Phase 9 — Holdout.** §15 steps 2–4. **HUMAN GATE** before step 4: owner confirms predictions for v0–v3 are all sealed and the scorer hash matches.

**Phase 10 — Reports.** `codeloop report`; optional label export. *Accept:* all artifacts in §16 regenerate from committed data with one command.

---

## 19. Decisions register (`config/project.yaml`)

| ID | Decision | Default | Change before |
|---|---|---|---|
| D0 | Seal seed | 20260917 | Phase 0 |
| D1 | Evidence policy for billable fields | `note_only` (dialogue-only facts → provider query) | Phase 3 |
| D2 | Coder-facing reason taxonomy | 7 coding-level reasons (§10.1); pipeline causes assigned at triage | Phase 3 |
| D3 | Minimum occurrences for a finding | 3 in-batch, or 2 if seen in a prior batch | Phase 3 |
| D4 | Eval runs per candidate | 3 runs, temperature 0, seeds 1–3 | Phase 3 |
| D5 | Gate thresholds | targeted −25% relative; regression −1.0 pp agreement max, −2.0 pp per-type recall max; scrubber non-increasing; escalation check | Phase 3 |
| D6 | Minimum evaluable n for module-level holdout reporting | 10 | Phase 3 |
| D7 | When holdout predictions are generated | at each version freeze, sealed; optional re-run at the end | Phase 3 |
| D8 | Blind subset size and official label | 5 per batch; reviewed label is official | Phase 3 |
| D9 | Primary inferential metric | mean per-encounter field agreement with paired bootstrap CIs; tiers as descriptives | Phase 3 |
| D10 | Module activation rule | `evaluable_n_est ≥ 15` and ≥5 spot-check confirmations | Phase 2 |

---

## Appendix A — CLI summary

```
codeloop seal                                  # Phase 0, once
codeloop ingest                                # rebuild data/dev from raw using committed holdout IDs
codeloop audit run | sample --n 30 | report
codeloop freeze
codeloop run --version vK|dev --batch <name> [--limit N] [--seeds 1,2,3]
codeloop review serve --batch <name> --version vK | --holdout-labeling
codeloop labels build --batch <name>
codeloop findings extract --batch <name> | package FIND-…
codeloop eval run --suite <path> [--runs N] [--limit N]
codeloop gate check --task tasks/FIND-… --base <commit> --head <commit>
codeloop version freeze vK
codeloop holdout predict --version vK --sealed | verify-scorer | score
codeloop score --gold <path> --pred <path>
codeloop report
codeloop export labels --release
```

## Appendix B — Things to state plainly in the README

- Encounters are scripted or role-played (ACI-Bench), not real patients; zero PHI.
- Public ICD label sets exist for the holdout encounters; they were filtered out at seal time, and the improvement agent has no route to them, but underlying models may have seen them in pretraining. Holdout labels are produced fresh by the project's CPC under the project's scope.
- Under `note_only`, dialogue drives provider queries, not billable fields; that is the compliant reading and is what the showcase demonstrates.
- Speaker tags in some ACI-Bench subsets are swapped by ASR; "who provided counseling" is therefore unreliable evidence, and the vaccine module treats it as such.
- The 75/90/100 tiers are descriptive; the inferential claim rests on D9 with n = 40 and paired CIs.
