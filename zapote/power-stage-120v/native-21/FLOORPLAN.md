# Native-21 floorplan (layout stage 1, Claude, 2026-10-06)

Board **290 × 140 mm**, 4 layers (native-20 stackup). In the R4 enclosure it
sits rotated 180°: the board's **top edge (KiCad y = 0) faces the enclosure
rear**, and its left edge (KiCad x = 0) is at world x = 141 (right). Board
frame below is KiCad: x right, y down, mm. World = (141 − x, 236 − y).
Source: D-36 (`round17/delegation/out-D36/`, RELAYOUT-REQUIREMENTS L11–L17).

## Area budget

Courtyards total ≈ 20,200 mm², 50 % of the board (`/area budget` in the
layout log). Largest: PS1/PS2 53 × 28, C5/C6 43 × 34, L1 46 × 30,
C21–C23 47 × 28, T1 24 × 33, RV1 24 × 24, F1 38 × 9, C1/C2 27 × 12.

## Zones (KiCad frame)

| Zone | Board x | Board y | Contents | Why |
| --- | --- | --- | --- | --- |
| **Sink row** | 0 – 106 | 0 – 8 | Q5, Q6, Q3, Q2, then **BR1** (106 mm), tabs at y ≈ 1.6, flush with the edge | Sink span world x 35…141 (L13). BR1 moved from native-20's far left to after Q2, so airflow (inlet world right = board left) passes the FETs before BR1 (D-18 order), without mirroring any footprint |
| **Power core** | 0 – 115 | 8 – 62 | native-20 core rows kept: gate R/hold-off under each gate pin, snubbers, R5 between the low-side sources, C38–C41 HF row, U1/U2 straddling the SELV island edge, F6 network (Cgs, PMEG + 1 Ω) at each gate, bias reservoirs (2×10 µF + 2×1 µF + 4×100 nF + 220 µF/0.68 Ω) **at each driver's VSS pins** | Gate loops per ECO L1. **Commutation loops measured, not carried over** (FEM 2026-10-08, FINDINGS M11): the film row sits 6 mm lower for F6, so leg A's parallel loop rises 24.9 → 37.6 nH at the reference, while leg B's falls 29.1 → 24.5 nH (C41 pulled in). Both legs pass all 252 F6 cases on the provisional matrices |
| **HS bias A / B** | 0 – 115 | 62 – 95 | SN6507-fed transformers T2/T3, rectifiers, LC filter, TPS7A47 split + TLVH431, rail monitor (LM339, TL431, ISO7710 straddling the island edge) per high-side domain, each a compact island referenced to its own switch node | HS domains swing with sw_a/sw_b: keep each island small, beside its driver, with functional creepage to its neighbours |
| **SELV island** | 30 – 160 | 62 – 125 | J4 (harness exits the rear via a short pigtail), U9/U4 SELV halves, CT comparators U10–U13, DIS ORs, BIAS_BAD filter, LINE_ZC buffer, PS1 secondary side | One island with an 8 mm moat (D5); every crossing part (U1, U2, U4, U9, U32–U34, U36, T1, PS1) straddles its edge |
| **HOT protection** | 106 – 160 | 8 – 60 | U3 HOT5 LDO, U5/U6/U7 OCP/OVP, U8 NAND, U14/U15 HOT5 monitor, R30–R37 dividers, on OCP_KELVIN_P with a **star return to R5.2** (L4) | Kelvin budget; short lead from R5 |
| **Mains / rectifier** | 106 – 290 | 0 – 60 | J1 at the top edge (rear), F1, RV1, C1/C2 X2, L1, C3/C4 Y1, link terminals J7–J10, C5 bulk, D3 TVS; BR1 adjacent at the row end | Mains enters at the rear (owner, D-36 L15) and flows L1 → BR1 → bus |
| **Tank** | 160 – 290 | 60 – 140 | T1 CT, C21–C23 resonant bank, bleed string R22–R25, C6 bulk, coil terminals J2/J5 at the top edge | Coil leads exit rearward (L15) |
| **Supplies** | 160 – 290 | 95 – 140 | PS1 (SELV), PS2 IRM-20-24 (TCO_L), J3 TCO loop, J6 PE, SN6507 driver + snubbers | AC-DC modules away from the gate loops; PS1 straddles the SELV moat |

