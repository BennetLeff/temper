# Real Induction Board Closure Arc — Requirements

**Date:** 2026-07-13
**Status:** Requirements — ready for planning
**Backfilled:** 2026-07-22 — the three `2026-07-13-*` plan files (`-001` pipeline overtest, `-008` fresh-build inventory gate, `-013` UCC21550 latch/sensors/supply closure) were committed to `docs/plans/` without a corresponding brainstorm requirements doc and without `origin:` metadata in their frontmatter. This root-arc requirements doc is reconstructed here from those three plans and the broader session record (atopile build green; regression suite green; firmware CTest 12/12 pass) so the three plans can backlink `origin:` to a single root brainstorm — consistent with the project's epic-into-5–15-subtasks decomposition convention in `AGENTS.md`.

## Problem

The temper project needs to move from "components and source are in place on paper" to "all gates measured against an actual generated board, with isolated safety signals, a closed UCC21550 gate-drive interface, and a routed board that passes KiCad's real DRC truth gate." The work had been accumulating in three loosely-coupled streams — Atopile build + netlist inventory, UCC21550 latch/sensor/supply closure, and the atopile → KiCad pipeline overtest — but no single requirements doc tied them together as one release arc. Each stream had status evidence but no origin document that subsequent planning could trace back to.

This doc provides that origin: it is the brainstorm for the induction-cooker **real-hardware closure arc**, from which `2026-07-13-001` (the overarching pipeline overtest), `2026-07-13-008` (the fresh-build inventory gate), and `2026-07-13-013` (the UCC21550 latch/sensor/supply closure) are sliced plan units.

## Verified current state (at the time)

### Build and inventory

- `ato build src/main.ato:Top` is green; emits `elec/build/default.net`.
- The inventory parser sees **73 components and 118 nets**.
- `uv.lock` had a duplicate `ortools` package record; it is repaired and parses as TOML with a single sourced entry.
- The import-linter script passes directly; `uv run` cannot be exercised in this sandbox because its package cache is incomplete and network access is disabled.

### UCC21550 latch / sensor / supply closure

- VCCI is supplied from 3.3 V; the 15 V rail retained for gate-side power.
- DIS is active-high on the `SHUTDOWN` net.
- OCP/OVP/thermal faults are latched by a cross-coupled NAND SR latch; reset is fault-qualified so a live fault cannot be cleared by firmware.
- Watchdog RESET_N and firmware runaway-cut feed the fault bus.
- Dead-time uses a 34 kΩ resistor (305.4 ns nominal); the in-box DT corner model reports 270.5–343.2 ns under 100-ppm/°C resistor, −40…150 °C, and datasheet ±10% device envelope — i.e., **not a guaranteed 300 ns hardware minimum**. A 39 kΩ candidate clears 300 ns in the model but still requires scope correlation. The in-box SPICE stub ignores DT, so the analytical model is the only in-box DT evidence until a vendor edge-accurate model is added.

### Sensor safety

- MAX31865 digital diagnostics and an independent comparator-to-latch path both specified; the comparator is **intentionally not wired** until its bias-current and tolerance corners are closed.
- The selected interface is a default-high `RTD_HW_FAULT`: post-ferrite `RTD_AVDD` powers the MAX31865/window logic; an upstream rail monitor rejects brownout before the window comparators become undefined; an Ioff-rated open-drain NAND sinks the fault line only when both window and rail permissions are valid. A second aggregate OR preserves set dominance because the original `SN74HC4075` is fully allocated.
- Selected REF2025/TLV3201/TPS3700 resistor network has property coverage and nominal selected-value ngspice coverage; tolerance/PVT remains covered by property tests rather than an unreviewed PSpice conversion. Low-voltage bench capture remains a release gate.

### Firmware

