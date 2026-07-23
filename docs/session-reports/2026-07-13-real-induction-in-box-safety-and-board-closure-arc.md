---
title: "Session Report: Real Induction Safety Path, In-Box Verification, and Board-Closure Gates"
date: 2026-07-13
status: in-progress
---

# Session Report: Real Induction Safety Path, In-Box Verification, and Board-Closure Gates

## Executive summary

This arc turned the real-induction-cooker work from a set of historical driver
notes and simulation ideas into a fail-closed, in-the-box-first implementation
path. The UCC21550 contract now defines the live interface; the RTD fault path
has both firmware and independent hardware action; portable ngspice models
cover the relevant timing/fault logic; and the board flow refuses to place or
route a KiCad PCB that has not imported the generated safety design.

The work does **not** claim physical closure. Real waveform integrity, GPIO
electrical behavior, component tolerance, isolation geometry, EMI, and final
PCB DRC remain hardware/EDA measurements. The decisive improvement is that
unmeasured or stale-board states now stop the flow rather than becoming a false
success.

## Decisions made

| Decision | Rationale | Consequence |
| --- | --- | --- |
| UCC21550 contract supersedes L6491 history | The actual gate driver, polarity, supplies, and shutdown ownership must be explicit before implementation. | The historical L6491 content is reference only. |
| Use firmware **and** hardware RTD fault handling | Firmware provides diagnosis and telemetry; a comparator/latch path provides bounded, independent action when firmware or SPI fails. | `RTD_HW_FAULT` participates in the dominant safety latch. |
| In-the-box first | Simulation, static contracts, property tests, and CLI gates should eliminate model/software errors before bench time. | Hardware-only claims are clearly named rather than used to block all progress. |
| Fail closed on stale board imports | An Atopile netlist and a manually maintained KiCad board can drift. | The clean flow checks generated-netlist/PCB parity before it routes. |
| KiCad DRC tool failure is UNMEASURED | A crashed or unparsable KiCad run cannot prove a clean board. | No zero-DRC claim is emitted when KiCad cannot measure. |

## What was built

### 1. Gate-driver and RTD safety contract

The live interface is documented in:

- `docs/hardware/UCC21550_INTERFACE_CONTRACT.md`
- `docs/hardware/RTD_SAFETY_DUAL_PATH.md`
- `docs/plans/2026-07-13-013-feat-ucc21550-latch-sensors-supply-plan.md`

The contract covers signal polarity, gate-disable behavior, latch ownership,
supplies, sensor-fault response, and the isolation boundary. It makes the
hardware safety behavior reviewable without inferring it from obsolete driver
notes or firmware control flow.

### 2. Dual-path RTD fault design

The generated Atopile design adds:

```text
REF2025 + TPS3700
        │
RTD window comparators (2 × TLV3201)
        │
SN74LVC1G08 / SN74LVC1G38
        │
RTD_HW_FAULT ──► fault OR ──► dominant shutdown latch ──► gate-drive inhibit

MAX31865 diagnostics ──► firmware state machine / telemetry
```

The two routes are intentionally complementary:

- Firmware reads MAX31865 status, classifies sensor conditions, records
  diagnostics, and handles controlled recovery.
- The analogue logic asserts `RTD_HW_FAULT` without depending on firmware
  scheduling, SPI correctness, or firmware fault classification.

The design uses REF2025, TPS3700, two TLV3201 comparators, SN74LVC1G08,
SN74LVC1G38, and a second SN74HC4075 in the existing safety-latch path.

### 3. Simulation and property-oriented verification

Portable ngspice models were established under `simulation/models/` for the
gate-driver timing and RTD safety chain. Tests exercise threshold/window and
transient behavior, including the dead-time component selection. This is the
right evidence for logic polarity, timing calculations, and regression-safe
model behavior; it is not a substitute for a physical probe at the driver.

Property-based tests were used where the invariant is broad rather than an
example-specific waveform: the board-safety parity gate is tested against
arbitrary required-net removals and arbitrary component counts below the
required minimum. A stale board must be rejected for every such generated
case, not only a curated fixture.

### 4. Real-board import/parity preflight

`packages/temper-placer/src/temper_placer/validation/real_board_inventory.py`
implements a non-negotiable preflight:

```python
validate_kicad_safety_parity(netlist_path, pcb_path)
```

