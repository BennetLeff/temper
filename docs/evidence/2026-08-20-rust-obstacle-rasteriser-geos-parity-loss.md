# The Rust obstacle rasteriser freed 3,020 cells GEOS blocks — an inverted index round trip

<!-- provenance: commit=167ddb0a922094119ccfd9c2175fe02d9fccb1e0 dirty=true -->
<!-- base origin/main @ 167ddb0a9; pcb/temper.kicad_pcb read-only (sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b before and after — never written) -->

**Date:** 2026-08-20
**Task:** find why `rasterize_area_polygons_py` diverged from GEOS on the real
board, and fix it in the conservative direction.
**Result:** **permissive mismatches 3,020 → 0.** Total mismatches 5,230 → 130,
every survivor in the safe direction (Rust blocks where GEOS frees). The cause
was a lossy index round trip, not a tolerance or an interval convention. Exact
0/0 parity on the pre-#1312 board is preserved. The routed board loses
8 segments (4553 → 4545) and holds vias/zones at 169/151.

## 1. The measurement

`shapely.contains()` vs `_tg.rasterize_area_polygons_py` over every cell centre
of all six layers, both fed the **identical** eroded polygon (the production
`OccupancyGridStage` parameters: `cell_size` 0.1, `margin` 2.0, `inflation`
`default_trace_width_mm / 2` = 0.1000).

Two directions, and they are not equally serious:

- **PERMISSIVE — Rust FREE, GEOS BLOCKED.** A safety defect. The eroded area's
  boundary already carries the trace-width/2 C-space inflation, so a cell freed
  there lets A\* route at *exactly* the clearance distance.
- **CONSERVATIVE — Rust BLOCKED, GEOS FREE.** Safe. Costs routable area, never
  clearance.

### Before (board `26981fea`)

| layer | mismatches | PERMISSIVE | CONSERVATIVE | cells |
|---|---|---|---|---|
| F.Cu | 623 | 273 | 350 | 3,998,400 |
| In1.Cu | 17 | 17 | 0 | 3,998,400 |
| In2.Cu | 17 | 17 | 0 | 3,998,400 |
| In3.Cu | 1,053 | 503 | 550 | 3,998,400 |
| In4.Cu | 2,136 | 1,138 | 998 | 3,998,400 |
| B.Cu | 1,384 | 1,072 | 312 | 3,998,400 |
| **total** | **5,230** | **3,020** | **2,210** | **23,990,400** |

### After

| layer | mismatches | PERMISSIVE | CONSERVATIVE | cells |
|---|---|---|---|---|
| F.Cu | 22 | **0** | 22 | 3,998,400 |
| In1.Cu | 1 | **0** | 1 | 3,998,400 |
| In2.Cu | 1 | **0** | 1 | 3,998,400 |
| In3.Cu | 32 | **0** | 32 | 3,998,400 |
| In4.Cu | 37 | **0** | 37 | 3,998,400 |
| B.Cu | 37 | **0** | 37 | 3,998,400 |
| **total** | **130** | **0** | **130** | **23,990,400** |

The differential's own assertion previously stopped at the first failing layer,
which is why it read as 623 rather than 5,230. It now measures all six and
reports both directions separately.

## 2. Characterising the divergence

Measuring each mismatched cell's `shapely.distance(point, area.boundary)` and
testing its centre coordinates against the ring edge tables separates the two
populations cleanly:

- **All 3,020 permissive cells sat at distance *exactly* `0.0` from the
  boundary**, and **100% of them had a centre coordinate exactly equal to an
  axis-aligned edge's coordinate** (`neither = 0` on every layer: 1,590 on a
  vertical edge's x, 1,430 on a horizontal edge's y, with overlap). These are
  not "near" the boundary. They are *on* it, which is exactly the case the
  convention exists to block.
- **The 2,210 conservative cells sat 8.7e-17 … 3.0e-14 mm *inside*** and were
  mostly (78%) not on any axis-aligned coordinate — cells a hair inside that
  the same arithmetic pushed the interval endpoint past.

So it is neither a tolerance, nor a half-open-vs-closed interval choice, nor an
ordering difference. It is one arithmetic defect with two signs.

