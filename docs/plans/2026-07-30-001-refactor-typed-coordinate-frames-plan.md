---
title: "refactor: Typed Coordinate Frames for the Placer's Geometry Pipeline"
type: refactor
status: active
date: 2026-07-30
---

# Typed Coordinate Frames for the Placer's Geometry Pipeline

## Summary

Retrofit phantom-typed coordinate frames (`Point[Local]` / `Point[World]`, etc.) onto the
placer's existing geometry vocabulary — starting at `core/pin_geometry.py`'s single
already-documented "canonical" transform function and working outward — so that mixing a
local pad offset with a world position becomes a `mypy` error instead of a silent numeric
bug. In parallel, promote the CP-SAT solver's already-correctly-shaped `PlacementUpdate`
(`io/_write_types.py`) into a shared `core` type and migrate `CpSatPlacementResult` and
`_apply_placements_to_pcb`/`route_pcb` onto it, so a solved rotation cannot be silently
dropped from a placement the way it was in #471. The migration is staged so each unit is
independently mergeable and behavior-preserving, and it explicitly does **not** extend
phantom types into the `dict[str, Any]` placement-blob consumers (`_copper.py`,
`domain_clearance.py`) — that would require inventing a second, much larger typed-schema
migration this plan recommends against taking on now (see Key Technical Decisions).

---

## Problem Frame

Four of this project's most damaging recent bugs share one shape — a value from one
coordinate frame (a local pad offset, a footprint anchor, a CP-SAT box-center) was used as
if it were in another, or a rotation was silently dropped from a value that should have
carried it — and none was caught by types, because every one of these quantities is
`tuple[float, float]` (or a bare `dict[str, tuple[float, float]]` for a whole placement).
`mypy` cannot distinguish "world" from "local" when both are literally the same type. This
plan surveys where that ambiguity actually lives in the code (not in theory) and proposes an
incremental, honestly-costed fix.

---

## Requirements

- **R1.** Name every coordinate frame currently in play in the placer's geometry pipeline,
  grounded in specific files/lines, not assumed to be just "local" and "world."
- **R2.** Design a phantom/newtype frame system (`Point[Local]`, `Point[World]`, etc.) such
  that adding a local offset to a world origin is a type error, and identify the smallest
  set of call sites where retrofitting it would have caught a real historical bug.
- **R3.** Design a unified `Placement` type (position + orientation) to replace
  `dict[str, tuple[float, float]]` position dicts paired with a separate, droppable
  `rotations` dict — the exact shape that let #471 happen — and determine whether
  `CpSatPlacementResult` / `PlacementUpdate` already supply the right building blocks.
- **R4.** Propose a migration order where every step is independently mergeable and
  behavior-preserving, with a concrete way to prove behavior preservation at each step.
- **R5.** Determine empirically — not by assumption — whether the CI type-check gate
  (`scripts/check_typecheck_gate.py`, `.typecheck-allowlist`) would actually enforce the
  proposed phantom types today, or whether they would be decorative until the gate's
  configuration changes.
- **R6.** State explicitly what this plan's approach does **not** catch, with reference to
  the specific historical bugs it would and would not have prevented.
- **R7.** Where a part of this plan's own scope is not worth doing given the codebase's
  current posture, say so plainly, with reasoning — do not pad the plan to look complete.

---

## Scope Boundaries

- No production code is written by this plan. Illustrative snippets in this document are
  directional, not implementation-ready.
- `pcb/**` and `elec/src/**` are read-only; nothing here proposes changing board or
  schematic source.
- Rust crates (`packages/temper-geometry`, `packages/temper-drc-rs`, etc.) are out of scope.
  `mypy`/phantom types are a Python-only mechanism; a parallel newtype effort in Rust (which
  already has a real type system and would use `struct Local(f64, f64);` or similar) is a
  separate, unscoped decision this plan does not make.