It checks that the generated netlist and actual PCB agree on required safety
nets and minimum component-family counts. `scripts/run_clean_flow.sh` runs it
as Step 0.

The current root board is correctly rejected because it has not imported the
new safety path. Missing evidence includes `RTD_HW_FAULT`, RTD force/sense
nets, `SHUTDOWN`, and component families REF2025, TPS3700, TLV3201,
SN74LVC1G08, SN74LVC1G38, and the additional SN74HC4075.

### 5. Place-to-route fail-closed repairs

The real-board route path was repaired so it no longer gives a synthetic or
misleading answer:

- The missing placement-legalization import target is a non-mutating collision
  audit; it must not force-move components beyond CP-SAT constraints.
- Placement auditing evaluates every component.
- The loop routes the provided KiCad board, applies CP-SAT positions to that
  board, and emits the corresponding routed PCB content.
- CLI success requires a loop result and a DRC report without errors.
- Feedback classification distinguishes real DRC violations from a complete
  route and cannot call an unmeasured board clean.

Before the generated-safety parity gate was introduced, the real flow routed
24/24 nets and emitted `pcb/temper_placed.kicad_pcb`. KiCad 10.0.4 then crashed
while running board DRC (`Array index out of range`). That result is recorded
as unmeasured, not zero DRC.

### 6. KiCad schematic serialization recovery

Four hierarchy sheets contained invalid embedded power symbols. A library
qualified parent name, such as `power:GND`, must have an unqualified child-unit
name, `GND_0_1`; the malformed files used `power:GND_0_1`. Their power symbols
also used an invalid pin-level effects layout.

Repaired:

| File | KiCad netlist export |
| --- | --- |
| `pcb/half_bridge.kicad_sch` | passes (annotation warning only) |
| `pcb/power_management.kicad_sch` | passes (annotation warning only) |
| `pcb/safety_interlock.kicad_sch` | passes (annotation warning only) |
| `pcb/sensing.kicad_sch` | power-symbol error repaired; another malformed record remains |

The sensing sheet is not declared healthy. The original failure is gone, but
KiCad still returns `Failed to load schematic` without a line diagnostic.

## Evidence obtained

| Check | Result |
| --- | --- |
| Atopile generation / `make netlist` | passed (legacy warnings remain) |
| Targeted board-parity and integration tests | 18 passed |
| Wider focused place/route suite | 38 passed |
| Targeted Ruff for newly added parity code/tests | passed |
| `uv run python scripts/import_linter_gate.py` | passed, 0 new violations |
| KiCad sheet exports | 3/4 pass; sensing remains unmeasured |
| Root board physical safety import | blocked correctly by parity preflight |
| Final `kicad-cli pcb drc` | unmeasured; KiCad 10.0.4 crashes |

## Boundaries that remain physical

The following must be measured on a representative assembled board. They are
not gaps in the model test suite; they are model-to-physical validity work:

1. SPI waveform integrity at the MAX31865 and isolation boundary.
2. Actual GPIO voltage levels and UCC21550 enable/latch behavior across supply
   sequencing and brownout.
3. Dead-time component tolerance and temperature drift under the real driver
   supply and switching environment.
4. PCB creepage/clearance, routing, return-current paths, and isolation barrier
   review after the generated safety circuitry is imported.
5. EMI, switching transients, and thermal response at operating power.

## Immediate continuation sequence

1. Repair `pcb/sensing.kicad_sch` through Eeschema using its first new
   diagnostic. Do not guess at custom symbol geometry. Confirm the MAX31865
   exposed-pad mapping before restoring an EP pin.
2. Import the generated Atopile schematic into `pcb/temper.kicad_pcb` using
   KiCad **Tools → Update PCB from Schematic**. `kicad-cli` cannot perform this
   native KiCad operation.
3. Assign footprints and enforce the UCC21550 isolation/routing boundary.
4. Re-run the parity preflight. Only then rerun placement, routing, and DRC.
5. Resolve or upgrade the KiCad 10.0.4 DRC crash before making a final board
   closure claim.
6. Move to bench validation only after the in-box gates report measured,
   consistent artifacts.

## Related records

- `docs/handoffs/2026-07-13-real-induction-board-safety-and-kicad-repair.md`
- `docs/hardware/UCC21550_INTERFACE_CONTRACT.md`
- `docs/hardware/RTD_SAFETY_DUAL_PATH.md`
- `AUTOMATED_PCB_DESIGN_INSTRUCTIONS.md`
