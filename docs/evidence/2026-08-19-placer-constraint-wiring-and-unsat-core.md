<!-- provenance: branch=fix/wire-placer-constraints, base=origin/main f5488973e.
     Board measured: pcb/temper.kicad_pcb sha256
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
     (verified unchanged before and after; never opened for writing -- every
     solve below is an in-memory measurement, nothing was written back).
     Environment: this worktree's OWN .venv (make venv-isolate / uv sync
     --all-packages, env -u CONDA_PREFIX). scripts/check_stale_extensions.py
     run immediately before the first measurement: PASSED, 10/10 fresh, 0 stale.
     ortools 9.15.6755. Machine SHARED with other agents throughout: load
     average 4.7-11.2 across the run, recorded per measurement below. No
     cProfile was attached to any solve. -->
---
module: placer
tags: [cp-sat, creepage, pd3, iec60335, isolation-barrier, unsat-core, wiring]
problem_type: diagnosis
---

# 2026-08-19: the placer was never asked to produce a compliant board — wiring it, and the UNSAT core that results

**Authority: analysis and measurement only.** `pcb/temper.kicad_pcb` was not
modified. Placements produced below are measurements, not candidates.

## 0. Headline

Three HARD safety-constraint families were **unreachable** from the default
`--loop` placement path, and the one family that *was* live enforced an
explicitly-unsourced 6.0 mm figure against a DRU that grades the same pairs at
12.6 mm. All three are now reachable, the live family now decides against the
DRU, and the placer was run.

The result is **both** answers, and the distinction matters:

| What was asked | Verdict | Time |
|---|---|---|
| Inter-component separation at the DRU-resolved figures (12.6 mm HV↔SELV) | **`optimal`** | 37.6 s |
| The same, plus the isolation barrier at `MIN_BARRIER_WIDTH_MM` = 12.6 mm | **`infeasible`** | 26 s |

The UNSAT is **not** a crowding result. Five components are *each individually*
contradictory with the 12.6 mm requirement, with zero interaction between them:
their own HV and SELV pads are closer together than 12.6 mm, and rotating or
relocating a rigid part cannot change the distance between its own pads.

## 1. What was unreachable, and why

`solve_placement` has three opt-in HARD constraint kwargs. Measured on
`origin/main` f5488973e:

| Family | Only production caller | Reachable from `--loop`? |
|---|---|---|
| `tank_creepage` | `cli/__init__.py:676`, inside the `--no-loop` branch | **No** |
| `isolation_barrier` | `cli/repair_commands.py` (`repair-unplaced`) | **No** |
| `heatsink_colocation` | *nothing in `src/`* | **No** |

`--loop` is the default (`cli/__init__.py:229-231`) and is what
`scripts/run_clean_flow.sh:44` and `scripts/run_physics_flow.sh:26` both run.

**They were unreachable, not merely unset.** `_loop_core.py::_call_solver`'s
`solver_kwargs` dict had no key for any of them, and `PlaceRouteLoop.run()` had
no parameter to carry one. No flag, config key, env var or YAML entry could
enable them.

### Why it happened — read from the history, not assumed

This was not an oversight about the loop; it was an oversight about *which
branch is the production one*.

