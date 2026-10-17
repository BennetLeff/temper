# B3 hot spots against ratings (s32, body-level model)


## c28_h10: 28 A Kconfig ceiling (29.4 A trip), still-air board bay: REALISTIC if 28 A is commissioned

| ref | rating | quantity | est C (50 C bay) | spread K | limit C | margin @50 | @55 | @61 | @78 | verdict @55 | source verified |
|---|---|---|---|---|---|---|---|---|---|---|---|
| board | laminate KB-6164 MOT / RTI elec 130 C | 1 mm-block copper peak | 180.6 | 6.0 | 130.0 | -50.6 | -55.6 | -61.6 | -78.6 | VIOLATION | yes |
| FET-row copper | laminate MOT 130 C | FET-row copper max cell (0.25 mm) | 170.9 | 1.1 | 130.0 | -40.9 | -45.9 | -51.9 | -68.9 | VIOLATION | yes |
| C40 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 146.2 | 1.9 | 110.0 | -36.2 | -41.2 | -47.2 | -64.2 | VIOLATION | limit yes, package path ASSUMED |
| R5 | terminal derating at 0.864 W with the 20 % power margin (G6 rule) | terminal (pad max cell) | 184.4 | 7.4 | 148.4 | -36.0 | -41.0 | -47.0 | -64.0 | VIOLATION | yes |
| C38 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 139.8 | 0.8 | 110.0 | -29.8 | -34.8 | -40.8 | -57.8 | VIOLATION | limit yes, package path ASSUMED |
| R5 | element 170 operating max | junction / element / body node | 196.6 | 6.8 | 170.0 | -26.6 | -31.6 | -37.6 | -54.6 | VIOLATION | yes |
| C41 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 135.3 | 0.8 | 110.0 | -25.3 | -30.3 | -36.3 | -53.3 | VIOLATION | limit yes, package path ASSUMED |
| C39 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 130.9 | 2.4 | 110.0 | -20.9 | -25.9 | -31.9 | -48.9 | VIOLATION | limit yes, package path ASSUMED |
| R12 | 1206 155 (unverified) | junction / element / body node | 161.0 | 1.6 | 155.0 | -6.0 | -11.0 | -17.0 | -34.0 | VIOLATION | limit yes, package path ASSUMED |
| C21 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 111.9 | 0.4 | 110.0 | -1.9 | -6.9 | -12.9 | -29.9 | VIOLATION | limit yes, package path ASSUMED |
| R58 | 1206 155 (unverified) | junction / element / body node | 155.6 | 4.4 | 155.0 | -0.6 | -5.6 | -11.6 | -28.6 | VIOLATION | limit yes, package path ASSUMED |
| C22 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 109.7 | 0.4 | 110.0 | 0.3 | -4.7 | -10.7 | -27.7 | VIOLATION | limit yes, package path ASSUMED |
| C23 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 107.6 | 0.5 | 110.0 | 2.4 | -2.6 | -8.6 | -25.6 | VIOLATION | limit yes, package path ASSUMED |
| R20 | 1206 155 (unverified) | junction / element / body node | 151.8 | 2.6 | 155.0 | 3.2 | -1.8 | -7.8 | -24.8 | EXCEEDS | limit yes, package path ASSUMED |
| C151 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 105.8 | 0.5 | 110.0 | 4.2 | -0.8 | -6.8 | -23.8 | VIOLATION | limit yes, package path ASSUMED |
| C152 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 104.9 | 0.5 | 110.0 | 5.1 | 0.1 | -5.9 | -22.9 | THIN | limit yes, package path ASSUMED |
| PS1 | IRM-20 ambient derating at 4.83 W | local air allowed | - | - | 78.1 | 28.1 | 23.1 | 17.1 | 0.1 | OK (bay air, not board) | yes |
| PS2 | IRM-20 ambient derating at 9.59 W | local air allowed | - | - | 70.2 | 20.2 | 15.2 | 9.2 | -7.8 | OK (bay air, not board) | yes |