## 3. The mechanism

A cell centre's world coordinate is, by definition and in the GEOS reference's
own numpy expression:

```
centre(i) = origin + (i + 0.5) * cell_size
```

The kernel recovered `i` from a world coordinate by **inverting** that:

```rust
let i1 = ((((hi - origin_x) / cell_size) - 0.5).ceil() as i64 - 1).min(cols - 1);
```

That inversion is not exact. `cell_size` (0.1) is not binary-representable and
`hi - origin_x` drops low bits, so the round trip drifts. Measured on In1.Cu
(`origin_x` = 6.0, `cell_size` = 0.1, column 880):

```
edge x            = 94.05000000000001   (0x1.7833333333334p+6)
centre(880)       = 94.05000000000001   (0x1.7833333333334p+6)   <- identical
inverted index    = 880.0000000000001   (0x1.b800000000001p+9)
drift             = +1.137e-13 index units
ceil(inverted) - 1 = 880                <- column 880 FREED
centre(880) < hi   = false              <- exact rule: BLOCKED
```

A drift of 1.1e-13 is thousands of ULPs at index 880, and `ceil` turns it into
a whole cell. The polygon has a vertical edge at exactly `x = 94.05000000000001`
— i.e. exactly on column 880's centre — so GEOS `contains` (which excludes the
boundary, DE-9IM `T*****FF*`) blocks it and the kernel freed it. Those 17 cells
are the whole In1.Cu/In2.Cu column.

The same defect **silently disabled the horizontal-edge pass**, which existed
precisely to catch centres lying on horizontal edges:

```rust
let jf = ((hy - origin_y) / cell_size) - 0.5;
if jf.round() == jf { /* re-block this row */ }
```

This asks whether the *lossy inversion* is integral. Real board offsets
essentially never satisfy it, so the pass was dead on the real board — and
alive only in the synthetic tests, whose round origins (−0.5) and cell sizes
(1.0) make the inversion exact. That is why all 30 synthetic parity tests
passed, including the explicit boundary-alignment case, while the real board
diverged.

## 4. Regression or latent? — **latent, proven**

Both halves were checked, and neither is inference:

1. **The kernel never changed.** `git diff dabbeaf73 origin/main --
   packages/temper-geometry/src/occupancy_raster.rs` is empty. It landed once,
   at `dabbeaf73` (2026-08-16, squashing `e3883414a`), and is byte-identical
   since.
2. **The pre-fix kernel really did score 0 on the 2026-08-15 board.** The board
   at `6285d6889` hashes to `077d4b69…`, exactly the digest in the
   2026-08-15 evidence doc's provenance header. Rebuilding the *unmodified*
   kernel and running the same comparison against that board's eroded geometry
   gives **0 mismatches across 22,276,800 cells** — matching the doc's "~22.3 M
   cells, 0 mismatches" claim. The doc was honest.