Every connector that leaves the board (J1, J2, J5, J3, J6, J4 pigtail) is on
or near the top edge, outside the sink span x 0–106 (L15).

## Open choices settled here

- **BR1 at the downstream end** keeps D-18's FET-first airflow. The BR1-first
  alternative would cost 7 % of the RθSA limit (0.2697 vs 0.2915 °C/W at a
  1.0 °C/W interface, D-18).
- **C41 and the outer HF capacitor** move from the row ends to the HF row
  under the FETs, so nothing overhangs the 106 mm row. Leg B's commutation
  loop is re-extracted anyway (native-21 FEM).
- Bulk C5 moves from the board's left edge to the mains zone (right of BR1).

## Stage 3 re-floorplan for routing (2026-10-06)

Routing showed the stage-1 floorplan could not carry its power copper: BR1's pin order
(RECT_P, L_FILT, N_FILT, RECT_N) sits at the end of the sink row, so mains, rectifier,
bus and both switch nodes all had to leave through the 30 mm under BR1, and the bring-up
link studs were 30 mm apart instead of the strap's 13.0 mm pitch (ASSEMBLY.md). Changes
(`layout/place.py`):

- **Link block** right of BR1, 2 x 2 at 13.0 mm: J9 (RECT_N) - J10 (HV_RET) on the edge
  row, J7 (RECT_P) - J8 (BUS_P) below; straps horizontal.
- **PS2** on the rear band (x 160-213), **J3** beside it, **F1** 4 mm right.
- **Protection** below the BR1-gate lanes (x 101-121.5, y 51-75); **LS block** under it.
- **Coil terminals** beside T1: J5 (RES_A) over J2 (COIL_FEED), 15 mm apart (5 mm tank
  rule); coil leads drop from the plate above (it covers board y <= 79).
- **Resonant bank** C21-C23 stacked at x 153-200 (RES_A pins left, SW_B right), **C5/C6**
  4 / 2 mm right; tank bleed chain across the top of C21; bus divider in the corridor
  between U1's SELV moat and the LOW blocks.

Copper lanes (`layout/route21.py`): F carries N_FILT over SW_A, B carries L_FILT over SW_B
(mains and switch nodes each a stacked pair), In1 / In2 carry RECT_P / RECT_N to the links
and the HV_RET / BUS_P trunk (stacked) from the core's bottom exit to J8/J10 and C5/C6.

### Further placement fixes found while routing

- **T2 / T3** turned 180°: their LOW primaries face the core (fed along In1), their SW secondaries
  face the islands.
- **PS1** turned so its SELV end faces a SELV/PE spur (x 205-216.8) joined to a bottom SELV
  corridor (y >= 131) back to the SELV band; Y caps C3/C4 and the LINE_ZC opto U36 straddle the
  spur, the zero-cross string sits between C5 and D3. **F1** turned (line clips toward J1),
  **RV1** turned (L_F pin up). Bus divider and coil terminals nudged; island and LOW-block pack
  gaps widened to 0.55-1.1 mm.

## Stage 3 routing method (`layout/route21.py`)

1. **Explicit copper:** power lanes and pours, gate networks, snubbers, shunt pads and the
   Kelvin pair, HV chains (bounded pad escapes, as native-20), the SN6507 feeds, PS2's LOW feeds,
   the LS-rail lines along the core plane's bottom band, mains input, stud lands.
2. **Rail planes** per island (reference plane on In1; In2 free for signals inside islands and
   the LOW blocks), with a via beside every pad (`fanout`).
