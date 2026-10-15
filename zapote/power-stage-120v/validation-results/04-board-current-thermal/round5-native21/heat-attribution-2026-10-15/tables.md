## Checks

| check | value |
|---|---|
| c18_h10 field 0.5 mm: max |sum of terms - full solve| on copper (K) | 3.77e-06 |
| c18_h10 field 0.5 mm: max |sum - full| junction nodes (K) | 3.15e-08 |
| c22_h10 field 0.5 mm: max |sum of terms - full solve| on copper (K) | 5.28e-06 |
| c22_h10 field 0.5 mm: max |sum - full| junction nodes (K) | 3.48e-08 |
| c18_h10 0.25 mm: max |synth - gate run| over tj / pad / block / FET row (K) | 1.32e-06 |
| c18_h10 0.25 mm: block peak at the gate run's location | True |
| c18_h10 0.5 mm: max |synth - gate run| over tj / pad / block / FET row (K) | 1.61e-06 |
| c18_h10 0.5 mm: block peak at the gate run's location | True |
| c22_h10 0.25 mm: max |synth - gate run| over tj / pad / block / FET row (K) | 1.32e-06 |
| c22_h10 0.25 mm: block peak at the gate run's location | True |
| c22_h10 0.5 mm: max |synth - gate run| over tj / pad / block / FET row (K) | 1.58e-06 |
| c22_h10 0.5 mm: block peak at the gate run's location | True |
| c18_h10: max |sum of terms - synthesized gate est| (K) | 1.02e-06 |
| c18_h10: max |sum of terms - margins-repro.json est_c (0.1 K rounded)| (K) | 4.88e-02 |
| c18_h10: max |sum of terms - committed margins.json est_c (0.1 K rounded)| (K) | 4.88e-02 |
| c18_h10: rows compared | 44 |
| c22_h10: max |sum of terms - synthesized gate est| (K) | 1.22e-06 |
| c22_h10: max |sum of terms - margins-repro.json est_c (0.1 K rounded)| (K) | 4.92e-02 |
| c22_h10: max |sum of terms - committed margins.json est_c (0.1 K rounded)| (K) | 4.92e-02 |
| c22_h10: rows compared | 44 |
| part watts at c22: max |unit x coef - run_basis.inputs| (W) | 5.55e-17 |
| part watts at c28: max |unit x coef - run_basis.inputs| (W) | 5.55e-17 |
| max |energy balance| over unit solves (W) | 2.81e-09 |

## Attribution c18_h10 (bay 61 C): every gated row

K at the row, 0.25 mm locator. 'bay+tie' = bay air + FET-case tie; 'heat' = all heat terms; 'mesh' = 3|Q(0.25)-Q(0.5)|. Top 5 heat terms with K and share of the rise over bay.

