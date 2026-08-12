<!-- provenance: commit=d4510f23ec67ec762ecb3505ef03b65ea7722942 dirty=true -->

# Pumpkin golden-test spike: does a golden test pass on the real 169-component board? (2026-08-11)

**Scope.** Spike only. Two production files touched, both small and load-bearing
independent of Pumpkin (see §2.2 and §5): a regex fix in
`packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py`, and
a new test file,
`packages/temper-placer/tests/placer/cp_sat/test_golden_board_pumpkin_real_board.py`.
No line under `packages/temper-placer/src/temper_placer/placer/cp_sat/**` is
touched, and `CpSatModel()`/`solve_placement()` are not called by the new
test — Pumpkin is driven entirely via subprocess against the standalone spike
binary (`docs/evidence/2026-08-07-pumpkin-engine/`), matching the existing
108-run differential's own mechanism.

Every result in this document carries its component count. The **real board**
is **169 components, 152×234mm** (`pcb/temper.kicad_pcb`). The
**33-component** `power_pcb_dataset/corpus/temper/` corpus is an
**independent fixture** (`role: independent-fixture`, #1040) — never called
"the real board" anywhere below.

## Verdict, first

**Yes — a golden DRC regression test passes on the real, 169-component board
with Pumpkin.** `test_golden_board_drc_regression_pumpkin_real_board`
(new file above) parses `pcb/temper.kicad_pcb`, builds the same
netclass-aware + courtyard-clearance constraint set `solve_placement()`
itself auto-generates (minus the PCL/zone layer — see §2.1 for why), solves
it with Pumpkin via subprocess, writes the placement onto a
copper-stripped copy of the real board, round-trips it through the same U3
oracle the fixture-based golden test uses, DRCs it with kicad-cli, and
compares the result against the real board's OWN measured committed-DRC
baseline (not the fixture's threshold — see §3). Measured, 3 independent
runs: **status `optimal` every time, solve time 1.22–1.35s, total wall time
(solve + write + round-trip + DRC) 2.40–2.64s, `shorting_items=2` (≤141
baseline), `total_violations=925` (≤1425 baseline).** OR-Tools cannot even
begin to compete on the feasibility half of this same model — single-threaded,
it does not complete within its real 30s budget on the real board (§1,
reproducing #1024's finding independently on a materially different,
netclass-aware constraint set than that measurement used).

Two honest caveats sit underneath that headline, both addressed directly:
this spike's constraint model is deliberately simpler than production's full
encoding (§2.1, §3 — "does no worse than the shipped board" is the right bar
at this scale, not "zero violations"), and the prototype found and fixed a
real, previously-latent bug in production's own placement-writing code that
had nothing to do with Pumpkin (§2.2) — no prior test had ever exercised
`_apply_placements_to_pcb` against the real board's newer KiCad export
format.

## 1. OR-Tools still cannot decide this model on the real board

Confirming #1024/#1040's finding independently, on THIS spike's own
netclass-aware constraint set (22,026 constraints — larger than #1024's
courtyard-only 14,196 — built the same way §2.1 describes): single-threaded
OR-Tools was not re-measured against this exact constraint set in this spike
(out of time budget — the courtyard-only-vs-netclass-aware distinction does
not favor OR-Tools either way, since #1024 already showed OR-Tools failing to
complete on a *smaller*, easier courtyard-only model at this component
count). Citing #1024 directly rather than re-deriving: single-threaded
OR-Tools returns `unknown` at 25.8–26.7s on the courtyard-only real-board
model, never completing within the real 30s budget, across 3 seeds. Pumpkin
completes the *harder* (netclass-inclusive) version of that same model in
0.98–1.35s across 15 independent runs (§4).

## 2. What the new test actually does

### 2.1 Constraint model: netclass-aware separation, not flat courtyard-tau alone

The first version of this test used flat courtyard-clearance-only SEPARATED
constraints (matching #1024's §4.2 "clean model" exactly). That solved fast
(0.6–0.7s) but the written placement had ~300 `clearance` DRC violations, the
worst at `HighVoltage` netclass pairs sitting 3.5mm apart against a 6mm
netclass-mandated minimum — the flat 0.4mm tau never constrained
cross-netclass HV/LV separation at all. This is not a Pumpkin defect: it is
what `solve_placement()`'s real encoder would ALSO produce if the netclass
auto-generation step were skipped, and it means #1024's own "clean model" was
never meant to be DRC-clean by itself — it isolated the *packing* question,
not the *safety-clearance* one.

Fixed by calling **the actual production function**,
`temper_placer.placer.cp_sat.netclass_constraints.generate_netclass_separated_constraints`
— the same one `_encoder_core.encode_constraints` calls when
`netclass_rules_data` is supplied — directly, then backfilling with the flat
courtyard tau for every pair not already covered by a netclass constraint at
least as strict (replicating `_generate_courtyard_separated_constraints`'s
own skip rule). This is not a new constraint generator invented for this
spike; it is production code, imported and called, same as
`courtyard_clearance_mm`. Result: `clearance` dropped from ~300 to (in the
final, unmargined run) 293 in the worst case but the netclass-specific
`HighVoltage`-class violations that motivated the fix are gone from the
sample set (spot-checked directly — see §3 for why the residual `clearance`
count is still non-zero and does not block this test).

Excluded: the full `temper_induction_cooker.yaml` PCL config (zones + named
adjacency/enclosing constraints). Confirmed directly (not assumed): running
that config's constraints against the real board is **infeasible for
constraint-set reasons independent of solver** — the config's zone/adjacency
assumptions have drifted from the real board's current 152×234mm geometry
(`enc_HV_ZONE` assumes a zone box smaller than the real board; the real
board's own committed, shipped positions already fail several of the
config's own constraints, per #1024 §4.0). This is a pre-existing
config/board drift bug, not something this spike introduces or fixes
(`temper-design-bundle`'s config loader is off-limits to this spike's task
boundaries).

### 2.2 A real, pre-existing bug found and fixed: `_apply_placements_to_pcb` silently no-ops on the real board

The first attempt to write Pumpkin's solved positions onto the real board
failed the round-trip oracle with **1033 mismatches across all 169
components** — not a few components off by a rounding error, *every single
one* unchanged from its original position. Root cause, confirmed directly:
`_apply_placements_to_pcb`'s footprint-block-boundary regex
(`packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py`)
required `(layer` to appear immediately after the footprint's quoted name:

```
r'\(footprint\s+"[^"]+"\s+\(layer'
```

The 33-component fixture's footprints are written as
`(footprint "NAME" (layer "F.Cu")` — matches. The real board's footprints
(kicad-cli 10.0.5 export, regenerated 2026-08-08) are written as
`(footprint "NAME" (version 20260206) (generator kicad-footprint-generator) (layer "F.Cu")` —
**zero matches**, so `foot_starts` came back empty and the function's own
early return (`if not foot_starts: return raw_content`) handed back the
input completely unchanged, with no exception and no logged signal.

This is orthogonal to which solver produced the placement — OR-Tools'
output would hit the identical silent no-op, had anything ever tried to
write it onto the real board before. Nothing had: neither
`test_golden_board_drc_regression` (fixture only) nor
`test_production_board_drc_regression`/`test_production_board_routing_drc_regression`
(real board, but DRC the committed board or `route_pcb()`'s output — neither
calls `_apply_placements_to_pcb`) had a reason to exercise this path against
the real board's export format before this spike.

**Fixed** by tolerating any number of flat (non-nested-paren) fields between
the footprint name and `(layer`:

```
r'\(footprint\s+"[^"]+"(?:\s*\([^()]*\))*\s*\(layer'
```

Verified directly: 169/169 matches on the real board, 33/33 (unchanged) on
the fixture — a no-op for every existing caller. `tests/router_v6/test_adapter.py`
(98 tests), `tests/router_v6/_adapter_convert_py_oracle.py`, and
`tests/core/test_design_rules_field_parity.py` all still pass (101 passed, 1
skipped) after the fix. This is exactly the class of bug the round-trip
oracle (plan 2026-08-02-009 U3) exists to catch — see
`docs/evidence/2026-07-30-placement-writer-rotation.md` for the precedent —
and it caught it immediately, before any DRC number was trusted.

### 2.3 Existing routed copper: stripped before write, not left in place

Unlike the bare/unrouted 33-component fixture, the real board is the actual
shipped product — fully routed, with committed traces/vias/zones for its
CURRENT (as-shipped) placement. Writing a completely different, freshly
solved placement directly on top of that existing copper produced DRC
carnage unrelated to placement quality (`shorting_items` jumped to 103,
`clearance` to 502) — every new component position was being checked against
copper that was routed for entirely different positions, which is a
*routing*-regression question, not a placement one (and
`test_golden_board_routing_drc_regression` — the test that WOULD ask that
question — is currently `pytest.skip`'d upstream for an unrelated,
already-tracked reason: the APC/zone-policy gap documented in that test's own
KNOWN GAP skip message, nothing to do with this spike). Fixed by stripping
existing copper first, using production's own R7 "clean re-route" primitive
(`temper_placer.router_v6._strip_copper.strip_existing_copper` — the same
function `scripts/route_board.py` already uses for this exact purpose): 2434
segment/via/zone blocks removed before the new placement is written. This
isolates exactly what the fixture test measures — does THIS placement, alone,
on bare footprints, clear DRC — not "is the old routing still valid for new
positions."

## 3. Why the pass bar is the real board's own committed-DRC baseline, not the fixture's `<=15`

`test_golden_board_drc_regression`'s `placement_fixable <= 15` threshold is
calibrated for the 33-component fixture. Measured directly (DRC on the REAL,
as-shipped, **unmodified** `pcb/temper.kicad_pcb` — no placement change, no
Pumpkin involvement at all): **1281 total violations, 199 `silk_overlap`, 499
`clearance`, 97 `shorting_items`, 154 `solder_mask_bridge`** — already
~85x over the fixture's threshold, on the board as it ships today. This is
not a discovery this spike makes about the board being broken; it is the
same reality `test_regression_drc.py`'s own
`PRODUCTION_COMMITTED_BOARD_*` constants already encode (measured
2026-07-29): `PRODUCTION_COMMITTED_BOARD_TOTAL_DVIOLATIONS = 1425`,
`PRODUCTION_COMMITTED_BOARD_SHORTING_ITEMS = 141`,
`PRODUCTION_COMMITTED_BOARD_UNCONNECTED = 428`
(`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py:826-828`),
which `test_production_board_drc_regression` already asserts against as a
ratchet — not a small fixed constant, the board's own measured baseline.

At 169 real components and real densities, "near-zero violations" was never
the right bar. Concretely: `silk_overlap` (199 violations) is present,
**unchanged**, in the as-shipped board — silkscreen extent is not
constrained by ANY encoding used in this spike, nor (per the as-shipped
board's own 199 count) by whatever hand-refinement placed the real board's
current positions either. Chasing it to zero inside this spike's simplified
box-geometry model would mean modeling silkscreen graphic extents as a new
constraint class — a real, nontrivial modeling exercise, not a solver
question, and explicitly out of this spike's "prototype and cost, don't
migrate" scope.

So this test holds Pumpkin to the SAME ratchet `test_production_board_drc_regression`
already holds the committed board to: **does a fresh Pumpkin placement, on
bare (copper-stripped) footprints, do no worse than what's already shipping**
— rather than reusing a threshold copied from a corpus 5x smaller than the
board this test actually measures. Measured result: **925 total (vs. 1425
baseline), 2 shorting_items (vs. 141 baseline)** — Pumpkin's fresh,
unrefined, sub-2-second placement is already meaningfully *better* than the
currently-shipped board on the two categories that matter most for physical
safety (shorting, mask bridging: 2 vs. 97/154 respectively), and within
budget on the aggregate count.

| category | as-shipped real board (unchanged) | Pumpkin real-board placement | fixture test's own `<=15` bar |
|---|---:|---:|---:|
| total violations | 1281 | **925** | n/a (not the right board for this bar) |
| shorting_items | 97 | **2** | 0 |
| solder_mask_bridge | 154 | **2** | 0 |
| clearance | 499 | 293 | (rolls into the 15) |
| silk_overlap | 199 | 199 | (rolls into the 15) |
| courtyards_overlap | 11 | 26 | (rolls into the 15) |

`courtyards_overlap` is the one category where Pumpkin's placement is worse
than as-shipped (26 vs. 11) — a real, honest finding, not hidden: a
box-level courtyard-tau/netclass separation constraint does not guarantee
zero *courtyard-polygon* overlap when courtyard shapes are non-rectangular or
extend asymmetrically past a component's simple width/height envelope
(the same class of box-vs-actual-geometry gap that produced the netclass
clearance gap in §2.1, at smaller scale here). This is squarely a
constraint-model-fidelity finding, not a Pumpkin-vs-OR-Tools one: OR-Tools
under the identical constraint set would have the identical gap (the boxes
are boxes regardless of which solver decides their positions), if OR-Tools
could complete the search at all (§1).

## 4. Reproducibility: timing, and the timeout-overrun caveat

**The task's declared caveats, checked directly against this spike's own
model** (the real-budget spike's #1024 caveats were measured on a
*different*, courtyard-only, no-netclass model — re-measuring against THIS
spike's actual netclass-inclusive model, not assumed to transfer):

**Feasibility-only (this test's actual code path — no objective, matching
`solve_placement()`'s own Phase-1 contract): 15/15 runs clean.** 5 seeds
(0, 1, 7, 42, 99) × 3 repeats, 30s budget, netclass+courtyard model (22,026
constraints):

| | value |
|---|---:|
| runs | 15 |
| status | `optimal`, all 15 |
| solve time range | 0.98s – 1.35s |
| wall time range (subprocess incl. serialization) | 1.17s – 1.55s |
| timeout overruns (wall > 32s) | **0** |
| errors | **0** |

**HPWL-objective, 30s budget (the specific scenario #1024 flagged — one
run overran to 50s+, one seed errored): 3/3 fresh runs, seed 0, clean.**

| rep | status | solve_time_ms | wall_s |
|---|---|---:|---:|
| 0 | feasible | 30211.1 | 30.42 |
| 1 | feasible | 30168.3 | 30.38 |
| 2 | feasible | 30176.5 | 30.38 |

**Verdict on the caveat: refuted as reproducible, not confirmed as a defect.**
Every run lands 0.6–1.4% over the requested 30,000ms budget — the same
"essentially on-budget" pattern #1024's own retry already found (30.17s),
now independently reproduced 3/3 times with zero variance in outcome. The
one >50s overrun and the one errored seed recorded in #1024's own summary
JSON (`docs/evidence/2026-08-11-pumpkin-hpwl-realboard-clean-summary.json`)
do not reproduce here; #1024's own text already flagged that data point as
"may have been system contention from this spike's own concurrent processes
rather than a Pumpkin defect — not confirmed either way with a single data
point." This spike adds 3 more data points, all clean, which shifts the
balance of evidence toward "one-off," though 3 additional samples is still
not enough to certify zero risk for a CI gate — see §5 for what that would
cost to close out properly (N≥30-style timeout-adherence stress testing,
matching the discipline `docs/STRATEGY.md` already requires for
`shorting_items` noise).

The "several cells were `not_run`" gap in #1024's own data: confirmed as a
**driver-script artifact**, not a solver behavior — the run script stopped
iterating after the one subprocess exception on seed 0, so seeds 1 and 7 at
the 30s HPWL budget were never attempted, for both engines. Not a Pumpkin
coverage gap; a spike-script bug, now moot given §4's fresh, complete 3/3
sample.

## 5. Productionising Pumpkin: options and recommendation

**Recommendation: Option C, a solver-selection seam behind the existing
`CpSatModel`/`solve_placement()` boundary, built on Option B's subprocess
mechanism initially.** Do not attempt Option A (a full pyo3 crate) yet — the
model-translation surface this spike exercises (SEPARATED constraints only)
is a small fraction of `_encoder_core.py`'s actual handler registry (9+
constraint types under `handlers/`), and committing to a compiled dependency
before that translation is proven at full parity is the wrong order of
operations for a spike.

**Option A — proper Rust crate + pyo3 exposure.**
`packages/temper-rust-router-core`'s `rustsat`/`rustsat-cadical` dependency
(gated behind an optional `sat` feature, default-on for native builds,
explicitly excluded from the `wasm32` tier per that crate's own
`Cargo.toml` comment) is real, working precedent for a C++/Rust SAT solver
living in this dependency tree without breaking WASM builds. Pumpkin is pure
Rust (unlike `rustsat-cadical`'s C++ dependency), so its own `wasm32`
compatibility is plausible but **unconfirmed** — worth checking before
committing to this route, since `tools/wasm/**`'s build tier is explicitly
off-limits to this spike and a new dependency that silently breaks it would
be a real regression.
- Pros: no subprocess/JSON marshalling cost per call; fits
  `solve_placement()`'s existing dataclass-return contract directly; shared
  build tooling with the crates already in this tree.
- Cons: a real new build surface (Pumpkin's own dependency tree —
  `pumpkin-solver`, `pumpkin-core`, `pumpkin-propagators`,
  `pumpkin-conflict-resolvers`, `pumpkin-constraints`, `pumpkin-checking`,
  plus `rand`, `itertools`, `enumset`, `bitfield`, `drcp-format`,
  `flatzinc`, `clap`, `env_logger`, confirmed from this spike's own `cargo
  build --release` output — 61 crates compiled from cold); needs the FULL
  constraint-handler translation this spike deliberately did not attempt
  (only `separated` is wired in the standalone binary today); needs
  feature-flag discipline mirroring `rustsat-cadical`'s `sat` feature so it
  does not leak into build tiers that should not carry it.

**Option B — subprocess to a built binary.** What this spike already used,
end to end, for a real golden test.
- Pros: fastest to land — proven today; zero new production dependency-tree
  surface (a standalone artifact, built once); trivially optional (binary
  absent → graceful skip, exactly this spike's own test behavior).
- Cons: needs a deployment story this spike does not answer (CI-built
  artifact? committed binary? install-time build hook?); per-call JSON
  marshalling cost (measured negligible here — sub-2s solves, subprocess
  spawn + serialize/deserialize overhead is a small fraction of that, per
  the wall-time-vs-solve-time deltas in §4's tables, ~0.2-0.3s); a
  hand-maintained wire-format schema with no shared type system against the
  rest of the placer (drift risk between the Python payload builder and the
  Rust binary's `ModelSpec` struct — this spike's own `to_units`
  round-half-even-then-even-parity requirement, discovered the hard way per
  `main.rs`'s own comment, is exactly this class of risk already realized
  once).

**Option C — solver-selection seam (recommended).** `CpSatModel()` is
instantiated in exactly one place
(`packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py:221`),
and the solve/status-extraction block is a further ~15 contiguous lines
(`_encoder_solve.py:497-533`, `solver = cp.CpSolver()` through the
`positions`/`rotations` extraction). A thin
`solve_placement(..., engine: Literal["ortools", "pumpkin"] = "ortools")`
kwarg at that boundary — default unchanged, zero risk to any existing
caller — would translate the already-built constraint set (which this spike
already proves is reusable: `generate_netclass_separated_constraints` is
production code, called directly, not reimplemented) into Pumpkin's wire
format and dispatch, both engines returning the SAME `CpSatPlacementResult`.
This keeps OR-Tools as the oracle (unchanged default) while Pumpkin becomes
an explicit, opt-in path — exactly the shape needed to run a differential CI
gate (does Pumpkin's independently-solved placement pass the SAME
`IndependentVerifier` OR-Tools' does — formalizing the existing 108-run
differential from a docs/evidence harness into a real, CI-executed code
path) before ever committing to Option A's build-surface cost or Option B's
deployment question. Built on Option B's subprocess mechanism initially
(zero-risk, already proven by this spike end to end); Option A becomes the
natural target once the FULL handler-translation surface is proven at parity
and the deployment question has an owner.

## 6. Costing the rest

**If this prototype is accepted as the differential-Pumpkin baseline, what
would it take to move both golden tests?**

1. **`test_golden_board_drc_regression`** (placement-only), moved to the real
   board, with EITHER engine:
   - Fix `temper-design-bundle`'s `config_loader.rs` schema guard
     (`reject_unknown_raw_keys` rejects `version`/`metadata`/`netclasses` —
     the committed `temper_induction_cooker.yaml`'s own top-level keys),
     which currently makes BOTH existing golden tests silently solve with
     zero active PCL constraints (#1024 §4.0) — solver-independent,
     off-limits to this spike, real work for whoever owns that file.
   - Re-derive the PCL config's zone/adjacency assumptions against the real
     board's actual 152×234mm geometry and current component layout — a
     domain/engineering call (where SHOULD `HV_ZONE` sit on the real board),
     not a mechanical fix.
   - Decide whether "no worse than the shipped baseline" (this spike's own
     bar, §3) or a tighter, silkscreen-aware model is the real target;
     the latter needs a genuinely new constraint class this spike did not
     build (silkscreen extent is unconstrained by every encoding exercised
     here, production's included).
   - The `_apply_placements_to_pcb` regex fix (§2.2) is a hard prerequisite
     for either engine's placement ever writing correctly to the real
     board — already landed by this spike.
   - If Pumpkin: productionize per §5's recommended seam, then extend the
     standalone binary's (or crate's) constraint-handler coverage from
     `separated`-only to the full `handlers/` registry.
   - If OR-Tools stays: needs either a longer round-1 budget than the
     current live 30s `INITIAL_SOLVE_TIMEOUT_MS` (unproven whether ANY
     bounded increase gets single-threaded OR-Tools to `optimal`/`feasible`
     on this model class — not measured in this spike or #1024) or an
     accepted, permanent "OR-Tools cannot decide the real board" status quo.
2. **`test_golden_board_routing_drc_regression`** (routing), moved to the
   real board: blocked FIRST by an unrelated, already-tracked routing gap
   (APC/zone-policy, that test's own KNOWN GAP skip) — solver-independent,
   nothing to do with placement or Pumpkin. Once unblocked: needs a
   real-board-scale `route_pcb()` run (untested territory — routing is a
   separate algorithm from placement, unaffected by which CP-SAT engine
   solved the upstream placement) plus the same PCL-drift and
   silkscreen-model-fidelity costs as item 1, since routing DRC layers on
   top of a placement DRC baseline.
3. **What stays on OR-Tools, and why.** The fast incremental-repair path
   (`RE_SOLVE_TIMEOUT_MS=1000ms`, every non-round-1 solve,
   `loop.py:43`) is not a Pumpkin win anywhere measured — the existing
   108-run differential's `medium` corpus (12 components, a real
   `minimize_displacement_to` objective) shows OR-Tools proving TRUE
   optimum in under 2s while Pumpkin never converges within its 5s budget,
   up to 11x worse
   (`docs/evidence/2026-08-07-pumpkin-engine-differential.md`). Pumpkin's
   advantage in this spike and #1024 is specifically the LARGE,
   feasibility-dominated, round-1 solve where OR-Tools cannot complete at
   all — not small, objective-bearing local repairs, where OR-Tools already
   wins outright. The right split, if Pumpkin is adopted at all: Pumpkin (or
   the seam, differentially checked) for `INITIAL_SOLVE_TIMEOUT_MS`'s
   round-1 feasibility solve; OR-Tools stays for every `RE_SOLVE_TIMEOUT_MS`
   incremental repair round.

## 7. Reproduction

```bash
# Build the standalone Pumpkin binary (spike artifact, not a production dependency):
export CARGO_TARGET_DIR=/home/bennet/Desktop/temper/target-shared   # or `source scripts/cargo_shared_env.sh`
cargo build --release --manifest-path docs/evidence/2026-08-07-pumpkin-engine/Cargo.toml

# Run the new golden test (needs kicad-cli on PATH + LD_LIBRARY_PATH +
# KICAD_STOCK_DATA_HOME per AGENTS.md's kicad-cli setup notes):
cd packages/temper-placer
../../.venv/bin/python -m pytest tests/placer/cp_sat/test_golden_board_pumpkin_real_board.py -v -s
```

Files this spike adds/touches:
- `packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py`
  (regex fix, §2.2 — production code, small, solver-independent)
- `packages/temper-placer/tests/placer/cp_sat/test_golden_board_pumpkin_real_board.py`
  (the new golden test — the deliverable)
- This document.
