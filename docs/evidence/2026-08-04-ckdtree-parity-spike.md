<!-- provenance: commit=15110feccc6ec9389f0777d3cff1ce9f81b11068 dirty=true (branched from origin/main at 15110fecc; the only working-tree change at measurement time was the untracked measurement script tools/measurements/ckdtree_parity_spike.py. All four production modules under measurement -- constraints_spatial_index.py, _zone_pour_stitch.py, constraints_drc_oracle.py, zone_emission.py -- plus pcb/temper.kicad_pcb were verified byte-identical to 15110fecc via diff before every run.) -->

# S2 spike: `scipy.spatial.cKDTree` parity (2026-08-04)

**Verdict: split, and neither half is blocked by what the survey said blocked
it.**

| Module | stmts | Survey bucket | Verdict here |
|---|---:|---|---|
| `router_v6/constraints_spatial_index.py` | 226 | BLOCKED | **UNBLOCKED → PORT**, conditional on one named precondition (§5.1) |
| `router_v6/_zone_pour_stitch.py` | 162 | BLOCKED | **UNBLOCKED → PORT**, with a recorded dormant hazard (§5.2) |

**388 statements move BLOCKED → PORT.**

The survey's stated rationale
(`docs/evidence/2026-08-04-router-v6-migration-survey.md` §2.3) was "kNN
tie-break order is implementation-defined". That rationale is **factually
wrong for the larger of the two modules**: `constraints_spatial_index.py`
performs no kNN query at all. What actually gates it is a different and much
cheaper thing — a scipy *default keyword*. For the smaller module the kNN
tie-break concern is exactly right in principle and is measurably capable of
changing emitted board geometry — but the code path that would do so is
unreachable from its only production caller.

---

## 1. Falsifiers, stated before measuring

Per the convention in `docs/evidence/2026-07-27-first-route-and-profile.md`.

**F1 (`constraints_spatial_index`).** *`cKDTree.query_ball_point` with default
keywords returns indices in ascending index order, so any Rust radius search
that scans its input array in order reproduces the caller's iteration order
exactly, and no downstream value can diverge.*
→ **F1 FIRED.** Order is not index order in 82–97% of queries (§3.1).

**F2 (`_zone_pour_stitch`).** *Exact distance ties among the pour vertices
never occur on real inputs; or where they occur the tied vertices are
coordinate-duplicates, so `all_verts[idx]` yields the same value whichever
index wins, and the emitted segment is invariant.*
→ **F2 FIRED, partially and informatively.** Ties are not merely possible,
they are *guaranteed* — every ring carries a duplicate closing vertex (84/84
rings, §3.4). Those particular ties are indeed idempotent. But a
distinct-coordinate tie is constructible from the module's own degenerate
geometry path and **does** change the emitted KiCad segment (§3.5). What
saves the module is not tie-freeness; it is unreachability.

---

## 2. What is actually asked of the tree

Enumerated from source at `15110fecc`. These two modules are the *only*
`cKDTree`/`KDTree` users in the repository (`grep -rn --include="*.py"
-e cKDTree -e KDTree packages/ tests/ tools/ scripts/`).

### 2.1 `constraints_spatial_index.py` — 3 builds, 3 queries, **zero kNN**

| Site | Construction | Query | `k` | Caller does |
|---|---|---|---|---|
| `rebuild_index` :188 | `cKDTree(midpoints)` | — | — | track midpoints |
| `rebuild_index` :197 | `cKDTree(centers)` | — | — | via centers |
| `rebuild_index` :206 | `cKDTree(centers)` | — | — | pad centers |
| `query_tracks_near` :233 | — | `query_ball_point([x,y], radius)` | n/a | `[self.tracks[i] for i in indices]`, optional layer filter |
| `query_vias_near` :252 | — | `query_ball_point([x,y], radius)` | n/a | `[self.vias[i] for i in indices]` |
| `query_pads_near` :266 | — | `query_ball_point([x,y], radius)` | n/a | `[self.pads[i] for i in indices]`, optional layer filter |

