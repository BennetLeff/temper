# Placement decisions — awaiting owner input

The 2026-09-25 implementation has reached the native shelf stage. This file
records decision status; proposed defaults are not approvals.

| ID | Decision | Current status |
| --- | --- | --- |
| D1 | Maximum board outline | Pending. Proposed 220 × 160 mm; used only for the provisional shelf. |
| D2 | Heatsink and airflow | Pending. Proposed shared PE-bonded heatsink along a long edge, with electrically insulated MOSFETs and bridge. Airflow direction is not chosen. |
| D3 | Physical stackup | Pending. Proposed two copper layers, 1.6 mm FR-4, 70 µm copper per side. The shelf generator's copper-layer declarations are not this physical stackup. |
| D4 | Review placement before routing | Required by the accepted plan. No placement approval has been given. |
| D5 | Insulation basis and barrier parts | Open. First establish the controller-side SELV_GND–PE reference architecture, then boundary working voltages and package/PCB requirements. See RULES-PREFLIGHT.md and ORACLE-REVIEW.md; the external answer is a proposal, not approval or a proven voltage bound. PD3 remains the project basis. |
| D6 | Mains entry and coil exit edges | Pending. Proposed mains left and coil right when viewed from the component side with the heatsink at the top. |

Part 4 §4.0 requires D1–D3 and D6 before deliberate placement. Part 4 §4.2
requires D5 resolution before barrier placement; §4.5 requires written
placement approval before Part 5 routing. No final rules, placement, routed
board or fabrication package is represented as complete.
