# P1 rail-order fixture PCB candidate — digital receipt

Date: 2026-09-23. Status: **lab-only routed PCB candidate**. This is a passive measurement coupon, not an auxiliary power supply, a protected rail producer, an approved mating harness, or an assembled/energized test. No physical board or waveform has been measured.

## Source and native identity

Atopile 0.2.69 compiled `rail-order-fixture-01/ato.yaml` and `elec/src/rail_order_fixture.ato` with SHA-256 `b90445a5b640bbfa57acb1a7c6d23c761e2f387ad286eb62d2b5e3f600ba99a4` and `8eb6791f8111d7fa7e59e42edbf43fb6d434922ad0fd1e90e43c997098db064d`. The generated [compiled.net](../../rail-order-fixture-01/candidate/source/compiled.net) is `a4ec5055939e6991849b182611de26e408366248f50e025d9a118eb3e362b567` at this checkout path; Atopile embeds its absolute build path, so that raw hash is path dependent. The [normalized.net](../../rail-order-fixture-01/candidate/source/normalized.net) is `9203c12513bf1e9327ed137a74422f5bddd8b8fbb1ea65033fe0726ddbd18708` and changes only the three generic symbol part IDs. The normalizer asserts that all compiled footprints, pins and nets remain equal.

The [native schematic](../../rail-order-fixture-01/candidate/rail-order-fixture.kicad_sch) SHA-256 is `44aa563e8a047bf15706c7db60f6572dcc520320063ffef5bd1eadf7455afbba`; the [routed PCB](../../rail-order-fixture-01/candidate/rail-order-fixture.kicad_pcb) is `2ee6bcb407eba3af88f05e37b8e811bd378dadd2038de25c9cc7bc7f89147d8f`. Pinned local copies of three standard KiCad footprints and a generated local symbol library resolve the exact component IDs. Generic header footprints are construction candidates only. The board uses a 100 × 55 mm two-layer outline and a copied standard project-rule baseline from the standalone gate-drive candidate; it does not inherit that unit's electrical acceptance.

## Verification

- Existing Rust rail-order audit: **10 expected nets, 13 passive components, 10 required fault-matrix cases, PASS**; analog status remains **INDETERMINATE**. Its 11 adverse tests pass, including AUX/logic short, SELV return join, missing ENA observation and recovered rail mistaken for re-arm.
- `kicad-cli` **10.0.4** ERC: [erc.rpt](erc.rpt), **0 errors and 0 warnings**. Exact KiCad XML schematic export matches the compiled Atopile source at **10 nets and 24 `(reference,pin)` nodes**; this check catches the earlier `lib:None` symbol-collapse error that silently omitted J3 pins 2–10.
- `kicad-cli` **10.0.4** DRC: [drc.rpt](drc.rpt), **0 violations, 0 unconnected pads, 0 footprint errors**. Independent `pcbnew` pad comparison matches the compiled source at **10 nets and 24 `(reference,pad)` pairs**, with zero connectivity unconnected count. Copper and top silkscreen were visually inspected by PDF render. No fabricated board was inspected.
- A deliberately bad silk label did trigger a KiCad CLI 10/macOS `SwiftNativeNSArray Array index out of range` crash while reporting the violation. Individual rule isolation identified `silk_over_copper` and `silk_overlap`; moving/hiding the offending labels produced the saved clean DRC result. The crash does not substitute for a passed DRC.

## Replay

From `rail-order-fixture-01/`, run Atopile 0.2.69 `build`. In this host environment `ato` is a broken symlink; the cached local invocation is:

```sh
PYTHONPATH="$(find /Users/bennet/.cache/uv/archive-v0 -mindepth 1 -maxdepth 1 -type d -print | paste -sd ':' -)" PYTHONDONTWRITEBYTECODE=1 /Users/bennet/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3.11 -m atopile.cli.cli build
```

From repository root, run `python3 zapote/auxiliary/rail-order-fixture-01/tools/normalize_netlist.py`, `python3 scripts/gen_schematics.py --netlist zapote/auxiliary/rail-order-fixture-01/candidate/source/normalized.net --bom-csv zapote/auxiliary/rail-order-fixture-01/build/default.csv --layout-config zapote/auxiliary/rail-order-fixture-01/candidate/schematic_layout.json --output-dir zapote/auxiliary/rail-order-fixture-01/candidate --no-oracle`, and `python3 zapote/auxiliary/rail-order-fixture-01/tools/finish_schematic.py`. Use KiCad's bundled Python to run `tools/build_board.py`, then run `kicad-cli sch erc` and `kicad-cli pcb drc` on the native paths. The `--no-oracle` generator flag only avoids its shared generic-symbol oracle; exact KiCad exported-node equality was separately checked above.

## Open product and physical gates

The Rev38 HOT H1/H2 source, SELV source, isolated inverter bias, branch fusing, current and startup envelopes, output peak, insulation, and installed temperature remain unselected or unmeasured. The fixture itself requires a reviewed coupon/harness pin map, isolated current-limited low-energy supply limits, independent discharge check before any relevant hardware connection, and instrument grounding/load review before a powered capture. It cannot directly mate with Rev38 or be used to infer a safe gate-off state.
