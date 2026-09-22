# GATE — FIND-DX-0039

base `45c7beeb734e` → head `dc1ce88e861e` · **PASS**

| check | result | detail |
|---|---|---|
| paths | pass | only permitted paths changed |
| targeted | pass | error rate base 1.000 -> head 0.750 (need <= 0.750); runs [0.75, 0.75, 0.75] |
| regression_agreement | pass | mean agreement base 0.22838337930930522 -> head 0.7631241803464025 (max drop 0.010) |
| regression_dx_recall | pass | dx_recall base 0.2009685230024213 -> head 0.8595641646489104 (max drop 0.020) |
| regression_line_recall | pass | line_recall base 0.3023255813953488 -> head 0.9767441860465116 (max drop 0.020) |
| scrubber | pass | error-severity failures base 0.6666666666666666 -> head 0.0 (non-increasing) |
| compliance_escalation | pass | escalation failures across runs: 0 |

changed paths: codeloop/agent/pipeline.py, codeloop/tools/icd_retrieval.py

targeted error per run — base: [1.0, 1.0, 1.0]; head: [0.75, 0.75, 0.75]
