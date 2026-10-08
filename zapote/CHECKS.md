# Zapote ERC, DRC and layout checks

Start here to find a runnable check, its Rust implementation, its evidence and
what its result means. Run `make -C zapote help` from the repository root for the
command list. The [integration audit](layout-quality/INTEGRATION-AUDIT.md) maps
the existing ERC/DRC modules to actual consumers, including standalone and
test-only code.

## Choose a command

Commands below run from the repository root. Native commands require
`KICAD_PYTHON` pointing to Python with both `pcbnew` and `wx`; unit checks also
require `KICAD_CLI`. On the development Mac:

```sh
export KICAD_PYTHON="/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python"
export KICAD_CLI="/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
```

| Need | Command | Scope / result |
|---|---|---|
| Check any saved board | `make -C zapote check-board BOARD=/abs/board.kicad_pcb PROFILE=fab-profiles/jlcpcb-2layer-2oz.json` | Stackup, KiCad ERC/DRC with one finding per violation (type, location, items, actual/required), and fab-house DFM under a [vendor profile](fab-profiles/). Writes `report.json` and `summary.txt`; exit 0 pass, 1 fail, 2 indeterminate, 3 run error. Pass `ASSEMBLY=<process>` to state the assembly process; without it the result is at best indeterminate. |
| Placement/routing feedback | `make -C zapote check-layout` | Saved copper, paths, pad entries, coupling geometry, courtyards and placement distances; [details](layout-quality/NATIVE.md). |
| Current sharing, R and loss | `make -C zapote check-current` | Includes layout analysis plus the declared two-terminal DC experiments, layer samples and barrel currents; [assumptions and results](layout-quality/CURRENT.md). |
| Maintained unit ERC/DRC and engineering checks | `make -C zapote check-units` | Runs the five units in [units.json](validation/units.json), retaining pass/fail/indeterminate results. The full 120 V board is not registered there. |
| Saved-board stackup | `make -C zapote board-check BOARD=/absolute/path/to/board.kicad_pcb` | Stackup consistency only. `check-boards` applies it to the maintained unit board list. |
| Rust regression and property tests | `PROPTEST_CASES=2048 cargo test --release --locked --manifest-path zapote/Cargo.toml --workspace` | Software tests, including captured native-board replay; live KiCad tests require the separate command below. |
| Combined local checks | `make -C zapote check` | Release Rust tests → layout → current → unit checks. Stops at the first failing step; run individual commands when collecting every verdict. |
| Native manufacturing extraction oracle | `make -C zapote check-native-oracle` | Tests the KiCad-to-Rust P2 geometry boundary. |
| External thermal reference | `make -C zapote check-thermal-oracle` | Requires Gmsh/Elmer; verifies the retained reference model, not assembly cooling qualification. |

`check-layout` and `check-current` default to
[power-stage-120v/native-17/section.kicad_pcb](power-stage-120v/native-17/section.kicad_pcb).
Override `LAYOUT_BOARD` to select another saved candidate compatible with the
endpoint profile. Paths passed to Make are relative to `zapote/`, or absolute.
Neither command edits the board. New evidence directories must not already exist.

## Compare an edit

```sh
make -C zapote check-current CURRENT_RUN_DIR=/tmp/zapote-current-before
make -C zapote check-current \
  LAYOUT_BOARD=/absolute/path/to/edited.kicad_pcb \
  CURRENT_RUN_DIR=/tmp/zapote-current-after \
  CURRENT_BASELINE=/tmp/zapote-current-before/report.json
```

Read `report.json`: `native` contains geometry, `current` contains assumptions,
per-case solutions and gaps, and `comparison.changes` contains deltas. Missing
results remain null. Comparisons require the same evaluator, extractor and
profile. Geometry-only comparisons use `LAYOUT_RUN_DIR` and `LAYOUT_BASELINE`.
Unit runs instead use `RUN_DIR` and produce `summary.json` plus per-unit receipts.

Layout exit 0 means the measurement run completed; reconstruction/model gaps can
still be present in its report. Current exit 0 also requires all declared DC
cases to pass KCL, energy and mesh refinement checks. Neither qualifies the board.
The unit runner uses exit 2 for incomplete evidence;
Make returns nonzero on a failed recipe, so inspect the retained report to
distinguish failure from indeterminate. Do not interpret missing inputs as zero.

## Fab-house DFM profiles

