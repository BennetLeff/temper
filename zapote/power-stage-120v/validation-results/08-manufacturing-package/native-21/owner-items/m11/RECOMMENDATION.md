# M11: heatsink HOT↔PE insulation stack for native-21 (decision-ready recommendation)

Board: native-21 stage 11, rebuild SHA-256 `e85a4c82…` (the same build as D5-AUDIT). Enclosure: R25
(`output/temper-manufacturing-r25`, read-only). Date: 2026-10-08.

**Evidence classes.** MEASURED means computed from the board or the R25 model by a script in this folder.
CITED means taken from a datasheet or standard; the page is given. EST means an engineering estimate.

## 0. Verdict

1. **As built, the board and the R25 sink fail even basic insulation.**
   - The R25 sink base face is the plane of the board's rear edge. It spans Z 15.5–83, which covers the
     whole board thickness (Z 26–27.6).
   - HOT pours on all four layers come within 0.6 mm of that face. Every FET lead pad comes within 1.97 mm,
     and every BR1 pad within 2.6 mm.
   - Requirements: basic creepage is 4.0 mm (PD3, IIIa); reinforced creepage, the D5 floor, is 8.0 mm.
   - 39 of the 65 HOT copper items within 12 mm of PE are under 8 mm. MEASURED: `sink-paths.json`.
   - **No insulator choice fixes this.** The sink geometry has to change.
2. **Requirement: reinforced (or double) insulation HOT→sink.**
   - R38 bonds PE to the controller return.
   - D5-BASIS requires the HOT→controller barrier to stay reinforced with PE open. The sink is therefore
     part of that barrier.
3. **Recommended stack (no board change):**
   - **Insulator:** 2.0 mm AlN ceramic, in two tiles with non-conductive thermal compound on both faces. A
     tile 2.0 mm thick is reinforced insulation by measurement alone (IEC 60335-1 cl. 29.3.1).
   - **Pedestal:** an aluminium spreader bar ("pedestal"). Its lowest edge is ≥ 8.0 mm above the board top.
   - **Sink position:** the main sink base moves 8.0 mm back from the board edge.
   - **Clamp:** a stainless comb spring. It presses through a 3 mm glass-epoxy pressure strip and uses no
     tab screws.
   - **Thermal:** the interface is 0.40–0.63 °C/W per FET (conservative grease assumption) against D-36's
     ≤ 0.7 °C/W.
   - **Fit:** the board's 1.835 mm tab offset is almost exactly the stack thickness.
4. **Changes:**
   - **Enclosure:** set the sink back 8 mm, add the spreader bar, clamp comb and strip, and move the plenum end
     cap.
   - **BOM:** add 2 AlN tiles, the thermal compound, one GAP PAD HC 3.0 piece for BR1, the comb and the FR-4
     strip.
   - **Bench:** hipot at 3000 Vac for 60 s on the type sample and 2000 Vac for 1 s in routine production, plus
     a per-FET ΔT check.

## 1. Geometry as built (MEASURED)

`board_sink_geometry.py` (KiCad 10 pcbnew) → `board-sink-geometry.json`; `sink_paths.py` (shapely, net domains from
`native-21/layout/rules21.py`) → `sink-paths.json`. Board y = 0 is the rear edge, y < 0 beyond it. R25 pose:
world = (141 − x, 236 − y, 26 + z) (`src/electronics_r17.py`).

| Part | Body / tab face (F.Fab y) | Lead row | Pad edge to edge | Tab net |
| --- | --- | --- | --- | --- |
| Q5 (HS, leg B) | x 1.95–17.95, tab y = 1.835 | y 4.215, 5.45 mm pitch, 2.5 × 4.5 pads | 1.965 mm | bus_p |
| Q6 (LS, leg B) | x 19.95–35.95, 1.835 | same | 1.965 | sw_b |
| Q3 (LS, leg A) | x 42.05–58.05, 1.835 | same | 1.965 | sw_a |
| Q2 (HS, leg A) | x 60.05–76.05, 1.835 | same | 1.965 | bus_p |
| BR1 GBJ2510 | x 79.6–109.2, back y = 2.30 | y 4.6, Ø4.0 pads | 2.60 | plastic back (no metal) |

