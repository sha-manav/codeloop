# CodeLoop ledger

Append-only chronology of process events: UTC timestamp, event, hashes, actor.
Entries are appended by `codeloop` commands and never edited or deleted; a correction is a new entry.

## 2026-09-17T12:28:17Z — seal

- actor: manavshah <manavshah03@gmail.com>
- spec_version: 1.2
- codeloop_version: 0.1.0
- python: 3.12.14
- seal_seed: 20260917
- holdout_n: 40
- stratify_on: subset
- subset_counts: {"aci": 112, "virtassist": 55, "virtscribe": 40}
- allocation: {"aci": 21, "virtassist": 11, "virtscribe": 8}
- holdout_ids_sha256: 844ba4470653b79740ddc20268d98cdb6f8891d69a8a2ee6021208b8d20ab66a
- holdout_content_hashes_sha256: 6a0f42080522d9eaafc7006ff3c4ef1fceb818c5d66b89ad9bde662faeebb7f2
- holdout_encounters_enc_sha256: c05c062de63e1e1aaad0c2eb2141d7617ced7daa95755fdf87da150d0a9bef4c
- holdout_encounters_enc_meta_sha256: e7b9a1383f39cb7a721e371b843a5c595ed6a729e491fae04cb8700e885415e7
- dev_encounters_count: 167
- dev_encounters_sha256: 79bf27c2a7ad1bae4250384d7aa9d6425fcb3414b82086cf5c18ab09e0c7bdf1
- labels_public_amazon_count: 167
- labels_public_amazon_sha256: a71ac5bf4b43a60df580de66c1c43a11a11f49c3475bee8cba90ca02135c1fe1
- labels_public_medcoder_count: 165
- labels_public_medcoder_sha256: 26cea4b92d4f5660dcc825fef52ee82087f3c1bc3018db98bf88a65e01c0e5a2
- source_manifest_sha256: 33544f66eabaf31e89ae50f21e0469ef98aff06eb78a01d40f49021cbaa06499
- downloads: [{"bytes": 1319280, "md5": "e3e2456f1e84cdae844f122890c9340c", "name": "aci-bench-2023.zip", "sha256": "ed5f7cf5542fe5bfe1e6021613d40bcd7450ffbff561b5afa9c2289049881612", "source": "aci_bench", "url": "https://ndownloader.figshare.com/files/41498793"}, {"bytes": 611240, "md5": "fddd77b58e9a388e628d56fd03a3c94e", "name": "train.csv", "sha256": "6c778d4ac5e6cc6f1964786f9286e8d765c210f22ed6b57f83aff8497409cea4", "source": "aci_bench", "url": "https://ndownloader.figshare.com/files/41498793#aci-bench-corpus/challenge_data/train.csv"}, {"bytes": 177400, "md5": "724170c475f2fbb3a746825640797ebc", "name": "valid.csv", "sha256": "6629e89e3fb409d2b3eceab60dc7b32fe1d3fb8d4e07795039284965522aa4d0", "source": "aci_bench", "url": "https://ndownloader.figshare.com/files/41498793#aci-bench-corpus/challenge_data/valid.csv"}, {"bytes": 349998, "md5": "abdfa9ee82378310aa2ec2ff4b57eb4b", "name": "clinicalnlp_taskB_test1.csv", "sha256": "5cc4008e68545f84913744a8e493a58bdf17ba7e1b7a0be46d6943d6bfca9471", "source": "aci_bench", "url": "https://ndownloader.figshare.com/files/41498793#aci-bench-corpus/challenge_data/clinicalnlp_taskB_test1.csv"}, {"bytes": 385979, "md5": "e48e105aecbb085282d7f24fb3eec0c1", "name": "clinicalnlp_taskC_test2.csv", "sha256": "599e3330a14e25a0e056aee1365ffac7ebe50058f15821eae42a5513c2bb5a4f", "source": "aci_bench", "url": "https://ndownloader.figshare.com/files/41498793#aci-bench-corpus/challenge_data/clinicalnlp_taskC_test2.csv"}, {"bytes": 381908, "md5": "481da1da2cc849f130cc8a13141342b3", "name": "clef_taskC_test3.csv", "sha256": "d3c18362a42124ea2bd1b2b4b66ba76a11bb123dfdb416471ae3b5924d1428ec", "source": "aci_bench", "url": "https://ndownloader.figshare.com/files/41498793#aci-bench-corpus/challenge_data/clef_taskC_test3.csv"}, {"bytes": 9080, "md5": "f3b253b042f3013aeb90930c99fd98e3", "name": "code_train.csv", "sha256": "4d5bdaf743cfaad5863b486d9f783ed6b80a15b8a29d55d07fdd28506e89b1fb", "source": "amazon_labels", "url": "https://raw.githubusercontent.com/amazon-science/toward-clinical-coding-verification-adaptation/311f4afea6e6697f748ad23b62e8a0d70772736b/annotation/code_train.csv"}, {"bytes": 2269, "md5": "c1c9d327a9e562aae15e6b44209658cf", "name": "code_valid.csv", "sha256": "443c40ca1931f3257654cefb16ba6f72a75bb44db0f437107eb613d0af29bfad", "source": "amazon_labels", "url": "https://raw.githubusercontent.com/amazon-science/toward-clinical-coding-verification-adaptation/311f4afea6e6697f748ad23b62e8a0d70772736b/annotation/code_valid.csv"}, {"bytes": 13773, "md5": "ab6c0644606cd2ba81d1b8bf97dbf8b0", "name": "code_test.csv", "sha256": "9a443ca6271232b4dc90341a7efa07e6bda49ec7329cec80c1323cb29f232d7f", "source": "amazon_labels", "url": "https://raw.githubusercontent.com/amazon-science/toward-clinical-coding-verification-adaptation/311f4afea6e6697f748ad23b62e8a0d70772736b/annotation/code_test.csv"}, {"bytes": 505666, "md5": "f389aeac1abce0fac28a319058ab5c6f", "name": "text.csv", "sha256": "c869c55854a98a894aa776ad909e0582bc53e4de2f30a77f4d52e41dc52feda5", "source": "medcoder", "url": "https://zenodo.org/api/records/13308316/files/text.csv/content"}, {"bytes": 21079, "md5": "6fab815448536b58a3315253fd32f0b5", "name": "diagnosis.csv", "sha256": "60dd9f8d57a7fa84c711b1d5f4dc17c7273a0d553e069b783222107aae492106", "source": "medcoder", "url": "https://zenodo.org/api/records/13308316/files/diagnosis.csv/content"}, {"bytes": 120692, "md5": "ec45bd77804bd8ee7ae756d73809c360", "name": "supporting_evidence.csv", "sha256": "d1c2c33768c6079de85367419221f4957a1b34b81218c1b5af04f503e041ecc1", "source": "medcoder", "url": "https://zenodo.org/api/records/13308316/files/supporting_evidence.csv/content"}, {"bytes": 55320, "md5": "b216c317f917b7b3dda99a9ff1fe38f2", "name": "text_holdout.csv", "sha256": "71e6295ce6047d2eb192f1a71d8583c7a8b0ac6f8f05b6035a26072ccba5f957", "source": "medcoder", "url": "https://zenodo.org/api/records/13308316/files/text_holdout.csv/content"}, {"bytes": 2167, "md5": "36eefd666e977fafbb5160b0027f2aeb", "name": "diagnosis_holdout.csv", "sha256": "f09fe624e97b6afaa93b1a7552b25e366462dfae0b40d36cb9e6697006f1068b", "source": "medcoder", "url": "https://zenodo.org/api/records/13308316/files/diagnosis_holdout.csv/content"}]
- raw_entries_deleted: 3