* **`heatsink_colocation`** (#1082, `c43c50927`) was added with the commit
  message *"Puts the constraint on the production entry point at exact parity
  with `isolation_barrier`: an opt-in kwarg"*. Parity with `isolation_barrier`
  was achieved exactly — including its invisibility to `--loop`. The bar was
  "matches the sibling", and the sibling was already dark.
* **`tank_creepage`** (#1089, `ad8498f7d`) was introduced *"exposed opt-in via
  `solve_placement(tank_creepage=...)` at the same point in the sequence
  `isolation_barrier`/`heatsink_colocation` use"* — the same parity argument,
  one generation later.
* **`tank_creepage` was then deliberately turned on for production** in #1109
  (`b5e94b6f1`), whose commit message states: *"cli/__init__.py: the `optimize`
  production solve now passes `tank_creepage=...`. The constraint has existed
  since #1089 but was opt-in and unused, so no shipping solve held the tank node
  off the other HV nets."* That change is real and correct — it just landed in
  the `--no-loop` branch of `optimize`, and `--loop` is the default. The intent
  ("the production solve") and the effect ("the branch nothing runs") diverged
  silently, because both branches live in the same function under the same
  command name.

So the mechanism is this repo's own recurring one: **the live path is not where
it looks.** Each family was measured for feasibility, documented, tested, and
attached to a call site that reads like production. Nothing ever asserted that a
`--loop` round carries them, so nothing failed when it did not.

The audit-side kwargs `validator_input` and `body_collision_input` were wired
through the loop correctly (#617/#702), and their mechanism — instance state set
by `run()`, forwarded by `_call_solver` — is exactly what the three constraint
families needed and did not have. That asymmetry is the whole defect.

## 2. The changes

1. **`_loop_core.py`** — `run()` gains `tank_creepage` / `isolation_barrier` /
   `heatsink_colocation`; `_call_solver` forwards them. Per-round solver
   arguments must travel as instance state because the Rust loop
   (`cpsat_loop.rs:236`) calls `_call_solver` back with a fixed kwarg set.
   `heatsink_colocation` is tested `is not None` rather than for truthiness —
   rotation index `0` is a legitimate request and is falsy.
2. **`cli/__init__.py`** — the `--loop` branch now passes `tank_creepage` at
   exact parity with `--no-loop`, completing what #1109 intended.
   `isolation_barrier` and `heatsink_colocation` are left off by default: both
   need a value chosen by a human (corridor orientation/width; a rotation
   index), and §4 shows the barrier is currently infeasible, which is a finding
   to act on rather than a default to ship.
3. **`netclass_constraints.py`** — `dru_resolved_pairs=True` (passed by
   `_encoder_core.encode_constraints`) raises every cross-class pair figure onto
   `max(pair_clearance, pair_creepage)` from `pair_clearance.generated.yaml` /
   `pair_creepage.generated.yaml`, the projections of `pcb/temper.kicad_dru`
   that `kicad-cli pcb drc` actually grades by. See §3.
4. **`_encoder_solve.py`** — the REQ-SAFE-01 audit's coverage filter. See §5.

## 3. The netclass family: 6.0 mm → the DRU figures

The only separation family live on every production solve took its figures from
`netclass_rules.yaml`'s `class_pairs`, whose own `because` strings read
*"UNSOURCED legacy 6.0mm (debunked 'Table 16 working isolation at 400V'
citation; 6.0mm is in no recovered table)"*. The DRU grades the same HV↔SELV
pairs at **12.6 mm**.

Measured on the real board (168 components, load average 7.2):

| `min_distance_mm` | before | after |
|---|---:|---:|
| 0.15 | 84 | 0 |
| 0.20 | 0 | 84 |
| 0.25 | 38 | 38 |
| 0.50 | 1995 | 1995 |
| 2.00 | 393 | 352 |
| 6.00 | 6439 | 503 |
| 10.00 | 0 | 41 |
| **12.60** | **0** | **5936** |
| total | 8949 | 8949 |

**The raise is monotone — proven per pair, not asserted.** The constraint *set*
is identical (same 8,949 pairs); 6,061 pairs raised, **0 lowered**.

This is a `max()`, not a substitution, and that is load-bearing: for a few
same-domain pairs the DRU is deliberately *looser* than the legacy table
(`ACMains|HighVoltage` resolves to 3.0 mm clearance with no creepage rule at
all, against `class_pairs`' 6.0 mm). `netclass_rules.yaml`'s own comment records
that asymmetry on purpose. Substituting wholesale would have **weakened** the
placement model on those pairs, which is not something a re-sourcing change is
entitled to do. The per-class fallback `max(class_a.clearance, class_b.clearance)`
is folded into the same max for the same reason.

**The pinned oracle was not re-pinned.** `generate_netclass_separated_constraints`
is covered by a Rust-vs-Python differential against
`tests/pcl/_netclass_constraints_py_oracle.py`, a verbatim pre-port snapshot. The
DRU raise is therefore an **opt-in parameter defaulting to False**, so that
function's default behaviour stays byte-identical to the oracle and the
differential keeps asserting exactly what it was written to assert. The
production encoder passes `True`; `TestDruResolvedPairs` pins that path
separately. All 30 tests in both files pass.

## 4. The placer's verdict, and the UNSAT core

### 4a. Inter-component only: `optimal`

`solve_placement` on the real board, DRU-resolved netclass figures + tank
creepage at 10.0 mm, 600 s budget, seed 42, no cProfile, load average 4.7:

```
STATUS = optimal   solve_time 37594 ms (wall 37.6 s)   168/168 placed
```

**Scrutinised, because SAT was the surprising branch:**

* **Binding, not trivial.** 91 of the 5,936 constraints at 12.6 mm sit within
  0.5 mm of their margin. A family with no tight members would not be shaping
  the solution; this one is.
* **A real reshuffle.** All 168 components move; median displacement **117.5 mm**
  on a 164×234 mm board, largest 263.8 mm. This is a full re-place, not the
  input board handed back. (Consistent with `2026-07-30-copper-aware-domain-resolve.md`
  §3.2, which found 167/168 moved at the 8.0/10.0 mm margins.)
* An independent recomputation of Chebyshev box gaps from the solved coordinates
  found no violation. Four pairs read 0.0050 mm short across four *different*
  margins — a uniform, sub-quantum artifact of recomputing in float against a
  model that works in integer units (`units_per_mm = 100`, rounded to nearest
  **even** unit → 0.02 mm quantum). Not violations.

**Cost of the raise: +13%, not minutes.** The same solve run against pristine
`origin/main` f5488973e (i.e. the legacy 6.0 mm figures), same board, same seed,
same 600 s budget, load average 5.1, via `PYTHONPATH` at the base worktree:

| netclass figures | verdict | solve time |
|---|---|---:|
| 6.0 mm (legacy, `origin/main`) | `optimal` | 33 243 ms |
| 12.6 mm (DRU-resolved) | `optimal` | 37 594 ms |

So the raise did **not** change the verdict — it changed what the verdict
*means*: the same `optimal` now certifies 12.6 mm inter-component separation
instead of 6.0 mm. This also retires the cost concern in
`2026-08-17-placer-creepage-constraint-spike.md` §6, which extrapolated from the
8.0→10.0 mm trend that 12.6 mm would "plausibly take several minutes". Measured,
it costs 4.4 s.

**Why this is SAT despite §4b:** the netclass family is *inter-component* only.
The generator skips `a == b` by construction, so no `SeparatedConstraint` can
express a requirement between two pads of the **same** part. The five
non-compliant parts fail on exactly that — their own HV and SELV pads — and are
invisible to this family. A compliant-looking `optimal` here is therefore **not**
a claim that the board is compliant.

### 4b. With the isolation barrier: `infeasible`, with a minimal core

The barrier is the one wired family that *can* see intra-footprint straddle. Run
at `MIN_BARRIER_WIDTH_MM` = 12.6 mm (not the module default 13.1 mm, which adds
0.5 mm of integer-rounding headroom):

```
STATUS = infeasible   (26 s)
```

`solver.SufficientAssumptionsForInfeasibility()` returned **empty** — the
infeasibility does not depend on the assumption literals, because each isolator's
rotation pin is a plain `Add`. So the core was extracted by ablation, using the
module's own `relax_isolator_straddle` exemption:

| enforced isolator (all others relaxed) | verdict |
|---|---|
| **C6** | **infeasible** |
| **K1** | **infeasible** |
| K2 | optimal |
| K3 | optimal |
| PS1 | optimal |
| **T1** | **infeasible** |
| **T2** | **infeasible** |
| **U6** | **infeasible** |
| relax exactly {C6, K1, T1, T2, U6} | **optimal** (54.1 s) |

**The core is `{isolator_straddle_X : X ∈ {C6, K1, T1, T2, U6}}` together with
the 12.6 mm requirement, as five independent singleton cores.** Each is
sufficient on its own; relaxing exactly those five restores feasibility, so they
are also jointly necessary. No pair of components interacts. This is not "the
board is too crowded" — it is "five packages cannot span the barrier".

### 4c. The geometry behind the core — rotation-invariant, therefore irreducible

Rotating a footprint rotates every pad *and* every pad position together, so
pad-to-pad distances inside one part are invariant under placement. Measured with
`core.pad_geometry.pad_pair_distance` (exact Minkowski-sum copper-to-copper — the
same function `check_isolation_keepout.py` uses; no polygonisation error):

| ref | footprint | binding HV↔SELV pad pair | **min** mm | short by | max mm |
|---|---|---|---:|---:|---:|
| C6 | `C_Disc_D12.5mm_W5.0mm_P10.00mm` | 1 `PWR_RTN` ↔ 2 `gnd` | **8.0000** | 4.6000 | 8.0000 |
| K1 | `Relay_SPST_Omron-G4A-E` | 13 `power_in.ntc-no` ↔ A1 `…coil1` | **8.0000** | 4.6000 | 8.5494 |
| U6 | `SOIC16W_Isolated` | 9 `hb-gnd` ↔ 8 `+3V3` | **8.1000** | 4.5000 | 11.7145 |
| T1 | `CST3015` | 1 `tank-out` ↔ 4 `gnd` | **9.1000** | 3.5000 | 12.4933 |
| T2 | `CST3015` | 1 `hb-gnd` ↔ 4 `gnd` | **9.1000** | 3.5000 | 12.4933 |
| K2 | `Relay_SPDT_Schrack-RT314012` | 4 ↔ 5 | 12.7600 | — | 23.8075 |
| K3 | `Relay_SPDT_Schrack-RT314012` | 4 ↔ 5 | 12.7600 | — | 23.8075 |
| PS1 | `Converter_ACDC_MeanWell_IRM-10-xx` | 2 ↔ 3 | 35.5000 | — | 36.6387 |

**Correction to a figure in circulation.** The values 11.7145 mm (U6) and
12.4933 mm (T1/T2) are reproduced exactly above — but they are the **maximum**
HV↔SELV pad-pair distance, not the package's capability. Compliance requires
*every* HV↔SELV pad pair to clear 12.6 mm, so the **minimum** binds. The real
shortfalls are 4.5 mm (U6) and 3.5 mm (T1/T2), not 0.89 mm and 0.11 mm — an
order of magnitude worse. C6's 8.0000 mm (from its 10.00 mm lead pitch) is
correct as circulated. **K1 is a fifth member that was not on the list**, at
8.0000 mm.

### 4d. The board is sized to PD2, exactly

Corridor-width sweep, all 8 isolators enforced:

| corridor width | verdict |
|---|---|
| 13.1 mm (`MIN_BARRIER_WIDTH_MM` + 0.5) | infeasible |
| 12.76 mm | infeasible |
| **12.60 mm (PD3, enforced)** | **infeasible** |
| 9.10 mm | infeasible |
| 8.10 mm | infeasible |
| **8.00 mm (PD2)** | **`optimal`** (82.2 s) |

The feasibility cliff sits at exactly **8.0 mm** — the PD2 reinforced figure. The
committed footprint set was selected against PD2 and is jointly feasible there
with nothing relaxed. The 2026-08-15 PD2→PD3 decision moved the bar to 12.6 mm
and the footprint set was never revisited.

**So the honest statement of what must change is a bill of materials question,
not a placement question.** Five parts must be replaced with wider-creepage
packages (or the nets re-partitioned so those parts stop bridging domains). No
solver can help until then, and `MIN_BARRIER_WIDTH_MM` must not move to
accommodate them — PD3 governs the as-built, forced-air-vented, compartment-less
board.

## 5. The `domain_clearance_` filter is correct; the emptiness is upstream

`_encoder_solve.py`'s REQ-SAFE-01 post-solve audit filtered `constraint_objects`
to `id.startswith("domain_clearance_")`, which is empty on every production
solve — so the audit could only ever report coverage gaps, never raise.

**The prefix is right and was kept.** This filter attributes *blame*, it does not
restrict what is examined: the validator always runs over the whole placement,
and every violation is bucketed. A pair the filter covers becomes a HARD failure
(raises, on the "box separation implied copper separation" soundness proof); a
pair it does not cover becomes a coverage gap. Widening it wrongly would raise on
pairs the encoder never undertook to enforce. `netclass_autogen_` in particular
must stay out even now that it carries 12.6 mm: it is resolved through a
different classifier (KiCad net class via the DRU) over a different pair set, and
is deliberately far looser on same-domain pairs, so its SAT is not a statement
about the REQ-SAFE-01 margin for any given pair.

**One family was genuinely missing and was added:** `keepaway_unclassified_`.
`generate_unclassified_hv_keepaway_constraints` emits whole-component box
separations at `MAX_IEC_MARGIN_MM` from the same matrix, its docstring states its
soundness contract is *"identical"*, and it already anticipated this — *"so the
R24 post-solve audit (which filters on `domain_clearance_`) can be extended to
them the same way if desired"*. The filter is now the named constant
`REQ_SAFE_01_COVERED_ID_PREFIXES` carrying the full include/exclude argument.

**But this does not make the audit able to raise, and the fix for that is not in
the filter.** Neither included family is generated anywhere in `solve_placement`
— both come only from `repair_commands.py`'s `repair-unplaced`. On `temper
optimize` the covered set is empty because the solve genuinely made no
REQ-SAFE-01 claim, which is the correct classification of that fact. Only a
caller that actually posts those constraints can change it.

## 6. What was deliberately not done

**`generate_domain_clearance_constraints` was not wired into `solve_placement`.**
PR #1321 did that naively and #1353 measured the result: `check_tank_creepage_separation`
at 10.0 mm rejects **15 of 180** component pairs on the committed board, of which
only **2** are real copper shortfalls. `C25`×`RV1` shows a 0.400 mm box gap
against **43.80 mm** of actual copper; `C27`×`U4` 0.400 mm against 41.40 mm.

The mechanism is now clear and is worth stating precisely, because it is a
property of the model rather than a bug: a `SeparatedConstraint` separates whole
component *bounding boxes*, while creepage is measured between two *specific
pads on specific nets*. When the pads that matter sit on the far sides of their
respective packages, the box gap can be two orders of magnitude smaller than the
copper gap. Enforcing the box proxy as HARD at a creepage margin therefore
relocates parts that are already compliant by 40 mm.

That conservatism is sound (it can only over-constrain, never under-constrain),
which is why it is acceptable for the *netclass* family at §3 — those figures are
pair-clearance bars the DRU applies to all copper of both nets. It is **not**
acceptable as a substitute for a pad-level creepage constraint, and the honest
conclusion is that closing the remaining gap needs a pad-pair-level constraint,
not a wider box.

## 7. Reproduce

Three harnesses are committed beside this document. All are read-only with
respect to the board and import only production entry points
(`solve_placement`, `pad_pair_distance`, `generate_netclass_separated_constraints`).
Run from the repo root, in a worktree whose extensions are fresh:

```bash
scripts/check_stale_extensions.py            # must report 10/10 fresh FIRST

# §4c -- the package geometry behind the core (read-only, sub-second)
python docs/evidence/2026-08-19-isolator-package-maxima.py \
       pcb/temper.kicad_pcb elec/domain_manifest.yaml

# §3 -- the monotone-raise proof (no solve; ~2s)
python docs/evidence/2026-08-19-netclass-dru-raise-monotonicity.py \
       pcb/temper.kicad_pcb

# §4b -- the UNSAT core by ablation (9 solves, ~5 min)
python docs/evidence/2026-08-19-barrier-unsat-core-ablation.py
```

§4a's two verdicts are a direct `solve_placement` call on the parsed board
(`tank_creepage={"margin_mm": DEFAULT_TANK_CREEPAGE_MM}`, `timeout_ms=600_000`,
`seed=42`), with `isolation_barrier={"manifest_path": Path("elec/domain_manifest.yaml"),
"corridor_width_mm": MIN_BARRIER_WIDTH_MM, "orientation": "vertical"}` added for
the infeasible one.

## 8. Test status

`packages/temper-placer/tests/placer/cp_sat/` + `tests/pcl/` in full, run
serially with `--timeout=1800` on BOTH this branch and pristine `origin/main`
f5488973e (checked out in a separate detached worktree, same interpreter and
same compiled extensions via `PYTHONPATH`):

| | failed | passed | skipped | wall |
|---|---:|---:|---:|---:|
| `origin/main` f5488973e | **27** | 2 312 | 9 | 34 m 44 s |
| this branch | **27** | 2 318 | 9 | 35 m 11 s |

**The two failure sets are IDENTICAL** — `comm` in both directions is empty, so
there is not one failure on this branch that is not also on `origin/main`, and
none disappeared either. The `+6` passed is exactly the six tests added here,
all green.

The 27 pre-existing failures, by file:

| file | n | note |
|---|---:|---|
| `test_erc_gate.py` | 7 | `IECCreepageGate`/`ErcGate` family — the spike (`2026-08-17-placer-creepage-constraint-spike.md` §2) already recorded these as unregistered dead code |
| `test_physics_gate.py` | 6 | creepage sub-check, hardcoded 6.0mm — same §2 finding |
| `test_tank_creepage.py` | 6 | the set diagnosed in `2026-08-18-tank-creepage-11-reds-diagnosis.md`; none is a live board shortfall |
| `test_regression_drc.py` | 3 | board DRC regression pins |
| `test_body_collision.py` | 1 | allowlist coverage (asserts 6 allowlisted pairs, measures 1) |
| `test_heatsink_colocation.py` | 1 | `test_rejects_the_committed_board_placement` |
| `test_fixed_copper_builder_rust_differential.py` | 1 | real-board bit-identity pin |
| `test_e2e_netclass_ssot.py` | 1 | see below |
| `test_netclass_feedback.py` | 1 | see below |

The last two deserve naming because they *look* like this change's fault and are
not: both assert `"IEC 60335"` appears in a `because` string read straight out of
`netclass_rules.yaml`'s `class_pairs`, which this change does not touch — that
YAML still says "UNSOURCED legacy 6.0mm" on both branches. Fixing them means
re-sourcing that config file, which is a separate attributed decision (this
change re-sources what the *placer* enforces, deliberately without editing the
config's own recorded figures).

**New tests** (6, all passing): `TestDruResolvedPairs` (2) pins the raised
figures and the monotonicity property over the real config's full class
universe; four in `test_loop.py` pin reachability — the defect here was that
these kwargs *could not be reached*, so that deserves a regression pin,
including one asserting `heatsink_colocation=0` is not swallowed by a truthiness
test.

**Gates**, run on both trees: `check_oracle_hashes.py` 172/172 byte-identical to
their pins (**no oracle was re-pinned**), `import_linter_gate.py` 5 kept / 0
broken, `check_router_clearance_floor.py` PASS,
`physics_soundness_register_gate.py` OK, `check_creepage_clearance_drift.py`
exit 3 on **both** trees with output differing only in the repo-root path line.
`ruff check` clean on every file touched.

## 9. Board integrity

`pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified
identical before and after every measurement. No placement was written back; no
`drc_ceiling.json` re-measurement is owed because no board changed.