3. **Local and remaining connections** joined pair by pair inside chosen corridors; a grid
   search (`maze21.py`) finds bends, every result is checked against all authored copper.
4. **Insulation:** KiCad DRC with `section.kicad_dru` (per layer), plus the D5 barrier in
   **plan view over all layers** — enforced while authoring (`geom21`/`maze21`, pours clipped
   at creation) and checked on the filled board by `layout/barrier21.py` on every build.
   (The first routed passes had 779 plan-view pairs under 8 mm that per-layer DRC could not
   see; the gate now holds this at 0.)

Build: `sh native-21/layout/copper_iter.sh` (placement → board → rules → copper → fill + DRC →
barrier → plots); `layout/make_todo.py` turns the remaining ratsnest into the next pass's pairs.

### Incremental stage (`layout/incr21.py`, `layout/patches21.py`)

Full rebuilds re-route ~800 connections from scratch and the leftover set moves between runs
(32 open one build, 43 the next), so the last good build is frozen as `layout/copper_base.json`
and finished incrementally: `sh native-21/layout/incr_iter.sh copper_base.json DRC.json`
applies the base, then `patches21.py` (hand fixes: base items removed, explicit copper added),
then joins only the pairs KiCad still reports open. A bare pad attaches to any copper of its
net, not only the pad KiCad named. The summary now prints **plane splits** (zone-to-zone
ratsnest) separately from stray pins.

Fixes made this way (each in `patches21.py` with its reason):

- **HV_RET core plane was cut in four.** The Kelvin pair's In1 wedge ran from R5 (inside the
  LEG_RET region, which meets the board edge) to the bottom band, and C63's Cgs slot sealed off
  C41. So leg A's caps and the trunk had no copper path to the shunt. Now the pair leaves R5 on
  In1 as a dead-end notch to the C40/C38 gap, changes to In2 below the R5 / FET antipad row (also
  a notch from one edge), and rejoins its In1 band route. C63.2 reaches the LEG_RET via on In2.
  Earlier builds counted this as ordinary ratsnest.
- **Trunk bridge.** PS2's N_LS / V24_RAW feeds have to cross the In1 trunk band (F/B there carry
  the mains lanes). Their In1 L cuts the core plane off the bulk-cap leg (C5/C6), so an HV_RET
  pour on F and B beside the cut (203.5-226 × 52.5-75) joins both In1 pieces through 1.6 mm vias.
- **SELV spur.** The In1 HV_RET / In2 BUS_P planes were poured before the spur and cleared only
  the SELV pads, which pinched the opto's SELV pins shut. The spur plus 8.2 mm is now cut from
  them and the spur's SELV planes are re-poured.
- **LINE_ZC string re-folded** (place.py): each LED node sits beside its opto pin, so neither
  LED net crosses another string node at 3.2 mm.
- **SELV reference planes kept whole.** The router had put more than 600 mm of SELV signals
  (V15_SELV, LINE_ZC-RAW, CT_SENSE_MON, BUS_FAULT_ISO, BIAS_*) on In1/In2 along the band. That
  sliced V3V3 / SELV_GND into strips and cut the isolator pocket columns off. Those nets are now
  on F/B, and remaining SELV pairs try F/B before the inner layers.
- **U34 / U2 pockets:** the SELV long runs are re-laid after the pin vias and the short pin-to-pin
  nets, instead of hugging the pin rows.
- **Protection / LS-monitor pins boxed in by their neighbours** (HOT5 LDO output U3.5, U8's
  logic, the U9 / U4 / U32 isolator HOT pins that may only leave upward, R91.2, R29.2): each gets
  an explicit escape or via first. The leg-A SELV pocket's empty corner above U32 is cut back.
  The neighbours are re-laid as ordered groups (`route_group`: failures move to the front).
- Incremental pairs are **cumulative** over every DRC of the series. Ends are matched by
  connectivity clusters built from KiCad's *filled* pours of the previous build (`FILLS=`). Pour
  outlines overstated connectivity, and joining "any copper of the net" could land on an orphan.
