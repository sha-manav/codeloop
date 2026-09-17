# Prevalence audit (Phase 2)

Generated 2026-09-17T13:25:48Z. Dev encounters audited: 167 (the 40 holdout encounters are never audited).
Model(s): claude-opus-5; prompt hash(es): da9371916f1de85e…;
tokens in/out: 527313/57618. Flags: 106 (106 with a located evidence span).
Patient facts documented: age 139/167, sex 166/167.

Flags per encounter by subset: aci: mean 0.70 over 91; virtassist: mean 0.66 over 44; virtscribe: mean 0.41 over 32

## Spot-check

Sample drawn 2026-09-17T13:21:09Z with seed 20260920: 15 flagged-arm + 15 random-arm encounters out of 167 (86 with ≥1 flag).
Grades recorded: 26 flags graded (11 confirmed); missed services reported: 0.
Graders (latest grade per flag): {'provisional:claude-fable-5-1': 26}.

**Provisional:** grades from provisional:claude-fable-5-1 are a machine stand-in, not a CPC judgment. The CPC's grades replace them automatically (latest grade per flag wins); the module decisions below are provisional until then.

## Per-category prevalence and precision

`evaluable_n_est = flagged_encounters × precision` (precision from graded flags in the spot-check; Wilson 95% interval).

| Category | Flags | Flagged encounters | Graded | Confirmed | Precision (95% CI) | evaluable_n_est |
|---|---|---|---|---|---|---|
| in_office_injection | 0 | 0 | 0 | 0 | — | — |
| joint_aspiration_injection | 3 | 3 | 0 | 0 | — | — |
| laceration_repair | 0 | 0 | 0 | 0 | — | — |
| lesion_destruction | 0 | 0 | 0 | 0 | — | — |
| ecg | 9 | 9 | 2 | 0 | 0.00 (0.00–0.66) | 0.0 |
| spirometry | 3 | 3 | 0 | 0 | — | — |
| nebulizer_treatment | 0 | 0 | 0 | 0 | — | — |
| cerumen_removal | 0 | 0 | 0 | 0 | — | — |
| waived_in_office_test | 9 | 8 | 2 | 0 | 0.00 (0.00–0.66) | 0.0 |
| immunization | 0 | 0 | 0 | 0 | — | — |
| drug_administration_with_wastage | 0 | 0 | 0 | 0 | — | — |
| in_office_imaging | 64 | 62 | 15 | 11 | 0.73 (0.48–0.89) | 45.5 |
| other_procedure | 18 | 17 | 7 | 0 | 0.00 (0.00–0.35) | 0.0 |

## Module decisions (decision D10)

Rule: on iff `evaluable_n_est >= 15` and `confirmed >= 5`.

| Module | Signal | Flagged encounters | Confirmed | evaluable_n_est | Decision | Arithmetic |
|---|---|---|---|---|---|---|
| vaccine_admin | immunization | 0 | 0 | — | off | no flagged encounters (evaluable_n_est = 0) |
| jw_jz | drug_administration_with_wastage | 0 | 0 | — | off | no flagged encounters (evaluable_n_est = 0) |
| qw | waived_in_office_test | 8 | 0 | 0.0 | off | evaluable_n_est 0.0 < 15 and confirmed 0 < 5 |
| distinct_59x | ≥2 distinct procedure categories in one encounter | 15 | 0 | 0.0 | off | evaluable_n_est 0.0 < 15 and confirmed 0 < 5 |

## core_lines allowlist proposal (owner fills `config/scope.yaml`)

Code numbers only. A category is proposed for the allowlist when at least one flag was confirmed; the owner decides the final ranges.

| Category | Confirmed | evaluable_n_est | Proposed ranges |
|---|---|---|---|
| in_office_injection | 0 | — | hold: 96372-96379 |
| joint_aspiration_injection | 0 | — | hold: 20600-20611 |
| laceration_repair | 0 | — | hold: 12001-12007, 12011-12018, 12031-12057 |
| lesion_destruction | 0 | — | hold: 17000-17004, 17110-17111, 11300-11313, 11400-11446 |
| ecg | 0 | 0.0 | hold: 93000-93010 |
| spirometry | 0 | — | hold: 94010-94010, 94060-94060 |
| nebulizer_treatment | 0 | — | hold: 94640-94640 |
| cerumen_removal | 0 | — | hold: 69209-69210 |
| waived_in_office_test | 0 | 0.0 | hold: 81002-81002, 81025-81025, 82962-82962, 83036-83036, 86308-86308, 87804-87804, 87811-87811, 87880-87880 |
| immunization | 0 | — | hold: 90460-90461, 90471-90474, 90476-90759, 91300-91322 |
| drug_administration_with_wastage | 0 | — | hold: 96372-96379, J0000-J9999 |
| in_office_imaging | 11 | 45.5 | propose: 71045-71048, 72020-72120, 73000-73140, 73501-73660, 74018-74022 |
| other_procedure | 0 | 0.0 | hold: (none: define per finding) |

## Notes

- Flags are candidates from one structured LLM call per encounter; only the spot-check grades are human judgments.
- Speaker tags in some subsets are swapped by ASR, so `counseling_by` from the transcript is unreliable evidence.
- Per-encounter flag counts for the Phase 3 difficulty index are in `runs/audit/flag_counts.json`.
