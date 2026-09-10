# Buck Rev A — standalone 15 V → 3.3 V prototype board

A small, buildable bench board derived from the reviewed `BuckConverter3V3`
core (LMR51430). This directory holds the standalone schematic and PCB, the
local libraries they resolve against, the freeze manifest and the verification
records.

**This is a prototype, not a qualified or production design.** No hardware has
been assembled or measured. See the deferred-qualification list at the end.

## Status

| Item | State |
|---|---|
| Board | **Frozen**, revision A, 2026-09-10 |
| Source-manifest digest | `7cf32ae8c6be81a46b73bc72a8edf469f70031affaefecdf3b0050be5369a0ea` |
| Native ERC / DRC | 0 violations / 0 violations, 0 unconnected (KiCad 10.0.6) |
| Schematic ↔ board connectivity | exact match |
| Manufacturing export | release owner; waits on this freeze |
| Bench measurements | **NOT RUN** |

Freeze details: `verification/board-freeze.md`. Upstream identity:
`source-manifest.json`.

## Interface decisions (for release and bring-up owners)

- **J1 (input)** and **J2 (output)** are both Würth Elektronik
  **691253500002** (DigiKey `732-691253500002-ND`): WR-TBL Series 2535,
  2-position, 5.08 mm, **vertical / top wire entry**, rising-cage screw,
  16 A / 300 V UL, 30–12 AWG.
- Pinout: **J1.1 = VIN (`+15V`)**, **J1.2 = GND (`gnd`)**,
  **J2.1 = 3V3 (`+3V3`)**, **J2.2 = GND (`gnd`)**.
- Probe pads: **TP1 = VIN**, **TP2 = GND**, **TP3 = VOUT**, **TP4 = GND**.
  No TP5; SW stays on the U3.2 / L2.1 pads.
- Silk reads `VIN 13.5–16.5V -> 3V3 0.5A`, `ISOLATED DC - NO MAINS`, plus
  per-terminal polarity and reference designators.

## Files

| Path | Owner | Purpose |
|---|---|---|
| `buck-reva.kicad_sch`, `.kicad_pcb`, `.kicad_pro`, `.kicad_dru` | board | Standalone CAD and project rules |
| `buck-reva.kicad_sym`, `sym-lib-table` | board | Local symbols |
| `buck-reva.pretty/`, `fp-lib-table` | board | Local footprints |
| `source-manifest.json` | board | Freeze manifest (input hashes + provenance + interface) |
| `verification/` | board | ERC/DRC reports, netlist, renders, freeze and review docs |
| `procurement/`, `release/`, `export-release.sh` | release | Purchasing and manufacturing package |
| `docs/hardware/buck-reva/` (repo) | bring-up | Operator runbook and templates |

## Regenerating the derived outputs

All artifacts were produced with **KiCad CLI 10.0.6** at
`/Volumes/KiCad/KiCad/KiCad.app/Contents/MacOS/kicad-cli`:

```sh
K=/Volumes/KiCad/KiCad/KiCad.app/Contents/MacOS/kicad-cli
$K sch erc --format json --severity-all buck-reva.kicad_sch -o verification/buck-reva-erc.json
$K sch export netlist buck-reva.kicad_sch -o verification/buck-reva.net
$K pcb drc --all-track-errors --format json -o verification/buck-reva-drc.json buck-reva.kicad_pcb
```

The board was derived once from the reviewed witness fixture; see
`verification/connectivity.md` for the source-to-board reconciliation. Core
footprint UUIDs, positions and pad nets are carried over unchanged.

## Design rules

- 0.2 mm minimum track, 0.2 mm minimum clearance, 0.2 mm copper-to-edge
  (`buck-reva.kicad_dru` + project net class).
- Two layers, 50 × 40 mm, 1.6 mm FR-4, 1 oz copper, lead-free HASL,
  mask and silk both sides, top-side assembly.

## Deferred (not blockers for this prototype)

Combined capacitor derating, hot-inductor/fault characterization, validated
junction-temperature estimation, behavioral-model correlation and
environmental qualification. Physical assembly and powered bring-up are a
later milestone.
