# Placement decisions

The 2026-09-25 implementation has reached the native shelf stage. This file
records decision status. The owner approved the proposed D1–D3 and D6
defaults on 2026-09-25. The owner subsequently approved D5 as a conditional
placement basis; D4 remains open.

| ID | Decision | Current status |
| --- | --- | --- |
| D1 | Maximum board outline | **Approved 2026-09-25:** 220 × 160 mm maximum. |
| D2 | Heatsink and airflow | **Approved 2026-09-25:** shared PE-bonded heatsink along a long edge, with electrically insulated MOSFETs and bridge. Airflow direction is still not chosen. |
| D3 | Physical stackup | **Approved 2026-09-25 and implemented in native-02:** two copper layers, 1.6 mm FR-4, 70 µm copper per side. Fabricator stackup acceptance remains separate. |
| D4 | Review placement before routing | **Awaiting owner review.** native-04 (2026-09-26) answers the native-03 D4 review: gate networks at the gates, legs closed around R5, split potential groups, terminal-hardware envelopes. DRC 0, parity 0, stackup gate PASS; see PLACEMENT-REVIEW.md. No routing until written approval. |
| D5 | Insulation basis and barrier parts | **Conditionally approved 2026-09-25 by the owner:** single-point controller-ground–PE functional bond and an 8.0 mm minimum placement target. Use verified laminate group IIIa or better (not IIIb above 50 V). This authorizes provisional barrier placement, not insulation qualification. The source now includes the removable 0 Ω functional link; its placement remains pending. Coilcraft evidence, applicable working-voltage/high-frequency rules and package/module certification scope remain open; increase spacing or change parts if those checks require it. See D5-BASIS.md. |
| D6 | Mains entry and coil exit edges | **Approved 2026-09-25:** mains left, coil right, viewed from the component side with the heatsink at the top. |

Part 4 §4.0 requires D1–D3 and D6 before deliberate placement. Part 4 §4.2
requires D5 resolution before barrier placement; the conditional basis above now
permits provisional barrier placement, with qualification still open. Section 4.5 requires written
placement approval before Part 5 routing. No final rules, placement, routed
board or fabrication package is represented as complete.

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
remains open; no routing approval has been given. The lab call and RCA 12A3
teardown remain outstanding.