| row | est C | limit C | margin K | bay+tie (tie) | heat K | mesh K | top heat terms (K, share of rise over bay) |
|---|---|---|---|---|---|---|---|
| C40 body | 108.8 | 110.0 | +1.2 | 69.1 (+8.1) | 38.3 | 1.4 | part R_on 5.2 (11 %); part RECOM 4.9 (10 %); part HF_film 4.7 (10 %); sw_b_high 4.4 (9 %); sw_b_low 3.5 (7 %) |
| R10 terminal derating | 128.8 | 131.9 | +3.1 | 69.9 (+8.9) | 47.0 | 11.9 | part R_on 19.3 (28 %); sw_a_low 5.3 (8 %); sw_b_high 3.8 (6 %); sw_b_low 3.6 (5 %); part RECOM 1.9 (3 %) |
| C41 body | 106.2 | 110.0 | +3.8 | 69.9 (+8.9) | 35.3 | 1.0 | part RECOM 5.9 (13 %); part R_on 5.8 (13 %); part HF_film 4.8 (11 %); sw_b_high 4.2 (9 %); bus_mixed_q5 2.9 (6 %) |
| R20 terminal derating | 127.4 | 131.9 | +4.6 | 71.7 (+10.7) | 46.3 | 9.3 | part R_on 19.6 (30 %); sw_b_high 4.9 (7 %); part RECOM 3.6 (5 %); sw_b_low 3.3 (5 %); part R5 2.8 (4 %) |
| C38 body | 105.0 | 110.0 | +5.0 | 68.0 (+7.0) | 36.2 | 0.9 | part HF_film 4.5 (10 %); sw_b_high 4.2 (10 %); part R_on 4.0 (9 %); sw_b_low 3.8 (9 %); part RECOM 3.4 (8 %) |
| laminate 1 mm block | 125.0 | 130.0 | +5.0 | 70.4 (+9.4) | 48.0 | 6.7 | part R_on 13.7 (21 %); part R5 5.8 (9 %); sw_b_high 4.5 (7 %); sw_b_low 3.9 (6 %); part RECOM 3.1 (5 %) |
| R18 terminal derating | 126.7 | 131.9 | +5.3 | 72.3 (+11.3) | 44.5 | 9.9 | part R_on 21.5 (33 %); sw_b_high 4.6 (7 %); part RECOM 3.7 (6 %); bus_mixed_q5 2.9 (4 %); sw_b_low 2.4 (4 %) |
| U26 Tj | 119.1 | 125.0 | +5.9 | 61.4 (+0.4) | 46.3 | 11.4 | part U26 37.7 (65 %); part small_LDO 2.3 (4 %); sw_a_low 1.0 (2 %); sw_a 0.8 (1 %); coil_feed 0.8 (1 %) |
| R12 terminal derating | 125.4 | 131.9 | +6.6 | 70.4 (+9.4) | 48.1 | 6.9 | part R_on 14.0 (22 %); part R5 5.8 (9 %); sw_b_high 4.5 (7 %); sw_b_low 3.9 (6 %); part RECOM 3.1 (5 %) |
| laminate FET row | 122.1 | 130.0 | +7.9 | 70.6 (+9.6) | 47.0 | 4.4 | part R_on 13.5 (22 %); part R5 5.7 (9 %); sw_b_high 4.3 (7 %); sw_b_low 3.8 (6 %); leg_a_18p7 3.1 (5 %) |
| C39 body | 99.5 | 110.0 | +10.5 | 66.1 (+5.1) | 32.7 | 0.8 | sw_a_low 4.3 (11 %); part HF_film 4.2 (11 %); sw_b_high 4.0 (10 %); sw_b_low 3.9 (10 %); part R_on 2.6 (7 %) |
| R58 terminal derating | 116.4 | 128.2 | +11.8 | 70.6 (+9.6) | 43.4 | 2.4 | part R_on 6.7 (12 %); part R_off 5.7 (10 %); part R5 5.0 (9 %); sw_b_high 4.7 (9 %); sw_b_low 3.9 (7 %) |
| U42 Tj | 133.6 | 150.0 | +16.4 | 63.6 (+2.6) | 66.2 | 3.7 | part RECOM 57.2 (79 %); part R_on 1.7 (2 %); sw_b_high 1.3 (2 %); sw_b_low 0.9 (1 %); bus_mixed_q5 0.9 (1 %) |
| R57 terminal derating | 111.6 | 128.2 | +16.6 | 71.8 (+10.8) | 38.3 | 1.5 | part R_on 7.4 (15 %); part R_off 7.2 (14 %); sw_b_high 4.9 (10 %); part RECOM 4.1 (8 %); bus_mixed_q5 2.8 (6 %) |
| R54 terminal derating | 111.2 | 128.2 | +17.1 | 69.6 (+8.6) | 40.5 | 1.0 | part R_off 7.1 (14 %); part R_on 4.8 (10 %); sw_b_high 4.4 (9 %); sw_b_low 4.0 (8 %); sw_a_low 3.7 (7 %) |
| U41 Tj | 129.5 | 150.0 | +20.5 | 62.5 (+1.5) | 62.8 | 4.3 | part RECOM 55.6 (81 %); sw_b_high 0.9 (1 %); part R_on 0.8 (1 %); sw_b_low 0.8 (1 %); sw_a_low 0.7 (1 %) |
| R10 element | 132.3 | 155.0 | +22.7 | 70.1 (+9.1) | 53.3 | 9.0 | part R_on 25.8 (36 %); sw_a_low 5.4 (8 %); sw_b_high 3.7 (5 %); sw_b_low 3.5 (5 %); part RECOM 1.8 (3 %) |
| R20 element | 132.0 | 155.0 | +23.0 | 71.7 (+10.7) | 52.6 | 7.7 | part R_on 26.2 (37 %); sw_b_high 4.8 (7 %); part RECOM 3.5 (5 %); sw_b_low 3.3 (5 %); part R5 2.8 (4 %) |
| R18 element | 131.1 | 155.0 | +23.9 | 72.3 (+11.3) | 50.9 | 7.9 | part R_on 28.5 (41 %); sw_b_high 4.5 (6 %); part RECOM 3.6 (5 %); bus_mixed_q5 2.9 (4 %); sw_b_low 2.3 (3 %) |
| R12 element | 130.3 | 155.0 | +24.7 | 70.5 (+9.5) | 54.6 | 5.2 | part R_on 20.8 (30 %); part R5 5.9 (8 %); sw_b_high 4.4 (6 %); sw_b_low 3.8 (6 %); part RECOM 3.0 (4 %) |
| R53 terminal derating | 100.9 | 128.2 | +27.3 | 67.1 (+6.1) | 33.4 | 0.4 | sw_a_low 6.1 (15 %); sw_b_high 4.0 (10 %); sw_b_low 3.8 (10 %); sw_a 3.3 (8 %); part R_on 2.9 (7 %) |
| R58 element | 117.9 | 155.0 | +37.1 | 70.5 (+9.5) | 45.0 | 2.5 | part R_off 6.8 (12 %); part R_on 6.7 (12 %); part R5 5.2 (9 %); sw_b_high 4.7 (8 %); sw_b_low 3.9 (7 %) |
| R57 element | 112.8 | 155.0 | +42.2 | 71.8 (+10.8) | 39.7 | 1.3 | part R_off 8.6 (17 %); part R_on 7.4 (14 %); sw_b_high 4.9 (9 %); part RECOM 4.1 (8 %); bus_mixed_q5 2.8 (5 %) |
| R54 element | 112.3 | 155.0 | +42.7 | 69.5 (+8.5) | 41.9 | 0.9 | part R_off 8.6 (17 %); part R_on 4.8 (9 %); sw_b_high 4.3 (8 %); sw_b_low 4.0 (8 %); sw_a_low 3.7 (7 %) |
| R5 terminal derating | 118.3 | 161.1 | +42.7 | 70.5 (+9.5) | 45.1 | 2.7 | part R5 7.7 (13 %); part R_on 7.2 (13 %); sw_b_high 4.6 (8 %); sw_b_low 3.9 (7 %); hv_mixed_a 3.5 (6 %) |
| R5 element | 122.8 | 170.0 | +47.2 | 70.7 (+9.7) | 50.3 | 1.8 | part R5 14.6 (24 %); part R_on 7.2 (12 %); sw_b_high 4.4 (7 %); sw_b_low 3.8 (6 %); part RECOM 3.1 (5 %) |
| R53 element | 102.5 | 155.0 | +52.5 | 66.9 (+5.9) | 35.1 | 0.6 | sw_a_low 6.1 (15 %); part R_off 4.6 (11 %); sw_b_high 4.0 (10 %); sw_b_low 3.8 (9 %); sw_a 3.4 (8 %) |

## Attribution c22_h10 (bay 55 C): every gated row

K at the row, 0.25 mm locator. 'bay+tie' = bay air + FET-case tie; 'heat' = all heat terms; 'mesh' = 3|Q(0.25)-Q(0.5)|. Top 5 heat terms with K and share of the rise over bay.

