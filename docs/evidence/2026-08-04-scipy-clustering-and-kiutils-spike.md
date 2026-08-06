<!-- provenance: commit=15110feccc6ec9389f0777d3cff1ce9f81b11068 dirty=false -->

# S5 spike: `scipy.cluster.hierarchy` and `kiutils` boundaries in `router_v6`

**Date:** 2026-08-04
**Branch:** `docs/spike-scipy-clustering-and-kiutils-boundaries`, branched from
`origin/main` at `15110feccc6ec9389f0777d3cff1ce9f81b11068`.
**Scope:** the two smallest BLOCKED entries in the router\_v6 migration survey
(`docs/evidence/2026-08-04-router-v6-migration-survey.md` §2.3, PR #741) —
`zone_emission` (97 stmts) and `constraints_design_rules` (250 stmts).

No production code was changed and no Rust was built. Two measurement scripts
were added under `tools/measurements/`. Statement counts use `ast.stmt` node
counts, the same convention as the survey — reproduced and confirmed exactly
(250 and 97).

## Verdicts

| Part | Surface | Verdict | Statements |
|---|---|---|---:|
| 1 | `zone_emission` `scipy.cluster.hierarchy` | **UNBLOCKED** — tie-break not observable; scipy is also unreachable on the production path | 97 BLOCKED → PORT *(97 for the scipy blocker; a separate GEOS boundary remains, see §1.5)* |
| 2 | `constraints_design_rules` kiutils | **UNBLOCKED for kiutils; the recorded verdict does not cover this module** | 250 BLOCKED → 90 PORT (`ClearanceMatrix` less its `parse` seam) + 64 DEAD + 96 re-scoped, see §2.6 |

Both are *measured* dissolutions, not arguments. The falsifiers, stated in
advance, are in §1.1 and §2.1.

---

## Part 1 — `scipy.cluster.hierarchy` in `zone_emission.py`

`packages/temper-placer/src/temper_placer/router_v6/zone_emission.py:91-92`
imports `fcluster`/`linkage`/`pdist` inside `_cluster_positions`.

### 1.0 What the call actually is

Answering the brief's first question directly, from `zone_emission.py:94-95`:

```python
Z = linkage(pdist(positions), method="ward")
labels = fcluster(Z, t=threshold, criterion="distance")
```

- **linkage method:** `ward` (`pdist` at its default `euclidean` metric).
- **fcluster criterion:** `distance` — a flat cut of the dendrogram at height
  `t`.
- **`t`:** the brief paraphrased the line-44 docstring as deriving the cut
  threshold "from the largest gap in the linkage". The docstring does not say
  that and the code does not do that — correcting the record, because the
  distinction carries the verdict. The docstring says "the largest gap in
  sorted nearest-neighbour distances", and that is accurate: the threshold is
  computed at lines 55–89 **before `linkage` is ever called**, from the largest
  *relative* gap in the sorted per-pad nearest-neighbour distances, with a
  95th-percentile fallback floored at 10.0 mm. Nothing about the dendrogram
  feeds it.

  Consequence: the threshold is a pure function of the position *set* —
  order-independent, scipy-independent, and already pure Python.
  `tools/measurements/spike_zone_cluster_tie_invariance.py:_threshold_for`
  re-derives it without importing scipy at all. **The only thing scipy decides
  is the partition, at a threshold scipy did not choose.** That is a much
  smaller boundary than "hierarchical clustering" suggests.

### 1.1 Falsifier, stated before measuring

> **Ward agglomeration is only partially determined by the distances. When two
> candidate merges have equal cost, scipy's nn-chain implementation breaks the
> tie by point index order, and a Rust reimplementation is free to break it
> differently. If permuting the input position order — which permutes exactly
> the index order the tie-break consults — changes the emitted zone geometry on
> real net position sets, the blocker is real and the permutation that flips it
> is the concrete falsifier.**

Corollary stated at the same time: a *string* difference in the emitted
s-expression is not automatically a geometry difference, and charging a GEOS
serialisation artefact to scipy would be a false positive. Four comparison
levels were therefore fixed in advance: partition, canonical polygon
(rotation-independent vertex multiset), s-expression multiset, s-expression
sequence.

### 1.2 Method

`tools/measurements/spike_zone_cluster_tie_invariance.py`. 61 real per-net pad
position sets (every net on `pcb/temper.kicad_pcb` with >2 pads, extracted via
kiutils with footprint rotation applied), plus 4 synthetic exact-pitch cases
built to force ties. 64 seeded permutations each (seed 20260804), 4,160 trials
total. scipy 1.16.3 / shapely 2.1.2 / numpy 2.3.5 / kiutils 1.4.8, the repo's
own `.venv`.

Permutation is the right probe rather than a proxy: scipy's Ward runs the
nn-chain algorithm, whose tie-resolution is determined entirely by point index
order. Permuting the input *is* enumerating the tie-break space.

### 1.3 Result — the falsifier did **not** fire on real data, and **did** fire on synthetic exact-pitch data

| Corpus | cases | trials | cases w/ tied distances | cases w/ tied Ward merges | partition flips | canonical polygon flips |
|---|---:|---:|---:|---:|---:|---:|
| Real board nets | 61 | 3,904 | 1 | **0** | **0** | **0** |
| Synthetic exact-pitch | 4 | 256 | 4 | 4 | **182** | **182** |

Reading it:

1. **On real data the tie-break is never even exercised.** Exactly one net
   (`gnd`, 86 pads) has any tied pairwise distances at all (18 tied pairs out
   of 3,655), and **zero** nets produce a tied Ward merge height. The brief's
   premise — "PCB pad positions on a regular pitch produce exact ties
   constantly" — is true of pads *within* a footprint, but a net's pads span
   multiple footprints whose world positions come out of a float placement
   pipeline with arbitrary rotations, so the intra-footprint pitch regularity
   does not survive into the pairwise distance set. Zero partition flips across
   3,904 permutations.

2. **The blocker is nevertheless not vacuous — it is contingent.** The
   synthetic cases show the tie-break *is* observable when exact ties exist
   near the cut: `two_grids_4x4_sep80` flips the partition on 64/64
   permutations, `grid_6x6_pitch2.54` on 62/64. Notably `three_clusters_2x3`
   has 7 tied merges and flips **0** times — because its cut margin (distance
   from the fcluster threshold to the nearest merge height) is 3.78 mm, so no
   tied merge sits near the cut. **Tie existence is not the risk; ties within
   the cut margin are.** That is the sharp form of the condition, and it is
   what a future regression test should assert.

3. **Given the same partition, nothing else scipy produces leaks through.**
   `_cluster_positions` builds `clusters.setdefault(int(label), ...)` while
   walking positions in input order, then returns `list(clusters.values())`.
   Dict insertion order is first-appearance order of each label *in position
   order*, so the **label integers scipy assigns are not observable** — only
   the partition and the input order are. A Rust port need not reproduce
   scipy's labelling at all, only its partition.

### 1.4 The production path never calls `_cluster_positions`

The sole non-test consumer is `_zone_pour_stitch.py:266`, which passes
`cluster=not exempt` where `exempt = nc in _CONTINUITY_EXEMPT_CLASSES`
(`{"GND", "ACMains", "HighVoltage"}`). Zone eligibility is driven by
`NetClassRules.routing_strategy == "plane_required"`, which **only `ACMains`
and `HighVoltage` declare**. The eligible set is therefore a subset of the
exempt set, so `cluster` is `False` for every zone-eligible net.

Measured on `pcb/temper.kicad_pcb`: 16 zone-eligible nets, all of class
`HighVoltage` or `ACMains`, all exempt. **Nets reaching `_cluster_positions`:
zero.** Since the scipy import is function-local (line 91), scipy is not even
imported on the zone-emission path.

This is a second, independent reason the blocker does not bind — but it is the
weaker of the two, because it depends on a netclass SSOT value that
`_zone_pour_stitch.py:27-35` already documents as having changed once
(2026-07-28). The permutation result in §1.3 is the durable one.

### 1.5 What the survey missed: `zone_emission` has an unrecorded GEOS boundary

`_convex_hull_from_positions` (lines 120–123) calls
`MultiPoint(positions).convex_hull` and `.buffer(margin, join_style=2)`. It runs
for **every** cluster on **every** zone-eligible net regardless of the `cluster`
flag, so it is squarely on the production path. §2.3 of the survey lists
`zone_emission` only under `scipy.cluster.hierarchy`, and lists GEOS boolean
algebra against `obstacle_map`/`routing_space`/`placement_audit` only.

The permutation sweep found it: on real nets, **0** canonical-polygon flips but
**2,141/3,904** s-expression-multiset flips. Attribution probe
(`hull_ring_order_probe`):

| point set | vertices emitted | ring sequence stable under reversal | vertex set stable |
|---|---:|---|---|
| 2 collinear points | 66 | **no** | yes |
| 3-point triangle | 3 | yes | yes |
| 4-point square | 4 | yes | yes |

For ≥3 non-collinear points GEOS `convex_hull` is order-independent. For a
degenerate 2-point cluster it returns a `LineString`; `.buffer(1.0,
join_style=2)` produces a 66-vertex stadium whose exterior ring **starts at a
vertex chosen from input order**. Same copper, different bytes.

Two consequences worth recording:

- The 97 statements move out of the *scipy* blocker, but `zone_emission` still
  carries a GEOS dependency, so it belongs in the survey's systemic GEOS bucket
  rather than in an unqualified PORT. Recommendation in §3.
- A port must preserve **within-cluster point order** to keep the emitted
  `.kicad_pcb` byte-stable. `_cluster_positions` appends in original index
  order; that is a contract a Rust port has to honour, and it is specifiable
  rather than a blocker.

(Incidental, not this spike's to fix: a 2-pad zone emits a 66-vertex polygon
because `join_style=2` mitre does not apply to the round *caps* of a buffered
`LineString`. Flagged, not touched.)

### 1.6 Part 1 verdict

**UNBLOCKED.** The `scipy.cluster.hierarchy` tie-break is not observable in the
emitted zone geometry on any real net of the production board — 0 partition
flips and 0 polygon flips across 3,904 permutations of 61 real position sets —
and the code path is not reached at all under the current netclass SSOT.

**What would overturn it.** Any of:

1. A net whose pad set produces a tied Ward merge *within the cut margin*.
   Synthetic proof this is possible already exists in the measurement
   (`two_grids_4x4_sep80`, 64/64 flips at a 0.16 mm margin). A board that places
   two identical multi-pad footprints on the same rotation and same pitch, both
   on one net, is the realistic shape of that case.
2. `routing_strategy` gaining a `plane_required` class that is not in
   `_CONTINUITY_EXEMPT_CLASSES`, re-activating `cluster=True`. This has moved
   once before.
3. A Rust port that does not preserve within-cluster input order (§1.5) — which
   would break byte parity for reasons that have nothing to do with clustering.

Recommended ledger move (recommendation only, no ledger edited): 97 stmts out of
BLOCKED-on-scipy. Not to unqualified PORT — to the GEOS bucket, whose §1.5
dependency is the real remaining boundary.

---

## Part 2 — `kiutils` in `constraints_design_rules.py`

### 2.0 Was this already decided? **No — the cited verdict does not cover this module**

The brief asked to check first. `docs/wave4-verdicts.yaml` lines 81–86 on `main`
(line 55 as the survey cited it; the file has since grown a preamble) reads:

```yaml
  - pattern: packages/temper-placer/src/temper_placer/io/**
    verdict: MIGRATE
    phase: 3
    note: >-
      KiCad parse/export via the temper-design-bundle and temper-io-types Rust
      seeds. kiutils leaves the boundary at this phase (parent R4).
```

That entry's `pattern` is `.../temper_placer/io/**`. `constraints_design_rules.py`
lives in `.../temper_placer/router_v6/`, matched by the separate `router_v6/**`
entry at line 141 (`MIGRATE`, phase 5, whose note names `channel_skeleton`'s
shapely-Voronoi spike gate but says nothing about kiutils). **The recorded
kiutils note governs the `io/` tree, not this
module.** The survey's §2.3 row cites it as though it settled
`constraints_design_rules` (250 stmts); it does not. This spike therefore does
decide the question rather than re-deriving a settled one — and the answer runs
the opposite way from the citation.

### 2.1 Falsifier, stated before measuring

> **The carve-out fails if `ClearanceMatrix` reaches a third-party primitive of
> its own — kiutils or shapely — anywhere in its method bodies, or if the
> parser half and the matrix half are mutually referential in a way that cannot
> be cut without changing the module's public API. Either finding is a concrete
> refusal.**

### 2.2 Result — the falsifier **half fired**, on a boundary the brief did not name

Measured by `tools/measurements/spike_design_rules_split.py`
(250 module statements, matching the survey exactly):

| Definition | lines | stmts | third-party its own body reaches | consumers outside this module |
|---|---|---:|---|---|
| `RoutingZone` | 30–45 | 7 | — | **none** |
| `ZoneManager` | 48–125 | 33 | **shapely (runtime), numpy (runtime)** | **none** |
| `ClearanceMatrix` | 129–434 | **110** | **none** | `deterministic/stages/setup.py`, `router_v6/constraints_drc_oracle.py`, 2 test modules |
| `DesignRulesParser` | 437–533 | **40** | **kiutils (runtime, function-local)** | `deterministic/stages/setup.py`, `scripts/demo_drc_oracle.py`, 1 test module |
| `_classify_net` | 536–561 | 12 | — | **none** (all name matches elsewhere are unrelated functions) |
| `infer_zones` | 564–639 | 37 | **shapely (runtime)**, kiutils (typing-only) | **none** |

**(a) Does `ClearanceMatrix` genuinely have no kiutils/shapely dependency in its
own methods? Yes — and no.**

- *Yes* in its bodies: 110 statements, zero third-party name references, zero
  local imports. Its only non-stdlib import is `NetClassRules` from
  `temper_placer.core.design_rules`, itself a Phase-2 `MIGRATE` contract type.
- *No* through its field: `zone_manager: ZoneManager | None` (line 152) holds a
  live shapely `STRtree`, and `get_clearance(net_a, net_b, x, y)` delegates to
  `self.zone_manager.get_zone_at(x, y)` at line 194. `DRCOracle` calls the
  four-argument spatial form at **ten** sites
  (`constraints_drc_oracle.py:389,407,427,489,513,557,648,678,713,740`). So the
  GEOS dependency is real, it is on the DRC hot path, and it is inside the
  half the brief called "pure table lookup".

  Measured on the production board: `ClearanceMatrix.parse` builds a
  `ZoneManager` over **96** shapely polygons. But the spatial override only
  fires when `zone.name == "HV"` (line 207), and every zone the parser names is
  `Zone_0…Zone_95`. Over 4,000 seeded samples across 110 real net names and
  in-board coordinates, `get_clearance(a, b, x, y)` differed from
  `get_clearance(a, b)` **0 times**. The STRtree is built, queried from all ten
  DRC sites, and cannot change the answer on this board. That is a
  board-specific dead effect, not a general dissolution — it depends on zone
  naming — so it does **not** license dropping the field.

**(b) Who constructs it, and from what?** Three sites, and only one of them is a
parser:

1. `deterministic/stages/setup.py:55` — `ClearanceMatrix()` populated field by
   field from a `DesignRules`/`PlacementConstraints` object. **No parser
   involved.** This is the live production route when `design_rules` is
   supplied.
2. `deterministic/stages/setup.py:110` — `ClearanceMatrix.parse(state.board)`
   with the *internal* `core.board.Board`. Takes the non-kiutils branch.
3. `DesignRulesParser.create_default()` (setup.py:112, demo script, one test) —
   pure Python defaults, no kiutils.

**(c) Would the carve-out change the public API?** Yes, at exactly one
statement, and less than expected — see §2.4.

### 2.3 The kiutils half is dead code, measurably

Three independent measurements:

1. **`kiutils.board.Board` has no `netClasses` attribute** (kiutils 1.4.8,
   measured; `Board_attributes` in the script output). So
   `ClearanceMatrix.parse`'s dispatch at line 387,
   `if hasattr(board, "netClasses")`, is **False for a kiutils board too**. The
   branch that calls `DesignRulesParser.parse` is unreachable for *any* input.
   The repo already records this fact independently, at
   `io/_parse_nets.py:21` and `:124` — "kiutils 1.4.8 exposes neither
   `setup.defaults` nor `board.netClasses`, so the oracle's two kiutils-driven
   branches never fired." Same defect, second site.
2. **`DesignRulesParser.parse_from_file` — the module's only runtime kiutils
   import (line 509) — has zero callers** anywhere under `packages/`,
   `scripts/`, `benchmarks/`, `tools/`.
3. **`infer_zones` has zero callers**, and it is the *only* user of
   `MultiPoint.convex_hull` / `.buffer` in this module.

`DesignRulesParser.parse` is therefore reachable only from an unreachable
branch and an uncalled function. Its own `netClasses` loop (lines 471–486)
could not fire even if it were reached. The live half of `DesignRulesParser` is
`create_default()` — 11 statements, pure Python.

**This is the answer to the kiutils question and it is stronger than "keep at
the boundary": there is no kiutils boundary in this module to keep.** The
module's kiutils surface is one `TYPE_CHECKING` import (never executed, since
`from __future__ import annotations` is in force at line 10) and one lazy import
in a function nothing calls.

