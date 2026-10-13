# Benchmark board: native-21 stage 19c (2026-10-13)

Stage 19c is the reference that every simplification or improvement candidate is graded against (owner direction,
2026-10-13). A candidate replaces it only if `native-21/layout/gates/scorecard.py` accepts it against this card.

## Identity

| Item | Value |
|---|---|
| Tag | `native21s19c` |
| Routed board SHA-256 | `3d3a2c69c07a210262f0dc66789a2631e29370f6816c45869a7dea1813460d92` |
| Gerber ZIP SHA-256 | `13a89376905c94bcb38aa581233de73ad994fde5824e4367c65cdbfd2bb158de` |
| Frozen netlist | unchanged from 19b (`8a7e1c4a…`); audit.rs PASS, 80/80 tests |
| Rebuild | `sh native-21/layout/incr_iter.sh native-21/layout/copper.json - OUTDIR` at the benchmark commit |
| Scorecard | [`scorecard-native21s19c.json`](scorecard-native21s19c.json) (19b's, for reference: [`scorecard-native21s19b.json`](scorecard-native21s19b.json)) |

## What 19c changed against 19b

Only rubric finding F9 needed copper (`../09-rubric-review-s19b/RESOLUTION-PLAN.md`).

- **C7 moved under U1's VCCI/GND pins.** C7 is leg A's VCCI cap; the move matches what stage 19 did with C14 under U2. Both of leg A's PWM input layer changes now have a v3v3–selv_gnd capacitor within 3 mm: `pwm_ha` 7.59 → 2.11 mm and `pwm_la` 5.11 → 1.84 mm.
- **`return_path19.py` asserts every PWM input and ct_zc.** On 19b the gate fails as a negative control.
- **permit, bus_fault and bias_*_bad stay reported, not asserted.** These lines change state only at start or stop, and any disturbance can only disable the drivers. Their runs over the plane void at the U32/U33 isolation gap are recorded in DECISIONS 19c.
- **No part was added.** The BOM and placements are unchanged; vias went from 753 to 751.
- **TP15 (`pwm_la`) moved** to (81.2, 104.3), where it shares a reference test point.

Every other gate is identical to 19b:
- DRC 0 / 0 / parity 0, with library tables too;
- barrier and RES_A outer 0;
- Rust gate 0 over 5,837 items;
- D5 8.047 / 8.507 mm;
- fit 0;
- DFM PASS;
- Gerber review PASS;
- CPL audit 280 / 10 / 47;
- bypass 11/11;
- PI PASS;
- Kelvin band 67.72–116.44 A;
- B3 28 A h25 peak 136.0 °C.

## Known deficits carried by the benchmark

The desk studies on 13 October found the following. Each is a scorecard metric, so a candidate that fixes one scores
better on it.

| Metric (scorecard) | Benchmark | Target | Source | What fixes it |
|---|---|---|---|---|
| `fuse_copper_fusing_ratio`: narrowest series copper's fusing I²t ÷ F1 clearing I²t | 0.208 (R5→J10 neck, 1.17 mm, 355 A²s vs 1,710 A²s) | ≥ 2 | `02-protection-timing/shoot-through-f1/` | Widen the HV_RET / BUS_P necks. BR1 (510 A²s) can't survive any 25 A fuse, so it is sacrificial (DECISIONS 22). |
| `leakage_touch_mA`: touch current, PE open, 132 V | 0.974 mA | ≤ 0.25 mA (50 % of UL 1026's 0.5 mA, clause unconfirmed) | `07-conducted-emi/leakage/` | Less Y capacitance (the D-22 module's 6.9 nF/line dominates), with the EMI rerun |
| F2 breaking capacity vs a fault at J11 | FAIL: 1.1–3.6 kA prospective vs 200 A | ≥ prospective | `02-protection-timing/f2-coordination/` | A 1,500 A 5×20 in clips, or remove the board's blower tap |
| `cmti_gate_ratio_min`: driver CMTI ÷ 95 V/ns | 1.32 (UCC21550, 125 V/ns) | ≥ 1.5 | `06-controller-interface/cmti/` | A higher-CMTI driver, or bench-measured dv/dt ≤ 83 V/ns |
| `zero_stock_lines` / `single_source_lines` | 10 / 17 | lower | `08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13.*` | Swap UCC21550 (no stock until 2027-06), ISO7710 ×4, L1, … |
| `parts_usd_at_500` | $231.94 (parts only) | lower | same | Simplification candidates |

Also still open, and not board metrics:
- the loop re-extraction (F7, remote FEM);
- the pickup rerun (F8);
- F12 (B3 with L1 at 15 A, which needs a B3 input change);
- the EMI module parts (F10);
- the supplier questions (F1 CTI, TDK, Coilcraft, Mersen).

## Acceptance rule (fixed 2026-10-13, before any candidate)

A candidate is ACCEPTED over the benchmark only if all three hold:

1. **Every gate passes:** DRC, barrier, RES_A, DFM, return path, bypass, PI, D5, fit and audit.
2. **No performance metric is worse than the benchmark beyond its tolerance.** The tolerances are in `scorecard.PERF`. For example, D5 allows 0 mm, B3 allows 1 °C and EMI allows 0.5 dB.
3. **It is cheaper or simpler, or better.**
   - Cheaper or simpler means lower on at least one of parts cost at 500, BOM lines, placements, JLC extended lines, hand/consigned lines or zero-stock lines.
   - Better means strictly better on at least one performance metric, and not costlier on parts cost, lines, extended lines or hand lines without that.

The owner's goal is a board that is both cheaper/simpler **and** better. The rule above is the floor. Candidates that manage both rank first.

Score a candidate right after its own `chain.sh` run, and save the card:

    python3 native-21/layout/gates/scorecard.py TAG BUILDDIR --audit PASS --json validation-results/10-benchmark/scorecard-TAG.json
    python3 native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-TAG.json \
        --compare validation-results/10-benchmark/scorecard-native21s19c.json

Controls run 2026-10-13: 19c vs 19b gives ACCEPT (better `return_path_open_changes`, 39 vs 41, at equal cost), and 19b vs 19c gives REJECT.
