---
title: "Thermal-analysis corrections — per-footprint R, decided 80/85/120 °C margins, 60 °C ambient"
date: "2026-08-15"
category: evidence
module: temper_placer
problem_type: defect
component: thermal_analysis
severity: high
applies_when:
  - "auditing placer thermal metrics (measure_thermal / ThermalMetrics)"
  - "deciding what junction-temperature margin means on this board"
  - "reviewing the 150 °C margin family retired by the thermal threshold decision"
tags:
  - thermal
  - thermal-margin
  - junction-temperature
  - oracle-repin
  - honest-red
---

<!-- provenance: commit=25597894b dirty=false (record written at the thermal-corrections branch tip after the Rust table commit; the Python wiring commits below it) -->

# Thermal-analysis corrections (2026-08-15)

The safety-assertion audit found the placer's thermal analysis
(`packages/temper-placer/src/temper_placer/metrics/physics.py`,
`measure_thermal`) carried three defects, all in the same direction as the
wider audit: **a running analysis asserted a wrong safety value with an
implied authority attached**. Each defect made the analysis *look* safer
than the board is.

## Defect 1 — flat thermal resistance for every component

Pre-correction, `measure_thermal` applied the same
`Rjc=0.6 / Rch=0.25 / Rha=1.0` K/W stackup to **every** device. Real
components differ by an order of magnitude:

- IKW40N120H3 TO-247 IGBT: `Rjc = 0.31` K/W (datasheet).
- LMR51430 buck (SOT-23-ish): ~80 K/W junction-to-ambient through the PCB.

The fix adds a per-footprint thermal-properties table in Rust
(`packages/temper-thermal/src/thermal_properties.rs`, exposed as
`temper_thermal.lookup_thermal_properties_py`), **keyed by footprint, not
refdes** (designators are unstable across branches — handoff §6). Each
entry records its provenance (datasheet / repo table / UNSOURCED). The
legacy flat stackup survives only as the *fallback* for footprints with no
table entry, explicitly labelled UNSOURCED, so an unknown footprint
degrades to old behaviour instead of being silently assigned a value.
The Rust kernel (`measure_thermal_edges`) now accepts optional per-device
`rjc/rch/rha/copper` arrays; `None` keeps the legacy flat stackup
bit-identical for the pinned differential.

## Defect 2 — margin computed against 150 °C "typical shutdown"

Pre-correction: `thermal_margin_c = 150.0 - max_tj` with the comment
"150C is typical shutdown". The thermal threshold decision
(`docs/evidence/2026-08-15-thermal-threshold-decision.md`) established:

- **150 °C is the IKW40N120H3 *storage* temperature (Tstg = −55…+150 °C),
  not a junction limit.** The datasheet's Tvj(max) is **175 °C**.
- The governing protection chain is: **80 °C firmware trip** (decided;
  `OVER_TEMP_THRESHOLD` moves 100 → 80 °C so the firmware layer is live
  ahead of the hardware latch) → **85 °C hardware THM-01 latch** (wired,
  sim-verified) → **125 °C fault-state backstop**.

The fix computes three margins against the limits the repo actually
protects at:

- `thermal_margin_c` — margin to the decided firmware trip (**80 °C**).
- `thermal_margin_touch_c` — margin to the heatsink touch/trip temp
  (**85 °C**, `FUNCTIONAL_TEST_CRITERIA.md` §2.3).
- `thermal_margin_component_c` — margin to the component limit
  (**120 °C**, coil NTC trip per the same table).

Note: the firmware edit itself (100 → 80 in `safety.c`) is a **separate
pending task**; the analysis targets the decided value, not the
pre-decision `100.0f` still in the firmware tree. This is deliberate: a
margin against the current 100 °C would silently re-encode the dead-code
threshold the decision retired.

## Defect 3 — ambient 40 °C instead of the worst-case design ambient

Pre-correction default `ambient_temp_c = 40.0`. The repo's worst-case
design ambient is **60 °C** (`docs/guides/THERMAL_DESIGN_GUIDE.md` §2.2,
"Worst case design | 60 °C | Design limit");
`docs/ENVIRONMENTAL_SPEC.md` §1.1 allows 40 °C at rated power with linear
derating to 0 % at 60 °C — so 60 °C is the correct worst-case analysis
ambient. Fixed to `60.0`.

## Verification

- The Python oracle `tests/metrics/_physics_py_oracle.py` is re-pinned in
  the same PR (the keep-in-sync convention; the generator is
  `scripts/update_oracle_hashes.py` and the diff is what a reviewer sees).
  The oracle imports the corrected constants (`FIRMWARE_TRIP_C`,
  `TOUCH_TEMP_C`, `COMPONENT_MAX_C`) and the corrected per-footprint
  lookup from the live module, so it tracks the decided values by
  construction.
- `tests/metrics/test_physics_rust_differential.py` asserts bit-identity
  between the Rust kernel and the oracle across all five fields
  (`max_junction_temp_c`, `thermal_margin_c`,
  `thermal_margin_touch_c`, `thermal_margin_component_c`,
  `edge_distance_avg_mm`).
- `tests/metrics/test_physics.py` updated: unmeasured sentinel now returns
  `max_junction_temp_c == 60.0` (worst-case ambient), margin 0.0.

## Out of scope (separate follow-ups)

The decision doc also lists 150 °C / 40 °C in other analysis paths not
touched by this PR:

- `physics/parameter_bounds.py:259` `T_j_max = 150.0`
  (`compute_thermal_soundness`, FDM corner check).
- `physics/operating_point.py:89` `T_j_max = 150.0` and
  `T_amb = 40.0` (OperatingPointGate defaults).
- `validation/results/battery_run.py:245,705` `T_j_max = 150.0`.
- `temper-thermal/src/thermal_edges.rs` + `tj_cross_check.rs` tests.
- `elec/src/constraints.ato` `igbt_max_temp = 423.15 K` (150 °C).

These are deliberate, separate decisions per path (each has its own
callers/tests/oracles); they were left untouched to keep this PR
attribution-clean. See
`docs/evidence/2026-08-15-thermal-threshold-decision.md` §2 for the full
inventory.
