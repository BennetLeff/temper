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

The selected Würth 74650074 M4 terminals specify an **actual** 1.6–2.0 mm
PCB thickness. Nominal 1.6 mm does not establish the fabricated minimum;
confirm tolerance and THR reflow compatibility with the fabricator and
assembler before release. Wave soldering is not applicable to this terminal.

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
until RMS, peak/transient and high-frequency requirements are qualified,
including PE-open and external-earth cases. D5 conditionally approves
≥8.0 mm as a provisional placement floor with verified group IIIa-or-better
laminate; the certification lab and Coilcraft evidence remain open.

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
qualified working-voltage analysis, and record each lookup and its applicability
in `RULES.md`. The repository key `IIIa/IIIb` combines numeric values but does
not waive the standard's IIIb restriction above 50 V: specify verified IIIa
or better. D5 approves only an 8.0 mm provisional placement floor. Resolve
working-voltage/HF requirements before treating any distance as final.

| Boundary | Nets (A ↔ B) | Worst working voltage (from the design docs) | Insulation | Rule |
| --- | --- | --- | --- | --- |
| Controller ELV ↔ HOT | A in the audit's historical `SELV_NETS`; B live HOT | Not yet bounded; the rectifier does not cap DC-bus voltage at line crest | Reinforced objective; **≥8.0 mm provisional placement floor**, PD3, verified IIIa or better; D5-BASIS.md governs qualification | clearance and creepage |
| HOT ↔ PE | live HOT ↔ `pe`, which R38 functionally bonds to controller return | Not yet bounded; include open-PE/common-mode and tank cases | Do not retain an automatic basic-only exemption: review every HOT-to-PE path as a possible bypass of controller reinforced isolation. Use the ≥8.0 mm provisional PCB floor; qualify heatsink insulators and Y-capacitor paths separately | clearance and creepage |
| Line ↔ neutral before the bridge | `ac_l_in`, `l_f`, `l_filt` ↔ `ac_n_in`, `n_filt` | 140 V rms supply envelope; verify applicable abnormal/transient requirements | Functional, applicable table value | clearance |
| Tank nodes ↔ other HOT | `sw_a`, `sw_b`, `coil_feed`, `res_a`, `crbleed_*` ↔ other HOT nets | The former ~640 V peak is an estimate, not a bound | Functional; determine table 18 and HF applicability from qualified stress | creepage |
| Rectifier output ↔ downstream bus | `rect_p` ↔ `bus_p`; `rect_n` ↔ `hv_ret` at the removable J7/J8 and J9/J10 link pairs | Both rectifier output studs remain mains-live with links removed. The bench source connects only to J8/J10, after both links are physically open | Keep adequate assembled link-gap, PCB copper and lug insulation; verify isolation in both-link-open mode | clearance and assembly check |
| Bus ↔ low-voltage HOT | `bus_p` ↔ `hot5`, `v15_ls`, gate nets | The former ~200 V peak is not a bound during tank energy return | Functional; final band unresolved | clearance |
| Within each qualified low-voltage domain | — | ≤15 V only where the source establishes it | Provisional default; not an exemption for a domain crossing | 0.2 mm |


**Step 2, compare against each barrier part's own package creepage.** Read the
datasheet value for each part and fill this table in `RULES.md`:

| Part | Package | Datasheet external creepage (fill in) |
| --- | --- | --- |
| U1, U2 UCC21550BDWKR | SOIC-14 DWK | ___ mm |
| U9 ISO7710DWR | SOIC-16 DW, TI HV land pattern (8.1 mm pad gap) | ___ mm |
| U4 AMC1311BDWVR | SOIC-8 DWV | ___ mm |
| T1 CST3015-100ED | — | ≥ 8 mm (Coilcraft datasheet) |
| PS1 IRM-20-15 | module | Obtain internal insulation/certification scope; pin span alone is not package creepage evidence |

**If any package creepage is below the qualified controller↔HOT reinforced
value, STOP and report it before accepting the placement.** This is the
problem that left Rev38 with
104 unresolved barrier findings. Options to present:

