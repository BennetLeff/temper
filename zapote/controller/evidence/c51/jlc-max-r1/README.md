# jlc-max-r1: let JLC build the whole C51 controller (R39 Rref, BOM scan, plug-in items)

Scope study, 2026-11-25 (US Central); JLC reads 2026-11-26 04:13–04:31Z. Board: C51 circuit on `controller-c51`
(`frozen/default.csv`, 97 lines; no layout yet). Owner direction: JLC solders and builds as much as possible,
near-zero hand-soldering on the owner's bench. **Nothing was ordered, carted, logged into, contacted or pushed;
no build was run.** Lot sizes 5 / 10 / 20 boards; the project rule is JLC stock ≥ 2 × the need.

## Bottom line

1. **R39 → RESI PTFR0805B430RN9, LCSC C351565: 430 Ω, 0805, ±0.1 %, ±10 ppm/K, JLC stock 48,662** (detail read
   04:20:42Z). It is the only JLC-stocked part in the window "400 / 402 / 430 Ω, ≤ 0.1 %, ≤ 10 ppm/K" with an 0805
   land and enough stock (341 searches, 9,914 distinct JLC parts, 338 in the window, 4 with any stock). Same value
   and footprint: **no firmware change, no threshold-word change, no copper change, and the hardware runaway band
   stays inside its gate** (298.7–322.4 °C against 299.2–321.9 °C today; gate > 270, < 325).
   **Cost: it does not pass CR-2 gate 1b as written.** With ±10 ppm/K over the gate's 60 K board swing, the
   board-controlled terms are 0.418 K and the RSS 0.408 K at 250 °C, against 0.30 K for both (RG2012V: 0.257 / 0.298).
   The Rref tempco term doubles, from 0.161 K to 0.322 K. The part passes 1b only if the board stays within 31 K
   of the calibration temperature, and the C51 bay design air is 61 °C (DECISIONS C51), i.e. ≥ 36 K above a 25 °C
   calibration. So the 10 ppm bound the owner set and the CR-2 ±0.3 K requirement disagree; one of them has to
   move (owner decision, record in DECISIONS). No ≤ 5 ppm/K part in this window has JLC stock (201 of the 338 are
   ≤ 5 ppm, all at 0).
2. **400 / 402 Ω gives nothing and breaks a safety trip.** The only stocked 402 Ω ≤ 10 ppm parts are an 0402
   (C2692962, 3,257) and an 0805 with 2 in stock (C4093972). Accuracy is no better (1b 0.415 K), and the
   hardware runaway trip, which compares the RTD voltage with a BIAS divider (R > k (Rref + R_F+) / (1 − k)),
   moves down with Rref: **260.4–282.4 °C, below the 270 °C gate floor and below firmware's 300 °C runaway.**
   A value change means re-deriving the runaway divider, the window comparators and the firmware constants.
   Pt100 range is not the problem: R(320 °C)/Rref is 0.547 at 402 Ω (0.511 at 430 Ω), limit 0.95.
3. **Other C51 lines that are not cleanly JLC today:** C1/C9 electrolytic (0 stock), R47 61.9 k (2), U11/U25/U33/U37
   SN74LVC1G08DBVR (36 against 40 for 5 boards), U14 AD8436 (28, short at 20 boards), and four Extended lines whose
   stock fell by more than half since 2026-10-18 and now sit under 10 × the 20-board need: R23/R36/R152 140 k (454),
   R31 8.06 k (96), R32 34.8 k (67), U15 MCP3202 (47). Each has a same-rating JLC-stocked substitute or a
   pre-order route (table below). Every part C51 added has ≥ 2 × the 20-board need.
4. **After these swaps the owner solders nothing on the controller.** The 11 THT connector placements (J1 J2 J3
   J4 J7 J9 J10 J12 J13 J14 J15) are JLC lines that JLC hand-solders (`assemblyMode = manualWeld`). J11 is a
   copper-only TC2050 land. The U.FL coax and antenna are plug-in items (no solder), outside JLC PCBA.

