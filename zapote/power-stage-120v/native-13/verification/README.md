# Native-13 verification, 2026-09-27: detector part fixes

Native-13 is native-11 with two part-number swaps from
[validation task 02](../../validation-results/02-protection-timing/README.md),
approved by the owner:

- D4/D5: BAT54H,115 → **BAS116H,115**. It's a low-leakage clamp; the old part's
  hot leakage widened the CT trip band to 45–65 A at ~85 °C.
- R14/R6 → **100 Ω** (RC0603FR-07100RL), and R16/R8 → **1 kΩ**
  (RC0603FR-071KL). The PERMIT → DIS link drops from ~3.5 µs to ~0.35 µs
  worst case, and the total shutdown chain from 4.1–4.5 µs to 1.0–1.3 µs.

Native-12 is the placement. Against native-10, only these six parts' MPN and
Value fields differ; every pose, footprint and pad is identical.

Electrical board SHA-256: `ce1cf6361d1f30a8345d58b01b3511c695c7212d2c621808bc6dabe5b73960b6`.
The active board is the [presentation revision](presentation/) (labels and 3D models),
`8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129`, and its
copper is identical to the electrical board.

| Check | Result |
| --- | --- |
| Full DRC, fill + three repeats | 0 copper findings, 0 schematic mismatch; 28 library + 3 L1/J3 silk overlaps; board stable |
| Opens | Only the intended R5 Kelvin split; pad clusters identical to native-11 |
| Copper vs native-11 | Pads, tracks and vias identical. Seven refilled zone polygons differ by ≤ 0.10 mm² (largest: In1 HV_RET), from KiCad's refill; power screens unchanged (0.886 / 0.457) |
| Barrier | 0 (Rust) and 0 (pinned oracle) |
| Parity / copper identity / stackup / JLCPCB / hardware surface | PASS / PASS / pass / PASS / 0 hits |
| Presentation board | Copper identical; the same DRC counts and gates |
| Source audit | 53/53; board tests 44/44 (retargeted to native-12/13) |