## c22_h10: 22 A default ceiling (23.1 A trip), still-air board bay: REALISTIC default

| ref | rating | quantity | est C (50 C bay) | spread K | limit C | margin @50 | @55 | @61 | @78 | verdict @55 | source verified |
|---|---|---|---|---|---|---|---|---|---|---|---|
| board | laminate KB-6164 MOT / RTI elec 130 C | 1 mm-block copper peak | 137.1 | 6.0 | 130.0 | -7.1 | -12.1 | -18.1 | -35.1 | VIOLATION | yes |
| C40 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 116.3 | 1.9 | 110.0 | -6.3 | -11.3 | -17.3 | -34.3 | VIOLATION | limit yes, package path ASSUMED |
| C38 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 110.6 | 0.5 | 110.0 | -0.6 | -5.6 | -11.6 | -28.6 | VIOLATION | limit yes, package path ASSUMED |
| C41 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 109.5 | 0.5 | 110.0 | 0.5 | -4.5 | -10.5 | -27.5 | VIOLATION | limit yes, package path ASSUMED |
| FET-row copper | laminate MOT 130 C | FET-row copper max cell (0.25 mm) | 127.9 | 0.6 | 130.0 | 2.1 | -2.9 | -8.9 | -25.9 | VIOLATION | yes |
| C39 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 105.2 | 2.4 | 110.0 | 4.8 | -0.2 | -6.2 | -23.2 | EXCEEDS | limit yes, package path ASSUMED |
| U26 | TJ 125 | junction / element / body node | 111.0 | 9.5 | 125.0 | 14.0 | 9.0 | 3.0 | -14.0 | THIN | yes |
| R5 | terminal derating at 0.534 W with the 20 % power margin (G6 rule) | terminal (pad max cell) | 140.8 | 7.4 | 156.7 | 15.9 | 10.9 | 4.9 | -12.1 | OK | yes |
| U42 | Tj abs max 150 (OTP 160+/-10) | junction / element / body node | 130.6 | 2.4 | 150.0 | 19.4 | 14.4 | 8.4 | -8.6 | OK | yes |
| C21 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 90.2 | 0.2 | 110.0 | 19.8 | 14.8 | 8.8 | -8.2 | OK | limit yes, package path ASSUMED |
| C22 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 88.5 | 0.3 | 110.0 | 21.5 | 16.5 | 10.5 | -6.5 | OK | limit yes, package path ASSUMED |
| R5 | element 170 operating max | junction / element / body node | 148.3 | 6.8 | 170.0 | 21.7 | 16.7 | 10.7 | -6.3 | OK | yes |
| C23 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 86.8 | 0.3 | 110.0 | 23.2 | 18.2 | 12.2 | -4.8 | OK | limit yes, package path ASSUMED |
| U41 | Tj abs max 150 (OTP 160+/-10) | junction / element / body node | 126.8 | 3.2 | 150.0 | 23.2 | 18.2 | 12.2 | -4.8 | OK | yes |
| C151 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 85.5 | 0.3 | 110.0 | 24.5 | 19.5 | 13.5 | -3.5 | OK | limit yes, package path ASSUMED |
| C152 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 84.8 | 0.3 | 110.0 | 25.2 | 20.2 | 14.2 | -2.8 | OK | limit yes, package path ASSUMED |
| PS1 | IRM-20 ambient derating at 4.83 W | local air allowed | - | - | 78.1 | 28.1 | 23.1 | 17.1 | 0.1 | OK (bay air, not board) | yes |
| PS2 | IRM-20 ambient derating at 9.59 W | local air allowed | - | - | 70.2 | 20.2 | 15.2 | 9.2 | -7.8 | OK (bay air, not board) | yes |

## c28_h25: 28 A with 25 W/m2K forced air over both board faces: NO record provides that airflow

