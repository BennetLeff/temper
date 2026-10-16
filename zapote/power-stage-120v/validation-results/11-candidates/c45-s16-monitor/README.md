# Candidate 45: S16 rail-monitor fix (option 1c-4420), built as stage 45 (native21s45)

**Verdict: card REJECT against s44, on cost alone** (one more BOM line and one more JLC Extended line, with no card metric
that sees the fix). Every gate passes and no performance metric moves. Board native21s45 `26ce9531…`, chain CHAIN_DONE
with no spine owner (SPINE_LOCK PASS).

```
REJECT native21s45 vs validation-results/10-benchmark/scorecard-native21s44.json: cheaper ['parts_usd_at_500', 'jlc_assemblable_share_500'], better []; costlier on ['bom_lines', 'jlc_extended_lines'] with no performance gain
```

The case for adopting it is S16 correctness, which the card does not score: the s44 span windows overlap the rails'
worst-case tolerance, and s45's do not (section 2). The integrator decides (`DECISIONS-DRAFT.md`, item 60).

Branch `claude/native21-s45-s16-monitor` from `fa09aef3c` (board of record s44, `2a84051f`). The values are option
1c-4420 of `../s16-monitor-2026-10-15/results/monitor_wc.md`, chosen in DECISIONS 59 / OPEN-ITEMS S16.

## 1. What changed (BOM only)

Per rail (LS / HS-A / HS-B). Every role was confirmed from `elec/src/f6_bias.ato` RailMonitor and the frozen netlist,
and it matched the study's map.

| Role (`RailMonitor`) | Designators | s44 | s45 |
|---|---|---|---|
| `reference` (REF tied to K) | U17 / U19 / U21 | TL431AIDBZR | **TL431BIDBZR** (C41283) |
| `rhalf_top` | R79 / R97 / R112 | 10 k RT0603BRD0710KL | **4.42 k** RT0603BRD074K42L (on the BOM) |
| `ruv_top` (src → uv) | R81 / R99 / R114 | 4.42 k | **750 Ω** RT0603BRD07750RL (C861551) |
| `rov_top` (src → ov) | R83 / R101 / R116 | 7.68 k | **2.94 k** RT0603BRD072K94L (C705761) |
| `rspanuv_top` (p → spanuv) | R85 / R103 / R118 | 120 k | **90.9 k** RT0603BRD0790K9L (C728600) |
| `rspanuv_bot` | R86 / R104 / R119 | 10 k | **11 k** RT0603BRD0711KL (on the BOM) |
| `rspanov_top` (p → spanov) | R87 / R105 / R120 | 133 k ARG03BTC1333 | **104 k** RT0603BRD07104KL (C861070) |
| `rspanov_bot` | R88 / R106 / R121 | 10 k | **11 k** RT0603BRD0711KL |

Unchanged: `rref` R59 / R63 / R65 (2.2 k RC1206FR), `rhalf_bot`, `ruv_bot`, `rov_bot` (10 k), the LM339B, the 1 nF taps.

- **BOM lines:** TL431AIDBZR, RT0603BRD077K68L, RT0603BRD07120KL and ARG03BTC1333 go. TL431BIDBZR, RT0603BRD07750RL,
  RT0603BRD072K94L, RT0603BRD0790K9L and RT0603BRD07104KL come in. That is 93 → 94 lines, the study's delta exactly.
  Placements stay at 358.
- **Footprints:** all 24 instances keep their footprint: `Package_TO_SOT_SMD:SOT-23` for the TL431B (SLVS543S Table 5-1
  p.4, DBZ 1 = K, 2 = REF, 3 = A, the same as the A grade) and `R_0603_1608Metric` for the resistors (Yageo RT0603, Table 2
  p.5). The EasyEDA records of all five new LCSC numbers give the same pinout and package class (section 6).
- **Source:**
  - `f6_parts.ato`: BiasReference becomes TL431BIDBZR; Bias750R, Bias2k94, Bias90k9 and Bias104k replace Bias7k68,
    Bias120k and Bias133k.
  - `f6_bias.ato`: the RailMonitor values change.
- **Build:** atopile 0.2.69 offline plus `circuit_export.py`, refrozen to `frozen/` and `native-21/frozen/` (path
  normalised to `ps-integrate`).
  - `default.net` is byte-identical to s44: 358 components, 183 nets, the same designators and nodes.
  - Only `default.csv` and `resolved-components.json` change, in exactly these 24 instances.

## 2. Bands (re-derived from the frozen values: `scripts/bands45.py` → `results/bands-s45.md`)

