<!-- provenance: commit=7f7232629258417b88f4285e100e767e7e151b04 dirty=true (working tree
carries this task's own fix, measured against it) -- branch fix/pad-identity-ssot, worktree
/home/bennet/Desktop/temper-pad-identity-ssot, base origin/fix/board-schematic-resync
merged forward to PR #1177 (fix/router-net-batching-silent-drop, commit 7f7232629) per
this task's own instruction to build on that PR rather than duplicate or revert it.
pcb/temper.kicad_pcb NOT modified: sha256
b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6, identical before and
after every measurement below (matches PR #1177's own recorded hash for the same file).
Worktree built with `make venv-isolate` + `make extensions`; `scripts/check_stale_extensions.py`
reported 10/10 fresh (real `Compiling` lines observed for every crate, not a cache-poisoned
0.0Xs no-op) and every extension independently verified to `import`;
`scripts/check_venv_integrity.py` passed (18/18 entries resolve under this worktree). -->

# `(component_ref, pin_number)` is not a unique pad key -- the duplicate-pad-number survey, the identity decision, and what got fixed

## Verdict up front

1. **PR #1177 undercounted its own root cause.** It attributes the
   `discharge.k_dis1-no`/`discharge.k_dis2-no` defect to K2/K3 duplicating
   pad **"3"**. K2/K3 actually duplicate **three** pad numbers -- "1",
   "3", **and "4"** -- each the same 7.5mm-apart current-sharing shape.
   Pad "1" feeds `PWR_RTN`/`DC_BUS_RTN`; pad "4" feeds
   `discharge.k_dis1-nc`/`discharge.k_dis2-nc`. PR #1177's own two fixes
   (`_pipeline_grid._net_pad_positions`'s occurrence-indexed lookup,
   `topology_copper_audit.is_self_referential_net`'s narrowing) are
   General across all three pad numbers, not "3"-specific -- confirmed by
   re-reading the fixed code (`_net_pad_positions` tracks
   `occurrence_by_key` over the WHOLE `net.pins` list, not gated on which
   pad number). What PR #1177 undercounted is the SURVEY, not the fix.
2. **Eight more production call sites had the identical bug**, independent
   of PR #1177's two and of each other: `validation/metrics.py`,
   `router_v6/capacity_check.py`, `router_v6/resource_bound.py`,
   `router_v6/bundle_analyzer.py`, `router_v6/layer_assignment.py`,
   `router_v6/congestion.py`, and `router_v6/bottleneck_geometry.py`
   (twice, in two different functions). All eight are fixed in this task.
   Two more were found and are **not** fixed here -- Rust, on live and
   pinned-oracle paths, see "Left undone" below.
3. **The identity decision**: `(ref, pin_number, occurrence)`, occurrence
   counted in a component's own `Component.pins` encounter order. This is
   exactly what PR #1177's `_nth_matching_pin` already implemented ad hoc;
   this task promotes it to `temper_placer.core.pad_identity`, the single
   canonical implementation, and adds a Rust-side typed identity
   (`temper-design-bundle::pad_occurrence::PadOccurrence`) plus a new Rust
   `Component.get_pin_occurrences` method as the one SSOT for "what does a
   pin name/number match."
4. **A new, structural CI gate** (`scripts/check_pad_identity_ambiguity.py`)
   complements PR #1177's net-accounting gate: it is component-level, and
   fails when a footprint IN USE has a duplicate pad number AND a
   production `.get_pin(` call site outside a reviewed allowlist exists --
   catching the shape PR #1177's net-level gate is structurally blind to
   (see "The net-level gate's blind spot" below).

## Part 1: the duplicate-pad-number survey

### Method

`pcb/libs/**/*.kicad_mod` (the 13 library footprint files) and every
`(footprint ...)` block embedded in `pcb/temper.kicad_pcb` (KiCad embeds a
full copy of each placed footprint in the board file) were parsed with a
self-contained paren-balanced regex extraction -- the same technique
`check_net_pin_identity_pad_correspondence.py` and
`check_pad_identity_ambiguity.py` (this task's new gate) both use, no
compiled extension needed -- counting every `(pad "N" ...)` occurrence per
footprint and flagging any pad number/name that occurs more than once.

### Result: every footprint in `pcb/libs/**`

| Footprint file | Pads | Distinct numbers | Duplicated numbers |
|---|---:|---:|---|
| `Connector_JST.pretty/JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical.kicad_mod` | 4 | 4 | -- |
| `lib.pretty/ESP32-S3-WROOM-1.kicad_mod` | 39 | 39 | -- |
| `lib.pretty/LitzPad_15A.kicad_mod` | 2 | 2 | -- |
| `lib.pretty/SOIC16W_Isolated.kicad_mod` | 14 | 14 | -- |
| `temper.pretty/CMC_B82726S.kicad_mod` | 4 | 4 | -- |
| `temper.pretty/CST-1005.kicad_mod` | 4 | 4 | -- |
| `temper.pretty/CST2010.kicad_mod` | 12 | 12 | -- |
| `temper.pretty/CST3015.kicad_mod` | 4 | 4 | -- |
| `temper.pretty/C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal.kicad_mod` | 2 | 2 | -- |
| `temper.pretty/Converter_DCDC_RECOM_RP-S.kicad_mod` | 4 | 4 | -- |
| `temper.pretty/Relay_DPDT_Finder-40.52.kicad_mod` | 8 | 8 | -- |
| **`temper.pretty/Relay_SPDT_Schrack-RT314012.kicad_mod`** | 8 | 5 | **"1"x2, "3"x2, "4"x2** |
| **`temper.pretty/Relay_SPST_Omron-G4A-E.kicad_mod`** | 8 | 5 | **""x4** |

Only these last two footprint files, out of 13, declare a duplicate pad
number. Every other footprint on this board -- every resistor, capacitor,
diode, connector, IC, and the 39-pin ESP32-S3 module -- has one physical
pad per pad number, no exceptions.

### As placed on `pcb/temper.kicad_pcb` today

| Ref | Footprint | Duplicated pad numbers | Why |
|---|---|---|---|
| K2 | `temper:Relay_SPDT_Schrack-RT314012` | "1"x2, "3"x2, "4"x2 | 16A current-sharing contacts: each logical contact is fabricated as two physical solder holes, 7.5mm apart, both carrying one pad number |
| K3 | `temper:Relay_SPDT_Schrack-RT314012` | "1"x2, "3"x2, "4"x2 | same as K2 (identical footprint, same manufacturer part) |
| K1 | `temper:Relay_SPST_Omron-G4A-E` | ""x4 | four NPTH mechanical mounting holes, unconnected (no `(net ...)` clause) -- KiCad's convention for "not a pad number" |

K2's actual pad geometry, read directly off the board (position, type, and
the net each pad occurrence carries):

```
pad "2" thru_hole rect  at (0,0)      rot=270  net=34  discharge.k_dis1-coil1
pad "5" thru_hole oval  at (0,-7.5)   rot=270  net=35  discharge.k_dis1-coil2
pad "4" thru_hole oval  at (15.26,-7.5) rot=270 net=36  discharge.k_dis1-nc
pad "4" thru_hole oval  at (15.26,0)    rot=270 net=36  discharge.k_dis1-nc   <- dup, same net
pad "1" thru_hole oval  at (20.3,-7.5)  rot=270 net=13  PWR_RTN
pad "1" thru_hole oval  at (20.3,0)     rot=270 net=13  PWR_RTN               <- dup, same net
pad "3" thru_hole oval  at (25.34,-7.5) rot=270 net=37  discharge.k_dis1-no
pad "3" thru_hole oval  at (25.34,0)    rot=270 net=37  discharge.k_dis1-no  <- dup, same net
```

K3 is identical up to net names/numbers. Two invariants hold for every
duplicated pair on this board, confirmed against the raw board bytes
(not assumed): **both physical occurrences of a duplicated pad number
always carry the identical net** (electrically, that is what "current-
sharing contact" means -- they are the same node), and **the duplicate
pairs are always 7.5mm apart on this footprint**, never coincident. The
first invariant is what makes `core/loop_extractor.py::get_pin_net` safe
to leave on `Component.get_pin` (see "Audited safe" below); the second is
what makes a first-match bug silent rather than an obvious geometric
degeneracy -- the two points are real, distinct, and far enough apart that
collapsing them produces a plausible-looking but wrong answer, not a
NaN or a zero-area degenerate case something would notice.

K1's four NPTH pads are unconnected (`net=None`), so no `Net.pins`
construction ever references them and the general router/geometry bug
class this task investigates cannot reach them. They remain a data point
in the survey (a duplicate-pad-number footprint IS in use, so the
component-level gate correctly still flags K1) but are not part of the
call-site audit below, which is entirely about mis-resolving a pad's
*position*.

## Part 1, continued: every `(ref, pin)`-as-pad-key call site, audited

`grep -rn "\.get_pin("` across every `*.py` and `*.rs` in the tree found
one production Python call site of the pyo3 `Component.get_pin` method
outside `router_v6`/`validation` (audited safe, see below), and zero real
Rust call sites through that method -- but `Net.pins`-walking loops that
manually re-derive first-match pin lookup **without** calling `get_pin`
by name are the actual majority of the bug's spread, both in Python
(`congestion.py`, `bottleneck_geometry.py` used a bare
`next(p for p in comp.pins if p.name == x or p.number == x)`
one-liner) and in Rust (`terminal_planning.rs` uses
`comp.pins.iter().find(...)`). The table below is exhaustive for every
site this task found that resolves a `(ref, pin_number)` pair to a
specific physical pad (position, or "the" pin object) rather than merely
its existence or net membership.

| Site | Shape | Severity | Verdict |
|---|---|---|---|
| `router_v6/_pipeline_grid.py::_net_pad_positions` | `comp.get_pin(pin_name)`, walked over `net.pins` | HIGH | Fixed by PR #1177 (`_nth_matching_pin`, occurrence-indexed). This task refactored it to delegate to `pad_identity.resolve_net_pins`/`net_pad_positions` instead of keeping a local copy -- no behavior change, same fix, single source. |
| `router_v6/topology_copper_audit.py::is_self_referential_net` | `len(set(pins)) == 1` trusted as pad-identity proof | HIGH | Fixed by PR #1177 (narrowed to `len(pins) == 1`, the only position-independent case). Left as-is (already correct, no duplication to consolidate). |
| `validation/metrics.py::_compute_wirelength_metrics` | `comp.get_pin(pin_name)` per `net.pins` occurrence | HIGH | **Newly fixed this task.** Feeds HPWL wirelength metrics -- a duplicated pad's second occurrence collapsed onto the first, undercounting a net's bounding box. |
| `router_v6/capacity_check.py::_net_pad_positions` | `comp.get_pin(pin_name)`, a second, independent reimplementation of the SAME function name as `_pipeline_grid.py`'s (pre-fix) | HIGH | **Newly fixed this task.** Feeds pre-routing capacity-demand ratios. Note: kept its own non-rotation-aware `pin.position` math unchanged -- a separate, pre-existing, out-of-scope defect (see "Distinct from this task" below); only pad IDENTITY was fixed. |
| `router_v6/resource_bound.py::_net_bboxes_from_pcb` | `comp.get_pin(pin_name)` per `net.pins` occurrence | HIGH | **Newly fixed this task.** Feeds the resource-exhaustion theorem's per-net bounding boxes and conflict-cluster detection. |
| `router_v6/bundle_analyzer.py::BundleAnalyzer._net_pad_positions` | `comp.get_pin(pin_name)`, a THIRD independent reimplementation of the same function name | HIGH | **Newly fixed this task.** Feeds the convex-hull geometric footprint used for net-bundling/EMI-constraint detection. |
| `router_v6/layer_assignment.py::_get_net_dominant_direction` | `comp.get_pin(pin_name)` per `net.pins` occurrence | LOW (dead code) | **Newly fixed this task, preemptively.** `assign_layers`'s ONE production caller always passes `component_positions=None`, so this branch is unreached today (confirmed via `test_layer_assignment_rust_differential.py`'s own documented grep evidence). Fixed anyway since a future caller passing real positions would hit the bug live. |
| `router_v6/congestion.py::_get_pin_positions` | inline `for pin in comp.pins: if pin.name == x or pin.number == x: ... break` | HIGH | **Newly fixed this task.** Feeds min-cut source/sink geometry for grid-based congestion analysis (the placement optimizer's routability feasibility check). |
| `router_v6/bottleneck_geometry.py::_resolve_pad_cells` | same inline first-match `next(...)` shape | HIGH | **Newly fixed this task.** Builds min-cut source/sink cells for bottleneck (routability) analysis directly. |
| `router_v6/bottleneck_geometry.py` (pad-net-class capacity discount block, ~line 984) | same inline first-match `next(...)` shape | HIGH | **Newly fixed this task.** Feeds the R4 "category-HIGH neighbor discounts category-LOW capacity" safety-adjacent congestion rule -- a mis-resolved pad here could misattribute which net class a capacity cell belongs to. |
| `core/loop_extractor.py::get_pin_net` | `component.get_pin(pin_name)`, tries several candidate NAMES, returns the first match's NET | none | **Audited safe, left unchanged.** Every physical pad sharing a pad number carries the identical net by construction (see Part 1's invariant above) -- confirmed against K1/K2/K3 specifically, not assumed. Which physical occurrence answers "what net" is irrelevant when they can't disagree. Recorded as the one reviewed exception in `check_pad_identity_ambiguity.py`'s `ALLOWED_GET_PIN_CALL_SITES`. |
| `core/loop_extractor.py::get_common_net` | `{pin.net for pin in comp.pins if pin.net}` | none | Iterates ALL pins directly, never selects "the" pin by name -- no ambiguity possible. |
| `temper-rust-router/src/terminal_planning.rs::extract_net_terminals` | `comp.pins.iter().find(\|p\| p.name==x \|\| p.number==x)`, Rust-native reimplementation of `get_pin`'s exact semantics (the function's own comment says so) | HIGH, **NOT FIXED** | Live production path: `router_v6/terminal_extraction.py::extract_net_terminals` is a thin shim delegating straight to `temper_rust_router.extract_net_terminals_py` (this function), called from `_pipeline_route.py:555` with `net.pins` for every net Stage 4 processes. Pinned by 4 test files (`test_terminal_extraction_rust_differential.py`, `_wire_rust_differential.py`, `_wire_pbt.py`, plus the plain `test_terminal_extraction.py`) comparing against a frozen Python oracle bit-for-bit. See "Left undone" below for why this is reported, not fixed, in this task. |
| `temper-orchestration/src/pipeline_route.rs::run_collect_pad_positions` | `comp.call_method1("get_pin", (pin_name,))`, a direct Rust-to-Python call reproducing the same first-match semantics | HIGH, **NOT FIXED** | A Rust port of the pinned `_adapter_convert._write_routes_to_content` pad-position block (route-WRITING, not routing-decision, path). Same "both arms must change together" risk as the item above. See "Left undone." |

### Distinct from this task: two pre-existing, out-of-scope defects noticed in passing

- `router_v6/capacity_check.py::_net_pad_positions` and
  `router_v6/bundle_analyzer.py::_net_pad_positions` both add
  `pin.position` (the pin's LOCAL, pre-rotation offset) directly to
  `comp.initial_position`, instead of routing through
  `pin_world_position` (rotation-and-side-aware). This is the exact
  ROTATION bug `_pipeline_grid._net_pad_positions`'s own docstring
  describes being fixed there (2026-08-08, ~87.6% of this board's
  components have nonzero rotation) -- still present, independently, in
  these two files. Left unfixed here: it is a different defect class
  (rotation, not pad identity) from this task's mandate, and fixing it
  would change these two functions' numeric output for the ~87.6% of
  components with nonzero rotation, a much larger behavioral footprint
  than a pad-identity fix should carry in one PR. Flagged for a
  dedicated follow-up.
- `router_v6/bundle_analyzer.py`'s `_compute_median_edge_length` calls
  `skeleton.graph.edges_with_data()`, a method the `Graph` type in this
  tree does not have (`AttributeError`), on `main` before this task's
  changes (confirmed: `git show HEAD:...bundle_analyzer.py` has the same
  line; a same-commit run of the affected tests against the unmodified
  base fails identically). Pre-existing, unrelated to pad identity, not
  fixed here.

## Part 1, continued: the identity decision

Three candidates were weighed:

1. **Raw position `(ref, pin, position)`.** Rejected: position is the
   OUTPUT of pad resolution, not a usable input key -- every real caller
   that needs to look up a pad has only `(ref, pin_number)` in hand (that
   is exactly what `Net.pins` stores), never a coordinate. Circular.
2. **An opaque `PadId` assigned at parse time.** Rejected as
   disproportionate. It would need a new field crossing the pyo3 boundary
   on every mirrored `Pin` struct across (per PR #1167's own audit of a
   comparably-sized field) 6+ Rust crates, plus construction-site updates
   in ~90 test files that build `Pin`/`Component` objects directly with
   keyword arguments -- for a benefit `occurrence` already provides at
   zero schema cost. It is also, structurally, a second registry that
   could drift from `Component.pins`' own order the same way the
   1oz/2oz stackup value and the `kicad_pro`-vs-declared netclass name
   drifted from their sources (PR #1153, the `GND`/`kicad_pro` incident)
   -- a second place asserting an identity that the pin list itself
   already, implicitly, encodes.
3. **`(ref, pin_number, occurrence)`, occurrence in `Component.pins`
   encounter order (CHOSEN).** `net.pins` and `comp.pins` are both built
   by the same encounter-order iteration over a component's raw pad list
   (`extract_nets_pure` / `parse_engine.rs`), so the Nth occurrence of
   `(ref, pin_number)` in a net's own `.pins` corresponds EXACTLY to the
   Nth name/number-matching pin in that component's own `.pins` -- no new
   field, no pyo3 boundary change. **Stability**: unaffected by re-parsing
   an unmodified board (file order is deterministic) and unaffected by an
   unrelated board edit -- a pin with a DIFFERENT number added anywhere in
   the footprint never changes another pin's occurrence index, since only
   same-number pads increment it. This is exactly what PR #1177's
   `_nth_matching_pin` already implemented ad hoc for one call site; this
   task promotes it to the one canonical implementation
   (`temper_placer.core.pad_identity`) instead of leaving it to be
   re-derived independently at N call sites (which is, empirically, how
   eight of them ended up NOT having the fix at all).

## Part 2: the SSOT and the fail-closed gate

`temper_placer.core.pad_identity` (new module,
`packages/temper-placer/src/temper_placer/core/pad_identity.py`) is the
single source of truth for pad identity resolution: `PadOccurrence`
(the `(ref, pin_number, occurrence)` identity), `iter_matching_pins` /
`nth_matching_pin` / `get_unique_pin` / `resolve_net_pins` /
`net_pad_positions` / `duplicate_pad_numbers` / `iter_pin_occurrences`.
All nine fixed call sites (the two from PR #1177 plus the eight found
here) delegate to this module instead of restating the occurrence-tracking
logic locally -- eliminating three independent, near-identical copies of a
function literally named `_net_pad_positions` (in `_pipeline_grid.py`,
`capacity_check.py`, and `bundle_analyzer.py` -- exactly the "duplicated
declarations" pattern PR #1153's stackup contradiction and the
`GND`/`kicad_pro` netclass-name mismatch both trace back to).

The name/number MATCH itself (`pin.name == X or pin.number == X`) is now
owned by Rust: `Component.get_pin_occurrences` (new pyo3 method,
`netlist_contracts.rs`) returns EVERY matching pin, and
`pad_identity.iter_matching_pins` delegates to it rather than
re-implementing the comparison in Python a second time.

### The net-level gate's blind spot

PR #1177's `check_net_pin_identity_pad_correspondence.py` is a NET-level
invariant: it flags a net whose ENTIRE `(component_ref, pad_number)`
pin-identity view collapses to `<=1` distinct tuple while the real
physical pad count is `>1`. This is exactly right for
`discharge.k_dis1-no`/`discharge.k_dis2-no` (K2/K3 pad "3": the net's
ONLY pins are the two duplicate occurrences). It is structurally silent
for K2/K3's OTHER two duplicated pad numbers: `PWR_RTN`/`DC_BUS_RTN` (pad
"1") and `discharge.k_dis1-nc`/`discharge.k_dis2-nc` (pad "4") each
connect to several OTHER components too, so the net's distinct-tuple
count never drops to 1 -- the gate never fires for them, even though a
first-match consumer still mis-resolves K2/K3's own duplicated pad within
that net.

`scripts/check_pad_identity_ambiguity.py` (new gate, this task) closes
that blind spot by asking a structurally different, COMPONENT-level
question instead of a net-level one: does any footprint IN USE declare a
duplicate pad number (independent of which nets it participates in), and
does any production `.get_pin(` call site outside a small, reasoned
allowlist exist? Both conditions are checked independently and the gate
fails only on their conjunction (a duplicate-pad footprint with zero
unsafe consumers is harmless; the reverse is unreachable). Measured
against the real board and the real source tree after this task's fixes:

```
Footprints with a duplicate pad number: 3
  K1 (temper:Relay_SPST_Omron-G4A-E): ""x4
  K2 (temper:Relay_SPDT_Schrack-RT314012): "1"x2, "3"x2, "4"x2
  K3 (temper:Relay_SPDT_Schrack-RT314012): "1"x2, "3"x2, "4"x2

.get_pin( call sites in production source: 1
  reviewed, allowlisted (1):
    temper_placer/core/loop_extractor.py:257 in get_pin_net()

PASSED -- every .get_pin( call site is reviewed and allowlisted.
```

Registered in `gate_input_registry._CI_SCRIPT_SURVEY` and
`scripts/manifest.yaml`, wired into `.github/workflows/python-tests.yml`
alongside PR #1177's gate (never `continue-on-error`).

**What this gate deliberately does NOT catch**: a first-match pin
resolution written WITHOUT calling `.get_pin(` by name -- the inline
`for pin in comp.pins: if pin.name == x or pin.number == x: ... break`
shape that `congestion.py` and `bottleneck_geometry.py` both had before
this task. Every KNOWN instance of that shape was migrated onto
`pad_identity` in this same change, so nothing in the tree needs it
caught today, but a syntactic AST match for a `.get_pin(` METHOD CALL
cannot, by construction, see a hand-rolled equivalent that never calls
that method. This is a real, stated gap, not a silent one -- see "Left
unenforced" below.

## Part 3: type-level enforcement

Following PR #1167's convention (newtype + `compile_fail` doctest in
Rust, static gate in Python) rather than inventing a second style:

- **Rust**: `temper-design-bundle::pad_occurrence::PadOccurrence` --
  `PadOccurrence::new(pin_number, occurrence)`, no `From<&str>` /
  `From<String>` impl, so a bare pad number cannot silently stand in for
  a specific physical pad. `cargo test --doc -p temper-design-bundle`:
  the `compile_fail` doctest (`let _bad: PadOccurrence = "3".into();`)
  passes, i.e. is verified to NOT compile. Additive, not a retrofit --
  mirrors `temper-geometry::rotation_quadrant::RotationQuadrant`'s own
  "additive, not a retrofit" judgment exactly (see that module's doc):
  zero Rust production call sites resolve pin identity through
  `Component.get_pin` today (`terminal_planning.rs` reimplements the
  comparison inline instead, per the audit above), so this type is
  infrastructure for future Rust-side pad resolution, not a behavior
  change for anything that exists.
- **Python**: `Component.get_pin` (the pyo3 first-match method) still
  exists and still returns the first match -- removing it outright would
  break `core/loop_extractor.py::get_pin_net`'s audited-safe use and is a
  larger API break than this task's mandate. Instead,
  `pad_identity.get_unique_pin` is the enforcement primitive: it raises
  `AmbiguousPinError` the moment a caller asks for "the" pin on a
  component with more than one matching pad and supplies no occurrence --
  the exact shape that let `get_pin` silently return pad-3-of-2. This is
  weaker than a compile error (Python has none to offer here) but is
  fail-LOUD rather than fail-silent: the ambiguous case now raises
  immediately, every time, rather than returning a plausible-looking
  wrong answer. Paired with `scripts/check_pad_identity_ambiguity.py`
  (Part 2) as the static gate PR #1167's convention calls for.

### Left unenforced (stated plainly, per PR #1167's own precedent)

- **A hand-rolled first-match scan that never calls `.get_pin(` by
  name is not mechanically caught**, in either language. Every known
  instance was fixed in this task; a textual/AST gate for the general
  shape (not just the named method) would need to match something like
  "iterate `.pins`, compare `.name`/`.number` to a variable, stop at
  first match" -- a much higher false-positive-risk pattern than
  `check_rotation_quadrant_arithmetic.py`'s division/radians-call
  patterns, and not attempted here.
- **`Component.get_pin` itself is unchanged** -- still first-match,
  still silently wrong for a component with duplicate pad numbers if a
  caller bypasses `pad_identity` and calls it directly for a
  position-sensitive use. `check_pad_identity_ambiguity.py` catches this
  IF the call is written as `.get_pin(`; nothing stops a NEW hand-rolled
  reimplementation from reintroducing the same defect the way
  `congestion.py`/`bottleneck_geometry.py` independently did.
- **`terminal_planning.rs::extract_net_terminals` and
  `pipeline_route.rs::run_collect_pad_positions`** (Part 1's table) carry
  the identical bug, on a LIVE path (the former) and a pinned-oracle path
  (the latter), and are NOT fixed in this task. See "Left undone" below.

## Left undone

- **`temper-rust-router/src/terminal_planning.rs::extract_net_terminals`**
  is the live terminal-extraction kernel `_pipeline_route.py` calls for
  every net Stage 4 processes, reimplementing `get_pin`'s first-match
  semantics natively in Rust (the function's own comment says so). Fixing
  it correctly requires updating BOTH arms together --the pinned oracle
  (`tests/router_v6/_terminal_extraction_py_oracle.py`) and the Rust
  kernel -- per the PR #1136/#1137 lesson this task's own brief names
  explicitly ("changing a pad-identity type touches pinned Python oracles
  and Rust differential tests. Both arms must change together"). Four
  test files pin this function's exact output bit-for-bit
  (`test_terminal_extraction_rust_differential.py`,
  `test_terminal_extraction_wire_rust_differential.py`,
  `test_terminal_extraction_wire_pbt.py`, plus the un-suffixed
  `test_terminal_extraction.py`). Given this task's mandate is the SSOT
  and the gate, not a full cross-language migration, this is reported as
  the single most important follow-up rather than attempted under time
  pressure that risks a rushed cross-arm change -- exactly the failure
  mode PR #1136 hit.
- **`temper-orchestration/src/pipeline_route.rs::run_collect_pad_positions`**
  is a Rust port of the pinned `_adapter_convert._write_routes_to_content`
  pad-position block (route-WRITING, not routing-decision) and calls
  `comp.call_method1("get_pin", (pin_name,))` directly -- same first-match
  defect, same cross-arm risk, not fixed here for the same reason.
- **The two rotation-unaware `_net_pad_positions` functions**
  (`capacity_check.py`, `bundle_analyzer.py`) noted above under "Distinct
  from this task" -- a different defect class, flagged, not fixed.
- **A hand-rolled (non-`.get_pin(`-named) first-match reimplementation is
  not mechanically gated** -- see "Left unenforced" above.

## Verification

- `cargo test -p temper-design-bundle --lib pad_occurrence`: 5/5 unit
  tests pass.
- `cargo test -p temper-design-bundle --doc pad_occurrence`: 2/2 doctests
  pass, including the `compile_fail` proof.
- `uv run --no-sync maturin develop --release --manifest-path
  packages/temper-design-bundle/Cargo.toml`: real `Compiling
  temper-design-bundle` line observed (not a cache-poisoned 0.0Xs no-op);
  `scripts/check_stale_extensions.py` 10/10 fresh both before and after,
  every extension independently `import`-verified;
  `scripts/check_venv_integrity.py` 18/18 resolve under this worktree.
- `uv run pytest scripts/tests/test_check_pad_identity_ambiguity.py`:
  18/18 pass, including an end-to-end assertion against the real board
  and real source tree.
- ~1520 targeted pytest cases across every fixed call site's own test
  file plus every rotation/geometry-adjacent Rust-differential/PBT suite
  that touches the same code paths (`test_pipeline_grid_net_pad_positions`,
  `test_capacity_check`, `test_resource_bound`, `test_bundle_analyzer*`,
  `test_layer_assignment_rust_differential`, `test_bottleneck_geometry*`,
  `test_bottleneck_analysis*`, `test_validation_metrics_rust_differential`,
  `test_quality_metrics`, `test_topology_copper_audit`,
  `test_pad_connectivity_audit`, `test_congestion_rust_differential`,
  `test_congestion_tensor_rust_differential`): 1519 passed, 11 failed --
  every failure independently confirmed pre-existing on the unmodified
  base commit (`7f7232629`) via a side-by-side `PYTHONPATH`-swapped run
  against a throwaway worktree at the same commit, unrelated to pad
  identity (`bundle_analyzer.py::_compute_median_edge_length`'s
  pre-existing `edges_with_data` `AttributeError`, and
  `test_topology_copper_audit.py`'s `GATE_L`/`PWM_H` unexplained-gap
  case, both reproduced identically on the base commit).
- `scripts/check_manifest_gate.py`, `scripts/import_linter_gate.py`: both
  green.
- `gate_input_registry`'s completeness test
  (`test_every_invoked_ci_gate_script_is_registered`) confirms
  `check_pad_identity_ambiguity.py` is registered; its one failure
  (`check_router_clearance_floor.py`/`check_wasm_covered.py` missing)
  is pre-existing on the base commit, unrelated to this task.
- `git status --porcelain` / `git grep -l '^<<<<<<< '` clean before every
  commit; `pcb/temper.kicad_pcb` sha256 unchanged throughout.

## Hard constraints honored

- [x] `pcb/temper.kicad_pcb` never modified -- sha256 identical before/after
- [x] No clearance/creepage/safety value or ratchet ceiling changed
- [x] PR #1177's two call-site fixes and its
      `check_net_pin_identity_pad_correspondence.py` gate not duplicated or
      reverted -- built on top of them (merged forward, then
      `_pipeline_grid.py` refactored to delegate to the new SSOT without
      changing its fixed behavior)
- [x] Pad-identity type changes (the new Rust `PadOccurrence` newtype and
      `Component.get_pin_occurrences` method) shipped together with their
      Python-side consumer (`pad_identity.py`) in the same change --
      no one-arm-only change of the PR #1136/#1137 shape