### 2.4 Answering the brief's GEOS question

> "the module also uses GEOS `convex_hull`/`buffer`; establish whether those sit
> in the parser half or the matrix half."

**Neither half as the brief drew them, and they are two different GEOS uses:**

- `MultiPoint.convex_hull` + `.buffer` sit **entirely in `infer_zones`** (lines
  608, 610, 625, 626) — the zone-inference/parser side, and dead.
- `Polygon` / `Point` / `STRtree` sit in **`ZoneManager`**, which is neither
  parser nor matrix: it is a third component, reached *through* a
  `ClearanceMatrix` field, and it is live (§2.2a).

The module is three things, not two.

### 2.5 Carve-out proposal

Viable, and cheaper than the brief's framing. The seam is
`ClearanceMatrix.parse` (lines 366–434, **20 stmts**) — the classmethod that
makes the pure table reference `DesignRulesParser`, `RoutingZone`, and
`ZoneManager`. It is the *only* reason `ClearanceMatrix` names anything outside
itself. Remove it and the remaining **90 statements** reference nothing but
stdlib and `NetClassRules`.

Proposed split (a production change — **specified here, not made**, per the
spike constraint):

| New module | Contents | stmts | Verdict |
|---|---|---:|---|
| `router_v6/clearance_matrix.py` | `ClearanceMatrix` minus `parse` | 90 | **PORT** — pure dict/arithmetic, no third party |
| `router_v6/constraints_zones.py` | `RoutingZone`, `ZoneManager` | 40 | **KEEP** — shapely `STRtree`, the systemic GEOS boundary |
| `router_v6/constraints_design_rules.py` | `DesignRulesParser`, `_classify_net`, `infer_zones`, and `parse` relocated here as a free function | 120 | **Phase 3 formats/IO**, or **RETIRE** the dead parts (§2.6) |

