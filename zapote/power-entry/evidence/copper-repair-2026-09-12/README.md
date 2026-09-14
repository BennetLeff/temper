# Partial PFC copper repair

The agent widened one saved F.Cu `minus` segment from 4 to 6 mm without
changing its endpoints, UUID, net, layer, pads or any schematic input. Its
original failing graph edge `e45ca754-66c7-4204-987e-e69d5ed1af44:3` still
carries a determined nominal 15 A RMS. Its IPC-2221 scalar capacity increased
from 14.6513 to 19.6581 A. The [fresh parent screen](parent-screen.json) retains
the other four failures. No validation rule, current assumption or threshold
was changed, and no failed edge was accepted merely because its current became
indeterminate.

All 814 graph-edge current determinations are unchanged. The wider trace does
add one explicit pad-contact coverage gap: U12.2 offers a measured 4.2 mm
copper chord, which cannot certify a full 6 mm attachment. The PFC coverage-gap
count therefore rises from 56 to 57. The trace-width finding is resolved;
the complete trace-to-pad path has not acquired an ampacity certificate.

The canonical board is [section.kicad_pcb](../../candidate/section.kicad_pcb).
Its SHA-256 is
`84f4b325b25e4be71fcf990d9420ddb4346687ca1c28be63fb44a0d661fa2317`;
the prior board was
`8c36944562814d0871232758a9bd11bd2a2903993d9e4dae65f0857af54494cf`.
The common runner now selects [native-copper-12.json](../native-copper-12.json).
Historical native11 and oracle fixtures remain unchanged.

## Why the other four findings remain open

These are the 2.5 mm centered necks at bridge U1, on `minus`, `ac1`, `ac2`
and `plus`. Each has a determined nominal 15 A contribution and a 10.4205 A
uniform-trace capacity estimate. The reviewed GBU footprint has 5.08 mm pin
pitch and 3.0 mm-wide neighboring copper lands. At the current pin-centered
endpoints, the 2 mm clearance requirement bounds a round-ended track's width
to approximately `2 × (5.08 − 1.5 − 2) = 3.16 mm`. The uniform IPC screen
instead needs approximately 4.132 mm at 70 µm copper and a 20 °C rise.
Simply increasing these four segment widths therefore cannot satisfy both
existing constraints.

The [independent validation](../../../validation/p1-current/oracle-2026-09-12/README.md)
establishes the nominal current model and implementation of the stated
capacity equation. It does not validate physical temperature for short
terminal necks. The formula has no conductor-length, terminal-temperature or
heat-spreading inputs. A failed screen is not a measured overheating result.
KiCad's [calculator documentation](https://docs.kicad.org/5.1/en/pcb_calculator/pcb_calculator.pdf)
identifies this as an IPC-2221 trace-sizing calculation; IPC describes
[current-capacity guidance](https://www.ipc.org/TOC/IPC-2152.pdf) in terms of
conductor dimensions and allowable temperature rise.

The next engineering step is a source-bound thermal assessment of the finite
necks, pads and attached conductors, including terminal heating, copper
tolerance and operating conditions. If that cannot support the required
current and temperature limits, revise the physical bridge connection or
package. Neither a generic waiver nor reclassifying the findings as passes
closes this gap. Alternative routing approaches were not exhaustively ruled
out by this bounded width-only attempt.

## Evidence and limitations

- The [authoritative receipt](verification.json) records 320 Rust tests passed,
  zero failed or ignored. All seven maintained boards passed fresh native
  ERC/DRC and common binding checks. Overall `make check` remains nonzero
  because the power-entry unit retains four screening failures; the other six
  units remain indeterminate. Full run outputs are in [all-units.tar.gz](all-units.tar.gz)
  with [member hashes](all-units-index.json) and the [command log](check.log).
  This run records the uncommitted repair as dirty; it is not a clean-commit receipt.
- Luna authored the repair in an isolated checkout at `cb80a1df1`; the parent
  integrated and independently evaluated it. See the
  [operation manifest](operation-manifest.json) and
  [worker report](repair-report.md).
- Parent KiCad 10.0.4 [DRC](parent-drc.json) reports zero violations,
  zero unconnected items and zero parity issues, using `--all-track-errors`,
  `--schematic-parity` and `--severity-all`.
- Native geometry was freshly collected with the maintained
  `extract_current_sense_native.py` adapter and the
  [manufacturing extractor](parent-manufacturing.json). An initial use of the
  older RTD adapter omitted mechanical-pad classification and was rejected by
  Rust with `unexpected native pad`; that output was not accepted.
- Three worker DRC attempts aborted with code 134 and no report. These are
  failed tool executions, not observed clearance findings. The geometric bound
  above is a separate calculation. Intermediate board snapshots/hashes were
  not fully retained; the worker manifest discloses the missing evidence.
- No new regression was added for a one-value PCB edit. Existing width
  mutation/restoration tests remain unchanged; fresh saved-board evaluation
  verifies the actual repair. No simulation reference pin was changed.
- Thermal qualification, pad/barrel current capacity, area current sharing,
  real controller/device behavior and physical tests remain incomplete.
  This is not a fabrication or powered-operation release.
