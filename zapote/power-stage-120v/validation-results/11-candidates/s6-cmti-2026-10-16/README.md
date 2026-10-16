# S6: CMTI 1.5x rule on the FILTERED / OPEN rows (native-21, board of record s51), 2026-10-16

Analysis and read-only sourcing. Nothing in the PS repo was written. Every number below is reproduced by the
scripts in `scripts/`; the outputs are in `results/` and `sims/`.

## Rerun

    cd scripts
    zsh run_maxqrr.sh              # ngspice, ~25 min on 4 workers: S4 at maximum Qrr on the adopted gate network
    python3 -I cm_barrier.py       # ~5 s: common-mode dv/dt at each barrier's reference nets (round-3 EMI deck, transient)
    python3 -I jlc_fetch.py detail C428883 C5216431 C5439825 C3029754 C5439819   # stock cache (online once, then cached)
    python3 -I s6_verdict.py       # tables below -> results/s6_verdict.json, s6_verdict.stdout.txt

- `gn_s6.py` is the committed `gate-network-2026-10-15/scripts/gn.py` with three changes only: output goes to
  `../sims`, the C8 library is not hashed (unused here), and three configs are added (`split68_1_cgs4p7_tt260`,
  `split56_1_cgs4p7_tt260`, `split100_1_tt260`: the D-24 maximum-Qrr transit time, 260 ns, on the adopted network).
- **Control:** `split47_1_tt260` on `s4screen` reproduces the committed 106.21 V/ns exactly (56/56 rows).
  `split68_1_cgs4p7_tt125` on `s4b` reproduces the committed typical-Qrr 49.70 V/ns exactly.
- `cm_barrier.py` reads `validation-results/07-conducted-emi/round3/scripts/emi_topology.cir` (sha256 in
  `results/cm_barrier.json`) and keeps every element. A 5 ps / 1 ps step comparison agrees to 0.01 V/ns. Any run
  whose node voltage passes 3x the edge is rejected as a divergence and rerun at 2 ps. One case needed the rerun.
- `work/cmti_table_copy.py` is the committed `cmti_table.py`, pointed at the repo and writing its CSV into `work/`.
  It exits 1 on today's schematic; see section 5.

## 1. What the S6 row is

The rows come from `06-controller-interface/cmti/cmti_table.py`, and the 1.05x is 100 / 95:
- **100:** the CMTI minimum of the fitted 100 kV/us parts.
- **95 V/ns:** `DVDT_HARD`, the ALT-BIAS R10 model edge. It dates from before stage 42.

The same 95 V/ns is applied to every row, including rows that are "not a switch node; 95 V/ns applied as a
conservative bound".

| Ref | Part (s51 BOM) | Class | Barrier reference nets | What an upset does |
|---|---|---|---|---|
| U43, U44 | ISO6721FBDR | FILTERED | N_HA = SW_A / N_HB = SW_B to N_LS | pauses or adds at most 1–2 heartbeat edges (c24 FMEA §6a): availability only |
| U32 | CA-IS3720HW | FILTERED | N_LS / LEG_RET to SELV_GND (= PE through r_fe 0 Ω) | drops or adds one heartbeat edge; only a sustained wave holds BIAS_GOOD |
| U9 | CA-IS3720HW | OPEN | OCP_KELVIN_P / LEG_RET to SELV_GND | BUS_FAULT glitch; R134 / C167 (τ 100 ns) on the board; the controller's debounce is not in this repo |
| U4 | AMC1311BDWVR | OPEN | OCP_KELVIN_P (GND1) to SELV_GND | one spurious VBUS sample; no gate command |
| U36 | VOL628A-2X001T | OPEN | L_FILT / N_FILT to SELV_GND | false zero-cross edge; no CMTI is published |

What the classes mean:
- **FILTERED:** the output reaches only a time-filtered line. Here that line is the heartbeat hold node,
  R_bleed ‖ C_hold with τ = 49.9 µs; one dropped period of ≥ 0.42 µs rides through (c24 SPICE, design J).
- **OPEN:** there is no CMTI number, or the consumer of the output is off-board.

