# First native projection — shelf, unrouted

Generated and independently checked on 2026-09-25 in
`worktrees/ps-build`, branch `codex/power-stage-120v-build`, from the audited
source at `ad51823308f3a65d7bfe86351a128af5f237b31e`. No electrical source
was changed. The coordinator regenerated the worker's result rather than
copying its board; the final CT land-pattern correction was then regenerated in the integration checkout.

**Shelf poses are not a placement. Nothing in native-01 is reviewed for
layout, creepage, thermal or mechanical fit.**

The provisional outline is 220 × 160 mm. All 91 parts fit in 149.41 mm of
height with 5 mm edge margins and 3 mm courtyard gaps. Rust owns ordering,
packing, conservative micrometre rounding, pad-fallback expansion and
overflow rejection. KiCad supplies footprint bounds. The original shelf reproduced across two checkouts; final corrected geometry
was regenerated and checked against the source.

## Results

| Check | Measured result | Disposition |
| --- | --- | --- |
| Source audit | 91 components, 67 nets; PASS | Source identity/connectivity only |
| Frozen netlist and CSV | Byte-identical after source-path normalization | PASS |
| Board/source oracle | 91 footprints, 67 nets, raw pad numbers and outline match compiled source | PASS |
| Schematic/source oracle | 264 pin assignments, 56 multi-pin nets; connectivity partitions isomorphic | PASS; single-pin nets excluded by this oracle |
| Board footprint count | 91 | PASS |
| Schematic parity | 0, in each of three DRC runs | PASS |
| Courtyard overlap | 0, in each run | PASS for shelf |
| Clearance findings | 0, in each run | Shelf baseline only; final insulation rules absent |
| DRC `violations` array | 18 `lib_footprint_mismatch` warnings; zero `silk_over_copper`; no errors in this array | Explained below |
| DRC unconnected items | 199 reported in each run | Expected error category on unrouted board; capped, therefore **at least 199**, not an exact census |
| ERC | 210 warnings, 0 errors | Explained below |
| Rust physical-stackup gate | FAIL: `DRC.BOARD.STACKUP`, `requires exactly one stackup field; found 0` | Expected Part 3 failure; Part 4 prerequisite |
| Copper tracks / vias / zones | None | Unrouted |

All three DRC runs used the same board hash and `--all-track-errors
--schematic-parity`; reports are `native-01/drc.json`, `drc-02.json` and
`drc-03.json`. No custom exclusions were added. KiCad reports five default ignored checks:
missing courtyard, track endpoint centered on via, tuning-profile geometry,
symbol footprint filters, and footprint component-type consistency. These
are recorded in each JSON report; this is not an all-checks fabrication gate. The generated candidate library
and sibling `fp-lib-table` were present. The Rust gate report is
`native-01/stackup.json`.

The generator retains the archived **six-copper-layer candidate template**.
Its layer declarations are not a physical stackup and are not approval of
six layers. The proposed Part 4 two-layer, 2 oz stackup still needs D3 and a
new generated board. No custom creepage rules or routing acceptance is
claimed for this shelf.

## Warning explanations

The 18 footprint-library mismatches name BR1, C1–C4, D1–D2, F1, J1–J4,
PS1–PS2, and Q2/Q3/Q5/Q6. Independent `pcbnew` comparison against the
vendored libraries proves identical pad numbers, local integer coordinates,
size, drill size, shape, orientation, layers, attribute and roundrect radius
ratio for all 18. Graphic class/layer counts also match. Graphic bounding-box
differences occur only on F.Fab text: `${REFERENCE}` expands to the actual
designator on 17 footprints. BR1 has no such graphic difference; its
Reference/Value fields move from their donor positions to hidden F.Fab
fields under the archived serializer repair. That repair applies to the
other fields too. Copper, courtyard and silkscreen graphic bounds are
unchanged. `native-01/footprint-comparison.json` retains this comparison.
These annotation differences remain reported, not waived for fabrication.

The initial CST3015 donor produced two silkscreen-over-primary-pad warnings.
Checking the manufacturer drawing exposed a more serious land-pattern error.
The corrected footprint now uses 4.8 × 9.0 mm primary pads and an 18.5 mm
primary-to-secondary copper edge gap; both warnings disappear. See F7 in
`FOOTPRINTS.md`. Its 18.5 mm PCB gap does not establish package creepage.

ERC warnings are:

- 91 `lib_symbol_issues`: synthetic embedded symbols have no configured
  external symbol-library nickname.
- 18 `footprint_link_issues`: schematic ERC lacks configured external
  library links for these symbols; board vendoring and pin mapping pass.
