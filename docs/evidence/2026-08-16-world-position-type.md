---
module: packages/temper-geometry
tags: [world-position, pin-geometry, rotation, pad-position, ssot, rust, property-tests, compile-fail]
problem_type: bug-fix-and-guard
date: 2026-08-16
---

# WorldPosition — a type that makes unrotated pad positions unrepresentable (2026-08-16)

**Purpose**: the "naive `comp_pos + pin_pos` without component rotation" bug
hit **three times** this session. Each fix was the same — "call the rotation
kernel (`pin_world_position_at` / `pin_world_position_at_py`) instead of the
naive sum" — and nothing prevented the next caller from reintroducing it.
This changeset adds a `WorldPosition` type
(`packages/temper-geometry/src/world_position.rs`) whose **only** constructor
applies the full kernel (side mirror + R(-θ) + rotation quadrant + component
position) by construction: private fields, no `From<(f64, f64)>`, two
`compile_fail` doctests pinning both. A future caller cannot forget the
rotation — there is no raw-coordinate path into the type.

**Branch**: `feat/world-position-type` (worktree
`/tmp/opencode/agent-world-pos`), base `origin/main` @ `593d9ab24`.

<!-- provenance: commit=c5bd5e05a5abae7c2f9c5a7f09017ba130092b5e dirty=false -->

---

## 1. The three incidents

All three are instances of mechanism #1 from the 2026-08-15 handoff ("one
fact, many homes, drifting") — the pad world-position fact had a naive home
alongside the correct kernel home, and each naive home produced silent wrong
answers:

1. **Zone-stitch swap shorts (2026-08-15).** `run_collect_pad_positions`
   (the board→pad-positions conversion feeding the zone-stitch writer)
   summed `comp.initial_position + pin.position` with NO component rotation.
   For a rotated 2-pad component that lands every pad on the MIRROR position
   across the anchor — i.e. the OTHER pad — so the zone-stitch writer
   emitted each net's stitch track from the other net's physical pad:
   **204 `shorting_items` + 2 `tracks_crossing`** on the 2026-08-15 routed
   board (e.g. w1_1's stitch from RV1's ac_n pad). See
   `docs/evidence/2026-08-15-router-pad-avoidance-fix.md`.
2. **Zone hulls at wrong coordinates.** The same naive sum placed zone hulls
   and the connectivity preflight at wrong coordinates for the **148/169**
   components with nonzero rotation — measured: only **21/59 real pads**
   inside their same-layer hulls.
3. **The `run_collect_pad_positions` rotation omission, again.**
   Re-introduced after fix 1 and re-fixed by calling back into
   `pin_world_position_at_py` (the same kernel).

The recurring shape: a correct kernel existed (`pin_world_position_at` /
`pin_world_position_kernel`, documented as the pad-position SSOT in
`docs/solutions/architecture-patterns/pad-position-ssot-placer-2026-06-28.md`),
but nothing forced callers through it. This changeset makes the SSOT a
**type**: the world position of a pad can only be constructed by
`WorldPosition::from_component_pin`, which delegates to that exact kernel.

## 2. The type

```rust
pub struct WorldPosition { x: f64, y: f64 }  // fields PRIVATE

impl WorldPosition {
    /// The ONLY constructor — applies the full kernel:
    /// rotation_rad = comp_rotation + quadrant·(π/2)
    /// world = comp_pos + R(-rotation_rad)·(mirror_x(pin_offset, side))
    pub fn from_component_pin(
        comp_pos: (f64, f64),
        comp_rotation: f64,
        pin_offset: (f64, f64),
        initial_rotation_quadrant: i32,
        initial_side: i32,
    ) -> Self { ... }
    pub fn x(&self) -> f64 { ... }
    pub fn y(&self) -> f64 { ... }
    pub fn as_point(&self) -> geo::Point<f64> { ... }
    pub fn as_tuple(&self) -> (f64, f64) { ... }
}
```