- (a) Keep PD3 and move to wider-package parts, for example the ISO7710 in the
  DWW package. This is a source change: edit `parts.ato`, rebuild, re-audit.
- (b) Justify PD2 with an IEC 60664-3 coating or a sealed compartment. That's a
  certification-lab question; record it as OPEN.
- (c) Board slots under the part add board creepage only, **not** package-surface
  creepage. They don't solve (a) by themselves.

D5 has been conditionally decided for provisional placement. Keep the lab,
Coilcraft and high-frequency findings visible in the review package; a larger
qualified requirement requires redesign before release.

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
| Z1 Mains entry | `j_mains` J1, `f1` F1, `rv1` RV1, `cx1` C1, `rb1a` R1, `rb1b` R2, `l1` L1, `cx2` C2, `cy1` C3, `cy2` C4 | Cord-entry edge (D6): J1 → F1 → RV1/C1 → L1 → C2. C3/C4's PE pads go to separate J6, not J1. Their 10 mm-pitch local footprint has 1.5 mm pads and 8.5 mm nominal copper gap. Leave L1 retention space. |
| Z2 Rectifier + bus | `br1` BR1, `c_bus1` C5, `c_bus2` C6, `r_bus1` R3, `r_bus2` R4, `r_shunt` R5, `tvs_bus` D3, `c_hf_a1/a2` C38/C39, `c_hf_b1/b2` C40/C41, `link_pos.terminal_rect/bus` J7/J8, `link_neg.terminal_rect/bus` J9/J10 | BR1 at the heatsink edge. C5/C6 are 42 × 33 mm, 48 mm tall radials. Place C38/C39 by leg A and C40/C41 by leg B; BUS_P/HV_RET returns include R5, never LEG_RET. D3 spans BUS_P/HV_RET near bulk. J7↔J8 and J9↔J10 have external removable jumpers and no PCB joins. Preserve insulated jumper/lug envelopes. |
| Z3 Bridge legs | `leg_a.q_high` Q2, `leg_a.q_low` Q3, `leg_b.q_high` Q5, `leg_b.q_low` Q6; snubbers `leg_a.c_snub_h` C12, `leg_a.c_snub_l` C13, `leg_b.c_snub_h` C19, `leg_b.c_snub_l` C20; gate networks `leg_a.r_gh` R10, `leg_a.r_gh_pd` R11, `leg_a.r_gl` R12, `leg_a.r_gl_pd` R13, `leg_b.r_gh` R18, `leg_b.r_gh_pd` R19, `leg_b.r_gl` R20, `leg_b.r_gl_pd` R21 | MOSFETs standing on the heatsink edge. Each snubber **directly across its MOSFET's drain/source pins**. Gate resistors at the gate pins |
| Z3b Leg-A driver | `leg_a.driver` U1, `leg_a.d_boot` D1, `leg_a.c_vcci` C7, `leg_a.c_ls` C8, `leg_a.c_ls_bulk` C9, `leg_a.c_boot` C10, `leg_a.c_boot_hf` C11, `leg_a.permit_fet` Q1, `leg_a.r_permit` R6, `leg_a.r_permit_pd` R7, `leg_a.r_dis_pu` R8, `leg_a.r_dt` R9 | U1 ≤ ~25 mm from Q2 and Q3 gates, output pins (9–16) facing the MOSFETs. **C7, Q1 and R6–R9 are on U1's SELV side (pins 1–8)** and belong in or at the edge of Z6 |
| Z3c Leg-B driver | `leg_b.driver` U2, `leg_b.d_boot` D2, `leg_b.c_vcci` C14, `leg_b.c_ls` C15, `leg_b.c_ls_bulk` C16, `leg_b.c_boot` C17, `leg_b.c_boot_hf` C18, `leg_b.permit_fet` Q4, `leg_b.r_permit` R14, `leg_b.r_permit_pd` R15, `leg_b.r_dis_pu` R16, `leg_b.r_dt` R17 | Same as Z3b for Q5 and Q6. **C14, Q4 and R14–R17 are SELV-side** |
| Z4 Tank | `c_res1` C21, `c_res2` C22, `c_res3` C23, `r_crb1..4` R22–R25, `t_ct` T1, `j_coil` J2, `j_coil_return` J5 | Coil-exit edge (D6). T1 primary (pins 1, 2) sits between SW_A and J2 COIL_FEED; its secondary (pins 3, 4) faces the controller zone. The external coil spans J2 to J5 RES_A. Use separate M4 terminal/lug envelopes, initially ≥30 mm centers, then check actual high-frequency/fault insulation. R22–R25 span RES_A to SW_B beside the CDE bank. Earlier ~640 V peak was an example, not a bound. |
| Z5 HOT auxiliary | `ps_gate` PS2, `j_tco` J3, `u_ldo` U3, `c_v15` C24, `c_ldo_in` C25, `c_ldo_out` C26, `u_vsense` U4 (HOT side), `r_div1..4` R26–R29, `r_div_bot` R30, `c_div` C27, `c_vs1` C28, `u_ref` U5, `r_ref_bias` R31, `r_ocp_ref` R32, `r_ocp_sense` R33, `r_th_top` R34, `r_th_bot` R35, `c_ocp_node` C30, `c_th` C31, `u_ocp` U6, `c_ocp_vcc` C32, `r_ovp_top` R36, `r_ovp_bot` R37, `c_ovp_th` C33, `u_ovp` U7, `c_ovp_vcc` C34, `u_nand` U8, `c_nand_vcc` C35, `u_iso` U9 (HOT side), `c_iso1` C36 | Near R5: the OCP Kelvin sense (R5 pad 3) and the `leg_ret` star (R5 pad 2). U7 (OVP) reads `vsense_in` at R30/C27, so keep it next to U4. The R26–R29 string runs from `bus_p` toward U4, spreading the voltage along its length. PS2 away from the heatsink's hot air |
| Z6 SELV | `j_selv` J4, `ps_selv` PS1 (output pins 3, 4), `c_vs2` C29, `c_iso2` C37, plus the SELV-side parts of Z3b/Z3c, and the SELV pins of U1, U2, U4, U9 and T1 | A strip along one edge, separated from all HOT copper by the reinforced distance from 4.2. **C29 and C37 are SELV bypass capacitors** for U4 and U9's side 2; don't place them with Z5 |
| Z6b Functional earth | `j_pe` J6, `r_fe` R38 | Cord PE bonds directly to the chassis/heatsink stud; a separate branch lands on J6 Phoenix 1704004. R38 is the removable 0 Ω controller-return bond near J6. Keep pads, traces and hardware ≥8 mm from HOT provisionally. Neither J6 nor R38 carries the primary protective-earth path. |