## 2026-09-17T13:00:07Z — gate: phase 0 cleared

- actor: manavshah <manavshah03@gmail.com>
- decision: D0 seal seed 20260917 confirmed by the owner; key stored outside the repo (owner keychain)
- holdout_ids_sha256: 844ba4470653b79740ddc20268d98cdb6f8891d69a8a2ee6021208b8d20ab66a
- project_yaml_sha256: 2699ba284dc077f5b34dfc3ad852f5446a4363883ce321ecb389b28d56affacf
- next_phase: 1 — contract and scorer

## 2026-09-17T13:05:32Z — phase 1 accepted: contract and scorer

- actor: manavshah <manavshah03@gmail.com>
- scoring_version: 1.0
- scoring_tree_sha256_pre_freeze: 8ac5646c3621c55d86b46de987433f46118117ffadaed942cc08cb47e8b5f02a
- scope_yaml_sha256: fde4ce434b25714a9b6fd334fe06b03014ddde750309bc36a4e7a21411c9df49
- note: codeloop/scoring is self-contained (stdlib + pydantic + yaml); the freeze hash is recorded at Phase 3

## 2026-09-17T13:15:43Z — audit run

- actor: manavshah <manavshah03@gmail.com>
- run_id: audit-20260917T131543Z-bac7d8
- model: claude-opus-5
- prompt_hash: ffe2bd81a064447d46e310ec9943f04fffefeb097e8ca7b40b150817ed1da6b7
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- encounters: 0
- flags: 0
- per_category_flags: {}
- tokens_in: 0
- tokens_out: 0
- cache_hits: 0
- failures: 1
- estimated_cost_usd: 0.0