## 1. R39 (pan MAX31865 Rref)

Requirement: 430 Ω (or a value the circuit can take), ≤ 0.1 %, TCR ≤ 10 ppm/K (owner), 0805 preferred.
The circuit (`elec/src/rtd_c1_block.ato:82-85`, 4-wire, datasheet Figure 4) is a Pt100 at about 3.8 mA;
Rref dissipates 6.7 mW at VBIAS 2.06 V and −20 °C.

### Candidates (JLC, live)

| Part | LCSC | Pkg | Tol / TCR (JLC attribute) | JLC stock (read, UTC) | Covers 2× at 5/10/20 | Footprint / firmware consequence | Verdict |
|---|---|---|---|---|---|---|---|
| Susumu RG2012V-431-W-T1 (fitted) | C4260028 | 0805 | 0.05 % / 5 | 0 (04:13:05Z; 0 also 10-18 and 11-25) | no | — | not buyable at JLC |
| **RESI PTFR0805B430RN9** | **C351565** | 0805 | 0.1 % / 10 | **48,662** (04:20:42Z) | yes | none: same value, same R_0805 land | **JLC places it** (subject to the CR-2 decision) |
| RESI PTFR0603B430RN9 | C2692824 | 0603 | 0.1 % / 10 | 2,141 (04:20:43Z) | yes | land R_0805 → R_0603 (C51 not laid out yet, so no copper cost), but `board_derivations.yaml:102,123` keys on the 0805 footprint | 0805 is equal and needs nothing |
| RESI PTFR0402B402RN9 | C2692962 | 0402 | 0.1 % / 10 | 3,257 | yes | value + 0402 land; runaway trip and firmware re-derived (§1.3) | reject |
| TE RN73C2A402RBTDF | C4093972 | 0805 | 0.1 % / 10 | 2 | no | value change | reject |
| Yageo RT0805BRD07430RL (C35 swap) | C865488 | 0805 | 0.1 % / 25 | 3,826 | yes | none | outside owner's bound; C37 already rejected it |

TCR check against the maker: RESI's PTFR datasheet (sha256 `ce6a100a…`, `reads/datasheets.json`) gives the
ordering code PTFR | size | tolerance B = ±0.1 % | value | TCR **N = ±10 ppm/°C** (V = ±5) | 9 = standard, and lists
±5/±10/±25 ppm for 0805 100 Ω–10.2 kΩ; load life 2000 h at 70 °C typ < 0.01 %, max < 0.1 %; AEC-Q200. JLC lists
−55…+125 °C, the datasheet −55…+155 °C; the board runs ≤ 85 °C either way. The PTFR 5 ppm / 0.05 % variants
(PTFR0805A430RV9 etc.) have no JLC listing (searched, 0 hits). Closest stocked 25 ppm 0805s, for the record:
ERA6AEB431V C473279 (11,619), RT0805BRD07430RL C865488 (3,826), ARG05BTC4300N C2828743 (861).

### 1.2 Accuracy budget (CR-2) and trips: `r39_budget.py` → `r39-budget.json`

The committed sensor-r3 checks (`../../sensor-r3-checks/checks.py`, run on the as-built netlist exactly as
`run_as_built.py` does) with only R39 changed. The RG2012V row reproduces the committed `checks-as-built.json`
(0.257 / 0.298 K, band 299.2–321.9 °C) and `controller_calcs.json` threshold words.

