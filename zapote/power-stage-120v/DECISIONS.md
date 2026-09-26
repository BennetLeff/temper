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
| D4 | Review placement before routing | Required by the accepted plan. No placement approval has been given. |
| D5 | Insulation basis and barrier parts | **Conditionally approved 2026-09-25 by the owner:** single-point controller-ground–PE functional bond and an 8.0 mm minimum placement target. Use verified laminate group IIIa or better (not IIIb above 50 V). This authorizes provisional barrier placement, not insulation qualification. The source now includes the removable 0 Ω functional link; its placement remains pending. Coilcraft evidence, applicable working-voltage/high-frequency rules and package/module certification scope remain open; increase spacing or change parts if those checks require it. See D5-BASIS.md. |
| D6 | Mains entry and coil exit edges | **Approved 2026-09-25:** mains left, coil right, viewed from the component side with the heatsink at the top. |

Part 4 §4.0 requires D1–D3 and D6 before deliberate placement. Part 4 §4.2
requires D5 resolution before barrier placement; the conditional basis above now
permits provisional barrier placement, with qualification still open. Section 4.5 requires written
placement approval before Part 5 routing. No final rules, placement, routed
board or fabrication package is represented as complete.
