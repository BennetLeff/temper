# Pad copper rectangles were rotated the wrong way — and no number on this board changed

**Date:** 2026-08-18
**Board:** `pcb/temper.kicad_pcb`, sha256 `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`,
verified byte-identical before and after every measurement below. Never modified.
**Base:** `origin/main` @ `9bf6e5df7`.
**Ground truth:** pcbnew `10.0.5-10.0.5~ubuntu24.04.1`.
**Threshold changes:** none. No clearance, creepage, copper-weight or DRU value was touched.

---

## 1. What was wrong

`core/pad_geometry.py::pad_core_polygon` and `::pad_polygon` oriented a pad's
copper rectangle with

```python
rotate(core, math.degrees(rotation_rad), origin=(0, 0), use_radians=False)
```

`shapely.affinity.rotate`'s `angle` is CCW-positive — **R(+θ)**. KiCad rotates a
footprint child **clockwise**, R(−θ). Their bit-exact Rust twin,
`clearance_geometry.rs::shapely_rotation_cos_sin`, replicated the same omission.
Meanwhile `scripts/check_board_containment.py::_pad_polygons` rotated the
*identical object* through `kicad_transform.shapely_rotation_angle_deg`, i.e.
R(−θ). Both could not be right.

This is a genuinely separate bug from the one PR #1376 fixed. That one was about
where a pad's **centre** lands. This one is about which way its **rectangle** is
turned about that centre. Two independent code paths, two independent sign
decisions.

## 2. Ground truth: pcbnew says R(−θ)

`scripts/kicad_pad_polygon_oracle.py` builds a rectangular pad at a given size,
centre and orientation in pcbnew and reads back the corners of the polygon KiCad
fills with copper. Ten rows, ten agreements:

| pad size (mm) | angle | R(−θ) matches pcbnew | R(+θ) matches pcbnew |
|---|---|---|---|
| 4.0 × 1.0 | 30° | **yes** | no |
| 4.0 × 1.0 | 45° | **yes** | no |
| 3.0 × 1.5 | 23° | **yes** | no |
| 2.0 × 0.5 | −37.5° | **yes** | no |
| 1.7 × 1.0 | 135° | **yes** | no |
| 0.9 × 1.6 | 61° | **yes** | no |
| 4.0 × 1.0 | **0°** | yes | **yes** |
| 4.0 × 1.0 | **90°** | yes | **yes** |
| 4.0 × 1.0 | **180°** | yes | **yes** |
| 4.0 × 1.0 | **270°** | yes | **yes** |

For the 4 × 1 mm pad at 30°, pcbnew's corners are
`(−1.982051, 0.566987) (1.482051, −1.433013) (1.982051, −0.566987) (−1.482051, 1.433013)`.
R(+30°) puts a corner at `(1.482051, 1.433013)`, which is not in that set.

**The last four rows are the whole story.** At every multiple of 90° the two
conventions produce the *same corner set*, differing only in the ring's traversal
order — which no distance, containment or area query can observe.

## 3. Why it was invisible

Measured over the real board, every pad, by parsing `pcb/temper.kicad_pcb`:

```
527 pads
pad-angle histogram: {0.0: 58, 90: 202, 180: 175, 270: 92}
```

**No pad on this board sits at any other angle.** That is why
`pad_pair_distance` reproduced `kicad-cli` to four decimals and was believed
correct. Correct by coincidence of placement, not by construction — and the
placer is free to emit a non-90° rotation at any time.

## 4. The fix

* Python: `pad_core_polygon` and `pad_polygon` now take the angle from
  `kicad_transform.shapely_rotation_angle_deg(math.degrees(rotation_rad))` —
  the sanctioned bridge, called rather than typed.
* Rust: `clearance_geometry.rs::shapely_rotation_cos_sin` now calls
  `kicad_transform::shapely_rotation_angle_deg` for the same negation. This is
  the shape `core_graph_geometry.rs::courtyard_global_points` already had
  (it negated its angle); the two are now consistent, and both obtain the
  negation from the same place.
* The verbatim oracle in `test_clearance_rust_differential.py` moved with them,
  necessarily — see §7.

## 5. Differential on real board geometry

