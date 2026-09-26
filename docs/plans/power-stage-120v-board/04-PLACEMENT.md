# Part 4: stackup, insulation rules and placement (ends at owner review)

**Goal:** a placed, unrouted board, `native-02/`, where:
- every part is in a deliberate location
- the design rules encode the insulation and functional spacing
- DRC with those rules shows **zero** clearance, creepage and courtyard violations
- the owner has reviewed and approved the placement

**Placement is edited in `poses.json`, never by dragging parts in KiCad.** Every
change is regenerated through `tools/build_native.py`, so the board stays a
projection of the source.

**Preconditions:** Part 3 merged; `native-01` generation works.

## 4.0 Decisions: get them before placing anything

Create `zapote/power-stage-120v/DECISIONS.md`. Record the owner's answers to
D1–D3 from `00-INDEX.md`; ask if they aren't given. Add:
- **D5, insulation basis.** Filled in by step 4.2. Needs owner sign-off if a
  barrier part fails.
- **D6, cord entry side and coil lead exit side,** which set where the J1 and J2
  terminals sit. Ask the owner.

## 4.1 Stackup

Default (D3): 2 layers, 1.6 mm, 70 µm copper both sides. Write `stackup.json`:

```json
{"schema": "temper.power-stage-120v.stackup.v1",
 "status": "planning CAD stackup; not a fabricator approval",
 "board_thickness_mm": 1.6,
 "layers": [
  {"name": "F.Mask", "type": "Top Solder Mask", "thickness_mm": 0.01},
  {"name": "F.Cu", "type": "copper", "thickness_mm": 0.07},
  {"name": "dielectric 1", "type": "core", "thickness_mm": 1.44, "material": "FR4", "epsilon_r": 4.5, "loss_tangent": 0.02},
  {"name": "B.Cu", "type": "copper", "thickness_mm": 0.07},
  {"name": "B.Mask", "type": "Bottom Solder Mask", "thickness_mm": 0.01}]}
```

Extend `tools/build_native.py` to apply it after `build(...)`. **Adapt**, don't
copy blindly, the Rev38 function `apply_planning_stackup` in
`git show "archive/rev38-power-entry-2026-09-25:zapote/power-entry/passive-reva/protection/interface-integration-38/tools/build_native.py"`.
Change its expected layer-order list to the five layers above and its schema
string to yours. Keep:
- the part that adds the `SourceInstance` and `MPN` footprint properties
- the stable pad UUIDs
- the manifest hash update

**Check:** `cargo run --quiet --locked --manifest-path zapote/Cargo.toml --bin zapote-board -- <native>/section.kicad_pcb`
must now **pass** `DRC.BOARD.STACKUP`.

## 4.2 Insulation and spacing rules: numbers first

**2026-09-25 integration correction:** the numerical voltage entries below
are inherited planning estimates, not established worst-case working voltages.
The diode-clamp argument and the later 468/511 V bus estimates do not prove
those bounds; see `zapote/power-stage-120v/ORACLE-REVIEW.md`. Moving T1 to
SW_A removes its direct resonant-node connection but retains high-frequency
switch-node stress. Do not generate final insulation rules from this table
until D5 establishes RMS, peak/transient and high-frequency requirements,
including PE-open and external-earth cases. The ≥8.0 mm target and FR-4
material-group assumption remain provisional.

**Step 1, compute the required distances with the repo's own IEC 60335-1 tables.**
The Rust extension must be built (`make extensions`, Part 1):

```python
import temper_design_bundle_python as t
t.creepage_table_lookup(3, "IIIa/IIIb", ">130-250", "17").value_mm()   # basic, table 17
t.creepage_table_lookup(3, "IIIa/IIIb", ">250-400", "17").value_mm()   # repo uses x2 = 12.6 reinforced
t.creepage_table_lookup(3, "IIIa/IIIb", ">500-800", "18").value_mm()   # functional, table 18 (tank)
t.clearance_table_lookup(2500).value_mm()
```

