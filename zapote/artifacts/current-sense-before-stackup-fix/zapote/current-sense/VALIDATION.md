# Current-sense validation contract

Run from the repository root. KiCad 10.0.4 and the pinned Atopile 0.2.69 build produced this revision. Supply a separate output path for every replay; the input builder refuses to overwrite an existing artifact.

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --manifest-path zapote/Cargo.toml --workspace
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --manifest-path zapote/Cargo.toml -p zapote-harness --example current_sense_input -- \
  zapote/current-sense/candidate/source-manifest.json \
  zapote/current-sense/circuit/current_sense_profile.json \
  zapote/current-sense/evidence/native-final.json \
  zapote/current-sense/circuit/model_output.json \
  /tmp/current-sense-input-new.json
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --manifest-path zapote/Cargo.toml -p zapote-harness --bin zapote-rtd -- \
  --current-sense-input /tmp/current-sense-input-new.json \
  --output /tmp/current-sense-report-new.json --no-telemetry
```

The validator exits nonzero for INDETERMINATE as well as FAIL. Inspect the report; do not relabel an indeterminate result as PASS because it has no hard findings. The native extraction must be regenerated if the board changes. `tools/run_current_sense_native_checks.py` retains exact commands and validates real KiCad report schemas. On this host native PCB DRC crashed inside the restricted sandbox; the same installed runtime succeeded outside it. A process crash was retained as a tool failure, not a DRC result.

## Implemented checks

| Area | Current evidence / scope |
|---|---|
| Source and native identity | Complete component/pad/net census, strict source pin map, MPN identity, original JSON hashes and normalized projection equality |
| Physical connectivity | Native copper clusters for the source endpoints; 12 multi-endpoint nets require physical copper; unused OR outputs remain intentionally unconnected |
| Electrical model | Independent Rust recomputation of both polarity thresholds and bounded loading, source value binding including the series resistor, fixed 45–55 A requirement |
| Copper clearance | Shape-aware pad/track/via/filled-zone pairs on common copper layers, including zone boundaries and holes |
| Primary-to-LV corridor | 12.6 mm minimum XY copper separation across layers, including GND pours; not assembled insulation certification |
| Native geometry | Two copper layers, allowed layers, positive finite geometry, minimum 0.25 mm track width, explicit supported pad-shape mapping |
| Placement locality | Authored center-distance guards: comparator bypass capacitors within 5 mm of their IC centers, OR bypass within 8 mm; these are placement guards, not impedance/timing qualification |
| Native KiCad | ERC, DRC, all-track errors and schematic parity; three final runs on unchanged inputs |

The current-sense path registers 11 rule families. Rule count is not test count and neither proves universal electrical correctness. Unsupported curved copper or unsupported pad shapes are rejected by the transport/validators rather than silently approximated. Mechanical assembly and thermal/current capability remain outside the completed digital checks.

## Negative controls

The corpus includes source pin/net mutations, changed bias values, rehashed contradictory model claims, missing native shape metadata, removed copper, duplicate parts, and a JSON round-trip test of the full real input. Geometry tests cover raw KiCad-to-donor enum mapping, rounded pads, trace/via crossings, filled-zone crossing without an interior route vertex, holes and cross-layer isolation. Real-board regressions insert the original via-through-supply-track mistake and a back-layer ground intrusion beneath the transformer primary. Both must fail the normal Rust validation path.

Changing or removing normalized profile limits cannot retain the owner's original artifact identity. The harness rebuilds the full profile projection before applying the rules. JSON uses exact floating-point round-trip parsing so serialization noise cannot manufacture a source mismatch.

## Physical gaps

The conditional numerical result does not include unspecified transformer transfer tolerance, frequency dependence, hot clamp leakage or bounded comparator hysteresis. Offset/CMRR applicability at the actual supply/common mode is conditional. Complete shutdown latency, startup/brownout response, primary copper/termination temperature, CT saturation and assembled insulation are INDETERMINATE or NOT RUN. The host monitor load and cable/ADC interface require independent qualification.
