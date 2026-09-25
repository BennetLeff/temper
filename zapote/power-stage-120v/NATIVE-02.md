# Second native projection — shelf, unrouted, approved stackup

Generated and checked on 2026-09-25 in `worktrees/ps-oracle`, branch
`feat/ps-oracle-source-changes`, from the audited 102-part source (the
ORACLE-ANSWER.md source changes). Supersedes [native-01](NATIVE-01.md), which
remains only as the pre-stackup fixture for `tests/test_planning_stackup.py`.

**Shelf poses are not a placement. Nothing in native-02 is reviewed for
layout, creepage, thermal or mechanical fit.**

The provisional 220 × 160 mm outline (D1) holds all 102 parts in 150.51 mm
of shelf height with 5 mm margins and 3 mm courtyard gaps. The approved D3
stackup (`stackup.json`: two copper layers, 70 µm, 1.44 mm FR-4 core, 1.6 mm
total) was applied by `tools/planning_stackup.py`, which also adds
`SourceInstance` and `MPN` properties to every footprint and deterministic
pad UUIDs, and removes the archived skeleton's four inner-layer declarations.

## Results

| Check | Measured result | Disposition |
| --- | --- | --- |
| Source audit | 102 components, 73 nets; PASS; 23/23 audit tests | PASS |
| Source reproducibility | Netlist and CSV byte-identical after path normalization between `ps-build` and `ps-oracle` builds | PASS |
| Board footprint count | 102 | PASS |
| Per-pad net parity vs `frozen/default.net` (independent of the manifest) | 292/292 source pin nodes on the mapped pad with the right net; only netless pads are J4's two locating holes | PASS |
| Footprint MPN census vs `frozen/resolved-components.json` | 102/102 | PASS |
| Schematic parity | 0 | PASS |
| Courtyard overlap, clearance | 0 | PASS for shelf; final insulation rules not yet applied |
| DRC `violations` | 18 `lib_footprint_mismatch` warnings, no errors | Same class and cause as native-01 (F.Fab text and field positions; see NATIVE-01.md) |
| DRC unconnected items | 221 | Expected on an unrouted board; KiCad caps this report |
| ERC | 233 warnings, 0 errors: 102 `lib_symbol_issues`, 101 `endpoint_off_grid`, 19 `footprint_link_issues`, 11 `isolated_pin_label` | Same classes as native-01, scaled by the added parts |
| Rust physical-stackup gate (`zapote-board`) | **PASS**: 2 copper layers, 1.600 mm stack = 1.600 mm declared | Was the expected native-01 failure; now resolved by D3 |
| Barrier land patterns | U1/U2 8.10 mm, U9 (ISO7710) 8.10 mm, U4 (AMC1311) 8.85 mm across the barrier | ≥ 8.0 mm basis (D5 proposal) met by the packages' copper |
| Stackup tool tests | 3/3 | PASS |
| Copper tracks / vias / zones | None | Unrouted |

Reports: `native-02/drc.json`, `native-02/erc.json`, `native-02/stackup.json`.
KiCad reports its five default ignored checks in `drc.json`; no custom
exclusions were added.

## Reproduction

From `zapote/power-stage-120v`, with a fresh `temper_design_bundle_python`
built into the repository-root `.venv` per TOOLCHAIN.md:

```sh
python3 tools/build_source.py source-build-01
CARGO_TARGET_DIR=/tmp/ps-native-cargo python3 tools/shelf_poses.py --output /tmp/ps-poses-check.json   # compare to poses.json
../../.venv/bin/python tools/build_native.py native-02 --stackup stackup.json
kicad-cli pcb drc --severity-all --all-track-errors --schematic-parity --format json --output native-02/drc.json native-02/section.kicad_pcb
kicad-cli sch erc --severity-all --format json --output native-02/erc.json native-02/section.kicad_sch
CARGO_TARGET_DIR=/tmp/ps-native-cargo cargo run --quiet --locked --offline --manifest-path ../Cargo.toml --bin zapote-board -- native-02/section.kicad_pcb
../../.venv/bin/python -m pytest -q tests/
```

Runtime: KiCad CLI 10.0.4; Atopile 0.2.69; rustc 1.92.0; CPython 3.12 venv.

## Identity

| Artifact | SHA-256 |
| --- | --- |
| `native-02/section.kicad_pcb` | `113ea4704a94a47b87586dc791e379818c89da8ab438073fccb8bb2317542178` |
| `native-02/section.kicad_sch` | `a8f5a11e3b34b95ceef0c78fe0f813cd95da17757588fabb1ce39c031bb978d1` |
| `native-02/source-manifest.json` | `db0973eb29588221b20c9b00e422d9735ad48ce71adb157ba698e1c1279dd2c9` |
| `poses.json` | `b85a2075bd37c82cda2c54db9c4113991a4639ef840ac77f538836c7a73f179c` |
| `outline.json` | `e629c0ff9e0de17674c523527df7bb33036429f5be286fabf8d6b147abf9f0bd` |
| `stackup.json` | `f78b19657dd082fe74fa142fb7b294b7f31cf62ec5099304bab8f738b47cf473` |

Previews: [board](native-02/board-preview.svg) and
[schematic](native-02/schematic-preview/section.svg).
Digital construction evidence only. Physical assembly, powered tests,
thermal/EMI measurements, insulation tests and certification: **NOT RUN**.
