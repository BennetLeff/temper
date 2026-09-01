<!-- provenance: commit=c70dde923e2793dd2687df03694829a1aa55e7a8 dirty=UNKNOWN -->
agent/layer-identity-type-v2, based on origin/fix/router-nlayer-routing @ f870bc966 (the branch
carrying PR #1178's 6-layer stackup declaration, board_layer_roles.py, and the 2026-08-13
ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED unfreeze fix, commit 1d6aa4020). pcb/temper.kicad_pcb
sha256=1b15b2747ff55977bd45154e23200c7feaf137e927c4fb9f59d27b2e4c4ade0d, UNCHANGED throughout (this
task touches no board file). Rust changes verified with `cargo test`/`cargo clippy -D warnings`
under CARGO_TARGET_DIR=<repo>/target-shared (the committed shared-cache convention); Python
integration verified against an isolated throwaway venv built via `maturin develop`, NOT the shared
repo .venv, specifically to avoid overwriting the shared compiled extension with a snapshot that
lacks concurrent agents' uncommitted changes to via_clearance.rs/trace_width_assignment.rs in the
same crate. Single agent, no subagents dispatched. -->

# Layer identity type: structural prevention for the stale-copy bug class, plus the SSOT dataflow audit's escalation

**Verdict up front.**

1. **Implemented and tested:** `temper-geometry/src/layer_identity.rs` — a `Layer`/`Stackup` type pair
   where `Layer`'s fields are private and there is no public struct-literal constructor. The only ways
   to obtain a `Layer` are `Stackup::parse`/`Stackup::from_path` (reading a real board's own
   `(layers ...)` + `(setup (stackup ...))` declaration) or the explicit, named `Stackup::test_only`
   escape hatch. A hardcoded stale copy — `Layer { name: "F.Cu".into(), .. }` written outside the
   module — is a compile error, proven by a `compile_fail` doctest that passes. 12 unit tests, all
   passing, including a direct regression test for the PR #1178 freeze (widening the declared signal
   set from 2 to 4 layers changes the parser's *output* with no second copy anywhere to have stayed
   frozen). Thin pyo3 bindings, verified end-to-end against a live Python interpreter.
2. **Implemented and tested, escalated mid-task by the SSOT dataflow audit and judged the higher-leverage
   fix:** `temper-design-bundle/src/parse_engine.rs`'s `raw_board_from_tree` — the general-purpose
   `.kicad_pcb` parser nearly everything in this repo eventually reads through — discarded the
   declared role token (`(0 "F.Cu" signal)`'s `signal`) entirely, keeping only the layer *name*. That
   is the deeper root cause: `io/_parse_board.py`'s `_extract_stackup`, the layer-role reader **every
   non-router_v6 consumer uses** (`core/ipc2152.py`, `router_v6/routing_space.py`,
   `router_v6/thermal_relief.py`, `physics/copper_coverage.py`, and five more per the audit), had no
   structural way to read a declared role even if it wanted to — the data was thrown away one layer
   below it. Fixed additively: `RawBoard` gained a `layer_roles: Vec<String>` field, index-aligned
   with the existing `layers: Vec<String>`, exposed as a new `"layer_roles"` dict key alongside the
   existing `"layers"` key. No existing field, key, or byte of existing output changed. §1.
3. **Deliberately not done, and why:** wiring `_extract_stackup`'s `use_declared_layer_roles` path (or
   any of its nine verified consumers) onto the newly-available role data; migrating
   `board_layer_roles.py`'s Python-side hand-rolled parser onto the new Rust type; the `LayerIndex`/
   `STANDARD_LAYER_ORDER` closed 4-element enum's twelve manufacturing-write call sites; the dead
   `layer:` field in `netclass_rules.yaml`. Each is real, each is the same bug shape, and none of them
   was cheap-and-clearly-correct within this task's remaining budget — §3 says exactly why for each,
   and gives a concrete migration path rather than leaving it unstated.