(90 + 40 + 120 = 250; the 11-statement module preamble is counted once, in the
third row.)

API cost, precisely: `ClearanceMatrix.parse` has exactly **one** production
call site (`setup.py:110`) and **zero** test call sites. Moving it to
`DesignRulesParser.from_board(board)` or a free `parse_clearance_matrix(board)`
is a one-line change plus the import. Everything else that touches
`ClearanceMatrix` — `constraints_drc_oracle.py:17,105` and the two test modules
— uses the constructor and the getters, which do not move. Re-exporting
`ClearanceMatrix` from the old module keeps even that at zero.

The `zone_manager` field stays on `ClearanceMatrix` and stays typed
`ZoneManager | None`, so the PORT candidate is 90 statements *with a hole*: a
Rust `ClearanceMatrix` needs an opaque handle to the Python/GEOS zone manager,
or the spatial branch must be hoisted out of `get_clearance` into the caller.
That is the honest cost, and it is the same shape as the survey's
`RoutingSpace.available_area` finding — a GEOS object used as a cross-boundary
*type*.

**Preferred variant.** Given §2.3, the cheaper move is to delete first and
split second: retiring `parse_from_file`, `infer_zones`, and the unreachable
`netClasses` branches removes the kiutils import entirely and shrinks the
parser half to `create_default` + `_classify_net` + the internal-board zone
extraction. The split then falls out with almost nothing left to place. Both
routes are production changes and out of scope here.

