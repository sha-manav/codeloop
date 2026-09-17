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
