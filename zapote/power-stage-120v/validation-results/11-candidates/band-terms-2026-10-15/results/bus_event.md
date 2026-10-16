## A. Tank state at gate-off (bank-ov grid; buses 198 / 280 / 287.62 / 323.04 V)

| trip level | runs | max I_off (A) | 1/2 L_max I_off^2 (J) | max tank energy 1/2 L i^2 + 1/2 C v^2 (J) | run |
|---|---:|---:|---:|---:|---|
| control 118.74 A, 198/280 V | | 155.45 | 0.8838 | 0.8964 | |
| CT band top 76.09 A (CT path alive; single fault) | 2787 | 110.18 | 0.444 | 0.4857 | Lmax_Cmin (max Z0), R 0.05, bus 323.04, 27740 Hz, i 108.8 A, v_C -486 V |
| s47 shunt top 119.09 A (bands-s47.md:24) | 2673 | 155.73 | 0.887 | 0.8972 | Lmax_Cmax, R 0.15, bus 280.0, 25087 Hz, i -151.0 A, v_C 479 V |
| shunt top + CMRR R1 (Q1 HOT5) 121.98 A | 2654 | 159.68 | 0.9326 | 0.9459 | Lmax_Cmax, R 0.15, bus 287.62, 25092 Hz, i -154.9 A, v_C 497 V |
| shunt top + CMRR R1 (physical HOT5) 122.83 A | 2653 | 161.02 | 0.9484 | 0.9642 | Lmax_Cmin (max Z0), R 0.15, bus 323.04, 26353 Hz, i -158.2 A, v_C 466 V |

## B. Closed form, V0 287.62 V, 500 uH / 30 A, C 14.9 uF, no clamp

| E_t basis | E_t (J) | Vpk (V) | C12 fam. /1000 (0.5) | C5C6 /750 (0.8) | C5C6 hot /570 (0.8) | C38-41 hot /687.5 (0.8) | BR1 /1000 (0.8) | 2EDR /1767 (0.5) | R3R4 V/2 /400 (1.0) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stale E_t 0.475 J (ALT-D3, stage 13b) | 0.475 | 451.63 | 0.452 | 0.602 | 0.792 | 0.657 | 0.452 | 0.256 | 0.565 |
| bank-ov 0.884 J (155.4 A, 73.15 uH) | 0.8833 | 503.0 | 0.503 **X** | 0.671 | 0.882 **X** | 0.732 | 0.503 | 0.285 | 0.629 |
| CT band top 76.09 A (CT path alive; single fault): max tank energy | 0.4857 | 452.99 | 0.453 | 0.604 | 0.795 | 0.659 | 0.453 | 0.256 | 0.566 |
| s47 shunt top 119.09 A (bands-s47.md:24): max tank energy | 0.8972 | 504.71 | 0.505 **X** | 0.673 | 0.885 **X** | 0.734 | 0.505 | 0.286 | 0.631 |
| shunt top + CMRR R1 (Q1 HOT5) 121.98 A: max tank energy | 0.9459 | 510.67 | 0.511 **X** | 0.681 | 0.896 **X** | 0.743 | 0.511 | 0.289 | 0.638 |
| shunt top + CMRR R1 (physical HOT5) 122.83 A: max tank energy | 0.9642 | 512.89 | 0.513 **X** | 0.684 | 0.900 **X** | 0.746 | 0.513 | 0.290 | 0.641 |

## C. OVP delay (line ring through the U7 filter, gate-off T_D after the filtered crossing)

| tau | lag (us) | V0' (V) | I0' (A) | overshoot (V) | naive 30 A x t (V) | ring peak alone (V) |
|---|---:|---:|---:|---:|---:|---:|
| nominal 15.67 k x 1 nF (15.668 us) | 15.766 | 321.71 | 26.139 | 34.09 | 36.31 | 393.53 |
| max (R +1 % / +0.1 %, C27 +5 %) (16.469 us) | 16.526 | 323.04 | 25.95 | 35.42 | 37.84 | 393.53 |

