# Design-capacity budget gate: fault-tree fan-in reachability

<!-- provenance: commit=9880a3b8dd1d4b4e9ea7cee19779e2d122944e67 dirty=UNKNOWN -->

**Date:** 2026-07-26
**Built at commit:** `45dd80e321b958c3da92c4244bae365c20471f2e` (branch tip of
`docs/methodology-loop-discipline` at the time of this spike; `elec/build/`
is gitignored and was built locally with `make netlist`, exit 0, 69/69
assertions passing)
**Method:** a netlist-graph reachability check
(`scripts/capacity_budget_gate.py`), not a pin-occupancy count. Verified
against the manual surveys in `docs/hardware/UVL02_DESIGN.md` SS7/SS7.1 and
`docs/hardware/OCP02_DESIGN.md`'s "Fault integration" section.
**Finding:** the gate reproduces the manual survey exactly — **0 of 18
SET-path inputs across both `SN74HC4075` packages are genuinely available**
— and names the same reason for each "looks free" input the design docs
found by hand.

## Falsifier (stated before implementation)

> If the check reports **any** SET-path input on `fault_or` or
> `fault_any_or` as genuinely available on the current tree, the check is
> wrong. Go find the bug in the reachability computation before touching
> the expected answer — the design docs' manual survey (two independent
> agents, `docs/hardware/UVL02_DESIGN.md` SS7.1) is ground truth here, not
> the tool.

**Did it fire?** No. `scripts/tests/test_capacity_budget_gate.py::
test_real_tree_reports_zero_available_set_path_inputs` asserts
`total_available == 0` against the real build and passes. The CLI run
against the real tree also confirms this (see "Measured capacity table"
below).

A second, complementary falsifier was also checked, to rule out the
"vacuously always says UNUSABLE" failure mode: **the check must be capable
of reporting AVAILABLE when a candidate input's gate genuinely reaches the
SET pin.** `test_gate1_available_when_output_reaches_set` constructs a
synthetic package whose gate1 output is wired straight to the SET pin and
asserts all three of its inputs come back `AVAILABLE`. This passed. Without
this test, a check that always emitted `UNUSABLE` would trivially "pass"
the zero-capacity falsifier for the wrong reason.

## How reachability is determined

**An input is only "available" if a signal applied there reaches the
destination pin via the netlist's existing, already-built wiring.** This is
computed, not assumed:

