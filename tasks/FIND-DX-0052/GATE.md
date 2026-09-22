# GATE — FIND-DX-0052

base `2904fa861917` → head `5b4e825ba5d3` · **PASS**

| check | result | detail |
|---|---|---|
| paths | pass | only permitted paths changed |
| targeted | pass | error rate base 0.917 -> head 0.333 (need <= 0.688); runs [0.5, 0.25, 0.25] |
| regression_agreement | pass | mean agreement base 0.7406612523279189 -> head 0.7348076614743282 (max drop 0.010) |
| regression_dx_recall | pass | dx_recall base 0.8333333333333334 -> head 0.8669467787114846 (max drop 0.020) |
| regression_line_recall | pass | line_recall base 0.9880952380952381 -> head 0.9880952380952381 (max drop 0.020) |
| scrubber | pass | error-severity failures base 1.6666666666666667 -> head 0.0 (non-increasing) |
| compliance_escalation | pass | escalation failures across runs: 0 |

changed paths: codeloop/agent/pipeline.py, codeloop/tools/icd_retrieval.py, tasks/FIND-DX-0052/EXEC_PLAN.md

targeted error per run — base: [1.0, 0.75, 1.0]; head: [0.5, 0.25, 0.25]
