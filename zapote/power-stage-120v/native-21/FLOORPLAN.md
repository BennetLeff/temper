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
| **Power core** | 0 – 115 | 8 – 62 | native-20 core rows kept: gate R/hold-off under each gate pin, snubbers, R5 between the low-side sources, C38–C41 HF row, U1/U2 straddling the SELV island edge, F6 network (Cgs, PMEG + 1 Ω) at each gate, bias reservoirs (2×10 µF + 2×1 µF + 4×100 nF + 220 µF/0.68 Ω) **at each driver's VSS pins** | Proven gate and commutation loops; rail model ≤ 0.5 nH added per branch (ECO L1) |
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

## Next stages

2. `prototype-closure/pcb/build_native21.py`: generate the unrouted board from
   native-21/frozen + `native-21/placement.json`, then DRC for courtyards,
   barrier and creepage pre-checks, and the fit gate on its STEP.
3. Power copper: BUS_P / HV_RET / LEG_RET planes, switch-node pours, bias
   rail loops.
4. Signal routing, then DRC, barrier gate (`tools/barrier_check.py`), audit
   parity and the release gates.
