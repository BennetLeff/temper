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
| D3 | Physical stackup | **Revised approval 2026-09-26:** four copper layers. Supersedes the two-layer default. Current proposed stackup is 1.6 mm overall, 70 µm copper on all four layers. Layer-count approval does not establish inner-plane ampacity or fabricator stackup acceptance. |
| D4 | Review placement before routing | **Renewed conditional approval 2026-09-26 by the owner** (reply: “approve”) for native-05 placement and native-06 routing at `3c07eea57` (routed board SHA-256 `500cdb4b…`). Supersedes the native-04 approval at `341e3c70c`. Conditions: **(1)** before fabrication, add parallel copper so the local In2 BUS_P upper branch (screen ratio 0.945) and the western In2 BUS_P neck (~6% margin at 15 A) screen at ≥ 1.0 with margin, then re-run the power review — routing only, no part moves; **(2)** at bring-up, measure `ocp_node` during hard switching at full current, and confirm the RC filter margin against false trips and trip delay for the 59 mm paired Kelvin run; **(3)** at bring-up, measure Vgs ringing on all four switches before raising current; the remedy is the gate resistor value, not placement. Routing rules stay as before: local-capacitor returns through R5 current pads 1/4; Kelvin pads 2/3 separate; gate drives paired with their source returns; overlapping bus/return copper; the provisional insulation rules enforced. Not a fabrication or powered-operation release. See PLACEMENT-REVIEW.md. |
| D5 | Insulation basis and barrier parts | **Conditionally approved 2026-09-25 by the owner:** single-point controller-ground–PE functional bond and an 8.0 mm minimum placement target. Use verified laminate group IIIa or better (not IIIb above 50 V). This authorizes provisional barrier placement, not insulation qualification. The source includes the removable 0 Ω functional link R38, placed beside the PE terminal inside the controller island in native-05; covered by the renewed D4 approval. Coilcraft evidence, applicable working-voltage/high-frequency rules and package/module certification scope remain open; increase spacing or change parts if those checks require it. See D5-BASIS.md. |
| D6 | Mains entry and coil exit edges | **Approved 2026-09-25:** mains left, coil right, viewed from the component side with the heatsink at the top. |

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
