# Placement decisions

This file records owner decisions. The owner approved the proposed D1–D3
and D6 defaults on 2026-09-25, then D5 as a conditional placement basis.
On 2026-09-26 the owner approved a revised 240 × 160 mm, four-layer design
basis. On 2026-09-26 the owner also gave renewed D4 approval for the revised
native-05 placement and native-06 routing, with three conditions (below).

| ID | Decision | Current status |
| --- | --- | --- |
| D1 | Maximum board outline | **Revised approval 2026-09-26:** 240 × 160 mm. Supersedes the 220 × 160 mm default. Owner reply: “Approve 240 × 160 mm, four layers”. |
| D2 | Heatsink and airflow | **Approved 2026-09-25:** shared PE-bonded heatsink along a long edge, with electrically insulated MOSFETs and bridge. Airflow direction is still not chosen. |
| D3 | Physical stackup | **Revised approval 2026-09-26:** four copper layers. Supersedes the two-layer default. **Fabricator 2026-09-26: JLCPCB (owner).** Stackup is JLCPCB JLC041622-7628: 2 oz on all four layers (70 µm outer, 61 µm inner finished) and a 0.5 mm core between In1 and In2, ordered as nominal 1.6 mm (1.653 mm stackup sum). Designed to JLCPCB's 2 oz rules in native-08/09. Laminate CTI must be confirmed on the order; see FAB-JLCPCB.md. Layer-count approval does not establish inner-plane ampacity. |
| D4 | Review placement before routing | **Renewed conditional approval 2026-09-26 by the owner** (reply: “approve”) for native-05 placement and native-06 routing at `3c07eea57` (routed board SHA-256 `500cdb4b…`). Supersedes the native-04 approval at `341e3c70c`. Conditions: **(1)** before fabrication, widen BUS_P copper where the nominal screen showed only ~6% margin: the local In2 upper branch (demand/screen 0.945) and the western In2 neck (0.945 at 15 A). Routing only, no part moves. *Addressed in native-07* (board `68fb5234…`: local row 0.805, western neck with B.Cu parallel 0.443), and still met on the JLCPCB build native-09 at 61 µm inner copper (board `ccaa3859…`: 0.886 and 0.457); see native-09/verification/README.md; **(2)** at bring-up, measure `ocp_node` during hard switching at full current, and confirm the RC filter margin against false trips and trip delay for the 59 mm paired Kelvin run; **(3)** at bring-up, measure Vgs ringing on all four switches before raising current; the remedy is the gate resistor value, not placement. Routing rules stay as before: local-capacitor returns through R5 current pads 1/4; Kelvin pads 2/3 separate; gate drives paired with their source returns; overlapping bus/return copper; the provisional insulation rules enforced. Not a fabrication or powered-operation release. See PLACEMENT-REVIEW.md. |
| D5 | Insulation basis and barrier parts | **Conditionally approved 2026-09-25 by the owner:** single-point controller-ground–PE functional bond and an 8.0 mm minimum placement target. Use verified laminate group IIIa or better (not IIIb above 50 V). This authorizes provisional barrier placement, not insulation qualification. The source includes the removable 0 Ω functional link R38, placed beside the PE terminal inside the controller island in native-05; covered by the renewed D4 approval. Coilcraft evidence, applicable working-voltage/high-frequency rules and package/module certification scope remain open; increase spacing or change parts if those checks require it. See D5-BASIS.md. |
| D6 | Mains entry and coil exit edges | **Approved 2026-09-25:** mains left, coil right, viewed from the component side with the heatsink at the top. |


