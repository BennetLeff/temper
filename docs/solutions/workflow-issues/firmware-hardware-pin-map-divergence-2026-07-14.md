---
title: "When firmware and schematic disagree on GPIO pin assignments, verify against the real module datasheet before picking a side"
date: "2026-07-14"
category: workflow-issues
module: mcu-pin-assignment
problem_type: workflow_issue
component: development_workflow
severity: critical
applies_when:
  - "A schematic and its firmware were authored/generated in separate passes (different sessions, tools, or people)"
  - "Reconciling a KiCad schematic's GPIO wiring against firmware pin-definition headers"
  - "Deciding which of two conflicting sources of truth (drawn hardware vs written code) to treat as authoritative"
symptoms:
  - "Nearly every GPIO function (SPI, I2C, chip-select, interrupt) is assigned to a different physical pin in firmware vs. the schematic"
  - "A firmware header comment contradicts a different comment elsewhere in the same file about the same pin"
  - "A header comment says pin numbers are 'provisional until PCB layout is finalized' but the .c files already implement timing-sensitive logic against those exact numbers"
tags:
  - pin-mapping
  - firmware-hardware-sync
  - esp32
  - source-of-truth
  - datasheet-verification
---

# When firmware and schematic disagree on GPIO pin assignments, verify against the real module datasheet before picking a side

## Context

Rewiring `pcb/mcu.kicad_sch`'s ESP32-S3 connections surfaced that the schematic's own
documentation comment ("IO9: SPI_MISO") and `firmware/components/hal/include/temper_pins.h`
("`PIN_SPI_MISO 12`") assigned nearly every SPI/I2C/status signal to a *different* physical GPIO.
Of roughly 18 pin functions, only 3 agreed between the two sources. Naively trusting either source
without a tie-breaking method risks wiring a board that firmware can never actually drive
correctly, or rewriting tested firmware to match a schematic that was itself wrong.

## Guidance

Don't average, don't guess, and don't default to "the schematic is the hardware, so it wins."
Establish a hierarchy of evidence and check it explicitly:

1. **Working code beats documentation comments.** If one side is a header comment and the other
   is `.c` code that implements timing-sensitive logic (SPI bus setup, interrupt handlers) against
   specific pin numbers, and property/unit tests already assert behavior derived from those
   numbers, that code is real evidence of intent. A comment ("provisional until PCB layout is
   finalized") is not — especially when it contradicts the code in the same file.
2. **Check internal self-consistency of each source.** A firmware header with a comment on one
   line ("IO13 is ZCD") that contradicts its own `#define` two pins later is a red flag for that
   source's reliability, independent of which side "wins" overall.
3. **Verify the winning side's specific pin choices are hardware-valid before committing.** Don't
   just trust the more-consistent source blindly — cross-check its actual GPIO numbers against the
   real module's pinout for reserved/strapping/special-function pins:
   - Find the project's own bundled reference symbol for the exact module variant in use (e.g.
     `components/ESP32-S3/ESP32-S3-WROOM-1.kicad_sym`) — this is frequently more trustworthy than
     general chip-family knowledge, because it reflects the *exact part number* (flash/PSRAM
     variant affects which GPIOs are physically broken out at all).
   - Check the winning source doesn't collide with strapping pins, unless explicitly and
     deliberately handled (a comment like "GPIO0 - boot button, use with care" is a good sign the
     author was pin-aware, not a red flag).
   - Check for coherent tradeoffs: e.g. a design that repurposes native-USB pins (GPIO19/20 on
     ESP32-S3) for other functions is only sound if it also defines a UART-based debug console
     elsewhere — internal coherence across the whole pin map is itself evidence of a deliberate,
     validated choice rather than an oversight.

## Why This Matters

Getting this decision backwards is expensive in a specific way: if you rewire the schematic to
match a stale/wrong firmware pin map, you propagate the error into physical hardware. If you
instead rewrite tested firmware to match an unverified schematic, you silently invalidate any
timing analysis, property tests, or safety-critical documentation (interrupt latency budgets, SPI
setup/hold margins) that was built against the original firmware pin numbers — and that
invalidation is easy to miss because the code still compiles and superficially "works" against a
simulator or the previous (correct) board rev.

## When to Apply

- Whenever a schematic and firmware pin-definition file for the same MCU disagree on more than a
  couple of signals — that volume of disagreement means at least one side drifted independently
  and needs a deliberate reconciliation pass, not a one-off patch.
- Before treating "the schematic is newer" or "the firmware is newer" as sufficient justification
  on its own — recency doesn't imply correctness when both sides can drift.
- Any time a "provisional" or "TBD" comment sits next to code that has clearly moved past
  provisional (has tests, has referenced safety/timing docs, is called from production paths).

## Examples

Comparison table used to make the call in this case (partial):

| Function | Firmware GPIO | Schematic GPIO | Agreement? |
|---|---|---|---|
| SPI Clock | 8 | 11 | No |
| SPI MOSI | 11 | 10 | No |
| I2C SDA | 38 | 8 | No |
| Watchdog kick | 7 | 7 | Yes |
| Relay bypass | 19 | 19 | Yes |

Firmware won because: `rtd_service.c` already implements SPI2 setup against GPIO8/9/10/11/12 with
tests referenced by a safety-timing design doc; the header explicitly avoids the module's
flash/PSRAM-reserved GPIO range (26-37); and it deliberately repurposes native-USB pins only
because it separately defines a UART console — a coherent, validated pin budget, not a stale draft.

## Related
- `docs/solutions/tooling-decisions/kicad-embedded-symbols-lose-pin-semantics-2026-07-14.md` — the
  companion technique for finding a project's exact-variant reference symbol/library instead of
  relying on general part-family knowledge.