- **Placement fixes found while routing (stage 4):** the TPS7A47 NR/SS caps (C81, C74) now sit
  beside pin 14; the packer had put them about 35 mm away. The rail monitors' 5 V LDOs moved to free
  island spots. U32 (LS-monitor isolator) moved 3 mm right, which widened the SELV neck below the
  leg-A pocket from 1.3 to 4.3 mm.
- incr21 reconciles placement changes against the frozen base. Copper that served a moved part's old
  pads, and chains left dangling by that, are dropped; pours are re-clipped to the plan-view
  barrier around moved pads; island rail pours (N_HA / N_HB) are protected from later tracks.
- Leg-A N_HA: U1.14 and its decoupling cluster get vias to the B bank above the LOW band (OUT_L's
  In1 run moved to y 34.7 to open the only legal spots).
- **Leg-A high-side -2 V block** (C50/C51, C90/C91, C110-C113, C126, R51, R71 under U1):
  - The packer interleaved N_HA and SW_A pads in alternating columns.
  - With vias banned across the In1 LOW band, every F escape for one net cut another.
  - Fix: R71 moves to (75.6, 34.6) beside U1.16's column, just below C39's courtyard. P_HA rises
    straight to it and its SW_A end meets the feed from above.
  - The block's N_HA / SW_A / damp copper is then re-laid F-only as one group: N_HA to a B-bank
    via at (74.8, 30.7), SW_A to the feed.
- **Long SELV runs as one ordered group** (BIAS_BAD, PWM_LA/HB, PERMIT, the BIAS_*_BAD nets and the
  F/B-only SELV set, with the leg-A pocket's local nets). BIAS_BAD's U22.2 leaves under U22's body,
  where PWM_LA used to run.
- Status: **fully routed: 0 unconnected, 0 DRC errors, 0 plan-view barrier violations, 0 plane
  splits**, on two consecutive builds (from 32 / 0 / 0 / 3 hidden splits in the frozen base).
### Accepted plane slots and through-plane vias (core planes In1 HV_RET / In2 BUS_P)

None of these splits a plane: the build counts zone-to-zone ratsnest as a plane split on every
run, and that count is 0. Their inductance effect belongs to the FEM rerun on this copper (task 01).

| Where | Layer | What | Why it is acceptable |
| --- | --- | --- | --- |
| Bottom band of the core plane (y 38.5-47, x 0.6-121) | In1 | LS rails (N_LS / LEG_RET / V15_LS), Kelvin pair, SN6507 T-lines | Runs along the plane's lower edge, not across the switching loops (FETs at y 4 to caps at y 28); LOW group = HV_RET's group, 0.2 mm |
| Kelvin pair, R5 to the C40/C38 gap | In1, then In2 | Dead-end notches, one per plane | Each cuts from one edge only; the earlier straight In1 wedge cut the plane in two and was replaced |
| OUT_L leg A, (56,31) to (82,37) | In1 | Interior slot along y 34.7 | Below the bus caps, parallel to the cap-to-FET current; moved from y 33.6 to open the N_HA via spot |
| C56.2 Cgs source to the LEG_RET region | In1 | Slot x 46.4, y 12.2-23.3 | Ends on HV_RET copper (C38.2); no split |
| C63.2 Cgs source to R21.2's via | In2 | Interior slot | The In1 version sealed off leg B's C41 piece; on In2 it is a hole in BUS_P |
| PS2 N_LS / V24_RAW feeds across the trunk | In1 | Cut of the trunk band | Bridged on F and B beside the cut (203.5-226 x 52.5-75) with ten 1.6 mm vias |
| Gate-source and Cgs vias through the core | all | Antipads in HV_RET / BUS_P | Planes are protected against tracks only; vias open antipads |

- **Stage 5 (2026-10-08):**
  - Post-route cleanup (incr21): 68 vias moved off SMD pads, 20 same-net drill clashes merged,
    dangling chains and single-layer vias pruned.
  - Reference labels: 272 on silk at the JLC legend minimum, 75 on F.Fab only (no clear spot).
  - Generated schematic: ERC 0 errors, DRC schematic parity 0.
  - Rust barrier gate: 0.
  - Re-run fit gates found the bias-bank electrolytics' bodies 0.15 mm into the 1210s; fixed in
    the bank template (body collisions 0, board in R4 0 hits).
  - Kelvin OCP band on this copper: 47.51-97.98 A.
  - Manifest: `verification/final-manifest.json`.
- **Stage 6 (2026-10-08):** the board current screen (task 04 round 5) found R5's current pads fed through
  two (HV_RET) and three (LEG_RET) 0.3 mm vias, up to 18 A in one via. `layout/patches21.py` (base =
  stage-5 copper; the stage-4/5 record is `patches21_v1.py`) adds legal 0.6/0.3 vias, 7 in R5.4 and
  10 at R5.1, filled and capped in the pads. It clips SW_B's B.Cu outline under R5, where its fill was
  0 mm². The worst via falls to 7.3 A (coherent 34 A case). DRC, parity, barrier (both gates), DFM
  and plane splits are all 0 / PASS; the Kelvin band is unchanged.
  Also in stage 6: SW_B's B.Cu tank lane widened from 4.4-5.6 to 7.2-9.3 mm over x 58-74 (SW_A's B.Cu link
  pour trimmed to y <= 12.5; the Cgs/R71 return via moved to (73.1, 15.2)). Tank-path screen and the 22 A
  RMS tank ceiling: task 04 round 5 README, DECISIONS.md 2026-10-08.
