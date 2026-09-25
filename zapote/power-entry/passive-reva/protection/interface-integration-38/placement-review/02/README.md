# Rev38 anchored native placement diagnostic 02

**Status: diagnostic, 2026-09-24. U7 remains open.** The current
`native-stackup-diagnostic/` is a saved 295-reference native probe built from
the frozen `source-build-06` receipt
`a164f33463b42748eefd4474be5f225077e191eae2378448eccad69b932b3d36`
and the approved 360 × 250 mm **planning** envelope. It includes the
provisional `stackup.json` (SHA-256
`45bbfe06341177314ac3e9722ac2afcbf6eda05e8fc87cec052ade77aa98b488`)
as both native PCB CAD data and a source-manifest input. The earlier
pre-stackup diagnostic board had SHA-256
`d28a745e2560fc478ea2b35708eec6ae2fa8d0df894429e10136aee7bec9cc75`
and the same 0 ERC, 0 non-routing DRC, 0 schematic-parity, 499 capped
unconnected result; its duplicate generated files were removed after the
stackup-aware replay. This output is not a reviewed placement, routed board,
approved insulation design, or fabrication release.

`poses.json` starts from the prior diagnostic shelf pose set (SHA-256
`46d114daca00f24e90a2362ae6ef9ff2b5ac65452d31afde73842fbddf73419b`).
The 21 proposed anchor references already matched that set except for U229.
Exactly three source-instance poses changed:

| Source instance / reference | Before `(x, y, angle)` mm/deg | This probe | Reason |
| --- | --- | --- | --- |
| `pfc_power.local_c` / U229 | `(178, 154, 0)` | `(182, 154, 0)` | Apply the proposed local VD reservoir anchor. |
| `ac_input.y1` / U246 | `(54.8, 10.5, 0)` | `(65, 45, 0)` | Remove three 0.15 mm clearances against U2 and a silkscreen collision with U259; screen a location between the AC/PE entry and CMC. The Y1 route and insulation path remain unreviewed. |
| `hot15_converter.fb_bottom` / U263 | `(179.42, 23.35, 0)` | `(184.5, 23.35, 0)` | Remove U224 reference silkscreen overlap and two silkscreen-over-copper findings. Feedback-loop placement remains unreviewed. |

All other 292 poses still come from the arbitrary shelf diagnostic. In
particular, X2 U244 and MOV U245 remain at the top edge, outside a reviewed
AC input layout. The isolation corridor, connector mating direction,
mounting supports, capacitor vent and heatsink volumes have not been accepted.
The generated board has no tracks, standalone vias, zones, slots, or mounting
holes. `placement-overview.svg` shows the same diagnostic pose set in 2D;
the stackup update changes CAD construction fields, not footprint positions.

## Saved artifacts and checks

| Artifact | SHA-256 |
| --- | --- |
| `poses.json` | `ae0177b9adb8dc7540d27955cfacf502ce281a53404e0627770635ee394f47ab` |
| `native-stackup-diagnostic/section.kicad_pcb` | `957ca67ada9338d91f9384695d3b3bf9d0f4a87263b471391700faf60760542d` |
| `native-stackup-diagnostic/section.kicad_sch` | `339154c9e3809782da312c8d85053ee9cfea2d87196b3b20652d25be9261201c` |
| `native-stackup-diagnostic/source-manifest.json` | `a20fcf73531417dc140bb3b9ce3c1fb309d7b7a0f909992839edeeba845c6051` |
| `native-stackup-diagnostic/drc-parity.json` | `f6da18e3ac625f7f04c91e3bedde5bd3f18d0b9bafaa189688f6c76c6297080b` |
| `native-stackup-diagnostic/stackup-report.json` | `a770ff1c7676463f5ea0c1aecc5f2200e3dffea1a04806543d36e5b251e6ec67` |
| `native-stackup-diagnostic/identity-report.json` | `f022b0ab703b9535de45d9e3af41a5ead61e7eafa22c7aed07d6ba7018263a0e` |
| `native-stackup-diagnostic/native-export.json` | `8a13ca76432e6f9d78c22153ccb138f9bb295b3efb55f10a893cd60dcb57e1a4` |