- Firmware/schematic GPIO map is collision-free: PWM_H/PWM_L = GPIO4/5, watchdog kick/reset = GPIO7/6, reset request = GPIO14, runaway-cut = GPIO15, ZCD = GPIO13.
- Firmware routes software-detected fan, RTD, and ADC faults through the active-high runaway-cut helper before entering `STATE_FAULT`.
- Firmware uses the inclusive 10 Ω/300 Ω PT100 guard thresholds from generated configuration; the legacy >10 kΩ gross-open diagnostic is preserved as a secondary SIL trace.
- Firmware build: pass, including standalone low-temperature and explicit end-to-end integration targets. Full firmware CTest: **12/12 pass** (thermal-mass, PLL, integration, state-machine, safety, SIL).

### Tests

- Contract, inventory, device-power, and property-based regression tests: **37 passed**.
- Hypothesis coverage for generated latch fault/reset sequences and generated inventory identities, duplicate references, counts, and hashes.
- Firmware thermal-mass regression includes a monotonic classification property sweep: increasing measured rise cannot make a pan classify heavier.

### Open PCB release gates

- Import the generated netlist into the actual KiCad board and run electrical rules + HV/LV + creepage/clearance checks. Source-level map cannot prove routed isolation, return-current control, or copper geometry.
- The macOS 26 / KiCad 10.0.4 local `kicad-cli pcb drc` aborts (`SwiftNativeNSArray.swift:78: Fatal error: Array index out of range`). This is now **fail-closed**: the Linux regression runner installs KiCad and runs the real DRC as a blocking truth gate; a CLI crash is an unmeasured failure, never a clean report. The local crash no longer masks routing closure, but it also does not establish it.
- The source-level Rust diagnostic additionally finds component-overlap and clearance findings in the present candidate set (including power-stage parts in `temper_final_verified.kicad_pcb`). It is a **diagnostic, not a substitute** for KiCad's truth gate; do not waive or raise a DRC ceiling to make this workstream look closed.
- Review the complete MCU pin map against the routed board (PWM GPIO4/5; SPI GPIO8/10/11/12; MAX31865 DRDY GPIO9; ZCD GPIO13; safety GPIO6/7/14/15/20; relay GPIO19; optional I²C GPIO38/39; reserved RTD2 CS GPIO16). No pin serves two electrical functions.
- Choose 34 kΩ versus the 39 kΩ candidate against the actual dead-time requirement, then scope-correlate OUTA/OUTB and both gate VGS waveforms at resistor / temperature / bus-voltage / representative-load corners.
- Close the PT100 hardware comparator design with measured MAX31865 bias current, threshold/offset/TCR corners, connector protection, supply-loss behavior, and injected short/open bench tests. Retain the firmware path.

## Dependency spine (the release arc's critical path)

1. Fresh build and inventory.
2. Netlist ingest, provenance, net-class and identity checks.
3. UCC21550 interface/latch/sensor/supply closure.
4. Measured physics anchors and FMEA envelope.
5. Firmware fault-path evidence.
6. DRC/routing closure and integration gate.

## Requirements

### R1 — Fresh-build inventory gate

`ato build src/main.ato:Top` produces a deterministic KiCad netlist with component and net identities, source provenance, artifact SHA-256, command, and tool version. Reject missing, empty, stale, duplicate reference/timestamp, duplicate net-code, or count-mismatched artifacts. The inventory is the only artifact accepted by downstream ingest; it does not silently substitute the historical board.

- Sliced to plan: `2026-07-13-008` (fresh-build inventory gate).

### R2 — Real-induction board pipeline overtest

No placement or physics result is accepted until the source hash, artifact hash, identity, net classes, UCC21550 interface contract, physics anchors, FMEA envelope, firmware fault behavior, and DRC/routing closure are all checked — exercised against a real `ato build → netlist → board → DRC` traversal, not a source-level read.

- Sliced to plan: `2026-07-13-001` (real induction board pipeline overtest).

### R3 — UCC21550 latch / sensor / supply closure

