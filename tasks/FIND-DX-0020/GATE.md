# GATE — FIND-DX-0020

base `05b6e64` → head `9d30187d95ce` · **PASS**

| check | result | detail |
|---|---|---|
| paths | pass | only permitted paths changed |
| targeted | pass | error rate base 0.889 -> head 0.222 (need <= 0.667); runs [0.0, 0.333, 0.333] |
| regression_agreement | pass | mean agreement base 0.6851501379279158 -> head 0.7194679600235155 (max drop 0.010) |
| regression_dx_recall | pass | dx_recall base 0.9021739130434782 -> head 0.9021739130434782 (max drop 0.020) |
| regression_line_recall | pass | line_recall base 1.0 -> head 1.0 (max drop 0.020) |
| scrubber | pass | error-severity failures base 0.6666666666666666 -> head 0.6666666666666666 (non-increasing) |
| compliance_escalation | pass | escalation failures across runs: 0 |

changed paths: codeloop/agent/pipeline.py, codeloop/rules/dx_rules.py, codeloop/rules/sections.py

targeted error per run — base: [1.0, 0.667, 1.0]; head: [0.0, 0.333, 0.333]