`bands45.py` reads the MPN and value of every monitor part from `frozen/resolved-components.json` (all three rails, which
are asserted identical). It cross-checks each value against its Yageo part number and runs the S16 study's own
`model.py` / `monitor_wc.evaluate` on them, unchanged. Two controls are asserted:
- **R1:** the s44 values reproduce the study's s43 table to 1e-4;
- **R2:** the frozen s45 values reproduce the study's 1c-4420 table to 1e-4: nominal, worst case, RSS, Q / H margins and
  joint RSS. **They match.**

| Threshold | s44 worst case | s44 RSS | s45 worst case | s45 RSS | Rail limit | Rail margin WC, s44 → s45 | Rail margin RSS, s44 → s45 |
|---|---|---|---|---|---:|---:|---:|
| neg UV (release ≤) | 1.7395–1.8583 | 1.767–1.830 | 1.8146–1.9044 | 1.832–1.887 | 1.9654 | +0.107 → +0.061 | +0.135 → +0.078 |
| neg OV (trip ≥) | 2.1313–2.2798 | 2.166–2.244 | 2.1825–2.2942 | 2.205–2.272 | 2.0757 | +0.056 → +0.107 | +0.091 → +0.129 |
| span UV (release ≤) | 15.6299–16.8044 | 15.924–16.504 | 15.5689–16.4788 | 15.778–16.265 | 16.575 | **−0.229 → +0.096** | +0.071 → +0.310 |
| span OV (trip ≥) | 17.1923–18.4855 | 17.516–18.154 | 17.5692–18.5984 | 17.807–18.356 | 17.425 | **−0.233 → +0.144** | +0.091 → +0.382 |

The s44 RSS margins are the study's s43 values (`monitor_wc.md`, s43 table). On joint RSS, span UV goes from 4.6σ to 6.0σ
and span OV from 4.7σ to 6.4σ.

Catch side (Q = the committed F6 qualification basis, H = hard ratings):
- **neg UV:** +0.060 V against the 1.754 V edge-rule floor. It was −0.015 V at s44, so the pre-existing neg-UV Q gap is
  cleared.
- **neg OV:** +0.106 V against 2.4 V.
- **span UV:** +0.069 V against the 15.5 V droop-campaign span. That is positive, but under the 0.5 % target, so MARGINAL,
  as the study found.
- **span OV:** the upper corner is **18.598 V**.
  - Against the study's Q basis (the 18.0 V hot-load span) it reads −0.598 V.
  - The out-D33 hot-load campaign was re-run at **19 V** (`out-D33/rail-hot-19V/hot-load.json`, 128 / 128, DECISIONS 59
    integration note). Against that 19.0 V ceiling the margin is **+0.402 V**.
  - Against H (the 2EDR8259X 21 V operating maximum) it is +2.40 V, a VDD ratio of **0.886**.

## 3. Card (`10-benchmark/scorecard-native21s45.json`) and compare

**Gates:** all pass, the same as s44: DRC 0 / 0 / 0, barrier, RES_A, DFM, return path, bypass, PI, RES_A creepage 18, D5,
enclosure fit, jet strip, `audit.rs` and `b3_ratings`.

**Performance:** every field is identical to s44:
- D5 8.047 / 8.507, RES_A 13.375;
- return-path opens 7, worst asserted 2.72;
- Kelvin 67.77, OCP pickup 4.17 A, fuse ratio 0.993;
- B3 laminate −30.2, rated part −32.3, release +1.2 K;
- EMI 12.4 dB, touch 0.241 mA, CMTI 1.579, bank 1.022 / 1.045;
- ledger violations 0 and unaudited SAFETY / POWER 0;
- track corners and any-angle unchanged.

**What moved (cost only):**

| Field | s44 | s45 |
|---|---|---|
| bom_lines | 93 | **94** |
| jlc_extended_lines | 68 | **69** |
| parts_usd_at_500 / at_5 | 202.38 / 306.90 | 201.60 / 304.99 |
| jlc_assemblable_share_500 | 0.849 | 0.851 |

**The card's −$0.78 at 500 is a price-basis artefact, not a saving** (`scripts/cost45.py` → `results/cost-s44-s45.md`).
- The lines that leave carry the 2026-10-13 class-default ESTIMATE in `STOCK-2026-10-13.csv`: TL431AIDBZR at $0.40 and
  every 0603 thin film at $0.008.
- The lines that come in carry fetched JLC prices (`STOCK-2026-10-13-addendum-s45.csv`, as stage 42 did).
- With every changed line on the 2026-10-15 JLC ladders, the delta is **+$0.181 per board**. That is the study's +$0.167
  plus $0.013: RT0603BRD0710KL drops to 19 per board, which moves it to a dearer price break.

