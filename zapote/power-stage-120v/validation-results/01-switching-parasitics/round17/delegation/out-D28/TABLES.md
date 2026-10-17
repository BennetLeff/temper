# Recorded D-28 captures

All rows are recorded attempts, not interpolated operating permissions. INDETERMINATE includes aborted, unsettled, missing-refinement and failed-refinement cases. The per-transition screens below remain provisional unless `verdicts.csv` qualifies the capture. The original-startup `v…` attempts and the legacy-matrix 35 kHz anchor are separate from the native-19 complementary-startup 50 kHz phase campaign. See [METHOD.md](METHOD.md).

Power is DC tank-resistor power. The overlap column is the four-transition positive-terminal-power proxy at 50 kHz (35 kHz for the anchor), not dissipated heat or efficiency. [Definitions and sources](METHOD.md#switching-measurements-and-limits).

| Capture / raw evidence | Bus V | R Ω | Phase ° | Step ns | Transient / periodic | Tank W | Overlap proxy W | Verdict |
|---|---:|---:|---:|---:|---|---:|---:|---|
| [anchor-original-170-35k](runs/anchor-original-170-35k/result.json) | 170 | 2 | 180 | 0.5 | indeterminate / missing | — | — | INDETERMINATE |
| [anchor-original-170-35k-repeat](runs/anchor-original-170-35k-repeat/result.json) | 170 | 2 | 180 | 0.5 | unqualified_complete / complete | 889.166 | 9.627 | INDETERMINATE |
| [boundary-v170-r2-p100-s0.5](runs/boundary-v170-r2-p100-s0.5/result.json) | 170 | 2 | 100 | 0.5 | unqualified_complete / complete | 103.982 | 5.003 | INDETERMINATE |
| [boundary-v170-r2-p110-s0.5](runs/boundary-v170-r2-p110-s0.5/result.json) | 170 | 2 | 110 | 0.5 | unqualified_complete / complete | 118.976 | 5.386 | INDETERMINATE |
| [boundary-v170-r2-p125-s0.25](runs/boundary-v170-r2-p125-s0.25/result.json) | 170 | 2 | 125 | 0.25 | unqualified_complete / complete | 139.714 | 5.801 | INDETERMINATE |
| [boundary-v170-r2-p125-s0.5](runs/boundary-v170-r2-p125-s0.5/result.json) | 170 | 2 | 125 | 0.5 | unqualified_complete / complete | 139.714 | 5.780 | INDETERMINATE |
| [boundary-v170-r2-p130-s0.5](runs/boundary-v170-r2-p130-s0.5/result.json) | 170 | 2 | 130 | 0.5 | indeterminate / missing | — | — | INDETERMINATE |
| [boundary-v198-r2-p100-s0.5](runs/boundary-v198-r2-p100-s0.5/result.json) | 198 | 2 | 100 | 0.5 | unqualified_complete / complete | 141.267 | 5.550 | INDETERMINATE |
| [boundary-v198-r2-p110-s0.5](runs/boundary-v198-r2-p110-s0.5/result.json) | 198 | 2 | 110 | 0.5 | unqualified_complete / complete | 161.566 | 6.065 | INDETERMINATE |
| [complementary-v170-r100-p180-s1](runs/complementary-v170-r100-p180-s1/result.json) | 170 | 100 | 180 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v170-r100-p30-s1](runs/complementary-v170-r100-p30-s1/result.json) | 170 | 100 | 30 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v170-r100-p90-s0.5](runs/complementary-v170-r100-p90-s0.5/result.json) | 170 | 100 | 90 | 0.5 | unqualified_complete / complete | 126.413 | 57.692 | INDETERMINATE |
| [complementary-v170-r100-p90-s1](runs/complementary-v170-r100-p90-s1/result.json) | 170 | 100 | 90 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v170-r2-p0-s1](runs/complementary-v170-r2-p0-s1/result.json) | 170 | 2 | 0 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v170-r2-p120-s0.25](runs/complementary-v170-r2-p120-s0.25/result.json) | 170 | 2 | 120 | 0.25 | unqualified_complete / complete | 133.072 | 5.742 | INDETERMINATE |
| [complementary-v170-r2-p120-s0.5](runs/complementary-v170-r2-p120-s0.5/result.json) | 170 | 2 | 120 | 0.5 | unqualified_complete / complete | 133.072 | 5.721 | INDETERMINATE |
| [complementary-v170-r2-p120-s1](runs/complementary-v170-r2-p120-s1/result.json) | 170 | 2 | 120 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v170-r2-p150-s0.5](runs/complementary-v170-r2-p150-s0.5/result.json) | 170 | 2 | 150 | 0.5 | unqualified_complete / complete | 166.450 | 6.064 | INDETERMINATE |
| [complementary-v170-r2-p150-s1](runs/complementary-v170-r2-p150-s1/result.json) | 170 | 2 | 150 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v170-r2-p180-s0.5](runs/complementary-v170-r2-p180-s0.5/result.json) | 170 | 2 | 180 | 0.5 | unqualified_complete / complete | 179.220 | 9.479 | INDETERMINATE |
| [complementary-v170-r2-p180-s1](runs/complementary-v170-r2-p180-s1/result.json) | 170 | 2 | 180 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v170-r2-p30-s1](runs/complementary-v170-r2-p30-s1/result.json) | 170 | 2 | 30 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v170-r2-p60-s0.5](runs/complementary-v170-r2-p60-s0.5/result.json) | 170 | 2 | 60 | 0.5 | unqualified_complete / complete | 45.393 | 12.098 | INDETERMINATE |
| [complementary-v170-r2-p60-s1](runs/complementary-v170-r2-p60-s1/result.json) | 170 | 2 | 60 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v170-r2-p90-s0.25](runs/complementary-v170-r2-p90-s0.25/result.json) | 170 | 2 | 90 | 0.25 | unqualified_complete / complete | 88.648 | 4.709 | INDETERMINATE |
| [complementary-v170-r2-p90-s0.5](runs/complementary-v170-r2-p90-s0.5/result.json) | 170 | 2 | 90 | 0.5 | unqualified_complete / complete | 88.648 | 4.720 | INDETERMINATE |
| [complementary-v170-r2-p90-s1](runs/complementary-v170-r2-p90-s1/result.json) | 170 | 2 | 90 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v198-r100-p180-s1](runs/complementary-v198-r100-p180-s1/result.json) | 198 | 100 | 180 | 1 | unqualified_complete / not_settled | 343.932 | 57.097 | INDETERMINATE |
| [complementary-v198-r100-p30-s1](runs/complementary-v198-r100-p30-s1/result.json) | 198 | 100 | 30 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v198-r100-p90-s0.5](runs/complementary-v198-r100-p90-s0.5/result.json) | 198 | 100 | 90 | 0.5 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v198-r100-p90-s1](runs/complementary-v198-r100-p90-s1/result.json) | 198 | 100 | 90 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v198-r2-p0-s1](runs/complementary-v198-r2-p0-s1/result.json) | 198 | 2 | 0 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v198-r2-p120-s0.5](runs/complementary-v198-r2-p120-s0.5/result.json) | 198 | 2 | 120 | 0.5 | unqualified_complete / complete | 180.588 | 6.641 | INDETERMINATE |
| [complementary-v198-r2-p120-s1](runs/complementary-v198-r2-p120-s1/result.json) | 198 | 2 | 120 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v198-r2-p150-s0.5](runs/complementary-v198-r2-p150-s0.5/result.json) | 198 | 2 | 150 | 0.5 | unqualified_complete / complete | 225.840 | 7.120 | INDETERMINATE |
| [complementary-v198-r2-p150-s1](runs/complementary-v198-r2-p150-s1/result.json) | 198 | 2 | 150 | 1 | unqualified_complete / complete | 225.840 | 7.065 | INDETERMINATE |
| [complementary-v198-r2-p180-s0.5](runs/complementary-v198-r2-p180-s0.5/result.json) | 198 | 2 | 180 | 0.5 | unqualified_complete / complete | 243.128 | 12.021 | INDETERMINATE |
| [complementary-v198-r2-p180-s1](runs/complementary-v198-r2-p180-s1/result.json) | 198 | 2 | 180 | 1 | unqualified_complete / complete | 243.128 | 11.884 | INDETERMINATE |
| [complementary-v198-r2-p30-s1](runs/complementary-v198-r2-p30-s1/result.json) | 198 | 2 | 30 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v198-r2-p60-s0.5](runs/complementary-v198-r2-p60-s0.5/result.json) | 198 | 2 | 60 | 0.5 | unqualified_complete / complete | 60.916 | 8.551 | INDETERMINATE |
| [complementary-v198-r2-p60-s1](runs/complementary-v198-r2-p60-s1/result.json) | 198 | 2 | 60 | 1 | unqualified_complete / not_settled | 60.917 | 8.480 | INDETERMINATE |
| [complementary-v198-r2-p90-s0.5](runs/complementary-v198-r2-p90-s0.5/result.json) | 198 | 2 | 90 | 0.5 | indeterminate / missing | — | — | INDETERMINATE |
| [complementary-v198-r2-p90-s1](runs/complementary-v198-r2-p90-s1/result.json) | 198 | 2 | 90 | 1 | unqualified_complete / complete | 120.379 | 5.118 | INDETERMINATE |
| [v170-r2-p0-s1](runs/v170-r2-p0-s1/result.json) | 170 | 2 | 0 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [v170-r2-p120-s1](runs/v170-r2-p120-s1/result.json) | 170 | 2 | 120 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [v170-r2-p150-s1](runs/v170-r2-p150-s1/result.json) | 170 | 2 | 150 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [v170-r2-p30-s1](runs/v170-r2-p30-s1/result.json) | 170 | 2 | 30 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [v170-r2-p60-s1](runs/v170-r2-p60-s1/result.json) | 170 | 2 | 60 | 1 | indeterminate / missing | — | — | INDETERMINATE |
| [v170-r2-p90-s1](runs/v170-r2-p90-s1/result.json) | 170 | 2 | 90 | 1 | indeterminate / missing | — | — | INDETERMINATE |

