# L2 footprint correction and scratch qualification

Status: corrected candidate with bounded native verification; not a fabrication
release or a qualification of the frozen experiment inputs.

The Bourns SRP1265A drawing identifies 5R6M as the lead-frame terminal version.
Its recommended land span is 14.2 mm, inner gap 8.0 mm, and pad height 5.0 mm.
Equal rectangular pads therefore have width `(14.2-8.0)/2 = 3.1 mm` and centers
at +/-5.55 mm. Both the Luna agent and host visually inspected the drawing.
The [retained manufacturer PDF](../buck-20260909/sources/bourns-srp1265a.pdf)
has SHA-256 `30b470999b737a6350ce5b09a917a5f12090c2e0895a78ddc15285e3d44ec649`.

| Geometry | Existing fixture | Corrected proposal |
|---|---:|---:|
| Pad centers | +/-5.00 mm | +/-5.55 mm |
| Pad dimensions | 3.4 × 5.5 mm | 3.1 × 5.0 mm |
| Inner land gap | 6.6 mm | 8.0 mm |
| Outer land span | 13.4 mm | 14.2 mm |
| Nominal body, F.Fab | Absent | 13.5 × 12.5 mm |
| Maximum body, User.Drawings | Absent in fixture footprint | 14.0 × 12.8 mm |
| Courtyard | Absent | 15.0 × 13.8 mm |

The courtyard is a proposed assembly convention, not a Bourns dimension. It
provides 0.5 mm around the maximum body and 0.4 mm beyond the outer land edges.
Review it against the assembly rules and Bourns inspection guidance before
fabrication release. A 3D model is still absent.

The [standalone footprint](layout/srp1265a-5r6m-proposal.kicad_mod) has SHA-256
`edf846ce16f68be8b74e6da0e9bf2712729a297d18e466efde127d0b089bf203`.
KiCad pcbnew 10.0.4 loaded it and verified two pads, numbers 1/2, the stated
centers and dimensions; see [native-validation.json](layout/native-validation.json).

## Scratch board

The agent copied the compact-v4 candidate and its complete sibling project,
rules and library context, then changed only L2's pad/mechanical geometry.
Placement, tracks, UUIDs and nets were retained. Pad 1 remains `sw`, pad 2
remains `+3V3`; at the unchanged L2 center (31,20) mm the pad centers are now
(25.45,20) and (36.55,20) mm. The retained
[candidate board](layout/candidate-v5/candidate.kicad_pcb) has SHA-256
`1d1ae546a0e78fe4c923b5cee736bc0811ca13a7cca33853274052f556d13ac3`.

The existing native collector loaded the board and returned 12 footprints,
15 visible labels and complete pad/net measurements. Its result is
[layout-native-v5-final.json](layout/candidate-v5/layout-native-v5-final.json).
pcbnew emitted a nonfatal `create wxApp before calling this` stderr assertion;
the collector still returned the complete measurement.

An initial L2 library mismatch was fixed by exporting the corrected embedded
footprint through pcbnew into the sibling `fixture.pretty` library. The earlier
reports are retained for provenance. The first three clean reports used bare
CLI invocation and must not be cited as verification with the repository's
required all-track-errors configuration. The final verification record below
identifies the corrected procedure and results separately.

The final three runs used KiCad CLI 10.0.4, `--all-track-errors --format json`,
and the repository's `_single_threaded_kicad_env()` context seeded from the
local KiCad 10.0 settings with `MaximumThreads=1`. Each exited 0 and reported
zero violations and zero unconnected items, with errors and warnings included.
See the [first](layout/candidate-v5/drc-v5-pinned-1.json),
[second](layout/candidate-v5/drc-v5-pinned-2.json) and
[third](layout/candidate-v5/drc-v5-pinned-3.json) raw reports,
[commands](layout/candidate-v5/commands.md), and
[provenance](layout/candidate-v5/pinned-drc-provenance.json).
The board hash remained unchanged. Three repeated results establish this
bounded candidate check, not a statistical ceiling or production-board gate.

## Qualification boundary

The current project ignores `missing_courtyard`, `track_not_centered_on_via`,
`tuning_profile_track_geometries`, `footprint_filters_mismatch` and
`footprint_type_mismatch`. Native DRC cannot establish those omitted claims.
L2's explicit courtyard does not establish complete courtyard coverage for
the rest of this candidate.

No Rust layout judge, frozen reference qualification, four-development/six-
reserved-input refresh, or defect-specific negative controls were run. Those
remain required before replacing experiment inputs. In particular, the 4 mm
nearest-ground-anchor check and 20 mm connected-path measurement are distinct
evaluator quantities. Native DRC does not replace either check or establish
converter transient performance.
