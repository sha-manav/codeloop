# Decisions register

Rendered from `config/project.yaml` by `codeloop render-decisions` (`make decisions`).
Edit the YAML, not this file. Status: `default` = builder default awaiting the owner;
`confirmed` / `changed` = owner action; `locked` = frozen at Phase 3.

| ID | Decision | Value | Status | Change before |
|---|---|---|---|---|
| D0 | Seal seed | `20260917` | locked | Phase 0 |
| D1 | Evidence policy for billable fields | `note_only` | locked | Phase 3 |
| D2 | Coder-facing reason taxonomy | `["missed", "unsupported", "specificity", "wrong_value", "guideline", "query_needed", "judgment"]` | locked | Phase 3 |
| D3 | Minimum occurrences for a finding | `{"if_seen_in_prior_batch": 2, "in_batch": 3}` | locked | Phase 3 |
| D4 | Eval runs per candidate | `{"provider_seed": null, "runs": 3, "seeds": [1, 2, 3], "temperature": null}` | locked | Phase 3 |
| D5 | Gate thresholds | `{"compliance_escalation_check": "required", "regression_mean_agreement_drop_max_pp": 1.0, "regression_per_type_recall_drop_max_pp": 2.0, "scrubber_errors": "non_increasing", "targeted_no_run_may_rise": true, "targeted_relative_error_reduction_min": 0.25}` | locked | Phase 3 |
| D6 | Minimum evaluable n for module-level holdout reporting | `10` | locked | Phase 3 |
| D7 | When holdout predictions are generated | `at_each_version_freeze_sealed` | locked | Phase 3 |
| D8 | Blind subset size and official label | `{"blind_per_batch": 5, "official_label": "reviewed"}` | locked | Phase 3 |
| D9 | Primary inferential metric | `{"interval": "paired_bootstrap_95", "primary": "mean_per_encounter_field_agreement", "resamples": 10000, "tier_intervals": "wilson", "tiers": [0.75, 0.9, 1.0]}` | locked | Phase 3 |
| D10 | Module activation rule | `{"evaluable_n_est_min": 15, "spot_check_confirmed_min": 5}` | locked | Phase 2 |

## Rationale

### D0 — Seal seed

Any fixed integer works; the value is recorded in the ledger together with the ID-list hash so the draw can be reproduced. Chosen as the project start date.

### D1 — Evidence policy for billable fields

The signed note is the medical record; a compliant coder does not code from the transcript. Dialogue-only facts become provider queries. Alternative: note_or_dialogue (coder guidelines must then say the same, or every dialogue-supported field will be graded unsupported).

### D2 — Coder-facing reason taxonomy

One click per edit, describing the coding error rather than the software. Pipeline causes (extraction_miss, mapper_gap, tool_data_gap, rule_bug, grader_bug, model_reasoning) are assigned at triage, never by the coder.

### D3 — Minimum occurrences for a finding

A candidate becomes eligible at >=3 encounters in the batch, or >=2 if the same grouping key appeared in a prior batch; below that it stays a candidate and is re-checked next batch.

### D4 — Eval runs per candidate

Three runs per candidate, reported as mean, per-run values and run-to-run variance. The pinned model (claude-opus-5, see config/models.yaml) accepts neither a temperature nor a seed parameter, so both are recorded as null; the seeds 1..3 are requested-seed labels that discriminate the three runs in the LLM cache key and in traces, not provider sampling controls.

### D5 — Gate thresholds

Targeted error rate must fall by at least 25% relative (mean over runs) without rising on any run; regression agreement may drop at most 1.0 pp and no per-type recall more than 2.0 pp; scrubber error count may not increase; the escalation check must pass for every encounter.

### D6 — Minimum evaluable n for module-level holdout reporting

Below 10 evaluable encounters a module result is reported as "insufficient (n=...)".

### D7 — When holdout predictions are generated

Sealed predictions are produced at each version freeze so a model retirement between versions cannot break the final comparison; an optional re-run of all four happens after v3.

### D8 — Blind subset size and official label

Five encounters per batch (11%) are coded blind before the draft is revealed; the reviewed label is official and the blind label feeds the anchoring analysis.

### D9 — Primary inferential metric

With n = 40 a binary 100% tier has +-15 pp intervals and cannot separate versions; the continuous mean with paired bootstrap CIs can. Tier shares are headline descriptives.

### D10 — Module activation rule

A module is on iff evaluable_n_est = flagged x spot-check precision >= 15 and at least five flags were confirmed in the spot-check.

## Seeds and parameters (not numbered decisions)

- seeds: `{"audit_sample_seed": 20260920, "bootstrap_seed": 20260921, "seal_seed": 20260917, "second_cpc_seed": 20260919, "split_seed": 20260918}`
- holdout: `{'n': 40, 'stratify_on': 'subset'}`
- dev split: `{'seed': 20, 'batches': 3, 'batch_size': 45, 'spare': 12, 'blind_per_batch': 5}`