Use **PD3**. The repo decided PD3 for forced-air cooking boards (see
`docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md` and the comments in
`scripts/generate_kicad_dru.py`). Pick each boundary's voltage band from the
worst-case working voltage below, and record every lookup result in `RULES.md`.

| Boundary | Nets (A ↔ B) | Worst working voltage (from the design docs) | Insulation | Rule |
| --- | --- | --- | --- | --- |
| SELV ↔ HOT | A in the audit's `SELV_NETS` list; B any other net except PE | Rails and switch nodes 99 V rms / 198 V peak; mains 140 V rms (T1 now on `sw_a`, so no SELV part faces the resonant node) | **Reinforced, uniform ≥ 8.0 mm** (PD3, IIIa/IIIb, >125–250 band), per D5 proposal in `zapote/power-stage-120v/ORACLE-ANSWER.md` | clearance and creepage |
| HOT ↔ PE | any HOT net ↔ `pe` | 140 V rms mains; tank nodes higher | Basic, at the matching band | clearance and creepage |
| Line ↔ neutral before the bridge | `ac_l_in`, `l_f`, `l_filt` ↔ `ac_n_in`, `n_filt` | 140 V rms | Functional (table 17 value) | clearance |
| Tank nodes ↔ other HOT | `sw_a`, `sw_b`, `coil_feed`, `res_a`, `crbleed_*` ↔ other HOT nets | up to ~640 V peak (`res_a`) | Functional, table 18 `>500-800` | creepage |
| Bus ↔ low-voltage HOT | `bus_p` ↔ `hot5`, `v15_ls`, gate nets | ~200 V peak | Functional | clearance |
| Everything else | — | ≤ 15 V | Default | 0.2 mm |

**Step 2, compare against each barrier part's own package creepage.** Read the
datasheet value for each part and fill this table in `RULES.md`:

| Part | Package | Datasheet external creepage (fill in) |
| --- | --- | --- |
| U1, U2 UCC21550BDWKR | SOIC-14 DWK | ___ mm |
| U9 ISO7710FDWR | SOIC-16 DW, TI HV land pattern (8.1 mm pad gap) | ___ mm |
| U4 AMC1311BDWVR | SOIC-8 DWV | ___ mm |
| T1 CST3015-100ED | — | ≥ 8 mm (Coilcraft datasheet) |
| PS1 IRM-20-15 | module | input/output pin distance from the MEAN WELL drawing |

**If any package creepage is below the required SELV↔HOT reinforced value, STOP
and ask the owner (decision D5).** This is the exact problem that left Rev38 with
104 unresolved barrier findings. Options to present:

- (a) Keep PD3 and move to wider-package parts, for example the ISO7710 in the
  DWW package. This is a source change: edit `parts.ato`, rebuild, re-audit.
- (b) Justify PD2 with an IEC 60664-3 coating or a sealed compartment. That's a
  certification-lab question; record it as OPEN.
- (c) Board slots under the part add board creepage only, **not** package-surface
  creepage. They don't solve (a) by themselves.

Don't continue placement near the barrier until D5 is decided. Placement of the
pure-HOT zones (Z1–Z4 below) may proceed meanwhile.

**Step 3, write `tools/write_rules.py`,** which writes `<native>/section.kicad_dru`:

- Read the net names from the generated board: the `(net N "name")` entries.
- Assign each net to SELV, HOT, PE, TANK, MAINS_IN or BUS **using the same lists as
  `audit.rs`.** If a net name in the audit isn't on the board, exit non-zero.
- Emit one KiCad custom rule per boundary above, with `(constraint clearance (min X))`
  and `(constraint creepage (min X))`, conditioned on explicit net-name lists
  (`A.NetName == 'v3v3' || ...`).
- **Validate the syntax** by running DRC: a rule-parse error appears in the report.
  Fix it until DRC runs clean of parse errors.

## 4.3 Placement

Edit `poses.json` (`[x_mm, y_mm, angle_deg]`, angle counter-clockwise, KiCad
convention), regenerate `native-0N`, apply rules, run DRC. Repeat.

**Zones.** Power flows from mains entry on one edge to the coil terminal:

Designators below come from the frozen build (`frozen/default.net`) and are
listed with their **instance paths**, which is what `poses.json` is keyed by.
Always place by instance path, and confirm the designator in
`native-0N/source-manifest.json` if the source has changed since.

| Zone | Instance path → designator | Rules |
| --- | --- | --- |
| Z1 Mains entry | `j_mains` J1, `f1` F1, `rv1` RV1, `cx1` C1, `rb1a` R1, `rb1b` R2, `l1` L1, `cx2` C2, `cy1` C3, `cy2` C4 | At the cord-entry edge (D6). Order along the current path: J1 → F1 → RV1/C1 → L1 → C2. C3 and C4 go straight to J1's PE pin. Leave room around L1 (90 g) for a strap or adhesive |
| Z2 Rectifier + bus | `br1` BR1, `c_bus1` C5, `c_bus2` C6, `r_bus1` R3, `r_bus2` R4, `r_shunt` R5 | BR1 on the heatsink edge (D2). C5 and C6 **within ~20 mm of the bridge legs**: they are the commutation capacitors. R5 between the low-side sources (`leg_ret`) and the C5/C6 negative terminals (`hv_ret`) |
| Z3 Bridge legs | `leg_a.q_high` Q2, `leg_a.q_low` Q3, `leg_b.q_high` Q5, `leg_b.q_low` Q6; snubbers `leg_a.c_snub_h` C12, `leg_a.c_snub_l` C13, `leg_b.c_snub_h` C19, `leg_b.c_snub_l` C20; gate networks `leg_a.r_gh` R10, `leg_a.r_gh_pd` R11, `leg_a.r_gl` R12, `leg_a.r_gl_pd` R13, `leg_b.r_gh` R18, `leg_b.r_gh_pd` R19, `leg_b.r_gl` R20, `leg_b.r_gl_pd` R21 | MOSFETs standing on the heatsink edge. Each snubber **directly across its MOSFET's drain/source pins**. Gate resistors at the gate pins |
| Z3b Leg-A driver | `leg_a.driver` U1, `leg_a.d_boot` D1, `leg_a.c_vcci` C7, `leg_a.c_ls` C8, `leg_a.c_ls_bulk` C9, `leg_a.c_boot` C10, `leg_a.c_boot_hf` C11, `leg_a.permit_fet` Q1, `leg_a.r_permit` R6, `leg_a.r_permit_pd` R7, `leg_a.r_dis_pu` R8, `leg_a.r_dt` R9 | U1 ≤ ~25 mm from Q2 and Q3 gates, output pins (9–16) facing the MOSFETs. **C7, Q1 and R6–R9 are on U1's SELV side (pins 1–8)** and belong in or at the edge of Z6 |
| Z3c Leg-B driver | `leg_b.driver` U2, `leg_b.d_boot` D2, `leg_b.c_vcci` C14, `leg_b.c_ls` C15, `leg_b.c_ls_bulk` C16, `leg_b.c_boot` C17, `leg_b.c_boot_hf` C18, `leg_b.permit_fet` Q4, `leg_b.r_permit` R14, `leg_b.r_permit_pd` R15, `leg_b.r_dis_pu` R16, `leg_b.r_dt` R17 | Same as Z3b for Q5 and Q6. **C14, Q4 and R14–R17 are SELV-side** |
| Z4 Tank | `c_res1` C21, `c_res2` C22, `c_res3` C23, `r_crb1..4` R22–R25, `t_ct` T1, `j_coil` J2 | Between the legs and J2 (coil-exit edge, D6). T1's primary (pins 1, 2) sits between `sw_a` and J2 pin 1 (`coil_feed`); its secondary (pins 3, 4) faces the SELV zone. The R22–R25 bleed string runs from `res_a` to `sw_b` alongside the C21–C23 bank, spreading ~640 V peak along its length |
| Z5 HOT auxiliary | `ps_gate` PS2, `j_tco` J3, `u_ldo` U3, `c_v15` C24, `c_ldo_in` C25, `c_ldo_out` C26, `u_vsense` U4 (HOT side), `r_div1..4` R26–R29, `r_div_bot` R30, `c_div` C27, `c_vs1` C28, `u_ref` U5, `r_ref_bias` R31, `r_ocp_ref` R32, `r_ocp_sense` R33, `r_th_top` R34, `r_th_bot` R35, `c_ocp_node` C30, `c_th` C31, `u_ocp` U6, `c_ocp_vcc` C32, `r_ovp_top` R36, `r_ovp_bot` R37, `c_ovp_th` C33, `u_ovp` U7, `c_ovp_vcc` C34, `u_and` U8, `c_and_vcc` C35, `u_iso` U9 (HOT side), `c_iso1` C36 | Near R5: the OCP Kelvin sense (R5 pad 3) and the `leg_ret` star (R5 pad 2). U7 (OVP) reads `vsense_in` at R30/C27, so keep it next to U4. The R26–R29 string runs from `bus_p` toward U4, spreading the voltage along its length. PS2 away from the heatsink's hot air |
| Z6 SELV | `j_selv` J4, `ps_selv` PS1 (output pins 3, 4), `c_vs2` C29, `c_iso2` C37, plus the SELV-side parts of Z3b/Z3c, and the SELV pins of U1, U2, U4, U9 and T1 | A strip along one edge, separated from all HOT copper by the reinforced distance from 4.2. **C29 and C37 are SELV bypass capacitors** for U4 and U9's side 2; don't place them with Z5 |

