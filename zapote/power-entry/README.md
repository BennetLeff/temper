# Active-PFC power-entry unit

The standalone 54-component board is routed. Source-build-22, the native23
source manifest, and the saved candidate agree on all 33 nets. The
[current copper-repair checkpoint](evidence/copper-repair-2026-09-12/README.md)
widens one `minus` trace from 4 to 6 mm. Native DRC reports zero violations,
unconnected links and schematic parity findings. The Rust nominal PFC screen
still reports **four failures** at the bridge terminal necks; thermal and other
engineering qualification remain incomplete.

The design targets the 1,800 W nominal AC-input class at 120 VAC. At 15 A RMS
and PF 0.99, real input is 1,782 W before conversion losses. The nominal bus
setpoint is 389.615 V. This does not claim 1,800 W delivered to the pan.

## Inspect the result

- [Native KiCad PCB](candidate/section.kicad_pcb) and [schematic](candidate/section.kicad_sch)
- [Current native geometry](evidence/native-copper-12.json), selected by the common unit runner
- [Routed checkpoint and hashes](evidence/routed-checkpoint.json)
- [Native DRC](evidence/drc-11.json), [ERC](evidence/erc-11.json), [Rust report](evidence/rust-11.json)
- [3D render](evidence/power-entry-routed.png), [front copper](evidence/power-entry-front.svg), [back copper](evidence/power-entry-back.svg)
- [Construction review and limits](evidence/routing-review.md)
- [Exact source BOM](source-build-22/build/default.csv), [interfaces](INTERFACES.md), [acceptance scope](ACCEPTANCE.md)

The prototype outline is **230 × 210 mm**, two copper layers, 70 µm copper,
1.6 mm total thickness. It grew 20 mm from the placed candidate to provide a
separate earth/Y-capacitor corridor. This is an engineering prototype allowance;
heatsinks, missing component models, service access and final cooker enclosure
fit are not established by this render.

The agent authored placements and explicit routes; the existing KiCad adapter
applied them. Rust checks the result. No placer or router search was added.

All auxiliary, permit and relay-control headers are HOT bus-minus referenced.
They require external isolated bias and control. Precharge/bypass sequencing,
15 A RMS foldback, active discharge, loaded switching, thermal behavior and EMC
remain integration/qualification work. Passive discharge alone takes about
21 minutes nominal to reach 60 V. No purchase, fabrication order or powered
measurement has been performed.

The previous [unrouted checkpoint](evidence/construction-checkpoint.json) and
native05 fixture remain historical counterexamples, not the current board.
The native11 reports, routed-checkpoint hashes and renders above describe the
pre-repair routing; the copper-repair checkpoint records the current saved bytes.
