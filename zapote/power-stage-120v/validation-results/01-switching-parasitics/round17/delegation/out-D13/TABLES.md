# D-13 decision tables

All values are simulator observations, not hardware bounds. Indeterminate runs have no verdict.

## baseline all

| Tj °C | attempted / indeterminate | max off V | max VDS V | off fails model / 3.0 / 1.9 | VDS fails | S1 ZVS / completed | EΣ µJ range |
|---|---|---|---|---|---|---|---|
| 27 | 56 / 0 | 5.078517 | 511.1413 | 24 / 26 / 40 | 0 | 36 / 36 | 84.020–789.753 |
| 100 | 56 / 0 | 5.036497 | 512.8953 | 27 / 27 / 40 | 0 | 36 / 36 | 93.653–784.924 |
| 150 | 56 / 2 | 4.905446 | 513.7754 | 34 / 26 / 38 | 0 | 24 / 36 | 102.092–782.916 |

## F6 all

| Tj °C | attempted / indeterminate | max off V | max VDS V | off fails model / 3.0 / 1.9 | VDS fails | S1 ZVS / completed | EΣ µJ range |
|---|---|---|---|---|---|---|---|
| 27 | 56 / 0 | 0.511685 | 482.2470 | 0 / 0 / 0 | 0 | 36 / 36 | 61.087–766.647 |
| 100 | 56 / 0 | 0.283947 | 475.2766 | 0 / 0 / 0 | 0 | 36 / 36 | 63.130–763.690 |
| 150 | 56 / 56 | — | — | no verdict | no verdict | — | — |

## baseline nominal

| Tj °C | attempted / indeterminate | max off V | max VDS V | off fails model / 3.0 / 1.9 | VDS fails | S1 ZVS / completed | EΣ µJ range |
|---|---|---|---|---|---|---|---|
| 27 | 20 / 0 | 4.523586 | 511.1413 | 4 / 6 / 20 | 0 | 12 / 12 | 84.860–788.805 |
| 100 | 20 / 0 | 4.480325 | 512.8953 | 7 / 7 / 20 | 0 | 12 / 12 | 96.037–784.193 |
| 150 | 20 / 1 | 4.440149 | 513.7754 | 15 / 7 / 19 | 0 | 12 / 12 | 103.098–782.916 |

## F6 nominal

| Tj °C | attempted / indeterminate | max off V | max VDS V | off fails model / 3.0 / 1.9 | VDS fails | S1 ZVS / completed | EΣ µJ range |
|---|---|---|---|---|---|---|---|
| 27 | 20 / 0 | 0.511685 | 482.2470 | 0 / 0 / 0 | 0 | 12 / 12 | 62.335–765.439 |
| 100 | 20 / 0 | 0.283947 | 474.8672 | 0 / 0 / 0 | 0 | 12 / 12 | 63.652–762.828 |
| 150 | 20 / 20 | — | — | no verdict | no verdict | — | — |

## F7 nominal

| Tj °C | attempted / indeterminate | max off V | max VDS V | off fails model / 3.0 / 1.9 | VDS fails | S1 ZVS / completed | EΣ µJ range |
|---|---|---|---|---|---|---|---|
| 27 | 20 / 0 | 4.182724 | 510.9661 | 4 / 4 / 4 | 0 | 12 / 12 | 87.527–789.753 |
| 100 | 20 / 0 | 4.134434 | 512.1218 | 4 / 4 / 4 | 0 | 12 / 12 | 98.854–784.924 |
| 150 | 20 / 1 | 4.101881 | 513.0911 | 3 / 3 / 3 | 0 | 12 / 12 | 106.230–781.221 |

## Individual decision cases