## 2026-09-17T13:17:15Z — audit run

- actor: manavshah <manavshah03@gmail.com>
- run_id: audit-20260917T131701Z-1790ac
- model: claude-opus-5
- prompt_hash: ffe2bd81a064447d46e310ec9943f04fffefeb097e8ca7b40b150817ed1da6b7
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- encounters: 3
- flags: 3
- per_category_flags: {"other_procedure": 3}
- tokens_in: 11022
- tokens_out: 1637
- cache_hits: 0
- failures: 0
- estimated_cost_usd: 0.15

## 2026-09-17T13:20:59Z — audit run

- actor: manavshah <manavshah03@gmail.com>
- run_id: audit-20260917T131816Z-d9a3cb
- model: claude-opus-5
- prompt_hash: da9371916f1de85ea606500dc2b011571814856a5c966211bd5c5e271d54ac81
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- encounters: 167
- flags: 106
- per_category_flags: {"ecg": 9, "in_office_imaging": 64, "joint_aspiration_injection": 3, "other_procedure": 18, "spirometry": 3, "waived_in_office_test": 9}
- tokens_in: 527313
- tokens_out: 57618
- cache_hits: 0
- failures: 0
- estimated_cost_usd: 4.43

## 2026-09-17T13:21:09Z — audit sample

- actor: manavshah <manavshah03@gmail.com>
- seed: 20260920
- n: 30
- population: 167
- population_flagged: 86
- encounter_ids: {"flagged": ["D2N004", "D2N048", "D2N054", "D2N086", "D2N094", "D2N096", "D2N109", "D2N117", "D2N120", "D2N131", "D2N133", "D2N141", "D2N160", "D2N184", "D2N193"], "random": ["D2N026", "D2N067", "D2N068", "D2N078", "D2N089", "D2N113", "D2N125", "D2N136", "D2N153", "D2N166", "D2N169", "D2N174", "D2N175", "D2N182", "D2N196"]}

## 2026-09-17T13:27:28Z — gate: phase 2 (provisional)

- actor: manavshah <manavshah03@gmail.com>
- audit_report_sha256: aa482264bef4840ae31521b35022206bf06a91fb2d4aa27c96c678ab434dc3bb
- spot_check_grader: provisional:claude-fable-5-1 (machine stand-in; CPC grades pending and will override)
- module_decisions: {"distinct_59x": false, "jw_jz": false, "qw": false, "vaccine_admin": false}
- core_lines: in_office_imaging ranges only (11/15 provisional precision, evaluable_n_est 45.5); other categories held
- scope_yaml_sha256: d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03
- owner_action: CPC grades the spot-check via `codeloop audit serve --reviewer <id>`, then `codeloop audit report`, revise scope.yaml, re-freeze before Phase 8

## 2026-09-17T13:28:55Z — freeze

