# Auxiliary board next milestone — reviewed choice

## Decision

Build the existing **mains-disconnected rail-order laboratory fixture** as a routed standalone KiCad PCB. This is a passive measurement coupon, not the cooker auxiliary supply. Keep the HOT and SELV product-supply choices open until the missing current, startup, protection, insulation, and installed-temperature envelopes are evidenced.

## Brainstorm and review

| Path | What it could deliver now | Review finding |
| --- | --- | --- |
| H1: IRM-20-15 direct HOT source | A source/protection PCB candidate | The documented 50 °C static screen leaves 62.5 mV before path drop. Complete load and fault peaks, branch fuse/inrush, FET/shunt and local temperature are unknown. A routed board would imply unsupported source acceptance. |
| H2: IRM-20-24 then LMR36015 HOT source | A regulated source/protection PCB candidate | Better ideal feedback-only voltage margin, but still lacks converter dynamics, cutoff output peak, source load, branch protection, thermal and restart proof. |
| P1: passive rail-order lab fixture | A native schematic and routed PCB for the existing 13-footprint, 10-net Atopile circuit | Source connectivity and lab scope are already defined and audited. This is the bounded route chosen. Its generic headers and probe pads are layout candidates, not an orderable or live-board interface. |

The existing U1–R1 evidence reports 151 unknown load/selection fields and no selected product source. This plan does not replace U2/U3 of the auxiliary product-supply plan. It advances the previously source-defined P1 fixture only.

## Work and checks

1. Rebuild the exact fixture Atopile source with version 0.2.69, keep its generated netlist/BOM and source hashes, and rerun the independent 13-component/10-net audit.
2. Generate a flat native schematic from the compiled netlist and a native board from its exact pad map. Place all 13 footprints, route ten nets, mark the coupon LAB ONLY, and keep J1/J2/J3 pin identities visible.
3. Check source-to-native pad mapping, schematic exported netlist, KiCad ERC and DRC. Save tool versions, artifact hashes, positive results and any residual violations. Test that a swapped rail or missing probe would be rejected by the existing audit.
4. Record that the fixture is not a protected AUX producer, has no hardware capture or reviewed mating harness, and cannot connect to energized Rev38.

## Exit condition

A reproducible native lab-fixture PCB candidate with no unrouted or shorted nets and an explicit digital-only status. Product auxiliary source selection and physical qualification remain open.