Placement rules (check each one; list the outcome in `PLACEMENT-REVIEW.md`):

1. **Commutation loops:** C5/C6 and C38–C41 BUS_P → high-side drain →
   low-side source → R5 power pads → each capacitor's HV_RET. Keep area and
   inductance small. Record capacitor, MOSFET and R5 bounds and identify both
   local leg paths. Keep R5 Kelvin traces out of power copper.
2. **Gate loops:** driver output pin → gate resistor → gate → source/Kelvin → driver
   return. Record each loop's bounding box.
3. **Barrier:** draw a straight or stepped barrier line on `F.Fab` and `B.Fab` from edge to edge.
   Only the barrier parts may straddle it. Measure the minimum copper-to-copper
   distance across it.
4. **Heat:** MOSFETs and BR1 occupy the heatsink edge; snubbers and local
   capacitors must fit close enough for the measured loop target without
   overheating. Keep tall film capacitors and IRM modules out of exhaust;
   record airflow direction, which D2 has not selected.
5. **Heavy parts:** L1, C5/C6 and C21–C23 need retention and height checks;
   four-pin radial mounting alone does not prove vibration survival. Leave
   space for adhesive, straps or brackets as needed.
6. **Access:** F1 and J1–J10 must be reachable for intended wiring, with
   clearance for coil lugs and both removable bus jumpers. Check screws,
   lug orientations and insulation envelopes in the enclosure.

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
