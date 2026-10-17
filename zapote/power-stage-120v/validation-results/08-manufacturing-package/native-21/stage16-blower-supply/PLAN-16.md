# Stage 16 plan: separate blower supply (PS3)

Planning only. Nothing in the unit or on `controller-layout` was changed by this study. Every number comes from a script in this folder (outputs in `out/`) or from a cited data sheet page.

**Baseline**
- **Power board:** native-21 stage 15b. Board `9a9c43c6…`, `layout/copper.json` `a831e90c…`, DECISIONS items 10–14.
- **Controller:** branch `controller-layout` `4bed3716a`, DECISIONS C28, open item 13.
- **Enclosure:** R39, `output/temper-manufacturing-r39`, CURRENT.json.

**Why this stage exists:** the 2026-10-08 entry "D-18(3) fan supply superseded" says it reverses "if … PS1's load exceeds ~80 % of its rating". At full blower speed PS1 would carry 40.8 W against its 21 W rating (`out/budget16.txt`), so that condition is met. The owner wants a separate supply so that a blower start or stall cannot brown out the controller logic.

## 0. Decision summary

| Item | Decision |
|---|---|
| Topology | **(a)**: a dedicated 15 V SELV module (**PS3**) feeds the controller's existing TPS62933 blower buck (U2) through its own harness pair. The buck input is separated from the logic 15 V. |
| Part | **Mean Well IRM-60-15ST**: the chassis-mount screw-terminal variant of the IRM-60-15. 60 W, 15 V 4 A, 109 × 52 × 33.5 mm. |
| Where | **Not on native-21**: there is no room for it (see §2.1). It is chassis-mounted in the enclosure. The candidate volume is in §2.3, and the enclosure team owns the final allocation. |
| Power-board change | A small mains tap only: **F2** (3.15 A time-lag) + **J11** (JST B2P3-VH, the J3 part) beside PS1's AC pins. The tap is fed from L_FILT / N_FILT, i.e. after F1 and the L1/C1/C2 filter, like PS1/PS2. No part moves, and no SELV copper is added. |
| Controller | New J13 (JST B2P-VH) for V15_BLW. U2's VIN, its EN divider top and its input caps move from v15_selv to V15_BLW, and a 100 µF bulk cap is added. FAN_OFF and the PWM-into-FB scheme are unchanged. |
| Firmware | `aux_max_a` 1.3 → **2.55 A** (static, at full blower), or a drive-scheduled allowance (§5). |

Rejected options:
- **(b)**, a direct 12 V rail: the TPS62933 cannot make 12.40 V from 12 V, and switching or PWM-ing a 2.9 A rail into a 3-wire tach blower loses both the speed control and the tach.
- **(c)**, upsizing PS1: §1.3.

## 1. Topology and part

### 1.1 Load (`budget16.py`)

**Blower** (Delta BFB1012VH-F00, enclosure R33 study 10 / spec p.1):
- 32.4 W / 2.70 A at 12.0 V (Delta maximum).
- At the buck's 12.40 V duty-0 corner (C28), the fan law gives **35.7 W / 2.88 A**. This is an estimate, on study 10's basis.
- The owner's 12.4 V × 2.70 A = 33.5 W is below that figure, so the plan designs to 35.7 W.

**PS3 output:** 35.7 W / η_buck 0.90 (the controller_calcs allocation) = **39.7 W**. That is **2.72 A** at the 15 V −2.5 % corner.

**PS1 after the split:** 4.8 W of 21 W (23 %). This is the logic share from `controller_calcs.json`: 14.8 W total at the R32 cap minus 10.0 W of blower input.

### 1.2 Candidates