PE solids in R25 that face this edge:
- **Sink envelope:** X32..149 → board x −8..109. The base face is at y = 0, Z 15.5–83.
- **Plenum end cap** (R21 X31 wall): at x ≈ 110, running forward to y = 0.
- **Inlet hood wall:** it has no HOT copper within 12 mm.

**Nearest HOT copper to the sink face:**

| Distance | Copper |
| ---: | --- |
| 0.60 mm | F.Cu leg_ret, sw_a, n_filt; B.Cu sw_a, sw_b, l_filt; In1 rect_p, leg_ret; In2 bus_p, rect_n (pours run to the edge rule) |
| 1.965–1.969 mm | all 12 FET pads, including the gate pads, which are HOT |
| 2.60 mm | BR1 pads |
| 3.575 mm | leg_ret via at (40.9, 4.0) |
| 3.81 mm | gate and drain tracks on F.Cu |
| 7.58–7.85 mm | ocp_kelvin_p |

The plenum end cap is 0.60 mm from In2 rect_n and 3.14 mm from BR1 pad 4.

**Package geometry above the board:**
- Source: Infineon IPW65R018CFD7 Rev 2.0 p.12, PG-TO247-3 drawing Z8B00003327 rev 06. The package seats
  on the lead shoulders (b1 ≥ 1.60 and b2 ≥ 2.57 against the 1.5 mm drill).
- **Body bottom:** 3.85–4.50 mm (L1).
- **Exposed drain metal:** from 5.55–12.41 mm to 23.20–25.49 mm (D, D1, D2).
- **Plastic beside the metal:** ≥ 0.675 mm ((E − E1)/2 minimum).
- **Lead offset:** the leads sit 2.20–2.60 mm (A1) in front of the tab face. Lead pads at 1.965 mm from the
  edge are therefore unavoidable for a vertical TO-247 whose tab is at the edge.
- **Consequence:** PE metal can't sit beside the board edge at the height of the leads. The PE contact face
  has to start above the board, and the sink proper has to stand back from the edge.

## 2. Requirement per path

Standard text: IS 302-1:2008, India's identical adoption of IEC 60335-1, ed. 4.x era. It is the same OCR
artifact the repo already cites (312,769 bytes, SHA-256 `2695a4bc…`, `dl-is302/`). The governing edition
(D5-BASIS cites ed. 6/2020) and the Part 2 for this appliance are for the lab to confirm. **IEC 60664-1 itself was
not available.** IEC 60335-1 cl. 29 note 1 states that its distances derive from it (IS 15382-1 = IEC 60664-1).

**Why reinforced, not basic.**
- In IEC 60335-1, Class I logic normally allows *basic* insulation from live parts to earthed metal.
- Here, R38 makes the PE-bonded sink galvanically the controller return.
- D5-BASIS (owner-approved): "maintain the full HOT-to-controller reinforced insulation requirement with PE
  open … heatsink insulators must also be checked for bypassing that barrier … use the 8.0 mm provisional
  PCB floor there too."
- With PE open, a single failure of a basic-only tab insulator puts HOT onto the controller ground. **Design
  to reinforced.**
- If the lab later accepts an earthed-ELV (basic + PE) classification, the 2 mm AlN still complies. Only the
  distances below would halve (4.0 mm).
- **The geometry fix of §1 is needed either way:** 0.6 mm fails the basic 4.0 mm too.

**Inputs:**
- **Rated voltage:** 120 V. Table 15 row ii (> 50 ≤ 150 V), OVC II (cl. 29.1) → **1500 V rated impulse**.
- **Working voltage HOT→PE:** |rail − PE| ≤ Vbus + Vf. In normal operation that is 99 V rms / 198 V pk at
  127 V + 10 % (ORACLE-ANSWER Q2).
- **Bus up to ~400 V:** this is a fault/pumped-bus transient (OVP restart inhibit 280 V; RV1 clamp ≈ 460 V).
  Per ORACLE-ANSWER Q3 it governs clearance and component ratings, not creepage. The sensitivity case is
  shown.