4. **No DRU/clearance/creepage/copper-weight threshold changed. No ceiling touched. `pcb/temper.kicad_pcb`
   untouched throughout** (sha256 above, checked before and after).

---

## 0. What this task was asked to do, and how the scope actually resolved

The brief named three known hardcoded sites from PR #1178's freeze incident:
`board_layer_roles.ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED`, `router_v6/grid_prep_stage.py`'s
`for layer in ("F.Cu", "B.Cu")`, and `router_v6/_astar_nlayer.py`'s `preferred_order = ["F.Cu", "B.Cu"]`.
On this branch (`fix/router-nlayer-routing`), a same-day prior commit (`1d6aa4020`,
2026-08-13) had already fixed the *symptom* at the Python level: both `grid_prep_stage.py` and
`_astar_nlayer.py` now read through `board_layer_roles.py`'s accessor instead of holding an
independent literal — verified by direct inspection, both files import
`ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED`/`routable_signal_layers_from_path` from that module and
contain no bare `("F.Cu", "B.Cu")` tuple anymore. That left exactly one surviving hardcoded copy:
`board_layer_roles.py`'s own `ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED` tuple and its hand-rolled
Python regex parser for the `(layers ...)` block.

Mid-task, a concurrent SSOT dataflow audit reported a bigger, better-evidenced version of the same
bug one layer down: `board_layer_roles.py` is not the general layer-role reader for this codebase —
`_extract_stackup` is, and it uses a positional/zone-content heuristic because the Rust parser
beneath it never captured the declared role token at all. That is a structural blocker for the whole
class of consumers, not just router_v6, and the audit traced it to a specific ~8-line gap in
`parse_engine.rs`. Given the coordinator's explicit instruction to treat this as the priority and,
if the full consumer rewiring exceeded budget, "deliver the parser change alone," this document
covers both: the originally-scoped type (§1-2), and the escalated parser fix plus what it does and
does not unblock (§1.4, §3).

## 1. What was implemented

### 1.1 `Layer`/`Stackup` (`temper-geometry/src/layer_identity.rs`)

Full module doc comment is in the source; summary of the structural claims:

- **`Layer`'s fields are private; there is no public struct-literal constructor.** Verified by a
  `compile_fail` doctest (`cargo test --doc layer_identity`, passing) that attempts exactly the
  hardcoded-literal shape the PR #1178 bug took and confirms it does not compile from outside the
  module.
- **The only constructors are `Stackup::parse`, `Stackup::from_path`, and the explicit
  `Stackup::test_only` escape hatch.** `parse`/`from_path` read the board's own `(layers ...)` block
  for name+role and `(setup (stackup ...))` for copper thickness — the same two blocks
  `board_layer_roles.py` and `scripts/check_stackup_copper_weight_gate.py` already read independently
  in Python, now with one Rust implementation instead of an implicit third Python copy.
  `Stackup::test_only` takes a `Vec<TestOnlyLayerSpec>` — named, greppable, and requires spelling out
  every field per layer; there is no bare-tuple path into a `Layer`.
- **Copper weight is inseparable from the layer it was parsed for.** `Layer::copper_weight_oz(&self)`
  takes `&self`; there is no free function taking a bare layer name. A copper-weight-aware
  trace-width function must accept a `&Layer`, and the only way to hold one is to have gone through a
  real (or test-only) stackup. `copper_weight_oz_for(layer: &Layer) -> f64` demonstrates the shape —
  trivial on purpose, since the point is the *signature*, not the arithmetic (`thickness_mm / 0.035`).
- **Position (`Outer`/`Inner`) is derived, never asserted** — first/last declared copper layer are
  outer, everything between is inner. This directly replaces the shape of
  `check_stackup_copper_weight_gate.py`'s own `OUTER_LAYERS = ("F.Cu", "B.Cu")` /
  `INNER_LAYERS = ("In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu")` tuples (not migrated in this change — see
  §3.5) with a rule that cannot itself go stale on an 8-layer board, because it reads the board's own
  order instead of naming layers.