| R39 | 1b board terms (gate ≤ 0.30 K) | 1b RSS (≤ 0.30 K) | Rref tempco at 250 / 100 °C | 1b passes up to board ΔT | Runaway band (gate 270–325 °C) | High / low words | No gain cal: tol at 250 °C |
|---|---|---|---|---|---|---|---|
| RG2012V 0.05 % / 5 | 0.257 PASS | 0.298 PASS | 0.161 / 0.110 K | 60 K | 299.2–321.9 PASS | 35544 / 12844 | 0.268 K |
| **PTFR0805B430RN9 0.1 % / 10** | **0.418 FAIL** | **0.408 FAIL** | 0.322 / 0.219 K | **31 K** | 298.7–322.4 PASS | 35544 / 12844 | 0.536 K |
| RT0805BRD 0.1 % / 25 | 0.901 FAIL | 0.842 FAIL | 0.804 / 0.548 K | 12 K | 298.2–323.0 PASS | 35544 / 12844 | 0.536 K |
| 402 Ω 0.1 % / 10 | 0.415 FAIL | 0.398 FAIL | 0.322 / 0.219 K | 35 K | **260.4–282.4 FAIL** | 38018 / 13740 | 0.536 K |

- Gate 1b assumes a single-point gain calibration at R(200 °C) with the board at 25 °C and a board range of
  0–85 °C (|ΔT| 60 K). After that calibration the tolerance cancels; the TCR does not.
- **Firmware has no gain calibration today:** `rtd_convert.c:16` and `max31865.h:70` divide by a fixed 430.0
  (fw-unified `fbd6f5ca9`). Until the CR-2 calibration exists, tolerance adds directly: 0.27 K at 250 °C for
  0.05 %, 0.54 K for 0.1 %. That gap exists with either part; the calibration is a firmware item either way.
- Levers that keep the PTFR inside 1b without a new part: calibrate with the board warm (only helps if the board's
  real range is narrower than 0–85 °C), or re-state 1b. Both are owner calls on a requirement, not part choices.

### 1.3 What a value change (400 / 402 Ω) would touch

Firmware (fw-unified `fbd6f5ca9`): `components/sensors/include/max31865.h:70` (`MAX31865_RREF_OHM 430.0f`),
`components/sensors/rtd_convert.c:16`, `tools/board_derivations.yaml:103,124` (`value: 430ohm`),
`config.yaml:131,139` (words 12844 / 35544 → 13740 / 38018 at 402 Ω), `config.h:96-97` doc strings, and the tests
that hard-code 430 (`test/test_common.h:270`, `test/test_c1_units.c:210`, `tools/test_board_derivation_lib.py`).
Hardware: the runaway divider `r_runaway_top/bot` (`controller.ato` ≈ 800) and the window dividers
(`rtd_c1_block.ato:280-291`); calcs `controller_calcs.py:231,238` hard-code 430 Ω and 5 ppm.

### 1.4 What the 430 Ω PTFR swap touches (no constant changes)

- Controller: override the MPN in `controller.ato` (C35 pattern, as at `controller.ato:569-571`; `rtd_c1_block.ato`
  must stay equal to the RTD source plus listed edits, `port_rtd_c1.py --check`), tolerance to 0.1 %;
  `evidence/sensor-r3-checks/run_as_built.py:25` `RREF_TC` needs `"PTFR0805B430RN9": 10e-6` (it raises KeyError
  otherwise); `controller_calcs.py:218,231` (runaway corners use 0.05 % + 5 ppm); land-pattern gate needs JLC
  pads for C351565 (`tools/check_land_patterns.py`); ORDER.md §2 and DECISIONS (C37 / C51 R39 bullet).
- Firmware: none in code. Comments name the old part: `max31865.h:65`, `rtd_convert.h:37`.

## 2. C51 BOM against live JLC stock: `bom_scan.py` → `bom-scan.json`

97 lines (96 with an LCSC code; J11 is a copper land). 90 Extended, 6 Basic; 8 lines (11 placements) are THT
that JLC hand-solders. Stock read 04:13–04:31Z; "was" = `evidence/order/stock-read-2026-10-18.json`.