- **Pollution degree:** PD3, the IEC 60335-2-6 cl. 29.2 default for cooking appliances
  (`docs/evidence/2026-07-30-pollution-degree-determination.md`). The sink sits in the forced kitchen-air
  duct, so PD3 is certain here.
- **Frequency:** the low-side tabs (Q3 sw_a, Q6 sw_b) switch at 33–40 kHz. The high-side tabs (bus_p) and
  BR1 carry the line frequency only.

| Path | Requirement (reinforced) | Source row |
| --- | --- | --- |
| **Through the insulator** (solid) | ≥ 2 mm thick, **or** ≥ 3 layers each passing the supplementary 16.3 test, **or** thermal assessment plus the 16.3 test | cl. 29.3, 29.3.1 b), 29.3.2, 29.3.3 |
| Electric strength (type test, 1 min, 50 Hz) | 2500 V (working ≤ 150 V); **3000 V** (working > 150 ≤ 250 V, footnote b); 2.4U + 2400 = **3360 V** if U = 400 V | Table 7 row iii; footnote b |
| **Creepage** round the pad edge, board-edge copper to the sink, leads | 2 × Table 17 row iii (> 125–250 V) PD3 IIIa 4.0 → **8.0 mm** = D5 floor. Group I surfaces: 6.4 mm. U = 400 V: 2 × 6.3 = 12.6 mm (not used: transient) | Table 17 row iii, cl. 29.2.3 |
| Creepage over ceramic | "For glass, ceramics and other inorganic insulating materials that do not track, creepage distances need not be greater than the associated clearance" | Table 17 note 2 |
| **Clearance** (leads, tab edge, board-edge copper, clamp) | Next impulse step 2500 V → 1.5 mm, + 0.5 mm because assembly affects the distance → **2.0 mm**. With a 400 V bus (cl. 29.1.5: + 202 V) → interpolated 1.70 + 0.5 = **2.2 mm** | Table 16, cl. 29.1, 29.1.3, 29.1.5 |
| Clamp hardware (metal touching PE) | Same as the rows above. Package mould compound is **not** credited: Infineon gives V_ISO "n.a." (p.3 Table 2) | — |
| BR1 body | GBJ case dielectric strength 2500 Vrms (Diodes p.1). That is ≥ the basic 1250 V test, but no thickness or creepage data is published → credit as **basic only** and add supplementary/reinforced insulation | Table 7 row i |
| Routine production test | 2000 Vac 1 s (double/reinforced, rated ≤ 150 V); dc alternative 1.5× = 3000 Vdc | Annex A, Table 19 |

**Basic, for reference:** clearance 0.8 mm (PD3 footnote) + 0.5 = 1.3 mm; creepage 4.0 mm; type test 1250 V.

**Not reproduced here (lab to confirm):**
- The IEC 60664-1 partial-discharge threshold (recurring peak > 700 V). The worst die transient is 470 V
  (DECISIONS 2026-10-08), so it would not apply.
- The IEC 60664-4 > 30 kHz field limits for thin solid insulation. With 470 V across 2.0 mm AlN, the peak
  field is 0.23 kV/mm; across K-10 0.152 mm it is 3.1 kV/mm (`stack-calc.txt`). The thick ceramic sits far
  below any thin-layer HF concern.

## 3. Candidate insulators: thermal cost vs D-36 (≤ 0.7 °C/W per FET)

**Losses** (task 03 round 3, scaled to the 22 A tank envelope):
- FETs: HS 7.38 W, LS 7.45 W.
- BR1: 28.35 W at 15 A (the task-03 bound), 21.0 W at the 11.1 A hold.
- Total sink load: 58.0 W.
- Tab area: 151–240 mm² (task 03, from Infineon p.12 E1 × D1 less the hole).

`stack_calc.py` → `stack-calc.txt` / `.json`:

| Candidate | t (mm) | Breakdown | Rcs per TO-247 (°C/W) | ≤ 0.7 | C tab→PE | 29.3 route | Source |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| SIL PAD K-10 | 0.152 | 6 kVac | 1.10–1.75 | no (D-18 rejected) | 33–52 pF | (c) only | Henkel guide p.62 table, p.60 |
| SIL PAD 1500ST | 0.203 | 3 kVac | 0.62–0.98 | no | — | (c) only | Henkel p.62 |
| HI-FLOW 300P | 0.10–0.13 | 5 kVac | 0.35–0.55 | yes | — | (c) only | Henkel p.51 |
| AlN 1.0 mm + 2 × compound | 1.0 | 14 kV (EST from kV/mm) | 0.08–0.12 opt / 0.37–0.59 cons | yes | 11.5–18.3 pF | (c) only | Kyocera AN216A p.1; DOW/Henkel |
| **AlN 2.0 mm + 2 × compound** | **2.0** | **28 kV (EST)** | **0.11–0.17 opt / 0.40–0.63 cons** | **yes** | **5.8–9.1 pF** | **(a) by measurement** | same |
| Al₂O₃ 2.0 mm + 2 × compound | 2.0 | — | 0.40–0.63 opt / 0.69–1.10 cons | no | — | (a) | k = 24 W/mK EST |

**Thermal inputs:**
- **AlN:** Kyocera Fineceramics Europe AN216A, 2023-04-03, p.1: k 150 W/mK, 14 kV/mm, εr 8.6, CTE 4.6 ppm/K,
  flexural strength 310 MPa. The resistance is modelled 1-D over the tab area, with no credit for lateral
  spreading (conservative).
- **Compound, optimistic:** DOWSIL TC-5622, Form 11-3087-01 C p.1: 0.06 °C·cm²/W at 25 N/cm², 0.02 mm bond line.
- **Compound, conservative:** Henkel TIC 1000A p.41 gives 0.32 °C/W in the TO-220 fixture. The TO-220 test
  area is ≈ 0.2 in² (EST, inferred from the p.62–63 tables: K-10 0.41/2.01, SP400 1.45/6.61). That gives
  0.17–0.27 °C/W per interface.
  - TIC 1000A and TIC 4000 themselves are **excluded**: "electrically conductive filler" (p.41–42 note 1).
    Squeeze-out would bridge the ceramic's creepage.
- **Interface definition:** Rcs is the D-36 "interface", i.e. the insulator plus both contacts.

**Junction screen:**
- The spreader bar plus its greased joint adds 0.016 °C/W, shared by the whole sink (EST: 8 mm 6061-class
  Al over 117 × 47 mm).
- With R_SA = 0.237 °C/W (R25 model, 22.7 CFM), the sink runs at Ts = 64.7 °C at 50 °C inlet.
- Worst low-side FET: Tj = 71.5 °C on 2 mm AlN (conservative compound).
- BR1: 82.5 °C at 15 A.
- **The 0.7 °C/W budget is met with 0.07 °C/W to spare at the conservative end.** The absolute
  temperatures are far from limits, because task 03's losses omit switching terms. D-36's budget is the
  binding check, not Tj.

**Why 2.0 mm AlN and not a thinner insulator:**
- **Compliance:** a 2 mm tile is reinforced by cl. 29.3.1 on a caliper reading. A thin layer (K-10, 300P,
  1 mm AlN) is reinforced only through the lab's cl. 29.3.3 thermal-assessment and test route.
- **Thermal cost:** 2 mm costs 0.04 °C/W more than 1 mm.
- **Geometry:** the 2.04 mm stack (tile plus two 0.02 mm bond lines) fills the board's existing 1.835 mm tab
  offset. The leftover 0.205 mm puts the pedestal face just beyond the board edge.
  - A thin film would put the PE face 1.7 mm over the board, directly above the leads.
  - From the lead tops (z 3.85, y 3.77) to the pedestal edge is then only 4.6 mm unless that edge rises to
    ≥ 11.6 mm. At that height the pedestal misses the lower tab metal.
- **EMI:** tab→PE capacitance falls about 5.7× compared with K-10 (5.8–9.1 pF against the 32–52 pF task 03
  gave A7). This helps the task-07 CM budget; it was modelled with the K-10 range.