The rule (RESOLUTION-PLAN.md F6 step 1) reads: "**Pass:** CMTI ≥ 1.5 × the max dv/dt for every crossing whose upset
produces a gate command. Crossings whose output is time-filtered (≥ 10 µs) may pass on the filter." So **the 1.5x
rule does not apply to any S6 row by its own wording.** FILTERED rows pass on the filter, and the script already
prints PASS for them. OPEN rows are open because of the consumer or a missing number, not because of the ratio.

The same plan step asks for "the dv/dt that crossing actually sees". The table never computed that, so it is done
here.

## 2. The dv/dt each barrier actually sees

### 2a. The switch-node edge (U43 / U44 by construction; also U1 / U2)

Adopted network (stage 42): R_on 68 Ω 2512 + Cgs 4.7 nF. The 20–80 % chord is the repo's slew basis, the same as the
ledger's 49.7.

| Basis | Grid | S4 chord | Indicative peak | diF/dt | Source |
|---|---|---|---|---|---|
| typical Qrr (TT 125 ns) | full 640/640 | **49.70 V/ns** | 64.7 V/ns | 244 A/µs | committed `full.md`; peak from the s4b rerun |
| **maximum Qrr (TT 260 ns, 4.60 µC)** | **full 640/640, every screen passes** | **68.16 V/ns** | **90.6 V/ns** | 244 A/µs | `sims/split68_1_cgs4p7_tt260/full` (new) |
| max Qrr, 56 Ω + 4.7 nF | s4b 42/42 | 78.9 | | 277 | new |
| max Qrr, 100 Ω, Cgs 1 nF | s4b 42/42 | 72.4 | | 274 | new |
| max Qrr, 47 Ω, Cgs 1 nF (the ledger's stand-in) | s4screen 56/56 | 106.21 | | 470 | control, matches the committed value |

Notes on the table:
- The worst row is S4, leg A, HS turning on, 280 V, strong driver, 150 °C, ESL 10 nH. The other cases at maximum Qrr:
  S1 20.6, S2 20.5, S5 22.1 V/ns. Die VDS peaks at 435 V (S2).
- **The ledger's "maximum Qrr 106.2 V/ns" was the 47 Ω / 1 nF network, not the one fitted.** The adopted network
  reads 68.2 V/ns. 68 Ω + 4.7 nF is also the lowest of the networks tested at maximum Qrr, so the gate network gives
  no further cheap reduction.
- **"Indicative peak"** is the instantaneous ddt(v(sw)) on the top-chord rows: chord × the median peak/chord ratio,
  about 1.33.
  - The harness's B-source ddt at its 0.2 ns step is not a qualified metric. It throws isolated spikes (106–989 V/ns
    on rows whose chord is 66–68) and some failed reads (0.1–0.5).
  - Ratios outside 1.0–1.6 are rejected in `s6_verdict.py`.
- **Side finding (S14):** 68.16 V/ns at maximum Qrr is 0.97 of the CFD7's 70 V/ns diode rating and above the 56 V/ns
  (80 %) screen. diF/dt is 244 against the 1,040 A/µs screen. S14's maximum-Qrr basis therefore moves from "not run"
  to "under the rating, over the 80 % screen".

### 2b. HOT return to SELV (U32, U9, U4) and line to SELV (U36): common-mode divider

Neither side of these barriers is a switch node. Their dv/dt is the fraction of the leg edge that the parasitic
capacitive divider puts on HV_RET relative to PE. On this board SELV_GND is PE (r_fe 0 Ω).

`cm_barrier.py` model:
- **Edge:** one 287.6 V leg-A ramp with leg B static, i.e. no opposed-leg cancellation.
- **FET tabs:** re-valued for the decided M11 stack: 2.032 mm AlN, 200–300 mm² of tab, 7.8–11.6 pF, so 12 pF is used.
  Round 3's 42 pF silicone pad is kept as the high case.
- **Rectifier:** two states, conducting (mains crest) and **all four diodes blocking** (bus held at peak at idle or
  restart, the worse state).

Results at the 68.16 V/ns maximum-Qrr chord (1 ns-chord dv/dt on HV_RET to PE):

