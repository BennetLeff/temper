# Enclosure re-layout: power-board requirements checklist

The enclosure work will move parts of the power board. This page collects
every requirement the simulation campaign has put on that re-layout, so that
nothing decided in [DECISIONS.md](DECISIONS.md) is lost when copper moves.
Each row links to its evidence. Start from **native-20** (values current as of
2026-10-05).

## Circuit changes to implement in the re-layout

| # | Requirement | Why / evidence |
| --- | --- | --- |
| L1 | **F6 negative gate bias:** a **TCO-switched HOT-side supply** (on `TCO_L`, referenced to `leg_ret`) feeds the low sides directly (+15 V, −2 V shunt-regulated split) and one SN6507-class driver with two functional-isolation high-side transformers. The −2 V rail stays more negative than −1.6 V at the edge, with ≥ 2.2 µF + 100 nF local reservoir at each driver VSS in a low-ESL loop. 1 nF Cgs and 1 Ω + PMEG6030EP per gate; rail-window monitor gating DIS; bootstrap network removed; HOT5 from a low-Iq LDO with a star return to R5.2 (DECISIONS 2026-10-06, revised) | S4/S5 fail without it; `f6-vneg` sensitivity sets the −1.6 V limit |
| L2 | Keep **R34 = 10.6 kΩ RT0603BRD0710K6L** and **R8/R16 = 330 Ω** | Shunt-OCP band and gate-off delay ([native-20](native-20/README.md)) |
| L3 | Keep **R9/R17 = 49.9 kΩ ±0.1 %** (443 ns nominal dead time) | F7, native-18 |
| L3a | **Line zero-cross detector:** reinforced AC-input optocoupler from L_FILT/N_FILT (resistor string sized for 120 V +10 %), output `LINE_ZC` on J4.16 (replacing one SELV_GND; re-check the D-20 return allocation) | Bursts need line crossings; the bus holds its peak when idle (DECISIONS 2026-10-06) |

## Layout rules

| # | Rule | Why / evidence |
| --- | --- | --- |
| L4 | **Shunt Kelvin return:** the lead from **R5.2** into the HOT island carries all HOT-side supply current (≤ 21 mA) and sets the OCP trip error (each 10 mA across 0.1 Ω lowers the trip by ≈ 1 A). Either widen/parallel it to ≤ 50 mΩ, or star-return the AMC1311, the MC78L05 and the ISO7710 to R5.2 separately from the threshold divider (R35) and the reference (U5) | [kelvin/](validation-results/02-protection-timing/kelvin/README.md): today −2.19 A of trip shift, band 47.54–97.98 A |
| L5 | **Gate loops and power loops at least as tight as native-19.** The decision margins depend on the power-to-gate mutuals (M13/M14/M23/M24) and on the power-loop self-inductance; leg B's power loop is already larger than leg A's | round-17 d2 README; leg B S4 VDS 537 V without F6 |
| L6 | Keep C38–C41 local bus capacitors at their pads (ESL 1.06 nH typical) | D-7 |
| L7 | Do not change stackup or the FET footprints without re-running the FET geometry check | `leg_region_diff.py` flags |

## Enclosure items that touch the board

| # | Requirement | Evidence |
| --- | --- | --- |
| L8 | Forced-air sink RθSA ≤ 0.15 °C/W, ≥ 20 CFM, ≤ 1.0 °C/W per FET interface; dedicated duct coil → mains; fans on their own SELV 12 V supply | DECISIONS 2026-10-03 (cooling) |
| L9 | Reserve the 20 A DM + CM inlet filter module (110 × 80 × 50 mm, 8 W), out of the sink exhaust | DECISIONS 2026-10-05 (EMI) |
| L10 | Controller 3.3 V rail: power-board DC subtotal **41.657 mA** (native-20) | task 06 `interface_numbers.py` |

## Enclosure fit in R4 (D-36, `validation-results/01-switching-parasitics/round17/delegation/out-D36/`)

