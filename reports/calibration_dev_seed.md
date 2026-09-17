# Calibration: dev on seed

Reference only: public label sets were produced under other scopes and guidelines; they are not the project's gold.

## vs Amazon (n = 20)

- exact-code diagnosis precision/recall/F1 (mean per encounter): 0.399 / 0.592 / 0.457
- category (first three characters) precision/recall/F1: 0.469 / 0.696 / 0.539
- first-listed code present in the reference set: 13/20 = 0.650 (Wilson 0.433–0.819)
- predicted codes per encounter: 3.25; reference codes per encounter: 2.15

| Encounter | predicted | reference | exact matches |
|---|---|---|---|
| D2N002 | 4 | 3 | 2 |
| D2N006 | 5 | 3 | 2 |
| D2N012 | 5 | 3 | 1 |
| D2N048 | 2 | 3 | 0 |
| D2N050 | 2 | 1 | 1 |
| D2N055 | 0 | 1 | 0 |
| D2N058 | 5 | 4 | 3 |
| D2N083 | 1 | 1 | 1 |
| D2N100 | 2 | 2 | 1 |
| D2N108 | 2 | 1 | 1 |
| D2N113 | 5 | 1 | 0 |
| D2N140 | 5 | 1 | 1 |
| D2N141 | 5 | 4 | 1 |
| D2N151 | 2 | 3 | 1 |
| D2N158 | 5 | 3 | 2 |
| D2N160 | 4 | 3 | 3 |
| D2N162 | 1 | 1 | 1 |
| D2N173 | 5 | 3 | 2 |
| D2N176 | 3 | 1 | 1 |
| D2N187 | 2 | 1 | 0 |

## vs MedCodER (n = 20)

- exact-code diagnosis precision/recall/F1 (mean per encounter): 0.384 / 0.604 / 0.445
- category (first three characters) precision/recall/F1: 0.444 / 0.692 / 0.514
- first-listed code present in the reference set: 13/20 = 0.650 (Wilson 0.433–0.819)
- predicted codes per encounter: 3.25; reference codes per encounter: 1.95

| Encounter | predicted | reference | exact matches |
|---|---|---|---|
| D2N002 | 4 | 3 | 2 |
| D2N006 | 5 | 3 | 1 |
| D2N012 | 5 | 3 | 2 |
| D2N048 | 2 | 1 | 0 |
| D2N050 | 2 | 1 | 0 |
| D2N055 | 0 | 1 | 0 |
| D2N058 | 5 | 4 | 3 |
| D2N083 | 1 | 1 | 1 |
| D2N100 | 2 | 2 | 1 |
| D2N108 | 2 | 1 | 1 |
| D2N113 | 5 | 1 | 0 |
| D2N140 | 5 | 1 | 1 |
| D2N141 | 5 | 4 | 2 |
| D2N151 | 2 | 3 | 1 |
| D2N158 | 5 | 3 | 2 |
| D2N160 | 4 | 1 | 1 |
| D2N162 | 1 | 1 | 1 |
| D2N173 | 5 | 3 | 2 |
| D2N176 | 3 | 1 | 1 |
| D2N187 | 2 | 1 | 1 |
