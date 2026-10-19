# commission-s53: the bench procedure re-based on stage 53, and a gate against drift

`firmware/components/power/COMMISSIONING.md` gave stage-15 board numbers for a stage 53 board of record. This study
re-bases it on **native-21 stage 53**: board SHA-256 `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`,
copper key `b7a0bc5790b9` (`08-manufacturing-package/native-21/fab/FAB-NOTE.md`, `10-benchmark/scorecard-native21s53.json`,
DECISIONS 75). It also adds a gate so the procedure cannot drift from the board again. Branch `study/commission-s53` (base
`codex/power-stage-integration` f9d945326). No firmware behaviour, threshold or default changed.

## How the numbers are kept honest

Every board-specific number in the procedure is now in one generated **board table** (rows B1–B19, J4, probe points,
ceiling ladder). `firmware/tools/commissioning_board_table.py` renders it. The steps cite its rows instead of repeating the
numbers.

- **Board of record:** read from FAB-NOTE (stage, board SHA-256, copper key). The scorecard for that stage must carry the
  same hash.
- **Re-derived on every run:** designators by ato role from `native-21/frozen/resolved-components.json`, part values from
  the frozen BOM, J4 from the frozen netlist. The CT band and the nominal trips come from the round-3 engine
  (`02-protection-timing/round3/thresholds.py`, its `validate_inputs` included), run on the frozen parts. The rest:
  - OCP: the Kelvin budget (`kelvin_budget.py` BAND_BEFORE / FLOOR, `budget-native21s53.json`) and the band record it names;
  - CT burden temperature: the B3 margins;
  - D3 / D17 stand-off: the datasheet ledger;
  - dead time: the 2EDR8259X estimator (`c25-driver/scripts/dt_window.py`, `audit.rs` DT_WINDOW_NS);
  - VBUS receiver: the controller's D-11 calc (`zapote/controller/tools/controller_calcs.py`);
  - probe points: `native-21/BRINGUP-PROBES.md`;
  - firmware side: `n21_signal.h`, `tank_freq.h` and Kconfig.
- **Facts no light tool reproduces** (SPICE timing, bank ladder stops, the T1 ratio, which band record serves this stage)
  are in `STAGE_FACTS["53"]`, each with its DECISIONS / OPEN-ITEMS citation. A new board of record has no entry, so the tool
  exits 5 until someone re-bases the procedure on it.
- **`--check`** (exit 3 on drift) fails on any of:
  - a block that differs from the render;
  - an introduction that does not name the board-of-record stage;
  - a `stage-NN board` or `stage NN: R…` claim for any other stage;
  - a power-board resistor value in the prose that the frozen BOM does not have (`controller R…` is exempt);
  - an unknown `TEMPER_POWER_*` symbol;
  - a commissioning-record provisional value that differs from the Kconfig default;
  - a backticked firmware symbol that no firmware source mentions.
- **CI:** Firmware Tests, the step "Commissioning procedure vs board of record", runs `--check` and
  `firmware/tools/test_commissioning_board_table.py` (27 tests). The workflow now also triggers on the board sources it
  reads.

Evidence (`results/`):
- `check.txt`: PASS on the committed procedure; 27 / 27 tests.
- `negative-control-stale-copy.txt`: B3 set back to the stage-15 band, and the old board-revision line re-inserted. Exit 3,
  with three failures: the table, the stage-15 claim and R34 12.6 kΩ.
- `negative-control-f9d945326.txt`: the pre-change procedure with the s53 table inserted gives 12 failures, every
  stage-14 / 15 / 49 board claim and every stale R34 / R35 value (exit 3). Unchanged, it is a gate error (exit 5).
- `reruns.txt`: `kelvin_budget.py native21s53` and `dt_window.py` re-run byte-identical to their committed outputs.

## Numbers changed (old → new, source)