| stacked case | E_t (J) | coherent Vpk (V) | naive Vpk (V) | ratios (coherent) |
|---|---:|---:|---:|---|
| nominal 15.67 k x 1 nF | E_t 0.475 J (stale) | 0.475 | 457.68 | 472.68 | 0.458 | 0.610 | 0.803 **X** | 0.666 | 0.458 | 0.259 | 0.572 |
| nominal 15.67 k x 1 nF | E_t at the CT top 76.09 A | 0.4857 | 459.11 | 474.04 | 0.459 | 0.612 | 0.805 **X** | 0.668 | 0.459 | 0.260 | 0.574 |
| nominal 15.67 k x 1 nF | E_t at 119.09 A | 0.8972 | 512.11 | 524.77 | 0.512 **X** | 0.683 | 0.898 **X** | 0.745 | 0.512 | 0.290 | 0.640 |
| nominal 15.67 k x 1 nF | E_t at the CMRR top | 0.9459 | 518.14 | 530.57 | 0.518 **X** | 0.691 | 0.909 **X** | 0.754 | 0.518 | 0.293 | 0.648 |
| max (R +1 % / +0.1 %, C27 +5 %) | E_t 0.475 J (stale) | 0.475 | 457.9 | 473.62 | 0.458 | 0.611 | 0.803 **X** | 0.666 | 0.458 | 0.259 | 0.572 |
| max (R +1 % / +0.1 %, C27 +5 %) | E_t at the CT top 76.09 A | 0.4857 | 459.33 | 474.97 | 0.459 | 0.612 | 0.806 **X** | 0.668 | 0.459 | 0.260 | 0.574 |
| max (R +1 % / +0.1 %, C27 +5 %) | E_t at 119.09 A | 0.8972 | 512.38 | 525.65 | 0.512 **X** | 0.683 | 0.899 **X** | 0.745 | 0.512 | 0.290 | 0.640 |
| max (R +1 % / +0.1 %, C27 +5 %) | E_t at the CMRR top | 0.9459 | 518.41 | 531.45 | 0.518 **X** | 0.691 | 0.909 **X** | 0.754 | 0.518 | 0.293 | 0.648 |

## D. Time-domain gate-off event (clamp V-I lines are assumptions; see docstring)