- actor: manavshah <manavshah03@gmail.com>
- codeloop_version: 0.1.0
- split_seed: 20260918
- sizes: {"batch1": 45, "batch2": 45, "batch3": 45, "seed": 20, "spare": 12}
- blind_per_batch: 5
- set_summary: {"batch1": {"mean_amazon_codes": 1.8, "mean_audit_flags": 0.733, "mean_difficulty": -0.193, "mean_note_len": 2580.778, "n": 45, "subsets": {"aci": 24, "virtassist": 12, "virtscribe": 9}}, "batch2": {"mean_amazon_codes": 2.2, "mean_audit_flags": 0.578, "mean_difficulty": -0.01, "mean_note_len": 2616.911, "n": 45, "subsets": {"aci": 24, "virtassist": 12, "virtscribe": 9}}, "batch3": {"mean_amazon_codes": 2.111, "mean_audit_flags": 0.533, "mean_difficulty": -0.009, "mean_note_len": 2740.178, "n": 45, "subsets": {"aci": 25, "virtassist": 11, "virtscribe": 9}}, "seed": {"mean_amazon_codes": 2.15, "mean_audit_flags": 0.7, "mean_difficulty": 0.269, "mean_note_len": 2742.35, "n": 20, "subsets": {"aci": 12, "virtassist": 5, "virtscribe": 3}}, "spare": {"mean_amazon_codes": 2.083, "mean_audit_flags": 0.75, "mean_difficulty": 0.345, "mean_note_len": 2796.917, "n": 12, "subsets": {"aci": 6, "virtassist": 4, "virtscribe": 2}}}
- dev_split_sha256: 8172cd79122c28eda0d4ef2b492764df3ff5fa440d5ff6cb1fc10dd79784f332
- scope_yaml_sha256: d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03
- scope_status: provisional
- project_yaml_sha256: 8879f817b7cad164f5d3c57337448f801148b69047fd1abcb72c8adad09b4c30
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- config_tree_sha256: f81acb30d3946d8880a3b4721e7523cbdc3322eeaa07cebda119961c947f637f
- splits_tree_sha256: 6aeb65788dc2d07ace87d838fa52de386a03edb2b0be9a3569e353306e23e17b
- scoring_tree_sha256: df376e926e0db2c576209b15c630a37f9ada644023453ad862ddc947d24a7411
- decisions: D0–D10 locked

## 2026-09-17T13:44:22Z — tables build

- actor: manavshah <manavshah03@gmail.com>
- tables_yaml_sha256: 47a324256764e933abb47ef82eab82f0577f18f703a2bf80e04a3385210e3b89
- row_counts: {"asp_ndc": 7367, "cvx": 290, "hcpcs": 16320, "hcpcs_modifiers": 579, "icd10cm": 98375, "icd10cm_index": 63109, "mue": 15212, "ptp": 2637645, "rvu": 19453}
- tables_sqlite_sha256: 7191362299a10af92cdf2fe428a4bfe7dfee50abcadedae6f302fa4f95c9c2f8

## 2026-09-17T13:51:05Z — run dev seed