Placement rules (check each one; list the outcome in `PLACEMENT-REVIEW.md`):

1. **Commutation loop:** C5/C6 (+) → high-side drain → low-side source → R5 → C5/C6 (−).
   Keep the enclosed area small. Record the bounding box of the four MOSFETs, C5, C6 and R5 in mm².
2. **Gate loops:** driver output pin → gate resistor → gate → source/Kelvin → driver
   return. Record each loop's bounding box.
3. **Barrier:** draw a straight or stepped barrier line on `F.Fab` and `B.Fab` from edge to edge.
   Only the barrier parts may straddle it. Measure the minimum copper-to-copper
   distance across it.
4. **Heat:** nothing but the MOSFETs, BR1 and their snubbers within 10 mm of the heatsink edge.
   Keep the film capacitors and IRM modules out of the heatsink's exhaust path; record the assumed airflow direction.
5. **Heavy parts:** L1, C5, C6, C21, C22 need mechanical retention. Leave space for
   adhesive, a strap or a bracket, and note it.
6. **Access:** fuse F1 and terminals J1, J2, J3, J4 reachable for service and wiring.

## 4.4 Checks for each iteration

```sh
python3 tools/build_native.py native-0N --stackup stackup.json
python3 tools/write_rules.py native-0N/section.kicad_pcb
kicad-cli pcb drc --severity-all --schematic-parity --format json \
  --output native-0N/drc.json native-0N/section.kicad_pcb
cargo run --quiet --locked --manifest-path ../Cargo.toml --bin zapote-board -- native-0N/section.kicad_pcb
kicad-cli pcb export svg --mode-single --page-size-mode 2 --layers F.Cu,B.Cu,F.Fab,F.SilkS,Edge.Cuts \
  --output native-0N/placement.svg native-0N/section.kicad_pcb   # --mode-single: write one file at this path
```

**Exit criteria for placement:**
- schematic parity 0
- 0 `courtyards_overlap`
- 0 `clearance` and 0 `creepage` violations between pads
- the stackup gate passes

Unconnected items are expected (unrouted).

## 4.5 Owner review package, then **STOP**

Write `PLACEMENT-REVIEW.md` with:
- the placement SVG
- the zone map
- the measurements from rules 1–6
- the rules table with the lookup values
- D1–D6 as decided
- the list of anything PROVISIONAL

Commit and open a PR titled
`feat(power): power-stage-120v placement for review (unrouted)`.
**Do not start Part 5 until the owner approves the placement in writing.**

## Stop and ask if

- any barrier part's package creepage is below the reinforced requirement (D5)
- the parts can't fit within D1 while meeting the rules
- a rule value can't be derived from the lookup, for example because a band doesn't exist
- a placement requirement conflicts with the heatsink concept (D2)
