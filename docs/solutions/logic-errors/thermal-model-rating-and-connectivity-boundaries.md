---
title: Thermal models need complete connectivity and scoped sensor ratings
date: 2026-09-11
category: logic-errors
component: zapote-thermal-sense
symptoms:
  - Pin coverage was mistaken for proof of connected copper
  - A sensor temperature rating was copied onto its connector
  - Nominal trip agreement obscured missing release corner calculations
root_cause: Draft validation checked partial evidence and inherited stale part facts
resolution: Exact per-net clusters, current manufacturer evidence, and independent trip/release controls
---

# What happened

The first thermal Rust draft formed a union of native connectivity nodes. Every endpoint could appear while a net remained split into disconnected clusters. It also reduced the strict pin map to a set, losing duplicate/malformed rows, and reported only heating corner bounds. A current manufacturer review corrected a stale 125 °C caveat: the exact NTC assembly is rated to 150 °C without connector, whereas the XH connector has an 85 °C limit.

# What enforces the correction

`zapote-erc/src/thermal_sense.rs` now checks one native cluster per authored net, exact node sets, and strict pin/reference/uniqueness coverage. Tests split a net while preserving the complete union of endpoints, inject duplicate/malformed evidence and change values coherently with source attributes. This tests the failure mode rather than relying on a missing-pin example alone.

Both output states of the loaded feedback divider are calculated. All 64 endpoint combinations of four resistor tolerances, R25 and beta are enumerated for trip and release. An independent KCL/beta audit supplies rounded numerical references. Agreement still does not qualify beta extrapolation, comparator nonidealities or thermal coupling.

The native footprint reload adapter is exercised at 37° against KiCad itself. The control deliberately loses pad body orientation while keeping native pad centres; reload restores the native library state. A displaced pad must cause rejection without writing the board.

# What transfers

Transfer the procedure: verify each connected group, reject lossy evidence normalization, evaluate both hysteresis states, and scope ratings to the actual assembly that earned them. Read current exact-part evidence before carrying an earlier limitation forward. Do not transfer thermal threshold values, component identities, or a sensor rating to another unit or its connector.

# What remains unproven

An open NTC or short to VCC reads cold in this topology. The analog monitor approaches VCC, so receiver acquisition/range is a separate obligation. The standalone unit contains no open-sensor diagnostic or latch. The next safety-interlock design must address this gap explicitly. Hardware, harness assembly and shutdown timing are NOT RUN.

Evidence: `zapote/thermal-sense/MODEL.md`, `INTERFACES.md`, Rust thermal tests, native transport test, and `evidence/final-manifest.json`. No controlled memory-effectiveness comparison was performed.