| Item | Old (stage-15 text) | Stage 53 | Source |
|---|---|---|---|
| Board named | "for the **stage-15** board (R34 12.6 kΩ, R43/R46 2.21 kΩ)", plus a stage-14 CT-band note | stage 53, hash and copper key above | FAB-NOTE; scorecard-native21s53 |
| OCP divider | R34 12.6 k / R35 11.7 k | R32 10 k / R33 7.5 k / R34 16 k / R35 11 k (RT0603BRD 0.1 %); nominal 92.59 A, U6 VCM 1.0185 V | frozen BOM; thresholds.py at nominal; DECISIONS 70 |
| OCP band | 66.30–118.74 A after Kelvin | 71.59–114.57 A before Kelvin; shift −2.41 A (census) / −2.455 A (bound); low 69.18 A, **69.13 A at the bound**; floor 64.17 A | kelvin_budget.py BAND_BEFORE["native21s53"], budget-native21s53.json (re-run); band record s52-proto-bom/results/bands-s52.json, carried to s53 per DECISIONS 75 |
| OCP extra rows | — | c28: 70.50–115.96 A (68.04 A at the bound); S23 R1 reading: 68.95–117.31 A (66.49 A) | bands-s52.json tlv3201_readings |
| OCP pass rule | record only | pass inside B3; between B3 and B5 → OPEN-ITEMS S23, ceiling stays 17.5 A; below the floor → fail | design call (DECISIONS 70 "Reverses if") |
| CT comparators | "U10–U13", 64.55–76.09 A | U10 (+) / U11 (−), U13 OR; **64.55–76.09 A both polarities, unchanged**, nominal 70.18 A | thresholds.py exact_corners on T1 CST3015-200ED (1:200), R39 3 Ω, R43 / R46 2.21 k, R44 / R45 10 k |
| OVP | "U7, 280 V" | nominal 280.0 V; pass window (release) 272.61–287.47 V; c28 272.47–287.62 V; uniform-hottest bound 271.85–288.27 V | bands-s52.json rows |
| OVP bench supply | "≤ 50 mA, 300 V" | **voltage limit 295 V**, ≤ 50 mA. 300 V equals the D3 / D17 string stand-off (2 × 30KPA150CA); 295 V sits above the 288.27 V bound | datasheet ledger (30KPA150CA); B6 |
| Firmware over-range | 231 V ± 6 % | 1210 mV = 230.9 V; 217.1–244.8 V (same value, now derived) | n21_signal.h; controller_calcs.d11_receiver; frozen BOM divider |
| Dead time | 396.6–488 ns (UCC21550 figure, R9 / R17 49.9 k) | **408.3–569.0 ns** estimate (2EDR8259X Table 19); pass = the simulated window 340–600 ns | dt_window.py (re-run); audit.rs DT_WINDOW_NS; DECISIONS 31 |
| Driver UVLO in the brown-out order | UCC21550 VCCI | 2EDR8259X VDDI, on ≤ 2.95 V / off ≥ 2.55 V | CONTROLLER-REQUEST.md "one stale line"; ledger |
| BIAS_GOOD timing | ≤ 90 µs (123 µs) | ≤ 90.3 µs (≤ 122.9 µs); the other three limits unchanged (13.6 µs, 0.53 ms, 0.36 ms); "board has stage 50" → s53 has option P | DECISIONS 71 |
| Probe names | "one driver's DIS", "TP19", "R135.2", "C166" | TP17 PERMIT, TP18 leg-B DIS, TP19 BIAS_GOOD, TP20 BUS_FAULT, TP22 CT_MON, TP5 / TP27 ocp_node, TP52 / TP28 REF25, TP4 / TP26 V24_RAW; hsb_good at R135.2, hb_hold at C166.1 / R133.1 (no pads) | BRINGUP-PROBES.md; frozen netlist |
| J4 | prose only | rendered from the netlist (J4.1 bias_good_j4 … J4.16 line_zc) | frozen netlist |
| Bank gate 1 | "B32654A on pre-s49 boards", ≤ 20 K or TDK p.57 curve | C22, ΔT ≤ 20 K × F_T(T_A)² and T_A + ΔT ≤ 125 °C (H bank) | OPEN-ITEMS S25; DECISIONS 74 |
| Ladder | 17.5 → … → 28 A | 17.5 → 24 A on the H bank; 26 / 28 A on a B board only; floor column added | B14; round-6 board-side-protection.csv; DECISIONS 9 |
| No-pan clamp test (9a.6) | ceiling 28 A in the bench config | 17.5 A until a ladder step has passed its thermal gate, then the highest passed step (never above B14's stop) | owner default 2026-10-18; B14 |
| Ceiling precondition | "Stage-15 board confirmed: R34 12.6 k …" | stage 53 parts B2 / B9 / B13 confirmed | frozen BOM |
| Release margin | s45 +1.0 K only | adds s53 +1.3 K at 17.5 A (R10); 18 A not re-solved on s53 | scorecard-native21s53 b3_release_margin_K |
| Gate 4 floor | envelope + 3 A + 2 A | the same, and the shunt must also clear the floor + 1.17 A (the s53 OCP pickup model is 4.17 A at 60 kHz) until gate 5 measures it | scorecard ocp_pickup_stack_pan60_A |
| Bench power, steps 2–4 | "V15_LS and the F6 bias from isolated bench supplies" | **BR1 not fitted** (owner decision 2026-10-18); PS2 from the inlet at 120 V through the isolation transformer and analyser, J3 loop with the bench DF110S TCO; isolated DC supply on the C6.1 / C6.3 leads (B19); hv_ret tied to PE at one point in steps 2–4 and removed before BR1 is fitted; new step 4b "fit BR1" (owner, bench-sink-r1 procedure) | B18 / B19 from the frozen netlist and `native-21/layout/pads.json`; datasheet ledger MPM-20-24 (80–264 VAC) |
| Pre-J13 bring-up | — | power board alone from a breakout, J4.3 bench 3.30 V (J4.3 contract 3.135–3.465 V) | DECISIONS 76; power-stage README |
| RAIL_OK | GPIO35 | GPIO35 as captured; TCA9555 P02 after the J13 merge | CONTROLLER-REQUEST.md addendum 3 item 12 |

Kconfig / config symbols: every `TEMPER_POWER_*` name in the procedure exists. The record's provisional values equal the
Kconfig defaults: F_MAX 60000, F_MIN 35000, PAN_Q_MAX_X10 100, PAN_R_MIN_MOHM 800, TANK_CEILING_DA 175, VSW 100,
CT_ZC 0 / n, LINE_ZC 0, EST_ERROR 100000, VBUS / CT_MON / RMS trims 0. Every backticked firmware constant is present in the
firmware sources (gate-checked).

## Firmware / board disagreements (for the owner; nothing changed)

1. **`TEMPER_POWER_TANK_CEILING_DA` allows 28 A (range 100–280); the s53 H bank stops the ladder at 24 A.** Only the silk fit
   mark and the procedure enforce it. The gate reports this as a FINDING on every run. Options: cap the range at 240 for an
   H lot, or add a bank-variant field that `config_ok` checks.
2. **`TANK_PEAK_TRIP_MAX_A` = 64.5 A against the B9 CT low corner of 64.55 A: 0.05 A margin.** That corner is computed with
   the CT network at a uniform 85 °C. Only R39 has a B3 row (78.1 °C max). R40–R46 have none, and a hotter network moves
   the corner down. It holds today, but it rests on the provisional B10.
3. **Stale firmware citations (values still correct on s53):**
   - `tank_freq.h:83` and `n21_binding.h:87` cite the "stage-15 CT band low corner 64.55 A".
   - The Kconfig help still says "the hardware (stage 15) is sized for 28 A" and points to the superseded
     `ENCLOSURE-REQUEST.md`.
   - The Kconfig help step numbers do not match the procedure:

     | Kconfig field | Kconfig help says | Procedure step |
     |---|---|---|
     | VBUS_OFFSET | 2 | 1 |
     | VBUS_GAIN | 4 | 1 / 5 |
     | CT_MON_ZERO | 2 | 1 |
     | RMS_GAIN | 5 | 1 / 6 |
     | EST_ERROR | 8 | 7 |
     | LINE_ZC | 2 | 5 |
     | VSW / CT_ZC | 7 | 4 |
4. **`TANK_PEAK_PICKUP_A` = 3.0 A (DECISIONS 9's stack); the s53 OCP Kelvin pickup model is 4.17 A at 60 kHz.** That model
   is the shunt comparator's path, so it may not apply to the CT_MON peak trip. The owner should confirm.
5. **`CTRL_GPIO_RAIL_OK_RB` = GPIO35.** It is correct for the controller as captured and changes with the J13 merge, which is
   in progress in `ps-integrate`. The procedure marks every dependent step "pending the J13 merge".

Agreements the gate now checks on every run:
- `N21_CT_MON_V_PER_A` 0.015 V/A = R39 / T1 ratio.
- `controller_calcs.d11_receiver`'s k = the board's R30 / (R26..R30), 8.3342 × 10⁻³.
- The 230.9 V over-range sits below the OVP low corner with its +6 %.
- The F_MAX range top equals the 60 kHz PS2 window top (S18).

## Other records that disagree with s53 (reported, not changed)

- **`hardware/CURRENT.tsv` and `hardware/README.md` pin native21-stage15b**, board `9a9c43c6…`, not s53. They sit untracked
  in the main checkout (`/Users/bennet/Desktop/temper/hardware`) and are absent from this branch. Not re-pinned.
- **The power-stage `README.md` J4 table is stale against s53:**
  - it lists J4.16 as SELV_GND, but the s53 netlist has `line_zc` there (H9);
  - it gives BUS_FAULT as "≈61 A shunt / ≈55 A CT (50.9–59.5 A)";
  - the barrier list still names PS1 IRM-20-15, deleted at s38.
- **`OPEN-ITEMS.md`'s header still names s51 as the board of record.**
- **The B13 row cites "D3 stand-off 295 V"**, but the ledger gives the 30KPA150CA string as 300 V.
- **`BRINGUP-PROBES.md`'s fixings table** (generated by `plan_board_only21.py`) still says H2 may take metal and H9 / H10
  nylon, but DECISIONS 76 leaves H2, H9 and H10 empty. PROTOTYPE-LOT's "Fixings … H2–H7" uses R43's numbering.

## Still provisional

- **B3–B6 band record:** s52's own B3 solve, carried to s53 (kelvin_budget.py s53 note, DECISIONS 75: no OCP part or OCP-net
  copper change). s53 has its own Kelvin run. The s53 B3 runs are not in the tree, so `bands52.py`-style re-solving was not
  possible here.
- **B10:** the CT network temperature for R40–R46.
- **B13:** a datasheet-table interpolation, not an Infineon guarantee. The pass rule is the simulated window.
- **B15a–d:** SPICE bounds; the bench measures them.
- **Bench supplies:** the 0.2 A limit on J4.3 (pre-J13 breakout). The single hv_ret–PE tie in steps 2–4 is a design call
  (it keeps the floating HOT domain at PE while BR1 is out), not a cited rule.
- **Controller side:** every step marked "pending the J13 merge".

## Open questions

1. **CT at 28 A (B boards only).** If the 4.17 A pickup model applied to the CT path too, the floor would be 65.34 A, above
   the CT low corner of 64.55 A. Does the pickup term apply to T1's secondary path? The procedure applies 4.17 A to the
   shunt only.
2. ~~Step 9a.6 ceiling~~: closed by the owner default (2026-10-18): 17.5 A until a ladder step passes its thermal gate.
3. ~~24 V back-feed~~: closed by the owner decision (2026-10-18): BR1 is left out and PS2 runs from its own input.
4. **The 0.05 A margin** of disagreement 2: recorded as OPEN-ITEMS S29 and COMMISSIONING H14, recommending B3 thermal rows
   for R40–R46. No firmware cap changes.
5. **JLC order:** `fab/bom-jlcpcb.csv` still lists BR1 for JLC assembly. Deselect it at order, as RV1 (OPEN-ITEMS B16).

## Owner decision 2026-10-18: BR1 out for bring-up (addendum)

- **Why:** PS2.4 is on v24_raw with no series diode (frozen netlist), so a 24 V back-feed would drive an unpowered MEAN WELL
  output. MEAN WELL gives no statement allowing that. BR1 is the only part with pins on both l_filt / n_filt and bus_p /
  hv_ret (B18, checked by the tool on every run).
- **Steps 2–4:** BR1 not fitted. The inlet is fed at 120 V from the isolation transformer through the analyser, so PS2 runs
  through J3 and the bench DF110S TCO (`bench-sink-r1/README.md` D5, branch `study/bench-sink-r1`). The bus is dead
  (step 2) or fed by the isolated, current-limited DC supply (steps 3–4).
- **DC supply connection (B19):** C6.1 (bus_p) / C6.3 (hv_ret), through-hole leads of one part, with soldered tails. The tool
  picks the pad pair from `native-21/layout/pads.json`: the bus_p / hv_ret pair on one part farthest from any other net's
  pad. That is 18.9 mm to L1.3 and 24.3 mm to C2.2, both n_filt. There is no bus test pad. C40 / C41 sit farther from
  mains, but gate-drive pads are 6–7 mm away, a clip-slip risk in step 4.
- **Hazards and reference:**
  - Mains is on the HOT input side from step 2 (inlet, l_filt / n_filt, F2 / J11, J3, PS2 input), so use isolated probes
    only.
  - With BR1 out, the bus and the HOT domain float. They are tied to PE at one point (hv_ret, the DC supply's negative, to
    the bench PE stud) in steps 2–4.
  - The tie is removed before BR1 is fitted, and its absence is checked with a DMM.
- **Step 4b:** the owner fits BR1 per the bench-sink procedure (through-hole, bottom preheat ≥ 100 °C), then repeats the
  bench-sink insulation test and power-on check before step 5. Step 5 drops the old 24 V hand-back.
- **Removed:** the provisional 24 V back-feed and its 0.5 A limit.

## Staging branch reconciliation, 2026-10-18 (addendum; `study/proto-bringup-merge`)

**J13 merge as landed.** The merge landed: controller `controller-j13-merge` C49 / C50, power-stage DECISIONS 79, firmware
`0550fffcf`. On the staging branch the gate failed on `CTRL_GPIO_RAIL_OK_RB`, which the firmware no longer has. The symbol
rule caught the drift, and 2 tests failed with it. Every "pending the J13 merge" in COMMISSIONING.md is now the as-landed
fact:
- **Ground rules:**
  - The controller is the C49 board only. Its logic 15 V comes in on J13 through D9.
  - J4.1 is read on GPIO35 through controller R124 / C97 / R123, and J4.1 never sees 15 V.
  - RAIL_OK_RB is TCA9555 P02, read from the expander snapshot.
  - The C48 controller is never connected.
  - The J4 breakout stays, as an inline breakout and as an option for the power-board-only items.
- **Step 1:** the bench 15 V goes into J13, with the blower unplugged and J4.1 open. New check: GPIO35 reads low with J4.1 open.
- **Step 2:** the controller is on the bench 15 V into J13, and PS3 first feeds J13 at step 5's mains sequencing.
- **Item 2.6:** the checks run (no N/A). They close B13 H2 and C50's "GPIO35 not on hardware" risk, with C49's
  `bias_good` design levels cited.
- **8c.7:** the two J13-unplug items become PS3-loss checks: the controller powers down and the pads, PERMIT and DIS fail
  safe. They add C50 accepted risk 1, a scope of the logic rail at blower start and PS3 hiccup, judged against C49
  `merge_rail`.

**BRING-UP.md** (`08-manufacturing-package/native-21/`, from 15a0a9b12) is rewritten as a short overview that points to
COMMISSIONING steps. Its contradictions with the owner decisions are gone:
- **The bench feed:** its stage 2 left the PS2 / V24_RAW feed TBD. Now BR1 is out, PS2 runs from mains in steps 2–4, and the bus comes from DC.
- **The dim bulb:** its stage 3 applied mains through the dim bulb with BR1 fitted. Now the dim bulb is used only at step 5, after step 4b.
- **Hot-air gear:** removed, because JLC places U41 / U42 (consign-r1).
- **The hand-fit list:** "15 hand-fitted parts" becomes BR1, RV1, the F1 clips and the F1 cartridge (consign-r1 answer 4).
- **The coil:** its "88 µH ±10 %, loaded ≥ 53.4 µH, DCR ≤ 0.12 Ω" is replaced by the coil study's M1–M5 plan and pass levels, and the spec version is now an open owner item.

The overview keeps:
- the GFCI → isolation transformer → variac → dim-bulb chain;
- the stop conditions, now pointing to their steps;
- the records list.

It points to `bench-sink-r1/README.md` revision 3 (one common sink, a shim selected per JLC-soldered FET) and to
`output/temper-coil-r1/`.

Decisions made in that rewrite:
- **The dim bulb at step 5:** it is in for the first raise and items 1–2 with the bridge idle, and taken out before item 3's
  first bench session (a series lamp moves the line the firmware measures). COMMISSIONING step 5 now says so too, and its
  "Isolation" rule names the GFCI and the overview.
- **Touch current:** it moved out of the first-power chain. IEC 60990 measures against an earthed supply, and behind a
  floating isolation transformer it reads near zero.

**Gate extended to BRING-UP.md.** BRING-UP.md has no generated block, so the table rule does not apply, but the other rules
do. `--check` now also:
- runs the prose rules on it (stage claims, power-board resistor values, Kconfig and firmware symbols);
- requires its introduction to name the board of record;
- fails on any "step N" or "step N item M" that COMMISSIONING.md does not have.
That last rule catches a renumbered or deleted step leaving a dangling pointer. 11 new tests cover it; one of them is the J13
drift itself (38 pass). Negative control: `results/negative-control-proto-merge-25c01539a.txt`, the two files as merged,
which fail on `CTRL_GPIO_RAIL_OK_RB` and on the overview's "s53" intro. The gate does not catch a *procedural* contradiction,
such as BR1 fitted at the wrong step. Those were reconciled by hand, and keeping BRING-UP.md free of its own numbers is what
limits them.

**Coil spec: R1 against the committed 53.43 µH floor** (`scripts/coil_floor.py` → `results/coil-floor.{md,json}`, from the
coil study's committed `pans.json` and `trim_heating.json`; no re-solve). Under the committed spec:
- **Row 3 fails on the reference class.** Cast iron at nominal µ gives 46.10 µH (Ø240) and 50.73 µH (Ø180; the spec's
  reference pan is 180–220 mm).
- **Row 3 passes in 6 of 24 ferrous pan cases, all at the high-µ bracket** (430, tri-ply and cast iron at µ high). At nominal
  µ every class fails; the closest is 430 at Ø180, 53.38 µH, 0.05 µH short. Carbon steel fails at every µ.
- **No tune state reaches the floor:** R1 plus the spare turn (89.85 µH free-air) gives 50.39 µH on cast iron Ø240.
- **Row 3b (ratio ≥ 0.60) also fails** on the reference case: 0.568.
- **Row 1 (79.2–96.8 µH) passes** for R1 (81.1 µH).

Under the uncommitted 70 µH version (41.5 µH floor; the one R1 was designed to), the reference case passes, and 17 of 24 cases
pass.

The committed floor is derived from a 300 nF ±10 % tank and `PLL_MIN_FREQ_HZ` 44 kHz (its §2), not from native-21's
5 × 100 nF bank (B14) and 35–60 kHz loop (B16).

Reported, not resolved: the owner decides which spec version is of record. Until then the bench uses the coil study's levels.

## Files

- `firmware/components/power/COMMISSIONING.md` (re-based; board table between the markers).
- `firmware/tools/commissioning_board_table.py` (generator and check), `firmware/tools/test_commissioning_board_table.py`.
- `.github/workflows/firmware-tests.yml` (the step, numpy, trigger paths).
- `results/` (check, negative controls, re-runs).
- `zapote/power-stage-120v/OPEN-ITEMS.md` rows S29 (CT margin) and B16 (BR1 not fitted at JLC).
- Staging addendum: `zapote/power-stage-120v/validation-results/08-manufacturing-package/native-21/BRING-UP.md` (rewritten),
  `scripts/coil_floor.py`, `results/coil-floor.{md,json}`, `results/check-proto-merge.txt`,
  `results/negative-control-proto-merge-25c01539a.txt`.
