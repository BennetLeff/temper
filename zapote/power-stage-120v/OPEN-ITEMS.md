# native-21 open items (register, updated 2026-10-15)

One row per open item on the power board, so nothing falls between lanes. Board of record: **s41** (board d4b2445c,
4 layers; DECISIONS 53, on s40 of DECISIONS 52). Keep this current: when an item closes, give the DECISIONS number
and move it to "Closed" at the end. Agents marked "running" write to scratch; the integration session reviews and
commits their results.

Lanes:
- **Layout lanes** are one-writer worktrees, one per isolation island (13-coupling), merged one at a time through the
  scorecard. At most 2–3 run at once.
- **Analysis lanes** build nothing and run in parallel.

Scorecard (DECISIONS 43, 45, 46): compare against `10-benchmark/scorecard-native21s41.json`. The release gates
(`RELEASE_GATES`: `b3_ratings`) and the leakage limit are absolute conditions for an order. A candidate is graded on
their ratchets.

## 1. Correctness and safety (ranked first)

| # | Item | Evidence | Lane / owner | Status | Next |
|---|---|---|---|---|---|
| S2 | **Board temperatures vs ratings (s41, still air, bay 55 °C, DECISIONS 53):** 22 A: laminate **+1.2 K (passes)**, C40 film −2.7 K; 28 A: laminate −25.1 K, films −15 to −25 K, R5 element −0.3 K. **1206 gate resistors fail derating at every ceiling** (−39.6 K). Still-air ceiling: laminate 22.3 A, + film 21.1 A. 28 A in still air is not reachable by layout on 2 oz (JLC has no 3 oz multilayer) | DECISIONS 46, 51, 53; `b3-ratings/`, `c36-tank-copper/` | Candidate 39 (gate R → 2512); enclosure airflow reply (only route to 28 A); C40 at 22 A | Open | After 39: re-run targets at bay 61 °C on s41; set the release ceiling. **Line-current basis:** the cases use I_line 11.1 A, but the firmware bound is 13.5 A (I_ps·1.10 + I_aux). At 13.5 A gated rows move ≤ 0.1 K, C40 / ceiling unchanged, C38 c22 +0.1 → −0.0 K, L1 −12 K (adv, +25 K left) (`b3-ratings/line-hold-2026-10-15/`). After 39 merges: move run_basis / fet_case / run_study to I_line 13.5 A. **Product consequence** (temper-8d nameplate-r1, `sensor-c1-impulse-mining:output/temper-nameplate-r1/`, cross-checked against the round-6 ngspice grid, 931 vs 904 W at 22 A): pooled pan power is 650 / 856 / 931 W at an 18 / 21 / 22 A ceiling (0.42–0.61× the Control Freak), whatever the nameplate. Only board-face airflow (the 24–28 A route) moves it. Firmware `tank_limit_a` is still 22 A: set it to the computed release ceiling after 39 |
| S15 | **UL 858 25.3.1 (safe with the solid-state control dead or stuck):** on this board, the firmware-independent trips (R5 Kelvin OCP, U7 OVP 280 V, bias-rail heartbeat → BIAS_GOOD, BUS_FAULT → controller interlock → DIS) all act on faults. A stage stuck on at normal current trips none of them. The only firmware-independent cut for that case is the TCO loop (J3): opening it removes PS2, and with it all gate drive, HOT5 and OCP_OK (DECISIONS 2026-10-06). The TCO rating and mounting are still provisional, set from measured glass and sink temperatures (README; electrical review P1) | temper-8d round 3; FAULT-INTERFACE; DECISIONS 2026-10-06 | Owner / enclosure (TCO rating, mounting); controller (whether PERMIT needs an MCU watchdog) | Open | Choose the TCO and its location so that it opens before the pan or glass is damaged with the stage stuck on at the ceiling; certifier confirms that the TCO counts as the 25.3.1 backstop |
| S14 | **IPW65R018CFD7 body-diode limits broken in S4:** dv/dt 85.8 V/ns (70 rated) and diF/dt 2,101 A/µs (1,300 rated) on the vendor model; at typical Qrr 109–112 V/ns and die VDS 620 V. S4 is a burst design case (370–740 edges per leg before the software latch) | DECISIONS 49, 54; gate-network study | Candidate 39 layout lane (R_on 68 Ω 2512 + Cgs 4.7 nF; ps-layers, stage tag s42) | Running | Max-Qrr basis open: D-8 bench (R_on 39 / 68 / 100 Ω × Cgs 1 / 4.7 nF, repeated S4 edges); controller: hardware capacitive-mode detector |
| S1 | Touch leakage: was 0.974 mA. **Built in s38 (DECISIONS 50):** 0.2412 mA DESIGN (budget 0.25, margin 8.8 µA) with the off-board D-22 module Y removed + SCF31X choke and PS3 → MPM-65-15ST; s19b EMI 12.37 / 8.19 dB | `c23-supply-topology/README.md`; co-design study | Controller (J13 merge, PS3); D-22 module (`c23-supply-topology/MODULE-REQUEST.md`); certifier (MPM approvals: IEC 60601-1 / 60335-1, no UL file) | Passes on the model | Bench: measured supply leakage, SCF31X DM leakage, HF touch with the lab's meter network. Robust variant (L1 → SCF31X) needs an L1-slot re-layout |
| S12 | Laminate UL scope: KB-6164 (35 µm) and KB-6165 (54 µm) multilayer rows don't cover 61 µm (2 oz) inner copper; KB-6164F / 6165F / 6167F list 102 µm, and JLC's "TG155" option links KB-6165F. Item 41 named KB-6164 for CTI; `stackup.json` still says Nan Ya NP-155F | DECISIONS 41, 51 | Owner → JLC (UL Product iQ needs a login) | Open | Which recognised JLC-4 construction covers 4 L, 2 oz inner, CTI ≥ 175 V; then fix the order remark and stackup.json together |
| S3 | F6's 252/252 result rests on round-17 loop matrices from board 76ec8cca, not s35 | `c33-six-layer/adoption/README.md` | FEM (remote box) | Blocked: box offline | Owner restarts the box; run `adoption/fem/chain_c33.sh` for s35 |
| S8 | C5 / C6 ripple at 28 A: on the vendor basis the fitted part carries 28 A only at cap ambient ≤ 80 °C; no stocked part fixes 28 A at 85 °C. 28 % of the HF ripple power is above TDK's 95 kHz chart edge | DECISIONS 45 | Parts | Verdict recorded | B32676G1106K once "Z 1" = catalogue part is confirmed (owner or distributor); bench C5 case temperature |
| S9 | Resonant bank 1.045× TDK's curve at 28 A; no ≤ 0.85 option in authorised stock | DECISIONS 37, 45 | Candidate 34 | Waits on stock | Moot below 28 A while S2 limits the ceiling |
| S6 | CMTI 1.5× rule not met on FILTERED / OPEN rows (1.05×) | `c31-bom/README.md` | Parts / certifier | Open | Covered by the isolator review; NSi822xW rejected (no open-input state) |
| S7 | Datasheet ledger: 3 VERIFIED / 29 PARTIAL / 1 VIOLATION / 59 UNAUDITED (SIGNAL) of 92 lines | `datasheet-ledger/` | Parts verification: two analysis batches (A: 14 lines, B: 13 lines; the CFD7 goes with candidate 39) | Running | Merge their proposed entries; then the SIGNAL lines |
| S10 | Return-path open changes: 18 → 15 (s40, DECISIONS 52). The 14 left outside HS-B / LS are on SELV / Kelvin nets (bus_fault_hot ×3, ocp_ok_hot, ovp_ok_hot ×2, permit ×3, bus_fault_iso, bus_fault, bias_good ×3); 1 is the GOOD node at U45.1 | DECISIONS 39–40, 52 | Layout (SELV side) | Open | A SELV-side return-path pass |
| S11 | Certifier questions (CERTIFIER-PACKET A1–A4: F1, insulation, PEC / FMEA, supply approvals, RES_A, coil-lane voltage); add S12 to A3 | `owner-items/CERTIFIER-PACKET.md` | Owner | Draft, not sent | Owner sends the packet |
| S13 | temper-8d requests: AMC1301 measured input current on R5 (HOT5 domain; J4 +2 pins; +7–9 % power at the 15 A plug); pan-detect re-validation on the full bridge (Al / Cu / small / warped pans); ±1 kHz dither at 120 Hz (check ZVS at fs − 1 kHz). Split-R coil EMI model: right physics, no verdict change (DECISIONS 47) | `git show sensor-c1-impulse-mining:output/temper-coil-driver-r1/RECOMMENDATIONS.md` | AMC1301: a later candidate (kept out of 23 to hold its scope; its power argument is capped by S2); firmware items to the controller | Logged | After S2 |

