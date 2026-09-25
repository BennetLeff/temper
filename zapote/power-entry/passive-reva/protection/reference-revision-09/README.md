# Clamp and protection integration — revision 09

This revision joins the previously separate source candidates, checks their
connections, and records what still prevents hardware or full-converter
acceptance. It does not change the retained 54-part board or restart the long
simulation campaign.

## Result and disposition

| Work | Result | Remaining limit |
|---|---|---|
| Clamp wiring | The review source reuses the compiled BAV23C candidate: ground anode, filtered ISENSE cathode, unused anode isolated | The part's low-current/temperature bounds remain insufficient; the authored hot model fails the chosen loading screen |
| Gate/standby integration | New Atopile source compiles with VD feedback, separate VD/VB sensing, protected gate drive and local-enable standby release | Source integration only; no new layout, full-plant transient, supply/isolation producer or hardware result |
| Component count | Actual export contains 131 instances: 54 + 79 − 2 redundant gate parts | This still has the complexity problem. It is an audit candidate, not an accepted compact board design |
| Fuse coordination | Source-fed, bank-fed and local-reservoir paths are distinguished; exact F1/F2 data and unknowns are recorded | Neither fuse is coordinated to a bounded physical fault waveform/withstand envelope |

The combined source is in [source-candidate](source-candidate/README.md).
It intentionally exposes the external F2, local reservoir, HOT 5 V and AUX_15V supply producers, relay-control
and ARM/PERMIT interfaces as missing assembly requirements. It does not hide them
behind an ideal physical actuator or count them as installed parts.

The compiler also shares library metadata by footprint. Its netlist library
MPNs cannot identify individual parts; see the [export limitation](export-metadata-limit.md).
The resolved per-instance record remains the source-part authority.

The parent-built [connectivity checker](graph-checks/README.md) passes on the
actual export. All nine regression tests pass, including rejection of four
well-formed wiring errors: reversed clamp, feedback on the bulk bank, direct
gate bypass and external-permit bypass. These establish selected connections,
not complete circuit correctness. [Results](graph-checks/parent-tests.txt).

## Evidence reused and checked

The earlier clamp correction was already compiled and its topology tested.
Repeating a nominal SPICE experiment would not resolve the missing vendor
data. The parent rebuilt and ran its actual Rust checker on the retained
netlist and logs: [clamp replay](reused-checks/clamp-replay.txt).
The checker exits **1**, as expected for the unresolved hot loading screen:

| Authored-model temperature | Clamp current at the −0.438 V stimulus | Chosen 1 µA / 2 mV screen |
|---|---:|---|
| 25 °C | 0.0702 µA | Pass |
| 85 °C | 1.865 µA | Fail on current |
| 125 °C | 9.590 µA | Fail on current and 2.110 mV shift |

The same replay passes the graph, nominal negative-clamp and reversed-diode
control checks. These are results of an assumed diode model, not measured
Vishay failures. The manufacturer data does not establish that model's
low-current or temperature behavior.

The parent also replayed the existing standby checker: baseline and doubled-
capacitance cases pass; the deliberately broken inhibit case is rejected.
See [standby replay](reused-checks/standby-replay-summary.json). Earlier
RevB rail/fault/fresh-arm results retain their original source/model scope;
they are not new simulations of the combined physical source.

## Engineering decisions

1. **Keep the corrected clamp topology as a provisional candidate.** Do not
   simply reverse BAT54H and declare it fixed. Resolve allowable PCL loading
   and selected-diode bounds before adopting the part.
2. **Do not adopt the 131-instance assembly as the final design.** This source
   reveals the complete connection and component cost of the current blocks.
   A reference-led reduction must preserve the verified functions and explicit
   fault paths before layout or another full operating campaign.
3. **Do not give gate-off credit for a failed-short MOSFET.** F1 covers the
   source path; F2 is in the bank path. Local capacitor discharge bypasses F2
   when the diode also conducts in reverse because of failure. Energy
   withstand, discharge/clamping or interruption must be assessed separately.
4. **Do not manufacture a fuse-clearing law.** F1's low-breaking-capacity data
   requires a prospective-current assessment. F2's 700 Vac clearing I²t does
   not supply capacitor-discharge DC let-through, and its 2.5 ms rating's
   definition needs confirmation.

## Detailed records and concrete external dependencies

- [Clamp evidence](clamp-evidence.md) / [structured record](clamp-evidence.json)
- [Integration map](integration-map.md) / [structured record](integration-map.json)
- [Fuse coordination](fuse-coordination.md) / [structured record](fuse-coordination.json)
- [Manufacturer question drafts](manufacturer-questions.md), **not sent**
- [Parent verification](parent-review.json)

The next adoption gates are diode/controller application data, a justified
component reduction, physical source/fuse/withstand bounds, and the missing
assembly interfaces. A new full converter run cannot establish those facts.
Hardware remains unavailable and unverified.