| ref | rating | quantity | est C (50 C bay) | spread K | limit C | margin @50 | @55 | @61 | @78 | verdict @55 | source verified |
|---|---|---|---|---|---|---|---|---|---|---|---|
| board | laminate KB-6164 MOT / RTI elec 130 C | 1 mm-block copper peak | 127.2 | 5.3 | 130.0 | 2.8 | -2.2 | -8.2 | -25.2 | EXCEEDS | yes |
| FET-row copper | laminate MOT 130 C | FET-row copper max cell (0.25 mm) | 117.8 | 0.7 | 130.0 | 12.2 | 7.2 | 1.2 | -15.8 | OK | yes |
| C40 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 96.8 | 1.3 | 110.0 | 13.2 | 8.2 | 2.2 | -14.8 | OK | limit yes, package path ASSUMED |
| C38 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 93.1 | 0.4 | 110.0 | 16.9 | 11.9 | 5.9 | -11.1 | OK | limit yes, package path ASSUMED |
| C21 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 89.1 | 0.3 | 110.0 | 20.9 | 15.9 | 9.9 | -7.1 | OK | limit yes, package path ASSUMED |
| C39 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 89.1 | 1.3 | 110.0 | 20.9 | 15.9 | 9.9 | -7.1 | OK | limit yes, package path ASSUMED |
| R5 | terminal derating at 0.864 W with the 20 % power margin (G6 rule) | terminal (pad max cell) | 126.6 | 2.2 | 148.4 | 21.8 | 16.8 | 10.8 | -6.2 | OK | yes |
| C22 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 87.6 | 0.4 | 110.0 | 22.4 | 17.4 | 11.4 | -5.6 | OK | limit yes, package path ASSUMED |
| C41 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 87.6 | 0.4 | 110.0 | 22.4 | 17.4 | 11.4 | -5.6 | OK | limit yes, package path ASSUMED |
| C23 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 86.1 | 0.5 | 110.0 | 23.9 | 18.9 | 12.9 | -4.1 | OK | limit yes, package path ASSUMED |
| C152 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 85.1 | 0.5 | 110.0 | 24.9 | 19.9 | 13.9 | -3.1 | OK | limit yes, package path ASSUMED |
| C151 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 85.0 | 0.5 | 110.0 | 25.0 | 20.0 | 14.0 | -3.0 | OK | limit yes, package path ASSUMED |
| C5 | MKP Top,max 110 | junction / element / body node | 77.8 | 0.4 | 110.0 | 32.2 | 27.2 | 21.2 | 4.2 | OK | limit yes, package path ASSUMED |
| R5 | element 170 operating max | junction / element / body node | 137.5 | 2.0 | 170.0 | 32.5 | 27.5 | 21.5 | 4.5 | OK | yes |
| C6 | MKP Top,max 110 | junction / element / body node | 74.5 | 0.3 | 110.0 | 35.5 | 30.5 | 24.5 | 7.5 | OK | limit yes, package path ASSUMED |
| U26 | TJ 125 | junction / element / body node | 88.7 | 3.4 | 125.0 | 36.3 | 31.3 | 25.3 | 8.3 | OK | yes |
| PS1 | IRM-20 ambient derating at 4.83 W | local air allowed | - | - | 78.1 | 28.1 | 23.1 | 17.1 | 0.1 | OK (bay air, not board) | yes |
| PS2 | IRM-20 ambient derating at 9.59 W | local air allowed | - | - | 70.2 | 20.2 | 15.2 | 9.2 | -7.8 | OK (bay air, not board) | yes |

## der14_h10: blower-stall derate hold (14.7 A), still air: realistic transient-to-steady case

