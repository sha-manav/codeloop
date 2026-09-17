# Ingest report

Generated 2026-09-17T12:28:15Z by `codeloop seal`. This report contains counts and hashes only;
it never contains encounter text and never lists holdout encounter IDs.

## Sources

| Source | Title | License | Landing | Pinned |
|---|---|---|---|---|
| aci_bench | ACI-Bench corpus (figshare release v1) | CC BY 4.0 | https://doi.org/10.6084/m9.figshare.22494601.v1 | b909b2bb9cf1d19de08df15cddde7bd0179665e4 |
| amazon_labels | ICD-10-CM annotations from "Toward Reliable Clinical Coding with Language Models: Verification and Lightweight Adaptation" (amazon-science) | CC BY-NC 4.0 | https://github.com/amazon-science/toward-clinical-coding-verification-adaptation | 311f4afea6e6697f748ad23b62e8a0d70772736b |
| medcoder | Dataset for MedCodER, A Generative AI Assistant for Medical Coding (Zenodo record 13308316) | CC BY-NC-ND 4.0 | https://doi.org/10.5281/zenodo.13308316 | release as linked |

## Downloads

| Source | File | Bytes | SHA-256 | MD5 | Verified against |
|---|---|---|---|---|---|
| aci_bench | aci-bench-2023.zip | 1319280 | `ed5f7cf5542fe5bfe1e6021613d40bcd7450ffbff561b5afa9c2289049881612` | `e3e2456f1e84cdae844f122890c9340c` | md5 |
| aci_bench | train.csv | 611240 | `6c778d4ac5e6cc6f1964786f9286e8d765c210f22ed6b57f83aff8497409cea4` | `fddd77b58e9a388e628d56fd03a3c94e` | — |
| aci_bench | valid.csv | 177400 | `6629e89e3fb409d2b3eceab60dc7b32fe1d3fb8d4e07795039284965522aa4d0` | `724170c475f2fbb3a746825640797ebc` | — |
| aci_bench | clinicalnlp_taskB_test1.csv | 349998 | `5cc4008e68545f84913744a8e493a58bdf17ba7e1b7a0be46d6943d6bfca9471` | `abdfa9ee82378310aa2ec2ff4b57eb4b` | — |
| aci_bench | clinicalnlp_taskC_test2.csv | 385979 | `599e3330a14e25a0e056aee1365ffac7ebe50058f15821eae42a5513c2bb5a4f` | `e48e105aecbb085282d7f24fb3eec0c1` | — |
| aci_bench | clef_taskC_test3.csv | 381908 | `d3c18362a42124ea2bd1b2b4b66ba76a11bb123dfdb416471ae3b5924d1428ec` | `481da1da2cc849f130cc8a13141342b3` | — |
| amazon_labels | code_train.csv | 9080 | `4d5bdaf743cfaad5863b486d9f783ed6b80a15b8a29d55d07fdd28506e89b1fb` | `f3b253b042f3013aeb90930c99fd98e3` | — |
| amazon_labels | code_valid.csv | 2269 | `443c40ca1931f3257654cefb16ba6f72a75bb44db0f437107eb613d0af29bfad` | `c1c9d327a9e562aae15e6b44209658cf` | — |
| amazon_labels | code_test.csv | 13773 | `9a443ca6271232b4dc90341a7efa07e6bda49ec7329cec80c1323cb29f232d7f` | `ab6c0644606cd2ba81d1b8bf97dbf8b0` | — |
| medcoder | text.csv | 505666 | `c869c55854a98a894aa776ad909e0582bc53e4de2f30a77f4d52e41dc52feda5` | `f389aeac1abce0fac28a319058ab5c6f` | md5 |
| medcoder | diagnosis.csv | 21079 | `60dd9f8d57a7fa84c711b1d5f4dc17c7273a0d553e069b783222107aae492106` | `6fab815448536b58a3315253fd32f0b5` | md5 |
| medcoder | supporting_evidence.csv | 120692 | `d1c2c33768c6079de85367419221f4957a1b34b81218c1b5af04f503e041ecc1` | `ec45bd77804bd8ee7ae756d73809c360` | md5 |
| medcoder | text_holdout.csv | 55320 | `71e6295ce6047d2eb192f1a71d8583c7a8b0ac6f8f05b6035a26072ccba5f957` | `b216c317f917b7b3dda99a9ff1fe38f2` | md5 |
| medcoder | diagnosis_holdout.csv | 2167 | `f09fe624e97b6afaa93b1a7552b25e366462dfae0b40d36cb9e6697006f1068b` | `36eefd666e977fafbb5160b0027f2aeb` | md5 |