**D4 note, 2026-09-27:** the owner approved adding the tank-CT detector, so T1's secondary is terminated on this board (validation-results/06-controller-interface). That is a placement change: 21 parts on a new SELV island lobe by T1, and U13/C47 beside J4. **Renewed D4 approved by the owner on 2026-09-27** (reply: “approve”) for native-10 (placement) and native-11 (routed; electrical board `2fec2924…`, active presentation board `05141028…`), under conditions 1–3. Condition 1 still holds on native-11: the power screens are unchanged. Condition 2 adds a bench item: with the tank running, check CT_ZC and CT_MON for switching-node pickup, and verify the tank-CT trip at the ~55 A design point with injected primary current. Not a fabrication or powered-operation release.

**2026-09-27, native-12/13:** the owner approved two part-number swaps from validation task 02. D4/D5 change from BAT54H to BAS116H (hot leakage). R14/R6 change to 100 Ω and R16/R8 to 1 kΩ, which speeds the PERMIT → DIS path. Poses, footprints, pads, tracks and vias are identical to native-10/11. The zone refill differs by ≤ 0.10 mm². The D4 approval above therefore carries to native-12 (placement) and native-13 (routed; electrical `ce1cf636…`, active presentation board `8056fc95…`).

**2026-09-27, native-14/15:** the owner approved correcting C1/C2 (reply: “yes”) from KEMET R463R410000M1M, whose 27.5 mm pitch didn't fit the 22.5 mm footprint, to R463N410000N1M (22.5 mm pitch; validation task 07 round 2). A new footprint, `temper:KEMET_R463N410000N1M_P22.50_ReviewOnly`, and a maximum-body 3D envelope come with it. Poses, pads, tracks and vias are identical to native-12/13, and so are the placement metrics. The zone refill differs only in vertex order. The courtyard is 0.35 mm wider per side. C1 is now 1.56 mm from RV1. C2's C5/BR1 gaps and heat-zone margin are unchanged. **D4 carry-over to native-14 (placement) and native-15 (routed; electrical `bec1df67…`, active presentation board `a3ac1249…`) is recommended by the reviewer (Claude) and awaits the owner's confirmation**, because the body outline changed. See native-15/verification/README.md.
Part 4 §4.0 requires D1–D3 and D6 before deliberate placement. Part 4 §4.2
requires D5 resolution before barrier placement; the conditional basis above now
permits provisional barrier placement, with qualification still open. Section 4.5 requires written
placement approval before Part 5 routing. Native-05/native-06 are now the regenerated placement and routed review
artifacts. Their prototype checks are recorded in PLACEMENT-REVIEW.md. Renewed
D4 is conditionally approved; its condition 1 and physical qualification remain open. No fabrication package is released.

## Prototype source revision, 2026-09-25

The owner approved D3 MRT130KP295CV across BUS_P/HV_RET; two 2.7 µF/1000 V
TDK B32656G0275J000 bulk capacitors; four 100 nF/1000 V TDK
B32652A0104K000 local capacitors (two per leg, BUS_P to HV_RET); retention
of the CDE resonant capacitors; Phoenix 1704004 as the PCB PE branch; two
separate Würth 74650074 M4 coil terminals; smaller C3/C4 pads at 10 mm
pitch; and removable links on **both** rectifier rails. These choices are
implemented in the source revision. J1 is now L/N only (Phoenix 1711725),
J6 is the PE branch, J2/J5 are coil studs, and J7–J10 are link studs.
The external jumpers are deliberately absent from the source net joins.
With both removed, BR1 and J7/J9 still become mains-live if mains is
present; a floating bench source may connect only to J8 BUS_P and J10
HV_RET. Cord PE still bonds directly to the chassis stud, with a separate
branch to J6. The PE branch and C3/C4 footprint changes receive **no**
waiver from D5. See [ASSEMBLY.md](ASSEMBLY.md) and
[PROTOTYPE-POWER-LOOP.md](PROTOTYPE-POWER-LOOP.md).

This is source-level approval. The new 114-part native projection, deliberate
placement, complete copper, enclosure assembly, 20 A link capability at its
operating temperature, and powered qualification are separate checks. D4
is renewed for native-05/native-06 with the conditions above. The lab call and RCA 12A3
teardown remain outstanding.
