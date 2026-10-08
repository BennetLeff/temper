# Layout-quality checks

**Start here:** [all Zapote checks and commands](../CHECKS.md).
For saved boards, use [native geometry](NATIVE.md) or
[native current / resistance / loss](CURRENT.md); the latter includes geometry.
[Latest native evidence](mesh-evidence/README.md) contains the actual board runs
and mutation proofs. The supplied-model mode below is a separate entry point.

Nine advisory Rust checks for comparing Zapote placement and routing candidates.
Implementation: `zapote-drc::layout_quality`. Batch CLI: `zapote-layout-quality`.
These checks do not place or route the board and do not modify native artifacts.
For direct saved-board feedback, use the [native integration](NATIVE.md):
`make -C zapote check-layout`. It now runs under `make -C zapote check` and
supports board-to-board deltas. The [integration audit](INTEGRATION-AUDIT.md)
separates executed checks, missing inputs and unconnected kernels.
The [validation record](evidence/README.md) includes tests, benchmarks, lint
limitations and the native-17 example output.

## Supplied-model mode

From the repository root:

```sh
cargo run --release --locked --manifest-path zapote/Cargo.toml \
  -p zapote-harness --bin zapote-layout-quality -- \
  zapote/power-stage-120v/native-17/section.kicad_pcb \
  < zapote/layout-quality/native17-unit-slew.json
```

This example deliberately exits **2**: the existing leg-A extraction provides one
unit-slew sensitivity case, while eight requested families have no supplied inputs.
It reports 6.8372 V induced EMF for the declared simultaneous 1 A/ns port slews.
That is not an operating waveform or MOSFET VGS. The example uses the native-17
presentation board hash; its copper is the electrical revision's copper.

To evaluate just that sensitivity, set `required_checks` to `["gate_coupling"]`.
Exit 0 means all requested families evaluated and no supplied budget was exceeded;
it does **not** mean the board is safe. Exit 1 means a budget was exceeded. Exit 2
means bad input, stale board binding, invalid calculations or missing coverage.
Case errors are retained beside successful cases. Batch identity/JSON errors are
sent to stderr without emitting a partial report.

This supplied-model mode verifies the full SHA-256 of saved board bytes and records the request's
SHA-256. It does not parse KiCad or prove the supplied model was extracted from
those bytes. `source_revision`, `basis`, object identities and `assumptions` must
identify that provenance. Prepare a fresh input after relevant geometry, BOM,
stackup, operating-point or assembly changes. Missing model data stays missing.

## Inputs, results and boundaries

Every request has schema version 1, board SHA-256, source revision, required check
families and cases. Each case has an ID, basis, nonempty assumptions, a tagged
scenario (`kind`, `parameters`) and a list of budgets. All structs reject unknown
JSON fields. Public typed structs are the authoritative schema; the tests include
an all-nine-family serialization example.

| Family | Supplied model | Metrics / object witnesses | Important boundary |
|---|---|---|---|
| `gate_coupling` | Signed mutual inductances and simultaneous current slews | Signed EMF, absolute-sign bound, dominant port | No VGS/Miller/driver transient solve; use the existing extracted multiport/SPICE workflow for that |
| `kelvin_sense` | Shared R/L, magnetic pickup, two capacitive pickups, resistive input transfer, shunt value | Differential input error and equivalent trip-current error | Resistive transfer approximation only; no implicit RC bandwidth |
| `switch_coupling` | Nonoverlapping filled rectangular patches, surface z, uniform dielectric, differential slew | Per-pair projected C, total projected displacement current | No fringing, shielding, coplanar extraction or multi-dielectric stack; not a coupling bound |
| `decoupling` | Effective C, complete branch ESR/R and ESL/L, frequencies | Complex supply Z and each branch's current participation | Independent series-RLC branches; no shared/mutual L. Sweep maximum covers supplied frequencies only |
| `return_path` | Continuous native 3D polyline and shared R/L terms | Length, detour and shared disturbance | Chord reference ignores routing obstacles; supplied path must establish connectivity |
| `copper_distribution` | Connected resistance graph, section areas and balanced currents | Node V, per-edge I/J/loss, total loss and KCL residual | DC lumped sections; no spatial crowding within an unmeshed section, AC effects or temperature solution |
| `emi_bypass` | Magnetic/electric coupling plus victim transfer-impedance bound | Independent-sign bypass voltage and contributions | Pickup screen, not insertion loss or regulatory EMI prediction |
| `thermal_influence` | Assembly-specific thermal transfer coefficients, losses and drift coefficients | Temperature, drift and dominant heater | Linear steady-state model within an explicit temperature interval; no invented airflow/contact properties |
| `assembly_margin` | Oriented bodies represented by 3D axis-aligned envelopes, tolerances and access | Worst-case signed separation and object pairs | Conservative boxes/access reservations, not exact body collision; positive separation is Euclidean, negative penetration is minimum axis translation |