### 2.6 Part 2 verdict

**UNBLOCKED on kiutils.** The recorded `wave4-verdicts.yaml` note governs
`io/**` and does not cover this module; measured against kiutils 1.4.8 the
module has no live kiutils code path at all.

**Carve-out: viable.** `ClearanceMatrix` is 110 statements with zero
third-party references in its own bodies (confirmed), of which 90 are free of
any intra-module reference once the 20-statement `parse` classmethod moves. Cost
is one production call site.

**But the falsifier half-fired**, and the doc records it rather than rounding
it away: `ClearanceMatrix.zone_manager` is a live shapely `STRtree` on the DRC
hot path. The carve-out separates `ClearanceMatrix` from *kiutils*, not from
*GEOS*.

Recommended ledger moves (recommendations only — no ledger edited):

| stmts | from | to |
|---:|---|---|
| 90 | BLOCKED (kiutils) | **PORT** — `ClearanceMatrix` minus `parse` |
| 20 | BLOCKED (kiutils) | **Phase 3 formats/IO** — the `parse` seam |
| 40 | BLOCKED (kiutils) | **BLOCKED (GEOS)** — `ZoneManager`/`RoutingZone`, reclassified to the correct blocker |
| 64 | BLOCKED (kiutils) | **DEAD** — `parse_from_file` (5), `infer_zones` (37), `DesignRulesParser.parse` (22, reachable only from those two) |
| 36 | BLOCKED (kiutils) | **PORT / Phase 3** — `create_default` (11), `_classify_net` (12), `DesignRulesParser` class body (2), module preamble (11) |

