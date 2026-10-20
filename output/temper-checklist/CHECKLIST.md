# Temper: checklist from today's state to (a) a working prototype and (b) a production run

**As of 2026-10-19.** Read-only audit of the repo. Nothing was built, run, ordered or sent, and no git state was changed. Web search was not used, so there are no web-sourced figures in this file. Figures quoted from repo files that the repo itself sourced from the web (for example the Litz class or the lug ratings) keep the repo's own label.

**Method.** Five read-only research passes (power board, controller, sensor, enclosure/UI/compliance, firmware/test/supply) plus my own read of the coil study. I re-checked these citations myself:
- the CPL preview's "not checked" list;
- the MAX31865 automatic fault cycle and the 1526/45722 threshold words;
- `TANK_PEAK_TRIP_MAX_A` 64.5;
- the UI-board parts;
- the coil-stud decision and the Würth 7466004R thread;
- every coil-r1 row;
- the 12A3 references;
- the coil-spec versions.

Other line numbers come from the research passes and were not all re-opened. An auditor should treat them as "where to look", not as quotes. Sources are listed in [CHECKLIST-SOURCES.md](CHECKLIST-SOURCES.md).

**Headline fact: there is no bench measurement anywhere in the project.** Every margin below is a desk model, a datasheet value or a vendor read:
- `PS/README.md:137`: "Physical assembly, powered test, EMI, insulation and certification: NOT RUN".
- `NAT/BRING-UP.md:1`: "prepared, NOT run".
- `PS/DECISIONS.md:3061` (item 80): "Nothing in it has been run".
- `COIL/README.md:3`: "modelled only".
- `SR3/bench/README.md:23-30`: survey not run.

**Row counts (379 rows):**

| Status | Rows | Note |
|---|---|---|
| OPEN | 196 | |
| IN PROGRESS | 82 | |
| DONE | 50 | Mostly decisions, CAD geometry, vendor-viewer checks or committed logs; no DONE rests on a simulation alone |
| OWNER-ONLY | 41 | |
| BLOCKED | 10 | |

By phase: Prototype 84, Production 81, Both 213, one superseded.

## Legend

**Path prefixes**

| Prefix | Path |
|---|---|
| MAIN | `/Users/bennet/Desktop/temper` (main checkout, local `main`) |
| PSI | `/Users/bennet/Desktop/temper/worktrees/ps-integrate` (branch `codex/power-stage-integration`) |
| PS | `PSI/zapote/power-stage-120v` |
| NAT | `PS/validation-results/08-manufacturing-package/native-21` |
| OI | `NAT/owner-items` |
| CAND | `PS/validation-results/11-candidates` |
| FW | `PSI/firmware` (the firmware that matches C49) |
| COIL | `PSI/output/temper-coil-r1` |
| CJ | `/Users/bennet/Desktop/temper/worktrees/ctrl-j13/zapote/controller` (branch `controller-j13-merge`) |
| UIB | `/Users/bennet/Desktop/temper/worktrees/ctrl-j13/zapote/ui-board` (same branch) |
| SR3 | `MAIN/output/temper-sensor-r3` |
| R43 | `MAIN/output/temper-manufacturing-r43` |
| OC | `MAIN/output/temper-owned-controls` (the R44 "owned controls" programme) |
| AF1 | `MAIN/output/temper-airflow-r1` |
| SPEC | `PSI/docs/hardware/TANK_COIL_SPECIFICATION.md` |

**Tracking tags** (after each evidence path)

| Tag | Meaning |
|---|---|
| {T} | Committed on the named branch, clean |
| {M} | Committed, but with **uncommitted edits** in the working tree |
| {U} | **Untracked** in that checkout. A committed copy exists elsewhere, named in the row |
| {U\*} | **Untracked and never committed on any branch.** Data-loss risk |
| {OM} | Committed only on `origin/main`. The local copy is missing, older or untracked |
| {CJ} | Committed only on `controller-j13-merge` |

**Evidence kinds** (in the Decision and Evidence cells)

| Tag | Meaning |
|---|---|
| [DEC] | Recorded decision (a DECISIONS item or README decision) |
| [ASM] | Assumption, provisional value or unverified figure |
| [SIM] | Simulation, model or hand calculation |
| [CAD] | CAD or geometry check |
| [CODE] | Code, or a committed host-test log |
| [DS] | Datasheet value |
| [VEN] | Vendor stock/price read or quote (dated; not a reservation) |
| [PLAN] | Procedure or plan only |
| [BENCH] | Bench measurement. **None exists** |

**Status:** DONE = closed, with evidence of the kind the item needs. IN PROGRESS = work exists but a bench, vendor or certifier confirmation is missing. OPEN = not started, or no decision. BLOCKED = waits on a named dependency. OWNER-ONLY = a purchase, an outreach, sending something, or the owner's own call.

**Phase:** Prototype / Production / Both.

**Owner:** Claude (Claude can do it) / owner / bench (needs hands and instruments) / external (vendor, certifier, counsel).

---

