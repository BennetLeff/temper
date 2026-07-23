---
title: "Dual-Path RTD Fault Containment: Firmware Diagnoses, Hardware Inhibits"
date: 2026-07-13
category: architecture-patterns
module: elec/src/modules.ato
problem_type: architecture_pattern
component: induction-safety
severity: high
applies_when:
  - "A sensor fault must stop power conversion even if the application processor, SPI bus, or firmware state machine is impaired"
  - "A digital temperature frontend provides rich status but is not the sole protection mechanism"
  - "A shutdown latch already exists and can accept a sensor-fault contributor"
tags:
  - rtd
  - max31865
  - hardware-safety
  - firmware-safety
  - fault-containment
  - ucc21550
  - induction-cooker
---

# Dual-Path RTD Fault Containment: Firmware Diagnoses, Hardware Inhibits

## Context

An RTD frontend such as MAX31865 offers precise measurement and diagnostic
status, but its useful information reaches the controller through a powered
digital path. A stalled state machine, corrupted SPI transaction, missed
interrupt, or power-sequencing defect can delay that path. For an induction
power stage, temperature protection must still reach the gate-drive inhibit
path under those conditions.

The solution is not to discard the firmware path. Firmware is the correct
place for fault classification, telemetry, UI behavior, and recovery policy.
The safety error was treating it as the only physical containment mechanism.

## Pattern

Implement two independent consumers of the sensor condition:

```text
RTD electrical condition
 ├── MAX31865 → SPI/DRDY → firmware → state-machine fault/telemetry
 └── reference + comparators → fault logic → dominant hardware latch → inhibit
```

The hardware path must have all of the following properties:

1. **Independent detection.** It derives an out-of-window condition from the
   analogue sensor electrical state, not a decoded firmware register.
2. **Defined supplies.** Its reference and supervisor behavior are specified;
   an unpowered/undervoltage comparator cannot be silently treated as healthy.
3. **Default-safe logic.** The combination logic makes loss of a valid window
   assert the fault, rather than needing firmware to create a fault pulse.
4. **Dominant shutdown.** The result is ORed into the existing safety fault
   latch such that a software enable cannot override it.
5. **Recovery policy separation.** Hardware may latch until a deliberate reset;
   firmware may report and sequence recovery but never bypass the latch.

In Temper, REF2025 and TPS3700 support the comparison environment, two
TLV3201 comparators produce the RTD window result, SN74LVC1G08/
SN74LVC1G38 produce default-high `RTD_HW_FAULT`, and a second SN74HC4075 feeds
the dominant safety latch.

## Why both paths are necessary

| Question | Firmware path | Hardware path |
| --- | --- | --- |
| Which RTD/SPI diagnostic occurred? | Yes | No; it sees only electrical validity. |
| Can it log and show the condition? | Yes | No. |
| Can it act after CPU/SPI scheduling failure? | Not reliably | Yes, within analogue/logic propagation bounds. |
| Can software bypass a latched sensor fault? | Must not | No, by construction. |
| Can it prove the sensor is in-range? | It can estimate/diagnose | It asserts only a configured electrical window. |

This split avoids two symmetric errors: trusting firmware as a safety relay, or
trying to make a small hardware comparator network provide all product-level
diagnostics.

## Verification ladder

Use different instruments for different claims:

1. **Contract review:** document polarities, failure response, reset/latch
   semantics, supplies, and isolation boundary in the gate-driver contract.
2. **In-box simulation:** exercise comparator thresholds, logic polarity,
   propagation timing, and supply/fault combinations in portable ngspice.
3. **Property tests:** generate fault-net/component omissions and require the
   real-board preflight to reject them.
4. **EDA parity/DRC:** ensure the imported board actually contains the safety
   route, required component families, clearances, and isolation constraints.
5. **Bench validation:** inject open/short/out-of-window RTD conditions and
   observe physical latch/inhibit timing under real supply and switching noise.

Passing a lower rung does not turn a higher rung into a pass. In particular,
simulation cannot establish actual GPIO levels, EMI immunity, or PCB isolation.

## When to apply

Apply this pattern when a sensor fault can cause an unsafe thermal, current, or
motion condition and the product has a practical hardware shutdown path.

Do not apply it by adding an unreviewed comparator that bypasses the system
safety latch. That creates a second, inconsistent shutdown authority. Feed the
existing dominant latch and document its reset behavior instead.

## Related

- `docs/hardware/UCC21550_INTERFACE_CONTRACT.md`
- `docs/hardware/RTD_SAFETY_DUAL_PATH.md`
- `docs/session-reports/2026-07-13-real-induction-in-box-safety-and-board-closure-arc.md`