| # | Constraint | Why |
| --- | --- | --- |
| L11 | Outline 290 × 140 mm at R4 x −149…141, y 96…236, plus a 91 × 50 SELV tongue at world x 50…141, y 46…96 (decision 2026-10-08, M10); board bottom Z 26 ± 1 | Only band that fits between the front module, the sensor corridor and the coil legs; native-20's 240 × 160 fits nowhere |
| L12 | No part > 50 mm above the board bottom | Coil support plate at Z 85 |
| L13 | BR1 + four TO-247 in one rear-edge row within x 35…141 (≈ 106 mm), order right→left Q2, Q3, Q6, Q5, BR1; tabs flush/proud | Sink right of the sensor corridor; D-18 airflow order |
| L14 | Keep-out for the sink 114 × 50 × 73 (x 35…149, y 236…284, Z 10…83) and for the ducts (inlet x 149…183; exhaust x 35…95 to the rear wall) | 0.24 °C/W at 20 CFM / 0.21 at 30 CFM (model) |
| L15 | Mains entry and coil terminals on/near the rear edge outside the sink span (J4 sits on the tongue's front edge: decision 2026-10-08, M10); enclosure connectors on the rear wall | Owner: connectors at the rear |
| L16 | Fan ≈ 30 CFM at ≈ 140 Pa (60 × 38 high-pressure or blower, from a published curve); MOSFET interface ≤ 0.7 °C/W | D-18 hard limit with margin |
| L17 | Re-run `validation-plan/enclosure-fit/fit_gate.py --mode plan` on native-21's STEP | Release gate |

## After the re-layout (gates before any bench power)

1. `leg_region_diff.py native-20 → new board`. Any CHANGED leg means a FEM
   re-extraction of that leg (`campaign.py`; delete field files after each
   matrix).
2. Re-run the decision grids (S1/S2/S4/S5, both legs, F6 deck with PMEG6030EP)
   on the new matrices: `round17/d2/f6_legs.py --diode pmeg --temps 27,100,150`
   for both `--cases decision` and `--cases startup`.
3. Re-run `kelvin_plane.py` and `kelvin_budget.py` on a new copper export;
   the band minimum must stay ≥ 44 A.
4. Source audit (`audit.rs`), DRC with schematic parity, and ERC, as for native-20.

Bench work on native-20 before the re-layout lands: [validation-plan/BENCH-NATIVE20-ADDENDUM.md](validation-plan/BENCH-NATIVE20-ADDENDUM.md).

## Firmware requirements arising from the same decisions

- 180° fixed phase only; no phase shift (F9 closed by decision).
- Low power by line-synchronous half-cycle bursts with **T_burst ≥ max(2 s,
  4.6·d^3.2/0.65^3.2)**, 20 s default ([flicker screen](validation-results/07-conducted-emi/flicker/README.md)).
- On native-20 (unipolar drive): continuous operation only, until the
  first-edge capture passes (DECISIONS 2026-10-05, F6 addendum).

## Production shrink (native-22)

Added 2026-10-27. The owner approved shrinking in the production re-layout. The prototype lot stays s53, unchanged.
Evidence: `output/temper-power-shrink-native22/` (floorplan, transplant-proxy B3 thermal gate, README). Board
frame = s53's KiCad frame; the power core keeps its s53 coordinates. **Do not route before the go/no-go list in
that README is met.** Dependency tags: **[CERT]** certifier answer, **[INLET]** inlet-module design, **[AIR]**
bench board-face h (DECISIONS 69), **[R45]** enclosure revision R45, **[PART]** part choice.

| # | Requirement | Why / evidence | Depends on |
| --- | --- | --- | --- |
| S1 | **Outline 218 × 140 mm rectangle, no tongue** (30,520 mm², 68 % of s53). Smallest the floorplan packer fits: 210 × 140 (J1N at the far end of the rear band, longer L/N lanes, C5/C6 hotter, see S7). Height stays 140: the SELV island and J6 already sit at y 126–138. Replaces L11 (and its tongue) for native-22 | `results/floorplan_native22_218.json`, `results/width_scan.json` (218 recipe A, 210 recipe B) | [R45] |
| S2 | **These parts leave for the D-22 inlet module:** J1, F1, RV1, C1, C2, C3, C4, R1, R2, L1, PS2, J3 (TCO loop), F2, R130, J11 (5,386 mm² of board courtyard). The module now carries the cord terminal, F1 (and its I²t check, today 0.993), the MOV, every X and Y cap (the whole touch-current budget, today 0.2412 mA of 0.25), L1 *and* its own CM / DM stages (the ≥ 100 µH per-line DM inductor is still unselected), PS2 with its local-air limit (80.2 °C at 7.08 W) and the TCO loop, and the blower tap. Heat it takes from the board: L1 1.29 W and PS2 1.35 W at the release case, plus ≈ 0.34 W of line copper, on top of D-22's 8 W allowance (≥ 10.6 W; F1 and R130 not quantified). Size grows by ≈ 8,300–10,800 mm² of carrier [EST] beyond D-22's 110 × 80 × 50 mm. Replaces L9's size and heat | `results/inlet_module_budget.json`; `c23-supply-topology/MODULE-REQUEST.md`; DECISIONS 50, 74 | [INLET] [CERT] (F1, Y caps, J1 items move from the board packet to the module) |
| S3 | **Two new board inputs from the module:** J1N (L_FILT / N_FILT, 13.5 A firmware line bound; J1's Phoenix MKDS 5/2-9.52 footprint) on the rear edge beside BR1's AC pins (x 111–131), and J3N (V24_RAW / N_LS, PS2's output, HOT and TCO-switched; J3's JST VH footprint) on the right edge. The LINE_ZC string R67–R70 takes L_FILT / N_FILT from J1N. J6 + R38 (PE functional bond) stay on the board | floorplan JSON `new`; DECISIONS 2026-10-06 (TCO cuts all gate drive) | [INLET] |
| S4 | **J4 on the main body's front edge** at x 43–72, y 130–140, inside the SELV island; C176 and TP19 move aside; R146 and the J4 transfer caps sit beside it. The harness leaves 50 mm further back than from the tongue: re-check the 74 mm lead and the "in front of the Nomex barrier" condition (M10's reverse condition) | floorplan JSON; DECISIONS 2026-10-08 M10 | [R45] |
| S5 | **Power core rigid at s53 poses, and its copper copied, not re-routed:** FET row Q5/Q6/Q3/Q2 + BR1 on the rear edge (L13), HF film row C38–C41 (L6), R5 and its Kelvin (L4), gate and F6 networks, U1/U2, bias reservoirs, bias islands. Gate: `leg_region_diff.py` s53 → native-22 must show both legs UNCHANGED, else FEM re-extraction and the F6 decks (L5, L7) | floorplan keeps 398 parts at s53 poses; DECISIONS 2026-10-08 / 2026-10-17 power-loop entries | — |
| S6 | **Tank rigid at s53 poses:** bank C21–C23 / C151 / C152 (both footprints), bleed string R22–R25, T1, studs J2 / J5 with a 10 mm stud keep-out for the upturned lugs | DECISIONS M6 amendment; OPEN-ITEMS S25 / S28 unchanged | — |
| S7 | **C5 / C6 on the rear band** (x 131–218, y 0–34), D3 / D17 / R3 / R4 on the right strip, on the In1 HV_RET / In2 BUS_P planes. **New thermal flag:** their advisory case row (TDK Top,max 105 °C) reads 105.6 °C for the hotter cap (C6) at 28 A, h 16 + jets, against 93.9 °C for s53's hotter cap (C5), and 87.7 °C against 80.8 °C at 17.5 A still air; on the 210-wide variant it is 116.7 °C. Phase 1 must keep them out of the FET-row / BR1 hot field or give them flow; OPEN-ITEMS S8 (28 A only at cap ambient ≤ 80 °C) gets harder | `results/thermal_gate.json` advisory rows | [AIR] [R45] |
| S8 | **FET row / sink interface unchanged in geometry** (L13, L14, M11 setback): production sink S8 (DECISIONS 2026-10-09 R32 item 1). Insulator: the prototype keeps the 2 mm AlN tiles. Production follows the insulation-basis study: if the lab accepts basic insulation to a protectively earthed sink, use a HI-FLOW 300P-class film or thin catalogue ceramic (≥ 4.0 mm creepage over organic film) and re-run the CM EMI model with the higher switch-tab capacitance; if it does not (R38 read as functional earth on SELV), keep the AlN or remove R38. Interface ≤ 0.7 °C/W (L16) either way | `output/temper-insulation-basis-r1/README.md` §3, §5 | [CERT] |
| S9 | **Creepage / clearance:** 8.0 mm HOT ↔ SELV / PE on every layer (D5-BASIS provisional floor); RES_A ≥ 12.6 mm to SELV / PE on outer layers; PE branch ≥ 8 mm from HOT. Floorplan audit: min HOT–LOW pad gap between different parts 8.17 mm; moved / new parts 8.27 mm; nearest moved SELV pad to RES_A outer copper 40.4 mm. If the lab reads coil-lane working voltage as crest-RMS, coil lanes need 7.4 mm and RES_A 6.3 mm (board-wide) | floorplan JSON `barrier_audit`; D5-BASIS; review-packet-s53 gate 5 | [CERT] |
| S10 | **Thermal basis (B3 on the transplant proxy, same code and settings as s53, bay 61 °C, I_line 13.5 A, hot copper):** 17.5 A release case, still air (h 10): worst gated margin **+0.2 K** (R10) against s53's +1.3 K; h ≈ 10.4 W/m²K restores +1.3 K. 28 A (S24 jets + base h): needs **h ≥ 16.2** (s53 15.4) on the FET-row laminate row; the DECISIONS 69 pass rule then asks nominal ≥ 1.2 × h_req. **Requires plane copper (In1 HV_RET / In2 BUS_P) poured across the vacated rear band from the FET row to C5/C6:** with those cells bare the needs rise to h 11.2 (17.5 A) and 18.0 (28 A). Proxy, not a routed board: re-run B3 on the routed native-22 before release | `results/thermal_gate.json`, `results/b3_*.json` | [AIR] |
| S11 | **R_on 2 W class for R10 / R12 / R18 / R20** (recommended, not required by S10): lifts the still-air margin to +3.4 K (laminate 1 mm block then binds). No part chosen; goes through the DECISIONS 54 gate-network checks | `results/thermal_gate.json` `*_ron2w` | [PART] |
| S12 | **Mounting holes:** H5–H8 and H10 keep their s53 places; H1, H3, H4 (R43 standoffs) move to (213, 135), (4, 125), (206, 49); H2 and H9 (empty in R43) are dropped. R45 adds bosses to match | floorplan JSON; DECISIONS 76 | [R45] |
| S13 | **Rows above that still apply unchanged:** L1–L3a (built), L4, L5–L7, L8, L10, L12 (≤ 50 mm), L13, L14, L15 (J1N / J3N on the rear and right edges; J4 on the front edge), L16, L17 (fit gate on native-22's STEP, in R45), and the four "after the re-layout" gates. L9 → S2, L11 → S1 | this file | — |
| S14 | **Hand-routed only:** every lane written explicitly in a native-22 layout source forked from `native-21/layout/` (explicit copper as in `route21.py` stage 1 and `patches21.py`); no Freerouting, no autorouter. s53 core copper is copied, not re-generated | owner rule; README §6 | — |