**Against the other benchmarks** (`results/compare.txt`):
- ACCEPT against s43 and s42;
- REJECT against s41 on the laminate ratchet only (the DECISIONS 55 override, as for s42 to s44).

## 4. Copper and placements are identical to s44

`scripts/geom_diff45.py` → `results/geom-s44-s45.json`, s44 `2a84051f` against s45 `26ce9531`:
- **Footprints:** 358 = 358. None differs in library id, layer, position, rotation or any pad (number, net, position,
  size, shape, drill, layers).
- **Tracks, arcs and vias:** 5,115 items, equal. Zone outlines: 87, equal. Edge.Cuts equal.
- **Fields:** only U17 / U19 / U21 and the 21 resistors above differ, and only in their `Value` / `MPN` text.
- **Control:** the same script reads s44's run 1 against run 2 as identical.

Further checks:
- **`copper_key.py`:** `d33d77ac…` on both boards. So task 04 and B3 took cache hits on the s44-run-1 computation.
- **`fill_hash.py`:** area hash `39fe161d` on both, symmetric difference 0.16 mm² in total (worst 0.034 mm² per
  layer / net, under the 0.1 mm² refill tolerance; `results/fill-hash-s44-s45.txt`).
- **Gerbers:** they differ textually, for two reasons:
  - KiCad writes the footprints in a new order on every build, which renumbers the apertures (F.Paste, the masks, silk);
  - the copper layers also carry the refill tessellation that `fill_hash.py` exists for.

  The drill files, Edge.Cuts and B.Paste differ only in their timestamps. The geometry comparison above is made on the
  board file for this reason.
- **`track_cleanup21.py`:** 0 edits (`results/cleanup-s45.json`). `copper.json` is unchanged (`9b48413e`).
- **Fuse necks and OCP pickup:** `s45_necks.json` equals `s44_necks.json` apart from the board hash (min ratio 0.993).
  `coil-pickup/s21b/result-s45.json` equals s44's apart from its hashes (4.17 A).
- **B3 ratings:** re-solved on this board. 3 of 132 rows move 0.1 K (refill noise: C152 c22, U41 Tj c22, R20 c28), and
  the metrics are unchanged.

## 5. Chain runs

```sh
R=/Users/bennet/Desktop/temper/worktrees/runs-native21/s45
cp runs-native21/s44/p1/j1/copper-dump.json $R/pass-j1/        # the s44 pass that planned s44's test points
TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s45 $R/pass-j1 $R/c45     # CHAIN_DONE, board 26ce9531
python3 -I native-21/layout/gates/scorecard.py native21s45 $R/c45 --audit PASS --json validation-results/10-benchmark/scorecard-native21s45.json
python3 -I native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-native21s45.json \
    --compare validation-results/10-benchmark/scorecard-native21s44.json
```

- **Run 1** (`$R/c45-run1`, board `4dbb136a`) was CHAIN_DONE on the same copper (copper key `d33d77ac`, geometry
  identical to s44). It showed two annotation losses, fixed before run 2:
  - `pin_functions21.py` keys the DBZ pin table by MPN, so U17 / U19 / U21 fell back to untyped p1 / p2 / p3. TL431BIDBZR
    is added to the table (same pins as the A grade).
  - The CPL audit had no EasyEDA footprint for the five new LCSC numbers. U17 / U19 / U21 then stayed NEEDS-PREVIEW, but
    proposed 270° on the DB rule alone.
- **Fix for the CPL audit:** the five public EasyEDA records were fetched (`lceda.cn`, raw copies in `$R/ee-raw`). Only
  those five were distilled into `cpl-rotation-audit/sources/easyeda-footprints.json`, with the audit's own `distill()`.
- **Run 2** (`$R/c45`) is the board of this candidate. CPL audit: 284 OK / 55 NEEDS-PREVIEW / 8 CORRECTED, as at s44.
  - U17 / U19 / U21 are NEEDS-PREVIEW with the same EasyEDA-vs-DB conflict (180° vs 270°) as the TL431A had.
  - The 12 new-value resistors are OK.

## 6. Source checks, ledger and sourcing

- **`audit.rs`:**
  - IDENTITY for all 24 instances moves to the new MPNs. Run on the new build before that edit, it fails on exactly those
    24.
  - New test `stage45_rail_monitor_values_hold`: the TL431A, the 10 k halfref top, or any old tap value back on a monitor
    must fail.
  - **87 / 87** tests pass; the audit passes on `build/` and on both frozen copies.
- **`verify_source.py`:** asserts the MPN, value and footprint of every monitor part on all three rails
  (`source-check.json`).