- **What is explicitly NOT structural:** `ENGINE_SUPPORTED_SIGNAL_LAYER_NAMES`, the router engine's
  real occupancy-grid/A*-pathfinding coverage. No board file states what the *router implementation*
  supports, so no parse can derive it — this remains a hand-maintained `&[&str]` constant. The
  structural improvement is narrower: it is now the *only* copy of that fact in the tree (previously
  at least three independent copies), reached solely through `Stackup::routable_signal_layers`. A
  consumer can no longer hardcode its own copy of the pair, because the only way to obtain a `Layer`
  at all is through this module — but widening the engine's real capability is still a deliberate,
  reviewed, one-line edit here, not something the type system makes automatic. Say this plainly:
  that residual is *checked* (by inspection, at review time), not made unrepresentable.

Twelve unit tests cover: role/position/copper-weight parsing on a synthetic 6-layer board; the exact
PR #1178 regression shape (2→4 signal layers, no second copy to have stayed frozen); the 2-layer
board still parsing; `routable_signal_layers`'s intersection; every fail-closed error path (missing
`(layers ...)`, missing `(setup (stackup ...))`, a declared copper layer with no matching thickness
entry, no recognized copper layer at all); the test-only escape hatch's position derivation; and
`LayerRole::is_routable_role`. All pass under `cargo test --no-default-features --lib layer_identity`
and the crate's full 8401-test suite is unaffected. `cargo clippy --no-default-features -D warnings`
and `cargo clippy --features python -D warnings` are both clean (the crate denies
`clippy::unwrap_used`/`expect_used`; every fallible parse path returns a typed `StackupParseError`
rather than panicking on untrusted board text).

Thin pyo3 surface: `Layer`/`Stackup` pyclasses (getters only — `name`, `role`, `is_internal`,
`copper_thickness_mm`, `copper_weight_oz` on `Layer`; `layer`, `layer_names`, `signal_layer_names`,
`routable_signal_layer_names` on `Stackup`), plus `parse_stackup`, `parse_stackup_from_path`,
`test_only_stackup`, `engine_supported_signal_layer_names` module functions. Registered append-only
at `lib.rs`'s tail (`crate::layer_identity::register(m)?` after `units::register`), matching the
crate's established "declared after X so appends cannot rewrite a parallel agent's lines" convention.
Checked every existing `add_function`/pyclass name in the crate before adding these — no collisions
with the `kw_boundary_match_py` duplicate the brief flagged (that pair is untouched, in
`via_clearance.rs`/`trace_width_assignment.rs`, neither edited by this change).

Verified end-to-end against a live Python interpreter (isolated throwaway venv, `maturin develop`,
not the shared repo `.venv`): parsing a synthetic 6-layer board correctly returns
`signal_layer_names() == ["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"]`, `F.Cu.copper_weight_oz == 2.0`,
`In1.Cu.copper_weight_oz == 1.0` / `is_internal == True`, the test-only escape hatch round-trips, and
a malformed board (no `(layers ...)` block) raises `ValueError` rather than returning a partial
result.

### 1.2 `parse_engine.rs`'s role-token gap (`temper-design-bundle/src/parse_engine.rs`)

`raw_board_from_tree`'s `"layers"` match arm parsed `(0 "F.Cu" signal)` by reading index 1 (the name)
and discarding index 2 (the role) — confirmed directly in the pre-change source, and independently
by the audit. `RawBoard.layers: Vec<String>` therefore carried names only; nothing built on top of it
(`_extract_stackup`, `extract_stackup_raw`'s Python callers) could read a declared role from this
path even if it tried, and fell back to inferring one from zone content or structural position
instead. `docs/evidence/2026-07-27-phantom-layer-stackup.md` already documents one incident this
produced; `_extract_stackup`'s own `use_declared_layer_roles` flag (added by the U2 slice, commit
`895cc4597`) is an *opt-in, position-based* partial mitigation, still not a read of the actual
declared token — see §3.1.

