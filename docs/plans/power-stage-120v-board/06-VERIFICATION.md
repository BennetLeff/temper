# Part 6: verification, frozen identity and review package

**Goal:** one reproducible, hash-pinned record showing the routed board is a
faithful projection of the audited source and passes every digital gate. Plus a
**review-only** fabrication package: Gerbers, drill, BOM, positions, renders.
This is **not** an order. It proves nothing physical.

**Precondition:** Part 5 merged: routed board with 0 unconnected, 0 violations,
parity 0.

## 6.1 Freeze

1. Copy the final routed native directory to `native-final/`. Nothing in it may
   be hand-edited afterward.
2. Write `tools/check_native_parity.py`. For every footprint pad in
   `native-final/section.kicad_pcb` that has a net, look up `(reference, pad)` in
   `native-final/source-manifest.json` → `strict_pin_map`, map the source
   `(reference, pin)` to its net via `bridge.nets`, and require the board pad's net
   to equal it. Also require:
   - every `(reference, pin)` in `bridge.nets` has a board pad
   - the only netless pads are those listed in `unconnected_pads`

   Print totals and exit non-zero on any mismatch. **Mutation-test it:** swap two
   pads' nets in a temporary copy of the board and confirm the script fails.
   Commit that test as a function in the script or in a `tests/` file.

## 6.2 Gates (all must pass; paste the outputs into `ACCEPTANCE.md`)

Run from `zapote/power-stage-120v`:

| Gate | Command | Pass |
| --- | --- | --- |
| Source audit | `rustc --edition=2021 -O audit.rs -o /tmp/a && /tmp/a source-build-01/build/default.net source-build-01/build/default.csv source-build-01/resolved-components.json` | `PASS` |
| Audit mutations | `rustc --edition=2021 --test audit.rs -o /tmp/at && /tmp/at` | all tests pass |
| Frozen-copy identity | compare `source-build-01` outputs to `frozen/` after path normalization (as in Part 1 step 1.4) | identical |
| Native parity | `python3 tools/check_native_parity.py native-final` | 0 mismatches |
| KiCad schematic parity + DRC | `kicad-cli pcb drc --severity-all --all-track-errors --schematic-parity --refill-zones --format json --output native-final/drc.json native-final/section.kicad_pcb` | parity 0, unconnected 0, **errors 0**; each warning listed and explained |
| ERC | `kicad-cli sch erc --severity-all --format json --output native-final/erc.json native-final/section.kicad_sch` | errors 0; warnings explained |
| Stackup gate | `cargo run --quiet --locked --manifest-path ../Cargo.toml --bin zapote-board -- native-final/section.kicad_pcb` | pass |
| Design rules present | `native-final/section.kicad_dru` exists, and the barrier self-test from Part 5 step 1 is recorded | yes |
| Footprint census | 91 footprints; each footprint's `MPN` property equals `resolved-components.json` for its `SourceInstance` | 91/91 |
| Zapote workspace | `cargo test --locked --manifest-path ../Cargo.toml --workspace` | still all pass |

A gate that can't run is **INDETERMINATE**, never PASS. Say why.

## 6.3 Review package (not an order)

```sh
P=review-package-$(date -u +%Y%m%d)
mkdir -p $P/gerbers $P/drill
kicad-cli pcb export gerbers --output $P/gerbers/ native-final/section.kicad_pcb
kicad-cli pcb export drill   --output $P/drill/   native-final/section.kicad_pcb
kicad-cli pcb export pos --format csv --units mm --output $P/positions.csv native-final/section.kicad_pcb
kicad-cli pcb export pdf --mode-single --layers F.Cu,B.Cu,F.SilkS,Edge.Cuts --output $P/board.pdf native-final/section.kicad_pcb
kicad-cli sch export pdf --output $P/schematic.pdf native-final/section.kicad_sch
cp source-build-01/build/default.csv $P/bom.csv
```

Then:

- **Reconcile the BOM:** every designator in `positions.csv` appears in `bom.csv` with
  the MPN from `resolved-components.json`. The eight hand-authored or copied
  footprints appear in `FOOTPRINTS.md`. Record `91/91`.
- **Off-board items:** list them in `$P/OFF-BOARD.md`. They aren't in the source:
  - coil, and coil leads with lugs
  - two Microtemp G4A thermal cutoffs (heatsink ~120 °C; under-glass TBD) and their wiring to J3
  - heatsink, insulating pads, fan
  - the 6.3 × 32 mm fuse itself, if the clips are fitted empty
  - mains cord with strain relief
  - the SELV harness to the controller
- **`$P/MANIFEST.json`:** the SHA-256 of every file in the package and of `native-final/section.kicad_pcb`.

## 6.4 `ACCEPTANCE.md` (the single record)

Sections:

1. **Identity:** hashes of the source `.ato` files, `source-build-01` outputs,
   `frozen/`, `native-final/` files and the review package manifest. Tool versions:
   Atopile, kicad-cli, rustc, strict-bridge extension.
2. **Digital gates:** the 6.2 table with actual outputs: PASS / FAIL / INDETERMINATE.
3. **Open or provisional items,** each with an owner:
   - insulation basis D5 and any certification-lab question
   - PROVISIONAL footprints
   - the under-glass cutoff rating
   - the coil (resonant bank value tied to the 70 µH nominal)
   - "C" parts in `POWER-SECTION.md`
4. **NOT RUN (physical),** listed explicitly:
   - assembly inspection
   - hipot / insulation test
   - low-voltage power-up
   - gate waveforms and dead time
   - OCP trip calibration
   - thermal run
   - conducted-EMI pre-scan
   - full-power operation
   - safety certification
5. **Statement:** "Digital construction evidence only. No fabrication order, no
   energized test, no safety or EMC compliance is claimed."

## Acceptance checklist

- [ ] `native-final/` frozen; `check_native_parity.py` passes, with its mutation test
- [ ] Every gate in 6.2 PASS, or INDETERMINATE with a reason; no FAIL
- [ ] Review package and manifest; BOM reconciled 91/91
- [ ] `ACCEPTANCE.md` complete with the NOT RUN list
- [ ] PR titled `feat(power): power-stage-120v verified native board (review package)`

## Stop and ask if

- any gate FAILs, and the fix would change the source or placement
- the fabricator, stackup or insulation choices need an owner decision before export