- 90 `endpoint_off_grid`: synthetic symbol/pin positions fall off KiCad's
  preferred schematic grid; labels coincide with their corresponding pins
  and native parity is zero.
- 11 `isolated_pin_label`: explicit single-pin source nets retained to keep
  source-to-native parity, including unused pins.

The A1 schematic is a synthetic connectivity projection with global labels,
not a functional schematic review. The flat path was restored from the
archive and given room for 91 symbols; its columns, rows and label directions
were visually checked. Existing hierarchical generation retains its defaults.

## Reproduction and environment

Runtime: KiCad CLI 10.0.4; Atopile 0.2.69; kiutils 1.4.8; Rust 1.92.0.
The source wrapper uses the cached pinned Atopile environment. The native
wrapper uses the isolated bridge interpreter at
`/Users/bennet/Desktop/temper/worktrees/ps-toolchain-sol/.venv/bin/python`
(CPython 3.14.7), with the fresh `temper_design_bundle_python` extension.
The full ten-extension gate is not claimed green in this minimal venv;
only the required design-bundle extension is installed and checked fresh.

From the unit directory, on a fresh checkout with no output directories:

```sh
python3 tools/build_source.py source-build-01
# poses.json is committed; use a new output to verify deterministic generation.
CARGO_TARGET_DIR=/tmp/ps-native-cargo python3 tools/shelf_poses.py --output /tmp/ps-canonical-poses.json
/Users/bennet/Desktop/temper/worktrees/ps-toolchain-sol/.venv/bin/python tools/build_native.py native-01
kicad-cli sch erc --severity-all --format json --output native-01/erc.json native-01/section.kicad_sch
kicad-cli pcb drc --severity-all --all-track-errors --schematic-parity --format json --output native-01/drc.json native-01/section.kicad_pcb
CARGO_TARGET_DIR=/tmp/ps-native-cargo cargo run --quiet --locked --offline --manifest-path ../Cargo.toml --bin zapote-board -- native-01/section.kicad_pcb
kicad-cli pcb export svg --mode-single --layers F.Cu,F.SilkS,F.CrtYd,F.Fab,Edge.Cuts --fit-page-to-board --exclude-drawing-sheet --output native-01/board-preview.svg native-01/section.kicad_pcb
kicad-cli sch export svg --output native-01/schematic-preview native-01/section.kicad_sch
```

The second and third DRC commands used output names `drc-02.json` and
`drc-03.json`. On this Mac, sandboxed KiCad DRC crashes in the native macOS
runtime; the actual measurements used a scoped unsandboxed CLI invocation.
Fontconfig emits configuration warnings but ERC/DRC and SVG exports complete.

Independent source oracle results and hashes are retained in
`native-01/source-oracles.json`. Board-to-schematic parity alone would not
prove either artifact agrees with the compiled source. The source adapter
also verifies every recorded source and build hash before parsing; mutation
tests prove that altered netlist/CSV exports and missing hash entries fail.

The missing runtime dependencies uncovered by generation were the archived
candidate-board functions in `scripts/gen_pcb_skeleton.py` and flat-schematic
functions in `scripts/gen_schematics.py`, beyond Part 1's initial salvage.
The shared adapter now consistently uses per-designator BOM part identity
for board and schematic Value fields; nominal values remain in the manifest's
`source_attributes`. Unit-specific manifest/schema labels preserve the
current-sense defaults. Regression tests cover nominal-value/MPN disagreement,
metadata defaults and the 91-symbol page envelope.

## Identity

| Artifact | SHA-256 |
| --- | --- |
| `native-01/section.kicad_pcb` | `ace40079ee7f9dbde98810a250079714d4f102bb9cd4a0925ba589233281414d` |
| `native-01/section.kicad_sch` | `16e939d1deb481ec8a1bb5b210cdf18f208e113d7fc72aa7cf756f7bcdf319b9` |
| `native-01/source-manifest.json` | `46c6aa2b893f1ef4ba7d57b8c04e51f4230b5b1656cb18370ab03dff1c1507fc` |
| `poses.json` | `1fdc0e5c68433fe22fcae7d4b09e6874dc68267fe121170898aa60566213649f` |
| `outline.json` | `e629c0ff9e0de17674c523527df7bb33036429f5be286fabf8d6b147abf9f0bd` |
| Strict bridge extension | `3cfae7fd068e252d0fa3680a4673c191d236643d8108df72807f838027cad09f` |

Previews: [board](native-01/board-preview.svg) and
[schematic](native-01/schematic-preview/section.svg).
Digital construction evidence only. Physical assembly, powered tests,
thermal/EMI measurements, insulation tests and certification: **NOT RUN**.
