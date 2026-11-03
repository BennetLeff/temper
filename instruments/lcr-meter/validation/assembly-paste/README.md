# Solder paste and tombstoning (2026-11-03)

Run it with `<kicad-python> validation/assembly-paste/paste_check.py`. It reads `cad/temper-lcr.kicad_pcb`, writes `paste-check.json`, and exits 1 on any finding.

**Result: 0 findings.** 667 paste apertures, 5 exposed pads, 187 two-pad parts.

## Stencil area ratio (IPC-7525: ≥ 0.66)

Paste is 100 % of each pad everywhere: the board, footprint and pad paste margins are all 0. The only exceptions are footprints that define their own windows.

| Part | Aperture | 0.10 mm foil | 0.12 mm | 0.15 mm |
|---|---|---|---|---|
| U1 RP2040, 0.4 mm pitch | 0.875 × 0.2 | 0.81 | **0.68** | 0.54 |
| U13 TPS65131, 0.5 mm pitch | 0.775 × 0.25 | 0.95 | 0.79 | 0.63 |
| U14 corner pads A1–A4 | 0.25 × 0.25 | 0.63 | 0.52 | 0.42 |
| Everything else | | | ≥ 0.99 | ≥ 0.79 |

- **Stencil thickness.** JLC's stencil guide gives 0.10–0.12 mm for 0.4 mm-pitch QFNs (0.10 mm usual) and 0.12–0.15 mm for 0.5 mm pitch: <https://jlcpcb.com/blog/how-to-choose-a-solder-paste-stencil>, read 2026-11-03. At either 0.4 mm-pitch thickness, U1 passes. A 0.15 mm foil would put U1 at 0.54 and U13 at 0.63. The handoff's order remark therefore asks for a stencil ≤ 0.12 mm.
- **U14 corner pads.** These are kept as a NOTE, not a finding. TI's own RGE0024R "Example stencil design" (SLASF24A, 4225246/A) uses the same 0.25 mm square apertures. The pads are VSS anchors, and VSS also reaches the exposed pad and pin 12.

## Exposed-pad paste coverage (50–80 %: TI SLUA271, IPC-7093)

| Part | EP | Paste | Coverage | Vias in EP (Plugged) |
|---|---|---|---|---|
| U1 RP2040 | 3.2 × 3.2 | KiCad library windowpane | 65 % | 8 |
| U13 TPS65131 | 2.45 × 2.45 | library | 65 % | 9 |
| U11, U12 TPS7A | 1.57 × 1.89 | library | 65 % | 6 each |
| U14 TAC5112 | 2.1 × 2.1 | 4 × 0.94² (TI example stencil) | 80 % | 4 |

## Tombstoning screen

There is no copper pour on F.Cu. A pad's heat sink is its track, plus any GND via within 1.0 mm, since the In1/In2/B.Cu pours are GND and connect vias solid. The screen lists a part when one pad sinks at least 4× the other and the light side is ≤ 0.3 mm of track.

- 42 parts are listed: 33 × 0603, 4 × 0805, 2 × 1210, 1 × 1206, D4 and SW2.
- 40 of the 42 are the same pattern: a decoupling or pull-down part with a GND via on one pad and a 0.2 mm track on the other.
- No part is 0402 or smaller, which is where this asymmetry causes tombstones. At 0603 and up it is routine, so the list is a NOTE for first-article inspection, not a finding.
- Heaviest cases: C97 and D17 (2 GND vias on one side), C45 0805 (2 vias), C102 (0.4 mm + 1 via).