Fix: `RawBoard` gained `layer_roles: Vec<String>`, index-aligned with `layers`, populated in the same
loop (`s.get(2)` alongside the existing `s.get(1)`, empty string if no third token). Exposed as a new
`"layer_roles"` key on `extract_stackup_raw()`'s output dict, additive alongside the existing
`"layers"` key. No existing field, struct layout, or output byte changed for any existing caller.

Verified: `cargo check`/`cargo clippy -D warnings` clean under both `--no-default-features` and
`--features python`; the crate's 33 pure-Rust unit tests unaffected; and, live, in the same isolated
throwaway venv:

```
raw = temper_design_bundle_python.parse_engine.extract_stackup_raw(board_text)
raw["layers"]      == ["F.Cu", "In1.Cu", "B.Cu", "B.Adhes"]
raw["layer_roles"] == ["signal", "power", "signal", "user"]
```

index-aligned and correct, including `"user"` for a non-copper layer. No test file in the repo
references `extract_stackup_raw` today (grepped — none), so this change carries essentially zero
regression surface by construction, not merely by argument.

## 2. Design principle recap: what is structural vs. what is checked

| Property | Mechanism | Structural or checked |
|---|---|---|
| A `Layer`'s role/position/copper-weight cannot be asserted independently of its name | Private fields, no struct literal | **Structural** — compile error |
| A `Layer` cannot be obtained without parsing a real (or test-only) stackup | No other constructor exists | **Structural** — compile error |
| Copper weight cannot be read without a `Layer` | `copper_weight_oz(&self)` | **Structural** — compile error |
| Position reflects the board's own declared order | Derived at parse time, no name list | **Structural** — no second fact to disagree |
| The router engine's real layer capability | `ENGINE_SUPPORTED_SIGNAL_LAYER_NAMES`, one Rust constant | **Checked** — single copy, human-reviewed on change, not derivable from any board file |
| `_extract_stackup` and its nine consumers read the *real* declared role | Data now available (`layer_roles`); not wired | **Not yet either** — see §3.1 |
| `board_layer_roles.py` itself uses the Rust parser | Not done this session | **Not yet either** — see §3.2 |

## 3. Design for the remaining cases, with a concrete migration path

### 3.1 `_extract_stackup` and its nine verified consumers (highest leverage, most risk)

**What's true today.** `io/_parse_board.py`'s `_extract_stackup(..., use_declared_layer_roles=False)`
is the default, production path for every consumer that isn't one of the four router_v6 modules wired
to `board_layer_roles.py`. Its role classification is zone-content first (a plane-required net's zone
on a layer forces that whole physical layer to `"plane"`), falling back to *structural position*
(index 0 or the last copper index = `"signal"`, everything else = `"mixed"`) — never the literal
declared token. The `use_declared_layer_roles=True` opt-in (U2, commit `895cc4597`) replaces the
zone-content half but **still uses the positional heuristic**, not the real token — confirmed by
reading its implementation directly (`layer_type = "signal" if i == 0 or i == layer_count - 1 else
"mixed"`). Verified consumers still on the default heuristic path per the audit: `core/ipc2152.py`,
`router_v6/routing_space.py`, `router_v6/thermal_relief.py`, `physics/copper_coverage.py`, and five
more not individually confirmed by this agent.

**Why this wasn't wired in this session.** `_extract_stackup`'s own docstring is explicit:
"NOT SAFE TO ENABLE ALONE IN PRODUCTION... flipping this on before pours become derived output (this
plan's U3) reproduces the recorded 12x completion regression in
`docs/evidence/2026-07-28-stackup-partial-revert.md`." That danger is about the *default* flipping to
`True` before `obstacle_map.py` stops treating un-regenerated zones as opaque obstacles on every layer
— not about whether the *opt-in* path reads a heuristic or the real token. Making the opt-in path
honest (read `raw["layer_roles"]` by name instead of deriving from position) is plausibly safe in
isolation — it changes nothing for any caller that leaves the flag at its default `False` — but two
of its highest-value validating consumers (`core/ipc2152.py`, and
`temper-orchestration/src/clearance.rs` for the Rust side) are this session's other active agents'
territory, and doing it without being able to run their test suites alongside real concurrent edits
in the same session is exactly the kind of change that produces the "worktree collision" failure mode
this task's own non-negotiable constraints warn about.