There is no `query`, no `query_pairs`, no `sparse_distance_matrix`, and no
`k` anywhere in the module. All three constructions use scipy defaults
(`leafsize=16, compact_nodes=True, copy_data=False, balanced_tree=True,
boxsize=None`) — no `balanced_tree=`/`compact_nodes=` is passed explicitly.

This matters because `query_ball_point` is a *radius* query: its result set is
fully determined by the predicate `distance <= r`. There is no "which of two
equidistant neighbours wins" question to answer. The only degree of freedom is
the **order** of the returned index list.

**The consumers are all in `constraints_drc_oracle.py`**, in two shapes:

- **First-match-wins, early return** — `can_place_via` (:384, :403, :422) and
  `can_place_track_segment` (:480, :504, :548) loop the result and
  `return (False, f"...violation with {track.id}...")` on the first violating
  item. The *boolean* is order-invariant (if any neighbour violates, some
  neighbour violates); the *reason string* names an arbitrary one.
- **Append-all** — `validate_all` (:634, :670, :702, :734) appends a
  `Violation` per violating pair. The violation *multiset* is order-invariant;
  the returned *list order* mirrors the query order.

### 2.2 `_zone_pour_stitch.py` — 1 build, 1 query, `k=1`

One site, `_stitch_isolated_pads` :163–:187:

```python
tree = cKDTree(all_verts)
for px, py in outside:
    _dist, idx = tree.query((px, py))      # k=1 (default)
    nearest_x, nearest_y = all_verts[idx]
    segments.append(f"  (segment (start {px:.4f} {py:.4f})"
                    f" (end {nearest_x:.4f} {nearest_y:.4f}) ...")
```

The returned **index selects the endpoint of an emitted KiCad track segment**.
This is the genuinely order-sensitive site the survey was worried about: a
different-but-equidistant index is a different piece of copper on the board.

---

## 3. Measurements

All produced by `tools/measurements/ckdtree_parity_spike.py`, re-runnable as:

```
./.venv/bin/python tools/measurements/ckdtree_parity_spike.py
```

scipy 1.16.3, numpy 2.3.5, shapely 2.1.2, CPython 3.12.

The script never mutates production code. Where it needs an alternative
implementation it substitutes one **inside the process only** (`E3` rebinds the
`cKDTree` name in `constraints_spatial_index`'s namespace, restoring it in a
`finally`). `IndexOrderTree` is a brute-force stand-in that returns ascending
indices — i.e. what a straightforward Rust radius search over the same array
produces.

### 3.1 E1 — `query_ball_point` order is not index order (F1's falsifier)

12,000 single-point queries over three point-set families:

| Point set | non-empty queries | **not in index order** | membership mismatch vs brute force | max hits |
|---|---:|---:|---:|---:|
| uniform random | 3875 | **3194 (82.4%)** | **0** | 126 |
| grid, 0.1 mm pitch | 3970 | **3862 (97.3%)** | **0** | 599 |
| grid, 1.27 mm pitch | 3931 | **3737 (95.1%)** | **0** | 293 |

Two facts, both load-bearing:

1. The order is essentially *never* index order. This is not a rare tie
   pathology — it is the normal case, because scipy's `return_sorted` default
   is `None`, documented as "does not sort single point queries".
2. The **membership is always identical** — 0 mismatches in 12,000 queries.
   A Rust port gets the same *set* for free; only the sequence differs.

The PCB-grid rows are the relevant ones for this repo, and they are the worst:
grid geometry makes the divergence near-universal.

### 3.2 E2 — membership is permutation-stable, including at exact boundaries

600 trials, each building the tree twice (original and permuted insertion
order) and remapping indices back to coordinates:

