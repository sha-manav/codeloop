# GATE — FIND-DX-0030

base `ba0a30d` → head `0b9b92cc16ea` · **FAIL**

| check | result | detail |
|---|---|---|
| paths | pass | only permitted paths changed |
| targeted | pass | error rate base 1.000 -> head 0.400 (need <= 0.750); runs [0.4, 0.4, 0.4] |
| regression_agreement | pass | mean agreement base 0.7058024691358025 -> head 0.7194679600235155 (max drop 0.010) |
| regression_dx_recall | FAIL | dx_recall base 0.9456521739130435 -> head 0.9021739130434782 (max drop 0.020) |
| regression_line_recall | pass | line_recall base 1.0 -> head 1.0 (max drop 0.020) |
| scrubber | FAIL | error-severity failures base 0.0 -> head 0.6666666666666666 (non-increasing) |
| compliance_escalation | pass | escalation failures across runs: 0 |

changed paths: codeloop/agent/pipeline.py, codeloop/rules/dx_rules.py, codeloop/rules/sections.py

targeted error per run — base: [1.0]; head: [0.4, 0.4, 0.4]