The copper regeneration `23b5daf8d` (#1312, 2026-08-17, zones 96 → 151)
therefore **exposed** a latent numerical gap rather than causing a regression.
It introduced geometry whose C-space edges land exactly on cell centres; the
older board simply never produced that coincidence.

The fixed kernel also still scores **0/0 on `077d4b69`**, so the fix is not a
trade of one board's parity for another's.

## 5. The fix

`packages/temper-geometry/src/occupancy_raster.rs`. Never recover an index by
inverting the centre formula; decide every bound against the
**exactly-reconstructed centre**, which is bit-identical to the coordinate GEOS
was handed (same IEEE-754 operation sequence as numpy's
`origin + (idx + 0.5) * cell_size`).

- `cell_center(origin, cell_size, idx)` is the single authoritative definition.
- `correct_index` takes the inverted value as a *starting guess only* and walks
  it (bounded, ±2 steps) onto the first index whose real centre satisfies the
  predicate. `cell_center` is strictly monotone in `idx` for positive
  `cell_size`, so the walk is well-defined.
- Four bounds replace the four `floor`/`ceil` inversions:
  `first_center_after` / `last_center_before` (strict — the interval fill, where
  a centre exactly on a bound is boundary and stays blocked) and
  `first_center_at_or_after` / `last_center_at_or_before` (inclusive — the
  horizontal-edge blocking pass, where a centre on an endpoint is still on the
  boundary). Every fallback errs toward blocking.
- The horizontal-edge pass now tests `cell_center(...) == hy` — an exact
  question about a real centre, not about the lossy inversion — so it fires on
  real geometry.
- `rasterize_area_polygons` runs all interior fills first, then all horizontal
  blocking passes, instead of one interleaved pass per polygon. For a valid
  MultiPolygon the two are equivalent; phasing removes the order dependence
  where a later component's interior fill could free an earlier component's
  boundary.

## 6. The residual 130 is irreducible in f64, and is safe

Every one of the 130 survivors is a cell whose centre x is exactly some
vertical edge's x, with GEOS placing it 8.7e-17 … 5.5e-15 mm *inside*. The
In1.Cu case: the row centre `y = 237.85000000000002` passes 2.8e-14 above a
ring vertex at `(94.05000000000001, 237.85)`, so the crossing interpolation
`x1 + t*(x2 - x1)` runs at `t = 0.9999999999992573` and rounds onto the vertex
exactly, while GEOS's double-double robust predicates resolve the point as
interior.

Matching that would mean evaluating Shewchuk orientation predicates per
candidate cell rather than computing crossings in plain doubles. It is not a
tolerance that can be tightened.

**Honest caveat:** the residual is conservative *as measured on this board*, on
every one of the 130 cells, but its direction is not proven for arbitrary
geometry — a sub-ULP crossing collapse could in principle round the other way.
What *is* structural is that the entire population of exact coincidences (the
3,020, where "on the boundary" is a well-posed question) is now decided
exactly. The remaining ambiguity is confined to points within ~5e-15 mm of a
boundary, a scale at which "which side" carries no DRC meaning.

## 7. Routed-board consequence

`scripts/route_board.py --net-batching --batch-size 10`, board `26981fea`
(unmodified — verified before and after; output written to a scratch path):

| | segments | vias | zones | pad-connected | fake-completion |
|---|---|---|---|---|---|
| committed route (baseline) | 4553 | 169 | 151 | — | — |
| post-fix | 4545 | 169 | 151 | 60/139 | 6 |

The fix nets 940 fewer free cells out of 23,990,400 (3,020 newly blocked, 2,080
newly freed). The routed board loses **8 segments**, holds vias and zones
exactly, and the router does not lose a net to it. A board that routes 8 fewer
segments but never at less than clearance distance is the better board.

## 8. Reproducing

```bash
make venv-isolate                       # under: env -u CONDA_PREFIX

# The parity differential (all six layers, both directions).
uv run pytest packages/temper-placer/tests/router_v6/test_occupancy_grid_rust_differential.py -v

# The mechanism, pinned without the board:
#   Python: test_rasterize_area_polygons_lossy_index_roundtrip_keeps_boundary_blocked
#   Rust:   cargo test --manifest-path packages/temper-geometry/Cargo.toml \
#             --features python --lib occupancy_raster
#           (test_index_roundtrip_really_is_lossy and the four index-bound tests)

# The route.
uv run python3 scripts/route_board.py --output /tmp/routed.kicad_pcb \
    --net-batching --batch-size 10
```

Board digests: `pcb/temper.kicad_pcb` =
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`, unchanged
before and after every measurement above. The 2026-08-15 comparison board is
`git show 6285d6889:pcb/temper.kicad_pcb` =
`077d4b6993c2708ea8d32572300f2964d2e0fb1634f903f5736b3a6eb38f2fda`.

## 9. What the differential now asserts

The old assertion (`np.array_equal`, aborting on the first failing layer) is
not satisfiable in f64 for the reason in §6, and was only ever true by the
board's luck. It is replaced by the contract that actually matters, which is
strictly stronger in the direction that carries the safety stake:

- **`sum(permissive) == 0`** across all six layers. No budget, no tolerance.
- **`sum(conservative) <= 130`**, a downward-only ratchet. Raising it would mean
  the kernel started discarding routable area — safe, but a real regression that
  wants its own investigation.
- The `total_cells >= 15_000_000` shrunk-board guard is retained.
