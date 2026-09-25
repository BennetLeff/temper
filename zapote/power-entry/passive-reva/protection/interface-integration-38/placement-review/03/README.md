# Rev38 functional-region placement diagnostic 03

**Status: saved native placement candidate, U7 OPEN (2026-09-24).** This is a
295-footprint source-to-PFC section-board probe on the user-approved
360 × 250 mm planning envelope. It is neither a routed board nor an
insulation, mechanical, thermal or fabrication release. The governing source
is `source-build-06`; the DWW barrier, F1/AUX/F2 construction and full
current/voltage envelope remain open.

`poses.json` records every source instance. Relative to the shelf diagnostic
in `placement-review/02`, 275 of 295 poses changed. The large inductor moved
from `(180,74)` to `(160,60)` mm and the rectifier bridge from `(95,42)` to
`(125,120)` mm, opening a HOT-side strip beside the two DWW isolators. The
receiver parts now occupy that strip and nearby HOT control space. Source
logic and the controller-port parts stay on the SELV side. X2 and MOV moved
from the board's top edge into the AC-input region. The two DWW isolators,
16-contact SELV port, four bulk capacitors, F2 studs and other listed large
anchors retained their previous poses. [Placement overview](native-diagnostic/placement-fit.png)
is the KiCad 10.0.4 courtyard/silkscreen export used for visual inspection.

This was a first packing pass with 1.5 mm candidate courtyard
separation for moved parts. It is **not** a routing optimization or a
reviewed clearance rule. Native KiCad was the collision oracle. Every
footprint courtyard stayed at least 5 mm inside the planning outline; every
ordinary HOT footprint remained left of `x=235` mm and every source/port
footprint right of `x=270` mm. Only the two isolators span the reserved
corridor. These coordinates do not settle connector cable exits, current
loops, inductor magnetic field, capacitor venting, heatsinks, support holes,
F2 lugs, test-point access, or the installed enclosure.

A straight-line minimum-spanning-tree estimate from exported pad centers
reduced the `rect_minus` proxy from 144.4 to 49.1 mm, `vd_local` from 289.7
to 175.2 mm and `vb_bank` from 459.6 to 234.7 mm. It also increased the
`ac_rect_n` proxy from 190.5 to 205.7 mm, `hot0` from 1124.8 to 1273.7 mm
and `hot_logic5` from 547.0 to 703.4 mm. These are placement comparisons,
not routed lengths, voltage drop, current density, noise or thermal evidence.
The longer return/logic paths are specific review targets before routing.

## Saved evidence

| Artifact | SHA-256 |
| --- | --- |
| `poses.json` | `c3bd07de25a8c53da0576a330256a138279704ae37d54e4cc8b476216f78c7a5` |
| `native-diagnostic/section.kicad_pcb` | `c277e9cae08213557f8bed43253253966229c695a9e754474d229babcf786ff5` |
| `native-diagnostic/section.kicad_sch` | `339154c9e3809782da312c8d85053ee9cfea2d87196b3b20652d25be9261201c` |
| `native-diagnostic/source-manifest.json` | `46bd18598f2717da1891d0398639a60bebc798e13bfecb529ac60cbe05de4798` |
| `native-diagnostic/native-export.json` | `3c539845b5e6e7b841d2450732d9ac6bc25b8b64d0abe9d24637ce9fd651b56e` |
| `native-diagnostic/drc.json` | `b0734440b0ff5ac807b92f6180ec85006ed6a962623aed50893a341efcb67b87` |
| `native-diagnostic/erc.json` | `accaca7b810c1d261145329bfe2ee9ff65dc89cae8c5d147ed5f3324745c450c` |
| `native-diagnostic/identity-report.json` | `7eac1a6503e9e38818c23497f1cbd82a7871ded7b8af3fdddde0519992c5e92b` |

A second `build_native.py` invocation from the saved `poses.json` produced
byte-identical PCB and source-manifest files. `zapote-board` reports PASS for
the exact saved PCB bytes, its provisional 1.8 mm/six-layer CAD stackup and
all six source input hashes. KiCad 10.0.4 ERC reports zero findings. DRC with
all severities and schematic parity reports zero violations and zero parity
issues; its 499 unconnected items are a cap on the unrouted board, not a
count of all remaining connections. The checked DRC configuration retains
its listed ignored checks, and no Rev38 net-pair insulation rules exist yet.

The KiCad footprint-library comparison loads all 295 footprints from the
candidate-local libraries and reports zero missing or out-of-date footprints
(`footprint-parity.json`). The source/native receipt compares all 295
components, 246 named nets and 1,052 distinct numeric pad edges, with zero
missing or extra edges (`source-native-parity.json`). KiCad exposes 1,070
physical pad connections because several lands share an electrical pad
number. The Rust native document binder checks the embedded exact PCB
against native component, MPN, pad-net, UUID and copper census; its
`rev38_native_domains` integration test passes. The same test keeps the
provisional 16.0 mm SELV/live projected copper-distance result **FAIL**,
including the unchanged 15.2 mm opposed DWW pad gap. The pin-side check
covers 62 SELV, 183 live and one PE named nets; it is not a reviewed voltage
or insulation schedule.

The next U7 step is a physical placement review with real cable, fastener,
thermal, field and assembly volumes, followed by a chosen insulation
construction and complete net-pair rules. Routing follows U4 electrical
review. Only a joined, routed and independently checked `native/section`
can be considered for the plan's native-board acceptance; physical fault
captures remain NOT RUN.