## 2. Buildability (JLC fab and assembly)

| # | Item | Evidence | Lane / owner | Status | Next |
|---|---|---|---|---|---|
| B1 | **L1 B82726S2203A020 sets the build date:** no authorised stock, 29-week lead, so a 500-board build lands ~2027-05 if ordered now. 14 lines short for 500 boards, 3 for 5; JLC-assemblable share 0.851 / 0.968 | DECISIONS 45; `sourcing/study-2026-10-15/` | Owner (ordering); EMI re-run for L1 alternate B82726S2243A020 | Plan ready | Owner pre-orders (README §4). L1 alternate: c29 / D-22 EMI re-run with 0.75 mH / 8 µH |
| B2 | Five "short" lines are read gaps (DigiKey bot check, Octopart 403), not proven shortages | DECISIONS 45 | Sourcing | Open | Re-take the snapshot when the sites read again |
| B4 | Order remarks: KB-6164 with KB-6064 prepreg (S12 may change this), stack JLC041622-7628 named, Confirm production file. Thickness remark dropped (DECISIONS 44) | FAB-NOTE | Order (owner) | Ready | Answered at JLC's file review |
| B5 | Track-geometry hygiene: 104 right angles, 206 acute corners (44 fold-backs), 704 mm any-angle on s35 | DECISIONS 43, 48 | Cleanup pass (tool merged) | Proved on s35 as s37 (ACCEPT) | Apply last, on the merged copper, then the chain |
| B6 | Stencil: J2 / J5 want 150 µm paste; fine-pitch parts' stencil not chosen; J2 / J5 CPL rows NEEDS-PREVIEW | DECISIONS 44 | Order (owner) | Open | Step stencil or aperture choice at order |
| B7 | `PROTOTYPE-LOT.md` lists superseded parts (UCC21550, ISO7710, 74650074R) | `08-manufacturing-package/native-21/` | Integration | Stale | Regenerate from the snapshot when the BOM settles |
| B10 | **Validation cases from temper-8d mining round 3** (`sensor-c1-impulse-mining:output/temper-mining-r3/`): UL 858 59.6 iron bar (2 × 100 × 20 mm, ≤ 35 °C rise at the highest setting) plus fork / spoon / knife on pan detection; 47.8 off within 30 s of vessel removal, manual reset; bad-pan set (multi-ply Al with a thin stainless base, Demeyere ControlInduc cold → 250 °C, Demeyere Proline) at full power, showing pll_control stays stable and the hardware OCP (R5 Kelvin) / OVP (U7, 280 V) / tank-CT trips act before any device is overstressed (ties to S14's capacitive-mode case) | temper-8d round 3 | Bring-up / test plan (owner, controller) | New | Add to the bench plan beside D-8 |
| B11 | **Aux inlet allowance (temper-8d, applied):** `blower_aux.c` base_a 1.3 → 0.26 A (PS1 gone), ps3_eta 0.875, ps3_pf 0.67. The allowance at 108 V goes from 1.35 / 1.93 / 2.57 to 0.31 / 0.60 / 0.887 A (blower off / mid / full), and the full-blower hold from 9.94 to 11.47 A. The board is covered: B3 at 13.5 A line current, `line-hold-2026-10-15/`. The constants stay PROVISIONAL until the true-RMS bench check (`output/temper-aux-load-r1/BENCH-RMS.md`: blower states × 108 / 120 / 132 V; CH2 = the J1 line conductor with the J3 and J11 leads passed through backwards) | `output/temper-aux-load-r1/` (aux_load.py reruns byte-identical) | Bring-up (owner) | Applied, bench open | Run BENCH-RMS with the e_est qualification (COMMISSIONING 7.5) |
| B8 | End-of-line veto test: force MON_GOOD_HA low, then MON_GOOD_HB low; the heartbeat stops and BIAS_GOOD drops within its hold time (screens the GOOD-node corridor open, DECISIONS 52) | FMEA §6c | Bring-up / test plan (owner) | New | Add to the production test spec |
| B9 | PMEG6030EP,115 (gate turn-off diode): JLC holds 3; the JSMSEMI clone C53114006 is not qualified | DECISIONS 54 | Sourcing (owner pre-order) | New | Add to the pre-order list or qualify an alternate |

## 3. Cost (scorecard parts $206.44 at 500 on the 2026-10-13 survey; $186.54 on the 2026-10-15 snapshot; bare board $17.28)

| # | Item | $ per board | Lane / owner | Status |
|---|---|---|---|---|
| C1 | Bridge MOSFETs 4 × IPW65R018CFD7 | 40.70 | CM8 −$6.77 (drop-in, needs R_ext 12 Ω; proxy model; DigiKey 482 vs 2,000, 24 wk): deferred to candidate 39 (DECISIONS 49) | Studied |
| C2 | Bus TVS D3 / D17 (snapshot: $8.17 from Good-Ark at DigiKey, not $19.64) and F1 (A2 #5) | 8.17 + 18.52 | Owner / certifier | Packet |
| C3 | U41 / U42 RECOM bias modules | 14.74 | Kept (DECISIONS 49: discrete saves $2.8–3.9, zero-stock controller, transformer Cw unbounded); T&R at the 750 break −$0.38 | Closed |
| C4 | C5 / C6 | 12.34 | Parts (S8) | Alternate chosen, pending suffix |
| C5 | PS1 deletion (candidate 23) | 4.20 saved net of PS2 → MPM | Done (DECISIONS 50) | Closed |
| C7 | Bare board: six layers $19.11 vs four $17.28 pinned; area compaction ~$1.5 per 10 % | DECISIONS 40 | After candidate 23 (compaction) | Open |

## 4. Layout lanes (one building: ps-layers; ps-selv free)

| Lane (island) | Candidate | Status | Blocked on |
|---|---|---|---|
| Tank / FET row (WS3 / WS4 boundary) | 36: done, stage 41 (DECISIONS 53); shunt not adopted | Merged | — |
| Gate networks (HS / LS driver outputs) | 39: R_on 68 Ω 2512 + Cgs 4.7 nF (DECISIONS 54); fixes S14 (typical Qrr) and the S2 gate-R derating; stage tag s42 | Running (ps-layers, branch claude/native21-c39-gate-network) | — |
| SELV side (WS5, spine owner) | 23: done, stage 38 (DECISIONS 50); spine baseline re-issued (s38) | Merged | — |
| HS-B / LS (WS4) | 30a / 30b done, stage 40 (DECISIONS 52) | Merged | — |
| Tank / bank | 34: resonant bank | Waits on stock | S9 |
| Whole board (last) | Geometry cleanup pass (B5; tool merged, DECISIONS 48: s35 → s37 right angles 104 → 50, acute 206 → 23, fold-backs 44 → 3, any-angle 704 → 308 mm; ACCEPT); compaction (C7) | Tool ready; ps-layers free | Run on the merged copper after c23 / c36 / c30 land |

## 5. Owner actions

- Restart the remote FEM box (S3).
- Send the certifier packet (S11, with S12).
- Relay to the controller session: `c23-supply-topology/CONTROLLER-REQUEST.md` (J13, with addenda 1–2: a stage-38 board needs the J13 merge and J4.1 dropped before it is powered); the still-air ceiling ≤ 18 A until
  S2 passes (DECISIONS 46); temper-8d's controller CR-1..CR-7
  (`git show sensor-c1-impulse-mining:output/temper-sensor-r3/pcb/CHANGE-REQUEST.md`; not this board, so not reviewed
  here).
- Relay `c23-supply-topology/MODULE-REQUEST.md` (D-22 module: Y caps removed, SCF31X choke) and `c23-supply-topology/ENCLOSURE-REQUEST.md`.
- Relay `b3-ratings/ENCLOSURE-REQUEST.md` (board-face airflow) and `c35-smt-terminals/ENCLOSURE-REQUEST.md` (lug
  seat +2.5 mm) to the enclosure session.
- Pre-order the long-lead parts (`sourcing/study-2026-10-15/README.md` §4), L1 first.
- Confirm DigiKey's "B32676G1106K Z 1" is the catalogue B32676G1106K (S8).
- Bench: coil L / R with real pans; bank hot spot; terminal pull, torque and temperature; module temperatures; bay air
  and board copper at R5 in an enclosure soak (S2).

## Closed

- Six layers: phase A accepted on the data, not adopted on price (DECISIONS 39–40).
- CTI (DECISIONS 41).
- SELV-spine lock in the chain (27e946580).
- Board thickness vs the REDCUBE terminals, and JLC's THR reflow: SMT terminals adopted (DECISIONS 42, 44; was S5, B3).
- Buildability metric in the scorecard (DECISIONS 45; was B2's metric half).
- B3 temperatures compared with ratings: gate in place (DECISIONS 46; the violation itself is S2).