| case | status | off V | model / 3.0 / 1.9 off screen | VDS V | incoming V / ZVS | Eoff / Eon / EΣ µJ |
|---|---|---|---|---|---|---|
| baseline_T27_S1_v170_i37_d0_dt307_esl1.06_step0.2 | complete | 3.939656 | FAIL/FAIL/FAIL | 203.6573 | 2.6084 / True | 63.601 / 16.512 / 92.519 |
| baseline_T27_S1_v170_i37_d0_dt307_esl10_step0.2 | complete | 4.040019 | FAIL/FAIL/FAIL | 197.3561 | 2.5959 / True | 61.980 / 16.487 / 90.845 |
| baseline_T27_S1_v170_i37_d1_dt307_esl1.06_step0.2 | complete | 3.645653 | FAIL/FAIL/FAIL | 202.6481 | 1.4563 / True | 58.766 / 16.624 / 86.419 |
| baseline_T27_S1_v170_i37_d1_dt307_esl10_step0.2 | complete | 3.599795 | FAIL/FAIL/FAIL | 196.9136 | 1.2567 / True | 56.647 / 16.626 / 84.020 |
| baseline_T27_S1_v170_i37_d0_dt348_esl1.06_step0.2 | complete | 2.234341 | pass/pass/FAIL | 203.6704 | -0.8774 / True | 65.926 / 16.852 / 93.445 |
| baseline_T27_S1_v170_i37_d0_dt348_esl10_step0.2 | complete | 2.236391 | pass/pass/FAIL | 197.4478 | -0.8620 / True | 64.700 / 16.852 / 92.643 |
| baseline_T27_S1_v170_i37_d1_dt348_esl1.06_step0.2 | complete | 2.129946 | pass/pass/FAIL | 202.6481 | -0.8802 / True | 60.347 / 16.871 / 86.926 |
| baseline_T27_S1_v170_i37_d1_dt348_esl10_step0.2 | complete | 2.110780 | pass/pass/FAIL | 196.9183 | -0.8767 / True | 58.258 / 16.859 / 84.860 |
| baseline_T27_S1_v170_i37_d0_dt443_esl1.06_step0.2 | complete | 0.935938 | pass/pass/pass | 203.6704 | -0.8757 / True | 69.546 / 16.829 / 95.857 |
| baseline_T27_S1_v170_i37_d0_dt443_esl10_step0.2 | complete | 0.844226 | pass/pass/pass | 197.4478 | -0.8920 / True | 67.983 / 16.830 / 95.164 |
| baseline_T27_S1_v170_i37_d1_dt443_esl1.06_step0.2 | complete | 0.601600 | pass/pass/pass | 202.6481 | -0.8668 / True | 63.906 / 16.870 / 90.144 |
| baseline_T27_S1_v170_i37_d1_dt443_esl10_step0.2 | complete | 0.523881 | pass/pass/pass | 196.9183 | -0.8836 / True | 61.239 / 16.849 / 87.527 |
| baseline_T27_S1_v198_i37_d0_dt307_esl1.06_step0.2 | complete | 3.868663 | FAIL/FAIL/FAIL | 256.9860 | 3.9125 / True | 69.988 / 16.482 / 112.735 |
| baseline_T27_S1_v198_i37_d0_dt307_esl10_step0.2 | complete | 3.936716 | FAIL/FAIL/FAIL | 251.0463 | 3.7508 / True | 66.679 / 16.474 / 110.063 |
| baseline_T27_S1_v198_i37_d1_dt307_esl1.06_step0.2 | complete | 3.651484 | FAIL/FAIL/FAIL | 252.1719 | 2.3736 / True | 62.885 / 16.597 / 102.629 |
| baseline_T27_S1_v198_i37_d1_dt307_esl10_step0.2 | complete | 3.563503 | FAIL/FAIL/FAIL | 248.4789 | 2.1419 / True | 60.205 / 16.613 / 101.142 |
| baseline_T27_S1_v198_i37_d0_dt348_esl1.06_step0.2 | complete | 2.390226 | pass/pass/FAIL | 256.9880 | -0.8962 / True | 74.168 / 16.844 / 113.268 |
| baseline_T27_S1_v198_i37_d0_dt348_esl10_step0.2 | complete | 2.357025 | pass/pass/FAIL | 251.0937 | -0.8906 / True | 71.521 / 16.858 / 111.365 |
| baseline_T27_S1_v198_i37_d1_dt348_esl1.06_step0.2 | complete | 2.227937 | pass/pass/FAIL | 252.1731 | -0.8894 / True | 66.193 / 16.867 / 103.099 |
| baseline_T27_S1_v198_i37_d1_dt348_esl10_step0.2 | complete | 2.210957 | pass/pass/FAIL | 248.4834 | -0.8962 / True | 63.693 / 16.858 / 101.914 |
| baseline_T27_S1_v198_i37_d0_dt443_esl1.06_step0.2 | complete | 0.943383 | pass/pass/pass | 256.9880 | -0.8604 / True | 82.561 / 16.837 / 115.849 |
| baseline_T27_S1_v198_i37_d0_dt443_esl10_step0.2 | complete | 0.856950 | pass/pass/pass | 251.0937 | -0.8997 / True | 79.060 / 16.815 / 113.648 |
| baseline_T27_S1_v198_i37_d1_dt443_esl1.06_step0.2 | complete | 0.608324 | pass/pass/pass | 252.1731 | -0.8527 / True | 74.182 / 16.880 / 106.645 |
| baseline_T27_S1_v198_i37_d1_dt443_esl10_step0.2 | complete | 0.534988 | pass/pass/pass | 248.4834 | -0.8843 / True | 70.867 / 16.842 / 104.760 |
| baseline_T27_S1_v280_i37_d0_dt307_esl1.06_step0.2 | complete | 4.061502 | FAIL/FAIL/FAIL | 360.4075 | 7.3534 / True | 86.123 / 16.346 / 152.287 |
| baseline_T27_S1_v280_i37_d0_dt307_esl10_step0.2 | complete | 3.967501 | FAIL/FAIL/FAIL | 376.0882 | 7.0459 / True | 84.415 / 16.407 / 166.584 |
| baseline_T27_S1_v280_i37_d1_dt307_esl1.06_step0.2 | complete | 3.807383 | FAIL/FAIL/FAIL | 361.2711 | 5.2420 / True | 75.853 / 16.472 / 139.065 |
| baseline_T27_S1_v280_i37_d1_dt307_esl10_step0.2 | complete | 3.686630 | FAIL/FAIL/FAIL | 378.2458 | 5.1342 / True | 73.825 / 16.573 / 154.436 |
| baseline_T27_S1_v280_i37_d0_dt348_esl1.06_step0.2 | complete | 2.566968 | pass/pass/FAIL | 360.4075 | -0.9138 / True | 93.890 / 16.859 / 152.480 |
| baseline_T27_S1_v280_i37_d0_dt348_esl10_step0.2 | complete | 2.583656 | pass/pass/FAIL | 376.0882 | -0.9396 / True | 95.489 / 16.936 / 167.630 |
| baseline_T27_S1_v280_i37_d1_dt348_esl1.06_step0.2 | complete | 2.386561 | pass/pass/FAIL | 361.2711 | -0.9022 / True | 82.897 / 16.884 / 139.485 |
| baseline_T27_S1_v280_i37_d1_dt348_esl10_step0.2 | complete | 2.421826 | pass/pass/FAIL | 378.2458 | -0.9418 / True | 83.565 / 16.923 / 155.486 |
| baseline_T27_S1_v280_i37_d0_dt443_esl1.06_step0.2 | complete | 0.939869 | pass/pass/pass | 360.4075 | -0.8440 / True | 110.067 / 16.857 / 154.976 |
| baseline_T27_S1_v280_i37_d0_dt443_esl10_step0.2 | complete | 0.871643 | pass/pass/pass | 376.0882 | -0.9098 / True | 114.265 / 16.817 / 169.456 |
| baseline_T27_S1_v280_i37_d1_dt443_esl1.06_step0.2 | complete | 0.610336 | pass/pass/pass | 361.2711 | -0.8372 / True | 99.108 / 16.898 / 143.365 |
| baseline_T27_S1_v280_i37_d1_dt443_esl10_step0.2 | complete | 0.552280 | pass/pass/pass | 378.2458 | -0.8889 / True | 102.691 / 16.852 / 158.606 |
| baseline_T27_S2_v280_i71_d0_dt307_esl1.06_step0.2 | complete | 5.078451 | FAIL/FAIL/FAIL | 326.7091 | -0.8980 / True | 481.254 / 43.725 / 554.987 |
| baseline_T27_S2_v280_i71_d0_dt307_esl10_step0.2 | complete | 5.078517 | FAIL/FAIL/FAIL | 335.2273 | -0.9208 / True | 486.787 / 43.621 / 569.343 |
| baseline_T27_S2_v280_i71_d1_dt307_esl1.06_step0.2 | complete | 4.802475 | FAIL/FAIL/FAIL | 340.1225 | -0.9635 / True | 439.161 / 43.807 / 500.238 |
| baseline_T27_S2_v280_i71_d1_dt307_esl10_step0.2 | complete | 4.678528 | FAIL/FAIL/FAIL | 346.0073 | -0.9444 / True | 429.564 / 43.744 / 495.661 |
| baseline_T27_S2_v280_i71_d0_dt348_esl1.06_step0.2 | complete | 3.134191 | pass/FAIL/FAIL | 326.7091 | -1.0630 / True | 494.449 / 43.861 / 557.197 |
| baseline_T27_S2_v280_i71_d0_dt348_esl10_step0.2 | complete | 3.237586 | pass/FAIL/FAIL | 335.2273 | -1.0396 / True | 501.591 / 43.885 / 573.428 |
| baseline_T27_S2_v280_i71_d1_dt348_esl1.06_step0.2 | complete | 2.702226 | pass/pass/FAIL | 340.1225 | -1.0424 / True | 442.177 / 43.951 / 502.403 |
| baseline_T27_S2_v280_i71_d1_dt348_esl10_step0.2 | complete | 2.644617 | pass/pass/FAIL | 346.0073 | -1.0462 / True | 434.006 / 43.937 / 499.452 |
| baseline_T27_S2_v280_i71_d0_dt443_esl1.06_step0.2 | complete | 1.720942 | pass/pass/pass | 326.7091 | -1.0276 / True | 500.286 / 43.960 / 563.438 |
| baseline_T27_S2_v280_i71_d0_dt443_esl10_step0.2 | complete | 1.588991 | pass/pass/pass | 335.2273 | -1.0615 / True | 509.767 / 43.948 / 579.291 |
| baseline_T27_S2_v280_i71_d1_dt443_esl1.06_step0.2 | complete | 1.109300 | pass/pass/pass | 340.1225 | -1.0283 / True | 447.127 / 44.042 / 509.206 |
| baseline_T27_S2_v280_i71_d1_dt443_esl10_step0.2 | complete | 0.982568 | pass/pass/pass | 346.0073 | -1.0525 / True | 439.849 / 44.018 / 505.649 |
| baseline_T27_S4_v198_i-20_d0_dt348_esl1.06_step0.2 | complete | 4.523586 | FAIL/FAIL/FAIL | 483.0166 | 198.5723 / False | 4.025 / 611.369 / 771.954 |
| baseline_T27_S4_v198_i-20_d0_dt348_esl10_step0.2 | complete | 4.416064 | FAIL/FAIL/FAIL | 511.1413 | 199.0994 / False | 4.021 / 600.745 / 786.058 |
| baseline_T27_S4_v198_i-20_d1_dt348_esl1.06_step0.2 | complete | 4.124373 | FAIL/FAIL/FAIL | 444.3992 | 198.6071 / False | 4.019 / 634.226 / 779.670 |
| baseline_T27_S4_v198_i-20_d1_dt348_esl10_step0.2 | complete | 3.986797 | FAIL/FAIL/FAIL | 457.4367 | 198.9498 / False | 4.018 / 626.377 / 788.805 |
| baseline_T27_S4_v198_i-20_d0_dt443_esl1.06_step0.2 | complete | 4.182724 | FAIL/FAIL/FAIL | 481.3704 | 198.9130 / False | 5.530 / 612.536 / 773.981 |
| baseline_T27_S4_v198_i-20_d0_dt443_esl10_step0.2 | complete | 4.127100 | FAIL/FAIL/FAIL | 510.9661 | 198.6376 / False | 5.526 / 600.836 / 787.387 |
| baseline_T27_S4_v198_i-20_d1_dt443_esl1.06_step0.2 | complete | 3.829355 | FAIL/FAIL/FAIL | 444.3099 | 198.8409 / False | 5.523 / 633.586 / 780.340 |
| baseline_T27_S4_v198_i-20_d1_dt443_esl10_step0.2 | complete | 3.687441 | FAIL/FAIL/FAIL | 457.8837 | 198.6892 / False | 5.523 / 625.675 / 789.753 |
| baseline_T100_S1_v170_i37_d0_dt307_esl1.06_step0.2 | complete | 4.430703 | FAIL/FAIL/FAIL | 206.8420 | 6.5200 / True | 72.513 / 17.137 / 105.646 |
| baseline_T100_S1_v170_i37_d0_dt307_esl10_step0.2 | complete | 4.528834 | FAIL/FAIL/FAIL | 200.4615 | 7.0927 / True | 71.360 / 17.103 / 103.773 |
| baseline_T100_S1_v170_i37_d1_dt307_esl1.06_step0.2 | complete | 4.054692 | FAIL/FAIL/FAIL | 205.4124 | 5.1578 / True | 66.557 / 17.232 / 96.772 |
| baseline_T100_S1_v170_i37_d1_dt307_esl10_step0.2 | complete | 4.050629 | FAIL/FAIL/FAIL | 198.4305 | 4.7432 / True | 64.343 / 17.234 / 93.653 |
| baseline_T100_S1_v170_i37_d0_dt348_esl1.06_step0.2 | complete | 2.383204 | pass/pass/FAIL | 208.1373 | -0.7123 / True | 77.286 / 17.830 / 107.771 |
| baseline_T100_S1_v170_i37_d0_dt348_esl10_step0.2 | complete | 2.478410 | pass/pass/FAIL | 201.5133 | -0.6880 / True | 75.362 / 17.787 / 105.443 |
| baseline_T100_S1_v170_i37_d1_dt348_esl1.06_step0.2 | complete | 2.297396 | pass/pass/FAIL | 205.4124 | -0.7454 / True | 70.088 / 17.831 / 98.979 |
| baseline_T100_S1_v170_i37_d1_dt348_esl10_step0.2 | complete | 2.252436 | pass/pass/FAIL | 198.4305 | -0.7234 / True | 67.480 / 17.817 / 96.037 |
| baseline_T100_S1_v170_i37_d0_dt443_esl1.06_step0.2 | complete | 0.932921 | pass/pass/pass | 208.1373 | -0.7890 / True | 81.649 / 17.829 / 110.046 |
| baseline_T100_S1_v170_i37_d0_dt443_esl10_step0.2 | complete | 0.851050 | pass/pass/pass | 201.5133 | -0.7648 / True | 79.667 / 17.842 / 108.455 |
| baseline_T100_S1_v170_i37_d1_dt443_esl1.06_step0.2 | complete | 0.601809 | pass/pass/pass | 205.4124 | -0.7866 / True | 73.832 / 17.833 / 101.085 |
| baseline_T100_S1_v170_i37_d1_dt443_esl10_step0.2 | complete | 0.526764 | pass/pass/pass | 198.4305 | -0.7781 / True | 70.838 / 17.848 / 98.854 |
| baseline_T100_S1_v198_i37_d0_dt307_esl1.06_step0.2 | complete | 4.418614 | FAIL/FAIL/FAIL | 260.1648 | 7.3638 / True | 77.957 / 17.126 / 127.983 |
| baseline_T100_S1_v198_i37_d0_dt307_esl10_step0.2 | complete | 4.576159 | FAIL/FAIL/FAIL | 254.3268 | 7.6965 / True | 76.022 / 17.090 / 125.821 |
| baseline_T100_S1_v198_i37_d1_dt307_esl1.06_step0.2 | complete | 4.021871 | FAIL/FAIL/FAIL | 252.7282 | 5.9294 / True | 70.468 / 17.218 / 114.962 |
| baseline_T100_S1_v198_i37_d1_dt307_esl10_step0.2 | complete | 4.062708 | FAIL/FAIL/FAIL | 248.2771 | 5.3043 / True | 67.087 / 17.220 / 111.897 |
| baseline_T100_S1_v198_i37_d0_dt348_esl1.06_step0.2 | complete | 2.402530 | pass/pass/FAIL | 261.4549 | -0.7094 / True | 87.067 / 17.893 / 130.093 |
| baseline_T100_S1_v198_i37_d0_dt348_esl10_step0.2 | complete | 2.402353 | pass/pass/FAIL | 255.5281 | -0.6640 / True | 84.267 / 17.849 / 127.916 |
| baseline_T100_S1_v198_i37_d1_dt348_esl1.06_step0.2 | complete | 2.332752 | pass/pass/FAIL | 253.6611 | -0.7492 / True | 77.590 / 17.878 / 117.243 |
| baseline_T100_S1_v198_i37_d1_dt348_esl10_step0.2 | complete | 2.235324 | pass/pass/FAIL | 249.5762 | -0.7101 / True | 74.015 / 17.870 / 114.561 |
| baseline_T100_S1_v198_i37_d0_dt443_esl1.06_step0.2 | complete | 0.940104 | pass/pass/pass | 261.4549 | -0.8085 / True | 96.158 / 17.829 / 131.973 |
| baseline_T100_S1_v198_i37_d0_dt443_esl10_step0.2 | complete | 0.864776 | pass/pass/pass | 255.5281 | -0.7756 / True | 93.203 / 17.875 / 130.666 |
| baseline_T100_S1_v198_i37_d1_dt443_esl1.06_step0.2 | complete | 0.607644 | pass/pass/pass | 253.6611 | -0.8003 / True | 85.504 / 17.827 / 119.266 |
| baseline_T100_S1_v198_i37_d1_dt443_esl10_step0.2 | complete | 0.538043 | pass/pass/pass | 249.5762 | -0.7927 / True | 81.527 / 17.868 / 117.379 |
| baseline_T100_S1_v280_i37_d0_dt307_esl1.06_step0.2 | complete | 4.532109 | FAIL/FAIL/FAIL | 345.6641 | 11.1904 / True | 90.846 / 16.985 / 157.825 |
| baseline_T100_S1_v280_i37_d0_dt307_esl10_step0.2 | complete | 4.668608 | FAIL/FAIL/FAIL | 362.7658 | 10.9086 / True | 90.599 / 16.986 / 172.312 |
| baseline_T100_S1_v280_i37_d1_dt307_esl1.06_step0.2 | complete | 4.162324 | FAIL/FAIL/FAIL | 346.0875 | 8.7162 / True | 81.517 / 17.079 / 142.842 |
| baseline_T100_S1_v280_i37_d1_dt307_esl10_step0.2 | complete | 4.211919 | FAIL/FAIL/FAIL | 366.6463 | 7.7638 / True | 78.364 / 17.130 / 157.133 |
| baseline_T100_S1_v280_i37_d0_dt348_esl1.06_step0.2 | complete | 2.557826 | pass/pass/FAIL | 345.6641 | -0.6884 / True | 104.773 / 17.904 / 160.223 |
| baseline_T100_S1_v280_i37_d0_dt348_esl10_step0.2 | complete | 2.501695 | pass/pass/FAIL | 362.7658 | -0.6356 / True | 106.231 / 17.923 / 174.746 |
| baseline_T100_S1_v280_i37_d1_dt348_esl1.06_step0.2 | complete | 2.453322 | pass/pass/FAIL | 346.0875 | -0.7188 / True | 93.551 / 17.904 / 145.662 |
| baseline_T100_S1_v280_i37_d1_dt348_esl10_step0.2 | complete | 2.359135 | pass/pass/FAIL | 366.6463 | -0.6675 / True | 93.742 / 17.959 / 160.426 |
| baseline_T100_S1_v280_i37_d0_dt443_esl1.06_step0.2 | complete | 0.930068 | pass/pass/pass | 345.6641 | -0.8142 / True | 118.346 / 17.825 / 161.620 |
| baseline_T100_S1_v280_i37_d0_dt443_esl10_step0.2 | complete | 0.872856 | pass/pass/pass | 362.7658 | -0.7871 / True | 124.007 / 17.916 / 177.251 |
| baseline_T100_S1_v280_i37_d1_dt443_esl1.06_step0.2 | complete | 0.606920 | pass/pass/pass | 346.0875 | -0.8083 / True | 106.159 / 17.829 / 147.516 |
| baseline_T100_S1_v280_i37_d1_dt443_esl10_step0.2 | complete | 0.549671 | pass/pass/pass | 366.6463 | -0.8090 / True | 110.503 / 17.912 / 163.542 |
| baseline_T100_S2_v280_i71_d0_dt307_esl1.06_step0.2 | complete | 5.001238 | FAIL/FAIL/FAIL | 327.1108 | 0.1015 / True | 491.241 / 42.232 / 601.160 |
| baseline_T100_S2_v280_i71_d0_dt307_esl10_step0.2 | complete | 5.036497 | FAIL/FAIL/FAIL | 330.8848 | 0.4712 / True | 491.065 / 42.115 / 616.235 |
| baseline_T100_S2_v280_i71_d1_dt307_esl1.06_step0.2 | complete | 4.805599 | FAIL/FAIL/FAIL | 335.0987 | -0.8073 / True | 473.509 / 42.500 / 546.297 |
| baseline_T100_S2_v280_i71_d1_dt307_esl10_step0.2 | complete | 4.813052 | FAIL/FAIL/FAIL | 339.2211 | -0.8374 / True | 466.338 / 42.508 / 542.916 |
| baseline_T100_S2_v280_i71_d0_dt348_esl1.06_step0.2 | complete | 3.496557 | FAIL/FAIL/FAIL | 327.1108 | -0.9244 / True | 545.354 / 42.792 / 605.328 |
| baseline_T100_S2_v280_i71_d0_dt348_esl10_step0.2 | complete | 3.602984 | FAIL/FAIL/FAIL | 330.8848 | -0.8898 / True | 551.776 / 42.738 / 619.206 |
| baseline_T100_S2_v280_i71_d1_dt348_esl1.06_step0.2 | complete | 3.016611 | FAIL/FAIL/FAIL | 335.0987 | -0.9132 / True | 490.902 / 42.852 / 550.676 |
| baseline_T100_S2_v280_i71_d1_dt348_esl10_step0.2 | complete | 2.893758 | pass/pass/FAIL | 339.2211 | -0.8878 / True | 481.362 / 42.816 / 547.154 |
| baseline_T100_S2_v280_i71_d0_dt443_esl1.06_step0.2 | complete | 1.705075 | pass/pass/pass | 327.1108 | -0.9563 / True | 550.479 / 42.882 / 610.511 |
| baseline_T100_S2_v280_i71_d0_dt443_esl10_step0.2 | complete | 1.587593 | pass/pass/pass | 330.8848 | -0.9383 / True | 560.241 / 42.927 / 626.123 |
| baseline_T100_S2_v280_i71_d1_dt443_esl1.06_step0.2 | complete | 1.104631 | pass/pass/pass | 335.0987 | -0.9580 / True | 495.965 / 42.944 / 556.056 |
| baseline_T100_S2_v280_i71_d1_dt443_esl10_step0.2 | complete | 0.983896 | pass/pass/pass | 339.2211 | -0.9489 / True | 488.431 / 42.967 / 554.041 |
| baseline_T100_S4_v198_i-20_d0_dt348_esl1.06_step0.2 | complete | 4.480325 | FAIL/FAIL/FAIL | 484.2709 | 198.4877 / False | 3.986 / 612.241 / 769.854 |
| baseline_T100_S4_v198_i-20_d0_dt348_esl10_step0.2 | complete | 4.374690 | FAIL/FAIL/FAIL | 512.8953 | 198.9111 / False | 3.984 / 602.033 / 782.623 |
| baseline_T100_S4_v198_i-20_d1_dt348_esl1.06_step0.2 | complete | 4.074685 | FAIL/FAIL/FAIL | 441.8893 | 198.5015 / False | 3.982 / 635.168 / 775.041 |
| baseline_T100_S4_v198_i-20_d1_dt348_esl10_step0.2 | complete | 3.949382 | FAIL/FAIL/FAIL | 460.2509 | 198.7527 / False | 3.982 / 626.735 / 784.193 |
| baseline_T100_S4_v198_i-20_d0_dt443_esl1.06_step0.2 | complete | 4.134434 | FAIL/FAIL/FAIL | 483.6745 | 198.8470 / False | 5.273 / 613.366 / 770.522 |
| baseline_T100_S4_v198_i-20_d0_dt443_esl10_step0.2 | complete | 4.079504 | FAIL/FAIL/FAIL | 512.1218 | 198.5352 / False | 5.272 / 602.096 / 783.577 |
| baseline_T100_S4_v198_i-20_d1_dt443_esl1.06_step0.2 | complete | 3.768367 | FAIL/FAIL/FAIL | 442.2588 | 198.7778 / False | 5.270 / 634.605 / 775.476 |
| baseline_T100_S4_v198_i-20_d1_dt443_esl10_step0.2 | complete | 3.639022 | FAIL/FAIL/FAIL | 460.9101 | 198.5738 / False | 5.270 / 626.158 / 784.924 |
| baseline_T150_S1_v170_i37_d0_dt307_esl1.06_step0.2 | complete | 4.535410 | FAIL/FAIL/FAIL | 211.2295 | 12.5679 / False | 77.019 / 15.941 / 115.564 |
| baseline_T150_S1_v170_i37_d0_dt307_esl10_step0.2 | complete | 4.482559 | FAIL/FAIL/FAIL | 205.8135 | 13.5990 / False | 75.997 / 15.906 / 114.273 |
| baseline_T150_S1_v170_i37_d1_dt307_esl1.06_step0.2 | complete | 4.404094 | FAIL/FAIL/FAIL | 207.0943 | 10.2398 / False | 73.331 / 16.013 / 105.201 |
| baseline_T150_S1_v170_i37_d1_dt307_esl10_step0.2 | complete | 4.333256 | FAIL/FAIL/FAIL | 200.1547 | 10.0879 / False | 71.422 / 16.019 / 102.092 |
| baseline_T150_S1_v170_i37_d0_dt348_esl1.06_step0.2 | complete | 2.680172 | FAIL/pass/FAIL | 210.9784 | -0.5998 / True | 85.263 / 16.722 / 116.253 |
| baseline_T150_S1_v170_i37_d0_dt348_esl10_step0.2 | complete | 2.904420 | FAIL/pass/FAIL | 205.1691 | -0.6173 / True | 83.551 / 16.695 / 114.317 |
| baseline_T150_S1_v170_i37_d1_dt348_esl1.06_step0.2 | complete | 2.439256 | pass/pass/FAIL | 207.0943 | -0.6058 / True | 78.295 / 16.742 / 106.761 |
| baseline_T150_S1_v170_i37_d1_dt348_esl10_step0.2 | complete | 2.474769 | pass/pass/FAIL | 200.1547 | -0.6239 / True | 74.941 / 16.719 / 103.098 |
| baseline_T150_S1_v170_i37_d0_dt443_esl1.06_step0.2 | complete | 0.928008 | pass/pass/pass | 210.9784 | -0.6841 / True | 91.351 / 16.824 / 119.125 |
| baseline_T150_S1_v170_i37_d0_dt443_esl10_step0.2 | complete | 0.853060 | pass/pass/pass | 205.1691 | -0.6712 / True | 88.951 / 16.793 / 117.043 |
| baseline_T150_S1_v170_i37_d1_dt443_esl1.06_step0.2 | complete | 0.601870 | pass/pass/pass | 207.0943 | -0.6963 / True | 82.922 / 16.832 / 109.677 |
| baseline_T150_S1_v170_i37_d1_dt443_esl10_step0.2 | complete | 0.527656 | pass/pass/pass | 200.1547 | -0.6763 / True | 79.302 / 16.814 / 106.230 |
| baseline_T150_S1_v198_i37_d0_dt307_esl1.06_step0.2 | complete | 4.609206 | FAIL/FAIL/FAIL | 264.4467 | 13.3648 / False | 81.735 / 15.935 / 138.750 |
| baseline_T150_S1_v198_i37_d0_dt307_esl10_step0.2 | complete | 4.559623 | FAIL/FAIL/FAIL | 259.7164 | 15.0370 / False | 79.826 / 15.904 / 137.929 |
| baseline_T150_S1_v198_i37_d1_dt307_esl1.06_step0.2 | complete | 4.475890 | FAIL/FAIL/FAIL | 254.1025 | 10.8341 / False | 77.779 / 15.999 / 124.426 |
| baseline_T150_S1_v198_i37_d1_dt307_esl10_step0.2 | complete | 4.414823 | FAIL/FAIL/FAIL | 250.8414 | 10.7672 / False | 75.090 / 16.011 / 121.568 |
| baseline_T150_S1_v198_i37_d0_dt348_esl1.06_step0.2 | complete | 2.603036 | FAIL/pass/FAIL | 264.1319 | -0.5530 / True | 94.593 / 16.766 / 139.484 |
| baseline_T150_S1_v198_i37_d0_dt348_esl10_step0.2 | complete | 2.899700 | FAIL/pass/FAIL | 258.9229 | -0.5785 / True | 91.766 / 16.714 / 137.890 |
| baseline_T150_S1_v198_i37_d1_dt348_esl1.06_step0.2 | complete | 2.376382 | pass/pass/FAIL | 254.7263 | -0.5736 / True | 86.224 / 16.778 / 126.174 |
| baseline_T150_S1_v198_i37_d1_dt348_esl10_step0.2 | complete | 2.431124 | pass/pass/FAIL | 251.1483 | -0.5920 / True | 81.456 / 16.741 / 122.787 |
| baseline_T150_S1_v198_i37_d0_dt443_esl1.06_step0.2 | complete | 0.935388 | pass/pass/pass | 264.1319 | -0.6898 / True | 106.624 / 16.857 / 142.124 |
| baseline_T150_S1_v198_i37_d0_dt443_esl10_step0.2 | complete | 0.866743 | pass/pass/pass | 258.9229 | -0.6511 / True | 103.263 / 16.820 / 140.738 |
| baseline_T150_S1_v198_i37_d1_dt443_esl1.06_step0.2 | complete | 0.607515 | pass/pass/pass | 254.7263 | -0.7052 / True | 95.707 / 16.856 / 129.143 |
| baseline_T150_S1_v198_i37_d1_dt443_esl10_step0.2 | complete | 0.538613 | pass/pass/pass | 251.1483 | -0.6655 / True | 91.101 / 16.841 / 126.152 |
| baseline_T150_S1_v280_i37_d0_dt307_esl1.06_step0.2 | complete | 4.620245 | FAIL/FAIL/FAIL | 340.4764 | 18.0228 / False | 91.600 / 15.790 / 163.396 |
| baseline_T150_S1_v280_i37_d0_dt307_esl10_step0.2 | complete | 4.634767 | FAIL/FAIL/FAIL | 352.6964 | 21.3819 / False | 88.951 / 15.801 / 177.477 |
| baseline_T150_S1_v280_i37_d1_dt307_esl1.06_step0.2 | complete | 4.494760 | FAIL/FAIL/FAIL | 336.0117 | 15.0524 / False | 88.728 / 15.864 / 147.294 |
| baseline_T150_S1_v280_i37_d1_dt307_esl10_step0.2 | complete | 4.496512 | FAIL/FAIL/FAIL | 356.7960 | 15.0710 / False | 87.193 / 15.920 / 160.669 |
| baseline_T150_S1_v280_i37_d0_dt348_esl1.06_step0.2 | complete | 2.735508 | FAIL/pass/FAIL | 339.9694 | -0.4879 / True | 110.632 / 16.757 / 163.932 |
| baseline_T150_S1_v280_i37_d0_dt348_esl10_step0.2 | complete | 2.978884 | FAIL/pass/FAIL | 352.6964 | -0.5032 / True | 110.890 / 16.716 / 176.954 |
| baseline_T150_S1_v280_i37_d1_dt348_esl1.06_step0.2 | complete | 2.504172 | FAIL/pass/FAIL | 336.0117 | -0.5479 / True | 100.612 / 16.765 / 148.920 |
| baseline_T150_S1_v280_i37_d1_dt348_esl10_step0.2 | complete | 2.505623 | FAIL/pass/FAIL | 356.7960 | -0.5437 / True | 98.556 / 16.757 / 161.724 |
| baseline_T150_S1_v280_i37_d0_dt443_esl1.06_step0.2 | complete | 0.921291 | pass/pass/pass | 340.1863 | -0.6989 / True | 126.226 / 16.855 / 166.653 |
| baseline_T150_S1_v280_i37_d0_dt443_esl10_step0.2 | complete | 0.869752 | pass/pass/pass | 352.6964 | -0.6400 / True | 130.374 / 16.844 / 179.952 |
| baseline_T150_S1_v280_i37_d1_dt443_esl1.06_step0.2 | complete | 0.605467 | pass/pass/pass | 336.0117 | -0.7046 / True | 113.963 / 16.858 / 152.188 |
| baseline_T150_S1_v280_i37_d1_dt443_esl10_step0.2 | complete | 0.545365 | pass/pass/pass | 356.7960 | -0.6534 / True | 117.287 / 16.870 / 165.618 |
| baseline_T150_S2_v280_i71_d0_dt307_esl1.06_step0.2 | complete | 4.888419 | FAIL/FAIL/FAIL | 326.6358 | 2.9161 / True | 480.180 / 40.046 / 641.298 |
| baseline_T150_S2_v280_i71_d0_dt307_esl10_step0.2 | complete | 4.905446 | FAIL/FAIL/FAIL | 328.4993 | 5.4286 / True | 470.144 / 39.907 / 657.068 |
| baseline_T150_S2_v280_i71_d1_dt307_esl1.06_step0.2 | complete | 4.764530 | FAIL/FAIL/FAIL | 331.4277 | -0.1634 / True | 480.537 / 40.494 / 583.562 |
| baseline_T150_S2_v280_i71_d1_dt307_esl10_step0.2 | complete | 4.746406 | FAIL/FAIL/FAIL | 333.5374 | -0.3105 / True | 475.496 / 40.558 / 581.098 |
| baseline_T150_S2_v280_i71_d0_dt348_esl1.06_step0.2 | complete | 3.787641 | FAIL/FAIL/FAIL | 326.6358 | -0.7990 / True | 585.568 / 41.033 / 643.721 |
| baseline_T150_S2_v280_i71_d0_dt348_esl10_step0.2 | complete | 3.988760 | FAIL/FAIL/FAIL | 328.4993 | -0.8087 / True | 593.293 / 40.942 / 657.677 |
| baseline_T150_S2_v280_i71_d1_dt348_esl1.06_step0.2 | complete | 3.271630 | FAIL/FAIL/FAIL | 331.4277 | -0.8316 / True | 530.296 / 41.046 / 586.464 |
| baseline_T150_S2_v280_i71_d1_dt348_esl10_step0.2 | complete | 3.227008 | FAIL/FAIL/FAIL | 333.5374 | -0.8242 / True | 518.586 / 41.012 / 583.001 |
| baseline_T150_S2_v280_i71_d0_dt443_esl1.06_step0.2 | complete | 1.694989 | pass/pass/pass | 326.6358 | -0.8858 / True | 591.556 / 41.191 / 649.687 |
| baseline_T150_S2_v280_i71_d0_dt443_esl10_step0.2 | complete | 1.583285 | pass/pass/pass | 328.4993 | -0.8482 / True | 602.196 / 41.174 / 664.235 |
| baseline_T150_S2_v280_i71_d1_dt443_esl1.06_step0.2 | complete | 1.102346 | pass/pass/pass | 331.4277 | -0.8784 / True | 535.675 / 41.241 / 593.050 |
| baseline_T150_S2_v280_i71_d1_dt443_esl10_step0.2 | complete | 0.981998 | pass/pass/pass | 333.5374 | -0.8525 / True | 527.290 / 41.228 / 590.180 |
| baseline_T150_S4_v198_i-20_d0_dt348_esl1.06_step0.2 | complete | 4.440149 | FAIL/FAIL/FAIL | 486.3860 | 198.3871 / False | 3.712 / 613.252 / 771.095 |
| baseline_T150_S4_v198_i-20_d0_dt348_esl10_step0.2 | complete | 4.337946 | FAIL/FAIL/FAIL | 513.7754 | 198.8485 / False | 3.710 / 603.300 / 782.916 |
| baseline_T150_S4_v198_i-20_d1_dt348_esl1.06_step0.2 | complete | 4.040009 | FAIL/FAIL/FAIL | 442.2402 | 198.4081 / False | 3.709 / 635.910 / 772.090 |
| baseline_T150_S4_v198_i-20_d1_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| baseline_T150_S4_v198_i-20_d0_dt443_esl1.06_step0.2 | complete | 4.101881 | FAIL/FAIL/FAIL | 485.3388 | 198.7539 / False | 4.846 / 614.054 / 768.786 |
| baseline_T150_S4_v198_i-20_d0_dt443_esl10_step0.2 | complete | 4.046177 | FAIL/FAIL/FAIL | 513.0911 | 198.4441 / False | 4.845 / 603.079 / 781.221 |
| baseline_T150_S4_v198_i-20_d1_dt443_esl1.06_step0.2 | complete | 3.728833 | FAIL/FAIL/FAIL | 441.6644 | 198.6818 / False | 4.843 / 635.265 / 772.231 |
| baseline_T150_S4_v198_i-20_d1_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T27_S1_v170_i37_d0_dt307_esl1.06_step0.2 | complete | -1.103844 | pass/pass/pass | 193.9408 | -0.8915 / True | 35.475 / 17.280 / 61.087 |
| F6_T27_S1_v170_i37_d0_dt307_esl10_step0.2 | complete | -1.267829 | pass/pass/pass | 196.8195 | -0.8879 / True | 36.483 / 17.283 / 64.230 |
| F6_T27_S1_v170_i37_d1_dt307_esl1.06_step0.2 | complete | -1.419174 | pass/pass/pass | 194.9769 | -0.8930 / True | 35.663 / 17.307 / 61.737 |
| F6_T27_S1_v170_i37_d1_dt307_esl10_step0.2 | complete | -1.482124 | pass/pass/pass | 197.6382 | -0.8905 / True | 36.663 / 17.321 / 65.021 |
| F6_T27_S1_v170_i37_d0_dt348_esl1.06_step0.2 | complete | -1.105528 | pass/pass/pass | 193.9408 | -0.8694 / True | 36.372 / 17.239 / 62.335 |
| F6_T27_S1_v170_i37_d0_dt348_esl10_step0.2 | complete | -1.271558 | pass/pass/pass | 196.8195 | -0.8812 / True | 37.453 / 17.229 / 64.706 |
| F6_T27_S1_v170_i37_d1_dt348_esl1.06_step0.2 | complete | -1.421510 | pass/pass/pass | 194.9769 | -0.8664 / True | 36.725 / 17.257 / 63.422 |
| F6_T27_S1_v170_i37_d1_dt348_esl10_step0.2 | complete | -1.485053 | pass/pass/pass | 197.6382 | -0.8795 / True | 37.703 / 17.252 / 65.653 |
| F6_T27_S1_v170_i37_d0_dt443_esl1.06_step0.2 | complete | -1.107207 | pass/pass/pass | 193.9408 | -0.8745 / True | 38.215 / 17.120 / 66.072 |
| F6_T27_S1_v170_i37_d0_dt443_esl10_step0.2 | complete | -1.276104 | pass/pass/pass | 196.8195 | -0.8729 / True | 39.689 / 17.137 / 68.220 |
| F6_T27_S1_v170_i37_d1_dt443_esl1.06_step0.2 | complete | -1.422992 | pass/pass/pass | 194.9769 | -0.8753 / True | 38.787 / 17.107 / 67.162 |
| F6_T27_S1_v170_i37_d1_dt443_esl10_step0.2 | complete | -1.487761 | pass/pass/pass | 197.6382 | -0.8711 / True | 40.197 / 17.122 / 69.394 |
| F6_T27_S1_v198_i37_d0_dt307_esl1.06_step0.2 | complete | -1.105445 | pass/pass/pass | 219.6236 | -0.8819 / True | 36.650 / 17.286 / 62.468 |
| F6_T27_S1_v198_i37_d0_dt307_esl10_step0.2 | complete | -1.267789 | pass/pass/pass | 217.7024 | -0.8726 / True | 36.165 / 17.271 / 62.849 |
| F6_T27_S1_v198_i37_d1_dt307_esl1.06_step0.2 | complete | -1.417968 | pass/pass/pass | 220.8490 | -0.8861 / True | 36.961 / 17.319 / 63.374 |
| F6_T27_S1_v198_i37_d1_dt307_esl10_step0.2 | complete | -1.484060 | pass/pass/pass | 219.1139 | -0.8741 / True | 36.455 / 17.311 / 63.835 |
| F6_T27_S1_v198_i37_d0_dt348_esl1.06_step0.2 | complete | -1.108134 | pass/pass/pass | 219.6236 | -0.8800 / True | 37.392 / 17.225 / 62.884 |
| F6_T27_S1_v198_i37_d0_dt348_esl10_step0.2 | complete | -1.270737 | pass/pass/pass | 217.7024 | -0.8882 / True | 36.943 / 17.218 / 63.262 |
| F6_T27_S1_v198_i37_d1_dt348_esl1.06_step0.2 | complete | -1.422162 | pass/pass/pass | 220.8490 | -0.8769 / True | 37.792 / 17.242 / 64.007 |
| F6_T27_S1_v198_i37_d1_dt348_esl10_step0.2 | complete | -1.487349 | pass/pass/pass | 219.1139 | -0.8885 / True | 37.298 / 17.242 / 64.141 |
| F6_T27_S1_v198_i37_d0_dt443_esl1.06_step0.2 | complete | -1.110012 | pass/pass/pass | 219.6236 | -0.8735 / True | 39.107 / 17.109 / 66.685 |
| F6_T27_S1_v198_i37_d0_dt443_esl10_step0.2 | complete | -1.276216 | pass/pass/pass | 217.7024 | -0.8800 / True | 38.635 / 17.122 / 66.218 |
| F6_T27_S1_v198_i37_d1_dt443_esl1.06_step0.2 | complete | -1.423894 | pass/pass/pass | 220.8490 | -0.8723 / True | 39.839 / 17.097 / 68.051 |
| F6_T27_S1_v198_i37_d1_dt443_esl10_step0.2 | complete | -1.491233 | pass/pass/pass | 219.1139 | -0.8791 / True | 39.203 / 17.106 / 67.324 |
| F6_T27_S1_v280_i37_d0_dt307_esl1.06_step0.2 | complete | -1.108977 | pass/pass/pass | 353.1383 | -0.8518 / True | 64.215 / 17.500 / 104.696 |
| F6_T27_S1_v280_i37_d0_dt307_esl10_step0.2 | complete | -1.269258 | pass/pass/pass | 350.9203 | -0.8264 / True | 62.442 / 17.428 / 107.699 |
| F6_T27_S1_v280_i37_d1_dt307_esl1.06_step0.2 | complete | -1.429480 | pass/pass/pass | 354.9431 | -0.8641 / True | 65.600 / 17.539 / 108.604 |
| F6_T27_S1_v280_i37_d1_dt307_esl10_step0.2 | complete | -1.490268 | pass/pass/pass | 353.0222 | -0.8246 / True | 63.752 / 17.488 / 111.717 |
| F6_T27_S1_v280_i37_d0_dt348_esl1.06_step0.2 | complete | -1.111048 | pass/pass/pass | 353.1383 | -0.9109 / True | 67.695 / 17.327 / 105.433 |
| F6_T27_S1_v280_i37_d0_dt348_esl10_step0.2 | complete | -1.271565 | pass/pass/pass | 350.9203 | -0.9123 / True | 67.548 / 17.379 / 109.502 |
| F6_T27_S1_v280_i37_d1_dt348_esl1.06_step0.2 | complete | -1.431382 | pass/pass/pass | 354.9431 | -0.9069 / True | 69.251 / 17.326 / 109.376 |
| F6_T27_S1_v280_i37_d1_dt348_esl10_step0.2 | complete | -1.493133 | pass/pass/pass | 353.0222 | -0.9186 / True | 69.038 / 17.408 / 113.631 |
| F6_T27_S1_v280_i37_d0_dt443_esl1.06_step0.2 | complete | -1.115403 | pass/pass/pass | 353.1383 | -0.8645 / True | 74.980 / 17.180 / 109.379 |
| F6_T27_S1_v280_i37_d0_dt443_esl10_step0.2 | complete | -1.276179 | pass/pass/pass | 350.9203 | -0.9003 / True | 75.416 / 17.186 / 112.708 |
| F6_T27_S1_v280_i37_d1_dt443_esl1.06_step0.2 | complete | -1.437108 | pass/pass/pass | 354.9431 | -0.8572 / True | 77.811 / 17.175 / 114.438 |
| F6_T27_S1_v280_i37_d1_dt443_esl10_step0.2 | complete | -1.498202 | pass/pass/pass | 353.0222 | -0.9011 / True | 77.876 / 17.166 / 117.461 |
| F6_T27_S2_v280_i71_d0_dt307_esl1.06_step0.2 | complete | -0.317568 | pass/pass/pass | 383.0867 | -0.9878 / True | 234.767 / 44.889 / 316.230 |
| F6_T27_S2_v280_i71_d0_dt307_esl10_step0.2 | complete | -0.638856 | pass/pass/pass | 373.0269 | -1.0202 / True | 219.797 / 44.730 / 304.745 |
| F6_T27_S2_v280_i71_d1_dt307_esl1.06_step0.2 | complete | -0.896309 | pass/pass/pass | 366.6981 | -1.0000 / True | 187.683 / 44.828 / 261.144 |
| F6_T27_S2_v280_i71_d1_dt307_esl10_step0.2 | complete | -1.023365 | pass/pass/pass | 362.1565 | -1.0360 / True | 173.687 / 44.704 / 246.578 |
| F6_T27_S2_v280_i71_d0_dt348_esl1.06_step0.2 | complete | -0.320304 | pass/pass/pass | 383.0867 | -1.0553 / True | 242.697 / 44.843 / 320.779 |
| F6_T27_S2_v280_i71_d0_dt348_esl10_step0.2 | complete | -0.641790 | pass/pass/pass | 373.0269 | -1.0137 / True | 228.358 / 44.855 / 310.115 |
| F6_T27_S2_v280_i71_d1_dt348_esl1.06_step0.2 | complete | -0.898509 | pass/pass/pass | 366.6981 | -1.0547 / True | 192.765 / 44.726 / 265.443 |
| F6_T27_S2_v280_i71_d1_dt348_esl10_step0.2 | complete | -1.025271 | pass/pass/pass | 362.1565 | -1.0169 / True | 178.577 / 44.708 / 251.847 |
| F6_T27_S2_v280_i71_d0_dt443_esl1.06_step0.2 | complete | -0.325880 | pass/pass/pass | 383.0867 | -1.0617 / True | 251.275 / 44.320 / 327.343 |
| F6_T27_S2_v280_i71_d0_dt443_esl10_step0.2 | complete | -0.645662 | pass/pass/pass | 373.0269 | -1.0581 / True | 237.719 / 44.456 / 317.808 |
| F6_T27_S2_v280_i71_d1_dt443_esl1.06_step0.2 | complete | -0.902455 | pass/pass/pass | 366.6981 | -1.0530 / True | 198.731 / 44.195 / 271.977 |
| F6_T27_S2_v280_i71_d1_dt443_esl10_step0.2 | complete | -1.026509 | pass/pass/pass | 362.1565 | -1.0460 / True | 184.354 / 44.324 / 259.458 |
| F6_T27_S4_v198_i-20_d0_dt348_esl1.06_step0.2 | complete | 0.092271 | pass/pass/pass | 460.5742 | 198.3448 / False | 4.691 / 610.954 / 741.684 |
| F6_T27_S4_v198_i-20_d0_dt348_esl10_step0.2 | complete | 0.511685 | pass/pass/pass | 478.8235 | 199.3546 / False | 4.687 / 600.802 / 753.595 |
| F6_T27_S4_v198_i-20_d1_dt348_esl1.06_step0.2 | complete | -0.682481 | pass/pass/pass | 434.8028 | 198.4036 / False | 4.699 / 631.765 / 747.813 |
| F6_T27_S4_v198_i-20_d1_dt348_esl10_step0.2 | complete | -0.087811 | pass/pass/pass | 482.2470 | 199.0656 / False | 4.699 / 614.706 / 765.439 |
| F6_T27_S4_v198_i-20_d0_dt443_esl1.06_step0.2 | complete | 0.025309 | pass/pass/pass | 459.8062 | 198.8790 / False | 6.195 / 612.131 / 744.358 |
| F6_T27_S4_v198_i-20_d0_dt443_esl10_step0.2 | complete | 0.458435 | pass/pass/pass | 478.1086 | 198.6799 / False | 6.192 / 601.346 / 755.537 |
| F6_T27_S4_v198_i-20_d1_dt443_esl1.06_step0.2 | complete | -0.688940 | pass/pass/pass | 437.6824 | 198.8827 / False | 6.203 / 630.605 / 749.443 |
| F6_T27_S4_v198_i-20_d1_dt443_esl10_step0.2 | complete | -0.110840 | pass/pass/pass | 481.5083 | 198.6543 / False | 6.204 / 614.354 / 766.647 |
| F6_T100_S1_v170_i37_d0_dt307_esl1.06_step0.2 | complete | -1.079323 | pass/pass/pass | 193.7263 | -0.7815 / True | 37.055 / 18.023 / 63.130 |
| F6_T100_S1_v170_i37_d0_dt307_esl10_step0.2 | complete | -1.241549 | pass/pass/pass | 197.1644 | -0.7721 / True | 38.126 / 18.034 / 66.303 |
| F6_T100_S1_v170_i37_d1_dt307_esl1.06_step0.2 | complete | -1.395191 | pass/pass/pass | 194.4377 | -0.7851 / True | 37.205 / 18.036 / 63.731 |
| F6_T100_S1_v170_i37_d1_dt307_esl10_step0.2 | complete | -1.469880 | pass/pass/pass | 198.0153 | -0.7744 / True | 38.327 / 18.053 / 67.195 |
| F6_T100_S1_v170_i37_d0_dt348_esl1.06_step0.2 | complete | -1.080479 | pass/pass/pass | 193.7263 | -0.7684 / True | 37.833 / 17.991 / 63.652 |
| F6_T100_S1_v170_i37_d0_dt348_esl10_step0.2 | complete | -1.243105 | pass/pass/pass | 197.1644 | -0.7824 / True | 39.095 / 17.985 / 66.619 |
| F6_T100_S1_v170_i37_d1_dt348_esl1.06_step0.2 | complete | -1.398994 | pass/pass/pass | 194.4377 | -0.7649 / True | 38.096 / 18.003 / 64.586 |
| F6_T100_S1_v170_i37_d1_dt348_esl10_step0.2 | complete | -1.470167 | pass/pass/pass | 198.0153 | -0.7820 / True | 39.368 / 17.996 / 67.485 |
| F6_T100_S1_v170_i37_d0_dt443_esl1.06_step0.2 | complete | -1.083858 | pass/pass/pass | 193.7263 | -0.7663 / True | 39.661 / 17.945 / 67.217 |
| F6_T100_S1_v170_i37_d0_dt443_esl10_step0.2 | complete | -1.248595 | pass/pass/pass | 197.1644 | -0.7707 / True | 41.266 / 17.947 / 69.557 |
| F6_T100_S1_v170_i37_d1_dt443_esl1.06_step0.2 | complete | -1.403688 | pass/pass/pass | 194.4377 | -0.7658 / True | 40.197 / 17.942 / 68.313 |
| F6_T100_S1_v170_i37_d1_dt443_esl10_step0.2 | complete | -1.474964 | pass/pass/pass | 198.0153 | -0.7694 / True | 41.774 / 17.941 / 70.711 |
| F6_T100_S1_v198_i37_d0_dt307_esl1.06_step0.2 | complete | -1.081659 | pass/pass/pass | 219.4219 | -0.7670 / True | 38.269 / 18.029 / 64.463 |
| F6_T100_S1_v198_i37_d0_dt307_esl10_step0.2 | complete | -1.239562 | pass/pass/pass | 217.5221 | -0.7588 / True | 37.661 / 18.016 / 64.592 |
| F6_T100_S1_v198_i37_d1_dt307_esl1.06_step0.2 | complete | -1.394320 | pass/pass/pass | 220.5798 | -0.7711 / True | 38.529 / 18.046 / 65.376 |
| F6_T100_S1_v198_i37_d1_dt307_esl10_step0.2 | complete | -1.468028 | pass/pass/pass | 218.9030 | -0.7591 / True | 37.960 / 18.040 / 65.651 |
| F6_T100_S1_v198_i37_d0_dt348_esl1.06_step0.2 | complete | -1.083849 | pass/pass/pass | 219.4219 | -0.7792 / True | 39.003 / 17.988 / 64.673 |
| F6_T100_S1_v198_i37_d0_dt348_esl10_step0.2 | complete | -1.241426 | pass/pass/pass | 217.5221 | -0.7835 / True | 38.539 / 17.993 / 65.353 |
| F6_T100_S1_v198_i37_d1_dt348_esl1.06_step0.2 | complete | -1.396510 | pass/pass/pass | 220.5798 | -0.7775 / True | 39.343 / 17.997 / 65.523 |
| F6_T100_S1_v198_i37_d1_dt348_esl10_step0.2 | complete | -1.470084 | pass/pass/pass | 218.9030 | -0.7848 / True | 38.891 / 18.006 / 66.246 |
| F6_T100_S1_v198_i37_d0_dt443_esl1.06_step0.2 | complete | -1.086185 | pass/pass/pass | 219.4219 | -0.7683 / True | 40.618 / 17.937 / 67.847 |
| F6_T100_S1_v198_i37_d0_dt443_esl10_step0.2 | complete | -1.246533 | pass/pass/pass | 217.5221 | -0.7774 / True | 40.235 / 17.946 / 67.716 |
| F6_T100_S1_v198_i37_d1_dt443_esl1.06_step0.2 | complete | -1.401702 | pass/pass/pass | 220.5798 | -0.7663 / True | 41.263 / 17.933 / 69.134 |
| F6_T100_S1_v198_i37_d1_dt443_esl10_step0.2 | complete | -1.473679 | pass/pass/pass | 218.9030 | -0.7774 / True | 40.800 / 17.940 / 68.774 |
| F6_T100_S1_v280_i37_d0_dt307_esl1.06_step0.2 | complete | -1.102808 | pass/pass/pass | 352.6350 | -0.7232 / True | 64.967 / 18.120 / 106.167 |
| F6_T100_S1_v280_i37_d0_dt307_esl10_step0.2 | complete | -1.266475 | pass/pass/pass | 350.0272 | -0.7192 / True | 62.677 / 18.076 / 108.597 |
| F6_T100_S1_v280_i37_d1_dt307_esl1.06_step0.2 | complete | -1.436563 | pass/pass/pass | 354.3662 | -0.7286 / True | 66.474 / 18.155 / 109.946 |
| F6_T100_S1_v280_i37_d1_dt307_esl10_step0.2 | complete | -1.509097 | pass/pass/pass | 352.0873 | -0.7139 / True | 63.848 / 18.101 / 112.522 |
| F6_T100_S1_v280_i37_d0_dt348_esl1.06_step0.2 | complete | -1.105025 | pass/pass/pass | 352.6350 | -0.8118 / True | 69.148 / 18.052 / 107.200 |
| F6_T100_S1_v280_i37_d0_dt348_esl10_step0.2 | complete | -1.272637 | pass/pass/pass | 350.0272 | -0.7906 / True | 68.769 / 18.096 / 111.036 |
| F6_T100_S1_v280_i37_d1_dt348_esl1.06_step0.2 | complete | -1.438667 | pass/pass/pass | 354.3662 | -0.8149 / True | 70.633 / 18.056 / 110.934 |
| F6_T100_S1_v280_i37_d1_dt348_esl10_step0.2 | complete | -1.515822 | pass/pass/pass | 352.0873 | -0.7969 / True | 70.251 / 18.113 / 115.103 |
| F6_T100_S1_v280_i37_d0_dt443_esl1.06_step0.2 | complete | -1.109793 | pass/pass/pass | 352.6350 | -0.7687 / True | 76.151 / 17.954 / 110.248 |
| F6_T100_S1_v280_i37_d0_dt443_esl10_step0.2 | complete | -1.278649 | pass/pass/pass | 350.0272 | -0.8001 / True | 76.539 / 17.988 / 114.009 |
| F6_T100_S1_v280_i37_d1_dt443_esl1.06_step0.2 | complete | -1.450405 | pass/pass/pass | 354.3662 | -0.7611 / True | 78.730 / 17.951 / 115.005 |
| F6_T100_S1_v280_i37_d1_dt443_esl10_step0.2 | complete | -1.523927 | pass/pass/pass | 352.0873 | -0.8037 / True | 78.975 / 17.982 / 118.684 |
| F6_T100_S2_v280_i71_d0_dt307_esl1.06_step0.2 | complete | -0.295252 | pass/pass/pass | 382.4289 | -0.9111 / True | 249.997 / 43.409 / 328.910 |
| F6_T100_S2_v280_i71_d0_dt307_esl10_step0.2 | complete | -0.632098 | pass/pass/pass | 373.1262 | -0.9476 / True | 235.867 / 43.366 / 318.304 |
| F6_T100_S2_v280_i71_d1_dt307_esl1.06_step0.2 | complete | -0.881906 | pass/pass/pass | 364.4091 | -0.9133 / True | 202.981 / 43.404 / 274.227 |
| F6_T100_S2_v280_i71_d1_dt307_esl10_step0.2 | complete | -1.005225 | pass/pass/pass | 359.6478 | -0.9528 / True | 188.738 / 43.361 / 258.860 |
| F6_T100_S2_v280_i71_d0_dt348_esl1.06_step0.2 | complete | -0.301137 | pass/pass/pass | 382.4289 | -0.9413 / True | 258.475 / 43.488 / 333.664 |
| F6_T100_S2_v280_i71_d0_dt348_esl10_step0.2 | complete | -0.639039 | pass/pass/pass | 373.1262 | -0.9028 / True | 244.087 / 43.455 / 323.502 |
| F6_T100_S2_v280_i71_d1_dt348_esl1.06_step0.2 | complete | -0.887774 | pass/pass/pass | 364.4091 | -0.9490 / True | 208.600 / 43.409 / 278.803 |
| F6_T100_S2_v280_i71_d1_dt348_esl10_step0.2 | complete | -1.010827 | pass/pass/pass | 359.6478 | -0.9153 / True | 193.285 / 43.377 / 263.947 |
| F6_T100_S2_v280_i71_d0_dt443_esl1.06_step0.2 | complete | -0.305976 | pass/pass/pass | 382.4289 | -0.9730 / True | 267.016 / 43.140 / 340.175 |
| F6_T100_S2_v280_i71_d0_dt443_esl10_step0.2 | complete | -0.647172 | pass/pass/pass | 373.1262 | -0.9550 / True | 253.929 / 43.256 / 330.936 |
| F6_T100_S2_v280_i71_d1_dt443_esl1.06_step0.2 | complete | -0.891480 | pass/pass/pass | 364.4091 | -0.9640 / True | 214.673 / 43.066 / 285.107 |
| F6_T100_S2_v280_i71_d1_dt443_esl10_step0.2 | complete | -1.016414 | pass/pass/pass | 359.6478 | -0.9460 / True | 199.322 / 43.149 / 271.105 |
| F6_T100_S4_v198_i-20_d0_dt348_esl1.06_step0.2 | complete | -0.043883 | pass/pass/pass | 458.7366 | 198.1904 / False | 4.308 / 611.558 / 739.511 |
| F6_T100_S4_v198_i-20_d0_dt348_esl10_step0.2 | complete | 0.283947 | pass/pass/pass | 472.5117 | 199.3331 / False | 4.305 / 602.976 / 750.493 |
| F6_T100_S4_v198_i-20_d1_dt348_esl1.06_step0.2 | complete | -0.702685 | pass/pass/pass | 435.8592 | 198.2438 / False | 4.310 / 631.481 / 747.502 |
| F6_T100_S4_v198_i-20_d1_dt348_esl10_step0.2 | complete | -0.172005 | pass/pass/pass | 474.8672 | 199.0101 / False | 4.310 / 616.777 / 762.828 |
| F6_T100_S4_v198_i-20_d0_dt443_esl1.06_step0.2 | complete | -0.116607 | pass/pass/pass | 456.1220 | 198.7584 / False | 5.595 / 613.129 / 741.557 |
| F6_T100_S4_v198_i-20_d0_dt443_esl10_step0.2 | complete | 0.266319 | pass/pass/pass | 473.2326 | 198.5404 / False | 5.593 / 603.112 / 752.180 |
| F6_T100_S4_v198_i-20_d1_dt443_esl1.06_step0.2 | complete | -0.676304 | pass/pass/pass | 437.7129 | 198.7914 / False | 5.598 / 630.689 / 749.082 |
| F6_T100_S4_v198_i-20_d1_dt443_esl10_step0.2 | complete | -0.183785 | pass/pass/pass | 475.2766 | 198.4845 / False | 5.598 / 616.142 / 763.690 |
| F6_T150_S1_v170_i37_d0_dt307_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d0_dt307_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d1_dt307_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d1_dt307_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d0_dt348_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d0_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d1_dt348_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d1_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d0_dt443_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d0_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d1_dt443_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v170_i37_d1_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d0_dt307_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d0_dt307_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d1_dt307_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d1_dt307_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d0_dt348_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d0_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d1_dt348_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d1_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d0_dt443_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d0_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d1_dt443_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v198_i37_d1_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d0_dt307_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d0_dt307_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d1_dt307_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d1_dt307_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d0_dt348_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d0_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d1_dt348_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d1_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d0_dt443_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d0_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d1_dt443_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S1_v280_i37_d1_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d0_dt307_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d0_dt307_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d1_dt307_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d1_dt307_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d0_dt348_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d0_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d1_dt348_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d1_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d0_dt443_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d0_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d1_dt443_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S2_v280_i71_d1_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S4_v198_i-20_d0_dt348_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S4_v198_i-20_d0_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S4_v198_i-20_d1_dt348_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S4_v198_i-20_d1_dt348_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S4_v198_i-20_d0_dt443_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S4_v198_i-20_d0_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S4_v198_i-20_d1_dt443_esl1.06_step0.2 | indeterminate | — | — | — | — | — |
| F6_T150_S4_v198_i-20_d1_dt443_esl10_step0.2 | indeterminate | — | — | — | — | — |