| row | est C | limit C | margin K | bay+tie (tie) | heat K | mesh K | top heat terms (K, share of rise over bay) |
|---|---|---|---|---|---|---|---|
| C40 body | 116.0 | 110.0 | -6.0 | 65.1 (+10.1) | 48.7 | 2.2 | sw_b_high 6.5 (11 %); sw_b_low 5.2 (9 %); part R_on 5.2 (8 %); part RECOM 4.9 (8 %); part HF_film 4.7 (8 %) |
| laminate 1 mm block | 135.8 | 130.0 | -5.8 | 66.7 (+11.7) | 61.4 | 7.8 | part R_on 13.7 (17 %); part R5 8.7 (11 %); sw_b_high 6.7 (8 %); sw_b_low 5.8 (7 %); leg_a_18p7 3.9 (5 %) |
| R12 terminal derating | 136.1 | 131.9 | -4.2 | 66.7 (+11.7) | 61.5 | 7.9 | part R_on 14.0 (17 %); part R5 8.7 (11 %); sw_b_high 6.7 (8 %); sw_b_low 5.8 (7 %); leg_a_18p7 4.0 (5 %) |
| R10 terminal derating | 136.0 | 131.9 | -4.0 | 66.1 (+11.1) | 58.0 | 11.9 | part R_on 19.3 (24 %); sw_a_low 7.9 (10 %); sw_b_high 5.7 (7 %); sw_b_low 5.4 (7 %); sw_a 2.7 (3 %) |
| laminate FET row | 132.6 | 130.0 | -2.6 | 67.0 (+12.0) | 60.3 | 5.3 | part R_on 13.4 (17 %); part R5 8.6 (11 %); sw_b_high 6.5 (8 %); sw_b_low 5.7 (7 %); leg_a_18p7 4.6 (6 %) |
| C38 body | 112.2 | 110.0 | -2.2 | 63.7 (+8.7) | 46.8 | 1.7 | sw_b_high 6.3 (11 %); sw_b_low 5.7 (10 %); sw_a_low 4.7 (8 %); part HF_film 4.5 (8 %); part R_on 4.0 (7 %) |
| R20 terminal derating | 133.7 | 131.9 | -1.8 | 68.4 (+13.4) | 56.0 | 9.4 | part R_on 19.6 (25 %); sw_b_high 7.3 (9 %); sw_b_low 4.9 (6 %); part R5 4.2 (5 %); part RECOM 3.6 (5 %) |
| C41 body | 111.2 | 110.0 | -1.2 | 66.1 (+11.1) | 43.5 | 1.5 | sw_b_high 6.3 (11 %); part RECOM 5.9 (10 %); part R_on 5.8 (10 %); part HF_film 4.8 (8 %); bus_mixed_q5 4.3 (8 %) |
| R18 terminal derating | 131.4 | 131.9 | +0.5 | 69.1 (+14.1) | 52.5 | 9.9 | part R_on 21.5 (28 %); sw_b_high 6.9 (9 %); bus_mixed_q5 4.4 (6 %); part RECOM 3.7 (5 %); sw_b_low 3.6 (5 %) |
| R58 terminal derating | 125.7 | 128.2 | +2.5 | 66.8 (+11.8) | 56.1 | 2.8 | part R5 8.5 (12 %); sw_b_high 7.0 (10 %); part R_on 6.8 (10 %); sw_b_low 5.9 (8 %); hv_mixed_a 4.4 (6 %) |
| C39 body | 105.6 | 110.0 | +4.4 | 61.3 (+6.3) | 42.8 | 1.5 | sw_a_low 6.4 (13 %); sw_b_high 6.0 (12 %); sw_b_low 5.8 (11 %); part HF_film 4.2 (8 %); sw_a 3.6 (7 %) |
| R54 terminal derating | 119.4 | 128.2 | +8.8 | 65.7 (+10.7) | 52.2 | 1.5 | part R_off 7.1 (11 %); sw_b_high 6.5 (10 %); sw_b_low 6.0 (9 %); sw_a_low 5.5 (9 %); part R_on 4.8 (7 %) |
| U26 Tj | 115.6 | 125.0 | +9.4 | 55.5 (+0.5) | 48.9 | 11.2 | part U26 37.7 (62 %); part small_LDO 2.3 (4 %); sw_a_low 1.5 (3 %); sw_a 1.3 (2 %); coil_feed 1.2 (2 %) |
| R57 terminal derating | 117.5 | 128.2 | +10.7 | 68.5 (+13.5) | 47.0 | 2.0 | part R_on 7.4 (12 %); sw_b_high 7.3 (12 %); part R_off 7.2 (12 %); bus_mixed_q5 4.2 (7 %); part RECOM 4.1 (7 %) |
| R12 element | 140.9 | 155.0 | +14.1 | 66.8 (+11.8) | 67.9 | 6.2 | part R_on 20.8 (24 %); part R5 8.8 (10 %); sw_b_high 6.6 (8 %); sw_b_low 5.7 (7 %); leg_a_18p7 4.2 (5 %) |
| R10 element | 139.6 | 155.0 | +15.4 | 66.3 (+11.3) | 64.2 | 9.1 | part R_on 25.8 (30 %); sw_a_low 8.1 (10 %); sw_b_high 5.6 (7 %); sw_b_low 5.3 (6 %); sw_a 2.7 (3 %) |
| R20 element | 138.6 | 155.0 | +16.4 | 68.4 (+13.4) | 62.2 | 8.0 | part R_on 26.2 (31 %); sw_b_high 7.2 (9 %); sw_b_low 4.9 (6 %); part R5 4.2 (5 %); part RECOM 3.5 (4 %) |
| R18 element | 135.7 | 155.0 | +19.3 | 69.1 (+14.1) | 58.6 | 8.0 | part R_on 28.5 (35 %); sw_b_high 6.8 (8 %); bus_mixed_q5 4.3 (5 %); part RECOM 3.6 (4 %); sw_b_low 3.5 (4 %) |
| U42 Tj | 130.6 | 150.0 | +19.4 | 58.3 (+3.3) | 68.9 | 3.4 | part RECOM 57.2 (76 %); sw_b_high 1.9 (3 %); part R_on 1.7 (2 %); sw_b_low 1.3 (2 %); bus_mixed_q5 1.3 (2 %) |
| R53 terminal derating | 108.2 | 128.2 | +20.0 | 62.6 (+7.6) | 44.8 | 0.8 | sw_a_low 9.2 (17 %); sw_b_high 5.9 (11 %); sw_b_low 5.7 (11 %); sw_a 4.9 (9 %); part R_on 2.9 (5 %) |
| U41 Tj | 124.7 | 150.0 | +25.3 | 56.8 (+1.8) | 65.1 | 2.9 | part RECOM 55.6 (80 %); sw_b_high 1.3 (2 %); sw_b_low 1.2 (2 %); sw_a_low 1.0 (1 %); part R_on 0.8 (1 %) |
| R5 terminal derating | 130.9 | 156.7 | +25.8 | 66.8 (+11.8) | 60.1 | 4.0 | part R5 11.5 (15 %); part R_on 7.2 (10 %); sw_b_high 6.9 (9 %); sw_b_low 5.9 (8 %); hv_mixed_a 5.2 (7 %) |
| R58 element | 127.3 | 155.0 | +27.7 | 66.9 (+11.9) | 57.7 | 2.7 | part R5 7.8 (11 %); sw_b_high 7.0 (10 %); part R_off 6.8 (9 %); part R_on 6.7 (9 %); sw_b_low 5.8 (8 %) |
| R5 element | 138.0 | 170.0 | +32.0 | 67.0 (+12.0) | 68.1 | 2.8 | part R5 21.8 (26 %); part R_on 7.2 (9 %); sw_b_high 6.6 (8 %); sw_b_low 5.7 (7 %); hv_mixed_a 4.0 (5 %) |
| R54 element | 120.5 | 155.0 | +34.5 | 65.6 (+10.6) | 53.5 | 1.4 | part R_off 8.6 (13 %); sw_b_high 6.5 (10 %); sw_b_low 6.0 (9 %); sw_a_low 5.5 (8 %); part R_on 4.8 (7 %) |
| R57 element | 118.6 | 155.0 | +36.4 | 68.4 (+13.4) | 48.5 | 1.7 | part R_off 8.6 (14 %); part R_on 7.4 (12 %); sw_b_high 7.2 (11 %); bus_mixed_q5 4.2 (7 %); part RECOM 4.1 (7 %) |
| R53 element | 109.9 | 155.0 | +45.1 | 62.4 (+7.4) | 46.5 | 1.1 | sw_a_low 9.2 (17 %); sw_b_high 5.9 (11 %); sw_b_low 5.7 (10 %); sw_a 5.0 (9 %); part R_off 4.6 (8 %) |

## Full term breakdown, c18_h10 (K at the row)

