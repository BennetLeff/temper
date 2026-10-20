# Verification receipt — 2026-10-20

The final native KiCad10.0.4 rebuild completed with:

- ERC:0 errors,0 warnings,0 other findings (`erc.json`, severity-all, exit-code-violations).
- DRC:0 violations,0 unconnected items,0 schematic parity issues (`drc.json`, severity-all, all-track-errors, refill-zones, schematic-parity).
- Source JSON ↔ native schematic XML ↔ PCB pad nets: all51 components and all mapped pins agree, including intentional NC nets.
- Native position export ↔ source placement: every centre/angle/side agrees.45 SMT CPL placements match26 SMT BOM lines; six hand-fitted headers remain only in the complete BOM.
- Physical package/pin order reviewed against manufacturer references; corrected HRO USB and YXC oscillator land patterns are project-local. Part-specific LCSC library orientation corrections are applied. Final vendor assembly preview remains outstanding.
- Two successive native CAD builds and zone fills produced byte-identical PCB files after seeding KiCad's UUID generator. UUID serialization initially varied despite identical geometry; this was corrected in the adapter before final exports.
- Final PCB SHA256: `e900c8bc9d4e0a8a8c1c94e035e8c639383577aab73bb2175d8e059a88dee42b`.
- Final schematic SHA256: `e4a896e518a6eeff9ad37278746617d9019298611079dce30cc9a1fdd642de20`.
- Native schematic, top copper/silk and clean assembly drawing visually inspected. Actual Gerber top/bottom copper, ground, power and mask rendered with PyGerber2.4.3 API V2 and inspected. The legacy raster-2d renderer omitted roundrect macro pads; it is not used for final evidence. In1 is a continuous ground plane; In2 contains separated digital/analog supply pours. No obvious unintended open/copper crossing was found in the final renders.
- Parent independently reran severity-all DRC with all-track-errors, schematic parity and zone refill on the exact final PCB hash: zero violations, zero unconnected items and zero parity findings (`independent-drc-final.json`). The unchanged schematic also passed independent ERC. Independent BOM/CPL membership, all45 centres/angles, all26 part codes, Gerber ZIP bytes and main archive hashes passed. Earlier check receipts are retained as history.
- Host software:11 unit tests +1 integration test pass, default/offline builds and clippy checks pass. Release macOS arm64 binary included. No physical USB meter was available.
- Analog review:96 limited generic two-pole op-amp cases completed. See`analog-review.md` for assumptions, peaking and limitations. This is not an AD8606 manufacturer model, measured phase margin or an accuracy certificate.

## What remains unverified

Actual assembled-board behavior, USB enumeration/suspend and OS driver interaction, analog oscillation/distortion/noise, low-frequency DFT performance, calibration accuracy, fixture repeatability, ESR floor, component substitutions, vendor machine placement preview and assembler DFM. The prototype package does not imply those checks have passed. Follow`docs/bring-up.md` before relying on measurements.