| Part | Rating | Load | Ambient for this load (p.3 derating) | Size (p.2) | Stock (2026-10-12) |
|---|---|---|---|---|---|
| **IRM-60-15ST** (chassis) | 60 W, 15 V 4 A | 66 % | ≈ 64 °C | 109 × 52 × 33.5, 4 × Ø3.5 | DigiKey 1866-3066-ND **374**, $17.30; LCSC C7290321: 0 |
| IRM-60-15 (PCB) | same | 66 % | ≈ 64 °C | 87 × 52 × 29.5 | LCSC C6280128: 0; Jameco 2224850 |
| IRM-45-15 (PCB) | 45 W, 3 A | 88 % | ≈ 55 °C (IRM-60 curve assumed; the IRM-45 page was not re-read) | 87 × 52 × 29.5 | LCSC C5656527: 585 |
| IRM-30-15 | 30 W | 132 % | — (over its rating) | 69.5 × 39 × 24 | — |

How the ambient column is derived:
- IRM-60-SPEC 2025-11-21 p.3 derating, "for others" curve: 100 % to 50 °C, 75 % at 60 °C, down to 15 % at 85 °C. This was read from the graph.
- The project's air basis is 50 °C (D-18).

The IRM-45 is the same body as the IRM-60 with less margin, so the IRM-60 is the choice. **Fallback if IRM-60-15ST stock fails:** IRM-60-15 (PCB pins) on a small carrier, or IRM-45-15, accepting 88 % load and ≈ 55 °C.

**Data-sheet facts (IRM-60-SPEC 2025-11-21):**
- **p.1:**
  - Class II (no FG pin); OVC III; LPS except 5 V;
  - EMI Class B without added parts;
  - −30…85 °C.
- **p.2:**
  - Input 85–305 Vac. **AC current 1.8 A typ at 115 Vac.** **Inrush 30 A typ cold start at 115 Vac.**
  - **Hold-up 12 ms at 115 Vac, full load.**
  - Efficiency 89 %; ripple 120 mV p-p; tolerance ±2.5 %; set-up 2000 ms at 115 Vac.
  - Overload 115–160 %, hiccup; OVP 15.75–20.25 V.
  - **Withstand I/P–O/P 4.2 kVac.**
  - Safety: **IEC 62368-1, UL 62368-1, TUV EN 62368-1, BS EN/EN 60335-1, IEC/EN 61558-1/-2-16**. OVC III under 62368-1 and 61558; **OVC II under 60335-1**; 2000 m.
  - ST variant: 109 × 52 × 33.5, vibration 5 G.

**Insulation:**
- A Class II module with 4.2 kVac I/O withstand provides the input-to-output reinforced insulation inside the approved component.
- Its creepage is covered by the approval: the data sheet does not state an internal creepage figure.
- On the system side, reinforced insulation is needed only between the mains harness and SELV parts (§4).

### 1.3 Why not (c), upsizing PS1

- **Room:** an 88 × 53 courtyard in PS1's corner displaces **7–10 parts besides PS1** (`free_space.py`, option (c)).
  - Best case: C21, C22, C23, C151, C152 (the resonant bank), C5 and H7 (a fixed enclosure standoff).
  - That is a tank re-floorplan, which re-opens F6, B3, Kelvin and D5.
- **Inlet:** it buys nothing. The same blower power reaches the inlet whichever module carries it.
- **Brown-out:** it keeps the blower start and stall on the logic rail, which is the coupling the owner wants removed.

(c) is rejected on all three counts.

### 1.4 Start-up inrush, stall and fusing

**Module cold-start inrush:**
- The inrush is 30 A typ at 115 Vac (PS1/PS2: 20 A typ, IRM-20-SPEC p.2).
- F2 is a 3.15 A time-lag fuse. If the inrush is modelled as a 2 ms half-sine, the I²t is ≈ 0.9 A²s, against the 0215 3.15 A part's melting I²t of 43.3 A²s (ratio 48; an ESTIMATE). If F2 ends up a UMT 250, re-check against its own I²t.
- F1 (KLDR025, Class CC time-delay) sees three module inrushes at power-on; that is not a new stress class.