`pcb/temper.kicad_pcb`, every pad, before (origin/main) vs after, with all 10
extensions verified fresh by `make extensions-check` on both sides. Values
compared as `float.hex()`, i.e. bit-exact.

| quantity | population | differences |
|---|---|---|
| `pad_pair_distance` over every unordered pad pair | **138,601 pairs** | **0** |
| `pad_polygon` bounds (quad_segs=16) | 518 pads | **0** |
| `pad_core_polygon` **corner sets** | 518 pads | **0** (worst displacement **0.0 mm**) |
| `pad_core_polygon` ring traversal order | 518 pads | 261 changed |

**No measured figure on this board changed.** The only observable difference is
the order in which a rectangle's four corners are listed, which is not geometry.

That is the expected result and it is also the point: the fix is provably a no-op
*here*, and provably not a no-op anywhere off a 90° multiple. §2's table is the
measurement that distinguishes those two claims; §5's is the one that proves the
change is safe to land.

### 5.1 One figure DID change — a test helper, not a measurement

`test_clearance_rust_differential.py::_world_rotate` rotated a pad's **centre**
by R(+δ) while `rot + delta` turned its **copper** by R(−δ). Opposite senses. It
agreed with itself only because `pad_core_polygon` was also R(+θ); correcting the
kernel exposed it immediately — 8/8 seeds of
`test_metamorphic_rotation_invariance`, worst observed `10.002908` vs
`9.955485` mm (0.047 mm) on the first failing case. The helper now rotates the
centre through `kicad_transform.rotate_local_to_world`, the same sense the
pad-angle term always had. This is a bug in the test's own algebra, not in any
production number.

## 6. The gate, and its anti-vacuity

`scripts/check_pad_core_polygon_oracle.py` resolves **5 implementations by
import and calls them** against pcbnew's pinned corners.

**On the real pre-fix tree** (before any source edit, all extensions fresh):

```
[FAIL] core.pad_geometry.pad_core_polygon:      worst 2.061553055 mm -- R(+theta)
[FAIL] core.pad_geometry.pad_polygon:           worst 2.061553055 mm -- R(+theta)
[FAIL] temper_geometry.pad_pair_distance_py:    worst 1.443487036 mm -- R(+theta)?
[ok  ] check_board_containment.py::_pad_polygons: worst 0.000001434 mm
[ok  ] kicad_transform.shapely_rotation_angle_deg: worst 0.000001434 mm
exit 3
```

The two passing rows are the positive control: they were already R(−θ), so if
they had failed, the gate's own comparison would have been what was wrong. Worst
clean error is `1.4e-06 mm` — pcbnew's own nanometre quantisation — against a
`1e-05 mm` tolerance.

**After the fix:** all 5 pass, worst `1.434e-06 mm`, exit 0.

**Live Rust mutation test.** The sign flip was removed from
`clearance_geometry.rs`, the crate rebuilt with `maturin develop --release`, and
the gate re-run:

```
[FAIL] temper_geometry.pad_pair_distance_py: worst 1.443487036 mm -- R(+theta)?
exit 3
```

Only the Rust site moved; the other four stayed clean, so the gate localises the
mutation rather than merely detecting it. Reverted and rebuilt; back to 0.

**Corpus self-checks.** Every row must separate the two conventions by more than
0.1 mm; a row at a multiple of 90° is a hard **error**, not a skip; at least 4
asymmetric (width ≠ height) rows are required, because a square at 45° is
symmetric under both conventions and is a 90° row in disguise; and pcbnew's
pinned answers must themselves *be* R(−θ), so a corrupt corpus cannot enforce a
fiction. The corpus is pinned to the oracle script's sha256 and fails closed
telling you to **regenerate**, never to re-pin.

**False-positive guard.** A perturbation 10× below tolerance must stay clean —
a gate that fires on float noise gets switched off.

## 7. What the differential suite can and cannot prove

`test_clearance_rust_differential.py` pins Rust ≡ Python/Shapely bit-for-bit. It
cannot see a convention error, because a **consistently wrong pair passes it** —
and did, from the Wave 3 migration until today. Correcting one side without the
other would not have produced evidence; it would have produced a red suite.