Rectangle patches must represent actual filled material, not the bounding boxes
of tracks/pads/zones. Subdivide without overlap and exclude holes. Coordinates
are already in board space: this code does not apply another KiCad rotation.
For arbitrary polygons or accurate coupling, supply field-extracted terms to the
electrical kernels. Native mode now provides polygon-based adjacent-layer
projections using its own KiCad capture; field extraction remains separate.
The board's existing coarse copper census is not used for these projections.

For copper, a section area must be actual conducting area. A via/barrel section
requires its plated area, not the drill area. Use `resistance_ohm()` only for
uniform conductors; spreading resistance comes from an appropriate discretization
or external extraction. `Network::new()` factors once and `solve()` reuses that
factor for repeated candidate load cases. Do not re-factor for each waveform
sample when the resistance graph is unchanged.

## Budgets

Metrics remain separate: no weighted score can trade insulation or noise margin
for appearance. With no budget a case is `unscored`. `within_budgets` applies only
to supplied budgets under the stated model; unbudgeted metrics are still advisory.
Negative margin means a violated budget. A misspelled metric is an error.

Available metric keys (units are part of the name):

- Gate: `pickup_magnitude_v`, `independent_sign_bound_v`.
- Kelvin: `sense_error_magnitude_v`, `current_error_bound_a`.
- Switch: `projected_capacitance_pf`, `projected_displacement_a`.
- Decoupling: `sampled_peak_impedance_ohm`.
- Return: `detour_ratio`, `shared_voltage_bound_v`.
- Copper: `total_loss_w`, `peak_section_current_density_a_per_mm2`.
- EMI: `bypass_voltage_bound_v`.
- Thermal: `temperature_c`, `drift_magnitude_ppm`.
- Assembly: `minimum_gap_lower_bound_mm` (minimum budgets only).

Budget format: `{"metric":"current_error_bound_a","direction":"maximum","limit":1.0}`.
Limits come from the reviewed design's actual error/thermal/noise budgets; this
library does not choose universal thresholds. Check every required operating case
and both bridge legs: family coverage alone does not prove case completeness.

## Correctness and performance

All numerical inputs and derived outputs are checked for finiteness. Empty
required populations, duplicate identities, invalid model domains and disconnected
networks are rejected. A known-zero effect needs an explicit zero-valued term.
Missing evidence cannot become an empty successful result.

The copper solver uses diagonally scaled grounded Cholesky, checks every node's
KCL residual and rejects ill-conditioned factorizations. It supports up to 512
nodes: O(V³ + E) preparation and O(V² + E) per solve. Use the field-solver pipeline
for larger copper meshes. Geometry sweeps prune x-disjoint pairs; they are
O(n log n + candidate pairs), with quadratic worst cases. Outputs retain stable
object order or explicitly sorted severity/identity order.

```sh
PROPTEST_CASES=2048 cargo test --locked --manifest-path zapote/Cargo.toml \
  -p zapote-drc --test layout_quality --test layout_quality_copper \
  --test layout_quality_electrical --test layout_quality_geometry --test layout_quality_report
cargo test --locked --manifest-path zapote/Cargo.toml \
  -p zapote-harness --test layout_quality_cli
cargo bench --locked --manifest-path zapote/Cargo.toml \
  -p zapote-drc --bench layout_quality
```

Tests include independent closed-form parallel/Wheatstone networks, energy and KCL
conservation, ground/orientation changes, conductor and rectangle subdivision,
geometry sweep versus exhaustive pairs, thermal monotonicity, antiresonance,
invalid inputs, report coverage, and an actual native-17 board hash/CLI witness.
The recorded matrix is a production-shaped input, not an independent physical
oracle. No numerical test here establishes the accuracy of a supplied field or
thermal model.

Primary physical references: TI UCC21550 datasheet (supply/layout sections),
https://www.ti.com/lit/ds/symlink/ucc21550.pdf ; Analog Devices AN-136,
https://www.analog.com/en/resources/app-notes/an-136.html . The specific model
approximations and unit conversions above are part of this library's contract.