(90 + 20 + 40 + 64 + 36 = 250.)

Net: of 250 statements the survey put in BLOCKED-on-kiutils, **zero** are
blocked on kiutils.

---

## 3. Recommendations to the ledger (not applied)

`docs/wave4-verdicts.yaml`, `power_pcb_dataset/drc_ceiling.json`, and all
baselines are untouched, per the spike constraints.

1. **Correct the survey's §2.3 kiutils row.** It cites
   `wave4-verdicts.yaml` for a module that entry does not match (§2.0).
2. **Remove `scipy.cluster.hierarchy` from the blocker list.** It was added as
   a new blocker by the survey; it does not survive measurement (§1.6). The
   `scipy.spatial.cKDTree` and GEOS entries the survey added at the same time
   are untouched by this spike and are owned by other agents.
3. **Add `zone_emission` to the GEOS bucket** (§1.5) — it was measured to have
   an order-dependent GEOS serialisation on the production path that §2.3 does
   not record.
4. **Reclassify `constraints_design_rules`'s 250 statements** per the §2.6
   table. The 63 statements measured dead deserve a `RETIRE` verdict with the
   kiutils-1.4.8 evidence attached, alongside the existing `io/_parse_nets.py`
   record of the same defect.
5. **Regression shape, if either surface is ported.** For Part 1, assert the
   condition §1.3 actually identifies: no tied Ward merge height within the cut
   margin, rather than "no ties". For Part 2, pin the byte-for-byte emitted
   zone s-expressions for a fixed input order — the property §1.5 shows is
   order-sensitive.

