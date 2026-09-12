# Power-entry unit

Source-build-18 is the current 53-component candidate for a standalone 120 VAC, 1,800 W nominal AC input. The target is 15 A RMS at PF 0.99 (about 1,782 W real input), with active CCM boost PFC regulating a nominal 389.615 V bus. The source is `elec/src/power_entry_unit.ato`.

The bus is a single PFC output with no capacitor midpoint. AUX, CONTROL, and PERMIT returns reference HOT bus-minus and are never MCU or SELV grounds. External isolated bias, precharge, permit sequencing, and RMS foldback are integration requirements; default state is off. Passive discharge uses two 150 kOhm bleeders and is approximately 21 minutes nominal, so active discharge and timing qualification remain open.

The 53-part candidate is unrouted and unaccepted. ERC, DRC, schematic parity, ampacity, inrush, ripple, thermal, EMI, insulation, and discharge checks have not established a construction pass.

## Coordinator construction checkpoint

Source-build-18 and candidate/source-manifest.json govern the 53-component circuit.
Native ERC (erc-04.json): zero findings. Native DRC (drc-05.json): zero geometry
violations, zero schematic-parity findings, **94 unconnected links**. Rust
(rust-05.json) rejects disconnected copper while accepting the exact source/pad
graph and saved-document binding. No copper routing has been accepted.
The 230 × 190 mm outline is a prototype allowance; component models, heatsinks,
service space and final enclosure fit remain incomplete. The render omits bodies
for several parts without local 3D models. It is not an assembly-clearance proof.