So the oracle moved in lockstep, and the convention is anchored somewhere the
oracle cannot reach: against pcbnew, at non-90° angles. Two new permanent tests
in that same file read the pinned corpus, so the anchor cannot be deleted without
failing the differential suite too — and one of them is a mutation test asserting
that the pre-fix R(+θ) body would have missed pcbnew's answer by more than
0.1 mm.

## 8. Rust rotation sites: routed, or exempted with a reason

A sweep of all `packages/*/src/**.rs` found the KiCad convention typed out by
hand in ten functions across six crates, plus three integer quadrant tables.

**Routed through `kicad_transform` (bit-identical by construction):**

| site | why the swap changes no bits |
|---|---|
| `clearance_geometry.rs::rotate_local_to_world` | same `pad_geometry::math_cos_sin`, same op order |
| `clearance_geometry.rs::shapely_rotation_cos_sin` | sign only; IEEE negation |
| `drc_constraints_geometry.rs::rotate_local_to_world` / `::rotate_world_to_local` / `::place_local_to_world` | same `math_cos_sin`, same order |
| `congestion_analysis.rs::rotate_local_to_world` | `host_math::cos/sin` and `math_cos_sin` are the *same function pointer* — both `dlsym(RTLD_DEFAULT, "cos"/"sin")` with the same `f64::cos/sin` fallback |
| `escape_via.rs::rotate_local_to_world` | as above |
| `core_graph_geometry.rs::pin_world_position_kernel` | as above, via `place_local_to_world`; the side mirror stays local because it must precede the rotation |
| `core_graph_geometry.rs::courtyard_global_points` | negation only |
| `connectivity_kernels.rs::to_pad_coordinates` | same `deg * (PI/180.0)` shape, same `(x*c − y*s, x*s + y*c)` |

Proof: 138,601-pair board differential (§5) plus the full `temper-placer` suite
and `cargo test -p temper-geometry` (8,467 tests).

**Registered exemptions, each with its reason** (in
`check_no_raw_rotation_trig.py::RUST_EXEMPT_FUNCTIONS`):

* `transform.rs::transform_pin_position` / `transform_pin_positions` — correct
  R(−θ), but on **plain `f64::cos`/`sin`**, which differs from the host-libm path
  by 1 ulp on this platform (`kicad_transform.rs`'s own header documents exactly
  this and names this function). Routing it would *change output bits* — the
  opposite of a behaviour-preserving migration.
* `net_ordering.rs` / `terminal_planning.rs` — `temper-rust-router` has no
  dependency on `temper-geometry`; the file's own comment records that as the
  reason for the duplication. Adding a crate dependency and moving onto the
  host-libm path is a bigger change than this one, and not a no-op.
* `parse_engine.rs::extract_components_pure` — the `.kicad_pcb` parse path. The
  crate *does* depend on `temper-geometry`; the blocker is arithmetic, not
  dependency: it converts with `f64::to_radians` while `kicad_transform` uses the
  CPython-shaped `t * (PI/180.0)`. Needs its own differential; recorded as a
  decision rather than an omission.
* `placer_compute.rs::apply_{component,parametric}_template` — receives cos/sin
  as an **injected callback** into CPython's own `math.cos`/`sin`, precisely so
  the kernel does not re-type the transcendental. That seam is already an
  exemption on the Python side (`placer/template.py::_cos_sin`).
* `clearance_geometry.rs::shapely_rotation_cos_sin` and
  `core_graph_geometry.rs::courtyard_global_points` — shapely/numpy **affine
  replicas**. They legitimately need their own trig (shapely's degrees round-trip
  and its `2.5e-16` snap, which a point transform has no business carrying). What
  they must not type is the *sign*, and neither does.
* `pad_geometry.rs::support_radius`, `fixed_copper.rs::local_pad_half` —
  sign-invariant by construction (`|cos|`, `|sin|`).
* the two dlsym host-libm providers — the base case; they *are* the cos/sin
  `kicad_transform` itself calls.

**Quadrant tables.** `pad_geometry.rs::project_onto_barrier_axis` and
`clearance.rs::project_onto_barrier_axis_impl` are two copies of the same
R(−θ) table. They are *not* consolidated, because they differ deliberately at the
boundary (catch-all vs `None`). What is now enforced for free is that their four
in-range arms never drift — compared against a **stated** expectation, not only
against each other, because two copies can drift together.