## 0. Programme level

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| G-01 | Overall maturity: nothing built or measured | Both | IN PROGRESS | none | PS/README.md:137 {T}; NAT/BRING-UP.md:1 {T}; PS/DECISIONS.md:3061 {T}; COIL/README.md:3 {T} | Every "pass" in this file is desk evidence | owner+bench | Orders (PWR-82, CTL-05) | The first bench data will move many rows at once |
| G-02 | A written exit criterion for "working prototype" (what must heat, at what power, for how long, with which sensor) | Prototype | OPEN | none: not found in repo as one definition | not found. Closest: NAT/PROTOTYPE-LOT.md gates {T}; COIL/README.md §5 {T} | An auditor cannot sign "prototype done" without it | owner (Claude can draft) | — | Proposal: native-21 + C49 + R1 coil heats a ferrous pan at ≤ 17.5 A under the pan RTD with all trips verified |
| G-03 | Product requirements document (rated power, setpoint range, pan classes, noise, markets) | Production | OPEN | none: not found | Closest: PSI/docs/ENVIRONMENTAL_SPEC.md:1-15 {T} (2025-12-17); PSI/docs/REGULATORY_COMPLIANCE.md {T} | Rated power and the market set the standard, the cooling and the nameplate | owner | — | See G-04 and CMP-04 |
| G-04 | Rated or delivered power | Both | OPEN | none for the product. The release ceiling of 17.5 A tank is a decision (G-05) | Old docs: "1800 W (US)" in docs/REGULATORY_COMPLIANCE.md:65 {T}. "At 18 A, pooled pan power is about 650 W at 120 V" in PS/DECISIONS.md:2029 {T}. Coil model: median 1041 W (model basis) / 720 W (priors basis) at 17.5 A, in COIL/README.md:110-116 {T} [SIM] | The three figures use different pan and coil bases; none is measured | owner+bench | Bench power runs (TST-09) | **Contradiction** (C-list #1). Nameplate and marketing cannot be set yet |
| G-05 | Tank release ceiling 17.5 A | Both | DONE (decision) / IN PROGRESS (basis) | [DEC] item 61: 17.5 A, still air, 61 °C bay, margin +1.3 K, binding row R10 | PS/DECISIONS.md:2193 {T}; FW/components/power/Kconfig:35-39 {T} | The board-thermal model sets it [SIM] | Claude (docs) | — | PS/OPEN-ITEMS.md:25,105,112 still say 18 A (**contradiction**). Going above it needs board-face airflow (PWR-44) |

## 1. Power board (native-21, board of record s53)

### 1a. PCB fabrication

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| PWR-01 | Board of record | Both | DONE (candidate, not released) | [DEC] item 75: s53, SHA-256 82af7bd9…, copper key b7a0bc5790b9; 290 × 190 mm L outline, 4 layers | PS/DECISIONS.md:2972 {T}; NAT/fab/FAB-NOTE.md:3-24 {T} | — | — | — | PS/OPEN-ITEMS.md:3 still says s51; PS/README.md:3 says 240 × 160 (**contradictions**) |
| PWR-02 | Reproducibility of the routed board | Both | IN PROGRESS | [DEC] the .kicad_pcb/STEP live outside git and are regenerated from copper.json by chain.sh | NAT/review-packet-s53/README.md §2-3 {U}; PS/native-21/section.kicad_pcb {U} | A board of record should be re-creatable byte for byte | Claude+owner (commit) | — | Thermal results move 0.1 K between builds of the same copper (PS/DECISIONS.md:2998) |
| PWR-03 | Stackup | Both | DONE | [DEC] JLC041622-7628, 1.6 mm, 2 oz outer and inner (61 µm finished inner), 0.5 mm core [VEN JLC stackup API] | PS/FAB-JLCPCB.md:12-14 {T}; PS/native-21/stackup.json {T} | — | — | — | PS/stackup.json:20,33 (old) says Nan Ya NP-155F (**stale file**) |
| PWR-04 | Finish, vias, DFM | Both | DONE | [DEC] ENIG; 0.3 mm vias epoxy-filled and capped; JLC DFM PASS | NAT/fab/FAB-NOTE.md {T} | — | — | — | Via counts in FAB-NOTE (765/750/859/876) are stale against the s53 census (777 vias, 99 plated pads) |
| PWR-05 | Laminate CTI | Both | IN PROGRESS | [DEC] item 41: order names "KB6164 - TG135" (Kingboard, CTI PLC 3 = IIIa, 175 V) | PS/DECISIONS.md:1309 {T}; NAT/sourcing/inquiries/CTI-RESEARCH-2026-10-14.md {T} | The 8.0 mm floor assumes material group IIIa | external (JLC) | PWR-06 | **Zero margin** to CTI 175 V |
| PWR-06 | Laminate UL scope at 2 oz inner copper | Both | OWNER-ONLY | none | PS/OPEN-ITEMS.md:42 (S12) {T}; OI/JLC-LAMINATE-QUESTION.md {U} ("send-ready, not sent") | The Kingboard UL row for KB-616x allows 35 µm of inner copper; the board has 61 µm [DS] | owner (send) | — | Order gate 3. A "no" means a different laminate or a stackup change |
| PWR-07 | Stencil thickness | Prototype | OPEN | none | PS/OPEN-ITEMS.md:61 (B6) {T} | J2/J5 want 150 µm paste | owner at order | — | — |
| PWR-08 | Stale FAB-NOTE pre-order tier (still asks for FEM/F6, which item 77 closed) | Prototype | OPEN | — | NAT/fab/FAB-NOTE.md:29 {T} against PS/DECISIONS.md:3031-3040 {T} | The vendor note must match the record | Claude | — | — |
| PWR-09 | Bare-board price | Production | DONE (quote read) | [VEN] $17.28/board at 500 (4 layers); 6 layers $19.11, not adopted | PS/DECISIONS.md:1263-1281 (item 40) {T} | — | — | — | Gerber quote 2026-10-14, not an order |

### 1b. Assembly

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| PWR-10 | Assembly policy consign-r1: JLC does as much as possible | Both | IN PROGRESS | [DEC-draft] JLC assembles 92 of 95 lines (19 Basic / 73 Extended), including through-hole parts it hand-solders | CAND/consign-r1/DECISIONS-DRAFT.md:1-12 {T}; NAT/PROTOTYPE-LOT.md:34-66 {T}; NAT/fab/FAB-NOTE.md {T} | The owner wants JLC to assemble everything it can (owner 2026-10-18) | Claude (number it) | — | **Not numbered in DECISIONS.md** (0 mentions), but already applied in FAB-NOTE |
| PWR-11 | Owner home-bench through-hole: BR1 GBJ2510-F, RV1 TMOV20RP175E, F1 clips 2 × 01250003H, F1 cartridge | Prototype | OWNER-ONLY | [DEC] DNP at JLC, fitted by the owner on a ≥ 100 °C bottom-preheated board | NAT/fab/hand-assembly-extras.csv {T}; NAT/fab/bom-jlcpcb.csv {T} | Through-hole only on the home bench | owner+bench | Preheater (order gate 4a) | PS/OPEN-ITEMS.md:70 (B16) says BR1 is still for JLC; the BOM says DNP (**contradiction**) |
| PWR-12 | FET buy and consignment: IPW65R018CFD7 × 120 from DigiKey | Prototype | OWNER-ONLY (prepared, not ordered) | [DEC] one lot, $1,281.51; consign 84 to JLC, keep 36 | NAT/PROTOTYPE-LOT.md:102-112 {T} [VEN 2026-10-17] | One lot for matching; JLC's own price is about $20.64 each | owner | — | DigiKey 459 in stock, 8-week lead at the read |
| PWR-13 | CPL: 31 NEEDS-PREVIEW rows; the bank and D3/D17 have no LCSC number | Prototype | OWNER-ONLY | none | NAT/PROTOTYPE-LOT.md (CPL row, gate 6) {T} | Rotations must be confirmed in JLC's viewer | owner (viewer) | — | The controller's first upload placed 5 ICs wrong (CTL-08); expect the same here |
| PWR-14 | Lead-trim rule ≤ 2.5 mm below the board | Both | DONE (rule) | [DEC] | PS/ASSEMBLY.md:49 {T}; PS/DECISIONS.md:401 {T} | Untrimmed TO-247 leads come within 0.8 mm of the PE base | bench (verify) | — | Inspection item for the JLC lot |
| PWR-15 | FET seating before solder (coplanarity for the sink stack) | Both | OPEN | [DEC] a seat-before-solder fixture, coplanar within 0.05 mm | OI/m11/SINK-DRAWING-NOTES.md "Acceptance" {T}; PS/DECISIONS.md:473 {T}; CAND/bench-sink-r1/README.md §8, Q10 {T} | Modelled tab-plane spread 0.270–1.800 mm against 0.0195 mm of compliance [SIM] | owner+external | — | **Contradiction:** the consign-r1 remark has JLC hand-solder the FETs on their lead shoulders (FAB-NOTE remarks). The production sink stack depends on this |

### 1c. BOM, stock, lead time

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| PWR-16 | Prototype lot of 20 boards: stock | Prototype | IN PROGRESS | [DEC] stock gate sized at 20 boards | NAT/PROTOTYPE-LOT.md:74-100 {T}; OI/order/proto-stock-s52-20boards.csv {T} [VEN 2026-10-15/16/18] | 0 short lines on dated reads | owner | — | "A distributor read is not a reservation": re-read on order day |
| PWR-17 | Production L1 B82726S2203A020 | Production | OWNER-ONLY | [DEC] stays the production part; the prototype uses B82726S2243A020 (s52, DECISIONS 74) | PS/OPEN-ITEMS.md:56-57 (B1, B15) {T} [VEN] | 0 authorised stock, 29-week lead; sets the 500-unit build date (about 2027-05 if ordered now) | owner | — | The EMI result depends on which L1 is fitted (PWR-75) |
| PWR-18 | 28 A bank part B32643B8104J000 | Production | OWNER-ONLY | none (not pre-ordered) | PS/OPEN-ITEMS.md:37 (S28) {T} [VEN] | 28-week lead, MOQ 2080. The prototype H bank caps the ladder at 24 A | owner | — | — |
| PWR-19 | 500-board short lines and pre-orders | Production | OWNER-ONLY | [DEC] owner action 7: pre-order L1, PMEG6030EP, LM2901BIDR, RT0603BRD07750RL, LM4050AEM3-2.5 (≥ 550), TLV3201 | PS/OPEN-ITEMS.md:125 {T}; NAT/sourcing/study-2026-10-15/README.md:190-209 {T} | 13–15 lines short at 500 | owner | — | Also 2EDR8259X ("39 wk if missed"). Counts differ: scorecard 13 vs 14 (**minor contradiction**) |
| PWR-20 | Power-board parts cost | Production | IN PROGRESS | none | NAT/PROTOTYPE-LOT.md:68-70 {T} ($174.99 at 500); PS/validation-results/10-benchmark/scorecard-native21s53.json {T} (v1 $201.42 / v2 $175.04 at 500; $305.16 / $274.93 at 5) | Dated reads, not quotes | Claude | — | PS/OPEN-ITEMS.md:72 says $171.71 (s45). The scorecard prices 58 of 93 lines at class defaults (SUP-05) |

### 1d. Power devices, thermal interface, heatsink

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| PWR-21 | Bridge devices | Both | DONE | [DEC] Q2/Q3/Q5/Q6 IPW65R018CFD7 (650 V CFD7 MOSFET, TO-247-3). No IGBTs | PS/native-21/frozen/default.csv {T} | — | — | — | Firmware text still says "IGBT" (FW/config.yaml:299-300; FW-13) |
| PWR-22 | Production insulator between FET tabs and sink (M11) | Production | IN PROGRESS (decided, not sourced) | [DEC] two shared 2.00 mm AlN tiles (≥ 150 W/mK, Kyocera AN216A class, lapped, flat ≤ 0.03 mm), 6.5 mm overhang; tile A = Q5+Q6, tile B = Q3+Q2+BR1; reinforced by thickness (IEC 60335-1 29.3.1) | PS/DECISIONS.md:268-281, 293-304 {T} | Sink is PE-bonded and user-touchable, so HOT↔PE needs reinforced insulation | external (certifier, vendor) | PWR-23, CMP-15 | Whether reinforced insulation is required is still a certifier question |
| PWR-23 | AlN tiles: RFQ and purchase | Both | OWNER-ONLY (prepared, not sent) | [DEC] item 80: buy 4 stacks for the lot | PS/DECISIONS.md:299-304, 3056-3058 {T} [VEN estimate ≈ $350/stack; 4 stacks ≈ $0.7–1.3k] | Custom cut from 2.032 mm plate (Valley AlN-110 / Almath) | owner | — | Unquoted custom part |
| PWR-24 | Thermal compound | Both | BLOCKED | [DEC] Electrolube HTCP20S (2.5 W/mK, 42 kV/mm) on both faces, below Z70 only [DS] | PS/DECISIONS.md:300 {T}; CAND/c53-astra-results/local/m11/CONFIRMED.md row 2 {T} | — | owner | Availability: "from 30 December 2026" (Conro); Silmid none (47 business days) [VEN] | No second compound named: **not found** |
| PWR-25 | Interface resistance | Both | IN PROGRESS | none | OI/m11/stack-calc.txt {T}; OI/m11/RECOMMENDATION.md:152 {T} [SIM] | 0.40–0.63 °C/W per FET (conservative) against a 0.7 °C/W budget | bench | Parts (PWR-23/24/26) | Rcs optimistic 0.106–0.168 °C/W; tab-to-PE 5.8–9.1 pF |
| PWR-26 | Clamp and mounting force | Both | OPEN | [DEC] stainless 1.4310 comb spring through a 3 mm FR-4/G-10 strip; no screw through any TO-247 hole; 3 × M3 into the bar; custom RFQ | PS/DECISIONS.md:276, 474 {T}; OI/m11/RECOMMENDATION.md:235 {T} | Screwless clamping keeps creepage | owner+external | — | **Force stated three ways:** 60–80 N/device (DECISIONS:276); "≥ 60 N, target 80" (RECOMMENDATION:235); acceptance 45–102 N, capped at Infineon's clip maximum (DECISIONS:474) |
| PWR-27 | Torques | Both | IN PROGRESS | [DS] PE ear M4 nyloc 1.2 N·m; J2/J5 7466004R 1.2 N·m; J1 0.5–0.6 N·m (Phoenix p.3); bench BR1 M3 ≤ 0.56 N·m | OI/m11/SINK-DRAWING-NOTES.md {T}; PS/DECISIONS.md:1342 {T}; CAND/c54-j1-thermal/README.md {U} | — | bench | — | Retention and pull are untested (OPEN-ITEMS B10 list) |
| PWR-28 | BR1 gap pad thickness | Both | OPEN | [DS] Bergquist GAP PAD HC 3.0 (3.0 W/mK, > 5000 Vac) | PS/DECISIONS.md:275, 301 {T} (0.5 mm / 0.020"); PS/DECISIONS.md:421, 476 {T} and SINK-DRAWING-NOTES.md:34 {T} (1.0 mm / 0.040") | Rcs ≈ 0.37–0.38 K/W [SIM est.] | Claude (reconcile) + owner | — | **Contradiction**; changes the stack height |
| PWR-29 | Sink-stack isolation test | Both | OPEN | [PLAN] type test 3000 Vac 60 s on the clamped assembly; routine 2000 Vac 1 s; partial discharge not assessed | PS/DECISIONS.md:280, 385 {T}; CAND/bench-sink-r1/README.md Q8 {T} | Reinforced barrier qualification | bench/external | Parts | Gates mains-connected operation, not the bench lot (NAT/fab/FAB-NOTE.md:34) |
| PWR-30 | Production heatsink S8 | Production | IN PROGRESS | [DEC] 6063, 8 mm base, 15 × 1.5 mm fins, PE-bonded, chassis-carried, brackets ≥ 8 mm from HOT; requires R_SA ≤ 0.29 °C/W at ≥ 13 CFM delivered | PS/DECISIONS.md:378-386, 469-472 {T} [SIM requirement.py: 125.9 W, Tj 125 °C, 50 °C air] | Supersedes 0.15 °C/W at ≥ 20 CFM | owner+external | Drawing/quote not found | Spreader-bar CNC prepared, not ordered |
| PWR-31 | Sink load and contingency sink K1 | Production | OPEN | [DEC] switch to K1 (R_SA 0.214) if the bench sink load exceeds 125 W | PS/DECISIONS.md:614-617 {T} [SIM] | At 28 A: 132.8–149.9 W hard-switched against 67.8 W ZVS | bench | First switching data | PS/DECISIONS.md:1643 says the K1 result "was not reproduced" |
| PWR-32 | Bench sink for the prototype (bench-sink-r1) | Prototype | OWNER-ONLY (prepared, not ordered) | [DEC] Wakefield 511-3M, SIL PAD 2000 0.010" strip, brass shims by feeler gauge, screwless Lee-spring clamp 60–102 N, sink to PE, NTCALUG01A NTC, Cantherm DF110S TCO | CAND/bench-sink-r1/README.md §1, §9 {T} | Parts about $360 [VEN est.] | owner | — | "No 1250 V AC hipot on the board" (README:13) |
| PWR-33 | Bench-sink thermal limits | Prototype | IN PROGRESS | [SIM] Tj 87.1 °C at 17.5 A / 30 °C; 111.4 °C at 22 A (fan needed); 182.8 °C at 28 A without a fan (not allowed); ZVS lost → 178.6 °C at the 95 °C firmware trip | CAND/bench-sink-r1/README.md §4 {T} | Sets the bench envelope: ≤ 17.5 A without a fan | bench | — | Losing ZVS on the bench sink overheats the FETs before the sink trip |
| PWR-34 | Firmware sink model constant | Both | OPEN | none | FW fan_guard.h:26 {T} (FAN_RTH_HEATSINK 1.0 °C/W "approx") against PS/DECISIONS.md:472 (≤ 0.29) | Stale constant | Claude | — | — |

### 1e. Fan and airflow (board side)

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| PWR-35 | Production blower | Both | IN PROGRESS | [DEC] Delta BFB1012VH-F00, 12 V, 1.42 A typ / 2.70 A max [DS]; fed by PS3 → controller buck → J13 | PS/DECISIONS.md:618, 621-628, 1504 {T} | — | bench | — | Airflow at the operating point is unmeasured (ENC-11) |
| PWR-36 | Fan control law | Both | IN PROGRESS | [CODE] sink setpoint 88.6 °C, off below 50 °C, drive cap 0.8; stall = < 300 rpm for > 1 s → 10 % power cap (PROVISIONAL) | FW/components/control/thermal_mgmt.h:219-227, 278-281 {T} | — | bench | — | — |
| PWR-37 | Blower tach pulses per revolution | Both | OPEN | [ASM] 2 ppr, "unverified" | FW/config.yaml:211-221 {T} | Not in the Delta spec | bench | — | Wrong ppr = wrong stall detection |
| PWR-38 | PS3 hiccup vs fan start current | Prototype | OPEN | none | CJ/DECISIONS.md:713, 723 {CJ} | PS3 overload hiccup at 4.98–5.85 A resets the controller (fails safe); trips only if the fan draws ≈ 4.96 A at 12.4 V | bench | — | Fan start/lock current and the hiccup timing are in no datasheet |
| PWR-39 | 28 A route: second (face) fan or jets plus base flow | Production | OPEN | none | PS/OPEN-ITEMS.md:33, 35 (S24, S26) {T} [SIM] | 28 A needs board-face h ≥ 16 W/m²K at 61 °C and ≥ 3.0 m/s across the bank | owner | Enclosure R45 (ENC-13) | No tach or stall clamp exists for a face fan (FW-38) |
| PWR-40 | Board-face h measurement | Both | OPEN | [PLAN] unpowered DC B3 inversion, ≥ 3 enclosure + fan sets (DECISIONS 69) | CAND/bench-h-2026-10-16/results.md {T} | Calibrates the board-thermal model | bench | An enclosure mock-up | — |

### 1f. Board thermal

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| PWR-41 | Release margin at 17.5 A | Both | IN PROGRESS | [DEC] item 61 | PS/DECISIONS.md:2193 {T}; NAT/review-packet-s53/README.md §4 gate 18 {U} [SIM] | +1.3 K; binding row R10 (68 Ω 2512 gate resistor) | bench | — | Thin margin on a model |
| PWR-42 | Still-air shortfall at 22/28 A | Production | OPEN | none | PS/OPEN-ITEMS.md:33 (S24) {T} [SIM] | c22/c28 miss by −50.8 K (laminate) and −51.0 K (rated part) | owner | PWR-39 | Power above 17.5 A depends on the enclosure |
| PWR-43 | BOM swaps proposed to lift the margin | Both | OPEN (proposal) | none | CAND/c54-release-margins/README.md {U} | +1.3 → +3.8 K with PS122WF680JT4E, ERJ-PA3F4991V, 16SVPK220M | owner | — | 16SVPK220M: 0 at JLC/LCSC; 55-week factory lead [VEN] |
| PWR-44 | J1 mains-terminal temperature | Both | OPEN | none | PS/OPEN-ITEMS.md:30 {T} (104.6 °C, +0.4 K); review packet {U} (103.1 °C, +1.9 K); CAND/c54-j1-thermal/README.md {U} (76.2–98.8 °C with a 14 AWG lead, +6.2 K; proposes an F.Cu strip) | Three estimates disagree [SIM] | bench | — | **Contradiction**; measure with a real cord |
| PWR-45 | Bank self-heating gate (S25) | Prototype | OPEN | [DEC] pre-lot bench gate: ΔT ≤ 20 K × F_T² and T_A + ΔT ≤ 125 °C; S25 runs on the first board before the rest of the lot is powered | PS/OPEN-ITEMS.md:34 (S25) {T}; NAT/PROTOTYPE-LOT.md:117-124 {T} [SIM: C22 at 0.871 / 1.133 of rating at 18.375 A] | — | bench | First board | Timing **contradiction**: DECISIONS.md:3027-3029 makes it a pre-build gate (consigned bank); PROTOTYPE-LOT gate 7 says JLC now buys the bank |
| PWR-46 | PS2 MPM-20-24 ambient | Both | OPEN | none | PS/OPEN-ITEMS.md:28, 36 (S18, S27) {T} [SIM] | 76.0 °C local air, +4.2 K at release; a 78 °C stacked bay fails at any load | owner | — | Firmware measures no air temperature (SNS-41) |

### 1g. Protections

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| PWR-47 | Mains fuse F1 | Both | IN PROGRESS | [DEC] Littelfuse KLDR025.TXP, UL Class CC, 25 A time-delay, 600 Vac / 200 kA, in 2 × 01250003H open clips; no inlet fuse | PS/DECISIONS.md:318-337 {T}; OI/CERTIFIER-PACKET.md A2 #6-7 {M}; NAT/sourcing/inquiries/F1-CERTIFIER.md {M} | Branch breaker plus F1 | external (certifier) | CMP-05 | The clips carry no printed voltage rating and no CSA file. PS/README.md:113,127 still say MDA-25-R (**stale**) |
| PWR-48 | Nameplate 120 V vs 120/127 V | Both | OWNER-ONLY | none: "open (owner)" | PS/DECISIONS.md:236 {T} | Under the nominal-voltage rule this decided the old F1's interrupt basis | owner | — | That entry predates the KLDR change; whether it still binds was not re-derived (gap) |
| PWR-49 | F1 I²t vs the narrowest board copper | Both | OPEN | none | PS/validation-results/02-protection-timing/shoot-through-f1/s53_necks.json {T} [SIM] | Ratio 0.993, a 0.7 % fail (conductor-only 1.021) | Claude+owner | — | Fix is copper width or a lower-I²t fuse |
| PWR-50 | Line current limit (15 A) is firmware-only | Both | OPEN | [DEC] firmware estimate: hold 11.1 A, e_est 10 % provisional. R5 hardware average-current trip (13.88 A) designed but deferred | PS/DECISIONS.md:170-186, 3003-3008 {T} | F1 never opens at 15–25 A | external (certifier) | CMP-13 | May pull in UL 60730-1 Annex H / UL 1998 |
| PWR-51 | Shunt OCP chain | Both | IN PROGRESS | [DEC] R5 1 mΩ Kelvin → TLV3201 → NAND → CA-IS3720HW → BUS_FAULT; band 69.18–114.57 A | PS/DECISIONS.md:2982 {T} [SIM] | Shoot-through cover (no desat, PWR-56) | bench | — | Comparator common-mode term unproven: bench n = 30 TLV3201 from ≥ 3 reels, 25–125 °C (S23, OPEN-ITEMS:32) |
| PWR-52 | Tank CT trip vs firmware cap | Both | OPEN | [DEC] CT band 64.55–76.09 A; firmware cap TANK_PEAK_TRIP_MAX_A 64.5 A (intentionally just below) | FW/components/power/include/tank_freq.h:103-105 {T}; PS/OPEN-ITEMS.md:38 (S29) {T} | Firmware should trip before hardware | Claude+owner | — | Only 0.05 A of separation. Proposed fix (R44/R45 → 11 k, firmware 62.5 A) is in CAND/c54-ct-band {U}, not applied |
| PWR-53 | Bus OVP | Both | IN PROGRESS | [DEC] U7 at 280 V nominal (band top 287.62 V); firmware OV latch at 231 V via AMC1311. Inhibits restart, does not clamp | PS/README.md:115 {T}; PS/OPEN-ITEMS.md:29 (S20) {T} | — | bench | — | AMC1311 input is 2.43 V at 287.62 V, above its 2.0 V full scale but below clip (S22) |
| PWR-54 | DC-link clamp | Both | OPEN | [DEC] D3 + D17 = 2 × Good-Ark 30KPA150CA in series | PS/DECISIONS.md:461 {T} [DS+SIM] | Standoff is 0.9587 of rating at the OVP top; a 384 V plug-in overshoot exceeds VBR min | external+bench | Maker confirmation | PS/DC-LINK-CLAMP.md and PROTOTYPE-POWER-LOOP.md still say MRT130KP295CV and 2.7 µF caps (**stale**) |
| PWR-55 | Inrush | Both | IN PROGRESS (desk pass; bench confirm missing) | [DEC] no NTC or limiter (film bus 18.4 µF) | PS/DECISIONS.md:457-460 {T} [SIM] | Inrush I²t ≤ 1.8 % of F1 | bench (confirm) | — | — |
| PWR-56 | Desaturation detection | Both | DONE (decision) | [DEC] none by design; shoot-through covered by the R5 OCP | PS/DECISIONS.md:2318 {T} | — | — | — | Validation plan 02 (protection timing) shows "static criterion failed" (00-MASTER-PLAN.md:232), but that table is stale (TST-02) |
| PWR-57 | Surge (RV1 TMOV20RP175E) | Both | OPEN | [DS] 175 Vrms, 455 V clamp | PS/DC-LINK-CLAMP.md:41-61 {T}; PS/README.md:120 {T} | Test levels set by the certifier | external | CMP-05 | — |
| PWR-58 | Thermal cut-off (stuck-on backstop) | Both | OPEN (HIGH) | [ASM] TCO loop on J3 opens PS2 and removes gate drive (not the power path); rating and mounting provisional | PS/OPEN-ITEMS.md:26 (S15) {T}; CAND/c53-stuck-on/README.md {T}; R43/BOM.csv:59-60 {U\*} (Microtemp G4A "rating to select") | The only firmware-independent stuck-on cut (UL 858 25.3.1) | owner+external | CMP-12 | Inlet relay DNP, not built |
| PWR-59 | BIAS_GOOD heartbeat to the controller | Both | IN PROGRESS | [DEC] items 71/79: BIAS_GOOD = bias_ok AND PERMIT on J4.1 | PS/DECISIONS.md:2677, 3049-3051 {T} | Lets the controller detect a dead bias supply | bench | Controller (CTL-17) | Never on hardware |
| PWR-60 | FMEA coverage | Production | OPEN | none | PS/OPEN-ITEMS.md:67 (B13) {T} | U5 (REF25) open was undetected; watchdog built at s48; monitor front-end field coverage 0 % | Claude | — | FMEA update open |

### 1h. Gate drive, sense, capacitors

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| PWR-61 | Gate drivers | Both | IN PROGRESS | [DEC] U1/U2 Infineon 2EDR8259XXUMA1: reinforced, VIORM 1767 Vpk, UL 1577 E311313 [DS] | PS/DECISIONS.md:1038-1063 {T} | — | bench | — | DIS-to-output delay not in the datasheet (CTL-26). PS/README.md:9 says UCC21550 (**stale**) |
| PWR-62 | Dead time R9/R17 49.9 kΩ 0.1 % | Both | IN PROGRESS | [DEC] 2026-10-03 change from 39 kΩ | PS/DECISIONS.md:27, 1046 {T} | Turned-off FET gate exceeded the 1.9 V screen at 39 kΩ [SIM] | bench | First switching | Estimates differ: 396.6–488.0 ns (the 2026-10-03 entry) and 408–569 ns (DECISIONS:1046). Measure at bring-up |
| PWR-63 | Switching robustness (F6 grid, S4/S14) | Both | IN PROGRESS | [DEC] item 77: closed on the s51 matrices | PS/DECISIONS.md:3031-3040 {T}; PS/OPEN-ITEMS.md:40 (S14) {T} [SIM] | 640/640 pass; worst VDS 435.7 V. Max-Qrr S4 dv/dt 67.43–68.16 V/ns = 0.96–0.97 of the 70 V/ns diode rating (over the 56 V/ns 80 % screen) | bench | D-8 double-pulse | Body-diode recovery has never been measured |
| PWR-64 | High-side bias | Both | OPEN | [DEC] RECOM R24C2T25/R-R (5 kVAC reinforced) + U26 TPS7A4700 | PS/OPEN-ITEMS.md:30 (S21) {T} | U26 TJ is +4.1–4.4 K at release; no BOM fix, needs layout | owner | — | — |
| PWR-65 | Shunt R5 rating basis | Both | OWNER-ONLY | none | PS/owner-outbox/2026-10-12.md §1 {T} (Bourns inquiry drafted, not sent) | 5 W derated 70 → 170 °C; the reference point is unconfirmed; element 130.1 °C (ratio 0.765) [DS+SIM] | owner (send) | — | — |
| PWR-66 | DC bus capacitors C5/C6 | Production | OPEN | [DEC] TDK B32676G1905K000, 2 × 9 µF 750 VDC | PS/DECISIONS.md:457 {T}; PS/OPEN-ITEMS.md:44 (S8) {T} | At 28 A, rated ripple only with cap ambient ≤ 80 °C; 28 % of HF ripple power lies above TDK's 95 kHz chart edge | bench | — | — |
| PWR-67 | Resonant bank (prototype) | Prototype | IN PROGRESS (≤ 24 A desk pass; S25 bench gate missing) | [DEC] item 74: 5 × TDK B32643H8104J000 (0.5 µF, 2000 V); an H board is never commissioned above 24 A | PS/DECISIONS.md:2876 {T}; NAT/PROTOTYPE-LOT.md:117-124 {T} [DS+SIM] | Vendor-curve ratio 0.844 at 24 A | — | — | PS/README.md:124 (0.54 µF) and PROTOTYPE-POWER-LOOP.md:39-44 (CDE 942C) are **stale** |

### 1i. Insulation, EMI, touch current, aux load

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| PWR-68 | HOT ↔ SELV/PE creepage floor 8.0 mm | Both | IN PROGRESS | [DEC] D5: PD3, IIIa, reinforced | PS/D5-BASIS.md {T}; NAT/review-packet-s53/README.md §4 #4, #13 {U} [CAD gate] | Audit 8.047 / 8.507 mm | external | CMP-14 | Barrier packages are exactly 8 mm (2EDR8259X, CA-IS3720HW, VOL628A): zero margin |
| PWR-69 | RES_A inner-layer clearance | Both | OPEN | [DEC] "same-layer = solid insulation" (closest 8.328 mm) | NAT/fab/FAB-NOTE.md (mains tier) {T}; OI/CERTIFIER-PACKET.md A3 #10 {M} | 297 V rms at 28 A; outer layers ≥ 12.6 mm | external | CMP-05 | Needs certifier acceptance |
| PWR-70 | Coil studs J2/J5 and their lugs | Both | IN PROGRESS | [DEC] owner 2026-10-08 (review M6): J2/J5 stay at 15.0 mm centres. Insulated M4 ring terminals required (bare ring ≤ 10 mm, ring-to-ring ≥ 5.0 mm at any rotation); candidate TE 2-34853-1 (105 °C vinyl) | PS/DECISIONS.md:242-250 {T}; PS/ASSEMBLY.md:39-46 {T} | Functional insulation, ≤ 362 V rms at 28 A with a pan [SIM] | owner | COIL-22/23 | **Conflicts with the coil study** (non-insulated lugs; 105 °C is under the 130 °C winding limit). Reverses to a board-wide re-layout if the lab uses crest RMS |
| PWR-71 | EMI filter on the board | Both | IN PROGRESS | [DEC] C1/C2 KEMET R463N410050N1K (X2), L1, C3/C4 Murata DE1E3RA222MJ4BH01F (Y1 2.2 nF), RV1, plus an off-board D-22 inlet module | PS/native-21/frozen/default.csv {T} | — | — | PWR-72 | — |
| PWR-72 | Conducted EMI margin with the prototype L1 | Prototype | BLOCKED | none | NAT/PROTOTYPE-LOT.md (EMI; gate 5) {T}; PS/OPEN-ITEMS.md:57 (B15) {T}; CAND/c23-supply-topology/MODULE-REQUEST.md {T} [SIM] | With L1 2203: 12.37 / 8.19 dB. With 2243: 6.03 / 1.57 dB, INCONCLUSIVE, unless the inlet module gives ≥ 100 µH DM per line (then 11.14 / 6.95 dB) | owner | Inlet-module part; the request is unanswered | Order gate 5 needs the module or a written EMI deviation |
| PWR-73 | X2 capacitor C2 ripple | Both | OPEN | none | PS/native-21/verification/datasheet-ledger/README.md {M} [DS+SIM] | 1.15 A line-cycle RMS at release; passes only while C2 ≤ 86.4 °C; fails at 28 A | bench | — | — |
| PWR-74 | Touch current | Both | IN PROGRESS | [DEC] budget 0.25 mA (50 % of 0.5 mA) | PS/OPEN-ITEMS.md:41 (S1) {T}; PS/validation-results/07-conducted-emi/leakage/result.json {T}; CAND/c54-touch-current/README.md {U} [SIM from datasheet-maximum leakage] | 0.2412 mA design: **8.8 µA margin**. Estimated lab reading 0.306 mA against 0.5 mA | bench/external | CMP-10 | Depends on the IEC-only MPM supplies being accepted |
| PWR-75 | Aux-load allowance | Both | IN PROGRESS | [DEC] B11: cut from 1.35 / 1.93 / 2.57 A | PS/OPEN-ITEMS.md:64 (B11) {T}; PSI/output/temper-aux-load-r1/README.md, BENCH-RMS.md {T} | Real increment 0.10–0.33 A typical [SIM+DS]; PROVISIONAL until BENCH-RMS | bench | — | Figures differ: 0.31 / 0.60 / 0.887 A (OPEN-ITEMS:64) vs 0.31 / 0.65 / 0.887 A (FW/README.md:78-86). **Verify** |

### 1j. Bring-up, review, documents

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| PWR-76 | Bring-up procedure | Prototype | OPEN (prepared, not run) | [PLAN] SELV only → mains on PS2 with BR1 out and the bus from an isolated DC supply (CT/OCP/OVP calibration, first switching, ZVS) → owner fits BR1 → variac + dim bulb → heating. First-power ceiling 17.5 A; IR stop 100 °C (provisional) | NAT/BRING-UP.md {T}; FW/components/power/COMMISSIONING.md {T} | Staged energisation | bench | Boards, controller, coil, bench sink | — |
| PWR-77 | Bench DC landing point | Prototype | OPEN | none | PS/ASSEMBLY.md:66 {T} (BR1.1/BR1.4); CAND/bench-sink-r1/README.md Q9 {T} (C6.1/C6.3); NAT/BRING-UP.md {T} ("B19 leads") | Must be one answer before first power | Claude | — | **Contradiction** (3 versions) |
| PWR-78 | Bench equipment (order gate 10) | Prototype | OWNER-ONLY | none | NAT/PROTOTYPE-LOT.md:161 {T} | — | owner | — | No LISN or spectrum analyser is on the list (TST-13) |
| PWR-79 | Power order gates | Prototype | BLOCKED | [PLAN] gates 3 (laminate), 4 (Global Sourcing, consigned FETs, pre-orders), 4a (preheater), 5 (inlet module or EMI deviation), 6 (31 CPL rows), 7 (bank re-read), 10 (equipment), 11 (owner spend approval) | NAT/PROTOTYPE-LOT.md:133-163 {T} | — | owner | PWR-06, PWR-72, PWR-13 | Gate 8 (J13 merge) text says "not done on any controller branch", but DECISIONS 79 says it landed (**contradiction**, CTL-30) |
| PWR-80 | Independent design review | Both | DONE (desk) | [DEC] item 79 | NAT/INDEPENDENT-REVIEW-2026-10-18.md {T}; PS/DECISIONS.md:3052 {T} | No BLOCKER on PERMIT, gate drive or barrier; 2 MAJOR and 4 MINOR handled | — | — | AI review, not a licensed reviewer |
| PWR-81 | External PCB-designer review packet | Both | OWNER-ONLY | none | NAT/review-packet-s53/README.md {U} | A human professional review before production | owner | — | Untracked; c54 lanes were still running when it was written |
| PWR-82 | Place the JLC PCBA order (10–20 boards) | Prototype | OWNER-ONLY (prepared, not ordered) | [DEC] owner 2026-10-16: lot of 10–20 | NAT/PROTOTYPE-LOT.md:1, 13-24 {T}; OI/order/ORDER-PACKAGE.md {T} | — | owner | PWR-79 | — |
| PWR-83 | Stale power-stage README and side docs | Both | OPEN | — | PS/README.md:3, 9, 80-135 {T}; PS/FAULT-INTERFACE.md:3; PS/DC-LINK-CLAMP.md; PS/PROTOTYPE-POWER-LOOP.md; PS/ASSEMBLY.md:12-28, 81-83 | They describe UCC21550, ISO7710, PS1, MDA-25-R, CT 1:100, 39 kΩ, 0.54 µF, 240 × 160 mm and THR 74650074 | Claude | — | An auditor or vendor reading the README gets the wrong board |

## 2. Controller board (C49, branch controller-j13-merge)

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| CTL-01 | Which controller to order | Prototype | DONE | [DEC] C50: the first order is C49 (J13 merge), not C48 | CJ/DECISIONS.md:720-725 {CJ} | Firmware matches C49 only (FW/README.md:166-170) | — | — | — |
| CTL-02 | Board spec | Prototype | DONE | [DEC] 206 × 76 mm, 4 layers, JLC04161H-7628, 1.6 mm, 1 oz outer / 0.5 oz inner, HASL lead-free, tented vias, no impedance control | CJ/ORDER.md:48-63 {CJ}; CJ/fab/fab-notes.md:5-7 {CJ} | — | — | — | — |
| CTL-03 | Routing robustness | Prototype | IN PROGRESS (risk accepted) | [DEC] one clean run (DRC 0 errors, 0 unconnected, parity 0) | CJ/DECISIONS.md:726 {CJ}; CJ/evidence/convergence-c49.json {CJ} [SIM router] | The 3-run convergence closes on 1 of 3 runs (runs 2 and 3 each left one net open) | — | — | The board of record is fine; the router is fragile for re-spins |
| CTL-04 | Design verification | Prototype | DONE (desk) | [CODE] verify_controller: 248 checks, 0 failed; stranded-via gate (check 14) | CJ/evidence/verify.json {CJ}; CJ/DECISIONS.md:717 {CJ} | — | — | — | ORDER.md:30 and README.md:65 say 233 checks and 13/13 layout checks (**stale**) |
| CTL-05 | JLC order | Prototype | OWNER-ONLY (prepared, not ordered) | [DEC] ordering is the owner's | CJ/ORDER.md:28 {CJ}; CJ/evidence/fab-loose-ends/cpl-rotation/PREVIEW-2026-10-19.md:3 {CJ} | Draft project "controller-gerbers" holds the uploaded Gerbers, BOM and CPL; not in the cart, not paid | owner | CTL-09, CTL-10, CTL-12 | — |
| CTL-06 | PCBA service level | Prototype | DONE | [DEC] Standard PCBA, not Economic | PREVIEW-2026-10-19.md:5-6 {CJ}; CJ/ORDER.md:5, 63 {CJ} [VEN viewer] | 83 extended part types (Economic allows 80); U4 ESP32-S3 is "Standard only" | — | — | — |
| CTL-07 | Upload integrity | Prototype | DONE | [CODE] sha256 match: BOM 259acf19…, CPL 2327ec70…, zip 53f5addd… | CJ/ORDER.md:24-25, 41-44 {CJ} | — | — | — | BOM 89 lines; CPL 288 placements (279 SMD, 9 THT), all top side |
| CTL-08 | CPL rotation, ICs | Prototype | DONE (vendor viewer) | [DEC] geometry offsets applied (29 rotations); pin 1 confirmed on 16 parts; polarity on C9, D7, D9, U7 | PREVIEW-2026-10-19.md:14-31 {CJ}; CJ/DECISIONS.md:727-728 {CJ} | As first uploaded, U11/U12/U16/Q1 were 180° wrong and U3 90° | — | — | CJ/fab/fab-notes.md:14-15 and LAYOUT.md:255 still say KiCad rotations are used as-is (**stale**) |
| CTL-09 | CPL check of the THT connectors J1, J2, J3, J4, J7 | Prototype | OWNER-ONLY | none | PREVIEW-2026-10-19.md:23-26, 34 {CJ} | Body and keying against the silk; the viewer shows no pin-1 mark | owner (JLC viewer) | — | **Not done.** J4 was not re-checked after the revert (the browser extension disconnected) |
| CTL-10 | CPL check of D1–D6 (ESD5Z3.3, C61148) and C1 | Prototype | OWNER-ONLY | none | PREVIEW-2026-10-19.md:34 {CJ}; CJ/fab/cpl-jlcpcb.csv {CJ} | Argued from D7/C9 [ASM], but D7 is a different LCSC code (C82044), and D1–D6 sit at mixed rotations (D1/D6 270°, D2–D5 90°) | owner (JLC viewer) | — | **Not done** |
| CTL-11 | Order-day checks | Prototype | OWNER-ONLY | [DEC] U4 must appear as an SMT placement; reject any JLC "similar part" substitution (especially R39 and the 0.1 % thin-film parts) | CJ/ORDER.md:116-117 {CJ} | — | owner | — | — |
| CTL-12 | R39 RG2012V-431-W-T1 (430 Ω 0.05 %, the MAX31865 Rref) has no stock | Prototype | BLOCKED | [DEC] C37 rejects the degraded RT0805BRD07430RL (0.80 K vs 0.16 K error at 250 °C) | CJ/ORDER.md:22, 77-85 {CJ}; CJ/evidence/order/stock-read-2026-10-18.json {CJ}; CJ/evidence/fab-loose-ends/consignment/consignment-sheet.md:46-49, 86 {CJ} [VEN] | JLC 0 stock; DigiKey only a 3,000-piece reel at $1.23745 (USD 3,712.35), 22-week lead; ten 0.05 % equivalents all 0 | owner | Supply | Pan-RTD accuracy has nil margin without it (SNS-12) |
| CTL-13 | R39 fallback | Prototype | IN PROGRESS | [DEC] JLC places R39 as DNP; an RG2012V is hand-fitted later. The pan-RTD channel is unusable until then | CJ/ORDER.md:85 {CJ} | — | owner | CTL-12 | Hand-fitting an 0805 conflicts with "home bench through-hole only" (SUP-01). ORDER.md:85 says rotation 180 but the CPL has 0 (**contradiction**) |
| CTL-14 | Quantity | Prototype | OWNER-ONLY | [DEC-recommendation] 5 bare PCBs, assemble 3, consign R39 × 5 | CJ/ORDER.md:144-152 {CJ} | — | owner | — | — |
| CTL-15 | Controller cost | Both | IN PROGRESS | none | CJ/ORDER.md:12, 154-163 {CJ}; CJ/DECISIONS.md:724 {CJ} [VEN] | Parts USD 65.35/board; 5 bare PCBs about USD 34.70. Excludes assembly, extended-part fees, VAT 13 % + 2 %, shipping | Claude | — | — |
| CTL-16 | Thin-stock lines | Prototype | OWNER-ONLY | none | stock-read-2026-10-18.json {CJ}; CJ/evidence/fab-loose-ends/consignment/distributor_records.json {CJ} [VEN] | TPS3703A4330DSERQ1 16; AD8436ARQZ 65; RC0603FR-0756K2L 133; 74HC30PW 144; TLV9031 146. TPS3703-Q1 at DigiKey: 0, 26 weeks | owner | — | ORDER.md:91, 93 have older figures (18, 106). Re-read on pay day |
| CTL-17 | BIAS_GOOD input on GPIO35 | Prototype | IN PROGRESS | [DEC] C49: R124 10 k, C97 1 nF C0G, R123 1 M; deliberately no TVS | CJ/DECISIONS.md:710-712 {CJ} [SIM: high level 0.82 × VDD vs VIH 0.75; τ ≈ 190 µs] | — | bench | — | Never on hardware |
| CTL-18 | RAIL_OK_RB moved to TCA9555 P02 | Prototype | DONE (design) | [DEC] C49 | CJ/DECISIONS.md:710 {CJ}; FW/components/hal/include/controller_pins.h:107 {T} | — | — | — | — |
| CTL-19 | J13 rail merge | Prototype | IN PROGRESS | [DEC] logic rail v15_selv fed from V15_BLW through D9 SS14 | CJ/DECISIONS.md:710, 712 {CJ} [SIM] | Worst-corner logic rail ≥ 13.9 V; PS3 total 44.55 W of 65 W | bench | — | D9 has never been on hardware |
| CTL-20 | J4 power-board connector (Molex 43045-1600) and its drawing | Both | OPEN | [DEC] pin map: 1 bias_good … 16 line_zc | CJ/DECISIONS.md:115, 710 {CJ}; CJ/ORDER.md:108 {CJ} ("drawing still unread"); CJ/LAYOUT.md:245-254 {CJ} ("owner supplied 2026-10-12, not committed") | Plug overhang X−52 vs the enclosure's X−50 | owner | — | **Contradiction**. Also ENCLOSURE-HANDOFF.md:27 (pin 1 v15_selv, mating +X) vs LAYOUT.md:227 (mating −X) |
| CTL-21 | Other connectors | Prototype | DONE | [DEC] J13 JST B2P-VH (LCSC C160315); J10 blower B3B-XH (V_BLOWER / GND / FG); J3 RTD B4B-XH (4-wire); J12 rim NTC B3B-XH | CJ/DECISIONS.md:226-232, 254, 371-372, 499, 588 {CJ} | — | — | — | — |
| CTL-22 | Harnesses and programming cable | Prototype | OPEN | none: not on any order list | not found | TC2050-IDC-NL cable; J4 43025-1600 housings + 43030 crimps; J13 VHR-2N / SVH-21T; PS3 | Claude (list) + owner (buy) | — | Without them, bring-up stalls on day 1 |
| CTL-23 | Programming and debug | Prototype | DONE (design) | [DEC] J11 Tag-Connect TC2050-IDC-NL land (no BOM line); USB-Serial-JTAG on GPIO19/20 | CJ/DECISIONS.md:591-594 {CJ}; CJ/ORDER.md:114 {CJ} | — | — | CTL-22 | — |
| CTL-24 | Hardware safety supervisor | Both | IN PROGRESS | [DEC] PERMIT = latch Q AND RUN_EN (GPIO14, 4.7 k pull-down); read-backs through the LVC244; TPS3823 WDI on GPIO18; timeout 0.9–2.5 s | CJ/README.md:85-120 {CJ}; CJ/DECISIONS.md:162-168, 596-606 {CJ} [SIM: 262,144 netlist cases enumerated] | Protective functions are independent of the MCU | bench | — | The watchdog timeout is stated three ways (FW-10) |
| CTL-25 | Runaway comparator bands | Both | IN PROGRESS | [DEC] pan trip 298.8–323.1 °C; rim NTC trip 262.1–288.3 °C (86.6 k fit gated on bench T3) | CJ/DECISIONS.md:548-552, 434 {CJ} [SIM] | Hardware backstop above the firmware's 300 °C | owner (accept band) + bench | SNS-22 | Owner acceptance of the band is open (open item) |
| CTL-26 | Capacitive-mode detector (C39) | Both | OPEN | [DEC] uses the OVP input | CJ/DECISIONS.md:555-585, 459 {CJ} | Needs a 2EDR8259X DIS-to-output delay ≤ 190 ns, which is not in its datasheet | bench | — | Decides whether the detector vetoes the first bad edge |
| CTL-27 | Thermal trip ladder | Both | IN PROGRESS | [DEC] C32: heatsink firmware 95 °C / hardware 101.4 °C (98.3–104.6); coil firmware 165 °C / hardware 175.7 °C | CJ/DECISIONS.md:309-312 {CJ}; FW/config.yaml:274-290 {T} | — | bench | — | — |
| CTL-28 | AD8436 settling | Both | OPEN | [ASM] ≤ 3.4 ms with CAVG 100 nF (linear scaling of a datasheet figure) | CJ/DECISIONS.md:134, 435 {CJ} | — | bench | — | — |
| CTL-29 | PS3 blower supply part | Both | OPEN | [DEC] power stage: MPM-65-15ST | PS/DECISIONS.md:1504 {T}; FW/README.md:79 {T} | MPM was chosen for touch current (PWR-74) | Claude (docs) + owner | — | **Contradiction:** CJ/README.md:135 and R43/BOM.csv:206 still say IRM-60-15ST |
| CTL-30 | Controller source in the integration branch | Both | OPEN | [DEC] item 79: firmware targets controller-j13-merge (59ff40af5) | PS/DECISIONS.md:3049-3054 {T}; PSI/zapote/controller/DECISIONS.md {T} (stale copy, C1–C22, 230 lines) | One source of truth before ordering | owner (merge) | — | NAT/PROTOTYPE-LOT.md:156-158 (gate 8) says "not done on any controller branch" (**contradiction**) |
| CTL-31 | Stale controller README | Both | OPEN | — | CJ/README.md:70, 125, 135, 172, 199 {CJ} | Still lists PS1, J4.1 as a supply, GPIO9 SDA, AD8436BRQZ | Claude | — | — |

## 3. Coil (output/temper-coil-r1; all {T} on PSI unless noted)

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| COIL-01 | Coil state | Both | IN PROGRESS | none | COIL/README.md:3 | "Modelled only. No coil has been wound or measured" | owner+bench | Litz, ferrite | — |
| COIL-02 | Winding of record R1 | Prototype | IN PROGRESS | [DEC] D2: 14.47 inner + 6.46 outer = 20.93 turns, ~81 µH free air; wind with one spare outer turn, tune into 76–86 µH, never below 5.46 outer turns | COIL/README.md:19-47, 170-179; BUILD-AND-MEASURE.md:5-13 | Passes spec row 3 on cast iron (46.1 vs 41.5 µH) where 70 µH fails (39.7); over the ceiling at 60 kHz in 1 run vs 14 for 70 µH [SIM] | bench | COIL-09, COIL-12 | Reverses if the ceiling rises to ≥ 24 A |
| COIL-03 | Model basis | Both | IN PROGRESS | [DEC] D1: trust the 3D discrete-bar solve, carry it with the 2D model, calibrate on the bench | COIL/README.md:56-70, 166-168; COIL/model/fem3d/results/*.json (commits 36048995c, 1bbc45d5f) | 2D overstates free-air L by 11 % (bar smearing); the factors transfer within 0.4 % [SIM]; solver validated against the filament sum and Dodd–Deeds | bench | M2 | Reverses if the wound L differs by > 5 %. Field files were deleted; re-runs need the remote box |
| COIL-04 | Coil R against spec rows 4–5 | Prototype | IN PROGRESS | none | COIL/README.md:21-28 [SIM] | R_dc 83.2 mΩ vs ≤ 100; R_ac 86.6 vs ≤ 193 mΩ at 25 °C (design Litz). Stock RMC Litz models ~90 mΩ R_dc | bench | M3, M5 | — |
| COIL-05 | Pan µ (loaded L/R) | Both | OPEN | [ASM] µ 50–500 by pan class | COIL/README.md:79-91, 269 | Moves loaded L by ±30 % and R by ±40 % | bench | M4 | The biggest unknown in the coil-to-power-stage match |
| COIL-06 | Resonant bank unchanged for the coil | Prototype | IN PROGRESS (desk pass; bench missing) | [DEC] D3: keep 0.5 µF (5 × B32643H8104J000) | COIL/README.md:181-186 [SIM] | f_res 27–41 kHz keeps 35–60 kHz with f/f_res ≥ 1.21; V_C ≤ 143 V rms / 311 V pk at 17.5 A | bench | — | — |
| COIL-07 | Litz for the first coils | Prototype | OWNER-ONLY | [DEC] D4: stock solderable Litz. Recommended RM Cybernetics 12 A, 1000 × 0.05 mm, OD 2.55; alternative Elecify 1050/44; Elecify 200/38 rejected (fails row 4) | COIL/README.md:188-191; COIL/ORDER-LIST.md:11-17 | Grade-200 enamel will not solder-strip at home; the custom wire is ~6 weeks and £1000 MOQ (earlier read) | owner (ask RMC for price and stock) | — | RMC datasheet (web read 2026-10-19, per ORDER-LIST:17): **class 155** [DS]; stock **unconfirmed**. Elecify class and OD unstated |
| COIL-08 | Winding temperature limit for stock Litz | Prototype | DONE (decision) | [DEC] D4 / §5: winding ≤ 130 °C; stop at 130 °C on any thermocouple | COIL/README.md:191; BUILD-AND-MEASURE.md:140 | Class 155 with 25 K margin | bench (enforce) | — | The lumped model puts the winding at 113–131 °C in a 230 °C-glass fry hold (HOT-LIMITS:7) [SIM], so sustained frying may hit the stop |
| COIL-09 | Qualification Litz (spec rows 8/11, class 200) | Production | OPEN | [DEC] D4: 270 × 0.10 mm, type 2, class-200 enamel, Nomex or PTFE serve | COIL/ORDER-LIST.md:15; SPEC rows 8, 11 | Spec requires class ≥ 200 | owner | RFQ (RMC / New England Wire / Elektrisola) | 4–8 weeks *est.*; no RFQ sent |
| COIL-10 | Stock Litz as a documented deviation | Prototype | DONE | [DEC] S4 | COIL/README.md:265 | Spec rows 8 and 11 | — | — | — |
| COIL-11 | Ferrite bars for the prototype | Prototype | OWNER-ONLY | [DEC] D9: R43's ten 90 × 15 × 5 PC95 bars are adequate at the shipping ceiling | COIL/README.md:137-151, 216-217; COIL/ORDER-LIST.md:19-28 | 0.46 Bs at 17.5 A crest, no pan [SIM] | owner | — | Option A (eBay 135111122358) is **unverified** (listing returned 403). Backup: TDK PC95SP100X100X5 plates cut into strips (Mouser stock is a snapshot, not a live read). M1 checks every bar |
| COIL-12 | Ferrite vs peak current (spec row 7) | Production | OPEN | [DEC] prototype deviation recorded in the spec | SPEC row 7 (line 43); COIL/README.md:143-147, 257-261 | Ten 15 mm bars reach 0.93 Bs at 76 A with no pan (over the 0.75 rule) [SIM] | owner | — | Production closes it with ≥ 20 mm bars (row 12) |
| COIL-13 | Production ferrite | Production | OPEN | [ASM] 85–90 × 20 × 5 PC95 custom (Feiteng / ChaoNeng) | COIL/ORDER-LIST.md:26 | — | owner+external | — | No public price, no RFQ |
| COIL-14 | Former route | Both | IN PROGRESS | [DEC] D6: coil 1 on a printed former (route B: PC, PA-CF or ASA) or the FR4 sheet (route C); G11 CNC (route A) in parallel for sustained heating | COIL/README.md:197-206; COIL/ORDER-LIST.md §3 | All routes within 1.2 % L [SIM fidelity.py] | owner | — | — |
| COIL-15 | Printed formers fail at 130–150 °C | Prototype | DONE (finding) | [DEC] printed formers for bench L work and low power only; sustained heating uses route A | COIL/HOT-LIMITS.md:15-17, 41-44 | PC HDT 117–141 °C; ASA ~100 °C; PA12-CF sources conflict [DS, web reads by the study] | — | — | — |
| COIL-16 | G11 CNC former | Both | OWNER-ONLY | [DEC] route A from cad/out/former_R1_cnc.step, regenerated with `--bundle <measured OD>` | COIL/ORDER-LIST.md:34; COIL/HOT-LIMITS.md:13 | G-11 155 °C continuous (Gund TDS); ≥ 50 % flexural strength retained at 150 °C (Piedmont) [DS] | owner | Litz OD | Not quoted (1–3 weeks *est.*) |
| COIL-17 | Former CAD fidelity | Prototype | DONE | [CAD] former.py rebuilds R43's former exactly (0 mm³ difference) | COIL/cad/out/checks.json (R43_reconstruction) | — | — | — | — |
| COIL-18 | Comb-tooth thickness with OD 2.55 Litz | Prototype | OPEN | [DEC] print with a 0.25 mm nozzle, or skip the outer teeth and use spacer cord | COIL/cad/out/checks.json (teeth_mm: print 0.461, CNC 0.561 mm); BUILD-AND-MEASURE.md:27 | — | bench | — | Comb-tooth creep is unmodelled (HOT-LIMITS:45) |
| COIL-19 | Winding envelope vs spec row 16 | Both | OPEN | none | BUILD-AND-MEASURE.md:59-60 (R1 end r114.8; spare end r118.1); checks.json (spare notch edge 119.322, rim 120.0); SPEC row 16 (winding r 26–114) | The outer end sits 0.8 mm past the spec envelope (4.1 mm with the spare turn) | Claude (check) | — | Possibly an end-of-winding convention; **not reconciled in the repo** |
| COIL-20 | Winding jig | Prototype | IN PROGRESS (designed, not built) | [DEC] D7: wooden turntable, no metal above the top plate (149 mm below the winding), coil ~420 mm above the bench | COIL/cad/jig.py:1-30; cad/out/jig_assembly.step, jig_dxf/*.dxf, jig_cutlist.csv; renders/jig_assembly.png | L can be measured on the jig | owner (build, one weekend) | — | Reverses if L on and off the jig differs by > 0.5 % |
| COIL-21 | Build procedure and traveller | Prototype | DONE (plan) | [PLAN] W1–W10 and traveller sheet; supersedes R43's COIL-PROTOTYPE-BUILD.md where listed | COIL/BUILD-AND-MEASURE.md §1, §4 | — | bench | — | R43 guide itself is {U\*} |
| COIL-22 | Lead termination method | Prototype | OPEN | [PLAN] solder-pot strip 15 mm, then crimp a **non-insulated** tinned M4 ring for 1.5–2.5 mm²; qualify on scrap (1 m sample within +5 % of n·π·d²/4 at datasheet Ω/km) | COIL/BUILD-AND-MEASURE.md:67-71; COIL/ORDER-LIST.md:60 | Copper area 1.96 mm² (1000 × 0.05) | owner+bench | PWR-70 | **Contradicts PS/DECISIONS.md:245** (insulated M4 ring terminals required on J2/J5) |
| COIL-23 | Ring-lug part for 130–150 °C | Both | BLOCKED | none: "not a settled choice" | COIL/HOT-LIMITS.md:20-39 | Nylon PIDG is rated 105 °C. TE 50840: PTFE, 288 °C, 14 AWG, #8 stud; **obsolete at Digi-Key**; RS UK showed 22 pcs; ring ID 4.0 mm is tight for M4. Substitute 1577639-1: PEEK, **24-week lead, rating unverified** | owner | Supply | The PS decision's candidate TE 2-34853-1 is 105 °C vinyl (PS/DECISIONS.md:249), also below the 130 °C limit |
| COIL-24 | Coil stud size (M4 vs "M6") | Both | DONE (by evidence); doc fix OPEN | [DEC] studs are M4: Würth 7466004R "M4 internal through-hole thread" (item 44) | PS/DECISIONS.md:1365 {T}; PS/DECISIONS.md:242 ("coil-stud spacing (review M6)") {T}; PS/ASSEMBLY.md:39 {T} | "M6" in R43's BOM ("power-stage M6 as amended") is **review item M6**, not a thread size | Claude (fix HOT-LIMITS:39) | — | COIL/HOT-LIMITS.md:39 says "unresolved". ASSEMBLY.md:12-13 still names THR 74650074 (also M4) |
| COIL-25 | J2 lead dress | Both | DONE (rule) | [DEC] upturned lug; J2 barrel axis ≤ 8 mm from the stud, or barrel + insulation OD ≤ ~7 mm for the first ~12 mm | PS/ASSEMBLY.md:45 {T} | A horizontal barrel collides with C21/C22, U16/U26, T1 or J7 [CAD R26] | bench | — | — |
| COIL-26 | Measurement plan M1–M7 | Prototype | OPEN (plan ready) | [PLAN] pass levels per spec rows 2–5, 3, 3b | COIL/BUILD-AND-MEASURE.md §2 | Turns modelled numbers into measured ones | bench | Coil, instruments | — |
| COIL-27 | Instruments | Prototype | OWNER-ONLY | [DEC] D8: LCR (TH2830 class, 20–60 kHz) for L; ring-down for R_ac | COIL/ORDER-LIST.md §6; COIL/README.md:214 | At Q ≈ 230 an LCR's R reading carries about ±20 mΩ | owner | — | TH2830 about €899 excl. VAT (the study's earlier read) |
| COIL-28 | Tuning tool | Prototype | DONE (tool) | [CODE] model/tune.py; half turn ≈ 4.3 µH | COIL/BUILD-AND-MEASURE.md §3 | — | — | — | — |
| COIL-29 | Coil NTC | Both | IN PROGRESS | [DEC] controller C32: coil NTC becomes a Semitec 104GT-2-class bead (300 °C); firmware must switch to the 104GT-2 table | COIL/ORDER-LIST.md:62; COIL/BUILD-AND-MEASURE.md:72 (W10); CJ/DECISIONS.md:302-330 {CJ}; PS/DECISIONS.md:498, 620 {T} | Pad at r86.3, 2.0 mm wall | owner+Claude | — | Mount (lug or bonded sleeve) open with the enclosure. Whether FW has the 104GT-2 table: not verified (FW-35) |
| COIL-30 | Coil thermal model | Both | IN PROGRESS | none | COIL/HOT-LIMITS.md:6-8; MAIN/output/coil-review-2026-10-10 {U\*} [SIM, assumed blower curve] | 22 A: 88–100 °C; 28 A: 104–122 °C; 28 A at the 0.23 Ω target: 137–168 °C | bench | — | Hot spots not modelled. **The source folder is untracked** |
| COIL-31 | First-power rules | Prototype | DONE (decision) | [DEC] 17.5 A; winding ≤ 130 °C; no aluminium pan until a pan-detect probe exists | COIL/BUILD-AND-MEASURE.md §5 | Aluminium Ø240 draws 28–36 A rms at 60 kHz [SIM], crossing the CT band | bench | — | FW decided against a pre-start probe on today's hardware (FW-17), so the aluminium ban stays a user rule |
| COIL-32 | Coil insulation test (M7) | Both | OPEN | [PLAN] R43 hipot winding to bars and carrier screws; coil-NTC 3000 V rms 1 min after humidity, PD < 10 pC | COIL/BUILD-AND-MEASURE.md:92 | — | bench | — | Refers to R43's guide {U\*} |
| COIL-33 | **The owner's RCA 12A3 coil** | Prototype | OPEN | none: no decision whether it is used, measured or retired | PS/DECISIONS.md:57 {T} ("RCA 12A3 teardown remain outstanding"); PS/PROTOTYPE-POWER-LOOP.md:80 {T}; R43/design/r12/DECISIONS.md:15-17 {U\*} (donor-chassis Ø200 constraint retired); SR3/box/field_sweep.py:9 {T on PSI} ("the RCA 12A3 coil has not been measured") | Any field or heating claim for it uses assumed radii | owner+bench | — | Coil-r1 does not mention it. Measure L/R/geometry if it will be powered |
| COIL-34 | Recommendations F1–F4 to firmware/power stage | Both | IN PROGRESS | [DEC] F3 settled in FW (no probe); no-pan stop implemented (2.0 s) | COIL/README.md:219-251; FW/build-evidence/f3-pan-probe/README.md:1-12 {T}; FW/config.yaml:438-494 {T} | — | Claude | — | F1 (widen test plants) and F2 (Q-aware lag): not verified in FW |
| COIL-35 | Stale statement in the coil README | Both | OPEN | — | COIL/README.md:253 ("this branch's committed copy is the stale 88 µH version") | The spec is now committed on PSI (dd8e7962d, 93b9ea185) | Claude | — | — |
| COIL-36 | Spec internal contradiction | Both | OPEN | — | SPEC line 59 ("Electrical rows 1–7 are stale … 88 µH") against rows 1 and 7 (updated) | Spec must not go to a supplier while it contradicts itself (line 59 says so) | Claude | — | MAIN's working-tree copy (sha256 637a7603…) also differs from PSI's committed copy (2ec8cc8b…) |
| COIL-37 | Volume winding process / supplier | Production | OPEN | [DEC] spec row 13: moulded carrier (≥ 200 °C class, e.g. PPS-GF or PA46-GF), comb spokes, four lugs at r127 | SPEC row 13; PS/owner-outbox/2026-10-12.md (coil-winder RFQ, not sent) {T} | — | owner+external | — | No winder selected; no process, yield or EOL test for the coil |
| COIL-38 | Not modelled | Both | OPEN | none | COIL/README.md:72-75, 275-280 | Heat-sink spreader bar reaching Z95 under the coil; real lead loops; non-round enclosure parts | Claude (FEM) | — | Could lower L and add loss |
| COIL-39 | Production L target (70 vs 80 µH) | Production | OPEN | [DEC] prototype = alternate B; production "remains a power-stage decision" | SPEC line 239 | — | owner | Bench M4 data | — |
| COIL-40 | Prototype coil budget | Prototype | IN PROGRESS | none | COIL/ORDER-LIST.md:76-78 | $200–500 per coil (2026-10-10 review planning estimate) | — | — | Not a quote |

## 4. Centre temperature sensor cartridge (C1, sensor-r3)

Tracking: SR3 in MAIN is untracked. A newer tracked copy is on `origin/main` (PR #1695, 09a3520ba) and adds leak-barrier/, robustness/ and newer firmware/. The STEP files and box/ exist only locally; box/ is tracked on PSI (792de8805). "{U=OM}" below means untracked locally with an identical copy committed on origin/main.

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| SNS-01 | Preserve the sensor work | Both | OPEN | — | `git status` in MAIN: `?? output/temper-sensor-r3/`; STEPs (cad/*.step, bench/jig-*.step) on no branch | Scratchpads and worktrees get wiped | owner (commit) | — | STEPs {U\*} |
| SNS-02 | Build state | Both | OPEN | none | SR3/cad/QUOTE-LIST.md:5 {U=OM}; SR3/bench/README.md:23-30 {U=OM} | Not built, nothing ordered; supplier classes only, sized for 20 cartridges + 10 % | owner | — | — |
| SNS-03 | Architecture C1 over C0/R16 | Both | DONE (decision) | [DEC] C1 | SR3/DECISIONS.md:70, 104 {U=OM}; SR3/PATENTS.md {OM} | C0/R16 reads close to Breville US11378463B2 claims 1/12 | — | — | R43 still models R16/C0 (SNS-38) |
| SNS-04 | CAD gates | Both | IN PROGRESS | [CAD] 11 PASS, G8 OPEN | SR3/cad/checks.json:2-16 {U=OM}; SR3/cad/DECISIONS.md:82-95 | — | Claude+external | SNS-10 | — |
| SNS-05 | Si3N4 disc | Both | OWNER-ONLY | [DEC] Ø8.0 × 0.32 mm, lapped flat ≤ 1 µm, Ra ≤ 0.1 µm, 0.2 × 45° chamfer | SR3/HANDOFF.md:46; SR3/cad/QUOTE-LIST.md:11 {U=OM} | RFQ must state 0.32 ± 0.015, a ≥ 700 MPa flexural cert, edge chips ≤ 0.05 | owner | — | **No part number**; supplier is a class only (Toshiba Materials / Kyocera / Rogers curamik + lapping shop) |
| SNS-06 | Disc strength (G6) | Both | IN PROGRESS | [SIM Roark] | SR3/cad/DECISIONS.md:25, 89 | 298.7 MPa, SF 2.34 at 20 N with the inner tube (the unbacked span fails at SF 1.8) | bench | — | Durability bench T5 (10,000 slides, ball drop, 200 thermal cycles) not run |
| SNS-07 | Bench kit uses alumina instead of Si3N4 | Prototype | DONE (bench decision) | [DEC] lean kit: 99.6 % alumina 0.254 mm (+20.2 % C_cap, model-corrected) | SR3/bench/DECISIONS.md:176-192 | Cost | — | — | Bench results must be model-corrected back to Si3N4 |
| SNS-08 | Pt100 element | Both | OWNER-ONLY | [DEC] IST P0K1.202 (1.8 × 2.0 × 0.65), 4-wire; quote list names P0K1.202.6W.A.007 | SR3/HANDOFF.md:47; SR3/cad/QUOTE-LIST.md:26 | — | owner | — | **Tolerance class not stated** for the cartridge (only "F0.15" for the bench element, SR3/bench/RIG.md:22) |
| SNS-09 | Hot-zone leads, harness, connector | Both | IN PROGRESS | [DEC] manganin Ø0.08 in a fused-silica 4-bore capillary; M22759/12-26 pigtail; Alpha Wire 55493 harness (UL AWM 20229, 200 °C); Micro-Fit 43020/43025-0600 | SR3/cad/DECISIONS.md:9-12; SR3/pcb/DECISIONS.md:222-249; SR3/pcb/REQUIREMENTS.md:79-82 | — | external | — | Pigtail and harness ODs open |
| SNS-10 | Bond adhesive rating | Both | BLOCKED | none: G8 OPEN | SR3/cad/DECISIONS.md:47-50; SR3/HANDOFF.md:48 | Needs ≥ 260 °C continuous; bond models at 259.9 °C. EPO-TEK 930-4 publishes only "< 325 °C intermittent"; Duralco 128 is 260 °C (zero margin) [DS] | external (Epoxy Technology statement) | Vendor | Single point of failure for accuracy and leakage |
| SNS-11 | Hot-zone insulation ≥ 10 MΩ at 300 °C | Both | BLOCKED | [ASM] the quartz capillary's ~100 MΩ at 350 °C is not credited | leak-barrier/SPEC.md §Construction {OM}; firmware/DECISIONS.md:3177 {OM} | — | external | Supplier confirmation | — |
| SNS-12 | RTD front-end accuracy | Both | IN PROGRESS | [SIM] 0.298 K RSS (nil margin to 0.30); 0.58 K strict linear | SR3/pcb/DECISIONS.md:96-127 | Needs R39 RG2012V-431-W-T1 | owner | CTL-12 | — |
| SNS-13 | RTD self-heating | Both | IN PROGRESS (desk pass; bench missing) | [SIM] bias 3.16–3.92 mA, ≤ 2.19 mW; worst 0.090 K at h_c 888; firmware subtracts 0.061 K | SR3/pcb/DECISIONS.md:205-218 | — | bench (confirm) | — | — |
| SNS-14 | Main spring | Both | OWNER-ONLY | [DEC] A-286, d 0.50, D 8.0, ~6 active coils, P1 1.30 ± 0.08 N at 15.60 mm, P2 1.70 ± 0.08 N at 13.40 mm, ends open | SR3/cad/QUOTE-LIST.md:19; SR3/cad/DECISIONS.md:29, 41 | A closed end turn costs 2.1 W in the eye [SIM] | owner | — | Not ordered |
| SNS-15 | Spring eddy re-screen (G7) | Both | IN PROGRESS (sim PASS) | [SIM analytic loss × FEM field] PASS | SR3/cad/field-screen.json; SR3/cad/checks.json G7; SR3/cad/DECISIONS.md:90 | 2.9 mW / 0.69 K at 8.23 mT, 60 kHz; 11.3 K at the 20 mT / 100 kHz corner; wave spring 0.09 W; 316 stainless rejected (204 °C relaxation) | bench | SNS-22 (T1 field map) | The field itself is unmeasured |
| SNS-16 | Field sweep over coil variants | Both | IN PROGRESS (sim done; field unmeasured) | [SIM] | SR3/box/field_sweep.py:1-10; box/field-sweep.json {T on PSI, 792de8805} | R36 coil: 7.44 mT, ΔT 0.459 K; worst 5.566 K at 13.8 mT on an assumed narrow coil, no ferrite, 100 kHz | — | — | **Non-R36 radii are assumed** (RCA 12A3 unmeasured, COIL-33) |
| SNS-17 | Wave-spring creepage (floating part) | Production | OPEN | [DEC] relies on series creepage | SR3/cad/DECISIONS.md:70 | 7.42 mm direct vs 8.0 mm; 13.37 mm in series | external (safety reviewer) | — | UL 60335-1 acceptance of the floating-part sum is open |
| SNS-18 | Contact conductance h_c | Both | OPEN | [DEC] C1 uses h_nom 1300; floor ≈ 700 (τ63 ≈ 1.35 s). The old "h_c ≳ 2000" applied to the R16 cap and is superseded | SR3/README.md:30, 70-79; SR3/DECISIONS.md:19 | Modelled worst 888 (as-cast iron, Ra 6.0, tilt 2 mrad) gives τ63 1.10 s [SIM]. **Ra and tilt are assumed** | bench | SNS-19 | 0.1 s of margin to the 1.2 s gate; less if C_cap is the effusivity 45.4 |
| SNS-19 | Contact survey (τ63 gate) | Prototype | OPEN | [PLAN/DEC] dry τ63 ≤ 1.2 s on every pan; ≥ 12 pans across 6 classes; STOP above 1.35 s | SR3/DECISIONS.md:122-133; SR3/bench/PROCEDURE.md:89-107 | Decides whether C1 works | bench | SNS-20 | h_c has never been measured |
| SNS-20 | Bench survey kit | Prototype | OWNER-ONLY (prepared, not ordered) | [DEC] lean kit recommended | SR3/bench/bom.json:2; SR3/bench/DECISIONS.md:141-156 | Lean ≈ $313 + $65 optional; reference $1,285 ("ESTIMATED … not quoted") | owner | — | — |
| SNS-21 | Bench logger firmware | Prototype | OPEN | — | SR3/bench/DECISIONS.md:98-113 ("Not compiled or run here") | — | Claude | — | — |
| SNS-22 | Bench T1 / T2 / T3 (R16 plan) | Prototype | OPEN | [PLAN] T1 field map (Z 80/90/100/106; 25/50/100 % power); T2 self-heating; T3 accuracy/response, also the rim-log criterion before fitting CR-5 | R43/design/r16/BENCH-TEST-PLAN.md:23-53 {U\*}; SR3/DECISIONS.md:56-57; R43/design/r43/HANDOFF.md:221 {U\*} | — | bench | Hardware | T2's "PEEK body < 150 °C" cannot apply to C1 (PEEK cup modelled at 200.8 °C, Vespel collar 256–258 °C). **No C1-specific T2 criterion exists** |
| SNS-23 | Sensor PCB acceptance items 1–6 | Prototype | OPEN | [PLAN] pickup ≤ 1 LSB; open-lead ≤ 100 ms; runaway trip 299–322 °C with 0 / 20 Ω added; rim ≤ 252 °C; ESD ±8 / ±15 kV; accuracy on 3 boards | SR3/pcb/CHANGE-REQUEST.md:305-320 | — | bench | Controller built | — |
| SNS-24 | C1 firmware location | Both | OPEN (integration) | [CODE] host-tested and merged on origin/main; the ESP-IDF image links (317 KB) but is "not bench-ready" | firmware/DECISIONS.md:2918, 2955, 3151 {OM} | — | Claude | DOC-02 | **PSI firmware has no C1 code** (FW-06/07) |
| SNS-25 | Closed-loop co-simulation | Both | IN PROGRESS (sim done; no hardware) | [SIM] B1 15/16, B2 16/16, B3 16/16; B5 confirm in 20.7–20.9 s; 0 false latches | firmware/README.md:251-260 {OM} | — | — | — | [DEC] the B5 15 s clause miss is accepted (SR3/DECISIONS.md:111-120) |
| SNS-26 | Leakage hazard (element-parallel leak) | Production | OPEN (HIGH) | [DEC] the 300 °C bar is carried by insulation plus a production test, not by firmware | firmware/DECISIONS.md:3039 {OM}; leak-barrier/SPEC.md {OM} [SIM] | 277 of 624 leak runs hazardous; 4 never latch | owner+external | SNS-11 | Production test is a proposed 192-assembly plan; no lab engaged |
| SNS-27 | Undetectable 1–7 kΩ parallel leakage | Production | OPEN (HIGH) | none | SR3/pcb/REQUIREMENTS.md:43; SR3/pcb/DECISIONS.md:180-183 | 1 kΩ reads 164 °C at a true 250 °C [SIM] | owner | — | Electrically undetectable by design |
| SNS-28 | Stuck post plus pan bow | Production | OPEN | none | robustness/DECISIONS.md:244-296 {OM} [SIM] | Overheats by up to 42.58 K (8 of 15 cases over SP + 15 K); unobservable | owner | — | Crud-friction margin (6.5×) unmeasured |
| SNS-29 | Glass-crack and disc-crack failure modes | Production | OPEN | none: **not found** | only "the bore edge [is] brittle" in SR3/bench/PROCEDURE.md:121-122 | — | Claude | — | No FMEA row for a cracked glass at the sensor bore |
| SNS-30 | Vespel SP-1 rating | Production | OPEN | [DS] 288 °C continuous (distributor figure) | SR3/cad/DECISIONS.md:52 | UL RTI (file E530329) not read | owner (UL iQ) | — | — |
| SNS-31 | Seal and wiper temperatures | Production | IN PROGRESS | [SIM G8 2-D axisymmetric] | SR3/cad/thermal-axisym.json; SR3/cad/DECISIONS.md:91 | Gasket 251.1 vs 260 °C; wiper 243.5 vs 260 °C | bench | — | FFKM conductivity assumed |
| SNS-32 | Connector air temperature | Both | OPEN | [ASM] ≤ 50 °C carried from R43, not computed | SR3/cad/DECISIONS.md:13; SR3/pcb/DECISIONS.md:311-314 | — | bench (EM2 thermocouple) | — | ≥ 150 °C connector fallback open |
| SNS-33 | Glass thickness tolerance near the bore | Both | OWNER-ONLY | [DEC] put 4.00 ± 0.03 within Ø40 of the bore on the glass RFQ | SR3/cad/DECISIONS.md:18 | Closes the G2 tolerance chain | owner | ENC-06 | CERAN tolerance is unpublished |
| SNS-34 | Rim NTC | Both | IN PROGRESS | [DEC] Semitec 104GT-2 in the body-rib pocket at r14.5, bearing on the glass outside the cap; GPIO9 / ADC1_CH8, 1.00 k pull-up; ADS1115 rejected | SR3/HANDOFF.md:55; SR3/pcb/DECISIONS.md:150-176; CJ C31 {CJ} | Accuracy 10.2 K at 250 °C (7.5 K of it is B tolerance) [SIM] | bench | — | SR3/HANDOFF.md:230-232 still says ADS1115 (**contradiction**) |
| SNS-35 | Pt100-vs-rim cross-check threshold | Both | OPEN (doc) | [DEC] 25 K | SR3/pcb/REQUIREMENTS.md:57; firmware/DECISIONS.md:136 {OM} | — | Claude | — | SR3/HANDOFF.md:339-340 says 15 K (**contradiction**) |
| SNS-36 | CR-5 rim hardware trip resistor | Both | OPEN | [DEC] TLV3201, 262.3–288.1 °C, ORed into RUNAWAY; the 86.6 k may stay unfitted until bench T3 | CJ/DECISIONS.md:548 {CJ}; SR3/pcb/DECISIONS.md:178-203 | — | owner+bench | SNS-22 | **Contradiction:** firmware/DECISIONS.md:1270-1276 says lower it to 76.8 k (≤ 244.5 °C); D-BARRIER (L2361) says unchanged at 86.6 k (≤ 252 °C) |
| SNS-37 | Rim NTC self-heating and glass lag | Both | OPEN | [ASM] τ_g 60 s | firmware/DECISIONS.md:1361-1377, 2969 {OM} | 2.6 K (PS/DECISIONS.md:620), 2.3 K (CJ C31), ≤ 4.53 K uncorrected (FW README:319) | bench | — | Three values |
| SNS-38 | Enclosure still carries the R16/C0 cartridge | Production | OPEN | none | R43/BOM.csv:130 {U\*}; R43/design/r43/HANDOFF.md:180, 221 {U\*} | C1 has a different envelope, and C0 has the patent issue | owner | ENC-03 | Needs an enclosure round (R44/R45) |
| SNS-39 | Patent freedom to operate before tooling | Production | OWNER-ONLY | [DEC] a US FTO opinion is needed before tooling | SR3/DECISIONS.md:8-10, 80-85; SR3/cad/DECISIONS.md:64; SR3/PATENTS.md {OM} | Impulse allowed claims unread; wiper-as-"flexible diaphragm" question for counsel | external (counsel) | — | **Not legal advice** |
| SNS-40 | Spill sump | Both | DONE (CAD) | [CAD] 2047 mm³ vs ≥ 2000 | SR3/cad/DECISIONS.md:92 | — | — | — | 2 % margin |
| SNS-41 | Other NTCs | Both | IN PROGRESS | [DEC] heatsink NTC Vishay NTCALUG01A104GA on GPIO6 via the CR-8 divider (gain 0.855072); no ambient/bay sensor fitted (optional relay only) | FW/README.md:72 {T}; PS/OPEN-ITEMS.md:~113 {T}; PSI/zapote/controller/DECISIONS.md:92-97 (M12 probe assumed NTC) {T} | — | owner | — | No bay-air sensor even though PS2 fails in a 78 °C bay (PWR-46) |

## 5. User-interface hardware

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| UI-01 | Display part | Both | IN PROGRESS | [DEC] Newhaven NHD-3.12-25664UCW2 OLED, 256 × 64, SSD1322, 4-wire SPI | UIB/README.md:4 {CJ}; CJ/DECISIONS.md:22-24 (C3) {CJ}; R43/BOM.csv:109 {U\*} | **Selection rationale is thin:** "Retain … for the display mockup" (PSI/docs/research/mit-product-design/readiness/manufacturing/material-selection.md:26 {T}); C3 explains only the SPI choice. **No comparison on lifetime/burn-in, readability, temperature, cost or second source was found** | owner (Claude can write the trade study) | — | Single-source module |
| UI-02 | OLED temperature | Both | OPEN | none | FF4 = PSI/output/temper-flush-front-r4/front-panel-engineering-plan.md:57-59 {T}; OC/SPEC.md:58 {U\*}; OC/DELEGATION.md:89 {U\*} [DS+SIM] | Rated −40…85 °C; module target 65 °C "proposed, not achieved"; fascia OLED zone 44–69 °C expected, **116–176 °C with a pan pushed to the front edge** | bench | — | A pan at the front edge can overheat the display |
| UI-03 | OLED lifetime / burn-in | Production | OPEN | none: **not found** | — | Static UI on an OLED | Claude | — | Gap |
| UI-04 | OLED socket height | Prototype | OPEN | none | OC/DELEGATION.md:73 {U\*}; UIB/bom/ui-parts.csv (J3 PM254V-11-20-H85, C46595982) {CJ}; UIB/DECISIONS.md U30 (E2) {CJ} | The only LCSC 1 × 20 socket is 8.5 mm tall against a modelled 3.0 mm gap | owner | ENC-03 | "The main open mechanical item" |
| UI-05 | OLED supply and 3V3 budget | Both | IN PROGRESS (desk pass; bench missing) | [DEC] U3/U29: the module makes its own 12 V from 3V3 | UIB/DECISIONS.md U3, U29 {CJ} [SIM] | 385.3 mA total at maxima; 74.7 mA of headroom on the non-OLED allocation | bench | — | OLED margins 0.40 V low / 0.13 V high |
| UI-06 | SSD1322 init sequence | Prototype | OPEN | — | FW/build-evidence/esp-idf/PLATFORM.md:215-217 {T} | Needs a bench check | bench | — | — |
| UI-07 | Control concept | Both | DONE (decision) | [DEC] owner 2026-10-12 (U19): three PCB tact switches under owned metal caps, plus a removable magnetic knob read through the 3 mm 5052 fascia by a TMAG5170; Grayhill encoder and APEM buttons removed | UIB/DECISIONS.md:3, U19 {CJ}; UIB/README.md:3-7 {CJ}; R43/design/r43/DECISIONS.md:98 {U\*} | Sealed fascia; the owner's design | — | — | R43/BOM.csv:114-117 still lists APEM and Grayhill (**superseded**). CJ/DECISIONS.md:433 open item 3 ("not chosen") and FW ui_board_map.h:5 ("UI board NOT designed yet") are **stale** |
| UI-08 | Tact switches | Both | OPEN | [DEC] U27: C&K KSC223G LFG (Y31B13136FPLFG), gold, gullwing, 2.25 ± 0.55 N | UIB/DECISIONS.md U27 {CJ} | — | owner | Stock | JLC 0 stock → consign or hand-fit (an **SMD** part on a through-hole-only home bench). The KSC2 drawing was not obtained; footprint pad pairing open |
| UI-09 | Button cap stack | Production | OPEN | [ASM] black-anodized 6061 caps with a captured rolling FKM diaphragm: "a prototype candidate, not a validated actuator stack" | OC/DECISIONS.md:10 {U\*}; OC/SPEC.md {U\*} | Targets: 2–5 N, 0.35–0.65 mm, ≥ 100,000 cycles | bench | — | — |
| UI-10 | Magnetic knob | Both | OPEN | [DEC] TMAG5170A1QDGKR (±100 mT); stage-one magnet Ø10 × 5 Sm2Co17 (RECOMA 35E) | OC/DECISIONS.md:14-15 {U\*}; OC/STATUS.md:6 {U\*}; UIB/README.md:21-30 {CJ} | Targets: 24 detents, 18–30 mN·m, angle ≤ 1° [ASM]; "No ring-error, torque, pull-force or new-cost result yet" | owner+bench | — | Stray-field jitter 0.69° in the bare no-pan transient, over the 0.5° target [SIM] |
| UI-11 | Knob sensor-tab temperature | Both | IN PROGRESS | [SIM] | UIB/DECISIONS.md U29 {CJ} | Die at 120 °C against the 150 °C rating and the 125 °C design target (5 K) | bench | — | — |
| UI-12 | Knob stage-one spend | Prototype | OWNER-ONLY | [DEC] stage one approved ($123.69–214.69 [VEN est.]) | OC/STATUS.md:7 {U\*} | — | owner | ENC-03 | "No orders or vendor contact" |
| UI-13 | Buzzer | Both | IN PROGRESS | [DEC] U28: GSD9605YB-5V2800 (LCSC C530415), self-oscillating, on expander GP6 | UIB/DECISIONS.md U28 {CJ}; OC/DELEGATION.md:74 {U\*} | Body 69.9–83.9 °C [SIM] against an 85 °C rating taken from the LCSC listing [ASM, UNVERIFIED]: 1.1 K margin at the 80 °C board limit | bench | — | SPL at 3.3 V unknown; no fascia opening → needs a membrane or labyrinth |
| UI-14 | STOP: software or hardware | Both | OPEN | [DEC-recommendation] U15: software STOP plus "UI lost > 100 ms = stop" | UIB/DECISIONS.md U15 {CJ}; FW/build-evidence/ui-board/README.md:13 {T} | Protective trips are hardware and do not depend on the UI | external (lab) + owner | CMP-05 | A hardware STOP needs one J7 pin and a controller change |
| UI-15 | Residual-heat / status indication (LEDs) | Both | OPEN | none: no LED on the UI or controller BOMs | UIB/bom/ui-parts.csv {CJ}; FF4 front-panel-engineering-plan.md:44-46 {T} ("design rule" only); DECISIONS.md:188 {CJ} (LED output "unsupported-safe") | A hot-surface indication is typical for hobs; whether the governing standard requires it was **not verified** in the repo | owner+external | CMP-01 | The OLED could carry it if it stays powered |
| UI-16 | UI board design | Both | IN PROGRESS | [DEC] schematic rev 2 | UIB/README.md:10 {CJ} [CODE: 190/190 checks, 38/38 mutations] | — | Claude (layout) | ENC-03 (E1–E5) | **No layout, not fabricated.** Committed only on controller-j13-merge |
| UI-17 | UI parts stock | Prototype | OWNER-ONLY | none | UIB/DECISIONS.md U31-U32 {CJ} [VEN 2026-10-12] | Tact 0; TMP122 17; buzzer 280 | owner | — | — |
| UI-18 | UI firmware | Both | OPEN | — | FW/main/platform/ui_board_map.h:4-11, 32-35 {T}; FW/main/ui.c:3 {T}; FW/build-evidence/esp-idf/README.md:139-141 {T} | MCP23S08 map PROVISIONAL; GP3–GP5 still named encoder A/B/switch (rev 2: GP3 sensor CS, GP4 ALERT, GP5 spare); TMAG5170 not implemented; ui.c not built | Claude | — | **Contradiction** between firmware map and UI board |
| UI-19 | Controller-to-UI interface | Both | DONE | [DEC] C26: J7 12-way JST XH, SPI on its own host (SCK 40, MOSI 41, MISO 44, CS_OLED# 47, CS_EXP# 48, D/C 45) | CJ/DECISIONS.md:190-205 {CJ}; FW/components/hal/include/controller_pins.h:85-90 {T} | — | — | — | — |
| UI-20 | Enclosure items for the UI (E1–E5) | Both | BLOCKED | [PLAN] for R44 | UIB/DECISIONS.md U30, U32 {CJ} | E1 hole wall 0.3 mm; E2 socket height; E3 J7 access; E4 buzzer datum; E5 tab standoffs and steel keep-out R25 | owner | ENC-03 (R44 on hold) | — |
| UI-21 | Display lens | Both | OPEN | [DEC] 108 × 38 R4, 2.0 mm chemically strengthened soda-lime on 3M 4905P VHB | R43/BOM.csv:106-107 {U\*} | VHB is listed for 93 °C continuous [DS] | bench | — | Hot-oil and peel qualification open; fascia can reach 116–176 °C (UI-02) |
| UI-22 | Sealing and ESD targets | Production | OPEN | [ASM] IP67 plus spillage with the knob on or off; ESD ±8 kV contact / ±15 kV air | OC/SPEC.md:64 {U\*} | — | bench | — | Untested |
| UI-23 | Controls cost | Production | IN PROGRESS | none | OC/STATUS.md:5 {U\*} [estimate] | Buttons $10.57–19.85 (vs APEM ~$84); knob $22–50; tooling/NRE $27–67k | owner | — | — |
| UI-24 | Wi-Fi and the web UI | Production | OPEN | none: Wi-Fi is an "option, unqualified" | CJ/DECISIONS.md:148-154 {CJ}; FW/components/webui {T}; R43/BOM.csv:86, 194 {U\*} (WROOM-1U + a custom Johanson 2450AT18A100 antenna board) | — | owner | — | Shipping Wi-Fi adds FCC 15C / ISED radio approval (CMP-18) |

## 6. Enclosure and mechanical (R43 line)

**R43 has never been committed on any branch.**

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| ENC-01 | R43 digital candidate | Both | IN PROGRESS | [DEC] status `DESIGN_CANDIDATE_PENDING_INTEGRATION_REVIEW`; BOM 218 rows | R43/CURRENT.json:3 {U\*}; R43/design/r43/HANDOFF.md:51, 72 {U\*} [CAD: "All gates pass"] | — | owner | — | — |
| ENC-02 | Commit or archive R43, OC and AF1 | Both | OPEN (HIGH) | — | `git log --all` finds no commit of R43 or OC | Data-loss risk (worktrees and scratchpads have been wiped before) | owner | — | — |
| ENC-03 | R44 owned-controls round | Both | BLOCKED | [DEC] OC: "Do not edit [R43] or start R44 until the owner reports it final" | OC/STATUS.md:9 {U\*}; R43/design/r43/HANDOFF.md:77 {U\*} | — | owner | The owner declaring R43 final | Blocks UI-04, UI-20, SNS-38 |
| ENC-04 | Revision numbering clash | Both | OPEN | — | PS/DECISIONS.md:3019-3020 {T} ("new bosses are an R44 enclosure change") vs R43 HANDOFF:77 (R44 = controls); AF1 jets = R45 | — | Claude | — | — |
| ENC-05 | Glass top part | Both | OPEN | [DEC] black glass-ceramic slab 350 × 340 × 4, R6 corners, flat-polished edges, 0.5 mm arris, Ø18 sensor hole | R43/BOM.csv:3 {U\*}; R43/design/r14/parts-research.md:75, 77 {U\*} | Material "glass ceramic or qualified ceramic glass"; **no part number, no supplier** | owner | — | CERAN / KeraBlack+ OEM-only (unverified); Capska black NeoCeram 4/5 mm is a stock option |
| ENC-06 | Glass RFQ | Both | OWNER-ONLY | — | R43/design/r43/HANDOFF.md:113, 127 {U\*}; R43/quote-package/QUOTE-REQUEST.md:25 {U\*} ("no print") | Bored and undrilled, bore-edge strength, thickness near the bore (SNS-33) | owner | — | Unsent |
| ENC-07 | Glass bore-edge strength | Both | OPEN (HIGH) | none | R43/design/r32/BENCH-PLAN.md:53 {U\*} [SIM] | 164–210 MPa modelled vs "≥ 110 MPa typical strength": the plan's "Top mechanical risk" | bench+external | ENC-06 | G1 test: 1.80 kg vessel dropped 10× from 150 mm over the bore |
| ENC-08 | Glass bond | Both | OPEN | [DEC] Novasil S 96 (S96-04-C04), 1.0 mm bed on 0.8 mm beads, plus a 1 mm edge seal | R43/BOM.csv:169 {U\*}; R43/design/r32/BENCH-PLAN.md:54 {U\*} | Rated −40/+180 °C [DS] | bench | — | G2 adhesion test open. Bond-line temperature vs 180 °C: **not found** (the glass underside reaches 230–250 °C at the centre, SPEC row 11) |
| ENC-09 | Prototype coil carrier | Prototype | DONE (CAD) | [DEC] McMaster 5076N31 G11/FR5 1/4 in sheet, machined | R43/BOM.csv:122 {U\*} | — | — | — | — |
| ENC-10 | Production carrier/former material | Production | OPEN | [DEC] PPS-GF40 moulded; requires CTI ≥ 175 and RTI ≥ 150 °C | R43/BOM.csv:198 {U\*}; R43/quote-package/QUOTE-REQUEST.md:16 {U\*}; COIL/HOT-LIMITS.md:14 {T} | Generic GF40: 220 °C continuous (Techtron), HDT/A 267 °C [DS] | owner | — | **Grade unspecified; UL RTI not found.** SPEC row 13 asks for "≥ 200 °C class" against RTI ≥ 150 in the quote (inconsistent) |
| ENC-11 | Air path | Both | IN PROGRESS | [DEC] Delta BFB1012VH-F00 blower → 105 × Ø5 base field → push hood → sink → exhaust plenum → 210 × Ø5 door field; ~27 % bleeds to the coil plenum | R43/design/r32/DECISIONS.md:73-80 {U\*} [CAD+SIM] | — | bench | — | Operating point "first-order model … Bench T1 airflow measurement" (HANDOFF:211) |
| ENC-12 | Noise | Production | OPEN | [SIM] about 41 dB(A) typical; owner target ≤ 45 dB(A) | R43/design/r32/DECISIONS.md:89 {U\*}; BENCH-PLAN.md:35 (A5) | — | bench | — | — |
| ENC-13 | Board-face air jets for > 18 A | Production | OPEN | [PLAN] 8 × Ø3 mm, 0.41–0.48 CFM, for enclosure round R45 | AF1/README.md:1-14 {OM} | "Nothing here is measured" | owner | ENC-03 | Gates the power rating above 17.5 A |
| ENC-14 | native-21 mounting | Both | IN PROGRESS | [DEC] item 76: seven standoffs at H1, H3–H8; H2, H9, H10 empty | PS/DECISIONS.md:3013-3020 {T} | — | Claude | — | **Contradictions:** NAT/PROTOTYPE-LOT.md "Fixings" (nylon H2–H7, metal H1) and R32 BENCH-PLAN.md:19 |
| ENC-15 | Controller and UI-board mounting | Both | DONE (CAD) | [DEC] controller: six nylon 6/6 V-0 snap-in supports, 12 mm. UI board: four Ø6 × 8 bosses (M3) on the 6061 OLED carrier, PEM IFHA-M3-10 | R43/BOM.csv:90-105 {U\*} | — | — | — | — |
| ENC-16 | Fasteners | Both | DONE | [DEC] one 2.5 mm hex key drives every metal M3/M4 (ISO 7380); PEM families 5 → 3 | R43/design/r43/HANDOFF.md:47 {U\*} | Service simplicity | — | — | — |
| ENC-17 | SELV segregation | Both | IN PROGRESS | [DEC] ≥ 8.0 mm to mains-class and ≥ 12.6 mm to tank-class parts; double-insulated SELV leads; Nomex barrier deleted | R43/design/r32/DECISIONS.md:31 {U\*} [CAD] | — | bench (E3) | — | — |
| ENC-18 | PS3 clearances | Both | DONE (CAD) | [DEC] rules DC ≥ 8 / AC ≥ 3.2 / AC-to-SELV ≥ 8 mm | R43/design/r43/DECISIONS.md:27, 76 {U\*}; HANDOFF:94 | DC block to HOT 9.01 mm; J13 pair 8.65 mm; barrier gaps 2.22 / 2.20 mm (rule ≥ 2.0) | — | — | — |
| ENC-19 | J13 barrier material | Both | OPEN | [DS] Formex GK-62, 1.575 mm FR PP | R43/design/r43/DECISIONS.md:23, 89 {U\*}; OC/DELEGATION.md:81 {U\*} | R43: V-0 / ≥ 105 °C "not stored in the repo". OC study 14 found "V-0 and RTI 115 °C", flag at 69–86 °C worst | owner | — | Finding not applied; ITW GK-62 inquiry in PS/owner-outbox/2026-10-12.md not sent |
| ENC-20 | Cable ties | Both | OPEN | none | R43/design/r43/DECISIONS.md:93 {U\*}; OC/DELEGATION.md:81 {U\*} | OC: raise to PA66 rated ≥ 120 °C (tie reaches 101 °C worst) | owner | — | Catalogue number open at four points |
| ENC-21 | Unanchored 315 mm mains span | Both | OPEN | none | R43/design/r43/DECISIONS.md:69-73 {U\*} [CAD] | Nearest SELV 16.09 mm; 11.10 mm after 4.99 mm droop | bench | — | — |
| ENC-22 | EMI: seat ring | Both | IN PROGRESS (design; pre-scan missing) | [DEC] seat ring P1 one jointless piece | R43/design/r32/DECISIONS.md:66-69 {U\*} [SIM] | FCC §18.305 margin: 731 vs 1500 µV/m (2082 with the ring broken) | bench | — | — |
| ENC-23 | EMI contingency screen | Production | OPEN | [ASM] fit a perforated 0.5 mm steel screen, PE-bonded at 2 points, if the pre-scan is within 6 dB | R43/design/r43/HANDOFF.md:179 {U\*} | — | Claude (CAD fit) | TST-13 | No metal shield under the coil today ("ring 1.2 W") |
| ENC-24 | Coil-eye eddy flag | Both | OPEN | none | R43/design/r31/BENCH-PLAN.md:48 {U\*}; HANDOFF:221 | Closes with bench S1 field data | bench | — | Links SNS-15/22 |
| ENC-25 | Feet | Both | OPEN | [DS] McMaster 8689N18 push-in silicone, 3.18 mm grip | R43/BOM.csv:24-27 {U\*}; R32/DECISIONS.md:62 | — | bench | — | Base is 2.03 mm; BOM has 4 rows but the design has 5 feet (**contradictions**) |
| ENC-26 | Mains cord | Both | OPEN | [DEC] detachable NEMA 5-15P to IEC C19, 15 A, 14 AWG, ~1.8 m, UL/CSA listed | R43/BOM.csv:34 {U\*}; HANDOFF:215 | — | owner | — | "Part number to select" |
| ENC-27 | Inlet | Both | DONE (selection) | [DEC] Schurter EC11.0001.001 switched C20 inlet, 2-pole rocker (IEC 16 A / UL 20 A, 250 V) [DS] | R43/BOM.csv:34 {U\*}; R43/design/r32/DECISIONS.md:64 {U\*} | Acts as the disconnect | — | — | — |
| ENC-28 | Inlet fuse deleted | Both | IN PROGRESS | [DEC] R28: no inlet fuse; branch breaker plus F1 | R43/design/r43/HANDOFF.md:214 {U\*} | — | external | CMP-05 | **Contradiction** inside R43/design/r32/CERTIFICATION-QUESTIONS.md (:10 "no inlet fuse" vs :40 "30 A inlet fuse") |
| ENC-29 | Earth bonding | Both | IN PROGRESS | [DEC] cord PE to a chassis star; door and bulkhead earth through 2 screws each; cover through 4 screws + one wired bond; braid to S1; sink strap to S3 | R43/design/r32/CERTIFICATION-QUESTIONS.md:76-77 {U\*}; R43/BOM.csv:154, 161 {U\*} | E1 ≤ 0.1 Ω at 25 A for 120 s (model ~38 mΩ); EM8 ≤ 2.5 mΩ per bond | bench | — | Cover earthing **contradiction** ("welded stud" at :57 vs 4 screws vs "no CD welding") |
| ENC-30 | TCO parts | Both | OPEN (HIGH) | [ASM] Microtemp G4A on the sink and under the glass, "rating to select" | R43/BOM.csv:59-60 {U\*} | Stuck-on backstop | owner | PWR-58 | — |
| ENC-31 | D-22 inlet EMI module | Both | BLOCKED | [ASM] a 110 × 80 × 50 allocation only | R43/BOM.csv:58 {U\*}; CAND/c23-supply-topology/MODULE-REQUEST.md:1-12 {T}; PS/OPEN-ITEMS.md:118 {T} | Power stage asks for its Y caps to be removed and an SCF31X choke | owner | Module selection | Links PWR-72 |
| ENC-32 | PS3 part in the enclosure | Both | OPEN | — | R43/BOM.csv:206 {U\*} (IRM-60-15ST) vs PS/DECISIONS.md:1504 {T} (MPM-65-15ST) | — | Claude | — | **Contradiction** (CTL-29) |
| ENC-33 | Enclosure quote package | Both | OWNER-ONLY (prepared, not sent) | — | R43/design/r43/DECISIONS.md:85 {U\*} | — | owner | — | The R14, R22 and R33 packages were never sent either |
| ENC-34 | Enclosure cost BOM | Production | OPEN | none | R43/design/r43/HANDOFF.md:102 {U\*} | Lives only in a claude.ai artifact (T3BemZGn4BHjMzvSk4wyau), "estimates until quotes arrive" | Claude | — | No repo file |
| ENC-35 | R4 flush front | — | DONE (superseded concept) | [DEC] `PROTOTYPE_NOMINAL_FIT_ONLY` | PSI/output/temper-flush-front-r4/CURRENT.json:3 {T} | — | — | — | — |
| ENC-36 | Minor BOM inconsistencies | Both | OPEN | — | R43/BOM.csv:122 (79 coil jets) vs design/r34/DECISIONS.md:49 (87); BOM.csv:132 (custom A-286 wave spring) vs r39/DECISIONS.md:23 (standard Smalley Inconel X-750) | — | Claude | — | — |
| ENC-37 | Enclosure thermal soak | Both | OPEN | [PLAN] | PS/OPEN-ITEMS.md:63 (B10 list) {T} | — | bench | — | — |

## 7. Firmware and control (FW = PSI/firmware unless noted)

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| FW-01 | Which firmware is of record | Both | OPEN (HIGH) | [DEC] item 79: PSI firmware matches C49 | PS/DECISIONS.md:3049-3054 {T}; FW/README.md:166-170 {T} | — | Claude+owner | DOC-02 | Three diverging lines: **PSI** (C49 pins, BIAS_GOOD, no C1 sensor code); **origin/main** (C1 sensor firmware); **ctrl-j13/firmware** (stale, 8ab8e8220, OVER_TEMP 80 °C) |
| FW-02 | State machine | Both | DONE (host) | [CODE] 9 states (INIT, IDLE, PAN_DET, PREHEAT, HEATING, NO_PAN, COOLDOWN, FAULT, RUNAWAY_FAULT); 9 reachable, 63 edges, 5 invariants | FW/main/state_machine.h:30-39; FW/transition_table.yaml:87-88; FW/tools/proof_record.json {T} | — | — | — | FW/README.md:9-20 lists 8 states (**stale**) |
| FW-03 | Transition table as single source | Both | DONE | [CODE] codegen fails on any missing (state, event) cell; CI checks drift | FW/transition_table.yaml:1-12; .github/workflows/firmware-tests.yml:162-164 {T} | — | — | — | — |
| FW-04 | Crosscheck divergence | Both | OPEN | none: "a firmware maintainer's call" | state-machine-crosscheck-allowlist.yaml:31-49 {T} | (STATE_FAULT, EVENT_FAULT_RESET_PERSISTS) goes to FAULT_NONE in production but FAULT_OVER_TEMP in the test generator | Claude+owner | — | Open since 2026-08-07 |
| FW-05 | Runaway boundary | Both | IN PROGRESS (host-tested; not on hardware) | [CODE] 300 °C absolute and 15 °C/s, checked before all state logic; latched with no software clear | FW/main/state_machine.c:247-250, 374-375, 503-517; FW/config.yaml:224-234 {T} | — | bench | — | — |
| FW-06 | MAX31865 fault cycle | Prototype | OPEN (HIGH) | [DEC] C37: the board needs the **manual** cycle with ≥ 5.5 ms per step | FW/components/sensors/include/max31865.h:34, 48 {T} (AUTOMATIC, 0x04); CJ/DECISIONS.md:544-545 {CJ} | C37: the automatic cycle false-flags a healthy input (status 0x18) at all 48 transient corners [SIM] | Claude | — | The fix exists on origin/main (firmware D-FCYC) {OM}; not in PSI. **Pan RTD will likely fault at first power** |
| FW-07 | MAX31865 threshold words | Prototype | OPEN (HIGH) | [DEC] C46: 35544 (360 °C) / 12844 (−40 °C) | FW/config.yaml:129-143 {T} (1526 / 45722 = 10 / 300 Ω); CJ/DECISIONS.md:669-685 {CJ} | — | Claude | — | C46 says "firmware … and this repo now agree": **false on PSI** |
| FW-08 | Heatsink ADC gain (C45, 0.85507) | Prototype | OPEN | [DEC] C45 | CJ/DECISIONS.md:641, 466 {CJ} | Not found in PSI firmware (grep) | Claude | — | origin/main firmware carries 0.855072 {OM} |
| FW-09 | Watchdog feed point | Both | OPEN | [DEC] C42: feed only from the supervisor task, after a progress check | FW/main/state_machine.c:239-245 {T}; CJ/DECISIONS.md:605 {CJ} | Code feeds at the top of every update | Claude | — | — |
| FW-10 | Watchdog timeout statement | Both | OPEN (doc) | [DEC] C42: 0.9–2.5 s | CJ/DECISIONS.md:600 {CJ}; FW/README.md:327 {T} (1.6 s); FW/components/power/COMMISSIONING.md step 1 {T} (0.9–1.6 s) | — | Claude | — | **Contradiction** |
| FW-11 | BIAS_GOOD read-back | Prototype | IN PROGRESS | [CODE] checks 1–3: idle stuck 3-of-8; high 2 ms after RUN_EN; 20 ms drop → FAULT_BIAS_GOOD_LOST | FW/README.md:106-172; FW/config.yaml:342-411 {T} | — | bench | — | Optional checks (d) and (e) not implemented. FW/README.md:337-338 still says "inert" (**stale**) |
| FW-12 | Legacy fan_guard thresholds | Both | OPEN | — | FW/components/safety/fan_guard.c:7, 27 {T} (T_MAX 80 °C, IGBT era) | — | Claude | — | — |
| FW-13 | Overcurrent code paths | Both | OPEN | [DEC] D1: the state machine uses BUS_FAULT and the tank trips | FW/main/platform/platform_esp32.c:68-75; FW/components/safety/safety.c:265-267; FW/config.yaml:292-319 {T} | read_dc_bus_current returns +INFINITY (dead); OVER_CURRENT_THRESHOLD 40 A "IGBT continuous rating" survives in unused code; IGBT_SHORT 50 A "UNCITED" | Claude | — | Dead code with stale safety text confuses an auditor |
| FW-14 | Tank ceiling | Both | DONE | [DEC] item 61; Kconfig default 175 (17.5 A), range 100–280 | FW/components/power/Kconfig:35-39 {T} | — | — | — | — |
| FW-15 | Pan detection constants | Both | IN PROGRESS | [ASM] PAN_DET 5000 ms, NO_PAN 3000 ms, debounce 10, confidence 3, Q_MAX ×10 100, R_MIN 800 mΩ | FW/config.yaml:40-50, 145-154 {T}; COMMISSIONING.md:476 | — | bench | COIL M4 | — |
| FW-16 | No-pan stop | Both | IN PROGRESS | [DEC] lag ≥ 84.0°, R ≤ 0.5 Ω, RMS ≥ 2.5 A, 240 halves (2.0 s) | FW/config.yaml:438-494 {T} [SIM coil-r1 model] | UL 858 47.8 allows 30 s | bench | — | — |
| FW-17 | Pre-start pan probe | Both | DONE (decision) | [DEC] F3: no probe on today's hardware (one 8.3 µs pulse stays under the trips; two do not) | FW/build-evidence/f3-pan-probe/README.md:1-12 {T} [SIM] | — | — | — | Aluminium pans stay a trip risk (COIL-31) |
| FW-18 | Minimum continuous power | Production | OPEN | none | COMMISSIONING.md:524 (H12) {T} [SIM] | ≈ 73 W into a 1.4 Ω pan; over-delivers below the 60 kHz point | owner | — | Simmer usability |
| FW-19 | Power loop and live retiming | Both | IN PROGRESS | [CODE] 60 → 35 kHz, ±6 % dead band | FW/components/power/Kconfig:57-67; COMMISSIONING.md:475, 522 (H10) {T} | — | bench | — | "Live retiming HIL — not done" |
| FW-20 | Q-aware lag threshold (coil F2) | Both | OPEN | none found in FW | COIL/README.md:234-238 | 45° lag binds in 45 of 108 model runs | Claude+owner | Power-stage confirmation of commutation current | Not verified in FW |
| FW-21 | Inlet current regulation | Both | IN PROGRESS | [ASM] 13.5 A regulated; e_est 10 % provisional; hold/trip 11.99 / 13.36 A (blower off) | FW/README.md:78-86; Kconfig:84-88; COMMISSIONING.md:330, 482-484 {T} | — | bench | BENCH-RMS | — |
| FW-22 | Electrical calibration | Prototype | OPEN | [PLAN] COMMISSIONING step 1: VBUS_OFFSET_UV, VBUS_GAIN_PPM, CT_MON_ZERO_MV, RMS_GAIN_PPM, LINE_ZC_OFFSET_US, VSW_DELAY_NS, CT_ZC_DELAY_NS | Kconfig:30-33, 90-135; COMMISSIONING.md:162-194, 457-496 {T} | Defaults 0 / unity; TEMPER_POWER_CALIBRATED=n; every "Measured" cell is empty | bench | Boards | — |
| FW-23 | RTD calibration (offset / Callendar–Van Dusen trim) | Both | OPEN | none: **not found** | no row in COMMISSIONING.md:457-490 | — | Claude | — | Gap |
| FW-24 | Coil calibration and tank sweep | Prototype | OPEN | [PLAN] measure the coil's L, Q and DCR before use; re-run the tank sweep on it | NAT/PROTOTYPE-LOT.md:161-162 {T}; PS/DECISIONS.md:3056+ {T} | — | bench | COIL-26 | — |
| FW-25 | Hardware binding off by default | Both | DONE | [CODE] CONFIG_TEMPER_POWER_HW_BINDING=n; mode INHIBITED; PERMIT never asserted | COMMISSIONING.md:116-117; Kconfig:3-9 {T} | Safe default | — | — | — |
| FW-26 | ESP-IDF target build | Both | DONE (committed log) | [CODE] strict v5.3.6 build passes (f0cbab2f0) | FW/build-evidence/esp-idf/README.md:17-47; bin-size.txt {T} | Built outside the repo | Claude | — | Bin size 412,960 (bin-size.txt) vs 410,000 (README). Kconfig:7-8 says "never compiled" (**contradiction**) |
| FW-27 | Open build warnings | Both | OPEN | — | FW/build-evidence/esp-idf/README.md:60-71 {T} | pll_control capture callbacks unwired; `estimation_complete` unused at state_handlers.c:282 ("possible logic gap"); deprecated ADC_ATTEN_DB_11 | Claude | — | — |
| FW-28 | Host tests | Both | DONE (committed evidence, not re-run) | [CODE] 29/29 ctest targets (2026-10-12): state_machine_tests 75, sil_fault_tests 23, max31865 20, platform_logic 17 | FW/build-evidence/esp-idf/ctest-summary.txt {T}; FW/test/CMakeLists.txt (31 targets) | — | — | — | FW/README.md:254-255 says "37 unit / 30 integration" (**stale**) |
| FW-29 | CI test coverage | Both | OPEN | — | .github/workflows/firmware-tests.yml:147, 192, 220 {T} | CI runs only controller_pins / thermal_mgmt / ntc_guard / coil_guard, state_machine / fault_list, and sil_fault_tests. **Not run:** n21_binding, tank_freq, blower_aux, platform_logic, max31865, safety, pan_detection, integration, pid, pll, rms | Claude | — | — |
| FW-30 | ESP-IDF build in CI | Both | OPEN | — | .github/workflows/release-artifacts.yml:3-18 {T} (runs only on a published release) | PS/DECISIONS.md:3051 says "the CI IDF build is the proof" | Claude | — | **Contradiction** |
| FW-31 | Code coverage figure | Production | OPEN | none: not found | FW/README.md:116 {T} (only FMEA chain rows: 36.9 %, 13.8 % as built) | — | Claude | — | — |
| FW-32 | Never run on hardware | Prototype | OPEN | — | Kconfig:7-8; COMMISSIONING.md:133; FW/README.md:192-193 {T} | — | bench | Boards | — |
| FW-33 | Field update path | Production | OPEN | [DEC by omission] no OTA (factory partition only) | FW/partitions.csv:3-6 {T} | — | owner | — | Production units cannot be updated without opening them |
| FW-34 | Software safety class | Production | OPEN | none | OI/CERTIFIER-CHECKLIST.md §12-13 {M} | UL 60730-1 Annex H / UL 1998 applicability | external | CMP-05 | — |
| FW-35 | Coil NTC table for the 104GT-2 bead | Both | OPEN | [DEC] C32 requires it | CJ/DECISIONS.md:302-330 {CJ} | — | Claude | — | Not verified in FW |
| FW-36 | Rim and coil NTC plausibility constants | Both | IN PROGRESS | [ASM] rim below range > 30 s while pan > 150 °C; coil < 25 °C after > 5 min at > 50 %; "bench-tunable" | FW/README.md:214-220 {T} | — | bench | — | — |
| FW-37 | Setpoint range | Both | OPEN (doc) | — | FW/README.md:360 {T} (50–250 °C) vs FW/config.yaml:25 {T} (MIN_TEMP 30) | — | Claude | — | — |
| FW-38 | Face-fan stall protection | Production | OPEN | none | PS/OPEN-ITEMS.md:35 (S26) {T} | thermal_mgmt.h clamps only the blower | Claude | PWR-39 | — |

## 8. Test and validation

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| TST-01 | Any bench measurement | Both | OPEN | — | G-01 | — | bench | Orders | **None exists** |
| TST-02 | Validation master plan currency | Both | OPEN | — | PS/validation-plan/00-MASTER-PLAN.md:3, 225-239 {T} (dated 2026-10-02, native-17) | Plan 09 says "not started", but PS/validation-plan/enclosure-fit/plan-result.json {M} says pass | Claude | — | zapote/VALIDATION.md:46 links to a missing validation/README.md |
| TST-03 | Bench-capture verdict tool | Both | DONE (tool) | [CODE] bench_verdict.py, tests B0–B4 | PS/validation-plan/bench-verdict.md {T} | "No aggregate PASS means hardware qualification" | — | — | No captures yet |
| TST-04 | Power-stage bring-up | Prototype | OPEN | see PWR-76 | NAT/BRING-UP.md {T} | — | bench | — | — |
| TST-05 | D-8 double pulse (body-diode recovery) | Both | OPEN | [PLAN] | PS/OPEN-ITEMS.md:40 (S14) {T}; validation-results/01-switching-parasitics/STATUS.md {T} | Diode dv/dt at 0.96–0.97 of rating | bench | Boards | — |
| TST-06 | Gate timing / dead time on the board | Prototype | OPEN | [PLAN] confirm at bring-up | PS/DECISIONS.md (2026-10-03 entry) {T} | — | bench | — | — |
| TST-07 | BENCH-RMS (aux load) | Prototype | OPEN | [PLAN] | PSI/output/temper-aux-load-r1/BENCH-RMS.md {T} | Retires the provisional allowance | bench | — | — |
| TST-08 | S25 bank hot spot on the first board | Prototype | OPEN | [DEC] before the rest of the lot is powered | NAT/PROTOTYPE-LOT.md:117-124 {T} | — | bench | — | — |
| TST-09 | Thermal bench set | Both | OPEN | [PLAN] sink load (> 125 W → K1); interface Rcs; board-face h; J1 temperature; PS2 bay air; gate-row IR reading; enclosure soak | PS/OPEN-ITEMS.md:63, 127-137 {T} | — | bench | — | — |
| TST-10 | UL 858 bench cases (B10) | Both | OPEN | [PLAN] 59.6 iron bar ≤ 35 °C rise; fork/spoon/knife pan detection; 47.8 off within 30 s; bad-pan set | PS/OPEN-ITEMS.md:63 {T}; NAT/PROTOTYPE-LOT.md:198-203 {T} | — | bench | — | Applies only if UL 858 governs (CMP-01) |
| TST-11 | S15 stuck-on injection | Both | OPEN | [PLAN] jumper DIS off; time the TCO | NAT/PROTOTYPE-LOT.md:191 {T} | — | bench | PWR-58 | — |
| TST-12 | OCP comparator population test | Production | OPEN | [PLAN] n = 30 TLV3201 from ≥ 3 reels, 25–125 °C | PS/OPEN-ITEMS.md:32 (S23) {T} | — | bench | — | — |
| TST-13 | EMC pre-scan | Both | OPEN | [PLAN] EM4 conducted 9 kHz–30 MHz, ≥ 6 dB below 47 CFR §18.307(a); EM5 loop ≤ 750 µV/m; EM6 ≥ 10 dB below §18.305; EM7 IEC 62233 ≤ 6.25 µT | R43/design/r32/BENCH-PLAN.md:90-93 {U\*} | — | bench/external | Equipment | No LISN or analyser on the gate-10 list |
| TST-14 | Hipot / dielectric | Both | OPEN | [PLAN] type 3000 Vac 60 s; routine 2000 Vac 1 s; PD not assessed | PS/DECISIONS.md:280 {T}; NAT/fab/FAB-NOTE.md:34 {T} | Gates mains-connected operation | bench/external | — | — |
| TST-15 | Touch current | Both | OPEN | [PLAN] at first article | NAT/PROTOTYPE-LOT.md:194 {T} | Limit class 0.5 vs 0.75 mA open (CMP-26) | bench | — | — |
| TST-16 | Earth continuity | Both | OPEN | [PLAN] E1 ≤ 0.1 Ω at 25 A for 120 s; EM8 ≤ 2.5 mΩ per bond | R43/design/r32/BENCH-PLAN.md:42-43, 94 {U\*} | — | bench | — | — |
| TST-17 | Burn-in | Production | OPEN | none: **not found** | — | — | Claude (plan) | — | — |
| TST-18 | End-of-line test content | Production | OPEN | [PLAN] only B8 (force MON_GOOD_HA then MON_GOOD_HB low; BIAS_GOOD must drop) plus EOL pads | PS/OPEN-ITEMS.md:65 (B8) {T}; OI/CERTIFIER-PACKET.md:58 (#27) {M} | — | Claude+external | — | Certifier acceptance asked |
| TST-19 | End-of-line fixture | Production | OPEN | none: **not found** | zapote/fixtures holds only validator JSON | Bed of nails, functional coil/sensor test, hipot station | Claude (spec) | — | — |
| TST-20 | Coil M1–M7 | Prototype | OPEN | see COIL-26 | — | — | bench | — | — |
| TST-21 | Sensor bench (τ63 survey; T1–T3; PCB items; T5 durability) | Prototype | OPEN | see SNS-19/22/23 | — | — | bench | — | — |
| TST-22 | Enclosure bench plan | Both | OPEN | [PLAN] G1 drop, G2 adhesion, A5 noise, E3, M11 feet drop, span sag | R43/design/r32/BENCH-PLAN.md {U\*} | — | bench | — | — |
| TST-23 | UI bench | Both | OPEN | [PLAN] MISO eye; stray-field jitter; tact force; buzzer SPL; tab temperature | UIB/DECISIONS.md U32.3 {CJ} | — | bench | — | — |
| TST-24 | Firmware hardware-in-the-loop | Both | OPEN | none | COMMISSIONING.md (commissioning record) {T} | — | Claude+bench | — | — |
| TST-25 | Sensor leak-barrier production test | Production | OPEN | [PLAN] 192-assembly qualification plan | leak-barrier/SPEC.md {OM} | — | external | — | No lab engaged |
| TST-26 | Gerber hole review currency | Prototype | OPEN | [CODE] 869/869 holes checked, but at stage 19b | NAT/README.md:24-41 {T} | Re-run on s53 | Claude | — | NAT/README.md:8 gerber SHA c9eaf0d9… vs FAB-NOTE a6afd37a… (**stale**) |

## 9. Compliance and legal (not legal advice)

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| CMP-01 | Governing safety standard | Production | OPEN (HIGH) | none: UL 858 vs UL 1026 undecided | OI/CERTIFIER-CHECKLIST.md:22-29 {M}; OI/CERTIFIER-PACKET.md:19-21 {M}; R43/design/r32/CERTIFICATION-QUESTIONS.md:7, 83 {U\*} | "No primary UL text has been read"; IEC 60335-1 used as a proxy [ASM] | external (certifier) | CMP-05 | Everything in this section depends on it |
| CMP-02 | Markets | Production | DONE (decision) | [DEC] 120–127 V~ 60 Hz, NEMA 5-15P; US/Canada/Mexico from day 1 (owner) | PS/DECISIONS.md:311 {T} | — | — | — | docs/REGULATORY_COMPLIANCE.md:11-31 (UL 858 + CE/EN 55014) is **stale** |
| CMP-03 | Nameplate voltage | Production | OWNER-ONLY | none | PS/DECISIONS.md:236 {T} | — | owner | — | Same as PWR-48 |
| CMP-04 | Nameplate power | Production | OPEN | none | see G-04 | — | owner | Bench data | — |
| CMP-05 | Send the certifier packet and checklist | Both | OWNER-ONLY (draft, not sent) | — | OI/CERTIFIER-PACKET.md:3 {M}; OI/CERTIFIER-CHECKLIST.md {M} (29 items; email placeholders, no recipient); NAT/sourcing/inquiries/F1-CERTIFIER.md:3 {M} | — | owner | — | The s53 refresh is **uncommitted**. The lab call is also outstanding (PS/DECISIONS.md:57) |
| CMP-06 | Enclosure certification questions | Production | OWNER-ONLY | — | R43/design/r32/CERTIFICATION-QUESTIONS.md:5 {U\*} ("not yet submitted") | — | owner | — | — |
| CMP-07 | Datasheet-ledger rule (approval basis per rating) | Both | DONE (gate) | [DEC] one entry per BOM line, ratings with their approval basis (IEC vs cULus vs CSA); the gate fails on any VIOLATION or UNAUDITED safety/power line | PS/native-21/verification/datasheet-ledger/README.md:3-20 {M} | Created after J1 1711725 proved to be 24 A IEC but 15 A cULus / 10 A CSA | — | — | The gate does not run in PR CI (DOC-12) |
| CMP-08 | Ledger state at s53 | Both | IN PROGRESS | [DS] 95 lines: 3 VERIFIED / 92 PARTIAL / 0 UNAUDITED / 0 VIOLATION, PASS; 209 gaps (54 bench, 31 certifier, 46 owner, 76 B3-estimate) | ledger README "Current findings" and ledger-report.json {M} | — | Claude+owner | — | **Uncommitted.** Committed HEAD says "2/28/62"; OPEN-ITEMS:47 says 3/32/58; OPEN-ITEMS:30 says 3/91/0 (**contradictions**) |
| CMP-09 | UL files verified in UL Product iQ | Production | OWNER-ONLY | none | OI/CERTIFIER-CHECKLIST.md §17 {M} | E511334, E542996, E311313, E181974 and E76222 are quoted from datasheets only; T1 CST3015-200ED has no working-voltage figure or approval file | owner (UL iQ login) | — | — |
| CMP-10 | IEC-60601-only supply modules (PS2 MPM-20-24, PS3 MPM-65-15ST) | Production | OPEN (HIGH) | [DEC] chosen for leakage | OI/CERTIFIER-CHECKLIST.md:271-282 {M}; OI/CERTIFIER-PACKET.md:47 (A3 #14) {M} | No UL file printed | external | CMP-05 | A "no" breaks the leakage budget (0.653 mA) |
| CMP-11 | J1 mains terminal approval | Both | IN PROGRESS | [DEC] J1 changed to Phoenix 1714971 MKDS 5/2-9,5 (UL/cUL and CSA 30 A, 300 V) | ledger README:105-110 {M} | — | owner | — | E60425 / CSA 13631 unconfirmed (UL iQ 403) |
| CMP-12 | Stuck-on (UL 858 25.3.1) | Production | OPEN (HIGH, ranked #1) | [ASM] TCO only | OI/CERTIFIER-CHECKLIST.md:227-240 {M}; OI/CERTIFIER-PACKET.md:57 {M} | Removes gate drive, not the power path; the inlet relay (DNP) is not built | external+owner | CMP-05 | A "no" means relay hardware on the board |
| CMP-13 | Firmware-only protections | Production | OPEN (HIGH) | none | OI/CERTIFIER-CHECKLIST.md:169-181, 201-225 {M} | 15 A line limit and 22 A tank/creepage clamp are firmware; PEC status of the monitor/DIS path (60335-1 19.11/19.13) | external | CMP-05 | — |
| CMP-14 | Insulation coordination basis | Production | OPEN | [ASM] PD3; coil-lane working voltage as line-cycle RMS | PS/DECISIONS.md:242-250 {T}; OI/CERTIFIER-PACKET.md A3 #11 {M} | A crest-RMS reading forces a board-wide ≥ 5.7 mm re-layout | external | CMP-05 | — |
| CMP-15 | Reinforced insulation at the heatsink | Production | IN PROGRESS | [DEC] M11 reinforced by thickness | PS/DECISIONS.md:268-304 {T}; docs/evidence (commits 17a4e6d94, 6b109dd91, d452536c8) {T} | cl. 8.2 keys reinforced insulation on probe-B touchability (the repo's own reading) | external | CMP-05 | — |
| CMP-16 | F2 protection behind a non-UL resistor | Production | OPEN | none | ledger README "Resolved" {M}; OI/CERTIFIER-PACKET.md A2 #8 {M} | F2 Schurter 3403.0279.23 (1500 A UL at 277 VAC) sits behind R130 0.15 Ω AC05 (not UL-recognised); J11 fault bounded at 980 A [SIM] | external | — | — |
| CMP-17 | Bus discharge and label | Production | OPEN | [SIM] τ 6.6 s; plug pin < 34 V in 1 s is met | OI/CERTIFIER-PACKET.md:63 {M} | — | external | — | "Wait 15 s" label question |
| CMP-18 | EMC/radio route | Production | OPEN | none | R43/design/r32/CERTIFICATION-QUESTIONS.md:62 {U\*} | FCC Part 18 (ISM) asked; no Part 15C / modular-grant or ISED radio analysis found for the Wi-Fi + custom antenna | external | UI-24 | — |
| CMP-19 | EMF (IEC 62233) | Production | OPEN | [PLAN] EM7 ≤ 6.25 µT | R43/design/r32/BENCH-PLAN.md:93 {U\*} | — | bench/external | — | — |
| CMP-20 | Mexico (NOM) | Production | OPEN | [DEC] marks UL/CSA plus NOM (ANCE/NYCE) | R43/design/r32/CERTIFICATION-QUESTIONS.md:65 {U\*} | Which NOM standards apply is a question | external | — | — |
| CMP-21 | Labelling and rating plate | Production | OPEN | none | PSI/docs/REGULATORY_COMPLIANCE.md:60-84 {T} (generic 2025-12 template: 120 V / 1800 W US, 230 V / 2000 W EU, CE, WEEE) | — | Claude (draft) | CMP-01, G-04 | No artwork. Bilingual (Canada) and Spanish (Mexico) labelling **not found** |
| CMP-22 | User manual and safety instructions | Production | OPEN | none | PSI/docs/REGULATORY_COMPLIANCE.md:86-104 {T} (requirements list only) | — | Claude (draft) | CMP-01 | Must cover the aluminium-pan restriction (COIL-31) and the hot-surface warning |
| CMP-23 | Patent review | Production | OWNER-ONLY | [DEC] engineer's claim chart, "not legal advice and not a freedom-to-operate opinion"; C1 chosen | SR3/PATENTS.md:3-7, 18, 26-48, 158-172 {OM} | Breville US11378463B2 (active to 2038-11-14) vs C0; Impulse US12712433B1 is mined in MAIN/output/temper-coil-driver-r1 {U\*} | external (counsel) | — | Counsel actions 1–5 not engaged. **Not legal advice** |
| CMP-24 | Patent-driven design rules | Both | DONE | [DEC] "at most one under-cap sensor feeds hardware"; "Never add plunger position sensors" | SR3/PATENTS.md:75, 84-85 {OM} | — | — | — | — |
| CMP-25 | Wave-spring floating-part creepage | Production | OPEN | see SNS-17 | — | — | external | — | — |
| CMP-26 | Touch-current limit class | Production | OPEN | none | OI/CERTIFIER-PACKET.md:26 {M} | Portable 0.5 mA or stationary 0.75 mA | external | CMP-01 | docs/REGULATORY_COMPLIANCE.md:126 says "< 0.75 mA (Class I)" |
| CMP-27 | Surge test levels | Production | OPEN | see PWR-57 | — | — | external | — | — |

## 10. Supply chain and production

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| SUP-01 | Assembly split: JLC does everything possible; home bench is through-hole only | Both | IN PROGRESS | [DEC-draft] consign-r1 (PWR-10) | CAND/consign-r1/DECISIONS-DRAFT.md {T} | Owner's preference | owner | — | **Exceptions that break it:** controller R39 0805 hand-fit (CTL-13); UI tact switches (SMD, 0 stock, UI-08); coil crimping and winding (COIL-22) |
| SUP-02 | Power-board production readiness at 500 | Production | OPEN | none | scorecard-native21s53.json (cost.*) {T}; PS/OPEN-ITEMS.md:56 {T} | 13–14 lines short; build lead 28.0 wk (scorecard) or 29 wk (L1); JLC-assemblable share 0.851–0.853; 17 single-source lines, 6 zero-stock lines | owner | — | — |
| SUP-03 | Long-lead pre-orders | Production | OWNER-ONLY | see PWR-19 | NAT/sourcing/study-2026-10-15/README.md:190-209 {T} | Bank 23–28 wk, MOQ 2,080 | owner | — | — |
| SUP-04 | Second sources | Production | OPEN | none | NAT/sourcing/study-2026-10-15/README.md:101-188 {T}; PS/OPEN-ITEMS.md:68 (B9) {T} | C5/C6 alternate B32676G1106K (suffix unconfirmed); J2/J5 alternates. **None verified** for J6 1704004 or T1 (Coilcraft direct; "get a Coilcraft quote"); JSMSEMI PMEG clone unqualified | owner | — | Also single-source: the OLED module, R39, the TMAG5170, the AlN tiles, the compound |
| SUP-05 | Scorecard pricing basis | Production | OPEN | — | PS/OPEN-ITEMS.md:81 (C8) {T} | 58 of 93 lines priced at class defaults (e.g. TL431A $0.40 vs $0.049) | Claude | — | — |
| SUP-06 | Controller supply | Both | OPEN | — | CTL-12, CTL-16 | R39 single source with a 22-week reel; TPS3703-Q1 26 weeks at DigiKey | owner | — | — |
| SUP-07 | UI supply | Both | OPEN | — | UI-17 | JLC-listed parts USD 12.60/board plus the tacts | owner | — | — |
| SUP-08 | Coil custom parts | Production | OPEN | none | COIL/ORDER-LIST.md:15, 26; COIL/HOT-LIMITS.md:22-37 | Litz (custom class 200: ~6 wk, £1000 MOQ earlier read); ferrite (custom, no price); ring lugs (50840 obsolete at DK; 1577639-1 24 wk); PPS carrier tool (no quote) | owner+external | — | — |
| SUP-09 | Coil winding process at volume | Production | OPEN | none: **not found** | SPEC row 13; PS/owner-outbox/2026-10-12.md (coil-winder RFQ, not sent) {T} | — | owner+external | — | No winder, fixture, cycle time or coil EOL test |
| SUP-10 | Sensor cartridge production | Production | OPEN | none | SR3/cad/QUOTE-LIST.md {U=OM} | Custom Kalrez wiper tool; leak-barrier production test (TST-25) | owner+external | — | No process, yield or fixture |
| SUP-11 | Enclosure production tooling | Production | OPEN | none: **not found** (only the controls NRE of $27–67k) | OC/STATUS.md:5 {U\*} | — | owner | ENC-33 | — |
| SUP-12 | Unit cost roll-up (power + controller + UI + coil + sensor + enclosure + glass + cord + assembly + test + packaging) | Production | OPEN | none: **not found** | pieces in PWR-20, CTL-15, UI-23, COIL-40, ENC-34 | — | Claude | Quotes | Parts are dated reads, not quotes |
| SUP-13 | Prototype cost roll-up | Prototype | OPEN | none: **not found as one file** | pieces: FETs $1,281.51 (PWR-12); bench sink ≈ $360 (PWR-32); AlN stacks ≈ $0.7–1.3k (PWR-23); controller parts USD 65.35/board + fees (CTL-15); sensor bench kit $313 / $1,285 (SNS-20); coil $200–500 per coil (COIL-40); LCR ≈ €899 (COIL-27); knob stage one $123.69–214.69 (UI-12) | — | Claude | — | The JLC power-PCBA total is not stated in the repo ("no prototype-lot parts total is claimed", PROTOTYPE-LOT:68-70) |
| SUP-14 | Retail packaging (carton, ISTA drop) | Production | OPEN | none: **not found** | PSI/docs/research/mit-product-design/readiness/mechanical/packaging.md {T} is internal board packaging, not a shipping carton | — | Claude+owner | — | — |
| SUP-15 | Production fixtures | Production | OPEN | [DEC] only the FET seat-before-solder fixture is specified (PWR-15) | PS/DECISIONS.md:473 {T} | Coil winding, sensor assembly and EOL fixtures not found | Claude | — | — |
| SUP-16 | Order-day stock re-read | Both | OWNER-ONLY | [DEC] re-read stock at order (every board) | NAT/PROTOTYPE-LOT.md {T}; CJ/ORDER.md {CJ} | — | owner | — | — |

## 11. Documentation and configuration control

| ID | Item | Phase | Status | Decision made | Evidence | Justification / why | Owner | Blocked by | Notes and risks |
|---|---|---|---|---|---|---|---|---|---|
| DOC-01 | Uncommitted and untracked evidence | Both | OPEN (HIGH) | — | {U\*}: R43, OC, MAIN/output/coil-review-2026-10-10, MAIN/output/temper-coil-driver-r1, SR3 STEPs. {U}: NAT/review-packet-s53, CAND/c54-*, OI/JLC-LAMINATE-QUESTION.md, PS/native-21/section.kicad_pcb, candidate-libs, models3d, routed. {M}: datasheet ledger, certifier packet/checklist, F1-CERTIFIER.md | Worktrees and scratchpads have been deleted before | owner (commit) | — | This file itself is uncommitted |
| DOC-02 | Branch integration | Both | OPEN (HIGH) | — | PSI is 789 commits ahead of origin/main and does not contain it (C1 sensor firmware, SR3 docs); controller-j13-merge unmerged (C49, UI board) | One baseline is needed before ordering | owner | — | — |
| DOC-03 | consign-r1 numbered in DECISIONS.md | Both | OPEN | — | CAND/consign-r1/DECISIONS-DRAFT.md {T} | — | Claude | — | — |
| DOC-04 | DECISIONS inventory | Both | DONE (list) | — | PS/DECISIONS.md (D1–D6 plus items to 80); CJ/DECISIONS.md (C1–C50) {CJ}; UIB/DECISIONS.md (U1–U32) {CJ}; COIL/README.md §2 (D1–D9); SR3/DECISIONS.md plus cad/, pcb/, bench/ DECISIONS {U=OM}; R43/design/rNN/DECISIONS.md {U\*}; OC/DECISIONS.md {U\*}; PSI/output/temper-aux-load-r1/DECISIONS.md; PS/validation-results/12-decisions/*.md | — | — | — | No cross-index of decisions across subsystems |
| DOC-05 | Stale documents | Both | OPEN | — | PS/README.md; CJ/README.md; FW/README.md; PS/OPEN-ITEMS.md header (s51, 18 A); NAT/fab/FAB-NOTE.md; NAT/sourcing/README.md; 00-MASTER-PLAN.md; COIL/README.md:253; COIL/HOT-LIMITS.md:39; SPEC line 59; zapote/VALIDATION.md:46; SR3/HANDOFF.md (15 K, ADS1115, pairs, DRDY, firmware-sim/) | — | Claude | — | See the contradiction register |
| DOC-06 | Frozen-folder discipline | Both | OPEN | [ASM] "treat learned artifacts as immutable, versioned, and hashed" is the only written rule | zapote/AGENTS.md:79-81 {T}; PS/native-21/frozen/manifest.json {T} (holds only {"version":"2.0"}) | — | Claude | — | — |
| DOC-07 | Revision-line registry | Both | OPEN | none | Lines found: enclosure temper-manufacturing-rNN (R43; R44 controls; R45 jets); sensor temper-sensor-rN (r3); coil temper-coil-r1; power native-NN / sNN; controller CNN; UI UNN | No single registry | Claude | — | Numbering clash (ENC-04) |
| DOC-08 | Two copies of the coil spec | Both | OPEN | — | MAIN working tree (sha256 637a7603…, uncommitted) vs PSI committed (2ec8cc8b…) | — | Claude | — | — |
| DOC-09 | Datasheet archive | Production | OPEN | — | UIB/DECISIONS.md:3 (datasheets in a scratch dir outside the repo); COIL/HOT-LIMITS.md (read through web search) | Ledger citations must survive | Claude | — | Repo is public, so copyright limits what can be committed |
| DOC-10 | Netlist libsource fields | Both | OPEN | — | PS/OPEN-ITEMS.md (B14) {T} | Stale | Claude | — | — |
| DOC-11 | Ledger gate in CI | Both | OPEN | — | .github/workflows/firmware-tests.yml:38, 66 {T} (ledger.json is only a path trigger) | — | Claude | — | — |

---

## Critical path

The ordered list of what unblocks what. Items in parallel share a number.

**(a) Working prototype**
1. **Preserve and baseline** (DOC-01, DOC-02, ENC-02, SNS-01).
   - Commit R43, OC, the SR3 STEPs and the uncommitted ledger and certifier work.
   - Merge controller-j13-merge and origin/main's C1 firmware into one baseline.
   - Cheap, and it protects everything after it.
2. **Firmware fixes needed before any RTD is powered** (FW-06, FW-07, FW-08, FW-09, FW-35).
   - Manual MAX31865 cycle; words 35544/12844; HS_ADC gain; WDI feed point; coil NTC table.
   - Claude can do these now, on the baseline from step 1.
3. **Owner decisions and outreach that gate the power order** (PWR-79).
   - Send the JLC laminate question (PWR-06).
   - Settle the inlet module, or write the EMI deviation (PWR-72).
   - Confirm the 31 CPL rows in the viewer (PWR-13).
   - Buy the FET lot (PWR-12) and the preheater; approve spend.
   - Then order the power PCBA (PWR-82).
4. **Controller order (in parallel with 3).**
   - Finish the JLC viewer checks: J1/J2/J3/J4/J7, D1–D6, C1 (CTL-09, CTL-10).
   - Decide R39: place DNP and hand-fit later, or wait (CTL-12, CTL-13).
   - Buy the harness parts and the TC2050 cable (CTL-22).
   - Order C49 (CTL-05).
5. **Coil (in parallel with 3 and 4).**
   - Ask RMC for stock; buy the Litz and ferrite (Mouser plates, traceable) (COIL-07, COIL-11).
   - Build the jig (COIL-20).
   - Settle the lug: insulated vs bare, part rated ≥ 130 °C (COIL-22, COIL-23, PWR-70).
   - Wind, tune, then run M1–M5 (COIL-26).
   - **Output:** measured L/R, which feeds the tank sweep (FW-24).
6. **Bench sink and its TCO** (PWR-32, PWR-58).
   - Needed before any switching.
7. **Bring-up** (PWR-76):
   - SELV → calibration (FW-22) → isolated DC bus;
   - first switching and dead time (TST-06), D-8 (TST-05);
   - S25 bank gate on board 1 (PWR-45);
   - fit BR1 → variac;
   - heat a ferrous pan at ≤ 17.5 A, winding ≤ 130 °C.
8. **Sensor (in parallel from step 1).**
   - Lean bench kit (SNS-20) → τ63 survey (SNS-19).
   - This decides C1. Then the adhesive and capillary statements (SNS-10, SNS-11), then the cartridge parts (SNS-02).
   - Whether first heating may run on a stand-in RTD or thermocouple is **not stated in the repo** (gap).
9. **Enclosure fit** (only needed for an enclosed prototype).
   - The owner declares R43 final → R44 controls (UI-20) → glass RFQ (ENC-06) → UI board layout (UI-16).

**(b) Production run** (after (a))

10. **Certifier engagement** (CMP-05). The answers fix the architecture:
    - governing standard (CMP-01);
    - the MPM modules (CMP-10);
    - stuck-on / TCO vs relay (CMP-12);
    - firmware-only limits (CMP-13);
    - working-voltage convention (CMP-14);
    - reinforced insulation at the sink (CMP-15).

    Any "no" can force board re-layout or relay hardware, so this precedes the production layout freeze.
11. **Power rating** (G-04, CMP-04):
    - board-face airflow, jets in R45 (ENC-13, PWR-39, PWR-40);
    - the production sink stack (PWR-22 to PWR-31);
    - then thermal validation at 22/28 A.
12. **EMI:**
    - inlet module (ENC-31);
    - pre-scan with a LISN (TST-13);
    - optional screen (ENC-23).
13. **Long-lead pre-orders** (PWR-17, PWR-18, PWR-19). L1 at 29 weeks sets the build date.
14. **Coil production:**
    - class-200 Litz (COIL-09);
    - ≥ 20 mm ferrite (COIL-12, COIL-13);
    - PPS carrier grade and RTI (ENC-10);
    - winder (SUP-09);
    - production L target (COIL-39).
15. **Sensor production:**
    - leakage production test (SNS-26, TST-25);
    - Vespel RTI (SNS-30);
    - FTO opinion before tooling (SNS-39, CMP-23).
16. **Manufacturing package:**
    - EOL test and fixture (TST-18, TST-19);
    - burn-in (TST-17);
    - labels and manual (CMP-21, CMP-22);
    - packaging (SUP-14);
    - unit cost roll-up (SUP-12);
    - external PCB review (PWR-81).

## Audit questions

1. Where is the one written definition of "working prototype done", and who signs it? (G-02)
2. What is the product's rated power: 1800 W, ~1041 W (model median) or ~650 W (pooled at 18 A)? Which basis goes on the nameplate? (G-04, CMP-04, G-05)
3. Which firmware tree is of record, and how is the C1 sensor code on origin/main going to reach the C49 build before the first RTD power-up? (FW-01, FW-06, FW-07, SNS-24, DOC-02)
4. C46 says firmware and controller "now agree" on the MAX31865 words. Who checked, on which branch? (FW-07)
5. The coil lug: the power-stage decision requires insulated M4 ring terminals and names a 105 °C vinyl part; the coil study specifies non-insulated lugs and a 130 °C winding limit. Which governs, and what is the lug's rated temperature and approval? (PWR-70, COIL-22, COIL-23, COIL-24)
6. Is the stud M4? Show the drawing, and correct HOT-LIMITS.md:39. (COIL-24)
7. What evidence supports reinforced insulation through 2 mm AlN at the sink, and has a certifier agreed that it is needed and sufficient? (PWR-22, CMP-15, PWR-29)
8. Why is clamp force stated three ways (60–80, ≥ 60/80, 45–102 N), and which value is on the drawing? (PWR-26)
9. Who resolves the BR1 gap-pad thickness (0.5 vs 1.0 mm), and what does it do to the stack height? (PWR-28)
10. How will JLC-soldered TO-247s meet 0.0195 mm of compliance when the model predicts 0.27–1.8 mm of tab spread? (PWR-15)
11. What is the stuck-on argument if the lab rejects a gate-drive-only TCO? What does the relay cost in board area and schedule? (PWR-58, CMP-12)
12. If the lab rejects the IEC-60601-only MPM supplies, what happens to the 8.8 µA touch-current margin? (CMP-10, PWR-74)
13. Has anyone confirmed with JLC that KB-6164 is UL-listed at 61 µm of inner copper? (PWR-06)
14. With the prototype L1, the EMI margin is inconclusive (1.57 dB). Is the prototype going to be powered from the mains before the inlet module exists? (PWR-72, ENC-31)
15. Who completes the JLC viewer checks of J1/J2/J3/J4/J7, D1–D6 and C1, given that the first upload placed five ICs wrong? (CTL-08, CTL-09, CTL-10)
16. R39 has no stock and a 22-week reel. Does hand-fitting an 0805 break the through-hole-only home-bench rule, and what accuracy does the RTD have until then? (CTL-12, CTL-13, SNS-12, SUP-01)
17. What does the RCA 12A3 coil contribute? If it will be powered, where are its measurements? (COIL-33, SNS-16)
18. The C1 sensor's response gate has 0.1 s of modelled margin on assumed roughness and tilt. What is the fallback if τ63 > 1.2 s on real pans? (SNS-18, SNS-19)
19. The bond adhesive has no published continuous rating at 260 °C, and element-parallel leakage is undetectable. What qualifies the 300 °C safety bar in production? (SNS-10, SNS-26, SNS-27)
20. Is the glass bore edge (164–210 MPa modelled vs ~110 MPa typical) acceptable without a supplier strength cert? (ENC-07)
21. R43 still models the R16/C0 cartridge, which reads close to a Breville claim. When is the enclosure updated to C1, and has counsel seen it? (SNS-38, CMP-23)
22. Why are R43 and the owned-controls programme not committed anywhere? (ENC-02, DOC-01)
23. Which tests run in PR CI, and why do max31865, tank_freq and n21_binding not? (FW-29, FW-30, DOC-11)
24. What is the end-of-line test for a production unit (coil, sensor, hipot, earth, functional), and on what fixture? (TST-18, TST-19, TST-17)
25. What is the unit cost, and what does the prototype campaign cost in total? (SUP-12, SUP-13)

## Contradiction register (claims that disagree; both sides cited)

| # | Topic | Claim A | Claim B |
|---|---|---|---|
| C1 | Rated/delivered power | 1800 W US (PSI/docs/REGULATORY_COMPLIANCE.md:65) | ~650 W pooled at 18 A (PS/DECISIONS.md:2029); median 1041 W model at 17.5 A (COIL/README.md:112) |
| C2 | Coil lug type | Insulated M4 ring terminals required on J2/J5 (PS/DECISIONS.md:245) | Non-insulated tinned M4 ring (COIL/BUILD-AND-MEASURE.md:70; COIL/ORDER-LIST.md:60) |
| C3 | Coil stud size | "Stud size is unresolved … M6 as amended" (COIL/HOT-LIMITS.md:39, reading R43/BOM.csv:72-73) | "M6" is review item M6 (PS/DECISIONS.md:242; PS/ASSEMBLY.md:39); stud is M4 (7466004R, PS/DECISIONS.md:1365) |
| C4 | MAX31865 fault cycle | AUTOMATIC (FW/components/sensors/include/max31865.h:34, 48) | Manual cycle, ≥ 5.5 ms steps (CJ/DECISIONS.md:544-545, C37) |
| C5 | MAX31865 thresholds | 1526 / 45722 (FW/config.yaml:131, 139) | 35544 / 12844, and "firmware agrees" (CJ/DECISIONS.md:669-685, C46) |
| C6 | Tank release ceiling | 17.5 A (PS/DECISIONS.md:2193; Kconfig:39) | 18.0 A (PS/OPEN-ITEMS.md:25, 105, 112) |
| C7 | Board of record | s51 (PS/OPEN-ITEMS.md:3) | s53 (PS/DECISIONS.md:2972; NAT/fab/FAB-NOTE.md:3) |
| C8 | Laminate | KB-6164 settled, hard order condition (NAT/fab/FAB-NOTE.md; PS/FAB-JLCPCB.md:20-26) | UL row stops at 35 µm inner Cu, board has 61 µm (PS/OPEN-ITEMS.md:42; OI/JLC-LAMINATE-QUESTION.md) |
| C9 | BR1 gap pad | 0.5 mm / 0.020" (PS/DECISIONS.md:275, 301) | 1.0 mm / 0.040" (PS/DECISIONS.md:421, 476; SINK-DRAWING-NOTES.md:34) |
| C10 | Clamp force | 60–80 N/device (PS/DECISIONS.md:276) | ≥ 60 N target 80 (OI/m11/RECOMMENDATION.md:235); acceptance 45–102 N (PS/DECISIONS.md:474) |
| C11 | FET soldering | Seat-before-solder fixture, coplanar 0.05 mm (PS/DECISIONS.md:473) | JLC hand-solders on lead shoulders (NAT/fab/FAB-NOTE.md remarks) |
| C12 | PS3 part | MPM-65-15ST (PS/DECISIONS.md:1504; FW/README.md:79) | IRM-60-15ST (R43/BOM.csv:206; CJ/README.md:135) |
| C13 | J13 merge status | Landed on controller-j13-merge (PS/DECISIONS.md:3049-3050) | "Not done on any controller branch" (NAT/PROTOTYPE-LOT.md:156-158) |
| C14 | Watchdog timeout | 1.6 s (FW/README.md:327); 0.9–1.6 s (COMMISSIONING.md step 1) | 0.9–2.5 s (CJ/DECISIONS.md:600, C42) |
| C15 | CI IDF build | "The CI IDF build is the proof" (PS/DECISIONS.md:3051) | IDF build runs only on a published release (.github/workflows/release-artifacts.yml:3-5) |
| C16 | IDF compile status | "Never compiled against ESP-IDF" (FW/components/power/Kconfig:7-8) | Compiled with HW_BINDING=y (FW/build-evidence/esp-idf/README.md:12-28) |
| C17 | Ledger counts | 2/28/62 (committed ledger README:30) | 3/92/0/0 (working tree); 3/32/58 (OPEN-ITEMS:47); 3/91/0 (OPEN-ITEMS:30) |
| C18 | J4 Molex drawing | "Still unread" (CJ/ORDER.md:108) | "Owner-supplied 2026-10-12, not committed" (CJ/LAYOUT.md:245-254) |
| C19 | J4 mating side | +X (CJ/ENCLOSURE-HANDOFF.md:27) | −X (CJ/LAYOUT.md:227) |
| C20 | R39 CPL rotation | 180 (CJ/ORDER.md:85) | 0 (CJ/fab/cpl-jlcpcb.csv) |
| C21 | UI controls | APEM IPR3PAD2 + Grayhill encoder (R43/BOM.csv:114-117); "encoder and buzzer not chosen" (CJ/DECISIONS.md:433) | Tact switches + TMAG5170 knob + GSD9605YB buzzer (UIB/README.md:3-7) |
| C22 | Expander GP3–GP5 | Encoder A/B/switch (FW/main/platform/ui_board_map.h:32-34) | Sensor CS / ALERT / spare (UIB/README.md:65) |
| C23 | Rim cross-check threshold | 15 K (SR3/HANDOFF.md:339-340) | 25 K (SR3/pcb/DECISIONS.md:170-171; firmware/DECISIONS.md:136 {OM}) |
| C24 | Rim ADC | ADS1115 (SR3/HANDOFF.md:230-232) | GPIO9, ADS1115 rejected (SR3/pcb/DECISIONS.md:150-162) |
| C25 | CR-5 resistor | Lower to 76.8 k, ≤ 244.5 °C (firmware/DECISIONS.md:1270-1276 {OM}) | Unchanged 86.6 k, ≤ 252 °C (D-BARRIER, firmware/DECISIONS.md:2361 {OM}) |
| C26 | Native-21 mounting holes | H1, H3–H8 used; H2/H9/H10 empty (PS/DECISIONS.md:3013-3020) | Nylon H2–H7, metal H1 (NAT/PROTOTYPE-LOT.md "Fixings"; R43 r32 BENCH-PLAN.md:19) |
| C27 | Inlet fuse | "No inlet fuse" (R43/design/r32/CERTIFICATION-QUESTIONS.md:10) | "30 A inlet fuse" (same file :40) |
| C28 | Coil spec stale note | Rows 1–7 "stale … 88 µH" (SPEC line 59) | Rows 1 and 7 updated to 70/80 µH and 76 A (SPEC lines 36, 43) |
| C29 | Coil README on spec | "This branch's committed copy is the stale 88 µH version" (COIL/README.md:253) | Spec committed on PSI with the coil corrections (dd8e7962d, 93b9ea185) |
| C30 | J1 temperature | 104.6 °C (PS/OPEN-ITEMS.md:30) | 103.1 °C (review packet); 76.2–98.8 °C (CAND/c54-j1-thermal) |
| C31 | Power-stage README | UCC21550, ISO7710, PS1, MDA-25-R, CT 1:100, 39 kΩ, 0.54 µF, 240 × 160 mm (PS/README.md) | 2EDR8259X, CA-IS3720HW, PS1 deleted, KLDR025.TXP, 1:200, 49.9 kΩ, 0.50 µF, 290 × 190 mm (DECISIONS and BOM) |
| C32 | Sink cut-off | ≈ 120 °C G4A (PS/README.md:134) | Hardware 98.3–104.6 °C, firmware 95 °C (thermal_mgmt.h:152-159); bench TCO Tf 110 °C |
| C33 | Firmware state count | 8 states (FW/README.md:9-20) | 9 states (FW/main/state_machine.h:30-39) |
| C34 | Plan 09 | "Not started" (00-MASTER-PLAN.md:239) | pass: true (enclosure-fit/plan-result.json) |
| C35 | Aux allowance at mid blower | 0.60 A (PS/OPEN-ITEMS.md:64) | 0.65 A (FW/README.md:78-86), research-pass reading, verify |

## Gaps I could not assess

- **Line numbers I did not re-open myself.** Most power, controller, sensor, enclosure, firmware and compliance line numbers came from the read-only research passes. I re-checked a sample (method note at the top) and found no error, but the rest are "where to look".
- **No builds, tests or CAD checks were re-run.** Every "passes" is the committed log or file. A deleted or stale log would not be caught.
- **The RCA 12A3 coil.** Its location, geometry and intended use are not in the repo beyond "teardown outstanding" and "not measured".
- **First heating without the C1 sensor.** Whether it is allowed (with a thermocouple or stand-in RTD) is not stated anywhere I read.
- **The datasheet ledger's 95 entries were not audited line by line.** Only the summary counts and the cited gap findings were read.
- **R43 internal CAD checks, the R43 BOM's 218 rows and the full SPEC rows 1–16 were sampled, not read in full.**
- **Origin/main's newer SR3 content** (leak-barrier/, robustness/, firmware/) was read through the research pass only.
- **Prices, stock and lead times** are as dated in the repo. None was refreshed, because web search was not used.
- **Standards text.** No UL or IEC clause text is in the repo. Whether a residual-heat indicator, hardware STOP or bilingual labels are required could not be checked.
- **Legal.** The patent rows report the repo's own claim chart. They are not legal advice, and FTO was not assessed.
- **Coil-review 2026-10-10 and temper-coil-driver-r1** are untracked in MAIN. Their contents were not checked beyond their READMEs.
- **The claude.ai enclosure cost artifact** (ENC-34) was not opened.
