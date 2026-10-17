| tank A | I part A | vendor ratio 35 kHz | gate strict (pads28 / scaled) | gate + gap (pads28 / scaled) |
|---|---|---|---|---|
| 18 | 3.897 | 0.629 | 0.785 / 0.785 | 0.559 / 0.559 |
| 20 | 4.33 | 0.698 | 0.872 / 0.872 | 0.621 / 0.621 |
| 22 | 4.763 | 0.768 | 0.959 / 0.959 | 0.683 / 0.683 |
| 24 | 5.196 | 0.838 | 1.046 / 1.046 | 0.745 / 0.745 |
| 26 | 5.629 | 0.908 | 1.134 / 1.134 | 0.807 / 0.807 |
| 28 | 6.062 | 0.978 | 1.221 / 1.221 | 0.869 / 0.869 |

Highest step with gate <= 1.00 and vendor <= 0.85: pads28/strict 22.0, pads28/gap 24.0, scaled/strict 22.0, scaled/gap 24.0
Highest step, gate only: pads28/strict 22.0, pads28/gap 28.0, scaled/strict 22.0, scaled/gap 28.0
Vendor ratio 0.85 is reached at tank 24.34 A (current only; no flow term).

28 A velocity along x for gate 1.00 (pads held at the 3.07 m/s solve; bulk rise 3.7 K x 3.07 / v):
- strict @61 h20: gate at 3.07 m/s 1.221, v for 1.00 = 6.17 (conservative)
- strict @55 h15: gate at 3.07 m/s 1.218, v for 1.00 = 6.12 (conservative)
- gap @61 h20: gate at 3.07 m/s 0.869, v for 1.00 = 1.19 (BELOW 3.07: pads held, not conservative)
- gap @55 h15: gate at 3.07 m/s 0.869, v for 1.00 = 1.19 (BELOW 3.07: pads held, not conservative)

Control (strict 28 A = bank_air_cand gate): {'bank_air_cand_gate': 1.221, 'here': 1.221, 'pass': True}