- actor: manavshah <manavshah03@gmail.com>
- run_id: dev-seed-20260917T135105Z-06731b
- commit: 3c2bb7e08f75383f6c2bf50fdd590f5da34ccfb8
- seeds: [1]
- encounters: 2
- llm_calls: 0
- tokens_in: 0
- tokens_out: 0
- cache_hits: 0
- failures: 2
- scrubber_rule_counts: {}
- compliance_failed: 0
- predictions_sha256: {"1": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_sha256: d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03
- tables_version: tables.yaml:47a324256764e933/parser:1
- estimated_cost_usd: 0.0

## 2026-09-17T13:52:43Z — run dev seed

- actor: manavshah <manavshah03@gmail.com>
- run_id: dev-seed-20260917T135153Z-7801bd
- commit: 2e5b6cff6b44be7c1cf50fa7230789fe332e6769
- seeds: [1]
- encounters: 1
- llm_calls: 3
- tokens_in: 7469
- tokens_out: 2988
- cache_hits: 0
- failures: 0
- scrubber_rule_counts: {}
- compliance_failed: 0
- predictions_sha256: {"1": "c5b3070467df39d7524ddd7af741bdb069f0a3147b1860278e705f3f98ffbf01"}
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_sha256: d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03
- tables_version: tables.yaml:47a324256764e933/parser:1
- estimated_cost_usd: 0.11

## 2026-09-17T13:55:06Z — run dev seed

- actor: manavshah <manavshah03@gmail.com>
- run_id: dev-seed-20260917T135305Z-2e3c12
- commit: 2e5b6cff6b44be7c1cf50fa7230789fe332e6769
- seeds: [1]
- encounters: 20
- llm_calls: 47
- tokens_in: 114241
- tokens_out: 46126
- cache_hits: 3
- failures: 0
- scrubber_rule_counts: {}
- compliance_failed: 0
- predictions_sha256: {"1": "e201e2a3884059f7f680d549d523a4165870d0e895f47d43122c6a74f2a6117a"}
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_sha256: d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03
- tables_version: tables.yaml:47a324256764e933/parser:1
- estimated_cost_usd: 1.72

## 2026-09-17T13:59:55Z — run dev seed

- actor: manavshah <manavshah03@gmail.com>
- run_id: dev-seed-20260917T135844Z-26618f
- commit: 2e5b6cff6b44be7c1cf50fa7230789fe332e6769
- seeds: [1]
- encounters: 20
- llm_calls: 47
- tokens_in: 114241
- tokens_out: 47494
- cache_hits: 27
- failures: 0
- scrubber_rule_counts: {"STRUCTURAL:error": 1}
- compliance_failed: 0
- predictions_sha256: {"1": "d807ff4e44bc223f9b97e4182af42c4db2b901e4c1b3c091adb06c3a1ef575ab"}
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_sha256: d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03
- tables_version: tables.yaml:47a324256764e933/parser:1
- estimated_cost_usd: 1.76

## 2026-09-17T14:02:39Z — run dev spare

- actor: manavshah <manavshah03@gmail.com>
- run_id: dev-spare-20260917T140100Z-70e89d
- commit: aea2584fdcaedb9d61f2e21da5193db9d76cd949
- seeds: [1]
- encounters: 12
- llm_calls: 26
- tokens_in: 73611
- tokens_out: 33416
- cache_hits: 0
- failures: 0
- scrubber_rule_counts: {}
- compliance_failed: 0
- predictions_sha256: {"1": "90ab3970e6691ecd1b12e1774d8a3a5bca0dc6864f505e0ddc19b52cd7884015"}
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_sha256: d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03
- tables_version: tables.yaml:47a324256764e933/parser:1
- estimated_cost_usd: 1.2

## 2026-09-17T14:15:33Z — holdout predict v0 (sealed)

- actor: manavshah <manavshah03@gmail.com>
- n: 40
- predictions_enc_sha256: 942ecbef74d4cd0f69e25a18d08ecc92353438e4d2b5477e57b2c0a6e648d0d3
- traces_enc_sha256: 7a6cb471ce9ccde407b4c08f8d8e5218c0acf564f3f6392c03ce5a856e45527e
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_sha256: d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03
- tables_version: tables.yaml:47a324256764e933/parser:1
- tokens_in: 271584
- tokens_out: 123407
- cache: disabled
- seed: 1

## 2026-09-17T14:15:33Z — version freeze v0

- actor: manavshah <manavshah03@gmail.com>
- commit: 2fd92e0e97c821cca1daed387c9d00481fae5f38
- tag: v0
- models_yaml: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_yaml: d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03
- tables_yaml: 47a324256764e933abb47ef82eab82f0577f18f703a2bf80e04a3385210e3b89
- project_decisions: 0fde53c535095a2227a030082760517dd7683b70cc2a968769b7fb677b98c7a3
- scoring_tree: df376e926e0db2c576209b15c630a37f9ada644023453ad862ddc947d24a7411
- config_tree: e6a12d0ced459526a21ee40b6480f4c38236e5867733ae121d75290f267d6149
- prompt_hashes: {"audit": "da9371916f1de85ea606500dc2b011571814856a5c966211bd5c5e271d54ac81", "extract": "7491eb0094deeef74e820702f18ad5c728534984f3c8ed68fc99a0d47f856339", "map_dx": "ecfc8fbd2fd14049735a2a9260101ee25bac8fa974016b5a96cf4bba89233594", "map_lines": "10a6c8c2db8110e7a5915da78017d95d8aed5fe47160ed3d449201c74437a7ad", "ping": "e9a79ea28a061709d7d3838bb8dfe791b6496a74b93d4c0790c3053d559ff32f"}
- sealed_predictions_sha256: 942ecbef74d4cd0f69e25a18d08ecc92353438e4d2b5477e57b2c0a6e648d0d3

## 2026-09-17T14:20:15Z — run v0 batch1

- actor: manavshah <manavshah03@gmail.com>
- run_id: v0-batch1-20260917T141554Z-e93a04
- commit: 35ba86dc6c90063fb60847386a65628ac50c4521
- seeds: [1]
- encounters: 45
- llm_calls: 110
- tokens_in: 284682
- tokens_out: 119524
- cache_hits: 0
- failures: 0
- scrubber_rule_counts: {}
- compliance_failed: 0
- predictions_sha256: {"1": "3c20a2069b163c3f4ed8f3cc0a1f1d215dca6e66b2a2389423a3dcea957937f2"}
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_sha256: d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03
- tables_version: tables.yaml:47a324256764e933/parser:1
- estimated_cost_usd: 4.41

## 2026-09-18T06:29:31Z — coder guidelines committed

- actor: manavshah <manavshah03@gmail.com>
- file: docs/CODER_GUIDELINES.md
- version: 1.0
- sha256: 101e69ddbab0080e02d273e0e1d94edd42acf118f47d281ac78458d07472631c
- evidence_policy: note_only (matches D1)

## 2026-09-18T06:31:35Z — note

- actor: manavshah <manavshah03@gmail.com>
- text: Owner-requested edits after the freeze: D4 reworded (3 runs unchanged; temperature/provider seed recorded as null, seeds are cache-key discriminators), scope.yaml icd10cm_release pinned to FY2027. Config hashes now differ from the freeze entry; run 'codeloop freeze --supersede' (and 'codeloop version freeze v0 --supersede' if v0 should reflect the new config) before batch1 review.

## 2026-09-18T06:33:17Z — freeze superseded (correction)

- actor: manavshah <manavshah03@gmail.com>
- reason: config corrected after the freeze: D4 reworded to match models.yaml, icd10cm_release pinned to FY2027
- previous_commit: 3c2bb7e08f75383f6c2bf50fdd590f5da34ccfb8
- renamed_tag: freeze-provisional
- previous_dev_split: data/splits/dev_split.provisional-20260918T063317Z.json
- previous_dev_split_sha256: 8172cd79122c28eda0d4ef2b492764df3ff5fa440d5ff6cb1fc10dd79784f332
- previous_scoring_tree_sha256: df376e926e0db2c576209b15c630a37f9ada644023453ad862ddc947d24a7411

## 2026-09-18T06:33:17Z — freeze

- actor: manavshah <manavshah03@gmail.com>
- codeloop_version: 0.1.0
- split_seed: 20260918
- sizes: {"batch1": 45, "batch2": 45, "batch3": 45, "seed": 20, "spare": 12}
- blind_per_batch: 5
- set_summary: {"batch1": {"mean_amazon_codes": 1.8, "mean_audit_flags": 0.733, "mean_difficulty": -0.193, "mean_note_len": 2580.778, "n": 45, "subsets": {"aci": 24, "virtassist": 12, "virtscribe": 9}}, "batch2": {"mean_amazon_codes": 2.2, "mean_audit_flags": 0.578, "mean_difficulty": -0.01, "mean_note_len": 2616.911, "n": 45, "subsets": {"aci": 24, "virtassist": 12, "virtscribe": 9}}, "batch3": {"mean_amazon_codes": 2.111, "mean_audit_flags": 0.533, "mean_difficulty": -0.009, "mean_note_len": 2740.178, "n": 45, "subsets": {"aci": 25, "virtassist": 11, "virtscribe": 9}}, "seed": {"mean_amazon_codes": 2.15, "mean_audit_flags": 0.7, "mean_difficulty": 0.269, "mean_note_len": 2742.35, "n": 20, "subsets": {"aci": 12, "virtassist": 5, "virtscribe": 3}}, "spare": {"mean_amazon_codes": 2.083, "mean_audit_flags": 0.75, "mean_difficulty": 0.345, "mean_note_len": 2796.917, "n": 12, "subsets": {"aci": 6, "virtassist": 4, "virtscribe": 2}}}
- dev_split_sha256: befc71b0a30073fa94f17e93e771183204bfd08f516aba98ef96622fabdc3305
- scope_yaml_sha256: 099cef2ae33929bb61f8cece6597506f5edb42e50d164cd0a4d833ce31a5d735
- scope_status: provisional
- project_yaml_sha256: 9003e5305d179ad2d8326eb38669598d9dc9e5283cf1f53faaaccf68cc3ababe
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- config_tree_sha256: e47b9fb7c803366e00528ed0b3ee9262dbee1176207ff5da217670bb984feebc
- splits_tree_sha256: ee7189ae572e4aa484d632faeead1afb100b3681b77de5496b8102d4b3073085
- scoring_tree_sha256: df376e926e0db2c576209b15c630a37f9ada644023453ad862ddc947d24a7411
- decisions: D0–D10 locked

## 2026-09-18T06:33:32Z — version v0 superseded (correction)

- actor: manavshah <manavshah03@gmail.com>
- reason: re-frozen on the corrected config (superseded freeze 3c2bb7e)
- version: v0
- previous_commit: 2fd92e0e97c821cca1daed387c9d00481fae5f38
- renamed_tag: v0-provisional
- moved: versions/v0 -> versions/v0-provisional; runs/v0 -> runs/v0-provisional; data/sealed/predictions_v0.enc -> data/sealed/predictions_v0-provisional.enc; data/sealed/predictions_v0.enc.meta.json -> data/sealed/predictions_v0-provisional.enc.meta.json; data/sealed/predictions_v0.sha256 -> data/sealed/predictions_v0-provisional.sha256; data/sealed/traces_v0.enc -> data/sealed/traces_v0-provisional.enc; data/sealed/traces_v0.enc.meta.json -> data/sealed/traces_v0-provisional.enc.meta.json

## 2026-09-18T06:38:06Z — holdout predict v0 (sealed)

- actor: manavshah <manavshah03@gmail.com>
- n: 40
- predictions_enc_sha256: 05af4b0d0c5de8eedf332da7328255a44e28dc9778a15ecb2f688592d5bb2ce5
- traces_enc_sha256: 65559a2a53fc5c9647eec11d7c61a3210c38f5b944a9db70179d1b9b64689014
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_sha256: 099cef2ae33929bb61f8cece6597506f5edb42e50d164cd0a4d833ce31a5d735
- tables_version: tables.yaml:47a324256764e933/parser:1
- tokens_in: 278084
- tokens_out: 123742
- cache: disabled
- seed: 1

## 2026-09-18T06:38:06Z — version freeze v0

- actor: manavshah <manavshah03@gmail.com>
- commit: bfa5d76d595e7e59f6d922791701d1e84cc03966
- tag: v0
- models_yaml: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_yaml: 099cef2ae33929bb61f8cece6597506f5edb42e50d164cd0a4d833ce31a5d735
- tables_yaml: 47a324256764e933abb47ef82eab82f0577f18f703a2bf80e04a3385210e3b89
- project_decisions: eef4e335d8f4f4352c3b73ebd83b977c9682b03c06a498412b6a5461e088f514
- scoring_tree: df376e926e0db2c576209b15c630a37f9ada644023453ad862ddc947d24a7411
- config_tree: e47b9fb7c803366e00528ed0b3ee9262dbee1176207ff5da217670bb984feebc
- prompt_hashes: {"audit": "da9371916f1de85ea606500dc2b011571814856a5c966211bd5c5e271d54ac81", "cluster_findings": "4f6bceb52b30d59830a35e613e7d188e0c72cfc863f2bd3f36a354683ec12afe", "extract": "7491eb0094deeef74e820702f18ad5c728534984f3c8ed68fc99a0d47f856339", "map_dx": "ecfc8fbd2fd14049735a2a9260101ee25bac8fa974016b5a96cf4bba89233594", "map_lines": "10a6c8c2db8110e7a5915da78017d95d8aed5fe47160ed3d449201c74437a7ad", "ping": "e9a79ea28a061709d7d3838bb8dfe791b6496a74b93d4c0790c3053d559ff32f"}
- sealed_predictions_sha256: 05af4b0d0c5de8eedf332da7328255a44e28dc9778a15ecb2f688592d5bb2ce5

## 2026-09-18T06:38:14Z — run v0 batch1

- actor: manavshah <manavshah03@gmail.com>
- run_id: v0-batch1-20260918T063809Z-ff1251
- commit: a28ce7ec8caabfaba6279ea9e8ad4bbc7b22088e
- seeds: [1]
- encounters: 45
- llm_calls: 110
- tokens_in: 284682
- tokens_out: 119524
- cache_hits: 110
- failures: 0
- scrubber_rule_counts: {}
- compliance_failed: 0
- predictions_sha256: {"1": "0f29c2733fb3a3191e57cd7ef57918f422bd422714b911100f8d3915548dd73c"}
- models_yaml_sha256: 767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3
- scope_sha256: 099cef2ae33929bb61f8cece6597506f5edb42e50d164cd0a4d833ce31a5d735
- tables_version: tables.yaml:47a324256764e933/parser:1
- estimated_cost_usd: 4.41
