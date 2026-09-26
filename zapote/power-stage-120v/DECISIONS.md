# Placement decisions

The 2026-09-25 implementation has reached the native shelf stage. This file
records decision status. The owner approved the proposed D1–D3 and D6
defaults on 2026-09-25; D4 and D5 remain open.

| ID | Decision | Current status |
| --- | --- | --- |
| D1 | Maximum board outline | **Approved 2026-09-25:** 220 × 160 mm maximum. |
| D2 | Heatsink and airflow | **Approved 2026-09-25:** shared PE-bonded heatsink along a long edge, with electrically insulated MOSFETs and bridge. Airflow direction is still not chosen. |
| D3 | Physical stackup | **Approved 2026-09-25 and implemented in native-02:** two copper layers, 1.6 mm FR-4, 70 µm copper per side. Fabricator stackup acceptance remains separate. |
| D4 | Review placement before routing | Required by the accepted plan. No placement approval has been given. |
| D5 | Insulation basis and barrier parts | **Open.** The proposed single-point SELV_GND–PE functional bond is not present in the source and has not been approved. A uniform ≥ 8.0 mm barrier is a provisional target, not a demonstrated PD3 requirement. The five source changes are implemented, but working-voltage bounds, high-frequency requirements, actual laminate CTI, package/module certification scope and Coilcraft CST3015 evidence remain unresolved. See ORACLE-REVIEW.md; the 468/511 V estimates do not close this decision. |
| D6 | Mains entry and coil exit edges | **Approved 2026-09-25:** mains left, coil right, viewed from the component side with the heatsink at the top. |

Part 4 §4.0 requires D1–D3 and D6 before deliberate placement. Part 4 §4.2
requires D5 resolution before barrier placement; §4.5 requires written
placement approval before Part 5 routing. No final rules, placement, routed
board or fabrication package is represented as complete.