- The `pcbnew` differential oracle and the single-transform lint (both in flight on branches
  stacked on PR #479, per the dispatching brief) are not designed or modified here. This
  plan's Implementation Units are complementary to, not a replacement for, that work — see
  Key Technical Decisions and System-Wide Impact.
- Extending typed frames into the `dict[str, Any]` "placement blob" representation consumed
  by `requirements/validators/_copper.py` and `placer/cp_sat/domain_clearance.py` is
  evaluated and explicitly **not** included as a committed Implementation Unit — see Key
  Technical Decisions for why, and `### Deferred to Follow-Up Work` below for what a future
  plan would need to do to take it on.
- Widening the CI type-check gate's strictness to match `packages/temper-placer`'s own
  `pyproject.toml` (R5's finding) is scoped as one small Implementation Unit (U7) but its
  fallout (whether the newly-checked untyped-def bodies introduce new allowlist debt) is not
  fully enumerated here — that count is deferred to U7's own execution.

### Deferred to Follow-Up Work

- A typed replacement for the `dict[str, Any]` placement/board blob that
  `_copper.py`/`domain_clearance.py` consume (would need to cross the `src`-imports-`tests`
  boundary that `domain_clearance.py`'s own docstring already flags as architecturally
  unusual — see Key Technical Decisions).
- Extending `Point[Frame]` into the Rust crates, if the Python-side migration proves its
  value.
- A dedicated pass reconciling `core/units.py`'s currently-unused `Millimeters`/`CellIndex`
  NewTypes with the grid/occupancy-cell frame this plan names (F6) — flagged as a precedent
  risk (Key Technical Decisions) but not scheduled as an Implementation Unit here.

---

## Context & Research

### The frames actually in play (R1)

Six distinct coordinate frames are live in the placer's geometry pipeline today, named from
the code that produces or consumes them — not from an idealized "local vs. world" model:

| # | Frame | Where it lives | Notes |
|---|---|---|---|
| F1 | **KiCad footprint-anchor** | `fp.position` in a `.kicad_pcb` `(at X Y ANGLE)`; written by `write_placements_to_pcb` (`io/_write_board.py:148-156`) | The only frame KiCad itself understands. Every other frame exists to be converted back to this one before a board is written. |
| F2 | **Pad-local offset (pad-centroid-relative)** | `Pin.position` (`core/netlist.py:47`, "offset from component center"); populated at parse time by `_parse_modules.py:117-125` after subtracting the centroid offset; the dict form `p["offset"]` in `requirements/validators/_copper.py:112` | Pre-rotation. This is what `core/pin_geometry.py::pin_world_position` takes as its `pin` argument. |
| F3 | **Footprint-anchor→pad-centroid offset ("center_offset")** | Computed `_parse_modules.py:109-114` (`center_offset_x/y`), stored as **stringified attributes**, not typed fields: `Component.attributes["_center_offset_x"/"_center_offset_y"]` (`_parse_modules.py:161-171`) | A frame that exists today only as a `dict[str, str]` entry — there is no dataclass field for it at all, so it can't be phantom-typed without first promoting it to a real field. |
| F4 | **CP-SAT box-center / solve frame** (this codebase's own "world") | `Component.initial_position` (`core/netlist.py:82`, computed as `fp.position + R(-θ)·center_offset` at `_parse_modules.py:153-156`); `CpSatPlacementResult.positions` (`placer/cp_sat/_encoder_solve.py:42`); `ComponentVars.x_center/y_center` (documented in `placer/cp_sat/domain_clearance.py:47-48`) | This is the frame CP-SAT solves in and the frame `_copper.py`'s safety validator measures in. It is **not** the same point as F1 whenever a component's pad centroid isn't at its KiCad anchor. |
| F5 | **Board/world absolute pad-copper frame** | Resolved pad centers post rotation+translation: `_Pad.cx/cy` (`requirements/validators/_copper.py:120-121`); `PadData.position` (`_parse_modules.py:200-204`) | What the REQ-SAFE-01 clearance/creepage check actually measures between. |
| F6 | **Grid/occupancy cell frame** | Declared (but see below) in `core/units.py:56-116` (`Millimeters`, `CellIndex`, `mm_to_cell`/`cell_to_mm`); the *actual* mm↔cell conversions used at runtime are separately hand-rolled: `deterministic/stages/_grid_core.py:199 _mm_to_cell`, `router_v6/bottleneck_geometry.py:356 _mm_to_cell`, `pipeline/feedback.py:76-77` (`gx = (positions[:, 0] - origin[0]) / cell_size`) | See "A precedent that already exists — and already failed" below. This is the frame the task brief's "grid/occupancy cells are plausible" guess was pointing at; it is real, but the type system built for it is not load-bearing today. |

F2 and F3 are easy to conflate: F3 is the *vector between* F1 and the origin F2 is measured
from. `_calculate_footprint_bounds` (`io/_parse_modules.py:285-371`, the #460 bug) computes
its bounding box from `pad.position.X/Y` and graphic-item coordinates, which are in the
**raw F1-anchor frame** (`hw = max(abs(x_min), abs(x_max))` at line 357-358 and line
367-368 assumes the anchor sits at the box's center — i.e., assumes F3 is zero). That
assumption is false whenever a footprint's pads aren't centered on its KiCad anchor, which
is common for asymmetric parts (TO-247s, connectors). The resulting `(width, height)`
becomes `Component.bounds`, which CP-SAT sizes its placement box from, centered at
`Component.initial_position` — an **F4** point. The box is therefore sized in F1 but
centered in F4: exactly the "box computed in anchor frame, used in centroid frame" bug
named in the dispatching brief. This is confirmed still open, not yet on `main`: PR #460
(`fix/domain-clearance-copper-aware`) is the fix, and `docs/evidence/2026-07-30-placement-writer-rotation.md`
§3.2 reproduces its reported regression directly against `main`'s current
`_calculate_footprint_bounds`.

### What already exists, and where the four bugs actually sit today

- **#412/#420/#426 (pad bodies not rotated with footprint): fixed on `main`.**
  `io/_write_board.py::_reorient_pads` (lines 23-56) rewrites every pad's absolute angle by
  the same delta as the footprint's rotation, because — its own docstring explains — a
  `.kicad_pcb` pad angle is **absolute**, not additive to the parent footprint's. KiCad
  auto-transforms a pad's F2 *position* when the footprint rotates (that part was always
  correct), but never its *orientation* — that's a second, independent transform that has to
  be applied explicitly. This is why the fix reads as "call the missing function," not "fix
  a frame mismatch": the position and orientation of a rotated part are two different
  quantities that happen to share one rotation angle, and only one of them auto-propagates
  through KiCad's own semantics.
- **#460 (`_calculate_footprint_bounds`, anchor vs. centroid frame): still open.** See above.
  Not yet merged to `main` as of this plan (PR #460, branch
  `fix/domain-clearance-copper-aware`).
- **#471 (`_apply_placements_to_pcb` dropping rotation): fixed on `main`, but inert, and
  entangled with a second, still-open frame bug.** `router_v6/_adapter_convert.py:786-798`
  now accepts an optional `rotations: dict[str, float] | None = None` and applies it
  (`docs/evidence/2026-07-30-placement-writer-rotation.md` §1). But: (a) **no caller passes
  it** — `route_pcb`, `_loop_routing.py`, and both golden-board regression tests all still
  call the affected functions without `rotations=`, so the fix is capability-only, not
  wired on (§5 of the same evidence doc); and (b) applying it exposes a **second, entangled,
  still-open bug** — `_apply_placements_to_pcb`'s callers never do the F4→F1 `center_offset`
  conversion that `write_placements_to_pcb` already performs (`_write_board.py:130-143`,
  "Convert from bounding-box-center to footprint-origin coordinates"). Measured directly
  (§3.2, §4 of the evidence doc): applying the rotation fix on top of the still-wrong
  position makes the golden-board DRC regression *worse* (`shorting_items` 1→4,
  `placement_fixable` 10→16, newly over the test's own gate), not better. This is the
  clearest empirical demonstration in this codebase that fixing one frame conversion while
  leaving an adjacent one wrong doesn't partially help — it can actively hurt.
- **#479 (R(+θ) vs. R(−θ)): fixed on `main` across 12 sites**, commit `0a8e7194`. Full list
  in the commit message; the two most relevant to this plan's scope are
  `io/_parse_modules.py` (F1→F4 center-offset rotation) and
  `core/pin_geometry.py::pin_world_position_at` (F2→F5, "the canonical...single source of
  truth for all pad-position computation" per its own module docstring, line 8).

### The already-correctly-shaped `Placement` building block (R3)

`io/_write_types.py:42-56` already defines:

```python
@dataclass
class PlacementUpdate:
    ref: str
    x: float
    y: float
    rotation: float  # degrees: 0, 90, 180, or 270
```

— position and orientation as one inseparable value, which is exactly what R3 asks for.
`write_placements_to_pcb` (`io/_write_board.py:59-96`) already consumes it. But it is not
used anywhere else: `CpSatPlacementResult` (`placer/cp_sat/_encoder_solve.py:34-76`) instead
carries `positions: dict[str, tuple[float, float]]` and `rotations: dict[str, int]` as two
independently-optional collections, bridged by `to_placements_dict()` (line 59) and
`to_rotations_dict()` (line 63) — two accessor methods that exist specifically to paper over
the fact that the underlying data isn't unified. `_apply_placements_to_pcb`/`route_pcb`
(`router_v6/_adapter_convert.py:167-198, 786-798`) take the same split shape:
`placements: dict[str, tuple[float, float]]` plus an independently-optional
`rotations: dict[str, float] | None = None`. This split-and-optional shape is structurally
*why* #471 was possible: nothing forced a caller who had a rotation to actually pass it.

`placer/cp_sat` does not currently import `io` at all (verified: no
`from temper_placer.io` / `import temper_placer.io` anywhere under
`placer/cp_sat/*.py`), so a shared `Placement` type usable by both `CpSatPlacementResult`
(in `placer/cp_sat`) and `write_placements_to_pcb` (in `io`) cannot live in
`io/_write_types.py` as-is without creating a new cross-package dependency. `core/` is the
correct home — it already hosts `geometry_types.py`, `units.py`, `pin_geometry.py`, and
`netlist.py`, and the import-linter contract (`.importlinter:13-20`) already establishes
`core` as the dependency-free leaf both `placer/cp_sat` and `io` may import from.

### A precedent that already exists — and already failed (R5, R7)

`core/units.py` (lines 1-20) is, in miniature, exactly the pattern this plan proposes for
coordinate frames — but for *units* instead of *frames*:

```python
"""
This module provides NewType wrappers for common physical units to prevent bugs...
Using NewType provides compile-time type checking with zero runtime overhead.

Example of bug prevented by type system:
    # Before (bug):
    cell_x = int(x_mm / cell_size)
    grid.is_available(cell_x, cell_y)  # WRONG! is_available expects mm, not cell index
    # After (type-safe):
    cell_x = mm_to_cell(Millimeters(x_mm), Millimeters(cell_size))
```

`Millimeters`, `CellIndex`, `mm_to_cell`, `cell_to_mm` are real, tested, re-exported from
`core/__init__.py` (verified: `core/__init__.py:82` imports them) — and **not used by a
single real mm↔cell conversion anywhere in the codebase.** The actual runtime conversions
are separately hand-rolled with plain `float`/`int`:
`deterministic/stages/_grid_core.py:199 def _mm_to_cell(self, x_mm: float, y_mm: float) -> tuple[int, int]`
and `router_v6/bottleneck_geometry.py:356 def _mm_to_cell(grid, x_mm: float, y_mm: float) -> tuple[int, int]`
never call `core.units.mm_to_cell` at all. This is the F6 frame from the table above, and
it is a real, already-shipped, in-this-repo instance of exactly the failure mode this
plan's user brief warns about — a gate that exists but never fired, of the same species the
project has already documented four times (per this project's own retrospective habit — see
project memory on new-error-class response). It is directly relevant evidence for how much
migration follow-through this plan's own units need, not just how they should be typed —
see Key Technical Decisions and Implementation Units U1-U6.

### Would `mypy` actually enforce this today? (R5)

Empirically tested, not assumed. The CI gate (`scripts/check_typecheck_gate.py`, invoked at
`.github/workflows/python-tests.yml:2662` with **no** `working-directory:` override, i.e.
from the repo root) runs `uv run mypy <scope> --ignore-missing-imports` from the repo root.
mypy resolves its config from the **root** `pyproject.toml`'s `[tool.mypy]`
(`pyproject.toml:83-90`) when invoked this way — not
`packages/temper-placer/pyproject.toml`'s `[tool.mypy]` (`packages/temper-placer/pyproject.toml:148-157`),
even though the scanned files live under `packages/temper-placer/src`. The two configs
differ materially: the package-level config sets `disallow_untyped_defs = true` and
`check_untyped_defs = true`; the root config the CI gate actually uses sets **neither**.

Verified with a scratch probe (two functions, one unannotated with a type error in its body,
one fully annotated with the same class of error), run both ways:

- From the repo root (root `pyproject.toml`, what CI actually runs): the unannotated
  function's error is **silently skipped** — mypy emits
  `note: By default the bodies of untyped functions are not checked, consider using
  --check-untyped-defs [annotation-unchecked]` and reports nothing for that line. The fully
  annotated function's error is still caught.
- From `packages/temper-placer/` (its own stricter `pyproject.toml`): both errors are caught.
- Quantified across the real codebase: `mypy packages/temper-placer/src --ignore-missing-imports`
  (root config, matches CI exactly) reports **220 errors in 37 files** — matching
  `.typecheck-allowlist`'s own header exactly, confirming this is precisely what the gate
  runs. Adding `--check-untyped-defs` (the package's own declared strictness) raises that to
  **237 errors in 43 files** — 17 more errors the gate is not currently catching purely
  because of this config mismatch, not because the code is correct.

**The honest conclusion: partially decorative, but not where it matters most for this
plan.** All functions actually implicated in the four historical bugs
(`_extract_components_from_pcb`, `_calculate_footprint_bounds` in `_parse_modules.py`;
`route_pcb`, `_apply_placements_to_pcb` in `_adapter_convert.py`; every function in
`domain_clearance.py`; every function in `_copper.py`) already carry full parameter and
return annotations (verified by grep — zero unannotated `def`s in any of the four target
files). Because mypy only skips *unannotated* function bodies, a phantom-frame retrofit on
these specific, already-fully-typed functions **would** be checked under the CI gate exactly
as it runs today — this is not the `core/units.py` failure mode. The 17-error,
6-file gap that `--check-untyped-defs` would newly surface is real, but it sits elsewhere in
the codebase, not in this plan's target files. U7 proposes closing that gap anyway, both
because it's a genuine, cheap-to-fix inconsistency between a declared and an enforced
strictness level, and because it removes the one condition under which a *future* addition
to these same files could silently regress to unchecked.

---

## Key Technical Decisions

- **Do not extend phantom frame types into the `dict[str, Any]` placement-blob consumers
  (`_copper.py`, `domain_clearance.py`) as part of this migration.** Both files' entry
  points (`_component_pads(comp: dict[str, Any])`, `generate_domain_clearance_constraints(
  placement: dict[str, Any], ...)`) operate on an ad hoc, JSON-shaped "placement" dict, not
  on `Point`/`Pin`/`Component` dataclasses at all. `comp["position"]`,
  `p.get("offset", (0.0, 0.0))`, `placement["board"]["surface_cutouts"]` are all `Any`-typed
  reads from a nested dict — phantom types on `tuple[float, float]` have literally nothing
  to attach to here without first replacing the dict with a typed schema. That replacement
  is a materially larger, separate architectural decision: `domain_clearance.py`'s own
  module docstring already flags that it imports across the `src`→`tests` boundary
  ("architecturally unusual... called out plainly") specifically to share this dict-shaped
  representation with the test-tree validator it must stay consistent with; a typed
  replacement would need to cross that same unusual boundary, plus decide how the dict's
  JSON/serialization role (this shape appears to be built for and possibly serialized
  across a process or fixture boundary, not just passed in-process) survives typing. This
  is exactly the kind of scope this plan's own brief asked to flag rather than pad out:
  **recommended against, for now** — a future plan can pick it up once/if the core-geometry
  migration (U1-U6) has demonstrated real value.
- **Start at `core/pin_geometry.py`, not at `Pin`/`Component`'s own fields.** The module
  already documents itself as "the canonical...single source of truth for all pad-position
  computation" (`pin_geometry.py:8`). Retyping its three functions first (U2) is the
  smallest possible change that exercises the phantom-type mechanism against real call
  sites, before committing to retyping the much more widely-used `Pin.position` /
  `Component.initial_position` fields themselves (U3).
- **`core/units.py`'s dead `Millimeters`/`CellIndex` precedent is a warning, not a
  counter-argument.** It shows phantom types decay to decoration specifically when they are
  added *without* migrating the call sites they were meant to protect. This plan's
  Implementation Units are therefore each scoped to include the call-site migration, not
  just the type definition — U1 (types only, explicitly inert) is the one exception, and it
  is scoped that way deliberately as the smallest possible first PR, with U2 landing in the
  same work session or immediately after so the type never sits unused the way
  `core/units.py`'s has.
- **This plan is complementary to, not a replacement for, the `pcbnew` differential oracle
  and the single-transform lint in flight on PR #479's stack.** See "What This Does Not
  Catch" below — phantom types cannot catch a wrong constant inside a correctly-shaped
  signature, which is exactly what #479 was.

---

## Open Questions

### Resolved During Planning

- **Would the CI gate enforce phantom types on the target files, or are they decorative?**
  Resolved empirically (see Context & Research): not decorative for the four historically-
  buggy files specifically, because they are already fully annotated; the gate's
  root/package config mismatch is real but affects a different, smaller slice of the
  codebase (17 errors, 6 files, quantified above).
- **Does `CpSatPlacementResult` already have the right shape?** No — `PlacementUpdate`
  (`io/_write_types.py`) does; `CpSatPlacementResult` still splits position and rotation
  into two independently-optional collections. U5 migrates it.

### Deferred to Implementation

- **Exact `Point[Frame]` implementation mechanics** (a `Generic[F]` frozen dataclass with a
  phantom `TypeVar` bound to marker classes `Local`/`World`/`Anchor`/`Centroid`, vs. a
  simpler `NewType`-per-frame scheme matching `core/units.py`'s existing style) — a
  judgment call best made with the actual mypy version and its `Generic`+`frozen=True`
  dataclass interaction in front of the implementer (U1).
- **Whether F3 (the anchor→centroid `center_offset`) needs its own promoted dataclass field
  or can stay a derived quantity** computed on demand from F1 and F2 — U3/U4's execution
  should settle this once the parser code is actually being touched; this plan does not
  presume the answer.
- **Whether PR #460 lands before or after this plan's U4** — they touch the same function
  (`_calculate_footprint_bounds`). If #460 merges first, U4 becomes "retype the fixed
  function"; if this plan's U4 lands first, #460 should rebase onto the typed signature. Not
  a blocker either direction, but whichever lands second should explicitly check for this.

---

## High-Level Technical Design

> This illustrates the intended approach and is directional guidance for review, not
> implementation specification. The implementing agent should treat it as context, not code
> to reproduce.

```python
# core/geometry_types.py (illustrative -- not a spec)

class Local:      # marker type, never instantiated
    ...
class World:       # marker type, never instantiated
    ...

F = TypeVar("F")

@dataclass(frozen=True)
class Point(Generic[F]):
    x: float
    y: float
    # No frame-conversion arithmetic lives here. The only sanctioned route
    # between frames is a named transform function (see pin_geometry.py),
    # never `+`/`-` on two Points of different frames -- that's the whole point.

# core/pin_geometry.py (illustrative signature change)
def pin_world_position(pin: "Pin", comp: "Component") -> Point[World]:
    ...  # pin.position: Point[Local], comp.initial_position: Point[World]

# core/placement_types.py (illustrative -- promotes io/_write_types.PlacementUpdate)
@dataclass(frozen=True)
class Placement:
    ref: str
    position: Point[World]
    rotation_deg: float   # no longer a separately-optional dict entry
```

The key discipline this buys: `Point[Local] + Point[World]` (or any bare arithmetic mixing
frames) is a `mypy` error under `--strict`-adjacent settings, because `Point[F]` for two
different `F` are different, incompatible generic instantiations. The *only* way to go from
`Point[Local]` to `Point[World]` becomes calling a named transform function — which is
exactly `pin_world_position`, already the single documented chokepoint.

---

## Implementation Units

### U1. Add `Point[Frame]` phantom type to `core/geometry_types.py`, additive only

**Goal:** Introduce the generic `Point[F]` type and `Local`/`World`/`Anchor`/`Centroid`
marker types (exact marker set decided at implementation time per Open Questions) in
`core/geometry_types.py`, alongside the existing frame-agnostic `Point` dataclass (which
stays, unchanged, for callers not yet migrated — e.g. `Track`/`Via`/`Pad` in the same file,
which are out of scope for this plan).

**Requirements:** R2

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/core/geometry_types.py`
- Test: `packages/temper-placer/tests/core/test_geometry_types.py` (new or existing,
  whichever the implementer finds)

**Approach:**
- Zero existing call sites change. This unit exists purely to prove the phantom-type
  mechanism type-checks cleanly (`Generic` + `frozen=True` dataclass) before any real code
  depends on it.
- Explicitly time-boxed to land together with or immediately before U2 — per Key Technical
  Decisions, an unused phantom type is exactly the `core/units.py` failure mode this plan
  names as a precedent risk.

**Test scenarios:**
- Happy path: `Point[World](1.0, 2.0)` and `Point[Local](1.0, 2.0)` both construct and
  compare correctly for equality within the same frame.
- Error path (type-check only, not a runtime test): a snippet assigning `Point[Local]` to a
  variable annotated `Point[World]` is confirmed to fail `mypy` (captured as a `# type:
  ignore`-free negative-compile fixture, or documented manual verification — implementer's
  judgment on the cheapest reliable mechanism).

**Verification:**
- `mypy` passes on `core/geometry_types.py` with no new allowlist entries needed.
- Existing tests referencing the frame-agnostic `Point` are unaffected.

---

### U2. Retype `core/pin_geometry.py`'s transform functions

**Goal:** Change `pin_world_position`, `pin_world_position_at`, and `pin_world_radius`
(`core/pin_geometry.py:34-` through `:116-`) to accept/return `Point[Local]`/`Point[World]`
instead of bare `tuple[float, float]`, since this module is already the documented single
chokepoint for local→world pad-position math.

**Requirements:** R2

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/core/pin_geometry.py`
- Test: `packages/temper-placer/tests/core/test_pin_geometry.py` (existing — extend)

**Approach:**
- `pin: Pin` and `comp: Component` still carry plain `tuple[float, float]` fields at this
  stage (U3 migrates those) — so this unit's function bodies construct
  `Point[Local](*pin.position)` / `Point[World](*comp.initial_position)` internally and
  return a `Point[World]`. Callers of `pin_world_position` that expect a bare tuple get a
  `Point[World]` back; the implementer should decide whether to add a thin
  `.as_tuple()` compatibility method on `Point` so this unit does not force every caller of
  `pin_world_position` to migrate in the same PR (recommended, to keep this unit's blast
  radius small and behavior-preserving).
- **Execution note:** Characterization-first. Before changing the signatures, capture the
  current numeric output of `pin_world_position`/`pin_world_position_at` for a representative
  set of (pin, component) pairs (including at least one non-zero-rotation, non-zero-center-
  offset case, given #479's history in exactly this function) and assert the retyped version
  produces byte-identical floats.

**Test scenarios:**
- Happy path: existing `test_pin_geometry.py` cases pass unchanged in value, now returning
  `Point[World]` (via `.as_tuple() == (expected_x, expected_y)` or equivalent).
- Edge case: a pin at a non-zero rotation index and a component with `initial_rotation`
  covering all four quadrants (0/90/180/270) — this is exactly where #479 lived.
- Integration: a caller elsewhere in the codebase (e.g. `router_v6` or `validation`,
  whichever currently calls `pin_world_position`) still compiles and passes without
  modification, proving the compatibility shim holds.

**Verification:**
- `mypy` passes with no new allowlist entries.
- Every existing caller of the three retyped functions either compiles unchanged (via the
  compatibility shim) or is updated in this same unit if the shim proves impractical.

---

### U3. Migrate `Pin.position` and `Component.initial_position` field types

**Goal:** Change `core/netlist.py::Pin.position` to `Point[Local]` and
`Component.initial_position`/`bounds` to `Point[World]` (position) and a still-plain
`tuple[float, float]` (bounds, which is a size, not a point — not in scope for frame typing).

**Requirements:** R2

**Dependencies:** U2

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/core/netlist.py`
- Modify: `packages/temper-placer/src/temper_placer/io/_parse_modules.py` (the constructor
  call sites: `_extract_components_from_pcb`, `Pin(...)` construction)
- Test: `packages/temper-placer/tests/core/test_netlist.py`,
  `packages/temper-placer/tests/io/test_parse_modules.py` (existing — extend)

**Approach:**
- This is the unit where the type system starts actually constraining real construction
  code, not just the one already-typed transform module. Expect this to surface every place
  that currently does arithmetic directly on `Pin.position`/`Component.initial_position`
  outside `pin_geometry.py` — each such site either needs to route through a sanctioned
  transform or gets an explicit `.as_tuple()` escape hatch, decided case by case.
- **Execution note:** Characterization-first, same rationale as U2 — golden values before
  retyping, not after.

**Test scenarios:**
- Happy path: constructing a `Component`/`Pin` from a real parsed footprint (use an existing
  fixture from `test_parse_modules.py`) produces the same numeric values as before, now
  frame-typed.
- Integration: the golden-board regression tests
  (`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`) still pass —
  this is the load-bearing check that the retype changed no runtime behavior.

**Verification:**
- `mypy` passes with no new allowlist entries (or newly-justified ones, reviewed
  individually).
- `test_regression_drc.py`'s golden-board tests are unchanged in outcome.

---

### U4. Retype `_calculate_footprint_bounds` and the `center_offset` computation

**Goal:** Make the F1 (anchor) vs. F3 (anchor→centroid offset) distinction explicit in
`io/_parse_modules.py:109-114, 285-371`, so the box-in-anchor-frame /
centered-at-centroid-frame mismatch behind #460 becomes a signature-level type mismatch
rather than a silent numeric one — coordinating with PR #460 per the Open Questions note
above (whichever change lands second rebases onto the other).

**Requirements:** R2, R6

**Dependencies:** U3

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/io/_parse_modules.py`
- Test: `packages/temper-placer/tests/io/test_parse_modules.py` (existing — extend with an
  asymmetric-footprint case, i.e. non-zero `center_offset`)

**Approach:**
- Introduce (or coordinate with #460's own introduction of) an explicit typed
  `center_offset: Point[???]` representation — this plan does not presume whether that ends
  up a fifth marker frame or a plain `(dx, dy)` vector type (a vector isn't a point in the
  affine-geometry sense; conflating the two is itself a frame-adjacent bug class, worth the
  implementer's attention here) — replacing the current `Component.attributes["_center_offset_x"]`
  stringified-dict representation (`_parse_modules.py:161-171`) with a real field, since a
  string-keyed `dict[str, str]` cannot be phantom-typed at all.
- **Execution note:** This unit's test scenario for the asymmetric-footprint case is the
  regression test that would have caught #460 directly — write it whether or not #460 has
  already merged, since if #460 merges first this becomes the characterization test proving
  U4's retype preserves its fix.

**Test scenarios:**
- Happy path: a symmetric footprint (`center_offset == (0, 0)`) — bounds computation
  unchanged from today.
- Edge case: an asymmetric footprint (e.g. a synthesized 3-pad TO-247-shaped fixture with
  pads at local x = 0/5.45/10.9, matching the real `Q2` case measured in
  `docs/evidence/2026-07-30-placement-writer-rotation.md` §4) — bounds are computed
  correctly relative to the centroid, not the raw anchor.
- Integration: `Component.bounds` feeding into `CpSatModel`'s placement-box sizing
  (`placer/cp_sat/model.py`, wherever it consumes `Component.bounds`) produces a box that
  actually contains the footprint's real extent for the asymmetric case.

**Verification:**
- `mypy` passes.
- New asymmetric-footprint test fails on the pre-U4 code and passes after — direct proof
  this unit fixes (or preserves #460's fix of) the anchor/centroid frame mismatch.

---

### U5. Unify `CpSatPlacementResult` on a shared `Placement` type

**Goal:** Promote `io/_write_types.py::PlacementUpdate`'s shape (ref + position + rotation
as one inseparable value) into a `core`-hosted `Placement` type (see High-Level Technical
Design), and migrate `CpSatPlacementResult.positions`/`rotations`
(`placer/cp_sat/_encoder_solve.py:42-43`) to a single `placements: dict[str, Placement]`
field. Migrate `_apply_placements_to_pcb`/`route_pcb`
(`router_v6/_adapter_convert.py:167-198, 786-798`) to accept `placements: dict[str,
Placement]` instead of the current split `placements: dict[str, tuple[float, float]]` +
optional `rotations: dict[str, float] | None`.

**Requirements:** R3

**Dependencies:** U1 (for `Point[World]`, used inside `Placement`)

**Files:**
- Create: `packages/temper-placer/src/temper_placer/core/placement_types.py` (or add to
  `core/geometry_types.py` if the implementer judges that a better fit)
- Modify: `packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py`
- Modify: `packages/temper-placer/src/temper_placer/cli/__init__.py` (the
  `cp_result.rotations.get(ref, 0) * 90.0` call site at line 628, which
  `to_rotations_dict()` was introduced specifically to deduplicate — this becomes direct
  field access on `Placement` instead)
- Modify: `packages/temper-placer/src/temper_placer/placer/cp_sat/_loop_routing.py` (calls
  `to_placements_dict()` at lines 135, 189)
- Test: `packages/temper-placer/tests/router_v6/test_adapter.py` (existing
  `TestApplyPlacementsToPcbRotation` suite — update signatures, keep assertions),
  `packages/temper-placer/tests/placer/cp_sat/test_encoder_solve.py` (existing — extend)

**Approach:**
- `to_placements_dict()`/`to_rotations_dict()` become unnecessary — direct field access on
  `Placement` replaces both — but consider keeping thin deprecated wrappers for one release
  if external callers beyond this repo's own tree are a concern (unlikely for an internal
  tool; implementer's call).
- This is the unit that makes R3's core claim true: a caller can no longer construct a valid
  `placements` argument without supplying a rotation, because `Placement` has no
  rotation-optional shape the way the current split dict does.
- **Execution note:** Test-first for the signature change itself — write the failing test
  asserting `_apply_placements_to_pcb` requires (not merely accepts) a rotation per
  `Placement`, mirroring how `TestApplyPlacementsToPcbRotation`'s 7 existing cases already
  test the optional-rotations behavior; this unit's job is to make "no rotation supplied"
  impossible to represent, not just tested.

**Test scenarios:**
- Happy path: solving a placement, converting to `Placement` values, and writing them via
  `_apply_placements_to_pcb` reproduces the exact same output as today's
  `positions`+`rotations` path, for a case with non-trivial rotation.
- Edge case: a component the solver did not rotate (rotation index 0) — `Placement.rotation_deg
  == 0.0` round-trips correctly (matching the existing "omit angle token when it normalizes
  to 0" convention in `_reorient_pads_in_footprint_block`).
- Error path: attempting to construct a `dict[str, Placement]` with a ref missing from the
  positions half of today's split representation is no longer expressible as a partial
  state — verify by type inspection / a compile-time check, not a runtime test, since the
  whole point is this state becomes unrepresentable.
- Integration: `_loop_routing.py`'s two `to_placements_dict()` call sites (lines 135, 189)
  still produce a routable board after migrating to direct `Placement` field access.

**Verification:**
- `mypy` passes.
- `test_golden_board_drc_regression` and `test_regression_drc.py`'s other golden-board
  tests are unchanged in outcome (this unit changes representation, not behavior — callers
  still don't pass rotation through by default unless a separate follow-up wires it on,
  matching the existing, deliberate, evidence-documented decision not to wire it on yet).

---

### U6. Migrate `write_placements_to_pcb` onto the shared `Placement` type

**Goal:** Replace `io/_write_types.py::PlacementUpdate` with the `core`-hosted `Placement`
from U5 (or make `PlacementUpdate` a thin alias, implementer's call), so both writer entry
points (`write_placements_to_pcb` and `_apply_placements_to_pcb`) consume the identical type.

**Requirements:** R3

**Dependencies:** U5

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/io/_write_types.py`
- Modify: `packages/temper-placer/src/temper_placer/io/_write_board.py`
- Test: `packages/temper-placer/tests/io/test_write_board.py` (existing — extend)

**Approach:**
- Mechanical once U5 lands: `PlacementUpdate`'s fields already match `Placement`'s shape
  exactly (`ref`, `x`/`y` → `position: Point[World]`, `rotation` → `rotation_deg`).

**Test scenarios:**
- Happy path: `write_placements_to_pcb` with a `Placement`-keyed dict produces byte-identical
  `.kicad_pcb` output to today's `PlacementUpdate`-keyed call, for the existing test fixture
  set.
- Test expectation: none beyond the above — this unit is a pure rename/unification with no
  new behavior.

**Verification:**
- `mypy` passes.
- `test_write_board.py` passes unchanged in assertions.

---

### U7. Close the type-check gate's config gap

**Goal:** Make `scripts/check_typecheck_gate.py` actually run with the strictness
`packages/temper-placer/pyproject.toml` declares (`disallow_untyped_defs`,
`check_untyped_defs`), so the R5 finding's 17-error/6-file gap closes and this migration's
new phantom types (and any future ones) can't quietly regress to unchecked the way
`core/units.py`'s did.

**Requirements:** R5, R7

**Dependencies:** None (independently mergeable at any point; not gated on U1-U6)

**Files:**
- Modify: `scripts/check_typecheck_gate.py` (point its `mypy` invocation at the package
  config explicitly, e.g. `--config-file packages/temper-placer/pyproject.toml`, or run it
  with `working-directory: packages/temper-placer` to match how every other strict-config
  step in `.github/workflows/python-tests.yml` already does — 9 other steps in that file use
  exactly this pattern)
- Modify: `.typecheck-allowlist` (the 17 newly-surfaced errors need allowlist entries or
  fixes — implementer's judgment per the monotonic-shrink convention already documented in
  `AGENTS.md`)

**Approach:**
- **Execution note:** Run `--check-untyped-defs` locally first to get the exact 17-error
  list before touching the gate script, so the allowlist update in this unit is informed by
  real output, not a guess.

**Test scenarios:**
- Happy path: `scripts/check_typecheck_gate.py --init` regenerates `.typecheck-allowlist`
  and the new total matches the 237-errors/43-files figure measured in this plan's Context &
  Research (or a lower number, if some are fixed rather than allowlisted).
- Verification: CI's `type-check` job passes on a branch with no other changes, proving the
  config-parity fix alone doesn't newly fail the build once the allowlist accounts for it.

**Verification:**
- `check_typecheck_gate.py` (default mode) now reports the same count whether run from the
  repo root or from `packages/temper-placer/`.

---

## System-Wide Impact

- **Interaction graph:** `pin_geometry.py` (U2) is imported broadly across `router_v6`,
  `validation`, and `deterministic` — its retype has the widest blast radius of any single
  unit, mitigated by the `.as_tuple()` compatibility shim strategy. `CpSatPlacementResult`
  (U5) is read by `placer/cp_sat/_loop_routing.py`, `cli/__init__.py`, and the place→route
  feedback loop; all three are named as explicit file touches in U5 rather than left
  implicit.
- **Error propagation:** None of these units change runtime error behavior — every one is
  scoped as behavior-preserving, proven via characterization tests captured before each
  retype (see each unit's Execution note) and the golden-board DRC regression suite, which
  is the project's existing standing mechanism for catching exactly this class of
  regression.
- **State lifecycle risks:** None identified — no persistent state, caching, or async
  lifecycle is touched by any unit.
- **API surface parity:** `_apply_placements_to_pcb` and `write_placements_to_pcb` (U5, U6)
  become symmetric in their placement type after this migration, which they are not today —
  this is itself one of R3's goals, not an incidental side effect.
- **Integration coverage:** The golden-board regression tests
  (`test_golden_board_drc_regression`, `test_golden_board_routing_drc_regression`) are the
  one cross-layer check that unit tests alone won't substitute for — every unit that touches
  a construction or writer path (U3-U6) should be run against them, not just its own local
  test file.
- **Unchanged invariants:** This plan does not change whether `_apply_placements_to_pcb`'s
  rotation-application is wired on by default (it explicitly is not, today, per the
  evidence doc's measured finding that doing so currently worsens DRC via the still-open
  center_offset gap) — U5 changes the *representation* callers use, not the decision of
  which callers pass a real rotation. Wiring rotation on by default remains gated on fixing
  the center_offset conversion in `_apply_placements_to_pcb`'s callers, which is out of this
  plan's scope (it's the same architectural follow-up the evidence doc already names, R22
  in `AGENTS.md`'s terms).

---

## What This Plan Does Not Catch (R6)

Types constrain shape, not value. Two of the four motivating bugs were not shape errors:

- **#479 (R(+θ) vs. R(−θ)):** `_rotate(x: float, y: float, theta_rad: float) -> tuple[float,
  float]` (`requirements/validators/_copper.py:72-94`) had a completely correct,
  narrow signature both before and after the fix — the bug was a sign flip inside
  correctly-typed trigonometry. `Point[Local]` in, `Point[World]` out would type-check
  identically whether the implementation used `+θ` or `−θ`. This is exactly why the
  dispatching brief frames this plan as complementary to, not a replacement for, the
  `pcbnew` differential oracle (which checks against KiCad's own real behavior, not a
  self-consistent type signature) and the single-transform lint (which can enforce "call
  the one sanctioned function" but not "the sanctioned function computes the right
  constant").
- **#412/#420/#426 (pad bodies not rotated with footprint):** the defect was a missing
  function call (`_reorient_pads` not yet existing/not yet called), not a type mismatch —
  `fp.position.angle` and each pad's own `.position.angle` were always both plainly `float`,
  never confused for a different frame. A `Placement` type unifying position+rotation (U5)
  addresses the *adjacent* problem of a rotation being droppable from a placement *result*;
  it does not, by itself, guarantee every consumer of that rotation (like a footprint's pad
  bodies) actually applies it everywhere it must.

What this plan's units *do* directly address: #460 (U4, a genuine frame mismatch) and #471
(U5, a genuine "rotation optional-and-droppable" type shape). That is two of four — stated
plainly, not rounded up.

---

## Risks & Dependencies

| Risk | Mitigation |
|---|---|
| `pin_geometry.py`'s wide fan-in (U2) causes a large, hard-to-review diff if the compatibility shim is skipped | Keep `.as_tuple()` escape hatch mandatory for U2; do not force caller migration in the same unit |
| Phantom types added but call sites never migrated (the `core/units.py` precedent) | U1 is explicitly time-boxed to land with/immediately before U2; no unit in this plan adds a frame type without also migrating at least one real call site in the same or the very next unit |
| U4 and PR #460 touch the same function and could conflict | Explicitly named in Open Questions; whichever lands second rebases; not a blocker either direction |
| Wiring `_apply_placements_to_pcb`'s rotation on by default (a temptation once U5 makes it "the obvious next step") worsens DRC, per the evidence doc's own measurement | Explicitly out of scope (System-Wide Impact, "Unchanged invariants") — U5 changes representation only, not the wire-on decision, which is gated on the separate center_offset architectural fix |
| U7's `--check-untyped-defs` surfaces 17 new errors that could block CI if landed without allowlisting | U7's own test scenario requires running `--init` and confirming the count before the gate change merges |
| Extending this migration's spirit into `_copper.py`/`domain_clearance.py` looks like an obvious "finish the job" next step but is a much larger typed-schema migration | Explicitly recommended against in Key Technical Decisions, with the specific architectural reason (the `dict[str, Any]` blob crosses a `src`→`tests` import boundary this repo already flags as unusual) |

---

## Documentation / Operational Notes

- `core/pin_geometry.py`'s module docstring already claims canonical status; once U2 lands,
  its docstring should be updated to state that it is now also the sole sanctioned
  frame-conversion boundary, not just the sole position-math implementation — small wording
  addition, not a new claim.
- If U7 lands, `AGENTS.md`'s existing type-check gate documentation (none currently
  describes `scripts/check_typecheck_gate.py`'s config resolution) would benefit from a
  short note explaining the root-vs-package config distinction this plan's research
  surfaced, so a future contributor doesn't have to re-derive it empirically.

---

## Sources & References

- `packages/temper-placer/src/temper_placer/core/geometry_types.py` — frame-agnostic
  `Point`, target for U1.
- `packages/temper-placer/src/temper_placer/core/pin_geometry.py` — canonical transform
  function, target for U2.
- `packages/temper-placer/src/temper_placer/core/netlist.py` — `Pin`, `Component`, target
  for U3.
- `packages/temper-placer/src/temper_placer/core/units.py` — the dead `Millimeters`/
  `CellIndex` precedent cited throughout.
- `packages/temper-placer/src/temper_placer/io/_parse_modules.py` — `_calculate_footprint_bounds`
  (#460), `_extract_components_from_pcb`.
- `packages/temper-placer/src/temper_placer/io/_write_board.py` — `write_placements_to_pcb`,
  `_reorient_pads` (#412/#420/#426 fix).
- `packages/temper-placer/src/temper_placer/io/_write_types.py` — `PlacementUpdate`.
- `packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py` —
  `_apply_placements_to_pcb`, `route_pcb` (#471).
- `packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py` —
  `CpSatPlacementResult`.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py` — CP-SAT
  box-center frame, `dict[str, Any]` placement blob.
- `packages/temper-placer/src/temper_placer/requirements/validators/_copper.py` — `_rotate`
  (#479), `dict[str, Any]` placement blob.
- `scripts/check_typecheck_gate.py`, `.typecheck-allowlist`, `pyproject.toml`,
  `packages/temper-placer/pyproject.toml`, `.github/workflows/python-tests.yml` — the mypy
  enforcement investigation (R5).
- `.importlinter` — `core`/`router_v6` boundary contract informing U5's type placement.
- `docs/evidence/2026-07-30-placement-writer-rotation.md` — #471's fix, measurement, and the
  entangled center_offset bug.
- `docs/evidence/2026-07-29-intra-component-shorts-root-cause.md`,
  `docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md` — #412 and #479's
  root-cause documentation.
- Commit `0a8e7194` — #479's 12-site fix list.
- Commits `2382e168`, `771ac3ea`, `459472aa` — #412/#420/#426.
- Commits `b21110ab`/`27bc79bc` — #471.
- PR #460 (branch `fix/domain-clearance-copper-aware`, open as of this plan) —
  `_calculate_footprint_bounds`'s fix, referenced but not merged.
- `docs/plans/2026-07-28-002-fix-pad-geometry-model-plan.md` — related, prior pad-geometry
  correctness work (shape-aware radius model); this plan's frame-typing work is orthogonal
  to that plan's shape-correctness work.