| term | group | scales | C40 body | R10 terminal derating | C41 body | R20 terminal derating | C38 body | laminate 1 mm block | U26 Tj | R12 terminal derating | laminate FET row | U42 Tj | U41 Tj | R10 element | R5 terminal derating | R5 element |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bay_air | - | - | 61.00 | 61.00 | 61.00 | 61.00 | 61.00 | 61.00 | 61.00 | 61.00 | 61.00 | 61.00 | 61.00 | 61.00 | 61.00 | 61.00 |
| fet_tie | G03 (sink) | t_case - bay | 8.12 | 8.91 | 8.92 | 10.73 | 6.97 | 9.40 | 0.42 | 9.40 | 9.65 | 2.61 | 1.46 | 9.08 | 9.48 | 9.68 |
| ac_l_main | G01 | line (I_line 13.5 A, fixed) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ac_n_main | G01 | line (I_line 13.5 A, fixed) | 0.00 | 0.01 | 0.00 | 0.00 | 0.01 | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 |
| bus_mixed_q2 | G03 | tank I^2 | 0.36 | 1.24 | 0.21 | 0.26 | 0.81 | 0.50 | 0.09 | 0.50 | 0.52 | 0.08 | 0.15 | 1.24 | 0.44 | 0.44 |
| bus_mixed_q5 | G03 | tank I^2 | 2.28 | 0.83 | 2.89 | 2.29 | 1.10 | 1.54 | 0.06 | 1.53 | 1.44 | 0.86 | 0.27 | 0.81 | 1.70 | 1.60 |
| coil_feed | G04 | tank I^2 | 0.01 | 0.02 | 0.01 | 0.01 | 0.02 | 0.01 | 0.81 | 0.01 | 0.01 | 0.00 | 0.01 | 0.02 | 0.01 | 0.01 |
| hv_mixed_a | G08 | tank I^2 | 2.28 | 1.24 | 1.33 | 1.63 | 1.96 | 2.49 | 0.10 | 2.48 | 2.20 | 0.49 | 0.48 | 1.21 | 3.50 | 2.71 |
| hv_mixed_b | G08 | tank I^2 | 1.43 | 0.73 | 0.96 | 1.20 | 1.03 | 1.82 | 0.07 | 1.81 | 1.58 | 0.32 | 0.24 | 0.71 | 2.83 | 2.08 |
| leg_a_18p7 | G03 | tank I^2 | 1.34 | 1.74 | 0.87 | 1.19 | 1.61 | 2.64 | 0.07 | 2.65 | 3.07 | 0.31 | 0.30 | 1.77 | 2.22 | 2.61 |
| leg_b_18p7 | G03 | tank I^2 | 0.26 | 0.15 | 0.19 | 0.28 | 0.20 | 0.53 | 0.01 | 0.54 | 0.63 | 0.06 | 0.04 | 0.15 | 0.52 | 0.72 |
| res_a | G04 | tank I^2 | 0.03 | 0.08 | 0.02 | 0.02 | 0.06 | 0.04 | 0.27 | 0.04 | 0.04 | 0.01 | 0.02 | 0.08 | 0.03 | 0.03 |
| sw_a | G03 | tank I^2 | 0.60 | 1.80 | 0.35 | 0.42 | 1.27 | 0.78 | 0.84 | 0.78 | 0.80 | 0.13 | 0.30 | 1.78 | 0.69 | 0.70 |
| sw_a_low | G03 | tank I^2 | 1.69 | 5.30 | 1.01 | 1.26 | 3.15 | 2.48 | 1.02 | 2.49 | 2.62 | 0.38 | 0.66 | 5.43 | 2.15 | 2.21 |
| sw_b_high | G03 | tank I^2 | 4.36 | 3.84 | 4.24 | 4.87 | 4.19 | 4.50 | 0.79 | 4.49 | 4.35 | 1.30 | 0.90 | 3.74 | 4.62 | 4.45 |
| sw_b_low | G03 | tank I^2 | 3.48 | 3.62 | 2.56 | 3.30 | 3.84 | 3.91 | 0.78 | 3.91 | 3.81 | 0.87 | 0.81 | 3.54 | 3.92 | 3.81 |
| part R5 | G08 | tank I^2 | 2.83 | 1.46 | 1.95 | 2.81 | 2.06 | 5.85 | 0.08 | 5.82 | 5.69 | 0.65 | 0.43 | 1.43 | 7.68 | 14.62 |
| part R_on | G05 | frequency/charge-set (60 kHz window top, deck Q) | 5.16 | 19.26 | 5.83 | 19.60 | 3.99 | 13.75 | 0.20 | 13.95 | 13.51 | 1.68 | 0.85 | 25.80 | 7.21 | 7.20 |
| part R_off | G05 | frequency/charge-set (60 kHz window top, deck Q) | 1.48 | 1.31 | 1.45 | 1.71 | 1.36 | 1.84 | 0.09 | 1.84 | 1.77 | 0.44 | 0.29 | 1.28 | 2.07 | 1.89 |
| part bank | G04 | tank I^2 | 0.05 | 0.12 | 0.03 | 0.03 | 0.10 | 0.06 | 0.25 | 0.06 | 0.06 | 0.01 | 0.03 | 0.12 | 0.05 | 0.05 |
| part C5_C6 | G02 | tank I^2 | 0.01 | 0.04 | 0.01 | 0.01 | 0.03 | 0.02 | 0.04 | 0.02 | 0.02 | 0.00 | 0.01 | 0.04 | 0.02 | 0.02 |
| part HF_film | G03 | fixed estimate | 4.70 | 0.87 | 4.75 | 1.11 | 4.46 | 1.11 | 0.08 | 1.11 | 1.05 | 0.49 | 0.29 | 0.84 | 1.17 | 1.10 |
| part RECOM | G06 | frequency/charge-set (60 kHz window top, deck Q) | 4.88 | 1.91 | 5.89 | 3.61 | 3.44 | 3.10 | 0.17 | 3.09 | 2.90 | 57.16 | 55.57 | 1.85 | 3.33 | 3.13 |
| part U26 | G06 | frequency/charge-set (60 kHz window top, deck Q) | 0.17 | 0.43 | 0.10 | 0.12 | 0.37 | 0.21 | 37.67 | 0.21 | 0.22 | 0.04 | 0.11 | 0.42 | 0.19 | 0.19 |
| part small_LDO | G07/G08 | fixed estimate | 0.13 | 0.17 | 0.12 | 0.09 | 0.17 | 0.11 | 2.26 | 0.11 | 0.11 | 0.59 | 0.58 | 0.16 | 0.11 | 0.11 |
| part PS2 | G06 | frequency/charge-set (60 kHz window top, deck Q) | 0.12 | 0.33 | 0.07 | 0.09 | 0.26 | 0.16 | 0.29 | 0.16 | 0.16 | 0.03 | 0.07 | 0.33 | 0.14 | 0.14 |
| part L1 | G01 | line (I_line 13.5 A, fixed) | 0.05 | 0.12 | 0.03 | 0.03 | 0.10 | 0.06 | 0.12 | 0.06 | 0.06 | 0.01 | 0.03 | 0.12 | 0.05 | 0.05 |
| part drivers | G05 | frequency/charge-set (60 kHz window top, deck Q) | 0.60 | 0.37 | 0.46 | 0.38 | 0.59 | 0.43 | 0.08 | 0.43 | 0.41 | 0.31 | 0.34 | 0.36 | 0.45 | 0.42 |
| part R39 | G09 | tank I^2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| part rest | G04/G09 | fixed estimate | 0.01 | 0.03 | 0.01 | 0.01 | 0.02 | 0.01 | 0.03 | 0.01 | 0.01 | 0.00 | 0.01 | 0.03 | 0.01 | 0.01 |
| mesh_corr | - | - | 1.42 | 11.91 | 0.96 | 9.30 | 0.87 | 6.68 | 11.37 | 6.87 | 4.42 | 3.74 | 4.29 | 9.00 | 2.74 | 1.78 |
| **sum = est** | | | **108.83** | **128.84** | **106.21** | **127.36** | **105.04** | **125.03** | **119.09** | **125.37** | **122.11** | **133.59** | **129.53** | **132.35** | **118.33** | **122.76** |

