<!-- provenance: commit=a3fbaff37afd739b72f2b109847813b30ceb8e88 dirty=true (working tree carries
this task's own fix, measured against it before/after) -- branch
fix/router-net-batching-silent-drop, worktree
../temper-wt-fix-router-net-batching-silent-drop, base origin/fix/board-schematic-resync
(#1134) per the task's own instruction. pcb/temper.kicad_pcb NOT modified: sha256
b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6, identical before and
after every measurement below (matches the committed blob at this commit). Worktree built
with `make venv-isolate`; `scripts/check_stale_extensions.py` reported 10/10 fresh AND all
10 extensions independently verified to `import` cleanly (temper_geometry needed
`cargo clean -p temper-geometry` + a direct `cargo build --features python,pyo3/extension-module`
rebuild -- the first `maturin develop` after `make venv-isolate` silently produced a `.so`
with no `PyInit_temper_geometry` symbol, a live instance of the "PASSED 10/10 fresh for a
module that could not be imported" hazard this task's own brief warned about);
`scripts/check_venv_integrity.py` passed (18/18 entries resolve under this worktree).
`make netlist` run in this worktree. Both full production routes below
(`scripts/route_board.py --net-batching --batch-size 10`) are live, foreground-verified
runs (~410-413s wall each) against the unmodified committed board. -->

# `discharge.k_dis1-no`/`discharge.k_dis2-no` do not vanish from the router -- they get a false "routed successfully" while emitting zero connecting copper, because a name-identity assumption is false for this board's manufacturer-duplicated relay pads

## Verdict up front

1. **PR #1172's own diagnosis of these two nets does not reproduce.** It
   reports `discharge.k_dis1-no`/`discharge.k_dis2-no` as "never appear in
   any router accounting at all under net-batching -- not attempted, not
   declined, not routed." A live, foreground-verified
   `scripts/route_board.py --net-batching --batch-size 10` run against the
   unmodified committed board shows both nets **are** attempted: Stage 3's
   net-batching solves topology for them in batch 0 (`status=sat
   failed=0`), and Stage 4's A* prints `discharge.k_dis1-no routed
   successfully` / `discharge.k_dis2-no routed successfully`.
2. **The real defect is worse than absence: a false positive.** Despite
   the "routed successfully" print, `pad_connectivity_audit` (ground
   truth -- real pad positions parsed directly off the board) shows
   `has_any_copper == False` for both nets pre-fix -- zero segments/vias
   ever join their pads. Both land in the 40-net "honest gap" bucket PR
   #1172 also measured, but PR #1172's own explanation for how they got
   there ("never appear in any accounting") is not what happens; a
   different, more specific mechanism is.
3. **Root cause: `(component_ref, pin_name)` tuple identity is used, in
   two independent places, as a proxy for "physical pad identity" -- and
   it is false for this board.** K2/K3
   (`temper:Relay_SPDT_Schrack-RT314012`, the bus-discharge relays)
   fabricate contact pad "3" (the NO contact) as **two physical solder
   holes, 7.5mm apart, both pad-numbered "3"**, for 16A current sharing
   (confirmed against the footprint's own embedded datasheet comment in
   `pcb/temper.kicad_pcb`, not assumed). `Net.pins` for both nets is
   `[('K2', '3'), ('K2', '3')]` / `[('K3', '3'), ('K3', '3')]` -- two
   IDENTICAL tuples, by construction, because both physical pads share one
   pad number. Two call sites treated that identity as proof of "same
   physical pad, nothing to connect":
   - `_pipeline_grid._net_pad_positions`: `Component.get_pin(name)`
     (`netlist_contracts.rs`) always returns its FIRST name/number match,
     so both occurrences resolved to the SAME coordinate. A* then
     "routes" a zero-length path between two identical points, succeeds
     trivially, and never actually reaches the real second pad.
   - `topology_copper_audit.is_self_referential_net`: `len(set(pins)) ==
     1` was trusted as proof of "same physical pad" for `len(pins) >= 2`
     -- this function's OWN prior docstring cited these exact two nets as
     its "MEASURED real example," proving the false assumption was
     already baked in and asserted as fact by an earlier investigation.
4. **Not a net-batching-specific bug.** Both call sites are in Stage 4,
   which runs identically regardless of `enable_net_batching`; `pcb.nets`
   (and each net's `.pins`) is the same list either way. The defect is
   present with or without `--net-batching`, at any batch size -- PR
   #1172's title question ("possible batching-side bug") is answered no.
5. **No other net on this board hits the same shape.** A systematic scan
   (`scripts/check_net_pin_identity_pad_correspondence.py`, self-contained
   regex parse of the committed board, no compiled extension needed)
   compares every net's `(component_ref, pad_number)` pin-identity view
   against its real, independently-counted physical pad occurrences.
   `discharge.k_dis1-no`/`discharge.k_dis2-no` are the only two matches
   out of 139 raw nets (112 nets with >=2 pin instances). `PWR_RTN`/
   `DC_BUS_RTN` also have K2/K3's duplicated-pad-number pads but are
   `_should_route`-excluded (zone-pour path, a materially different
   mechanism, out of this task's scope); `discharge.k_dis1-nc`/
   `discharge.k_dis2-nc` have the identical duplicate-pad pattern on ONE
   of their pins but additional real distinct pins (R14/R7, R15/R9) keep
   their pin-identity view above the 1-distinct-tuple threshold, so they
   were never silently collapsed the same way -- they fail Stage 4's A*
   honestly (`forced_segment_fail_closed`, PR #1172's mechanism-1
   congestion class), same before and after this fix.

## 1. Reproducing the false "routed successfully"

Live run, `scripts/route_board.py --net-batching --batch-size 10` against
the unmodified committed board (`TEMPER_BATCH_TRACE=1`), pre-fix:

```
[batch-trace] batch=0 nets=10 status=sat ... failed=0
  (batch 0 contains discharge.k_dis1-no, discharge.k_dis2-no -- both solved)
...
      ✓ discharge.k_dis1-no routed successfully
      ✓ discharge.k_dis2-no routed successfully
...
Result: 70/106 nets (66.0%)  segments=3331 vias=26 zones=80  wall=412.8s
Result (pad connectivity, PRIMARY metric): 53/139 nets fully pad-connected  fake-completion=46 honest-gap=40
```

Neither net appears in the printed `Unrouted (36)` list (they did not
fail Stage 4). Neither appears in the `Fake-completion nets (46)` list
(no copper was emitted at all, not partial copper). Direct
`pad_connectivity_audit.audit_pcb_file` against this run's own output
confirms the honest ground truth:

```
discharge.k_dis1-no: pad_count=2, pads_connected=1, fully_connected=False,
  has_any_copper=False, unreached_pads=(K2.3@(137.32,72.21), K2.3@(144.82,72.21))
discharge.k_dis2-no: pad_count=2, pads_connected=1, fully_connected=False,
  has_any_copper=False, unreached_pads=(K3.3@(59.37,25.25), K3.3@(66.87,25.25))
```

Two genuinely distinct physical pads, 7.5mm apart, zero copper joining
them -- despite the "routed successfully" print immediately above.

## 2. Tracing the mechanism

`_net_pad_positions` (`_pipeline_grid.py`) resolves each `net.pins` entry
via `comp.get_pin(pin_name)`. For `discharge.k_dis1-no`'s
`[('K2','3'), ('K2','3')]`, both calls hit `Component.get_pin` (Rust,
`netlist_contracts.rs`):

```rust
fn get_pin<'py>(&self, py: Python<'py>, name_or_number: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    for pin in self.pins.bind(py).try_iter()? {
        let pin = pin?;
        if pin.getattr("name")?.eq(name_or_number)? || pin.getattr("number")?.eq(name_or_number)? {
            return Ok(pin);  // <-- first match, always
        }
    }
    Ok(py.None().into_bound(py))
}
```

`comp.pins` genuinely DOES contain 2 distinct `Pin` objects for K2's pad
"3" (parsed from the board's two separate `(pad "3" ...)` blocks, at
local offsets `(25.34, -7.5)` and `(25.34, 0)`) -- `get_pin` just has no
way to return anything but the first. `_net_pad_positions` therefore
returned `[(137.32, 72.21), (137.32, 72.21)]` (world-transformed, but
identical) instead of the real two distinct world positions. Stage 4's
A* was handed a start point equal to its own end point, "routed" a
zero-length path, and never touched the real second pad.

Independently, `topology_copper_audit.is_self_referential_net` used
`len(set(pins)) == 1` (true for `[('K2','3'), ('K2','3')]`) as proof the
net was "the same physical pad, listed more than once" -- so any
diagnostic run through that module would have certified the resulting
no-copper net as `legitimate_reason="self_referential_pad"`, not flagged
it.

## 3. The fix

- **`_pipeline_grid._net_pad_positions`** (root cause): resolves each
  `(component_ref, pin_name)` occurrence in a net's own pin list to the
  Nth matching physical pin on that component, in encounter order (a new
  `_nth_matching_pin` helper), instead of always taking `get_pin`'s first
  match. `net.pins` and `comp.pins` are built by the same encounter-order
  iteration (`extract_nets_pure` / `parse_engine.rs`), so this
  correspondence is exact, not a heuristic.
- **`topology_copper_audit.is_self_referential_net`**: narrowed to only
  trust `len(pins) == 1` (a genuinely single-pin-instance net -- nothing
  else it could resolve to, regardless of position). `len(pins) >= 2`
  with identical tuples is no longer treated as proof of physical-pad
  identity, since K2/K3 disprove that assumption on this exact board.
- **`pad_connectivity_audit.find_pin_identity_pad_mismatches`** (new):
  the reusable accounting guard -- flags any net whose pin-identity view
  collapses to <=1 distinct tuple while its real, ground-truth pad count
  (independently parsed, no name-based lookup) is > 1. Wired into
  `route_board.py`'s own reporting (`audit_pad_connectivity`) so the
  actual command this task names surfaces the discrepancy unconditionally
  in its normal output, not only via a separate script.
- **`scripts/check_net_pin_identity_pad_correspondence.py`** (new gate,
  registered in `gate_input_registry._CI_SCRIPT_SURVEY` and
  `scripts/manifest.yaml`, wired into `.github/workflows/python-tests.yml`):
  self-contained (regex parse of the raw `.kicad_pcb`, no compiled
  extension needed) standing check of the same invariant, with a
  human-reviewed allowlist (`KNOWN_DUPLICATE_PAD_NUMBER_NETS`) for the two
  known-and-fixed cases -- any other net hitting this shape fails closed.

## 4. Fix verified end-to-end (measured, not inferred)

Second live, foreground-verified `scripts/route_board.py --net-batching
--batch-size 10` run, identical command, same unmodified committed board
(sha256 unchanged throughout), with the fix applied:

```
Result: 70/106 nets (66.0%)  segments=3337 vias=26 zones=80  wall=410.0s
Result (pad connectivity, PRIMARY metric): 54/139 nets fully pad-connected  fake-completion=47 honest-gap=38
```

| metric | pre-fix | post-fix | delta |
|---|---:|---:|---:|
| fully pad-connected | 53/139 | 54/139 | +1 |
| fake-completion | 46/139 | 47/139 | +1 |
| honest-gap (no copper at all) | 40/139 | 38/139 | -2 |
| segments | 3331 | 3337 | +6 |

Per-net, directly re-audited against this second run's own output:

```
discharge.k_dis1-no: pad_count=2, pads_connected=2, fully_connected=True,
  has_any_copper=True, unreached_pads=()
  -- FULLY FIXED: real copper now joins both real physical pads.

discharge.k_dis2-no: pad_count=2, pads_connected=1, fully_connected=False,
  has_any_copper=True, unreached_pads=(K3.3@..., K3.3@...)
  -- has_any_copper flipped False->True (Stage 4 now genuinely attempts
     the real 2-terminal net instead of a degenerate 1-point one), but the
     attempt does not fully connect. This is no longer the silent/false
     defect this task exists to fix: is_fake_completion() correctly
     classifies it (has_any_copper AND NOT fully_connected), it is listed
     by name in the run's own "Fake-completion nets" output, and it is
     the SAME already-well-instrumented b39b382d-shape defect class this
     codebase already has robust detection for -- honest, visible,
     accounted for. Whether it can be made to fully route is a Stage 4
     A*/geometry question, explicitly out of this task's scope ("whether
     these two nets can actually be routed is not your problem").
```

Both nets left the 40-net "honest gap, no explanation" bucket. Neither
net's pads were joined by copper that does not actually connect them --
`pcb/temper.kicad_pcb` was never modified, and no forced/fabricated
segment was introduced anywhere in this investigation.

## 5. The accounting guard fires (task requirement: prove it bites)

Unit-level: `packages/temper-placer/tests/router_v6/test_pad_connectivity_audit.py::test_guard_fires_for_the_real_discharge_relay_shape`
constructs the exact losing condition (duplicate `(component_ref,
pin_name)` tuples, real `pad_count=2`) and asserts
`find_pin_identity_pad_mismatches` returns both net names.
`test_guard_against_the_real_board_finds_exactly_the_two_known_nets` runs
the same check against the real, committed board end-to-end and asserts
the result is exactly `['discharge.k_dis1-no', 'discharge.k_dis2-no']`.

`packages/temper-placer/tests/router_v6/test_pipeline_grid_net_pad_positions.py::test_net_pad_positions_resolves_duplicate_pad_number_to_distinct_physical_pads`
proves the root-cause fix directly: reverting `_pipeline_grid.py` to its
pre-fix content (verified by temporarily restoring the committed version
and re-running this exact test) makes this test FAIL with `(25.34, -7.5)
!= (25.34, -7.5)` -- both occurrences collapsing to the identical
coordinate, the precise defect this task fixes.

Gate-level (self-contained, no compiled extension):

```
$ python3 scripts/check_net_pin_identity_pad_correspondence.py
Board: pcb/temper.kicad_pcb
Nets checked: 139
Known, reviewed duplicate-pad-number nets (2, see KNOWN_DUPLICATE_PAD_NUMBER_NETS): discharge.k_dis1-no, discharge.k_dis2-no

PASSED -- 0 unexpected pin-identity/pad-count mismatches across 139 net(s) checked (2 pre-approved, reviewed exception(s)).

$ python3 -c "from check_net_pin_identity_pad_correspondence import run; from pathlib import Path; print(run(Path('pcb/temper.kicad_pcb'), allowlist=frozenset()))"
=== VIOLATIONS: 2 (unexpected, not on the allowlist) ===
  discharge.k_dis1-no: ...
  discharge.k_dis2-no: ...
FAILED -- 2 unexpected violation(s)
(exit 3)
```

## 6. What is left undone

- `discharge.k_dis2-no` does not FULLY route post-fix (Section 4) --
  becoming honest fake-completion instead of silent zero-copper is this
  task's actual deliverable; making it fully connect is a Stage 4
  A*/geometry question outside this task's stated scope.
- The `PWR_RTN`/`DC_BUS_RTN` zone-pour-path variant of the same
  underlying "duplicate pad number" board shape (mechanism 2 in PR
  #1172's own table) is not investigated here -- different code path
  (`_zone_pour_stitch.py`, not `_net_pad_positions`), out of scope.
- `scripts/check_net_pin_identity_pad_correspondence.py` is wired into
  the `board-provenance-requirements-gates` CI job's `run:` steps but its
  actual CI execution (as opposed to this document's local, foreground
  verification) was not observed in a live GitHub Actions run as part of
  this investigation.
