# Second native projection — shelf, unrouted, approved stackup

Generated and checked on 2026-09-25 in `worktrees/ps-build`, branch
`codex/power-stage-120v-build`, from the audited 102-part source, including
the five oracle source changes and the REF25 bias correction in
[REFERENCE-BIAS.md](REFERENCE-BIAS.md). Supersedes [native-01](NATIVE-01.md), which
remains only as the pre-stackup fixture for `tests/test_planning_stackup.py`.

**Shelf poses are not a placement. Nothing in native-02 is reviewed for
layout, creepage, thermal or mechanical fit.**

The provisional 220 × 160 mm outline (D1) holds all 102 parts in 150.51 mm
of shelf height with 5 mm margins and 3 mm courtyard gaps. The approved D3
stackup (`stackup.json`: two copper layers, 70 µm, 1.44 mm FR-4 core, 1.6 mm
total) was applied by `tools/planning_stackup.py`, which also adds
`SourceInstance` and `MPN` properties to every footprint and deterministic
pad UUIDs keyed by source instance (stable across designator renumbering), and removes the archived skeleton's four inner-layer declarations.

The generated schematic uses 12 columns so all 102 parts fit within A1.
The exported board and schematic were visually inspected after regeneration.
Shelf annotation overlaps remain; this is a connectivity projection, not a
finished layout or assembly drawing.

## Results

| Check | Measured result | Disposition |
| --- | --- | --- |
| Source audit | 102 components, 73 nets; PASS; 27/27 audit tests | PASS |
| Source reproducibility | Netlist and CSV byte-identical after path normalization between two independently compiled source snapshots | PASS |
| Board footprint count | 102 | PASS |
| Per-pad net parity vs `frozen/default.net` (independent of the manifest) | 292/292 source pin nodes on the mapped pad with the right net; only netless pads are J4's two locating holes | PASS |
| Footprint MPN census vs `frozen/resolved-components.json` | 102/102 | PASS |
| Schematic parity | 0 | PASS |
| Courtyard overlap, clearance | 0 | PASS for shelf; final insulation rules not yet applied |
| DRC `violations` | 18 `lib_footprint_mismatch` warnings, no errors | Three runs agree; independent pcbnew comparison confirms identical pad geometry and non-text graphics (see native-02/footprint-comparison.json) |
| DRC unconnected items | 221 | Expected on an unrouted board; 221 reported in each of three runs |
| ERC | 233 warnings, 0 errors: 102 `lib_symbol_issues`, 101 `endpoint_off_grid`, 19 `footprint_link_issues`, 11 `isolated_pin_label` | Same classes as native-01, scaled by the added parts |
| Rust physical-stackup gate (`zapote-board`) | **PASS**: 2 copper layers, 1.600 mm stack = 1.600 mm declared | Was the expected native-01 failure; now resolved by D3 |
| Barrier land patterns | U1/U2 8.10 mm, U9 (ISO7710) 8.10 mm, U4 (AMC1311) 8.85 mm across the barrier | Footprint geometry only; does not establish package-surface or complete insulation compliance |
| Stackup tool tests | 4/4 | PASS |
| Copper tracks / vias / zones | None | Unrouted |

Reports: `native-02/drc.json`, `drc-02.json`, `drc-03.json`,
`erc.json`, `stackup.json`, `source-oracles.json` and
`footprint-comparison.json` (all under `native-02/`).
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
| `native-02/section.kicad_pcb` | `0c0cf92e1d4ba35334e7af6f7f63e4edaee0c31b02a754fb3eeea0c0b26081fa` |
| `native-02/section.kicad_sch` | `59d26f9d73f0f2c4251759c89c52e9aafd2d782cf1880d6af2801630c389412f` |
| `native-02/source-manifest.json` | `ca818c19c1bd8d2c516239ae63240ef173f3785dc28377a769a0b6d41f9df530` |
| `poses.json` | `b85a2075bd37c82cda2c54db9c4113991a4639ef840ac77f538836c7a73f179c` |
| `outline.json` | `e629c0ff9e0de17674c523527df7bb33036429f5be286fabf8d6b147abf9f0bd` |
| `stackup.json` | `f78b19657dd082fe74fa142fb7b294b7f31cf62ec5099304bab8f738b47cf473` |

Previews: [board](native-02/board-preview.svg) and
[schematic](native-02/schematic-preview/section.svg).
Digital construction evidence only. Physical assembly, powered tests,
thermal/EMI measurements, insulation tests and certification: **NOT RUN**.