| | count |
|---|---:|
| trials | 600 |
| returned *set* differs | **0** |
| returned *sequence* differs | 42 (7.0%) |
| exact-boundary trials (radius set to a stored point's exact distance) | 600 |
| exact-boundary *set* differs | **0** |

The boundary row rules out a second, independent hazard: the `<=` inclusion
test at `distance == radius` is stable, so a port does not have to replicate a
floating-point boundary convention.

The 7% sequence figure is worth noting against the 82–97% of E1: cKDTree's
output order is *mostly* a function of the spatial subdivision rather than of
insertion index, which is precisely why it disagrees with index order almost
always while being fairly insensitive to permutation.

### 3.3 E3 — does module 1's ordering reach an observable output?

Real `DRCOracle` + `PCBGeometry` + `ClearanceMatrix`, grid-snapped geometry,
swept over three densities. Order can only become observable when several
*violating* neighbours land in one query result, so the sparse case proves
nothing on its own and is reported only for contrast.

| | sparse (40/60/25) | dense (80/120/50) | very-dense (160/240/100) | very-dense, `return_sorted=True` |
|---|---:|---:|---:|---:|
| segment probes / rejections | 200 / 86 | 200 / 190 | 200 / 200 | 200 / 200 |
| **segment boolean diffs** | **0** | **0** | **0** | **0** |
| segment reason-string diffs | 4 | 55 | **157** | **0** |
| via probes / rejections | 200 / 97 | 200 / 198 | 200 / 200 | 200 / 200 |
| **via boolean diffs** | **0** | **0** | **0** | **0** |
| via reason-string diffs | 6 | 94 | **184** | **0** |
| `validate_all` violations | 17 | 285 | 3322 | 3322 |
| violation **multiset** equal | ✅ | ✅ | ✅ | ✅ |
| violation **sequence** equal | ✅ | ❌ | ❌ | ✅ |

Concrete divergences (very-dense):

```
reason string:
  cKDTree      "clearance violation with track_219: 0.000mm < 0.450mm required"
  index-order  "clearance violation with track_136: 0.000mm < 0.450mm required"

validate_all sequence, first differing element:
  cKDTree      ('track_clearance', 'track_0', 'track_86', 0.0, 0.45)
  index-order  ('track_clearance', 'track_0', 'track_31', 0.0, 0.45)
```

So: **every accept/reject decision is invariant** (0 boolean diffs across 1,200
probes with 971 rejections, at every density), the set of violations found is
invariant at every density up to 3,322 violations, but two *returned values*
diverge — the reason string, and the order of `validate_all`'s list. Under G2
(`docs/wave4-discipline-contract.md`:23, bit-exact `==`, not tolerance, with
"insertion order" named as a required crafted edge case), a differential suite
comparing `list[Violation]` with `==` fails on the dense boards.

**The control arm settles it.** Forcing `return_sorted=True` — scipy's own
opt-out of the unsorted default — drives every divergence to zero at the
*densest* configuration: 0 reason-string diffs across 400 probes, and the full
3,322-element violation sequence compares equal. The divergence is caused
entirely by one default keyword, not by anything structural about k-d trees.

### 3.4 E4 — tie census on the real production board (`pcb/temper.kicad_pcb`)

Real pad positions, extracted by replicating
`_adapter_convert._write_routes_to_content`'s collection loop verbatim, then
fed through the real `compute_zones_for_net`. 16 zone-eligible nets (all
ACMains or HighVoltage — those are the only two netclasses declaring
`routing_strategy == "plane_required"`).

| configuration | rings | rings with duplicate closing vertex | **outside-pad queries** | ties | distinct-coord ties |
|---|---:|---:|---:|---:|---:|
| **production** (`cluster=False`, margin 6.0 mm) | 32 | **32/32** | **0** | 0 | 0 |
| `cluster=False`, margin 1.0 / 0.3 / 0.05 mm | 32 | 32/32 | **0** | 0 | 0 |
| `cluster=True`, margin 6.0 / 1.0 / 0.3 / 0.05 mm | 84 | **84/84** | **0** | 0 | 0 |

Two findings.

**(a) Every ring carries a duplicate vertex.**
`_convex_hull_from_positions` explicitly *pops* the closing vertex
(`zone_emission.py`:129–130), and then `_stitch_isolated_pads` feeds the result
back through `Polygon(pts).exterior.coords`, which re-closes the ring. So
`all_verts` always contains `all_verts[0] == all_verts[n-1]` — a guaranteed
exact tie, in 84 of 84 rings. It is harmless precisely because the tied indices
carry *identical coordinates*, and the code consumes `all_verts[idx]`, not
`idx`. This is the "same value by a different route" dissolution.

**(b) The query never runs.** Zero outside-pad queries in all eight
configurations. This is structural, not a property of this board's data:

- `_zone_layers_for_net` returns non-empty only for `plane_required`, i.e.
  only ACMains and HighVoltage.
- Both of those are in `_CONTINUITY_EXEMPT_CLASSES`
  (`_zone_pour_stitch.py`:36), so `_emit_zone_pours` always passes
  `cluster=not exempt` → **`cluster=False`** for every zone-eligible net.
- `compute_zones_for_net(cluster=False)` builds one hull over *all* the net's
  pads; `_convex_hull_from_positions` then buffers it by `margin > 0`.
- `_emit_zone_pours` passes that same `zone_points_by_net` to
  `_stitch_isolated_pads` alongside the *same* `pad_positions` it was built
  from.

Every pad is inside (strictly, after a positive buffer) the hull of the very
point set it belongs to, so `outside` is always empty and the `cKDTree`
construction at :172 is never reached. The `cluster=True` rows show this is not
even specific to the single-hull path: `_cluster_positions` is a partition, so
each pad is inside *its own* cluster's hull too.

### 3.5 E5 — falsifier: is the emitted segment invariant under ring rotation?

Rotating a closed ring's vertex list leaves the polygon identical but
relabels the indices — exactly the perturbation a different tree
implementation, or a Rust polygon builder, could introduce.

**Real board:** `_stitch_isolated_pads` emits **0 segments**; 5 rotations, 0
output changes. Consistent with §3.4(b) — vacuously invariant.

**Crafted tie:** built from the module's own degenerate path.
`_convex_hull_from_positions` emits an axis-aligned square for a single-position
cluster (`zone_emission.py`:118); a pad on that square's vertical centre line is
exactly equidistant from its two bottom corners. Using the real ACMains net
`ac_l` so the netclass gate passes, square centred (50, 50) with h = 6.0, pad at
(50, 34):

```
k=0  verts=[(44,44),(56,44),(56,56),(44,56),(44,44)]  tied=[0,1,4]  query→0  (44.0, 44.0)
k=1  verts=[(56,44),(56,56),(44,56),(44,44),(56,44)]  tied=[0,3,4]  query→0  (56.0, 44.0)
k=2  verts=[(56,56),(44,56),(44,44),(56,44),(56,56)]  tied=[2,3]    query→2  (44.0, 44.0)
k=3  verts=[(44,56),(44,44),(56,44),(56,56),(44,56)]  tied=[1,2]    query→1  (44.0, 44.0)
```

The tie is exact — `dmin == 11.661903789690601` bit-identically for both
distinct corners — and cKDTree's pick flips with index order. Run through the
real `_stitch_isolated_pads`, the four rotations produce **2 distinct outputs**:

```
(segment (start 50.0000 34.0000) (end 44.0000 44.0000) (width 0.2000) (layer "F.Cu") (net 1) ...)
(segment (start 50.0000 34.0000) (end 56.0000 44.0000) (width 0.2000) (layer "F.Cu") (net 1) ...)
```

**Different copper on the board, from a pure index relabelling.** Shapely does
not reorder the ring (the `verts` above follow the rotation exactly), so this
is cKDTree's tie-break and nothing else.

This is the concrete falsifier the survey was right to fear. It just cannot be
reached through `_emit_zone_pours`.

---

## 4. Existing test coverage of the live path

One test reaches the `cKDTree` query:
`tests/router_v6/test_adapter.py::TestStitchIsolatedPads::test_pad_outside_zone_gets_stitch_trace`
(:1228), which hand-supplies `zone_points` unrelated to `pad_positions` — the
thing the production caller never does. That fixture is tie-free (pad (50,50)
vs square (0,0)–(10,10): nearest vertex (10,10) is unique) and asserts only on
the segment's `start`, never on the query-selected `end`. So it would not catch
a tie-break flip even on a tied fixture.

---

## 5. Verdicts

### 5.1 `constraints_spatial_index.py` (226 stmts) — UNBLOCKED → PORT, with a precondition

The survey's stated reason does not apply: **the module issues no kNN query**,
so "kNN tie-break order is implementation-defined" is not the hazard here. The
real hazard is narrower and measured: scipy's `return_sorted=None` default
leaves single-point `query_ball_point` results unsorted (§3.1), and two
returned values inherit that order — the `reason` string of
`can_place_via`/`can_place_track_segment`, and the sequence of
`validate_all()`'s list (§3.3).

Neither reaches a *decision*: 0 boolean diffs in 1,200 probes, violation
multiset equal at every density. In production the divergent values are also
unread — `DRCSweepStage` binds `reason` and discards it
(`deterministic/stages/drc_sweep.py`:58) and is not registered in either
pipeline in `deterministic/__init__.py`; `get_valid_via_sites` discards the
message (`constraints_drc_oracle.py`:614); `DRCValidationStage` stores
`validate_all()`'s output into `BoardState.drc_violations`
(`drc_validation.py`:56), which **no production module reads** (only its length
and per-type counts are used, both order-invariant). But "currently unread" is
not a parity argument under G2, which asserts on returned values.

**Precondition (a recommendation — not applied here, per the no-production-code
constraint):** pass `return_sorted=True` at the three `query_ball_point` call
sites (`constraints_spatial_index.py`:233, :252, :266) *before* porting. This
is a one-keyword change per site with a measured effect: it removes 100% of
the divergence at the densest configuration tested (§3.3 control arm), and it
makes the Python and any index-ordered Rust implementation agree by
construction, so G2's `==` assertions hold without a normalisation shim in the
test harness.

Landing that keyword change on the Python side first is also independently
correct: it makes today's `validate_all()` output deterministic with respect
to a scipy implementation detail, which it currently is not.

Risk if ported *without* the precondition: a differential suite must compare
`validate_all()` as a multiset and must exclude `reason` strings from `==`.
That is a tolerance-shaped exemption, which G2 does not grant. Do the keyword
first.

### 5.2 `_zone_pour_stitch.py` (162 stmts) — UNBLOCKED → PORT, hazard recorded

The tie-break *is* observable in principle and would change emitted board
geometry (§3.5) — the survey's concern is technically correct. But the
`cKDTree` branch is unreachable from its only production caller (§3.4b), a
structural consequence of pours being the convex hulls of exactly the pads
being tested. Measured 0 queries in 8 configurations spanning both `cluster`
values and margins from 6.0 mm down to 0.05 mm.

The `cKDTree` usage is ~14 lines of a 162-statement module whose real content is
netclass resolution, zone-parameter lookup, zone emission, and path chamfering
— none of which touch scipy. Porting is not gated on k-d tree parity.

**Recorded hazard, for whoever ports it:** the branch becomes live the moment a
netclass declares `routing_strategy == "plane_required"` while *not* being in
`_CONTINUITY_EXEMPT_CLASSES` — which routes `compute_zones_for_net` through
`cluster=True`, where a pad can sit outside every hull. The module's own
docstring (:29–35) already flags GND as dormant in exactly this way. If that
happens, a Rust port must break ties by lowest index over the `all_verts` array
as built, which is what cKDTree happens to do for the k=0/2/3 rotations above
but **not** for k=1 — i.e. cKDTree's own choice is not "lowest index", and
replicating it exactly would mean replicating its build and traversal. The
right move at that point is to make the tie-break explicit in the Python first
(e.g. `min` over `(distance, index)`), not to chase cKDTree's internals.

---

## 6. Recommended ledger changes (recommendations only — nothing was edited)

Per the brief, `docs/wave4-verdicts.yaml`, `power_pcb_dataset/drc_ceiling.json`
and all baselines were left untouched.

1. Move `constraints_spatial_index` (226) and `_zone_pour_stitch` (162) from
   BLOCKED to **PORT**. The BLOCKED bucket drops 1,753 → **1,365 statements**.
2. Do **not** add `scipy.spatial.cKDTree` to the ledger as a blocker (survey
   §7 item 4 proposed adding it). Record it instead as a **resolved spike**,
   citing this document, alongside the KTD8 EDT keep.
3. Record the `return_sorted=True` precondition (§5.1) as a prerequisite slice
   on `constraints_spatial_index`'s port — a Python-only change, landable
   independently and worth landing on its own merits.
4. Correct the survey's §2.3 rationale for these two modules: the blocker was
   attributed to kNN tie-break order, which does not exist in the 226-statement
   module and is unreachable in the 162-statement one.

---

## 7. What this spike does **not** establish

- **No Rust k-d tree was benchmarked or built.** No crate was evaluated for
  correctness or speed; per the brief, no `cargo`/`maturin` ran. The claim is
  "order is not a parity obstacle once `return_sorted=True` is set", not "crate
  X is a drop-in". Whether any Rust port of these modules is *faster* is
  untouched here — the survey's own §5 arithmetic (~2.3% of wall time for the
  whole Stage-3 Python surface) should be checked before anyone ports for
  perf.
