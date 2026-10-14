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

**Datasheet ratings (added 2026-10-13, after stage 26).** `ledger_violations` and `ledger_unaudited_safety_power` come from
`native-21/verification/datasheet-ledger/gate.py`. It holds every BOM line against its datasheet limits, approval basis and
worst-case stress from the repo. Both are ratchets with zero tolerance, so a candidate may not add:
- a rating violation;
- a BOM MPN the ledger does not know;
- an unaudited SAFETY/POWER line.

A new part therefore needs a ledger entry before its card can be accepted. The stage-26 card is the first with them: 2 / 2
(J1's 15 A cULus rating and F2's 200 A breaking capacity; the R1/R2 X-cap bleed and the C12–C20 snubber caps are not yet
audited).

The owner's goal is a board that is both cheaper/simpler **and** better. The rule above is the floor. Candidates that manage both rank first.

Score a candidate right after its own `chain.sh` run, and save the card:

    python3 native-21/layout/gates/scorecard.py TAG BUILDDIR --audit PASS --json validation-results/10-benchmark/scorecard-TAG.json
    python3 native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-TAG.json \
        --compare validation-results/10-benchmark/scorecard-native21s19c.json

Controls run 2026-10-13: 19c vs 19b gives ACCEPT (better `return_path_open_changes`, 39 vs 41, at equal cost), and 19b vs 19c gives REJECT.

## Candidates graded so far

| Stage | Change | Verdict | Card |
|---|---|---|---|
| 28 | F2 → Schurter UMT-H 1.5 kA + R130 0.15 Ω limiter (J11 fault ≤ 980 A); OCP nets locked to stage 27 | **ACCEPT** against 19c and 27. Better: ledger violations 1 → 0 (F4 closed; the ledger gate passes). Costs: parts +$0.34, +1 line, +1 placement, +2 Extended, +1 zero-stock (UMT-H at Digi-Key only). | [`scorecard-native21s28.json`](scorecard-native21s28.json) |
| 27 | J1 → Phoenix 1714971 MKDS 5/2-9,5 (UL / CSA group B 30 A); F1 5.65 mm left; mains pours redrawn | **ACCEPT** against 19c and 26. Cheaper: parts $222.28 → $221.82. Better: ledger violations 2 → 1, unaudited SAFETY/POWER 2 → 0. Every other metric identical. | [`scorecard-native21s27.json`](scorecard-native21s27.json) |
| 26 | C126–C129 6SVPC220M → 6SVPC220MV (BOM only) | **ACCEPT** against 19c and 22. Cheaper: parts $223.10 → $222.28; stock 13 → 845 on that line. Performance identical. | [`scorecard-native21s26.json`](scorecard-native21s26.json) |
| 22 | DIS = NAND(PERMIT, BIAS_GOOD); Q1 / Q4, R8 / R16 deleted | **ACCEPT** against 19c and 21b. Cheaper: −4 placements, −1 line (+1 Extended). Better: return-path open changes 39 → 37, OCP pickup 4.78 → 4.17 A. | [`scorecard-native21s22.json`](scorecard-native21s22.json) |
| 21b | Stage 21 plus KELVIN_N under its pour, C30 / C31 beside U6 (F8) | **ACCEPT** against 19c and 21. Better: OCP pickup 8.71 → 4.78 A (gate 6.5 A), Kelvin band +0.05 A, at equal cost. | [`scorecard-native21s21b.json`](scorecard-native21s21b.json) |
| 21 | BR1 feeds the bus directly; J7–J10 removed; R5.4 via field 0.8/0.5 mm | **ACCEPT** against 19c and 20. Cheaper: parts $234.83 → $223.91, placements −4. Better: fuse-copper ratio 0.208 → 0.993; B3 136.0 → 135.1 °C; BUS_P span passes 3 %. | [`scorecard-native21s21.json`](scorecard-native21s21.json) |
| 20 | T1 1:200 + R39 3.0 Ω, U36 -2X bin, bank J tolerance (BOM only) | **ACCEPT**. Simpler: hand lines −1, zero-stock lines −1. Better: bank 28 A ratio 1.105 → 1.022. Parts +$2.89 at 500. | [`scorecard-native21s20.json`](scorecard-native21s20.json) |

`consign_lines` (BOM lines with no LCSC code, r2-dfm P4) was added on 2026-10-13 and back-filled on every card from its tag's BOM: 10 on 19c, 8 from stage 20 on. `hand_or_consign_lines` counts every THT line, so it moves only when a line is deleted.

`bank_ratio_tdk_28A_40k` was added to the card with stage 20 and back-filled on 19c from the same script (DECISIONS 23). Prices for new MPNs come from `STOCK-2026-10-13-addendum-*.csv`, on a same-channel, conservative basis.