## 4. Recommended stack

The cross-section is at a FET, in the y–z plane. y is measured from the board edge (positive toward the
board); z is the height above the board top.

```
 z (mm)                         sink base face at y = -8.0 (world Y244)  ← set back 8 mm
  55 ┤      ║pedestal 7.8 mm Al║   comb-spring screws at z ≈ 40–45 (≥14 mm above tab metal)
  32 ┤  AlN ║                  ║ ← tile top: tab-metal top (≤ 25.5) + 6.0 overhang
     │  2.0 ║                  ║    FR-4 pressure strip 3 mm on the package fronts, z ≈ 9–23
  8  ┤      ║__________________║ ← pedestal lower edge z_s = 8.0
  0  ┼──AlN foot on board────────── board top; HOT pours to y = 0.6, lead pads from y = 1.965
     y: -8.0      -0.205  0  1.835 (tab)  4.215 (leads)
```

### 4.1 Paths for this stack (MEASURED, `sink_paths.py` → `sink-paths.json` "proposed"; all ≥ 8.0 mm)

| Path | Length | Floor |
| --- | ---: | ---: |
| F.Cu edge pour (y 0.6) → along the tile foot joint → up its outer face → pedestal edge | 8.77 mm | 8.0 |
| B.Cu edge pour → round the board edge → pedestal edge | 10.37 mm | 8.0 |
| B.Cu / In1 / In2 edge copper → set-back sink base (plan view) | 8.60 mm | 8.0 |
| FET lead pad (y 1.965) → joint → pedestal edge | 10.13 mm | 8.0 |
| Tab-metal end edge → tile end → round 2.0 mm thickness → pedestal | 6.0 + 2.0 = 8.0 mm | 8.0 |
| Tab-metal top edge → tile top → pedestal | 8.0 mm | 8.0 |

Notes on the paths:
- **Tile joint:** where tile A meets tile B (x = 39.0, in the 6.1 mm Q6–Q3 gap), the path is
  3.725 + 2.0 + 2.3 = **8.0 mm**. That needs a **5 mm relief groove in the pedestal under the joint** (x 36.5–41.5).
  The groove lies entirely behind the gap between the bodies, so it costs no contact area under any tab.
- **Clearances** are at least as long as these paths, because the tile foot blocks the straight line.
- **Margin:** each path has ≥ 0.6 mm over 8.0 mm, except the two overhang rows, which sit exactly at 8.0 by
  construction. Specify 6.5 mm on the drawing for a 0.5 mm tolerance.
- **Ceramic surfaces:** they would need only the 2.0 mm clearance (Table 17 note 2). The 8.0 mm D5 floor is
  applied anyway, because the creepage paths also cross the package plastic, solder mask and compound.

### 4.2 Parts

