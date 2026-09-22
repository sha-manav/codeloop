# CodeLoop reports

Regenerated 2026-09-22T20:25:36Z from committed data. In-scope fields: diagnoses, first-listed, and lines in the scope allowlist; E/M is excluded.

![curve](curve.svg)

## Headline: live and holdout cells

| version | batch | tag | n | mean agreement | ≥75% | ≥90% | 100% | touches | minutes |
|---|---|---|---|---|---|---|---|---|---|
| v0 | batch1 | live | 45 | 0.7058 | 0.51 | 0.29 | 0.29 | 1.82 | 4.42 |
| v1 | batch2 | live | 45 | 0.8733 | 0.84 | 0.62 | 0.62 | 0.82 | 4.46 |
| v2 | batch3 | live | 45 | 0.8959 | 0.87 | 0.67 | 0.62 | 0.69 | 2.72 |
| — | holdout | not scored yet | | | | | | | |

## Appendix: version × batch (all cells, tagged)

| version | batch | tag | mean agreement | dx recall | line recall | scrubber acceptance | evidence support | query precision |
|---|---|---|---|---|---|---|---|---|
| v0 | batch1 | live | 0.7058 | 0.946 | 1.000 | 1.00 | 0.62 (474) | 0.46 (87) |
| v1 | batch1 | in-sample | 0.7372 | 0.946 | 1.000 | 1.00 | 0.62 (474) | 0.46 (87) |
| v1 | batch2 | live | 0.8733 | 0.870 | 1.000 | 1.00 | 0.97 (452) | 0.57 (94) |
| v2 | batch1 | in-sample | 0.7196 | 0.946 | 1.000 | 1.00 | 0.62 (474) | 0.46 (87) |
| v2 | batch2 | in-sample | 0.8649 | 0.904 | 1.000 | 1.00 | 0.97 (452) | 0.57 (94) |
| v2 | batch3 | live | 0.8959 | 0.914 | 1.000 | 1.00 | 0.95 (539) | 0.37 (95) |

## Anchoring (blind subset)

| version | batch | n | blind vs reviewed | agent vs blind | agent vs reviewed |
|---|---|---|---|---|---|
| v0 | batch1 | 4 | 0.510 | 0.308 | 0.527 |
| v1 | batch1 | 4 | 0.510 | 0.308 | 0.527 |
| v1 | batch2 | 5 | 0.455 | 0.254 | 0.674 |
| v2 | batch1 | 4 | 0.510 | 0.308 | 0.527 |
| v2 | batch2 | 5 | 0.455 | 0.267 | 0.669 |
| v2 | batch3 | 5 | 0.524 | 0.367 | 0.798 |

## Scrubber rule-fire counts per cell

- v0 on batch1: none
- v1 on batch1: none
- v1 on batch2: none
- v2 on batch1: none
- v2 on batch2: none
- v2 on batch3: none

## Findings log

| id | status | batch | count | before | after | next-batch error rate |
|---|---|---|---|---|---|---|
| FIND-DX-0001 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0002 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0003 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0004 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0005 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0006 | resolved | batch1 | 3 | 0.5833 | 0.1667 | 0.25 |
| FIND-DX-0007 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0008 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0009 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0010 | rejected | batch1 | 7 | None | None | None |
| FIND-DX-0011 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0012 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0013 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0014 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0015 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0016 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0017 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0018 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0019 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0020 | resolved | batch1 | 3 | 0.8889 | 0.2222 | 0.0 |
| FIND-DX-0021 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0022 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0023 | resolved | batch1 | 3 | 1.0 | 0.0 | 0.0 |
| FIND-DX-0024 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0025 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0026 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0027 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0028 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0029 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0030 | resolved | batch1 | 5 | 1.0 | 0.4 | 0.0 |
| FIND-DX-0031 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0032 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0033 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0034 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0035 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0036 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0037 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0038 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0039 | resolved | batch1 | 3 | 1.0 | 0.75 | None |
| FIND-DX-0040 | candidate | batch1 | 2 | None | None | None |
| FIND-DX-0041 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0042 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0043 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0044 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0045 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0046 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0047 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0048 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0049 | candidate | batch1 | 1 | None | None | None |
| FIND-DX-0050 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0051 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0052 | resolved | batch2 | 5 | 0.917 | 0.333 | 0.071 |
| FIND-DX-0053 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0054 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0055 | candidate | batch2 | 3 | None | None | None |
| FIND-DX-0056 | candidate | batch2 | 2 | None | None | None |
| FIND-DX-0057 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0058 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0059 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0060 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0061 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0062 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0063 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0064 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0065 | candidate | batch2 | 2 | None | None | None |
| FIND-DX-0066 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0067 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0068 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0069 | candidate | batch2 | 1 | None | None | None |
| FIND-DX-0070 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0071 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0072 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0073 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0074 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0075 | candidate | batch3 | 2 | None | None | None |
| FIND-DX-0076 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0077 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0078 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0079 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0080 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0081 | candidate | batch3 | 2 | None | None | None |
| FIND-DX-0082 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0083 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0084 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0085 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0086 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0087 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0088 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0089 | candidate | batch3 | 1 | None | None | None |
| FIND-DX-0090 | candidate | batch3 | 1 | None | None | None |
| FIND-LINES-0001 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0002 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0003 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0004 | candidate | batch1 | 2 | None | None | None |
| FIND-LINES-0005 | candidate | batch1 | 3 | None | None | None |
| FIND-LINES-0006 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0007 | candidate | batch1 | 2 | None | None | None |
| FIND-LINES-0008 | candidate | batch1 | 1 | None | None | None |
| FIND-LINES-0009 | candidate | batch2 | 1 | None | None | None |
| FIND-LINES-0010 | candidate | batch2 | 1 | None | None | None |
| FIND-LINES-0011 | candidate | batch2 | 1 | None | None | None |
| FIND-LINES-0012 | candidate | batch2 | 1 | None | None | None |
| FIND-LINES-0013 | candidate | batch3 | 1 | None | None | None |

## Other reports

- [Audit](audit.md)
- [Ingest](ingest.md)
- Holdout: not scored yet
- [calibration_dev_seed](calibration_dev_seed.md)