## Full term breakdown, c22_h10 (K at the row)

| term | group | scales | C40 body | laminate 1 mm block | R12 terminal derating | R10 terminal derating | laminate FET row | C38 body | R20 terminal derating | C41 body | U26 Tj | R10 element | U42 Tj | U41 Tj | R5 terminal derating | R5 element |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bay_air | - | - | 55.00 | 55.00 | 55.00 | 55.00 | 55.00 | 55.00 | 55.00 | 55.00 | 55.00 | 55.00 | 55.00 | 55.00 | 55.00 | 55.00 |
| fet_tie | G03 (sink) | t_case - bay | 10.11 | 11.70 | 11.70 | 11.09 | 12.02 | 8.68 | 13.36 | 11.10 | 0.53 | 11.30 | 3.26 | 1.81 | 11.80 | 12.05 |
| ac_l_main | G01 | line (I_line 13.5 A, fixed) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ac_n_main | G01 | line (I_line 13.5 A, fixed) | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.01 | 0.00 | 0.00 | 0.01 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 |
| bus_mixed_q2 | G03 | tank I^2 | 0.54 | 0.74 | 0.75 | 1.85 | 0.77 | 1.21 | 0.39 | 0.32 | 0.13 | 1.86 | 0.12 | 0.22 | 0.65 | 0.66 |
| bus_mixed_q5 | G03 | tank I^2 | 3.40 | 2.29 | 2.29 | 1.24 | 2.16 | 1.64 | 3.42 | 4.32 | 0.09 | 1.22 | 1.28 | 0.40 | 2.53 | 2.39 |
| coil_feed | G04 | tank I^2 | 0.01 | 0.02 | 0.02 | 0.04 | 0.02 | 0.03 | 0.01 | 0.01 | 1.21 | 0.03 | 0.00 | 0.01 | 0.02 | 0.02 |
| hv_mixed_a | G08 | tank I^2 | 3.40 | 3.72 | 3.70 | 1.86 | 3.30 | 2.93 | 2.44 | 1.99 | 0.15 | 1.80 | 0.74 | 0.72 | 5.23 | 4.05 |
| hv_mixed_b | G08 | tank I^2 | 2.13 | 2.72 | 2.71 | 1.09 | 2.37 | 1.54 | 1.79 | 1.44 | 0.10 | 1.07 | 0.48 | 0.36 | 4.22 | 3.11 |
| leg_a_18p7 | G03 | tank I^2 | 2.00 | 3.94 | 3.96 | 2.60 | 4.58 | 2.40 | 1.78 | 1.31 | 0.11 | 2.64 | 0.46 | 0.45 | 3.32 | 3.90 |
| leg_b_18p7 | G03 | tank I^2 | 0.38 | 0.80 | 0.80 | 0.22 | 0.95 | 0.30 | 0.41 | 0.28 | 0.01 | 0.22 | 0.09 | 0.06 | 0.78 | 1.07 |
| res_a | G04 | tank I^2 | 0.04 | 0.05 | 0.05 | 0.11 | 0.06 | 0.09 | 0.03 | 0.02 | 0.41 | 0.11 | 0.01 | 0.02 | 0.05 | 0.05 |
| sw_a | G03 | tank I^2 | 0.89 | 1.17 | 1.17 | 2.68 | 1.19 | 1.90 | 0.63 | 0.52 | 1.25 | 2.67 | 0.20 | 0.45 | 1.03 | 1.04 |
| sw_a_low | G03 | tank I^2 | 2.52 | 3.70 | 3.71 | 7.92 | 3.88 | 4.70 | 1.89 | 1.52 | 1.52 | 8.10 | 0.57 | 0.99 | 3.21 | 3.30 |
| sw_b_high | G03 | tank I^2 | 6.51 | 6.72 | 6.71 | 5.73 | 6.49 | 6.25 | 7.27 | 6.34 | 1.18 | 5.59 | 1.94 | 1.34 | 6.90 | 6.64 |
| sw_b_low | G03 | tank I^2 | 5.20 | 5.84 | 5.84 | 5.41 | 5.68 | 5.73 | 4.92 | 3.83 | 1.17 | 5.28 | 1.30 | 1.21 | 5.86 | 5.68 |
| part R5 | G08 | tank I^2 | 4.23 | 8.74 | 8.70 | 2.18 | 8.59 | 3.08 | 4.20 | 2.91 | 0.11 | 2.14 | 0.98 | 0.64 | 11.47 | 21.85 |
| part R_on | G05 | frequency/charge-set (60 kHz window top, deck Q) | 5.16 | 13.75 | 13.95 | 19.26 | 13.44 | 3.99 | 19.60 | 5.83 | 0.20 | 25.80 | 1.68 | 0.85 | 7.21 | 7.20 |
| part R_off | G05 | frequency/charge-set (60 kHz window top, deck Q) | 1.48 | 1.84 | 1.84 | 1.31 | 1.77 | 1.36 | 1.71 | 1.45 | 0.09 | 1.28 | 0.44 | 0.29 | 2.07 | 1.89 |
| part bank | G04 | tank I^2 | 0.07 | 0.09 | 0.09 | 0.18 | 0.09 | 0.15 | 0.05 | 0.04 | 0.37 | 0.18 | 0.02 | 0.04 | 0.08 | 0.08 |
| part C5_C6 | G02 | tank I^2 | 0.02 | 0.03 | 0.03 | 0.06 | 0.03 | 0.04 | 0.01 | 0.01 | 0.06 | 0.05 | 0.00 | 0.01 | 0.02 | 0.02 |
| part HF_film | G03 | fixed estimate | 4.70 | 1.11 | 1.11 | 0.87 | 1.05 | 4.46 | 1.11 | 4.75 | 0.08 | 0.84 | 0.49 | 0.29 | 1.17 | 1.10 |
| part RECOM | G06 | frequency/charge-set (60 kHz window top, deck Q) | 4.88 | 3.10 | 3.09 | 1.91 | 2.90 | 3.44 | 3.61 | 5.89 | 0.17 | 1.85 | 57.16 | 55.57 | 3.33 | 3.13 |
| part U26 | G06 | frequency/charge-set (60 kHz window top, deck Q) | 0.17 | 0.21 | 0.21 | 0.43 | 0.22 | 0.37 | 0.12 | 0.10 | 37.67 | 0.42 | 0.04 | 0.11 | 0.19 | 0.19 |
| part small_LDO | G07/G08 | fixed estimate | 0.13 | 0.11 | 0.11 | 0.17 | 0.11 | 0.17 | 0.09 | 0.12 | 2.26 | 0.16 | 0.59 | 0.58 | 0.11 | 0.11 |
| part PS2 | G06 | frequency/charge-set (60 kHz window top, deck Q) | 0.12 | 0.16 | 0.16 | 0.33 | 0.16 | 0.26 | 0.09 | 0.07 | 0.29 | 0.33 | 0.03 | 0.07 | 0.14 | 0.14 |
| part L1 | G01 | line (I_line 13.5 A, fixed) | 0.05 | 0.06 | 0.06 | 0.12 | 0.06 | 0.10 | 0.03 | 0.03 | 0.12 | 0.12 | 0.01 | 0.03 | 0.05 | 0.05 |
| part drivers | G05 | frequency/charge-set (60 kHz window top, deck Q) | 0.60 | 0.43 | 0.43 | 0.37 | 0.41 | 0.59 | 0.38 | 0.46 | 0.08 | 0.36 | 0.31 | 0.34 | 0.45 | 0.42 |
| part R39 | G09 | tank I^2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 |
| part rest | G04/G09 | fixed estimate | 0.01 | 0.01 | 0.01 | 0.03 | 0.01 | 0.02 | 0.01 | 0.01 | 0.03 | 0.03 | 0.00 | 0.01 | 0.01 | 0.01 |
| mesh_corr | - | - | 2.20 | 7.77 | 7.91 | 11.87 | 5.25 | 1.70 | 9.39 | 1.54 | 11.20 | 9.14 | 3.38 | 2.86 | 3.98 | 2.80 |
| **sum = est** | | | **115.96** | **135.83** | **136.11** | **135.96** | **132.57** | **112.16** | **133.74** | **111.19** | **115.63** | **139.62** | **130.58** | **124.74** | **130.89** | **137.96** |

