# Second native projection — shelf, unrouted, approved stackup

Generated and checked on 2026-09-25 in `worktrees/ps-build`, branch
`codex/power-stage-120v-build`, from the audited 114-part source, including
the five oracle source changes, fault-high NAND/non-F isolator, removable
functional PE link R38, axial bus TVS D3, separate PE and M4 coil terminals, two removable external rail links, 5.8 µF
bus bank, revised Y1 pads, and the REF25 bias correction in
[REFERENCE-BIAS.md](REFERENCE-BIAS.md). Supersedes [native-01](NATIVE-01.md), which
remains only as the pre-stackup fixture for `tests/test_planning_stackup.py`.

**Shelf poses are not a placement. Nothing in native-02 is reviewed for
layout, creepage, thermal or mechanical fit.**

The provisional 220 × 160 mm outline (D1) holds all 114 parts in 148.99 mm
of shelf height with 5 mm margins and 3 mm courtyard gaps. The approved D3
stackup (`stackup.json`: two copper layers, 70 µm, 1.44 mm FR-4 core, 1.6 mm
total) was applied by `tools/planning_stackup.py`, which also adds
`SourceInstance` and `MPN` properties to every footprint and deterministic
pad UUIDs keyed by source instance (stable across designator renumbering), and removes the archived skeleton's four inner-layer declarations.

The generated schematic uses 12 columns so all 114 parts fit within A1.
The exported board and schematic were visually inspected after regeneration.
Shelf annotation overlaps remain; this is a connectivity projection, not a
finished layout or assembly drawing.

## Results

| Check | Measured result | Disposition |
| --- | --- | --- |
| Source audit | 114 components, 75 nets; PASS; 48/48 audit tests | PASS |
| Source reproducibility | Netlist and CSV byte-identical after path normalization between two independently compiled source snapshots | PASS |
| Board footprint count | 114 | PASS |
| Per-pad net parity vs `frozen/default.net` (independent of the manifest) | 313/313 source pin nodes on the mapped pad with the right net; 333 physical copper pads verified; eight mechanical holes and 24 paste-only apertures are netless | PASS |
| Footprint MPN census vs `frozen/resolved-components.json` | 114/114 | PASS |
| Schematic parity | 0 | PASS |
| Courtyard overlap, clearance | 0 | PASS for shelf; final insulation rules not yet applied |
| DRC `violations` | 28 `lib_footprint_mismatch` warnings, no errors | Three runs agree; independent pcbnew comparison confirms identical pad geometry and non-text graphics (see native-02/footprint-comparison.json) |
| DRC unconnected items | 258 | Expected on an unrouted board; 258 reported in each of three runs |
| ERC | 270 warnings, 0 errors: 114 `lib_symbol_issues`, 113 `endpoint_off_grid`, 32 `footprint_link_issues`, 11 `isolated_pin_label` | Same classes as native-01, scaled by the added parts |
| Rust physical-stackup gate (`zapote-board`) | **PASS**: 2 copper layers, 1.600 mm stack = 1.600 mm declared | Was the expected native-01 failure; now resolved by D3 |
| Barrier land patterns | U1/U2 8.10 mm, U9 (ISO7710) 8.10 mm, U4 (AMC1311) 8.85 mm across the barrier | Footprint geometry only; does not establish package-surface or complete insulation compliance |
| Scoped adapter tests, including stackup and paste-only footprint regressions | 22/22 | PASS |
| Copper tracks / vias / zones | None | Unrouted |

Reports: `native-02/drc.json`, `drc-02.json`, `drc-03.json`,
`erc.json`, `stackup.json`, `source-oracles.json` and
`footprint-comparison.json` and `physical-pad-check.json` (all under `native-02/`).
KiCad reports its five default ignored checks in `drc.json`; no custom
exclusions were added.

## Reproduction

Use a **fresh checkout** (no `source-build-01` directory), from
`zapote/power-stage-120v`, with the fresh native bridge configured per
TOOLCHAIN.md. Both builders refuse existing output directories. These commands
write a new temporary native projection and preserve committed evidence:

```sh
PS_BRIDGE_PY=/Users/bennet/Desktop/temper/worktrees/ps-toolchain-sol/.venv/bin/python
PS_CHECK_DIR="$(mktemp -d)"
python3 tools/build_source.py source-build-01
CARGO_TARGET_DIR=/tmp/ps-native-cargo python3 tools/shelf_poses.py --output "$PS_CHECK_DIR/poses.json"
cmp poses.json "$PS_CHECK_DIR/poses.json"
"$PS_BRIDGE_PY" tools/build_native.py "$PS_CHECK_DIR/native" --stackup stackup.json
kicad-cli pcb drc --severity-all --all-track-errors --schematic-parity --format json --output "$PS_CHECK_DIR/drc.json" "$PS_CHECK_DIR/native/section.kicad_pcb"
kicad-cli sch erc --severity-all --format json --output "$PS_CHECK_DIR/erc.json" "$PS_CHECK_DIR/native/section.kicad_sch"
CARGO_TARGET_DIR=/tmp/ps-native-cargo cargo run --quiet --locked --offline --manifest-path ../Cargo.toml --bin zapote-board -- "$PS_CHECK_DIR/native/section.kicad_pcb"
/tmp/ps-check-venv/bin/python -m pytest -q tests/
```

The native adapter and test environment both require `kiutils==1.4.8`; install
it in the selected Python environments before running the commands above.

Runtime: KiCad CLI 10.0.4; Atopile 0.2.69; rustc 1.92.0;
CPython 3.14.7 native bridge; Python 3.12.12 test venv. The absolute Python
paths above identify this run's host runtimes; configure equivalent fresh
runtimes when reproducing elsewhere. `native-02/verification.json` records
source and artifact content hashes, checkout revision, dirty state at
measurement, and the three-run DRC sample count/ranges. The source content
hashes identify the measured edit state; the pre-edit HEAD is not presented
as its complete source identity.

## Identity

| Artifact | SHA-256 |
| --- | --- |
| `native-02/section.kicad_pcb` | `d571bfe0560d93ef20cca98648b595c69dbcff816ca778babb23b341a8a40fa9` |
| `native-02/section.kicad_sch` | `5c4ce191ae868a28bee17418fd663b77193a3fab1c700614c6fdf7a1c8428fbf` |
| `native-02/source-manifest.json` | `1fde8f30a8a65d6987191e46dcb3d8da6627238545b1d8c1581356ce5711e0d8` |
| `poses.json` | `3904a40508e062e31d8413e32908473573c5acacbe63c52d31dd9d574fc9d199` |
| `outline.json` | `e629c0ff9e0de17674c523527df7bb33036429f5be286fabf8d6b147abf9f0bd` |
| `stackup.json` | `f78b19657dd082fe74fa142fb7b294b7f31cf62ec5099304bab8f738b47cf473` |

Previews: [board](native-02/board-preview.svg) and
[schematic](native-02/schematic-preview/section.svg).
Digital construction evidence only. Physical assembly, powered tests,
thermal/EMI measurements, insulation tests and certification: **NOT RUN**.

J1 now carries L/N only, with PE on separate J6. C3/C4 nominal copper gap is
8.50 mm. These resolve the prior package-spacing blockers but do not establish
assembled creepage. The six M4 terminals retain all 24 paste apertures and all
24 same-number copper pads; source/source-native checks cover each physical pad.
The native adapter now excludes non-copper apertures from its electrical map
while still failing closed on unmapped copper pads. Rust shelf ordering is by
height, width, then instance path so the new parts fit the approved outline.

Final insulation rules and deliberate placement remain unfinished. TVS surge
performance, all terminal/lug and four-pin capacitor assembly details, HOT5
behavior, physical tests, lab review and the RCA teardown remain open. See
ASSEMBLY.md, DC-LINK-CLAMP.md and PROTOTYPE-POWER-LOOP.md.

The final terminal-library vendoring rebuild produced byte-identical board and
schematic files; only library-origin entries in the source manifest changed.
The recorded DRC/ERC and pad measurements therefore apply to the final bytes.
