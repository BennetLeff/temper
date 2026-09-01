# Porting `astar_core._astar_search` to Rust — measured

**2026-08-18.** The last live pure-Python search kernel in the router is now
Rust. The routed board is byte-identical.

Worktree cut fresh from `origin/main` `9bf6e5df797cf93e0122b742ab87661bf097dd81`;
`pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`, never
modified. Own `.venv` via `make venv-isolate` — the shared checkout's venv was
**8 of 10 crates stale** while other sessions rebuilt into it, so nothing was
measured there. `scripts/check_stale_extensions.py` was run immediately before
every measurement below and reported `fresh=10 stale=0`; on the one occasion it
did not (freshly-written `.rs` files, `.so` from ten minutes earlier) the run
aborted on the gate rather than producing a number.

## Headline

| | baseline (Python) | with the Rust kernel |
|---|---|---|
| routed content sha256 | `6d4e17337bcf2633fb256f3da4d6fe981c91123827eff715a2c8aa870d195981` | **identical** |
| segments / vias / zones | 4553 / 169 / 151 | **identical** |
| completion rate | 0.3238095238095238 | identical |
| wall clock | 226.95 s | 198.01 s, 208.24 s |

Flags: `route_board.route_once(pcb/temper.kicad_pcb, configs/netclass_rules.yaml)`
with every default — no `--pruning`, no `--net-batching`, no `--max-sat-nets`,
no `--nlayer-astar-spike`, existing copper stripped. **cProfile was not
attached** to any of these runs. Load average at the start of each: 4.28 /
4.59 / 6.15 on 24 cores, with other agents' `pytest` and `rustc` running
throughout — which is why the two post-port runs differ by 10 s from each
other and the wall-clock delta is reported as a range, not a figure.

The digest is the result. The wall-clock saving is real but is bounded by
what the search actually costs: **16.68 s of a ~210 s route**, measured below.

## What the search actually does in production

Recorded by wrapping the call site's own module global for one full route
(`scripts/capture_astar_backbone_corpus.py`). The shim is proven
behaviour-neutral by the digest: the instrumented run produced the same
`6d4e1733…` board.

* **271 calls**, 16.68 s total, all from
  `_corridor_backbone.route_edge_astar` — `gnd` via `_ground_plane`, and
  `+3V3` / `vcc` / `+15V` / `V_BUS_SENSE` via `_power_islands`.
* **260 of the 271 return `None`.** 96% of the work is searches that exhaust
  the frontier without reaching the goal. That, not path-finding, is the
  regime this kernel lives in.
* Grids run to **979,400 cells**, median 185,640.
* **Exactly one argument shape occurs**:
  `neighbor_tensor=None, thermal_flat=None, thermal_weight=0.0, net_id=1,
  corridor_mask=<array>`. The tensor branch, the thermal term and the
  `net_id < 0` path are all unreached from production.
* **Every one of the 271 grids contains only `0` and `-1`.** This was checked
  on every call, not assumed. `_ROUTE_NET_ID = 1` is never written into a
  cell, so `is_same_net` is always False and the 0.25 discount never fires:
  the live cost model is exactly `1.0` cardinal, `DIAGONAL_COST_FACTOR *
  sqrt(2)` diagonal.

## Why `astar_kernel_3d` was not the base

`temper_rust_router_core::astar::astar_kernel_3d` is the live 2D primary
search for every net and was left untouched. It is also not a faithful base
for this port, in three independent ways, each sufficient to move an argmin:

1. it keeps a **closed set** and skips re-expansion; `_astar_search` has none,
   so nodes re-expand and stale heap entries are fully re-processed;
2. it computes in **f32** (octile heuristic evaluated in f64, then cast);
3. it hardcodes `std::f32::consts::SQRT_2` and has no counterpart to
   `astar_core.DIAGONAL_COST_FACTOR`, which the Python multiplies in on every
   diagonal expansion.

The port is therefore a separate kernel,
`temper_rust_router_core::astar_search2d`, mirroring the Python statement for
statement in f64.

## The differential

`packages/temper-placer/tests/router_v6/test_astar_search2d_rust_differential.py`
replays all 271 recorded production searches through the pinned oracle
(`_astar_core_py_oracle.py`, verbatim extraction from `9bf6e5df7`) and the
Rust, and requires the identical cell sequence — including on the 260 that
find nothing.

```
271 real corridor-backbone searches
  live Python  16.98 s
  oracle       16.95 s
  Rust          0.73 s     (23.3x)
  mismatches       0       (against each other AND against the in-run record)
```

