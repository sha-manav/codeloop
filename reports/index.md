# CodeLoop reports

Regenerated 2026-09-20T09:29:56Z from committed data. In-scope fields: diagnoses, first-listed, and lines in the scope allowlist; E/M is excluded.

![curve](curve.svg)

## Headline: live and holdout cells

| version | batch | tag | n | mean agreement | ≥75% | ≥90% | 100% | touches | minutes |
|---|---|---|---|---|---|---|---|---|---|
| v0 | batch1 | live | 45 | 0.7058 | 0.51 | 0.29 | 0.29 | 1.82 | 4.42 |
| — | holdout | not scored yet | | | | | | | |

## Appendix: version × batch (all cells, tagged)

| version | batch | tag | mean agreement | dx recall | line recall | scrubber acceptance | evidence support | query precision |
|---|---|---|---|---|---|---|---|---|
| v0 | batch1 | live | 0.7058 | 0.946 | 1.000 | 1.00 | 0.62 (474) | 0.46 (87) |

## Anchoring (blind subset)

| version | batch | n | blind vs reviewed | agent vs blind | agent vs reviewed |
|---|---|---|---|---|---|
| v0 | batch1 | 4 | 0.510 | 0.308 | 0.527 |

## Scrubber rule-fire counts per cell

- v0 on batch1: none

## Findings log

| id | status | batch | count | before | after | next-batch error rate |
|---|---|---|---|---|---|---|
| FIND-DX-0001 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0002 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0003 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0004 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0005 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0006 | resolved | batch1 | 3 | 0.5833 | 0.1667 | None |
| FIND-DX-0007 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0008 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0009 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0010 | ambiguous | batch1 | 7 | None | None | None |
| FIND-DX-0011 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0012 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0013 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0014 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0015 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0016 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0017 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0018 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0019 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0020 | resolved | batch1 | 3 | 0.8889 | 0.2222 | None |
| FIND-DX-0021 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0022 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0023 | resolved | batch1 | 3 | 1.0 | 0.0 | None |
| FIND-DX-0024 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0025 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0026 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0027 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0028 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0029 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0030 | resolved | batch1 | 5 | 1.0 | 0.4 | None |
| FIND-DX-0031 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0032 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0033 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0034 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0035 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0036 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0037 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0038 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0039 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0040 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0041 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0042 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0043 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0044 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0045 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0046 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0047 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0048 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0049 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0001 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0002 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0003 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0004 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0005 | candidate | batch1 | 3 | None | None | None |
| FIND-LINES-0006 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0007 | candidate | batch1 | 2 | None | None | None |
| FIND-LINES-0008 | candidate | batch1 | 1 | None | None | None |

## Other reports

- [Audit](audit.md)
- [Ingest](ingest.md)
- Holdout: not scored yet
- [calibration_dev_seed](calibration_dev_seed.md)
