# P2 mechanical and manufacturing contract

`zapote_drc::manufacturing::validate` is the Rust authority for the P2
geometry checks. A native adapter must populate `ManufacturingInput` from the
saved KiCad export:

* `bodies`: each required component's actual F.Fab polygon, pose, and native
  angle; missing required polygons produce `INDETERMINATE`.
* `outline` and `cutouts`: the actual Edge.Cuts polygons, including holes.
* `copper`: exact copper polygons per layer, including zones after fill.
* `pads` and `holes`: native copper and drill dimensions. Pad bounding boxes
  are used only to calculate the explicitly declared annular-ring minimum;
  they are never used as body or outline geometry.
* `limits`: source-declared prototype limits. `qualified: false` always adds
  a qualification gap, so a prototype result cannot be presented as a
  fabrication release. No vendor acceptance values are embedded here.

The callable function returns the existing `CheckReport`. Findings include
rule ID, object IDs, and actual/required values where a numeric comparison is
made. `AnglePolicy::Arbitrary` handles finite angles with KiCad's clockwise
`R(-theta)` convention. `QuadrantsOnly` explicitly reports non-quadrant poses
as indeterminate for adapters that have not yet proven arbitrary-angle support.

The contract covers body collision, annular-ring minimum, drill-to-drill
clearance, copper against Edge.Cuts/cutouts, missing body/process inputs, and
angle support. It does not claim solder-mask registration, heatsink contact,
press-fit tolerances, solder-wave keepout, or vendor qualification; those
properties require additional native fields and reviewed process limits.

## Current maintained-board baseline

The first real saved candidates are replayed by `replay.py` with KiCad
10.0.4's pcbnew API and the Rust truth function. Raw JSON-lines output is in
`baseline-real.ndjson`; the summarized counts are in `baseline-real.json`.
The current boards all fail at least one exact copper/outline check, and the
prototype process envelope adds a qualification indeterminate. This preserves
real failures rather than treating missing fabrication qualification as a pass.

| unit | saved candidate | sha256 | current P2 result |
|---|---|---|---|
| RTD | `rtd/unit/candidate/section.kicad_pcb` | `d9908e58335fc9e20d9d786af4423ba8844d7ee893a08dc99472a3dd357653cb` | INDETERMINATE: native extraction pending |
| current-sense | `current-sense/candidate/section.kicad_pcb` | `ce54a8983876bc750e6b37857599d7e404e8bf846ddfd2ea2b96535a7552f623` | INDETERMINATE: native extraction pending |
| voltage-sense | `voltage-sense/candidate/section.kicad_pcb` | `ef9853e9fb03df4f7723076ac8eb77c17743465a0b2e146cec11d2da54876e1f` | INDETERMINATE: native extraction pending |
| thermal-sense | `thermal-sense/candidate/section.kicad_pcb` | `09eb0c3485aed367f2a33732c89d4820ff88a7a1114e534d62ac0ce43713964c` | FAIL with qualification indeterminate |
| interlock | `interlock/candidate/section.kicad_pcb` | `09017d5c8ffa4414220adab11190829bb603e2e7063588f3838a75650fbfbe87` | INDETERMINATE: native extraction pending |
| gate-drive | `gate-drive/candidate/section.kicad_pcb` | `5cf179bd8318b936f36b83e7ac18301fecdbab180d3f00c1811a9f4fcb862495` | INDETERMINATE: native extraction pending |
| power-entry | `power-entry/candidate/section.kicad_pcb` | `8c36944562814d0871232758a9bd11bd2a2903993d9e4dae65f0857af54494cf` | INDETERMINATE: native extraction pending |

Replay command:

```bash
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 \
  zapote/validation/p2/replay.py
```

The adapter records the seven board hashes, pcbnew version, evaluated native
populations, and every object-level finding. It calls `validate(&input)` once
per board and keeps each report alongside native DRC evidence.