## c18_h10: K at the row by kind of change

| | C40 body | R10 terminal derating | C41 body | R20 terminal derating | C38 body | laminate 1 mm block | U26 Tj | R12 terminal derating | laminate FET row | U42 Tj |
|---|---|---|---|---|---|---|---|---|---|---|
| bay_air | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 |
| part heat, frequency/charge-set (60 kHz window top, deck Q) | 12.4 | 23.6 | 13.8 | 25.5 | 10.0 | 19.5 | 38.5 | 19.7 | 19.0 | 59.7 |
| copper loss, tank I^2 | 18.1 | 20.6 | 14.6 | 16.7 | 19.2 | 21.2 | 4.9 | 21.2 | 21.1 | 4.8 |
| FET-case tie (sink) | 8.1 | 8.9 | 8.9 | 10.7 | 7.0 | 9.4 | 0.4 | 9.4 | 9.6 | 2.6 |
| mesh_corr | 1.4 | 11.9 | 1.0 | 9.3 | 0.9 | 6.7 | 11.4 | 6.9 | 4.4 | 3.7 |
| part heat, tank I^2 | 2.9 | 1.6 | 2.0 | 2.9 | 2.2 | 5.9 | 0.4 | 5.9 | 5.8 | 0.7 |
| part heat, fixed estimate | 4.8 | 1.1 | 4.9 | 1.2 | 4.7 | 1.2 | 2.4 | 1.2 | 1.2 | 1.1 |
| part heat, line (I_line 13.5 A, fixed) | 0.0 | 0.1 | 0.0 | 0.0 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.0 |
| copper loss, line (I_line 13.5 A, fixed) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## c18_h10: K at the row by group (G01-G10)

| | C40 body | R10 terminal derating | C41 body | R20 terminal derating | C38 body | laminate 1 mm block | U26 Tj | R12 terminal derating | laminate FET row | U42 Tj |
|---|---|---|---|---|---|---|---|---|---|---|
| bay_air | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 |
| G03 | 19.1 | 19.4 | 17.1 | 15.0 | 20.6 | 18.0 | 3.7 | 18.0 | 18.3 | 4.5 |
| G06 | 5.2 | 2.7 | 6.1 | 3.8 | 4.1 | 3.5 | 38.1 | 3.5 | 3.3 | 57.2 |
| G05 | 7.2 | 20.9 | 7.7 | 21.7 | 5.9 | 16.0 | 0.4 | 16.2 | 15.7 | 2.4 |
| G03 (sink tie) | 8.1 | 8.9 | 8.9 | 10.7 | 7.0 | 9.4 | 0.4 | 9.4 | 9.6 | 2.6 |
| mesh_corr | 1.4 | 11.9 | 1.0 | 9.3 | 0.9 | 6.7 | 11.4 | 6.9 | 4.4 | 3.7 |
| G08 | 6.5 | 3.4 | 4.2 | 5.6 | 5.1 | 10.2 | 0.2 | 10.1 | 9.5 | 1.5 |
| G07/G08 | 0.1 | 0.2 | 0.1 | 0.1 | 0.2 | 0.1 | 2.3 | 0.1 | 0.1 | 0.6 |
| G04 | 0.1 | 0.2 | 0.0 | 0.1 | 0.2 | 0.1 | 1.3 | 0.1 | 0.1 | 0.0 |
| G01 | 0.1 | 0.1 | 0.0 | 0.0 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.0 |
| G02 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| G04/G09 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| G09 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## c22_h10: K at the row by kind of change

| | C40 body | laminate 1 mm block | R12 terminal derating | R10 terminal derating | laminate FET row | C38 body | R20 terminal derating | C41 body | U26 Tj | U42 Tj |
|---|---|---|---|---|---|---|---|---|---|---|
| bay_air | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 |
| copper loss, tank I^2 | 27.0 | 31.7 | 31.7 | 30.8 | 31.4 | 28.7 | 25.0 | 21.9 | 7.3 | 7.2 |
| part heat, frequency/charge-set (60 kHz window top, deck Q) | 12.4 | 19.5 | 19.7 | 23.6 | 18.9 | 10.0 | 25.5 | 13.8 | 38.5 | 59.7 |
| FET-case tie (sink) | 10.1 | 11.7 | 11.7 | 11.1 | 12.0 | 8.7 | 13.4 | 11.1 | 0.5 | 3.3 |
| mesh_corr | 2.2 | 7.8 | 7.9 | 11.9 | 5.3 | 1.7 | 9.4 | 1.5 | 11.2 | 3.4 |
| part heat, tank I^2 | 4.3 | 8.9 | 8.8 | 2.4 | 8.7 | 3.3 | 4.3 | 3.0 | 0.6 | 1.0 |
| part heat, fixed estimate | 4.8 | 1.2 | 1.2 | 1.1 | 1.2 | 4.7 | 1.2 | 4.9 | 2.4 | 1.1 |
| part heat, line (I_line 13.5 A, fixed) | 0.0 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.0 | 0.0 | 0.1 | 0.0 |
| copper loss, line (I_line 13.5 A, fixed) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## c22_h10: K at the row by group (G01-G10)

