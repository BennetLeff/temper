---
title: Real induction board pipeline overtest
type: feat
status: active
date: 2026-07-13
origin: docs/brainstorms/2026-07-13-real-induction-board-closure-arc-requirements.md
---

# Real induction board pipeline overtest

The work starts with a fresh Atopile build and a provenance-carrying KiCad
netlist inventory. No placement or physics result is accepted until the
source hash, artifact hash, identity, net classes, UCC21550 interface contract,
physics anchors, FMEA envelope, firmware fault behavior, and DRC/routing
closure are all checked.

## Dependency spine

1. Fresh build and inventory.
2. Netlist ingest, provenance, net-class and identity checks.
3. UCC21550 interface/latch/sensor/supply closure.
4. Measured physics anchors and FMEA envelope.
5. Firmware fault-path evidence.
6. DRC/routing closure and integration gate.

Current state: `ato build src/main.ato:Top` is green and emits `elec/build/default.net`.
The inventory parser sees 73 components and 118 nets. The UCC21550 path now has
3.3 V VCCI, active-high DIS, a fault-qualified set-dominant latch, watchdog and
runaway-cut inputs, and a 34 kΩ DT resistor as a nominal starting point from
TI's dead-time relationship. The in-box DT corner model reports 270.5–343.2 ns
under explicit resistor/temperature/device assumptions, so it does not prove a
300 ns hardware-only minimum; a 39 kΩ candidate and scope correlation remain
under review. The existing SPICE stub ignores DT, so the analytical model is
the only in-box DT evidence until a vendor edge-accurate model is added; scope
correlation remains mandatory. Sensor safety is specified as both MAX31865
digital diagnostics and an independent comparator-to-latch path, but the
comparator is intentionally not wired until its bias-current and tolerance
corners are closed.

The firmware/schematic GPIO map is now collision-free: PWM_H/PWM_L use GPIO4/5,
watchdog kick/reset use GPIO7/6, reset request uses GPIO14, runaway-cut uses
GPIO15, and ZCD uses GPIO13.

Verification status:

- Atopile build: pass.
- Contract, inventory, device-power, and property-based regression tests: 37
  passed.
- Property-based tests cover generated latch fault/reset sequences and
  generated inventory identities, duplicate references, counts, and hashes.
- Firmware thermal-mass regression now includes a monotonic classification
  property sweep: increasing measured rise cannot make a pan classify heavier.
- Firmware build: pass, including the standalone low-temperature and explicit
  end-to-end integration targets.
- Full firmware CTest: 12/12 pass, including thermal-mass, PLL, integration,
  state-machine, safety, and SIL suites.

## Remaining PCB release gates

- Import the generated netlist into the actual KiCad board and run electrical
  rules plus high-voltage/low-voltage and creepage/clearance checks. The
  source-level map cannot prove routed isolation, return-current control, or
  copper geometry.
- The macOS 26 / KiCad 10.0.4 local `kicad-cli pcb drc` invocation aborts
  before a measurement with `Swift/SwiftNativeNSArray.swift:78: Fatal error:
  Array index out of range`. This is now fail-closed: the Linux regression
  runner installs KiCad and runs the real KiCad DRC as a blocking truth gate;
  a CLI crash is explicitly an unmeasured failure, never a clean report.
  The local crash therefore no longer masks routing closure, but it also does
  not establish it. The first Linux truth-gate result must be retained with
  the selected authoritative, routed board and its schematic-parity report.
- The source-level Rust diagnostic additionally finds component-overlap and
  clearance findings in the present candidate set (including power-stage
  parts in `temper_final_verified.kicad_pcb`). It is a diagnostic, not a
  substitute for KiCad's truth gate; do not waive or raise a DRC ceiling to
  make this workstream look closed.
- Review the complete MCU map against the routed board: PWM GPIO4/5, SPI
  GPIO8/10/11/12, MAX31865 DRDY GPIO9, ZCD GPIO13, safety GPIO6/7/14/15/20,
  relay GPIO19, optional I²C GPIO38/39, and reserved RTD2 CS GPIO16. No pin is
  allowed to serve two electrical functions.
- Choose 34 kΩ versus the 39 kΩ candidate against the actual dead-time
  requirement, then capture OUTA/OUTB and both gate VGS waveforms at resistor,
  temperature, bus-voltage, and representative-load corners.
- Close the PT100 hardware comparator design with measured MAX31865 bias
  current, threshold/offset/TCR corners, connector protection, supply-loss
  behavior, and injected short/open bench tests. Retain the firmware path.

The malformed `uv.lock` condition was also repaired: the duplicate `ortools`
package record was removed and the lock now parses as TOML with one sourced
entry. The import-linter script passes directly; `uv run` cannot be exercised
in this sandbox because its package cache is incomplete and network access is
disabled.