A synthetic randomized differential (400 grids, all four argument shapes
including thermal, validity tensor, corridor mask, same-net and foreign-net
cells) also reports 0 mismatches.

The strongest single case is `test_diagonal_cost_factor_is_read_per_call`:
with `DIAGONAL_COST_FACTOR = 0.5` a diagonal step costs less than a cardinal
one, so the octile heuristic stops being admissible and this closed-set-free
search's re-expansion order — not optimality — decides the path. The two
engines still agree exactly. That test **failed on first run**, and the
failure was the test's, not the kernel's: the oracle is a standalone verbatim
copy and carries its own `DIAGONAL_COST_FACTOR`, so setting only
`astar_core`'s compared two different cost models.

## Float spelling

Two divergences measured in this repo the same day —
`d ** 2 != d * d` at `d = 98.07985406973864`, and
`math.sqrt(s) != s ** 0.5` at `s = 55489.646545994874` — are pinned as
counterexample tests. Neither is reachable from inside this search: it spells
its only root `math.sqrt(2.0)` and never squares with `**`. The Rust uses
`std::f64::consts::SQRT_2`, the correctly-rounded double IEEE-754 requires
`sqrt` to return, which is bit-identical to `math.sqrt(2.0)`
(`0x1.6a09e667f3bcdp+0`).

## Tie-breaking, argued rather than sampled

Python pushes `(priority, (x, y))` onto `heapq`, so ties break
lexicographically on the integer cell tuple. The Rust orders on the same
triple. Two heap entries can compare equal only when priority *and* cell are
equal — i.e. when the entries are indistinguishable — so the pop **sequence**
is fixed by the comparison alone and does not depend on either
implementation's internal sift order. This is why the parity claim does not
rest on the corpus happening to avoid ties.

## What else moved

* The pure-Python `_astar_search` and `_heuristic` are **deleted** from
  `astar_core.py` (368 → 225 lines). The standing rule is one home, not two in
  agreement.
* `astar_core_rust._astar_search_rust`'s ImportError fallback used to degrade
  to that function. It now **raises**: there is no second implementation left,
  and returning `None` would read to callers as "no route exists" rather than
  "the extension is missing".
* Seven test modules were re-pointed. Suites that assert *live* behaviour
  (dijkstra oracle PBT, inductive ladder, metamorphic PBT, bit tensor,
  corridor erosion) now exercise the Rust. Suites for which the Python *was*
  the reference point at the pinned oracle: `test_astar_kernel_rust_differential`
  (where `_astar_search` has always been `astar_kernel_3d`'s oracle) and
  `test_astar_runtime_monitor` (the monitor is a per-Python-pop callback the
  Rust cannot serve — that callback is the cost the port removed). The
  monitor's `_heuristic` monkeypatch moved with the function, per
  `docs/solutions/best-practices/moved-function-relocates-monkeypatch-surface-2026-07-29.md`.
* `check_rust_coverage_illusions.py`'s incident note for `astar_core` said the
  Python was "live"; that is now false and the note says so. The ledger row
  itself stands — the module still calls no Rust, and the namesake still does
  not implement it.

## Independent pre-existing failure, flagged not fixed

`test_adapter_convert_marshal_rust_differential.py::test_build_route_payload_zero_length_path`
fails in this worktree. It is unrelated: the whole Rust diff outside the new
files is four lines of module registration. The cause is `968d1a33d`
("enforce the 0.254mm annular floor in `Via::new`") — a via with
`diameter=0.6, drill=0.3` has a 0.15 mm ring, below the 0.254 mm floor, so
`Via::new` raises it; the Python-side reference in that test still expects
0.6. It fails on `main` too, for anyone with freshly-built extensions, and is
invisible to anyone whose `temper_rust_router` predates that commit. Not
touched here: it is a real safety enforcement meeting a stale test
expectation, and deciding which gives way is not this change's call.

## 2026-09-01 refresh against current `main`

The production board changed after the original capture, so the corpus was
recaptured rather than re-labelled. A fresh, uninstrumented `route_once()`
produced routed-content SHA-256
`7ca01328a795ef43376ca28f601e0ff04b4ab2a73c22b7ede45fd75c247aaf85`
with 4,714 segments, 176 vias, and 170 zones. The instrumented capture then
reproduced that digest byte-for-byte.

The current board produces 283 live corridor-backbone searches: 272 return
`None` and 11 find a path. Production still uses exactly the original
argument shape (`net_id=1`, corridor mask present, no neighbor tensor, no
thermal field), and every captured occupancy grid still contains only `0`
and `-1`. The Rust implementation and pinned pre-migration Python oracle are
held to bit-exact agreement over this refreshed corpus.