| ref | rating | quantity | est C (50 C bay) | spread K | limit C | margin @50 | @55 | @61 | @78 | verdict @55 | source verified |
|---|---|---|---|---|---|---|---|---|---|---|---|
| U26 | TJ 125 | junction / element / body node | 102.1 | 4.4 | 125.0 | 22.9 | 17.9 | 11.9 | -5.1 | OK | yes |
| C40 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 85.5 | 0.6 | 110.0 | 24.5 | 19.5 | 13.5 | -3.5 | OK | limit yes, package path ASSUMED |
| C41 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 84.7 | 0.2 | 110.0 | 25.3 | 20.3 | 14.3 | -2.7 | OK | limit yes, package path ASSUMED |
| board | laminate KB-6164 MOT / RTI elec 130 C | 1 mm-block copper peak | 102.9 | 3.4 | 130.0 | 27.1 | 22.1 | 16.1 | -0.9 | OK | yes |
| U42 | Tj abs max 150 (OTP 160+/-10) | junction / element / body node | 122.8 | 2.0 | 150.0 | 27.2 | 22.2 | 16.2 | -0.8 | OK | yes |
| C38 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 82.6 | 0.4 | 110.0 | 27.4 | 22.4 | 16.4 | -0.6 | OK | limit yes, package path ASSUMED |
| U41 | Tj abs max 150 (OTP 160+/-10) | junction / element / body node | 121.5 | 1.6 | 150.0 | 28.5 | 23.5 | 17.5 | 0.5 | OK | yes |
| C39 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 78.8 | 0.6 | 110.0 | 31.2 | 26.2 | 20.2 | 3.2 | OK | limit yes, package path ASSUMED |
| C21 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 68.9 | 0.1 | 110.0 | 41.1 | 36.1 | 30.1 | 13.1 | OK | limit yes, package path ASSUMED |
| C22 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 67.6 | 0.1 | 110.0 | 42.4 | 37.4 | 31.4 | 14.4 | OK | limit yes, package path ASSUMED |
| FET-row copper | laminate MOT 130 C | FET-row copper max cell (0.25 mm) | 87.3 | 0.2 | 130.0 | 42.7 | 37.7 | 31.7 | 14.7 | OK | yes |
| C23 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 66.6 | 0.1 | 110.0 | 43.4 | 38.4 | 32.4 | 15.4 | OK | limit yes, package path ASSUMED |
| C151 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 65.8 | 0.1 | 110.0 | 44.2 | 39.2 | 33.2 | 16.2 | OK | limit yes, package path ASSUMED |
| C5 | MKP Top,max 110 | junction / element / body node | 65.5 | 0.2 | 110.0 | 44.5 | 39.5 | 33.5 | 16.5 | OK | limit yes, package path ASSUMED |
| C152 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 65.4 | 0.1 | 110.0 | 44.6 | 39.6 | 33.6 | 16.6 | OK | limit yes, package path ASSUMED |
| L1 | climatic upper 125 | junction / element / body node | 79.8 | 0.9 | 125.0 | 45.2 | 40.2 | 34.2 | 17.2 | OK | limit yes, package path ASSUMED |
| PS1 | IRM-20 ambient derating at 4.83 W | local air allowed | - | - | 78.1 | 28.1 | 23.1 | 17.1 | 0.1 | OK (bay air, not board) | yes |
| PS2 | IRM-20 ambient derating at 9.59 W | local air allowed | - | - | 70.2 | 20.2 | 15.2 | 9.2 | -7.8 | OK (bay air, not board) | yes |

## nominal_h10: round-3 1710 W at 120 V (line 14.25 A > the 11.1 A inlet hold): NOT reachable; the scorecard's case