- **Open items:**
  - **44 vias** remain mostly inside SMD pads (the straight-stub dogbone found no spot within 1.3 mm;
    a routed-stub trial moves 15 more, 28 stay; R5's current pads need in-pad vias anyway). **Decided
    2026-10-08:** order every 0.3 mm via epoxy-filled and capped (JLC POFV); see DECISIONS.md.
  - **2 oz via rule (2026-10-08):** JLC's 0.254 mm ring is the PTH rule; vias need diameter >= hole
    + 0.1 mm, so the 0.6/0.3 signal vias stand (DFM gate PASS). A trial upsize to 0.72/0.2 could not
    re-route the LS bias block: the block is at 84 % courtyard area, its size-sorted row-pack
    scatters each IC's parts (IC-to-satellite runs of 12-30 mm), and functional sub-packing needs
    about 4 mm more height than the block has. If a future change needs more routing room there, the
    lever is 0402 for its low-voltage passives (an ECO through the source), then a functional pack.
  - Accepted warnings: 6 short dangling stubs, 20 silk-over-copper, PS1/PS2 outline silk at the
    board edge (2) and J3/PS2 outline silk (2). Nudging PS1/PS2/J3 broke the mains-entry escapes
    and the PS1/C4 courtyards. The 199 `lib_footprint_issues` are the project's unconfigured
    stock-library table.
  - FEM extraction and decision reruns (task 01): setup and coarse mesh gates done, solves pending
    remote access.
- Router: a final whole-corridor maze pass for long detours, and circumscribed clearance
  buffers. Polygonal buffers fell 0.04 mm short at the 8 mm barrier, more than the 0.03 mm
  margin, so found paths failed the exact check.

## Next stages

2. `prototype-closure/pcb/build_native21.py`: generate the unrouted board from
   native-21/frozen + `native-21/placement.json`, then DRC for courtyards,
   barrier and creepage pre-checks, and the fit gate on its STEP.
3. Power copper: BUS_P / HV_RET / LEG_RET planes, switch-node pours, bias
   rail loops.
4. Signal routing, then DRC, barrier gate (`tools/barrier_check.py`), audit
   parity and the release gates.
