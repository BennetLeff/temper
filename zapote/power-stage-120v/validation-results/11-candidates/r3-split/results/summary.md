## Worst S4 cases (top 3 die VDS + top 3 off-gate per leg), dL added in series with both gate ports

| dL (nH) | leg A die VDS (V) | leg A off-gate (V) | leg B die VDS (V) | leg B off-gate (V) |
|---:|---:|---:|---:|---:|
| 0 | 467.6 | 0.694 | 490.2 | 1.145 |
| 3 | 464.9 | 0.490 | 484.8 | 0.990 |
| 6 | 462.8 | 0.289 | 478.7 | 0.816 |
| 10 | 460.7 | 0.035 | 468.8 | 0.570 |
| 20 | 457.8 | -0.503 | 441.6 | -0.032 |
| 40 | 459.1 | -0.792 | 416.1 | -0.646 |

## Whole decision + startup set (S1/S2/S4/S5, 27/100/150 C, both legs), dL in both gate ports

| leg | dL (nH) | cases | indeterminate | max die VDS (V) | VDS limit fails | max off-gate (V) | 1.9 V fails | ZVS fails (S1 only) | worst |VGS| (V) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 10 | 252 | 0 | 461.7 | 0 | 0.238 | 0 | 0 | 15.02 |
| A | 20 | 252 | 0 | 460.2 | 0 | 0.030 | 0 | 0 | 15.02 |
| B | 10 | 252 | 0 | 471.6 | 0 | 0.570 | 0 | 0 | 15.02 |
| B | 20 | 252 | 0 | 456.0 | 0 | 0.079 | 0 | 0 | 15.02 |

Base (dL = 0) S1 ZVS flags come from the committed results; S1 rows with `base_zvs` false: 0 of 96

L at the driver output node instead of the gate port (71 matched cases, 1 indeterminate): max |dVDS| = 0.169 V, max |d off-gate| = 0.0011 V

## Connector loop inductance added per gate path (computed)

| connector | signal/return pairs in parallel | connector loop (nH) | vias (nH) | breakout stubs 2x10 mm (nH) | total (nH) |
|---|---:|---:|---:|---:|---:|
| 2.54 mm square-pin header/socket (0.64 sq), mated path 9 mm | 1 | 7.04 | 2.4 | 5.02 | 14.46 |
| 2.54 mm square-pin header/socket (0.64 sq), mated path 9 mm | 2 | 3.29 | 1.2 | 2.51 | 7.0 |
| 2.54 mm square-pin header/socket (0.64 sq), mated path 9 mm | 3 | 2.12 | 0.8 | 1.67 | 4.6 |
| 2.54 mm square-pin header/socket (0.64 sq), mated path 9 mm | 4 | 1.56 | 0.6 | 1.25 | 3.42 |
| 2.00 mm header (0.5 sq), 7 mm | 1 | 5.49 | 2.35 | 5.02 | 12.86 |
| 2.00 mm header (0.5 sq), 7 mm | 2 | 2.57 | 1.18 | 2.51 | 6.25 |
| 2.00 mm header (0.5 sq), 7 mm | 3 | 1.66 | 0.78 | 1.67 | 4.12 |
| 2.00 mm header (0.5 sq), 7 mm | 4 | 1.22 | 0.59 | 1.25 | 3.06 |
| 1.27 mm header (0.4 sq), 6 mm | 1 | 4.3 | 2.23 | 5.02 | 11.55 |
| 1.27 mm header (0.4 sq), 6 mm | 2 | 1.99 | 1.12 | 2.51 | 5.62 |
| 1.27 mm header (0.4 sq), 6 mm | 3 | 1.28 | 0.74 | 1.67 | 3.69 |
| 1.27 mm header (0.4 sq), 6 mm | 4 | 0.94 | 0.56 | 1.25 | 2.75 |
| 0.8 mm edge-rate class (contact 0.3x0.5), 5.97 mm stack | 1 | 3.34 | 2.07 | 5.02 | 10.43 |
| 0.8 mm edge-rate class (contact 0.3x0.5), 5.97 mm stack | 2 | 1.51 | 1.04 | 2.51 | 5.05 |
| 0.8 mm edge-rate class (contact 0.3x0.5), 5.97 mm stack | 3 | 0.95 | 0.69 | 1.67 | 3.31 |
| 0.8 mm edge-rate class (contact 0.3x0.5), 5.97 mm stack | 4 | 0.69 | 0.52 | 1.25 | 2.46 |