| | C40 body | laminate 1 mm block | R12 terminal derating | R10 terminal derating | laminate FET row | C38 body | R20 terminal derating | C41 body | U26 Tj | U42 Tj |
|---|---|---|---|---|---|---|---|---|---|---|
| bay_air | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 |
| G03 | 26.1 | 26.3 | 26.3 | 28.5 | 26.8 | 28.6 | 21.8 | 23.2 | 5.5 | 6.5 |
| G06 | 5.2 | 3.5 | 3.5 | 2.7 | 3.3 | 4.1 | 3.8 | 6.1 | 38.1 | 57.2 |
| G05 | 7.2 | 16.0 | 16.2 | 20.9 | 15.6 | 5.9 | 21.7 | 7.7 | 0.4 | 2.4 |
| G03 (sink tie) | 10.1 | 11.7 | 11.7 | 11.1 | 12.0 | 8.7 | 13.4 | 11.1 | 0.5 | 3.3 |
| G08 | 9.8 | 15.2 | 15.1 | 5.1 | 14.3 | 7.6 | 8.4 | 6.3 | 0.4 | 2.2 |
| mesh_corr | 2.2 | 7.8 | 7.9 | 11.9 | 5.3 | 1.7 | 9.4 | 1.5 | 11.2 | 3.4 |
| G07/G08 | 0.1 | 0.1 | 0.1 | 0.2 | 0.1 | 0.2 | 0.1 | 0.1 | 2.3 | 0.6 |
| G04 | 0.1 | 0.2 | 0.2 | 0.3 | 0.2 | 0.3 | 0.1 | 0.1 | 2.0 | 0.0 |
| G01 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.0 | 0.0 | 0.1 | 0.0 |
| G02 | 0.0 | 0.0 | 0.0 | 0.1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1 | 0.0 |
| G04/G09 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| G09 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Ceilings (synthesized gate case, every gated row)

- bay61: 18.44 A (C40: MKP Top,max 110 C (TDK B3265* June 2026 p.35))
- bay55: 20.04 A (C40: MKP Top,max 110 C (TDK B3265* June 2026 p.35))
- bay61 I_trip^2 method (c22/c28 synthesized at bay 61; ceilings.py): 18.44 A (C40 body)

## Levers: one term cut 10 %, c18 / bay 61

| term | kind | group | scales | W at c18 | dK C40 | dK R10 term. | dK lam. block | K/W at C40 | K/W at R10 | ceiling bay 61 (gain) | binding after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| part R_on | part heat | G05 | frequency/charge-set (60 kHz window top, deck Q) | 0.868 | 0.56 | 3.18 | 1.86 | 5.9 | 22.2 | 18.65 (+0.21) | C40 body |
| sw_b_high | copper loss in net sw_b | G03 | tank I^2 | 1.168 | 0.47 | 0.41 | 0.51 | 3.7 | 3.3 | 18.63 (+0.19) | C40 body |
| part HF_film | part heat | G03 | fixed estimate | 0.200 | 0.50 | 0.09 | 0.14 | 23.5 | 4.3 | 18.63 (+0.19) | C40 body |
| sw_b_low | copper loss in net sw_b | G03 | tank I^2 | 1.140 | 0.37 | 0.38 | 0.44 | 3.1 | 3.2 | 18.59 (+0.15) | C40 body |
| part RECOM | part heat | G06 | frequency/charge-set (60 kHz window top, deck Q) | 2.058 | 0.39 | 0.12 | 0.28 | 2.4 | 0.9 | 18.58 (+0.14) | C40 body |
| part R5 | part heat | G08 | tank I^2 | 0.357 | 0.31 | 0.15 | 0.70 | 7.9 | 4.1 | 18.56 (+0.12) | C40 body |
| sw_a_low | copper loss in net sw_a | G03 | tank I^2 | 1.137 | 0.17 | 0.50 | 0.22 | 1.5 | 4.7 | 18.51 (+0.07) | C40 body |
| leg_a_18p7 | copper loss in net leg_ret | G03 | tank I^2 | 0.249 | 0.13 | 0.19 | 0.17 | 5.4 | 7.0 | 18.49 (+0.05) | C40 body |
| sw_a | copper loss in net sw_a | G03 | tank I^2 | 0.670 | 0.06 | 0.18 | 0.08 | 0.9 | 2.7 | 18.46 (+0.02) | C40 body |

## Scenarios (stated cuts), ceilings

| change | ceiling bay 61 (gain) | binding | ceiling bay 55 (gain) | binding |
|---|---|---|---|---|
| R_on 0.217 -> 0.17 W (bench IR at the simulated value, DECISIONS 56) | 18.89 (+0.45) | C40 body | 20.46 (+0.42) | C40 body |
| sw_b copper -20 % (both states) | 19.14 (+0.70) | C40 body | 20.81 (+0.77) | C40 body |
| sw_a copper -20 % (both states) | 18.63 (+0.19) | C40 body | 20.25 (+0.21) | C40 body |
| hv_ret copper -20 % (hv_mixed a/b) | 18.78 (+0.34) | C40 body | 20.41 (+0.37) | C40 body |
| leg_ret copper -20 % (leg a/b) | 18.56 (+0.12) | C40 body | 20.18 (+0.14) | C40 body |
| bus_p copper -20 % (bus_mixed q2/q5) | 18.67 (+0.23) | C40 body | 20.3 (+0.26) | C40 body |
| all tank copper -20 % (every tank-scaled A4 field) | 20.19 (+1.75) | C40 body | 21.94 (+1.90) | C40 body |
| HF film self-heat 0 (C38-C41 rows 0.05 -> 0 W) | 19.47 (+1.03) | R10 terminal derating | 20.9 (+0.86) | laminate 1 mm block |
| RECOM U41/U42 -20 % | 18.73 (+0.29) | C40 body | 20.31 (+0.27) | C40 body |
| U26 -20 % | 18.45 (+0.01) | C40 body | 20.05 (+0.01) | C40 body |
| drivers U1/U2 -20 % | 18.48 (+0.04) | C40 body | 20.09 (+0.05) | C40 body |
| R_off -20 % | 18.56 (+0.12) | C40 body | 20.16 (+0.12) | C40 body |
| bank ESR -20 % | 18.45 (+0.01) | C40 body | 20.05 (+0.01) | C40 body |
| R5 0.5 mOhm (row x0.5) | 19.07 (+0.63) | C40 body | 20.73 (+0.69) | C40 body |
| sw_b copper -10 % (both states) | 18.78 (+0.34) | C40 body | 20.42 (+0.38) | C40 body |
| HF film self-heat halved (0.05 -> 0.025 W each) | 19.31 (+0.87) | R10 terminal derating | 20.73 (+0.69) | laminate 1 mm block |
| fan sink setpoint 88.6 -> 83.6 C (firmware FAN_SINK_SETPOINT_C) | 18.91 (+0.47) | C40 body | 20.48 (+0.44) | C40 body |
| fan sink setpoint 88.6 -> 78.6 C | 19.36 (+0.92) | C40 body | 20.9 (+0.86) | C40 body |
| R_on 0.17 W + sw_b -20 % | 19.61 (+1.17) | C40 body | 21.24 (+1.20) | C40 body |