| Item | Specification | Notes |
| --- | --- | --- |
| **Tile A** (Q5, Q6) | AlN ≥ 150 W/mK, **2.00 ± 0.05 mm**, both faces lapped, flatness ≤ 0.03 mm, 0.3 mm edge chamfer, no holes; **x −4.0 … 38.75, z ≈ 0.2 … 32** (42.75 × 31.8 mm) | Kyocera AN216A class (or Maruwa/CoorsTek/SAM equivalents); custom cut, **quote required** |
| **Tile B** (Q3, Q2, BR1) | same; **x 39.25 … 113.0** (73.75 × 31.8 mm) | Differential expansion against Al over 76 mm and 50 K: 0.07 mm (CTE 4.6 vs 23.6 ppm/K EST). The compound lets it slip; no hard stops at both ends |
| **Thermal compound**, both faces | Non-curing, **metal-oxide-filled, electrically non-conductive** silicone. Candidate DOWSIL TC-5622 (4.3 W/mK, Form 11-3087-01 C p.1). **Hold:** the TDS gives no dielectric/volume-resistivity figure, so get it from Dow before release | Not TIC 1000A/4000 (conductive filler, Henkel p.41–42). Screen-print 0.02–0.05 mm; wipe squeeze-out off the tile edges |
| **BR1 gap filler** | GAP PAD HC 3.0, 0.508 mm (0.020"), 3.0 W/mK, > 5000 Vac (Henkel p.12), between the BR1 back face (y 2.30) and tile B (y 1.835) | Rcs BR1 ≈ 0.38 °C/W total (EST). Case (basic, 2500 Vrms) + 2 mm AlN → more than reinforced |
| **Spreader bar (pedestal)** | 6061/6082 Al, **7.8 mm thick**, x −8 … 109, z **8.0** … ≥ 48 above the board top; contact face flat ≤ 0.03 mm, Ra ≤ 0.8 µm. 5 mm relief groove at x 36.5–41.5; bolted and greased to the sink base | Adds 0.016 °C/W shared (EST). Alternative: an extrusion with a ≥ 12 mm base, milled to the same lower land |
| **Clamp** | Stainless (1.4310) **comb spring**, one finger per device, screwed to the bar at z ≈ 40–45 (≥ 14 mm above any tab metal). It presses through a **3.0 mm FR-4/G-10 pressure strip** (CTI ≥ 175, IIIa; RTI ≥ 130 °C) lying on the package fronts at z ≈ 9–23 | **No screw through the TO-247 hole and no metal on the package.** 3 mm laminate is reinforced by cl. 29.3.1 between the PE finger and the package. Mould compound is not credited |
| **Clamp force** | **≥ 60 N, target 80 N per TO-247** (25 N/cm² → 38–60 N, 50 psi → 52–83 N over 151–240 mm²); **≈ 100–150 N on BR1** (EST, 25 N/cm² over its 585 mm² back face) | Infineon's 60 N·cm screw torque (p.3) does not apply to a clip; tune the fingers to the force |

## 5. What it changes

**Board: nothing required.**
- The tab offset (1.835 mm) is kept on purpose: it is the insulator stack. Update RELAYOUT L13's "tabs
  flush/proud" to "tab plane y = 1.835 = 2 mm AlN stack" and record the change in DECISIONS.
- Optional at the next re-spin:
  - Move BR1 by −0.465 mm in y to put its back on the FET tab plane, deleting the gap pad.
  - Pull the HOT pours inside the sink span back from 0.6 to ≥ 1.0 mm for more margin (not needed for
    8.0 mm).

**BOM additions:** 2 AlN tiles, the thermal compound, 1 GAP PAD HC 3.0 piece (≈ 32 × 22 mm), the
spreader bar, the comb spring with 2–3 M4 screws and serrated washers, and the 3 mm FR-4 pressure strip.

**Enclosure (R26):**
- **Sink set-back:** move the sink envelope 8.0 mm rearward (Y236..284 → **Y244..292**), with its inlet hood
  fin-tip cover, the plenum (now Y292..) and the **X31 plenum end cap**. The cap is now 0.6 mm from In2
  rect_n; after the move it sits ≥ 8 mm from the board edge.
- **Spreader bar:** add it at Y236..243.8, Z ≥ 35.6 world (board top 27.6 + 8.0). Nothing PE may sit within
  8 mm of the board edge below Z 35.6.
- **Re-runs:** the enclosure fit gate, the R21 airflow/system-curve model (the plenum is 8 mm shorter), and
  the sink-NTC/TCO positions.

**Bench and lab:**
- **Type test (lab):** run on the clamped sink assembly with the tiles and the FR-4 strip, FETs and BR1
  fitted. Fit C3/C4, or remove them and test them separately.
  - Electric strength HOT (all power nets tied) → sink: **3000 Vac, 60 s** (Table 7 reinforced, working
    > 150 ≤ 250 V), or **3360 Vac** if the lab takes U = 400 V.
  - Repeat after the cl. 19 abnormal tests and after thermal cycling. Look for tile cracking.
  - Measure creepage and clearance on the assembly against §4.1 with 2 N on bare conductors (cl. 29.2).
- **Routine (production):** **2000 Vac, 1 s** HOT→PE (Table 19, reinforced, rated ≤ 150 V), or 3000 Vdc.
  With C3/C4 fitted, the ac leakage is about 3.3 mA at 2000 V, 60 Hz (EST, 2 × 2.2 nF), inside the 5 mA trip.
  Use dc if the margin is tight.
- **Thermal:**
  - BENCH-PLAN P2: add a thermocouple on each tab top edge and one in the pedestal behind each device.
  - Accept **Tcase − Tpedestal ≤ 0.7 °C/W × P_device** at full power.
  - Confirm that the clamp force is within 60–100 N per TO-247 with a load cell on a dummy package.
- **Inspection:** tiles intact (dye or visual) after assembly and after thermal cycling; no compound on the
  tile edges.

## 6. Open items and risks

- **Standards:**
  - The governing edition (ed. 4.x text here, ed. 6 in D5-BASIS) and the cl. 29.3 routes are for the lab to
    confirm.
  - The earthed-ELV vs SELV classification decides reinforced against basic.
  - Neither changes the recommended hardware.
- **Compound:** its dielectric data (Dow) is still to come.
- **AlN tiles:** price, lead time and an edge-chip acceptance criterion need a quote.
- **Contact area:** for a package with the shortest metal (D1 = 13.08 mm), up to 2.45 mm of the tab-metal
  bottom lies below the pedestal edge (z_s 8.0 against 5.55). That part depends on spreading in the AlN.
  The 1-D thermal model gives it no credit; the bench ΔT check covers it.
- **BR1:** it overhangs the R25 sink span end by 0.2 mm (x 109.2 against 109). This is thermally negligible.
  Tile B extends past it to x 113.
- **Airflow:** moving the sink 8 mm changes the R21 airflow path; the model needs a re-run.
- **Brittle insulator under spring load:** the specified flatness (≤ 0.03 mm, tile and bar) is the main
  failure-mode control.
- **Sink sensors:** the SELV sink NTC and the TCOs on the sink are fine, because the sink is PE/controller
  potential.

## 7. Files and sources

**Scripts** (folder `m11/`):
- `board_sink_geometry.py` → `board-sink-geometry.json`
  (`…/KiCad.app/…/python3 board_sink_geometry.py ../s11/section.kicad_pcb board-sink-geometry.json`).
- `sink_paths.py` → `sink-paths.json`
  (`PYTHONDONTWRITEBYTECODE=1 python3 -B sink_paths.py ../s11/copper-dump.json board-sink-geometry.json sink-paths.json`).
- `stack_calc.py` → `stack-calc.txt`, `stack-calc.json`.

**Datasheets:**
- Infineon IPW65R018CFD7 Rev 2.0 (2021-04-19), p.3 and p.12; SHA `c364050a…`.
- Diodes GBJ2510 DS21221 Rev 11-2 (May 2025), p.1, 2 and 4; SHA `c7d96577…`.
- Henkel Thermal Interface Selection Guide (2017), printed pp.12, 41–42, 51, 60–63; SHA `6a739a3e…`.
  These three are in `validation-results/03-loss-thermal-budget/round3/sources/`.
- Kyocera Fineceramics Europe AN216A (2023-04-03), p.1; SHA `aecb8af7…`; `dl-kyocera/`.
- DOWSIL TC-5622 TDS Form 11-3087-01 C (2017), p.1; SHA `ff7032e7…`; `dl-dow/`.

**Standard:** IS 302-1:2008 (IEC 60335-1), SHA `2695a4bc…`, `dl-is302/`. Clauses used: 16.3 and Table 7;
Table 15; 29.1, 29.1.3, 29.1.5 and Table 16; 29.2, 29.2.3, Table 17 rows iii and iv and note 2; 29.3,
29.3.1–29.3.3; Annex A, Table 19.

**Project:** D5-BASIS.md, D5-AUDIT.md, REVIEW M11, DECISIONS (D-18 2026-10-03, D-36, the 2026-10-08
envelope and input-current entries), ORACLE-ANSWER Q2/Q3, task 03 round 3, R25 `src/electronics_r17.py`,
`electronics_r21.py` and `inputs/native-21/native21-plan.json`.
