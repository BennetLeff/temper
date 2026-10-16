# native-21 open items (register, updated 2026-10-15)

One row per open item on the power board, so nothing falls between lanes. Board of record: **s45** (board 26ce9531,
rebuilt a1e6488f with identical geometry; 4 layers; DECISIONS 60: s44's copper with the S16 monitor fix; DECISIONS 58).
Thermal basis: B3 on hot copper, release case c17.5 @ 61, tank ceiling 17.5 A (DECISIONS 61); not releasable until the
85 °C monitor ICs are replaced (stage 46). Keep this current: when an item closes, give the DECISIONS number
and move it to "Closed" at the end. Agents marked "running" write to scratch; the integration session reviews and
commits their results.

Lanes:
- **Layout lanes** are one-writer worktrees, one per isolation island (13-coupling), merged one at a time through the
  scorecard. At most 2–3 run at once.
- **Analysis lanes** build nothing and run in parallel.

Scorecard (DECISIONS 43, 45, 46): compare against `10-benchmark/scorecard-native21s45.json` (the board of record). The release gates
(`RELEASE_GATES`: `b3_ratings`) and the leakage limit are absolute conditions for an order. A candidate is graded on
their ratchets.

## 1. Correctness and safety (ranked first)

| # | Item | Evidence | Lane / owner | Status | Next |
|---|---|---|---|---|---|
| S2 | **Board temperatures vs ratings (s42, still air, DECISIONS 55):** gated still-air ceiling **20.0 A at bay 55 °C, 18.3 A at bay 61 °C** (R10 R_on derating, laminate block, C40); release ceiling **18.0 A** (firmware default 22 → 18 A, follow-on commit). 28 A in still air is not reachable on 2 oz (c28 laminate −30.6 K). History: s41 22 A laminate +1.2 K, but the 1206 gate resistors failed with no tank current.  | DECISIONS 46, 51, 53, 55; `b3-ratings/`, `c39-gate-network/` | Enclosure airflow reply (the only route above ~20 A). **Reply in hand:** temper-8d airflow-r1 (`sensor-c1-impulse-mining:output/temper-airflow-r1/`, 4142408bf) gives 8 × Ø3 mm jets from the push hood, about 0.48 CFM at drive 0.55 and an estimated h ≈ 100 (Martin, outside its Re range). The board needs h_top 73 / 97 W/m²K at 28 A, bay 55 / 61 °C (C40 then C38 limit), and their sweep reproduces s42 margins.json to 0.0 K. **Board side, queued after s43:** (a) a jet-region h case in run_basis / thermal_body (port their override), so that COMMISSIONING gate 0 can be evaluated; (b) a body-to-air path for C38–C41 (lead-only is the upper bound today); (c) **done:** `gates/jet_strip_height.py` (chain + card gate `jet_strip_height`; s42 max 1.72 mm, C12) checks the height ≤ 4 mm keep-out on the jet strip: the B3 model frame x 0–90, y 7.0–23.5 mm, inclusive, on cell and part centres (`board_h_sweep.py:86`). Grow it to the jet box's projected footprint + 1 mm (enclosure X −140..−53, Y 213.5..225.5, floor 6.0 mm above the board) once the enclosure-to-board transform is pinned; (d) U26 at 28 A / bay 61 °C keeps only 0.6–2.4 K and airflow does not reach it, so it needs a candidate. No ceiling raise until the jet h is measured on the bench; bench R_on IR reading (0.217 W bound vs ~0.17 W simulated) | Open | **Release gate PASS on s42 at c18 / bay 61 / 13.5 A, +0.7 K (R10), DECISIONS 56; firmware ships 18 A.** **Line-current basis:** the cases use I_line 11.1 A, but the firmware bound is 13.5 A (I_ps·1.10 + I_aux). At 13.5 A gated rows move ≤ 0.1 K, C40 / ceiling unchanged, C38 c22 +0.1 → −0.0 K, L1 −12 K (adv, +25 K left) (`b3-ratings/line-hold-2026-10-15/`). Done: I_line 13.5 A everywhere (DECISIONS 56). **Product consequence** (temper-8d nameplate-r1, `sensor-c1-impulse-mining:output/temper-nameplate-r1/`, cross-checked against the round-6 ngspice grid, 931 vs 904 W at 22 A): pooled pan power is 650 / 856 / 931 W at an 18 / 21 / 22 A ceiling (0.42–0.61× the Control Freak), whatever the nameplate. Only board-face airflow (the 24–28 A route) moves it. Firmware ships 18 A (DECISIONS 56) |
| S15 | **UL 858 25.3.1 (safe with the solid-state control dead or stuck):** on this board, the firmware-independent trips (R5 Kelvin OCP, U7 OVP 280 V, bias-rail heartbeat → BIAS_GOOD, BUS_FAULT → controller interlock → DIS) all act on faults. A stage stuck on at normal current trips none of them. The only firmware-independent cut for that case is the TCO loop (J3): opening it removes PS2, and with it all gate drive, HOT5 and OCP_OK (DECISIONS 2026-10-06). The TCO rating and mounting are still provisional, set from measured glass and sink temperatures (README; electrical review P1) | temper-8d round 3; FAULT-INTERFACE; DECISIONS 2026-10-06 | Owner / enclosure (TCO rating, mounting); controller (whether PERMIT needs an MCU watchdog) | Open | Choose the TCO and its location so that it opens before the pan or glass is damaged with the stage stuck on at the ceiling; certifier confirms that the TCO counts as the 25.3.1 backstop |
| S17 | **B3 never corrects copper loss for temperature** (found by heat attribution, 2026-10-15). The A4 fields are 20 °C DC copper (`run_board.py:312`); B3 scales them by I² only, while the tank copper runs at 83–112 °C on the c18 field (×1.25–1.36 loss). A one-step estimate on the s43 model adds +6.1 K at C40, +6.5 K at R10 and +7.2 K at the laminate block, and takes the bay-61 still-air ceiling from 18.44 A to ~16.4 A: **the 18 A release case may not hold.** The estimate is outside the gate's model; do not cite it until the coupled solve exists | `round5-native21/heat-attribution-2026-10-15/` §Surprises 1 | B3 model lane (hot-copper iteration), then release basis | **Partly done (DECISIONS 61)** | B3 is hot by default (q20·(1 + α(T − 20 °C)), fixed J, solved at each bay); the release case is now c17.5_h10 @ 61 (R10 +1.0 K on s45 by direct solve; 18 A was −0.7 K) and firmware ships 17.5 A (44cf184a7). G6 R5 still passes on hot copper (32.6 % on s42). **Residual:** (a) the 85 °C monitor ICs fail the release case at any current; stage 46 (125 °C grades) fixes it; (b) the controller-enclosure jet h_top (45 / 59 W/m²K, temper-8d) was solved cold and must be re-solved; (c) `cu_temp_basis` still waives 12 files: S17 (8 diagnostic / dated a4field scripts: b3-convergence, h10-stall, r5-derating, stage15b), S17-ipc (`sw_widths.py` ×2), S17-neck (`neck_fin.py` ×2), expiring 2026-11-30; retire them (re-basis or mark as dated records) and switch on `--fail-waived` |
| S18 | **PS2 (MPM-20-24) temperature: inside rating by estimate, model fix needed.** The hot-copper sweep read PS2 pads 112 °C vs its 85 °C rating, but that rating is **ambient** (MPM-20-SPEC p.2 / p.3 curve; no Tc), and ~34 K of the pad reading is PS2's own 0.67 W forced through its pins because B3's `meanwell` class has no body-to-air path (`thermal_body.py:123`). With its heat removed the board under it is bay + 5 K; equivalent ambient ≈ 65 °C at c18 @ 61 against 82.9 °C allowed at its 7.08 W load (+17.8 K; +9.1 K at the 9.59 W allocation; pessimistic bound +2.9 K) | `b3-ratings/ps2-thermal-2026-10-15/` | B3 model (body-to-air for `meanwell`, row on equivalent ambient vs the p.3 curve); bench S2 soak | New | Model fix in the next B3 lane; S2 soak TCs: PS2 case top (predict +20 K, refutes ≥ +35 K), shielded local air, bay air, insulated pin pad; log PS2 output (refutes > 9.6 W) |
| S16 | **Rail-monitor windows overlap the rails' tolerance at worst-case corners: confirmed on worst case** (span UV upper 16.804 V vs rail min 16.575 V; span OV lower 17.192 V vs LS max 17.425 V); on RSS ~1–2 ppm per rail. Fail-safe direction (refuse to start / nuisance trip). Main term: TL431A tolerance and drift. Fix chosen: **option 1c-4420** (TL431BIDBZR, R79 4.42 k, new taps; BOM-only, +$0.17). Its span-OV corner 18.60 V is covered by the out-D33 hot-load re-run at 19 V (128 / 128). Candidate B (TPS3701, +$1.53) not adopted for S16; its fault-isolation case is mixed (better on C2 / C4 die and open / short faults and C7; open questions on silent reference drift and the C5 7 V pin) and settled by FMEA (DECISIONS 59): B as drawn is a regression (17 V on a 7 V pin under one fault); amended B beats 1c-4420 by ~13 % FIT·rails for +$1.49 and a three-island re-lay, so only if those islands are re-laid | `11-candidates/s16-monitor-2026-10-15/`; `out-D33/rail-hot-19V/` | Candidate (next, BOM-only stage) | **Done (DECISIONS 60, stage 45)** | Residuals closed: B3 probe rows at the monitors exist (hot basis) and show the 85 °C grades fail at bay 61 → stage 46; U17 / U19 / U21 rotation settled at 180° from datasheet pin evidence (CPL audit). Open: buy RT0603BRD07750RL early (2,661 at JLC vs 1,500) |
| S14 | **IPW65R018CFD7 body-diode limits broken in S4:** dv/dt 85.8 V/ns (70 rated) and diF/dt 2,101 A/µs (1,300 rated) on the vendor model; at typical Qrr 109–112 V/ns and die VDS 620 V. S4 is a burst design case (370–740 edges per leg before the software latch) | DECISIONS 49, 54; gate-network study | Candidate 39, stage 42 (DECISIONS 55): 49.7 V/ns and 244 A/µs at typical Qrr; CFD7 VIOLATION → PARTIAL | Built (typical Qrr) | Max-Qrr basis open: D-8 bench (R_on 39 / 68 / 100 Ω × Cgs 1 / 4.7 nF, repeated S4 edges); controller: hardware capacitive-mode detector |
| S1 | Touch leakage: was 0.974 mA. **Built in s38 (DECISIONS 50):** 0.2412 mA DESIGN (budget 0.25, margin 8.8 µA) with the off-board D-22 module Y removed + SCF31X choke and PS3 → MPM-65-15ST; s19b EMI 12.37 / 8.19 dB | `c23-supply-topology/README.md`; co-design study | Controller (J13 merge, PS3); D-22 module (`c23-supply-topology/MODULE-REQUEST.md`); certifier (MPM approvals: IEC 60601-1 / 60335-1, no UL file) | Passes on the model | Bench: measured supply leakage, SCF31X DM leakage, HF touch with the lab's meter network. Robust variant (L1 → SCF31X) needs an L1-slot re-layout |
| S12 | Laminate UL scope: KB-6164 (35 µm) and KB-6165 (54 µm) multilayer rows don't cover 61 µm (2 oz) inner copper; KB-6164F / 6165F / 6167F list 102 µm, and JLC's "TG155" option links KB-6165F. Item 41 named KB-6164 for CTI; `stackup.json` still says Nan Ya NP-155F | DECISIONS 41, 51 | Owner → JLC (UL Product iQ needs a login) | Open | Which recognised JLC-4 construction covers 4 L, 2 oz inner, CTI ≥ 175 V; then fix the order remark and stackup.json together |
| S3 | F6's 252/252 result rests on round-17 loop matrices from board 76ec8cca, not s35 | `c33-six-layer/adoption/README.md` | FEM (remote box) | Blocked: box offline | Owner restarts the box; run `adoption/fem/chain_c33.sh` for s35 |
| S8 | C5 / C6 ripple at 28 A: on the vendor basis the fitted part carries 28 A only at cap ambient ≤ 80 °C; no stocked part fixes 28 A at 85 °C. 28 % of the HF ripple power is above TDK's 95 kHz chart edge | DECISIONS 45 | Parts | Verdict recorded | B32676G1106K once "Z 1" = catalogue part is confirmed (owner or distributor); bench C5 case temperature |
| S9 | Resonant bank 1.045× TDK's curve at 28 A; no ≤ 0.85 option in authorised stock | DECISIONS 37, 45 | Candidate 34 | Waits on stock | Moot below 28 A while S2 limits the ceiling |
| S6 | CMTI 1.5× rule not met on FILTERED / OPEN rows (1.05×) | `c31-bom/README.md` | Parts / certifier | Open | Covered by the isolator review; NSi822xW rejected (no open-input state) |
| S7 | Datasheet ledger: **3 VERIFIED / 32 PARTIAL / 58 UNAUDITED (SIGNAL) / 0 VIOLATION** of 93 lines; gate PASS | `datasheet-ledger/` (3367e789b) | Batches A (14) + B (13) merged on s42 under the DECISIONS 56 stress basis: thermal ratings judged at c18 / bay 61 °C; c22 / c28 overruns are `owner: airflow route (c22/c28)` gaps; electrical ratings at s42's 49.7 V/ns S4 edge; max-Qrr (106 V/ns) is a D-8 gap on every CMTI line | Merged | Cleared: 25121WF680JT4E (0.775 at c18), R5 (0.14; element 0.72), bank (0.71 of the curve, 90.0 °C), ISO6721FB CMTI 2.0×, 2EDR8259X 3.0×. B3 advisory C5 / C6 Top,max 110 → 105 °C (TDK p.13). Thin at c18: C40 0.99, GRM31A5C3A102 FET-row 0.984. Owner: correct the C12 / C13 / C19 / C20 source MPN to CC1206JKNPOCBN102 (JLC already orders it). Next: the 58 SIGNAL lines; bench D-8 (max Qrr) and the gate-row IR reading |
| S10 | Return-path open changes: 18 → 15 (s40) → **7 (s44, DECISIONS 58: all 8 SELV-net opens closed by transfer caps C169–C175)**. The 7 left are HOT side: bus_fault_hot ×3, ocp_ok_hot, ovp_ok_hot ×2, the GOOD node at U45.1. Their vias sit off the In1 ocp_kelvin_p / n_ls pours with In2 / B bare | DECISIONS 39–40, 52, 58 | Layout (WS4 / G08) | Open (7) | A HOT-side pass: Kelvin / n_ls reference copper at those vias, with the stage-28 OCP lock, OCP pickup (4.17 A) and Kelvin band re-checked |
| S11 | Certifier questions (CERTIFIER-PACKET A1–A4: F1, insulation, PEC / FMEA, supply approvals, RES_A, coil-lane voltage); add S12 to A3 | `owner-items/CERTIFIER-PACKET.md` | Owner | Draft, not sent | Owner sends the packet |
| S13 | temper-8d requests: AMC1301 measured input current on R5 (HOT5 domain; J4 +2 pins; +7–9 % power at the 15 A plug); pan-detect re-validation on the full bridge (Al / Cu / small / warped pans); ±1 kHz dither at 120 Hz (check ZVS at fs − 1 kHz). Split-R coil EMI model: right physics, no verdict change (DECISIONS 47) | `git show sensor-c1-impulse-mining:output/temper-coil-driver-r1/RECOMMENDATIONS.md` | AMC1301: a later candidate (kept out of 23 to hold its scope; its power argument is capped by S2); firmware items to the controller | Logged | After S2 |

## 2. Buildability (JLC fab and assembly)

| # | Item | Evidence | Lane / owner | Status | Next |
|---|---|---|---|---|---|
| B1 | **L1 B82726S2203A020 sets the build date:** no authorised stock, 29-week lead, so a 500-board build lands ~2027-05 if ordered now. 14 lines short for 500 boards, 3 for 5; JLC-assemblable share 0.851 / 0.968 | DECISIONS 45; `sourcing/study-2026-10-15/` | Owner (ordering); EMI re-run for L1 alternate B82726S2243A020 | Plan ready | Owner pre-orders (README §4). L1 alternate: c29 / D-22 EMI re-run with 0.75 mH / 8 µH |
| B2 | Five "short" lines are read gaps (DigiKey bot check, Octopart 403), not proven shortages | DECISIONS 45 | Sourcing | Open | Re-take the snapshot when the sites read again |
| B4 | Order remarks: KB-6164 with KB-6064 prepreg (S12 may change this), stack JLC041622-7628 named, Confirm production file. Thickness remark dropped (DECISIONS 44) | FAB-NOTE | Order (owner) | Ready | Answered at JLC's file review |
| B5 | Track-geometry hygiene: **done on s43** (DECISIONS 57): right angles 100 → 49, acute 199 → 23, fold-backs 43 → 3, any-angle 675 → 273 mm | DECISIONS 43, 48, 57 | — | Done | Later lanes re-run the pass after merging (it is idempotent) |
| B6 | Stencil: J2 / J5 want 150 µm paste; fine-pitch parts' stencil not chosen; J2 / J5 CPL rows NEEDS-PREVIEW | DECISIONS 44 | Order (owner) | Open | Step stencil or aperture choice at order |
| B7 | `PROTOTYPE-LOT.md` regenerated for s43 (board 61447816): 4 L, KB-6164, s43 BOM, 2026-10-15 snapshot, 18 A firmware gate | `08-manufacturing-package/native-21/PROTOTYPE-LOT.md` | Integration | Done | Re-run when the BOM changes or the snapshot is re-taken (B2) |
| B10 | **Validation cases from temper-8d mining round 3** (`sensor-c1-impulse-mining:output/temper-mining-r3/`): UL 858 59.6 iron bar (2 × 100 × 20 mm, ≤ 35 °C rise at the highest setting) plus fork / spoon / knife on pan detection; 47.8 off within 30 s of vessel removal, manual reset; bad-pan set (multi-ply Al with a thin stainless base, Demeyere ControlInduc cold → 250 °C, Demeyere Proline) at full power, showing pll_control stays stable and the hardware OCP (R5 Kelvin) / OVP (U7, 280 V) / tank-CT trips act before any device is overstressed (ties to S14's capacitive-mode case) | temper-8d round 3 | Bring-up / test plan (owner, controller) | New | Add to the bench plan beside D-8 |
| B11 | **Aux inlet allowance (temper-8d, applied):** `blower_aux.c` base_a 1.3 → 0.26 A (PS1 gone), ps3_eta 0.875, ps3_pf 0.67. The allowance at 108 V goes from 1.35 / 1.93 / 2.57 to 0.31 / 0.60 / 0.887 A (blower off / mid / full), and the full-blower hold from 9.94 to 11.47 A. The board is covered: B3 at 13.5 A line current, `line-hold-2026-10-15/`. The constants stay PROVISIONAL until the true-RMS bench check (`output/temper-aux-load-r1/BENCH-RMS.md`: blower states × 108 / 120 / 132 V; CH2 = the J1 line conductor with the J3 and J11 leads passed through backwards) | `output/temper-aux-load-r1/` (aux_load.py reruns byte-identical) | Bring-up (owner) | Applied, bench open | Run BENCH-RMS with the e_est qualification (COMMISSIONING 7.5) |
| B8 | End-of-line veto test: force MON_GOOD_HA low, then MON_GOOD_HB low; the heartbeat stops and BIAS_GOOD drops within its hold time (screens the GOOD-node corridor open, DECISIONS 52) | FMEA §6c | Bring-up / test plan (owner) | New | Add to the production test spec |
| B12 | **Chain latency (scoped verification, `layout/gates/scoped/`, opt-in `SCOPED_PLAN`)**: parts-only lane 16.8 → 7.3 min, desk / gate-script changes 16.8 → 0.4 min, layout lanes no gain (B3 reads all copper). Back-test 17 cases, 0 misses. Follow-ons: (a) **B3 ratings has no cache** (9.4 min every chain); (b) run the B3 legacy study + sweep beside the ratings solves (29.4 → 23.3 min on every thermal run); (c) `copper_key` hashes `.kicad_pro` byte for byte, so schematic-only edits bust it; (d) a text-only stack-up edit misses the caches; (e) ratings inputs are not derived from the BOM; (f) the ledger reads `.md` lines, so docs are scorecard inputs | `layout/gates/scoped/README.md`, `backtest.py` | Integration (tooling) | Applied | First full chain after this commit is the scoped benchmark; then (a), (b) |
| B13 | **No proof test covers dormant masking in the rail monitors** (any variant; FMEA DECISIONS 59): B8 screens the HS veto corridor only. Options: an end-of-line per-tap forcing test (catches 72–91 %, manufacturing defects only); an LS rail-raise test (ground the unused TPS7A4700 3P2V pin → 20.2 V) that catches every LS span-OV mask, dividers included | `11-candidates/s16-fmea-b-2026-10-15/` §proof tests | Bring-up / test plan (owner) | New | Choose the test hooks (a test pad on 3P2V, per-tap pads) before the next layout touches the monitor islands |
| B9 | PMEG6030EP,115 (gate turn-off diode): JLC holds 3 at the c39 read, 7 in the s43 snapshot (8 needed for 2 boards, 20 for 5); the JSMSEMI clone C53114006 is not qualified | DECISIONS 54 | Sourcing (owner pre-order) | New | Add to the pre-order list or qualify an alternate |

## 3. Cost (scorecard parts, s45, `bom_pricing-v1`: $171.71 at 500 / $262.77 at 5, every line from a dated read, not a quote: 19 lines at 500 have no read holding the whole lot; legacy basis $201.60; bare board $17.28)

| # | Item | $ per board | Lane / owner | Status |
|---|---|---|---|---|
| C1 | Bridge MOSFETs 4 × IPW65R018CFD7 | 40.70 | CM8 −$6.77 (drop-in, needs R_ext 12 Ω; proxy model; DigiKey 482 vs 2,000, 24 wk): deferred to candidate 39 (DECISIONS 49) | Studied |
| C2 | Bus TVS D3 / D17 (snapshot: $8.17 from Good-Ark at DigiKey, not $19.64) and F1 (A2 #5) | 8.17 + 18.52 | Owner / certifier | Packet |
| C3 | U41 / U42 RECOM bias modules | 14.74 | Kept (DECISIONS 49: discrete saves $2.8–3.9, zero-stock controller, transformer Cw unbounded); T&R at the 750 break −$0.38 | Closed |
| C4 | C5 / C6 | 12.34 | Parts (S8) | Alternate chosen, pending suffix |
| C5 | PS1 deletion (candidate 23) | 4.20 saved net of PS2 → MPM | Done (DECISIONS 50) | Closed |
| C8 | **The scorecard prices 58 of 93 BOM lines at class-default estimates** (e.g. LM4040A $0.40 vs JLC $1.26; TL431A $0.40 vs $0.049), so logic swaps score wrong. The snapshot also prices U41 / U42 at $0.0204, a JLC 'listed_no_stock' artefact; the card uses DK $7.37 Stage 45 shows it again: the card reads −$0.78 for a change that costs +$0.18 on like-for-like JLC ladders (`c45-s16-monitor/results/cost-s44-s45.md`) | simplify-2026-10-15 §6 S2 / S3 | Sourcing / scorecard | **Done (2026-10-15)** | `gates/bom_pricing.py` (card keys `*_v2`, `price_basis`, `price_estimated_lines` = [], artefact rule rejects the RECOM $0.0204 / $0.0397 rows); s44 → s45 delta +$0.1807 = `cost45.py`. Compare uses v2 only when both cards carry the same basis, else NOTE (or `--strict-basis` refuses). s45 benchmark re-scored. Residual: re-take reads for the 19 lines with no lot-holding source (IPW65R018CFD7, B32654 bank, 30KPA150CA, KLDR025) |
| C7 | Bare board: six layers $19.11 vs four $17.28 pinned; area compaction ~$1.5 per 10 % | DECISIONS 40 | After candidate 23 (compaction) | Open |

## 4. Layout lanes (none building; ps-layers and ps-selv free)

Coupling model (13-coupling, refreshed on s43): out of sample on s33–s43 it keeps part of its power (AUC 0.70 vs 0.81 in
sample; 0.86 without s38's mains re-lay). Use it to schedule lanes, never to skip the scorecard. New interface contract
WS1↔WS4 (0.212): a shared re-check of leakage (0.241 / 0.25 mA) and release-case heat, not shared layout. Spine lock held
on every non-owner stage since s32 (0 locked items changed).

| Lane (island) | Candidate | Status | Blocked on |
|---|---|---|---|
| Tank / FET row (WS3 / WS4 boundary) | 36: done, stage 41 (DECISIONS 53); shunt not adopted | Merged | — |
| Gate networks (HS / LS driver outputs) | 39: done, stage 42 (DECISIONS 55); laminate REJECT overridden | Merged | — |
| SELV side (WS5, spine owner) | 23: done, stage 38 (DECISIONS 50); 44: SELV return-path pass, stage 44 (DECISIONS 58); spine baseline re-issued (s44) | Merged | — |
| HS-B / LS (WS4) | 30a / 30b done, stage 40 (DECISIONS 52) | Merged | — |
| Tank / bank | 34: resonant bank | Waits on stock | S9 |
| Whole board (last) | Geometry cleanup pass: done on s43 (DECISIONS 57); (B5; tool merged, DECISIONS 48: s35 → s37 right angles 104 → 50, acute 206 → 23, fold-backs 44 → 3, any-angle 704 → 308 mm; ACCEPT); compaction (C7) | Done; ps-layers free | — |

## 5. Owner actions

Ranked by what they unlock.

1. **Push board-face airflow with the enclosure session** (`b3-ratings/ENCLOSURE-REQUEST.md`). It is the only route
   above about 20 A of tank current. At the 18 A release ceiling, pooled pan power is about 650 W at 120 V (0.42× the
   Control Freak, S2). Also relay `c35-smt-terminals/ENCLOSURE-REQUEST.md` (lug seat +2.5 mm) and
   `c23-supply-topology/ENCLOSURE-REQUEST.md`.
2. **Choose the TCO rating and its mounting** (S15). It is the UL 858 25.3.1 backstop for a stage stuck on.
3. **Relay to the controller session:**
   - `c23-supply-topology/CONTROLLER-REQUEST.md` (J13, addenda 1–2). A stage-38+ board needs the J13 merge and J4.1
     dropped before it is powered.
   - The firmware on this branch now ships the 18 A tank ceiling (DECISIONS 56) and the RMS-increment aux allowance
     (B11). The controller image must carry both.
   - `c39-gate-network/CONTROLLER-REQUEST.md`: a hardware capacitive-mode (phase) detector (S14).
   - Optional: a bay-air sensor would let the firmware run 20 A when the bay reads ≤ 55 °C (DECISIONS 55).
   - temper-8d's controller CR-1..CR-7 (`git show sensor-c1-impulse-mining:output/temper-sensor-r3/pcb/CHANGE-REQUEST.md`;
     not this board, not reviewed here).
4. **Relay** `c23-supply-topology/MODULE-REQUEST.md` (D-22 module: Y caps removed, SCF31X choke).
5. **Send the certifier packet:**
   - S11, with S12 (laminate UL scope for 61 µm inner copper);
   - the MPM approvals;
   - the EOL veto test (B8);
   - S15 (TCO as the 25.3.1 backstop).
6. **Ask JLC about the laminate UL scope for 2 oz inner copper** (S12).
7. **Pre-order the long-lead parts** (`sourcing/study-2026-10-15/README.md` §4): L1 first, then PMEG6030EP (B9).
   Confirm that DigiKey's "B32676G1106K Z 1" is the catalogue B32676G1106K (S8).
8. **Bench, first:**
   - the gate-row IR reading (the R_on 0.217 W bound behind the +0.7 K release margin);
   - D-8 double pulse for max Qrr (S14);
   - BENCH-RMS for the aux allowance (B11);
   - B10's UL 858 cases and the bad-pan set.
9. **Bench, then:**
   - coil L / R with real pans;
   - the bank hot spot;
   - terminal pull, torque and temperature;
   - module temperatures;
   - bay air and board copper at R5 in an enclosure soak (S2).
10. **Restart the remote FEM box** (S3).
11. **Delete about 11 MB of scratch** under `runs-native21/s40/` (`src0`, `src1`, `src2`, `view`, `t-*.json`). The
    safety check blocked me from removing it.

## Closed

- Six layers: phase A accepted on the data, not adopted on price (DECISIONS 39–40).
- CTI (DECISIONS 41).
- SELV-spine lock in the chain (27e946580).
- Board thickness vs the REDCUBE terminals, and JLC's THR reflow: SMT terminals adopted (DECISIONS 42, 44; was S5, B3).
- Buildability metric in the scorecard (DECISIONS 45; was B2's metric half).
- B3 temperatures compared with ratings: gate in place (DECISIONS 46; the violation itself is S2).