## ACI-Bench encounters

- files parsed: train.csv, valid.csv, clinicalnlp_taskB_test1.csv, clinicalnlp_taskC_test2.csv, clef_taskC_test3.csv
- encounters: 207 (expected 207)
- per original split: {'train': 67, 'valid': 20, 'test1': 40, 'test2': 40, 'test3': 40}
- per subset: {'aci': 112, 'virtassist': 55, 'virtscribe': 40}
- per split × subset: {'train': {'aci': 35, 'virtassist': 20, 'virtscribe': 12}, 'valid': {'aci': 11, 'virtassist': 5, 'virtscribe': 4}, 'test1': {'aci': 22, 'virtassist': 10, 'virtscribe': 8}, 'test2': {'aci': 22, 'virtassist': 10, 'virtscribe': 8}, 'test3': {'aci': 22, 'virtassist': 10, 'virtscribe': 8}}
- dialogue turns: 11436; speaker tags: {'doctor': 5897, 'patient': 5406, 'patient_guest': 132, 'unknown': 1}
- untagged continuation lines (appended to previous turn): 12; leading untagged lines (speaker `unknown`): 1; blank lines dropped: 14
- notes with trailing whitespace (kept as released): 88; texts containing CR (normalized): 0
- note length (chars) min/mean/max: 852/2687/5712
- not ingested: `*_metadata.csv` (patient age/sex, chief complaint) and `src_experiment_data/` (ASR variants); the agent must take patient facts from the note/dialogue with spans (spec §6).

## Holdout

- n = 40, seed = 20260917, stratified on subset; allocation: {'virtassist': 11, 'virtscribe': 8, 'aci': 21}
- IDs: `data/splits/holdout_ids.txt`; content hashes: `data/sealed/holdout_content_hashes.json`; encrypted content: `data/sealed/holdout_encounters.enc`

## Amazon ICD-10-CM labels (calibration only)

- documents: 207; code rows: 438
- matched by encounter ID: 207; unmatched documents: 0 (0 rows)
- code strings not shaped like ICD-10-CM: 0
- encounters without an Amazon record: none
- committed after holdout removal: 167 records in `data/labels_public/amazon.jsonl`

## MedCodER labels (calibration only)

- documents: 204 (partition test: 184, MedCodER's own 'holdout' partition: 20 — unrelated to the CodeLoop holdout)
- diagnosis rows: 396; supporting-evidence rows: 883
- matched to encounters by note text: 204 ({'exact': 6, 'rstrip': 11, 'collapsed_ws': 187}); unmatched documents: 0 (0 rows dropped); duplicate matches: 0
- MedCodER's own offsets verified against MedCodER's text: diagnoses 396/396, evidence 0/883
- snippets re-located uniquely in our note_text: diagnoses 301 located / 95 not; evidence 866 located / 17 not
- code strings not shaped like ICD-10-CM: 1
- encounters without a MedCodER record: D2N096, D2N191; plus 1 holdout encounter(s), not listed

## License notes (owner review before any publication)

- ACI-Bench: CC BY 4.0. Normalized encounter text in `data/dev/` is gitignored by default and rebuilt by `make data`; committing it is an owner decision.
- Amazon annotations: CC BY-NC 4.0 (non-commercial). Committed as a filtered derivative for calibration.
- MedCodER: CC BY-NC-ND 4.0 (non-commercial, no derivatives). The committed file is a row-filtered, reformatted subset; confirm that this counts as permitted redistribution before publishing the repository.
