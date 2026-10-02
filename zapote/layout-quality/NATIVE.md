# Native placement and routing feedback

`make -C zapote check-layout` now reads the saved 120 V PCB through KiCad and
computes Rust layout measurements. `make -C zapote check` includes this step
before the five-unit acceptance runner. It does not edit or route the PCB.

```sh
make -C zapote check-layout \
  KICAD_PYTHON=/path/to/python-with-pcbnew \
  LAYOUT_BOARD=power-stage-120v/native-17/section.kicad_pcb \
  LAYOUT_RUN_DIR=/tmp/layout-before

# After an edit, use a new evidence directory and compare with the prior report.
make -C zapote check-layout \
  KICAD_PYTHON=/path/to/python-with-pcbnew \
  LAYOUT_BOARD=/absolute/path/to/edited.kicad_pcb \
  LAYOUT_RUN_DIR=/tmp/layout-after \
  LAYOUT_BASELINE=/tmp/layout-before/report.json
```

On this Mac the runtime is
`/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python`.
The direct CLI is `zapote-layout-quality --native BOARD --python PYTHON
--output NEW_DIRECTORY [--baseline REPORT]`. Paths passed to make are relative
to `zapote/`, or absolute. The output directory must not exist.

Exit 0 means native measurement completed. It is **not board acceptance**:
`status` remains `geometry_evaluated_physical_models_incomplete`. Invalid board,
profile, extraction, or comparison input exits 2. The original model-JSON CLI
retains its separate budget/coverage exit contract in [README](README.md).

## What is connected

KiCad owns world coordinates, flashed copper layers, pad contacts, courtyards,
track/via geometry, and saved zone polygons. The Python file only transports
those facts. Rust owns the endpoint profile, shortest supported paths, resistance,
polygon unions/intersections, dielectric series calculation, metrics and deltas.
All profile endpoint nets match exact names; a source/pinout change requires a
reviewed profile update. This is not a substitute for source-to-native parity.

| Family | Native input and useful feedback | Still missing |
|---|---|---|
| Gate | Driver→resistor→gate paths, pad distances, track R | Mutual L and operating slews for both legs; VGS transient solve |
| Kelvin | Shunt→sense input paths, lengths and track R | Shared current and pickup/transfer models |
| Switch coupling | Unioned filled copper, holes, adjacent layer overlap and declared dielectric stack | Fringing, coplanar/shielded fields and operating dv/dt |
| Decoupling | Supply/return endpoint distances and supported routed paths | Effective C, ESR/ESL and complete branch inductance |
| Returns | Actual supported track/via paths; explicit gaps when no path is reconstructed | Zone interiors, interior T-junctions, pad barrels, common-current model |
| Copper | Every straight track's uniform-conductor R at 20 °C | Zone/pad/via current distribution, plating, crowding, AC and thermal solution |
| EMI | Raw/filtered net projected adjacent-layer overlap | Magnetic bypass and victim transfer impedance |
| Thermal | Named heater/victim component distances | Losses, assembly heat transfer and drift coefficients |
| Assembly | Same-side native courtyard gap within 5 mm and overlap area | 3D bodies, hardware, tolerances and access envelopes |

These are geometric measurements and explicitly bounded calculations. They do
not automatically supply all nine original model kernels with physical inputs.
Missing geometry/model adapters are software work, not merely bench qualification.
Five millimetres is a reporting window, not an assembly acceptance threshold.
A pair leaving that window is reported as removed, never as improvement to zero.

Paths include straight links from native track endpoints to pad centres; R only
includes track copper. They are shortest paths in the supported graph, not proof
of the shortest path through the entire conductor. A failed reconstruction does
not declare an electrical open. Native copper graphics and unsupported routed
items are explicit gaps. Zone geometry uses saved fills: refill in KiCad after
edits that invalidate them. Polygonization uses 1 µm error; the projected C model
is neither an upper bound nor a complete coupling estimate. Zero projected
overlap does not mean zero real coupling.

## Provenance and repeatability

Every run retains extractor stdout/stderr, command, PCB SHA-256, snapshot hash,
extractor hash, KiCad version, evaluator binary hash, source revision/dirty state,
runtime and report. Board/extractor bytes must remain unchanged through capture.
Deltas require identical evaluator/extractor hashes and profile/schema; rebuilds
require remeasuring both candidates. Added/removed metrics retain null endpoints.
Do not compare debug and release reports as if the evaluators were identical.

Object ordering is normalized before graph construction and polygon union.
Electrical dimensions come from the saved ordered stackup; adjacent capacitance
uses the sum of dielectric thickness/epsilon between copper surfaces. Duplicate
copper overlap is unioned, holes are retained, and unflashed copper is excluded.

## Retained live evidence

[Native-17 report](native-evidence/native17-report.json): KiCad 10.0.4,
PCB SHA-256 `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
Release execution took 2.252 s on this host, including native extraction and
report persistence. This is one wall-clock observation, not a benchmark claim.
The run evaluated 135 footprints, 412 non-NPTH pad records (including records
without flashed copper), 641 tracks, 177 vias, 25 zones and 1,931 copper
object/layer records. It produced 1,326 metric rows and 22 reconstructed paths;
13 requested paths remain uncomputed.

- Driver→resistor lengths: A-high 38.233 mm, A-low 44.270 mm,
  B-high 30.798 mm, B-low 35.413 mm. Each resistor→gate segment is 6.9225 mm.
- Shunt-positive and shunt-negative paths: 77.229 and 70.269 mm.
- No positive courtyard overlaps or projected adjacent-layer overlaps for the
  selected coupling pairs were found. These narrow results are not 3D clearance
  or electrical noise verdicts.

[Live mutation proof](native-evidence/native-edit-proof.tar.gz) and
[test log](native-evidence/native-edit-test.log): a scratch copy halved the width
of gate track `9361b75b-b449-49c0-97f1-f1cc3ed83759`. Section resistance changed
from 0.000808125 to 0.00161625 Ω; A-high driver-path track resistance rose by
0.000808125 Ω. The test verified the original PCB bytes stayed unchanged.
The archive contains the changed PCB, both native snapshots/reports and logs.

[Tests](native-evidence/native-tests.log) include two PBT properties run with
2,048 cases each, independent rectangular-area and uniform-conductor formulas,
one-nanometre gaps, net/layer separation, actual-board replay, object permutation,
holes/union, stale hashes, wrong profile, duplicate IDs/pins and delta semantics.
The compressed native fixture is captured KiCad output, not hand-authored JSON.
The live test is ignored by default because it needs KiCad; explicitly run it:

```sh
KICAD_PYTHON=/path/to/python-with-pcbnew cargo test --locked \
  --manifest-path zapote/Cargo.toml -p zapote-harness \
  --test layout_native_cli -- --ignored --nocapture
```

The broader integration audit is [INTEGRATION-AUDIT.md](INTEGRATION-AUDIT.md).