| Case | HV_RET to PE | CMTI 100 / seen | N_FILT to PE (U36) |
|---|---|---|---|
| nominal, rectifier conducting | 0.74 V/ns | 135x | 0.67 |
| **nominal, rectifier blocking** | **6.59 V/ns** | **15x** | 0.31 |
| worst single parameter: 100 pF coil-to-PE, all on the SW_A end (blocking) | 22.6 | 4.4x | 1.3 |
| Y-cap lead ESL 20 nH (blocking) | 15.2 | 6.6x | 17.9 |
| every tab 42 pF, silicone pad (blocking) | 11.5 | 8.7x | 0.5 |
| T1 interwinding 20 pF (unspecified by Coilcraft) | 10.7 | 9.3x | 0.6 |
| **stacked-pessimistic, AlN tabs**: coil 100 pF all on A + T1 20 pF + Y ESL 20 nH + sink on its own 150 nH bond + C_j 20 pF, undamped | **86.7** (conducting) / 51.6 (blocking) | **1.15x** | 86.7 |

The stacked case is a high-Q LC ring: ±150 V at about 125 MHz with only lumped losses, i.e. 17–19 A of
common-mode current. It is a stack of assumed corners, not a manufacturing bound.

**Verdict for 2b:**
- With nominal parasitics these barriers see 1–10 % of the edge. The 95 V/ns (or 68 V/ns) bound overstates their
  stress by 15–135x.
- With single-parameter pessimism they see at most a third of the edge: 4.4x margin at maximum Qrr.
- The desk model cannot **bound** them below the switch-node edge. An undamped stack of assumed parasitics rings to
  1.3x the edge. Only a measurement closes this, so it is the bench item below.
- A local fix does not help (2c).

### 2c. Fix (b): a local Y1 capacitor across the barrier does not work

The idea is 1 nF or 2.2 nF, Y1, with 3 nH mounted, from HV_RET to SELV_GND at the U9 / U32 / U4 cluster.

| Case at 68.16 V/ns | without | + 1 nF | + 2.2 nF |
|---|---|---|---|
| nominal blocking | 6.59 | 7.66 (worse) | 8.53 (worse) |
| stacked, AlN, blocking (peak / 1 ns chord) | 60.1 / 51.6 | 60.1 / 44.9 | 60.1 / 45.2 |

- The edge is over before 3 nH lets the capacitor act, so the peak is unchanged. It also needs a footprint across the
  8 mm reinforced floor and adds 34–48 µA of PE leakage. **Rejected.**
- The other (b) lever is a slower gate. It was already spent at stage 42, and 56 Ω or 100 Ω are worse at maximum Qrr
  (table 2a).

## 3. Verdict per channel

CMTI minimum against the dv/dt the barrier sees. Typical Qrr uses the 49.7 V/ns chord; maximum Qrr uses the 68.16
V/ns chord and the indicative 90.6 V/ns peak. Rows 2b use the nominal blocking case.

| Ref | CMTI min | typ Qrr | max Qrr chord | max Qrr peak | Applicable rule | Verdict |
|---|---|---|---|---|---|---|
| U1, U2 2EDR8259X (GATE; context) | 150 | 3.0x | **2.20x** | 1.65x | 1.5x | **PASS** at both Qrr bases. Closes the ledger's "max Qrr 1.41x" gap on desk evidence |
| U43, U44 ISO6721FBDR | 100 | 2.0x | **1.47x** | 1.10x | filter (τ 49.9 µs ≥ 10 µs), plus CMTI ≥ edge as a rating | **PASS** on the filter. Rating ≥ edge holds at maximum Qrr: 0.68 of it on the chord, 0.91 on the peak. The 1.5x rule would read 1.47x if it applied; it does not |
| U32 CA-IS3720HW | 100 | 19x | 15x | 10x | filter | **PASS** on the filter. Stacked-pessimistic 1.15x: bench |
| U9 CA-IS3720HW | 100 | 19x | 15x | 10x | none (no gate command) | **OPEN on the consumer only** (controller BUS_FAULT debounce). On-board R134 / C167 τ = 100 ns |
| U4 AMC1311B | 100 | 19x | 15x | 10x | none (measurement) | **OPEN on the consumer only** (firmware single-sample rejection) |
| U36 VOL628A | none | n/a (0.3–0.7 V/ns nominal) | | | none | **OPEN: no datasheet number.** Line-side transients (EFT / surge) dominate; firmware zero-cross window |

**S6 as worded ("1.5x not met on FILTERED / OPEN rows, 1.05x") is a mis-scoped rule applied to a superseded edge.**