- **Kernel-only construction.** `from_component_pin` calls the existing
  `pin_world_position_kernel` (mirror X when `side == 1`, KiCad's R(-θ)
  convention `x·c + y·s, -x·s + y·c` via `host_math` cos/sin for bit-exact
  parity with CPython's libm, then add comp position) — the exact kernel the
  session's three fixes all converged on. No `comp_pos + pin_pos` path
  exists.
- **Two compile_fail doctests** pin the unrepresentability:
  `WorldPosition { x: 1.0, y: 2.0 }` (private fields, E0451) and
  `WorldPosition::from((1.0, 2.0))` (no `From` impl, E0277). Both run under
  CI's `Doctests (cargo test --doc, --no-default-features)` step
  (`.github/workflows/python-tests.yml`), so they are enforced, not
  decorative.
- **pyo3 binding** `world_position_from_component_pin_py` returns the
  `(x, y)` tuple for Python-side callers that already hold resolved values;
  the duck-typed `pin_world_position_at_py` (attribute-reading) stays for
  object-graph callers.
- **Unconditional module** (pure Rust, like `units`/`clearance_halo`); the
  pyo3 surface is `#[cfg(feature = "python")]` beside it.

## 3. Property tests

Each test is mutation-verifiable against the bug it guards:

| Property | Guards |
|---|---|
| **180° two-pin swap** — after quadrant-2 rotation, pin A lands where unrotated pin B was, and the *naive* sum lands A on B's REAL (rotated) pad — the swap-short mechanism, pinned explicitly | incident 1 |
| **0° identity** — world == `comp_pos + pin_offset` exactly (the kernel degenerates to the naive sum, which is what made it seductive) | identity |
| **90° trigonometric transform** — R(-π/2) maps local +x to world −y; quadrant path and float path agree | R(-θ) sign/convention |
| **side mirror** — `side == 1` mirrors X before rotation, matching the kernel's own anchored test | side correction |
| **round-trip** — rotate by θ then −θ (about origin) recovers the offset; plus a **proptest** sweep over random θ and offsets, and a **rotation-composition** proptest (R(-θ₁) then R(-θ₂) = R(-(θ₁+θ₂)), at the origin) | rotation-sign defects (the `investigate/rotation-sign-defect` class) |

Registered on the wasm32 tier via `scripts/gen_wasm_test_registry.py
--crate temper-geometry` (6 tests in
`world_position::tests::WASM_TESTS`); proptests excluded structurally
(dev-dependency), matching `clearance_halo.rs`.

## 4. Proven call site — `run_collect_pad_positions`

`temper-orchestration/src/pipeline_route.rs::run_collect_pad_positions` is
refactored from calling back into the Python
`temper_geometry.pin_world_position_at_py` kernel to building a
`WorldPosition` directly (new `temper-geometry` dependency on
`temper-orchestration`). The attribute reads replicate the kernel's
`rot_to_radians` dispatch exactly (missing → 0.0, int → index·π/2, float →
as-is) and `initial_side` (missing/falsy → 0), so:

- the **pinned differential** (`tests/router_v6/_adapter_convert_py_oracle.py`
  `_oracle_collect_pad_positions`, SHA256-pinned, plus the marshal
  differential's `_oracle_collect_pad_positions`) — **29/29 pass, bit-exact**;
- the rotation-0 duck-typed stub cases are unchanged by construction.

This is the proof the type wraps the kernel correctly in real production
code; other correct call sites (model_builder's `pin_world_positions`,
terminal_planning, etc.) adopt it incrementally.

## 5. Zone generator contract documented

`zone_generator.rs` (#1257) does **not** compute world positions itself — it
receives `own_pads` from callers who already resolve through
`pin_world_position` (rotation-aware). Its `own_pads` contract is now
documented at both the `pour_outline` and `pour_outline_py` entry points:
these MUST be world positions, produced via `WorldPosition::from_component_pin`
(never a bare `comp_pos + pin_pos` sum), citing both incidents.

## 6. Incidental: two pre-existing clippy errors fixed

`main`'s `Rust Checks` CI job is currently red (verified against run
31983690247 for `593d9ab24`): `cargo clippy --all-features --all-targets
-D warnings` on `temper-geometry` fails on two `zone_generator.rs` pyo3
bridge functions — `clippy::type_complexity` on `pour_outline_py`
(`PyResult<Vec<Vec<Vec<(f64, f64)>>>>`) and `clippy::too_many_arguments` on
`emit_zone_outline_s_expr_py` (8 params). Both are pyo3 bridge contracts
whose signatures are fixed by the Python-side API; factored types or fewer
arguments would change the module's Python surface. Added the two targeted
`#[allow]`s with justification comments (same treatment as
`pipeline_route.rs::run_build_route_payload`'s existing
`#[allow(clippy::type_complexity)]`), making temper-geometry clippy-clean.

## 7. Verification summary

- `cargo test` `temper-geometry` (no-default-features, CI config): **8461
  lib + 31 doc tests pass**, incl. the 6 new tests + 2 proptests + 2
  compile_fail doctests.
- `cargo test --doc --no-default-features`: 5 pass (CI's Doctests step).
- `cargo test` `temper-orchestration` (CI config: 15 integration binaries +
  `grid_hv::tests::` + `host_math` dlsym test): all pass. Two lib tests
  (`marshal::tests::end_to_end_placements_field_via_getattr`,
  `netlist_owned::tests::drc_oracle_roundtrips_bit_identically_...`)
  flaked once under concurrent agent load, pass in isolation and on rerun —
  not touched by this change (verified: they do not exercise the
  pad-position path).
- `cargo clippy --all-features --all-targets -D warnings`: clean for both
  crates.
- `python3 scripts/gen_wasm_test_registry.py --crate temper-geometry
  --check`: up to date (idempotent).
- pytest differential `test_adapter_convert_marshal_rust_differential.py`:
  **29/29**, plus adapter-convert and zone-pour differentials: 65/65,
  pin_geometry: 31/31. (Two `test_pad_identity.py` failures are
  pre-existing on main — the fixture passes `initial_rotation=0`, the kwarg
  renamed to `initial_rotation_quadrant` on 2026-08-13; files byte-identical
  to main.)

## 8. What this does NOT do

- Does NOT refactor every existing correct call site (model_builder,
  terminal_planning, congestion_analysis, escape_via, drc marshals): the
  type exists to prevent FUTURE naive-sum callers; adoption is incremental,
  one proven site at a time.
- Does NOT change any kernel math, any Python object surface, or the
  differential oracles (byte-identical results, verified).
- Does NOT touch `pcb/temper.kicad_pcb`.