- VCCI sourced from 3.3 V; DIS active-high; OCP/OVP/thermal faults latched by a cross-coupled NAND SR latch; reset fault-qualified so a live fault cannot be cleared by firmware; watchdog RESET_N and firmware runaway-cut feed the fault bus.
- Dead-time configured (34 kΩ nominal / 39 kΩ candidate) with scope correlation mandatory before PCB release.
- Sensor safety defaults high (`RTD_HW_FAULT`); window + rail-monitor permission gating; aggregate OR preserves set dominance.
- MCU GPIO map collision-free and asserted by a contract test.

- Sliced to plan: `2026-07-13-013` (UCC21550 latch, sensor, and supply closure).

### R4 — KiCad DRC truth gate is the only release verdict

DRC/routing closure is established by `kicad-cli pcb drc` on a real Linux runner (the macOS local crash is fail-closed-UNMEASURED, never clean). Source-level Rust diagnostics are diagnostics, not substitutes. Do not waive or raise a DRC ceiling to make the workstream look closed.

### R5 — Firmware fault-path evidence

Firmware routes software-detected fan, RTD, ADC faults through the active-high runaway-cut helper before `STATE_FAULT`; the full firmware CTest suite passes (thermal-mass, PLL, integration, state-machine, safety, SIL). Physical GPIO assertion and the sensor threshold/front-end choice remain hardware-review evidence gates.

## Scope boundaries

- The schematic-level audit remediation work (the `2026-07-15-003 → -009` cluster) is a **separate arc** — its origin is `docs/audits/2026-07-15-atopile-electrical-design-audit.md`, not this brainstorm. Cross-referenced here only because its `003` (grounding/isolation) is on the release critical path once UCC21550 closure is in.
- "Finish the board" routing-completion scope lives in `2026-07-10-001` (and its backfilled origin `2026-07-10-finish-the-board-requirements.md`); this arc treats the resulting routed board as input, not as work to be done here.

## Non-negotiable guards (the project's hard-won discipline)

1. **Measure the territory, not the map**: DRC is run against an actual generated board on a Linux runner, not inferred from the source-level map.
2. **Fail-closed measurement**: a `kicad-cli` crash is UNMEASURED, never a clean report.
3. **A diagnostic is not a substitute for a truth gate**: source-level Rust diagnostics matter, but they never close a release gate alone — and never relax a DRC ceiling to make the source-level view look better than it is.
4. **No pin serves two electrical functions**: the MCU GPIO map collision-free assertion is enforced by a contract test, not by inspection.

## Success metrics

- A clean `ato build` produces a deterministic inventory with freshness checking enabled (R1).
- The full dependency spine (build → ingest → identity → UCC21550 closure → physics → firmware → DRC) runs end-to-end with every gate checked, no silent substitutions (R2).
- Dead-time resistor chosen against the measured 300 ns hardware minimum across resistor/temperature/device corners, with scope correlation captured (R3).
- A real `kicad-cli pcb drc` result on a Linux runner is the only release verdict that closes DRC/routing; macOS local crashes are fail-closed UNMEASURED (R4).
- Full firmware CTest (12/12) passes with fault-path evidence captured (R5).

## Sources & References

- Plans:
  - [`docs/plans/2026-07-13-001-feat-real-induction-board-pipeline-overtest-plan.md`](../plans/2026-07-13-001-feat-real-induction-board-pipeline-overtest-plan.md)
  - [`docs/plans/2026-07-13-008-feat-real-induction-fresh-build-inventory-plan.md`](../plans/2026-07-13-008-feat-real-induction-fresh-build-inventory-plan.md)
  - [`docs/plans/2026-07-13-013-feat-ucc21550-latch-sensors-supply-plan.md`](../plans/2026-07-13-013-feat-ucc21550-latch-sensors-supply-plan.md)
- Related arc: `docs/audits/2026-07-15-atopile-electrical-design-audit.md` (origin of the `2026-07-15-003 → -009` schematic-audit-fix cluster, downstream of this arc's UCC21550 closure)
- Hardware design doc: `docs/hardware/RTD_SAFETY_DUAL_PATH.md`