## 4. Fix (a): a higher-CMTI pin-compatible part with a defined failsafe

Stock is JLC on 2026-10-16 (`results/jlc-raw/`). Each slot needs 2 parts per board: 40 for 20 boards, 1,000 for 500.

| Slot | Candidate | CMTI min | Open-input state defined | VIORM use (287.6 V) | JLC stock | $ at 500 | Pin-compatible | Result |
|---|---|---|---|---|---|---|---|---|
| U9 / U32 (SOIC-16W, pins 4 → 13, default H) | CA-IS3720HW (fitted) | 100 | yes (Table 9-1) | 20 % | 1,640 | 0.5188 | – | keep |
| | NSi8220W1-DSWR | **200** | **no**: DS 1.5 Table 7.1 gives only "VDD1 unready → H"; inputs have an 8–15 µA "pull high or low" | 14 % | **91** (20 boards: yes; 500: no) | 0.7228 | yes (3/4/13/14, 1/7, 9/16) | reject: FMEA §6b needs the open-input state; stock. VDE 0884-11 cert 40052820, not -17 |
| | ADuM220N1 / 221N | 75 | yes | 849 Vpk | | | ADI pinout | reject (worse: Rev B p.4, 75 min / 100 typ) |
| | ISO7710 / ISO7720 / ISO7820 | 85 | yes | | 29 (ISO7710F) | | yes | reject (worse) |
| | Infineon 2DIB14x1F (ISOFACE) | 100 | yes | | | | | no gain |
| | 2Pai π122M31 / E31 | 75 typ | supply loss only | | | | | reject |
| U43 / U44 (SOIC-8, INB 3 → OUTB 6, default L) | ISO6721FBDR (fitted) | 100 | yes ("both input states") | 45 % | 4,900 | 0.4112 | – | keep |
| | NSi8221N0-DSPR | **200** | **no** | **50.9 %** (VIORM 565 Vpk; VIOWM 400 Vrms: 50.8 %) | 1,540 | 0.5205 | yes (NSi8221N pin map = ISO6721 D) | reject: open input; barrier derating > 50 % |
| | NSi8222N0-DSPR | 200 | no | 50.9 % | 1,304 | 0.5123 | **no**: pin 3 is an OUTB output and would fight the driven INB net | reject |
| | Würth 18012115411L (WPME-CDIS) | **none** (CMTI row: "—, 150, —" kV/µs, typical only; DS v1.1 July 2024) | default L | 566 Vpk | | | | reject: no guaranteed figure |

**Result:**
- No pin-compatible, stocked part has a higher **guaranteed** CMTI together with a datasheet-defined open-input state.
- The Novosense parts are the only ones above 100 kV/µs minimum, and both fail FMEA §6b's open-input requirement. The
  SOIC-8 part also fails the 50 % VIORM rule, and the SOIC-16W part has 91 in stock.
- The 2026-10-14 NSi822xW rejection stands, re-read against DS Rev 1.5 Table 7.1.

## 5. Recommended fix: (c), a records change. No BOM or layout change, $0

The rule's basis is the wrong edge. The rows already pass under the rule's own scope. The stated ratio comes from a
stale script.

1. **OPEN-ITEMS S6 → Closed (rule scope + evidence).** FILTERED rows pass on the 49.9 µs filter. OPEN rows are open
   only on their consumers, which are already listed as controller items: BUS_FAULT debounce, VBUS single-sample
   rejection, zero-cross window. The 1.05x was 100 / 95 against the pre-stage-42 ALT-BIAS model edge.
2. **`cmti_table.py` is stale against today's `elec/src`.** Rerun as-is, it reports 3 enumeration MISMATCHes and exits
   1 (`results/cmti_table_committed_rerun.stdout.txt`):
   - iso6721_links 2 vs 1;
   - IsoReinfL 0 vs 1;
   - PS1 0 vs 1.

   It also mislabels several rows:
   - U44 still shows as CA-IS3720LW; it has been ISO6721FBDR since stage 40;
   - PS1 IRM-20-15 is still listed but is gone;
   - PS2 shows as IRM-20-24; it is MPM-20-24;
   - it still prints the UCC21550 "derived" block.

   The proposed edits:
   - `DVDT_HARD` 95 → the s42 basis: 49.7 typical and 68.16 maximum-Qrr chord, from this job's `sims/`;
   - add the plan's "dv/dt actually seen" column: switch node for U1 / U2 / U43 / U44, and the CM-divider nominal and
     sensitivity for U9 / U32 / U4 / U36 (`cm_barrier.py`);
   - fix the three enumeration expectations and the MPNs.