- **Datasheet ledger** (`scripts/ledger45.py`, idempotent; stresses cited to `results/bands-s45.md` lines):
  - TL431AIDBZR, RT0603BRD077K68L, RT0603BRD07120KL and ARG03BTC1333 are removed.
  - **TL431BIDBZR** is added, SIGNAL, PARTIAL:
    - SLVS543S Table 6.12 p.13: Vref 2.483–2.507 V, VI(dev) 34 mV max;
    - Table 6.4 p.5 checks: VKA 2.541 / 36 V; IK 7.29 mA operating and 9.79 mA at a 24 V span against 100 mA (minimum
      5.65 mA ≥ 1 mA);
    - gaps: no B3 rows at the monitor islands (64.3 °C is an estimate, against the 85 °C I-grade limit); the 24 V fault
      span is a stated case, not a bound; no load-life drift figure.
  - **The four new resistors** are added, SIGNAL, PARTIAL, on Yageo RT V.16 (Table 2 p.5, Fig. 6 p.6). They are checked
    for working voltage and for power against the 85 °C derated 82.4 mW. The worst is the 90.9 k / 104 k tops at 21.4–21.7
    V, 0.29 of 75 V. The gaps are the same two.
  - **Re-listed:**
    - RT0603BRD074K42L → R79 / R97 / R112;
    - RT0603BRD0710KL loses 9 designators (28 → 19);
    - RT0603BRD0711KL gains R86 / R88 / R104 / R106 / R119 / R121.
  - **2EDR8259XXUMA1:** "VDD at the span OV trip" goes from 17.84 V to **18.60 V**, a ratio of **0.886** of 21 V.
  - `gate.py` PASS: 94 lines, 3 VERIFIED / 37 PARTIAL / 54 UNAUDITED / 0 VIOLATION (was 3 / 32 / 58 / 0 of 93).
    `tests/test_gate.py`: 24 ok, 0 failures.
- **Sourcing (`study-2026-10-15/run_all.sh`):**
  - The new s45 step builds `snapshot/s45/` from the five cached JLC detail records, copied from the S16 study into
    `scripts/jlc-raw`.
  - The 10 k and 11 k lines are re-priced on their own ladders at the new quantities.
  - `../SNAPSHOT-2026-10-15.csv` gains 5 rows and re-keys 3. Every earlier step reruns byte-identical.
  - `apply_lcsc.py` maps the five new MPNs.
- **JLC stock at 500 boards:** RT0603BRD07750RL has 2,661 against the 1,500 needed, so buy early. The other four have
  ≥ 8,015.
- **Docs:** `native-21/ECO.md` carries the new nominal windows.
- **Kelvin tables:** `kelvin_budget.py` / `kelvin_plane.py` gain the `native21s45` entries (the OCP divider is unchanged).

## 7. Tests (with `native-21/section.kicad_pcb` = the s45 board `26ce9531`)

| Test | Result |
|---|---|
| ledger `tests/test_gate.py` | 24 ok, 0 failures |
| ledger `gate.py` | PASS |
| `gates/test_track_geometry.py` | 7 / 7 |
| `gates/test_spine_lock.py` | 11 / 11 |
| `layout/test_track_cleanup21.py` | 45 / 45 |
| `gates/test_jet_strip_height.py` | 7 / 7 |
| `gates/scoped/test_scoped.py` | 16 / 16 |
| `audit.rs --test` | 87 / 87 |
| `verify_source.py` | PASS |

## 8. Notes and limits

- **Not done here (OPEN-ITEMS S16 next steps):**
  - the FMEA C1–C7 re-run on the s45 values;
  - B3 probe rows at the monitor parts;
  - the 15.5 V droop campaign at the new span-UV corner (15.569 V, MARGINAL on the 0.5 % target).
- **The neg-UV rail margin narrows on purpose:** +0.107 → +0.061 V worst case, +0.078 V RSS. The window moves up to clear
  the edge-rule floor.
- **Fault-case stress, R77 / TLVH431 open:** src is bounded by P (the 4.99 k bleed holds it lower), and with the 750 Ω
  neg-UV top, its 10 k bottom (R82 / R100 / R115) would see at most 17.3 V, 30 mW at an 18.6 V span. That is within the
  RT0603 85 °C rating (82.4 mW). RT0603BRD0710KL itself stays UNAUDITED SIGNAL.
- **Not edited:**
  - FAB-NOTE's board / Gerber SHA (integration records);
  - DECISIONS.md and OPEN-ITEMS.md (draft in `DECISIONS-DRAFT.md`).
- **Not staged:**
  - `fab/assembly-drawing.pdf`;
  - `validation-plan/enclosure-fit/plan-result.json`;
  - the datasheet PDFs (scratch copies in `runs-native21/s45/dl/`).