1. **Identity**, not from `elec/build/default.net`'s `libsource`/`(comp
   ...)` fields — confirmed on this tree that they alias by footprint:
   `U24` (the real `SN74HC00` SR latch, `safety.latch`) is mislabeled
   `libsource part "SN74HC4075DR"` in `.net` because it shares the
   SOIC-14 footprint with `U22`/`U23`. Ten SOT-23-5 ICs elsewhere in the
   same file are all mislabeled `REF2025AIDDCR` for the same reason
   (verified directly: `U10`, `U12`, `U14` all carry that `libsource part`
   despite being a comparator, an AND gate, and a NAND gate respectively).
   Identity instead comes from **`elec/build/default.csv`** (its `LCSC`
   column is populated from `components.get_mpn()` in atopile's own BOM
   generator — grouped by the real `mpn` attribute set in
   `elec/src/components.ato`, not by footprint) combined with
   `default.net`'s own **`sheetpath`** field (the atopile instance path,
   e.g. `"safety.fault_or"`), which is written from the design hierarchy
   and is *not* subject to the same footprint-aliasing bug. Both are
   disk-persisted outputs of `make netlist` — no console-log capture
   needed (atopile's `designator-map` build target only ever prints to
   the terminal via `rich.print`; it is never written to a file, so it
   cannot be a dependency of a repeatable check).
2. **Connectivity** comes from `default.net`'s `(nets ...)` section,
   parsed by a small hand-written recursive-descent S-expression parser
   (`_parse_sexp` in `scripts/capacity_budget_gate.py`) rather than
   regex/line-scanning, so it can't silently drift if the export is
   reformatted. Every `(ref, pin)` resolves to a net; a net's other
   members are its "occupants."
3. **A datasheet pin-role registry** (`scripts/capacity_budget_packages.yaml`)
   declares, per MPN, which pins are inputs/outputs of which internal gate
   (e.g. `SN74HC4075`'s gate 1 = inputs `A1,B1,C1` → output `Y1`). This is
   a physical-part fact, independent of `elec/src/*.ato`'s module
   hierarchy, so the check keeps working if the fault tree is refactored.
4. **Occupancy classification**, per input pin:
   - `OCCUPIED` — net has another real driver (or another aggregator
     gate's own output pin, classified separately as an internal
     *cascade*, since that's a deliberate design element, not a defect).
   - `GND_TIED` — net is the same net as this package's own `GND` pin
     (resolved generically via the pin-role registry, not a hardcoded net
     name — the actual net is a huge board-wide `PWR_RTN` return that
     nothing in the config names directly).
   - `UNREFERENCED` — a singleton net (nothing wired there at all).
5. **Forward reachability (BFS)**: for every instantiated aggregator gate,
   an edge is added from each input pin's net to the gate's own output
   pin's net (true for any OR-type fan-in gate regardless of the other
   inputs' state). BFS from a candidate gate's output net, over every
   instantiated aggregator's edges, computes the full set of reachable
   nets. **Availability = the declared SET pin's net is in that reachable
   set.** If the *reset-qualifier* pin's net is reachable but the SET
   pin's is not, the input is reported `UNUSABLE` with that specific
   reason (this is `fault_any_or.C2` today — see below). If the gate's
   own output net is a singleton (drives nothing), every candidate input
   on that gate is `UNUSABLE` regardless of its own occupancy — this is
   the "dead gate" case (`fault_or` gate 3, `fault_any_or` gate 3).

This directly encodes the distinction the task called out as the whole
point: a naive "count unconnected pins" check would see `fault_any_or`'s
`A3/B3/C3` as three free inputs and be wrong, because that gate's `Y3`
reaches nothing.

## Measured capacity table (today's tree)

Full text output of `uv run python scripts/capacity_budget_gate.py`
against `elec/build/` built at `45dd80e3` (2 packages, 158 nets, 24 pins,
18 SET-path inputs inspected):

| Package | Gate | Pin | Occupancy | Verdict | Reason |
|---|---|---|---|---|---|
| `safety.fault_or` (U22) | gate1 | A1 | OCCUPIED | UNUSABLE | `safety.ocp.comp` (U15) |
| `safety.fault_or` (U22) | gate1 | B1 | OCCUPIED | UNUSABLE | `safety.ovp.comp` (U16) |
| `safety.fault_or` (U22) | gate1 | C1 | OCCUPIED | UNUSABLE | `safety.thermal.comp` (U17) |
| `safety.fault_or` (U22) | gate2 | A2 | OCCUPIED | UNUSABLE | internal cascade (own Y1 feedback) |
| `safety.fault_or` (U22) | gate2 | B2 | OCCUPIED | UNUSABLE | `safety.latch.Y4` (watchdog, U24) |
| `safety.fault_or` (U22) | gate2 | C2 | OCCUPIED | UNUSABLE | `mcu.mcu` (runaway-cut, U25) |
| `safety.fault_or` (U22) | gate3 | A3/B3/C3 | GND_TIED | UNUSABLE | gate3's `Y3` drives nothing (dead gate) |
| `safety.fault_any_or` (U23) | gate1 | A1 | OCCUPIED | UNUSABLE | internal cascade (`fault_or.Y2`) |
| `safety.fault_any_or` (U23) | gate1 | B1 | OCCUPIED | UNUSABLE | `rtd_pan.fault_nand`/pullup (RTD hw fault) |
| `safety.fault_any_or` (U23) | gate1 | C1 | OCCUPIED | UNUSABLE | `safety.coil_thermal.comp` (**THM-02**, U18) |
| `safety.fault_any_or` (U23) | gate2 | A2 | OCCUPIED | UNUSABLE | internal cascade (own Y1 / latch.A1 loop) |
| `safety.fault_any_or` (U23) | gate2 | B2 | OCCUPIED | UNUSABLE | `mcu.mcu` (reset request, U25) |
| `safety.fault_any_or` (U23) | gate2 | C2 | GND_TIED | UNUSABLE | reaches only the RESET qualifier (`latch.A3`), never SET |
| `safety.fault_any_or` (U23) | gate3 | A3/B3/C3 | UNREFERENCED | UNUSABLE | gate3's `Y3` drives nothing (dead gate) |

**Totals: 18 SET-path inputs inspected, 11 OCCUPIED, 7 GND-tied/unreferenced,
0 AVAILABLE.** SET pin: `SN74HC00DR.A1` (`safety.latch`, U24). Reset
qualifier: `SN74HC00DR.A3`.

This matches, pin-for-pin, the manual survey conclusions in
`UVL02_DESIGN.md` SS7 (re-surveyed against the tree including THM-02,
`d99c88e2`) and `OCP02_DESIGN.md`'s "Fault integration"/"Second finding"
sections — including the specific correction the UVL-02 doc records: an
earlier survey run against a stale worktree (missing THM-02) wrongly
believed `fault_any_or.C1` was still free. The gate here is run against
the tree it was built from, not a cached belief, so it cannot repeat that
mistake as long as `make netlist` is re-run before the gate.

## Anti-vacuity proofs

All exercised directly against the real gate script (`scripts/
capacity_budget_gate.py`) and asserted in `scripts/tests/
test_capacity_budget_gate.py`. None of these exit 0:

| Condition | Exit code | Reproduced with |
|---|---|---|
| Netlist file missing | **5** | `--netlist /tmp/does_not_exist.net` |
| Netlist file empty | **5** | `: > /tmp/empty.net` |
| BOM file missing | **5** | `--bom /tmp/does_not_exist.csv` |
| BOM file empty | **5** | `: > /tmp/empty.csv` |
| Netlist malformed (unbalanced parens) | **5** | truncated `(export (components (comp (ref "U1"))` |
| `required_packages` entry has 0 instances | **5** | netlist with only a resistor, no `SN74HC4075DR`/`SN74HC00DR` |
| `fault_tree.aggregator_mpns` names an MPN absent from `packages` | **5** | config edited to reference `NOT_A_REAL_PART` |
| Destination MPN has 0 or 2+ instances (ambiguous SET pin) | **5** | synthetic netlist with two `SN74HC00DR` instances |
| Real capacity defect: an external signal wired into a dead-output gate | **3** | synthetic fixture, `test_capacity_defect_real_occupant_on_dead_gate` |
| Clean run, 0 defects (today's real tree) | **0** | `uv run python scripts/capacity_budget_gate.py` |

Exit codes measured with `cmd > /tmp/out.txt 2>&1; echo "exit=$?"` (no
pipelines), file read back with the `Read` tool, never `head`/`tail` on
conclusions.

**Non-vacuity of the report itself:** the tool prints and asserts (in the
real-tree test) `Packages inspected: 2 | nets inspected: 158 | pins
inspected: 24 | SET-path inputs evaluated: 18` on every run — the exact
"how many packages/pins/paths were inspected" figure the task asked for,
so a future run that silently inspects 0 packages (e.g. because a refactor
changed `elec/src/main.ato:Top` to no longer emit these designators) is
visibly wrong rather than silently passing.

## What blocks CI (exit 3) versus what's a legitimate state (exit 0)

The gate's **blocking** condition is deliberately narrow and intent-free:
an aggregator gate with a real (non-GND, non-cascade) occupant on one of
its inputs whose own output net is a dead end. That is objectively a bug
regardless of design intent — nobody wires a real fault signal into a gate
that produces no effect on purpose.

**Zero available capacity is not, by itself, a blocking condition** — it
is the design's actual, correctly-diagnosed current state, and forcing it
to be a hard failure would prevent any future commit from landing on an
already-exhausted resource, which is not what was asked. The gate instead
prints a non-blocking `WARNING` when total available capacity is 0,
visible in every CI run and the GitHub step summary, so the next agent
designing a tenth fault source sees "0 available" in the CI log for this
PR without having to re-run the manual survey — the exact gap that caused
today's two-agent duplicate search.

I considered making "reaches only the reset-qualifier pin while occupied"
a blocking condition too, but rejected it: `fault_any_or.C2`'s sibling
inputs (`A2`/`B2`) are *intentionally* the reset-qualifier's real
computation inputs — reaching only `latch.A3` is correct behavior for
that gate, not a bug. Distinguishing "intentional reset-qualifier gate"
from "a fault source accidentally wired onto the reset path" from
netlist structure alone is a real limitation (see UNVERIFIED below); the
narrower dead-output-gate condition avoids false-positiving on this case
while still catching the case that is unambiguously always wrong.

## Other finite resources: covered or excluded

- **Logic-gate fan-in on the fault tree (`SN74HC4075` x2 → `SN74HC00`
  SET path)** — covered, this document.
- **Isolator channels (`UCC21550`, half-bridge gate driver)** — checked by
  hand, not automated: exactly one instance, both of its two channels
  (`INA`/`INB`) are used, one for `gate_hs` and one for `gate_ls`. This is
  a fixed 1:1 match to the half-bridge's own topology (a half-bridge always
  needs exactly two gate drives) with no possibility of a third consumer
  ever contending for a channel here, so it doesn't exhibit the
  "independent surveys keep missing the same trap" failure mode that
  motivated this task. Not automated; flagged for a human to keep in mind
  if a second half-bridge or additional switch is ever added.
- **MCU GPIOs (`ESP32-S3-WROOM-1`)** — out of scope for this pass.
  `elec/src/modules.ato` currently wires roughly 10 GPIOs (`IO4`-`IO7`,
  `IO17`, `IO47`, `GPIO1`-`GPIO3`, ...) out of ~45 exposed by the module's
  pin map — not currently under the kind of contention the fault tree is.
  More importantly, GPIO capacity isn't purely a netlist-reachability
  question the way fan-in is: a GPIO's availability also depends on
  firmware pin-mux configuration and strapping-pin constraints (e.g. boot
  mode pins) that don't appear in the netlist at all, so this would need a
  materially different check, not a small config addition to this one. A
  dedicated spike, not an extension of this gate.
- **Connector pins / test points** — out of scope. `J1` (fan) and
  `TP1`-`TP3` are 2-pin/1-pin parts with a single declared consumer each;
  no multi-consumer contention exists today to make reachability
  ambiguous the way a 3-input OR gate's spare input is.
- **Rail current/power budgets (`power_3v3`, `aux_supply`, bulk caps)** —
  out of scope. This is a continuous quantity (sum of currents/watts
  across consumers), not a discrete channel-occupancy-and-reachability
  problem, and the repo already has a working mechanism for it: `ato
  build`'s own `assert` system currently checks `p_bleed_actual`,
  `p_standby_max < 5W`, etc. directly against derived values (69/69
  passing on this tree). Extending that arithmetic is a different shape
  of check than a graph-reachability gate and was judged out of scope for
  this spike rather than folded in half-built.

## UNVERIFIED

- **Designator stability across builds.** `U22`/`U23`/`U24` are assigned
  by atopile in module-declaration order; identity in this gate is
  actually keyed by `default.csv`'s MPN + `default.net`'s `sheetpath`
  (both stable under reordering), not by designator letter, so this
  should not matter — but I have not tested the gate against a
  deliberately reordered/renamed fault-tree module to confirm designator
  churn alone can't break it. UNVERIFIED.
- **Whether atopile's `sheetpath` field is guaranteed present and
  single-level for every future component**, or whether a deeper
  submodule nesting could ever produce multiple `names` entries in one
  `sheetpath` node (the parser takes the text after the last `::` in a
  single string; I have not found or constructed a netlist with a
  multi-name `sheetpath`, i.e. `(names "a" "b")`, and don't know if
  atopile's exporter ever emits that shape). UNVERIFIED.
- **Behavior on a genuinely huge design** (thousands of nets) —
  performance was not measured; the BFS and net-parsing are both linear
  in netlist size and this tree (158 nets) runs in well under a second,
  but no explicit large-N test exists. UNVERIFIED.
- **The narrower "reset-qualifier-occupied-as-a-bug" detection** described
  above was deliberately not implemented (see rationale) — whether a
  cheap, low-false-positive heuristic for it exists is UNVERIFIED, not
  ruled out.
- **CI wiring was added to `.github/workflows/python-tests.yml` and
  validated locally** (manifest gate, ruff, pytest, the gate itself, all
  exit 0/pass against a freshly rebuilt `elec/build/`) but this branch has
  not been pushed and no actual GitHub Actions run has been observed —
  whether the container image (`ghcr.io/bennetleff/temper-ci:latest`) has
  every dependency this script needs (`pyyaml`, present in `uv.lock`) is
  UNVERIFIED beyond `uv sync --all-packages` succeeding locally.

## Files

- `scripts/capacity_budget_gate.py` — the check.
- `scripts/capacity_budget_packages.yaml` — pin-role registry + fault-tree
  destination config.
- `scripts/tests/test_capacity_budget_gate.py` — 21 tests: parser unit
  tests, synthetic-netlist classification/reachability tests (including
  the positive-AVAILABLE case), anti-vacuity fail-closed proofs, and the
  real-tree integration test that is this gate's own falsifier.
- `.github/workflows/python-tests.yml` — CI wiring in the `test` job,
  immediately after the import-linter gate (same job that already builds
  `elec/build/` before it).
- `scripts/manifest.yaml` — registry entry for the new script.
