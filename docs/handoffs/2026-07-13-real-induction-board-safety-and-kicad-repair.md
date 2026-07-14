---
date: "2026-07-13"
topic: real-induction-board-safety-and-kicad-repair
status: handoff
---

# Handoff: Real Induction Board Safety and KiCad Recovery

## Current state

The UCC21550 and RTD safety implementation is built and verified in-box, but
the physical KiCad PCB has **not** imported the generated safety design. The
board flow now stops at that boundary rather than routing a stale board.

- Generated electrical design: UCC21550 shutdown contract plus dual-path RTD
  fault containment (firmware diagnosis and an independent hardware latch).
- Board-flow preflight: `validate_kicad_safety_parity()` rejects a KiCad PCB
  missing the required generated safety nets or component families.
- Three malformed KiCad hierarchy sheets now parse; `pcb/sensing.kicad_sch`
  still has another malformed record after its reported power-symbol error was
  repaired.
- Final physical-board DRC is unmeasured: installed KiCad 10.0.4 crashes while
  running it. This must never be reported as zero DRC.

No ECO calls were made, per the project-owner instruction.

## What was implemented

### Hardware safety path

The Atopile design adds a default-safe RTD hardware fault path:

```text
REF2025 + TPS3700 → TLV3201 window comparators → LVC fault logic
                                                 → RTD_HW_FAULT
                                                 → OR → dominant safety latch
                                                 → SHUTDOWN / UCC21550 DIS

MAX31865 → SPI/DRDY → firmware diagnostics, telemetry, recovery policy
```

The comparison/fault components are REF2025, TPS3700, two TLV3201s,
SN74LVC1G08, SN74LVC1G38, and a second SN74HC4075. Firmware retains the
MAX31865 diagnostic path but cannot override the hardware latch.

Authoritative records:

- `docs/hardware/UCC21550_INTERFACE_CONTRACT.md`
- `docs/hardware/RTD_SAFETY_DUAL_PATH.md`
- `docs/plans/2026-07-13-013-feat-ucc21550-latch-sensors-supply-plan.md`

### In-box verification

- Portable ngspice RTD and UCC21550 models/tests are under `elec/validation/`
  and the relevant simulation documentation.
- The real-board inventory/parity gate is in
  `packages/temper-placer/src/temper_placer/validation/real_board_inventory.py`.
- Property-based tests cover arbitrary removal of required safety nets and
  insufficient component-family counts.
- The place-to-route loop now routes the supplied board with CP-SAT positions,
  fails closed on missing reports/DRC errors, and does not claim a clean board
  from an unmeasured result.

## Measured results

```text
Firmware CTest:                                  13/13 passed
Focused safety/parity/place-route Python suite:  49 passed
Atopile `make netlist`:                          passed (legacy warnings only)
Import-boundary gate:                            passed, 0 new violations
```

The actual root board is deliberately rejected by the new parity gate because
it lacks `RTD_HW_FAULT`, RTD force/sense nets, and the generated reference,
rail-monitor, comparator, and LVC logic families. This is the correct result.

## KiCad serialization work

Repaired files:

| Sheet | Result |
| --- | --- |
| `pcb/half_bridge.kicad_sch` | `kicad-cli sch export netlist` succeeds. |
| `pcb/power_management.kicad_sch` | succeeds. |
| `pcb/safety_interlock.kicad_sch` | succeeds. |
| `pcb/sensing.kicad_sch` | original power-unit-name failure fixed; another parse failure remains. |

The faulty symbols had library-qualified child names such as
`power:GND_0_1`; KiCad requires the child name `GND_0_1`. Their pin effects
layout was also normalized to KiCad's native embedded-symbol format.

For sensing, do not guess at a fix. The MAX31865 symbol/instance mismatch
(orphan pin 21) was removed, but KiCad still reports a generic load failure.
Open it in Eeschema and use the first new diagnostic. If a custom symbol is
named, replace it from the local library (`max31865/MAX31865.kicad_sym` or
`components/ADUM1250/ADUM1250.kicad_sym`) rather than editing its geometry by
hand. Verify the MAX31865 exposed-pad mapping before adding an EP pin.

## Next sequence

1. Repair and netlist-export `pcb/sensing.kicad_sch`.
2. In KiCad, use **Tools → Update PCB from Schematic** to import the generated
   safety design into `pcb/temper.kicad_pcb`. `kicad-cli` cannot perform this
   native KiCad update.
3. Assign footprints and enforce the documented UCC21550 isolation/routing
   boundary.
4. Re-run the parity preflight, then place/route/DRC the imported board.
5. Resolve the KiCad DRC crash or use a KiCad version that measures the board.
6. Only then bench-test SPI integrity, actual GPIO/latch levels, dead-time
   tolerance, isolation, EMI, and high-power thermal behavior.

## Related compound record

- `docs/session-reports/2026-07-13-real-induction-in-box-safety-and-board-closure-arc.md`
- `docs/solutions/architecture-patterns/dual-path-rtd-fault-containment-2026-07-13.md`
- `docs/solutions/tooling-decisions/generated-safety-netlist-to-pcb-parity-gate-2026-07-13.md`