**Blower start:**
- U2's high-side limit of 4.2–5.8 A (SLUSEA4D, via C28) bounds the 15 V draw at **3.9–5.3 A**.
- IRM-60's overload protection starts at 69 W = **4.6 A** (low corner, hiccup).
- So a hiccup is possible only if the blower draws > **5.0 A at 12.4 V (1.85 × Delta's maximum)** for longer than the module's OCP response.
- Delta does not specify start current. **Bench gate G-B1:** measure the start current and PS3's output at a full-voltage enable.
- Mitigations, in order:
  1. **Firmware:** enable at the drive floor (duty 100 % → 5.03–5.78 V), then ramp.
  2. **Hardware:** a larger C_SS on U2 (c_ss_12, 10 nF today). The writer computes t_ss from SLUSEA4D.
- At cold boot, PS3's own 30 ms rise time already ramps the input.

**Stall:**
- Delta's spec p.2: a locked rotor shuts the current down, so a stall is not a sustained overload.
- If the blower draws over the limit anyway, PS3 hiccups and recovers on its own.
- In every case the tach reads 0 Hz, and the existing L3 firmware path derates the tank.
- The logic rail (PS1) is unaffected by construction.

**Fusing:**
- **F2**, time-lag 3.15 A, in L only, on the power board ahead of J11.
- Steady input at the design load is 1.27 A at 108 V (40 % of F2).
- Candidates:
  - **Schurter UMT 250 3.15 A (3403.0171)**: SMD 10.1 × 3.1 mm, 250 VAC. Distributor data gives **200 A at 250 VAC breaking capacity**; confirm on Schurter's data sheet.
  - The HBC alternative, **Littelfuse 02153.15MXP**: 1.5 kA at 250 VAC, LCSC C142723, 3808 in stock. It does not fit on the board as a 5 × 20 in clips: `tap_spot.py` finds 0 spots for a 23.3 × 16.6 block. It would go in an in-line holder at the module end.
  - The TR5 372 is rejected: 35 A at 250 VAC breaking capacity (Littelfuse 372 data sheet, rev 10/10/16, p.2).
- **Open, certifier:** F2's breaking capacity is below the prospective fault current at the high-line corner (the same question as F1, DECISIONS 2026-10-08). F1 (Class CC) is the backup.
- **DC side:** no fuse is needed, because the module is LPS (p.1) and protects itself (p.2).

## 2. Power-board placement (native-21)

### 2.1 No room for the module (`free_space.py`, `enclosure_space.py`)

- **IRM-60/45 (87 × 52):**
  - **0** courtyard-free positions among 31,521 on the board.
  - **Least-displacing spot:** board (45, 145) on the SELV tongue. It displaces 26 SELV parts and covers 4,070 mm² of SELV copper.
  - **Its body also hits the UI board:** controls_ui_board's underside is at z 43.4, which leaves 15.8 mm of headroom over the board against 30.5 mm needed. This matches place.py's "≤ 22 mm for y > 160" tongue rule.
  - **Best main-body spot:** displaces 92 parts.
- **IRM-30 / IRM-20:** fit only on the tongue (60 / 536 free positions). Both are too small electrically and too tall for the tongue.
- **Option (c):** §1.3.

### 2.2 Mains tap J11 + F2 (`tap_spot.py`)

The only legal cluster on the board is to the right of PS1's AC pins (PS1.1 l_filt (255.8, 136.4); PS1.2 n_filt (255.8, 115.6)). It is under D3/D17 and left of H1.

**Block:** 12.9 × 14.2 mm (J11 over a UMT 250), centre **(266.5, 123.5)**, `out/tap-spot-umt.txt`. The distances below come from pour outlines, so they are lower bounds.

| Check | Distance |
|---|---|
| tap source (l_filt / n_filt) | 2.8 mm |
| SELV / PE / H1's earthed M3 head | 9.3 mm (≥ 8.0 D5; H1 is the only metal fixing, board_only21.json) |
| HOT (D3 / D17 / bus pours) | 3.4 mm (≥ 3.2) |
| other MAINS groups | 8.8 mm (≥ 3.2) |
| foreign copper under it | none |

**Poses (courtyard centres, KiCad frame, place.py convention):**
- **F2:** UMT 250, (266.5, 118.4), rot 0 (body along x).
- **J11:** B2P3-VH(LF)(SN), LCSC C160745, 2038 in stock. Courtyard centre (266.5, 125.8), **rot 0**, so the posts lie along x at 7.92 mm. Use J3's measured courtyard offset from parts.json when converting to the footprint origin.

**Nets:**
- l_filt → F2.1;
- F2.2 → new net **blw_l** → J11.1;
- n_filt → J11.2.

**Copper:** three short tracks (≤ 15 mm each) from PS1.1 / PS1.2 into the block, on the layers PS1's feed already uses. Width ≥ 1.0 mm, because F2 rather than F1 protects this branch.

**Move / re-route scale:** **no part moves**; three tracks, no pour edits. Fallback if the UMT block will not route: J11 alone fits at (266.5, 121.0) or (265.0, 128.0) (`out/tap-spot-header.txt`, 285 spots), with an HBC in-line fuse at the module end.

**Rule files:**
- `domains.py` MAINS_PREFIX: add `blw_l`.
- `write_rules21.py`: blw_l is **its own MAINS group**, like AC_L_IN against l_f, because F2 can open.

**SELV return / PE:**
- No SELV copper is added to native-21, and PS3's output never touches it.
- PS3 −V is referenced only at the controller (J13.2 → selv_gnd). The blower current returns on its own pair, and selv_gnd stays earthed through R_FE as today.
- No new PE bond.

### 2.3 Module location in the enclosure (`enclosure_space.py`, R39 catalog)

**Envelope:** IRM-60-15ST body + 2 mm + 10 mm of wire dress per terminal end. It is checked against every R39 solid, with native-21's real stage-15b bodies in place of its allocation envelope. Harness AABBs are reported, not treated as blocking.

**Result:** 1,139 clear grid positions. **All of them are over native-21's left/front strip or under the coil.**

**Best, outside the coil:**

| Item | Value |
|---|---|
| Orientation | flat, long axis y |
| Centre (world) | (−141.5, 69.5) |
| Envelope | x −170…−114, y 3…136, z 32.5–70 |
| Plan gap to the ferrite bars | +6.9 mm |
| Over native-21 | the tongue's left part and the strip between the board's left edge and the wall |
| Harnesses to re-dress | probe_M12_to_controller, fan_to_controller |

**Alternative:** flat, long-x, (−115.5, 118.5), which lies 3.6 mm inside the ferrite plan.

The floor spot at (6, 305–315) is under the coil centre and is rejected for coil field.

**Requirements for the enclosure team:**
- a bracket from the floor or left wall: the module must not sit on native-21;
- ≥ 5 mm air over native-21's tallest part below it;
- AC end facing J11's route, DC end toward the controller;
- module ambient ≤ 60 °C;
- ≥ 6 mm plan distance outside the coil ferrite;
- run board_in_enclosure / the R39 fit with the module solid.

## 3. Controller changes (branch `controller-layout`)

1. **`elec/src/controller.ato`:**
   - new `signal v15_blw` (net V15_BLW);
   - new `j_blw` = **J13**, JST **B2P-VH** 3.96 mm. VH is rated 10 A, 250 V (JST eVH.pdf p.1, as cited for J3). LCSC C20571196. Pins: p1 V15_BLW, p2 selv_gnd.
   - Move `u_12.VIN`, `r_en12_top.p1`, `c_in12a/b/c.p1` from v15_selv to v15_blw.
   - Add `c_blw_bulk` = Cap100u25Elec on v15_blw, beside U2's input. Its 25 V rating is above PS3's 20.25 V OVP maximum.
   - U2's EN UVLO now follows PS3, not PS1.
2. **Unchanged:**
   - U2's FB network (140 k / 11.5 k, 56.2 k + 12.1 k / 1 µF from GPIO46);
   - Q_FAN_OFF on EN from expander P15, with the 10 k gate pull-down;
   - the J10 pin map and the FG path.
   They reference selv_gnd and 3.3 V only, so the C28 fail-safe directions hold:
   - reset or MCU off → full speed;
   - expander still an input → blower on;
   - PWM stuck high → minimum speed, which the tach sees.
   - **New case:** PS3 missing → U2 off → tach 0 Hz → the existing L3 derate path.
3. **Optional:** a **BLW_PG** divider from V15_BLW into spare expander pin P16, so firmware can tell "PS3 absent" from "blower failed". The writer sizes it against the TCA9555 V_IH in controller_calcs.
4. **Layout:**
   - `layout/floorplan.py` places J13 at a board edge facing the module (left edge, near J4, preferred), with the bulk cap at U2.
   - The J13 → C_in → U2 → GND → J13 loop must not use J4's ground pins.
   - Route V15_BLW ≥ 1.0 mm (2.72 A), then route, DRC and silk.
5. **`tools/controller_calcs.py`:**
   - `blower_supply()`: VIN source = PS3, IRM-60-15, 15 V ±2.5 %.
   - Add `ps3_budget()`: 39.7 W of 60 W, derating at 50/60 °C, J13 VH rating, harness drop.
   - Split the PS1 budget so it excludes the blower.
6. **`tools/verify_controller.py`:**
   - `j4: pin1_feeds_both_bucks` **fails by design** after the split. Replace it with `pin1_feeds_3v3_buck_only`.
   - New `blwin` section:
     - `j13_pin_map`;
     - `u2_vin_en_caps_on_v15_blw`;
     - `no_part_bridges_v15_blw_and_v15_selv`;
     - `bulk_cap_on_v15_blw`.
   - `v3v3: ps1_within_21W_at_r32_blower_cap` becomes `ps1_within_21W_at_full_blower`, which now passes at 4.8 W plus the direct v15 loads.
   - Add `ps3_within_rating_at_design_load`.
   - `check_blower` (J10, FB, FAN_OFF) stays as it is and must still pass.
   - The J4 port checks are unchanged: J4's pinout does not change.
7. **`inputs/native-21/`:** re-import after the power-board source change (J11/F2 are new parts; J4 is unchanged), then rerun the port byte-equality checks.
8. **Documents:**
   - DECISIONS: amend C28 and close open item 13;
   - LAYOUT.md;
   - ENCLOSURE-HANDOFF.md: J13, the PS3 harness and the module allocation;
   - bom.

## 4. Harness

| Run | From → to | Wire | Connectors | Notes |
|---|---|---|---|---|
| **BLW-AC** (mains) | native-21 J11 → PS3 AC/L, AC/N | 18 AWG, mains-rated, 105 °C or better (the TCO harness class in R39-HARNESS-LIST) | JST **VHR-3N** (cavity 2 empty, as J3) + **SVH-21T-P1.1** (AWG 18–22; LCSC A3963-TP class); ferrules at the module's screw terminals | J11's world position is (125.5, 109.5); the module's AC end is at about (−142, 124). The run is ≈ 270 mm in plan, so the cut is ≈ 350 mm (estimate). **It crosses over native-21's SELV band and the controller area, so it needs reinforced insulation to SELV:** an insulated wire plus a glass-silicone sleeve, retained positively (IEC 60335-1 cl. 22–23, as R39 does for the NTC leads). Keep it ≥ the reinforced distance from SELV conductors and off the coil plenum. |
| **BLW-DC** (SELV) | PS3 +V/−V → controller J13 | **18 AWG** twisted pair | JST **VHR-2N** + **SVH-21T-P1.1** at J13; ferrules at PS3 | At 2.72 A: 450 mm loop = 18.9 mΩ, 51 mV, 0.14 W. AWG20 gives 81 mV, so AWG18 is chosen for start transients up to the 5.3 A bound. VH's 10 A rating covers both. XH (3 A with AWG22, eXH) would run at 91 % continuous, so it is rejected. |

- J11 (VH 7.92 mm, 2-position) and J13 (VH 3.96 mm, 2-position) cannot be cross-mated.
- J10 and the blower extension are unchanged (C28: AWG22 / XHP-3, 2.88 A ≤ 3 A).
- The enclosure regenerates its harness list (`build_harness_list.py`) with both new routes.

## 5. Inlet, nameplate and heat (`budget16.py`)

**Method:** the method in DECISIONS (2026-10-08 entry and its correction) and `input_limits.c`:
- I_aux is each module's typical AC current at 115 Vac, scaled to 108 V;
- hold = (13.5 − I_aux) / 1.1.

| Allowance | I_aux | Hold | Tank-side input at 120 V |
|---|---|---|---|
| today (2 × IRM-20 at full load) | 1.28 → 1.3 A | 11.1 A | 1239 W |
| PS3 at its 60 W rating | 3.19 A | 9.37 A | 1046 W (−193) |
| **PS3 at its 39.7 W design load (recommended static)** | **2.55 A** | **9.96 A** | **1111 W (−127)** |
| drive-scheduled: blower off / Delta typ / max | 1.28 / 1.88 / 2.55 A | 11.11 / 10.56 / 9.96 A | — |

- **The firmware must subtract PS3.** Today's `aux_max_a` = 1.3 A covers "both IRM-20 at full load" (input_limits.h) and does not include PS3.
- **Minimum change:** `aux_max_a = 2.55`; the host tests in `test_input_limits.c` change with it.
- **Better:** schedule the allowance with the commanded blower drive:
  - I_aux(d) = 1.28 + 1.92 × P_blower_in(d) / 60 W, using the fan-law drive the firmware already computes.
  - This recovers most of the hold at typical blower speeds.
- In both cases the bench qualification of e_est (the existing gate) applies, plus a true-RMS check of the three-module aux current.

**Physics check:** PS3's real input at the design load is 44.6 W. The RMS allowance is larger because a capacitor-input module draws peaky current; the linear-sum method is conservative.

**Cord and nameplate:**
- The total stays ≤ 15 A RMS, because the firmware still regulates the total inlet estimate to 13.5 A. Only the split between power stage and auxiliaries changes.
- The 120–127 V nameplate current is unchanged.
- The rated power input marking (IEC 60335-1 cl. 10) must be re-confirmed on the bench with the blower at full speed.

**Heat:**
- PS3 dissipates **4.9 W** at the design load (89 %). It sits in the front-left volume, out of the sink duct.
- PS1's output falls from 21 W (its rating ceiling) to 4.8 W, so its loss falls by ≈ 3.1 W, on the board, near C5/C6.
- **Net enclosure heat:** +1.8 W, moved off the power board.
- B3 sees PS1 cooler. That is not a new hot spot, so no B3 re-run is required (an optional confirmation is listed below).

## 6. Writer steps, gates and risks

Step order (P = power board unit, C = controller branch, E = enclosure, F = firmware). Re-opened evidence: **D5/barrier: re-run** (new MAINS copper). **Kelvin: no** (OCP path untouched; the regenerated band must still read 66.37–118.74 A). **B3: no** (optional confirmation). **F6: no** (no loop copper touched).

| # | Step | Gate |
|---|---|---|
| P1 | `elec/src/parts.ato`: `MainsTapHeader` (B2P3-VH, as TcoLoopHeader) and `BranchFuseT3A15` (UMT 250 3.15 A, or as chosen in §1.4). `power_stage_120v.ato`: f_blw (F2) l_filt → blw_l; j_blw_ac (J11) blw_l / n_filt. `audit.rs`: the tap sits after F1 and the filter; F2 is time-lag, ≤ 3.15 A, ≥ 250 VAC; blw_l is not SELV. | atopile build; verify_source; audit (77 + new tests); ERC |
| P2 | `domains.py` (blw_l → MAINS), `write_rules21.py` (blw_l own group), `place.py` put(f_blw (266.5, 118.4) 0; j_blw_ac (266.5, 125.8) 0), `measure_parts.py` / parts.json | place; rules writer (no UNCLASSIFIED) |
| P3 | `patches21.add_stage16`: three tracks from PS1.1 / PS1.2; silk "MAINS, BLOWER PSU FEED"; `native21-envelopes.json` J11 25 mm (as J3) | **DRC 0/0/0, parity 0**; **barrier21 + Rust gate 0**; **d5_audit** (HOT-SELV ≥ 8.047, H1 npth ≥ 8); Kelvin band unchanged; JLC DFM; Gerber review; fit (board_in_enclosure, R39 pose translate x0 −141) |
| P4 | DECISIONS item 15 (stage 16); final-manifest | hashes recorded |
| C1–C8 | §3 in order: source → calcs → verify → floorplan / route → DRC → fab → docs | verify_controller all PASS with the replaced j4 check and the new blwin / ps3 checks; DRC 0; JLC DFM; convergence 3/3 |
| E1 | IRM-60-15ST allocation and bracket (§2.3), both harness routes (§4), harness list regenerated, R39 fit with the module solid | 0 hits; bend rule; reinforced routing note for BLW-AC |
| F1 | `input_limits.c` aux (static 2.55 A or drive-scheduled); host tests; blower enable at the floor then ramp | host tests; hold recomputed in DECISIONS |
| G-B1 (bench) | blower start current and PS3 hiccup margin at a full-voltage enable; PS3 output ripple with the coil at 28 A (coil-edge field) | no hiccup; ripple within the buck's input range |
| G-B2 (bench) | true-RMS aux current of PS1 + PS2 + PS3 at full blower, 108 / 120 / 132 V; IEC 60335-1 cl. 10 input | replaces the 2.55 A allowance |

**Risks:**
1. **Enclosure volume is the critical path.** The only clear volume sits over the board's left/front edge, beside the M12 probe and fan harness. If the enclosure team cannot bracket it there, the fallback is a native-21 re-floorplan with the PCB module. That re-opens D5, Kelvin, B3 and F6 (§1.3, §2.1).
2. **Mains run over SELV:** the BLW-AC harness crosses over SELV areas and needs reinforced insulation and retention. Certifier review.
3. **F2's breaking capacity** is below the prospective fault current at 127 V + 10 %, with F1 as backup. Certifier, as with F1.
4. **Inlet hold:** −127 W at a static full-blower allowance. Drive scheduling recovers it at typical speed.
5. **Blower start current** is unspecified; the hiccup margin is 1.85 × Delta's maximum. G-B1.
6. **Coil-edge 31 kHz field at PS3:** +6.9 mm outside the ferrite plan. The module's immunity is tested only at 50/60 Hz (IEC 61000-4-8, p.2). G-B1.
7. **Stock:** IRM-60-15ST has 374 at DigiKey with a 17-week factory lead time and 0 at LCSC. Buy prototype quantities early. The fallbacks are in §1.2.

## Files

Scripts: `dump_board.py` (KiCad Python), `common.py`, `free_space.py`, `tap_spot.py`, `enclosure_space.py`, `budget16.py`, `board_map.py`, `jlc_lookup.py`.

Outputs in `out/`:
- `free-space.txt`
- `tap-spot.txt` (5 × 20 clips: 0 spots), `tap-spot-umt.txt`, `tap-spot-header.txt`
- `enclosure-space.txt`, `enclosure-space-z10.txt`
- `budget16.txt`
- `board-map-stage16.png`

Other folders:
- `jlc/raw/`: LCSC/JLC search cache, fetched 2026-10-12.
- `datasheets-local/`: Mean Well and Littelfuse PDFs, for reference only; do not commit.

Board model: from the unit's `native-21/section.kicad_pcb`, `layout/board_only21.json` and `layout/copper.json` (a831e90c). It uses pour outlines, not fills, so the copper distances are lower bounds.

Reproduce:

```
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
$KP dump_board.py board/dump.json
python3 -B free_space.py board/dump.json > out/free-space.txt
python3 -B tap_spot.py board/dump.json 12.9 14.2 > out/tap-spot-umt.txt
python3 enclosure_space.py 20 > out/enclosure-space.txt
python3 budget16.py > out/budget16.txt
python3 -B board_map.py board/dump.json out/board-map-stage16.png
```