| case | Vbus pk (V) | clamp I pk (A) | clamp E (J) | t>half (us) | pulse ratio exp / rect (per device) | ratios |
|---|---:|---:|---:|---:|---|---|
| max-E run at 119.09 A | V0 287.62 V, I0 30 A | clamp none | 498.97 | 0.0 | 0.0 |  |  /  | 0.499 | 0.665 | 0.875 **X** | 0.726 | 0.499 | 0.282 | 0.624 |
| max-E run at 119.09 A | V0 287.62 V, I0 30 A | clamp onset VBR min 335.2 V (low line) | 406.32 | 70.15 | 1.0886 | 37.5 | 0.2237 / 0.3389 | 0.406 | 0.542 | 0.713 | 0.591 | 0.406 | 0.230 | 0.508 |
| max-E run at 119.09 A | V0 287.62 V, I0 30 A | clamp onset 368.72 V (Littelfuse VBR max) (high line) | 421.95 | 70.45 | 0.8973 | 28.89 | 0.2113 / 0.3202 | 0.422 | 0.563 | 0.740 | 0.614 | 0.422 | 0.239 | 0.527 |
| max-E run at 119.09 A | V0 287.62 V, I0 30 A | clamp high line hot, x(1 + 0.1 %/K x 48 K) at 73 C | 435.91 | 62.5 | 0.772 | 27.89 | 0.1911 / 0.2896 | 0.436 | 0.581 | 0.765 | 0.634 | 0.436 | 0.247 | 0.545 |
| max-E run at 119.09 A | V0 287.62 V, I0 30 A | clamp near-ideal at VBR min -10 C, 323 V, 129.8 A at 329.5 V (bounds the clamp current) | 330.16 | 142.97 | 1.2779 | 24.24 | 0.314 / 0.4757 | 0.330 | 0.440 | 0.579 | 0.480 | 0.330 | 0.187 | 0.413 |
| max-E run at 119.09 A | V0 323.04 V, I0 25.95 A (OVP delay) | clamp none | 505.72 | 0.0 | 0.0 |  |  /  | 0.506 **X** | 0.674 | 0.887 **X** | 0.736 | 0.506 | 0.286 | 0.632 |
| max-E run at 119.09 A | V0 323.04 V, I0 25.95 A (OVP delay) | clamp onset VBR min 335.2 V (low line) | 407.86 | 71.67 | 1.1014 | 41.96 | 0.2394 / 0.3627 | 0.408 | 0.544 | 0.716 | 0.593 | 0.408 | 0.231 | 0.510 |
| max-E run at 119.09 A | V0 323.04 V, I0 25.95 A (OVP delay) | clamp onset 368.72 V (Littelfuse VBR max) (high line) | 422.84 | 71.62 | 0.9202 | 31.87 | 0.2234 / 0.3386 | 0.423 | 0.564 | 0.742 | 0.615 | 0.423 | 0.239 | 0.528 |
| max-E run at 119.09 A | V0 323.04 V, I0 25.95 A (OVP delay) | clamp high line hot, x(1 + 0.1 %/K x 48 K) at 73 C | 438.43 | 65.68 | 0.792 | 25.03 | 0.1939 / 0.2938 | 0.438 | 0.585 | 0.769 | 0.638 | 0.438 | 0.248 | 0.548 |
| max-E run at 119.09 A | V0 323.04 V, I0 25.95 A (OVP delay) | clamp near-ideal at VBR min -10 C, 323 V, 129.8 A at 329.5 V (bounds the clamp current) | 331.37 | 167.05 | 1.2919 | 25.68 | 0.3763 / 0.5702 | 0.331 | 0.442 | 0.581 | 0.482 | 0.331 | 0.188 | 0.414 |
| max-E run at the CMRR top | V0 287.62 V, I0 30 A | clamp none | 505.6 | 0.0 | 0.0 |  |  /  | 0.506 **X** | 0.674 | 0.887 **X** | 0.735 | 0.506 | 0.286 | 0.632 |
| max-E run at the CMRR top | V0 287.62 V, I0 30 A | clamp onset VBR min 335.2 V (low line) | 408.71 | 72.51 | 1.1341 | 38.0 | 0.2337 / 0.3541 | 0.409 | 0.545 | 0.717 | 0.595 | 0.409 | 0.231 | 0.511 |
| max-E run at the CMRR top | V0 287.62 V, I0 30 A | clamp onset 368.72 V (Littelfuse VBR max) (high line) | 424.03 | 73.19 | 0.9453 | 29.86 | 0.2234 / 0.3385 | 0.424 | 0.565 | 0.744 | 0.617 | 0.424 | 0.240 | 0.530 |
| max-E run at the CMRR top | V0 287.62 V, I0 30 A | clamp high line hot, x(1 + 0.1 %/K x 48 K) at 73 C | 438.27 | 65.48 | 0.82 | 28.82 | 0.2038 / 0.3088 | 0.438 | 0.584 | 0.769 | 0.637 | 0.438 | 0.248 | 0.548 |
| max-E run at the CMRR top | V0 287.62 V, I0 30 A | clamp near-ideal at VBR min -10 C, 323 V, 129.8 A at 329.5 V (bounds the clamp current) | 330.39 | 147.63 | 1.3214 | 24.33 | 0.3249 / 0.4923 | 0.330 | 0.441 | 0.580 | 0.481 | 0.330 | 0.187 | 0.413 |
| max-E run at the CMRR top | V0 323.04 V, I0 25.95 A (OVP delay) | clamp none | 510.52 | 0.0 | 0.0 |  |  /  | 0.510 **X** | 0.681 | 0.896 **X** | 0.743 | 0.510 | 0.289 | 0.638 |
| max-E run at the CMRR top | V0 323.04 V, I0 25.95 A (OVP delay) | clamp onset VBR min 335.2 V (low line) | 410.21 | 73.99 | 1.1462 | 42.76 | 0.2503 / 0.3793 | 0.410 | 0.547 | 0.720 | 0.597 | 0.410 | 0.232 | 0.513 |
| max-E run at the CMRR top | V0 323.04 V, I0 25.95 A (OVP delay) | clamp onset 368.72 V (Littelfuse VBR max) (high line) | 424.82 | 74.24 | 0.9678 | 32.85 | 0.2354 / 0.3567 | 0.425 | 0.566 | 0.745 | 0.618 | 0.425 | 0.240 | 0.531 |
| max-E run at the CMRR top | V0 323.04 V, I0 25.95 A (OVP delay) | clamp high line hot, x(1 + 0.1 %/K x 48 K) at 73 C | 440.51 | 68.3 | 0.839 | 25.81 | 0.2049 / 0.3105 | 0.441 | 0.587 | 0.773 | 0.641 | 0.441 | 0.249 | 0.551 |
| max-E run at the CMRR top | V0 323.04 V, I0 25.95 A (OVP delay) | clamp near-ideal at VBR min -10 C, 323 V, 129.8 A at 329.5 V (bounds the clamp current) | 331.57 | 171.13 | 1.3357 | 25.79 | 0.3864 / 0.5854 | 0.332 | 0.442 | 0.582 | 0.482 | 0.332 | 0.188 | 0.414 |

Published clamp bound (VC <= 466.8 V for I <= 129.8 A, 25 C): 0.467 | 0.622 | 0.819 **X** | 0.679 | 0.467 | 0.264 | 0.584; hot (+0.1 %/K assumed, 73 C) 489.2 V: 0.489 | 0.652 | 0.858 **X** | 0.712 | 0.489 | 0.277 | 0.612