## Per-row ceilings (each gated row alone; A)

| row | bay 61 | bay 55 |
|---|---|---|
| C40 body | 18.44 | 20.05 |
| R10 terminal derating | 19.14 | 20.71 |
| laminate 1 mm block | 19.39 | 20.56 |
| C41 body | 19.72 | 21.53 |
| C38 body | 19.78 | 21.32 |
| R12 terminal derating | 19.82 | 20.97 |
| R20 terminal derating | 19.85 | 21.36 |
| laminate FET row | 20.24 | 21.35 |
| R18 terminal derating | 20.52 | 22.22 |
| R58 terminal derating | 21.55 | 22.63 |
| C39 body | 21.79 | 23.39 |
| R54 terminal derating | 23.23 | 24.4 |
| R12 element | 24.29 | 25.21 |
| R57 terminal derating | 24.35 | 25.66 |
| R10 element | 25.18 | 26.35 |
| R5 terminal derating | 25.4 | 26.03 |
| R20 element | 25.89 | 27.05 |
| R53 terminal derating | 26.11 | 27.3 |
| U26 Tj | 26.55 | 32.99 |
| R5 element | 26.7 | 27.35 |
| R58 element | 27.54 | 28.43 |
| R18 element | 27.79 | 29.1 |
| R54 element | 29.39 | 30.33 |
| R53 element | 31.74 | 32.73 |
| R57 element | 31.77 | 32.79 |
| U42 Tj | 36.57 | 40.0 |
| U41 Tj | 40.0 | 40.0 |

## Bay sensitivity (c18)

- C40 body: {"dest_dbay_K_per_K": 0.7470475903428735}
- R10 terminal derating: {"dest_dbay_K_per_K": 0.7369576543569565}
- C41 body: {"dest_dbay_K_per_K": 0.7241648199727422}
- R20 terminal derating: {"dest_dbay_K_per_K": 0.6784903705119945}
- laminate 1 mm block: {"dest_dbay_K_per_K": 0.7383088674396276}
- laminate FET row: {"dest_dbay_K_per_K": 0.7064971104264259}
- U26 Tj: {"dest_dbay_K_per_K": 0.9894910800394996}
- U42 Tj: {"dest_dbay_K_per_K": 0.9327934138472074}
- ceiling_A_per_K_bay (61 -> 55): 0.26666666666666633
- t_case_c18_C: {"Q2": 92.86, "Q5": 92.86, "Q3": 92.91, "Q6": 92.91}
- t_case_c22_C: {"Q2": 94.68, "Q5": 94.68, "Q3": 94.72, "Q6": 94.72}

## Levers at c22 / bay 55: K gained per 10 % cut of one term

| term | W at c22 | C40 body | laminate 1 mm block | R12 terminal derating | R10 terminal derating | laminate FET row | C38 body |
|---|---|---|---|---|---|---|---|
| sw_b_high | 1.745 | 0.71 | 0.77 | 0.76 | 0.67 | 0.68 | 0.67 |
| part R_on | 0.868 | 0.56 | 2.22 | 1.94 | 3.28 | 1.73 | 0.43 |
| sw_b_low | 1.704 | 0.56 | 0.65 | 0.65 | 0.63 | 0.59 | 0.62 |
| part HF_film | 0.200 | 0.50 | 0.14 | 0.14 | 0.11 | 0.11 | 0.47 |
| part R5 | 0.534 | 0.46 | 1.04 | 1.00 | 0.23 | 0.96 | 0.33 |
| part RECOM | 2.058 | 0.39 | 0.28 | 0.27 | 0.15 | 0.20 | 0.20 |
| hv_mixed_a | 0.413 | 0.38 | 0.50 | 0.49 | 0.22 | 0.33 | 0.32 |
| bus_mixed_q5 | 0.526 | 0.38 | 0.28 | 0.28 | 0.14 | 0.23 | 0.18 |
| sw_a_low | 1.698 | 0.26 | 0.33 | 0.34 | 0.63 | 0.41 | 0.51 |
| hv_mixed_b | 0.264 | 0.25 | 0.38 | 0.37 | 0.12 | 0.23 | 0.17 |
| leg_a_18p7 | 0.372 | 0.20 | 0.26 | 0.27 | 0.23 | 0.52 | 0.26 |
| sw_a | 1.001 | 0.09 | 0.11 | 0.12 | 0.29 | 0.13 | 0.20 |

## Outside the model: copper TCR, first order (c18 / bay 61)

- heat-weighted copper temperature and loss scale per field: sw_a 90.4 C x1.28; sw_a_low 95.9 C x1.30; sw_b_high 98.0 C x1.31; sw_b_low 95.8 C x1.30; res_a 82.9 C x1.25; coil_feed 86.0 C x1.26; leg_a_18p7 109.2 C x1.35; leg_b_18p7 112.3 C x1.36; hv_mixed_a 104.4 C x1.33; hv_mixed_b 106.3 C x1.34; bus_mixed_q2 99.1 C x1.31; bus_mixed_q5 102.1 C x1.32
- added K at the row: C40 body +6.1; R10 terminal derating +6.5; laminate 1 mm block +7.2; C41 body +4.9; R20 terminal derating +5.4
- ceiling bay 61: 16.42 A (-2.02), C40 body

## Tank copper deposited within 5 mm of the binding rows (W, c18, by layer)

- **C40 body** at [31.7, 28.2] (junction): sw_b_high B.C 0.007; sw_b_low B.C 0.007; hv_mixed_a In1 0.012; hv_mixed_b In1 0.006; bus_mixed_q5 In2 0.008
- **R10 terminal derating** at [64.12, 15.38] (F.Cu): sw_a_low B.C 0.037; sw_b_high B.C 0.018; sw_b_low B.C 0.018; bus_mixed_q2 In2 0.014
- **laminate 1 mm block** at [45.5, 15.5] (F.Cu): sw_b_high B.C 0.070; sw_b_low B.C 0.070; leg_a_18p7 In1 0.030; bus_mixed_q5 In2 0.010