## 4. Unverified / explicit UNKNOWN

- **Only one board was measured.** `pcb/temper.kicad_pcb`. Part 1's real-data
  result is a property of this board's pad geometry, not a theorem. The
  synthetic cases show the failing shape exists; whether any *other* board in
  `power_pcb_dataset/` produces it is **UNKNOWN** — the script takes a board
  path argument, so this is one command to answer.
- **No Rust was written or built**, so no Rust-vs-Python differential exists for
  either surface. The Part 1 argument is that scipy's tie-break is not
  observable, not that some particular Rust Ward implementation matches scipy.
- **scipy version.** Measured at 1.16.3 (the repo `.venv`). scipy's Ward
  tie-break is not a documented API guarantee; a version bump could change it.
  That is an argument *for* the verdict — the boundary is already unpinned in
  Python — but the sensitivity was not measured across versions.
- **`ZoneManager`'s zero-effect result is board-specific.** 0/4,000 differing
  samples holds because this board's zones are named `Zone_N` and the override
  requires the literal name `"HV"`. Whether that naming is intentional was not
  investigated; it is not this spike's question.
- The 66-vertex 2-pad zone polygon (§1.5) was observed, not judged.

## 5. Reproduction

```
python tools/measurements/spike_zone_cluster_tie_invariance.py [BOARD]
python tools/measurements/spike_design_rules_split.py [MODULE.py ...]
```

Both write JSON to stdout, are read-only, and import no Rust extension.