## Per-transition provisional screens

Edge 0 turns on the high-side device; edge 1 turns on the low-side device. Positive current has the desired inductive polarity. CT delay is from the outgoing off command to the next appropriate current zero; an absent value does not pass the inhibit proposal. VDS peak is the maximum of both devices in the leg over the full cycle. Gate peak covers the outgoing device’s commanded-off interval, including other-leg disturbances.

| Capture / final replay | Leg, edge | Inductive A | Incoming VDS V | ZVS screen | Off gate V | <3 / <1.9 V | Full-cycle VDS V | <520 V | CT delay ns | Overlap µJ |
|---|---|---:|---:|---|---:|---|---:|---|---:|---:|
| [anchor-original-170-35k-repeat](runs/anchor-original-170-35k-repeat/replay/analysis.json) | A, 0 | 31.809 | -0.848 | True | 1.623 | True / True | 191.902 | True | 5973.4 | 71.020 |
| [anchor-original-170-35k-repeat](runs/anchor-original-170-35k-repeat/replay/analysis.json) | A, 1 | 31.808 | -0.845 | True | 1.347 | True / True | 191.902 | True | 5973.1 | 66.501 |
| [anchor-original-170-35k-repeat](runs/anchor-original-170-35k-repeat/replay/analysis.json) | B, 0 | 31.808 | -0.848 | True | 1.623 | True / True | 191.903 | True | 5973.1 | 71.019 |
| [anchor-original-170-35k-repeat](runs/anchor-original-170-35k-repeat/replay/analysis.json) | B, 1 | 31.809 | -0.845 | True | 1.347 | True / True | 191.903 | True | 5973.0 | 66.505 |
| [boundary-v170-r2-p100-s0.5](runs/boundary-v170-r2-p100-s0.5/replay/analysis.json) | A, 0 | 8.204 | 21.980 | False | 0.714 | True / True | 185.009 | True | 2763.4 | 22.899 |
| [boundary-v170-r2-p100-s0.5](runs/boundary-v170-r2-p100-s0.5/replay/analysis.json) | A, 1 | 8.205 | 21.940 | False | 0.724 | True / True | 185.009 | True | 2763.3 | 23.038 |
| [boundary-v170-r2-p100-s0.5](runs/boundary-v170-r2-p100-s0.5/replay/analysis.json) | B, 0 | 8.533 | 12.774 | False | 0.646 | True / True | 179.586 | True | 7207.8 | 27.072 |
| [boundary-v170-r2-p100-s0.5](runs/boundary-v170-r2-p100-s0.5/replay/analysis.json) | B, 1 | 8.533 | 12.767 | False | 0.650 | True / True | 179.586 | True | 7207.8 | 27.041 |
| [boundary-v170-r2-p110-s0.5](runs/boundary-v170-r2-p110-s0.5/replay/analysis.json) | A, 0 | 9.193 | 14.589 | False | 0.713 | True / True | 186.483 | True | 3002.7 | 25.162 |
| [boundary-v170-r2-p110-s0.5](runs/boundary-v170-r2-p110-s0.5/replay/analysis.json) | A, 1 | 9.192 | 14.706 | False | 0.717 | True / True | 186.483 | True | 3002.8 | 25.150 |
| [boundary-v170-r2-p110-s0.5](runs/boundary-v170-r2-p110-s0.5/replay/analysis.json) | B, 0 | 9.530 | 8.108 | True | 0.721 | True / True | 181.113 | True | 6891.7 | 28.752 |
| [boundary-v170-r2-p110-s0.5](runs/boundary-v170-r2-p110-s0.5/replay/analysis.json) | B, 1 | 9.531 | 8.150 | True | 0.728 | True / True | 181.113 | True | 6891.6 | 28.656 |
| [boundary-v170-r2-p125-s0.25](runs/boundary-v170-r2-p125-s0.25/replay/analysis.json) | A, 0 | 10.679 | 7.899 | True | 0.625 | True / True | 185.591 | True | 3377.6 | 28.269 |
| [boundary-v170-r2-p125-s0.25](runs/boundary-v170-r2-p125-s0.25/replay/analysis.json) | A, 1 | 10.679 | 7.987 | True | 0.656 | True / True | 185.591 | True | 3377.6 | 28.290 |
| [boundary-v170-r2-p125-s0.25](runs/boundary-v170-r2-p125-s0.25/replay/analysis.json) | B, 0 | 10.932 | 4.381 | True | 0.573 | True / True | 187.543 | True | 6433.2 | 29.740 |
| [boundary-v170-r2-p125-s0.25](runs/boundary-v170-r2-p125-s0.25/replay/analysis.json) | B, 1 | 10.933 | 4.356 | True | 0.570 | True / True | 187.543 | True | 6433.2 | 29.713 |
| [boundary-v170-r2-p125-s0.5](runs/boundary-v170-r2-p125-s0.5/replay/analysis.json) | A, 0 | 10.679 | 7.906 | True | 0.625 | True / True | 185.368 | True | 3377.6 | 28.246 |
| [boundary-v170-r2-p125-s0.5](runs/boundary-v170-r2-p125-s0.5/replay/analysis.json) | A, 1 | 10.679 | 7.995 | True | 0.657 | True / True | 185.368 | True | 3377.7 | 28.274 |
| [boundary-v170-r2-p125-s0.5](runs/boundary-v170-r2-p125-s0.5/replay/analysis.json) | B, 0 | 10.932 | 4.379 | True | 0.568 | True / True | 187.470 | True | 6433.2 | 29.573 |
| [boundary-v170-r2-p125-s0.5](runs/boundary-v170-r2-p125-s0.5/replay/analysis.json) | B, 1 | 10.933 | 4.354 | True | 0.572 | True / True | 187.470 | True | 6433.2 | 29.511 |
| [boundary-v198-r2-p100-s0.5](runs/boundary-v198-r2-p100-s0.5/replay/analysis.json) | A, 0 | 9.545 | 14.983 | False | 0.659 | True / True | 213.367 | True | 2741.4 | 25.210 |
| [boundary-v198-r2-p100-s0.5](runs/boundary-v198-r2-p100-s0.5/replay/analysis.json) | A, 1 | 9.545 | 14.993 | False | 0.679 | True / True | 213.367 | True | 2741.4 | 25.184 |
| [boundary-v198-r2-p100-s0.5](runs/boundary-v198-r2-p100-s0.5/replay/analysis.json) | B, 0 | 10.009 | 7.161 | True | 0.690 | True / True | 209.453 | True | 7185.8 | 30.379 |
| [boundary-v198-r2-p100-s0.5](runs/boundary-v198-r2-p100-s0.5/replay/analysis.json) | B, 1 | 10.010 | 7.119 | True | 0.696 | True / True | 209.453 | True | 7185.9 | 30.224 |
| [boundary-v198-r2-p110-s0.5](runs/boundary-v198-r2-p110-s0.5/replay/analysis.json) | A, 0 | 10.697 | 9.075 | True | 0.706 | True / True | 218.050 | True | 2984.2 | 27.609 |
| [boundary-v198-r2-p110-s0.5](runs/boundary-v198-r2-p110-s0.5/replay/analysis.json) | A, 1 | 10.697 | 9.270 | True | 0.715 | True / True | 218.050 | True | 2984.3 | 27.664 |
| [boundary-v198-r2-p110-s0.5](runs/boundary-v198-r2-p110-s0.5/replay/analysis.json) | B, 0 | 11.159 | 3.997 | True | 0.623 | True / True | 209.897 | True | 6873.2 | 33.037 |
| [boundary-v198-r2-p110-s0.5](runs/boundary-v198-r2-p110-s0.5/replay/analysis.json) | B, 1 | 11.159 | 4.030 | True | 0.583 | True / True | 209.897 | True | 6873.1 | 32.999 |
| [complementary-v170-r100-p90-s0.5](runs/complementary-v170-r100-p90-s0.5/replay/analysis.json) | A, 0 | -0.075 | 169.696 | False | 3.656 | False / False | 369.784 | True | — | 341.919 |
| [complementary-v170-r100-p90-s0.5](runs/complementary-v170-r100-p90-s0.5/replay/analysis.json) | A, 1 | -0.075 | 169.690 | False | 3.422 | False / False | 369.784 | True | — | 340.613 |
| [complementary-v170-r100-p90-s0.5](runs/complementary-v170-r100-p90-s0.5/replay/analysis.json) | B, 0 | 1.673 | 165.473 | False | 2.121 | True / False | 335.113 | True | 2697.8 | 236.374 |
| [complementary-v170-r100-p90-s0.5](runs/complementary-v170-r100-p90-s0.5/replay/analysis.json) | B, 1 | 1.673 | 165.491 | False | 1.969 | True / False | 335.113 | True | 2700.1 | 234.928 |
| [complementary-v170-r2-p120-s0.25](runs/complementary-v170-r2-p120-s0.25/replay/analysis.json) | A, 0 | 10.183 | 10.339 | False | 0.726 | True / True | 186.276 | True | 3251.3 | 27.994 |
| [complementary-v170-r2-p120-s0.25](runs/complementary-v170-r2-p120-s0.25/replay/analysis.json) | A, 1 | 10.183 | 10.428 | False | 0.721 | True / True | 186.276 | True | 3251.4 | 28.024 |
| [complementary-v170-r2-p120-s0.25](runs/complementary-v170-r2-p120-s0.25/replay/analysis.json) | B, 0 | 10.477 | 5.166 | True | 0.576 | True / True | 186.078 | True | 6584.7 | 29.451 |
| [complementary-v170-r2-p120-s0.25](runs/complementary-v170-r2-p120-s0.25/replay/analysis.json) | B, 1 | 10.477 | 5.235 | True | 0.596 | True / True | 186.078 | True | 6584.6 | 29.368 |
| [complementary-v170-r2-p120-s0.5](runs/complementary-v170-r2-p120-s0.5/replay/analysis.json) | A, 0 | 10.183 | 10.354 | False | 0.724 | True / True | 186.186 | True | 3251.3 | 27.867 |
| [complementary-v170-r2-p120-s0.5](runs/complementary-v170-r2-p120-s0.5/replay/analysis.json) | A, 1 | 10.183 | 10.442 | False | 0.719 | True / True | 186.186 | True | 3251.4 | 27.909 |
| [complementary-v170-r2-p120-s0.5](runs/complementary-v170-r2-p120-s0.5/replay/analysis.json) | B, 0 | 10.477 | 5.160 | True | 0.579 | True / True | 185.874 | True | 6584.7 | 29.367 |
| [complementary-v170-r2-p120-s0.5](runs/complementary-v170-r2-p120-s0.5/replay/analysis.json) | B, 1 | 10.477 | 5.226 | True | 0.598 | True / True | 185.874 | True | 6584.7 | 29.271 |
| [complementary-v170-r2-p150-s0.5](runs/complementary-v170-r2-p150-s0.5/replay/analysis.json) | A, 0 | 13.094 | 1.671 | True | 0.504 | True / True | 186.158 | True | 4026.1 | 29.962 |
| [complementary-v170-r2-p150-s0.5](runs/complementary-v170-r2-p150-s0.5/replay/analysis.json) | A, 1 | 13.093 | 1.784 | True | 0.553 | True / True | 186.158 | True | 4026.2 | 30.063 |
| [complementary-v170-r2-p150-s0.5](runs/complementary-v170-r2-p150-s0.5/replay/analysis.json) | B, 0 | 13.007 | 0.440 | True | 0.557 | True / True | 186.608 | True | 5692.9 | 30.705 |
| [complementary-v170-r2-p150-s0.5](runs/complementary-v170-r2-p150-s0.5/replay/analysis.json) | B, 1 | 13.008 | 0.415 | True | 0.593 | True / True | 186.608 | True | 5692.8 | 30.539 |
| [complementary-v170-r2-p180-s0.5](runs/complementary-v170-r2-p180-s0.5/replay/analysis.json) | A, 0 | 14.984 | -0.699 | True | 1.229 | True / True | 201.225 | True | 4833.2 | 47.425 |
| [complementary-v170-r2-p180-s0.5](runs/complementary-v170-r2-p180-s0.5/replay/analysis.json) | A, 1 | 14.984 | -0.699 | True | 1.080 | True / True | 201.225 | True | 4833.2 | 47.364 |
| [complementary-v170-r2-p180-s0.5](runs/complementary-v170-r2-p180-s0.5/replay/analysis.json) | B, 0 | 14.984 | -0.699 | True | 1.229 | True / True | 201.225 | True | 4833.2 | 47.426 |
| [complementary-v170-r2-p180-s0.5](runs/complementary-v170-r2-p180-s0.5/replay/analysis.json) | B, 1 | 14.984 | -0.699 | True | 1.080 | True / True | 201.225 | True | 4833.2 | 47.364 |
| [complementary-v170-r2-p60-s0.5](runs/complementary-v170-r2-p60-s0.5/replay/analysis.json) | A, 0 | 4.491 | 154.717 | False | 0.943 | True / True | 223.188 | True | 1872.4 | 83.872 |
| [complementary-v170-r2-p60-s0.5](runs/complementary-v170-r2-p60-s0.5/replay/analysis.json) | A, 1 | 4.491 | 154.711 | False | 0.894 | True / True | 223.188 | True | 1872.7 | 82.241 |
| [complementary-v170-r2-p60-s0.5](runs/complementary-v170-r2-p60-s0.5/replay/analysis.json) | B, 0 | 4.275 | 148.455 | False | 0.762 | True / True | 231.963 | True | 8539.3 | 38.010 |
| [complementary-v170-r2-p60-s0.5](runs/complementary-v170-r2-p60-s0.5/replay/analysis.json) | B, 1 | 4.275 | 148.467 | False | 0.790 | True / True | 231.963 | True | 8539.1 | 37.840 |
| [complementary-v170-r2-p90-s0.25](runs/complementary-v170-r2-p90-s0.25/replay/analysis.json) | A, 0 | 7.231 | 40.271 | False | 0.798 | True / True | 179.917 | True | 2532.3 | 22.236 |
| [complementary-v170-r2-p90-s0.25](runs/complementary-v170-r2-p90-s0.25/replay/analysis.json) | A, 1 | 7.232 | 39.382 | False | 0.819 | True / True | 179.917 | True | 2532.2 | 22.124 |
| [complementary-v170-r2-p90-s0.25](runs/complementary-v170-r2-p90-s0.25/replay/analysis.json) | B, 0 | 7.495 | 19.275 | False | 0.742 | True / True | 178.386 | True | 7532.2 | 24.909 |
| [complementary-v170-r2-p90-s0.25](runs/complementary-v170-r2-p90-s0.25/replay/analysis.json) | B, 1 | 7.496 | 19.190 | False | 0.755 | True / True | 178.386 | True | 7532.3 | 24.906 |
| [complementary-v170-r2-p90-s0.5](runs/complementary-v170-r2-p90-s0.5/replay/analysis.json) | A, 0 | 7.231 | 40.646 | False | 0.798 | True / True | 179.696 | True | 2532.3 | 22.273 |
| [complementary-v170-r2-p90-s0.5](runs/complementary-v170-r2-p90-s0.5/replay/analysis.json) | A, 1 | 7.232 | 39.586 | False | 0.819 | True / True | 179.696 | True | 2532.2 | 22.142 |
| [complementary-v170-r2-p90-s0.5](runs/complementary-v170-r2-p90-s0.5/replay/analysis.json) | B, 0 | 7.495 | 19.276 | False | 0.740 | True / True | 178.143 | True | 7532.2 | 24.987 |
| [complementary-v170-r2-p90-s0.5](runs/complementary-v170-r2-p90-s0.5/replay/analysis.json) | B, 1 | 7.496 | 19.194 | False | 0.754 | True / True | 178.143 | True | 7532.3 | 25.000 |
| [complementary-v198-r100-p180-s1](runs/complementary-v198-r100-p180-s1/replay/analysis.json) | A, 0 | 1.861 | 193.735 | False | 2.430 | True / False | 357.478 | True | 967.2 | 281.368 |
| [complementary-v198-r100-p180-s1](runs/complementary-v198-r100-p180-s1/replay/analysis.json) | A, 1 | 1.861 | 193.742 | False | 2.286 | True / False | 357.478 | True | 967.2 | 289.599 |
| [complementary-v198-r100-p180-s1](runs/complementary-v198-r100-p180-s1/replay/analysis.json) | B, 0 | 1.861 | 193.735 | False | 2.430 | True / False | 357.481 | True | 967.2 | 281.377 |
| [complementary-v198-r100-p180-s1](runs/complementary-v198-r100-p180-s1/replay/analysis.json) | B, 1 | 1.861 | 193.742 | False | 2.286 | True / False | 357.481 | True | 967.2 | 289.603 |
| [complementary-v198-r2-p120-s0.5](runs/complementary-v198-r2-p120-s0.5/replay/analysis.json) | A, 0 | 11.849 | 5.666 | True | 0.665 | True / True | 218.829 | True | 3235.9 | 31.230 |
| [complementary-v198-r2-p120-s0.5](runs/complementary-v198-r2-p120-s0.5/replay/analysis.json) | A, 1 | 11.849 | 5.700 | True | 0.658 | True / True | 218.829 | True | 3236.0 | 31.227 |
| [complementary-v198-r2-p120-s0.5](runs/complementary-v198-r2-p120-s0.5/replay/analysis.json) | B, 0 | 12.250 | 1.637 | True | 0.607 | True / True | 215.724 | True | 6569.3 | 35.214 |
| [complementary-v198-r2-p120-s0.5](runs/complementary-v198-r2-p120-s0.5/replay/analysis.json) | B, 1 | 12.250 | 1.712 | True | 0.603 | True / True | 215.724 | True | 6569.3 | 35.155 |
| [complementary-v198-r2-p150-s0.5](runs/complementary-v198-r2-p150-s0.5/replay/analysis.json) | A, 0 | 15.244 | -0.703 | True | 0.488 | True / True | 217.262 | True | 4014.5 | 35.219 |
| [complementary-v198-r2-p150-s0.5](runs/complementary-v198-r2-p150-s0.5/replay/analysis.json) | A, 1 | 15.243 | -0.703 | True | 0.522 | True / True | 217.262 | True | 4014.6 | 35.252 |
| [complementary-v198-r2-p150-s0.5](runs/complementary-v198-r2-p150-s0.5/replay/analysis.json) | B, 0 | 15.181 | -0.729 | True | 0.670 | True / True | 217.570 | True | 5681.2 | 36.030 |
| [complementary-v198-r2-p150-s0.5](runs/complementary-v198-r2-p150-s0.5/replay/analysis.json) | B, 1 | 15.183 | -0.729 | True | 0.606 | True / True | 217.570 | True | 5681.1 | 35.909 |
| [complementary-v198-r2-p150-s1](runs/complementary-v198-r2-p150-s1/replay/analysis.json) | A, 0 | 15.244 | -0.706 | True | 0.485 | True / True | 216.952 | True | 4014.5 | 34.929 |
| [complementary-v198-r2-p150-s1](runs/complementary-v198-r2-p150-s1/replay/analysis.json) | A, 1 | 15.243 | -0.705 | True | 0.532 | True / True | 216.952 | True | 4014.6 | 34.999 |
| [complementary-v198-r2-p150-s1](runs/complementary-v198-r2-p150-s1/replay/analysis.json) | B, 0 | 15.181 | -0.731 | True | 0.667 | True / True | 217.573 | True | 5681.2 | 35.763 |
| [complementary-v198-r2-p150-s1](runs/complementary-v198-r2-p150-s1/replay/analysis.json) | B, 1 | 15.183 | -0.731 | True | 0.602 | True / True | 217.573 | True | 5681.1 | 35.616 |
| [complementary-v198-r2-p180-s0.5](runs/complementary-v198-r2-p180-s0.5/replay/analysis.json) | A, 0 | 17.474 | -0.777 | True | 1.447 | True / True | 239.535 | True | 4823.4 | 60.167 |
| [complementary-v198-r2-p180-s0.5](runs/complementary-v198-r2-p180-s0.5/replay/analysis.json) | A, 1 | 17.474 | -0.777 | True | 1.272 | True / True | 239.535 | True | 4823.4 | 60.041 |
| [complementary-v198-r2-p180-s0.5](runs/complementary-v198-r2-p180-s0.5/replay/analysis.json) | B, 0 | 17.474 | -0.777 | True | 1.447 | True / True | 239.537 | True | 4823.4 | 60.166 |
| [complementary-v198-r2-p180-s0.5](runs/complementary-v198-r2-p180-s0.5/replay/analysis.json) | B, 1 | 17.474 | -0.777 | True | 1.272 | True / True | 239.537 | True | 4823.4 | 60.042 |
| [complementary-v198-r2-p180-s1](runs/complementary-v198-r2-p180-s1/replay/analysis.json) | A, 0 | 17.474 | -0.770 | True | 1.441 | True / True | 239.141 | True | 4823.4 | 59.460 |
| [complementary-v198-r2-p180-s1](runs/complementary-v198-r2-p180-s1/replay/analysis.json) | A, 1 | 17.474 | -0.769 | True | 1.269 | True / True | 239.141 | True | 4823.4 | 59.376 |
| [complementary-v198-r2-p180-s1](runs/complementary-v198-r2-p180-s1/replay/analysis.json) | B, 0 | 17.474 | -0.770 | True | 1.441 | True / True | 239.140 | True | 4823.4 | 59.455 |
| [complementary-v198-r2-p180-s1](runs/complementary-v198-r2-p180-s1/replay/analysis.json) | B, 1 | 17.474 | -0.769 | True | 1.269 | True / True | 239.140 | True | 4823.4 | 59.383 |
| [complementary-v198-r2-p60-s0.5](runs/complementary-v198-r2-p60-s0.5/replay/analysis.json) | A, 0 | 5.188 | 177.917 | False | 0.742 | True / True | 231.113 | True | 1857.1 | 59.141 |
| [complementary-v198-r2-p60-s0.5](runs/complementary-v198-r2-p60-s0.5/replay/analysis.json) | A, 1 | 5.188 | 177.910 | False | 0.765 | True / True | 231.113 | True | 1857.2 | 58.552 |
| [complementary-v198-r2-p60-s0.5](runs/complementary-v198-r2-p60-s0.5/replay/analysis.json) | B, 0 | 5.025 | 169.208 | False | 0.827 | True / True | 238.145 | True | 8523.9 | 26.621 |
| [complementary-v198-r2-p60-s0.5](runs/complementary-v198-r2-p60-s0.5/replay/analysis.json) | B, 1 | 5.025 | 169.227 | False | 0.847 | True / True | 238.145 | True | 8523.8 | 26.704 |
| [complementary-v198-r2-p60-s1](runs/complementary-v198-r2-p60-s1/replay/analysis.json) | A, 0 | 5.188 | 177.864 | False | 0.742 | True / True | 230.934 | True | 1857.1 | 58.870 |
| [complementary-v198-r2-p60-s1](runs/complementary-v198-r2-p60-s1/replay/analysis.json) | A, 1 | 5.188 | 177.858 | False | 0.765 | True / True | 230.934 | True | 1857.2 | 58.261 |
| [complementary-v198-r2-p60-s1](runs/complementary-v198-r2-p60-s1/replay/analysis.json) | B, 0 | 5.025 | 169.152 | False | 0.827 | True / True | 237.918 | True | 8523.8 | 26.190 |
| [complementary-v198-r2-p60-s1](runs/complementary-v198-r2-p60-s1/replay/analysis.json) | B, 1 | 5.025 | 169.172 | False | 0.846 | True / True | 237.918 | True | 8523.7 | 26.279 |
| [complementary-v198-r2-p90-s1](runs/complementary-v198-r2-p90-s1/replay/analysis.json) | A, 0 | 8.405 | 22.729 | False | 0.782 | True / True | 209.578 | True | 2506.4 | 24.711 |
| [complementary-v198-r2-p90-s1](runs/complementary-v198-r2-p90-s1/replay/analysis.json) | A, 1 | 8.405 | 22.654 | False | 0.780 | True / True | 209.578 | True | 2506.2 | 24.534 |
| [complementary-v198-r2-p90-s1](runs/complementary-v198-r2-p90-s1/replay/analysis.json) | B, 0 | 8.814 | 12.201 | False | 0.621 | True / True | 207.486 | True | 7506.2 | 26.533 |
| [complementary-v198-r2-p90-s1](runs/complementary-v198-r2-p90-s1/replay/analysis.json) | B, 1 | 8.815 | 12.139 | False | 0.642 | True / True | 207.486 | True | 7506.4 | 26.577 |