| ref | rating | quantity | est C (50 C bay) | spread K | limit C | margin @50 | @55 | @61 | @78 | verdict @55 | source verified |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C40 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 109.7 | 1.9 | 110.0 | 0.3 | -4.7 | -10.7 | -27.7 | VIOLATION | limit yes, package path ASSUMED |
| board | laminate KB-6164 MOT / RTI elec 130 C | 1 mm-block copper peak | 127.6 | 6.0 | 130.0 | 2.4 | -2.6 | -8.6 | -25.6 | EXCEEDS | yes |
| C38 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 104.3 | 0.4 | 110.0 | 5.7 | 0.7 | -5.3 | -22.3 | OK | limit yes, package path ASSUMED |
| C41 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 103.8 | 0.4 | 110.0 | 6.2 | 1.2 | -4.8 | -21.8 | OK | limit yes, package path ASSUMED |
| C39 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 99.6 | 2.4 | 110.0 | 10.4 | 5.4 | -0.6 | -17.6 | OK | limit yes, package path ASSUMED |
| FET-row copper | laminate MOT 130 C | FET-row copper max cell (0.25 mm) | 118.5 | 0.5 | 130.0 | 11.5 | 6.5 | 0.5 | -16.5 | OK | yes |
| U26 | TJ 125 | junction / element / body node | 109.9 | 9.5 | 125.0 | 15.1 | 10.1 | 4.1 | -12.9 | OK | yes |
| U42 | Tj abs max 150 (OTP 160+/-10) | junction / element / body node | 128.7 | 2.4 | 150.0 | 21.3 | 16.3 | 10.3 | -6.7 | OK | yes |
| C21 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 86.2 | 0.2 | 110.0 | 23.8 | 18.8 | 12.8 | -4.2 | OK | limit yes, package path ASSUMED |
| U41 | Tj abs max 150 (OTP 160+/-10) | junction / element / body node | 125.9 | 3.2 | 150.0 | 24.1 | 19.1 | 13.1 | -3.9 | OK | yes |
| C22 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 84.5 | 0.3 | 110.0 | 25.5 | 20.5 | 14.5 | -2.5 | OK | limit yes, package path ASSUMED |
| C23 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 82.8 | 0.3 | 110.0 | 27.2 | 22.2 | 16.2 | -0.8 | OK | limit yes, package path ASSUMED |
| R5 | terminal derating at 0.461 W with the 20 % power margin (G6 rule) | terminal (pad max cell) | 131.2 | 7.4 | 158.5 | 27.3 | 22.3 | 16.3 | -0.7 | OK | yes |
| L1 | climatic upper 125 | junction / element / body node | 97.0 | 0.6 | 125.0 | 28.0 | 23.0 | 17.0 | -0.0 | OK | limit yes, package path ASSUMED |
| C151 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 81.5 | 0.2 | 110.0 | 28.5 | 23.5 | 17.5 | 0.5 | OK | limit yes, package path ASSUMED |
| C152 | MKP Top,max 110 (TA + self-heating) | junction / element / body node | 80.8 | 0.2 | 110.0 | 29.2 | 24.2 | 18.2 | 1.2 | OK | limit yes, package path ASSUMED |
| PS1 | IRM-20 ambient derating at 4.83 W | local air allowed | - | - | 78.1 | 28.1 | 23.1 | 17.1 | 0.1 | OK (bay air, not board) | yes |
| PS2 | IRM-20 ambient derating at 9.59 W | local air allowed | - | - | 70.2 | 20.2 | 15.2 | 9.2 | -7.8 | OK (bay air, not board) | yes |

## Fix sensitivities (0.5 mm, delta K vs the same-mesh h10 baseline)