| Line (refs, per board) | Current part / LCSC | Issue | Live stock (was) | Need 2× at 5 / 10 / 20 | Candidate | Candidate stock (read) | Ratings vs requirement | Margin effect | Consequence | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| R39 (1) | RG2012V-431-W-T1 C4260028 | 0 | 0 (0) | 10 / 20 / 40 | PTFR0805B430RN9 **C351565** | 48,662 (04:20:42Z) | 430 Ω 0.1 % 10 ppm vs 0.05 % 5 ppm | CR-2 1b 0.418 K vs 0.30 K gate (§1.2) | §1.4 | **JLC, after the owner settles CR-2 vs the 10 ppm bound**; else consign RG2012V (no source found) |
| C1, C9 (2) | Panasonic EEE-FK1E101P C178539 | 0 | 0 (663) | 20 / 40 / 80 | Nichicon UCD1E101MCL6GS **C445471**; Panasonic EEE-FK1E101AL C1881543 | 772 (04:28:06Z); 97 (04:28:05Z) | 100 µF ±20 % 25 V, D8 × L6.2, 105 °C 2000 h, ESR 260 mΩ (JLC attributes; datasheets not read) | none modelled: calcs use 100 µF −20 % only (`controller_calcs.py:580`, `ps3_loss_sim.py:98`); harness damping is not modelled with any part | `Cap100u25Elec` mpn (`controller_parts.ato:118`), `verify_controller.py:1026` keys on the MPN; land gate; polarity in the JLC preview | **Swap to C445471** (FK-AL covers 20 boards only just) |
| R47 (1) | ERA-3AEB6192V C4019122 | 2 left | 2 (181) | 10 / 20 / 40 | Yageo RT0603BRD0761K9L **C861498** | 5,464 (04:30:46Z) | 61.9 k 0.1 % 25 ppm 0603, identical | none (window arithmetic uses 0.1 % + 25 ppm; `verify_controller.py:889` knows RT0603BRD) | override in `controller.ato` (C35 pattern; library stays byte-identical) | **Swap** |
| U11 U25 U33 U37 (4) | TI SN74LVC1G08DBVR C7666 | 36 < 40 | 36 (69,364) | 40 / 80 / 160 | TI SN74LVC1G08QDBVRQ1 **C840098** | 7,990 (04:30:47Z) | same DBV pin-out; tpd max 4.5 ns at 3.3 V ± 0.3 V, −40…85 °C (SCES556H 5.7), the 4.5 ns `controller_calcs.py:928` uses | none: capmode slack stays 189.9 ns | overrides per instance; `verify_controller.py:110,424` match the MPN string; land gate | **Swap** (the other JLC listings under the TI number are other makers' copies: not counted) |
| U14 (1) | AD8436ARQZ-R7 C495329 | short at 20 | 28 (65) | 10 / 20 / 40 | same part: JLC pre-order now (5 or 10 boards), Global Sourcing for 20 | — | same | none | none | **Pre-order**; production direction (C35) deletes U14 |
| U15 (1) | MCP3202-CI/SN C56997 | falling | 47 (736) | 10 / 20 / 40 | same part, pre-order | — | same | none | none | **Pre-order on order day** |
| R23 R36 R152 (3) | RT0603BRD07140KL C861125 | falling | 454 (7,880) | 30 / 60 / 120 | Panasonic ERA-3AEB1403V C4020746 or Vishay TNPW0603140KBEEA C2075683 | 4,352 / 4,908 (04:30Z) | 140 k 0.1 % 25 ppm 0603, identical | none | override MPN | covers 20 boards today; **swap only if < 120 at order** |
| R31 (1) | RT0603BRD078K06L C861587 | falling | 96 (2,636) | 10 / 20 / 40 | Vishay TNPW06038K06BEEA C2075702 | 285 | 8.06 k 0.1 % 25 ppm, identical | none | override MPN | keep; swap if < 40 at order |
| R32 (1) | RC0603FR-0734K8L C137741 | falling | 67 (7,394) | 10 / 20 / 40 | Yageo AF0603FR-0734K8L C2098331; Vishay CRCW060334K8FKEA C844554 | 31,248 / 50,780 | 34.8 k 1 % 100 ppm, identical | none | override MPN | **Swap** (deep stock, same family) |
| U3 (1) | TPS3703A4330DSERQ1 C1850327 | thin, only listing | 56 (16) | 10 / 20 / 40 | same part, pre-order | — | — | — | — | **Pre-order on order day** |
| J4 (1) | Molex 43045-1600 C277731 (JLC model "430451600") | THT | 900 (709) | 10 / 20 / 40 | — (searches "430451600", "43045-1600", "0430451600" all return only C277731) | — | — | — | — | JLC hand-solders |
| R130 (1, C51) | RT0805BRD074K3L C728653 | watch | 2,404 (4,813 at 2026-11-25 14:54Z) | 10 / 20 / 40 | — | — | — | — | — | fine; re-read at order |
| J1 J2 J3 J9 J10 J12 J13 J14 J15 J7 | JST XH / PH / VH | THT | ≥ 5,734 | — | — | — | — | — | — | JLC hand-solders |
| J11 | TC2050 land | no part | — | — | — | — | — | — | — | copper only (C41) |

**Parts new in C51** (designators not on the C49 frozen BOM at `cb7ac6435`; `c51_new_refs` in `bom-scan.json`):
all have ≥ 2 × the 20-board need. BAV199-7-F C155248 11,177 (D10–D13, need 160); EMC2301-1-ACZL-TR C148036 1,959;
BSS138LT1G C82045 300,950; B4B-XH-A C144395 491,880 (J9); B2B-PH-K-S C131337 337,301 (J14); B5B-XH-A C157991
57,437 (J15); MAX31865AAP+T C779509 2,132 (U30, U50; need 80); TPS62933DRLR C3200405 36,772 (U51);
RT0603BRD0747KL C326725 15,023; RT0805BRD074K3L C728653 2,404 (above); the rest are existing passives.
No C51 part is trending down to the 2× line.

## 3. Plug-in and non-BOM items

| Item | Status | Can JLC supply / fit it? | Route |
|---|---|---|---|
| U.FL coax (150 mm, 1.13 mm) + 2450AT18A100 chip-antenna board (DECISIONS C26) | No antenna-board design in this repo; JLC has no listing for 2450AT18A100 (search, 0 hits) | Not in PCBA: it has no land or CPL row, and JLC does not ship unassembled parts with PCBs (power study's policy read) | Owner snaps it on (no solder). A single COTS part replaces coax + board: e.g. Kinghelm KH-FPC2.4G-1.13IPEX-240 C4943394 (2.45 GHz FPC, 1.13 mm coax, IPEX, 90 in stock) or HJ-2.4G-IPEX1-L=80mm C1693673 (373). That is an enclosure / RF choice (R33 chose the chip-antenna board): **defer to the enclosure line**; confirm the IPEX generation is MHF I (U.FL) |
| TC2050-IDC-NL cable | programming tool | n/a | owner's bench tool |
| Harness mates (XH / PH / VH housings, Micro-Fit plug) | harness, not board | n/a | harness BOM |

## Change now vs defer (controller)

Change now (BOM-only, no copper, no margin loss): C1/C9 → C445471; R47 → C861498; U11/U25/U33/U37 →
C840098; R32 → C2098331. Owner decision first, then change: R39 → C351565 (CR-2 1b vs the 10 ppm bound).
On the order day: pre-order U3, U14, U15; re-read stock, and swap the 140 k / 8.06 k if they are under 2× at the
lot size. Defer: antenna COTS vs chip-antenna board (enclosure).

## Re-run

- `python3 -I jlc_fetch.py search "<kw>" | detail Cxxx` (online; cached in `reads/*.json.gz` with fetch time,
  request and the full response's sha256; search pages keep only the fields the scripts read; `--refresh` re-reads).
- `python3 -I r39_candidates.py` → `r39-candidates.json` (offline, from the cached searches).
- `python3 r39_budget.py` → `r39-budget.json` (offline; imports `sensor-r3-checks/checks.py` and `controller_calcs.py`).
- `python3 -I bom_scan.py` → `bom-scan.json` (offline from the cache; needs `git` for the C49 BOM).
- Datasheets read (not committed, sha256 in `reads/datasheets.json`): RESI PTFR (V8), TI SCES556H.
