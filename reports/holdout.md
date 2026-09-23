# Holdout results (n = 40)

Scored once on 2026-09-23T20:28:14Z with the frozen scorer; primary coder `cpc1`.
Primary inferential metric (D9): mean per-encounter field agreement with paired bootstrap 95% CIs; tier shares are descriptive (Wilson intervals).

| version | mean agreement | hierarchical | ≥75% | ≥90% | 100% | dx recall | line recall | core_lines |
|---|---|---|---|---|---|---|---|---|
| v0 | 0.3686 | 0.4156 | 0.10 (0.04–0.23) | 0.07 (0.03–0.20) | 0.07 (0.03–0.20) | 0.535 | 1.000 | n=10, line-field agreement 0.6785714285714286 |
| v1 | 0.3616 | 0.4079 | 0.15 (0.07–0.29) | 0.10 (0.04–0.23) | 0.10 (0.04–0.23) | 0.509 | 0.833 | n=10, line-field agreement 0.6538461538461539 |
| v2 | 0.3680 | 0.4221 | 0.10 (0.04–0.23) | 0.10 (0.04–0.23) | 0.10 (0.04–0.23) | 0.553 | 1.000 | n=10, line-field agreement 0.6785714285714286 |
| v3 | 0.3456 | 0.3948 | 0.12 (0.05–0.26) | 0.07 (0.03–0.20) | 0.07 (0.03–0.20) | 0.518 | 1.000 | n=10, line-field agreement 0.6551724137931034 |

## Pairwise differences (later − earlier), paired bootstrap

| pair | diff | 95% CI | n |
|---|---|---|---|
| v0->v1 | -0.0070 | -0.0494 … +0.0332 | 40 |
| v0->v2 | -0.0006 | -0.0331 … +0.0305 | 40 |
| v0->v3 | -0.0230 | -0.0605 … +0.0153 | 40 |
| v1->v2 | +0.0064 | -0.0285 … +0.0420 | 40 |
| v1->v3 | -0.0160 | -0.0575 … +0.0208 | 40 |
| v2->v3 | -0.0224 | -0.0540 … +0.0092 | 40 |