| case:fix | C40.tj_c | PS2.pad_mean_c | R5.pad_max_cell_c | R5.tj_c | R58.tj_c | U26.tj_c | U41.tj_c | U42.tj_c | board.fet_row_max | board.peak_1mm_block |
|---|---|---|---|---|---|---|---|---|---|---|
| c28:h15 | -25.3 | -12.0 | -27.1 | -27.3 | -26.9 | -12.0 | -13.1 | -17.6 | -27.0 | -27.1 |
| c28:h20 | -39.2 | -18.3 | -42.4 | -42.7 | -41.9 | -18.0 | -20.2 | -26.9 | -42.5 | -42.3 |
| c28:a4x0p7 | -20.4 | -5.2 | -25.1 | -24.8 | -23.4 | -4.0 | -3.0 | -6.1 | -27.7 | -25.1 |
| c28:a4x0p5 | -33.9 | -8.6 | -41.8 | -41.3 | -39.0 | -6.7 | -5.0 | -10.1 | -44.2 | -41.9 |
| c28:R5x0p5 | -4.5 | -0.1 | -13.9 | -20.7 | -8.4 | -0.1 | -0.4 | -1.2 | -4.2 | -7.0 |
| c28:modx0p5 | -2.8 | -0.1 | -2.2 | -2.1 | -2.3 | -0.1 | -31.1 | -29.5 | -1.5 | -2.2 |
| c28:ps0p5 | -0.1 | -16.0 | -0.1 | -0.1 | -0.1 | -0.2 | -0.0 | -0.0 | -0.2 | -0.1 |
| c22:h15 | -17.2 | -9.0 | -18.2 | -18.3 | -18.1 | -9.4 | -11.1 | -13.8 | -18.0 | -18.2 |
| c22:h20 | -26.6 | -13.8 | -28.4 | -28.6 | -28.2 | -14.3 | -17.3 | -21.3 | -28.2 | -28.4 |
| c22:a4x0p7 | -12.6 | -3.2 | -15.5 | -15.3 | -14.5 | -2.5 | -1.9 | -3.8 | -16.4 | -15.5 |
| c22:a4x0p5 | -21.0 | -5.4 | -25.8 | -25.5 | -24.1 | -4.2 | -3.1 | -6.3 | -26.6 | -25.8 |
| c22:R5x0p5 | -2.8 | -0.1 | -8.5 | -12.8 | -5.2 | -0.1 | -0.3 | -0.8 | -2.6 | -5.1 |
| c22:modx0p5 | -2.8 | -0.1 | -2.2 | -2.1 | -2.3 | -0.1 | -31.1 | -29.5 | -1.5 | -2.2 |
| c22:ps0p5 | -0.1 | -16.0 | -0.1 | -0.1 | -0.1 | -0.2 | -0.0 | -0.0 | -0.2 | -0.1 |

## Still-air (h 10) ceiling sweep, estimate incl. uncertainty at 50 C bay

| ceiling A | board block | FET row | R5 element | R5 terminal / limit | U42 Tj | C40 body |
|---|---|---|---|---|---|---|
| 14 | 104.9 | 87.7 | 102.7 | 99.8 / 164.6 | 122.2 | 88.0 |
| 16 | 107.1 | 95.9 | 112.2 | 108.3 / 162.9 | 124.0 | 93.9 |
| 18 | 114.4 | 105.2 | 122.9 | 118.0 / 161.1 | 125.9 | 100.6 |
| 20 | 125.2 | 116.0 | 135.0 | 128.8 / 159.0 | 128.2 | 108.0 |
| 22 | 137.1 | 127.9 | 148.3 | 140.8 / 156.7 | 130.6 | 116.3 |

Highest ceiling meeting laminate 130 C, R5 170 C and U42 150 C: {'model_50': 20, 'bay_expected_55': 18, 'bay_worst_B3only_61': 18, 'bay_stacked_78': None}

## Still-air h estimate

```
{
 "dT_50K": {
  "Ra": 235288,
  "h_conv_up": 7.5,
  "h_conv_down": 3.9,
  "h_rad_upper_bound": 9.0
 },
 "dT_80K": {
  "Ra": 313495,
  "h_conv_up": 8.4,
  "h_conv_down": 4.3,
  "h_rad_upper_bound": 10.3
 },
 "note": "convection alone is 4-9 W/m2K; radiation adds up to ~9-10 only where a face sees cool walls (most of the top face sees component bodies, the coil carrier and a 61-78 C bay). Still air therefore sits near h 10-15; h 25 needs forced flow over the board, which no enclosure record provides."
}
```