`fab-profiles/*.json` turn a fab house's published capabilities into the P2
manufacturing limits. Each value carries the vendor's text verbatim and the date
it was read; the loader rejects a limit whose quote does not state its number.
Shipped: JLCPCB 2-layer 2 oz, 4-layer 1 oz and 4-layer 2 oz (read 2026-10-08).
Vias use JLC's via rule (diameter ≥ hole + 0.1 mm, ring ≥ 0.05 mm), not the
component-hole ring; rings use the vendor's absolute minimum, not its
recommendation. Rules: annular ring (via/PTH), hole spacing (via/via vs other),
track width, drill size (via, PTH min/max, NPTH), copper-to-edge, board size, and
PTH outer lands (every plated through-hole has copper on F.Cu and B.Cu; pad and via copper
is extracted only on layers KiCad flashes).
Track *spacing* stays with the board's native KiCad DRC rules. `units.json` names
a profile per maintained unit.

## Find implementations and evidence

| Check family / surface | Starting point |
|---|---|
| All nine advisory model families | [Layout-quality catalog](layout-quality/README.md), [Rust model kernels](packages/zapote-drc/src/layout_quality/mod.rs). Supplied-model mode is distinct from native extraction. |
| Native geometry and conductor paths | [Native guide](layout-quality/NATIVE.md), [Rust native analysis](packages/zapote-drc/src/native_layout/mod.rs). |
| Native DC sheet/barrel model | [Current guide](layout-quality/CURRENT.md), [profile and report](packages/zapote-drc/src/native_layout/current.rs), [solver](packages/zapote-drc/src/native_layout/sheet.rs). |
| ERC, manufacturing, isolation, power, switching and operating limits | [Integration audit](layout-quality/INTEGRATION-AUDIT.md): actual callers and remaining inputs for each surface. |
| Legacy Temper rule registry | [Rust registry](https://github.com/BennetLeff/temper/blob/archive/zapote-coil-intake-2026-09-25/packages/temper-drc-rs/src/rules/mod.rs), [donor inventory](validation/inventory-2026-09-12.json). Registration in Temper does not mean execution on Zapote. |
| Native extraction, report persistence and commands | [Extractor](tools/layout_snapshot.py), [Rust harness](packages/zapote-harness/src/layout_native.rs), [CLI](packages/zapote-harness/src/bin/zapote-layout-quality.rs), [Makefile](Makefile). |
| Latest measured results and regression proofs | [Native copper/current evidence](layout-quality/mesh-evidence/README.md), including tests, benchmarks, raw runs, scratch mutations and source hashes. |
| Acceptance objective and missing coverage | [Validation contract](VALIDATION.md), [integration follow-up #1628](https://github.com/BennetLeff/temper/issues/1628). |

Run the native mutation/connectivity proofs explicitly; they are ignored by the
default Rust test invocation because they need KiCad:

```sh
cargo test --release --locked --manifest-path zapote/Cargo.toml \
  -p zapote-harness --test layout_native_cli -- --include-ignored --nocapture
```

For performance measurements:

```sh
cargo bench --locked --manifest-path zapote/Cargo.toml \
  -p zapote-drc --bench layout_quality
```

## Integration and CI checkpoint

Landed on `main` by the 2026-10-08 squash landing PRs, cut from integration
freeze `ea5718069` plus layout-quality `ff28b521e` (full history: tag
`archive/zapote-history-2026-10-08`). `.github/workflows/zapote.yml` runs the
Rust suite and the tree-budget gate (`python3 zapote/tools/evidence_archive.py check`,
also available locally as `make -C zapote check-tree`) on every PR
touching `zapote/**`. Native KiCad commands (`check-layout`, `check-current`,
`check-units`) remain local-only; #1628 tracks CI for them.
Bulk evidence (`*.gz`, `*.npz` outside `packages/`, and any file over 5 MB)
lives in release `zapote-evidence-2026-10-08`; restore it in place with
`python3 zapote/tools/evidence_archive.py fetch`.

CI can run the Rust/PBT suite and native current command, retain artifacts even
on failure, and make missing geometry or failed numerical checks blocking.
Resistance/loss deltas remain advisory until engineering limits are adopted.
`check-current` already includes layout analysis, so a future CI job can avoid
running `check-layout` separately. Keep KiCad ERC/DRC, clearance/creepage, source
parity, manufacturing, thermal and unit-acceptance gates: this model does not
replace their coverage. Switching-state currents, AC/inductance, thermal and
assembly integration remain explicit in the audit.