3. **Ledger stresses "CMTI edge, maximum Qrr (open)" 106.21 → 68.16 V/ns** (adopted network, full grid 640/640) on
   ISO6721FBDR, CA-IS3720HW, AMC1311BDWVR, 2EDR8259XXUMA1 and R24C2T25/R-R:
   - 2EDR "CMTI 1.5x, max Qrr" becomes 2.20x (gap closed on desk);
   - ISO6721 "CMTI, max Qrr" becomes 0.68 of the rating (1.47x);
   - RECOM 2.20x.

   Note the indicative peak (90.6 V/ns) in each condition.
4. **S14:** add the maximum-Qrr row: 68.16 V/ns, 0.97 of the 70 V/ns diode rating, over the 56 V/ns screen; diF/dt
   244 A/µs passes.

Cost $0. BOM unchanged, copper unchanged. If the bench (6) later fails U43 / U44, the fallback is a re-spin choice,
not a drop-in. In order of preference:
- a slower S4 edge (firmware / gate);
- a vendor statement on NSi8221's open-input state plus a part with VIORM ≥ 576 Vpk (NSi8221W0 SOW-8 needs a new
  footprint).

## 6. What the bench (D-8 and bring-up) must still confirm

1. **S4 at maximum-Qrr parts**, the D-8 double pulse at 198 / 280 V, −20 A, leg A HS turn-on:
   - SW_A 20–80 % chord ≤ 100 V/ns, and the peak ≤ 100 V/ns, for U43 / U44's rating;
   - chord ≤ 100 V/ns for U1 / U2's 1.5x.

   The desk model predicts 68.2 V/ns chord and about 91 V/ns peak. The probe needs ≥ 500 MHz, and the reading must
   be taken in the 20–80 % window.
2. **HV_RET-to-SELV_GND dv/dt at hard S4 / S5 edges, on the full assembly**: AlN stack, sink bond, coil, pan, harness,
   with the rectifier both conducting and blocking (idle bus at peak).
   - The pass line for U9 / U32 / U4 at 1.5x is ≤ 66.7 V/ns. The model says 0.7–6.6 nominal.
   - Use a high-CMRR differential probe, or a fibre-isolated probe on the SELV side.
   - This is the number the desk cannot bound (stacked corner 87 V/ns).
3. **Glitch capture on burst S4** (370–740 edges): U43 / U44 OUTB, U32 HB_RX, U9 BUS_FAULT_FLT. BIAS_GOOD must not
   drop, and BUS_FAULT must not latch, through a full burst.
4. **Consumer side (controller session):**
   - BUS_FAULT debounce ≥ 2 samples or about 10 µs;
   - VBUS single-sample outlier rejection;
   - LINE_ZC period window.
5. **U36:** EFT 1 kV and surge at the inlet with LINE_ZC on a scope (the ledger's existing item).
6. **Certifier:** look up UL E511334 (CA-IS3720) in Product iQ. This is unchanged from DECISIONS 34.

## Files

- `scripts/gn_s6.py`, `scripts/run_maxqrr.sh`: maximum-Qrr S4 grid; results in `sims/<cfg>/<grid>/results.json`.
- `scripts/cm_barrier.py`: CM divider; results in `results/cm_barrier.json` and `.stdout.txt`, decks in
  `results/cm_decks/`.
- `scripts/s6_verdict.py`: tables; `results/s6_verdict.json` and `.stdout.txt`.
- `scripts/jlc_fetch.py` and `results/jlc-raw/`: stock and price, fetched 2026-10-16.
- `dl/`: downloaded datasheets, read with pdftotext only.
  - NSi822x DS 1.5, chipdip mirror, sha256 `d7b9c51b27d956ce…`.
  - ADuM220N/221N Rev B, sha256 `e6e4bb411cd0aa8c…`.
  - Würth 18012115411L v1.1, sha256 `a78d1122c9cf65ee…`.
- `work/cmti_table_copy.py`: the committed table rerun (exit 1, stale).