The native generator now projects the audited `SourceInstance` and `MPN`
values from its source manifest into every one of the 295 board footprints.
It also stamps all 1,089 KiCad pad objects with stable UUIDs (including
16 mask/paste-only objects and three non-plated holes); two independent
regenerations produced byte-identical PCB and manifest files. The strict
Rust native binder checks the saved document's component MPNs, pad numbers,
net names and UUIDs against the KiCad export. Its real-board test passes.
The shared KiCad extractor reads the saved board as 295 components, 1,070
pad connections and 1,052 native connectivity clusters, with zero tracks,
vias or zones. This transport export is an input for later copper-domain
checks, not such a check itself. The generator's source and raw-pad checks passed, and the
manifest's board and stackup hashes match the saved inputs. KiCad 10.0.4 ERC
with all severities reported **0 violations**. KiCad DRC with schematic
parity and all severities reported **0 non-routing violations** and **0
schematic parity issues**, down from seven non-routing findings in the
previous shelf diagnostic. KiCad reported **499 unconnected items**, its
output cap on this unrouted board; this is not a route-completion count.
`FootprintNeedsUpdate` against the generated candidate-local libraries
reported **0 mismatches across 295 placed footprints** on the final
stackup-aware diagnostic. The board has zero routed tracks and zones.

The reusable Rust `DRC.BOARD.STACKUP` gate reports **PASS**: six copper
layers, with copper, dielectric and mask adding to **1.800000 mm**, equal to
the declared board thickness. This is nominal CAD consistency only. The
fabricator, finished thickness tolerance, laminate CTI, thermal/current
construction and insulation schedule remain unselected.
Changing only the board's general thickness to 1.7 mm in a temporary copy
made the same Rust gate fail: the 1.800000 mm stackup sum differed from the
1.700000 mm declaration. That negative control checks the gate's response to
an invalid stackup; it does not qualify the selected materials.

The Rust `zapote-board` identity mode reports **PASS** for these exact PCB
bytes and all six source-manifest inputs (`default.csv`, `default.net`,
`outline.json`, `poses.json`, `resolved-components.json`, `stackup.json`).
Its focused CLI tests verify that changed PCB bytes with a valid stackup
and a stale compiled netlist both fail. The manifest itself is separately
pinned by the SHA-256 above. This gate does not establish electrical
correctness or detect a copper-domain bridge in an unrouted board.

An independent export of the saved schematic compared named numeric
`(net, reference, pin)` edges against the frozen compiled source after
excluding the declared off-board F2 (U226): **295 references, 246 nets, and
1,052 edges**, with zero missing or extra references or edges. The exported
netlist is saved as `native-stackup-diagnostic/export.xml`. The source bridge's
`source-manifest.json` records the source, pose and library identities.

The DRC result uses the current generator's provisional board rules and
ignored-check list. It cannot approve the 15.2 mm opposed-pad copper gap at
the DWW isolators against the provisional 16.0 mm Group IIIa board-surface
screen, the final air/creepage construction, current carrying copper, or the
physical fault-response behavior. Reviewed placement and routing should
follow U4 electrical review and the open fabricator stackup, supply,
connector, and insulation decisions.

The focused Rust native-domain test currently classifies only `selv3v3` and
`selv_gnd` against `hot0` and `hot_logic5`, with a provisional 16.0 mm
board-surface screen. It **fails** on a measured 15.2 mm DWW opposed-pad
gap and other shelf-placement conflicts. All remaining native nets are
reported as a coverage gap. A synthetic SELV trace across a HOT pad fails
the domain rule, and the mutated export fails saved-board binding. This is
negative evidence and a rule-plumbing check, not a complete insulation
assessment. See `zapote/packages/zapote-drc/tests/rev38_native_domains.rs`.