**Concrete migration path:**
1. In `_extract_stackup`, when `use_declared_layer_roles=True` and `raw["layer_roles"]` is present
   and non-empty, build a `{name: role}` dict from `zip(raw["layers"], raw["layer_roles"])` and look
   up each `copper_layers[i]["name"]` in it directly, falling back to the current positional rule only
   for a name absent from the dict (a board with a `(setup (stackup ...))` entry but no matching
   `(layers ...)` declaration — an inconsistency worth a warning, not a hard failure, matching this
   module's existing fail-open-with-warning convention for other partial data).
2. Do not touch the default (`use_declared_layer_roles=False`) path in the same change — it stays
   zone-content-first, unchanged, until U3 lands.
3. Land this as its own PR with its own differential/oracle re-pin (the `_stackup_py_oracle.py`
   verbatim copy will need the same edit, keeping the oracle and production implementation identical
   — the migration's own established contract), reviewed by whoever owns `ipc2152.py` and
   `clearance.rs` at the time, specifically checking whether any of the nine consumers' *current*
   test fixtures assert the positional (not token-based) classification for a board where the two
   would disagree — if none do, the opt-in path's behavior is unchanged for every existing test and
   only becomes more correct for a board that declares a non-first/last layer's role unusually.
4. `Stackup`/`Layer` (this task's Rust type) is the natural target for `_extract_stackup` to build on
   top of entirely, once ready to stop threading three dicts (`raw["layers"]`, `raw["layer_roles"]`,
   `raw["stackup_layers"]`) by hand — `Stackup::parse` already does that assembly, index-alignment and
   all, and is tested for it.

### 3.2 `board_layer_roles.py` itself

The Python module's hand-rolled regex parser (`parse_declared_layer_roles`, `_LAYER_ENTRY_RE`) and
its `ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED` tuple are functionally identical to
`layer_identity.rs`'s `Stackup::parse` / `ENGINE_SUPPORTED_SIGNAL_LAYER_NAMES` — this Rust module was
written specifically to be the thing this Python module delegates to. Not wired in this session
because doing so makes `board_layer_roles.py`'s import-time behavior depend on a rebuilt
`temper_geometry` native extension, and this session cannot safely rebuild the **shared** repo
`.venv` without risking the loss of two other agents' concurrent uncommitted Rust changes in the same
crate (`via_clearance.rs`, `trace_width_assignment.rs`) from the installed `.so` until they rebuild it
themselves. The Rust binding is proven correct against an isolated venv instead (§1.1).

**Concrete migration path:** once no other agent has uncommitted changes in `temper-geometry` (i.e.
after this session's parallel work lands), replace `parse_declared_layer_roles`/
`parse_declared_layer_roles_from_path`/`signal_layer_names`/`routable_signal_layers`/`is_signal_layer`
with thin wrappers over `temper_geometry.parse_stackup`/`parse_stackup_from_path` +
`Stackup.signal_layer_names`/`Stackup.routable_signal_layer_names`, and replace
`ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED = ("F.Cu", ...)` with
`tuple(temper_geometry.engine_supported_signal_layer_names())`. Public function signatures and the
`LayerRole` Python enum stay unchanged, so `grid_prep_stage.py`/`_astar_nlayer.py`/`_pipeline_route.py`/
`_zone_pour_stitch.py` need no edits at all — they already only touch the accessor, not the
implementation behind it (verified in this session, §0).

### 3.3 `LayerIndex` / `STANDARD_LAYER_ORDER` (`core/board.py`)

A closed 4-element `IntEnum` (`F_CU, IN1_CU, IN2_CU, B_CU`) plus a `STANDARD_LAYER_ORDER` tuple,
per the audit backing twelve manufacturing-write call sites via `_validate_4_layer_output`. Same bug
shape as the router's frozen pair: correct only because the production board has stayed 4-layer;
silently wrong the moment a 6-layer (or any non-4-layer) board reaches those call sites, with no
mechanism to notice. Not migrated here — `core/board.py` is a large, `_install_dataclass_fields`-driven
core module (`Board`, `Zone`, `Component`, `Layer`/`LayerStackup` dataclasses all live there) with its
own migration machinery, well outside a "cheap and clearly correct" edit. The natural fix is a
`Layer`-typed replacement for the `IntEnum` indexing (`Stackup::layers()`'s ordering already gives
positional index without a name-to-int table that must be kept in sync with a board's real layer
count) — flagged here as a distinct, appropriately-scoped follow-up, not attempted.

### 3.4 `netclass_rules.yaml`'s dead `layer:` field

Every one of the 13 netclasses in `packages/temper-placer/configs/netclass_rules.yaml` declares a
`layer: "F.Cu"` (or `"B.Cu"`/`"In1.Cu"`) key (confirmed directly — 13 occurrences). A light spot-check
of `core/design_rules.py` (the module that loads this YAML) found no code path reading a `"layer"`
key from a netclass rule, consistent with the audit's claim that nothing reads it — a full trace of
every netclass-rule consumer was not performed by this agent. This is the inverse of the bug class
this task addresses: not a stale copy that silently disagrees with the SSOT, but a *dead* SSOT-shaped
field that looks load-bearing and is not, while the real layer preference lives in an unrelated
hand-maintained enum (`channel_mapping.py`'s `layer_assignment` heuristic, per `board_layer_roles.py`'s
own docstring, §"What layer_assignment.py's soft *preferred*-layer heuristic... still does NOT cover").
This task's own escape-hatch principle applies directly: either (a) wire `design_rules.py` to actually
read and validate this field against a real `Stackup`'s declared layer names (rejecting a netclass
rule that names a layer the board doesn't declare — turning a currently-inert field into a checked
one), or (b) delete the field, since an assertion nothing reads is arguably worse than an admitted gap.
Recommend (a) if any human intent behind the field is recoverable from `git blame`/PR history (not
checked here); (b) otherwise. Not attempted in this session — genuinely a judgment call, not a
mechanical migration, and outside this task's Rust-type-system charter either way.

### 3.5 Copper-weight outer/inner partition in `check_stackup_copper_weight_gate.py`

`OUTER_LAYERS = ("F.Cu", "B.Cu")` / `INNER_LAYERS = ("In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu")` — a
fourth instance of the same shape, hardcoded independently of `board_layer_roles.py`'s signal-layer
set and of this task's new `Stackup`. The gate's own docstring argues this is a deliberately separate
axis (outer/inner COPPER WEIGHT, a fab question) from signal/power ROUTABILITY (a routing-architecture
question) — a real distinction, not a mistake — but `LayerPosition::Outer`/`Inner` in this task's
`Stackup` answers exactly the "outer vs inner" half of that question *structurally* (first/last
declared copper layer, not a name list), and would let this gate stop hand-maintaining its own
partition without changing what question it asks. Not migrated here: `check_stackup_copper_weight_gate.py`
is a CI gate whose thresholds this task's constraints explicitly forbid weakening or changing, and its
current bare-tuple form is arguably fine as *checked* input to a gate that already re-derives both
sides of its comparison live from source (its own docstring's stated design principle) — flagged for
awareness, not urgent.

### 3.6 Units and reference frames (scoped per the brief, not implemented)

The brief asked to scope this fully and implement only where cheap and clearly correct. Findings:

- **`temper-geometry/src/units.rs` already exists** (Wave 4 Phase A, landed before this task) —
  `Mm`/`Mil`/`Inch` newtype wrappers with `to_mil`/`to_mm`/`to_inch` conversions, bit-exact against
  the pinned `pcl_parse.rs` conversion constants, with pyo3 marshalling functions. This *is* the
  units-in-the-type-system infrastructure the brief asked about — it predates this task and was not
  duplicated. What is missing is call-site adoption: no kernel in this repo's Rust yet takes an `Mm`
  parameter instead of a bare `f64` (confirmed by that module's own doc comment — "Nothing in the
  tree converts mil/inch↔mm at runtime today"). Adopting it at specific call sites (e.g. threading
  `Layer::copper_thickness_mm` through as an `Mm` rather than a bare `f64`, which this task did NOT do
  — see `layer_identity.rs`'s `f64` fields) is a natural, cheap follow-up but was not done here to
  keep this module's public surface consistent with the rest of the crate's established `f64`-at-the-
  pyo3-boundary convention (`units.rs`'s own stated design).
- **Reference frames (local vs. world) are already partially typed**: `kicad_transform.rs` is the
  sanctioned single implementation of the R(-theta) convention, cited in this task's brief as the
  12-wrong-copy incident; it takes/returns bare `(f64, f64)` tuples, not a `LocalOffset`/`WorldPoint`
  newtype pair. A frame-typed wrapper (`struct Local(f64, f64); struct World(f64, f64);` with
  `rotate_local_to_world(Local, Theta) -> World` as the only conversion) would make "was this already
  rotated" a type question instead of a naming-convention question, closing the exact class of bug
  the 12-copy incident represents. Not implemented here: it is a real, cheap, likely-correct change,
  but touches `kicad_transform.rs`, a file with its own extensive differential/PBT pinning
  (`test_kicad_transform_rust_differential.py`, `test_kicad_transform_pbt.py`) that this task did not
  budget time to re-verify against, and changing a widely-called function's signature (even if the
  arithmetic is unchanged) has a large blast radius across every caller in this crate. Flagged as the
  single highest-value follow-up in this category.
- **Quadrant index vs. degrees**: already fixed independently, before this task started — commit
  `d8d772961` (`fix(placer): rename initial_rotation -> initial_rotation_quadrant`, in this branch's
  own ancestry) renamed the field so the unit is nameable even though the type is still a bare `int`.
  A true `RotationQuadrant(u8)` newtype (rejecting values outside `0..4` at construction) would close
  the remaining gap — cheap, but out of this task's file scope (placer core, not geometry/layer
  identity) and not attempted.

## 4. Fallback: where the type system cannot reach

Per the brief's instruction to add the narrowest possible enforcement where structural prevention is
not achievable, and to treat it as fallback rather than primary: no new lint or gate was added in this
session. The one candidate — a grep-based CI check for bare `"F.Cu"`/`"B.Cu"`/`"In[0-9]\.Cu"` string
literals outside `layer_identity.rs`, `board_layer_roles.py`, and declared test-fixture modules —
was considered and not implemented, because (a) this repo already has dozens of legitimate non-SSOT
uses of these literals (doc comments, S-expression fixture text in tests, DSN export syntax,
`Component.layer` default values unrelated to stackup routability) that a naive grep would flag as
false positives at a volume that would make the gate ignored rather than useful, and (b) distinguishing
a "routability decision" literal from an "incidental reference" literal (the same triage the
`docs/evidence/2026-08-13-router-nlayer-routing.md` inventory did by hand for 29 files) is not a
mechanical grep — it needs the same human judgment a reviewer would apply, which argues for lint-at-
review (a PR template checklist item: "any new bare layer-name literal deciding routability/role/
weight? If so, does it read `board_layer_roles`/`layer_identity` instead?") over lint-in-CI for now.
If a future instance of this bug class recurs at a *specific* file (the way `kw_boundary_match_py`'s
duplicate registration did), a narrowly-scoped grep gate for that one shape (matching this repo's
`check_layer_plane_emission_coverage.py`/`check_stackup_copper_weight_gate.py` convention of one gate
per specific, previously-recurring failure mode) is the right next step — not a broad one now.