## 9. Known limits

* The Rust lint is textual, not AST-based (no Rust parser in this repo's
  dependency set; `check_rotation_quadrant_arithmetic.py` sets the precedent).
  It strips `//` comments with quote-parity tracking so a `//` inside a string
  cannot hide a rotation, and does **not** strip block comments — it over-reports
  rather than under-reports, which is the safe direction.
* The lint removes the *capability to type the formula*. It cannot see a wrong
  **sign** inside a function it exempts — the live mutation in §6 passes the lint
  and fails the pcbnew gate. The two are complementary and both are wired.
* The gate probes **rectangular** pads only. For `rect` the corner radius is 0,
  so the copper outline *is* `pad_core_polygon`'s core and both sides are exact
  4-corner polygons. Round shapes would need an arc-approximation tolerance and
  would discriminate no better.

## 10. Two pre-existing failures on `origin/main`, not from this change

Both reproduce with the relevant files byte-identical to `origin/main`:

1. `test_design_rules_rust_differential.py::test_module_constants_identical` —
   the Rust `TEMPER_NET_ASSIGNMENTS` carries `hb-gnd: HighVoltage`, the Python
   oracle does not. `design_rules.rs`, `_design_rules_py_oracle.py` and the test
   are all untouched by this change.
2. `pad_geometry::tests::pow2_is_exact_where_powi_is_not` (`cargo test
   -p temper-geometry`, 1 of 8,468) — a `powi` denormal assertion.
   `pad_geometry.rs` is untouched by this change.
3. `scripts/check_manifest_gate.py` still fails on
   `check_placement_pair_creepage.py`, which has no manifest entry on
   `origin/main` either (already reported by PR #1376).

## 11. A measurement trap hit during this work

Two distinct build hazards were hit, both silent-by-default.

1. **`maturin develop --release` printed `Installed temper-geometry-0.1.0`
   while leaving the installed `.so` at its previous mtime.**
   `make extensions-check` showed `[STALE]` for four crates. A gate was
   consequently run once against a kernel built from different source — which
   is exactly how the gate first appeared to "pass then fail" with no source
   change in between.

2. **A bare `cargo build --release` in `packages/temper-geometry` poisoned the
   shared cdylib.** The crate's `python` feature is not default, so that build
   linked `target-shared/release/libtemper_geometry.so` *without*
   `PyInit_temper_geometry` — and that path is shared across every worktree on
   this host. Subsequent `maturin develop` runs printed
   `Finished ... in 0.04s`, `Installed temper-geometry-0.1.0`, and one
   `⚠️ Warning: Couldn't find the symbol PyInit_temper_geometry` line, then
   installed the broken artifact. `check_stale_extensions.py` caught it as
   `[UNLOADABLE]` and named the cause correctly.
   **`cargo clean -p temper-geometry` did not fix it** (`Removed 0 files` —
   cargo's fingerprint was satisfied). What worked was
   `touch packages/temper-geometry/src/lib.rs` followed by
   `maturin develop --release`, confirming a real `Compiling temper-geometry`
   line and a 1m05s build, then rebuilding the three dependent crates the
   touch had just made stale.

A broken `.so` fails **loud** (`ImportError: dynamic module does not define
module export function`), never silently — so no measurement in this document
was taken through one. Every number here was re-measured with
`make extensions-check` reporting `PASSED -- 10/10 extension module(s) fresh`
and `import temper_geometry` verified live.

**Run `make extensions-check` between the edit and the measurement, not just
after the build command claims success. And do not use bare `cargo build` in a
pyo3 crate whose `python` feature is non-default.**

## 12. Reproduce

```bash
# ground truth (needs an interpreter with pcbnew bindings)
python3 scripts/check_pad_core_polygon_oracle.py --regenerate-corpus

# the gate, and its own tests
python3 scripts/check_pad_core_polygon_oracle.py
pytest scripts/tests/test_check_pad_core_polygon_oracle.py

# the lint, both halves
python3 scripts/check_no_raw_rotation_trig.py
pytest scripts/tests/test_check_no_raw_rotation_trig.py

# the differential the fix had to keep
pytest packages/temper-placer/tests/requirements/test_clearance_rust_differential.py
```