- **`query_ball_point` membership was verified against a brute-force
  reference, not against a Rust implementation.** 0/12,000 mismatches (§3.1)
  and 0/600 at exact boundaries (§3.2) is strong, but a real port still owes
  G2 its own differential suite.
- **E3's geometry is synthetic.** It is grid-snapped and deliberately crowded
  to force multiple violating neighbours into one query radius; it is not a
  routed production board. The boolean-invariance result (0/1,200) is therefore
  a strong negative on synthetic stress, and the *sequence*-divergence result
  is a positive existence proof — but the production-board rate of
  `validate_all` sequence divergence is **UNKNOWN**, because `DRCValidationStage`
  output was not captured from a full pipeline run.
- **`BoardState.drc_violations` has no production reader today** (§5.1). I
  verified this by grep over `packages/temper-placer/src`. If a consumer is
  added that depends on list order, §5.1's precondition stops being optional
  and becomes a correctness fix.
- **The unreachability argument in §3.4(b) is an argument plus 8 measured
  configurations, not a proof.** It rests on `_cluster_positions` being a
  partition and on `margin > 0` for every zone-eligible netclass (6.0 mm for
  both ACMains and HighVoltage today). A netclass with `clearance == 0` would
  route `_convex_hull_from_positions` down its non-`exterior` fallback branch
  (`zone_emission.py`:131–134), which builds a square around only
  `points.coords[0]` — that path *could* leave pads outside. No such netclass
  exists at `15110fecc`.

---

## 8. Reproduction

```
git checkout 15110feccc6ec9389f0777d3cff1ce9f81b11068
./.venv/bin/python tools/measurements/ckdtree_parity_spike.py            # all
./.venv/bin/python tools/measurements/ckdtree_parity_spike.py --only e3  # one
```

The script resolves `temper_placer` from the installed workspace package when
one is present, falling back to `packages/temper-placer/src` otherwise. The
measurements above were taken with the workspace venv (scipy 1.16.3), after
confirming by `diff` that `constraints_spatial_index.py`,
`_zone_pour_stitch.py`, `constraints_drc_oracle.py`, `zone_emission.py` and
`pcb/temper.kicad_pcb` were byte-identical to `15110fecc`.
